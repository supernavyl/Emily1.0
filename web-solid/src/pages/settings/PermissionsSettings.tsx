import { createSignal, onMount, Show, For } from 'solid-js'
import {
  Shield, Eye, Brain, Lock, Loader, CircleCheck, CircleAlert,
  FolderOpen, Terminal, Monitor, Bell, Mail, CalendarDays,
  MessageSquare, Globe, Search, Cpu, House,
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

// ── Data types ────────────────────────────────────────────────────────────

interface Permissions {
  vision_enabled: boolean
  screen_capture: boolean
  emotion_detection: boolean
  save_history: boolean
  pii_scrub: boolean
  encrypt_at_rest: boolean
}

interface ToolPermissions {
  file_read: boolean
  file_write: boolean
  shell: boolean
  code_execution: boolean
  computer_control: boolean
  screen_awareness: boolean
  notifications: boolean
  email: boolean
  calendar: boolean
  discord: boolean
  web_search: boolean
  web_fetch: boolean
  home_assistant: boolean
}

const TOOL_GROUPS: Array<{
  title: string
  icon: LucideIcon
  tools: Array<{ key: keyof ToolPermissions; label: string; desc: string }>
}> = [
  {
    title: 'Files & System',
    icon: FolderOpen,
    tools: [
      { key: 'file_read', label: 'Read files', desc: 'Read files within allowed paths.' },
      { key: 'file_write', label: 'Write files', desc: 'Create and modify files. Always requires approval.' },
      { key: 'shell', label: 'Shell commands', desc: 'Run terminal commands. Always requires approval.' },
      { key: 'code_execution', label: 'Code execution', desc: 'Execute code in a sandboxed environment.' },
    ],
  },
  {
    title: 'Computer Control',
    icon: Monitor,
    tools: [
      { key: 'computer_control', label: 'Open apps & files', desc: 'Launch applications and open files.' },
      { key: 'screen_awareness', label: 'Screen & system awareness', desc: 'Read active windows, processes, clipboard.' },
      { key: 'notifications', label: 'System notifications', desc: 'Send desktop notifications.' },
    ],
  },
  {
    title: 'Communication',
    icon: Mail,
    tools: [
      { key: 'email', label: 'Email (read)', desc: 'Read emails via IMAP.' },
      { key: 'calendar', label: 'Calendar', desc: 'Read calendar events.' },
      { key: 'discord', label: 'Discord', desc: 'Send and read Discord messages.' },
    ],
  },
  {
    title: 'Internet & Integrations',
    icon: Globe,
    tools: [
      { key: 'web_search', label: 'Web search', desc: 'Search the web.' },
      { key: 'web_fetch', label: 'Web fetch / browse', desc: 'Fetch and read content from any URL.' },
      { key: 'home_assistant', label: 'Home Assistant', desc: 'Control smart home devices.' },
    ],
  },
]

// ── Component ─────────────────────────────────────────────────────────────

function PermissionsSettings() {
  const [perms, setPerms] = createSignal<Permissions | null>(null)
  const [tools, setTools] = createSignal<ToolPermissions | null>(null)
  const [loading, setLoading] = createSignal(true)
  const [saving, setSaving] = createSignal<string | null>(null)
  const [status, setStatus] = createSignal<{ ok: boolean; msg: string } | null>(null)

  onMount(async () => {
    try {
      const [pRes, tRes] = await Promise.all([
        fetch(`${API_RAW}/settings/permissions`),
        fetch(`${API_RAW}/settings/tools`),
      ])
      if (pRes.ok) setPerms(await pRes.json())
      if (tRes.ok) setTools(await tRes.json())
      if (!pRes.ok && !tRes.ok) {
        setStatus({ ok: false, msg: 'Could not load permissions -- is the API running?' })
      }
    } catch {
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setLoading(false)
  })

  const togglePerm = async (key: keyof Permissions, value: boolean) => {
    const p = perms()
    if (!p) return
    const prev = p[key]
    setPerms({ ...p, [key]: value })
    setSaving(key)
    try {
      const r = await fetch(`${API_RAW}/settings/permissions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
      if (!r.ok) {
        setPerms({ ...p, [key]: prev })
        setStatus({ ok: false, msg: 'Failed to save.' })
      } else {
        setStatus(null)
      }
    } catch {
      setPerms({ ...p, [key]: prev })
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setSaving(null)
  }

  const toggleTool = async (key: keyof ToolPermissions, value: boolean) => {
    const t = tools()
    if (!t) return
    const prev = t[key]
    setTools({ ...t, [key]: value })
    setSaving(`tool_${key}`)
    try {
      const r = await fetch(`${API_RAW}/settings/tools`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
      if (!r.ok) {
        setTools({ ...t, [key]: prev })
        setStatus({ ok: false, msg: 'Failed to save.' })
      } else {
        setStatus(null)
      }
    } catch {
      setTools({ ...t, [key]: prev })
      setStatus({ ok: false, msg: 'Network error.' })
    }
    setSaving(null)
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
      <div class="space-y-4">
        {/* Tool access groups */}
        <Show when={tools()}>
          {(t) => (
            <>
              <div style={cardStyle}>
                <div class="flex items-center gap-2 text-sm font-semibold" style={{ color: 'oklch(0.93 0.01 90)' }}>
                  <Shield size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                  Tool Access
                </div>
                <p class="text-xs mt-2" style={{ color: 'oklch(0.55 0.03 185)' }}>
                  Control exactly what Emily can do on your computer. Disabled tools return an error when called.
                </p>
              </div>

              <For each={TOOL_GROUPS}>
                {(group) => {
                  const GroupIcon = group.icon
                  return (
                    <div style={cardStyle} class="space-y-0">
                      <div class="flex items-center gap-2 text-sm font-semibold mb-2" style={{ color: 'oklch(0.93 0.01 90)' }}>
                        <GroupIcon size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                        {group.title}
                      </div>
                      <For each={group.tools}>
                        {(tool) => (
                          <PermRow
                            icon={group.icon}
                            label={tool.label}
                            description={tool.desc}
                            value={t()[tool.key]}
                            onChange={(v) => void toggleTool(tool.key, v)}
                            disabled={saving() === `tool_${tool.key}`}
                          />
                        )}
                      </For>
                    </div>
                  )
                }}
              </For>
            </>
          )}
        </Show>

        {/* Vision & Perception */}
        <Show when={perms()}>
          {(p) => (
            <>
              <div style={cardStyle} class="space-y-0">
                <div class="flex items-center gap-2 text-sm font-semibold mb-2" style={{ color: 'oklch(0.93 0.01 90)' }}>
                  <Eye size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                  Vision & Perception
                </div>
                <PermRow
                  icon={Eye} label="Camera (webcam)"
                  description="Allow Emily to see through your webcam for emotion detection and context."
                  value={p().vision_enabled}
                  onChange={(v) => void togglePerm('vision_enabled', v)}
                  disabled={saving() === 'vision_enabled'}
                />
                <PermRow
                  icon={Eye} label="Screen capture"
                  description="Periodically capture your screen so Emily can understand what you're working on."
                  value={p().screen_capture}
                  onChange={(v) => void togglePerm('screen_capture', v)}
                  disabled={saving() === 'screen_capture'}
                />
                <PermRow
                  icon={Eye} label="Emotion detection"
                  description="Analyse facial expressions from webcam to adapt Emily's tone and responses."
                  value={p().emotion_detection}
                  onChange={(v) => void togglePerm('emotion_detection', v)}
                  disabled={!p().vision_enabled || saving() === 'emotion_detection'}
                />
              </div>

              <div style={cardStyle} class="space-y-0">
                <div class="flex items-center gap-2 text-sm font-semibold mb-2" style={{ color: 'oklch(0.93 0.01 90)' }}>
                  <Brain size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                  Memory
                </div>
                <PermRow
                  icon={Brain} label="Save conversation history"
                  description="Store every conversation turn so Emily remembers past interactions."
                  value={p().save_history}
                  onChange={(v) => void togglePerm('save_history', v)}
                  disabled={saving() === 'save_history'}
                />
              </div>

              <div style={cardStyle} class="space-y-0">
                <div class="flex items-center gap-2 text-sm font-semibold mb-2" style={{ color: 'oklch(0.93 0.01 90)' }}>
                  <Lock size={16} style={{ color: 'oklch(0.72 0.17 162)' }} />
                  Data Protection
                </div>
                <PermRow
                  icon={Lock} label="Scrub personal information"
                  description="Automatically redact names, emails, phone numbers from stored logs."
                  value={p().pii_scrub}
                  onChange={(v) => void togglePerm('pii_scrub', v)}
                  disabled={saving() === 'pii_scrub'}
                />
                <PermRow
                  icon={Lock} label="Encrypt data at rest"
                  description="Encrypt stored memories and conversation history on disk."
                  value={p().encrypt_at_rest}
                  onChange={(v) => void togglePerm('encrypt_at_rest', v)}
                  disabled={saving() === 'encrypt_at_rest'}
                />
              </div>
            </>
          )}
        </Show>

        <Show when={status()}>{(s) => <StatusMsg ok={s().ok} msg={s().msg} />}</Show>

        <p class="text-xs px-1" style={{ color: 'oklch(0.55 0.03 185)' }}>
          Changes take effect immediately for this session. Restart Emily to apply permanently.
        </p>
      </div>
    </Show>
  )
}

export default PermissionsSettings
