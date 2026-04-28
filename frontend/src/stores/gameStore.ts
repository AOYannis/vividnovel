import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type {
  PlayerProfile, Cast, Choice, ImageSlot, SequenceCosts, SSEEvent,
} from '../api/types'

export interface HistorySequence {
  id: string
  sequence_number: number
  narration_segments: string[]
  choices_offered: { id: string; text: string }[]
  choice_made: { id: string; text: string } | null
  costs: any
  images: { id: string; image_index: number; url: string; prompt: string; cost: number; seed: number; generation_time: number; gen_settings: any }[]
  videos: { id: string; url: string; prompt: string; cost: number; generation_time: number }[]
}

/** A completed sequence's data, frozen for scroll-back display. */
export interface CompletedSequence {
  sequenceNumber: number
  narrationSegments: string[]
  images: ImageSlot[]
  videoUrl: string | null
  choiceMade: Choice | null
}

interface GameState {
  // ── Setup ──
  step: 'setup' | 'playing' | 'choosing' | 'history' | 'gallery' | 'admin' | 'playground'
  player: PlayerProfile | null
  setting: string | null
  cast: Cast | null
  sessionId: string | null

  // ── Current sequence ──
  sequenceNumber: number
  narrationSegments: string[]  // one per scene (0-4), filled progressively
  activeSegmentIndex: number   // which segment is currently receiving text
  images: ImageSlot[]
  choices: Choice[]
  isStreaming: boolean
  sequenceCosts: SequenceCosts | null
  relationships: Record<string, import('../api/types').RelationshipData>
  currentScene: number         // which scene the user is viewing (0-4)

  // ── Scene chat (in-scene interaction) ──
  sceneChats: Record<number, {
    messages: { role: 'user' | 'narrator'; text: string }[]
    adaptedImageUrl?: string
    adaptedImageLoading?: boolean
  }>

  // ── Phone (character messaging) ──
  phoneOpen: boolean
  phoneActiveChar: string | null  // which character's thread is open
  phoneChats: Record<string, { role: 'user' | 'character' | 'system'; text: string; imageUrl?: string; rendezvous?: import('../api/types').KnownWhereabout }[]>
  metCharacters: string[]  // character codenames the player has met
  characterNames: Record<string, string>  // codename → story name (set by Grok)

  // ── Completed sequences (for infinite scroll-back) ──
  completedSequences: CompletedSequence[]

  // ── History (previous sequences recap from DB) ──
  historySequences: HistorySequence[]

  // ── Video ──
  videoStatus: 'none' | 'generating' | 'ready' | 'error'
  videoUrl: string | null
  videoCost: number
  videoPrompt: string | null
  videoGenerationTime: number

  // ── Debug ──
  showDebug: boolean
  generatedPrompts: { index: number; prompt: string; actors: string[] }[]
  allSequenceCosts: SequenceCosts[]
  debugContext: { systemPromptLength: number; persistentMemory: string; narrativeMemory: string; grokModel: string } | null

  // ── Slice-of-life world ──
  world: import('../api/types').WorldState | null
  characterStates: Record<string, import('../api/types').CharacterState>
  knownWhereabouts: import('../api/types').KnownWhereabout[]
  presenceNow: Record<string, string[]>     // loc_id → [char_codes] for current slot
  upcomingRendezvous: import('../api/types').UpcomingRendezvous[]

  // ── Actions ──
  setPlayer: (p: PlayerProfile) => void
  setSetting: (s: string) => void
  setCast: (c: Cast) => void
  startSession: (sessionId: string) => void
  resumeSession: (sessionId: string, sequenceNumber: number, history: HistorySequence[], metCharacters?: string[], characterNames?: Record<string, string>) => void
  startStreaming: () => void
  handleSSEEvent: (event: SSEEvent) => void
  selectChoice: (choice: Choice) => void
  resetForNewSequence: () => void
  setCurrentScene: (scene: number) => void
  setWorld: (w: import('../api/types').WorldState | null) => void
  setWorldPayload: (payload: import('../api/types').WorldPayload) => void
  toggleDebug: () => void
  openGallery: (sessionId: string) => void
  openAdmin: () => void
  openPlayground: () => void
  reset: () => void
}

const createEmptyImages = (): ImageSlot[] => []

export const useGameStore = create<GameState>()(persist((set, get) => ({
  step: 'setup',
  player: null,
  setting: null,
  cast: null,
  sessionId: null,

  sequenceNumber: 0,
  narrationSegments: [],
  activeSegmentIndex: 0,
  images: createEmptyImages(),
  choices: [],
  isStreaming: false,
  sequenceCosts: null,
  relationships: {},
  currentScene: 0,
  world: null,
  characterStates: {},
  knownWhereabouts: [],
  presenceNow: {},
  upcomingRendezvous: [],

  sceneChats: {},
  phoneOpen: false,
  phoneActiveChar: null,
  phoneChats: {},
  metCharacters: [],
  characterNames: {},
  completedSequences: [],
  historySequences: [],

  videoStatus: 'none',
  videoUrl: null,
  videoCost: 0,
  videoPrompt: null,
  videoGenerationTime: 0,

  showDebug: false,
  generatedPrompts: [],
  allSequenceCosts: [],
  debugContext: null,

  setPlayer: (p) => set({ player: p }),
  setSetting: (s) => set({ setting: s }),
  setCast: (c) => set({ cast: c }),

  startSession: (sessionId) => set({
    sessionId,
    step: 'playing',
    sequenceNumber: 0,
  }),

  resumeSession: (sessionId: string, sequenceNumber: number, history: HistorySequence[] = [], metCharacters: string[] = [], characterNames: Record<string, string> = {}) => {
    // Convert DB history into CompletedSequences for infinite scroll-back
    // Also rebuild the met characters list from history (in case the server didn't send any)
    const derivedMet = new Set<string>(metCharacters)
    for (const seq of history) {
      for (const img of seq.images || []) {
        for (const actor of (img as any).actors_present || []) {
          if (actor) derivedMet.add(actor)
        }
      }
    }
    const completed: CompletedSequence[] = history.map((seq) => {
      const sortedImages = [...(seq.images || [])].sort((a, b) => a.image_index - b.image_index)
      return {
        sequenceNumber: seq.sequence_number,
        narrationSegments: seq.narration_segments || [],
        images: Array.from({ length: (seq.narration_segments || []).length || sortedImages.length || 0 }, (_, i) => {
          const dbImg = sortedImages.find((img) => img.image_index === i)
          if (dbImg?.url) {
            return {
              index: i,
              status: 'ready' as const,
              url: dbImg.url,
              prompt: dbImg.prompt,
              cost: dbImg.cost,
              seed: dbImg.seed,
              generationTime: dbImg.generation_time,
              genSettings: dbImg.gen_settings,
            }
          }
          return { index: i, status: 'pending' as const }
        }),
        videoUrl: seq.videos?.[0]?.url || null,
        choiceMade: seq.choice_made || null,
      }
    })

    // Get the last sequence's choices for the "continue" prompt
    const lastSeq = history[history.length - 1]
    const lastChoices = lastSeq?.choices_offered || []

    set({
      sessionId,
      step: 'choosing',
      sequenceNumber,
      completedSequences: completed,
      choices: lastChoices,
      historySequences: history,
      metCharacters: Array.from(derivedMet),
      characterNames: { ...characterNames },
    })
  },

  startStreaming: () => set({
    isStreaming: true,
    narrationSegments: [],
    activeSegmentIndex: 0,
    images: createEmptyImages(),
    choices: [],
    sequenceCosts: null,
    generatedPrompts: [],
    debugContext: null,
    currentScene: 0,
    sceneChats: {},
    videoStatus: 'none',
    videoUrl: null,
    videoCost: 0,
    videoPrompt: null,
  }),

  handleSSEEvent: (event) => {
    const state = get()

    switch (event.type) {
      case 'narration_delta': {
        // Append text to the current active segment (grow array if needed)
        const segments = [...state.narrationSegments]
        const idx = state.activeSegmentIndex
        while (segments.length <= idx) segments.push('')
        segments[idx] = (segments[idx] || '') + event.content
        set({ narrationSegments: segments })
        break
      }

      case 'image_requested': {
        // The narration before this tool_call belongs to this image's scene.
        // Future narration goes to the NEXT segment.
        const nextSegment = event.index + 1
        // Track met characters and story names
        const newMet = [...state.metCharacters]
        for (const actor of (event.actors_in_scene || [])) {
          if (actor && !newMet.includes(actor)) newMet.push(actor)
        }
        const newNames = { ...state.characterNames }
        const eventNames = (event as any).character_names || {}
        for (const [code, name] of Object.entries(eventNames)) {
          if (code && name) newNames[code] = name as string
        }
        // Grow images array if needed (dynamic scene count)
        let newImages = [...state.images]
        while (newImages.length <= event.index) {
          newImages.push({ index: newImages.length, status: 'pending' as const })
        }
        newImages = newImages.map((img) =>
          img.index === event.index
            ? {
                ...img,
                status: 'generating' as const,
                prompt: event.prompt,
                actors: event.actors_in_scene,
              }
            : img
        )
        set({
          activeSegmentIndex: nextSegment,
          metCharacters: newMet,
          characterNames: newNames,
          images: newImages,
          generatedPrompts: [
            ...state.generatedPrompts,
            { index: event.index, prompt: event.prompt, actors: event.actors_in_scene },
          ],
        })
        break
      }

      case 'image_ready': {
        set({
          images: state.images.map((img) =>
            img.index === event.index
              ? {
                  ...img,
                  status: 'ready' as const,
                  url: event.url,
                  cost: event.cost,
                  seed: event.seed,
                  generationTime: event.generation_time,
                  genSettings: (event as any).settings,
                }
              : img
          ),
        })
        break
      }

      case 'image_error':
        set({
          images: state.images.map((img) =>
            img.index === event.index
              ? { ...img, status: 'error' as const, error: event.error }
              : img
          ),
        })
        break

      case 'video_requested':
        set({ videoStatus: 'generating', videoPrompt: event.prompt })
        break

      case 'video_ready':
        set({ videoStatus: 'ready', videoUrl: event.url, videoCost: event.cost, videoGenerationTime: event.generation_time })
        break

      case 'video_error':
        set({ videoStatus: 'error' })
        console.error('Video error:', event.error)
        break

      case 'choices_available':
        set({ choices: event.choices, step: 'choosing' })
        break

      case 'sequence_complete':
        set({
          isStreaming: false,
          sequenceCosts: event.costs,
          sequenceNumber: event.sequence_number,
          allSequenceCosts: [...state.allSequenceCosts, event.costs],
          relationships: (event as any).relationships || state.relationships,
        })
        break

      case 'scene_video_ready': {
        // Davinci video — route to current sequence or completed sequence
        const videoSeqNum = (event as any).sequence_number ?? state.sequenceNumber
        const sceneVideoCost = Number((event as any).cost ?? 0) || 0
        const isSimulated = (event as any).simulated === true
        if (videoSeqNum === state.sequenceNumber || videoSeqNum === state.sequenceNumber - 1) {
          // Might belong to current sequence images (if not yet archived)
          const currentHasScene = state.images.some((img) => img.index === event.index && img.status === 'ready')
          if (currentHasScene) {
            // Top-up the live sequenceCosts.video_cost in case the per-scene video
            // arrived AFTER sequence_complete fired (P-Video typically takes 20-60s
            // and the choice screen ships earlier with a partial estimate).
            const liveCosts = state.sequenceCosts
              ? { ...state.sequenceCosts, video_cost: (state.sequenceCosts.video_cost ?? 0) + sceneVideoCost, total_sequence_cost: (state.sequenceCosts.total_sequence_cost ?? 0) + sceneVideoCost }
              : state.sequenceCosts
            set({
              images: state.images.map((img) =>
                img.index === event.index
                  ? { ...img, sceneVideoUrl: isSimulated ? undefined : event.url, sceneVideoSimulated: isSimulated }
                  : img
              ),
              sequenceCosts: liveCosts,
            })
            break
          }
        }
        // Check completed sequences — find the right one by sequence number
        const completed = [...state.completedSequences]
        for (const seq of completed) {
          if (seq.sequenceNumber === videoSeqNum) {
            seq.images = seq.images.map((img) =>
              img.index === event.index
                ? { ...img, sceneVideoUrl: isSimulated ? undefined : event.url, sceneVideoSimulated: isSimulated }
                : img
            )
            // Top up costs on the archived sequence too
            if (seq.costs && sceneVideoCost > 0) {
              seq.costs = {
                ...seq.costs,
                video_cost: (seq.costs.video_cost ?? 0) + sceneVideoCost,
                total_sequence_cost: (seq.costs.total_sequence_cost ?? 0) + sceneVideoCost,
              }
            }
            set({ completedSequences: completed })
            break
          }
        }
        break
      }

      case 'scene_video_error':
        console.error(`Scene ${event.index} video error:`, event.error)
        break

      case 'scene_audio_ready': {
        // Attach the audio to whichever image entry matches `index` REGARDLESS of status.
        // TTS now sometimes finishes before image gen (especially on the direct-xAI fast
        // path) so the previous "must be 'ready'" gate would silently drop the audio and
        // the user would hear nothing on that scene. We also grow the images array if
        // image_requested hasn't arrived yet — the audio sits on a pending entry until
        // the image catches up.
        const audioSeqNum = (event as any).sequence_number ?? state.sequenceNumber
        const audioPatch = {
          sceneAudioUrl: event.url,
          sceneAudioData: event.audio_data || undefined,
          sceneAudioForVideoOnly: !!event.for_video_only,
        }
        if (audioSeqNum === state.sequenceNumber || audioSeqNum === state.sequenceNumber - 1) {
          let newImages = [...state.images]
          while (newImages.length <= event.index) {
            newImages.push({ index: newImages.length, status: 'pending' as const })
          }
          newImages = newImages.map((img) =>
            img.index === event.index ? { ...img, ...audioPatch } : img,
          )
          set({ images: newImages })
          break
        }
        const completedAudio = [...state.completedSequences]
        for (const seq of completedAudio) {
          if (seq.sequenceNumber === audioSeqNum) {
            seq.images = seq.images.map((img) =>
              img.index === event.index ? { ...img, ...audioPatch } : img,
            )
            set({ completedSequences: completedAudio })
            break
          }
        }
        break
      }

      case 'scene_audio_error':
        console.error(`Scene ${event.index} audio error:`, event.error)
        break

      case 'debug_context':
        set({
          debugContext: {
            systemPromptLength: event.system_prompt_length,
            persistentMemory: event.persistent_memory || '',
            narrativeMemory: event.narrative_memory || '',
            grokModel: event.grok_model,
          },
        })
        break

      case 'error':
        set({ isStreaming: false })
        console.error('Story error:', event.message)
        break
    }
  },

  selectChoice: (choice) => {
    const state = get()
    // Archive the current sequence before starting the next one
    const archived: CompletedSequence = {
      sequenceNumber: state.sequenceNumber,
      narrationSegments: [...state.narrationSegments],
      images: state.images.map((img) => ({ ...img })),
      videoUrl: state.videoUrl,
      choiceMade: choice,
    }
    set({
      step: 'playing',
      completedSequences: [...state.completedSequences, archived],
    })
  },

  resetForNewSequence: () => set({
    narrationSegments: [],
    activeSegmentIndex: 0,
    images: createEmptyImages(),
    choices: [],
    sequenceCosts: null,
    generatedPrompts: [],
    currentScene: 0,
    step: 'playing',
    videoStatus: 'none',
    videoUrl: null,
    videoCost: 0,
    videoPrompt: null,
  }),

  setCurrentScene: (scene) => set({ currentScene: scene }),
  setWorld: (w) => set({ world: w }),
  setWorldPayload: (payload) => set((state) => ({
    world: payload.world,
    characterStates: payload.character_states || {},
    knownWhereabouts: payload.known_whereabouts || [],
    presenceNow: payload.presence_now || {},
    upcomingRendezvous: payload.upcoming_rendezvous || [],
    // The world payload now also carries relationships (trust, history, etc.).
    // Merge so we don't clobber state when the field is absent.
    relationships: payload.relationships ?? state.relationships,
  })),

  toggleDebug: () => set({ showDebug: !get().showDebug }),

  openGallery: (sessionId) => set({ step: 'gallery', sessionId }),
  openAdmin: () => set({ step: 'admin' }),
  openPlayground: () => set({ step: 'playground' }),

  reset: () => set({
    step: 'setup',
    player: null,
    setting: null,
    cast: null,
    sessionId: null,
    sequenceNumber: 0,
    narrationSegments: [],
    activeSegmentIndex: 0,
    images: createEmptyImages(),
    choices: [],
    isStreaming: false,
    sequenceCosts: null,
    currentScene: 0,
    world: null,
    characterStates: {},
    knownWhereabouts: [],
    presenceNow: {},
    upcomingRendezvous: [],
    sceneChats: {},
    phoneOpen: false,
    phoneActiveChar: null,
    phoneChats: {},
    metCharacters: [],
    characterNames: {},
    completedSequences: [],
    historySequences: [],
    showDebug: false,
    generatedPrompts: [],
    allSequenceCosts: [],
    debugContext: null,
  }),
}),
{
  name: 'graphbun-game',
  partialize: (state) => ({
    // Persist only what's needed to restore the game state on reload
    step: state.step,
    sessionId: state.sessionId,
    player: state.player,
    setting: state.setting,
    cast: state.cast,
    sequenceNumber: state.sequenceNumber,
    narrationSegments: state.narrationSegments,
    // Strip large data URLs (base64 videos/images) to stay within localStorage quota
    images: state.images.map(({ sceneVideoUrl, sceneAudioData, sceneAudioForVideoOnly, ...img }) => img),
    choices: state.choices,
    currentScene: state.currentScene,
    completedSequences: state.completedSequences.map(({ videoUrl, ...seq }) => ({
      ...seq,
      images: seq.images.map(({ sceneVideoUrl, sceneAudioData, sceneAudioForVideoOnly, ...img }) => img),
    })),
    sceneChats: Object.fromEntries(
      Object.entries(state.sceneChats).map(([k, v]) => [k, { ...v, adaptedImageUrl: undefined }])
    ),
    phoneChats: state.phoneChats,
    metCharacters: state.metCharacters,
    characterNames: state.characterNames,
    videoStatus: state.videoStatus,
    videoUrl: state.videoUrl,
    videoCost: state.videoCost,
    videoPrompt: state.videoPrompt,
    sequenceCosts: state.sequenceCosts,
    allSequenceCosts: state.allSequenceCosts,
    generatedPrompts: state.generatedPrompts,
    // NOT persisted: isStreaming, activeSegmentIndex, showDebug, debugContext,
    // historySequences, videoGenerationTime
  }),
  onRehydrate: () => {
    return (state) => {
      if (!state) return
      // If we were streaming when the page was closed, we're no longer streaming
      state.isStreaming = false
      // If step was 'playing' and we have content, switch to 'choosing'
      // so the user can see what they had and continue
      if (state.step === 'playing' && state.sessionId) {
        const hasContent = state.images.some((img: ImageSlot) => img.status === 'ready')
        if (hasContent) {
          state.step = 'choosing'
        }
      }
    }
  },
},
))
