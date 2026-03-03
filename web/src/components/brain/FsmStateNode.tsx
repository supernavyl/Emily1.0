interface Props {
  label: string
  x: number
  y: number
  active: boolean
  size?: number
}

const STATE_COLORS: Record<string, string> = {
  IDLE: '#555570',
  LISTENING: '#3b82f6',
  BACKCHANNELING: '#a855f7',
  PROCESSING: '#f59e0b',
  FILLING: '#eab308',
  SPEAKING: '#22c55e',
  INTERRUPTED: '#ef4444',
  ONBOARDING: '#8b9cf7',
}

export function FsmStateNode({ label, x, y, active, size = 32 }: Props) {
  const color = STATE_COLORS[label] || '#555570'

  return (
    <g className={active ? 'animate-glow-node' : ''}>
      {/* Outer pulse ring when active */}
      {active && (
        <circle cx={x} cy={y} r={size + 8} fill="none" stroke={color} strokeWidth="1" opacity={0.3}>
          <animate attributeName="r" values={`${size + 4};${size + 14};${size + 4}`} dur="2s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.4;0;0.4" dur="2s" repeatCount="indefinite" />
        </circle>
      )}

      {/* Main circle */}
      <circle
        cx={x} cy={y} r={size}
        fill={active ? color : 'var(--color-surface-raised)'}
        fillOpacity={active ? 0.2 : 1}
        stroke={color}
        strokeWidth={active ? 2.5 : 1.5}
      />

      {/* Label */}
      <text
        x={x} y={y}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={active ? color : 'var(--color-text-secondary)'}
        fontSize="8"
        fontWeight={active ? '700' : '500'}
        fontFamily="var(--font-mono)"
      >
        {label}
      </text>
    </g>
  )
}
