"""Регрессионные тесты распознавания счёта.

Два пласта:

1. Исходный баг точности — `test_real_kz_receipt_extracts_correct_values`:
   на реальной табличной квитанции ЭСО сервис когда-то уверенно возвращал год
   "2026" как сумму. Fixture — настоящий born-digital PDF ЭСО, лежит в
   tests/fixtures/.

2. Баг устойчивости загрузки, найденный жюри на отборе (этот файл его
   покрывает целиком). Первопричина — обработка счёта была НЕ ограничена по
   памяти: небольшой «скан в PDF», где размер страницы в пунктах равен размеру
   картинки в пикселях, рендерился в ~67-Мп битмап (~200 МБ) на фиксированных
   200 DPI и выбивал воркер по OOM на деплое с 512 МБ. Ни один битый PDF сам по
   себе не ронял сервис (ошибки PyMuPDF/PIL уже ловятся), падала именно память.
   Тесты ниже проверяют оба предохранителя (лимит размера входа и лимит
   разрешения рендера) и то, что КАЖДЫЙ проблемный вход даёт
   requires_manual_review=True с суммой None, а не падение и не догадку.
"""

import io
import struct
import zlib
from pathlib import Path

import fitz  # PyMuPDF — та же версия, что в проде
import pytest
from PIL import Image, ImageDraw

from app.services.bills_service import (
    MAX_IMAGE_PIXELS,
    MAX_UPLOAD_BYTES,
    OCR_RENDER_DPI,
    RENDER_MAX_PX,
    _safe_render_dpi,
    process_bill_upload,
)

FIXTURES = Path(__file__).parent / "fixtures"
KZ_RECEIPT = FIXTURES / "sample_receipt_kz.pdf"


def _read(path: Path) -> bytes:
    return path.read_bytes()


# --- Строим проблемные PDF/картинки той же PyMuPDF/PIL, что в проде ----------


def _text_pdf(*pages: str) -> bytes:
    """Born-digital PDF с текстовым слоем (по странице на аргумент)."""
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _blank_page_pdf(width_pt: float, height_pt: float) -> bytes:
    """Страница без текстового слоя заданного размера → путь OCR-рендера.
    Большие размеры (14000pt) — это «dimension bomb»."""
    doc = fitz.open()
    doc.new_page(width=width_pt, height=height_pt)
    data = doc.tobytes()
    doc.close()
    return data


def _rotated_text_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Сумма с НДС: 1789,65   Потреблено: 70 кВт·ч   июнь 2026")
    page.set_rotation(90)
    data = doc.tobytes()
    doc.close()
    return data


def _encrypted_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Сумма с НДС: 1789,65 июнь 2026")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    doc.close()
    return data


def _scan_to_pdf_pointsize() -> bytes:
    """«Скан в PDF»: размер страницы в пунктах == размеру картинки в пикселях
    (2480×3508). Именно такой файл рендерился в 67-Мп битмап на dpi=200 и
    выбивал воркер по памяти — при этом сам файл крошечный (JPEG). Текстового
    слоя нет → идёт в OCR-рендер."""
    img = Image.new("RGB", (2480, 3508), "white")
    ImageDraw.Draw(img).text((200, 400), "Summa 1789 tg Potrebleno 70 kWt iyun 2026", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    doc = fitz.open()
    page = doc.new_page(width=2480, height=3508)
    page.insert_image(page.rect, stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


def _png_with_declared_size(width: int, height: int) -> bytes:
    """PNG, объявляющий в заголовке (IHDR) огромный размер, но без пиксельных
    данных. Image.open прочитает .size из заголовка — этого хватает проверить
    предохранитель MAX_IMAGE_PIXELS, НЕ аллоцируя гигабайты (декомпрессионная
    бомба)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-бит RGB
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


# --- 1. Исходный баг точности (born-digital таблица) -------------------------


def test_real_kz_receipt_extracts_correct_values(db):
    """Табличный PDF ЭСО: реальные значения — 1789.65 ₸ (сумма с НДС),
    70 кВт·ч, июнь 2026. Раньше сервис возвращал 2026/6 и success."""
    result = process_bill_upload(
        db,
        filename="sample_receipt_kz.pdf",
        content=_read(KZ_RECEIPT),
        content_type="application/pdf",
    )

    assert result.ocr_status == "pdf_table_success"
    assert result.requires_manual_review is False
    assert result.amount_tenge == pytest.approx(1789.65)
    assert result.consumption_kwh == pytest.approx(70.0)
    assert result.period == "2026-06"

    # Явная защита от прежнего бага: год/мелкие числа больше не подставляются.
    assert result.amount_tenge != 2026
    assert result.consumption_kwh != 6


# --- 2. Предохранитель №1: размер входа --------------------------------------


def test_oversized_file_goes_to_manual_review(db):
    """Вход больше лимита → manual_review без попытки распарсить/отрендерить.
    Это отсекает нехватку памяти на большом файле до начала обработки."""
    payload = b"%PDF-1.4\n" + b"0" * MAX_UPLOAD_BYTES  # > лимита
    result = process_bill_upload(db, "big.pdf", payload, "application/pdf")
    assert result.ocr_status == "file_too_large"
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


def test_at_limit_file_not_rejected_by_size(db):
    """Граница: ровно лимит — НЕ file_too_large (отвалится позже как мусор, но
    не по размеру). Защита от off-by-one в проверке размера."""
    payload = b"0" * MAX_UPLOAD_BYTES
    result = process_bill_upload(db, "edge.pdf", payload, "application/pdf")
    assert result.ocr_status != "file_too_large"
    assert result.requires_manual_review is True


# --- 3. Предохранитель №2: разрешение рендера --------------------------------


def test_scan_to_pdf_pointsize_is_memory_bounded(db):
    """Крошечный (<10 МБ) «скан в PDF» с page-size == pixel-size: раньше
    рендерился в ~67 Мп (~200 МБ) на dpi=200 и ронял воркер по памяти. Теперь →
    штатный manual review без падения (именно рендер был проблемой, не размер —
    файл заведомо меньше лимита)."""
    data = _scan_to_pdf_pointsize()
    assert len(data) < MAX_UPLOAD_BYTES
    result = process_bill_upload(db, "scan.pdf", data, "application/pdf")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


@pytest.mark.parametrize("dims", [(595, 842), (2480, 3508), (14000, 14000), (100, 100)])
def test_render_dpi_keeps_bitmap_bounded(dims):
    """_safe_render_dpi гарантирует для ЛЮБОЙ геометрии: длинная сторона
    рендера ≤ RENDER_MAX_PX и DPI ≤ потолка. Это и держит битмап в десятках МБ
    вместо сотен."""
    rect = fitz.Rect(0, 0, *dims)
    dpi = _safe_render_dpi(rect)
    assert 1 <= dpi <= OCR_RENDER_DPI
    longest_px = max(dims) * dpi / 72.0
    assert longest_px <= RENDER_MAX_PX + 1


def test_render_dpi_degenerate_page():
    """Вырожденная (нулевая) страница не делит на ноль — возвращает потолок."""
    assert _safe_render_dpi(fitz.Rect(0, 0, 0, 0)) == OCR_RENDER_DPI


def test_dimension_bomb_pdf_no_crash(db):
    """PDF с абсурдно большой страницей (14000×14000pt) → manual review без
    гигантской аллокации."""
    result = process_bill_upload(db, "bomb.pdf", _blank_page_pdf(14000, 14000), "application/pdf")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


def test_decompression_bomb_image_guarded(db):
    """Картинка с огромным объявленным разрешением → manual review БЕЗ
    декодирования пикселей в память (проверка по заголовку)."""
    huge = _png_with_declared_size(40000, 40000)  # 1.6 млрд px > MAX_IMAGE_PIXELS
    assert 40000 * 40000 > MAX_IMAGE_PIXELS
    result = process_bill_upload(db, "bomb.png", huge, "image/png")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


# --- 4. Прочие проблемные формы: не падаем и не выдумываем сумму --------------


def test_multipage_pdf_no_crash(db):
    """Многостраничный PDF (данные не на первой странице) → штатный manual
    review, без падения и без выдуманной суммы."""
    data = _text_pdf(
        "Сопроводительное письмо",
        "Приложение",
        "Ведомость: Сумма с НДС 1789,65 июнь 2026",
    )
    result = process_bill_upload(db, "multi.pdf", data, "application/pdf")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


def test_rotated_page_no_crash(db):
    result = process_bill_upload(db, "rot.pdf", _rotated_text_pdf(), "application/pdf")
    assert result.requires_manual_review is True


def test_encrypted_pdf_manual_review(db):
    """Зашифрованный PDF (load_page кидает ValueError) → ловится → manual
    review, не 500."""
    result = process_bill_upload(db, "enc.pdf", _encrypted_pdf(), "application/pdf")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


def test_non_latin_key_fields_no_wrong_amount(db):
    """Ключевые поля не на ru/en (греческий) → сервис не выдаёт уверенное
    неверное число, а просит ручную правку."""
    result = process_bill_upload(db, "gr.pdf", _text_pdf("Σύνολο 1789 ευρώ Ιούνιος 2026"), "application/pdf")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


def test_headerless_table_manual_review(db):
    """Текстовый слой есть, но нужных колонок/ключевых слов нет → manual
    review, суммы не выдумываем из случайных чисел."""
    result = process_bill_upload(db, "nohdr.pdf", _text_pdf("Код 12345 Количество 6789 Значение 42"), "application/pdf")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


# --- Ранее найденные крайние случаи (сохранены) ------------------------------


def test_corrupt_bytes_go_to_manual_review_not_500(db):
    result = process_bill_upload(db, "junk.jpg", b"this is not an image", "image/jpeg")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


def test_empty_file_goes_to_manual_review(db):
    result = process_bill_upload(db, "empty.png", b"", "image/png")
    assert result.requires_manual_review is True


def test_manual_review_response_never_invents_amount(db):
    """Общий инвариант: если сумма не извлечена — она None, а не догадка."""
    result = process_bill_upload(db, "junk.pdf", b"%PDF-1.4 broken", "application/pdf")
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


# --- HTTP-контракт эндпоинта (то, что ловило жюри) ---------------------------


def test_upload_endpoint_oversized_returns_200_manual_review(db):
    """Через реальный HTTP-роут: перебор по размеру — это 200 + manual_review,
    а не 500 и не оборванное соединение. Роутер читает не больше лимита+1 байта,
    поэтому огромный файл не буферизуется в память целиком.

    get_db переопределён на тестовую сессию; lifespan не запускаем (запрос его
    не требует — эндпоинт при manual_review в БД не пишет)."""
    from fastapi.testclient import TestClient

    from app.db.base import get_db
    from app.main import app

    def _use_test_db():
        yield db

    app.dependency_overrides[get_db] = _use_test_db
    try:
        client = TestClient(app)
        files = {"file": ("big.pdf", b"%PDF-1.4\n" + b"0" * MAX_UPLOAD_BYTES, "application/pdf")}
        resp = client.post("/bills/upload", files=files)
        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_manual_review"] is True
        assert body["ocr_status"] == "file_too_large"
        assert body["amount_tenge"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
