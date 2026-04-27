import { useState, useEffect } from 'react'
import { useGameStore } from '../stores/gameStore'
import {
  getSystemPrompt, updateSystemPrompt, resetSystemPrompt,
  streamPromptModification, getSessionDebug, getSessionMemories,
  fetchAvailableLoras, getStyleLoras, updateStyleLoras, getExtraLoras, updateExtraLoras,
  getVideoSettings, updateVideoSettings,
  regenImage, rewriteImagePrompt,
} from '../api/client'
import type { LoraInfo, ExtraLora } from '../api/types'
import { useMediaQuery } from '../hooks/useMediaQuery'
import BottomSheet from './layout/BottomSheet'

interface DebugPanelProps {
  onClose?: () => void
}

export default function DebugPanel({ onClose }: DebugPanelProps) {
  const isDesktop = useMediaQuery('(min-width: 768px)')
  const { sessionId, generatedPrompts, allSequenceCosts, sequenceNumber, videoCost, videoGenerationTime, videoStatus, videoPrompt, images, debugContext } = useGameStore()
  const [tab, setTab] = useState<'prompts' | 'system' | 'memory' | 'loras' | 'video' | 'costs'>('prompts')
  const [memoryData, setMemoryData] = useState<{ persistent_memory: string; narrative_memory: string; mem0_enabled: boolean } | null>(null)
  const [memoryLoading, setMemoryLoading] = useState(false)
  const [systemPrompt, setSystemPrompt] = useState('')
  const [isOverride, setIsOverride] = useState(false)
  const [modifyInstructions, setModifyInstructions] = useState('')
  const [modifying, setModifying] = useState(false)
  const [debugInfo, setDebugInfo] = useState<any>(null)

  // LoRA state
  const [availableLoras, setAvailableLoras] = useState<LoraInfo[]>([])
  const [extraLoras, setExtraLoras] = useState<ExtraLora[]>([])
  const [lorasLoaded, setLorasLoaded] = useState(false)
  const [styleLoras, setStyleLoras] = useState<ExtraLora[]>([])

  // Video settings
  const [videoSettings, setVideoSettings] = useState({ draft: true, audio: true, duration: 5, resolution: '720p' })
  const [videoSettingsLoaded, setVideoSettingsLoaded] = useState(false)

  // Editable prompts + regen
  const [editedPrompts, setEditedPrompts] = useState<Record<number, string>>({})
  // nsfwToggle removed — style mood is now handled via LoRA overrides
  const [customSeed, setCustomSeed] = useState<Record<number, string>>({})
  const [overrideActors, setOverrideActors] = useState<Record<number, string[]>>({})
  const [perImageLoras, setPerImageLoras] = useState<Record<number, { id: string; weight: number }[]>>({})
  const [perImageSize, setPerImageSize] = useState<Record<number, { width: number; height: number }>>({})
  const [perImageSteps, setPerImageSteps] = useState<Record<number, number>>({})
  const [regenIdx, setRegenIdx] = useState<number | null>(null)
  const [rewriteInstructions, setRewriteInstructions] = useState<Record<number, string>>({})
  const [rewritingIdx, setRewritingIdx] = useState<number | null>(null)

  // Prompt variants (shared localStorage with SetupPage)
  const [savedVariants, setSavedVariants] = useState<{ name: string; prompt: string; date: string }[]>([])
  const [variantName, setVariantName] = useState('')
  const [showVariantPicker, setShowVariantPicker] = useState(false)

  useEffect(() => {
    try {
      const raw = localStorage.getItem('graphbun_prompt_variants')
      if (raw) setSavedVariants(JSON.parse(raw))
    } catch { /* ignore */ }
  }, [])

  const persistVariants = (variants: typeof savedVariants) => {
    setSavedVariants(variants)
    localStorage.setItem('graphbun_prompt_variants', JSON.stringify(variants))
  }

  useEffect(() => {
    if (sessionId && tab === 'system') {
      getSystemPrompt(sessionId).then((data) => {
        setSystemPrompt(data.prompt)
        setIsOverride(data.is_override)
      })
    }
    if (sessionId && tab === 'costs') {
      getSessionDebug(sessionId).then(setDebugInfo)
    }
    if ((tab === 'loras' || tab === 'prompts') && !lorasLoaded) {
      fetchAvailableLoras().then((l) => { setAvailableLoras(l); setLorasLoaded(true) })
      if (sessionId) {
        getStyleLoras(sessionId).then(setStyleLoras)
        getExtraLoras(sessionId).then(setExtraLoras)
      }
    }
    if (tab === 'video' && !videoSettingsLoaded && sessionId) {
      getVideoSettings(sessionId).then((s) => { setVideoSettings(s); setVideoSettingsLoaded(true) })
    }
  }, [sessionId, tab, sequenceNumber])

  // ── Style LoRA handlers ──
  const updateStyleLoraWeight = (i: number, weight: number) => {
    setStyleLoras(styleLoras.map((l, idx) => idx === i ? { ...l, weight } : l))
  }
  const removeStyleLora = (i: number) => setStyleLoras(styleLoras.filter((_, idx) => idx !== i))
  const addStyleLora = () => setStyleLoras([...styleLoras, { id: '', weight: 1.0 }])
  const updateStyleLoraId = (i: number, id: string) => {
    setStyleLoras(styleLoras.map((l, idx) => idx === i ? { ...l, id } : l))
  }
  const saveStyleLoras = async () => {
    if (!sessionId) return
    await updateStyleLoras(sessionId, styleLoras.filter(l => l.id))
  }

  // ── Extra LoRA handlers ──
  const addExtraLora = () => setExtraLoras([...extraLoras, { id: '', weight: 1.0 }])
  const removeExtraLora = (i: number) => setExtraLoras(extraLoras.filter((_, idx) => idx !== i))
  const updateExtraLoraField = (i: number, field: 'id' | 'weight', value: string | number) => {
    setExtraLoras(extraLoras.map((l, idx) => idx === i ? { ...l, [field]: value } : l))
  }
  const saveExtraLoras = async () => {
    if (!sessionId) return
    await updateExtraLoras(sessionId, extraLoras.filter(l => l.id))
  }

  const handleSavePrompt = async () => {
    if (!sessionId) return
    await updateSystemPrompt(sessionId, systemPrompt)
    setIsOverride(true)
  }

  const handleResetPrompt = async () => {
    if (!sessionId) return
    await resetSystemPrompt(sessionId)
    const data = await getSystemPrompt(sessionId)
    setSystemPrompt(data.prompt)
    setIsOverride(false)
  }

  const handleModifyWithGrok = async () => {
    if (!sessionId || !modifyInstructions) return
    setModifying(true)
    let newPrompt = ''
    await streamPromptModification(
      sessionId,
      modifyInstructions,
      (text) => {
        newPrompt += text
        setSystemPrompt(newPrompt)
      },
      (fullText) => {
        setSystemPrompt(fullText)
        setModifying(false)
        setModifyInstructions('')
      },
    )
  }

  const panelContent = (
    <>
      {/* Tabs */}
      <div className="flex overflow-x-auto no-scrollbar whitespace-nowrap border-b border-neutral-800 shrink-0">
        {(['prompts', 'system', 'memory', 'loras', 'video', 'costs'] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t)
              if (t === 'memory' && !memoryData && sessionId) {
                setMemoryLoading(true)
                getSessionMemories(sessionId)
                  .then(setMemoryData)
                  .catch(() => {})
                  .finally(() => setMemoryLoading(false))
              }
            }}
            className={`px-3 py-3 min-w-[56px] shrink-0 text-xs font-medium transition-colors ${
              tab === t
                ? 'text-indigo-400 border-b border-indigo-400'
                : 'text-neutral-500 hover:text-neutral-300'
            }`}
          >
            {({
              prompts: 'Prompts', system: 'System', memory: 'Mem0',
              loras: 'LoRA', video: 'Video', costs: 'Costs',
            } as const)[t]}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {/* ── Generated Image Prompts (editable + regen) ── */}
        {tab === 'prompts' && (
          <div className="space-y-3">
            {generatedPrompts.length === 0 && (
              <p className="text-neutral-600 text-xs text-center py-8">
                Les prompts apparaissent ici pendant la narration
              </p>
            )}
            {generatedPrompts.map((p) => {
              const edited = editedPrompts[p.index]
              const currentPrompt = edited !== undefined ? edited : p.prompt
              const isEdited = edited !== undefined && edited !== p.prompt
              const isRegening = regenIdx === p.index
              const activeActors = overrideActors[p.index] ?? p.actors
              const allActorCodes = availableLoras.filter(l => l.type === 'character').map(l => {
                // Map LoRA id to actor codename from ACTOR_REGISTRY
                const codeMap: Record<string, string> = {
                  'warmline:202603170001@1': 'milena',
                  'warmline:202603170002@1': 'nataly',
                  'warmline:202603200001@1': 'shorty_asian',
                  'warmline:202603200002@1': 'blonde_cacu',
                  'warmline:202603150002@1': 'pwfp',
                }
                return { code: codeMap[l.id] || l.id, name: l.name, trigger: l.trigger }
              }).filter(a => a.code)

              return (
                <div key={p.index} className="bg-neutral-900 rounded-lg p-3 border border-neutral-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-indigo-400">
                      Image {p.index}
                    </span>
                    <div className="flex items-center gap-1">
                      {isEdited && (
                        <button
                          onClick={() => { setEditedPrompts(prev => { const n = {...prev}; delete n[p.index]; return n }); setOverrideActors(prev => { const n = {...prev}; delete n[p.index]; return n }) }}
                          className="text-[10px] text-neutral-600 hover:text-neutral-400"
                        >
                          reset
                        </button>
                      )}
                    </div>
                  </div>
                  {/* Actor toggles */}
                  <div className="flex flex-wrap gap-1">
                    {allActorCodes.map(a => {
                      const active = activeActors.includes(a.code)
                      return (
                        <button
                          key={a.code}
                          onClick={() => {
                            const newActors = active
                              ? activeActors.filter(c => c !== a.code)
                              : [...activeActors, a.code]
                            setOverrideActors(prev => ({...prev, [p.index]: newActors}))
                          }}
                          className={`px-1.5 py-0.5 rounded text-[9px] font-medium transition-colors ${
                            active
                              ? 'bg-purple-800 text-purple-200 border border-purple-600'
                              : 'bg-neutral-800 text-neutral-500 border border-neutral-700 hover:border-neutral-600'
                          }`}
                          title={a.trigger ? `trigger: ${a.trigger}` : a.code}
                        >
                          {a.name}
                        </button>
                      )
                    })}
                  </div>
                  <textarea
                    value={currentPrompt}
                    onChange={(e) => setEditedPrompts(prev => ({...prev, [p.index]: e.target.value}))}
                    rows={5}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-[11px] text-neutral-300 font-mono leading-relaxed resize-y focus:border-indigo-500 focus:outline-none"
                  />
                  {/* Rewrite with AI */}
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      value={rewriteInstructions[p.index] || ''}
                      onChange={(e) => setRewriteInstructions(prev => ({...prev, [p.index]: e.target.value}))}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && rewriteInstructions[p.index]?.trim()) {
                          e.preventDefault()
                          const instr = rewriteInstructions[p.index].trim()
                          setRewritingIdx(p.index)
                          let newText = ''
                          rewriteImagePrompt(
                            currentPrompt, instr,
                            (t) => { newText += t; setEditedPrompts(prev => ({...prev, [p.index]: newText})) },
                            (full) => { setEditedPrompts(prev => ({...prev, [p.index]: full})); setRewritingIdx(null); setRewriteInstructions(prev => ({...prev, [p.index]: ''})) },
                          )
                        }
                      }}
                      placeholder="Ex: robe en soie au lieu de velours..."
                      className="flex-1 bg-neutral-950 border border-neutral-800 rounded px-2 py-1 text-[10px] text-neutral-400 focus:border-purple-500 focus:outline-none placeholder-neutral-700"
                    />
                    <button
                      onClick={() => {
                        const instr = (rewriteInstructions[p.index] || '').trim()
                        if (!instr) return
                        setRewritingIdx(p.index)
                        let newText = ''
                        rewriteImagePrompt(
                          currentPrompt, instr,
                          (t) => { newText += t; setEditedPrompts(prev => ({...prev, [p.index]: newText})) },
                          (full) => { setEditedPrompts(prev => ({...prev, [p.index]: full})); setRewritingIdx(null); setRewriteInstructions(prev => ({...prev, [p.index]: ''})) },
                        )
                      }}
                      disabled={rewritingIdx === p.index || !(rewriteInstructions[p.index] || '').trim()}
                      className="bg-purple-700 hover:bg-purple-600 disabled:opacity-30 px-2 py-1 rounded text-[10px] font-medium transition-colors shrink-0"
                    >
                      {rewritingIdx === p.index ? '...' : 'AI'}
                    </button>
                  </div>

                  {/* ── Regen Settings Panel ── */}
                  <details className="mt-1">
                    <summary className="text-[10px] text-neutral-500 cursor-pointer hover:text-neutral-300 font-medium">
                      Regen Settings {perImageLoras[p.index] ? '(custom LoRAs)' : ''}
                    </summary>
                    <div className="mt-2 bg-neutral-950 rounded-lg p-2 space-y-2">
                      {/* Resolution + Steps */}
                      <div className="grid grid-cols-3 gap-1.5">
                        <div>
                          <label className="text-[9px] text-neutral-600">Width</label>
                          <input type="number" step={64} min={256} max={2048}
                            value={perImageSize[p.index]?.width ?? images[p.index]?.genSettings?.width ?? 1280}
                            onChange={(e) => setPerImageSize(prev => ({...prev, [p.index]: { width: +e.target.value, height: prev[p.index]?.height ?? 720 }}))}
                            className="w-full bg-neutral-900 border border-neutral-800 rounded px-1.5 py-0.5 text-[10px] text-neutral-300 font-mono focus:border-indigo-500 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="text-[9px] text-neutral-600">Height</label>
                          <input type="number" step={64} min={256} max={2048}
                            value={perImageSize[p.index]?.height ?? images[p.index]?.genSettings?.height ?? 720}
                            onChange={(e) => setPerImageSize(prev => ({...prev, [p.index]: { width: prev[p.index]?.width ?? 1280, height: +e.target.value }}))}
                            className="w-full bg-neutral-900 border border-neutral-800 rounded px-1.5 py-0.5 text-[10px] text-neutral-300 font-mono focus:border-indigo-500 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="text-[9px] text-neutral-600">Steps</label>
                          <input type="number" min={1} max={50}
                            value={perImageSteps[p.index] ?? images[p.index]?.genSettings?.steps ?? 8}
                            onChange={(e) => setPerImageSteps(prev => ({...prev, [p.index]: +e.target.value}))}
                            className="w-full bg-neutral-900 border border-neutral-800 rounded px-1.5 py-0.5 text-[10px] text-neutral-300 font-mono focus:border-indigo-500 focus:outline-none"
                          />
                        </div>
                      </div>

                      {/* Style mood info */}
                      {images[p.index]?.genSettings?.style_moods && (
                        <div className="text-[9px] text-neutral-600">
                          Moods: <span className="text-neutral-400">{images[p.index].genSettings!.style_moods.join(', ')}</span>
                        </div>
                      )}

                      {/* Seed */}
                      <div className="flex items-center gap-1">
                        <span className="text-[10px] text-neutral-600 shrink-0">Seed:</span>
                        <input type="text" value={customSeed[p.index] ?? ''} placeholder="random"
                          onChange={(e) => setCustomSeed(prev => ({...prev, [p.index]: e.target.value}))}
                          className="flex-1 bg-neutral-900 border border-neutral-800 rounded px-1.5 py-0.5 text-[10px] text-neutral-400 font-mono focus:border-amber-500 focus:outline-none placeholder-neutral-700 min-w-0" />
                        {images[p.index]?.seed && (
                          <button onClick={() => setCustomSeed(prev => ({...prev, [p.index]: String(images[p.index].seed)}))}
                            className="text-[9px] text-amber-500/60 hover:text-amber-400 shrink-0" title={`Current: ${images[p.index].seed}`}>this</button>
                        )}
                        {p.index > 0 && images[p.index - 1]?.seed && (
                          <button onClick={() => setCustomSeed(prev => ({...prev, [p.index]: String(images[p.index - 1]!.seed)}))}
                            className="text-[9px] text-indigo-400/60 hover:text-indigo-300 shrink-0">prev</button>
                        )}
                        {customSeed[p.index] && (
                          <button onClick={() => setCustomSeed(prev => { const n = {...prev}; delete n[p.index]; return n })}
                            className="text-[9px] text-neutral-600 hover:text-neutral-400 shrink-0">&times;</button>
                        )}
                      </div>

                      {/* Per-image LoRA overrides */}
                      <div className="border-t border-neutral-800 pt-2">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[9px] text-neutral-500 font-medium">LoRA overrides</span>
                          <div className="flex gap-1">
                            {!perImageLoras[p.index] && images[p.index]?.genSettings?.loras && (
                              <button onClick={() => setPerImageLoras(prev => ({...prev, [p.index]: images[p.index].genSettings!.loras.map(l => ({...l}))}))}
                                className="text-[9px] text-indigo-400/60 hover:text-indigo-300">from last gen</button>
                            )}
                            <button onClick={() => setPerImageLoras(prev => ({...prev, [p.index]: [...(prev[p.index] || []), {id: '', weight: 1.0}]}))}
                              className="text-[9px] text-indigo-400/60 hover:text-indigo-300">+ add</button>
                            {perImageLoras[p.index] && (
                              <button onClick={() => setPerImageLoras(prev => { const n = {...prev}; delete n[p.index]; return n })}
                                className="text-[9px] text-red-400/60 hover:text-red-300">clear</button>
                            )}
                          </div>
                        </div>
                        {(perImageLoras[p.index] || []).map((lora, li) => (
                          <div key={li} className="flex items-center gap-1 mb-1">
                            <select value={lora.id}
                              onChange={(e) => setPerImageLoras(prev => ({...prev, [p.index]: prev[p.index].map((l, i) => i === li ? {...l, id: e.target.value} : l)}))}
                              className="flex-1 bg-neutral-900 border border-neutral-800 rounded px-1 py-0.5 text-[9px] text-neutral-300 focus:border-indigo-500 focus:outline-none min-w-0">
                              <option value="">Select...</option>
                              {availableLoras.map(al => (
                                <option key={al.id} value={al.id}>{al.name}</option>
                              ))}
                            </select>
                            <input type="number" step={0.1} min={-4} max={4} value={lora.weight}
                              onChange={(e) => setPerImageLoras(prev => ({...prev, [p.index]: prev[p.index].map((l, i) => i === li ? {...l, weight: +e.target.value} : l)}))}
                              className="w-12 bg-neutral-900 border border-neutral-800 rounded px-1 py-0.5 text-[9px] text-neutral-300 font-mono focus:border-indigo-500 focus:outline-none" />
                            <button onClick={() => setPerImageLoras(prev => ({...prev, [p.index]: prev[p.index].filter((_, i) => i !== li)}))}
                              className="text-neutral-600 hover:text-red-400 text-[10px]">&times;</button>
                          </div>
                        ))}
                        {!perImageLoras[p.index] && (
                          <p className="text-[9px] text-neutral-700">Using session defaults (actors + style + extra)</p>
                        )}
                      </div>

                      {/* Last gen info (read-only) */}
                      {images[p.index]?.genSettings?.final_prompt && (
                        <details className="border-t border-neutral-800 pt-1">
                          <summary className="text-[9px] text-neutral-600 cursor-pointer hover:text-neutral-400">Last prompt sent</summary>
                          <p className="mt-1 text-[9px] text-neutral-500 whitespace-pre-wrap font-mono leading-relaxed max-h-24 overflow-y-auto">
                            {images[p.index].genSettings!.final_prompt}
                          </p>
                        </details>
                      )}
                    </div>
                  </details>

                  {/* Regen button */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={async () => {
                        if (!sessionId) return
                        setRegenIdx(p.index)
                        try {
                          const seedStr = customSeed[p.index]?.trim()
                          const seedVal = seedStr ? parseInt(seedStr) || undefined : undefined
                          const result = await regenImage({
                            sessionId,
                            prompt: currentPrompt,
                            actorsPresent: activeActors,
                            imageIndex: p.index,
                            seed: seedVal,
                            loraOverrides: perImageLoras[p.index]?.filter(l => l.id) || undefined,
                            width: perImageSize[p.index]?.width,
                            height: perImageSize[p.index]?.height,
                            steps: perImageSteps[p.index],
                          })
                          useGameStore.getState().handleSSEEvent({
                            type: 'image_ready', index: p.index, url: result.url,
                            cost: result.cost, seed: result.seed, generation_time: result.elapsed,
                            settings: result.settings,
                          } as any)
                        } catch (e) {
                          console.error('Regen failed:', e)
                        } finally {
                          setRegenIdx(null)
                        }
                      }}
                      disabled={isRegening}
                      className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 px-3 py-1.5 rounded text-[11px] font-medium transition-colors"
                    >
                      {isRegening ? 'Generating...' : 'Regen'}
                    </button>
                    <span className="text-[10px] text-neutral-600 flex-1 text-right">
                      {currentPrompt.length}c
                      {perImageLoras[p.index] && <span className="text-amber-400/60 ml-1">custom LoRAs</span>}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* ── System Prompt Editor ── */}
        {tab === 'system' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-500">
                {isOverride ? 'Override actif' : 'Auto-généré'}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowVariantPicker(!showVariantPicker)}
                  className="text-xs text-indigo-400 hover:text-indigo-300"
                >
                  Variantes ({savedVariants.length})
                </button>
                {isOverride && (
                  <button
                    onClick={handleResetPrompt}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Reset
                  </button>
                )}
              </div>
            </div>

            {/* Variant picker */}
            {showVariantPicker && (
              <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-2 space-y-1">
                {savedVariants.length === 0 && (
                  <p className="text-[10px] text-neutral-600 text-center py-1">Aucune variante</p>
                )}
                {savedVariants.map((v) => (
                  <div key={v.name} className="flex items-center gap-1">
                    <button
                      onClick={() => { setSystemPrompt(v.prompt); setShowVariantPicker(false) }}
                      className="flex-1 text-left text-xs text-neutral-300 hover:text-white px-2 py-1 rounded hover:bg-neutral-800 truncate"
                    >
                      {v.name}
                    </button>
                    <button
                      onClick={() => persistVariants(savedVariants.filter((x) => x.name !== v.name))}
                      className="text-neutral-600 hover:text-red-400 text-xs px-1"
                    >
                      &times;
                    </button>
                  </div>
                ))}
              </div>
            )}

            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={16}
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-neutral-300 font-mono resize-y focus:border-indigo-500 focus:outline-none"
            />

            {/* Save as variant + apply */}
            <div className="flex gap-2">
              <input
                type="text"
                value={variantName}
                onChange={(e) => setVariantName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && systemPrompt) {
                    const label = variantName.trim() || `Variante ${savedVariants.length + 1}`
                    persistVariants([
                      ...savedVariants.filter((v) => v.name !== label),
                      { name: label, prompt: systemPrompt, date: new Date().toISOString() },
                    ])
                    setVariantName('')
                  }
                }}
                placeholder="Nom variante..."
                className="flex-1 bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-indigo-500 focus:outline-none placeholder-neutral-600"
              />
              <button
                onClick={() => {
                  const label = variantName.trim() || `Variante ${savedVariants.length + 1}`
                  persistVariants([
                    ...savedVariants.filter((v) => v.name !== label),
                    { name: label, prompt: systemPrompt, date: new Date().toISOString() },
                  ])
                  setVariantName('')
                }}
                className="bg-neutral-800 hover:bg-neutral-700 px-3 py-1.5 rounded text-xs text-neutral-300 transition-colors"
              >
                Save
              </button>
            </div>

            <button
              onClick={handleSavePrompt}
              className="w-full bg-indigo-700 hover:bg-indigo-600 py-2 rounded-lg text-xs font-medium transition-colors"
            >
              Appliquer à la session
            </button>

            <div className="border-t border-neutral-800 pt-3">
              <label className="text-xs text-neutral-500 block mb-1">
                Modifier avec Grok
              </label>
              <textarea
                value={modifyInstructions}
                onChange={(e) => setModifyInstructions(e.target.value)}
                rows={3}
                placeholder="Ex: rends la narration plus sensuelle..."
                className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-neutral-300 resize-y focus:border-purple-500 focus:outline-none"
              />
              <button
                onClick={handleModifyWithGrok}
                disabled={modifying || !modifyInstructions}
                className="w-full mt-2 bg-purple-700 hover:bg-purple-600 disabled:opacity-40 py-2 rounded-lg text-xs font-medium transition-colors"
              >
                {modifying ? 'Modification en cours...' : 'Modifier avec Grok'}
              </button>
            </div>
          </div>
        )}

        {/* ── LoRA ── */}
        {tab === 'loras' && (
          <div className="space-y-4">
            {/* Style LoRAs (default, removable) */}
            <div>
              <h4 className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">Style LoRAs (par défaut)</h4>
              <p className="text-[10px] text-neutral-600 mb-2">Appliqués à chaque image. Modifie les poids ou retire-les.</p>
              {styleLoras.map((lora, i) => {
                const loraInfo = availableLoras.find((l) => l.id === lora.id)
                return (
                  <div key={i} className="bg-neutral-900 rounded-lg p-2 border border-neutral-800 space-y-1 mb-2">
                    <div className="flex items-center justify-between">
                      <select
                        value={lora.id}
                        onChange={(e) => updateStyleLoraId(i, e.target.value)}
                        className="flex-1 bg-neutral-950 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-300 focus:border-indigo-500 focus:outline-none"
                      >
                        <option value="">Sélectionner...</option>
                        {availableLoras.map((al) => (
                          <option key={al.id} value={al.id}>{al.name}</option>
                        ))}
                      </select>
                      <button onClick={() => removeStyleLora(i)} className="text-neutral-500 hover:text-red-400 text-sm ml-2">&times;</button>
                    </div>
                    <div className="flex items-center gap-2">
                      <input type="range" min={0} max={2} step={0.1} value={lora.weight}
                        onChange={(e) => updateStyleLoraWeight(i, parseFloat(e.target.value))} className="flex-1" />
                      <span className="text-xs font-mono text-neutral-400 w-8 text-right">{lora.weight.toFixed(1)}</span>
                    </div>
                  </div>
                )
              })}
              <button onClick={addStyleLora} className="text-xs text-indigo-400 hover:text-indigo-300">+ Ajouter style</button>
              <button onClick={saveStyleLoras}
                className="w-full mt-2 bg-indigo-700 hover:bg-indigo-600 py-1.5 rounded-lg text-xs font-medium transition-colors">
                Appliquer styles
              </button>
            </div>

            {/* Extra LoRAs (additional) */}
            <div className="border-t border-neutral-800 pt-3">
              <h4 className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">Extra LoRAs</h4>
              <p className="text-[10px] text-neutral-600 mb-2">LoRAs additionnels (en plus du casting et des styles).</p>

              {extraLoras.map((lora, i) => (
                <div key={i} className="bg-neutral-900 rounded-lg p-2 border border-neutral-800 space-y-1 mb-2">
                  <div className="flex items-center gap-2">
                    <select value={lora.id} onChange={(e) => updateExtraLoraField(i, 'id', e.target.value)}
                      className="flex-1 bg-neutral-950 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-300 focus:border-indigo-500 focus:outline-none">
                      <option value="">Sélectionner...</option>
                      {availableLoras.map((al) => (
                        <option key={al.id} value={al.id}>{al.name} ({al.type})</option>
                      ))}
                    </select>
                    <button onClick={() => removeExtraLora(i)} className="text-neutral-500 hover:text-red-400 text-sm">&times;</button>
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="range" min={-4} max={4} step={0.1} value={lora.weight}
                      onChange={(e) => updateExtraLoraField(i, 'weight', parseFloat(e.target.value))} className="flex-1" />
                    <span className="text-xs font-mono text-neutral-400 w-8 text-right">{lora.weight.toFixed(1)}</span>
                  </div>
                </div>
              ))}

              <button onClick={addExtraLora} className="text-xs text-indigo-400 hover:text-indigo-300">+ Ajouter extra</button>
              <button onClick={saveExtraLoras}
                className="w-full mt-2 bg-indigo-700 hover:bg-indigo-600 py-1.5 rounded-lg text-xs font-medium transition-colors">
                Appliquer extras
              </button>
            </div>
          </div>
        )}

        {/* ── Video ── */}
        {tab === 'video' && (
          <div className="space-y-3">
            {/* Current video status */}
            <div className="bg-neutral-900 rounded-lg p-3 border border-neutral-800">
              <h4 className="text-xs font-medium text-neutral-400 mb-2">Dernière vidéo</h4>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-neutral-500">Status:</span>
                  <span className={`font-mono ${videoStatus === 'ready' ? 'text-emerald-400' : videoStatus === 'generating' ? 'text-amber-400' : 'text-neutral-400'}`}>
                    {videoStatus}
                  </span>
                </div>
                {videoCost > 0 && (
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Cost:</span>
                    <span className="text-neutral-300 font-mono">${videoCost.toFixed(4)}</span>
                  </div>
                )}
                {videoGenerationTime > 0 && (
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Gen time:</span>
                    <span className="text-neutral-300">{videoGenerationTime}s</span>
                  </div>
                )}
                {videoPrompt && (
                  <div className="mt-2">
                    <span className="text-neutral-500 block mb-1">Prompt:</span>
                    <p className="text-neutral-400 text-[10px] whitespace-pre-wrap bg-neutral-950 rounded p-2">{videoPrompt}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Video settings for next sequence */}
            <div className="bg-neutral-900 rounded-lg p-3 border border-neutral-800">
              <h4 className="text-xs font-medium text-neutral-400 mb-2">Settings (prochaine séquence)</h4>
              <div className="space-y-2">
                <label className="flex items-center justify-between text-sm cursor-pointer">
                  <span className={videoSettings.simulate ? 'text-amber-400' : 'text-neutral-300'}>
                    {videoSettings.simulate ? 'Simulation (~60s, $0)' : 'Simulation'}
                  </span>
                  <input type="checkbox" checked={videoSettings.simulate || false}
                    onChange={(e) => setVideoSettings({ ...videoSettings, simulate: e.target.checked })}
                    className="rounded bg-neutral-800 border-neutral-700 text-amber-500" />
                </label>
                <label className="flex items-center justify-between text-sm cursor-pointer">
                  <span className={videoSettings.early_start ? 'text-emerald-400' : 'text-neutral-300'}>
                    {videoSettings.early_start ? 'Early start (from img 0)' : 'Early start'}
                  </span>
                  <input type="checkbox" checked={videoSettings.early_start || false}
                    onChange={(e) => setVideoSettings({ ...videoSettings, early_start: e.target.checked })}
                    className="rounded bg-neutral-800 border-neutral-700 text-emerald-500" />
                </label>
                <label className="flex items-center justify-between text-sm text-neutral-300 cursor-pointer">
                  <span>Draft mode</span>
                  <input type="checkbox" checked={videoSettings.draft}
                    onChange={(e) => setVideoSettings({ ...videoSettings, draft: e.target.checked })}
                    className="rounded bg-neutral-800 border-neutral-700 text-indigo-500" />
                </label>
                <label className="flex items-center justify-between text-sm text-neutral-300 cursor-pointer">
                  <span>Audio</span>
                  <input type="checkbox" checked={videoSettings.audio}
                    onChange={(e) => setVideoSettings({ ...videoSettings, audio: e.target.checked })}
                    className="rounded bg-neutral-800 border-neutral-700 text-indigo-500" />
                </label>
                <div>
                  <div className="flex justify-between text-xs">
                    <span className="text-neutral-400">Duration</span>
                    <span className="text-neutral-500 font-mono">{videoSettings.duration}s</span>
                  </div>
                  <input type="range" min={2} max={10} value={videoSettings.duration}
                    onChange={(e) => setVideoSettings({ ...videoSettings, duration: parseInt(e.target.value) })}
                    className="w-full mt-1" />
                </div>
                <div>
                  <label className="text-xs text-neutral-400">Resolution</label>
                  <select value={videoSettings.resolution}
                    onChange={(e) => setVideoSettings({ ...videoSettings, resolution: e.target.value })}
                    className="w-full mt-1 bg-neutral-950 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-300 focus:border-indigo-500 focus:outline-none">
                    <option value="720p">720p</option>
                    <option value="1080p">1080p</option>
                  </select>
                </div>
              </div>
              <button
                onClick={async () => { if (sessionId) await updateVideoSettings(sessionId, videoSettings) }}
                className="w-full mt-3 bg-indigo-700 hover:bg-indigo-600 py-1.5 rounded-lg text-xs font-medium transition-colors">
                Appliquer
              </button>
            </div>
          </div>
        )}

        {/* ── Mem0 Memory ── */}
        {tab === 'memory' && (
          <div className="space-y-3">
            {/* Live context from current sequence (SSE) */}
            {debugContext && (
              <div className="bg-neutral-950 rounded-lg p-3 border border-neutral-800">
                <h4 className="text-xs font-medium text-neutral-400 mb-2">
                  Contexte injecte (sequence en cours)
                </h4>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Modele</span>
                    <span className="text-neutral-300 font-mono">{debugContext.grokModel}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">System prompt</span>
                    <span className="text-neutral-300 font-mono">{debugContext.systemPromptLength} chars</span>
                  </div>
                </div>
              </div>
            )}

            {/* Persistent memory (cross-session) */}
            <div className="bg-neutral-950 rounded-lg p-3 border border-neutral-800">
              <h4 className="text-xs font-medium text-amber-400/80 mb-2">
                Memoire persistante (cross-session)
              </h4>
              {memoryLoading ? (
                <div className="flex items-center gap-2 text-xs text-neutral-500 py-2">
                  <div className="w-3 h-3 border border-neutral-700 border-t-indigo-500 rounded-full animate-spin" />
                  Chargement...
                </div>
              ) : (debugContext?.persistentMemory || memoryData?.persistent_memory) ? (
                <pre className="text-[10px] text-neutral-400 font-mono whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                  {debugContext?.persistentMemory || memoryData?.persistent_memory}
                </pre>
              ) : (
                <p className="text-[10px] text-neutral-600 italic">Aucun souvenir persistant pour ce cadre.</p>
              )}
            </div>

            {/* Narrative memory (within session) */}
            <div className="bg-neutral-950 rounded-lg p-3 border border-neutral-800">
              <h4 className="text-xs font-medium text-indigo-400/80 mb-2">
                Memoire narrative (session en cours)
              </h4>
              {memoryLoading ? (
                <div className="flex items-center gap-2 text-xs text-neutral-500 py-2">
                  <div className="w-3 h-3 border border-neutral-700 border-t-indigo-500 rounded-full animate-spin" />
                  Chargement...
                </div>
              ) : (debugContext?.narrativeMemory || memoryData?.narrative_memory) ? (
                <pre className="text-[10px] text-neutral-400 font-mono whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                  {debugContext?.narrativeMemory || memoryData?.narrative_memory}
                </pre>
              ) : (
                <p className="text-[10px] text-neutral-600 italic">
                  {sequenceNumber === 0 ? 'Premiere sequence — pas encore de memoire narrative.' : 'Aucun souvenir narratif.'}
                </p>
              )}
            </div>

            {/* Refresh button */}
            <button
              onClick={() => {
                if (!sessionId) return
                setMemoryLoading(true)
                getSessionMemories(sessionId)
                  .then(setMemoryData)
                  .catch(() => {})
                  .finally(() => setMemoryLoading(false))
              }}
              disabled={memoryLoading || !sessionId}
              className="w-full text-xs bg-neutral-800 hover:bg-neutral-700 disabled:opacity-30 py-2 rounded-lg text-neutral-400 transition-colors"
            >
              {memoryLoading ? 'Chargement...' : 'Rafraichir depuis Mem0'}
            </button>

            {/* Mem0 status */}
            <div className="text-[9px] text-neutral-600 text-center">
              Mem0: {memoryData?.mem0_enabled !== false ? 'active' : 'desactive'}
            </div>
          </div>
        )}

        {/* ── Costs ── */}
        {tab === 'costs' && (
          <div className="space-y-3">
            {/* Session totals */}
            {debugInfo && (
              <div className="bg-neutral-900 rounded-lg p-3 border border-neutral-800">
                <h4 className="text-xs font-medium text-neutral-400 mb-2">Session totale</h4>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Grok tokens (in/out):</span>
                    <span className="text-neutral-300 font-mono">
                      {debugInfo.costs.grok_input_tokens} / {debugInfo.costs.grok_output_tokens}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Grok cost:</span>
                    <span className="text-neutral-300 font-mono">
                      ${debugInfo.costs.grok_cost.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Images cost:</span>
                    <span className="text-neutral-300 font-mono">
                      ${debugInfo.costs.image_cost.toFixed(4)}
                    </span>
                  </div>
                  {videoCost > 0 && (
                    <div className="flex justify-between">
                      <span className="text-neutral-500">Video cost:</span>
                      <span className="text-neutral-300 font-mono">${videoCost.toFixed(4)}</span>
                    </div>
                  )}
                  <div className="flex justify-between border-t border-neutral-800 pt-1 mt-1">
                    <span className="text-neutral-400 font-medium">Total:</span>
                    <span className="text-emerald-400 font-mono font-medium">
                      ${debugInfo.costs.total.toFixed(4)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Per-sequence costs */}
            {allSequenceCosts.map((cost, i) => (
              <div key={i} className="bg-neutral-900 rounded-lg p-3 border border-neutral-800">
                <h4 className="text-xs font-medium text-neutral-400 mb-2">Sequence {i + 1}</h4>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Grok:</span>
                    <span className="font-mono text-neutral-300">
                      ${cost.grok_cost.toFixed(4)}
                      <span className="text-neutral-600 ml-1">
                        ({cost.grok_input_tokens}in/{cost.grok_output_tokens}out)
                      </span>
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Images:</span>
                    <span className="font-mono text-neutral-300">
                      {cost.image_costs.map((c, j) => (
                        <span key={j} className="ml-1">${c.toFixed(3)}</span>
                      ))}
                    </span>
                  </div>
                  {(cost.video_cost ?? 0) > 0 && (
                    <div className="flex justify-between">
                      <span className="text-neutral-500">Video:</span>
                      <span className="font-mono text-neutral-300">${cost.video_cost?.toFixed(4)}</span>
                    </div>
                  )}
                  {(cost.tts_cost ?? 0) > 0 && (
                    <div className="flex justify-between">
                      <span className="text-neutral-500">TTS:</span>
                      <span className="font-mono text-neutral-300">
                        ${cost.tts_cost?.toFixed(4)}
                        <span className="text-neutral-600 ml-1">
                          (audio ${(cost.tts_audio_cost ?? 0).toFixed(4)} + enh ${(cost.tts_enhance_cost ?? 0).toFixed(4)})
                        </span>
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Total:</span>
                    <span className="font-mono text-emerald-400">
                      ${cost.total_sequence_cost.toFixed(4)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Temps:</span>
                    <span className="text-neutral-400">{cost.elapsed_seconds}s</span>
                  </div>
                </div>
              </div>
            ))}

            {allSequenceCosts.length === 0 && (
              <p className="text-neutral-600 text-xs text-center py-8">
                Les coûts apparaissent après chaque séquence
              </p>
            )}
          </div>
        )}
      </div>
    </>
  )

  if (isDesktop) {
    return (
      <aside className="w-96 shrink-0 border-l border-neutral-800 bg-neutral-900/50 flex flex-col overflow-hidden pt-12">
        {panelContent}
      </aside>
    )
  }

  return (
    <BottomSheet open onClose={onClose ?? (() => {})} initialHeight="70vh">
      <div className="flex flex-col h-full bg-neutral-900/95">
        {panelContent}
      </div>
    </BottomSheet>
  )
}
