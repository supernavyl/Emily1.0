import { onMount, onCleanup } from 'solid-js'
import { pushEvents, setWsConnected, type BrainEvent } from '../stores/brain'
import { API_SECRET, PROD_TAURI } from '../lib/env'

const BACKOFF_BASE_MS = 2000
const BACKOFF_MULTIPLIER = 1.5
const BACKOFF_MAX_MS = 30000

function getWsUrl(categories?: string[]): string {
  const base = PROD_TAURI ? 'ws://127.0.0.1:8001' : ''
  const params = new URLSearchParams()
  if (API_SECRET) params.set('token', API_SECRET)
  if (categories?.length) params.set('cats', categories.join(','))
  const qs = params.toString()
  return `${base}/ws/brain${qs ? '?' + qs : ''}`
}

export function createBrainWS(categories?: string[]): void {
  let ws: WebSocket | null = null
  let buffer: BrainEvent[] = []
  let rafId: number | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let retryDelay = BACKOFF_BASE_MS
  let disposed = false

  function flush(): void {
    rafId = null
    if (buffer.length === 0) return
    pushEvents(buffer)
    buffer = []
  }

  function scheduleFlush(): void {
    if (rafId !== null) return
    rafId = requestAnimationFrame(flush)
  }

  function connect(): void {
    if (disposed) return

    const url = getWsUrl(categories)
    ws = new WebSocket(url)

    ws.onopen = () => {
      retryDelay = BACKOFF_BASE_MS
      setWsConnected(true)
    }

    ws.onmessage = (ev: MessageEvent) => {
      try {
        const parsed: BrainEvent | BrainEvent[] = JSON.parse(ev.data as string)
        if (Array.isArray(parsed)) {
          buffer.push(...parsed)
        } else {
          buffer.push(parsed)
        }
        scheduleFlush()
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      setWsConnected(false)
      if (disposed) return
      retryTimer = setTimeout(() => {
        retryDelay = Math.min(retryDelay * BACKOFF_MULTIPLIER, BACKOFF_MAX_MS)
        connect()
      }, retryDelay)
    }

    ws.onerror = () => {
      // onclose fires after onerror, reconnect handled there
    }
  }

  onMount(() => {
    connect()
  })

  onCleanup(() => {
    disposed = true
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    if (retryTimer !== null) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    // Flush remaining buffer
    if (buffer.length > 0) {
      pushEvents(buffer)
      buffer = []
    }
  })
}
