import { useState, useRef, useMemo, useCallback, useEffect } from 'react'
import { useT } from '../../i18n'
import { useGameStore } from '../../stores/gameStore'
import { streamSceneChat, regenSceneVideo } from '../../api/client'
import type { ImageSlot } from '../../api/types'

interface SceneCardProps {
  index: number
  narration: string
  image: ImageSlot
  isStreaming: boolean
  isActive: boolean
  /** Whether this scene is currently visible/viewed (from IntersectionObserver) */
  isViewing: boolean
  totalScenes: number
  onSceneRef: (index: number, el: HTMLDivElement | null) => void
  onRegenImage?: (index: number) => void
  regenLoading?: boolean
  /** Enable scene chat (disabled for completed/archived scenes) */
  chatEnabled?: boolean
}

/** Map known LoRA IDs to short display names */
const LORA_NAMES: Record<string, string> = {
  'warmline:202603170002@1': 'Nataly',
  'warmline:202603200001@1': 'Shorty Asian',
  'warmline:202603200002@1': 'Blonde Cacu',
  'warmline:202603290001@1': 'Korean',
  'warmline:202603290002@1': 'Woman041',
  'warmline:202603290003@1': 'White Short',
  'warmline:202603240002@1': 'Mystic XXX',
  'warmline:2279079@2637792': 'ZIT NSFW v2',
  'warmline:202603220003@1': 'Blow (bjz)',
  'warmline:202603220002@1': 'Dog (dgz)',
  'warmline:202603290004@1': 'Titjob',
  'warmline:202603290005@1': 'POV HJ',
  'warmline:202603230003@1': 'ShemPen',
}

function loraShortName(id: string): string {
  return LORA_NAMES[id] || id.replace('warmline:', '').replace('@1', '')
}

// Global audio unlock — once the user interacts with any scene, all scenes can auto-play with sound.
// Browser autoplay policies require a user gesture (click/tap/keydown) on this DOCUMENT before
// programmatic audio.play() will succeed. We listen for the first such gesture page-wide so we
// don't depend on the user happening to tap the video element specifically.
let _audioUnlocked = false
const _audioListeners = new Set<() => void>()
function globalUnlockAudio() {
  if (_audioUnlocked) return
  _audioUnlocked = true
  _audioListeners.forEach((fn) => fn())
}

if (typeof window !== 'undefined') {
  const onFirstGesture = () => {
    globalUnlockAudio()
    window.removeEventListener('pointerdown', onFirstGesture, true)
    window.removeEventListener('touchstart', onFirstGesture, true)
    window.removeEventListener('keydown', onFirstGesture, true)
  }
  window.addEventListener('pointerdown', onFirstGesture, true)
  window.addEventListener('touchstart', onFirstGesture, { capture: true, passive: true })
  window.addEventListener('keydown', onFirstGesture, true)
}

const LINES_PER_PAGE = 3

/** Clean agent meta-text that leaks into narration */
function cleanNarration(text: string): string {
  if (!text) return ''
  let cleaned = text
  // Remove function call references
  cleaned = cleaned.replace(/generate_scene_image\s*\(.*?\)/gi, '')
  cleaned = cleaned.replace(/generate_scene_video\s*\(.*?\)/gi, '')
  cleaned = cleaned.replace(/provide_choices\s*\(.*?\)/gi, '')
  cleaned = cleaned.replace(/image_index\s*=\s*\d+/gi, '')
  // Remove meta-acknowledgements (full line)
  cleaned = cleaned.replace(/^(compris|d'accord|entendu|ok|understood|sure|certainly)[,.]?\s*(je |i |let me |voici ).*$/gim, '')
  cleaned = cleaned.replace(/^(je continue|i'?ll continue|continuing|let me continue).*$/gim, '')
  // Clean whitespace
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n').replace(/ {2,}/g, ' ').trim()
  return cleaned
}

/** Split narration into pages of ~LINES_PER_PAGE sentences each. */
function paginateText(text: string): string[] {
  const trimmed = (text || '').trim()
  if (!trimmed) return []
  // Split on sentence boundaries — keep delimiters
  const parts = trimmed.split(/(?<=[.!?»])\s+/).filter(Boolean)
  const pages: string[] = []
  let current = ''
  let lineCount = 0

  for (const s of parts) {
    const sentenceLines = Math.ceil(s.length / 45)
    if (lineCount + sentenceLines > LINES_PER_PAGE && current) {
      pages.push(current.trim())
      current = s
      lineCount = sentenceLines
    } else {
      current = current ? `${current} ${s}` : s
      lineCount += sentenceLines
    }
  }
  if (current.trim()) pages.push(current.trim())
  // Dedupe consecutive identical pages (defensive)
  const deduped: string[] = []
  for (const p of pages) {
    if (p && p !== deduped[deduped.length - 1]) deduped.push(p)
  }
  return deduped.length ? deduped : [trimmed]
}

interface DialogueBubble {
  text: string
  isPlayer: boolean // stage direction about the player vs character speaking
}

/** Extract dialogue lines from narration text. Returns bubbles + remaining stage direction. */
function extractDialogue(narration: string): { bubbles: DialogueBubble[]; stageDirection: string } {
  if (!narration) return { bubbles: [], stageDirection: '' }

  const bubbles: DialogueBubble[] = []
  // Match dialogue in «...», "...", "..." or '...'
  let remaining = narration
  const dialogueRegex = /[«""\u201C]([^»""\u201D]+)[»""\u201D]/g
  let match: RegExpExecArray | null

  while ((match = dialogueRegex.exec(narration)) !== null) {
    bubbles.push({ text: match[1].trim(), isPlayer: false })
  }

  // Stage direction = narration without the dialogue quotes
  remaining = narration
    .replace(/[«""\u201C][^»""\u201D]+[»""\u201D]/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim()

  return { bubbles, stageDirection: remaining }
}

export default function SceneCard({
  index,
  narration,
  image,
  isStreaming,
  isActive,
  onSceneRef,
  onRegenImage,
  regenLoading = false,
  chatEnabled = false,
  totalScenes,
  isViewing,
}: SceneCardProps) {
  const t = useT()
  const { sessionId, sceneChats, generatedPrompts } = useGameStore()
  const [imageLoaded, setImageLoaded] = useState(false)
  const [showText, setShowText] = useState(true)
  const [showNarration, setShowNarration] = useState(true)
  const [currentPage, setCurrentPage] = useState(0)
  const [showControls, setShowControls] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [videoMuted, setVideoMuted] = useState(true)
  const [audioReady, setAudioReady] = useState(_audioUnlocked)
  const [videoRegenLoading, setVideoRegenLoading] = useState(false)
  const [showVideoPrompt, setShowVideoPrompt] = useState(false)
  const [videoPromptEdit, setVideoPromptEdit] = useState('')
  const [videoWaitSeconds, setVideoWaitSeconds] = useState(0)
  const videoWaitRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Timer: count up while image is ready but video hasn't arrived
  useEffect(() => {
    if (image.status === 'ready' && image.url && !image.sceneVideoUrl && !image.sceneVideoSimulated) {
      // Start counting
      setVideoWaitSeconds(0)
      videoWaitRef.current = setInterval(() => setVideoWaitSeconds((s) => s + 1), 1000)
      return () => { if (videoWaitRef.current) clearInterval(videoWaitRef.current) }
    } else {
      // Video arrived or image not ready — stop
      if (videoWaitRef.current) clearInterval(videoWaitRef.current)
      videoWaitRef.current = null
      setVideoWaitSeconds(0)
    }
  }, [image.status, image.url, image.sceneVideoUrl, image.sceneVideoSimulated])
  const sceneVideoRef = useRef<HTMLVideoElement>(null)
  const sceneAudioRef = useRef<HTMLAudioElement>(null)
  const soundPlayCount = useRef(0) // how many loops have played with sound

  // ── Standalone TTS narration audio ──
  // Skip standalone playback when:
  // - the audio was generated only for the video lip-sync (dialogue-only TTS, voice_to_video=true)
  // - or the video has already arrived (its soundtrack covers the scene)
  const sceneAudioSrc = image.sceneAudioData || image.sceneAudioUrl
  const playStandaloneAudio = !!sceneAudioSrc && !image.sceneVideoUrl && !image.sceneAudioForVideoOnly
  const audioStartedRef = useRef(false)
  useEffect(() => {
    const a = sceneAudioRef.current
    if (!a || !playStandaloneAudio) return
    if (!isViewing) {
      a.pause()
      return
    }
    a.muted = false
    // Only reset on the FIRST play of this clip. If the user scrolled away mid-clip
    // and came back, resume from where they left off (no restart from zero).
    if (!audioStartedRef.current) {
      a.currentTime = 0
      audioStartedRef.current = true
    }
    // Try to play unconditionally — the user may have already gestured on the
    // page (e.g. clicking "Start Game") even if we haven't seen our own gesture
    // event yet. If autoplay policy blocks it, we'll get an error, fall back to
    // muted, and try again once the global gesture listener fires.
    a.play()
      .then(() => globalUnlockAudio())
      .catch(() => {
        a.muted = true
        a.play().catch(() => {})
      })
  }, [isViewing, audioReady, playStandaloneAudio])

  // Subscribe to global audio unlock
  useEffect(() => {
    if (_audioUnlocked) { setAudioReady(true); return }
    const handler = () => setAudioReady(true)
    _audioListeners.add(handler)
    return () => { _audioListeners.delete(handler) }
  }, [])
  const touchStartX = useRef(0)
  const touchStartY = useRef(0)

  // Scene chat data
  const sceneChat = sceneChats[index]
  const chatMessages = sceneChat?.messages || []
  const adaptedImageUrl = sceneChat?.adaptedImageUrl
  const adaptedImageLoading = sceneChat?.adaptedImageLoading || false

  const isTyping = isStreaming && isActive

  // ── Video playback management ──
  // - Videos play muted by default (autoPlay + onLoadedData fallback)
  // - Tap to unmute (user gesture required on mobile)
  // - Scroll away → mute
  // - After first tap unlocks audio globally, subsequent scenes auto-play with sound

  // When user scrolls away → mute. When scrolling TO a scene after audio unlock → unmute.
  // On mobile, the unmute-from-effect only works AFTER a user gesture has unlocked audio
  // on the same video element. We use play() to re-engage after unmuting.
  useEffect(() => {
    const v = sceneVideoRef.current
    if (!v || !image.sceneVideoUrl) return

    if (!isViewing) {
      // Scrolled away → mute (always works)
      v.muted = true
      setVideoMuted(true)
    } else if (isViewing && audioReady) {
      // Scrolled TO this scene and audio was previously unlocked
      soundPlayCount.current = 0
      v.muted = false
      v.currentTime = 0
      setVideoMuted(false)
      // play() needed in case the video was paused or stalled
      v.play().catch(() => {
        // If unmuted play fails (mobile first-gesture restriction), fall back to muted
        v.muted = true
        setVideoMuted(true)
        v.play().catch(() => {})
      })
    }
  }, [isViewing, audioReady, image.sceneVideoUrl])

  // After one full loop with sound, mute and keep looping silently
  useEffect(() => {
    const v = sceneVideoRef.current
    if (!v) return
    const onTimeUpdate = () => {
      if (!v.muted && v.currentTime < 0.3 && soundPlayCount.current > 0) {
        v.muted = true
        setVideoMuted(true)
      }
      if (!v.muted && v.currentTime > 0.5) {
        soundPlayCount.current = 1
      }
    }
    v.addEventListener('timeupdate', onTimeUpdate)
    return () => v.removeEventListener('timeupdate', onTimeUpdate)
  }, [image.sceneVideoUrl])

  // Clean narration of any leaked system/meta text
  const cleanedNarration = useMemo(() => cleanNarration(narration), [narration])

  // Extract dialogue bubbles from the original scene narration
  const baseDialogue = useMemo(() => extractDialogue(cleanedNarration), [cleanedNarration])

  // When viewing a chat narrator response, extract dialogue from THAT text instead
  const currentChatMessage = sceneChats[index]?.messages
  const lastNarratorMsg = currentChatMessage ? [...currentChatMessage].reverse().find((m) => m.role === 'narrator') : undefined
  const chatDialogue = useMemo(
    () => lastNarratorMsg ? extractDialogue(cleanNarration(lastNarratorMsg.text)) : null,
    [lastNarratorMsg],
  )

  // Show chat dialogue when viewing a chat page (currentPage past narration pages), else original
  // Note: narrationPages count depends on dialogueBubbles, so we use a simpler heuristic
  const viewingChat = currentChatMessage && currentChatMessage.length > 0
  const dialogueBubbles = viewingChat && chatDialogue ? chatDialogue.bubbles : baseDialogue.bubbles
  const stageDirection = viewingChat && chatDialogue ? chatDialogue.stageDirection : baseDialogue.stageDirection

  // Build pages: narration pages + chat messages + chat input placeholder
  // When dialogue bubbles exist, paginate ONLY the stage direction (the dialogue is shown separately as bubbles).
  // Otherwise paginate the full narration.
  const narrationPages = useMemo(() => {
    const sourceText = dialogueBubbles.length > 0 ? stageDirection : cleanedNarration
    return paginateText(sourceText)
  }, [cleanedNarration, dialogueBubbles.length, stageDirection])
  const chatPages: string[] = useMemo(() => {
    return chatMessages.map((m) =>
      m.role === 'user' ? `> ${m.text}` : m.text
    )
  }, [chatMessages])

  // All pages: narration + chat responses + (chat input page if enabled and not streaming)
  // Chat available as soon as this scene has narration + image (don't wait for full sequence)
  const hasChatInput = chatEnabled && !isTyping && narrationPages.length > 0 && (image.status === 'ready' || image.status === 'generating')
  const allPages = [...narrationPages, ...chatPages]
  const chatInputPageIndex = allPages.length  // The index where chat input would appear
  const totalPages = allPages.length + (hasChatInput ? 1 : 0)

  // When narration pages change (new text arrives), reset to page 0
  const prevPagesLen = useRef(0)
  if (narrationPages.length !== prevPagesLen.current) {
    prevPagesLen.current = narrationPages.length
    if (!isTyping && currentPage >= narrationPages.length) {
      setCurrentPage(0)
    }
  }

  const isOnChatInputPage = currentPage === chatInputPageIndex && hasChatInput
  const pageText = isOnChatInputPage ? '' : (allPages[Math.min(currentPage, allPages.length - 1)] || '')
  const isUserMessage = !isOnChatInputPage && currentPage >= narrationPages.length && chatMessages[currentPage - narrationPages.length]?.role === 'user'

  // Horizontal swipe on narration area to page through text.
  // The narration zone uses touch-none to fully capture touch events
  // and prevent the parent vertical scroll from hijacking the gesture.
  const onNarrationTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
  }, [])

  const onNarrationTouchEnd = useCallback((e: React.TouchEvent) => {
    const dx = touchStartX.current - e.changedTouches[0].clientX
    const dy = Math.abs(touchStartY.current - e.changedTouches[0].clientY)
    if (Math.abs(dx) > 30) {
      // Horizontal swipe — page through text
      e.preventDefault()
      e.stopPropagation()
      if (dx > 0 && currentPage < totalPages - 1) setCurrentPage(currentPage + 1)
      if (dx < 0 && currentPage > 0) setCurrentPage(currentPage - 1)
    }
    // If mostly vertical (dy > dx), do nothing — the parent scroll handles it
  }, [currentPage, totalPages])

  // Keyboard: ArrowLeft/ArrowRight to page through text (only when this card is active)
  useEffect(() => {
    if (!isActive || totalPages <= 1 || isTyping) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' && currentPage < totalPages - 1) {
        e.preventDefault()
        e.stopPropagation()
        setCurrentPage(currentPage + 1)
      } else if (e.key === 'ArrowLeft' && currentPage > 0) {
        e.preventDefault()
        e.stopPropagation()
        setCurrentPage(currentPage - 1)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isActive, currentPage, totalPages, isTyping])

  // ── Scene chat handler ──
  const handleChatSend = useCallback(async () => {
    if (!chatInput.trim() || !sessionId || chatLoading) return
    const msg = chatInput.trim()
    setChatInput('')
    setChatLoading(true)

    const store = useGameStore.getState()
    const promptData = generatedPrompts.find((p) => p.index === index)

    // Add user message to store
    const prevChat = store.sceneChats[index] || { messages: [] }
    useGameStore.setState({
      sceneChats: {
        ...store.sceneChats,
        [index]: { ...prevChat, messages: [...prevChat.messages, { role: 'user' as const, text: msg }] },
      },
    })

    let responseText = ''
    try {
      await streamSceneChat(
        {
          sessionId,
          sceneIndex: index,
          message: msg,
          currentNarration: narration,
          imagePrompt: promptData?.prompt || image.genSettings?.final_prompt || '',
          imageSeed: image.seed,
          actorsPresent: promptData?.actors || [],
          styleMoods: image.genSettings?.style_moods || ['neutral'],
          locationDescription: '',
          clothingState: undefined,
        },
        // onNarration
        (text) => { responseText += text },
        // onNarrationDone
        (fullText) => {
          responseText = fullText
          const s = useGameStore.getState()
          const chat = s.sceneChats[index] || { messages: [] }
          useGameStore.setState({
            sceneChats: {
              ...s.sceneChats,
              [index]: { ...chat, messages: [...chat.messages, { role: 'narrator' as const, text: fullText }] },
            },
          })
          // Move to the narrator response page
          setCurrentPage(narrationPages.length + chat.messages.length)
        },
        // onImageGenerating
        () => {
          const s = useGameStore.getState()
          const chat = s.sceneChats[index] || { messages: [] }
          useGameStore.setState({
            sceneChats: { ...s.sceneChats, [index]: { ...chat, adaptedImageLoading: true } },
          })
        },
        // onImageReady
        (url) => {
          const s = useGameStore.getState()
          const chat = s.sceneChats[index] || { messages: [] }
          useGameStore.setState({
            sceneChats: { ...s.sceneChats, [index]: { ...chat, adaptedImageUrl: url, adaptedImageLoading: false } },
          })
        },
        // onError
        (error) => { console.error('Scene chat error:', error) },
      )
    } catch (e) {
      console.error('Scene chat failed:', e)
    } finally {
      setChatLoading(false)
    }
  }, [chatInput, sessionId, chatLoading, index, narration, image, generatedPrompts, narrationPages.length])

  const handleVideoRegen = useCallback(async (draft: boolean) => {
    if (!sessionId || !image.url || videoRegenLoading) return
    setVideoRegenLoading(true)
    try {
      const result = await regenSceneVideo({
        session_id: sessionId,
        scene_index: index,
        image_url: image.url,
        prompt: videoPromptEdit || narration || undefined,
        draft,
      })
      // Update the image slot with new video URL
      const store = useGameStore.getState()
      store.handleSSEEvent({
        type: 'scene_video_ready',
        index,
        sequence_number: store.sequenceNumber,
        url: result.video_url,
        generation_time: result.elapsed,
        job_id: 'regen',
        simulated: false,
      } as any)
    } catch (e) {
      console.error('Video regen failed:', e)
    } finally {
      setVideoRegenLoading(false)
    }
  }, [sessionId, index, image.url, videoRegenLoading, videoPromptEdit, narration])

  const handleTapImage = useCallback((e: React.MouseEvent) => {
    // Don't toggle if tapping a button
    if ((e.target as HTMLElement).closest('button')) return

    const v = sceneVideoRef.current
    // If video is present and muted → unmute and play (user gesture, works on mobile)
    if (v && image.sceneVideoUrl && videoMuted) {
      globalUnlockAudio()
      soundPlayCount.current = 0
      v.muted = false
      v.currentTime = 0
      setVideoMuted(false)
      v.play().catch(() => {})
      return // don't toggle text on this tap
    }

    // Tap cycles: text visible → text + controls → everything hidden
    if (!showText) {
      setShowText(true)
      setShowControls(false)
    } else if (!showControls) {
      setShowControls(true)
    } else {
      setShowText(false)
      setShowControls(false)
    }
  }, [videoMuted, image.sceneVideoUrl])

  return (
    <div
      ref={(el) => onSceneRef(index, el)}
      data-scene-index={index}
      className="h-[100dvh] snap-start snap-always relative shrink-0 overflow-hidden"
      onClick={handleTapImage}
    >
      {/* ── Background layer: image → video crossfade → chat adapted image ── */}
      {image.status === 'ready' && image.url ? (
        <>
          {!imageLoaded && <div className="absolute inset-0 shimmer" />}
          {/* Blurred backdrop (desktop only) — same image stretched + blurred to fill the viewport */}
          <img
            src={image.url}
            alt=""
            aria-hidden
            className={`hidden md:block absolute inset-0 w-full h-full object-cover transition-opacity duration-700 scale-110 blur-2xl brightness-50 ${
              imageLoaded ? 'opacity-100' : 'opacity-0'
            }`}
          />
          {/* Original image — cover on mobile (immersive), contain on desktop (preserve ratio) */}
          <img
            src={image.url}
            alt=""
            className={`absolute inset-0 w-full h-full object-cover md:object-contain transition-opacity duration-700 ${
              imageLoaded ? 'opacity-100' : 'opacity-0'
            }`}
            onLoad={() => setImageLoaded(true)}
          />
          {/* Davinci talking-head video — fades in over image when ready */}
          {image.sceneVideoUrl && currentPage < narrationPages.length && (
            <>
              <video
                ref={sceneVideoRef}
                src={image.sceneVideoUrl}
                autoPlay
                loop
                muted
                playsInline
                onLoadedData={(e) => {
                  const vid = e.target as HTMLVideoElement
                  vid.play().catch(() => {})
                }}
                className="absolute inset-0 z-[1] w-full h-full object-cover md:object-contain transition-opacity duration-700 opacity-100"
              />
              {/* Sound indicator — tap anywhere to unmute/mute */}
              <div className="absolute top-14 right-3 z-[5] bg-black/50 backdrop-blur-sm rounded-full w-8 h-8 flex items-center justify-center pointer-events-none">
                {videoMuted ? (
                  <svg className="w-4 h-4 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-3.72a.75.75 0 011.28.53v14.88a.75.75 0 01-1.28.53L6.75 14.25H3.75a.75.75 0 01-.75-.75v-3a.75.75 0 01.75-.75h3z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4 text-white/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-3.72a.75.75 0 011.28.53v14.88a.75.75 0 01-1.28.53L6.75 15.75H3.75a.75.75 0 01-.75-.75v-6a.75.75 0 01.75-.75h3z" />
                  </svg>
                )}
              </div>
            </>
          )}
          {/* Simulated video badge — shows when Davinci is in simulate mode */}
          {image.sceneVideoSimulated && (
            <div className="absolute top-14 left-3 z-[5] bg-purple-600/70 backdrop-blur-sm rounded-full px-2.5 py-1 flex items-center gap-1.5 pointer-events-none">
              <div className="w-2 h-2 rounded-full bg-purple-300 animate-pulse" />
              <span className="text-[10px] text-white/90 font-mono">VIDEO SIM</span>
            </div>
          )}
          {/* Video generation timer — subtle indicator while waiting */}
          {videoWaitSeconds > 2 && !image.sceneVideoUrl && !image.sceneVideoSimulated && (
            <div className="absolute top-14 left-3 z-[5] bg-black/40 backdrop-blur-sm rounded-full px-2.5 py-1 flex items-center gap-1.5 pointer-events-none">
              <div className="w-2 h-2 rounded-full bg-cyan-400/70 animate-pulse" />
              <span className="text-[10px] text-white/50 font-mono">{videoWaitSeconds}s</span>
            </div>
          )}
          {/* TTS narration audio (hidden player — only plays when no video yet) */}
          {playStandaloneAudio && (
            <>
              <audio
                ref={sceneAudioRef}
                src={sceneAudioSrc}
                preload="auto"
                className="hidden"
              />
              {isViewing && (
                <div className="absolute top-3 right-3 z-[5] bg-amber-600/70 backdrop-blur-sm rounded-full px-2.5 py-1 flex items-center gap-1.5 pointer-events-none">
                  <div className="w-2 h-2 rounded-full bg-amber-200 animate-pulse" />
                  <span className="text-[10px] text-white/90 font-mono">VOICE</span>
                </div>
              )}
            </>
          )}
          {/* Adapted image (from chat) — overlays when viewing chat pages */}
          {adaptedImageUrl && (
            <img
              src={adaptedImageUrl}
              alt=""
              className={`absolute inset-0 z-[2] w-full h-full object-cover md:object-contain transition-opacity duration-500 ${
                currentPage >= narrationPages.length ? 'opacity-100' : 'opacity-0'
              }`}
            />
          )}
          {/* Loading shimmer for adapted image */}
          {adaptedImageLoading && currentPage >= narrationPages.length && (
            <div className="absolute inset-0 z-[3] shimmer opacity-50" />
          )}
        </>
      ) : image.status === 'generating' ? (
        <div className="absolute inset-0 shimmer" />
      ) : image.status === 'error' ? (
        <div className="absolute inset-0 bg-red-950/20 flex items-center justify-center">
          <span className="text-red-400 text-sm px-6 text-center">{image.error || 'Image generation failed'}</span>
        </div>
      ) : (
        <div className="absolute inset-0 bg-neutral-950" />
      )}

      {/* ── Dialogue bubbles — floating at top of frame ── */}
      {showText && !isTyping && dialogueBubbles.length > 0 && currentPage < narrationPages.length && (
        <div className="absolute top-12 left-0 right-0 z-[8] px-4 sm:px-6 flex flex-col gap-2 pointer-events-none">
          {dialogueBubbles.map((bubble, i) => (
            <div
              key={i}
              className={`max-w-[75%] px-4 py-2.5 rounded-2xl backdrop-blur-md shadow-lg ${
                i % 2 === 0
                  ? 'bg-white/90 text-neutral-900 rounded-br-sm self-end'
                  : 'bg-indigo-500/90 text-white rounded-bl-sm self-start'
              }`}
            >
              <p className="text-[14px] md:text-[15px] leading-snug font-medium italic">
                &laquo; {bubble.text} &raquo;
              </p>
            </div>
          ))}
        </div>
      )}

      {/* ── Bottom overlay: narration + controls ── */}
      <div
        className={`absolute bottom-0 left-0 right-0 z-10 transition-all duration-300 ${
          showText ? 'translate-y-0 opacity-100' : 'translate-y-[calc(100%-2rem)] opacity-40'
        }`}
      >
        <div className="bg-gradient-to-t from-black/90 via-black/60 to-transparent pt-16 pb-6 px-5 sm:px-8 max-h-[60vh] overflow-y-auto no-scrollbar">
          {/* Scene indicator + narration toggle */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] text-white/30 font-mono tracking-wider">
              {index + 1} / {totalScenes}
            </span>
            {/* Narration toggle */}
            {showText && narration && !isTyping && dialogueBubbles.length > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); setShowNarration(!showNarration) }}
                className="text-[9px] text-white/30 hover:text-white/60 transition-colors ml-2 px-1.5 py-0.5 rounded bg-white/5"
              >
                {showNarration ? 'hide narration' : 'show narration'}
              </button>
            )}
            {/* Page dots — only if multiple pages */}
            {totalPages > 1 && showText && showNarration && (
              <div className="flex items-center gap-1 ml-2">
                {Array.from({ length: totalPages }, (_, i) => (
                  <button
                    key={i}
                    onClick={(e) => { e.stopPropagation(); setCurrentPage(i) }}
                    className={`rounded-full transition-all ${
                      i === currentPage
                        ? 'w-4 h-1.5 bg-white/70'
                        : 'w-1.5 h-1.5 bg-white/25'
                    }`}
                  />
                ))}
                <span className="text-[9px] text-white/20 ml-1 font-mono">{currentPage + 1}/{totalPages}</span>
              </div>
            )}
            <div className="flex-1" />
            {!showText && (
              <span className="text-[9px] text-white/30">{t('game.tap_to_show')}</span>
            )}
          </div>

          {/* Narration text — shown when expanded or when no dialogue bubbles */}
          {showText && narration ? (
            <div
              onTouchStart={onNarrationTouchStart}
              onTouchEnd={onNarrationTouchEnd}
              className="touch-none select-none relative"
            >
              {/* Show narration when: typing, no dialogue bubbles, narration toggle on, or viewing a chat page */}
              {(isTyping || dialogueBubbles.length === 0 || showNarration || currentPage >= narrationPages.length) ? (
                <>
                  {/* Desktop prev/next arrows */}
                  {totalPages > 1 && !isTyping && (
                    <>
                      {currentPage > 0 && (
                        <button
                          onClick={(e) => { e.stopPropagation(); setCurrentPage(currentPage - 1) }}
                          className="hidden md:flex absolute -left-8 top-1/2 -translate-y-1/2 w-6 h-6 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 text-white/50 hover:text-white transition-colors"
                        >
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                          </svg>
                        </button>
                      )}
                      {currentPage < totalPages - 1 && (
                        <button
                          onClick={(e) => { e.stopPropagation(); setCurrentPage(currentPage + 1) }}
                          className="hidden md:flex absolute -right-8 top-1/2 -translate-y-1/2 w-6 h-6 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 text-white/50 hover:text-white transition-colors"
                        >
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                      )}
                    </>
                  )}
                  {!isOnChatInputPage ? (
                    <>
                      <p
                        className={`leading-relaxed text-[15px] md:text-base max-w-3xl whitespace-pre-wrap drop-shadow-lg min-h-[2em] ${
                          isTyping ? 'typing-cursor text-white/90'
                            : isUserMessage ? 'text-indigo-300/90 italic'
                            : dialogueBubbles.length > 0 ? 'text-white/50 text-[13px]'
                            : 'text-white/90'
                        }`}
                      >
                        {isTyping ? cleanedNarration : pageText}
                      </p>
                      {totalPages > 1 && currentPage === 0 && !isTyping && (
                        <p className="text-[9px] text-white/20 mt-1.5">
                          <span className="md:hidden">{t('game.swipe_hint')}</span>
                          <span className="hidden md:inline">&larr; &rarr; arrows to read more</span>
                        </p>
                      )}
                    </>
                  ) : (
                    /* Chat input page */
                    <div className="max-w-xl" onClick={(e) => e.stopPropagation()}>
                      <p className="text-[11px] text-white/30 mb-2">Chat / Action</p>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && chatInput.trim()) {
                              e.preventDefault()
                              handleChatSend()
                            }
                            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                              e.stopPropagation()
                            }
                          }}
                          placeholder="Parle, agis..."
                          disabled={chatLoading}
                          className="flex-1 bg-black/50 border border-white/20 rounded-xl px-4 py-3 text-sm text-white focus:border-indigo-500 focus:outline-none placeholder-white/20 disabled:opacity-50"
                        />
                        <button
                          onClick={(e) => { e.stopPropagation(); handleChatSend() }}
                          disabled={!chatInput.trim() || chatLoading}
                          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 px-5 py-3 rounded-xl text-sm font-medium transition-colors min-h-[48px]"
                        >
                          {chatLoading ? '...' : '\u2192'}
                        </button>
                      </div>
                    </div>
                  )}
                  {chatLoading && !isOnChatInputPage && (
                    <div className="flex items-center gap-2 mt-2 text-white/40 text-xs">
                      <div className="w-3 h-3 border border-white/20 border-t-white/60 rounded-full animate-spin" />
                      <span>...</span>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          ) : narration ? (
            null
          ) : isStreaming && image.status === 'pending' ? (
            <div className="flex items-center gap-3 text-white/50">
              <div className="w-4 h-4 border-2 border-white/20 border-t-white/60 rounded-full animate-spin" />
              <span className="text-sm">{t('game.story_starting')}</span>
            </div>
          ) : null}

          {/* Moods + LoRAs badges */}
          {image.status === 'ready' && showText && image.genSettings && (
            <div className="flex flex-wrap gap-1 mt-2">
              {image.genSettings.style_moods?.map((mood) => (
                <span key={mood} className="text-[9px] px-1.5 py-0.5 rounded bg-purple-900/60 text-purple-300 font-mono">
                  {mood}
                </span>
              ))}
              {image.genSettings.loras?.map((lora) => (
                <span key={lora.id} className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-900/60 text-indigo-300 font-mono">
                  {loraShortName(lora.id)} <span className="text-indigo-500">@{lora.weight}</span>
                </span>
              ))}
            </div>
          )}

          {/* Cost + seed + regen */}
          {image.status === 'ready' && showControls && showText && (
            <>
              <div className="flex items-center gap-3 mt-1 text-[10px] text-white/20">
                <span>${image.cost?.toFixed(4)}</span>
                <span>{image.generationTime}s</span>
                {image.seed && <span>#{image.seed}</span>}
                <div className="flex-1" />
                {onRegenImage && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onRegenImage(index)
                    }}
                    disabled={regenLoading}
                    className="text-white/40 hover:text-white/80 transition-colors disabled:opacity-30 text-xs min-h-[36px] px-2"
                  >
                    {regenLoading ? '...' : t('game.regen_image')}
                  </button>
                )}
              </div>
              {/* Video regen controls */}
              {image.url && (
                <div className="mt-2 space-y-1.5" onClick={(e) => e.stopPropagation()}>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleVideoRegen(false)}
                      disabled={videoRegenLoading}
                      className="text-purple-400/70 hover:text-purple-300 transition-colors disabled:opacity-30 text-[10px] min-h-[28px] px-1.5"
                    >
                      {videoRegenLoading ? 'generating...' : image.sceneVideoUrl ? 'regen video (HQ)' : 'gen video (HQ)'}
                    </button>
                    <button
                      onClick={() => handleVideoRegen(true)}
                      disabled={videoRegenLoading}
                      className="text-purple-400/40 hover:text-purple-300 transition-colors disabled:opacity-30 text-[10px] min-h-[28px] px-1.5"
                    >
                      draft
                    </button>
                    <button
                      onClick={() => { setShowVideoPrompt(!showVideoPrompt); if (!videoPromptEdit) setVideoPromptEdit(narration) }}
                      className="text-white/20 hover:text-white/50 transition-colors text-[10px] min-h-[28px] px-1.5"
                    >
                      {showVideoPrompt ? 'hide prompt' : 'edit prompt'}
                    </button>
                  </div>
                  {showVideoPrompt && (
                    <textarea
                      value={videoPromptEdit}
                      onChange={(e) => setVideoPromptEdit(e.target.value)}
                      rows={3}
                      className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white/70 font-mono focus:border-purple-500 focus:outline-none resize-y"
                      placeholder="Video prompt (narration used by default)"
                    />
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Collapsed text indicator ── */}
      {!showText && narration && (
        <div className="absolute bottom-0 left-0 right-0 z-10 flex items-center justify-center pb-3">
          <div className="bg-black/50 backdrop-blur-sm rounded-full px-3 py-1 flex items-center gap-1.5">
            <svg className="w-3 h-3 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
            </svg>
            <span className="text-[10px] text-white/40">{t('game.text_label')}</span>
          </div>
        </div>
      )}
    </div>
  )
}
