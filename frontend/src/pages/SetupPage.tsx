import { useState, useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useGameStore } from '../stores/gameStore'
import { useT, useI18n, UI_LANGUAGES } from '../i18n'
import { fetchActors, fetchSettings, startGame, fetchAvailableLoras, fetchDefaultStyleMoods, fetchGrokModels, fetchLanguages, previewSystemPrompt, listSessions, resumeSession, deleteSession, getSessionHistory, clearAllMemories } from '../api/client'
import type { Actor, Setting, LoraInfo, GrokModel } from '../api/types'
import ProfileModal from '../components/ProfileModal'
import Phone from '../components/game/Phone'
import { loadProfile, hasProfile } from '../lib/profile'

type SetupStep = 'home' | 'player' | 'setting' | 'cast' | 'prompt'

export default function SetupPage() {
  const store = useGameStore()
  const t = useT()
  const { locale, setLocale } = useI18n()
  const [step, setStep] = useState<SetupStep>('home')
  const [showDebug, setShowDebug] = useState(false)
  const [showProfileModal, setShowProfileModal] = useState(false)
  const [showAdvancedPrompt, setShowAdvancedPrompt] = useState(false)
  const [showHomePhone, setShowHomePhone] = useState(false)
  const [openingPhone, setOpeningPhone] = useState(false)
  const [phoneSession, setPhoneSession] = useState<{ id: string; player_name: string; setting: string } | null>(null)
  const [allLoras, setAllLoras] = useState<LoraInfo[]>([])
  const [actors, setActors] = useState<Actor[]>([])
  const [settings, setSettings] = useState<Setting[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [savedSessions, setSavedSessions] = useState<any[]>([])
  const [resuming, setResuming] = useState<string | null>(null)

  // Style moods
  const [styleMoods, setStyleMoods] = useState<Record<string, any>>({})
  const [moodsLoaded, setMoodsLoaded] = useState(false)
  const [newMoodName, setNewMoodName] = useState('')
  const [simulateVideo, setSimulateVideo] = useState(false)
  const [earlyStartVideo, setEarlyStartVideo] = useState(false)
  const [videoMode, setVideoMode] = useState<'256_10' | '256_5' | '540_5'>('256_10')
  const [videoBackend, setVideoBackend] = useState<'davinci' | 'pvideo' | 'none'>('pvideo')
  const [videoDraftMode, setVideoDraftMode] = useState(true)
  const [videoStartScene, setVideoStartScene] = useState(0)  // 0=all, 4=last 4 only
  const [pvideoPromptUpsampling, setPvideoPromptUpsampling] = useState<'default' | 'on' | 'off'>('default')

  // Grok model selection
  const [grokModels, setGrokModels] = useState<GrokModel[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [defaultModel, setDefaultModel] = useState('')

  // Language selection
  const [languages, setLanguages] = useState<{ code: string; label: string }[]>([])
  const [selectedLanguage, setSelectedLanguage] = useState('fr')

  // Player form
  const [name, setName] = useState('')
  const [age, setAge] = useState(28)
  const [gender, setGender] = useState('homme')
  const [customGender, setCustomGender] = useState('')
  const [preferences, setPreferences] = useState('femmes')
  const [customPreferences, setCustomPreferences] = useState('')

  // Custom setting
  const [customSetting, setCustomSetting] = useState('')

  // Cast
  const [selectedActors, setSelectedActors] = useState<string[]>([])
  const [actorGenders, setActorGenders] = useState<Record<string, string>>({})  // codename -> 'female' | 'trans'
  const [customCharacterDesc, setCustomCharacterDesc] = useState('')

  // System prompt
  const [systemPrompt, setSystemPrompt] = useState('')
  const [promptLoading, setPromptLoading] = useState(false)
  const [promptEdited, setPromptEdited] = useState(false)

  // Prompt variants (localStorage)
  const [savedVariants, setSavedVariants] = useState<{ name: string; prompt: string; date: string }[]>([])
  const [variantName, setVariantName] = useState('')
  const [showVariants, setShowVariants] = useState(false)

  // Load saved variants from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem('graphbun_prompt_variants')
      if (raw) setSavedVariants(JSON.parse(raw))
    } catch { /* ignore */ }
  }, [])

  const persistVariants = (variants: typeof savedVariants) => {
    setSavedVariants(variants)
    localStorage.setItem('graphbun_prompt_variants', JSON.stringify(variants))
  }

  const saveVariant = () => {
    const label = variantName.trim() || `Variante ${savedVariants.length + 1}`
    const existing = savedVariants.filter((v) => v.name !== label)
    persistVariants([...existing, { name: label, prompt: systemPrompt, date: new Date().toISOString() }])
    setVariantName('')
  }

  const loadVariant = (v: { name: string; prompt: string }) => {
    setSystemPrompt(v.prompt)
    setPromptEdited(true)
    setShowVariants(false)
  }

  const deleteVariant = (name: string) => {
    persistVariants(savedVariants.filter((v) => v.name !== name))
  }

  useEffect(() => {
    Promise.all([fetchActors(), fetchSettings()]).then(([a, s]) => {
      setActors(a)
      setSettings(s)
    })
    fetchGrokModels().then(({ models, default: def }) => {
      setGrokModels(models)
      setDefaultModel(def)
      setSelectedModel(def)
    }).catch(() => {})
    fetchLanguages().then(({ languages: langs, default: def }) => {
      setLanguages(langs)
      setSelectedLanguage(def)
    }).catch(() => {})
    listSessions().then(setSavedSessions).catch(() => {})

    // Pre-fill from saved profile
    const profile = loadProfile()
    if (profile.name) {
      setName(profile.name)
      setAge(profile.age)
      setGender(profile.gender)
      if (profile.customGender) setCustomGender(profile.customGender)
      setPreferences(profile.preferences)
      if (profile.customPreferences) setCustomPreferences(profile.customPreferences)
      setSelectedLanguage(profile.language)
    }
  }, [])

  /** Start a new story — skip the player step if profile is set */
  const startNewStory = () => {
    const profile = loadProfile()
    if (profile.name) {
      // Pre-fill and skip directly to setting step
      setName(profile.name)
      setAge(profile.age)
      setGender(profile.gender)
      if (profile.customGender) setCustomGender(profile.customGender)
      setPreferences(profile.preferences)
      if (profile.customPreferences) setCustomPreferences(profile.customPreferences)
      setSelectedLanguage(profile.language)
      setStep('setting')
    } else {
      // No profile yet → fall back to the player form
      setStep('player')
    }
  }

  useEffect(() => {
    if (showDebug && allLoras.length === 0) {
      fetchAvailableLoras().then(setAllLoras)
    }
  }, [showDebug])

  const handleResume = async (sessionId: string) => {
    setResuming(sessionId)
    try {
      const [data, historyData] = await Promise.all([
        resumeSession(sessionId),
        getSessionHistory(sessionId),
      ])
      store.resumeSession(
        data.session_id,
        data.sequence_number || 0,
        historyData.sequences || [],
        data.met_characters || [],
        data.character_names || {},
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resume')
    } finally {
      setResuming(null)
    }
  }

  /** Open the phone for a saved session WITHOUT starting/resuming it.
   * Loads met_characters + character_names into the store and opens the phone overlay. */
  const openPhoneForSession = async (sessionId: string) => {
    setOpeningPhone(true)
    try {
      const [data, historyData] = await Promise.all([
        resumeSession(sessionId),
        getSessionHistory(sessionId),
      ])
      // Push minimal session data into the store so Phone can use it.
      // We DO NOT call store.resumeSession (which sets step='choosing') —
      // we want to stay on the home page. We just inject the phone-relevant fields.
      const derivedMet: Set<string> = new Set(data.met_characters || [])
      for (const seq of (historyData.sequences || [])) {
        for (const img of seq.images || []) {
          for (const a of (img as any).actors_present || []) {
            if (a) derivedMet.add(a)
          }
        }
      }
      useGameStore.setState({
        sessionId: data.session_id,
        metCharacters: Array.from(derivedMet),
        characterNames: data.character_names || {},
        phoneOpen: true,
      })
      setPhoneSession({
        id: sessionId,
        player_name: data.player?.name || 'Anonyme',
        setting: data.setting === 'custom' ? 'Custom' : (data.setting || ''),
      })
      setShowHomePhone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open phone')
    } finally {
      setOpeningPhone(false)
    }
  }

  const handleOpenPhoneFromHome = () => {
    // Default to the most recent session
    if (savedSessions.length === 0) return
    const latest = savedSessions[0]
    openPhoneForSession(latest.id)
  }

  const toggleActor = (codename: string) => {
    setSelectedActors((prev) => {
      if (prev.includes(codename)) return prev.filter((c) => c !== codename)
      return [...prev, codename]
    })
  }

  const resolvePlayer = () => {
    const resolvedGender = gender === 'custom' ? customGender || 'autre' : gender
    const resolvedPrefs = preferences === 'custom' ? customPreferences || 'tout le monde' : preferences
    return { name, age, gender: resolvedGender, preferences: resolvedPrefs }
  }

  const goToPromptStep = async () => {
    if (!store.setting || selectedActors.length < 1) return
    setPromptLoading(true)
    // Load default moods if not loaded
    if (!moodsLoaded) {
      try {
        const data = await fetchDefaultStyleMoods()
        setStyleMoods(data.style_moods)
        if (!allLoras.length) setAllLoras(data.available_loras || [])
        setMoodsLoaded(true)
      } catch { /* ignore */ }
    }
    try {
      const prompt = await previewSystemPrompt({
        player: resolvePlayer(),
        setting: store.setting,
        actors: selectedActors,
        custom_setting: store.setting === 'custom' ? customSetting : undefined,
      })
      setSystemPrompt(prompt)
      setPromptEdited(false)
      setStep('prompt')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to preview prompt')
    } finally {
      setPromptLoading(false)
    }
  }

  const handleStart = async () => {
    if (!store.setting || selectedActors.length < 1) return
    setLoading(true)
    setError('')
    try {
      const player = resolvePlayer()
      store.setPlayer(player)
      store.setCast({ actors: selectedActors })

      const result = await startGame({
        player,
        setting: store.setting,
        actors: selectedActors,
        actor_genders: Object.keys(actorGenders).length > 0 ? actorGenders : undefined,
        custom_setting: store.setting === 'custom' ? customSetting : undefined,
        system_prompt_override: promptEdited ? systemPrompt : undefined,
        style_moods: moodsLoaded ? styleMoods : undefined,
        grok_model: selectedModel && selectedModel !== defaultModel ? selectedModel : undefined,
        language: selectedLanguage !== 'fr' ? selectedLanguage : undefined,
        video_simulate: simulateVideo || undefined,
        video_early_start: earlyStartVideo || undefined,
        video_hd: videoMode === '540_5' || undefined,
        video_short: videoMode === '256_5' || undefined,
        video_backend: videoBackend,
        video_draft: videoDraftMode,
        video_start_scene: videoStartScene || undefined,
        pvideo_prompt_upsampling: pvideoPromptUpsampling === 'default' ? undefined : pvideoPromptUpsampling === 'on',
        custom_character_desc: selectedActors.includes('custom') ? customCharacterDesc || undefined : undefined,
      })
      store.startSession(result.session_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start game')
    } finally {
      setLoading(false)
    }
  }

  /* ── Navigation buttons rendered into fixed bottom bar on mobile ── */
  const renderNavButtons = () => {
    if (step === 'home') {
      return null  // Home page has its own CTAs
    }
    if (step === 'player') {
      return (
        <button
          onClick={() => setStep('setting')}
          disabled={!name}
          className="w-full min-h-[48px] bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed py-3 rounded-lg font-medium transition-colors"
        >
          {t('setup.next')}
        </button>
      )
    }
    if (step === 'setting') {
      return (
        <div className="flex gap-3">
          <button
            onClick={() => setStep('home')}
            className="flex-1 min-h-[48px] bg-neutral-800 hover:bg-neutral-700 py-3 rounded-lg font-medium transition-colors"
          >
            {t('setup.back')}
          </button>
          <button
            onClick={() => setStep('cast')}
            disabled={!store.setting || (store.setting === 'custom' && !customSetting.trim())}
            className="flex-1 min-h-[48px] bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed py-3 rounded-lg font-medium transition-colors"
          >
            {t('setup.next')}
          </button>
        </div>
      )
    }
    if (step === 'cast') {
      return (
        <div className="flex gap-3">
          <button
            onClick={() => setStep('setting')}
            className="flex-1 min-h-[48px] bg-neutral-800 hover:bg-neutral-700 py-3 rounded-lg font-medium transition-colors"
          >
            {t('setup.back')}
          </button>
          <button
            onClick={goToPromptStep}
            disabled={selectedActors.length < 1 || promptLoading}
            className="flex-1 min-h-[48px] bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed py-3 rounded-lg font-medium transition-colors"
          >
            {promptLoading ? t('setup.loading') : t('setup.next')}
          </button>
        </div>
      )
    }
    if (step === 'prompt') {
      return (
        <div className="flex gap-3">
          <button
            onClick={() => setStep('cast')}
            className="flex-1 min-h-[48px] bg-neutral-800 hover:bg-neutral-700 py-3 rounded-lg font-medium transition-colors"
          >
            {t('setup.back')}
          </button>
          <button
            onClick={handleStart}
            disabled={loading}
            className="flex-1 min-h-[48px] bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-30 disabled:cursor-not-allowed py-3 rounded-lg font-medium transition-all"
          >
            {loading ? t('setup.starting') : t('setup.start')}
          </button>
        </div>
      )
    }
    return null
  }

  return (
    <div className="min-h-[100dvh] bg-neutral-950 px-4 py-6 md:px-8 md:py-12">
      {/* Profile + Phone pill — top left */}
      <div className="fixed top-4 left-4 z-50 flex gap-2 items-center">
        <button
          onClick={() => setShowProfileModal(true)}
          className="flex items-center gap-2 px-3 py-1.5 min-h-[36px] rounded-full bg-neutral-900/80 hover:bg-neutral-800 text-neutral-300 transition-colors text-xs backdrop-blur-sm"
          title={t('profile.title')}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
          </svg>
          <span className="hidden sm:inline">{loadProfile().name || t('profile.set_up')}</span>
        </button>
        {/* Phone — only enabled if there's at least one saved session */}
        {savedSessions.length > 0 && (
          <button
            onClick={handleOpenPhoneFromHome}
            disabled={openingPhone}
            className="flex items-center gap-1.5 px-3 py-1.5 min-h-[36px] rounded-full bg-neutral-900/80 hover:bg-neutral-800 text-neutral-300 transition-colors text-xs backdrop-blur-sm disabled:opacity-50"
            title="Phone"
          >
            <span>📱</span>
            <span className="hidden sm:inline">Phone</span>
          </button>
        )}
      </div>

      {/* Top right: empty (controls moved into profile menu) */}

      {/* Debug panel (slide-in from right) */}
      {showDebug && (
        <div className="fixed top-0 right-0 w-full md:w-96 h-full bg-neutral-900 border-l border-neutral-800 z-40 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-neutral-800 flex items-center justify-between">
            <span className="text-sm font-medium text-neutral-300">Debug — Setup</span>
            <button onClick={() => setShowDebug(false)} className="text-neutral-500 hover:text-neutral-300 min-h-[44px] min-w-[44px] flex items-center justify-center text-xl">&times;</button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* System prompt preview */}
            <div>
              <h4 className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">System Prompt (template)</h4>
              <p className="text-[11px] text-neutral-500 mb-2">
                Le prompt complet sera construit au démarrage avec les infos joueur, cadre et casting.
                Il sera éditable en jeu via le panneau Debug.
              </p>
              <div className="bg-neutral-950 rounded-lg p-3 text-xs text-neutral-400 font-mono max-h-48 overflow-y-auto whitespace-pre-wrap">
                Narrateur visual novel adulte{'\n'}
                Narration: français (tu), 2e personne{'\n'}
                Prompts image: anglais, 80-200 mots{'\n'}
                5 images/séquence via generate_scene_image{'\n'}
                3 choix + 1 libre via provide_choices{'\n'}
                Cohérence visuelle stricte{'\n'}
                POV première personne
              </div>
            </div>

            {/* Available LoRAs */}
            <div>
              <h4 className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">LoRAs disponibles ({allLoras.length})</h4>
              <div className="space-y-1">
                {allLoras.map((l) => (
                  <div key={l.id} className="flex items-center justify-between bg-neutral-950 rounded px-3 py-1.5 text-xs">
                    <div>
                      <span className="text-neutral-300">{l.name}</span>
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] ${
                        l.type === 'character' ? 'bg-purple-900/50 text-purple-400' : 'bg-indigo-900/50 text-indigo-400'
                      }`}>
                        {l.type}
                      </span>
                    </div>
                    {l.trigger && (
                      <span className="text-neutral-600 font-mono text-[10px]">{l.trigger}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Grok model info */}
            <div>
              <h4 className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">Modèle Grok</h4>
              <div className="bg-neutral-950 rounded-lg p-3 text-xs text-neutral-400 space-y-1">
                {(() => {
                  const m = grokModels.find(x => x.id === selectedModel)
                  return m ? (<>
                    <div className="flex justify-between">
                      <span>Modèle</span>
                      <span className="text-neutral-300 font-mono">{m.id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Tier</span>
                      <span className={`font-medium ${m.tier === 'premium' ? 'text-amber-400' : m.tier === 'standard' ? 'text-indigo-400' : 'text-neutral-300'}`}>{m.tier}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Prix</span>
                      <span className="text-neutral-300">${m.input_price} / ${m.output_price} par 1M tokens</span>
                    </div>
                  </>) : (
                    <div className="flex justify-between">
                      <span>Modèle</span>
                      <span className="text-neutral-300 font-mono">{selectedModel || defaultModel || '...'}</span>
                    </div>
                  )
                })()}
                <div className="flex justify-between">
                  <span>Image gen</span>
                  <span className="text-neutral-300">Z-Image Turbo, ~6s</span>
                </div>
                <div className="flex justify-between">
                  <span>Safety checker</span>
                  <span className="text-red-400">OFF</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="w-full max-w-lg mx-auto pb-28 md:pb-0 md:flex md:flex-col md:items-stretch">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold mb-2">
            <span className="text-indigo-400">Graph</span>
            <span className="text-purple-400">Bun</span>
          </h1>
          <p className="text-neutral-500 text-sm">Ton histoire. Tes choix.</p>
        </div>

        {/* Saved sessions */}
        {false && savedSessions.length > 0 && step === 'player' && (
          <div className="mb-8 fade-in">
            <h3 className="text-sm text-neutral-400 mb-3">{t('setup.resume_title')}</h3>
            <div className="space-y-2">
              {savedSessions.slice(0, 5).map((s) => (
                <div key={s.id} className="flex gap-2 items-stretch">
                  <button
                    onClick={() => handleResume(s.id)}
                    disabled={resuming !== null}
                    className="flex-1 text-left p-4 md:p-3 rounded-xl border border-neutral-800 bg-neutral-900/50 hover:border-indigo-700 hover:bg-indigo-950/20 transition-all disabled:opacity-50 min-h-[56px]"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-neutral-200 text-sm font-medium">
                          {s.player?.name || 'Anonyme'}
                        </span>
                        <span className="text-neutral-600 text-xs ml-2">
                          Seq. {s.sequence_number}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-neutral-500">
                        <span>{s.setting === 'custom' ? 'Custom' : s.setting?.replace('_', ' ')}</span>
                        {s.total_costs?.total > 0 && (
                          <span className="text-emerald-400/60 font-mono">${s.total_costs.total.toFixed(3)}</span>
                        )}
                      </div>
                    </div>
                    <div className="text-[10px] text-neutral-600 mt-1">
                      {new Date(s.updated_at).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      {resuming === s.id && <span className="ml-2 text-indigo-400">{t('setup.loading')}</span>}
                    </div>
                  </button>
                  <button
                    onClick={() => store.openGallery(s.id)}
                    className="px-3 md:px-2 min-w-[44px] rounded-xl border border-neutral-800 bg-neutral-900/50 text-neutral-600 hover:text-indigo-400 hover:border-indigo-700 transition-colors text-xs flex items-center justify-center"
                    title="Voir la galerie"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V5.25a1.5 1.5 0 00-1.5-1.5H3.75a1.5 1.5 0 00-1.5 1.5v14.25c0 .828.672 1.5 1.5 1.5z" />
                    </svg>
                  </button>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation()
                      if (!confirm(t('setup.delete_confirm'))) return
                      await deleteSession(s.id)
                      setSavedSessions(prev => prev.filter(x => x.id !== s.id))
                    }}
                    className="px-3 md:px-2 min-w-[44px] rounded-xl border border-neutral-800 bg-neutral-900/50 text-neutral-600 hover:text-red-400 hover:border-red-900 transition-colors text-sm flex items-center justify-center"
                    title="Supprimer"
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
            <div className="border-t border-neutral-800 mt-4 pt-4 flex items-center justify-between">
              <p className="text-xs text-neutral-600">{t('setup.new_story')}</p>
              <button
                onClick={async () => {
                  if (!confirm(t('setup.clear_memories_confirm'))) return
                  try {
                    const result = await clearAllMemories()
                    alert(`${result.cleared} ${t('setup.clear_memories_done')}`)
                  } catch (e) {
                    alert(t('common.error') + ': ' + (e instanceof Error ? e.message : 'inconnu'))
                  }
                }}
                className="text-[10px] px-2 py-1 min-h-[36px] rounded-lg bg-neutral-900 text-neutral-600 hover:text-red-400 hover:bg-red-950/30 transition-colors"
              >
                {t('setup.clear_memories')}
              </button>
            </div>
          </div>
        )}

        {/* Step indicator (hidden on home) */}
        {step !== 'home' && (
        <div className="flex justify-center gap-2 mb-8">
          {(['player', 'setting', 'cast', 'prompt'] as const).map((s, i) => {
            const allSteps = ['player', 'setting', 'cast', 'prompt'] as const
            const isCurrent = s === step
            const isPast = i < allSteps.indexOf(step)
            return (
              <div
                key={s}
                className={`rounded-full transition-colors ${
                  /* Mobile: uniform dots; Desktop: bars */
                  'w-2.5 h-2.5 md:h-1 md:rounded-full'
                } ${
                  s === 'prompt' ? 'md:w-20' : 'md:w-12'
                } ${
                  isCurrent
                    ? 'bg-indigo-500'
                    : isPast
                      ? 'bg-indigo-800'
                      : 'bg-neutral-800'
                }`}
              />
            )
          })}
        </div>
        )}

        {/* ── Step 0: Home (landing) ── */}
        {step === 'home' && (
          <div className="fade-in space-y-6">
            {savedSessions.length > 0 ? (
              <>
                <h2 className="text-base font-semibold text-neutral-300">{t('setup.resume_title') || 'Continue a story'}</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {savedSessions.slice(0, 6).map((s) => (
                    <div key={s.id} className="group relative rounded-2xl overflow-hidden border border-neutral-800 hover:border-indigo-600 transition-all aspect-[4/3] bg-neutral-900">
                      {s.thumbnail_url ? (
                        <img
                          src={s.thumbnail_url}
                          alt=""
                          className="absolute inset-0 w-full h-full object-cover opacity-70 group-hover:opacity-90 transition-opacity"
                          loading="lazy"
                        />
                      ) : (
                        <div className="absolute inset-0 bg-gradient-to-br from-indigo-950/40 to-purple-950/40" />
                      )}
                      <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/40 to-transparent" />
                      <button
                        onClick={() => handleResume(s.id)}
                        disabled={resuming !== null}
                        className="absolute inset-0 w-full h-full text-left p-4 flex flex-col justify-end disabled:opacity-50"
                      >
                        <div className="flex items-baseline gap-2">
                          <span className="text-white font-semibold text-base drop-shadow">{s.player?.name || 'Anonyme'}</span>
                          <span className="text-white/60 text-xs">Seq. {s.sequence_number}</span>
                        </div>
                        <div className="flex items-center gap-2 text-[11px] text-white/60 mt-1">
                          <span>{s.setting === 'custom' ? 'Custom' : s.setting?.replace('_', ' ')}</span>
                          {s.total_costs?.total > 0 && (
                            <span className="text-emerald-400/80 font-mono">${s.total_costs.total.toFixed(3)}</span>
                          )}
                          <span className="text-white/40 ml-auto">
                            {new Date(s.updated_at).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
                          </span>
                        </div>
                        {resuming === s.id && (
                          <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          </div>
                        )}
                      </button>
                      {/* Action buttons (gallery + delete) — top-right corner */}
                      <div className="absolute top-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => { e.stopPropagation(); store.openGallery(s.id) }}
                          className="w-8 h-8 rounded-full bg-black/60 backdrop-blur-sm text-white/70 hover:text-white hover:bg-indigo-600/70 transition-colors flex items-center justify-center"
                          title="Galerie"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V5.25a1.5 1.5 0 00-1.5-1.5H3.75a1.5 1.5 0 00-1.5 1.5v14.25c0 .828.672 1.5 1.5 1.5z" />
                          </svg>
                        </button>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation()
                            if (!confirm(t('setup.delete_confirm'))) return
                            await deleteSession(s.id)
                            setSavedSessions(prev => prev.filter(x => x.id !== s.id))
                          }}
                          className="w-8 h-8 rounded-full bg-black/60 backdrop-blur-sm text-white/70 hover:text-white hover:bg-red-600/70 transition-colors flex items-center justify-center"
                          title="Supprimer"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {/* New story CTA */}
            <button
              onClick={startNewStory}
              className="w-full py-5 rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/30"
            >
              {savedSessions.length > 0 ? t('setup.start_new_story') : t('setup.start_first_story')}
            </button>

            {savedSessions.length > 0 && (
              <button
                onClick={async () => {
                  if (!confirm(t('setup.clear_memories_confirm'))) return
                  try {
                    const result = await clearAllMemories()
                    alert(`${result.cleared} ${t('setup.clear_memories_done')}`)
                  } catch (e) {
                    alert(t('common.error') + ': ' + (e instanceof Error ? e.message : 'inconnu'))
                  }
                }}
                className="w-full text-[11px] text-neutral-600 hover:text-red-400 transition-colors py-2"
              >
                {t('setup.clear_memories')}
              </button>
            )}
          </div>
        )}

        {/* ── Step 1: Player ── */}
        {step === 'player' && (
          <div className="fade-in space-y-4">
            <h2 className="text-xl font-semibold text-neutral-200 mb-4">{t('setup.step1.title')}</h2>
            <div>
              <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('setup.step1.name')}</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('setup.step1.name_placeholder')}
                className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-4 py-3.5 text-neutral-100 focus:border-indigo-500 focus:outline-none transition-colors"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div>
                <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('setup.step1.age')}</label>
                <input
                  type="number"
                  value={age}
                  onChange={(e) => setAge(+e.target.value)}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-3.5 text-neutral-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('setup.step1.gender')}</label>
                <select
                  value={gender}
                  onChange={(e) => { setGender(e.target.value); if (e.target.value !== 'custom') setCustomGender('') }}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-3.5 text-neutral-100 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="homme">{t('setup.step1.gender.man')}</option>
                  <option value="femme">{t('setup.step1.gender.woman')}</option>
                  <option value="non-binaire">{t('setup.step1.gender.nb')}</option>
                  <option value="custom">{t('setup.step1.gender.other')}</option>
                </select>
                {gender === 'custom' && (
                  <input
                    value={customGender}
                    onChange={(e) => setCustomGender(e.target.value)}
                    placeholder={t('setup.step1.gender.custom_placeholder')}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-3 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none"
                  />
                )}
              </div>
              <div>
                <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('setup.step1.preferences')}</label>
                <select
                  value={preferences}
                  onChange={(e) => { setPreferences(e.target.value); if (e.target.value !== 'custom') setCustomPreferences('') }}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-3.5 text-neutral-100 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="femmes">{t('setup.step1.pref.women')}</option>
                  <option value="hommes">{t('setup.step1.pref.men')}</option>
                  <option value="tout le monde">{t('setup.step1.pref.everyone')}</option>
                  <option value="custom">{t('setup.step1.pref.other')}</option>
                </select>
                {preferences === 'custom' && (
                  <input
                    value={customPreferences}
                    onChange={(e) => setCustomPreferences(e.target.value)}
                    placeholder={t('setup.step1.pref.custom_placeholder')}
                    className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-3 text-sm text-neutral-100 focus:border-indigo-500 focus:outline-none"
                  />
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Step 2: Setting ── */}
        {step === 'setting' && (
          <div className="fade-in space-y-4">
            <h2 className="text-xl font-semibold text-neutral-200 mb-4">{t('setup.step2.title')}</h2>
            <div className="space-y-3">
              {settings.map((s) => (
                <button
                  key={s.id}
                  onClick={() => { store.setSetting(s.id); setCustomSetting('') }}
                  className={`w-full text-left p-4 rounded-xl border transition-all min-h-[56px] ${
                    store.setting === s.id && !customSetting
                      ? 'border-indigo-500 bg-indigo-950/40'
                      : 'border-neutral-800 bg-neutral-900 hover:border-neutral-700'
                  }`}
                >
                  <div className="font-semibold text-neutral-100">{t(`setting.${s.id}.label`) !== `setting.${s.id}.label` ? t(`setting.${s.id}.label`) : s.label}</div>
                  <div className="text-sm text-neutral-400 mt-1">{t(`setting.${s.id}.desc`) !== `setting.${s.id}.desc` ? t(`setting.${s.id}.desc`) : s.description}</div>
                </button>
              ))}
              {/* Custom setting */}
              <div
                className={`w-full text-left p-4 rounded-xl border transition-all ${
                  store.setting === 'custom'
                    ? 'border-purple-500 bg-purple-950/40'
                    : 'border-neutral-800 bg-neutral-900'
                }`}
              >
                <button
                  onClick={() => store.setSetting('custom')}
                  className="w-full text-left min-h-[44px]"
                >
                  <div className="font-semibold text-neutral-100">{t('setup.step2.custom')}</div>
                  <div className="text-sm text-neutral-400 mt-1">{t('setup.step2.custom_desc')}</div>
                </button>
                {store.setting === 'custom' && (
                  <textarea
                    value={customSetting}
                    onChange={(e) => setCustomSetting(e.target.value)}
                    rows={3}
                    placeholder={t('setup.step2.custom_placeholder')}
                    className="w-full mt-3 bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-3.5 text-sm text-neutral-200 focus:border-purple-500 focus:outline-none placeholder-neutral-600 resize-y"
                  />
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Step 3: Cast ── */}
        {step === 'cast' && (
          <div className="fade-in space-y-4">
            <h2 className="text-xl font-semibold text-neutral-200 mb-1">{t('setup.step3.title')}</h2>
            <p className="text-sm text-neutral-500 mb-4">{t('setup.step3.subtitle')}</p>
            <div className="grid grid-cols-2 gap-3">
              {actors.map((actor) => {
                const selected = selectedActors.includes(actor.codename)
                const isTrans = actorGenders[actor.codename] === 'trans'
                return (
                  <div
                    key={actor.codename}
                    className={`relative p-5 md:p-4 rounded-xl border text-left transition-all min-h-[80px] ${
                      selected
                        ? isTrans
                          ? 'border-pink-500 bg-pink-950/30'
                          : 'border-purple-500 bg-purple-950/40'
                        : 'border-neutral-800 bg-neutral-900 hover:border-neutral-700'
                    }`}
                  >
                    <button
                      onClick={() => toggleActor(actor.codename)}
                      className="block w-full text-left"
                    >
                      {selected && (
                        <span className={`absolute top-2 right-2 text-white text-xs w-6 h-6 md:w-5 md:h-5 rounded-full flex items-center justify-center ${
                          isTrans ? 'bg-pink-600' : 'bg-purple-600'
                        }`}>
                          ✓
                        </span>
                      )}
                      <div className="font-semibold text-neutral-100 text-base md:text-sm">{actor.display_name}</div>
                      <div className="text-sm md:text-xs text-neutral-400 mt-1">{actor.description}</div>
                    </button>
                    {/* Gender toggle — only when actor is selected */}
                    {selected && (
                      <div className="flex gap-1 mt-2 bg-black/30 rounded-full p-0.5 w-fit" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => setActorGenders((prev) => { const n = { ...prev }; delete n[actor.codename]; return n })}
                          className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                            !isTrans ? 'bg-purple-600 text-white' : 'text-neutral-500 hover:text-neutral-300'
                          }`}
                        >
                          ♀
                        </button>
                        <button
                          onClick={() => setActorGenders((prev) => ({ ...prev, [actor.codename]: 'trans' }))}
                          className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                            isTrans ? 'bg-pink-600 text-white' : 'text-neutral-500 hover:text-neutral-300'
                          }`}
                        >
                          ⚧ trans
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {/* Custom character description */}
            {selectedActors.includes('custom') && (
              <div className="mt-3 fade-in">
                <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('setup.step3.custom_label')}</label>
                <textarea
                  value={customCharacterDesc}
                  onChange={(e) => setCustomCharacterDesc(e.target.value)}
                  rows={3}
                  placeholder={t('setup.step3.custom_placeholder')}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-3.5 text-sm text-neutral-200 focus:border-purple-500 focus:outline-none placeholder-neutral-600 resize-y"
                />
                <p className="text-[10px] text-neutral-600 mt-1">
                  {t('setup.step3.custom_hint')}
                </p>
              </div>
            )}
            {error && (
              <div className="text-red-400 text-sm bg-red-950/30 rounded-lg p-3">{error}</div>
            )}
          </div>
        )}

        {/* ── Step 4: System Prompt ── */}
        {step === 'prompt' && (
          <div className="fade-in space-y-4">
            {/* Default: friendly summary, advanced toggle hides the raw prompt */}
            {!showAdvancedPrompt ? (
              <div className="text-center py-8 space-y-4">
                <div className="text-5xl">🎬</div>
                <h2 className="text-xl font-semibold text-neutral-200">
                  {t('setup.step4.ready_title')}
                </h2>
                <p className="text-sm text-neutral-500 max-w-sm mx-auto">
                  {t('setup.step4.ready_subtitle')}
                </p>
                <button
                  onClick={() => setShowAdvancedPrompt(true)}
                  className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors underline-offset-2 hover:underline"
                >
                  {t('setup.step4.advanced')}
                </button>
              </div>
            ) : (
              <>
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-neutral-200">{t('setup.step4.title')}</h2>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowAdvancedPrompt(false)}
                  className="text-xs px-2.5 py-1.5 min-h-[40px] rounded-lg bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition-colors"
                >
                  {t('common.collapse')}
                </button>
                <button
                  onClick={() => setShowVariants(!showVariants)}
                  className={`text-xs px-2.5 py-1.5 min-h-[40px] rounded-lg transition-colors ${
                    showVariants
                      ? 'bg-indigo-900 text-indigo-300'
                      : 'bg-neutral-800 text-neutral-400 hover:text-neutral-200'
                  }`}
                >
                  {t('setup.step4.variants')} ({savedVariants.length})
                </button>
              </div>
            </div>

            {/* Variants panel */}
            {showVariants && (
              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-3 space-y-2">
                {savedVariants.length === 0 && (
                  <p className="text-xs text-neutral-600 text-center py-2">{t('setup.step4.no_variants')}</p>
                )}
                {savedVariants.map((v) => (
                  <div key={v.name} className="flex items-center gap-2 bg-neutral-950 rounded-lg px-3 py-3 md:py-2 min-h-[48px]">
                    <button
                      onClick={() => loadVariant(v)}
                      className="flex-1 text-left"
                    >
                      <div className="text-sm text-neutral-200">{v.name}</div>
                      <div className="text-[10px] text-neutral-600 mt-0.5">
                        {new Date(v.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                        {' · '}
                        {v.prompt.length} chars
                      </div>
                    </button>
                    <button
                      onClick={() => deleteVariant(v.name)}
                      className="text-neutral-600 hover:text-red-400 text-sm shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center"
                    >
                      &times;
                    </button>
                  </div>
                ))}
              </div>
            )}

            <p className="text-sm text-neutral-500">
              {t('setup.step4.subtitle')}
            </p>
            <textarea
              value={systemPrompt}
              onChange={(e) => { setSystemPrompt(e.target.value); setPromptEdited(true) }}
              className="w-full min-h-[200px] md:min-h-[400px] bg-neutral-900 border border-neutral-800 rounded-lg px-4 py-3.5 text-xs text-neutral-300 font-mono leading-relaxed resize-y focus:border-indigo-500 focus:outline-none transition-colors"
            />

            {/* Save variant */}
            <div className="flex gap-2">
              <input
                type="text"
                value={variantName}
                onChange={(e) => setVariantName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveVariant() }}
                placeholder={t('setup.step4.variant_placeholder')}
                className="flex-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-3.5 text-sm text-neutral-300 focus:border-indigo-500 focus:outline-none placeholder-neutral-600"
              />
              <button
                onClick={saveVariant}
                className="bg-neutral-800 hover:bg-neutral-700 px-4 py-3 min-h-[48px] rounded-lg text-sm font-medium text-neutral-300 transition-colors"
              >
                {t('setup.step4.save_variant')}
              </button>
            </div>

            {promptEdited && (
              <p className="text-xs text-amber-400/70">
                {t('setup.step4.prompt_edited')}
              </p>
            )}

            {/* Language selector */}
            {languages.length > 0 && (
              <div>
                <label className="text-xs text-neutral-500 uppercase tracking-wider">{t('setup.step4.language')}</label>
                <select
                  value={selectedLanguage}
                  onChange={(e) => setSelectedLanguage(e.target.value)}
                  className="w-full mt-1 bg-neutral-900 border border-neutral-800 rounded-lg px-4 py-3 text-neutral-100 focus:border-indigo-500 focus:outline-none transition-colors"
                >
                  {languages.map((l) => (
                    <option key={l.code} value={l.code}>{l.label}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Grok model selector */}
            {grokModels.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-neutral-300">{t('setup.step4.model')}</h3>
                <div className="space-y-2">
                  {grokModels.map((m) => {
                    const isSelected = selectedModel === m.id
                    const isDefault = m.id === defaultModel
                    const tierColors = {
                      budget: 'border-neutral-700 bg-neutral-900/50',
                      standard: 'border-indigo-800 bg-indigo-950/30',
                      premium: 'border-amber-800 bg-amber-950/20',
                    }
                    const tierBadge = {
                      budget: 'bg-neutral-800 text-neutral-400',
                      standard: 'bg-indigo-900/60 text-indigo-400',
                      premium: 'bg-amber-900/60 text-amber-400',
                    }
                    return (
                      <button
                        key={m.id}
                        onClick={() => setSelectedModel(m.id)}
                        className={`w-full text-left px-4 py-3.5 md:py-3 rounded-xl border transition-all min-h-[56px] ${
                          isSelected
                            ? m.tier === 'premium'
                              ? 'border-amber-500 bg-amber-950/40'
                              : 'border-indigo-500 bg-indigo-950/40'
                            : tierColors[m.tier] + ' hover:border-neutral-600'
                        }`}
                      >
                        <div className="flex items-center justify-between flex-wrap gap-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-neutral-100">{m.label}</span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${tierBadge[m.tier]}`}>
                              {m.tier}
                            </span>
                            {isDefault && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-neutral-800 text-neutral-500">
                                {t('common.default')}
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-neutral-500 font-mono">
                            ${m.input_price} / ${m.output_price}
                          </span>
                        </div>
                        <p className="text-[11px] text-neutral-500 mt-1">{m.description}</p>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Video simulation toggle (admin only) */}
            {useAuthStore.getState().isAdmin && (<>
              <label className="flex items-center justify-between bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3.5 md:py-3 cursor-pointer min-h-[56px]">
                <div>
                  <span className={`text-sm font-medium ${simulateVideo ? 'text-amber-400' : 'text-neutral-300'}`}>
                    {t('setup.step4.simulate_video')}
                  </span>
                  <p className="text-[10px] text-neutral-500 mt-0.5">
                    {simulateVideo ? t('setup.step4.simulate_video_on') : t('setup.step4.simulate_video_off')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={simulateVideo}
                  onChange={(e) => setSimulateVideo(e.target.checked)}
                  className="rounded bg-neutral-800 border-neutral-700 text-amber-500 w-5 h-5 md:w-4 md:h-4"
                />
              </label>
              <label className="flex items-center justify-between bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3.5 md:py-3 cursor-pointer min-h-[56px]">
                <div>
                  <span className={`text-sm font-medium ${earlyStartVideo ? 'text-emerald-400' : 'text-neutral-300'}`}>
                    {t('setup.step4.early_start')}
                  </span>
                  <p className="text-[10px] text-neutral-500 mt-0.5">
                    {earlyStartVideo ? t('setup.step4.early_start_on') : t('setup.step4.early_start_off')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={earlyStartVideo}
                  onChange={(e) => setEarlyStartVideo(e.target.checked)}
                  className="rounded bg-neutral-800 border-neutral-700 text-emerald-500 w-5 h-5 md:w-4 md:h-4"
                />
              </label>
              <div className="bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3.5 md:py-3 min-h-[56px]">
                <span className="text-sm font-medium text-neutral-300">Video engine</span>
                <div className="flex bg-neutral-800 rounded-lg p-0.5 mt-2">
                  {([['davinci', 'Davinci'], ['pvideo', 'P-Video'], ['none', 'Off']] as const).map(([val, label]) => (
                    <button key={val} onClick={() => setVideoBackend(val)}
                      className={`flex-1 px-2 py-1.5 text-xs rounded-md transition-colors ${videoBackend === val
                        ? val === 'none' ? 'bg-neutral-600 text-white' : 'bg-purple-700 text-white'
                        : 'text-neutral-500 hover:text-neutral-300'}`}>
                      {label}
                    </button>
                  ))}
                </div>
                <p className="text-[9px] text-neutral-600 mt-1.5">
                  {videoBackend === 'davinci' ? 'MagiHuman — Grok vision prompt, talking head'
                    : videoBackend === 'pvideo' ? 'Pruna P-Video via Runware — draft mode, faster'
                    : 'No per-scene video generation'}
                </p>
              </div>
              {videoBackend === 'davinci' && (
                <div className="bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3.5 md:py-3 min-h-[56px]">
                  <span className="text-sm font-medium text-neutral-300">Davinci quality</span>
                  <div className="flex bg-neutral-800 rounded-lg p-0.5 mt-2">
                    {([['256_10', '256p / 10s'], ['256_5', '256p / 5s'], ['540_5', '540p / 5s']] as const).map(([val, label]) => (
                      <button key={val} onClick={() => setVideoMode(val)}
                        className={`flex-1 px-2 py-1.5 text-xs rounded-md transition-colors ${videoMode === val ? 'bg-purple-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {/* Draft mode + start scene — applies to both backends when not 'none' */}
              {videoBackend !== 'none' && (
                <>
                  <div className="bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3.5 md:py-3 min-h-[56px]">
                    <span className="text-sm font-medium text-neutral-300">Video quality</span>
                    <div className="flex bg-neutral-800 rounded-lg p-0.5 mt-2">
                      <button onClick={() => setVideoDraftMode(true)}
                        className={`flex-1 px-2 py-1.5 text-xs rounded-md transition-colors ${videoDraftMode ? 'bg-purple-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                        Draft (fast)
                      </button>
                      <button onClick={() => setVideoDraftMode(false)}
                        className={`flex-1 px-2 py-1.5 text-xs rounded-md transition-colors ${!videoDraftMode ? 'bg-purple-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                        Full quality
                      </button>
                    </div>
                    <p className="text-[9px] text-neutral-600 mt-1.5">
                      {videoDraftMode ? 'Fast & cheap — lower visual quality' : 'Better quality — ~3x slower & more expensive'}
                    </p>
                  </div>
                  <div className="bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3.5 md:py-3 min-h-[56px]">
                    <span className="text-sm font-medium text-neutral-300">Generate video for</span>
                    <div className="flex bg-neutral-800 rounded-lg p-0.5 mt-2">
                      {([
                        [0, 'All 8 scenes'],
                        [4, 'Last 4 scenes'],
                        [6, 'Last 2 scenes'],
                      ] as const).map(([val, label]) => (
                        <button key={val} onClick={() => setVideoStartScene(val)}
                          className={`flex-1 px-2 py-1.5 text-xs rounded-md transition-colors ${videoStartScene === val ? 'bg-purple-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                          {label}
                        </button>
                      ))}
                    </div>
                    <p className="text-[9px] text-neutral-600 mt-1.5">
                      {videoStartScene === 0 ? 'Every scene gets a video' : `Scenes 0-${videoStartScene - 1} = image only, scenes ${videoStartScene}-7 = image + video`}
                    </p>
                  </div>
                </>
              )}
              {videoBackend === 'pvideo' && (
                <div className="bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3.5 md:py-3 min-h-[56px]">
                  <span className="text-sm font-medium text-neutral-300">P-Video prompt upsampling</span>
                  <div className="flex bg-neutral-800 rounded-lg p-0.5 mt-2">
                    {([['default', 'Default'], ['on', 'On'], ['off', 'Off']] as const).map(([val, label]) => (
                      <button key={val} onClick={() => setPvideoPromptUpsampling(val)}
                        className={`flex-1 px-2 py-1.5 text-xs rounded-md transition-colors ${pvideoPromptUpsampling === val ? 'bg-purple-700 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}>
                        {label}
                      </button>
                    ))}
                  </div>
                  <p className="text-[9px] text-neutral-600 mt-1.5">
                    {pvideoPromptUpsampling === 'default' ? 'Use Runware default (likely true)'
                      : pvideoPromptUpsampling === 'on' ? 'Force ON — Pruna enhances the prompt'
                      : 'Force OFF — raw narration only'}
                  </p>
                </div>
              )}
            </>)}

            {/* Style Moods Configuration */}
            <details className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden">
              <summary className="px-4 py-3.5 md:py-3 text-sm font-medium text-neutral-300 cursor-pointer hover:text-neutral-100 min-h-[48px] flex items-center">
                {t('setup.step4.moods_title')} ({Object.keys(styleMoods).length} moods)
              </summary>
              <div className="px-4 pb-4 space-y-2">
                <p className="text-[11px] text-neutral-500 mb-2">
                  L'IA peut combiner plusieurs moods par image. Chaque mood a un LoRA, un bloc de prompt et un exemple.
                </p>
                {Object.entries(styleMoods).map(([mood, data]) => {
                  const d = data || {} as any
                  const lora = d.lora
                  return (
                    <details key={mood} className="bg-neutral-950 rounded-lg border border-neutral-800 overflow-hidden">
                      <summary className="px-3 py-2.5 md:py-2 flex items-center justify-between cursor-pointer hover:bg-neutral-900 min-h-[44px]">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-indigo-400 font-mono">{mood}</span>
                          {lora && <span className="text-[9px] text-neutral-600">{lora.name}</span>}
                          {d.prompt_block && <span className="text-[9px] text-purple-400/60">prompt</span>}
                        </div>
                        {mood !== 'neutral' && (
                          <button
                            onClick={(e) => { e.preventDefault(); setStyleMoods(prev => { const n = {...prev}; delete n[mood]; return n }) }}
                            className="text-neutral-600 hover:text-red-400 text-sm min-w-[36px] min-h-[36px] flex items-center justify-center"
                          >&times;</button>
                        )}
                      </summary>
                      <div className="px-3 pb-3 space-y-2 border-t border-neutral-800 pt-2">
                        {/* Description */}
                        <input type="text" value={d.description || ''} placeholder="Description (quand utiliser ce mood)..."
                          onChange={(e) => setStyleMoods(prev => ({...prev, [mood]: {...(prev[mood] || {}), description: e.target.value}}))}
                          className="w-full bg-neutral-900 border border-neutral-800 rounded px-2 py-2 md:py-1 text-[11px] md:text-[10px] text-neutral-400 focus:border-indigo-500 focus:outline-none placeholder-neutral-700" />
                        {/* LoRA */}
                        <div className="flex items-center gap-2">
                          <span className="text-[9px] text-neutral-600 w-10 shrink-0">LoRA</span>
                          <select value={lora?.id || ''}
                            onChange={(e) => {
                              const id = e.target.value
                              if (!id) {
                                setStyleMoods(prev => ({...prev, [mood]: {...(prev[mood] || {}), lora: null}}))
                              } else {
                                const info = allLoras.find(l => l.id === id)
                                setStyleMoods(prev => ({...prev, [mood]: {...(prev[mood] || {}), lora: {id, name: info?.name || id, weight: lora?.weight || 0.6}}}))
                              }
                            }}
                            className="flex-1 bg-neutral-900 border border-neutral-800 rounded px-2 py-2 md:py-1 text-[11px] md:text-[10px] text-neutral-300 focus:border-indigo-500 focus:outline-none min-w-0">
                            <option value="">Aucun</option>
                            {allLoras.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                          </select>
                          {lora && (
                            <input type="number" step={0.1} min={0} max={2} value={lora.weight ?? 0.6}
                              onChange={(e) => setStyleMoods(prev => ({...prev, [mood]: {...prev[mood], lora: {...prev[mood]?.lora, weight: +e.target.value}}}))}
                              className="w-14 bg-neutral-900 border border-neutral-800 rounded px-1.5 py-2 md:py-1 text-[11px] md:text-[10px] text-neutral-300 font-mono focus:border-indigo-500 focus:outline-none" />
                          )}
                        </div>
                        {/* CFG + Steps overrides */}
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[9px] text-neutral-600">CFG</span>
                            <input type="number" step={0.5} min={0} max={20}
                              value={d.cfg ?? ''}
                              onChange={(e) => setStyleMoods(prev => ({...prev, [mood]: {...(prev[mood] || {}), cfg: e.target.value === '' ? null : +e.target.value}}))}
                              placeholder="def"
                              className="w-14 bg-neutral-900 border border-neutral-800 rounded px-1.5 py-2 md:py-1 text-[11px] md:text-[10px] text-neutral-300 font-mono focus:border-indigo-500 focus:outline-none placeholder-neutral-700" />
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[9px] text-neutral-600">Steps</span>
                            <input type="number" step={1} min={1} max={50}
                              value={d.steps ?? ''}
                              onChange={(e) => setStyleMoods(prev => ({...prev, [mood]: {...(prev[mood] || {}), steps: e.target.value === '' ? null : +e.target.value}}))}
                              placeholder="def"
                              className="w-14 bg-neutral-900 border border-neutral-800 rounded px-1.5 py-2 md:py-1 text-[11px] md:text-[10px] text-neutral-300 font-mono focus:border-indigo-500 focus:outline-none placeholder-neutral-700" />
                          </div>
                          <span className="text-[8px] text-neutral-700 flex-1">vide = valeur globale</span>
                        </div>
                        {/* Prompt block */}
                        <div>
                          <span className="text-[9px] text-neutral-600">Bloc prompt (injecte dans Couche 1, avant habits)</span>
                          <textarea value={d.prompt_block || ''} rows={2}
                            onChange={(e) => setStyleMoods(prev => ({...prev, [mood]: {...(prev[mood] || {}), prompt_block: e.target.value}}))}
                            placeholder="Ex: bjz, pov oral sex, woman kneeling, gaze up toward camera..."
                            className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-2 md:py-1 text-[11px] md:text-[10px] text-neutral-300 font-mono resize-y focus:border-purple-500 focus:outline-none placeholder-neutral-700" />
                        </div>
                        {/* Example */}
                        <div>
                          <span className="text-[9px] text-neutral-600">Exemple (guide l'IA)</span>
                          <textarea value={d.example || ''} rows={2}
                            onChange={(e) => setStyleMoods(prev => ({...prev, [mood]: {...(prev[mood] || {}), example: e.target.value}}))}
                            placeholder="Ex: A close-up shot of a 25-year-old woman with half-lidded eyes..."
                            className="w-full mt-0.5 bg-neutral-900 border border-neutral-800 rounded px-2 py-2 md:py-1 text-[11px] md:text-[10px] text-neutral-400 font-mono resize-y focus:border-purple-500 focus:outline-none placeholder-neutral-700" />
                        </div>
                      </div>
                    </details>
                  )
                })}
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    value={newMoodName}
                    onChange={(e) => setNewMoodName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newMoodName.trim()) {
                        setStyleMoods(prev => ({...prev, [newMoodName.trim()]: null}))
                        setNewMoodName('')
                      }
                    }}
                    placeholder="Nouveau mood..."
                    className="flex-1 bg-neutral-950 border border-neutral-800 rounded px-3 py-2.5 md:py-1.5 text-xs text-neutral-300 focus:border-indigo-500 focus:outline-none placeholder-neutral-600"
                  />
                  <button
                    onClick={() => {
                      if (newMoodName.trim()) {
                        setStyleMoods(prev => ({...prev, [newMoodName.trim()]: null}))
                        setNewMoodName('')
                      }
                    }}
                    className="bg-neutral-800 hover:bg-neutral-700 px-3 py-2.5 md:py-1.5 min-h-[44px] md:min-h-0 rounded text-xs text-neutral-300 transition-colors"
                  >
                    + Mood
                  </button>
                </div>
              </div>
            </details>
              </>
            )}

            {error && (
              <div className="text-red-400 text-sm bg-red-950/30 rounded-lg p-3">{error}</div>
            )}
          </div>
        )}

        {/* ── Action bar: fixed bottom on mobile, inline on desktop ── */}
        <div className="fixed bottom-0 inset-x-0 p-4 glass border-t border-neutral-800/50 md:static md:bg-transparent md:border-0 md:backdrop-blur-none md:p-0 md:mt-8 z-30">
          <div className="max-w-lg mx-auto md:mx-0">
            {renderNavButtons()}
          </div>
        </div>
      </div>

      {/* Profile modal */}
      <ProfileModal
        open={showProfileModal}
        onClose={() => setShowProfileModal(false)}
        onOpenDebug={() => setShowDebug(true)}
      />

      {/* Phone overlay (from home) */}
      {showHomePhone && (
        <Phone
          sessionSwitcher={{
            sessions: savedSessions.map((s) => ({
              id: s.id,
              label: `${s.player?.name || 'Anonyme'} — ${s.setting === 'custom' ? 'Custom' : s.setting?.replace('_', ' ')}`,
            })),
            current: phoneSession?.id || null,
            onSwitch: (id) => openPhoneForSession(id),
          }}
          onCloseAll={() => {
            setShowHomePhone(false)
            useGameStore.setState({ phoneOpen: false, sessionId: null, metCharacters: [], characterNames: {} })
          }}
        />
      )}
    </div>
  )
}
