import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AuthEventType, Theme
from app.schemas.common import ORM, Str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)
    display_name: Str = Field(min_length=1, max_length=80)
    timezone: str = "Asia/Kolkata"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)
    remember: bool = False


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role_title: str | None
    timezone: str
    theme: Theme
    email_verified: bool
    onboarding_completed: bool
    has_password: bool


class AuthOut(BaseModel):
    access_token: str
    expires_in: int
    user: UserOut


class RefreshOut(BaseModel):
    access_token: str
    expires_in: int


class LogoutIn(BaseModel):
    all: bool = False


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class AuthEventOut(ORM):
    id: int
    event_type: AuthEventType
    ip: str | None
    user_agent: str | None
    created_at: datetime


class DeleteAccountIn(BaseModel):
    password: str | None = None
    google_reauth_token: str | None = None
    confirm: str
