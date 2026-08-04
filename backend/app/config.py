from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    warble_api_key: str
    warble_base_url: str = "https://warble.shortlistos.com/v1"

    # Expects an async-driver URL: postgresql+asyncpg://... for Supabase/Postgres,
    # or the sqlite+aiosqlite default below for local dev.
    database_url: str = "sqlite+aiosqlite:///./warble.db"

    # Optional: the marketing agent degrades to its deterministic answers
    # when this is unset. Declared here (rather than read straight off
    # os.environ) because pydantic-settings loads .env into this object
    # only — it never exports into the process environment, so a key that
    # lives in .env is invisible to os.environ.get().
    anthropic_api_key: str | None = None


settings = Settings()
