import { useState, useMemo, useEffect, useRef } from 'react'
import { ChevronDown, ChevronRight, Eye, FileText } from 'lucide-react'
import { useChatStore } from '../../stores/chat'

type PhaseType = 'analyzing' | 'considering' | 'comparing' | 'concluding' | 'uncertain'

interface Phase {
  type: PhaseType
  label: string
  content: string
}

const PHASE_CONFIG: Record<PhaseType, { color: string; icon: string; label: string }> = {
  analyzing: { color: '#3b82f6', icon: '🔍', label: 'Analyzing' },
  considering: { color: '#22c55e', icon: '💭', label: 'Considering' },
  comparing: { color: '#eab308', icon: '⚖️', label: 'Comparing' },
  concluding: { color: '#a855f7', icon: '✅', label: 'Concluding' },
  uncertain: { color: '#6b7280', icon: '🤔', label: 'Uncertain' },
}

function classifyPhase(text: string): PhaseType {
  const lower = text.toLowerCase()
  if (/\b(therefore|best approach|final|in conclusion|the answer)\b/.test(lower)) return 'concluding'
  if (/\b(compare|trade.?off|between|versus|pros.*cons)\b/.test(lower)) return 'comparing'
  if (/\b(option|alternatively|what if|could also|another approach)\b/.test(lower)) return 'considering'
  if (/\b(unsure|might|hmm|wait|not sure|uncertain)\b/.test(lower)) return 'uncertain'
  return 'analyzing'
}

function PhaseCard({ phase, defaultOpen }: { phase: Phase; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const config = PHASE_CONFIG[phase.type]

  return (
    <div className="border-l-2 mb-1" style={{ borderColor: config.color }}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 w-full text-left hover:bg-surface-hover transition-colors"
      >
        {open ? <ChevronDown className="w-3 h-3 text-text-muted" /> : <ChevronRight className="w-3 h-3 text-text-muted" />}
        <span className="text-xs">{config.icon}</span>
        <span className="text-xs font-medium" style={{ color: config.color }}>{config.label}</span>
      </button>
      {open && (
        <div className="px-4 pb-2 text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
          {phase.content}
        </div>
      )}
    </div>
  )
}

export function ThinkingPhases() {
  const streamingThinking = useChatStore((s) => s.streamingThinking)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const messages = useChatStore((s) => s.messages)
  const [viewMode, setViewMode] = useState<'phases' | 'raw'>('phases')
  const scrollRef = useRef<HTMLDivElement>(null)

  // Get thinking content: streaming first, then last assistant message
  const thinkingText = streamingThinking || (() => {
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
    return lastAssistant?.thinking_content || ''
  })()

  const phases = useMemo<Phase[]>(() => {
    if (!thinkingText) return []
    return thinkingText.split(/\n\n+/).filter(Boolean).map((block) => ({
      type: classifyPhase(block),
      label: PHASE_CONFIG[classifyPhase(block)].label,
      content: block.trim(),
    }))
  }, [thinkingText])

  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [thinkingText, isStreaming])

  if (!thinkingText) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-muted text-xs">
        No thinking content yet
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border">
        <span className="text-xs text-text-muted">
          {phases.length} phases · ~{Math.round(thinkingText.length / 4)} tokens
        </span>
        <div className="flex gap-1">
          <button
            onClick={() => setViewMode('phases')}
            className={`p-1 rounded ${viewMode === 'phases' ? 'bg-accent/20 text-accent' : 'text-text-muted hover:text-text-secondary'}`}
            title="Phases view"
          >
            <Eye className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setViewMode('raw')}
            className={`p-1 rounded ${viewMode === 'raw' ? 'bg-accent/20 text-accent' : 'text-text-muted hover:text-text-secondary'}`}
            title="Raw view"
          >
            <FileText className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-1">
        {viewMode === 'phases' ? (
          phases.map((phase, i) => (
            <PhaseCard key={i} phase={phase} defaultOpen={i === phases.length - 1} />
          ))
        ) : (
          <pre className="text-xs text-text-secondary p-3 whitespace-pre-wrap leading-relaxed font-mono">
            {thinkingText}
            {isStreaming && <span className="inline-block w-1.5 h-3.5 bg-accent animate-pulse ml-0.5" />}
          </pre>
        )}
      </div>
    </div>
  )
}
