import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Codebase Mapper API"
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()