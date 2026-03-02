"""
User activity log model for audit trail.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.db.database import Base


class UserActivityLog(Base):
    """
    User activity log for audit trail.

    Tracks all user actions including:
    - Login/logout
    - Project creation/deletion
    - Step execution
    - Document access
    - Configuration changes
    """
    __tablename__ = "user_activity_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    username = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)  # login, create_project, execute_step, etc.
    resource_type = Column(String(50), nullable=True)  # project, document, user, etc.
    resource_id = Column(String(255), nullable=True)  # project_id, document_id, etc.
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)
    details = Column(JSON, nullable=True)  # Additional details as JSON
    status = Column(String(20), nullable=False, default="success")  # success, failure, error
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<UserActivityLog(id={self.id}, user={self.username}, action={self.action}, status={self.status})>"

    def to_dict(self):
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": self.details,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LoginAttempt(Base):
    """
    Login attempt tracking for security.

    Tracks failed login attempts to prevent brute force attacks.
    """
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    user_agent = Column(String(500), nullable=True)
    success = Column(Integer, nullable=False, default=0)  # 0 = failure, 1 = success
    failure_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<LoginAttempt(id={self.id}, username={self.username}, ip={self.ip_address}, success={self.success})>"

    def to_dict(self):
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "username": self.username,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": bool(self.success),
            "failure_reason": self.failure_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
