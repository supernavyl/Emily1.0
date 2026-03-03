import { useEffect, useState, type ReactNode } from 'react'
import { useOnboardingStore } from '../../../stores/onboarding'

interface Props {
  children: ReactNode
}

export function PhaseTransition({ children }: Props) {
  const transitioning = useOnboardingStore((s) => s.transitioning)
  const completeTransition = useOnboardingStore((s) => s.completeTransition)
  const [stage, setStage] = useState<'visible' | 'exiting' | 'entering'>('visible')

  useEffect(() => {
    if (!transitioning) return

    // Exit old content
    setStage('exiting')

    const enterTimer = setTimeout(() => {
      setStage('entering')
    }, 320)

    const visibleTimer = setTimeout(() => {
      setStage('visible')
      completeTransition()
    }, 680)

    return () => {
      clearTimeout(enterTimer)
      clearTimeout(visibleTimer)
    }
  }, [transitioning, completeTransition])

  const className =
    stage === 'exiting'
      ? 'animate-phase-out'
      : stage === 'entering'
        ? 'animate-phase-in'
        : ''

  return (
    <div
      className={className}
      style={{ willChange: stage !== 'visible' ? 'opacity, transform' : undefined }}
    >
      {children}
    </div>
  )
}
