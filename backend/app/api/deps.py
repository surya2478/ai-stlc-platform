"""Shared FastAPI dependency injections."""
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.rbac_service import VIEW_PROJECT, user_has_permission
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)
settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/token", auto_error=False)

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    db: DBSession,
) -> User | None:
    # 1. Read token from cookie
    token = request.cookies.get("access_token")
    
    # 2. Fallback to Authorization header if not in cookie
    if not token:
        authorization: str = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]

    if token is None:
        return None
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        jti: str = payload.get("jti")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            
        # Check Redis blocklist
        if jti:
            is_blocked = await redis_client.get(f"blocklist:{jti}")
            if is_blocked:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    repo = UserRepository(db)
    user = await repo.get_by_id(int(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


async def _ensure_dev_user(db: AsyncSession):
    from app.core.security import hash_password
    from app.database import AsyncSessionLocal

    if not settings.dev_seed_user_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dev user seeding is disabled",
        )
    if not settings.dev_seed_user_email or not settings.dev_seed_user_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dev user seed email/password are not configured",
        )

    repo = UserRepository(db)

    # First try: user may already exist
    dev_user = await repo.get_by_email(settings.dev_seed_user_email)
    if dev_user is not None:
        logger.info("Dev user found in DB (id=%s)", dev_user.id)
        return dev_user

    # Not found - seed via its own committed session
    logger.info("Dev user not found - attempting to seed now")
    seed_error = None
    try:
        async with AsyncSessionLocal() as seed_db:
            seed_db.add(User(
                email=settings.dev_seed_user_email,
                full_name="Dev User",
                hashed_password=hash_password(settings.dev_seed_user_password),
                role="admin",
                is_active=True,
                is_superuser=True,
            ))
            await seed_db.commit()
            logger.info("Dev user seeded successfully")
    except Exception as exc:
        seed_error = exc
        logger.warning("Dev user seed failed: %s: %s", type(exc).__name__, exc)

    # Second try: re-fetch after seeding
    dev_user = await repo.get_by_email(settings.dev_seed_user_email)
    if dev_user is not None:
        return dev_user

    # Still not found - surface the seed error so it is visible
    if seed_error is not None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dev user seed failed: {type(seed_error).__name__}: {seed_error}",
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Dev user not found and could not be created. Check DB and backend logs.",
    )


async def require_user(
    current_user: Annotated[User | None, Depends(get_current_user)],
    db: DBSession,
) -> User:
    if current_user is not None:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_project_access(project_id: int, current_user: User, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.owner_id == current_user.id or await user_has_permission(db, current_user, project_id, VIEW_PROJECT):
        return project
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def require_permission(permission: str, project_id: int, current_user: User, db: AsyncSession) -> Project:
    project = await require_project_access(project_id, current_user, db)
    if project.owner_id == current_user.id:
        return project
    if not await user_has_permission(db, current_user, project_id, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return project


def permission_dependency(permission: str):
    async def _dependency(project_id: int, current_user: CurrentUser, db: DBSession) -> Project:
        return await require_permission(permission, project_id, current_user, db)

    return _dependency


async def require_entity_project_access(entity, current_user: User, db: AsyncSession) -> None:
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    project_id = getattr(entity, "project_id", None)
    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Entity is not project-scoped",
        )
    await require_project_access(project_id, current_user, db)


async def require_entity_permission(entity, permission: str, current_user: User, db: AsyncSession) -> None:
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    project_id = getattr(entity, "project_id", None)
    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Entity is not project-scoped",
        )
    await require_permission(permission, project_id, current_user, db)


CurrentUser = Annotated[User, Depends(require_user)]
