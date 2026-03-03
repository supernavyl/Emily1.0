import { useBrainStore } from '../../stores/brain'
import { BarChart } from '../charts/BarChart'
import { Sparkle, User, Cpu, Heart, Brain, FileText } from 'lucide-react'

const PROMPT_STACK = [
  { label: 'Core System', icon: Cpu, desc: 'Identity, capabilities, behavior rules, safety' },
  { label: 'Persona Injection', icon: Sparkle, desc: 'Curiosity, warmth, humor, formality traits' },
  { label: 'User Profile', icon: User, desc: 'Name, preferences, goals, relationships' },
  { label: 'Emotional State', icon: Heart, desc: 'Concern, confidence → subtle behavior modifiers' },
  { label: 'RAG Context', icon: FileText, desc: 'Retrieved knowledge chunks with confidence scores' },
]

export function PersonalityMatrix() {
  const profiles = useBrainStore((s) => s.profiles)
  const skills = useBrainStore((s) => s.skills)

  // Default persona traits
  const traits = profiles?.persona || { curiosity: 0.8, warmth: 0.75, humor: 0.6, formality: 0.3 }

  const traitBars = [
    { label: 'Curiosity', value: traits.curiosity || 0.8, color: 'var(--color-phase-analyzing)' },
    { label: 'Warmth', value: traits.warmth || 0.75, color: 'var(--color-warning-amber)' },
    { label: 'Humor', value: traits.humor || 0.6, color: 'var(--color-cost-green)' },
    { label: 'Formality', value: traits.formality || 0.3, color: 'var(--color-phase-comparing)' },
  ]

  const activeSkillId = 'normal'
  const activeSkill = skills[activeSkillId]

  return (
    <div className="p-6 space-y-6 animate-scale-in">
      <div className="grid grid-cols-2 gap-6">
        {/* Personality Traits */}
        <div className="bg-surface-raised border border-border rounded-xl p-6">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Personality Traits</h3>
          <BarChart bars={traitBars} height={14} />
          <p className="text-xs text-text-muted mt-4 leading-relaxed">
            These traits shape Emily's communication style. Higher curiosity → more follow-up questions.
            Higher warmth → more personable responses. These are injected into every prompt via the persona system.
          </p>
        </div>

        {/* Core Identity */}
        <div className="bg-surface-raised border border-border rounded-xl p-6">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Core Identity</h3>
          <div className="space-y-3">
            <p className="text-sm text-text-primary leading-relaxed italic">
              "A persistent, intelligent AI companion with consistent personality, deep memory, and genuine curiosity."
            </p>
            <div className="flex flex-wrap gap-2">
              {['Direct', 'Warm', 'Intellectually Curious', 'Witty', 'Accurate'].map(trait => (
                <span key={trait} className="text-xs px-2.5 py-1 bg-accent/10 text-accent rounded-full">{trait}</span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Active Skill */}
      <div className="bg-surface-raised border border-border rounded-xl p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Skills Library</h3>
        <div className="grid grid-cols-4 gap-2">
          {Object.entries(skills).length === 0 ? (
            <div className="col-span-4 text-xs text-text-muted py-4 text-center">Loading skills...</div>
          ) : (
            Object.entries(skills).map(([id, skill]: [string, any]) => (
              <div key={id} className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${
                id === activeSkillId ? 'border-accent/40 bg-accent/5' : 'border-border bg-surface'
              }`}>
                <span className="text-base">{skill.icon || '⚡'}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-text-primary truncate">{skill.name}</div>
                  <div className="text-[10px] text-text-muted truncate">{skill.description}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Prompt Assembly Stack */}
      <div className="bg-surface-raised border border-border rounded-xl p-6">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Prompt Injection Stack</h3>
        <p className="text-xs text-text-muted mb-4">
          Every prompt Emily receives is dynamically assembled from these layers, top to bottom:
        </p>
        <div className="space-y-2">
          {PROMPT_STACK.map(({ label, icon: Icon, desc }, i) => (
            <div key={label} className="flex items-center gap-3">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                  <Icon className="w-4 h-4 text-accent" />
                </div>
                {i < PROMPT_STACK.length - 1 && (
                  <div className="w-px h-4 bg-border mt-1" />
                )}
              </div>
              <div>
                <span className="text-sm font-medium text-text-primary">{label}</span>
                <p className="text-xs text-text-muted">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
