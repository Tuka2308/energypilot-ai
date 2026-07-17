from fastapi import APIRouter

from app.models.schemas import AnomaliesResponse
from app.services import anomalies_service

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("/{profile_id}", response_model=AnomaliesResponse)
def get_anomalies(profile_id: str) -> AnomaliesResponse:
    return anomalies_service.get_anomalies(profile_id)
