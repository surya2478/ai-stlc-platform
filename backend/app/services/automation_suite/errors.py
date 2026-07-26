"""Typed errors for the Automation Test Suite service."""
from __future__ import annotations

from fastapi import HTTPException


class AutomationSuiteError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})
