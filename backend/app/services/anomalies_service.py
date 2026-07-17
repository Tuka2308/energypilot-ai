"""Обнаружение аномалий потребления — пороговое правило (не ML).

По MVP-скоупу CLAUDE.md: простое объяснимое правило, а не Isolation Forest/
AutoEncoder (они явно вне скоупа). Сравниваем потребление последнего
(«текущего») месяца с исторической базой пользователя и, если рост выше
порога, поднимаем флаг с человекочитаемым объяснением.

Почему порог именно +30% (ANOMALY_THRESHOLD_PERCENT):
- Помесячное потребление электричества в квартире и без смены привычек
  колеблется примерно на ±10-20%: разное число дней в месяце, погода,
  занятость. Это нормальный «шум».
- +30% к личной базе — это примерно 1,5-2 «шумовых» отклонения: уже выше
  обычных колебаний, но ещё не экстремум. Так мы ловим поведенчески
  значимый рост рано (до прихода большого счёта — в этом весь смысл
  продукта), не заваливая пользователя ложными срабатываниями на бытовой
  разброс. Это нижняя граница диапазона из ТЗ (30-40%); берём её, чтобы
  предупреждать раньше, а серьёзность градируем severity.
- Флагуем только РОСТ: боль пользователя — неожиданно большой счёт, падение
  расхода предупреждать не нужно.

Про сезонность («без явного сезонного объяснения»): зимний рост отопления —
ожидаем, это не аномалия. Честный способ это учесть без ML — сравнивать с
тем же календарным месяцем год назад, если он есть в истории. Если года ещё
нет (частый случай на хакатоне), сравниваем со средним по истории и честно
подписываем базу сравнения — полноценная сезонная декомпозиция это уже
работа Prophet в прогнозе, а не порогового правила.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import Anomaly, AnomaliesResponse, AnomalySeverity, AnomalyStatus
from app.services import bill_history_service
from app.services.bill_history_service import BillReading
# Тот же порог истории, что и у прогноза: меньше — не с чем сравнивать.
from app.services.forecast_service import MIN_HISTORY_POINTS

# Порог флага и граница «высокой» серьёзности (обоснование — в докстринге).
ANOMALY_THRESHOLD_PERCENT = 30.0
HIGH_SEVERITY_PERCENT = 60.0


def get_anomalies(profile_id: str) -> AnomaliesResponse:
    history = bill_history_service.get_history(profile_id)

    if len(history) < MIN_HISTORY_POINTS:
        return AnomaliesResponse(
            profile_id=profile_id,
            status=AnomalyStatus.insufficient_history,
            anomalies=[],
            history_points=len(history),
            message=(
                f"Недостаточно истории для проверки аномалий: есть {len(history)} мес., "
                f"нужно минимум {MIN_HISTORY_POINTS}. Загрузите ещё счета."
            ),
        )

    current = history[-1]
    baseline = history[:-1]
    anomaly = _detect(profile_id, current, baseline)

    return AnomaliesResponse(
        profile_id=profile_id,
        status=AnomalyStatus.ok,
        anomalies=[anomaly] if anomaly else [],
        history_points=len(history),
    )


def _detect(profile_id: str, current: BillReading, baseline: list[BillReading]) -> Anomaly | None:
    metric, getter = _pick_metric(current, baseline)
    current_value = getter(current)
    if current_value is None:
        return None

    reference, baseline_label = _baseline_reference(current, baseline, getter)
    if reference is None or reference <= 0:
        return None

    change_percent = (current_value - reference) / reference * 100.0
    if change_percent < ANOMALY_THRESHOLD_PERCENT:
        return None  # роста нет или он в пределах нормы

    severity = (
        AnomalySeverity.high if change_percent >= HIGH_SEVERITY_PERCENT else AnomalySeverity.medium
    )
    unit = "кВт·ч" if metric == "consumption_kwh" else "₸"
    rounded = round(change_percent)

    return Anomaly(
        id=f"anomaly-{profile_id}-{current.period}",
        detected_at=datetime.now(timezone.utc),
        title=f"Рост потребления на {rounded}% за {current.period}",
        description=(
            f"Потребление за {current.period} — {_fmt(current_value)} {unit}, "
            f"это на {rounded}% выше, чем {baseline_label} ({_fmt(reference)} {unit}). "
            f"Похоже на изменение привычек или новый прибор — стоит проверить."
        ),
        severity=severity,
        change_percent=round(change_percent, 1),
        metric=metric,
        current_period=current.period,
        current_value=round(current_value, 1),
        baseline_value=round(reference, 1),
        baseline_label=baseline_label,
    )


def _pick_metric(current, baseline):
    """Предпочитаем кВт·ч: они отражают поведение, а сумма растёт ещё и от
    тарифа (это не аномалия расхода). Если кВт·ч нет — падаем на сумму."""
    baseline_with_kwh = sum(1 for r in baseline if r.consumption_kwh is not None)
    if current.consumption_kwh is not None and baseline_with_kwh >= 2:
        return "consumption_kwh", lambda r: r.consumption_kwh
    return "amount_tenge", lambda r: r.amount_tenge


def _baseline_reference(current, baseline, getter):
    """База сравнения: тот же месяц год назад (учитывает сезон), иначе —
    среднее по истории."""
    yoy_period = _year_ago(current.period)
    for reading in baseline:
        if reading.period == yoy_period and getter(reading) is not None:
            return getter(reading), f"в тот же месяц год назад ({yoy_period})"

    values = [getter(r) for r in baseline if getter(r) is not None]
    if not values:
        return None, None
    return sum(values) / len(values), f"среднее за {len(values)} мес."


def _year_ago(period: str) -> str:
    year, month = period.split("-")
    return f"{int(year) - 1}-{month}"


def _fmt(value: float) -> str:
    # Целые показываем без дробной части (312, а не 312.0), дробные — с одной.
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"
