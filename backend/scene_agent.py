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
- The player's body is the camera — only his/her **hands, forearms, lower torso**
  may enter the frame, NEVER his/her full face or body.

## ⚠️ Player hands/forearms enter from the BOTTOM of the frame — never the sides
When the player's hands or forearms appear (taking, holding, reaching, touching,
clinking, gesturing, etc.), they MUST enter the frame from BELOW — like a
video-game first-person viewmodel. Anchor every hand/forearm to one of:
`from frame bottom`, `at frame bottom edge`, `at bottom-right edge`, `at bottom-left edge`.
ONE or TWO hands are both fine — as long as BOTH come from below.

NEVER use the unanchored phrase "at frame edges" (plural). Z-Image reads "edges"
as the LEFT and RIGHT sides and renders two disembodied hands at left+right,
which looks like two strangers flanking the subject — not the player.

❌ BAD : "male hands at frame edges holding glasses"
   → renders two stranger-hands at left and right, breaking POV.
✅ GOOD: "the player's right hand entering from frame bottom-right, holding a
        champagne flute and clinking it against hers"
   → one hand, anchored at the bottom — clearly the player's own viewmodel.
✅ GOOD: "both of the player's forearms entering from frame bottom, hands wrapping
        around her waist as he leans in"
   → two hands, but both anchored from BELOW — still reads as the player.

## ⚠️ Plural/shared body language → translate to singular POV
The narrator's `scene_summary` and `pose_hint` will often use plural body language
("bodies leaning closer", "they sit together", "side-by-side", "between them",
"shared X", "their X") or describe shared/joint poses (sitting together, lying
together, walking together). Z-Image reads these literally and renders TWO visible
bodies — and since only ONE character LoRA is loaded, both bodies get the actor's
face, producing a "twin character" rendering.

ALWAYS translate plural / shared phrasing to singular POV. The actor performs the
action; the player anchors the frame from below (hand on lap, arm beside her, etc.).
Examples:

❌ BAD : "seated side-by-side on the bench, bodies leaning closer"
   → renders TWO visible bodies side by side (twin actor faces).
✅ GOOD: "seated on the bench, the camera (player) seated next to her with player's
        arm visible at frame bottom-right resting on his thigh, her body angled toward
        the camera leaning slightly closer, her hand resting on his lap visible at
        frame bottom"
   → ONE visible body (hers) + player anchored at frame bottom.

❌ BAD : "their hands intertwined on the vine, bodies imperceptibly closer"
   → renders two bodies + a pair of hands belonging to neither.
✅ GOOD: "her hand intertwined with the player's right hand at frame bottom resting
        on a glowing vine, her body angled in close from the side"

NEVER write "bodies", "they", "them", "their", "two of you", "side-by-side" as
visible-frame descriptors. Only ONE body is ever in the frame — hers. The player's
presence is implied by hands/forearms anchored from frame bottom.

## ✦ Contact framings (head-on-shoulder, embrace from side, nestled, leaning against)
EXCEPTION to "hands at frame bottom": when the action involves the actor PHYSICALLY
TOUCHING the player's torso/shoulder/chest/lap — head resting on shoulder, nestled
against chest, arm wrapped around her, leaning into him, hand flat on his chest,
straddling his lap, head in his lap, etc. — the player's body part she is touching
SHOULD appear as a SLIVER at the appropriate frame edge in SOFT FOCUS / blurred
bokeh. The frame edge depends on the geometry of the contact: head-on-RIGHT-shoulder
→ sliver at frame right; nestled against chest from POV looking down → sliver of
chest at frame bottom; arm draped from above → sliver at frame top.

What the sliver shows:
- A small piece of the player's garment (a sleeve, a collar, a shoulder, a lapel,
  a fold of fabric) — or bare skin if the scene calls for shirtless. Pick a garment
  detail that is PLAUSIBLE for THIS player in THIS specific setting (read the
  setting brief and the player block — invent from there, not from the default
  outfit the era is usually drawn with).
- A few inches of fabric and one small body part (shoulder edge, upper arm, side of
  chest). NEVER his face, neck, jawline, stubble, hair, or full silhouette.
- Always SOFT FOCUS / blurred / out of focus / shallow depth of field on the player's
  body part — Z-Image reads "sliver in soft focus" as bokeh, which prevents the
  ghost-character bug AND avoids needing pixel-level player-clothing consistency.

❌ BAD : "her head resting tenderly on the player's shoulder with player's forearm
        visible at frame bottom-left draped along the bench beside her"
   → renders her on a bench but no spatial relationship — looks like she is alone.
✅ GOOD: "her head resting against his chest, only a sliver of his shirt fabric
        and the side of his shoulder visible at frame right in soft focus,
        her face turned slightly toward him, her hand flat on his chest at frame
        bottom-right, intimate POV first-person from his perspective"
   → her dominant in frame, player's body anchored as a blurred sliver at right
     edge, clearly an embrace from his POV.

❌ BAD : "she straddles the player on the bench, his torso below her"
   → no visible relationship, may render her floating alone.
✅ GOOD: "her seated on his lap facing the camera, only a sliver of his garment
        and the curve of his shoulder visible at frame bottom-left in soft
        focus, her hands resting on his shoulders at frame bottom corners"

The trigger is the ACTION semantics ("touching", "leaning against", "nestled",
"resting on", "hand on his X", "in his lap"). When you see those in scene_summary
or pose_hint, switch from "hands-at-bottom" mode to "sliver-at-frame-edge" mode.
Never use BOTH descriptors for the same scene — pick the one that fits the contact
geometry.

Three additional rules that make the embrace ACTUALLY read as an embrace in the
rendered image (each one is non-optional for contact framings):

▸ **Gaze direction MUST point toward him, not the camera.** A girl with her head on
  someone's shoulder while looking at the camera reads as a posed portrait, not an
  embrace — the model loses the contact relationship. Always specify gaze:
  - "her eyes turned away from the camera, looking up toward him"
  - "her gaze directed at his chest just beside her"
  - "her eyes closed in contentment, head turned toward his neck"
  - "her face turned right toward him, looking at his shoulder"
  NEVER write "looking at the camera", "warm gaze locked on camera", "eyes meeting
  yours" for contact framings — those gazes break the embrace.

▸ **Framing MUST be CLOSE-UP regardless of shot_intent.** If `shot_intent` says
  "wide shot" / "tender wide shot" / "atmospheric wide" while the action is contact,
  OVERRIDE to close-up. Wide shots dissolve the embrace because the actor isn't
  dominant in the frame. Use phrasings:
  - "close-up portrait, her face and upper body fill the frame"
  - "tight intimate close-up, framed from chest up"
  - "shallow embrace framing, her head and upper torso dominant in composition"
  Reasoning: a contact embrace needs the actor to OWN the frame so the touch points
  (her head on his chest, his arm around her) are clearly visible.

▸ **Use MULTIPLE touch anchors, not just one sliver.** A single sliver in soft focus
  isn't enough for Z-Image to commit to an embrace pose — it'll often hedge by
  rendering her alone with a random fabric edge. Reinforce with 2-3 contact points:
  - the sliver itself (her resting against → his shoulder/chest at frame edge)
  - HIS arm/hand reaching ACROSS to wrap around her shoulders or waist (visible)
  - HER hand making contact with his torso (flat on his chest, gripping his sleeve)
  Three converging touch cues = the model commits to "embrace from his POV".

❌ BAD : "her head resting against his shoulder, sliver of dark jacket at frame
        right in soft focus, warm flirtatious gaze with parted lips" (gaze on
        camera, single anchor, no framing override)
   → renders her alone on a bench, looking at viewer, with a random fabric edge.
✅ GOOD: "close-up portrait of her nestled against his chest, intimate embrace
        framing from chest up, her face and upper body fill the frame, only a
        sliver of his charcoal henley shirt and the curve of his shoulder visible
        at frame right in soft focus, his arm wrapped around her shoulders coming
        in from frame top-right also in soft focus, her right hand flat on his
        chest at frame bottom-right, her eyes turned away from the camera looking
        up toward him with parted lips and soft flush"
   → three converging touch anchors + close framing + gaze toward him =
     unmistakable embrace from his POV.

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
- "POV first-person, hands resting on knees at frame bottom, looking out over
   the water..." → forearms/hands anchored from below, never from the sides.

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

# Pose hint (optional)
If a "Pose hint" block is provided, use it as INSPIRATION for the actor's body
position/posture: lying / kneeling / leaning / standing / seated, body orientation,
contact with surfaces or props (massage table, bar, headboard). Be specific in your
prompt about the posture — but do NOT copy the hint VERBATIM if it contains plural
body language ("bodies", "side-by-side", "together", "they", "them", "their") or
shared-pose phrasings. Those describe the NARRATIVE moment between two characters;
in the IMAGE only HER body is visible, the player is the camera. Translate per the
POV rules (her body + player's hands/forearms at frame bottom).
When no pose hint is given, infer the natural posture from the action.

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
A mood directive is provided separately when the scene calls for one. There are TWO formats:

LEGACY (most moods today): the runtime AUTOMATICALLY prepends the full mood directive
to your prompt. For these moods:
- DO NOT echo or repeat the mood directive.
- DO NOT redescribe the framing/poses already implied by the mood (e.g. for a `kiss`
  close-up, do NOT mention hands, blouse, or the wider room — they are out of frame).
- DO write the *unique* details of THIS scene: character identity (hair, eyes, age),
  the specific location, the lighting, 1-2 atmospheric beats, and the camera/film keywords.

NEW DECLARATIVE (e.g. `kiss`): the mood block carries `Framing intent`, `Reference
examples`, and `Mood directives`. There is NO runtime prepend — YOU are the integrator.
- READ the framing intent and write a prompt that fits it.
- DRAW STRUCTURAL INSPIRATION from ONE of the reference examples (rotate across
  successive calls — don't always pick #1; vary the framing across scenes for variety).
- NEVER copy a reference example verbatim; ADAPT each phrase to this scene's character,
  location, lighting, and pose.
- STRICTLY OBEY every line in the `Mood directives` list — they are non-negotiable
  (e.g. "skip clothing description", "use singular face", "only one woman visible").
- ⚠️ **Mood directives OVERRIDE all global continuity rules above.** When a directive
  says "DO NOT include any clothing description" or "skip body description", do
  NOT include the locked clothing/appearance even if those blocks were provided.
  The directive is the source of truth for THIS scene; the lock state stays intact
  for future non-mood scenes.

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


def _format_decor_block(decor_lock: str) -> str:
    """Per-location decor description (locked across all scenes at this location).
    The specialist MUST honour the architecture, materials, fixed furniture, and
    fixed props verbatim — no swapping, no recolouring, no re-imagining the room.
    Time-of-day lighting and pose still vary; the SPACE is constant.
    """
    if not (decor_lock or "").strip():
        return ""
    return (
        "Locked decor for THIS location (use VERBATIM — same architecture, "
        "materials, fixtures, fixed furniture and fixed props as previous scenes "
        "here. Lighting and time-of-day still vary per the time-of-day block; the "
        "SPACE is constant):\n"
        f"{decor_lock.strip()}"
    )


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


def _format_pose_block(pose_hint: str | None) -> str:
    """Optional pose / body-position guidance. Used when the scene needs an
    explicit posture (lying face-down on a massage table, kneeling on the
    sand, leaning against the bar) that scene_summary alone wouldn't make
    obvious. Specialist should anchor the actor's body to this — but TRANSLATE
    plural body language ('side-by-side', 'bodies', 'they') to POV singular
    per the rules in SYSTEM_PROMPT, not copy verbatim."""
    if not pose_hint:
        return ""
    return (
        "## Pose hint (the body posture this scene calls for — INSPIRATION, not verbatim)\n"
        f"{pose_hint.strip()}\n\n"
        "⚠️ If this hint contains plural body language ('bodies', 'side-by-side', "
        "'together', 'they', 'them', 'their'), DO NOT copy those words verbatim — "
        "translate per the POV rules above (only HER body in frame, player anchored "
        "via hands/forearms at frame bottom). The pose intent matters; the exact "
        "phrasing is yours to write."
    )


def _is_new_format_mood(mood_data: dict | None) -> bool:
    """A mood is in the new declarative format when it carries any of
    `framing_intent`, `examples`, or `agent_directives`. Such moods are
    integrated into the prompt by Grok (the prompt-builder agent), with NO
    runtime prepend. Legacy moods (only `prompt_block`) keep the old
    behaviour: runtime prepends, agent doesn't repeat."""
    if not isinstance(mood_data, dict):
        return False
    return any(mood_data.get(k) for k in ("framing_intent", "examples", "agent_directives"))


def _format_mood_block(mood_name: str | None, mood_data: dict | None) -> str:
    if not mood_name or mood_name == "neutral":
        return "Mood: `neutral` — no special framing or LoRA. Compose the shot freely."
    if not mood_data:
        return f"Mood: `{mood_name}` — (mood data not found, default to neutral framing)."
    desc = (mood_data.get("description") or "").strip()

    # New declarative format — Grok is the integrator.
    if _is_new_format_mood(mood_data):
        framing = (mood_data.get("framing_intent") or "").strip()
        examples = mood_data.get("examples") or []
        directives = mood_data.get("agent_directives") or []
        out = [f"## Mood: `{mood_name}` — {desc}", ""]
        out.append("YOU are responsible for integrating this mood into the prompt — there is "
                   "NO runtime prepend. Read the framing intent, draw structural inspiration "
                   "from ONE of the reference examples (rotate across calls — don't always use "
                   "#1), strictly obey every directive, and write a unique prompt for THIS "
                   "scene's character + location + lighting. Never copy a reference example "
                   "verbatim, never literally merge two of them.")
        out.append("")
        if framing:
            out.append("Framing intent (what this mood IS):")
            out.append(framing)
            out.append("")
        if examples:
            out.append("Reference examples (rotate inspiration across them; ADAPT, NEVER copy verbatim):")
            for i, ex in enumerate(examples, 1):
                out.append(f"  {i}. {str(ex).strip()}")
            out.append("")
        if directives:
            out.append("Mood directives (MUST obey):")
            for d in directives:
                out.append(f"  - {str(d).strip()}")
        return "\n".join(out)

    # Legacy format — runtime prepends `prompt_block`; agent only sees it as reference.
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
    system_prompt_override: str | None = None,
    pose_hint: str | None = None,
    decor_lock: str = "",
) -> tuple[str, float]:
    """Synthesise a Z-Image Turbo prompt from a lean narrator scene spec.

    Returns (prompt_string, elapsed_seconds). Falls back to a minimal hand-rolled
    prompt on Grok failure so the image pipeline never blocks.

    `system_prompt_override`: when set, replaces the module-level SYSTEM_PROMPT
    for this single call. Used by the /iterate prompt-lab tab to test edits
    against captured historical scene inputs.

    `decor_lock`: per-location dense physical-space description, locked across
    scenes at this location. When non-empty, surfaced to the specialist as a
    `Locked decor` block to keep architecture/materials/fixtures consistent.
    """
    actor_block = _format_actor_block(actors_present, actor_lookup)
    mood_block = _format_mood_block(mood_name, mood_data)
    clothing_block = _format_clothing_block(actors_present, clothing_state or {})
    appearance_block = _format_appearance_block(actors_present, appearance_state or {})
    decor_block = _format_decor_block(decor_lock)
    time_block = _format_time_of_day_block(time_of_day)
    pose_block = _format_pose_block(pose_hint)

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
{decor_block}
{time_block}
Player gender: {player_gender}
Story language: {language} (the prompt itself stays in ENGLISH)

Narrator summary (what is happening in this 10-second beat):
{scene_summary or '(no summary provided)'}

Shot intent (camera/tone hint from the narrator):
{safe_shot_intent or '(no specific intent — pick a fitting shot)'}

Characters visible in this image:
{actor_block}

{mood_block}

{appearance_block}

{clothing_block}

{pose_block}

Now produce ONE Z-Image Turbo prompt (raw text, no quotes, no labels) that
satisfies every rule from the system prompt. If the location is a custom setting
(pirate, sci-fi, fantasy…) make sure the visual vocabulary fits — never default
to a generic Parisian café when the setting says otherwise."""

    sys_msg = system_prompt_override if system_prompt_override else SYSTEM_PROMPT

    start = time.time()
    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
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


async def extract_clothing(
    grok_client,
    *,
    codename: str,
    image_prompt: str,
    grok_model: str = "grok-4-1-fast-non-reasoning",
    prior_lock: str = "",
) -> str:
    """Pull a DENSE, REUSABLE clothing description for one character out of an
    already-crafted image prompt. Used to lock the outfit on first sighting AND
    after a confirmed clothing change, so future scenes can re-inject the rich
    description verbatim and Z-Image renders the same garments each time.

    The returned phrase is the source of truth for `consistency.clothing[code]`.
    It must be specific enough that Z-Image Turbo cannot reasonably re-interpret
    it across renders. The extractor is instructed to COMMIT to plausible
    concrete specifics (colour, fabric, hardware) when the source prompt is
    vague — passing vagueness through guarantees visual drift.

    `prior_lock`: when non-empty, this is a RE-EXTRACT after the change
    classifier flagged a deliberate clothing change. The extractor preserves
    every element of the prior lock VERBATIM and only updates the specific
    items the new image prompt clearly describes as changed (opened, removed,
    torn, swapped). Stops identity drift (e.g. chestnut-brown jacket becoming
    black on re-extract just because the narrator described it opening).

    Returns a comma-separated phrase (~40-110 words) or empty string on
    failure. Cost: ~150 input + ~150 output tokens per call (~$0.00008 each on
    Grok 4.1 Fast). Fires once per actor on first sighting, plus once whenever
    the LLM clothing-change classifier flags an actor as having changed.
    """
    if not image_prompt or not codename:
        return ""
    sys_msg = (
        "You extract the OUTFIT of ONE specific character from a Z-Image Turbo "
        "prompt and produce a dense, factual lock that future prompts will "
        "reuse VERBATIM to keep the same garments rendering consistently across "
        "scenes.\n\n"
        "REQUIREMENTS — every garment AND every accessory MUST specify:\n"
        "  - exact garment shape/cut (be specific about silhouette — neckline, "
        "hem, fit, length, construction. Never write the bare category 'dress' "
        "or 'top'.)\n"
        "  - colour NAMED concretely with HUE and SATURATION qualifiers (never "
        "'blue' or 'dark'). Pick a colour that fits THIS character and THIS "
        "world specifically — don't default to a recurring palette across "
        "characters and don't reach for the same handful of colours every time.\n"
        "  - fabric/material — be specific about weave, weight, finish; never "
        "omit. Pick what would PLAUSIBLY exist in this character's wardrobe "
        "given their setting, era, and life.\n"
        "  - closure/construction details when relevant (be specific — name "
        "the actual closure, seam, or construction).\n"
        "  - hardware and accessories piece by piece: jewellery with "
        "metal+colour, footwear with material+colour, belts/bags/eyewear with "
        "material+colour.\n"
        "  - visible state if explicit in source (e.g. slipped strap, "
        "half-unbuttoned, drenched, torn at hem).\n\n"
        "When the source prompt is VAGUE ('revealing pirate silks', 'sleek "
        "corporate mini-dress', 'casual outfit', 'elegant gown'), DO NOT echo "
        "the vagueness. Commit to plausible concrete specifics consistent with "
        "the character and setting visible in the prompt. The lock is the "
        "source of truth — a vague lock guarantees visual drift across scenes.\n\n"
        "EXCLUDE: head, face, hair, skin, body shape, pose, action, location, "
        "lighting, camera, mood.\n\n"
        "OUTPUT: a single comma-separated phrase, ~40-110 words, no labels, "
        "no quotes, no commentary. If no outfit is described AND the codename "
        "does not appear, output an empty string.\n\n"
        "GOOD: 'off-shoulder crimson silk-satin corset top with black lace "
        "trim along bust line, fitted brushed-brown-leather corset belt with "
        "brass eyelets, asymmetric tea-length black cotton skirt slit on right "
        "thigh, knee-high tan suede boots with two brass-buckle straps, "
        "hammered-bronze hoop earrings, thin braided-leather choker'\n"
        "BAD: 'revealing pirate silks' (no colour, no material, no specifics)\n"
        "BAD: 'sleek corporate mini-dress, chrome jewelry' (vague garment, no "
        "colour, no fabric, no piece-by-piece jewellery)\n"
        "BAD: 'blue dress with jewellery' (no shade, no fabric, no shape, "
        "no jewellery type)"
    )
    if (prior_lock or "").strip():
        user_msg = (
            f"Character codename: `{codename}`\n\n"
            f"PRIOR LOCK (the canonical outfit before this scene — this is the SOURCE OF TRUTH "
            f"for the character's identity, every word matters):\n"
            f"« {prior_lock.strip()} »\n\n"
            f"This is a RE-EXTRACT triggered by the change classifier. The new image prompt "
            f"below describes the SAME character but with a deliberate change (an item removed, "
            f"opened, torn, swapped, added, revealed, or repositioned).\n\n"
            f"Your job: produce the FULL UPDATED LOCK (same shape as a fresh extract — single "
            f"comma-separated phrase). Update ONLY the specific items the new image prompt "
            f"clearly indicates were changed. Preserve EVERY OTHER element of the prior lock "
            f"VERBATIM — same colour names, same fabric/material, same garment shapes, same "
            f"accessories, same hardware. Identity-defining details MUST NOT drift across this "
            f"re-extract. If the new prompt is vague about a detail that's in the prior lock, "
            f"keep the prior lock's wording for it.\n\n"
            f"Image prompt to extract clothing from:\n{image_prompt}\n\n"
            f"Output the updated dense clothing phrase:"
        )
    else:
        user_msg = (
            f"Character codename: `{codename}`\n\n"
            f"Image prompt to extract clothing from:\n{image_prompt}\n\n"
            f"Output the dense clothing phrase:"
        )
    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=320,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text.startswith(("'", '"')) and text.endswith(("'", '"')) and len(text) > 2:
            text = text[1:-1].strip()
        return text
    except Exception as e:
        print(f"[scene_agent] extract_clothing({codename}) failed: {e}")
        return ""


async def extract_decor(
    grok_client,
    *,
    location_id: str,
    location_name: str,
    location_type: str,
    location_description: str,
    setting_label: str,
    custom_setting_text: str,
    image_prompt: str,
    grok_model: str = "grok-4-1-fast-non-reasoning",
    prior_lock: str = "",
) -> str:
    """Pull a DENSE, REUSABLE physical-space description for ONE location out of
    an already-crafted image prompt. Used to lock the decor on first visit AND
    after a confirmed narrator-described decor change, so future scenes at this
    same location can re-inject the rich description verbatim and Z-Image renders
    the same room each time.

    The returned phrase is the source of truth for `Location.decor_lock`. It must
    be specific enough that Z-Image cannot reasonably re-interpret it across
    renders. The extractor is instructed to COMMIT to plausible concrete specifics
    (architecture, materials, fixtures, fixed props) when the source prompt is
    vague — passing vagueness through guarantees visual drift.

    `prior_lock`: when non-empty, this is a RE-EXTRACT after the change
    classifier flagged a material decor change. The extractor preserves every
    element of the prior lock VERBATIM and only updates what the new image
    prompt clearly describes as physically altered. Stops identity drift (e.g.
    a chestnut-walnut bar becoming polished black on re-extract just because
    the narrator described smoke damage).

    Returns a comma-separated phrase (~80-150 words) or empty string on failure.
    Cost: ~200 input + ~200 output tokens per call (~$0.0001 each on Grok 4.1
    Fast). Fires once per location on first scene rendered there, plus once
    whenever the LLM decor-change classifier flags a material change.
    """
    if not image_prompt or not location_id:
        return ""
    sys_msg = (
        "You extract the PHYSICAL SPACE (architecture, materials, fixtures, "
        "fixed furniture, fixed props) of ONE specific location from a Z-Image "
        "Turbo prompt and produce a dense, factual lock that future prompts at "
        "this same location will reuse VERBATIM to keep the room rendering "
        "consistently across scenes.\n\n"
        "REQUIREMENTS — the lock MUST cover, with concrete specifics:\n"
        "  - room/space shape and dimensional feel (long narrow gallery, "
        "low-ceilinged cellar, double-height industrial loft, etc.)\n"
        "  - architectural style and era cues — be specific about what kind of "
        "building this is\n"
        "  - dominant materials with concrete colour + finish (worn oak "
        "floorboards with grey patina, matte black-cement walls, polished brass "
        "counter — never bare 'wood' or 'metal')\n"
        "  - signature furniture pieces named specifically (a curved walnut "
        "bar with brushed-steel footrail, a low Mid-Century teak coffee table, "
        "a buttoned oxblood Chesterfield by the window — not 'a bar', 'a table', "
        "'a sofa')\n"
        "  - wall treatment (paint colour, tile, panelling, art style — without "
        "any text/letters since Z-Image cannot render text)\n"
        "  - fixed atmospheric props (the kind of bottles behind the bar, the "
        "kind of plants by the window, the rug pattern, the fixtures style)\n"
        "  - window/door treatment (arched leaded windows, sliding glass with "
        "brushed-aluminium frame, etc.)\n"
        "  - ceiling and floor signature details when relevant\n\n"
        "When the source prompt is VAGUE about decor ('cosy bar', 'modern "
        "apartment', 'futurist club'), DO NOT echo the vagueness. Commit to "
        "plausible concrete specifics consistent with the location's name, "
        "type, one-line description, and the setting brief. The lock is the "
        "source of truth — a vague lock guarantees visual drift across scenes. "
        "Pick choices that fit THIS specific place, not the default look the "
        "genre is usually drawn with.\n\n"
        "EXCLUDE: people, characters, action, pose, clothing, mood, "
        "time-of-day lighting (sun direction, lamp on/off), weather, "
        "scene-specific atmosphere. Those vary per scene; the SPACE is "
        "constant. Describe the room as it would look in plain ambient light "
        "with nobody in it.\n\n"
        "OUTPUT: a single comma-separated phrase, ~80-150 words, no labels, no "
        "quotes, no commentary. If the source prompt has no decor information at "
        "all (e.g. extreme close-up of a face with no environment visible), "
        "infer plausible decor from the location's name + type + description + "
        "setting and commit to it anyway — a missing lock is worse than a "
        "reasonable inferred lock.\n\n"
        "GOOD: 'long narrow Haussmann-era apartment, 3.5m ceilings with white "
        "ornate cornices, herringbone parquet in honey-toned oak, walls in soft "
        "ivory with a single charcoal-grey accent wall behind a low Mid-Century "
        "teak credenza, tall double french doors opening onto a wrought-iron "
        "balcony, brass picture rail running the perimeter, a buttoned "
        "oxblood-leather Chesterfield by the window, a worn kilim rug in faded "
        "ochre and indigo, a tall floor lamp with brushed-brass arm and "
        "linen-cream shade, two unframed monochrome photographs leaning against "
        "the wall'\n"
        "BAD: 'cosy Parisian apartment with warm decor' (vague, no materials, "
        "no specifics, no signature furniture)\n"
        "BAD: 'modern bar with dark wood and warm lights' (no shape, no "
        "specific materials, no fixed props, no signature furniture)"
    )
    setting_line = setting_label or "(unspecified setting)"
    if custom_setting_text:
        setting_line += f" — custom: {custom_setting_text[:300]}"
    if (prior_lock or "").strip():
        user_msg = (
            f"Location id: `{location_id}`\n"
            f"Location name: {location_name}\n"
            f"Location type: {location_type}\n"
            f"Location one-line description: {location_description or '(none)'}\n"
            f"Setting: {setting_line}\n\n"
            f"PRIOR LOCK (the canonical physical space before this scene — this is the SOURCE "
            f"OF TRUTH for the location's identity, every word matters):\n"
            f"« {prior_lock.strip()} »\n\n"
            f"This is a RE-EXTRACT triggered by the change classifier. The new image prompt "
            f"below describes the SAME location but with a deliberate material change "
            f"(structural damage, redecoration, repainting, fire/smoke damage, conversion, "
            f"or a SIGNATURE permanent fixture/furniture added or removed).\n\n"
            f"Your job: produce the FULL UPDATED LOCK (same shape as a fresh extract — single "
            f"comma-separated phrase). Update ONLY what the new image prompt clearly indicates "
            f"was physically altered. Preserve EVERY OTHER element of the prior lock VERBATIM — "
            f"same room shape, same architectural style, same materials/colours/finishes for "
            f"untouched surfaces, same signature furniture pieces, same fixed props. "
            f"Identity-defining details MUST NOT drift across this re-extract. If the new prompt "
            f"is vague about a detail that's in the prior lock, keep the prior lock's wording "
            f"for it.\n\n"
            f"Image prompt to extract decor from:\n{image_prompt}\n\n"
            f"Output the updated dense decor phrase:"
        )
    else:
        user_msg = (
            f"Location id: `{location_id}`\n"
            f"Location name: {location_name}\n"
            f"Location type: {location_type}\n"
            f"Location one-line description: {location_description or '(none)'}\n"
            f"Setting: {setting_line}\n\n"
            f"Image prompt to extract decor from:\n{image_prompt}\n\n"
            f"Output the dense decor phrase:"
        )
    try:
        resp = await grok_client.chat.completions.create(
            model=grok_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=420,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text.startswith(("'", '"')) and text.endswith(("'", '"')) and len(text) > 2:
            text = text[1:-1].strip()
        return text
    except Exception as e:
        print(f"[scene_agent] extract_decor({location_id}) failed: {e}")
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
