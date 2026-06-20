import pytest
from fastapi import HTTPException
from app.core.password_validation import validate_password_strength
from app.api.v1.endpoints.users import lockout_tracker, login
from fastapi.security import OAuth2PasswordRequestForm
from unittest.mock import AsyncMock, MagicMock
from starlette.requests import Request
from starlette.responses import Response
from datetime import datetime, timedelta, timezone

def test_password_strength_validation():
    # Too short
    with pytest.raises(ValueError, match="at least 12 characters"):
        validate_password_strength("Short1!")

    # No uppercase
    with pytest.raises(ValueError, match="at least one uppercase letter"):
        validate_password_strength("lowercase123!")

    # No lowercase
    with pytest.raises(ValueError, match="at least one lowercase letter"):
        validate_password_strength("UPPERCASE123!")

    # No digit
    with pytest.raises(ValueError, match="at least one digit"):
        validate_password_strength("NoDigitsHere!")

    # No special char
    with pytest.raises(ValueError, match="at least one special character"):
        validate_password_strength("NoSpecial1234")

    # Common password (password123 is in SecLists and fails other rules, so let's mock/check a complex common one)
    # E.g. "Password123!" or we can mock/insert a test value into COMMON_PASSWORDS
    from app.core.common_passwords import COMMON_PASSWORDS
    COMMON_PASSWORDS.add("ComplexCommonPassword123!")
    with pytest.raises(ValueError, match="Password is too common"):
        validate_password_strength("ComplexCommonPassword123!")

    # Valid password
    validate_password_strength("SecureP@ss1234!")


@pytest.mark.asyncio
async def test_account_lockout_logic():
    # Setup mock form and DB
    form = OAuth2PasswordRequestForm(username="lockeduser@example.com", password="wrongpassword", scope="")
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    
    # Reset lockout tracker for this user
    username = "lockeduser@example.com"
    if username in lockout_tracker:
        del lockout_tracker[username]
        
    req = Request(scope={"type": "http", "client": ("127.0.0.1", 12345), "headers": [], "path": "/api/v1/users/token", "method": "POST"})
    res = Response()

    # Simulate 9 failed logins
    for i in range(9):
        with pytest.raises(HTTPException) as exc_info:
            await login(request=req, response=res, form_data=form, db=db)
        assert exc_info.value.status_code == 401
        assert "Incorrect email or password" in exc_info.value.detail
        assert lockout_tracker[username]["attempts"] == i + 1

    # The 10th failed login locks the account
    with pytest.raises(HTTPException) as exc_info:
        await login(request=req, response=res, form_data=form, db=db)
    assert exc_info.value.status_code == 401
    assert "locked due to too many failed" in exc_info.value.detail
    assert lockout_tracker[username]["attempts"] == 10
    assert lockout_tracker[username]["lockout_until"] is not None

    # Subsequent login requests block immediately
    with pytest.raises(HTTPException) as exc_info:
        await login(request=req, response=res, form_data=form, db=db)
    assert exc_info.value.status_code == 401
    assert "Account is locked" in exc_info.value.detail
