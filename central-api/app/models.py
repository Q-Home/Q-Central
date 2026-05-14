from pydantic import BaseModel, Field
from typing import Any, Literal

DeviceStatus = Literal["registered", "pending", "authorized", "online", "offline", "blocked"]

class SerialCreate(BaseModel):
    serial: str
    name: str = "Unclaimed Q-Box"
    claim_token: str = "dev-claim-token"
    customer: str | None = None
    site: str | None = None
    model: str | None = None

class Device(BaseModel):
    serial: str
    name: str
    claim_token: str
    customer: str | None = None
    site: str | None = None
    model: str | None = None
    zerotier_node_id: str | None = None
    zerotier_ip: str | None = None
    authorized: bool = False
    status: DeviceStatus = "registered"
    firmware: str | None = None
    apps: list[str] = Field(default_factory=list)
    last_seen: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ProvisionRequest(BaseModel):
    serial: str
    claim_token: str
    hostname: str
    model: str | None = None
    firmware: str | None = None
    zerotier_node_id: str | None = None
    zerotier_ip: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ProvisionResponse(BaseModel):
    accepted: bool
    authorized: bool
    message: str
    config: dict[str, Any] = Field(default_factory=dict)

class Heartbeat(BaseModel):
    serial: str
    claim_token: str
    status: str = "online"
    firmware: str | None = None
    apps: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

class CustomerMapping(BaseModel):
    customer: str
    site: str | None = None
    name: str | None = None

class OtaJob(BaseModel):
    id: str
    serial: str
    target_firmware: str | None = None
    app: str | None = None
    command: str | None = None
    status: str = "queued"

class AppInstall(BaseModel):
    serial: str
    app: str
    version: str | None = None
