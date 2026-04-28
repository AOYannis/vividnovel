"""
Core orchestration engine.

Drives Grok streaming with function calling, intercepts tool calls
to fire Runware image generation in parallel, and yields SSE events.
"""
import asyncio
import json
import time
import uuid
from typing import AsyncIterator

from openai import AsyncOpenAI
from runware import Runware, IImageInference, ILora, ISafety
from runware.types import IVideoInference, IVideoInputs, ISettings, IAsyncTaskResponse

from config import (
    GROK_MODEL, GROK_PRICING, GROK_BASE_URL, XAI_API_KEY,
    IMAGE_MODEL, IMAGE_WIDTH, IMAGE_HEIGHT, IMAGE_STEPS, IMAGE_CFG, IMAGE_FORMAT,
    DEFAULT_STYLE_LORAS, DEFAULT_STYLE_MOODS, MAX_LORAS_PER_IMAGE,
    ACTOR_REGISTRY, IMAGES_PER_SEQUENCE, SETTINGS,
    VIDEO_MODEL, VIDEO_DURATION, VIDEO_RESOLUTION, VIDEO_DRAFT, VIDEO_AUDIO, VIDEO_SIMULATE, VIDEO_EARLY_START,
    MYSTIC_XXX_ZIT_V5_LORA_ID, SPECIALIST_STYLE_LORA_IDS, ZIT_NSFW_LORA_V2_ID,
)
from tools import ALL_TOOLS
from prompt_builder import build_system_prompt
from memory import (
    MEM0_ENABLED, recall_narrative_context, store_sequence_narrative,
    recall_character_memory, store_character_chat,
)
from logger import SequenceLogger
from davinci import DAVINCI_ENABLED, DAVINCI_TIMEOUT, generate_scene_video as davinci_generate, build_davinci_prompt
from scene_agent import craft_image_prompt, extract_appearance
from mood_gate import gate_mood, infer_mood_from_summary
from presence_gate import gate_presence


import re as _re

# Patterns that indicate agent meta-text, not actual narration
_META_PATTERNS = [
    _re.compile(r'generate_scene_image\s*\(.*?\)', _re.IGNORECASE),
    _re.compile(r'generate_scene_video\s*\(.*?\)', _re.IGNORECASE),
    _re.compile(r'provide_choices\s*\(.*?\)', _re.IGNORECASE),
    _re.compile(r"^(compris|d'accord|entendu|ok|understood|sure|certainly)[,.]?\s*(je |i |let me |voici )", _re.IGNORECASE),
    _re.compile(r"^(je continue|i'?ll continue|continuing|let me continue)", _re.IGNORECASE),
    _re.compile(r'image_index\s*=\s*\d+', _re.IGNORECASE),
]

def _clean_narration(text: str, codename_to_name: dict[str, str] | None = None) -> str:
    """Remove agent meta-text that leaks into narration.

    `codename_to_name`: optional map of cast codenames → resolved story names.
    Any verbatim codename found in the narration is replaced by the story name
    (or stripped if no name is known yet). Catches the introduction-turn slip
    where Grok writes 'white_short' instead of 'Elara'.
    """
    cleaned = text.strip()
    # Remove function call references
    for pat in _META_PATTERNS[:3]:
        cleaned = pat.sub('', cleaned)
    # If the entire text is meta-acknowledgement, drop it
    for pat in _META_PATTERNS[3:]:
        if pat.match(cleaned):
            return ''
    # Scrub verbatim cast codenames the narrator may have leaked
    if codename_to_name:
        for code, name in codename_to_name.items():
            if not code:
                continue
            pattern = _re.compile(rf'\b{_re.escape(code)}\b', _re.IGNORECASE)
            cleaned = pattern.sub(name or '', cleaned)
    # Clean up whitespace artifacts (and stray punctuation left by stripped codenames)
    cleaned = _re.sub(r'\s+([,;:.!?])', r'\1', cleaned)
    cleaned = _re.sub(r'([—–-])\s*\1+', r'\1', cleaned)
    cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = _re.sub(r'  +', ' ', cleaned)
    return cleaned.strip()


class ConsistencyTracker:
    """Tracks visual state for cross-image consistency."""

    def __init__(self):
        self.location: str = ""
        self.clothing: dict[str, str] = {}
        self.props: list[str] = []
        self.previous_prompts: list[str] = []
        self.prompt_overrides: dict[int, str] = {}  # image_index → user-edited prompt
        self.secondary_characters: dict[str, str] = {}  # codename → physical description
        # Lock: character display name → actor codename (first binding wins)
        # Prevents the agent from re-mapping "Camille" from `wh1te` to `nataly` mid-story
        self.character_actors: dict[str, str] = {}
        # Locked head-and-shoulders appearance per actor codename. Captured from
        # the first scene each actor appears in (via a tiny extractor call).
        # Stops hair / face / skin drift across scenes. Soft lock — the narrator
        # can override by saying "her hair is now wet" / etc. in scene_summary.
        self.appearance: dict[str, str] = {}

    def update_from_tool_call(self, args: dict):
        loc = args.get("location_description", "")
        if loc:
            self.location = loc
        for actor, clothing in args.get("clothing_state", {}).items():
            self.clothing[actor] = clothing
        prompt = args.get("image_prompt", "")
        if prompt:
            self.previous_prompts.append(prompt)
            # Auto-extract clothing from prompt if agent didn't fill clothing_state
            # This prevents costume changes between sequences when the agent forgets
            actors = args.get("actors_present", [])
            explicit_clothing = args.get("clothing_state", {})
            if actors and not explicit_clothing:
                self._extract_clothing_from_prompt(prompt, actors)
        # Track secondary characters for cross-scene consistency
        for code, desc in args.get("secondary_characters", {}).items():
            if desc:
                self.secondary_characters[code] = desc
        # Lock character_name → actor_code on first binding (don't overwrite)
        # The agent passes character_names = {codename: display_name} in the tool call.
        char_names = args.get("character_names", {}) or {}
        for code, display_name in char_names.items():
            if not code or not display_name:
                continue
            display_name = display_name.strip()
            if display_name and display_name not in self.character_actors:
                self.character_actors[display_name] = code

    def _extract_clothing_from_prompt(self, prompt: str, actors: list[str]):
        """Best-effort extraction of clothing descriptions from image prompts."""
        import re
        # Match "wearing ..." up to the next clause boundary (action, body part, camera term)
        match = re.search(
            r'wearing\s+(.+?)(?:\.\s|,\s*(?:she|he|her |his |one hand|both hands|eyes|gaze|looking|leaning|standing|sitting|holding|hands|pressed|seen |from |POV|shot on|highly|crisp|in a |at a |on a ))',
            prompt, re.IGNORECASE
        )
        if match:
            clothing_desc = match.group(1).strip().rstrip(',.')
            if actors and clothing_desc and len(clothing_desc) > 5:
                self.clothing[actors[0]] = clothing_desc

    def record_prompt_override(self, image_index: int, new_prompt: str):
        """Record a user-edited prompt to inform future consistency."""
        self.prompt_overrides[image_index] = new_prompt

    def to_dict(self) -> dict:
        return {
            "location": self.location,
            "clothing": dict(self.clothing),
            "props": list(self.props),
            "prompt_overrides": dict(self.prompt_overrides),
            "secondary_characters": dict(self.secondary_characters),
            "character_actors": dict(self.character_actors),
            "appearance": dict(self.appearance),
        }


class GameSession:
    """In-memory game session state."""

    def __init__(self, session_id: str, player: dict, setting: str, cast: dict, user_id: str = "dev-user"):
        self.id = session_id
        self.user_id = user_id
        self.player = player
        self.setting = setting
        self.cast = cast
        self.grok_model: str = GROK_MODEL  # per-session, can be changed
        self.language: str = "fr"  # narration language
        self.consistency = ConsistencyTracker()
        self.sequence_number = 0
        self.conversation_history: list[dict] = []
        self.system_prompt_override: str = ""
        self.custom_setting_text: str = ""
        self.extra_loras: list[dict] = []  # [{"id": "warmline:...", "weight": 0.7}]
        self.style_loras: list[dict] = [dict(s) for s in DEFAULT_STYLE_LORAS]  # mutable copy
        self.style_moods: dict = dict(DEFAULT_STYLE_MOODS)  # mood → LoRA mapping
        # Relationship progress per character (codename -> {level, encounters, last_mood})
        # level: 0=stranger, 1=acquaintance, 2=flirting, 3=close, 4=intimate, 5=lover
        self.relationships: dict[str, dict] = {}
        self.video_settings: dict = {
            "draft": VIDEO_DRAFT,
            "audio": VIDEO_AUDIO,
            "duration": VIDEO_DURATION,
            "resolution": VIDEO_RESOLUTION,
            "simulate": VIDEO_SIMULATE,
            "early_start": VIDEO_EARLY_START,
        }
        self.total_costs = {
            "grok_input_tokens": 0,
            "grok_output_tokens": 0,
            "grok_cost": 0.0,
            "image_cost": 0.0,
            "video_cost": 0.0,
            "total": 0.0,
        }
        # Slice-of-life world state — opt-in (None = classic mode with intro arc)
        from world import WorldState, CharacterState
        self.world: WorldState | None = None
        # Per-character agent states (Phase 2). Populated at game start when
        # slice_of_life=True. dict[codename → CharacterState].
        self.character_states: dict[str, CharacterState] = {}
        # Player-known whereabouts (Phase 2B): things the player has been TOLD
        # about future character locations. Source: dialogue extractor.
        # Each entry: {char, location_id, day, slot, source, is_rendezvous?, missed?, kept?}
        self.known_whereabouts: list[dict] = []
        # Missed rendez-vous events that haven't been mentioned in narration yet.
        # Cleared once the narrator has had one chance to weave them in. List of
        # {char, location_id, day, slot, source} (the original whereabouts entry).
        self.recent_missed_rendezvous: list[dict] = []


class StoryEngine:
    """Orchestrates Grok narration + Runware image generation pipeline."""

    def __init__(self, grok_client: AsyncOpenAI, runware_client: Runware):
        self.grok = grok_client
        self.runware = runware_client

    async def run_sequence(
        self, session: GameSession, choice_id: str | None = None, choice_text: str | None = None,
    ) -> AsyncIterator[dict]:
        """
        Generator that yields SSE events for one story sequence.
        Uses an asyncio.Queue to merge Grok stream events and image completion events.
        """
        queue: asyncio.Queue = asyncio.Queue()

        # Run orchestration in background, push events to queue
        task = asyncio.create_task(
            self._orchestrate(session, choice_id, choice_text, queue)
        )

        # Yield events from queue until done
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

        # Propagate exceptions
        if task.done() and task.exception():
            yield {"type": "error", "message": str(task.exception())}

    async def _orchestrate(
        self, session: GameSession, choice_id: str | None,
        choice_text: str | None, queue: asyncio.Queue,
    ):
        """Main orchestration loop: Grok streaming + tool call interception."""
        log = SequenceLogger(session.id, session.sequence_number, session.grok_model)
        try:
            # Store session config for _generate_image to use
            self._session_moods = session.style_moods
            if hasattr(session, '_custom_actor_override'):
                self._custom_override = session._custom_actor_override

            # ── Adjudicate past rendez-vous (Feature 1 follow-up) ──────────
            # Walk every PAST rdv and decide: kept (player was there) vs missed.
            # Missed RDVs apply a relationship penalty (level -1, clamped 0) AND
            # are stashed on session.recent_missed_rendezvous so the next
            # encounter's prompt can mention it in narration.
            if session.world and session.known_whereabouts:
                from world import adjudicate_past_rendezvous
                missed, kept = adjudicate_past_rendezvous(session.world, session.known_whereabouts)
                for w in missed:
                    code = w.get("char")
                    if code and code in session.relationships:
                        rel = session.relationships[code]
                        prev = int(rel.get("level", 0) or 0)
                        rel["level"] = max(0, prev - 1)
                        print(f"[rdv] MISSED — {code} relationship dropped {prev}→{rel['level']} "
                              f"(rdv at {w.get('location_id')}/{w.get('slot')} day {w.get('day')})")
                    session.recent_missed_rendezvous.append(w)
                if kept:
                    for w in kept:
                        print(f"[rdv] KEPT — {w.get('char')} at {w.get('location_id')}/{w.get('slot')} day {w.get('day')}")

            # ── Daily tick (Phase 5) ────────────────────────────────────
            # Advance each character's inner life ONCE per game day. Updates
            # today_mood / intentions_toward_player / recent_event so the
            # narrator gets a fresh signal to play with each new day.
            if session.world and session.character_states:
                _needs_tick = any(
                    (cs.last_tick_day or 0) < session.world.day
                    for cs in session.character_states.values()
                )
                if _needs_tick:
                    try:
                        from agent import daily_tick as _daily_tick
                        from config import SETTINGS as _SETTINGS
                        _setting_label = (
                            _SETTINGS.get(session.setting, {}).get("label")
                            or session.custom_setting_text[:80]
                            or session.setting
                            or ""
                        )
                        _updates = await _daily_tick(
                            self.grok,
                            session.character_states,
                            session.relationships,
                            session.world.day,
                            _setting_label,
                            custom_setting_text=session.custom_setting_text or "",
                            grok_model=session.grok_model,
                        )
                        for code, payload in (_updates or {}).items():
                            cs = session.character_states.get(code)
                            if not cs:
                                continue
                            if payload.get("today_mood"):
                                cs.today_mood = payload["today_mood"]
                            if payload.get("intentions_toward_player"):
                                cs.intentions_toward_player = payload["intentions_toward_player"]
                            if payload.get("recent_event"):
                                cs.recent_event = payload["recent_event"]
                            cs.last_tick_day = session.world.day
                            print(f"[tick] {code} (day {session.world.day}): "
                                  f"mood={cs.today_mood!r} intent={cs.intentions_toward_player!r} "
                                  f"event={cs.recent_event[:60]!r}")
                    except Exception as e:
                        print(f"[tick] daily_tick failed: {e}; characters keep yesterday's state")

            # Resolve which characters are present at the current location/slot.
            # The list is what build_system_prompt uses to inject FULL agent
            # context only for the relevant characters (vs dumping all bios).
            present_characters: list[str] = []
            rendezvous_here_now: list[dict] = []  # rendez-vous matching THIS loc + slot
            if session.world and session.character_states:
                from world import who_is_at, imminent_rendezvous
                present_characters = who_is_at(
                    session.world.current_location,
                    session.world.day,
                    session.world.slot,
                    session.character_states,
                )
                # ── Early-game presence cap ──
                # Sequence 0 (the very first one): always solo so the player can
                # breathe and find their bearings before any encounter.
                # Sequences 1-2: cap at ONE character max — even if the resolver
                # placed several at the same location, pick the first one only.
                # Sequence 3+: no cap — the world is fully alive.
                if session.sequence_number == 0:
                    if present_characters:
                        print(f"[slice] Forcing solo first sequence (resolver had {present_characters})")
                    present_characters = []
                elif session.sequence_number in (1, 2) and len(present_characters) > 1:
                    print(f"[slice] Capping early sequence to 1 char (resolver had {present_characters})")
                    present_characters = present_characters[:1]

                # ── Rendez-vous override (Feature 1) ─────────────────────────
                # A rendez-vous IS a meeting — it overrides the early-game cap
                # and the resolver. If a character has agreed to meet the player
                # at THIS location AND it's NOW (status=='now'), force their
                # presence so the encounter actually happens.
                rdv_imminent = imminent_rendezvous(
                    session.world,
                    session.known_whereabouts or [],
                )
                rendezvous_here_now = [
                    r for r in rdv_imminent
                    if r.get("status") == "now"
                    and r.get("location_id") == session.world.current_location
                ]
                for r in rendezvous_here_now:
                    code = r.get("char")
                    if code and code not in present_characters:
                        present_characters.append(code)
                        print(f"[slice] RENDEZ-VOUS override: {code} forced into "
                              f"present_characters (rdv at {r.get('location_id')}/{r.get('slot')})")

            # Compute "next-slot" rendez-vous teasers for the prompt: rdvs with
            # status='next' that are NOT also already-here-now (those win above).
            rendezvous_next: list[dict] = []
            if session.world and session.character_states:
                from world import imminent_rendezvous as _imm
                _next = _imm(session.world, session.known_whereabouts or [])
                _here_chars = {r.get("char") for r in rendezvous_here_now}
                rendezvous_next = [r for r in _next if r.get("status") == "next" and r.get("char") not in _here_chars]

            # Surface any not-yet-narrated missed RDVs to the prompt. We hand the
            # whole list once and clear it — the narrator gets ONE chance to weave
            # the consequences in (a cold greeting, a sharp comment, etc.).
            missed_to_narrate = list(session.recent_missed_rendezvous)
            session.recent_missed_rendezvous.clear()

            # Build system prompt
            system_prompt = session.system_prompt_override or build_system_prompt(
                player=session.player,
                cast=session.cast,
                setting_id=session.setting,
                consistency_state=session.consistency.to_dict(),
                sequence_number=session.sequence_number,
                previous_choice=choice_text,
                custom_setting_text=session.custom_setting_text,
                style_moods=session.style_moods,
                custom_actor_override=getattr(session, '_custom_actor_override', None),
                language=session.language,
                relationships=session.relationships,
                world=session.world,
                character_states=session.character_states,
                present_characters=present_characters,
                rendezvous_here_now=rendezvous_here_now,
                rendezvous_next=rendezvous_next,
                recent_missed_rendezvous=missed_to_narrate,
            )

            # Mem0 memory recall (session-scoped only — no cross-session contamination)
            persistent_memory = ""
            narrative_memory = ""

            # Recall session narrative memories (current game, previous sequences only)
            if MEM0_ENABLED and session.sequence_number > 0:
                try:
                    narrative_memory = recall_narrative_context(
                        session_id=session.id,
                        user_id=session.user_id,
                    )
                    if narrative_memory:
                        log.log_mem0_recall("narrative", narrative_memory)
                        system_prompt += "\n\n" + narrative_memory
                except Exception:
                    pass  # Mem0 failure should never block the game

            # Recall per-character memories (what each character knows about the player)
            if MEM0_ENABLED and session.sequence_number > 0:
                try:
                    cast_codes = session.cast.get("actors", [])
                    char_memories = []
                    for char_code in cast_codes:
                        if not char_code:
                            continue
                        char_mem = recall_character_memory(session.user_id, char_code, setting_id=session.setting)
                        if char_mem:
                            display = ACTOR_REGISTRY.get(char_code, {}).get("display_name", char_code)
                            char_memories.append(f"### Ce que {display} sait sur le joueur\n{char_mem}")
                            log.log_mem0_recall(f"character:{char_code}", char_mem)
                    if char_memories:
                        system_prompt += (
                            "\n\n## Mémoire des personnages\n"
                            "Chaque personnage se souvient de ses interactions avec le joueur. "
                            "Utilise ces souvenirs pour des réactions PERSONNALISÉES — "
                            "le personnage fait référence à ce qu'il sait, naturellement.\n\n"
                            + "\n\n".join(char_memories)
                        )
                except Exception:
                    pass  # Mem0 failure should never block the game

            model = session.grok_model
            pricing = GROK_PRICING.get(model, {"input": 0.20, "output": 0.50})
            log.log_system_prompt(len(system_prompt), bool(persistent_memory), bool(narrative_memory))

            # Emit debug context (full system prompt + memories) for debug panel
            await queue.put({
                "type": "debug_context",
                "system_prompt_length": len(system_prompt),
                "persistent_memory": persistent_memory,
                "narrative_memory": narrative_memory,
                "grok_model": model,
                "sequence_number": session.sequence_number,
            })

            # Initialize messages for this sequence
            messages = [{"role": "system", "content": system_prompt}]

            # Build narrative context from previous sequence's conversation history.
            # Instead of raw messages (mostly tool-call noise), extract only the
            # narration text and the choice — this gives Grok a clear story thread.
            if session.conversation_history:
                prev_narration_parts = []
                for msg in session.conversation_history:
                    if msg.get("role") == "assistant" and msg.get("content"):
                        prev_narration_parts.append(msg["content"].strip())
                if prev_narration_parts:
                    recap = "\n\n".join(prev_narration_parts)
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Voici le résumé de la séquence précédente (pour contexte narratif, "
                            f"ne pas répéter) :\n\n{recap}"
                        ),
                    })
                    messages.append({
                        "role": "assistant",
                        "content": "Compris, je continue l'histoire à partir de ce point.",
                    })

            if choice_text and session.sequence_number > 0:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Le joueur a choisi : \"{choice_text}\". "
                        f"Continue : écris 1-2 phrases pour la scène 0, puis appelle generate_scene_image(image_index=0)."
                    ),
                })
            elif session.sequence_number > 0:
                # Resumed session without an explicit choice — continue from context
                messages.append({
                    "role": "user",
                    "content": (
                        f"Le joueur reprend l'histoire. Écris 1-2 phrases pour la scène 0, "
                        f"puis appelle generate_scene_image(image_index=0). "
                        f"Répète pour chaque scène jusqu'à {IMAGES_PER_SEQUENCE - 1}, puis provide_choices avec 4 choix."
                    ),
                })
            else:
                cast_codes_str = ", ".join(session.cast.get("actors", []))
                messages.append({
                    "role": "user",
                    "content": (
                        f"Commence l'histoire. Le joueur arrive dans UN lieu ou UNE situation "
                        f"où il va naturellement croiser plusieurs personnes (casting disponible : "
                        f"{cast_codes_str}). Pas un défilé — une scène vivante où les gens se "
                        f"croisent, s'interrompent, coexistent. Présente environ la moitié du casting "
                        f"dans cette séquence, le reste viendra naturellement après.\n"
                        f"\nÉcris 1-2 phrases pour la scène 0 (installation du décor + le joueur seul), "
                        f"puis appelle generate_scene_image(image_index=0). "
                        f"Répète pour chaque scène jusqu'à {IMAGES_PER_SEQUENCE - 1}, puis provide_choices."
                    ),
                })

            image_tasks: dict[int, asyncio.Task] = {}
            completed_images: dict[int, dict] = {}
            scene_actors: dict[int, list[str]] = {}  # image_index → actors_present (for DB persistence)
            davinci_fire_tasks: list[asyncio.Task] = []  # track _fire_davinci tasks
            video_task: asyncio.Task | None = None
            video_early_started = False
            images_generated = 0
            narration_segments_acc: list[str] = []  # accumulate narration for davinci prompts
            tts_tasks_by_idx: dict[int, asyncio.Task] = {}  # per-scene TTS tasks (fired at tool-call time)
            choices_provided = False
            sequence_start = time.time()
            grok_input_tokens = 0
            grok_output_tokens = 0
            grok_cached_tokens = 0  # cumulative across rounds — measures cache hit effectiveness
            # TTS cost accumulators (mutated by concurrent _fire_tts_task; safe under
            # asyncio's single-thread model where += is atomic). Engine is per-sequence
            # so these reset naturally on each call.
            self._tts_audio_cost_total = 0.0      # Runware/xAI TTS audio bytes
            self._tts_enhance_input_tokens = 0    # Grok enhance call input tokens (cumulative)
            self._tts_enhance_output_tokens = 0
            self._tts_enhance_cached_tokens = 0
            # Per-scene video cost accumulator — P-Video and Davinci tasks fire
            # concurrently and emit costs via scene_video_ready events, but those
            # need to be summed back into the per-sequence total.
            self._scene_video_cost_total = 0.0

            # Loop: stream Grok, intercept tool calls, fire images, continue
            early_start = session.video_settings.get("early_start", False)

            log.log_messages(messages)
            for round_num in range(IMAGES_PER_SEQUENCE + 4):  # safety limit
                # Check for completed images at the start of each round
                await self._flush_completed_images(
                    image_tasks, completed_images, queue,
                    narration_segments=narration_segments_acc, session=session,
                    tts_tasks=tts_tasks_by_idx,
                )

                # Early video start: fire video gen as soon as image 0 is ready
                if early_start and not video_early_started and 0 in completed_images:
                    first_url = completed_images[0].get("url", "")
                    if first_url:
                        video_early_started = True
                        # Use a generic prompt for early start (will be replaced if LLM provides one later)
                        early_prompt = (
                            "Subtle breathing motion, gentle eye movement, soft ambient sound, "
                            "barely perceptible slow push-in, static background, looping motion"
                        )
                        video_task = asyncio.create_task(
                            self._generate_video(early_prompt, first_url, session.video_settings)
                        )
                        await queue.put({
                            "type": "video_requested",
                            "prompt": early_prompt + " (early start from image 0)",
                            "input_image_index": 0,
                        })

                # x-grok-conv-id: stable per-session header that xAI uses to
                # route subsequent requests to the same prompt-cache shard,
                # maximising hit rate (~75% off cached input tokens).
                # stream_options.include_usage: surface the final usage object
                # (incl. prompt_tokens_details.cached_tokens) on the last chunk
                # so we can measure actual cache hit rate per round.
                stream = await self.grok.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=ALL_TOOLS,
                    parallel_tool_calls=False,
                    stream=True,
                    stream_options={"include_usage": True},
                    extra_headers={"x-grok-conv-id": session.id} if session and getattr(session, "id", None) else None,
                )

                content_acc = ""
                tool_calls_acc: dict[int, dict] = {}
                finish_reason = None
                round_usage = None  # populated by the final chunk when stream_options.include_usage is set

                async for chunk in stream:
                    # The final chunk in an include_usage stream carries `usage` with
                    # `prompt_tokens`, `completion_tokens`, and `prompt_tokens_details.cached_tokens`.
                    # That chunk has an empty `choices` array, so we capture usage and skip.
                    if getattr(chunk, "usage", None):
                        round_usage = chunk.usage
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta

                    # Narration text
                    if delta.content:
                        content_acc += delta.content
                        await queue.put({
                            "type": "narration_delta",
                            "content": delta.content,
                        })

                    # Tool call deltas (accumulate)
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": "",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["arguments"] += tc.function.arguments

                    # Opportunistically check for completed images
                    for img_idx, img_task in list(image_tasks.items()):
                        if img_task.done() and img_idx not in completed_images:
                            await self._emit_image_result(
                                img_idx, img_task, completed_images, queue,
                                narration_segments=narration_segments_acc, session=session,
                                _log=log, davinci_fire_tasks=davinci_fire_tasks,
                                tts_tasks=tts_tasks_by_idx,
                            )

                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                # Token accounting — prefer real usage from the API; fall back to
                # char-based estimate if the include_usage stream didn't deliver
                # (older models, network truncation, etc.).
                if round_usage is not None:
                    grok_input_tokens += getattr(round_usage, "prompt_tokens", 0) or 0
                    grok_output_tokens += getattr(round_usage, "completion_tokens", 0) or 0
                    details = getattr(round_usage, "prompt_tokens_details", None)
                    if details is not None:
                        grok_cached_tokens += getattr(details, "cached_tokens", 0) or 0
                else:
                    grok_input_tokens += len(json.dumps(messages).encode()) // 4
                    grok_output_tokens += len(content_acc.encode()) // 4

                # Handle based on finish reason
                if finish_reason == "tool_calls" and tool_calls_acc:
                    # Build assistant message
                    assistant_tool_calls = []
                    for idx in sorted(tool_calls_acc.keys()):
                        tc = tool_calls_acc[idx]
                        assistant_tool_calls.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        })

                    messages.append({
                        "role": "assistant",
                        "content": content_acc or None,
                        "tool_calls": assistant_tool_calls,
                    })

                    # Accumulate narration for Davinci prompts (after cleaning)
                    if content_acc:
                        # Build codename → story-name map for the scrubber. Catches
                        # introduction-turn leaks ('white_short' before Elara is locked).
                        # Sources: already-locked names in consistency, plus character_names
                        # from tool calls in THIS round (not yet committed to consistency).
                        cast_codes = [c for c in (session.cast.get("actors") or []) if c]
                        code_to_name = {code: "" for code in cast_codes}
                        for display_name, code in (session.consistency.character_actors or {}).items():
                            if code:
                                code_to_name[code] = display_name
                        for _tc in assistant_tool_calls:
                            try:
                                _args = json.loads(_tc["function"]["arguments"])
                            except (json.JSONDecodeError, KeyError):
                                continue
                            for code, display_name in (_args.get("character_names") or {}).items():
                                if code and display_name and not code_to_name.get(code):
                                    code_to_name[code] = display_name
                        cleaned = _clean_narration(content_acc, code_to_name)
                        if cleaned:
                            narration_segments_acc.append(cleaned)

                    # Log the round
                    tool_names = [tc["function"]["name"] for tc in assistant_tool_calls]
                    log.log_grok_round(round_num, len(content_acc), tool_names)

                    # Process each tool call
                    for tc_data in assistant_tool_calls:
                        fn_name = tc_data["function"]["name"]
                        try:
                            args = json.loads(tc_data["function"]["arguments"])
                        except json.JSONDecodeError:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_data["id"],
                                "content": '{"error": "invalid JSON"}',
                            })
                            continue

                        if fn_name == "generate_scene_image":
                            image_index = args.get("image_index", images_generated)
                            images_generated += 1

                            # ── Phase 3A: image-prompt specialist ──────────────
                            # Narrator sends a lean spec (scene_summary + shot_intent
                            # + single mood name). The specialist composes the actual
                            # Z-Image prompt + we normalise mood → style_moods list
                            # so the rest of the pipeline (relationship scoring, LoRA
                            # stacking, TTS, consistency tracker) keeps working.
                            scene_summary = (args.get("scene_summary") or "").strip()
                            shot_intent = (args.get("shot_intent") or "").strip()
                            requested_mood = (args.get("mood") or "neutral").strip() or "neutral"
                            requested_actors = args.get("actors_present", []) or []

                            # Phase 3D follow-up: server-side presence gate (slice mode).
                            # Strips cast members the resolver did NOT place at the current
                            # location/slot. In SOLO mode (no allowed cast at all) we extend
                            # the strip set to ALL ACTOR_REGISTRY entries — otherwise pool
                            # actors slip through (Grok will guess a codename like 'nesra'
                            # and the LoRA loads coincidentally).
                            slice_enforce = session.world is not None
                            if slice_enforce and not present_characters:
                                _gated = list(ACTOR_REGISTRY.keys())
                            else:
                                _gated = session.cast.get("actors", []) or []
                            actors_present, gate_removed = gate_presence(
                                requested_actors,
                                cast_codes=_gated,
                                allowed_cast=present_characters if slice_enforce else None,
                                enforce=slice_enforce,
                            )
                            if gate_removed:
                                print(f"[presence_gate] scene {image_index}: stripped {gate_removed} "
                                      f"(allowed={present_characters})")
                                # Also strip them from character_names so the lock isn't created
                                _names = args.get("character_names") or {}
                                for _code in gate_removed:
                                    _names.pop(_code, None)
                                args["character_names"] = _names
                                args["actors_present"] = actors_present

                            # Auto-promote: if narrator picked `neutral` but the
                            # scene_summary clearly says "missionary" / "kiss" / etc.,
                            # lift the mood to the matching position. Catches the
                            # over-cautious narrator that defaults to neutral while
                            # writing explicit prose.
                            promoted = infer_mood_from_summary(scene_summary, requested_mood)
                            if promoted:
                                print(f"[mood_gate] scene {image_index}: auto-promoted "
                                      f"{requested_mood!r} → {promoted!r} from scene_summary")
                                requested_mood = promoted

                            # Phase 3C: server-side mood gate (relationship-level rule).
                            mood_name, mood_downgraded = gate_mood(
                                requested_mood, actors_present, session.relationships
                            )
                            if mood_downgraded:
                                print(f"[mood_gate] scene {image_index}: {requested_mood!r} → {mood_name!r} "
                                      f"(actors={actors_present}, relationships gated)")

                            actor_genders_map = (session.cast or {}).get("actor_genders", {}) or {}
                            actor_lookup: dict[str, dict] = {}
                            for code in actors_present:
                                base = ACTOR_REGISTRY.get(code) or {}
                                if code == "custom" and getattr(self, "_custom_override", None):
                                    base = {**base, **self._custom_override}
                                actor_lookup[code] = {
                                    "trigger_word": base.get("trigger_word"),
                                    "prompt_prefix": base.get("prompt_prefix"),
                                    "description": base.get("description"),
                                    "gender": actor_genders_map.get(code, "female"),
                                }

                            mood_data = (session.style_moods or DEFAULT_STYLE_MOODS).get(mood_name)

                            location_hint = args.get("location_description") or ""
                            if not location_hint and session.world is not None:
                                _loc = session.world.location_by_id(session.world.current_location)
                                if _loc:
                                    location_hint = f"{_loc.name} ({_loc.type}) — {_loc.description}"

                            setting_label = (
                                SETTINGS.get(session.setting, {}).get("label")
                                or session.custom_setting_text[:80]
                                or session.setting
                                or ""
                            )

                            # Clothing: merge consistency tracker (locked outfits from
                            # earlier scenes) with this scene's args (narrator may have
                            # declared a change). args wins per-actor — so a deliberate
                            # outfit change overrides the lock.
                            merged_clothing: dict[str, str] = dict(session.consistency.clothing or {})
                            for _ac, _cl in (args.get("clothing_state") or {}).items():
                                if _cl:
                                    merged_clothing[_ac] = _cl

                            # Locked head/shoulders appearance from prior scenes.
                            appearance_state = dict(session.consistency.appearance or {})

                            # Time of day from world.slot — the specialist needs it to
                            # pick lighting that doesn't default to bright daylight.
                            tod = session.world.slot if session.world else None

                            crafted_prompt, craft_elapsed = await craft_image_prompt(
                                self.grok,
                                scene_index=image_index,
                                scene_summary=scene_summary,
                                shot_intent=shot_intent,
                                actors_present=actors_present,
                                mood_name=mood_name,
                                actor_lookup=actor_lookup,
                                mood_data=mood_data,
                                setting_label=setting_label,
                                custom_setting_text=session.custom_setting_text or "",
                                location_hint=location_hint,
                                clothing_state=merged_clothing,
                                appearance_state=appearance_state,
                                time_of_day=tod,
                                language=session.language or "fr",
                                player_gender=(session.player or {}).get("gender", "male"),
                                grok_model=session.grok_model,
                            )

                            # Capture appearance for any cast member appearing for the
                            # FIRST time. Fire-and-forget: a per-actor extractor call
                            # so subsequent scenes can lock the look. Skipped on retry
                            # if the extractor fails / returns empty.
                            for _ac in actors_present:
                                if _ac and _ac not in session.consistency.appearance:
                                    try:
                                        _look = await extract_appearance(
                                            self.grok,
                                            codename=_ac,
                                            image_prompt=crafted_prompt,
                                            grok_model=session.grok_model,
                                        )
                                        if _look:
                                            session.consistency.appearance[_ac] = _look
                                            print(f"[appearance] locked {_ac}: {_look[:80]}")
                                    except Exception as _e:
                                        print(f"[appearance] extract for {_ac} failed: {_e}")

                            # Inject specialist output back into args so downstream
                            # code (consistency tracker, _generate_image, frontend
                            # event payload) sees the materialised prompt.
                            args["image_prompt"] = crafted_prompt
                            args["style_moods"] = ["neutral"] if mood_name == "neutral" else [mood_name]

                            log.log_image_prompt_crafted(
                                image_index, scene_summary, shot_intent, mood_name,
                                actors_present, crafted_prompt, craft_elapsed,
                            )

                            # Log the image request
                            log.log_image_request(
                                image_index,
                                crafted_prompt,
                                actors_present,
                                args["style_moods"],
                                args.get("secondary_characters", {}),
                            )

                            # Update relationship progress for actors in the scene.
                            # Use the REQUESTED (post-promotion) mood, not the post-gate
                            # one — otherwise trust never grows when the gate is active
                            # (Catch-22: gate downgrades to neutral, level stays at 1,
                            # next scene still gated, infinite loop).
                            rel_actors = actors_present
                            rel_moods = [requested_mood]
                            for actor_code in rel_actors:
                                if actor_code not in session.relationships:
                                    session.relationships[actor_code] = {
                                        "level": 0, "encounters": 0, "scenes": 0,
                                        "intimate_scenes": 0, "last_mood": "neutral",
                                    }
                                rel = session.relationships[actor_code]
                                rel["scenes"] += 1
                                rel["last_mood"] = rel_moods[0] if rel_moods else "neutral"
                                # Bump level based on mood
                                _intimate_moods = {"explicit_mystic", "blowjob", "blowjob_closeup", "cunnilingus",
                                                   "cunnilingus_from_behind", "missionary", "cowgirl",
                                                   "reverse_cowgirl", "doggystyle", "spooning", "standing_sex",
                                                   "anal_doggystyle", "anal_missionary", "anal_missionary_shemale",
                                                   "cumshot_face", "titjob", "handjob"}
                                if any(m in _intimate_moods for m in rel_moods):
                                    rel["intimate_scenes"] += 1
                                    rel["level"] = max(rel["level"], 4)
                                elif "sensual_tease" in rel_moods or "kiss" in rel_moods:
                                    rel["level"] = max(rel["level"], min(rel["level"] + 1, 3), 2)
                                else:
                                    rel["level"] = max(rel["level"], 1)
                                # Promote to lover after multiple intimate scenes
                                if rel["intimate_scenes"] >= 3:
                                    rel["level"] = 5

                            # Fire image gen (non-blocking)
                            img_task = asyncio.create_task(
                                self._generate_image(args, session.cast, session.style_loras, session.extra_loras, _log=log)
                            )
                            image_tasks[image_index] = img_task

                            # ── Fire TTS NOW (concurrent with image gen) — audio is ready
                            #    by the time the user lands on the scene, instead of waiting
                            #    for the image to finish first. ────────────────────────────
                            voice_narration_on = session.video_settings.get("voice_narration", False) if session else False
                            if voice_narration_on:
                                v_voice = session.video_settings.get("voice_id", "ara") if session else "ara"
                                v_lang = session.video_settings.get("voice_language", "fr") if session else "fr"
                                v_enhance = session.video_settings.get("voice_enhance", True) if session else True
                                v_stereo = session.video_settings.get("voice_stereo", True) if session else True
                                v_to_video = session.video_settings.get("voice_to_video", False) if session else False
                                v_backend = session.video_settings.get("video_backend", "pvideo") if session else "pvideo"
                                v_start_scene = session.video_settings.get("video_start_scene", 0) if session else 0
                                v_narration_voice = session.video_settings.get("narration_voice", "sal") if session else "sal"
                                v_actor_voices = (session.cast or {}).get("actor_voices", {}) if session else {}
                                # Same logic as _emit_image_result for dialogue-only / for_video_only:
                                # only when this scene will actually get a P-Video that uses our audio.
                                will_have_video = (v_backend == "pvideo") and (image_index >= v_start_scene)
                                wants_dialogue_only = bool(v_to_video and will_have_video)
                                # Use the latest narration appended for this round
                                ntext = narration_segments_acc[-1] if narration_segments_acc else ""
                                if ntext.strip():
                                    # Lipsync-mode TTS only makes sense when there IS dialogue.
                                    # If the scene is pure narration (no quoted lines), forcing
                                    # the video to lip-sync narration audio looks wrong (the
                                    # character mouths the narrator's words, in the narrator's
                                    # voice). Detect early and route accordingly:
                                    #   - has dialogue → dialogue-only TTS for video lipsync
                                    #     (existing behaviour)
                                    #   - no dialogue + lipsync wanted → standalone narration
                                    #     TTS so the user still hears the scene; SKIP the
                                    #     video-bound TTS so video gen falls back to its
                                    #     prompt-only path (ambient sounds, breath, etc.)
                                    use_dialogue_only = wants_dialogue_only
                                    register_for_video = wants_dialogue_only
                                    if wants_dialogue_only:
                                        from tts import extract_dialogue
                                        if not extract_dialogue(ntext).strip():
                                            print(f"[tts] Scene {image_index}: no dialogue in narration "
                                                  f"— skipping lipsync TTS, firing standalone narration only "
                                                  f"(video will use prompt-only ambient).")
                                            use_dialogue_only = False
                                            register_for_video = False
                                    tts_task = self._launch_tts(
                                        image_index, ntext, queue,
                                        sequence_number=session.sequence_number if session else 0,
                                        voice=v_voice, language=v_lang, enhance=v_enhance,
                                        session_id=session.id if session else "",
                                        dialogue_only=use_dialogue_only,
                                        for_video_only=use_dialogue_only,
                                        stereo=v_stereo,
                                        log_ref=log,
                                        narration_voice=v_narration_voice,
                                        actor_voices=v_actor_voices,
                                        actors_present=actors_present,
                                    )
                                    if register_for_video:
                                        tts_tasks_by_idx[image_index] = tts_task

                            scene_actors[image_index] = list(args.get("actors_present", []) or [])
                            await queue.put({
                                "type": "image_requested",
                                "index": image_index,
                                "prompt": args.get("image_prompt", ""),
                                "actors_in_scene": args.get("actors_present", []),
                                "location": args.get("location_description", ""),
                                "character_names": args.get("character_names", {}),
                            })

                            # Update consistency tracker
                            session.consistency.update_from_tool_call(args)

                            # Synthetic tool result — instruct Grok to continue with next narration
                            next_idx = image_index + 1
                            if next_idx < IMAGES_PER_SEQUENCE:
                                tool_msg = (
                                    f"Image {image_index} is generating. "
                                    f"Now write scene {next_idx}: 1 short sentence of stage direction "
                                    f"+ 1 dialogue line (max 20 words). Remember: this scene = 10 seconds "
                                    f"of video, ONE moment only. Then call generate_scene_image "
                                    f"with image_index={next_idx}."
                                )
                            else:
                                _vb = session.video_settings.get("video_backend", "pvideo") if session else "pvideo"
                                if _vb in ("davinci", "pvideo"):
                                    # Per-scene videos handled automatically — skip generate_scene_video tool
                                    tool_msg = (
                                        f"Image {image_index} is generating. "
                                        f"All {IMAGES_PER_SEQUENCE} images done. Videos are generated automatically. "
                                        f"Now call provide_choices with 4 choices."
                                    )
                                else:
                                    tool_msg = (
                                        f"Image {image_index} is generating. "
                                        f"All {IMAGES_PER_SEQUENCE} images done. "
                                        f"Now call provide_choices with 4 choices."
                                    )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_data["id"],
                                "content": tool_msg,
                            })

                        elif fn_name == "generate_scene_video":
                            video_prompt = args.get("video_prompt", "")
                            session._last_video_prompt = video_prompt
                            log.log_video_request(video_prompt, max(image_tasks.keys()) if image_tasks else 4)

                            _vb = session.video_settings.get("video_backend", "pvideo")
                            if _vb in ("davinci", "pvideo"):
                                # Per-scene videos handled automatically — skip legacy P-Video
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc_data["id"],
                                    "content": "Video handled automatically. Call provide_choices.",
                                })
                                continue

                            if video_early_started and video_task is not None:
                                # Early start already fired — video is generating or done
                                # Just record the LLM's prompt for persistence
                                pass
                            else:
                                # Normal flow: use the last image as input
                                last_img_idx = max(image_tasks.keys()) if image_tasks else 4
                                last_img_task = image_tasks.get(last_img_idx)
                                if last_img_task and not last_img_task.done():
                                    last_result = await last_img_task
                                    completed_images[last_img_idx] = last_result
                                    await queue.put({
                                        "type": "image_ready",
                                        "index": last_img_idx,
                                        "url": last_result["url"],
                                        "cost": last_result["cost"],
                                        "seed": last_result.get("seed"),
                                        "generation_time": last_result["elapsed"],
                                        "settings": last_result.get("settings"),
                                    })
                                last_url = completed_images.get(last_img_idx, {}).get("url", "")

                                if last_url:
                                    video_task = asyncio.create_task(
                                        self._generate_video(video_prompt, last_url, session.video_settings)
                                    )
                                    await queue.put({
                                        "type": "video_requested",
                                        "prompt": video_prompt,
                                        "input_image_index": last_img_idx,
                                    })

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_data["id"],
                                "content": (
                                    "Video generation started. "
                                    "Now call provide_choices with 3 choices for the player."
                                ),
                            })

                        elif fn_name == "provide_choices":
                            choices = args.get("choices", [])
                            choices_provided = True
                            log.log_choices(choices)

                            await queue.put({
                                "type": "choices_available",
                                "choices": choices,
                            })

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_data["id"],
                                "content": '{"status": "choices_presented"}',
                            })

                elif finish_reason == "stop":
                    # Grok ended a turn with text but no tool call. Two cases:
                    #   - images_generated == 0: never started → bail with error.
                    #   - images_generated < IMAGES_PER_SEQUENCE: stopped mid-sequence.
                    #     This happens with very lean prompts (slice solo) where the model
                    #     decides it's done early. Nudge it to keep going.
                    print(f"[engine] WARNING: finish_reason=stop on round {round_num} with "
                          f"{images_generated} images so far, content_acc len={len(content_acc)}")
                    log.log_error(
                        f"Grok stopped without calling a tool on round {round_num} "
                        f"(images_generated={images_generated}, content_len={len(content_acc)}). "
                        f"Last content: {content_acc[:200]!r}"
                    )
                    if images_generated == 0:
                        await queue.put({
                            "type": "error",
                            "message": "Grok produced narration but didn't call generate_scene_image. "
                                       "This usually self-resolves on retry — please start the sequence again.",
                        })
                        break
                    if not choices_provided and images_generated < IMAGES_PER_SEQUENCE:
                        # Mid-sequence early stop — push a synthetic user message asking
                        # for the next scene and continue the loop.
                        next_idx = images_generated
                        messages.append({
                            "role": "user",
                            "content": (
                                f"La séquence n'est pas terminée. Il reste "
                                f"{IMAGES_PER_SEQUENCE - images_generated} scène(s) à écrire "
                                f"(prochaine = scène {next_idx}). Écris 1-2 phrases courtes, "
                                f"puis appelle generate_scene_image avec image_index={next_idx}. "
                                f"Continue dans le même lieu et la même ambiance."
                            ),
                        })
                        continue
                    if images_generated >= IMAGES_PER_SEQUENCE and not choices_provided:
                        # All images done but Grok forgot provide_choices — nudge.
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Toutes les {IMAGES_PER_SEQUENCE} scènes sont générées. "
                                f"Appelle maintenant provide_choices avec exactement 4 choix."
                            ),
                        })
                        continue
                    break
                elif finish_reason and finish_reason not in ("tool_calls",):
                    # Anything other than stop/tool_calls (e.g. "length", "content_filter") —
                    # log it so we can diagnose. Loop continues to next round; if there's an
                    # actual problem the safety limit will catch it.
                    print(f"[engine] unexpected finish_reason={finish_reason!r} on round {round_num}")
                    log.log_error(f"Unexpected finish_reason={finish_reason!r} on round {round_num}")

                # If we have all images and choices, we're done
                if images_generated >= IMAGES_PER_SEQUENCE and choices_provided:
                    break

            # Wait for all remaining image tasks
            for idx in sorted(image_tasks.keys()):
                if idx not in completed_images:
                    await self._emit_image_result(
                        idx, image_tasks[idx], completed_images, queue,
                        narration_segments=narration_segments_acc, session=session,
                        _log=log, davinci_fire_tasks=davinci_fire_tasks,
                        tts_tasks=tts_tasks_by_idx,
                    )

            # Wait for P-Video if it was started (skip if Davinci handles videos)
            video_result = None
            video_cost = 0.0
            if video_task is not None and not DAVINCI_ENABLED:
                try:
                    video_result = await asyncio.wait_for(video_task, timeout=120)
                    video_cost = video_result.get("cost", 0) or 0
                    log.log_video_result(video_cost, video_result.get("elapsed", 0))
                    await queue.put({
                        "type": "video_ready",
                        "url": video_result["url"],
                        "cost": video_cost,
                        "generation_time": video_result["elapsed"],
                    })
                except asyncio.TimeoutError:
                    await queue.put({"type": "video_error", "error": "Video generation timed out (120s)"})
                except Exception as e:
                    await queue.put({"type": "video_error", "error": str(e)})

            # Wait briefly for in-flight TTS tasks so their costs land in this
            # sequence's totals (typical TTS finishes in 2-5s; cap at 15s so a
            # stuck task can't hold up the choice screen).
            if StoryEngine._tts_pending > 0 and StoryEngine._tts_done_event:
                try:
                    await asyncio.wait_for(StoryEngine._tts_done_event.wait(), timeout=15)
                except asyncio.TimeoutError:
                    print(f"[tts] cost-calc wait timed out; partial TTS cost this sequence")

            # Compute costs (after video so we include video_cost)
            elapsed = round(time.time() - sequence_start, 1)
            # Cached input tokens are billed at a fraction of the regular input price.
            # Default discount: 75% off (matches Grok 4.1 Fast: $0.20→$0.05/M).
            # Pricing entries can override via a "cached" field if the model has a
            # different cache rate (e.g. Grok 4.20 is 90% off).
            cached_price = pricing.get("cached", pricing["input"] * 0.25)
            non_cached_input = max(0, grok_input_tokens - grok_cached_tokens)
            grok_cost = (
                non_cached_input * pricing["input"]
                + grok_cached_tokens * cached_price
                + grok_output_tokens * pricing["output"]
            ) / 1_000_000
            image_total_cost = sum(
                img.get("cost", 0) for img in completed_images.values()
            )
            # Per-scene videos (P-Video) fire concurrently; sum whatever has
            # completed by now into video_cost. Late-arriving scene_video_ready
            # events also carry per-scene cost, so the frontend can top-up the
            # per-sequence number as remaining videos finish.
            video_cost = (video_cost or 0) + self._scene_video_cost_total
            # TTS cost: audio bytes (xAI/Runware) + the Grok enhance call.
            # Enhance uses the same Grok model & pricing as the main story (it's
            # the same client), so apply the same input/cached/output rates.
            tts_audio_cost = round(self._tts_audio_cost_total, 6)
            enhance_non_cached = max(0, self._tts_enhance_input_tokens - self._tts_enhance_cached_tokens)
            tts_enhance_cost = (
                enhance_non_cached * pricing["input"]
                + self._tts_enhance_cached_tokens * cached_price
                + self._tts_enhance_output_tokens * pricing["output"]
            ) / 1_000_000
            tts_total_cost = round(tts_audio_cost + tts_enhance_cost, 6)
            total_cost = grok_cost + image_total_cost + video_cost + tts_total_cost

            # Update session costs
            session.total_costs["grok_input_tokens"] += grok_input_tokens
            session.total_costs["grok_output_tokens"] += grok_output_tokens
            session.total_costs["grok_cost"] += grok_cost
            session.total_costs["image_cost"] += image_total_cost
            session.total_costs["video_cost"] += video_cost
            session.total_costs.setdefault("tts_cost", 0.0)
            session.total_costs["tts_cost"] += tts_total_cost
            session.total_costs["total"] += total_cost

            # Save only narrative messages for next sequence context
            # (skip system prompt, tool calls, and tool responses — they're noise)
            session.conversation_history = [
                msg for msg in messages
                if msg.get("role") == "assistant" and msg.get("content")
            ]
            session.sequence_number += 1

            # Store narrative facts in Mem0 (fire-and-forget, non-blocking)
            if MEM0_ENABLED:
                try:
                    all_narration = ""
                    cast_codes_post = [c for c in (session.cast.get("actors") or []) if c]
                    code_to_name_post = {code: "" for code in cast_codes_post}
                    for display_name, code in (session.consistency.character_actors or {}).items():
                        if code:
                            code_to_name_post[code] = display_name
                    for msg in messages:
                        if msg.get("role") == "assistant" and msg.get("content"):
                            cleaned = _clean_narration(msg["content"], code_to_name_post)
                            if cleaned:
                                all_narration += cleaned + "\n"

                    # Mem0 client is sync — run in executor to avoid blocking
                    _sid = session.id
                    _uid = session.user_id
                    _seq = session.sequence_number - 1
                    _choice = choice_text
                    _setting = session.setting
                    _chars = session.cast.get("actors", [])

                    log.log_mem0_store(len(all_narration), _choice)

                    _setting_id = session.setting
                    def _store():
                        # Session-scoped + per-character memory (cross-session via user+setting)
                        store_sequence_narrative(
                            session_id=_sid, user_id=_uid,
                            sequence_number=_seq, narration_text=all_narration,
                            choice_made=_choice, setting_label=_setting,
                            characters=_chars,
                            setting_id=_setting_id,
                        )

                    asyncio.get_event_loop().run_in_executor(None, _store)
                except Exception:
                    pass  # Never block the game

            # Bump encounters count for actors that appeared in this sequence
            sequence_actors = set()
            for actor_code in session.relationships.keys():
                pass
            for tc_args in [args for args in [None] if args]:  # placeholder
                pass
            # Actors are tracked via relationships dict — bump encounter
            for actor_code in list(session.relationships.keys()):
                if session.relationships[actor_code].get("scenes", 0) > 0:
                    session.relationships[actor_code]["encounters"] += 1

            await queue.put({
                "type": "sequence_complete",
                "sequence_number": session.sequence_number,
                "grok_model": model,
                "relationships": session.relationships,
                "costs": {
                    "grok_input_tokens": grok_input_tokens,
                    "grok_output_tokens": grok_output_tokens,
                    "grok_cached_tokens": grok_cached_tokens,
                    "grok_cost": round(grok_cost, 6),
                    "image_costs": [
                        completed_images.get(i, {}).get("cost", 0)
                        for i in range(IMAGES_PER_SEQUENCE)
                    ],
                    "video_cost": round(video_cost, 4),
                    "tts_cost": tts_total_cost,
                    "tts_audio_cost": tts_audio_cost,
                    "tts_enhance_cost": round(tts_enhance_cost, 6),
                    "total_sequence_cost": round(total_cost, 4),
                    "total_session_cost": round(session.total_costs["total"], 4),
                    "elapsed_seconds": elapsed,
                },
            })

            # Extract narration segments from assistant messages (one per scene)
            narration_segments = []
            cast_codes_extract = [c for c in (session.cast.get("actors") or []) if c]
            code_to_name_extract = {code: "" for code in cast_codes_extract}
            for display_name, code in (session.consistency.character_actors or {}).items():
                if code:
                    code_to_name_extract[code] = display_name
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("content"):
                    cleaned = _clean_narration(msg["content"], code_to_name_extract)
                    if cleaned:
                        narration_segments.append(cleaned)
            # Pad to exactly 5 segments
            narration_segments = narration_segments[:IMAGES_PER_SEQUENCE]
            while len(narration_segments) < IMAGES_PER_SEQUENCE:
                narration_segments.append("")

            # ── Phase 2B: extract player-visible whereabouts from this sequence's
            #    narration. Cheap Grok call (~250+80 tok). Only fires in slice mode
            #    with character_states populated. Append (deduped) to session.known_whereabouts.
            if session.world is not None and session.character_states:
                try:
                    from agent import extract_whereabouts
                    full_narr = "\n\n".join(seg for seg in narration_segments if seg)
                    new_mentions = await extract_whereabouts(
                        self.grok, full_narr,
                        list(session.character_states.keys()),
                        session.world.day, session.world.slot,
                        session.world.locations,
                        grok_model=model,
                    )
                    # Dedupe: same (char, day, slot, location_id) already present?
                    seen = {(m["char"], m["day"], m["slot"], m["location_id"]) for m in session.known_whereabouts}
                    existing_loc_ids = {l.id for l in session.world.locations}
                    added = 0
                    new_locs_added = 0
                    for m in new_mentions:
                        # Phase C: if the extractor proposed a NEW location, register
                        # it on the world before storing the whereabouts (so the
                        # location is visible on the map and the whereabouts is valid).
                        new_loc = m.pop("new_location", None) if isinstance(m, dict) else None
                        if new_loc and new_loc.get("id") not in existing_loc_ids:
                            from world import Location as _Loc
                            session.world.locations.append(_Loc(
                                id=new_loc["id"],
                                name=new_loc.get("name") or new_loc["id"],
                                type=new_loc.get("type") or "other",
                                description=new_loc.get("description") or "",
                            ))
                            existing_loc_ids.add(new_loc["id"])
                            new_locs_added += 1
                            print(f"[world] +location {new_loc['id']} ({new_loc.get('name')!r}) "
                                  f"from narration: « {(m.get('source') or '')[:60]} »")
                        key = (m["char"], m["day"], m["slot"], m["location_id"])
                        if key not in seen:
                            session.known_whereabouts.append(m)
                            seen.add(key)
                            added += 1
                    if added:
                        print(f"[agent] +{added} known whereabouts (total {len(session.known_whereabouts)})"
                              + (f" + {new_locs_added} new locations" if new_locs_added else ""))
                except Exception as e:
                    print(f"[agent] whereabouts extract failed: {e}")

            # Log narration + costs
            log.log_narration(narration_segments)
            log.log_costs(grok_cost, image_total_cost, video_cost, total_cost,
                          grok_input_tokens, grok_output_tokens, elapsed,
                          cached_tokens=grok_cached_tokens,
                          tts_cost=tts_total_cost,
                          tts_audio_cost=tts_audio_cost,
                          tts_enhance_cost=round(tts_enhance_cost, 6))

            # Persist to database (after video is done)
            import db as _db
            if _db.DB_ENABLED:
                # Save choice_made on the PREVIOUS sequence (if this isn't the first)
                if choice_text and session.sequence_number > 0:
                    _db.fire_and_forget(_db.update_sequence_choice(
                        session.id,
                        session.sequence_number - 1,
                        {"id": choice_id or "?", "text": choice_text},
                    ))

                images_persist = []
                for i in range(IMAGES_PER_SEQUENCE):
                    ci = completed_images.get(i, {})
                    prompt_i = session.consistency.previous_prompts[i] if i < len(session.consistency.previous_prompts) else ""
                    images_persist.append({
                        "index": i,
                        "url": ci.get("url"),
                        "prompt": prompt_i,
                        "actors": scene_actors.get(i, []),
                        "cost": ci.get("cost", 0),
                        "seed": ci.get("seed"),
                        "generation_time": ci.get("elapsed"),
                        "settings": ci.get("settings"),
                    })
                video_persist = None
                if video_result:
                    video_persist = {
                        "url": video_result["url"],
                        "cost": video_result["cost"],
                        "generation_time": video_result["elapsed"],
                        "prompt": getattr(session, '_last_video_prompt', ''),
                    }
                seq_costs = {
                    "grok_model": model,
                    "grok_input_tokens": grok_input_tokens,
                    "grok_output_tokens": grok_output_tokens,
                    "grok_cost": round(grok_cost, 6),
                    "image_costs": [completed_images.get(i, {}).get("cost", 0) for i in range(IMAGES_PER_SEQUENCE)],
                    "video_cost": round(video_cost, 4),
                    "total_sequence_cost": round(total_cost, 4),
                }
                _db.fire_and_forget(_db.save_session(session))
                _db.fire_and_forget(_db.save_sequence(
                    session.id, session.sequence_number,
                    narration_segments, choices if choices_provided else [],
                    None, seq_costs, images_persist, video_persist,
                ))

        except Exception as e:
            import traceback
            log.log_error(str(e))
            traceback.print_exc()
            await queue.put({"type": "error", "message": str(e)})

        finally:
            # Wait for all Davinci prompt generation tasks (Grok calls) to finish first
            if DAVINCI_ENABLED and davinci_fire_tasks:
                pending_fires = [t for t in davinci_fire_tasks if not t.done()]
                if pending_fires:
                    print(f"[davinci] Waiting for {len(pending_fires)} prompt generation tasks...")
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*pending_fires, return_exceptions=True),
                            timeout=30,  # Grok calls shouldn't take more than 30s
                        )
                    except asyncio.TimeoutError:
                        print(f"[davinci] Timeout waiting for prompt generation")

            # Now wait for all queued videos to complete before closing SSE
            if DAVINCI_ENABLED and StoryEngine._davinci_pending > 0:
                print(f"[davinci] Waiting for {StoryEngine._davinci_pending} remaining videos...")
                try:
                    await asyncio.wait_for(StoryEngine._davinci_done_event.wait(), timeout=DAVINCI_TIMEOUT * 5)
                except asyncio.TimeoutError:
                    print(f"[davinci] Timeout waiting for videos — closing SSE anyway")
                print(f"[davinci] All videos done.")

            if StoryEngine._pvideo_pending > 0:
                print(f"[pvideo] Waiting for {StoryEngine._pvideo_pending} remaining videos...")
                try:
                    if StoryEngine._pvideo_done_event:
                        await asyncio.wait_for(StoryEngine._pvideo_done_event.wait(), timeout=600)
                except asyncio.TimeoutError:
                    print(f"[pvideo] Timeout waiting for videos — closing SSE anyway")
                print(f"[pvideo] All videos done.")

            if StoryEngine._tts_pending > 0:
                print(f"[tts] Waiting for {StoryEngine._tts_pending} remaining audio clips...")
                try:
                    if StoryEngine._tts_done_event:
                        await asyncio.wait_for(StoryEngine._tts_done_event.wait(), timeout=120)
                except asyncio.TimeoutError:
                    print(f"[tts] Timeout waiting for audio — closing SSE anyway")
                print(f"[tts] All audio done.")

            log.finish()
            await queue.put(None)  # Signal done

    async def _generate_image(
        self, args: dict, cast: dict,
        style_loras: list[dict] | None = None,
        extra_loras: list[dict] | None = None,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        _log: SequenceLogger | None = None,
    ) -> dict:
        """Generate a scene image with appropriate LoRAs (max 3, priority: characters > mood > style > extra)."""
        prompt = args.get("image_prompt", "")
        actors = args.get("actors_present", [])

        # Parse style moods — support both old (string) and new (array) formats
        raw_moods = args.get("style_moods", args.get("style_mood", ["neutral"]))
        if isinstance(raw_moods, str):
            active_moods = [raw_moods] if raw_moods != "neutral" else []
        elif isinstance(raw_moods, list):
            active_moods = [m for m in raw_moods if m != "neutral"]
        else:
            active_moods = []
        # Backward compat
        if args.get("use_nsfw_style") and not active_moods:
            active_moods = ["explicit_mystic"]

        # 0. Secondary characters — track for consistency only.
        # Do NOT auto-prepend descriptions: if a secondary character should be
        # visible, Grok must include their description in the prompt text itself.
        # Auto-prepending caused main character LoRAs to render the secondary
        # character's features (e.g. male face on female LoRA).

        # Safety net: auto-add cast members that Grok forgot in actors_present.
        # Reasoning models sometimes omit actors_present but still describe the
        # character in the prompt or clothing_state. Three signals checked:
        actors_set = set(actors)
        prompt_lower = prompt.lower()
        clothing_keys = set(args.get("clothing_state", {}).keys())

        for cast_code in cast.get("actors", []):
            if not cast_code or cast_code in actors_set:
                continue
            actor_data = ACTOR_REGISTRY.get(cast_code)
            if not actor_data:
                continue

            should_add = False
            tw = actor_data.get("trigger_word", "")
            prefix = actor_data.get("prompt_prefix", "")

            # Signal 1: trigger word appears in the prompt text
            if tw and tw in prompt:
                should_add = True
            # Signal 2: prompt prefix (non-LoRA chars like Ciri) appears in prompt
            elif prefix and prefix.lower()[:30] in prompt_lower:
                should_add = True
            # Signal 3: character codename appears in clothing_state
            #   (model remembered clothing but forgot actors_present)
            elif cast_code in clothing_keys:
                should_add = True

            if should_add:
                actors.append(cast_code)
                actors_set.add(cast_code)

        # Priority layers (highest first)
        character_loras = []
        mood_loras = []
        other_loras = []

        # 1. Character LoRAs or prompt prefixes (highest priority)
        # For multi-character scenes: only PREPEND the first character's trigger word
        # at the start of the prompt. Additional characters' trigger words should appear
        # naturally in the prompt body where they're described — prepending all trigger
        # words at the start causes Z-Image to blend the LoRA influences and both
        # characters end up looking alike.

        # Allow active moods to override the actor's default LoRA weight
        # (e.g. anal_missionary_shemale reduces character LoRA to 0.6 so the
        # specialised pose LoRA can dominate). First mood with the override wins.
        moods_config_for_char = getattr(self, '_session_moods', None) or DEFAULT_STYLE_MOODS
        char_lora_weight_override: float | None = None
        for _mood_name in active_moods:
            _md = moods_config_for_char.get(_mood_name)
            if _md and _md.get("char_lora_weight") is not None:
                char_lora_weight_override = float(_md["char_lora_weight"])
                break

        is_first_actor = True
        for actor_code in actors:
            actor = ACTOR_REGISTRY.get(actor_code)
            if not actor:
                continue
            # Apply per-session custom actor override
            if actor_code == "custom" and hasattr(self, '_custom_override'):
                actor = {**actor, **self._custom_override}
            # LoRA-based characters
            if actor.get("lora_id"):
                tw = actor.get("trigger_word")
                # Only add LoRA if the character's trigger word is in the prompt
                # (or will be prepended for the first actor). This prevents
                # e.g. Nataly's LoRA from overriding Yennefer's appearance
                # when both are in actors_present but only Yennefer is described.
                tw_present = tw and tw in prompt
                if tw_present or is_first_actor:
                    character_loras.append(ILora(
                        model=actor["lora_id"],
                        weight=char_lora_weight_override if char_lora_weight_override is not None else actor["default_weight"],
                    ))
                    if tw and tw not in prompt and is_first_actor:
                        prompt = f"{tw}, {prompt}"
            # Prompt-prefix characters (no LoRA, e.g. Ciri, Yennefer)
            elif actor.get("prompt_prefix"):
                prefix = actor["prompt_prefix"]
                if prefix not in prompt:
                    if is_first_actor:
                        prompt = f"{prefix}, {prompt}"
            is_first_actor = False

        # 2. Style mood LoRAs + cfg/steps overrides (multiple possible, chosen by LLM per scene)
        moods_config = getattr(self, '_session_moods', None) or DEFAULT_STYLE_MOODS
        mood_cfg_override = None
        mood_steps_override = None
        for mood_name in active_moods:
            mood_data = moods_config.get(mood_name)
            if not mood_data:
                continue
            lora = mood_data.get("lora")
            if lora and lora.get("id"):
                mood_loras.append(ILora(
                    model=lora["id"],
                    weight=lora.get("weight", 0.6),
                ))
            # Inject the mood prompt_block into the final prompt.
            # PREPEND the full mood block (not just the trigger) right after the
            # actor trigger word — Z-Image weighs the start of the prompt more
            # heavily. This ensures framing/composition directives are honored.
            pb = mood_data.get("prompt_block", "")
            if pb:
                # Avoid duplicating if Grok already echoed the mood block
                pb_key = pb[:40].lower()
                if pb_key not in prompt.lower():
                    # Try to insert AFTER the actor trigger word so the trigger stays first
                    # (the actor trigger may be a single word or a longer prompt_prefix)
                    inserted = False
                    for actor_code in actors:
                        actor_data_full = ACTOR_REGISTRY.get(actor_code, {})
                        actor_tw = actor_data_full.get("trigger_word", "")
                        if actor_tw and prompt.startswith(actor_tw):
                            rest = prompt[len(actor_tw):].lstrip(", ")
                            prompt = f"{actor_tw}, {pb}, {rest}"
                            inserted = True
                            break
                    if not inserted:
                        prompt = f"{pb}, {prompt}"
            # Pick up cfg/steps overrides (last mood wins)
            if mood_data.get("cfg") is not None:
                mood_cfg_override = mood_data["cfg"]
            if mood_data.get("steps") is not None:
                mood_steps_override = mood_data["steps"]

        # 3. Trans actor handling — when an actor in the scene is flagged as `trans`
        # and the active mood is EXPLICIT (not casual/teasing), we:
        #   - Add the ZTurbo Pen V3 LoRA (anatomical detail) — except for doggystyle
        #     where stacking it with dgz produces artifacts
        #   - Inject "trans woman, erect penis visible" into the prompt so the agent's
        #     existing position description applies to a trans body
        _intimate_moods = {
            "explicit_mystic", "blowjob", "blowjob_closeup",
            "cunnilingus", "cunnilingus_from_behind",
            "missionary", "cowgirl", "reverse_cowgirl",
            "spooning", "standing_sex",
            "anal_doggystyle", "anal_missionary", "anal_missionary_shemale",
            "cumshot_face", "titjob", "handjob",
            # Note: "doggystyle" is intentionally excluded — ZTurbo Pen V3 + dgz LoRA
            # produces bad results. The agent should describe the trans anatomy via the
            # injected prompt fragment instead.
        }
        actor_genders = (cast or {}).get("actor_genders", {}) or {}
        trans_actor_present = any(
            actor_genders.get(code) == "trans" for code in actors
        )
        # If any active mood opts out of the auto trans LoRA stack (e.g. it provides its
        # own specialised LoRA like Mishra), skip ZTurbo Pen V3 but keep the prompt
        # fragment so the agent's anatomy description still applies.
        skip_trans_lora_mood = any(
            (moods_config.get(m) or {}).get("skip_trans_lora") for m in active_moods
        )
        if trans_actor_present and any(m in _intimate_moods for m in active_moods):
            if not skip_trans_lora_mood:
                # Add the anatomical detail LoRA (ZTurbo Pen V3)
                mood_loras.append(ILora(model="warmline:202603170004@1", weight=1.0))
            # Inject trans description into the prompt (after trigger word, before scene details)
            trans_fragment = "trans woman with erect penis visible, anatomical detail, futa anatomy"
            if trans_fragment[:30].lower() not in prompt.lower():
                prompt = f"{prompt}, {trans_fragment}"
        elif trans_actor_present and any(m == "doggystyle" for m in active_moods):
            # Doggystyle case: skip the ZTurbo LoRA, just inject the prompt fragment
            trans_fragment = "trans woman with erect penis visible, anatomical detail, futa anatomy"
            if trans_fragment[:30].lower() not in prompt.lower():
                prompt = f"{prompt}, {trans_fragment}"

        # 4. Session style LoRAs (editable via debug)
        if style_loras:
            for sl in style_loras:
                other_loras.append(ILora(model=sl["id"], weight=sl.get("weight", 1.0)))

        # 5. Extra LoRAs (debug)
        if extra_loras:
            for el in extra_loras:
                other_loras.append(ILora(model=el["id"], weight=el.get("weight", 1.0)))

        # Blow (bjz) / Dog (dgz) + Mystic together causes bad artifacts; drop Mystic when either is present.
        # ZIT NSFW LoRA v2 (cunnilingus, cunnilingus_from_behind, sensual_tease) + Mystic stacks poorly; drop Mystic when ZIT v2 is present.
        # PhotoShemPen and character LoRAs may stay combined with Mystic (unless ZIT v2 also present).
        _combined_style = mood_loras + other_loras
        if any(l.model in SPECIALIST_STYLE_LORA_IDS for l in _combined_style):
            mood_loras = [l for l in mood_loras if l.model != MYSTIC_XXX_ZIT_V5_LORA_ID]
            other_loras = [l for l in other_loras if l.model != MYSTIC_XXX_ZIT_V5_LORA_ID]
        if any(l.model == ZIT_NSFW_LORA_V2_ID for l in _combined_style):
            mood_loras = [l for l in mood_loras if l.model != MYSTIC_XXX_ZIT_V5_LORA_ID]
            other_loras = [l for l in other_loras if l.model != MYSTIC_XXX_ZIT_V5_LORA_ID]

        # Merge with dedup (last wins)
        all_loras = character_loras + mood_loras + other_loras
        seen: dict[str, ILora] = {}
        for lora in all_loras:
            seen[lora.model] = lora
        deduped = list(seen.values())

        # Enforce max LoRAs: prioritize characters, then mood, then others
        if len(deduped) > MAX_LORAS_PER_IMAGE:
            char_ids = {l.model for l in character_loras}
            mood_ids = {l.model for l in mood_loras}
            # Sort: characters first, then nsfw, then others
            deduped.sort(key=lambda l: (
                0 if l.model in char_ids else 1 if l.model in mood_ids else 2
            ))
            deduped = deduped[:MAX_LORAS_PER_IMAGE]

        lora_list = deduped

        seed = args.get("seed")

        final_width = width or IMAGE_WIDTH
        final_height = height or IMAGE_HEIGHT
        # Priority: explicit override > mood override > global default
        final_steps = steps or mood_steps_override or IMAGE_STEPS
        final_cfg = mood_cfg_override if mood_cfg_override is not None else IMAGE_CFG

        start = time.time()
        request = IImageInference(
            model=IMAGE_MODEL,
            positivePrompt=prompt,
            width=final_width,
            height=final_height,
            steps=final_steps,
            CFGScale=final_cfg,
            seed=seed if seed else None,
            outputFormat=IMAGE_FORMAT,
            includeCost=True,
            lora=lora_list,
            numberResults=1,
            safety=ISafety(checkContent=False),
        )

        images = await self.runware.imageInference(requestImage=request)
        elapsed = round(time.time() - start, 2)

        img = images[0]
        cost = getattr(img, "cost", 0) or 0
        result_seed = getattr(img, "seed", None)
        lora_info = [{"id": l.model, "weight": l.weight} for l in lora_list]

        # Log image result with all final details
        if _log:
            _log.log_image_result(
                args.get("image_index", -1), lora_info, prompt,
                final_width, final_height, final_steps, final_cfg,
                result_seed, cost, elapsed,
            )

        return {
            "url": img.imageURL,
            "cost": cost,
            "seed": result_seed,
            "elapsed": elapsed,
            "settings": {
                "width": final_width,
                "height": final_height,
                "steps": final_steps,
                "cfg": final_cfg,
                "seed_used": seed if seed else None,
                "loras": lora_info,
                "style_moods": active_moods or ["neutral"],
                "prompt_length": len(prompt),
                "final_prompt": prompt,
            },
        }

    async def _generate_video(self, prompt: str, input_image_url: str, video_settings: dict | None = None, audio_url: str | None = None) -> dict:
        """Generate a video clip from an image using P-Video (or simulate).
        If audio_url is provided, it's passed as inputs.audio so the output uses that
        soundtrack (and duration is derived from the audio)."""
        vs = video_settings or {}

        # Simulation mode: wait ~60s, return the input image as "video"
        if vs.get("simulate", False):
            await asyncio.sleep(60)
            return {
                "url": input_image_url,  # use the source image as placeholder
                "cost": 0,
                "elapsed": 60.0,
                "simulated": True,
            }

        from runware import IInputFrame

        start = time.time()
        # Only set promptUpsampling if explicitly configured (otherwise let Runware default apply)
        settings_kwargs = {
            "draft": vs.get("draft", VIDEO_DRAFT),
            "audio": vs.get("audio", VIDEO_AUDIO),
        }
        if audio_url:
            # Audio carries the scene direction — disable prompt upsampling so Pruna doesn't
            # re-inflate our minimal prompt and contradict the audio.
            settings_kwargs["promptUpsampling"] = False
        elif "pvideo_prompt_upsampling" in vs and vs["pvideo_prompt_upsampling"] is not None:
            settings_kwargs["promptUpsampling"] = vs["pvideo_prompt_upsampling"]

        inputs_kwargs: dict = {"frameImages": [IInputFrame(image=input_image_url, frame="first")]}
        # When audio drives the scene we keep the prompt minimal — verbose narration
        # competes with the audio for the character's behaviour and tends to hurt lip-sync.
        effective_prompt = "a person speaking to the camera" if audio_url else prompt
        video_kwargs: dict = {
            "model": VIDEO_MODEL,
            "positivePrompt": effective_prompt,
            "resolution": vs.get("resolution", VIDEO_RESOLUTION),
            "outputFormat": "MP4",
            "includeCost": True,
            "settings": ISettings(**settings_kwargs),
        }
        if audio_url:
            inputs_kwargs["audio"] = audio_url
            # Audio mode: duration derived from audio length, must NOT pass duration
        else:
            video_kwargs["duration"] = vs.get("duration", VIDEO_DURATION)
        video_kwargs["inputs"] = IVideoInputs(**inputs_kwargs)

        request = IVideoInference(**video_kwargs)

        result = await self.runware.videoInference(requestVideo=request)
        if isinstance(result, IAsyncTaskResponse):
            videos = await self.runware.getResponse(taskUUID=result.taskUUID)
        else:
            videos = result

        elapsed = round(time.time() - start, 1)
        video_url = videos[0].videoURL
        cost = sum(getattr(v, "cost", 0) or 0 for v in videos)

        return {"url": video_url, "cost": cost, "elapsed": elapsed}

    async def _watch_video(self, task: asyncio.Task, queue: asyncio.Queue):
        """Monitor video task completion and push event."""
        try:
            result = await task
            await queue.put({
                "type": "video_ready",
                "url": result["url"],
                "cost": result["cost"],
                "generation_time": result["elapsed"],
            })
        except Exception as e:
            await queue.put({
                "type": "video_error",
                "error": str(e),
            })

    # Class-level queue for serializing Davinci requests (one at a time)
    _davinci_queue: asyncio.Queue | None = None
    _davinci_worker_running: bool = False
    _davinci_pending: int = 0  # number of jobs enqueued but not yet completed
    _davinci_done_event: asyncio.Event | None = None

    async def _ensure_davinci_worker(self):
        """Start the Davinci worker if not already running."""
        if not StoryEngine._davinci_queue:
            StoryEngine._davinci_queue = asyncio.Queue()
        if not StoryEngine._davinci_done_event:
            StoryEngine._davinci_done_event = asyncio.Event()
        if not StoryEngine._davinci_worker_running:
            StoryEngine._davinci_worker_running = True
            asyncio.create_task(self._davinci_worker())

    async def _davinci_worker(self):
        """Process Davinci jobs one at a time (API only handles one concurrent job)."""
        try:
            while True:
                job = await asyncio.wait_for(StoryEngine._davinci_queue.get(), timeout=120)
                if job is None:
                    break
                scene_index, image_url, prompt, seed, seq_num, sse_queue, video_hd, video_short, session_id = job
                try:
                    from davinci import DAVINCI_HD_WIDTH, DAVINCI_HD_HEIGHT, DAVINCI_HD_SECONDS
                    if video_hd:
                        extra_kwargs = {"width": DAVINCI_HD_WIDTH, "height": DAVINCI_HD_HEIGHT, "seconds": DAVINCI_HD_SECONDS}
                        mode_label = "HD 540p/5s"
                    elif video_short:
                        extra_kwargs = {"seconds": DAVINCI_HD_SECONDS}  # 5s at default 256p
                        mode_label = "256p/5s"
                    else:
                        extra_kwargs = {}
                        mode_label = "256p/10s"
                    print(f"[davinci] Scene {scene_index} (seq {seq_num}): starting video gen {mode_label}...")
                    print(f"[davinci] Prompt: {prompt[:150]}...")
                    result = await davinci_generate(
                        image_url=image_url,
                        davinci_prompt=prompt,
                        seed=seed,
                        **extra_kwargs,
                    )
                    simulated = result.get("simulated", False)
                    if simulated:
                        # Simulation mode — use original image URL as "video"
                        video_data_url = image_url
                    else:
                        import base64
                        video_b64 = base64.b64encode(result["video_bytes"]).decode()
                        video_data_url = f"data:video/mp4;base64,{video_b64}"

                    print(f"[davinci] Scene {scene_index} (seq {seq_num}): {'SIMULATED' if simulated else 'done'} in {result['duration']}s")
                    await sse_queue.put({
                        "type": "scene_video_ready",
                        "index": scene_index,
                        "sequence_number": seq_num,
                        "url": video_data_url,
                        "generation_time": result["generation_time"],
                        "job_id": result["job_id"],
                        "simulated": simulated,
                    })
                    # Persist video URL to DB (the pod URL, not base64)
                    if not simulated and session_id and result.get("video_url"):
                        import db as _db
                        _db.fire_and_forget(_db.save_scene_video(
                            session_id, seq_num, scene_index, result["video_url"]
                        ))
                except Exception as e:
                    print(f"[davinci] Scene {scene_index}: error — {e}")
                    await sse_queue.put({
                        "type": "scene_video_error",
                        "index": scene_index,
                        "error": str(e),
                    })
                finally:
                    StoryEngine._davinci_pending -= 1
                    if StoryEngine._davinci_pending <= 0:
                        StoryEngine._davinci_pending = 0
                        if StoryEngine._davinci_done_event:
                            StoryEngine._davinci_done_event.set()
        except asyncio.TimeoutError:
            pass  # No more jobs for 2 min — worker exits
        finally:
            StoryEngine._davinci_worker_running = False
            if StoryEngine._davinci_done_event:
                StoryEngine._davinci_done_event.set()

    async def _enqueue_davinci(
        self, scene_index: int, image_url: str, prompt: str,
        seed: int | None, sse_queue: asyncio.Queue,
        sequence_number: int = 0,
        video_hd: bool = False, video_short: bool = False,
        session_id: str = "",
    ):
        """Enqueue a Davinci job for sequential processing."""
        await self._ensure_davinci_worker()
        StoryEngine._davinci_pending += 1
        if StoryEngine._davinci_done_event:
            StoryEngine._davinci_done_event.clear()
        await StoryEngine._davinci_queue.put((scene_index, image_url, prompt, seed, sequence_number, sse_queue, video_hd, video_short, session_id))

    # ─── P-Video (Runware) per-scene — concurrent (serverless, no queue needed) ─
    _pvideo_tasks: list[asyncio.Task] = []
    _pvideo_pending: int = 0
    _pvideo_done_event: asyncio.Event | None = None

    async def _fire_pvideo_task(
        self, scene_index: int, image_url: str, prompt: str,
        sse_queue: asyncio.Queue, sequence_number: int = 0,
        draft: bool = True, session_id: str = "",
        prompt_upsampling: bool | None = None,
        audio_url: str | None = None,
    ):
        """Fire a P-Video generation concurrently (Runware is serverless — no need to serialize).
        If audio_url is provided, the output video uses that audio as soundtrack."""
        try:
            audio_tag = f", audio={'on' if audio_url else 'off'}"
            print(f"[pvideo] Scene {scene_index} (seq {sequence_number}): starting {'draft' if draft else 'full'}, upsampling={prompt_upsampling}{audio_tag}...")
            print(f"[pvideo] Prompt: {prompt[:150]}...")
            result = await self._generate_video(prompt, image_url, {
                "draft": draft,
                "audio": True,
                "duration": 5,
                "resolution": "720p",
                "pvideo_prompt_upsampling": prompt_upsampling,
            }, audio_url=audio_url)
            video_url = result.get("url", "")
            video_cost = result.get("cost", 0) or 0
            self._scene_video_cost_total += video_cost
            print(f"[pvideo] Scene {scene_index} (seq {sequence_number}): done in {result['elapsed']}s (${video_cost:.3f})")
            await sse_queue.put({
                "type": "scene_video_ready",
                "index": scene_index,
                "sequence_number": sequence_number,
                "url": video_url,
                "generation_time": result["elapsed"],
                "job_id": f"pvideo-{scene_index}",
                "simulated": False,
                "cost": video_cost,
            })
            # Persist video URL + cost to DB
            if session_id:
                import db as _db
                if video_url:
                    _db.fire_and_forget(_db.save_scene_video(
                        session_id, sequence_number, scene_index, video_url
                    ))
                if video_cost > 0:
                    _db.fire_and_forget(_db.add_scene_video_cost(session_id, video_cost))
        except Exception as e:
            print(f"[pvideo] Scene {scene_index}: error — {e}")
            await sse_queue.put({
                "type": "scene_video_error",
                "index": scene_index,
                "error": str(e),
            })
        finally:
            StoryEngine._pvideo_pending -= 1
            if StoryEngine._pvideo_pending <= 0:
                StoryEngine._pvideo_pending = 0
                if StoryEngine._pvideo_done_event:
                    StoryEngine._pvideo_done_event.set()

    def _launch_pvideo(
        self, scene_index: int, image_url: str, prompt: str,
        sse_queue: asyncio.Queue, sequence_number: int = 0,
        draft: bool = True, session_id: str = "",
        prompt_upsampling: bool | None = None,
        audio_url: str | None = None,
    ):
        """Launch a P-Video task concurrently (no queue — all scenes in parallel).
        If audio_url is provided, that audio is used as the video's soundtrack."""
        if not StoryEngine._pvideo_done_event:
            StoryEngine._pvideo_done_event = asyncio.Event()
        StoryEngine._pvideo_pending += 1
        StoryEngine._pvideo_done_event.clear()
        task = asyncio.create_task(self._fire_pvideo_task(
            scene_index, image_url, prompt, sse_queue,
            sequence_number=sequence_number, draft=draft, session_id=session_id,
            prompt_upsampling=prompt_upsampling, audio_url=audio_url,
        ))
        StoryEngine._pvideo_tasks.append(task)

    # ─── Per-scene TTS (xAI via Runware) ─────────────────────────────────────
    _tts_pending: int = 0
    _tts_done_event: asyncio.Event | None = None
    _tts_tasks: list[asyncio.Task] = []

    async def _fire_tts_task(
        self, scene_index: int, narration_text: str,
        sse_queue: asyncio.Queue, sequence_number: int,
        voice: str, language: str, enhance: bool,
        session_id: str,
        dialogue_only: bool = False,
        for_video_only: bool = False,
        stereo: bool = True,
        log_ref: 'SequenceLogger | None' = None,
        narration_voice: str | None = None,
        actor_voices: dict[str, str] | None = None,
        actors_present: list[str] | None = None,
    ) -> str:
        """Generate TTS for a scene's narration, emit scene_audio_ready, return audio URL.
        - dialogue_only: extract only quoted dialogue from the narration before TTS
          (used when feeding the audio into video lip-sync — narration prose isn't spoken).
        - for_video_only: tell the UI not to play this clip standalone (it lives in the video).
        - When NOT dialogue_only AND a narration_voice is provided, the narration prose
          and the dialogue lines are voiced separately and stitched together so each part
          gets its own voice (Phase A multi-voice TTS).
        """
        from tts import (
            enhance_speech_text, generate_speech, extract_dialogue,
            generate_speech_direct_xai, select_speech_backend,
            parse_speech_segments, concat_audio_chunks, dedupe_boundary_pauses,
        )
        audio_url = ""
        try:
            text = (narration_text or "").strip()
            if not text:
                if log_ref:
                    log_ref.log_tts_error(scene_index, "narration_text empty — skipped")
                return ""
            if log_ref:
                log_ref.log_tts_request(
                    scene_index, voice, language, len(text),
                    dialogue_only, for_video_only, enhance, stereo,
                )
            if dialogue_only:
                dlg = extract_dialogue(text)
                if dlg:
                    text = dlg
                else:
                    # No quoted lines → fall back to full narration so the video still gets audio
                    print(f"[tts] Scene {scene_index}: dialogue_only requested but no quoted lines, using full narration")

            # Decide whether to go multi-voice. We split when:
            #   - not in dialogue_only mode (P-Video lip-sync needs ONE voice)
            #   - not piping into a video (for_video_only is False)
            #   - a distinct narration_voice was configured
            #   - the parsed text actually has BOTH narration prose and dialogue
            multi_voice_eligible = (
                not dialogue_only
                and not for_video_only
                and bool(narration_voice)
            )

            segments: list[tuple[str, str]] = []  # [(enhanced_text, voice_to_use), ...]
            enhance_elapsed = 0.0
            enhance_usage_total = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
            spoken = text  # Used for log + scene_audio_ready event

            # Pick the speaker voice once — used both for the multi-voice path
            # and for narration-only / dialogue-only single-voice routing below.
            av = actor_voices or {}
            speaker_voice = voice  # configured fallback dialogue voice
            if actors_present:
                for code in actors_present:
                    if code in av:
                        speaker_voice = av[code]
                        break

            single_mode = "dialogue"  # default mode for the single-voice fallback below

            if multi_voice_eligible:
                parsed = parse_speech_segments(text)
                has_dialogue = any(s["kind"] == "dialogue" for s in parsed)
                has_narration = any(s["kind"] == "narration" for s in parsed)
                # Pure-narration scene → single voice = narration_voice + narration mode.
                # Pure-dialogue scene → single voice = speaker_voice + dialogue mode.
                # Mixed → multi-voice path (segment-by-segment).
                if has_narration and not has_dialogue:
                    voice = narration_voice
                    single_mode = "narration"
                elif has_dialogue and not has_narration:
                    voice = speaker_voice
                    single_mode = "dialogue"
                has_both = has_narration and has_dialogue
                if has_both:

                    # Per-segment enhance with the right mode + voice. Run in
                    # parallel — adds ~1s vs single enhance, much better direction.
                    if enhance:
                        async def _enh(seg: dict) -> tuple[str, str, float, dict]:
                            seg_voice = narration_voice if seg["kind"] == "narration" else speaker_voice
                            seg_mode = "narration" if seg["kind"] == "narration" else "dialogue"
                            try:
                                enhanced, el, usage = await enhance_speech_text(
                                    self.grok, seg["text"],
                                    voice=seg_voice, language=language,
                                    mode=seg_mode, grok_model=GROK_MODEL,
                                )
                            except Exception as e:
                                print(f"[tts] Scene {scene_index}: enhance segment failed — {e}, raw text")
                                enhanced, el, usage = seg["text"], 0.0, {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
                            return enhanced, seg_voice, el, usage
                        gather = await asyncio.gather(*[_enh(s) for s in parsed])
                        segments_text = [g[0] for g in gather]
                        segments_voices = [g[1] for g in gather]
                        # Dedupe pauses at boundaries (avoids double-pause concat glitches)
                        segments_text = dedupe_boundary_pauses(segments_text)
                        segments = list(zip(segments_text, segments_voices))
                        enhance_elapsed = round(max((g[2] for g in gather), default=0.0), 2)
                        for g in gather:
                            for k in enhance_usage_total:
                                enhance_usage_total[k] += g[3].get(k, 0)
                        spoken = "\n".join(segments_text)
                    else:
                        # No enhance — segment plain text directly
                        for s in parsed:
                            v = narration_voice if s["kind"] == "narration" else speaker_voice
                            segments.append((s["text"], v))
                        spoken = text

                    # Roll up enhance usage into the engine's total
                    self._tts_enhance_input_tokens += enhance_usage_total["input_tokens"]
                    self._tts_enhance_output_tokens += enhance_usage_total["output_tokens"]
                    self._tts_enhance_cached_tokens += enhance_usage_total["cached_tokens"]

            # Single-voice fallback path — used when not eligible for split,
            # or when the text doesn't have both narration and dialogue. The
            # mode + voice for this path were set above (single_mode, voice).
            if not segments:
                if enhance:
                    try:
                        spoken, enhance_elapsed, enhance_usage = await enhance_speech_text(
                            self.grok, text, voice=voice, language=language,
                            mode=single_mode, grok_model=GROK_MODEL,
                        )
                        self._tts_enhance_input_tokens += enhance_usage.get("input_tokens", 0)
                        self._tts_enhance_output_tokens += enhance_usage.get("output_tokens", 0)
                        self._tts_enhance_cached_tokens += enhance_usage.get("cached_tokens", 0)
                    except Exception as e:
                        print(f"[tts] Scene {scene_index}: enhance failed — {e}, falling back to raw text")
                        spoken = text

            # ── Synthesis path ───────────────────────────────────────────────
            backend = select_speech_backend(prefer_url=for_video_only, stereo=stereo)
            mode_tag = "dialogue" if dialogue_only else ("narration+dialogue" if segments else "narration")

            if segments:
                # Multi-voice path. Generate each segment in parallel via xAI direct
                # (raw bytes), then naive-concat MP3. Skip Runware entirely — we
                # don't need a hosted URL because for_video_only is False here.
                from config import XAI_API_KEY
                print(f"[tts] Scene {scene_index} (seq {sequence_number}): multi-voice {len(segments)} segments "
                      f"({language}, enhance={enhance_elapsed}s)...")
                gather = await asyncio.gather(*[
                    generate_speech_direct_xai(XAI_API_KEY, seg_text, voice=seg_voice, language=language)
                    for seg_text, seg_voice in segments
                ], return_exceptions=False)
                # Decode each base64 data URI back to raw bytes for concat
                import base64 as _b64
                raw_chunks: list[bytes] = []
                total_cost = 0.0
                total_elapsed = 0.0
                for r in gather:
                    data_uri = r.get("audio_data") or ""
                    if "," in data_uri:
                        raw_chunks.append(_b64.b64decode(data_uri.split(",", 1)[1]))
                    total_cost += float(r.get("cost", 0) or 0)
                    total_elapsed = max(total_elapsed, float(r.get("elapsed", 0) or 0))
                merged = concat_audio_chunks(raw_chunks, output_format="MP3")
                merged_b64 = _b64.b64encode(merged).decode()
                res = {
                    "audio_url": "",
                    "audio_data": f"data:audio/mpeg;base64,{merged_b64}",
                    "voice": f"{narration_voice}+dlg",
                    "language": language,
                    "char_count": sum(r.get("char_count", 0) for r in gather),
                    "cost": total_cost,
                    "elapsed": round(total_elapsed, 2),
                    "backend": "xai-multi",
                }
            else:
                print(f"[tts] Scene {scene_index} (seq {sequence_number}): generating {mode_tag} via {backend} {voice}/{language} ({len(spoken)}c, enhance={enhance_elapsed}s)...")
                if backend == "xai":
                    from config import XAI_API_KEY
                    res = await generate_speech_direct_xai(
                        XAI_API_KEY, spoken,
                        voice=voice, language=language,
                    )
                else:
                    res = await generate_speech(
                        self.runware, spoken,
                        voice=voice, language=language,
                        channels=2 if stereo else 1,
                    )

            audio_url = res.get("audio_url", "") or ""
            tts_audio_cost = float(res.get("cost", 0) or 0)
            self._tts_audio_cost_total += tts_audio_cost
            print(f"[tts] Scene {scene_index}: done in {res.get('elapsed')}s (${tts_audio_cost:.4f})")
            if log_ref:
                log_ref.log_tts_result(
                    scene_index, audio_url, res.get("char_count", 0),
                    res.get("cost", 0), res.get("elapsed", 0), enhance_elapsed,
                    enhanced_text=spoken if enhance else None,
                    backend=res.get("backend"),
                )
            await sse_queue.put({
                "type": "scene_audio_ready",
                "index": scene_index,
                "sequence_number": sequence_number,
                "url": audio_url,
                "audio_data": res.get("audio_data"),
                "voice": res.get("voice", voice),
                "language": language,
                "char_count": res.get("char_count", 0),
                "cost": res.get("cost", 0),
                "generation_time": res.get("elapsed", 0),
                "enhanced_text": spoken if enhance else None,
                "for_video_only": for_video_only,
                "dialogue_only": dialogue_only,
                "backend": res.get("backend"),
            })
            if session_id and audio_url:
                import db as _db
                if hasattr(_db, "save_scene_audio"):
                    _db.fire_and_forget(_db.save_scene_audio(
                        session_id, sequence_number, scene_index, audio_url
                    ))
        except Exception as e:
            print(f"[tts] Scene {scene_index}: error — {e}")
            if log_ref:
                log_ref.log_tts_error(scene_index, str(e))
            await sse_queue.put({
                "type": "scene_audio_error",
                "index": scene_index,
                "error": str(e),
            })
        finally:
            StoryEngine._tts_pending -= 1
            if StoryEngine._tts_pending <= 0:
                StoryEngine._tts_pending = 0
                if StoryEngine._tts_done_event:
                    StoryEngine._tts_done_event.set()
        return audio_url

    def _launch_tts(
        self, scene_index: int, narration_text: str,
        sse_queue: asyncio.Queue, sequence_number: int,
        voice: str = "ara", language: str = "fr", enhance: bool = True,
        session_id: str = "",
        dialogue_only: bool = False,
        for_video_only: bool = False,
        stereo: bool = True,
        log_ref: 'SequenceLogger | None' = None,
        narration_voice: str | None = None,
        actor_voices: dict[str, str] | None = None,
        actors_present: list[str] | None = None,
    ) -> asyncio.Task:
        """Launch a TTS task for the given scene's narration. Returns the task so the
        caller can await the audio URL (e.g. for voice-to-video chaining)."""
        if not StoryEngine._tts_done_event:
            StoryEngine._tts_done_event = asyncio.Event()
        StoryEngine._tts_pending += 1
        StoryEngine._tts_done_event.clear()
        task = asyncio.create_task(self._fire_tts_task(
            scene_index, narration_text, sse_queue, sequence_number,
            voice, language, enhance, session_id,
            dialogue_only=dialogue_only, for_video_only=for_video_only,
            stereo=stereo, log_ref=log_ref,
            narration_voice=narration_voice,
            actor_voices=actor_voices,
            actors_present=actors_present,
        ))
        StoryEngine._tts_tasks.append(task)
        return task

    async def _flush_completed_images(
        self, tasks: dict, completed: dict, queue: asyncio.Queue,
        narration_segments: list[str] | None = None,
        session: 'GameSession | None' = None,
        _log: 'SequenceLogger | None' = None,
        davinci_fire_tasks: list | None = None,
        tts_tasks: dict[int, asyncio.Task] | None = None,
    ):
        """Check and emit any completed image tasks."""
        for idx, task in list(tasks.items()):
            if task.done() and idx not in completed:
                await self._emit_image_result(
                    idx, task, completed, queue,
                    narration_segments=narration_segments, session=session,
                    _log=_log, davinci_fire_tasks=davinci_fire_tasks,
                    tts_tasks=tts_tasks,
                )

    async def _emit_image_result(
        self, idx: int, task: asyncio.Task, completed: dict, queue: asyncio.Queue,
        narration_segments: list[str] | None = None,
        session: 'GameSession | None' = None,
        _log: 'SequenceLogger | None' = None,
        davinci_fire_tasks: list | None = None,
        tts_tasks: dict[int, asyncio.Task] | None = None,
    ):
        """Emit image_ready or image_error event. Optionally fire Davinci video gen."""
        try:
            result = await task
            completed[idx] = result
            await queue.put({
                "type": "image_ready",
                "index": idx,
                "url": result["url"],
                "cost": result["cost"],
                "seed": result.get("seed"),
                "generation_time": result["elapsed"],
                "settings": result.get("settings"),
            })

            # Fire per-scene video generation in background (non-blocking)
            video_backend = session.video_settings.get("video_backend", "pvideo") if session else "pvideo"
            # If davinci selected but pod is down, skip silently (don't block)
            if video_backend == "davinci" and not DAVINCI_ENABLED:
                video_backend = "none"
            # video_start_scene: skip video gen for scenes before the threshold (image only)
            video_start_scene = session.video_settings.get("video_start_scene", 0) if session else 0
            if idx < video_start_scene:
                video_backend = "none"
            print(f"[video] Scene {idx}: video_backend={video_backend}, has_url={bool(result.get('url'))}, start_scene={video_start_scene}")

            # ── TTS was launched at tool-call time (in the streaming loop), so the audio
            #    has been generating in parallel with the image. Pick up the task here only
            #    so voice_to_video can chain video on the audio URL. ─────────────────────
            voice_to_video = session.video_settings.get("voice_to_video", False) if session else False
            _seq_num = session.sequence_number if session else 0
            _session_id = session.id if session else ""
            tts_task: asyncio.Task | None = (tts_tasks or {}).get(idx)

            if result.get("url") and narration_segments and video_backend != "none":
                if video_backend == "pvideo":
                    # P-Video (Runware) — fire concurrently (serverless, no queue)
                    _draft = session.video_settings.get("draft", True) if session else True
                    _upsampling = session.video_settings.get("pvideo_prompt_upsampling") if session else None
                    narration_text = narration_segments[idx] if idx < len(narration_segments) else ""
                    prompt = narration_text.strip() or "a person looking at the camera"

                    if voice_to_video and tts_task is not None:
                        # Voice-to-video: video must wait for TTS audio URL, then use it as soundtrack
                        async def _fire_video_after_tts(
                            _t=tts_task, _idx=idx, _url=result["url"], _prompt=prompt,
                            _q=queue, _seq=_seq_num, _draft=_draft, _sid=_session_id,
                            _ups=_upsampling,
                        ):
                            try:
                                audio_url = await _t
                            except Exception as e:
                                print(f"[video] Scene {_idx}: TTS failed ({e}), firing video without audio")
                                audio_url = None
                            self._launch_pvideo(
                                _idx, _url, _prompt, _q,
                                sequence_number=_seq, draft=_draft,
                                session_id=_sid, prompt_upsampling=_ups,
                                audio_url=audio_url or None,
                            )
                        asyncio.create_task(_fire_video_after_tts())
                    else:
                        self._launch_pvideo(
                            idx, result["url"], prompt, queue,
                            sequence_number=_seq_num, draft=_draft,
                            session_id=_session_id,
                            prompt_upsampling=_upsampling,
                        )

                elif video_backend == "davinci":
                    # Davinci (MagiHuman) — Grok vision prompt generation
                    char_name = "a young woman"
                    if session and session.cast:
                        actor_code = (session.cast.get("actors") or [""])[0]
                        if actor_code:
                            actor_info = ACTOR_REGISTRY.get(actor_code, {})
                            desc_text = actor_info.get("description", "")
                            if desc_text:
                                char_name = desc_text
                            elif actor_info.get("prompt_prefix"):
                                char_name = actor_info["prompt_prefix"].split(",")[0]

                    language = getattr(session, 'language', 'fr') if session else 'fr'
                    lang_map = {'fr': 'French', 'en': 'English', 'es': 'Spanish', 'de': 'German', 'ja': 'Japanese'}
                    lang_label = lang_map.get(language, 'French')

                    _video_hd = session.video_settings.get("video_hd", False) if session else False
                    _video_short = session.video_settings.get("video_short", False) if session else False

                    async def _fire_davinci(
                        _idx=idx, _result=result, _char_name=char_name,
                        _lang_label=lang_label, _seq_num=_seq_num,
                        _narration_segments=narration_segments, _queue=queue, _log_ref=_log,
                        _video_hd=_video_hd, _video_short=_video_short,
                        _sid=_session_id,
                    ):
                        narration = _narration_segments[_idx] if _idx < len(_narration_segments) else ""
                        image_prompt = _result.get("settings", {}).get("final_prompt", "")

                        davinci_prompt = await build_davinci_prompt(
                            image_prompt=image_prompt,
                            narration=narration,
                            character_name=_char_name,
                            language=_lang_label,
                            image_url=_result.get("url"),
                        )
                        seed = _result.get("seed")

                        if _log_ref:
                            _log_ref.log_davinci_request(_idx, davinci_prompt, _result["url"], seed)

                        await self._enqueue_davinci(
                            _idx, _result["url"], davinci_prompt, seed, _queue,
                            sequence_number=_seq_num,
                            video_hd=_video_hd, video_short=_video_short,
                            session_id=_sid,
                        )

                    t = asyncio.create_task(_fire_davinci())
                    if davinci_fire_tasks is not None:
                        davinci_fire_tasks.append(t)
        except Exception as e:
            completed[idx] = {"cost": 0, "error": str(e)}
            await queue.put({
                "type": "image_error",
                "index": idx,
                "error": str(e),
            })
