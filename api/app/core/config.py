from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json


class Settings(BaseSettings):
    DATABASE_URL: str
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5-20250514"
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "service-account.json"
    GOOGLE_DRIVE_FOLDER_ID: str
    APP_ENV: str = "development"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    SECRET_KEY: str
    QUOTE_API_KEY: str = ""
    OPERATOR_EMAIL: str = ""
    OPERATOR_PASSWORD_HASH: str = ""
    OUTPUT_DIR: str = ""
    CATALOG_VOLUME_DIR: str = ""  # Persistent volume path for catalogs (Railway)
    SERVICE_ACCOUNT_BASE64: str = ""

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def validate_secret_key(cls, v):
        if len(v) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",")]
        return v

    model_config = {"env_file": ".env"}


settings = Settings()
