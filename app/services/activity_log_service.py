"""
Activity logging service for audit trail.
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.db.activity_models import UserActivityLog, LoginAttempt
import logging

logger = logging.getLogger(__name__)


class ActivityLogService:
    """Service for logging user activities."""

    @staticmethod
    def log_activity(
        db: Session,
        user_id: int,
        username: str,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> UserActivityLog:
        """
        Log a user activity.

        Args:
            db: Database session
            user_id: User ID
            username: Username
            action: Action performed (login, create_project, etc.)
            resource_type: Type of resource (project, document, user, etc.)
            resource_id: ID of the resource
            ip_address: IP address of the user
            user_agent: User agent string
            details: Additional details as dictionary
            status: Status of the action (success, failure, error)
            error_message: Error message if status is failure or error

        Returns:
            Created activity log
        """
        try:
            log = UserActivityLog(
                user_id=user_id,
                username=username,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
                status=status,
                error_message=error_message
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
            db.rollback()
            raise

    @staticmethod
    def get_user_activities(
        db: Session,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[UserActivityLog]:
        """
        Get user activities with filters.

        Args:
            db: Database session
            user_id: Filter by user ID
            username: Filter by username
            action: Filter by action
            resource_type: Filter by resource type
            status: Filter by status
            start_date: Filter by start date
            end_date: Filter by end date
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of activity logs
        """
        query = db.query(UserActivityLog)

        if user_id:
            query = query.filter(UserActivityLog.user_id == user_id)
        if username:
            query = query.filter(UserActivityLog.username == username)
        if action:
            query = query.filter(UserActivityLog.action == action)
        if resource_type:
            query = query.filter(UserActivityLog.resource_type == resource_type)
        if status:
            query = query.filter(UserActivityLog.status == status)
        if start_date:
            query = query.filter(UserActivityLog.created_at >= start_date)
        if end_date:
            query = query.filter(UserActivityLog.created_at <= end_date)

        return query.order_by(UserActivityLog.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def count_activities(
        db: Session,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """Count activities with filters."""
        query = db.query(UserActivityLog)

        if user_id:
            query = query.filter(UserActivityLog.user_id == user_id)
        if action:
            query = query.filter(UserActivityLog.action == action)
        if status:
            query = query.filter(UserActivityLog.status == status)
        if start_date:
            query = query.filter(UserActivityLog.created_at >= start_date)
        if end_date:
            query = query.filter(UserActivityLog.created_at <= end_date)

        return query.count()

    @staticmethod
    def log_login_attempt(
        db: Session,
        username: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        success: bool = False,
        failure_reason: Optional[str] = None
    ) -> LoginAttempt:
        """
        Log a login attempt.

        Args:
            db: Database session
            username: Username
            ip_address: IP address
            user_agent: User agent string
            success: Whether login was successful
            failure_reason: Reason for failure

        Returns:
            Created login attempt log
        """
        try:
            attempt = LoginAttempt(
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                success=1 if success else 0,
                failure_reason=failure_reason
            )
            db.add(attempt)
            db.commit()
            db.refresh(attempt)
            return attempt
        except Exception as e:
            logger.error(f"Failed to log login attempt: {e}")
            db.rollback()
            raise

    @staticmethod
    def get_failed_login_attempts(
        db: Session,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        minutes: int = 15
    ) -> int:
        """
        Get count of failed login attempts in the last N minutes.

        Args:
            db: Database session
            username: Filter by username
            ip_address: Filter by IP address
            minutes: Time window in minutes

        Returns:
            Count of failed attempts
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        query = db.query(LoginAttempt).filter(
            LoginAttempt.success == 0,
            LoginAttempt.created_at >= cutoff_time
        )

        if username:
            query = query.filter(LoginAttempt.username == username)
        if ip_address:
            query = query.filter(LoginAttempt.ip_address == ip_address)

        return query.count()

    @staticmethod
    def is_ip_blocked(db: Session, ip_address: str, max_attempts: int = 5, minutes: int = 15) -> bool:
        """
        Check if an IP address is blocked due to too many failed attempts.

        Args:
            db: Database session
            ip_address: IP address to check
            max_attempts: Maximum allowed failed attempts
            minutes: Time window in minutes

        Returns:
            True if IP is blocked, False otherwise
        """
        failed_attempts = ActivityLogService.get_failed_login_attempts(
            db, ip_address=ip_address, minutes=minutes
        )
        return failed_attempts >= max_attempts

    @staticmethod
    def is_user_blocked(db: Session, username: str, max_attempts: int = 5, minutes: int = 15) -> bool:
        """
        Check if a user is blocked due to too many failed attempts.

        Args:
            db: Database session
            username: Username to check
            max_attempts: Maximum allowed failed attempts
            minutes: Time window in minutes

        Returns:
            True if user is blocked, False otherwise
        """
        failed_attempts = ActivityLogService.get_failed_login_attempts(
            db, username=username, minutes=minutes
        )
        return failed_attempts >= max_attempts

    @staticmethod
    def get_activity_stats(
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get activity statistics.

        Args:
            db: Database session
            start_date: Start date for statistics
            end_date: End date for statistics

        Returns:
            Dictionary with statistics
        """
        query = db.query(UserActivityLog)

        if start_date:
            query = query.filter(UserActivityLog.created_at >= start_date)
        if end_date:
            query = query.filter(UserActivityLog.created_at <= end_date)

        total_activities = query.count()
        successful_activities = query.filter(UserActivityLog.status == "success").count()
        failed_activities = query.filter(UserActivityLog.status == "failure").count()
        error_activities = query.filter(UserActivityLog.status == "error").count()

        # Count by action type
        from sqlalchemy import func
        action_counts = db.query(
            UserActivityLog.action,
            func.count(UserActivityLog.id).label('count')
        ).group_by(UserActivityLog.action).all()

        return {
            "total_activities": total_activities,
            "successful_activities": successful_activities,
            "failed_activities": failed_activities,
            "error_activities": error_activities,
            "action_counts": {action: count for action, count in action_counts},
            # 前端兼容字段
            "by_action": {action: count for action, count in action_counts},
            "by_status": {
                "success": successful_activities,
                "failure": failed_activities,
                "error": error_activities
            },
            "by_user": {},
            "recent_activities": []
        }
