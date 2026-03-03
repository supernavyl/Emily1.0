import { useMemo } from 'react'
import { useChatStore } from '../../stores/chat'

interface FlowNode {
  id: string
  label: string
  x: number
  y: number
  status: 'idle' | 'active' | 'complete'
  model?: string
  tokens?: number
  latency?: number
}

const STEP_COLORS: Record<string, string> = {
  idle: '#555570',
  active: 'var(--color-accent, #3b82f6)',
  complete: '#22c55e',
}

const NODE_RADIUS = 28

export function FlowDiagram() {
  const reasoningSteps = useChatStore((s) => s.reasoningSteps)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const streamMeta = useChatStore((s) => s.streamMeta)

  // Build nodes from the default flow + any reasoning steps
  const nodes = useMemo<FlowNode[]>(() => {
    const defaultFlow = [
      { id: 'query', label: 'Query' },
      { id: 'route', label: 'Route' },
      { id: 'retrieve', label: 'Retrieve' },
      { id: 'reason', label: 'Reason' },
      { id: 'critique', label: 'Critique' },
      { id: 'respond', label: 'Respond' },
    ]

    // If we have actual reasoning steps, map them
    const stepNames = new Set(reasoningSteps.map((s) => s.step_name))
    const completedSteps = new Set(
      reasoningSteps.filter((s) => s.event_type === 'step_complete').map((s) => s.step_name),
    )
    const activeSteps = new Set(
      reasoningSteps.filter((s) => s.event_type === 'step_start' && !completedSteps.has(s.step_name)).map((s) => s.step_name),
    )

    return defaultFlow.map((n, i) => {
      const x = 40 + i * 100
      const y = 80
      let status: FlowNode['status'] = 'idle'

      // Map default flow names to step activity
      if (completedSteps.has(n.id) || (n.id === 'query' && reasoningSteps.length > 0) || (n.id === 'respond' && !isStreaming && reasoningSteps.length > 0)) {
        status = 'complete'
      } else if (activeSteps.has(n.id) || (n.id === 'route' && isStreaming && reasoningSteps.length === 0)) {
        status = 'active'
      }

      // If streaming is active, mark respond as active at minimum
      if (isStreaming && n.id === 'respond' && reasoningSteps.length === 0) {
        status = 'active'
      }

      // During streaming, mark the first few nodes as complete
      if (isStreaming) {
        if (n.id === 'query') status = 'complete'
        if (n.id === 'route') status = 'complete'
      }

      const stepData = reasoningSteps.find((s) => s.step_name === n.id && s.event_type === 'step_complete')
      return {
        ...n,
        x,
        y,
        status,
        model: stepData?.model || (n.id === 'route' ? streamMeta?.provider : undefined),
        tokens: (stepData?.metadata?.tokens as number) || undefined,
      }
    })
  }, [reasoningSteps, isStreaming, streamMeta])

  const edges = useMemo(() => {
    const result: Array<{ from: FlowNode; to: FlowNode; active: boolean }> = []
    for (let i = 0; i < nodes.length - 1; i++) {
      const from = nodes[i]
      const to = nodes[i + 1]
      const active = from.status !== 'idle' && to.status !== 'idle'
      result.push({ from, to, active })
    }
    return result
  }, [nodes])

  return (
    <div className="flex-1 flex items-center justify-center p-4 overflow-auto">
      <svg viewBox="0 0 640 160" className="w-full max-h-[200px]" style={{ maxWidth: 640 }}>
        <defs>
          <marker id="flow-arrow" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#555570" />
          </marker>
          <marker id="flow-arrow-active" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-accent, #3b82f6)" />
          </marker>
        </defs>

        {/* Edges */}
        {edges.map(({ from, to, active }, i) => (
          <line
            key={i}
            x1={from.x + NODE_RADIUS + 4}
            y1={from.y}
            x2={to.x - NODE_RADIUS - 4}
            y2={to.y}
            stroke={active ? 'var(--color-accent, #3b82f6)' : '#555570'}
            strokeWidth={active ? 2 : 1}
            markerEnd={active ? 'url(#flow-arrow-active)' : 'url(#flow-arrow)'}
            opacity={active ? 1 : 0.4}
          />
        ))}

        {/* Nodes */}
        {nodes.map((node) => (
          <g key={node.id}>
            {/* Pulse ring for active */}
            {node.status === 'active' && (
              <circle cx={node.x} cy={node.y} r={NODE_RADIUS + 4} fill="none" stroke={STEP_COLORS.active} strokeWidth={1.5} opacity={0.5}>
                <animate attributeName="r" from={NODE_RADIUS + 2} to={NODE_RADIUS + 10} dur="1.2s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.6" to="0" dur="1.2s" repeatCount="indefinite" />
              </circle>
            )}

            <circle
              cx={node.x}
              cy={node.y}
              r={NODE_RADIUS}
              fill={node.status === 'idle' ? '#1a1a2e' : node.status === 'active' ? 'var(--color-accent, #3b82f6)' : '#22c55e'}
              stroke={STEP_COLORS[node.status]}
              strokeWidth={2}
              opacity={node.status === 'idle' ? 0.5 : 1}
            />

            <text x={node.x} y={node.y + 1} textAnchor="middle" dominantBaseline="middle" fontSize="9" fill="white" fontWeight={node.status !== 'idle' ? 600 : 400}>
              {node.label}
            </text>

            {/* Model label below */}
            {node.model && (
              <text x={node.x} y={node.y + NODE_RADIUS + 14} textAnchor="middle" fontSize="7" fill="#888">
                {node.model}
              </text>
            )}

            {/* Token count below model */}
            {node.tokens && (
              <text x={node.x} y={node.y + NODE_RADIUS + 24} textAnchor="middle" fontSize="7" fill="#666">
                {node.tokens} tok
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  )
}
