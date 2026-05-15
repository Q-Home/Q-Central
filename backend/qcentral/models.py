from datetime import datetime, timezone
from enum import Enum
from sqlmodel import Field, SQLModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class DeviceStatus(str, Enum):
    pending = "pending"
    online = "online"
    offline = "offline"
    disabled = "disabled"


class Device(SQLModel, table=True):
    serial: str = Field(primary_key=True, index=True)
    claim_token_hash: str
    agent_token_hash: str | None = None
    name: str | None = None
    customer: str | None = None
    site: str | None = None
    model: str | None = None
    ip_address: str | None = None
    zerotier_node_id: str | None = None
    zerotier_network_id: str | None = None
    firmware: str | None = None
    target_firmware: str | None = None
    authorized: bool = False
    status: DeviceStatus = DeviceStatus.pending
    last_seen: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    event: str
    actor: str
    serial: str | None = None
    detail: str | None = None
    created_at: datetime = Field(default_factory=now_utc)


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    serial: str = Field(index=True)
    kind: str
    payload_json: str
    status: str = "queued"
    result: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
