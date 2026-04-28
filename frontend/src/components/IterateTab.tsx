import { useEffect, useMemo, useState } from 'react'
import {
  fetchIterateScenes, fetchIterateSystemPrompt, iterateRecraft,
  fetchPlaygroundConfig,
  type IterateScene,
} from '../api/client'

interface LoraEntry { id: string; weight: number }
interface AvailableLora { id: string; name: string; type: string }

/**
 * Prompt-builder iteration lab.
 *
 * Lets the developer pick a scene from a past game session, see the original
 * Z-Image prompt + the EXACT inputs the prompt-builder agent received, edit
 * the agent's SYSTEM_PROMPT in a textarea, and re-run the full chain
 * (prompt-builder → Z-Image) with those same inputs to compare outputs.
 *
 * Goal: iterate on the SYSTEM_PROMPT teaching against real-game data without
 * having to reproduce the full game flow each time. When happy, manually
 * copy the improved SYSTEM_PROMPT back into backend/scene_agent.py.
 */

interface RecraftResult {
  crafted_prompt: string
  craft_elapsed: number
  image: {
    url: string
    cost: number
    seed: number | null
    elapsed: number
    settings: {
      final_prompt: string
      loras: { id: string; weight: number }[]
      width: number
      height: number
      steps: number
      cfg: number
    }
  }
}

export default function IterateTab() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [scenes, setScenes] = useState<IterateScene[]>([])
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [defaultSystemPrompt, setDefaultSystemPrompt] = useState('')
  const [useOriginalSeed, setUseOriginalSeed] = useState(true)
  const [recrafting, setRecrafting] = useState(false)
  const [result, setResult] = useState<RecraftResult | null>(null)

  // Mood + LoRA editor state — re-initialised when user picks a new scene.
  const [moodName, setMoodName] = useState<string>('')
  const [moodPromptBlock, setMoodPromptBlock] = useState<string>('')
  const [moodDescription, setMoodDescription] = useState<string>('')
  const [moodCharLoraWeight, setMoodCharLoraWeight] = useState<number | ''>('')
  const [loras, setLoras] = useState<LoraEntry[]>([])
  const [availableLoras, setAvailableLoras] = useState<AvailableLora[]>([])
  const [productionMoods, setProductionMoods] = useState<Record<string, { description: string; prompt_block?: string; lora?: { id: string; name: string; weight: number } | null }>>({})

  // Load scenes + default SYSTEM_PROMPT + playground config (LoRAs, prod moods) once on mount.
  useEffect(() => {
    setLoading(true)
    Promise.all([fetchIterateScenes(50), fetchIterateSystemPrompt(), fetchPlaygroundConfig()])
      .then(([scn, sys, cfg]) => {
        setScenes(scn.scenes || [])
        setSystemPrompt(sys.system_prompt || '')
        setDefaultSystemPrompt(sys.system_prompt || '')
        setAvailableLoras(cfg.loras || [])
        setProductionMoods(cfg.moods || {})
        if ((scn.scenes || []).length > 0) {
          const first = scn.scenes[0]
          setSelectedKey(`${first.session_id}:${first.sequence_number}:${first.scene_index}`)
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const selected: IterateScene | null = useMemo(() => {
    if (!selectedKey) return null
    return scenes.find((s) => `${s.session_id}:${s.sequence_number}:${s.scene_index}` === selectedKey) || null
  }, [selectedKey, scenes])

  // Re-initialise mood + LoRA editor whenever the selected scene changes.
  useEffect(() => {
    if (!selected) return
    const ri = selected.replay_inputs || {}
    const mn: string = ri.mood_name || ''
    const md: any = ri.mood_data || {}
    setMoodName(mn)
    setMoodPromptBlock(md.prompt_block || '')
    setMoodDescription(md.description || '')
    setMoodCharLoraWeight(typeof md.char_lora_weight === 'number' ? md.char_lora_weight : '')
    setLoras((selected.loras_applied || []).map((l) => ({ id: l.id, weight: l.weight })))
  }, [selected])

  // Detect whether the mood block / LoRAs are still pristine for diff hint.
  const moodIsPristine = useMemo(() => {
    if (!selected) return true
    const md: any = selected.replay_inputs?.mood_data || {}
    return moodPromptBlock === (md.prompt_block || '') &&
           moodDescription === (md.description || '') &&
           moodCharLoraWeight === (typeof md.char_lora_weight === 'number' ? md.char_lora_weight : '')
  }, [selected, moodPromptBlock, moodDescription, moodCharLoraWeight])
  const lorasArePristine = useMemo(() => {
    if (!selected) return true
    const orig = selected.loras_applied || []
    if (orig.length !== loras.length) return false
    return loras.every((l, i) => l.id === orig[i].id && Math.abs(l.weight - orig[i].weight) < 0.0001)
  }, [selected, loras])

  const handleRecraft = async () => {
    if (!selected) return
    setRecrafting(true)
    setError('')
    setResult(null)
    try {
      // Build mood override: take the original mood_data and replace
      // prompt_block / description / char_lora_weight with the edited values.
      const origMd: any = selected.replay_inputs?.mood_data || {}
      const moodOverride: Record<string, any> = {
        ...origMd,
        prompt_block: moodPromptBlock,
        description: moodDescription,
      }
      if (moodCharLoraWeight !== '' && !Number.isNaN(Number(moodCharLoraWeight))) {
        moodOverride.char_lora_weight = Number(moodCharLoraWeight)
      } else {
        delete moodOverride.char_lora_weight
      }
      const r = await iterateRecraft({
        replay_inputs: selected.replay_inputs,
        system_prompt: systemPrompt,
        use_original_seed: useOriginalSeed,
        seed: useOriginalSeed ? selected.seed : null,
        width: selected.width,
        height: selected.height,
        steps: selected.steps,
        loras: loras.length ? loras : null,
        mood_data_override: moodOverride,
        mood_name_override: moodName || null,
      })
      setResult(r)
    } catch (e: any) {
      setError(e.message || 'Recraft failed')
    } finally {
      setRecrafting(false)
    }
  }

  const handleReset = () => setSystemPrompt(defaultSystemPrompt)

  const handleResetMood = () => {
    if (!selected) return
    const md: any = selected.replay_inputs?.mood_data || {}
    setMoodPromptBlock(md.prompt_block || '')
    setMoodDescription(md.description || '')
    setMoodCharLoraWeight(typeof md.char_lora_weight === 'number' ? md.char_lora_weight : '')
  }
  const handleResetLoras = () => {
    if (!selected) return
    setLoras((selected.loras_applied || []).map((l) => ({ id: l.id, weight: l.weight })))
  }
  const handleLoadFromProductionMood = (key: string) => {
    const m = productionMoods[key]
    if (!m) return
    setMoodName(key)
    setMoodPromptBlock(m.prompt_block || '')
    setMoodDescription(m.description || '')
    if (m.lora) {
      // Insert/replace the production mood's LoRA in the list (others kept).
      setLoras((prev) => {
        const filtered = prev.filter((l) => l.id !== m.lora!.id)
        return [...filtered, { id: m.lora!.id, weight: m.lora!.weight }]
      })
    }
  }
  const handleCopyMoodConfig = async () => {
    const cfg: Record<string, any> = {
      description: moodDescription,
      prompt_block: moodPromptBlock,
    }
    if (moodCharLoraWeight !== '' && !Number.isNaN(Number(moodCharLoraWeight))) {
      cfg.char_lora_weight = Number(moodCharLoraWeight)
    }
    // Loras: by convention, the first non-character LoRA is the mood's "lora".
    const moodLora = loras.find((l) => {
      const meta = availableLoras.find((a) => a.id === l.id)
      return meta && meta.type !== 'character'
    })
    if (moodLora) {
      const meta = availableLoras.find((a) => a.id === moodLora.id)
      cfg.lora = { id: moodLora.id, name: meta?.name || moodLora.id, weight: moodLora.weight }
    }
    const json = `"${moodName || 'new_mood'}": ${JSON.stringify(cfg, null, 4)},`
    try {
      await navigator.clipboard.writeText(json)
    } catch {
      // Fallback: show in a window prompt for manual copy
      window.prompt('Copy this mood config and paste into backend/config.py DEFAULT_STYLE_MOODS:', json)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-950/40 border border-red-900/50 rounded p-3 text-xs text-red-300">{error}</div>
      )}

      {/* Scene picker */}
      <div className="space-y-2">
        <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
          Pick a scene from past games {loading && <span className="text-amber-500 ml-2">loading…</span>}
        </label>
        <select
          value={selectedKey}
          onChange={(e) => { setSelectedKey(e.target.value); setResult(null) }}
          className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-2 text-xs text-neutral-300 focus:border-amber-600 focus:outline-none"
        >
          <option value="">— select a scene —</option>
          {scenes.map((s) => {
            const k = `${s.session_id}:${s.sequence_number}:${s.scene_index}`
            const sumPreview = (s.scene_summary || '(no summary)').slice(0, 70)
            const ts = s.timestamp ? s.timestamp.slice(5, 16).replace('T', ' ') : ''
            return (
              <option key={k} value={k}>
                {ts} · seq {s.sequence_number} #{s.scene_index} · {sumPreview}
              </option>
            )
          })}
        </select>
        {!loading && scenes.length === 0 && (
          <p className="text-[11px] text-neutral-500 italic">
            No scenes captured yet. Play a sequence and come back — only scenes generated AFTER the iterate
            feature shipped will appear here (older logs lack the replay_inputs snapshot).
          </p>
        )}
      </div>

      {selected && (
        <>
          {/* Original scene panel */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Original image */}
            <div className="space-y-2">
              <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">Original image</label>
              {selected.image_url ? (
                <img
                  src={selected.image_url}
                  alt="Original"
                  className="w-full rounded-lg border border-neutral-800"
                  style={{ maxHeight: '50vh', objectFit: 'contain' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
              ) : (
                <div className="text-[11px] text-neutral-600 italic p-4 border border-neutral-900 rounded-lg">
                  Image URL not available (may have expired or wasn't persisted).
                </div>
              )}
              <div className="text-[10px] text-neutral-500 font-mono space-y-0.5">
                <div>seed: <span className="text-neutral-300">{selected.seed ?? 'random'}</span></div>
                <div>loras: <span className="text-neutral-300">{selected.loras_applied?.map((l) => `${l.id}@${l.weight}`).join(', ') || 'none'}</span></div>
                {selected.width && <div>{selected.width}×{selected.height} · {selected.steps} steps</div>}
              </div>
            </div>

            {/* Original prompt + caller inputs */}
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
                  Z-Image prompt sent (the result of the prompt-builder agent)
                </label>
                <pre className="mt-1 bg-neutral-950 border border-neutral-800 rounded p-2 text-[11px] text-neutral-300 whitespace-pre-wrap font-mono max-h-44 overflow-y-auto">
                  {selected.final_prompt || '(empty)'}
                </pre>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
                  Narrator caller inputs (what the prompt-builder received)
                </label>
                <div className="mt-1 bg-neutral-950 border border-neutral-800 rounded p-2 text-[11px] text-neutral-400 font-mono space-y-1 max-h-44 overflow-y-auto">
                  <Field label="scene_summary" value={selected.replay_inputs?.scene_summary} />
                  <Field label="shot_intent" value={selected.replay_inputs?.shot_intent} />
                  <Field label="mood_name" value={selected.replay_inputs?.mood_name} />
                  <Field label="actors_present" value={(selected.replay_inputs?.actors_present || []).join(', ')} />
                  <Field label="time_of_day" value={selected.replay_inputs?.time_of_day} />
                  <Field label="location_hint" value={selected.replay_inputs?.location_hint} />
                  <Field label="setting_label" value={selected.replay_inputs?.setting_label} />
                  <Field label="custom_setting_text" value={selected.replay_inputs?.custom_setting_text} truncate />
                  <Field label="language" value={selected.replay_inputs?.language} />
                  <Field label="player_gender" value={selected.replay_inputs?.player_gender} />
                  <Field label="clothing_state" value={fmtDict(selected.replay_inputs?.clothing_state)} truncate />
                  <Field label="appearance_state" value={fmtDict(selected.replay_inputs?.appearance_state)} truncate />
                </div>
              </div>
            </div>
          </div>

          {/* SYSTEM_PROMPT editor */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
                Prompt-builder SYSTEM_PROMPT (edit and re-craft)
              </label>
              <button
                onClick={handleReset}
                className="text-[10px] text-amber-500 hover:text-amber-400"
                title="Reset to current production SYSTEM_PROMPT"
              >
                ↺ reset to default
              </button>
            </div>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={20}
              className="w-full bg-neutral-950 border border-neutral-800 rounded p-3 text-[11px] text-neutral-200 font-mono focus:border-amber-600 focus:outline-none resize-y"
              spellCheck={false}
            />
            <div className="text-[10px] text-neutral-600 font-mono">
              {systemPrompt.length} chars · {systemPrompt === defaultSystemPrompt ? 'unchanged from default' : 'edited'}
            </div>
          </div>

          {/* Mood editor */}
          <div className="space-y-2 pt-3 border-t border-neutral-900">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
                Mood — name, prompt block (incorporated by Grok), LoRA weight tweaks
              </label>
              <div className="flex items-center gap-2">
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) handleLoadFromProductionMood(e.target.value)
                    e.target.value = ''
                  }}
                  className="bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-[10px] text-neutral-300 focus:border-amber-600 focus:outline-none"
                  title="Load another production mood as a starting point"
                >
                  <option value="">↩ load production mood…</option>
                  {Object.keys(productionMoods).sort().map((k) => (
                    <option key={k} value={k}>{k}</option>
                  ))}
                </select>
                <button
                  onClick={handleResetMood}
                  className="text-[10px] text-amber-500 hover:text-amber-400"
                  title="Reset to the original mood as captured for this scene"
                >↺ reset</button>
                <button
                  onClick={handleCopyMoodConfig}
                  className="text-[10px] text-emerald-500 hover:text-emerald-400"
                  title="Copy the current mood config as JSON to paste into backend/config.py DEFAULT_STYLE_MOODS"
                >📋 copy config</button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <div>
                <label className="text-[10px] text-neutral-500 font-mono">name (key)</label>
                <input
                  type="text"
                  value={moodName}
                  onChange={(e) => setMoodName(e.target.value)}
                  placeholder="e.g. sensual_tease, my_new_mood"
                  className="w-full bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-200 font-mono focus:border-amber-600 focus:outline-none"
                />
              </div>
              <div className="md:col-span-2">
                <label className="text-[10px] text-neutral-500 font-mono">description (one-liner)</label>
                <input
                  type="text"
                  value={moodDescription}
                  onChange={(e) => setMoodDescription(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-200 focus:border-amber-600 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="text-[10px] text-neutral-500 font-mono">prompt_block (incorporated by Grok into the Z-Image prompt)</label>
              <textarea
                value={moodPromptBlock}
                onChange={(e) => setMoodPromptBlock(e.target.value)}
                rows={4}
                placeholder="e.g. soft warm lighting, intimate atmosphere, faces close, hand brushing cheek..."
                className="w-full bg-neutral-950 border border-neutral-800 rounded p-2 text-[11px] text-neutral-200 font-mono focus:border-amber-600 focus:outline-none resize-y"
                spellCheck={false}
              />
            </div>
            <div className="flex items-center gap-3">
              <label className="text-[10px] text-neutral-500 font-mono">char_lora_weight override (optional, drops main char LoRA when a pose LoRA must dominate):</label>
              <input
                type="number"
                step={0.05}
                min={0}
                max={1.5}
                value={moodCharLoraWeight}
                onChange={(e) => setMoodCharLoraWeight(e.target.value === '' ? '' : parseFloat(e.target.value))}
                placeholder="—"
                className="w-20 bg-neutral-950 border border-neutral-800 rounded px-2 py-1 text-xs text-neutral-200 font-mono focus:border-amber-600 focus:outline-none"
              />
              {!moodIsPristine && (
                <span className="text-[10px] text-amber-500 font-mono">edited</span>
              )}
            </div>
          </div>

          {/* LoRA editor */}
          <div className="space-y-2 pt-3 border-t border-neutral-900">
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
                LoRAs (sliders set strength · max 3 active in production · order matters)
              </label>
              <button
                onClick={handleResetLoras}
                className="text-[10px] text-amber-500 hover:text-amber-400"
              >↺ reset to original</button>
            </div>
            <div className="space-y-1.5">
              {loras.map((lo, i) => {
                const meta = availableLoras.find((a) => a.id === lo.id)
                return (
                  <div key={i} className="flex items-center gap-2">
                    <select
                      value={lo.id}
                      onChange={(e) => {
                        const next = [...loras]
                        next[i] = { ...next[i], id: e.target.value }
                        setLoras(next)
                      }}
                      className="flex-1 bg-neutral-900 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-300 focus:border-amber-600 focus:outline-none"
                    >
                      {availableLoras.map((a) => (
                        <option key={a.id} value={a.id}>{a.name} ({a.type})</option>
                      ))}
                      {!meta && <option value={lo.id}>{lo.id} (unknown)</option>}
                    </select>
                    <input
                      type="range"
                      min={-2} max={2} step={0.05}
                      value={lo.weight}
                      onChange={(e) => {
                        const next = [...loras]
                        next[i] = { ...next[i], weight: parseFloat(e.target.value) }
                        setLoras(next)
                      }}
                      className="w-32 accent-amber-600"
                    />
                    <input
                      type="number"
                      step={0.05} min={-2} max={2}
                      value={lo.weight}
                      onChange={(e) => {
                        const next = [...loras]
                        next[i] = { ...next[i], weight: parseFloat(e.target.value) || 0 }
                        setLoras(next)
                      }}
                      className="w-16 bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-xs text-neutral-200 font-mono focus:border-amber-600 focus:outline-none"
                    />
                    <button
                      onClick={() => setLoras(loras.filter((_, j) => j !== i))}
                      className="text-neutral-600 hover:text-red-400 text-xs"
                      title="remove"
                    >✕</button>
                  </div>
                )
              })}
              <button
                onClick={() => availableLoras[0] && setLoras([...loras, { id: availableLoras[0].id, weight: 0.8 }])}
                className="text-[10px] text-amber-500 hover:text-amber-400"
              >+ add LoRA</button>
              {!lorasArePristine && (
                <span className="ml-3 text-[10px] text-amber-500 font-mono">edited</span>
              )}
            </div>
          </div>

          {/* Run controls */}
          <div className="flex items-center gap-3 pt-2 border-t border-neutral-900">
            <label className="text-[11px] text-neutral-400 flex items-center gap-2">
              <input
                type="checkbox"
                checked={useOriginalSeed}
                onChange={(e) => setUseOriginalSeed(e.target.checked)}
                className="w-3.5 h-3.5 accent-amber-600"
              />
              Use original seed ({selected.seed ?? 'n/a'}) for apples-to-apples comparison
            </label>
            <div className="flex-1" />
            <button
              onClick={handleRecraft}
              disabled={recrafting || !systemPrompt.trim()}
              className="px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:bg-neutral-800 disabled:text-neutral-600 text-white text-xs font-medium rounded transition-colors"
            >
              {recrafting ? 'Crafting + rendering…' : 'Re-craft & render'}
            </button>
          </div>

          {/* Result panel */}
          {result && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-neutral-900">
              <div className="space-y-2">
                <label className="text-[10px] uppercase tracking-wider text-emerald-500 font-mono">
                  New image (custom SYSTEM_PROMPT)
                </label>
                <img
                  src={result.image.url}
                  alt="Recrafted"
                  className="w-full rounded-lg border border-emerald-900/40"
                  style={{ maxHeight: '50vh', objectFit: 'contain' }}
                />
                <div className="text-[10px] text-neutral-500 font-mono space-y-0.5">
                  <div>seed: <span className="text-neutral-300">{result.image.seed ?? 'random'}</span></div>
                  <div>cost: <span className="text-neutral-300">${result.image.cost.toFixed(4)}</span> · {result.image.elapsed}s render · {result.craft_elapsed}s craft</div>
                  <div>loras: <span className="text-neutral-300">{result.image.settings.loras?.map((l) => `${l.id}@${l.weight}`).join(', ') || 'none'}</span></div>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] uppercase tracking-wider text-emerald-500 font-mono">
                  New Z-Image prompt
                </label>
                <pre className="bg-neutral-950 border border-emerald-900/40 rounded p-2 text-[11px] text-neutral-300 whitespace-pre-wrap font-mono max-h-[50vh] overflow-y-auto">
                  {result.crafted_prompt}
                </pre>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Field({ label, value, truncate }: { label: string; value: any; truncate?: boolean }) {
  const v = value === undefined || value === null || value === '' ? '—' : String(value)
  const display = truncate && v.length > 200 ? v.slice(0, 200) + '…' : v
  return (
    <div>
      <span className="text-neutral-600">{label}:</span>{' '}
      <span className="text-neutral-300">{display}</span>
    </div>
  )
}

function fmtDict(d: Record<string, string> | undefined): string {
  if (!d || Object.keys(d).length === 0) return ''
  return Object.entries(d).map(([k, v]) => `${k}: ${(v || '').slice(0, 60)}`).join(' | ')
}
