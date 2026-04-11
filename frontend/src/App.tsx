import { useEffect, lazy, Suspense } from 'react'
import { useAuthStore } from './stores/authStore'
import { useGameStore } from './stores/gameStore'
import AuthPage from './pages/AuthPage'
import SetupPage from './pages/SetupPage'
import GamePage from './pages/GamePage'
import GalleryPage from './pages/GalleryPage'
import HistoryPage from './pages/HistoryPage'
import AdminPage from './pages/AdminPage'

const PlaygroundPage = lazy(() => import('./pages/PlaygroundPage'))

function App() {
  const { user, loading, enabled, initialize } = useAuthStore()
  const step = useGameStore((s) => s.step)

  useEffect(() => {
    initialize()
  }, [])

  // Playground — no auth required, render before auth gate
  if (step === 'playground') {
    return (
      <Suspense fallback={<div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-neutral-700 border-t-indigo-500 rounded-full animate-spin" />
      </div>}>
        <PlaygroundPage />
      </Suspense>
    )
  }

  // Loading auth state
  if (loading) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-neutral-700 border-t-indigo-500 rounded-full animate-spin" />
      </div>
    )
  }

  // Auth required but not logged in
  if (enabled && !user) {
    return <AuthPage />
  }

  // Game flow
  if (step === 'setup') return <SetupPage />
  if (step === 'history') return <HistoryPage />
  if (step === 'gallery') return <GalleryPage />
  if (step === 'admin') return <AdminPage />
  return <GamePage />
}

export default App
