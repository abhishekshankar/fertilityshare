"""Auth routes: register, login, me, Google OAuth."""

import os
import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from syllabus.api.auth import create_access_token, hash_password, verify_password
from syllabus.api.deps import get_current_user, get_db
from syllabus.db.models import User

router = APIRouter(prefix="/v1", tags=["auth"])

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _allowed_emails() -> set[str]:
    """Allowlist from env (comma-separated). Empty or unset = no one allowed by default."""
    raw = os.environ.get("ALLOWED_EMAILS", "").strip()
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


class RegisterBody(BaseModel):
    email: EmailStr
    password: str


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    email: str
    invite_allowed: bool = False


@router.post("/auth/register", responses={400: {"description": "Email already registered"}})
async def register(
    body: RegisterBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        invite_allowed=body.email.lower() in _allowed_emails(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return TokenResponse(access_token=token)


@router.post("/auth/login", responses={401: {"description": "Invalid email or password"}})
async def login(
    body: LoginBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalars().first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.invite_allowed = user.email.lower() in _allowed_emails()
    await session.commit()
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return TokenResponse(access_token=token)


@router.get("/auth/me")
async def me(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MeResponse:
    # Re-sync invite_allowed from allowlist so adding an email takes effect without API restart
    allowed = user.email.lower() in _allowed_emails()
    if user.invite_allowed != allowed:
        user.invite_allowed = allowed
        await session.commit()
        await session.refresh(user)
    return MeResponse(id=str(user.id), email=user.email, invite_allowed=user.invite_allowed)


@router.get("/auth/google", responses={503: {"description": "Google OAuth not configured"}})
async def auth_google() -> RedirectResponse:
    """Redirect to Google OAuth consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    state = secrets.token_urlsafe(32)
    redirect_uri = f"{os.environ.get('API_URL', 'http://127.0.0.1:8000')}/v1/auth/google/callback"
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid email profile"
        f"&state={state}"
    )
    return RedirectResponse(url=url)


def _debug_log(payload: dict) -> None:
    import json
    entry = {"sessionId": "41ee7a", "timestamp": __import__("time").time() * 1000, **payload}
    line = json.dumps(entry) + "\n"
    # Stdout so Railway/production logs capture it (Option B)
    print(f"[oauth-debug] {line.strip()}", flush=True)
    # Local file for cursor debug session (optional; may fail in containers)
    log_path = "/Users/abhi/Documents/GitHub/fertilityshare/.cursor/debug-41ee7a.log"
    try:
        with open(log_path, "a") as f:
            f.write(line)
    except Exception:
        pass


@router.get("/auth/google/callback")
async def auth_google_callback(
    session: Annotated[AsyncSession, Depends(get_db)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Exchange code for tokens, get user info, create/link user, redirect to frontend with token."""
    # #region agent log
    _debug_log({"location": "auth.py:google_callback:entry", "message": "google_callback_entry", "data": {"has_error": bool(error), "has_code": bool(code), "frontend_url": FRONTEND_URL}, "hypothesisId": "H1"})
    # #endregion
    if error or not code:
        _debug_log({"location": "auth.py:google_callback", "message": "redirect_login_access_denied", "data": {}, "hypothesisId": "H1"})
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=access_denied")
    redirect_uri = f"{os.environ.get('API_URL', 'http://127.0.0.1:8000')}/v1/auth/google/callback"
    # #region agent log
    _debug_log({"location": "auth.py:google_callback", "message": "token_exchange_request", "data": {"redirect_uri": redirect_uri, "api_url_env": os.environ.get("API_URL"), "has_client_id": bool(GOOGLE_CLIENT_ID), "has_client_secret": bool(GOOGLE_CLIENT_SECRET)}, "hypothesisId": "H1"})
    # #endregion
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if token_resp.status_code != 200:
        try:
            err_body = token_resp.text
            if len(err_body) > 500:
                err_body = err_body[:500] + "..."
        except Exception:
            err_body = ""
        _debug_log({"location": "auth.py:google_callback", "message": "redirect_login_token_exchange_failed", "data": {"status": token_resp.status_code, "response_body": err_body}, "hypothesisId": "H1"})
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=token_exchange_failed")
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        _debug_log({"location": "auth.py:google_callback", "message": "redirect_login_no_token", "data": {}, "hypothesisId": "H1"})
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_token")
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if user_resp.status_code != 200:
        _debug_log({"location": "auth.py:google_callback", "message": "redirect_login_userinfo_failed", "data": {"status": user_resp.status_code}, "hypothesisId": "H1"})
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=userinfo_failed")
    userinfo = user_resp.json()
    google_id = userinfo.get("id")
    email = userinfo.get("email")
    if not google_id or not email:
        _debug_log({"location": "auth.py:google_callback", "message": "redirect_login_missing_profile", "data": {}, "hypothesisId": "H1"})
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=missing_profile")
    result = await session.execute(select(User).where(User.google_id == google_id))
    user = result.scalars().first()
    if not user:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if user:
            user.google_id = google_id
            user.invite_allowed = email.lower() in _allowed_emails()
            await session.commit()
            await session.refresh(user)
        else:
            user = User(
                email=email,
                google_id=google_id,
                invite_allowed=email.lower() in _allowed_emails(),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
    else:
        user.invite_allowed = user.email.lower() in _allowed_emails()
        await session.commit()
    token = create_access_token({"sub": str(user.id), "email": user.email})
    success_url = f"{FRONTEND_URL}/auth/callback?token={token}"
    _debug_log({"location": "auth.py:google_callback", "message": "redirect_success", "data": {"redirect_url_prefix": success_url[:80]}, "hypothesisId": "H1"})
    return RedirectResponse(url=success_url)
