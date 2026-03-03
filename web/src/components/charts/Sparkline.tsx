interface Props {
  data: number[]
  width?: number
  height?: number
  color?: string
  filled?: boolean
}

export function Sparkline({ data, width = 200, height = 40, color = 'var(--color-accent)', filled = true }: Props) {
  if (data.length < 2) {
    return (
      <svg width={width} height={height}>
        <text x={width / 2} y={height / 2} textAnchor="middle" dominantBaseline="middle" fill="var(--color-text-muted)" fontSize="10">
          Collecting data...
        </text>
      </svg>
    )
  }

  const max = Math.max(...data, 0.01)
  const min = Math.min(...data, 0)
  const range = max - min || 1
  const pad = 2

  const stepX = (width - pad * 2) / (data.length - 1)
  const points = data.map((v, i) => ({
    x: pad + i * stepX,
    y: pad + (height - pad * 2) * (1 - (v - min) / range),
  }))

  const linePoints = points.map(p => `${p.x},${p.y}`).join(' ')
  const fillPoints = `${pad},${height - pad} ${linePoints} ${width - pad},${height - pad}`

  return (
    <svg width={width} height={height} className="select-none">
      {filled && (
        <polygon
          points={fillPoints}
          fill={color}
          fillOpacity={0.1}
        />
      )}
      <polyline
        points={linePoints}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Current value dot */}
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r={2.5}
        fill={color}
      />
    </svg>
  )
}
