from pydantic import model_validator
from pydantic_settings import BaseSettings


_INSECURE_DEFAULT = "change-me-to-a-random-64-char-string"


class Settings(BaseSettings):
    PROJECT_NAME: str = "KipFP"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+asyncpg://kipfp:kipfp@db:5432/kipfp"
    REDIS_URL: str = "redis://redis:6379/0"

    # FIX(C1): default was publicly known, allowing JWT forgery
    SECRET_KEY: str = _INSECURE_DEFAULT

    @model_validator(mode="after")
    def _reject_insecure_secret(self) -> "Settings":
        if self.SECRET_KEY == _INSECURE_DEFAULT:
            raise ValueError(
                "SECRET_KEY env var must be set to a random secret — "
                "the default value is publicly known and insecure"
            )
        return self

    ACCESS_TOKEN_EXPIRE_HOURS: int = 24
    JWT_ALGORITHM: str = "HS256"

    NETSUITE_ACCOUNT_ID: str = ""
    NETSUITE_CONSUMER_KEY: str = ""
    NETSUITE_CONSUMER_SECRET: str = ""
    NETSUITE_TOKEN_KEY: str = ""
    NETSUITE_TOKEN_SECRET: str = ""

    XERO_CLIENT_ID: str = ""
    XERO_CLIENT_SECRET: str = ""
    XERO_REDIRECT_URI: str = "http://localhost:8000/api/v1/connectors/xero/callback"

    BIGQUERY_SERVICE_ACCOUNT_JSON: str = ""
    BIGQUERY_SA_KEY_FILE: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
