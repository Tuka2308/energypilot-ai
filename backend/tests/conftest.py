"""Тестовая инфраструктура: изолированная БД PostgreSQL + фикстуры.

Тесты гоняются на ОТДЕЛЬНОЙ базе `energypilot_test` (тот же сервер Postgres,
что подняли docker-compose'ом), чтобы прогоны не зависели от порядка и не
загрязняли рабочие данные. Перед каждым тестом все таблицы очищаются, так
что тесты полностью изолированы друг от друга.

БД создаётся автоматически при первом запуске (CREATE DATABASE через
maintenance-подключение к `postgres`), таблицы — через тот же create_all,
что и в приложении. Так тесты заодно проверяют реальный драйвер psycopg и
реальную схему, а не SQLite-суррогат.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import app.db.models  # noqa: F401  — регистрирует модели в Base.metadata
from app.core.config import settings
from app.db.base import Base, _with_driver
from app.models.schemas import OnboardingRequest, TariffType
from app.services import onboarding_service

TEST_DB_NAME = "energypilot_test"

_base_url = make_url(_with_driver(settings.database_url))
_test_url = _base_url.set(database=TEST_DB_NAME)


def _ensure_test_database() -> None:
    """CREATE DATABASE energypilot_test, если её ещё нет (через подключение к
    служебной БД postgres в режиме AUTOCOMMIT — CREATE DATABASE нельзя в
    транзакции)."""
    admin_engine = create_engine(_base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        admin_engine.dispose()


_ensure_test_database()
_test_engine = create_engine(_test_url)
Base.metadata.create_all(bind=_test_engine)
_TestSession = sessionmaker(bind=_test_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Чистая БД перед каждым тестом. CASCADE снимает зависимости FK, RESTART
    IDENTITY сбрасывает автоинкременты — прогоны не зависят от порядка."""
    with _test_engine.begin() as conn:
        conn.execute(text("TRUNCATE profiles, appliances, bills RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture()
def db():
    """Сессия БД на один тест (закрывается в teardown)."""
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def make_profile(db):
    """Фабрика профилей: создаёт запись в profiles и возвращает profile_id.

    Нужна, потому что bills ссылается на profiles по FK — прежде чем засеять
    историю счетов, профиль должен существовать (в проде так и есть: сначала
    онбординг, потом счета)."""

    def _make(
        *,
        city: str = "Караганда",
        area_sqm: float = 55,
        occupants: int = 3,
        tariff_type: TariffType = TariffType.flat,
        tariff_rate: float | None = None,
        appliances: list | None = None,
    ) -> str:
        payload = OnboardingRequest(
            city=city,
            area_sqm=area_sqm,
            occupants=occupants,
            tariff_type=tariff_type,
            tariff_rate=tariff_rate,
            appliances=appliances or [],
        )
        return onboarding_service.create_profile(db, payload).profile_id

    return _make
