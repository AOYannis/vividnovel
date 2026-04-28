"""Slice-of-life agent layer — Phase 2.

One-shot character state generator. Called once per cast member at game start.
Returns a CharacterState with personality, job, and a weekly schedule keyed
to the actual location IDs available in the player's chosen setting.

Cost: ~250-400 input tokens + ~150-250 output tokens per character (~$0.0001
each on Grok 4.1 Fast). For a 5-character cast: ~$0.0005 once per session.
"""
from __future__ import annotations
import json
from typing import Any

from world import CharacterState, Location


SLOT_KEYS = (
    "weekday_morning",
    "weekday_afternoon",
    "weekday_evening",
    "weekday_night",
    "weekend_morning",
    "weekend_afternoon",
    "weekend_evening",
    "weekend_night",
)


def _build_prompt(actor_data: dict, setting_label: str, locations: list[Location]) -> tuple[str, str]:
    """System + user message pair for one character. Asks for a JSON object with
    personality, job, and a week-template schedule using only the available
    location IDs."""
    loc_lines = "\n".join(
        f"- `{loc.id}` ({loc.type}): {loc.name} — {loc.description}"
        for loc in locations
    )
    description = actor_data.get("description") or actor_data.get("prompt_prefix") or ""

    sys_msg = (
        "You design a believable adult NPC for a slice-of-life dating game. "
        "Given a brief character description and a list of available city "
        "locations, you produce a compact agent profile in strict JSON. "
        "Be concrete and grounded — pick a job that makes sense, a personality "
        "that fits, and a weekly schedule that reflects how this person would "
        "actually live in this city. Never invent locations outside the provided list."
    )

    user_msg = f"""Setting: {setting_label}

Character description (visual + light context):
{description}

Available locations (use ONLY these IDs in the schedule):
{loc_lines}

Produce a JSON object with this EXACT shape (no extra keys, no markdown):
{{
  "personality": "<one sentence, max 120 chars, traits + vibe>",
  "job": "<one short noun phrase: occupation/role, max 60 chars>",
  "temperament": "<reserved | normal | wild — drives how quickly they open up to the player; reserved = slow, wild = fast>",
  "schedule": {{
    "weekday_morning":   "<location_id | a|b | free>",
    "weekday_afternoon": "<location_id | a|b | free>",
    "weekday_evening":   "<location_id | a|b | free>",
    "weekday_night":     "<location_id | a|b | free>",
    "weekend_morning":   "<location_id | a|b | free>",
    "weekend_afternoon": "<location_id | a|b | free>",
    "weekend_evening":   "<location_id | a|b | free>",
    "weekend_night":     "<location_id | a|b | free>"
  }}
}}

Schedule values:
- A single location id (e.g. "cafe_du_coin") = always there at this slot
- Two-or-three pipe-separated ids (e.g. "yoga|home") = varies day-to-day
- "free" = no fixed routine; the character may be anywhere or off-screen
  (resolver treats them as ABSENT — they appear less often, which makes
   encounters feel more meaningful).

Schedule design rules — IMPORTANT for game balance:
- Job-related slots: pin to a single location (they really go to work).
- Evening slots: prefer "free" or 2-3 piped candidates. Rarely a single
  pinned location — that makes the character predictable AND too easy to find.
  An evening "free" means the player MIGHT bump into them anywhere, but
  often won't see them at all that night → encounters feel earned.
- Night slot: usually "home", but feel free to use "free" for night-owl types.
- Aim for 2-4 "free" slots across the week. Variety matters — DON'T put
  the same location in more than 2 slots total.
- This character should NOT be findable everywhere — they should have a
  RHYTHM. The player learns it over time.

Output ONLY the JSON, no commentary."""
    return sys_msg, user_msg


def _coerce_schedule(raw: dict, valid_loc_ids: set[str]) -> dict[str, str]:
    """Validate Grok's output against the real location list. Drops invalid ids,
    coerces missing slots to 'free'."""
    out: dict[str, str] = {}
    for key in SLOT_KEYS:
        val = str(raw.get(key, "free")).strip().lower()
        if val == "free" or not val:
            out[key] = "free"
            continue
        # Filter pipe-separated entries against the valid set
        parts = [p.strip() for p in val.split("|") if p.strip()]
        kept = [p for p in parts if p in valid_loc_ids]
        out[key] = "|".join(kept) if kept else "free"
    return out


async def generate_character_state(
    grok_client,
    code: str,
    actor_data: dict,
    setting_label: str,
    locations: list[Location],
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> CharacterState:
    """Generate a CharacterState for one cast member. Falls back to an empty
    state with all slots 'free' if Grok fails — the character then never
    auto-appears, which is safe but less interesting.

    The returned state has empty today_mood / intentions; those are filled by
    Phase 5's daily tick (not yet implemented)."""
    sys_msg, user_msg = _build_prompt(actor_data, setting_label, locations)
    valid_ids = {loc.id for loc in locations}

    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.8,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"[agent] generate_character_state({code}) failed: {e}; using empty defaults")
        data = {}

    _temp = str(data.get("temperament", "")).strip().lower()
    if _temp not in ("reserved", "normal", "wild"):
        _temp = "normal"
    return CharacterState(
        code=code,
        personality=str(data.get("personality", "")).strip()[:200],
        job=str(data.get("job", "")).strip()[:80],
        schedule=_coerce_schedule(data.get("schedule", {}), valid_ids),
        temperament=_temp,
    )


async def generate_all_character_states(
    grok_client,
    cast_actors: list[tuple[str, dict]],
    setting_label: str,
    locations: list[Location],
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> dict[str, CharacterState]:
    """Legacy parallel-per-character path. Kept as a fallback. New code should
    use generate_world_and_agents() which produces locations + schedules in a
    single coherent Grok call."""
    import asyncio
    tasks = [
        generate_character_state(grok_client, code, data, setting_label, locations, grok_model)
        for code, data in cast_actors
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    states = {state.code: state for state in results}
    _deconflict_schedules(states)
    return states


# ─── Unified world + agent generator (Phase 2 — deeper fix) ───────────────

async def generate_world_and_agents(
    grok_client,
    setting_label: str,
    custom_setting_text: str,
    cast_actors: list[tuple[str, dict]],
    grok_model: str = "grok-4-1-fast-non-reasoning",
    language: str = "fr",
) -> tuple[list[Location], dict[str, CharacterState]]:
    """ONE Grok call that produces:
      1. A setting-themed location set (5-7 locations with themed names + IDs).
      2. Character schedules for the entire cast, jointly designed so:
         - Each character has a DISTINCT rhythm (different "haunts").
         - At most ONE cast member single-pins any social-evening slot per location.
         - "home" is the PLAYER's home — cast members are FORBIDDEN to schedule there.
         - Each character has 3-5 "free" slots per week (encounters feel earned).
    Returns (locations, character_states). On any failure, returns ([], {}) and
    the caller should fall back to default_world_for_setting + per-character gen.

    Cost: ~700 input + ~600 output tokens (~$0.0004) — one call replaces the
    N parallel calls of the legacy path.
    """
    if not cast_actors:
        return [], {}

    cast_summary = "\n".join(
        f"- `{code}`: {((data.get('description') or data.get('prompt_prefix') or ''))[:140]}"
        for code, data in cast_actors
    )
    cast_codes_str = ", ".join(f"`{code}`" for code, _ in cast_actors)

    # When the user supplied a custom setting, it DOMINATES — the canned setting
    # label is just a fallback. Mixing both ("Paris contemporain — New York 2026")
    # made the LLM generate Paris-themed locations even when the user wanted NYC.
    if custom_setting_text:
        setting_blurb = custom_setting_text[:400]
    else:
        setting_blurb = setting_label

    # Language for location names + descriptions. The user's narration language is
    # the truth — generating French location names for an English game broke
    # immersion (and confused Grok later when it had to use them in narration).
    lang_label = {
        "fr": "French", "en": "English", "es": "Spanish", "de": "German",
        "it": "Italian", "pt": "Portuguese", "ja": "Japanese", "ko": "Korean",
        "zh": "Chinese", "ru": "Russian", "ar": "Arabic", "tr": "Turkish",
        "nl": "Dutch", "pl": "Polish", "hi": "Hindi",
    }.get(language, "French")

    sys_msg = (
        "You design a tiny lived-in world for an interactive adult fiction game: "
        "a SETTING-FAITHFUL location set + the cast's typical whereabouts. The setting "
        "brief below is the SOURCE OF TRUTH — your locations must feel like they "
        "belong to THAT setting, not to a generic city. A manor weekend gets manor "
        "rooms. A yacht cruise gets ship areas. A pirate haven gets pirate-port "
        "places. A futurist megacity gets futurist places. Never copy locations "
        "from a different setting.\n\n"
        f"⚠️ CRITICAL: write all `name` and `description` fields in **{lang_label}** "
        f"(this is the player's language). Use names that fit the setting AND the language "
        f"(e.g. for a New York setting in English: 'Your apartment, Brooklyn' not 'Ton appart, "
        f"Brooklyn'). Setting determines the THEME; language determines the WORDING."
    )

    user_msg = f"""Setting: {setting_blurb}

Cast (codenames are TECHNICAL ids — never alter them; the in-story name is invented separately):
{cast_summary}

Produce a JSON object with this EXACT shape (no markdown, no extra keys):
{{
  "locations": [
    {{"id": "<lowercase_snake_case_id>", "name": "<themed display name>", "type": "home|cafe|bar|club|gym|park|work|salon|other", "description": "<one-line setting-specific description>"}},
    ...
  ],
  "schedules": {{
    "<character_codename>": {{
      "personality": "<one short sentence — traits + vibe>",
      "job": "<one short noun phrase>",
      "temperament": "<reserved | normal | wild — see TEMPERAMENT block>",
      "schedule": {{
        "weekday_morning":   "<location_id | a|b | free>",
        "weekday_afternoon": "<...>",
        "weekday_evening":   "<...>",
        "weekday_night":     "<...>",
        "weekend_morning":   "<...>",
        "weekend_afternoon": "<...>",
        "weekend_evening":   "<...>",
        "weekend_night":     "<...>"
      }}
    }}
  }}
}}

TEMPERAMENT — pick ONE per character (drives how quickly they open up to the player):
- `reserved`: slow to warm up, requires real seduction effort, refuses early advances. ~20-30% of cast.
- `normal`: standard pace, neither cold nor instantly available. ~50-60% of cast.
- `wild`: open, flirty, escalates quickly when interest is mutual. ~10-20% of cast.
Pick a MIX across the cast — never make all characters the same temperament.

LOCATIONS — exactly 6 locations, designed for THIS SPECIFIC SETTING:
- ⚠️ The first location MUST have id EXACTLY "home" (literal string, lowercase,
  4 letters) AND type "home". This is a TECHNICAL CONSTANT the engine relies on
  — never invent another id for it (no "your_suite", "guest_room", "cabin_a"
  etc. as the id). Its DISPLAY NAME however changes wildly with the setting:
  "Your suite at the manor", "Cabine du capitaine", "Ta capsule, niveau 47",
  "Your tent at the rented mansion", "Loge d'artiste" — pick what fits. The
  ID is a constant; the NAME is contextual.
- The other 5 locations: invent contextual ids (snake_case ASCII, must start
  with a letter, no digits as first char) like "library_west_wing", "deck_aft",
  "noodle_bar", "old_docks", "kitchen_main", "ballroom".
- DO NOT default to a generic urban-modern stack (bar + café + gym + park + club)
  unless the setting genuinely calls for it. A manor whodunnit, a yacht cruise,
  a polar expedition, an astronomical observatory all need very different sets.
- The `type` field is a loose hint for the map ICON only — pick the closest
  match from {{home, cafe, bar, club, gym, park, work, salon, other}}, or
  "other" if nothing fits. The type does NOT constrain what the place actually is.

SCHEDULES — for each character codename in {cast_codes_str}:
- "home" is FORBIDDEN as that character's location at any slot — that's the
  player's private space, off-limits to the cast. (Use "free" if unsure.)
- At most ONE cast member may single-pin (no pipe) the same location at the SAME
  evening slot ("weekday_evening" or "weekend_evening"). If two would clash, change one
  to "free" or to a multi-candidate ("a|b").
- Use "free" 3-5 slots per character per week. Predictability kills the magic.
- Anchor each character to the location that fits their role/job/habit in this
  setting (a chef = the kitchen; a captain = the bridge; a librarian = the
  library; a bartender = the bar). Pinned single id at the slot when they
  WOULD be there.
- Make schedules COHESIVE with each character's persona and the setting.
- Make schedules DIFFERENT across the cast — each character has a distinct rhythm.

Output only the JSON, no commentary."""

    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.85,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"[agent] generate_world_and_agents failed: {e}; caller should fall back")
        return [], {}

    # Validate locations
    raw_locs = data.get("locations") or []
    locations: list[Location] = []
    seen_ids: set[str] = set()
    has_home = False
    for raw_loc in raw_locs:
        if not isinstance(raw_loc, dict):
            continue
        loc_id = str(raw_loc.get("id", "")).strip().lower()
        if not loc_id or loc_id in seen_ids:
            continue
        # Sanitize id to safe characters
        loc_id = "".join(c if (c.isalnum() or c == "_") else "_" for c in loc_id)
        if not loc_id or not loc_id[0].isalpha():
            continue
        seen_ids.add(loc_id)
        if loc_id == "home":
            has_home = True
        locations.append(Location(
            id=loc_id,
            name=str(raw_loc.get("name", loc_id))[:80],
            type=str(raw_loc.get("type", "other")).lower()[:20],
            description=str(raw_loc.get("description", ""))[:200],
        ))

    # Recovery: Grok sometimes invents a contextual id ("guest_suite", "your_room")
    # for the player's home instead of the literal "home" constant the engine
    # depends on. If we have a location with type="home" but its id isn't "home",
    # rename it. Or, last resort, force the first location to be home.
    if not has_home and locations:
        for i, loc in enumerate(locations):
            if loc.type == "home":
                locations[i] = Location(id="home", name=loc.name, type="home", description=loc.description)
                seen_ids.discard(loc.id)
                seen_ids.add("home")
                has_home = True
                print(f"[agent] recovered: renamed location id '{loc.id}' → 'home' (type=home was set)")
                break
    if not has_home and locations:
        loc = locations[0]
        locations[0] = Location(id="home", name=loc.name, type="home", description=loc.description)
        seen_ids.discard(loc.id)
        seen_ids.add("home")
        has_home = True
        print(f"[agent] recovered: forced first location ('{loc.id}', type='{loc.type}') → 'home' as last-resort anchor")

    if not locations or not has_home or len(locations) < 4:
        print(f"[agent] world generation returned invalid locations ({len(locations)}, has_home={has_home})")
        # Surface what Grok returned so we can see WHY validation failed.
        print(f"[agent] raw output (first 800 chars): {raw[:800]}")
        return [], {}

    valid_loc_ids = {loc.id for loc in locations}
    valid_loc_ids_no_home = valid_loc_ids - {"home"}

    # Validate schedules — strip "home" assignments and unknown ids
    raw_schedules = data.get("schedules") or {}
    states: dict[str, CharacterState] = {}
    for code, _ in cast_actors:
        raw = raw_schedules.get(code) or {}
        if not isinstance(raw, dict):
            raw = {}
        sched_raw = raw.get("schedule") or {}
        sched: dict[str, str] = {}
        for slot in SLOT_KEYS:
            val = str(sched_raw.get(slot, "free")).strip().lower()
            if val == "free" or not val:
                sched[slot] = "free"
                continue
            parts = [p.strip() for p in val.split("|") if p.strip()]
            # Filter against valid IDs AND strip 'home' (player-only)
            kept = [p for p in parts if p in valid_loc_ids_no_home]
            sched[slot] = "|".join(kept) if kept else "free"
        _temp = str(raw.get("temperament", "")).strip().lower()
        if _temp not in ("reserved", "normal", "wild"):
            _temp = "normal"
        states[code] = CharacterState(
            code=code,
            personality=str(raw.get("personality", "")).strip()[:200],
            job=str(raw.get("job", "")).strip()[:80],
            schedule=sched,
            temperament=_temp,
        )

    # Strict deconflict pass (defence in depth — Grok should already comply)
    _deconflict_schedules(states)

    print(f"[agent] generated {len(locations)} themed locations + {len(states)} agent schedules")
    return locations, states


async def craft_map_image_prompt(
    grok_client,
    *,
    setting_label: str,
    custom_setting_text: str,
    locations: list[Location],
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> str:
    """Craft ONE Z-Image Turbo prompt that paints the world map as a stylised
    illustration — vignettes/icons of each location laid out across the canvas.
    The visual style adapts to the setting era (eg parchment for ancient, neon
    schematic for cyberpunk, watercolour travel-poster or subway map etc. for contemporary, engraved
    atlas for Belle Époque, etc.).

    Critical: NO TEXT, NO LABELS — Z-Image cannot render text reliably. Locations
    are recognised purely by their architectural silhouette and surrounding
    details, not by written names.

    Returns the prompt string, or empty string on failure (caller should skip
    map background and fall back to plain modal). Fires ONCE per game at world creation.
    """
    if not locations:
        return ""
    locs_for_prompt = "\n".join(
        f"  - {loc.name} ({loc.type}): {(loc.description or '').strip()[:140]}"
        for loc in locations
    )
    setting_blurb = (custom_setting_text or setting_label or "").strip()[:400]
    sys_msg = (
        "You craft ONE Z-Image Turbo prompt that illustrates a fictional MAP of "
        "the world for a slice-of-life story. Examples below are just for inspiration, do not take them as they are but just for ideas, fit to the actual context of the story and provided locations\n\n"
        "FORMAT: a stylised cartographic ILLUSTRATION (top-down or 3/4 isometric "
        "bird's-eye view), NOT a literal modern street map. Each named location "
        "appears as a small architectural vignette or symbolic icon arranged "
        "across the canvas, connected by paths/roads/waterways/transit lines "
        "appropriate to the setting.\n\n"
        "STYLE — pick a visual treatment that fits the era and tone:\n"
        "  - Ancient/historical/fantasy → weathered parchment with hand-drawn "
        "ink, sepia tones, compass rose, decorative cartouches\n"
        "  - Cyberpunk/futurist → neon-lit isometric schematic, holographic "
        "grid, glowing data-lines, dark base palette\n"
        "  - Modern cosy/contemporary → soft watercolour travel-poster style, "
        "warm pastels, hand-painted feel\n"
        "  - Belle Époque / 1800s → engraved atlas plate, copperplate hatching, "
        "ivory paper, ornate border\n"
        "  - Post-apocalyptic → torn cloth or scrap-metal etched map, muted, "
        "weathered\n"
        "Pick whichever fits BEST and commit to it.\n\n"
        "CRITICAL RULES:\n"
        "  - NO TEXT. NO WORDS. NO LETTERS. NO LABELS. NO SIGNAGE. NO NUMBERS. "
        "Z-Image cannot render text reliably and any attempt produces gibberish.\n"
        "  - NO PEOPLE, NO CHARACTERS, NO PORTRAITS — purely environmental.\n"
        "  - Each location is recognisable by its silhouette and surroundings "
        "only (a café = small awning + outdoor tables; a club = neon halo + "
        "queue rope; a park = trees + paths; a home = small townhouse vignette).\n\n"
        "INCLUDE: rich atmospheric detail, era-appropriate terrain and "
        "landmarks between the locations, soft vignetting, painterly texture, "
        "high-quality illustration craft.\n\n"
        "OUTPUT: ONLY the Z-Image prompt, ~80-160 words, no preamble, no "
        "labels, no quotes, no commentary."
    )
    user_msg = (
        f"Setting: {setting_blurb}\n\n"
        f"Locations to depict (as small architectural vignettes, NO labels):\n"
        f"{locs_for_prompt}\n\n"
        f"Output the Z-Image prompt:"
    )
    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Belt and suspenders: hard-suffix the no-text constraint so even if Grok
        # forgets, Z-Image gets the strongest possible negative signal.
        if text and "no text" not in text.lower():
            text = text + ", no text, no words, no letters, no labels, no signage"
        return text
    except Exception as e:
        print(f"[agent] craft_map_image_prompt failed: {e}")
        return ""


# Only EVENING slots get deconflicted. Mornings/afternoons (work) and nights
# (home) are expected to have multiple cast members at the same location —
# everyone goes to work, everyone goes home to sleep. Evenings are when the
# clustering creates the "bar full of cast" bombardment.
_DECONFLICT_SLOTS = ("weekday_evening", "weekend_evening")


def _deconflict_schedules(states: dict[str, CharacterState]) -> None:
    """When 2+ characters all single-pin to the same location at an EVENING slot,
    keep the first (deterministic by code order) and force the rest to 'free'.
    Multi-candidate slots ("a|b") are left alone — stable_choice already
    varies them per character per day. Mornings/afternoons/nights are skipped
    (work/home overlap is realistic and expected)."""
    if len(states) < 2:
        return
    codes_sorted = sorted(states.keys())
    for slot_key in _DECONFLICT_SLOTS:
        loc_to_codes: dict[str, list[str]] = {}
        for code in codes_sorted:
            spec = states[code].schedule.get(slot_key, "free")
            if spec and spec != "free" and "|" not in spec:
                loc_to_codes.setdefault(spec, []).append(code)
        for loc, chars_here in loc_to_codes.items():
            if len(chars_here) > 1:
                for c in chars_here[1:]:
                    print(f"[agent] deconflict: {c}.{slot_key} {loc} → free (overlap with {chars_here[0]})")
                    states[c].schedule[slot_key] = "free"


# ─── Whereabouts extractor (Phase 2B) ───────────────────────────────────────

SLOT_NAMES = ("morning", "afternoon", "evening", "night")


async def extract_whereabouts(
    grok_client,
    narration_text: str,
    char_codes: list[str],
    current_day: int,
    current_slot: str,
    locations: list[Location],
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> list[dict]:
    """Scan a sequence's narration for characters announcing future whereabouts
    ('I'll be at the bar tomorrow night', 'rendez-vous demain matin au café').

    Returns a list of {char, location_id, day, slot, source} entries — each one
    representing something the player has just been TOLD. Non-mentions return [].

    Cost: ~250 input + 80 output tokens per call (~$0.00006 on Grok 4.1 Fast).
    Called once at end of each sequence."""
    if not narration_text.strip() or not char_codes:
        return []
    loc_lines = "\n".join(f"- `{loc.id}`: {loc.name}" for loc in locations)
    char_codes_str = ", ".join(f"`{c}`" for c in char_codes)
    sys_msg = (
        "You read a short interactive-novel scene and extract any FUTURE-self "
        "statements characters make about where they'll be. You ALSO flag whether "
        "each is a 'rendez-vous' — a MUTUAL appointment with the player ('see you "
        "tomorrow at the bar', 'meet me at the park at 8pm') vs a one-sided "
        "whereabout ('I'll be at the gym tomorrow', 'I work at the cafe in the "
        "mornings'). When a location is mentioned that ISN'T in the existing list, "
        "you may PROPOSE a new location. Output strict JSON. Be conservative — only "
        "extract explicit statements, NOT vague hints. If nothing qualifies, return "
        "an empty array."
    )
    user_msg = f"""Current day: {current_day}, current slot: {current_slot}.

Characters in scope (only extract for these codenames):
{char_codes_str}

Available locations (use ONLY these IDs unless you propose a new one — see below):
{loc_lines}

Scene text:
{narration_text[:3000]}

Output a JSON object with key "mentions" → an array of objects:
{{
  "mentions": [
    {{
      "char": "<codename, must be in scope>",
      "location_id": "<must match an available id OR a `new_location.id` you propose below>",
      "day": <integer day number, e.g. {current_day} or {current_day + 1}>,
      "slot": "<morning|afternoon|evening|night>",
      "source": "<short verbatim quote or paraphrase, max 80 chars>",
      "is_rendezvous": <true if this is a MUTUAL appointment (player + character agree to meet), false if it is just the character announcing where they will be>,
      "new_location": null  OR  {{
        "id": "<lowercase_snake_case_id, must NOT clash with existing ids above>",
        "name": "<display name, themed to the setting>",
        "type": "<home|cafe|bar|club|gym|park|work|salon|other>",
        "description": "<one short sentence>"
      }}
    }}
  ]
}}

Rules:
- ONLY explicit statements about FUTURE plans (relative to "current day {current_day}, {current_slot}").
- A character saying where they ARE NOW does NOT count.
- A vague invitation ("on se voit bientôt") does NOT count — only specifics.
- If a relative time is mentioned ("demain", "tomorrow"), convert to absolute day number.
- "Ce soir" / "tonight" → day {current_day}, slot "evening" (only if current slot is morning/afternoon).
- If you can't pin down BOTH a location AND a day+slot, skip the mention.
- `is_rendezvous=true` ONLY when the line is a MUTUAL agreement: "Rendez-vous demain matin au café",
  "On se retrouve à 20h au bar", "Viens me voir au studio mardi", "See you at the gym tomorrow".
  The player's response/choice should imply acceptance, OR the language should be unambiguous about
  meeting the player (NOT a third-party meeting).
- `is_rendezvous=false` when it's just informational: "Je serai au boulot demain", "I work mornings at
  the cafe" — useful to know, but no commitment to meet.
- `new_location`: ONLY propose a new location when the scene mentions a SPECIFIC place that
  isn't in the existing list AND has a clear identity ("le nouveau bar du Marais Le Sphinx",
  "ma cabane à la plage de Belle-Île"). Set `location_id` to that new id. NEVER duplicate an
  existing place under a new name. NEVER propose for vague mentions ("un café", "la plage").
- Empty array if nothing qualifies. NO commentary."""

    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"[agent] extract_whereabouts failed: {e}")
        return []

    mentions = data.get("mentions") or []
    valid_chars = set(char_codes)
    valid_locs = {loc.id for loc in locations}
    cleaned: list[dict] = []
    for m in mentions:
        if not isinstance(m, dict):
            continue
        char = str(m.get("char", "")).strip()
        loc_id = str(m.get("location_id", "")).strip()
        slot = str(m.get("slot", "")).strip().lower()
        source = str(m.get("source", "")).strip()[:120]
        try:
            day = int(m.get("day", 0))
        except (TypeError, ValueError):
            continue
        if char not in valid_chars:
            continue
        # Allow location_id to refer to a NEW location proposed inline
        new_loc_payload = m.get("new_location") if isinstance(m.get("new_location"), dict) else None
        if loc_id not in valid_locs and not new_loc_payload:
            continue
        if slot not in SLOT_NAMES:
            continue
        if day < current_day:
            continue   # future-only
        entry = {
            "char": char,
            "location_id": loc_id,
            "day": day,
            "slot": slot,
            "source": source,
            "is_rendezvous": bool(m.get("is_rendezvous", False)),
        }
        if new_loc_payload:
            # Sanitise the proposed new location. Engine will register it on the
            # world before this whereabouts becomes useful.
            new_id = str(new_loc_payload.get("id", "")).strip().lower()
            new_id = "".join(c if (c.isalnum() or c == "_") else "_" for c in new_id)
            if new_id and new_id[0].isalpha() and new_id == loc_id and new_id not in valid_locs:
                entry["new_location"] = {
                    "id": new_id,
                    "name": str(new_loc_payload.get("name", new_id))[:80],
                    "type": str(new_loc_payload.get("type", "other")).lower()[:20],
                    "description": str(new_loc_payload.get("description", ""))[:200],
                }
            elif new_id != loc_id or new_id in valid_locs:
                # Mismatched / already-existing → drop the proposal but keep the
                # mention only if the loc_id is valid; otherwise skip the entry.
                if loc_id not in valid_locs:
                    continue
        cleaned.append(entry)
    return cleaned


# ─── Bidirectional trust deltas ──────────────────────────────────────────

async def extract_trust_deltas(
    grok_client,
    *,
    previous_choice: str,
    narration_text: str,
    present_chars: list[str],
    relationships: dict[str, dict],
    character_states: dict[str, "CharacterState"],
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> list[dict]:
    """Read the player's last choice + the resulting sequence narration, decide
    how each present character would feel about the player's behaviour, and
    return one trust delta per character.

    Returns a list of `{char, delta, reason}` dicts. `delta` is an INTEGER in
    `[-3..+3]` (-3 = serious betrayal/rejection, 0 = neutral, +3 = profound
    bonding moment). Empty list if nothing meaningful happened.

    Cost: ~250 input + 80 output tokens per call (~$0.00006 on Grok 4.1 Fast).
    Called once at end of each sequence where present_chars is non-empty.
    """
    if not present_chars:
        return []
    if not (narration_text or "").strip():
        return []

    char_lines = []
    for code in present_chars:
        cs = character_states.get(code)
        rel = (relationships or {}).get(code) or {}
        level = int(rel.get("level", 0) or 0)
        temp = (getattr(cs, "temperament", "normal") if cs else "normal") or "normal"
        persona = getattr(cs, "personality", "") if cs else ""
        char_lines.append(
            f"- `{code}` (level {level}, temperament `{temp}`): {persona or '(no persona)'}"
        )
    chars_block = "\n".join(char_lines)

    sys_msg = (
        "You read a short interactive-novel sequence and decide how each present "
        "character felt about the PLAYER'S behaviour during it. Output strict JSON. "
        "Be calibrated and conservative — most sequences should produce small or "
        "zero deltas. Only +3 / -3 for genuinely defining moments (a real betrayal, "
        "a real revelation, a profound act of trust). Most scenes drift in -1..+1."
    )

    user_msg = f"""Player's previous choice (what they JUST decided to do):
"{previous_choice or '(none — sequence opened cold)'}"

Resulting sequence narration:
{(narration_text or '')[:3000]}

Characters present in this sequence:
{chars_block}

For EACH character above, decide a trust delta in [-3..+3] based on what the
PLAYER said/did/chose during the sequence (NOT based on what the character did).

Calibration:
- +3: profound act of trust, vulnerability, or genuine connection. Rare.
- +2: clear positive signal (active listening, kindness, shared intimacy honoured properly).
- +1: small good moment (a compliment landed well, a thoughtful gesture).
-  0: neutral / nothing notable happened toward this character.
- -1: minor friction (distracted, dismissive, slightly self-centred).
- -2: clear bad signal (rude, broke a small confidence, emotional miss).
- -3: serious betrayal, public humiliation, broken promise. Rare.

Reason should be ONE short sentence quoting or describing the player's specific
action that triggered the delta. NEVER attribute deltas to mood/scene type alone
("they had sex, +3" is wrong — sex is mechanical, the trust comes from how the
player handled it). Focus on choices and dialogue.

Output strict JSON:
{{
  "deltas": [
    {{"char": "<codename>", "delta": <int -3..3>, "reason": "<short sentence, max 100 chars>"}}
  ]
}}

Only include characters with delta != 0. Empty array if nothing meaningful happened.
NO commentary."""

    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"[agent] extract_trust_deltas failed: {e}")
        return []

    deltas = data.get("deltas") or []
    valid_chars = set(present_chars)
    out: list[dict] = []
    for d in deltas:
        if not isinstance(d, dict):
            continue
        char = str(d.get("char", "")).strip()
        if char not in valid_chars:
            continue
        try:
            delta = int(d.get("delta", 0))
        except (TypeError, ValueError):
            continue
        if delta == 0:
            continue
        delta = max(-3, min(3, delta))
        reason = str(d.get("reason", "")).strip()[:140]
        out.append({"char": char, "delta": delta, "reason": reason})
    return out


# ─── Clothing change classifier ──────────────────────────────────────────

async def detect_clothing_changes(
    grok_client,
    *,
    scene_summary: str,
    actors_present: list[str],
    locked_clothing: dict[str, str],
    language: str = "fr",
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> set[str]:
    """Read a scene summary and decide which present actors actually changed
    their outfit IN THIS SCENE. Returns the set of codenames whose clothing
    was deliberately altered (took off, put on, undressed, naked reveal, …).

    Replaces brittle keyword matching that only worked for a fixed phrase list.
    Calls Grok 4.1 Fast with a tiny focused prompt — language-agnostic, robust
    to literary phrasing ("elle laissa glisser sa robe à terre", "her dress
    pooled around her ankles", etc.).

    Cost: ~80 input + ~30 output tokens per call (~$0.00002 each). Returns
    empty set when no actors are present or summary is empty.
    """
    if not actors_present or not (scene_summary or "").strip():
        return set()

    locked_lines: list[str] = []
    for code in actors_present:
        locked = locked_clothing.get(code, "")
        if locked:
            locked_lines.append(f"- `{code}`: currently wearing « {locked[:120]} »")
        else:
            locked_lines.append(f"- `{code}`: no locked outfit yet (first scene with them)")
    locked_block = "\n".join(locked_lines)

    sys_msg = (
        "You read a single scene description and decide whether each named character "
        "deliberately CHANGED their outfit during the scene. Output strict JSON. "
        "A change means: removing, adding, swapping, opening, tearing, or revealing "
        "clothing in a way the narrator clearly describes — including subtle literary "
        "phrasings ('her dress pooled around her ankles', 'la robe glissa au sol'). "
        "It is NOT a change if the narrator merely paraphrases the same outfit, "
        "describes movement, posture, atmosphere, or unrelated body details. "
        "Be conservative: if uncertain, return false."
    )
    user_msg = f"""Scene description (in {language}):
{scene_summary[:1000]}

Characters present + their CURRENTLY LOCKED outfit:
{locked_block}

For each character, return whether their outfit changed DURING THIS SCENE.

Output strict JSON:
{{
  "changes": [
    {{"char": "<codename>", "changed": <true|false>, "what": "<one short phrase, max 60 chars, only when changed=true>"}}
  ]
}}

Include EVERY character listed above (even when changed=false). NO commentary."""

    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"[agent] detect_clothing_changes failed: {e}")
        return set()

    out: set[str] = set()
    valid = set(actors_present)
    for c in (data.get("changes") or []):
        if not isinstance(c, dict):
            continue
        code = str(c.get("char", "")).strip()
        if code in valid and bool(c.get("changed", False)):
            out.add(code)
    return out


# ─── Phone-chat rendez-vous extractor ────────────────────────────────────

async def extract_phone_rendezvous(
    grok_client,
    *,
    player_msg: str,
    char_response: str,
    char_code: str,
    current_day: int,
    current_slot: str,
    locations: list[Location],
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> list[dict]:
    """Extract a rendez-vous from a single phone-chat exchange (one player
    message + the character's response).

    Returns the SAME shape as `extract_whereabouts` mentions:
    `[{char, location_id, day, slot, source, is_rendezvous, new_location?}]`.
    The `char` field is always `char_code` (the phone partner). `is_rendezvous`
    is always `True` here — the only kind we surface from phone exchanges is
    a mutual commitment to meet. May propose a `new_location` if a specific
    named place isn't in the existing list.

    Empty list if no clear meeting was agreed. Cost ~$0.00006 per exchange.
    """
    if not (player_msg or "").strip() or not (char_response or "").strip():
        return []
    if not char_code or not locations:
        return []
    loc_lines = "\n".join(f"- `{loc.id}`: {loc.name}" for loc in locations)

    sys_msg = (
        "You read a SHORT phone-chat exchange between the player and ONE character. "
        "Your only job: detect whether they JUST agreed to meet — a real, mutual "
        "rendez-vous with a SPECIFIC location AND a SPECIFIC time. Output strict "
        "JSON. Conservative: vague invitations ('on se voit bientôt', 'someday'), "
        "wishes, or one-sided proposals without acceptance do NOT qualify."
    )

    user_msg = f"""Current day: {current_day}, current slot: {current_slot}.
Phone partner codename: `{char_code}`

Available locations (use ONLY these IDs unless you propose a new one):
{loc_lines}

Player message: {player_msg.strip()[:500]}
Character response: {char_response.strip()[:500]}

Output JSON:
{{
  "rendezvous": null  OR  {{
    "location_id": "<existing id, or the id you propose in `new_location`>",
    "day": <integer day, e.g. {current_day} or {current_day + 1}>,
    "slot": "<morning|afternoon|evening|night>",
    "source": "<short verbatim quote (max 80 chars) showing the agreement>",
    "new_location": null OR {{"id": "<lowercase_snake_case>", "name": "<themed display name>", "type": "<home|cafe|bar|club|gym|park|work|salon|other>", "description": "<one short sentence>"}}
  }}
}}

Rules:
- ONLY emit when both messages clearly point to a meeting (e.g. player asks "café demain à 14h ?" and character says "ouais avec plaisir").
- Convert relative times ("demain", "ce soir") to absolute day+slot.
- "Ce soir" / "tonight" → day {current_day} slot evening (only when current slot is morning/afternoon).
- If you can't pin down BOTH a location AND a day+slot AND mutual consent → set `rendezvous: null`.
- `new_location` ONLY when a SPECIFIC named place is mentioned that isn't in the list above. Never for vague mentions like "un café".
- NO commentary."""

    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"[agent] extract_phone_rendezvous failed: {e}")
        return []

    rdv = data.get("rendezvous")
    if not isinstance(rdv, dict):
        return []

    valid_locs = {loc.id for loc in locations}
    loc_id = str(rdv.get("location_id", "")).strip()
    slot = str(rdv.get("slot", "")).strip().lower()
    source = str(rdv.get("source", "")).strip()[:120]
    try:
        day = int(rdv.get("day", 0))
    except (TypeError, ValueError):
        return []
    if slot not in SLOT_NAMES:
        return []
    if day < current_day:
        return []

    new_loc_payload = rdv.get("new_location") if isinstance(rdv.get("new_location"), dict) else None
    entry: dict = {
        "char": char_code,
        "location_id": loc_id,
        "day": day,
        "slot": slot,
        "source": source,
        "is_rendezvous": True,
    }
    if loc_id not in valid_locs:
        if not new_loc_payload:
            return []  # location must be valid OR a proposed new one
        new_id = str(new_loc_payload.get("id", "")).strip().lower()
        new_id = "".join(c if (c.isalnum() or c == "_") else "_" for c in new_id)
        if not new_id or not new_id[0].isalpha() or new_id != loc_id or new_id in valid_locs:
            return []
        entry["new_location"] = {
            "id": new_id,
            "name": str(new_loc_payload.get("name", new_id))[:80],
            "type": str(new_loc_payload.get("type", "other")).lower()[:20],
            "description": str(new_loc_payload.get("description", ""))[:200],
        }
    return [entry]


# ─── Daily tick (Phase 5) ─────────────────────────────────────────────────

async def daily_tick(
    grok_client,
    character_states: dict[str, CharacterState],
    relationships: dict[str, dict],
    day: int,
    setting_label: str,
    custom_setting_text: str = "",
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> dict[str, dict]:
    """Advance each cast member's inner life by one day.

    For every character whose `last_tick_day < day`, ask Grok for an updated
    `today_mood`, `intentions_toward_player`, and a 1-line `recent_event`
    (what they did off-screen). The narrator reads these from the cast
    block to drive nuanced reactions instead of static personality.

    Returns `{code: {today_mood, intentions_toward_player, recent_event}}`
    — caller is responsible for writing them back onto the CharacterState
    objects and updating `last_tick_day`.

    Cost: ~200 input + ~80 output tokens per character (~$0.00005 each on
    Grok 4.1 Fast). For a 4-character cast: ~$0.0002 once per game day.
    """
    if not character_states or day <= 0:
        return {}
    eligible = [
        (code, cs) for code, cs in character_states.items()
        if (cs.last_tick_day or 0) < day
    ]
    if not eligible:
        return {}

    setting_blurb = setting_label
    if custom_setting_text:
        setting_blurb += f" — {custom_setting_text[:200]}"

    sys_msg = (
        "You write a one-day-later inner update for ONE adult NPC. Output strict JSON. "
        "The character lives in a slice-of-life world; their mood and intentions toward "
        "the player should drift naturally based on personality, current relationship "
        "state, and what plausibly happened to them off-screen yesterday. Be concrete "
        "and grounded — no melodrama unless the relationship state warrants it."
    )

    async def _tick_one(code: str, cs: CharacterState) -> tuple[str, dict]:
        rel = (relationships or {}).get(code) or {}
        level = int(rel.get("level", 0) or 0)
        scenes = int(rel.get("scenes", 0) or 0)
        last_mood = rel.get("last_mood", "neutral")
        prev_mood = cs.today_mood or "(none yet)"
        prev_intent = cs.intentions_toward_player or "(none yet)"
        prev_event = cs.recent_event or "(none yet)"
        user_msg = f"""Setting: {setting_blurb}
Character codename: {code}
Personality: {cs.personality or '—'}
Job: {cs.job or '—'}
Temperament: {cs.temperament}
Today is day {day} of the game.

Current relationship with the player:
- level: {level} (0 stranger → 5 lover)
- scenes shared: {scenes}
- last visual mood (from prev scene): {last_mood}

Previous-day state (what you previously assigned):
- mood: "{prev_mood}"
- intentions_toward_player: "{prev_intent}"
- last recent_event: "{prev_event}"

Produce a JSON object (no markdown, no commentary):
{{
  "today_mood": "<one short phrase, max 80 chars — fits the personality + temperament + relationship arc>",
  "intentions_toward_player": "<one short phrase, max 100 chars — what they want from / want to do with the player today>",
  "recent_event": "<one short sentence, max 120 chars — what plausibly happened to them OFF-SCREEN yesterday: a small life beat (a meeting, a realisation, a phone call, a routine moment with a colleague), grounded in their job/personality. NOT about the player.>"
}}

Drift rules:
- moods should EVOLVE — don't repeat the previous mood verbatim.
- if relationship level is high (3+), intentions can include desire / wanting to see the player.
- if level is 0 and scenes is 0, intentions are about their own life, NOT the player.
- recent_event should never claim the character met / saw the player; it's their PRIVATE life.
- write in the same language as the setting if obvious, else English."""
        try:
            resp = await grok_client.chat.completions.create(
                model=grok_model,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.85,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
        except Exception as e:
            print(f"[agent] daily_tick({code}) failed: {e}")
            return code, {}
        return code, {
            "today_mood": str(data.get("today_mood", "")).strip()[:120],
            "intentions_toward_player": str(data.get("intentions_toward_player", "")).strip()[:160],
            "recent_event": str(data.get("recent_event", "")).strip()[:200],
        }

    import asyncio
    results = await asyncio.gather(*[_tick_one(code, cs) for code, cs in eligible])
    return {code: payload for code, payload in results if payload}
