import { API_BASE, authHeaders } from '../lib/env'

export interface ReasoningStepEvent {
  event_type: string
  step_name: string
  model: string
  content: string
  metadata: Record<string, unknown>
}

export interface SkillProgressEvent {
  skill_id: string
  step_name: string
  step_index: number
  total_steps: number
  status: string
  tier: string
  content_preview: string
  tokens: number
  latency_ms: number
}

export interface SearchEvent {
  status: 'searching' | 'found' | 'reading' | 'done' | 'error'
  query?: string
  count?: number
  results?: Array<{ title: string; url: string }>
  sources?: Array<{ title: string; url: string }>
  url?: string
  title?: string
  message?: string
}

export interface SSECallbacks {
  onMeta?: (data: {
    model_key: string; model_id: string; provider: string; display: string;
    mode_id?: string; mode_display?: string; mode_icon?: string; reasoning_strategy?: string;
  }) => void
  onThinking?: (text: string) => void
  onSearch?: (data: SearchEvent) => void
  onText?: (text: string) => void
  onUsage?: (data: import('./types').UsageData) => void
  onError?: (message: string) => void
  onDone?: () => void
  onReasoningStep?: (data: ReasoningStepEvent) => void
  onSkillProgress?: (data: SkillProgressEvent) => void
}

export function streamChat(
  body: {
    message: string
    conversation_id?: string | null
    model_id?: string
    skill_id?: string
    mode_id?: string
    profile_id?: string
    messages?: Array<{ role: string; content: string }>
    web_search?: boolean
  },
  callbacks: SSECallbacks,
  signal?: AbortSignal,
): void {
  const run = async () => {
    const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
      signal,
    })

    if (!res.ok) {
      const text = await res.text()
      callbacks.onError?.(`HTTP ${res.status}: ${text}`)
      return
    }

    const reader = res.body?.getReader()
    if (!reader) return

    const decoder = new TextDecoder()
    let buffer = ''
    let doneFired = false

    const fireDone = () => {
      if (!doneFired) {
        doneFired = true
        callbacks.onDone?.()
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const raw = line.slice(6)
          try {
            const data = JSON.parse(raw)
            switch (eventType) {
              case 'meta':
                callbacks.onMeta?.(data)
                break
              case 'thinking':
                callbacks.onThinking?.(data.text)
                break
              case 'search':
                callbacks.onSearch?.(data)
                break
              case 'text':
                callbacks.onText?.(data.text)
                break
              case 'usage':
                callbacks.onUsage?.(data)
                break
              case 'error':
                callbacks.onError?.(data.message)
                break
              case 'reasoning_step':
                callbacks.onReasoningStep?.(data)
                break
              case 'skill_progress':
                callbacks.onSkillProgress?.(data)
                break
              case 'done':
                fireDone()
                break
            }
          } catch {
            // skip malformed JSON
          }
          eventType = ''
        }
      }
    }

    fireDone()
  }

  run().catch((err) => {
    if (err.name !== 'AbortError') {
      callbacks.onError?.(String(err))
    }
  })
}
