import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str

    model_config = {"from_attributes": True}


class InterestResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    bio: str | None = Field(default=None, max_length=500)
    age: int | None = Field(default=None, ge=18, le=120)
    gender: Literal["male", "female", "other"] | None = None
    seeking: Literal["male", "female", "everyone"] | None = None
    age_min: int | None = Field(default=None, ge=18, le=120)
    age_max: int | None = Field(default=None, ge=18, le=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    interests: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_age_range(self) -> "ProfileUpdateRequest":
        if (
            self.age_min is not None
            and self.age_max is not None
            and self.age_min > self.age_max
        ):
            raise ValueError("age_min must be <= age_max")
        return self


class ProfileResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    bio: str | None
    age: int | None
    gender: str | None
    seeking: str | None
    age_min: int | None
    age_max: int | None
    photo_url: str | None
    interests: list[str]
    has_location: bool

    model_config = {"from_attributes": True}


class PhotoResponse(BaseModel):
    photo_url: str
