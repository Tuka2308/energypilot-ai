"""Сервис онбординга — профиль квартиры/техники/тарифа в PostgreSQL.

Возвращаемые типы — OnboardingResponse / OnboardingRequest, те же, что читают
роутер и чат-пайплайн; за хранение отвечают таблицы profiles/appliances.
"""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import Appliance as ApplianceRow
from app.db.models import Profile as ProfileRow
from app.models.schemas import Appliance, OnboardingRequest, OnboardingResponse, TariffType


def create_profile(db: Session, payload: OnboardingRequest) -> OnboardingResponse:
    profile_id = str(uuid4())
    db.add(
        ProfileRow(
            id=profile_id,
            city=payload.city,
            area_sqm=payload.area_sqm,
            occupants=payload.occupants,
            tariff_type=payload.tariff_type.value,
            tariff_rate=payload.tariff_rate,
            appliances=[
                ApplianceRow(name=a.name, power_watts=a.power_watts, quantity=a.quantity)
                for a in payload.appliances
            ],
        )
    )
    db.commit()
    return OnboardingResponse(profile_id=profile_id, received=payload)


def get_profile(db: Session, profile_id: str) -> OnboardingRequest | None:
    """Профиль по id как OnboardingRequest — нужен чат-пайплайну для контекста.

    Собираем обратно ту же Pydantic-модель, что пришла на онбординге, чтобы
    chat_service читал `.city/.appliances/.tariff_type` как и раньше."""
    row = db.get(ProfileRow, profile_id)
    if row is None:
        return None
    return OnboardingRequest(
        city=row.city,
        area_sqm=row.area_sqm,
        occupants=row.occupants,
        tariff_type=TariffType(row.tariff_type),
        tariff_rate=row.tariff_rate,
        appliances=[
            Appliance(name=a.name, power_watts=a.power_watts, quantity=a.quantity)
            for a in row.appliances
        ],
    )
