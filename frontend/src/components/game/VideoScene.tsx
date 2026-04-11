import { useRef, useEffect, useState } from 'react'
import { useT } from '../../i18n'
import type { ImageSlot } from '../../api/types'

interface VideoSceneProps {
  videoStatus: string
  videoUrl: string | null
  images: ImageSlot[]
  onSceneRef: (el: HTMLDivElement | null) => void
}

export default function VideoScene({
  videoStatus,
  videoUrl,
  images,
  onSceneRef,
}: VideoSceneProps) {
  const t = useT()
  const lastReadyImage = [...images].reverse().find((i) => i.status === 'ready')
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isMuted, setIsMuted] = useState(true)

  // Mobile browsers block autoplay with audio — start muted, autoplay, then
  // let the user tap to unmute
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.play().catch(() => {
      // If even muted autoplay fails (very old browsers), ignore
    })
  }, [videoUrl])

  const toggleMute = () => {
    const video = videoRef.current
    if (!video) return
    video.muted = !video.muted
    setIsMuted(video.muted)
    // If it wasn't playing (e.g. autoplay blocked), start now
    if (video.paused) video.play().catch(() => {})
  }

  return (
    <div
      ref={onSceneRef}
      className="h-[100dvh] snap-start snap-always relative shrink-0 overflow-hidden"
    >
      {/* Video or fallback image */}
      {videoStatus === 'ready' && videoUrl ? (
        <>
          <video
            ref={videoRef}
            key={videoUrl}
            src={videoUrl}
            autoPlay
            loop
            muted
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
          />
          {/* Mute/unmute button */}
          <button
            onClick={toggleMute}
            className="absolute bottom-6 right-5 z-20 bg-black/50 backdrop-blur-sm rounded-full w-10 h-10 flex items-center justify-center text-white/70 hover:text-white transition-colors"
          >
            {isMuted ? (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-3.72a.75.75 0 011.28.53v14.88a.75.75 0 01-1.28.53L6.75 14.25H3.75a.75.75 0 01-.75-.75v-3a.75.75 0 01.75-.75h3z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-3.72a.75.75 0 011.28.53v14.88a.75.75 0 01-1.28.53L6.75 15.75H3.75a.75.75 0 01-.75-.75v-6a.75.75 0 01.75-.75h3z" />
              </svg>
            )}
          </button>
          {/* Tap to unmute hint — only when muted */}
          {isMuted && (
            <div className="absolute bottom-6 left-0 right-16 z-10 flex justify-center pointer-events-none">
              <span className="text-[10px] text-white/30 bg-black/30 backdrop-blur-sm rounded-full px-3 py-1">
                {t('game.unmute')}
              </span>
            </div>
          )}
        </>
      ) : (
        <>
          {/* Fallback: last ready image */}
          {lastReadyImage?.url && (
            <img
              src={lastReadyImage.url}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
            />
          )}

          {/* Dark overlay when no video */}
          <div className="absolute inset-0 bg-black/40" />

          {/* Loading indicator */}
          {videoStatus === 'generating' && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <div className="bg-black/60 backdrop-blur-sm text-white/60 text-sm px-5 py-3 rounded-full flex items-center gap-3">
                <div className="w-4 h-4 border-2 border-white/20 border-t-white/60 rounded-full animate-spin" />
                {t('game.video_loading')}
              </div>
            </div>
          )}

          {/* Error state */}
          {videoStatus === 'error' && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <div className="bg-red-950/60 backdrop-blur-sm text-red-300 text-sm px-5 py-3 rounded-2xl">
                {t('game.video_failed')}
              </div>
            </div>
          )}

          {/* Pending */}
          {videoStatus === 'none' && !lastReadyImage?.url && (
            <div className="absolute inset-0 bg-neutral-950" />
          )}
        </>
      )}
    </div>
  )
}
