import type { Agent } from '../../stores/brain'

interface Props {
  agent: Agent
}

export function AgentCard({ agent }: Props) {
  const isCore = agent.type === 'core'
  const isActive = agent.status === 'active' || agent.status === 'running'

  return (
    <div className={`bg-surface-raised border rounded-xl p-3 transition-all ${
      isCore ? 'border-accent/30' : 'border-border'
    }`}>
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
          isActive ? 'bg-cost-green animate-heartbeat' : 'bg-text-muted'
        }`} />
        <span className="text-sm font-semibold text-text-primary truncate">{agent.name}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ml-auto flex-shrink-0 ${
          isCore
            ? 'bg-accent/10 text-accent'
            : 'bg-surface-hover text-text-muted'
        }`}>
          {agent.type}
        </span>
      </div>
      <p className="text-xs text-text-muted truncate">{agent.role}</p>
    </div>
  )
}
