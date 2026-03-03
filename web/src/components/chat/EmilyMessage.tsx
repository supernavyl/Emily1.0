import { useState, useRef, useCallback } from 'react'
import { API_BASE } from '../../lib/env'
import {
  Copy, Check, ThumbsUp, ThumbsDown, RotateCcw,
  Brain, Volume2, Square, Sparkles, ChevronDown, ChevronRight, Globe,
} from 'lucide-react'
import { MarkdownRenderer } from '../markdown/MarkdownRenderer'
import { useChatStore } from '../../stores/chat'
import { formatCost, formatLatency } from '../../lib/cost'
import { PROVIDER_COLORS } from '../../api/types'
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

export function EmilyMessage({ message, streaming, streamText, streamThinking, model, provider, searchSources }: Props) {
  const rateMessage = useChatStore((s) => s.rateMessage)
  const [copied, setCopied] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [thinkingCollapsed, setThinkingCollapsed] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const content = streaming ? streamText || '' : message?.content || ''
  const thinking = streaming ? streamThinking || '' : message?.thinking_content || ''
  const displayModel = model || message?.model || ''
  const displayProvider = provider || message?.provider || ''

  const handleCopy = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleSpeak = useCallback(async () => {
    if (speaking) {
      audioRef.current?.pause()
      if (audioRef.current) audioRef.current.currentTime = 0
      setSpeaking(false)
      return
    }
    if (!content.trim()) return

    setSpeaking(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/tts/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: content }),
      })
      if (!res.ok) throw new Error(`TTS failed: ${res.status}`)

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
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
  }, [content, speaking])

  return (
    <div className="flex group gap-2.5 items-start">
      {/* Emily avatar */}
      <div className="w-7 h-7 rounded-full bg-accent/15 border border-accent/30 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Sparkles className="w-3.5 h-3.5 text-accent" />
      </div>

      <div className="max-w-[82%] min-w-0 space-y-1.5">
        {/* Name label */}
        <span className="text-xs font-semibold text-accent">Emily</span>

        {thinking && (
          <div className="border border-thinking-border bg-thinking-bg rounded-xl overflow-hidden">
            <button
              onClick={() => !streaming && setThinkingCollapsed(!thinkingCollapsed)}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-phase-analyzing font-medium hover:bg-white/[0.02] transition-colors"
            >
              {!streaming && (thinkingCollapsed
                ? <ChevronRight className="w-3 h-3 flex-shrink-0" />
                : <ChevronDown className="w-3 h-3 flex-shrink-0" />
              )}
              <Brain className="w-3.5 h-3.5 flex-shrink-0" />
              <span>Thinking</span>
              <span className="text-text-muted font-normal ml-1">
                ~{Math.round(thinking.length / 4).toLocaleString()} tokens
              </span>
              {streaming && (
                <span className="flex items-center gap-1.5 ml-auto">
                  <span className="w-1.5 h-1.5 rounded-full bg-phase-analyzing animate-pulse" />
                  <span className="text-[10px] text-text-muted font-normal">live</span>
                </span>
              )}
            </button>
            {!thinkingCollapsed && (
              <div className="px-3 pb-3 border-t border-thinking-border/50">
                <div className="text-xs text-text-muted leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto mt-2">
                  {thinking}
                  {streaming && (
                    <span className="inline-block w-1 h-3 bg-phase-analyzing animate-pulse ml-0.5 -mb-0.5 rounded-sm" />
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="bg-emily-bubble rounded-2xl rounded-tl-md px-4 py-3 border border-border/50">
          {content ? (
            <MarkdownRenderer content={content} />
          ) : streaming ? (
            <div className="flex items-center gap-2 text-text-muted text-sm">
              <span className="flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
              Emily is thinking...
            </div>
          ) : null}
        </div>

        {/* Search sources */}
        {searchSources && searchSources.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1">
            {searchSources.map((s, i) => (
              <a
                key={i}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface border border-border text-xs text-text-secondary hover:text-accent hover:border-accent/30 transition-colors"
              >
                <Globe className="w-3 h-3" />
                <span className="max-w-[150px] truncate">{s.title}</span>
              </a>
            ))}
          </div>
        )}

        {/* Action bar */}
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity pl-1">
          {displayModel && (
            <div className="flex items-center gap-1.5 text-xs text-text-muted mr-2">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: PROVIDER_COLORS[displayProvider] || '#555' }}
              />
              <span>{displayModel}</span>
            </div>
          )}

          {message && !streaming && (
            <>
              {message.latency_ms != null && (
                <span className="text-xs text-text-muted mr-1">{formatLatency(message.latency_ms)}</span>
              )}
              {message.cost_usd > 0 && (
                <span className="text-xs text-cost-green mr-1">{formatCost(message.cost_usd)}</span>
              )}
            </>
          )}

          <div className="flex items-center gap-0.5 ml-auto">
            {content && !streaming && (
              <button
                onClick={handleSpeak}
                className={`p-1 rounded-md transition-colors ${speaking ? 'text-accent bg-accent/10' : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'}`}
                title={speaking ? 'Stop reading' : 'Read aloud'}
              >
                {speaking ? <Square className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
              </button>
            )}

            <button
              onClick={handleCopy}
              className="p-1 rounded-md text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
              title="Copy"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-cost-green" /> : <Copy className="w-3.5 h-3.5" />}
            </button>

            {message && !streaming && (
              <>
                <button
                  onClick={() => rateMessage(message.id, message.rating === 1 ? 0 : 1)}
                  className={`p-1 rounded-md transition-colors ${message.rating === 1 ? 'text-cost-green bg-cost-green/10' : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'}`}
                  title="Good response"
                >
                  <ThumbsUp className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => rateMessage(message.id, message.rating === -1 ? 0 : -1)}
                  className={`p-1 rounded-md transition-colors ${message.rating === -1 ? 'text-error-red bg-error-red/10' : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'}`}
                  title="Bad response"
                >
                  <ThumbsDown className="w-3.5 h-3.5" />
                </button>
                <button className="p-1 rounded-md text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors" title="Retry">
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
