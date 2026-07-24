"""Тесты прогноза счёта (Prophet).

`test_forecast_with_multi_month_history` реально обучает модель (~1-2 c,
требует cmdstan); тесты на нехватку истории быстрые и модель не трогают.
Изоляция и фикстуры db/make_profile — в conftest.py (отдельная тестовая БД).
"""

from app.services import bill_history_service as hist
from app.services.bill_history_service import BillReading
from app.services.forecast_service import get_forecast
from app.models.schemas import ForecastStatus


def test_new_user_one_bill_is_insufficient_history(db, make_profile):
    """Новый пользователь с одним счётом — Prophet не форсируем, отдаём
    явный статус без выдуманного числа."""
    pid = make_profile()
    hist.seed_history(db, pid, [BillReading("2026-06", 18000.0, 300.0)])
    result = get_forecast(db, pid)

    assert result.status == ForecastStatus.insufficient_history
    assert result.predicted_amount_tenge is None
    assert result.history_points == 1
    assert result.message  # человекочитаемое пояснение есть


def test_unknown_profile_is_insufficient_history(db):
    result = get_forecast(db, "no-such-profile")
    assert result.status == ForecastStatus.insufficient_history
    assert result.history_points == 0


def test_forecast_with_multi_month_history(db, make_profile):
    """Полгода+ истории → готовый прогноз с доверительным интервалом.
    Проверяем инварианты, а не точное число (Prophet стохастичен): прогноз
    в разумном бытовом диапазоне и лежит внутри своего интервала."""
    pid = make_profile()
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
    hist.seed_history(db, pid, history)
    result = get_forecast(db, pid)

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


def test_confidence_interval_not_absurdly_narrow(db, make_profile):
    """Регрессия на переобучение сезонности: интервал не должен схлопываться
    в точку на короткой истории с трендом."""
    pid = make_profile()
    history = [
        BillReading("2025-12", 27400.0, 445.0),
        BillReading("2026-01", 29900.0, 486.0),
        BillReading("2026-02", 26800.0, 436.0),
        BillReading("2026-03", 21200.0, 345.0),
        BillReading("2026-04", 17100.0, 278.0),
        BillReading("2026-05", 15400.0, 250.0),
    ]
    hist.seed_history(db, pid, history)
    result = get_forecast(db, pid)

    assert result.status == ForecastStatus.ok
    width = result.predicted_amount_upper_tenge - result.predicted_amount_lower_tenge
    assert width > 100  # интервал реально ненулевой
