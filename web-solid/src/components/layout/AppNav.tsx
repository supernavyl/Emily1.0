import { For } from 'solid-js'
import { MessageSquare, Mic, Eye, ScrollText, Brain, Terminal, Settings } from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'
import { uiState, setActivePage, type AppPage } from '../../stores/ui'

const TABS: { id: AppPage; label: string; icon: LucideIcon }[] = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'voice', label: 'Voice', icon: Mic },
  { id: 'vision', label: 'Vision', icon: Eye },
  { id: 'logs', label: 'Logs', icon: ScrollText },
  { id: 'brain', label: 'Brain', icon: Brain },
  { id: 'terminal', label: 'Terminal', icon: Terminal },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export function AppNav() {
  return (
    <nav class="flex items-center gap-0.5 px-2">
      <For each={TABS}>
        {(tab) => {
          const Icon = tab.icon
          return (
            <button
              onClick={() => setActivePage(tab.id)}
              class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors"
              style={{
                'font-size': 'var(--text-small)',
                'font-family': 'var(--font-display)',
                'font-weight': uiState.activePage === tab.id ? '600' : '500',
                color: uiState.activePage === tab.id ? 'oklch(0.72 0.17 162)' : 'oklch(0.50 0.04 185)',
                background: uiState.activePage === tab.id ? 'oklch(0.72 0.17 162 / 0.12)' : '',
              }}
              onMouseEnter={(e) => {
                if (uiState.activePage !== tab.id) {
                  e.currentTarget.style.background = 'oklch(0.26 0.03 185)'
                  e.currentTarget.style.color = 'oklch(0.65 0.03 185)'
                }
              }}
              onMouseLeave={(e) => {
                if (uiState.activePage !== tab.id) {
                  e.currentTarget.style.background = ''
                  e.currentTarget.style.color = 'oklch(0.50 0.04 185)'
                }
              }}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          )
        }}
      </For>
    </nav>
  )
}
