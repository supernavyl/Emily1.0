import { createSignal, onMount, Show, For } from 'solid-js'
import {
  Mic, SlidersHorizontal, Brain, Eye, Lock, Loader,
  CircleCheck, CircleAlert, ChevronDown, Check,
  BookOpen, Plus, Trash2, Zap,
} from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'
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
  onKeyDown?: (e: KeyboardEvent) => void
}) {
  return (
    <input
      type="text"
      value={props.value}
      onInput={(e) => props.onInput(e.currentTarget.value)}
      onKeyDown={props.onKeyDown}
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

function Toggle(props: { enabled: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={props.enabled}
      onClick={() => !props.disabled && props.onChange(!props.enabled)}
      disabled={props.disabled}
      class="relative w-10 h-5 rounded-full transition-colors duration-200 shrink-0 disabled:opacity-40"
      style={{ background: props.enabled ? 'oklch(0.72 0.17 162)' : 'oklch(0.30 0.02 185)' }}
    >
      <span
        class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200"
        style={{ transform: props.enabled ? 'translateX(20px)' : 'translateX(0)' }}
      />
    </button>
  )
}

function PermRow(props: {
  icon: LucideIcon
  label: string
  description: string
  value: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  const Icon = props.icon
  return (
    <div class="flex items-start justify-between gap-4 py-3" style={{ 'border-bottom': '1px solid oklch(0.30 0.02 185)' }}>
      <div class="flex items-start gap-3 min-w-0">
        <Icon size={16} class="mt-0.5 shrink-0" style={{ color: 'oklch(0.55 0.03 185)' }} />
        <div class="min-w-0">
          <div class="text-sm font-medium" style={{ color: 'oklch(0.93 0.01 90)' }}>{props.label}</div>
          <div class="text-xs mt-0.5" style={{ color: 'oklch(0.55 0.03 185)' }}>{props.description}</div>
        </div>
      </div>
      <Toggle enabled={props.value} onChange={props.onChange} disabled={props.disabled} />
    </div>
  )
}

function Dropdown(props: {
  value: string
  onChange: (v: string) => void
  options: Array<{ value: string; label: string }>
  disabled?: boolean
}) {
  const [open, setOpen] = createSignal(false)
  let ref: HTMLDivElement | undefined

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
        <span>{selected()?.label ?? props.value}</span>
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

function Slider(props: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  label?: string
  description?: string
}) {
  const min = () => props.min ?? 0
  const max = () => props.max ?? 1
  const step = () => props.step ?? 0.05
  const display = () => step() >= 1 ? String(Math.round(props.value)) : props.value.toFixed(2)

  return (
    <div class="space-y-1.5">
      <Show when={props.label}>
        <div class="flex items-center justify-between">
          <span class="text-xs uppercase tracking-wider font-medium" style={{ color: 'oklch(0.55 0.03 185)' }}>
            {props.label}
          </span>
          <span
            class="text-xs font-mono px-1.5 py-0.5 rounded"
            style={{ color: 'oklch(0.72 0.17 162)', background: 'oklch(0.72 0.17 162 / 0.1)' }}
          >
            {display()}
          </span>
        </div>
      </Show>
      <input
        type="range"
        min={min()}
        max={max()}
        step={step()}
        value={props.value}
        onInput={(e) => props.onChange(Number(e.currentTarget.value))}
        class="w-full h-2 rounded-full appearance-none cursor-pointer"
        style={{ background: 'oklch(0.30 0.02 185)', 'accent-color': 'oklch(0.72 0.17 162)' }}
      />
      <Show when={props.description}>
        <p class="text-xs" style={{ color: 'oklch(0.55 0.03 185)' }}>{props.description}</p>
      </Show>
    </div>
  )
}

// ── Data types ────────────────────────────────────────────────────────────

interface AdvancedData {
  stt_profile: string
  stt_beam_size: number
  llm_temperature: number
  memory_backup_interval: number
  memory_decay_days: number
  self_improve: boolean
  track_perf: boolean
  guest_mode: boolean
  verify_timeout: number
}

const STT_PROFILE_OPTIONS = [
  { value: 'fast', label: 'Fast -- lower latency, slightly less accurate' },
  { value: 'accurate', label: 'Accurate -- best quality, slightly higher latency' },
]

const DECAY_OPTIONS = [
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '180', label: '180 days' },
  { value: '365', label: '1 year (default)' },
  { value: '9999', label: 'Forever' },
]

const TIMEOUT_OPTIONS = [
  { value: '15', label: '15 minutes' },
  { value: '30', label: '30 minutes' },
  { value: '60', label: '1 hour (default)' },
  { value: '240', label: '4 hours' },
  { value: '99999', label: 'Never (not recommended)' },
]

// ── Rules sub-section ─────────────────────────────────────────────────────

function RulesSection() {
  const [rules, setRules] = createSignal<string[]>([])
  const [input, setInput] = createSignal('')
  const [loading, setLoading] = createSignal(true)
  const [saving, setSaving] = createSignal(false)
  const [status, setStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  onMount(() => {
    fetch(`${API_RAW}/settings/rules`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { rules?: string[] } | null) => { if (d?.rules) setRules(d.rules) })
      .finally(() => setLoading(false))
  })

  const save = async (newRules: string[]) => {
    setSaving(true)
    setStatus(null)
    try {
      const r = await fetch(`${API_RAW}/settings/rules`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules: newRules }),
      })
      if (r.ok) {
        setStatus({ ok: true, msg: 'Rules saved.' })
        setTimeout(() => setStatus(null), 2000)
      } else {
        setStatus({ ok: false, msg: 'Save failed.' })
      }
    } catch {
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setSaving(false)
  }

  const add = () => {
    const trimmed = input().trim()
    if (!trimmed || rules().includes(trimmed)) return
    const next = [...rules(), trimmed]
    setRules(next)
    setInput('')
    void save(next)
  }

  const remove = (i: number) => {
    const next = rules().filter((_, j) => j !== i)
    setRules(next)
    void save(next)
  }

  const EXAMPLE_RULES = [
    'Always reply in English regardless of the language I write in.',
    'Keep all responses under 200 words unless I explicitly ask for more.',
    'Never use bullet points -- always write in flowing prose.',
    'Always end code blocks with a brief explanation of what the code does.',
    "When you're unsure, say so explicitly rather than guessing.",
  ]

  return (
    <Show
      when={!loading()}
      fallback={
        <div class="flex items-center gap-2 text-sm py-4" style={{ color: 'oklch(0.55 0.03 185)' }}>
          <Loader size={16} class="animate-spin" /> Loading...
        </div>
      }
    >
      <div class="space-y-4">
        <div style={cardStyle} class="space-y-4">
          <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
            <BookOpen size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
            Behavior Rules
          </div>
          <p class="text-xs -mt-1" style={{ color: 'oklch(0.55 0.03 185)' }}>
            Rules are injected into Emily's system prompt on every request.
          </p>

          <Show
            when={rules().length > 0}
            fallback={
              <p class="text-xs italic py-2" style={{ color: 'oklch(0.55 0.03 185)' }}>
                No rules yet. Add your first rule below.
              </p>
            }
          >
            <div class="space-y-1">
              <For each={rules()}>
                {(rule, i) => (
                  <div
                    class="flex items-start gap-2 rounded-lg px-3 py-2 group"
                    style={{ background: 'oklch(0.18 0.02 185)' }}
                  >
                    <span
                      class="text-xs font-mono shrink-0 mt-0.5"
                      style={{ color: 'oklch(0.72 0.17 162)' }}
                    >
                      {i() + 1}.
                    </span>
                    <span class="text-sm flex-1 leading-relaxed" style={{ color: 'oklch(0.93 0.01 90)' }}>
                      {rule}
                    </span>
                    <button
                      onClick={() => remove(i())}
                      class="opacity-0 group-hover:opacity-100 transition-all p-0.5 shrink-0"
                      style={{ color: 'oklch(0.55 0.03 185)' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </For>
            </div>
          </Show>

          <div class="flex gap-2 pt-1">
            <TextInput
              value={input()}
              onInput={setInput}
              onKeyDown={(e) => e.key === 'Enter' && add()}
              placeholder="e.g. Always reply in English"
            />
            <Btn onClick={add} loading={saving()} disabled={!input().trim()}>Add</Btn>
          </div>
          <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
        </div>

        <div style={cardStyle} class="space-y-2">
          <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
            <Zap size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
            Example Rules
          </div>
          <div class="space-y-1">
            <For each={EXAMPLE_RULES}>
              {(ex) => (
                <button
                  onClick={() => setInput(ex)}
                  class="w-full text-left text-xs px-2 py-1 rounded transition-colors"
                  style={{ color: 'oklch(0.55 0.03 185)' }}
                >
                  + {ex}
                </button>
              )}
            </For>
          </div>
        </div>
      </div>
    </Show>
  )
}

// ── Main component ────────────────────────────────────────────────────────

function AdvancedSettings() {
  const [data, setData] = createSignal<AdvancedData | null>(null)
  const [loading, setLoading] = createSignal(true)
  const [saving, setSaving] = createSignal(false)
  const [status, setStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  onMount(() => {
    fetch(`${API_RAW}/settings/advanced`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: AdvancedData) => setData(d))
      .catch(() => setStatus({ ok: false, msg: 'Could not load advanced settings.' }))
      .finally(() => setLoading(false))
  })

  const set = <K extends keyof AdvancedData>(key: K) => (v: AdvancedData[K]) => {
    const d = data()
    if (d) setData({ ...d, [key]: v })
  }

  const save = async () => {
    const d = data()
    if (!d) return
    setSaving(true)
    setStatus(null)
    try {
      const r = await fetch(`${API_RAW}/settings/advanced`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(d),
      })
      if (r.ok) setStatus({ ok: true, msg: 'Advanced settings saved.' })
      else setStatus({ ok: false, msg: 'Save failed.' })
    } catch {
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setSaving(false)
  }

  return (
    <Show
      when={!loading()}
      fallback={
        <div class="flex items-center gap-2 text-sm py-4" style={{ color: 'oklch(0.55 0.03 185)' }}>
          <Loader size={16} class="animate-spin" /> Loading...
        </div>
      }
    >
      <Show when={data()} fallback={
        <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
      }>
        {(d) => (
          <div class="space-y-4">
            {/* Speech Recognition */}
            <div style={cardStyle} class="space-y-4">
              <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
                <Mic size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                Speech Recognition
              </div>
              <div>
                <FieldLabel>STT Profile</FieldLabel>
                <Dropdown
                  value={d().stt_profile}
                  onChange={set('stt_profile')}
                  options={STT_PROFILE_OPTIONS}
                />
              </div>
              <Slider
                label="Beam size"
                description="Larger beams improve accuracy but increase compute. Default: 5."
                value={d().stt_beam_size}
                onChange={set('stt_beam_size')}
                min={1}
                max={10}
                step={1}
              />
            </div>

            {/* Language Model */}
            <div style={cardStyle} class="space-y-4">
              <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
                <SlidersHorizontal size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                Language Model
              </div>
              <Slider
                label="Temperature"
                description="Lower = more deterministic. Higher = more creative. Default: 0.7."
                value={d().llm_temperature}
                onChange={set('llm_temperature')}
                min={0.0}
                max={1.5}
                step={0.05}
              />
            </div>

            {/* Memory & System */}
            <div style={cardStyle} class="space-y-4">
              <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
                <Brain size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                Memory & System
              </div>
              <Slider
                label="Auto-backup interval (minutes)"
                description="How often Emily backs up episodic memory to disk."
                value={d().memory_backup_interval}
                onChange={set('memory_backup_interval')}
                min={5}
                max={120}
                step={5}
              />
              <div>
                <FieldLabel>Memory decay period</FieldLabel>
                <Dropdown
                  value={String(d().memory_decay_days)}
                  onChange={(v) => set('memory_decay_days')(Number(v))}
                  options={DECAY_OPTIONS}
                />
              </div>
              <PermRow
                icon={Brain}
                label="Self-improvement"
                description="Allow Emily to evolve her prompts based on feedback and performance metrics."
                value={d().self_improve}
                onChange={set('self_improve')}
              />
              <PermRow
                icon={Eye}
                label="Performance tracking"
                description="Log response quality metrics to guide self-improvement."
                value={d().track_perf}
                onChange={set('track_perf')}
              />
              <PermRow
                icon={Lock}
                label="Guest mode"
                description="Allow people other than the owner to interact with Emily in limited mode."
                value={d().guest_mode}
                onChange={set('guest_mode')}
              />
              <div>
                <FieldLabel>Session verify timeout</FieldLabel>
                <Dropdown
                  value={String(d().verify_timeout)}
                  onChange={(v) => set('verify_timeout')(Number(v))}
                  options={TIMEOUT_OPTIONS}
                />
              </div>
            </div>

            <div class="flex items-center gap-3 pt-1">
              <Btn loading={saving()} onClick={save}>Save Advanced</Btn>
              <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
            </div>

            {/* Rules section */}
            <div class="pt-4" style={{ 'border-top': '1px solid oklch(0.30 0.02 185)' }}>
              <RulesSection />
            </div>
          </div>
        )}
      </Show>
    </Show>
  )
}

export default AdvancedSettings
