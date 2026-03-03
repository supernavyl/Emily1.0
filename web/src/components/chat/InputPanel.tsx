import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import { Send, Square, Paperclip, Globe, Zap, X, Cpu, Layers } from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import { useModelsStore } from '../../stores/models'
import { PROVIDER_COLORS } from '../../api/types'
import { getSkillIcon } from '../../lib/skill-icons'
import { getModeTheme } from '../../lib/mode-themes'

// Ordered by specificity — first match wins
const SKILL_HINTS: Array<{ skill: string; name: string; pattern: RegExp }> = [
  {
    skill: 'translate', name: 'Translate',
    pattern: /\b(translate|in french|in spanish|in german|in japanese|in chinese|in arabic|in portuguese|in russian|in italian|en français|auf deutsch|en español|中文|日本語)\b/i,
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
  const sendMessage = useChatStore((s) => s.sendMessage)
  const stopGeneration = useChatStore((s) => s.stopGeneration)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const activeId = useChatStore((s) => s.activeId)
  const createConversation = useChatStore((s) => s.createConversation)
  const streamMeta = useChatStore((s) => s.streamMeta)

  const activeModel = useModelsStore((s) => s.activeModel)
  const activeSkill = useModelsStore((s) => s.activeSkill)
  const setActiveSkill = useModelsStore((s) => s.setActiveSkill)
  const activeMode = useModelsStore((s) => s.activeMode)
  const setActiveMode = useModelsStore((s) => s.setActiveMode)
  const models = useModelsStore((s) => s.models)
  const skills = useModelsStore((s) => s.skills)
  const modes = useModelsStore((s) => s.modes)

  const [text, setText] = useState('')
  const [webSearch, setWebSearch] = useState(false)
  const [attachments, setAttachments] = useState<File[]>([])
  const [suggestedSkill, setSuggestedSkill] = useState<{ skill: string; name: string } | null>(null)
  const [showModeDropdown, setShowModeDropdown] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const skillDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }, [])

  useEffect(() => adjustHeight(), [text, adjustHeight])

  // Close mode dropdown on click outside
  useEffect(() => {
    if (!showModeDropdown) return
    const handler = () => setShowModeDropdown(false)
    const timer = setTimeout(() => document.addEventListener('click', handler), 0)
    return () => { clearTimeout(timer); document.removeEventListener('click', handler) }
  }, [showModeDropdown])

  // Debounced skill detection as user types
  useEffect(() => {
    if (skillDebounceRef.current) clearTimeout(skillDebounceRef.current)
    skillDebounceRef.current = setTimeout(() => {
      const detected = detectSkill(text)
      if (detected && detected.skill !== activeSkill) {
        setSuggestedSkill(detected)
      } else {
        setSuggestedSkill(null)
      }
    }, 400)
    return () => {
      if (skillDebounceRef.current) clearTimeout(skillDebounceRef.current)
    }
  }, [text, activeSkill])

  const handleSend = async () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return

    if (!activeId) {
      await createConversation(trimmed.slice(0, 50))
    }

    sendMessage(trimmed, activeModel, activeSkill, activeMode, webSearch)
    setText('')
    setSuggestedSkill(null)
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleAttach = () => fileInputRef.current?.click()

  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    const valid = files.filter((f) => f.size <= 10 * 1024 * 1024)
    setAttachments((prev) => [...prev, ...valid])
    e.target.value = ''
  }

  const removeAttachment = (idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx))
  }

  const formatSize = (bytes: number) => {
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${bytes} B`
  }

  // During streaming show the actual resolved model; before that show selected model
  const resolvedModelKey = isStreaming && streamMeta?.model_key ? streamMeta.model_key : activeModel
  const modelSpec = resolvedModelKey !== 'auto' ? models[resolvedModelKey] : null
  const modelDisplay = resolvedModelKey === 'auto'
    ? 'Auto'
    : (modelSpec?.display?.replace('Emily — ', '') || resolvedModelKey)
  const providerColor = modelSpec ? (PROVIDER_COLORS[modelSpec.provider] || '#555') : '#888'
  const currentSkill = skills[activeSkill]
  const ActiveSkillIcon = getSkillIcon(activeSkill)
  const currentMode = modes[activeMode]

  return (
    <div className="border-t border-border bg-surface-raised px-4 py-3 flex-shrink-0">
      <div className="max-w-4xl mx-auto space-y-2">
        {attachments.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            {attachments.map((file, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface border border-border text-xs text-text-secondary"
              >
                <Paperclip className="w-3 h-3" />
                <span className="max-w-[120px] truncate">{file.name}</span>
                <span className="text-text-muted">{formatSize(file.size)}</span>
                <button onClick={() => removeAttachment(i)} className="text-text-muted hover:text-error-red">
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Emily anything..."
              rows={1}
              className="w-full resize-none rounded-xl bg-surface border border-border px-4 py-3 pr-24 text-sm text-text-primary placeholder:text-text-muted input-mode-border transition-colors leading-relaxed"
              style={{ minHeight: '44px', maxHeight: '220px' }}
            />

            <div className="absolute right-2 bottom-2 flex items-center gap-1">
              <button
                onClick={handleAttach}
                className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
                title="Attach files"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <button
                onClick={() => setWebSearch(!webSearch)}
                className={`p-1.5 rounded-lg transition-colors
                  ${webSearch ? 'text-accent bg-accent/10' : 'text-text-muted hover:text-text-secondary hover:bg-surface-hover'}`}
                title="Web search"
              >
                <Globe className="w-4 h-4" />
              </button>
              <button
                className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
                title="Quick mode"
              >
                <Zap className="w-4 h-4" />
              </button>
            </div>
          </div>

          {isStreaming ? (
            <button
              onClick={stopGeneration}
              className="p-3 rounded-xl bg-error-red hover:bg-error-red/80 text-white transition-colors flex-shrink-0"
              title="Stop generation"
            >
              <Square className="w-5 h-5" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!text.trim()}
              className="p-3 rounded-xl bg-accent hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed text-white transition-colors flex-shrink-0"
              title="Send message"
            >
              <Send className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Status bar: active model + skill suggestion */}
        <div className="flex items-center justify-between min-h-[20px]">
          <div className="flex items-center gap-1.5 text-xs text-text-muted">
            <Cpu className="w-3 h-3 flex-shrink-0" />
            <span
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: providerColor }}
            />
            <span className={isStreaming && streamMeta ? 'text-accent' : 'text-text-muted'}>
              {modelDisplay}
            </span>
            {currentSkill && (() => {
              const modeTheme = getModeTheme(activeSkill)
              return (
                <>
                  <span className="text-text-muted/40">·</span>
                  <div
                    className="w-4 h-4 rounded flex items-center justify-center flex-shrink-0"
                    style={{ background: modeTheme.gradient }}
                  >
                    <ActiveSkillIcon className="w-2.5 h-2.5 text-white" />
                  </div>
                  <span style={{ color: modeTheme.accent }}>{currentSkill.name}</span>
                </>
              )
            })()}
            {activeMode !== 'normal' && currentMode && (
              <>
                <span className="text-text-muted/40">·</span>
                <span className="text-accent text-[10px]">{currentMode.icon} {currentMode.display}</span>
              </>
            )}
            {/* Mode selector */}
            <div className="relative ml-1">
              <button
                onClick={() => setShowModeDropdown(!showModeDropdown)}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded text-text-muted hover:text-text-secondary hover:bg-surface-hover transition-colors"
                title="Select mode"
              >
                <Layers className="w-3 h-3" />
              </button>
              {showModeDropdown && (
                <div className="absolute bottom-full left-0 mb-1 w-48 bg-surface-raised border border-border rounded-lg shadow-lg py-1 z-50">
                  {Object.entries(modes).map(([id, mode]) => (
                    <button
                      key={id}
                      onClick={() => { setActiveMode(id); setShowModeDropdown(false) }}
                      className={`w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 hover:bg-surface-hover transition-colors ${
                        id === activeMode ? 'text-accent' : 'text-text-secondary'
                      }`}
                    >
                      <span>{mode.icon}</span>
                      <span className="flex-1">{mode.display}</span>
                      {mode.reasoning_strategy !== 'direct' && (
                        <span className="text-[9px] text-text-muted">{mode.reasoning_strategy.replace(/_/g, ' ')}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {suggestedSkill && (() => {
            const SuggestedIcon = getSkillIcon(suggestedSkill.skill)
            return (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-text-muted">Try:</span>
              <button
                onClick={() => { setActiveSkill(suggestedSkill.skill); setSuggestedSkill(null) }}
                className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent/10 border border-accent/30 text-xs text-accent hover:bg-accent/20 transition-colors"
              >
                <SuggestedIcon className="w-3 h-3" />
                <span>{suggestedSkill.name}</span>
              </button>
              <button
                onClick={() => setSuggestedSkill(null)}
                className="text-text-muted hover:text-text-secondary transition-colors"
                title="Dismiss"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
            )
          })()}
        </div>

        <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFiles} />
      </div>
    </div>
  )
}
