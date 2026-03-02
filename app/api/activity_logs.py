"""
Activity logs API endpoints (Admin only).
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.database import get_db
from app.services.activity_log_service import ActivityLogService
from app.middleware.auth import require_admin
from app.db.models import User as DBUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity-logs", tags=["Activity Logs"])


@router.get("/")
async def get_activity_logs(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    username: Optional[str] = Query(None, description="Filter by username"),
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get activity logs (Admin only).

    Args:
        user_id: Filter by user ID
        username: Filter by username
        action: Filter by action
        resource_type: Filter by resource type
        status: Filter by status
        skip: Number of records to skip
        limit: Maximum number of records
        current_user: Current admin user
        db: Database session

    Returns:
        List of activity logs
    """
    try:
        logs = ActivityLogService.get_user_activities(
            db,
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            status=status,
            skip=skip,
            limit=limit
        )

        total = ActivityLogService.count_activities(
            db,
            user_id=user_id,
            action=action,
            status=status
        )

        return {
            "logs": [log.to_dict() for log in logs],
            "total": total,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        logger.error(f"Failed to get activity logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/stats")
async def get_activity_stats(
    start_date: Optional[datetime] = Query(None, description="Start date for statistics"),
    end_date: Optional[datetime] = Query(None, description="End date for statistics"),
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get activity statistics (Admin only).

    Args:
        start_date: Start date for statistics
        end_date: End date for statistics
        current_user: Current admin user
        db: Database session

    Returns:
        Activity statistics
    """
    try:
        stats = ActivityLogService.get_activity_stats(
            db,
            start_date=start_date,
            end_date=end_date
        )

        logger.info(f"Admin {current_user.username} retrieved activity stats")

        return stats

    except Exception as e:
        logger.error(f"Failed to get activity stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/login-attempts")
async def get_login_attempts(
    username: Optional[str] = Query(None, description="Filter by username"),
    ip_address: Optional[str] = Query(None, description="Filter by IP address"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get login attempts (Admin only).

    Args:
        username: Filter by username
        ip_address: Filter by IP address
        success: Filter by success status
        skip: Number of records to skip
        limit: Maximum number of records
        current_user: Current admin user
        db: Database session

    Returns:
        List of login attempts
    """
    try:
        from app.db.activity_models import LoginAttempt

        query = db.query(LoginAttempt)

        if username:
            query = query.filter(LoginAttempt.username == username)
        if ip_address:
            query = query.filter(LoginAttempt.ip_address == ip_address)
        if success is not None:
            query = query.filter(LoginAttempt.success == (1 if success else 0))

        total = query.count()
        attempts = query.order_by(LoginAttempt.created_at.desc()).offset(skip).limit(limit).all()

        logger.info(f"Admin {current_user.username} retrieved login attempts")

        return {
            "attempts": [attempt.to_dict() for attempt in attempts],
            "total": total,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        logger.error(f"Failed to get login attempts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
