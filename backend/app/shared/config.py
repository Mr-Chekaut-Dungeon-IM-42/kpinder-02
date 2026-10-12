from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_BACKEND_ROOT / ".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 10080
    cors_origins: list[str] = ["http://localhost:5173"]

    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_presigned_url_ttl_seconds: int = 3600

    matching_radius_km: float = 50.0
    matching_feed_size: int = 20


settings = Settings()
