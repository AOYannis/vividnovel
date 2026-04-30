"""GraphBun Phase 2 — Configuration"""
import os
from pathlib import Path

# ─── Load .env file if present (local dev) ───────────────────────────────────
def _load_env_file():
    """Minimal .env loader (no python-dotenv dependency).
    Looks for backend/.env relative to this file."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # Don't override existing env vars
        if key and key not in os.environ:
            os.environ[key] = val

_load_env_file()

# ─── Admin ────────────────────────────────────────────────────────────────────
ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "").split(",")  # comma-separated Supabase user UUIDs

# ─── API Keys ────────────────────────────────────────────────────────────────
RUNWARE_API_KEY = os.environ.get("RUNWARE_API_KEY", "")
FAL_API_KEY = os.environ.get("FAL_API_KEY", "")
WAVESPEEDAI_API_KEY = os.environ.get("WAVESPEEDAI_API_KEY", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
runpod_Pruna_API = os.environ.get("runpod_Pruna_API", "")

# ─── Grok ────────────────────────────────────────────────────────────────────
GROK_BASE_URL = "https://api.x.ai/v1"
GROK_MODEL = os.environ.get("GROK_MODEL", "grok-4-1-fast-non-reasoning")

GROK_PRICING = {
    "grok-3-mini": {"input": 0.30, "output": 0.50},
    "grok-4-1-fast-non-reasoning": {"input": 0.20, "output": 0.50},
    "grok-4-1-fast": {"input": 0.20, "output": 0.50},
    "grok-4.20-beta-latest-non-reasoning": {"input": 2.00, "output": 6.00},
    "grok-4.20-beta-latest": {"input": 2.00, "output": 6.00},
}

GROK_MODELS = [
    {
        "id": "grok-3-mini",
        "label": "Grok 3 Mini",
        "tier": "budget",
        "description": "Cheap & fast. Good for testing.",
        "input_price": 0.30,
        "output_price": 0.50,
    },
    {
        "id": "grok-4-1-fast-non-reasoning",
        "label": "Grok 4.1 Fast",
        "tier": "standard",
        "description": "Default. Fast narration, good quality.",
        "input_price": 0.20,
        "output_price": 0.50,
    },
    {
        "id": "grok-4-1-fast",
        "label": "Grok 4.1 Fast (Reasoning)",
        "tier": "standard",
        "description": "Same speed, with chain-of-thought reasoning for deeper narratives.",
        "input_price": 0.20,
        "output_price": 0.50,
    },
    {
        "id": "grok-4.20-beta-latest-non-reasoning",
        "label": "Grok 4.20 Beta",
        "tier": "premium",
        "description": "Most advanced. Richer storytelling, 10x cost.",
        "input_price": 2.00,
        "output_price": 6.00,
    },
    {
        "id": "grok-4.20-beta-latest",
        "label": "Grok 4.20 Beta (Reasoning)",
        "tier": "premium",
        "description": "Most advanced with reasoning. Best narrative quality, highest cost.",
        "input_price": 2.00,
        "output_price": 6.00,
    },
]

# ─── Image Generation ────────────────────────────────────────────────────────
IMAGE_MODEL = "runware:z-image@turbo"
# runware:twinflow-z-image-turbo@0 or "runware:z-image@turbo" 
IMAGE_WIDTH = 768
IMAGE_HEIGHT = 1152
IMAGE_STEPS = 8
IMAGE_CFG = 0
IMAGE_FORMAT = "WEBP"
IMAGES_PER_SEQUENCE = 8

# ─── Actors (Character LoRAs) ────────────────────────────────────────────────
ACTOR_REGISTRY = {
    "nataly": {
        "display_name": "Nataly",
        "lora_id": "warmline:202603170002@1",
        "trigger_word": "N@t@ly",
        "default_weight": 0.8,
        "description": "Brune, regard doux et chaleureux",
    },
    "shorty_asian": {
        "display_name": "Shorty Asian",
        "lora_id": "warmline:202603200001@1",
        "trigger_word": "sh0r7y_asian",
        "default_weight": 0.8,
        "description": "Petite femme asiatique, traits fins",
    },
    "blonde_cacu": {
        "display_name": "ZiT Blonde Cacu",
        "lora_id": "warmline:202603200002@1",
        "trigger_word": "b10ndi",
        "default_weight": 0.8,
        "description": "Blonde, allure glamour",
    },
    "korean": {
        "display_name": "Korean Girl",
        "lora_id": "warmline:202603290001@1",  # TODO: replace after uploading Korean_zimage-turbo.safetensors
        "trigger_word": "k0r3an",
        "default_weight": 0.8,
        "description": "Young Korean woman, soft features, elegant",
    },
    "woman041": {
        "display_name": "Woman 041",
        "lora_id": "warmline:202603290002@1",  # TODO: replace after uploading woman041-zit.safetensors
        "trigger_word": "woman041",
        "default_weight": 0.8,
        "description": "Attractive woman, natural look",
    },
    "white_short": {
        "display_name": "White Short Hair",
        "lora_id": "warmline:202603290003@1",  # TODO: replace after uploading White_short_ZiT.safetensors
        "trigger_word": "wh1te",
        "default_weight": 0.8,
        "description": "Woman with short white/platinum hair, striking look",
    },
    "nesra": {
        "display_name": "Nesra",
        "lora_id": "warmline:202604260002@1",
        "trigger_word": "nesra",
        "default_weight": 0.8,
        "description": "European-Asian mix, layered curly hair, freckles, hazel-green eyes, always dressed very sexy",
    },
    "ciri": {
        "display_name": "Ciri (Witcher)",
        "lora_id": None,
        "trigger_word": None,
        "default_weight": 0,
        # Description shown to the agent — generic physical traits only, no source reference
        "description": "Young woman early 20s, ashen platinum-blonde short messy bob, striking emerald-green eyes, fair skin, athletic slim build, sharp angular features, confident fierce expression",
        # Prompt prefix for the IMAGE model — keeps the source reference because Z-Image needs it to render the look
        "prompt_prefix": "Ciri from The Witcher 3 video game, young woman early 20s, ashen platinum-blonde short messy bob hair, striking emerald-green eyes, fair skin, athletic slim build, sharp angular features, confident fierce expression",
    },
    "yennefer": {
        "display_name": "Yennefer (Witcher)",
        "lora_id": None,
        "trigger_word": None,
        "default_weight": 0,
        "description": "Woman late 20s, long raven-black curly hair, piercing violet eyes, pale porcelain skin, elegant hourglass figure, aristocratic features, mysterious alluring gaze",
        "prompt_prefix": "Yennefer of Vengerberg from The Witcher 3 video game, woman late 20s, long raven-black curly hair, piercing violet eyes, pale porcelain skin, elegant hourglass figure, aristocratic features, mysterious alluring gaze",
    },
    "custom": {
        "display_name": "Custom",
        "lora_id": None,
        "trigger_word": None,
        "default_weight": 0,
        "description": "Personnage personnalisé — décrit par le joueur",
        "prompt_prefix": "",
        "is_custom": True,
    },
}

# ─── Style Moods (LLM picks 0+ per scene) ────────────────────────────────────
# Position / scene helpers: prompt_block guides Z-Image; optional LoRA per mood.
# Mystic XXX ZIT V5 @1.0 for all explicit positions (blowjob, cunnilingus, doggystyle, anal, etc.).
# ZIT NSFW LoRA v2 only for sensual_tease (clothed/semi-clothed teasing).
# Specialist LoRAs (titjob, handjob, shemale) have their own dedicated LoRAs — do not stack with Mystic.
# The LLM can activate MULTIPLE moods per image (concatenate prompt_block text).
# All explicit moods use steps=14 and cfg=0 for best quality (vs default 8 steps).
MYSTIC_XXX_ZIT_V5_LORA_ID = "warmline:202603240002@1"
ZIT_NSFW_LORA_V2_ID = "warmline:2279079@2637792"
# bjz/dgz only: do not stack with Mystic (PhotoShemPen, character LoRAs + Mystic are OK).
TITJOB_LORA_ID = "warmline:202603290004@1"
POVHJ_LORA_ID = "warmline:202603290005@1"
SPECIALIST_STYLE_LORA_IDS = frozenset({
    "warmline:202603220003@1",  # Blow (bjz)
    "warmline:202603220002@1",  # Dog (dgz)
    TITJOB_LORA_ID,             # Titjob (Nsfw_Titjob)
    POVHJ_LORA_ID,              # POV Handjob (povhj)
})
_LORA_MYSTIC_XXX_ZIT_V5 = {"id": MYSTIC_XXX_ZIT_V5_LORA_ID, "name": "Mystic XXX ZIT V5", "weight": 1.0}
_LORA_ZIT_NSFW_V2_TEASE = {"id": ZIT_NSFW_LORA_V2_ID, "name": "ZIT NSFW LoRA v2", "weight": 0.72}
_LORA_ZIT_NSFW_V2_CUNNI = {"id": ZIT_NSFW_LORA_V2_ID, "name": "ZIT NSFW LoRA v2", "weight": 0.88}

DEFAULT_STYLE_MOODS = {
    "neutral": {
        "description": "Scène normale — conversation, rue, bar, pas d’acte sexuel au cadre",
        "lora": None,
        "prompt_block": "",
        "example": "",
        "cfg": None,
        "steps": None,
    },
    "kiss": {
        "description": (
            "Baiser POV extrême gros plan — visage très près, lèvres entrouvertes prêtes à embrasser la caméra, "
            "parfait pour les moments d'intimité non explicite mais intenses"
        ),
        "lora": None,
        "cfg": 0,
        "steps": 14,
        # ── Declarative mood teaching (new schema) ──
        # When `framing_intent` / `examples` / `agent_directives` are present,
        # the prompt-builder agent (Grok) is responsible for integrating the
        # mood into the final prompt. The runtime DOES NOT prepend any text.
        # This replaces the legacy `prompt_block` for this mood.
        "framing_intent": (
            "Extreme macro POV first-person of HER face/lips approaching the camera. "
            "The player IS the camera; only ONE woman is visible in the frame. Body, "
            "clothing, and the wider room are out of frame."
        ),
        "examples": [
            # Each example is a complete reference prompt showing one valid framing
            # for this mood. Grok rotates inspiration across them and adapts to the
            # current scene's character/location/lighting. NEVER copied verbatim.
            (
                "young woman, soft warm gaze, head tilted slightly, lower half of her "
                "face fills the frame, full glossy lips slightly parted toward the camera "
                "with a glimpse of moist tongue and white teeth, eyes closed in bliss, "
                "faint lip gloss sheen, warm rim light catching her cheekbone, candlelit "
                "room glow in soft bokeh background, 85mm macro lens, Portra Film Photo, "
                "ultra shallow depth of field, natural film grain, organic textures"
            ),
            (
                "three-quarter angle close-up of her face approaching the camera, "
                "cheekbone and eyelash catchlight visible, lips parted in anticipation "
                "just before contact, eyes half-closed, single warm key light from the "
                "side, highly detailed skin texture with subtle pores, 85mm macro, "
                "shallow depth of field, soft bokeh"
            ),
            (
                "head-on extreme close-up of her parted lips filling the lower half of "
                "the frame, tip of tongue just visible, eyes closed and tilted slightly "
                "down, softened ambient glow on her skin, 100mm macro lens, hyper-shallow "
                "depth of field, natural film grain, intimate quiet atmosphere"
            ),
        ],
        "agent_directives": [
            # Hard rules Grok MUST obey when crafting this mood's prompt.
            "ABSOLUTELY ONE woman visible — never any second person, never plural 'faces'.",
            "Use SINGULAR 'face' — even if scene_summary says 'her lips against yours' "
            "or similar, interpret 'yours' as the camera (no second visible face).",
            "DO NOT include any clothing description — out of frame in this framing.",
            "DO NOT include body description below the collarbone — out of frame.",
            "Keep appearance details to FACE-ONLY (hair colour visible at temples, eye "
            "colour, lip shape, freckles, skin tone) — skip height, build, breast/hip notes.",
        ],
    },
    "sensual_tease": {
        "description": (
            "Séduction / teasing / flirt — tension, regards, vêtements entrouverts (pas de tout-nu forcé ; "
            "préférer ce mood à Mystic quand le personnage est encore habillé ou à moitié déshabillé, ou nu avant penetration)"
        ),
        "lora": _LORA_ZIT_NSFW_V2_TEASE,
        "prompt_block": (
            "nsfw_master intimate sensual atmosphere, partial clothing dress or lingerie still on, slipped strap unbuttoned blouse, "
            "cleavage bare shoulders skirt hem, warm flirtatious gaze parted lips, soft flush, "
            "photorealistic skin, soft key light"
        ),
        "example": (
            "She leans on bar in silk slip dress, lace edge visible, one strap fallen, eye contact toward camera, "
            "warm bokeh, city lights behind"
        ),
        "cfg": None,
        "steps": None,
    },
    "explicit_mystic": {
        "description": "Explicite générique (Mystic V5) — tension / nu / intimité quand il y a une penetration visible, quand la position n’est pas encore cadrée",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "POV first-person explicit photograph, as seen through the player eyes, primary focus on her face and body, "
            "nude or partially nude, warm natural skin tones, realistic anatomy, shallow depth of field, "
            "if the man appears only his hands forearms or lower torso at bottom of frame edges, "
            "bedroom or private interior, or outside in a public place, passionate expression, soft key light on skin, "
            "highly detailed skin texture with subtle pores and natural tones. "
            "Shot on 50mm lens, Portra Film Photo, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "POV eye-level: her face and shoulders fill the frame, she leans toward the lens, "
            "man’s hands at bottom edge of frame, warm rim light, dark blurred background, film grain"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "blowjob": {
        "description": "Fellation POV — bouche sur le pénis, regard vers la caméra, visage visible",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "POV Close-up photograph of a woman performing fellatio on a man. "
            "The woman wearing a detailed dangling earring, looking up with her mouth open, tongue extended to lick "
            "the man's erect penis. The man's penis is prominently in the foreground, with visible veins and a pinkish glans. "
            "The angle is from the man's point of view, looking down at her. "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "POV looking down: her eyes locked to lens, lips on shaft, hands on male thighs, "
            "warm bedroom light, soft sheets background, shallow DOF"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "blowjob_closeup": {
        "description": "Fellation très gros plan — focus sur les lèvres, la langue et le pénis, moins de visage",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "POV Close-up oral sex. Close-up photograph of a woman performing fellatio on a man. "
            "The woman's face is partially visible, showing her pink lips and tongue extended to lick the man's erect penis. "
            "Her tongue is in contact with the penis, which is prominently displayed in the foreground. "
            "The man's penis is large, with visible veins and a pinkish glans. "
            "The woman's skin is fair, her lips slightly parted, revealing a small part of her upper teeth. "
            "The background is blurred. The lighting is soft, highlighting the textures of the skin "
            "and the moistness of the woman's tongue. The focus is on the intimate act, "
            "with the penis occupying the central part of the frame. "
            "The angle is from the man's point of view, looking down at her. "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "Extreme close-up: pink lips and tongue on shaft, veins visible, "
            "blurred background, soft light on skin moisture"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "cunnilingus": {
        "description": (
            "Cunnilingus classique — femme sur le dos, jambes écartées, POV du donneur vers le haut "
            "(visage haut du cadre, vulve bas)"
        ),
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "cunnilingus, POV Close-up photograph of a woman's vulva, with her legs spread apart. "
            "Her skin is light and smooth, with a small patch of dark pubic hair above her vulva, "
            "her vulva labia visibly wet, her vulva dripping saliva, and her labia are slightly parted by man's hands at the bottom of the frame. The texture of her skin is soft, with faint blue veins visible. "
            "Face at top of frame with parted lips and eyes half-closed in pleasure looking down toward camera, "
            "medium breasts and smooth belly in mid-frame, vulva visible at lower frame with hands around it "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "POV looking up from between her thighs: her face at top, torso middle, vulva lower, "
            "parted lips, half-closed eyes, warm lamplight"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "cunnilingus_from_behind": {
        "description": (
            "Cunnilingus « from behind » — gros plan macro sur les quatre pattes, vulve/anus remplissant le cadre"
        ),
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "Close-up photograph of a woman's anus and vulva. Her skin is light and smooth, "
            "with a slight pinkish hue around the genital area. She is on fours, "
            "and a hand with neatly trimmed nails is gently touching her thigh. "
            "The background is a red fabric, possibly a bedsheet, adding a contrasting color to her pale skin. "
            "The lighting is bright and even, highlighting the natural texture and folds of her skin. "
            "The focus is sharp, capturing the details of her anatomy. "
            "The image is intimate and detailed, emphasizing the natural beauty and form of the female genitalia. "
            "highly detailed skin texture with subtle pores and natural tones. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "Close-up: vulva and anus from behind on all fours, hand on thigh, red bedsheet, "
            "bright even light, sharp anatomical detail, natural skin tones"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "missionary": {
        "description": "Missionnaire — femme sur le dos, jambes écartées, partenaire entre ses cuisses",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "POV first-person looking down at naked woman on bed on her back, spread legs, penis visible at bottom of frame penetrating her vulva "
            "medium breasts, nipples, navel, nude, realistic skin, closed eyes or intimate eye contact toward camera, "
            "only male penis, hands or groin at lower edge of frame."
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            
        ),
        "example": (
            "POV missionary: her face and breasts dominant, legs wrapped or spread, male forearms at frame edges, "
            "white sheets, soft window light"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "cowgirl": {
        "description": "Cowgirl — femme au dessus pénétrée vaignalement, face au partenaire",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "POV explicit shot of a woman visible on the entire frame, she is straddling, her vulva penetrated by a penis, man chest and penis visible at the bottom, "
            "The woman has her hands on man's chest or her thighs, vaginal sex, eye contact or head tilted back, bedroom, photorealistic, "
            "her torso and face dominant in frame, explicit penis penetration visible at the bottom of the frame, "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate lighting casting soft shadows. "
            
        ),
        "example": (
            "POV from below: she leans forward hands on his chest, hair falling forward, "
            "warm side light, motion blur subtle on hips"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "reverse_cowgirl": {
        "description": "Cowgirl inversée — femme au-dessus, dos à la caméra / au partenaire",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "reverse cowgirl, POV first-person from below looking up at woman from behind, straddling, back arched, "
            "buttocks prominent, man lying beneath, hands on her hips or ass at frame edge, penis penetrating her vulva, vaginal sex, visible anus above her vulva,explicit, "
            "bedroom lighting, "
            "highly detailed skin texture with subtle pores and natural tones. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details"
        ),
        "example": (
            "POV from mattress: her arched back and ass fill upper frame, she looks over shoulder, rim light on spine"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "doggystyle": {
        "description": "Levrette — à quatre pattes, pénétration vaginale par derrière, POV derrière",
        "lora": {"id": "warmline:202603220002@1", "name": "Dog (dgz)", "weight": 1.0},
        "prompt_block": (
            "dgz, pov, intimate explicit photograph, woman on hands and knees on bed, man behind penetrating from behind, "
            "his hands gripping her hips, erect penis visible entering her, muscular male arms and hands, "
            "her expression surprise or pleasure, raw adult scene, "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "POV from behind: white bed, her ass arched, his hands on hips, "
            "both nude, sharp focus on connection, warm light"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "titjob": {
        "description": "Titjob / branlette espagnole — pénis entre les seins, POV par-dessus",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "Titjob, POV first-person looking down, woman pressing breasts together around erect penis, "
            "her hands squeezing breasts from sides, shaft visible between cleavage, "
            "her gaze upward toward camera, intimate close-up, "
            "highly detailed skin texture with subtle pores and natural skin tones, sun-kissed skin, "
            "crisp details, organic textures. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading"
        ),
        "example": (
            "POV from above: her face looking up between pressed breasts, shaft between cleavage, "
            "warm golden light, polished wood and leather accents"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "handjob": {
        "description": "Branlette / handjob — POV par-dessus, main sur le pénis",
        "lora": {"id": POVHJ_LORA_ID, "name": "POV Handjob (povhj)", "weight": 1.0},
        "prompt_block": (
            "povhj, POV first-person looking down, woman's hand wrapped around erect penis, "
            "her fingers gripping shaft, her face visible looking up or at the action, "
            "intimate close-up, photorealistic skin, warm bedroom lighting, "
            "highly detailed skin texture with subtle pores and natural tones. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details"
        ),
        "example": (
            "POV from above: her hand on shaft, her face looking up with parted lips, "
            "warm side light, shallow depth of field"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "spooning": {
        "description": "Cuillère — côte à côte, pénétration depuis derrière en position allongée",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "spooning sex, POV first-person over her shoulder in bed, side lying, "
            "POV man'spenis visible at bottom right of frame, penetrating her vulva from behind, her face in profile toward camera,  "
            "warm soft bedroom light, tight crop no wide establishing shot, "
            "highly detailed skin texture with subtle pores and natural tones. "
        ),
        "example": (
            "POV intimate crop: tangled legs, her head on pillow turned slightly toward lens, "
            "sweat-gloss skin, shallow DOF"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "standing_sex": {
        "description": "Debout — pénétration vaginale debout contre un mur, face à face",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "standing sex, POV first-person chest-height, laying against wall, "
            "woman's face and upper body dominant, penis visible at the bottom of the frame penetrating her vulva while she's standing, male hands on her waist at frame "
            "edges,  explicit, cinematic lighting,  "
            "highly detailed skin texture with subtle pores and natural tones. "
        ),
        "example": (
            "POV: her back to wall filling frame, his forearms at lower edge, "
            "overhead spot + warm bounce from floor"
        ),
        "cfg": 0,
        "steps": 8,
    },
    "anal_doggystyle": {
        "description": "Anal levrette — à quatre pattes, pénétration anale par derrière, POV serré",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "Anal cumshot. A POV photograph of a sexual act. "
            "A naked woman with light skin is on all fours on a white bed, "
            "looking back over her shoulder with her mouth slightly open. "
            "A man is behind her, holding his erect penis against her anus. "
            "The woman's vulva is visible, with some pubic hair. "
            "The bed has a white quilted cover. The lighting is bright and even, "
            "highlighting the subjects and creating minimal shadows. "
            "The woman's expression is one of surprise or pleasure. "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "POV behind: she looks over shoulder, mouth open, on all fours, "
            "white bed, bright even light, anal penetration visible"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "anal_missionary": {
        "description": "Anal missionnaire — femme sur le dos, jambes écartées et relevées, pénétration anale POV",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "Anal, POV Close-up Anal sex. A photograph of a woman with light skin, "
            "lying on a white bed, legs spread and raised, exposing her vulva. "
            "A man's erect penis is penetrating her anus. "
            "She has small breasts with light pink areolas. "
            "Her expression is slightly open-mouthed, with a hint of pleasure. "
            "The lighting is bright and even, highlighting the woman's body and the act. "
            "The bed has white sheets, and the background is mostly out of focus. "
            "Face at top of frame with parted lips and eyes half-closed in pleasure looking down toward camera, "
            "medium breasts and smooth belly in mid-frame, "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "POV looking down: her face top, breasts mid, legs raised and spread, "
            "anal penetration, white sheets, bright even light"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "cumshot_face": {
        "description": "Éjaculation faciale — gros plan sur le visage avec sperme sur les lèvres, la langue et le visage",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "Cumshot, POV extreme Close-up on lips. Close-up photograph of a woman's face. "
            "The woman's face is partially visible, showing her pink lips and tongue. "
            "She has cum on her face, lips and tongue. "
            "The woman's skin is fair, and her lips are slightly parted, revealing a small part of her upper teeth. "
            "The background is blurred. The lighting is soft, highlighting the textures of the skin "
            "and the moistness of the woman's tongue. "
            "High intimacy and sensuality act, "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "Extreme close-up: her face with cum on lips and tongue, parted lips, "
            "blurred background, soft warm light, detailed skin"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "anal_missionary_shemale": {
        "description": (
            "Anal missionnaire POV avec une shemale — variante d'anal_missionary "
            "spécialisée pour les personnages trans, pénis érigé visible. Utilise le "
            "LoRA Mishra (spécialisé pose POV missionnaire) à la place du LoRA Mystic. "
            "NE PAS empiler avec `futa_shemale` — Mishra fournit déjà la pose et l'anatomie. "
            "Le LoRA du personnage est réduit à 0.6 pour laisser Mishra dominer la pose."
        ),
        "lora": {"id": "warmline:202604260001@1", "name": "Mishra v5", "weight": 0.9},
        "char_lora_weight": 0.7,   # override actor's default_weight for this mood
        "skip_trans_lora": True,   # do NOT auto-add ZTurbo Pen V3 even for trans actors
        "prompt_block": (
            "mishra, Anal missionary POV with a shemale. "
            "POV close-up looking down at a trans woman lying on her back on a white bed, "
            "legs spread and raised, her erect penis prominently visible on her belly, "
            "POV first-person male penetrating her anally, "
            "her hands gripping the sheets, slightly open mouth with a hint of pleasure, "
            "natural skin tones, photorealistic anatomy, anatomical detail, "
            "highly detailed skin texture with subtle pores, warm intimate bedside lamp lighting, "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details"
        ),
        "example": (
            "POV looking down: shemale on her back, legs raised and spread, "
            "her erect penis visible on her belly, anal penetration POV, "
            "white sheets, warm intimate light"
        ),
        "cfg": 1,
        "steps": 18,
    },
    "futa_shemale": {
        "description": (
            "Futa / shemale RÉVÉLATION ANATOMIQUE — UNIQUEMENT pour les scènes où le personnage "
            "est NU OU partiellement déshabillé ET ses organes génitaux sont VISIBLES dans le cadre. "
            "NE PAS utiliser pour des scènes habillées, même suggestives — utiliser `sensual_tease` "
            "ou `kiss` à la place jusqu'au moment de la révélation. Stacke avec le LoRA du personnage "
            "pour préserver son apparence."
        ),
        "lora": {"id": "warmline:202603170004@1", "name": "ZTurbo Pen V3", "weight": 1.0},
        "prompt_block": (
            "anatomical reveal moment, character is nude or partially undressed with genital area visible in frame, "
            "erect penis prominently displayed, detailed veins and glans anatomy, "
            "natural skin tones, photorealistic anatomy, intimate framing focused on the reveal"
        ),
        "example": (
            "She lifts her dress hem, revealing her erect penis between her thighs, intimate bedroom lighting"
        ),
        "cfg": 1,
        "steps": 15,
    },
}
# Additional style LoRAs always applied (editable via debug)
DEFAULT_STYLE_LORAS: list[dict] = []
MAX_LORAS_PER_IMAGE = 3

# ─── Video Generation ────────────────────────────────────────────────────────
VIDEO_MODEL = "prunaai:p-video@0"
VIDEO_DURATION = 5
VIDEO_RESOLUTION = "720p"
VIDEO_DRAFT = True
VIDEO_AUDIO = True
VIDEO_SIMULATE = False  # if True, skip real video gen, simulate ~60s loading
VIDEO_EARLY_START = False  # if True, start video gen from image 0 instead of waiting for image 4

# ─── All LoRAs (for debug picker) ────────────────────────────────────────────
AVAILABLE_LORAS = [
    {"id": "warmline:2279079@2637792", "name": "ZIT NSFW LoRA v2", "type": "style", "trigger": "nsfw_master"},
    {"id": "warmline:202603120001@1", "name": "Futagrow", "type": "style"},
    {"id": "warmline:202603120002@1", "name": "NakedErectFutaZit", "type": "style"},
    {"id": "warmline:202603150001@1", "name": "NSFW Hentai", "type": "style"},
    {"id": "warmline:202603150002@1", "name": "PWFP", "type": "character"},
    {"id": "warmline:202603170001@1", "name": "Milena", "type": "character"},
    {"id": "warmline:202603170002@1", "name": "Nataly", "type": "character", "trigger": "N@T@LY"},
    {"id": "warmline:202603170003@1", "name": "NS Unlocked V1", "type": "style"},
    {"id": "warmline:202603170004@1", "name": "ZTurbo Pen V3", "type": "style"},
    {"id": "warmline:202603200001@1", "name": "Shorty Asian", "type": "character", "trigger": "sh0r7y_asian"},
    {"id": "warmline:202603200002@1", "name": "ZiT Blonde Cacu", "type": "character", "trigger": "b10ndi"},
    {"id": "warmline:202603200003@1", "name": "NS Master ZIT", "type": "style"},
    {"id": "warmline:202603220001@1", "name": "FutaV4", "type": "style"},
    {"id": "warmline:202603220002@1", "name": "Dog (dgz)", "type": "style", "trigger": "dgz"},
    {"id": "warmline:202603220003@1", "name": "Blow (bjz)", "type": "style", "trigger": "bjz"},
    {"id": "warmline:202603220004@1", "name": "Missio", "type": "style"},
    {"id": "warmline:202603230001@1", "name": "0lga", "type": "character", "trigger": "blond0lga"},
    {"id": "warmline:202603230002@1", "name": "Nsfw Miss", "type": "style"},
    {"id": "warmline:202603230003@1", "name": "PhotoShemPen V1", "type": "style"},
    {"id": "warmline:202603240001@1", "name": "Nicegirls Zimage", "type": "style"},
    {"id": "warmline:202603240002@1", "name": "Mystic XXX ZIT V5", "type": "style"},
    {"id": "warmline:202603290001@1", "name": "Korean Girl", "type": "character", "trigger": "k0r3an"},
    {"id": "warmline:202603290002@1", "name": "Woman 041", "type": "character", "trigger": "woman041"},
    {"id": "warmline:202603290003@1", "name": "White Short Hair", "type": "character", "trigger": "wh1te"},
    {"id": TITJOB_LORA_ID, "name": "Nsfw Titjob", "type": "style", "trigger": "Nsfw_Titjob"},
    {"id": POVHJ_LORA_ID, "name": "POV Handjob (povhj)", "type": "style", "trigger": "povhj"},
    {"id": "warmline:202604110001@1", "name": "ZPenis V2", "type": "style"},
    {"id": "warmline:202604260001@1", "name": "Mishra v5", "type": "style", "trigger": "mishra"},
    {"id": "warmline:202604260002@1", "name": "Nesra V3", "type": "character", "trigger": "nesra"},
]

# ─── Settings ────────────────────────────────────────────────────────────────
SETTINGS = {
    "paris_2026": {
        "label": "Paris, 2026",
        "description": "Paris contemporain — vie urbaine d'aujourd'hui, scène ordinaire et intime",
        "era": "contemporain",
    },
    "paris_1800": {
        "label": "Paris, 1830",
        "description": "Paris du début du XIXe — moeurs, atmosphère et rythme de l'époque romantique",
        "era": "XIXe siècle",
    },
    "neo_2100": {
        "label": "Neo-Tokyo, 2100",
        "description": "Mégalopole futuriste du XXIIe siècle — vie urbaine d'une ville-monde",
        "era": "futuriste",
    },
    # ─── Huis-clos / mystères ──────────────────────────────────────────────
    # Rich, hand-written briefs. The full `description` text is what flows
    # downstream to Grok (location generation, cast schedules, map prompt) —
    # so the prose is intentionally dense and specific. The short `teaser`
    # is what the player sees in the setup card.
    "mystery_cornouailles": {
        "label": "Le manoir des Cornouailles",
        "teaser": "Manoir victorien isolé par la tempête. Patriarche assassiné dans la bibliothèque verrouillée.",
        "era": "huis-clos contemporain",
        "description": (
            "Falaises battues par la tempête, vieille demeure victorienne perdue sur la côte anglaise. "
            "Le patriarche Lord Ashworth a réuni sa famille pour annoncer son nouveau testament. "
            "Au matin, on le retrouve dans la bibliothèque verrouillée de l'intérieur, une coupe de "
            "porto renversée à ses pieds. La route est inondée, le téléphone coupé. Suspects : la "
            "jeune épouse de 30 ans sa cadette, le fils héritier ruiné par les paris, la fille adoptée "
            "écartée du testament, le majordome qui sait trop de choses, le médecin de famille "
            "étrangement nerveux, et la nièce écrivaine qui prenait des notes pendant le dîner."
        ),
    },
    "mystery_transsiberien": {
        "label": "Train de nuit Moscou-Vladivostok",
        "teaser": "Transsibérien, sept jours hors du monde. Oligarque étranglé avec sa propre cravate Hermès.",
        "era": "huis-clos contemporain",
        "description": (
            "Compartiment de luxe du Transsibérien, sept jours de voyage, taïga gelée à perte de vue. "
            "Au troisième matin, l'oligarque Volkov est retrouvé mort dans sa cabine, étranglé avec "
            "sa propre cravate Hermès. Le prochain arrêt est dans 14 heures. Suspects : son garde "
            "du corps qui dormait juste à côté, sa maîtresse française, un journaliste d'investigation "
            "qui le suivait, un diplomate chinois aux bagages diplomatiques inviolables, une vieille "
            "dame qui joue aux échecs toute seule, et le serveur du wagon-restaurant qui a versé son thé."
        ),
    },
    "mystery_arcs": {
        "label": "Chalet aux Arcs, tempête de neige",
        "teaser": "Réunion HEC vingt ans après. Fortune fracassée au pied de l'escalier. Tempête, télécabines coupées.",
        "era": "huis-clos contemporain",
        "description": (
            "Réunion d'anciens amis de prépa HEC, vingt ans après. Sept personnes, un chalet de luxe, "
            "du champagne, des secrets. La tempête a coupé l'accès aux pistes et aux télécabines. Au "
            "matin, Alexandre — devenu le plus riche du groupe — gît au pied de l'escalier, le crâne "
            "fracassé. Chute accidentelle ou meurtre ? Suspects : l'ex qu'il a quittée pour épouser sa "
            "meilleure amie, l'associé qu'il a évincé, le copain devenu raté qui lui empruntait de "
            "l'argent, la femme actuelle qui a vu les SMS, le frère cadet jaloux, et l'ami d'enfance "
            "médecin qui a « constaté » la mort un peu vite."
        ),
    },
    "mystery_egee": {
        "label": "Yacht en mer Égée",
        "teaser": "Le Calliope croise les Cyclades. Magnat introuvable, peignoir abandonné sur le pont arrière.",
        "era": "huis-clos contemporain",
        "description": (
            "Le Calliope, voilier de 50 mètres, croisière privée entre les Cyclades. À bord : un "
            "magnat de la presse grec, sa famille recomposée, quelques invités triés sur le volet. "
            "Au matin, le magnat est introuvable dans sa cabine. On retrouve son peignoir sur le pont "
            "arrière et des traces de sang sur le bastingage. Le capitaine refuse de regagner le port "
            "avant l'enquête. Suspects : la nouvelle épouse, son fils du premier mariage déshérité, "
            "le rédacteur en chef qu'il s'apprêtait à virer, l'avocate de la famille qui connaît tous "
            "les dossiers, un romancier invité qui semblait fasciné par lui, et l'équipage philippin "
            "que personne n'interroge."
        ),
    },
    "mystery_pensionnat": {
        "label": "Pensionnat suisse, week-end de retrouvailles",
        "teaser": "Internat huppé de Lausanne, 25 ans après. Prof pendue dans la chapelle. Le scandale de 99 remonte.",
        "era": "huis-clos contemporain",
        "description": (
            "Un internat huppé près de Lausanne ouvre ses portes pour les 25 ans de la promo. Une "
            "douzaine d'anciens élèves, quelques profs encore en poste, le directeur émérite. Au "
            "petit déjeuner, on découvre Mme Berger, la prof de littérature, pendue dans la chapelle. "
            "Mais le nœud ne correspond pas à un suicide. Tout le monde se souvient du « scandale de "
            "99 » que personne n'a jamais éclairci. Suspects : ceux qui étaient impliqués dans "
            "l'affaire, et ceux qui ont fait semblant de ne rien voir."
        ),
    },
    "mystery_bordeaux": {
        "label": "Vendanges au château bordelais",
        "teaser": "Domaine viticole prestigieux, dégustation des nouveaux millésimes. Œnologue noyé dans une cuve.",
        "era": "huis-clos contemporain",
        "description": (
            "Domaine viticole prestigieux pendant les vendanges. Le propriétaire, œnologue mondialement "
            "reconnu, accueille critiques, acheteurs et famille pour la dégustation des nouveaux "
            "millésimes. Au matin du second jour, on le retrouve noyé dans une cuve de fermentation. "
            "Suspects : ses deux fils en guerre pour la succession, le maître de chai qui rêvait du "
            "domaine, un critique américain à la plume assassine, un acheteur chinois éconduit, sa "
            "fille végane et anti-alcool, et la jeune œnologue qu'il venait d'embaucher."
        ),
    },
    "mystery_mont_blanc": {
        "label": "Refuge de haute montagne, Mont-Blanc",
        "teaser": "Tempête imprévue, huit alpinistes coincés à 3800m. Guide chef d'expédition, piolet en pleine poitrine.",
        "era": "huis-clos contemporain",
        "description": (
            "Tempête imprévue, huit alpinistes coincés dans un refuge à 3800 mètres. Vivres pour trois "
            "jours, hélico impossible avant 48 heures. La deuxième nuit, le guide chef d'expédition "
            "est retrouvé dans son sac de couchage, un piolet planté dans la poitrine. La porte du "
            "refuge n'a pas été ouverte. Suspects : tous ceux qui dormaient dans la pièce commune, "
            "plus le gardien du refuge qui avait sa chambre à part."
        ),
    },
    "mystery_theatre": {
        "label": "Théâtre parisien, première annulée",
        "teaser": "Soir de générale. Première actrice empoisonnée au troisième acte. Portes fermées, troupe retenue.",
        "era": "huis-clos contemporain",
        "description": (
            "Soir de générale dans un grand théâtre parisien. La première actrice s'effondre au "
            "troisième acte, empoisonnée. Les portes sont fermées, le public et la troupe sont retenus "
            "pour interrogatoire jusqu'au matin. Suspects : le metteur en scène qui couchait avec elle, "
            "le mari producteur qui finance le spectacle, l'actrice doublure qui prend sa place ce "
            "soir, le critique du Monde au premier rang qui l'avait détruite l'an dernier, le régisseur "
            "amoureux transi, et l'auteur qui voulait la virer du rôle."
        ),
    },
    "mystery_glenan": {
        "label": "Île privée des Glénan",
        "teaser": "Île de la tech, mer démontée, pas de réseau. Hôte évanoui, téléphone fracassé sur les rochers.",
        "era": "huis-clos contemporain",
        "description": (
            "Un milliardaire de la tech a invité une dizaine d'invités sur son île privée pour fêter "
            "le rachat de sa boîte. Vedette en panne, mer démontée, pas de réseau. Au réveil, l'hôte "
            "n'est nulle part. On retrouve son téléphone fracassé sur les rochers et une lettre de "
            "démission qu'il n'avait jamais envoyée. Suspects : son cofondateur qu'il avait poussé "
            "dehors, sa femme qui demandait le divorce, son DAF accusé d'avoir maquillé les comptes, "
            "une journaliste tech qui préparait un papier au vitriol, son thérapeute personnel, et "
            "son chef cuisinier qui connaît tous les invités depuis dix ans."
        ),
    },
}
