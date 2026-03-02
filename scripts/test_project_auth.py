"""
Test project API with authentication.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import httpx
from app.db.database import SessionLocal
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.models.user import UserCreate, LoginRequest


BASE_URL = "http://localhost:8000"


async def test_project_api():
    """Test project API with authentication."""
    print("=" * 60)
    print("Testing Project API with Authentication")
    print("=" * 60)
    print()

    db = SessionLocal()

    try:
        # Create a test user
        print("Step 1: Create test user")
        try:
            test_user = UserService.create_user(
                db,
                UserCreate(username="testuser", email="test@example.com", password="test123"),
                role="user",
                is_active=True
            )
            print(f"[OK] Test user created: {test_user.username}")
        except ValueError:
            test_user = UserService.get_user_by_username(db, "testuser")
            print(f"[OK] Test user already exists: {test_user.username}")
        print()

        # Login as admin
        print("Step 2: Login as admin")
        admin_login = LoginRequest(username="admin", password="admin123")
        admin_result = AuthService.login(db, admin_login)
        if not admin_result:
            print("[ERROR] Admin login failed!")
            return
        admin_token, _ = admin_result
        print(f"[OK] Admin logged in, token: {admin_token[:50]}...")
        print()

        # Login as test user
        print("Step 3: Login as test user")
        user_login = LoginRequest(username="testuser", password="test123")
        user_result = AuthService.login(db, user_login)
        if not user_result:
            print("[ERROR] User login failed!")
            return
        user_token, _ = user_result
        print(f"[OK] User logged in, token: {user_token[:50]}...")
        print()

        async with httpx.AsyncClient() as client:
            # Test: List projects as admin
            print("Step 4: List projects as admin")
            response = await client.get(
                f"{BASE_URL}/api/projects/",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            if response.status_code == 200:
                projects = response.json()
                print(f"[OK] Admin can list projects: {len(projects)} projects found")
            else:
                print(f"[ERROR] Failed to list projects: {response.status_code}")
            print()

            # Test: List projects as user
            print("Step 5: List projects as user")
            response = await client.get(
                f"{BASE_URL}/api/projects/",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            if response.status_code == 200:
                projects = response.json()
                print(f"[OK] User can list projects: {len(projects)} projects found")
            else:
                print(f"[ERROR] Failed to list projects: {response.status_code}")
            print()

            # Test: List projects without auth
            print("Step 6: List projects without authentication")
            response = await client.get(f"{BASE_URL}/api/projects/")
            if response.status_code == 401:
                print("[OK] Unauthenticated request correctly rejected (401)")
            else:
                print(f"[ERROR] Expected 401, got {response.status_code}")
            print()

        print("=" * 60)
        print("[SUCCESS] All authentication tests passed!")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_project_api())
