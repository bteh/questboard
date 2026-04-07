import os
import subprocess
from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_release: str = ""
    database_url: str = ""
    manage_schema_on_startup: bool | None = None
    llm_provider: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    allow_runtime_llm_config: bool = True
    resume_dir: str = "knowledge"
    config_dir: str = "config"
    data_dir: str = "data"
    hosted_mode: bool = False
    dev_hosted_auth: bool = False
    dev_hosted_auth_secret: str = ""
    dev_hosted_auth_issuer: str = "https://launchboard.dev.local/auth/v1"
    dev_hosted_personas_path: str = ""
    dev_hosted_auth_token_ttl_hours: int = 12
    session_cookie_name: str = "lb_session"
    csrf_cookie_name: str = "lb_csrf"
    session_secure_cookies: bool = False
    embedded_scheduler_enabled: bool | None = None
    workspace_ttl_days: int = 7
    workspace_storage_dir: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "launchboard-private"
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    hosted_platform_managed_ai: bool = True
    hosted_allow_workspace_llm_config: bool = False
    worker_id: str = ""
    worker_poll_interval_seconds: float = 2.0
    worker_lease_seconds: int = 120
    worker_retry_base_seconds: int = 15
    location_provider: str = "local"
    pelias_url: str = ""
    location_cache_ttl_seconds: int = 1800
    location_rate_limit_per_minute: int = 90
    upload_rate_limit_per_minute: int = 12
    search_rate_limit_per_minute: int = 20
    search_suggest_timeout_seconds: int = 25

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "job_tracker.db")

    @property
    def resolved_database_url(self) -> str:
        return self.database_url.strip() or f"sqlite:///{self.db_path}"

    @property
    def using_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite:///")

    @property
    def resolved_workspace_storage_dir(self) -> str:
        if self.workspace_storage_dir:
            return self.workspace_storage_dir
        return os.path.join(self.data_dir, "workspaces")

    @property
    def resolved_supabase_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url.rstrip("/")
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def dev_hosted_auth_enabled(self) -> bool:
        return bool(self.hosted_mode and self.dev_hosted_auth)

    @property
    def resolved_dev_hosted_auth_secret(self) -> str:
        return self.dev_hosted_auth_secret.strip() or "launchboard-dev-hosted-auth-secret-key"

    @property
    def resolved_dev_hosted_auth_issuer(self) -> str:
        return self.dev_hosted_auth_issuer.strip() or "https://launchboard.dev.local/auth/v1"

    @property
    def allow_workspace_llm_config(self) -> bool:
        if self.hosted_mode:
            return bool(self.hosted_allow_workspace_llm_config)
        return bool(self.allow_runtime_llm_config)

    @property
    def should_manage_schema_on_startup(self) -> bool:
        if self.manage_schema_on_startup is not None:
            return bool(self.manage_schema_on_startup)
        return self.using_sqlite

    @property
    def use_embedded_scheduler(self) -> bool:
        if self.embedded_scheduler_enabled is not None:
            return bool(self.embedded_scheduler_enabled)
        return not self.hosted_mode

    @cached_property
    def resolved_app_release(self) -> str:
        explicit = self.app_release.strip()
        if explicit:
            return explicit

        repo_root = Path(__file__).resolve().parents[2]
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_root,
                check=False,
            )
        except Exception:
            result = None

        if result and result.returncode == 0:
            release = result.stdout.strip()
            if release:
                return release

        return "dev"


def get_settings() -> Settings:
    return Settings()
