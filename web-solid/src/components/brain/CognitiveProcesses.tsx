import { Show, For } from 'solid-js'
import { brainState } from '../../stores/brain'
import { FsmStateDiagram } from './FsmStateDiagram'
import { AgentCard } from './AgentCard'

export function CognitiveProcesses() {
  const fsmState = () => brainState.status?.fsm_state || 'IDLE'
  const fsmHistory = () => brainState.status?.fsm_history || []
  const metrics = () => brainState.status?.metrics || {}

  return (
    <div class="p-6 space-y-6 animate-scale-in">
      {/* FSM Diagram */}
      <FsmStateDiagram currentState={fsmState()} history={fsmHistory()} />

      {/* Agent Grid */}
      <div>
        <h3
          class="text-xs font-semibold uppercase mb-3"
          style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
        >
          Agent Network
        </h3>
        <div class="grid grid-cols-3 gap-3">
          <Show
            when={brainState.agents.length > 0}
            fallback={
              <div class="col-span-3 text-center text-xs py-8" style={{ color: 'var(--color-text-muted)' }}>
                No agents loaded
              </div>
            }
          >
            <For each={brainState.agents}>
              {(agent) => <AgentCard agent={agent} />}
            </For>
          </Show>
        </div>
      </div>

      {/* Priority Queue Stats */}
      <div
        class="rounded-xl p-4"
        style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
      >
        <h3
          class="text-xs font-semibold uppercase mb-3"
          style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
        >
          Task Processing
        </h3>
        <div class="grid grid-cols-5 gap-3">
          <For each={[
            { label: 'P0 Emergency', color: 'var(--color-error)', desc: 'Unbounded' },
            { label: 'P1 Realtime', color: 'var(--color-warning)', desc: '8 concurrent' },
            { label: 'P2 Active', color: 'var(--color-accent)', desc: '4 concurrent' },
            { label: 'P3 Background', color: 'var(--color-phase-comparing)', desc: '2 concurrent' },
            { label: 'P4 Idle', color: 'var(--color-text-muted)', desc: '1 concurrent' },
          ]}>
            {(item) => (
              <div class="text-center">
                <div
                  class="w-3 h-3 rounded-full mx-auto mb-1"
                  style={{ 'background-color': item.color }}
                />
                <div class="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  {item.label}
                </div>
                <div style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                  {item.desc}
                </div>
              </div>
            )}
          </For>
        </div>
        <div class="flex items-center gap-4 mt-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <span>
            Queue depth: <span class="font-mono" style={{ color: 'var(--color-text-primary)' }}>{metrics().agent_queue || 0}</span>
          </span>
          <span>
            Wake words: <span class="font-mono" style={{ color: 'var(--color-text-primary)' }}>{metrics().wake_words || 0}</span>
          </span>
          <span>
            STT errors: <span class="font-mono" style={{ color: 'var(--color-text-primary)' }}>{metrics().stt_errors || 0}</span>
          </span>
        </div>
      </div>
    </div>
  )
}
