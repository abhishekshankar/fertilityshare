"""Rate limiting tests: 429 + Retry-After, per-IP, /health exempt."""

import pytest
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter

from syllabus.api.main import app
from syllabus.api.rate_limit import get_remote_address

# Route name for /health so we can exempt it on a test limiter (middleware checks this)
_HEALTH_ROUTE_NAME = "syllabus.api.main.health"


def _key_by_forwarded(request):
    """Use X-Forwarded-For as key when present (for per-IP test without env reload)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@pytest.fixture
def strict_limiter():
    """Temporarily use 2/minute so we can trigger 429 in a few requests."""
    original = app.state.limiter
    new_limiter = Limiter(
        key_func=get_remote_address,
        application_limits=["2/minute"],
        default_limits=[],
        headers_enabled=True,
    )
    new_limiter._exempt_routes.add(_HEALTH_ROUTE_NAME)
    app.state.limiter = new_limiter
    yield
    app.state.limiter = original


async def test_v1_rate_limited_returns_429_and_retry_after(strict_limiter):
    """Exceeding per-IP limit returns 429 and Retry-After header."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # First two requests allowed (401 without auth is fine; limit still applies)
        r1 = await client.get("/v1/courses")
        r2 = await client.get("/v1/courses")
        assert r1.status_code == 401
        assert r2.status_code == 401
        # Third request should be rate limited
        r3 = await client.get("/v1/courses")
    assert r3.status_code == 429
    retry_after_header_names = [k.lower() for k in r3.headers]
    assert "retry-after" in retry_after_header_names
    retry_after = r3.headers.get("Retry-After") or r3.headers.get("retry-after")
    assert retry_after is not None
    assert retry_after.isdigit()
    assert int(retry_after) > 0


async def test_health_exempt_from_rate_limit(strict_limiter):
    """GET /health is exempt and never returns 429."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for _ in range(5):
            r = await client.get("/health")
            assert r.status_code == 200
            assert r.json() == {"status": "ok"}


async def test_different_ips_do_not_share_limit():
    """Different keys (e.g. X-Forwarded-For IPs) have separate rate limit buckets."""
    original = app.state.limiter
    app.state.limiter = Limiter(
        key_func=_key_by_forwarded,
        application_limits=["2/minute"],
        default_limits=[],
        headers_enabled=True,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Exhaust limit for "client_a"
            for _ in range(3):
                r = await client.get(
                    "/v1/courses",
                    headers={"X-Forwarded-For": "192.168.1.1"},
                )
            assert r.status_code == 429
            # Different IP should still get 401 (not 429)
            r_other = await client.get(
                "/v1/courses",
                headers={"X-Forwarded-For": "192.168.1.2"},
            )
        assert r_other.status_code == 401
    finally:
        app.state.limiter = original
