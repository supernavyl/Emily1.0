import type { Phase } from '../../../stores/onboarding'

interface Props {
  currentPhase: Phase
  className?: string
}

// Asymmetric constellation pattern (like a real star pattern)
const STARS: { x: number; y: number; label: string }[] = [
  { x: 20, y: 45, label: 'Awakening' },
  { x: 50, y: 20, label: 'Name' },
  { x: 85, y: 38, label: 'Identity' },
  { x: 115, y: 12, label: 'Voice' },
  { x: 148, y: 40, label: 'Trust' },
  { x: 170, y: 18, label: 'Bond' },
  { x: 195, y: 42, label: 'Alive' },
]

// Lines connect adjacent stars
const LINES: [number, number][] = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 4],
  [4, 5],
  [5, 6],
]

export function ProgressConstellation({ currentPhase, className = '' }: Props) {
  // Phase 0 has no star; phases 1-7 map to stars 0-6
  const activeStarIndex = currentPhase - 1

  return (
    <div className={`pointer-events-none absolute right-6 top-8 ${className}`}>
      <svg
        width="220"
        height="60"
        viewBox="0 0 220 60"
        fill="none"
        role="progressbar"
        aria-valuenow={currentPhase}
        aria-valuemin={0}
        aria-valuemax={7}
        aria-label="Onboarding progress"
      >
        {/* Constellation lines */}
        {LINES.map(([from, to], i) => {
          const a = STARS[from]
          const b = STARS[to]
          const completed = to <= activeStarIndex
          const dx = b.x - a.x
          const dy = b.y - a.y
          const length = Math.sqrt(dx * dx + dy * dy)

          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="rgba(124,106,247,0.3)"
              strokeWidth={completed ? 1 : 0.5}
              strokeDasharray={length}
              strokeDashoffset={completed ? 0 : length}
              style={{
                opacity: completed ? 0.5 : 0.12,
                transition: 'stroke-dashoffset 0.8s ease, opacity 0.8s ease',
              }}
            />
          )
        })}

        {/* Stars */}
        {STARS.map((star, i) => {
          const isCompleted = i < activeStarIndex
          const isActive = i === activeStarIndex

          return (
            <g key={i}>
              {/* Glow ring for active star */}
              {isActive && (
                <circle
                  cx={star.x}
                  cy={star.y}
                  r={8}
                  fill="none"
                  stroke="rgba(124,106,247,0.4)"
                  strokeWidth={1}
                  style={{ animation: 'pulse-ring 2s ease-in-out infinite' }}
                />
              )}

              {/* Star */}
              <circle
                cx={star.x}
                cy={star.y}
                r={isActive ? 3.5 : isCompleted ? 3 : 2}
                fill={
                  isCompleted || isActive
                    ? 'rgba(124,106,247,0.9)'
                    : 'rgba(124,106,247,0.15)'
                }
                className={isActive ? 'animate-star-ignite' : ''}
                style={{
                  filter:
                    isCompleted || isActive
                      ? 'drop-shadow(0 0 6px rgba(124,106,247,0.5))'
                      : 'none',
                  transition: 'fill 0.5s ease, r 0.5s ease',
                }}
              />

              {/* Label — only show for active */}
              {isActive && (
                <text
                  x={star.x}
                  y={star.y + 16}
                  textAnchor="middle"
                  fill="rgba(124,106,247,0.6)"
                  fontSize="7"
                  fontFamily="Inter, sans-serif"
                  className="animate-fade-up"
                >
                  {star.label}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
