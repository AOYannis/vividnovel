"""xAI Text-to-Speech helpers — shared between playground & story engine."""
from __future__ import annotations
import time
import uuid
import base64
from typing import Optional

import aiohttp


SUPPORTED_VOICES = ["ara", "eve", "leo", "rex", "sal"]
SUPPORTED_LANGUAGES = [
    "auto", "en", "fr", "es-ES", "es-MX", "de", "it", "pt-BR", "pt-PT",
    "ja", "ko", "zh", "ru", "tr", "vi", "id", "hi", "bn",
    "ar-EG", "ar-SA", "ar-AE",
]


TTS_TAG_GUIDE = """xAI TTS reads the input LITERALLY — anything that isn't a recognized tag is spoken aloud,
including parentheses, asterisks, ALL CAPS, ellipses, hyphens, and stage directions.
The ONLY way to add expression is via the tags below.

INLINE TAGS — place at the exact moment the sound occurs (no wrapping):
  [pause]            short silence
  [long-pause]       longer silence
  [breath]           audible breath
  [inhale]           sharp/deep inhale
  [exhale]           audible exhale (great for tension release)
  [sigh]             a sigh
  [laugh]            short laugh
  [chuckle]          quiet amused laugh
  [giggle]           light playful laugh
  [cry]              sob / cry
  [tsk]              tongue-against-teeth disapproval
  [tongue-click]     tongue click
  [lip-smack]        lip smack
  [hum-tune]         brief hummed melody

WRAPPING TAGS — wrap the affected text:
  <soft>...</soft>                          hushed, gentle
  <whisper>...</whisper>                    quiet, intimate
  <loud>...</loud>                          raised volume
  <slow>...</slow>                          slower delivery
  <fast>...</fast>                          rapid delivery
  <higher-pitch>...</higher-pitch>          lifted pitch
  <lower-pitch>...</lower-pitch>            dropped pitch
  <build-intensity>...</build-intensity>    crescendo across the wrapped span
  <decrease-intensity>...</decrease-intensity>   diminuendo across the wrapped span
  <emphasis>...</emphasis>                  stress the wrapped word(s)
  <sing-song>...</sing-song>                playful sing-song melody
  <singing>...</singing>                    actually sung
  <laugh-speak>...</laugh-speak>            speech mixed with laughter

ABSOLUTE RULES — violate any of these and the output is broken:
1. Do NOT use parentheses (softly), asterisks *sighs*, brackets [softly], em-dashes for direction,
   or ANY stage-direction notation outside the tag list above. These will be SPOKEN LITERALLY.
2. Do NOT add narration, character names, "she said", or any words the speaker would not say.
3. Do NOT translate. Keep the source language exactly.
4. Layer tags to be expressive: combine wrapping (e.g. <whisper>) with inline (e.g. [breath], [exhale])
   to create real emotion — a flat sentence with one tag is a wasted opportunity. Aim for 3-7 tags
   in a typical 1-3 sentence prompt.
5. Match the tags to the Direction the user gave (intimate → <whisper>+[breath]+<slow>;
   building tension → <build-intensity>+[inhale]; teasing → <sing-song>+[chuckle]; etc.).
6. Output ONLY the rewritten spoken text with tags. No preamble, no explanation, no quotes around it.
"""


_DIALOGUE_RE = __import__("re").compile(r"[«\"“]([^»\"”]+)[»\"”]")


def extract_dialogue(text: str) -> str:
    """Pull out only the dialogue lines from a narration block.
    Matches French «…», curly "…", and straight \"…\" quotes.
    Returns the joined dialogue text (one line per quote), or '' if none found."""
    if not text:
        return ""
    lines = [m.group(1).strip() for m in _DIALOGUE_RE.finditer(text)]
    return "\n".join(line for line in lines if line)


_LEAK_PREFIX_RE = __import__("re").compile(
    # Use [ \t]* instead of \s* so we don't consume the trailing newline (which would
    # let .* eat the next line of real content).
    r"^[ \t]*(voice|language|direction|text|brief)[ \t]*:[ \t]*[^\n]*$",
    __import__("re").IGNORECASE | __import__("re").MULTILINE,
)


def _strip_leaked_metadata(text: str) -> str:
    """Remove any echoed 'Voice: ...', 'Language: ...', 'Direction: ...', 'Text:' lines
    that Grok occasionally repeats from the user message — they would otherwise be
    spoken aloud verbatim by xAI TTS."""
    cleaned = _LEAK_PREFIX_RE.sub("", text)
    # Collapse the blank lines we leave behind
    cleaned = __import__("re").sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


async def enhance_speech_text(
    grok_client,
    text: str,
    *,
    voice: str = "ara",
    language: str = "fr",
    brief: str = "",
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> tuple[str, float]:
    """Use Grok to rewrite plain text into an xAI-TTS-tagged expressive prompt.
    Returns (enhanced_text, elapsed_seconds).
    Voice/language are NOT included in the user message — they tend to leak back
    into the output and get spoken aloud. They're only used here for logging context."""
    start = time.time()
    sys_msg = (
        "You are a voice direction assistant. Rewrite the user's text into an "
        "expressive prompt for xAI Text-to-Speech.\n\n" + TTS_TAG_GUIDE
    )
    user_msg = ""
    if brief.strip():
        user_msg += f"Direction (do NOT echo): {brief.strip()}\n\n"
    user_msg += text.strip()

    resp = await grok_client.chat.completions.create(
        model=grok_model,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=1500,
    )
    enhanced = (resp.choices[0].message.content or "").strip()
    if enhanced.startswith("```") and enhanced.endswith("```"):
        enhanced = enhanced.strip("`").strip()
    if (enhanced.startswith('"') and enhanced.endswith('"')) or (enhanced.startswith("'") and enhanced.endswith("'")):
        enhanced = enhanced[1:-1].strip()
    # Defensive scrub in case Grok still echoes header-style metadata
    enhanced = _strip_leaked_metadata(enhanced)
    _ = (voice, language)  # acknowledged but intentionally not sent to Grok
    return enhanced, round(time.time() - start, 2)


async def generate_speech(
    runware_client,
    text: str,
    *,
    voice: str = "ara",
    language: str = "fr",
    output_format: str = "MP3",
    fetch_base64: bool = False,
    channels: Optional[int] = None,        # 1 = mono, 2 = stereo
    sample_rate: Optional[int] = None,     # 8000-48000 Hz; allowed: 8000, 16000, 22050, 24000, 44100, 48000
    bitrate: Optional[int] = None,         # 32-320 kbps (MP3 only)
) -> dict:
    """Generate speech audio via Runware xAI TTS.
    Returns: {audio_url, audio_data (data URI or None), char_count, cost, elapsed, voice, language}."""
    from runware import IAudioInference, IAudioSpeech, IAudioSettings

    if not text.strip():
        raise ValueError("text is required")

    start = time.time()
    audio_settings = None
    if channels is not None or sample_rate is not None or bitrate is not None:
        audio_settings = IAudioSettings(
            sampleRate=sample_rate,
            bitrate=bitrate,
            channels=channels,
        )
    request = IAudioInference(
        taskUUID=str(uuid.uuid4()),
        model="xai:tts@0",
        speech=IAudioSpeech(text=text, voice=voice, language=language),
        outputType="URL",
        outputFormat=output_format,
        audioSettings=audio_settings,
        includeCost=True,
        deliveryMethod="sync",
    )
    result = await runware_client.audioInference(requestAudio=request)
    audio = result[0] if isinstance(result, list) else result
    if audio is None:
        raise RuntimeError("TTS returned no audio")

    audio_url = getattr(audio, "audioURL", None) or ""
    audio_b64 = getattr(audio, "audioBase64Data", None) or ""
    cost = float(getattr(audio, "cost", 0) or 0)

    if fetch_base64 and not audio_b64 and audio_url:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(audio_url) as r:
                    audio_b64 = base64.b64encode(await r.read()).decode()
        except Exception:
            pass

    mime = {"MP3": "audio/mpeg", "WAV": "audio/wav", "FLAC": "audio/flac", "OGG": "audio/ogg"}.get(output_format, "audio/mpeg")
    return {
        "audio_url": audio_url,
        "audio_data": f"data:{mime};base64,{audio_b64}" if audio_b64 else None,
        "voice": voice,
        "language": language,
        "char_count": len(text),
        "cost": cost,
        "elapsed": round(time.time() - start, 2),
        "backend": "runware",
    }


# ─── Direct xAI TTS path ─────────────────────────────────────────────────────
# Faster than going through Runware (~2-3s less per scene) because we skip the
# extra hop and Runware's CDN-upload step. Returns raw audio bytes — no hosted
# URL, so this can't feed P-Video's inputs.audio for lip-sync.
# xAI direct does NOT expose a "channels" field, so output is whatever xAI
# defaults to (mono). Callers that need stereo must use generate_speech (Runware).

XAI_TTS_ENDPOINT = "https://api.x.ai/v1/tts"


async def generate_speech_direct_xai(
    api_key: str,
    text: str,
    *,
    voice: str = "ara",
    language: str = "en",
    output_format: str = "MP3",        # MP3 | WAV | PCM | MULAW | ALAW
    sample_rate: Optional[int] = None,  # 8000-48000 Hz
    bitrate: Optional[int] = None,      # 32-320 kbps (MP3 only — value in kbps)
    optimize_streaming_latency: int = 0,
) -> dict:
    """Generate speech directly via xAI's REST endpoint.
    Returns: {audio_url:'', audio_data: data-URI, char_count, cost:0, elapsed, voice, language, backend:'xai'}.

    The endpoint is unary — returns full bytes after generation. Cost isn't returned by xAI in the
    response body; xAI bills $4.20 / 1M characters so we compute it locally for parity with Runware.
    """
    if not api_key:
        raise ValueError("XAI_API_KEY not configured")
    if not text.strip():
        raise ValueError("text is required")

    codec = (output_format or "MP3").lower()
    output_format_obj: dict = {"codec": codec}
    if sample_rate is not None:
        output_format_obj["sample_rate"] = int(sample_rate)
    if bitrate is not None and codec == "mp3":
        # xAI takes bps, our other helper takes kbps — match the runware helper convention here
        output_format_obj["bit_rate"] = int(bitrate) * 1000

    payload = {
        "text": text,
        "voice_id": voice,
        "language": language,
        "output_format": output_format_obj,
        "optimize_streaming_latency": int(optimize_streaming_latency),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "audio/*",
    }

    start = time.time()
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(XAI_TTS_ENDPOINT, json=payload, headers=headers) as resp:
            if resp.status != 200:
                err_body = await resp.text()
                raise RuntimeError(f"xAI TTS HTTP {resp.status}: {err_body[:300]}")
            audio_bytes = await resp.read()

    if not audio_bytes:
        raise RuntimeError("xAI TTS returned empty body")

    audio_b64 = base64.b64encode(audio_bytes).decode()
    mime = {"mp3": "audio/mpeg", "wav": "audio/wav", "pcm": "audio/L16",
            "mulaw": "audio/mulaw", "alaw": "audio/alaw"}.get(codec, "audio/mpeg")
    # xAI bills per character: $4.20 per 1M chars
    cost = round(len(text) * 4.20 / 1_000_000, 6)
    return {
        "audio_url": "",
        "audio_data": f"data:{mime};base64,{audio_b64}",
        "voice": voice,
        "language": language,
        "char_count": len(text),
        "cost": cost,
        "elapsed": round(time.time() - start, 2),
        "backend": "xai",
    }


def select_speech_backend(*, prefer_url: bool, stereo: bool) -> str:
    """Pick the right TTS path:
    - 'runware' when we need a hosted URL (e.g. for P-Video lip-sync). xAI direct
      returns raw bytes only.
    - 'xai' for everything else — significantly faster (skip the Runware proxy +
      CDN-upload hop). Output is mono regardless of the `stereo` flag, which is a
      small cosmetic trade for ~3s saved per scene; the browser plays mono through
      both speakers anyway.
    """
    if prefer_url:
        return "runware"
    _ = stereo  # accepted for signature compatibility but no longer gates routing
    return "xai"
