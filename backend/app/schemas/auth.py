"""
Auth API schemas — signup/login request bodies and the responses.

Validation happens HERE, at the border: a bad email or phone is rejected with
422 before any business logic runs. EmailStr checks the address; a field
validator normalizes the phone to 2547XXXXXXXX (or rejects it).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils import normalize_kenyan_phone


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(description="Kenyan mobile, any format — normalized to 2547…")
    # Min 8 per NIST guidance (length beats forced complexity). Max 128 so a
    # giant input can't be used to burn CPU in the hasher.
    password: str = Field(min_length=8, max_length=128)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, v: str) -> str:
        try:
            return normalize_kenyan_phone(v)
        except ValueError as e:
            # Re-raised as a pydantic validation error → HTTP 422 with this text.
            raise ValueError(str(e)) from e


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    """What signup and login return. `bearer` tells the client to send it as
    `Authorization: Bearer <token>`."""

    access_token: str
    token_type: str = "bearer"


class AccountOut(BaseModel):
    """The logged-in account's own view. NOTE what's absent: password_hash.
    A response schema is a whitelist — the hash has no field here, so it can
    never be serialized out, even by accident."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    phone: str
    created_at: datetime
