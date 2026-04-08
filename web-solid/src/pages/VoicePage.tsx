import { createSignal, createEffect, createMemo, onMount, onCleanup, For, Show, type Component } from 'solid-js'
import { API_RAW } from '../lib/env'
import {
  Mic, MicOff, Volume2, Trash2, Radio, Cpu, Zap, Clock,
  Activity, Waves, Brain, Speaker, ChevronRight, MicVocal, ChevronDown, Check,
} from 'lucide-solid'

// ── Custom dropdown (native <select> broken in WebKitGTK/Tauri) ─────────────

function VoiceDropdown(props: {
  value: string
  options: { value: string; label: string }[]
  onChange: (v: string) => void
}) {
  const [open, setOpen] = createSignal(false)
  let ref: HTMLDivElement | undefined

  createEffect(() => {
    if (!open()) return
    const handler = (e: MouseEvent) => {
      if (ref && !ref.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    onCleanup(() => document.removeEventListener('mousedown', handler))
  })

  const selected = createMemo(() => props.options.find(o => o.value === props.value))

  return (
    <div ref={ref} class="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        class="w-full flex items-center justify-between bg-black border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 font-mono hover:border-[oklch(0.72_0.17_162/0.40)] transition-colors"
      >
        <span>{selected()?.label ?? 'Default'}</span>
        <ChevronDown class={`w-3 h-3 text-slate-600 transition-transform flex-shrink-0 ml-1 ${open() ? 'rotate-180' : ''}`} />
      </button>
      <Show when={open()}>
        <div class="absolute z-50 w-full mt-1 bg-surface border border-white/10 rounded-xl shadow-2xl overflow-hidden">
          <div class="max-h-48 overflow-y-auto py-1">
            <For each={props.options}>{(opt) => (
              <button
                type="button"
                onClick={() => { props.onChange(opt.value); setOpen(false) }}
                class={`w-full text-left flex items-center gap-2 px-3 py-1.5 text-xs font-mono transition-colors hover:bg-white/5 ${
                  opt.value === props.value ? 'text-[oklch(0.72_0.17_162)]' : 'text-slate-400'
                }`}
              >
                <Show when={opt.value === props.value} fallback={<span class="w-2.5" />}>
                  <Check class="w-2.5 h-2.5 flex-shrink-0" />
                </Show>
                {opt.label}
              </button>
            )}</For>
          </div>
        </div>
      </Show>
    </div>
  )
}

// ── Types ────────────────────────────────────────────────────────────────────

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

// ── FSM active stages ───────────────────────────────────────────────────────

const FSM_ACTIVE_STAGES: Record<string, string[]> = {
  LOADING:     ['mic', 'vad', 'stt', 'llm', 'tts', 'spk'],
  LISTENING:   ['mic', 'vad'],
  PROCESSING:  ['stt', 'llm'],
  FILLING:     ['stt', 'llm'],
  SPEAKING:    ['tts', 'spk'],
  INTERRUPTED: ['mic', 'vad'],
  IDLE:        [],
}

// ── Waveform canvas ─────────────────────────────────────────────────────────

function WaveformCanvas(props: { active: boolean; fsm: string }) {
  let canvasRef: HTMLCanvasElement | undefined
  let frameId = 0
  let phase = 0

  onMount(() => {
    const canvas = canvasRef
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    const draw = () => {
      const W = canvas.width
      const H = canvas.height
      ctx.clearRect(0, 0, W, H)

      ctx.strokeStyle = 'rgba(20,184,166,0.06)'
      ctx.lineWidth = 1
      for (let x = 0; x < W; x += 20) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
      }
      for (let y = 0; y < H; y += 10) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
      }

      ctx.strokeStyle = 'rgba(20,184,166,0.15)'
      ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke()

      if (props.active) {
        const grad = ctx.createLinearGradient(0, 0, W, 0)
        const color = props.fsm === 'LISTENING' ? '6,182,212' : props.fsm === 'SPEAKING' ? '52,211,153' : '20,184,166'
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
          const y = H / 2 + Math.sin(t * Math.PI * 6 + phase) * H * 0.28
            + Math.sin(t * Math.PI * 14 + phase * 1.7) * H * 0.12
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
          const y = H / 2 + Math.sin(t * Math.PI * 9 + phase * 2.1 + 1) * H * 0.15
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.stroke()
        ctx.globalAlpha = 1
        phase += 0.08
      } else {
        ctx.strokeStyle = 'rgba(20,184,166,0.3)'
        ctx.lineWidth = 1.5
        ctx.beginPath()
        for (let x = 0; x <= W; x++) {
          const t = x / W
          const y = H / 2 + Math.sin(t * Math.PI * 2 + phase * 0.2) * H * 0.02
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.stroke()
        phase += 0.005
      }

      frameId = requestAnimationFrame(draw)
    }

    draw()
    onCleanup(() => cancelAnimationFrame(frameId))
  })

  return (
    <canvas
      ref={canvasRef}
      width={480}
      height={80}
      class="w-full rounded-lg border border-white/5 bg-black/40"
      style={{ 'image-rendering': 'crisp-edges' }}
    />
  )
}

// ── Pipeline node ───────────────────────────────────────────────────────────

interface PipelineNodeProps {
  id: string
  label: string
  sublabel?: string
  detail?: string
  icon: Component<{ class?: string }>
  active: boolean
  color: 'cyan' | 'violet' | 'emerald' | 'amber' | 'slate'
  loading?: boolean
}

function PipelineNode(props: PipelineNodeProps) {
  const palette: Record<string, { border: string; bg: string; text: string; glow: string }> = {
    cyan:    { border: 'border-cyan-500/50',    bg: 'bg-cyan-500/10',    text: 'text-cyan-300',    glow: 'shadow-[0_0_16px_rgba(6,182,212,0.4)]' },
    violet:  { border: 'border-teal-500/50',    bg: 'bg-teal-500/10',    text: 'text-teal-300',    glow: 'shadow-[0_0_16px_rgba(20,184,166,0.4)]' },
    emerald: { border: 'border-emerald-500/50', bg: 'bg-emerald-500/10', text: 'text-emerald-300', glow: 'shadow-[0_0_16px_rgba(52,211,153,0.4)]' },
    amber:   { border: 'border-amber-500/50',   bg: 'bg-amber-500/10',   text: 'text-amber-300',   glow: 'shadow-[0_0_16px_rgba(251,191,36,0.4)]' },
    slate:   { border: 'border-slate-500/50',   bg: 'bg-slate-500/10',   text: 'text-slate-300',   glow: 'shadow-[0_0_12px_rgba(148,163,184,0.3)]' },
  }
  const p = palette[props.color]
  const cls = () => props.active
    ? `border ${p.border} ${p.bg} ${p.text} ${p.glow}`
    : 'border border-white/5 bg-black/20 text-slate-700'

  const Icon = props.icon

  return (
    <div class={`relative flex flex-col items-center gap-1 px-3 py-2.5 rounded-xl transition-all duration-300 min-w-[90px] ${cls()}`}>
      <Show when={props.loading && props.active}>
        <div class="absolute inset-0 rounded-xl overflow-hidden pointer-events-none">
          <div class="absolute inset-0 animate-pulse opacity-20"
            style={{ background: 'radial-gradient(circle, var(--color-accent) 0%, transparent 70%)' }} />
        </div>
      </Show>
      <div class={`transition-all ${props.active ? 'opacity-100' : 'opacity-25'}`}>
        <Icon class="w-4 h-4" />
      </div>
      <span class={`text-[9px] font-mono font-bold uppercase tracking-widest leading-none ${props.active ? '' : 'text-slate-700'}`}>{props.label}</span>
      <Show when={props.sublabel}>
        <span class={`text-[8px] font-mono leading-none ${props.active ? 'opacity-70' : 'text-slate-800'}`}>{props.sublabel}</span>
      </Show>
      <Show when={props.detail}>
        <span
          class={`text-[7.5px] font-mono leading-none truncate max-w-[88px] text-center ${props.active ? 'opacity-50' : 'text-slate-900'}`}
          title={props.detail}
        >
          {(props.detail?.length ?? 0) > 12 ? props.detail!.slice(0, 11) + '\u2026' : props.detail}
        </span>
      </Show>
    </div>
  )
}

// ── Pipeline arrow ──────────────────────────────────────────────────────────

function Arrow(props: { active: boolean }) {
  return (
    <ChevronRight
      class={`w-3 h-3 flex-shrink-0 transition-all duration-300 ${props.active ? 'text-white/40' : 'text-white/10'}`}
    />
  )
}

// ── Full pipeline flow ──────────────────────────────────────────────────────

function PipelineFlow(props: { status: VoiceStatus | null; listening: boolean }) {
  const fsm = () => props.status?.fsm_state || 'IDLE'
  const active = () => FSM_ACTIVE_STAGES[fsm()] ?? []
  const loading = () => fsm() === 'LOADING'

  const isActive = (id: string) => active().includes(id)
  const between = (a: string, b: string) => isActive(a) || isActive(b)

  const sttLabel = () => props.status?.stt_provider === 'faster_whisper' ? 'FasterWhisper' : (props.status?.stt_provider ?? 'STT')
  const sttDetail = () => props.status?.stt_model ?? 'base.en'
  const vadDetail = () => props.status?.vad_threshold != null ? `thr ${props.status!.vad_threshold}` : '0.5'
  const llmTier = () => props.status?.llm_tier ?? 'voice_fast'
  const llmModel = () => props.status?.llm_model
  const llmShort = () => {
    const m = llmModel()
    return m ? m.split('/').pop() ?? m : '\u2014'
  }
  const ttsLabel = () => props.status?.tts_engine ?? 'kokoro'
  const ttsDetail = () => props.status?.tts_voice ?? 'af_heart'

  return (
    <div class="flex items-center gap-1 overflow-x-auto pb-1 min-w-0 scrollbar-hide">
      <PipelineNode id="mic" label="MIC" sublabel="input" icon={MicVocal}
        active={isActive('mic') || props.listening} color="cyan" loading={loading()} />
      <Arrow active={between('mic', 'vad')} />
      <PipelineNode id="vad" label="VAD" sublabel="Silero" detail={vadDetail()}
        icon={Waves} active={isActive('vad')} color="cyan" loading={loading()} />
      <Arrow active={between('vad', 'stt')} />
      <PipelineNode id="stt" label="STT" sublabel={sttLabel()} detail={sttDetail()}
        icon={Cpu} active={isActive('stt')} color="violet" loading={loading()} />
      <Arrow active={between('stt', 'llm')} />
      <PipelineNode id="llm" label={llmTier().toUpperCase()} sublabel="LLM" detail={llmShort()}
        icon={Brain} active={isActive('llm')} color="violet" loading={loading()} />
      <Arrow active={between('llm', 'tts')} />
      <PipelineNode id="tts" label={ttsLabel().toUpperCase()} sublabel="TTS" detail={ttsDetail()}
        icon={Volume2} active={isActive('tts')} color="emerald" loading={loading()} />
      <Arrow active={between('tts', 'spk')} />
      <PipelineNode id="spk" label="SPK" sublabel="output" icon={Speaker}
        active={isActive('spk')} color="emerald" loading={loading()} />
    </div>
  )
}

// ── Model info card ─────────────────────────────────────────────────────────

function ModelCard(props: {
  stage: string; model?: string; provider?: string; voice?: string; active: boolean
}) {
  return (
    <div class={`rounded-xl border p-2.5 transition-all duration-300 ${
      props.active ? 'border-teal-500/25 bg-teal-500/5' : 'border-white/5'
    }`} style={props.active ? {} : { background: 'oklch(0.20 0.02 185)' }}>
      <div class={`text-[8px] font-mono uppercase tracking-widest mb-1 ${props.active ? 'text-teal-400' : 'text-slate-700'}`}>{props.stage}</div>
      <div class={`font-mono text-xs font-semibold truncate ${props.active ? 'text-slate-200' : 'text-slate-600'}`} title={props.model}>
        {props.model ?? '\u2014'}
      </div>
      <Show when={props.provider}>
        <div class={`font-mono text-[9px] mt-0.5 ${props.active ? 'text-slate-500' : 'text-slate-800'}`}>{props.provider}</div>
      </Show>
      <Show when={props.voice}>
        <div class={`font-mono text-[9px] ${props.active ? 'text-emerald-500' : 'text-slate-800'}`}>voice: {props.voice}</div>
      </Show>
    </div>
  )
}

// ── Metric card ─────────────────────────────────────────────────────────────

function MetricCard(props: {
  icon: Component<{ class?: string }>; label: string; value: string | number; unit?: string; color?: string
}) {
  const colors: Record<string, string> = {
    cyan: 'text-cyan-400 border-cyan-500/20 bg-cyan-500/5',
    emerald: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5',
    violet: 'text-teal-400 border-teal-500/20 bg-teal-500/5',
    amber: 'text-amber-400 border-amber-500/20 bg-amber-500/5',
  }
  const Icon = props.icon
  return (
    <div class={`rounded-xl border p-3 ${colors[props.color ?? 'cyan']}`}>
      <div class="flex items-center gap-1.5 mb-1">
        <Icon class="w-3 h-3 opacity-70" />
        <span class="text-[9px] uppercase tracking-widest opacity-60 font-semibold">{props.label}</span>
      </div>
      <div class="font-mono text-lg font-bold leading-none">
        {props.value}
        <Show when={props.unit}>
          <span class="text-[10px] opacity-50 ml-1 font-normal">{props.unit}</span>
        </Show>
      </div>
    </div>
  )
}

// ── Module pill ─────────────────────────────────────────────────────────────

function ModulePill(props: { label: string; ok: boolean }) {
  return (
    <div class={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-mono font-semibold border
      ${props.ok ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-400' : 'bg-red-500/10 border-red-500/25 text-red-400'}`}>
      <span class={`w-1.5 h-1.5 rounded-full ${props.ok ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`} />
      {props.label}
    </div>
  )
}

// ── FSM state badge ─────────────────────────────────────────────────────────

function FsmBadge(props: { state: string }) {
  const styles: Record<string, string> = {
    IDLE: 'text-slate-400 border-slate-600 bg-slate-800/50',
    LISTENING: 'text-cyan-300 border-cyan-500/40 bg-cyan-500/10 animate-pulse',
    PROCESSING: 'text-teal-300 border-teal-500/40 bg-teal-500/10',
    SPEAKING: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10',
    INTERRUPTED: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
    FILLING: 'text-sky-300 border-sky-500/40 bg-sky-500/10',
    LOADING: 'text-slate-300 border-slate-500/40 bg-slate-500/10 animate-pulse',
  }
  return (
    <span class={`px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold border tracking-widest ${styles[props.state] ?? styles.IDLE}`}>
      {props.state}
    </span>
  )
}

// ── Device row (display only) ───────────────────────────────────────────────

function DeviceRow(props: { direction: string; deviceName: string | null | undefined }) {
  return (
    <div class="flex items-center gap-2 min-w-0">
      <span class="text-[9px] font-mono uppercase tracking-widest text-slate-600 w-14 flex-shrink-0">{props.direction}</span>
      <span class="text-[10px] font-mono text-slate-400 truncate" title={props.deviceName ?? undefined}>
        {props.deviceName && props.deviceName !== 'None' ? props.deviceName : 'system default'}
      </span>
    </div>
  )
}

// ── Output device picker ────────────────────────────────────────────────────

function OutputDevicePicker(props: {
  outputDevices: DeviceInfo[]
  currentOutputIdx: string | null | undefined
  onSwitch: (idx: number) => Promise<void>
}) {
  const [open, setOpen] = createSignal(false)
  const [switching, setSwitching] = createSignal(false)
  let ref: HTMLDivElement | undefined

  createEffect(() => {
    if (!open()) return
    const handler = (e: MouseEvent) => {
      if (ref && !ref.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    onCleanup(() => document.removeEventListener('mousedown', handler))
  })

  const current = () => props.outputDevices.find(d => String(d.index) === props.currentOutputIdx)
  const label = () => current()?.name ?? (props.currentOutputIdx && props.currentOutputIdx !== 'None' ? props.currentOutputIdx : 'system default')

  const handleSelect = async (idx: number) => {
    setOpen(false)
    setSwitching(true)
    try { await props.onSwitch(idx) } finally { setSwitching(false) }
  }

  return (
    <div class="relative flex items-center gap-2 min-w-0" ref={ref}>
      <span class="text-[9px] font-mono uppercase tracking-widest text-slate-600 w-14 flex-shrink-0">Output</span>
      <button
        onClick={() => setOpen(o => !o)}
        class={`flex items-center gap-1 text-[10px] font-mono truncate max-w-[180px] rounded px-1.5 py-0.5 transition-colors ${
          switching()
            ? 'text-amber-400 animate-pulse'
            : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
        }`}
        title={label()}
      >
        <span class="truncate">{switching() ? 'switching\u2026' : label()}</span>
        <ChevronDown class={`w-2.5 h-2.5 flex-shrink-0 transition-transform ${open() ? 'rotate-180' : ''}`} />
      </button>

      <Show when={open()}>
        <div class="absolute left-14 top-5 z-50 min-w-[200px] max-w-[280px] bg-surface border border-white/10 rounded-xl shadow-xl overflow-hidden">
          <div class="px-3 py-1.5 border-b border-white/5">
            <span class="text-[9px] font-mono uppercase tracking-widest text-slate-600">Output Device</span>
          </div>
          <div class="max-h-48 overflow-y-auto py-1">
            <Show when={props.outputDevices.length > 0} fallback={
              <div class="px-3 py-2 text-[10px] font-mono text-slate-600">No output devices found</div>
            }>
              <For each={props.outputDevices}>{(d) => (
                <button
                  onClick={() => void handleSelect(d.index)}
                  class="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-white/5 transition-colors group"
                >
                  <Check
                    class={`w-2.5 h-2.5 flex-shrink-0 ${String(d.index) === props.currentOutputIdx ? 'text-emerald-400' : 'opacity-0'}`}
                  />
                  <span class={`text-[10px] font-mono truncate ${String(d.index) === props.currentOutputIdx ? 'text-slate-200' : 'text-slate-500 group-hover:text-slate-300'}`}>
                    {d.name}
                  </span>
                  <Show when={d.is_default_output}>
                    <span class="ml-auto text-[8px] font-mono text-slate-700 flex-shrink-0">default</span>
                  </Show>
                </button>
              )}</For>
            </Show>
          </div>
        </div>
      </Show>
    </div>
  )
}

// ── Transcript row ──────────────────────────────────────────────────────────

function TranscriptRow(props: { entry: TranscriptEntry }) {
  const isUser = () => props.entry.speaker === 'user'
  const time = () => new Date(props.entry.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const conf = () => props.entry.confidence ?? null

  return (
    <div class={`rounded-xl p-3 border ${isUser()
      ? 'bg-cyan-500/5 border-cyan-500/15'
      : 'bg-teal-500/5 border-teal-500/15'}`}>
      <div class="flex items-center justify-between mb-1.5">
        <span class={`text-[10px] font-mono font-bold uppercase tracking-widest ${isUser() ? 'text-cyan-400' : 'text-teal-400'}`}>
          {isUser() ? '\u25CF USER' : '\u25C6 EMILY'}
        </span>
        <span class="text-[9px] text-slate-600 font-mono">{time()}</span>
      </div>
      <p class="text-sm text-slate-200 leading-relaxed">{props.entry.text}</p>
      <Show when={conf() !== null}>
        <div class="mt-2 flex items-center gap-2">
          <div class="flex-1 h-0.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              class={`h-full rounded-full transition-all ${conf()! > 0.8 ? 'bg-emerald-500' : conf()! > 0.5 ? 'bg-amber-500' : 'bg-red-500'}`}
              style={{ width: `${conf()! * 100}%` }}
            />
          </div>
          <span class="text-[9px] font-mono text-slate-500">{(conf()! * 100).toFixed(0)}%</span>
        </div>
      </Show>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────

export function VoicePage() {
  const [status, setStatus] = createSignal<VoiceStatus | null>(null)
  const [listening, setListening] = createSignal(false)
  const [transcript, setTranscript] = createSignal<TranscriptEntry[]>([])
  const [devices, setDevices] = createSignal<DeviceList | null>(null)
  const [voices, setVoices] = createSignal<string[]>([])
  const [selectedVoice, setSelectedVoice] = createSignal('')
  const [speed, setSpeed] = createSignal(100)
  const [ttsText, setTtsText] = createSignal('')
  const [wordCount, setWordCount] = createSignal(0)
  let scrollRef: HTMLDivElement | undefined

  // Poll status + transcript every 2s
  onMount(() => {
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API_RAW}/audio/voice/status`)
        if (res.ok) setStatus(await res.json())
      } catch { /* ignore */ }
      try {
        const res = await fetch(`${API_RAW}/audio/voice/transcript`)
        if (res.ok) {
          const data = await res.json()
          const logs: Array<{ text?: string; event?: string; confidence?: number; timestamp?: string }> = data.entries || []
          const entries: TranscriptEntry[] = logs
            .filter((l) => l.text)
            .map((l) => ({
              speaker: l.event === 'stt_result' ? 'user' as const : 'emily' as const,
              text: l.text!,
              confidence: l.confidence,
              ts: l.timestamp ? new Date(l.timestamp).getTime() : Date.now(),
            }))
          if (entries.length > 0) {
            setTranscript(entries)
            setWordCount(entries.reduce((n, e) => n + e.text.split(' ').length, 0))
          }
        }
      } catch { /* ignore */ }
    }, 2000)
    onCleanup(() => clearInterval(poll))
  })

  // Fetch audio devices once
  onMount(() => {
    fetch(`${API_RAW}/audio/devices`).then(r => r.ok ? r.json() : null).then(d => {
      if (d) setDevices(d)
    }).catch(() => { /* ignore */ })
    fetch(`${API_RAW}/audio/voice/voices`).then(r => r.ok ? r.json() : null).then((v: { voices?: { kokoro?: Array<{ id: string }> } } | null) => {
      if (v?.voices?.kokoro) {
        setVoices(v.voices.kokoro.map((x) => x.id))
      }
    }).catch(() => { /* ignore */ })
  })

  createEffect(() => {
    transcript() // track
    if (scrollRef) scrollRef.scrollTop = scrollRef.scrollHeight
  })

  const toggleListening = async () => {
    const next = !listening()
    try {
      await fetch(next ? `${API_RAW}/audio/voice/start` : `${API_RAW}/audio/voice/stop`, { method: 'POST' })
      setListening(next)
    } catch {
      setListening(next)
    }
  }

  const testTts = async () => {
    if (!ttsText().trim()) return
    try {
      await fetch(`${API_RAW}/audio/voice/test-tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: ttsText(), engine: selectedVoice() || undefined }),
      })
    } catch { /* ignore */ }
  }

  const switchVoice = async (voiceId: string) => {
    setSelectedVoice(voiceId)
    try {
      await fetch(`${API_RAW}/audio/voice/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice: voiceId || (status()?.tts_voice ?? 'af_heart') }),
      })
    } catch { /* ignore */ }
  }

  const switchOutputDevice = async (idx: number) => {
    try {
      const res = await fetch(`${API_RAW}/audio/devices/output`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device: idx }),
      })
      if (res.ok) {
        setDevices(prev => prev ? { ...prev, current_output: String(idx) } : prev)
      }
    } catch { /* ignore */ }
  }

  const fsmState = () => status()?.fsm_state || 'IDLE'
  const isRunning = () => status()?.running || false
  const apiConnected = () => status() !== null
  const latency = () => status()?.latency_ms

  const resolveDevice = (idx: string | null | undefined, list: DeviceInfo[]) => {
    if (!idx || idx === 'None') return null
    const byIdx = list.find(d => String(d.index) === idx)
    return byIdx?.name ?? idx
  }
  const inputName = () => {
    const d = devices()
    return d
      ? resolveDevice(status()?.current_input_device, d.input_devices)
      : status()?.current_input_device
  }

  const activeStages = () => FSM_ACTIVE_STAGES[fsmState()] ?? []
  const sttActive = () => activeStages().includes('stt')
  const llmActive = () => activeStages().includes('llm')
  const ttsActive = () => activeStages().includes('tts')

  const llmModelDisplay = () => {
    const m = status()?.llm_model
    return m ? (m.split('/').pop() ?? m) : '\u2014'
  }

  return (
    <div class="flex flex-col flex-1 min-h-0" style={{ background: 'oklch(0.18 0.02 185)' }}>
      {/* Status bar */}
      <div
        class="flex items-center justify-between px-4 py-2 flex-shrink-0"
        style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)', background: 'oklch(0.22 0.025 185)' }}
      >
        <div class="flex items-center gap-3">
          <div class="flex items-center gap-1.5">
            <span
              class="w-2 h-2 rounded-full transition-colors"
              style={{
                background: apiConnected() ? 'oklch(0.72 0.15 145)' : 'oklch(0.65 0.20 25)',
                'box-shadow': apiConnected() ? '0 0 5px oklch(0.72 0.15 145 / 0.6)' : 'none',
              }}
            />
            <span
              style={{
                'font-size': '0.625rem',
                'font-family': 'var(--font-mono)',
                'text-transform': 'uppercase',
                'letter-spacing': '0.1em',
                color: apiConnected() ? 'oklch(0.72 0.15 145)' : 'oklch(0.65 0.20 25)',
              }}
            >
              {apiConnected() ? 'Connected' : 'Offline'}
            </span>
          </div>
          <div
            class="flex items-center gap-1.5 pl-2"
            style={{ 'border-left': '1px solid oklch(0.30 0.03 185)' }}
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              style={{
                background: isRunning() ? 'oklch(0.72 0.17 162)' : 'oklch(0.30 0.03 185)',
                animation: isRunning() ? 'tidal-pulse 1.4s ease-in-out infinite' : 'none',
              }}
            />
            <span style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', 'text-transform': 'uppercase', 'letter-spacing': '0.1em', color: 'oklch(0.58 0.04 185)' }}>
              Engine
            </span>
          </div>
          <FsmBadge state={fsmState()} />
        </div>

        <div class="flex items-center gap-2" style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', color: 'oklch(0.58 0.04 185)' }}>
          <Show when={status()?.voice_mode}>
            <span style={{ 'text-transform': 'uppercase', 'letter-spacing': '0.1em' }}>{status()!.voice_mode!.replace('_', ' ')}</span>
          </Show>
          <span style={{ color: 'oklch(0.30 0.03 185)' }}>|</span>
          <Clock class="w-3 h-3" />
          <span style={{ color: latency() != null ? 'oklch(0.75 0.16 85)' : 'oklch(0.58 0.04 185)' }}>
            {latency() != null ? `${latency()!.toFixed(0)} ms` : '-- ms'}
          </span>
        </div>
      </div>

      {/* Bento grid body */}
      <div class="flex-1 min-h-0 grid p-3 gap-3" style={{ 'grid-template-columns': '280px 1fr', 'grid-template-rows': 'auto 1fr' }}>
        {/* Cell A: Orb + listen button (spans 2 rows) */}
        <div
          class="row-span-2 rounded-2xl p-4 flex flex-col gap-4 overflow-y-auto"
          style={{ background: 'oklch(0.22 0.025 185)', border: '1px solid oklch(0.30 0.03 185)' }}
        >
          <WaveformCanvas active={listening()} fsm={fsmState()} />

          <button
            onClick={() => void toggleListening()}
            class="flex items-center justify-center gap-2 py-2.5 rounded-xl font-semibold text-sm transition-all"
            style={listening()
              ? { background: 'oklch(0.65 0.20 25 / 0.12)', border: '1px solid oklch(0.65 0.20 25 / 0.30)', color: 'oklch(0.65 0.20 25)', 'font-family': 'var(--font-display)' }
              : { background: 'oklch(0.72 0.17 162 / 0.12)', border: '1px solid oklch(0.72 0.17 162 / 0.30)', color: 'oklch(0.72 0.17 162)', 'font-family': 'var(--font-display)' }
            }
          >
            <Show when={listening()} fallback={<Mic class="w-4 h-4" />}>
              <MicOff class="w-4 h-4" />
            </Show>
            {listening() ? 'Stop Listening' : 'Start Listening'}
          </button>

          {/* Metrics */}
          <div class="grid grid-cols-2 gap-2">
            <MetricCard icon={Activity} label="State" value={fsmState()} color="cyan" />
            <MetricCard icon={Zap} label="Latency" value={latency()?.toFixed(0) ?? '--'} unit="ms" color="amber" />
            <MetricCard icon={Cpu} label="Words" value={wordCount()} color="violet" />
            <MetricCard icon={Radio} label="Mode" value={status()?.voice_mode?.replace('_', ' ') ?? '--'} color="emerald" />
          </div>

          {/* Modules */}
          <div>
            <p
              class="mb-2"
              style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', 'text-transform': 'uppercase', 'letter-spacing': '0.1em', color: 'oklch(0.58 0.04 185)' }}
            >
              Pipeline Modules
            </p>
            <div class="flex flex-wrap gap-1.5">
              <ModulePill label="STT" ok={status()?.stt_available ?? false} />
              <ModulePill label="TTS" ok={status()?.tts_available ?? false} />
              <For each={status()?.modules_loaded ?? []}>{(m) => (
                <ModulePill label={m} ok />
              )}</For>
            </div>
          </div>

          {/* TTS Test */}
          <div style={{ 'border-top': '1px solid oklch(0.30 0.03 185)', 'padding-top': '0.75rem' }}>
            <p
              class="mb-2"
              style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', 'text-transform': 'uppercase', 'letter-spacing': '0.1em', color: 'oklch(0.58 0.04 185)' }}
            >
              TTS Test
            </p>
            <div class="rounded-xl p-3 space-y-3" style={{ background: 'oklch(0.18 0.02 185)' }}>
              <div>
                <label class="mb-1.5 block" style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', color: 'oklch(0.58 0.04 185)' }}>
                  Voice
                </label>
                <VoiceDropdown
                  value={selectedVoice()}
                  onChange={(v) => void switchVoice(v)}
                  options={[
                    { value: '', label: `Default (${status()?.tts_voice ?? 'af_heart'})` },
                    ...voices().map(v => ({ value: v, label: v })),
                  ]}
                />
              </div>
              <div>
                <div class="flex justify-between mb-1">
                  <label style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', color: 'oklch(0.58 0.04 185)' }}>Speed</label>
                  <span style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', color: 'oklch(0.72 0.17 162)' }}>{(speed() / 100).toFixed(2)}\u00D7</span>
                </div>
                <input
                  type="range" min={50} max={200} value={speed()}
                  onInput={(e) => setSpeed(Number(e.currentTarget.value))}
                  class="w-full h-1 appearance-none rounded-full"
                  style={{ background: 'oklch(0.30 0.03 185)', 'accent-color': 'oklch(0.72 0.17 162)' }}
                />
              </div>
              <div class="flex gap-2">
                <input
                  value={ttsText()}
                  onInput={(e) => setTtsText(e.currentTarget.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void testTts()}
                  placeholder="Test synthesis\u2026"
                  class="flex-1 rounded-lg px-2.5 py-1.5 focus:outline-none"
                  style={{
                    background: 'oklch(0.22 0.025 185)',
                    border: '1px solid oklch(0.30 0.03 185)',
                    'font-size': 'var(--text-small)',
                    color: 'oklch(0.93 0.01 90)',
                    'font-family': 'var(--font-body)',
                  }}
                />
                <button
                  onClick={() => void testTts()}
                  class="p-1.5 rounded-lg transition-colors"
                  style={{
                    background: 'oklch(0.72 0.17 162 / 0.15)',
                    border: '1px solid oklch(0.72 0.17 162 / 0.25)',
                    color: 'oklch(0.72 0.17 162)',
                  }}
                >
                  <Volume2 class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Cell B: Pipeline flow */}
        <div
          class="rounded-2xl p-4 flex-shrink-0 space-y-3"
          style={{ background: 'oklch(0.22 0.025 185)', border: '1px solid oklch(0.30 0.03 185)' }}
        >
          <div class="flex items-center gap-2">
            <Waves class="w-3.5 h-3.5" style={{ color: 'oklch(0.58 0.04 185)' }} />
            <span style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', 'text-transform': 'uppercase', 'letter-spacing': '0.1em', color: 'oklch(0.58 0.04 185)' }}>
              Voice Pipeline
            </span>
          </div>
          <PipelineFlow status={status()} listening={listening()} />
          <div class="grid grid-cols-3 gap-2">
            <ModelCard
              stage="STT \u00B7 Speech\u2192Text"
              model={`${status()?.stt_provider ?? 'faster_whisper'} ${status()?.stt_model ?? 'base.en'}`}
              provider={`VAD thr: ${status()?.vad_threshold ?? 0.5} \u00B7 Silero`}
              active={sttActive()}
            />
            <ModelCard
              stage={`LLM \u00B7 ${status()?.llm_tier ?? 'voice_fast'} tier`}
              model={llmModelDisplay()}
              provider="ollama \u00B7 temp 0.7"
              active={llmActive()}
            />
            <ModelCard
              stage="TTS \u00B7 Text\u2192Speech"
              model={status()?.tts_engine ?? 'kokoro'}
              provider="local \u00B7 af_heart"
              voice={status()?.tts_voice ?? 'af_heart'}
              active={ttsActive()}
            />
          </div>
          <div class="flex items-center gap-6 px-1">
            <DeviceRow direction="Input" deviceName={inputName()} />
            <div class="w-px h-3" style={{ background: 'oklch(0.30 0.03 185)' }} />
            <OutputDevicePicker
              outputDevices={devices()?.output_devices ?? []}
              currentOutputIdx={status()?.current_output_device ?? devices()?.current_output}
              onSwitch={switchOutputDevice}
            />
          </div>
        </div>

        {/* Cell C: Transcript */}
        <div
          class="rounded-2xl flex flex-col min-h-0"
          style={{ background: 'oklch(0.22 0.025 185)', border: '1px solid oklch(0.30 0.03 185)' }}
        >
          <div
            class="flex items-center justify-between px-4 py-2 flex-shrink-0"
            style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)' }}
          >
            <div class="flex items-center gap-2">
              <Activity class="w-3.5 h-3.5" style={{ color: 'oklch(0.58 0.04 185)' }} />
              <span style={{ 'font-size': '0.625rem', 'font-family': 'var(--font-mono)', 'text-transform': 'uppercase', 'letter-spacing': '0.1em', color: 'oklch(0.58 0.04 185)' }}>
                Live Transcript
              </span>
              <span style={{ 'font-size': '0.5625rem', 'font-family': 'var(--font-mono)', color: 'oklch(0.30 0.03 185)' }}>
                {transcript().length} entries \u00B7 {wordCount()} words
              </span>
            </div>
            <button
              onClick={() => { setTranscript([]); setWordCount(0) }}
              class="p-1 rounded-lg transition-colors"
              style={{ color: 'oklch(0.58 0.04 185)' }}
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>

          <div ref={scrollRef} class="flex-1 overflow-y-auto p-3 space-y-2">
            <Show when={transcript().length > 0} fallback={
              <div class="flex flex-col items-center justify-center h-full gap-3" style={{ color: 'oklch(0.58 0.04 185)' }}>
                <Radio class="w-8 h-8 opacity-30" />
                <p style={{ 'font-size': 'var(--text-small)', 'font-family': 'var(--font-body)' }}>No transcript yet \u2014 start listening</p>
              </div>
            }>
              <For each={transcript()}>{(entry) => (
                <TranscriptRow entry={entry} />
              )}</For>
            </Show>
          </div>
        </div>
      </div>
    </div>
  )
}
