"""JWT creation/validation and password hashing."""

import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get("JWT_SECRET", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt truncates at 72 bytes; passlib can raise ValueError if longer
_BCRYPT_MAX_BYTES = 72


def _truncate_for_bcrypt(s: str) -> str:
    """Truncate to at most 72 UTF-8 bytes on a character boundary so bcrypt sees stable input."""
    encoded = s.encode("utf-8")
    if len(encoded) <= _BCRYPT_MAX_BYTES:
        return s
    truncated = encoded[:_BCRYPT_MAX_BYTES]
    return truncated.decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return pwd_context.hash(_truncate_for_bcrypt(password))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_truncate_for_bcrypt(plain), hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
