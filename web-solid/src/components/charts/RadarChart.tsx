import { For, Show } from 'solid-js'

interface Axis {
  label: string
  value: number
}

interface RadarChartProps {
  axes: Axis[]
  size?: number
  color?: string
  guides?: number
}

export function RadarChart(props: RadarChartProps) {
  const size = () => props.size ?? 200
  const color = () => props.color ?? 'var(--color-accent)'
  const guides = () => props.guides ?? 4
  const cx = () => size() / 2
  const cy = () => size() / 2
  const padding = 30
  const r = () => size() / 2 - padding
  const n = () => props.axes.length
  const angleStep = () => (2 * Math.PI) / n()
  const startAngle = -Math.PI / 2

  const point = (i: number, scale: number) => {
    const angle = startAngle + i * angleStep()
    return {
      x: cx() + r() * scale * Math.cos(angle),
      y: cy() + r() * scale * Math.sin(angle),
    }
  }

  const polygon = (scale: number) =>
    props.axes.map((_, i) => point(i, scale)).map((p) => `${p.x},${p.y}`).join(' ')

  const dataPolygon = () =>
    props.axes.map((a, i) => point(i, Math.min(a.value, 1))).map((p) => `${p.x},${p.y}`).join(' ')

  return (
    <Show when={n() >= 3}>
      <svg width={size()} height={size()} class="select-none">
        {/* Guide polygons */}
        <For each={Array.from({ length: guides() }, (_, g) => g)}>
          {(g) => (
            <polygon
              points={polygon((g + 1) / guides())}
              fill="none"
              stroke="var(--color-border)"
              stroke-width="1"
              opacity={0.5}
            />
          )}
        </For>

        {/* Axis lines */}
        <For each={props.axes}>
          {(_, i) => {
            const p = () => point(i(), 1)
            return (
              <line
                x1={cx()} y1={cy()} x2={p().x} y2={p().y}
                stroke="var(--color-border)" stroke-width="1" opacity={0.3}
              />
            )
          }}
        </For>

        {/* Data polygon */}
        <polygon
          points={dataPolygon()}
          fill={color()}
          fill-opacity={0.15}
          stroke={color()}
          stroke-width="2"
          class="transition-all duration-500 ease-out"
        />

        {/* Data dots */}
        <For each={props.axes}>
          {(a, i) => {
            const p = () => point(i(), Math.min(a.value, 1))
            return <circle cx={p().x} cy={p().y} r={3} fill={color()} />
          }}
        </For>

        {/* Labels */}
        <For each={props.axes}>
          {(a, i) => {
            const p = () => point(i(), 1.25)
            return (
              <text
                x={p().x} y={p().y}
                text-anchor="middle"
                dominant-baseline="middle"
                fill="var(--color-text-muted)"
                font-size="10"
                font-family="var(--font-sans)"
              >
                {a.label}
              </text>
            )
          }}
        </For>
      </svg>
    </Show>
  )
}
