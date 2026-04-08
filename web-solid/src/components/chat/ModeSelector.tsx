import { createSignal, createEffect, createMemo, onCleanup, For, Show } from 'solid-js'
import { Search, X } from 'lucide-solid'
import { uiState, setModeSelectorOpen } from '../../stores/ui'
import { modelsState, setActiveSkill } from '../../stores/models'
import { getModesByCategory, getModeTheme, type ModeTheme } from '../../lib/mode-themes'

const CAPABILITY_LABELS: Record<string, { label: string; color: string }> = {
  thinking:    { label: 'Thinking',  color: 'oklch(0.60 0.15 230)' },
  web_search:  { label: 'Web',      color: 'oklch(0.70 0.13 215)' },
  code_exec:   { label: 'Code',     color: 'oklch(0.72 0.15 145)' },
  multi_model: { label: 'Multi',    color: 'oklch(0.75 0.16 85)' },
}

function TemperatureBar(props: { value: number }) {
  const pct = () => Math.round(props.value * 100)
  const barColor = () => {
    const L = 0.65 + props.value * 0.10
    const C = 0.12 + props.value * 0.05
    const H = 185 - props.value * 100
    return `oklch(${L.toFixed(2)} ${C.toFixed(2)} ${Math.round(H)})`
  }

  return (
    <div class="flex items-center gap-1.5" title={`Temperature: ${props.value}`}>
      <div class="w-12 h-1 rounded-full overflow-hidden" style={{ background: 'oklch(0.30 0.03 185)' }}>
        <div
          class="h-full rounded-full transition-all"
          style={{ width: `${pct()}%`, 'background-color': barColor() }}
        />
      </div>
      <span class="text-[10px] font-mono" style={{ color: 'oklch(0.58 0.04 185)' }}>{props.value}</span>
    </div>
  )
}

function ModeCard(props: {
  theme: ModeTheme
  active: boolean
  focused: boolean
  index: number
  onSelect: () => void
  onHover: () => void
}) {
  const Icon = props.theme.icon
  let ref: HTMLButtonElement | undefined

  createEffect(() => {
    if (props.focused) ref?.scrollIntoView({ block: 'nearest' })
  })

  return (
    <button
      ref={ref}
      onClick={props.onSelect}
      onMouseEnter={props.onHover}
      class="animate-mode-card flex items-start gap-3 p-3 rounded-xl text-left transition-colors"
      style={{
        'animation-delay': `${props.index * 28}ms`,
        background: props.focused ? 'oklch(0.26 0.03 185)' : '',
        'box-shadow': props.active ? `0 0 10px ${props.theme.glow}, inset 0 0 0 1px ${props.theme.accent}35` : '',
        outline: props.focused ? '1px solid oklch(0.30 0.03 185)' : '',
      }}
    >
      <div
        class="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: props.theme.gradient, 'box-shadow': `0 0 14px ${props.theme.glow}` }}
      >
        <Icon class="w-5 h-5" style={{ color: 'oklch(0.18 0.02 185)' }} />
      </div>

      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <span
            style={{
              'font-weight': '600',
              'font-size': 'var(--text-body)',
              'font-family': 'var(--font-display)',
              color: 'oklch(0.93 0.01 90)',
            }}
          >
            {props.theme.name}
          </span>
          <Show when={props.active}>
            <span
              class="px-1.5 py-0.5 rounded-full"
              style={{
                'font-size': '0.625rem',
                'font-weight': '700',
                'font-family': 'var(--font-display)',
                background: `${props.theme.accent}1f`,
                color: props.theme.accent,
              }}
            >
              Active
            </span>
          </Show>
        </div>
        <p
          class="mt-0.5 line-clamp-2"
          style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}
        >
          {props.theme.description}
        </p>

        <div class="flex items-center gap-2 mt-1.5">
          <Show when={props.theme.capabilities.length > 0}>
            <div class="flex items-center gap-1">
              <For each={props.theme.capabilities}>{(cap) => {
                const badge = CAPABILITY_LABELS[cap]
                return (
                  <Show when={badge}>
                    <span
                      class="px-1.5 py-0.5 rounded-full"
                      style={{
                        'font-size': '0.625rem',
                        'font-weight': '600',
                        'font-family': 'var(--font-display)',
                        background: `${badge!.color}1a`,
                        color: badge!.color,
                      }}
                    >
                      {badge!.label}
                    </span>
                  </Show>
                )
              }}</For>
            </div>
          </Show>
          <TemperatureBar value={props.theme.temperature} />
        </div>
      </div>
    </button>
  )
}

export function ModeSelector() {
  const [query, setQuery] = createSignal('')
  const [focusIdx, setFocusIdx] = createSignal(-1)
  let inputRef: HTMLInputElement | undefined

  const categories = createMemo(() => getModesByCategory())

  // Filter modes by search query
  const filtered = createMemo(() => {
    if (!query().trim()) return categories()
    const q = query().toLowerCase()
    return categories()
      .map((cat) => ({
        ...cat,
        modes: cat.modes.filter(
          (m) =>
            m.name.toLowerCase().includes(q) ||
            m.description.toLowerCase().includes(q) ||
            m.id.includes(q)
        ),
      }))
      .filter((cat) => cat.modes.length > 0)
  })

  // Flat list of all visible mode IDs for keyboard nav
  const flatModes = createMemo(() => filtered().flatMap((cat) => cat.modes))

  const selectMode = (id: string) => {
    setActiveSkill(id)
    setModeSelectorOpen(false)
    setQuery('')
    setFocusIdx(-1)
  }

  // Focus input on open
  createEffect(() => {
    if (uiState.modeSelectorOpen) {
      setQuery('')
      setFocusIdx(-1)
      requestAnimationFrame(() => inputRef?.focus())
    }
  })

  // Keyboard navigation
  createEffect(() => {
    if (!uiState.modeSelectorOpen) return

    const handler = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setFocusIdx((i) => Math.min(i + 1, flatModes().length - 1))
          break
        case 'ArrowUp':
          e.preventDefault()
          setFocusIdx((i) => Math.max(i - 1, 0))
          break
        case 'Enter':
          e.preventDefault()
          if (focusIdx() >= 0 && focusIdx() < flatModes().length) {
            selectMode(flatModes()[focusIdx()].id)
          }
          break
        case 'Escape':
          e.preventDefault()
          setModeSelectorOpen(false)
          break
      }
    }

    window.addEventListener('keydown', handler)
    onCleanup(() => window.removeEventListener('keydown', handler))
  })

  // Build a global running index so card stagger works across categories
  const categoryWithGlobalIdx = createMemo(() => {
    let globalIdx = 0
    return filtered().map((cat) => ({
      ...cat,
      modesWithIdx: cat.modes.map((mode) => ({ mode, idx: globalIdx++ })),
    }))
  })

  return (
    <Show when={uiState.modeSelectorOpen}>
      <div
        class="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]"
        style={{ background: 'oklch(0.18 0.02 185 / 0.88)', 'backdrop-filter': 'blur(6px)' }}
        onClick={(e) => { if (e.target === e.currentTarget) setModeSelectorOpen(false) }}
      >
        <div
          class="animate-mode-overlay w-[640px] max-h-[72vh] flex flex-col rounded-2xl shadow-2xl overflow-hidden"
          style={{ background: 'oklch(0.22 0.025 185)', border: '1px solid oklch(0.30 0.03 185)' }}
        >
          {/* Search header */}
          <div class="flex items-center gap-3 px-4 py-3" style={{ 'border-bottom': '1px solid oklch(0.30 0.03 185)' }}>
            <Search class="w-4 h-4 flex-shrink-0" style={{ color: 'oklch(0.50 0.04 185)' }} />
            <input
              ref={inputRef}
              value={query()}
              onInput={(e) => { setQuery(e.currentTarget.value); setFocusIdx(0) }}
              placeholder="Search modes..."
              class="flex-1 bg-transparent focus:outline-none"
              style={{ 'font-size': 'var(--text-body)', color: 'oklch(0.93 0.01 90)', 'font-family': 'var(--font-body)' }}
            />
            <button
              onClick={() => setModeSelectorOpen(false)}
              class="p-1 rounded-lg transition-colors"
              style={{ color: 'oklch(0.50 0.04 185)' }}
            >
              <X class="w-4 h-4" />
            </button>
          </div>

          {/* Mode list */}
          <div class="flex-1 overflow-y-auto px-3 py-3 space-y-4">
            <For each={categoryWithGlobalIdx()}>{(cat) => (
              <div>
                <h3
                  class="px-1 mb-2"
                  style={{
                    'font-size': '0.6875rem',
                    'font-weight': '600',
                    'font-family': 'var(--font-display)',
                    color: 'oklch(0.50 0.04 185)',
                    'text-transform': 'uppercase',
                    'letter-spacing': '0.08em',
                  }}
                >
                  {cat.label}
                </h3>
                <div class="grid grid-cols-2 gap-1.5">
                  <For each={cat.modesWithIdx}>{({ mode, idx }) => (
                    <ModeCard
                      theme={mode}
                      active={modelsState.activeSkill === mode.id}
                      focused={focusIdx() === flatModes().indexOf(mode)}
                      index={idx}
                      onSelect={() => selectMode(mode.id)}
                      onHover={() => setFocusIdx(flatModes().indexOf(mode))}
                    />
                  )}</For>
                </div>
              </div>
            )}</For>

            <Show when={flatModes().length === 0}>
              <div
                class="py-8 text-center"
                style={{ 'font-size': 'var(--text-body)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}
              >
                No modes match "{query()}"
              </div>
            </Show>
          </div>

          {/* Footer hint */}
          <div
            class="flex items-center justify-between px-4 py-2"
            style={{ 'border-top': '1px solid oklch(0.30 0.03 185)', 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}
          >
            <div class="flex items-center gap-3">
              <For each={[
                { key: '\u2191\u2193', rest: 'Navigate' },
                { key: '\u21B5', rest: 'Select' },
                { key: 'Esc', rest: 'Close' },
              ]}>{(hint) => (
                <span>
                  <kbd
                    class="px-1 py-0.5 rounded"
                    style={{ background: 'oklch(0.18 0.02 185)', border: '1px solid oklch(0.30 0.03 185)', color: 'oklch(0.65 0.03 185)', 'font-family': 'var(--font-mono)' }}
                  >
                    {hint.key}
                  </kbd>
                  {' '}{hint.rest}
                </span>
              )}</For>
            </div>
            <span style={{ 'font-family': 'var(--font-body)' }}>
              Current:{' '}
              <span style={{ color: getModeTheme(modelsState.activeSkill).accent, 'font-family': 'var(--font-display)' }}>
                {getModeTheme(modelsState.activeSkill).name}
              </span>
            </span>
          </div>
        </div>
      </div>
    </Show>
  )
}
