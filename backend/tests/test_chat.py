"""Тесты чат-пайплайна энергокоуча.

LLM в тестах не вызывается: ключи принудительно обнуляются monkeypatch'ем,
проверяем детерминированные части пайплайна — сбор контекста, блок фактов
(включая запрет выдумывать прогноз), офлайн-fallback, память диалога.
"""

import pytest

from app.core.config import settings
from app.models.schemas import (
    Appliance,
    ChatMessageRequest,
    OnboardingRequest,
    TariffType,
)
from app.services import bill_history_service as hist
from app.services import chat_service, onboarding_service
from app.services.bill_history_service import BillReading
from app.services.chat_service import build_context, _render_facts, get_coach_reply


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Чистая история/диалоги и гарантированно офлайн-режим LLM (обнуляем
    все три ключа каскада — реальный backend/.env может содержать любой
    из них, тесты не должны зависеть от сети)."""
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "ollama_base_url", None)
    hist.clear()
    chat_service.clear_sessions()
    yield
    hist.clear()
    chat_service.clear_sessions()


def _make_profile() -> str:
    response = onboarding_service.create_profile(
        OnboardingRequest(
            city="Караганда",
            area_sqm=55,
            occupants=3,
            tariff_type=TariffType.differentiated,
            tariff_rate=22.04,
            appliances=[Appliance(name="Бойлер", power_watts=2000, quantity=1)],
        )
    )
    return response.profile_id


def _seed_normal(profile_id: str) -> None:
    hist.seed_history(profile_id, [
        BillReading("2026-03", 15000.0, 245.0),
        BillReading("2026-04", 15200.0, 252.0),
        BillReading("2026-05", 15100.0, 250.0),
        BillReading("2026-06", 16300.0, 270.0),  # +8% — не аномалия
    ])


def _seed_spike(profile_id: str) -> None:
    hist.seed_history(profile_id, [
        BillReading("2026-03", 15000.0, 245.0),
        BillReading("2026-04", 15200.0, 252.0),
        BillReading("2026-05", 15100.0, 250.0),
        BillReading("2026-06", 21000.0, 345.0),  # ~+38% — аномалия
    ])


def test_facts_block_contains_profile_forecast_and_tariff():
    profile_id = _make_profile()
    _seed_normal(profile_id)
    facts = _render_facts(build_context(profile_id))

    assert "Караганда" in facts
    assert "Бойлер 2000 Вт" in facts
    assert "дифференцированный" in facts
    assert "22.04" in facts
    assert "ПРОГНОЗ на 2026-07" in facts
    assert "АНОМАЛИИ: не обнаружены" in facts


def test_facts_block_forbids_forecast_when_insufficient():
    """Ключевая защита от галлюцинаций: при нехватке истории блок фактов
    содержит явный запрет называть сумму, а не выдуманное число."""
    profile_id = _make_profile()  # истории нет вообще
    facts = _render_facts(build_context(profile_id))

    assert "НЕДОСТУПЕН" in facts
    assert "ЗАПРЕЩЕНО" in facts
    assert "₸ (диапазон" not in facts  # никакой суммы прогноза в фактах нет


def test_facts_block_contains_anomaly_numbers():
    profile_id = _make_profile()
    _seed_spike(profile_id)
    facts = _render_facts(build_context(profile_id))

    assert "АНОМАЛИЯ за 2026-06" in facts
    assert "345" in facts and "249" in facts  # current и baseline
    assert "+38.6%" in facts


def test_normal_question_offline_fallback():
    """Обычный вопрос про экономию без LLM: осмысленный ответ из контекста,
    честная пометка офлайн-режима, sources перечисляет вошедшие блоки."""
    profile_id = _make_profile()
    _seed_normal(profile_id)

    result = get_coach_reply(ChatMessageRequest(profile_id=profile_id, message="Как сэкономить?"))

    assert "Прогноз на 2026-07" in result.reply
    assert "тариф день/ночь" in result.reply  # персональный совет от техники
    assert "OPENAI_API_KEY" in result.reply  # пометка офлайн-режима
    assert set(result.sources) == {"profile", "tariff", "forecast"}


def test_question_with_anomaly_leads_with_it_and_estimates_savings():
    profile_id = _make_profile()
    _seed_spike(profile_id)

    result = get_coach_reply(ChatMessageRequest(profile_id=profile_id, message="Почему так много?"))

    assert "345" in result.reply  # цифры аномалии в ответе
    assert "anomalies" in result.sources
    # экономия посчитана из реальных данных (доля превышения × прогноз)
    assert result.estimated_savings_tenge is not None
    assert 0 < result.estimated_savings_tenge < 50000


def test_insufficient_history_answer_does_not_invent_numbers():
    profile_id = _make_profile()  # истории нет

    result = get_coach_reply(ChatMessageRequest(profile_id=profile_id, message="Какой будет счёт?"))

    assert "недостаточно истории" in result.reply.lower()
    assert "forecast" not in result.sources
    assert result.estimated_savings_tenge is None


def test_dialogue_memory_keeps_turns_per_profile():
    profile_id = _make_profile()
    _seed_normal(profile_id)

    get_coach_reply(ChatMessageRequest(profile_id=profile_id, message="Как сэкономить?"))
    get_coach_reply(ChatMessageRequest(profile_id=profile_id, message="А если стирать ночью?"))

    session = chat_service._sessions[profile_id]
    assert len(session) == 4  # 2 пары «вопрос-ответ»
    assert session[0]["content"] == "Как сэкономить?"
    assert session[2]["content"] == "А если стирать ночью?"

    # память изолирована по профилям
    other = _make_profile()
    assert other not in chat_service._sessions
