import { createEffect, createMemo, Show, For } from 'solid-js'
import { chatState } from '../../stores/chat'

const EVENT_COLORS: Record<string, string> = {
  step_start: 'var(--color-phase-analyzing)',
  step_complete: 'var(--color-cost-green)',
  thinking: 'var(--color-phase-comparing)',
  model_switch: 'var(--color-warning-amber)',
  critique: 'var(--color-warning-amber)',
  branch: 'var(--color-accent)',
  consensus: 'var(--color-phase-concluding)',
  escalation: 'var(--color-error-red)',
}

interface TimelineEvent {
  type: string
  name: string
  model: string | undefined
  content: string
  tokens: number
  confidence: number | undefined
  time: number
}

export function ReasoningTimeline() {
  let scrollRef: HTMLDivElement | undefined

  const events = createMemo<TimelineEvent[]>(() => {
    const all: TimelineEvent[] = [
      ...chatState.reasoningSteps.map((s) => ({
        type: s.event_type,
        name: s.step_name,
        model: s.model || undefined,
        content: s.content,
        tokens: (s.metadata?.tokens as number) || 0,
        confidence: (s.metadata?.confidence as number) || undefined,
        time: s.timestamp,
      })),
      ...chatState.skillProgress.map((s) => ({
        type: 'skill_progress',
        name: `${s.skill_id}:${s.step_name}`,
        model: s.tier || undefined,
        content: s.content_preview,
        tokens: s.tokens,
        confidence: undefined,
        time: Date.now(),
      })),
    ]
    return all.sort((a, b) => a.time - b.time)
  })

  createEffect(() => {
    const _ = events().length
    if (chatState.isStreaming && scrollRef) {
      scrollRef.scrollTop = scrollRef.scrollHeight
    }
  })

  const startTime = createMemo(() => events()[0]?.time || Date.now())

  return (
    <Show when={events().length > 0} fallback={
      <div class="flex-1 flex items-center justify-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
        No reasoning events yet
      </div>
    }>
      <div ref={scrollRef} class="flex-1 overflow-y-auto p-3">
        <div class="relative" style={{ 'padding-left': '24px' }}>
          {/* Vertical timeline line */}
          <div
            class="absolute top-0 bottom-0"
            style={{ left: '8px', width: '1px', background: 'var(--color-border)' }}
          />

          <For each={events()}>
            {(event) => {
              const color = () => EVENT_COLORS[event.type] || 'var(--color-text-muted)'
              const elapsed = () => event.time - startTime()
              return (
                <div class="relative mb-3 last:mb-0">
                  {/* Timeline dot */}
                  <div
                    class="absolute w-2.5 h-2.5 rounded-full"
                    style={{
                      left: '-16px',
                      top: '4px',
                      'border': `2px solid ${color()}`,
                      background: 'var(--color-surface)',
                    }}
                  />

                  <div class="flex items-start gap-2">
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2 mb-0.5">
                        <span
                          class="px-1.5 py-0.5 rounded font-medium"
                          style={{
                            'font-size': '10px',
                            'background-color': `${color()}20`,
                            color: color(),
                          }}
                        >
                          {event.type.replace(/_/g, ' ')}
                        </span>
                        <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                          {event.name}
                        </span>
                        <Show when={event.model}>
                          <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)', opacity: 0.6 }}>
                            {event.model}
                          </span>
                        </Show>
                        <span
                          class="ml-auto flex-shrink-0"
                          style={{ 'font-size': '10px', color: 'var(--color-text-muted)', opacity: 0.4 }}
                        >
                          +{elapsed()}ms
                        </span>
                      </div>

                      <Show when={event.content}>
                        <p
                          class="leading-relaxed"
                          style={{
                            'font-size': '11px',
                            color: 'var(--color-text-secondary)',
                            display: '-webkit-box',
                            '-webkit-line-clamp': '2',
                            '-webkit-box-orient': 'vertical',
                            overflow: 'hidden',
                          }}
                        >
                          {event.content}
                        </p>
                      </Show>

                      <div class="flex items-center gap-2 mt-0.5">
                        <Show when={event.tokens > 0}>
                          <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                            {event.tokens} tok
                          </span>
                        </Show>
                        <Show when={event.confidence !== undefined}>
                          <span style={{
                            'font-size': '10px',
                            color: event.confidence! >= 0.7
                              ? 'var(--color-cost-green)'
                              : event.confidence! >= 0.4
                                ? 'var(--color-warning-amber)'
                                : 'var(--color-error-red)',
                          }}>
                            conf: {(event.confidence! * 100).toFixed(0)}%
                          </span>
                        </Show>
                      </div>
                    </div>
                  </div>
                </div>
              )
            }}
          </For>

          <Show when={chatState.isStreaming}>
            <div class="relative mb-0">
              <div
                class="absolute w-2.5 h-2.5 rounded-full animate-pulse"
                style={{ left: '-16px', top: '4px', background: 'var(--color-accent)' }}
              />
              <span style={{ 'font-size': '10px', color: 'var(--color-accent)' }}>Processing...</span>
            </div>
          </Show>
        </div>
      </div>
    </Show>
  )
}
