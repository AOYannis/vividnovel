"""Server-side mood gating (Phase 3C).

The narrator picks a mood name for each scene, but the prompt only carries a
*reminder* of the relationship-level rule. This module enforces that rule in
Python so the LLM can't accidentally jump from STRANGER to a missionary close-up.

If the requested mood is not allowed at the highest current relationship level
across the actors in the scene, we DOWNGRADE to the most permissive mood that
IS allowed for that level. The downgrade is logged so behaviour is auditable.
"""
from __future__ import annotations

# Mood → minimum relationship level required.
# 0 = STRANGER, 1 = ACQUAINTANCE, 2 = FLIRTING, 3 = CLOSE, 4 = INTIMATE, 5 = LOVER
_MOOD_MIN_LEVEL: dict[str, int] = {
    "neutral": 0,
    "sensual_tease": 2,
    "kiss": 2,
    "explicit_mystic": 3,
    "blowjob": 3,
    "blowjob_closeup": 3,
    "cunnilingus": 3,
    "cunnilingus_from_behind": 3,
    "missionary": 3,
    "cowgirl": 3,
    "reverse_cowgirl": 3,
    "doggystyle": 3,
    "spooning": 3,
    "standing_sex": 3,
    "anal_doggystyle": 4,
    "anal_missionary": 4,
    "anal_missionary_shemale": 4,
    "cumshot_face": 4,
    "titjob": 3,
    "handjob": 3,
    "futa_shemale": 4,
}

# Per-level safe fallback when the requested mood is too explicit.
_LEVEL_FALLBACK: dict[int, str] = {
    0: "neutral",
    1: "neutral",
    2: "sensual_tease",
    3: "kiss",
    4: "explicit_mystic",
    5: "explicit_mystic",
}


def _scene_max_level(actors_present: list[str], relationships: dict | None) -> int:
    """Highest relationship level among the actors in this scene. No actors
    or no relationships data → treat as stranger (level 0)."""
    if not actors_present or not relationships:
        return 0
    max_level = 0
    for code in actors_present:
        rel = relationships.get(code) or {}
        try:
            lvl = int(rel.get("level", 0) or 0)
        except (TypeError, ValueError):
            lvl = 0
        if lvl > max_level:
            max_level = lvl
    return max_level


def gate_mood(mood_name: str, actors_present: list[str], relationships: dict | None) -> tuple[str, bool]:
    """Validate a requested mood against current relationship state.

    Returns (resolved_mood, was_downgraded). `was_downgraded` is True when the
    requested mood was rejected by the gate and replaced with a safe fallback
    — callers can log this for auditability.
    """
    requested = (mood_name or "neutral").strip() or "neutral"
    min_level = _MOOD_MIN_LEVEL.get(requested)
    # Unknown mood: leave it alone, the runtime will treat it as neutral anyway.
    if min_level is None:
        return requested, False
    scene_level = _scene_max_level(actors_present, relationships)
    if scene_level >= min_level:
        return requested, False
    fallback = _LEVEL_FALLBACK.get(scene_level, "neutral")
    return fallback, True
