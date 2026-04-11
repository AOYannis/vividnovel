"""Davinci MagiHuman video generation client.

Generates talking-head videos from images + prompts via RunPod API.
Non-blocking: submit job, poll for completion, return video URL.
"""
import asyncio
import aiohttp
import time
import os
import re

# ─── Config ──────────────────────────────────────────────────────
DAVINCI_POD_ID = os.environ.get("DAVINCI_POD_ID", "")
DAVINCI_API_KEY = os.environ.get("DAVINCI_API_KEY", "")
DAVINCI_ENABLED = bool(DAVINCI_POD_ID and DAVINCI_API_KEY)

# Video resolution presets
DAVINCI_WIDTH = 256
DAVINCI_HEIGHT = 448
DAVINCI_SECONDS = 10
DAVINCI_HD_WIDTH = 540
DAVINCI_HD_HEIGHT = 960
DAVINCI_HD_SECONDS = 5
DAVINCI_POLL_INTERVAL = 2  # seconds between polls
DAVINCI_TIMEOUT = 180  # max wait per video
DAVINCI_SUBMIT_RETRIES = 30  # max retries on 429 (one every 5s = 150s max wait)
DAVINCI_SIMULATE = os.environ.get("DAVINCI_SIMULATE", "").lower() in ("1", "true", "yes")
DAVINCI_SIMULATE_DELAY = 10  # seconds to fake loading when simulating

DAVINCI_PROMPT_SYSTEM = """You are a top-tier film director generating Enhanced Prompts for daVinci-MagiHuman, an avatar-style AI video model that excels at facial performance but requires minimal body movement.

You receive THREE inputs:
- Input 1: First-frame image — the visual anchor for the video
- Input 2: Image generation prompt — technical description used to create the image
- Input 3: Story narration — the narrative context with dialogue

Output ONLY the raw Enhanced Prompt — no headers, no numbering, no labels, no markdown.

## Generation Steps
1. Analyze the first-frame image: identify the character's actual appearance, expression, clothing, environment, lighting, and composition.
2. Extract dialogue and emotional intent from the narration.
3. Integrate both into a single Enhanced Prompt following the format below.

## Output Format — 3 paragraphs separated by a blank line:

### PARAGRAPH 1 — Main Body (150-200 words, ALWAYS in English)
Follow this strict structure:
- **Initial State:** One sentence establishing the character's appearance (from the IMAGE, not the text prompt) and surroundings, plus their overall emotional disposition. The disposition MUST match the tone of what the character is about to say — if the dialogue is anxious, the initial state should reflect tension, not seduction.
- **Chronological Audio-Visual Narrative:** Narrate all events in strict time order. The character's torso and global position must remain STATIONARY throughout. Integrate dialogue at the exact moment it occurs.
- **Facial Dynamics:** The facial expression MUST match the EMOTIONAL CONTENT of the dialogue.
  If the character says something urgent/anxious → furrowed brows, tightened jaw, widened eyes, pursed lips. NOT a smirk.
  If the character says something seductive → heavy-lidded eyes, parted lips, slight head tilt. NOT wide-eyed surprise.
  If the character says something playful → raised brows, asymmetric smile, crinkled eyes. NOT a neutral stare.
  FIRST determine the emotion from the dialogue, THEN describe the matching muscle movements.
  Detail specific muscles: raising of outer brows, tightening of lip corners, wrinkling of the nose, parting of lips.
  Name the expression (smirk, grimace, pout, scowl) ONLY if it matches what's being said.
- **Body Kinematics:** Only head angle shifts, shoulder tension, micro-gestures. NO significant physical displacement or large limb movements. If hands are not visible in the image, do NOT describe hand movements.
- **Speech Integration:** When dialogue occurs, follow this exact pattern:
  1. Describe the vocal delivery FIRST (tone, pace, pitch, volume) in natural language
  2. Then the quoted dialogue line in its original language
  3. Then describe the lip and jaw mechanics for lip-sync AFTER
  Example: "She speaks in a low, husky tone with slow deliberate pace, mid-low pitch, and breathy volume, "Viens ici, Yannis..." — jaw drops with precise phonetic syncing, lower lip protrudes and rounds, lips seal and part rhythmically."
  Do NOT bury the vocal delivery inside a long technical sentence. Keep it as a clear, standalone cue that Davinci can interpret.
- **Action Downscaling:** Convert any large-scale actions from the narration into stationary micro-movements (e.g., "dancing" → "subtle rhythmic sway of shoulders").
- **Cinematography:** Describe camera angle and shot distance. Camera must be STATIC — no following, orbiting, zooming, or cutting. Describe lighting quality and direction. Depth of field focused sharply on facial features.
- **Environment:** Background must remain largely rigid. Avoid describing background elements in motion.
- The language must be CLINICAL and devoid of interpretation. No metaphors or narrative frames.

### PARAGRAPH 2 — Dialogue
Must begin with "Dialogue:" then:
<5-word character description, spoken language>: "dialogue content"
- Extract ONLY the spoken words from the narration (text inside « », " ", or quotes).
- Do NOT include narration, action descriptions, or stage directions in the dialogue. Only the words the character actually says out loud.
- The dialogue must be SHORT — maximum 15 words. If the narration has a longer quote, extract only the most impactful phrase or shorten it.
- Keep dialogue in its ORIGINAL language — do not translate.
- If no dialogue exists, infer a fitting short line (<20 words) or use a reaction sound like "(soft sigh)".
- If emotional tone is not specified, infer from context.
- The video is 10 seconds — the dialogue must be deliverable naturally within that time.

### PARAGRAPH 3 — Background Sound
Must begin with "Background Sound:" then:
<description of the most prominent background sound> (between angle brackets)
- This should be CINEMATIC — think film soundtrack. Include ambient music where appropriate:
  * Romantic/sensual scenes → soft jazz piano, breathy saxophone, lo-fi beats
  * Tense/thriller scenes → low droning strings, heartbeat pulse
  * Elegant/luxury scenes → classical strings, soft harp
  * Urban night scenes → distant city hum, muffled bass from nearby club
  * Nature scenes → wind, birds, water — layered with subtle atmospheric music
- If no sound fits, use: <No prominent background sound>

## Critical Rules
- Ignore LoRA trigger words in the image prompt (N@t@ly, b10ndi, sh0r7y_asian, wh1te, k0r3an, woman041, blond0lga) — these are meaningless technical tokens.
- Ignore image-gen jargon (Shot on, depth of field, film grain, Portra Film Photo, POV first-person, etc.).
- Dialogue appears TWICE: woven chronologically in the main body AND repeated in the Dialogue section.
- Base your physical description on the IMAGE you see, not the text prompt. The image is the ground truth.
- WORD COUNT: The main body paragraph MUST be strictly 150-200 words. Count your words. If you exceed 200, cut less important details. If under 150, add more facial dynamics. Do NOT include the word count in the output (no "(178 words)" annotations).
- DIALOGUE LENGTH: Maximum 20 words in the Dialogue section. Extract only the spoken words, never narration. The video is 10 seconds — the character must say it naturally in that time. If the narration dialogue is longer, extract only the most impactful phrase.
- NO-CHARACTER IMAGES: Look at the image carefully. If there is NO clearly visible human face in the frame (establishing shots, landscapes, object close-ups), you MUST NOT invent or hallucinate a character. Do NOT describe anyone "entering the frame" or "appearing from off-screen". Describe only what is VISIBLE: the environment with subtle motion (candle flicker, light shifts, vapor trails, reflections, rain streaks). Use "(ambient silence)" for dialogue. Do NOT add facial dynamics, speech, or body kinematics. The narration may mention characters but if you cannot SEE a face in the image, ignore the narration's character references entirely.
- Do NOT include any meta-commentary, annotations, or word counts in the output. Output only the 3-paragraph Enhanced Prompt.

example of good prompt : 

A young man with short, dark hair and a neatly trimmed beard, wearing a bright yellow polo shirt, sits in a stationary position. His disposition is earnest and slightly agitated, but his torso remains completely still within the frame. He maintains a fixed posture as he prepares to speak. The scene is captured in a static medium close-up shot, focusing on his upper torso and face. He speaks with a rapid, slightly high-pitched, and emphatic tone, his mouth opening wide to articulate each word with precision, his brow furrowing slightly as he says, "有 的 人 在 一 起 生 活 一 辈 子，还 带 着 假 面 具 呢，比 如 说 你 十 年 了。" His eyes are wide and fixed toward the right, conveying a sense of frustration. The lip muscles show distinct dynamics as he articualtes the CJK characters. As he finishes the sentence, his voice abruptly cuts off, and a sudden, sharp, high-pitched electronic screech pierces the air. The background remains a static, blurred dark blue scene throughout the performance.

Dialogue: <Young man in yellow polo, Mandarin>: "有 的 人 在 一 起 生 活 一 辈 子，还 带 着 假 面 具 呢，比 如 说 你 十 年 了。"

Background Sound: <A sudden, sharp, high-pitched electronic screech>

"""


def _base_url():
    return f"https://{DAVINCI_POD_ID}-8888.proxy.runpod.net"


async def check_status() -> dict | None:
    """Check if the Davinci API is reachable and warm."""
    if not DAVINCI_ENABLED:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_base_url()}/status",
                headers={"X-Api-Key": DAVINCI_API_KEY},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


async def generate_scene_video(
    image_url: str,
    davinci_prompt: str,
    seconds: int = DAVINCI_SECONDS,
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    """Submit a video generation job and poll until complete.

    Args:
        image_url: URL of the source image
        davinci_prompt: Full 3-section Davinci prompt
        seconds: Video duration (default 5)
        seed: Generation seed (None for random)

    Returns:
        {"video_url": str, "duration": float, "job_id": str}
    """
    if DAVINCI_SIMULATE:
        print(f"[davinci] SIMULATE mode — waiting {DAVINCI_SIMULATE_DELAY}s...")
        await asyncio.sleep(DAVINCI_SIMULATE_DELAY)
        return {
            "video_url": "simulated",
            "video_bytes": b"",  # empty — frontend will show placeholder
            "duration": DAVINCI_SIMULATE_DELAY,
            "job_id": "sim-" + str(int(time.time())),
            "generation_time": DAVINCI_SIMULATE_DELAY,
            "simulated": True,
        }

    base = _base_url()
    headers = {"X-Api-Key": DAVINCI_API_KEY}

    # Auto-detect if API is reachable — fallback to simulate if pod is down
    try:
        async with aiohttp.ClientSession() as probe:
            async with probe.get(f"{base}/status", headers=headers, timeout=aiohttp.ClientTimeout(total=5)):
                pass
    except Exception:
        print(f"[davinci] API unreachable at {base} — auto-simulating ({DAVINCI_SIMULATE_DELAY}s)")
        await asyncio.sleep(DAVINCI_SIMULATE_DELAY)
        return {
            "video_url": "simulated",
            "video_bytes": b"",
            "duration": DAVINCI_SIMULATE_DELAY,
            "job_id": "sim-" + str(int(time.time())),
            "generation_time": DAVINCI_SIMULATE_DELAY,
            "simulated": True,
        }

    async with aiohttp.ClientSession() as session:
        # Download the source image
        async with session.get(image_url) as img_resp:
            if img_resp.status != 200:
                raise Exception(f"Failed to download image: {img_resp.status}")
            image_data = await img_resp.read()
            content_type = img_resp.headers.get("Content-Type", "image/webp")

        # Submit generation job (with 429 retry)
        start = time.time()
        job_id = None
        for attempt in range(DAVINCI_SUBMIT_RETRIES):
            # Rebuild FormData each attempt (aiohttp consumes it)
            form = aiohttp.FormData()
            form.add_field("prompt", davinci_prompt)
            form.add_field("image", image_data, filename="scene.webp", content_type=content_type)
            form.add_field("seconds", str(seconds))
            form.add_field("br_width", str(width or DAVINCI_WIDTH))
            form.add_field("br_height", str(height or DAVINCI_HEIGHT))
            if seed is not None:
                form.add_field("seed", str(seed))

            async with session.post(
                f"{base}/generate",
                headers=headers,
                data=form,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    submit_data = await resp.json()
                    job_id = submit_data["job_id"]
                    break
                elif resp.status == 429:
                    # Server busy — wait and retry
                    print(f"[davinci] Server busy (429), retry {attempt + 1}/{DAVINCI_SUBMIT_RETRIES}...")
                    await asyncio.sleep(5)
                    continue
                else:
                    error = await resp.text()
                    raise Exception(f"Davinci submit failed ({resp.status}): {error}")
        if job_id is None:
            raise Exception(f"Davinci submit failed: server busy after {DAVINCI_SUBMIT_RETRIES} retries")

        # Poll for completion
        deadline = time.time() + DAVINCI_TIMEOUT
        poll_failures = 0
        while time.time() < deadline:
            await asyncio.sleep(DAVINCI_POLL_INTERVAL)
            try:
                async with session.get(
                    f"{base}/generate/{job_id}",
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        poll_failures += 1
                        if poll_failures > 3:
                            raise Exception(f"Davinci poll failed {poll_failures}x (last: {resp.status})")
                        continue
                    data = await resp.json()
            except (aiohttp.ContentTypeError, Exception) as e:
                poll_failures += 1
                if poll_failures > 3:
                    raise Exception(f"Davinci poll error: {e}")
                continue
            poll_failures = 0  # reset on success
            if data.get("status") == "completed":
                elapsed = round(time.time() - start, 1)
                video_path = data["video_url"]
                async with session.get(
                    f"{base}{video_path}",
                    headers=headers,
                ) as vid_resp:
                    video_bytes = await vid_resp.read()
                return {
                    "video_url": f"{base}{video_path}",
                    "video_bytes": video_bytes,
                    "duration": elapsed,
                    "job_id": job_id,
                    "generation_time": data.get("duration_seconds", elapsed),
                }
            elif data.get("status") == "failed":
                raise Exception(f"Davinci generation failed: {data.get('error', 'unknown')}")

        raise Exception(f"Davinci timeout after {DAVINCI_TIMEOUT}s")


async def build_davinci_prompt(
    image_prompt: str,
    narration: str,
    character_name: str = "a young woman",
    language: str = "French",
    image_url: str | None = None,
) -> str:
    """Convert a Z-Image prompt + narration into a Davinci Enhanced Prompt via Grok vision.

    Sends the generated image + text context to Grok so it can describe
    what's actually in the frame with clinical precision.
    """
    from openai import AsyncOpenAI
    from config import XAI_API_KEY, GROK_BASE_URL

    text_part = (
        f"Image generation prompt (for context, but prefer what you SEE in the image):\n"
        f"{image_prompt}\n\n"
        f"Story narration for this scene:\n{narration}\n\n"
        f"Character: {character_name}\n"
        f"Spoken language: {language}"
    )

    # Build user message with vision if image URL available
    if image_url:
        user_content = [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": text_part},
        ]
    else:
        user_content = text_part

    try:
        client = AsyncOpenAI(api_key=XAI_API_KEY, base_url=GROK_BASE_URL)
        resp = await client.chat.completions.create(
            model="grok-4-1-fast-non-reasoning",
            messages=[
                {"role": "system", "content": DAVINCI_PROMPT_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        result = resp.choices[0].message.content.strip()
        # Strip any word count annotations Grok might add (e.g. "(178 words)")
        result = re.sub(r'\s*\(\d+\s*words?\)\s*', '', result)
        print(f"[davinci] Prompt generated via Grok vision ({len(result)} chars)")
        return result
    except Exception as e:
        print(f"[davinci] Grok prompt generation failed: {e} — using raw image prompt")
        # Minimal fallback
        desc = image_prompt
        for tw in ["N@t@ly", "sh0r7y_asian", "b10ndi", "k0r3an", "woman041", "wh1te", "blond0lga"]:
            desc = desc.replace(f"{tw}, ", "").replace(tw, "")
        desc = re.sub(r'Shot on .*$', '', desc, flags=re.DOTALL).strip()
        return f"{desc}\n\nDialogue:\n<{character_name}, {language}>: \"(soft exhale)\"\n\nBackground Sound:\n<No prominent background sound>"
