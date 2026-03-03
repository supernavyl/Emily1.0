import { useMemo, useRef, useEffect, useState } from 'react'
import {
  Brain, Clock, Cpu, DollarSign, Gauge, Eye, AlignLeft,
  ChevronDown, ChevronRight, Timer, Search, Lightbulb,
  Scale, CheckCircle2, HelpCircle, Sparkles,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import { formatCost, formatTokens, formatLatency } from '../../lib/cost'
import { PROVIDER_COLORS } from '../../api/types'

// ── Phase detection ─────────────────────────────────────────────

interface ReasoningPhase {
  type: 'analyzing' | 'considering' | 'comparing' | 'concluding' | 'uncertain'
  content: string
}

const PHASE_PATTERNS: Array<{ type: ReasoningPhase['type']; pattern: RegExp }> = [
  { type: 'analyzing', pattern: /\b(break down|understand|analyze|examine|look at|let me think|let's|first|need to)\b/i },
  { type: 'considering', pattern: /\b(consider|option|approach|alternatively|what if|one way|could|maybe|perhaps)\b/i },
  { type: 'comparing', pattern: /\b(compare|versus|trade-?off|better|worse|between|however|on the other hand)\b/i },
  { type: 'concluding', pattern: /\b(therefore|thus|conclude|best approach|in summary|so the|final|answer is)\b/i },
  { type: 'uncertain', pattern: /\b(unsure|not certain|might|unclear|hard to say|depends|tricky|hmm|wait)\b/i },
]

const PHASE_COLORS: Record<string, { border: string; text: string; bg: string }> = {
  analyzing:   { border: 'border-phase-analyzing',   text: 'text-phase-analyzing',   bg: 'bg-phase-analyzing/5' },
  considering: { border: 'border-phase-considering', text: 'text-phase-considering', bg: 'bg-phase-considering/5' },
  comparing:   { border: 'border-phase-comparing',   text: 'text-phase-comparing',   bg: 'bg-phase-comparing/5' },
  concluding:  { border: 'border-phase-concluding',  text: 'text-phase-concluding',  bg: 'bg-phase-concluding/5' },
  uncertain:   { border: 'border-phase-uncertain',   text: 'text-phase-uncertain',   bg: 'bg-phase-uncertain/5' },
}

const PHASE_LABELS: Record<string, string> = {
  analyzing: 'Analyzing',
  considering: 'Considering',
  comparing: 'Comparing',
  concluding: 'Concluding',
  uncertain: 'Uncertain',
}

const PHASE_ICONS: Record<string, LucideIcon> = {
  analyzing:   Search,
  considering: Lightbulb,
  comparing:   Scale,
  concluding:  CheckCircle2,
  uncertain:   HelpCircle,
}

function detectPhase(text: string): ReasoningPhase['type'] {
  for (const { type, pattern } of PHASE_PATTERNS) {
    if (pattern.test(text)) return type
  }
  return 'analyzing'
}

// ── Elapsed timer hook ──────────────────────────────────────────

function useElapsed(active: boolean) {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef(0)

  useEffect(() => {
    if (!active) {
      setElapsed(0)
      return
    }
    startRef.current = Date.now()
    const id = setInterval(() => setElapsed(Date.now() - startRef.current), 100)
    return () => clearInterval(id)
  }, [active])

  return elapsed
}

function formatElapsed(ms: number): string {
  if (ms < 1000) return '0s'
  const s = Math.floor(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

// ── Phase card (expandable) ─────────────────────────────────────

function PhaseCard({ phase, defaultOpen }: { phase: ReasoningPhase; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? true)
  const colors = PHASE_COLORS[phase.type]
  const PhaseIcon = PHASE_ICONS[phase.type] || Search
  const isLong = phase.content.length > 200

  return (
    <div className={`border-l-2 ${colors.border} ${colors.bg} rounded-r-lg transition-colors`}>
      <button
        onClick={() => isLong && setOpen(!open)}
        className={`w-full flex items-center gap-1.5 px-3 py-1.5 ${isLong ? 'cursor-pointer hover:bg-white/[0.03]' : 'cursor-default'}`}
      >
        {isLong ? (
          open
            ? <ChevronDown className={`w-3 h-3 ${colors.text} shrink-0`} />
            : <ChevronRight className={`w-3 h-3 ${colors.text} shrink-0`} />
        ) : (
          <PhaseIcon className={`w-3 h-3 ${colors.text} shrink-0`} />
        )}
        <span className={`text-[10px] font-semibold uppercase tracking-wider ${colors.text}`}>
          {PHASE_LABELS[phase.type]}
        </span>
        {!open && isLong && (
          <span className="text-[10px] text-text-muted ml-auto">
            {phase.content.length} chars
          </span>
        )}
      </button>
      {open && (
        <div className="px-3 pb-2">
          <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
            {phase.content}
          </p>
        </div>
      )}
    </div>
  )
}

// ── Raw thinking view ───────────────────────────────────────────

function EmptyReasoningState() {
  return (
    <div className="flex flex-col items-center justify-center py-10 px-4 gap-3">
      <div className="w-10 h-10 rounded-xl bg-phase-analyzing/10 flex items-center justify-center">
        <Sparkles className="w-5 h-5 text-phase-analyzing/60" />
      </div>
      <p className="text-xs text-text-muted text-center leading-relaxed">
        Emily's reasoning process will appear here when she uses extended thinking
      </p>
    </div>
  )
}

function RawView({ text, streaming }: { text: string; streaming: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (streaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [text, streaming])

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3">
      {text ? (
        <pre className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap font-sans">
          {text}
          {streaming && (
            <span className="inline-block w-1.5 h-3.5 bg-phase-analyzing animate-pulse ml-0.5 -mb-0.5 rounded-sm" />
          )}
        </pre>
      ) : (
        <EmptyReasoningState />
      )}
    </div>
  )
}

// ── Phases view ─────────────────────────────────────────────────

function PhasesView({ phases, streaming }: { phases: ReasoningPhase[]; streaming: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (streaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [phases, streaming])

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
      {phases.length > 0 ? (
        phases.map((phase, i) => (
          <PhaseCard key={i} phase={phase} defaultOpen={streaming ? true : i >= phases.length - 3} />
        ))
      ) : (
        <EmptyReasoningState />
      )}
      {streaming && phases.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-phase-analyzing animate-pulse" />
          <span className="text-[10px] text-text-muted">thinking...</span>
        </div>
      )}
    </div>
  )
}

// ── Metadata row ────────────────────────────────────────────────

function MetadataRow({ icon: Icon, label, value, color }: {
  icon: typeof Brain; label: string; value: string; color?: string
}) {
  return (
    <div className="flex items-center justify-between py-1">
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <Icon className="w-3.5 h-3.5" />
        <span>{label}</span>
      </div>
      <span className={`text-xs font-mono ${color || 'text-text-secondary'}`}>{value}</span>
    </div>
  )
}

// ── Session stats ───────────────────────────────────────────────

function SessionStats() {
  const messages = useChatStore((s) => s.messages)

  const stats = useMemo(() => {
    let totalTokens = 0
    let totalCost = 0
    let totalLatency = 0
    let msgCount = 0
    const modelsUsed = new Set<string>()

    for (const m of messages) {
      if (m.role === 'assistant') {
        totalTokens += m.tokens_in + m.tokens_out + m.tokens_thinking
        totalCost += m.cost_usd
        totalLatency += m.latency_ms || 0
        msgCount++
        if (m.model) modelsUsed.add(m.model)
      }
    }

    return {
      messages: messages.length,
      totalTokens,
      totalCost,
      avgLatency: msgCount > 0 ? Math.round(totalLatency / msgCount) : 0,
      modelsUsed: modelsUsed.size,
    }
  }, [messages])

  return (
    <div className="space-y-1">
      <MetadataRow icon={Brain} label="Messages" value={String(stats.messages)} />
      <MetadataRow icon={Cpu} label="Total tokens" value={formatTokens(stats.totalTokens)} />
      <MetadataRow icon={DollarSign} label="Total cost" value={formatCost(stats.totalCost)} color="text-cost-green" />
      <MetadataRow icon={Gauge} label="Avg latency" value={stats.avgLatency > 0 ? formatLatency(stats.avgLatency) : '—'} />
      <MetadataRow icon={Brain} label="Models used" value={String(stats.modelsUsed)} />
    </div>
  )
}

// ── Main panel ──────────────────────────────────────────────────

type ViewMode = 'phases' | 'raw'

export function ReasoningPanel() {
  const streamingThinking = useChatStore((s) => s.streamingThinking)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const lastUsage = useChatStore((s) => s.lastUsage)
  const streamMeta = useChatStore((s) => s.streamMeta)
  const messages = useChatStore((s) => s.messages)

  const [viewMode, setViewMode] = useState<ViewMode>('phases')
  const [lastMsgOpen, setLastMsgOpen] = useState(true)
  const [sessionOpen, setSessionOpen] = useState(true)

  const lastAssistant = useMemo(
    () => [...messages].reverse().find((m) => m.role === 'assistant'),
    [messages],
  )

  const thinkingText = isStreaming ? streamingThinking : lastAssistant?.thinking_content || ''
  const isThinking = isStreaming && !!streamingThinking
  const elapsed = useElapsed(isThinking)

  // Estimate tokens from character count (~4 chars per token)
  const estimatedTokens = Math.round(thinkingText.length / 4)

  const phases = useMemo(() => {
    if (!thinkingText) return []
    const paragraphs = thinkingText.split(/\n{2,}/).filter(Boolean)
    return paragraphs.map((p): ReasoningPhase => ({
      type: detectPhase(p),
      content: p.trim(),
    }))
  }, [thinkingText])

  const displayUsage = lastUsage || (lastAssistant ? {
    tokens_in: lastAssistant.tokens_in,
    tokens_out: lastAssistant.tokens_out,
    tokens_thinking: lastAssistant.tokens_thinking,
    cost_usd: lastAssistant.cost_usd,
    latency_ms: lastAssistant.latency_ms || 0,
    model_key: lastAssistant.model || '',
    provider: lastAssistant.provider || '',
  } : null)

  return (
    <div className="h-full flex flex-col bg-surface-raised">
      {/* ── Thinking section ─────────────────────────── */}
      <div className="flex-[3] border-b border-border overflow-hidden flex flex-col">
        {/* Header with controls */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-wider shrink-0">
            <Brain className="w-3.5 h-3.5" />
            Reasoning
          </div>

          <div className="flex items-center gap-2">
            {/* View toggle */}
            {thinkingText && (
              <div className="flex items-center bg-surface rounded-lg border border-border overflow-hidden">
                <button
                  onClick={() => setViewMode('phases')}
                  className={`flex items-center gap-1 px-2 py-1 text-[10px] transition-colors ${
                    viewMode === 'phases' ? 'bg-accent/15 text-accent' : 'text-text-muted hover:text-text-secondary'
                  }`}
                  title="Classified phases"
                >
                  <Eye className="w-3 h-3" />
                  Phases
                </button>
                <button
                  onClick={() => setViewMode('raw')}
                  className={`flex items-center gap-1 px-2 py-1 text-[10px] transition-colors ${
                    viewMode === 'raw' ? 'bg-accent/15 text-accent' : 'text-text-muted hover:text-text-secondary'
                  }`}
                  title="Raw thinking text"
                >
                  <AlignLeft className="w-3 h-3" />
                  Raw
                </button>
              </div>
            )}

            {/* Live indicator */}
            {isThinking && (
              <div className="flex items-center gap-1 text-[10px] text-phase-analyzing shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-phase-analyzing animate-pulse" />
                live
              </div>
            )}
          </div>
        </div>

        {/* Live metrics bar (only during active thinking) */}
        {isThinking && (
          <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border/50 bg-surface">
            <div className="flex items-center gap-1 text-[10px] text-text-muted">
              <Timer className="w-3 h-3" />
              <span className="font-mono text-text-secondary">{formatElapsed(elapsed)}</span>
            </div>
            <div className="flex items-center gap-1 text-[10px] text-text-muted">
              <Brain className="w-3 h-3" />
              <span className="font-mono text-text-secondary">~{estimatedTokens.toLocaleString()} tok</span>
            </div>
            {streamMeta?.model_key && (
              <div className="flex items-center gap-1 text-[10px] text-text-muted ml-auto">
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: PROVIDER_COLORS[streamMeta.provider] || '#555' }}
                />
                <span className="truncate max-w-[100px]">{streamMeta.model_key}</span>
              </div>
            )}
          </div>
        )}

        {/* Done metrics bar (after thinking finished, showing final stats) */}
        {!isThinking && thinkingText && (
          <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border/50 bg-surface">
            <div className="flex items-center gap-1 text-[10px] text-text-muted">
              <Brain className="w-3 h-3" />
              <span className="font-mono text-text-secondary">
                {displayUsage?.tokens_thinking
                  ? formatTokens(displayUsage.tokens_thinking)
                  : `~${estimatedTokens.toLocaleString()}`} think tokens
              </span>
            </div>
            <div className="flex items-center gap-1 text-[10px] text-text-muted">
              <AlignLeft className="w-3 h-3" />
              <span className="font-mono text-text-secondary">{phases.length} phases</span>
            </div>
          </div>
        )}

        {/* Content area */}
        {viewMode === 'raw' ? (
          <RawView text={thinkingText} streaming={isThinking} />
        ) : (
          <PhasesView phases={phases} streaming={isThinking} />
        )}
      </div>

      {/* ── Last Message section ─────────────────────── */}
      <div className={`${lastMsgOpen ? 'flex-[2]' : 'flex-none'} border-b border-border overflow-hidden flex flex-col`}>
        <button
          onClick={() => setLastMsgOpen(!lastMsgOpen)}
          className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border text-xs font-semibold text-text-muted uppercase tracking-wider hover:text-text-secondary transition-colors w-full text-left"
        >
          {lastMsgOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Last Message
          {!lastMsgOpen && displayUsage && (
            <span className="ml-auto text-text-muted font-normal normal-case tracking-normal">
              {formatCost(displayUsage.cost_usd)} · {formatLatency(displayUsage.latency_ms)}
            </span>
          )}
        </button>
        {lastMsgOpen && (
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {displayUsage ? (
              <div className="space-y-1">
                {displayUsage.model_key && (
                  <div className="flex items-center gap-2 text-xs text-text-secondary mb-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: PROVIDER_COLORS[displayUsage.provider] || '#555' }}
                    />
                    <span>{displayUsage.model_key}</span>
                    <span className="text-text-muted">({displayUsage.provider})</span>
                  </div>
                )}
                <MetadataRow icon={Cpu} label="Tokens in" value={formatTokens(displayUsage.tokens_in)} />
                <MetadataRow icon={Cpu} label="Tokens out" value={formatTokens(displayUsage.tokens_out)} />
                {displayUsage.tokens_thinking > 0 && (
                  <MetadataRow icon={Brain} label="Think tokens" value={formatTokens(displayUsage.tokens_thinking)} color="text-phase-analyzing" />
                )}
                <MetadataRow icon={DollarSign} label="Cost" value={formatCost(displayUsage.cost_usd)} color="text-cost-green" />
                <MetadataRow icon={Clock} label="Latency" value={formatLatency(displayUsage.latency_ms)} />
              </div>
            ) : (
              <p className="text-xs text-text-muted text-center py-4">No message data yet</p>
            )}
          </div>
        )}
      </div>

      {/* ── Session Stats section ────────────────────── */}
      <div className={`${sessionOpen ? 'flex-[1]' : 'flex-none'} overflow-hidden flex flex-col`}>
        <button
          onClick={() => setSessionOpen(!sessionOpen)}
          className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border text-xs font-semibold text-text-muted uppercase tracking-wider hover:text-text-secondary transition-colors w-full text-left"
        >
          {sessionOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Session Stats
        </button>
        {sessionOpen && (
          <div className="flex-1 overflow-y-auto px-4 py-3">
            <SessionStats />
          </div>
        )}
      </div>
    </div>
  )
}
