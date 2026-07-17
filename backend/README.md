# EnergyPilot AI — backend

FastAPI-скелет под MVP-скоуп (см. корневой `CLAUDE.md`). Все роуты сейчас
возвращают моковые данные — реальные OCR/ML/LLM подключаются следующим шагом
в соответствующих `app/services/*`, без изменения контрактов роутеров.

## Структура

```
app/
  main.py            # создание FastAPI-приложения, CORS, регистрация роутеров
  core/config.py      # настройки из env/.env
  routers/            # HTTP-слой: онбординг, счета, прогноз, аномалии, чат
  models/schemas.py   # Pydantic-контракты запросов/ответов
  services/           # бизнес-логика (пока моки, один файл на фичу)
```

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Открыть `http://localhost:8000/docs` — Swagger со всеми эндпоинтами.

Через Docker — см. `docker-compose.yml` в корне репозитория.
