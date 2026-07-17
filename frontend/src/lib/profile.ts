// Пока нет авторизации/сессий на бэкенде, profile_id из онбординга
// прокидывается между страницами через localStorage — этого достаточно
// для демо-сценария одного пользователя в рамках хакатона.
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
