import { createSignal, createEffect, createMemo, onMount, onCleanup, For, Show } from 'solid-js'
import { API_RAW } from '../lib/env'
import {
  Search, Trash2, Download, RefreshCw, Shield,
  Zap, AlertTriangle, Bug, Info, ChevronRight,
  Activity, Radio, Brain, Layers,
} from 'lucide-solid'
import type { Component } from 'solid-js'

// ── Types ───────────────────────────────────────────────────────────────────

type LogLevel = 'debug' | 'info' | 'warning' | 'error'
type LogTab   = 'logs' | 'audit'

interface LogEntry {
  timestamp?: string
  level?: LogLevel
  event?: string
  message?: string
  [key: string]: unknown
}

// ── Level config ────────────────────────────────────────────────────────────

const LEVEL_CFG: Record<LogLevel, { color: string; bg: string; border: string; icon: Component<{ class?: string; style?: Record<string, string> }>; label: string }> = {
  debug: {
    color:  'var(--color-text-muted)',
    bg:     'transparent',
    border: 'transparent',
    icon:   Bug,
    label:  'DBG',
  },
  info: {
    color:  'var(--color-phase-comparing)',
    bg:     'color-mix(in oklch, var(--color-phase-comparing) 6%, transparent)',
    border: 'color-mix(in oklch, var(--color-phase-comparing) 20%, transparent)',
    icon:   Info,
    label:  'INF',
  },
  warning: {
    color:  'var(--color-warning)',
    bg:     'color-mix(in oklch, var(--color-warning) 7%, transparent)',
    border: 'color-mix(in oklch, var(--color-warning) 22%, transparent)',
    icon:   AlertTriangle,
    label:  'WRN',
  },
  error: {
    color:  'var(--color-error)',
    bg:     'color-mix(in oklch, var(--color-error) 8%, transparent)',
    border: 'color-mix(in oklch, var(--color-error) 28%, transparent)',
    icon:   Zap,
    label:  'ERR',
  },
}

// ── Emily commentary triggers ───────────────────────────────────────────────

const EMILY_COMMENTARY: { pattern: RegExp; message: string }[] = [
  { pattern: /startup|bootstrap|initialized/i,     message: "I just woke up" },
  { pattern: /error|exception|failed|crash/i,       message: "Something went wrong \u2014 let me check." },
  { pattern: /reflection/i,                         message: "I'm reflecting on my recent experiences." },
  { pattern: /memory.*saved|episode.*saved/i,       message: "Just saved a new memory." },
  { pattern: /llm_first_token/i,                    message: "Thinking in progress\u2026" },
  { pattern: /tts|synthesis|speaking/i,             message: "Finding my voice." },
  { pattern: /wake.*word|hey.*emily/i,              message: "Someone's calling for me!" },
  { pattern: /shutdown|closing/i,                   message: "Time to rest." },
]

function getEmilyComment(log: LogEntry): string | null {
  const text = `${log.event || ''} ${log.message || ''}`.toLowerCase()
  for (const { pattern, message } of EMILY_COMMENTARY) {
    if (pattern.test(text)) return message
  }
  return null
}

// ── Module extractor ────────────────────────────────────────────────────────

function extractModule(log: LogEntry): string {
  const event = String(log.event || '')
  if (event.includes('.')) return event.split('.')[0]
  const parts = event.split('_')
  return parts[0] || 'core'
}

// ── Format helpers ──────────────────────────────────────────────────────────

function fmtTime(ts?: string): string {
  if (!ts) return ''
  try { return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
  catch { return ts.slice(11, 19) }
}

function fmtMs(ts?: string): string {
  if (!ts) return ''
  try { return '.' + String(new Date(ts).getMilliseconds()).padStart(3, '0') }
  catch { return '' }
}

// ── Module activity panel ───────────────────────────────────────────────────

function ModulePanel(props: { logs: LogEntry[] }) {
  const modules = createMemo(() => {
    const counts: Record<string, { total: number; errors: number; last?: string }> = {}
    for (const log of props.logs) {
      const m = extractModule(log)
      if (!counts[m]) counts[m] = { total: 0, errors: 0 }
      counts[m].total++
      if (log.level === 'error' || log.level === 'warning') counts[m].errors++
      counts[m].last = log.timestamp
    }
    return Object.entries(counts)
      .sort((a, b) => b[1].total - a[1].total)
      .slice(0, 15)
  })

  const maxCount = createMemo(() => Math.max(...modules().map(([, v]) => v.total), 1))

  return (
    <div class="w-40 flex-shrink-0 border-r border-border flex flex-col">
      <div class="px-3 py-2 border-b border-border">
        <div class="flex items-center gap-1.5">
          <Layers class="w-3 h-3 text-text-muted" />
          <span class="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Modules</span>
        </div>
      </div>
      <div class="flex-1 overflow-y-auto p-2 space-y-1">
        <For each={modules()}>{([mod, data]) => (
          <div class="group">
            <div class="flex items-center justify-between mb-0.5">
              <span class="text-[10px] text-text-secondary font-mono truncate flex-1">{mod}</span>
              <span class={`text-[10px] font-mono ${data.errors > 0 ? 'text-warning-amber' : 'text-text-muted'}`}>
                {data.total}
              </span>
            </div>
            <div class="h-1 bg-surface rounded-full overflow-hidden">
              <div
                class="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${(data.total / maxCount()) * 100}%`,
                  'background-color': data.errors > 0 ? 'var(--color-warning)' : 'var(--color-accent)',
                  opacity: '0.7',
                }}
              />
            </div>
          </div>
        )}</For>
        <Show when={modules().length === 0}>
          <div class="text-[10px] text-text-muted text-center py-4">No modules</div>
        </Show>
      </div>
    </div>
  )
}

// ── Log entry row ───────────────────────────────────────────────────────────

function LogRow(props: { log: LogEntry; idx: number; isNew: boolean }) {
  const [expanded, setExpanded] = createSignal(false)
  const level = () => (props.log.level as LogLevel) || 'info'
  const cfg = () => LEVEL_CFG[level()] || LEVEL_CFG.info
  const module = () => extractModule(props.log)
  const emily = () => getEmilyComment(props.log)

  const extraKeys = createMemo(() =>
    Object.keys(props.log).filter(k => !['timestamp', 'level', 'event', 'message'].includes(k))
  )

  return (
    <div
      class={props.isNew ? 'animate-log-row' : ''}
      style={props.isNew ? { 'animation-delay': `${Math.min(props.idx * 0.02, 0.4)}s` } : undefined}
    >
      <div
        class="group flex items-start gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-all hover:scale-[1.002]"
        style={{
          'background-color': expanded() ? cfg().bg : undefined,
          border: expanded() ? `1px solid ${cfg().border}` : '1px solid transparent',
        }}
        onMouseEnter={(e) => {
          if (!expanded()) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor = cfg().bg
          }
        }}
        onMouseLeave={(e) => {
          if (!expanded()) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor = ''
          }
        }}
        onClick={() => extraKeys().length > 0 && setExpanded(e => !e)}
      >
        {/* Level icon */}
        <div class="flex-shrink-0 mt-0.5">
          {(() => { const Icon = cfg().icon; return <Icon class="w-3 h-3" style={{ color: cfg().color }} /> })()}
        </div>

        {/* Timestamp */}
        <div class="flex-shrink-0 w-20 text-[10px] font-mono text-text-muted tabular-nums">
          {fmtTime(props.log.timestamp)}
          <span class="opacity-40">{fmtMs(props.log.timestamp)}</span>
        </div>

        {/* Level badge */}
        <span class="flex-shrink-0 text-[9px] font-bold tracking-widest w-8" style={{ color: cfg().color }}>
          {cfg().label}
        </span>

        {/* Module */}
        <span class="flex-shrink-0 text-[10px] font-mono text-text-muted w-20 truncate opacity-60">
          {module()}
        </span>

        {/* Event */}
        <span class="flex-shrink-0 text-[11px] font-semibold text-text-secondary w-36 truncate">
          {props.log.event}
        </span>

        {/* Message */}
        <span class="text-[11px] text-text-muted flex-1 truncate">
          {props.log.message || ''}
        </span>

        {/* Expand indicator */}
        <Show when={extraKeys().length > 0}>
          <ChevronRight
            class="w-3 h-3 text-text-muted flex-shrink-0 opacity-0 group-hover:opacity-100 transition-all"
            style={{ transform: expanded() ? 'rotate(90deg)' : 'none' }}
          />
        </Show>
      </div>

      {/* Expanded payload */}
      <Show when={expanded() && extraKeys().length > 0}>
        <div class="ml-[5.5rem] mr-3 mb-1">
          <pre class="p-3 bg-code-bg border border-code-border rounded-lg text-[11px] text-text-secondary overflow-x-auto max-h-48 leading-relaxed">
            {JSON.stringify(
              Object.fromEntries(extraKeys().map(k => [k, props.log[k]])),
              null, 2
            )}
          </pre>
        </div>
      </Show>

      {/* Emily commentary */}
      <Show when={emily() && level() !== 'debug'}>
        <div class="ml-[5.5rem] mr-3 mb-1 flex items-center gap-1.5 opacity-50 hover:opacity-80 transition-opacity">
          <div class="w-4 h-4 rounded-full bg-accent/15 border border-accent/30 flex items-center justify-center flex-shrink-0">
            <Brain class="w-2.5 h-2.5 text-accent" />
          </div>
          <span class="text-[10px] italic text-text-muted">{emily()}</span>
        </div>
      </Show>
    </div>
  )
}

// ── Live indicator ──────────────────────────────────────────────────────────

function LiveIndicator(props: { live: boolean }) {
  return (
    <div class="flex items-center gap-1.5">
      <div
        class={`w-2 h-2 rounded-full ${props.live ? 'animate-live-pulse bg-success' : 'bg-text-muted'}`}
      />
      <span class={`text-[10px] font-semibold uppercase tracking-wider ${props.live ? 'text-success' : 'text-text-muted'}`}>
        {props.live ? 'Live' : 'Paused'}
      </span>
    </div>
  )
}

// ── Level counts ────────────────────────────────────────────────────────────

function LevelBar(props: { logs: LogEntry[] }) {
  const counts = createMemo(() => {
    const c = { debug: 0, info: 0, warning: 0, error: 0 }
    for (const l of props.logs) {
      const lvl = l.level as LogLevel
      if (lvl in c) c[lvl]++
    }
    return c
  })

  return (
    <div class="flex items-center gap-3">
      <For each={Object.entries(counts()) as [LogLevel, number][]}>{([lvl, count]) => {
        const cfgEntry = LEVEL_CFG[lvl]
        return (
          <Show when={count > 0}>
            <div class="flex items-center gap-1">
              {(() => { const Icon = cfgEntry.icon; return <Icon class="w-3 h-3" style={{ color: cfgEntry.color }} /> })()}
              <span class="text-[11px] font-mono tabular-nums" style={{ color: cfgEntry.color }}>
                {count}
              </span>
            </div>
          </Show>
        )
      }}</For>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────

export function LogsPage() {
  const [logs, setLogs] = createSignal<LogEntry[]>([])
  const [level, setLevel] = createSignal<LogLevel | 'all'>('all')
  const [search, setSearch] = createSignal('')
  const [autoScroll, setAutoScroll] = createSignal(true)
  const [tab, setTab] = createSignal<LogTab>('logs')
  const [prevCount, setPrevCount] = createSignal(0)
  let scrollRef: HTMLDivElement | undefined
  let prevLogsCount = 0

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${API_RAW}/logs/recent?n=500`)
      if (!res.ok) return
      const data = await res.json()
      const newLogs: LogEntry[] = Array.isArray(data) ? data : data.logs || []
      setPrevCount(prevLogsCount)
      prevLogsCount = newLogs.length
      setLogs(newLogs)
    } catch { /* ignore */ }
  }

  onMount(() => {
    void fetchLogs()
    const poll = setInterval(() => void fetchLogs(), 2000)
    onCleanup(() => clearInterval(poll))
  })

  createEffect(() => {
    logs() // track
    if (autoScroll() && scrollRef) {
      scrollRef.scrollTop = scrollRef.scrollHeight
    }
  })

  const filtered = createMemo(() => logs().filter(log => {
    if (level() !== 'all' && log.level !== level()) return false
    if (search()) {
      const s = search().toLowerCase()
      const text = `${log.event || ''} ${log.message || ''} ${JSON.stringify(log)}`.toLowerCase()
      if (!text.includes(s)) return false
    }
    return true
  }))

  const exportLogs = () => {
    const blob = new Blob([JSON.stringify(filtered(), null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `emily-logs-${new Date().toISOString().slice(0, 19)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div class="flex flex-1 flex-col min-h-0">
      {/* Top toolbar */}
      <div class="flex items-center gap-2 px-4 py-2 border-b border-border flex-shrink-0 flex-wrap gap-y-1">
        <Activity class="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
        <span class="text-[11px] font-bold text-text-muted uppercase tracking-widest">Logs</span>

        {/* Tab switcher */}
        <div class="flex bg-surface rounded-lg p-0.5">
          <button
            onClick={() => setTab('logs')}
            class={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              tab() === 'logs' ? 'bg-surface-raised text-text-primary' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            Stream
          </button>
          <button
            onClick={() => setTab('audit')}
            class={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              tab() === 'audit' ? 'bg-surface-raised text-text-primary' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            <Shield class="w-3 h-3" />
            Audit
          </button>
        </div>

        <Show when={tab() === 'logs'}>
          <div class="w-px h-4 bg-border" />

          <LiveIndicator live={autoScroll()} />

          {/* Level filter */}
          <select
            value={level()}
            onInput={(e) => setLevel(e.currentTarget.value as LogLevel | 'all')}
            class="bg-surface border border-border rounded-lg px-2 py-1 text-xs text-text-primary"
          >
            <option value="all">All</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
            <option value="debug">Debug</option>
          </select>

          {/* Search */}
          <div class="flex items-center gap-1.5 bg-surface border border-border rounded-lg px-2 py-1">
            <Search class="w-3 h-3 text-text-muted" />
            <input
              value={search()}
              onInput={(e) => setSearch(e.currentTarget.value)}
              placeholder="Filter\u2026"
              class="bg-transparent text-xs text-text-primary placeholder:text-text-muted w-28 outline-none"
            />
          </div>

          {/* Level counts */}
          <LevelBar logs={filtered()} />
        </Show>

        <div class="flex-1" />

        <Show when={tab() === 'logs'}>
          <button
            onClick={() => setAutoScroll(a => !a)}
            class={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
              autoScroll() ? 'bg-success/15 text-success' : 'bg-surface text-text-muted'
            }`}
          >
            <Radio class="w-3 h-3" />
            Auto
          </button>
          <button onClick={exportLogs} class="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted" title="Export">
            <Download class="w-3.5 h-3.5" />
          </button>
          <button onClick={() => setLogs([])} class="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted" title="Clear">
            <Trash2 class="w-3.5 h-3.5" />
          </button>
          <button onClick={() => void fetchLogs()} class="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted" title="Refresh">
            <RefreshCw class="w-3.5 h-3.5" />
          </button>
        </Show>
      </div>

      <Show when={tab() === 'logs'} fallback={
        <div class="flex-1 flex items-center justify-center text-text-muted text-sm">
          Audit Trail (Coming Soon)
        </div>
      }>
        <div class="flex flex-1 min-h-0">
          {/* Module sidebar */}
          <ModulePanel logs={filtered()} />

          {/* Log stream */}
          <div class="flex-1 flex flex-col min-w-0">
            <div
              ref={scrollRef}
              class="flex-1 overflow-y-auto p-2 font-mono text-xs leading-relaxed"
            >
              <Show when={filtered().length > 0} fallback={
                <div class="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
                  <Activity class="w-8 h-8 opacity-20" />
                  <p class="text-xs">No log entries match your filter</p>
                </div>
              }>
                <div class="space-y-0.5">
                  <For each={filtered()}>{(log, i) => (
                    <LogRow
                      log={log}
                      idx={i()}
                      isNew={i() >= prevCount()}
                    />
                  )}</For>
                </div>
              </Show>
            </div>

            {/* Status footer */}
            <div class="flex items-center justify-between px-4 py-1.5 border-t border-border text-[10px] text-text-muted flex-shrink-0">
              <div class="flex items-center gap-3">
                <span>{filtered().length} / {logs().length} entries</span>
                <Show when={logs().length > prevCount() && prevCount() > 0}>
                  <span class="text-success animate-live-pulse">
                    +{logs().length - prevCount()} new
                  </span>
                </Show>
              </div>
              <span>{new Date().toLocaleTimeString('en-US', { hour12: false })}</span>
            </div>
          </div>
        </div>
      </Show>
    </div>
  )
}
