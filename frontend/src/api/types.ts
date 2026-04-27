// ─── API Types ───────────────────────────────────────────────────────────────

export interface Actor {
  codename: string
  display_name: string
  description: string
}

export interface Setting {
  id: string
  label: string
  description: string
}

export interface PlayerProfile {
  name: string
  age: number
  gender: string
  preferences: string
}

export interface Cast {
  actors: string[]  // ordered list of actor codenames (priority of encounter)
}

// ─── SSE Event Types ─────────────────────────────────────────────────────────

export type SSEEvent =
  | { type: 'narration_delta'; content: string }
  | { type: 'image_requested'; index: number; prompt: string; actors_in_scene: string[]; location: string }
  | { type: 'image_ready'; index: number; url: string; cost: number; seed?: number; generation_time: number; settings?: ImageGenSettings }
  | { type: 'image_error'; index: number; error: string }
  | { type: 'video_requested'; prompt: string; input_image_index: number }
  | { type: 'video_ready'; url: string; cost: number; generation_time: number }
  | { type: 'video_error'; error: string }
  | { type: 'choices_available'; choices: Choice[] }
  | { type: 'sequence_complete'; sequence_number: number; costs: SequenceCosts; relationships?: Record<string, RelationshipData> }
  | { type: 'debug_context'; system_prompt_length: number; persistent_memory: string; narrative_memory: string; grok_model: string; sequence_number: number }
  | { type: 'scene_video_ready'; index: number; sequence_number: number; url: string; generation_time: number; job_id: string }
  | { type: 'scene_video_error'; index: number; error: string }
  | { type: 'scene_audio_ready'; index: number; sequence_number: number; url: string; audio_data?: string | null; voice: string; language: string; char_count: number; cost: number; generation_time: number; enhanced_text?: string | null; for_video_only?: boolean; dialogue_only?: boolean }
  | { type: 'scene_audio_error'; index: number; error: string }
  | { type: 'error'; message: string }

export interface RelationshipData {
  level: number       // 0=stranger, 1=acquaintance, 2=flirting, 3=close, 4=intimate, 5=lover
  encounters: number  // number of sequences with this character
  scenes: number      // total scenes featuring this character
  intimate_scenes: number
  last_mood: string
}

export interface Choice {
  id: string
  text: string
}

export interface GrokModel {
  id: string
  label: string
  tier: 'budget' | 'standard' | 'premium'
  description: string
  input_price: number
  output_price: number
}

export interface SequenceCosts {
  grok_input_tokens: number
  grok_output_tokens: number
  grok_cached_tokens?: number
  grok_cost: number
  image_costs: number[]
  video_cost?: number
  tts_cost?: number          // total of (xAI/Runware audio bytes) + (Grok enhance call)
  tts_audio_cost?: number    // audio bytes only
  tts_enhance_cost?: number  // Grok enhance call only
  total_sequence_cost: number
  total_session_cost: number
  elapsed_seconds: number
}

// ─── Image Generation Settings ───────────────────────────────────────────────

export interface ImageGenSettings {
  width: number
  height: number
  steps: number
  cfg: number
  seed_used?: number | null
  loras: { id: string; weight: number }[]
  style_moods: string[]
  prompt_length: number
  final_prompt?: string
}

// ─── Image Slot State ────────────────────────────────────────────────────────

export type ImageStatus = 'pending' | 'generating' | 'ready' | 'error'

export interface ImageSlot {
  index: number
  status: ImageStatus
  url?: string
  sceneVideoUrl?: string  // Davinci talking-head video for this scene
  sceneVideoSimulated?: boolean  // true when Davinci is in simulate mode (no real video)
  sceneAudioUrl?: string         // xAI TTS narration audio for this scene
  sceneAudioData?: string        // data:audio/mpeg;base64,... for instant playback
  sceneAudioForVideoOnly?: boolean  // when true, this audio lives in the video — don't play standalone
  prompt?: string
  cost?: number
  seed?: number
  generationTime?: number
  error?: string
  genSettings?: ImageGenSettings
  actors?: string[]
}

// ─── Story Sequence ──────────────────────────────────────────────────────────

export interface NarrationSegment {
  imageIndex: number
  text: string
}

export interface StorySequence {
  number: number
  narration: string
  images: ImageSlot[]
  choices: Choice[]
  costs?: SequenceCosts
}

// ─── LoRA ────────────────────────────────────────────────────────────────────

export interface LoraInfo {
  id: string
  name: string
  type: string
  trigger?: string
}

export interface ExtraLora {
  id: string
  weight: number
}
