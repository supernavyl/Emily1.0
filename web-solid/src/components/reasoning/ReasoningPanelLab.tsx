import {
  createSignal, createEffect, createMemo, onMount, onCleanup,
  Show, For,
} from 'solid-js'
import { Maximize2, Minimize2, PanelRightClose } from 'lucide-solid'
import {
  uiState, cycleReasoningPanel, setReasoningPanelSize,
} from '../../stores/ui'
import { chatState } from '../../stores/chat'

// ── Phase classification (lifted from ThinkingPhases.tsx) ──────────────────

type PhaseType = 'analyzing' | 'considering' | 'comparing' | 'concluding' | 'uncertain'

const PHASE_CONFIG: Record<PhaseType, { color: string; label: string }> = {
  analyzing:   { color: 'var(--color-phase-analyzing)',   label: 'ANALYZING' },
  considering: { color: 'var(--color-cost-green)',        label: 'CONSIDERING' },
  comparing:   { color: 'var(--color-warning-amber)',     label: 'COMPARING' },
  concluding:  { color: 'var(--color-accent)',            label: 'CONCLUDING' },
  uncertain:   { color: 'var(--color-text-muted)',        label: 'UNCERTAIN' },
}

function classifyPhase(text: string): PhaseType {
  const lower = text.toLowerCase()
  if (/\b(therefore|best approach|final|in conclusion|the answer)\b/.test(lower)) return 'concluding'
  if (/\b(compare|trade.?off|between|versus|pros.*cons)\b/.test(lower)) return 'comparing'
  if (/\b(option|alternatively|what if|could also|another approach)\b/.test(lower)) return 'considering'
  if (/\b(unsure|might|hmm|wait|not sure|uncertain)\b/.test(lower)) return 'uncertain'
  return 'analyzing'
}

// ── Flow diagram data (lifted from FlowDiagram.tsx) ────────────────────────

interface FlowNode {
  id: string
  label: string
  x: number
  y: number
  status: 'idle' | 'active' | 'complete'
  model?: string
  tokens?: number
}

const NODE_RADIUS = 24
const DEFAULT_FLOW = [
  { id: 'query', label: 'Query' },
  { id: 'route', label: 'Route' },
  { id: 'retrieve', label: 'Retrieve' },
  { id: 'reason', label: 'Reason' },
  { id: 'critique', label: 'Critique' },
  { id: 'respond', label: 'Respond' },
]

const STEP_COLORS: Record<string, string> = {
  idle:     'oklch(0.40 0.03 185)',
  active:   'var(--color-accent)',
  complete: 'var(--color-cost-green)',
}

// ── Timeline event colors ──────────────────────────────────────────────────

const EVENT_COLORS: Record<string, string> = {
  step_start:    'var(--color-phase-analyzing)',
  step_complete: 'var(--color-cost-green)',
  thinking:      'var(--color-phase-comparing)',
  model_switch:  'var(--color-warning-amber)',
  critique:      'var(--color-warning-amber)',
  branch:        'var(--color-accent)',
  consensus:     'var(--color-phase-concluding)',
  escalation:    'var(--color-error-red)',
}

// ── Thinking phase interface ───────────────────────────────────────────────

interface Phase {
  type: PhaseType
  label: string
  content: string
}

// ══════════════════════════════════════════════════════════════════════════════
//  ReasoningPanelLab — "Data-Science Laboratory" 3-Zone Layout
// ══════════════════════════════════════════════════════════════════════════════

export function ReasoningPanelLab() {
  const [viewMode, setViewMode] = createSignal<'parsed' | 'raw'>('parsed')
  let scrollRef: HTMLDivElement | undefined

  // ── Keyboard shortcut: Ctrl+Shift+R ────────────────────────────────────

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'R') {
      e.preventDefault()
      cycleReasoningPanel()
    }
  }

  onMount(() => document.addEventListener('keydown', handleKeyDown))
  onCleanup(() => document.removeEventListener('keydown', handleKeyDown))

  // ── Derived state ──────────────────────────────────────────────────────

  const currentPhase = createMemo<PhaseType>(() => {
    const thinking = chatState.streamingThinking
    if (!thinking) return 'analyzing'
    const blocks = thinking.split(/\n\n+/).filter(Boolean)
    if (blocks.length === 0) return 'analyzing'
    return classifyPhase(blocks[blocks.length - 1])
  })

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

  // ── Flow diagram memos ─────────────────────────────────────────────────

  const flowNodes = createMemo<FlowNode[]>(() => {
    const steps = chatState.reasoningSteps
    const streaming = chatState.isStreaming
    const meta = chatState.streamMeta

    const completedSteps = new Set(
      steps.filter((s) => s.event_type === 'step_complete').map((s) => s.step_name),
    )
    const activeSteps = new Set(
      steps
        .filter((s) => s.event_type === 'step_start' && !completedSteps.has(s.step_name))
        .map((s) => s.step_name),
    )

    return DEFAULT_FLOW.map((n, i) => {
      const x = 40 + i * 100
      const y = 60
      let status: FlowNode['status'] = 'idle'

      if (
        completedSteps.has(n.id) ||
        (n.id === 'query' && steps.length > 0) ||
        (n.id === 'respond' && !streaming && steps.length > 0)
      ) {
        status = 'complete'
      } else if (
        activeSteps.has(n.id) ||
        (n.id === 'route' && streaming && steps.length === 0)
      ) {
        status = 'active'
      }

      if (streaming && n.id === 'respond' && steps.length === 0) status = 'active'
      if (streaming) {
        if (n.id === 'query') status = 'complete'
        if (n.id === 'route') status = 'complete'
      }

      const stepData = steps.find(
        (s) => s.step_name === n.id && s.event_type === 'step_complete',
      )
      return {
        ...n,
        x,
        y,
        status,
        model: stepData?.model || (n.id === 'route' ? meta?.provider : undefined),
        tokens: (stepData?.metadata?.tokens as number) || undefined,
      }
    })
  })

  const flowEdges = createMemo(() => {
    const n = flowNodes()
    const result: Array<{ from: FlowNode; to: FlowNode; active: boolean }> = []
    for (let i = 0; i < n.length - 1; i++) {
      const from = n[i]
      const to = n[i + 1]
      result.push({ from, to, active: from.status !== 'idle' && to.status !== 'idle' })
    }
    return result
  })

  const hasFlowActivity = createMemo(() =>
    flowNodes().some((n) => n.status !== 'idle'),
  )

  // ── Conditional section memos ──────────────────────────────────────────

  const modelOutputs = createMemo(() =>
    chatState.reasoningSteps.filter(
      (s) => s.event_type === 'step_complete' && s.step_name.startsWith('model_'),
    ),
  )

  const consensusResult = createMemo(() =>
    chatState.reasoningSteps.find(
      (s) => s.event_type === 'consensus' && s.step_name === 'complete',
    ),
  )

  const timelineEvents = createMemo(() => {
    const startTime = chatState.reasoningSteps[0]?.timestamp || Date.now()
    return chatState.reasoningSteps.map((s) => ({
      type: s.event_type,
      name: s.step_name,
      model: s.model || undefined,
      content: s.content,
      tokens: (s.metadata?.tokens as number) || 0,
      confidence: (s.metadata?.confidence as number) || undefined,
      elapsed: s.timestamp - startTime,
    }))
  })

  const memoryEvents = createMemo(() =>
    chatState.reasoningSteps.filter(
      (s) =>
        s.step_name === 'retrieve' ||
        s.step_name === 'search' ||
        s.event_type === 'rag_retrieval',
    ),
  )

  // ── Telemetry ──────────────────────────────────────────────────────────

  const totalTokens = createMemo(() => {
    const u = chatState.lastUsage
    if (!u) return 0
    return u.tokens_in + u.tokens_out + (u.tokens_thinking || 0)
  })

  // ── Auto-scroll when streaming ─────────────────────────────────────────

  createEffect(() => {
    const _t = thinkingText()
    const _s = chatState.reasoningSteps.length
    if (chatState.isStreaming && scrollRef) {
      scrollRef.scrollTop = scrollRef.scrollHeight
    }
  })

  // ── Inline style helpers ───────────────────────────────────────────────

  const monoStyle = {
    'font-family': 'var(--font-mono)',
    'text-transform': 'uppercase' as const,
    'letter-spacing': '0.05em',
  }

  const sectionHeaderStyle = (color: string) => ({
    ...monoStyle,
    'font-size': '10px',
    'font-weight': '600',
    'border-left': `3px solid ${color}`,
    'padding-left': '8px',
    'padding-top': '4px',
    'padding-bottom': '4px',
    'margin-bottom': '8px',
    color: 'oklch(0.65 0.03 185)',
  })

  // ═══════════════════════════════════════════════════════════════════════
  //  RENDER
  // ═══════════════════════════════════════════════════════════════════════

  return (
    <div
      class="flex flex-col h-full"
      style={{ background: 'oklch(0.18 0.02 185)', color: 'var(--color-text-primary)' }}
    >
      {/* ── ZONE 1: Masthead (~48px fixed) ──────────────────────────────── */}
      <div
        class="flex items-center justify-between px-3 flex-shrink-0"
        style={{
          height: '48px',
          'border-bottom': '1px solid oklch(0.30 0.03 185)',
        }}
      >
        {/* Left cluster */}
        <div class="flex items-center gap-3 min-w-0">
          {/* Title */}
          <span
            style={{
              'font-family': 'var(--font-mono)',
              'font-size': '9px',
              'font-weight': '600',
              'text-transform': 'uppercase',
              'letter-spacing': '0.15em',
              color: 'oklch(0.65 0.03 185)',
            }}
          >
            EMILY REASONING LAB
          </span>

          {/* REC indicator */}
          <span class="flex items-center gap-1.5">
            <span
              class="w-2 h-2 rounded-full"
              classList={{
                'animate-rec-blink': chatState.isStreaming,
              }}
              style={{
                background: chatState.isStreaming
                  ? 'oklch(0.65 0.20 25)'
                  : 'oklch(0.40 0.03 185)',
              }}
            />
            <span
              style={{
                'font-family': 'var(--font-mono)',
                'font-size': '9px',
                'letter-spacing': '0.1em',
                color: chatState.isStreaming
                  ? 'oklch(0.65 0.20 25)'
                  : 'oklch(0.40 0.03 185)',
              }}
            >
              REC
            </span>
          </span>

          {/* SIG badge — current phase */}
          <span
            class="px-1.5 py-0.5 rounded"
            style={{
              'font-family': 'var(--font-mono)',
              'font-size': '9px',
              'letter-spacing': '0.05em',
              background: `color-mix(in oklch, ${PHASE_CONFIG[currentPhase()].color} 15%, transparent)`,
              color: PHASE_CONFIG[currentPhase()].color,
            }}
          >
            SIG: {PHASE_CONFIG[currentPhase()].label} (est.)
          </span>

          {/* Model badge */}
          <Show when={chatState.streamMeta}>
            {(meta) => (
              <span
                style={{
                  'font-family': 'var(--font-mono)',
                  'font-size': '9px',
                  color: 'oklch(0.50 0.04 185)',
                }}
              >
                {meta().display || meta().model_id}
                <Show when={meta().reasoning_strategy && meta().reasoning_strategy !== 'direct'}>
                  {' '}/ {meta().reasoning_strategy}
                </Show>
              </span>
            )}
          </Show>
        </div>

        {/* Right cluster: fullscreen toggle + close */}
        <div class="flex items-center gap-1">
          <button
            onClick={() =>
              setReasoningPanelSize(
                uiState.reasoningPanelSize === 'fullscreen' ? 'sidebar' : 'fullscreen',
              )
            }
            class="p-1 rounded transition-colors"
            style={{
              color: 'oklch(0.50 0.04 185)',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
            }}
            title={
              uiState.reasoningPanelSize === 'fullscreen'
                ? 'Exit fullscreen'
                : 'Fullscreen'
            }
          >
            {uiState.reasoningPanelSize === 'fullscreen' ? (
              <Minimize2 size={14} />
            ) : (
              <Maximize2 size={14} />
            )}
          </button>
          <button
            onClick={() => setReasoningPanelSize('hidden')}
            class="p-1 rounded transition-colors"
            style={{
              color: 'oklch(0.50 0.04 185)',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
            }}
            title="Close panel"
          >
            <PanelRightClose size={14} />
          </button>
        </div>
      </div>

      {/* ── ZONE 2: Signal + Content (scrollable flex-grow) ─────────────── */}
      <div ref={scrollRef} class="flex-1 min-h-0 overflow-y-auto">
        {/* ── Sub-area 2a: Flow Diagram (instrument styled) ────────────── */}
        <div
          class="lab-grid-bg"
          style={{
            'border-bottom': '1px solid oklch(0.25 0.02 185)',
            padding: '12px 16px',
          }}
        >
          <Show
            when={hasFlowActivity()}
            fallback={
              <div class="flex items-center justify-center" style={{ height: '80px' }}>
                <svg viewBox="0 0 400 40" class="w-full" style={{ 'max-width': '400px' }}>
                  <line
                    x1="0" y1="20" x2="400" y2="20"
                    stroke="oklch(0.30 0.03 185)" stroke-width="1"
                  />
                  <text
                    x="200" y="20" text-anchor="middle" dominant-baseline="middle"
                    font-size="10"
                    font-family="var(--font-mono)"
                    fill="oklch(0.40 0.03 185)"
                    letter-spacing="0.15em"
                  >
                    NO SIGNAL
                  </text>
                </svg>
              </div>
            }
          >
            <svg
              viewBox="0 0 640 120"
              class="w-full"
              style={{ 'max-height': '120px', 'max-width': '640px', margin: '0 auto', display: 'block' }}
            >
              <defs>
                <marker
                  id="lab-arrow"
                  viewBox="0 0 10 7"
                  refX="9"
                  refY="3.5"
                  markerWidth="8"
                  markerHeight="6"
                  orient="auto"
                >
                  <polygon
                    points="0 0, 10 3.5, 0 7"
                    fill="oklch(0.40 0.03 185)"
                  />
                </marker>
                <marker
                  id="lab-arrow-active"
                  viewBox="0 0 10 7"
                  refX="9"
                  refY="3.5"
                  markerWidth="8"
                  markerHeight="6"
                  orient="auto"
                >
                  <polygon
                    points="0 0, 10 3.5, 0 7"
                    fill="var(--color-accent)"
                  />
                </marker>
              </defs>

              {/* Edges */}
              <For each={flowEdges()}>
                {(edge) => (
                  <line
                    x1={edge.from.x + NODE_RADIUS + 4}
                    y1={edge.from.y}
                    x2={edge.to.x - NODE_RADIUS - 4}
                    y2={edge.to.y}
                    stroke={
                      edge.active
                        ? 'var(--color-accent)'
                        : 'oklch(0.30 0.03 185)'
                    }
                    stroke-width={edge.active ? 1.5 : 1}
                    marker-end={
                      edge.active
                        ? 'url(#lab-arrow-active)'
                        : 'url(#lab-arrow)'
                    }
                    opacity={edge.active ? 1 : 0.4}
                  />
                )}
              </For>

              {/* Nodes — ring style (stroke-only) */}
              <For each={flowNodes()}>
                {(node) => (
                  <g>
                    {/* Active pulse ring */}
                    <Show when={node.status === 'active'}>
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={NODE_RADIUS + 4}
                        fill="none"
                        stroke={STEP_COLORS.active}
                        stroke-width={1}
                        opacity={0.5}
                      >
                        <animate
                          attributeName="r"
                          from={NODE_RADIUS + 2}
                          to={NODE_RADIUS + 12}
                          dur="1.2s"
                          repeatCount="indefinite"
                        />
                        <animate
                          attributeName="opacity"
                          from="0.6"
                          to="0"
                          dur="1.2s"
                          repeatCount="indefinite"
                        />
                      </circle>
                    </Show>

                    {/* Ring node (stroke-only, not filled) */}
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={NODE_RADIUS}
                      fill="none"
                      stroke={STEP_COLORS[node.status]}
                      stroke-width={node.status === 'idle' ? 1 : 2}
                      opacity={node.status === 'idle' ? 0.4 : 1}
                    />

                    <text
                      x={node.x}
                      y={node.y + 1}
                      text-anchor="middle"
                      dominant-baseline="middle"
                      font-size="8"
                      font-family="var(--font-mono)"
                      fill={
                        node.status === 'idle'
                          ? 'oklch(0.45 0.03 185)'
                          : STEP_COLORS[node.status]
                      }
                      font-weight={node.status !== 'idle' ? 600 : 400}
                      letter-spacing="0.05em"
                    >
                      {node.label.toUpperCase()}
                    </text>

                    <Show when={node.model}>
                      <text
                        x={node.x}
                        y={node.y + NODE_RADIUS + 12}
                        text-anchor="middle"
                        font-size="7"
                        font-family="var(--font-mono)"
                        fill="oklch(0.45 0.03 185)"
                      >
                        {node.model}
                      </text>
                    </Show>

                    <Show when={node.tokens}>
                      <text
                        x={node.x}
                        y={node.y + NODE_RADIUS + 22}
                        text-anchor="middle"
                        font-size="7"
                        font-family="var(--font-mono)"
                        fill="oklch(0.45 0.03 185)"
                      >
                        {node.tokens} tok
                      </text>
                    </Show>
                  </g>
                )}
              </For>
            </svg>
          </Show>
        </div>

        {/* ── Sub-area 2b: Thinking Content (readable) ─────────────────── */}
        <div style={{ padding: '12px 16px' }}>
          <Show
            when={thinkingText()}
            fallback={
              <div
                class="flex items-center justify-center"
                style={{
                  height: '80px',
                  'font-family': 'var(--font-mono)',
                  'font-size': '10px',
                  'letter-spacing': '0.15em',
                  'text-transform': 'uppercase',
                  color: 'var(--color-text-muted)',
                }}
              >
                NO COGNITIVE TRACE
              </div>
            }
          >
            {/* Header row with count + Raw/Parsed toggle */}
            <div
              class="flex items-center justify-between mb-2"
              style={{ 'border-bottom': '1px solid oklch(0.25 0.02 185)', 'padding-bottom': '6px' }}
            >
              <span
                style={{
                  'font-family': 'var(--font-mono)',
                  'font-size': '10px',
                  'text-transform': 'uppercase',
                  'letter-spacing': '0.05em',
                  color: 'oklch(0.50 0.04 185)',
                }}
              >
                {phases().length} phases
              </span>
              <div class="flex gap-1">
                <button
                  onClick={() => setViewMode('parsed')}
                  class="px-2 py-0.5 rounded"
                  style={{
                    'font-family': 'var(--font-mono)',
                    'font-size': '9px',
                    'text-transform': 'uppercase',
                    'letter-spacing': '0.05em',
                    border: 'none',
                    cursor: 'pointer',
                    background:
                      viewMode() === 'parsed'
                        ? 'oklch(0.72 0.17 162 / 0.15)'
                        : 'transparent',
                    color:
                      viewMode() === 'parsed'
                        ? 'var(--color-accent)'
                        : 'oklch(0.45 0.03 185)',
                  }}
                >
                  Parsed
                </button>
                <button
                  onClick={() => setViewMode('raw')}
                  class="px-2 py-0.5 rounded"
                  style={{
                    'font-family': 'var(--font-mono)',
                    'font-size': '9px',
                    'text-transform': 'uppercase',
                    'letter-spacing': '0.05em',
                    border: 'none',
                    cursor: 'pointer',
                    background:
                      viewMode() === 'raw'
                        ? 'oklch(0.72 0.17 162 / 0.15)'
                        : 'transparent',
                    color:
                      viewMode() === 'raw'
                        ? 'var(--color-accent)'
                        : 'oklch(0.45 0.03 185)',
                  }}
                >
                  Raw
                </button>
              </div>
            </div>

            {/* Phase content */}
            <Show
              when={viewMode() === 'parsed'}
              fallback={
                <pre
                  class="text-xs whitespace-pre-wrap leading-relaxed"
                  style={{
                    'font-family': 'var(--font-mono)',
                    color: 'var(--color-text-secondary)',
                  }}
                >
                  {thinkingText()}
                  <Show when={chatState.isStreaming}>
                    <span
                      class="inline-block w-1.5 h-3.5 animate-pulse ml-0.5"
                      style={{ background: 'var(--color-accent)' }}
                    />
                  </Show>
                </pre>
              }
            >
              <For each={phases()}>
                {(phase) => {
                  const config = () => PHASE_CONFIG[phase.type]
                  return (
                    <div
                      class="mb-2"
                      style={{ 'border-left': `2px solid ${config().color}` }}
                    >
                      <div class="flex items-center gap-2 px-3 py-1">
                        {/* 8x8 colored square */}
                        <span
                          class="flex-shrink-0"
                          style={{
                            width: '8px',
                            height: '8px',
                            background: config().color,
                          }}
                        />
                        <span
                          style={{
                            'font-family': 'var(--font-mono)',
                            'font-size': '10px',
                            'font-weight': '600',
                            'text-transform': 'uppercase',
                            'letter-spacing': '0.05em',
                            color: config().color,
                          }}
                        >
                          {config().label}
                        </span>
                      </div>
                      <div
                        class="px-4 pb-2 text-xs leading-relaxed whitespace-pre-wrap"
                        style={{
                          'font-family': 'var(--font-body)',
                          color: 'var(--color-text-secondary)',
                        }}
                      >
                        {phase.content}
                      </div>
                    </div>
                  )
                }}
              </For>
              <Show when={chatState.isStreaming}>
                <span
                  class="inline-block w-1.5 h-3.5 animate-pulse ml-4"
                  style={{ background: 'var(--color-accent)' }}
                />
              </Show>
            </Show>
          </Show>
        </div>

        {/* ── Conditional: MODEL CONSENSUS ──────────────────────────────── */}
        <Show when={modelOutputs().length > 0}>
          <div style={{ padding: '0 16px 12px' }}>
            <div style={sectionHeaderStyle('var(--color-accent)')}>
              MODEL CONSENSUS
            </div>
            <div
              class="grid gap-3"
              style={{
                'grid-template-columns': `repeat(${Math.min(modelOutputs().length, 3)}, 1fr)`,
              }}
            >
              <For each={modelOutputs()}>
                {(output, i) => (
                  <div
                    class="rounded overflow-hidden"
                    style={{ border: '1px solid oklch(0.28 0.03 185)' }}
                  >
                    <div
                      class="px-3 py-1.5 flex items-center justify-between"
                      style={{
                        background: 'oklch(0.22 0.025 185)',
                        'border-bottom': '1px solid oklch(0.28 0.03 185)',
                      }}
                    >
                      <span
                        style={{
                          ...monoStyle,
                          'font-size': '10px',
                          color: 'var(--color-text-primary)',
                        }}
                      >
                        {output.model || `MODEL ${i() + 1}`}
                      </span>
                      <Show when={output.metadata?.tokens}>
                        <span
                          style={{
                            'font-family': 'var(--font-mono)',
                            'font-size': '9px',
                            color: 'oklch(0.45 0.03 185)',
                          }}
                        >
                          {output.metadata.tokens as number} tok
                        </span>
                      </Show>
                    </div>
                    <div
                      class="p-3 text-xs leading-relaxed whitespace-pre-wrap overflow-y-auto"
                      style={{
                        'font-family': 'var(--font-body)',
                        color: 'var(--color-text-secondary)',
                        'max-height': '300px',
                      }}
                    >
                      {output.content}
                    </div>
                  </div>
                )}
              </For>
            </div>

            <Show when={consensusResult()}>
              {(result) => (
                <div
                  class="rounded overflow-hidden mt-3"
                  style={{ border: '1px solid oklch(0.72 0.17 162 / 0.3)' }}
                >
                  <div
                    class="px-3 py-1.5"
                    style={{
                      background: 'oklch(0.72 0.17 162 / 0.08)',
                      'border-bottom': '1px solid oklch(0.72 0.17 162 / 0.2)',
                    }}
                  >
                    <span
                      style={{
                        ...monoStyle,
                        'font-size': '10px',
                        color: 'var(--color-accent)',
                      }}
                    >
                      CONSENSUS SYNTHESIS
                    </span>
                  </div>
                  <div
                    class="p-3 text-xs leading-relaxed whitespace-pre-wrap"
                    style={{
                      'font-family': 'var(--font-body)',
                      color: 'var(--color-text-secondary)',
                    }}
                  >
                    {result().content}
                  </div>
                </div>
              )}
            </Show>
          </div>
        </Show>

        {/* ── Conditional: EVENT TIMELINE ───────────────────────────────── */}
        <Show when={chatState.reasoningSteps.length > 0}>
          <div style={{ padding: '0 16px 12px' }}>
            <div style={sectionHeaderStyle('var(--color-phase-analyzing)')}>
              EVENT TIMELINE
            </div>
            <div class="relative" style={{ 'padding-left': '20px' }}>
              {/* Vertical line */}
              <div
                class="absolute top-0 bottom-0"
                style={{
                  left: '6px',
                  width: '1px',
                  background: 'oklch(0.28 0.03 185)',
                }}
              />

              <For each={timelineEvents()}>
                {(event) => {
                  const color = () =>
                    EVENT_COLORS[event.type] || 'var(--color-text-muted)'
                  return (
                    <div class="relative mb-2 last:mb-0">
                      <div
                        class="absolute w-2 h-2 rounded-full"
                        style={{
                          left: '-16px',
                          top: '4px',
                          border: `1.5px solid ${color()}`,
                          background: 'oklch(0.18 0.02 185)',
                        }}
                      />
                      <div class="flex items-center gap-2 mb-0.5 flex-wrap">
                        <span
                          class="px-1 py-0.5 rounded"
                          style={{
                            'font-family': 'var(--font-mono)',
                            'font-size': '9px',
                            'text-transform': 'uppercase',
                            'letter-spacing': '0.03em',
                            background: `color-mix(in oklch, ${color()} 12%, transparent)`,
                            color: color(),
                          }}
                        >
                          {event.type.replace(/_/g, ' ')}
                        </span>
                        <span
                          style={{
                            'font-family': 'var(--font-mono)',
                            'font-size': '9px',
                            color: 'oklch(0.50 0.04 185)',
                          }}
                        >
                          {event.name}
                        </span>
                        <Show when={event.model}>
                          <span
                            style={{
                              'font-family': 'var(--font-mono)',
                              'font-size': '9px',
                              color: 'oklch(0.40 0.03 185)',
                            }}
                          >
                            {event.model}
                          </span>
                        </Show>
                        <span
                          class="ml-auto"
                          style={{
                            'font-family': 'var(--font-mono)',
                            'font-size': '9px',
                            color: 'oklch(0.40 0.03 185)',
                          }}
                        >
                          +{event.elapsed}ms
                        </span>
                      </div>
                      <Show when={event.content}>
                        <p
                          class="text-xs leading-relaxed line-clamp-2"
                          style={{
                            'font-family': 'var(--font-body)',
                            color: 'var(--color-text-secondary)',
                          }}
                        >
                          {event.content}
                        </p>
                      </Show>
                      <div class="flex items-center gap-2 mt-0.5">
                        <Show when={event.tokens > 0}>
                          <span
                            style={{
                              'font-family': 'var(--font-mono)',
                              'font-size': '9px',
                              color: 'oklch(0.45 0.03 185)',
                            }}
                          >
                            {event.tokens} tok
                          </span>
                        </Show>
                        <Show when={event.confidence !== undefined}>
                          <span
                            style={{
                              'font-family': 'var(--font-mono)',
                              'font-size': '9px',
                              color:
                                event.confidence! >= 0.7
                                  ? 'var(--color-cost-green)'
                                  : event.confidence! >= 0.4
                                    ? 'var(--color-warning-amber)'
                                    : 'var(--color-error-red)',
                            }}
                          >
                            conf: {(event.confidence! * 100).toFixed(0)}%
                          </span>
                        </Show>
                      </div>
                    </div>
                  )
                }}
              </For>

              <Show when={chatState.isStreaming}>
                <div class="relative mb-0">
                  <div
                    class="absolute w-2 h-2 rounded-full animate-pulse"
                    style={{
                      left: '-16px',
                      top: '4px',
                      background: 'var(--color-accent)',
                    }}
                  />
                  <span
                    style={{
                      'font-family': 'var(--font-mono)',
                      'font-size': '9px',
                      color: 'var(--color-accent)',
                      'text-transform': 'uppercase',
                    }}
                  >
                    Processing...
                  </span>
                </div>
              </Show>
            </div>
          </div>
        </Show>

        {/* ── Conditional: MEMORY RETRIEVAL ─────────────────────────────── */}
        <Show when={memoryEvents().length > 0}>
          <div style={{ padding: '0 16px 12px' }}>
            <div style={sectionHeaderStyle('var(--color-specimen-blue)')}>
              MEMORY RETRIEVAL
            </div>
            <div class="space-y-2">
              <For each={memoryEvents()}>
                {(event) => (
                  <div
                    class="rounded p-3"
                    style={{ border: '1px solid oklch(0.28 0.03 185)' }}
                  >
                    <div class="flex items-center gap-2 mb-1">
                      <span
                        style={{
                          ...monoStyle,
                          'font-size': '10px',
                          color: 'var(--color-text-primary)',
                        }}
                      >
                        {event.step_name.toUpperCase()}
                      </span>
                      <Show when={event.model}>
                        <span
                          style={{
                            'font-family': 'var(--font-mono)',
                            'font-size': '9px',
                            color: 'oklch(0.45 0.03 185)',
                          }}
                        >
                          {event.model}
                        </span>
                      </Show>
                    </div>
                    <Show when={event.content}>
                      <div
                        class="text-xs leading-relaxed whitespace-pre-wrap"
                        style={{
                          'font-family': 'var(--font-body)',
                          color: 'var(--color-text-secondary)',
                        }}
                      >
                        {event.content}
                      </div>
                    </Show>
                    <Show when={event.metadata?.relevance_scores}>
                      <div class="mt-2 flex gap-1 flex-wrap">
                        <For each={event.metadata.relevance_scores as number[]}>
                          {(score) => (
                            <span
                              class="px-1.5 py-0.5 rounded"
                              style={{
                                'font-family': 'var(--font-mono)',
                                'font-size': '9px',
                                background: 'oklch(0.22 0.025 185)',
                                color:
                                  score >= 0.7
                                    ? 'var(--color-cost-green)'
                                    : score >= 0.4
                                      ? 'var(--color-warning-amber)'
                                      : 'var(--color-text-muted)',
                              }}
                            >
                              {(score * 100).toFixed(0)}%
                            </span>
                          )}
                        </For>
                      </div>
                    </Show>
                  </div>
                )}
              </For>
            </div>
          </div>
        </Show>
      </div>

      {/* ── ZONE 3: Telemetry Strip (~36px fixed bottom) ────────────────── */}
      <div
        class="flex items-center px-3 flex-shrink-0"
        style={{
          height: '36px',
          'border-top': '1px solid oklch(0.28 0.03 185)',
          background: 'oklch(0.16 0.02 185)',
        }}
      >
        <Show
          when={chatState.lastUsage}
          fallback={
            <span
              style={{
                'font-family': 'var(--font-mono)',
                'font-size': '10px',
                'text-transform': 'uppercase',
                'letter-spacing': '0.1em',
                color: 'var(--color-text-muted)',
              }}
            >
              AWAITING TELEMETRY
            </span>
          }
        >
          {(usage) => (
            <div
              class="flex items-center gap-0 tabular-nums"
              style={{
                'font-family': 'var(--font-mono)',
                'font-size': '10px',
                'text-transform': 'uppercase',
                'letter-spacing': '0.03em',
                color: 'oklch(0.55 0.04 185)',
              }}
            >
              <span>LAT: {usage().latency_ms}ms</span>
              <span style={{ margin: '0 6px', opacity: 0.4 }}>|</span>
              <span>TOK: {totalTokens()}</span>
              <Show when={usage().cost_usd > 0}>
                <span style={{ margin: '0 6px', opacity: 0.4 }}>|</span>
                <span>COST: ${usage().cost_usd.toFixed(4)}</span>
              </Show>
              <Show when={chatState.reasoningSteps.length > 0}>
                <span style={{ margin: '0 6px', opacity: 0.4 }}>|</span>
                <span>STEPS: {chatState.reasoningSteps.length}</span>
              </Show>
              <Show when={chatState.isStreaming}>
                <span style={{ margin: '0 6px', opacity: 0.4 }}>|</span>
                <span class="flex items-center gap-1.5">
                  <span
                    class="w-1.5 h-1.5 rounded-full animate-rec-blink"
                    style={{ background: 'var(--color-accent)' }}
                  />
                  ACTIVE
                </span>
              </Show>
            </div>
          )}
        </Show>
      </div>
    </div>
  )
}
