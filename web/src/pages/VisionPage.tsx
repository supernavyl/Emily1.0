import { useState, useEffect, useCallback, useRef } from 'react'
import { API_RAW } from '../lib/env'
import {
  Eye, Monitor, Camera, Cpu, Scan, RefreshCw, AlertCircle,
  User, Activity, Zap, Clock, ChevronRight, Maximize2,
} from 'lucide-react'

const API = API_RAW

// ── Types ────────────────────────────────────────────────────────────────────

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

// ── Presence color map ───────────────────────────────────────────────────────

const PRESENCE_COLOR: Record<string, string> = {
  PRESENT: '#22c55e',
  IDLE: '#f59e0b',
  AWAY: '#ef4444',
  UNKNOWN: '#64748b',
}

const PRESENCE_GLOW: Record<string, string> = {
  PRESENT: 'rgba(34,197,94,0.3)',
  IDLE: 'rgba(245,158,11,0.3)',
  AWAY: 'rgba(239,68,68,0.3)',
  UNKNOWN: 'rgba(100,116,139,0.2)',
}

// ── Sub-components ───────────────────────────────────────────────────────────

function StatusDot({ active, label }: { active: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div
        className="w-2 h-2 rounded-full"
        style={{
          backgroundColor: active ? '#22c55e' : '#ef4444',
          boxShadow: active ? '0 0 6px rgba(34,197,94,0.5)' : 'none',
        }}
      />
      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
        {label}
      </span>
    </div>
  )
}

function HudFrame({
  children,
  label,
  live,
  className = '',
  onMaximize,
}: {
  children: React.ReactNode
  label: string
  live?: boolean
  className?: string
  onMaximize?: () => void
}) {
  return (
    <div className={`relative group ${className}`}>
      {/* Glass card */}
      <div className="relative overflow-hidden rounded-xl border border-cyan-500/15 bg-black/60 backdrop-blur-sm">
        {/* Corner brackets */}
        <div className="absolute top-0 left-0 w-5 h-5 border-t-2 border-l-2 border-cyan-500/40 rounded-tl animate-bracket-pulse" />
        <div className="absolute top-0 right-0 w-5 h-5 border-t-2 border-r-2 border-cyan-500/40 rounded-tr animate-bracket-pulse" />
        <div className="absolute bottom-0 left-0 w-5 h-5 border-b-2 border-l-2 border-cyan-500/40 rounded-bl animate-bracket-pulse" />
        <div className="absolute bottom-0 right-0 w-5 h-5 border-b-2 border-r-2 border-cyan-500/40 rounded-br animate-bracket-pulse" />

        {/* Scan line */}
        <div className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent animate-scan-line pointer-events-none" />

        {/* Header bar */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-cyan-500/10 bg-cyan-500/[0.03]">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono uppercase tracking-widest text-cyan-400/70">
              {label}
            </span>
            {live && (
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-live-pulse" />
                <span className="text-[9px] font-mono text-red-400/80">LIVE</span>
              </div>
            )}
          </div>
          {onMaximize && (
            <button
              onClick={onMaximize}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:bg-white/5 rounded"
            >
              <Maximize2 className="w-3 h-3 text-cyan-400/50" />
            </button>
          )}
        </div>

        {/* Content */}
        {children}
      </div>
    </div>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
  color = '#06b6d4',
}: {
  icon: typeof Eye
  label: string
  value: string
  color?: string
}) {
  return (
    <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg border border-white/[0.06] bg-white/[0.02]">
      <Icon className="w-4 h-4 flex-shrink-0" style={{ color }} />
      <div className="min-w-0">
        <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">{label}</div>
        <div className="text-sm font-medium text-slate-200 truncate">{value}</div>
      </div>
    </div>
  )
}

function EmotionBar({ emotion, confidence }: { emotion: string; confidence: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-mono text-slate-500 w-16 truncate">{emotion}</span>
      <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.round(confidence * 100)}%`,
            background: `linear-gradient(90deg, #7c6af7, #06b6d4)`,
          }}
        />
      </div>
      <span className="text-[10px] font-mono text-slate-500 w-8 text-right">
        {Math.round(confidence * 100)}%
      </span>
    </div>
  )
}

function PresenceRing({ state, confidence }: { state: string; confidence: number }) {
  const color = PRESENCE_COLOR[state] ?? PRESENCE_COLOR.UNKNOWN
  const glow = PRESENCE_GLOW[state] ?? PRESENCE_GLOW.UNKNOWN
  const radius = 32
  const circumference = 2 * Math.PI * radius
  const dashoffset = circumference * (1 - confidence)

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative w-20 h-20">
        <svg viewBox="0 0 80 80" className="w-full h-full -rotate-90">
          <circle cx="40" cy="40" r={radius} fill="none" stroke="white" strokeOpacity="0.05" strokeWidth="3" />
          <circle
            cx="40" cy="40" r={radius}
            fill="none"
            stroke={color}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashoffset}
            style={{ filter: `drop-shadow(0 0 6px ${glow})`, transition: 'stroke-dashoffset 0.5s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <User className="w-5 h-5" style={{ color }} />
        </div>
      </div>
      <span className="text-xs font-mono font-medium" style={{ color }}>{state}</span>
      <span className="text-[10px] text-slate-500">{Math.round(confidence * 100)}% conf</span>
    </div>
  )
}

// ── Expanded image modal ─────────────────────────────────────────────────────

function ImageModal({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-scale-in"
      onClick={onClose}
    >
      <div className="relative max-w-[90vw] max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={alt} className="max-w-full max-h-[85vh] rounded-xl border border-cyan-500/20" />
        <button
          onClick={onClose}
          className="absolute top-2 right-2 px-2 py-1 rounded bg-black/60 text-xs font-mono text-slate-300 hover:bg-black/80"
        >
          ESC
        </button>
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export function VisionPage() {
  const [status, setStatus] = useState<VisionStatus | null>(null)
  const [obs, setObs] = useState<Observations | null>(null)
  const [tick, setTick] = useState(0)
  const [analyzing, setAnalyzing] = useState(false)
  const [expanded, setExpanded] = useState<'screen' | 'webcam' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const screenRef = useRef<HTMLImageElement>(null)
  const webcamRef = useRef<HTMLImageElement>(null)

  // Poll status once on mount
  useEffect(() => {
    fetch(`${API}/vision/status`)
      .then((r) => r.json())
      .then(setStatus)
      .catch((e) => setError(`Vision API unreachable: ${e.message}`))
  }, [])

  // Refresh feeds every 3s
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 3000)
    return () => clearInterval(id)
  }, [])

  // Poll observations every 3s
  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API}/vision/observations`)
        if (res.ok) {
          setObs(await res.json())
          setError(null)
        }
      } catch {
        // Silently retry
      }
    }, 3000)
    return () => clearInterval(poll)
  }, [])

  // Keyboard shortcut: Escape closes modal
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(null)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const triggerAnalysis = useCallback(async () => {
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
    } catch (e: any) {
      setError(e.message)
    } finally {
      setAnalyzing(false)
    }
  }, [])

  const presenceState = obs?.presence?.state ?? 'UNKNOWN'
  const presenceColor = PRESENCE_COLOR[presenceState] ?? PRESENCE_COLOR.UNKNOWN
  const lastAnalysisAge = obs?.last_analysis_ts
    ? Math.round((Date.now() / 1000) - obs.last_analysis_ts)
    : null

  const screenSrc = `${API}/vision/screenshot?t=${tick}`
  const webcamSrc = `${API}/vision/webcam?t=${tick}`

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-y-auto" style={{ background: '#050510' }}>
      {/* Expanded image modal */}
      {expanded && (
        <ImageModal
          src={expanded === 'screen' ? screenSrc : webcamSrc}
          alt={expanded === 'screen' ? 'Screen capture' : 'Camera feed'}
          onClose={() => setExpanded(null)}
        />
      )}

      {/* ── Status bar ── */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-white/[0.06] bg-black/40 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-mono font-semibold text-cyan-400 tracking-wide">
              PERCEPTION HUD
            </span>
          </div>
          <div className="w-px h-4 bg-white/10" />
          <StatusDot active={status?.initialized ?? false} label="Pipeline" />
          <StatusDot active={status?.screen_available ?? false} label="Screen" />
          <StatusDot active={status?.webcam_available ?? false} label="Camera" />
        </div>

        <div className="flex items-center gap-3">
          {status?.analyzer_model && (
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-500">
              <Cpu className="w-3 h-3" />
              {status.analyzer_model}
            </div>
          )}
          {lastAnalysisAge !== null && (
            <div className="flex items-center gap-1 text-[10px] font-mono text-slate-500">
              <Clock className="w-3 h-3" />
              {lastAnalysisAge}s ago
            </div>
          )}
          <button
            onClick={triggerAnalysis}
            disabled={analyzing}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-mono
              bg-cyan-500/10 text-cyan-400 border border-cyan-500/20
              hover:bg-cyan-500/20 hover:border-cyan-500/30
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-all"
          >
            <RefreshCw className={`w-3 h-3 ${analyzing ? 'animate-spin' : ''}`} />
            {analyzing ? 'ANALYZING...' : 'ANALYZE NOW'}
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-5 mt-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* ── Main grid ── */}
      <div className="flex-1 p-5 grid grid-cols-[1fr_1fr] grid-rows-[auto_1fr] gap-4 min-h-0">

        {/* Screen capture feed */}
        <HudFrame
          label="Screen Capture"
          live={status?.screen_available}
          onMaximize={() => setExpanded('screen')}
        >
          <div className="relative aspect-video bg-black/80">
            {status?.screen_available ? (
              <img
                ref={screenRef}
                src={screenSrc}
                alt="Screen capture"
                className="w-full h-full object-contain"
                onError={() => {
                  if (screenRef.current) screenRef.current.style.display = 'none'
                }}
                onLoad={() => {
                  if (screenRef.current) screenRef.current.style.display = 'block'
                }}
              />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <Monitor className="w-8 h-8 text-slate-600" />
                <span className="text-xs font-mono text-slate-600">NO SIGNAL</span>
              </div>
            )}
            {/* Overlay: active app badge */}
            {obs?.screen?.active_app && (
              <div className="absolute bottom-2 left-2 flex items-center gap-1.5 px-2 py-1 rounded bg-black/70 backdrop-blur-sm border border-cyan-500/20">
                <Scan className="w-3 h-3 text-cyan-400" />
                <span className="text-[10px] font-mono text-cyan-300">{obs.screen.active_app}</span>
              </div>
            )}
            {obs?.screen?.content_type && (
              <div className="absolute bottom-2 right-2 px-2 py-1 rounded bg-black/70 backdrop-blur-sm border border-purple-500/20">
                <span className="text-[10px] font-mono text-purple-300">{obs.screen.content_type}</span>
              </div>
            )}
          </div>
        </HudFrame>

        {/* Webcam feed + presence/emotion sidebar */}
        <HudFrame
          label="Camera Feed"
          live={status?.webcam_available}
          onMaximize={() => setExpanded('webcam')}
        >
          <div className="flex">
            <div className="relative flex-1 aspect-video bg-black/80">
              {status?.webcam_available ? (
                <img
                  ref={webcamRef}
                  src={webcamSrc}
                  alt="Camera feed"
                  className="w-full h-full object-contain"
                  onError={() => {
                    if (webcamRef.current) webcamRef.current.style.display = 'none'
                  }}
                  onLoad={() => {
                    if (webcamRef.current) webcamRef.current.style.display = 'block'
                  }}
                />
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                  <Camera className="w-8 h-8 text-slate-600" />
                  <span className="text-xs font-mono text-slate-600">NO SIGNAL</span>
                </div>
              )}
              {/* Presence indicator overlay */}
              {obs?.presence && (
                <div
                  className="absolute top-2 right-2 flex items-center gap-1.5 px-2 py-1 rounded-full bg-black/70 backdrop-blur-sm"
                  style={{ borderColor: presenceColor, borderWidth: 1 }}
                >
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: presenceColor, boxShadow: `0 0 6px ${presenceColor}` }}
                  />
                  <span className="text-[10px] font-mono font-medium" style={{ color: presenceColor }}>
                    {presenceState}
                  </span>
                </div>
              )}
              {/* Face detected badge */}
              {obs?.presence?.face_detected && (
                <div className="absolute top-2 left-2 px-2 py-1 rounded bg-green-500/10 border border-green-500/20">
                  <span className="text-[10px] font-mono text-green-400">FACE DETECTED</span>
                </div>
              )}
            </div>

            {/* Sidebar: presence ring + emotion bars */}
            <div className="w-36 border-l border-cyan-500/10 p-3 flex flex-col items-center gap-3 bg-black/30">
              {obs?.presence ? (
                <PresenceRing state={presenceState} confidence={obs.presence.confidence} />
              ) : (
                <div className="flex flex-col items-center gap-1 py-3">
                  <User className="w-5 h-5 text-slate-600" />
                  <span className="text-[10px] font-mono text-slate-600">OFFLINE</span>
                </div>
              )}

              {/* Emotion bars */}
              {obs?.emotions?.all_emotions && (
                <div className="w-full space-y-1.5 mt-1">
                  <div className="text-[9px] font-mono uppercase tracking-wider text-slate-500 mb-1">
                    Emotions
                  </div>
                  {Object.entries(obs.emotions.all_emotions)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 5)
                    .map(([emotion, confidence]) => (
                      <EmotionBar key={emotion} emotion={emotion} confidence={confidence} />
                    ))}
                </div>
              )}

              {/* Primary emotion */}
              {obs?.emotions?.primary_emotion && !obs?.emotions?.all_emotions && (
                <div className="text-center mt-1">
                  <div className="text-[9px] font-mono uppercase tracking-wider text-slate-500 mb-1">
                    Primary
                  </div>
                  <span className="text-sm font-medium text-purple-300">
                    {obs.emotions.primary_emotion}
                  </span>
                  {obs.emotions.confidence != null && (
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      {Math.round(obs.emotions.confidence * 100)}%
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </HudFrame>

        {/* ── Bottom panel: Emily's observations ── */}
        <div className="col-span-2 flex gap-4 min-h-0">

          {/* Scene analysis */}
          <div className="flex-1 flex flex-col rounded-xl border border-purple-500/15 bg-black/60 backdrop-blur-sm overflow-hidden min-h-0">
            <div className="flex items-center gap-2 px-4 py-2 border-b border-purple-500/10 bg-purple-500/[0.03] flex-shrink-0">
              <Eye className="w-3.5 h-3.5 text-purple-400" />
              <span className="text-[10px] font-mono uppercase tracking-widest text-purple-400/70">
                Emily's Observations
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
              {obs?.screen?.summary ? (
                <div className="space-y-3">
                  <p className="text-sm text-slate-300 leading-relaxed">
                    {obs.screen.summary}
                  </p>
                  {obs.screen.text_content && (
                    <div className="space-y-1">
                      <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                        <ChevronRight className="w-3 h-3" />
                        Visible text content
                      </div>
                      <p className="text-xs text-slate-400 leading-relaxed bg-white/[0.02] rounded-lg p-3 border border-white/[0.04]">
                        {obs.screen.text_content}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 gap-2">
                  <Scan className="w-6 h-6 text-slate-600" />
                  <span className="text-xs font-mono text-slate-600">
                    No analysis yet — click ANALYZE NOW
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* OCR text + Metrics column */}
          <div className="w-80 flex flex-col gap-4 min-h-0">

            {/* OCR panel */}
            <div className="flex-1 flex flex-col rounded-xl border border-cyan-500/15 bg-black/60 backdrop-blur-sm overflow-hidden min-h-0">
              <div className="flex items-center gap-2 px-4 py-2 border-b border-cyan-500/10 bg-cyan-500/[0.03] flex-shrink-0">
                <Scan className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-[10px] font-mono uppercase tracking-widest text-cyan-400/70">
                  OCR Extract
                </span>
              </div>
              <div className="flex-1 overflow-y-auto p-3 min-h-0">
                {obs?.ocr_text ? (
                  <pre className="text-[11px] font-mono text-slate-400 leading-relaxed whitespace-pre-wrap break-words">
                    {obs.ocr_text}
                  </pre>
                ) : (
                  <div className="flex items-center justify-center py-6">
                    <span className="text-[10px] font-mono text-slate-600">Awaiting OCR...</span>
                  </div>
                )}
              </div>
            </div>

            {/* Metric cards */}
            <div className="grid grid-cols-2 gap-2 flex-shrink-0">
              <MetricCard
                icon={Monitor}
                label="Active App"
                value={obs?.screen?.active_app ?? '—'}
                color="#06b6d4"
              />
              <MetricCard
                icon={Activity}
                label="Content"
                value={obs?.screen?.content_type ?? '—'}
                color="#7c6af7"
              />
              <MetricCard
                icon={User}
                label="Presence"
                value={presenceState}
                color={presenceColor}
              />
              <MetricCard
                icon={Zap}
                label="Emotion"
                value={obs?.emotions?.primary_emotion ?? '—'}
                color="#f59e0b"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
