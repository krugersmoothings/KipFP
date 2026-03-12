from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "KipFP"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+asyncpg://kipfp:kipfp@db:5432/kipfp"
    REDIS_URL: str = "redis://redis:6379/0"

    SECRET_KEY: str = "change-me-to-a-random-64-char-string"
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

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
