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
        "prompt_block": (
            "An extreme macro close-up POV first-person shot, eye-level intimate kiss from the camera perspective, "
            "ultra-tight crop of her half face filling the entire frame, "
            "only the lower half of her face visible with the rest heavily cropped out, "
            "eyes closed in bliss, head slightly tilted, full glossy lips slightly parted for a kiss to the camera, "
            "visible moist tongue tip and glimpse of white teeth, "
            "highly detailed skin texture with subtle pores and natural skin tones, faint lip gloss sheen. "
            "Shot on 85mm macro lens, Portra Film Photo, ultra shallow depth of field, crisp details, organic textures. "
            "CRITICAL: only one woman visible, no second person in frame"
        ),
        "example": (
            "Her lower face fills the frame, lips parted toward the lens, eyes closed, "
            "warm rim light catching her cheekbone"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "sensual_tease": {
        "description": (
            "Séduction / teasing / flirt — tension, regards, vêtements entrouverts (pas de tout-nu forcé ; "
            "préférer ce mood à Mystic quand le personnage est encore habillé ou à moitié déshabillé)"
        ),
        "lora": _LORA_ZIT_NSFW_V2_TEASE,
        "prompt_block": (
            "intimate sensual atmosphere, partial clothing dress or lingerie still on, slipped strap unbuttoned blouse, "
            "cleavage bare shoulders skirt hem, warm flirtatious gaze parted lips, soft flush, "
            "no full nude unless narrative already undressed, photorealistic skin, soft key light"
        ),
        "example": (
            "She leans on bar in silk slip dress, lace edge visible, one strap fallen, eye contact toward camera, "
            "warm bokeh, city lights behind"
        ),
        "cfg": None,
        "steps": None,
    },
    "explicit_mystic": {
        "description": "Explicite générique (Mystic V5) — tension / nu / intimité quand la position n’est pas encore cadrée",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "POV first-person explicit photograph, as seen through the player eyes, primary focus on her face and body, "
            "nude or partially nude, warm natural skin tones, realistic anatomy, shallow depth of field, "
            "if the man appears only his hands forearms or lower torso at frame edges never his face or full body, "
            "bedroom or private interior, passionate expression, soft key light on skin, "
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
            "Her skin is light and smooth, with a small patch of dark pubic hair above her pink, "
            "slightly parted by fingers labia. The texture of her skin is soft, with faint blue veins visible. "
            "Face at top of frame with parted lips and eyes half-closed in pleasure looking down toward camera, "
            "medium breasts and smooth belly in mid-frame, intimate oral contact area at lower frame, "
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
        "description": "Missionnaire — femme sur le dos, jambes écartées, partenaire entre ses cuisses (POV possible)",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "hetero, POV first-person looking down at naked woman on bed on her back, spread legs, vaginal sex, "
            "medium breasts, nipples, navel, nude, realistic skin, closed eyes or intimate eye contact toward camera, "
            "only male hands or groin at lower edge of frame, bedroom, uncensored, no wide shot of both bodies, "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate bedside lamp lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details, organic textures"
        ),
        "example": (
            "POV missionary: her face and breasts dominant, legs wrapped or spread, male forearms at frame edges, "
            "white sheets, soft window light"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "cowgirl": {
        "description": "Cowgirl — femme au-dessus, face au partenaire, chevauchée",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "cowgirl position, POV first-person lying on back looking up at woman straddling, riding, "
            "hands on his chest or her thighs, vaginal sex, eye contact or head tilted back, bedroom, photorealistic, "
            "her torso and face dominant in frame, explicit penetration implied or visible, "
            "highly detailed skin texture with subtle pores and natural tones, "
            "warm intimate lighting casting soft shadows. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details"
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
            "buttocks prominent, man lying beneath, hands on her hips or ass at frame edge, vaginal sex, explicit, "
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
            "spooning sex, POV first-person over her shoulder in bed, side lying, man behind woman, both nude, "
            "intimate penetration from behind, her face in profile toward camera, his arm around her waist visible, "
            "warm soft bedroom light, tight crop no wide establishing shot, "
            "highly detailed skin texture with subtle pores and natural tones. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details"
        ),
        "example": (
            "POV intimate crop: tangled legs, her head on pillow turned slightly toward lens, "
            "sweat-gloss skin, shallow DOF"
        ),
        "cfg": 0,
        "steps": 14,
    },
    "standing_sex": {
        "description": "Debout — contre un mur, jambe relevée, ou face à face debout",
        "lora": _LORA_MYSTIC_XXX_ZIT_V5,
        "prompt_block": (
            "standing sex, POV first-person chest-height, against wall or door, one leg lifted or wrapped around waist, "
            "her face and upper body dominant, passionate embrace, penetration, male hands under her thighs at frame "
            "edges, indoor location, explicit, cinematic lighting, no distant wide couple shot, "
            "highly detailed skin texture with subtle pores and natural tones. "
            "Shot on 50mm lens, Portra Film Photo, shallow depth of field, cinematic color grading, crisp details"
        ),
        "example": (
            "POV: her back to wall filling frame, his forearms at lower edge, "
            "overhead spot + warm bounce from floor"
        ),
        "cfg": 0,
        "steps": 14,
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
    {"id": "warmline:2279079@2637792", "name": "ZIT NSFW LoRA v2", "type": "style"},
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
]

# ─── Settings ────────────────────────────────────────────────────────────────
SETTINGS = {
    "paris_2026": {
        "label": "Paris, 2026",
        "description": "Paris contemporain — bars branchés, terrasses, appartements haussmanniens",
        "era": "contemporain",
    },
    "paris_1800": {
        "label": "Paris, 1830",
        "description": "Paris romantique — salons, bals, ruelles pavées à la lueur des bougies",
        "era": "XIXe siècle",
    },
    "neo_2100": {
        "label": "Neo-Tokyo, 2100",
        "description": "Mégalopole futuriste — néons, hologrammes, clubs cyberpunk",
        "era": "futuriste",
    },
}
