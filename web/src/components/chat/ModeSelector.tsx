import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Search, X } from 'lucide-react'
import { useUIStore } from '../../stores/ui'
import { useModelsStore } from '../../stores/models'
import { getModesByCategory, getModeTheme, type ModeTheme } from '../../lib/mode-themes'

const CAPABILITY_LABELS: Record<string, { label: string; color: string }> = {
  thinking:    { label: 'Thinking',  color: '#8b5cf6' },
  web_search:  { label: 'Web',      color: '#3b82f6' },
  code_exec:   { label: 'Code',     color: '#10b981' },
  multi_model: { label: 'Multi',    color: '#f59e0b' },
}

function TemperatureBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const hue = 200 - value * 160 // blue at 0 → orange-red at 1
  return (
    <div className="flex items-center gap-1.5" title={`Temperature: ${value}`}>
      <div className="w-12 h-1 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: `hsl(${hue}, 80%, 55%)` }}
        />
      </div>
      <span className="text-[10px] text-text-muted font-mono">{value}</span>
    </div>
  )
}

function ModeCard({
  theme,
  active,
  focused,
  index,
  onSelect,
  onHover,
}: {
  theme: ModeTheme
  active: boolean
  focused: boolean
  index: number
  onSelect: () => void
  onHover: () => void
}) {
  const Icon = theme.icon
  const ref = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: 'nearest' })
  }, [focused])

  return (
    <button
      ref={ref}
      onClick={onSelect}
      onMouseEnter={onHover}
      className={`
        animate-mode-card flex items-start gap-3 p-3 rounded-xl text-left transition-all
        ${focused ? 'bg-surface-hover ring-1 ring-border' : 'hover:bg-surface-hover/50'}
        ${active ? 'ring-1' : ''}
        active:scale-[0.97] active:transition-transform
      `}
      style={{
        animationDelay: `${index * 30}ms`,
        ...(active ? { ringColor: theme.accent, boxShadow: `0 0 12px ${theme.glow}` } : {}),
      }}
    >
      {/* Gradient icon container */}
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{
          background: theme.gradient,
          boxShadow: `0 0 16px ${theme.glow}`,
        }}
      >
        <Icon className="w-5 h-5 text-white" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm text-text-primary">{theme.name}</span>
          {active && (
            <span
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
              style={{ backgroundColor: `${theme.accent}20`, color: theme.accent }}
            >
              Active
            </span>
          )}
        </div>
        <p className="text-xs text-text-muted mt-0.5 line-clamp-2">{theme.description}</p>

        <div className="flex items-center gap-2 mt-1.5">
          {theme.capabilities.length > 0 && (
            <div className="flex items-center gap-1">
              {theme.capabilities.map((cap) => {
                const badge = CAPABILITY_LABELS[cap]
                if (!badge) return null
                return (
                  <span
                    key={cap}
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                    style={{ backgroundColor: `${badge.color}18`, color: badge.color }}
                  >
                    {badge.label}
                  </span>
                )
              })}
            </div>
          )}
          <TemperatureBar value={theme.temperature} />
        </div>
      </div>
    </button>
  )
}

export function ModeSelector() {
  const open = useUIStore((s) => s.modeSelectorOpen)
  const setOpen = useUIStore((s) => s.setModeSelectorOpen)
  const activeSkill = useModelsStore((s) => s.activeSkill)
  const setActiveSkill = useModelsStore((s) => s.setActiveSkill)

  const [query, setQuery] = useState('')
  const [focusIdx, setFocusIdx] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)

  const categories = useMemo(() => getModesByCategory(), [])

  // Filter modes by search query
  const filtered = useMemo(() => {
    if (!query.trim()) return categories
    const q = query.toLowerCase()
    return categories
      .map((cat) => ({
        ...cat,
        modes: cat.modes.filter(
          (m) =>
            m.name.toLowerCase().includes(q) ||
            m.description.toLowerCase().includes(q) ||
            m.id.includes(q)
        ),
      }))
      .filter((cat) => cat.modes.length > 0)
  }, [categories, query])

  // Flat list of all visible mode IDs for keyboard nav
  const flatModes = useMemo(
    () => filtered.flatMap((cat) => cat.modes),
    [filtered]
  )

  const selectMode = useCallback(
    (id: string) => {
      setActiveSkill(id)
      setOpen(false)
      setQuery('')
      setFocusIdx(-1)
    },
    [setActiveSkill, setOpen]
  )

  // Focus input on open
  useEffect(() => {
    if (open) {
      setQuery('')
      setFocusIdx(-1)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  // Keyboard navigation
  useEffect(() => {
    if (!open) return

    const handler = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setFocusIdx((i) => Math.min(i + 1, flatModes.length - 1))
          break
        case 'ArrowUp':
          e.preventDefault()
          setFocusIdx((i) => Math.max(i - 1, 0))
          break
        case 'Enter':
          e.preventDefault()
          if (focusIdx >= 0 && focusIdx < flatModes.length) {
            selectMode(flatModes[focusIdx].id)
          }
          break
        case 'Escape':
          e.preventDefault()
          setOpen(false)
          break
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, focusIdx, flatModes, selectMode, setOpen])

  if (!open) return null

  // Build a global running index so card stagger works across categories
  let globalIdx = 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]"
      style={{ backgroundColor: 'rgba(10, 10, 15, 0.85)', backdropFilter: 'blur(8px)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false)
      }}
    >
      <div className="animate-mode-overlay w-[640px] max-h-[72vh] flex flex-col bg-surface-raised/95 backdrop-blur-md border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Search header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search className="w-4 h-4 text-text-muted flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setFocusIdx(0)
            }}
            placeholder="Search modes..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
          />
          <button
            onClick={() => setOpen(false)}
            className="p-1 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Mode list */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
          {filtered.map((cat) => (
            <div key={cat.category}>
              <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider px-1 mb-2">
                {cat.label}
              </h3>
              <div className="grid grid-cols-2 gap-1.5">
                {cat.modes.map((mode) => {
                  const idx = globalIdx++
                  return (
                    <ModeCard
                      key={mode.id}
                      theme={mode}
                      active={activeSkill === mode.id}
                      focused={focusIdx === flatModes.indexOf(mode)}
                      index={idx}
                      onSelect={() => selectMode(mode.id)}
                      onHover={() => setFocusIdx(flatModes.indexOf(mode))}
                    />
                  )
                })}
              </div>
            </div>
          ))}

          {flatModes.length === 0 && (
            <div className="py-8 text-center text-sm text-text-muted">
              No modes match "{query}"
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-border text-xs text-text-muted">
          <div className="flex items-center gap-3">
            <span><kbd className="px-1 py-0.5 rounded bg-surface border border-border text-text-secondary">↑↓</kbd> Navigate</span>
            <span><kbd className="px-1 py-0.5 rounded bg-surface border border-border text-text-secondary">↵</kbd> Select</span>
            <span><kbd className="px-1 py-0.5 rounded bg-surface border border-border text-text-secondary">Esc</kbd> Close</span>
          </div>
          <span>
            Current: <span style={{ color: getModeTheme(activeSkill).accent }}>{getModeTheme(activeSkill).name}</span>
          </span>
        </div>
      </div>
    </div>
  )
}
