# GraphBun — Architecture & Technical Documentation

## Overview

GraphBun is an interactive adult visual novel ("livre dont vous êtes le héros") powered by AI. The story is narrated by Grok (X.AI), illustrated by Z-Image Turbo (Runware), and animated by P-Video (Pruna). The player makes choices that shape the narrative.

**Stack**: FastAPI (Python) + Vite/React/TypeScript + Supabase (auth + DB) + Runware (image/video) + Grok (story LLM) + Mem0 (optional memory layer)

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND (Vite + React 19 + TypeScript + Zustand + Tailwind)   │
│  Port 5173                                                       │
│                                                                  │
│  Pages: AuthPage → SetupPage → GamePage / GalleryPage / Admin   │
│  Stores: authStore (Supabase JWT) + gameStore (game state)       │
│  API: client.ts (apiFetch with auto auth headers)               │
│  SSE: useStoryStream hook for real-time narration + images       │
└──────────────────────┬───────────────────────────────────────────┘
                       │ HTTP + SSE (proxied via Vite)
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  BACKEND (FastAPI + Python 3.13)                                 │
│  Port 8001                                                       │
│                                                                  │
│  main.py ──── 40+ routes (game, debug, admin, sessions)         │
│  story_engine.py ──── Grok streaming + Runware image pipeline   │
│  prompt_builder.py ──── System prompt construction              │
│  tools.py ──── Grok function calling schemas                    │
│  auth.py ──── Supabase JWT (JWKS/ES256)                         │
│  db.py ──── Supabase persistence (service_role)                 │
│  memory.py ──── Mem0 narrative memory (optional)                │
│  config.py ──── Actors, moods, LoRAs, settings                  │
└────────┬──────────────┬──────────────┬──────────────┬───────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐
    │  Grok   │   │ Runware  │   │ Supabase │   │  Mem0   │
    │ (X.AI)  │   │ Z-Image  │   │ Auth+DB  │   │(optional│
    │ Stream  │   │ P-Video  │   │ RLS      │   │ memory) │
    └─────────┘   └──────────┘   └──────────┘   └─────────┘
```

---

## Core Pipeline: How a Sequence Works

Each game sequence produces 5 images + narration + 1 video + 3 choices. The pipeline is designed to minimize perceived latency.

```
Time   Grok Stream                   Runware              Frontend
──────────────────────────────────────────────────────────────────────
0s     Start streaming narration #0  -                    Text appears
~3s    ⚡ tool_call: image 0         → Image 0 starts     "Loading..."
~5s    Narration continues...        Image 0 gen (~6s)    Player reads
~9s    ⚡ tool_call: image 1         Image 0 READY ✓      Image 0 shown
                                     → Image 1 starts     Player reads
~15s   ⚡ tool_call: image 2         Image 1 READY ✓      Swipe → img 1
                                     → Image 2 starts     ...
~30s   All 5 images done             Video starts (~50s)  Scene 5: choices
~80s   -                             Video READY ✓        Video plays
```

**Key mechanisms:**
- `parallel_tool_calls=False` forces Grok to alternate narration ↔ tool call
- Each tool call fires `asyncio.create_task()` for Runware (non-blocking)
- `asyncio.Queue` merges Grok stream events + image completion events into a single SSE stream
- The frontend shows a shimmer placeholder until each image is ready

---

## Project Structure

```
20260319_RunwV2/
├── backend/
│   ├── main.py              # FastAPI app, all routes (28KB)
│   ├── story_engine.py      # Core orchestration engine (36KB)
│   ├── prompt_builder.py    # System prompt construction (25KB)
│   ├── tools.py             # Grok function calling schemas
│   ├── config.py            # Actors, moods, LoRAs, settings (20KB)
│   ├── auth.py              # Supabase JWT verification (JWKS/ES256)
│   ├── db.py                # Supabase persistence (service_role)
│   ├── memory.py            # Mem0 narrative memory (optional)
│   └── migrations/
│       └── 001_initial_schema.sql
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Auth gating → page routing
│   │   ├── api/
│   │   │   ├── client.ts     # 40+ API functions with auth headers
│   │   │   └── types.ts      # SSE events, ImageSlot, SequenceCosts, etc.
│   │   ├── stores/
│   │   │   ├── authStore.ts  # Supabase auth state (Zustand)
│   │   │   └── gameStore.ts  # Game state machine (Zustand)
│   │   ├── hooks/
│   │   │   └── useStoryStream.ts  # SSE connection hook
│   │   ├── pages/
│   │   │   ├── AuthPage.tsx       # Login / signup / magic link
│   │   │   ├── SetupPage.tsx      # 4-step wizard (player → setting → cast → prompt)
│   │   │   ├── GamePage.tsx       # Fullscreen cinematic viewer
│   │   │   ├── GalleryPage.tsx    # Session replay with images/videos
│   │   │   └── AdminPage.tsx      # Cost dashboard (admin only)
│   │   ├── components/
│   │   │   └── DebugPanel.tsx     # Advanced dev tools sidebar
│   │   └── lib/
│   │       └── supabase.ts        # Supabase client init
│   ├── .env                  # VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY
│   └── vite.config.ts        # Proxy /api → localhost:8001
├── app.py                    # Phase 1 standalone test interface
├── static/index.html         # Phase 1 HTML UI
└── requirements.txt
```

---

## Backend Components

### `config.py` — Central Configuration

**Actors** (6 available for casting):

| Codename | Display | LoRA | Trigger | Type |
|----------|---------|------|---------|------|
| `nataly` | Nataly | warmline:202603170002@1 | `N@t@ly` | LoRA-based |
| `shorty_asian` | Shorty Asian | warmline:202603200001@1 | `sh0r7y_asian` | LoRA-based |
| `blonde_cacu` | ZiT Blonde Cacu | warmline:202603200002@1 | `b10ndi` | LoRA-based |
| `ciri` | Ciri (Witcher) | None | None | Prompt-prefix |
| `yennefer` | Yennefer (Witcher) | None | None | Prompt-prefix |
| `custom` | Custom | None | None | User-described |

**Style Moods** (13 configurable, LLM picks per scene):

Each mood has: `description`, `lora` (optional, with weight), `prompt_block` (injected into image prompt Layer 1), `example`, `cfg` override, `steps` override.

| Mood | LoRA | Purpose |
|------|------|---------|
| `neutral` | None | Normal scenes |
| `sensual_tease` | ZIT NSFW v2 (0.72) | Seduction, tension |
| `explicit_mystic` | Mystic XXX V5 (1.0) | Generic explicit |
| `blowjob` | Blow bjz (1.0) | Oral sex |
| `cunnilingus` | ZIT NSFW v2 (0.88) | Cunnilingus |
| `missionary` | Mystic XXX V5 (1.0) | Missionary position |
| `cowgirl` | Mystic XXX V5 (1.0) | Woman on top |
| `doggystyle` | Dog dgz (1.0) | From behind |
| `futa_shemale` | PhotoShemPen V1 (1.0) | Futa/shemale |
| ... | ... | ... |

**LoRA conflict rules:**
- Blow (bjz) and Dog (dgz) are exclusive with Mystic XXX ZIT V5
- ZIT NSFW v2 + Mystic stack poorly → Mystic dropped when ZIT v2 present
- PhotoShemPen + Mystic OK
- Max 3 LoRAs per image (priority: characters > mood > style > extra)

**Available LoRAs** (21 total) for debug picker.

### `story_engine.py` — Core Orchestration

**Classes:**
- `ConsistencyTracker`: Tracks location, clothing, props, prompt overrides across scenes
- `GameSession`: In-memory session state (player, cast, history, costs, settings)
- `StoryEngine`: Drives the Grok ↔ Runware pipeline

**`_orchestrate()` flow:**
1. Build system prompt (via `prompt_builder`)
2. Recall Mem0 memories (if enabled, sequence > 0)
3. Loop: stream Grok → intercept tool calls → fire image gen → continue
4. After 5 images: fire video gen (or early start from image 0)
5. Wait for video → persist to DB → close SSE stream

**`_generate_image()` flow:**
1. Resolve active moods → collect mood LoRAs + cfg/steps overrides
2. Resolve actors → add character LoRAs + trigger words/prompt prefixes
3. Add session style LoRAs + extra LoRAs
4. Deduplicate, enforce max 3, apply conflict rules
5. Build IImageInference request → call Runware
6. Return URL, cost, seed, settings metadata

### `prompt_builder.py` — System Prompt Construction

Builds the system prompt from ~10 sections:
1. **Role**: Narrator of an adult visual novel
2. **Execution flow**: Strict alternation (narration → tool call × 5 → video → choices)
3. **Narration rules**: 2nd person French, dialogue with « », player never speaks
4. **Player profile**: Name, age, gender, preferences
5. **Setting**: Location, era, atmosphere (or custom text)
6. **Cast**: Actors with trigger words/prompt prefixes, story names
7. **Image prompt rules**: Camera Director Formula (4 layers), Z-Image Turbo specifics
8. **Style moods**: Available moods with prompt blocks and examples
9. **Video rules**: Looping motion, subtle for explicit scenes
10. **Consistency**: Location/clothing/props tracking + prompt overrides

### `tools.py` — Grok Function Calling

Three tools defined for Grok:
- `generate_scene_image`: 100-250 word prompt, actors_present, location, clothing_state, style_moods[]
- `generate_scene_video`: Motion + audio description for P-Video
- `provide_choices`: 3 story choices after 5 images

### `auth.py` — Supabase JWT Verification

- Uses JWKS endpoint (ECC P-256, ES256) to verify tokens
- If `SUPABASE_URL` not set → dev mode (returns dummy user)
- `get_current_user()` FastAPI dependency for protected routes

### `db.py` — Supabase Persistence

Uses service_role key (bypasses RLS) for:
- `save_session()`: Upsert game session state
- `save_sequence()`: Store completed sequence with images + video
- `list_user_sessions()`: List user's sessions
- `load_session_data()`: Reload session from DB
- `admin_get_all_costs()`: Aggregate costs across all users
- All writes are fire-and-forget (never block the game)

### `memory.py` — Mem0 Narrative Memory (Optional)

Supplements the ConsistencyTracker with extracted narrative facts:
- After each sequence: sends narration text to Mem0, which auto-extracts key facts
- Before each sequence: recalls facts and appends to system prompt
- Scoped by `user_id + session_id` (MD5 hash)
- If `MEM0_API_KEY` not set → all operations are no-ops

---

## Frontend Components

### State Management (Zustand)

**`authStore`**: user, session, loading, isAdmin, sign in/out methods

**`gameStore`**: Step machine with states:
- `setup` → `playing` → `choosing` → (next sequence or `gallery`/`admin`)
- Tracks: narrationSegments[5], images[5] with ImageSlot, currentScene (0-5), video state, costs

### Pages

**`SetupPage`** — 4-step wizard:
1. Player profile (name, age, gender with custom option, preferences with custom option)
2. Setting (3 presets + custom text)
3. Cast (1-2 actors, custom character description)
4. System prompt (editable, prompt variants in localStorage, style mood configurator, video settings)

**`GamePage`** — Fullscreen cinematic:
- Image fills entire viewport (16:9, object-cover)
- Narration overlay at bottom (gradient fade, visible on hover/streaming)
- 6-dot navigation: scenes 0-4 (white) + scene 5/video (purple)
- Swipe/arrow/keyboard navigation
- Scene 5: video plays with choices overlay
- Debug panel sidebar (collapsible)

**`DebugPanel`** — 5 tabs:
- **Prompts**: Editable image prompts, actor toggles, AI rewrite, seed control, per-image LoRA overrides, resolution/steps, regen button
- **System**: System prompt editor, Grok-powered modification, prompt variants (localStorage)
- **LoRA**: Style LoRAs (session default) + Extra LoRAs (additive)
- **Video**: Status, prompt, settings (draft, audio, duration, resolution, simulate, early_start)
- **Costs**: Per-sequence and session cost breakdown

**`GalleryPage`** — Session replay with image grid, narration snippets, video preview, lightbox

**`AdminPage`** — Cost dashboard: grand total, per-user breakdown, per-session details

### SSE Protocol

| Event | When | Data |
|-------|------|------|
| `narration_delta` | Text streamed | `{content}` |
| `image_requested` | Tool call detected | `{index, prompt, actors, location}` |
| `image_ready` | Runware complete | `{index, url, cost, seed, settings}` |
| `image_error` | Generation failed | `{index, error}` |
| `video_requested` | Video gen started | `{prompt, input_image_index}` |
| `video_ready` | Video complete | `{url, cost, generation_time}` |
| `choices_available` | End of sequence | `{choices[]}` |
| `sequence_complete` | All done | `{costs}` |

---

## Database Schema (Supabase)

4 tables with Row Level Security:

```sql
game_sessions (id, user_id, player, setting, cast_config, ...)
  └── sequences (id, session_id, sequence_number, narration_segments, choices, costs)
       ├── images (id, sequence_id, image_index, url, prompt, seed, gen_settings)
       └── videos (id, sequence_id, url, prompt, cost)
```

RLS ensures users can only access their own data. Backend writes use service_role key (bypasses RLS).

---

## Image Generation — Z-Image Turbo

### Camera Director Formula

Prompts are structured in 4 layers:
1. **Subject & Action**: Shot type, age, ethnicity, body type, clothing (materials, state), hand positions
2. **Setting & Context**: Location, decor, environment grounding
3. **Lighting**: Explicit lighting style (crucial — without it, renders look plastic)
4. **Camera & Style**: Lens type, photography style keyword

### Key Rules
- Z-Image Turbo ignores negations (CFG=0) — never write "no X"
- Trigger words prepended automatically by backend (or prompt_prefix for no-LoRA actors)
- "Magic keywords" for natural skin: `highly detailed skin texture`, `subtle skin pores`, `natural skin tones`
- Style moods inject `prompt_block` text into Layer 1 before clothing description
- Safety checker disabled: `ISafety(checkContent=False)`

### LoRA Priority (max 3 per image)
1. Character LoRAs (from `actors_present`)
2. Mood LoRAs (from `style_moods[]`)
3. Session style LoRAs (debug panel)
4. Extra LoRAs (debug panel)

Deduplication: last occurrence wins. Conflict rules drop Mystic when bjz/dgz/ZIT v2 present.

---

## Authentication Flow

```
Frontend                    Backend                    Supabase
   │                           │                          │
   │  signIn(email, pwd)       │                          │
   │──────────────────────────►│                          │
   │                           │                          │
   │  JWT (ES256)              │                          │
   │◄──────────────────────────│                          │
   │                           │                          │
   │  /api/game/start          │                          │
   │  Authorization: Bearer JWT│                          │
   │──────────────────────────►│                          │
   │                           │  Verify JWT via JWKS     │
   │                           │─────────────────────────►│
   │                           │  OK + user_id            │
   │                           │◄─────────────────────────│
   │                           │                          │
   │  {session_id}             │  Write to DB (service_role)
   │◄──────────────────────────│─────────────────────────►│
```

---

## Environment Variables

### Backend
| Variable | Required | Purpose |
|----------|----------|---------|
| `RUNWARE_API_KEY` | Yes (has default) | Image/video generation |
| `XAI_API_KEY` | Yes (has default) | Grok LLM |
| `SUPABASE_URL` | For auth + DB | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | For DB writes | Service role key |
| `ADMIN_USER_IDS` | For admin features | Comma-separated UUIDs |
| `MEM0_API_KEY` | Optional | Mem0 narrative memory |

### Frontend (.env)
| Variable | Purpose |
|----------|---------|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Publishable key for auth |

---

## Running the Application

```bash
# Terminal 1 — Backend
cd backend && source ../.venv/bin/activate
SUPABASE_URL=https://mwrhulryocftpnsgcxyt.supabase.co \
SUPABASE_SERVICE_KEY=<service_key> \
ADMIN_USER_IDS=<your-uuid> \
MEM0_API_KEY=<optional> \
python main.py

# Terminal 2 — Frontend
cd frontend && npm run dev

# Open http://localhost:5173
```

### First-time setup
1. Create Supabase project, enable Email auth
2. Run `backend/migrations/001_initial_schema.sql` in Supabase SQL Editor
3. Fill `frontend/.env` with Supabase URL + publishable key
4. `pip install -r requirements.txt` + `npm install`

---

## Cost Structure

| Service | Unit | Approximate Cost |
|---------|------|-----------------|
| Grok (grok-4-1-fast) | 1M tokens in/out | $0.20 / $0.50 |
| Z-Image Turbo | per image | ~$0.002 |
| P-Video (draft, 720p, 5s) | per video | ~$0.05 |
| Supabase | free tier | $0 |
| Mem0 | free tier | $0 |

**Per sequence** (~5 images + 1 video + Grok): ~$0.07
**Per session** (5 sequences): ~$0.35

---

## Feature Summary

| Feature | Status |
|---------|--------|
| Story generation (Grok streaming + function calling) | ✅ |
| Image generation (Z-Image Turbo, 5 per sequence) | ✅ |
| Video generation (P-Video, 1 per sequence) | ✅ |
| 6 playable characters (3 LoRA + 2 Witcher + 1 custom) | ✅ |
| 13 style moods with LoRA + prompt blocks | ✅ |
| Fullscreen cinematic UI with swipe navigation | ✅ |
| Free-text player choices | ✅ |
| Custom story settings | ✅ |
| Editable system prompt + AI modification | ✅ |
| Image regen with custom LoRAs, seed, resolution | ✅ |
| AI prompt rewriting | ✅ |
| Video regen | ✅ |
| Video simulation mode ($0) | ✅ |
| Video early start (from image 0) | ✅ |
| Supabase Auth (email/password + magic link) | ✅ |
| Session persistence (DB) | ✅ |
| Session resume | ✅ |
| Gallery mode (replay with images/videos) | ✅ |
| Admin cost dashboard | ✅ |
| Row Level Security | ✅ |
| Prompt variant saving (localStorage) | ✅ |
| Mem0 narrative memory (optional) | ✅ (experimental) |
| Detailed cost tracking per sequence | ✅ |
| Per-image generation settings in debug | ✅ |
