import type { Agent } from '../../stores/brain'

interface AgentCardProps {
  agent: Agent
}

export function AgentCard(props: AgentCardProps) {
  const isCore = () => props.agent.type === 'core'
  const isActive = () => props.agent.status === 'active' || props.agent.status === 'running'

  return (
    <div
      class="rounded-xl p-3 transition-all"
      style={{
        background: 'var(--color-surface-raised)',
        border: `1px solid ${isCore() ? 'oklch(0.72 0.17 162 / 0.3)' : 'var(--color-border)'}`,
      }}
    >
      <div class="flex items-center gap-2 mb-1.5">
        <span
          class={`w-2 h-2 rounded-full flex-shrink-0 ${isActive() ? 'animate-heartbeat' : ''}`}
          style={{ background: isActive() ? 'var(--color-cost-green)' : 'var(--color-text-muted)' }}
        />
        <span class="text-sm font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
          {props.agent.name}
        </span>
        <span
          class="ml-auto flex-shrink-0 px-1.5 py-0.5 rounded-full font-medium"
          style={{
            'font-size': '10px',
            background: isCore() ? 'oklch(0.72 0.17 162 / 0.1)' : 'var(--color-surface-hover)',
            color: isCore() ? 'var(--color-accent)' : 'var(--color-text-muted)',
          }}
        >
          {props.agent.type}
        </span>
      </div>
      <p class="text-xs truncate" style={{ color: 'var(--color-text-muted)' }}>
        {props.agent.role}
      </p>
    </div>
  )
}
