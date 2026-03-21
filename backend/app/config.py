import os

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = ""
    llm_provider: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    allow_runtime_llm_config: bool = True
    resume_dir: str = "knowledge"
    config_dir: str = "config"
    data_dir: str = "data"
    hosted_mode: bool = False
    session_cookie_name: str = "lb_session"
    csrf_cookie_name: str = "lb_csrf"
    session_secure_cookies: bool = False
    workspace_ttl_days: int = 7
    workspace_storage_dir: str = ""
    location_provider: str = "local"
    pelias_url: str = ""
    location_cache_ttl_seconds: int = 1800
    location_rate_limit_per_minute: int = 90
    upload_rate_limit_per_minute: int = 12
    search_rate_limit_per_minute: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "job_tracker.db")

    @property
    def resolved_workspace_storage_dir(self) -> str:
        if self.workspace_storage_dir:
            return self.workspace_storage_dir
        return os.path.join(self.data_dir, "workspaces")

def get_settings() -> Settings:
    return Settings()
