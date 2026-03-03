import { useState, useEffect } from 'react'
import { Lock, Mail, ArrowLeft, Loader, CheckCircle, AlertCircle, ShieldOff } from 'lucide-react'
import { useUIStore } from '../../stores/ui'

import { API_RAW } from '../../lib/env'
const API = API_RAW

type Screen = 'login' | 'forgot' | 'verify' | 'setup'

function StatusMsg({ ok, msg }: { ok: boolean; msg: string }) {
  return (
    <div className={`flex items-center gap-2 text-sm mt-2 ${ok ? 'text-cost-green' : 'text-error-red'}`}>
      {ok ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
      {msg}
    </div>
  )
}

export function LoginScreen() {
  const setAuthenticated = useUIStore((s) => s.setAuthenticated)
  const [screen, setScreen] = useState<Screen>('login')
  const [passphrase, setPassphrase] = useState('')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [newPass, setNewPass] = useState('')
  const [setupPass, setSetupPass] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null)
  const [passphraseSet, setPassphraseSet] = useState(true)

  // Check if passphrase has ever been configured
  useEffect(() => {
    fetch(`${API}/settings/auth/status`)
      .then(r => r.json())
      .then(d => {
        if (d.has_owner && !d.passphrase_set) {
          setPassphraseSet(false)
          setScreen('setup')
        }
      })
      .catch(() => {})
  }, [])

  const login = async () => {
    if (!passphrase.trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase }),
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
    if (!email.trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/forgot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
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
    if (!code.trim() || !newPass.trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/verify-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, new_passphrase: newPass }),
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
    if (!setupPass.trim()) return
    setLoading(true)
    setStatus(null)
    try {
      const r = await fetch(`${API}/settings/auth/setup-passphrase`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase: setupPass }),
      })
      if (r.ok) {
        setStatus({ ok: true, msg: 'Passphrase set! You\'re all set.' })
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

  const handleKeyDown = (e: React.KeyboardEvent, action: () => void) => {
    if (e.key === 'Enter') action()
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-surface">
      <div className="w-full max-w-sm space-y-6 p-8">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-accent/15 flex items-center justify-center mx-auto">
            <Lock className="w-6 h-6 text-accent" />
          </div>
          <h1 className="text-xl font-semibold text-text-primary">
            {screen === 'login' && 'Welcome Back'}
            {screen === 'forgot' && 'Forgot Passphrase'}
            {screen === 'verify' && 'Enter Code'}
            {screen === 'setup' && 'First Time Setup'}
          </h1>
          <p className="text-sm text-text-muted">
            {screen === 'login' && 'Enter your passphrase to continue'}
            {screen === 'forgot' && 'We\'ll send a reset code to your email'}
            {screen === 'verify' && 'Check your email for the 6-digit code'}
            {screen === 'setup' && 'Set a passphrase to secure your Emily instance'}
          </p>
        </div>

        {screen === 'login' && (
          <div className="space-y-4">
            <input
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              onKeyDown={(e) => handleKeyDown(e, login)}
              placeholder="Passphrase"
              aria-label="Passphrase"
              autoFocus
              className="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
            />
            <button
              onClick={login}
              disabled={loading || !passphrase.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {loading && <Loader className="w-3.5 h-3.5 animate-spin" />}
              Sign In
            </button>
            <button
              onClick={() => { setScreen('forgot'); setStatus(null) }}
              className="w-full text-xs text-text-muted hover:text-accent transition-colors"
            >
              Forgot passphrase?
            </button>
            {!passphraseSet && (
              <button
                onClick={() => setAuthenticated(true)}
                className="w-full flex items-center justify-center gap-1.5 text-xs text-text-muted hover:text-accent transition-colors"
              >
                <ShieldOff className="w-3 h-3" />
                Skip (no passphrase configured)
              </button>
            )}
          </div>
        )}

        {screen === 'forgot' && (
          <div className="space-y-4">
            <div className="relative">
              <Mail aria-hidden="true" className="absolute left-3 top-2.5 w-4 h-4 text-text-muted" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e, forgot)}
                placeholder="Email address"
                aria-label="Email address"
                autoFocus
                className="w-full bg-surface-raised border border-border rounded-lg pl-9 pr-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <button
              onClick={forgot}
              disabled={loading || !email.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {loading && <Loader className="w-3.5 h-3.5 animate-spin" />}
              Send Reset Code
            </button>
            <button
              onClick={() => { setScreen('login'); setStatus(null) }}
              className="w-full flex items-center justify-center gap-1 text-xs text-text-muted hover:text-accent transition-colors"
            >
              <ArrowLeft className="w-3 h-3" /> Back to login
            </button>
          </div>
        )}

        {screen === 'verify' && (
          <div className="space-y-4">
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="6-digit code"
              aria-label="Verification code"
              maxLength={6}
              autoFocus
              className="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors text-center tracking-widest text-lg font-mono"
            />
            <input
              type="password"
              value={newPass}
              onChange={(e) => setNewPass(e.target.value)}
              onKeyDown={(e) => handleKeyDown(e, verify)}
              placeholder="New passphrase"
              aria-label="New passphrase"
              className="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
            />
            <button
              onClick={verify}
              disabled={loading || !code.trim() || !newPass.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {loading && <Loader className="w-3.5 h-3.5 animate-spin" />}
              Reset Passphrase
            </button>
            <button
              onClick={() => { setScreen('forgot'); setStatus(null) }}
              className="w-full flex items-center justify-center gap-1 text-xs text-text-muted hover:text-accent transition-colors"
            >
              <ArrowLeft className="w-3 h-3" /> Back
            </button>
          </div>
        )}

        {screen === 'setup' && (
          <div className="space-y-4">
            <input
              type="password"
              value={setupPass}
              onChange={(e) => setSetupPass(e.target.value)}
              onKeyDown={(e) => handleKeyDown(e, setupPassphrase)}
              placeholder="Choose a passphrase"
              aria-label="Choose a passphrase"
              autoFocus
              className="w-full bg-surface-raised border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors"
            />
            <button
              onClick={setupPassphrase}
              disabled={loading || !setupPass.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {loading && <Loader className="w-3.5 h-3.5 animate-spin" />}
              Set Passphrase
            </button>
            <button
              onClick={() => setAuthenticated(true)}
              className="w-full flex items-center justify-center gap-1.5 text-xs text-text-muted hover:text-accent transition-colors"
            >
              <ShieldOff className="w-3 h-3" />
              Skip for now (local access only)
            </button>
          </div>
        )}

        {status && <StatusMsg {...status} />}
      </div>
    </div>
  )
}
