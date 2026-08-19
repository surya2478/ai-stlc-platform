"""
STLC Automation Platform - FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.core.limiter import limiter

from app.api.v1.router import api_router
from app.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _seed_dev_user() -> None:
    """
    In local dev mode, optionally seed a user from explicit environment
    variables. This is disabled by default so repository defaults do not
    ship credentials.
    """
    from app.core.security import hash_password
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.repositories.user_repository import UserRepository

    if not settings.dev_seed_user_enabled:
        logger.info("Local dev user seeding disabled")
        return
    if not settings.dev_seed_user_email or not settings.dev_seed_user_password:
        logger.warning("Local dev user seeding requested but email/password are not configured")
        return

    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        existing = await repo.get_by_email(settings.dev_seed_user_email)
        if existing:
            logger.info("Dev user already exists (id=%s)", existing.id)
            return

        dev_user = User(
            email=settings.dev_seed_user_email,
            full_name="Dev User",
            hashed_password=hash_password(settings.dev_seed_user_password),
            role="admin",
            is_active=True,
            is_superuser=True,
        )
        db.add(dev_user)
        await db.commit()
        await db.refresh(dev_user)
        logger.info("Dev user seeded - id=%s email=%s", dev_user.id, settings.dev_seed_user_email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("STLC Platform starting up [env=%s]", settings.app_env)

    from app.core.startup_checks import validate_production_config
    validate_production_config(settings)

    import os

    for sub in ("uploads", "reports", "artifacts", "scripts"):
        os.makedirs(f"{settings.file_storage_path}/{sub}", exist_ok=True)

    if settings.app_env == "local":
        try:
            await _seed_dev_user()
        except Exception as exc:
            logger.warning("Dev user seed failed (DB may not be ready yet): %s", exc)

    yield
    logger.info("STLC Platform shutting down")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # Disable legacy XSS auditor (causes XSS in IE/old Chrome; modern browsers ignore it)
        response.headers["X-XSS-Protection"] = "0"
        # No Strict-Transport-Security: this deployment is served over plain
        # HTTP. A browser ignores HSTS received over HTTP anyway, and emitting
        # it is actively harmful the first time anyone reaches the host over
        # TLS — that browser then force-upgrades every later http:// visit to a
        # port nothing listens on, curable only by clearing the site's HSTS
        # entry by hand. Restore this line together with TLS termination.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI Agent-based End-to-End STLC Automation Platform. "
        "Manages the full Software Test Life Cycle via autonomous agents."
    ),
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["health"], summary="Root health check")
async def root():
    # SEC-050: Return only status — no env, version, or app name to unauthenticated callers.
    return {"status": "ok"}
