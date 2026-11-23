"""GET /v1/course/{id}, GET /v1/courses, progress and feedback."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from syllabus.api.deps import get_current_user_allowed, get_db
from syllabus.db.models import Course, Progress, User, UserCourseState

router = APIRouter(prefix="/v1", tags=["course"])

_COURSE_NOT_FOUND = "Course not found"


async def _get_user_course(session: AsyncSession, course_id: UUID, user_id: UUID) -> Course:
    """Fetch a course owned by the user, raising 404 if not found."""
    result = await session.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    course = result.scalars().first()
    if course is None:
        raise HTTPException(status_code=404, detail=_COURSE_NOT_FOUND)
    return course


async def _get_or_create_progress(
    session: AsyncSession, user_id: UUID, course_id: UUID, lesson_id: UUID
) -> Progress:
    """Get existing progress row or create a new one."""
    progress_result = await session.execute(
        select(Progress).where(
            Progress.user_id == user_id,
            Progress.course_id == course_id,
            Progress.lesson_id == lesson_id,
        )
    )
    progress = progress_result.scalars().first()
    if progress:
        return progress
    progress = Progress(user_id=user_id, course_id=course_id, lesson_id=lesson_id)
    session.add(progress)
    return progress


async def _upsert_course_state(
    session: AsyncSession, user_id: UUID, course_id: UUID, last_lesson_index: int
) -> None:
    """Update or create UserCourseState for resume position."""
    state_result = await session.execute(
        select(UserCourseState).where(
            UserCourseState.user_id == user_id,
            UserCourseState.course_id == course_id,
        )
    )
    state = state_result.scalars().first()
    if state:
        state.last_lesson_index = last_lesson_index
    else:
        session.add(
            UserCourseState(
                user_id=user_id, course_id=course_id, last_lesson_index=last_lesson_index
            )
        )


def _total_lessons(course_spec: dict) -> int:
    modules = course_spec.get("modules") or []
    return sum(len(m.get("lessons") or []) for m in modules)


@router.get("/courses")
async def list_courses(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_allowed)],
) -> list[dict]:
    """List current user's courses with completion %."""
    result = await session.execute(
        select(Course).where(Course.user_id == user.id).order_by(Course.created_at.desc())
    )
    courses = result.scalars().all()
    out = []
    for c in courses:
        total = _total_lessons(c.course_spec)
        count_result = await session.execute(
            select(func.count(Progress.id)).where(
                Progress.user_id == user.id,
                Progress.course_id == c.id,
                Progress.completed_at.isnot(None),
            )
        )
        completed = count_result.scalar() or 0
        pct = round(100 * completed / total, 0) if total else 0
        out.append(
            {
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "completion_pct": int(pct),
                "generation_status": getattr(c, "generation_status", "complete"),
            }
        )
    return out


@router.get("/course/{course_id}", responses={404: {"description": _COURSE_NOT_FOUND}})
async def get_course(
    course_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_allowed)],
) -> dict:
    """Return CourseSpec JSON for the course. User must own the course."""
    course = await _get_user_course(session, course_id, user.id)
    spec = dict(course.course_spec)
    spec["generation_status"] = getattr(course, "generation_status", "complete")
    spec["job_id"] = course.job_id
    return spec


@router.get("/course/{course_id}/progress", responses={404: {"description": _COURSE_NOT_FOUND}})
async def get_course_progress(
    course_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_allowed)],
) -> dict:
    """Return completed lesson ids and last_lesson_index for resume."""
    await _get_user_course(session, course_id, user.id)
    progress_result = await session.execute(
        select(Progress.lesson_id).where(
            Progress.user_id == user.id,
            Progress.course_id == course_id,
            Progress.completed_at.isnot(None),
        )
    )
    completed_lesson_ids = [str(r) for r in progress_result.scalars().all()]
    state_result = await session.execute(
        select(UserCourseState).where(
            UserCourseState.user_id == user.id,
            UserCourseState.course_id == course_id,
        )
    )
    state = state_result.scalars().first()
    last_lesson_index = state.last_lesson_index if state else 0
    return {"completed_lesson_ids": completed_lesson_ids, "last_lesson_index": last_lesson_index}


class CompleteBody(BaseModel):
    last_lesson_index: int | None = None


class StateUpdateBody(BaseModel):
    last_lesson_index: int


class FeedbackBody(BaseModel):
    feedback: str  # "up", "down", or free text


@router.post(
    "/course/{course_id}/lesson/{lesson_id}/complete",
    responses={404: {"description": _COURSE_NOT_FOUND}},
)
async def complete_lesson(
    course_id: UUID,
    lesson_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_allowed)],
    body: CompleteBody | None = None,
) -> dict:
    """Record lesson completed; optionally update last_lesson_index for resume."""
    await _get_user_course(session, course_id, user.id)
    progress = await _get_or_create_progress(session, user.id, course_id, lesson_id)
    if progress.completed_at is None:
        progress.completed_at = datetime.now(timezone.utc)
    if body and body.last_lesson_index is not None:
        await _upsert_course_state(session, user.id, course_id, body.last_lesson_index)
    await session.commit()
    return {"ok": True}


@router.post(
    "/course/{course_id}/lesson/{lesson_id}/feedback",
    responses={404: {"description": _COURSE_NOT_FOUND}},
)
async def post_lesson_feedback(
    course_id: UUID,
    lesson_id: UUID,
    body: FeedbackBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_allowed)],
) -> dict:
    """Store thumbs or free-text feedback for a lesson."""
    await _get_user_course(session, course_id, user.id)
    progress = await _get_or_create_progress(session, user.id, course_id, lesson_id)
    progress.feedback = body.feedback
    await session.commit()
    return {"ok": True}


@router.put(
    "/course/{course_id}/state",
    responses={404: {"description": _COURSE_NOT_FOUND}},
)
async def update_course_state(
    course_id: UUID,
    body: StateUpdateBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_allowed)],
) -> dict:
    """Update last_lesson_index for resume position."""
    await _get_user_course(session, course_id, user.id)
    await _upsert_course_state(session, user.id, course_id, body.last_lesson_index)
    await session.commit()
    return {"ok": True}
