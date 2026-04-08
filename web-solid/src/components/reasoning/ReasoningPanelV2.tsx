import { createSignal, createEffect, onMount, onCleanup, Switch, Match, For } from 'solid-js'
import {
  Workflow, Brain, GitCompare, Clock, Database,
  Maximize2, Minimize2, PanelRightClose,
} from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'
import {
  uiState, cycleReasoningPanel, setReasoningPanelSize,
} from '../../stores/ui'
import type { ReasoningPanelSize } from '../../stores/ui'
import { chatState } from '../../stores/chat'
import { FlowDiagram } from './FlowDiagram'
import { ThinkingPhases } from './ThinkingPhases'
import { ModelComparison } from './ModelComparison'
import { ReasoningTimeline } from './ReasoningTimeline'
import { MemoryInsight } from './MemoryInsight'
import { ReasoningMetrics } from './ReasoningMetrics'

type Tab = 'flow' | 'thinking' | 'comparison' | 'timeline' | 'memory'

const TABS: Array<{ id: Tab; label: string; icon: LucideIcon }> = [
  { id: 'flow', label: 'Flow', icon: Workflow },
  { id: 'thinking', label: 'Thinking', icon: Brain },
  { id: 'comparison', label: 'Compare', icon: GitCompare },
  { id: 'timeline', label: 'Timeline', icon: Clock },
  { id: 'memory', label: 'Memory', icon: Database },
]

const SIZE_ICON: Record<ReasoningPanelSize, LucideIcon> = {
  sidebar: Maximize2,
  half: Maximize2,
  fullscreen: Minimize2,
  hidden: Maximize2,
}

export function ReasoningPanelV2() {
  const [activeTab, setActiveTab] = createSignal<Tab>('flow')

  // Auto-switch to thinking tab when thinking content arrives
  createEffect(() => {
    if (chatState.streamingThinking && activeTab() === 'flow') {
      setActiveTab('thinking')
    }
  })

  // Keyboard shortcut: Ctrl+Shift+R to cycle panel sizes
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'R') {
      e.preventDefault()
      cycleReasoningPanel()
    }
  }

  onMount(() => {
    document.addEventListener('keydown', handleKeyDown)
  })
  onCleanup(() => {
    document.removeEventListener('keydown', handleKeyDown)
  })

  const modeDisplay = () => chatState.streamMeta?.mode_display || 'Normal'
  const modeIcon = () => chatState.streamMeta?.mode_icon || ''
  const strategy = () => chatState.streamMeta?.reasoning_strategy || 'direct'

  const SizeIcon = () => SIZE_ICON[uiState.reasoningPanelSize]

  return (
    <div class="flex flex-col h-full" style={{ background: 'oklch(0.18 0.02 185)' }}>
      {/* Header */}
      <div
        class="flex items-center justify-between px-3 py-2"
        style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)' }}
      >
        <div class="flex items-center gap-2 min-w-0">
          <Brain size={16} class="flex-shrink-0" style={{ color: 'oklch(0.72 0.17 162)' }} />
          <span
            class="truncate"
            style={{
              'font-size': 'var(--text-small)',
              'font-weight': '600',
              'font-family': 'var(--font-display)',
              color: 'oklch(0.93 0.01 90)',
            }}
          >
            Reasoning
          </span>
          {chatState.isStreaming && (
            <span
              class="flex items-center gap-1"
              style={{
                'font-size': '0.625rem',
                color: 'oklch(0.72 0.17 162)',
                'font-family': 'var(--font-mono)',
              }}
            >
              <span
                class="w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ background: 'oklch(0.72 0.17 162)' }}
              />
              {modeIcon()} {modeDisplay()}
            </span>
          )}
          {strategy() !== 'direct' && (
            <span
              class="px-1.5 py-0.5 rounded"
              style={{
                'font-size': '0.625rem',
                'font-family': 'var(--font-display)',
                background: 'oklch(0.72 0.17 162 / 0.10)',
                color: 'oklch(0.72 0.17 162)',
              }}
            >
              {strategy().replace(/_/g, ' ')}
            </span>
          )}
        </div>

        <div class="flex items-center gap-1">
          <button
            onClick={() => setReasoningPanelSize(
              uiState.reasoningPanelSize === 'fullscreen' ? 'sidebar' : 'fullscreen'
            )}
            class="p-1 rounded transition-colors"
            style={{ color: 'oklch(0.50 0.04 185)', background: 'transparent', border: 'none', cursor: 'pointer' }}
            title={uiState.reasoningPanelSize === 'fullscreen' ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {uiState.reasoningPanelSize === 'fullscreen'
              ? <Minimize2 size={14} />
              : <Maximize2 size={14} />}
          </button>
          <button
            onClick={() => setReasoningPanelSize('hidden')}
            class="p-1 rounded transition-colors"
            style={{ color: 'oklch(0.50 0.04 185)', background: 'transparent', border: 'none', cursor: 'pointer' }}
            title="Close panel"
          >
            <PanelRightClose size={14} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div class="flex" style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)' }}>
        <For each={TABS}>
          {(tab) => {
            const Icon = tab.icon
            return (
              <button
                onClick={() => setActiveTab(tab.id)}
                class="flex items-center gap-1 px-3 py-1.5 transition-colors"
                style={{
                  'font-size': '0.6875rem',
                  'font-family': 'var(--font-display)',
                  'border-bottom': `2px solid ${activeTab() === tab.id ? 'oklch(0.72 0.17 162)' : 'transparent'}`,
                  color: activeTab() === tab.id ? 'oklch(0.72 0.17 162)' : 'oklch(0.50 0.04 185)',
                  background: 'transparent',
                  border: 'none',
                  'border-bottom-width': '2px',
                  'border-bottom-style': 'solid',
                  'border-bottom-color': activeTab() === tab.id ? 'oklch(0.72 0.17 162)' : 'transparent',
                  cursor: 'pointer',
                }}
              >
                <Icon size={12} />
                <span>{tab.label}</span>
              </button>
            )
          }}
        </For>
      </div>

      {/* Tab content */}
      <div class="flex-1 min-h-0 overflow-hidden flex flex-col">
        <Switch>
          <Match when={activeTab() === 'flow'}>
            <FlowDiagram />
          </Match>
          <Match when={activeTab() === 'thinking'}>
            <ThinkingPhases />
          </Match>
          <Match when={activeTab() === 'comparison'}>
            <ModelComparison />
          </Match>
          <Match when={activeTab() === 'timeline'}>
            <ReasoningTimeline />
          </Match>
          <Match when={activeTab() === 'memory'}>
            <MemoryInsight />
          </Match>
        </Switch>
      </div>

      {/* Bottom metrics bar */}
      <ReasoningMetrics />
    </div>
  )
}
