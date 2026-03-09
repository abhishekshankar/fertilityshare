"""Shared dependencies: DB session and current user."""

from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from syllabus.api.auth import decode_access_token
from syllabus.db.database import async_session_factory
from syllabus.db.models import User


async def get_db():
    async with async_session_factory() as session:
        yield session


async def _token_to_user(session: AsyncSession, token: str) -> User | None:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await session.execute(select(User).where(User.id == UUID(user_id)))
    return result.scalars().first()


async def get_current_user(
    session: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None, alias="Authorization"),
) -> User:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    user = await _token_to_user(session, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token or user not found")
    return user


async def get_current_user_allowed(
    user: User = Depends(get_current_user),
) -> User:
    """Require authenticated user with invite_allowed (for generate, courses, etc.)."""
    if not user.invite_allowed:
        raise HTTPException(status_code=403, detail="Access not allowed; you are on the waitlist.")
    return user


async def get_current_user_for_stream(
    session: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None, alias="Authorization"),
    token: str | None = Query(None, alias="token"),
) -> User:
    """Auth for SSE stream: accept Bearer header or ?token= for EventSource."""
    auth_token = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization.replace("Bearer ", "").strip()
    elif token:
        auth_token = token
    if not auth_token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    user = await _token_to_user(session, auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token or user not found")
    return user


async def get_current_user_allowed_for_stream(
    user: User = Depends(get_current_user_for_stream),
) -> User:
    """Require invite_allowed for SSE stream."""
    if not user.invite_allowed:
        raise HTTPException(status_code=403, detail="Access not allowed; you are on the waitlist.")
    return user
