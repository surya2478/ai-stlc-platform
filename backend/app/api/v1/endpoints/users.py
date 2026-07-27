"""User auth and management endpoints."""
from datetime import datetime, timedelta, timezone
import logging
from fastapi import APIRouter, HTTPException, Query, status, Request, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm
import jwt
from jwt.exceptions import PyJWTError

from app.core.limiter import limiter
from app.core.password_validation import validate_password_strength

from app.api.deps import CurrentUser, DBSession
from app.core.security import create_access_token, hash_password, verify_password, create_refresh_token
from app.core.redis_client import redis_client
from app.config import get_settings

settings = get_settings()
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.rbac_service import (
    GLOBAL_ADMIN_ROLES,
    MANAGE_PROJECT,
    list_user_memberships,
    permissions_for_role,
    user_has_permission,
)
from app.schemas.user import Token, UserCreate, UserRead, UserUpdate
from app.core import audit_logger as audit

router = APIRouter()

GLOBAL_ROLES = ["admin", "qa_engineer", "qa_lead", "viewer"]
logger = logging.getLogger(__name__)

# In-memory account lockout tracker: {username: {"attempts": int, "lockout_until": datetime}}
lockout_tracker = {}


def require_platform_admin(user: User) -> None:
    if not (user.is_superuser or user.role in GLOBAL_ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin access required")


async def ensure_not_last_active_admin(db: DBSession, user: User, updates: UserUpdate) -> None:
    if user.is_superuser and (updates.is_active is False or updates.is_superuser is False or (updates.role and updates.role not in GLOBAL_ADMIN_ROLES)):
        repo = UserRepository(db)
        admins = [
            candidate
            for candidate in await repo.list_users(skip=0, limit=200)
            if candidate.id != user.id and candidate.is_active and (candidate.is_superuser or candidate.role in GLOBAL_ADMIN_ROLES)
        ]
        if not admins:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one active platform admin must remain",
            )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")
async def register(request: Request, data: UserCreate, db: DBSession):
    try:
        validate_password_strength(data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    repo = UserRepository(db)
    email = data.email.strip().lower()
    existing = await repo.get_by_email(email)
    if existing:
        audit.registration(email=email, ip=request.client.host if request.client else None, success=False, reason="email_already_registered")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(
        email=email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role="qa_engineer",
        is_superuser=False,
    )
    result = await repo.create(user)
    audit.registration(email=email, ip=request.client.host if request.client else None, success=True)
    return result


@router.get("", response_model=list[UserRead])
@router.get("/", response_model=list[UserRead])
async def list_users(
    current_user: CurrentUser,
    db: DBSession,
    skip: int = 0,
    limit: int = Query(50, ge=1, le=200),
    search: str | None = None,
    project_id: int | None = Query(None, ge=1),
):
    if not (current_user.is_superuser or current_user.role in GLOBAL_ADMIN_ROLES):
        if not project_id or not await user_has_permission(db, current_user, project_id, MANAGE_PROJECT):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin access required")
    repo = UserRepository(db)
    return await repo.list_users(skip=skip, limit=limit, search=search)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, current_user: CurrentUser, db: DBSession):
    require_platform_admin(current_user)
    if data.role not in GLOBAL_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid global role")
    # Same strength policy as /register. Without this an admin could mint an
    # account weaker than any user could create for themselves.
    try:
        validate_password_strength(data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    repo = UserRepository(db)
    # Normalise exactly as /register and /login do. Storing the address as
    # typed produced accounts that could never log in: login lowercases before
    # looking up, so a row created as "Admin@Local.test" was unreachable. The
    # duplicate check has to use the normalised form too, or a second,
    # unreachable row could be created alongside an existing account.
    email = data.email.strip().lower()
    existing = await repo.get_by_email(email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(
        email=email,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password),
        role=data.role,
        is_superuser=data.is_superuser,
        is_active=True,
    )
    return await repo.create(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(user_id: int, data: UserUpdate, current_user: CurrentUser, db: DBSession):
    require_platform_admin(current_user)
    if data.role is not None and data.role not in GLOBAL_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid global role")
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await ensure_not_last_active_admin(db, user, data)
    updates = data.model_dump(exclude_unset=True)
    return await repo.update(user, updates)


@router.post("/token", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: DBSession = ...):
    username = form_data.username.strip().lower()
    
    # Check lockout status
    now = datetime.now(timezone.utc)
    lockout = lockout_tracker.get(username)
    if lockout and lockout.get("lockout_until"):
        if now < lockout["lockout_until"]:
            remaining = int((lockout["lockout_until"] - now).total_seconds() / 60)
            remaining = max(1, remaining)
            logger.warning("Blocked login attempt for locked-out user: %s", username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Account is locked due to too many failed login attempts. Try again in {remaining} minutes.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            # Lockout expired
            lockout_tracker[username] = {"attempts": 0, "lockout_until": None}

    repo = UserRepository(db)
    user = await repo.get_by_email(username)
    client_ip = request.client.host if request.client else None
    if not user or not verify_password(form_data.password, user.hashed_password):
        # Track failed attempt
        if username not in lockout_tracker:
            lockout_tracker[username] = {"attempts": 0, "lockout_until": None}

        lockout_tracker[username]["attempts"] += 1
        attempts = lockout_tracker[username]["attempts"]

        logger.warning("Failed login attempt for email %s. Attempt %s/10.", username, attempts)
        audit.login_failure(email=username, ip=client_ip, reason="bad_credentials")

        if attempts >= 10:
            lockout_tracker[username]["lockout_until"] = now + timedelta(minutes=30)
            logger.critical("User account locked due to excessive failed logins: %s", username)
            audit.login_failure(email=username, ip=client_ip, reason="account_locked")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is locked due to too many failed login attempts. Try again in 30 minutes.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Success: clear failed attempts
    lockout_tracker[username] = {"attempts": 0, "lockout_until": None}

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    memberships = await list_user_memberships(db, user.id)
    membership_claims = [
        {
            "project_id": membership.project_id,
            "role": membership.role,
            "permissions": sorted(permissions_for_role(membership.role)),
        }
        for membership in memberships
    ]
    # NOTE: project_memberships (with per-project permission lists) is deliberately
    # kept out of the JWT and only returned in the response body below. Embedding it
    # in the cookie pushed the encoded token past the browser's ~4096-byte per-cookie
    # limit for users with several memberships, so the browser silently dropped the
    # access_token cookie on every login/refresh -- nothing in the backend reads
    # global_role/project_memberships back out of the token, so this is safe.
    token = create_access_token(
        user.id,
        extra_claims={"global_role": user.role},
    )
    refresh_token = create_refresh_token(user.id)

    # Set httpOnly cookies
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True if settings.app_env != "local" else False,
        samesite="strict",
        max_age=15 * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True if settings.app_env != "local" else False,
        samesite="strict",
        max_age=7 * 24 * 3600,
    )

    audit.login_success(user_id=user.id, email=user.email, ip=client_ip)
    return Token(access_token=token, global_role=user.role, project_memberships=membership_claims)


@router.post("/logout")
async def logout(request: Request, response: Response, db: DBSession):
    client_ip = request.client.host if request.client else None
    user_id: int | None = None
    user_email: str | None = None
    revoked_jti: str | None = None

    # Revoke access token
    access_token = request.cookies.get("access_token")
    if not access_token:
        authorization: str = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            access_token = authorization.split(" ")[1]

    if access_token:
        try:
            payload = jwt.decode(access_token, settings.app_secret_key, algorithms=["HS256"], options={"verify_exp": False})
            jti = payload.get("jti")
            user_id = payload.get("sub")
            if jti:
                revoked_jti = jti
                await redis_client.setex(f"blocklist:{jti}", 15 * 60, "true")
        except PyJWTError:
            pass

    # Revoke refresh token
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = jwt.decode(refresh_token, settings.app_secret_key, algorithms=["HS256"], options={"verify_exp": False})
            jti = payload.get("jti")
            if jti:
                await redis_client.setex(f"blocklist:{jti}", 7 * 24 * 3600, "true")
        except PyJWTError:
            pass

    audit.logout(user_id=int(user_id) if user_id else None, email=user_email or "", jti=revoked_jti, ip=client_ip)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"status": "success", "detail": "Logged out successfully"}


@router.post("/refresh", response_model=Token)
async def refresh_session(request: Request, response: Response, db: DBSession):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
        
    try:
        payload = jwt.decode(refresh_token, settings.app_secret_key, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        jti: str = payload.get("jti")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
            
        # Check if refresh token is blocklisted
        is_blocked = await redis_client.get(f"blocklist:{jti}")
        if is_blocked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")
            
        # Rotation reuse detection
        is_used = await redis_client.get(f"refresh_used:{jti}")
        if is_used:
            logger.critical("Replay attack detected on refresh token %s for user %s", jti, user_id)
            response.delete_cookie("access_token")
            response.delete_cookie("refresh_token")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token reuse detected. Re-authentication required.")
            
        # Mark current refresh token as used
        await redis_client.setex(f"refresh_used:{jti}", 7 * 24 * 3600, "used")
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate refresh token")
        
    repo = UserRepository(db)
    user = await repo.get_by_id(int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        
    # Generate new tokens
    memberships = await list_user_memberships(db, user.id)
    membership_claims = [
        {
            "project_id": membership.project_id,
            "role": membership.role,
            "permissions": sorted(permissions_for_role(membership.role)),
        }
        for membership in memberships
    ]
    # See NOTE in login() -- project_memberships stays out of the JWT/cookie.
    new_access_token = create_access_token(
        user.id,
        extra_claims={"global_role": user.role},
    )
    new_refresh_token = create_refresh_token(user.id)
    
    # Set cookies
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=True if settings.app_env != "local" else False,
        samesite="strict",
        max_age=15 * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True if settings.app_env != "local" else False,
        samesite="strict",
        max_age=7 * 24 * 3600,
    )
    
    return Token(access_token=new_access_token, global_role=user.role, project_memberships=membership_claims)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser):
    return current_user
