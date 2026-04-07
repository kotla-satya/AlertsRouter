from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/alerts_router"
    # secret_key: str = "change-me"
    # algorithm: str = "HS256"
    # access_token_expire_minutes: int = 1440


settings = Settings()
