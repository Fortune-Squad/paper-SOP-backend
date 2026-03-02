"""
User service for CRUD operations on users.
"""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.db.models import User as DBUser
from app.models.user import UserCreate, UserUpdate
from app.utils.security import get_password_hash, verify_password
import logging

logger = logging.getLogger(__name__)


class UserService:
    """Service class for user management operations."""

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[DBUser]:
        """Get user by ID."""
        return db.query(DBUser).filter(DBUser.id == user_id).first()

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[DBUser]:
        """Get user by username."""
        return db.query(DBUser).filter(DBUser.username == username).first()

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[DBUser]:
        """Get user by email."""
        if not email:
            return None
        return db.query(DBUser).filter(DBUser.email == email).first()

    @staticmethod
    def get_users(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        role: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[DBUser]:
        """
        Get list of users with optional filters.

        Args:
            db: Database session
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            role: Filter by role ('admin' or 'user')
            is_active: Filter by activation status

        Returns:
            List of User objects
        """
        query = db.query(DBUser)

        if role:
            query = query.filter(DBUser.role == role)
        if is_active is not None:
            query = query.filter(DBUser.is_active == is_active)

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def create_user(db: Session, user: UserCreate, role: str = "user", is_active: bool = False) -> DBUser:
        """
        Create a new user.

        Args:
            db: Database session
            user: UserCreate model with username, email, password
            role: User role ('admin' or 'user'), default 'user'
            is_active: Account activation status, default False (requires admin approval)

        Returns:
            Created User object

        Raises:
            ValueError: If username or email already exists
        """
        # Check if username exists
        if UserService.get_user_by_username(db, user.username):
            raise ValueError(f"Username '{user.username}' already exists")

        # Check if email exists (if provided)
        if user.email and UserService.get_user_by_email(db, user.email):
            raise ValueError(f"Email '{user.email}' already exists")

        # Hash password
        hashed_password = get_password_hash(user.password)

        # Create user
        db_user = DBUser(
            username=user.username,
            email=user.email,
            hashed_password=hashed_password,
            role=role,
            is_active=is_active
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        logger.info(f"User created: {user.username} (role={role}, is_active={is_active})")
        return db_user

    @staticmethod
    def update_user(db: Session, user_id: int, user_update: UserUpdate) -> Optional[DBUser]:
        """
        Update user information.

        Args:
            db: Database session
            user_id: User ID
            user_update: UserUpdate model with fields to update

        Returns:
            Updated User object, or None if user not found
        """
        db_user = UserService.get_user_by_id(db, user_id)
        if not db_user:
            return None

        # Update fields if provided
        update_data = user_update.model_dump(exclude_unset=True)

        if "password" in update_data:
            # Hash new password
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

        for field, value in update_data.items():
            setattr(db_user, field, value)

        db.commit()
        db.refresh(db_user)

        logger.info(f"User updated: {db_user.username} (id={user_id})")
        return db_user

    @staticmethod
    def delete_user(db: Session, user_id: int) -> bool:
        """
        Delete a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            True if deleted, False if user not found
        """
        db_user = UserService.get_user_by_id(db, user_id)
        if not db_user:
            return False

        username = db_user.username
        db.delete(db_user)
        db.commit()

        logger.info(f"User deleted: {username} (id={user_id})")
        return True

    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[DBUser]:
        """
        Authenticate user with username and password.

        Args:
            db: Database session
            username: Username
            password: Plain text password

        Returns:
            User object if authentication successful, None otherwise
        """
        user = UserService.get_user_by_username(db, username)
        if not user:
            logger.warning(f"Authentication failed: User '{username}' not found")
            return None

        if not verify_password(password, user.hashed_password):
            logger.warning(f"Authentication failed: Invalid password for user '{username}'")
            return None

        if not user.is_active:
            logger.warning(f"Authentication failed: User '{username}' is not active")
            return None

        logger.info(f"User authenticated: {username}")
        return user

    @staticmethod
    def activate_user(db: Session, user_id: int) -> Optional[DBUser]:
        """
        Activate a user account (admin approval).

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Updated User object, or None if user not found
        """
        db_user = UserService.get_user_by_id(db, user_id)
        if not db_user:
            return None

        db_user.is_active = True
        db.commit()
        db.refresh(db_user)

        logger.info(f"User activated: {db_user.username} (id={user_id})")
        return db_user

    @staticmethod
    def deactivate_user(db: Session, user_id: int) -> Optional[DBUser]:
        """
        Deactivate a user account.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Updated User object, or None if user not found
        """
        db_user = UserService.get_user_by_id(db, user_id)
        if not db_user:
            return None

        db_user.is_active = False
        db.commit()
        db.refresh(db_user)

        logger.info(f"User deactivated: {db_user.username} (id={user_id})")
        return db_user

    @staticmethod
    def count_users(db: Session, role: Optional[str] = None, is_active: Optional[bool] = None) -> int:
        """
        Count users with optional filters.

        Args:
            db: Database session
            role: Filter by role
            is_active: Filter by activation status

        Returns:
            Number of users matching filters
        """
        query = db.query(DBUser)

        if role:
            query = query.filter(DBUser.role == role)
        if is_active is not None:
            query = query.filter(DBUser.is_active == is_active)

        return query.count()
