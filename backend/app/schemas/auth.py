from datetime import datetime

from pydantic import AliasChoices, BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    mobile_number: str = Field(min_length=10, max_length=30)
    password: str = Field(max_length=256)
    display_name: str = Field(min_length=1, max_length=100)
    invitation_code: str | None = Field(default=None, max_length=100)
    terms_privacy_accepted: bool = False


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320, validation_alias=AliasChoices("identifier", "email"))
    password: str = Field(max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(RefreshRequest):
    pass


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(max_length=256)


class PasswordResetTokenRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


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
    mobile_number: str | None
    status: str
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    learner_id: str


class RegisterResponse(AccountRead):
    tokens: TokenPair
