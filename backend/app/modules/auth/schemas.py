from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

# Username dinormalisasi ke huruf kecil supaya "Bagas" dan "bagas" adalah akun yang sama.
Username = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=50)
]
# Batas atas mencegah request raksasa membebani scrypt.
Password = Annotated[str, StringConstraints(min_length=1, max_length=256)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    full_name: str
    resource_id: str | None
    last_login_at: datetime | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead
