import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, MessageSquare, Plus, Settings, Download, X } from 'lucide-react'
import { useUIStore } from '../../stores/ui'
import { useChatStore } from '../../stores/chat'
import { api } from '../../api/client'
import type { SearchResult } from '../../api/types'

const COMMANDS = [
  { icon: Plus, label: 'New Conversation', shortcut: 'Ctrl+N', action: 'new' },
  { icon: Download, label: 'Export', action: 'export' },
  { icon: Settings, label: 'Settings', action: 'settings' },
]

export function SearchOverlay() {
  const setSearchOpen = useUIStore((s) => s.setSearchOpen)
  const selectConversation = useChatStore((s) => s.selectConversation)
  const createConversation = useChatStore((s) => s.createConversation)

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSearchOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setSearchOpen])

  const doSearch = useCallback(async (q: string) => {
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
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => doSearch(query), 200)
    return () => clearTimeout(timer)
  }, [query, doSearch])

  const handleSelect = (conversationId: string) => {
    selectConversation(conversationId)
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
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      style={{ backgroundColor: 'rgba(10, 10, 15, 0.8)', backdropFilter: 'blur(4px)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setSearchOpen(false)
      }}
    >
      <div
        ref={overlayRef}
        className="w-[560px] bg-surface-raised border border-border rounded-2xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-4 duration-200"
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search className="w-5 h-5 text-text-muted flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations, type a command..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
          />
          <button
            onClick={() => setSearchOpen(false)}
            className="p-1 rounded text-text-muted hover:text-text-secondary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="max-h-80 overflow-y-auto">
          {query.length >= 2 && results.length > 0 && (
            <div className="py-2">
              <div className="px-4 py-1 text-xs font-semibold text-text-muted uppercase tracking-wider">
                Results
              </div>
              {results.map((r) => (
                <button
                  key={`${r.conversation_id}-${r.message_id}`}
                  onClick={() => handleSelect(r.conversation_id)}
                  className="w-full flex items-start gap-3 px-4 py-2.5 hover:bg-surface-hover transition-colors text-left"
                >
                  <MessageSquare className="w-4 h-4 text-text-muted mt-0.5 flex-shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-text-primary truncate">
                      {r.title}
                    </div>
                    <div
                      className="text-xs text-text-muted mt-0.5 line-clamp-2"
                      dangerouslySetInnerHTML={{
                        __html: r.excerpt
                          .replace(/«/g, '<mark class="bg-warning-amber/30 text-warning-amber rounded px-0.5">')
                          .replace(/»/g, '</mark>'),
                      }}
                    />
                  </div>
                </button>
              ))}
            </div>
          )}

          {query.length >= 2 && results.length === 0 && !loading && (
            <div className="px-4 py-8 text-center text-text-muted text-sm">
              No results found
            </div>
          )}

          {query.length < 2 && (
            <div className="py-2">
              <div className="px-4 py-1 text-xs font-semibold text-text-muted uppercase tracking-wider">
                Commands
              </div>
              {COMMANDS.map(({ icon: Icon, label, shortcut, action }) => (
                <button
                  key={action}
                  onClick={() => handleCommand(action)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover transition-colors text-left"
                >
                  <Icon className="w-4 h-4 text-text-muted" />
                  <span className="flex-1 text-sm text-text-secondary">{label}</span>
                  {shortcut && (
                    <kbd className="text-xs text-text-muted bg-surface px-1.5 py-0.5 rounded border border-border">
                      {shortcut}
                    </kbd>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
