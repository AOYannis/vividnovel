import { useState, useEffect, useRef } from 'react'
import { useGameStore } from '../stores/gameStore'
import {
  fetchPlaygroundConfig, generatePlayground, manualGenerate, playgroundVideo,
  playgroundTTS, playgroundTTSEnhance, playgroundAudioVideo,
} from '../api/client'
import IterateTab from '../components/IterateTab'

interface PlaygroundConfig {
  actors: { code: string; name: string; description: string }[]
  settings: { id: string; name: string }[]
  moods: Record<string, { description: string; prompt_block: string; lora: { id: string; name: string; weight: number } | null }>
  loras: { id: string; name: string; type: string }[]
  defaults: { width: number; height: number; steps: number }
  languages: string[]
  tts?: {
    voices: { id: string; label: string }[]
    languages: string[]
  }
}

interface ImageResult {
  url: string
  cost: number
  seed: number | null
  elapsed: number
  settings: {
    width: number; height: number; steps: number; cfg: number
    loras: { id: string; weight: number }[]
    style_moods?: string[]
    final_prompt: string
  }
}

interface SimResult {
  simulated_prompt: string
  actors_present: string[]
  style_moods: string[]
  narration: string
  image: ImageResult | null
  image_error?: string
}

type Mode = 'simulate' | 'manual' | 'video' | 'speech' | 'iterate'

function LoraEditor({ loras, available, onChange }: {
  loras: { id: string; weight: number }[]
  available: { id: string; name: string }[]
  onChange: (loras: { id: string; weight: number }[]) => void
}) {
  return (
    <div className="space-y-1.5">
      {loras.map((lo, i) => (
        <div key={i} className="flex items-center gap-2">
          <select
            value={lo.id}
            onChange={(e) => {
              const next = [...loras]; next[i] = { ...next[i], id: e.target.value }; onChange(next)
            }}
            className="flex-1 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-amber-600 focus:outline-none"
          >
            {available.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
          <input
            type="number" value={lo.weight} step={0.05} min={-4} max={4}
            onChange={(e) => {
              const next = [...loras]; next[i] = { ...next[i], weight: parseFloat(e.target.value) || 0.8 }; onChange(next)
            }}
            className="w-16 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-amber-600 focus:outline-none"
          />
          <button onClick={() => onChange(loras.filter((_, j) => j !== i))}
            className="text-neutral-600 hover:text-red-400 text-xs transition-colors">x</button>
        </div>
      ))}
      <button
        onClick={() => available[0] && onChange([...loras, { id: available[0].id, weight: 0.8 }])}
        className="text-[10px] text-amber-500 hover:text-amber-400 transition-colors"
      >+ add LoRA</button>
    </div>
  )
}

function ResultPanel({ image, config, onUseSeed }: {
  image: ImageResult
  config: PlaygroundConfig
  onUseSeed: (seed: number) => void
}) {
  return (
    <>
      <div className="relative rounded-lg overflow-hidden bg-neutral-900 border border-neutral-800/50">
        <img src={image.url} alt="Generated" className="w-full h-auto" style={{ maxHeight: '70vh', objectFit: 'contain' }} />
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-4 py-3">
          <div className="flex items-center gap-3 text-[10px] text-neutral-400 font-mono flex-wrap">
            <span>${image.cost?.toFixed(4)}</span>
            <span>{image.elapsed}s</span>
            <span>{image.settings.width}x{image.settings.height}</span>
            <span>steps={image.settings.steps}</span>
            <span>cfg={image.settings.cfg}</span>
            {image.seed && (
              <button onClick={() => onUseSeed(image.seed!)}
                className="text-amber-500 hover:text-amber-400 transition-colors cursor-pointer">
                seed={image.seed}
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="space-y-3">
        <div>
          <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">LoRAs applied</label>
          <div className="flex flex-wrap gap-1 mt-1">
            {image.settings.loras?.map((l, i) => {
              const name = config.loras.find((cl) => cl.id === l.id)?.name || l.id
              return (
                <span key={i} className="text-[10px] px-2 py-0.5 rounded bg-indigo-900/50 text-indigo-300 font-mono">
                  {name} <span className="text-indigo-500">@{l.weight}</span>
                </span>
              )
            })}
            {(!image.settings.loras || image.settings.loras.length === 0) && (
              <span className="text-[10px] text-neutral-600">none</span>
            )}
          </div>
        </div>
        <div>
          <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Final prompt sent</label>
          <pre className="mt-1 text-[10px] text-neutral-500 font-mono leading-relaxed bg-neutral-900/30 rounded-lg px-3 py-2 border border-neutral-800/30 whitespace-pre-wrap max-h-40 overflow-y-auto">
            {image.settings.final_prompt}
          </pre>
        </div>
      </div>
    </>
  )
}

export default function PlaygroundPage() {
  const reset = useGameStore((s) => s.reset)
  const [config, setConfig] = useState<PlaygroundConfig | null>(null)
  const [mode, setMode] = useState<Mode>('simulate')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // ── Simulate mode state ──
  const [scene, setScene] = useState('She leans closer in the candlelit salon, her eyes locked on yours.')
  const [actor, setActor] = useState('nataly')
  const [setting, setSetting] = useState('paris_2026')
  const [mood, setMood] = useState('neutral')
  const [language, setLanguage] = useState('en')
  const [customMoodBlock, setCustomMoodBlock] = useState('')
  const [customMoodLoras, setCustomMoodLoras] = useState<{ id: string; weight: number }[]>([])
  const [simLoraOverrides, setSimLoraOverrides] = useState<{ id: string; weight: number }[]>([])
  const [useSimOverrides, setUseSimOverrides] = useState(false)
  const [rawMode, setRawMode] = useState(false)
  const [simulatedPrompt, setSimulatedPrompt] = useState('')
  const [simResult, setSimResult] = useState<SimResult | null>(null)

  // ── Manual mode state ──
  const [manualBackend, setManualBackend] = useState<'runware' | 'wavespeed'>('runware')
  const [manualPrompt, setManualPrompt] = useState('')
  const [manualLoras, setManualLoras] = useState<{ id: string; weight: number }[]>([])
  const [manualResult, setManualResult] = useState<ImageResult | null>(null)

  // ── Video mode state ──
  const [videoBackend, setVideoBackend] = useState<'davinci' | 'pvideo'>('davinci')
  const [videoImageUrl, setVideoImageUrl] = useState('')
  const [videoPrompt, setVideoPrompt] = useState('')
  const [videoNarration, setVideoNarration] = useState('')
  const [videoSeconds, setVideoSeconds] = useState(10)
  const [videoDraft, setVideoDraft] = useState(false)
  const [videoAudio, setVideoAudio] = useState(true)
  const [videoSize, setVideoSize] = useState('720p')
  const [videoPromptUpsampling, setVideoPromptUpsampling] = useState(true)
  const [videoResult, setVideoResult] = useState<{
    video_data: string | null; video_url: string; job_id: string
    generation_time: number; elapsed: number; cost?: number; prompt_used: string; simulated: boolean
  } | null>(null)
  const [videoLoading, setVideoLoading] = useState(false)

  // ── Speech mode state ──
  const [speechConcept, setSpeechConcept] = useState('Une invitation chuchotée, intime: « Approche... ne dis rien. »')
  const [speechBrief, setSpeechBrief] = useState('intimate, breathy, slow')
  const [speechVoice, setSpeechVoice] = useState('ara')
  const [speechLanguage, setSpeechLanguage] = useState('fr')
  const [speechStereo, setSpeechStereo] = useState(true)
  const [speechPrompt, setSpeechPrompt] = useState('')
  const [speechAudioData, setSpeechAudioData] = useState<string | null>(null)
  const [speechAudioUrl, setSpeechAudioUrl] = useState('')
  const [speechAudioMeta, setSpeechAudioMeta] = useState<{ chars: number; cost: number; elapsed: number } | null>(null)
  const [speechEnhancing, setSpeechEnhancing] = useState(false)
  const [speechGenerating, setSpeechGenerating] = useState(false)
  const [speechVideoLoading, setSpeechVideoLoading] = useState(false)
  const [speechVideoData, setSpeechVideoData] = useState<string | null>(null)
  const [speechVideoUrl, setSpeechVideoUrl] = useState('')
  const [speechVideoMeta, setSpeechVideoMeta] = useState<{ cost: number; elapsed: number; prompt_used: string } | null>(null)
  const [speechVideoImageUrl, setSpeechVideoImageUrl] = useState('')
  const [speechVideoPrompt, setSpeechVideoPrompt] = useState('')
  const [speechVideoDraft, setSpeechVideoDraft] = useState(false)
  const [speechVideoResolution, setSpeechVideoResolution] = useState('720p')
  const [enhanceElapsed, setEnhanceElapsed] = useState<number | null>(null)
  const speechAudioRef = useRef<HTMLAudioElement>(null)

  // ── ControlNet state ──
  const [cnEnabled, setCnEnabled] = useState(false)
  // Auto-switch to fal when ControlNet enabled (Runware doesn't support it)
  const handleCnToggle = (enabled: boolean) => {
    setCnEnabled(enabled)
    if (enabled) setManualBackend('wavespeed')
  }
  const [cnType, setCnType] = useState('openpose_full')
  const [cnGuideUrl, setCnGuideUrl] = useState('')
  const [cnWeight, setCnWeight] = useState(1.0)
  const [cnStartPct, setCnStartPct] = useState(0)
  const [cnEndPct, setCnEndPct] = useState(100)
  const [cnMode, setCnMode] = useState('balanced')
  const [cnHandsFace, setCnHandsFace] = useState(true)

  // ── Shared state ──
  const [width, setWidth] = useState(768)
  const [height, setHeight] = useState(1152)
  const [steps, setSteps] = useState(8)
  const [cfg, setCfg] = useState(0)
  const [seed, setSeed] = useState('')
  const [history, setHistory] = useState<{ timestamp: number; url: string; prompt: string; mode: Mode }[]>([])

  const resultRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchPlaygroundConfig()
      .then((c) => {
        setConfig(c)
        setWidth(c.defaults.width)
        setHeight(c.defaults.height)
        setSteps(c.defaults.steps)
      })
      .catch((e) => setError(e.message))
  }, [])

  // When mood changes, prefill custom mood fields
  useEffect(() => {
    if (!config || mood === '__custom__') return
    const m = config.moods[mood]
    if (m) {
      setCustomMoodBlock(m.prompt_block || '')
      setCustomMoodLoras(m.lora ? [{ id: m.lora.id, weight: m.lora.weight }] : [])
    }
  }, [mood, config])

  const handleSimulate = async (skipImage: boolean) => {
    setLoading(true)
    setError('')
    try {
      const res = await generatePlayground({
        scene_description: scene,
        actor, setting,
        mood: mood === '__custom__' ? 'neutral' : mood,
        language,
        width, height, steps,
        seed: seed ? parseInt(seed) : null,
        lora_overrides: useSimOverrides && simLoraOverrides.length > 0 ? simLoraOverrides : null,
        skip_image: skipImage,
        raw_mode: rawMode,
        custom_mood_block: customMoodBlock || undefined,
      })
      setSimulatedPrompt(res.simulated_prompt)
      setSimResult(res)
      if (res.image) {
        setHistory((prev) => [{ timestamp: Date.now(), url: res.image!.url, prompt: scene, mode: 'simulate' }, ...prev].slice(0, 20))
      }
      if (!skipImage) setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleManualGenerate = async () => {
    if (!manualPrompt.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await manualGenerate({
        prompt: manualPrompt,
        backend: manualBackend,
        loras: manualLoras,
        width, height, steps, cfg,
        seed: seed ? parseInt(seed) : null,
        controlnet: cnEnabled && cnGuideUrl ? {
          type: cnType,
          guide_image: cnGuideUrl,
          weight: cnWeight,
          start_step_pct: cnStartPct,
          end_step_pct: cnEndPct,
          control_mode: cnMode,
          include_hands_face: cnHandsFace,
        } : null,
      })
      setManualResult(res)
      setHistory((prev) => [{ timestamp: Date.now(), url: res.url, prompt: manualPrompt.slice(0, 50), mode: 'manual' }, ...prev].slice(0, 20))
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleVideoGenerate = async () => {
    if (!videoImageUrl.trim()) return
    setVideoLoading(true)
    setError('')
    setVideoResult(null)
    try {
      const res = await playgroundVideo({
        image_url: videoImageUrl,
        prompt: videoPrompt || undefined,
        narration: videoNarration || undefined,
        seconds: videoSeconds,
        backend: videoBackend,
        draft: videoDraft,
        audio: videoAudio,
        size: videoSize,
        prompt_upsampling: videoPromptUpsampling,
      })
      setVideoResult(res)
      // Populate prompt field so user can edit and regenerate
      if (res.prompt_used && !videoPrompt) setVideoPrompt(res.prompt_used)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setVideoLoading(false)
    }
  }

  // Use last generated image URL for video mode
  const useImageForVideo = (url: string) => {
    setVideoImageUrl(url)
    setMode('video')
  }

  // ── Speech handlers ──
  const handleSpeechEnhance = async () => {
    if (!speechConcept.trim()) return
    setSpeechEnhancing(true)
    setError('')
    try {
      const res = await playgroundTTSEnhance({
        text: speechConcept,
        voice: speechVoice,
        language: speechLanguage,
        brief: speechBrief,
      })
      setSpeechPrompt(res.enhanced_text)
      setEnhanceElapsed(res.elapsed)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSpeechEnhancing(false)
    }
  }

  const handleSpeechGenerate = async () => {
    const text = (speechPrompt || speechConcept).trim()
    if (!text) return
    setSpeechGenerating(true)
    setError('')
    setSpeechAudioData(null)
    setSpeechAudioUrl('')
    try {
      const res = await playgroundTTS({
        text,
        voice: speechVoice,
        language: speechLanguage,
        output_format: 'MP3',
        channels: speechStereo ? 2 : 1,
      })
      setSpeechAudioData(res.audio_data)
      setSpeechAudioUrl(res.audio_url)
      setSpeechAudioMeta({ chars: res.char_count, cost: res.cost, elapsed: res.elapsed })
      setTimeout(() => speechAudioRef.current?.play().catch(() => {}), 100)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSpeechGenerating(false)
    }
  }

  const handleSpeechAudioVideo = async () => {
    if (!speechVideoImageUrl.trim() || !speechAudioUrl) return
    setSpeechVideoLoading(true)
    setError('')
    setSpeechVideoData(null)
    setSpeechVideoUrl('')
    try {
      const res = await playgroundAudioVideo({
        image_url: speechVideoImageUrl,
        audio_url: speechAudioUrl,
        prompt: speechVideoPrompt || undefined,
        resolution: speechVideoResolution,
        draft: speechVideoDraft,
      })
      setSpeechVideoData(res.video_data)
      setSpeechVideoUrl(res.video_url)
      setSpeechVideoMeta({ cost: res.cost, elapsed: res.elapsed, prompt_used: res.prompt_used })
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSpeechVideoLoading(false)
    }
  }

  const insertSpeechTag = (tag: string) => {
    const ta = document.activeElement as HTMLTextAreaElement | null
    if (ta && ta.tagName === 'TEXTAREA' && ta.dataset.speechprompt === '1') {
      const start = ta.selectionStart
      const end = ta.selectionEnd
      const before = speechPrompt.slice(0, start)
      const sel = speechPrompt.slice(start, end)
      const after = speechPrompt.slice(end)
      let inserted = tag
      if (tag.includes('___')) {
        // Wrapping tag (e.g. <whisper>___</whisper>)
        inserted = tag.replace('___', sel || 'text')
      }
      const next = before + inserted + after
      setSpeechPrompt(next)
      setTimeout(() => {
        ta.focus()
        ta.setSelectionRange(start + inserted.length, start + inserted.length)
      }, 0)
    } else {
      setSpeechPrompt((p) => p + (p.endsWith(' ') || !p ? '' : ' ') + tag.replace('___', 'text'))
    }
  }

  const totalSpeechElapsed = (speechAudioMeta?.elapsed || 0) + (speechVideoMeta?.elapsed || 0)

  if (!config) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-neutral-700 border-t-amber-500 rounded-full animate-spin" />
      </div>
    )
  }

  const currentImage = mode === 'simulate' ? simResult?.image : mode === 'manual' ? manualResult : null

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      {/* Header */}
      <header className="border-b border-neutral-800/50 bg-neutral-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={reset} className="text-neutral-500 hover:text-neutral-300 transition-colors text-sm">&larr; Back</button>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-amber-500" />
            <h1 className="text-sm font-medium tracking-wide text-neutral-300">IMAGE PLAYGROUND</h1>
          </div>
          {/* Mode tabs */}
          <div className="flex bg-neutral-900 rounded-lg p-0.5 ml-4">
            <button
              onClick={() => setMode('simulate')}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${mode === 'simulate' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
            >Simulate</button>
            <button
              onClick={() => setMode('manual')}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${mode === 'manual' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
            >Manual</button>
            <button
              onClick={() => setMode('video')}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${mode === 'video' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
            >Video</button>
            <button
              onClick={() => setMode('speech')}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${mode === 'speech' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
            >Speech</button>
            <button
              onClick={() => setMode('iterate')}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${mode === 'iterate' ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
              title="Iterate on the prompt-builder SYSTEM_PROMPT against captured past scenes"
            >Iterate</button>
          </div>
          <div className="flex-1" />
          <span className="text-[10px] text-neutral-600 font-mono">Z-Image Turbo</span>
        </div>
      </header>

      {/* Iterate mode: full-width, bypasses the two-column layout */}
      {mode === 'iterate' && (
        <div className="max-w-[1600px] mx-auto p-4 lg:p-6">
          <IterateTab />
        </div>
      )}

      {mode !== 'iterate' && (
      <div className="max-w-[1600px] mx-auto flex flex-col lg:flex-row gap-0 lg:gap-6 p-4 lg:p-6">
        {/* ── Left panel ── */}
        <div className="w-full lg:w-[440px] shrink-0 space-y-4">

          {mode === 'video' && (
            /* ── Video mode ── */
            <>
              {/* Backend selector */}
              <div className="flex bg-neutral-900 rounded-lg p-0.5">
                <button onClick={() => setVideoBackend('davinci')}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-md transition-colors ${videoBackend === 'davinci' ? 'bg-purple-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                  Davinci (MagiHuman)
                </button>
                <button onClick={() => setVideoBackend('pvideo')}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-md transition-colors ${videoBackend === 'pvideo' ? 'bg-cyan-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                  P-Video (Pruna)
                </button>
              </div>
              <div>
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Source image URL</label>
                <input value={videoImageUrl} onChange={(e) => setVideoImageUrl(e.target.value)}
                  placeholder="https://... or paste a generated image URL"
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none placeholder-neutral-600 transition-colors" />
                {videoImageUrl && (
                  <img src={videoImageUrl} alt="Source" className="mt-2 w-full max-h-48 object-contain rounded-lg border border-neutral-800" />
                )}
              </div>
              <div>
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">
                  {videoBackend === 'davinci' ? 'Davinci prompt' : 'Video prompt'}
                  {videoBackend === 'davinci' && <span className="text-neutral-600"> (leave empty for auto-generation via Grok vision)</span>}
                </label>
                <textarea value={videoPrompt} onChange={(e) => setVideoPrompt(e.target.value)} rows={6}
                  placeholder={videoBackend === 'davinci'
                    ? '3-paragraph Enhanced Prompt... or leave empty to auto-generate from the image'
                    : 'Describe what happens in the video — speech, motion, mood...'}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none resize-y placeholder-neutral-600 transition-colors font-mono text-[11px]" />
              </div>
              <div>
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">
                  Narration context <span className="text-neutral-600">(for auto-prompt — dialogue, scene description)</span>
                </label>
                <textarea value={videoNarration} onChange={(e) => setVideoNarration(e.target.value)} rows={2}
                  placeholder='She whispers: "Come closer..." — her eyes half-closed'
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none resize-none placeholder-neutral-600 transition-colors" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Duration (s)</label>
                  <input type="number" value={videoSeconds} onChange={(e) => setVideoSeconds(parseInt(e.target.value) || 5)} min={1} max={30}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-amber-600 focus:outline-none" />
                </div>
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Resolution</label>
                  <select value={videoSize} onChange={(e) => setVideoSize(e.target.value)}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-amber-600 focus:outline-none">
                    <option value="480p">480p</option>
                    <option value="720p">720p</option>
                  </select>
                </div>
              </div>
              <div className="flex flex-wrap gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={videoAudio} onChange={(e) => setVideoAudio(e.target.checked)}
                    className="rounded bg-neutral-800 border-neutral-700 text-purple-500 w-4 h-4" />
                  <span className="text-xs text-neutral-400">Audio</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={videoDraft} onChange={(e) => setVideoDraft(e.target.checked)}
                    className="rounded bg-neutral-800 border-neutral-700 text-amber-500 w-4 h-4" />
                  <span className="text-xs text-neutral-400">Draft</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={videoPromptUpsampling} onChange={(e) => setVideoPromptUpsampling(e.target.checked)}
                    className="rounded bg-neutral-800 border-neutral-700 text-cyan-500 w-4 h-4" />
                  <span className="text-xs text-neutral-400">Prompt upsampling</span>
                </label>
              </div>
            </>
          )}

          {mode === 'speech' && (
            /* ── Speech mode ── */
            <>
              {/* Voice + Language */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Voice</label>
                  <select value={speechVoice} onChange={(e) => setSpeechVoice(e.target.value)}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none transition-colors">
                    {(config.tts?.voices || [
                      { id: 'eve', label: 'Eve' }, { id: 'ara', label: 'Ara' },
                      { id: 'leo', label: 'Leo' }, { id: 'rex', label: 'Rex' },
                      { id: 'sal', label: 'Sal' },
                    ]).map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Language</label>
                  <select value={speechLanguage} onChange={(e) => setSpeechLanguage(e.target.value)}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none transition-colors">
                    {(config.tts?.languages || ['auto', 'en', 'fr']).map((l) => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Channels (mono/stereo) */}
              <div className="flex bg-neutral-900 rounded-lg p-0.5">
                <button onClick={() => setSpeechStereo(false)}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-md transition-colors ${!speechStereo ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                  Mono
                </button>
                <button onClick={() => setSpeechStereo(true)}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-md transition-colors ${speechStereo ? 'bg-amber-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                  Stereo
                </button>
              </div>

              {/* Step 1 — Concept */}
              <div className="border border-amber-900/30 rounded-lg p-3 space-y-2 bg-amber-950/10">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                  <label className="text-[10px] text-amber-400 uppercase tracking-wider font-medium">1. Concept</label>
                </div>
                <textarea value={speechConcept} onChange={(e) => setSpeechConcept(e.target.value)} rows={3}
                  placeholder="What should be said? Plain text — Grok will add expression tags."
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none resize-y placeholder-neutral-600 transition-colors" />
                <div>
                  <label className="text-[9px] text-neutral-600 uppercase">Direction (optional emotion brief)</label>
                  <input value={speechBrief} onChange={(e) => setSpeechBrief(e.target.value)}
                    placeholder="intimate, breathy, slow"
                    className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-amber-600 focus:outline-none placeholder-neutral-600" />
                </div>
                <button onClick={handleSpeechEnhance} disabled={speechEnhancing || !speechConcept.trim()}
                  className="w-full bg-amber-700/70 hover:bg-amber-600 disabled:opacity-30 text-white py-2 rounded-lg text-xs font-medium transition-colors">
                  {speechEnhancing ? 'Enhancing...' : 'Enhance with Grok →'}
                </button>
                {enhanceElapsed != null && (
                  <p className="text-[9px] text-neutral-500 text-right">enhanced in {enhanceElapsed}s</p>
                )}
              </div>

              {/* Step 2 — Editable expressive prompt */}
              <div className="border border-purple-900/30 rounded-lg p-3 space-y-2 bg-purple-950/10">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-purple-500" />
                    <label className="text-[10px] text-purple-400 uppercase tracking-wider font-medium">2. Speech prompt (editable)</label>
                  </div>
                  <span className="text-[9px] text-neutral-600 font-mono">{speechPrompt.length} chars</span>
                </div>
                <textarea value={speechPrompt} data-speechprompt="1"
                  onChange={(e) => setSpeechPrompt(e.target.value)} rows={6}
                  placeholder="Click 'Enhance with Grok' or type the speech prompt directly. Use [pause], [laugh], <whisper>...</whisper>, etc."
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-neutral-200 font-mono leading-relaxed focus:border-purple-600 focus:outline-none resize-y placeholder-neutral-600 transition-colors" />
                {/* Tag inserter */}
                <div className="space-y-1">
                  <div className="flex flex-wrap gap-1">
                    <span className="text-[9px] text-neutral-600 mr-1 self-center">inline:</span>
                    {[
                      'pause', 'long-pause', 'breath', 'inhale', 'exhale', 'sigh',
                      'laugh', 'chuckle', 'giggle', 'cry', 'tsk', 'tongue-click', 'lip-smack', 'hum-tune',
                    ].map((t) => (
                      <button key={t} onClick={() => insertSpeechTag(`[${t}]`)}
                        className="text-[9px] px-1.5 py-0.5 rounded bg-neutral-800 hover:bg-purple-900/50 text-neutral-400 hover:text-purple-300 font-mono transition-colors">
                        {t}
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <span className="text-[9px] text-neutral-600 mr-1 self-center">wrap:</span>
                    {[
                      'soft', 'whisper', 'loud', 'slow', 'fast',
                      'higher-pitch', 'lower-pitch', 'build-intensity', 'decrease-intensity',
                      'emphasis', 'sing-song', 'singing', 'laugh-speak',
                    ].map((t) => (
                      <button key={t} onClick={() => insertSpeechTag(`<${t}>___</${t}>`)}
                        className="text-[9px] px-1.5 py-0.5 rounded bg-neutral-800 hover:bg-cyan-900/50 text-neutral-400 hover:text-cyan-300 font-mono transition-colors">
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <button onClick={handleSpeechGenerate} disabled={speechGenerating || (!speechPrompt.trim() && !speechConcept.trim())}
                  className="w-full bg-purple-700 hover:bg-purple-600 disabled:opacity-30 text-white py-2 rounded-lg text-xs font-medium transition-colors">
                  {speechGenerating ? 'Generating audio...' : 'Generate Audio'}
                </button>
              </div>

              {/* Step 3 — Lip-sync (only when audio is ready) */}
              {speechAudioUrl && (
                <div className="border border-cyan-900/30 rounded-lg p-3 space-y-2 bg-cyan-950/10">
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-cyan-500" />
                    <label className="text-[10px] text-cyan-400 uppercase tracking-wider font-medium">3. Audio-to-video (P-Video)</label>
                  </div>
                  <div>
                    <label className="text-[9px] text-neutral-600 uppercase">Source image URL</label>
                    <input value={speechVideoImageUrl} onChange={(e) => setSpeechVideoImageUrl(e.target.value)}
                      placeholder="https://... portrait of the speaker"
                      className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none placeholder-neutral-600" />
                    {speechVideoImageUrl && (
                      <img src={speechVideoImageUrl} alt="Source"
                        className="mt-1.5 max-h-32 rounded border border-neutral-800"
                        onError={(e) => (e.target as HTMLImageElement).style.display = 'none'} />
                    )}
                  </div>
                  <div>
                    <label className="text-[9px] text-neutral-600 uppercase">Visual prompt (optional)</label>
                    <textarea value={speechVideoPrompt} onChange={(e) => setSpeechVideoPrompt(e.target.value)} rows={2}
                      placeholder="auto: speaking naturally — or describe motion, expression, lighting..."
                      className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-[11px] text-neutral-300 font-mono focus:border-cyan-600 focus:outline-none resize-y placeholder-neutral-600" />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[9px] text-neutral-600 uppercase">Resolution</label>
                      <select value={speechVideoResolution} onChange={(e) => setSpeechVideoResolution(e.target.value)}
                        className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none">
                        <option value="720p">720p</option>
                        <option value="1080p">1080p</option>
                      </select>
                    </div>
                    <label className="flex items-end gap-2 cursor-pointer pb-1.5">
                      <input type="checkbox" checked={speechVideoDraft} onChange={(e) => setSpeechVideoDraft(e.target.checked)}
                        className="rounded bg-neutral-800 border-neutral-700 text-cyan-500 w-3.5 h-3.5" />
                      <span className="text-[10px] text-neutral-400">Draft</span>
                    </label>
                  </div>
                  <p className="text-[9px] text-neutral-600">P-Video generates ambient motion with audio attached — not true lip-sync.</p>
                  <button onClick={handleSpeechAudioVideo} disabled={speechVideoLoading || !speechVideoImageUrl.trim()}
                    className="w-full bg-cyan-700 hover:bg-cyan-600 disabled:opacity-30 text-white py-2 rounded-lg text-xs font-medium transition-colors">
                    {speechVideoLoading ? 'Generating lip-synced video...' : 'Generate Lip-Synced Video'}
                  </button>
                </div>
              )}
            </>
          )}

          {mode === 'simulate' ? (
            <>
              {/* Raw mode toggle */}
              <label className="flex items-center justify-between bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 cursor-pointer">
                <div>
                  <span className={`text-xs font-medium ${rawMode ? 'text-amber-400' : 'text-neutral-300'}`}>
                    Raw mode {rawMode && '(no Grok)'}
                  </span>
                  <p className="text-[9px] text-neutral-600 mt-0.5">
                    {rawMode
                      ? 'Use scene description as-is, prepend trigger word + mood block'
                      : 'Grok rewrites your scene description into a full prompt'}
                  </p>
                </div>
                <input type="checkbox" checked={rawMode} onChange={(e) => setRawMode(e.target.checked)}
                  className="rounded bg-neutral-800 border-neutral-700 text-amber-500 w-4 h-4" />
              </label>
              {/* Scene description */}
              <div>
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">
                  {rawMode ? 'Raw image prompt' : 'Scene description'}
                </label>
                <textarea value={scene} onChange={(e) => setScene(e.target.value)} rows={rawMode ? 5 : 3}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none resize-y placeholder-neutral-600 transition-colors"
                  placeholder={rawMode ? 'Extreme close-up on woman face, lips parted...' : 'Describe what happens in this scene...'} />
              </div>

              {/* Actor + Setting */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Actor</label>
                  <select value={actor} onChange={(e) => setActor(e.target.value)}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none transition-colors">
                    {config.actors.map((a) => <option key={a.code} value={a.code}>{a.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Setting</label>
                  <select value={setting} onChange={(e) => setSetting(e.target.value)}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none transition-colors">
                    {config.settings.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
              </div>

              {/* Mood + Language */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Mood</label>
                  <select value={mood} onChange={(e) => setMood(e.target.value)}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none transition-colors">
                    {Object.entries(config.moods).map(([k, v]) => (
                      <option key={k} value={k}>{k}</option>
                    ))}
                    <option value="__custom__">-- custom --</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Language</label>
                  <select value={language} onChange={(e) => setLanguage(e.target.value)}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none transition-colors">
                    {config.languages.map((l) => <option key={l} value={l}>{l.toUpperCase()}</option>)}
                  </select>
                </div>
              </div>

              {/* Custom mood editor */}
              <div className="border border-purple-900/30 rounded-lg p-3 space-y-2 bg-purple-950/10">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-500" />
                  <label className="text-[10px] text-purple-400 uppercase tracking-wider font-medium">
                    {mood === '__custom__' ? 'Custom mood' : `Mood: ${mood}`}
                  </label>
                </div>
                <div>
                  <label className="text-[9px] text-neutral-600 uppercase">Prompt block (prepended to image prompt)</label>
                  <textarea value={customMoodBlock} onChange={(e) => setCustomMoodBlock(e.target.value)} rows={2}
                    className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 font-mono focus:border-purple-600 focus:outline-none resize-y transition-colors"
                    placeholder="e.g. intimate sensual atmosphere, partial clothing..." />
                </div>
                <div>
                  <label className="text-[9px] text-neutral-600 uppercase">Mood LoRAs</label>
                  <LoraEditor loras={customMoodLoras} available={config.loras} onChange={setCustomMoodLoras} />
                </div>
              </div>

              {/* LoRA overrides */}
              <div className="border border-neutral-800/50 rounded-lg p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={useSimOverrides} onChange={(e) => setUseSimOverrides(e.target.checked)}
                    className="rounded border-neutral-700 bg-neutral-900 text-amber-600 focus:ring-amber-600" />
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Override all LoRAs</label>
                </div>
                {useSimOverrides && <LoraEditor loras={simLoraOverrides} available={config.loras} onChange={setSimLoraOverrides} />}
              </div>
            </>
          ) : mode === 'manual' ? (
            /* ── Manual mode ── */
            <>
              {/* Backend selector */}
              <div className="flex bg-neutral-900 rounded-lg p-0.5">
                <button onClick={() => setManualBackend('runware')}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-md transition-colors ${manualBackend === 'runware' ? 'bg-neutral-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                  Runware
                </button>
                <button onClick={() => setManualBackend('wavespeed')}
                  className={`flex-1 px-3 py-1.5 text-xs rounded-md transition-colors ${manualBackend === 'wavespeed' ? 'bg-cyan-800 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                  WaveSpeed {cnEnabled && '+ ControlNet'}
                </button>
              </div>

              <div>
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Image prompt (direct to Z-Image Turbo)</label>
                <textarea value={manualPrompt} onChange={(e) => setManualPrompt(e.target.value)} rows={8}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 font-mono leading-relaxed focus:border-amber-600 focus:outline-none resize-y placeholder-neutral-600 transition-colors"
                  placeholder="POV first-person, eye-level, A candid medium shot of..." />
              </div>
              <div>
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">LoRAs</label>
                <LoraEditor loras={manualLoras} available={config.loras} onChange={setManualLoras} />
              </div>

              {/* ControlNet */}
              <div className="border border-cyan-900/30 rounded-lg p-3 space-y-2.5 bg-cyan-950/10">
                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={cnEnabled} onChange={(e) => handleCnToggle(e.target.checked)}
                    className="rounded border-neutral-700 bg-neutral-900 text-cyan-600 focus:ring-cyan-600" />
                  <div className="w-1.5 h-1.5 rounded-full bg-cyan-500" />
                  <label className="text-[10px] text-cyan-400 uppercase tracking-wider font-medium">ControlNet</label>
                </div>
                {cnEnabled && (
                  <>
                    {/* Type selector */}
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[9px] text-neutral-600 uppercase">Type</label>
                        <select value={cnType} onChange={(e) => setCnType(e.target.value)}
                          className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none">
                          <optgroup label="OpenPose">
                            <option value="openpose_full">OpenPose Full</option>
                            <option value="openpose">OpenPose Basic</option>
                            <option value="openpose_face">OpenPose Face</option>
                            <option value="openpose_hand">OpenPose Hand</option>
                          </optgroup>
                          <optgroup label="Depth">
                            <option value="depth_midas">Depth (Midas)</option>
                            <option value="depth_zoe">Depth (Zoe)</option>
                            <option value="depth_leres">Depth (LeReS)</option>
                          </optgroup>
                          <optgroup label="Edge">
                            <option value="canny">Canny Edge</option>
                          </optgroup>
                        </select>
                      </div>
                      <div>
                        <label className="text-[9px] text-neutral-600 uppercase">Control mode</label>
                        <select value={cnMode} onChange={(e) => setCnMode(e.target.value)}
                          className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none">
                          <option value="balanced">Balanced</option>
                          <option value="prompt">Prompt priority</option>
                          <option value="controlnet">ControlNet priority</option>
                        </select>
                      </div>
                    </div>

                    {/* Guide image URL */}
                    <div>
                      <label className="text-[9px] text-neutral-600 uppercase">Guide image URL</label>
                      <input type="text" value={cnGuideUrl} onChange={(e) => setCnGuideUrl(e.target.value)}
                        placeholder="https://... (pose/depth reference image)"
                        className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none placeholder-neutral-600" />
                      {cnGuideUrl && (
                        <img src={cnGuideUrl} alt="Guide" className="mt-1.5 w-24 h-auto rounded border border-neutral-800 opacity-80"
                          onError={(e) => (e.target as HTMLImageElement).style.display = 'none'} />
                      )}
                    </div>

                    {/* Weight + Step range */}
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="text-[9px] text-neutral-600 uppercase">Weight</label>
                        <input type="number" value={cnWeight} step={0.05} min={0} max={2}
                          onChange={(e) => setCnWeight(parseFloat(e.target.value) || 1)}
                          className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none" />
                      </div>
                      <div>
                        <label className="text-[9px] text-neutral-600 uppercase">Start %</label>
                        <input type="number" value={cnStartPct} min={0} max={100}
                          onChange={(e) => setCnStartPct(parseInt(e.target.value) || 0)}
                          className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none" />
                      </div>
                      <div>
                        <label className="text-[9px] text-neutral-600 uppercase">End %</label>
                        <input type="number" value={cnEndPct} min={0} max={100}
                          onChange={(e) => setCnEndPct(parseInt(e.target.value) || 100)}
                          className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-cyan-600 focus:outline-none" />
                      </div>
                    </div>

                    {/* OpenPose-specific: hands+face toggle */}
                    {cnType.startsWith('openpose') && (
                      <div className="flex items-center gap-2">
                        <input type="checkbox" checked={cnHandsFace} onChange={(e) => setCnHandsFace(e.target.checked)}
                          className="rounded border-neutral-700 bg-neutral-900 text-cyan-600 focus:ring-cyan-600" />
                        <label className="text-[9px] text-neutral-500">Include hands & face detection</label>
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          ) : null}

          {/* ── Shared: Resolution / Steps / CFG / Seed ── (image modes only) */}
          {(mode === 'simulate' || mode === 'manual') && (
          <div className="grid grid-cols-5 gap-2">
            {[
              { label: 'Width', value: width, set: setWidth, step: 64, min: 256, max: 2048 },
              { label: 'Height', value: height, set: setHeight, step: 64, min: 256, max: 2048 },
              { label: 'Steps', value: steps, set: setSteps, step: 1, min: 1, max: 50 },
              { label: 'CFG', value: cfg, set: setCfg, step: 0.5, min: 0, max: 20 },
            ].map((f) => (
              <div key={f.label}>
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">{f.label}</label>
                <input type="number" value={f.value} onChange={(e) => f.set(parseFloat(e.target.value) || 0)}
                  step={f.step} min={f.min} max={f.max}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-2 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none transition-colors" />
              </div>
            ))}
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Seed</label>
              <input type="text" value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ''))} placeholder="rand"
                className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-2 py-2 text-sm text-neutral-100 focus:border-amber-600 focus:outline-none placeholder-neutral-600 transition-colors" />
            </div>
          </div>
          )}

          {/* Action buttons */}
          {mode === 'simulate' ? (
            <div className="flex gap-2">
              <button onClick={() => handleSimulate(true)} disabled={loading || !scene.trim()}
                className="flex-1 bg-neutral-800 hover:bg-neutral-700 disabled:opacity-30 text-neutral-200 py-2.5 rounded-lg text-sm font-medium transition-colors">
                {loading ? '...' : 'Simulate Prompt'}
              </button>
              <button onClick={() => handleSimulate(false)} disabled={loading || !scene.trim()}
                className="flex-1 bg-amber-700 hover:bg-amber-600 disabled:opacity-30 text-white py-2.5 rounded-lg text-sm font-medium transition-colors">
                {loading ? '...' : 'Simulate + Generate'}
              </button>
            </div>
          ) : mode === 'manual' ? (
            <button onClick={handleManualGenerate} disabled={loading || !manualPrompt.trim()}
              className="w-full bg-amber-700 hover:bg-amber-600 disabled:opacity-30 text-white py-2.5 rounded-lg text-sm font-medium transition-colors">
              {loading ? 'Generating...' : 'Generate Image'}
            </button>
          ) : mode === 'video' ? (
            <button onClick={handleVideoGenerate} disabled={videoLoading || !videoImageUrl.trim()}
              className="w-full bg-purple-700 hover:bg-purple-600 disabled:opacity-30 text-white py-2.5 rounded-lg text-sm font-medium transition-colors">
              {videoLoading ? 'Generating video...' : 'Generate Video'}
            </button>
          ) : null}

          {error && (
            <div className="bg-red-950/30 border border-red-900/50 rounded-lg px-3 py-2 text-xs text-red-400">{error}</div>
          )}

          {/* Simulated prompt (simulate mode only) */}
          {mode === 'simulate' && simulatedPrompt && (
            <div>
              <div className="flex items-center gap-2 mb-1">
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Simulated prompt</label>
                <span className="text-[9px] text-neutral-600 font-mono">{simulatedPrompt.length} chars</span>
                {simResult?.actors_present?.map((a) => (
                  <span key={a} className="text-[9px] px-1.5 py-0.5 bg-indigo-900/50 text-indigo-300 rounded font-mono">{a}</span>
                ))}
                {simResult?.style_moods?.map((m) => (
                  <span key={m} className="text-[9px] px-1.5 py-0.5 bg-purple-900/50 text-purple-300 rounded font-mono">{m}</span>
                ))}
              </div>
              <textarea value={simulatedPrompt} onChange={(e) => setSimulatedPrompt(e.target.value)} rows={6}
                className="w-full bg-neutral-900/50 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-neutral-300 font-mono leading-relaxed focus:border-amber-600 focus:outline-none resize-y transition-colors" />
            </div>
          )}

          {mode === 'simulate' && simResult?.narration && (
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Agent narration</label>
              <p className="mt-1 text-xs text-neutral-400 leading-relaxed bg-neutral-900/30 rounded-lg px-3 py-2 border border-neutral-800/30">
                {simResult.narration}
              </p>
            </div>
          )}
        </div>

        {/* ── Right panel: Results ── */}
        <div ref={resultRef} className="flex-1 min-w-0 space-y-4 mt-6 lg:mt-0">
          {mode === 'speech' ? (
            <div className="space-y-4">
              {/* Total time tracker */}
              {(speechAudioMeta || speechVideoMeta) && (
                <div className="flex items-center gap-3 text-[11px] font-mono text-neutral-400 bg-neutral-900/50 border border-neutral-800/50 rounded-lg px-3 py-2">
                  <span className="text-neutral-500">Time:</span>
                  {enhanceElapsed != null && <span>enhance {enhanceElapsed}s</span>}
                  {speechAudioMeta && <span className="text-purple-300">tts {speechAudioMeta.elapsed}s</span>}
                  {speechVideoMeta && <span className="text-cyan-300">video {speechVideoMeta.elapsed}s</span>}
                  <span className="ml-auto text-amber-300">total {(((enhanceElapsed || 0) + totalSpeechElapsed)).toFixed(1)}s</span>
                </div>
              )}

              {/* Audio result */}
              {speechAudioData ? (
                <div className="rounded-lg bg-neutral-900 border border-neutral-800/50 p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-purple-500" />
                    <label className="text-[10px] text-purple-400 uppercase tracking-wider font-medium">Speech audio</label>
                    <span className="text-[9px] text-neutral-600 font-mono ml-auto">
                      {speechAudioMeta?.chars}c · ${speechAudioMeta?.cost.toFixed(4)} · {speechAudioMeta?.elapsed}s
                    </span>
                  </div>
                  <audio ref={speechAudioRef} src={speechAudioData} controls className="w-full" />
                  {speechAudioUrl && (
                    <a href={speechAudioUrl} target="_blank" rel="noreferrer"
                      className="text-[10px] text-neutral-500 hover:text-amber-400 transition-colors font-mono break-all">
                      {speechAudioUrl}
                    </a>
                  )}
                </div>
              ) : speechGenerating ? (
                <div className="rounded-lg bg-neutral-900/30 border border-neutral-800/30 p-12 text-center">
                  <div className="w-6 h-6 border-2 border-neutral-700 border-t-purple-500 rounded-full animate-spin mx-auto mb-3" />
                  <p className="text-neutral-500 text-sm">Generating speech...</p>
                </div>
              ) : (
                <div className="rounded-lg bg-neutral-900/30 border border-neutral-800/30 border-dashed p-12 text-center">
                  <div className="text-neutral-700 text-3xl mb-2">&#9836;</div>
                  <p className="text-neutral-600 text-sm">
                    Type a concept, optionally enhance with Grok, then generate speech.
                  </p>
                </div>
              )}

              {/* Video result */}
              {speechVideoData ? (
                <div className="rounded-lg bg-neutral-900 border border-neutral-800/50 overflow-hidden">
                  <video src={speechVideoData} controls autoPlay loop className="w-full h-auto" style={{ maxHeight: '60vh' }} />
                  <div className="px-4 py-3 bg-gradient-to-t from-black/80 to-transparent">
                    <div className="flex items-center gap-3 text-[10px] text-neutral-400 font-mono flex-wrap">
                      <span>{speechVideoMeta?.elapsed}s</span>
                      {speechVideoMeta && speechVideoMeta.cost > 0 && (
                        <span className="text-green-400">${speechVideoMeta.cost.toFixed(3)}</span>
                      )}
                      <span className="text-cyan-400">P-Video lip-sync</span>
                    </div>
                    {speechVideoMeta?.prompt_used && (
                      <pre className="mt-2 text-[10px] text-neutral-500 font-mono leading-relaxed whitespace-pre-wrap max-h-24 overflow-y-auto">
                        {speechVideoMeta.prompt_used}
                      </pre>
                    )}
                  </div>
                </div>
              ) : speechVideoLoading ? (
                <div className="rounded-lg bg-neutral-900/30 border border-neutral-800/30 p-8 text-center">
                  <div className="w-6 h-6 border-2 border-neutral-700 border-t-cyan-500 rounded-full animate-spin mx-auto mb-3" />
                  <p className="text-neutral-500 text-sm">Generating lip-synced video...</p>
                  <p className="text-neutral-600 text-xs mt-1">P-Video typically 20–60s</p>
                </div>
              ) : null}
            </div>
          ) : mode === 'video' && videoResult ? (
            <div className="space-y-4">
              {videoResult.video_data ? (
                <div className="relative rounded-lg overflow-hidden bg-neutral-900 border border-neutral-800/50">
                  <video src={videoResult.video_data} controls autoPlay loop
                    className="w-full h-auto" style={{ maxHeight: '70vh' }} />
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-4 py-3">
                    <div className="flex items-center gap-3 text-[10px] text-neutral-400 font-mono flex-wrap">
                      <span>{videoResult.elapsed}s total</span>
                      <span>{videoResult.generation_time}s gen</span>
                      {videoResult.cost != null && videoResult.cost > 0 && <span className="text-green-400">${videoResult.cost.toFixed(3)}</span>}
                      <span className="text-purple-400">job={videoResult.job_id}</span>
                      {videoResult.simulated && <span className="text-yellow-500">SIMULATED</span>}
                    </div>
                  </div>
                </div>
              ) : videoResult.simulated ? (
                <div className="rounded-lg bg-yellow-950/20 border border-yellow-900/30 p-6 text-center">
                  <p className="text-yellow-400 text-sm">Video simulated (pod offline)</p>
                  <p className="text-yellow-500/60 text-xs mt-1">job={videoResult.job_id} | {videoResult.elapsed}s</p>
                </div>
              ) : null}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Davinci prompt</label>
                  <span className="text-[9px] text-neutral-600">(edit & regenerate)</span>
                </div>
                <textarea
                  value={videoPrompt || videoResult.prompt_used}
                  onChange={(e) => setVideoPrompt(e.target.value)}
                  rows={12}
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-[11px] text-neutral-300 font-mono leading-relaxed focus:border-purple-600 focus:outline-none resize-y transition-colors"
                />
                <button onClick={handleVideoGenerate} disabled={videoLoading || !videoImageUrl.trim()}
                  className="w-full mt-2 bg-purple-700 hover:bg-purple-600 disabled:opacity-30 text-white py-2 rounded-lg text-xs font-medium transition-colors">
                  {videoLoading ? 'Generating...' : 'Regenerate with edited prompt'}
                </button>
              </div>
            </div>
          ) : mode === 'video' && videoLoading ? (
            <div className="rounded-lg bg-neutral-900/30 border border-neutral-800/30 p-12 text-center">
              <div className="w-6 h-6 border-2 border-neutral-700 border-t-purple-500 rounded-full animate-spin mx-auto mb-3" />
              <p className="text-neutral-500 text-sm">Generating video...</p>
              <p className="text-neutral-600 text-xs mt-1">This may take 30-120 seconds</p>
            </div>
          ) : currentImage ? (
            <>
              <ResultPanel image={currentImage} config={config} onUseSeed={(s) => setSeed(String(s))} />
              {/* Quick button to send this image to video mode */}
              <button onClick={() => useImageForVideo(currentImage.url)}
                className="w-full bg-purple-900/30 hover:bg-purple-900/50 border border-purple-800/30 text-purple-300 py-2 rounded-lg text-xs font-medium transition-colors">
                Use this image for video generation
              </button>
            </>
          ) : simResult?.image_error ? (
            <div className="rounded-lg bg-red-950/20 border border-red-900/30 p-6 text-center">
              <p className="text-red-400 text-sm">Image generation failed</p>
              <p className="text-red-500/60 text-xs mt-1">{simResult.image_error}</p>
            </div>
          ) : (
            <div className="rounded-lg bg-neutral-900/30 border border-neutral-800/30 border-dashed p-12 text-center">
              <div className="text-neutral-700 text-3xl mb-2">&#9670;</div>
              <p className="text-neutral-600 text-sm">
                {mode === 'simulate' ? 'Describe a scene and let the agent craft the prompt'
                  : mode === 'video' ? 'Paste an image URL and generate a talking-head video'
                  : 'Write a prompt and generate directly'}
              </p>
            </div>
          )}

          {/* History */}
          {history.length > 0 && (
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">History</label>
              <div className="flex gap-2 mt-1 overflow-x-auto pb-2">
                {history.map((h) => (
                  <div key={h.timestamp} className="shrink-0 rounded-lg overflow-hidden border border-neutral-800/50 relative group">
                    <img src={h.url} alt="" className="w-16 h-24 object-cover" />
                    <div className="absolute top-0.5 right-0.5">
                      <span className={`text-[8px] px-1 rounded ${h.mode === 'simulate' ? 'bg-amber-900/80 text-amber-300' : 'bg-blue-900/80 text-blue-300'}`}>
                        {h.mode === 'simulate' ? 'S' : 'M'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  )
}
