import { createMemo, Show, For } from 'solid-js'
import { chatState } from '../../stores/chat'

export function ModelComparison() {
  const modelOutputs = createMemo(() =>
    chatState.reasoningSteps.filter(
      (s) => s.event_type === 'step_complete' && s.step_name.startsWith('model_'),
    ),
  )

  const consensusResult = createMemo(() =>
    chatState.reasoningSteps.find(
      (s) => s.event_type === 'consensus' && s.step_name === 'complete',
    ),
  )

  return (
    <Show when={modelOutputs().length > 0} fallback={
      <div class="flex-1 flex items-center justify-center text-xs p-4" style={{ color: 'var(--color-text-muted)' }}>
        <div class="text-center">
          <p class="mb-1">No multi-model comparison data</p>
          <p style={{ opacity: 0.6 }}>Use Debate or Research mode with consensus strategy to compare models</p>
        </div>
      </div>
    }>
      <div class="flex-1 overflow-y-auto p-3 space-y-3">
        <div
          class="grid gap-3"
          style={{ 'grid-template-columns': `repeat(${Math.min(modelOutputs().length, 3)}, 1fr)` }}
        >
          <For each={modelOutputs()}>
            {(output, i) => (
              <div class="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
                <div
                  class="px-3 py-1.5 flex items-center justify-between"
                  style={{
                    background: 'var(--color-surface-hover)',
                    'border-bottom': '1px solid var(--color-border)',
                  }}
                >
                  <span class="text-xs font-medium" style={{ color: 'var(--color-text-primary)' }}>
                    {output.model || `Model ${i() + 1}`}
                  </span>
                  <Show when={output.metadata?.tokens}>
                    <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                      {output.metadata.tokens as number} tok
                    </span>
                  </Show>
                </div>
                <div
                  class="p-3 text-xs leading-relaxed whitespace-pre-wrap overflow-y-auto"
                  style={{ color: 'var(--color-text-secondary)', 'max-height': '300px' }}
                >
                  {output.content}
                </div>
              </div>
            )}
          </For>
        </div>

        <Show when={consensusResult()}>
          {(result) => (
            <div class="rounded-lg overflow-hidden" style={{ border: '1px solid oklch(0.72 0.17 162 / 0.3)' }}>
              <div
                class="px-3 py-1.5"
                style={{
                  background: 'oklch(0.72 0.17 162 / 0.1)',
                  'border-bottom': '1px solid oklch(0.72 0.17 162 / 0.2)',
                }}
              >
                <span class="text-xs font-medium" style={{ color: 'var(--color-accent)' }}>
                  Consensus Synthesis
                </span>
              </div>
              <div class="p-3 text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--color-text-secondary)' }}>
                {result().content}
              </div>
            </div>
          )}
        </Show>
      </div>
    </Show>
  )
}
