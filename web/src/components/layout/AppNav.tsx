import { MessageSquare, Mic, Eye, ScrollText, Brain, Terminal, Settings } from 'lucide-react'
import { useUIStore, type AppPage } from '../../stores/ui'

const TABS: { id: AppPage; label: string; icon: typeof MessageSquare }[] = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'voice', label: 'Voice', icon: Mic },
  { id: 'vision', label: 'Vision', icon: Eye },
  { id: 'logs', label: 'Logs', icon: ScrollText },
  { id: 'brain', label: 'Brain', icon: Brain },
  { id: 'terminal', label: 'Terminal', icon: Terminal },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export function AppNav() {
  const activePage = useUIStore((s) => s.activePage)
  const setActivePage = useUIStore((s) => s.setActivePage)

  return (
    <nav className="flex items-center gap-1 px-2">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => setActivePage(id)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
            ${activePage === id
              ? 'bg-accent/15 text-accent'
              : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'
            }`}
        >
          <Icon className="w-3.5 h-3.5" />
          {label}
        </button>
      ))}
    </nav>
  )
}
