"""Slice-of-life world state — Phase 1.

The 'world' tracks where the player is in physical (location) and temporal
(day + slot) space. Sequences don't auto-advance time anymore; time only moves
when the player explicitly chooses to (via the map / 'go elsewhere' choice).
Most consecutive sequences stay in the same location-slot, preserving the
storyboard-within-an-evening rhythm.

Phase 1 scope: scaffold + per-setting location catalog + manual location
switching that advances time by one slot. Schedules / presence resolver /
agent ticks come in later phases.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict


# Time slots in order — used to compute next-slot transitions
SLOTS: tuple[str, ...] = ("morning", "afternoon", "evening", "night")

# Cap on per-character `recent_events` log. Keeps the prompt + persistence small
# while giving the narrator enough context to reference recent off-screen life.
MAX_RECENT_EVENTS: int = 7
SLOT_LABELS_FR = {
    "morning": "matin",
    "afternoon": "après-midi",
    "evening": "soir",
    "night": "nuit",
}
SLOT_LABELS_EN = {
    "morning": "morning",
    "afternoon": "afternoon",
    "evening": "evening",
    "night": "night",
}


@dataclass
class Location:
    id: str          # stable code, used in URLs and prompts
    name: str        # displayed to the player
    type: str        # cafe | bar | home | work | gym | park | club | other
    description: str = ""  # one-liner for the agent's context


@dataclass
class WorldState:
    day: int = 1                              # 1-indexed day counter
    slot: str = "evening"                     # current time slot
    locations: list[Location] = field(default_factory=list)
    current_location: str = ""                # location.id; "" before first move
    history: list[dict] = field(default_factory=list)  # last N location-slot visits
    map_background_url: str = ""              # one-shot Z-Image illustration of the world map

    def as_dict(self) -> dict:
        return {
            "day": self.day,
            "slot": self.slot,
            "locations": [asdict(loc) for loc in self.locations],
            "current_location": self.current_location,
            "history": list(self.history)[-20:],  # cap at 20 for prompt size
            "map_background_url": self.map_background_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldState":
        return cls(
            day=int(data.get("day", 1)),
            slot=str(data.get("slot", "evening")),
            locations=[Location(**loc) for loc in data.get("locations", [])],
            current_location=str(data.get("current_location", "")),
            history=list(data.get("history", [])),
            map_background_url=str(data.get("map_background_url", "")),
        )

    def location_by_id(self, loc_id: str) -> Location | None:
        return next((loc for loc in self.locations if loc.id == loc_id), None)


# ─── Per-setting location catalogues ────────────────────────────────────────
# These are starter sets. Phase 2 will let the user pick / customise.

_PARIS_2026_LOCATIONS = [
    Location("home", "Ton appart, 11ᵉ", "home", "Petit appartement parisien, balcon, vue sur les toits"),
    Location("cafe_du_coin", "Le Petit Marais", "cafe", "Café-bar du Marais, terrasse, clientèle d'habitués"),
    Location("bar_marais", "Le Mary Celeste", "bar", "Bar à cocktails branché, ambiance feutrée"),
    Location("yoga", "Studio Vinyasa", "gym", "Studio de yoga lumineux, baies vitrées"),
    Location("buttes_chaumont", "Buttes-Chaumont", "park", "Parc vallonné, lac, ponts suspendus"),
    Location("work", "Boulot", "work", "Espace de coworking dans le 11ᵉ"),
]

_PARIS_1800_LOCATIONS = [
    Location("home", "Ton appartement, rue de Sèvres", "home", "Logement bourgeois, mansardes, cheminée"),
    Location("salon", "Salon littéraire", "salon", "Salon mondain où se croise l'élite parisienne"),
    Location("opera", "Opéra Le Peletier", "club", "Loges, foyer doré, intrigues nocturnes"),
    Location("jardin", "Jardin du Luxembourg", "park", "Allées gravillonnées, statues, parasols"),
    Location("cafe_procope", "Café Procope", "cafe", "Café littéraire, intellectuels et révolutionnaires"),
    Location("atelier", "Ton atelier", "work", "Atelier d'artiste/écrivain, table d'écriture, esquisses"),
]

_NEO_2100_LOCATIONS = [
    Location("home", "Capsule, niveau 47", "home", "Studio compact dans une mégastructure, vue holographique"),
    Location("club_neon", "Neon Drift", "club", "Club synthwave, hologrammes, danseurs augmentés"),
    Location("noodle_bar", "Mama Wei's", "cafe", "Bar à nouilles tenu par une vieille dame, rétro-futur"),
    Location("hangar_42", "Hangar 42", "bar", "Bar underground dans un ancien hangar, cyberpunks"),
    Location("park_solar", "Parc solaire", "park", "Parc en hauteur sous une verrière, jardin botanique"),
    Location("work", "Studio de design augmenté", "work", "Espace de travail VR/AR"),
]

# Setting-agnostic placeholder locations used when Grok world-generation fails
# AND the setting is "custom" / unknown. Better than dumping a bespoke-prompt
# user into a Parisian apartment they didn't ask for. Names are intentionally
# generic so the narrator can re-skin them via the custom_setting_text in the
# system prompt without contradiction.
_GENERIC_LOCATIONS = [
    Location("home", "Your place", "home", "The room or space the player retreats to"),
    Location("hub", "The main gathering area", "other", "Where most of the cast tends to congregate"),
    Location("private_room", "A quieter side room", "other", "Calmer spot, used for private conversations"),
    Location("outside", "Outside / grounds", "park", "Open-air space adjacent to the main setting"),
    Location("hidden_corner", "A discreet corner", "other", "Off-the-beaten-path spot, ideal for secrets"),
    Location("threshold", "Entry / threshold", "other", "Where people arrive and leave"),
]

_DEFAULT_LOCATIONS = _GENERIC_LOCATIONS  # fallback for unknown / custom settings

LOCATION_CATALOG: dict[str, list[Location]] = {
    "paris_2026": _PARIS_2026_LOCATIONS,
    "paris_1800": _PARIS_1800_LOCATIONS,
    "neo_2100": _NEO_2100_LOCATIONS,
    "custom": _GENERIC_LOCATIONS,  # explicit so custom-setting users never get Paris
}


def default_world_for_setting(setting_id: str) -> WorldState:
    """Build a fresh WorldState for a given setting. Player starts at 'home'
    on day 1 evening (a common slice-of-life starting point — coming back from work)."""
    catalog = LOCATION_CATALOG.get(setting_id, _DEFAULT_LOCATIONS)
    locations = [Location(**asdict(loc)) for loc in catalog]  # deep copy
    return WorldState(
        day=1,
        slot="evening",
        locations=locations,
        current_location="home",
        history=[{"day": 1, "slot": "evening", "location": "home"}],
    )


def advance_time(state: WorldState) -> None:
    """Advance to the next slot; wrap to next day after night."""
    try:
        i = SLOTS.index(state.slot)
    except ValueError:
        i = 2  # default to evening if slot got corrupted
    if i == len(SLOTS) - 1:  # night → morning of next day
        state.slot = SLOTS[0]
        state.day += 1
    else:
        state.slot = SLOTS[i + 1]


def set_location(state: WorldState, location_id: str, advance: bool = True) -> None:
    """Switch current location. By default also advances time by one slot
    (going somewhere else takes time). Pass advance=False for instant teleport
    cases (debug, edge UX)."""
    if not state.location_by_id(location_id):
        raise ValueError(f"Unknown location: {location_id}")
    if advance:
        advance_time(state)
    state.current_location = location_id
    state.history.append({
        "day": state.day,
        "slot": state.slot,
        "location": location_id,
    })


def location_label(state: WorldState, lang: str = "fr") -> str:
    """Render '[Day N, slot] @ [location name]' for the prompt or UI."""
    loc = state.location_by_id(state.current_location)
    name = loc.name if loc else state.current_location or "?"
    slot_label = (SLOT_LABELS_FR if lang == "fr" else SLOT_LABELS_EN).get(state.slot, state.slot)
    if lang == "fr":
        return f"Jour {state.day} · {slot_label} · {name}"
    return f"Day {state.day} · {slot_label} · {name}"


# ─── Phase 2: per-character agent state + presence resolver ────────────────

import hashlib as _hashlib
from dataclasses import dataclass, field as _field


def weekday_kind(day: int) -> str:
    """Map day → 'weekday' (Mon-Fri) or 'weekend' (Sat-Sun).
    Day 1 is treated as a Monday; cycle every 7."""
    return "weekday" if (day - 1) % 7 < 5 else "weekend"


def stable_choice(seed_parts: tuple, candidates: list[str]) -> str | None:
    """Pick one candidate deterministically from seed_parts. Same seed → same
    choice. Used so a character's "free slot" choice varies day-to-day but
    re-renders identically when the same prompt is rebuilt mid-sequence."""
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    h = _hashlib.md5(":".join(str(s) for s in seed_parts).encode()).hexdigest()
    idx = int(h[:8], 16) % len(candidates)
    return candidates[idx]


@dataclass
class CharacterState:
    """Per-character agent state. Generated once at game start by agent.py.
    Schedules are keyed as '<weekday|weekend>_<slot>' → 'loc_id' or 'a|b|c' or 'free'.
    'free' means the character has no fixed plan — they may or may not appear
    anywhere; the resolver treats them as absent unless an override applies."""
    code: str                            # actor codename (matches ACTOR_REGISTRY)
    personality: str = ""                # 1-line trait summary
    job: str = ""                        # role / occupation
    schedule: dict[str, str] = _field(default_factory=dict)
    overrides: dict[str, str] = _field(default_factory=dict)  # "<day>_<slot>" → loc_id
    today_mood: str = ""                 # populated by daily tick
    intentions_toward_player: str = ""   # populated by daily tick
    # Off-screen life log: list of {day, text} entries. Most-recent first or
    # last? We append in chronological order (oldest first) and trim from the
    # head when len > MAX_RECENT_EVENTS. Use `recent_event` (singular) as a
    # convenience accessor for the latest entry — kept for back-compat with
    # older serialized state and the prompt's `Hier (off-screen)` line.
    recent_events: list[dict] = _field(default_factory=list)
    last_tick_day: int = 0               # last world.day the daily_tick ran for this char (avoid re-firing on same day)
    # How quickly this character opens up. Drives the narrative reaction cues
    # injected into the relationships block — does NOT change LoRA gating.
    # Valid values: "reserved" | "normal" | "wild". Defaults to "normal".
    temperament: str = "normal"

    @property
    def recent_event(self) -> str:
        """Back-compat: return the most recent event's text (or empty string)."""
        if not self.recent_events:
            return ""
        return str(self.recent_events[-1].get("text", "") or "")

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "personality": self.personality,
            "job": self.job,
            "schedule": dict(self.schedule),
            "overrides": dict(self.overrides),
            "today_mood": self.today_mood,
            "intentions_toward_player": self.intentions_toward_player,
            "recent_events": list(self.recent_events),
            "last_tick_day": self.last_tick_day,
            "temperament": self.temperament,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterState":
        _temp = str(data.get("temperament", "normal")).strip().lower()
        if _temp not in ("reserved", "normal", "wild"):
            _temp = "normal"
        try:
            _last_tick = int(data.get("last_tick_day", 0) or 0)
        except (TypeError, ValueError):
            _last_tick = 0
        # Migration: older sessions stored a single `recent_event: str`. Promote
        # it to a one-entry list so the new accessor works.
        events_raw = data.get("recent_events")
        events: list[dict] = []
        if isinstance(events_raw, list):
            for e in events_raw:
                if isinstance(e, dict) and (e.get("text") or "").strip():
                    try:
                        events.append({"day": int(e.get("day", 0) or 0), "text": str(e["text"])[:240]})
                    except (TypeError, ValueError):
                        continue
        elif "recent_event" in data and (data.get("recent_event") or "").strip():
            events.append({"day": _last_tick, "text": str(data["recent_event"])[:240]})
        return cls(
            code=str(data.get("code", "")),
            personality=str(data.get("personality", "")),
            job=str(data.get("job", "")),
            schedule=dict(data.get("schedule", {})),
            overrides=dict(data.get("overrides", {})),
            today_mood=str(data.get("today_mood", "")),
            intentions_toward_player=str(data.get("intentions_toward_player", "")),
            recent_events=events,
            last_tick_day=_last_tick,
            temperament=_temp,
        )

    def schedule_for(self, day: int, slot: str) -> str:
        """Resolve where this character is on a given day-slot.
        Returns '' if no info; 'loc_id' if pinned; 'a|b|c' if multi-candidate."""
        # 1. Explicit override (rendez-vous, announced presence) wins
        ov_key = f"{day}_{slot}"
        if ov_key in self.overrides:
            return self.overrides[ov_key]
        # 2. Weekly template
        kind = weekday_kind(day)
        return self.schedule.get(f"{kind}_{slot}", "")


def who_is_at(
    location_id: str,
    day: int,
    slot: str,
    character_states: dict[str, CharacterState],
) -> list[str]:
    """Return codenames of characters whose schedule places them at this
    location-slot. Pipe-separated multi-candidates resolve via stable_choice
    (same seed → same character, but varies day-to-day).
    'free' / empty schedule entries → character is NOT present (they may be
    anywhere; we don't roll for them by default)."""
    present: list[str] = []
    for code, state in character_states.items():
        spec = state.schedule_for(day, slot)
        if not spec or spec == "free":
            continue
        candidates = [s.strip() for s in spec.split("|") if s.strip()]
        chosen = stable_choice((code, day, slot), candidates)
        if chosen == location_id:
            present.append(code)
    return present


def all_known_whereabouts(
    day: int,
    slot: str,
    character_states: dict[str, CharacterState],
) -> dict[str, str]:
    """Map of {char_code → location_id} for all characters whose schedule
    places them somewhere this slot (regardless of where the player is).
    Used by the map UI to surface 'X is at Y' hints."""
    out: dict[str, str] = {}
    for code, state in character_states.items():
        spec = state.schedule_for(day, slot)
        if not spec or spec == "free":
            continue
        candidates = [s.strip() for s in spec.split("|") if s.strip()]
        chosen = stable_choice((code, day, slot), candidates)
        if chosen:
            out[code] = chosen
    return out


def set_rendezvous(state: CharacterState, day: int, slot: str, location_id: str) -> None:
    """Pin a character to a specific location-slot (rendez-vous accepted)."""
    state.overrides[f"{day}_{slot}"] = location_id


# ─── Rendez-vous lifecycle helpers (Feature 1) ──────────────────────────────

def slot_distance(from_day: int, from_slot: str, to_day: int, to_slot: str) -> int:
    """Number of slots from (from_day, from_slot) to (to_day, to_slot).
    Negative if the target is in the past, 0 if same, positive if future.
    Assumes 4 slots per day (morning/afternoon/evening/night)."""
    try:
        f = SLOTS.index(from_slot)
    except ValueError:
        f = 0
    try:
        t = SLOTS.index(to_slot)
    except ValueError:
        t = 0
    return (to_day - from_day) * len(SLOTS) + (t - f)


def rendezvous_status(world: WorldState, rdv_day: int, rdv_slot: str) -> str:
    """Return the lifecycle status of a rendez-vous relative to NOW.
    - 'now':     happening this exact slot
    - 'next':    one slot away (the player's current scene is the lead-up)
    - 'soon':    2-4 slots away (visible as "upcoming" but not yet imminent)
    - 'future':  more than one day away
    - 'past':    already happened
    """
    d = slot_distance(world.day, world.slot, rdv_day, rdv_slot)
    if d < 0:
        return "past"
    if d == 0:
        return "now"
    if d == 1:
        return "next"
    if d <= 4:
        return "soon"
    return "future"


def imminent_rendezvous(world: WorldState, whereabouts: list[dict]) -> list[dict]:
    """Filter known_whereabouts down to rendez-vous that are happening NOW or NEXT
    slot. Each item gets a `status` field added. Used by the engine (force the
    character into the scene) and by the map UI (RDV badge)."""
    out: list[dict] = []
    for w in whereabouts or []:
        if not w.get("is_rendezvous"):
            continue
        try:
            day = int(w.get("day", 0))
        except (TypeError, ValueError):
            continue
        slot = str(w.get("slot", "")).strip().lower()
        if slot not in SLOTS:
            continue
        status = rendezvous_status(world, day, slot)
        if status in ("now", "next"):
            out.append({**w, "status": status})
    return out


def player_was_at(world: WorldState, day: int, slot: str, location_id: str) -> bool:
    """True if world.history records the player at (day, slot, location_id).
    Also true if the player is currently there at that exact slot (history entry
    is appended on arrival, so a present-slot stay is included)."""
    for h in (world.history or []):
        try:
            if int(h.get("day", 0)) == int(day) and str(h.get("slot", "")) == slot and str(h.get("location", "")) == location_id:
                return True
        except (TypeError, ValueError):
            continue
    return False


def missed_rendezvous(world: WorldState, whereabouts: list[dict]) -> list[dict]:
    """Past rendez-vous where the player was NOT at the location. Items NOT yet
    flagged `missed=True` are returned (so the caller can apply the penalty
    once and persist the flag).
    """
    out: list[dict] = []
    for w in whereabouts or []:
        if not w.get("is_rendezvous"):
            continue
        if w.get("missed") or w.get("kept"):
            continue  # already adjudicated
        try:
            day = int(w.get("day", 0))
        except (TypeError, ValueError):
            continue
        slot = str(w.get("slot", "")).strip().lower()
        if slot not in SLOTS:
            continue
        if rendezvous_status(world, day, slot) != "past":
            continue
        loc_id = str(w.get("location_id", "")).strip()
        if player_was_at(world, day, slot, loc_id):
            continue  # player kept the date — handled separately
        out.append(w)
    return out


def adjudicate_past_rendezvous(world: WorldState, whereabouts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Walk every PAST rendez-vous and split into (missed, kept) lists. Mutates
    the source dicts to add `missed=True` or `kept=True` so they're never
    re-counted. Caller is responsible for persisting the updated whereabouts.
    """
    missed: list[dict] = []
    kept: list[dict] = []
    for w in whereabouts or []:
        if not w.get("is_rendezvous"):
            continue
        if w.get("missed") or w.get("kept"):
            continue
        try:
            day = int(w.get("day", 0))
        except (TypeError, ValueError):
            continue
        slot = str(w.get("slot", "")).strip().lower()
        if slot not in SLOTS:
            continue
        if rendezvous_status(world, day, slot) != "past":
            continue
        loc_id = str(w.get("location_id", "")).strip()
        if player_was_at(world, day, slot, loc_id):
            w["kept"] = True
            kept.append(w)
        else:
            w["missed"] = True
            missed.append(w)
    return missed, kept


def upcoming_rendezvous(world: WorldState, whereabouts: list[dict]) -> list[dict]:
    """Same as imminent_rendezvous but includes 'soon' and 'future' too — used
    by the map UI to show ALL pending appointments, not just the imminent ones."""
    out: list[dict] = []
    for w in whereabouts or []:
        if not w.get("is_rendezvous"):
            continue
        try:
            day = int(w.get("day", 0))
        except (TypeError, ValueError):
            continue
        slot = str(w.get("slot", "")).strip().lower()
        if slot not in SLOTS:
            continue
        status = rendezvous_status(world, day, slot)
        if status == "past":
            continue
        out.append({**w, "status": status})
    # Sort by absolute slot index (soonest first)
    out.sort(key=lambda x: slot_distance(world.day, world.slot, int(x["day"]), x["slot"]))
    return out
