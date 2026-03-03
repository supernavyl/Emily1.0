import { useChatStore } from '../../stores/chat'
import { Database, Search } from 'lucide-react'

export function MemoryInsight() {
  const reasoningSteps = useChatStore((s) => s.reasoningSteps)

  // Find memory/RAG retrieval events
  const memoryEvents = reasoningSteps.filter(
    (s) => s.step_name === 'retrieve' || s.step_name === 'search' || s.event_type === 'rag_retrieval',
  )

  if (memoryEvents.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-muted text-xs p-4">
        <div className="text-center">
          <Database className="w-8 h-8 mx-auto mb-2 text-text-muted/30" />
          <p className="mb-1">No memory retrieval data</p>
          <p className="text-text-muted/60">RAG retrieval and memory access will appear here during Research and Deep Think modes</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-2">
      {memoryEvents.map((event, i) => (
        <div key={i} className="border border-border rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Search className="w-3.5 h-3.5 text-accent" />
            <span className="text-xs font-medium text-text-primary">{event.step_name}</span>
            {event.model && (
              <span className="text-[10px] text-text-muted">{event.model}</span>
            )}
          </div>
          {event.content && (
            <div className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
              {event.content}
            </div>
          )}
          {event.metadata?.relevance_scores && (
            <div className="mt-2 flex gap-1 flex-wrap">
              {(event.metadata.relevance_scores as number[]).map((score, j) => (
                <span
                  key={j}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-surface-hover"
                  style={{ color: score >= 0.7 ? '#22c55e' : score >= 0.4 ? '#eab308' : '#888' }}
                >
                  {(score * 100).toFixed(0)}%
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
