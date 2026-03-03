import type { Phase } from '../../../stores/onboarding'

interface Props {
  phase: Phase
  speaking: boolean
  typing: boolean
  className?: string
}

export function CosmicOrb({ phase, speaking, typing, className = '' }: Props) {
  // Phase 0: invisible
  if (phase === 0) return <div className={`h-24 ${className}`} />

  const isRadiant = phase === 7
  const isSubdued = phase === 5
  const isMaterializing = phase === 1

  // Core animation
  const coreAnimation = speaking
    ? 'cosmic-speak 1.2s ease-in-out infinite'
    : typing
      ? 'cosmic-breathe 0.8s ease-in-out infinite'
      : 'cosmic-breathe 3s ease-in-out infinite'

  // Glow intensity
  const glowMultiplier = isRadiant ? 2 : isSubdued ? 0.5 : 1
  const glowBase = 0.35 * glowMultiplier
  const glowSpread = 12 * glowMultiplier

  return (
    <div
      className={`relative mx-auto mb-6 flex h-24 w-24 flex-shrink-0 items-center justify-center ${
        isMaterializing ? 'animate-orb-materialize' : ''
      } ${className}`}
      style={{
        transition: 'opacity 0.8s ease, transform 0.8s ease',
        transform: isRadiant ? 'scale(1.15)' : 'scale(1)',
      }}
    >
      {/* Outer orbit ring */}
      <div
        className="absolute inset-0 rounded-full border border-accent/15"
        style={{
          animation: `ring-rotate ${isRadiant ? '8s' : '15s'} linear infinite`,
        }}
      >
        <div className="absolute -top-0.5 left-1/2 h-1.5 w-1.5 rounded-full bg-accent/40" />
      </div>

      {/* Inner orbit ring */}
      <div
        className="absolute inset-3 rounded-full border border-accent/20"
        style={{
          animation: `ring-rotate ${isRadiant ? '5s' : '10s'} linear infinite reverse`,
        }}
      >
        <div className="absolute -bottom-0.5 right-2 h-1 w-1 rounded-full bg-accent/50" />
      </div>

      {/* Third ring — only on confirm/done phases */}
      {(phase === 6 || phase === 7) && (
        <div
          className="absolute -inset-2 rounded-full border border-accent/10"
          style={{
            animation: 'ring-rotate 20s linear infinite',
            opacity: phase === 7 ? 0.4 : 0.2,
          }}
        >
          <div className="absolute -right-0.5 top-4 h-1 w-1 rounded-full bg-accent/30" />
        </div>
      )}

      {/* Core orb */}
      <div
        className={isRadiant ? 'animate-aurora' : ''}
        style={{
          width: 56,
          height: 56,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: `radial-gradient(circle at 35% 35%, rgba(124,106,247,${0.5 * glowMultiplier}) 0%, rgba(124,106,247,${0.2 * glowMultiplier}) 50%, rgba(124,106,247,0.05) 100%)`,
          border: `1px solid rgba(124,106,247,${glowBase})`,
          animation: coreAnimation,
        }}
      >
        <div
          style={{
            width: 24,
            height: 24,
            borderRadius: '50%',
            background: `radial-gradient(circle at 40% 40%, rgba(124,106,247,${0.9 * glowMultiplier}), rgba(124,106,247,${0.5 * glowMultiplier}))`,
            boxShadow: `0 0 ${glowSpread}px rgba(124,106,247,${0.5 * glowMultiplier})`,
            transition: 'box-shadow 0.5s ease',
          }}
        />
      </div>

      {/* Ripple effect on voice selection (phase 4 entry) */}
      {speaking && phase === 4 && (
        <div
          className="animate-ripple absolute inset-0 rounded-full border border-accent/30"
          style={{ pointerEvents: 'none' }}
        />
      )}
    </div>
  )
}
