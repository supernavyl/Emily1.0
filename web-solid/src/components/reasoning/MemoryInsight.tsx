import { createMemo, Show, For } from 'solid-js'
import { Database, Search } from 'lucide-solid'
import { chatState } from '../../stores/chat'

export function MemoryInsight() {
  const memoryEvents = createMemo(() =>
    chatState.reasoningSteps.filter(
      (s) =>
        s.step_name === 'retrieve' ||
        s.step_name === 'search' ||
        s.event_type === 'rag_retrieval',
    ),
  )

  return (
    <Show when={memoryEvents().length > 0} fallback={
      <div class="flex-1 flex items-center justify-center text-xs p-4" style={{ color: 'var(--color-text-muted)' }}>
        <div class="text-center">
          <Database size={32} style={{ margin: '0 auto 8px', opacity: 0.3, color: 'var(--color-text-muted)' }} />
          <p class="mb-1">No memory retrieval data</p>
          <p style={{ opacity: 0.6 }}>
            RAG retrieval and memory access will appear here during Research and Deep Think modes
          </p>
        </div>
      </div>
    }>
      <div class="flex-1 overflow-y-auto p-3 space-y-2">
        <For each={memoryEvents()}>
          {(event) => (
            <div class="rounded-lg p-3" style={{ border: '1px solid var(--color-border)' }}>
              <div class="flex items-center gap-2 mb-2">
                <Search size={14} style={{ color: 'var(--color-accent)' }} />
                <span class="text-xs font-medium" style={{ color: 'var(--color-text-primary)' }}>
                  {event.step_name}
                </span>
                <Show when={event.model}>
                  <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                    {event.model}
                  </span>
                </Show>
              </div>
              <Show when={event.content}>
                <div class="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--color-text-secondary)' }}>
                  {event.content}
                </div>
              </Show>
              <Show when={event.metadata?.relevance_scores}>
                <div class="mt-2 flex gap-1 flex-wrap">
                  <For each={event.metadata.relevance_scores as number[]}>
                    {(score) => (
                      <span
                        class="px-1.5 py-0.5 rounded"
                        style={{
                          'font-size': '10px',
                          background: 'var(--color-surface-hover)',
                          color: score >= 0.7
                            ? 'var(--color-cost-green)'
                            : score >= 0.4
                              ? 'var(--color-warning-amber)'
                              : 'var(--color-text-muted)',
                        }}
                      >
                        {(score * 100).toFixed(0)}%
                      </span>
                    )}
                  </For>
                </div>
              </Show>
            </div>
          )}
        </For>
      </div>
    </Show>
  )
}
