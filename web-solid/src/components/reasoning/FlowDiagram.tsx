import { createMemo, For } from 'solid-js'
import { chatState } from '../../stores/chat'

interface FlowNode {
  id: string
  label: string
  x: number
  y: number
  status: 'idle' | 'active' | 'complete'
  model?: string
  tokens?: number
}

const STEP_COLORS: Record<string, string> = {
  idle: 'var(--color-text-muted)',
  active: 'var(--color-accent)',
  complete: 'var(--color-cost-green)',
}

const NODE_RADIUS = 28

const DEFAULT_FLOW = [
  { id: 'query', label: 'Query' },
  { id: 'route', label: 'Route' },
  { id: 'retrieve', label: 'Retrieve' },
  { id: 'reason', label: 'Reason' },
  { id: 'critique', label: 'Critique' },
  { id: 'respond', label: 'Respond' },
]

export function FlowDiagram() {
  const nodes = createMemo<FlowNode[]>(() => {
    const steps = chatState.reasoningSteps
    const streaming = chatState.isStreaming
    const meta = chatState.streamMeta

    const completedSteps = new Set(
      steps.filter((s) => s.event_type === 'step_complete').map((s) => s.step_name),
    )
    const activeSteps = new Set(
      steps
        .filter((s) => s.event_type === 'step_start' && !completedSteps.has(s.step_name))
        .map((s) => s.step_name),
    )

    return DEFAULT_FLOW.map((n, i) => {
      const x = 40 + i * 100
      const y = 80
      let status: FlowNode['status'] = 'idle'

      if (
        completedSteps.has(n.id) ||
        (n.id === 'query' && steps.length > 0) ||
        (n.id === 'respond' && !streaming && steps.length > 0)
      ) {
        status = 'complete'
      } else if (
        activeSteps.has(n.id) ||
        (n.id === 'route' && streaming && steps.length === 0)
      ) {
        status = 'active'
      }

      if (streaming && n.id === 'respond' && steps.length === 0) {
        status = 'active'
      }

      if (streaming) {
        if (n.id === 'query') status = 'complete'
        if (n.id === 'route') status = 'complete'
      }

      const stepData = steps.find(
        (s) => s.step_name === n.id && s.event_type === 'step_complete',
      )
      return {
        ...n,
        x,
        y,
        status,
        model: stepData?.model || (n.id === 'route' ? meta?.provider : undefined),
        tokens: (stepData?.metadata?.tokens as number) || undefined,
      }
    })
  })

  const edges = createMemo(() => {
    const n = nodes()
    const result: Array<{ from: FlowNode; to: FlowNode; active: boolean }> = []
    for (let i = 0; i < n.length - 1; i++) {
      const from = n[i]
      const to = n[i + 1]
      const active = from.status !== 'idle' && to.status !== 'idle'
      result.push({ from, to, active })
    }
    return result
  })

  return (
    <div class="flex-1 flex items-center justify-center p-4 overflow-auto">
      <svg viewBox="0 0 640 160" class="w-full" style={{ 'max-height': '200px', 'max-width': '640px' }}>
        <defs>
          <marker id="flow-arrow" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-text-muted)" />
          </marker>
          <marker id="flow-arrow-active" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-accent)" />
          </marker>
        </defs>

        {/* Edges */}
        <For each={edges()}>
          {(edge) => (
            <line
              x1={edge.from.x + NODE_RADIUS + 4}
              y1={edge.from.y}
              x2={edge.to.x - NODE_RADIUS - 4}
              y2={edge.to.y}
              stroke={edge.active ? 'var(--color-accent)' : 'var(--color-text-muted)'}
              stroke-width={edge.active ? 2 : 1}
              marker-end={edge.active ? 'url(#flow-arrow-active)' : 'url(#flow-arrow)'}
              opacity={edge.active ? 1 : 0.4}
            />
          )}
        </For>

        {/* Nodes */}
        <For each={nodes()}>
          {(node) => (
            <g>
              {/* Pulse ring for active */}
              {node.status === 'active' && (
                <circle
                  cx={node.x} cy={node.y} r={NODE_RADIUS + 4}
                  fill="none" stroke={STEP_COLORS.active} stroke-width={1.5} opacity={0.5}
                >
                  <animate attributeName="r" from={NODE_RADIUS + 2} to={NODE_RADIUS + 10} dur="1.2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.6" to="0" dur="1.2s" repeatCount="indefinite" />
                </circle>
              )}

              <circle
                cx={node.x} cy={node.y} r={NODE_RADIUS}
                fill={
                  node.status === 'idle'
                    ? 'var(--color-thinking-bg)'
                    : node.status === 'active'
                      ? 'var(--color-accent)'
                      : 'var(--color-cost-green)'
                }
                stroke={STEP_COLORS[node.status]}
                stroke-width={2}
                opacity={node.status === 'idle' ? 0.5 : 1}
              />

              <text
                x={node.x} y={node.y + 1}
                text-anchor="middle" dominant-baseline="middle"
                font-size="9" fill="white"
                font-weight={node.status !== 'idle' ? 600 : 400}
              >
                {node.label}
              </text>

              {node.model && (
                <text
                  x={node.x} y={node.y + NODE_RADIUS + 14}
                  text-anchor="middle" font-size="7" fill="var(--color-text-muted)"
                >
                  {node.model}
                </text>
              )}

              {node.tokens && (
                <text
                  x={node.x} y={node.y + NODE_RADIUS + 24}
                  text-anchor="middle" font-size="7" fill="var(--color-text-muted)"
                >
                  {node.tokens} tok
                </text>
              )}
            </g>
          )}
        </For>
      </svg>
    </div>
  )
}
