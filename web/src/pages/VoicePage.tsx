import { useState, useEffect, useRef, useCallback } from 'react'
import { API_RAW } from '../lib/env'
import {
  Mic, MicOff, Volume2, Trash2, Radio, Cpu, Zap, Clock,
  Activity, Waves, Brain, Speaker, ChevronRight, MicVocal, ChevronDown, Check,
} from 'lucide-react'

// Custom dropdown — native <select> is broken in WebKitGTK/Tauri
function VoiceDropdown({ value, options, onChange }: {
  value: string
  options: { value: string; label: string }[]
  onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const selected = options.find(o => o.value === value)

  return (
    <div ref={ref} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between bg-black border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 font-mono hover:border-violet-500/40 transition-colors"
      >
        <span>{selected?.label ?? 'Default'}</span>
        <ChevronDown className={`w-3 h-3 text-slate-600 transition-transform flex-shrink-0 ml-1 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 w-full mt-1 bg-[#080810] border border-white/10 rounded-xl shadow-2xl overflow-hidden">
          <div className="max-h-48 overflow-y-auto py-1">
            {options.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => { onChange(opt.value); setOpen(false) }}
                className={`w-full text-left flex items-center gap-2 px-3 py-1.5 text-xs font-mono transition-colors hover:bg-white/5 ${
                  opt.value === value ? 'text-violet-400' : 'text-slate-400'
                }`}
              >
                {opt.value === value && <Check className="w-2.5 h-2.5 flex-shrink-0" />}
                {opt.value !== value && <span className="w-2.5" />}
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface VoiceStatus {
  voice_mode?: string
  running?: boolean
  tts_available?: boolean
  stt_available?: boolean
  fsm_state?: string
  modules_loaded?: string[]
  latency_ms?: number
  confidence?: number
  current_input_device?: string | null
  current_output_device?: string | null
  // Pipeline model details
  stt_provider?: string
  stt_model?: string
  llm_tier?: string
  llm_model?: string
  tts_engine?: string
  tts_voice?: string
  vad_threshold?: number
}

interface TranscriptEntry {
  speaker: 'user' | 'emily'
  text: string
  confidence?: number
  ts: number
}

interface DeviceInfo {
  index: number
  name: string
  hostapi: string
  is_default_input: boolean
  is_default_output: boolean
}

interface DeviceList {
  input_devices: DeviceInfo[]
  output_devices: DeviceInfo[]
  current_input: string | null
  current_output: string | null
}

// ── Which pipeline stages glow for each FSM state ──────────────
const FSM_ACTIVE_STAGES: Record<string, string[]> = {
  LOADING:    ['mic', 'vad', 'stt', 'llm', 'tts', 'spk'],
  LISTENING:  ['mic', 'vad'],
  PROCESSING: ['stt', 'llm'],
  FILLING:    ['stt', 'llm'],
  SPEAKING:   ['tts', 'spk'],
  INTERRUPTED:['mic', 'vad'],
  IDLE:       [],
}

// ── Animated oscilloscope waveform ──────────────────────────────
function WaveformCanvas({ active, fsm }: { active: boolean; fsm: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const frameRef = useRef<number>(0)
  const phaseRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    const draw = () => {
      const W = canvas.width
      const H = canvas.height
      ctx.clearRect(0, 0, W, H)

      ctx.strokeStyle = 'rgba(99,102,241,0.06)'
      ctx.lineWidth = 1
      for (let x = 0; x < W; x += 20) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
      }
      for (let y = 0; y < H; y += 10) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
      }

      ctx.strokeStyle = 'rgba(99,102,241,0.15)'
      ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke()

      if (active) {
        const grad = ctx.createLinearGradient(0, 0, W, 0)
        const color = fsm === 'LISTENING' ? '6,182,212' : fsm === 'SPEAKING' ? '52,211,153' : '99,102,241'
        grad.addColorStop(0, `rgba(${color},0)`)
        grad.addColorStop(0.3, `rgba(${color},0.8)`)
        grad.addColorStop(0.7, `rgba(${color},0.8)`)
        grad.addColorStop(1, `rgba(${color},0)`)

        ctx.shadowColor = `rgba(${color},0.6)`
        ctx.shadowBlur = 8
        ctx.strokeStyle = grad
        ctx.lineWidth = 2
        ctx.beginPath()
        for (let x = 0; x <= W; x++) {
          const t = x / W
          const noise = (Math.random() - 0.5) * 0.18
          const y = H / 2 + Math.sin(t * Math.PI * 6 + phaseRef.current) * H * 0.28
            + Math.sin(t * Math.PI * 14 + phaseRef.current * 1.7) * H * 0.12
            + noise * H
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.stroke()
        ctx.shadowBlur = 0

        ctx.globalAlpha = 0.3
        ctx.strokeStyle = `rgba(${color},0.4)`
        ctx.lineWidth = 1
        ctx.beginPath()
        for (let x = 0; x <= W; x++) {
          const t = x / W
          const y = H / 2 + Math.sin(t * Math.PI * 9 + phaseRef.current * 2.1 + 1) * H * 0.15
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.stroke()
        ctx.globalAlpha = 1
        phaseRef.current += 0.08
      } else {
        ctx.strokeStyle = 'rgba(99,102,241,0.3)'
        ctx.lineWidth = 1.5
        ctx.beginPath()
        for (let x = 0; x <= W; x++) {
          const t = x / W
          const y = H / 2 + Math.sin(t * Math.PI * 2 + phaseRef.current * 0.2) * H * 0.02
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.stroke()
        phaseRef.current += 0.005
      }

      frameRef.current = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(frameRef.current)
  }, [active, fsm])

  return (
    <canvas
      ref={canvasRef}
      width={480}
      height={80}
      className="w-full rounded-lg border border-white/5 bg-black/40"
      style={{ imageRendering: 'crisp-edges' }}
    />
  )
}

// ── Pipeline node ────────────────────────────────────────────────
interface PipelineNodeProps {
  id: string
  label: string
  sublabel?: string
  detail?: string
  icon: React.ReactNode
  active: boolean
  color: 'cyan' | 'violet' | 'emerald' | 'amber' | 'slate'
  loading?: boolean
}

function PipelineNode({ label, sublabel, detail, icon, active, color, loading }: PipelineNodeProps) {
  const palette: Record<string, { border: string; bg: string; text: string; glow: string; dim: string }> = {
    cyan:    { border: 'border-cyan-500/50',    bg: 'bg-cyan-500/10',    text: 'text-cyan-300',    glow: 'shadow-[0_0_16px_rgba(6,182,212,0.4)]',    dim: 'border-cyan-900/30 bg-cyan-950/20 text-cyan-800' },
    violet:  { border: 'border-violet-500/50',  bg: 'bg-violet-500/10',  text: 'text-violet-300',  glow: 'shadow-[0_0_16px_rgba(124,58,237,0.4)]',   dim: 'border-violet-900/30 bg-violet-950/20 text-violet-800' },
    emerald: { border: 'border-emerald-500/50', bg: 'bg-emerald-500/10', text: 'text-emerald-300', glow: 'shadow-[0_0_16px_rgba(52,211,153,0.4)]',   dim: 'border-emerald-900/30 bg-emerald-950/20 text-emerald-800' },
    amber:   { border: 'border-amber-500/50',   bg: 'bg-amber-500/10',   text: 'text-amber-300',   glow: 'shadow-[0_0_16px_rgba(251,191,36,0.4)]',   dim: 'border-amber-900/30 bg-amber-950/20 text-amber-800' },
    slate:   { border: 'border-slate-500/50',   bg: 'bg-slate-500/10',   text: 'text-slate-300',   glow: 'shadow-[0_0_12px_rgba(148,163,184,0.3)]',  dim: 'border-slate-800/30 bg-slate-900/20 text-slate-700' },
  }
  const p = palette[color]
  const cls = active
    ? `border ${p.border} ${p.bg} ${p.text} ${p.glow}`
    : `border border-white/5 bg-black/20 text-slate-700`

  return (
    <div className={`relative flex flex-col items-center gap-1 px-3 py-2.5 rounded-xl transition-all duration-300 min-w-[90px] ${cls}`}>
      {loading && active && (
        <div className="absolute inset-0 rounded-xl overflow-hidden pointer-events-none">
          <div className="absolute inset-0 animate-pulse opacity-20"
            style={{ background: `radial-gradient(circle, ${color === 'cyan' ? '#06b6d4' : color === 'violet' ? '#7c3aed' : '#34d399'} 0%, transparent 70%)` }} />
        </div>
      )}
      <div className={`transition-all ${active ? 'opacity-100' : 'opacity-25'}`}>{icon}</div>
      <span className={`text-[9px] font-mono font-bold uppercase tracking-widest leading-none ${active ? '' : 'text-slate-700'}`}>{label}</span>
      {sublabel && (
        <span className={`text-[8px] font-mono leading-none ${active ? 'opacity-70' : 'text-slate-800'}`}>{sublabel}</span>
      )}
      {detail && (
        <span className={`text-[7.5px] font-mono leading-none truncate max-w-[88px] text-center ${active ? 'opacity-50' : 'text-slate-900'}`}
          title={detail}>{detail.length > 12 ? detail.slice(0, 11) + '…' : detail}</span>
      )}
    </div>
  )
}

// ── Pipeline arrow ───────────────────────────────────────────────
function Arrow({ active }: { active: boolean }) {
  return (
    <ChevronRight
      className={`w-3 h-3 flex-shrink-0 transition-all duration-300 ${active ? 'text-white/40' : 'text-white/10'}`}
    />
  )
}

// ── Full pipeline flow ───────────────────────────────────────────
function PipelineFlow({ status, listening }: { status: VoiceStatus | null; listening: boolean }) {
  const fsm = status?.fsm_state || 'IDLE'
  const active = FSM_ACTIVE_STAGES[fsm] ?? []
  const loading = fsm === 'LOADING'

  const isActive = (id: string) => active.includes(id)
  const between = (a: string, b: string) => isActive(a) || isActive(b)

  // Derive nice display names
  const sttLabel = status?.stt_provider === 'faster_whisper' ? 'FasterWhisper' : (status?.stt_provider ?? 'STT')
  const sttDetail = status?.stt_model ?? 'base.en'
  const vadDetail = status?.vad_threshold != null ? `thr ${status.vad_threshold}` : '0.5'
  const llmTier = status?.llm_tier ?? 'voice_fast'
  const llmModel = status?.llm_model
  // shorten model name: "goekdenizguelmez/JOSIEFIED-Qwen3:8b" → "JOSIEFIED-Qwen3:8b"
  const llmShort = llmModel ? llmModel.split('/').pop() ?? llmModel : '—'
  const ttsLabel = status?.tts_engine ?? 'kokoro'
  const ttsDetail = status?.tts_voice ?? 'af_heart'

  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1 min-w-0 scrollbar-hide">
      {/* MIC */}
      <PipelineNode id="mic" label="MIC" sublabel="input" icon={<MicVocal className="w-4 h-4" />}
        active={isActive('mic') || listening} color="cyan" loading={loading} />
      <Arrow active={between('mic', 'vad')} />
      {/* Silero VAD */}
      <PipelineNode id="vad" label="VAD" sublabel="Silero" detail={vadDetail}
        icon={<Waves className="w-4 h-4" />} active={isActive('vad')} color="cyan" loading={loading} />
      <Arrow active={between('vad', 'stt')} />
      {/* STT */}
      <PipelineNode id="stt" label="STT" sublabel={sttLabel} detail={sttDetail}
        icon={<Cpu className="w-4 h-4" />} active={isActive('stt')} color="violet" loading={loading} />
      <Arrow active={between('stt', 'llm')} />
      {/* LLM */}
      <PipelineNode id="llm" label={llmTier.toUpperCase()} sublabel="LLM" detail={llmShort}
        icon={<Brain className="w-4 h-4" />} active={isActive('llm')} color="violet" loading={loading} />
      <Arrow active={between('llm', 'tts')} />
      {/* TTS */}
      <PipelineNode id="tts" label={ttsLabel.toUpperCase()} sublabel="TTS" detail={ttsDetail}
        icon={<Volume2 className="w-4 h-4" />} active={isActive('tts')} color="emerald" loading={loading} />
      <Arrow active={between('tts', 'spk')} />
      {/* Speaker */}
      <PipelineNode id="spk" label="SPK" sublabel="output" icon={<Speaker className="w-4 h-4" />}
        active={isActive('spk')} color="emerald" loading={loading} />
    </div>
  )
}

// ── Model info card ──────────────────────────────────────────────
function ModelCard({ stage, model, provider, voice, active }: {
  stage: string; model?: string; provider?: string; voice?: string; active: boolean
}) {
  return (
    <div className={`rounded-xl border p-2.5 transition-all duration-300 ${
      active ? 'border-violet-500/25 bg-violet-500/5' : 'border-white/5 bg-black/20'
    }`}>
      <div className={`text-[8px] font-mono uppercase tracking-widest mb-1 ${active ? 'text-violet-500' : 'text-slate-700'}`}>{stage}</div>
      <div className={`font-mono text-xs font-semibold truncate ${active ? 'text-slate-200' : 'text-slate-600'}`} title={model}>
        {model ?? '—'}
      </div>
      {provider && (
        <div className={`font-mono text-[9px] mt-0.5 ${active ? 'text-slate-500' : 'text-slate-800'}`}>{provider}</div>
      )}
      {voice && (
        <div className={`font-mono text-[9px] ${active ? 'text-emerald-500' : 'text-slate-800'}`}>voice: {voice}</div>
      )}
    </div>
  )
}

// ── Metric card ─────────────────────────────────────────────────
function MetricCard({ icon: Icon, label, value, unit, color = 'cyan' }: {
  icon: any; label: string; value: string | number; unit?: string; color?: string
}) {
  const colors: Record<string, string> = {
    cyan: 'text-cyan-400 border-cyan-500/20 bg-cyan-500/5',
    emerald: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5',
    violet: 'text-violet-400 border-violet-500/20 bg-violet-500/5',
    amber: 'text-amber-400 border-amber-500/20 bg-amber-500/5',
  }
  return (
    <div className={`rounded-xl border p-3 ${colors[color]}`}>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="w-3 h-3 opacity-70" />
        <span className="text-[9px] uppercase tracking-widest opacity-60 font-semibold">{label}</span>
      </div>
      <div className="font-mono text-lg font-bold leading-none">
        {value}
        {unit && <span className="text-[10px] opacity-50 ml-1 font-normal">{unit}</span>}
      </div>
    </div>
  )
}

// ── Module pill ─────────────────────────────────────────────────
function ModulePill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-mono font-semibold border
      ${ok ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-400' : 'bg-red-500/10 border-red-500/25 text-red-400'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`} />
      {label}
    </div>
  )
}

// ── FSM state badge ─────────────────────────────────────────────
function FsmBadge({ state }: { state: string }) {
  const styles: Record<string, string> = {
    IDLE: 'text-slate-400 border-slate-600 bg-slate-800/50',
    LISTENING: 'text-cyan-300 border-cyan-500/40 bg-cyan-500/10 animate-pulse',
    PROCESSING: 'text-violet-300 border-violet-500/40 bg-violet-500/10',
    SPEAKING: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10',
    INTERRUPTED: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
    FILLING: 'text-sky-300 border-sky-500/40 bg-sky-500/10',
    LOADING: 'text-slate-300 border-slate-500/40 bg-slate-500/10 animate-pulse',
  }
  return (
    <span className={`px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold border tracking-widest ${styles[state] ?? styles.IDLE}`}>
      {state}
    </span>
  )
}

// ── Audio device row (input — display only) ──────────────────────
function DeviceRow({ direction, deviceName }: { direction: string; deviceName: string | null | undefined }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-[9px] font-mono uppercase tracking-widest text-slate-600 w-14 flex-shrink-0">{direction}</span>
      <span className="text-[10px] font-mono text-slate-400 truncate" title={deviceName ?? undefined}>
        {deviceName && deviceName !== 'None' ? deviceName : 'system default'}
      </span>
    </div>
  )
}

// ── Output device picker (interactive) ───────────────────────────
function OutputDevicePicker({
  outputDevices,
  currentOutputIdx,
  onSwitch,
}: {
  outputDevices: DeviceInfo[]
  currentOutputIdx: string | null | undefined
  onSwitch: (idx: number) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const current = outputDevices.find(d => String(d.index) === currentOutputIdx)
  const label = current?.name ?? (currentOutputIdx && currentOutputIdx !== 'None' ? currentOutputIdx : 'system default')

  const handleSelect = async (idx: number) => {
    setOpen(false)
    setSwitching(true)
    try { await onSwitch(idx) } finally { setSwitching(false) }
  }

  return (
    <div className="relative flex items-center gap-2 min-w-0" ref={ref}>
      <span className="text-[9px] font-mono uppercase tracking-widest text-slate-600 w-14 flex-shrink-0">Output</span>
      <button
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1 text-[10px] font-mono truncate max-w-[180px] rounded px-1.5 py-0.5 transition-colors ${
          switching
            ? 'text-amber-400 animate-pulse'
            : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
        }`}
        title={label}
      >
        <span className="truncate">{switching ? 'switching…' : label}</span>
        <ChevronDown className={`w-2.5 h-2.5 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-14 top-5 z-50 min-w-[200px] max-w-[280px] bg-[#12121f] border border-white/10 rounded-xl shadow-xl overflow-hidden">
          <div className="px-3 py-1.5 border-b border-white/5">
            <span className="text-[9px] font-mono uppercase tracking-widest text-slate-600">Output Device</span>
          </div>
          <div className="max-h-48 overflow-y-auto py-1">
            {outputDevices.length === 0 ? (
              <div className="px-3 py-2 text-[10px] font-mono text-slate-600">No output devices found</div>
            ) : (
              outputDevices.map(d => (
                <button
                  key={d.index}
                  onClick={() => handleSelect(d.index)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-white/5 transition-colors group"
                >
                  <Check
                    className={`w-2.5 h-2.5 flex-shrink-0 ${String(d.index) === currentOutputIdx ? 'text-emerald-400' : 'opacity-0'}`}
                  />
                  <span className={`text-[10px] font-mono truncate ${String(d.index) === currentOutputIdx ? 'text-slate-200' : 'text-slate-500 group-hover:text-slate-300'}`}>
                    {d.name}
                  </span>
                  {d.is_default_output && (
                    <span className="ml-auto text-[8px] font-mono text-slate-700 flex-shrink-0">default</span>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Transcript row ──────────────────────────────────────────────
function TranscriptRow({ entry }: { entry: TranscriptEntry }) {
  const isUser = entry.speaker === 'user'
  const time = new Date(entry.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const conf = entry.confidence ?? null

  return (
    <div className={`rounded-xl p-3 border ${isUser
      ? 'bg-cyan-500/5 border-cyan-500/15'
      : 'bg-violet-500/5 border-violet-500/15'}`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className={`text-[10px] font-mono font-bold uppercase tracking-widest ${isUser ? 'text-cyan-400' : 'text-violet-400'}`}>
          {isUser ? '● USER' : '◆ EMILY'}
        </span>
        <span className="text-[9px] text-slate-600 font-mono">{time}</span>
      </div>
      <p className="text-sm text-slate-200 leading-relaxed">{entry.text}</p>
      {conf !== null && (
        <div className="mt-2 flex items-center gap-2">
          <div className="flex-1 h-0.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${conf > 0.8 ? 'bg-emerald-500' : conf > 0.5 ? 'bg-amber-500' : 'bg-red-500'}`}
              style={{ width: `${conf * 100}%` }}
            />
          </div>
          <span className="text-[9px] font-mono text-slate-500">{(conf * 100).toFixed(0)}%</span>
        </div>
      )}
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────
export function VoicePage() {
  const [status, setStatus] = useState<VoiceStatus | null>(null)
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [devices, setDevices] = useState<DeviceList | null>(null)
  const [voices, setVoices] = useState<string[]>([])
  const [selectedVoice, setSelectedVoice] = useState('')
  const [speed, setSpeed] = useState(100)
  const [ttsText, setTtsText] = useState('')
  const [wordCount, setWordCount] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Poll status + transcript every 2s
  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API_RAW}/audio/voice/status`)
        if (res.ok) setStatus(await res.json())
      } catch {}
      try {
        const res = await fetch(`${API_RAW}/audio/voice/transcript`)
        if (res.ok) {
          const data = await res.json()
          const logs: any[] = data.entries || []
          const entries: TranscriptEntry[] = logs
            .filter((l) => l.text)
            .map((l) => ({
              speaker: l.event === 'stt_result' ? 'user' as const : 'emily' as const,
              text: l.text,
              confidence: l.confidence,
              ts: l.timestamp ? new Date(l.timestamp).getTime() : Date.now(),
            }))
          if (entries.length > 0) {
            setTranscript(entries)
            setWordCount(entries.reduce((n, e) => n + e.text.split(' ').length, 0))
          }
        }
      } catch {}
    }, 2000)
    return () => clearInterval(poll)
  }, [])

  // Fetch audio devices once
  useEffect(() => {
    fetch(`${API_RAW}/audio/devices`).then(r => r.ok ? r.json() : null).then(d => {
      if (d) setDevices(d)
    }).catch(() => {})
    fetch(`${API_RAW}/audio/voice/voices`).then(r => r.ok ? r.json() : null).then(v => {
      if (v?.voices?.kokoro) {
        setVoices(v.voices.kokoro.map((x: any) => x.id))
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [transcript])

  const toggleListening = useCallback(async () => {
    const next = !listening
    try {
      await fetch(next ? `${API_RAW}/audio/voice/start` : `${API_RAW}/audio/voice/stop`, { method: 'POST' })
      setListening(next)
    } catch {
      setListening(next)
    }
  }, [listening])

  const testTts = useCallback(async () => {
    if (!ttsText.trim()) return
    try {
      await fetch(`${API_RAW}/audio/voice/test-tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: ttsText, engine: selectedVoice || undefined }),
      })
    } catch {}
  }, [ttsText, selectedVoice])

  const switchVoice = useCallback(async (voiceId: string) => {
    setSelectedVoice(voiceId)
    try {
      await fetch(`${API_RAW}/audio/voice/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice: voiceId || (status?.tts_voice ?? 'af_heart') }),
      })
    } catch {}
  }, [status?.tts_voice])

  const switchOutputDevice = useCallback(async (idx: number) => {
    try {
      const res = await fetch(`${API_RAW}/audio/devices/output`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device: idx }),
      })
      if (res.ok) {
        setDevices(prev => prev ? { ...prev, current_output: String(idx) } : prev)
      }
    } catch {}
  }, [])

  const fsmState = status?.fsm_state || 'IDLE'
  const isRunning = status?.running || false
  const apiConnected = status !== null
  const latency = status?.latency_ms

  // Resolve human-readable device names from the devices list
  const resolveDevice = (idx: string | null | undefined, list: DeviceInfo[]) => {
    if (!idx || idx === 'None') return null
    const byIdx = list.find(d => String(d.index) === idx)
    return byIdx?.name ?? idx
  }
  const inputName = devices
    ? resolveDevice(status?.current_input_device, devices.input_devices)
    : status?.current_input_device
  const outputName = devices
    ? resolveDevice(status?.current_output_device, devices.output_devices)
    : status?.current_output_device

  // Model cards — which stage is "active" right now
  const activeStages = FSM_ACTIVE_STAGES[fsmState] ?? []
  const sttActive = activeStages.includes('stt')
  const llmActive = activeStages.includes('llm')
  const ttsActive = activeStages.includes('tts')

  const llmModelDisplay = status?.llm_model
    ? (status.llm_model.split('/').pop() ?? status.llm_model)
    : '—'

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-[#08080f]">

      {/* ── Top bar ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 bg-black/30 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full transition-colors ${apiConnected ? 'bg-emerald-400 shadow-[0_0_6px_#34d399]' : 'bg-red-500 animate-pulse'}`} />
            <span className={`text-[10px] font-mono uppercase tracking-widest ${apiConnected ? 'text-emerald-500' : 'text-red-500'}`}>
              {apiConnected ? 'Connected' : 'Offline'}
            </span>
          </div>
          <div className="flex items-center gap-1.5 pl-1 border-l border-white/5">
            <span className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-cyan-400 animate-pulse' : 'bg-slate-700'}`} />
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">Engine</span>
          </div>
          <FsmBadge state={fsmState} />
        </div>

        <div className="flex items-center gap-2 text-[10px] font-mono">
          {status?.voice_mode && (
            <span className="text-slate-600 uppercase tracking-widest">{status.voice_mode.replace('_', ' ')}</span>
          )}
          <span className="text-slate-700">|</span>
          <Clock className="w-3 h-3 text-slate-600" />
          <span className={latency != null ? 'text-amber-400' : 'text-slate-600'}>
            {latency != null ? `${latency.toFixed(0)} ms` : '-- ms'}
          </span>
        </div>
      </div>

      {/* ── Body ────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* Left panel — controls */}
        <div className="w-72 border-r border-white/5 flex flex-col gap-4 p-4 overflow-y-auto flex-shrink-0">

          <WaveformCanvas active={listening} fsm={fsmState} />

          <button
            onClick={toggleListening}
            className={`flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold text-sm transition-all
              ${listening
                ? 'bg-red-500/15 border border-red-500/30 text-red-400 hover:bg-red-500/25 shadow-[0_0_20px_rgba(239,68,68,0.1)]'
                : 'bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/25 shadow-[0_0_20px_rgba(6,182,212,0.1)]'}`}
          >
            {listening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            {listening ? 'Stop Listening' : 'Start Listening'}
          </button>

          {/* Metrics grid */}
          <div className="grid grid-cols-2 gap-2">
            <MetricCard icon={Activity} label="State" value={fsmState} color="cyan" />
            <MetricCard icon={Zap} label="Latency" value={latency?.toFixed(0) ?? '--'} unit="ms" color="amber" />
            <MetricCard icon={Cpu} label="Words" value={wordCount} color="violet" />
            <MetricCard icon={Radio} label="Mode" value={status?.voice_mode?.replace('_', ' ') ?? '--'} color="emerald" />
          </div>

          {/* Modules */}
          <div>
            <p className="text-[9px] font-mono uppercase tracking-widest text-slate-600 mb-2">Pipeline Modules</p>
            <div className="flex flex-wrap gap-1.5">
              <ModulePill label="STT" ok={status?.stt_available ?? false} />
              <ModulePill label="TTS" ok={status?.tts_available ?? false} />
              {(status?.modules_loaded ?? []).map(m => (
                <ModulePill key={m} label={m} ok />
              ))}
            </div>
          </div>

          {/* TTS settings */}
          <div className="border-t border-white/5 pt-3">
            <p className="text-[9px] font-mono uppercase tracking-widest text-slate-600 mb-2">TTS Test</p>
            <div className="bg-black rounded-xl p-3 space-y-3">
            <div>
              <label className="text-[10px] text-slate-500 mb-1.5 block font-mono">Voice</label>
              <VoiceDropdown
                value={selectedVoice}
                onChange={switchVoice}
                options={[
                  { value: '', label: `Default (${status?.tts_voice ?? 'af_heart'})` },
                  ...voices.map(v => ({ value: v, label: v })),
                ]}
              />
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <label className="text-[10px] text-slate-500 font-mono">Speed</label>
                <span className="text-[10px] font-mono text-violet-400">{(speed / 100).toFixed(2)}×</span>
              </div>
              <input
                type="range" min={50} max={200} value={speed}
                onChange={e => setSpeed(Number(e.target.value))}
                className="w-full h-1 appearance-none bg-slate-800 rounded-full accent-violet-500"
              />
            </div>
            <div className="flex gap-2">
              <input
                value={ttsText}
                onChange={e => setTtsText(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && testTts()}
                placeholder="Test synthesis…"
                className="flex-1 bg-black border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300
                  font-mono placeholder:text-slate-700 focus:outline-none focus:border-violet-500/50"
              />
              <button
                onClick={testTts}
                className="p-1.5 rounded-lg bg-violet-600/20 border border-violet-500/25 text-violet-400 hover:bg-violet-600/30"
              >
                <Volume2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
        </div>

        {/* Right panel */}
        <div className="flex-1 flex flex-col min-w-0">

          {/* ── Pipeline flow section ─────────────────────── */}
          <div className="border-b border-white/5 px-4 py-3 flex-shrink-0 space-y-3">

            <div className="flex items-center gap-2 mb-1">
              <Waves className="w-3.5 h-3.5 text-slate-600" />
              <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">Voice Pipeline</span>
            </div>

            {/* Node flow */}
            <PipelineFlow status={status} listening={listening} />

            {/* Model detail row */}
            <div className="grid grid-cols-3 gap-2">
              <ModelCard
                stage="STT · Speech→Text"
                model={`${status?.stt_provider ?? 'faster_whisper'} ${status?.stt_model ?? 'base.en'}`}
                provider={`VAD thr: ${status?.vad_threshold ?? 0.5} · Silero`}
                active={sttActive}
              />
              <ModelCard
                stage={`LLM · ${status?.llm_tier ?? 'voice_fast'} tier`}
                model={llmModelDisplay}
                provider={`ollama · temp 0.7`}
                active={llmActive}
              />
              <ModelCard
                stage="TTS · Text→Speech"
                model={status?.tts_engine ?? 'kokoro'}
                provider="local · af_heart"
                voice={status?.tts_voice ?? 'af_heart'}
                active={ttsActive}
              />
            </div>

            {/* Audio device strip */}
            <div className="flex items-center gap-6 px-1">
              <DeviceRow direction="Input" deviceName={inputName} />
              <div className="w-px h-3 bg-white/5" />
              <OutputDevicePicker
                outputDevices={devices?.output_devices ?? []}
                currentOutputIdx={status?.current_output_device ?? devices?.current_output}
                onSwitch={switchOutputDevice}
              />
            </div>
          </div>

          {/* ── Transcript ───────────────────────────────── */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 flex-shrink-0">
            <div className="flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-slate-600" />
              <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">Live Transcript</span>
              <span className="text-[9px] font-mono text-slate-700">{transcript.length} entries · {wordCount} words</span>
            </div>
            <button
              onClick={() => { setTranscript([]); setWordCount(0) }}
              className="p-1 rounded-lg hover:bg-white/5 text-slate-700 hover:text-slate-400 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2">
            {transcript.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-700">
                <Radio className="w-8 h-8 opacity-30" />
                <p className="text-xs font-mono">No transcript yet — start listening</p>
              </div>
            ) : (
              transcript.map((entry, i) => <TranscriptRow key={i} entry={entry} />)
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
