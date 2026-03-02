"""
Create an admin user account.
Can be run from command line or imported as a module.
"""
import sys
from pathlib import Path
import os
from getpass import getpass

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import SessionLocal, init_db
# Import all models first to avoid circular dependency issues
from app.db.models import User
from app.db.refresh_token_models import RefreshToken
from app.db.activity_models import UserActivityLog, LoginAttempt
from app.db.password_reset_models import PasswordResetToken
# Now import the service and pydantic models
from app.models.user import UserCreate
from app.services.user_service import UserService


def create_admin_user(username: str, password: str, email: str = None) -> bool:
    """
    Create an admin user.

    Args:
        username: Admin username
        password: Admin password
        email: Admin email (optional)

    Returns:
        True if successful, False otherwise
    """
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = UserService.get_user_by_username(db, username)
        if existing_user:
            print(f"[ERROR] User '{username}' already exists!")
            return False

        # Create admin user
        user_create = UserCreate(
            username=username,
            email=email,
            password=password
        )

        admin_user = UserService.create_user(
            db,
            user_create,
            role="admin",
            is_active=True  # Admin is active by default
        )

        print(f"[OK] Admin user created successfully!")
        print(f"   Username: {admin_user.username}")
        print(f"   Email: {admin_user.email or 'N/A'}")
        print(f"   Role: {admin_user.role}")
        print(f"   Active: {admin_user.is_active}")

        return True

    except Exception as e:
        print(f"[ERROR] Error creating admin user: {str(e)}")
        return False

    finally:
        db.close()


def main():
    """Interactive admin user creation."""
    print("=" * 60)
    print("Create Admin User")
    print("=" * 60)
    print()

    # Check if database exists
    from app.db.database import DATABASE_PATH
    db_path = Path(DATABASE_PATH) if DATABASE_PATH else None
    if db_path and not db_path.exists():
        print("[WARNING] Database not found. Initializing database...")
        init_db()
        print()

    # Get admin credentials from environment variables or user input
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    email = os.getenv("ADMIN_EMAIL")

    if username and password:
        print("Using credentials from environment variables...")
        print(f"Username: {username}")
        print(f"Email: {email or 'N/A'}")
        print()
    else:
        print("Enter admin credentials:")
        username = input("Username: ").strip()
        email = input("Email (optional): ").strip() or None
        password = getpass("Password: ")
        password_confirm = getpass("Confirm password: ")

        if password != password_confirm:
            print("[ERROR] Passwords do not match!")
            return

        print()

    # Validate input
    if not username or len(username) < 3:
        print("[ERROR] Username must be at least 3 characters!")
        return

    if not password or len(password) < 6:
        print("[ERROR] Password must be at least 6 characters!")
        return

    # Create admin user
    success = create_admin_user(username, password, email)

    if success:
        print()
        print("=" * 60)
        print("[SUCCESS] Admin user creation complete!")
        print("=" * 60)
        print()
        print("You can now:")
        print("1. Start the application: uvicorn app.main:app --reload")
        print(f"2. Login with username: {username}")


if __name__ == "__main__":
    main()
