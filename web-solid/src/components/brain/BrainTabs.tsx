import { For } from 'solid-js'
import { Activity, Heart, Cpu, Database, Network, Fingerprint, Radio, MessageSquare } from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'

export type BrainTab = 'neural' | 'emotional' | 'cognitive' | 'memory' | 'fleet' | 'personality' | 'stream' | 'chat'

const TABS: { id: BrainTab; label: string; icon: LucideIcon }[] = [
  { id: 'neural', label: 'Neural', icon: Activity },
  { id: 'emotional', label: 'Affect', icon: Heart },
  { id: 'cognitive', label: 'Cognit', icon: Cpu },
  { id: 'memory', label: 'Memory', icon: Database },
  { id: 'fleet', label: 'Fleet', icon: Network },
  { id: 'personality', label: 'Matrix', icon: Fingerprint },
  { id: 'stream', label: 'Stream', icon: Radio },
  { id: 'chat', label: 'Query', icon: MessageSquare },
]

interface BrainTabsProps {
  active: BrainTab
  onChange: (tab: BrainTab) => void
}

export function BrainTabs(props: BrainTabsProps) {
  return (
    <nav
      aria-label="Brain dashboard sections"
      class="flex items-stretch flex-shrink-0 overflow-x-auto scrollbar-hide"
      style={{
        background: 'var(--color-surface-raised)',
        'border-bottom': '1px solid var(--color-border)',
      }}
    >
      <For each={TABS}>
        {(tab, idx) => {
          const Icon = tab.icon
          return (
            <button
              onClick={() => props.onChange(tab.id)}
              aria-current={props.active === tab.id ? 'page' : undefined}
              class="flex flex-col items-center justify-center gap-0.5 px-4 py-2 whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] min-w-[56px]"
              style={{
                'border-right': idx() < TABS.length - 1 ? '1px solid var(--color-border)' : undefined,
                'border-bottom': props.active === tab.id
                  ? '2px solid var(--color-accent)'
                  : '2px solid transparent',
                color: props.active === tab.id
                  ? 'var(--color-accent)'
                  : 'var(--color-readout-dim)',
                background: 'transparent',
                'border-radius': '0',
              }}
              onMouseEnter={(e) => {
                if (props.active !== tab.id) {
                  e.currentTarget.style.color = 'var(--color-text-secondary)'
                }
              }}
              onMouseLeave={(e) => {
                if (props.active !== tab.id) {
                  e.currentTarget.style.color = 'var(--color-readout-dim)'
                }
              }}
            >
              <Icon size={14} aria-hidden="true" />
              <span
                style={{
                  'font-family': 'var(--font-mono)',
                  'font-size': '10px',
                  'letter-spacing': '0.08em',
                  'text-transform': 'uppercase',
                  'line-height': '1',
                }}
              >
                {tab.label}
              </span>
            </button>
          )
        }}
      </For>
    </nav>
  )
}
