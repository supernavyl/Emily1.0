import { createMemo, For } from 'solid-js'
import { brainState } from '../../stores/brain'
import { RadarChart } from '../charts/RadarChart'
import { Sparkline } from '../charts/Sparkline'
import { BarChart } from '../charts/BarChart'

const STYLE_PARAMS = [
  { key: 'rate_mod', label: 'Speaking Rate', baseline: 1.0 },
  { key: 'pitch_mod', label: 'Pitch Range', baseline: 1.0 },
  { key: 'energy_mod', label: 'Energy', baseline: 1.0 },
  { key: 'warmth', label: 'Warmth', baseline: 0.75 },
  { key: 'pause_freq', label: 'Pause Freq', baseline: 0.5 },
  { key: 'sent_len', label: 'Sentence Len', baseline: 10 },
  { key: 'vocab', label: 'Vocabulary', baseline: 0.5 },
]

const EMOTION_COLORS: Record<string, string> = {
  engagement:  'var(--color-accent)',
  confidence:  'var(--color-cost-green)',
  concern:     'var(--color-warning-amber)',
  enthusiasm:  'var(--color-phase-comparing)',
}

const EMOTION_DIMS = ['engagement', 'confidence', 'concern', 'enthusiasm'] as const

export function EmotionalCortex() {
  const emotions = createMemo(() => brainState.status?.emotional_state || {})

  const radarAxes = createMemo(() => [
    { label: 'Engagement', value: emotions().engagement || 0 },
    { label: 'Confidence', value: emotions().confidence || 0 },
    { label: 'Concern', value: emotions().concern || 0 },
    { label: 'Enthusiasm', value: emotions().enthusiasm || 0 },
  ])

  const styleParams = createMemo(() => {
    const warmth = emotions().engagement || 0.5
    return STYLE_PARAMS.map((p) => ({
      label: p.label,
      value: p.key === 'warmth' ? warmth * 1.1 :
             p.key === 'energy_mod' ? 0.8 + (emotions().enthusiasm || 0) * 0.4 :
             p.key === 'rate_mod' ? 0.9 + (emotions().engagement || 0) * 0.2 :
             p.key === 'pitch_mod' ? 0.85 + (emotions().enthusiasm || 0) * 0.35 :
             p.key === 'pause_freq' ? 0.3 + (emotions().concern || 0) * 0.4 :
             p.key === 'sent_len' ? (6 + (1 - (emotions().concern || 0)) * 8) / 14 :
             p.key === 'vocab' ? 0.3 + (emotions().confidence || 0) * 0.4 :
             p.baseline,
      max: p.key === 'sent_len' ? 1 : 1.5,
      color: 'var(--color-accent)',
    }))
  })

  return (
    <div class="p-6 space-y-6 animate-scale-in">
      <div class="grid grid-cols-2 gap-6">
        {/* Large Radar */}
        <div
          class="rounded-xl p-6 flex flex-col items-center"
          style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
        >
          <h3
            class="text-xs font-semibold uppercase mb-4 self-start"
            style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
          >
            Emotional Radar
          </h3>
          <RadarChart axes={radarAxes()} size={260} />
          <div class="flex gap-4 mt-4">
            <For each={Object.entries(emotions())}>
              {([key, val]) => (
                <div class="flex items-center gap-1.5">
                  <span
                    class="w-2 h-2 rounded-full"
                    style={{ 'background-color': EMOTION_COLORS[key] || 'var(--color-accent)' }}
                  />
                  <span class="text-xs capitalize" style={{ color: 'var(--color-text-secondary)' }}>{key}</span>
                  <span class="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
                    {(val as number).toFixed(2)}
                  </span>
                </div>
              )}
            </For>
          </div>
        </div>

        {/* Response Style Parameters */}
        <div
          class="rounded-xl p-6"
          style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
        >
          <h3
            class="text-xs font-semibold uppercase mb-4"
            style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
          >
            Response Style Parameters
          </h3>
          <p class="text-xs mb-4" style={{ color: 'var(--color-text-muted)' }}>
            Emily adapts these parameters based on detected user emotion
          </p>
          <BarChart bars={styleParams()} height={10} />
        </div>
      </div>

      {/* Emotion History Sparklines */}
      <div
        class="rounded-xl p-6"
        style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
      >
        <h3
          class="text-xs font-semibold uppercase mb-4"
          style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
        >
          Emotion History (last 5 min)
        </h3>
        <div class="grid grid-cols-4 gap-4">
          <For each={[...EMOTION_DIMS]}>
            {(dim) => {
              const data = createMemo(() => brainState.emotionHistory.map((e) => (e[dim] as number) || 0))
              return (
                <div class="flex flex-col gap-1">
                  <div class="flex justify-between items-center">
                    <span class="text-xs capitalize" style={{ color: 'var(--color-text-secondary)' }}>{dim}</span>
                    <span class="text-xs font-mono" style={{ color: EMOTION_COLORS[dim] }}>
                      {(emotions()[dim] || 0).toFixed(2)}
                    </span>
                  </div>
                  <Sparkline
                    data={data()}
                    width={200}
                    height={40}
                    color={EMOTION_COLORS[dim] || 'var(--color-accent)'}
                  />
                </div>
              )
            }}
          </For>
        </div>
      </div>

      {/* Emotion Sync Info */}
      <div
        class="rounded-xl p-4"
        style={{ background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)' }}
      >
        <h3
          class="text-xs font-semibold uppercase mb-2"
          style={{ color: 'var(--color-text-muted)', 'letter-spacing': '0.05em' }}
        >
          Emotional Synchronization
        </h3>
        <p class="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
          Emily detects 10 user emotions (Neutral, Happy, Excited, Anxious, Frustrated, Sad, Confused, Curious, Bored, Tired)
          and adapts her response style in real-time. Positive emotions are mirrored; negative emotions are calmed.
          Changes are smoothed using EMA (a=0.2) to prevent jarring shifts.
        </p>
      </div>
    </div>
  )
}
