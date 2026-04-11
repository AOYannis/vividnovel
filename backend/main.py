"""
GraphBun Phase 2 — FastAPI Backend
Story orchestration + image generation pipeline.
"""
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List
from openai import AsyncOpenAI
from runware import Runware

from config import (
    RUNWARE_API_KEY, XAI_API_KEY, GROK_BASE_URL, GROK_MODEL,
    ACTOR_REGISTRY, SETTINGS, GROK_PRICING, GROK_MODELS, AVAILABLE_LORAS,
    DEFAULT_STYLE_MOODS, ADMIN_USER_IDS,
    IMAGE_WIDTH, IMAGE_HEIGHT, IMAGE_STEPS,
)
from story_engine import StoryEngine, GameSession
from logger import ChatLogger
from prompt_builder import build_system_prompt, SUPPORTED_LANGUAGES
from auth import get_current_user
from memory import (
    MEM0_ENABLED, delete_session_memories, delete_persistent_memories,
    delete_all_user_memories, recall_persistent_memory, recall_narrative_context,
    store_character_chat, recall_character_memory,
)
import db

# ─── Clients ─────────────────────────────────────────────────────────────────

runware_client: Optional[Runware] = None
grok_client = AsyncOpenAI(api_key=XAI_API_KEY, base_url=GROK_BASE_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runware_client
    try:
        runware_client = Runware(api_key=RUNWARE_API_KEY)
        await runware_client.connect()
        print("[ok] Runware connected")
    except Exception as e:
        print(f"[!!] Runware connection failed: {e}")
        runware_client = None
    yield

app = FastAPI(title="GraphBun Phase 2", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory state ─────────────────────────────────────────────────────────

def get_user_session(session_id: str, user: dict) -> GameSession:
    """Get a session, verifying ownership."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.user_id != user["user_id"]:
        raise HTTPException(403, "Not your session")
    return session

sessions: dict[str, GameSession] = {}

# ─── Request Models ──────────────────────────────────────────────────────────


class PlayerProfile(BaseModel):
    name: str
    age: int
    gender: str
    preferences: str


class StartGameRequest(BaseModel):
    player: PlayerProfile
    setting: str  # "paris_2026" | "paris_1800" | "neo_2100" | "custom"
    actors: list[str]  # ordered list of actor codenames (priority of encounter)
    custom_setting: Optional[str] = None  # user-defined setting description
    system_prompt_override: Optional[str] = None
    style_moods: Optional[dict] = None  # custom mood → LoRA mapping
    grok_model: Optional[str] = None  # override per-session LLM model
    language: Optional[str] = None  # narration language (fr, en, es, de, etc.)
    video_simulate: bool = False
    video_early_start: bool = False
    video_hd: bool = False   # 540p/5s
    video_short: bool = False  # 256p/5s
    video_backend: str = "pvideo"  # "davinci" | "pvideo" | "none"
    pvideo_prompt_upsampling: Optional[bool] = None  # None=runware default, True=force on, False=force off
    custom_character_desc: Optional[str] = None  # description for the "custom" actor


class PreviewPromptRequest(BaseModel):
    player: PlayerProfile
    setting: str
    actors: list[str]
    custom_setting: Optional[str] = None


class SequenceRequest(BaseModel):
    session_id: str
    choice_id: Optional[str] = None
    choice_text: Optional[str] = None


class SystemPromptUpdate(BaseModel):
    session_id: str
    prompt: str


class PromptModifyRequest(BaseModel):
    session_id: str
    instructions: str


# ─── Setup Routes ────────────────────────────────────────────────────────────


@app.get("/api/actors")
async def get_actors():
    """Return available actors for casting."""
    actors = []
    for code, actor in ACTOR_REGISTRY.items():
        actors.append({
            "codename": code,
            "display_name": actor["display_name"],
            "description": actor["description"][:80],  # truncate for display
            "has_lora": bool(actor.get("lora_id")),
            "is_custom": actor.get("is_custom", False),
        })
    return {"actors": actors}


@app.get("/api/settings")
async def get_settings():
    """Return available story settings."""
    settings = []
    for sid, s in SETTINGS.items():
        settings.append({
            "id": sid,
            "label": s["label"],
            "description": s["description"],
        })
    return {"settings": settings}


@app.get("/api/default-style-moods")
async def get_default_style_moods():
    """Return the default style mood configs (full structure with prompt blocks)."""
    return {"style_moods": DEFAULT_STYLE_MOODS, "available_loras": AVAILABLE_LORAS}


@app.get("/api/grok-models")
async def get_grok_models():
    """Return available Grok models with pricing and descriptions."""
    return {
        "models": GROK_MODELS,
        "default": GROK_MODEL,
    }


@app.get("/api/languages")
async def get_languages():
    """Return supported narration languages."""
    return {
        "languages": [
            {"code": code, "label": lang["label"]}
            for code, lang in SUPPORTED_LANGUAGES.items()
        ],
        "default": "fr",
    }


# ─── Game Routes ─────────────────────────────────────────────────────────────


@app.post("/api/game/preview-prompt")
async def preview_system_prompt(req: PreviewPromptRequest):
    """Preview the system prompt before starting the game."""
    if req.setting != "custom" and req.setting not in SETTINGS:
        raise HTTPException(400, f"Unknown setting: {req.setting}")
    cast = {"actors": req.actors}
    prompt = build_system_prompt(
        player=req.player.model_dump(),
        cast=cast,
        setting_id=req.setting,
        custom_setting_text=req.custom_setting,
    )
    return {"prompt": prompt}


@app.post("/api/game/start")
async def start_game(req: StartGameRequest, user: dict = Depends(get_current_user)):
    """Create a new game session."""
    if req.setting != "custom" and req.setting not in SETTINGS:
        raise HTTPException(400, f"Unknown setting: {req.setting}")
    if not req.actors:
        raise HTTPException(400, "Must select at least one actor")
    for actor_code in req.actors:
        if actor_code not in ACTOR_REGISTRY:
            raise HTTPException(400, f"Unknown actor: {actor_code}")
    if len(req.actors) != len(set(req.actors)):
        raise HTTPException(400, "Duplicate actors not allowed")

    cast = {"actors": req.actors}
    session_id = str(uuid.uuid4())
    session = GameSession(
        session_id=session_id,
        player=req.player.model_dump(),
        setting=req.setting,
        cast=cast,
        user_id=user["user_id"],
    )
    if req.grok_model and req.grok_model in GROK_PRICING:
        session.grok_model = req.grok_model
    if req.language:
        session.language = req.language
    if req.custom_setting:
        session.custom_setting_text = req.custom_setting
    if req.system_prompt_override:
        session.system_prompt_override = req.system_prompt_override
    if req.style_moods:
        session.style_moods = req.style_moods
    if req.video_simulate:
        session.video_settings["simulate"] = True
    if req.video_early_start:
        session.video_settings["early_start"] = True
    if req.video_hd:
        session.video_settings["video_hd"] = True
    if req.video_short:
        session.video_settings["video_short"] = True
    if req.video_backend:
        session.video_settings["video_backend"] = req.video_backend
    if req.pvideo_prompt_upsampling is not None:
        session.video_settings["pvideo_prompt_upsampling"] = req.pvideo_prompt_upsampling
    # Patch custom character description into ACTOR_REGISTRY for this session
    if req.custom_character_desc:
        session._custom_actor_override = {
            "description": req.custom_character_desc,
            "prompt_prefix": req.custom_character_desc,
        }
    sessions[session_id] = session

    # Persist to DB (fire-and-forget)
    db.fire_and_forget(db.save_session(session))

    cast_info = {code: ACTOR_REGISTRY[code] for code in req.actors}
    setting_info = SETTINGS.get(req.setting) or {
        "label": "Personnalisé",
        "description": req.custom_setting or "",
        "era": "custom",
    }
    return {
        "session_id": session_id,
        "player": req.player.model_dump(),
        "setting": setting_info,
        "cast": cast_info,
    }


@app.post("/api/game/sequence")
async def run_sequence(req: SequenceRequest, user: dict = Depends(get_current_user)):
    """Stream a story sequence via SSE."""
    session = get_user_session(req.session_id, user)
    if runware_client is None:
        raise HTTPException(503, "Runware not connected")

    engine = StoryEngine(grok_client, runware_client)

    async def event_stream():
        try:
            async for event in engine.run_sequence(
                session,
                choice_id=req.choice_id,
                choice_text=req.choice_text,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── Scene Chat Route ────────────────────────────────────────────────────────


class SceneChatRequest(BaseModel):
    session_id: str
    scene_index: int
    message: str
    current_narration: str = ""
    image_prompt: str = ""
    image_seed: Optional[int] = None
    actors_present: List[str] = []
    style_moods: List[str] = ["neutral"]
    location_description: str = ""
    clothing_state: Optional[dict] = None


@app.post("/api/game/scene-chat")
async def scene_chat(req: SceneChatRequest, user: dict = Depends(get_current_user)):
    """Chat with a character or perform an action within a scene.

    Streams: narration response + adapted image generation.
    """
    session = get_user_session(req.session_id, user)
    if runware_client is None:
        raise HTTPException(503, "Runware not connected")

    engine = StoryEngine(grok_client, runware_client)

    async def event_stream():
        chat_log = ChatLogger(req.session_id, req.scene_index, session.grok_model)
        try:
            # Recall what the characters know about the player
            char_context = ""
            if MEM0_ENABLED and req.actors_present:
                import asyncio
                for char_code in req.actors_present:
                    try:
                        char_mem = await asyncio.get_event_loop().run_in_executor(
                            None, lambda c=char_code: recall_character_memory(session.user_id, c, setting_id=session.setting)
                        )
                        if char_mem:
                            char_context += f"\nCe que {char_code} sait sur le joueur :\n{char_mem}\n"
                    except Exception:
                        pass

            # Build a focused chat prompt
            system_msg = (
                f"Tu es le narrateur d'un roman visuel interactif. "
                f"Le joueur interagit avec la scène en cours.\n\n"
                f"Contexte de la scène :\n{req.current_narration}\n\n"
                f"Lieu : {req.location_description}\n"
                f"Personnages présents : {', '.join(req.actors_present)}\n"
            )
            if char_context:
                system_msg += f"\n{char_context}\n"
            # List available moods for the agent
            from config import DEFAULT_STYLE_MOODS
            mood_list = ", ".join(DEFAULT_STYLE_MOODS.keys())

            system_msg += (
                f"\nRéponds en 2-4 phrases, à la 2e personne ('tu'), dans le même style "
                f"que la narration. Décris ce qui se passe suite à l'action/message du joueur. "
                f"Reste cohérent avec la scène. Si le personnage sait quelque chose sur le joueur "
                f"(voir mémoire ci-dessus), il peut y faire référence naturellement.\n\n"
                f"Ensuite, fournis DEUX lignes techniques (en anglais) :\n\n"
                f"IMAGE_CHANGE: [description des changements visuels par rapport à l'image actuelle, en anglais]\n"
                f"MOOD: [le mood approprié pour la nouvelle image]\n\n"
                f"Moods disponibles : {mood_list}\n\n"
                f"Exemples :\n"
                f"IMAGE_CHANGE: she is now laughing with head tilted back, eyes crinkled\n"
                f"MOOD: neutral\n\n"
                f"IMAGE_CHANGE: she pulls her dress strap off shoulder, biting her lip\n"
                f"MOOD: sensual_tease\n\n"
                f"IMAGE_CHANGE: close-up, lips wrapped around shaft, gaze upward\n"
                f"MOOD: blowjob\n\n"
                f"Choisis le mood qui correspond à l'action. "
                f"Génère TOUJOURS une ligne IMAGE_CHANGE (même minime : expression, posture, geste)."
            )

            # Use session's language
            lang = getattr(session, 'language', 'fr')
            if lang != 'fr':
                from prompt_builder import SUPPORTED_LANGUAGES
                lang_label = SUPPORTED_LANGUAGES.get(lang, {}).get('label', lang)
                system_msg += f"\n\nIMPORTANT: La narration doit être en {lang_label}."

            chat_log.log_request(req.message, req.actors_present, char_context, req.style_moods)

            stream = await grok_client.chat.completions.create(
                model=session.grok_model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": req.message},
                ],
                stream=True,
            )

            full_text = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_text += text
                    # Stream narration but not the IMAGE_CHANGE line
                    if "IMAGE_CHANGE:" not in full_text:
                        yield f"data: {json.dumps({'type': 'narration_delta', 'content': text})}\n\n"

            # Parse out IMAGE_CHANGE and MOOD directives
            narration_text = full_text
            image_change = ""
            new_mood = ""
            if "IMAGE_CHANGE:" in full_text:
                parts = full_text.split("IMAGE_CHANGE:")
                narration_text = parts[0].strip()
                remainder = parts[1].strip()
                # Extract MOOD if present
                if "MOOD:" in remainder:
                    change_parts = remainder.split("MOOD:")
                    image_change = change_parts[0].strip()
                    new_mood = change_parts[1].strip().split()[0] if change_parts[1].strip() else ""
                else:
                    image_change = remainder

            chat_log.log_response(narration_text, image_change, new_mood)
            yield f"data: {json.dumps({'type': 'narration_done', 'text': narration_text})}\n\n"

            # Always generate an adapted image if we have a base prompt
            if image_change and req.image_prompt:
                yield f"data: {json.dumps({'type': 'image_generating'})}\n\n"

                # Use the mood from Grok, fall back to original
                active_moods = [new_mood] if new_mood and new_mood in DEFAULT_STYLE_MOODS else req.style_moods
                mood_changed = new_mood and new_mood in DEFAULT_STYLE_MOODS and [new_mood] != req.style_moods

                # Build adapted prompt: insert change before camera settings
                adapted_prompt = req.image_prompt
                if ". Shot on" in adapted_prompt:
                    before_cam, after_cam = adapted_prompt.split(". Shot on", 1)
                    adapted_prompt = f"{before_cam}. {image_change}. Shot on{after_cam}"
                else:
                    adapted_prompt = f"{adapted_prompt}, {image_change}"

                # If the mood changed (different position), drop the seed —
                # a new pose needs a fresh composition, same seed forces the old layout
                use_seed = None if mood_changed else req.image_seed

                try:
                    args = {
                        "image_prompt": adapted_prompt,
                        "actors_present": req.actors_present,
                        "style_moods": active_moods,
                        "seed": use_seed,
                    }
                    result = await engine._generate_image(
                        args, session.cast,
                        session.style_loras, session.extra_loras,
                    )
                    chat_log.log_image(
                        adapted_prompt, active_moods,
                        result.get("settings", {}).get("loras", []),
                        result.get("seed"), result.get("cost", 0), result.get("elapsed", 0),
                    )
                    yield f"data: {json.dumps({'type': 'image_ready', 'url': result['url'], 'cost': result['cost'], 'prompt': adapted_prompt, 'mood': active_moods})}\n\n"
                except Exception as e:
                    chat_log.log_error(str(e))
                    yield f"data: {json.dumps({'type': 'image_error', 'error': str(e)})}\n\n"

            # Store chat exchange in each character's memory (fire-and-forget)
            if MEM0_ENABLED and narration_text and req.actors_present:
                import asyncio
                _msg = req.message
                _resp = narration_text
                _uid = session.user_id
                _setting = session.setting
                _actors = list(req.actors_present)
                def _store_chat():
                    for char_code in _actors:
                        store_character_chat(_uid, char_code, _msg, _resp, setting_id=_setting)
                asyncio.get_event_loop().run_in_executor(None, _store_chat)

            chat_log.finish()
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            chat_log.log_error(str(e))
            chat_log.finish()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── Phone Chat Route ────────────────────────────────────────────────────────


class PhoneChatRequest(BaseModel):
    session_id: str
    character_code: str  # codename of the character to chat with
    message: str


@app.post("/api/game/phone-chat")
async def phone_chat(req: PhoneChatRequest, user: dict = Depends(get_current_user)):
    """Chat with a character via the in-game phone.

    Uses character memory for context. Character can optionally send a selfie.
    Exchange is stored in character memory for future narrative use.
    """
    session = get_user_session(req.session_id, user)

    # Get character info
    from config import ACTOR_REGISTRY
    actor = ACTOR_REGISTRY.get(req.character_code, {})
    display_name = actor.get("display_name", req.character_code)

    # Recall what this character knows + narrative context
    char_context = ""
    narrative_context = ""
    if MEM0_ENABLED:
        import asyncio
        try:
            char_context = await asyncio.get_event_loop().run_in_executor(
                None, lambda: recall_character_memory(session.user_id, req.character_code, setting_id=session.setting)
            )
        except Exception:
            pass
        try:
            narrative_context = await asyncio.get_event_loop().run_in_executor(
                None, lambda: recall_narrative_context(session.id, session.user_id)
            )
        except Exception:
            pass

    # Also get the recent narration recap from conversation history
    narration_recap = ""
    if session.conversation_history:
        parts = [m.get("content", "") for m in session.conversation_history if m.get("role") == "assistant" and m.get("content")]
        if parts:
            narration_recap = "\n".join(parts[-3:])  # last 3 narration blocks

    async def event_stream():
        chat_log = ChatLogger(req.session_id, -1, session.grok_model)
        try:
            # Get player info for context
            player_name = session.player.get("name", "le joueur")

            system_msg = (
                f"Tu incarnes {display_name}, un personnage d'un roman visuel interactif. "
                f"{player_name} t'envoie un message sur ton téléphone.\n\n"
                f"Tu es {display_name}. Apparence : {actor.get('description', 'inconnue')}.\n"
                f"Cadre de l'histoire : {session.setting}\n"
                f"Le joueur s'appelle {player_name}.\n\n"
            )
            if char_context:
                system_msg += (
                    f"Voici ce que tu sais sur {player_name} (tes souvenirs personnels) :\n{char_context}\n\n"
                )
            if narration_recap:
                system_msg += (
                    f"Ce qui s'est passé récemment dans l'histoire :\n{narration_recap}\n\n"
                )
            if narrative_context:
                system_msg += (
                    f"Contexte narratif général :\n{narrative_context}\n\n"
                )
            system_msg += (
                f"Réponds comme {display_name} répondrait par message : "
                f"naturel, en character, avec sa personnalité. "
                f"Messages courts (1-3 phrases), comme un vrai texto. "
                f"Tu peux utiliser des émojis si ça correspond au personnage. "
                f"Tu te souviens de ce qui s'est passé avec le joueur.\n\n"
                f"Si la conversation devient visuelle (le joueur demande une photo, "
                f"ou tu veux montrer où tu es / ce que tu fais), ajoute à la fin :\n"
                f"SELFIE: [description en anglais de la photo que tu enverrais, "
                f"incluant ton apparence, ta tenue actuelle, le lieu, l'éclairage, style selfie]\n"
                f"Sinon, n'ajoute PAS de ligne SELFIE.\n\n"
                f"Ne JAMAIS mentionner le nom d'un acteur/actrice célèbre."
            )

            # Use session's language
            lang = getattr(session, 'language', 'fr')
            if lang != 'fr':
                from prompt_builder import SUPPORTED_LANGUAGES
                lang_label = SUPPORTED_LANGUAGES.get(lang, {}).get('label', lang)
                system_msg += f"\n\nIMPORTANT: Réponds en {lang_label}."

            chat_log.log_request(req.message, [req.character_code], char_context, [])

            stream = await grok_client.chat.completions.create(
                model=session.grok_model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": req.message},
                ],
                stream=True,
            )

            full_text = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_text += text
                    if "SELFIE:" not in full_text:
                        yield f"data: {json.dumps({'type': 'message_delta', 'content': text})}\n\n"

            # Parse out selfie directive
            message_text = full_text
            selfie_prompt = ""
            if "SELFIE:" in full_text:
                parts = full_text.split("SELFIE:")
                message_text = parts[0].strip()
                selfie_prompt = parts[1].strip()

            chat_log.log_response(message_text, selfie_prompt, "")
            yield f"data: {json.dumps({'type': 'message_done', 'text': message_text, 'character': req.character_code})}\n\n"

            # Generate selfie if requested
            if selfie_prompt and runware_client:
                yield f"data: {json.dumps({'type': 'selfie_generating'})}\n\n"
                try:
                    engine = StoryEngine(grok_client, runware_client)
                    # Build selfie prompt with character trigger word
                    tw = actor.get("trigger_word", "")
                    prefix = actor.get("prompt_prefix", "")
                    full_selfie = selfie_prompt
                    if tw:
                        full_selfie = f"{tw}, {selfie_prompt}"
                    elif prefix:
                        full_selfie = f"{prefix}, {selfie_prompt}"

                    # Add selfie-style keywords
                    full_selfie += (
                        ", selfie photo, front-facing camera, casual phone photo, "
                        "natural lighting, highly detailed skin texture, subtle skin pores, "
                        "natural skin tones, shot on smartphone camera, shallow depth of field"
                    )

                    args = {
                        "image_prompt": full_selfie,
                        "actors_present": [req.character_code],
                        "style_moods": ["neutral"],
                    }
                    # Use a cast with ONLY the contacted character to avoid
                    # loading the current sequence's actor LoRA on the selfie
                    selfie_cast = {"actors": [req.character_code]}
                    result = await engine._generate_image(
                        args, selfie_cast,
                        session.style_loras, session.extra_loras,
                    )
                    chat_log.log_image(full_selfie, ["neutral"],
                                       result.get("settings", {}).get("loras", []),
                                       result.get("seed"), result.get("cost", 0), result.get("elapsed", 0))
                    yield f"data: {json.dumps({'type': 'selfie_ready', 'url': result['url'], 'cost': result['cost']})}\n\n"
                except Exception as e:
                    chat_log.log_error(f"Selfie generation failed: {e}")
                    yield f"data: {json.dumps({'type': 'selfie_error', 'error': str(e)})}\n\n"

            # Store in character memory
            if MEM0_ENABLED:
                import asyncio
                _uid = session.user_id
                _setting = session.setting
                _char = req.character_code
                _msg = req.message
                _resp = message_text
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: store_character_chat(_uid, _char, f"[phone] {_msg}", _resp, setting_id=_setting)
                )

            chat_log.finish()
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            chat_log.log_error(str(e))
            chat_log.finish()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── Rewrite Prompt Route ─────────────────────────────────────────────────────


class RewritePromptRequest(BaseModel):
    current_prompt: str
    instructions: str


@app.post("/api/game/rewrite-prompt")
async def rewrite_image_prompt(req: RewritePromptRequest):
    """Ask Grok to rewrite an image prompt based on instructions."""
    async def event_stream():
        try:
            stream = await grok_client.chat.completions.create(
                model=GROK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You rewrite image prompts for Z-Image Turbo. "
                            "You receive a current prompt and modification instructions. "
                            "Return ONLY the modified prompt, keeping the Camera Director structure: "
                            "Layer 1 (Subject & Action), Layer 2 (Setting), Layer 3 (Lighting), "
                            "Layer 4 (Camera & Style). "
                            "Always include skin realism keywords: 'highly detailed skin texture', "
                            "'subtle skin pores', 'natural skin tones'. "
                            "Always end with a camera/lens and photography style. "
                            "Never use negation words (no, not, without) — the model ignores them. "
                            "Never use: selfie, phone, camera (as object), mirror, blur, artifact. "
                            "Describe only what IS in the scene."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Current prompt:\n{req.current_prompt}\n\n"
                            f"Modification:\n{req.instructions}\n\n"
                            f"Return the modified prompt:"
                        ),
                    },
                ],
                stream=True,
            )
            full_text = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_text += text
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── Regen Routes ────────────────────────────────────────────────────────────


class RegenLoraOverride(BaseModel):
    id: str
    weight: float = 1.0


class RegenImageRequest(BaseModel):
    session_id: str
    prompt: str
    actors_present: List[str] = []
    image_index: Optional[int] = None
    use_nsfw_style: bool = False
    seed: Optional[int] = None
    lora_overrides: Optional[List[RegenLoraOverride]] = None  # if set, replaces ALL auto LoRAs
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None


class RegenVideoRequest(BaseModel):
    session_id: str
    prompt: str
    input_image_url: str


@app.post("/api/game/regen-image")
async def regen_image(req: RegenImageRequest, user: dict = Depends(get_current_user)):
    """Regenerate an image with current session LoRA settings."""
    session = get_user_session(req.session_id, user)
    if runware_client is None:
        raise HTTPException(503, "Runware not connected")

    engine = StoryEngine(grok_client, runware_client)
    args = {
        "image_prompt": req.prompt,
        "actors_present": req.actors_present if not req.lora_overrides else [],  # skip auto actors if overrides
        "use_nsfw_style": req.use_nsfw_style,
        "seed": req.seed,
    }

    # Override resolution/steps if provided
    overrides = {}
    if req.width: overrides["width"] = req.width
    if req.height: overrides["height"] = req.height
    if req.steps: overrides["steps"] = req.steps

    try:
        if req.lora_overrides is not None:
            # Full manual control: use only the provided LoRAs
            manual_loras = [{"id": l.id, "weight": l.weight} for l in req.lora_overrides]
            result = await engine._generate_image(
                args, session.cast,
                style_loras=manual_loras,
                extra_loras=[],
                **overrides,
            )
        else:
            result = await engine._generate_image(
                args, session.cast, session.style_loras, session.extra_loras,
                **overrides,
            )
        # Record the prompt override for consistency tracking
        if req.image_index is not None:
            session.consistency.record_prompt_override(req.image_index, req.prompt)
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/game/regen-video")
async def regen_video(req: RegenVideoRequest, user: dict = Depends(get_current_user)):
    """Regenerate a video with current session video settings."""
    session = get_user_session(req.session_id, user)
    if runware_client is None:
        raise HTTPException(503, "Runware not connected")

    engine = StoryEngine(grok_client, runware_client)
    try:
        result = await engine._generate_video(
            req.prompt, req.input_image_url, session.video_settings
        )
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, str(e))


class RegenSceneVideoRequest(BaseModel):
    session_id: str
    scene_index: int
    image_url: str         # source image URL
    prompt: str = ""       # video prompt — if empty, fallback
    draft: bool = False    # non-draft by default for regen


@app.post("/api/game/regen-scene-video")
async def regen_scene_video(req: RegenSceneVideoRequest, user: dict = Depends(get_current_user)):
    """Regenerate a per-scene video (P-Video via Runware) with prompt editing and draft control."""
    session = get_user_session(req.session_id, user)
    if runware_client is None:
        raise HTTPException(503, "Runware not connected")

    import time as _time

    prompt = req.prompt.strip()
    if not prompt:
        prompt = "a person looking at the camera"

    engine = StoryEngine(grok_client, runware_client)
    start = _time.time()
    try:
        result = await engine._generate_video(prompt, req.image_url, {
            "draft": req.draft,
            "audio": True,
            "duration": 5,
            "resolution": "720p",
        })
    except Exception as e:
        raise HTTPException(500, str(e))

    elapsed = round(_time.time() - start, 1)
    video_url = result.get("url", "")
    video_cost = result.get("cost", 0) or 0

    # Persist to DB
    if video_url:
        import db as _db
        _db.fire_and_forget(_db.save_scene_video(
            req.session_id, session.sequence_number, req.scene_index, video_url
        ))
        if video_cost > 0:
            _db.fire_and_forget(_db.add_scene_video_cost(req.session_id, video_cost))

    return {
        "video_url": video_url,
        "cost": video_cost,
        "elapsed": elapsed,
        "draft": req.draft,
        "prompt_used": prompt,
    }


# ─── Debug Routes ────────────────────────────────────────────────────────────


@app.get("/api/debug/system-prompt/{session_id}")
async def get_system_prompt(session_id: str):
    """Get the current system prompt for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    current = session.system_prompt_override or build_system_prompt(
        player=session.player,
        cast=session.cast,
        setting_id=session.setting,
        consistency_state=session.consistency.to_dict(),
        sequence_number=session.sequence_number,
    )
    return {"prompt": current, "is_override": bool(session.system_prompt_override)}


@app.put("/api/debug/system-prompt")
async def update_system_prompt(req: SystemPromptUpdate):
    """Override the system prompt for a session."""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.system_prompt_override = req.prompt
    db.fire_and_forget(db.save_session(session))
    return {"ok": True}


@app.delete("/api/debug/system-prompt/{session_id}")
async def reset_system_prompt(session_id: str):
    """Reset to auto-generated system prompt."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.system_prompt_override = ""
    return {"ok": True}


@app.post("/api/debug/modify-prompt")
async def modify_prompt_with_grok(req: PromptModifyRequest):
    """Ask Grok to modify the system prompt based on instructions."""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    current = session.system_prompt_override or build_system_prompt(
        player=session.player,
        cast=session.cast,
        setting_id=session.setting,
        consistency_state=session.consistency.to_dict(),
        sequence_number=session.sequence_number,
    )

    async def event_stream():
        try:
            stream = await grok_client.chat.completions.create(
                model=GROK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un expert en prompt engineering. "
                            "On te donne un system prompt existant et des instructions de modification. "
                            "Retourne UNIQUEMENT le nouveau system prompt modifié, sans explication."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"## System prompt actuel :\n\n{current}\n\n"
                            f"## Instructions de modification :\n\n{req.instructions}\n\n"
                            f"Retourne le prompt modifié :"
                        ),
                    },
                ],
                stream=True,
            )
            full_text = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_text += text
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/debug/session/{session_id}")
async def get_session_debug(session_id: str):
    """Full session debug info."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {
        "id": session.id,
        "sequence_number": session.sequence_number,
        "grok_model": session.grok_model,
        "consistency": session.consistency.to_dict(),
        "costs": session.total_costs,
        "image_prompts": session.consistency.previous_prompts,
        "conversation_length": len(session.conversation_history),
        "video_settings": session.video_settings,
    }


# ─── Model Selection Routes ──────────────────────────────────────────────────


class ModelUpdate(BaseModel):
    session_id: str
    grok_model: str


@app.get("/api/debug/grok-model/{session_id}")
async def get_session_model(session_id: str):
    """Get current Grok model for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"grok_model": session.grok_model}


@app.put("/api/debug/grok-model")
async def update_session_model(req: ModelUpdate):
    """Change Grok model for a session (takes effect on next sequence)."""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if req.grok_model not in GROK_PRICING:
        raise HTTPException(400, f"Unknown model: {req.grok_model}. Available: {list(GROK_PRICING.keys())}")
    session.grok_model = req.grok_model
    return {"ok": True, "grok_model": session.grok_model}


# ─── Memory Debug Routes ────────────────────────────────────────────────────


@app.get("/api/debug/memories/{session_id}")
async def get_session_memories(session_id: str):
    """Fetch all Mem0 memories that would be injected for this session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    persistent = ""
    narrative = ""

    if MEM0_ENABLED:
        import asyncio
        cast_codes = session.cast.get("actors", [])

        try:
            persistent = await asyncio.get_event_loop().run_in_executor(
                None, lambda: recall_persistent_memory(
                    user_id=session.user_id,
                    cast_codenames=cast_codes,
                    setting_id=session.setting,
                )
            )
        except Exception:
            persistent = "(error fetching persistent memories)"

        if session.sequence_number > 0:
            try:
                narrative = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: recall_narrative_context(
                        session_id=session.id,
                        user_id=session.user_id,
                    )
                )
            except Exception:
                narrative = "(error fetching narrative memories)"

    return {
        "mem0_enabled": MEM0_ENABLED,
        "persistent_memory": persistent,
        "narrative_memory": narrative,
        "setting_id": session.setting,
        "sequence_number": session.sequence_number,
    }


# ─── Style Moods Routes ──────────────────────────────────────────────────────


@app.get("/api/debug/style-moods/{session_id}")
async def get_style_moods(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"style_moods": session.style_moods}


class StyleMoodEntry(BaseModel):
    mood: str
    lora_id: Optional[str] = None
    lora_name: Optional[str] = None
    weight: float = 0.6


class StyleMoodsUpdate(BaseModel):
    session_id: str
    moods: List[StyleMoodEntry]


@app.put("/api/debug/style-moods")
async def update_style_moods(req: StyleMoodsUpdate):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    new_moods = {}
    for entry in req.moods:
        if entry.lora_id:
            new_moods[entry.mood] = {"id": entry.lora_id, "name": entry.lora_name or entry.mood, "weight": entry.weight}
        else:
            new_moods[entry.mood] = None
    session.style_moods = new_moods
    return {"ok": True, "style_moods": new_moods}


# ─── Video Settings Routes ────────────────────────────────────────────────────


class VideoSettingsUpdate(BaseModel):
    session_id: str
    draft: bool = True
    audio: bool = True
    duration: int = 5
    resolution: str = "720p"
    simulate: bool = False
    early_start: bool = False


@app.get("/api/debug/video-settings/{session_id}")
async def get_video_settings(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"video_settings": session.video_settings}


@app.put("/api/debug/video-settings")
async def update_video_settings(req: VideoSettingsUpdate):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.video_settings = {
        "draft": req.draft,
        "audio": req.audio,
        "duration": req.duration,
        "resolution": req.resolution,
        "simulate": req.simulate,
        "early_start": req.early_start,
    }
    return {"ok": True, "video_settings": session.video_settings}


# ─── Extra LoRA Routes ────────────────────────────────────────────────────────


class ExtraLoraItem(BaseModel):
    id: str
    weight: float = 1.0


class ExtraLorasUpdate(BaseModel):
    session_id: str
    extra_loras: List[ExtraLoraItem]


class StyleLorasUpdate(BaseModel):
    session_id: str
    style_loras: List[ExtraLoraItem]


@app.get("/api/debug/loras")
async def get_available_loras():
    """All LoRAs available for the debug picker."""
    return {"loras": AVAILABLE_LORAS}


@app.get("/api/debug/style-loras/{session_id}")
async def get_style_loras(session_id: str):
    """Get default style LoRAs for a session (can be removed/modified)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"style_loras": session.style_loras}


@app.put("/api/debug/style-loras")
async def update_style_loras(req: StyleLorasUpdate):
    """Update default style LoRAs for a session."""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.style_loras = [{"id": l.id, "weight": l.weight} for l in req.style_loras]
    return {"ok": True, "style_loras": session.style_loras}


@app.get("/api/debug/extra-loras/{session_id}")
async def get_extra_loras(session_id: str):
    """Get extra LoRAs for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"extra_loras": session.extra_loras}


@app.put("/api/debug/extra-loras")
async def update_extra_loras(req: ExtraLorasUpdate):
    """Set extra LoRAs for a session (added to every image gen on top of model-chosen ones)."""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.extra_loras = [{"id": l.id, "weight": l.weight} for l in req.extra_loras]
    return {"ok": True, "extra_loras": session.extra_loras}


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)


# ─── Admin Routes ────────────────────────────────────────────────────────────


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["user_id"] not in ADMIN_USER_IDS:
        raise HTTPException(403, "Admin access required")
    return user


@app.get("/api/admin/costs")
async def admin_costs(user: dict = Depends(require_admin)):
    """Aggregate costs across all users (admin only)."""
    data = await db.admin_get_all_costs()
    return data


@app.get("/api/admin/check")
async def admin_check(user: dict = Depends(get_current_user)):
    """Check if current user is admin."""
    return {"is_admin": user["user_id"] in ADMIN_USER_IDS}


# ─── Session History Routes ──────────────────────────────────────────────────


@app.get("/api/user/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    """List all saved game sessions for the authenticated user."""
    data = await db.list_user_sessions(user["user_id"])
    return {"sessions": data}


@app.post("/api/user/sessions/{session_id}/resume")
async def resume_session(session_id: str, user: dict = Depends(get_current_user)):
    """Resume a saved session — load from DB into memory."""
    # Already in memory?
    if session_id in sessions:
        s = sessions[session_id]
        if s.user_id != user["user_id"]:
            raise HTTPException(403, "Not your session")
        return {"session_id": session_id, "sequence_number": s.sequence_number}

    # Load from DB
    row = await db.load_session_data(session_id, user["user_id"])
    if not row:
        raise HTTPException(404, "Session not found")

    session = GameSession(
        session_id=row["id"],
        player=row["player"],
        setting=row["setting"],
        cast=row["cast_config"],
        user_id=row["user_id"],
    )
    session.sequence_number = row.get("sequence_number", 0)
    session.conversation_history = row.get("conversation_history", [])
    session.system_prompt_override = row.get("system_prompt_override", "")
    session.custom_setting_text = row.get("custom_setting_text", "")
    session.grok_model = row.get("grok_model", GROK_MODEL)
    session.language = row.get("language", "fr")
    session.style_loras = row.get("style_loras", [])
    session.extra_loras = row.get("extra_loras", [])
    session.video_settings = row.get("video_settings", {})
    session.total_costs = row.get("total_costs", {})
    # Restore consistency
    cs = row.get("consistency_state", {})
    session.consistency.location = cs.get("location", "")
    session.consistency.clothing = cs.get("clothing", {})
    session.consistency.props = cs.get("props", [])
    session.consistency.prompt_overrides = {int(k): v for k, v in cs.get("prompt_overrides", {}).items()}
    session.consistency.secondary_characters = cs.get("secondary_characters", {})
    session.consistency.character_actors = cs.get("character_actors", {})

    sessions[session_id] = session

    # Derive met_characters + character_names from history (for the phone UI)
    met_characters: list[str] = []
    character_names: dict[str, str] = {}
    try:
        history = await db.load_sequence_history(session_id)
        for seq in history:
            for img in seq.get("images") or []:
                for actor in img.get("actors_present") or []:
                    if actor and actor not in met_characters:
                        met_characters.append(actor)
        # Invert the locked character_actors mapping (display_name → code) to get (code → display_name)
        for display_name, actor_code in session.consistency.character_actors.items():
            character_names[actor_code] = display_name
    except Exception:
        pass

    return {
        "session_id": session_id,
        "sequence_number": session.sequence_number,
        "player": session.player,
        "setting": session.setting,
        "cast": session.cast,
        "met_characters": met_characters,
        "character_names": character_names,
    }


@app.get("/api/user/sessions/{session_id}/history")
async def get_session_history(session_id: str, user: dict = Depends(get_current_user)):
    """Get all sequences with images/videos for a session (replay)."""
    # Verify ownership
    row = await db.load_session_data(session_id, user["user_id"])
    if not row:
        raise HTTPException(404, "Session not found")
    history = await db.load_sequence_history(session_id)
    return {"session": row, "sequences": history}


@app.delete("/api/user/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    """Delete a saved session and its Mem0 memories."""
    user_id = user["user_id"]
    # Remove from memory if present
    if session_id in sessions:
        s = sessions[session_id]
        if s.user_id != user_id:
            raise HTTPException(403, "Not your session")
        del sessions[session_id]
    # Delete session memories from Mem0 (fire-and-forget)
    if MEM0_ENABLED:
        import asyncio
        asyncio.get_event_loop().run_in_executor(
            None, lambda: delete_session_memories(user_id, session_id)
        )
    # Delete from DB
    ok = await db.delete_session(session_id, user_id)
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"ok": True}


@app.delete("/api/user/memories")
async def clear_all_memories(user: dict = Depends(get_current_user)):
    """Clear ALL Mem0 memories for the current user (all settings)."""
    if not MEM0_ENABLED:
        return {"ok": True, "cleared": 0, "message": "Mem0 not enabled"}
    user_id = user["user_id"]
    # Clear persistent memories for all known settings + empty setting
    all_settings = list(SETTINGS.keys()) + ["custom", ""]
    import asyncio
    cleared = await asyncio.get_event_loop().run_in_executor(
        None, lambda: delete_all_user_memories(user_id, all_settings)
    )
    return {"ok": True, "cleared": cleared}


# ─── Playground (no auth) ────────────────────────────────────────────────────

@app.get("/api/playground/config")
async def playground_config():
    """Return actors, settings, moods, LoRAs, and defaults for the playground UI."""
    actors = [
        {"code": code, "name": info["display_name"], "description": info.get("description", "")}
        for code, info in ACTOR_REGISTRY.items()
        if code != "custom"
    ]
    settings = [
        {"id": sid, "name": sdata.get("name", sid)}
        for sid, sdata in SETTINGS.items()
    ]
    moods = {
        k: {
            "description": v.get("description", k),
            "prompt_block": v.get("prompt_block", ""),
            "lora": v.get("lora"),
        }
        for k, v in DEFAULT_STYLE_MOODS.items()
    }
    return {
        "actors": actors,
        "settings": settings,
        "moods": moods,
        "loras": AVAILABLE_LORAS,
        "defaults": {"width": IMAGE_WIDTH, "height": IMAGE_HEIGHT, "steps": IMAGE_STEPS},
        "languages": list(SUPPORTED_LANGUAGES.keys()),
    }


class PlaygroundRequest(BaseModel):
    scene_description: str
    actor: str = "nataly"
    setting: str = "paris_2026"
    mood: str = "neutral"
    language: str = "fr"
    width: int = IMAGE_WIDTH
    height: int = IMAGE_HEIGHT
    steps: int = IMAGE_STEPS
    seed: Optional[int] = None
    lora_overrides: Optional[List[dict]] = None
    skip_image: bool = False
    raw_mode: bool = False  # if True, skip Grok and use scene_description as-is
    custom_mood_block: Optional[str] = None  # custom mood prompt_block override


@app.post("/api/playground/generate")
async def playground_generate(req: PlaygroundRequest):
    """Two-step playground: Grok simulates image prompt, then generates the image.
    If raw_mode=True, skip Grok and use scene_description as-is (with mood block + actor trigger).
    """
    from tools import SCENE_IMAGE_TOOL
    import json as _json

    if req.actor not in ACTOR_REGISTRY:
        raise HTTPException(400, f"Unknown actor: {req.actor}")

    cast = {"actors": [req.actor]}

    # ── Raw mode: build the prompt directly without Grok ──
    if req.raw_mode:
        actor_data = ACTOR_REGISTRY[req.actor]
        trigger = actor_data.get("trigger_word", "") or actor_data.get("prompt_prefix", "")
        # Use custom mood block if provided, else look up the mood
        mood_block = req.custom_mood_block
        if not mood_block:
            mood_data = DEFAULT_STYLE_MOODS.get(req.mood, {})
            mood_block = mood_data.get("prompt_block", "")

        parts = []
        if trigger:
            parts.append(trigger)
        if mood_block:
            parts.append(mood_block)
        parts.append(req.scene_description)
        simulated_prompt = ", ".join(p for p in parts if p)

        result = {
            "simulated_prompt": simulated_prompt,
            "actors_present": [req.actor],
            "style_moods": [req.mood],
            "clothing_state": {},
            "location": "",
            "secondary_characters": {},
            "narration": "(raw mode — no narration)",
            "image": None,
        }

        if not req.skip_image:
            if runware_client is None:
                raise HTTPException(503, "Runware not connected")
            engine = StoryEngine(grok_client, runware_client)
            gen_args = {
                "image_prompt": simulated_prompt,
                "actors_present": [req.actor],
                "style_moods": [req.mood],
                "seed": req.seed,
            }
            try:
                if req.lora_overrides is not None:
                    manual_loras = [{"id": l["id"], "weight": l.get("weight", 0.8)} for l in req.lora_overrides]
                    img_result = await engine._generate_image(
                        gen_args, cast,
                        style_loras=manual_loras, extra_loras=[],
                        width=req.width, height=req.height, steps=req.steps,
                    )
                else:
                    img_result = await engine._generate_image(
                        gen_args, cast,
                        width=req.width, height=req.height, steps=req.steps,
                    )
                result["image"] = img_result
            except Exception as e:
                result["image_error"] = str(e)

        return result

    # ── Default: Grok-mediated simulation ──
    # Step 1: Build system prompt (same as in-game)
    player = {"name": "Player", "age": 28, "gender": "male", "preferences": "women"}
    system_prompt = build_system_prompt(
        player=player,
        cast=cast,
        setting_id=req.setting if req.setting in SETTINGS else "paris_2026",
        language=req.language,
    )

    # Step 2: Ask Grok to generate ONLY the tool call for this scene.
    # If a custom mood block is provided, tell Grok how to write a COMPLEMENTARY
    # image_prompt — not a duplication of the mood block.
    framing_directive = ""
    if req.custom_mood_block:
        framing_directive = (
            f"\n\n⚠️ MOOD BLOCK (auto-injected — DO NOT repeat its content in your image_prompt):\n"
            f"\"{req.custom_mood_block.strip()}\"\n\n"
            f"This mood block already defines the FRAMING, COMPOSITION, and POSE. "
            f"It will be automatically inserted at the START of the final prompt.\n\n"
            f"Your image_prompt should be SHORT and contain ONLY what the mood block does NOT cover:\n"
            f"- The actor's UNIQUE identity (hair color/length, eye color, skin tone, age) — "
            f"if not already specified in the mood\n"
            f"- The specific LOCATION/setting (e.g. 'Neo-Tokyo neon-lit street', 'Parisian salon')\n"
            f"- The LIGHTING style (e.g. 'warm candlelight', 'neon reflections')\n"
            f"- 1-2 atmospheric details visible in the cropped frame\n"
            f"- Photo style (lens, film stock)\n"
            f"⛔ DO NOT repeat: the framing, the shot type, body parts/poses already in the mood block, "
            f"or anything not visible in the cropped frame (clothing, hands, room details when it's a face crop).\n"
            f"Aim for ~30-60 words MAX in your image_prompt."
        )

    user_msg = (
        f"Generate a single scene image for the following scene description. "
        f"Use mood: {req.mood}. "
        f"Call generate_scene_image with image_index=0.\n\n"
        f"Scene: {req.scene_description}"
        f"{framing_directive}"
    )

    try:
        resp = await grok_client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            tools=[SCENE_IMAGE_TOOL],
            tool_choice={"type": "function", "function": {"name": "generate_scene_image"}},
            max_tokens=800,
            temperature=0.7,
        )
    except Exception as e:
        raise HTTPException(500, f"Grok error: {e}")

    # Parse the tool call
    msg = resp.choices[0].message
    if not msg.tool_calls:
        raise HTTPException(500, "Grok did not generate a tool call")

    tool_call = msg.tool_calls[0]
    try:
        args = _json.loads(tool_call.function.arguments)
    except Exception:
        raise HTTPException(500, f"Failed to parse tool call args: {tool_call.function.arguments}")

    simulated_prompt = args.get("image_prompt", "")
    actors_present = args.get("actors_present", [])
    style_moods = args.get("style_moods", [req.mood])

    # If a custom mood block was provided, PREPEND it to the prompt (Z-Image weighs
    # the start more heavily than the end). The actor trigger word stays first.
    if req.custom_mood_block:
        cmb = req.custom_mood_block.strip()
        if cmb and cmb[:40].lower() not in simulated_prompt.lower():
            # Try to insert after the actor trigger word (first comma-separated token)
            actor_data = ACTOR_REGISTRY.get(req.actor, {})
            trigger = actor_data.get("trigger_word", "")
            if trigger and simulated_prompt.startswith(trigger):
                # Insert mood block right after the trigger
                rest = simulated_prompt[len(trigger):].lstrip(", ")
                simulated_prompt = f"{trigger}, {cmb}, {rest}"
            else:
                simulated_prompt = f"{cmb}, {simulated_prompt}"

    result = {
        "simulated_prompt": simulated_prompt,
        "actors_present": actors_present,
        "style_moods": style_moods,
        "clothing_state": args.get("clothing_state", {}),
        "location": args.get("location_description", ""),
        "secondary_characters": args.get("secondary_characters", {}),
        "narration": msg.content or "",
        "image": None,
    }

    # Step 3: Generate the image (unless skip_image)
    if not req.skip_image:
        if runware_client is None:
            raise HTTPException(503, "Runware not connected")

        engine = StoryEngine(grok_client, runware_client)
        gen_args = {
            "image_prompt": simulated_prompt,
            "actors_present": actors_present,
            "style_moods": style_moods,
            "seed": req.seed,
        }

        try:
            if req.lora_overrides is not None:
                manual_loras = [{"id": l["id"], "weight": l.get("weight", 0.8)} for l in req.lora_overrides]
                img_result = await engine._generate_image(
                    gen_args, cast,
                    style_loras=manual_loras, extra_loras=[],
                    width=req.width, height=req.height, steps=req.steps,
                )
            else:
                img_result = await engine._generate_image(
                    gen_args, cast,
                    width=req.width, height=req.height, steps=req.steps,
                )
            result["image"] = img_result
        except Exception as e:
            result["image_error"] = str(e)

    return result


class ControlNetConfig(BaseModel):
    type: str = "openpose"  # openpose | canny | depth_midas | depth_zoe | depth_leres
    guide_image: str = ""   # URL of the reference image
    weight: float = 1.0
    start_step_pct: int = 0
    end_step_pct: int = 100
    control_mode: str = "balanced"  # balanced | prompt | controlnet
    include_hands_face: bool = True  # OpenPose only


class ManualGenRequest(BaseModel):
    prompt: str
    backend: str = "runware"  # "runware" | "fal"
    loras: List[dict] = []  # [{"id": "...", "weight": 0.8}]
    width: int = IMAGE_WIDTH
    height: int = IMAGE_HEIGHT
    steps: int = IMAGE_STEPS
    cfg: float = 0
    seed: Optional[int] = None
    controlnet: Optional[ControlNetConfig] = None


async def _generate_via_wavespeed(req: ManualGenRequest) -> dict:
    """Generate image via WaveSpeed AI — supports ControlNet + LoRA on Z-Image Turbo."""
    import aiohttp
    import time
    from config import WAVESPEEDAI_API_KEY

    if not WAVESPEEDAI_API_KEY:
        raise HTTPException(503, "WAVESPEEDAI_API_KEY not configured")

    base = "https://api.wavespeed.ai/api/v3"
    headers = {
        "Authorization": f"Bearer {WAVESPEEDAI_API_KEY}",
        "Content-Type": "application/json",
    }

    has_cn = req.controlnet and req.controlnet.guide_image
    has_lora = len(req.loras) > 0

    # Pick the right WaveSpeed endpoint
    if has_cn:
        endpoint = "wavespeed-ai/z-image-turbo/controlnet"
    elif has_lora:
        endpoint = "wavespeed-ai/z-image/turbo-lora"
    else:
        endpoint = "wavespeed-ai/z-image/turbo"

    args: dict = {
        "prompt": req.prompt,
        "size": f"{req.width}*{req.height}",
        "output_format": "webp",
        "enable_sync_mode": True,
    }
    if req.seed is not None and req.seed > 0:
        args["seed"] = req.seed

    # LoRAs — WaveSpeed uses path/scale
    if has_lora and not has_cn:  # LoRA endpoint (no CN+LoRA combo endpoint)
        args["loras"] = [{"path": l["id"], "scale": l.get("weight", 0.8)} for l in req.loras]

    # ControlNet — flat params
    if has_cn:
        cn = req.controlnet
        mode_map = {
            "openpose": "pose", "openpose_full": "pose", "openpose_face": "pose",
            "canny": "canny", "depth_midas": "depth", "depth_zoe": "depth", "depth_leres": "depth",
        }
        args["image"] = cn.guide_image
        args["mode"] = mode_map.get(cn.type, "pose")
        args["strength"] = cn.weight

    start = time.time()
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{base}/{endpoint}",
                headers=headers,
                json=args,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(resp.status, f"WaveSpeed error: {error_text}")
                result = await resp.json()
        except aiohttp.ClientError as e:
            raise HTTPException(500, f"WaveSpeed connection error: {e}")

    data = result.get("data", {})
    if data.get("status") == "failed":
        raise HTTPException(500, f"WaveSpeed generation failed: {data.get('error', 'unknown')}")

    outputs = data.get("outputs", [])
    if not outputs:
        raise HTTPException(500, "WaveSpeed returned no images")

    elapsed = round(time.time() - start, 2)
    inference_ms = data.get("timings", {}).get("inference", 0)

    return {
        "url": outputs[0],
        "cost": 0.005 if not has_cn else 0.012,
        "seed": data.get("seed") or req.seed,
        "elapsed": elapsed,
        "settings": {
            "width": req.width,
            "height": req.height,
            "steps": req.steps,
            "cfg": req.cfg,
            "loras": [{"id": l["id"], "weight": l.get("weight", 0.8)} for l in req.loras],
            "final_prompt": req.prompt,
            "controlnet": {"type": req.controlnet.type, "weight": req.controlnet.weight, "guide_image": bool(req.controlnet.guide_image)} if req.controlnet else None,
            "backend": "wavespeed",
            "endpoint": endpoint,
            "inference_ms": inference_ms,
        },
    }


async def _generate_via_runware(req: ManualGenRequest) -> dict:
    """Generate image via Runware — no ControlNet on Z-Image Turbo."""
    if runware_client is None:
        raise HTTPException(503, "Runware not connected")

    from runware import IImageInference, ILora, ISafety
    from config import IMAGE_MODEL, IMAGE_FORMAT
    import time

    lora_list = [ILora(model=l["id"], weight=l.get("weight", 0.8)) for l in req.loras] if req.loras else []

    start = time.time()
    try:
        images = await runware_client.imageInference(
            IImageInference(
                model=IMAGE_MODEL,
                positivePrompt=req.prompt,
                width=req.width,
                height=req.height,
                steps=req.steps,
                CFGScale=req.cfg,
                seed=req.seed or None,
                outputFormat=IMAGE_FORMAT,
                includeCost=True,
                lora=lora_list if lora_list else None,
                numberResults=1,
                safety=ISafety(checkContent=False),
            )
        )
    except Exception as e:
        raise HTTPException(500, str(e))

    elapsed = round(time.time() - start, 2)
    img = images[0]
    return {
        "url": img.imageURL,
        "cost": getattr(img, 'cost', None) or 0,
        "seed": getattr(img, 'seed', None),
        "elapsed": elapsed,
        "settings": {
            "width": req.width,
            "height": req.height,
            "steps": req.steps,
            "cfg": req.cfg,
            "loras": [{"id": l["id"], "weight": l.get("weight", 0.8)} for l in req.loras],
            "final_prompt": req.prompt,
            "controlnet": None,
            "backend": "runware",
        },
    }


@app.post("/api/playground/manual")
async def playground_manual(req: ManualGenRequest):
    """Direct image generation — full manual control. Supports runware or wavespeed backend."""
    if req.backend == "wavespeed":
        return await _generate_via_wavespeed(req)
    else:
        return await _generate_via_runware(req)


class PlaygroundVideoRequest(BaseModel):
    image_url: str          # URL of the source image
    prompt: str = ""        # Davinci prompt (if empty, auto-generate via Grok vision)
    narration: str = ""     # Story narration (for auto-prompt generation)
    seconds: int = 10
    seed: Optional[int] = None
    backend: str = "davinci"  # "davinci" | "pvideo"
    draft: bool = False
    audio: bool = True
    size: str = "720p"
    prompt_upsampling: bool = True


async def _playground_video_pvideo(req: PlaygroundVideoRequest) -> dict:
    """Generate video via Pruna P-Video on RunPod serverless."""
    import asyncio
    import time as _time
    import aiohttp
    import base64
    from config import runpod_Pruna_API

    if not runpod_Pruna_API:
        raise HTTPException(503, "RunPod P-Video API key not configured")

    start = _time.time()
    prompt = req.prompt.strip() or req.narration.strip() or "a person looking at the camera"

    # Submit job
    async with aiohttp.ClientSession() as session:
        payload = {
            "input": {
                "prompt": prompt,
                "image": req.image_url,
                "duration": req.seconds,
                "size": req.size,
                "fps": 24,
                "aspect_ratio": "9:16",
                "draft": req.draft,
                "save_audio": req.audio,
                "prompt_upsampling": req.prompt_upsampling,
                "enable_safety_checker": True,
                "seed": req.seed or 0,
            }
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {runpod_Pruna_API}",
        }

        async with session.post(
            "https://api.runpod.ai/v2/p-video/run",
            json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise HTTPException(resp.status, f"P-Video submit failed: {error}")
            data = await resp.json()
            job_id = data.get("id")
            if not job_id:
                raise HTTPException(500, f"P-Video: no job ID returned: {data}")

        # Poll for completion
        poll_url = f"https://api.runpod.ai/v2/p-video/status/{job_id}"
        deadline = _time.time() + 300  # 5 min max
        while _time.time() < deadline:
            await asyncio.sleep(3)
            async with session.get(poll_url, headers=headers) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                status = data.get("status")
                if status == "COMPLETED":
                    output = data.get("output", {})
                    video_url = output.get("video_url") or output.get("result", "")
                    if not video_url:
                        raise HTTPException(500, f"P-Video completed but no video URL: {output}")
                    # Download video bytes
                    async with session.get(video_url) as vid_resp:
                        video_bytes = await vid_resp.read()
                    elapsed = round(_time.time() - start, 1)
                    video_b64 = base64.b64encode(video_bytes).decode()
                    cost = output.get("cost", 0)
                    return {
                        "video_data": f"data:video/mp4;base64,{video_b64}",
                        "video_url": video_url,
                        "job_id": job_id,
                        "generation_time": elapsed,
                        "elapsed": elapsed,
                        "cost": cost,
                        "prompt_used": prompt,
                        "simulated": False,
                        "backend": "pvideo",
                    }
                elif status == "FAILED":
                    error = data.get("error", "unknown")
                    raise HTTPException(500, f"P-Video failed: {error}")

        raise HTTPException(504, f"P-Video timeout after 300s (job {job_id})")


@app.post("/api/playground/video")
async def playground_video(req: PlaygroundVideoRequest):
    """Generate video from image. Supports davinci (MagiHuman) or pvideo (Pruna P-Video) backend."""
    if req.backend == "pvideo":
        return await _playground_video_pvideo(req)

    # Davinci path
    import time as _time
    from davinci import generate_scene_video, build_davinci_prompt, DAVINCI_ENABLED
    import base64

    if not DAVINCI_ENABLED:
        raise HTTPException(503, "Davinci video generation is not configured")

    if not req.image_url:
        raise HTTPException(400, "image_url is required")

    start = _time.time()

    # Build or use provided prompt
    davinci_prompt = req.prompt.strip()
    if not davinci_prompt:
        davinci_prompt = await build_davinci_prompt(
            image_prompt="",
            narration=req.narration or "(no narration provided)",
            character_name="a young woman",
            language="French",
            image_url=req.image_url,
        )

    # Generate video
    try:
        result = await generate_scene_video(
            image_url=req.image_url,
            davinci_prompt=davinci_prompt,
            seconds=req.seconds,
            seed=req.seed,
        )
    except Exception as e:
        raise HTTPException(500, f"Video generation failed: {e}")

    elapsed = round(_time.time() - start, 1)
    video_bytes = result.get("video_bytes", b"")
    video_b64 = base64.b64encode(video_bytes).decode() if video_bytes else ""

    return {
        "video_data": f"data:video/mp4;base64,{video_b64}" if video_b64 else None,
        "video_url": result.get("video_url", ""),
        "job_id": result.get("job_id", ""),
        "generation_time": result.get("generation_time", elapsed),
        "elapsed": elapsed,
        "prompt_used": davinci_prompt,
        "simulated": result.get("simulated", False),
    }
