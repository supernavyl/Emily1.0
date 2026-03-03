interface Bar {
  label: string
  value: number
  max?: number
  color?: string
}

interface Props {
  bars: Bar[]
  height?: number
}

export function BarChart({ bars, height = 12 }: Props) {
  return (
    <div className="space-y-2">
      {bars.map((bar) => {
        const max = bar.max ?? 1
        const pct = max > 0 ? Math.min(bar.value / max, 1) * 100 : 0
        const color = bar.color || 'var(--color-accent)'
        return (
          <div key={bar.label} className="flex items-center gap-2">
            <span className="text-xs text-text-secondary w-20 truncate text-right">{bar.label}</span>
            <div className="flex-1 bg-surface rounded-full overflow-hidden" style={{ height }}>
              <div
                className="h-full rounded-full transition-all duration-500 ease-out"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
            <span className="text-xs text-text-muted w-10 text-right font-mono">{bar.value.toFixed(2)}</span>
          </div>
        )
      })}
    </div>
  )
}
