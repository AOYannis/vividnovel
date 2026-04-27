"""Server-side presence gating for slice-of-life mode (Phase 3D follow-up).

Same pattern as `mood_gate.py`: the slice prompt tells the narrator who is
allowed to appear (the resolver's `present_characters` list, possibly capped
for early sequences), but Grok 4.1 Fast routinely ignores that rule and pulls
extra cast members in for narrative convenience.

This module enforces the rule in Python by stripping cast codenames from
`actors_present` when they are NOT in the resolver's allowed list. Stripped
characters lose their LoRA load, relationship update, and character-name lock
for that scene — they become anonymous in the image (specialist composes them
from the scene_summary text instead, like any non-cast NPC).

Pool actors (LoRA-backed but not in the session cast) and unknown codenames
pass through unchanged — the narrator is free to introduce pool members at
any sequence.
"""
from __future__ import annotations


def gate_presence(
    actors_present: list[str],
    *,
    cast_codes: list[str],
    allowed_cast: list[str] | None,
    enforce: bool,
) -> tuple[list[str], list[str]]:
    """Filter `actors_present` against the slice presence rules.

    Args:
        actors_present: codenames the narrator put on the current scene.
        cast_codes: the session's cast codenames (gate target — only these
            can be stripped; pool/unknown codenames always pass through).
        allowed_cast: cast codenames currently allowed in scene (typically
            the engine's resolved+capped `present_characters`). `None` means
            no enforcement (classic mode).
        enforce: master switch — when False, returns input unchanged. Used
            so the engine can disable the gate by config if needed.

    Returns:
        (filtered_actors, removed_codenames). The narrator's text may still
        mention removed characters; the gate only affects which LoRAs load
        and which relationship/lock state updates fire.
    """
    if not enforce or allowed_cast is None:
        return list(actors_present), []
    cast_set = set(cast_codes)
    allowed_set = set(allowed_cast)
    kept: list[str] = []
    removed: list[str] = []
    for code in actors_present:
        if not code:
            continue
        if code in cast_set and code not in allowed_set:
            removed.append(code)
        else:
            kept.append(code)
    return kept, removed
