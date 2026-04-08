import { createMemo, For } from 'solid-js'
import { Brain, Code2, Search, Zap, BookOpen } from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'
import { createConversation, sendMessage } from '../../stores/chat'
import { modelsState } from '../../stores/models'
import { getModeTheme } from '../../lib/mode-themes'

interface Suggestion {
  icon: LucideIcon
  text: string
}

const DEFAULT_SUGGESTIONS: Suggestion[] = [
  { icon: Brain, text: 'Explain quantum computing simply' },
  { icon: Code2, text: 'Write a Python web scraper' },
  { icon: Search, text: 'Research the latest AI developments' },
  { icon: Zap, text: 'Help me debug this error' },
  { icon: BookOpen, text: 'Summarize this article for me' },
]

const MODE_SUGGESTIONS: Record<string, Suggestion[]> = {
  code: [
    { icon: Code2, text: 'Debug this Python traceback' },
    { icon: Zap, text: 'Optimize this SQL query' },
    { icon: Brain, text: 'Explain this algorithm step by step' },
    { icon: Search, text: 'Find a library for web scraping' },
  ],
  writing: [
    { icon: BookOpen, text: 'Draft a blog post about AI ethics' },
    { icon: Brain, text: "Improve this paragraph's clarity" },
    { icon: Zap, text: 'Write a compelling product description' },
    { icon: Search, text: 'Outline a 2000-word essay' },
  ],
  research: [
    { icon: Search, text: 'Summarize recent papers on LLMs' },
    { icon: Brain, text: 'Compare quantum vs classical computing' },
    { icon: BookOpen, text: 'Find sources for climate change data' },
    { icon: Zap, text: 'Analyze market trends in AI' },
  ],
  deep_think: [
    { icon: Brain, text: 'What are the implications of AGI?' },
    { icon: Search, text: 'Break down the Fermi paradox' },
    { icon: BookOpen, text: 'Analyze the trolley problem deeply' },
    { icon: Zap, text: 'Evaluate pros and cons of remote work' },
  ],
  brainstorm: [
    { icon: Zap, text: 'Give me 10 startup ideas in AI' },
    { icon: Brain, text: 'Creative ways to learn a new language' },
    { icon: Search, text: 'Innovative approaches to urban farming' },
    { icon: BookOpen, text: 'Alternative revenue models for apps' },
  ],
}

export function EmptyState() {
  const theme = createMemo(() => getModeTheme(modelsState.activeSkill))

  const suggestions = createMemo(() =>
    MODE_SUGGESTIONS[modelsState.activeSkill] ?? DEFAULT_SUGGESTIONS,
  )

  const heading = createMemo(() =>
    modelsState.activeSkill === 'normal' ? 'Emily Chat' : `${theme().name} Mode`,
  )

  const subtitle = createMemo(() =>
    modelsState.activeSkill === 'normal'
      ? 'Your cognitive AI companion. Ask anything, explore ideas, write code, or dive into research.'
      : theme().description,
  )

  const handleSuggestion = async (text: string) => {
    await createConversation(text.slice(0, 40))
    sendMessage(text)
  }

  return (
    <div class="flex-1 flex items-start justify-center p-8 pt-16">
      <div class="max-w-lg w-full space-y-8">
        <div class="space-y-3">
          <div
            class="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{
              background: theme().gradient,
              'box-shadow': `0 0 28px ${theme().glow}`,
            }}
          >
            {(() => {
              const Icon = theme().icon
              return <Icon size={28} style={{ color: 'oklch(0.18 0.02 185)' }} />
            })()}
          </div>
          <h1
            style={{
              'font-family': 'var(--font-display)',
              'font-size': 'var(--text-h1)',
              color: 'oklch(0.93 0.01 90)',
              'line-height': '1.2',
            }}
          >
            {heading()}
          </h1>
          <p
            style={{
              'font-family': 'var(--font-body)',
              'font-size': 'var(--text-body)',
              color: 'oklch(0.65 0.03 185)',
              'line-height': '1.65',
            }}
          >
            {subtitle()}
          </p>
        </div>

        <div class="grid gap-2">
          <For each={suggestions()}>
            {(item) => {
              const SIcon = item.icon
              return (
                <button
                  onClick={() => handleSuggestion(item.text)}
                  class="flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-left group"
                  style={{
                    border: '1px solid oklch(0.30 0.03 185)',
                    'border-left': `3px solid ${theme().accent}`,
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'oklch(0.26 0.03 185)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                >
                  <SIcon size={20} class="flex-shrink-0" style={{ color: theme().accent }} />
                  <span
                    style={{
                      'font-family': 'var(--font-body)',
                      'font-size': 'var(--text-body)',
                      color: 'oklch(0.65 0.03 185)',
                    }}
                  >
                    {item.text}
                  </span>
                </button>
              )
            }}
          </For>
        </div>

        <p style={{ 'font-size': 'var(--text-small)', color: 'oklch(0.50 0.04 185)', 'font-family': 'var(--font-body)' }}>
          Press{' '}
          <kbd
            class="px-1.5 py-0.5 rounded"
            style={{
              background: 'oklch(0.26 0.03 185)',
              border: '1px solid oklch(0.30 0.03 185)',
              color: 'oklch(0.65 0.03 185)',
              'font-family': 'var(--font-mono)',
              'font-size': 'var(--text-small)',
            }}
          >
            Ctrl+M
          </kbd>
          {' '}to change mode &middot;{' '}
          <kbd
            class="px-1.5 py-0.5 rounded"
            style={{
              background: 'oklch(0.26 0.03 185)',
              border: '1px solid oklch(0.30 0.03 185)',
              color: 'oklch(0.65 0.03 185)',
              'font-family': 'var(--font-mono)',
              'font-size': 'var(--text-small)',
            }}
          >
            Ctrl+K
          </kbd>
          {' '}to search
        </p>
      </div>
    </div>
  )
}
