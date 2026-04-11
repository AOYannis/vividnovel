// Local user profile — defaults for the new-story form
// Persisted in localStorage so the player doesn't have to re-enter their info.

export interface UserProfile {
  name: string
  age: number
  gender: string  // 'homme' | 'femme' | 'custom' | <free text>
  customGender?: string
  preferences: string  // 'femmes' | 'hommes' | 'custom' | <free text>
  customPreferences?: string
  language: string  // 'fr' | 'en' | etc.
}

const STORAGE_KEY = 'graphbun_user_profile'

export const DEFAULT_PROFILE: UserProfile = {
  name: '',
  age: 28,
  gender: 'homme',
  preferences: 'femmes',
  language: 'fr',
}

export function loadProfile(): UserProfile {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_PROFILE }
    const parsed = JSON.parse(raw)
    return { ...DEFAULT_PROFILE, ...parsed }
  } catch {
    return { ...DEFAULT_PROFILE }
  }
}

export function saveProfile(profile: UserProfile): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
  } catch { /* ignore quota errors */ }
}

export function hasProfile(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw)
    return !!parsed.name && !!parsed.age
  } catch {
    return false
  }
}
