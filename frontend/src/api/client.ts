import type { SSEEvent, Actor, Setting, LoraInfo, ExtraLora, GrokModel, KnownWhereabout } from './types'
import { useAuthStore } from '../stores/authStore'

// In dev (Vite): empty → /api proxied to localhost:8001
// In prod (Railway): set VITE_API_BASE to the backend service URL
const BASE = import.meta.env.VITE_API_BASE || ''

// ─── Auth-aware fetch helper ─────────────────────────────────────────────────

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
    ...(options.headers as Record<string, string> || {}),
  }
  return fetch(`${BASE}${url}`, { ...options, headers })
}

// ─── Session History ─────────────────────────────────────────────────────────

export async function listSessions(): Promise<any[]> {
  const res = await apiFetch('/api/user/sessions')
  const data = await res.json()
  return data.sessions || []
}

export async function resumeSession(sessionId: string) {
  const res = await apiFetch(`/api/user/sessions/${sessionId}/resume`, { method: 'POST' })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function deleteSession(sessionId: string) {
  const res = await apiFetch(`/api/user/sessions/${sessionId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error((await res.json()).detail)
}

export async function clearAllMemories(): Promise<{ cleared: number }> {
  const res = await apiFetch('/api/user/memories', { method: 'DELETE' })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function getSessionHistory(sessionId: string) {
  const res = await apiFetch(`/api/user/sessions/${sessionId}/history`)
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

// ─── REST API ────────────────────────────────────────────────────────────────

export async function checkAdmin(): Promise<boolean> {
  try {
    const res = await apiFetch('/api/admin/check')
    const data = await res.json()
    return data.is_admin
  } catch { return false }
}

export async function fetchAdminCosts() {
  const res = await apiFetch('/api/admin/costs')
  if (!res.ok) throw new Error('Admin access denied')
  return res.json()
}

export async function fetchDefaultStyleMoods() {
  const res = await apiFetch('/api/default-style-moods')
  return res.json()
}

export async function fetchGrokModels(): Promise<{ models: GrokModel[]; default: string }> {
  const res = await apiFetch('/api/grok-models')
  return res.json()
}

export async function fetchActors(): Promise<Actor[]> {
  const res = await apiFetch(`/api/actors`)
  const data = await res.json()
  return data.actors
}

export async function fetchSettings(): Promise<Setting[]> {
  const res = await apiFetch(`/api/settings`)
  const data = await res.json()
  return data.settings
}

export async function previewSystemPrompt(params: {
  player: { name: string; age: number; gender: string; preferences: string }
  setting: string
  actors: string[]
  custom_setting?: string
}): Promise<string> {
  const res = await apiFetch(`/api/game/preview-prompt`, {
    method: 'POST',
    body: JSON.stringify(params),
  })
  const data = await res.json()
  return data.prompt
}

export async function fetchLanguages(): Promise<{ languages: { code: string; label: string }[]; default: string }> {
  const res = await apiFetch('/api/languages')
  return res.json()
}

export async function startGame(params: {
  player: { name: string; age: number; gender: string; preferences: string }
  setting: string
  actors: string[]
  actor_genders?: Record<string, string>
  custom_setting?: string
  system_prompt_override?: string
  style_moods?: Record<string, any>
  grok_model?: string
  language?: string
  video_simulate?: boolean
  video_early_start?: boolean
  video_hd?: boolean
  video_short?: boolean
  video_backend?: string
  video_draft?: boolean
  video_start_scene?: number
  pvideo_prompt_upsampling?: boolean
  custom_character_desc?: string
  voice_narration?: boolean
  voice_to_video?: boolean
  voice_id?: string
  voice_language?: string
  voice_enhance?: boolean
  voice_stereo?: boolean
  slice_of_life?: boolean
}) {
  const res = await apiFetch(`/api/game/start`, {
    method: 'POST',
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

// ─── Phone Chat ─────────────────────────────────────────────────────────────

export interface PhoneChatHandlers {
  onMessageDelta: (text: string) => void
  onMessageDone: (text: string, character: string) => void
  onSelfieGenerating: () => void
  onSelfieReady: (url: string, cost: number) => void
  onRendezvousAdded?: (rdv: KnownWhereabout) => void
  onError: (error: string) => void
}

export async function streamPhoneChat(
  params: { sessionId: string; characterCode: string; message: string },
  handlers: PhoneChatHandlers,
): Promise<void> {
  const res = await apiFetch('/api/game/phone-chat', {
    method: 'POST',
    body: JSON.stringify({
      session_id: params.sessionId,
      character_code: params.characterCode,
      message: params.message,
    }),
  })
  if (!res.ok || !res.body) { handlers.onError('Phone chat failed'); return }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'message_delta') handlers.onMessageDelta(data.content)
        else if (data.type === 'message_done') handlers.onMessageDone(data.text, data.character)
        else if (data.type === 'selfie_generating') handlers.onSelfieGenerating()
        else if (data.type === 'selfie_ready') handlers.onSelfieReady(data.url, data.cost)
        else if (data.type === 'rendezvous_added') handlers.onRendezvousAdded?.(data.rendezvous)
        else if (data.type === 'error') handlers.onError(data.message)
      } catch { /* skip */ }
    }
  }
}

// ─── Scene Chat ─────────────────────────────────────────────────────────────

export async function streamSceneChat(
  params: {
    sessionId: string
    sceneIndex: number
    message: string
    currentNarration: string
    imagePrompt: string
    imageSeed?: number | null
    actorsPresent: string[]
    styleMoods: string[]
    locationDescription: string
    clothingState?: Record<string, string>
  },
  onNarration: (text: string) => void,
  onNarrationDone: (fullText: string) => void,
  onImageGenerating: () => void,
  onImageReady: (url: string, cost: number, prompt: string) => void,
  onError: (error: string) => void,
): Promise<void> {
  const res = await apiFetch('/api/game/scene-chat', {
    method: 'POST',
    body: JSON.stringify({
      session_id: params.sessionId,
      scene_index: params.sceneIndex,
      message: params.message,
      current_narration: params.currentNarration,
      image_prompt: params.imagePrompt,
      image_seed: params.imageSeed,
      actors_present: params.actorsPresent,
      style_moods: params.styleMoods,
      location_description: params.locationDescription,
      clothing_state: params.clothingState,
    }),
  })

  if (!res.ok || !res.body) {
    onError('Scene chat request failed')
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'narration_delta') onNarration(data.content)
        else if (data.type === 'narration_done') onNarrationDone(data.text)
        else if (data.type === 'image_generating') onImageGenerating()
        else if (data.type === 'image_ready') onImageReady(data.url, data.cost, data.prompt)
        else if (data.type === 'error') onError(data.message)
      } catch { /* skip */ }
    }
  }
}

// ─── Regen ───────────────────────────────────────────────────────────────────

export async function rewriteImagePrompt(
  currentPrompt: string,
  instructions: string,
  onText: (text: string) => void,
  onDone: (fullText: string) => void,
) {
  const res = await apiFetch(`/api/game/rewrite-prompt`, {
    method: 'POST',
    body: JSON.stringify({ current_prompt: currentPrompt, instructions }),
  })
  if (!res.body) return
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'text') onText(data.content)
        if (data.type === 'done') onDone(data.full_text)
      } catch { /* skip */ }
    }
  }
}

export interface RegenImageOptions {
  sessionId: string
  prompt: string
  actorsPresent?: string[]
  imageIndex?: number
  useNsfwStyle?: boolean
  seed?: number
  loraOverrides?: { id: string; weight: number }[]
  width?: number
  height?: number
  steps?: number
}

export async function regenImage(opts: RegenImageOptions) {
  const res = await apiFetch(`/api/game/regen-image`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: opts.sessionId,
      prompt: opts.prompt,
      actors_present: opts.actorsPresent || [],
      image_index: opts.imageIndex,
      use_nsfw_style: opts.useNsfwStyle || false,
      seed: opts.seed || undefined,
      lora_overrides: opts.loraOverrides || undefined,
      width: opts.width || undefined,
      height: opts.height || undefined,
      steps: opts.steps || undefined,
    }),
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return (await res.json()).result
}

export async function regenSceneVideo(params: {
  session_id: string
  scene_index: number
  image_url: string
  prompt?: string
  draft?: boolean
}): Promise<{ video_url: string; cost: number; elapsed: number; draft: boolean; prompt_used: string }> {
  const res = await apiFetch('/api/game/regen-scene-video', {
    method: 'POST',
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function regenVideo(sessionId: string, prompt: string, inputImageUrl: string) {
  const res = await apiFetch(`/api/game/regen-video`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, prompt, input_image_url: inputImageUrl }),
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return (await res.json()).result
}

// ─── SSE Streaming ───────────────────────────────────────────────────────────

export async function streamSequence(
  sessionId: string,
  choiceId?: string,
  choiceText?: string,
  onEvent?: (event: SSEEvent) => void,
): Promise<void> {
  const res = await apiFetch(`/api/game/sequence`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      choice_id: choiceId,
      choice_text: choiceText,
    }),
  })

  if (!res.ok) throw new Error('Sequence request failed')
  if (!res.body) throw new Error('No response body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const event: SSEEvent = JSON.parse(line.slice(6))
        onEvent?.(event)
      } catch {
        // skip malformed
      }
    }
  }
}

// ─── Debug API ───────────────────────────────────────────────────────────────

export async function getSystemPrompt(sessionId: string) {
  const res = await apiFetch(`/api/debug/system-prompt/${sessionId}`)
  return res.json()
}

export async function updateSystemPrompt(sessionId: string, prompt: string) {
  await apiFetch(`/api/debug/system-prompt`, {
    method: 'PUT',
    body: JSON.stringify({ session_id: sessionId, prompt }),
  })
}

export async function resetSystemPrompt(sessionId: string) {
  await apiFetch(`/api/debug/system-prompt/${sessionId}`, { method: 'DELETE' })
}

export async function getSessionDebug(sessionId: string) {
  const res = await apiFetch(`/api/debug/session/${sessionId}`)
  return res.json()
}

export async function getSessionMemories(sessionId: string) {
  const res = await apiFetch(`/api/debug/memories/${sessionId}`)
  return res.json()
}

export interface Mem0Item {
  id?: string
  memory: string
  created_at?: string
  updated_at?: string
  metadata?: any
}

export interface Mem0AllResponse {
  mem0_enabled: boolean
  session_id?: string
  setting_id?: string
  scopes?: {
    session_narrative: { scope_id: string; memories: Mem0Item[] }
    persistent: { scope_id: string; memories: Mem0Item[] }
    per_character: Record<string, { scope_id: string; memories: Mem0Item[] }>
  }
}

export async function getAllMem0(sessionId: string): Promise<Mem0AllResponse> {
  const res = await apiFetch(`/api/debug/mem0/all/${sessionId}`)
  return res.json()
}

export async function getVideoSettings(sessionId: string) {
  const res = await apiFetch(`/api/debug/video-settings/${sessionId}`)
  return (await res.json()).video_settings
}

export async function updateVideoSettings(sessionId: string, settings: {
  draft: boolean; audio: boolean; duration: number; resolution: string
}) {
  await apiFetch(`/api/debug/video-settings`, {
    method: 'PUT',
    body: JSON.stringify({ session_id: sessionId, ...settings }),
  })
}

export async function fetchAvailableLoras(): Promise<LoraInfo[]> {
  const res = await apiFetch(`/api/debug/loras`)
  const data = await res.json()
  return data.loras
}

export async function getStyleLoras(sessionId: string): Promise<ExtraLora[]> {
  const res = await apiFetch(`/api/debug/style-loras/${sessionId}`)
  const data = await res.json()
  return data.style_loras
}

export async function updateStyleLoras(sessionId: string, loras: ExtraLora[]) {
  await apiFetch(`/api/debug/style-loras`, {
    method: 'PUT',
    body: JSON.stringify({ session_id: sessionId, style_loras: loras }),
  })
}

export async function getExtraLoras(sessionId: string): Promise<ExtraLora[]> {
  const res = await apiFetch(`/api/debug/extra-loras/${sessionId}`)
  const data = await res.json()
  return data.extra_loras
}

export async function updateExtraLoras(sessionId: string, loras: ExtraLora[]) {
  await apiFetch(`/api/debug/extra-loras`, {
    method: 'PUT',
    body: JSON.stringify({ session_id: sessionId, extra_loras: loras }),
  })
}

export async function streamPromptModification(
  sessionId: string,
  instructions: string,
  onText: (text: string) => void,
  onDone: (fullText: string) => void,
) {
  const res = await apiFetch(`/api/debug/modify-prompt`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, instructions }),
  })
  if (!res.body) return

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'text') onText(data.content)
        if (data.type === 'done') onDone(data.full_text)
      } catch { /* skip */ }
    }
  }
}

// ─── Playground (no auth) ───────────────────────────────────────────────────

export async function fetchPlaygroundConfig(): Promise<{
  actors: { code: string; name: string; description: string }[]
  settings: { id: string; name: string }[]
  moods: Record<string, {
    description: string
    prompt_block?: string
    lora?: { id: string; name: string; weight: number } | null
  }>
  loras: { id: string; name: string; type: string }[]
  defaults: { width: number; height: number; steps: number }
  languages: string[]
  tts?: {
    voices: { id: string; label: string }[]
    languages: string[]
  }
}> {
  const res = await fetch(`${BASE}/api/playground/config`)
  if (!res.ok) throw new Error('Failed to fetch playground config')
  return res.json()
}

export async function generatePlayground(params: {
  scene_description: string
  actor: string
  setting: string
  mood: string
  language?: string
  width?: number
  height?: number
  steps?: number
  seed?: number | null
  lora_overrides?: { id: string; weight: number }[] | null
  skip_image?: boolean
  raw_mode?: boolean
  custom_mood_block?: string
}): Promise<{
  simulated_prompt: string
  actors_present: string[]
  style_moods: string[]
  narration: string
  image: {
    url: string
    cost: number
    seed: number | null
    elapsed: number
    settings: {
      width: number; height: number; steps: number; cfg: number
      loras: { id: string; weight: number }[]
      style_moods: string[]
      final_prompt: string
    }
  } | null
  image_error?: string
}> {
  const res = await fetch(`${BASE}/api/playground/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Playground generation failed')
  }
  return res.json()
}

// ─── Prompt-builder Iteration Lab ───────────────────────────────────────────

export interface IterateScene {
  session_id: string
  sequence_number: number
  scene_index: number
  timestamp: string
  scene_summary: string
  shot_intent: string
  mood: string
  actors_present: string[]
  final_prompt: string
  replay_inputs: Record<string, any>
  image_url: string
  loras_applied: { id: string; weight: number }[]
  seed: number | null
  width?: number
  height?: number
  steps?: number
  cfg?: number
}

export async function fetchIterateSystemPrompt(): Promise<{ system_prompt: string }> {
  const res = await apiFetch('/api/iterate/system_prompt')
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed to load system prompt')
  return res.json()
}

export async function fetchIterateScenes(limit = 30): Promise<{ scenes: IterateScene[] }> {
  const res = await apiFetch(`/api/iterate/scenes?limit=${limit}`)
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed to load scenes')
  return res.json()
}

export async function iterateRecraft(params: {
  replay_inputs: Record<string, any>
  system_prompt: string
  use_original_seed?: boolean
  seed?: number | null
  width?: number
  height?: number
  steps?: number
  loras?: { id: string; weight: number }[] | null
  mood_data_override?: Record<string, any> | null
  mood_name_override?: string | null
}): Promise<{
  crafted_prompt: string
  craft_elapsed: number
  image: {
    url: string
    cost: number
    seed: number | null
    elapsed: number
    settings: {
      width: number; height: number; steps: number; cfg: number
      loras: { id: string; weight: number }[]
      final_prompt: string
    }
  }
}> {
  const res = await apiFetch('/api/iterate/recraft', {
    method: 'POST',
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Recraft failed')
  }
  return res.json()
}


export async function playgroundVideo(params: {
  image_url: string
  prompt?: string
  narration?: string
  seconds?: number
  seed?: number | null
  backend?: string
  draft?: boolean
  audio?: boolean
  size?: string
  prompt_upsampling?: boolean
}): Promise<{
  video_data: string | null
  video_url: string
  job_id: string
  generation_time: number
  elapsed: number
  prompt_used: string
  simulated: boolean
}> {
  const res = await fetch(`${BASE}/api/playground/video`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Video generation failed')
  }
  return res.json()
}

export async function manualGenerate(params: {
  prompt: string
  backend?: string
  loras: { id: string; weight: number }[]
  width?: number
  height?: number
  steps?: number
  cfg?: number
  seed?: number | null
  controlnet?: {
    type: string
    guide_image: string
    weight: number
    start_step_pct: number
    end_step_pct: number
    control_mode: string
    include_hands_face: boolean
  } | null
}): Promise<{
  url: string
  cost: number
  seed: number | null
  elapsed: number
  settings: {
    width: number; height: number; steps: number; cfg: number
    loras: { id: string; weight: number }[]
    final_prompt: string
  }
}> {
  const res = await fetch(`${BASE}/api/playground/manual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Manual generation failed')
  }
  return res.json()
}

export async function playgroundTTSEnhance(params: {
  text: string
  voice?: string
  language?: string
  brief?: string
}): Promise<{ enhanced_text: string; elapsed: number }> {
  const res = await fetch(`${BASE}/api/playground/tts/enhance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'TTS enhancement failed')
  }
  return res.json()
}

export async function playgroundTTS(params: {
  text: string
  voice?: string
  language?: string
  output_format?: string
  channels?: number
  sample_rate?: number
  bitrate?: number
}): Promise<{
  audio_url: string
  audio_data: string | null
  voice: string
  language: string
  char_count: number
  cost: number
  elapsed: number
}> {
  const res = await fetch(`${BASE}/api/playground/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'TTS failed')
  }
  return res.json()
}

export async function playgroundAudioVideo(params: {
  image_url: string
  audio_url: string
  prompt?: string
  resolution?: string
  fps?: number
  draft?: boolean
  seed?: number | null
}): Promise<{
  video_url: string
  video_data: string | null
  prompt_used: string
  cost: number
  elapsed: number
  generation_time: number
}> {
  const res = await fetch(`${BASE}/api/playground/audio_video`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Audio-to-video failed')
  }
  return res.json()
}

// ─── Slice-of-life: World / Map ─────────────────────────────────────────────

export async function goToLocation(params: {
  session_id: string
  location_id: string
  advance_time?: boolean
}): Promise<import('./types').WorldPayload> {
  const res = await apiFetch('/api/game/go_to_location', {
    method: 'POST',
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'go_to_location failed')
  }
  return res.json()
}

export async function fetchWorld(sessionId: string): Promise<import('./types').WorldPayload> {
  const res = await apiFetch(`/api/game/world?session_id=${encodeURIComponent(sessionId)}`)
  if (!res.ok) throw new Error('Failed to fetch world')
  return res.json()
}
