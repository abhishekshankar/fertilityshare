"""IntentNode: parse raw intake into structured ParsedIntake (PRD T-001, Addendum P1/P2)."""

import json
import os
import re

from langchain_openai import ChatOpenAI

from syllabus.models.schemas import ParsedIntake
from syllabus.pipeline.prompts import PEDAGOGY_PREAMBLE


# Sanitize to reduce prompt injection (PRD 3.3 edge cases)
def _sanitize(text: str, max_len: int = 2000) -> str:
    if not text or not isinstance(text, str):
        return ""
    # Strip control chars and truncate
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def _parse_from_dict(data: dict) -> ParsedIntake:
    """Build ParsedIntake from a structured dict (e.g. API request)."""
    level = (data.get("level") or "beginner").lower()
    if level not in ("beginner", "intermediate", "advanced"):
        level = "beginner"
    target_end_state = _sanitize(str(data.get("target_end_state", "")), 200)
    return ParsedIntake(
        journey_stage=_sanitize(str(data.get("journey_stage", "")), 500),
        diagnosis=_sanitize(str(data.get("diagnosis") or ""), 200) or None,
        confusion=_sanitize(str(data.get("confusion", "")), 1000),
        level=level,
        target_end_state=target_end_state,
    )


def _parse_from_text(text: str, llm: ChatOpenAI | None = None) -> ParsedIntake:
    """Use LLM to extract structured intake from free text (P2: includes target_end_state)."""
    text = _sanitize(text, 2000)
    if not llm:
        llm = ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL_INTENT", "gpt-4o-mini"),
            temperature=0,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    prompt = f"""{PEDAGOGY_PREAMBLE}

You are a fertility education intake parser. Extract structured fields from the following patient message.
Output ONLY valid JSON with exactly these keys: journey_stage, diagnosis (string or null), confusion, level, target_end_state.
- journey_stage: one of: "Newly diagnosed", "Preparing for first IUI", "Preparing for first IVF", "After failed cycle / veteran", "Considering egg freezing", "Partner supporting someone", "I don't know yet"
- diagnosis: e.g. "PCOS", "low AMH", "MFI", "unexplained", or null if unknown
- confusion: their main question or confusion in their words (short)
- level: one of "beginner", "intermediate", "advanced"
- target_end_state: one sentence (under 50 words) describing what the learner will be able to do or understand by the end of this course. Example: "By the end of this course, you will be able to explain your IVF protocol options to your partner and ask informed questions at your next RE consultation."

Patient message:
{text}

JSON:"""
    response = llm.invoke(prompt)
    content = response.content.strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()
    data = json.loads(content)
    # Ensure target_end_state is set from LLM output
    data["target_end_state"] = _sanitize(str(data.get("target_end_state", "")), 200)
    return _parse_from_dict(data)


def run_intent(raw_intake: str | dict, llm: ChatOpenAI | None = None) -> ParsedIntake:
    """
    Parse raw intake (string or dict) into ParsedIntake.
    Sanitizes all user text to reduce prompt injection risk.
    """
    if isinstance(raw_intake, dict):
        return _parse_from_dict(raw_intake)
    return _parse_from_text(raw_intake, llm=llm)


def intent_node(state: dict) -> dict:
    """LangGraph node: state must have raw_intake."""
    raw = state.get("raw_intake")
    if raw is None:
        return {"error": "Missing raw_intake"}
    try:
        parsed = run_intent(raw)
        return {"parsed_intake": parsed, "error": None}
    except Exception as e:
        return {"error": str(e), "parsed_intake": None}
