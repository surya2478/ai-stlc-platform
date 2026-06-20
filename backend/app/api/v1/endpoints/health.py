"""Health and readiness endpoints."""
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.database import get_db, get_pool_status

router = APIRouter()
_start_time = time.time()


@router.get("/", summary="Basic liveness probe")
async def health_check():
    return {"status": "ok", "uptime_seconds": round(time.time() - _start_time, 1)}


@router.get("/ready", summary="Readiness probe — checks DB connectivity")
async def readiness(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}


@router.get("/pool", summary="Database connection pool statistics")
async def pool_stats(current_user: CurrentUser):
    """SEC-027: Pool stats require authentication — exposes DB internals."""
    return await get_pool_status()
