import { createEffect, For, Show } from 'solid-js'
import { Globe } from 'lucide-solid'
import { chatState } from '../../stores/chat'
import { UserMessage } from './UserMessage'
import { EmilyMessage } from './EmilyMessage'

export function MessageList() {
  let bottomEl: HTMLDivElement | undefined

  createEffect(() => {
    // Track dependencies for auto-scroll
    const _len = chatState.messages.length
    const _text = chatState.streamingText
    const _search = chatState.searchStatus
    void _len
    void _text
    void _search
    bottomEl?.scrollIntoView({ behavior: 'smooth' })
  })

  return (
    <div class="flex-1 overflow-y-auto">
      <div class="max-w-4xl mx-auto px-4 py-6 space-y-6">
        <For each={chatState.messages}>
          {(msg) => (
            <Show when={msg.role === 'user'} fallback={
              <Show when={msg.role === 'assistant'}>
                <EmilyMessage message={msg} />
              </Show>
            }>
              <UserMessage message={msg} />
            </Show>
          )}
        </For>

        <Show when={chatState.isStreaming && chatState.searchStatus && chatState.searchStatus.status !== 'done'}>
          <div class="flex items-center gap-2 px-4 py-2 ml-9 text-xs" style={{ color: 'oklch(0.50 0.04 185)' }}>
            <Globe size={14} class="animate-pulse" style={{ color: 'oklch(0.72 0.17 162)' }} />
            <span>
              <Show when={chatState.searchStatus?.status === 'searching'}>
                Searching the web...
              </Show>
              <Show when={chatState.searchStatus?.status === 'found'}>
                Found {(chatState.searchStatus as { count?: number })?.count} results
              </Show>
              <Show when={chatState.searchStatus?.status === 'reading'}>
                Reading: <span style={{ color: 'oklch(0.65 0.03 185)' }}>
                  {(chatState.searchStatus as { title?: string })?.title}
                </span>
              </Show>
              <Show when={chatState.searchStatus?.status === 'error'}>
                <span style={{ color: 'oklch(0.65 0.20 25)' }}>
                  Search failed: {(chatState.searchStatus as { message?: string })?.message}
                </span>
              </Show>
            </span>
          </div>
        </Show>

        <Show when={chatState.isStreaming}>
          <EmilyMessage
            streaming
            streamText={chatState.streamingText}
            streamThinking={chatState.streamingThinking}
            model={chatState.streamMeta?.display || ''}
            provider={chatState.streamMeta?.provider || ''}
            searchSources={chatState.searchSources ?? undefined}
          />
        </Show>

        <div ref={bottomEl} />
      </div>
    </div>
  )
}
