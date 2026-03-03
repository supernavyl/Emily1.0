import { useState, useCallback, useRef } from 'react'
import { API_RAW } from '../lib/env'

interface OnboardingAIOptions {
  name?: string
  aiName?: string
  voiceLabel?: string
  passphraseSet?: boolean
}

interface OnboardingAIReturn {
  text: string
  loading: boolean
  error: string | null
  isFallback: boolean
  ask: (step: string, opts?: OnboardingAIOptions) => Promise<string>
  clear: () => void
}

export function useOnboardingAI(): OnboardingAIReturn {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isFallback, setIsFallback] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const ask = useCallback(
    async (step: string, opts: OnboardingAIOptions = {}): Promise<string> => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setLoading(true)
      setError(null)
      setIsFallback(false)

      try {
        const res = await fetch(`${API_RAW}/onboarding/respond`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            step,
            name: opts.name ?? '',
            ai_name: opts.aiName ?? '',
            voice_label: opts.voiceLabel ?? '',
            passphrase_set: opts.passphraseSet ?? false,
          }),
          signal: controller.signal,
        })
        if (!res.ok) throw new Error('AI response failed')
        const data: { text: string; fallback?: boolean } = await res.json()
        const responseText = data.text || ''
        setIsFallback(data.fallback || false)
        setText(responseText)
        return responseText
      } catch (e) {
        if ((e as Error).name === 'AbortError') return ''
        setError((e as Error).message)
        return ''
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const clear = useCallback(() => {
    setText('')
    setError(null)
    setIsFallback(false)
  }, [])

  return { text, loading, error, isFallback, ask, clear }
}
