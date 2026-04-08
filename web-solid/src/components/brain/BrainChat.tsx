import { createSignal, createEffect, Show, For } from 'solid-js'
import { Send } from 'lucide-solid'
import { API_BASE, authHeaders } from '../../lib/env'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

function StreamingIndicator() {
  return (
    <div
      aria-label="Emily is responding"
      style={{
        display: 'flex',
        'align-items': 'flex-end',
        gap: '3px',
        height: '14px',
        'margin-left': '24px',
        'margin-top': '8px',
      }}
    >
      <For each={[0, 1, 2]}>
        {(i) => (
          <span
            aria-hidden="true"
            style={{
              width: '3px',
              height: '10px',
              background: 'var(--color-phosphor-green)',
              'border-radius': '1px',
              display: 'inline-block',
              animation: `wave-bar 0.9s ease-in-out ${i * 0.18}s infinite`,
              'transform-origin': 'bottom',
            }}
          />
        )}
      </For>
    </div>
  )
}

export function BrainChat() {
  const [messages, setMessages] = createSignal<ChatMessage[]>([])
  const [input, setInput] = createSignal('')
  const [streaming, setStreaming] = createSignal(false)
  let scrollRef: HTMLDivElement | undefined
  let inputRef: HTMLInputElement | undefined

  createEffect(() => {
    const _ = messages()
    if (scrollRef) {
      scrollRef.scrollTop = scrollRef.scrollHeight
    }
  })

  const sendMessage = async () => {
    const text = input().trim()
    if (!text || streaming()) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setStreaming(true)

    try {
      const res = await fetch(`${API_BASE}/api/v1/chat`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ message: text, stream: true }),
      })

      if (!res.ok || !res.body) {
        setMessages((prev) => [...prev, { role: 'assistant', content: '[Error: request failed]' }])
        setStreaming(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let assistantText = ''
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.text) {
                assistantText += data.text
                setMessages((prev) => {
                  const next = [...prev]
                  next[next.length - 1] = { role: 'assistant', content: assistantText }
                  return next
                })
              }
            } catch {
              if (line.slice(6).trim() && line.slice(6).trim() !== '[DONE]') {
                assistantText += line.slice(6)
                setMessages((prev) => {
                  const next = [...prev]
                  next[next.length - 1] = { role: 'assistant', content: assistantText }
                  return next
                })
              }
            }
          }
        }
      }
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: '[Error: connection failed]' }])
    } finally {
      setStreaming(false)
      setTimeout(() => inputRef?.focus(), 0)
    }
  }

  return (
    <div class="flex flex-col h-full">
      {/* Header */}
      <div
        style={{
          display: 'flex',
          'flex-direction': 'column',
          'justify-content': 'center',
          padding: '0 16px',
          height: '40px',
          'min-height': '40px',
          background: 'var(--color-surface-raised)',
          'border-bottom': '1px solid var(--color-border)',
          'flex-shrink': '0',
        }}
      >
        <span
          style={{
            'font-family': 'var(--font-mono)',
            'font-weight': '600',
            'font-size': '11px',
            'letter-spacing': '0.08em',
            color: 'var(--color-text-primary)',
            'text-transform': 'uppercase',
          }}
        >
          Query Terminal
        </span>
        <span
          style={{
            'font-family': 'var(--font-mono)',
            'font-size': '9px',
            'letter-spacing': '0.04em',
            color: 'var(--color-readout-dim)',
            'margin-top': '1px',
          }}
        >
          direct cortical interface
        </span>
      </div>

      {/* Message buffer */}
      <div
        ref={scrollRef}
        class="flex-1 overflow-y-auto"
        style={{ background: 'var(--color-surface)', padding: '16px 0' }}
        aria-live="polite"
        aria-label="Query terminal messages"
      >
        <Show
          when={messages().length > 0}
          fallback={
            <p
              style={{
                'font-family': 'var(--font-mono)',
                'font-size': '11px',
                color: 'var(--color-readout-dim)',
                'letter-spacing': '0.03em',
                padding: '0 20px',
                margin: '0',
                'line-height': '1.7',
              }}
            >
              No queries in buffer. Type to interrogate the neural substrate.
            </p>
          }
        >
          <For each={messages()}>
            {(msg, i) => {
              const isUser = msg.role === 'user'
              const isLastStreaming = () => streaming() && i() === messages().length - 1 && !isUser

              if (isUser) {
                return (
                  <div style={{ display: 'flex', 'justify-content': 'flex-end', padding: '4px 16px' }}>
                    <span
                      style={{
                        'font-family': 'var(--font-mono)',
                        'font-size': '12px',
                        color: 'var(--color-text-primary)',
                        'max-width': '75%',
                        'white-space': 'pre-wrap',
                        'word-break': 'break-word',
                      }}
                    >
                      <span
                        style={{ color: 'var(--color-accent)', 'margin-right': '6px', 'user-select': 'none' }}
                        aria-hidden="true"
                      >
                        &gt;
                      </span>
                      {msg.content}
                    </span>
                  </div>
                )
              }

              return (
                <div
                  style={{
                    padding: '8px 16px 8px 20px',
                    'border-top': '1px solid var(--color-accent)',
                    'margin-left': '0',
                    'margin-top': '4px',
                    'margin-bottom': '4px',
                  }}
                >
                  <Show when={isLastStreaming() && !msg.content} fallback={
                    <p
                      style={{
                        'font-family': 'var(--font-body)',
                        'font-size': '15px',
                        'line-height': '1.65',
                        color: 'var(--color-text-secondary)',
                        margin: '0',
                        'padding-left': '24px',
                        'white-space': 'pre-wrap',
                        'word-break': 'break-word',
                      }}
                    >
                      {msg.content}
                      <Show when={isLastStreaming()}>
                        <span
                          class="animate-cursor-blink"
                          style={{ color: 'var(--color-accent)', 'margin-left': '2px' }}
                          aria-hidden="true"
                        >
                          |
                        </span>
                      </Show>
                    </p>
                  }>
                    <StreamingIndicator />
                  </Show>
                </div>
              )
            }}
          </For>
        </Show>
      </div>

      {/* Input */}
      <div
        style={{
          display: 'flex',
          'align-items': 'center',
          padding: '10px 16px',
          'border-top': '1px solid var(--color-border)',
          background: 'var(--color-surface-raised)',
          gap: '8px',
          'flex-shrink': '0',
        }}
      >
        <label for="brain-chat-input" class="sr-only">Query Emily</label>
        <input
          id="brain-chat-input"
          ref={inputRef}
          type="text"
          value={input()}
          onInput={(e) => setInput(e.currentTarget.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="> query_"
          disabled={streaming()}
          autocomplete="off"
          spellcheck={false}
          style={{
            flex: '1',
            background: 'transparent',
            border: 'none',
            'border-bottom': '1px solid var(--color-border)',
            'border-radius': '0',
            outline: 'none',
            padding: '4px 0',
            'font-family': 'var(--font-mono)',
            'font-size': '13px',
            color: 'var(--color-text-primary)',
            'caret-color': 'var(--color-accent)',
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderBottomColor = 'var(--color-accent)'
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderBottomColor = 'var(--color-border)'
          }}
        />
        <button
          onClick={() => sendMessage()}
          disabled={streaming() || !input().trim()}
          aria-label="Send query"
          style={{
            display: 'flex',
            'align-items': 'center',
            'justify-content': 'center',
            width: '28px',
            height: '28px',
            border: '1px solid var(--color-border)',
            'border-radius': '2px',
            background: 'transparent',
            color: input().trim() && !streaming() ? 'var(--color-accent)' : 'var(--color-readout-dim)',
            cursor: input().trim() && !streaming() ? 'pointer' : 'not-allowed',
            opacity: streaming() ? '0.4' : '1',
            transition: 'color 80ms ease-out, border-color 80ms ease-out',
            'flex-shrink': '0',
          }}
          onMouseEnter={(e) => {
            if (!streaming() && input().trim()) {
              e.currentTarget.style.borderColor = 'var(--color-accent)'
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--color-border)'
          }}
        >
          <Send size={12} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
