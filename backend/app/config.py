from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas"
    secret_key: str = "change-me"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    strava_client_id: str = Field(default="", validation_alias=AliasChoices("STRAVA_CLIENT_ID", "client_id"))
    strava_client_secret: str = Field(default="", validation_alias=AliasChoices("STRAVA_CLIENT_SECRET", "client_secret"))
    strava_verify_token: str = "change-me"
    strava_webhook_secret: str = ""
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "atlas-photos"
    s3_public_base_url: str = "http://localhost:9000/atlas-photos"


settings = Settings()
