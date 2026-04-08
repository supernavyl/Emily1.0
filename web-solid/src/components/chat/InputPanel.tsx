import { createSignal, createEffect, onCleanup, Show, For, createMemo } from 'solid-js'
import { Send, Square, Paperclip, Globe, Zap, X, Cpu, Layers } from 'lucide-solid'
import {
  chatState, sendMessage, stopGeneration, createConversation,
} from '../../stores/chat'
import {
  modelsState, setActiveSkill, setActiveMode,
} from '../../stores/models'
import { PROVIDER_COLORS } from '../../api/types'
import { getSkillIcon } from '../../lib/skill-icons'
import { getModeTheme } from '../../lib/mode-themes'

const SKILL_HINTS: Array<{ skill: string; name: string; pattern: RegExp }> = [
  {
    skill: 'translate', name: 'Translate',
    pattern: /\b(translate|in french|in spanish|in german|in japanese|in chinese|in arabic|in portuguese|in russian|in italian|en fran[cç]ais|auf deutsch|en espa[nñ]ol)\b/i,
  },
  {
    skill: 'code', name: 'Code',
    pattern: /\b(function|class|debug|refactor|implement|algorithm|syntax error|runtime error|stack trace|python|javascript|typescript|rust|java|golang|sql|html|css|react|vue|fastapi|flask|django|api route|compile)\b/i,
  },
  {
    skill: 'singing', name: 'Singing',
    pattern: /\bwrite (?:a )?(?:song|lyrics|rap|poem)\b|\bcompose (?:a )?(?:melody|song|music)\b/i,
  },
  {
    skill: 'research', name: 'Research',
    pattern: /\b(find sources|look up|latest (?:news|research|studies)|cite|peer.?reviewed|evidence for|statistics on|data on)\b/i,
  },
  {
    skill: 'writing', name: 'Writing',
    pattern: /\bwrite (?:a|an|me|my)\b|\b(draft|essay|blog post|article|cover letter|rewrite|proofread|improve (?:my|this) (?:writing|text|paragraph))\b/i,
  },
  {
    skill: 'brainstorm', name: 'Brainstorm',
    pattern: /\b(brainstorm|give me \d* ?ideas|list \d* ?(?:ways|options|ideas)|different approaches|alternatives to)\b/i,
  },
  {
    skill: 'deep_think', name: 'Deep Think',
    pattern: /\b(explain (?:in detail|deeply|thoroughly|step.?by.?step)|what causes|break.?down|implications of|evaluate the|analyze|analyse)\b/i,
  },
]

function detectSkill(text: string): { skill: string; name: string } | null {
  if (text.length < 12) return null
  for (const hint of SKILL_HINTS) {
    if (hint.pattern.test(text)) return hint
  }
  return null
}

export function InputPanel() {
  const [text, setText] = createSignal('')
  const [webSearch, setWebSearch] = createSignal(false)
  const [attachments, setAttachments] = createSignal<File[]>([])
  const [suggestedSkill, setSuggestedSkill] = createSignal<{ skill: string; name: string } | null>(null)
  const [showModeDropdown, setShowModeDropdown] = createSignal(false)
  let textareaRef: HTMLTextAreaElement | undefined
  let fileInputRef: HTMLInputElement | undefined

  const adjustHeight = () => {
    const el = textareaRef
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }

  createEffect(() => {
    void text()
    adjustHeight()
  })

  // Close mode dropdown on click outside
  createEffect(() => {
    if (!showModeDropdown()) return
    const handler = () => setShowModeDropdown(false)
    const timer = setTimeout(() => document.addEventListener('click', handler), 0)
    onCleanup(() => {
      clearTimeout(timer)
      document.removeEventListener('click', handler)
    })
  })

  // Debounced skill detection
  createEffect(() => {
    const currentText = text()
    const timer = setTimeout(() => {
      const detected = detectSkill(currentText)
      if (detected && detected.skill !== modelsState.activeSkill) {
        setSuggestedSkill(detected)
      } else {
        setSuggestedSkill(null)
      }
    }, 400)
    onCleanup(() => clearTimeout(timer))
  })

  const handleSend = async () => {
    const trimmed = text().trim()
    if (!trimmed || chatState.isStreaming) return

    if (!chatState.activeId) {
      await createConversation(trimmed.slice(0, 50))
    }

    sendMessage(trimmed, modelsState.activeModel, modelsState.activeSkill, modelsState.activeMode, webSearch())
    setText('')
    setSuggestedSkill(null)
    textareaRef?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const handleAttach = () => fileInputRef?.click()

  const handleFiles = (e: Event) => {
    const target = e.target as HTMLInputElement
    const files = Array.from(target.files || [])
    const valid = files.filter((f) => f.size <= 10 * 1024 * 1024)
    setAttachments((prev) => [...prev, ...valid])
    target.value = ''
  }

  const removeAttachment = (idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx))
  }

  const formatSize = (bytes: number) => {
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${bytes} B`
  }

  const resolvedModelKey = createMemo(() =>
    chatState.isStreaming && chatState.streamMeta?.model_key
      ? chatState.streamMeta.model_key
      : modelsState.activeModel,
  )

  const modelSpec = createMemo(() =>
    resolvedModelKey() !== 'auto' ? modelsState.models[resolvedModelKey()] : null,
  )

  const modelDisplay = createMemo(() =>
    resolvedModelKey() === 'auto'
      ? 'Auto'
      : (modelSpec()?.display?.replace('Emily — ', '') || resolvedModelKey()),
  )

  const providerColor = createMemo(() =>
    modelSpec() ? (PROVIDER_COLORS[modelSpec()!.provider] || '#555') : '#888',
  )

  const currentSkill = createMemo(() => modelsState.skills[modelsState.activeSkill])
  const currentMode = createMemo(() => modelsState.modes[modelsState.activeMode])

  return (
    <div
      class="px-4 py-3 flex-shrink-0"
      style={{ 'border-top': '1px solid oklch(0.30 0.03 185)', background: 'oklch(0.22 0.025 185)' }}
    >
      <div class="max-w-4xl mx-auto space-y-2">
        <Show when={attachments().length > 0}>
          <div class="flex items-center gap-2 flex-wrap">
            <For each={attachments()}>
              {(file, i) => (
                <div
                  class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg"
                  style={{
                    background: 'oklch(0.18 0.02 185)',
                    border: '1px solid oklch(0.30 0.03 185)',
                    'font-size': 'var(--text-small)',
                    color: 'oklch(0.65 0.03 185)',
                    'font-family': 'var(--font-body)',
                  }}
                >
                  <Paperclip size={12} />
                  <span class="max-w-[120px] truncate">{file.name}</span>
                  <span style={{ color: 'oklch(0.50 0.04 185)' }}>{formatSize(file.size)}</span>
                  <button onClick={() => removeAttachment(i())} style={{ color: 'oklch(0.50 0.04 185)' }}>
                    <X size={12} />
                  </button>
                </div>
              )}
            </For>
          </div>
        </Show>

        <div class="flex items-end gap-2">
          <div class="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={text()}
              onInput={(e) => setText(e.currentTarget.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Emily anything..."
              rows={1}
              class="w-full resize-none rounded-xl px-4 py-3 pr-24 input-mode-border transition-colors leading-relaxed"
              style={{
                'min-height': '44px',
                'max-height': '220px',
                background: 'oklch(0.18 0.02 185)',
                border: '1px solid oklch(0.30 0.03 185)',
                color: 'oklch(0.93 0.01 90)',
                'font-size': 'var(--text-body)',
                'font-family': 'var(--font-body)',
              }}
            />

            <div class="absolute right-2 bottom-2 flex items-center gap-1">
              <button
                onClick={handleAttach}
                class="p-1.5 rounded-lg transition-colors"
                style={{ color: 'oklch(0.50 0.04 185)' }}
                title="Attach files"
              >
                <Paperclip size={16} />
              </button>
              <button
                onClick={() => setWebSearch(!webSearch())}
                class="p-1.5 rounded-lg transition-colors"
                style={{
                  color: webSearch() ? 'oklch(0.72 0.17 162)' : 'oklch(0.50 0.04 185)',
                  background: webSearch() ? 'oklch(0.72 0.17 162 / 0.10)' : '',
                }}
                title="Web search"
              >
                <Globe size={16} />
              </button>
              <button
                class="p-1.5 rounded-lg transition-colors"
                style={{ color: 'oklch(0.50 0.04 185)' }}
                title="Quick mode"
              >
                <Zap size={16} />
              </button>
            </div>
          </div>

          <Show
            when={chatState.isStreaming}
            fallback={
              <button
                onClick={handleSend}
                disabled={!text().trim()}
                class="p-3 rounded-xl transition-colors flex-shrink-0 disabled:opacity-30 disabled:cursor-not-allowed"
                style={{ background: 'oklch(0.72 0.17 162)', color: 'oklch(0.18 0.02 185)' }}
                onMouseEnter={(e) => { if (text().trim()) e.currentTarget.style.background = 'oklch(0.78 0.14 162)' }}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'oklch(0.72 0.17 162)')}
                title="Send message"
              >
                <Send size={20} />
              </button>
            }
          >
            <button
              onClick={stopGeneration}
              class="p-3 rounded-xl transition-colors flex-shrink-0"
              style={{ background: 'oklch(0.65 0.20 25)', color: 'oklch(0.93 0.01 90)' }}
              title="Stop generation"
            >
              <Square size={20} />
            </button>
          </Show>
        </div>

        {/* Status bar */}
        <div class="flex items-center justify-between min-h-[20px]">
          <div class="flex items-center gap-1.5 text-xs" style={{ color: 'oklch(0.50 0.04 185)' }}>
            <Cpu size={12} class="flex-shrink-0" />
            <span
              class="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ 'background-color': providerColor() }}
            />
            <span style={{ color: chatState.isStreaming && chatState.streamMeta ? 'oklch(0.72 0.17 162)' : 'oklch(0.50 0.04 185)' }}>
              {modelDisplay()}
            </span>
            <Show when={currentSkill()}>
              {(() => {
                const modeTheme = createMemo(() => getModeTheme(modelsState.activeSkill))
                const ActiveSkillIcon = createMemo(() => getSkillIcon(modelsState.activeSkill))
                return (
                  <>
                    <span style={{ color: 'oklch(0.50 0.04 185 / 0.4)' }}>&middot;</span>
                    <div
                      class="w-4 h-4 rounded flex items-center justify-center flex-shrink-0"
                      style={{ background: modeTheme().gradient }}
                    >
                      {(() => {
                        const Icon = ActiveSkillIcon()
                        return <Icon size={10} style={{ color: 'white' }} />
                      })()}
                    </div>
                    <span style={{ color: modeTheme().accent }}>{currentSkill()!.name}</span>
                  </>
                )
              })()}
            </Show>
            <Show when={modelsState.activeMode !== 'normal' && currentMode()}>
              <span style={{ color: 'oklch(0.50 0.04 185 / 0.4)' }}>&middot;</span>
              <span class="text-[10px]" style={{ color: 'oklch(0.72 0.17 162)' }}>
                {currentMode()!.icon} {currentMode()!.display}
              </span>
            </Show>
            {/* Mode selector */}
            <div class="relative ml-1">
              <button
                onClick={() => setShowModeDropdown(!showModeDropdown())}
                class="flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors"
                style={{ color: 'oklch(0.50 0.04 185)' }}
                title="Select mode"
              >
                <Layers size={12} />
              </button>
              <Show when={showModeDropdown()}>
                <div
                  class="absolute bottom-full left-0 mb-1 w-48 rounded-lg shadow-lg py-1 z-50"
                  style={{ background: 'oklch(0.22 0.025 185)', border: '1px solid oklch(0.30 0.03 185)' }}
                >
                  <For each={Object.entries(modelsState.modes)}>
                    {([id, mode]) => (
                      <button
                        onClick={() => { setActiveMode(id); setShowModeDropdown(false) }}
                        class="w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 transition-colors"
                        style={{
                          color: id === modelsState.activeMode ? 'oklch(0.72 0.17 162)' : 'oklch(0.65 0.03 185)',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'oklch(0.26 0.03 185)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                      >
                        <span>{mode.icon}</span>
                        <span class="flex-1">{mode.display}</span>
                        <Show when={mode.reasoning_strategy !== 'direct'}>
                          <span class="text-[9px]" style={{ color: 'oklch(0.50 0.04 185)' }}>
                            {mode.reasoning_strategy.replace(/_/g, ' ')}
                          </span>
                        </Show>
                      </button>
                    )}
                  </For>
                </div>
              </Show>
            </div>
          </div>

          <Show when={suggestedSkill()}>
            {(suggested) => {
              const SuggestedIcon = createMemo(() => getSkillIcon(suggested().skill))
              return (
                <div class="flex items-center gap-1.5">
                  <span class="text-xs" style={{ color: 'oklch(0.50 0.04 185)' }}>Try:</span>
                  <button
                    onClick={() => { setActiveSkill(suggested().skill); setSuggestedSkill(null) }}
                    class="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs transition-colors"
                    style={{
                      background: 'oklch(0.72 0.17 162 / 0.10)',
                      border: '1px solid oklch(0.72 0.17 162 / 0.30)',
                      color: 'oklch(0.72 0.17 162)',
                    }}
                  >
                    {(() => {
                      const Icon = SuggestedIcon()
                      return <Icon size={12} />
                    })()}
                    <span>{suggested().name}</span>
                  </button>
                  <button
                    onClick={() => setSuggestedSkill(null)}
                    class="transition-colors"
                    style={{ color: 'oklch(0.50 0.04 185)' }}
                    title="Dismiss"
                  >
                    <X size={12} />
                  </button>
                </div>
              )
            }}
          </Show>
        </div>

        <input ref={fileInputRef} type="file" multiple class="hidden" onChange={handleFiles} />
      </div>
    </div>
  )
}
