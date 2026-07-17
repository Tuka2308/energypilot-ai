from fastapi import APIRouter

from app.models.schemas import ForecastResponse
from app.services import forecast_service

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("/{profile_id}", response_model=ForecastResponse)
def get_forecast(profile_id: str) -> ForecastResponse:
    """Прогноз счёта на текущий месяц по истории счетов профиля (Prophet).
    Контракт пути не меняется; расширен только формат ответа (см.
    ForecastResponse: status/интервал/history_points)."""
    return forecast_service.get_forecast(profile_id)
