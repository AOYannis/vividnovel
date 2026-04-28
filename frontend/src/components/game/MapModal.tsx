import { useEffect, useState } from 'react'
import { fetchWorld, goToLocation } from '../../api/client'
import { useGameStore } from '../../stores/gameStore'
import { useT } from '../../i18n'
import type { Location, WorldState, WorldSlot, KnownWhereabout } from '../../api/types'

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
  const t = useT()
  const SLOT_LABEL: Record<WorldSlot, string> = {
    morning: t('map.slot.morning'),
    afternoon: t('map.slot.afternoon'),
    evening: t('map.slot.evening'),
    night: t('map.slot.night'),
  }
  const world = useGameStore((s) => s.world)
  const sessionId = useGameStore((s) => s.sessionId)
  const characterStates = useGameStore((s) => s.characterStates)
  const knownWhereabouts = useGameStore((s) => s.knownWhereabouts)
  const presenceNow = useGameStore((s) => s.presenceNow)
  const characterNames = useGameStore((s) => s.characterNames)
  const upcomingRendezvous = useGameStore((s) => s.upcomingRendezvous)
  const setWorldPayload = useGameStore((s) => s.setWorldPayload)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState('')
  // Card fade-in: open → map shows immediately → ~280ms later the card itself
  // fades in. Reset to false on close so re-opens replay the animation.
  const [cardVisible, setCardVisible] = useState(false)

  // Refresh world payload when modal opens — picks up any new whereabouts the
  // post-sequence extractor added since the user last looked.
  useEffect(() => {
    if (open && sessionId && world) {
      fetchWorld(sessionId).then(setWorldPayload).catch(() => {})
    }
  }, [open, sessionId])

  useEffect(() => {
    if (!open) { setCardVisible(false); return }
    // Tiny delay so the user perceives "map first, then card" — long enough
    // for the eye to register the illustration, short enough not to feel slow.
    const id = window.setTimeout(() => setCardVisible(true), 280)
    return () => window.clearTimeout(id)
  }, [open])

  if (!open) return null
  if (!world || !sessionId) {
    return (
      <div className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center" onClick={onClose}>
        <div className="bg-neutral-950 border border-neutral-800 rounded-2xl p-6 text-neutral-400 text-sm">
          {t('map.not_active')}
          <button onClick={onClose} className="block mt-3 text-amber-500 hover:text-amber-400">{t('map.close')}</button>
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

  const mapBgUrl = world.map_background_url || ''

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 overflow-hidden" onClick={onClose}>
      {/* Full-viewport map background — replaces the usual black overlay. */}
      {mapBgUrl ? (
        <>
          <img
            src={mapBgUrl}
            alt=""
            aria-hidden
            className="absolute inset-0 w-full h-full object-cover"
          />
          {/* Darkening scrim over the map for card legibility + click-through-to-close */}
          <div className="absolute inset-0 bg-black/55 backdrop-blur-[2px]" />
        </>
      ) : (
        <div className="absolute inset-0 bg-black/85 backdrop-blur-sm" />
      )}
      <div
        className={`relative z-10 bg-neutral-950/85 backdrop-blur-md border border-neutral-800 rounded-2xl w-full max-w-md max-h-[90vh] overflow-hidden flex transition-all duration-500 ease-out ${
          cardVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Scrollable content */}
        <div className="relative z-10 w-full overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-neutral-950/85 backdrop-blur-md border-b border-neutral-800 px-4 py-3 flex items-center justify-between">
          <div>
            <div className="text-xs text-neutral-500 uppercase tracking-wider">{t('map.title')}</div>
            <div className="text-sm text-neutral-200 font-mono">
              {t('map.day')} {world.day} · {SLOT_ICON[world.slot]} {SLOT_LABEL[world.slot]}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-500 hover:text-neutral-200 text-2xl leading-none px-2"
            aria-label={t('map.close')}
          >
            ×
          </button>
        </div>

        {/* Imminent rendez-vous teaser — top of modal so the player sees it first */}
        {upcomingRendezvous && upcomingRendezvous.some((r) => r.status === 'now' || r.status === 'next') && (
          <div className="px-4 pt-3 pb-1">
            <div className="text-[10px] text-rose-400/80 uppercase tracking-wider mb-1.5 font-mono">
              ⏰ {t('map.rdv')}
            </div>
            <div className="space-y-1.5">
              {upcomingRendezvous.filter((r) => r.status === 'now' || r.status === 'next').map((r, i) => {
                const loc = world.locations.find((l) => l.id === r.location_id)
                const statusLabel = r.status === 'now' ? t('map.rdv_now') : t('map.rdv_next')
                const statusColor = r.status === 'now'
                  ? 'border-rose-500/50 bg-rose-950/30 text-rose-200'
                  : 'border-amber-700/40 bg-amber-950/20 text-amber-200'
                return (
                  <div
                    key={`rdv-now-${r.char}-${r.day}-${r.slot}-${i}`}
                    className={`text-[11px] border rounded px-3 py-2 ${statusColor}`}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[9px] uppercase tracking-wider opacity-80">{statusLabel}</span>
                      <span className="text-neutral-400">{t('map.rdv_with')}</span>
                      <span className="font-mono font-semibold">{shortName(r.char, characterNames)}</span>
                      <span className="text-neutral-500">·</span>
                      <span>{loc?.name || r.location_id}</span>
                    </div>
                    {r.source && (
                      <div className="text-[10px] opacity-70 italic mt-0.5">« {r.source} »</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Locations */}
        <div className="p-4 space-y-2">
          <p className="text-[11px] text-neutral-500 mb-3">
            {t('map.pick_location')}{' '}
            <span className="text-amber-400">{SLOT_LABEL[upcomingSlot]}</span>.
          </p>
          {world.locations.map((loc) => {
            const isCurrent = loc.id === world.current_location
            const isPending = pending === loc.id
            // Likely-present characters at this location right now (resolver output)
            const charsHere = (presenceNow[loc.id] || []).filter((c) => c in characterStates)
            // Rendez-vous with status that target THIS location (any future status)
            const rdvHere = (upcomingRendezvous || []).filter((r) => r.location_id === loc.id)
            const hasImminentRdv = rdvHere.some((r) => r.status === 'now' || r.status === 'next')
            return (
              <button
                key={loc.id}
                onClick={() => handlePick(loc)}
                disabled={!!pending}
                className={`w-full text-left rounded-xl border px-4 py-3 transition-colors ${
                  isCurrent
                    ? 'border-amber-700/50 bg-amber-950/20 text-amber-300'
                    : hasImminentRdv
                      ? 'border-rose-700/50 bg-rose-950/15 text-neutral-200 hover:border-rose-600/70 hover:bg-rose-950/30 disabled:opacity-40 disabled:cursor-not-allowed'
                      : 'border-neutral-800 bg-neutral-900 text-neutral-200 hover:border-emerald-800/50 hover:bg-emerald-950/20 disabled:opacity-40 disabled:cursor-not-allowed'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-xl">{TYPE_ICON[loc.type] || TYPE_ICON.other}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium flex items-center gap-2 flex-wrap">
                      {loc.name}
                      {isCurrent && <span className="text-[9px] uppercase tracking-wider text-amber-500">{t('map.you_are_here')}</span>}
                      {hasImminentRdv && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-900/50 text-rose-200 border border-rose-700/50 font-mono uppercase tracking-wider">
                          ⏰ {t('map.rdv')}
                        </span>
                      )}
                      {charsHere.map((c) => (
                        <span
                          key={c}
                          className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-800/40 font-mono"
                          title={isCurrent
                            ? `${shortName(c, characterNames)} ${t('map.character_here_tooltip')}`
                            : `${shortName(c, characterNames)} ${t('map.character_on_arrival_tooltip')}`}
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
              {t('map.agenda_title')}
            </div>
            <div className="space-y-1.5">
              {futureWhereabouts.map((w, i) => {
                const loc = world.locations.find((l) => l.id === w.location_id)
                const dayLabel = w.day === world.day ? t('map.agenda_today') : `${t('map.agenda_day_short')}${w.day}`
                const isRdv = !!w.is_rendezvous
                return (
                  <div
                    key={`${w.char}-${w.day}-${w.slot}-${w.location_id}-${i}`}
                    className={`text-[11px] rounded px-3 py-1.5 ${
                      isRdv
                        ? 'text-rose-200 bg-rose-950/25 border border-rose-800/40'
                        : 'text-neutral-400 bg-neutral-900/60 border border-neutral-800/60'
                    }`}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      {isRdv && <span className="text-[9px] uppercase tracking-wider text-rose-400/80 font-mono">⏰ {t('map.rdv')}</span>}
                      <span className={isRdv ? 'text-rose-300 font-mono' : 'text-emerald-400 font-mono'}>{shortName(w.char, characterNames)}</span>
                      <span className="text-neutral-600">·</span>
                      <span>{dayLabel} {SLOT_LABEL[w.slot]}</span>
                      <span className="text-neutral-600">·</span>
                      <span className={isRdv ? 'text-rose-100' : 'text-neutral-300'}>{loc?.name || w.location_id}</span>
                    </div>
                    {w.source && (
                      <div className={`text-[10px] italic mt-0.5 ${isRdv ? 'text-rose-300/70' : 'text-neutral-600'}`}>« {w.source} »</div>
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
            <div className="text-[10px] text-neutral-600 uppercase tracking-wider mb-1">{t('map.history_title')}</div>
            <div className="text-[11px] text-neutral-500 font-mono space-y-0.5">
              {world.history.slice(-5).reverse().map((h, i) => {
                const loc = world.locations.find((l) => l.id === h.location)
                return (
                  <div key={i}>
                    {t('map.agenda_day_short')}{h.day} · {SLOT_LABEL[h.slot]} · {loc?.name || h.location}
                  </div>
                )
              })}
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
