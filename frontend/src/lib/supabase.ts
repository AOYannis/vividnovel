import { createClient, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

export const supabaseEnabled = !!(supabaseUrl && supabaseAnonKey)

export const supabase: SupabaseClient = supabaseEnabled
  ? createClient(supabaseUrl, supabaseAnonKey)
  : (null as unknown as SupabaseClient) // Will never be called if !supabaseEnabled
