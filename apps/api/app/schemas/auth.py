from pydantic import BaseModel, EmailStr, Field

from app.schemas.users import UserPublic


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    otp_code: str | None = Field(
        default=None, max_length=32,
        description="6-digit TOTP or recovery code, required when 2FA is enabled",
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access_token expires
    user: UserPublic
