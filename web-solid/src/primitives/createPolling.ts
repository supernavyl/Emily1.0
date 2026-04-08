import { createSignal, onMount, onCleanup } from 'solid-js'
import type { Accessor } from 'solid-js'

interface PollingResult<T> {
  data: Accessor<T | null>
  loading: Accessor<boolean>
  error: Accessor<string | null>
  refetch: () => void
}

export function createPolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): PollingResult<T> {
  const [data, setData] = createSignal<T | null>(null)
  const [loading, setLoading] = createSignal(false)
  const [error, setError] = createSignal<string | null>(null)
  let intervalId: ReturnType<typeof setInterval> | null = null

  async function doFetch(showLoading: boolean): Promise<void> {
    if (showLoading) setLoading(true)
    try {
      const result = await fetcher()
      setData(() => result)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  function refetch(): void {
    void doFetch(false)
  }

  onMount(() => {
    void doFetch(true)
    intervalId = setInterval(() => {
      void doFetch(false)
    }, intervalMs)
  })

  onCleanup(() => {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
  })

  return { data, loading, error, refetch }
}
