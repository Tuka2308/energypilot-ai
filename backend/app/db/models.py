"""ORM-модели — доменные структуры сервисов (профиль/техника/счета).

Три таблицы:
- profiles   — анкета квартиры (город/площадь/жильцы/тариф). id = UUID-строка,
               тот же profile_id, что отдаётся фронту и ходит по всем эндпоинтам.
- appliances — техника профиля (1:N к profiles).
- bills      — подтверждённые счета профиля (1:N). Уникальность по
               (profile_id, period): один счёт на месяц, повторная загрузка/
               правка обновляет строку, а не плодит дубли — Prophet ждёт по
               одной точке на дату.

FK-и с ON DELETE CASCADE: удаление профиля забирает его технику и счета —
осмысленная целостность вместо прежней неявной связи «оба словаря по одному
ключу profile_id».
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID-строка
    city: Mapped[str] = mapped_column(String)
    area_sqm: Mapped[float] = mapped_column(Float)
    occupants: Mapped[int] = mapped_column(Integer)
    tariff_type: Mapped[str] = mapped_column(String)  # значение TariffType (flat/…)
    tariff_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    appliances: Mapped[list[Appliance]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    bills: Mapped[list[Bill]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class Appliance(Base):
    __tablename__ = "appliances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    power_watts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    profile: Mapped[Profile] = relationship(back_populates="appliances")


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("profile_id", "period", name="uq_bill_profile_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    period: Mapped[str] = mapped_column(String)  # "YYYY-MM"
    amount_tenge: Mapped[float] = mapped_column(Float)
    consumption_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_status: Mapped[str | None] = mapped_column(String, nullable=True)

    profile: Mapped[Profile] = relationship(back_populates="bills")
