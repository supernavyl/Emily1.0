import { useMemo } from 'react'
import { useChatStore } from '../../stores/chat'

export function ModelComparison() {
  const reasoningSteps = useChatStore((s) => s.reasoningSteps)

  // Find consensus/model comparison steps
  const modelOutputs = useMemo(() => {
    return reasoningSteps.filter(
      (s) => s.event_type === 'step_complete' && s.step_name.startsWith('model_'),
    )
  }, [reasoningSteps])

  const consensusResult = useMemo(() => {
    return reasoningSteps.find(
      (s) => s.event_type === 'consensus' && s.step_name === 'complete',
    )
  }, [reasoningSteps])

  if (modelOutputs.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-muted text-xs p-4">
        <div className="text-center">
          <p className="mb-1">No multi-model comparison data</p>
          <p className="text-text-muted/60">Use Debate or Research mode with consensus strategy to compare models</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-3">
      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(modelOutputs.length, 3)}, 1fr)` }}>
        {modelOutputs.map((output, i) => (
          <div key={i} className="border border-border rounded-lg overflow-hidden">
            <div className="px-3 py-1.5 bg-surface-hover border-b border-border flex items-center justify-between">
              <span className="text-xs font-medium text-text-primary">{output.model || `Model ${i + 1}`}</span>
              {output.metadata?.tokens && (
                <span className="text-[10px] text-text-muted">{output.metadata.tokens as number} tok</span>
              )}
            </div>
            <div className="p-3 text-xs text-text-secondary leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto">
              {output.content}
            </div>
          </div>
        ))}
      </div>

      {consensusResult && (
        <div className="border border-accent/30 rounded-lg overflow-hidden">
          <div className="px-3 py-1.5 bg-accent/10 border-b border-accent/20">
            <span className="text-xs font-medium text-accent">Consensus Synthesis</span>
          </div>
          <div className="p-3 text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
            {consensusResult.content}
          </div>
        </div>
      )}
    </div>
  )
}
