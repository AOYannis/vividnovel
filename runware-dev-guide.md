# Runware Development Guide — Z-Image & P-Video

## Setup

```bash
pip install runware
```

```python
from runware import Runware, IImageInference, ILora
from runware.types import IVideoInference, IFrameImage, ISettings, IVideoInputs, IAsyncTaskResponse
```

---

## Image Generation (Z-Image Turbo)

### Basic Usage

```python
async def generate_image(prompt: str):
    runware = Runware(api_key="YOUR_API_KEY")
    await runware.connect()

    request = IImageInference(
        model="runware:z-image@turbo",
        positivePrompt=prompt,
        width=720,
        height=1280,
        steps=8,
        CFGScale=0,           # 0 for Turbo models
        numberResults=1,
        outputFormat="PNG",
        includeCost=True,
    )

    images = await runware.imageInference(requestImage=request)
    for img in images:
        print(f"URL: {img.imageURL}, Cost: ${img.cost}, Seed: {img.seed}")
```

### With LoRA

```python
request = IImageInference(
    model="runware:z-image@turbo",
    positivePrompt="your prompt here",
    width=1056,
    height=1584,
    steps=8,
    CFGScale=0,
    outputFormat="PNG",
    includeCost=True,
    lora=[
        ILora(model="warmline:202603170001@1", weight=1.0),   # Milena
        ILora(model="warmline:202603170004@1", weight=0.5),   # ZTurbo Pen V3
    ],
)
```

### Multiple LoRAs with Per-LoRA Weights

```python
lora=[
    ILora(model="warmline:2279079@2637792", weight=0.8),     # ZIT NSFW v2
    ILora(model="warmline:202603170003@1", weight=1.2),      # NS Unlocked V1
]
```

Weight range: **-4.0 to 4.0** (default: 1.0). Negative weights invert the LoRA's effect.

### Parameters Reference

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `model` | str | — | Required. `"runware:z-image@turbo"` for Z-Image |
| `positivePrompt` | str | — | Required. Natural-language description |
| `negativePrompt` | str | `""` | Ignored by Z-Image Turbo (CFG=0) |
| `width` | int | 1024 | 256–2048, step 64 |
| `height` | int | 1024 | 256–2048, step 64 |
| `steps` | int | 8 | 1–100. 8 is optimal for Turbo |
| `CFGScale` | float | 0 | 0 for Turbo. 0–20 for other models |
| `seed` | int | random | 0 = random. Set for reproducibility |
| `numberResults` | int | 1 | 1–4 images per request |
| `outputFormat` | str | `"PNG"` | PNG, JPG, WEBP |
| `lora` | list | `[]` | List of `ILora(model=AIR_ID, weight=FLOAT)` |
| `includeCost` | bool | False | Include cost in response |

### Recommended Aspect Ratios

| Use Case | Dimensions | Ratio |
|----------|-----------|-------|
| Portrait (phone) | 720 x 1280 | 9:16 |
| Landscape | 1280 x 720 | 16:9 |
| Square | 1024 x 1024 | 1:1 |
| Photo portrait | 832 x 1216 | 2:3 |
| Photo landscape | 1216 x 832 | 3:2 |

### Prompt Tips for Z-Image Turbo

- Write prompts as **natural-language descriptions**, not comma-separated tags
- Put the most important elements first
- Use camera/photography terms: `"85mm lens"`, `"shallow depth of field"`, `"golden hour"`, `"film grain"`
- Include quality anchors: `"sharp focus, correct human anatomy, highly detailed, photorealistic, no blur, no artifacts"`
- Be specific: exact age, clothing materials, colors, textures
- Optimal prompt length: **80–200 words**

---

## Video Generation (P-Video)

### Basic Usage (Image-to-Video)

```python
async def generate_video(image_url: str, prompt: str):
    runware = Runware(api_key="YOUR_API_KEY")
    await runware.connect()

    request = IVideoInference(
        model="prunaai:p-video@0",
        positivePrompt=prompt,
        duration=5,
        resolution="720p",
        outputFormat="MP4",
        includeCost=True,
        inputs=IVideoInputs(
            frameImages=[{
                "inputImage": image_url,
                "frame": "first",
            }]
        ),
        settings=ISettings(
            draft=True,        # Faster, cheaper
            audio=True,        # Generate audio from prompt
        ),
    )

    result = await runware.videoInference(requestVideo=request)

    # P-Video is async — poll for result
    if isinstance(result, IAsyncTaskResponse):
        videos = await runware.getResponse(taskUUID=result.taskUUID)
    else:
        videos = result

    video_url = videos[0].videoURL
    cost = sum(getattr(v, "cost", 0) or 0 for v in videos)
    print(f"Video: {video_url}, Cost: ${cost}")
```

### P-Video Settings

| Setting | Type | Default | Effect |
|---------|------|---------|--------|
| `draft` | bool | False | Faster generation, lower quality |
| `audio` | bool | False | Generate audio (dialogue, ambient sound) from prompt |
| `promptUpsampling` | bool | False | AI-enhance the prompt before generating |

### Input Image Formats

P-Video accepts the source image in three formats:

```python
# 1. Public URL
"inputImage": "https://example.com/image.png"

# 2. Runware UUID (from a previous image generation)
"inputImage": "550e8400-e29b-41d4-a716-446655440000"

# 3. Base64 data URI
"inputImage": "data:image/png;base64,iVBORw0KGgo..."
```

### Video Prompt Tips

The video prompt should describe **motion + audio**, not the scene (the scene comes from the source image):

```
"She leans closer, eyes narrowing, and whispers 'I warned you, Marco.'
Wind stirs her dark hair, warm candlelight flickers across her face,
slow camera push-in."
```

Combine:
- **Subtle motion**: camera drift, hair movement, breathing, turning
- **Spoken dialogue**: what characters say (when `audio=True`)
- **Ambient sound**: rain, wind, footsteps, music cues
- Keep it **1–3 sentences**

### Other Video Models

For non-P-Video models, the API is slightly different:

```python
# LTX-2 Fast / Vidu
request = IVideoInference(
    model="lightricks:2@1",     # or "vidu:4@2"
    positivePrompt="your prompt",
    duration=5,
    width=1280,                  # Required (no "resolution" param)
    height=720,
    outputFormat="MP4",
    includeCost=True,
    frameImages=[IFrameImage(inputImage=image_url, frame="first")],
)
```

| Model | AIR ID | Resolution | Audio | Draft |
|-------|--------|-----------|-------|-------|
| P-Video (Pruna) | `prunaai:p-video@0` | 720p / 1080p | Yes | Yes |
| LTX-2 Fast | `lightricks:2@1` | Custom w/h | No | No |
| Vidu Q2 Turbo | `vidu:3@2` | Custom w/h | No | No |
| Vidu Q3 Turbo | `vidu:4@2` | Custom w/h | No | No |

### Video Resolutions

**P-Video** uses `resolution` param: `"720p"` or `"1080p"`

**Other models** use explicit `width`/`height`:

| Label | Dimensions |
|-------|-----------|
| 720p 16:9 | 1280 x 720 |
| 720p 9:16 | 720 x 1280 |
| 1080p 16:9 | 1920 x 1080 |
| 1080p 9:16 | 1080 x 1920 |

---

## Uploaded LoRA Models

All LoRAs are uploaded for the `z_image_turbo` architecture.

| Name | AIR ID | Description |
|------|--------|-------------|
| ZIT NSFW LoRA v2 | `warmline:2279079@2637792` | CivitAI NSFW style |
| Futagrow | `warmline:202603120001@1` | Futa/transformation |
| NakedErectFutaZit | `warmline:202603120002@1` | NSFW combo style |
| NSFW Hentai | `warmline:202603150001@1` | Hentai/anime NSFW style |
| PWFP | `warmline:202603150002@1` | PWFP character |
| Milena | `warmline:202603170001@1` | Milena character |
| Nataly | `warmline:202603170002@1` | Nataly character (trigger: `N@T@LY`) |
| NS Unlocked V1 | `warmline:202603170003@1` | NSFW unrestricted |
| ZTurbo Pen V3 | `warmline:202603170004@1` | Pen/drawing artistic style |
| Shorty Asian | `warmline:202603200001@1` | Asian character (trigger: `sh0r7y_asian`) |
| ZiT Blonde Cacu | `warmline:202603200002@1` | Blonde character (trigger: `b10ndi`) |
| NS Master ZIT | `warmline:202603200003@1` | NS Master style |
| FutaV4 | `warmline:202603220001@1` | Futa V4 style |
| Dog (dgz) | `warmline:202603220002@1` | Dog style (trigger: `dgz`) |
| Blow (bjz) | `warmline:202603220003@1` | Blow style (trigger: `bjz`) |
| Missio | `warmline:202603220004@1` | Missio style |

### Using a Character LoRA

Character LoRAs (Milena, Nataly, PWFP, Shorty Asian, ZiT Blonde Cacu) generate images of a specific person. Combine with a descriptive prompt:

```python
request = IImageInference(
    model="runware:z-image@turbo",
    positivePrompt="25-year-old woman with dark wavy hair, wearing a red silk dress, "
                   "standing in a candlelit ballroom, soft warm lighting, 85mm lens, "
                   "shallow depth of field, photorealistic, sharp focus, no blur",
    width=720,
    height=1280,
    steps=8,
    CFGScale=0,
    lora=[ILora(model="warmline:202603170001@1", weight=1.0)],  # Milena
    includeCost=True,
)
```

### Using a Style LoRA

Style LoRAs (ZTurbo Pen V3, NSFW Hentai) change the rendering style:

```python
lora=[ILora(model="warmline:202603170004@1", weight=0.7)]   # Pen style at 70%
```

Lower weights (0.3–0.7) give a subtle style influence. Weight 1.0+ for full style takeover.

### Combining Multiple LoRAs

You can stack a character LoRA + a style LoRA:

```python
lora=[
    ILora(model="warmline:202603170001@1", weight=1.0),   # Milena (character)
    ILora(model="warmline:202603170004@1", weight=0.5),   # Pen style (subtle)
]
```

---

## Uploading New LoRAs

See [upload-lora-guide.md](./upload-lora-guide.md) for the full process. Quick summary:

```bash
# 1. Host the file (catbox.moe for <200MB, litterbox for <1GB)
curl -s -F "reqtype=fileupload" -F "fileToUpload=@your_lora.safetensors" https://catbox.moe/user/api.php

# 2. Register on Runware (Python)
```

```python
result = await runware.modelUpload(IUploadModelLora(
    air="warmline:202603200001@1",          # Next available ID
    architecture="z_image_turbo",
    name="My New LoRA",
    downloadURL="https://files.catbox.moe/abc123.safetensors",
    uniqueIdentifier="my-new-lora-v1",
    version="1.0",
    format="safetensors",
    private=True,
    defaultWeight=1.0,
    shortDescription="What it does",
))
```

AIR ID convention: `warmline:YYYYMMDDNNNN@1` (date + counter).

---

## Complete Example: Image + Video Pipeline

```python
import asyncio
from runware import Runware, IImageInference, ILora
from runware.types import IVideoInference, IVideoInputs, ISettings, IAsyncTaskResponse

API_KEY = "YOUR_API_KEY"

async def generate_scene():
    runware = Runware(api_key=API_KEY)
    await runware.connect()

    # Step 1: Generate image
    image_request = IImageInference(
        model="runware:z-image@turbo",
        positivePrompt=(
            "POV, first person view, 32-year-old woman resembling Natalie Portman, "
            "dark wavy hair, wearing a black leather jacket over cream silk blouse, "
            "standing in a dimly lit gothic manor hallway, warm candlelight, "
            "85mm lens, shallow depth of field, photorealistic, sharp focus, "
            "correct human anatomy, no blur, no artifacts"
        ),
        width=720,
        height=1280,
        steps=8,
        CFGScale=0,
        outputFormat="PNG",
        includeCost=True,
        lora=[ILora(model="warmline:202603170003@1", weight=0.5)],  # NS Unlocked
    )

    images = await runware.imageInference(requestImage=image_request)
    image_url = images[0].imageURL
    print(f"Image: {image_url} (${images[0].cost})")

    # Step 2: Animate with P-Video
    video_request = IVideoInference(
        model="prunaai:p-video@0",
        positivePrompt=(
            "She leans closer and whispers 'Follow me.' "
            "Candlelight flickers, slow camera push-in, ambient creaking."
        ),
        duration=5,
        resolution="720p",
        outputFormat="MP4",
        includeCost=True,
        inputs=IVideoInputs(
            frameImages=[{"inputImage": image_url, "frame": "first"}]
        ),
        settings=ISettings(draft=True, audio=True),
    )

    result = await runware.videoInference(requestVideo=video_request)
    if isinstance(result, IAsyncTaskResponse):
        videos = await runware.getResponse(taskUUID=result.taskUUID)
    else:
        videos = result

    video_url = videos[0].videoURL
    video_cost = sum(getattr(v, "cost", 0) or 0 for v in videos)
    print(f"Video: {video_url} (${video_cost})")

asyncio.run(generate_scene())
```

---

## Existing Apps Using This Stack

| App | Location | Description |
|-----|----------|-------------|
| **Gradio Playground** | `./app.py` | Standalone image/video generator with full LoRA support. Run: `python app.py` |
| **Visual Novel** | `./visual-novel/` | Interactive AI visual novel (Next.js + FastAPI). Backend: `uvicorn main:app --reload --port 8000`, Frontend: `npm run dev` |
| **VisualHeat** | `./VisualHeat/` | AI storyboard tool. Same stack as visual-novel |
