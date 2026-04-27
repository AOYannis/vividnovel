import { useState } from 'react'
import { useT } from '../../i18n'
import type { Choice, ImageSlot, SequenceCosts } from '../../api/types'

interface ChoicesPanelProps {
  choices: Choice[]
  onChoice: (choice: Choice) => void
  videoCost: number
  sequenceCosts: SequenceCosts | null
  videoStatus: string
  videoUrl: string | null
  videoPrompt: string | null
  sessionId: string | null
  images: ImageSlot[]
  onRegenVideo?: () => void
  regenVideoLoading?: boolean
  /** Slice-of-life: when present, render an extra "Aller ailleurs" button that opens the map. */
  onOpenMap?: () => void
}

export default function ChoicesPanel({
  choices,
  onChoice,
  videoCost,
  sequenceCosts,
  videoStatus,
  videoUrl,
  videoPrompt,
  sessionId,
  images,
  onRegenVideo,
  regenVideoLoading = false,
  onOpenMap,
}: ChoicesPanelProps) {
  const t = useT()
  const [freeText, setFreeText] = useState('')

  const handleFreeTextSubmit = () => {
    if (freeText.trim()) {
      onChoice({ id: 'free', text: freeText.trim() })
      setFreeText('')
    }
  }

  return (
    <div className="h-[100dvh] snap-start relative shrink-0 overflow-hidden flex items-center justify-center">
      {/* Semi-transparent dark background with glassmorphism */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-md" />

      {/* Content */}
      <div className="relative z-10 w-full max-w-lg px-6 py-8">
        {choices.length > 0 && (
          <>
            <p className="text-white/50 text-sm mb-5 text-center tracking-wide">
              {t('game.what_do_you_do')}
            </p>

            <div className="space-y-3">
              {choices.map((choice) => (
                <button
                  key={choice.id}
                  onClick={() => onChoice(choice)}
                  className="w-full text-left min-h-[56px] p-4 rounded-2xl border border-white/10 bg-white/5 hover:border-indigo-500/50 hover:bg-indigo-950/30 transition-all group backdrop-blur-sm active:scale-[0.98]"
                >
                  <span className="text-indigo-400 font-mono text-xs mr-2 uppercase">
                    {choice.id}
                  </span>
                  <span className="text-white/90 text-sm leading-relaxed">
                    {choice.text}
                  </span>
                </button>
              ))}

              {/* Slice-of-life: open map / go elsewhere */}
              {onOpenMap && (
                <button
                  onClick={onOpenMap}
                  className="w-full text-left min-h-[56px] p-4 rounded-2xl border border-emerald-500/30 bg-emerald-950/20 hover:border-emerald-500/60 hover:bg-emerald-900/30 transition-all backdrop-blur-sm active:scale-[0.98]"
                >
                  <span className="text-emerald-400 font-mono text-xs mr-2 uppercase">⌖</span>
                  <span className="text-white/90 text-sm leading-relaxed">{t('map.go_elsewhere_choice')}</span>
                </button>
              )}

              {/* Free text option */}
              <div className="min-h-[56px] p-4 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-purple-400 font-mono text-xs">D</span>
                  <span className="text-white/40 text-sm">{t('game.other_choice')}</span>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={freeText}
                    onChange={(e) => setFreeText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleFreeTextSubmit()
                    }}
                    placeholder={t('game.free_text_placeholder')}
                    className="flex-1 bg-black/50 border border-white/20 rounded-xl px-4 py-3 text-sm text-white focus:border-purple-500 focus:outline-none placeholder-white/20"
                  />
                  <button
                    onClick={handleFreeTextSubmit}
                    disabled={!freeText.trim()}
                    className="bg-purple-700 hover:bg-purple-600 disabled:opacity-30 px-5 py-3 rounded-xl text-sm font-medium transition-colors"
                  >
                    {t('game.go')}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Regen video button */}
        {videoStatus === 'ready' && videoUrl && onRegenVideo && (
          <div className="mt-4 flex justify-center">
            <button
              onClick={onRegenVideo}
              disabled={regenVideoLoading || !videoPrompt}
              className="text-white/40 hover:text-white/70 text-xs transition-colors disabled:opacity-30 bg-white/5 px-4 py-2 rounded-full backdrop-blur-sm border border-white/10"
            >
              {regenVideoLoading ? '...' : t('game.regen_video')}
            </button>
          </div>
        )}

        {/* Cost footer */}
        <div className="mt-6 flex items-center justify-center gap-4 text-[10px] text-white/20 font-mono">
          {videoCost > 0 && <span>Video: ${videoCost.toFixed(4)}</span>}
          {sequenceCosts && (
            <span>
              Seq: ${sequenceCosts.total_sequence_cost.toFixed(4)} ({sequenceCosts.elapsed_seconds}s)
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
