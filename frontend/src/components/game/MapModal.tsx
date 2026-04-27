import { useEffect, useState } from 'react'
import { fetchWorld, goToLocation } from '../../api/client'
import { useGameStore } from '../../stores/gameStore'
import type { Location, WorldState, WorldSlot, KnownWhereabout } from '../../api/types'

const SLOT_LABEL: Record<WorldSlot, string> = {
  morning: 'matin',
  afternoon: 'après-midi',
  evening: 'soir',
  night: 'nuit',
}

const SLOT_ICON: Record<WorldSlot, string> = {
  morning: '☀',
  afternoon: '◐',
  evening: '☾',
  night: '★',
}

const TYPE_ICON: Record<string, string> = {
  home: '⌂',
  cafe: '☕',
  bar: '◆',
  club: '♬',
  gym: '◊',
  park: '☘',
  work: '▲',
  salon: '✦',
  other: '○',
}

function nextSlot(slot: WorldSlot): WorldSlot {
  const order: WorldSlot[] = ['morning', 'afternoon', 'evening', 'night']
  return order[(order.indexOf(slot) + 1) % order.length]
}

function shortName(charCode: string, charNames: Record<string, string>): string {
  // Prefer the in-story display name (the prénom Grok invented), fallback to the codename
  return charNames[charCode] || charCode
}

function compareWhereabouts(a: KnownWhereabout, b: KnownWhereabout): number {
  if (a.day !== b.day) return a.day - b.day
  const order: WorldSlot[] = ['morning', 'afternoon', 'evening', 'night']
  return order.indexOf(a.slot) - order.indexOf(b.slot)
}

interface MapModalProps {
  open: boolean
  onClose: () => void
  /** Called after the location has been switched, with the new world state. The
   *  parent should then trigger a fresh sequence to play out the visit. */
  onMoved?: (world: WorldState) => void
}

export default function MapModal({ open, onClose, onMoved }: MapModalProps) {
  const world = useGameStore((s) => s.world)
  const sessionId = useGameStore((s) => s.sessionId)
  const characterStates = useGameStore((s) => s.characterStates)
  const knownWhereabouts = useGameStore((s) => s.knownWhereabouts)
  const presenceNow = useGameStore((s) => s.presenceNow)
  const characterNames = useGameStore((s) => s.characterNames)
  const setWorldPayload = useGameStore((s) => s.setWorldPayload)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState('')

  // Refresh world payload when modal opens — picks up any new whereabouts the
  // post-sequence extractor added since the user last looked.
  useEffect(() => {
    if (open && sessionId && world) {
      fetchWorld(sessionId).then(setWorldPayload).catch(() => {})
    }
  }, [open, sessionId])

  if (!open) return null
  if (!world || !sessionId) {
    return (
      <div className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center" onClick={onClose}>
        <div className="bg-neutral-950 border border-neutral-800 rounded-2xl p-6 text-neutral-400 text-sm">
          Slice-of-life mode is not active for this session.
          <button onClick={onClose} className="block mt-3 text-amber-500 hover:text-amber-400">Close</button>
        </div>
      </div>
    )
  }

  const handlePick = async (loc: Location) => {
    if (pending) return
    if (loc.id === world.current_location) {
      onClose()
      return
    }
    setPending(loc.id)
    setError('')
    try {
      const payload = await goToLocation({ session_id: sessionId, location_id: loc.id })
      setWorldPayload(payload)
      onClose()
      if (payload.world) onMoved?.(payload.world)
    } catch (e: any) {
      setError(e.message || 'Move failed')
    } finally {
      setPending(null)
    }
  }

  const upcomingSlot = nextSlot(world.slot)

  // Group future whereabouts (day,slot >= now) by location for the agenda view
  const futureWhereabouts = knownWhereabouts
    .filter((w) => {
      if (w.day > world.day) return true
      if (w.day < world.day) return false
      const order: WorldSlot[] = ['morning', 'afternoon', 'evening', 'night']
      return order.indexOf(w.slot) >= order.indexOf(world.slot)
    })
    .sort(compareWhereabouts)
    .slice(0, 8)

  return (
    <div className="fixed inset-0 z-[100] bg-black/85 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-neutral-950 border border-neutral-800 rounded-2xl w-full max-w-md max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-neutral-950/95 backdrop-blur-sm border-b border-neutral-800 px-4 py-3 flex items-center justify-between">
          <div>
            <div className="text-xs text-neutral-500 uppercase tracking-wider">Carte</div>
            <div className="text-sm text-neutral-200 font-mono">
              Jour {world.day} · {SLOT_ICON[world.slot]} {SLOT_LABEL[world.slot]}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-500 hover:text-neutral-200 text-2xl leading-none px-2"
            aria-label="Fermer"
          >
            ×
          </button>
        </div>

        {/* Locations */}
        <div className="p-4 space-y-2">
          <p className="text-[11px] text-neutral-500 mb-3">
            Choisis un lieu où aller. Le temps avance d'un cran : prochain moment ={' '}
            <span className="text-amber-400">{SLOT_LABEL[upcomingSlot]}</span>.
          </p>
          {world.locations.map((loc) => {
            const isCurrent = loc.id === world.current_location
            const isPending = pending === loc.id
            // Likely-present characters at this location right now (resolver output)
            const charsHere = (presenceNow[loc.id] || []).filter((c) => c in characterStates)
            return (
              <button
                key={loc.id}
                onClick={() => handlePick(loc)}
                disabled={!!pending}
                className={`w-full text-left rounded-xl border px-4 py-3 transition-colors ${
                  isCurrent
                    ? 'border-amber-700/50 bg-amber-950/20 text-amber-300'
                    : 'border-neutral-800 bg-neutral-900 text-neutral-200 hover:border-emerald-800/50 hover:bg-emerald-950/20 disabled:opacity-40 disabled:cursor-not-allowed'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-xl">{TYPE_ICON[loc.type] || TYPE_ICON.other}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium flex items-center gap-2 flex-wrap">
                      {loc.name}
                      {isCurrent && <span className="text-[9px] uppercase tracking-wider text-amber-500">tu es ici</span>}
                      {charsHere.map((c) => (
                        <span
                          key={c}
                          className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-800/40 font-mono"
                          title={`${shortName(c, characterNames)} est probablement ici en ce moment`}
                        >
                          {shortName(c, characterNames)}
                        </span>
                      ))}
                    </div>
                    {loc.description && (
                      <div className="text-[11px] text-neutral-500 mt-0.5 line-clamp-2">{loc.description}</div>
                    )}
                  </div>
                  {isPending && (
                    <span className="text-amber-400 text-xs">…</span>
                  )}
                </div>
              </button>
            )
          })}
          {error && (
            <div className="mt-3 p-2 bg-red-950/30 border border-red-900/40 rounded text-xs text-red-400">{error}</div>
          )}
        </div>

        {/* Agenda — what the player has been TOLD about future whereabouts */}
        {futureWhereabouts.length > 0 && (
          <div className="px-4 pb-4">
            <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5">
              Agenda — ce qu'on t'a dit
            </div>
            <div className="space-y-1.5">
              {futureWhereabouts.map((w, i) => {
                const loc = world.locations.find((l) => l.id === w.location_id)
                const dayLabel = w.day === world.day ? "aujourd'hui" : `J${w.day}`
                return (
                  <div
                    key={`${w.char}-${w.day}-${w.slot}-${w.location_id}-${i}`}
                    className="text-[11px] text-neutral-400 bg-neutral-900/60 border border-neutral-800/60 rounded px-3 py-1.5"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-emerald-400 font-mono">{shortName(w.char, characterNames)}</span>
                      <span className="text-neutral-600">·</span>
                      <span>{dayLabel} {SLOT_LABEL[w.slot]}</span>
                      <span className="text-neutral-600">·</span>
                      <span className="text-neutral-300">{loc?.name || w.location_id}</span>
                    </div>
                    {w.source && (
                      <div className="text-[10px] text-neutral-600 italic mt-0.5">« {w.source} »</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Recent history */}
        {world.history && world.history.length > 0 && (
          <div className="px-4 pb-4">
            <div className="text-[10px] text-neutral-600 uppercase tracking-wider mb-1">Récents</div>
            <div className="text-[11px] text-neutral-500 font-mono space-y-0.5">
              {world.history.slice(-5).reverse().map((h, i) => {
                const loc = world.locations.find((l) => l.id === h.location)
                return (
                  <div key={i}>
                    J{h.day} · {SLOT_LABEL[h.slot]} · {loc?.name || h.location}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
