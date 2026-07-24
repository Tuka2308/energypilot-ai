"""Подключение к PostgreSQL: engine, фабрика сессий, DI-зависимость.

SQLAlchemy 2.x + psycopg (v3). Драйвер psycopg2 сознательно НЕ используется:
его binary-пакет не собирается под локальный Python 3.14 (проверено в этом
проекте раньше). psycopg[binary] 3.x даёт готовые wheel'ы и для 3.14 (venv),
и для 3.12-slim (контейнер).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей (app/db/models.py)."""


def _with_driver(url: str) -> str:
    """Подставляет драйвер psycopg в схему URL.

    В .env/docker-compose URL записан нейтрально (`postgresql://...`), чтобы
    то же значение годилось для psql и внешних инструментов. SQLAlchemy же
    должен знать драйвер явно, иначе по умолчанию тянет psycopg2 (которого у
    нас нет). Поэтому нормализуем схему здесь, а не заставляем менять env.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


# pool_pre_ping: проверяет соединение перед выдачей из пула — переживает
# перезапуск Postgres/разрыв простаивающего коннекта без 500 на первом
# запросе. expire_on_commit=False: сервисы конвертируют ORM-объекты в
# Pydantic/dataclass до конца запроса, атрибуты не должны протухать после
# commit.
engine = create_engine(_with_driver(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: сессия на один запрос, всегда закрывается.

    Никакого глобального состояния — роутер получает сессию через
    Depends(get_db) и прокидывает её в сервисы.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Создаёт таблицы при старте приложения.

    Осознанно `create_all`, без Alembic: для хакатона схема простая и меняется
    редко, а миграции добавили бы инфраструктуру и шаг в запуск. `create_all`
    идемпотентен (создаёт только отсутствующие таблицы) и не трогает уже
    существующие данные в volume Postgres. Для продакшена следующий шаг —
    Alembic, чтобы менять схему без потери данных.
    """
    # Импорт здесь, а не сверху: гарантирует, что модели зарегистрированы в
    # Base.metadata к моменту create_all, и не создаёт циклических импортов.
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
