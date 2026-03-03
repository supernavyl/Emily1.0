import { useMemo, useRef, useEffect } from 'react'
import { useChatStore } from '../../stores/chat'

const EVENT_COLORS: Record<string, string> = {
  step_start: '#3b82f6',
  step_complete: '#22c55e',
  thinking: '#a855f7',
  model_switch: '#eab308',
  critique: '#f59e0b',
  branch: '#06b6d4',
  consensus: '#8b5cf6',
  escalation: '#ef4444',
}

export function ReasoningTimeline() {
  const reasoningSteps = useChatStore((s) => s.reasoningSteps)
  const skillProgress = useChatStore((s) => s.skillProgress)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Merge and sort all events by timestamp
  const events = useMemo(() => {
    const all = [
      ...reasoningSteps.map((s) => ({
        type: s.event_type,
        name: s.step_name,
        model: s.model,
        content: s.content,
        tokens: (s.metadata?.tokens as number) || 0,
        confidence: (s.metadata?.confidence as number) || undefined,
        time: s.timestamp,
      })),
      ...skillProgress.map((s) => ({
        type: 'skill_progress',
        name: `${s.skill_id}:${s.step_name}`,
        model: s.tier,
        content: s.content_preview,
        tokens: s.tokens,
        confidence: undefined,
        time: Date.now(),
      })),
    ]
    return all.sort((a, b) => a.time - b.time)
  }, [reasoningSteps, skillProgress])

  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events.length, isStreaming])

  if (events.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-muted text-xs">
        No reasoning events yet
      </div>
    )
  }

  const startTime = events[0]?.time || Date.now()

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto p-3">
      <div className="relative pl-6">
        {/* Vertical timeline line */}
        <div className="absolute left-2 top-0 bottom-0 w-px bg-border" />

        {events.map((event, i) => {
          const color = EVENT_COLORS[event.type] || '#555'
          const elapsed = event.time - startTime

          return (
            <div key={i} className="relative mb-3 last:mb-0">
              {/* Timeline dot */}
              <div
                className="absolute -left-4 top-1 w-2.5 h-2.5 rounded-full border-2 bg-surface"
                style={{ borderColor: color }}
              />

              <div className="flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-medium" style={{ backgroundColor: color + '20', color }}>
                      {event.type.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[10px] text-text-muted">{event.name}</span>
                    {event.model && (
                      <span className="text-[10px] text-text-muted/60">{event.model}</span>
                    )}
                    <span className="text-[10px] text-text-muted/40 ml-auto flex-shrink-0">
                      +{elapsed}ms
                    </span>
                  </div>

                  {event.content && (
                    <p className="text-[11px] text-text-secondary leading-relaxed line-clamp-2">
                      {event.content}
                    </p>
                  )}

                  <div className="flex items-center gap-2 mt-0.5">
                    {event.tokens > 0 && (
                      <span className="text-[10px] text-text-muted">{event.tokens} tok</span>
                    )}
                    {event.confidence !== undefined && (
                      <span className="text-[10px]" style={{ color: event.confidence >= 0.7 ? '#22c55e' : event.confidence >= 0.4 ? '#eab308' : '#ef4444' }}>
                        conf: {(event.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })}

        {isStreaming && (
          <div className="relative mb-0">
            <div className="absolute -left-4 top-1 w-2.5 h-2.5 rounded-full bg-accent animate-pulse" />
            <span className="text-[10px] text-accent">Processing...</span>
          </div>
        )}
      </div>
    </div>
  )
}
