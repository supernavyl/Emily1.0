import { create } from 'zustand'

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

  // Mouse position for particle interaction
  mousePos: { x: number; y: number } | null

  setPhase: (p: Phase) => void
  beginTransition: (to: Phase) => void
  completeTransition: () => void
  setData: (partial: Partial<OnboardingData>) => void
  setIsSpeaking: (v: boolean) => void
  setInputVisible: (v: boolean) => void
  setSubmitting: (v: boolean) => void
  setError: (e: string | null) => void
  setExiting: (v: boolean) => void
  setMousePos: (pos: { x: number; y: number } | null) => void
  reset: () => void
}

const initialData: OnboardingData = {
  name: '',
  aiName: '',
  voice: 'en-US-JennyNeural',
  voiceLabel: 'Jenny',
  passphrase: '',
  email: '',
}

export const useOnboardingStore = create<OnboardingState>((set) => ({
  phase: 0,
  prevPhase: null,
  transitioning: false,

  data: { ...initialData },

  isSpeaking: false,
  inputVisible: false,
  submitting: false,
  error: null,
  exiting: false,
  mousePos: null,

  setPhase: (p) => set({ phase: p }),
  beginTransition: (to) =>
    set((s) => ({
      transitioning: true,
      prevPhase: s.phase,
      inputVisible: false,
      phase: to,
    })),
  completeTransition: () => set({ transitioning: false }),
  setData: (partial) =>
    set((s) => ({ data: { ...s.data, ...partial } })),
  setIsSpeaking: (v) => set({ isSpeaking: v }),
  setInputVisible: (v) => set({ inputVisible: v }),
  setSubmitting: (v) => set({ submitting: v }),
  setError: (e) => set({ error: e }),
  setExiting: (v) => set({ exiting: v }),
  setMousePos: (pos) => set({ mousePos: pos }),
  reset: () =>
    set({
      phase: 0,
      prevPhase: null,
      transitioning: false,
      data: { ...initialData },
      isSpeaking: false,
      inputVisible: false,
      submitting: false,
      error: null,
      exiting: false,
    }),
}))
