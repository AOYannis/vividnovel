import { useState, useEffect } from 'react'
import { type UserProfile, loadProfile, saveProfile } from '../lib/profile'
import { useT, useI18n, UI_LANGUAGES } from '../i18n'

interface ProfileModalProps {
  open: boolean
  onClose: () => void
  onSave?: (profile: UserProfile) => void
}

export default function ProfileModal({ open, onClose, onSave }: ProfileModalProps) {
  const t = useT()
  const { setLocale } = useI18n()
  const [profile, setProfile] = useState<UserProfile>(loadProfile())

  // Reload from storage every time the modal opens
  useEffect(() => {
    if (open) setProfile(loadProfile())
  }, [open])

  if (!open) return null

  const handleSave = () => {
    saveProfile(profile)
    setLocale(profile.language)
    onSave?.(profile)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-md bg-neutral-950 border border-neutral-800 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-neutral-800 flex items-center justify-between">
          <h2 className="text-base font-semibold text-neutral-200">{t('profile.title')}</h2>
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-200 text-xl w-8 h-8 flex items-center justify-center">&times;</button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* Name */}
          <div>
            <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">{t('setup.step1.name')}</label>
            <input
              type="text"
              value={profile.name}
              onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              placeholder={t('setup.step1.name_placeholder')}
              className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none placeholder-neutral-600"
            />
          </div>

          {/* Age + Gender + Attracted to */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">{t('setup.step1.age')}</label>
              <input
                type="number"
                value={profile.age}
                onChange={(e) => setProfile({ ...profile, age: parseInt(e.target.value) || 18 })}
                min={18}
                max={99}
                className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">{t('setup.step1.gender')}</label>
              <select
                value={profile.gender}
                onChange={(e) => setProfile({ ...profile, gender: e.target.value })}
                className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-2 py-2.5 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none"
              >
                <option value="homme">{t('setup.step1.gender.man')}</option>
                <option value="femme">{t('setup.step1.gender.woman')}</option>
                <option value="non-binaire">{t('setup.step1.gender.nb')}</option>
                <option value="custom">{t('setup.step1.gender.other')}</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">{t('setup.step1.preferences')}</label>
              <select
                value={profile.preferences}
                onChange={(e) => setProfile({ ...profile, preferences: e.target.value })}
                className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-2 py-2.5 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none"
              >
                <option value="femmes">{t('setup.step1.pref.women')}</option>
                <option value="hommes">{t('setup.step1.pref.men')}</option>
                <option value="tout le monde">{t('setup.step1.pref.everyone')}</option>
                <option value="custom">{t('setup.step1.pref.other')}</option>
              </select>
            </div>
          </div>

          {/* Custom gender */}
          {profile.gender === 'custom' && (
            <input
              type="text"
              value={profile.customGender || ''}
              onChange={(e) => setProfile({ ...profile, customGender: e.target.value })}
              placeholder={t('setup.step1.gender.custom_placeholder')}
              className="w-full bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none placeholder-neutral-600"
            />
          )}

          {/* Custom preferences */}
          {profile.preferences === 'custom' && (
            <input
              type="text"
              value={profile.customPreferences || ''}
              onChange={(e) => setProfile({ ...profile, customPreferences: e.target.value })}
              placeholder={t('setup.step1.pref.custom_placeholder')}
              className="w-full bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none placeholder-neutral-600"
            />
          )}

          {/* Language */}
          <div>
            <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">{t('profile.language')}</label>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {UI_LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => setProfile({ ...profile, language: lang.code })}
                  className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
                    profile.language === lang.code
                      ? 'bg-indigo-600 text-white'
                      : 'bg-neutral-900 text-neutral-400 hover:text-neutral-200'
                  }`}
                >
                  {lang.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-neutral-800 flex gap-2">
          <button onClick={onClose} className="flex-1 bg-neutral-900 hover:bg-neutral-800 text-neutral-300 py-2.5 rounded-lg text-sm font-medium transition-colors">
            {t('common.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={!profile.name.trim()}
            className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed text-white py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
