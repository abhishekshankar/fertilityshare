"""GET /v1/course/{id}, GET /v1/courses, progress and feedback."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from syllabus.api.deps import get_current_user_allowed, get_db
from syllabus.db.models import Course, Progress, User, UserCourseState

router = APIRouter(prefix="/v1", tags=["course"])


def _total_lessons(course_spec: dict) -> int:
    modules = course_spec.get("modules") or []
    return sum(len(m.get("lessons") or []) for m in modules)


@router.get("/courses")
async def list_courses(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_allowed),
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
            }
        )
    return out


@router.get("/course/{course_id}")
async def get_course(
    course_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_allowed),
) -> dict:
    """Return CourseSpec JSON for the course. User must own the course."""
    result = await session.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    course = result.scalars().first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course.course_spec


@router.get("/course/{course_id}/progress")
async def get_course_progress(
    course_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_allowed),
) -> dict:
    """Return completed lesson ids and last_lesson_index for resume."""
    result = await session.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    course = result.scalars().first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
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


@router.post("/course/{course_id}/lesson/{lesson_id}/complete")
async def complete_lesson(
    course_id: UUID,
    lesson_id: UUID,
    body: CompleteBody | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_allowed),
) -> dict:
    """Record lesson completed; optionally update last_lesson_index for resume."""
    result = await session.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    course = result.scalars().first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    progress_result = await session.execute(
        select(Progress).where(
            Progress.user_id == user.id,
            Progress.course_id == course_id,
            Progress.lesson_id == lesson_id,
        )
    )
    progress = progress_result.scalars().first()
    now = datetime.now(timezone.utc)
    if progress:
        if progress.completed_at is None:
            progress.completed_at = now
    else:
        progress = Progress(
            user_id=user.id,
            course_id=course_id,
            lesson_id=lesson_id,
            completed_at=now,
        )
        session.add(progress)
    if body and body.last_lesson_index is not None:
        state_result = await session.execute(
            select(UserCourseState).where(
                UserCourseState.user_id == user.id,
                UserCourseState.course_id == course_id,
            )
        )
        state = state_result.scalars().first()
        if state:
            state.last_lesson_index = body.last_lesson_index
        else:
            state = UserCourseState(
                user_id=user.id,
                course_id=course_id,
                last_lesson_index=body.last_lesson_index,
            )
            session.add(state)
    await session.commit()
    return {"ok": True}


@router.post("/course/{course_id}/lesson/{lesson_id}/feedback")
async def post_lesson_feedback(
    course_id: UUID,
    lesson_id: UUID,
    body: FeedbackBody,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_allowed),
) -> dict:
    """Store thumbs or free-text feedback for a lesson."""
    result = await session.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    course = result.scalars().first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    progress_result = await session.execute(
        select(Progress).where(
            Progress.user_id == user.id,
            Progress.course_id == course_id,
            Progress.lesson_id == lesson_id,
        )
    )
    progress = progress_result.scalars().first()
    if progress:
        progress.feedback = body.feedback
    else:
        progress = Progress(
            user_id=user.id,
            course_id=course_id,
            lesson_id=lesson_id,
            completed_at=None,
            feedback=body.feedback,
        )
        session.add(progress)
    await session.commit()
    return {"ok": True}


@router.put("/course/{course_id}/state")
async def update_course_state(
    course_id: UUID,
    body: StateUpdateBody,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_allowed),
) -> dict:
    """Update last_lesson_index for resume position."""
    result = await session.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    if result.scalars().first() is None:
        raise HTTPException(status_code=404, detail="Course not found")
    state_result = await session.execute(
        select(UserCourseState).where(
            UserCourseState.user_id == user.id,
            UserCourseState.course_id == course_id,
        )
    )
    state = state_result.scalars().first()
    if state:
        state.last_lesson_index = body.last_lesson_index
    else:
        state = UserCourseState(
            user_id=user.id,
            course_id=course_id,
            last_lesson_index=body.last_lesson_index,
        )
        session.add(state)
    await session.commit()
    return {"ok": True}
