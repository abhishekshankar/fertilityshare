"""FastAPI app: V1 API (generate, stream, course)."""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from syllabus.api.rate_limit import limiter
from syllabus.api.routes import auth, course, generate


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log OAuth status so devs know what redirect URI to add in Google Cloud Console
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    api_url = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
    if client_id:
        print(
            f"[auth] Google OAuth configured. Redirect URI: {api_url}/v1/auth/google/callback",
            flush=True,
        )
    else:
        print(
            "[auth] Google OAuth not configured (set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET for Sign in with Google)",
            flush=True,
        )
    yield
    # shutdown: nothing to close for in-memory job store


app = FastAPI(title="Syllabus API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_allowed_origins = (
    os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001",
    )
    .strip()
    .split(",")
)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@limiter.exempt
def health(request: Request):
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(generate.router)
app.include_router(course.router)
