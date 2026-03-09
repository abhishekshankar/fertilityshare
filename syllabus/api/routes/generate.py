"""POST /v1/generate and GET /v1/generate/{job_id}/stream (SSE)."""

import asyncio
import json
import queue
import threading
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from syllabus.api.deps import get_current_user_allowed, get_current_user_allowed_for_stream
from syllabus.api.job_store import create_job, get_queue, get_status, put_event, set_status, cleanup_job
from syllabus.db.database import async_session_factory
from syllabus.db.models import Course, User
from syllabus.models.schemas import IntakeData
from syllabus.pipeline.graph import stream_pipeline, STREAM_MESSAGES

router = APIRouter(prefix="/v1", tags=["generate"])


def _run_streaming_job_sync(payload: dict, sync_queue: queue.Queue) -> None:
    """Run pipeline in a thread; put node names then ('__done__', result) to sync_queue."""
    try:
        def callback(node_name: str, state: dict) -> None:
            sync_queue.put(node_name)

        result = stream_pipeline(payload, callback=callback)
        sync_queue.put(("__done__", result))
    except Exception as exc:
        sync_queue.put(("__error__", str(exc)))


async def _run_job(job_id: str, intake: IntakeData, user_id: uuid.UUID | None = None) -> None:
    """Background task: run pipeline in thread, bridge events to async SSE queue."""
    sync_queue: queue.Queue = queue.Queue()
    payload = intake.model_dump()
    loop = asyncio.get_running_loop()

    thread = threading.Thread(
        target=_run_streaming_job_sync,
        args=(payload, sync_queue),
        daemon=True,
    )
    thread.start()

    course_spec_dict = None

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: sync_queue.get(timeout=1.0)),
                    timeout=300.0,
                )
            except (asyncio.TimeoutError, queue.Empty):
                if not thread.is_alive():
                    break
                continue
            if isinstance(item, tuple) and item[0] == "__done__":
                course_spec_dict = item[1]
                break
            if isinstance(item, tuple) and item[0] == "__error__":
                raise RuntimeError(item[1])
            node_name = item
            msg, progress = STREAM_MESSAGES.get(node_name, ("Processing…", 50))
            await put_event(job_id, {"stage": node_name, "message": msg, "progress": progress})

        if course_spec_dict is not None:
            async with async_session_factory() as session:
                course = Course(
                    course_spec=course_spec_dict,
                    title=course_spec_dict.get("title", "Your course"),
                    job_id=job_id,
                    user_id=user_id,
                )
                session.add(course)
                await session.commit()
                await session.refresh(course)
                course_id = str(course.id)
            set_status(job_id, "done", course_id=course_id)
            await put_event(
                job_id,
                {"stage": "done", "message": "Course ready.", "progress": 100, "course_id": course_id},
            )
            await put_event(job_id, {"done": True, "course_id": course_id})
        else:
            err = "Generation failed or QA did not pass."
            set_status(job_id, "failed", error=err)
            await put_event(job_id, {"stage": "error", "message": err, "progress": 0})
            await put_event(job_id, {"done": True, "error": err})
    except Exception as e:
        set_status(job_id, "failed", error=str(e))
        await put_event(job_id, {"stage": "error", "message": str(e), "progress": 0})
        await put_event(job_id, {"done": True, "error": str(e)})
    finally:
        cleanup_job(job_id)


@router.post("/generate")
async def post_generate(intake: IntakeData, user: User = Depends(get_current_user_allowed)) -> dict:
    """Queue a generation job; return job_id. Requires auth."""
    job_id = create_job()
    asyncio.create_task(_run_job(job_id, intake, user_id=user.id))
    return {"job_id": job_id, "status": "queued"}


@router.get("/generate/{job_id}/stream")
async def stream_generate(
    job_id: str,
    user: User = Depends(get_current_user_allowed_for_stream),
) -> StreamingResponse:
    """SSE stream of progress events for the job."""

    async def event_generator():
        # Send immediately so client isn't stuck on "Connecting…" (helps with proxy buffering)
        yield f"data: {json.dumps({'stage': 'connecting', 'message': 'Connecting…', 'progress': 0})}\n\n"
        queue = get_queue(job_id)
        if queue is None:
            status = get_status(job_id)
            if status and status.get("status") == "done" and status.get("course_id"):
                yield f"data: {json.dumps({'stage': 'done', 'progress': 100, 'course_id': status['course_id']})}\n\n"
            else:
                yield f"data: {json.dumps({'error': 'Job not found or expired'})}\n\n"
            return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'error': 'Timeout'})}\n\n"
                break
            if event.get("done"):
                yield f"data: {json.dumps(event)}\n\n"
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
