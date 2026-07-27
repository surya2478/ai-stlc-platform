"""Typed errors for the UI-019 Live Recorder service."""
from __future__ import annotations

from fastapi import HTTPException


class RecorderError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, **extra):
        detail = {"code": code, "message": message}
        detail.update(extra)
        super().__init__(status_code=status_code, detail=detail)
