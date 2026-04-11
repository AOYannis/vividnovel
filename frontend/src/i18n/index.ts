import { create } from 'zustand'
import translations from './translations'

interface I18nState {
  locale: string
  setLocale: (locale: string) => void
}

// Persist locale in localStorage
const savedLocale = typeof window !== 'undefined'
  ? localStorage.getItem('graphbun_locale') || 'fr'
  : 'fr'

export const useI18n = create<I18nState>((set) => ({
  locale: savedLocale,
  setLocale: (locale: string) => {
    localStorage.setItem('graphbun_locale', locale)
    set({ locale })
  },
}))

/**
 * Translate a key. Falls back to French, then returns the key itself.
 */
export function t(key: string, locale?: string): string {
  const lang = locale || useI18n.getState().locale
  return translations[lang]?.[key] || translations['fr']?.[key] || key
}

/**
 * React hook for translations. Re-renders when locale changes.
 */
export function useT() {
  const locale = useI18n((s) => s.locale)
  return (key: string) => translations[locale]?.[key] || translations['fr']?.[key] || key
}

/** Available UI languages (subset with good coverage) */
export const UI_LANGUAGES = [
  { code: 'fr', label: 'Francais' },
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Espanol' },
  { code: 'de', label: 'Deutsch' },
  { code: 'ja', label: '日本語' },
]
