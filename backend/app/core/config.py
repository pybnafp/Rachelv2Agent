from functools import lru_cache
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 720
    data_dir: Path = Field(Path("data/jobs"),
                           validation_alias=AliasChoices("DATA_DIR", "data_dir"))
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    default_llm_name: str = "deepseek"
    max_heavy_atoms: int = 80
    max_running_per_user: int = 3
    testing: bool = False
    pubchem_offline: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
