"""Grok function calling tool definitions."""

from config import IMAGES_PER_SEQUENCE

# ─── Phase 3A — lean narrator schema ─────────────────────────────────────────
# The narrator no longer writes the image prompt itself. It emits a SHORT scene
# spec (summary + camera intent + mood name + visible actors). A specialist
# agent (`scene_agent.craft_image_prompt`) turns that spec into the actual
# Z-Image Turbo prompt at runtime. This keeps the narrator's system prompt
# small and focused on storytelling — image rules live in scene_agent.py.
SCENE_IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_scene_image",
        "description": (
            "Generate the image for the CURRENT scene. Call ONCE per scene, AFTER writing "
            "1-2 short sentences of stage direction + character dialogue. "
            "You DO NOT write the image prompt — a specialist agent composes it from your "
            "scene_summary + shot_intent + mood + actors_present. Just describe WHAT "
            "happens; the specialist owns POV, lighting, camera, and skin-realism keywords. "
            "Always pass actors_present (LoRA loading depends on it)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_index": {
                    "type": "integer",
                    "description": f"Scene number in this sequence (0-{IMAGES_PER_SEQUENCE - 1})",
                    "enum": list(range(IMAGES_PER_SEQUENCE)),
                },
                "scene_summary": {
                    "type": "string",
                    "description": (
                        "1-2 sentences describing what is HAPPENING in this 10-second beat: "
                        "who is doing what, body language, key emotion. Plain prose, in the "
                        "narration language. NO camera direction, NO lighting words — just "
                        "the action. Example: \"She leans across the bar, voice low, fingers "
                        "tracing the rim of her glass while she watches you.\""
                    ),
                },
                "shot_intent": {
                    "type": "string",
                    "description": (
                        "1 short line of camera/tone hint for the image specialist. "
                        "Examples: 'intimate close-up, warmth', 'wide atmospheric establishing shot, "
                        "rainy street', 'over-the-shoulder, tense', 'extreme macro of two hands'. "
                        "Optional but strongly recommended — it steers the shot type."
                    ),
                },
                "mood": {
                    "type": "string",
                    "description": (
                        "ONE canonical mood name. Use 'neutral' for normal scenes (conversations, "
                        "atmosphere, daily life). Use a specific mood name for intimate/sexual "
                        "scenes — pick the SPECIFIC position when one fits "
                        "(kiss, sensual_tease, blowjob, cunnilingus, missionary, doggystyle, "
                        "cowgirl, etc.). The available moods and the relationship-level gating "
                        "are explained in the system prompt."
                    ),
                },
                "actors_present": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "CRITICAL: codenames of cast members visible in this image. "
                        "Use the EXACT codenames from the cast (e.g. 'nataly', 'shorty_asian'). "
                        "This list controls which character LoRAs are loaded — omitting a "
                        "character makes their face look WRONG. Empty array [] is correct ONLY "
                        "for atmospheric shots with no cast member visible."
                    ),
                },
                "character_names": {
                    "type": "object",
                    "description": (
                        "Map cast codenames to the STORY NAMES used in the narration. "
                        "E.g. {'nataly': 'Nathalie', 'shorty_asian': 'Mei'}. "
                        "Include this on EVERY call so the system locks each name to its actor."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "location_description": {
                    "type": "string",
                    "description": (
                        "Brief location tag for cross-scene continuity (e.g. 'candlelit hotel "
                        "room with velvet curtains'). Copy IDENTICALLY from the previous scene "
                        "if the location is unchanged."
                    ),
                },
                "clothing_state": {
                    "type": "object",
                    "description": (
                        "Current clothing per visible cast member, keyed by codename. "
                        "Each character has their OWN clothing — never copy one character's "
                        "outfit onto another. Copy IDENTICALLY from the previous scene unless "
                        "the narrative just changed that character's clothing."
                    ),
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": [
                "image_index",
                "scene_summary",
                "actors_present",
                "mood",
            ],
        },
    },
}

CHOICES_TOOL = {
    "type": "function",
    "function": {
        "name": "provide_choices",
        "description": (
            f"After generating all {IMAGES_PER_SEQUENCE} scene images, provide exactly 4 choices "
            f"for the player to continue the story. Call this once, after the last image."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "choices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Choice identifier (a, b, c, or d)",
                            },
                            "text": {
                                "type": "string",
                                "description": "Description of the choice (1-2 sentences in the SAME LANGUAGE as the narration, 2nd person singular)",
                            },
                        },
                        "required": ["id", "text"],
                    },
                    "minItems": 4,
                    "maxItems": 4,
                }
            },
            "required": ["choices"],
        },
    },
}

SCENE_VIDEO_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_scene_video",
        "description": (
            "Generate a short looping video clip from the last generated image. "
            f"Call this ONCE, right after generate_scene_image for image_index={IMAGES_PER_SEQUENCE - 1} (the last image). "
            "The clip repeats; keep motion subtle and seamless. "
            "For explicit/intimate scenes prefer heavy breathing, tiny circular or swaying motion, "
            "almost no speech except a few words or the player's first name — avoid big gestures or long dialogue."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_prompt": {
                    "type": "string",
                    "description": (
                        "Motion and audio in English (1-3 short sentences). "
                        "Describe ONLY movement and sound, NOT the static image. "
                        "The output loops — use smooth, subtle, continuous motion (no big pose changes). "
                        "Explicit/intimate scenes: strong audible breathing, faint moans, "
                        "subtle circular hip motion or micro-sway, steady or barely drifting camera; "
                        "speech at most a few words or the player's first name whispered — no long lines. "
                        "Non-explicit: blinking, soft hair movement, slow lean, short whisper, ambient sound. "
                        "Example (intimate): 'Heavy breathing and slow shallow circular motion, "
                        "fingers slightly tightening, static camera, she whispers the name once.' "
                        "Example (social): 'She smiles, sips wine, soft jazz and bar murmur, gentle slow push-in.'"
                    ),
                },
            },
            "required": ["video_prompt"],
        },
    },
}

ALL_TOOLS = [SCENE_IMAGE_TOOL, SCENE_VIDEO_TOOL, CHOICES_TOOL]
