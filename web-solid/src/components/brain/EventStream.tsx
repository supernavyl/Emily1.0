/**
 * Virtualized live scrolling event feed with category filtering.
 * Data-lab aesthetic: phosphor-green timestamps, segmented filter bank, REC indicator.
 * Uses @tanstack/solid-virtual for paint-performant rendering of high-volume events.
 */

import { createSignal, createMemo, createEffect, Show, For } from 'solid-js'
import { createVirtualizer } from '@tanstack/solid-virtual'
import { brainState, type BrainEvent } from '../../stores/brain'

const CATEGORY_BORDER: Record<string, string> = {
  llm:        'var(--color-alert-warm)',
  fsm:        'var(--color-accent)',
  agent:      'var(--color-specimen-blue)',
  memory:     'var(--color-phosphor-green)',
  perception: 'var(--color-accent)',
  react:      'var(--color-phosphor-green)',
  log:        'var(--color-readout-dim)',
  tool:       'var(--color-threshold-red)',
  proactive:  'var(--color-specimen-blue)',
}

const CATEGORY_TEXT: Record<string, string> = {
  llm:        'var(--color-alert-warm)',
  fsm:        'var(--color-accent)',
  agent:      'var(--color-specimen-blue)',
  memory:     'var(--color-phosphor-green)',
  perception: 'var(--color-accent)',
  react:      'var(--color-phosphor-green)',
  log:        'var(--color-readout-dim)',
  tool:       'var(--color-threshold-red)',
  proactive:  'var(--color-specimen-blue)',
}

const ALL_CATEGORIES = Object.keys(CATEGORY_BORDER)

const ROW_HEIGHT = 28

function eventRate(events: BrainEvent[]): number {
  const now = Date.now() / 1000
  const recent = events.filter((e) => now - e.ts < 5).length
  return Math.round(recent / 5)
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  const s = String(d.getSeconds()).padStart(2, '0')
  const ms = String(Math.floor((ts % 1) * 10))
  return `${h}:${m}:${s}.${ms}`
}

export function EventStream() {
  const [activeFilters, setActiveFilters] = createSignal<Set<string>>(new Set(ALL_CATEGORIES))
  const [autoScroll, setAutoScroll] = createSignal(true)
  let scrollRef: HTMLDivElement | undefined

  const filteredEvents = createMemo(() =>
    brainState.events.filter((e) => activeFilters().has(e.cat))
  )

  const evtRate = createMemo(() => eventRate(brainState.events))

  const virtualizer = createVirtualizer({
    get count() { return filteredEvents().length },
    getScrollElement: () => scrollRef ?? null,
    estimateSize: () => ROW_HEIGHT,
    overscan: 20,
  })

  // Auto-scroll to bottom when new events arrive
  createEffect(() => {
    const len = filteredEvents().length
    void len
    if (autoScroll() && scrollRef && len > 0) {
      requestAnimationFrame(() => {
        virtualizer.scrollToIndex(len - 1, { align: 'end' })
      })
    }
  })

  const toggleFilter = (cat: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  return (
    <div class="flex flex-col h-full">
      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          'align-items': 'center',
          'justify-content': 'space-between',
          padding: '0 12px',
          height: '28px',
          'min-height': '28px',
          background: 'var(--color-surface-raised)',
          'border-bottom': '1px solid var(--color-border)',
          'flex-shrink': '0',
        }}
      >
        {/* Left: REC indicator */}
        <div style={{ display: 'flex', 'align-items': 'center', gap: '6px' }}>
          <Show
            when={brainState.wsConnected}
            fallback={
              <>
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    'border-radius': '50%',
                    background: 'var(--color-threshold-red)',
                    display: 'inline-block',
                    'flex-shrink': '0',
                  }}
                  aria-hidden="true"
                />
                <span
                  style={{
                    'font-family': 'var(--font-mono)',
                    'font-size': '10px',
                    'letter-spacing': '0.08em',
                    color: 'var(--color-threshold-red)',
                  }}
                >
                  NO SIG
                </span>
              </>
            }
          >
            <span
              class="animate-rec-blink"
              style={{
                width: '6px',
                height: '6px',
                'border-radius': '50%',
                background: 'var(--color-phosphor-green)',
                display: 'inline-block',
                'flex-shrink': '0',
              }}
              aria-hidden="true"
            />
            <span
              style={{
                'font-family': 'var(--font-mono)',
                'font-size': '10px',
                'letter-spacing': '0.08em',
                color: 'var(--color-phosphor-green)',
              }}
            >
              REC
            </span>
          </Show>
          <span
            style={{
              'font-family': 'var(--font-mono)',
              'font-size': '10px',
              'letter-spacing': '0.06em',
              color: 'var(--color-readout-dim)',
              'margin-left': '4px',
            }}
          >
            BRAIN EVENT STREAM
          </span>
        </div>

        {/* Right: event count + rate */}
        <div
          style={{
            'font-family': 'var(--font-mono)',
            'font-size': '10px',
            color: 'var(--color-readout-dim)',
            'font-variant-numeric': 'tabular-nums',
            display: 'flex',
            gap: '8px',
            'align-items': 'center',
          }}
        >
          <span>{filteredEvents().length} EVT</span>
          <span style={{ color: 'var(--color-phosphor-green)' }}>{evtRate()} evt/s</span>
        </div>
      </div>

      {/* Filter bank */}
      <div
        class="scrollbar-hide"
        style={{
          display: 'flex',
          'align-items': 'center',
          gap: '0',
          padding: '4px 8px',
          'border-bottom': '1px solid var(--color-border)',
          background: 'var(--color-surface)',
          'flex-shrink': '0',
          'overflow-x': 'auto',
        }}
      >
        <span
          style={{
            'font-family': 'var(--font-mono)',
            'font-size': '9px',
            'letter-spacing': '0.06em',
            color: 'var(--color-readout-dim)',
            'margin-right': '6px',
            'text-transform': 'uppercase',
            'flex-shrink': '0',
          }}
        >
          CH:
        </span>
        <For each={ALL_CATEGORIES}>
          {(cat) => {
            const isActive = () => activeFilters().has(cat)
            const catColor = CATEGORY_TEXT[cat] ?? 'var(--color-readout-dim)'
            const borderColor = CATEGORY_BORDER[cat] ?? 'var(--color-readout-dim)'
            return (
              <button
                onClick={() => toggleFilter(cat)}
                aria-pressed={isActive()}
                style={{
                  'font-family': 'var(--font-mono)',
                  'font-size': '9px',
                  'letter-spacing': '0.06em',
                  'text-transform': 'uppercase',
                  padding: '2px 6px',
                  margin: '0 1px',
                  'border-radius': '2px',
                  cursor: 'pointer',
                  border: `1px solid ${borderColor}`,
                  background: isActive() ? `color-mix(in oklch, ${borderColor} 15%, transparent)` : 'transparent',
                  color: isActive() ? catColor : 'var(--color-readout-dim)',
                  opacity: isActive() ? 1 : 0.45,
                  'border-left': `2px solid ${borderColor}`,
                  'text-decoration': isActive() ? 'none' : 'line-through',
                  transition: 'opacity 80ms ease-out, background-color 80ms ease-out',
                }}
              >
                {cat}
              </button>
            )
          }}
        </For>
        {/* TAIL/HOLD toggle */}
        <button
          onClick={() => setAutoScroll(!autoScroll())}
          style={{
            'font-family': 'var(--font-mono)',
            'font-size': '9px',
            'letter-spacing': '0.06em',
            padding: '2px 6px',
            'margin-left': '8px',
            'border-radius': '2px',
            border: '1px solid var(--color-border)',
            background: autoScroll() ? 'oklch(0.68 0.14 155 / 0.12)' : 'transparent',
            color: autoScroll() ? 'var(--color-phosphor-green)' : 'var(--color-readout-dim)',
            cursor: 'pointer',
            'flex-shrink': '0',
          }}
        >
          {autoScroll() ? 'TAIL' : 'HOLD'}
        </button>
      </div>

      {/* Virtualized event list */}
      <div
        ref={scrollRef}
        class="flex-1 overflow-y-auto scan-overlay"
        style={{
          background: 'var(--color-surface)',
          position: 'relative',
          contain: 'strict',
        }}
        aria-live="polite"
        aria-label="Brain event feed"
      >
        <Show
          when={filteredEvents().length > 0}
          fallback={
            <div
              style={{
                display: 'flex',
                'flex-direction': 'column',
                'align-items': 'center',
                'justify-content': 'center',
                height: '100%',
                gap: '12px',
              }}
            >
              <svg
                width="40"
                height="40"
                viewBox="0 0 40 40"
                aria-hidden="true"
                style={{ opacity: '0.3' }}
              >
                <line x1="20" y1="0" x2="20" y2="40" stroke="var(--color-phosphor-green)" stroke-width="1" />
                <line x1="0" y1="20" x2="40" y2="20" stroke="var(--color-phosphor-green)" stroke-width="1" />
                <circle cx="20" cy="20" r="6" fill="none" stroke="var(--color-phosphor-green)" stroke-width="1" />
                <circle cx="20" cy="20" r="1.5" fill="var(--color-phosphor-green)" />
              </svg>
              <span
                style={{
                  'font-family': 'var(--font-mono)',
                  'font-size': '11px',
                  color: 'var(--color-readout-dim)',
                  'letter-spacing': '0.04em',
                }}
              >
                {'> awaiting signal_'}
                <span class="animate-cursor-blink" aria-hidden="true">|</span>
              </span>
            </div>
          }
        >
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            <For each={virtualizer.getVirtualItems()}>
              {(vRow) => {
                const event = () => filteredEvents()[vRow.index]
                return (
                  <div
                    style={{
                      position: 'absolute',
                      top: '0',
                      left: '0',
                      width: '100%',
                      height: `${vRow.size}px`,
                      transform: `translateY(${vRow.start}px)`,
                    }}
                  >
                    <EventRow event={event()} />
                  </div>
                )
              }}
            </For>
          </div>

          {/* Live-tail indicator */}
          <Show when={autoScroll()}>
            <div
              aria-hidden="true"
              style={{
                position: 'sticky',
                bottom: '0',
                height: '1px',
                background: 'var(--color-accent)',
                opacity: '0.4',
                'flex-shrink': '0',
              }}
            />
          </Show>
        </Show>
      </div>
    </div>
  )
}

function EventRow(props: { event: BrainEvent }) {
  const timeStr = () => formatTime(props.event.ts)
  const borderColor = () => CATEGORY_BORDER[props.event.cat] ?? 'var(--color-readout-dim)'
  const textColor = () => CATEGORY_TEXT[props.event.cat] ?? 'var(--color-readout-dim)'
  const catLabel = () => props.event.cat.toUpperCase().slice(0, 5).padEnd(5, '\u00A0')
  const dataStr = () => JSON.stringify(props.event.data).slice(0, 120)

  return (
    <div
      class="animate-ticker-step"
      style={{
        display: 'flex',
        'align-items': 'center',
        gap: '0.5rem',
        padding: '3px 12px 3px 8px',
        'border-left': `2px solid ${borderColor()}`,
        'border-bottom': '1px solid oklch(0.24 0.015 185 / 0.5)',
        height: `${ROW_HEIGHT}px`,
        'box-sizing': 'border-box',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'var(--color-surface-hover)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent'
      }}
    >
      {/* Timestamp */}
      <span
        style={{
          'font-family': 'var(--font-mono)',
          'font-size': '11px',
          color: 'var(--color-phosphor-green)',
          width: '76px',
          'flex-shrink': '0',
          'font-variant-numeric': 'tabular-nums',
        }}
      >
        {timeStr()}
      </span>

      {/* Category badge */}
      <span
        style={{
          'font-family': 'var(--font-mono)',
          'font-size': '10px',
          'letter-spacing': '0.06em',
          color: textColor(),
          border: `1px solid ${borderColor()}`,
          padding: '0 3px',
          'border-radius': '2px',
          width: '48px',
          'flex-shrink': '0',
          display: 'inline-block',
          'text-align': 'center',
          'line-height': '16px',
        }}
      >
        {catLabel()}
      </span>

      {/* Event kind */}
      <span
        style={{
          'font-family': 'var(--font-mono)',
          'font-size': '11px',
          color: 'var(--color-text-secondary)',
          width: '96px',
          'flex-shrink': '0',
          overflow: 'hidden',
          'text-overflow': 'ellipsis',
          'white-space': 'nowrap',
        }}
      >
        {props.event.kind}
      </span>

      {/* Data preview */}
      <span
        style={{
          'font-family': 'var(--font-mono)',
          'font-size': '11px',
          color: 'var(--color-readout-dim)',
          flex: '1',
          overflow: 'hidden',
          'white-space': 'nowrap',
          'text-overflow': 'ellipsis',
        }}
      >
        {dataStr()}
      </span>
    </div>
  )
}
