interface Axis {
  label: string
  value: number
}

interface Props {
  axes: Axis[]
  size?: number
  color?: string
  guides?: number
}

export function RadarChart({ axes, size = 200, color = 'var(--color-accent)', guides = 4 }: Props) {
  const cx = size / 2
  const cy = size / 2
  const padding = 30
  const r = (size / 2) - padding
  const n = axes.length
  if (n < 3) return null

  const angleStep = (2 * Math.PI) / n
  const startAngle = -Math.PI / 2

  const point = (i: number, scale: number) => {
    const angle = startAngle + i * angleStep
    return {
      x: cx + r * scale * Math.cos(angle),
      y: cy + r * scale * Math.sin(angle),
    }
  }

  const polygon = (scale: number) =>
    axes.map((_, i) => point(i, scale)).map(p => `${p.x},${p.y}`).join(' ')

  const dataPolygon = axes.map((a, i) => point(i, Math.min(a.value, 1))).map(p => `${p.x},${p.y}`).join(' ')

  return (
    <svg width={size} height={size} className="select-none">
      {/* Guide polygons */}
      {Array.from({ length: guides }, (_, g) => (
        <polygon
          key={g}
          points={polygon((g + 1) / guides)}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth="1"
          opacity={0.5}
        />
      ))}

      {/* Axis lines */}
      {axes.map((_, i) => {
        const p = point(i, 1)
        return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="var(--color-border)" strokeWidth="1" opacity={0.3} />
      })}

      {/* Data polygon */}
      <polygon
        points={dataPolygon}
        fill={color}
        fillOpacity={0.15}
        stroke={color}
        strokeWidth="2"
        className="transition-all duration-500 ease-out"
      />

      {/* Data dots */}
      {axes.map((a, i) => {
        const p = point(i, Math.min(a.value, 1))
        return <circle key={i} cx={p.x} cy={p.y} r={3} fill={color} />
      })}

      {/* Labels */}
      {axes.map((a, i) => {
        const p = point(i, 1.25)
        return (
          <text
            key={i}
            x={p.x}
            y={p.y}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="var(--color-text-muted)"
            fontSize="10"
            fontFamily="var(--font-sans)"
          >
            {a.label}
          </text>
        )
      })}
    </svg>
  )
}
