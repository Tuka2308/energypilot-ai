from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.base import init_db
from app.routers import anomalies, bills, chat, forecast, onboarding


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём таблицы при старте (create_all идемпотентен, данные в volume
    # Postgres не трогает — см. app/db/base.init_db). Docker-compose держит
    # backend через depends_on: db healthy, поэтому Postgres уже готов.
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS открыт под локальный Next.js дев-сервер — на хакатоне фронт и бэк
# всегда идут парой, отдельный env для origin пока избыточен.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(onboarding.router)
app.include_router(bills.router)
app.include_router(forecast.router)
app.include_router(anomalies.router)
app.include_router(chat.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
