import { useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useT } from '../i18n'

export default function AuthPage() {
  const t = useT()
  const { signIn, signUp, signInWithMagicLink } = useAuthStore()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [magicLinkSent, setMagicLinkSent] = useState(false)
  const [signupSuccess, setSignupSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'signup') {
        const { error } = await signUp(email, password)
        if (error) {
          setError(error)
        } else {
          setSignupSuccess(true)
        }
      } else {
        const { error } = await signIn(email, password)
        if (error) setError(error)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold mb-2">
            <span className="text-indigo-400">Graph</span>
            <span className="text-purple-400">Bun</span>
          </h1>
          <p className="text-neutral-500 text-sm">Ton histoire. Tes choix.</p>
        </div>

        {signupSuccess ? (
          <div className="fade-in text-center space-y-4">
            <div className="bg-emerald-950/30 border border-emerald-800 rounded-xl p-4">
              <p className="text-emerald-400 text-sm">Compte cree !</p>
              <p className="text-neutral-400 text-xs mt-2">Verifie ton email pour confirmer ton compte, puis connecte-toi.</p>
            </div>
            <button
              onClick={() => { setSignupSuccess(false); setMode('login') }}
              className="text-indigo-400 hover:text-indigo-300 text-sm"
            >
              {t('auth.login')}
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="fade-in space-y-4">
            {/* Mode tabs */}
            <div className="flex border border-neutral-800 rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => setMode('login')}
                className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                  mode === 'login'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-neutral-900 text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {t('auth.login')}
              </button>
              <button
                type="button"
                onClick={() => setMode('signup')}
                className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                  mode === 'signup'
                    ? 'bg-purple-600 text-white'
                    : 'bg-neutral-900 text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {t('auth.signup')}
              </button>
            </div>

            <div>
              <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('auth.email')}</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-4 py-3 text-neutral-100 focus:border-indigo-500 focus:outline-none transition-colors"
              />
            </div>

            <div>
              <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('auth.password')}</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-4 py-3 text-neutral-100 focus:border-indigo-500 focus:outline-none transition-colors"
              />
            </div>

            {error && (
              <div className="text-red-400 text-sm bg-red-950/30 rounded-lg p-3">{error}</div>
            )}

            <button
              type="submit"
              disabled={loading}
              className={`w-full py-3 rounded-lg font-medium transition-all disabled:opacity-40 ${
                mode === 'login'
                  ? 'bg-indigo-600 hover:bg-indigo-500'
                  : 'bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500'
              }`}
            >
              {loading ? '...' : mode === 'login' ? t('auth.login') : t('auth.signup')}
            </button>

            {mode === 'login' && (
              <div className="border-t border-neutral-800 pt-4 mt-4">
                {magicLinkSent ? (
                  <p className="text-emerald-400 text-sm text-center">Lien envoye ! Verifie ton email.</p>
                ) : (
                  <button
                    type="button"
                    onClick={async () => {
                      if (!email) { setError('Entre ton email'); return }
                      setLoading(true)
                      const { error } = await signInWithMagicLink(email)
                      if (error) setError(error)
                      else setMagicLinkSent(true)
                      setLoading(false)
                    }}
                    disabled={loading}
                    className="w-full py-2.5 rounded-lg text-sm text-neutral-400 hover:text-neutral-200 bg-neutral-900 hover:bg-neutral-800 transition-colors disabled:opacity-40"
                  >
                    Connexion par lien magique
                  </button>
                )}
              </div>
            )}
          </form>
        )}
      </div>
    </div>
  )
}
