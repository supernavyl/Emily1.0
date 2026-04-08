import { createSignal, onMount, Show } from 'solid-js'
import { Lock, Mail, ArrowLeft, Loader, CheckCircle, AlertCircle, ShieldOff } from 'lucide-solid'
import { setAuthenticated } from '../../stores/ui'
import { API_RAW } from '../../lib/env'

const API = API_RAW

type Screen = 'login' | 'forgot' | 'verify' | 'setup'

function StatusMsg(props: { ok: boolean; msg: string }) {
  return (
    <div class={`flex items-center gap-2 text-sm mt-2 ${props.ok ? 'text-cost-green' : 'text-error-red'}`}>
      <Show when={props.ok} fallback={<AlertCircle class="w-4 h-4" />}>
        <CheckCircle class="w-4 h-4" />
      </Show>
      {props.msg}
    </div>
  )
}

export function LoginScreen() {
  const [screen, setScreen] = createSignal<Screen>('login')
  const [passphrase, setPassphrase] = createSignal('')
  const [email, setEmail] = createSignal('')
  const [code, setCode] = createSignal('')
  const [newPass, setNewPass] = createSignal('')
  const [setupPass, setSetupPass] = createSignal('')
  const [loading, setLoading] = createSignal(false)
  const [status, setStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)
  const [passphraseSet, setPassphraseSet] = createSignal(true)

  // Check if passphrase has ever been configured
  onMount(() => {
    fetch(`${API}/settings/auth/status`)
      .then(r => r.json())
      .then((d: { has_owner?: boolean; passphrase_set?: boolean }) => {
        if (d.has_owner && !d.passphrase_set) {
          setPassphraseSet(false)
          setScreen('setup')
        }
      })
      .catch(() => { /* ignore */ })
  })

  const login = async () => {
    if (!passphrase().trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase: passphrase() }),
      })
      if (r.ok) {
        setAuthenticated(true)
      } else {
        const d = await r.json()
        setStatus({ ok: false, msg: d.detail || 'Invalid passphrase' })
      }
    } catch {
      setStatus({ ok: false, msg: 'Could not reach API' })
    }
    setLoading(false)
  }

  const forgot = async () => {
    if (!email().trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/forgot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email() }),
      })
      const d = await r.json()
      if (r.ok) {
        setStatus({ ok: true, msg: d.message })
        setScreen('verify')
      } else {
        setStatus({ ok: false, msg: d.detail || 'Failed to send code' })
      }
    } catch {
      setStatus({ ok: false, msg: 'Could not reach API' })
    }
    setLoading(false)
  }

  const verify = async () => {
    if (!code().trim() || !newPass().trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/verify-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code(), new_passphrase: newPass() }),
      })
      const d = await r.json()
      if (r.ok) {
        setStatus({ ok: true, msg: 'Passphrase reset! Redirecting to login...' })
        setTimeout(() => { setScreen('login'); setStatus(null) }, 1500)
      } else {
        setStatus({ ok: false, msg: d.detail || 'Verification failed' })
      }
    } catch {
      setStatus({ ok: false, msg: 'Could not reach API' })
    }
    setLoading(false)
  }

  const setupPassphrase = async () => {
    if (!setupPass().trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/setup-passphrase`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase: setupPass() }),
      })
      if (r.ok) {
        setStatus({ ok: true, msg: "Passphrase set! You're all set." })
        setTimeout(() => setAuthenticated(true), 800)
      } else {
        const d = await r.json()
        setStatus({ ok: false, msg: d.detail || 'Failed to set passphrase' })
      }
    } catch {
      setStatus({ ok: false, msg: 'Could not reach API' })
    }
    setLoading(false)
  }

  const handleKeyDown = (e: KeyboardEvent, action: () => void) => {
    if (e.key === 'Enter') action()
  }

  return (
    <div class="flex h-screen w-screen items-center justify-center bg-surface">
      <div class="w-full max-w-sm space-y-6 p-8">
        <div class="text-center space-y-2">
          <div class="w-12 h-12 rounded-full bg-accent/15 flex items-center justify-center mx-auto">
            <Lock class="w-6 h-6 text-accent" />
          </div>
          <h1 class="text-xl font-semibold text-text-primary">
            {screen() === 'login' && 'Welcome Back'}
            {screen() === 'forgot' && 'Forgot Passphrase'}
            {screen() === 'verify' && 'Enter Code'}
            {screen() === 'setup' && 'First Time Setup'}
          </h1>
          <p class="text-sm text-text-muted">
            {screen() === 'login' && 'Enter your passphrase to continue'}
            {screen() === 'forgot' && "We'll send a reset code to your email"}
            {screen() === 'verify' && 'Check your email for the 6-digit code'}
            {screen() === 'setup' && 'Set a passphrase to secure your Emily instance'}
          </p>
        </div>

        <Show when={screen() === 'login'}>
          <div class="space-y-4">
            <input
              type="password"
              value={passphrase()}
              onInput={(e) => setPassphrase(e.currentTarget.value)}
              onKeyDown={(e) => handleKeyDown(e, () => void login())}
              placeholder="Passphrase"
              aria-label="Passphrase"
              autofocus
              class="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
            />
            <button
              onClick={() => void login()}
              disabled={loading() || !passphrase().trim()}
              class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              <Show when={loading()}><Loader class="w-3.5 h-3.5 animate-spin" /></Show>
              Sign In
            </button>
            <button
              onClick={() => { setScreen('forgot'); setStatus(null) }}
              class="w-full text-xs text-text-muted hover:text-accent transition-colors"
            >
              Forgot passphrase?
            </button>
            <Show when={!passphraseSet()}>
              <button
                onClick={() => setAuthenticated(true)}
                class="w-full flex items-center justify-center gap-1.5 text-xs text-text-muted hover:text-accent transition-colors"
              >
                <ShieldOff class="w-3 h-3" />
                Skip (no passphrase configured)
              </button>
            </Show>
          </div>
        </Show>

        <Show when={screen() === 'forgot'}>
          <div class="space-y-4">
            <div class="relative">
              <Mail aria-hidden="true" class="absolute left-3 top-2.5 w-4 h-4 text-text-muted" />
              <input
                type="email"
                value={email()}
                onInput={(e) => setEmail(e.currentTarget.value)}
                onKeyDown={(e) => handleKeyDown(e, () => void forgot())}
                placeholder="Email address"
                aria-label="Email address"
                autofocus
                class="w-full bg-surface-raised border border-border rounded-lg pl-9 pr-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <button
              onClick={() => void forgot()}
              disabled={loading() || !email().trim()}
              class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              <Show when={loading()}><Loader class="w-3.5 h-3.5 animate-spin" /></Show>
              Send Reset Code
            </button>
            <button
              onClick={() => { setScreen('login'); setStatus(null) }}
              class="w-full flex items-center justify-center gap-1 text-xs text-text-muted hover:text-accent transition-colors"
            >
              <ArrowLeft class="w-3 h-3" /> Back to login
            </button>
          </div>
        </Show>

        <Show when={screen() === 'verify'}>
          <div class="space-y-4">
            <input
              type="text"
              value={code()}
              onInput={(e) => setCode(e.currentTarget.value)}
              placeholder="6-digit code"
              aria-label="Verification code"
              maxLength={6}
              autofocus
              class="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors text-center tracking-widest text-lg font-mono"
            />
            <input
              type="password"
              value={newPass()}
              onInput={(e) => setNewPass(e.currentTarget.value)}
              onKeyDown={(e) => handleKeyDown(e, () => void verify())}
              placeholder="New passphrase"
              aria-label="New passphrase"
              class="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
            />
            <button
              onClick={() => void verify()}
              disabled={loading() || !code().trim() || !newPass().trim()}
              class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              <Show when={loading()}><Loader class="w-3.5 h-3.5 animate-spin" /></Show>
              Reset Passphrase
            </button>
            <button
              onClick={() => { setScreen('forgot'); setStatus(null) }}
              class="w-full flex items-center justify-center gap-1 text-xs text-text-muted hover:text-accent transition-colors"
            >
              <ArrowLeft class="w-3 h-3" /> Back
            </button>
          </div>
        </Show>

        <Show when={screen() === 'setup'}>
          <div class="space-y-4">
            <input
              type="password"
              value={setupPass()}
              onInput={(e) => setSetupPass(e.currentTarget.value)}
              onKeyDown={(e) => handleKeyDown(e, () => void setupPassphrase())}
              placeholder="Choose a passphrase"
              aria-label="Choose a passphrase"
              autofocus
              class="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
            />
            <button
              onClick={() => void setupPassphrase()}
              disabled={loading() || !setupPass().trim()}
              class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              <Show when={loading()}><Loader class="w-3.5 h-3.5 animate-spin" /></Show>
              Set Passphrase
            </button>
            <button
              onClick={() => setAuthenticated(true)}
              class="w-full flex items-center justify-center gap-1.5 text-xs text-text-muted hover:text-accent transition-colors"
            >
              <ShieldOff class="w-3 h-3" />
              Skip for now (local access only)
            </button>
          </div>
        </Show>

        <Show when={status()}>
          <StatusMsg ok={status()!.ok} msg={status()!.msg} />
        </Show>
      </div>
    </div>
  )
}
