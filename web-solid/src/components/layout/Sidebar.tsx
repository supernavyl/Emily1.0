import { createSignal, createMemo, Show, For } from 'solid-js'
import {
  Plus, Search, Pin, Trash2, Settings,
  ChevronDown, ChevronRight, Copy, Moon, Sun,
} from 'lucide-solid'
import {
  chatState, createConversation, selectConversation,
  deleteConversation, pinConversation, duplicateConversation,
} from '../../stores/chat'
import { modelsState, setActiveSkill } from '../../stores/models'
import { uiState, toggleTheme, setSearchOpen } from '../../stores/ui'
import { getSkillIcon } from '../../lib/skill-icons'
import { getModeTheme } from '../../lib/mode-themes'
import { relativeTime, dateGroup } from '../../lib/time'
import { formatCost } from '../../lib/cost'
import { PROVIDER_COLORS } from '../../api/types'
import type { ConversationSummary } from '../../api/types'

function ProviderDot(props: { provider: string | null }) {
  const color = () => PROVIDER_COLORS[props.provider || ''] || '#555'
  return (
    <span
      class="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style={{ 'background-color': color() }}
    />
  )
}

function ConversationItem(props: { conv: ConversationSummary }) {
  const [showActions, setShowActions] = createSignal(false)
  const isActive = () => chatState.activeId === props.conv.id

  return (
    <button
      onClick={() => selectConversation(props.conv.id)}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
      class="group w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors"
      style={isActive()
        ? { background: 'oklch(0.26 0.03 185)', color: 'oklch(0.93 0.01 90)' }
        : { color: 'oklch(0.65 0.03 185)' }
      }
    >
      <ProviderDot provider={props.conv.provider} />
      <div class="flex-1 min-w-0">
        <div class="truncate text-sm font-medium" style={{ 'font-family': 'var(--font-body)' }}>
          {props.conv.title}
        </div>
        <div
          class="flex items-center gap-2 mt-0.5"
          style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}
        >
          <span>{relativeTime(props.conv.updated_at)}</span>
          <Show when={props.conv.total_messages > 0}>
            <span>{props.conv.total_messages} msgs</span>
          </Show>
          <Show when={props.conv.total_cost_usd > 0}>
            <span style={{ color: 'oklch(0.72 0.15 145)' }}>{formatCost(props.conv.total_cost_usd)}</span>
          </Show>
        </div>
      </div>
      <Show when={showActions() || props.conv.pinned}>
        <div class="flex items-center gap-0.5 flex-shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); pinConversation(props.conv.id, !props.conv.pinned) }}
            class="p-1 rounded transition-colors"
            style={props.conv.pinned
              ? { color: 'oklch(0.72 0.17 162)' }
              : { color: 'oklch(0.50 0.04 185)', opacity: showActions() ? '1' : '0' }
            }
            title={props.conv.pinned ? 'Unpin' : 'Pin'}
          >
            <Pin size={14} />
          </button>
          <Show when={showActions()}>
            <button
              onClick={(e) => { e.stopPropagation(); duplicateConversation(props.conv.id) }}
              class="p-1 rounded transition-colors opacity-0 group-hover:opacity-100"
              style={{ color: 'oklch(0.50 0.04 185)' }}
              title="Duplicate"
            >
              <Copy size={14} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); deleteConversation(props.conv.id) }}
              class="p-1 rounded transition-colors opacity-0 group-hover:opacity-100"
              style={{ color: 'oklch(0.50 0.04 185)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'oklch(0.65 0.20 25)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'oklch(0.50 0.04 185)')}
              title="Delete"
            >
              <Trash2 size={14} />
            </button>
          </Show>
        </div>
      </Show>
    </button>
  )
}

function SkillCard(props: { id: string; name: string; active: boolean; onClick: () => void }) {
  const Icon = () => getSkillIcon(props.id)
  const theme = () => getModeTheme(props.id)

  return (
    <button
      onClick={props.onClick}
      class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all w-full text-left"
      style={props.active ? {
        background: 'oklch(0.26 0.03 185)',
        'box-shadow': `0 0 10px ${theme().glow}, inset 0 0 0 1px ${theme().accent}40`,
      } : undefined}
    >
      <div
        class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
        style={props.active
          ? { background: theme().gradient, 'box-shadow': `0 0 7px ${theme().glow}` }
          : { 'background-color': `${theme().accent}15` }
        }
      >
        {(() => {
          const I = Icon()
          return (
            <I
              size={14}
              style={{ color: props.active ? 'oklch(0.18 0.02 185)' : theme().accent }}
            />
          )
        })()}
      </div>
      <span
        class="truncate"
        style={props.active
          ? { color: theme().accent, 'font-weight': '600', 'font-family': 'var(--font-body)' }
          : { color: 'oklch(0.65 0.03 185)', 'font-family': 'var(--font-body)' }
        }
      >
        {props.name}
      </span>
    </button>
  )
}

export function Sidebar() {
  const [searchQuery, setSearchQuery] = createSignal('')
  const [collapsedGroups, setCollapsedGroups] = createSignal<Set<string>>(new Set())
  const [skillsExpanded, setSkillsExpanded] = createSignal(true)

  const filtered = createMemo(() => {
    const q = searchQuery().toLowerCase()
    if (!q) return chatState.conversations
    return chatState.conversations.filter((c) => c.title.toLowerCase().includes(q))
  })

  const grouped = createMemo(() => {
    const groups: Record<string, ConversationSummary[]> = {}
    const pinnedConvs = filtered().filter((c) => c.pinned)
    const rest = filtered().filter((c) => !c.pinned)

    if (pinnedConvs.length > 0) groups['Pinned'] = pinnedConvs
    for (const conv of rest) {
      const group = dateGroup(conv.updated_at)
      if (!groups[group]) groups[group] = []
      groups[group].push(conv)
    }
    return groups
  })

  const toggleGroup = (name: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  return (
    <div
      class="w-[260px] flex-shrink-0 border-r border-[oklch(0.30_0.03_185)] flex flex-col h-full"
      style={{ background: 'oklch(0.22 0.025 185)' }}
    >
      <div class="p-3 space-y-2">
        <button
          onClick={() => createConversation()}
          class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-medium text-sm transition-colors"
          style={{
            background: 'oklch(0.72 0.17 162)',
            color: 'oklch(0.18 0.02 185)',
            'font-family': 'var(--font-display)',
            'font-weight': '600',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'oklch(0.78 0.14 162)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'oklch(0.72 0.17 162)')}
        >
          <Plus size={16} />
          New Conversation
        </button>

        <div class="relative">
          <Search
            size={14}
            class="absolute left-2.5 top-1/2 -translate-y-1/2"
            style={{ color: 'oklch(0.50 0.04 185)' }}
          />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery()}
            onInput={(e) => setSearchQuery(e.currentTarget.value)}
            onFocus={() => { if (!searchQuery()) setSearchOpen(true) }}
            class="w-full pl-8 pr-3 py-2 rounded-lg text-sm transition-colors focus:outline-none"
            style={{
              background: 'oklch(0.18 0.02 185)',
              color: 'oklch(0.93 0.01 90)',
              border: '1px solid oklch(0.30 0.03 185)',
              'font-family': 'var(--font-body)',
            }}
          />
        </div>
      </div>

      <div class="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
        <For each={Object.entries(grouped())}>
          {([group, convs]) => (
            <div>
              <button
                onClick={() => toggleGroup(group)}
                class="flex items-center gap-1 px-2 py-1.5 w-full transition-colors"
                style={{
                  'font-size': '0.6875rem',
                  'font-weight': '600',
                  'font-family': 'var(--font-display)',
                  color: 'oklch(0.50 0.04 185)',
                  'text-transform': 'uppercase',
                  'letter-spacing': '0.08em',
                }}
              >
                <Show when={collapsedGroups().has(group)} fallback={<ChevronDown size={12} />}>
                  <ChevronRight size={12} />
                </Show>
                {group}
                <span class="ml-auto font-normal" style={{ color: 'oklch(0.50 0.04 185)' }}>
                  {convs.length}
                </span>
              </button>
              <Show when={!collapsedGroups().has(group)}>
                <For each={convs}>
                  {(conv) => <ConversationItem conv={conv} />}
                </For>
              </Show>
            </div>
          )}
        </For>

        <Show when={filtered().length === 0}>
          <div
            class="px-3 py-8 text-center text-sm"
            style={{ color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}
          >
            {searchQuery() ? 'No matches' : 'No conversations yet'}
          </div>
        </Show>
      </div>

      <div class="px-2 py-2" style={{ 'border-top': '1px solid oklch(0.30 0.03 185)' }}>
        <button
          onClick={() => setSkillsExpanded(!skillsExpanded())}
          class="flex items-center gap-1 px-2 py-1.5 w-full transition-colors"
          style={{
            'font-size': '0.6875rem',
            'font-weight': '600',
            'font-family': 'var(--font-display)',
            color: 'oklch(0.50 0.04 185)',
            'text-transform': 'uppercase',
            'letter-spacing': '0.08em',
          }}
        >
          <Show when={skillsExpanded()} fallback={<ChevronRight size={12} />}>
            <ChevronDown size={12} />
          </Show>
          Skills & Modes
        </button>
        <Show when={skillsExpanded()}>
          <div class="mt-1 space-y-0.5 max-h-56 overflow-y-auto">
            <For each={Object.entries(modelsState.skills)}>
              {([id, skill]) => (
                <SkillCard
                  id={id}
                  name={skill.name}
                  active={modelsState.activeSkill === id}
                  onClick={() => setActiveSkill(id)}
                />
              )}
            </For>
          </div>
        </Show>
      </div>

      <div
        class="px-3 py-2 flex items-center justify-between"
        style={{ 'border-top': '1px solid oklch(0.30 0.03 185)', 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)' }}
      >
        <button class="flex items-center gap-1.5 transition-colors">
          <Settings size={14} />
          <span style={{ 'font-family': 'var(--font-body)' }}>Settings</span>
        </button>
        <button
          onClick={toggleTheme}
          class="transition-colors"
          title="Toggle theme"
        >
          <Show when={uiState.theme === 'dark'} fallback={<Sun size={14} />}>
            <Moon size={14} />
          </Show>
        </button>
        <span style={{ 'font-family': 'var(--font-mono)', 'font-size': '0.6875rem' }}>v1.0.0</span>
      </div>
    </div>
  )
}
