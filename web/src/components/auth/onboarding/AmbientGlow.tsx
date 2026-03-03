import type { Phase } from '../../../stores/onboarding'

interface Props {
  phase: Phase
}

const phaseConfig: Record<number, { opacity: number; scale: number; hue: string }> = {
  0: { opacity: 0, scale: 0.5, hue: '#7c6af7' },
  1: { opacity: 0.06, scale: 0.8, hue: '#7c6af7' },
  2: { opacity: 0.1, scale: 1, hue: '#7c6af7' },
  3: { opacity: 0.1, scale: 1, hue: '#6366f1' },
  4: { opacity: 0.12, scale: 1, hue: '#7c6af7' },
  5: { opacity: 0.05, scale: 0.9, hue: '#4f46e5' },
  6: { opacity: 0.1, scale: 1, hue: '#7c6af7' },
  7: { opacity: 0.18, scale: 1.2, hue: '#a855f7' },
}

export function AmbientGlow({ phase }: Props) {
  const cfg = phaseConfig[phase] ?? phaseConfig[2]

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {/* Primary glow — center */}
      <div
        className="animate-glow-pulse absolute rounded-full"
        style={{
          '--glow-base': cfg.opacity,
          width: 600 * cfg.scale,
          height: 600 * cfg.scale,
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -60%)',
          background: `radial-gradient(circle, ${cfg.hue} 0%, transparent 70%)`,
          filter: 'blur(100px)',
          opacity: cfg.opacity,
          transition: 'opacity 1.5s ease, width 1.5s ease, height 1.5s ease',
        } as React.CSSProperties}
      />

      {/* Secondary glow — bottom left */}
      <div
        className="absolute rounded-full"
        style={{
          width: 400,
          height: 400,
          bottom: '-10%',
          left: '-5%',
          background: 'radial-gradient(circle, #3b82f6 0%, transparent 70%)',
          filter: 'blur(90px)',
          opacity: cfg.opacity * 0.6,
          animation: 'nebula-drift 30s ease-in-out 5s infinite reverse',
          transition: 'opacity 1.5s ease',
        }}
      />

      {/* Tertiary glow — top right */}
      <div
        className="absolute rounded-full"
        style={{
          width: 350,
          height: 350,
          top: '-5%',
          right: '-5%',
          background: 'radial-gradient(circle, #a855f7 0%, transparent 65%)',
          filter: 'blur(80px)',
          opacity: cfg.opacity * 0.4,
          animation: 'nebula-drift 20s ease-in-out 10s infinite',
          transition: 'opacity 1.5s ease',
        }}
      />
    </div>
  )
}
