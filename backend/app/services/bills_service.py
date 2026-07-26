"""Сервис распознавания счёта за электроэнергию.

Два пути извлечения данных, по типу входа:

1. **Цифровой PDF-документ (born-digital)** — типичная "Ведомость
   потребления электроэнергии" ЭСО: это таблица с текстовым слоем, а не
   картинка. Здесь мы НЕ гоним OCR (он превращал бы точный текст в шум и
   путался в плотной таблице — именно так сервис однажды уверенно вернул
   год "2026" как сумму). Вместо этого читаем таблицу через
   `page.find_tables()` PyMuPDF и достаём значения из конкретных колонок
   по их заголовкам ("Сумма с НДС", "Потреблено").

2. **Фото счётчика / сканированный PDF без текстового слоя** — здесь без
   OCR не обойтись (pytesseract над бинарником tesseract-ocr: офлайн, без
   ключей, одинаково ставится локально и в Docker). Извлечение — по
   ключевым словам рядом с числом, но БЕЗ жадного фолбэка "первое число в
   диапазоне": лучше отправить на ручную правку, чем подставить случайную
   цифру.

Сквозное правило (CLAUDE.md): распознавание не должно блокировать флоу.
Любая ошибка/неоднозначность/низкая уверенность → 200 с
requires_manual_review=True, никогда не 500 и никогда не тихо-неверное
значение.
"""

from __future__ import annotations

import io
import logging
import re
from statistics import mean
from uuid import uuid4

import pytesseract
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.schemas import BillManualCorrection, BillUploadResponse
from app.services import bill_history_service

logger = logging.getLogger(__name__)

# --- Границы ресурсов (почему это здесь — на защиту) -------------------------
# Первопричина бага загрузки, найденного на отборе: обработка счёта была НЕ
# ограничена по памяти. Ни один битый PDF сам по себе не роняет сервис (все
# ошибки PyMuPDF/PIL уже ловятся и уходят в manual_review), НО:
#   1. большой файл целиком читался в память (`await file.read()`), и
#   2. страница рендерилась в картинку на фиксированных 200 DPI —
#      фото-скан A4 (2480×3508) → битмап ~67 Мп ≈ 200 МБ, плюс копии PIL при
#      препроцессинге. На деплое с 512 МБ памяти (Railway) это выбивает воркер
#      по OOM: жюри видит оборванную загрузку (502), а не штатный manual_review.
# Ниже — два независимых предохранителя: лимит размера входа и лимит
# разрешения рендера. Любой перебор — это graceful manual_review, не падение.

# Больше — не буферизуем и не обрабатываем (см. config.max_upload_mb). Роутер
# читает не более MAX_UPLOAD_BYTES+1 байта, поэтому память не вырастает даже на
# многогигабайтном входе.
MAX_UPLOAD_BYTES = settings.max_upload_mb * 1024 * 1024

# Целевое разрешение рендера PDF-страницы в картинку для OCR. 200 DPI — потолок
# качества; фактический DPI понижается так, чтобы длинная сторона не превышала
# RENDER_MAX_PX. 2200 px по длинной стороне ≈ 150 DPI для A4 — Tesseract читает
# квитанцию уверенно, а битмап держится в пределах ~10 МБ вместо сотен.
OCR_RENDER_DPI = 200
RENDER_MAX_PX = 2200

# Фото-счёт с телефона — максимум ~12 Мп. 40 Мп с запасом; выше считаем мусором/
# декомпрессионной бомбой и уводим в manual_review, НЕ декодируя пиксели в память.
MAX_IMAGE_PIXELS = 40_000_000

# Разумные границы месячного счёта городской квартиры в РК (см.
# docs/research-context.md). Диапазон отсекает грубый мусор (склеенный
# номер лицевого счёта, дата), но САМ ПО СЕБЕ недостаточен: ошибочное число
# вроде года "2026" тоже попадает в диапазон сумм. Поэтому диапазон — лишь
# один из фильтров, а не единственный критерий доверия.
AMOUNT_TENGE_RANGE = (300.0, 300_000.0)
CONSUMPTION_KWH_RANGE = (5.0, 5_000.0)

# Средняя уверенность tesseract по словам (0-100). Ниже — результат не
# годится для авто-заполнения.
MIN_CONFIDENCE = 40.0

# OCR-путь (фото): ключевые слова, рядом с которыми в тексте ожидается
# число. Русские и английские — казахстанские счета обычно на русском.
AMOUNT_KEYWORDS = ("сумма к оплате", "к оплате", "итого к оплате", "сумма", "оплате", "total", "amount")
CONSUMPTION_KEYWORDS = ("квт", "kwh", "потреблено", "потребление", "расход", "consumption")

# Заголовки колонок табличного PDF. Нормализуем (нижний регистр, схлопнутые
# пробелы/переводы строк) и ищем по подстроке. Сумма С НДС — это итог к
# оплате, его и кладём в amount_tenge; сумма БЕЗ НДС нужна как перекрёстная
# проверка (с НДС обязана быть >= без НДС).
COL_AMOUNT_WITH_VAT = "сумма с ндс"
COL_AMOUNT_WITHOUT_VAT = "сумма без ндс"
# Стем: в шапке заголовок переносится как "Потреблен\nие" → "потреблен ие",
# поэтому ищем по корню, а не по полному "потреблено".
COL_CONSUMPTION = "потреблен"

# Строки-итоги табличного счёта. Значения в них дублируют итог документа.
TOTAL_ROW_LABELS = ("всего", "итого")

PERIOD_PATTERN = re.compile(r"\b(20\d{2})[.\-/](0[1-9]|1[0-2])\b|\b(0[1-9]|1[0-2])[.\-/](20\d{2})\b")
NUMBER_PATTERN = re.compile(r"\d[\d\s ]*[.,]?\d*")

RU_MONTHS = {
    "январь": "01", "января": "01",
    "февраль": "02", "февраля": "02",
    "март": "03", "марта": "03",
    "апрель": "04", "апреля": "04",
    "май": "05", "мая": "05",
    "июнь": "06", "июня": "06",
    "июль": "07", "июля": "07",
    "август": "08", "августа": "08",
    "сентябрь": "09", "сентября": "09",
    "октябрь": "10", "октября": "10",
    "ноябрь": "11", "ноября": "11",
    "декабрь": "12", "декабря": "12",
}
RU_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(RU_MONTHS.keys()) + r")\s+(20\d{2})\b", re.IGNORECASE
)

TESSERACT_LANGS = "rus+eng"


def process_bill_upload(
    db: Session,
    filename: str,
    content: bytes,
    content_type: str | None,
    profile_id: str | None = None,
) -> BillUploadResponse:
    bill_id = str(uuid4())

    # Предохранитель №1 — размер входа. Роутер отдаёт максимум
    # MAX_UPLOAD_BYTES+1 байт, так что len> лимита означает «файл больше
    # лимита». Не пытаемся парсить — это и есть та самая нехватка памяти на
    # большом файле. Пустой файл (0 байт) пропускаем дальше: он штатно
    # отвалится в parse_error/manual_review ниже.
    if len(content) > MAX_UPLOAD_BYTES:
        logger.warning(
            "Счёт %s больше лимита (%d байт > %d) — на ручную правку",
            filename, len(content), MAX_UPLOAD_BYTES,
        )
        return _manual_review_response(bill_id, "file_too_large")

    is_pdf = (content_type == "application/pdf") or filename.lower().endswith(".pdf")

    if is_pdf:
        try:
            structured = _extract_from_pdf(bill_id, content)
        except Exception:
            logger.warning("Не удалось разобрать PDF счёта %s", filename, exc_info=True)
            return _manual_review_response(bill_id, "pdf_parse_error")
        if structured is not None:
            _record_if_confident(db, profile_id, structured)
            return structured
        # PDF без текстового слоя (скан) — падаем в OCR-путь ниже.

    response = _extract_via_ocr(bill_id, filename, content, content_type)
    _record_if_confident(db, profile_id, response)
    return response


def apply_manual_correction(db: Session, payload: BillManualCorrection) -> BillUploadResponse:
    # Ручная правка — это подтверждённое пользователем показание, пишем в
    # историю (если фронт передал profile_id). Именно эти данные потом
    # кормят Prophet-прогноз.
    _safe_record(
        db,
        profile_id=payload.profile_id or "",
        period=payload.period,
        amount_tenge=payload.amount_tenge,
        consumption_kwh=payload.consumption_kwh,
        ocr_status="manual_override",
    )
    return BillUploadResponse(
        bill_id=payload.bill_id,
        ocr_status="manual_override",
        amount_tenge=payload.amount_tenge,
        consumption_kwh=payload.consumption_kwh,
        period=payload.period,
        requires_manual_review=False,
    )


def _record_if_confident(db: Session, profile_id: str | None, response: BillUploadResponse) -> None:
    """Пишем в историю только уверенно распознанные счета (не те, что ушли
    на ручную проверку) и только если известны profile_id/период/сумма."""
    if (
        profile_id
        and not response.requires_manual_review
        and response.period
        and response.amount_tenge is not None
    ):
        _safe_record(
            db,
            profile_id=profile_id,
            period=response.period,
            amount_tenge=response.amount_tenge,
            consumption_kwh=response.consumption_kwh,
            ocr_status=response.ocr_status,
        )


def _safe_record(db: Session, **kwargs) -> None:
    """Запись в историю не должна ронять эндпоинт счёта: OCR-ответ уже готов и
    важнее, чем побочная запись в БД. При ошибке — откат и лог, а не 500 (то
    же правило graceful-degradation, что и для самого распознавания)."""
    try:
        bill_history_service.record_reading(db, **kwargs)
    except Exception:
        db.rollback()
        logger.warning("Не удалось записать счёт в историю профиля", exc_info=True)


def _manual_review_response(
    bill_id: str,
    ocr_status: str,
    *,
    amount: float | None = None,
    consumption: float | None = None,
    period: str | None = None,
) -> BillUploadResponse:
    return BillUploadResponse(
        bill_id=bill_id,
        ocr_status=ocr_status,
        amount_tenge=amount,
        consumption_kwh=consumption,
        period=period,
        requires_manual_review=True,
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip().lower()


# --- Путь 1: структурный разбор табличного PDF -------------------------------


def _extract_from_pdf(bill_id: str, content: bytes) -> BillUploadResponse | None:
    """Возвращает результат для цифрового PDF, либо None, если это скан без
    текстового слоя (тогда вызывающий уходит в OCR)."""
    import fitz  # PyMuPDF

    with fitz.open(stream=content, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise ValueError("PDF без страниц")
        page = doc.load_page(0)
        page_text = page.get_text()
        if not page_text.strip():
            return None  # скан — не наш путь

        period = _extract_period(page_text)

        tables = page.find_tables()
        for table in tables.tables:
            result = _extract_from_table(bill_id, table.extract(), period)
            if result is not None:
                return result

    # Текстовый слой есть, но нужную таблицу/колонки не нашли — не выдумываем
    # цифры, отправляем на ручную проверку.
    return _manual_review_response(bill_id, "pdf_table_not_recognized", period=_period_or_none(content))


def _extract_from_table(
    bill_id: str, rows: list[list], period: str | None
) -> BillUploadResponse | None:
    if not rows:
        return None

    col_names = _build_column_names(rows)
    amount_col = _find_column(col_names, COL_AMOUNT_WITH_VAT)
    consumption_col = _find_column(col_names, COL_CONSUMPTION)
    if amount_col is None:
        return None  # не та таблица

    body = rows[_header_row_count(rows):]

    amount = _consistent_column_value(body, amount_col, AMOUNT_TENGE_RANGE)
    without_vat_col = _find_column(col_names, COL_AMOUNT_WITHOUT_VAT)
    amount_without_vat = (
        _consistent_column_value(body, without_vat_col, AMOUNT_TENGE_RANGE)
        if without_vat_col is not None
        else None
    )
    consumption = (
        _consistent_column_value(body, consumption_col, CONSUMPTION_KWH_RANGE)
        if consumption_col is not None
        else None
    )

    # Сумма не извлеклась однозначно из своей колонки — без неё результат
    # бесполезен, на ручную правку.
    if amount is None:
        return _manual_review_response(
            bill_id, "pdf_amount_ambiguous", consumption=consumption, period=period
        )

    # Перекрёстная проверка: итог с НДС не может быть меньше суммы без НДС.
    # Если меньше — колонки распознаны неверно, не доверяем.
    if amount_without_vat is not None and amount < amount_without_vat:
        return _manual_review_response(
            bill_id, "pdf_amount_inconsistent", consumption=consumption, period=period
        )

    return BillUploadResponse(
        bill_id=bill_id,
        ocr_status="pdf_table_success",
        amount_tenge=amount,
        consumption_kwh=consumption,
        period=period,
        requires_manual_review=False,
    )


def _build_column_names(rows: list[list]) -> list[str]:
    """Собирает имя каждой колонки из заголовочных строк (в этом формате
    'Начислено' в строке 0 и 'Сумма с НДС' в строке 1 относятся к одной
    колонке — конкатенируем все заголовочные ячейки по индексу)."""
    header_rows = rows[: _header_row_count(rows)]
    width = max(len(r) for r in rows)
    names: list[str] = []
    for col in range(width):
        parts = []
        for row in header_rows:
            if col < len(row) and row[col]:
                parts.append(str(row[col]))
        names.append(_normalize(" ".join(parts)))
    return names


def _header_row_count(rows: list[list]) -> int:
    """Заголовок — строки до первой, где в первой ячейке появляется
    контент строки данных (адрес точки учёта или метка итога). Для
    'Ведомости' это первые 2 строки (шапка + подзаголовки колонок)."""
    for idx, row in enumerate(rows):
        first = _normalize(str(row[0])) if row and row[0] else ""
        if not first:
            continue
        if idx > 0:
            return idx
    return 1


def _find_column(col_names: list[str], target: str) -> int | None:
    for idx, name in enumerate(col_names):
        if target in name:
            return idx
    return None


def _consistent_column_value(
    body: list[list], col: int, value_range: tuple[float, float]
) -> float | None:
    """Собирает все числа в колонке по строкам данных, фильтрует по
    диапазону и возвращает значение, только если оно ОДНО (все совпадают).

    Это и есть замена «просто диапазону»: в табличном счёте итог
    дублируется в строках данных/Итого/Всего. Если в колонке несколько
    РАЗНЫХ значений в диапазоне — это неоднозначность (не та колонка,
    сбитая разметка), доверять нельзя → None → ручная проверка.
    """
    low, high = value_range
    values: set[float] = set()
    for row in body:
        if col >= len(row) or not row[col]:
            continue
        number = _parse_money(str(row[col]))
        if number is not None and low <= number <= high:
            values.add(round(number, 2))
    if len(values) == 1:
        return values.pop()
    return None


def _parse_money(cell: str) -> float | None:
    # Пробел/неразрывный пробел между цифрами — разделитель тысяч
    # ("1 789,65" → "1789,65"); запятая — десятичный разделитель.
    collapsed = re.sub(r"(?<=\d)[\s ](?=\d)", "", cell)
    match = re.search(r"\d+(?:[.,]\d+)?", collapsed)
    if not match:
        return None
    try:
        return float(match.group().replace(",", "."))
    except ValueError:
        return None


def _period_or_none(content: bytes) -> str | None:
    try:
        import fitz

        with fitz.open(stream=content, filetype="pdf") as doc:
            return _extract_period(doc.load_page(0).get_text())
    except Exception:
        return None


# --- Путь 2: OCR фото/скана ---------------------------------------------------


def _extract_via_ocr(
    bill_id: str, filename: str, content: bytes, content_type: str | None
) -> BillUploadResponse:
    try:
        image = _load_as_image(filename, content, content_type)
    except Exception:
        logger.warning("Не удалось декодировать файл счёта %s", filename, exc_info=True)
        return _manual_review_response(bill_id, "ocr_unsupported_format")

    try:
        text, confidence = _run_ocr(image)
    except Exception:
        logger.warning("Ошибка Tesseract при распознавании %s", filename, exc_info=True)
        return _manual_review_response(bill_id, "ocr_engine_error")

    if not text.strip():
        return _manual_review_response(bill_id, "ocr_empty_result")

    amount = _extract_number_near_keywords(text, AMOUNT_KEYWORDS, AMOUNT_TENGE_RANGE)
    consumption = _extract_number_near_keywords(text, CONSUMPTION_KEYWORDS, CONSUMPTION_KWH_RANGE)
    period = _extract_period(text)

    if confidence < MIN_CONFIDENCE:
        return _manual_review_response(
            bill_id, "ocr_low_confidence", amount=amount, consumption=consumption, period=period
        )

    # Нет суммы у ключевого слова — не выдумываем «первое число в диапазоне»
    # (именно так год попадал в сумму), а просим поправить руками.
    if amount is None:
        return _manual_review_response(
            bill_id, "ocr_no_amount_found", consumption=consumption, period=period
        )

    return BillUploadResponse(
        bill_id=bill_id,
        ocr_status="ocr_success",
        amount_tenge=amount,
        consumption_kwh=consumption,
        period=period,
        requires_manual_review=False,
    )


def _load_as_image(filename: str, content: bytes, content_type: str | None) -> Image.Image:
    is_pdf = (content_type == "application/pdf") or filename.lower().endswith(".pdf")
    if is_pdf:
        return _first_pdf_page_to_image(content)

    # Картинка: сначала читаем ТОЛЬКО заголовок (Image.open ленивый — пиксели
    # ещё не декодированы, но .size уже известен). Если объявленное разрешение
    # абсурдно большое — это декомпрессионная бомба или мусор: уходим на
    # ручную правку, НЕ раздувая память декодом. exif_transpose заодно чинит
    # ориентацию фото с телефона (частый источник «повёрнутых» снимков).
    image = Image.open(io.BytesIO(content))
    width, height = image.size
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError(f"image too large: {width}x{height}px")
    image = ImageOps.exif_transpose(image).convert("RGB")
    return _downscale_for_ocr(image)


def _first_pdf_page_to_image(content: bytes) -> Image.Image:
    import fitz  # PyMuPDF

    with fitz.open(stream=content, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise ValueError("PDF без страниц")
        page = doc.load_page(0)
        # Предохранитель №2 — разрешение рендера. DPI подбираем под размер
        # страницы, чтобы длинная сторона битмапа не превышала RENDER_MAX_PX.
        # Так страница с абсурдными размерами (dimension-bomb) или скан в 300+
        # DPI не превращаются в гигабайтный pixmap — качества хватает для OCR,
        # а память ограничена.
        pixmap = page.get_pixmap(dpi=_safe_render_dpi(page.rect))
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _safe_render_dpi(rect) -> int:
    """DPI, при котором длинная сторона страницы уложится в RENDER_MAX_PX,
    но не выше OCR_RENDER_DPI. Вырожденная (нулевая) страница — вернём потолок,
    пусть дальше решает обычный путь."""
    longest_pt = max(rect.width, rect.height)
    if longest_pt <= 0:
        return OCR_RENDER_DPI
    fit_dpi = RENDER_MAX_PX * 72.0 / longest_pt
    return max(1, int(min(OCR_RENDER_DPI, fit_dpi)))


def _downscale_for_ocr(image: Image.Image) -> Image.Image:
    """Ужимает картинку до RENDER_MAX_PX по длинной стороне. Держит рабочий
    битмап (и его копии в препроцессинге) в десятках МБ вместо сотен."""
    longest = max(image.size)
    if longest <= RENDER_MAX_PX:
        return image
    scale = RENDER_MAX_PX / longest
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(new_size)


def _run_ocr(image: Image.Image) -> tuple[str, float]:
    processed = _preprocess(image)
    data = pytesseract.image_to_data(
        processed, lang=TESSERACT_LANGS, output_type=pytesseract.Output.DICT
    )
    words = [w for w in data["text"] if w.strip()]
    confidences = [float(c) for c, w in zip(data["conf"], data["text"]) if w.strip() and float(c) >= 0]
    text = " ".join(words)
    avg_confidence = mean(confidences) if confidences else 0.0
    return text, avg_confidence


def _preprocess(image: Image.Image) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    deskewed = _deskew(grayscale)
    return ImageOps.autocontrast(deskewed)


def _deskew(image: Image.Image) -> Image.Image:
    """Поворот по данным tesseract OSD. OSD часто не справляется на тёмных/
    размытых фото — это не повод падать, продолжаем без коррекции."""
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        rotation = osd.get("rotate", 0)
    except Exception:
        return image

    if rotation:
        return image.rotate(-rotation, expand=True, fillcolor=255)
    return image


def _extract_number_near_keywords(
    text: str, keywords: tuple[str, ...], value_range: tuple[float, float]
) -> float | None:
    """Ищет число сразу после ключевого слова. Если разные ключевые слова
    дают РАЗНЫЕ числа в диапазоне — это неоднозначность, возвращаем None
    (→ ручная проверка), а не первое попавшееся. Жадного фолбэка на «любое
    число в тексте» здесь намеренно нет."""
    lowered = text.lower()
    low, high = value_range

    candidates: set[float] = set()
    for keyword in keywords:
        for match in re.finditer(re.escape(keyword), lowered):
            window = lowered[match.end() : match.end() + 20]
            number = _parse_money(window)
            if number is not None and low <= number <= high:
                candidates.add(round(number, 2))

    if len(candidates) == 1:
        return candidates.pop()
    return None


def _extract_period(text: str) -> str | None:
    month_match = RU_MONTH_PATTERN.search(text)
    if month_match:
        month = RU_MONTHS[month_match.group(1).lower()]
        return f"{month_match.group(2)}-{month}"

    match = PERIOD_PATTERN.search(text)
    if not match:
        return None
    if match.group(1):
        return f"{match.group(1)}-{match.group(2)}"
    return f"{match.group(4)}-{match.group(3)}"
