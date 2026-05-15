from functools import lru_cache
from pydantic import AnyHttpUrl, Field, field_validator
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
    admin_credential_hash: str = Field(min_length=20)
    admin_role: str = "admin"
    mfa_required: bool = False
    mfa_seed: str | None = None
    session_minutes: int = 480
    cors_origins: str = "https://q-central.zt.q-home.local"
    zerotier_network_id: str | None = None
    zerotier_api_token: str | None = None
    auto_authorize: bool = True
    log_level: str = "INFO"
    metrics_enabled: bool = True
    ota_verify_signatures: bool = True
    ota_public_key_pem: str | None = None
    geoip_allowed_countries: str = ""

    @field_validator("secret_key", "admin_credential_hash")
    @classmethod
    def reject_defaults(cls, value: str) -> str:
        if value.startswith("change-me") or value.startswith("replace-"):
            raise ValueError("production credential values must be changed")
        return value

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def allowed_country_list(self) -> list[str]:
        return [x.strip().upper() for x in self.geoip_allowed_countries.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
