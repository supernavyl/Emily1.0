import { createSignal, createEffect, onMount, onCleanup, For, Show } from 'solid-js'
import { Search, MessageSquare, Plus, Settings, Download, X } from 'lucide-solid'
import { setSearchOpen } from '../../stores/ui'
import { selectConversation, createConversation } from '../../stores/chat'
import { api } from '../../api/client'
import type { SearchResult } from '../../api/types'
import type { Component } from 'solid-js'

const COMMANDS: { icon: Component<{ class?: string }>; label: string; shortcut?: string; action: string }[] = [
  { icon: Plus, label: 'New Conversation', shortcut: 'Ctrl+N', action: 'new' },
  { icon: Download, label: 'Export', action: 'export' },
  { icon: Settings, label: 'Settings', action: 'settings' },
]

export function SearchOverlay() {
  const [query, setQuery] = createSignal('')
  const [results, setResults] = createSignal<SearchResult[]>([])
  const [loading, setLoading] = createSignal(false)
  let inputRef: HTMLInputElement | undefined

  onMount(() => {
    inputRef?.focus()
  })

  onMount(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSearchOpen(false)
    }
    window.addEventListener('keydown', handler)
    onCleanup(() => window.removeEventListener('keydown', handler))
  })

  const doSearch = async (q: string) => {
    if (q.length < 2) {
      setResults([])
      return
    }
    setLoading(true)
    try {
      const { results: r } = await api.search(q)
      setResults(r)
    } catch {
      setResults([])
    }
    setLoading(false)
  }

  createEffect(() => {
    const q = query()
    const timer = setTimeout(() => void doSearch(q), 200)
    onCleanup(() => clearTimeout(timer))
  })

  const handleSelect = (conversationId: string) => {
    void selectConversation(conversationId)
    setSearchOpen(false)
  }

  const handleCommand = async (action: string) => {
    switch (action) {
      case 'new':
        await createConversation()
        break
    }
    setSearchOpen(false)
  }

  return (
    <div
      class="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] backdrop-blur-sm"
      style={{ 'background-color': 'oklch(0.10 0.015 185 / 0.8)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setSearchOpen(false)
      }}
    >
      <div class="w-[560px] bg-surface-raised border border-border rounded-2xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-4 duration-200">
        <div class="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search class="w-5 h-5 text-text-muted flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query()}
            onInput={(e) => setQuery(e.currentTarget.value)}
            placeholder="Search conversations, type a command..."
            class="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
          />
          <button
            onClick={() => setSearchOpen(false)}
            class="p-1 rounded text-text-muted hover:text-text-secondary transition-colors"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="max-h-80 overflow-y-auto">
          <Show when={query().length >= 2 && results().length > 0}>
            <div class="py-2">
              <div class="px-4 py-1 text-xs font-semibold text-text-muted uppercase tracking-wider">
                Results
              </div>
              <For each={results()}>{(r) => (
                <button
                  onClick={() => handleSelect(r.conversation_id)}
                  class="w-full flex items-start gap-3 px-4 py-2.5 hover:bg-surface-hover transition-colors text-left"
                >
                  <MessageSquare class="w-4 h-4 text-text-muted mt-0.5 flex-shrink-0" />
                  <div class="min-w-0">
                    <div class="text-sm font-medium text-text-primary truncate">
                      {r.title}
                    </div>
                    <div
                      class="text-xs text-text-muted mt-0.5 line-clamp-2"
                      innerHTML={r.excerpt
                        .replace(/\u00AB/g, '<mark class="bg-warning-amber/30 text-warning-amber rounded px-0.5">')
                        .replace(/\u00BB/g, '</mark>')}
                    />
                  </div>
                </button>
              )}</For>
            </div>
          </Show>

          <Show when={query().length >= 2 && results().length === 0 && !loading()}>
            <div class="px-4 py-8 text-center text-text-muted text-sm">
              No results found
            </div>
          </Show>

          <Show when={query().length < 2}>
            <div class="py-2">
              <div class="px-4 py-1 text-xs font-semibold text-text-muted uppercase tracking-wider">
                Commands
              </div>
              <For each={COMMANDS}>{(cmd) => {
                const Icon = cmd.icon
                return (
                  <button
                    onClick={() => void handleCommand(cmd.action)}
                    class="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover transition-colors text-left"
                  >
                    <Icon class="w-4 h-4 text-text-muted" />
                    <span class="flex-1 text-sm text-text-secondary">{cmd.label}</span>
                    <Show when={cmd.shortcut}>
                      <kbd class="text-xs text-text-muted bg-surface px-1.5 py-0.5 rounded border border-border">
                        {cmd.shortcut}
                      </kbd>
                    </Show>
                  </button>
                )
              }}</For>
            </div>
          </Show>
        </div>
      </div>
    </div>
  )
}
