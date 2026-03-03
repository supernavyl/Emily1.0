import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  variant?: 'default' | 'accent' | 'dim'
  animate?: 'fade-up' | 'scale-in' | 'none'
  delay?: number
  className?: string
  onClick?: () => void
}

const variants = {
  default: {
    background: 'rgba(255,255,255,0.035)',
    border: '1px solid rgba(255,255,255,0.07)',
    boxShadow: '0 4px 24px rgba(0,0,0,0.2)',
  },
  accent: {
    background: 'rgba(124,106,247,0.08)',
    border: '1px solid rgba(124,106,247,0.25)',
    boxShadow: '0 4px 24px rgba(124,106,247,0.1)',
  },
  dim: {
    background: 'rgba(255,255,255,0.02)',
    border: '1px solid rgba(255,255,255,0.04)',
    boxShadow: 'none',
  },
}

const animations = {
  'fade-up': 'animate-fade-up',
  'scale-in': 'animate-scale-in',
  none: '',
}

export function GlassCard({
  children,
  variant = 'default',
  animate = 'fade-up',
  delay = 0,
  className = '',
  onClick,
}: Props) {
  return (
    <div
      className={`rounded-2xl px-4 py-3 backdrop-blur-xl ${animations[animate]} ${className}`}
      style={{
        ...variants[variant],
        animationDelay: delay ? `${delay}ms` : undefined,
      }}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
