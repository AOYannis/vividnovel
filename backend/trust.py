"""Trust score model — bidirectional, temperament-aware, drives level transitions.

The *level* (0-5: stranger→lover) is the visible relationship grade. The *trust*
score is a continuous backing number that accumulates as the player behaves well
(or poorly) toward a character. Trust crossing certain thresholds nudges the
level up; trust dropping far enough nudges the level down.

The mood-based per-scene level bumps in `story_engine` still act as a FLOOR
(if a kiss happens, level >= 2 immediately) — trust just provides a softer,
bidirectional pressure on top.
"""
from __future__ import annotations

# Trust thresholds per level (cumulative, monotone-increasing). At trust ≥
# threshold[N], the character is at level N. Levels 0..5 mirror the existing
# rel.level vocabulary (stranger → acquaintance → flirting → close → intimate
# → lover).
_LEVEL_THRESHOLDS: dict[int, float] = {
    0: 0.0,
    1: 1.0,    # acquaintance — one good interaction
    2: 4.0,    # flirting — sustained interest
    3: 9.0,    # close — emotional intimacy earned
    4: 16.0,   # intimate — physical intimacy + sustained good behaviour
    5: 26.0,   # lover — long-term, established
}

# Per-temperament curve. Each multiplier is applied at the appropriate stage:
#   pos_mult  → applied to positive deltas before adding (wild trusts faster)
#   neg_mult  → applied to negative deltas before adding (reserved hurts more)
#   thresh    → applied to the level thresholds (wild lowers them, reserved raises)
_TEMPERAMENT: dict[str, dict[str, float]] = {
    "wild":     {"pos_mult": 1.5, "neg_mult": 0.7, "thresh": 0.7},
    "normal":   {"pos_mult": 1.0, "neg_mult": 1.0, "thresh": 1.0},
    "reserved": {"pos_mult": 0.7, "neg_mult": 1.3, "thresh": 1.4},
}


def _curve(temperament: str) -> dict[str, float]:
    return _TEMPERAMENT.get(temperament or "normal") or _TEMPERAMENT["normal"]


def apply_trust_delta(rel: dict, delta: int, temperament: str, *, reason: str = "") -> dict:
    """Mutate `rel` in place: applies `delta` (with temperament curve) to
    `rel['trust']` and recomputes `rel['level']`. The level NEVER drops below
    a per-scene mood-based floor (`rel['scene_mood_floor_level']`), so an
    intimate scene still locks in level 4 even if trust dips.

    Returns a small dict describing what happened (for logging / debug):
      {applied_delta, new_trust, new_level, level_change, reason}
    """
    curve = _curve(temperament)
    raw = float(delta)
    if raw > 0:
        applied = raw * curve["pos_mult"]
    elif raw < 0:
        applied = raw * curve["neg_mult"]
    else:
        applied = 0.0

    prev_trust = float(rel.get("trust", 0.0) or 0.0)
    new_trust = prev_trust + applied
    rel["trust"] = round(new_trust, 2)

    prev_level = int(rel.get("level", 0) or 0)
    floor_level = int(rel.get("scene_mood_floor_level", 0) or 0)

    # Level derived from trust against per-temperament thresholds.
    threshold_mult = curve["thresh"]
    derived_level = 0
    for lvl, base_thr in _LEVEL_THRESHOLDS.items():
        if new_trust >= base_thr * threshold_mult:
            derived_level = lvl

    # Final level: max(derived, mood floor) — mood-based bumps always win
    # because they reflect things that PHYSICALLY happened on screen.
    new_level = max(derived_level, floor_level)
    rel["level"] = new_level

    return {
        "applied_delta": round(applied, 2),
        "raw_delta": delta,
        "new_trust": rel["trust"],
        "new_level": new_level,
        "level_change": new_level - prev_level,
        "reason": reason,
    }


def record_scene_mood_floor(rel: dict, mood_floor: int) -> None:
    """Lock in a non-decreasing `scene_mood_floor_level`. Used by the engine's
    per-scene mood logic so that an intimate scene at level 4 is preserved
    even if the trust score wouldn't justify it yet (mechanical reality wins
    over score-based extrapolation)."""
    prev = int(rel.get("scene_mood_floor_level", 0) or 0)
    rel["scene_mood_floor_level"] = max(prev, int(mood_floor or 0))
    # Also bump level itself so display never lags behind the floor.
    rel["level"] = max(int(rel.get("level", 0) or 0), rel["scene_mood_floor_level"])


def thresholds_for(temperament: str) -> dict[int, float]:
    """Return the trust thresholds adjusted for this temperament — useful for
    debug UIs ("level 3 unlocks at trust 12.6 for reserved nesra")."""
    mult = _curve(temperament)["thresh"]
    return {lvl: round(base * mult, 1) for lvl, base in _LEVEL_THRESHOLDS.items()}
