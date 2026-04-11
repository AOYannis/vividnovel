"""Grok function calling tool definitions."""

from config import IMAGES_PER_SEQUENCE

SCENE_IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_scene_image",
        "description": (
            "Generate an image for the current scene. Call ONCE per scene, "
            "AFTER writing 1-2 short sentences of stage direction + character dialogue. "
            "The image_prompt must be FULLY SELF-CONTAINED: the image model "
            "has NO memory of previous images. Describe EVERYTHING from scratch "
            "every time (full character appearance, full setting, full lighting). "
            "Describe each character ONCE only — never duplicate a character. "
            "Always specify what each hand is doing. "
            "Every image MUST be first-person POV from the player (camera = player's eyes): "
            "frame the NPC(s) as the player sees them; if the male player is in the scene, "
            "only his hands/forearms/lower body may appear at frame edges — never his full face "
            "or a third-person wide shot of the couple. "
            "The model IGNORES negations: never write 'no X' or 'without X' — "
            "instead describe positively what IS in the scene."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_index": {
                    "type": "integer",
                    "description": f"Scene number in this sequence (0-{IMAGES_PER_SEQUENCE - 1})",
                    "enum": list(range(IMAGES_PER_SEQUENCE)),
                },
                "image_prompt": {
                    "type": "string",
                    "description": (
                        "SELF-CONTAINED image prompt in English (100-250 words) for Z-Image Turbo. "
                        "MUST use first-person POV (player's eyes): start with POV markers; "
                        "never describe a third-person wide shot of two full bodies. "
                        "The model has ZERO context between images. Structure as a Camera Director: "
                        "Layer 1 (Subject): POV first-person, [shot type] of a [age, ethnicity, body type, facial features], "
                        "wearing [specific clothing with materials and state]. Describe each character ONCE. "
                        "Specify what each hand is doing. "
                        "Layer 2 (Setting): specific location, decor, environment details. "
                        "Layer 3 (Lighting): MUST name a specific lighting style "
                        "(e.g. 'soft diffused daylight', 'warm golden key light from vintage sconces', "
                        "'neon-lit nightclub ambiance'). Always include a specific lighting style, avoid non natural lighting styles (e.g. 'studio lighting', 'softbox lighting')."
                        "Layer 4 (Camera): lens type, photography style keyword "
                        "(e.g. 'Shot on Leica M10, 50mm lens, Portra Film Photo, crisp details, "
                        "shallow depth of field'). "
                        "MUST include skin realism keywords: 'highly detailed skin texture', "
                        "'subtle skin pores', 'natural skin tones'. "
                        "NEVER use negation words or these words: 'selfie', 'phone', 'camera', "
                        "'mirror', 'blur', 'artifact', 'you', 'your', 'viewer'."
                    ),
                },
                "actors_present": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "CRITICAL: List of actor codenames visible in this image. "
                        "Use exact codenames from the cast (e.g. 'nataly', 'shorty_asian'). "
                        "This field controls which character LoRAs are applied — if you "
                        "omit a character, their LoRA will NOT be loaded and they will "
                        "look WRONG. Always include ALL cast members visible in the scene. "
                        "Only use an empty array [] for atmospheric shots with NO person visible."
                    ),
                },
                "character_names": {
                    "type": "object",
                    "description": (
                        "Map actor codenames to their STORY NAMES (the names used in narration). "
                        "E.g. {'nataly': 'Nathalie', 'shorty_asian': 'Mei'}. "
                        "Include this on EVERY call so the system tracks which name each character uses."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "location_description": {
                    "type": "string",
                    "description": (
                        "Brief location tag (e.g. 'candlelit 1830s Parisian salon with velvet furniture'). "
                        "Copy-paste IDENTICALLY from previous scene if location unchanged."
                    ),
                },
                "clothing_state": {
                    "type": "object",
                    "description": (
                        "Current clothing for each visible actor. Keys = actor codenames. "
                        "Values = full clothing description. "
                        "CRITICAL: each character has their OWN clothing — never copy one "
                        "character's outfit to another. Verify the codename matches the "
                        "correct character before writing. Copy-paste IDENTICALLY from "
                        "previous scene unless the narrative changes that specific character's clothing."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "style_moods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of active style moods for this image. You can combine multiple moods. "
                        "Each mood injects a visual directive and may activate a style LoRA. "
                        "Available moods and their effects are listed in the system prompt. "
                        "Use ['neutral'] for normal scenes. Examples: ['sensual_tease'] for flirt/partial dress, "
                        "['explicit_mystic'], ['missionary'], ['doggystyle'], ['blowjob'], ['cunnilingus'], "
                        "['cunnilingus_from_behind'], ['cowgirl']."
                    ),
                },
                "secondary_characters": {
                    "type": "object",
                    "description": (
                        "Declare secondary characters (not in the main cast) appearing in this scene. "
                        "Keys = stable codenames you invent (e.g. 'rival_marco', 'barman_jules', 'colleague_anna'). "
                        "Values = detailed physical description in English: age, ethnicity, build, facial features, "
                        "hair style/color. Use famous actor/actress resemblances for visual anchoring "
                        "(e.g. 'resembling a young Oscar Isaac, early 30s, olive skin, dark stubble, strong jaw, "
                        "intense dark brown eyes, athletic build, 180cm'). "
                        "Reuse the EXACT same codename and description across all scenes for consistency. "
                        "The description is prepended to the image prompt automatically."
                    ),
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": [
                "image_index",
                "image_prompt",
                "actors_present",
                "location_description",
                "clothing_state",
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
