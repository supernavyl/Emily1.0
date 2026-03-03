import { useState, useEffect, useCallback, useRef } from 'react'
import {
  User, Mic, Volume2, Key, Bot, Loader, CheckCircle, AlertCircle,
  RefreshCw, Play, ShieldCheck, Eye, Brain, Lock, ChevronDown, Check,
  Sparkles, SlidersHorizontal,
  FolderOpen, Terminal, Monitor, Bell, Mail, CalendarDays,
  MessageSquare, Globe, Home, Cpu, Search, Shield,
  Puzzle, BookOpen, Plus, Trash2, Pencil, X, Zap,
} from 'lucide-react'

import { API_RAW } from '../lib/env'
const API = API_RAW

// ── Primitives ─────────────────────────────────────────────────────────────

function StatusMsg({ ok, msg }: { ok: boolean; msg: string }) {
  return (
    <div className={`flex items-center gap-2 text-sm ${ok ? 'text-cost-green' : 'text-error-red'}`}>
      {ok ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
      {msg}
    </div>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-surface-raised border border-border rounded-xl p-5 space-y-4">
      {children}
    </div>
  )
}

function CardTitle({ icon: Icon, title }: { icon: typeof User; title: string }) {
  return (
    <div className="flex items-center gap-2 text-text-primary font-semibold text-sm">
      <Icon className="w-4 h-4 text-accent" />
      {title}
    </div>
  )
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-xs text-text-muted uppercase tracking-wider font-medium mb-1">
      {children}
    </label>
  )
}

function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary
                 placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
    />
  )
}

// ── Custom Dropdown (replaces native <select> — broken in WebKitGTK/Tauri) ──

function Dropdown({
  value, onChange, options, disabled, placeholder, label,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
  placeholder?: string
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [focusIdx, setFocusIdx] = useState(-1)
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        if (!open) { setOpen(true); setFocusIdx(0) }
        else setFocusIdx(i => Math.min(i + 1, options.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        if (open) setFocusIdx(i => Math.max(i - 1, 0))
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        if (open && focusIdx >= 0) { onChange(options[focusIdx].value); setOpen(false) }
        else { setOpen(true); setFocusIdx(0) }
        break
      case 'Escape':
        setOpen(false)
        break
      case 'Home':
        if (open) { e.preventDefault(); setFocusIdx(0) }
        break
      case 'End':
        if (open) { e.preventDefault(); setFocusIdx(options.length - 1) }
        break
    }
  }

  return (
    <div ref={ref} className="relative w-full">
      <button
        type="button"
        onClick={() => !disabled && setOpen(o => !o)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        className="w-full flex items-center justify-between bg-surface border border-border rounded-lg
                   px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent
                   transition-colors disabled:opacity-50 hover:border-accent/60"
      >
        <span className={selected ? 'text-text-primary' : 'text-text-muted'}>
          {selected?.label ?? placeholder ?? value}
        </span>
        <ChevronDown aria-hidden="true" className={`w-4 h-4 text-text-muted transition-transform shrink-0 ml-2 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div role="listbox" aria-label={label} className="absolute z-50 w-full mt-1 bg-surface-raised border border-border rounded-xl shadow-xl overflow-hidden">
          <div className="max-h-60 overflow-y-auto py-1">
            {options.map((opt, i) => (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={opt.value === value}
                onClick={() => { onChange(opt.value); setOpen(false) }}
                className={`w-full flex items-center justify-between px-3 py-2 text-sm transition-colors
                            hover:bg-surface text-left ${
                  opt.value === value ? 'text-accent' : 'text-text-primary'
                } ${i === focusIdx ? 'bg-surface-hover' : ''}`}
              >
                {opt.label}
                {opt.value === value && <Check aria-hidden="true" className="w-3.5 h-3.5 text-accent shrink-0 ml-2" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Slider with value pill ──────────────────────────────────────────────────

function Slider({
  value, onChange, min = 0, max = 1, step = 0.05,
  label, description, disabled,
}: {
  value: number
  onChange: (v: number) => void
  min?: number; max?: number; step?: number
  label?: string; description?: string; disabled?: boolean
}) {
  const display = step >= 1 ? String(Math.round(value)) : value.toFixed(2)
  return (
    <div className="space-y-1.5">
      {label && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-text-muted uppercase tracking-wider font-medium">{label}</span>
          <span className="text-xs font-mono text-accent bg-accent/10 px-1.5 py-0.5 rounded">{display}</span>
        </div>
      )}
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        disabled={disabled}
        className="w-full h-2 bg-border rounded-full appearance-none cursor-pointer accent-accent
                   disabled:opacity-50 disabled:cursor-not-allowed"
      />
      {description && <p className="text-xs text-text-muted">{description}</p>}
    </div>
  )
}

function Btn({
  loading, variant = 'primary', children, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean; variant?: 'primary' | 'ghost' }) {
  return (
    <button
      {...props}
      disabled={loading || props.disabled}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors
                  disabled:opacity-50 ${
        variant === 'primary'
          ? 'bg-accent text-white hover:bg-accent/90'
          : 'bg-surface border border-border text-text-secondary hover:text-text-primary hover:border-accent'
      }`}
    >
      {loading && <Loader className="w-3.5 h-3.5 animate-spin" />}
      {children}
    </button>
  )
}

function Toggle({ enabled, onChange, disabled }: { enabled: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={enabled}
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`relative w-10 h-5 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-accent/50 disabled:opacity-40 shrink-0 ${
        enabled ? 'bg-accent' : 'bg-border'
      }`}
    >
      <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200 ${
        enabled ? 'translate-x-5' : 'translate-x-0'
      }`} />
    </button>
  )
}

function PermRow({
  icon: Icon, label, description, value, onChange, disabled,
}: {
  icon: typeof Eye; label: string; description: string
  value: boolean; onChange: (v: boolean) => void; disabled?: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-0">
      <div className="flex items-start gap-3 min-w-0">
        <Icon className="w-4 h-4 text-text-muted mt-0.5 shrink-0" />
        <div className="min-w-0">
          <div className="text-sm text-text-primary font-medium">{label}</div>
          <div className="text-xs text-text-muted mt-0.5">{description}</div>
        </div>
      </div>
      <Toggle enabled={value} onChange={onChange} disabled={disabled} />
    </div>
  )
}

// ── Tabs ───────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'profile',     label: 'Profile',     icon: User             },
  { id: 'audio',       label: 'Audio',       icon: Mic              },
  { id: 'voice',       label: 'Voice',       icon: Volume2          },
  { id: 'personality', label: 'Personality', icon: Sparkles         },
  { id: 'advanced',    label: 'Advanced',    icon: SlidersHorizontal},
  { id: 'skills',      label: 'Skills',      icon: Zap              },
  { id: 'plugins',     label: 'Plugins',     icon: Puzzle           },
  { id: 'rules',       label: 'Rules',       icon: BookOpen         },
  { id: 'privacy',     label: 'Privacy',     icon: ShieldCheck      },
  { id: 'security',    label: 'Security',    icon: Key              },
] as const

type Tab = typeof TABS[number]['id']

// ── Profile tab ────────────────────────────────────────────────────────────

interface ProfileData { has_owner: boolean; name: string; ai_name: string; email: string }

function RegisterForm({ onDone }: { onDone: () => void }) {
  const [name, setName]       = useState('')
  const [aiName, setAiName]   = useState('Emily')
  const [pass, setPass]       = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)

  const submit = async () => {
    if (!name.trim() || !pass.trim()) return setStatus({ ok: false, msg: 'Name and passphrase are required.' })
    if (pass !== confirm) return setStatus({ ok: false, msg: 'Passphrases do not match.' })
    setLoading(true)
    try {
      const r = await fetch(`${API}/settings/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), passphrase: pass, ai_name: aiName.trim() || 'Emily' }),
      })
      const d = await r.json()
      if (r.ok) { setStatus({ ok: true, msg: d.message }); setTimeout(onDone, 1200) }
      else setStatus({ ok: false, msg: d.detail || 'Registration failed.' })
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setLoading(false)
  }

  return (
    <Card>
      <CardTitle icon={User} title="First-time Setup" />
      <p className="text-sm text-text-muted">No owner registered yet. Set up your profile to get started.</p>
      <div><FieldLabel>Your name</FieldLabel><TextInput value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Alex" /></div>
      <div><FieldLabel>AI name</FieldLabel><TextInput value={aiName} onChange={e => setAiName(e.target.value)} placeholder="Emily" /></div>
      <div><FieldLabel>Passphrase</FieldLabel><TextInput type="password" value={pass} onChange={e => setPass(e.target.value)} placeholder="Choose a passphrase" /></div>
      <div><FieldLabel>Confirm passphrase</FieldLabel><TextInput type="password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="Repeat passphrase" /></div>
      <div className="flex items-center gap-3 pt-1">
        <Btn loading={loading} onClick={submit}>Create Profile</Btn>
        {status && <StatusMsg {...status} />}
      </div>
    </Card>
  )
}

function ProfileTab() {
  const [data, setData]     = useState<ProfileData | null>(null)
  const [aiName, setAiName] = useState('')
  const [email, setEmail]   = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/settings/profile`)
      if (!r.ok) throw new Error()
      const d: ProfileData = await r.json()
      setData(d); setAiName(d.ai_name); setEmail(d.email)
    } catch { setStatus({ ok: false, msg: 'Could not load profile — is the API running?' }) }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const save = async () => {
    setSaving(true); setStatus(null)
    try {
      const r = await fetch(`${API}/settings/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ai_name: aiName.trim() || undefined,
          email:   email.trim()  || undefined,
        }),
      })
      const d = await r.json()
      if (r.ok) setStatus({ ok: true, msg: 'Saved.' })
      else setStatus({ ok: false, msg: d.detail || 'Save failed.' })
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setSaving(false)
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-sm py-4">
        <Loader className="w-4 h-4 animate-spin" /> Loading...
      </div>
    )
  }

  if (!data?.has_owner) return <RegisterForm onDone={load} />

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle icon={User} title="Owner" />
        <div>
          <FieldLabel>Name</FieldLabel>
          <div className="px-3 py-2 bg-surface border border-border rounded-lg text-sm text-text-secondary">
            {data.name}
          </div>
        </div>
      </Card>

      <Card>
        <CardTitle icon={Bot} title="AI Identity" />
        <div>
          <FieldLabel>AI name</FieldLabel>
          <TextInput value={aiName} onChange={e => setAiName(e.target.value)} placeholder="Emily" />
        </div>
        <div>
          <FieldLabel>Recovery email</FieldLabel>
          <TextInput type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
        </div>
        <div className="flex items-center gap-3 pt-1">
          <Btn loading={saving} onClick={save}>Save</Btn>
          {status && <StatusMsg {...status} />}
        </div>
      </Card>
    </div>
  )
}

// ── Audio tab ──────────────────────────────────────────────────────────────

interface DeviceInfo { index: number; name: string }
interface DeviceList {
  input_devices:  DeviceInfo[]
  output_devices: DeviceInfo[]
  current_input:  string | null
  current_output: string | null
}

function AudioTab() {
  const [devices, setDevices]   = useState<DeviceList | null>(null)
  const [inputIdx, setInputIdx]   = useState<number | null>(null)
  const [outputIdx, setOutputIdx] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const [saving, setSaving]   = useState<'input' | 'output' | null>(null)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null); setStatus(null)
    try {
      const r = await fetch(`${API}/audio/devices`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d: DeviceList = await r.json()
      setDevices(d)
      if (d.current_input  !== null) setInputIdx(Number(d.current_input))
      if (d.current_output !== null) setOutputIdx(Number(d.current_output))
      setRetryCount(0)
    } catch {
      setError('Could not load audio devices — API may still be starting up.')
    }
    setLoading(false)
  }, [])

  // Auto-retry up to 3 times at 5 s intervals when in error state
  useEffect(() => {
    if (error && retryCount < 3) {
      retryTimer.current = setTimeout(() => {
        setRetryCount(c => c + 1)
        load()
      }, 5000)
      return () => { if (retryTimer.current) clearTimeout(retryTimer.current) }
    }
  }, [error, retryCount, load])

  useEffect(() => { load() }, [load])

  const setDevice = async (type: 'input' | 'output', index: number) => {
    setSaving(type); setStatus(null)
    if (type === 'input') setInputIdx(index)
    else setOutputIdx(index)
    try {
      const r = await fetch(`${API}/audio/devices/${type}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device: index }),
      })
      const d = await r.json()
      if (r.ok && !d.warning) {
        setStatus({ ok: true, msg: `${type === 'input' ? 'Microphone' : 'Speaker'} updated.` })
      } else {
        setStatus({ ok: !!r.ok, msg: d.warning || d.detail || 'Applied with warnings.' })
      }
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setSaving(null)
  }

  if (loading && !devices) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-sm py-4">
        <Loader className="w-4 h-4 animate-spin" /> Loading devices...
      </div>
    )
  }

  if (error && !devices) {
    return (
      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-error-red shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-text-primary font-medium">Could not load audio devices</p>
            <p className="text-xs text-text-muted mt-0.5">{error}</p>
            {retryCount < 3 && (
              <p className="text-xs text-text-muted mt-1">
                Auto-retrying… ({retryCount}/3)
              </p>
            )}
          </div>
          <Btn variant="ghost" loading={loading} onClick={() => { setRetryCount(0); load() }}>
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </Btn>
        </div>
      </div>
    )
  }

  const inputOptions  = devices?.input_devices.map(d  => ({ value: String(d.index), label: `${d.index}: ${d.name}` })) ?? []
  const outputOptions = devices?.output_devices.map(d => ({ value: String(d.index), label: `${d.index}: ${d.name}` })) ?? []

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center justify-between">
          <CardTitle icon={Mic} title="Microphone" />
          <button onClick={load} title="Refresh device list"
            className="text-text-muted hover:text-text-primary transition-colors p-1 rounded">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
        <div>
          <FieldLabel>Input device</FieldLabel>
          <Dropdown
            value={inputIdx !== null ? String(inputIdx) : ''}
            onChange={v => setDevice('input', Number(v))}
            disabled={saving === 'input'}
            options={inputOptions}
            placeholder="Select microphone…"
          />
        </div>
        {saving === 'input' && (
          <div className="flex items-center gap-2 text-text-muted text-xs">
            <Loader className="w-3 h-3 animate-spin" /> Applying…
          </div>
        )}
      </Card>

      <Card>
        <CardTitle icon={Volume2} title="Speaker" />
        <div>
          <FieldLabel>Output device</FieldLabel>
          <Dropdown
            value={outputIdx !== null ? String(outputIdx) : ''}
            onChange={v => setDevice('output', Number(v))}
            disabled={saving === 'output'}
            options={outputOptions}
            placeholder="Select speaker…"
          />
        </div>
        {saving === 'output' && (
          <div className="flex items-center gap-2 text-text-muted text-xs">
            <Loader className="w-3 h-3 animate-spin" /> Applying…
          </div>
        )}
      </Card>

      {status && <StatusMsg {...status} />}
    </div>
  )
}

// ── Voice tab ──────────────────────────────────────────────────────────────

const KOKORO_VOICE_OPTIONS = [
  { value: 'af_heart',    label: 'Heart (F · EN-US)' },
  { value: 'af_bella',    label: 'Bella (F · EN-US)' },
  { value: 'af_sarah',    label: 'Sarah (F · EN-US)' },
  { value: 'af_nova',     label: 'Nova (F · EN-US)'  },
  { value: 'af_sky',      label: 'Sky (F · EN-US)'   },
  { value: 'am_adam',     label: 'Adam (M · EN-US)'  },
  { value: 'am_michael',  label: 'Michael (M · EN-US)'},
  { value: 'bf_emma',     label: 'Emma (F · EN-GB)'  },
  { value: 'bf_isabella', label: 'Isabella (F · EN-GB)'},
  { value: 'bm_george',   label: 'George (M · EN-GB)'},
]

interface VoiceSettings { voice: string; provider: string; available_providers: string[] }

function VoiceTab() {
  const [settings, setSettings] = useState<VoiceSettings | null>(null)
  const [voice, setVoice]       = useState('af_heart')
  const [provider, setProvider] = useState('kokoro')
  const [testText, setTestText] = useState("Hello! I'm Emily. How can I help you today?")
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [testing, setTesting]   = useState(false)
  const [status, setStatus]     = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    fetch(`${API}/audio/voice/settings`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((d: VoiceSettings) => { setSettings(d); setVoice(d.voice); setProvider(d.provider) })
      .catch(() => setStatus({ ok: false, msg: 'Could not load voice settings.' }))
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true); setStatus(null)
    try {
      const r = await fetch(`${API}/audio/voice/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice, provider }),
      })
      if (r.ok) setStatus({ ok: true, msg: 'Voice settings saved.' })
      else setStatus({ ok: false, msg: 'Save failed.' })
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setSaving(false)
  }

  const test = async () => {
    setTesting(true); setStatus(null)
    try {
      const r = await fetch(`${API}/audio/voice/test-tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: testText }),
      })
      if (r.ok) setStatus({ ok: true, msg: 'Playing through output device…' })
      else { const d = await r.json(); setStatus({ ok: false, msg: d.detail || 'TTS test failed.' }) }
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setTesting(false)
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-sm py-4">
        <Loader className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  const providers = settings?.available_providers?.length ? settings.available_providers : ['kokoro']
  const providerOptions = providers.map(p => ({ value: p, label: p }))

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle icon={Volume2} title="TTS Engine" />
        <div>
          <FieldLabel>Provider</FieldLabel>
          <Dropdown value={provider} onChange={setProvider} options={providerOptions} />
        </div>

        {provider === 'kokoro' && (
          <div>
            <FieldLabel>Voice</FieldLabel>
            <Dropdown value={voice} onChange={setVoice} options={KOKORO_VOICE_OPTIONS} />
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <Btn loading={saving} onClick={save}>Save</Btn>
          {status && <StatusMsg {...status} />}
        </div>
      </Card>

      <Card>
        <CardTitle icon={Play} title="Test Audio" />
        <div>
          <FieldLabel>Test phrase</FieldLabel>
          <TextInput
            value={testText}
            onChange={e => setTestText(e.target.value)}
            placeholder="Enter text to speak…"
          />
        </div>
        <div className="flex items-center gap-3 pt-1">
          <Btn variant="ghost" loading={testing} onClick={test}>
            {!testing && <Play className="w-3.5 h-3.5" />}
            Play
          </Btn>
          {status && <StatusMsg {...status} />}
        </div>
      </Card>
    </div>
  )
}

// ── Personality tab ────────────────────────────────────────────────────────

interface PersonaData {
  curiosity:  number
  warmth:     number
  directness: number
  humor:      number
  formality:  number
}

function PersonalityTab() {
  const [persona, setPersona] = useState<PersonaData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    fetch(`${API}/settings/persona`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setPersona)
      .catch(() => setStatus({ ok: false, msg: 'Could not load personality settings.' }))
      .finally(() => setLoading(false))
  }, [])

  const set = (key: keyof PersonaData) => (v: number) =>
    setPersona(p => p ? { ...p, [key]: v } : p)

  const save = async () => {
    if (!persona) return
    setSaving(true); setStatus(null)
    try {
      const r = await fetch(`${API}/settings/persona`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(persona),
      })
      if (r.ok) setStatus({ ok: true, msg: 'Personality saved.' })
      else setStatus({ ok: false, msg: 'Save failed.' })
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setSaving(false)
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-sm py-4">
        <Loader className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  if (!persona) return status ? <StatusMsg {...status} /> : null

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle icon={Sparkles} title="Tone" />
        <Slider
          label="Curiosity"
          description="How proactively Emily asks follow-up questions and explores topics."
          value={persona.curiosity}
          onChange={set('curiosity')}
        />
        <Slider
          label="Warmth"
          description="Emotional empathy and friendliness in responses."
          value={persona.warmth}
          onChange={set('warmth')}
        />
        <Slider
          label="Humor"
          description="Frequency of wit, wordplay, and light-heartedness."
          value={persona.humor}
          onChange={set('humor')}
        />
      </Card>

      <Card>
        <CardTitle icon={Brain} title="Communication Style" />
        <Slider
          label="Directness"
          description="How concise and assertive vs. hedged and exploratory Emily is."
          value={persona.directness}
          onChange={set('directness')}
        />
        <Slider
          label="Formality"
          description="Formal and professional vs. casual and conversational tone."
          value={persona.formality}
          onChange={set('formality')}
        />
      </Card>

      <div className="flex items-center gap-3 pt-1">
        <Btn loading={saving} onClick={save}>Save Personality</Btn>
        {status && <StatusMsg {...status} />}
      </div>
    </div>
  )
}

// ── Advanced tab ───────────────────────────────────────────────────────────

interface AdvancedData {
  stt_profile:            string
  stt_beam_size:          number
  llm_temperature:        number
  memory_backup_interval: number
  memory_decay_days:      number
  self_improve:           boolean
  track_perf:             boolean
  guest_mode:             boolean
  verify_timeout:         number
}

const STT_PROFILE_OPTIONS = [
  { value: 'fast',     label: 'Fast — lower latency, slightly less accurate' },
  { value: 'accurate', label: 'Accurate — best quality, slightly higher latency' },
]

const DECAY_OPTIONS = [
  { value: '30',   label: '30 days'             },
  { value: '90',   label: '90 days'             },
  { value: '180',  label: '180 days'            },
  { value: '365',  label: '1 year (default)'    },
  { value: '9999', label: 'Forever'             },
]

const TIMEOUT_OPTIONS = [
  { value: '15',    label: '15 minutes'                },
  { value: '30',    label: '30 minutes'                },
  { value: '60',    label: '1 hour (default)'          },
  { value: '240',   label: '4 hours'                   },
  { value: '99999', label: 'Never (not recommended)'   },
]

function AdvancedTab() {
  const [data, setData]     = useState<AdvancedData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    fetch(`${API}/settings/advanced`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setData)
      .catch(() => setStatus({ ok: false, msg: 'Could not load advanced settings.' }))
      .finally(() => setLoading(false))
  }, [])

  const set = <K extends keyof AdvancedData>(key: K) => (v: AdvancedData[K]) =>
    setData(d => d ? { ...d, [key]: v } : d)

  const save = async () => {
    if (!data) return
    setSaving(true); setStatus(null)
    try {
      const r = await fetch(`${API}/settings/advanced`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) setStatus({ ok: true, msg: 'Advanced settings saved.' })
      else setStatus({ ok: false, msg: 'Save failed.' })
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setSaving(false)
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-sm py-4">
        <Loader className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  if (!data) return status ? <StatusMsg {...status} /> : null

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle icon={Mic} title="Speech Recognition" />
        <div>
          <FieldLabel>STT Profile</FieldLabel>
          <Dropdown
            value={data.stt_profile}
            onChange={set('stt_profile')}
            options={STT_PROFILE_OPTIONS}
          />
        </div>
        <Slider
          label="Beam size"
          description="Larger beams improve accuracy but increase compute. Default: 5."
          value={data.stt_beam_size}
          onChange={set('stt_beam_size')}
          min={1} max={10} step={1}
        />
      </Card>

      <Card>
        <CardTitle icon={SlidersHorizontal} title="Language Model" />
        <Slider
          label="Temperature"
          description="Lower = more deterministic. Higher = more creative. Default: 0.7."
          value={data.llm_temperature}
          onChange={set('llm_temperature')}
          min={0.0} max={1.5} step={0.05}
        />
      </Card>

      <Card>
        <CardTitle icon={Brain} title="Memory & System" />
        <Slider
          label="Auto-backup interval (minutes)"
          description="How often Emily backs up episodic memory to disk."
          value={data.memory_backup_interval}
          onChange={set('memory_backup_interval')}
          min={5} max={120} step={5}
        />
        <div>
          <FieldLabel>Memory decay period</FieldLabel>
          <Dropdown
            value={String(data.memory_decay_days)}
            onChange={v => set('memory_decay_days')(Number(v))}
            options={DECAY_OPTIONS}
          />
        </div>
        <PermRow
          icon={Brain} label="Self-improvement"
          description="Allow Emily to evolve her prompts based on feedback and performance metrics."
          value={data.self_improve}
          onChange={set('self_improve')}
        />
        <PermRow
          icon={Eye} label="Performance tracking"
          description="Log response quality metrics to guide self-improvement."
          value={data.track_perf}
          onChange={set('track_perf')}
        />
        <PermRow
          icon={Lock} label="Guest mode"
          description="Allow people other than the owner to interact with Emily in limited mode."
          value={data.guest_mode}
          onChange={set('guest_mode')}
        />
        <div>
          <FieldLabel>Session verify timeout</FieldLabel>
          <Dropdown
            value={String(data.verify_timeout)}
            onChange={v => set('verify_timeout')(Number(v))}
            options={TIMEOUT_OPTIONS}
          />
        </div>
      </Card>

      <div className="flex items-center gap-3 pt-1">
        <Btn loading={saving} onClick={save}>Save Advanced</Btn>
        {status && <StatusMsg {...status} />}
      </div>
    </div>
  )
}

// ── Privacy tab ────────────────────────────────────────────────────────────

interface Permissions {
  vision_enabled:    boolean
  screen_capture:    boolean
  emotion_detection: boolean
  save_history:      boolean
  pii_scrub:         boolean
  encrypt_at_rest:   boolean
}

interface ToolPermissions {
  file_read:        boolean
  file_write:       boolean
  shell:            boolean
  code_execution:   boolean
  computer_control: boolean
  screen_awareness: boolean
  notifications:    boolean
  email:            boolean
  calendar:         boolean
  discord:          boolean
  web_search:       boolean
  web_fetch:        boolean
  home_assistant:   boolean
}

function PrivacyTab() {
  const [perms, setPerms]         = useState<Permissions | null>(null)
  const [tools, setTools]         = useState<ToolPermissions | null>(null)
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState<string | null>(null)
  const [status, setStatus]       = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    Promise.all([
      fetch(`${API}/settings/permissions`).then(r => r.ok ? r.json() : null),
      fetch(`${API}/settings/tools`).then(r => r.ok ? r.json() : null),
    ]).then(([p, t]) => {
      if (p) setPerms(p)
      if (t) setTools(t)
      if (!p && !t) setStatus({ ok: false, msg: 'Could not load permissions — is the API running?' })
    }).finally(() => setLoading(false))
  }, [])

  const toggle = async (key: keyof Permissions, value: boolean) => {
    if (!perms) return
    const prev = perms[key]
    setPerms({ ...perms, [key]: value })
    setSaving(key)
    try {
      const r = await fetch(`${API}/settings/permissions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
      if (!r.ok) { setPerms({ ...perms, [key]: prev }); setStatus({ ok: false, msg: 'Failed to save.' }) }
      else setStatus(null)
    } catch {
      setPerms({ ...perms, [key]: prev })
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setSaving(null)
  }

  const toggleTool = async (key: keyof ToolPermissions, value: boolean) => {
    if (!tools) return
    const prev = tools[key]
    setTools({ ...tools, [key]: value })
    setSaving(`tool_${key}`)
    try {
      const r = await fetch(`${API}/settings/tools`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
      if (!r.ok) { setTools({ ...tools, [key]: prev }); setStatus({ ok: false, msg: 'Failed to save.' }) }
      else setStatus(null)
    } catch {
      setTools({ ...tools, [key]: prev })
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setSaving(null)
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-sm py-4">
        <Loader className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  return (
    <div className="space-y-4">

      {/* ── Tool Access ─────────────────────────────────── */}
      {tools && <>
        <Card>
          <CardTitle icon={Shield} title="Tool Access" />
          <p className="text-xs text-text-muted -mt-1">
            Control exactly what Emily can do on your computer. Disabled tools return an error when called.
          </p>
        </Card>

        <Card>
          <CardTitle icon={FolderOpen} title="Files & System" />
          <PermRow
            icon={FolderOpen} label="Read files"
            description={`Read files within allowed paths (/home/supernovyl).`}
            value={tools.file_read}
            onChange={v => toggleTool('file_read', v)}
            disabled={saving === 'tool_file_read'}
          />
          <PermRow
            icon={FolderOpen} label="Write files"
            description="Create and modify files. Always requires your approval before writing."
            value={tools.file_write}
            onChange={v => toggleTool('file_write', v)}
            disabled={saving === 'tool_file_write'}
          />
          <PermRow
            icon={Terminal} label="Shell commands"
            description="Run terminal commands. Always requires your approval before executing."
            value={tools.shell}
            onChange={v => toggleTool('shell', v)}
            disabled={saving === 'tool_shell'}
          />
          <PermRow
            icon={Cpu} label="Code execution"
            description="Execute Python/JS code in a sandboxed environment via bubblewrap."
            value={tools.code_execution}
            onChange={v => toggleTool('code_execution', v)}
            disabled={saving === 'tool_code_execution'}
          />
        </Card>

        <Card>
          <CardTitle icon={Monitor} title="Computer Control" />
          <PermRow
            icon={Monitor} label="Open apps & files"
            description="Launch applications and open files using xdg-open."
            value={tools.computer_control}
            onChange={v => toggleTool('computer_control', v)}
            disabled={saving === 'tool_computer_control'}
          />
          <PermRow
            icon={Eye} label="Screen & system awareness"
            description="Read active windows, running processes, clipboard, and take screenshots."
            value={tools.screen_awareness}
            onChange={v => toggleTool('screen_awareness', v)}
            disabled={saving === 'tool_screen_awareness'}
          />
          <PermRow
            icon={Bell} label="System notifications"
            description="Send desktop notifications via libnotify."
            value={tools.notifications}
            onChange={v => toggleTool('notifications', v)}
            disabled={saving === 'tool_notifications'}
          />
        </Card>

        <Card>
          <CardTitle icon={Mail} title="Communication" />
          <PermRow
            icon={Mail} label="Email (read)"
            description="Read emails via IMAP. Configure credentials in .env."
            value={tools.email}
            onChange={v => toggleTool('email', v)}
            disabled={saving === 'tool_email'}
          />
          <PermRow
            icon={CalendarDays} label="Calendar"
            description="Read calendar events from the local calendar store."
            value={tools.calendar}
            onChange={v => toggleTool('calendar', v)}
            disabled={saving === 'tool_calendar'}
          />
          <PermRow
            icon={MessageSquare} label="Discord"
            description="Send and read Discord messages. Requires DISCORD_BOT_TOKEN in .env."
            value={tools.discord}
            onChange={v => toggleTool('discord', v)}
            disabled={saving === 'tool_discord'}
          />
        </Card>

        <Card>
          <CardTitle icon={Globe} title="Internet & Integrations" />
          <PermRow
            icon={Search} label="Web search"
            description="Search the web via the configured search endpoint."
            value={tools.web_search}
            onChange={v => toggleTool('web_search', v)}
            disabled={saving === 'tool_web_search'}
          />
          <PermRow
            icon={Globe} label="Web fetch / browse"
            description="Fetch and read content from any URL."
            value={tools.web_fetch}
            onChange={v => toggleTool('web_fetch', v)}
            disabled={saving === 'tool_web_fetch'}
          />
          <PermRow
            icon={Home} label="Home Assistant"
            description="Control smart home devices. Requires HA URL and token in config."
            value={tools.home_assistant}
            onChange={v => toggleTool('home_assistant', v)}
            disabled={saving === 'tool_home_assistant'}
          />
        </Card>
      </>}

      {/* ── Vision & Perception ─────────────────────────── */}
      {perms && <>
        <Card>
          <CardTitle icon={Eye} title="Vision & Perception" />
          <PermRow
            icon={Eye} label="Camera (webcam)"
            description="Allow Emily to see through your webcam for emotion detection and context."
            value={perms.vision_enabled}
            onChange={v => toggle('vision_enabled', v)}
            disabled={saving === 'vision_enabled'}
          />
          <PermRow
            icon={Eye} label="Screen capture"
            description="Periodically capture your screen so Emily can understand what you're working on."
            value={perms.screen_capture}
            onChange={v => toggle('screen_capture', v)}
            disabled={saving === 'screen_capture'}
          />
          <PermRow
            icon={Eye} label="Emotion detection"
            description="Analyse facial expressions from webcam to adapt Emily's tone and responses."
            value={perms.emotion_detection}
            onChange={v => toggle('emotion_detection', v)}
            disabled={!perms.vision_enabled || saving === 'emotion_detection'}
          />
        </Card>

        <Card>
          <CardTitle icon={Brain} title="Memory" />
          <PermRow
            icon={Brain} label="Save conversation history"
            description="Store every conversation turn so Emily remembers past interactions across sessions."
            value={perms.save_history}
            onChange={v => toggle('save_history', v)}
            disabled={saving === 'save_history'}
          />
        </Card>

        <Card>
          <CardTitle icon={Lock} title="Data Protection" />
          <PermRow
            icon={Lock} label="Scrub personal information"
            description="Automatically redact names, emails, phone numbers and other PII from stored logs."
            value={perms.pii_scrub}
            onChange={v => toggle('pii_scrub', v)}
            disabled={saving === 'pii_scrub'}
          />
          <PermRow
            icon={Lock} label="Encrypt data at rest"
            description="Encrypt stored memories and conversation history on disk."
            value={perms.encrypt_at_rest}
            onChange={v => toggle('encrypt_at_rest', v)}
            disabled={saving === 'encrypt_at_rest'}
          />
        </Card>
      </>}

      {status && <StatusMsg {...status} />}

      <p className="text-xs text-text-muted px-1">
        Changes take effect immediately for this session. Restart Emily to apply permanently.
      </p>
    </div>
  )
}

// ── Security tab ───────────────────────────────────────────────────────────

function SecurityTab() {
  const [current, setCurrent] = useState('')
  const [next, setNext]       = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)

  const reset = async () => {
    if (!current || !next) return setStatus({ ok: false, msg: 'All fields are required.' })
    if (next !== confirm)  return setStatus({ ok: false, msg: 'Passphrases do not match.' })
    setLoading(true); setStatus(null)
    try {
      const r = await fetch(`${API}/settings/password/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_passphrase: current, new_passphrase: next }),
      })
      const d = await r.json()
      if (r.ok) {
        setStatus({ ok: true, msg: 'Passphrase updated.' })
        setCurrent(''); setNext(''); setConfirm('')
      } else setStatus({ ok: false, msg: d.detail || 'Reset failed.' })
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setLoading(false)
  }

  return (
    <Card>
      <CardTitle icon={Key} title="Change Passphrase" />
      <p className="text-sm text-text-muted">
        Your passphrase verifies your identity during voice conversations.
      </p>
      <div><FieldLabel>Current passphrase</FieldLabel><TextInput type="password" value={current} onChange={e => setCurrent(e.target.value)} /></div>
      <div><FieldLabel>New passphrase</FieldLabel><TextInput type="password" value={next} onChange={e => setNext(e.target.value)} /></div>
      <div><FieldLabel>Confirm new passphrase</FieldLabel><TextInput type="password" value={confirm} onChange={e => setConfirm(e.target.value)} /></div>
      <div className="flex items-center gap-3 pt-1">
        <Btn loading={loading} onClick={reset}>Reset Passphrase</Btn>
        {status && <StatusMsg {...status} />}
      </div>
    </Card>
  )
}

// ── Skills tab ─────────────────────────────────────────────────────────────

interface SkillData {
  name: string; icon: string; description: string
  system_addition: string; temperature: number
  enable_thinking: boolean; enable_code_execution: boolean
  builtin: boolean
}

const BLANK_SKILL: Omit<SkillData, 'builtin'> = {
  name: '', icon: '🤖', description: '', system_addition: '',
  temperature: 0.5, enable_thinking: false, enable_code_execution: false,
}

function SkillModal({
  skillId, initial, onClose, onSaved,
}: {
  skillId: string | null   // null = new
  initial: Omit<SkillData, 'builtin'>
  onClose: () => void
  onSaved: (id: string) => void
}) {
  const [form, setForm] = useState({ ...initial })
  const [id, setId]   = useState(skillId ?? '')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const set = <K extends keyof typeof form>(k: K) => (v: typeof form[K]) =>
    setForm(f => ({ ...f, [k]: v }))

  const save = async () => {
    const sid = id.trim().replace(/\s+/g, '_').toLowerCase()
    if (!sid || !form.name.trim()) return setErr('ID and Name are required.')
    setSaving(true); setErr('')
    try {
      const r = await fetch(`${API}/settings/skills/${sid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (r.ok) onSaved(sid)
      else setErr((await r.json()).detail || 'Save failed.')
    } catch { setErr('Network error.') }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-surface-raised border border-border rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <span className="font-semibold text-text-primary">{skillId ? 'Edit Skill' : 'New Skill'}</span>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4 overflow-y-auto max-h-[70vh]">
          {!skillId && (
            <div>
              <FieldLabel>Skill ID (e.g. my_skill)</FieldLabel>
              <TextInput value={id} onChange={e => setId(e.target.value)} placeholder="my_skill" />
            </div>
          )}
          <div className="flex gap-3">
            <div className="w-20">
              <FieldLabel>Icon</FieldLabel>
              <TextInput value={form.icon} onChange={e => set('icon')(e.target.value)} placeholder="🤖" />
            </div>
            <div className="flex-1">
              <FieldLabel>Name</FieldLabel>
              <TextInput value={form.name} onChange={e => set('name')(e.target.value)} placeholder="My Skill" />
            </div>
          </div>
          <div>
            <FieldLabel>Description</FieldLabel>
            <TextInput value={form.description} onChange={e => set('description')(e.target.value)} placeholder="What this skill does" />
          </div>
          <div>
            <FieldLabel>System prompt addition</FieldLabel>
            <textarea
              value={form.system_addition}
              onChange={e => set('system_addition')(e.target.value)}
              rows={5}
              placeholder="Extra instructions injected into Emily's system prompt when this skill is active..."
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary
                         placeholder-text-muted focus:outline-none focus:border-accent transition-colors resize-y"
            />
          </div>
          <Slider label="Temperature" min={0} max={2} step={0.05}
            value={form.temperature} onChange={set('temperature')}
            description="Higher = more creative. 0.1 for code, 0.5 for chat, 1.0 for brainstorm." />
          <div className="flex gap-6">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
              <Toggle enabled={form.enable_thinking} onChange={set('enable_thinking')} />
              Extended thinking
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary">
              <Toggle enabled={form.enable_code_execution} onChange={set('enable_code_execution')} />
              Code execution
            </label>
          </div>
          {err && <StatusMsg ok={false} msg={err} />}
        </div>
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border">
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn loading={saving} onClick={save}>Save Skill</Btn>
        </div>
      </div>
    </div>
  )
}

function SkillsTab() {
  const [skills, setSkills] = useState<Record<string, SkillData>>({})
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<{ skillId: string | null; data: Omit<SkillData, 'builtin'> } | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/settings/skills`)
      if (r.ok) setSkills(await r.json())
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const del = async (id: string) => {
    setDeleting(id)
    try {
      await fetch(`${API}/settings/skills/${id}`, { method: 'DELETE' })
      await load()
    } finally { setDeleting(null) }
  }

  if (loading) return <div className="flex items-center gap-2 text-text-muted text-sm py-4"><Loader className="w-4 h-4 animate-spin" /> Loading…</div>

  const builtins = Object.entries(skills).filter(([, s]) => s.builtin)
  const customs  = Object.entries(skills).filter(([, s]) => !s.builtin)

  return (
    <div className="space-y-4">
      {modal && (
        <SkillModal
          skillId={modal.skillId}
          initial={modal.data}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load() }}
        />
      )}

      <div className="flex items-center justify-between">
        <p className="text-xs text-text-muted">Create custom skills that change Emily's behaviour, temperature, and system prompt.</p>
        <Btn variant="ghost" onClick={() => setModal({ skillId: null, data: { ...BLANK_SKILL } })}>
          <Plus className="w-3.5 h-3.5" /> New Skill
        </Btn>
      </div>

      {customs.length > 0 && (
        <Card>
          <CardTitle icon={Zap} title="Custom Skills" />
          <div className="space-y-0">
            {customs.map(([id, s]) => (
              <div key={id} className="flex items-center justify-between gap-3 py-3 border-b border-border last:border-0">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-xl w-7 text-center">{s.icon || '🤖'}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-text-primary">{s.name}</div>
                    <div className="text-xs text-text-muted truncate">{s.description || <span className="italic">No description</span>}</div>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={() => setModal({ skillId: id, data: { name: s.name, icon: s.icon, description: s.description, system_addition: s.system_addition, temperature: s.temperature, enable_thinking: s.enable_thinking, enable_code_execution: s.enable_code_execution } })}
                    className="p-1.5 rounded-lg hover:bg-white/5 text-text-muted hover:text-accent transition-colors">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => del(id)} disabled={deleting === id}
                    className="p-1.5 rounded-lg hover:bg-white/5 text-text-muted hover:text-red-400 transition-colors disabled:opacity-50">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <CardTitle icon={Bot} title="Built-in Skills" />
        <p className="text-xs text-text-muted -mt-1">Built-in skills can't be deleted. Click Edit to duplicate and customise.</p>
        <div className="space-y-0">
          {builtins.map(([id, s]) => (
            <div key={id} className="flex items-center justify-between gap-3 py-2.5 border-b border-border last:border-0">
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-lg w-7 text-center">{s.icon || '🤖'}</span>
                <div className="min-w-0">
                  <div className="text-sm text-text-primary">{s.name}</div>
                  <div className="text-xs text-text-muted truncate">{s.description}</div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {s.enable_thinking && <span className="text-[9px] font-mono text-violet-400 bg-violet-400/10 px-1.5 py-0.5 rounded">thinking</span>}
                <span className="text-[9px] font-mono text-text-muted">{s.temperature.toFixed(1)}°</span>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ── Plugins tab ─────────────────────────────────────────────────────────────

const PLUGIN_GROUPS = [
  {
    id: 'files',
    title: 'Files & System',
    icon: FolderOpen,
    tools: [
      { key: 'file_read',        label: 'Read files',       desc: 'Read files from disk within allowed paths.' },
      { key: 'file_write',       label: 'Write files',      desc: 'Create, edit and delete files.' },
      { key: 'shell',            label: 'Shell commands',   desc: 'Run terminal commands and scripts.' },
      { key: 'code_execution',   label: 'Code execution',   desc: 'Execute Python/JS/Bash snippets in a sandbox.' },
    ],
  },
  {
    id: 'computer',
    title: 'Computer Control',
    icon: Monitor,
    tools: [
      { key: 'computer_control', label: 'Open apps & URLs',  desc: 'Launch applications and open URLs in the browser.' },
      { key: 'screen_awareness', label: 'Screen & processes', desc: 'Read screen text, clipboard, active window and process list.' },
    ],
  },
  {
    id: 'comms',
    title: 'Communication',
    icon: MessageSquare,
    tools: [
      { key: 'notifications',    label: 'Notifications',    desc: 'Send desktop notifications.' },
      { key: 'email',            label: 'Email (read)',      desc: 'Read emails from configured inbox.' },
      { key: 'calendar',         label: 'Calendar',         desc: 'Read and create calendar events.' },
      { key: 'discord',          label: 'Discord',          desc: 'Send messages to Discord channels (requires bot token).' },
    ],
  },
  {
    id: 'internet',
    title: 'Internet',
    icon: Globe,
    tools: [
      { key: 'web_search',       label: 'Web search',       desc: 'Search the web via SearXNG.' },
      { key: 'web_fetch',        label: 'Web fetch',        desc: 'Fetch and read any webpage.' },
      { key: 'home_assistant',   label: 'Home Assistant',   desc: 'Control smart home devices (requires HA URL + token).' },
    ],
  },
] as const

type ToolKey = typeof PLUGIN_GROUPS[number]['tools'][number]['key']

function PluginsTab() {
  const [tools, setTools]   = useState<Record<string, boolean> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState<string | null>(null)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    fetch(`${API}/settings/tools`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setTools(d) })
      .finally(() => setLoading(false))
  }, [])

  const toggle = async (key: ToolKey, value: boolean) => {
    if (!tools) return
    const prev = tools[key]
    setTools({ ...tools, [key]: value })
    setSaving(key)
    try {
      const r = await fetch(`${API}/settings/tools`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
      if (!r.ok) { setTools({ ...tools, [key]: prev }); setStatus({ ok: false, msg: 'Failed to save.' }) }
      else setStatus(null)
    } catch { setTools({ ...tools, [key]: prev }); setStatus({ ok: false, msg: 'Network error.' }) }
    setSaving(null)
  }

  if (loading) return <div className="flex items-center gap-2 text-text-muted text-sm py-4"><Loader className="w-4 h-4 animate-spin" /> Loading…</div>

  return (
    <div className="space-y-4">
      <p className="text-xs text-text-muted px-1">Enable or disable each capability group. Disabled tools return an error when Emily tries to use them.</p>
      {PLUGIN_GROUPS.map(group => (
        <Card key={group.id}>
          <CardTitle icon={group.icon} title={group.title} />
          {group.tools.map(tool => (
            <PermRow
              key={tool.key}
              icon={group.icon}
              label={tool.label}
              description={tool.desc}
              value={tools?.[tool.key] ?? true}
              onChange={v => toggle(tool.key as ToolKey, v)}
              disabled={saving === tool.key}
            />
          ))}
        </Card>
      ))}
      {status && <StatusMsg {...status} />}
      <p className="text-xs text-text-muted px-1">Changes take effect immediately for this session.</p>
    </div>
  )
}

// ── Rules tab ───────────────────────────────────────────────────────────────

function RulesTab() {
  const [rules, setRules]   = useState<string[]>([])
  const [input, setInput]   = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [status, setStatus]   = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    fetch(`${API}/settings/rules`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.rules) setRules(d.rules) })
      .finally(() => setLoading(false))
  }, [])

  const save = async (newRules: string[]) => {
    setSaving(true); setStatus(null)
    try {
      const r = await fetch(`${API}/settings/rules`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules: newRules }),
      })
      if (r.ok) { setStatus({ ok: true, msg: 'Rules saved.' }); setTimeout(() => setStatus(null), 2000) }
      else setStatus({ ok: false, msg: 'Save failed.' })
    } catch { setStatus({ ok: false, msg: 'Network error.' }) }
    setSaving(false)
  }

  const add = () => {
    const trimmed = input.trim()
    if (!trimmed || rules.includes(trimmed)) return
    const next = [...rules, trimmed]
    setRules(next); setInput(''); save(next)
  }

  const remove = (i: number) => {
    const next = rules.filter((_, j) => j !== i)
    setRules(next); save(next)
  }

  if (loading) return <div className="flex items-center gap-2 text-text-muted text-sm py-4"><Loader className="w-4 h-4 animate-spin" /> Loading…</div>

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle icon={BookOpen} title="Behavior Rules" />
        <p className="text-xs text-text-muted -mt-1">
          Rules are injected into Emily's system prompt on every request. Use them for permanent instructions like "always reply in English" or "never mention competitors".
        </p>

        {rules.length === 0 ? (
          <p className="text-xs text-text-muted italic py-2">No rules yet. Add your first rule below.</p>
        ) : (
          <div className="space-y-1">
            {rules.map((rule, i) => (
              <div key={i} className="flex items-start gap-2 bg-surface rounded-lg px-3 py-2 group">
                <span className="text-xs text-accent font-mono shrink-0 mt-0.5">{i + 1}.</span>
                <span className="text-sm text-text-primary flex-1 leading-relaxed">{rule}</span>
                <button
                  onClick={() => remove(i)}
                  className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-red-400 transition-all p-0.5 shrink-0"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <TextInput
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && add()}
            placeholder="e.g. Always reply in English"
            className="flex-1"
          />
          <Btn onClick={add} loading={saving} disabled={!input.trim()}>
            <Plus className="w-3.5 h-3.5" /> Add
          </Btn>
        </div>
        {status && <StatusMsg {...status} />}
      </Card>

      <Card>
        <CardTitle icon={Zap} title="Example Rules" />
        <div className="space-y-1">
          {[
            'Always reply in English regardless of the language I write in.',
            'Keep all responses under 200 words unless I explicitly ask for more.',
            'Never use bullet points — always write in flowing prose.',
            'Always end code blocks with a brief explanation of what the code does.',
            "When you're unsure, say so explicitly rather than guessing.",
          ].map(ex => (
            <button key={ex} onClick={() => setInput(ex)}
              className="w-full text-left text-xs text-text-muted hover:text-text-secondary px-2 py-1 rounded hover:bg-white/5 transition-colors">
              + {ex}
            </button>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('profile')

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Tab bar */}
      <div className="flex border-b border-border px-6 shrink-0 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap ${
              tab === id
                ? 'border-accent text-accent'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-lg mx-auto">
          {tab === 'profile'     && <ProfileTab />}
          {tab === 'audio'       && <AudioTab />}
          {tab === 'voice'       && <VoiceTab />}
          {tab === 'personality' && <PersonalityTab />}
          {tab === 'advanced'    && <AdvancedTab />}
          {tab === 'skills'      && <SkillsTab />}
          {tab === 'plugins'     && <PluginsTab />}
          {tab === 'rules'       && <RulesTab />}
          {tab === 'privacy'     && <PrivacyTab />}
          {tab === 'security'    && <SecurityTab />}
        </div>
      </div>
    </div>
  )
}
