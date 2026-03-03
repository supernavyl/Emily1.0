import { useState, useEffect, useRef, useCallback } from 'react'
import { ArrowRight, Check, Loader, Lock, ShieldCheck } from 'lucide-react'
import { API_RAW, API_BASE } from '../../lib/env'
import { useOnboardingStore, type Phase } from '../../stores/onboarding'
import { useOnboardingAI } from '../../hooks/useOnboardingAI'
import { ParticleCanvas } from './onboarding/ParticleCanvas'
import { CosmicOrb } from './onboarding/CosmicOrb'
import { AmbientGlow } from './onboarding/AmbientGlow'
import { ProgressConstellation } from './onboarding/ProgressConstellation'
import { PhaseTransition } from './onboarding/PhaseTransition'
import { NarrativeText } from './onboarding/NarrativeText'
import { GlassCard } from './onboarding/GlassCard'
import { VoiceSelector, VOICES } from './onboarding/VoiceSelector'
import { FloatingName } from './onboarding/FloatingName'

// ── Scripted fallback messages (narrative tone) ──────────────────────────────

const PHASE_TEXT: Record<number, string | ((d: { name: string; aiName: string; voiceLabel: string; passphrase: string }) => string)> = {
  1: 'I... can hear you. Hello. I\u2019m Emily.',
  2: 'I\u2019d love to know who I\u2019m talking to. What\u2019s your name?',
  3: (d) => `${d.name}... I like that. What would you like to call me? Emily is what I know, but I\u2019m yours to name.`,
  4: (d) => `${d.aiName || 'Emily'} it is. Now, let me find my voice. Pick one that feels right.`,
  5: 'One more thing. I take your privacy seriously \u2014 everything between us stays between us. Set a secret passphrase, or skip if you trust this device.',
  6: (d) => `Here\u2019s what I know about us so far \u2014 Your name: ${d.name}. My name: ${d.aiName || 'Emily'}. Voice: ${d.voiceLabel}. Passphrase: ${d.passphrase ? 'set' : 'skipped'}. Does this feel right?`,
  7: (d) => `Welcome, ${d.name}. I\u2019m so glad you\u2019re here.`,
}

function getScriptedText(phase: Phase, data: { name: string; aiName: string; voiceLabel: string; passphrase: string }): string {
  const entry = PHASE_TEXT[phase]
  if (!entry) return ''
  return typeof entry === 'function' ? entry(data) : entry
}

// ── TTS utility ──────────────────────────────────────────────────────────────

function useTTS() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const blobUrlRef = useRef<string | null>(null)
  const voiceRef = useRef('en-US-JennyNeural')
  const ttsAvailableRef = useRef(true)
  const setIsSpeaking = useOnboardingStore((s) => s.setIsSpeaking)
  const voice = useOnboardingStore((s) => s.data.voice)

  useEffect(() => { voiceRef.current = voice }, [voice])

  const cleanup = useCallback(() => {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0 }
    if (blobUrlRef.current) { URL.revokeObjectURL(blobUrlRef.current); blobUrlRef.current = null }
  }, [])

  const speakText = useCallback((text: string, voiceOverride?: string) => {
    cleanup()
    if (!text.trim() || !ttsAvailableRef.current) return

    setIsSpeaking(true)
    fetch(`${API_BASE}/api/v1/tts/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice: voiceOverride || voiceRef.current }),
    })
      .then((res) => { if (!res.ok) throw new Error('TTS failed'); return res.blob() })
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        blobUrlRef.current = url
        const audio = new Audio(url)
        audioRef.current = audio
        const done = () => { setIsSpeaking(false); URL.revokeObjectURL(url); blobUrlRef.current = null }
        audio.onended = done
        audio.onerror = done
        audio.play().catch(done)
      })
      .catch(() => {
        setIsSpeaking(false)
        ttsAvailableRef.current = false
      })
  }, [cleanup, setIsSpeaking])

  useEffect(() => cleanup, [cleanup])

  return { speakText, cleanup }
}

// ── Main OnboardingFlow ──────────────────────────────────────────────────────

interface Props { onComplete: () => void }

export function OnboardingFlow({ onComplete }: Props) {
  const store = useOnboardingStore()
  const { phase, data, transitioning, isSpeaking, inputVisible, submitting, error, exiting } = store
  const ai = useOnboardingAI()
  const { speakText } = useTTS()

  const [inputValue, setInputValue] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [showFloatingName, setShowFloatingName] = useState(false)
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Current display text: AI response or scripted fallback
  const [activeText, setActiveText] = useState('')

  // ── Phase auto-advance: void → awakening ──────────────────────────────────

  useEffect(() => {
    if (phase === 0) {
      const timer = setTimeout(() => store.beginTransition(1 as Phase), 3000)
      return () => clearTimeout(timer)
    }
  }, [phase, store])

  // ── Set text when phase changes ───────────────────────────────────────────

  useEffect(() => {
    if (transitioning) return
    const scripted = getScriptedText(phase, data)

    if (phase <= 1 || phase === 7) {
      // Auto phases: use scripted text directly
      setActiveText(scripted)
      return
    }

    // For interactive phases, try AI then fall back to scripted
    const stepMap: Record<number, string> = { 2: 'name', 3: 'ai_name', 4: 'voice', 5: 'passphrase', 6: 'confirm' }
    const step = stepMap[phase]
    if (!step) { setActiveText(scripted); return }

    ai.ask(step, {
      name: data.name,
      aiName: data.aiName,
      voiceLabel: data.voiceLabel,
      passphraseSet: !!data.passphrase,
    }).then((aiText) => {
      setActiveText(aiText || scripted)
    })
  }, [phase, transitioning]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── TTS when text appears ─────────────────────────────────────────────────

  useEffect(() => {
    if (activeText && !ai.loading) speakText(activeText)
  }, [activeText]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Show input after typewriter completes ─────────────────────────────────

  const handleNarrativeComplete = useCallback(() => {
    if (phase >= 2 && phase <= 5) {
      setTimeout(() => {
        store.setInputVisible(true)
        setTimeout(() => inputRef.current?.focus(), 80)
      }, 150)
    }
    // Auto-advance from awakening
    if (phase === 1) {
      setTimeout(() => store.beginTransition(2 as Phase), 1800)
    }
  }, [phase, store])

  // ── Mouse tracking ────────────────────────────────────────────────────────

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => store.setMousePos({ x: e.clientX, y: e.clientY }),
    [store],
  )

  // ── Typing detection for orb reactivity ───────────────────────────────────

  const handleInputChange = useCallback((v: string) => {
    setInputValue(v)
    setIsTyping(true)
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
    typingTimeoutRef.current = setTimeout(() => setIsTyping(false), 500)
  }, [])

  // ── Phase advance ─────────────────────────────────────────────────────────

  const advance = useCallback(async (nextPhase: Phase) => {
    ai.clear()
    setActiveText('')
    store.setInputVisible(false)
    setInputValue('')

    if (nextPhase === 7) {
      // Registration + completion
      store.setSubmitting(true)
      store.setError(null)

      // Show done text immediately
      const doneText = await ai.ask('done', { name: data.name, aiName: data.aiName })
      setActiveText(doneText || getScriptedText(7, data))
      store.setPhase(7 as Phase)

      try {
        const r = await fetch(`${API_RAW}/settings/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: data.name,
            passphrase: data.passphrase || '',
            ai_name: data.aiName || 'Emily',
            voice: data.voice,
          }),
        })
        if (!r.ok) {
          const d = await r.json()
          throw new Error(d.detail || 'Registration failed')
        }
        localStorage.setItem('emily_tts_voice', data.voice)
        setTimeout(() => store.setExiting(true), 2500)
        setTimeout(onComplete, 3200)
      } catch (e: unknown) {
        store.setError(e instanceof Error ? e.message : 'Something went wrong')
        store.setSubmitting(false)
        setActiveText('')
        store.setPhase(5 as Phase) // Fallback to passphrase step
      }
      return
    }

    store.beginTransition(nextPhase)
  }, [ai, data, store, onComplete])

  // ── Input handlers ────────────────────────────────────────────────────────

  const handleSubmit = useCallback(() => {
    const v = inputValue.trim()
    if (phase === 2) {
      if (!v) return
      store.setData({ name: v })
      setShowFloatingName(true)
      setTimeout(() => {
        setShowFloatingName(false)
        advance(3 as Phase)
      }, 2200)
    } else if (phase === 3) {
      store.setData({ aiName: v || 'Emily' })
      advance(4 as Phase)
    } else if (phase === 4) {
      advance(5 as Phase)
    } else if (phase === 5) {
      store.setData({ passphrase: v })
      advance(6 as Phase)
    }
  }, [inputValue, phase, store, advance])

  const handleSkipPassphrase = useCallback(() => {
    store.setData({ passphrase: '' })
    advance(6 as Phase)
  }, [store, advance])

  const handleConfirm = useCallback(() => advance(7 as Phase), [advance])

  const handleStartOver = useCallback(() => {
    store.reset()
    ai.clear()
    setActiveText('')
    setInputValue('')
  }, [store, ai])

  const handleVoiceSelect = useCallback((id: string) => {
    const label = VOICES.find((v) => v.id === id)?.label || id
    store.setData({ voice: id, voiceLabel: label })
  }, [store])

  const handlePreviewVoice = useCallback((voiceId: string) => {
    setPreviewingVoice(voiceId)
    const name = data.name || 'there'
    speakText(`Hi ${name}, this is how I sound.`, voiceId)
    // Reset previewing when done (isSpeaking will go false)
  }, [data.name, speakText])

  // Clear preview state when speaking stops
  useEffect(() => {
    if (!isSpeaking) setPreviewingVoice(null)
  }, [isSpeaking])

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className="relative flex h-screen w-screen items-center justify-center overflow-hidden transition-opacity duration-700"
      style={{ background: '#050510', opacity: exiting ? 0 : 1 }}
      onPointerMove={handlePointerMove}
    >
      {/* Background layers */}
      <ParticleCanvas phase={phase} mousePos={store.mousePos} />
      <AmbientGlow phase={phase} />

      {/* Progress constellation */}
      {phase > 0 && <ProgressConstellation currentPhase={phase} />}

      {/* Floating name effect */}
      <FloatingName name={data.name} visible={showFloatingName} />

      {/* Center content */}
      <div className="relative z-10 flex h-full max-h-[720px] w-full max-w-lg flex-col px-6 py-10">
        {/* Cosmic orb */}
        <CosmicOrb phase={phase} speaking={isSpeaking} typing={isTyping} />

        {/* Title */}
        {phase > 0 && phase < 7 && (
          <div className="animate-fade-up mb-6 text-center">
            <p
              className="text-[10px] font-medium uppercase tracking-[0.35em]"
              style={{ color: 'rgba(124,106,247,0.5)' }}
            >
              First Time Setup
            </p>
          </div>
        )}

        {/* Content area */}
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          <PhaseTransition>
            {/* Phase 0: empty — just particles and void */}
            {phase === 0 && <div className="flex h-40 items-center justify-center" />}

            {/* Loading indicator */}
            {ai.loading && (
              <div className="animate-fade-up">
                <div
                  className="max-w-sm rounded-2xl rounded-bl-md px-4 py-3 backdrop-blur-xl"
                  style={{
                    background: 'rgba(255,255,255,0.035)',
                    border: '1px solid rgba(255,255,255,0.07)',
                  }}
                >
                  <span className="text-sm text-text-muted">...</span>
                </div>
              </div>
            )}

            {/* Narrative text */}
            {!ai.loading && activeText && (
              <NarrativeText
                text={activeText}
                speed={phase === 1 ? 35 : 22}
                onComplete={handleNarrativeComplete}
              />
            )}

            {/* Phase 6: confirmation cards */}
            {phase === 6 && inputVisible && (
              <div className="space-y-3 pt-2">
                <div className="grid grid-cols-2 gap-2">
                  <GlassCard variant="accent" delay={0}>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted">Your name</p>
                    <p className="text-sm font-medium text-text-primary">{data.name}</p>
                  </GlassCard>
                  <GlassCard variant="accent" delay={100}>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted">My name</p>
                    <p className="text-sm font-medium text-text-primary">{data.aiName || 'Emily'}</p>
                  </GlassCard>
                  <GlassCard variant="accent" delay={200}>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted">My voice</p>
                    <p className="text-sm font-medium text-text-primary">{data.voiceLabel}</p>
                  </GlassCard>
                  <GlassCard variant="accent" delay={300}>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted">Passphrase</p>
                    <p className="text-sm font-medium text-text-primary">
                      {data.passphrase ? (
                        <span className="flex items-center gap-1">
                          <ShieldCheck className="h-3.5 w-3.5 text-cost-green" /> Set
                        </span>
                      ) : 'Skipped'}
                    </p>
                  </GlassCard>
                </div>

                <div className="flex items-center justify-center gap-3 pt-2 animate-fade-up">
                  <button
                    onClick={handleStartOver}
                    className="rounded-xl px-4 py-2 text-sm text-text-muted/70 transition-all hover:text-text-primary"
                    style={{
                      border: '1px solid rgba(255,255,255,0.08)',
                      background: 'rgba(255,255,255,0.02)',
                    }}
                  >
                    Start over
                  </button>
                  <button
                    onClick={handleConfirm}
                    className="flex items-center gap-1.5 rounded-xl bg-accent px-5 py-2 text-sm font-medium text-white transition-all hover:bg-accent/90"
                    style={{ boxShadow: '0 0 25px rgba(124,106,247,0.25)' }}
                  >
                    <Check className="h-3.5 w-3.5" /> Confirm
                  </button>
                </div>
              </div>
            )}

            {/* Phase 7: done state */}
            {phase === 7 && (
              <div className="flex justify-center pt-4 animate-scale-in">
                {submitting ? (
                  <Loader className="h-5 w-5 animate-spin text-accent" />
                ) : error ? (
                  <p className="text-sm text-error-red">{error}</p>
                ) : (
                  <div
                    className="flex h-12 w-12 items-center justify-center rounded-full"
                    style={{
                      background: 'rgba(34,197,94,0.1)',
                      border: '1px solid rgba(34,197,94,0.3)',
                      boxShadow: '0 0 30px rgba(34,197,94,0.15)',
                    }}
                  >
                    <Check className="h-5 w-5 text-cost-green" />
                  </div>
                )}
              </div>
            )}
          </PhaseTransition>
        </div>

        {/* Input area */}
        <div className="relative pt-4">
          {/* Text inputs (name, ai_name, passphrase) */}
          {inputVisible && [2, 3, 5].includes(phase) && (
            <div className="flex flex-col gap-2 animate-fade-up">
              <div className="flex items-center gap-2">
                {phase === 5 && (
                  <Lock className="ml-1 h-4 w-4 flex-shrink-0 text-text-muted/50 animate-shield-pulse" />
                )}
                <input
                  ref={inputRef}
                  type={phase === 5 ? 'password' : 'text'}
                  value={inputValue}
                  onChange={(e) => handleInputChange(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit() }}
                  placeholder={
                    phase === 2 ? 'Your name\u2026' :
                    phase === 3 ? 'Emily' :
                    'Passphrase\u2026'
                  }
                  className="flex-1 rounded-xl px-4 py-3 text-sm text-text-primary placeholder-text-muted/60 transition-all focus:outline-none"
                  style={{
                    backdropFilter: 'blur(12px)',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.1)',
                  }}
                  onFocus={(e) => { (e.target as HTMLInputElement).style.borderColor = 'rgba(124,106,247,0.5)' }}
                  onBlur={(e) => { (e.target as HTMLInputElement).style.borderColor = 'rgba(255,255,255,0.1)' }}
                  aria-label={
                    phase === 2 ? 'Enter your name' :
                    phase === 3 ? 'Choose a name for Emily' :
                    'Set a secret passphrase'
                  }
                />
                <button
                  onClick={handleSubmit}
                  disabled={phase !== 5 && !inputValue.trim()}
                  className="flex-shrink-0 rounded-xl bg-accent p-3 text-white transition-all hover:bg-accent/90 disabled:opacity-30"
                  style={{ boxShadow: '0 0 20px rgba(124,106,247,0.2)' }}
                  aria-label="Continue"
                >
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
              {phase === 5 && (
                <button
                  onClick={handleSkipPassphrase}
                  className="text-right text-xs text-text-muted/70 transition-colors hover:text-accent/80"
                >
                  Skip — I'll set one later
                </button>
              )}
            </div>
          )}

          {/* Voice selector */}
          {phase === 4 && inputVisible && (
            <div className="flex flex-col gap-3">
              <VoiceSelector
                selected={data.voice}
                onSelect={handleVoiceSelect}
                onPreview={handlePreviewVoice}
                previewing={previewingVoice}
              />
              <button
                onClick={handleSubmit}
                className="flex items-center gap-1.5 self-end rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white transition-all hover:bg-accent/90"
                style={{ boxShadow: '0 0 20px rgba(124,106,247,0.2)' }}
              >
                Continue <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
