interface Props {
  active: boolean
  bars?: number
}

export function AudioLevelIndicator({ active, bars = 12 }: Props) {
  return (
    <div className="flex items-end justify-center gap-[3px] h-8">
      {Array.from({ length: bars }, (_, i) => (
        <div
          key={i}
          className="w-[3px] rounded-full transition-all"
          style={{
            backgroundColor: active ? 'var(--color-accent)' : 'var(--color-border)',
            height: active ? '100%' : '30%',
            transformOrigin: 'bottom',
            animation: active ? `wave-bar 0.6s ease-in-out ${i * 80}ms infinite` : 'none',
          }}
        />
      ))}
    </div>
  )
}
