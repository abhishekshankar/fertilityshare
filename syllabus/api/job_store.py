"""In-memory job store for generation jobs (job_id -> queue for SSE)."""

import asyncio
import uuid
from typing import Any

# job_id -> asyncio.Queue that receives SSE events (dicts with stage, message, progress, etc.)
_job_queues: dict[str, asyncio.Queue] = {}
# job_id -> { "status": "queued"|"running"|"done"|"failed", "course_id"?: uuid, "error"?: str }
_job_status: dict[str, dict[str, Any]] = {}


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _job_queues[job_id] = asyncio.Queue()
    _job_status[job_id] = {"status": "queued"}
    return job_id


def get_queue(job_id: str) -> asyncio.Queue | None:
    return _job_queues.get(job_id)


def get_status(job_id: str) -> dict[str, Any] | None:
    return _job_status.get(job_id)


def set_status(
    job_id: str, status: str, course_id: str | None = None, error: str | None = None
) -> None:
    if job_id in _job_status:
        _job_status[job_id]["status"] = status
        if course_id is not None:
            _job_status[job_id]["course_id"] = course_id
        if error is not None:
            _job_status[job_id]["error"] = error


async def put_event(job_id: str, event: dict[str, Any]) -> None:
    q = _job_queues.get(job_id)
    if q is not None:
        await q.put(event)


def cleanup_job(job_id: str) -> None:
    """Remove queue so no more events; keep status so late SSE clients can get course_id."""
    _job_queues.pop(job_id, None)
