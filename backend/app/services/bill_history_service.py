"""История счетов пользователя (в памяти процесса).

Отдельный модуль-хранилище: до этого счёт после распознавания просто
возвращался фронту и нигде не сохранялся. Прогнозу же нужна история за
несколько месяцев, поэтому подтверждённые показания складываем сюда, по
profile_id. Та же логика, что и у onboarding_service: PostgreSQL — следующий
шаг, для демо-сессии одного пользователя in-memory достаточно.

Одна запись = один месяц (period "YYYY-MM"). Повторная запись за тот же
месяц перезаписывает старую — так ручная правка суммы обновляет историю,
а не плодит дубли одного месяца (Prophet ждёт по одной точке на дату).
"""

from __future__ import annotations

from dataclasses import dataclass

_history: dict[str, dict[str, "BillReading"]] = {}


@dataclass
class BillReading:
    period: str  # "YYYY-MM"
    amount_tenge: float
    consumption_kwh: float | None = None


def record_reading(
    profile_id: str, period: str, amount_tenge: float, consumption_kwh: float | None = None
) -> None:
    """Сохраняет подтверждённое показание. Ключ по месяцу — перезапись, а не
    дубликат (см. модуль-докстринг)."""
    if not profile_id or not period:
        return
    _history.setdefault(profile_id, {})[period] = BillReading(
        period=period, amount_tenge=amount_tenge, consumption_kwh=consumption_kwh
    )


def get_history(profile_id: str) -> list[BillReading]:
    """Показания профиля, отсортированные по месяцу (по возрастанию)."""
    by_period = _history.get(profile_id, {})
    return [by_period[p] for p in sorted(by_period)]


def seed_history(profile_id: str, readings: list[BillReading]) -> None:
    """Массовая загрузка истории — для тестов и демо (наполнить профиль
    несколькими месяцами без прогона через OCR)."""
    for reading in readings:
        record_reading(profile_id, reading.period, reading.amount_tenge, reading.consumption_kwh)


def clear(profile_id: str | None = None) -> None:
    """Сброс — для изоляции тестов."""
    if profile_id is None:
        _history.clear()
    else:
        _history.pop(profile_id, None)
