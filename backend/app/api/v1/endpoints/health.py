"""Health and readiness endpoints."""
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()
_start_time = time.time()


@router.get("/", summary="Basic liveness probe")
async def health_check():
    return {"status": "ok", "uptime_seconds": round(time.time() - _start_time, 1)}


@router.get("/ready", summary="Readiness probe — checks DB connectivity")
async def readiness(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}
