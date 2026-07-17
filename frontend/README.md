# EnergyPilot AI — frontend

Next.js (App Router) + Tailwind v4. Экраны повторяют MVP-скоуп из корневого
`CLAUDE.md`: анкета → загрузка счёта → дашборд → чат с энергокоучем.

## Структура

```
src/
  app/
    onboarding/  # единая форма: квартира + техника + тариф
    bills/       # загрузка счёта + fallback на ручную правку
    dashboard/   # прогноз, разбивка по категориям, аномалии
    chat/        # чат с энергокоучем
  lib/
    api.ts       # клиент к backend (fetch-обёртка)
    types.ts     # TS-типы, зеркалящие Pydantic-схемы backend
    profile.ts   # profile_id из онбординга хранится в localStorage —
                 # авторизации/сессий на бэкенде пока нет
  components/    # NavBar и общие UI-элементы
```

## Локальный запуск

```bash
npm install
cp .env.local.example .env.local
npm run dev
```

По умолчанию фронт ходит на `http://localhost:8000` (backend). Поменять —
через `NEXT_PUBLIC_API_URL` в `.env.local`.

Через Docker — см. `docker-compose.yml` в корне репозитория (backend там
поднимается вместе с PostgreSQL; frontend пока запускается локально через
`npm run dev`).
