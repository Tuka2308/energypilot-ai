from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import AnomaliesResponse
from app.services import anomalies_service

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("/{profile_id}", response_model=AnomaliesResponse)
def get_anomalies(profile_id: str, db: Session = Depends(get_db)) -> AnomaliesResponse:
    return anomalies_service.get_anomalies(db, profile_id)
