import { useState, useEffect, useCallback } from 'react'
import {
  Workflow, Brain, GitCompare, Clock, Database,
  Maximize2, Minimize2, PanelRightClose,
} from 'lucide-react'
import { useUIStore, type ReasoningPanelSize } from '../../stores/ui'
import { useChatStore } from '../../stores/chat'
import { FlowDiagram } from './FlowDiagram'
import { ThinkingPhases } from './ThinkingPhases'
import { ModelComparison } from './ModelComparison'
import { ReasoningTimeline } from './ReasoningTimeline'
import { MemoryInsight } from './MemoryInsight'
import { ReasoningMetrics } from './ReasoningMetrics'

type Tab = 'flow' | 'thinking' | 'comparison' | 'timeline' | 'memory'

const TABS: Array<{ id: Tab; label: string; icon: typeof Workflow }> = [
  { id: 'flow', label: 'Flow', icon: Workflow },
  { id: 'thinking', label: 'Thinking', icon: Brain },
  { id: 'comparison', label: 'Compare', icon: GitCompare },
  { id: 'timeline', label: 'Timeline', icon: Clock },
  { id: 'memory', label: 'Memory', icon: Database },
]

const SIZE_ICON: Record<ReasoningPanelSize, typeof Maximize2> = {
  sidebar: Maximize2,
  half: Maximize2,
  fullscreen: Minimize2,
  hidden: Maximize2,
}

export function ReasoningPanelV2() {
  const [activeTab, setActiveTab] = useState<Tab>('flow')
  const panelSize = useUIStore((s) => s.reasoningPanelSize)
  const cyclePanel = useUIStore((s) => s.cycleReasoningPanel)
  const setSize = useUIStore((s) => s.setReasoningPanelSize)
  const streamMeta = useChatStore((s) => s.streamMeta)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const streamingThinking = useChatStore((s) => s.streamingThinking)

  // Auto-switch to thinking tab when thinking content arrives
  useEffect(() => {
    if (streamingThinking && activeTab === 'flow') {
      setActiveTab('thinking')
    }
  }, [streamingThinking, activeTab])

  // Keyboard shortcut: Ctrl+Shift+R to cycle panel sizes
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'R') {
      e.preventDefault()
      cyclePanel()
    }
  }, [cyclePanel])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const modeDisplay = streamMeta?.mode_display || 'Normal'
  const modeIcon = streamMeta?.mode_icon || ''
  const strategy = streamMeta?.reasoning_strategy || 'direct'

  const SizeIcon = SIZE_ICON[panelSize]

  const tabContent = () => {
    switch (activeTab) {
      case 'flow': return <FlowDiagram />
      case 'thinking': return <ThinkingPhases />
      case 'comparison': return <ModelComparison />
      case 'timeline': return <ReasoningTimeline />
      case 'memory': return <MemoryInsight />
    }
  }

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <Brain className="w-4 h-4 text-accent flex-shrink-0" />
          <span className="text-xs font-medium text-text-primary truncate">Reasoning</span>
          {isStreaming && (
            <span className="flex items-center gap-1 text-[10px] text-accent">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              {modeIcon} {modeDisplay}
            </span>
          )}
          {strategy !== 'direct' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent">
              {strategy.replace(/_/g, ' ')}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={cyclePanel}
            className="p-1 rounded text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
            title={`Panel: ${panelSize} (Ctrl+Shift+R)`}
          >
            <SizeIcon className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setSize('hidden')}
            className="p-1 rounded text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
            title="Close panel"
          >
            <PanelRightClose className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1 px-3 py-1.5 text-[11px] transition-colors border-b-2 ${
              activeTab === id
                ? 'border-accent text-accent'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
          >
            <Icon className="w-3 h-3" />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {tabContent()}
      </div>

      {/* Bottom metrics bar */}
      <ReasoningMetrics />
    </div>
  )
}
