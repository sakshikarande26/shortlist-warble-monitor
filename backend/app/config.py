from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    warble_api_key: str
    warble_base_url: str = "https://warble.shortlistos.com/v1"


settings = Settings()
