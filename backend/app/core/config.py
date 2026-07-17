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
    openai_model: str = "gpt-4o-mini"
    # Офлайн-fallback по стеку CLAUDE.md: локальный Ollama, если нет ключа
    # OpenAI (например, http://localhost:11434).
    ollama_base_url: str | None = None
    ollama_model: str = "llama3.1"

    # Next.js dev-сервер занимает следующий свободный порт (3000, 3001,
    # 3002...), если предыдущий держит зависший процесс. Перечисляем эти
    # порты явно и для localhost, и для 127.0.0.1 (браузер считает их
    # разными origin) — не открываем "*", чтобы список оставался осознанным
    # dev-белым списком.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
