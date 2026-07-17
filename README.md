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

- Frontend: Next.js (App Router) + Tailwind CSS
- Backend: FastAPI
- ML: scikit-learn / Prophet (подключается на следующем этапе)
- LLM: OpenAI API, fallback — Ollama офлайн (подключается на следующем этапе)
- DB: PostgreSQL
- Deploy: Docker + Railway

## Архитектура

```
frontend (Next.js) --HTTP/JSON--> backend (FastAPI) --> PostgreSQL
                                        |
                                        └-- services/ (пока моки,
                                            дальше: OCR / ML-прогноз /
                                            правило аномалий / LLM-чат)
```

Backend разложен по фичам онбординга, загрузки счёта, прогноза, аномалий и
чата: `routers/` — HTTP-слой, `models/schemas.py` — контракты
запросов/ответов, `services/` — бизнес-логика (сейчас заглушки с моковыми
ответами, чтобы фронт мог интегрироваться до готовности OCR/ML/LLM).

## Локальный запуск

Backend + PostgreSQL через Docker:

```bash
docker compose up --build
```

Backend поднимется на `http://localhost:8000` (Swagger — `/docs`).

Frontend — отдельно (пока не в docker-compose, чтобы сохранить быстрый
hot-reload):

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend — на `http://localhost:3000`.

Подробности по каждой части — в [backend/README.md](backend/README.md) и
[frontend/README.md](frontend/README.md).
