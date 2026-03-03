import { useBrainStore } from '../../stores/brain'
import { ProgressRing } from '../charts/ProgressRing'
import { RadarChart } from '../charts/RadarChart'
import { Sparkline } from '../charts/Sparkline'
import { Activity, Users, Database, Clock, Zap, MessageSquare } from 'lucide-react'

export function NeuralOverview() {
  const status = useBrainStore((s) => s.status)
  const agents = useBrainStore((s) => s.agents)
  const workingMemory = useBrainStore((s) => s.workingMemory)
  const emotionHistory = useBrainStore((s) => s.emotionHistory)

  const res = status?.resources
  const emotions = status?.emotional_state || {}
  const metrics = status?.metrics || {}
  const fsmState = status?.fsm_state || 'IDLE'

  const formatUptime = (s?: number) => {
    if (!s) return '0m'
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }

  const radarAxes = [
    { label: 'Engage', value: emotions.engagement || 0 },
    { label: 'Confid', value: emotions.confidence || 0 },
    { label: 'Concern', value: emotions.concern || 0 },
    { label: 'Enthus', value: emotions.enthusiasm || 0 },
  ]

  const engagementHistory = emotionHistory.map(e => e.engagement || 0)

  return (
    <div className="p-6 space-y-6 animate-scale-in">
      {/* FSM State Hero */}
      <div className="flex items-center gap-8">
        <div className="flex flex-col items-center">
          <div className={`w-28 h-28 rounded-full border-2 flex items-center justify-center animate-pulse-ring ${
            fsmState === 'IDLE' ? 'border-text-muted' :
            fsmState === 'SPEAKING' ? 'border-cost-green' :
            fsmState === 'PROCESSING' ? 'border-warning-amber' :
            fsmState === 'LISTENING' ? 'border-phase-analyzing' :
            'border-accent'
          }`}>
            <div className="text-center">
              <div className="text-2xl font-bold text-text-primary font-mono">{fsmState}</div>
              <div className="text-[10px] text-text-muted mt-0.5">FSM State</div>
            </div>
          </div>
        </div>

        {/* Resource Rings */}
        <div className="flex gap-6">
          <div className="relative">
            <ProgressRing
              value={res?.cpu_percent || 0}
              max={100}
              size={90}
              label="CPU"
              color={res?.cpu_percent && res.cpu_percent > 80 ? 'var(--color-error-red)' : 'var(--color-phase-analyzing)'}
            />
          </div>
          <div className="relative">
            <ProgressRing
              value={res?.ram_used_gb || 0}
              max={res?.ram_total_gb || 64}
              size={90}
              label="RAM"
              color="var(--color-phase-comparing)"
              format={(v) => `${v.toFixed(1)}G`}
            />
          </div>
          <div className="relative">
            <ProgressRing
              value={(res?.vram_used_mb || 0) / 1024}
              max={(res?.vram_total_mb || 24576) / 1024}
              size={90}
              label="VRAM"
              color="var(--color-cost-green)"
              format={(v) => `${v.toFixed(1)}G`}
            />
          </div>
        </div>

        {/* Emotional Radar */}
        <div className="flex flex-col items-center">
          <RadarChart axes={radarAxes} size={160} />
          <span className="text-xs text-text-muted -mt-2">Emotional State</span>
        </div>

        {/* Engagement Sparkline */}
        <div className="flex flex-col items-center gap-1">
          <span className="text-xs text-text-muted">Engagement Trend</span>
          <Sparkline data={engagementHistory} width={160} height={50} color="var(--color-accent)" />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-6 gap-3">
        {[
          { icon: Users, label: 'Active Agents', value: agents.filter(a => a.status === 'active' || a.status === 'running').length, color: 'text-accent' },
          { icon: Database, label: 'Working Memory', value: `${(workingMemory?.token_count || 0).toLocaleString()} tok`, color: 'text-phase-comparing' },
          { icon: Clock, label: 'Uptime', value: formatUptime(status?.uptime_s), color: 'text-cost-green' },
          { icon: MessageSquare, label: 'Conversations', value: metrics.conversations || 0, color: 'text-phase-analyzing' },
          { icon: Zap, label: 'LLM Requests', value: metrics.llm_requests || 0, color: 'text-warning-amber' },
          { icon: Activity, label: 'Tool Calls', value: metrics.tool_calls || 0, color: 'text-phase-concluding' },
        ].map(({ icon: Icon, label, value, color }) => (
          <div key={label} className="bg-surface-raised border border-border rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Icon className={`w-3.5 h-3.5 ${color}`} />
              <span className="text-[10px] text-text-muted uppercase tracking-wider">{label}</span>
            </div>
            <div className="text-lg font-bold text-text-primary">{value}</div>
          </div>
        ))}
      </div>

      {/* Emotion Dimensions Detail */}
      <div className="bg-surface-raised border border-border rounded-xl p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Emotional Dimensions</h3>
        <div className="grid grid-cols-4 gap-4">
          {Object.entries(emotions).map(([key, val]) => (
            <div key={key} className="flex flex-col gap-1">
              <div className="flex justify-between items-center">
                <span className="text-xs text-text-secondary capitalize">{key}</span>
                <span className="text-xs font-mono text-text-muted">{val.toFixed(2)}</span>
              </div>
              <div className="h-2 bg-surface rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700 ease-out"
                  style={{
                    width: `${Math.min(val * 100, 100)}%`,
                    backgroundColor: 'var(--color-accent)',
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
