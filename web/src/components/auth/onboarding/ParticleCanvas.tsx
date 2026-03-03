import { useEffect, useRef, useCallback } from 'react'
import type { Phase } from '../../../stores/onboarding'

interface Props {
  phase: Phase
  mousePos: { x: number; y: number } | null
}

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  opacity: number
  baseOpacity: number
  hue: number
  active: boolean
}

const MAX_PARTICLES = 200
const TRAIL_ALPHA = 0.12
const MOUSE_RADIUS = 80
const MOUSE_FORCE = 0.4
const DAMPING = 0.985

function createParticle(cx: number, cy: number, scatter: number): Particle {
  const angle = Math.random() * Math.PI * 2
  const dist = Math.random() * scatter
  const baseOpacity = Math.random() * 0.6 + 0.15
  return {
    x: cx + Math.cos(angle) * dist,
    y: cy + Math.sin(angle) * dist,
    vx: (Math.random() - 0.5) * 0.3,
    vy: (Math.random() - 0.5) * 0.3,
    size: Math.random() * 1.5 + 0.5,
    opacity: baseOpacity,
    baseOpacity,
    hue: 240 + Math.random() * 40, // purple range
    active: false,
  }
}

export function ParticleCanvas({ phase, mousePos }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const frameRef = useRef(0)
  const phaseRef = useRef(phase)
  const mousePosRef = useRef(mousePos)
  const prevPhaseRef = useRef(phase)
  const phaseStartRef = useRef(performance.now())

  phaseRef.current = phase
  mousePosRef.current = mousePos

  // Track phase changes for burst effects
  useEffect(() => {
    if (phase !== prevPhaseRef.current) {
      prevPhaseRef.current = phase
      phaseStartRef.current = performance.now()
    }
  }, [phase])

  const initParticles = useCallback((w: number, h: number) => {
    const cx = w / 2
    const cy = h / 2
    const particles: Particle[] = []
    for (let i = 0; i < MAX_PARTICLES; i++) {
      particles.push(createParticle(cx, cy, Math.min(w, h) * 0.4))
    }
    particlesRef.current = particles
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d', { willReadFrequently: false })
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    const resize = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      if (particlesRef.current.length === 0) {
        initParticles(w, h)
      }
    }

    resize()
    window.addEventListener('resize', resize)

    const loop = () => {
      const w = canvas.width / dpr
      const h = canvas.height / dpr
      const cx = w / 2
      const cy = h / 2
      const p = phaseRef.current
      const mouse = mousePosRef.current
      const elapsed = (performance.now() - phaseStartRef.current) / 1000
      const particles = particlesRef.current

      // Trail effect instead of clearRect
      ctx.fillStyle = `rgba(5, 5, 16, ${TRAIL_ALPHA})`
      ctx.fillRect(0, 0, w, h)

      // Determine how many particles should be active
      let activeCount: number
      if (p === 0) {
        // Void: start with 1, grow to 40 over 3s
        activeCount = Math.min(Math.floor(1 + elapsed * 13), 40)
      } else if (p === 1) {
        // Awakening: ramp up to full
        activeCount = Math.min(Math.floor(40 + elapsed * 80), MAX_PARTICLES)
      } else if (p === 7) {
        activeCount = MAX_PARTICLES
      } else {
        activeCount = MAX_PARTICLES
      }

      for (let i = 0; i < particles.length; i++) {
        const pt = particles[i]
        pt.active = i < activeCount

        if (!pt.active) {
          pt.opacity *= 0.95
          if (pt.opacity < 0.01) continue
        } else {
          // Phase-specific forces
          if (p === 0) {
            // Void: spawn from center, radiate slowly
            if (pt.opacity < pt.baseOpacity * 0.5) {
              pt.x = cx + (Math.random() - 0.5) * 20
              pt.y = cy + (Math.random() - 0.5) * 20
              pt.opacity = pt.baseOpacity
            }
            pt.vx += (Math.random() - 0.5) * 0.08
            pt.vy += (Math.random() - 0.5) * 0.08
          } else if (p === 1) {
            // Awakening: coalesce toward orb center (spring physics)
            const orbY = cy - 60 // orb is above center
            const dx = cx - pt.x
            const dy = orbY - pt.y
            const dist = Math.sqrt(dx * dx + dy * dy)
            if (dist > 30) {
              pt.vx += (dx / dist) * 0.015
              pt.vy += (dy / dist) * 0.015
            } else {
              // Orbit when close
              pt.vx += (-dy / dist) * 0.008
              pt.vy += (dx / dist) * 0.008
            }
            // Fade in
            pt.opacity = Math.min(pt.opacity + 0.01, pt.baseOpacity)
          } else if (p === 5) {
            // Trust: contract, dim
            const dx = cx - pt.x
            const dy = cy - pt.y
            pt.vx += dx * 0.0003
            pt.vy += dy * 0.0003
            pt.opacity = Math.min(pt.opacity, pt.baseOpacity * 0.6)
          } else if (p === 6) {
            // Confirm: orbit formation
            const angle = (i / activeCount) * Math.PI * 2 + elapsed * 0.2
            const radius = 100 + (i % 3) * 20
            const targetX = cx + Math.cos(angle) * radius
            const targetY = cy + Math.sin(angle) * radius
            pt.vx += (targetX - pt.x) * 0.005
            pt.vy += (targetY - pt.y) * 0.005
            pt.opacity = Math.min(pt.opacity + 0.005, pt.baseOpacity)
          } else if (p === 7) {
            // Done: explosion outward, then drift
            if (elapsed < 1) {
              const dx = pt.x - cx
              const dy = pt.y - cy
              const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
              pt.vx += (dx / dist) * 0.5
              pt.vy += (dy / dist) * 0.5
              pt.opacity = Math.min(pt.baseOpacity * 1.5, 1)
            } else {
              pt.vx += (Math.random() - 0.5) * 0.02
              pt.vy += (Math.random() - 0.5) * 0.02
            }
          } else {
            // Phases 2-4: gentle ambient drift
            pt.vx += (Math.random() - 0.5) * 0.015
            pt.vy += (Math.random() - 0.5) * 0.015
            // Very gentle pull to center
            pt.vx += (cx - pt.x) * 0.00005
            pt.vy += (cy - pt.y) * 0.00005
            pt.opacity = Math.min(pt.opacity + 0.005, pt.baseOpacity)
          }
        }

        // Mouse repulsion
        if (mouse && pt.active) {
          const dx = pt.x - mouse.x
          const dy = pt.y - mouse.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < MOUSE_RADIUS && dist > 1) {
            const force = (MOUSE_FORCE * (MOUSE_RADIUS - dist)) / (dist * dist)
            pt.vx += dx * force
            pt.vy += dy * force
          }
        }

        // Integrate
        pt.x += pt.vx
        pt.y += pt.vy
        pt.vx *= DAMPING
        pt.vy *= DAMPING

        // Wrap at edges
        if (pt.x < -20) pt.x = w + 20
        if (pt.x > w + 20) pt.x = -20
        if (pt.y < -20) pt.y = h + 20
        if (pt.y > h + 20) pt.y = -20

        // Draw
        if (pt.opacity < 0.01) continue
        ctx.beginPath()
        ctx.arc(pt.x, pt.y, pt.size, 0, Math.PI * 2)
        ctx.fillStyle = `hsla(${pt.hue}, 70%, 75%, ${pt.opacity})`
        ctx.fill()
      }

      frameRef.current = requestAnimationFrame(loop)
    }

    frameRef.current = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(frameRef.current)
      window.removeEventListener('resize', resize)
    }
  }, [initParticles])

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0"
      role="presentation"
      aria-hidden="true"
    />
  )
}
