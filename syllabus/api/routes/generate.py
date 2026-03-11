"""POST /v1/generate and GET /v1/generate/{job_id}/stream (SSE) — F-016 progressive delivery."""

import asyncio
import json
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from syllabus.api.deps import get_current_user_allowed, get_current_user_allowed_for_stream
from syllabus.api.job_store import (
    cleanup_job,
    create_job,
    get_queue,
    get_status,
    put_event,
    set_job_task,
    set_status,
)
from syllabus.db.database import async_session_factory
from syllabus.db.models import Course, User
from syllabus.models.schemas import IntakeData
from syllabus.pipeline.graph import STREAM_MESSAGES, stream_pipeline_progressive

router = APIRouter(prefix="/v1", tags=["generate"])


def _build_skeleton_spec(intake: IntakeData, outline_modules: list[dict]) -> dict:
    """Build a skeleton CourseSpec dict from outline data with empty lesson content."""
    modules = []
    for mod in outline_modules:
        lessons = []
        for les in mod.get("lessons", []):
            lessons.append({
                "id": les["id"],
                "title": les["title"],
                "objective": les.get("objective", ""),
                "blocks": [],
                "key_takeaways": [],
                "knowledge_type": "declarative",
                "emotional_sensitivity_level": "low",
                "flashcards": [],
                "quiz": None,
            })
        modules.append({
            "id": mod["id"],
            "title": mod["title"],
            "objective": mod.get("objective", ""),
            "lessons": lessons,
        })

    title = modules[0]["title"] if len(modules) == 1 else "Your fertility learning course"

    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "intake": intake.model_dump(),
        "modules": modules,
        "metadata": {
            "pipeline_version": "0.1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_versions": {},
        },
    }


async def _run_job(
    job_id: str,
    intake: IntakeData,
    user_id: uuid.UUID | None = None,
    course_id: str | None = None,
) -> None:
    """Background task: run progressive pipeline, bridge events to async SSE queue."""
    sync_q: queue.Queue = queue.Queue()
    payload = intake.model_dump()
    loop = asyncio.get_running_loop()
    start_time = time.time()

    thread = threading.Thread(
        target=stream_pipeline_progressive,
        args=(payload, sync_q),
        daemon=True,
    )
    thread.start()

    total_lessons = 0
    completed_count = 0

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: sync_q.get(timeout=1.0)),
                    timeout=300.0,
                )
            except (asyncio.TimeoutError, queue.Empty):
                if not thread.is_alive():
                    break
                continue

            if isinstance(item, tuple) and item[0] == "__done__":
                course_spec_dict = item[1]
                elapsed_ms = int((time.time() - start_time) * 1000)
                if course_id:
                    async with async_session_factory() as session:
                        c = await session.get(Course, uuid.UUID(course_id))
                        if c:
                            c.course_spec = course_spec_dict
                            c.title = course_spec_dict.get("title", "Your course")
                            c.generation_status = "complete"
                            await session.commit()
                set_status(job_id, "done", course_id=course_id)
                await put_event(job_id, {
                    "event": "generation_complete",
                    "course_id": course_id,
                    "total_lessons": total_lessons,
                    "generation_time_ms": elapsed_ms,
                })
                await put_event(job_id, {"done": True, "course_id": course_id})
                break

            elif isinstance(item, tuple) and item[0] == "__error__":
                raise RuntimeError(item[1])

            elif isinstance(item, tuple) and item[0] == "node":
                node_name = item[1]
                msg, progress = STREAM_MESSAGES.get(node_name, ("Processing…", 50))
                await put_event(job_id, {
                    "event": node_name,
                    "stage": node_name,
                    "message": msg,
                    "progress": progress,
                })

            elif isinstance(item, tuple) and item[0] == "outline_ready":
                outline_modules = item[1]
                total_lessons = sum(len(m["lessons"]) for m in outline_modules)
                if course_id:
                    skeleton_spec = _build_skeleton_spec(intake, outline_modules)
                    async with async_session_factory() as session:
                        c = await session.get(Course, uuid.UUID(course_id))
                        if c:
                            c.course_spec = skeleton_spec
                            c.title = skeleton_spec.get("title", "Your course")
                            await session.commit()
                await put_event(job_id, {
                    "event": "outline_ready",
                    "course_id": course_id,
                    "modules": outline_modules,
                    "progress": 25,
                })

            elif isinstance(item, tuple) and item[0] == "lesson_ready":
                _, mod_idx, les_idx, lesson_dict = item
                completed_count += 1
                progress = 25 + int(65 * completed_count / max(total_lessons, 1))
                if course_id:
                    async with async_session_factory() as session:
                        c = await session.get(Course, uuid.UUID(course_id))
                        if c and c.course_spec:
                            spec = dict(c.course_spec)
                            modules = list(spec.get("modules", []))
                            if mod_idx < len(modules):
                                mod = dict(modules[mod_idx])
                                lessons = list(mod.get("lessons", []))
                                if les_idx < len(lessons):
                                    lessons[les_idx] = lesson_dict
                                    mod["lessons"] = lessons
                                    modules[mod_idx] = mod
                                    spec["modules"] = modules
                                    c.course_spec = spec
                                    await session.commit()
                await put_event(job_id, {
                    "event": "lesson_ready",
                    "course_id": course_id,
                    "module_index": mod_idx,
                    "lesson_index": les_idx,
                    "lesson": lesson_dict,
                    "progress": progress,
                })

    except Exception as e:
        if course_id:
            status = "partial" if completed_count > 0 else "failed"
            async with async_session_factory() as session:
                c = await session.get(Course, uuid.UUID(course_id))
                if c:
                    c.generation_status = status
                    await session.commit()
        set_status(job_id, "failed", error=str(e))
        await put_event(job_id, {"event": "error", "stage": "error", "message": str(e), "progress": 0})
        await put_event(job_id, {"done": True, "error": str(e)})
    finally:
        cleanup_job(job_id)


@router.post("/generate")
async def post_generate(
    intake: IntakeData,
    user: Annotated[User, Depends(get_current_user_allowed)],
) -> dict:
    """Queue a generation job; create course skeleton immediately. Returns job_id + course_id."""
    async with async_session_factory() as session:
        course = Course(
            course_spec={"modules": []},
            title="Generating your course...",
            user_id=user.id,
            generation_status="generating",
        )
        session.add(course)
        await session.commit()
        await session.refresh(course)
        course_id = str(course.id)

    job_id = create_job()

    async with async_session_factory() as session:
        c = await session.get(Course, course.id)
        if c:
            c.job_id = job_id
            await session.commit()

    task = asyncio.create_task(_run_job(job_id, intake, user_id=user.id, course_id=course_id))
    set_job_task(job_id, task)
    set_status(job_id, "queued", course_id=course_id)
    return {"job_id": job_id, "course_id": course_id, "status": "queued"}


@router.get("/generate/{job_id}/stream")
async def stream_generate(
    job_id: str,
    user: Annotated[User, Depends(get_current_user_allowed_for_stream)],
) -> StreamingResponse:
    """SSE stream of progressive generation events for the job."""

    async def event_generator():
        yield f"data: {json.dumps({'event': 'connecting', 'stage': 'connecting', 'message': 'Connecting…', 'progress': 0})}\n\n"
        q = get_queue(job_id)
        if q is None:
            status = get_status(job_id)
            if status and status.get("status") == "done" and status.get("course_id"):
                yield f"data: {json.dumps({'event': 'generation_complete', 'stage': 'done', 'progress': 100, 'course_id': status['course_id']})}\n\n"
                yield f"data: {json.dumps({'done': True, 'course_id': status['course_id']})}\n\n"
            else:
                yield f"data: {json.dumps({'error': 'Job not found or expired'})}\n\n"
            return
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=120.0)
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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
