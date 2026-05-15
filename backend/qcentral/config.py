from functools import lru_cache
from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="Q_CENTRAL_", env_file=".env", extra="ignore")

    hostname: str = "q-central.zt.q-home.local"
    external_url: AnyHttpUrl = "https://q-central.zt.q-home.local"
    db_path: str = "/data/qcentral.db"
    secret_key: str = Field(min_length=32)
    admin_token: str = Field(min_length=32)
    cors_origins: str = "https://q-central.zt.q-home.local"
    zerotier_network_id: str | None = None
    zerotier_api_token: str | None = None
    auto_authorize: bool = True
    log_level: str = "INFO"

    @field_validator("secret_key", "admin_token")
    @classmethod
    def reject_defaults(cls, value: str) -> str:
        if value.startswith("change-me") or value.startswith("replace-"):
            raise ValueError("production secrets must be changed")
        return value

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
