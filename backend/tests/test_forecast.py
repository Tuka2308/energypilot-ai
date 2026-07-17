"""Тесты прогноза счёта (Prophet).

Prophet-путь (Case ok) помечен @pytest.mark.slow-подобным образом через
отдельный тест: он реально обучает модель (~1-2 c) и требует cmdstan. Тест
на нехватку истории быстрый и модель не трогает.
"""

import pytest

from app.services import bill_history_service as hist
from app.services.bill_history_service import BillReading
from app.services.forecast_service import MIN_HISTORY_POINTS, get_forecast
from app.models.schemas import ForecastStatus


@pytest.fixture(autouse=True)
def _clean_history():
    hist.clear()
    yield
    hist.clear()


def test_new_user_one_bill_is_insufficient_history():
    """Новый пользователь с одним счётом — Prophet не форсируем, отдаём
    явный статус без выдуманного числа."""
    hist.seed_history("u1", [BillReading("2026-06", 18000.0, 300.0)])
    result = get_forecast("u1")

    assert result.status == ForecastStatus.insufficient_history
    assert result.predicted_amount_tenge is None
    assert result.history_points == 1
    assert result.message  # человекочитаемое пояснение есть


def test_unknown_profile_is_insufficient_history():
    result = get_forecast("no-such-profile")
    assert result.status == ForecastStatus.insufficient_history
    assert result.history_points == 0


def test_forecast_with_multi_month_history():
    """Полгода+ истории → готовый прогноз с доверительным интервалом.
    Проверяем инварианты, а не точное число (Prophet стохастичен): прогноз
    в разумном бытовом диапазоне и лежит внутри своего интервала."""
    history = [
        BillReading("2025-09", 15200.0, 250.0),
        BillReading("2025-10", 17800.0, 292.0),
        BillReading("2025-11", 21500.0, 350.0),
        BillReading("2025-12", 27400.0, 445.0),
        BillReading("2026-01", 29900.0, 486.0),
        BillReading("2026-02", 26800.0, 436.0),
        BillReading("2026-03", 21200.0, 345.0),
        BillReading("2026-04", 17100.0, 278.0),
        BillReading("2026-05", 15400.0, 250.0),
        BillReading("2026-06", 16050.0, 261.0),
    ]
    hist.seed_history("u2", history)
    result = get_forecast("u2")

    assert result.status == ForecastStatus.ok
    assert result.history_points == len(history)
    assert result.forecast_period == "2026-07"  # месяц после последнего в истории

    # Доверительный интервал присутствует и корректно окружает прогноз.
    assert result.predicted_amount_lower_tenge is not None
    assert result.predicted_amount_upper_tenge is not None
    assert (
        result.predicted_amount_lower_tenge
        <= result.predicted_amount_tenge
        <= result.predicted_amount_upper_tenge
    )

    # Разумный бытовой диапазон — ловим прежний баг с сезонностью, когда
    # прогноз улетал в сотни тысяч тенге.
    assert 5_000 < result.predicted_amount_tenge < 60_000

    assert result.predicted_consumption_kwh is not None
    assert result.breakdown  # структура расхода для дашборда заполнена


def test_confidence_interval_not_absurdly_narrow():
    """Регрессия на переобучение сезонности: интервал не должен схлопываться
    в точку на короткой истории с трендом."""
    history = [
        BillReading("2025-12", 27400.0, 445.0),
        BillReading("2026-01", 29900.0, 486.0),
        BillReading("2026-02", 26800.0, 436.0),
        BillReading("2026-03", 21200.0, 345.0),
        BillReading("2026-04", 17100.0, 278.0),
        BillReading("2026-05", 15400.0, 250.0),
    ]
    hist.seed_history("u3", history)
    result = get_forecast("u3")

    assert result.status == ForecastStatus.ok
    width = result.predicted_amount_upper_tenge - result.predicted_amount_lower_tenge
    assert width > 100  # интервал реально ненулевой
