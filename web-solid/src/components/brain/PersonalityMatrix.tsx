import { createMemo, Show, For } from 'solid-js'
import { Sparkle, User, Cpu, Heart, Brain, FileText } from 'lucide-solid'
import type { LucideIcon } from 'lucide-solid'
import { brainState } from '../../stores/brain'
import { BarChart } from '../charts/BarChart'

const PROMPT_STACK: { label: string; icon: LucideIcon; desc: string }[] = [
  { label: 'Core System', icon: Cpu, desc: 'Identity, capabilities, behavior rules, safety' },
  { label: 'Persona Injection', icon: Sparkle, desc: 'Curiosity, warmth, humor, formality traits' },
  { label: 'User Profile', icon: User, desc: 'Name, preferences, goals, relationships' },
  { label: 'Emotional State', icon: Heart, desc: 'Concern, confidence \u2192 subtle behavior modifiers' },
  { label: 'RAG Context', icon: FileText, desc: 'Retrieved knowledge chunks with confidence scores' },
]

export function PersonalityMatrix() {
  const traits = createMemo(() => {
    const p = brainState.profiles as Record<string, Record<string, number>> | null
    return p?.persona || { curiosity: 0.8, warmth: 0.75, humor: 0.6, formality: 0.3 }
  })

  const traitBars = createMemo(() => [
    { label: 'Curiosity', value: traits().curiosity || 0.8, color: 'var(--color-phase-analyzing)' },
    { label: 'Warmth', value: traits().warmth || 0.75, color: 'var(--color-warning-amber)' },
    { label: 'Humor', value: traits().humor || 0.6, color: 'var(--color-cost-green)' },
    { label: 'Formality', value: traits().formality || 0.3, color: 'var(--color-phase-comparing)' },
  ])

  const activeSkillId = 'normal'
  const skills = () => brainState.skills

  return (
    <div class="p-6 space-y-6 animate-scale-in">
      <div class="grid grid-cols-2 gap-6">
        {/* Personality Traits */}
        <div
          class="rounded-xl p-6"
          style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
        >
          <h3
            class="text-xs font-semibold uppercase mb-4"
            style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
          >
            Personality Traits
          </h3>
          <BarChart bars={traitBars()} height={14} />
          <p class="text-xs mt-4 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
            These traits shape Emily's communication style. Higher curiosity = more follow-up questions.
            Higher warmth = more personable responses. These are injected into every prompt via the persona system.
          </p>
        </div>

        {/* Core Identity */}
        <div
          class="rounded-xl p-6"
          style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
        >
          <h3
            class="text-xs font-semibold uppercase mb-4"
            style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
          >
            Core Identity
          </h3>
          <div class="space-y-3">
            <p class="text-sm italic leading-relaxed" style={{ color: 'var(--color-text-primary)' }}>
              "A persistent, intelligent AI companion with consistent personality, deep memory, and genuine curiosity."
            </p>
            <div class="flex flex-wrap gap-2">
              <For each={['Direct', 'Warm', 'Intellectually Curious', 'Witty', 'Accurate']}>
                {(trait) => (
                  <span
                    class="text-xs px-2.5 py-1 rounded-full"
                    style={{ background: 'oklch(0.72 0.17 162 / 0.1)', color: 'var(--color-accent)' }}
                  >
                    {trait}
                  </span>
                )}
              </For>
            </div>
          </div>
        </div>
      </div>

      {/* Active Skill */}
      <div
        class="rounded-xl p-4"
        style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
      >
        <h3
          class="text-xs font-semibold uppercase mb-3"
          style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
        >
          Skills Library
        </h3>
        <div class="grid grid-cols-4 gap-2">
          <Show
            when={Object.entries(skills()).length > 0}
            fallback={
              <div class="col-span-4 text-xs py-4 text-center" style={{ color: 'var(--color-text-muted)' }}>
                Loading skills...
              </div>
            }
          >
            <For each={Object.entries(skills())}>
              {([id, skill]) => {
                const s = skill as { icon?: string; name?: string; description?: string }
                return (
                  <div
                    class="flex items-center gap-2 px-3 py-2 rounded-lg transition-all"
                    style={{
                      border: `1px solid ${id === activeSkillId ? 'oklch(0.72 0.17 162 / 0.4)' : 'var(--color-border)'}`,
                      background: id === activeSkillId ? 'oklch(0.72 0.17 162 / 0.05)' : 'var(--color-surface)',
                    }}
                  >
                    <span class="text-base">{s.icon || '\u26A1'}</span>
                    <div class="flex-1 min-w-0">
                      <div class="text-xs font-medium truncate" style={{ color: 'var(--color-text-primary)' }}>
                        {s.name || id}
                      </div>
                      <div class="truncate" style={{ 'font-size': '10px', color: 'var(--color-text-muted)' }}>
                        {s.description || ''}
                      </div>
                    </div>
                  </div>
                )
              }}
            </For>
          </Show>
        </div>
      </div>

      {/* Prompt Assembly Stack */}
      <div
        class="rounded-xl p-6"
        style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
      >
        <h3
          class="text-xs font-semibold uppercase mb-4"
          style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
        >
          Prompt Injection Stack
        </h3>
        <p class="text-xs mb-4" style={{ color: 'var(--color-text-muted)' }}>
          Every prompt Emily receives is dynamically assembled from these layers, top to bottom:
        </p>
        <div class="space-y-2">
          <For each={PROMPT_STACK}>
            {(item, i) => {
              const Icon = item.icon
              return (
                <div class="flex items-center gap-3">
                  <div class="flex flex-col items-center">
                    <div
                      class="w-8 h-8 rounded-lg flex items-center justify-center"
                      style={{ background: 'oklch(0.72 0.17 162 / 0.1)' }}
                    >
                      <Icon size={16} style={{ color: 'var(--color-accent)' }} />
                    </div>
                    <Show when={i() < PROMPT_STACK.length - 1}>
                      <div class="w-px h-4 mt-1" style={{ background: 'var(--color-border)' }} />
                    </Show>
                  </div>
                  <div>
                    <span class="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{item.label}</span>
                    <p class="text-xs" style={{ color: 'var(--color-text-muted)' }}>{item.desc}</p>
                  </div>
                </div>
              )
            }}
          </For>
        </div>
      </div>
    </div>
  )
}
