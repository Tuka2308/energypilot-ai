"""Прогноз счёта за электроэнергию на текущий месяц.

Одна модель — Prophet (по MVP-скоупу CLAUDE.md: без ансамбля LSTM/XGBoost/
Prophet). Вход — история подтверждённых счетов профиля (по одной точке на
месяц) из bill_history_service. Prophet сам моделирует тренд + годовую
сезонность (месяц как прокси сезона: зимой отопление → выше, летом ниже) и
из коробки отдаёт доверительный интервал (yhat_lower/yhat_upper) — его и
показываем как честный разброс.

Правило нехватки истории: при < MIN_HISTORY_POINTS точек Prophet даёт
неустойчивую цифру, поэтому НЕ форсируем модель, а возвращаем явный статус
insufficient_history без числа. Так новый пользователь с одним счётом видит
понятное сообщение, а не выдуманный прогноз.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.schemas import (
    ForecastCategoryBreakdown,
    ForecastResponse,
    ForecastStatus,
)
from app.services import bill_history_service

logger = logging.getLogger(__name__)

# Prophet хочет несколько точек, иначе тренд/интервал бессмысленны.
# 3 месяца — минимальный практичный порог для MVP.
MIN_HISTORY_POINTS = 3

# Годовую сезонность включаем только при наличии ~2 полных лет. На более
# короткой истории Prophet катастрофически переобучает сезонный компонент и
# экстраполирует бред (проверено: на 10 месяцах прогноз улетал в сотни тысяч
# тенге при неправдоподобно узком интервале). До этого порога — только
# тренд: честнее выдать тренд, чем выдуманную сезонность, которой в данных
# ещё нет.
SEASONALITY_MIN_MONTHS = 24

# 80% доверительный интервал: для бытового прогноза важнее «типичный
# диапазон», чем строгие 95% (которые на короткой истории слишком широки).
INTERVAL_WIDTH = 0.8

# Эвристическая разбивка прогноза по категориям — это НЕ выход Prophet
# (модель прогнозирует общую сумму), а типовые доли расхода квартиры,
# масштабированные к прогнозу. Нужна дашборду для «структуры расхода».
TYPICAL_SHARES = [
    ("Отопление/бойлер", 0.38),
    ("Кухонная техника", 0.23),
    ("Освещение", 0.10),
    ("Прочее", 0.29),
]


def get_forecast(profile_id: str) -> ForecastResponse:
    history = bill_history_service.get_history(profile_id)

    if len(history) < MIN_HISTORY_POINTS:
        return _insufficient(profile_id, len(history))

    try:
        return _prophet_forecast(profile_id, history)
    except Exception:
        # Модель не должна ронять эндпоинт. Если Prophet по какой-то причине
        # не сошёлся — сообщаем как о нехватке данных, а не выдаём число.
        logger.warning("Prophet не смог построить прогноз для %s", profile_id, exc_info=True)
        return _insufficient(profile_id, len(history), message="Не удалось построить прогноз по имеющимся данным.")


def _prophet_forecast(profile_id, history) -> ForecastResponse:
    # Ленивый импорт: Prophet тяжёлый и тянет cmdstanpy — не грузим его при
    # старте приложения и в тестах, которые прогноз не трогают.
    import pandas as pd
    from prophet import Prophet

    _silence_prophet_logs()

    df = pd.DataFrame(
        {
            "ds": [_period_to_date(r.period) for r in history],
            "y": [r.amount_tenge for r in history],
        }
    )

    # Сезонность (месяц как прокси сезона: отопление зимой) — только когда
    # истории хватает на 2 цикла; иначе трендовая модель без переобучения.
    use_seasonality = len(history) >= SEASONALITY_MIN_MONTHS
    model = Prophet(
        interval_width=INTERVAL_WIDTH,
        yearly_seasonality=use_seasonality,
        weekly_seasonality=False,  # данные месячные — недельная/дневная не нужны
        daily_seasonality=False,
    )
    model.fit(df)

    # Прогнозируем следующий месяц после последнего в истории — это и есть
    # текущий незакрытый счёт.
    next_period = _next_period(history[-1].period)
    future = pd.DataFrame({"ds": [_period_to_date(next_period)]})
    forecast = model.predict(future).iloc[0]

    predicted = max(0.0, float(forecast["yhat"]))
    lower = max(0.0, float(forecast["yhat_lower"]))
    upper = float(forecast["yhat_upper"])

    consumption = _forecast_consumption(history, predicted)

    return ForecastResponse(
        profile_id=profile_id,
        status=ForecastStatus.ok,
        forecast_period=next_period,
        predicted_amount_tenge=round(predicted, 2),
        predicted_amount_lower_tenge=round(lower, 2),
        predicted_amount_upper_tenge=round(upper, 2),
        predicted_consumption_kwh=consumption,
        confidence=_confidence_from_interval(predicted, lower, upper),
        breakdown=_breakdown(predicted),
        history_points=len(history),
        generated_at=datetime.now(timezone.utc),
    )


def _forecast_consumption(history, predicted_amount: float) -> float | None:
    """Оценка потребления в кВт·ч. Если во всех счетах есть кВт·ч — считаем
    средний тариф (тенге/кВт·ч) по истории и делим прогноз суммы на него.
    Это устойчивее, чем отдельная модель на короткой истории потребления, и
    согласовано с прогнозом суммы. Нет данных по кВт·ч — возвращаем None."""
    pairs = [(r.amount_tenge, r.consumption_kwh) for r in history if r.consumption_kwh]
    if not pairs:
        return None
    avg_tariff = sum(a for a, _ in pairs) / sum(c for _, c in pairs)
    if avg_tariff <= 0:
        return None
    return round(predicted_amount / avg_tariff, 1)


def _confidence_from_interval(predicted: float, lower: float, upper: float) -> float:
    """Скалярная «уверенность» 0..1 из ширины интервала: чем уже интервал
    относительно прогноза, тем выше. Оставлено для обратной совместимости с
    фронтом; настоящая мера разброса — сами границы интервала."""
    if predicted <= 0:
        return 0.0
    relative_half_width = (upper - lower) / (2 * predicted)
    return round(max(0.0, min(1.0, 1 - relative_half_width)), 2)


def _breakdown(predicted_amount: float) -> list[ForecastCategoryBreakdown]:
    return [
        ForecastCategoryBreakdown(
            category=name,
            amount_tenge=round(predicted_amount * share, 2),
            share_percent=round(share * 100, 1),
        )
        for name, share in TYPICAL_SHARES
    ]


def _insufficient(profile_id: str, points: int, message: str | None = None) -> ForecastResponse:
    return ForecastResponse(
        profile_id=profile_id,
        status=ForecastStatus.insufficient_history,
        history_points=points,
        message=message
        or (
            f"Недостаточно истории для прогноза: есть {points} мес., "
            f"нужно минимум {MIN_HISTORY_POINTS}. Загрузите ещё счета."
        ),
        generated_at=datetime.now(timezone.utc),
    )


def _silence_prophet_logs() -> None:
    # cmdstanpy/prophet шумят в stdout на каждый fit — глушим до WARNING.
    for name in ("cmdstanpy", "prophet"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _period_to_date(period: str) -> datetime:
    year, month = period.split("-")
    return datetime(int(year), int(month), 1)


def _next_period(period: str) -> str:
    year, month = (int(x) for x in period.split("-"))
    if month == 12:
        return f"{year + 1}-01"
    return f"{year}-{month + 1:02d}"
