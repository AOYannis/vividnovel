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
# 0 = STRANGER (just met this scene), 1 = ACQUAINTANCE, 2 = FLIRTING,
# 3 = CLOSE, 4 = INTIMATE, 5 = LOVER.
#
# These thresholds were tuned DOWN after the original values created a Catch-22:
# the relationship only levels up when intimate moods fire, but intimate moods
# only fire above a high level. So the gate now blocks ONLY the most absurd
# jumps (e.g. missionary at level 0 = first time you cross paths). Anything
# above acquaintance (level 1) is permitted — the narrator already knows the
# relationship state from the prompt and is the primary judge of pacing.
_MOOD_MIN_LEVEL: dict[str, int] = {
    "neutral": 0,
    "sensual_tease": 0,
    "kiss": 1,
    "explicit_mystic": 1,
    "blowjob": 1,
    "blowjob_closeup": 1,
    "cunnilingus": 1,
    "cunnilingus_from_behind": 1,
    "missionary": 1,
    "cowgirl": 1,
    "reverse_cowgirl": 1,
    "doggystyle": 1,
    "spooning": 1,
    "standing_sex": 1,
    "anal_doggystyle": 2,
    "anal_missionary": 2,
    "anal_missionary_shemale": 2,
    "cumshot_face": 2,
    "titjob": 1,
    "handjob": 1,
    "futa_shemale": 2,
}

# Per-level safe fallback when the requested mood is too explicit.
_LEVEL_FALLBACK: dict[int, str] = {
    0: "sensual_tease",
    1: "kiss",
    2: "explicit_mystic",
    3: "explicit_mystic",
    4: "explicit_mystic",
    5: "explicit_mystic",
}


# Auto-promote: when the narrator picks `neutral` but the scene_summary clearly
# describes a position, lift the mood to that position. Catches the case where
# the narrator is over-cautious about the gate and defaults to neutral while
# writing explicit prose. Order matters — first match wins (most specific first).
_SUMMARY_MOOD_HINTS: list[tuple[str, str]] = [
    # Anal positions (check before missionary/doggystyle so "anal missionary" wins)
    ("anal doggystyle", "anal_doggystyle"),
    ("anal missionary", "anal_missionary"),
    ("anal ", "anal_doggystyle"),
    # Specific positions
    ("cunnilingus from behind", "cunnilingus_from_behind"),
    ("cunnilingus", "cunnilingus"),
    ("blowjob close", "blowjob_closeup"),
    ("blowjob", "blowjob"),
    ("titjob", "titjob"),
    ("handjob", "handjob"),
    ("missionary", "missionary"),
    ("reverse cowgirl", "reverse_cowgirl"),
    ("cowgirl", "cowgirl"),
    ("doggystyle", "doggystyle"),
    ("doggy style", "doggystyle"),
    ("spooning", "spooning"),
    ("standing sex", "standing_sex"),
    ("cumshot", "cumshot_face"),
    # Soft / facial close-ups
    (" kiss", "kiss"),
    ("kissing", "kiss"),
    ("french kiss", "kiss"),
]


def infer_mood_from_summary(scene_summary: str, requested_mood: str) -> str | None:
    """If the narrator picked `neutral` but `scene_summary` clearly mentions a
    position keyword, return the matching mood name. Otherwise return None.

    Only fires when requested is neutral — when the narrator picked something
    explicit, we trust them.
    """
    if requested_mood and requested_mood != "neutral":
        return None
    if not scene_summary:
        return None
    text = scene_summary.lower()
    for needle, mood in _SUMMARY_MOOD_HINTS:
        if needle in text:
            return mood
    return None


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
