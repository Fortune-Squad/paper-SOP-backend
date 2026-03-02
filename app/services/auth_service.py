"""
Authentication service for user login and token management.
"""
from datetime import timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import LoginRequest, Token, TokenData
from app.services.user_service import UserService
from app.utils.security import create_access_token, decode_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
import logging

logger = logging.getLogger(__name__)


class AuthService:
    """Service class for authentication operations."""

    @staticmethod
    def login(db: Session, login_request: LoginRequest) -> Optional[tuple[str, dict]]:
        """
        Authenticate user and generate access token.

        Args:
            db: Database session
            login_request: LoginRequest with username and password

        Returns:
            Tuple of (access_token, user_dict) if successful, None otherwise
        """
        # Authenticate user
        user = UserService.authenticate_user(db, login_request.username, login_request.password)
        if not user:
            return None

        # Create access token
        access_token = AuthService.create_token_for_user(user.id, user.username, user.role)

        # Return token and user info
        user_dict = user.to_dict()
        return access_token, user_dict

    @staticmethod
    def create_token_for_user(user_id: int, username: str, role: str) -> str:
        """
        Create JWT access token for a user.

        Args:
            user_id: User ID
            username: Username
            role: User role

        Returns:
            JWT access token string
        """
        token_data = {
            "sub": str(user_id),  # Subject (user ID)
            "username": username,
            "role": role
        }

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(data=token_data, expires_delta=access_token_expires)

        logger.info(f"Access token created for user: {username} (id={user_id}, role={role})")
        return access_token

    @staticmethod
    def verify_token(token: str) -> Optional[TokenData]:
        """
        Verify and decode JWT access token.

        Args:
            token: JWT token string

        Returns:
            TokenData if valid, None otherwise
        """
        payload = decode_access_token(token)
        if not payload:
            return None

        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        role: str = payload.get("role")

        if user_id is None:
            return None

        return TokenData(user_id=user_id, username=username, role=role)

    @staticmethod
    def get_current_user_from_token(db: Session, token: str):
        """
        Get current user from JWT token.

        Args:
            db: Database session
            token: JWT token string

        Returns:
            User object if token is valid and user exists, None otherwise
        """
        token_data = AuthService.verify_token(token)
        if not token_data or not token_data.user_id:
            return None

        user = UserService.get_user_by_id(db, int(token_data.user_id))
        if not user or not user.is_active:
            return None

        return user
