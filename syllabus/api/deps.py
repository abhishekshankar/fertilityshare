"""Shared dependencies: DB session and current user."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from syllabus.api.auth import decode_access_token
from syllabus.db.database import async_session_factory
from syllabus.db.models import User

BEARER_PREFIX = "Bearer "


def parse_bearer_token(authorization: str | None) -> str | None:
    """Extract Bearer token from Authorization header. Returns None if missing or not Bearer."""
    if not authorization or not authorization.startswith(BEARER_PREFIX):
        return None
    return authorization.replace(BEARER_PREFIX, "").strip() or None


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
    session: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> User:
    token = parse_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    user = await _token_to_user(session, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token or user not found")
    return user


async def get_current_user_allowed(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require authenticated user with invite_allowed (for generate, courses, etc.)."""
    if not user.invite_allowed:
        raise HTTPException(status_code=403, detail="Access not allowed; you are on the waitlist.")
    return user


async def get_current_user_for_stream(
    session: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    token: Annotated[str | None, Query(alias="token")] = None,
) -> User:
    """Auth for SSE stream: accept Bearer header or ?token= for EventSource."""
    auth_token = parse_bearer_token(authorization) or token
    if not auth_token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    user = await _token_to_user(session, auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token or user not found")
    return user


async def get_current_user_allowed_for_stream(
    user: Annotated[User, Depends(get_current_user_for_stream)],
) -> User:
    """Require invite_allowed for SSE stream."""
    if not user.invite_allowed:
        raise HTTPException(status_code=403, detail="Access not allowed; you are on the waitlist.")
    return user
