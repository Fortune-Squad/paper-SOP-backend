"""
User management API endpoints (Admin only).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.models.user import User, UserUpdate
from app.services.user_service import UserService
from app.middleware.auth import require_admin
from app.db.models import User as DBUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["User Management"])


@router.get("/")
async def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    role: Optional[str] = Query(None, pattern="^(admin|user)$", description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by activation status"),
    search: Optional[str] = Query(None, description="Search by username or email"),
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all users (Admin only).

    Args:
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        role: Filter by role ('admin' or 'user')
        is_active: Filter by activation status
        search: Search by username or email
        current_user: Current admin user
        db: Database session

    Returns:
        User list with pagination info
    """
    # Get users with filters
    users = UserService.get_users(db, skip=skip, limit=limit, role=role, is_active=is_active)

    # Apply search filter if provided
    if search:
        search_lower = search.lower()
        users = [u for u in users if search_lower in u.username.lower() or (u.email and search_lower in u.email.lower())]

    # Get total count with same filters
    total = UserService.count_users(db, role=role, is_active=is_active)

    logger.info(f"Admin {current_user.username} listed users (count={len(users)}, total={total})")

    return {
        "users": [User.model_validate(user) for user in users],
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/stats")
async def get_user_stats(
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get user statistics (Admin only).

    Args:
        current_user: Current admin user
        db: Database session

    Returns:
        User statistics
    """
    total_users = UserService.count_users(db)
    active_users = UserService.count_users(db, is_active=True)
    pending_users = UserService.count_users(db, is_active=False)
    admin_users = UserService.count_users(db, role="admin")
    regular_users = UserService.count_users(db, role="user")

    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": pending_users,  # Frontend expects 'inactive_users'
        "admin_users": admin_users,
        "regular_users": regular_users
    }


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: int,
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get user by ID (Admin only).

    Args:
        user_id: User ID
        current_user: Current admin user
        db: Database session

    Returns:
        User info

    Raises:
        HTTPException: 404 if user not found
    """
    user = UserService.get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    return User.model_validate(user)


@router.put("/{user_id}", response_model=User)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update user information (Admin only).

    Args:
        user_id: User ID
        user_update: Fields to update
        current_user: Current admin user
        db: Database session

    Returns:
        Updated user info

    Raises:
        HTTPException: 404 if user not found
    """
    updated_user = UserService.update_user(db, user_id, user_update)

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    logger.info(f"Admin {current_user.username} updated user {updated_user.username} (id={user_id})")

    return User.model_validate(updated_user)


@router.post("/{user_id}/activate", response_model=User)
async def activate_user(
    user_id: int,
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Activate a user account (Admin only).

    Args:
        user_id: User ID
        current_user: Current admin user
        db: Database session

    Returns:
        Updated user info

    Raises:
        HTTPException: 404 if user not found
    """
    activated_user = UserService.activate_user(db, user_id)

    if not activated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    logger.info(f"Admin {current_user.username} activated user {activated_user.username} (id={user_id})")

    return User.model_validate(activated_user)


@router.post("/{user_id}/deactivate", response_model=User)
async def deactivate_user(
    user_id: int,
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Deactivate a user account (Admin only).

    Args:
        user_id: User ID
        current_user: Current admin user
        db: Database session

    Returns:
        Updated user info

    Raises:
        HTTPException: 404 if user not found, 400 if trying to deactivate self
    """
    # Prevent admin from deactivating themselves
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )

    deactivated_user = UserService.deactivate_user(db, user_id)

    if not deactivated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    logger.info(f"Admin {current_user.username} deactivated user {deactivated_user.username} (id={user_id})")

    return User.model_validate(deactivated_user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: DBUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a user (Admin only).

    Args:
        user_id: User ID
        current_user: Current admin user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: 404 if user not found, 400 if trying to delete self
    """
    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    # Get user info before deletion
    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    username = user.username

    # Delete user
    success = UserService.delete_user(db, user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    logger.info(f"Admin {current_user.username} deleted user {username} (id={user_id})")

    return {
        "message": f"User '{username}' deleted successfully",
        "user_id": user_id
    }
