interface Props {
  value: number
  max: number
  size?: number
  strokeWidth?: number
  label: string
  color?: string
  format?: (v: number) => string
}

export function ProgressRing({ value, max, size = 100, strokeWidth = 6, label, color = 'var(--color-accent)', format }: Props) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const pct = max > 0 ? Math.min(value / max, 1) : 0
  const offset = circumference * (1 - pct)
  const cx = size / 2
  const cy = size / 2

  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width={size} height={size} className="transform -rotate-90">
        <circle
          cx={cx} cy={cy} r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={cx} cy={cy} r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <span className="text-lg font-bold text-text-primary" style={{ color }}>
          {format ? format(value) : `${Math.round(pct * 100)}%`}
        </span>
      </div>
      <span className="text-xs text-text-muted font-medium">{label}</span>
    </div>
  )
}
