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
1. Wrapping tags MUST be written as `<tag>text</tag>`. NEVER as `[soft]`, `[whisper]`, `[loud]`,
   `[slow]`, `[fast]`, `[emphasis]` etc. — those are not valid inline tags and will be SPOKEN.
2. Every `<tag>` you open MUST have a matching `</tag>` before the end of the output.
3. Never nest the same tag inside itself (no `<soft>...<soft>...</soft>...</soft>`).
4. NEVER use markdown: no `*word*`, no `**word**`, no `_word_`, no `# headings`.
5. NEVER use parentheses for direction: no `(softly)`, no `(she whispers)`.
6. NEVER write character names, "she said", "he replied", scene titles, or anything that isn't
   the actual sound to be voiced.
7. NEVER translate. Keep the source language verbatim.
8. Output ONLY the spoken text with tags. No preamble, no quotes around the whole thing.

═══ EXPRESSION PALETTE — use sparingly and CONTEXTUALLY ═══
Treat tags like spice: the right amount makes the dish; too much ruins it. Restraint > density.

NARRATOR PROSE (description, action, between dialogues):
  • Default tone: dry voice, minimal tagging. Most narrative sentences need NO tags at all.
  • Wrap a whole prose clause in <soft>...</soft> when the moment is intimate, tender, or hushed.
  • Use <whisper>...</whisper> ONLY for genuinely whispered narration (rare — confidential, secretive).
  • One [pause] at most per prose sentence, only where a real beat exists in the storytelling.
  • Avoid [breath], [inhale], [exhale], [sigh] in pure narration — those are character sounds, not narrator sounds.
  • Avoid <slow>, <fast>, <higher-pitch>, <lower-pitch>, <emphasis>, <sing-song>, <singing>,
    <laugh-speak>, [laugh], [chuckle], [giggle], [cry], [tsk], [lip-smack], [hum-tune] in narration.

DIALOGUES (text inside quotes — what a character actually says):
  • Richer expression is welcome — match the speaker's emotion.
  • Whispered, intimate line → <whisper>...</whisper> around the whole line, optional [breath] at start.
  • Confident, loud line → <loud>...</loud> or <build-intensity>...</build-intensity>.
  • Teasing, playful → <sing-song>...</sing-song> or [chuckle] / [giggle] at appropriate beats.
  • Amused while talking → wrap in <laugh-speak>...</laugh-speak>.
  • Stress one key word with <emphasis>word</emphasis> — at most one per dialogue line.
  • Hesitation, thinking → [pause] mid-sentence, optionally [breath].
  • Sad / breaking → <soft>...</soft>, [sigh] or [cry] only if the line truly demands it.

═══ DENSITY GUIDE ═══
For a typical scene (2-4 sentences, mix of narration + 1 dialogue line):
  • 0-2 tags total in the narration prose.
  • 2-4 tags inside the dialogue (one wrapping tag + 1-2 inline beats + at most one <emphasis>).
  • Match the Direction (if provided) by choosing tags that fit the emotional brief — but never
    use a tag just because the Direction mentioned a feeling; only use it if the *delivery* genuinely calls for it.

═══ ANTI-PATTERNS — these are the failures we keep seeing, do NOT do them ═══
  • `<slow>; </slow>` (wrapping a single semicolon — pointless)
  • `<soft><slow>...whole paragraph...</soft>` (mismatched closing — ALWAYS close in reverse-open order)
  • `[loud]` or `[whisper]` or `[soft]` (bracket form for wrapping tags — invalid)
  • `*thump*` or `**Scene 2:**` (markdown — will be spoken literally)
  • Using <emphasis> on every other word (loses meaning — stress one word per dialogue at most)
  • Adding [breath] or [exhale] before every sentence (sounds asthmatic)
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
            # Opening tag
            if name in stack:
                # Already open — drop the duplicate open (no nesting same tag)
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


async def enhance_speech_text(
    grok_client,
    text: str,
    *,
    voice: str = "ara",
    language: str = "fr",
    brief: str = "",
    grok_model: str = "grok-4-1-fast-non-reasoning",
) -> tuple[str, float, dict]:
    """Use Grok to rewrite plain text into an xAI-TTS-tagged expressive prompt.
    Returns (enhanced_text, elapsed_seconds, usage_dict).
    `usage_dict` is `{"input_tokens": int, "output_tokens": int, "cached_tokens": int}` —
    used by callers to roll the enhance cost into per-sequence totals.
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
