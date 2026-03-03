import { useState, useRef, useEffect } from 'react'
import {
  ChevronDown, Brain, PanelRight, MoreVertical,
  Download, GitBranch, Copy, Trash2,
  Minus, Square, X,
} from 'lucide-react'
import { useModelsStore } from '../../stores/models'
import { useChatStore } from '../../stores/chat'
import { useUIStore } from '../../stores/ui'
import { formatCost, formatTokens, formatLatency } from '../../lib/cost'
import { MODEL_CATEGORIES, PROVIDER_COLORS } from '../../api/types'
import { AppNav } from './AppNav'
import { IS_TAURI } from '../../lib/env'
import { getModeTheme } from '../../lib/mode-themes'

function ModelSelector() {
  const models = useModelsStore((s) => s.models)
  const activeModel = useModelsStore((s) => s.activeModel)
  const setActiveModel = useModelsStore((s) => s.setActiveModel)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const activeDisplay = activeModel === 'auto'
    ? 'Emily — Auto'
    : models[activeModel]?.display || activeModel

  // Build flat list of all model keys for keyboard nav
  const allKeys = ['auto', ...Object.values(MODEL_CATEGORIES).flat().filter((k) => models[k])]
  const [focusIdx, setFocusIdx] = useState(-1)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        if (!open) { setOpen(true); setFocusIdx(0) }
        else setFocusIdx(i => Math.min(i + 1, allKeys.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        if (open) setFocusIdx(i => Math.max(i - 1, 0))
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        if (open && focusIdx >= 0) { setActiveModel(allKeys[focusIdx]); setOpen(false) }
        else { setOpen(true); setFocusIdx(0) }
        break
      case 'Escape':
        setOpen(false)
        break
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Select model"
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-surface-hover text-sm font-medium transition-colors"
      >
        {activeModel !== 'auto' && models[activeModel] && (
          <span
            aria-hidden="true"
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: PROVIDER_COLORS[models[activeModel].provider] || '#555' }}
          />
        )}
        <span className="truncate max-w-[200px]">{activeDisplay}</span>
        <ChevronDown aria-hidden="true" className="w-3.5 h-3.5 text-text-muted" />
      </button>

      {open && (
        <div role="listbox" aria-label="Model list" className="absolute top-full left-0 mt-1 w-80 max-h-[70vh] overflow-y-auto bg-surface-raised border border-border rounded-xl shadow-2xl z-50">
          <button
            role="option"
            aria-selected={activeModel === 'auto'}
            onClick={() => { setActiveModel('auto'); setOpen(false) }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-surface-hover transition-colors
              ${activeModel === 'auto' ? 'text-accent' : 'text-text-primary'} ${focusIdx === 0 ? 'bg-surface-hover' : ''}`}
          >
            <Brain aria-hidden="true" className="w-4 h-4" />
            <div className="text-left">
              <div className="font-medium">Emily — Auto</div>
              <div className="text-xs text-text-muted">Smart routing based on your message</div>
            </div>
          </button>

          {Object.entries(MODEL_CATEGORIES).map(([category, keys]) => {
            const available = keys.filter((k) => models[k])
            if (available.length === 0) return null
            return (
              <div key={category} role="group" aria-label={category}>
                <div className="px-4 py-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider border-t border-border">
                  {category}
                </div>
                {available.map((key) => {
                  const m = models[key]
                  const idx = allKeys.indexOf(key)
                  return (
                    <button
                      key={key}
                      role="option"
                      aria-selected={activeModel === key}
                      onClick={() => { setActiveModel(key); setOpen(false) }}
                      className={`w-full flex items-center gap-3 px-4 py-2 text-sm hover:bg-surface-hover transition-colors
                        ${activeModel === key ? 'text-accent' : 'text-text-primary'} ${idx === focusIdx ? 'bg-surface-hover' : ''}`}
                    >
                      <span
                        aria-hidden="true"
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: PROVIDER_COLORS[m.provider] || '#555' }}
                      />
                      <div className="flex-1 text-left min-w-0">
                        <div className="truncate font-medium">{m.display.replace('Emily — ', '')}</div>
                        <div className="flex items-center gap-2 text-xs text-text-muted">
                          <span>{m.speed}</span>
                          {m.input_usd > 0 && <span>${m.input_usd}/{m.output_usd}</span>}
                          {m.thinking && <span className="text-phase-analyzing">thinking</span>}
                          {m.vision && <span className="text-cost-green">vision</span>}
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ModeBadge() {
  const activeSkill = useModelsStore((s) => s.activeSkill)
  const setModeSelectorOpen = useUIStore((s) => s.setModeSelectorOpen)
  const theme = getModeTheme(activeSkill)
  const Icon = theme.icon

  return (
    <button
      onClick={() => setModeSelectorOpen(true)}
      aria-label="Select mode (Ctrl+M)"
      title="Ctrl+M"
      className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-surface-hover text-sm transition-colors group"
    >
      <div
        className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
        style={{
          background: theme.gradient,
          boxShadow: `0 0 10px ${theme.glow}`,
        }}
      >
        <Icon className="w-3.5 h-3.5 text-white" />
      </div>
      <span style={{ color: theme.accent }} className="font-medium">
        {theme.name}
      </span>
      <ChevronDown className="w-3 h-3 text-text-muted group-hover:text-text-secondary transition-colors" />
    </button>
  )
}

export function TopBar() {
  const lastUsage = useChatStore((s) => s.lastUsage)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const toggleRightPanel = useUIStore((s) => s.toggleRightPanel)
  const rightPanelVisible = useUIStore((s) => s.rightPanelVisible)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const activeId = useChatStore((s) => s.activeId)
  const deleteConversation = useChatStore((s) => s.deleteConversation)
  const duplicateConversation = useChatStore((s) => s.duplicateConversation)

  const handleClose = async () => {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      getCurrentWindow().close()
    } catch { /* not in Tauri */ }
  }
  const handleMinimize = async () => {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      getCurrentWindow().minimize()
    } catch { /* not in Tauri */ }
  }
  const handleMaximize = async () => {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      const win = getCurrentWindow()
      if (await win.isMaximized()) {
        win.unmaximize()
      } else {
        win.maximize()
      }
    } catch { /* not in Tauri */ }
  }

  return (
    <div className="h-11 border-b border-border flex items-center px-3 gap-2 bg-surface-raised flex-shrink-0" data-tauri-drag-region>
      <span className="text-sm font-bold text-accent mr-1 select-none">Emily</span>
      <div className="w-px h-5 bg-border" />
      <AppNav />
      <div className="w-px h-5 bg-border" />
      <ModelSelector />
      <div className="w-px h-5 bg-border" />
      <ModeBadge />

      <div className="flex-1" data-tauri-drag-region />

      {(lastUsage || isStreaming) && (
        <div className="flex items-center gap-3 text-xs font-mono text-text-muted">
          {lastUsage && (
            <>
              <span>in: {formatTokens(lastUsage.tokens_in)}</span>
              <span>out: {formatTokens(lastUsage.tokens_out)}</span>
              {lastUsage.tokens_thinking > 0 && (
                <span className="text-phase-analyzing">think: {formatTokens(lastUsage.tokens_thinking)}</span>
              )}
              <span className={lastUsage.cost_usd > 0.05 ? 'text-warning-amber' : 'text-cost-green'}>
                {formatCost(lastUsage.cost_usd)}
              </span>
              <span>{formatLatency(lastUsage.latency_ms)}</span>
            </>
          )}
          {isStreaming && (
            <span className="flex items-center gap-1 text-accent" aria-live="polite">
              <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              streaming
            </span>
          )}
        </div>
      )}

      <button
        onClick={toggleRightPanel}
        className={`p-1.5 rounded-lg hover:bg-surface-hover transition-colors
          ${rightPanelVisible ? 'text-accent' : 'text-text-muted'}`}
        aria-label="Toggle reasoning panel"
      >
        <PanelRight aria-hidden="true" className="w-4 h-4" />
      </button>

      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Conversation actions"
          aria-haspopup="true"
          aria-expanded={menuOpen}
          className="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted transition-colors"
        >
          <MoreVertical aria-hidden="true" className="w-4 h-4" />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 w-48 bg-surface-raised border border-border rounded-xl shadow-2xl z-50">
            {[
              { icon: Download, label: 'Export', action: () => {}, disabled: true },
              { icon: GitBranch, label: 'Fork', action: () => {}, disabled: true },
              { icon: Copy, label: 'Duplicate', action: () => { if (activeId) duplicateConversation(activeId) }, disabled: !activeId },
              { icon: Trash2, label: 'Clear', action: () => {
                if (activeId && confirm('Delete this conversation?')) deleteConversation(activeId)
              }, disabled: !activeId },
            ].map(({ icon: Icon, label, action, disabled }) => (
              <button
                key={label}
                onClick={() => { if (!disabled) { action(); setMenuOpen(false) } }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors first:rounded-t-xl last:rounded-b-xl
                  ${disabled ? 'text-text-muted cursor-not-allowed opacity-50' : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'}`}
                title={disabled && (label === 'Export' || label === 'Fork') ? 'Coming soon' : undefined}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {IS_TAURI && (
        <>
          <div className="w-px h-5 bg-border ml-1" />
          <button onClick={handleMinimize} className="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted transition-colors" title="Minimize">
            <Minus className="w-4 h-4" />
          </button>
          <button onClick={handleMaximize} className="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted transition-colors" title="Maximize">
            <Square className="w-3.5 h-3.5" />
          </button>
          <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-surface-hover hover:text-error-red text-text-muted transition-colors" title="Close">
            <X className="w-4 h-4" />
          </button>
        </>
      )}
    </div>
  )
}
