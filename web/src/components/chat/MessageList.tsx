import { useEffect, useRef } from 'react'
import { Globe } from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import { UserMessage } from './UserMessage'
import { EmilyMessage } from './EmilyMessage'

export function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const streamingText = useChatStore((s) => s.streamingText)
  const streamingThinking = useChatStore((s) => s.streamingThinking)
  const streamMeta = useChatStore((s) => s.streamMeta)
  const searchStatus = useChatStore((s) => s.searchStatus)
  const searchSources = useChatStore((s) => s.searchSources)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streamingText, searchStatus])

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {messages.map((msg) =>
          msg.role === 'user' ? (
            <UserMessage key={msg.id} message={msg} />
          ) : msg.role === 'assistant' ? (
            <EmilyMessage key={msg.id} message={msg} />
          ) : null,
        )}

        {isStreaming && searchStatus && searchStatus.status !== 'done' && (
          <div className="flex items-center gap-2 px-4 py-2 ml-9 text-xs text-text-muted">
            <Globe className="w-3.5 h-3.5 text-accent animate-pulse" />
            <span>
              {searchStatus.status === 'searching' && 'Searching the web...'}
              {searchStatus.status === 'found' && `Found ${searchStatus.count} results`}
              {searchStatus.status === 'reading' && (
                <>Reading: <span className="text-text-secondary">{searchStatus.title}</span></>
              )}
              {searchStatus.status === 'error' && (
                <span className="text-error-red">Search failed: {searchStatus.message}</span>
              )}
            </span>
          </div>
        )}

        {isStreaming && (
          <EmilyMessage
            streaming
            streamText={streamingText}
            streamThinking={streamingThinking}
            model={streamMeta?.display || ''}
            provider={streamMeta?.provider || ''}
            searchSources={searchSources ?? undefined}
          />
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
