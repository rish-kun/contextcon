"""Auth contract (filled by CP-16). Session cookie `dp_session`."""

from typing import Literal

from pydantic import Field

from app.api.schemas.common import ApiModel


class LoginIn(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class SignupIn(ApiModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    # Names the new workspace. Empty: "<display name>'s workspace".
    organisation: str = Field(default="", max_length=200)
    # Honeypot: a hidden field a person never fills. When set, nothing is created.
    company_url: str = Field(default="", max_length=500)


class VerificationSentOut(ApiModel):
    """The same answer whether or not the email has an account, so it reveals nothing."""

    status: Literal["verification_sent"] = "verification_sent"
    email: str


class VerifyIn(ApiModel):
    token: str = Field(min_length=1, max_length=200)


class ResendVerificationIn(ApiModel):
    email: str = Field(min_length=3, max_length=320)


class UserOut(ApiModel):
    id: str
    email: str
    display_name: str
