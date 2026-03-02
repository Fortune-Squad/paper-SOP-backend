"""
Pydantic models for user authentication and management.
"""
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """Base user model with common fields."""
    username: str = Field(..., min_length=3, max_length=50, description="Username (3-50 characters)")
    email: Optional[EmailStr] = Field(None, description="Email address (optional)")


class UserCreate(UserBase):
    """Model for user registration."""
    password: str = Field(..., min_length=6, max_length=100, description="Password (min 6 characters)")

    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        """Validate username contains only alphanumeric characters and underscores."""
        if not v.replace('_', '').isalnum():
            raise ValueError('Username must contain only alphanumeric characters and underscores')
        return v


class UserUpdate(BaseModel):
    """Model for updating user information."""
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6, max_length=100)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None


class UserInDB(UserBase):
    """Model for user stored in database (includes hashed password)."""
    id: int
    hashed_password: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)


class User(UserBase):
    """Model for user in API responses (excludes password)."""
    id: int
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Model for JWT token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Model for decoded JWT token data."""
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None


class LoginRequest(BaseModel):
    """Model for login request."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)


class LoginResponse(BaseModel):
    """Model for login response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: User


class RefreshTokenRequest(BaseModel):
    """Model for refresh token request."""
    refresh_token: str = Field(..., description="Refresh token")


class RegisterResponse(BaseModel):
    """Model for registration response."""
    message: str
    user: User


class ForgotPasswordRequest(BaseModel):
    """Model for forgot password request."""
    email: EmailStr = Field(..., description="Email address")


class ForgotPasswordResponse(BaseModel):
    """Model for forgot password response."""
    message: str


class ResetPasswordRequest(BaseModel):
    """Model for reset password request."""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=6, max_length=100, description="New password (min 6 characters)")


class ResetPasswordResponse(BaseModel):
    """Model for reset password response."""
    message: str
