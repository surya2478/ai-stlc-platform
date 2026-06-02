"""Shared FastAPI dependency injections."""
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
settings = get_settings()

DEV_USER_EMAIL = "dev@stlc.local"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/token", auto_error=False)

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: DBSession,
) -> User | None:
    if token is None:
        return None
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    repo = UserRepository(db)
    user = await repo.get_by_id(int(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def _ensure_dev_user(db: AsyncSession):
    from app.core.security import hash_password
    from app.database import AsyncSessionLocal

    repo = UserRepository(db)

    # First try: user may already exist
    dev_user = await repo.get_by_email(DEV_USER_EMAIL)
    if dev_user is not None:
        logger.info("Dev user found in DB (id=%s)", dev_user.id)
        return dev_user

    # Not found - seed via its own committed session
    logger.info("Dev user not found - attempting to seed now")
    seed_error = None
    try:
        async with AsyncSessionLocal() as seed_db:
            seed_db.add(User(
                email=DEV_USER_EMAIL,
                full_name="Dev User",
                hashed_password=hash_password("devpassword"),
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
    dev_user = await repo.get_by_email(DEV_USER_EMAIL)
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

    if settings.app_env == "local":
        return await _ensure_dev_user(db)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


CurrentUser = Annotated[User, Depends(require_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user)]
