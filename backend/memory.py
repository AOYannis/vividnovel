"""Mem0 narrative memory layer.

Supplements (does NOT replace) the existing ConsistencyTracker and conversation_history.
Extracts and recalls narrative facts across sequences to enrich the system prompt
without inflating the conversation history token count.

If MEM0_API_KEY is not set, all operations are no-ops.
"""
import os
import hashlib
import traceback

MEM0_API_KEY = os.environ.get("MEM0_API_KEY", "")
MEM0_ENABLED = bool(MEM0_API_KEY)

_client = None

if MEM0_ENABLED:
    try:
        from mem0 import MemoryClient
        _client = MemoryClient(api_key=MEM0_API_KEY)
        print("[ok] Mem0 connected")
    except Exception as e:
        print(f"[!!] Mem0 connection failed: {e} — running without memory")
        _client = None
        MEM0_ENABLED = False


def _user_session_id(user_id: str, session_id: str) -> str:
    """Combine user + session into a short clean Mem0 user_id."""
    raw = f"{user_id}:{session_id}"
    return "gb" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _persistent_user_id(user_id: str, setting: str = "") -> str:
    """User + setting scope for cross-session persistent memory.

    Same user + same setting = shared memories across sessions.
    Different setting = separate memory namespace (no cross-contamination).
    """
    raw = f"{user_id}:{setting}" if setting else user_id
    return "gbp" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _character_memory_id(session_id: str, character_code: str) -> str:
    """Per-character memory scope within a session."""
    raw = f"{session_id}:char:{character_code}"
    return "gbc" + hashlib.md5(raw.encode()).hexdigest()[:12]


def store_sequence_narrative(
    session_id: str,
    user_id: str,
    sequence_number: int,
    narration_text: str,
    choice_made: str | None,
    setting_label: str = "",
    characters: list[str] | None = None,
) -> None:
    """Extract and store narrative facts from a completed sequence.

    Stores both session-level facts AND per-character facts.
    Called in a thread executor (fire-and-forget).
    """
    if not _client:
        return
    try:
        scoped_uid = _user_session_id(user_id, session_id)

        # Session-level facts (general narrative continuity)
        facts = []
        if setting_label:
            facts.append(f"The story takes place in {setting_label}.")
        if narration_text:
            facts.append(f"In sequence {sequence_number + 1}, this happened: {narration_text[:1500]}")
        if choice_made:
            facts.append(f"The player decided to: {choice_made}")

        for fact in facts:
            _client.add(
                messages=[{"role": "user", "content": fact}],
                user_id=scoped_uid,
            )

        # Per-character facts — store narration in each character's memory
        # so they "remember" what happened when they were present
        if characters and narration_text:
            for char_code in characters:
                char_uid = _character_memory_id(session_id, char_code)
                _client.add(
                    messages=[{"role": "user", "content": (
                        f"During a scene with the player, this happened: "
                        f"{narration_text[:800]}"
                    )}],
                    user_id=char_uid,
                )
                if choice_made:
                    _client.add(
                        messages=[{"role": "user", "content": (
                            f"The player decided to: {choice_made}"
                        )}],
                        user_id=char_uid,
                    )
    except Exception:
        traceback.print_exc()


def store_character_chat(
    session_id: str,
    character_code: str,
    player_message: str,
    narrator_response: str,
) -> None:
    """Store a scene chat exchange in a character's memory.

    This makes the character "remember" what the player said/did.
    """
    if not _client:
        return
    try:
        char_uid = _character_memory_id(session_id, character_code)
        _client.add(
            messages=[{"role": "user", "content": (
                f"The player said/did: \"{player_message}\". "
                f"What happened: {narrator_response[:500]}"
            )}],
            user_id=char_uid,
        )
    except Exception:
        traceback.print_exc()


def recall_character_memory(
    session_id: str,
    character_code: str,
    limit: int = 10,
) -> str:
    """Recall what a character remembers about interactions with the player.

    Returns formatted string, or empty string.
    """
    if not _client:
        return ""
    try:
        char_uid = _character_memory_id(session_id, character_code)
        memories = _client.search(
            query="what does the character know about the player, conversations, revelations, shared moments",
            filters={"user_id": char_uid},
            limit=limit,
        )
        results = memories.get("results", []) if isinstance(memories, dict) else []
        if not results:
            all_mem = _client.get_all(filters={"user_id": char_uid})
            results = all_mem.get("results", []) if isinstance(all_mem, dict) else []
        if not results:
            return ""
        facts = [f"- {m['memory']}" for m in results if m.get("memory")]
        if not facts:
            return ""
        return "\n".join(facts)
    except Exception:
        traceback.print_exc()
        return ""


def recall_narrative_context(
    session_id: str,
    user_id: str,
    query: str = "story events, character names, relationships, key moments, clothing, location",
    limit: int = 20,
) -> str:
    """Recall narrative memories for this session to inject into the system prompt.

    Returns a formatted string of remembered facts, or empty string.
    Synchronous — called before streaming starts.
    """
    if not _client:
        return ""
    try:
        scoped_uid = _user_session_id(user_id, session_id)

        # Try search first (semantic relevance)
        memories = _client.search(
            query=query,
            filters={"user_id": scoped_uid},
            limit=limit,
        )

        results = memories.get("results", []) if isinstance(memories, dict) else []

        # Fallback to get_all if search returns nothing
        if not results:
            all_mem = _client.get_all(filters={"user_id": scoped_uid})
            results = all_mem.get("results", []) if isinstance(all_mem, dict) else []

        if not results:
            return ""

        facts = []
        for mem in results:
            text = mem.get("memory", "")
            if text:
                facts.append(f"- {text}")

        if not facts:
            return ""

        return (
            "## Mémoire narrative (faits retenus des séquences précédentes)\n"
            "Ces faits ont été automatiquement extraits. Utilise-les pour la cohérence "
            "narrative mais ne les répète pas textuellement au joueur.\n\n"
            + "\n".join(facts)
        )
    except Exception:
        traceback.print_exc()
        return ""


# ─── Cross-session persistent memory ─────────────────────────


def store_persistent_memory(
    user_id: str,
    cast_codenames: list[str],
    narration_text: str,
    choice_made: str | None,
    setting_label: str = "",
    setting_id: str = "",
) -> None:
    """Store cross-session facts about character relationships and player patterns.

    Scoped to user + setting, so different worlds have separate memory.
    Called in a thread executor (fire-and-forget).
    """
    if not _client:
        return
    try:
        uid = _persistent_user_id(user_id, setting_id)

        facts = []

        # Character encounter context — Mem0 will extract relationship facts
        if cast_codenames and narration_text:
            chars = ", ".join(cast_codenames)
            facts.append(
                f"In a story set in {setting_label or 'an unknown setting'}, "
                f"the player encountered characters: {chars}. "
                f"Here is what happened: {narration_text[:800]}"
            )

        # Player decision pattern
        if choice_made:
            facts.append(
                f"When given a choice, the player decided to: {choice_made}"
            )

        for fact in facts:
            _client.add(
                messages=[{"role": "user", "content": fact}],
                user_id=uid,
            )
    except Exception:
        traceback.print_exc()


def recall_persistent_memory(
    user_id: str,
    cast_codenames: list[str] | None = None,
    setting_id: str = "",
    limit: int = 15,
) -> str:
    """Recall cross-session memories about past encounters.

    Scoped to user + setting — only recalls memories from the same world.
    Returns formatted string for system prompt injection, or empty string.
    Synchronous — called before streaming starts.
    """
    if not _client:
        return ""
    try:
        uid = _persistent_user_id(user_id, setting_id)

        # Build query focusing on characters in current cast
        if cast_codenames:
            char_names = ", ".join(cast_codenames)
            query = (
                f"past encounters with {char_names}, relationship history, "
                f"player personality, recurring themes, emotional moments"
            )
        else:
            query = (
                "past story encounters, character relationships, "
                "player personality, recurring themes"
            )

        memories = _client.search(
            query=query,
            filters={"user_id": uid},
            limit=limit,
        )

        results = memories.get("results", []) if isinstance(memories, dict) else []

        # Fallback to get_all if search returns nothing
        if not results:
            all_mem = _client.get_all(filters={"user_id": uid})
            results = all_mem.get("results", []) if isinstance(all_mem, dict) else []

        if not results:
            return ""

        facts = []
        for mem in results:
            text = mem.get("memory", "")
            if text:
                facts.append(f"- {text}")

        if not facts:
            return ""

        return (
            "## Mémoire persistante (histoires précédentes)\n"
            "Ces souvenirs viennent de parties PRÉCÉDENTES du joueur. "
            "Le joueur a déjà vécu ces moments dans d'autres histoires. "
            "Utilise-les SUBTILEMENT pour créer des échos, des déjà-vu, "
            "des retrouvailles — comme si les personnages et le joueur "
            "partageaient un passé mystérieux.\n"
            "NE PAS réciter ces faits. Les MONTRER par des détails, "
            "des réactions, des regards qui en disent long.\n\n"
            + "\n".join(facts)
        )
    except Exception:
        traceback.print_exc()
        return ""


# ─── Memory cleanup ──────────────────────────────────────────


def delete_session_memories(user_id: str, session_id: str) -> None:
    """Delete all Mem0 memories for a specific session."""
    if not _client:
        return
    try:
        uid = _user_session_id(user_id, session_id)
        _client.delete_all(user_id=uid)
    except Exception:
        traceback.print_exc()


def delete_persistent_memories(user_id: str, setting_id: str = "") -> None:
    """Delete all persistent (cross-session) memories for a user + setting."""
    if not _client:
        return
    try:
        uid = _persistent_user_id(user_id, setting_id)
        _client.delete_all(user_id=uid)
    except Exception:
        traceback.print_exc()


def delete_all_user_memories(user_id: str, setting_ids: list[str] | None = None) -> int:
    """Delete ALL Mem0 memories for a user across given settings.

    Returns number of namespaces cleared.
    """
    if not _client:
        return 0
    cleared = 0
    try:
        for sid in (setting_ids or [""]):
            uid = _persistent_user_id(user_id, sid)
            _client.delete_all(user_id=uid)
            cleared += 1
    except Exception:
        traceback.print_exc()
    return cleared
