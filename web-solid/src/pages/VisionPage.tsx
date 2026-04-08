import { createSignal, createEffect, createMemo, onMount, onCleanup, For, Show, type Component } from 'solid-js'
import { API_RAW } from '../lib/env'
import {
  Eye, Monitor, Camera, Cpu, Scan, RefreshCw, AlertCircle,
  User, Activity, Zap, Clock, ChevronRight, Maximize2,
} from 'lucide-solid'

const API = API_RAW

// ── Types ───────────────────────────────────────────────────────────────────

interface VisionStatus {
  initialized: boolean
  screen_available: boolean
  webcam_available: boolean
  analyzer_model: string
  last_analysis_ts: number
}

interface Observations {
  screen: {
    active_app?: string
    content_type?: string
    summary?: string
    text_content?: string
  } | null
  presence: {
    state: string
    face_detected: boolean
    system_idle_s: number
    confidence: number
  } | null
  emotions: {
    primary_emotion?: string
    confidence?: number
    all_emotions?: Record<string, number>
  } | null
  ocr_text: string | null
  last_analysis_ts: number
}

// ── Presence color map ──────────────────────────────────────────────────────

const PRESENCE_COLOR: Record<string, string> = {
  PRESENT: 'var(--color-success)',
  IDLE:    'var(--color-warning)',
  AWAY:    'var(--color-error)',
  UNKNOWN: 'var(--color-text-muted)',
}

// ── Sub-components ──────────────────────────────────────────────────────────

function StatusDot(props: { active: boolean; label: string }) {
  return (
    <div class="flex items-center gap-1.5">
      <div
        class="w-2 h-2 rounded-full"
        style={{
          'background-color': props.active ? 'var(--color-success)' : 'var(--color-error)',
          'box-shadow': props.active ? '0 0 6px color-mix(in oklch, var(--color-success) 50%, transparent)' : 'none',
        }}
      />
      <span class="text-[10px] font-mono uppercase tracking-wider text-text-muted">
        {props.label}
      </span>
    </div>
  )
}

function HudFrame(props: {
  children: any
  label: string
  live?: boolean
  class?: string
  onMaximize?: () => void
}) {
  return (
    <div class={`relative group ${props.class ?? ''}`}>
      <div class="relative overflow-hidden rounded-xl border border-border bg-surface-raised">
        {/* Corner brackets */}
        <div class="absolute top-0 left-0 w-5 h-5 border-t-2 border-l-2 border-accent/30 rounded-tl animate-bracket-pulse" />
        <div class="absolute top-0 right-0 w-5 h-5 border-t-2 border-r-2 border-accent/30 rounded-tr animate-bracket-pulse" />
        <div class="absolute bottom-0 left-0 w-5 h-5 border-b-2 border-l-2 border-accent/30 rounded-bl animate-bracket-pulse" />
        <div class="absolute bottom-0 right-0 w-5 h-5 border-b-2 border-r-2 border-accent/30 rounded-br animate-bracket-pulse" />

        {/* Scan line */}
        <div class="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-accent/25 to-transparent animate-scan-line pointer-events-none" />

        {/* Header bar */}
        <div class="flex items-center justify-between px-3 py-1.5 border-b border-border bg-accent/[0.03]">
          <div class="flex items-center gap-2">
            <span class="text-[10px] font-mono uppercase tracking-widest text-text-muted">
              {props.label}
            </span>
            <Show when={props.live}>
              <div class="flex items-center gap-1">
                <div class="w-1.5 h-1.5 rounded-full bg-error animate-live-pulse" />
                <span class="text-[9px] font-mono text-error/80">LIVE</span>
              </div>
            </Show>
          </div>
          <Show when={props.onMaximize}>
            <button
              onClick={props.onMaximize}
              class="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:bg-surface-hover rounded"
            >
              <Maximize2 class="w-3 h-3 text-text-muted" />
            </button>
          </Show>
        </div>

        {/* Content */}
        {props.children}
      </div>
    </div>
  )
}

function VisionMetricCard(props: {
  icon: Component<{ class?: string; style?: Record<string, string> }>
  label: string
  value: string
  color?: string
}) {
  const Icon = props.icon
  return (
    <div class="flex items-center gap-2.5 px-3 py-2 rounded-lg border border-border bg-surface-raised">
      <Icon class="w-4 h-4 flex-shrink-0" style={{ color: props.color ?? 'var(--color-accent)' }} />
      <div class="min-w-0">
        <div class="text-[10px] font-mono uppercase tracking-wider text-text-muted">{props.label}</div>
        <div class="text-sm font-medium text-text-primary truncate">{props.value}</div>
      </div>
    </div>
  )
}

function EmotionBar(props: { emotion: string; confidence: number }) {
  return (
    <div class="flex items-center gap-2">
      <span class="text-[10px] font-mono text-text-muted w-16 truncate">{props.emotion}</span>
      <div class="flex-1 h-1.5 bg-surface rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.round(props.confidence * 100)}%`,
            background: 'linear-gradient(90deg, var(--color-accent), var(--color-phase-comparing))',
          }}
        />
      </div>
      <span class="text-[10px] font-mono text-text-muted w-8 text-right">
        {Math.round(props.confidence * 100)}%
      </span>
    </div>
  )
}

function PresenceRing(props: { state: string; confidence: number }) {
  const color = () => PRESENCE_COLOR[props.state] ?? PRESENCE_COLOR.UNKNOWN
  const radius = 32
  const circumference = 2 * Math.PI * radius
  const dashoffset = () => circumference * (1 - props.confidence)

  return (
    <div class="flex flex-col items-center gap-1.5">
      <div class="relative w-20 h-20">
        <svg viewBox="0 0 80 80" class="w-full h-full -rotate-90">
          <circle cx="40" cy="40" r={radius} fill="none" stroke="var(--color-border)" stroke-opacity="0.5" stroke-width="3" />
          <circle
            cx="40" cy="40" r={radius}
            fill="none"
            stroke={color()}
            stroke-width="3"
            stroke-linecap="round"
            stroke-dasharray={circumference}
            stroke-dashoffset={dashoffset()}
            style={{ transition: 'stroke-dashoffset 0.5s ease' }}
          />
        </svg>
        <div class="absolute inset-0 flex items-center justify-center">
          <User class="w-5 h-5" style={{ color: color() }} />
        </div>
      </div>
      <span class="text-xs font-mono font-medium" style={{ color: color() }}>{props.state}</span>
      <span class="text-[10px] text-text-muted">{Math.round(props.confidence * 100)}% conf</span>
    </div>
  )
}

// ── Expanded image modal ────────────────────────────────────────────────────

function ImageModal(props: { src: string; alt: string; onClose: () => void }) {
  return (
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-scale-in"
      onClick={props.onClose}
    >
      <div class="relative max-w-[90vw] max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
        <img src={props.src} alt={props.alt} class="max-w-full max-h-[85vh] rounded-xl border border-accent/20" />
        <button
          onClick={props.onClose}
          class="absolute top-2 right-2 px-2 py-1 rounded bg-surface/80 text-xs font-mono text-text-secondary hover:bg-surface"
        >
          ESC
        </button>
      </div>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────

export function VisionPage() {
  const [status, setStatus] = createSignal<VisionStatus | null>(null)
  const [obs, setObs] = createSignal<Observations | null>(null)
  const [tick, setTick] = createSignal(0)
  const [analyzing, setAnalyzing] = createSignal(false)
  const [expanded, setExpanded] = createSignal<'screen' | 'webcam' | null>(null)
  const [error, setError] = createSignal<string | null>(null)
  let screenRef: HTMLImageElement | undefined
  let webcamRef: HTMLImageElement | undefined

  // Poll status once on mount
  onMount(() => {
    fetch(`${API}/vision/status`)
      .then((r) => r.json())
      .then((d) => setStatus(d))
      .catch((e: Error) => setError(`Vision API unreachable: ${e.message}`))
  })

  // Refresh feeds every 3s
  onMount(() => {
    const id = setInterval(() => setTick((t) => t + 1), 3000)
    onCleanup(() => clearInterval(id))
  })

  // Poll observations every 3s
  onMount(() => {
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API}/vision/observations`)
        if (res.ok) {
          setObs(await res.json())
          setError(null)
        }
      } catch { /* retry silently */ }
    }, 3000)
    onCleanup(() => clearInterval(poll))
  })

  // Escape closes modal
  onMount(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(null)
    }
    window.addEventListener('keydown', handler)
    onCleanup(() => window.removeEventListener('keydown', handler))
  })

  const triggerAnalysis = async () => {
    setAnalyzing(true)
    try {
      const res = await fetch(`${API}/vision/analyze`, { method: 'POST' })
      if (res.ok) {
        setObs(await res.json())
        setError(null)
      } else {
        const data = await res.json().catch(() => ({ detail: 'Analysis failed' }))
        setError(data.detail || 'Analysis failed')
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setAnalyzing(false)
    }
  }

  const presenceState = () => obs()?.presence?.state ?? 'UNKNOWN'
  const presenceColor = () => PRESENCE_COLOR[presenceState()] ?? PRESENCE_COLOR.UNKNOWN
  const lastAnalysisAge = () => {
    const ts = obs()?.last_analysis_ts
    return ts ? Math.round((Date.now() / 1000) - ts) : null
  }

  const screenSrc = () => `${API}/vision/screenshot?t=${tick()}`
  const webcamSrc = () => `${API}/vision/webcam?t=${tick()}`

  const emotionEntries = createMemo(() => {
    const all = obs()?.emotions?.all_emotions
    if (!all) return []
    return Object.entries(all)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)
  })

  return (
    <div class="flex flex-1 flex-col min-h-0 overflow-y-auto bg-surface">
      {/* Expanded image modal */}
      <Show when={expanded()}>
        <ImageModal
          src={expanded() === 'screen' ? screenSrc() : webcamSrc()}
          alt={expanded() === 'screen' ? 'Screen capture' : 'Camera feed'}
          onClose={() => setExpanded(null)}
        />
      </Show>

      {/* Status bar */}
      <div class="flex items-center justify-between px-5 py-2.5 border-b border-border bg-surface-raised flex-shrink-0">
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <Eye class="w-4 h-4 text-accent" />
            <span class="text-xs font-mono font-semibold text-accent tracking-wide">
              PERCEPTION HUD
            </span>
          </div>
          <div class="w-px h-4 bg-border" />
          <StatusDot active={status()?.initialized ?? false} label="Pipeline" />
          <StatusDot active={status()?.screen_available ?? false} label="Screen" />
          <StatusDot active={status()?.webcam_available ?? false} label="Camera" />
        </div>

        <div class="flex items-center gap-3">
          <Show when={status()?.analyzer_model}>
            <div class="flex items-center gap-1.5 text-[10px] font-mono text-text-muted">
              <Cpu class="w-3 h-3" />
              {status()!.analyzer_model}
            </div>
          </Show>
          <Show when={lastAnalysisAge() !== null}>
            <div class="flex items-center gap-1 text-[10px] font-mono text-text-muted">
              <Clock class="w-3 h-3" />
              {lastAnalysisAge()}s ago
            </div>
          </Show>
          <button
            onClick={() => void triggerAnalysis()}
            disabled={analyzing()}
            class="flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-mono
              bg-accent/10 text-accent border border-accent/20
              hover:bg-accent/20 hover:border-accent/30
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-all"
          >
            <RefreshCw class={`w-3 h-3 ${analyzing() ? 'animate-spin' : ''}`} />
            {analyzing() ? 'ANALYZING...' : 'ANALYZE NOW'}
          </button>
        </div>
      </div>

      {/* Error banner */}
      <Show when={error()}>
        <div class="mx-5 mt-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-error/10 border border-error/20 text-error text-xs font-mono">
          <AlertCircle class="w-3.5 h-3.5 flex-shrink-0" />
          {error()}
        </div>
      </Show>

      {/* Main grid */}
      <div class="flex-1 p-5 grid grid-cols-[1fr_1fr] grid-rows-[auto_1fr] gap-4 min-h-0">
        {/* Screen capture feed */}
        <HudFrame
          label="Screen Capture"
          live={status()?.screen_available}
          onMaximize={() => setExpanded('screen')}
        >
          <div class="relative aspect-video bg-surface">
            <Show when={status()?.screen_available} fallback={
              <div class="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <Monitor class="w-8 h-8 text-text-muted opacity-40" />
                <span class="text-xs font-mono text-text-muted">NO SIGNAL</span>
              </div>
            }>
              <img
                ref={screenRef}
                src={screenSrc()}
                alt="Screen capture"
                class="w-full h-full object-contain"
                onError={() => { if (screenRef) screenRef.style.display = 'none' }}
                onLoad={() => { if (screenRef) screenRef.style.display = 'block' }}
              />
            </Show>
            <Show when={obs()?.screen?.active_app}>
              <div class="absolute bottom-2 left-2 flex items-center gap-1.5 px-2 py-1 rounded bg-surface/80 backdrop-blur-sm border border-accent/20">
                <Scan class="w-3 h-3 text-accent" />
                <span class="text-[10px] font-mono text-accent">{obs()!.screen!.active_app}</span>
              </div>
            </Show>
            <Show when={obs()?.screen?.content_type}>
              <div class="absolute bottom-2 right-2 px-2 py-1 rounded bg-surface/80 backdrop-blur-sm border border-phase-comparing/30">
                <span class="text-[10px] font-mono text-text-secondary">{obs()!.screen!.content_type}</span>
              </div>
            </Show>
          </div>
        </HudFrame>

        {/* Webcam feed + presence/emotion sidebar */}
        <HudFrame
          label="Camera Feed"
          live={status()?.webcam_available}
          onMaximize={() => setExpanded('webcam')}
        >
          <div class="flex">
            <div class="relative flex-1 aspect-video bg-surface">
              <Show when={status()?.webcam_available} fallback={
                <div class="absolute inset-0 flex flex-col items-center justify-center gap-2">
                  <Camera class="w-8 h-8 text-text-muted opacity-40" />
                  <span class="text-xs font-mono text-text-muted">NO SIGNAL</span>
                </div>
              }>
                <img
                  ref={webcamRef}
                  src={webcamSrc()}
                  alt="Camera feed"
                  class="w-full h-full object-contain"
                  onError={() => { if (webcamRef) webcamRef.style.display = 'none' }}
                  onLoad={() => { if (webcamRef) webcamRef.style.display = 'block' }}
                />
              </Show>
              <Show when={obs()?.presence}>
                <div
                  class="absolute top-2 right-2 flex items-center gap-1.5 px-2 py-1 rounded-full bg-surface/80 backdrop-blur-sm"
                  style={{ border: `1px solid ${presenceColor()}` }}
                >
                  <div class="w-2 h-2 rounded-full" style={{ 'background-color': presenceColor() }} />
                  <span class="text-[10px] font-mono font-medium" style={{ color: presenceColor() }}>
                    {presenceState()}
                  </span>
                </div>
              </Show>
              <Show when={obs()?.presence?.face_detected}>
                <div class="absolute top-2 left-2 px-2 py-1 rounded bg-success/10 border border-success/20">
                  <span class="text-[10px] font-mono text-success">FACE DETECTED</span>
                </div>
              </Show>
            </div>

            {/* Sidebar: presence ring + emotion bars */}
            <div class="w-36 border-l border-border p-3 flex flex-col items-center gap-3 bg-surface">
              <Show when={obs()?.presence} fallback={
                <div class="flex flex-col items-center gap-1 py-3">
                  <User class="w-5 h-5 text-text-muted opacity-40" />
                  <span class="text-[10px] font-mono text-text-muted">OFFLINE</span>
                </div>
              }>
                <PresenceRing state={presenceState()} confidence={obs()!.presence!.confidence} />
              </Show>

              {/* Emotion bars */}
              <Show when={emotionEntries().length > 0}>
                <div class="w-full space-y-1.5 mt-1">
                  <div class="text-[9px] font-mono uppercase tracking-wider text-text-muted mb-1">
                    Emotions
                  </div>
                  <For each={emotionEntries()}>{([emotion, confidence]) => (
                    <EmotionBar emotion={emotion} confidence={confidence} />
                  )}</For>
                </div>
              </Show>

              {/* Primary emotion (fallback when no all_emotions) */}
              <Show when={obs()?.emotions?.primary_emotion && !obs()?.emotions?.all_emotions}>
                <div class="text-center mt-1">
                  <div class="text-[9px] font-mono uppercase tracking-wider text-text-muted mb-1">
                    Primary
                  </div>
                  <span class="text-sm font-medium text-text-primary">
                    {obs()!.emotions!.primary_emotion}
                  </span>
                  <Show when={obs()?.emotions?.confidence != null}>
                    <div class="text-[10px] text-text-muted mt-0.5">
                      {Math.round(obs()!.emotions!.confidence! * 100)}%
                    </div>
                  </Show>
                </div>
              </Show>
            </div>
          </div>
        </HudFrame>

        {/* Bottom panel: Emily's observations */}
        <div class="col-span-2 flex gap-4 min-h-0">
          {/* Scene analysis */}
          <div class="flex-1 flex flex-col rounded-xl border border-border bg-surface-raised overflow-hidden min-h-0">
            <div class="flex items-center gap-2 px-4 py-2 border-b border-border bg-accent/[0.03] flex-shrink-0">
              <Eye class="w-3.5 h-3.5 text-accent" />
              <span class="text-[10px] font-mono uppercase tracking-widest text-text-muted">
                Emily's Observations
              </span>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
              <Show when={obs()?.screen?.summary} fallback={
                <div class="flex flex-col items-center justify-center py-8 gap-2">
                  <Scan class="w-6 h-6 text-text-muted opacity-30" />
                  <span class="text-xs font-mono text-text-muted">
                    No analysis yet \u2014 click ANALYZE NOW
                  </span>
                </div>
              }>
                <div class="space-y-3">
                  <p class="text-sm text-text-secondary leading-relaxed">
                    {obs()!.screen!.summary}
                  </p>
                  <Show when={obs()?.screen?.text_content}>
                    <div class="space-y-1">
                      <div class="flex items-center gap-1.5 text-[10px] font-mono text-text-muted uppercase tracking-wider">
                        <ChevronRight class="w-3 h-3" />
                        Visible text content
                      </div>
                      <p class="text-xs text-text-muted leading-relaxed bg-surface rounded-lg p-3 border border-border">
                        {obs()!.screen!.text_content}
                      </p>
                    </div>
                  </Show>
                </div>
              </Show>
            </div>
          </div>

          {/* OCR text + Metrics column */}
          <div class="w-80 flex flex-col gap-4 min-h-0">
            {/* OCR panel */}
            <div class="flex-1 flex flex-col rounded-xl border border-border bg-surface-raised overflow-hidden min-h-0">
              <div class="flex items-center gap-2 px-4 py-2 border-b border-border bg-accent/[0.03] flex-shrink-0">
                <Scan class="w-3.5 h-3.5 text-accent" />
                <span class="text-[10px] font-mono uppercase tracking-widest text-text-muted">
                  OCR Extract
                </span>
              </div>
              <div class="flex-1 overflow-y-auto p-3 min-h-0">
                <Show when={obs()?.ocr_text} fallback={
                  <div class="flex items-center justify-center py-6">
                    <span class="text-[10px] font-mono text-text-muted">Awaiting OCR...</span>
                  </div>
                }>
                  <pre class="text-[11px] font-mono text-text-secondary leading-relaxed whitespace-pre-wrap break-words">
                    {obs()!.ocr_text}
                  </pre>
                </Show>
              </div>
            </div>

            {/* Metric cards */}
            <div class="grid grid-cols-2 gap-2 flex-shrink-0">
              <VisionMetricCard icon={Monitor} label="Active App" value={obs()?.screen?.active_app ?? '\u2014'} color="var(--color-accent)" />
              <VisionMetricCard icon={Activity} label="Content" value={obs()?.screen?.content_type ?? '\u2014'} color="var(--color-phase-comparing)" />
              <VisionMetricCard icon={User} label="Presence" value={presenceState()} color={presenceColor()} />
              <VisionMetricCard icon={Zap} label="Emotion" value={obs()?.emotions?.primary_emotion ?? '\u2014'} color="var(--color-warning)" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
