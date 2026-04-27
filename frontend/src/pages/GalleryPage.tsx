import { useEffect, useState } from 'react'
import { useGameStore } from '../stores/gameStore'
import { useT } from '../i18n'
import { getSessionHistory } from '../api/client'

interface ImageData {
  id: string
  image_index: number
  url: string
  prompt: string
  actors_present: string[]
  cost: number
  seed: number
  generation_time: number
  gen_settings: any
  scene_video_url?: string
}

interface VideoData {
  id: string
  url: string
  prompt: string
  cost: number
  generation_time: number
}

interface SequenceData {
  id: string
  sequence_number: number
  narration_segments: string[]
  choices_offered: { id: string; text: string }[]
  choice_made: { id: string; text: string } | null
  costs: any
  images: ImageData[]
  videos: VideoData[]
}

export default function GalleryPage() {
  const t = useT()
  const { sessionId, reset } = useGameStore()
  const [session, setSession] = useState<any>(null)
  const [sequences, setSequences] = useState<SequenceData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedImage, setSelectedImage] = useState<ImageData | null>(null)
  const [selectedVideo, setSelectedVideo] = useState<VideoData | null>(null)
  const [showMeta, setShowMeta] = useState(false)

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    getSessionHistory(sessionId)
      .then((data) => {
        setSession(data.session)
        setSequences(data.sequences || [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <div className="min-h-[100dvh] bg-neutral-950 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-neutral-700 border-t-indigo-500 rounded-full animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-[100dvh] bg-neutral-950 flex items-center justify-center p-4">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <button onClick={reset} className="text-indigo-400 hover:text-indigo-300 text-sm">{t('gallery.back')}</button>
        </div>
      </div>
    )
  }

  const totalCost = session?.total_costs?.total || 0
  const totalGrok = session?.total_costs?.grok_cost || 0
  const totalImage = session?.total_costs?.image_cost || 0
  const playerName = session?.player?.name || 'Anonyme'
  const settingLabel = session?.setting === 'custom' ? 'Custom' : session?.setting?.replace('_', ' ')

  return (
    <div className="min-h-[100dvh] bg-neutral-950 text-neutral-100">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-neutral-950/90 backdrop-blur-sm border-b border-neutral-800 px-4 md:px-6 py-3 md:py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">
              <span className="text-indigo-400">Graph</span>
              <span className="text-purple-400">Bun</span>
              <span className="text-neutral-500 text-sm font-normal ml-3">{t('gallery.title')}</span>
            </h1>
            <p className="text-xs text-neutral-500 mt-0.5">
              {playerName} &middot; {settingLabel} &middot; {sequences.length} seq &middot;
              <span className="text-emerald-400/60 font-mono ml-1">${totalCost.toFixed(4)}</span>
              <span className="text-neutral-600 ml-2">(LLM ${totalGrok.toFixed(3)} &middot; Img ${totalImage.toFixed(3)})</span>
            </p>
          </div>
          <button
            onClick={reset}
            className="text-sm px-4 py-2 min-h-[44px] rounded-lg bg-neutral-900 text-neutral-400 hover:text-neutral-200 transition-colors flex items-center"
          >
            {t('gallery.back')}
          </button>
        </div>
      </header>

      {/* Sequences */}
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-8 space-y-12">
        {sequences.length === 0 && (
          <p className="text-neutral-600 text-center py-12">{t('gallery.no_sequences')}</p>
        )}

        {sequences.map((seq) => {
          const sortedImages = [...(seq.images || [])].sort((a, b) => a.image_index - b.image_index)
          const video = seq.videos?.[0]

          return (
            <div key={seq.id} className="fade-in">
              {/* Sequence header + cost breakdown */}
              <div className="flex items-center gap-3 mb-1">
                <span className="text-xs font-mono text-indigo-400 bg-indigo-950/40 px-2 py-1 rounded">
                  {t('game.seq')} {seq.sequence_number + 1}
                </span>
                {seq.costs && (
                  <span className="text-[10px] text-emerald-400/60 font-mono">
                    ${seq.costs.total_sequence_cost?.toFixed(4) || '0'}
                  </span>
                )}
              </div>
              {seq.costs && (
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 mb-4 text-[9px] font-mono text-neutral-600">
                  <span>LLM: ${seq.costs.grok_cost?.toFixed(4) || '0'} <span className="text-neutral-700">({seq.costs.grok_input_tokens?.toLocaleString() || 0}+{seq.costs.grok_output_tokens?.toLocaleString() || 0} tok)</span></span>
                  <span>Images: ${(seq.costs.image_costs?.reduce((a: number, b: number) => a + b, 0) || 0).toFixed(4)}</span>
                  {(seq.costs.video_cost ?? 0) > 0 && <span>Video: ${seq.costs.video_cost?.toFixed(4)}</span>}
                  {(seq.costs.tts_cost ?? 0) > 0 && <span>TTS: ${seq.costs.tts_cost?.toFixed(4)}</span>}
                  <span className="text-neutral-700">{seq.costs.elapsed_seconds ? `${Math.round(seq.costs.elapsed_seconds)}s` : ''}</span>
                </div>
              )}

              {/* Image grid + narration */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                {sortedImages.map((img) => (
                  <div key={img.id} className="group">
                    {/* Image card (with video overlay if available) */}
                    <div
                      className={`relative rounded-xl overflow-hidden border transition-colors cursor-pointer ${
                        img.scene_video_url ? 'border-purple-800/50 hover:border-purple-600' : 'border-neutral-800 hover:border-indigo-700'
                      }`}
                      onClick={() => {
                        if (img.scene_video_url) {
                          setSelectedVideo({ id: img.id, url: img.scene_video_url, prompt: img.prompt, cost: img.cost, generation_time: img.generation_time })
                        } else {
                          setSelectedImage(img); setShowMeta(false)
                        }
                      }}
                    >
                      {img.url ? (
                        img.scene_video_url ? (
                          <video
                            src={img.scene_video_url}
                            className="w-full aspect-video object-cover"
                            muted loop playsInline
                            onMouseEnter={(e) => (e.target as HTMLVideoElement).play()}
                            onMouseLeave={(e) => { const v = e.target as HTMLVideoElement; v.pause(); v.currentTime = 0 }}
                            poster={img.url}
                          />
                        ) : (
                          <img
                            src={img.url}
                            alt={`Scene ${img.image_index + 1}`}
                            className="w-full aspect-video object-cover"
                            loading="lazy"
                          />
                        )
                      ) : (
                        <div className="w-full aspect-video bg-neutral-900 flex items-center justify-center">
                          <span className="text-neutral-700 text-xs">{t('gallery.no_image')}</span>
                        </div>
                      )}
                      {/* Overlay */}
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-end">
                        <div className="w-full p-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="flex justify-between text-[9px] text-white/60">
                            <span>${img.cost?.toFixed(4)}</span>
                            <span>{img.generation_time}s</span>
                          </div>
                        </div>
                      </div>
                      <div className="absolute top-1 left-1 flex gap-1">
                        <span className="bg-black/50 text-white text-[9px] px-1.5 py-0.5 rounded">
                          {img.image_index + 1}
                        </span>
                        {img.scene_video_url && (
                          <span className="bg-purple-700/80 text-white text-[9px] px-1.5 py-0.5 rounded">
                            VID
                          </span>
                        )}
                      </div>
                    </div>
                    {/* Narration snippet */}
                    {seq.narration_segments?.[img.image_index] && (
                      <p className="text-[11px] text-neutral-500 mt-1.5 line-clamp-3 leading-relaxed">
                        {seq.narration_segments[img.image_index]}
                      </p>
                    )}
                  </div>
                ))}

                {/* Video card */}
                {video && (
                  <div className="group">
                    <div
                      className="relative rounded-xl overflow-hidden border border-purple-900/50 hover:border-purple-600 transition-colors cursor-pointer"
                      onClick={() => setSelectedVideo(video)}
                    >
                      <video
                        src={video.url}
                        className="w-full aspect-video object-cover"
                        muted
                        loop
                        onMouseEnter={(e) => (e.target as HTMLVideoElement).play()}
                        onMouseLeave={(e) => { (e.target as HTMLVideoElement).pause(); (e.target as HTMLVideoElement).currentTime = 0 }}
                      />
                      <div className="absolute top-1 left-1 bg-purple-700/80 text-white text-[9px] px-1.5 py-0.5 rounded">
                        VID
                      </div>
                      <div className="absolute bottom-1 right-1 text-[9px] text-white/40">
                        ${video.cost?.toFixed(4)}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Choice made */}
              {seq.choice_made && (
                <div className="mt-3 flex items-center gap-2">
                  <span className="text-[10px] text-neutral-600">{t('history.choice_label')}</span>
                  <span className="text-xs text-indigo-400/80 bg-indigo-950/30 px-2 py-1 rounded">
                    {seq.choice_made.text}
                  </span>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ═══ Image lightbox ═══ */}
      {selectedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setSelectedImage(null)}
        >
          <div className="max-w-5xl w-full max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <img
              src={selectedImage.url}
              alt=""
              className="max-h-[85vh] md:max-h-[70vh] w-full object-contain rounded-xl"
            />
            {/* Metadata: collapsed by default on mobile, always visible on md+ */}
            <div className="mt-4">
              <button
                onClick={() => setShowMeta(!showMeta)}
                className="md:hidden w-full text-center text-xs text-neutral-500 hover:text-neutral-300 py-2 transition-colors"
              >
                {showMeta ? 'Masquer' : t('gallery.show_details')}
              </button>
              <div className={`bg-neutral-900 rounded-xl p-4 overflow-y-auto max-h-[20vh] ${showMeta ? 'block' : 'hidden md:block'}`}>
                <div className="flex items-center gap-3 text-xs text-neutral-500 mb-2">
                  <span>Image {selectedImage.image_index + 1}</span>
                  <span className="text-emerald-400/60 font-mono">${selectedImage.cost?.toFixed(4)}</span>
                  <span>{selectedImage.generation_time}s</span>
                  {selectedImage.seed && <span className="font-mono">Seed: {selectedImage.seed}</span>}
                  {selectedImage.actors_present?.length > 0 && (
                    <span className="text-purple-400">{selectedImage.actors_present.join(', ')}</span>
                  )}
                </div>
                {selectedImage.prompt && (
                  <p className="text-[11px] text-neutral-400 font-mono whitespace-pre-wrap leading-relaxed">
                    {selectedImage.prompt}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => setSelectedImage(null)}
              className="absolute top-4 right-4 text-white/50 hover:text-white text-2xl"
            >
              &times;
            </button>
          </div>
        </div>
      )}

      {/* ═══ Video lightbox ═══ */}
      {selectedVideo && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setSelectedVideo(null)}
        >
          <div className="max-w-4xl w-full" onClick={(e) => e.stopPropagation()}>
            <video
              src={selectedVideo.url}
              controls
              autoPlay
              loop
              className="w-full rounded-xl"
            />
            <div className="mt-3 flex items-center gap-3 text-xs text-neutral-500">
              <span className="text-emerald-400/60 font-mono">${selectedVideo.cost?.toFixed(4)}</span>
              <span>{selectedVideo.generation_time}s</span>
            </div>
            {selectedVideo.prompt && (
              <p className="mt-2 text-[11px] text-neutral-400 font-mono">{selectedVideo.prompt}</p>
            )}
            <button
              onClick={() => setSelectedVideo(null)}
              className="absolute top-4 right-4 text-white/50 hover:text-white text-2xl"
            >
              &times;
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
