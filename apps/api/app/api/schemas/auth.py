"""Auth contract (filled by CP-16). Session cookie `dp_session`."""

from pydantic import Field

from app.api.schemas.common import ApiModel


class LoginIn(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(ApiModel):
    id: str
    email: str
    display_name: str
