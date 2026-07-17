from fastapi import APIRouter, UploadFile

from app.models.schemas import BillManualCorrection, BillUploadResponse
from app.services import bills_service

router = APIRouter(prefix="/bills", tags=["bills"])


@router.post("/upload", response_model=BillUploadResponse)
async def upload_bill(file: UploadFile) -> BillUploadResponse:
    """Фото/PDF счёта. OCR-сервис сам гарантирует, что любая ошибка
    распознавания превращается в requires_manual_review=True, а не в
    500 — эндпоинт остаётся тонким и не должен ничего для этого ловить."""
    content = await file.read()
    return bills_service.process_bill_upload(
        filename=file.filename or "unknown",
        content=content,
        content_type=file.content_type,
    )


@router.post("/manual-correction", response_model=BillUploadResponse)
def submit_manual_correction(payload: BillManualCorrection) -> BillUploadResponse:
    return bills_service.apply_manual_correction(payload)
