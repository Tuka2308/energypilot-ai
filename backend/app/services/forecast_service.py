"""Заглушка сервиса прогноза.

Возвращает статичный мок вместо Prophet/регрессии — модель по MVP-скоупу
одна (не ансамбль), подключается на следующем шаге в этом же сервисе, без
изменения контракта роутера.
"""

from datetime import datetime, timezone

from app.models.schemas import ForecastCategoryBreakdown, ForecastResponse


def get_forecast(profile_id: str) -> ForecastResponse:
    return ForecastResponse(
        profile_id=profile_id,
        forecast_period="2026-08",
        predicted_amount_tenge=21400.0,
        predicted_consumption_kwh=340.0,
        confidence=0.62,
        breakdown=[
            ForecastCategoryBreakdown(category="Отопление/бойлер", amount_tenge=8200.0, share_percent=38.3),
            ForecastCategoryBreakdown(category="Кухонная техника", amount_tenge=4900.0, share_percent=22.9),
            ForecastCategoryBreakdown(category="Освещение", amount_tenge=2100.0, share_percent=9.8),
            ForecastCategoryBreakdown(category="Прочее", amount_tenge=6200.0, share_percent=29.0),
        ],
        generated_at=datetime.now(timezone.utc),
    )
