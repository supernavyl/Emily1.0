import { useBrainStore } from '../../stores/brain'
import { FsmStateDiagram } from './FsmStateDiagram'
import { AgentCard } from './AgentCard'

export function CognitiveProcesses() {
  const status = useBrainStore((s) => s.status)
  const agents = useBrainStore((s) => s.agents)

  const fsmState = status?.fsm_state || 'IDLE'
  const fsmHistory = status?.fsm_history || []
  const metrics = status?.metrics || {}

  return (
    <div className="p-6 space-y-6 animate-scale-in">
      {/* FSM Diagram */}
      <FsmStateDiagram currentState={fsmState} history={fsmHistory} />

      {/* Agent Grid */}
      <div>
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Agent Network</h3>
        <div className="grid grid-cols-3 gap-3">
          {agents.length === 0 ? (
            <div className="col-span-3 text-center text-xs text-text-muted py-8">No agents loaded</div>
          ) : (
            agents.map((agent) => <AgentCard key={agent.name} agent={agent} />)
          )}
        </div>
      </div>

      {/* Priority Queue Stats */}
      <div className="bg-surface-raised border border-border rounded-xl p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Task Processing</h3>
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: 'P0 Emergency', color: 'bg-error-red', desc: 'Unbounded' },
            { label: 'P1 Realtime', color: 'bg-warning-amber', desc: '8 concurrent' },
            { label: 'P2 Active', color: 'bg-phase-analyzing', desc: '4 concurrent' },
            { label: 'P3 Background', color: 'bg-phase-comparing', desc: '2 concurrent' },
            { label: 'P4 Idle', color: 'bg-text-muted', desc: '1 concurrent' },
          ].map(({ label, color, desc }) => (
            <div key={label} className="text-center">
              <div className={`w-3 h-3 rounded-full ${color} mx-auto mb-1`} />
              <div className="text-xs font-medium text-text-secondary">{label}</div>
              <div className="text-[10px] text-text-muted">{desc}</div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
          <span>Queue depth: <span className="text-text-primary font-mono">{metrics.agent_queue || 0}</span></span>
          <span>Wake words: <span className="text-text-primary font-mono">{metrics.wake_words || 0}</span></span>
          <span>STT errors: <span className="text-text-primary font-mono">{metrics.stt_errors || 0}</span></span>
        </div>
      </div>
    </div>
  )
}
