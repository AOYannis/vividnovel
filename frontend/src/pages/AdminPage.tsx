import { useEffect, useState } from 'react'
import { fetchAdminCosts } from '../api/client'
import { useGameStore } from '../stores/gameStore'

interface UserCosts {
  user_id: string
  sessions: { player_name: string; cost: number; sequences: number; updated_at: string }[]
  total_cost: number
  total_sequences: number
  session_count: number
}

interface CostsData {
  grand_total: number
  total_sessions: number
  total_sequences: number
  total_users: number
  users: UserCosts[]
}

export default function AdminPage() {
  const reset = useGameStore((s) => s.reset)
  const [data, setData] = useState<CostsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchAdminCosts()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-neutral-700 border-t-indigo-500 rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || 'No data'}</p>
          <button onClick={reset} className="text-indigo-400 hover:text-indigo-300 text-sm">Retour</button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="sticky top-0 z-30 bg-neutral-950/90 backdrop-blur-sm border-b border-neutral-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">
              <span className="text-indigo-400">Graph</span>
              <span className="text-purple-400">Bun</span>
              <span className="text-red-400 text-sm font-normal ml-3">Admin</span>
            </h1>
          </div>
          <button onClick={reset} className="text-sm px-4 py-2 rounded-lg bg-neutral-900 text-neutral-400 hover:text-neutral-200 transition-colors">
            Retour
          </button>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
        {/* Grand totals */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="text-xs text-neutral-500 uppercase tracking-wider">Total cost</div>
            <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">${data.grand_total.toFixed(4)}</div>
          </div>
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="text-xs text-neutral-500 uppercase tracking-wider">Users</div>
            <div className="text-2xl font-bold text-indigo-400 mt-1">{data.total_users}</div>
          </div>
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="text-xs text-neutral-500 uppercase tracking-wider">Sessions</div>
            <div className="text-2xl font-bold text-purple-400 mt-1">{data.total_sessions}</div>
          </div>
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="text-xs text-neutral-500 uppercase tracking-wider">Sequences</div>
            <div className="text-2xl font-bold text-neutral-300 mt-1">{data.total_sequences}</div>
          </div>
        </div>

        {/* Per-user breakdown */}
        <div className="space-y-4">
          <h2 className="text-sm font-medium text-neutral-400">Par utilisateur</h2>
          {data.users.map((u) => (
            <div key={u.user_id} className="bg-neutral-900 rounded-xl border border-neutral-800 p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <span className="text-xs font-mono text-neutral-500">{u.user_id.slice(0, 8)}...</span>
                  <span className="text-xs text-neutral-600 ml-2">{u.session_count} sessions, {u.total_sequences} seq</span>
                </div>
                <span className="text-sm font-bold text-emerald-400 font-mono">${u.total_cost.toFixed(4)}</span>
              </div>
              <div className="space-y-1">
                {u.sessions.map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-xs bg-neutral-950 rounded px-3 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-neutral-300">{s.player_name}</span>
                      <span className="text-neutral-600">seq.{s.sequences}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-emerald-400/60 font-mono">${s.cost.toFixed(4)}</span>
                      <span className="text-neutral-700 text-[10px]">
                        {new Date(s.updated_at).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
