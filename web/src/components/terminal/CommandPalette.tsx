import { useState, useEffect, useRef } from 'react'
import { Search, MessageSquare, Mic, ScrollText, Brain, Terminal, Moon, Sun } from 'lucide-react'
import { useUIStore, type AppPage } from '../../stores/ui'

interface Props {
  onClose: () => void
  onCommand: (cmd: string) => void
}

const COMMANDS = [
  { id: 'chat', label: 'Go to Chat', icon: MessageSquare, page: 'chat' as AppPage },
  { id: 'voice', label: 'Go to Voice', icon: Mic, page: 'voice' as AppPage },
  { id: 'logs', label: 'Go to Logs', icon: ScrollText, page: 'logs' as AppPage },
  { id: 'brain', label: 'Go to Brain', icon: Brain, page: 'brain' as AppPage },
  { id: 'terminal', label: 'Go to Terminal', icon: Terminal, page: 'terminal' as AppPage },
  { id: 'status', label: 'Show API Status', icon: Search, cmd: '/status' },
  { id: 'models', label: 'List Models', icon: Search, cmd: '/models' },
  { id: 'agents', label: 'List Agents', icon: Search, cmd: '/agents' },
]

export function CommandPalette({ onClose, onCommand }: Props) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const setActivePage = useUIStore((s) => s.setActivePage)

  useEffect(() => { inputRef.current?.focus() }, [])

  const filtered = COMMANDS.filter(c =>
    c.label.toLowerCase().includes(query.toLowerCase()) ||
    c.id.includes(query.toLowerCase())
  )

  const handleSelect = (cmd: typeof COMMANDS[0]) => {
    if (cmd.page) {
      setActivePage(cmd.page)
      onClose()
    } else if (cmd.cmd) {
      onCommand(cmd.cmd)
      onClose()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { onClose(); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)) }
    if (e.key === 'Enter' && filtered[selected]) { handleSelect(filtered[selected]) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div className="relative w-[480px] bg-surface-raised border border-border rounded-xl shadow-2xl overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <Search className="w-4 h-4 text-text-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(0) }}
            onKeyDown={handleKeyDown}
            placeholder="Search commands..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
          />
          <kbd className="text-[10px] px-1.5 py-0.5 bg-surface rounded border border-border text-text-muted">ESC</kbd>
        </div>
        <div className="max-h-[300px] overflow-y-auto py-1">
          {filtered.map((cmd, i) => {
            const Icon = cmd.icon
            return (
              <button
                key={cmd.id}
                onClick={() => handleSelect(cmd)}
                className={`w-full flex items-center gap-3 px-4 py-2 text-sm transition-colors ${
                  i === selected ? 'bg-accent/10 text-accent' : 'text-text-secondary hover:bg-surface-hover'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{cmd.label}</span>
                {cmd.cmd && <span className="ml-auto text-xs text-text-muted font-mono">{cmd.cmd}</span>}
              </button>
            )
          })}
          {filtered.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-text-muted">No matching commands</div>
          )}
        </div>
      </div>
    </div>
  )
}
