"""Тесты порогового правила аномалий потребления.

Три обязательных сценария из ТЗ — нормальный рост, аномальный скачок,
нехватка истории — плюс проверки сезонного (год-к-году) сравнения и
фолбэка на сумму, когда нет кВт·ч. Изоляция и фикстуры db/make_profile — в
conftest.py (отдельная тестовая БД).
"""

from app.services import bill_history_service as hist
from app.services.bill_history_service import BillReading
from app.services.anomalies_service import (
    ANOMALY_THRESHOLD_PERCENT,
    get_anomalies,
)
from app.models.schemas import AnomalySeverity, AnomalyStatus


def test_insufficient_history_returns_explicit_status(db, make_profile):
    """Новый пользователь: сравнивать не с чем — явный статус, без выдумки."""
    pid = make_profile()
    hist.seed_history(db, pid, [BillReading("2026-06", 16000.0, 260.0)])
    result = get_anomalies(db, pid)

    assert result.status == AnomalyStatus.insufficient_history
    assert result.anomalies == []
    assert result.history_points == 1
    assert result.message


def test_normal_growth_within_threshold_is_not_flagged(db, make_profile):
    """Рост ~+8% — в пределах бытового шума, не аномалия."""
    pid = make_profile()
    hist.seed_history(db, pid, [
        BillReading("2026-03", 15000.0, 245.0),
        BillReading("2026-04", 15200.0, 252.0),
        BillReading("2026-05", 15100.0, 250.0),
        BillReading("2026-06", 16300.0, 270.0),  # ~+8% к среднему ~249
    ])
    result = get_anomalies(db, pid)

    assert result.status == AnomalyStatus.ok
    assert result.anomalies == []


def test_anomalous_spike_is_flagged_with_explanation(db, make_profile):
    """Скачок ~+38% выше порога → флаг с человекочитаемым объяснением и
    структурированными полями для UI/чата."""
    pid = make_profile()
    hist.seed_history(db, pid, [
        BillReading("2026-03", 15000.0, 245.0),
        BillReading("2026-04", 15200.0, 252.0),
        BillReading("2026-05", 15100.0, 250.0),
        BillReading("2026-06", 21000.0, 345.0),  # ~+38%
    ])
    result = get_anomalies(db, pid)

    assert result.status == AnomalyStatus.ok
    assert len(result.anomalies) == 1
    anomaly = result.anomalies[0]

    assert anomaly.change_percent >= ANOMALY_THRESHOLD_PERCENT
    assert anomaly.metric == "consumption_kwh"
    assert anomaly.current_period == "2026-06"
    assert anomaly.current_value == 345.0
    assert anomaly.baseline_value is not None
    # объяснение готово к показу: содержит и период, и процент
    assert "2026-06" in anomaly.description
    assert "%" in anomaly.description
    assert anomaly.severity in (AnomalySeverity.medium, AnomalySeverity.high)


def test_high_severity_for_large_spike(db, make_profile):
    pid = make_profile()
    hist.seed_history(db, pid, [
        BillReading("2026-03", 15000.0, 250.0),
        BillReading("2026-04", 15000.0, 250.0),
        BillReading("2026-05", 15000.0, 250.0),
        BillReading("2026-06", 15000.0, 425.0),  # +70%
    ])
    anomaly = get_anomalies(db, pid).anomalies[0]
    assert anomaly.severity == AnomalySeverity.high


def test_seasonal_year_over_year_comparison_preferred(db, make_profile):
    """Если есть тот же месяц год назад — сравниваем с ним (учёт сезона),
    а не со средним по всей истории."""
    pid = make_profile()
    rows = [BillReading(f"2025-{m:02d}", 15000.0, 250.0) for m in range(6, 13)]
    rows += [BillReading(f"2026-{m:02d}", 15000.0, 250.0) for m in range(1, 6)]
    rows.append(BillReading("2026-06", 20000.0, 330.0))  # vs 2025-06 (250) → +32%
    hist.seed_history(db, pid, rows)

    anomaly = get_anomalies(db, pid).anomalies[0]
    assert "год назад" in anomaly.baseline_label
    assert anomaly.baseline_value == 250.0


def test_amount_fallback_when_no_consumption(db, make_profile):
    """Нет кВт·ч в истории — сравниваем по сумме (и честно помечаем метрику)."""
    pid = make_profile()
    hist.seed_history(db, pid, [
        BillReading("2026-03", 15000.0),
        BillReading("2026-04", 15200.0),
        BillReading("2026-05", 15100.0),
        BillReading("2026-06", 21500.0),  # ~+42% к среднему ~15100
    ])
    anomaly = get_anomalies(db, pid).anomalies[0]
    assert anomaly.metric == "amount_tenge"


def test_consumption_drop_is_not_an_anomaly(db, make_profile):
    """Падение расхода — не повод для флага (боль пользователя — рост счёта)."""
    pid = make_profile()
    hist.seed_history(db, pid, [
        BillReading("2026-03", 15000.0, 400.0),
        BillReading("2026-04", 15000.0, 390.0),
        BillReading("2026-05", 15000.0, 395.0),
        BillReading("2026-06", 12000.0, 250.0),  # заметное падение
    ])
    result = get_anomalies(db, pid)
    assert result.anomalies == []
