from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    display_name: str = Field(min_length=1, max_length=100)
    invitation_code: str | None = Field(default=None, max_length=100)
    terms_privacy_accepted: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(RefreshRequest):
    pass


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(max_length=256)


class PasswordResetTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PasswordResetRequestResponse(BaseModel):
    message: str


class PasswordResetConfirmResponse(BaseModel):
    message: str


class PasswordResetTokenResponse(BaseModel):
    valid: bool


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AccountRead(BaseModel):
    id: str
    email: EmailStr
    status: str
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    learner_id: str


class RegisterResponse(AccountRead):
    tokens: TokenPair
