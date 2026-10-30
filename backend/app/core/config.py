from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cache_path() -> str:
    backend_dir = Path(__file__).resolve().parents[2]
    return str(backend_dir / ".cache" / "analysis.sqlite3")


def _backend_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    project_name: str = "AI Codebase Mapper API"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cache_db_path: str = Field(default_factory=_default_cache_path)

    model_config = SettingsConfigDict(env_file=_backend_env_path(), env_file_encoding="utf-8", extra="ignore")


settings = Settings()
