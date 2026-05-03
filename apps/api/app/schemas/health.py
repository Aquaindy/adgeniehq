from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    app: str
    env: str
    version: str


class ComponentHealth(BaseModel):
    component: str
    status: Literal["ok", "error"]
    detail: str | None = None
