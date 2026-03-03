import { useState, useRef, useEffect, useCallback } from 'react'
import { API_BASE, API_RAW } from '../lib/env'
import { Trash2, Command } from 'lucide-react'
import { JsonHighlighter } from '../components/terminal/JsonHighlighter'
import { CommandPalette } from '../components/terminal/CommandPalette'
import { useModelsStore } from '../stores/models'

interface TermLine {
  type: 'input' | 'output' | 'error' | 'json'
  text: string
}

const COMMANDS = ['/help', '/clear', '/status', '/models', '/agents', '/config', '/memory', '/voice']

export function TerminalPage() {
  const [lines, setLines] = useState<TermLine[]>([
    { type: 'output', text: 'Emily Terminal — connected to API at :8000' },
    { type: 'output', text: 'Type a command or chat message. Ctrl+K for command palette.\n' },
  ])
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [histIdx, setHistIdx] = useState(-1)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [tabHint, setTabHint] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const activeModel = useModelsStore((s) => s.activeModel)
  const activeSkill = useModelsStore((s) => s.activeSkill)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [lines])

  useEffect(() => { inputRef.current?.focus() }, [])

  // Ctrl+K listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Tab completion hint
  useEffect(() => {
    if (input.startsWith('/') && input.length > 1) {
      const match = COMMANDS.find(c => c.startsWith(input) && c !== input)
      setTabHint(match ? match.slice(input.length) : '')
    } else {
      setTabHint('')
    }
  }, [input])

  const addLine = useCallback((type: TermLine['type'], text: string) => {
    setLines(prev => [...prev, { type, text }])
  }, [])

  const handleSubmit = async () => {
    const cmd = input.trim()
    if (!cmd) return

    addLine('input', `❯ ${cmd}`)
    setHistory(prev => [cmd, ...prev])
    setHistIdx(-1)
    setInput('')

    if (cmd === '/help') {
      addLine('output', `Available commands:
  /status     — Show API health status
  /models     — List loaded models
  /agents     — List active agents
  /config     — Show sanitized config
  /memory     — Show memory stats
  /voice      — Show voice engine status
  /clear      — Clear terminal
  /help       — Show this help

Ctrl+K — Command palette
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
          } catch {}
        }
      }
      if (response) addLine('output', response)
    } catch (e) {
      addLine('error', `Connection error: ${e}`)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { handleSubmit() }
    else if (e.key === 'Tab' && tabHint) {
      e.preventDefault()
      setInput(input + tabHint)
    }
    else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (histIdx < history.length - 1) { const n = histIdx + 1; setHistIdx(n); setInput(history[n]) }
    }
    else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (histIdx > 0) { const n = histIdx - 1; setHistIdx(n); setInput(history[n]) }
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
    <div className="flex flex-1 flex-col min-h-0 bg-surface" onClick={() => inputRef.current?.focus()}>
      <div className="flex items-center justify-between px-4 py-2 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Terminal</span>
          <span className="text-[10px] px-1.5 py-0.5 bg-accent/10 text-accent rounded font-mono">{activeModel}</span>
          <span className="text-[10px] px-1.5 py-0.5 bg-surface-hover text-text-muted rounded">{activeSkill}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setPaletteOpen(true)} className="flex items-center gap-1 text-[10px] text-text-muted hover:text-text-secondary transition-colors">
            <Command className="w-3 h-3" />K
          </button>
          <button onClick={() => setLines([])} className="p-1 rounded-lg hover:bg-surface-hover text-text-muted">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 font-mono text-sm">
        {lines.map((line, i) => (
          <div key={i} className={`${lineColor(line.type)} whitespace-pre-wrap`}>
            {line.type === 'json' ? <JsonHighlighter text={line.text} /> : line.text}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 px-4 py-2 border-t border-border flex-shrink-0">
        <span className="text-accent font-mono text-sm font-bold">❯</span>
        <div className="flex-1 relative">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or message..."
            className="w-full bg-transparent text-sm font-mono text-text-primary placeholder:text-text-muted outline-none"
            spellCheck={false}
          />
          {tabHint && (
            <span className="absolute left-0 top-0 text-sm font-mono text-text-muted/30 pointer-events-none whitespace-pre">
              {input}<span className="text-text-muted/50">{tabHint}</span>
            </span>
          )}
        </div>
      </div>

      {paletteOpen && (
        <CommandPalette
          onClose={() => setPaletteOpen(false)}
          onCommand={(cmd) => { setInput(cmd); setTimeout(handleSubmit, 50) }}
        />
      )}
    </div>
  )
}
