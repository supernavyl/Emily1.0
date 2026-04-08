import { createSignal, onMount, Show } from 'solid-js'
import { User, Bot, Loader, CircleCheck, CircleAlert, Key } from 'lucide-solid'
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
  type?: string
}) {
  return (
    <input
      type={props.type ?? 'text'}
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

// ── Data types ────────────────────────────────────────────────────────────

interface ProfileData {
  has_owner: boolean
  name: string
  ai_name: string
  email: string
}

// ── Register form (no owner yet) ──────────────────────────────────────────

function RegisterForm(props: { onDone: () => void }) {
  const [name, setName] = createSignal('')
  const [aiName, setAiName] = createSignal('Emily')
  const [pass, setPass] = createSignal('')
  const [confirm, setConfirm] = createSignal('')
  const [loading, setLoading] = createSignal(false)
  const [status, setStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  const submit = async () => {
    if (!name().trim() || !pass().trim()) {
      setStatus({ ok: false, msg: 'Name and passphrase are required.' })
      return
    }
    if (pass() !== confirm()) {
      setStatus({ ok: false, msg: 'Passphrases do not match.' })
      return
    }
    setLoading(true)
    try {
      const r = await fetch(`${API_RAW}/settings/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name().trim(), passphrase: pass(), ai_name: aiName().trim() || 'Emily' }),
      })
      const d = await r.json()
      if (r.ok) {
        setStatus({ ok: true, msg: d.message })
        setTimeout(() => props.onDone(), 1200)
      } else {
        setStatus({ ok: false, msg: d.detail || 'Registration failed.' })
      }
    } catch {
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setLoading(false)
  }

  return (
    <div style={cardStyle} class="space-y-4">
      <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
        <User size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
        First-time Setup
      </div>
      <p class="text-sm" style={{ color: 'oklch(0.55 0.03 185)' }}>
        No owner registered yet. Set up your profile to get started.
      </p>
      <div><FieldLabel>Your name</FieldLabel><TextInput value={name()} onInput={setName} placeholder="e.g. Alex" /></div>
      <div><FieldLabel>AI name</FieldLabel><TextInput value={aiName()} onInput={setAiName} placeholder="Emily" /></div>
      <div><FieldLabel>Passphrase</FieldLabel><TextInput type="password" value={pass()} onInput={setPass} placeholder="Choose a passphrase" /></div>
      <div><FieldLabel>Confirm passphrase</FieldLabel><TextInput type="password" value={confirm()} onInput={setConfirm} placeholder="Repeat passphrase" /></div>
      <div class="flex items-center gap-3 pt-1">
        <Btn loading={loading()} onClick={submit}>Create Profile</Btn>
        <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
      </div>
    </div>
  )
}

// ── Profile settings ──────────────────────────────────────────────────────

function ProfileSettings() {
  const [data, setData] = createSignal<ProfileData | null>(null)
  const [aiName, setAiName] = createSignal('')
  const [email, setEmail] = createSignal('')
  const [loading, setLoading] = createSignal(true)
  const [saving, setSaving] = createSignal(false)
  const [status, setStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  // Passphrase change
  const [current, setCurrent] = createSignal('')
  const [next, setNext] = createSignal('')
  const [confirmPass, setConfirmPass] = createSignal('')
  const [passLoading, setPassLoading] = createSignal(false)
  const [passStatus, setPassStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API_RAW}/settings/profile`)
      if (!r.ok) throw new Error()
      const d: ProfileData = await r.json()
      setData(d)
      setAiName(d.ai_name)
      setEmail(d.email)
    } catch {
      setStatus({ ok: false, msg: 'Could not load profile -- is the API running?' })
    }
    setLoading(false)
  }

  onMount(() => { void load() })

  const save = async () => {
    setSaving(true)
    setStatus(null)
    try {
      const r = await fetch(`${API_RAW}/settings/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ai_name: aiName().trim() || undefined,
          email: email().trim() || undefined,
        }),
      })
      const d = await r.json()
      if (r.ok) setStatus({ ok: true, msg: 'Saved.' })
      else setStatus({ ok: false, msg: d.detail || 'Save failed.' })
    } catch {
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setSaving(false)
  }

  const resetPassphrase = async () => {
    if (!current() || !next()) {
      setPassStatus({ ok: false, msg: 'All fields are required.' })
      return
    }
    if (next() !== confirmPass()) {
      setPassStatus({ ok: false, msg: 'Passphrases do not match.' })
      return
    }
    setPassLoading(true)
    setPassStatus(null)
    try {
      const r = await fetch(`${API_RAW}/settings/password/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_passphrase: current(), new_passphrase: next() }),
      })
      const d = await r.json()
      if (r.ok) {
        setPassStatus({ ok: true, msg: 'Passphrase updated.' })
        setCurrent('')
        setNext('')
        setConfirmPass('')
      } else {
        setPassStatus({ ok: false, msg: d.detail || 'Reset failed.' })
      }
    } catch {
      setPassStatus({ ok: false, msg: 'Network error.' })
    }
    setPassLoading(false)
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
      <Show when={data()?.has_owner} fallback={<RegisterForm onDone={load} />}>
        <div class="space-y-4">
          {/* Owner card */}
          <div style={cardStyle} class="space-y-4">
            <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
              <User size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
              Owner
            </div>
            <div>
              <FieldLabel>Name</FieldLabel>
              <div
                class="px-3 py-2 rounded-lg text-sm"
                style={{
                  background: 'oklch(0.18 0.02 185)',
                  border: '1px solid oklch(0.30 0.02 185)',
                  color: 'oklch(0.75 0.03 185)',
                }}
              >
                {data()!.name}
              </div>
            </div>
          </div>

          {/* AI Identity card */}
          <div style={cardStyle} class="space-y-4">
            <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
              <Bot size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
              AI Identity
            </div>
            <div><FieldLabel>AI name</FieldLabel><TextInput value={aiName()} onInput={setAiName} placeholder="Emily" /></div>
            <div><FieldLabel>Recovery email</FieldLabel><TextInput type="email" value={email()} onInput={setEmail} placeholder="you@example.com" /></div>
            <div class="flex items-center gap-3 pt-1">
              <Btn loading={saving()} onClick={save}>Save</Btn>
              <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
            </div>
          </div>

          {/* Change passphrase card */}
          <div style={cardStyle} class="space-y-4">
            <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
              <Key size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
              Change Passphrase
            </div>
            <p class="text-sm" style={{ color: 'oklch(0.55 0.03 185)' }}>
              Your passphrase verifies your identity during voice conversations.
            </p>
            <div><FieldLabel>Current passphrase</FieldLabel><TextInput type="password" value={current()} onInput={setCurrent} /></div>
            <div><FieldLabel>New passphrase</FieldLabel><TextInput type="password" value={next()} onInput={setNext} /></div>
            <div><FieldLabel>Confirm new passphrase</FieldLabel><TextInput type="password" value={confirmPass()} onInput={setConfirmPass} /></div>
            <div class="flex items-center gap-3 pt-1">
              <Btn loading={passLoading()} onClick={resetPassphrase}>Reset Passphrase</Btn>
              <Show when={passStatus()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>
            </div>
          </div>
        </div>
      </Show>
    </Show>
  )
}

export default ProfileSettings
