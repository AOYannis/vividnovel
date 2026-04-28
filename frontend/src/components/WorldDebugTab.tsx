import { useEffect, useState } from 'react'
import { useGameStore } from '../stores/gameStore'
import { fetchWorld } from '../api/client'
import type { WorldSlot } from '../api/types'

const SLOT_LABEL: Record<WorldSlot, string> = {
  morning: 'matin', afternoon: 'après-midi', evening: 'soir', night: 'nuit',
}

const SLOT_ORDER = ['morning', 'afternoon', 'evening', 'night'] as const

/** Read-only inspector for the slice-of-life world layer.
 *  Shows: clock + locations, per-character agent state (personality, job,
 *  full schedule, mood, intentions, overrides), known whereabouts, and the
 *  resolver's current presence map. */
export default function WorldDebugTab() {
  const sessionId = useGameStore((s) => s.sessionId)
  const world = useGameStore((s) => s.world)
  const characterStates = useGameStore((s) => s.characterStates)
  const knownWhereabouts = useGameStore((s) => s.knownWhereabouts)
  const presenceNow = useGameStore((s) => s.presenceNow)
  const characterNames = useGameStore((s) => s.characterNames)
  const relationships = useGameStore((s) => s.relationships)
  const setWorldPayload = useGameStore((s) => s.setWorldPayload)
  const [refreshing, setRefreshing] = useState(false)

  // Refresh on mount so the inspector is always up to date
  useEffect(() => {
    if (!sessionId) return
    setRefreshing(true)
    fetchWorld(sessionId).then(setWorldPayload).catch(() => {}).finally(() => setRefreshing(false))
  }, [sessionId])

  const handleRefresh = async () => {
    if (!sessionId) return
    setRefreshing(true)
    try {
      const payload = await fetchWorld(sessionId)
      setWorldPayload(payload)
    } finally {
      setRefreshing(false)
    }
  }

  if (!world) {
    return (
      <div className="space-y-3 text-xs text-neutral-500">
        <p className="text-center py-8">
          Slice-of-life mode is not active for this session.
        </p>
      </div>
    )
  }

  const charCodes = Object.keys(characterStates)
  const currentLoc = world.locations.find((l) => l.id === world.current_location)

  return (
    <div className="space-y-4 text-xs">
      {/* Header + refresh */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] text-neutral-500 uppercase tracking-wider">Monde</div>
          <div className="text-neutral-200 font-mono">
            Jour {world.day} · {SLOT_LABEL[world.slot]} · {currentLoc?.name || world.current_location}
          </div>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="text-[10px] px-2 py-1 rounded bg-neutral-800 text-neutral-400 hover:text-neutral-200 disabled:opacity-30"
        >
          {refreshing ? '…' : '↻'}
        </button>
      </div>

      {/* Presence map — who's where right now */}
      <div className="bg-neutral-900 rounded-lg p-3 border border-neutral-800">
        <h4 className="text-xs font-medium text-neutral-300 mb-2">Présence actuelle ({SLOT_LABEL[world.slot]})</h4>
        <div className="space-y-1">
          {world.locations.map((loc) => {
            const here = presenceNow[loc.id] || []
            return (
              <div key={loc.id} className="flex items-center justify-between gap-2 font-mono text-[11px]">
                <span className={loc.id === world.current_location ? 'text-amber-400' : 'text-neutral-500'}>
                  {loc.id}
                </span>
                <span className="text-neutral-300 text-right truncate">
                  {here.length === 0 ? <span className="text-neutral-700">—</span> : here.map((c) => characterNames[c] || c).join(', ')}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Character states */}
      {charCodes.length === 0 ? (
        <div className="bg-neutral-900 rounded-lg p-3 border border-neutral-800 text-neutral-500 italic">
          Aucun état d'agent. Les personnages n'ont pas de planning généré.
        </div>
      ) : (
        charCodes.map((code) => {
          const cs = characterStates[code]
          const display = characterNames[code] || code
          const rel = (relationships || {})[code]
          const trust = rel?.trust ?? 0
          const trustHistory = rel?.trust_history || []
          const recentEvents = cs.recent_events || []
          const tempColor = cs.temperament === 'wild' ? 'text-rose-300 bg-rose-950/40 border-rose-800/40'
            : cs.temperament === 'reserved' ? 'text-cyan-300 bg-cyan-950/40 border-cyan-800/40'
            : 'text-neutral-300 bg-neutral-800/60 border-neutral-700'
          const levelLabel = ['STRANGER','ACQUAINTANCE','FLIRTING','CLOSE','INTIMATE','LOVER'][rel?.level ?? 0] || 'STRANGER'
          return (
            <div key={code} className="bg-neutral-900 rounded-lg p-3 border border-neutral-800 space-y-2">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <h4 className="text-xs font-medium text-emerald-400">
                  {display} <span className="text-neutral-600 font-mono">({code})</span>
                </h4>
                {cs.temperament && (
                  <span className={`text-[9px] uppercase tracking-wider font-mono px-1.5 py-0.5 rounded border ${tempColor}`}>
                    {cs.temperament}
                  </span>
                )}
              </div>

              {/* Relationship snapshot — level + trust score */}
              {rel && (
                <div className="bg-neutral-950/60 border border-neutral-800/50 rounded px-2 py-1.5 text-[11px]">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-1.5">
                      <span className="text-neutral-500">Niveau</span>
                      <span className="font-mono text-amber-300">{rel.level}</span>
                      <span className="text-neutral-600">·</span>
                      <span className="text-neutral-300">{levelLabel}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-neutral-500">Trust</span>
                      <span className={`font-mono ${trust > 0 ? 'text-emerald-300' : trust < 0 ? 'text-rose-300' : 'text-neutral-400'}`}>
                        {trust > 0 ? '+' : ''}{Number(trust).toFixed(1)}
                      </span>
                    </div>
                  </div>
                  <div className="text-[10px] text-neutral-600 mt-0.5">
                    {rel.scenes} scènes · {rel.intimate_scenes} intimes · last_mood=<span className="font-mono">{rel.last_mood}</span>
                    {rel.scene_mood_floor_level !== undefined && rel.scene_mood_floor_level > 0 && (
                      <> · floor=L{rel.scene_mood_floor_level}</>
                    )}
                  </div>
                </div>
              )}

              <div className="space-y-1 text-[11px]">
                {cs.personality && (
                  <div className="flex gap-2">
                    <span className="text-neutral-500 shrink-0 w-16">Persona</span>
                    <span className="text-neutral-200">{cs.personality}</span>
                  </div>
                )}
                {cs.job && (
                  <div className="flex gap-2">
                    <span className="text-neutral-500 shrink-0 w-16">Job</span>
                    <span className="text-neutral-200">{cs.job}</span>
                  </div>
                )}
                {cs.today_mood && (
                  <div className="flex gap-2">
                    <span className="text-neutral-500 shrink-0 w-16">Humeur</span>
                    <span className="text-neutral-200">{cs.today_mood}</span>
                  </div>
                )}
                {cs.intentions_toward_player && (
                  <div className="flex gap-2">
                    <span className="text-neutral-500 shrink-0 w-16">Envers toi</span>
                    <span className="text-neutral-200">{cs.intentions_toward_player}</span>
                  </div>
                )}
              </div>

              {/* Recent off-screen events */}
              {recentEvents.length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Vie hors-scène ({recentEvents.length})</div>
                  <ul className="text-[10px] text-neutral-300 space-y-0.5">
                    {recentEvents.slice().reverse().map((e, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-neutral-600 font-mono shrink-0">J{e.day}</span>
                        <span>{e.text}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Trust delta history (most recent first) */}
              {trustHistory.length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Trust deltas ({trustHistory.length})</div>
                  <ul className="text-[10px] space-y-0.5">
                    {trustHistory.slice().reverse().slice(0, 8).map((h, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-neutral-600 font-mono shrink-0">seq{h.sequence}</span>
                        <span className={`font-mono shrink-0 w-12 ${h.applied_delta > 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                          {h.applied_delta > 0 ? '+' : ''}{h.applied_delta.toFixed(1)}
                        </span>
                        {h.level_change !== 0 && (
                          <span className="font-mono shrink-0 text-amber-300">L{h.level_change > 0 ? '↑' : '↓'}</span>
                        )}
                        <span className="text-neutral-400 italic">{h.reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Schedule grid */}
              <div className="mt-2">
                <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Emploi du temps</div>
                <table className="w-full text-[10px] font-mono">
                  <thead>
                    <tr className="text-neutral-600">
                      <th className="text-left font-normal py-0.5">slot</th>
                      <th className="text-left font-normal py-0.5">semaine</th>
                      <th className="text-left font-normal py-0.5">week-end</th>
                    </tr>
                  </thead>
                  <tbody>
                    {SLOT_ORDER.map((slot) => (
                      <tr key={slot} className={world.slot === slot ? 'text-amber-400' : 'text-neutral-300'}>
                        <td className="py-0.5">{SLOT_LABEL[slot]}</td>
                        <td className="py-0.5">{cs.schedule[`weekday_${slot}`] || <span className="text-neutral-700">—</span>}</td>
                        <td className="py-0.5">{cs.schedule[`weekend_${slot}`] || <span className="text-neutral-700">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Overrides (rendez-vous etc.) */}
              {Object.keys(cs.overrides || {}).length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1">Overrides (rendez-vous)</div>
                  <ul className="text-[10px] font-mono text-purple-300 space-y-0.5">
                    {Object.entries(cs.overrides).map(([key, loc]) => (
                      <li key={key}>{key} → {loc}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )
        })
      )}

      {/* Known whereabouts (what the player has been told) */}
      <div className="bg-neutral-900 rounded-lg p-3 border border-neutral-800">
        <h4 className="text-xs font-medium text-neutral-300 mb-2">
          Whereabouts connus du joueur ({knownWhereabouts.length})
        </h4>
        {knownWhereabouts.length === 0 ? (
          <div className="text-[11px] text-neutral-600 italic">
            Aucune info reçue jusqu'ici. Les personnages n'ont rien annoncé.
          </div>
        ) : (
          <div className="space-y-1.5 text-[10px] font-mono">
            {knownWhereabouts.map((w, i) => (
              <div key={i} className="border-l-2 border-emerald-900/40 pl-2">
                <div>
                  <span className="text-emerald-400">{characterNames[w.char] || w.char}</span>
                  <span className="text-neutral-600"> · </span>
                  <span className="text-neutral-300">J{w.day} {SLOT_LABEL[w.slot]}</span>
                  <span className="text-neutral-600"> · </span>
                  <span className="text-neutral-200">{w.location_id}</span>
                </div>
                {w.source && <div className="text-neutral-600 italic mt-0.5">« {w.source} »</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
