"""
Seed initial admin users in a non-interactive way.

This script is safe to run multiple times: it will skip users that already exist.
It is intended to be used in deployment/entrypoint scripts after migrations.
"""
import sys
from pathlib import Path
from typing import List, TypedDict

# Ensure project root is on sys.path so `app` can be imported when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import SessionLocal  # type: ignore

# Import all ORM models that are referenced via string-based relationships
# so that SQLAlchemy's mapper configuration can resolve them correctly.
from app.db.models import User  # type: ignore  # noqa: F401
from app.db.refresh_token_models import RefreshToken  # type: ignore  # noqa: F401
from app.db.activity_models import UserActivityLog, LoginAttempt  # type: ignore  # noqa: F401
from app.db.password_reset_models import PasswordResetToken  # type: ignore  # noqa: F401

from app.services.user_service import UserService  # type: ignore
from app.models.user import UserCreate  # type: ignore


class AdminSpec(TypedDict):
    username: str
    password: str
    email: str


ADMIN_USERS: List[AdminSpec] = [
    {
        "username": "zyhadmin",
        "password": "Zhangyh0305!",
        "email": "alex_zhang1994@outlook.jp",
    },
    {
        "username": "qyfadmin",
        "password": "Qinyf0305!",
        "email": "ee06b147@gmail.com",
    },
    {
        "username": "cjadmin",
        "password": "Chenj0305!",
        "email": "chenj12@pcl.ac.cn",
    },
    {
        "username": "pzcadmin",
        "password": "Pangzc0305!",
        "email": "pangzch@pcl.ac.cn",
    },
]


def seed_admin_users() -> None:
    db = SessionLocal()
    try:
        for spec in ADMIN_USERS:
            username = spec["username"]
            existing = UserService.get_user_by_username(db, username)
            if existing:
                print(f"[SKIP] User '{username}' already exists")
                continue

            user_create = UserCreate(
                username=username,
                email=spec["email"],
                password=spec["password"],
            )

            user = UserService.create_user(
                db,
                user_create,
                role="admin",
                is_active=True,
            )

            print(f"[OK] Seeded admin user '{user.username}' ({user.email or 'N/A'})")
    finally:
        db.close()


def main() -> None:
    print("=" * 60)
    print("Seeding admin users")
    print("=" * 60)
    seed_admin_users()
    print("=" * 60)
    print("Seeding complete")
    print("=" * 60)


if __name__ == "__main__":
    main()

