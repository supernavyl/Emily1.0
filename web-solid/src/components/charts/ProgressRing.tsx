interface ProgressRingProps {
  value: number
  max: number
  size?: number
  strokeWidth?: number
  label?: string
  color?: string
  format?: (v: number, m: number) => string
}

export function ProgressRing(props: ProgressRingProps) {
  const size = () => props.size ?? 100
  const strokeWidth = () => props.strokeWidth ?? 6
  const color = () => props.color ?? 'var(--color-accent)'
  const radius = () => (size() - strokeWidth()) / 2
  const circumference = () => 2 * Math.PI * radius()
  const pct = () => props.max > 0 ? Math.min(props.value / props.max, 1) : 0
  const offset = () => circumference() * (1 - pct())
  const cx = () => size() / 2
  const cy = () => size() / 2

  const displayValue = () => {
    if (props.format) return props.format(props.value, props.max)
    return `${Math.round(pct() * 100)}%`
  }

  return (
    <div class="flex flex-col items-center gap-1.5" style={{ position: 'relative' }}>
      <svg
        width={size()}
        height={size()}
        class="transform -rotate-90"
      >
        <circle
          cx={cx()}
          cy={cy()}
          r={radius()}
          fill="none"
          stroke="var(--color-border)"
          stroke-width={strokeWidth()}
        />
        <circle
          cx={cx()}
          cy={cy()}
          r={radius()}
          fill="none"
          stroke={color()}
          stroke-width={strokeWidth()}
          stroke-dasharray={circumference()}
          stroke-dashoffset={offset()}
          stroke-linecap="round"
          style={{ transition: 'stroke-dashoffset 700ms ease-out' }}
        />
      </svg>
      <div
        class="absolute flex flex-col items-center justify-center"
        style={{ width: `${size()}px`, height: `${size()}px` }}
      >
        <span
          class="text-lg font-bold"
          style={{ color: color() }}
        >
          {displayValue()}
        </span>
      </div>
      {props.label && (
        <span class="text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>
          {props.label}
        </span>
      )}
    </div>
  )
}
