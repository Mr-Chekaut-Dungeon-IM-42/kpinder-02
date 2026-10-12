from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_BACKEND_ROOT / ".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 10080
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
