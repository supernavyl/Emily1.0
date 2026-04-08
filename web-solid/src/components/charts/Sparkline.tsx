import { Show } from 'solid-js'

interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
  filled?: boolean
}

export function Sparkline(props: SparklineProps) {
  const width = () => props.width ?? 200
  const height = () => props.height ?? 40
  const color = () => props.color ?? 'var(--color-accent)'
  const filled = () => props.filled ?? true
  const pad = 2

  const computed = () => {
    const d = props.data
    if (d.length < 2) return null
    const max = Math.max(...d, 0.01)
    const min = Math.min(...d, 0)
    const range = max - min || 1
    const stepX = (width() - pad * 2) / (d.length - 1)
    const points = d.map((v, i) => ({
      x: pad + i * stepX,
      y: pad + (height() - pad * 2) * (1 - (v - min) / range),
    }))
    const linePoints = points.map((p) => `${p.x},${p.y}`).join(' ')
    const fillPoints = `${pad},${height() - pad} ${linePoints} ${width() - pad},${height() - pad}`
    const lastPoint = points[points.length - 1]
    return { linePoints, fillPoints, lastPoint }
  }

  return (
    <svg width={width()} height={height()} class="select-none">
      <Show when={computed()} fallback={
        <text
          x={width() / 2} y={height() / 2}
          text-anchor="middle" dominant-baseline="middle"
          fill="var(--color-text-muted)" font-size="10"
        >
          Collecting data...
        </text>
      }>
        {(c) => (
          <>
            <Show when={filled()}>
              <polygon points={c().fillPoints} fill={color()} fill-opacity={0.1} />
            </Show>
            <polyline
              points={c().linePoints}
              fill="none"
              stroke={color()}
              stroke-width="1.5"
              stroke-linejoin="round"
              stroke-linecap="round"
            />
            <circle
              cx={c().lastPoint.x}
              cy={c().lastPoint.y}
              r={2.5}
              fill={color()}
            />
          </>
        )}
      </Show>
    </svg>
  )
}
