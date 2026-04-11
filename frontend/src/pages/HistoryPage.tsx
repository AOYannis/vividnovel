import { useState } from 'react'
import { useGameStore, type HistorySequence } from '../stores/gameStore'
import { useStoryStream } from '../hooks/useStoryStream'
import { useT } from '../i18n'

export default function HistoryPage() {
  const {
    historySequences, sequenceNumber, sessionId,
    reset, resetForNewSequence,
  } = useGameStore()
  const { startSequence } = useStoryStream()
  const [selectedImage, setSelectedImage] = useState<{ url: string; prompt: string; cost: number; seed: number; time: number } | null>(null)
  const [expandedSeq, setExpandedSeq] = useState<number | null>(null)
  const t = useT()
  const [freeText, setFreeText] = useState('')

  // Last sequence's choices (for continue flow)
  const lastSeq = historySequences[historySequences.length - 1]
  const lastChoices = lastSeq?.choices_offered || []

  const handleContinueWithChoice = (choiceId: string, choiceText: string) => {
    resetForNewSequence()
    startSequence(choiceId, choiceText)
  }

  const handleContinueNoChoice = () => {
    resetForNewSequence()
    startSequence()
  }

  return (
    <div className="min-h-[100dvh] bg-neutral-950 text-neutral-100">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-neutral-950/90 backdrop-blur-sm border-b border-neutral-800 px-4 md:px-6 py-3 md:py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">
              <span className="text-indigo-400">Graph</span>
              <span className="text-purple-400">Bun</span>
              <span className="text-neutral-500 text-sm font-normal ml-3">{t('history.title')}</span>
            </h1>
            <p className="text-xs text-neutral-500 mt-0.5">
              {historySequences.length} {t('history.sequences_played')}
            </p>
          </div>
          <button
            onClick={reset}
            className="text-sm px-4 py-2 rounded-lg bg-neutral-900 text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            {t('common.menu')}
          </button>
        </div>
      </header>

      {/* Sequences */}
      <div className="max-w-4xl mx-auto px-4 md:px-6 py-8 space-y-6">
        {historySequences.length === 0 && (
          <div className="text-center py-16">
            <p className="text-neutral-500 mb-6">{t('history.no_sequences')}</p>
            <button
              onClick={handleContinue}
              className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 px-8 py-3 rounded-xl font-medium transition-all"
            >
              {t('history.start_story')}
            </button>
          </div>
        )}

        {historySequences.map((seq) => (
          <SequenceCard
            key={seq.id}
            seq={seq}
            isExpanded={expandedSeq === seq.sequence_number}
            onToggle={() => setExpandedSeq(expandedSeq === seq.sequence_number ? null : seq.sequence_number)}
            onImageClick={(img) => setSelectedImage(img)}
          />
        ))}

        {/* Continue — pick a choice from last sequence or start fresh */}
        {historySequences.length > 0 && (
          <div className="py-8 pb-8 border-t border-neutral-800">
            {lastChoices.length > 0 ? (
              <div className="max-w-lg mx-auto">
                <p className="text-neutral-400 text-sm mb-4 text-center">
                  {t('game.resumed')} {sequenceNumber + 1} — {t('game.what_do_you_do')}
                </p>
                <div className="space-y-2">
                  {lastChoices.map((choice) => (
                    <button
                      key={choice.id}
                      onClick={() => handleContinueWithChoice(choice.id, choice.text)}
                      className="w-full text-left p-3 min-h-[56px] rounded-xl border border-neutral-800 bg-neutral-900/50 hover:border-indigo-500/50 hover:bg-indigo-950/30 transition-all"
                    >
                      <span className="text-indigo-400 font-mono text-xs mr-2">{choice.id.toUpperCase()}</span>
                      <span className="text-neutral-200 text-sm">{choice.text}</span>
                    </button>
                  ))}
                  {/* Free text option */}
                  <div className="p-4 min-h-[56px] rounded-xl border border-neutral-800 bg-neutral-900/50">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-purple-400 font-mono text-xs">D</span>
                      <span className="text-neutral-500 text-sm">{t('game.other_choice')}</span>
                    </div>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={freeText}
                        onChange={(e) => setFreeText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && freeText.trim()) {
                            handleContinueWithChoice('free', freeText.trim())
                          }
                        }}
                        placeholder={t('game.free_text_placeholder')}
                        className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-3 text-sm text-neutral-200 focus:border-purple-500 focus:outline-none placeholder-neutral-600"
                      />
                      <button
                        onClick={() => freeText.trim() && handleContinueWithChoice('free', freeText.trim())}
                        disabled={!freeText.trim()}
                        className="bg-purple-700 hover:bg-purple-600 disabled:opacity-30 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                      >
                        {t('game.go')}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center">
                <p className="text-neutral-500 text-sm mb-4">
                  {t('game.resumed')} {sequenceNumber + 1} — {t('history.ready_to_continue')}
                </p>
                <button
                  onClick={handleContinueNoChoice}
                  className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 px-8 py-3 rounded-xl font-medium transition-all text-lg"
                >
                  {t('game.continue')}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Image lightbox */}
      {selectedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setSelectedImage(null)}
        >
          <div className="max-w-5xl w-full" onClick={(e) => e.stopPropagation()}>
            <img
              src={selectedImage.url}
              alt=""
              className="max-h-[85vh] md:max-h-[80vh] w-full object-contain rounded-xl"
            />
            {selectedImage.prompt && (
              <div className="mt-3 bg-neutral-900 rounded-xl p-4 max-h-[15vh] overflow-y-auto">
                <div className="flex items-center gap-3 text-xs text-neutral-500 mb-2">
                  <span className="text-emerald-400/60 font-mono">${selectedImage.cost?.toFixed(4)}</span>
                  <span>{selectedImage.time}s</span>
                  {selectedImage.seed && <span className="font-mono">Seed: {selectedImage.seed}</span>}
                </div>
                <p className="text-[11px] text-neutral-400 font-mono whitespace-pre-wrap leading-relaxed">
                  {selectedImage.prompt}
                </p>
              </div>
            )}
            <button
              onClick={() => setSelectedImage(null)}
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

function SequenceCard({
  seq,
  isExpanded,
  onToggle,
  onImageClick,
}: {
  seq: HistorySequence
  isExpanded: boolean
  onToggle: () => void
  onImageClick: (img: { url: string; prompt: string; cost: number; seed: number; time: number }) => void
}) {
  const t = useT()
  const sortedImages = [...(seq.images || [])].sort((a, b) => a.image_index - b.image_index)
  const video = seq.videos?.[0]
  const hasNarration = seq.narration_segments?.some((s) => s && s.length > 0)

  return (
    <div className="bg-neutral-900/50 rounded-2xl border border-neutral-800 overflow-hidden fade-in">
      {/* Sequence header — clickable to expand */}
      <button
        onClick={onToggle}
        className="w-full px-5 py-4 flex items-center justify-between hover:bg-neutral-800/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-indigo-400 bg-indigo-950/40 px-2.5 py-1 rounded-lg">
            {t('game.seq')} {seq.sequence_number + 1}
          </span>
          {seq.costs?.total_sequence_cost != null && (
            <span className="text-[10px] text-emerald-400/60 font-mono">
              ${seq.costs.total_sequence_cost.toFixed(4)}
            </span>
          )}
          {seq.costs?.grok_model && (
            <span className="text-[10px] text-neutral-600">{seq.costs.grok_model}</span>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-neutral-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Image strip (always visible) */}
      <div className="px-5 pb-4">
        <div className="flex gap-2 overflow-x-auto pb-2 snap-x snap-mandatory">
          {sortedImages.map((img) => (
            <div
              key={img.id || img.image_index}
              className="relative shrink-0 w-28 md:w-36 snap-center rounded-lg overflow-hidden border border-neutral-800 hover:border-indigo-700 transition-colors cursor-pointer group"
              onClick={() => img.url && onImageClick({
                url: img.url,
                prompt: img.prompt,
                cost: img.cost,
                seed: img.seed,
                time: img.generation_time,
              })}
            >
              {img.url ? (
                <img
                  src={img.url}
                  alt={`Scene ${img.image_index + 1}`}
                  className="w-full aspect-video object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="w-full aspect-video bg-neutral-900 flex items-center justify-center">
                  <span className="text-neutral-700 text-[9px]">{t('gallery.no_image')}</span>
                </div>
              )}
              <div className="absolute top-1 left-1 bg-black/60 text-white text-[8px] px-1 py-0.5 rounded">
                {img.image_index + 1}
              </div>
            </div>
          ))}
          {/* Video thumbnail */}
          {video?.url && (
            <div className="relative shrink-0 w-28 md:w-36 snap-center rounded-lg overflow-hidden border border-purple-900/50 group">
              <video
                src={video.url}
                className="w-full aspect-video object-cover"
                muted
                loop
                onMouseEnter={(e) => (e.target as HTMLVideoElement).play()}
                onMouseLeave={(e) => { (e.target as HTMLVideoElement).pause(); (e.target as HTMLVideoElement).currentTime = 0 }}
              />
              <div className="absolute top-1 left-1 bg-purple-700/80 text-white text-[8px] px-1 py-0.5 rounded">
                VID
              </div>
            </div>
          )}
        </div>

        {/* Choice made badge */}
        {seq.choice_made && (
          <div className="flex items-center gap-2 mt-2">
            <span className="text-[10px] text-neutral-600">{t('history.choice_label')}</span>
            <span className="text-xs text-indigo-400/80 bg-indigo-950/30 px-2.5 py-1 rounded-lg">
              {seq.choice_made.text}
            </span>
          </div>
        )}
      </div>

      {/* Expanded: narration segments */}
      {isExpanded && (
        <div className="px-5 pb-5 border-t border-neutral-800 pt-4 space-y-4">
          {hasNarration ? (
            sortedImages.map((img, i) => {
              const narration = seq.narration_segments?.[img.image_index] || ''
              if (!narration) return null
              return (
                <div key={i} className="flex gap-4">
                  {img.url && (
                    <img
                      src={img.url}
                      alt=""
                      className="w-24 h-16 object-cover rounded-lg shrink-0 border border-neutral-800"
                    />
                  )}
                  <p className="text-sm md:text-sm text-neutral-300 leading-relaxed flex-1 break-words">
                    {narration}
                  </p>
                </div>
              )
            })
          ) : (
            <p className="text-xs text-neutral-600 italic">{t('history.no_narration')}</p>
          )}

          {/* Choices offered */}
          {seq.choices_offered?.length > 0 && (
            <div className="space-y-1.5 mt-3">
              <span className="text-[10px] text-neutral-600 uppercase tracking-wider">{t('history.choices_offered')}</span>
              {seq.choices_offered.map((c) => (
                <div
                  key={c.id}
                  className={`text-xs px-3 py-2 rounded-lg border ${
                    seq.choice_made?.id === c.id
                      ? 'border-indigo-700 bg-indigo-950/30 text-indigo-300'
                      : 'border-neutral-800 text-neutral-500'
                  }`}
                >
                  <span className="font-mono mr-2">{c.id.toUpperCase()}</span>
                  {c.text}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
