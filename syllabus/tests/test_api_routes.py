"""API route tests (auth, generate, course) using dependency overrides and mocks."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from syllabus.api.main import app
from syllabus.db.models import User


def _mock_user(invite_allowed: bool = True) -> User:
    u = User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash=None,
        invite_allowed=invite_allowed,
    )
    return u


@pytest.fixture
def mock_user():
    return _mock_user(invite_allowed=True)


@pytest.fixture
def mock_session_empty_courses():
    """Session that returns no courses and count 0 (for list_courses)."""
    session = AsyncMock()
    result_courses = MagicMock()
    result_courses.scalars.return_value.all.return_value = []
    result_count = MagicMock()
    result_count.scalar.return_value = 0
    session.execute = AsyncMock(side_effect=[result_courses, result_count])
    return session


@pytest.fixture
def mock_session_course_not_found():
    """Session where get_course finds no course (404)."""
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


async def test_health_returns_ok():
    """GET /health returns 200 and status ok (no auth)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_post_generate_requires_auth():
    """POST /v1/generate without Authorization returns 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/v1/generate",
            json={
                "journey_stage": "Newly diagnosed",
                "confusion": "What is AMH?",
                "level": "beginner",
            },
        )
    assert r.status_code == 401


async def test_get_courses_requires_auth():
    """GET /v1/courses without Authorization returns 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/v1/courses")
    assert r.status_code == 401


async def test_get_course_requires_auth():
    """GET /v1/course/{id} without Authorization returns 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get(f"/v1/course/{uuid.uuid4()}")
    assert r.status_code == 401


async def test_post_generate_returns_job_id_with_auth(mock_user):
    """POST /v1/generate with valid auth returns 200 and job_id."""
    from contextlib import asynccontextmanager

    from syllabus.api.deps import get_current_user_allowed

    async def override_user():
        return mock_user

    mock_session = AsyncMock()
    mock_course = MagicMock()
    mock_course.id = uuid.uuid4()

    async def mock_refresh(obj):
        obj.id = mock_course.id

    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = mock_refresh
    mock_session.get = AsyncMock(return_value=mock_course)

    @asynccontextmanager
    async def mock_session_factory():
        yield mock_session

    app.dependency_overrides[get_current_user_allowed] = override_user
    try:
        with (
            patch("syllabus.api.routes.generate._run_job", new_callable=AsyncMock),
            patch("syllabus.api.routes.generate.async_session_factory", mock_session_factory),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                r = await client.post(
                    "/v1/generate",
                    headers={"Authorization": "Bearer fake-token"},
                    json={
                        "journey_stage": "Newly diagnosed",
                        "confusion": "What is AMH?",
                        "level": "beginner",
                    },
                )
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data.get("status") == "queued"
    finally:
        app.dependency_overrides.clear()


async def test_get_courses_returns_list_with_auth(mock_user, mock_session_empty_courses):
    """GET /v1/courses with valid auth returns 200 and list (empty)."""
    from syllabus.api.deps import get_current_user_allowed, get_db

    async def override_user():
        return mock_user

    async def override_db():
        yield mock_session_empty_courses

    app.dependency_overrides[get_current_user_allowed] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get(
                "/v1/courses",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()


async def test_get_course_returns_404_when_not_found(mock_user, mock_session_course_not_found):
    """GET /v1/course/{id} with valid auth but unknown course returns 404."""
    from syllabus.api.deps import get_current_user_allowed, get_db

    course_id = uuid.uuid4()

    async def override_user():
        return mock_user

    async def override_db():
        yield mock_session_course_not_found

    app.dependency_overrides[get_current_user_allowed] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get(
                f"/v1/course/{course_id}",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert r.status_code == 404
        assert "not found" in r.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.clear()


async def test_post_generate_invalid_payload_returns_422():
    """POST /v1/generate with invalid body returns 422."""
    from syllabus.api.deps import get_current_user_allowed

    async def override_user():
        return _mock_user()

    app.dependency_overrides[get_current_user_allowed] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/v1/generate",
                headers={"Authorization": "Bearer fake-token"},
                json={"invalid": "payload"},
            )
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
