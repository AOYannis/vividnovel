"""Image-prompt specialist agent (Phase 3A).

The narrator agent emits a *lean* scene spec (summary + shot intent + mood name +
actors). This module turns that spec into a fully self-contained Z-Image Turbo
prompt by calling Grok 4.1 Fast with a focused, standalone system prompt.

Splitting this out keeps the narrator's system prompt small and focused on
storytelling — image direction lives here, where it can evolve without
contaminating the story with worked examples that bias the narrative.

Cost: ~400 input + ~200 output tokens per scene (~$0.0001 on Grok 4.1 Fast).
"""
from __future__ import annotations
import time

# Banned tokens — Z-Image Turbo generates them instead of avoiding them
BANNED_WORDS = (
    "selfie", "phone", "camera", "mirror", "blur", "artifact",
    "you", "your", "viewer", "same as before", "previous",
)

# Phrases in shot_intent that invite a third-person shot of the player. Even
# with the system-prompt ban, Grok writes things like "plan arrière silhouette"
# and the specialist composes obediently. We sanitize before passing.
import re as _re
_BACKSHOT_PATTERNS = [
    _re.compile(r"\b(plan\s+arri[èe]re|plan\s+de\s+dos|de\s+dos|dos\s+tourn[ée]?)\b", _re.IGNORECASE),
    _re.compile(r"\b(silhouette\s+(du|de\s+la)\s+(joueur|protagoniste|personnage|h[ée]ros))\b", _re.IGNORECASE),
    _re.compile(r"\b(silhouette\s+solitaire|silhouette\s+contemplative)\b", _re.IGNORECASE),
    _re.compile(r"\b(over[-\s]?the[-\s]?shoulder)\b", _re.IGNORECASE),
    _re.compile(r"\b(rear\s+shot|back\s+shot|from\s+behind\s+(the|a)\s+(player|protagonist|figure|man|woman|character))\b", _re.IGNORECASE),
    _re.compile(r"\b(wide\s+shot\s+(of|on)\s+(the\s+)?(player|protagonist|figure|man|woman|character))\b", _re.IGNORECASE),
]


# Face / visage close-up patterns. When NO cast actor is in the frame, any
# face close-up necessarily targets the player → broken POV. Only triggered
# for scenes with empty `actors_present`.
_PLAYER_FACE_PATTERNS = [
    _re.compile(r"\b(gros\s+plan\s+facial|gros\s+plan\s+sur\s+(le|son|ses)\s+(visage|yeux|bouche)|plan\s+facial)\b", _re.IGNORECASE),
    _re.compile(r"\b(close[-\s]?up\s+(of|on)\s+(the\s+|his\s+|her\s+)?(face|eyes|mouth)|facial\s+close[-\s]?up)\b", _re.IGNORECASE),
]


def _sanitize_shot_intent(intent: str, actors_present: list[str] | None = None) -> str:
    """Strip player-third-person-shot patterns from the narrator's shot_intent so
    the specialist isn't tempted to compose a back-shot or face close-up of the
    player. Replace stripped fragments with a POV-safe alternative.

    `actors_present` is used to gate face-close-up sanitisation: when at least
    one cast actor is in frame, "gros plan facial" likely targets THEM (legitimate);
    when empty, it can only mean the player's face (broken POV)."""
    if not intent:
        return intent
    out = intent
    for pat in _BACKSHOT_PATTERNS:
        out = pat.sub("plan large POV (paysage / décor)", out)
    if not actors_present:
        for pat in _PLAYER_FACE_PATTERNS:
            out = pat.sub("plan POV serré sur objet / détail (mains, eau, etc.)", out)
    out = _re.sub(r"\s{2,}", " ", out).strip(" ,;.")
    return out


SYSTEM_PROMPT = """You are an image-prompt specialist for an interactive adult visual novel.
Your only job: turn a short scene spec into ONE self-contained Z-Image Turbo prompt
(English, 80-200 words). You are NOT writing a story — only the visual prompt.

# Z-Image Turbo constraints
- Zero memory between images: every prompt must be 100% self-contained.
- Negations are IGNORED (CFG=0). NEVER write 'no X' / 'without X'. Describe positively what IS present.
- NEVER use these words anywhere in the prompt: """ + ", ".join(f"'{w}'" for w in BANNED_WORDS) + """.
- NEVER write a mood name (kiss, sensual_tease, blowjob, missionary, etc.) inside the prompt — those are technical
  parameters, not visual keywords.

# POV — first-person, player's eyes — STRICT
EVERY image is shot from the player's eyes. Camera = player's eyes.
- Open the prompt EARLY with a POV marker: `POV first-person`, `eye-level POV`,
  `seen from a first-person perspective`, `looking down`, `looking across`, etc.
- NEVER describe a third-person wide shot of two full bodies side by side.
- If the male player has physical presence in the scene, only his **hands, forearms,
  lower torso** may enter at the frame edges (as if he was looking at them through the
  camera) — NEVER his full face or body.
- If the player is not male, same rule: his/her body is the camera, never a tiered subject.

## ⛔ The player is NEVER a SUBJECT of the frame
Even if the narrator's `shot_intent` invites one of these — REJECT IT and re-frame as POV:
- "from behind a figure", "the player from behind", "back turned", "silhouetted figure",
  "broad shoulders against the X", "rear shot", "over-the-shoulder of the protagonist"
- "his face", "his hair", "his jawline", "stubble on his chin", "his eyes"
- "a man / a male figure / the protagonist standing / sitting / contemplating"
NEVER write any of these about the player. The player has no visible face, no visible
back, no visible silhouette — he/she is the camera. If the narrator asks for a wide
contemplative shot, render the LANDSCAPE the player is contemplating (looking outward
across the dunes / cityscape / room) — not the player's body.

POV-correct alternatives when the narrator wants atmosphere:
- "POV first-person looking across the vast Tatooine dunes at night, twin moons low on
   the horizon..." → camera is the player's eyes, scene is the landscape.
- "POV first-person, hands resting on knees at frame bottom edge, looking out over
   the water..." → only forearms/hands at edges, never face/back.

# Structure — 4 layers (Camera Director Formula)
Layer 1 — Subject & action: shot type + person (age, ethnicity, body, face) + clothing
  (materials, colours, state) + what each hand is doing. Describe each visible person
  ONCE, never duplicate. If MULTIPLE non-LoRA NPCs share the frame (waiters, drinkers,
  passers-by), give each one DISTINCT features (different hair, build, age, clothing) —
  do not write "three burly pirates" or "two waiters" as a uniform group; itemise them
  briefly so they don't all render as the same face. For atmospheric / object shots:
  describe what the player sees.
Layer 2 — Setting: precise location, decor, environment details.
Layer 3 — Lighting (mandatory): name a specific natural style — `soft diffused daylight`,
  `warm golden key light from vintage sconces`, `neon-lit nightclub ambiance`,
  `candlelight from a single taper`, `overcast window light`. Avoid generic studio terms.
Layer 4 — Camera & film: lens (`50mm`, `85mm`, `35mm`), photo style
  (`Portra Film Photo`, `Quiet Luxury Photo`, `Vibrant Analog Photo`,
  `editorial photography`, `candid street photo`), depth of field.

# Skin & realism (anti-plastic) — include for any human subject
- `highly detailed skin texture`, `subtle skin pores`, `natural skin tones`.
- Optional: `faint freckles`, `sun-kissed skin`, `natural film grain`, `crisp details`.

# Clothing continuity — CRITICAL
If a "Locked clothing" block is provided, copy each character's outfit VERBATIM into
the prompt — same garment, same colour, same materials. Never swap a color A dress for
a color B one between scenes. The only exception is when the scene_summary explicitly
says the character changed clothes ("she takes off the corset", "she puts on a coat").
If no locked clothing is provided yet (first time the character is on screen), invent
an outfit that fits the setting and the character.

# Appearance continuity — CRITICAL
If a "Locked appearance" block is provided for a character, use those head-and-shoulders
features VERBATIM (hair length / cut / colour / texture, eye colour, skin tone, age,
ethnicity, signature features). Don't paraphrase, don't substitute synonyms ("short bob"
≠ "pixie cut" ≠ "cropped hair"). The only exception is when scene_summary explicitly
describes a change ("hair now wet", "face flushed", "fresh makeup", "tear streaks") —
in that case keep the locked baseline AND add the situational change on top.

# Time of day & lighting — CRITICAL
When a "Time of day" is provided (morning / afternoon / evening / night), the lighting
MUST match it. Z-Image Turbo defaults to bright daylight if not told otherwise.
- night → candlelight, warm bedside lamp, neon glow, moonlight, streetlamp through window
- evening → warm sunset, golden hour, low amber lamps, dusk through curtains
- morning → cool diffused dawn, soft window light, pale daylight
- afternoon → bright natural daylight, sunlit interior
NEVER write "sunlit" / "bright daylight" / "morning light" for an evening or night scene.
The lighting style you pick (Layer 3) MUST be consistent with the time of day.

# Trigger words (LoRA tokens)
- If a TRIGGER word is provided for a character, place it AT THE VERY START of the prompt,
  followed by a comma — Z-Image weights prompt prefixes more heavily and the LoRA needs
  this anchor.
- For multi-character scenes: only the FIRST character's trigger goes at the start.
  Other characters' triggers, if provided, appear inline, just before that character's
  description in the prompt body. Never stack multiple triggers at the start — that
  blends the LoRAs and the characters end up looking alike.
- If NO actor is in the scene (atmospheric shot), no character trigger word is necessary.
- some mood specialized do also require a triggerword , see below

# Mood directive
A mood directive is provided separately when the scene calls for one. The runtime AUTOMATICALLY
prepends the full mood directive to your prompt. So:
- DO NOT echo or repeat the mood directive.
- DO NOT redescribe the framing/poses already implied by the mood (e.g. for a `kiss`
  close-up, do NOT mention hands, blouse, or the wider room — they are out of frame).
- DO write the *unique* details of THIS scene: character identity (hair, eyes, age),
  the specific location, the lighting, 1-2 atmospheric beats, and the camera/film keywords.

# Format
- English only.
- 80-200 words. Be tight. Z-Image Turbo likes detail but punishes filler.
- Output ONLY the raw prompt — no headers, no labels, no quotes around it,
  no commentary, no explanation. Just the prompt string.
"""


def _format_actor_block(actors_present: list[str], actor_lookup: dict[str, dict]) -> str:
    """Pretty-print actor data for the user message.

    `actor_lookup` maps codename -> {trigger_word, prompt_prefix, description, gender}.
    Empty `actors_present` does NOT mean atmospheric — it means no LoRA-backed cast
    member is in frame. Non-cast NPCs (waiters, passers-by, the questmaster, …) live
    only in the scene_summary and the specialist composes them from that text.
    """
    if not actors_present:
        return (
            "No LoRA-backed cast member in this shot. "
            "If `scene_summary` describes a person (waiter, neighbour, NPC, etc.), "
            "compose them in the prompt from that description. If the summary is "
            "purely environmental, render an atmospheric shot."
        )
    lines = []
    for code in actors_present:
        data = actor_lookup.get(code) or {}
        tw = data.get("trigger_word") or ""
        pp = data.get("prompt_prefix") or ""
        desc = data.get("description") or ""
        gender = data.get("gender") or "female"
        anchor = tw or (pp[:60] + "..." if pp else "")
        gender_note = " (TRANS — woman with penis; only mention 'trans woman with erect penis visible' for explicit nude moods, otherwise treat as woman)" if gender == "trans" else ""
        line = f"- `{code}`{gender_note}\n"
        if tw:
            line += f"    trigger word (place FIRST in prompt for first character): `{tw}`\n"
        elif pp:
            line += f"    no trigger — prepend this prefix instead: \"{pp}\"\n"
        if desc:
            line += f"    appearance hint: {desc}\n"
        lines.append(line)
    return "\n".join(lines)


def _format_clothing_block(actors_present: list[str], clothing_state: dict[str, str]) -> str:
    """Per-actor clothing description (locked across scenes by the consistency
    tracker). The specialist MUST honour these outfits verbatim — no swapping,
    no recolouring — unless the narrator says the character changed clothes.
    """
    if not clothing_state:
        return ""
    relevant = {code: clothing_state[code] for code in actors_present if code in clothing_state}
    extra = {code: clothing_state[code] for code in clothing_state if code not in actors_present}
    if not relevant and not extra:
        return ""
    lines = ["Locked clothing (use VERBATIM — same colour, same materials, same items as the previous scene):"]
    for code, clothing in relevant.items():
        lines.append(f"- `{code}`: {clothing}")
    for code, clothing in extra.items():
        lines.append(f"- (`{code}`, not visible this scene but locked for continuity): {clothing}")
    return "\n".join(lines)


def _format_appearance_block(actors_present: list[str], appearance_state: dict[str, str]) -> str:
    """Per-actor head-and-shoulders lock. Captured from the first scene each
    character appeared in. Stops drift on hair / face / skin / age across scenes.
    """
    if not appearance_state:
        return ""
    relevant = {code: appearance_state[code] for code in actors_present if code in appearance_state}
    if not relevant:
        return ""
    lines = ["Locked appearance (use VERBATIM — same hair / face / eyes / skin / age):"]
    for code, look in relevant.items():
        lines.append(f"- `{code}`: {look}")
    return "\n".join(lines)


def _format_time_of_day_block(time_of_day: str | None) -> str:
    """Single-line hint passed alongside the location. Specialist must pick a
    lighting style that matches it (Z-Image defaults to bright daylight otherwise)."""
    if not time_of_day:
        return ""
    return f"Time of day: **{time_of_day}** (the lighting in the prompt MUST match this — see system rules)."


def _format_mood_block(mood_name: str | None, mood_data: dict | None) -> str:
    if not mood_name or mood_name == "neutral":
        return "Mood: `neutral` — no special framing or LoRA. Compose the shot freely."
    if not mood_data:
        return f"Mood: `{mood_name}` — (mood data not found, default to neutral framing)."
    desc = (mood_data.get("description") or "").strip()
    pb = (mood_data.get("prompt_block") or "").strip()
    out = [f"Mood: `{mood_name}` — {desc}"]
    if pb:
        out.append(
            f"Mood directive (already auto-prepended by runtime — DO NOT repeat or paraphrase):\n"
            f"  \"{pb}\""
        )
    return "\n".join(out)


async def craft_image_prompt(
    grok_client,
    *,
    scene_index: int,
    scene_summary: str,
    shot_intent: str,
    actors_present: list[str],
    mood_name: str | None,
    actor_lookup: dict[str, dict],
    mood_data: dict | None,
    setting_label: str,
    custom_setting_text: str,
    location_hint: str,
    clothing_state: dict[str, str] | None,
    appearance_state: dict[str, str] | None,
    time_of_day: str | None,
    language: str,
    player_gender: str,
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> tuple[str, float]:
    """Synthesise a Z-Image Turbo prompt from a lean narrator scene spec.

    Returns (prompt_string, elapsed_seconds). Falls back to a minimal hand-rolled
    prompt on Grok failure so the image pipeline never blocks.
    """
    actor_block = _format_actor_block(actors_present, actor_lookup)
    mood_block = _format_mood_block(mood_name, mood_data)
    clothing_block = _format_clothing_block(actors_present, clothing_state or {})
    appearance_block = _format_appearance_block(actors_present, appearance_state or {})
    time_block = _format_time_of_day_block(time_of_day)

    # Server-side defense: strip player-back-shot phrasing from the narrator's
    # shot_intent before the specialist sees it. Otherwise Grok composes obediently
    # ("from behind a solitary male figure...") and the POV is broken. Face
    # close-ups when no actor is in scene are also stripped (the face would be
    # the player's by elimination).
    safe_shot_intent = _sanitize_shot_intent(shot_intent or "", actors_present)
    if safe_shot_intent != (shot_intent or ""):
        print(f"[scene_agent] sanitised shot_intent for scene {scene_index}: "
              f"{shot_intent!r} → {safe_shot_intent!r}")

    setting_line = setting_label or "(unspecified setting)"
    if custom_setting_text:
        setting_line += f" — custom: {custom_setting_text[:300]}"

    user_msg = f"""Scene {scene_index} for an interactive visual novel.

Setting: {setting_line}
Current location (canonical): {location_hint or '(unspecified)'}
{time_block}
Player gender: {player_gender}
Story language: {language} (the prompt itself stays in ENGLISH)

Narrator summary (what is happening in this 10-second beat):
{scene_summary or '(no summary provided)'}

Shot intent (camera/tone hint from the narrator):
{safe_shot_intent or '(no specific intent — pick a fitting shot)'}

Characters visible in this image:
{actor_block}

{appearance_block}

{clothing_block}

{mood_block}

Now produce ONE Z-Image Turbo prompt (raw text, no quotes, no labels) that
satisfies every rule from the system prompt. If the location is a custom setting
(pirate, sci-fi, fantasy…) make sure the visual vocabulary fits — never default
to a generic Parisian café when the setting says otherwise."""

    start = time.time()
    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.6,
            max_tokens=500,
        )
        prompt = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[scene_agent] craft_image_prompt failed: {e}; using fallback")
        prompt = _fallback_prompt(scene_summary, shot_intent, actors_present, actor_lookup, location_hint)

    # Defensive cleanup — strip wrapping quotes the model sometimes adds
    if prompt.startswith(("'", '"')) and prompt.endswith(("'", '"')) and len(prompt) > 2:
        prompt = prompt[1:-1].strip()

    elapsed = round(time.time() - start, 2)
    return prompt, elapsed


async def extract_appearance(
    grok_client,
    *,
    codename: str,
    image_prompt: str,
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> str:
    """Pull the head-and-shoulders description for one character out of an
    already-crafted image prompt. Used to lock the look on first appearance so
    later scenes don't drift the hair / face / skin / age details.

    Returns a short comma-separated phrase suitable for re-injection (~30-80
    words), or empty string on failure.
    """
    if not image_prompt or not codename:
        return ""
    sys_msg = (
        "You extract the head-and-shoulders appearance of ONE character from a "
        "Z-Image Turbo prompt. Output a short, dense, comma-separated phrase that "
        "can be reused VERBATIM in future prompts to lock the look. Include only: "
        "age, ethnicity / face type, hair (length, cut, colour, texture), eyes "
        "(colour, shape, expression-neutral), skin (tone, marks like freckles), "
        "any signature feature (jewellery on head, glasses, scar). EXCLUDE: "
        "clothing, body pose, location, lighting, camera, mood, action verbs. "
        "Output ONLY the phrase — no labels, no quotes, no commentary. If the "
        "prompt does not describe the character clearly, output an empty string."
    )
    user_msg = (
        f"Character codename: `{codename}`\n\n"
        f"Image prompt to extract from:\n{image_prompt}\n\n"
        f"Output the head-and-shoulders appearance phrase:"
    )
    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=160,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Strip wrapping quotes the model sometimes adds
        if text.startswith(("'", '"')) and text.endswith(("'", '"')) and len(text) > 2:
            text = text[1:-1].strip()
        return text
    except Exception as e:
        print(f"[scene_agent] extract_appearance({codename}) failed: {e}")
        return ""


def _fallback_prompt(
    scene_summary: str,
    shot_intent: str,
    actors_present: list[str],
    actor_lookup: dict[str, dict],
    location_hint: str,
) -> str:
    """Minimal hand-rolled prompt used when Grok is unreachable. Keeps the pipeline alive."""
    parts: list[str] = []
    if actors_present:
        first = actors_present[0]
        data = actor_lookup.get(first) or {}
        tw = data.get("trigger_word") or ""
        if tw:
            parts.append(tw)
    parts.append("POV first-person, eye-level")
    if shot_intent:
        parts.append(shot_intent.strip())
    if scene_summary:
        parts.append(scene_summary.strip())
    if location_hint:
        parts.append(f"in {location_hint}")
    parts.append(
        "soft natural lighting, highly detailed skin texture, subtle skin pores, "
        "natural skin tones, Shot on 50mm lens, Portra Film Photo, shallow depth of field, crisp details"
    )
    return ", ".join(p for p in parts if p)
