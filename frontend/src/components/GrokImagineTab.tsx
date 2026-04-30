import { useState, useRef, useMemo, useEffect } from 'react'
import { grokImagineEdit, grokImagineGenerate, type GrokImagineEditResult } from '../api/client'

type ImagineMode = 'generate' | 'edit'
type ImagineBackend = 'venice' | 'xai'

// xAI's documented set; Venice's enum is a subset (no 19.5:9 or 20:9 etc).
// We expose the full union — backend will reject unsupported ratios with a
// clear error message in the response panel.
const ASPECT_RATIOS = [
  '', '1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3',
  '2:1', '1:2', '21:9', '4:5', '19.5:9', '9:19.5', '20:9', '9:20', 'auto',
]

// Datalist suggestions per backend; users can type any string for new models.
const MODEL_SUGGESTIONS: Record<ImagineBackend, Record<ImagineMode, string[]>> = {
  venice: {
    generate: ['grok-imagine-image', 'qwen-image-2-pro', 'flux-2-max', 'firered-image'],
    edit:     ['grok-imagine-edit', 'qwen-image-2-pro-edit', 'flux-2-max-edit', 'firered-image-edit', 'nano-banana-pro-edit'],
  },
  xai: {
    generate: ['grok-imagine-image', 'grok-imagine-image-pro'],
    edit:     ['grok-imagine-image'],
  },
}

const defaultModelFor = (backend: ImagineBackend, mode: ImagineMode): string => MODEL_SUGGESTIONS[backend][mode][0]

export default function GrokImagineTab() {
  const [backend, setBackend] = useState<ImagineBackend>('venice')
  const [mode, setMode] = useState<ImagineMode>('generate')
  const [imageMode, setImageMode] = useState<'url' | 'upload'>('upload')
  const [imageUrl, setImageUrl] = useState('')
  const [uploadDataUri, setUploadDataUri] = useState('')
  const [uploadName, setUploadName] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState<string>(defaultModelFor('venice', 'generate'))
  const [modelTouched, setModelTouched] = useState(false)
  const [aspectRatio, setAspectRatio] = useState('')

  // xAI-specific
  const [n, setN] = useState<number | ''>('')
  const [quality, setQuality] = useState<string>('')      // '' | 'low' | 'medium' | 'high'
  const [resolution, setResolution] = useState<string>('') // '' | '1k' | '2k'
  const [responseFormat, setResponseFormat] = useState<string>('')

  // Venice-specific
  const [safeMode, setSafeMode] = useState<string>('')    // '' = backend default | 'true' | 'false'
  const [negativePrompt, setNegativePrompt] = useState('')
  const [seed, setSeed] = useState<number | ''>('')
  const [steps, setSteps] = useState<number | ''>('')
  const [cfgScale, setCfgScale] = useState<number | ''>('')
  const [imgFormat, setImgFormat] = useState<string>('')  // '' | 'png' | 'jpeg' | 'webp'

  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<GrokImagineEditResult | null>(null)
  const [error, setError] = useState('')
  const [showRaw, setShowRaw] = useState(false)

  // Auto-pick a sane default model when backend/mode changes (unless the user
  // has already manually edited the model field).
  useEffect(() => {
    if (!modelTouched) setModel(defaultModelFor(backend, mode))
  }, [backend, mode, modelTouched])

  const effectiveImageUrl = useMemo(
    () => (imageMode === 'url' ? imageUrl.trim() : uploadDataUri),
    [imageMode, imageUrl, uploadDataUri],
  )

  const handleUpload = (file: File) => {
    setUploadName(file.name)
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      setUploadDataUri(result) // already includes the "data:<mime>;base64," prefix
    }
    reader.readAsDataURL(file)
  }

  const handleSubmit = async () => {
    setError('')
    setResult(null)
    if (!prompt.trim()) {
      setError('Prompt is required.')
      return
    }
    if (mode === 'edit' && !effectiveImageUrl) {
      setError('Edit mode needs a source image (upload or URL).')
      return
    }
    setBusy(true)
    try {
      // Build params per backend; only include knobs the chosen backend supports.
      const safeModeBool = safeMode === '' ? null : safeMode === 'true'
      let r: GrokImagineEditResult
      if (mode === 'edit') {
        r = await grokImagineEdit({
          backend,
          image_url: effectiveImageUrl,
          prompt,
          model: model || null,
          aspect_ratio: aspectRatio || null,
          // xAI-only
          n: backend === 'xai' && n !== '' ? Number(n) : null,
          quality: backend === 'xai' ? (quality || null) : null,
          resolution: backend === 'xai' ? (resolution || null) : null,
          response_format: backend === 'xai' ? (responseFormat || null) : null,
          // Venice-only
          safe_mode: backend === 'venice' ? safeModeBool : null,
        })
      } else {
        r = await grokImagineGenerate({
          backend,
          prompt,
          model: model || null,
          aspect_ratio: aspectRatio || null,
          // xAI-only
          n: backend === 'xai' && n !== '' ? Number(n) : null,
          quality: backend === 'xai' ? (quality || null) : null,
          resolution: backend === 'xai' ? (resolution || null) : null,
          response_format: backend === 'xai' ? (responseFormat || null) : null,
          // Venice-only
          negative_prompt: backend === 'venice' ? (negativePrompt || null) : null,
          safe_mode: backend === 'venice' ? safeModeBool : null,
          cfg_scale: backend === 'venice' && cfgScale !== '' ? Number(cfgScale) : null,
          seed: backend === 'venice' && seed !== '' ? Number(seed) : null,
          steps: backend === 'venice' && steps !== '' ? Number(steps) : null,
          format: backend === 'venice' ? (imgFormat || null) : null,
        })
      }
      setResult(r)
      if (!r.ok && r.error) {
        setError(r.error)
      }
    } catch (e: any) {
      setError(e?.message || 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  // Convenience: build a renderable img src for either b64 or URL output.
  const imageSrc = (img: { url: string; b64_json: string; mime_type: string }) => {
    if (img.url) return img.url
    if (img.b64_json) return `data:${img.mime_type || 'image/png'};base64,${img.b64_json}`
    return ''
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ── Left: inputs ── */}
      <div className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-sm font-semibold text-amber-400">Grok Imagine</h2>
          <p className="text-[11px] text-neutral-500 leading-relaxed">
            {backend === 'venice' ? (
              <>
                Direct call to <code className="text-neutral-400">POST https://api.venice.ai/api/v1/image/{mode === 'edit' ? 'edit' : 'generate'}</code>{' '}
                with your <code className="text-neutral-400">VENICE_INFERENCE_KEY</code>.
              </>
            ) : (
              <>
                Direct call to <code className="text-neutral-400">POST https://api.x.ai/v1/images/{mode === 'edit' ? 'edits' : 'generations'}</code>{' '}
                with your <code className="text-neutral-400">XAI_API_KEY</code>.
              </>
            )}{' '}
            Manual playground — pick backend, model, aspect ratio,
            {mode === 'edit' ? ' upload (or link) a source image,' : ''} write the prompt,
            and inspect the response. Full raw JSON is shown for debugging.
          </p>
        </div>

        {/* Backend toggle — pivotal: changes endpoint, default model, request shape */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Backend</span>
          <div className="flex bg-neutral-900 rounded-lg p-0.5 w-fit">
            <button
              onClick={() => { setBackend('venice'); setModelTouched(false) }}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${backend === 'venice' ? 'bg-emerald-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
              title="Venice (api.venice.ai) — flat image field, grok-imagine-edit, returns binary PNG"
            >Venice</button>
            <button
              onClick={() => { setBackend('xai'); setModelTouched(false) }}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${backend === 'xai' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
              title="xAI direct (api.x.ai) — nested image.url, grok-imagine-image"
            >xAI direct</button>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono ml-3">Mode</span>
          <div className="flex bg-neutral-900 rounded-lg p-0.5 w-fit">
            <button
              onClick={() => { setMode('generate'); setModelTouched(false) }}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${mode === 'generate' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
              title="Text-to-image"
            >Generate</button>
            <button
              onClick={() => { setMode('edit'); setModelTouched(false) }}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${mode === 'edit' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
              title="Image-to-image"
            >Edit</button>
          </div>
        </div>

        {/* Image source — only in Edit mode */}
        {mode === 'edit' && (
        <div className="space-y-2 p-3 rounded-lg border border-neutral-800 bg-neutral-950/50">
          <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Source image</label>
          <div className="flex bg-neutral-900 rounded p-0.5 w-fit">
            <button
              onClick={() => setImageMode('upload')}
              className={`px-2.5 py-1 text-[11px] rounded transition-colors ${imageMode === 'upload' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
            >Upload file</button>
            <button
              onClick={() => setImageMode('url')}
              className={`px-2.5 py-1 text-[11px] rounded transition-colors ${imageMode === 'url' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
            >Public URL</button>
          </div>
          {imageMode === 'upload' ? (
            <div className="space-y-2">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-full px-3 py-2 bg-neutral-900 border border-neutral-800 hover:border-amber-700 rounded text-[12px] text-neutral-300 text-left"
              >
                {uploadName ? `📎 ${uploadName}` : 'Click to choose an image (.png / .jpg / .webp)'}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) handleUpload(f)
                }}
              />
              {uploadDataUri && (
                <div className="text-[10px] text-neutral-600 font-mono">
                  base64 data URI · {(uploadDataUri.length / 1024).toFixed(1)} KB
                </div>
              )}
            </div>
          ) : (
            <input
              type="text"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder="https://…/image.png"
              className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-[12px] text-neutral-200 focus:border-amber-600 focus:outline-none"
            />
          )}

          {/* Source preview */}
          {effectiveImageUrl && (
            <div className="pt-2">
              <div className="text-[10px] text-neutral-600 font-mono mb-1">Preview</div>
              <img
                src={effectiveImageUrl}
                alt="source"
                className="rounded border border-neutral-800 max-h-48 object-contain bg-neutral-900/50"
              />
            </div>
          )}
        </div>
        )}

        {/* Prompt */}
        <div className="space-y-1">
          <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
            {mode === 'edit' ? 'Edit prompt' : 'Generation prompt'}
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            placeholder='e.g. "Render this as a pencil sketch with detailed shading"'
            className="w-full bg-neutral-950 border border-neutral-800 rounded p-2 text-[12px] text-neutral-200 font-mono focus:border-amber-600 focus:outline-none resize-y"
          />
        </div>

        {/* Settings grid — shared knobs */}
        <div className="grid grid-cols-2 gap-3 p-3 rounded-lg border border-neutral-800 bg-neutral-950/50">
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
              Model {!modelTouched && <span className="text-neutral-700">(auto)</span>}
            </label>
            <input
              list="grok-imagine-models"
              value={model}
              onChange={(e) => { setModel(e.target.value); setModelTouched(true) }}
              className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 font-mono focus:border-amber-600 focus:outline-none"
            />
            <datalist id="grok-imagine-models">
              {MODEL_SUGGESTIONS[backend][mode].map((m) => <option key={m} value={m} />)}
            </datalist>
          </div>

          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Aspect ratio</label>
            <select
              value={aspectRatio}
              onChange={(e) => setAspectRatio(e.target.value)}
              className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 focus:border-amber-600 focus:outline-none"
            >
              {ASPECT_RATIOS.map((r) => <option key={r} value={r}>{r || '(default / inherit)'}</option>)}
            </select>
          </div>

          {/* xAI-only knobs */}
          {backend === 'xai' && (
            <>
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Quality (xAI)</label>
                <select
                  value={quality}
                  onChange={(e) => setQuality(e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 focus:border-amber-600 focus:outline-none"
                >
                  <option value="">(default)</option>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Resolution (xAI)</label>
                <select
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 focus:border-amber-600 focus:outline-none"
                >
                  <option value="">(default)</option>
                  <option value="1k">1k</option>
                  <option value="2k">2k</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">n / count (xAI)</label>
                <input
                  type="number" min={1} max={4} step={1}
                  value={n}
                  onChange={(e) => setN(e.target.value === '' ? '' : Number(e.target.value))}
                  placeholder="(default 1)"
                  className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 font-mono focus:border-amber-600 focus:outline-none"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Response format (xAI)</label>
                <select
                  value={responseFormat}
                  onChange={(e) => setResponseFormat(e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 focus:border-amber-600 focus:outline-none"
                >
                  <option value="">(default — url)</option>
                  <option value="b64_json">b64_json (inline base64)</option>
                </select>
              </div>
            </>
          )}

          {/* Venice knobs (always visible when backend=venice; some are
              generate-only — Venice's edit endpoint only documents
              safe_mode + aspect_ratio + model). */}
          {backend === 'venice' && (
            <>
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Safe mode (Venice)</label>
                <select
                  value={safeMode}
                  onChange={(e) => setSafeMode(e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 focus:border-amber-600 focus:outline-none"
                  title="Venice default is true (blurs adult content). Set false for explicit work."
                >
                  <option value="">(default — true, blurs adult)</option>
                  <option value="true">true (blur adult)</option>
                  <option value="false">false (no blur)</option>
                </select>
              </div>

              {mode === 'generate' && (
                <>
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Format (Venice)</label>
                    <select
                      value={imgFormat}
                      onChange={(e) => setImgFormat(e.target.value)}
                      className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 focus:border-amber-600 focus:outline-none"
                    >
                      <option value="">(default — webp)</option>
                      <option value="png">png</option>
                      <option value="jpeg">jpeg</option>
                      <option value="webp">webp</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">CFG scale (Venice)</label>
                    <input
                      type="number" min={0} max={20} step={0.5}
                      value={cfgScale}
                      onChange={(e) => setCfgScale(e.target.value === '' ? '' : Number(e.target.value))}
                      placeholder="(default 7.5)"
                      className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 font-mono focus:border-amber-600 focus:outline-none"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Steps (Venice)</label>
                    <input
                      type="number" min={1} max={50} step={1}
                      value={steps}
                      onChange={(e) => setSteps(e.target.value === '' ? '' : Number(e.target.value))}
                      placeholder="(default 8)"
                      className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 font-mono focus:border-amber-600 focus:outline-none"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Seed (Venice)</label>
                    <input
                      type="number"
                      value={seed}
                      onChange={(e) => setSeed(e.target.value === '' ? '' : Number(e.target.value))}
                      placeholder="(random)"
                      className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[11px] text-neutral-300 font-mono focus:border-amber-600 focus:outline-none"
                    />
                  </div>
                </>
              )}
            </>
          )}
        </div>

        {/* Venice-generate-only: negative prompt (full width) */}
        {backend === 'venice' && mode === 'generate' && (
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Negative prompt (Venice)</label>
            <textarea
              value={negativePrompt}
              onChange={(e) => setNegativePrompt(e.target.value)}
              rows={2}
              placeholder='e.g. "blurry, low quality, watermark, text"'
              className="w-full bg-neutral-950 border border-neutral-800 rounded p-2 text-[11px] text-neutral-200 font-mono focus:border-amber-600 focus:outline-none resize-y"
            />
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={busy || !prompt.trim() || (mode === 'edit' && !effectiveImageUrl)}
          className="w-full px-4 py-2.5 bg-amber-700 hover:bg-amber-600 disabled:opacity-30 disabled:cursor-not-allowed rounded text-sm font-medium text-white transition-colors"
        >
          {busy ? 'Calling xAI…' : (mode === 'edit' ? '▶ Edit image' : '▶ Generate image')}
        </button>

        {error && (
          <div className="p-3 rounded border border-red-900/60 bg-red-950/30 text-[12px] text-red-300 font-mono whitespace-pre-wrap">
            {error}
          </div>
        )}
      </div>

      {/* ── Right: result ── */}
      <div className="space-y-3">
        {!result && !busy && (
          <div className="border border-neutral-800 rounded-lg p-6 text-center text-[12px] text-neutral-600">
            No result yet.
          </div>
        )}
        {busy && (
          <div className="border border-amber-900/40 rounded-lg p-6 text-center text-[12px] text-amber-500 font-mono">
            Waiting on xAI…
          </div>
        )}

        {result && (
          <>
            {/* Status strip */}
            <div className={`p-2.5 rounded border text-[11px] font-mono ${result.ok ? 'border-emerald-900/50 bg-emerald-950/20 text-emerald-300' : 'border-red-900/50 bg-red-950/20 text-red-300'}`}>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <span>status: <span className="text-neutral-100">{result.ok ? 'OK' : `ERROR ${result.status_code ?? ''}`}</span></span>
                <span>elapsed: <span className="text-neutral-100">{result.elapsed}s</span></span>
                {result.model && <span>model: <span className="text-neutral-100">{result.model}</span></span>}
                {result.cost_usd != null && (
                  <span>cost: <span className="text-neutral-100">${result.cost_usd.toFixed(6)}</span></span>
                )}
                {result.usage && Object.keys(result.usage).length > 0 && (
                  <span>usage: <span className="text-neutral-100">{JSON.stringify(result.usage)}</span></span>
                )}
              </div>
            </div>

            {/* Generated images */}
            {result.images && result.images.length > 0 && (
              <div className="space-y-3">
                {result.images.map((img, i) => (
                  <div key={i} className="space-y-1">
                    <div className="text-[10px] uppercase tracking-wider text-emerald-400 font-mono">
                      Result {i + 1}{img.mime_type ? ` · ${img.mime_type}` : ''}
                    </div>
                    {imageSrc(img) ? (
                      <img
                        src={imageSrc(img)}
                        alt={`result ${i + 1}`}
                        className="rounded border border-emerald-900/40 max-h-[60vh] object-contain bg-neutral-950"
                      />
                    ) : (
                      <div className="text-[11px] text-neutral-500 italic">No image data in this entry.</div>
                    )}
                    {img.revised_prompt && (
                      <div className="text-[10px] text-neutral-500 font-mono whitespace-pre-wrap p-2 rounded bg-neutral-950 border border-neutral-800">
                        <span className="text-neutral-700">revised_prompt:</span> {img.revised_prompt}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Error response details (if not ok) */}
            {!result.ok && result.response && (
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider text-red-400 font-mono">xAI error response</div>
                <pre className="text-[10px] text-red-300 font-mono whitespace-pre-wrap p-2 rounded bg-red-950/20 border border-red-900/40 overflow-auto max-h-60">
                  {JSON.stringify(result.response, null, 2)}
                </pre>
              </div>
            )}

            {/* Raw response (collapsible) */}
            <div>
              <button
                onClick={() => setShowRaw(v => !v)}
                className="text-[10px] text-neutral-500 hover:text-neutral-300 font-mono"
              >
                {showRaw ? '▼' : '▶'} raw response
              </button>
              {showRaw && (
                <pre className="mt-1 text-[10px] text-neutral-400 font-mono whitespace-pre-wrap p-2 rounded bg-neutral-950 border border-neutral-800 overflow-auto max-h-96">
                  {JSON.stringify(result, null, 2)}
                </pre>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
