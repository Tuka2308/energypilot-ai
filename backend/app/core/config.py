from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения / .env.

    На этапе скелета реально используется только пара полей (CORS, порт БД
    для docker-compose), остальные — заготовки под шаг с реальной логикой
    (OCR/ML/LLM), чтобы не переделывать конфиг позже.
    """

    app_name: str = "EnergyPilot AI API"
    environment: str = "development"

    database_url: str = "postgresql://energypilot:energypilot@localhost:5432/energypilot"

    openai_api_key: str | None = None
    ollama_base_url: str | None = None

    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
