import { FsmStateNode } from './FsmStateNode'

interface Props {
  currentState: string
  history: [string, string][]
}

const NODES: { id: string; x: number; y: number }[] = [
  { id: 'IDLE', x: 300, y: 45 },
  { id: 'LISTENING', x: 500, y: 100 },
  { id: 'BACKCHANNELING', x: 520, y: 220 },
  { id: 'PROCESSING', x: 300, y: 175 },
  { id: 'FILLING', x: 120, y: 175 },
  { id: 'SPEAKING', x: 100, y: 100 },
  { id: 'INTERRUPTED', x: 300, y: 300 },
  { id: 'ONBOARDING', x: 120, y: 300 },
]

const EDGES: [string, string][] = [
  ['IDLE', 'LISTENING'],
  ['IDLE', 'ONBOARDING'],
  ['LISTENING', 'PROCESSING'],
  ['LISTENING', 'BACKCHANNELING'],
  ['BACKCHANNELING', 'LISTENING'],
  ['PROCESSING', 'FILLING'],
  ['PROCESSING', 'SPEAKING'],
  ['FILLING', 'SPEAKING'],
  ['SPEAKING', 'IDLE'],
  ['SPEAKING', 'INTERRUPTED'],
  ['INTERRUPTED', 'LISTENING'],
  ['INTERRUPTED', 'IDLE'],
  ['ONBOARDING', 'IDLE'],
]

const nodeMap = Object.fromEntries(NODES.map(n => [n.id, n]))

export function FsmStateDiagram({ currentState, history }: Props) {
  const recentTransitions = new Set(
    history.slice(-5).map(([from, to]) => `${from}->${to}`)
  )

  return (
    <div className="bg-surface-raised border border-border rounded-xl p-4">
      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Conversation State Machine</h3>
      <svg viewBox="0 0 620 340" className="w-full" style={{ maxHeight: 280 }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-border)" />
          </marker>
          <marker id="arrow-active" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-accent)" />
          </marker>
        </defs>

        {/* Edges */}
        {EDGES.map(([from, to]) => {
          const a = nodeMap[from]
          const b = nodeMap[to]
          if (!a || !b) return null
          const key = `${from}->${to}`
          const isRecent = recentTransitions.has(key)
          const dx = b.x - a.x
          const dy = b.y - a.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          const nx = dx / dist
          const ny = dy / dist
          const offset = 36
          return (
            <line
              key={key}
              x1={a.x + nx * offset}
              y1={a.y + ny * offset}
              x2={b.x - nx * offset}
              y2={b.y - ny * offset}
              stroke={isRecent ? 'var(--color-accent)' : 'var(--color-border)'}
              strokeWidth={isRecent ? 2 : 1}
              opacity={isRecent ? 0.8 : 0.3}
              markerEnd={isRecent ? 'url(#arrow-active)' : 'url(#arrow)'}
            />
          )
        })}

        {/* Nodes */}
        {NODES.map(({ id, x, y }) => (
          <FsmStateNode key={id} label={id} x={x} y={y} active={currentState === id} />
        ))}
      </svg>

      {/* Recent transitions */}
      {history.length > 0 && (
        <div className="flex items-center gap-1 mt-2 overflow-x-auto text-xs font-mono">
          <span className="text-text-muted flex-shrink-0">History:</span>
          {history.slice(-8).map(([from, to], i) => (
            <span key={i} className="flex items-center gap-0.5 flex-shrink-0">
              <span className="text-text-secondary">{from}</span>
              <span className="text-text-muted">→</span>
              <span className="text-accent">{to}</span>
              {i < Math.min(history.length, 8) - 1 && <span className="text-border mx-0.5">·</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
