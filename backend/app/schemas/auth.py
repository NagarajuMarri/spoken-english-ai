from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(RefreshRequest):
    pass


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
