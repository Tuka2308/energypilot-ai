"""Pydantic-схемы запросов/ответов.

Модели сгруппированы по фиче (онбординг / счета / прогноз / аномалии / чат),
а не по слою хранения — на этапе скелета нет ORM-моделей, только контракт
API, чтобы фронт мог типизировать запросы уже сейчас.
"""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


# --- Онбординг --------------------------------------------------------------
# Одна форма на квартиру + технику + тариф — намеренно не разбито на
# отдельные under-модели/эндпоинты по MVP-правилу "не растягивать на
# отдельные экраны".


class TariffType(str, Enum):
    flat = "flat"  # единый тариф
    differentiated = "differentiated"  # дифференцированный (день/ночь)
    stepped = "stepped"  # ступенчатый по объёму потребления


class Appliance(BaseModel):
    name: str
    power_watts: int | None = Field(default=None, ge=0)
    quantity: int = Field(default=1, ge=1)


class OnboardingRequest(BaseModel):
    city: str
    area_sqm: float = Field(gt=0)
    occupants: int = Field(ge=1)
    tariff_type: TariffType
    tariff_rate: float | None = Field(default=None, description="тенге/кВт·ч, если известен")
    appliances: list[Appliance] = []


class OnboardingResponse(BaseModel):
    profile_id: str
    received: OnboardingRequest


# --- Загрузка счёта -----------------------------------------------------------


class BillUploadResponse(BaseModel):
    """Ответ OCR. `requires_manual_review=True` — сигнал фронту показать
    форму ручной правки, а не блокировать флоу (правило graceful-degradation
    из CLAUDE.md)."""

    bill_id: str
    ocr_status: str
    amount_tenge: float | None = None
    consumption_kwh: float | None = None
    period: str | None = None
    requires_manual_review: bool = True


class BillManualCorrection(BaseModel):
    bill_id: str
    amount_tenge: float = Field(gt=0)
    consumption_kwh: float | None = Field(default=None, ge=0)
    period: str


# --- Прогноз -----------------------------------------------------------------


class ForecastCategoryBreakdown(BaseModel):
    category: str
    amount_tenge: float
    share_percent: float


class ForecastResponse(BaseModel):
    profile_id: str
    forecast_period: str
    predicted_amount_tenge: float
    predicted_consumption_kwh: float
    confidence: float = Field(ge=0, le=1)
    breakdown: list[ForecastCategoryBreakdown]
    generated_at: datetime


# --- Аномалии ------------------------------------------------------------------


class AnomalySeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Anomaly(BaseModel):
    id: str
    detected_at: datetime
    title: str
    description: str
    severity: AnomalySeverity
    change_percent: float


class AnomaliesResponse(BaseModel):
    profile_id: str
    anomalies: list[Anomaly]


# --- Чат / энергокоуч ----------------------------------------------------------


class ChatMessageRequest(BaseModel):
    profile_id: str
    message: str


class ChatMessageResponse(BaseModel):
    reply: str
    estimated_savings_tenge: float | None = None
    sources: list[str] = Field(
        default_factory=list,
        description="какие данные учтены в ответе (профиль/прогноз/тариф/погода)",
    )
