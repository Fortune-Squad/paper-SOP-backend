"""
Unit tests for user management API endpoints.
Tests user CRUD operations, activation/deactivation, and statistics.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import Base, get_db
from app.services.user_service import UserService

# Create test database
TEST_DATABASE_URL = "sqlite:///./test_users.db"
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

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin_token():
    """Create admin user and return access token."""
    db = TestingSessionLocal()
    from app.models.user import UserCreate
    user_create = UserCreate(
        username="admin",
        email="admin@example.com",
        password="adminpass123"
    )
    UserService.create_user(db, user_create, role="admin", is_active=True)
    db.commit()
    db.close()

    # Login to get token
    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "adminpass123"
    })
    return response.json()["access_token"]


@pytest.fixture
def regular_user():
    """Create a regular user."""
    db = TestingSessionLocal()
    from app.models.user import UserCreate
    user_create = UserCreate(
        username="testuser",
        email="test@example.com",
        password="testpass123"
    )
    user = UserService.create_user(db, user_create, role="user", is_active=False)
    db.commit()
    # Store user data before closing session to avoid DetachedInstanceError
    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active
    }
    db.close()
    return type('User', (), user_data)()  # Return object with attributes


class TestListUsers:
    """Test listing users."""

    def test_list_users_as_admin(self, admin_token, regular_user):
        """Test listing users as admin."""
        response = client.get(
            "/api/users/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        users = response.json()
        assert len(users) >= 2  # admin + regular_user
        assert any(u["username"] == "admin" for u in users)
        assert any(u["username"] == "testuser" for u in users)

    def test_list_users_with_filters(self, admin_token, regular_user):
        """Test listing users with filters."""
        response = client.get(
            "/api/users/?role=admin",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        users = response.json()
        assert all(u["role"] == "admin" for u in users)

    def test_list_users_without_auth(self):
        """Test listing users without authentication."""
        response = client.get("/api/users/")
        assert response.status_code == 403  # Fixed: FastAPI returns 403 for missing auth


class TestGetUser:
    """Test getting user details."""

    def test_get_user_as_admin(self, admin_token, regular_user):
        """Test getting user details as admin."""
        response = client.get(
            f"/api/users/{regular_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        user = response.json()
        assert user["username"] == "testuser"
        assert user["email"] == "test@example.com"

    def test_get_nonexistent_user(self, admin_token):
        """Test getting nonexistent user."""
        response = client.get(
            "/api/users/999999",  # Use numeric ID instead of string
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404


class TestUpdateUser:
    """Test updating user."""

    def test_update_user_email(self, admin_token, regular_user):
        """Test updating user email."""
        response = client.put(
            f"/api/users/{regular_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": "newemail@example.com"}
        )
        assert response.status_code == 200
        user = response.json()
        assert user["email"] == "newemail@example.com"

    def test_update_user_role(self, admin_token, regular_user):
        """Test updating user role."""
        response = client.put(
            f"/api/users/{regular_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "admin"}
        )
        assert response.status_code == 200
        user = response.json()
        assert user["role"] == "admin"


class TestActivateDeactivateUser:
    """Test user activation and deactivation."""

    def test_activate_user(self, admin_token, regular_user):
        """Test activating a user."""
        response = client.post(
            f"/api/users/{regular_user.id}/activate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        user = response.json()
        assert user["is_active"] is True

    def test_deactivate_user(self, admin_token):
        """Test deactivating a user."""
        # Create and activate a user first
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(
            username="activeuser",
            email="active@example.com",
            password="password123"
        )
        user = UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        user_id = user.id
        db.close()

        # Deactivate
        response = client.post(
            f"/api/users/{user_id}/deactivate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        user = response.json()
        assert user["is_active"] is False


class TestDeleteUser:
    """Test user deletion."""

    def test_delete_user(self, admin_token, regular_user):
        """Test deleting a user."""
        response = client.delete(
            f"/api/users/{regular_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

        # Verify user is deleted
        response = client.get(
            f"/api/users/{regular_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404


class TestUserStatistics:
    """Test user statistics endpoint."""

    def test_get_user_stats(self, admin_token, regular_user):
        """Test getting user statistics."""
        response = client.get(
            "/api/users/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        stats = response.json()
        assert "total_users" in stats
        assert "active_users" in stats
        assert "admin_users" in stats
        assert stats["total_users"] >= 2
