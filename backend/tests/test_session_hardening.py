import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response
from fastapi.security import OAuth2PasswordRequestForm
from app.api.v1.endpoints.users import login, logout, refresh_session
from app.core.security import create_access_token, create_refresh_token
from app.core.redis_client import redis_client
import jwt

@pytest.mark.asyncio
async def test_login_sets_cookies():
    form = OAuth2PasswordRequestForm(username="testuser@example.com", password="password", scope="")
    db = AsyncMock()
    
    # Mock user exists
    user_mock = MagicMock()
    user_mock.id = 123
    user_mock.email = "testuser@example.com"
    user_mock.hashed_password = "hashed_password"
    user_mock.is_active = True
    user_mock.role = "qa_engineer"
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user_mock
    db.execute.return_value = mock_result

    req = Request(scope={"type": "http", "client": ("127.0.0.1", 12345), "headers": [], "path": "/api/v1/users/token", "method": "POST"})
    res = Response()
    
    with patch("app.api.v1.endpoints.users.verify_password", return_value=True), \
         patch("app.api.v1.endpoints.users.list_user_memberships", return_value=[]):
        response_body = await login(request=req, response=res, form_data=form, db=db)
        
    # Check that cookies are set
    cookies = [h for h in res.raw_headers if h[0] == b"set-cookie"]
    assert len(cookies) == 2
    cookie_str = b"".join(h[1] for h in cookies).decode()
    assert "access_token=" in cookie_str
    assert "refresh_token=" in cookie_str


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse():
    db = AsyncMock()
    user_mock = MagicMock()
    user_mock.id = 123
    user_mock.is_active = True
    user_mock.role = "qa_engineer"

    
    # Mock UserRepository.get_by_id
    with patch("app.api.v1.endpoints.users.UserRepository") as repo_mock, \
         patch("app.api.v1.endpoints.users.list_user_memberships", return_value=[]):
        repo_instance = repo_mock.return_value
        repo_instance.get_by_id = AsyncMock(return_value=user_mock)

        # Generate a refresh token
        ref_token = create_refresh_token(subject=123)
        payload = jwt.decode(ref_token, options={"verify_signature": False})
        jti = payload["jti"]

        # 1. Normal refresh
        req = Request(scope={
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [],
            "path": "/api/v1/users/refresh",
            "method": "POST"
        })
        req._cookies = {"refresh_token": ref_token}
        res = Response()

        with patch("app.core.redis_client.redis_client.get", new_callable=AsyncMock) as get_mock, \
             patch("app.core.redis_client.redis_client.setex", new_callable=AsyncMock) as setex_mock:
            get_mock.return_value = None
            setex_mock.return_value = None
            refresh_resp = await refresh_session(request=req, response=res, db=db)
            assert refresh_resp.access_token is not None

        # 2. Replay/Reuse detection: Mock redis indicating refresh token is already used
        async def mock_get(k):
            return "used" if "refresh_used:" in k else None

        with patch("app.core.redis_client.redis_client.get", new=mock_get):
            with pytest.raises(HTTPException) as exc_info:
                await refresh_session(request=req, response=res, db=db)
            assert exc_info.value.status_code == 401
            assert "Token reuse detected" in exc_info.value.detail


@pytest.mark.asyncio
async def test_logout_blacklists_tokens():
    req = Request(scope={
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [],
        "path": "/api/v1/users/logout",
        "method": "POST"
    })
    
    access_tok = create_access_token(subject=123)
    ref_tok = create_refresh_token(subject=123)
    
    req._cookies = {"access_token": access_tok, "refresh_token": ref_tok}
    res = Response()

    with patch("app.core.redis_client.redis_client.setex", new_callable=AsyncMock) as setex_mock:
        logout_resp = await logout(request=req, response=res, db=AsyncMock())
        assert logout_resp["status"] == "success"
        
        # Verify setex was called to blacklist the access and refresh token JTIs
        assert setex_mock.call_count == 2

