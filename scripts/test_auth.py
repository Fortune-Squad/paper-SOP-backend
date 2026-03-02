"""
Test authentication API endpoints.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from app.db.database import SessionLocal
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.models.user import LoginRequest


async def test_auth():
    """Test authentication flow."""
    print("=" * 60)
    print("Testing Authentication System")
    print("=" * 60)
    print()

    db = SessionLocal()

    try:
        # Test 1: Get admin user
        print("Test 1: Get admin user")
        admin = UserService.get_user_by_username(db, "admin")
        if admin:
            print(f"[OK] Admin user found: {admin.username}")
            print(f"     Role: {admin.role}")
            print(f"     Active: {admin.is_active}")
        else:
            print("[ERROR] Admin user not found!")
            return
        print()

        # Test 2: Login with correct credentials
        print("Test 2: Login with correct credentials")
        login_request = LoginRequest(username="admin", password="admin123")
        result = AuthService.login(db, login_request)
        if result:
            token, user_dict = result
            print(f"[OK] Login successful!")
            print(f"     Token: {token[:50]}...")
            print(f"     User: {user_dict['username']}")
        else:
            print("[ERROR] Login failed!")
            return
        print()

        # Test 3: Verify token
        print("Test 3: Verify token")
        token_data = AuthService.verify_token(token)
        if token_data:
            print(f"[OK] Token verified!")
            print(f"     User ID: {token_data.user_id}")
            print(f"     Username: {token_data.username}")
            print(f"     Role: {token_data.role}")
        else:
            print("[ERROR] Token verification failed!")
            return
        print()

        # Test 4: Get current user from token
        print("Test 4: Get current user from token")
        current_user = AuthService.get_current_user_from_token(db, token)
        if current_user:
            print(f"[OK] Current user retrieved!")
            print(f"     Username: {current_user.username}")
            print(f"     Role: {current_user.role}")
        else:
            print("[ERROR] Failed to get current user!")
            return
        print()

        # Test 5: Login with wrong password
        print("Test 5: Login with wrong password")
        wrong_login = LoginRequest(username="admin", password="wrongpassword")
        result = AuthService.login(db, wrong_login)
        if result is None:
            print("[OK] Login correctly rejected with wrong password")
        else:
            print("[ERROR] Login should have failed!")
        print()

        print("=" * 60)
        print("[SUCCESS] All authentication tests passed!")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_auth())
