# EnergyPilot AI — backend

FastAPI-скелет под MVP-скоуп (см. корневой `CLAUDE.md`). Загрузка счёта
(`app/services/bills_service.py`) уже делает реальный OCR; прогноз/аномалии/
чат пока возвращают моковые данные — подключаются следующим шагом, без
изменения контрактов роутеров.

## Структура

```
app/
  main.py            # создание FastAPI-приложения, CORS, регистрация роутеров
  core/config.py      # настройки из env/.env
  routers/            # HTTP-слой: онбординг, счета, прогноз, аномалии, чат
  models/schemas.py   # Pydantic-контракты запросов/ответов
  services/           # бизнес-логика (bills_service.py — реальный OCR,
                       # остальное пока моки, один файл на фичу)
```

## Системные зависимости

OCR загрузки счёта использует `tesseract-ocr` через `pytesseract` — сам
бинарник pip не ставит, нужен отдельно:

```bash
# macOS
brew install tesseract
# для распознавания кириллицы (казахстанские счета на русском) —
# положить rus.traineddata в tessdata, brew ставит только eng/osd/snum:
curl -fsSL -o "$(brew --prefix tesseract)/share/tessdata/rus.traineddata" \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/rus.traineddata

# Debian/Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-rus
```

В Docker-образе (`Dockerfile`) это уже прописано через `apt-get`.

**Честно про качество:** движок офлайн и бесплатный, но заметно слабее
облачных OCR на неровных/тёмных фото — таков компромисс за отсутствие
ключей/оплаты на хакатоне. Поэтому в `bills_service.py` любой низкой
уверенности или нераспознанной сумме сервис не подставляет случайные
цифры, а возвращает `requires_manual_review: true` — фронт всегда даёт
поправить руками.

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
