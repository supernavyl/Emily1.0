import { createSignal, onMount, Show } from 'solid-js'
import { Sparkles, Brain, Loader, CircleCheck, CircleAlert } from 'lucide-solid'
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

function Btn(props: {
  loading?: boolean
  disabled?: boolean
  onClick: () => void
  children: string
}) {
  return (
    <button
      disabled={props.loading || props.disabled}
      onClick={() => props.onClick()}
      class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
      style={{
        background: 'oklch(0.72 0.17 162)',
        color: 'oklch(0.18 0.02 185)',
      }}
    >
      <Show when={props.loading}>
        <Loader size={14} class="animate-spin" />
      </Show>
      {props.children}
    </button>
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
          <span
            class="text-xs uppercase tracking-wider font-medium"
            style={{ color: 'oklch(0.55 0.03 185)' }}
          >
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

interface PersonaData {
  curiosity: number
  warmth: number
  directness: number
  humor: number
  formality: number
}

// ── Component ─────────────────────────────────────────────────────────────

function PersonaSettings() {
  const [persona, setPersona] = createSignal<PersonaData | null>(null)
  const [loading, setLoading] = createSignal(true)
  const [saving, setSaving] = createSignal(false)
  const [status, setStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  onMount(() => {
    fetch(`${API_RAW}/settings/persona`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: PersonaData) => setPersona(d))
      .catch(() => setStatus({ ok: false, msg: 'Could not load personality settings.' }))
      .finally(() => setLoading(false))
  })

  const set = (key: keyof PersonaData) => (v: number) => {
    const p = persona()
    if (p) setPersona({ ...p, [key]: v })
  }

  const save = async () => {
    const p = persona()
    if (!p) return
    setSaving(true)
    setStatus(null)
    try {
      const r = await fetch(`${API_RAW}/settings/persona`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p),
      })
      if (r.ok) setStatus({ ok: true, msg: 'Personality saved.' })
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
      <Show when={persona()} fallback={
        <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
      }>
        {(p) => (
          <div class="space-y-4">
            {/* Tone card */}
            <div style={cardStyle} class="space-y-4">
              <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
                <Sparkles size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                Tone
              </div>
              <Slider
                label="Curiosity"
                description="How proactively Emily asks follow-up questions and explores topics."
                value={p().curiosity}
                onChange={set('curiosity')}
              />
              <Slider
                label="Warmth"
                description="Emotional empathy and friendliness in responses."
                value={p().warmth}
                onChange={set('warmth')}
              />
              <Slider
                label="Humor"
                description="Frequency of wit, wordplay, and light-heartedness."
                value={p().humor}
                onChange={set('humor')}
              />
            </div>

            {/* Communication style card */}
            <div style={cardStyle} class="space-y-4">
              <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
                <Brain size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                Communication Style
              </div>
              <Slider
                label="Directness"
                description="How concise and assertive vs. hedged and exploratory Emily is."
                value={p().directness}
                onChange={set('directness')}
              />
              <Slider
                label="Formality"
                description="Formal and professional vs. casual and conversational tone."
                value={p().formality}
                onChange={set('formality')}
              />
            </div>

            <div class="flex items-center gap-3 pt-1">
              <Btn loading={saving()} onClick={save}>Save Personality</Btn>
              <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
            </div>
          </div>
        )}
      </Show>
    </Show>
  )
}

export default PersonaSettings
