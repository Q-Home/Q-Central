from pydantic import BaseModel, Field
from typing import Any


class LoginRequest(BaseModel):
    username: str
    password: str | None = None
    credential: str | None = None
    code: str | None = None


class ProfileUpdateRequest(BaseModel):
    current_value: str
    new_value: str


class UserCreateRequest(BaseModel):
    username: str
    initial_value: str
    role: str = "readonly"
    full_name: str | None = None
    email: str | None = None
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    username: str | None = None
    role: str | None = None
    full_name: str | None = None
    email: str | None = None
    is_active: bool | None = None
    new_value: str | None = None


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
    apps: list[Any] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class JobCreateRequest(BaseModel):
    serial: str
    kind: str
    payload: dict[str, Any]
