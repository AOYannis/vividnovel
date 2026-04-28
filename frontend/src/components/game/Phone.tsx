import { useState, useRef, useEffect } from 'react'
import { useGameStore } from '../../stores/gameStore'
import { useT } from '../../i18n'
import { streamPhoneChat, fetchWorld } from '../../api/client'
import type { KnownWhereabout } from '../../api/types'

const AVATARS: Record<string, string> = {
  nataly: '👩‍🦰', shorty_asian: '👩‍🦱', blonde_cacu: '👱‍♀️',
  korean: '👩', woman041: '👩‍🦳', white_short: '👩‍🦲',
  ciri: '⚔️', yennefer: '🔮',
}

function charAvatar(code: string) { return AVATARS[code] || '👤' }

const RELATIONSHIP_LEVELS = [
  { label: 'stranger', emoji: '👋', color: 'text-neutral-500', bg: 'bg-neutral-800' },
  { label: 'acquaintance', emoji: '🙂', color: 'text-blue-400', bg: 'bg-blue-950/40' },
  { label: 'flirting', emoji: '😏', color: 'text-pink-400', bg: 'bg-pink-950/40' },
  { label: 'close', emoji: '💗', color: 'text-rose-400', bg: 'bg-rose-950/40' },
  { label: 'intimate', emoji: '🔥', color: 'text-orange-400', bg: 'bg-orange-950/40' },
  { label: 'lover', emoji: '❤️', color: 'text-red-400', bg: 'bg-red-950/40' },
]

function RelationshipBadge({ level, encounters }: { level: number; encounters: number }) {
  const r = RELATIONSHIP_LEVELS[Math.min(Math.max(level, 0), 5)]
  return (
    <div className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${r.bg}`}>
      <span className="text-[10px]">{r.emoji}</span>
      <span className={`text-[9px] font-mono ${r.color}`}>{r.label}</span>
      {encounters > 0 && <span className="text-[9px] text-white/30">·{encounters}</span>}
    </div>
  )
}

interface PhoneProps {
  /** When provided, shows a session switcher (used when phone is opened from the home page) */
  sessionSwitcher?: {
    sessions: { id: string; label: string }[]
    current: string | null
    onSwitch: (sessionId: string) => void
  }
  /** Override the default close behavior — used by the home page to also unmount the overlay */
  onCloseAll?: () => void
}

export default function Phone({ sessionSwitcher, onCloseAll }: PhoneProps = {}) {
  const t = useT()
  const {
    phoneOpen, phoneActiveChar, phoneChats, metCharacters, sessionId, characterNames, relationships,
  } = useGameStore()
  const [showSwitcher, setShowSwitcher] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [selfieLoading, setSelfieLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Story name (from Grok) → fallback to codename
  const charName = (code: string) => characterNames[code] || code

  // Auto-scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [phoneChats, phoneActiveChar, streamingText])

  if (!phoneOpen) return null

  const setPhoneOpen = (open: boolean) => useGameStore.setState({ phoneOpen: open })
  const setActiveChar = (code: string | null) => useGameStore.setState({ phoneActiveChar: code })

  const messages = phoneActiveChar ? (phoneChats[phoneActiveChar] || []) : []

  const handleSend = async () => {
    if (!input.trim() || !sessionId || !phoneActiveChar || loading) return
    const msg = input.trim()
    setInput('')
    setLoading(true)
    setStreamingText('')

    // Add user message
    const store = useGameStore.getState()
    const prev = store.phoneChats[phoneActiveChar] || []
    useGameStore.setState({
      phoneChats: { ...store.phoneChats, [phoneActiveChar]: [...prev, { role: 'user' as const, text: msg }] },
    })

    try {
      await streamPhoneChat(
        { sessionId, characterCode: phoneActiveChar, message: msg },
        {
          onMessageDelta: (text) => setStreamingText((s) => s + text),
          onMessageDone: (text) => {
            setStreamingText('')
            const s = useGameStore.getState()
            const msgs = s.phoneChats[phoneActiveChar!] || []
            useGameStore.setState({
              phoneChats: { ...s.phoneChats, [phoneActiveChar!]: [...msgs, { role: 'character' as const, text }] },
            })
          },
          onSelfieGenerating: () => setSelfieLoading(true),
          onSelfieReady: (url) => {
            setSelfieLoading(false)
            const s = useGameStore.getState()
            const msgs = s.phoneChats[phoneActiveChar!] || []
            useGameStore.setState({
              phoneChats: { ...s.phoneChats, [phoneActiveChar!]: [...msgs, { role: 'character' as const, text: '', imageUrl: url }] },
            })
          },
          onRendezvousAdded: (rdv: KnownWhereabout) => {
            // Inline confirmation chip in the chat thread
            const s = useGameStore.getState()
            const msgs = s.phoneChats[phoneActiveChar!] || []
            useGameStore.setState({
              phoneChats: { ...s.phoneChats, [phoneActiveChar!]: [...msgs, { role: 'system' as const, text: '', rendezvous: rdv }] },
            })
            // Refresh world payload so the map / agenda / RDV badges update.
            // Also picks up any new_location proposals tied to the rdv.
            if (sessionId) fetchWorld(sessionId).then((p) => useGameStore.getState().setWorldPayload(p)).catch(() => {})
          },
          onError: (error) => { console.error('Phone chat error:', error) },
        },
      )
    } catch (e) {
      console.error('Phone chat failed:', e)
    } finally {
      setLoading(false)
      setSelfieLoading(false)
    }
  }

  const handleClose = () => {
    if (onCloseAll) {
      onCloseAll()
    } else {
      setPhoneOpen(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={handleClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Phone frame */}
      <div
        className="relative w-full max-w-sm h-[80dvh] max-h-[700px] bg-neutral-950 rounded-[2rem] border border-neutral-800 shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Notch */}
        <div className="flex justify-center pt-2 pb-1">
          <div className="w-20 h-1 rounded-full bg-neutral-800" />
        </div>

        {phoneActiveChar ? (
          /* ── Chat thread ── */
          <>
            {/* Chat header */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-neutral-800">
              <button
                onClick={() => setActiveChar(null)}
                className="text-white/50 hover:text-white text-lg"
              >
                ←
              </button>
              <span className="text-lg">{charAvatar(phoneActiveChar)}</span>
              <div className="flex flex-col min-w-0">
                <span className="text-sm font-medium text-neutral-200 truncate">
                  {charName(phoneActiveChar)}
                </span>
                {relationships[phoneActiveChar] && (
                  <RelationshipBadge
                    level={relationships[phoneActiveChar].level}
                    encounters={relationships[phoneActiveChar].encounters}
                  />
                )}
              </div>
              <div className="flex-1" />
              <div className="w-2 h-2 rounded-full bg-emerald-400" />
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 no-scrollbar">
              {messages.length === 0 && !streamingText && (
                <p className="text-center text-neutral-600 text-xs py-8">
                  Start a conversation...
                </p>
              )}
              {messages.map((msg, i) => {
                // System row: rendez-vous confirmation chip, centered, distinct style.
                if (msg.role === 'system' && msg.rendezvous) {
                  const r = msg.rendezvous
                  const world = useGameStore.getState().world
                  const loc = world?.locations.find((l) => l.id === r.location_id)
                  const SLOT_FR: Record<string, string> = { morning: 'matin', afternoon: 'après-midi', evening: 'soir', night: 'nuit' }
                  const slotLabel = SLOT_FR[r.slot] || r.slot
                  const dayLabel = world && r.day === world.day ? "aujourd'hui" : `J${r.day}`
                  return (
                    <div key={i} className="flex justify-center">
                      <div className="max-w-[90%] rounded-xl px-3 py-2 bg-rose-950/40 border border-rose-800/50 text-rose-100">
                        <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-rose-300/80 mb-1">
                          <span>⏰</span>
                          <span>Rendez-vous noté</span>
                        </div>
                        <div className="text-xs leading-snug">
                          {dayLabel} · {slotLabel}
                          {loc && (<> · <span className="font-medium">{loc.name}</span></>)}
                        </div>
                        {r.source && (
                          <div className="text-[10px] text-rose-300/60 italic mt-0.5">« {r.source} »</div>
                        )}
                      </div>
                    </div>
                  )
                }
                return (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 ${
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white'
                        : 'bg-neutral-800 text-neutral-200'
                    }`}>
                      {msg.imageUrl && (
                        <img
                          src={msg.imageUrl}
                          alt=""
                          className="rounded-xl mb-2 w-full max-w-[200px]"
                        />
                      )}
                      {msg.text && (
                        <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                      )}
                    </div>
                  </div>
                )
              })}
              {/* Streaming indicator */}
              {streamingText && (
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-2xl px-3.5 py-2.5 bg-neutral-800 text-neutral-200">
                    <p className="text-sm leading-relaxed typing-cursor">{streamingText}</p>
                  </div>
                </div>
              )}
              {selfieLoading && (
                <div className="flex justify-start">
                  <div className="rounded-2xl px-3.5 py-2.5 bg-neutral-800">
                    <div className="w-32 h-40 shimmer rounded-xl" />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t border-neutral-800">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && input.trim()) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  placeholder="Message..."
                  disabled={loading}
                  className="flex-1 bg-neutral-900 border border-neutral-800 rounded-full px-4 py-2.5 text-sm text-white focus:border-indigo-500 focus:outline-none placeholder-neutral-600 disabled:opacity-50"
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || loading}
                  className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 w-10 h-10 rounded-full flex items-center justify-center text-white transition-colors shrink-0"
                >
                  {loading ? (
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </>
        ) : (
          /* ── Contact list ── */
          <>
            <div className="px-4 py-3 border-b border-neutral-800 relative">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium text-neutral-300">Messages</h2>
                {sessionSwitcher && sessionSwitcher.sessions.length > 1 && (
                  <button
                    onClick={() => setShowSwitcher(!showSwitcher)}
                    className="text-[10px] text-neutral-500 hover:text-neutral-200 transition-colors flex items-center gap-1"
                  >
                    {sessionSwitcher.sessions.find((s) => s.id === sessionSwitcher.current)?.label?.slice(0, 24) || 'Switch story'}
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                )}
              </div>
              {showSwitcher && sessionSwitcher && (
                <div className="absolute top-full right-2 mt-1 z-10 bg-neutral-900 border border-neutral-800 rounded-lg shadow-2xl py-1 max-w-[280px] max-h-[60vh] overflow-y-auto">
                  {sessionSwitcher.sessions.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => { sessionSwitcher.onSwitch(s.id); setShowSwitcher(false) }}
                      className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                        s.id === sessionSwitcher.current
                          ? 'bg-indigo-950/50 text-indigo-300'
                          : 'text-neutral-300 hover:bg-neutral-800'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="flex-1 overflow-y-auto">
              {metCharacters.length === 0 ? (
                <p className="text-center text-neutral-600 text-xs py-12">
                  No contacts yet — meet characters in the story first.
                </p>
              ) : (
                metCharacters.map((code) => {
                  const msgs = phoneChats[code] || []
                  const lastMsg = msgs[msgs.length - 1]
                  const unread = lastMsg?.role === 'character'
                  return (
                    <button
                      key={code}
                      onClick={() => setActiveChar(code)}
                      className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-neutral-900/50 transition-colors border-b border-neutral-800/50"
                    >
                      <span className="text-2xl">{charAvatar(code)}</span>
                      <div className="flex-1 text-left min-w-0">
                        <div className="flex items-center gap-2">
                          <div className="text-sm font-medium text-neutral-200 truncate">{charName(code)}</div>
                          {relationships[code] && (
                            <RelationshipBadge
                              level={relationships[code].level}
                              encounters={relationships[code].encounters}
                            />
                          )}
                        </div>
                        {lastMsg && (
                          <p className="text-xs text-neutral-500 truncate mt-0.5">
                            {lastMsg.rendezvous
                              ? '⏰ Rendez-vous noté'
                              : lastMsg.imageUrl
                              ? '📷 Photo'
                              : lastMsg.text?.slice(0, 40)}
                          </p>
                        )}
                      </div>
                      {unread && <div className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" />}
                    </button>
                  )
                })
              )}
            </div>
          </>
        )}

        {/* Home bar */}
        <div className="flex justify-center py-2">
          <div className="w-28 h-1 rounded-full bg-neutral-700" />
        </div>
      </div>
    </div>
  )
}
