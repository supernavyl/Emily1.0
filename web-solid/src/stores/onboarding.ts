import { createStore } from 'solid-js/store'

export type Phase = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7

export interface OnboardingData {
  name: string
  aiName: string
  voice: string
  voiceLabel: string
  passphrase: string
  email: string
}

interface OnboardingState {
  phase: Phase
  prevPhase: Phase | null
  transitioning: boolean

  data: OnboardingData

  isSpeaking: boolean
  inputVisible: boolean
  submitting: boolean
  error: string | null
  exiting: boolean

  mousePos: { x: number; y: number } | null
}

const initialData: OnboardingData = {
  name: '',
  aiName: '',
  voice: 'en-US-JennyNeural',
  voiceLabel: 'Jenny',
  passphrase: '',
  email: '',
}

const [onboardingState, setOnboardingState] = createStore<OnboardingState>({
  phase: 0 as Phase,
  prevPhase: null,
  transitioning: false,

  data: { ...initialData },

  isSpeaking: false,
  inputVisible: false,
  submitting: false,
  error: null,
  exiting: false,
  mousePos: null,
})

export { onboardingState }

export function setPhase(p: Phase): void {
  setOnboardingState('phase', p)
}

export function beginTransition(to: Phase): void {
  setOnboardingState({
    transitioning: true,
    prevPhase: onboardingState.phase,
    inputVisible: false,
    phase: to,
  })
}

export function completeTransition(): void {
  setOnboardingState('transitioning', false)
}

export function setOnboardingData(partial: Partial<OnboardingData>): void {
  setOnboardingState('data', (prev) => ({ ...prev, ...partial }))
}

export function setIsSpeaking(v: boolean): void {
  setOnboardingState('isSpeaking', v)
}

export function setInputVisible(v: boolean): void {
  setOnboardingState('inputVisible', v)
}

export function setSubmitting(v: boolean): void {
  setOnboardingState('submitting', v)
}

export function setOnboardingError(e: string | null): void {
  setOnboardingState('error', e)
}

export function setExiting(v: boolean): void {
  setOnboardingState('exiting', v)
}

export function setMousePos(pos: { x: number; y: number } | null): void {
  setOnboardingState('mousePos', pos)
}

export function resetOnboarding(): void {
  setOnboardingState({
    phase: 0 as Phase,
    prevPhase: null,
    transitioning: false,
    data: { ...initialData },
    isSpeaking: false,
    inputVisible: false,
    submitting: false,
    error: null,
    exiting: false,
  })
}
