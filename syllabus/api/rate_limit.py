"""Per-IP rate limiting for V1 API (PRD 6.5). In-memory backend; optional X-Forwarded-For when behind proxy."""

import os
import re

from fastapi import Request
from slowapi import Limiter

# Simple IPv4 and IPv6 patterns for validation (avoid header injection)
_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+$")


def _valid_ip(ip: str) -> bool:
    if not ip or not ip.strip():
        return False
    s = ip.strip()
    if _IPV4_RE.match(s):
        parts = s.split(".")
        return all(0 <= int(p) <= 255 for p in parts)
    return bool(_IPV6_RE.match(s))


def get_remote_address(request: Request) -> str:
    """Client IP for rate limit key. Uses X-Forwarded-For when RATE_LIMIT_TRUST_PROXY=1."""
    if os.getenv("RATE_LIMIT_TRUST_PROXY", "").strip().lower() in ("1", "true", "yes"):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Leftmost is the client when proxies append
            first = forwarded.split(",")[0].strip()
            if _valid_ip(first):
                return first
    client = getattr(request.client, "host", None) if request.client else None
    return client or "127.0.0.1"


def _default_limit_string() -> str:
    raw = os.getenv("RATE_LIMIT_DEFAULT", "100/minute").strip()
    return raw or "100/minute"


limiter = Limiter(
    key_func=get_remote_address,
    application_limits=[_default_limit_string()],
    default_limits=[],
    headers_enabled=True,
)
