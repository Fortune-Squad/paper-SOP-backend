"""
Password Reset service for managing password reset tokens and flow.
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import secrets
import logging

from app.db.password_reset_models import PasswordResetToken
from app.db.models import User
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


class PasswordResetService:
    """Service for managing password reset flow."""

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_reset_token(
        db: Session,
        user_id: int,
        email: str,
        expires_hours: int = 1
    ) -> PasswordResetToken:
        """
        Create a password reset token.

        Args:
            db: Database session
            user_id: User ID
            email: User email
            expires_hours: Token expiration in hours (default: 1)

        Returns:
            PasswordResetToken: Created reset token
        """
        token = PasswordResetService.generate_token()
        expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

        reset_token = PasswordResetToken(
            user_id=user_id,
            token=token,
            email=email,
            expires_at=expires_at
        )

        db.add(reset_token)
        db.commit()
        db.refresh(reset_token)

        logger.info(f"Created password reset token for user {user_id}, expires at {expires_at}")
        return reset_token

    @staticmethod
    def get_reset_token(db: Session, token: str) -> Optional[PasswordResetToken]:
        """
        Get password reset token by token string.

        Args:
            db: Database session
            token: Token string

        Returns:
            PasswordResetToken or None
        """
        return db.query(PasswordResetToken).filter(
            PasswordResetToken.token == token
        ).first()

    @staticmethod
    def verify_reset_token(db: Session, token: str) -> Optional[User]:
        """
        Verify password reset token and return associated user.

        Args:
            db: Database session
            token: Token string

        Returns:
            User if token is valid, None otherwise
        """
        reset_token = PasswordResetService.get_reset_token(db, token)

        if not reset_token:
            logger.warning(f"Password reset token not found")
            return None

        if not reset_token.is_valid():
            logger.warning(f"Password reset token is invalid (used or expired)")
            return None

        # Get user
        user = db.query(User).filter(User.id == reset_token.user_id).first()

        if not user:
            logger.warning(f"User not found for password reset token")
            return None

        return user

    @staticmethod
    def use_reset_token(db: Session, token: str) -> bool:
        """
        Mark a password reset token as used.

        Args:
            db: Database session
            token: Token string

        Returns:
            bool: True if marked as used, False if not found
        """
        reset_token = PasswordResetService.get_reset_token(db, token)

        if not reset_token:
            logger.warning(f"Password reset token not found for marking as used")
            return False

        reset_token.mark_as_used()
        db.commit()

        logger.info(f"Marked password reset token as used for user {reset_token.user_id}")
        return True

    @staticmethod
    def cleanup_expired_tokens(db: Session) -> int:
        """
        Delete expired password reset tokens from database.

        Args:
            db: Database session

        Returns:
            int: Number of tokens deleted
        """
        expired_tokens = db.query(PasswordResetToken).filter(
            PasswordResetToken.expires_at < datetime.utcnow()
        ).all()

        count = len(expired_tokens)
        for token in expired_tokens:
            db.delete(token)

        db.commit()

        logger.info(f"Cleaned up {count} expired password reset tokens")
        return count

    @staticmethod
    def request_password_reset(
        db: Session,
        email: str,
        frontend_url: str = "http://localhost:5173"
    ) -> bool:
        """
        Request password reset for a user by email.

        Args:
            db: Database session
            email: User email
            frontend_url: Frontend base URL

        Returns:
            bool: True if reset email sent, False otherwise
        """
        # Find user by email
        user = db.query(User).filter(User.email == email).first()

        if not user:
            logger.warning(f"Password reset requested for non-existent email: {email}")
            # Don't reveal if email exists or not (security)
            return True

        if not user.is_active:
            logger.warning(f"Password reset requested for inactive user: {email}")
            # Don't reveal if user is inactive (security)
            return True

        # Create reset token
        reset_token = PasswordResetService.create_reset_token(
            db, user.id, email
        )

        # Send reset email
        success = email_service.send_password_reset_email(
            to_email=email,
            username=user.username,
            reset_token=reset_token.token,
            frontend_url=frontend_url
        )

        if success:
            logger.info(f"Password reset email sent to {email}")
        else:
            logger.error(f"Failed to send password reset email to {email}")

        return success

    @staticmethod
    def reset_password(
        db: Session,
        token: str,
        new_password: str
    ) -> bool:
        """
        Reset user password using reset token.

        Args:
            db: Database session
            token: Reset token
            new_password: New password (plain text, will be hashed)

        Returns:
            bool: True if password reset successfully, False otherwise
        """
        # Verify token
        user = PasswordResetService.verify_reset_token(db, token)

        if not user:
            logger.warning(f"Invalid or expired password reset token")
            return False

        # Hash new password
        from app.services.auth_service import AuthService
        hashed_password = AuthService.hash_password(new_password)

        # Update user password
        user.hashed_password = hashed_password
        db.commit()

        # Mark token as used
        PasswordResetService.use_reset_token(db, token)

        # Revoke all refresh tokens for this user (force re-login)
        try:
            from app.services.refresh_token_service import RefreshTokenService
            RefreshTokenService.revoke_all_user_tokens(db, user.id)
            logger.info(f"Revoked all refresh tokens for user {user.username} after password reset")
        except Exception as e:
            logger.warning(f"Failed to revoke refresh tokens after password reset: {e}")

        logger.info(f"Password reset successfully for user {user.username}")
        return True
