"""Application configuration loaded from environment."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent

_env_files: list[str] = []
for candidate in (_REPO_ROOT / ".env", _BACKEND_DIR / ".env"):
    if candidate.is_file():
        _env_files.append(str(candidate))


class Settings(BaseSettings):
    """Central configuration for Jarvis AI backend."""

    model_config = SettingsConfigDict(
        env_file=_env_files or ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "Jarvis AI"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # Declared as str|list so .env comma-separated values are not JSON-decoded by pydantic-settings.
    CORS_ORIGINS: str | list[str] = "http://localhost:3000"

    # Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_TEMPERATURE: float = 0.7

    # Embeddings (Gemini free)
    EMBEDDING_MODEL: str = "models/text-embedding-004"

    # Database (default: local SQLite file — override for Postgres in production/Docker)
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/jarvis.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    # Use in-process fake Redis (no Redis server). OK for local dev; use real Redis in production.
    USE_FAKE_REDIS: bool = False

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
    ALLOWED_API_DOMAINS: str | list[str] = "api.github.com,httpbin.org"
    WORKSPACE_DIR: str = "./data/workspace"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @field_validator("CORS_ORIGINS", "ALLOWED_API_DOMAINS", mode="after")
    @classmethod
    def ensure_str_list(cls, v: str | list[str]) -> list[str]:
        """Normalize comma-separated env strings to list[str]."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


settings = Settings()
