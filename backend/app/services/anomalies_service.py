"""Заглушка сервиса аномалий.

По MVP-скоупу — пороговое правило ("рост X% без изменения привычек"), а не
ML (Isolation Forest/AutoEncoder). Мок возвращает пример такой аномалии,
чтобы фронт мог сверстать карточку до появления реального правила.
"""

from datetime import datetime, timezone

from app.models.schemas import Anomaly, AnomaliesResponse, AnomalySeverity


def get_anomalies(profile_id: str) -> AnomaliesResponse:
    return AnomaliesResponse(
        profile_id=profile_id,
        anomalies=[
            Anomaly(
                id="anomaly-mock-1",
                detected_at=datetime.now(timezone.utc),
                title="Рост потребления на 27% без новых приборов",
                description="Потребление за последние 7 дней выше обычного профиля при том же составе техники.",
                severity=AnomalySeverity.medium,
                change_percent=27.0,
            )
        ],
    )
