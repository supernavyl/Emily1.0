import { For } from 'solid-js'

interface Bar {
  label: string
  value: number
  max?: number
  color?: string
}

interface BarChartProps {
  bars: Bar[]
  height?: number
}

export function BarChart(props: BarChartProps) {
  const height = () => props.height ?? 12

  return (
    <div class="space-y-2">
      <For each={props.bars}>
        {(bar) => {
          const max = () => bar.max ?? 1
          const pct = () => max() > 0 ? Math.min(bar.value / max(), 1) * 100 : 0
          const color = () => bar.color ?? 'var(--color-accent)'
          return (
            <div class="flex items-center gap-2">
              <span class="text-xs w-20 truncate text-right" style={{ color: 'var(--color-text-secondary)' }}>
                {bar.label}
              </span>
              <div
                class="flex-1 rounded-full overflow-hidden"
                style={{ height: `${height()}px`, background: 'var(--color-surface)' }}
              >
                <div
                  class="h-full rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${pct()}%`, 'background-color': color() }}
                />
              </div>
              <span class="text-xs w-10 text-right font-mono" style={{ color: 'var(--color-text-muted)' }}>
                {bar.value.toFixed(2)}
              </span>
            </div>
          )
        }}
      </For>
    </div>
  )
}
