import { useState, useEffect, useRef } from 'react'

interface Props {
  text: string
  speed?: number
  className?: string
  onComplete?: () => void
}

export function NarrativeText({ text, speed = 22, className = '', onComplete }: Props) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)
  const completedRef = useRef(false)

  useEffect(() => {
    setDisplayed('')
    setDone(false)
    completedRef.current = false
    if (!text) return

    let i = 0
    const id = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) {
        clearInterval(id)
        setDone(true)
        if (!completedRef.current) {
          completedRef.current = true
          onComplete?.()
        }
      }
    }, speed)

    return () => clearInterval(id)
  }, [text, speed, onComplete])

  if (!text) return null

  return (
    <div className={`animate-fade-up ${className}`}>
      <div
        className="max-w-sm rounded-2xl rounded-bl-md px-4 py-3 backdrop-blur-xl"
        style={{
          background: 'rgba(255,255,255,0.035)',
          border: '1px solid rgba(255,255,255,0.07)',
          boxShadow: '0 4px 24px rgba(0,0,0,0.2)',
        }}
      >
        <p className="text-sm leading-relaxed text-text-primary/90">
          {displayed}
          {!done && (
            <span className="-mb-0.5 ml-0.5 inline-block h-3.5 w-0.5 animate-pulse rounded-sm bg-accent" />
          )}
        </p>
      </div>
    </div>
  )
}
