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
    Returns (enhanced_text, elapsed_seconds)."""
    start = time.time()
    sys_msg = (
        "You are a voice direction assistant. Rewrite the user's text into an "
        "expressive prompt for xAI Text-to-Speech.\n\n" + TTS_TAG_GUIDE
    )
    user_msg = f"Voice: {voice}\nLanguage: {language}\n"
    if brief.strip():
        user_msg += f"Direction: {brief.strip()}\n"
    user_msg += f"\nText:\n{text.strip()}"

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
    return enhanced, round(time.time() - start, 2)


async def generate_speech(
    runware_client,
    text: str,
    *,
    voice: str = "ara",
    language: str = "fr",
    output_format: str = "MP3",
    fetch_base64: bool = True,
) -> dict:
    """Generate speech audio via Runware xAI TTS.
    Returns: {audio_url, audio_data (data URI or None), char_count, cost, elapsed, voice, language}."""
    from runware import IAudioInference, IAudioSpeech

    if not text.strip():
        raise ValueError("text is required")

    start = time.time()
    request = IAudioInference(
        taskUUID=str(uuid.uuid4()),
        model="xai:tts@0",
        speech=IAudioSpeech(text=text, voice=voice, language=language),
        outputType="URL",
        outputFormat=output_format,
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
    }
