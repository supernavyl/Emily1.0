import { Brain, Code, Search, Zap, BookOpen } from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import { useModelsStore } from '../../stores/models'
import { getModeTheme } from '../../lib/mode-themes'

interface Suggestion {
  icon: typeof Brain
  text: string
  color: string
}

const DEFAULT_SUGGESTIONS: Suggestion[] = [
  { icon: Brain, text: 'Explain quantum computing simply', color: 'text-phase-analyzing' },
  { icon: Code, text: 'Write a Python web scraper', color: 'text-cost-green' },
  { icon: Search, text: 'Research the latest AI developments', color: 'text-accent' },
  { icon: Zap, text: 'Help me debug this error', color: 'text-warning-amber' },
  { icon: BookOpen, text: 'Summarize this article for me', color: 'text-phase-comparing' },
]

const MODE_SUGGESTIONS: Record<string, Suggestion[]> = {
  code: [
    { icon: Code, text: 'Debug this Python traceback', color: 'text-cost-green' },
    { icon: Zap, text: 'Optimize this SQL query', color: 'text-warning-amber' },
    { icon: Brain, text: 'Explain this algorithm step by step', color: 'text-phase-analyzing' },
    { icon: Search, text: 'Find a library for web scraping', color: 'text-accent' },
  ],
  writing: [
    { icon: BookOpen, text: 'Draft a blog post about AI ethics', color: 'text-phase-comparing' },
    { icon: Brain, text: 'Improve this paragraph\'s clarity', color: 'text-phase-analyzing' },
    { icon: Zap, text: 'Write a compelling product description', color: 'text-warning-amber' },
    { icon: Search, text: 'Outline a 2000-word essay', color: 'text-accent' },
  ],
  research: [
    { icon: Search, text: 'Summarize recent papers on LLMs', color: 'text-accent' },
    { icon: Brain, text: 'Compare quantum vs classical computing', color: 'text-phase-analyzing' },
    { icon: BookOpen, text: 'Find sources for climate change data', color: 'text-phase-comparing' },
    { icon: Zap, text: 'Analyze market trends in AI', color: 'text-warning-amber' },
  ],
  deep_think: [
    { icon: Brain, text: 'What are the implications of AGI?', color: 'text-phase-analyzing' },
    { icon: Search, text: 'Break down the Fermi paradox', color: 'text-accent' },
    { icon: BookOpen, text: 'Analyze the trolley problem deeply', color: 'text-phase-comparing' },
    { icon: Zap, text: 'Evaluate pros and cons of remote work', color: 'text-warning-amber' },
  ],
  brainstorm: [
    { icon: Zap, text: 'Give me 10 startup ideas in AI', color: 'text-warning-amber' },
    { icon: Brain, text: 'Creative ways to learn a new language', color: 'text-phase-analyzing' },
    { icon: Search, text: 'Innovative approaches to urban farming', color: 'text-accent' },
    { icon: BookOpen, text: 'Alternative revenue models for apps', color: 'text-phase-comparing' },
  ],
}

export function EmptyState() {
  const createConversation = useChatStore((s) => s.createConversation)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const activeSkill = useModelsStore((s) => s.activeSkill)
  const theme = getModeTheme(activeSkill)
  const Icon = theme.icon

  const suggestions = MODE_SUGGESTIONS[activeSkill] ?? DEFAULT_SUGGESTIONS
  const heading = activeSkill === 'normal' ? 'Emily Chat' : `${theme.name} Mode`
  const subtitle = activeSkill === 'normal'
    ? 'Your cognitive AI companion. Ask anything, explore ideas, write code, or dive into research.'
    : theme.description

  const handleSuggestion = async (text: string) => {
    await createConversation(text.slice(0, 40))
    sendMessage(text)
  }

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-lg text-center space-y-8">
        <div className="space-y-3">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto"
            style={{
              background: theme.gradient,
              boxShadow: `0 0 30px ${theme.glow}`,
            }}
          >
            <Icon className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-text-primary">{heading}</h1>
          <p className="text-text-secondary text-sm leading-relaxed">{subtitle}</p>
        </div>

        <div className="grid gap-2">
          {suggestions.map(({ icon: SIcon, text, color }) => (
            <button
              key={text}
              onClick={() => handleSuggestion(text)}
              className="flex items-center gap-3 px-4 py-3 rounded-xl border border-border hover:border-opacity-60 hover:bg-surface-hover transition-all text-left group"
              style={{ borderLeftWidth: 3, borderLeftColor: theme.accent }}
            >
              <SIcon className={`w-5 h-5 ${color} flex-shrink-0`} />
              <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors">
                {text}
              </span>
            </button>
          ))}
        </div>

        <p className="text-xs text-text-muted">
          Press <kbd className="px-1.5 py-0.5 rounded bg-surface-hover border border-border text-text-secondary">Ctrl+M</kbd> to change mode
          {' '}&middot;{' '}
          <kbd className="px-1.5 py-0.5 rounded bg-surface-hover border border-border text-text-secondary">Ctrl+K</kbd> to search
        </p>
      </div>
    </div>
  )
}
