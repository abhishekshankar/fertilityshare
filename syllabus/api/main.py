"""FastAPI app: V1 API (generate, stream, course)."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from syllabus.api.routes import auth, course, generate


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # shutdown: nothing to close for in-memory job store


app = FastAPI(title="Syllabus API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(generate.router)
app.include_router(course.router)
