import { useEffect, useState } from 'react'

interface Props {
  name: string
  visible: boolean
  onComplete?: () => void
}

export function FloatingName({ name, visible, onComplete }: Props) {
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (!visible) {
      setShow(false)
      return
    }
    setShow(true)
    const timer = setTimeout(() => {
      setShow(false)
      onComplete?.()
    }, 2000)
    return () => clearTimeout(timer)
  }, [visible, onComplete])

  if (!show || !name) return null

  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
      <span
        className="animate-float-up text-3xl font-light tracking-wide"
        style={{
          color: 'rgba(124,106,247,0.9)',
          textShadow: '0 0 30px rgba(124,106,247,0.5), 0 0 60px rgba(124,106,247,0.2)',
        }}
      >
        {name}
      </span>
    </div>
  )
}
