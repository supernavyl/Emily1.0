import { useChatStore } from '../../stores/chat'
import { Clock, Cpu, Coins, Layers } from 'lucide-react'

export function ReasoningMetrics() {
  const lastUsage = useChatStore((s) => s.lastUsage)
  const reasoningSteps = useChatStore((s) => s.reasoningSteps)
  const isStreaming = useChatStore((s) => s.isStreaming)

  const totalStepTokens = reasoningSteps.reduce(
    (sum, s) => sum + ((s.metadata?.tokens as number) || 0), 0,
  )
  const modelsUsed = [...new Set(reasoningSteps.map((s) => s.model).filter(Boolean))]

  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-surface border-t border-border text-xs text-text-muted">
      {lastUsage && (
        <>
          <div className="flex items-center gap-1" title="Latency">
            <Clock className="w-3 h-3" />
            <span>{lastUsage.latency_ms}ms</span>
          </div>
          <div className="flex items-center gap-1" title="Tokens">
            <Cpu className="w-3 h-3" />
            <span>{lastUsage.tokens_in + lastUsage.tokens_out + (lastUsage.tokens_thinking || 0)}</span>
          </div>
          {lastUsage.cost_usd > 0 && (
            <div className="flex items-center gap-1" title="Cost">
              <Coins className="w-3 h-3" />
              <span>${lastUsage.cost_usd.toFixed(4)}</span>
            </div>
          )}
        </>
      )}
      {reasoningSteps.length > 0 && (
        <div className="flex items-center gap-1" title="Reasoning steps">
          <Layers className="w-3 h-3" />
          <span>{reasoningSteps.length} steps</span>
        </div>
      )}
      {modelsUsed.length > 1 && (
        <span className="text-accent">{modelsUsed.length} models</span>
      )}
      {isStreaming && (
        <span className="ml-auto flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
          Active
        </span>
      )}
    </div>
  )
}
