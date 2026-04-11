import { create } from 'zustand'
import { supabase, supabaseEnabled } from '../lib/supabase'
import { checkAdmin } from '../api/client'
import type { User, Session } from '@supabase/supabase-js'

interface AuthState {
  user: User | null
  session: Session | null
  loading: boolean
  enabled: boolean
  isAdmin: boolean
  initialize: () => Promise<void>
  signUp: (email: string, password: string) => Promise<{ error: string | null }>
  signIn: (email: string, password: string) => Promise<{ error: string | null }>
  signInWithMagicLink: (email: string) => Promise<{ error: string | null }>
  signOut: () => Promise<void>
  getAccessToken: () => string | null
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAdmin: false,
  session: null,
  loading: true,
  enabled: supabaseEnabled,

  initialize: async () => {
    if (!supabaseEnabled) {
      set({ loading: false })
      return
    }
    const { data: { session } } = await supabase.auth.getSession()
    set({ session, user: session?.user ?? null, loading: false })

    // Check admin status
    if (session) {
      checkAdmin().then(isAdmin => set({ isAdmin }))
    }

    supabase.auth.onAuthStateChange((_event, session) => {
      set({ session, user: session?.user ?? null })
      if (session) checkAdmin().then(isAdmin => set({ isAdmin }))
      else set({ isAdmin: false })
    })
  },

  signUp: async (email, password) => {
    if (!supabaseEnabled) return { error: 'Supabase not configured' }
    const { error } = await supabase.auth.signUp({ email, password })
    return { error: error?.message ?? null }
  },

  signIn: async (email, password) => {
    if (!supabaseEnabled) return { error: 'Supabase not configured' }
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error?.message ?? null }
  },

  signInWithMagicLink: async (email) => {
    if (!supabaseEnabled) return { error: 'Supabase not configured' }
    const { error } = await supabase.auth.signInWithOtp({ email })
    return { error: error?.message ?? null }
  },

  signOut: async () => {
    if (supabaseEnabled) await supabase.auth.signOut()
    set({ user: null, session: null })
  },

  getAccessToken: () => get().session?.access_token ?? null,
}))
