import { useEffect, useRef, useCallback, useState } from 'react'
import { useGameStore } from '../stores/gameStore'
import { useStoryStream } from '../hooks/useStoryStream'
import { useSceneAudio } from '../hooks/useSceneAudio'
import { useT } from '../i18n'
import { regenImage, regenVideo } from '../api/client'
import DebugPanel from '../components/DebugPanel'
import SceneCard from '../components/game/SceneCard'
import VideoScene from '../components/game/VideoScene'
import ChoicesPanel from '../components/game/ChoicesPanel'
import Phone from '../components/game/Phone'
import MapModal from '../components/game/MapModal'

export default function GamePage() {
  const t = useT()
  const {
    narrationSegments, images, choices, isStreaming, sequenceNumber,
    sequenceCosts, showDebug, toggleDebug, step, currentScene,
    setCurrentScene, resetForNewSequence, selectChoice,
    videoStatus, videoUrl, videoCost, videoPrompt, generatedPrompts, sessionId,
    reset, activeSegmentIndex, completedSequences, world,
  } = useGameStore()
  const { startSequence } = useStoryStream()
  // Install the page-level singleton <audio> + first-gesture warmup BEFORE any
  // SceneCard mounts, so the very first scroll-to-scene already has an unlocked
  // audio element to play through (critical on iOS Safari).
  useSceneAudio()
  const [mapOpen, setMapOpen] = useState(false)
  const startedRef = useRef(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const sceneRefs = useRef<Map<number, HTMLDivElement>>(new Map())
  const videoSceneRef = useRef<HTMLDivElement | null>(null)
  const [regenLoading, setRegenLoading] = useState<number | null>(null)
  const [regenVideoLoading, setRegenVideoLoading] = useState(false)

  // ── Scene availability ──
  const availableScenes = images.filter((img) => img.status !== 'pending').length
  const scenesWithText = narrationSegments.filter((s) => s.length > 0).length
  const sceneCount = Math.max(availableScenes, scenesWithText)
  const hasVideo = videoStatus !== 'none'
  const hasChoicesScene = step === 'choosing' || hasVideo

  // Total items in the scroll feed
  const totalSlots = sceneCount + (hasVideo ? 1 : 0) + (hasChoicesScene ? 1 : 0)

  // ── Auto-start first sequence ──
  useEffect(() => {
    if (!startedRef.current && sequenceNumber === 0 && step === 'playing') {
      startedRef.current = true
      startSequence()
    }
  }, [])

  // ── Slice-of-life: fetch the full world payload (character states +
  //    known whereabouts + presence map) once on mount. Falls back silently
  //    if not in slice mode. The map modal also re-fetches on open. ──
  const setWorldPayload = useGameStore((s) => s.setWorldPayload)
  useEffect(() => {
    if (!sessionId || !world) return
    import('../api/client').then(({ fetchWorld }) => {
      fetchWorld(sessionId).then(setWorldPayload).catch(() => {})
    })
  }, [sessionId, world?.current_location, world?.day, world?.slot])

  // ── On resume: scroll to the bottom (choices / continue) ──
  // Only fires when we MOUNT already in the 'choosing' step (i.e. user reopened the app
  // on a saved choice screen). Must NOT fire when step *transitions* into 'choosing'
  // during active play — that yanks the user away from whatever scene they're reading.
  const resumeScrolledRef = useRef(false)
  const initialStepRef = useRef(step)
  useEffect(() => {
    const wasResumeMount = initialStepRef.current === 'choosing'
    if (
      wasResumeMount &&
      !resumeScrolledRef.current &&
      step === 'choosing' &&
      completedSequences.length > 0
    ) {
      resumeScrolledRef.current = true
      setTimeout(() => {
        const container = scrollContainerRef.current
        if (container) container.scrollTop = container.scrollHeight
      }, 200)
    }
  }, [step, completedSequences.length])

  // ── Auto-scroll to current sequence when a new one starts ──
  const prevSeqCountRef = useRef(completedSequences.length)
  useEffect(() => {
    if (completedSequences.length > prevSeqCountRef.current) {
      // A new sequence just started — scroll to the first scene of the current sequence
      prevSeqCountRef.current = completedSequences.length
      // Small delay to let the DOM render the new scenes
      setTimeout(() => {
        const firstScene = sceneRefs.current.get(0)
        if (firstScene) {
          firstScene.scrollIntoView({ behavior: 'smooth' })
        }
      }, 100)
    }
  }, [completedSequences.length])

  // ── Track active scene via IntersectionObserver ──
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
            const sceneIndex = Number(entry.target.getAttribute('data-scene-index'))
            if (!isNaN(sceneIndex)) {
              setCurrentScene(sceneIndex)
            }
          }
        }
      },
      { root: container, threshold: 0.5 },
    )

    // Observe all scene elements
    sceneRefs.current.forEach((el) => observer.observe(el))
    if (videoSceneRef.current) observer.observe(videoSceneRef.current)

    return () => observer.disconnect()
  }, [sceneCount, hasVideo, hasChoicesScene, setCurrentScene])

  // ── Scene ref registration ──
  const handleSceneRef = useCallback((index: number, el: HTMLDivElement | null) => {
    if (el) {
      el.setAttribute('data-scene-index', String(index))
      sceneRefs.current.set(index, el)
    } else {
      sceneRefs.current.delete(index)
    }
  }, [])

  const VIDEO_SCENE_IDX = 999 // sentinel for the video/choices scene

  const handleVideoSceneRef = useCallback((el: HTMLDivElement | null) => {
    if (el) {
      el.setAttribute('data-scene-index', String(VIDEO_SCENE_IDX))
    }
    videoSceneRef.current = el
  }, [])

  // ── Keyboard navigation (ArrowUp/ArrowDown) ──
  const scrollToScene = useCallback((sceneIndex: number) => {
    const el = sceneRefs.current.get(sceneIndex) || (sceneIndex === VIDEO_SCENE_IDX ? videoSceneRef.current : null)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        const nextScene = currentScene + 1
        if (nextScene < totalSlots) scrollToScene(nextScene < sceneCount ? nextScene : VIDEO_SCENE_IDX)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        const prevScene = currentScene - 1
        if (prevScene >= 0) scrollToScene(prevScene < sceneCount ? prevScene : VIDEO_SCENE_IDX)
      }
    },
    [currentScene, totalSlots, scrollToScene],
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // ── Choice handling ──
  const handleChoice = useCallback((choice: { id: string; text: string; target_location_id?: string | null }) => {
    selectChoice(choice)
    resetForNewSequence()
    startSequence(choice.id, choice.text, choice.target_location_id ?? null)
  }, [selectChoice, resetForNewSequence, startSequence])

  // ── Regen image ──
  const handleRegenImage = useCallback(async (index: number) => {
    if (!sessionId) return
    const promptData = generatedPrompts.find((p) => p.index === index)
    if (!promptData) return
    setRegenLoading(index)
    try {
      const result = await regenImage({
        sessionId: sessionId!,
        prompt: promptData.prompt,
        actorsPresent: promptData.actors,
        imageIndex: index,
      })
      useGameStore.getState().handleSSEEvent({
        type: 'image_ready',
        index,
        url: result.url,
        cost: result.cost,
        seed: result.seed,
        generation_time: result.elapsed,
      })
    } catch (e) {
      console.error('Regen image failed:', e)
    } finally {
      setRegenLoading(null)
    }
  }, [sessionId, generatedPrompts])

  // ── Regen video ──
  const handleRegenVideo = useCallback(async () => {
    if (!sessionId || !videoPrompt) return
    const lastReady = [...images].reverse().find((i) => i.status === 'ready')
    if (!lastReady?.url) return
    setRegenVideoLoading(true)
    try {
      const result = await regenVideo(sessionId, videoPrompt, lastReady.url)
      useGameStore.getState().handleSSEEvent({
        type: 'video_ready',
        url: result.url,
        cost: result.cost,
        generation_time: result.elapsed,
      })
    } catch (e) {
      console.error('Regen video failed:', e)
    } finally {
      setRegenVideoLoading(false)
    }
  }, [sessionId, videoPrompt, images])

  // ── Determine which dot index is "active" for the progress dots ──
  // scenes 0-4 => dot 0-4, video => dot 5, choices => dot 6
  const getActiveDotIndex = () => {
    return currentScene
  }
  const activeDot = getActiveDotIndex()

  return (
    <div className="h-[100dvh] bg-black flex">
      {/* ═══ VERTICAL SCROLL CONTAINER ═══ */}
      <div
        ref={scrollContainerRef}
        className="flex-1 h-[100dvh] overflow-y-auto snap-y snap-mandatory no-scrollbar relative"
      >
        {/* ── Previously completed sequences (scroll-back) ── */}
        {completedSequences.map((seq, seqIdx) => (
          <div key={`completed-${seqIdx}`}>
            {seq.images.map((img, i) => {
              const narr = seq.narrationSegments[i] || ''
              if (!narr && img.status === 'pending') return null
              return (
                <SceneCard
                  key={`completed-${seqIdx}-scene-${i}`}
                  index={i}
                  narration={narr}
                  image={img}
                  isStreaming={false}
                  isActive={false}
                  isViewing={false}
                  totalScenes={seq.images.length}
                  onSceneRef={() => {}}
                />
              )
            })}
            {/* Video from completed sequence */}
            {seq.videoUrl && (
              <VideoScene
                videoStatus="ready"
                videoUrl={seq.videoUrl}
                images={seq.images}
                onSceneRef={() => {}}
              />
            )}
            {/* Choice made divider */}
            {seq.choiceMade && (
              <div className="h-[40dvh] snap-start flex items-center justify-center bg-black/90">
                <div className="text-center px-6">
                  <span className="text-[10px] text-white/30 uppercase tracking-widest">{t('game.seq')} {seq.sequenceNumber + 1}</span>
                  <p className="text-indigo-400/80 text-sm mt-2 max-w-sm">
                    {seq.choiceMade.text}
                  </p>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* ── Current sequence: Image scenes (0 through sceneCount-1) ── */}
        {Array.from({ length: sceneCount }, (_, i) => (
          <SceneCard
            key={`scene-${i}`}
            index={i}
            narration={narrationSegments[i] || ''}
            image={images[i] || { index: i, status: 'pending' as const }}
            isStreaming={isStreaming}
            isActive={i === activeSegmentIndex}
            isViewing={i === currentScene}
            totalScenes={sceneCount}
            onSceneRef={handleSceneRef}
            onRegenImage={generatedPrompts.find((p) => p.index === i) ? handleRegenImage : undefined}
            regenLoading={regenLoading === i}
            chatEnabled
          />
        ))}

        {/* ── Video scene (after last image, before choices) ── */}
        {hasVideo && (
          <VideoScene
            videoStatus={videoStatus}
            videoUrl={videoUrl}
            images={images}
            onSceneRef={handleVideoSceneRef}
          />
        )}

        {/* ── Choices panel (last card) ── */}
        {hasChoicesScene && choices.length > 0 && (
          <div
            ref={(el) => {
              if (el) el.setAttribute('data-scene-index', String(VIDEO_SCENE_IDX + 1))
            }}
          >
            <ChoicesPanel
              choices={choices}
              onChoice={handleChoice}
              videoCost={videoCost}
              sequenceCosts={sequenceCosts}
              videoStatus={videoStatus}
              videoUrl={videoUrl}
              videoPrompt={videoPrompt}
              sessionId={sessionId}
              images={images}
              onRegenVideo={handleRegenVideo}
              regenVideoLoading={regenVideoLoading}
              onOpenMap={world ? () => setMapOpen(true) : undefined}
            />
          </div>
        )}

        {/* ── Resumed session with no choices: continue button ── */}
        {!isStreaming && step === 'choosing' && choices.length === 0 && (
          <div className="h-[100dvh] snap-start snap-always flex items-center justify-center bg-black/80">
            <div className="text-center px-6">
              <p className="text-white/60 text-sm mb-4">
                {t('game.resumed')} {sequenceNumber + 1}
              </p>
              <button
                onClick={() => {
                  resetForNewSequence()
                  startSequence()
                }}
                className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 px-8 py-3 rounded-xl font-medium transition-all text-white"
              >
                {t('game.continue')}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ═══ HUD OVERLAY (fixed, z-30) ═══ */}

      {/* Top-left: Logo + sequence number */}
      <div className="fixed top-0 left-0 z-30 flex items-center gap-3 px-5 py-3">
        <div className="bg-black/40 backdrop-blur-sm rounded-full px-3 py-1.5 flex items-center gap-2">
          <h1 className="text-sm font-bold drop-shadow-lg">
            <span className="text-indigo-400">Graph</span>
            <span className="text-purple-400">Bun</span>
          </h1>
          <span className="text-xs text-white/40">
            {t('game.seq')} {sequenceNumber + (isStreaming ? 1 : 0)}
          </span>
        </div>
      </div>

      {/* Top-right: session cost + debug + menu */}
      <div className="fixed top-0 right-0 z-30 flex items-center gap-2 px-5 py-3">
        {sequenceCosts && (
          <span className="text-[10px] text-emerald-400/70 font-mono drop-shadow bg-black/40 backdrop-blur-sm rounded-full px-2.5 py-1.5">
            ${sequenceCosts.total_session_cost.toFixed(4)}
          </span>
        )}
        {/* World badge + Map button (slice-of-life mode only) */}
        {world && (
          <>
            <button
              onClick={() => setMapOpen(true)}
              className="text-[10px] font-mono px-2.5 py-1.5 rounded-full transition-colors backdrop-blur-sm bg-emerald-950/50 text-emerald-300 hover:bg-emerald-900/60 border border-emerald-900/40"
              title={t('map.title_modal')}
            >
              ⌖ {t('map.agenda_day_short')}{world.day} · {t(`map.slot.${world.slot}`)} · {world.locations.find((l) => l.id === world.current_location)?.name || world.current_location}
            </button>
          </>
        )}
        {/* Phone button */}
        <button
          onClick={() => useGameStore.setState({ phoneOpen: true })}
          className="text-xs px-2.5 py-1.5 rounded-full transition-colors backdrop-blur-sm bg-black/40 text-white/50 hover:text-white/80"
        >
          📱
        </button>
        <button
          onClick={toggleDebug}
          className={`text-xs px-2.5 py-1.5 rounded-full transition-colors backdrop-blur-sm ${
            showDebug
              ? 'bg-indigo-600/80 text-white'
              : 'bg-black/40 text-white/50 hover:text-white/80'
          }`}
        >
          Debug
        </button>
        <button
          onClick={() => {
            if (confirm(t('game.menu_confirm'))) reset()
          }}
          className="text-xs px-2.5 py-1.5 rounded-full transition-colors backdrop-blur-sm bg-black/40 text-white/50 hover:text-white/80"
        >
          {t('game.menu')}
        </button>
      </div>

      {/* Right side: vertical dots progress indicator (mobile-friendly) */}
      {sceneCount > 0 && (
        <div className="fixed right-3 top-1/2 -translate-y-1/2 z-30 flex flex-col items-center gap-1.5">
          {Array.from({ length: sceneCount }, (_, i) => {
            const img = images[i]
            const isActive = i === currentScene
            const isReady = img?.status === 'ready'
            const isGenerating = img?.status === 'generating'
            const hasVideo = !!img?.sceneVideoUrl
            const hasContent = (img?.status !== 'pending') || (narrationSegments[i]?.length > 0)
            return (
              <button
                key={`dot-${i}`}
                onClick={() => scrollToScene(i)}
                disabled={!hasContent}
                className={`transition-all rounded-full drop-shadow-lg ${
                  isActive
                    ? hasVideo ? 'w-2 h-6 bg-white' : isReady ? 'w-2 h-6 bg-cyan-400' : 'w-2 h-6 bg-white'
                    : isReady && hasVideo
                      ? 'w-2 h-2 bg-white/60 hover:bg-white/80'
                      : isReady
                        ? 'w-2 h-2 bg-cyan-400/60 hover:bg-cyan-400/80'
                        : isGenerating
                          ? 'w-2 h-2 bg-amber-400/70 animate-pulse'
                          : hasContent
                            ? 'w-2 h-2 bg-white/30'
                            : 'w-2 h-2 bg-white/10'
                }`}
              />
            )
          })}
          {hasVideo && (
            <button
              key="dot-video"
              onClick={() => scrollToScene(VIDEO_SCENE_IDX)}
              className={`transition-all rounded-full drop-shadow-lg ${
                currentScene === VIDEO_SCENE_IDX
                  ? 'w-2 h-6 bg-purple-400'
                  : videoStatus === 'ready'
                    ? 'w-2 h-2 bg-purple-400/60 hover:bg-purple-400/80'
                    : 'w-2 h-2 bg-purple-400/30'
              }`}
            />
          )}
          {hasChoicesScene && choices.length > 0 && (
            <button
              key="dot-choices"
              onClick={() => {
                const choicesIndex = hasVideo ? 6 : 5
                const container = scrollContainerRef.current
                if (container) {
                  const el = container.querySelector(`[data-scene-index="${choicesIndex}"]`)
                  el?.scrollIntoView({ behavior: 'smooth' })
                }
              }}
              className={`transition-all rounded-full drop-shadow-lg ${
                currentScene >= (hasVideo ? 6 : 5)
                  ? 'w-2 h-6 bg-emerald-400'
                  : 'w-2 h-2 bg-emerald-400/40 hover:bg-emerald-400/60'
              }`}
            />
          )}
        </div>
      )}

      {/* Debug panel (sidebar on desktop, bottom sheet on mobile) */}
      {showDebug && <DebugPanel onClose={toggleDebug} />}
      <Phone />
      <MapModal
        open={mapOpen}
        onClose={() => setMapOpen(false)}
        onMoved={(newWorld) => {
          // After moving to a new location, immediately fire a new sequence
          // there. resetForNewSequence clears the previous scene's state so the
          // narration starts fresh.
          resetForNewSequence()
          // Synthetic choice text the backend uses to detect a deliberate
          // free-roam move. The slice-of-life prompt branches on the prefix to
          // enforce alone-by-default at the new destination.
          const newLoc = newWorld.locations.find((l) => l.id === newWorld.current_location)
          const moveText = `${t('map.move_choice_prefix')} : ${newLoc?.name || newWorld.current_location}`
          startSequence('move', moveText)
        }}
      />
    </div>
  )
}
