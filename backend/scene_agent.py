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


SYSTEM_PROMPT = """You are an image-prompt specialist for an interactive adult visual novel.
Your only job: turn a short scene spec into ONE self-contained Z-Image Turbo prompt
(English, 80-200 words). You are NOT writing a story — only the visual prompt.

# Z-Image Turbo constraints
- Zero memory between images: every prompt must be 100% self-contained.
- Negations are IGNORED (CFG=0). NEVER write 'no X' / 'without X'. Describe positively what IS present.
- NEVER use these words anywhere in the prompt: """ + ", ".join(f"'{w}'" for w in BANNED_WORDS) + """.
- NEVER write a mood name (kiss, sensual_tease, blowjob, missionary, etc.) inside the prompt — those are technical
  parameters, not visual keywords.

# POV — first-person, player's eyes
EVERY image is shot from the player's eyes. Camera = player's eyes.
- Open the prompt EARLY with a POV marker: `POV first-person`, `eye-level POV`,
  `seen from a first-person perspective`, `looking down`, `looking across`, etc.
- NEVER describe a third-person wide shot of two full bodies side by side.
- If the male player is physically present in the scene, only his **hands, forearms,
  lower torso** may enter at the frame edges — NEVER his full face or body.
- If the player is not male, same rule: his/her body is the camera, never a tiered subject.

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

# Trigger words (LoRA tokens)
- If a TRIGGER word is provided for a character, place it AT THE VERY START of the prompt,
  followed by a comma — Z-Image weights prompt prefixes more heavily and the LoRA needs
  this anchor.
- For multi-character scenes: only the FIRST character's trigger goes at the start.
  Other characters' triggers, if provided, appear inline, just before that character's
  description in the prompt body. Never stack multiple triggers at the start — that
  blends the LoRAs and the characters end up looking alike.
- If NO actor is in the scene (atmospheric shot), no trigger word at all.

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

    setting_line = setting_label or "(unspecified setting)"
    if custom_setting_text:
        setting_line += f" — custom: {custom_setting_text[:300]}"

    user_msg = f"""Scene {scene_index} for an interactive visual novel.

Setting: {setting_line}
Current location (canonical): {location_hint or '(unspecified)'}
Player gender: {player_gender}
Story language: {language} (the prompt itself stays in ENGLISH)

Narrator summary (what is happening in this 10-second beat):
{scene_summary or '(no summary provided)'}

Shot intent (camera/tone hint from the narrator):
{shot_intent or '(no specific intent — pick a fitting shot)'}

Characters visible in this image:
{actor_block}

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
