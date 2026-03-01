import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  Search, Trash2, Download, RefreshCw, Shield,
  Zap, AlertTriangle, Bug, Info, ChevronRight,
  Activity, Radio, Brain, Layers,
} from 'lucide-react'
import { AuditTrailTab } from '../components/logs/AuditTrailTab'
import { LogFrequencySparkline } from '../components/logs/LogFrequencySparkline'

// ─── Types ────────────────────────────────────────────────────────────────────

type LogLevel = 'debug' | 'info' | 'warning' | 'error'
type LogTab   = 'logs' | 'audit'

interface LogEntry {
  timestamp?: string
  level?: LogLevel
  event?: string
  message?: string
  [key: string]: unknown
}

// ─── Level config ─────────────────────────────────────────────────────────────

const LEVEL_CFG: Record<LogLevel, { color: string; bg: string; border: string; icon: React.FC<any>; label: string }> = {
  debug: {
    color:  '#555570',
    bg:     'transparent',
    border: 'transparent',
    icon:   Bug,
    label:  'DBG',
  },
  info: {
    color:  '#3b82f6',
    bg:     'rgba(59,130,246,0.04)',
    border: 'rgba(59,130,246,0.12)',
    icon:   Info,
    label:  'INF',
  },
  warning: {
    color:  '#f59e0b',
    bg:     'rgba(245,158,11,0.05)',
    border: 'rgba(245,158,11,0.18)',
    icon:   AlertTriangle,
    label:  'WRN',
  },
  error: {
    color:  '#ef4444',
    bg:     'rgba(239,68,68,0.07)',
    border: 'rgba(239,68,68,0.25)',
    icon:   Zap,
    label:  'ERR',
  },
}

// ─── Emily commentary triggers ────────────────────────────────────────────────

const EMILY_COMMENTARY: { pattern: RegExp; message: string }[] = [
  { pattern: /startup|bootstrap|initialized/i,     message: "I just woke up ✨" },
  { pattern: /error|exception|failed|crash/i,       message: "Something went wrong — let me check." },
  { pattern: /reflection/i,                         message: "I'm reflecting on my recent experiences." },
  { pattern: /memory.*saved|episode.*saved/i,       message: "Just saved a new memory." },
  { pattern: /llm_first_token/i,                    message: "Thinking in progress…" },
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

// ─── Module extractor ─────────────────────────────────────────────────────────

function extractModule(log: LogEntry): string {
  const event = String(log.event || '')
  if (event.includes('.')) return event.split('.')[0]
  const parts = event.split('_')
  return parts[0] || 'core'
}

// ─── Format helpers ───────────────────────────────────────────────────────────

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

// ─── Module activity panel ────────────────────────────────────────────────────

function ModulePanel({ logs }: { logs: LogEntry[] }) {
  const modules = useMemo(() => {
    const counts: Record<string, { total: number; errors: number; last?: string }> = {}
    for (const log of logs) {
      const m = extractModule(log)
      if (!counts[m]) counts[m] = { total: 0, errors: 0 }
      counts[m].total++
      if (log.level === 'error' || log.level === 'warning') counts[m].errors++
      counts[m].last = log.timestamp
    }
    return Object.entries(counts)
      .sort((a, b) => b[1].total - a[1].total)
      .slice(0, 15)
  }, [logs])

  const maxCount = Math.max(...modules.map(([, v]) => v.total), 1)

  return (
    <div className="w-40 flex-shrink-0 border-r border-border flex flex-col">
      <div className="px-3 py-2 border-b border-border">
        <div className="flex items-center gap-1.5">
          <Layers className="w-3 h-3 text-text-muted" />
          <span className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Modules</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {modules.map(([mod, data]) => (
          <div key={mod} className="group">
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[10px] text-text-secondary font-mono truncate flex-1">{mod}</span>
              <span className={`text-[10px] font-mono ${data.errors > 0 ? 'text-warning-amber' : 'text-text-muted'}`}>
                {data.total}
              </span>
            </div>
            <div className="h-1 bg-surface rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${(data.total / maxCount) * 100}%`,
                  backgroundColor: data.errors > 0 ? '#f59e0b' : '#7c6af7',
                  opacity: 0.7,
                }}
              />
            </div>
          </div>
        ))}
        {modules.length === 0 && (
          <div className="text-[10px] text-text-muted text-center py-4">No modules</div>
        )}
      </div>
    </div>
  )
}

// ─── Log entry row ────────────────────────────────────────────────────────────

interface LogRowProps {
  log: LogEntry
  idx: number
  isNew: boolean
}

function LogRow({ log, idx, isNew }: LogRowProps) {
  const [expanded, setExpanded] = useState(false)
  const level  = (log.level as LogLevel) || 'info'
  const cfg    = LEVEL_CFG[level] || LEVEL_CFG.info
  const Icon   = cfg.icon
  const module = extractModule(log)
  const emily  = getEmilyComment(log)

  const extraKeys = Object.keys(log).filter(
    k => !['timestamp', 'level', 'event', 'message'].includes(k)
  )

  return (
    <div
      className={isNew ? 'animate-log-row' : ''}
      style={isNew ? { animationDelay: `${Math.min(idx * 0.02, 0.4)}s` } : undefined}
    >
      <div
        className="group flex items-start gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-all hover:scale-[1.002]"
        style={{
          backgroundColor: expanded ? cfg.bg : undefined,
          border: expanded ? `1px solid ${cfg.border}` : '1px solid transparent',
        }}
        onMouseEnter={e => {
          if (!expanded) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor = cfg.bg
          }
        }}
        onMouseLeave={e => {
          if (!expanded) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor = ''
          }
        }}
        onClick={() => extraKeys.length > 0 && setExpanded(e => !e)}
      >
        {/* Level icon */}
        <div className="flex-shrink-0 mt-0.5">
          <Icon className="w-3 h-3" style={{ color: cfg.color }} />
        </div>

        {/* Timestamp */}
        <div className="flex-shrink-0 w-20 text-[10px] font-mono text-text-muted tabular-nums">
          {fmtTime(log.timestamp)}
          <span className="opacity-40">{fmtMs(log.timestamp)}</span>
        </div>

        {/* Level badge */}
        <span
          className="flex-shrink-0 text-[9px] font-bold tracking-widest w-8"
          style={{ color: cfg.color }}
        >
          {cfg.label}
        </span>

        {/* Module */}
        <span className="flex-shrink-0 text-[10px] font-mono text-text-muted w-20 truncate opacity-60">
          {module}
        </span>

        {/* Event */}
        <span className="flex-shrink-0 text-[11px] font-semibold text-text-secondary w-36 truncate">
          {log.event}
        </span>

        {/* Message */}
        <span className="text-[11px] text-text-muted flex-1 truncate">
          {log.message || ''}
        </span>

        {/* Expand indicator */}
        {extraKeys.length > 0 && (
          <ChevronRight
            className="w-3 h-3 text-text-muted flex-shrink-0 opacity-0 group-hover:opacity-100 transition-all"
            style={{ transform: expanded ? 'rotate(90deg)' : 'none' }}
          />
        )}
      </div>

      {/* Expanded payload */}
      {expanded && extraKeys.length > 0 && (
        <div className="ml-[5.5rem] mr-3 mb-1">
          <pre className="p-3 bg-code-bg border border-code-border rounded-lg text-[11px] text-text-secondary overflow-x-auto max-h-48 leading-relaxed">
            {JSON.stringify(
              Object.fromEntries(extraKeys.map(k => [k, log[k]])),
              null, 2
            )}
          </pre>
        </div>
      )}

      {/* Emily commentary */}
      {emily && level !== 'debug' && (
        <div className="ml-[5.5rem] mr-3 mb-1 flex items-center gap-1.5 opacity-50 hover:opacity-80 transition-opacity">
          <div className="w-4 h-4 rounded-full bg-accent/15 border border-accent/30 flex items-center justify-center flex-shrink-0">
            <Brain className="w-2.5 h-2.5 text-accent" />
          </div>
          <span className="text-[10px] italic text-text-muted">{emily}</span>
        </div>
      )}
    </div>
  )
}

// ─── Live indicator ───────────────────────────────────────────────────────────

function LiveIndicator({ live }: { live: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={`w-2 h-2 rounded-full ${live ? 'animate-live-pulse bg-cost-green' : 'bg-text-muted'}`}
      />
      <span className={`text-[10px] font-semibold uppercase tracking-wider ${live ? 'text-cost-green' : 'text-text-muted'}`}>
        {live ? 'Live' : 'Paused'}
      </span>
    </div>
  )
}

// ─── Level counts ─────────────────────────────────────────────────────────────

function LevelBar({ logs }: { logs: LogEntry[] }) {
  const counts = useMemo(() => {
    const c = { debug: 0, info: 0, warning: 0, error: 0 }
    for (const l of logs) {
      const lvl = l.level as LogLevel
      if (lvl in c) c[lvl]++
    }
    return c
  }, [logs])

  return (
    <div className="flex items-center gap-3">
      {(Object.entries(counts) as [LogLevel, number][]).map(([lvl, count]) => {
        const cfg = LEVEL_CFG[lvl]
        if (!count) return null
        return (
          <div key={lvl} className="flex items-center gap-1">
            <cfg.icon className="w-3 h-3" style={{ color: cfg.color }} />
            <span className="text-[11px] font-mono tabular-nums" style={{ color: cfg.color }}>
              {count}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function LogsPage() {
  const [logs,       setLogs]       = useState<LogEntry[]>([])
  const [level,      setLevel]      = useState<LogLevel | 'all'>('all')
  const [search,     setSearch]     = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [tab,        setTab]        = useState<LogTab>('logs')
  const [prevCount,  setPrevCount]  = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const prevLogsRef = useRef<LogEntry[]>([])

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch('/api/logs/recent?n=500')
      if (!res.ok) return
      const data = await res.json()
      const newLogs: LogEntry[] = Array.isArray(data) ? data : data.logs || []
      setPrevCount(prevLogsRef.current.length)
      prevLogsRef.current = newLogs
      setLogs(newLogs)
    } catch {}
  }, [])

  useEffect(() => {
    fetchLogs()
    const poll = setInterval(fetchLogs, 2000)
    return () => clearInterval(poll)
  }, [fetchLogs])

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const filtered = useMemo(() => logs.filter(log => {
    if (level !== 'all' && log.level !== level) return false
    if (search) {
      const s = search.toLowerCase()
      const text = `${log.event || ''} ${log.message || ''} ${JSON.stringify(log)}`.toLowerCase()
      if (!text.includes(s)) return false
    }
    return true
  }), [logs, level, search])

  const exportLogs = () => {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = `emily-logs-${new Date().toISOString().slice(0, 19)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const newEntriesStart = prevCount  // entries below this index are "new"

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {/* ── Top toolbar ────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border flex-shrink-0 flex-wrap gap-y-1">
        <Activity className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
        <span className="text-[11px] font-bold text-text-muted uppercase tracking-widest">Logs</span>

        {/* Tab switcher */}
        <div className="flex bg-surface rounded-lg p-0.5">
          <button
            onClick={() => setTab('logs')}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              tab === 'logs' ? 'bg-surface-raised text-text-primary' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            Stream
          </button>
          <button
            onClick={() => setTab('audit')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              tab === 'audit' ? 'bg-surface-raised text-text-primary' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            <Shield className="w-3 h-3" />
            Audit
          </button>
        </div>

        {tab === 'logs' && (
          <>
            <div className="w-px h-4 bg-border" />

            <LiveIndicator live={autoScroll} />

            {/* Level filter */}
            <select
              value={level}
              onChange={e => setLevel(e.target.value as LogLevel | 'all')}
              className="bg-surface border border-border rounded-lg px-2 py-1 text-xs text-text-primary"
            >
              <option value="all">All</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="debug">Debug</option>
            </select>

            {/* Search */}
            <div className="flex items-center gap-1.5 bg-surface border border-border rounded-lg px-2 py-1">
              <Search className="w-3 h-3 text-text-muted" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Filter…"
                className="bg-transparent text-xs text-text-primary placeholder:text-text-muted w-28 outline-none"
              />
            </div>

            {/* Level counts */}
            <LevelBar logs={filtered} />

            {/* Sparkline */}
            <LogFrequencySparkline logs={logs} />
          </>
        )}

        <div className="flex-1" />

        {tab === 'logs' && (
          <>
            <button
              onClick={() => setAutoScroll(a => !a)}
              className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
                autoScroll ? 'bg-cost-green/15 text-cost-green' : 'bg-surface text-text-muted'
              }`}
            >
              <Radio className="w-3 h-3" />
              Auto
            </button>
            <button onClick={exportLogs} className="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted" title="Export">
              <Download className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => setLogs([])} className="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted" title="Clear">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <button onClick={fetchLogs} className="p-1.5 rounded-lg hover:bg-surface-hover text-text-muted" title="Refresh">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </>
        )}
      </div>

      {tab === 'logs' ? (
        <div className="flex flex-1 min-h-0">
          {/* ── Module sidebar ───────────────────────────────────────── */}
          <ModulePanel logs={filtered} />

          {/* ── Log stream ──────────────────────────────────────────── */}
          <div className="flex-1 flex flex-col min-w-0">
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto p-2 font-mono text-xs leading-relaxed"
            >
              {filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
                  <Activity className="w-8 h-8 opacity-20" />
                  <p className="text-xs">No log entries match your filter</p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {filtered.map((log, i) => (
                    <LogRow
                      key={i}
                      log={log}
                      idx={i}
                      isNew={i >= newEntriesStart}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Status footer */}
            <div className="flex items-center justify-between px-4 py-1.5 border-t border-border text-[10px] text-text-muted flex-shrink-0">
              <div className="flex items-center gap-3">
                <span>{filtered.length} / {logs.length} entries</span>
                {logs.length > prevCount && prevCount > 0 && (
                  <span className="text-cost-green animate-live-pulse">
                    +{logs.length - prevCount} new
                  </span>
                )}
              </div>
              <span>{new Date().toLocaleTimeString('en-US', { hour12: false })}</span>
            </div>
          </div>
        </div>
      ) : (
        <AuditTrailTab />
      )}
    </div>
  )
}
