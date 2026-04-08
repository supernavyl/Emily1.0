import { createMemo, For, Show } from 'solid-js'
import { brainState } from '../../stores/brain'
import { DonutChart } from '../charts/DonutChart'

const PROVIDER_COLORS: Record<string, string> = {
  ollama:    'var(--color-text-secondary)',
  anthropic: 'var(--color-warning-amber)',
  openai:    'var(--color-cost-green)',
  google:    'var(--color-phase-comparing)',
  xai:       'var(--color-phase-comparing)',
  deepseek:  'var(--color-phase-analyzing)',
  groq:      'var(--color-error-red)',
  mistral:   'var(--color-warning-amber)',
  tabbyapi:  'var(--color-accent)',
  local:     'var(--color-cost-green)',
}

export function ModelFleet() {
  const grouped = createMemo(() => {
    const result: Record<string, { display: string; tier: string; thinking: boolean; vision: boolean }[]> = {}
    for (const [key, m] of Object.entries(brainState.models)) {
      const p = m.provider || 'unknown'
      if (!result[p]) result[p] = []
      result[p].push({ display: m.display || key, tier: m.tier || '', thinking: m.thinking, vision: m.vision })
    }
    return result
  })

  const tierCounts = createMemo(() => {
    const acc: Record<string, number> = {}
    for (const m of Object.values(brainState.models)) {
      const t = m.tier || 'other'
      acc[t] = (acc[t] || 0) + 1
    }
    return acc
  })

  const donutSegments = createMemo(() =>
    Object.entries(tierCounts()).map(([tier, count]) => ({
      label: tier,
      value: count,
      color: tier === 'fast'       ? 'var(--color-phase-comparing)' :
             tier === 'smart'      ? 'var(--color-accent)' :
             tier === 'reasoning'  ? 'var(--color-warning-amber)' :
             tier === 'nano'       ? 'var(--color-cost-green)' :
             tier === 'voice_fast' ? 'var(--color-phase-considering)' :
             tier === 'vision'     ? 'var(--color-error-red)' :
             tier === 'embedding'  ? 'var(--color-text-muted)' : 'var(--color-text-muted)',
    })),
  )

  const totalModels = createMemo(() => Object.keys(brainState.models).length)

  return (
    <div class="p-6 space-y-6 animate-scale-in">
      <div class="grid grid-cols-3 gap-6">
        {/* Tier Distribution */}
        <div
          class="rounded-xl p-4 flex flex-col items-center"
          style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
        >
          <h3
            class="text-xs font-semibold uppercase mb-4 self-start"
            style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
          >
            Tier Distribution
          </h3>
          <DonutChart segments={donutSegments()} size={140} centerLabel={`${totalModels()}`} />
        </div>

        {/* Provider Grid */}
        <div class="col-span-2 space-y-3">
          <h3
            class="text-xs font-semibold uppercase"
            style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
          >
            Providers
          </h3>
          <div class="grid grid-cols-2 gap-3">
            <For each={Object.entries(grouped())}>
              {([provider, providerModels]) => (
                <div
                  class="rounded-xl p-3"
                  style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
                >
                  <div class="flex items-center gap-2 mb-2">
                    <span
                      class="w-2.5 h-2.5 rounded-full"
                      style={{ 'background-color': PROVIDER_COLORS[provider] || '#555' }}
                    />
                    <span
                      class="text-xs font-semibold uppercase"
                      style={{ color: PROVIDER_COLORS[provider] || '#888' }}
                    >
                      {provider}
                    </span>
                    <span class="ml-auto" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                      {providerModels.length} models
                    </span>
                  </div>
                  <div class="space-y-0.5">
                    <For each={providerModels.slice(0, 5)}>
                      {(m) => (
                        <div class="flex items-center gap-1.5 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                          <span class="truncate flex-1">{m.display}</span>
                          <Show when={m.thinking}>
                            <span
                              class="px-1 rounded"
                              style={{ 'font-size': '9px', background: 'oklch(0.72 0.17 162 / 0.2)', color: 'var(--color-phase-analyzing)' }}
                            >
                              think
                            </span>
                          </Show>
                          <Show when={m.vision}>
                            <span
                              class="px-1 rounded"
                              style={{ 'font-size': '9px', background: 'oklch(0.72 0.15 145 / 0.2)', color: 'var(--color-cost-green)' }}
                            >
                              vision
                            </span>
                          </Show>
                        </div>
                      )}
                    </For>
                    <Show when={providerModels.length > 5}>
                      <div style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                        +{providerModels.length - 5} more
                      </div>
                    </Show>
                  </div>
                </div>
              )}
            </For>
          </div>
        </div>
      </div>

      {/* Fleet Stats */}
      <div
        class="rounded-xl p-4"
        style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
      >
        <h3
          class="text-xs font-semibold uppercase mb-2"
          style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
        >
          Fleet Summary
        </h3>
        <div class="flex gap-6 text-xs">
          <span style={{ color: 'var(--color-text-secondary)' }}>
            Total: <span class="font-mono" style={{ color: 'var(--color-text-primary)' }}>{totalModels()}</span>
          </span>
          <span style={{ color: 'var(--color-text-secondary)' }}>
            Providers: <span class="font-mono" style={{ color: 'var(--color-text-primary)' }}>{Object.keys(grouped()).length}</span>
          </span>
          <span style={{ color: 'var(--color-text-secondary)' }}>
            Thinking: <span class="font-mono" style={{ color: 'var(--color-text-primary)' }}>
              {Object.values(brainState.models).filter((m) => m.thinking).length}
            </span>
          </span>
          <span style={{ color: 'var(--color-text-secondary)' }}>
            Vision: <span class="font-mono" style={{ color: 'var(--color-text-primary)' }}>
              {Object.values(brainState.models).filter((m) => m.vision).length}
            </span>
          </span>
        </div>
      </div>
    </div>
  )
}
