// Типы зеркалят Pydantic-схемы backend/app/models/schemas.py.
// Держим их руками синхронизированными на этапе скелета — генерация
// клиента из OpenAPI имеет смысл добавить, когда контракт стабилизируется.

export type TariffType = "flat" | "differentiated" | "stepped";

export interface Appliance {
  name: string;
  power_watts?: number | null;
  quantity: number;
}

export interface OnboardingRequest {
  city: string;
  area_sqm: number;
  occupants: number;
  tariff_type: TariffType;
  tariff_rate?: number | null;
  appliances: Appliance[];
}

export interface OnboardingResponse {
  profile_id: string;
  received: OnboardingRequest;
}

export interface BillUploadResponse {
  bill_id: string;
  ocr_status: string;
  amount_tenge?: number | null;
  consumption_kwh?: number | null;
  period?: string | null;
  requires_manual_review: boolean;
}

export interface BillManualCorrection {
  bill_id: string;
  amount_tenge: number;
  consumption_kwh?: number | null;
  period: string;
  profile_id?: string | null;
}

export interface ForecastCategoryBreakdown {
  category: string;
  amount_tenge: number;
  share_percent: number;
}

export type ForecastStatus = "ok" | "insufficient_history";

export interface ForecastResponse {
  profile_id: string;
  status: ForecastStatus;
  forecast_period: string | null;
  predicted_amount_tenge: number | null;
  // Доверительный интервал из Prophet (yhat_lower / yhat_upper).
  predicted_amount_lower_tenge: number | null;
  predicted_amount_upper_tenge: number | null;
  predicted_consumption_kwh: number | null;
  confidence: number | null;
  breakdown: ForecastCategoryBreakdown[];
  history_points: number;
  message: string | null;
  generated_at: string;
}

export type AnomalySeverity = "low" | "medium" | "high";
export type AnomalyStatus = "ok" | "insufficient_history";

export interface Anomaly {
  id: string;
  detected_at: string;
  title: string;
  description: string;
  severity: AnomalySeverity;
  change_percent: number;
  metric: string;
  current_period: string | null;
  current_value: number | null;
  baseline_value: number | null;
  baseline_label: string | null;
}

export interface AnomaliesResponse {
  profile_id: string;
  status: AnomalyStatus;
  anomalies: Anomaly[];
  history_points: number;
  message: string | null;
}

export interface ChatMessageRequest {
  profile_id: string;
  message: string;
}

export interface ChatMessageResponse {
  reply: string;
  estimated_savings_tenge?: number | null;
  sources: string[];
}
