"""Supabase database client for persistence.

Uses the service_role key to bypass RLS (backend writes on behalf of users).
If not configured, all operations are no-ops.
"""
import os
import asyncio
import traceback
from typing import Optional

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DB_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

_client = None

if DB_ENABLED:
    from supabase import create_client
    _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_db():
    """Get the Supabase client. Returns None if not configured."""
    return _client


def fire_and_forget(coro):
    """Run a coroutine in the background without blocking. Log errors."""
    async def wrapper():
        try:
            await coro
        except Exception:
            traceback.print_exc()
    asyncio.create_task(wrapper())


async def save_session(session) -> None:
    """Persist a GameSession to the database."""
    if not _client:
        return
    try:
        # Pack the slice-of-life world state + character agent states into
        # video_settings under private keys. TODO: promote to dedicated columns
        # once the Supabase schema can be migrated.
        video_settings = dict(session.video_settings or {})
        if getattr(session, "world", None):
            video_settings["_world_state"] = session.world.as_dict()
        char_states = getattr(session, "character_states", None) or {}
        if char_states:
            video_settings["_character_states"] = {
                code: state.as_dict() for code, state in char_states.items()
            }
        known_wh = getattr(session, "known_whereabouts", None) or []
        if known_wh:
            video_settings["_known_whereabouts"] = list(known_wh)
        recent_missed = getattr(session, "recent_missed_rendezvous", None) or []
        if recent_missed:
            video_settings["_recent_missed_rendezvous"] = list(recent_missed)
        _client.table("game_sessions").upsert({
            "id": session.id,
            "user_id": session.user_id,
            "player": session.player,
            "setting": session.setting,
            "cast_config": session.cast,
            "custom_setting_text": getattr(session, "custom_setting_text", ""),
            "system_prompt_override": session.system_prompt_override,
            "sequence_number": session.sequence_number,
            "conversation_history": session.conversation_history,
            "consistency_state": session.consistency.to_dict(),
            "total_costs": session.total_costs,
            "style_loras": session.style_loras,
            "extra_loras": session.extra_loras,
            "video_settings": video_settings,
        }).execute()
    except Exception:
        traceback.print_exc()


async def save_sequence(session_id: str, seq_number: int, narration_segments: list,
                        choices: list, choice_made: dict | None, costs: dict | None,
                        images_data: list, video_data: dict | None) -> None:
    """Persist a completed sequence with its images and video."""
    if not _client:
        return
    try:
        # Upsert sequence
        seq_result = _client.table("sequences").upsert({
            "session_id": session_id,
            "sequence_number": seq_number,
            "narration_segments": narration_segments,
            "choices_offered": choices,
            "choice_made": choice_made,
            "costs": costs,
        }, on_conflict="session_id,sequence_number").execute()

        seq_id = seq_result.data[0]["id"] if seq_result.data else None
        if not seq_id:
            return

        # Upsert images
        for img in images_data:
            if not img.get("url"):
                continue
            _client.table("images").upsert({
                "sequence_id": seq_id,
                "image_index": img["index"],
                "url": img.get("url"),
                "prompt": img.get("prompt"),
                "actors_present": img.get("actors", []),
                "cost": img.get("cost", 0),
                "seed": img.get("seed"),
                "generation_time": img.get("generation_time"),
                "gen_settings": img.get("settings"),
            }, on_conflict="sequence_id,image_index").execute()

        # Upsert video
        if video_data and video_data.get("url"):
            _client.table("videos").upsert({
                "sequence_id": seq_id,
                "url": video_data["url"],
                "prompt": video_data.get("prompt"),
                "cost": video_data.get("cost", 0),
                "generation_time": video_data.get("generation_time"),
            }, on_conflict="sequence_id").execute()

    except Exception:
        traceback.print_exc()


async def save_scene_video(session_id: str, seq_number: int, image_index: int, video_url: str) -> None:
    """Persist a per-scene video URL to the image row."""
    if not _client or not video_url:
        return
    try:
        # Find the sequence
        seq_result = _client.table("sequences") \
            .select("id") \
            .eq("session_id", session_id) \
            .eq("sequence_number", seq_number) \
            .execute()
        if not seq_result.data:
            return
        seq_id = seq_result.data[0]["id"]
        # Update the image with video URL
        _client.table("images") \
            .update({"scene_video_url": video_url}) \
            .eq("sequence_id", seq_id) \
            .eq("image_index", image_index) \
            .execute()
    except Exception:
        traceback.print_exc()


async def add_scene_video_cost(session_id: str, cost: float) -> None:
    """Increment video_cost in the session's total_costs."""
    if not _client or cost <= 0:
        return
    try:
        result = _client.table("game_sessions") \
            .select("total_costs") \
            .eq("id", session_id) \
            .execute()
        if not result.data:
            return
        total_costs = result.data[0].get("total_costs", {})
        total_costs["video_cost"] = (total_costs.get("video_cost", 0) or 0) + cost
        total_costs["total"] = (total_costs.get("total", 0) or 0) + cost
        _client.table("game_sessions") \
            .update({"total_costs": total_costs}) \
            .eq("id", session_id) \
            .execute()
    except Exception:
        traceback.print_exc()


async def update_sequence_choice(session_id: str, seq_number: int, choice_made: dict) -> None:
    """Update the choice_made field on a completed sequence."""
    if not _client:
        return
    try:
        _client.table("sequences") \
            .update({"choice_made": choice_made}) \
            .eq("session_id", session_id) \
            .eq("sequence_number", seq_number) \
            .execute()
    except Exception:
        traceback.print_exc()


async def list_user_sessions(user_id: str) -> list:
    """List all sessions for a user, including a thumbnail (latest image url)."""
    if not _client:
        return []
    try:
        result = _client.table("game_sessions") \
            .select("id, player, setting, cast_config, sequence_number, total_costs, status, created_at, updated_at") \
            .eq("user_id", user_id) \
            .order("updated_at", desc=True) \
            .execute()
        sessions = result.data or []
        # Fetch one thumbnail per session — latest image of latest sequence
        for s in sessions:
            try:
                seq_res = _client.table("sequences") \
                    .select("id") \
                    .eq("session_id", s["id"]) \
                    .order("sequence_number", desc=True) \
                    .limit(1) \
                    .execute()
                if seq_res.data:
                    seq_id = seq_res.data[0]["id"]
                    img_res = _client.table("images") \
                        .select("url") \
                        .eq("sequence_id", seq_id) \
                        .not_.is_("url", "null") \
                        .order("image_index", desc=True) \
                        .limit(1) \
                        .execute()
                    if img_res.data and img_res.data[0].get("url"):
                        s["thumbnail_url"] = img_res.data[0]["url"]
            except Exception:
                pass  # thumbnail is optional
        return sessions
    except Exception:
        traceback.print_exc()
        return []


async def load_session_data(session_id: str, user_id: str) -> Optional[dict]:
    """Load full session data from DB."""
    if not _client:
        return None
    try:
        result = _client.table("game_sessions") \
            .select("*") \
            .eq("id", session_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        return result.data
    except Exception:
        traceback.print_exc()
        return None


async def load_sequence_history(session_id: str) -> list:
    """Load all sequences with images for a session (for replay)."""
    if not _client:
        return []
    try:
        result = _client.table("sequences") \
            .select("*, images(*), videos(*)") \
            .eq("session_id", session_id) \
            .order("sequence_number") \
            .execute()
        return result.data or []
    except Exception:
        traceback.print_exc()
        return []


async def admin_get_all_costs() -> dict:
    """Aggregate costs across all users (admin only)."""
    if not _client:
        return {}
    try:
        result = _client.table("game_sessions") \
            .select("user_id, player, total_costs, sequence_number, created_at, updated_at") \
            .order("updated_at", desc=True) \
            .execute()

        rows = result.data or []
        users: dict = {}
        grand_total = 0.0
        total_sessions = 0
        total_sequences = 0

        for row in rows:
            uid = row["user_id"]
            costs = row.get("total_costs") or {}
            session_total = costs.get("total", 0) or 0
            seq_count = row.get("sequence_number", 0)

            if uid not in users:
                users[uid] = {
                    "user_id": uid,
                    "sessions": [],
                    "total_cost": 0,
                    "total_sequences": 0,
                    "session_count": 0,
                }

            users[uid]["sessions"].append({
                "player_name": (row.get("player") or {}).get("name", "?"),
                "cost": session_total,
                "sequences": seq_count,
                "updated_at": row.get("updated_at"),
            })
            users[uid]["total_cost"] += session_total
            users[uid]["total_sequences"] += seq_count
            users[uid]["session_count"] += 1
            grand_total += session_total
            total_sessions += 1
            total_sequences += seq_count

        return {
            "grand_total": round(grand_total, 4),
            "total_sessions": total_sessions,
            "total_sequences": total_sequences,
            "total_users": len(users),
            "users": list(users.values()),
        }
    except Exception:
        traceback.print_exc()
        return {}


async def delete_session(session_id: str, user_id: str) -> bool:
    """Delete a session (cascades to sequences, images, videos)."""
    if not _client:
        return False
    try:
        _client.table("game_sessions") \
            .delete() \
            .eq("id", session_id) \
            .eq("user_id", user_id) \
            .execute()
        return True
    except Exception:
        traceback.print_exc()
        return False
