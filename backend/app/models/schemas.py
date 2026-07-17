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
    # Опционально: если фронт передаёт profile_id, подтверждённое показание
    # попадает в историю профиля и участвует в прогнозе. Поле опциональное,
    # чтобы не ломать существующий контракт эндпоинта.
    profile_id: str | None = None


# --- Прогноз -----------------------------------------------------------------


class ForecastStatus(str, Enum):
    ok = "ok"
    # Истории < MIN_HISTORY_POINTS месяцев: Prophet не даст осмысленного
    # прогноза, поэтому явно сообщаем статус вместо фейкового числа.
    insufficient_history = "insufficient_history"


class ForecastCategoryBreakdown(BaseModel):
    category: str
    amount_tenge: float
    share_percent: float


class ForecastResponse(BaseModel):
    """Ответ прогноза.

    Изменения относительно скелета (объяснимо на защите):
    - `status` — различает готовый прогноз и случай нехватки истории
      (новый пользователь с 1-2 счетами), чтобы не показывать выдуманное число.
    - `predicted_amount_lower_tenge` / `predicted_amount_upper_tenge` —
      доверительный интервал, который Prophet отдаёт из коробки (yhat_lower /
      yhat_upper); показываем пользователю честный разброс, а не одну цифру.
    - `history_points` — сколько месяцев истории пошло в модель (объяснимость).
    - числовые поля стали Optional: при insufficient_history их просто нет.
    `confidence` оставлен для обратной совместимости и выводится из ширины
    интервала (уже интервал → выше уверенность).
    """

    profile_id: str
    status: ForecastStatus = ForecastStatus.ok
    forecast_period: str | None = None
    predicted_amount_tenge: float | None = None
    predicted_amount_lower_tenge: float | None = None
    predicted_amount_upper_tenge: float | None = None
    predicted_consumption_kwh: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    breakdown: list[ForecastCategoryBreakdown] = []
    history_points: int = 0
    message: str | None = None
    generated_at: datetime


# --- Аномалии ------------------------------------------------------------------


class AnomalySeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AnomalyStatus(str, Enum):
    ok = "ok"
    # Истории < MIN_HISTORY_POINTS месяцев: не с чем сравнивать текущий
    # период, поэтому явно сообщаем статус вместо ложного вывода (тот же
    # порог, что у прогноза — см. forecast_service).
    insufficient_history = "insufficient_history"


class Anomaly(BaseModel):
    id: str
    detected_at: datetime
    title: str
    description: str
    severity: AnomalySeverity
    change_percent: float
    # Структурированные поля (добавлены к скелету): само число + база
    # сравнения. Нужны и UI (карточка), и промпту AI-чата на следующем шаге,
    # чтобы не парсить их обратно из свободного текста description.
    metric: str = "consumption_kwh"  # что сравнивали: consumption_kwh | amount_tenge
    current_period: str | None = None  # "YYYY-MM"
    current_value: float | None = None
    baseline_value: float | None = None
    baseline_label: str | None = None  # с чем сравнивали (среднее/год назад)


class AnomaliesResponse(BaseModel):
    """Ответ по аномалиям.

    Изменения относительно скелета (объяснимо на защите):
    - `status` — различает «проверили, всё в норме / есть аномалия» и «не с
      чем сравнивать» (новый пользователь), чтобы UI не показывал
      «аномалий нет» там, где на самом деле нет истории.
    - `history_points` / `message` — объяснимость и человекочитаемый текст
      для insufficient_history (симметрично ForecastResponse).
    """

    profile_id: str
    status: AnomalyStatus = AnomalyStatus.ok
    anomalies: list[Anomaly]
    history_points: int = 0
    message: str | None = None


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
