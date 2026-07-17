from fastapi import APIRouter, UploadFile

from app.models.schemas import BillManualCorrection, BillUploadResponse
from app.services import bills_service

router = APIRouter(prefix="/bills", tags=["bills"])


@router.post("/upload", response_model=BillUploadResponse)
async def upload_bill(file: UploadFile) -> BillUploadResponse:
    """Фото/PDF счёта. Реальный OCR подключается позже; контракт ответа уже
    содержит `requires_manual_review`, чтобы фронт мог сразу верстать
    fallback-форму ручной правки."""
    return bills_service.process_bill_upload(filename=file.filename or "unknown")


@router.post("/manual-correction", response_model=BillUploadResponse)
def submit_manual_correction(payload: BillManualCorrection) -> BillUploadResponse:
    return bills_service.apply_manual_correction(payload)
