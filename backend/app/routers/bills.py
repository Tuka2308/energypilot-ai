from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import BillManualCorrection, BillUploadResponse
from app.services import bills_service

router = APIRouter(prefix="/bills", tags=["bills"])


@router.post("/upload", response_model=BillUploadResponse)
async def upload_bill(
    file: UploadFile,
    profile_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> BillUploadResponse:
    """Фото/PDF счёта. OCR-сервис сам гарантирует, что любая ошибка
    распознавания превращается в requires_manual_review=True, а не в
    500 — эндпоинт остаётся тонким и не должен ничего для этого ловить.

    `profile_id` опционален (Form-поле): если передан, уверенно распознанный
    счёт попадает в историю профиля и участвует в прогнозе. Без него флоу
    работает как раньше — контракт не ломается."""
    content = await file.read()
    return bills_service.process_bill_upload(
        db,
        filename=file.filename or "unknown",
        content=content,
        content_type=file.content_type,
        profile_id=profile_id,
    )


@router.post("/manual-correction", response_model=BillUploadResponse)
def submit_manual_correction(
    payload: BillManualCorrection, db: Session = Depends(get_db)
) -> BillUploadResponse:
    return bills_service.apply_manual_correction(db, payload)
