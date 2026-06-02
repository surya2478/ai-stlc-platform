"""
STLC Automation Platform — FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.api.v1.router import api_router

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def _seed_dev_user() -> None:
    """
    In local dev mode, ensure a default user exists so the UI works
    without requiring registration / login.

    Email : dev@stlc.local
    Password : devpassword
    """
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.repositories.user_repository import UserRepository
    from app.core.security import hash_password

    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        existing = await repo.get_by_email("dev@stlc.local")
        if existing:
            logger.info("Dev user already exists (id=%s)", existing.id)
            return

        dev_user = User(
            email="dev@stlc.local",
            full_name="Dev User",
            hashed_password=hash_password("devpassword"),
            role="admin",
            is_active=True,
            is_superuser=True,
        )
        db.add(dev_user)
        await db.commit()
        await db.refresh(dev_user)
        logger.info("✅  Dev user seeded — id=%s  email=dev@stlc.local  password=devpassword", dev_user.id)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("🚀  STLC Platform starting up  [env=%s]", settings.app_env)

    # Ensure storage directories exist
    import os
    for sub in ("uploads", "reports", "artifacts", "scripts"):
        os.makedirs(f"{settings.file_storage_path}/{sub}", exist_ok=True)

    # Seed dev user in local mode
    if settings.app_env == "local":
        try:
            await _seed_dev_user()
        except Exception as exc:
            logger.warning("Dev user seed failed (DB may not be ready yet): %s", exc)

    yield
    logger.info("🛑  STLC Platform shutting down")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI Agent–based End-to-End STLC Automation Platform. "
        "Manages the full Software Test Life Cycle via autonomous agents."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Root health probe (used by load-balancers / Docker healthcheck) ───────────
@app.get("/", tags=["health"], summary="Root health check")
async def root():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
    }
