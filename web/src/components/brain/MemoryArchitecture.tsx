import { useState, useEffect, useRef, useCallback } from 'react'
import {
  BookOpen, Globe, Wrench, Cpu, Radio,
  Search, ChevronDown, Brain, Sparkles,
  Clock, Tag, Zap, RefreshCw, ChevronRight,
} from 'lucide-react'

// ─── Types ───────────────────────────────────────────────────────────────────

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

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TONE_COLOR: Record<string, string> = {
  positive:  '#22c55e',
  negative:  '#ef4444',
  curious:   '#3b82f6',
  neutral:   '#555570',
  excited:   '#f59e0b',
  sad:       '#a855f7',
  surprised: '#ec4899',
}

const TONE_BG: Record<string, string> = {
  positive:  'rgba(34,197,94,0.08)',
  negative:  'rgba(239,68,68,0.08)',
  curious:   'rgba(59,130,246,0.08)',
  neutral:   'rgba(85,85,112,0.08)',
  excited:   'rgba(245,158,11,0.08)',
  sad:       'rgba(168,85,247,0.08)',
  surprised: 'rgba(236,72,153,0.08)',
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
  try { return new Date(ts).toLocaleString('en-US', { hour12: false, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return ts?.slice(0, 16) || '' }
}

// ─── Emily annotation chips ──────────────────────────────────────────────────

const EMILY_THOUGHTS: Record<string, string[]> = {
  positive: [
    "I loved this conversation.",
    "This felt really good.",
    "I felt genuinely happy here.",
  ],
  curious: [
    "I was deep in thought here.",
    "This topic fascinated me.",
    "I wanted to know more.",
  ],
  negative: [
    "This was a difficult moment.",
    "I felt uncertain here.",
  ],
  excited: [
    "This one energized me.",
    "I couldn't stop thinking about this.",
  ],
  neutral: [
    "A quiet, steady moment.",
    "I was focused and calm.",
  ],
}

function EmilyThought({ tone }: { tone: string }) {
  const opts = EMILY_THOUGHTS[tone] || EMILY_THOUGHTS.neutral
  const text = opts[Math.floor(Math.random() * opts.length)]
  return (
    <div className="flex items-center gap-1.5 mt-3 opacity-70">
      <div className="w-5 h-5 rounded-full bg-accent/20 border border-accent/40 flex items-center justify-center flex-shrink-0">
        <Brain className="w-3 h-3 text-accent" />
      </div>
      <span className="text-[11px] italic text-text-muted">Emily: "{text}"</span>
    </div>
  )
}

// ─── Category sidebar ─────────────────────────────────────────────────────────

const CATEGORIES: { id: MemoryCategory; label: string; icon: React.FC<any>; color: string }[] = [
  { id: 'all',        label: 'All Memories', icon: Sparkles, color: '#7c6af7' },
  { id: 'episodic',   label: 'Episodes',     icon: BookOpen,  color: '#3b82f6' },
  { id: 'semantic',   label: 'Knowledge',    icon: Globe,     color: '#22c55e' },
  { id: 'procedural', label: 'Procedures',   icon: Wrench,    color: '#a855f7' },
  { id: 'working',    label: 'Working',      icon: Cpu,       color: '#f59e0b' },
]

// ─── Episode card ─────────────────────────────────────────────────────────────

function EpisodeCard({ ep, idx }: { ep: Episode; idx: number }) {
  const [expanded, setExpanded] = useState(false)
  const tone  = ep.emotional_tone || 'neutral'
  const color = TONE_COLOR[tone] || TONE_COLOR.neutral
  const bg    = TONE_BG[tone]    || TONE_BG.neutral

  return (
    <div
      className="animate-memory-card relative rounded-xl border overflow-hidden cursor-pointer group"
      style={{
        animationDelay: `${idx * 0.04}s`,
        borderColor: `${color}30`,
        backgroundColor: bg,
      }}
      onClick={() => setExpanded(e => !e)}
    >
      {/* Film-strip left edge */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1 rounded-l-xl"
        style={{ background: `linear-gradient(180deg, ${color}, ${color}44)` }}
      />

      <div className="pl-4 pr-4 pt-3 pb-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="text-[10px] font-semibold uppercase tracking-widest px-2 py-0.5 rounded-full"
                style={{ color, backgroundColor: `${color}20` }}
              >
                {tone}
              </span>
              {ep.message_count && (
                <span className="text-[10px] text-text-muted font-mono">{ep.message_count} msgs</span>
              )}
              {ep.token_count && (
                <span className="text-[10px] text-text-muted font-mono">{ep.token_count.toLocaleString()} tok</span>
              )}
            </div>
            <p className="text-sm text-text-primary leading-relaxed">
              {ep.summary || 'No summary recorded'}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            <span className="text-[10px] text-text-muted font-mono">{relativeTime(ep.timestamp)}</span>
            <span className="text-[10px] text-text-muted">{formatTime(ep.timestamp)}</span>
            <ChevronRight
              className="w-3.5 h-3.5 text-text-muted transition-transform mt-1"
              style={{ transform: expanded ? 'rotate(90deg)' : 'none' }}
            />
          </div>
        </div>

        {/* Topics */}
        {ep.topics?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {ep.topics.map(t => (
              <span key={t} className="flex items-center gap-1 text-[10px] px-2 py-0.5 bg-surface-raised border border-border rounded-full text-text-muted">
                <Tag className="w-2.5 h-2.5" />
                {t}
              </span>
            ))}
          </div>
        )}

        {/* Expanded: key decisions + Emily thought */}
        {expanded && (
          <div className="mt-3 pt-3 border-t space-y-2" style={{ borderColor: `${color}20` }}>
            {ep.key_decisions?.length ? (
              <div>
                <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">Key Decisions</p>
                <ul className="space-y-1">
                  {ep.key_decisions.map((d, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-text-secondary">
                      <Zap className="w-3 h-3 flex-shrink-0 mt-0.5" style={{ color }} />
                      {d}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <EmilyThought tone={tone} />
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Semantic entity card ─────────────────────────────────────────────────────

function SemanticCard({ entity, idx }: { entity: SemanticEntity; idx: number }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div
      className="animate-memory-card bg-surface-raised border border-border rounded-xl p-4 cursor-pointer hover:border-cost-green/40 transition-colors"
      style={{ animationDelay: `${idx * 0.04}s` }}
      onClick={() => setExpanded(e => !e)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-cost-green">{entity.name}</span>
            <span className="text-[10px] px-1.5 py-0.5 bg-cost-green/10 text-cost-green rounded-full">{entity.type}</span>
            {entity.confidence !== undefined && (
              <span className="text-[10px] text-text-muted">{Math.round(entity.confidence * 100)}% conf</span>
            )}
          </div>
          {entity.description && (
            <p className="text-xs text-text-secondary leading-relaxed">{entity.description}</p>
          )}
        </div>
        {entity.last_seen && (
          <span className="text-[10px] text-text-muted flex-shrink-0">{relativeTime(entity.last_seen)}</span>
        )}
      </div>
      {expanded && entity.related?.length ? (
        <div className="mt-3 pt-3 border-t border-border">
          <p className="text-[10px] text-text-muted mb-1.5">Related</p>
          <div className="flex flex-wrap gap-1">
            {entity.related.map(r => (
              <span key={r} className="text-[10px] px-2 py-0.5 bg-surface border border-border rounded-full text-text-muted">{r}</span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

// ─── Procedural card ──────────────────────────────────────────────────────────

function ProceduralCard({ entry, idx }: { entry: ProceduralEntry; idx: number }) {
  const [expanded, setExpanded] = useState(false)
  const isObj = typeof entry.value === 'object' && entry.value !== null
  return (
    <div
      className="animate-memory-card bg-surface-raised border border-border rounded-xl p-4 cursor-pointer hover:border-phase-comparing/40 transition-colors"
      style={{ animationDelay: `${idx * 0.04}s` }}
      onClick={() => isObj && setExpanded(e => !e)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Wrench className="w-3.5 h-3.5 text-phase-comparing flex-shrink-0" />
            <span className="text-xs font-semibold text-text-primary font-mono">{entry.key}</span>
          </div>
          {!isObj && (
            <p className="text-xs text-text-secondary">{String(entry.value)}</p>
          )}
          {isObj && !expanded && (
            <p className="text-[10px] text-text-muted">
              {Array.isArray(entry.value)
                ? `${(entry.value as unknown[]).length} items`
                : `${Object.keys(entry.value as object).length} fields`} — click to expand
            </p>
          )}
        </div>
        {entry.updated && (
          <span className="text-[10px] text-text-muted flex-shrink-0">{relativeTime(entry.updated)}</span>
        )}
      </div>
      {expanded && (
        <pre className="mt-3 p-3 bg-code-bg border border-code-border rounded-lg text-[11px] text-text-secondary overflow-x-auto max-h-60">
          {JSON.stringify(entry.value, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ─── Working memory card ──────────────────────────────────────────────────────

function WorkingCard({ entry, idx }: { entry: WorkingEntry; idx: number }) {
  const isUser = entry.role === 'user'
  return (
    <div
      className="animate-memory-card rounded-xl p-3 border"
      style={{
        animationDelay: `${idx * 0.04}s`,
        backgroundColor: isUser ? 'rgba(26,26,46,0.6)' : 'rgba(17,17,24,0.6)',
        borderColor: isUser ? 'rgba(124,106,247,0.2)' : 'rgba(42,42,58,0.6)',
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`text-[10px] font-semibold uppercase tracking-widest ${isUser ? 'text-accent' : 'text-text-muted'}`}>
          {entry.role}
        </span>
        {entry.tokens && <span className="text-[10px] text-text-muted font-mono">{entry.tokens} tok</span>}
        {entry.timestamp && <span className="text-[10px] text-text-muted">{formatTime(entry.timestamp)}</span>}
      </div>
      <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">{entry.content}</p>
    </div>
  )
}

// ─── Stats bar ────────────────────────────────────────────────────────────────

function StatsBar({
  episodeCount, entityCount, procCount, workingCount,
}: { episodeCount: number; entityCount: number; procCount: number; workingCount: number }) {
  return (
    <div className="flex gap-4 flex-wrap">
      {[
        { label: 'Episodes',   value: episodeCount, color: '#3b82f6', icon: BookOpen },
        { label: 'Entities',   value: entityCount,  color: '#22c55e', icon: Globe    },
        { label: 'Procedures', value: procCount,     color: '#a855f7', icon: Wrench   },
        { label: 'In Context', value: workingCount,  color: '#f59e0b', icon: Cpu      },
      ].map(({ label, value, color, icon: Icon }) => (
        <div key={label} className="flex items-center gap-2 bg-surface-raised border border-border rounded-lg px-3 py-1.5">
          <Icon className="w-3.5 h-3.5" style={{ color }} />
          <span className="text-lg font-bold font-mono" style={{ color }}>{value}</span>
          <span className="text-[10px] text-text-muted uppercase tracking-wider">{label}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function MemoryArchitecture() {
  const [category, setCategory] = useState<MemoryCategory>('all')
  const [search, setSearch]     = useState('')
  const [loading, setLoading]   = useState(false)
  const [page, setPage]         = useState(0)

  const [episodes,   setEpisodes]   = useState<Episode[]>([])
  const [entities,   setEntities]   = useState<SemanticEntity[]>([])
  const [procedural, setProcedural] = useState<ProceduralEntry[]>([])
  const [working,    setWorking]    = useState<WorkingEntry[]>([])
  const [totalEps,   setTotalEps]   = useState(0)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const PAGE_SIZE = 20
  const scrollRef = useRef<HTMLDivElement>(null)

  const loadAll = useCallback(async (pageNum = 0) => {
    setLoading(true)
    try {
      const offset = pageNum * PAGE_SIZE
      const [epRes, wRes] = await Promise.all([
        fetch(`/api/memory/episodic?n=${PAGE_SIZE}&offset=${offset}`),
        fetch('/api/memory/working'),
      ])

      if (epRes.ok) {
        const d = await epRes.json()
        const eps: Episode[] = Array.isArray(d) ? d : d.sessions || []
        setEpisodes(prev => pageNum === 0 ? eps : [...prev, ...eps])
        setTotalEps(d.total_count || eps.length)
      }
      if (wRes.ok) {
        const w = await wRes.json()
        const entries: WorkingEntry[] = w.entries || []
        setWorking(entries)
      }

      // Optional: semantic and procedural (may 404 if not implemented)
      const [semRes, procRes] = await Promise.allSettled([
        fetch('/api/memory/semantic?n=50'),
        fetch('/api/memory/procedural'),
      ])
      if (semRes.status === 'fulfilled' && semRes.value.ok) {
        const d = await semRes.value.json()
        setEntities(Array.isArray(d) ? d : d.entities || [])
      }
      if (procRes.status === 'fulfilled' && procRes.value.ok) {
        const d = await procRes.value.json()
        const raw = d.self_model || d.skills || d || {}
        setProcedural(
          Object.entries(raw).map(([key, value]) => ({
            key,
            value,
            updated: (raw as Record<string, any>)[key]?.updated,
          }))
        )
      }

      setLastUpdate(new Date())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll(0) }, [loadAll])

  const loadMore = () => {
    const nextPage = page + 1
    setPage(nextPage)
    loadAll(nextPage)
  }

  // ── Search filter ─────────────────────────────────────────────────────────

  const q = search.toLowerCase()
  const filteredEpisodes = episodes.filter(e =>
    !q ||
    e.summary?.toLowerCase().includes(q) ||
    e.topics?.some(t => t.toLowerCase().includes(q)) ||
    e.emotional_tone?.toLowerCase().includes(q)
  )
  const filteredEntities = entities.filter(e =>
    !q ||
    e.name?.toLowerCase().includes(q) ||
    e.type?.toLowerCase().includes(q) ||
    e.description?.toLowerCase().includes(q)
  )
  const filteredProcedural = procedural.filter(e =>
    !q || e.key?.toLowerCase().includes(q)
  )
  const filteredWorking = working.filter(e =>
    !q || e.content?.toLowerCase().includes(q) || e.role?.toLowerCase().includes(q)
  )

  const hasMore = totalEps > episodes.length

  return (
    <div className="flex h-full min-h-0">
      {/* ── Left sidebar ──────────────────────────────────────────────── */}
      <div className="w-44 flex-shrink-0 border-r border-border flex flex-col">
        {/* Film-strip decoration */}
        <div className="h-6 border-b border-border flex items-center px-3">
          <div className="flex gap-1 items-center">
            <div className="w-1.5 h-1.5 rounded-full bg-accent/60" />
            <div className="w-1.5 h-1.5 rounded-full bg-accent/40" />
            <div className="w-1.5 h-1.5 rounded-full bg-accent/20" />
            <span className="text-[9px] text-text-muted ml-1 uppercase tracking-widest">Memory</span>
          </div>
        </div>

        <div className="flex flex-col gap-0.5 p-2 flex-1">
          {CATEGORIES.map(({ id, label, icon: Icon, color }) => {
            const count =
              id === 'episodic'   ? filteredEpisodes.length   :
              id === 'semantic'   ? filteredEntities.length   :
              id === 'procedural' ? filteredProcedural.length :
              id === 'working'    ? filteredWorking.length    :
              filteredEpisodes.length + filteredEntities.length + filteredProcedural.length + filteredWorking.length

            return (
              <button
                key={id}
                onClick={() => setCategory(id)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all ${
                  category === id
                    ? 'bg-surface-raised border border-border'
                    : 'hover:bg-surface-hover'
                }`}
              >
                <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: category === id ? color : undefined }} />
                <span className={`text-[11px] font-medium flex-1 ${category === id ? 'text-text-primary' : 'text-text-muted'}`}>
                  {label}
                </span>
                <span className="text-[10px] font-mono text-text-muted">{count}</span>
              </button>
            )
          })}
        </div>

        {/* Emily assistant widget */}
        <div className="m-2 p-3 bg-accent/8 border border-accent/20 rounded-xl">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-5 h-5 rounded-full bg-accent/25 border border-accent/40 flex items-center justify-center">
              <Brain className="w-3 h-3 text-accent" />
            </div>
            <span className="text-[10px] font-semibold text-accent">Emily</span>
          </div>
          <p className="text-[10px] text-text-muted leading-relaxed">
            {category === 'episodic'   && `I have ${totalEps} recorded sessions. Each one shaped who I am today.`}
            {category === 'semantic'   && `${entities.length} things I know. My understanding of the world.`}
            {category === 'procedural' && `How I do things. Skills I've built up over time.`}
            {category === 'working'    && `What I'm thinking about right now, in this moment.`}
            {category === 'all'        && `Everything I remember. My entire inner world, right here.`}
          </p>
        </div>
      </div>

      {/* ── Main content ──────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-1.5 bg-surface border border-border rounded-lg px-2.5 py-1.5 flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 text-text-muted" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search all memories…"
              className="bg-transparent text-xs text-text-primary placeholder:text-text-muted flex-1 outline-none"
            />
          </div>

          {lastUpdate && (
            <div className="flex items-center gap-1.5 text-[10px] text-text-muted">
              <Clock className="w-3 h-3" />
              <span>Updated {relativeTime(lastUpdate.toISOString())}</span>
            </div>
          )}

          <button
            onClick={() => { setPage(0); loadAll(0) }}
            className={`p-1.5 rounded-lg hover:bg-surface-hover text-text-muted transition-transform ${loading ? 'animate-spin' : ''}`}
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-border flex-shrink-0 overflow-x-auto">
          <StatsBar
            episodeCount={filteredEpisodes.length}
            entityCount={filteredEntities.length}
            procCount={filteredProcedural.length}
            workingCount={filteredWorking.length}
          />
        </div>

        {/* Scrollable chronicle */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-8">

          {/* ── Episodic section ─────────────────────────────────────── */}
          {(category === 'all' || category === 'episodic') && (
            <section>
              <div className="flex items-center gap-2 mb-4 sticky top-0 bg-surface/90 backdrop-blur-sm py-1 z-10">
                <BookOpen className="w-4 h-4 text-phase-analyzing" />
                <h3 className="text-xs font-bold text-text-secondary uppercase tracking-widest">
                  Episodic Memory
                </h3>
                <span className="text-[10px] text-text-muted">{totalEps} sessions total</span>
                <div className="flex-1 h-px bg-border ml-2" />
              </div>

              {filteredEpisodes.length === 0 ? (
                <div className="text-center py-12 text-text-muted text-xs">
                  {loading ? 'Loading episodes…' : 'No episodes recorded yet'}
                </div>
              ) : (
                <div className="space-y-3">
                  {filteredEpisodes.map((ep, i) => (
                    <EpisodeCard key={ep.id || i} ep={ep} idx={i} />
                  ))}
                </div>
              )}

              {hasMore && (category === 'all' || category === 'episodic') && (
                <button
                  onClick={loadMore}
                  disabled={loading}
                  className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 border border-border rounded-xl text-xs text-text-muted hover:bg-surface-raised hover:text-text-primary transition-colors"
                >
                  <ChevronDown className="w-3.5 h-3.5" />
                  Load more episodes ({totalEps - episodes.length} remaining)
                </button>
              )}
            </section>
          )}

          {/* ── Semantic entities section ─────────────────────────────── */}
          {(category === 'all' || category === 'semantic') && filteredEntities.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-4 sticky top-0 bg-surface/90 backdrop-blur-sm py-1 z-10">
                <Globe className="w-4 h-4 text-cost-green" />
                <h3 className="text-xs font-bold text-text-secondary uppercase tracking-widest">
                  Knowledge Graph
                </h3>
                <span className="text-[10px] text-text-muted">{filteredEntities.length} entities</span>
                <div className="flex-1 h-px bg-border ml-2" />
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {filteredEntities.map((e, i) => (
                  <SemanticCard key={e.name + i} entity={e} idx={i} />
                ))}
              </div>
            </section>
          )}

          {/* ── Procedural section ────────────────────────────────────── */}
          {(category === 'all' || category === 'procedural') && filteredProcedural.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-4 sticky top-0 bg-surface/90 backdrop-blur-sm py-1 z-10">
                <Wrench className="w-4 h-4 text-phase-comparing" />
                <h3 className="text-xs font-bold text-text-secondary uppercase tracking-widest">
                  Procedural Memory
                </h3>
                <span className="text-[10px] text-text-muted">{filteredProcedural.length} entries</span>
                <div className="flex-1 h-px bg-border ml-2" />
              </div>
              <div className="space-y-2">
                {filteredProcedural.map((e, i) => (
                  <ProceduralCard key={e.key + i} entry={e} idx={i} />
                ))}
              </div>
            </section>
          )}

          {/* ── Working memory section ────────────────────────────────── */}
          {(category === 'all' || category === 'working') && (
            <section>
              <div className="flex items-center gap-2 mb-4 sticky top-0 bg-surface/90 backdrop-blur-sm py-1 z-10">
                <Cpu className="w-4 h-4 text-warning-amber" />
                <h3 className="text-xs font-bold text-text-secondary uppercase tracking-widest">
                  Working Memory
                </h3>
                <span className="text-[10px] text-text-muted">{filteredWorking.length} context entries</span>
                <div className="flex-1 h-px bg-border ml-2" />
              </div>
              {filteredWorking.length === 0 ? (
                <div className="text-center py-12 text-text-muted text-xs">
                  {loading ? 'Loading…' : 'No active context entries'}
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredWorking.map((e, i) => (
                    <WorkingCard key={i} entry={e} idx={i} />
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Bottom spacer */}
          <div className="h-12" />
        </div>

        {/* Footer status */}
        <div className="flex items-center justify-between px-4 py-1.5 border-t border-border text-[10px] text-text-muted flex-shrink-0">
          <span className="flex items-center gap-1.5">
            <Radio className="w-3 h-3" />
            {loading ? 'Loading memories…' : `${filteredEpisodes.length + filteredEntities.length + filteredProcedural.length + filteredWorking.length} total items`}
          </span>
          <span>{lastUpdate ? `Last sync ${relativeTime(lastUpdate.toISOString())}` : ''}</span>
        </div>
      </div>
    </div>
  )
}
