from functools import lru_cache
from typing import Literal
from uuid import UUID
from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="Q_CENTRAL_", env_file=".env", extra="ignore")

    hostname: str = "q-central.zt.q-home.local"
    external_url: AnyHttpUrl = "https://q-central.zt.q-home.local"
    database_url: str | None = None
    db_path: str = "/data/qcentral.db"
    cache_url: str | None = None
    secret_key: str = Field(min_length=32)
    admin_username: str = "admin"
    admin_credential_hash: str | None = Field(default=None, min_length=20)
    auth_mode: Literal["entra", "local"] = "entra"
    entra_tenant_id: UUID | None = None
    entra_client_id: UUID | None = None
    entra_client_secret: str | None = None
    entra_session_minutes: int = Field(default=15, ge=1, le=60)
    entra_admin_group_ids: str = ""
    entra_superadmin_group_ids: str = ""
    admin_role: str = "admin"
    mfa_required: bool = False
    mfa_seed: str | None = None
    session_minutes: int = 480
    cors_origins: str = "https://q-central.zt.q-home.local"
    zerotier_network_id: str | None = None
    zerotier_api_token: str | None = None
    github_token: str | None = None
    software_github_repo: str = "Q-Home/Q-Central"
    auto_authorize: bool = True
    log_level: str = "INFO"
    metrics_enabled: bool = True
    ota_verify_signatures: bool = True
    ota_public_key_pem: str | None = None
    geoip_allowed_countries: str = ""

    @field_validator("entra_admin_group_ids", "entra_superadmin_group_ids")
    @classmethod
    def validate_group_ids(cls, value: str) -> str:
        # Exact object IDs only; group names and wildcards cannot grant access.
        return ",".join(str(UUID(item.strip())) for item in value.split(",") if item.strip())

    @field_validator("entra_tenant_id", "entra_client_id", "entra_client_secret", mode="before")
    @classmethod
    def blank_entra_value(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("secret_key", "admin_credential_hash")
    @classmethod
    def reject_defaults(cls, value: str | None) -> str | None:
        if value and (value.startswith("change-me") or value.startswith("replace-")):
            raise ValueError("production credential values must be changed")
        return value

    @model_validator(mode="after")
    def validate_auth(self):
        if self.auth_mode == "local" and not self.admin_credential_hash:
            raise ValueError("local authentication requires an admin credential hash")
        if self.auth_mode == "entra" and self.external_url.scheme != "https":
            raise ValueError("Entra authentication requires an HTTPS external URL")
        return self

    @property
    def entra_configured(self) -> bool:
        return bool(self.entra_tenant_id and self.entra_client_id and self.entra_client_secret)

    @property
    def entra_redirect_uri(self) -> str:
        return str(self.external_url).rstrip("/") + "/api/auth/entra/callback"

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def allowed_country_list(self) -> list[str]:
        return [x.strip().upper() for x in self.geoip_allowed_countries.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
