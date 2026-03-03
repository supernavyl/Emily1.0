import { useBrainStore } from '../../stores/brain'
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
  engagement: 'var(--color-phase-analyzing)',
  confidence: 'var(--color-cost-green)',
  concern: 'var(--color-warning-amber)',
  enthusiasm: 'var(--color-phase-comparing)',
}

export function EmotionalCortex() {
  const emotions = useBrainStore((s) => s.status?.emotional_state || {})
  const emotionHistory = useBrainStore((s) => s.emotionHistory)

  const radarAxes = [
    { label: 'Engagement', value: emotions.engagement || 0 },
    { label: 'Confidence', value: emotions.confidence || 0 },
    { label: 'Concern', value: emotions.concern || 0 },
    { label: 'Enthusiasm', value: emotions.enthusiasm || 0 },
  ]

  // Simulate response style params from emotional state
  const warmth = emotions.engagement || 0.5
  const styleParams = STYLE_PARAMS.map(p => ({
    label: p.label,
    value: p.key === 'warmth' ? warmth * 1.1 :
           p.key === 'energy_mod' ? 0.8 + (emotions.enthusiasm || 0) * 0.4 :
           p.key === 'rate_mod' ? 0.9 + (emotions.engagement || 0) * 0.2 :
           p.key === 'pitch_mod' ? 0.85 + (emotions.enthusiasm || 0) * 0.35 :
           p.key === 'pause_freq' ? 0.3 + (emotions.concern || 0) * 0.4 :
           p.key === 'sent_len' ? (6 + (1 - (emotions.concern || 0)) * 8) / 14 :
           p.key === 'vocab' ? 0.3 + (emotions.confidence || 0) * 0.4 :
           p.baseline,
    max: p.key === 'sent_len' ? 1 : 1.5,
    color: 'var(--color-accent)',
  }))

  return (
    <div className="p-6 space-y-6 animate-scale-in">
      <div className="grid grid-cols-2 gap-6">
        {/* Large Radar */}
        <div className="bg-surface-raised border border-border rounded-xl p-6 flex flex-col items-center">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4 self-start">Emotional Radar</h3>
          <RadarChart axes={radarAxes} size={260} />
          <div className="flex gap-4 mt-4">
            {Object.entries(emotions).map(([key, val]) => (
              <div key={key} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: EMOTION_COLORS[key] || 'var(--color-accent)' }} />
                <span className="text-xs text-text-secondary capitalize">{key}</span>
                <span className="text-xs font-mono text-text-muted">{val.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Response Style Parameters */}
        <div className="bg-surface-raised border border-border rounded-xl p-6">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Response Style Parameters</h3>
          <p className="text-xs text-text-muted mb-4">Emily adapts these parameters based on detected user emotion</p>
          <BarChart bars={styleParams} height={10} />
        </div>
      </div>

      {/* Emotion History Sparklines */}
      <div className="bg-surface-raised border border-border rounded-xl p-6">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Emotion History (last 5 min)</h3>
        <div className="grid grid-cols-4 gap-4">
          {['engagement', 'confidence', 'concern', 'enthusiasm'].map(dim => {
            const data = emotionHistory.map(e => e[dim] || 0)
            return (
              <div key={dim} className="flex flex-col gap-1">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-text-secondary capitalize">{dim}</span>
                  <span className="text-xs font-mono" style={{ color: EMOTION_COLORS[dim] }}>
                    {(emotions[dim] || 0).toFixed(2)}
                  </span>
                </div>
                <Sparkline
                  data={data}
                  width={200}
                  height={40}
                  color={EMOTION_COLORS[dim] || 'var(--color-accent)'}
                />
              </div>
            )
          })}
        </div>
      </div>

      {/* Emotion Sync Info */}
      <div className="bg-surface-raised border border-border rounded-xl p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Emotional Synchronization</h3>
        <p className="text-xs text-text-secondary leading-relaxed">
          Emily detects 10 user emotions (Neutral, Happy, Excited, Anxious, Frustrated, Sad, Confused, Curious, Bored, Tired)
          and adapts her response style in real-time. Positive emotions are mirrored; negative emotions are calmed.
          Changes are smoothed using EMA (α=0.2) to prevent jarring shifts.
        </p>
      </div>
    </div>
  )
}
