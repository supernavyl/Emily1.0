import { For, Show, createMemo } from 'solid-js'
import { FsmStateNode } from './FsmStateNode'

interface FsmStateDiagramProps {
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

const nodeMap = Object.fromEntries(NODES.map((n) => [n.id, n]))

export function FsmStateDiagram(props: FsmStateDiagramProps) {
  const recentTransitions = createMemo(() =>
    new Set(
      props.history.slice(-5).map(([from, to]) => `${from}->${to}`),
    ),
  )

  return (
    <div class="rounded-xl p-4" style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}>
      <h3
        class="text-xs font-semibold uppercase mb-3"
        style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
      >
        Conversation State Machine
      </h3>
      <svg viewBox="0 0 620 340" class="w-full" style={{ 'max-height': '280px' }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-border)" />
          </marker>
          <marker id="arrow-active" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-accent)" />
          </marker>
        </defs>

        {/* Edges */}
        <For each={EDGES}>
          {([from, to]) => {
            const a = nodeMap[from]
            const b = nodeMap[to]
            if (!a || !b) return null
            const key = `${from}->${to}`
            const isRecent = () => recentTransitions().has(key)
            const dx = b.x - a.x
            const dy = b.y - a.y
            const dist = Math.sqrt(dx * dx + dy * dy)
            const nx = dx / dist
            const ny = dy / dist
            const offset = 36
            return (
              <line
                x1={a.x + nx * offset}
                y1={a.y + ny * offset}
                x2={b.x - nx * offset}
                y2={b.y - ny * offset}
                stroke={isRecent() ? 'var(--color-accent)' : 'var(--color-border)'}
                stroke-width={isRecent() ? 2 : 1}
                opacity={isRecent() ? 0.8 : 0.3}
                marker-end={isRecent() ? 'url(#arrow-active)' : 'url(#arrow)'}
              />
            )
          }}
        </For>

        {/* Nodes */}
        <For each={NODES}>
          {(node) => (
            <FsmStateNode
              label={node.id}
              x={node.x}
              y={node.y}
              active={props.currentState === node.id}
            />
          )}
        </For>
      </svg>

      {/* Recent transitions */}
      <Show when={props.history.length > 0}>
        <div class="flex items-center gap-1 mt-2 overflow-x-auto text-xs font-mono">
          <span style={{ color: 'var(--color-text-muted)' }} class="flex-shrink-0">History:</span>
          <For each={props.history.slice(-8)}>
            {([from, to], i) => (
              <span class="flex items-center gap-0.5 flex-shrink-0">
                <span style={{ color: 'var(--color-text-secondary)' }}>{from}</span>
                <span style={{ color: 'var(--color-text-muted)' }}>{'\u2192'}</span>
                <span style={{ color: 'var(--color-accent)' }}>{to}</span>
                {i() < Math.min(props.history.length, 8) - 1 && (
                  <span class="mx-0.5" style={{ color: 'var(--color-border)' }}>{'\u00B7'}</span>
                )}
              </span>
            )}
          </For>
        </div>
      </Show>
    </div>
  )
}
