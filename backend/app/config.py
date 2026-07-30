from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    warble_api_key: str
    warble_base_url: str = "https://warble.shortlistos.com/v1"

    # Expects an async-driver URL: postgresql+asyncpg://... for Supabase/Postgres,
    # or the sqlite+aiosqlite default below for local dev.
    database_url: str = "sqlite+aiosqlite:///./warble.db"


settings = Settings()
