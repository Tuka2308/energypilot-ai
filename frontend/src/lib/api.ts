import type {
  AnomaliesResponse,
  BillManualCorrection,
  BillUploadResponse,
  ChatMessageRequest,
  ChatMessageResponse,
  ForecastResponse,
  OnboardingRequest,
  OnboardingResponse,
} from "./types";

// Публичный env var — читается в браузере, поэтому обязателен префикс
// NEXT_PUBLIC_. Дефолт указывает на локальный FastAPI из docker-compose.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers:
      init?.body instanceof FormData
        ? undefined
        : { "Content-Type": "application/json" },
    ...init,
  });

  if (!res.ok) {
    throw new Error(`API ${path} вернул ${res.status}`);
  }

  return res.json() as Promise<T>;
}

export function submitOnboarding(payload: OnboardingRequest) {
  return request<OnboardingResponse>("/onboarding", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function uploadBill(file: File, profileId?: string | null) {
  const formData = new FormData();
  formData.append("file", file);
  // profile_id опционален: если есть, распознанный счёт попадёт в историю
  // профиля и будет учтён в прогнозе.
  if (profileId) formData.append("profile_id", profileId);
  return request<BillUploadResponse>("/bills/upload", {
    method: "POST",
    body: formData,
  });
}

export function submitManualCorrection(payload: BillManualCorrection) {
  return request<BillUploadResponse>("/bills/manual-correction", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getForecast(profileId: string) {
  return request<ForecastResponse>(`/forecast/${profileId}`);
}

export function getAnomalies(profileId: string) {
  return request<AnomaliesResponse>(`/anomalies/${profileId}`);
}

export function sendChatMessage(payload: ChatMessageRequest) {
  return request<ChatMessageResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
