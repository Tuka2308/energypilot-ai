"""История счетов профиля — таблица bills в PostgreSQL.

Прогнозу и аномалиям нужна история за несколько месяцев; подтверждённые
показания складываются сюда по profile_id. Возвращаемый тип — dataclass
`BillReading` (period/amount/consumption), тот же, что читают forecast_service
и anomalies_service, поэтому их логика не меняется.

Одна запись = один месяц (period "YYYY-MM"). Повторная запись за тот же месяц
обновляет строку, а не плодит дубль (уникальность (profile_id, period) на
уровне БД + upsert здесь) — Prophet ждёт по одной точке на дату.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bill as BillRow
from app.db.models import Profile as ProfileRow


@dataclass
class BillReading:
    period: str  # "YYYY-MM"
    amount_tenge: float
    consumption_kwh: float | None = None


def record_reading(
    db: Session,
    profile_id: str,
    period: str,
    amount_tenge: float,
    consumption_kwh: float | None = None,
    ocr_status: str | None = None,
) -> None:
    """Upsert показания за месяц. Пишем только для существующего профиля:
    пустой profile_id (ручная правка без него) или неизвестный id — тихо
    пропускаем, не создаём осиротевшие счета и не роняем флоу."""
    if not profile_id or not period:
        return
    if db.get(ProfileRow, profile_id) is None:
        return

    existing = db.scalar(
        select(BillRow).where(BillRow.profile_id == profile_id, BillRow.period == period)
    )
    if existing is None:
        db.add(
            BillRow(
                profile_id=profile_id,
                period=period,
                amount_tenge=amount_tenge,
                consumption_kwh=consumption_kwh,
                ocr_status=ocr_status,
            )
        )
    else:
        existing.amount_tenge = amount_tenge
        existing.consumption_kwh = consumption_kwh
        existing.ocr_status = ocr_status
    db.commit()


def get_history(db: Session, profile_id: str) -> list[BillReading]:
    """Показания профиля, отсортированные по месяцу (по возрастанию)."""
    rows = db.scalars(
        select(BillRow).where(BillRow.profile_id == profile_id).order_by(BillRow.period)
    ).all()
    return [
        BillReading(period=r.period, amount_tenge=r.amount_tenge, consumption_kwh=r.consumption_kwh)
        for r in rows
    ]


def seed_history(db: Session, profile_id: str, readings: list[BillReading]) -> None:
    """Массовая загрузка истории — для тестов и демо (наполнить профиль
    несколькими месяцами без прогона через OCR). Профиль должен существовать."""
    for reading in readings:
        record_reading(db, profile_id, reading.period, reading.amount_tenge, reading.consumption_kwh)
