# EnergyPilot AI

AI-ассистент, который по загруженному счёту / фото счётчика и короткой
анкете квартиры даёт прогноз следующего счёта за электричество, разбор
расхода по категориям, флаги аномалий и советы по экономии через чат.
Контекст задачи и MVP-скоуп — в [CLAUDE.md](CLAUDE.md) и
[docs/research-context.md](docs/research-context.md).

**Честная пометка:** CustDev в исследовании — синтетический (гипотезы,
выведенные из открытых макроданных KEGOC/Минэнерго/тарифных приказов), а не
реальные интервью. Регламент хакатона допускает это при открытом указании.

## Стек

| Слой | Технология |
|---|---|
| Frontend | Next.js (App Router) + Tailwind CSS |
| Backend | FastAPI |
| OCR | Tesseract (через pytesseract) — офлайн, без ключей/оплаты. Для цифровых PDF (типовые квитанции ЭСО) вместо OCR читается текстовый слой/таблица напрямую через PyMuPDF — точнее и без риска перепутать колонки |
| ML (прогноз) | Prophet — одна модель, без ансамбля (см. MVP-скоуп в CLAUDE.md) |
| Аномалии | Пороговое правило (не ML) — рост потребления ≥30% к базе пользователя |
| LLM (чат) | Каскад: **OpenAI** (основной путь) → Gemini → Ollama (офлайн) → детерминированный fallback. Gemini free tier у команды недоступен из-за регионального ограничения аккаунта Google — см. [backend/README.md](backend/README.md#ai-чат-энергокоуч-structured-pipeline) |
| DB | PostgreSQL |
| Deploy | Docker (docker-compose) + Railway |

## Архитектура

Поток данных на примере одного запроса в чат — от формы до ответа коуча:

```
Браузер (Next.js, :3000)
   │  fetch, JSON/multipart
   ▼
FastAPI (:8000)  ─┬─ routers/        HTTP-слой: онбординг, счета, прогноз, аномалии, чат
                   ├─ models/schemas.py   Pydantic-контракты запросов/ответов
                   └─ services/       бизнес-логика:
                        onboarding_service   — профиль квартиры/техники/тарифа
                        bills_service        — OCR/разбор счёта (Tesseract | PyMuPDF-таблица)
                        bill_history_service — история подтверждённых счетов профиля
                        forecast_service      — прогноз (Prophet) + доверительный интервал
                        anomalies_service     — пороговое правило по истории
                        chat_service          — LLM-пайплайн:
                              1. собирает контекст из ВСЕХ сервисов выше
                                 (профиль + прогноз + аномалии + тариф)
                              2. рендерит в явный блок фактов для промпта
                              3. вызывает LLM-каскад (OpenAI → Gemini → Ollama → offline)
                              4. держит память диалога по profile_id
   │
   ▼
PostgreSQL (:5432)  — поднимается в docker-compose, приложение пока хранит
                       профили/историю в памяти процесса (следующий шаг —
                       перенести в БД, схема готова к этому)
```

Ключевой момент архитектуры: у чата **нет собственной аналитики** — весь
контекст для LLM собирается из тех же сервисов, что кормят дашборд, поэтому
ответ коуча не может разойтись с цифрами на экране. Подробности каждой
фичи (почему именно такой порог аномалий, почему Prophet без сезонности на
короткой истории, как читается табличный PDF) — в
[backend/README.md](backend/README.md).

## Локальный запуск с нуля

Проверено пошагово от чистого клонирования до рабочего демо.

### 0. Что нужно заранее

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose (идут вместе в Docker Desktop)
- [Node.js](https://nodejs.org/) 20+ и npm
- Ключ OpenAI (для реального AI-чата — см. шаг 2; без ключа приложение всё
  равно работает, чат просто отвечает в офлайн-режиме)

### 1. Клонировать репозиторий

```bash
git clone https://github.com/Tuka2308/energypilot-ai.git
cd energypilot-ai
```

### 2. Настроить backend/.env

```bash
cp backend/.env.example backend/.env
```

Открыть `backend/.env` и заполнить хотя бы `OPENAI_API_KEY` (остальное можно
оставить пустым — есть дефолты и офлайн-fallback):

| Переменная | Обязательна? | Что это | Где взять |
|---|---|---|---|
| `OPENAI_API_KEY` | Рекомендуется | Ключ для AI-чата (основной провайдер) | https://platform.openai.com/api-keys |
| `OPENAI_MODEL` | Нет (дефолт `gpt-4o-mini`) | Модель OpenAI | — |
| `GEMINI_API_KEY` | Нет | Запасной LLM-провайдер в каскаде | https://aistudio.google.com/apikey — у нашей команды упирается в `429 limit: 0` (региональное ограничение аккаунта Google), поэтому не основной путь |
| `OLLAMA_BASE_URL` | Нет | Локальная модель как офлайн-запасной вариант | см. таблицу в [backend/README.md](backend/README.md) — значение отличается для Docker (`host.docker.internal`) и для запуска вне Docker (`localhost`) |
| `DATABASE_URL` | Нет (задаётся в docker-compose) | Строка подключения к Postgres | — |
| `CORS_ORIGINS` | Нет (есть безопасный dev-дефолт) | Какие origin фронтенда бэкенд пускает | — |

Без `OPENAI_API_KEY` (и остальных LLM-ключей) чат **не падает** — отвечает
в детерминированном офлайн-режиме с честной пометкой об этом. Остальные
фичи (OCR, прогноз, аномалии) от LLM-ключей не зависят вообще.

### 3. Поднять backend + PostgreSQL

```bash
docker compose up --build
```

Первая сборка компилирует CmdStan для Prophet — уходит несколько минут,
дальше кешируется в слое образа. Ждать в логах:

```
energypilot-ai-db-1       | ... database system is ready to accept connections
energypilot-ai-backend-1  | INFO:     Application startup complete.
```

Backend — на `http://localhost:8000`, Swagger со всеми эндпоинтами — на
`http://localhost:8000/docs`. Быстрая проверка в отдельном терминале:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 4. Поднять frontend

В отдельном терминале (frontend не в docker-compose — так сохраняется
быстрый hot-reload):

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Открыть `http://localhost:3000`.

### 5. Пройти демо-флоу

1. `/onboarding` — заполнить квартиру/технику/тариф одной формой.
2. `/bills` — загрузить счёт (в репозитории есть тестовая квитанция
   `backend/tests/fixtures/sample_receipt_kz.pdf` для проверки без
   реального документа) или ввести данные вручную. Для прогноза и
   аномалий нужно 3+ счетов за разные месяцы.
3. `/dashboard` — прогноз с доверительным интервалом, разбивка по
   категориям, карточка аномалии (если есть), переход в чат с
   готовым контекстным вопросом.
4. `/chat` — спросить энергокоуча; с заполненным `OPENAI_API_KEY`
   ответ реальный и персональный, без ключа — офлайн-fallback с
   пометкой об этом.

### Порты

| Порт | Что |
|---|---|
| `3000` | Frontend (Next.js dev-сервер) |
| `8000` | Backend (FastAPI), Swagger на `/docs` |
| `5432` | PostgreSQL (из docker-compose) |

### Тесты

Из корня репозитория, пока backend поднят через `docker compose up`:

```bash
docker compose exec backend python -m pytest
```

Или локально (см. [backend/README.md](backend/README.md#локальный-запуск-без-docker)):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pytest
```

Подробности по каждой фиче (OCR, Prophet-прогноз, пороговое правило
аномалий, чат-пайплайн) и системные зависимости — в
[backend/README.md](backend/README.md). Структура фронтенда — в
[frontend/README.md](frontend/README.md).
