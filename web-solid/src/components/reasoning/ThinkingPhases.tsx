import { createSignal, createEffect, createMemo, Show, For } from 'solid-js'
import { Eye, FileText } from 'lucide-solid'
import { chatState } from '../../stores/chat'

type PhaseType = 'analyzing' | 'considering' | 'comparing' | 'concluding' | 'uncertain'

interface Phase {
  type: PhaseType
  label: string
  content: string
}

const PHASE_CONFIG: Record<PhaseType, { color: string; icon: string; label: string }> = {
  analyzing: { color: 'var(--color-phase-analyzing)', icon: '🔍', label: 'Analyzing' },
  considering: { color: 'var(--color-cost-green)', icon: '💭', label: 'Considering' },
  comparing: { color: 'var(--color-warning-amber)', icon: '⚖️', label: 'Comparing' },
  concluding: { color: 'var(--color-accent)', icon: '✅', label: 'Concluding' },
  uncertain: { color: 'var(--color-text-muted)', icon: '🤔', label: 'Uncertain' },
}

function classifyPhase(text: string): PhaseType {
  const lower = text.toLowerCase()
  if (/\b(therefore|best approach|final|in conclusion|the answer)\b/.test(lower)) return 'concluding'
  if (/\b(compare|trade.?off|between|versus|pros.*cons)\b/.test(lower)) return 'comparing'
  if (/\b(option|alternatively|what if|could also|another approach)\b/.test(lower)) return 'considering'
  if (/\b(unsure|might|hmm|wait|not sure|uncertain)\b/.test(lower)) return 'uncertain'
  return 'analyzing'
}

interface PhaseCardProps {
  phase: Phase
  defaultOpen: boolean
}

function PhaseCard(props: PhaseCardProps) {
  const [open, setOpen] = createSignal(props.defaultOpen)
  const config = () => PHASE_CONFIG[props.phase.type]

  return (
    <div class="mb-1" style={{ 'border-left': `2px solid ${config().color}` }}>
      <button
        onClick={() => setOpen(!open())}
        class="flex items-center gap-2 px-3 py-1.5 w-full text-left transition-colors"
        style={{ background: 'transparent' }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-surface-hover)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
      >
        <Show when={open()} fallback={
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" stroke-width="2">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        }>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" stroke-width="2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </Show>
        <span class="text-xs">{config().icon}</span>
        <span class="text-xs font-medium" style={{ color: config().color }}>{config().label}</span>
      </button>
      <Show when={open()}>
        <div class="px-4 pb-2 text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--color-text-secondary)' }}>
          {props.phase.content}
        </div>
      </Show>
    </div>
  )
}

export function ThinkingPhases() {
  const [viewMode, setViewMode] = createSignal<'phases' | 'raw'>('phases')
  let scrollRef: HTMLDivElement | undefined

  const thinkingText = createMemo(() => {
    if (chatState.streamingThinking) return chatState.streamingThinking
    const lastAssistant = [...chatState.messages].reverse().find((m) => m.role === 'assistant')
    return lastAssistant?.thinking_content || ''
  })

  const phases = createMemo<Phase[]>(() => {
    const text = thinkingText()
    if (!text) return []
    return text.split(/\n\n+/).filter(Boolean).map((block) => ({
      type: classifyPhase(block),
      label: PHASE_CONFIG[classifyPhase(block)].label,
      content: block.trim(),
    }))
  })

  createEffect(() => {
    // Track dependencies
    const _ = thinkingText()
    if (chatState.isStreaming && scrollRef) {
      scrollRef.scrollTop = scrollRef.scrollHeight
    }
  })

  return (
    <Show when={thinkingText()} fallback={
      <div class="flex-1 flex items-center justify-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
        No thinking content yet
      </div>
    }>
      <div class="flex flex-col h-full">
        <div
          class="flex items-center justify-between px-3 py-1.5"
          style={{ 'border-bottom': '1px solid var(--color-border)' }}
        >
          <span class="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {phases().length} phases · ~{Math.round(thinkingText().length / 4)} tokens
          </span>
          <div class="flex gap-1">
            <button
              onClick={() => setViewMode('phases')}
              class="p-1 rounded"
              style={{
                background: viewMode() === 'phases' ? 'oklch(0.72 0.17 162 / 0.2)' : 'transparent',
                color: viewMode() === 'phases' ? 'var(--color-accent)' : 'var(--color-text-muted)',
              }}
              title="Phases view"
            >
              <Eye size={14} />
            </button>
            <button
              onClick={() => setViewMode('raw')}
              class="p-1 rounded"
              style={{
                background: viewMode() === 'raw' ? 'oklch(0.72 0.17 162 / 0.2)' : 'transparent',
                color: viewMode() === 'raw' ? 'var(--color-accent)' : 'var(--color-text-muted)',
              }}
              title="Raw view"
            >
              <FileText size={14} />
            </button>
          </div>
        </div>

        <div ref={scrollRef} class="flex-1 overflow-y-auto p-1">
          <Show when={viewMode() === 'phases'} fallback={
            <pre
              class="text-xs p-3 whitespace-pre-wrap leading-relaxed font-mono"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {thinkingText()}
              <Show when={chatState.isStreaming}>
                <span class="inline-block w-1.5 h-3.5 animate-pulse ml-0.5" style={{ background: 'var(--color-accent)' }} />
              </Show>
            </pre>
          }>
            <For each={phases()}>
              {(phase, i) => (
                <PhaseCard phase={phase} defaultOpen={i() === phases().length - 1} />
              )}
            </For>
          </Show>
        </div>
      </div>
    </Show>
  )
}
