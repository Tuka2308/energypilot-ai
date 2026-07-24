"""Тесты чат-пайплайна энергокоуча.

LLM в тестах не вызывается: ключи принудительно обнуляются monkeypatch'ем,
проверяем детерминированные части пайплайна — сбор контекста, блок фактов
(включая запрет выдумывать прогноз), офлайн-fallback, память диалога.
Изоляция БД и фикстуры db/make_profile — в conftest.py.
"""

import pytest

from app.core.config import settings
from app.models.schemas import Appliance, ChatMessageRequest, TariffType
from app.services import bill_history_service as hist
from app.services import chat_service
from app.services.bill_history_service import BillReading
from app.services.chat_service import build_context, _render_facts, get_coach_reply


@pytest.fixture(autouse=True)
def _offline_llm(monkeypatch):
    """Гарантированно офлайн-режим LLM (обнуляем все три ключа каскада —
    реальный backend/.env может содержать любой из них, тесты не должны
    зависеть от сети) и чистая память диалога. Данные в БД чистит conftest."""
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "ollama_base_url", None)
    chat_service.clear_sessions()
    yield
    chat_service.clear_sessions()


def _coach_profile(make_profile) -> str:
    return make_profile(
        tariff_type=TariffType.differentiated,
        tariff_rate=22.04,
        appliances=[Appliance(name="Бойлер", power_watts=2000, quantity=1)],
    )


def _seed_normal(db, profile_id: str) -> None:
    hist.seed_history(db, profile_id, [
        BillReading("2026-03", 15000.0, 245.0),
        BillReading("2026-04", 15200.0, 252.0),
        BillReading("2026-05", 15100.0, 250.0),
        BillReading("2026-06", 16300.0, 270.0),  # +8% — не аномалия
    ])


def _seed_spike(db, profile_id: str) -> None:
    hist.seed_history(db, profile_id, [
        BillReading("2026-03", 15000.0, 245.0),
        BillReading("2026-04", 15200.0, 252.0),
        BillReading("2026-05", 15100.0, 250.0),
        BillReading("2026-06", 21000.0, 345.0),  # ~+38% — аномалия
    ])


def test_facts_block_contains_profile_forecast_and_tariff(db, make_profile):
    pid = _coach_profile(make_profile)
    _seed_normal(db, pid)
    facts = _render_facts(build_context(db, pid))

    assert "Караганда" in facts
    assert "Бойлер 2000 Вт" in facts
    assert "дифференцированный" in facts
    assert "22.04" in facts
    assert "ПРОГНОЗ на 2026-07" in facts
    assert "АНОМАЛИИ: не обнаружены" in facts


def test_facts_block_forbids_forecast_when_insufficient(db, make_profile):
    """Ключевая защита от галлюцинаций: при нехватке истории блок фактов
    содержит явный запрет называть сумму, а не выдуманное число."""
    pid = _coach_profile(make_profile)  # истории нет вообще
    facts = _render_facts(build_context(db, pid))

    assert "НЕДОСТУПЕН" in facts
    assert "ЗАПРЕЩЕНО" in facts
    assert "₸ (диапазон" not in facts  # никакой суммы прогноза в фактах нет


def test_facts_block_contains_anomaly_numbers(db, make_profile):
    pid = _coach_profile(make_profile)
    _seed_spike(db, pid)
    facts = _render_facts(build_context(db, pid))

    assert "АНОМАЛИЯ за 2026-06" in facts
    assert "345" in facts and "249" in facts  # current и baseline
    assert "+38.6%" in facts


def test_normal_question_offline_fallback(db, make_profile):
    """Обычный вопрос про экономию без LLM: осмысленный ответ из контекста,
    честная пометка офлайн-режима, sources перечисляет вошедшие блоки."""
    pid = _coach_profile(make_profile)
    _seed_normal(db, pid)

    result = get_coach_reply(db, ChatMessageRequest(profile_id=pid, message="Как сэкономить?"))

    assert "Прогноз на 2026-07" in result.reply
    assert "тариф день/ночь" in result.reply  # персональный совет от техники
    assert "OPENAI_API_KEY" in result.reply  # пометка офлайн-режима
    assert set(result.sources) == {"profile", "tariff", "forecast"}


def test_question_with_anomaly_leads_with_it_and_estimates_savings(db, make_profile):
    pid = _coach_profile(make_profile)
    _seed_spike(db, pid)

    result = get_coach_reply(db, ChatMessageRequest(profile_id=pid, message="Почему так много?"))

    assert "345" in result.reply  # цифры аномалии в ответе
    assert "anomalies" in result.sources
    # экономия посчитана из реальных данных (доля превышения × прогноз)
    assert result.estimated_savings_tenge is not None
    assert 0 < result.estimated_savings_tenge < 50000


def test_insufficient_history_answer_does_not_invent_numbers(db, make_profile):
    pid = _coach_profile(make_profile)  # истории нет

    result = get_coach_reply(db, ChatMessageRequest(profile_id=pid, message="Какой будет счёт?"))

    assert "недостаточно истории" in result.reply.lower()
    assert "forecast" not in result.sources
    assert result.estimated_savings_tenge is None


def test_dialogue_memory_keeps_turns_per_profile(db, make_profile):
    pid = _coach_profile(make_profile)
    _seed_normal(db, pid)

    get_coach_reply(db, ChatMessageRequest(profile_id=pid, message="Как сэкономить?"))
    get_coach_reply(db, ChatMessageRequest(profile_id=pid, message="А если стирать ночью?"))

    session = chat_service._sessions[pid]
    assert len(session) == 4  # 2 пары «вопрос-ответ»
    assert session[0]["content"] == "Как сэкономить?"
    assert session[2]["content"] == "А если стирать ночью?"

    # память изолирована по профилям
    other = _coach_profile(make_profile)
    assert other not in chat_service._sessions
