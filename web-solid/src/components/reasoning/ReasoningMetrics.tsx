import { Show, createMemo } from 'solid-js'
import { Clock, Cpu, Coins, Layers } from 'lucide-solid'
import { chatState } from '../../stores/chat'

export function ReasoningMetrics() {
  const totalStepTokens = createMemo(() =>
    chatState.reasoningSteps.reduce(
      (sum, s) => sum + ((s.metadata?.tokens as number) || 0), 0,
    ),
  )

  const modelsUsed = createMemo(() =>
    [...new Set(chatState.reasoningSteps.map((s) => s.model).filter(Boolean))],
  )

  return (
    <div
      class="flex items-center gap-3 px-3 py-2 text-xs"
      style={{
        background: 'var(--color-surface)',
        'border-top': '1px solid var(--color-border)',
        color: 'var(--color-text-muted)',
      }}
    >
      <Show when={chatState.lastUsage}>
        {(usage) => (
          <>
            <div class="flex items-center gap-1" title="Latency">
              <Clock size={12} />
              <span>{usage().latency_ms}ms</span>
            </div>
            <div class="flex items-center gap-1" title="Tokens">
              <Cpu size={12} />
              <span>{usage().tokens_in + usage().tokens_out + (usage().tokens_thinking || 0)}</span>
            </div>
            <Show when={usage().cost_usd > 0}>
              <div class="flex items-center gap-1" title="Cost">
                <Coins size={12} />
                <span>${usage().cost_usd.toFixed(4)}</span>
              </div>
            </Show>
          </>
        )}
      </Show>
      <Show when={chatState.reasoningSteps.length > 0}>
        <div class="flex items-center gap-1" title="Reasoning steps">
          <Layers size={12} />
          <span>{chatState.reasoningSteps.length} steps</span>
        </div>
      </Show>
      <Show when={modelsUsed().length > 1}>
        <span style={{ color: 'var(--color-accent)' }}>{modelsUsed().length} models</span>
      </Show>
      <Show when={chatState.isStreaming}>
        <span class="ml-auto flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-accent)' }} />
          Active
        </span>
      </Show>
    </div>
  )
}
