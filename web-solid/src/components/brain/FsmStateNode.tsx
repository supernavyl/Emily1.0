import { Show } from 'solid-js'

interface FsmStateNodeProps {
  label: string
  x: number
  y: number
  active: boolean
  size?: number
}

const STATE_COLORS: Record<string, string> = {
  IDLE:           'var(--color-text-muted)',
  LISTENING:      'var(--color-phase-comparing)',
  BACKCHANNELING: 'var(--color-phase-analyzing)',
  PROCESSING:     'var(--color-warning-amber)',
  FILLING:        'var(--color-phase-considering)',
  SPEAKING:       'var(--color-cost-green)',
  INTERRUPTED:    'var(--color-error-red)',
  ONBOARDING:     'var(--color-accent)',
}

export function FsmStateNode(props: FsmStateNodeProps) {
  const size = () => props.size ?? 32
  const color = () => STATE_COLORS[props.label] || 'var(--color-text-muted)'

  return (
    <g class={props.active ? 'animate-glow-node' : ''}>
      <Show when={props.active}>
        <circle
          cx={props.x} cy={props.y} r={size() + 8}
          fill="none" stroke={color()} stroke-width="1" opacity={0.3}
        >
          <animate attributeName="r" values={`${size() + 4};${size() + 14};${size() + 4}`} dur="2s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.4;0;0.4" dur="2s" repeatCount="indefinite" />
        </circle>
      </Show>

      <circle
        cx={props.x} cy={props.y} r={size()}
        fill={props.active ? color() : 'var(--color-surface-raised)'}
        fill-opacity={props.active ? 0.2 : 1}
        stroke={color()}
        stroke-width={props.active ? 2.5 : 1.5}
      />

      <text
        x={props.x} y={props.y}
        text-anchor="middle" dominant-baseline="middle"
        fill={props.active ? color() : 'var(--color-text-secondary)'}
        font-size="8" font-weight={props.active ? '700' : '500'}
        font-family="var(--font-mono)"
      >
        {props.label}
      </text>
    </g>
  )
}
