"""Shared prompt fragments for pipeline nodes (PRD Addendum Section A: Prompting Architecture)."""

# P1: Pedagogy in architecture — preamble for all nodes
PEDAGOGY_PREAMBLE = """You operate within an educational pipeline governed by: (1) prerequisite ordering — no concept appears before its dependencies are covered, (2) cognitive load management — max one new concept layer per lesson, (3) active recall integration — every lesson must create opportunities for retrieval practice, (4) objective alignment — every piece of content must serve the stated end-state."""


def learner_objective_line(target_end_state: str) -> str:
    """P2: First line of context for downstream nodes."""
    if not (target_end_state and target_end_state.strip()):
        return ""
    return f"LEARNER OBJECTIVE: {target_end_state.strip()}\n\n"
