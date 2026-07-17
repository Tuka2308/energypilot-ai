"""Заглушка сервиса онбординга.

Хранит профили в памяти процесса (не в БД) — на этапе скелета этого
достаточно, чтобы фронт мог получить profile_id и переиспользовать его в
других мок-эндпоинтах (прогноз/аномалии/чат) в рамках одной демо-сессии.
Реальное сохранение в PostgreSQL — следующий шаг.
"""

from uuid import uuid4

from app.models.schemas import OnboardingRequest, OnboardingResponse

_profiles: dict[str, OnboardingRequest] = {}


def create_profile(payload: OnboardingRequest) -> OnboardingResponse:
    profile_id = str(uuid4())
    _profiles[profile_id] = payload
    return OnboardingResponse(profile_id=profile_id, received=payload)
