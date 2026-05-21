from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RedeemRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64)


class AppSumoCodePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    redeemed_at: datetime | None = None


class AppSumoStatus(BaseModel):
    """Current AppSumo lifetime entitlement for a workspace."""

    tier: int
    codes_redeemed: int
    max_tier: int
    can_stack_more: bool
    plan_code: str | None = None
    plan_display_name: str | None = None
    codes: list[AppSumoCodePublic] = []


# --- Admin (superuser) ------------------------------------------------------


class AdminGenerateRequest(BaseModel):
    count: int = Field(ge=1, le=10_000)
    batch: str | None = Field(default=None, max_length=64)
    prefix: str = Field(default="ADV", max_length=8)


class AdminGenerateResponse(BaseModel):
    generated: int
    batch: str | None = None
    codes: list[str]


class CodeStats(BaseModel):
    total: int
    redeemed: int
    refunded: int
    unredeemed: int


class DeactivateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64)
