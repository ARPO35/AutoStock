from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AutoStock"
    app_version: str = "0.1.0"
    data_dir: str = Field(default="/app/data")
    sqlite_path: str = Field(default="/app/data/app.db")
    frontend_dist_path: str = Field(default="/app/frontend_dist")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    model_config = SettingsConfigDict(
        env_prefix="AUTOSTOCK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
