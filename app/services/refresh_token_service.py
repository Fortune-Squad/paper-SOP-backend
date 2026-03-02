"""
Refresh Token service for managing long-term authentication tokens.
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import secrets
import logging

from app.db.refresh_token_models import RefreshToken
from app.db.models import User

logger = logging.getLogger(__name__)


class RefreshTokenService:
    """Service for managing refresh tokens."""

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(64)

    @staticmethod
    def create_refresh_token(
        db: Session,
        user_id: int,
        expires_days: int = 7
    ) -> RefreshToken:
        """
        Create a new refresh token for a user.

        Args:
            db: Database session
            user_id: User ID
            expires_days: Token expiration in days (default: 7)

        Returns:
            RefreshToken: Created refresh token
        """
        token = RefreshTokenService.generate_token()
        expires_at = datetime.utcnow() + timedelta(days=expires_days)

        refresh_token = RefreshToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )

        db.add(refresh_token)
        db.commit()
        db.refresh(refresh_token)

        logger.info(f"Created refresh token for user {user_id}, expires at {expires_at}")
        return refresh_token

    @staticmethod
    def get_refresh_token(db: Session, token: str) -> Optional[RefreshToken]:
        """
        Get refresh token by token string.

        Args:
            db: Database session
            token: Token string

        Returns:
            RefreshToken or None
        """
        return db.query(RefreshToken).filter(
            RefreshToken.token == token
        ).first()

    @staticmethod
    def verify_refresh_token(db: Session, token: str) -> Optional[User]:
        """
        Verify refresh token and return associated user.

        Args:
            db: Database session
            token: Token string

        Returns:
            User if token is valid, None otherwise
        """
        refresh_token = RefreshTokenService.get_refresh_token(db, token)

        if not refresh_token:
            logger.warning(f"Refresh token not found")
            return None

        if not refresh_token.is_valid():
            logger.warning(f"Refresh token is invalid (revoked or expired)")
            return None

        # Get user
        user = db.query(User).filter(User.id == refresh_token.user_id).first()

        if not user or not user.is_active:
            logger.warning(f"User not found or inactive for refresh token")
            return None

        return user

    @staticmethod
    def revoke_refresh_token(db: Session, token: str) -> bool:
        """
        Revoke a refresh token.

        Args:
            db: Database session
            token: Token string

        Returns:
            bool: True if revoked, False if not found
        """
        refresh_token = RefreshTokenService.get_refresh_token(db, token)

        if not refresh_token:
            logger.warning(f"Refresh token not found for revocation")
            return False

        refresh_token.revoke()
        db.commit()

        logger.info(f"Revoked refresh token for user {refresh_token.user_id}")
        return True

    @staticmethod
    def revoke_all_user_tokens(db: Session, user_id: int) -> int:
        """
        Revoke all refresh tokens for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            int: Number of tokens revoked
        """
        tokens = db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False
        ).all()

        count = 0
        for token in tokens:
            token.revoke()
            count += 1

        db.commit()

        logger.info(f"Revoked {count} refresh tokens for user {user_id}")
        return count

    @staticmethod
    def cleanup_expired_tokens(db: Session) -> int:
        """
        Delete expired refresh tokens from database.

        Args:
            db: Database session

        Returns:
            int: Number of tokens deleted
        """
        expired_tokens = db.query(RefreshToken).filter(
            RefreshToken.expires_at < datetime.utcnow()
        ).all()

        count = len(expired_tokens)
        for token in expired_tokens:
            db.delete(token)

        db.commit()

        logger.info(f"Cleaned up {count} expired refresh tokens")
        return count

    @staticmethod
    def get_user_tokens(db: Session, user_id: int) -> list[RefreshToken]:
        """
        Get all refresh tokens for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            list[RefreshToken]: List of refresh tokens
        """
        return db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id
        ).order_by(RefreshToken.created_at.desc()).all()
