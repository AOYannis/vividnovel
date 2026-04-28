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
including parentheses, asterisks, ALL CAPS, ellipses, hyphens, em-dashes, markdown,
and stage directions. The ONLY way to add expression is via the tags below.

INLINE TAGS — single token, no wrapping. Place at the exact moment the sound occurs:
  [pause] [long-pause]
  [breath] [inhale] [exhale] [sigh]
  [laugh] [chuckle] [giggle] [cry]
  [tsk] [tongue-click] [lip-smack] [hum-tune]

WRAPPING TAGS — MUST wrap text with both opening and closing tag, like XML:
  <soft>text</soft>      <whisper>text</whisper>      <loud>text</loud>
  <slow>text</slow>      <fast>text</fast>
  <higher-pitch>text</higher-pitch>     <lower-pitch>text</lower-pitch>
  <build-intensity>text</build-intensity>     <decrease-intensity>text</decrease-intensity>
  <emphasis>text</emphasis>     <sing-song>text</sing-song>
  <singing>text</singing>     <laugh-speak>text</laugh-speak>

═══ SYNTAX RULES (violation = the tag name is spoken aloud) ═══
1. Wrapping tags MUST be written as `<tag>text</tag>`. NEVER as `[soft]`, `[whisper]`, etc.
2. Every `<tag>` you open MUST have a matching `</tag>`.
3. Never nest the same tag inside itself.
4. **NEVER STACK / NEST DIFFERENT WRAPPING TAGS around the same text.** xAI TTS
   does not handle nested wrapping tags reliably — the inner tag name gets
   spoken aloud as a literal word ("slow", "soft", "lower-pitch"). Pick the
   ONE most-impactful tag for each clause. Never write
   `<soft><slow>text</slow></soft>` — pick `<soft>text</soft>` or
   `<slow>text</slow>` alone.
5. NEVER use markdown, stage directions, or character names.

═══ EXPRESSION PALETTE — SENSUAL ROMANCE / NSFW FOCUS ═══
Treat tags like a lover’s touch: the right amount feels heavenly; too much feels forced.
Pick ONE wrapping tag per sentence/clause — never stack them.

NARRATOR PROSE (context narration for romance/NSFW stories):
  • Default tone: warm, velvety, intimate, and seductive — like a lover whispering the story directly into the listener’s ear.
  • Use ONE of <slow>, <soft>, or <lower-pitch> per sentence — the one that fits
    best. Vary across sentences; never stack two of them on the same clause.
  • For intimate or erotic moments: prefer <whisper>...</whisper> alone, OR
    <soft>...</soft> alone. Pick ONE.
  • Breath sounds are allowed but SPARINGLY and only at natural emotional peaks:
    → [inhale] or [breath] when tension builds
    → [exhale] or [sigh] after a particularly charged moment
    → NEVER put [breath], [exhale], or [sigh] at the end of every sentence.
    - NEVER use "lower pitch" as words — use the tag <lower-pitch>...</lower-pitch>.
  • Use <whisper> only for the most confidential or highly erotic inner thoughts.
  • Use [pause] or [long-pause] for delicious tension between actions.

DIALOGUES (text inside quotes):
  • Much richer expression allowed — make it feel alive and aroused.
  • Intimate/sexy line → <whisper>...</whisper> alone (don't combine with anything).
  • Passionate line → <build-intensity>...</build-intensity> OR <emphasis>...</emphasis>
  • Teasing/playful → <sing-song>...</sing-song> or [chuckle]
  • One [breath]/[sigh] per line max, placed naturally.

═══ ANTI-PATTERNS — DO NOT DO THESE ═══
  • STACKING wrapping tags ("<soft><slow>...</slow></soft>") — the inner tag is spoken aloud.
  • Adding [breath] or [exhale] at the end of every narration sentence.
  • Over-tagging every single sentence with breath sounds.
  • Using <slow> on single words instead of whole clauses.
  • Putting breathing tags in every prose sentence.
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


# Walks the text and returns ordered segments tagged narration vs dialogue.
# Anything inside «», "", "" is dialogue; the rest is narration prose.
# Empty / whitespace-only segments are dropped.
_SEGMENT_RE = __import__("re").compile(r"([«\"“][^»\"”]+[»\"”])")


def parse_speech_segments(text: str) -> list[dict]:
    """Split a scene text into ordered segments for multi-voice TTS.

    Each segment is `{"kind": "narration" | "dialogue", "text": str}`. Dialogue
    text has the surrounding quotes stripped. Order is preserved so the caller
    can synthesise each part with its own voice and concatenate.
    """
    if not text or not text.strip():
        return []
    out: list[dict] = []
    for chunk in _SEGMENT_RE.split(text):
        if not chunk:
            continue
        if _SEGMENT_RE.fullmatch(chunk):
            inner = chunk[1:-1].strip()
            if inner:
                out.append({"kind": "dialogue", "text": inner})
        else:
            stripped = chunk.strip()
            if stripped:
                out.append({"kind": "narration", "text": stripped})
    return out


_TRAILING_PAUSE_RE = __import__("re").compile(r"(?:\s*\[(?:pause|long-pause|breath)\])+\s*$")
_LEADING_PAUSE_RE = __import__("re").compile(r"^\s*(?:\[(?:pause|long-pause|breath)\]\s*)+")


def dedupe_boundary_pauses(segments_text: list[str]) -> list[str]:
    """When neighbouring segments end / start with [pause]-style tokens, the MP3
    concat plays them as a double pause that feels like an audio glitch. Walk the
    list and trim trailing pauses on a segment if the next one starts with one.
    Returns a new list of the same length."""
    if not segments_text:
        return segments_text
    out = list(segments_text)
    for i in range(len(out) - 1):
        next_text = out[i + 1] or ""
        if _LEADING_PAUSE_RE.match(next_text):
            out[i] = _TRAILING_PAUSE_RE.sub("", out[i] or "")
    return out


def concat_audio_chunks(chunks: list[bytes], output_format: str = "MP3") -> bytes:
    """Concatenate raw audio bytes. For MP3, naive frame concat works in browsers
    when all chunks share the same encoder settings (xAI TTS does). For WAV we
    keep the first header and skip subsequent ones (44-byte RIFF). For anything
    else we fall back to naive concat — caller's responsibility to keep formats
    consistent across chunks.
    """
    if not chunks:
        return b""
    if len(chunks) == 1:
        return chunks[0]
    fmt = (output_format or "MP3").upper()
    if fmt == "WAV":
        # Keep the first 44-byte RIFF header, strip headers off subsequent chunks,
        # then patch the data-size + RIFF-size in the first header. xAI returns
        # standard WAV with a 44-byte header; we don't need to handle the LIST chunk.
        first = chunks[0]
        body = b"".join(c[44:] if len(c) > 44 else c for c in chunks)
        # Patch sizes
        import struct
        new_data_size = len(first) - 44 + len(body) - (len(chunks[0]) - 44)
        new_data_size = sum(len(c) - 44 for c in chunks)
        new_riff_size = 36 + new_data_size
        header = bytearray(first[:44])
        struct.pack_into("<I", header, 4, new_riff_size)
        struct.pack_into("<I", header, 40, new_data_size)
        return bytes(header) + body
    # MP3 (and fallback) — naive byte concat. Browsers handle multi-stream MP3.
    return b"".join(chunks)


import re as _re


_LEAK_PREFIX_RE = _re.compile(
    # Use [ \t]* instead of \s* so we don't consume the trailing newline (which would
    # let .* eat the next line of real content).
    r"^[ \t]*(voice|language|direction|text|brief)[ \t]*:[ \t]*[^\n]*$",
    _re.IGNORECASE | _re.MULTILINE,
)


def _strip_leaked_metadata(text: str) -> str:
    """Remove any echoed 'Voice: ...', 'Language: ...', 'Direction: ...', 'Text:' lines
    that Grok occasionally repeats from the user message — they would otherwise be
    spoken aloud verbatim by xAI TTS."""
    cleaned = _LEAK_PREFIX_RE.sub("", text)
    # Collapse the blank lines we leave behind
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


# Canonical tag sets — must match the prompt guide above.
INLINE_TTS_TAGS = frozenset({
    "pause", "long-pause", "breath", "inhale", "exhale", "sigh",
    "laugh", "chuckle", "giggle", "cry",
    "tsk", "tongue-click", "lip-smack", "hum-tune",
})
WRAPPING_TTS_TAGS = frozenset({
    "soft", "whisper", "loud", "slow", "fast",
    "higher-pitch", "lower-pitch",
    "build-intensity", "decrease-intensity",
    "emphasis", "sing-song", "singing", "laugh-speak",
})

_BRACKET_TAG_RE = _re.compile(r"\[([a-zA-Z][a-zA-Z\-]*)\]")
_XML_TAG_RE = _re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z\-]*)\s*[^>]*?(/?)\s*>")
# Markdown emphasis to strip (keep inner text). Avoid \\* characters in code points.
_MD_BOLD_RE = _re.compile(r"\*\*([^*\n]+?)\*\*")
_MD_ITALIC_RE = _re.compile(r"(?<![\\*])\*([^*\n]+?)\*(?!\*)")
_MD_BOLD_U_RE = _re.compile(r"__([^_\n]+?)__")
_MD_ITALIC_U_RE = _re.compile(r"(?<![\w_])_([^_\n]+?)_(?![\w_])")


def _sanitize_tts_tags(text: str) -> str:
    """Defensive scrub for malformed Grok output before sending to xAI TTS.

    Fixes the recurring failure modes seen in production logs:
      1. Markdown emphasis (`*foo*`, `**foo**`, `_foo_`, `__foo__`) — strip the markers, keep text.
      2. Bracket-form of wrapping tags (`[soft]`, `[whisper]`, `[loud]`, etc.) — drop them
         (xAI would speak the tag name as a word).
      3. Unknown bracket tokens that aren't valid inline tags — drop.
      4. Balance wrapping tags: drop orphan closing tags, auto-close orphan opening tags.
    Inline tags + valid wrapping pairs pass through unchanged.
    """
    if not text:
        return ""

    # 1. Strip markdown emphasis markers
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_BOLD_U_RE.sub(r"\1", text)
    text = _MD_ITALIC_U_RE.sub(r"\1", text)

    # 2 & 3. Replace bracket tokens: keep valid inline tags as-is, drop everything else
    def _bracket_repl(m: "_re.Match[str]") -> str:
        name = m.group(1).lower()
        if name in INLINE_TTS_TAGS:
            return f"[{name}]"
        return ""  # drop misused bracket tokens — silent rather than spoken
    text = _BRACKET_TAG_RE.sub(_bracket_repl, text)

    # 4. Walk XML tags, balance wrapping pairs, drop orphans
    out: list[str] = []
    stack: list[str] = []
    pos = 0
    for m in _XML_TAG_RE.finditer(text):
        out.append(text[pos:m.start()])
        is_close = m.group(1) == "/"
        name = m.group(2).lower()
        is_self_close = m.group(3) == "/"

        if name not in WRAPPING_TTS_TAGS:
            # Unknown XML tag — drop silently (rather than read aloud)
            pos = m.end()
            continue

        if is_self_close:
            # Self-closing wrapping tag is meaningless — drop
            pos = m.end()
            continue

        if is_close:
            if name in stack:
                # Auto-close any inner tags first (reverse-order)
                while stack and stack[-1] != name:
                    out.append(f"</{stack.pop()}>")
                # Now pop the matching one
                if stack and stack[-1] == name:
                    out.append(f"</{stack.pop()}>")
            # else: orphan closing — drop silently
        else:
            # Opening tag — flatten: at most ONE wrapping tag at a time.
            # xAI TTS does not handle nested wrapping tags reliably (it speaks the
            # inner tag name aloud as a literal word), so when ANY tag is already
            # on the stack we drop this new opening (and its eventual closer will
            # be silently ignored as an "orphan").
            if stack:
                # Already inside a wrapping tag — drop this nested open
                pass
            else:
                stack.append(name)
                out.append(f"<{name}>")
        pos = m.end()
    out.append(text[pos:])

    # Auto-close any leftover open wrapping tags
    while stack:
        out.append(f"</{stack.pop()}>")

    # Cleanup: collapse extra spaces left by tag drops
    result = "".join(out)
    result = _re.sub(r"[ \t]{2,}", " ", result)
    result = _re.sub(r"\s+([,.!?;:])", r"\1", result)  # drop space before punctuation
    return result.strip()


_MODE_BRIEFS = {
    "narration": (
        "MODE = SENSUAL NARRATION (third-person voice-over for romance/NSFW stories).\n"
        "- Style: warm, velvety, luxurious, and deeply intimate — like a lover telling the story in a candlelit bedroom.\n"
        "- Delivery must feel slow, soft, and husky throughout the entire narration.\n"
        "- Use gentle pauses for tension and very subtle breath sounds only at natural emotional peaks.\n"
        "- Keep everything elegant and seductive — never robotic or overdone.\n"
        "- ⚠️ Pick ONLY ONE wrapping tag per sentence (one of <slow>, <soft>, "
        "<lower-pitch>, <whisper>). NEVER stack two of them around the same text — "
        "xAI TTS reads the inner tag name aloud as a literal word."
    ),
    "dialogue": (
        "MODE = DIALOGUE (a character speaking out loud, in scene).\n"
        "- Make the delivery match the emotion: seductive, aroused, teasing, or passionate.\n"
        "- Allow natural breath and intensity changes that feel real and erotic.\n"
        "- ⚠️ Pick ONLY ONE wrapping tag per line. NEVER stack two."
    ),
}


async def enhance_speech_text(
    grok_client,
    text: str,
    *,
    voice: str = "ara",
    language: str = "fr",
    brief: str = "",
    mode: str = "dialogue",
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> tuple[str, float, dict]:
    """Use Grok to rewrite plain text into an xAI-TTS-tagged expressive prompt.
    Returns (enhanced_text, elapsed_seconds, usage_dict).
    `usage_dict` is `{"input_tokens": int, "output_tokens": int, "cached_tokens": int}` —
    used by callers to roll the enhance cost into per-sequence totals.
    `mode` selects the direction style — "narration" (slower, breathier, restrained)
    vs "dialogue" (conversational, expressive). Default is "dialogue" so existing
    callers (single-voice path) keep their old behaviour.
    Voice/language are NOT included in the user message — they tend to leak back
    into the output and get spoken aloud. They're only used here for logging context."""
    start = time.time()
    mode_brief = _MODE_BRIEFS.get(mode, _MODE_BRIEFS["dialogue"])
    sys_msg = (
        "You are an expert sensual voice director for romantic and NSFW stories. "
        "Your ONLY job is to output clean, ready-to-speak text with correct xAI TTS tags. "
        "Never write the word 'slow', 'soft', 'whisper', or any tag name as plain text. "
        "Always convert style instructions into proper XML-style tags. "
        "Output NOTHING except the final tagged speech text.\n\n"
        + mode_brief + "\n\n"
        + TTS_TAG_GUIDE
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
    # Defensive scrubs against the recurring failure modes we see in production:
    # 1. Header-style metadata leak (Voice:/Language:/Direction:/Text:)
    # 2. Markdown emphasis (*foo*, **foo**), bracket-form wrapping tags ([loud]),
    #    orphan/unbalanced wrapping tags — all of which xAI TTS would speak literally
    enhanced = _strip_leaked_metadata(enhanced)
    enhanced = _sanitize_tts_tags(enhanced)
    _ = (voice, language)  # acknowledged but intentionally not sent to Grok

    # Capture token usage for cost accounting
    usage = getattr(resp, "usage", None)
    usage_dict = {
        "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        "cached_tokens": (
            getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        ) if usage else 0,
    }
    return enhanced, round(time.time() - start, 2), usage_dict


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
