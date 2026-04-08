import { createSignal, createEffect, onMount, onCleanup, For, Show } from 'solid-js'
import { API_BASE, API_RAW } from '../lib/env'
import { Trash2, Command } from 'lucide-solid'
import { modelsState } from '../stores/models'

// ── Types ───────────────────────────────────────────────────────────────────

interface TermLine {
  type: 'input' | 'output' | 'error' | 'json'
  text: string
}

const COMMANDS = ['/help', '/clear', '/status', '/models', '/agents', '/config', '/memory', '/voice']

// ── Simple JSON highlighter ─────────────────────────────────────────────────

function JsonHighlighter(props: { text: string }) {
  const highlighted = () => {
    return props.text
      .replace(/"([^"]+)"(?=\s*:)/g, '<span style="color:oklch(0.72 0.17 162);">"$1"</span>')
      .replace(/:\s*"([^"]*?)"/g, ': <span style="color:oklch(0.72 0.15 145);">"$1"</span>')
      .replace(/:\s*(\d+\.?\d*)/g, ': <span style="color:oklch(0.75 0.16 85);">$1</span>')
      .replace(/:\s*(true|false|null)/g, ': <span style="color:oklch(0.65 0.20 25);">$1</span>')
  }

  // eslint-disable-next-line solid/no-innerhtml
  return <pre class="whitespace-pre-wrap" innerHTML={highlighted()} />
}

// ── Main component ──────────────────────────────────────────────────────────

export function TerminalPage() {
  const [lines, setLines] = createSignal<TermLine[]>([
    { type: 'output', text: 'Emily Terminal \u2014 connected to API at :8000' },
    { type: 'output', text: 'Type a command or chat message. Ctrl+K for command palette.\n' },
  ])
  const [input, setInput] = createSignal('')
  const [history, setHistory] = createSignal<string[]>([])
  const [histIdx, setHistIdx] = createSignal(-1)
  const [paletteOpen, setPaletteOpen] = createSignal(false)
  const [tabHint, setTabHint] = createSignal('')
  let scrollRef: HTMLDivElement | undefined
  let inputRef: HTMLInputElement | undefined

  createEffect(() => {
    lines() // track
    if (scrollRef) scrollRef.scrollTop = scrollRef.scrollHeight
  })

  onMount(() => { inputRef?.focus() })

  // Ctrl+K listener
  onMount(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    onCleanup(() => window.removeEventListener('keydown', handler))
  })

  // Tab completion hint
  createEffect(() => {
    const val = input()
    if (val.startsWith('/') && val.length > 1) {
      const match = COMMANDS.find(c => c.startsWith(val) && c !== val)
      setTabHint(match ? match.slice(val.length) : '')
    } else {
      setTabHint('')
    }
  })

  const addLine = (type: TermLine['type'], text: string) => {
    setLines(prev => [...prev, { type, text }])
  }

  const handleSubmit = async () => {
    const cmd = input().trim()
    if (!cmd) return

    addLine('input', `\u276F ${cmd}`)
    setHistory(prev => [cmd, ...prev])
    setHistIdx(-1)
    setInput('')

    if (cmd === '/help') {
      addLine('output', `Available commands:
  /status     \u2014 Show API health status
  /models     \u2014 List loaded models
  /agents     \u2014 List active agents
  /config     \u2014 Show sanitized config
  /memory     \u2014 Show memory stats
  /voice      \u2014 Show voice engine status
  /clear      \u2014 Clear terminal
  /help       \u2014 Show this help

Ctrl+K \u2014 Command palette
Or type any message to chat with Emily.`)
      return
    }

    if (cmd === '/clear') { setLines([]); return }

    const apiCommands: Record<string, string> = {
      '/status': `${API_RAW}/status`,
      '/models': `${API_BASE}/api/v1/models`,
      '/agents': `${API_RAW}/agents`,
      '/config': `${API_RAW}/config`,
      '/memory': `${API_RAW}/memory/working`,
      '/voice': `${API_RAW}/audio/voice/status`,
    }

    if (apiCommands[cmd]) {
      try {
        const res = await fetch(apiCommands[cmd])
        if (res.ok) {
          const data = await res.json()
          addLine('json', JSON.stringify(data, null, 2))
        } else {
          addLine('error', `API returned ${res.status}`)
        }
      } catch (e) {
        addLine('error', `Failed: ${e}`)
      }
      return
    }

    // Chat message via SSE
    try {
      const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: cmd }),
      })

      if (!res.ok) { addLine('error', `API error: ${res.status}`); return }
      const reader = res.body?.getReader()
      if (!reader) { addLine('error', 'No response body'); return }

      const decoder = new TextDecoder()
      let buffer = ''
      let response = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''
        for (const event of events) {
          const dataLine = event.split('\n').find(l => l.startsWith('data: '))
          if (!dataLine) continue
          try {
            const data = JSON.parse(dataLine.slice(6))
            if (data.token) response += data.token
            if (data.error) addLine('error', data.error)
          } catch { /* ignore */ }
        }
      }
      if (response) addLine('output', response)
    } catch (e) {
      addLine('error', `Connection error: ${e}`)
    }
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') { void handleSubmit() }
    else if (e.key === 'Tab' && tabHint()) {
      e.preventDefault()
      setInput(input() + tabHint())
    }
    else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (histIdx() < history().length - 1) { const n = histIdx() + 1; setHistIdx(n); setInput(history()[n]) }
    }
    else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (histIdx() > 0) { const n = histIdx() - 1; setHistIdx(n); setInput(history()[n]) }
      else { setHistIdx(-1); setInput('') }
    }
  }

  const lineColor = (type: TermLine['type']) => {
    switch (type) {
      case 'input': return 'text-accent'
      case 'error': return 'text-error-red'
      case 'json': return ''
      default: return 'text-text-secondary'
    }
  }

  return (
    <div class="flex flex-1 flex-col min-h-0 bg-surface" onClick={() => inputRef?.focus()}>
      <div class="flex items-center justify-between px-4 py-2 border-b border-border flex-shrink-0">
        <div class="flex items-center gap-3">
          <span class="text-xs font-semibold text-text-muted uppercase tracking-wider">Terminal</span>
          <span class="text-[10px] px-1.5 py-0.5 bg-accent/10 text-accent rounded font-mono">{modelsState.activeModel}</span>
          <span class="text-[10px] px-1.5 py-0.5 bg-surface-hover text-text-muted rounded">{modelsState.activeSkill}</span>
        </div>
        <div class="flex items-center gap-2">
          <button onClick={() => setPaletteOpen(true)} class="flex items-center gap-1 text-[10px] text-text-muted hover:text-text-secondary transition-colors">
            <Command class="w-3 h-3" />K
          </button>
          <button onClick={() => setLines([])} class="p-1 rounded-lg hover:bg-surface-hover text-text-muted">
            <Trash2 class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div ref={scrollRef} class="flex-1 overflow-y-auto p-4 font-mono text-sm">
        <For each={lines()}>{(line) => (
          <div class={`${lineColor(line.type)} whitespace-pre-wrap`}>
            <Show when={line.type === 'json'} fallback={line.text}>
              <JsonHighlighter text={line.text} />
            </Show>
          </div>
        )}</For>
      </div>

      <div class="flex items-center gap-2 px-4 py-2 border-t border-border flex-shrink-0">
        <span class="text-accent font-mono text-sm font-bold">{'\u276F'}</span>
        <div class="flex-1 relative">
          <input
            ref={inputRef}
            value={input()}
            onInput={(e) => setInput(e.currentTarget.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or message..."
            class="w-full bg-transparent text-sm font-mono text-text-primary placeholder:text-text-muted outline-none"
            spellcheck={false}
          />
          <Show when={tabHint()}>
            <span class="absolute left-0 top-0 text-sm font-mono text-text-muted/30 pointer-events-none whitespace-pre">
              {input()}<span class="text-text-muted/50">{tabHint()}</span>
            </span>
          </Show>
        </div>
      </div>

      {/* Command palette placeholder (the React version uses a separate component) */}
      <Show when={paletteOpen()}>
        <div
          class="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] backdrop-blur-sm"
          style={{ 'background-color': 'oklch(0.10 0.015 185 / 0.8)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setPaletteOpen(false) }}
        >
          <div class="w-[480px] bg-surface-raised border border-border rounded-2xl shadow-2xl overflow-hidden p-4">
            <div class="text-sm text-text-secondary mb-3">Command Palette</div>
            <div class="space-y-1">
              <For each={COMMANDS}>{(cmd) => (
                <button
                  onClick={() => { setInput(cmd); setPaletteOpen(false); void handleSubmit() }}
                  class="w-full text-left px-3 py-2 rounded-lg text-sm font-mono text-text-secondary hover:bg-surface-hover transition-colors"
                >
                  {cmd}
                </button>
              )}</For>
            </div>
          </div>
        </div>
      </Show>
    </div>
  )
}
