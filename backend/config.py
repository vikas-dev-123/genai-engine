"""Application configuration loaded from environment."""

from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for Jarvis AI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "Jarvis AI"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_TEMPERATURE: float = 0.7

    # Embeddings (Gemini free)
    EMBEDDING_MODEL: str = "models/text-embedding-004"

    # Database
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Voice
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "EXAVITQu4vr4xnSDxMaL"
    WHISPER_MODEL: str = "base.en"

    # RAG
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150
    MAX_RAG_RESULTS: int = 8
    FAISS_INDEX_DIR: str = "./data/faiss"

    # Tools
    ALLOWED_API_DOMAINS: list[str] = [
        "api.github.com",
        "httpbin.org",
    ]
    WORKSPACE_DIR: str = "./data/workspace"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @field_validator("CORS_ORIGINS", "ALLOWED_API_DOMAINS", mode="before")
    @classmethod
    def parse_comma_separated_list(cls, v: Any) -> list[str] | Any:
        """Allow comma-separated env strings for list fields."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


settings = Settings()
