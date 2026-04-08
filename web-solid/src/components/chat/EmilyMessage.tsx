import { createSignal, createMemo, Show, For } from 'solid-js'
import {
  Copy, Check, ThumbsUp, ThumbsDown, RotateCcw,
  Brain, Volume2, Square, Sparkles, ChevronDown, ChevronRight, Globe,
} from 'lucide-solid'
import { MarkdownRenderer } from '../markdown/MarkdownRenderer'
import { rateMessage } from '../../stores/chat'
import { formatCost, formatLatency } from '../../lib/cost'
import { PROVIDER_COLORS } from '../../api/types'
import { API_BASE } from '../../lib/env'
import type { Message } from '../../api/types'

interface Props {
  message?: Message
  streaming?: boolean
  streamText?: string
  streamThinking?: string
  model?: string
  provider?: string
  searchSources?: Array<{ title: string; url: string }>
}

export function EmilyMessage(props: Props) {
  const [copied, setCopied] = createSignal(false)
  const [speaking, setSpeaking] = createSignal(false)
  const [thinkingCollapsed, setThinkingCollapsed] = createSignal(false)
  let audioRef: HTMLAudioElement | null = null

  const content = createMemo(() =>
    props.streaming ? (props.streamText ?? '') : (props.message?.content ?? ''),
  )
  const thinking = createMemo(() =>
    props.streaming ? (props.streamThinking ?? '') : (props.message?.thinking_content ?? ''),
  )
  const displayModel = createMemo(() => props.model || props.message?.model || '')
  const displayProvider = createMemo(() => props.provider || props.message?.provider || '')

  const handleCopy = () => {
    navigator.clipboard.writeText(content())
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleSpeak = async () => {
    if (speaking()) {
      audioRef?.pause()
      if (audioRef) audioRef.currentTime = 0
      setSpeaking(false)
      return
    }
    const text = content().trim()
    if (!text) return

    setSpeaking(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/tts/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`TTS failed: ${res.status}`)

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef = audio
      audio.onended = () => {
        setSpeaking(false)
        URL.revokeObjectURL(url)
      }
      audio.onerror = () => {
        setSpeaking(false)
        URL.revokeObjectURL(url)
      }
      await audio.play()
    } catch {
      setSpeaking(false)
    }
  }

  return (
    <div class="flex group gap-2.5 items-start">
      {/* Emily avatar */}
      <div
        class="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{
          background: 'oklch(0.72 0.17 162 / 0.12)',
          border: '1px solid oklch(0.72 0.17 162 / 0.28)',
        }}
      >
        <Sparkles size={14} style={{ color: 'oklch(0.72 0.17 162)' }} />
      </div>

      <div class="max-w-[82%] min-w-0 space-y-1.5">
        {/* Name label */}
        <span
          style={{
            'font-size': 'var(--text-small)',
            'font-weight': '600',
            'font-family': 'var(--font-display)',
            color: 'oklch(0.72 0.17 162)',
          }}
        >
          Emily
        </span>

        <Show when={thinking()}>
          <div
            class="rounded-xl overflow-hidden"
            style={{
              border: '1px solid oklch(0.32 0.05 200)',
              background: 'oklch(0.19 0.025 200)',
            }}
          >
            <button
              onClick={() => !props.streaming && setThinkingCollapsed(!thinkingCollapsed())}
              class="w-full flex items-center gap-2 px-3 py-2 transition-colors"
              style={{
                'font-size': 'var(--text-small)',
                color: 'oklch(0.72 0.17 162)',
                'font-family': 'var(--font-body)',
                'font-weight': '500',
              }}
            >
              <Show when={!props.streaming}>
                <Show when={thinkingCollapsed()} fallback={<ChevronDown size={12} class="flex-shrink-0" />}>
                  <ChevronRight size={12} class="flex-shrink-0" />
                </Show>
              </Show>
              <Brain size={14} class="flex-shrink-0" />
              <span>Thinking</span>
              <span class="font-normal ml-1" style={{ color: 'oklch(0.50 0.04 185)' }}>
                ~{Math.round(thinking().length / 4).toLocaleString()} tokens
              </span>
              <Show when={props.streaming}>
                <span class="flex items-center gap-1.5 ml-auto">
                  <span
                    class="w-1.5 h-1.5 rounded-full animate-pulse"
                    style={{ background: 'oklch(0.72 0.17 162)' }}
                  />
                  <span style={{ 'font-size': '0.625rem', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-mono)' }}>
                    live
                  </span>
                </span>
              </Show>
            </button>
            <Show when={!thinkingCollapsed()}>
              <div class="px-3 pb-3" style={{ 'border-top': '1px solid oklch(0.32 0.05 200 / 0.5)' }}>
                <div
                  class="leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto mt-2"
                  style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}
                >
                  {thinking()}
                  <Show when={props.streaming}>
                    <span
                      class="inline-block w-1 h-3 animate-pulse ml-0.5 -mb-0.5 rounded-sm"
                      style={{ background: 'oklch(0.72 0.17 162)' }}
                    />
                  </Show>
                </div>
              </div>
            </Show>
          </div>
        </Show>

        <div
          class="rounded-2xl rounded-tl-sm px-4 py-3"
          style={{
            background: 'oklch(0.20 0.02 185)',
            border: '1px solid oklch(0.30 0.03 185 / 0.5)',
          }}
        >
          <Show
            when={content()}
            fallback={
              <Show when={props.streaming}>
                <div
                  class="flex items-center gap-2"
                  style={{ color: 'oklch(0.50 0.04 185)', 'font-size': 'var(--text-body)', 'font-family': 'var(--font-body)' }}
                >
                  <span class="flex gap-1">
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'oklch(0.72 0.17 162)', 'animation-delay': '0ms' }} />
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'oklch(0.72 0.17 162)', 'animation-delay': '150ms' }} />
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'oklch(0.72 0.17 162)', 'animation-delay': '300ms' }} />
                  </span>
                  Emily is thinking...
                </div>
              </Show>
            }
          >
            <MarkdownRenderer content={content()} />
          </Show>
        </div>

        {/* Search sources */}
        <Show when={props.searchSources && props.searchSources.length > 0}>
          <div class="flex flex-wrap gap-1.5 px-1">
            <For each={props.searchSources}>
              {(s) => (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="flex items-center gap-1 px-2 py-0.5 rounded-full transition-colors"
                  style={{
                    'font-size': 'var(--text-small)',
                    color: 'oklch(0.65 0.03 185)',
                    background: 'oklch(0.18 0.02 185)',
                    border: '1px solid oklch(0.30 0.03 185)',
                    'font-family': 'var(--font-body)',
                  }}
                >
                  <Globe size={12} />
                  <span class="max-w-[150px] truncate">{s.title}</span>
                </a>
              )}
            </For>
          </div>
        </Show>

        {/* Action bar */}
        <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity pl-1">
          <Show when={displayModel()}>
            <div
              class="flex items-center gap-1.5 mr-2"
              style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-mono)' }}
            >
              <span
                class="w-1.5 h-1.5 rounded-full"
                style={{ 'background-color': PROVIDER_COLORS[displayProvider()] || 'oklch(0.50 0.04 185)' }}
              />
              <span>{displayModel()}</span>
            </div>
          </Show>

          <Show when={props.message && !props.streaming}>
            <Show when={props.message!.latency_ms != null}>
              <span
                class="mr-1"
                style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-mono)' }}
              >
                {formatLatency(props.message!.latency_ms!)}
              </span>
            </Show>
            <Show when={props.message!.cost_usd > 0}>
              <span
                class="mr-1"
                style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.72 0.15 145)', 'font-family': 'var(--font-mono)' }}
              >
                {formatCost(props.message!.cost_usd)}
              </span>
            </Show>
          </Show>

          <div class="flex items-center gap-0.5 ml-auto">
            <Show when={content() && !props.streaming}>
              <button
                onClick={handleSpeak}
                class="p-1 rounded-md transition-colors"
                style={{
                  color: speaking() ? 'oklch(0.72 0.17 162)' : 'oklch(0.50 0.04 185)',
                  background: speaking() ? 'oklch(0.72 0.17 162 / 0.10)' : '',
                }}
                title={speaking() ? 'Stop reading' : 'Read aloud'}
              >
                <Show when={speaking()} fallback={<Volume2 size={14} />}>
                  <Square size={14} />
                </Show>
              </button>
            </Show>

            <button
              onClick={handleCopy}
              class="p-1 rounded-md transition-colors"
              style={{ color: 'oklch(0.50 0.04 185)' }}
              title="Copy"
            >
              <Show when={copied()} fallback={<Copy size={14} />}>
                <Check size={14} style={{ color: 'oklch(0.72 0.15 145)' }} />
              </Show>
            </button>

            <Show when={props.message && !props.streaming}>
              <button
                onClick={() => rateMessage(props.message!.id, props.message!.rating === 1 ? 0 : 1)}
                class="p-1 rounded-md transition-colors"
                style={{
                  color: props.message!.rating === 1 ? 'oklch(0.72 0.15 145)' : 'oklch(0.50 0.04 185)',
                  background: props.message!.rating === 1 ? 'oklch(0.72 0.15 145 / 0.10)' : '',
                }}
                title="Good response"
              >
                <ThumbsUp size={14} />
              </button>
              <button
                onClick={() => rateMessage(props.message!.id, props.message!.rating === -1 ? 0 : -1)}
                class="p-1 rounded-md transition-colors"
                style={{
                  color: props.message!.rating === -1 ? 'oklch(0.65 0.20 25)' : 'oklch(0.50 0.04 185)',
                  background: props.message!.rating === -1 ? 'oklch(0.65 0.20 25 / 0.10)' : '',
                }}
                title="Bad response"
              >
                <ThumbsDown size={14} />
              </button>
              <button
                class="p-1 rounded-md transition-colors"
                style={{ color: 'oklch(0.50 0.04 185)' }}
                title="Retry"
              >
                <RotateCcw size={14} />
              </button>
            </Show>
          </div>
        </div>
      </div>
    </div>
  )
}
