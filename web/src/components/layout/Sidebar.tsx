import { useState, useMemo } from 'react'
import {
  Plus, Search, Pin, Trash2, Settings,
  ChevronDown, ChevronRight, Copy, Moon, Sun,
} from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import { useModelsStore } from '../../stores/models'
import { useUIStore } from '../../stores/ui'
import { getSkillIcon } from '../../lib/skill-icons'
import { getModeTheme } from '../../lib/mode-themes'
import { relativeTime, dateGroup } from '../../lib/time'
import { formatCost } from '../../lib/cost'
import { PROVIDER_COLORS } from '../../api/types'
import type { ConversationSummary } from '../../api/types'

function ProviderDot({ provider }: { provider: string | null }) {
  const color = PROVIDER_COLORS[provider || ''] || '#555'
  return (
    <span
      className="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style={{ backgroundColor: color }}
    />
  )
}

function ConversationItem({ conv }: { conv: ConversationSummary }) {
  const activeId = useChatStore((s) => s.activeId)
  const selectConversation = useChatStore((s) => s.selectConversation)
  const deleteConversation = useChatStore((s) => s.deleteConversation)
  const pinConversation = useChatStore((s) => s.pinConversation)
  const duplicateConversation = useChatStore((s) => s.duplicateConversation)
  const [showActions, setShowActions] = useState(false)

  const isActive = activeId === conv.id

  return (
    <button
      onClick={() => selectConversation(conv.id)}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
      className={`group w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors
        ${isActive ? 'bg-surface-hover text-text-primary' : 'text-text-secondary hover:bg-surface-hover/50 hover:text-text-primary'}`}
    >
      <ProviderDot provider={conv.provider} />
      <div className="flex-1 min-w-0">
        <div className="truncate text-sm font-medium">{conv.title}</div>
        <div className="flex items-center gap-2 text-xs text-text-muted mt-0.5">
          <span>{relativeTime(conv.updated_at)}</span>
          {conv.total_messages > 0 && <span>{conv.total_messages} msgs</span>}
          {conv.total_cost_usd > 0 && (
            <span className="text-cost-green">{formatCost(conv.total_cost_usd)}</span>
          )}
        </div>
      </div>
      {(showActions || conv.pinned) && (
        <div className="flex items-center gap-0.5 flex-shrink-0">
          <button
            onClick={(e) => {
              e.stopPropagation()
              pinConversation(conv.id, !conv.pinned)
            }}
            className={`p-1 rounded hover:bg-surface-raised transition-colors
              ${conv.pinned ? 'text-accent' : 'text-text-muted opacity-0 group-hover:opacity-100'}`}
            aria-label={conv.pinned ? 'Unpin' : 'Pin'}
          >
            <Pin aria-hidden="true" className="w-3.5 h-3.5" />
          </button>
          {showActions && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  duplicateConversation(conv.id)
                }}
                className="p-1 rounded text-text-muted opacity-0 group-hover:opacity-100 hover:bg-surface-raised transition-colors"
                aria-label="Duplicate"
              >
                <Copy aria-hidden="true" className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  deleteConversation(conv.id)
                }}
                className="p-1 rounded text-text-muted opacity-0 group-hover:opacity-100 hover:bg-surface-raised hover:text-error-red transition-colors"
                aria-label="Delete"
              >
                <Trash2 aria-hidden="true" className="w-3.5 h-3.5" />
              </button>
            </>
          )}
        </div>
      )}
    </button>
  )
}

function SkillCard({ id, name, active, onClick }: {
  id: string; name: string; active: boolean; onClick: () => void
}) {
  const Icon = getSkillIcon(id)
  const theme = getModeTheme(id)
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all w-full text-left
        ${active ? 'bg-surface-hover' : 'hover:bg-surface-hover/50'}`}
      style={active ? {
        boxShadow: `0 0 12px ${theme.glow}, inset 0 0 0 1px ${theme.accent}40`,
      } : undefined}
    >
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
        style={active
          ? { background: theme.gradient, boxShadow: `0 0 8px ${theme.glow}` }
          : { backgroundColor: `${theme.accent}15` }
        }
      >
        <Icon
          className="w-3.5 h-3.5"
          style={{ color: active ? '#fff' : theme.accent }}
        />
      </div>
      <span
        className={`truncate ${active ? 'font-medium' : ''}`}
        style={active ? { color: theme.accent } : undefined}
      >
        {name}
      </span>
    </button>
  )
}

export function Sidebar() {
  const conversations = useChatStore((s) => s.conversations)
  const createConversation = useChatStore((s) => s.createConversation)
  const skills = useModelsStore((s) => s.skills)
  const activeSkill = useModelsStore((s) => s.activeSkill)
  const setActiveSkill = useModelsStore((s) => s.setActiveSkill)
  const setSearchOpen = useUIStore((s) => s.setSearchOpen)

  const [searchQuery, setSearchQuery] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [skillsExpanded, setSkillsExpanded] = useState(true)

  const filtered = useMemo(() => {
    if (!searchQuery) return conversations
    const q = searchQuery.toLowerCase()
    return conversations.filter((c) => c.title.toLowerCase().includes(q))
  }, [conversations, searchQuery])

  const grouped = useMemo(() => {
    const groups: Record<string, ConversationSummary[]> = {}
    const pinnedConvs = filtered.filter((c) => c.pinned)
    const rest = filtered.filter((c) => !c.pinned)

    if (pinnedConvs.length > 0) groups['Pinned'] = pinnedConvs
    for (const conv of rest) {
      const group = dateGroup(conv.updated_at)
      if (!groups[group]) groups[group] = []
      groups[group].push(conv)
    }
    return groups
  }, [filtered])

  const toggleGroup = (name: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  return (
    <div className="w-[260px] flex-shrink-0 border-r border-border flex flex-col bg-surface-raised h-full">
      <div className="p-3 space-y-2">
        <button
          onClick={() => createConversation()}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-white font-medium text-sm transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Conversation
        </button>

        <div className="relative">
          <Search aria-hidden="true" className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search conversations..."
            aria-label="Search conversations"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => {
              if (!searchQuery) setSearchOpen(true)
            }}
            className="w-full pl-8 pr-3 py-2 rounded-lg bg-surface text-sm text-text-primary placeholder:text-text-muted border border-border focus:border-accent focus:outline-none transition-colors"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
        {Object.entries(grouped).map(([group, convs]) => (
          <div key={group}>
            <button
              onClick={() => toggleGroup(group)}
              className="flex items-center gap-1 px-2 py-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider w-full hover:text-text-secondary transition-colors"
            >
              {collapsedGroups.has(group) ? (
                <ChevronRight className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
              {group}
              <span className="ml-auto text-text-muted font-normal">{convs.length}</span>
            </button>
            {!collapsedGroups.has(group) &&
              convs.map((conv) => <ConversationItem key={conv.id} conv={conv} />)}
          </div>
        ))}

        {filtered.length === 0 && (
          <div className="px-3 py-8 text-center text-text-muted text-sm">
            {searchQuery ? 'No matches' : 'No conversations yet'}
          </div>
        )}
      </div>

      <div className="border-t border-border px-2 py-2">
        <button
          onClick={() => setSkillsExpanded(!skillsExpanded)}
          className="flex items-center gap-1 px-2 py-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider w-full hover:text-text-secondary"
        >
          {skillsExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Skills & Modes
        </button>
        {skillsExpanded && (
          <div className="mt-1 space-y-0.5 max-h-64 overflow-y-auto">
            {Object.entries(skills).map(([id, skill]) => (
              <SkillCard
                key={id}
                id={id}
                name={skill.name}
                active={activeSkill === id}
                onClick={() => setActiveSkill(id)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-border px-3 py-2 flex items-center justify-between text-xs text-text-muted">
        <button className="flex items-center gap-1.5 hover:text-text-secondary transition-colors">
          <Settings className="w-3.5 h-3.5" />
          Settings
        </button>
        <button
          onClick={() => useUIStore.getState().toggleTheme()}
          className="hover:text-text-secondary transition-colors"
          aria-label="Toggle theme"
        >
          {useUIStore.getState().theme === 'dark' ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
        </button>
        <span>v1.0.0</span>
      </div>
    </div>
  )
}
