"""Регрессионные тесты распознавания счёта.

Ключевой тест — `test_real_kz_receipt_extracts_correct_values`: он ловит
конкретный баг, когда сервис на реальной табличной квитанции ЭСО уверенно
возвращал год "2026" как сумму и "6" как потребление. Fixture — настоящий
PDF ЭСО (born-digital, повёрнутая таблица), лежит в tests/fixtures/.
"""

from pathlib import Path

import pytest

from app.services.bills_service import process_bill_upload

FIXTURES = Path(__file__).parent / "fixtures"
KZ_RECEIPT = FIXTURES / "sample_receipt_kz.pdf"


def _read(path: Path) -> bytes:
    return path.read_bytes()


def test_real_kz_receipt_extracts_correct_values():
    """Табличный PDF ЭСО: реальные значения — 1789.65 ₸ (сумма с НДС),
    70 кВт·ч, июнь 2026. Раньше сервис возвращал 2026/6 и success."""
    result = process_bill_upload(
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


def test_corrupt_bytes_go_to_manual_review_not_500():
    result = process_bill_upload(
        filename="junk.jpg",
        content=b"this is not an image",
        content_type="image/jpeg",
    )
    assert result.requires_manual_review is True
    assert result.amount_tenge is None


def test_empty_file_goes_to_manual_review():
    result = process_bill_upload(
        filename="empty.png", content=b"", content_type="image/png"
    )
    assert result.requires_manual_review is True


def test_manual_review_response_never_invents_amount():
    """Общий инвариант: если сумма не извлечена — она None, а не догадка."""
    result = process_bill_upload(
        filename="junk.pdf", content=b"%PDF-1.4 broken", content_type="application/pdf"
    )
    assert result.requires_manual_review is True
    assert result.amount_tenge is None
