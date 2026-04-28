# GraphBun — Slice-of-Life Game Mechanics

A complete reference of every mechanic that runs when **slice-of-life mode** is enabled. Classic mode (intro arc + scenario-driven) is documented separately and is NOT covered here.

This file mirrors what's in the code as of late April 2026. File paths + key functions are inline so you can jump straight to the implementation.

---

## 1. World model

The slice world is a tiny 4-slot-per-day clock with a fixed set of locations and a stack of moves the player has made.

**Files**: `backend/world.py`

### Locations
- `Location(id, name, type, description)` — `id` is `lowercase_snake_case`, used for routing. `type` ∈ `{home, cafe, bar, club, gym, park, work, salon, other}` and drives the icon shown in the map.
- A world has exactly one `home` location (always the player's starting point) and one `work`. The other 4 are themed to the setting.

### Time
- Slots: `morning, afternoon, evening, night` (`world.py:18 SLOTS`)
- `world.day` is an integer ≥ 1
- `advance_time(state)` rolls the slot forward; night → morning of next day
- `set_location(state, location_id, advance=True)` switches location AND advances time by one slot (going somewhere takes time)
- `state.history: list[{day, slot, location}]` — every place the player has been; used to detect missed rendez-vous (§5.3).

### World creation (game start)
- `agent.generate_world_and_agents(grok, setting_label, custom_setting_text, cast_actors, language)` — ONE Grok call produces 6 themed locations + per-character schedules + temperaments in a single coherent shot. Names + descriptions are written in the player's narration `language` and themed to the chosen setting (Paris-2026, Paris-1830, Neo-Tokyo, or any custom blurb the user wrote).
- `setting_label` falls back to the canned setting; **`custom_setting_text` dominates** when present (mixing both confused the LLM into Paris-themed locations even when the player asked for NYC).
- Fallback: if the unified call fails, `default_world_for_setting(setting_id)` ships pre-canned Paris-2026/1800/Neo-2100 locations + per-character `generate_character_state` calls.

### Persistence
- World, character_states, known_whereabouts, and `recent_missed_rendezvous` are all stored on the session and round-trip through `db.py` via `session.video_settings._world_state`, `_character_states`, `_known_whereabouts`, `_recent_missed_rendezvous`. Old sessions resume cleanly because all `from_dict` paths default missing fields.

---

## 2. Cast — schedules, temperament, daily tick

Each cast member has a `CharacterState` (`world.py:190`) generated at game start.

### Fields
| Field | Purpose |
|---|---|
| `code` | LoRA codename (matches `ACTOR_REGISTRY`) |
| `personality` | one-line trait summary |
| `job` | role / occupation |
| `schedule` | dict `{<weekday|weekend>_<slot> → "<loc_id>" | "a|b" | "free"}` |
| `overrides` | per-day-slot pinning, used by `set_rendezvous` |
| `today_mood` | refreshed by daily tick |
| `intentions_toward_player` | refreshed by daily tick |
| `recent_events` | **list** of `{day, text}` (capped at `MAX_RECENT_EVENTS = 7`) — appended each daily tick. The `cs.recent_event` (singular) property still returns the latest entry's text for back-compat |
| `last_tick_day` | bookkeeping: never re-tick the same day |
| `temperament` | `reserved | normal | wild` — drives reaction cues + trust delta multipliers (NOT mood gating) |

### Schedules
- Pipe-separated multi-candidates ("`gym|cafe`") resolve via `stable_choice((code, day, slot), candidates)` — deterministic per character per day, but varies day-to-day.
- `free` = no fixed plan; the resolver treats them as ABSENT unless overridden by a rendez-vous.
- Schedules are **deconflicted** for evening slots: if 2+ cast members single-pin the same evening location, all but the first get demoted to `free` (`agent._deconflict_schedules`). Mornings/work and nights/home are intentionally allowed to overlap.

### Temperament (Feature 1 follow-up)
- Auto-picked by the world generator with a roughly 20/60/20 split (reserved/normal/wild). The LLM is told to mix temperaments across the cast.
- Temperament drives **narrative reactions**, not LoRA gating. See §3.3.

### Daily tick (`agent.daily_tick`)
- Runs at the start of any sequence where at least one character has `last_tick_day < world.day` — i.e., when a day has rolled over off-screen.
- **Throttling**: only ticks characters with `relationships[code].level >= 1` (ones the player has actually met). Saves cost on never-met cast; their state stays frozen until the player encounters them.
- For each eligible character, fires a parallel Grok call that returns `{today_mood, intentions_toward_player, recent_event}` based on personality + temperament + relationship level + previous-day state + recent_events history.
- `recent_event` is **appended** to `cs.recent_events` (capped at 7, oldest evicted). Each entry is a small off-screen life beat (a phone call, a routine work moment, a tiny realisation) — NEVER about the player.
- The narrator prompt's *Personnages présents* block surfaces the **last 3 events with day stamps** as a "Vie hors-scène (récente)" sublist — much richer continuity than the previous single "Hier" line.
- Cost: ~$0.0002 per game day per eligible character. Failure is non-blocking — characters just keep yesterday's state.

---

## 3. Encounters — resolver, caps, gates, rendez-vous

### 3.1 Presence resolver (`world.who_is_at`)
- Returns the codenames of cast members whose schedule places them at `(location_id, day, slot)`. Uses `stable_choice` for multi-candidate slots.
- Called once per sequence in `story_engine._orchestrate`. Result becomes `present_characters`.

### 3.2 Early-game cap
- **Sequence 0**: ALWAYS solo (`present_characters = []`) regardless of resolver. Even if a character would naturally be at home, they're stripped.
- **Sequences 1-2**: capped to ONE character max — the resolver may have placed several at the same location, only the first is kept.
- **Sequence 3+**: no cap, the world is fully alive.

### 3.3 Rendez-vous override (Feature 1)
A rendez-vous defeats the resolver AND the cap.

- **Detection**: `agent.extract_whereabouts` runs after every sequence. It parses the narration for future-self statements and flags each as `is_rendezvous: bool`. A rendez-vous is a *mutual* commitment ("on se voit demain au bar"), not a one-sided announcement ("je serai au boulot demain").
- **Status** (`world.rendezvous_status`): `now | next | soon | future | past`, derived from `slot_distance(world, rdv_day, rdv_slot)`. Updated implicitly every time the world clock advances.
- **Force presence**: in `_orchestrate`, when an `imminent_rendezvous` has `status='now'` AND its `location_id == world.current_location`, the character is unconditionally added to `present_characters`. The presence_gate (§4.4) trusts that list, so the LoRA loads for the meeting.
- **Prompt cue**: `prompt_builder._slice_sequence_context` injects a `### ⏰ RENDEZ-VOUS — MAINTENANT, ICI` block telling the narrator to play out the meeting (greeting, recognition, anticipation) instead of treating it as a chance encounter.
- **Teaser**: rendez-vous with `status='next'` (one slot away) get a softer `### ⏳ Rendez-vous imminent` block — the narrator can drop a subtle hook (a glance at the clock, a remembered text) to build anticipation.
- **Map UI**: `MapModal.tsx` shows a top-of-modal RDV teaser block (rose-tinted) for `now`/`next` rendez-vous, plus a per-location ⏰ RDV chip and a rose border on locations with imminent meetings. The agenda block distinguishes RDVs from informational whereabouts.

### 3.4 Missed rendez-vous (Feature 1 follow-up)
- **Adjudication** (`world.adjudicate_past_rendezvous`): every sequence start, walks PAST rendez-vous and decides:
  - `kept` — `world.history` shows the player at the rdv location during the rdv slot
  - `missed` — player was elsewhere
- Each entry gets a persistent `missed=True` or `kept=True` flag so it's never re-judged.
- **Penalty**: missed RDV drops `relationships[char].level` by 1, clamped at 0. Logged as `[rdv] MISSED — char relationship dropped 2→1 ...`.
- **Narrative cue**: missed RDVs are stashed on `session.recent_missed_rendezvous` and surfaced ONCE in the next sequence's prompt as a `### 💔 RENDEZ-VOUS MANQUÉ` block. The narrator gets temperament-specific reaction guidance:
  - `reserved` → froideur silencieuse, regards évités
  - `normal` → reproche lucide, demande d'explication
  - `wild` → pique sarcastique ou indifférence affichée
  
  Engine clears the list after the prompt is built so we don't keep nagging the narrator.

### 3.5 Whereabouts extractor & dynamic locations
- `agent.extract_whereabouts(grok, narration, char_codes, current_day, current_slot, locations)` runs after every sequence.
- Returns `[{char, location_id, day, slot, source, is_rendezvous, new_location?}]`.
- **Dynamic locations**: when narration mentions a SPECIFIC named place not in the existing list (e.g. "rendez-vous au Sphinx, le club du Marais"), the extractor proposes a `new_location: {id, name, type, description}`. The engine appends it to `world.locations` before storing the whereabouts. New locations show up in the map UI on the next world refresh.
- The extractor refuses vague mentions ("un café") — only specific named spots become real locations.

---

## 4. Narration — lean narrator + specialist agents (Phase 3A-D)

The narrator's system prompt used to be a 44k-char monolith with image rules, mood blocks, full bios, etc. It now lives at ~13-14k chars and only knows storytelling. Heavy lifting is done by specialist Grok agents.

### 4.1 Builder dispatch (`prompt_builder.build_system_prompt`)
- `world is not None` → `_build_slice_prompt`
- `world is None` → `_build_classic_prompt` (out of scope here)

Inside slice mode, three sub-branches:
- **Sequence 0** → `_build_slice_intro_prompt` — atmospheric tour of `home`, props hint at the world's other locations, end choices = those destinations.
- **`present_characters` is empty** (any later quiet beat) → `_build_slice_solo_prompt` — leanest variant, no cast / pool / relationships at all. Lets the narrator write a quiet solo scene without the cast tempting it.
- **Otherwise** → full slice prompt with cast bios, relationships, mood enum, etc.

### 4.2 Narrator's tool call
The narrator emits ONE `generate_scene_image(...)` call per scene with **lean** fields:
- `scene_summary` — 1-2 sentences in the narration language: who does what, body language, key emotion. NO camera direction, NO lighting words.
- `shot_intent` — 1 short hint ("gros plan intime", "plan atmosphérique large", "macro de deux mains"). Server-side scrubbed (§5.2) for player-back-shot patterns.
- `mood` — ONE canonical mood name (`neutral`, `kiss`, `missionary`, etc.). Server-side gated + auto-promoted (§5.3).
- `actors_present` — codenames of cast in the scene. Server-side gated (§4.4).
- `character_names` — codename → display name map. Locks identity once and for all.
- `location_description`, `clothing_state` — for cross-scene continuity.

The narrator does NOT write the Z-Image prompt. A specialist composes it (§5.1).

### 4.3 Codename scrubber
- `story_engine._clean_narration(text, codename_to_name)` runs on every assistant chunk.
- Replaces verbatim cast codenames in narration text with the display name (or strips them if no name is locked yet).
- Catches the introduction-turn slip where Grok writes `white_short` instead of `Elara` in narration.

### 4.4 Presence gate (`presence_gate.gate_presence`)
- Strips cast codenames from the narrator's `actors_present` if they're not in `present_characters`. Pool actors and unknown codenames pass through.
- **Solo mode** (slice + empty `present_characters`): expands the strip set to `ACTOR_REGISTRY.keys()` so pool actors don't leak in either. Without this, Grok will sometimes guess a real codename ("nesra") and the LoRA loads coincidentally.
- Stripped codenames are also removed from `character_names` so no permanent character lock is created.

### 4.5 Cast section (Phase 3B — lazy character bios)
- The cast block is now **one line per character**: `codename \`code\` — personality, job` for slice mode (or `description's first clause` if no daily tick has run yet).
- Visual bio (description + trigger word + LoRA hints) is loaded by the image specialist on demand from `ACTOR_REGISTRY` for actors in `actors_present`. The narrator never sees the visual bio.
- The cast intro forces: `INVENTE un prénom local — N'utilise JAMAIS le codename comme prénom de scène. nesra, white_short, blonde_cacu ne sont PAS des prénoms.`

### 4.6 Pool actors
- Any LoRA-backed actor in `ACTOR_REGISTRY` not in the session cast becomes a "pool" actor — the narrator can introduce them when narratively warranted.
- Pool block is just a comma-separated codename list. The specialist pulls the visual bio when the codename appears in `actors_present`.

### 4.7 Relationships block (with reaction cues)
- Six levels: `0 STRANGER → 5 LOVER`. Updated by `story_engine` after each scene based on the **requested** mood (post-promotion, pre-gate) so trust grows naturally.
- For each character: line shows `{level_label} · tempérament \`{temp}\` — N séquences, M scènes` and a temperament-aware **reaction cue** drawn from a 6×3 matrix in `prompt_builder._REACTION_CUES`. Examples:
  - L0 × reserved: *"très distante, observe à peine, refuserait tout contact ; un regard appuyé suffit à la mettre en retrait."*
  - L2 × wild: *"embrasse facilement, se laisse caresser par-dessus les vêtements ; pousserait elle-même vers plus si rien ne la freine."*
- Closing rule tells the narrator: use these as **narrative drivers, not constraints**. If the player tries something above the current level, the character HÉSITE / RECULE / REFUSE GENTIMENT — that creates the seduction tension. Mood gate handles the mechanical guardrail.

### 4.8 Trust score (bidirectional, temperament-curved)
On top of the per-scene mood-based level bumps, every relationship now carries a continuous **`trust: float`** score that drifts up and down based on the player's behaviour. Implementation in `backend/trust.py`.

- **Extractor** (`agent.extract_trust_deltas`): runs at the end of every sequence with `present_characters`. Reads `previous_choice + narration + per-char temperaments` and returns a list of `{char, delta ∈ -3..+3, reason}`. Calibration: ±3 for defining moments (real betrayal / real bonding), ±1 for small good/bad signals, 0 if nothing meaningful happened.
- **Temperament curves** (per character):
  | | pos_mult | neg_mult | thresh |
  |---|---|---|---|
  | wild | 1.5× | 0.7× | 0.7× |
  | normal | 1× | 1× | 1× |
  | reserved | 0.7× | 1.3× | 1.4× |
  
  `pos_mult` and `neg_mult` scale the raw delta before adding to trust. `thresh` scales the level transition bands. So a wild character grows trust faster + drops slower + needs less to level up; reserved is the inverse.
- **Level transitions** from trust (normal-temperament thresholds): `L1 ≥ 1`, `L2 ≥ 4`, `L3 ≥ 9`, `L4 ≥ 16`, `L5 ≥ 26`. Reserved characters need ×1.4 those values; wild characters need ×0.7.
- **Mood floor protection** (`record_scene_mood_floor`): every per-scene mood bump also locks `rel.scene_mood_floor_level`. The level NEVER drops below the floor, so a kiss scene physically happening locks `level >= 2` even if subsequent trust drops would otherwise push back to `1`. Mechanical reality wins over score-based extrapolation.
- **History**: `rel.trust_history` keeps the last 20 delta records `{sequence, raw_delta, applied_delta, new_trust, new_level, level_change, reason}` for the debug UI.
- Backend log per delta: `[trust] nesra (reserved): raw=+2 applied=+1.4 → trust=3.5 L1 ↑  (player listened patiently when she opened up)`.
- Cost: ~$0.00006 per sequence (single Grok call, only fires when `present_characters` is non-empty).

---

## 5. Image generation

### 5.1 Image-prompt specialist (`scene_agent.craft_image_prompt`)
- Receives the narrator's lean spec + actor lookup (description + trigger word + gender per code) + mood data + clothing state + appearance state + time of day + scene+setting context.
- Returns a fully self-contained Z-Image Turbo prompt (~80-200 words) following the 4-layer Camera Director Formula:
  1. **Subject**: shot type + person + clothing + hands; multiple non-LoRA NPCs must each get DISTINCT features.
  2. **Setting**: location, decor, environment.
  3. **Lighting** (mandatory, MUST match `time_of_day`): candlelight / amber lamps / dawn / sunlit per slot.
  4. **Camera**: lens + photo style + DoF.
- Skin realism keywords (`highly detailed skin texture`, `subtle skin pores`, `natural skin tones`) on every human subject.
- Trigger words placed at the very start for the FIRST character; additional trigger words appear inline before each character's description (never stacked at the start).

### 5.2 POV protection (multi-layer)
- **Specialist system prompt** has a strict "⛔ The player is NEVER a SUBJECT of the frame" section listing forbidden phrasings (back-shots, silhouettes, his face/jawline, "a male figure standing/contemplating") and POV-correct alternatives.
- **Narrator prompt** image-handoff: explicit ban on third-person shot intents.
- **Server-side sanitiser** (`scene_agent._sanitize_shot_intent`):
  - Strips back-shot patterns regardless of actors: `plan arrière`, `de dos`, `silhouette du joueur/protagoniste`, `silhouette solitaire/contemplative`, `over-the-shoulder`, `rear shot`, `from behind the player`, `wide shot of the player`. Replaced with "plan large POV (paysage / décor)".
  - When `actors_present` is empty, ALSO strips face close-up patterns (`gros plan facial`, `close-up of the face`, `gros plan sur le visage/yeux`) — by elimination, the face would be the player's. Replaced with "plan POV serré sur objet / détail".

### 5.3 Mood — gate + auto-promote
- **Mood gate** (`mood_gate.gate_mood`): each mood has a minimum relationship level. After the loosening pass:
  - `neutral`, `sensual_tease` → 0
  - `kiss`, `explicit_mystic`, `blowjob`, `cunnilingus`, `missionary`, `cowgirl`, `doggystyle`, `spooning`, `standing_sex`, `titjob`, `handjob` → 1
  - `anal_*`, `cumshot_face`, `futa_shemale` → 2
- Below threshold → downgraded to a per-level safe fallback: `0 → sensual_tease`, `1 → kiss`, `2+ → explicit_mystic`.
- **Relationship update uses the REQUESTED mood**, not the post-gate one — otherwise trust would never grow when the gate clamped (Catch-22 we hit and fixed).
- **Auto-promote** (`mood_gate.infer_mood_from_summary`): when the narrator picked `neutral` but `scene_summary` clearly mentions a position keyword (`missionary`, `kiss`, `blowjob`, `doggystyle`, `cunnilingus`, `cowgirl`, `spooning`, `cumshot`, `anal`, `titjob`, `handjob`), promote to the matching mood. Catches the over-cautious narrator that defaults to neutral while writing explicit prose.

### 5.4 Clothing lock
- `consistency.clothing: dict[code → outfit]` is updated from each scene's `clothing_state` arg.
- The engine merges the locked clothing with the current scene's args (args wins per-actor, so a deliberate change overrides) and passes the merged dict to the specialist.
- Specialist's system prompt has a "Clothing continuity — CRITICAL" rule: copy each character's outfit VERBATIM. Exception: when `scene_summary` explicitly says the character changed clothes ("she takes off the corset").

### 5.5 Appearance lock
- After the FIRST scene a cast member appears in, `scene_agent.extract_appearance(grok, codename, image_prompt)` pulls the head/shoulders description (age, ethnicity, hair, eyes, skin, signature features) from the just-crafted image prompt and stores it in `consistency.appearance[code]`.
- Subsequent scenes pass `appearance_state` to the specialist with a "Locked appearance — CRITICAL" rule: use those features VERBATIM, no synonyms ("short bob ≠ pixie cut ≠ cropped hair"). Exception: when `scene_summary` describes a change ("hair now wet", "fresh makeup") the locked baseline stays AND the situational change is added on top.

### 5.6 Time of day & lighting
- `world.slot` is passed as `time_of_day` to the specialist with a hard rule:
  - `night` → candlelight / warm bedside lamp / neon / moonlight / streetlamp
  - `evening` → warm sunset / golden hour / amber lamps / dusk through curtains
  - `morning` → cool diffused dawn / soft window light
  - `afternoon` → bright natural daylight / sunlit interior
- "NEVER write 'sunlit' / 'bright daylight' for an evening or night scene." Stops Z-Image defaulting to bright daylight when the world clock says midnight.

---

## 6. TTS narration & video lipsync

### 6.1 Multi-voice split (Phase A)
- Narration text is parsed into ordered segments by `tts.parse_speech_segments`: anything inside `«»` / `""` / `""` is `dialogue`, the rest is `narration`.
- For each scene:
  - **Pure narration** → single TTS call with `narration_voice` (default `sal`) and `mode="narration"`.
  - **Pure dialogue** → single TTS call with the speaker's voice (§6.2) and `mode="dialogue"`.
  - **Mixed** → segments enhanced in parallel (each with its own mode + voice), synthesised in parallel via xAI direct, MP3 chunks naive-concat'd.
- Boundary pauses are deduped (`tts.dedupe_boundary_pauses`) so the concat doesn't produce double-pauses.

### 6.2 Per-character voice (Phase B)
- At game start (`main.py:start_game`), `cast.actor_voices: {code → voice}` is auto-populated by gender:
  - female / unknown → cycle through `[ara, eve]`
  - male → cycle through `[leo, rex]`
  - trans → treated as female
- The dialogue voice for a scene is `actor_voices[first_present_actor]`, falling back to the configured `voice_id`.

### 6.3 Per-segment enhance
- Each segment is rewritten by Grok via `tts.enhance_speech_text` with a `mode`-specific brief (`_MODE_BRIEFS`):
  - **narration** mode: slow, breathy, restrained — `[pause]` between sentences, `<soft>` for confidences, NEVER `<loud>` / `<fast>` / `[laugh]`.
  - **dialogue** mode: conversational pace, expressive tags, `[laugh]` / `[chuckle]` / `[sigh]` allowed.
  - Both modes ship with a hard `⚠️ Pick ONLY ONE wrapping tag per sentence/line. NEVER stack two.` rule (the next bullet explains why).
- The full TTS tag dictionary lives at `tts.TTS_TAG_GUIDE`.
- **Tag flattening** (`_sanitize_tts_tags`): xAI TTS doesn't reliably handle nested wrapping tags — when it bails, it speaks the inner tag name aloud as a literal word ("slow", "soft", "lower-pitch"). The sanitizer now drops any wrapping-tag opening that arrives while another wrapping tag is already on the stack, keeping ONLY the outermost. So `<soft><slow><lower-pitch>X</lower-pitch></slow></soft>` collapses to `<soft>X</soft>` before reaching xAI. Sequential separate tags pass through unchanged; single-tag sentences pass through unchanged.

### 6.4 Narrator voice setting (UI)
- The setup page exposes **two voice dropdowns**:
  - **Narrator voice** (default `sal` neutral) — used for every narration prose segment regardless of who's in the scene.
  - **Dialogue fallback** (default `ara`) — used for dialogue when no per-character voice is auto-assigned (Phase B handles the rest).
- Backend: `narration_voice` field on `StartGameRequest`, stored at `session.video_settings["narration_voice"]`.

### 6.5 Video lipsync gating
- When `voice_to_video=True` AND the scene has dialogue → fire ONE dialogue-only TTS call, audio is fed to P-Video for lip-sync.
- When `voice_to_video=True` BUT the scene has NO dialogue → skip the lip-sync TTS, fire a standalone narration TTS instead. Video gen falls back to its prompt-only path (ambient sounds, breath). Stops the "character lip-syncing the narrator's words in `ara` voice" failure mode.

---

## 7. Mobile audio — singleton + gesture warmup

iOS Safari grants `audio.play()` per-element, only to elements that started loading during a user gesture. Per-scene `<audio>` elements (one per `SceneCard`) failed silently after the first one because each new mount missed the gesture window.

**Files**: `frontend/src/hooks/useSceneAudio.ts`, `frontend/src/components/game/SceneCard.tsx`

### 7.1 Singleton
- ONE `<audio>` element appended to `<body>` on first hook call. Module-scoped, persists across re-renders.
- `playscene(src, sceneIndex)` swaps `.src` and calls `.play()`. Idempotent for the same `(src, sceneIndex)`.
- `pauseScene(sceneIndex)` only pauses if the singleton is currently loaded with that scene's audio — prevents the "scene 5's audio finished loading mid-play of scene 0 → its effect re-fires → calls pause → silences scene 0" bug.

### 7.2 Gesture warmup
- First `pointerdown` / `touchstart` / `keydown` (capture phase) plays a 244-byte inlined silent WAV through the singleton, then immediately pauses. iOS marks that element as user-activated for the rest of the page lifetime; subsequent `.src=…` + `.play()` work without further gestures.
- Subscribers can read `isWarmed: boolean` to gate UI affordances.

### 7.3 SceneCard wiring
- Each `SceneCard` calls the hook and, in a single effect:
  ```
  if (isViewing) playScene(sceneAudioSrc, index)
  else pauseScene(index)
  ```
- The `isViewing` prop comes from `GamePage.tsx:98-122` IntersectionObserver (scroll-snap detection).
- `GamePage` calls `useSceneAudio()` once at the top so the singleton + gesture listeners are installed before any SceneCard mounts.

---

## 8. Map UI

**Files**: `frontend/src/components/game/MapModal.tsx`, `frontend/src/pages/GamePage.tsx`

### 8.1 List view (current)
- All locations shown as buttons with type icon + name + description.
- Per-location chips: cast members likely present, green-tinted. **The chip is a forecast** of who you'll find when you go:
  - For the **player's current location** → resolver at the **current** slot ("X is here right now").
  - For **other** locations → resolver at the **NEXT** slot ("X will be there when you arrive"), because clicking a non-current location calls `set_location(advance=True)` which bumps the slot. Without this split the chip lied: "Nesra at the bar" (evening) → tap → time advances to night → empty bar.
  - Tooltip wording branches: `map.character_here_tooltip` for current location, `map.character_on_arrival_tooltip` for others.
- Per-location ⏰ RDV chip (rose-tinted) when an imminent rendez-vous targets that location.
- Top-of-modal teaser block listing all `now` / `next` rendez-vous with the source quote.
- "Recent" footer showing the player's last 5 (day, slot, location) moves.
- "Agenda" block showing future whereabouts the player has been told about — RDVs are rose-tinted with a ⏰ RDV tag, plain whereabouts are emerald.

### 8.2 i18n
- All map strings go through `useT()` (`map.title`, `map.day`, `map.pick_location`, `map.you_are_here`, `map.rdv`, `map.rdv_now`, …). Dictionaries in `frontend/src/i18n/translations.ts` for `fr` and `en`. Other languages fall back to French via the lookup.

### 8.3 Free-roam choice
- A 5th `Aller ailleurs (carte)` choice is added to every sequence's choices list by `ChoicesPanel.tsx`. Tapping opens the map.
- When the player picks a destination from the map: frontend calls `/api/game/go_to_location` (advances time, sets new location) then auto-fires the next sequence with `previous_choice = "Aller ailleurs : <loc_name>"`.
- `prompt_builder._slice_sequence_context` detects `"ailleurs"` OR `"elsewhere"` in the previous choice and injects the **MOVED VIA MAP** rule: characters from the previous scene do NOT auto-follow.

---

## 9. Engine flow per sequence — the orchestration loop

`story_engine.StoryEngine._orchestrate` runs once per `/api/game/sequence` call. Order of operations:

1. **Adjudicate past rendez-vous** (§3.4) — apply penalties, stash missed list.
2. **Daily tick** (§2 — *Daily tick*) — refresh moods/intentions/recent_event for any character whose `last_tick_day < world.day`.
3. **Resolve presence** (§3.1) — `who_is_at(...)`.
4. **Apply early-game cap** (§3.2) — seq 0 = solo, seq 1-2 = max 1.
5. **Apply rendez-vous override** (§3.3) — force RDV-now characters into `present_characters`.
6. **Compute teaser RDVs** — `next` slot RDVs that aren't already happening here-now.
7. **Build system prompt** with all of the above + relationships (§4.7) + temperaments (reaction cues) + missed RDV cue (§3.4).
8. **Stream Grok** with the lean tool definitions. For each `generate_scene_image` tool call:
   - Sanitise `shot_intent` (POV defense, §5.2)
   - Apply `presence_gate` (§4.4)
   - Apply `mood_gate` + auto-promote (§5.3)
   - Update relationships from the REQUESTED mood
   - Build merged clothing + appearance state
   - Call `craft_image_prompt` (specialist, §5.1)
   - Capture appearance for any first-time cast member (§5.5)
   - Fire image generation + parallel TTS call (§6)
9. **At end of sequence**: extract whereabouts (§3.5) — may include new rendez-vous AND new dynamic locations.
10. **Persist + log + emit `sequence_complete`**.

Cost roll-up is logged to the per-sequence JSON event log at `backend/logs/last_sequence.json` and appended to `session_log.jsonl` for audit.

---

## 10. Mem0 long-term memory

`backend/memory.py` wraps the [mem0](https://mem0.ai) client. Three distinct namespaces, all hashed `user_id`s prefixed for clarity:

| Scope | id format | What it stores | When recalled |
|---|---|---|---|
| **session_narrative** | `gb<md5(user:session)>` | Per-game facts: setting label, sequence narrations, choices made | Recalled at every sequence start (`recall_narrative_context`) when `sequence_number > 0`. Injected as `## Mémoire narrative` block. |
| **persistent** | `gbp<md5(user:setting)>` | Cross-session facts SHARED across all games in the same setting (cast encounters, player decision patterns) | Recalled at every sequence start (`recall_persistent_memory`). Injected as `## Mémoire persistante (histoires précédentes)` block — the narrator treats these as *déjà-vu* shared past, never recites them verbatim. |
| **per-character** | `gbc<md5(user:setting:char:code)>` | What ONE specific character "remembers" about the player. Cross-session, scoped to (user + setting + character_code) so a character truly recognises the player when they meet again in a new game. | Recalled per-character at sequence start (`recall_character_memory`). Injected as `## Mémoire des personnages` per-character sublist. |

### Cross-character leak (fixed)
Before the fix, `store_sequence_narrative(...)` was called with `characters = session.cast.get("actors")` — i.e. the FULL cast. Every cast member's per-character memory got the narration of every sequence, even ones they were never in. Léa "remembered" Nesra's bar evening because her store was hit too.

Now (`backend/story_engine.py`, post-sequence): `_chars_in_sequence` is built from the union of every scene's `actors_present` (collected during the round) plus `present_characters` (resolver placement) as a backstop. Only characters who actually appeared get their per-character memory written to.

### Debug surface
- Endpoint `GET /api/debug/mem0/all/{session_id}` returns all three scopes in one call: `session_narrative`, `persistent`, and `per_character` (one entry per cast member with the raw memories + scope_id + timestamps).
- Frontend client: `getAllMem0(sessionId)` → `Mem0AllResponse` (`frontend/src/api/client.ts`).
- DebugPanel **Mem0 tab** shows:
  - The existing live-context panel (formatted blocks injected into the prompt).
  - **Mémoire par personnage** — one card per cast member with codename + fact count + scope_id + the raw memory list with creation timestamps. Empty card = "no memories stored for this character" — useful to verify isolation.
  - Two collapsible `<details>` for the raw session-narrative + persistent dumps.
- The refresh button refetches both the formatted block AND the raw all-scopes endpoint.

### Cleanup
- `delete_session_memories(user_id, session_id)` — wipe one game.
- `delete_persistent_memories(user_id, setting_id)` — wipe persistent for a setting (the "Effacer les souvenirs" button on Setup).
- `delete_all_user_memories(user_id, [setting_ids])` — wipe persistent across all settings.
- Per-character memories don't have a dedicated delete helper yet — clear via the mem0 dashboard by `user_id` if needed.

---

## 11. Cost & latency notes

Per sequence (8 scenes), slice mode, voice on:
- **Narrator Grok call**: ~$0.005-0.01 input, mostly cached after sequence 1. Smaller after Phase 3 lean refactor.
- **8× image-prompt specialist calls**: ~$0.0008 total. Parallel-friendly.
- **Per first-appearance**: 1 appearance extractor call (~$0.00005 each, fires once per actor per session).
- **8× image generation** (Z-Image Turbo via Runware): variable.
- **Per scene TTS**: 1-3 enhance calls + 1-3 synthesis calls (depending on segment count). Runs in parallel; latency = max segment time + ~1s.
- **Whereabouts extractor**: 1 call per sequence, ~$0.00006.
- **Daily tick**: 1 call per cast member per game day. ~$0.0002 for a 4-character cast.

---

## 12. File map (slice-mode-relevant)

**Backend**
- `backend/world.py` — World/Location/CharacterState, time, presence resolver, rendez-vous helpers, `MAX_RECENT_EVENTS`
- `backend/agent.py` — `generate_world_and_agents`, `daily_tick`, `extract_whereabouts`, `extract_trust_deltas`
- `backend/scene_agent.py` — `craft_image_prompt`, `extract_appearance`, POV sanitiser
- `backend/mood_gate.py` — `gate_mood`, `infer_mood_from_summary`
- `backend/presence_gate.py` — `gate_presence`
- `backend/trust.py` — `apply_trust_delta` (temperament curves), `record_scene_mood_floor`, `thresholds_for`
- `backend/memory.py` — mem0 wrappers: `store_sequence_narrative`, `store_character_chat`, `recall_*`, three id helpers (`_user_session_id`, `_persistent_user_id`, `_character_memory_id`)
- `backend/prompt_builder.py` — `_build_slice_prompt`, `_build_slice_intro_prompt`, `_build_slice_solo_prompt`, all the `_section_*` helpers, reaction cue matrix
- `backend/story_engine.py` — `_orchestrate` (the loop above), `_fire_tts_task` (multi-voice path), `_clean_narration` (codename scrubber)
- `backend/tts.py` — `parse_speech_segments`, `enhance_speech_text` (mode-aware), `extract_dialogue`, `concat_audio_chunks`, `dedupe_boundary_pauses`, `_sanitize_tts_tags` (with nested-tag flattening)
- `backend/main.py` — `/api/game/start` (slice path), `/api/game/sequence`, `/api/game/world`, `/api/game/go_to_location`, `/api/debug/mem0/all/{session_id}`, `_build_world_payload`
- `backend/db.py` — session save/restore including `_world_state`, `_character_states`, `_known_whereabouts`, `_recent_missed_rendezvous`

**Frontend**
- `frontend/src/components/game/MapModal.tsx` — list view, RDV badges, agenda, history, next-slot chip forecast
- `frontend/src/components/game/SceneCard.tsx` — scroll-snap target, audio via singleton hook
- `frontend/src/components/game/ChoicesPanel.tsx` — adds "Aller ailleurs" 5th choice
- `frontend/src/components/WorldDebugTab.tsx` — per-character debug card with temperament chip, trust score, scene/intimate counts, mood floor, recent_events log, trust deltas history
- `frontend/src/components/DebugPanel.tsx` — Mem0 tab with per-character cards, raw scope dumps
- `frontend/src/hooks/useSceneAudio.ts` — singleton `<audio>` + gesture warmup (mobile fix)
- `frontend/src/pages/GamePage.tsx` — IntersectionObserver, mounts the audio singleton, top-bar world badge, map button
- `frontend/src/pages/SetupPage.tsx` — narrator voice + dialogue fallback dropdowns
- `frontend/src/stores/gameStore.ts` — `world`, `characterStates`, `knownWhereabouts`, `presenceNow`, `upcomingRendezvous`, `relationships` (with trust history)
- `frontend/src/api/client.ts` — `getAllMem0` for per-character debug
- `frontend/src/i18n/translations.ts` — `map.*` keys (fr + en, others fall back to fr)

---

## 13. TODO — discussed but not yet shipped

Loose backlog of features we scoped or proposed during development but deferred. Roughly grouped by area; effort estimates are rough.

### Map / world UI
- **Visual map view (tier 1 — SVG)** — second tab in the map modal alongside the existing list. Locations as positioned nodes, theme per setting (metro-map for paris_2026, parchment for fantasy, neon grid for neo_2100). Auto-layout or pre-defined coords per canned setting. ~4-5h.
- **Visual map (tier 3 — Z-Image backdrop)** — generate one artistic map backdrop per session via Z-Image (textured parchment, blueprint, satellite), overlay SVG location nodes on top. Best-looking, +$0.002 once per session. ~5-6h.
- **Map → "next up" toast in the top bar** — when an RDV slips into `imminent`, surface it outside the modal too so the player doesn't have to open the map.
- **Auto-suggest "go to RDV" choice** — when an RDV is `next` and the player isn't at the location, inject a deterministic 5th choice `Aller au rendez-vous avec X` so they don't have to navigate.

### Relationships & character life
- ✅ ~~**Bidirectional trust deltas**~~ — shipped (§4.8). `agent.extract_trust_deltas` + `trust.apply_trust_delta`.
- ✅ ~~**Per-temperament difficulty curves**~~ — shipped (§4.8). Wild/normal/reserved curves on both deltas and thresholds.
- ✅ ~~**`recent_event` log instead of single field**~~ — shipped (§2). `cs.recent_events: list[{day, text}]`, capped at 7.
- ✅ ~~**Daily tick throttling**~~ — shipped (§2). Only ticks characters with `level >= 1`.
- **Mem0 per-character memory clearer** — small Setup/Debug button to wipe ONE character's per-character mem0 namespace (e.g. for testing or when a character has accumulated stale facts from a buggy run). Backend helper exists implicitly (`_client.delete_all(user_id=...)`) — just needs an endpoint + button.
- **Trust-aware choices** — when crafting end-of-sequence choices, the narrator could see the trust score per present character so it picks pro/anti-character options consistent with the relationship arc.

### TTS & audio
- **Player-gender voice fallback (Phase C)** — when narrator slips and writes a line attributable to the player ("Tu murmures…", first-person dialogue), voice it with `player_voice = {male: rex, female: eve, other: sal}` instead of the speaker voice. Detect via heuristics on dialogue surroundings. Log slips so we can tighten the narrator prompt. ~30min.
- **Smart speaker attribution in multi-character scenes** — currently uses `actors_present[0]`'s voice for all dialogue. With 2+ characters in scene, parse `« line » said NAME` patterns to pick the right voice per dialogue segment. ~1-2h.
- **Per-character voice UI dropdown** — currently auto-picked at game start. Surface as a dropdown in the cast picker so the user can override (cycle through `[ara, eve, leo, rex, sal]`). ~30min.
- **Mobile audio Phase 2 — URL fallback for multi-voice** — when Phase 1 (singleton + warmup) isn't enough and large base64 data URIs stall iOS decoders, cache merged MP3 server-side and serve via `GET /api/audio/{session}/{seq}/{idx}`. Frontend prefers URL on mobile UAs. ~2h. Skipped because Phase 1 alone resolved the user-reported symptom.
- **Preload next scene's audio** — fetch+decode the next scene's audio while the current one is playing so scroll-snap transitions are seamless. ~1h.

### Image / POV
- **Drop the mood gate entirely** — once the reaction-cue + temperament narrative drivers prove themselves, the Python mood gate becomes pure dead weight. Currently kept as a soft fallback for absurd jumps (missionary at level 0 stranger). ~30min cleanup if ever.
- **Tighten POV sanitiser if drift continues** — current patterns catch back-shots and (when no actor) face close-ups. Could extend to "wide shot of the protagonist", "point of view of X looking at Y", etc. Add patterns as we observe them.

### Phone / messaging
- **In-phone rendez-vous creation** — let the player propose an RDV directly through the phone chat (not just emerging from a scene). Detect `meet me at X tomorrow night` in player's typed phone message and add to known_whereabouts. ~1.5h.
- **Phone notifications for imminent RDVs** — small badge on the phone icon when an RDV is `now` or `next`, with a one-line reminder.

### Game flow
- **Choices anchor enforcement (deterministic)** — for the slice intro sequence, the narrator currently writes 4 choice texts pointing to up-to-4 destinations. Could be made fully deterministic: engine picks the 4 most evocative locations from the world and renders the choice buttons directly, narrator just writes the label. Removes a class of "narrator wrote ambiguous choices" failures.
- **Resume mid-sequence** — currently a sequence is atomic; if the user closes the tab mid-stream, the partial sequence is lost. Persist the in-flight scene index + accumulated narration so a reopen can pick up where it left off.

### Dev quality
- **HTTPS dev server option** — add `@vitejs/plugin-basic-ssl` + a `dev:lan-https` npm script for the day we hit an HTTPS-only browser feature (clipboard, mic, getUserMedia). Not blocking right now.
- **Per-mechanic test coverage** — `mood_gate`, `presence_gate`, `world` rdv helpers, `tts.parse_speech_segments` are all pure functions and trivial to unit-test. Currently only covered by manual smoke runs.
- **Telemetry on mood downgrades & POV sanitisations** — count how often each guardrail fires per session; if a class of fix is rarely needed, retire it. If it fires constantly, the prompt needs tightening.
