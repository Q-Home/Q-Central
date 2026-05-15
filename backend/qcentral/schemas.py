from pydantic import BaseModel
from typing import Any


class LoginRequest(BaseModel):
    username: str
    password: str | None = None
    credential: str | None = None
    code: str | None = None


class RegisterSerialRequest(BaseModel):
    serial: str
    customer: str | None = None
    site: str | None = None
    name: str | None = None
    model: str | None = None


class RegisterSerialResponse(BaseModel):
    serial: str
    claim_token: str


class ProvisionRequest(BaseModel):
    serial: str
    claim_token: str
    model: str | None = None
    firmware: str | None = None
    zerotier_node_id: str | None = None
    ip_address: str | None = None


class ProvisionResponse(BaseModel):
    serial: str
    authorized: bool
    agent_token: str
    central_url: str


class HeartbeatRequest(BaseModel):
    serial: str
    firmware: str | None = None
    ip_address: str | None = None
    apps: list[str] = []
    metrics: dict[str, Any] = {}


class JobCreateRequest(BaseModel):
    serial: str
    kind: str
    payload: dict[str, Any]
