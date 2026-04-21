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
    # Default PRODUCTION: safer for deploys que olvidan setear la env
    # (ej. Railway sin APP_ENV explícita). En dev local, el `.env` lo
    # override a "development" y el cookie sale SameSite=Lax + no Secure.
    APP_ENV: str = "production"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    # Regex de orígenes permitidos — complementa (no reemplaza) CORS_ORIGINS.
    # Uso principal: preview URLs de Vercel, que tienen un subdominio único
    # por commit (`<project>-git-<hash>-<team>.vercel.app`) y no se pueden
    # listar explícitamente. El default cubre las previews del team actual
    # sin requerir tocar env vars en Railway para cada deploy.
    #
    # Patrón: cualquier URL que empiece con el nombre del proyecto, tenga
    # algo en el medio, y termine con `-<team>-projects.vercel.app`. No
    # matchea proyectos ajenos (evita que una URL arbitraria con "vercel.app"
    # al final sirva para CSRF contra este backend).
    CORS_ORIGIN_REGEX: str = (
        r"^https://ia-agent-quote-marble-operator-.+-javi10824s-projects\.vercel\.app$"
    )
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
