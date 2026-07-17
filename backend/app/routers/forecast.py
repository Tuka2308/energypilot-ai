from fastapi import APIRouter

from app.models.schemas import ForecastResponse
from app.services import forecast_service

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("/{profile_id}", response_model=ForecastResponse)
def get_forecast(profile_id: str) -> ForecastResponse:
    return forecast_service.get_forecast(profile_id)
