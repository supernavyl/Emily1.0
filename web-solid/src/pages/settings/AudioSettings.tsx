import { createSignal, createEffect, onMount, Show, For } from 'solid-js'
import {
  Mic, Volume2, Play, Loader, CircleCheck, CircleAlert, RefreshCw, ChevronDown, Check,
} from 'lucide-solid'
import { API_RAW } from '../../lib/env'

// ── Shared primitives ─────────────────────────────────────────────────────

const cardStyle = {
  background: 'oklch(0.22 0.02 185)',
  border: '1px solid oklch(0.30 0.02 185)',
  'border-radius': '12px',
  padding: '20px',
}

function StatusMsg(props: { ok: boolean; msg: string }) {
  return (
    <div
      class="flex items-center gap-2 text-sm"
      style={{ color: props.ok ? 'oklch(0.72 0.17 162)' : 'oklch(0.68 0.20 25)' }}
    >
      <Show when={props.ok} fallback={<CircleAlert size={16} class="shrink-0" />}>
        <CircleCheck size={16} class="shrink-0" />
      </Show>
      {props.msg}
    </div>
  )
}

function FieldLabel(props: { children: string }) {
  return (
    <label
      class="block text-xs uppercase tracking-wider font-medium mb-1"
      style={{ color: 'oklch(0.55 0.03 185)' }}
    >
      {props.children}
    </label>
  )
}

function TextInput(props: {
  value: string
  onInput: (v: string) => void
  placeholder?: string
}) {
  return (
    <input
      type="text"
      value={props.value}
      onInput={(e) => props.onInput(e.currentTarget.value)}
      placeholder={props.placeholder}
      class="w-full rounded-lg px-3 py-2 text-sm transition-colors"
      style={{
        background: 'oklch(0.18 0.02 185)',
        border: '1px solid oklch(0.30 0.02 185)',
        color: 'oklch(0.93 0.01 90)',
        outline: 'none',
      }}
    />
  )
}

function Btn(props: {
  loading?: boolean
  variant?: 'primary' | 'ghost'
  disabled?: boolean
  onClick: () => void
  children: string
}) {
  const isPrimary = () => (props.variant ?? 'primary') === 'primary'
  return (
    <button
      disabled={props.loading || props.disabled}
      onClick={() => props.onClick()}
      class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
      style={{
        background: isPrimary() ? 'oklch(0.72 0.17 162)' : 'transparent',
        color: isPrimary() ? 'oklch(0.18 0.02 185)' : 'oklch(0.75 0.03 185)',
        border: isPrimary() ? 'none' : '1px solid oklch(0.30 0.02 185)',
      }}
    >
      <Show when={props.loading}>
        <Loader size={14} class="animate-spin" />
      </Show>
      {props.children}
    </button>
  )
}

// ── Dropdown (replaces native select — broken in WebKitGTK/Tauri) ─────────

function Dropdown(props: {
  value: string
  onChange: (v: string) => void
  options: Array<{ value: string; label: string }>
  disabled?: boolean
  placeholder?: string
}) {
  const [open, setOpen] = createSignal(false)
  let ref: HTMLDivElement | undefined

  // Close on outside click
  createEffect(() => {
    if (!open()) return
    const handler = (e: MouseEvent) => {
      if (ref && !ref.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  })

  const selected = () => props.options.find((o) => o.value === props.value)

  return (
    <div ref={ref} class="relative w-full">
      <button
        type="button"
        onClick={() => !props.disabled && setOpen((o) => !o)}
        disabled={props.disabled}
        class="w-full flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors disabled:opacity-50"
        style={{
          background: 'oklch(0.18 0.02 185)',
          border: '1px solid oklch(0.30 0.02 185)',
          color: selected() ? 'oklch(0.93 0.01 90)' : 'oklch(0.55 0.03 185)',
        }}
      >
        <span>{selected()?.label ?? props.placeholder ?? props.value}</span>
        <ChevronDown
          size={16}
          class="shrink-0 ml-2 transition-transform"
          style={{
            color: 'oklch(0.55 0.03 185)',
            transform: open() ? 'rotate(180deg)' : 'rotate(0)',
          }}
        />
      </button>

      <Show when={open()}>
        <div
          class="absolute z-50 w-full mt-1 rounded-xl shadow-xl overflow-hidden"
          style={{
            background: 'oklch(0.22 0.02 185)',
            border: '1px solid oklch(0.30 0.02 185)',
          }}
        >
          <div class="max-h-60 overflow-y-auto py-1">
            <For each={props.options}>
              {(opt) => (
                <button
                  type="button"
                  onClick={() => { props.onChange(opt.value); setOpen(false) }}
                  class="w-full flex items-center justify-between px-3 py-2 text-sm transition-colors text-left"
                  style={{
                    color: opt.value === props.value ? 'oklch(0.72 0.17 162)' : 'oklch(0.93 0.01 90)',
                    background: 'transparent',
                  }}
                >
                  {opt.label}
                  <Show when={opt.value === props.value}>
                    <Check size={14} class="shrink-0 ml-2" style={{ color: 'oklch(0.72 0.17 162)' }} />
                  </Show>
                </button>
              )}
            </For>
          </div>
        </div>
      </Show>
    </div>
  )
}

// ── Data types ────────────────────────────────────────────────────────────

interface DeviceInfo { index: number; name: string }
interface DeviceList {
  input_devices: DeviceInfo[]
  output_devices: DeviceInfo[]
  current_input: string | null
  current_output: string | null
}

interface VoiceSettings {
  voice: string
  provider: string
  available_providers: string[]
}

const KOKORO_VOICE_OPTIONS = [
  { value: 'af_heart', label: 'Heart (F - EN-US)' },
  { value: 'af_bella', label: 'Bella (F - EN-US)' },
  { value: 'af_sarah', label: 'Sarah (F - EN-US)' },
  { value: 'af_nova', label: 'Nova (F - EN-US)' },
  { value: 'af_sky', label: 'Sky (F - EN-US)' },
  { value: 'am_adam', label: 'Adam (M - EN-US)' },
  { value: 'am_michael', label: 'Michael (M - EN-US)' },
  { value: 'bf_emma', label: 'Emma (F - EN-GB)' },
  { value: 'bf_isabella', label: 'Isabella (F - EN-GB)' },
  { value: 'bm_george', label: 'George (M - EN-GB)' },
]

// ── Component ─────────────────────────────────────────────────────────────

function AudioSettings() {
  // Device state
  const [devices, setDevices] = createSignal<DeviceList | null>(null)
  const [inputIdx, setInputIdx] = createSignal<number | null>(null)
  const [outputIdx, setOutputIdx] = createSignal<number | null>(null)
  const [devLoading, setDevLoading] = createSignal(true)
  const [devError, setDevError] = createSignal<string | null>(null)
  const [devSaving, setDevSaving] = createSignal<'input' | 'output' | null>(null)
  const [devStatus, setDevStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  // Voice/TTS state
  const [voiceSettings, setVoiceSettings] = createSignal<VoiceSettings | null>(null)
  const [voice, setVoice] = createSignal('af_heart')
  const [provider, setProvider] = createSignal('kokoro')
  const [testText, setTestText] = createSignal("Hello! I'm Emily. How can I help you today?")
  const [voiceLoading, setVoiceLoading] = createSignal(true)
  const [voiceSaving, setVoiceSaving] = createSignal(false)
  const [testing, setTesting] = createSignal(false)
  const [voiceStatus, setVoiceStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  const loadDevices = async () => {
    setDevLoading(true)
    setDevError(null)
    setDevStatus(null)
    try {
      const r = await fetch(`${API_RAW}/audio/devices`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d: DeviceList = await r.json()
      setDevices(d)
      if (d.current_input !== null) setInputIdx(Number(d.current_input))
      if (d.current_output !== null) setOutputIdx(Number(d.current_output))
    } catch {
      setDevError('Could not load audio devices -- API may still be starting up.')
    }
    setDevLoading(false)
  }

  const setDevice = async (type: 'input' | 'output', index: number) => {
    setDevSaving(type)
    setDevStatus(null)
    if (type === 'input') setInputIdx(index)
    else setOutputIdx(index)
    try {
      const r = await fetch(`${API_RAW}/audio/devices/${type}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device: index }),
      })
      const d = await r.json()
      if (r.ok && !d.warning) {
        setDevStatus({ ok: true, msg: `${type === 'input' ? 'Microphone' : 'Speaker'} updated.` })
      } else {
        setDevStatus({ ok: !!r.ok, msg: d.warning || d.detail || 'Applied with warnings.' })
      }
    } catch {
      setDevStatus({ ok: false, msg: 'Network error.' })
    }
    setDevSaving(null)
  }

  const loadVoice = () => {
    fetch(`${API_RAW}/audio/voice/settings`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: VoiceSettings) => {
        setVoiceSettings(d)
        setVoice(d.voice)
        setProvider(d.provider)
      })
      .catch(() => setVoiceStatus({ ok: false, msg: 'Could not load voice settings.' }))
      .finally(() => setVoiceLoading(false))
  }

  const saveVoice = async () => {
    setVoiceSaving(true)
    setVoiceStatus(null)
    try {
      const r = await fetch(`${API_RAW}/audio/voice/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice: voice(), provider: provider() }),
      })
      if (r.ok) setVoiceStatus({ ok: true, msg: 'Voice settings saved.' })
      else setVoiceStatus({ ok: false, msg: 'Save failed.' })
    } catch {
      setVoiceStatus({ ok: false, msg: 'Network error.' })
    }
    setVoiceSaving(false)
  }

  const testTTS = async () => {
    setTesting(true)
    setVoiceStatus(null)
    try {
      const r = await fetch(`${API_RAW}/audio/voice/test-tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: testText() }),
      })
      if (r.ok) setVoiceStatus({ ok: true, msg: 'Playing through output device...' })
      else {
        const d = await r.json()
        setVoiceStatus({ ok: false, msg: d.detail || 'TTS test failed.' })
      }
    } catch {
      setVoiceStatus({ ok: false, msg: 'Network error.' })
    }
    setTesting(false)
  }

  onMount(() => {
    void loadDevices()
    loadVoice()
  })

  const inputOptions = () =>
    devices()?.input_devices.map((d) => ({ value: String(d.index), label: `${d.index}: ${d.name}` })) ?? []
  const outputOptions = () =>
    devices()?.output_devices.map((d) => ({ value: String(d.index), label: `${d.index}: ${d.name}` })) ?? []
  const providerOptions = () => {
    const vs = voiceSettings()
    const providers = vs?.available_providers?.length ? vs.available_providers : ['kokoro']
    return providers.map((p) => ({ value: p, label: p }))
  }

  return (
    <div class="space-y-4">
      {/* ── Devices section ──────────────────────────────────────────── */}
      <Show
        when={!devLoading() || devices()}
        fallback={
          <div class="flex items-center gap-2 text-sm py-4" style={{ color: 'oklch(0.55 0.03 185)' }}>
            <Loader size={16} class="animate-spin" /> Loading devices...
          </div>
        }
      >
        <Show
          when={!devError() || devices()}
          fallback={
            <div style={cardStyle}>
              <div class="flex items-start gap-3">
                <CircleAlert size={20} class="shrink-0 mt-0.5" style={{ color: 'oklch(0.68 0.20 25)' }} />
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium" style={{ color: 'oklch(0.93 0.01 90)' }}>
                    Could not load audio devices
                  </p>
                  <p class="text-xs mt-0.5" style={{ color: 'oklch(0.55 0.03 185)' }}>{devError()}</p>
                </div>
                <Btn variant="ghost" loading={devLoading()} onClick={loadDevices}>Retry</Btn>
              </div>
            </div>
          }
        >
          {/* Microphone */}
          <div style={cardStyle} class="space-y-4">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
                <Mic size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                Microphone
              </div>
              <button
                onClick={() => void loadDevices()}
                title="Refresh device list"
                class="p-1 rounded transition-colors"
                style={{ color: 'oklch(0.55 0.03 185)' }}
              >
                <RefreshCw size={14} />
              </button>
            </div>
            <div>
              <FieldLabel>Input device</FieldLabel>
              <Dropdown
                value={inputIdx() !== null ? String(inputIdx()) : ''}
                onChange={(v) => void setDevice('input', Number(v))}
                disabled={devSaving() === 'input'}
                options={inputOptions()}
                placeholder="Select microphone..."
              />
            </div>
            <Show when={devSaving() === 'input'}>
              <div class="flex items-center gap-2 text-xs" style={{ color: 'oklch(0.55 0.03 185)' }}>
                <Loader size={12} class="animate-spin" /> Applying...
              </div>
            </Show>
          </div>

          {/* Speaker */}
          <div style={cardStyle} class="space-y-4">
            <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
              <Volume2 size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
              Speaker
            </div>
            <div>
              <FieldLabel>Output device</FieldLabel>
              <Dropdown
                value={outputIdx() !== null ? String(outputIdx()) : ''}
                onChange={(v) => void setDevice('output', Number(v))}
                disabled={devSaving() === 'output'}
                options={outputOptions()}
                placeholder="Select speaker..."
              />
            </div>
            <Show when={devSaving() === 'output'}>
              <div class="flex items-center gap-2 text-xs" style={{ color: 'oklch(0.55 0.03 185)' }}>
                <Loader size={12} class="animate-spin" /> Applying...
              </div>
            </Show>
          </div>

          <Show when={devStatus()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
        </Show>
      </Show>

      {/* ── Voice / TTS section ──────────────────────────────────────── */}
      <Show
        when={!voiceLoading()}
        fallback={
          <div class="flex items-center gap-2 text-sm py-4" style={{ color: 'oklch(0.55 0.03 185)' }}>
            <Loader size={16} class="animate-spin" /> Loading voice settings...
          </div>
        }
      >
        {/* TTS Engine */}
        <div style={cardStyle} class="space-y-4">
          <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
            <Volume2 size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
            TTS Engine
          </div>
          <div>
            <FieldLabel>Provider</FieldLabel>
            <Dropdown value={provider()} onChange={setProvider} options={providerOptions()} />
          </div>
          <Show when={provider() === 'kokoro'}>
            <div>
              <FieldLabel>Voice</FieldLabel>
              <Dropdown value={voice()} onChange={setVoice} options={KOKORO_VOICE_OPTIONS} />
            </div>
          </Show>
          <div class="flex items-center gap-3 pt-1">
            <Btn loading={voiceSaving()} onClick={saveVoice}>Save</Btn>
            <Show when={voiceStatus()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
          </div>
        </div>

        {/* Test Audio */}
        <div style={cardStyle} class="space-y-4">
          <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
            <Play size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
            Test Audio
          </div>
          <div>
            <FieldLabel>Test phrase</FieldLabel>
            <TextInput
              value={testText()}
              onInput={setTestText}
              placeholder="Enter text to speak..."
            />
          </div>
          <div class="flex items-center gap-3 pt-1">
            <Btn variant="ghost" loading={testing()} onClick={testTTS}>Play</Btn>
          </div>
        </div>
      </Show>
    </div>
  )
}

export default AudioSettings
