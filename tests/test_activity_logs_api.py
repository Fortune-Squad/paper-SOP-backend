"""
Unit tests for activity logs API endpoints.
Tests activity log listing, filtering, and statistics.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import Base, get_db
from app.services.user_service import UserService
from app.services.activity_log_service import ActivityLogService

# Create test database
TEST_DATABASE_URL = "sqlite:///./test_activity_logs.db"
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

    # Login to get token (this will create activity logs)
    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "adminpass123"
    })
    return response.json()["access_token"]


class TestListActivityLogs:
    """Test listing activity logs."""

    def test_list_activity_logs(self, admin_token):
        """Test listing activity logs as admin."""
        response = client.get(
            "/api/activity-logs/",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert len(data["logs"]) > 0  # Should have login activity

    def test_list_activity_logs_with_filters(self, admin_token):
        """Test listing activity logs with filters."""
        response = client.get(
            "/api/activity-logs/?action=login&status=success",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        logs = data["logs"]
        assert all(log["action"] == "login" for log in logs)
        assert all(log["status"] == "success" for log in logs)

    def test_list_activity_logs_pagination(self, admin_token):
        """Test activity logs pagination."""
        response = client.get(
            "/api/activity-logs/?skip=0&limit=5",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) <= 5

    def test_list_activity_logs_without_auth(self):
        """Test listing activity logs without authentication."""
        response = client.get("/api/activity-logs/")
        assert response.status_code == 403  # Fixed: FastAPI returns 403 for missing auth


class TestActivityLogStatistics:
    """Test activity log statistics."""

    def test_get_activity_stats(self, admin_token):
        """Test getting activity statistics."""
        response = client.get(
            "/api/activity-logs/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        stats = response.json()
        assert "total_activities" in stats
        assert "successful_activities" in stats  # Fixed: API returns successful_activities
        assert "failed_activities" in stats  # Fixed: API returns failed_activities
        assert "error_activities" in stats  # Fixed: API returns error_activities
        assert stats["total_activities"] > 0


class TestLoginAttempts:
    """Test login attempts tracking."""

    def test_list_login_attempts(self, admin_token):
        """Test listing login attempts."""
        response = client.get(
            "/api/activity-logs/login-attempts",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "attempts" in data
        assert "total" in data
        assert len(data["attempts"]) > 0  # Should have login attempts

    def test_failed_login_creates_attempt(self):
        """Test that failed login creates login attempt record."""
        # Try to login with wrong password
        client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "wrongpassword"
        })

        # Create admin and check login attempts
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

        # Login as admin
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "adminpass123"
        })
        token = response.json()["access_token"]

        # Check login attempts
        response = client.get(
            "/api/activity-logs/login-attempts",
            headers={"Authorization": f"Bearer {token}"}
        )
        attempts = response.json()["attempts"]
        assert any(not attempt["success"] for attempt in attempts)


class TestActivityLogCreation:
    """Test that activities are logged correctly."""

    def test_login_creates_activity_log(self):
        """Test that successful login creates activity log."""
        # Create user
        db = TestingSessionLocal()
        from app.models.user import UserCreate
        user_create = UserCreate(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        UserService.create_user(db, user_create, role="user", is_active=True)
        db.commit()
        db.close()

        # Login
        client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "testpass123"
        })

        # Create admin to check logs
        db = TestingSessionLocal()
        user_create = UserCreate(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        UserService.create_user(db, user_create, role="admin", is_active=True)
        db.commit()
        db.close()

        # Login as admin
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "adminpass123"
        })
        token = response.json()["access_token"]

        # Check activity logs
        response = client.get(
            "/api/activity-logs/?username=testuser",
            headers={"Authorization": f"Bearer {token}"}
        )
        logs = response.json()["logs"]
        assert any(log["action"] == "login" and log["status"] == "success" for log in logs)
