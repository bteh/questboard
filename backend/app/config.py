from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    database_url: str = ""
    llm_provider: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    resume_dir: str = "knowledge"
    config_dir: str = "config"
    data_dir: str = "data"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "job_tracker.db")

def get_settings() -> Settings:
    return Settings()
