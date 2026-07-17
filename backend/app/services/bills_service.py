"""OCR-сервис для загрузки счёта.

Выбор движка — pytesseract (обёртка над бинарником tesseract-ocr):
единственный OCR, который не требует облачного API/ключей и одинаково
просто ставится и локально (brew install tesseract), и в Docker
(apt-get install tesseract-ocr) — то есть демо не зависит от сети во время
записи видео. PDF рендерится в изображение через PyMuPDF (pymupdf) — это
чистый Python-wheel без системной зависимости (в отличие от
pdf2image/poppler), поэтому не плодим лишний apt-пакет только ради PDF.

Ключевое правило из CLAUDE.md: OCR не должен блокировать флоу. Поэтому
единственная точка выхода с ошибкой — `_manual_review_response`: что бы ни
пошло не так (нечитаемый файл, tesseract не нашёл текст, распознанное
число выглядит как мусор), результат всегда 200 с
requires_manual_review=True, никогда не 500.
"""

from __future__ import annotations

import io
import logging
import re
from statistics import mean
from uuid import uuid4

import pytesseract
from PIL import Image, ImageOps

from app.models.schemas import BillManualCorrection, BillUploadResponse

logger = logging.getLogger(__name__)

# Разумные границы для месячного счёта городской квартиры в РК (см.
# docs/research-context.md). Число вне диапазона почти наверняка мусор OCR
# (склеенный номер лицевого счёта, дата, опечатка), а не реальная сумма —
# отдаём его в ручную проверку вместо того, чтобы показать пользователю
# счёт на 3 миллиона тенге.
AMOUNT_TENGE_RANGE = (500.0, 300_000.0)
CONSUMPTION_KWH_RANGE = (5.0, 5_000.0)

# Средняя уверенность tesseract по распознанным словам (0-100). Ниже —
# считаем результат непригодным для авто-заполнения.
MIN_CONFIDENCE = 40.0

# Казахстанские счета обычно на русском, поэтому ищем сумму/потребление по
# русским и английским ключевым словам рядом с числом.
AMOUNT_KEYWORDS = ("сумма", "оплате", "итого", "total", "amount")
CONSUMPTION_KEYWORDS = ("квт", "kwh", "потребление", "расход", "consumption")

PERIOD_PATTERN = re.compile(r"\b(20\d{2})[.\-/](0[1-9]|1[0-2])\b|\b(0[1-9]|1[0-2])[.\-/](20\d{2})\b")
NUMBER_PATTERN = re.compile(r"\d[\d\s]*[.,]?\d*")

TESSERACT_LANGS = "rus+eng"


def process_bill_upload(filename: str, content: bytes, content_type: str | None) -> BillUploadResponse:
    bill_id = str(uuid4())

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

    if confidence < MIN_CONFIDENCE:
        return _manual_review_response(
            bill_id,
            "ocr_low_confidence",
            amount=_extract_number_near_keywords(text, AMOUNT_KEYWORDS, AMOUNT_TENGE_RANGE),
            consumption=_extract_number_near_keywords(text, CONSUMPTION_KEYWORDS, CONSUMPTION_KWH_RANGE),
            period=_extract_period(text),
        )

    amount = _extract_number_near_keywords(text, AMOUNT_KEYWORDS, AMOUNT_TENGE_RANGE)
    consumption = _extract_number_near_keywords(text, CONSUMPTION_KEYWORDS, CONSUMPTION_KWH_RANGE)
    period = _extract_period(text)

    if amount is None:
        # Без суммы результат бесполезен для прогноза, даже если остальное
        # распозналось — просим поправить руками.
        return _manual_review_response(bill_id, "ocr_no_amount_found", consumption=consumption, period=period)

    return BillUploadResponse(
        bill_id=bill_id,
        ocr_status="ocr_success",
        amount_tenge=amount,
        consumption_kwh=consumption,
        period=period,
        requires_manual_review=False,
    )


def apply_manual_correction(payload: BillManualCorrection) -> BillUploadResponse:
    return BillUploadResponse(
        bill_id=payload.bill_id,
        ocr_status="manual_override",
        amount_tenge=payload.amount_tenge,
        consumption_kwh=payload.consumption_kwh,
        period=payload.period,
        requires_manual_review=False,
    )


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


def _load_as_image(filename: str, content: bytes, content_type: str | None) -> Image.Image:
    is_pdf = (content_type == "application/pdf") or filename.lower().endswith(".pdf")
    if is_pdf:
        return _first_pdf_page_to_image(content)
    return Image.open(io.BytesIO(content)).convert("RGB")


def _first_pdf_page_to_image(content: bytes) -> Image.Image:
    # Импорт внутри функции: PDF — не основной путь загрузки счёта (чаще
    # фото со счётчика), нет смысла тянуть PyMuPDF при каждом запуске сервиса.
    import fitz  # PyMuPDF

    with fitz.open(stream=content, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise ValueError("PDF без страниц")
        page = doc.load_page(0)
        pixmap = page.get_pixmap(dpi=200)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


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
    """Поворачивает изображение по данным tesseract OSD (orientation and
    script detection). OSD часто не справляется на тёмных/размытых фото —
    это не повод падать, просто продолжаем без коррекции поворота."""
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
    lowered = text.lower()
    low, high = value_range

    candidates: list[float] = []
    for keyword in keywords:
        for match in re.finditer(re.escape(keyword), lowered):
            window = lowered[match.end() : match.end() + 30]
            number = _parse_first_number(window)
            if number is not None and low <= number <= high:
                candidates.append(number)

    if candidates:
        return candidates[0]

    # Ключевое слово не нашлось (или OCR его исказил) — как fallback берём
    # первое число во всём тексте, попадающее в разумный диапазон.
    for match in NUMBER_PATTERN.finditer(text):
        number = _parse_first_number(match.group())
        if number is not None and low <= number <= high:
            return number

    return None


def _parse_first_number(fragment: str) -> float | None:
    match = NUMBER_PATTERN.search(fragment)
    if not match:
        return None
    raw = match.group().replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_period(text: str) -> str | None:
    match = PERIOD_PATTERN.search(text)
    if not match:
        return None
    if match.group(1):
        return f"{match.group(1)}-{match.group(2)}"
    return f"{match.group(4)}-{match.group(3)}"
