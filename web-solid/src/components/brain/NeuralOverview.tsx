import { Show, For } from 'solid-js'
import { Activity, Users, Database, Clock, Zap, MessageSquare } from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'
import { brainState } from '../../stores/brain'
import { ProgressRing } from '../charts/ProgressRing'

export function NeuralOverview() {
  const fsmState = () => brainState.status?.fsm_state ?? 'IDLE'
  const res = () => brainState.status?.resources
  const emotions = () => brainState.status?.emotional_state ?? {}
  const metrics = () => brainState.status?.metrics ?? {}

  const formatUptime = (s?: number): string => {
    if (!s) return '0m'
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }

  const fsmBorderClass = () => {
    switch (fsmState()) {
      case 'IDLE': return 'border-text-muted'
      case 'SPEAKING': return 'border-cost-green'
      case 'PROCESSING': return 'border-warning-amber'
      case 'LISTENING': return 'border-phase-comparing'
      default: return 'border-accent'
    }
  }

  const statCards = (): { icon: LucideIcon; label: string; value: string | number; color: string }[] => [
    { icon: Users, label: 'Active Agents', value: brainState.agents.filter((a) => a.status === 'active' || a.status === 'running').length, color: 'text-accent' },
    { icon: Database, label: 'Working Memory', value: `${(brainState.workingMemory?.token_count ?? 0).toLocaleString()} tok`, color: 'text-phase-comparing' },
    { icon: Clock, label: 'Uptime', value: formatUptime(brainState.status?.uptime_s), color: 'text-cost-green' },
    { icon: MessageSquare, label: 'Conversations', value: metrics().conversations ?? 0, color: 'text-phase-analyzing' },
    { icon: Zap, label: 'LLM Requests', value: metrics().llm_requests ?? 0, color: 'text-warning-amber' },
    { icon: Activity, label: 'Tool Calls', value: metrics().tool_calls ?? 0, color: 'text-phase-concluding' },
  ]

  return (
    <div class="p-6 space-y-6 animate-scale-in">
      {/* FSM State Hero + Resource Rings */}
      <div class="flex items-center gap-8">
        {/* FSM State Circle */}
        <div class="flex flex-col items-center">
          <div class={`w-28 h-28 rounded-full border-2 flex items-center justify-center animate-pulse-ring ${fsmBorderClass()}`}>
            <div class="text-center">
              <div
                class="text-2xl font-bold font-mono"
                style={{ color: 'var(--color-text-primary)' }}
              >
                {fsmState()}
              </div>
              <div
                class="text-[10px] mt-0.5"
                style={{ color: 'var(--color-text-muted)' }}
              >
                FSM State
              </div>
            </div>
          </div>
        </div>

        {/* Resource Rings */}
        <div class="flex gap-6">
          <ProgressRing
            value={res()?.cpu_percent ?? 0}
            max={100}
            size={90}
            label="CPU"
            color={res()?.cpu_percent != null && res()!.cpu_percent > 80 ? 'var(--color-error-red)' : 'var(--color-accent)'}
          />
          <ProgressRing
            value={res()?.ram_used_gb ?? 0}
            max={res()?.ram_total_gb ?? 64}
            size={90}
            label="RAM"
            color="var(--color-phase-comparing)"
            format={(v) => `${v.toFixed(1)}G`}
          />
          <ProgressRing
            value={(res()?.vram_used_mb ?? 0) / 1024}
            max={(res()?.vram_total_mb ?? 24576) / 1024}
            size={90}
            label="VRAM"
            color="var(--color-cost-green)"
            format={(v) => `${v.toFixed(1)}G`}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div class="grid grid-cols-6 gap-3">
        <For each={statCards()}>
          {(card) => {
            const Icon = card.icon
            return (
              <div
                class="rounded-xl p-3"
                style={{
                  background: 'var(--color-surface-raised)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div class="flex items-center gap-1.5 mb-1">
                  <Icon size={14} class={card.color} />
                  <span
                    class="text-[10px] uppercase tracking-wider"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    {card.label}
                  </span>
                </div>
                <div
                  class="text-lg font-bold"
                  style={{ color: 'var(--color-text-primary)' }}
                >
                  {card.value}
                </div>
              </div>
            )
          }}
        </For>
      </div>

      {/* Emotion Dimensions */}
      <Show when={Object.keys(emotions()).length > 0}>
        <div
          class="rounded-xl p-4"
          style={{
            background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-border)',
          }}
        >
          <h3
            class="text-xs font-semibold uppercase tracking-wider mb-3"
            style={{ color: 'var(--color-text-muted)' }}
          >
            Emotional Dimensions
          </h3>
          <div class="grid grid-cols-4 gap-4">
            <For each={Object.entries(emotions())}>
              {([key, val]) => (
                <div class="flex flex-col gap-1">
                  <div class="flex justify-between items-center">
                    <span
                      class="text-xs capitalize"
                      style={{ color: 'var(--color-text-secondary)' }}
                    >
                      {key}
                    </span>
                    <span
                      class="text-xs font-mono"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {val.toFixed(2)}
                    </span>
                  </div>
                  <div
                    class="h-2 rounded-full overflow-hidden"
                    style={{ background: 'var(--color-surface)' }}
                  >
                    <div
                      class="h-full rounded-full"
                      style={{
                        width: `${Math.min(val * 100, 100)}%`,
                        'background-color': 'var(--color-accent)',
                        transition: 'width 700ms ease-out',
                      }}
                    />
                  </div>
                </div>
              )}
            </For>
          </div>
        </div>
      </Show>
    </div>
  )
}
