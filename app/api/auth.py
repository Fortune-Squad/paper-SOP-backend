"""
Authentication API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.user import (
    UserCreate, User, LoginRequest, LoginResponse, RegisterResponse, Token, RefreshTokenRequest,
    ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest, ResetPasswordResponse
)
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.activity_log_service import ActivityLogService
from app.services.refresh_token_service import RefreshTokenService
from app.services.password_reset_service import PasswordResetService
from app.middleware.auth import get_current_user, get_current_active_user
from app.db.models import User as DBUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    db: Session = Depends(get_db)
):
    """
    Register a new user.

    **Note**: New users are created with `is_active=False` and require admin approval.

    Args:
        user_create: User registration data (username, email, password)
        db: Database session

    Returns:
        RegisterResponse with message and user info

    Raises:
        HTTPException: 400 if username or email already exists
    """
    try:
        # Create user with is_active=False (requires admin approval)
        db_user = UserService.create_user(db, user_create, role="user", is_active=False)

        # Convert to Pydantic model
        user = User.model_validate(db_user)

        logger.info(f"New user registered: {user.username} (pending approval)")

        return RegisterResponse(
            message="Registration successful. Your account is pending admin approval.",
            user=user
        )

    except ValueError as e:
        logger.warning(f"Registration failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=LoginResponse)
async def login(
    login_request: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Login with username and password.

    Args:
        login_request: Login credentials (username, password)
        request: FastAPI request object
        db: Database session

    Returns:
        LoginResponse with access token and user info

    Raises:
        HTTPException: 401 if credentials are invalid or account is not active
        HTTPException: 429 if too many failed attempts
    """
    # Get IP address and user agent
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Check if IP is blocked
    if ActivityLogService.is_ip_blocked(db, ip_address):
        ActivityLogService.log_login_attempt(
            db, login_request.username, ip_address, user_agent,
            success=False,
            failure_reason="IP blocked due to too many failed attempts"
        )
        logger.warning(f"Login blocked for IP: {ip_address}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts from this IP. Please try again in 15 minutes.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is blocked
    if ActivityLogService.is_user_blocked(db, login_request.username):
        ActivityLogService.log_login_attempt(
            db, login_request.username, ip_address, user_agent,
            success=False,
            failure_reason="User blocked due to too many failed attempts"
        )
        logger.warning(f"Login blocked for user: {login_request.username}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts for this account. Please try again in 15 minutes.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attempt login
    result = AuthService.login(db, login_request)

    if not result:
        # Record failed login attempt
        ActivityLogService.log_login_attempt(
            db, login_request.username, ip_address, user_agent,
            success=False,
            failure_reason="Invalid credentials"
        )

        # Calculate remaining attempts
        failed_attempts = ActivityLogService.get_failed_login_attempts(
            db, username=login_request.username, minutes=15
        )
        remaining = max(0, 5 - failed_attempts)

        logger.warning(f"Login failed for user: {login_request.username} ({remaining} attempts remaining)")

        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Incorrect username or password. {remaining} attempts remaining.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please try again in 15 minutes.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    access_token, user_dict = result
    user = User(**user_dict)

    # Create refresh token
    refresh_token_obj = RefreshTokenService.create_refresh_token(db, int(user.id))

    # Record successful login attempt
    ActivityLogService.log_login_attempt(
        db, login_request.username, ip_address, user_agent,
        success=True
    )

    # Log activity
    ActivityLogService.log_activity(
        db,
        user_id=int(user.id),
        username=user.username,
        action="login",
        ip_address=ip_address,
        user_agent=user_agent,
        status="success"
    )

    logger.info(f"User logged in: {user.username}")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_obj.token,
        token_type="bearer",
        user=user
    )


@router.post("/logout")
async def logout(
    current_user: DBUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Logout current user and revoke all refresh tokens.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    # Revoke all refresh tokens for this user
    revoked_count = RefreshTokenService.revoke_all_user_tokens(db, current_user.id)

    logger.info(f"User logged out: {current_user.username} ({revoked_count} tokens revoked)")

    return {
        "message": "Logout successful",
        "username": current_user.username,
        "tokens_revoked": revoked_count
    }


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: DBUser = Depends(get_current_active_user)
):
    """
    Get current user information.

    Args:
        current_user: Current authenticated user

    Returns:
        Current user info
    """
    return User.model_validate(current_user)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    Args:
        refresh_request: Refresh token request
        db: Database session

    Returns:
        New access token

    Raises:
        HTTPException: 401 if refresh token is invalid or expired
    """
    # Verify refresh token and get user
    user = RefreshTokenService.verify_refresh_token(db, refresh_request.refresh_token)

    if not user:
        logger.warning(f"Invalid or expired refresh token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new access token
    access_token = AuthService.create_token_for_user(
        user.id,
        user.username,
        user.role
    )

    logger.info(f"Token refreshed for user: {user.username}")

    return Token(access_token=access_token, token_type="bearer")


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset email.

    Args:
        request: Forgot password request with email
        db: Database session

    Returns:
        Success message

    Note:
        Always returns success message for security (don't reveal if email exists)
    """
    try:
        # Request password reset (sends email if user exists)
        PasswordResetService.request_password_reset(
            db,
            email=request.email,
            frontend_url="http://localhost:5173"  # TODO: Make this configurable
        )

        logger.info(f"Password reset requested for email: {request.email}")

        # Always return success message (don't reveal if email exists)
        return ForgotPasswordResponse(
            message="If the email exists in our system, you will receive a password reset link shortly."
        )

    except Exception as e:
        logger.error(f"Error processing password reset request: {str(e)}")
        # Still return success message for security
        return ForgotPasswordResponse(
            message="If the email exists in our system, you will receive a password reset link shortly."
        )


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using reset token.

    Args:
        request: Reset password request with token and new password
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: 400 if token is invalid or expired
    """
    try:
        # Reset password
        success = PasswordResetService.reset_password(
            db,
            token=request.token,
            new_password=request.new_password
        )

        if not success:
            logger.warning(f"Invalid or expired password reset token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired password reset token"
            )

        logger.info(f"Password reset successfully")

        return ResetPasswordResponse(
            message="Password reset successfully. You can now login with your new password."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting password"
        )
