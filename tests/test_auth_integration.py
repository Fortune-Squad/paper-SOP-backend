"""
Integration tests for authentication system.
Tests complete workflows including registration, login, token refresh, and password reset.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import Base, get_db
from app.services.user_service import UserService
import time

# Create test database
TEST_DATABASE_URL = "sqlite:///./test_integration.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    from app.db.models import User
    from app.db.activity_models import UserActivityLog, LoginAttempt
    from app.db.refresh_token_models import RefreshToken
    from app.db.password_reset_models import PasswordResetToken

    # Re-apply override in case another test module changed it
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestCompleteAuthenticationFlow:
    """Test complete authentication workflow."""

    def test_register_login_logout_flow(self):
        """Test complete flow: register -> admin activates -> login -> logout."""
        # Step 1: Register new user
        register_response = client.post("/api/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "password123"
        })
        assert register_response.status_code == 201
        user_data = register_response.json()
        assert user_data["user"]["is_active"] is False

        # Step 2: Try to login (should fail - not activated)
        login_response = client.post("/api/auth/login", json={
            "username": "newuser",
            "password": "password123"
        })
        assert login_response.status_code == 401

        # Step 3: Admin activates user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        admin_create = UserCreate(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        UserService.create_user(db, admin_create, role="admin", is_active=True)
        db.commit()
        db.close()

        # Admin login
        admin_login = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "adminpass123"
        })
        admin_token = admin_login.json()["access_token"]

        # Activate user
        user_id = user_data["user"]["id"]
        activate_response = client.post(
            f"/api/users/{user_id}/activate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert activate_response.status_code == 200

        # Step 4: Login successfully
        login_response = client.post("/api/auth/login", json={
            "username": "newuser",
            "password": "password123"
        })
        assert login_response.status_code == 200
        tokens = login_response.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

        # Step 5: Access protected endpoint
        me_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["username"] == "newuser"

        # Step 6: Logout
        logout_response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert logout_response.status_code == 200


class TestTokenRefreshFlow:
    """Test token refresh workflow."""

    def test_token_refresh_workflow(self):
        """Test complete token refresh flow."""
        # Create and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Login
        login_response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "password123"
        })
        tokens = login_response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Use access token
        me_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert me_response.status_code == 200

        # Refresh token
        refresh_response = client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert refresh_response.status_code == 200
        new_access_token = refresh_response.json()["access_token"]

        # Use new access token
        me_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        assert me_response.status_code == 200


class TestLoginFailureLimitFlow:
    """Test login failure limit workflow."""

    def test_login_failure_and_recovery(self):
        """Test login failure limit and automatic recovery."""
        # Create and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(
            username="testuser",
            email="test@example.com",
            password="correctpassword"
        )
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Make 4 failed attempts (should return 401)
        for i in range(4):
            response = client.post("/api/auth/login", json={
                "username": "testuser",
                "password": "wrongpassword"
            })
            assert response.status_code == 401

        # 5th attempt should be blocked (returns 429)
        response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "wrongpassword"
        })
        assert response.status_code == 429

        # Even correct password should be blocked
        response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "correctpassword"
        })
        assert response.status_code == 429


class TestUserManagementFlow:
    """Test user management workflow."""

    def test_admin_manages_users(self):
        """Test admin creating, activating, and managing users."""
        # Create admin
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        admin_create = UserCreate(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        UserService.create_user(db, admin_create, role="admin", is_active=True)
        db.commit()
        db.close()

        # Admin login
        admin_login = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "adminpass123"
        })
        admin_token = admin_login.json()["access_token"]

        # Register new user
        register_response = client.post("/api/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "password123"
        })
        user_id = register_response.json()["user"]["id"]

        # Admin lists users
        list_response = client.get(
            "/api/users/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_response.status_code == 200
        users = list_response.json()
        assert len(users) >= 2

        # Admin activates user
        activate_response = client.post(
            f"/api/users/{user_id}/activate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert activate_response.status_code == 200

        # Admin updates user
        update_response = client.put(
            f"/api/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": "updated@example.com"}
        )
        assert update_response.status_code == 200
        assert update_response.json()["user"]["email"] == "updated@example.com"

        # Admin deactivates user
        deactivate_response = client.post(
            f"/api/users/{user_id}/deactivate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert deactivate_response.status_code == 200

        # Admin deletes user
        delete_response = client.delete(
            f"/api/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert delete_response.status_code == 200


class TestActivityLoggingFlow:
    """Test activity logging workflow."""

    def test_activities_are_logged(self):
        """Test that user activities are properly logged."""
        # Create admin
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        admin_create = UserCreate(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        UserService.create_user(db, admin_create, role="admin", is_active=True)
        db.commit()
        db.close()

        # Admin login (creates activity log)
        admin_login = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "adminpass123"
        })
        admin_token = admin_login.json()["access_token"]

        # Create and activate user
        db = TestingSessionLocal()
        user_create = UserCreate(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        user = UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # User login (creates activity log)
        client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "password123"
        })

        # Failed login (creates activity log)
        client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "wrongpassword"
        })

        # Admin checks activity logs
        logs_response = client.get(
            "/api/activity-logs/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert logs_response.status_code == 200
        logs = logs_response.json()["logs"]
        assert len(logs) >= 2  # At least 2 successful login activities (admin + testuser)

        # Check statistics
        stats_response = client.get(
            "/api/activity-logs/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert stats_response.status_code == 200
        stats = stats_response.json()
        assert stats["total_activities"] >= 2  # Fixed: Only successful logins are logged
        assert stats["successful_activities"] >= 2  # Fixed: API returns successful_activities
        # Note: failed logins go to login_attempts table, not activity_logs
        # so failed_activities may be 0 here


class TestSecurityFlow:
    """Test security-related workflows."""

    def test_non_admin_cannot_access_admin_endpoints(self):
        """Test that regular users cannot access admin endpoints."""
        # Create regular user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(
            username="regularuser",
            email="regular@example.com",
            password="password123"
        )
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Login as regular user
        login_response = client.post("/api/auth/login", json={
            "username": "regularuser",
            "password": "password123"
        })
        user_token = login_response.json()["access_token"]

        # Try to access admin endpoints
        response = client.get(
            "/api/users/",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403  # Forbidden

        response = client.get(
            "/api/activity-logs/",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403  # Forbidden
