interface Segment {
  label: string
  value: number
  color: string
}

interface Props {
  segments: Segment[]
  size?: number
  strokeWidth?: number
  centerLabel?: string
}

export function DonutChart({ segments, size = 120, strokeWidth = 14, centerLabel }: Props) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const cx = size / 2
  const cy = size / 2
  const total = segments.reduce((s, seg) => s + seg.value, 0)
  if (total === 0) return null

  let cumulative = 0

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative">
        <svg width={size} height={size} className="transform -rotate-90">
          <circle cx={cx} cy={cy} r={radius} fill="none" stroke="var(--color-border)" strokeWidth={strokeWidth} />
          {segments.map((seg, i) => {
            const pct = seg.value / total
            const dashLength = circumference * pct
            const offset = circumference * cumulative
            cumulative += pct
            return (
              <circle
                key={i}
                cx={cx} cy={cy} r={radius}
                fill="none"
                stroke={seg.color}
                strokeWidth={strokeWidth}
                strokeDasharray={`${dashLength} ${circumference - dashLength}`}
                strokeDashoffset={-offset}
                className="transition-all duration-500"
              />
            )
          })}
        </svg>
        {centerLabel && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-sm font-bold text-text-primary">{centerLabel}</span>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center">
        {segments.filter(s => s.value > 0).map((seg, i) => (
          <div key={i} className="flex items-center gap-1 text-xs">
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: seg.color }} />
            <span className="text-text-muted">{seg.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
