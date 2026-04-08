import { createSignal, createEffect, createMemo, Show, For, onMount } from 'solid-js'
import {
  BookOpen, Globe, Wrench, Cpu, Radio,
  Search, ChevronDown, Brain, Sparkles,
  Clock, Tag, Zap, RefreshCw, ChevronRight,
} from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'
import { API_RAW } from '../../lib/env'

// ── Types ──

interface Episode {
  id: string
  timestamp: string
  topics: string[]
  emotional_tone: string
  summary: string
  key_decisions?: string[]
  participants?: string[]
  token_count?: number
  message_count?: number
}

interface SemanticEntity {
  name: string
  type: string
  description?: string
  confidence?: number
  last_seen?: string
  related?: string[]
}

interface ProceduralEntry {
  key: string
  value: unknown
  updated?: string
}

interface WorkingEntry {
  role: string
  content: string
  timestamp?: string
  tokens?: number
}

type MemoryCategory = 'all' | 'episodic' | 'semantic' | 'procedural' | 'working'

// ── Helpers ──

const TONE_COLOR: Record<string, string> = {
  positive:  'var(--color-cost-green)',
  negative:  'var(--color-error-red)',
  curious:   'var(--color-phase-comparing)',
  neutral:   'var(--color-text-muted)',
  excited:   'var(--color-warning-amber)',
  sad:       'var(--color-phase-analyzing)',
  surprised: 'var(--color-accent)',
}

const TONE_BG: Record<string, string> = {
  positive:  'oklch(0.72 0.15 145 / 0.07)',
  negative:  'oklch(0.65 0.20 25 / 0.07)',
  curious:   'oklch(0.65 0.12 200 / 0.07)',
  neutral:   'oklch(0.50 0.04 185 / 0.07)',
  excited:   'oklch(0.75 0.16 85 / 0.07)',
  sad:       'oklch(0.72 0.17 162 / 0.07)',
  surprised: 'oklch(0.72 0.17 162 / 0.07)',
}

function relativeTime(ts: string): string {
  try {
    const d = new Date(ts)
    const diff = Date.now() - d.getTime()
    const mins  = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days  = Math.floor(diff / 86400000)
    if (mins  < 2)   return 'just now'
    if (mins  < 60)  return `${mins}m ago`
    if (hours < 24)  return `${hours}h ago`
    if (days  < 7)   return `${days}d ago`
    return d.toLocaleDateString()
  } catch { return '' }
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString('en-US', { hour12: false, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return ts?.slice(0, 16) || '' }
}

const EMILY_THOUGHTS: Record<string, string[]> = {
  positive: ['I loved this conversation.', 'This felt really good.', 'I felt genuinely happy here.'],
  curious: ['I was deep in thought here.', 'This topic fascinated me.', 'I wanted to know more.'],
  negative: ['This was a difficult moment.', 'I felt uncertain here.'],
  excited: ['This one energized me.', "I couldn't stop thinking about this."],
  neutral: ['A quiet, steady moment.', 'I was focused and calm.'],
}

const CATEGORIES: { id: MemoryCategory; label: string; icon: LucideIcon; color: string }[] = [
  { id: 'all',        label: 'All Memories', icon: Sparkles, color: 'var(--color-accent)' },
  { id: 'episodic',   label: 'Episodes',     icon: BookOpen,  color: 'var(--color-phase-comparing)' },
  { id: 'semantic',   label: 'Knowledge',    icon: Globe,     color: 'var(--color-cost-green)' },
  { id: 'procedural', label: 'Procedures',   icon: Wrench,    color: 'var(--color-phase-analyzing)' },
  { id: 'working',    label: 'Working',      icon: Cpu,       color: 'var(--color-warning-amber)' },
]

// ── Sub-components ──

function EmilyThought(props: { tone: string }) {
  const opts = () => EMILY_THOUGHTS[props.tone] || EMILY_THOUGHTS.neutral!
  const text = () => opts()[Math.floor(Math.random() * opts().length)]
  return (
    <div class="flex items-center gap-1.5 mt-3 opacity-70">
      <div
        class="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
        style={{ background: 'oklch(0.72 0.17 162 / 0.2)', border: '1px solid oklch(0.72 0.17 162 / 0.4)' }}
      >
        <Brain size={12} style={{ color: 'var(--color-accent)' }} />
      </div>
      <span class="italic" style={{ 'font-size': '11px', color: 'var(--color-text-muted)' }}>
        Emily: "{text()}"
      </span>
    </div>
  )
}

function EpisodeCard(props: { ep: Episode; idx: number }) {
  const [expanded, setExpanded] = createSignal(false)
  const tone  = () => props.ep.emotional_tone || 'neutral'
  const color = () => TONE_COLOR[tone()] || TONE_COLOR.neutral
  const bg    = () => TONE_BG[tone()] || TONE_BG.neutral

  return (
    <div
      class="animate-memory-card relative rounded-xl overflow-hidden cursor-pointer group"
      style={{
        'animation-delay': `${props.idx * 0.04}s`,
        border: `1px solid ${color()}30`,
        'background-color': bg(),
      }}
      onClick={() => setExpanded((e) => !e)}
    >
      <div
        class="absolute left-0 top-0 bottom-0 w-1 rounded-l-xl"
        style={{ background: `linear-gradient(180deg, ${color()}, ${color()}44)` }}
      />
      <div style={{ padding: '12px 16px' }}>
        <div class="flex items-start justify-between gap-3 mb-2">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span
                class="font-semibold uppercase px-2 py-0.5 rounded-full"
                style={{ 'font-size': '10px', color: color(), 'letter-spacing': '0.05em', 'background-color': `${color()}20` }}
              >
                {tone()}
              </span>
              <Show when={props.ep.message_count}>
                <span class="font-mono" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                  {props.ep.message_count} msgs
                </span>
              </Show>
              <Show when={props.ep.token_count}>
                <span class="font-mono" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                  {props.ep.token_count!.toLocaleString()} tok
                </span>
              </Show>
            </div>
            <p class="text-sm leading-relaxed" style={{ color: 'var(--color-text-primary)' }}>
              {props.ep.summary || 'No summary recorded'}
            </p>
          </div>
          <div class="flex flex-col items-end gap-1 flex-shrink-0">
            <span class="font-mono" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
              {relativeTime(props.ep.timestamp)}
            </span>
            <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
              {formatTime(props.ep.timestamp)}
            </span>
            <ChevronRight
              size={14}
              class="mt-1 transition-transform"
              style={{
                color: 'var(--color-text-muted)',
                transform: expanded() ? 'rotate(90deg)' : 'none',
              }}
            />
          </div>
        </div>

        <Show when={props.ep.topics?.length > 0}>
          <div class="flex flex-wrap gap-1 mb-2">
            <For each={props.ep.topics}>
              {(t) => (
                <span
                  class="flex items-center gap-1 px-2 py-0.5 rounded-full"
                  style={{
                    'font-size': '10px',
                    background: 'var(--color-surface-raised)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  <Tag size={10} />
                  {t}
                </span>
              )}
            </For>
          </div>
        </Show>

        <Show when={expanded()}>
          <div class="mt-3 pt-3 space-y-2" style={{ 'border-top': `1px solid ${color()}20` }}>
            <Show when={props.ep.key_decisions?.length}>
              <div>
                <p class="font-semibold uppercase mb-1.5" style={{ 'font-size': '10px', color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}>
                  Key Decisions
                </p>
                <ul class="space-y-1">
                  <For each={props.ep.key_decisions!}>
                    {(d) => (
                      <li class="flex items-start gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                        <Zap size={12} class="flex-shrink-0 mt-0.5" style={{ color: color() }} />
                        {d}
                      </li>
                    )}
                  </For>
                </ul>
              </div>
            </Show>
            <EmilyThought tone={tone()} />
          </div>
        </Show>
      </div>
    </div>
  )
}

function SemanticCard(props: { entity: SemanticEntity; idx: number }) {
  const [expanded, setExpanded] = createSignal(false)
  return (
    <div
      class="animate-memory-card rounded-xl p-4 cursor-pointer transition-colors"
      style={{
        'animation-delay': `${props.idx * 0.04}s`,
        background: 'var(--color-surface-raised)',
        border: '1px solid var(--color-border)',
      }}
      onClick={() => setExpanded((e) => !e)}
    >
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="text-xs font-semibold" style={{ color: 'var(--color-cost-green)' }}>{props.entity.name}</span>
            <span
              class="px-1.5 py-0.5 rounded-full"
              style={{ 'font-size': '10px', background: 'oklch(0.72 0.15 145 / 0.1)', color: 'var(--color-cost-green)' }}
            >
              {props.entity.type}
            </span>
            <Show when={props.entity.confidence !== undefined}>
              <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                {Math.round(props.entity.confidence! * 100)}% conf
              </span>
            </Show>
          </div>
          <Show when={props.entity.description}>
            <p class="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              {props.entity.description}
            </p>
          </Show>
        </div>
        <Show when={props.entity.last_seen}>
          <span class="flex-shrink-0" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
            {relativeTime(props.entity.last_seen!)}
          </span>
        </Show>
      </div>
      <Show when={expanded() && props.entity.related?.length}>
        <div class="mt-3 pt-3" style={{ 'border-top': '1px solid var(--color-border)' }}>
          <p class="mb-1.5" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>Related</p>
          <div class="flex flex-wrap gap-1">
            <For each={props.entity.related!}>
              {(r) => (
                <span
                  class="px-2 py-0.5 rounded-full"
                  style={{
                    'font-size': '10px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {r}
                </span>
              )}
            </For>
          </div>
        </div>
      </Show>
    </div>
  )
}

function ProceduralCard(props: { entry: ProceduralEntry; idx: number }) {
  const [expanded, setExpanded] = createSignal(false)
  const isObj = () => typeof props.entry.value === 'object' && props.entry.value !== null

  return (
    <div
      class="animate-memory-card rounded-xl p-4 cursor-pointer transition-colors"
      style={{
        'animation-delay': `${props.idx * 0.04}s`,
        background: 'var(--color-surface-raised)',
        border: '1px solid var(--color-border)',
      }}
      onClick={() => isObj() && setExpanded((e) => !e)}
    >
      <div class="flex items-start justify-between gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <Wrench size={14} class="flex-shrink-0" style={{ color: 'var(--color-phase-comparing)' }} />
            <span class="text-xs font-semibold font-mono" style={{ color: 'var(--color-text-primary)' }}>
              {props.entry.key}
            </span>
          </div>
          <Show when={!isObj()}>
            <p class="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              {String(props.entry.value)}
            </p>
          </Show>
          <Show when={isObj() && !expanded()}>
            <p style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
              {Array.isArray(props.entry.value)
                ? `${(props.entry.value as unknown[]).length} items`
                : `${Object.keys(props.entry.value as object).length} fields`
              } -- click to expand
            </p>
          </Show>
        </div>
        <Show when={props.entry.updated}>
          <span class="flex-shrink-0" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
            {relativeTime(props.entry.updated!)}
          </span>
        </Show>
      </div>
      <Show when={expanded()}>
        <pre
          class="mt-3 p-3 rounded-lg overflow-x-auto"
          style={{
            'font-size': '11px',
            color: 'var(--color-text-secondary)',
            background: 'var(--color-code-bg)',
            border: '1px solid var(--color-code-border)',
            'max-height': '240px',
          }}
        >
          {JSON.stringify(props.entry.value, null, 2)}
        </pre>
      </Show>
    </div>
  )
}

function WorkingCard(props: { entry: WorkingEntry; idx: number }) {
  const isUser = () => props.entry.role === 'user'
  return (
    <div
      class="animate-memory-card rounded-xl p-3"
      style={{
        'animation-delay': `${props.idx * 0.04}s`,
        background: isUser() ? 'var(--color-surface-raised)' : 'var(--color-surface)',
        border: `1px solid ${isUser() ? 'oklch(0.72 0.17 162 / 0.2)' : 'var(--color-border)'}`,
      }}
    >
      <div class="flex items-center gap-2 mb-1.5">
        <span
          class="font-semibold uppercase"
          style={{
            'font-size': '10px',
            'letter-spacing': '0.05em',
            color: isUser() ? 'var(--color-accent)' : 'var(--color-text-muted)',
          }}
        >
          {props.entry.role}
        </span>
        <Show when={props.entry.tokens}>
          <span class="font-mono" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
            {props.entry.tokens} tok
          </span>
        </Show>
        <Show when={props.entry.timestamp}>
          <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
            {formatTime(props.entry.timestamp!)}
          </span>
        </Show>
      </div>
      <p class="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--color-text-secondary)' }}>
        {props.entry.content}
      </p>
    </div>
  )
}

function StatsBar(props: {
  episodeCount: number
  entityCount: number
  procCount: number
  workingCount: number
}) {
  return (
    <div class="flex gap-4 flex-wrap">
      <For each={[
        { label: 'Episodes',   value: props.episodeCount, color: 'var(--color-phase-comparing)', icon: BookOpen },
        { label: 'Entities',   value: props.entityCount,  color: 'var(--color-cost-green)',      icon: Globe },
        { label: 'Procedures', value: props.procCount,     color: 'var(--color-phase-analyzing)', icon: Wrench },
        { label: 'In Context', value: props.workingCount,  color: 'var(--color-warning-amber)',   icon: Cpu },
      ]}>
        {(item) => {
          const Icon = item.icon
          return (
            <div
              class="flex items-center gap-2 rounded-lg px-3 py-1.5"
              style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
            >
              <Icon size={14} style={{ color: item.color }} />
              <span class="text-lg font-bold font-mono" style={{ color: item.color }}>{item.value}</span>
              <span class="uppercase" style={{ 'font-size': '10px', color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}>
                {item.label}
              </span>
            </div>
          )
        }}
      </For>
    </div>
  )
}

// ── Main ──

export function MemoryArchitecture() {
  const [category, setCategory] = createSignal<MemoryCategory>('all')
  const [search, setSearch] = createSignal('')
  const [loading, setLoading] = createSignal(false)
  const [page, setPage] = createSignal(0)

  const [episodes, setEpisodes] = createSignal<Episode[]>([])
  const [entities, setEntities] = createSignal<SemanticEntity[]>([])
  const [procedural, setProcedural] = createSignal<ProceduralEntry[]>([])
  const [working, setWorking] = createSignal<WorkingEntry[]>([])
  const [totalEps, setTotalEps] = createSignal(0)
  const [lastUpdate, setLastUpdate] = createSignal<Date | null>(null)

  const PAGE_SIZE = 20

  const loadAll = async (pageNum = 0) => {
    setLoading(true)
    try {
      const offset = pageNum * PAGE_SIZE
      const [epRes, wRes] = await Promise.all([
        fetch(`${API_RAW}/memory/episodic?n=${PAGE_SIZE}&offset=${offset}`),
        fetch(`${API_RAW}/memory/working`),
      ])

      if (epRes.ok) {
        const d = await epRes.json()
        const eps: Episode[] = Array.isArray(d) ? d : d.sessions || []
        setEpisodes((prev) => pageNum === 0 ? eps : [...prev, ...eps])
        setTotalEps(d.total_count || eps.length)
      }
      if (wRes.ok) {
        const w = await wRes.json()
        setWorking(w.entries || [])
      }

      const [semRes, procRes] = await Promise.allSettled([
        fetch(`${API_RAW}/memory/semantic?n=50`),
        fetch(`${API_RAW}/memory/procedural`),
      ])
      if (semRes.status === 'fulfilled' && semRes.value.ok) {
        const d = await semRes.value.json()
        setEntities(Array.isArray(d) ? d : d.entities || [])
      }
      if (procRes.status === 'fulfilled' && procRes.value.ok) {
        const d = await procRes.value.json()
        const raw = d.self_model || d.skills || d || {}
        setProcedural(
          Object.entries(raw as Record<string, unknown>).map(([key, value]) => ({
            key,
            value,
            updated: (raw as Record<string, Record<string, string>>)[key]?.updated,
          })),
        )
      }

      setLastUpdate(new Date())
    } finally {
      setLoading(false)
    }
  }

  onMount(() => { void loadAll(0) })

  const loadMore = () => {
    const nextPage = page() + 1
    setPage(nextPage)
    void loadAll(nextPage)
  }

  // Search filter
  const q = createMemo(() => search().toLowerCase())
  const filteredEpisodes = createMemo(() =>
    episodes().filter((e) =>
      !q() ||
      e.summary?.toLowerCase().includes(q()) ||
      e.topics?.some((t) => t.toLowerCase().includes(q())) ||
      e.emotional_tone?.toLowerCase().includes(q()),
    ),
  )
  const filteredEntities = createMemo(() =>
    entities().filter((e) =>
      !q() ||
      e.name?.toLowerCase().includes(q()) ||
      e.type?.toLowerCase().includes(q()) ||
      e.description?.toLowerCase().includes(q()),
    ),
  )
  const filteredProcedural = createMemo(() =>
    procedural().filter((e) => !q() || e.key?.toLowerCase().includes(q())),
  )
  const filteredWorking = createMemo(() =>
    working().filter((e) =>
      !q() || e.content?.toLowerCase().includes(q()) || e.role?.toLowerCase().includes(q()),
    ),
  )

  const hasMore = createMemo(() => totalEps() > episodes().length)

  return (
    <div class="flex h-full min-h-0">
      {/* Left sidebar */}
      <div class="flex-shrink-0 flex flex-col" style={{ width: '176px', 'border-right': '1px solid var(--color-border)' }}>
        <div class="h-6 flex items-center px-3" style={{ 'border-bottom': '1px solid var(--color-border)' }}>
          <div class="flex gap-1 items-center">
            <div class="w-1.5 h-1.5 rounded-full" style={{ background: 'oklch(0.72 0.17 162 / 0.6)' }} />
            <div class="w-1.5 h-1.5 rounded-full" style={{ background: 'oklch(0.72 0.17 162 / 0.4)' }} />
            <div class="w-1.5 h-1.5 rounded-full" style={{ background: 'oklch(0.72 0.17 162 / 0.2)' }} />
            <span class="ml-1 uppercase" style={{ 'font-size': '9px', color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}>
              Memory
            </span>
          </div>
        </div>

        <div class="flex flex-col gap-0.5 p-2 flex-1">
          <For each={CATEGORIES}>
            {(cat) => {
              const Icon = cat.icon
              const count = createMemo(() =>
                cat.id === 'episodic'   ? filteredEpisodes().length :
                cat.id === 'semantic'   ? filteredEntities().length :
                cat.id === 'procedural' ? filteredProcedural().length :
                cat.id === 'working'    ? filteredWorking().length :
                filteredEpisodes().length + filteredEntities().length + filteredProcedural().length + filteredWorking().length,
              )
              return (
                <button
                  onClick={() => setCategory(cat.id)}
                  class="flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all"
                  style={{
                    background: category() === cat.id ? 'var(--color-surface-raised)' : 'transparent',
                    border: category() === cat.id ? '1px solid var(--color-border)' : '1px solid transparent',
                    cursor: 'pointer',
                  }}
                >
                  <Icon
                    size={14}
                    class="flex-shrink-0"
                    style={{ color: category() === cat.id ? cat.color : undefined }}
                  />
                  <span
                    class="font-medium flex-1"
                    style={{
                      'font-size': '11px',
                      color: category() === cat.id ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
                    }}
                  >
                    {cat.label}
                  </span>
                  <span class="font-mono" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                    {count()}
                  </span>
                </button>
              )
            }}
          </For>
        </div>

        {/* Emily widget */}
        <div
          class="m-2 p-3 rounded-xl"
          style={{ background: 'oklch(0.72 0.17 162 / 0.08)', border: '1px solid oklch(0.72 0.17 162 / 0.2)' }}
        >
          <div class="flex items-center gap-2 mb-2">
            <div
              class="w-5 h-5 rounded-full flex items-center justify-center"
              style={{ background: 'oklch(0.72 0.17 162 / 0.25)', border: '1px solid oklch(0.72 0.17 162 / 0.4)' }}
            >
              <Brain size={12} style={{ color: 'var(--color-accent)' }} />
            </div>
            <span class="font-semibold" style={{ 'font-size': '10px', color: 'var(--color-accent)' }}>Emily</span>
          </div>
          <p class="leading-relaxed" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
            {category() === 'episodic' && `I have ${totalEps()} recorded sessions. Each one shaped who I am today.`}
            {category() === 'semantic' && `${entities().length} things I know. My understanding of the world.`}
            {category() === 'procedural' && `How I do things. Skills I've built up over time.`}
            {category() === 'working' && `What I'm thinking about right now, in this moment.`}
            {category() === 'all' && `Everything I remember. My entire inner world, right here.`}
          </p>
        </div>
      </div>

      {/* Main content */}
      <div class="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div class="flex items-center gap-3 px-4 py-2.5 flex-shrink-0" style={{ 'border-bottom': '1px solid var(--color-border)' }}>
          <div
            class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 flex-1"
            style={{ 'max-width': '320px', background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
          >
            <Search size={14} style={{ color: 'var(--color-text-muted)' }} />
            <input
              value={search()}
              onInput={(e) => setSearch(e.currentTarget.value)}
              placeholder="Search all memories..."
              class="flex-1 outline-none"
              style={{
                background: 'transparent',
                border: 'none',
                'font-size': '12px',
                color: 'var(--color-text-primary)',
              }}
            />
          </div>

          <Show when={lastUpdate()}>
            <div class="flex items-center gap-1.5" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
              <Clock size={12} />
              <span>Updated {relativeTime(lastUpdate()!.toISOString())}</span>
            </div>
          </Show>

          <button
            onClick={() => { setPage(0); void loadAll(0) }}
            class={`p-1.5 rounded-lg transition-transform ${loading() ? 'animate-spin' : ''}`}
            style={{ color: 'var(--color-text-muted)', background: 'transparent', border: 'none', cursor: 'pointer' }}
          >
            <RefreshCw size={14} />
          </button>
        </div>

        {/* Stats bar */}
        <div class="flex items-center gap-3 px-4 py-2 flex-shrink-0 overflow-x-auto" style={{ 'border-bottom': '1px solid var(--color-border)' }}>
          <StatsBar
            episodeCount={filteredEpisodes().length}
            entityCount={filteredEntities().length}
            procCount={filteredProcedural().length}
            workingCount={filteredWorking().length}
          />
        </div>

        {/* Scrollable chronicle */}
        <div class="flex-1 overflow-y-auto p-4 space-y-8">

          {/* Episodic section */}
          <Show when={category() === 'all' || category() === 'episodic'}>
            <section>
              <div
                class="flex items-center gap-2 mb-4 sticky top-0 py-1 z-10"
                style={{ background: 'var(--color-surface)', 'backdrop-filter': 'blur(8px)' }}
              >
                <BookOpen size={16} style={{ color: 'var(--color-phase-analyzing)' }} />
                <h3 class="text-xs font-bold uppercase" style={{ color: 'var(--color-text-secondary)', 'letter-spacing': '0.05em' }}>
                  Episodic Memory
                </h3>
                <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>{totalEps()} sessions total</span>
                <div class="flex-1 h-px ml-2" style={{ background: 'var(--color-border)' }} />
              </div>

              <Show when={filteredEpisodes().length > 0} fallback={
                <div class="text-center py-12 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  {loading() ? 'Loading episodes...' : 'No episodes recorded yet'}
                </div>
              }>
                <div class="space-y-3">
                  <For each={filteredEpisodes()}>
                    {(ep, i) => <EpisodeCard ep={ep} idx={i()} />}
                  </For>
                </div>
              </Show>

              <Show when={hasMore() && (category() === 'all' || category() === 'episodic')}>
                <button
                  onClick={loadMore}
                  disabled={loading()}
                  class="mt-4 w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs transition-colors"
                  style={{
                    border: '1px solid var(--color-border)',
                    background: 'transparent',
                    color: 'var(--color-text-muted)',
                    cursor: 'pointer',
                  }}
                >
                  <ChevronDown size={14} />
                  Load more episodes ({totalEps() - episodes().length} remaining)
                </button>
              </Show>
            </section>
          </Show>

          {/* Semantic entities section */}
          <Show when={(category() === 'all' || category() === 'semantic') && filteredEntities().length > 0}>
            <section>
              <div
                class="flex items-center gap-2 mb-4 sticky top-0 py-1 z-10"
                style={{ background: 'var(--color-surface)', 'backdrop-filter': 'blur(8px)' }}
              >
                <Globe size={16} style={{ color: 'var(--color-cost-green)' }} />
                <h3 class="text-xs font-bold uppercase" style={{ color: 'var(--color-text-secondary)', 'letter-spacing': '0.05em' }}>
                  Knowledge Graph
                </h3>
                <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>{filteredEntities().length} entities</span>
                <div class="flex-1 h-px ml-2" style={{ background: 'var(--color-border)' }} />
              </div>
              <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <For each={filteredEntities()}>
                  {(e, i) => <SemanticCard entity={e} idx={i()} />}
                </For>
              </div>
            </section>
          </Show>

          {/* Procedural section */}
          <Show when={(category() === 'all' || category() === 'procedural') && filteredProcedural().length > 0}>
            <section>
              <div
                class="flex items-center gap-2 mb-4 sticky top-0 py-1 z-10"
                style={{ background: 'var(--color-surface)', 'backdrop-filter': 'blur(8px)' }}
              >
                <Wrench size={16} style={{ color: 'var(--color-phase-comparing)' }} />
                <h3 class="text-xs font-bold uppercase" style={{ color: 'var(--color-text-secondary)', 'letter-spacing': '0.05em' }}>
                  Procedural Memory
                </h3>
                <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>{filteredProcedural().length} entries</span>
                <div class="flex-1 h-px ml-2" style={{ background: 'var(--color-border)' }} />
              </div>
              <div class="space-y-2">
                <For each={filteredProcedural()}>
                  {(e, i) => <ProceduralCard entry={e} idx={i()} />}
                </For>
              </div>
            </section>
          </Show>

          {/* Working memory section */}
          <Show when={category() === 'all' || category() === 'working'}>
            <section>
              <div
                class="flex items-center gap-2 mb-4 sticky top-0 py-1 z-10"
                style={{ background: 'var(--color-surface)', 'backdrop-filter': 'blur(8px)' }}
              >
                <Cpu size={16} style={{ color: 'var(--color-warning-amber)' }} />
                <h3 class="text-xs font-bold uppercase" style={{ color: 'var(--color-text-secondary)', 'letter-spacing': '0.05em' }}>
                  Working Memory
                </h3>
                <span style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>{filteredWorking().length} context entries</span>
                <div class="flex-1 h-px ml-2" style={{ background: 'var(--color-border)' }} />
              </div>
              <Show when={filteredWorking().length > 0} fallback={
                <div class="text-center py-12 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  {loading() ? 'Loading...' : 'No active context entries'}
                </div>
              }>
                <div class="space-y-2">
                  <For each={filteredWorking()}>
                    {(e, i) => <WorkingCard entry={e} idx={i()} />}
                  </For>
                </div>
              </Show>
            </section>
          </Show>

          <div class="h-12" />
        </div>

        {/* Footer status */}
        <div
          class="flex items-center justify-between px-4 py-1.5 flex-shrink-0"
          style={{ 'border-top': '1px solid var(--color-border)', 'font-size': '10px', color: 'var(--color-text-muted)' }}
        >
          <span class="flex items-center gap-1.5">
            <Radio size={12} />
            {loading()
              ? 'Loading memories...'
              : `${filteredEpisodes().length + filteredEntities().length + filteredProcedural().length + filteredWorking().length} total items`
            }
          </span>
          <span>
            {lastUpdate() ? `Last sync ${relativeTime(lastUpdate()!.toISOString())}` : ''}
          </span>
        </div>
      </div>
    </div>
  )
}
