"""
Unit tests for authentication API endpoints.
Tests registration, login, logout, refresh token, and password reset.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import Base, get_db
from app.db.models import User
from app.services.user_service import UserService
import os

# Create test database
TEST_DATABASE_URL = "sqlite:///./test_auth.db"
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
    # Import all models to register them
    from app.db.models import User
    from app.db.activity_models import UserActivityLog, LoginAttempt
    from app.db.refresh_token_models import RefreshToken
    from app.db.password_reset_models import PasswordResetToken

    # Re-apply override in case another test module changed it
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user_data():
    """Test user data."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123"
    }


@pytest.fixture
def admin_user(test_user_data):
    """Create an admin user for testing."""
    db = TestingSessionLocal()
    try:
        from app.models.user import UserCreate
        user_create = UserCreate(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        user = UserService.create_user(db, user_create, role="admin", is_active=True)
        db.commit()
        # Store user data before closing session to avoid DetachedInstanceError
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }
        return user_data
    finally:
        db.close()


class TestUserRegistration:
    """Test user registration endpoint."""

    def test_register_success(self, test_user_data):
        """Test successful user registration."""
        response = client.post("/api/auth/register", json=test_user_data)
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Registration successful. Your account is pending admin approval."
        assert data["user"]["username"] == test_user_data["username"]
        assert data["user"]["email"] == test_user_data["email"]
        assert data["user"]["is_active"] is False  # New users require approval

    def test_register_duplicate_username(self, test_user_data):
        """Test registration with duplicate username."""
        # Register first user
        client.post("/api/auth/register", json=test_user_data)

        # Try to register with same username
        response = client.post("/api/auth/register", json=test_user_data)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    def test_register_invalid_username(self):
        """Test registration with invalid username."""
        response = client.post("/api/auth/register", json={
            "username": "ab",  # Too short
            "email": "test@example.com",
            "password": "testpass123"
        })
        assert response.status_code == 422  # Validation error

    def test_register_invalid_password(self, test_user_data):
        """Test registration with invalid password."""
        test_user_data["password"] = "123"  # Too short
        response = client.post("/api/auth/register", json=test_user_data)
        assert response.status_code == 422  # Validation error


class TestUserLogin:
    """Test user login endpoint."""

    def test_login_success(self, test_user_data):
        """Test successful login."""
        # Register and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(**test_user_data)
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Login
        response = client.post("/api/auth/login", json={
            "username": test_user_data["username"],
            "password": test_user_data["password"]
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == test_user_data["username"]

    def test_login_inactive_user(self, test_user_data):
        """Test login with inactive user."""
        # Register user (inactive by default)
        client.post("/api/auth/register", json=test_user_data)

        # Try to login
        response = client.post("/api/auth/login", json={
            "username": test_user_data["username"],
            "password": test_user_data["password"]
        })
        assert response.status_code == 401
        # Login endpoint returns generic error for security (doesn't reveal account status)
        assert response.json()["detail"]  # just verify there's an error message

    def test_login_wrong_password(self, test_user_data):
        """Test login with wrong password."""
        # Register and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(**test_user_data)
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Try to login with wrong password
        response = client.post("/api/auth/login", json={
            "username": test_user_data["username"],
            "password": "wrongpassword"
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self):
        """Test login with nonexistent user."""
        response = client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "password123"
        })
        assert response.status_code == 401


class TestLoginFailureLimit:
    """Test login failure limit and IP blocking."""

    def test_login_failure_limit(self, test_user_data):
        """Test that account gets blocked after 5 failed attempts."""
        # Register and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(**test_user_data)
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Make 4 failed login attempts (should return 401)
        for i in range(4):
            response = client.post("/api/auth/login", json={
                "username": test_user_data["username"],
                "password": "wrongpassword"
            })
            assert response.status_code == 401

        # 5th attempt should be blocked (returns 429)
        response = client.post("/api/auth/login", json={
            "username": test_user_data["username"],
            "password": "wrongpassword"
        })
        assert response.status_code == 429  # Too Many Requests
        assert "too many failed" in response.json()["detail"].lower()  # Fixed: partial match


class TestRefreshToken:
    """Test refresh token functionality."""

    def test_refresh_token_success(self, test_user_data):
        """Test successful token refresh."""
        # Register and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(**test_user_data)
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Login to get tokens
        login_response = client.post("/api/auth/login", json={
            "username": test_user_data["username"],
            "password": test_user_data["password"]
        })
        refresh_token = login_response.json()["refresh_token"]

        # Refresh token
        response = client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_token_invalid(self):
        """Test refresh with invalid token."""
        response = client.post("/api/auth/refresh", json={
            "refresh_token": "invalid_token"
        })
        assert response.status_code == 401

    def test_refresh_token_after_logout(self, test_user_data):
        """Test that refresh token is revoked after logout."""
        # Register and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(**test_user_data)
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Login
        login_response = client.post("/api/auth/login", json={
            "username": test_user_data["username"],
            "password": test_user_data["password"]
        })
        access_token = login_response.json()["access_token"]
        refresh_token = login_response.json()["refresh_token"]

        # Logout
        client.post("/api/auth/logout", headers={
            "Authorization": f"Bearer {access_token}"
        })

        # Try to refresh with revoked token
        response = client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert response.status_code == 401


class TestPasswordReset:
    """Test password reset functionality."""

    def test_forgot_password_success(self, test_user_data):
        """Test forgot password request."""
        # Register user with email
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(**test_user_data)
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Request password reset
        response = client.post("/api/auth/forgot-password", json={
            "email": test_user_data["email"]
        })
        # Should return 200 even if email service is disabled
        assert response.status_code == 200
        assert "email" in response.json()["message"].lower()

    def test_forgot_password_nonexistent_email(self):
        """Test forgot password with nonexistent email."""
        response = client.post("/api/auth/forgot-password", json={
            "email": "nonexistent@example.com"
        })
        # Should return 200 to prevent email enumeration
        assert response.status_code == 200

    def test_reset_password_invalid_token(self):
        """Test reset password with invalid token."""
        response = client.post("/api/auth/reset-password", json={
            "token": "invalid_token",
            "new_password": "newpassword123"
        })
        assert response.status_code == 400


class TestLogout:
    """Test logout functionality."""

    def test_logout_success(self, test_user_data):
        """Test successful logout."""
        # Register and activate user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(**test_user_data)
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Login
        login_response = client.post("/api/auth/login", json={
            "username": test_user_data["username"],
            "password": test_user_data["password"]
        })
        access_token = login_response.json()["access_token"]

        # Logout
        response = client.post("/api/auth/logout", headers={
            "Authorization": f"Bearer {access_token}"
        })
        assert response.status_code == 200
        assert "logout successful" in response.json()["message"].lower()  # Fixed: API returns "logout successful"

    def test_logout_without_token(self):
        """Test logout without authentication."""
        response = client.post("/api/auth/logout")
        assert response.status_code == 403  # Fixed: FastAPI returns 403 for missing auth
