"""Заглушка сервиса загрузки счёта.

`requires_manual_review` всегда True в моке — реальный OCR ещё не
подключён, а UX-правило из CLAUDE.md требует, чтобы фронт всегда был готов
показать форму ручной правки (OCR не должен блокировать флоу).
"""

from uuid import uuid4

from app.models.schemas import BillManualCorrection, BillUploadResponse


def process_bill_upload(filename: str) -> BillUploadResponse:
    return BillUploadResponse(
        bill_id=str(uuid4()),
        ocr_status="mock_ocr_low_confidence",
        amount_tenge=18500.0,
        consumption_kwh=312.0,
        period="2026-06",
        requires_manual_review=True,
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
