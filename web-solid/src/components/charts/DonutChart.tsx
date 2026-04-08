import { For, Show, createMemo } from 'solid-js'

interface Segment {
  label: string
  value: number
  color: string
}

interface DonutChartProps {
  segments: Segment[]
  size?: number
  strokeWidth?: number
  centerLabel?: string
}

export function DonutChart(props: DonutChartProps) {
  const size = () => props.size ?? 120
  const strokeWidth = () => props.strokeWidth ?? 14
  const radius = () => (size() - strokeWidth()) / 2
  const circumference = () => 2 * Math.PI * radius()
  const cx = () => size() / 2
  const cy = () => size() / 2
  const total = () => props.segments.reduce((s, seg) => s + seg.value, 0)

  const segmentsWithOffset = createMemo(() => {
    let cumulative = 0
    return props.segments.map((seg) => {
      const pct = total() > 0 ? seg.value / total() : 0
      const dashLength = circumference() * pct
      const offset = circumference() * cumulative
      cumulative += pct
      return { seg, dashLength, offset }
    })
  })

  const visibleSegments = createMemo(() =>
    props.segments.filter((s) => s.value > 0),
  )

  return (
    <Show when={total() > 0}>
      <div class="flex flex-col items-center gap-2">
        <div style={{ position: 'relative' }}>
          <svg width={size()} height={size()} class="transform -rotate-90">
            <circle
              cx={cx()} cy={cy()} r={radius()}
              fill="none" stroke="var(--color-border)" stroke-width={strokeWidth()}
            />
            <For each={segmentsWithOffset()}>
              {(item) => (
                <circle
                  cx={cx()} cy={cy()} r={radius()}
                  fill="none"
                  stroke={item.seg.color}
                  stroke-width={strokeWidth()}
                  stroke-dasharray={`${item.dashLength} ${circumference() - item.dashLength}`}
                  stroke-dashoffset={-item.offset}
                  class="transition-all duration-500"
                />
              )}
            </For>
          </svg>
          <Show when={props.centerLabel}>
            <div class="absolute inset-0 flex items-center justify-center">
              <span class="text-sm font-bold" style={{ color: 'var(--color-text-primary)' }}>
                {props.centerLabel}
              </span>
            </div>
          </Show>
        </div>
        <div class="flex flex-wrap gap-x-3 gap-y-1 justify-center">
          <For each={visibleSegments()}>
            {(seg) => (
              <div class="flex items-center gap-1 text-xs">
                <span
                  class="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ 'background-color': seg.color }}
                />
                <span style={{ color: 'var(--color-text-muted)' }}>{seg.label}</span>
              </div>
            )}
          </For>
        </div>
      </div>
    </Show>
  )
}
