// Пока нет авторизации/сессий на бэкенде, profile_id из онбординга
// прокидывается между страницами через localStorage — этого достаточно
// для демо-сценария одного пользователя в рамках хакатона.
import { useSyncExternalStore } from "react";

const PROFILE_ID_KEY = "energypilot_profile_id";

export function saveProfileId(profileId: string) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(PROFILE_ID_KEY, profileId);
  }
}

export function getProfileId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(PROFILE_ID_KEY);
}

/**
 * profile_id как React-состояние без hydration mismatch.
 *
 * Проблема: `useState(() => getProfileId())` на сервере даёт null (нет
 * localStorage), на клиенте — реальный id; ветвление рендера по этому
 * значению ломает гидрацию («Hydration failed...»). useSyncExternalStore —
 * штатный способ читать client-only значение: во время SSR/гидрации отдаёт
 * серверный снапшот `undefined` («ещё не знаем»), сразу после гидрации —
 * реальное значение из localStorage.
 *
 * Возвращает: undefined — гидрация не завершена (покажи плейсхолдер),
 * null — профиля нет (отправь в онбординг), string — profile_id.
 */
export function useProfileId(): string | null | undefined {
  return useSyncExternalStore(
    // Подписка не нужна: id меняется только через redirect после онбординга.
    () => () => {},
    () => getProfileId(),
    () => undefined,
  );
}
