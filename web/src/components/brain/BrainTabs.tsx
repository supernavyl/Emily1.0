import { Activity, Heart, Cpu, Database, Network, Fingerprint } from 'lucide-react'

export type BrainTab = 'neural' | 'emotional' | 'cognitive' | 'memory' | 'fleet' | 'personality'

const TABS: { id: BrainTab; label: string; icon: typeof Activity }[] = [
  { id: 'neural', label: 'Neural Overview', icon: Activity },
  { id: 'emotional', label: 'Emotional Cortex', icon: Heart },
  { id: 'cognitive', label: 'Cognitive', icon: Cpu },
  { id: 'memory', label: 'Memory', icon: Database },
  { id: 'fleet', label: 'Model Fleet', icon: Network },
  { id: 'personality', label: 'Personality', icon: Fingerprint },
]

interface Props {
  active: BrainTab
  onChange: (tab: BrainTab) => void
}

export function BrainTabs({ active, onChange }: Props) {
  return (
    <div className="flex items-center gap-1 px-4 py-2 border-b border-border bg-surface-raised flex-shrink-0 overflow-x-auto">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all
            ${active === id
              ? 'bg-accent/15 text-accent shadow-sm shadow-accent/10'
              : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'
            }`}
        >
          <Icon className="w-3.5 h-3.5" />
          {label}
        </button>
      ))}
    </div>
  )
}
