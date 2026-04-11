# How to Upload a Custom LoRA to Runware

## Prerequisites

- A Runware account with API key
- The Runware Python SDK installed (`pip install runware`)
- Your LoRA `.safetensors` file

## Step 1: Host the LoRA file at a public URL

The Runware API requires a **download URL** — it doesn't support direct file uploads.

### Recommended: catbox.moe (up to 200MB, no account needed)

```bash
# Copy to /tmp with .bin extension (optional, catbox accepts .safetensors too)
cp your_lora.safetensors /tmp/your_lora.bin

# Upload — returns a direct download URL
curl -s -F "reqtype=fileupload" -F "fileToUpload=@/tmp/your_lora.bin" https://catbox.moe/user/api.php
# → https://files.catbox.moe/abc123.bin
```

The returned URL is already a direct download link — no conversion needed.

### For files over 200MB: litterbox.catbox.moe (up to 1GB, expires after 72h)

```bash
curl -s -F "reqtype=fileupload" -F "time=72h" \
  -F "fileToUpload=@/tmp/your_lora.bin" \
  https://litterbox.catbox.moe/resources/internals/api.php
# → https://litter.catbox.moe/abc123.bin
```

72 hours is plenty — Runware downloads the file within seconds of the upload call.

### Hosts that DON'T work for large files

| Host | Issue |
|------|-------|
| **tmpfiles.org** | 413 Payload Too Large for files > ~100MB |
| **file.io** | 301 redirect loop |
| **transfer.sh** | SSL errors (exit code 35) |
| **0x0.st** | Blocks automated uploads (user-agent check) |
| **oshi.at** | Self-signed certificate |
| **bashupload.com** | 404 |

### CivitAI LoRAs

If your LoRA is on CivitAI, use their download URL directly:

```
https://civitai.com/api/download/models/<VERSION_ID>?type=Model&format=SafeTensor
```

> **Note:** CivitAI downloads may require an API token and can be slow, causing timeouts.

## Step 2: Upload via the SDK

```python
import asyncio
from runware import Runware
from runware.types import IUploadModelLora

API_KEY = "YOUR_API_KEY"

async def upload_lora():
    runware = Runware(api_key=API_KEY)
    await runware.connect()

    result = await asyncio.wait_for(
        runware.modelUpload(IUploadModelLora(
            air="warmline:YOUR_ID@YOUR_VERSION",   # AIR identifier (format: digits@digits)
            architecture="z_image_turbo",            # Must match the base model
            name="My Custom LoRA",                   # Display name
            downloadURL="https://files.catbox.moe/abc123.bin",
            uniqueIdentifier="my-custom-lora-v1",    # Unique slug
            version="1.0",
            format="safetensors",
            private=True,                            # Only visible to your account
            defaultWeight=1.0,
            shortDescription="Description of what this LoRA does",
            # positiveTriggerWords="trigger word",   # Optional: if the LoRA requires a trigger
        )),
        timeout=300,  # 5 min timeout
    )
    print("Upload result:", result)

asyncio.run(upload_lora())
```

### AIR ID convention for this project

We use `warmline:YYYYMMDDNNNN@VERSION` as AIR IDs:

| LoRA | AIR ID |
|------|--------|
| ZIT NSFW LoRA v2 (CivitAI) | `warmline:2279079@2637792` |
| Futagrow | `warmline:202603120001@1` |
| NakedErectFutaZit | `warmline:202603120002@1` |
| NSFW Hentai (z-image-turbo) | `warmline:202603150001@1` |
| PWFP | `warmline:202603150002@1` |
| Milena (character) | `warmline:202603170001@1` |
| Nataly (character) | `warmline:202603170002@1` |
| NS Unlocked V1 | `warmline:202603170003@1` |
| ZTurbo Pen V3 | `warmline:202603170004@1` |
| Shorty Asian (character, trigger: `sh0r7y_asian`) | `warmline:202603200001@1` |
| ZiT Blonde Cacu (character, trigger: `b10ndi`) | `warmline:202603200002@1` |
| NS Master ZIT (style) | `warmline:202603200003@1` |

For new uploads, increment the counter: `warmline:YYYYMMDD0003@1`, etc.

### Parameter reference

| Parameter            | Required | Description                                                              |
|----------------------|----------|--------------------------------------------------------------------------|
| `air`                | Yes      | AIR identifier. Format: `prefix:id@version` (e.g. `warmline:123@456`)   |
| `architecture`       | Yes      | Must match the base model (e.g. `z_image_turbo`, `flux1d`, `sdxl`)      |
| `name`               | Yes      | Human-readable name                                                      |
| `downloadURL`        | Yes      | Public URL to the `.safetensors` file                                    |
| `uniqueIdentifier`   | Yes      | Unique slug for this model                                               |
| `version`            | Yes      | Version string (e.g. `"1.0"`)                                           |
| `format`             | Yes      | File format: `"safetensors"`                                             |
| `private`            | Yes      | `True` = only your account, `False` = public                            |
| `defaultWeight`      | No       | Default LoRA weight (1.0 recommended)                                    |
| `shortDescription`   | No       | Brief description (min 2 chars)                                          |
| `positiveTriggerWords`| No      | Trigger words needed to activate the LoRA                                |

## Step 3: Add to the visual novel app

After upload returns `status: 'ready'`, add the LoRA to `visual-novel/backend/routers/costs.py`:

```python
AVAILABLE_LORAS = [
    {"id": "", "name": "None"},
    {"id": "warmline:2279079@2637792", "name": "ZIT NSFW LoRA v2"},
    # ... add your new entry:
    {"id": "warmline:YOUR_ID@YOUR_VERSION", "name": "Your LoRA Name"},
]
```

The backend auto-reloads. The new LoRA appears in the settings dropdown immediately.

## Step 4 (optional): Use in code directly

```python
from runware import IImageInference, ILora

request = IImageInference(
    positivePrompt="your prompt here",
    model="runware:z-image@turbo",
    width=1024,
    height=1024,
    steps=8,
    CFGScale=0,
    lora=[ILora(model="warmline:YOUR_ID@YOUR_VERSION", weight=1.0)],
)
```

## Important notes

- **Architecture must match**: A LoRA trained for `flux1d` won't work with `z_image_turbo` and vice versa. The API will return `unsupportedLoraModel` if there's a mismatch.
- **AIR format**: The `air` field prefix (`warmline:`, `terrapinbear:`, etc.) is your namespace. The `id@version` part must be digits.
- **CivitAI LoRAs**: Not all CivitAI LoRAs are pre-registered on Runware. If you get `invalidLoraModel`, you need to upload it first using this process.
- **Finding compatible LoRAs**: Use the model search API to find LoRAs already available for your architecture:

```python
from runware.types import IModelSearch

results = await runware.modelSearch(
    IModelSearch(category="lora", architecture="z_image_turbo", limit=10)
)
for m in results.results:
    print(m.air, m.name)
```
