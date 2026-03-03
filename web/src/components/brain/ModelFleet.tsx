import { useBrainStore } from '../../stores/brain'
import { DonutChart } from '../charts/DonutChart'

const PROVIDER_COLORS: Record<string, string> = {
  ollama: '#e8e8e8',
  anthropic: '#d4a27f',
  openai: '#74aa9c',
  google: '#4285f4',
  xai: '#1da1f2',
  deepseek: '#5b7ff5',
  groq: '#f55d42',
  mistral: '#ff7000',
  tabbyapi: '#a855f7',
  local: '#22c55e',
}

export function ModelFleet() {
  const models = useBrainStore((s) => s.models)

  const grouped = Object.entries(models).reduce<Record<string, { display: string; tier: string; thinking: boolean; vision: boolean }[]>>((acc, [key, m]) => {
    const p = m.provider || 'unknown'
    if (!acc[p]) acc[p] = []
    acc[p].push({ display: m.display || key, tier: m.tier || '', thinking: m.thinking, vision: m.vision })
    return acc
  }, {})

  const tierCounts = Object.values(models).reduce<Record<string, number>>((acc, m) => {
    const t = m.tier || 'other'
    acc[t] = (acc[t] || 0) + 1
    return acc
  }, {})

  const donutSegments = Object.entries(tierCounts).map(([tier, count]) => ({
    label: tier,
    value: count,
    color: tier === 'fast' ? '#3b82f6' :
           tier === 'smart' ? '#a855f7' :
           tier === 'reasoning' ? '#f59e0b' :
           tier === 'nano' ? '#22c55e' :
           tier === 'voice_fast' ? '#eab308' :
           tier === 'vision' ? '#ef4444' :
           tier === 'embedding' ? '#555570' : '#8888aa',
  }))

  const totalModels = Object.keys(models).length

  return (
    <div className="p-6 space-y-6 animate-scale-in">
      <div className="grid grid-cols-3 gap-6">
        {/* Tier Distribution */}
        <div className="bg-surface-raised border border-border rounded-xl p-4 flex flex-col items-center">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4 self-start">Tier Distribution</h3>
          <DonutChart segments={donutSegments} size={140} centerLabel={`${totalModels}`} />
        </div>

        {/* Provider Grid */}
        <div className="col-span-2 space-y-3">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Providers</h3>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(grouped).map(([provider, providerModels]) => (
              <div key={provider} className="bg-surface-raised border border-border rounded-xl p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PROVIDER_COLORS[provider] || '#555' }} />
                  <span className="text-xs font-semibold uppercase" style={{ color: PROVIDER_COLORS[provider] || '#888' }}>
                    {provider}
                  </span>
                  <span className="text-[10px] text-text-muted ml-auto">{providerModels.length} models</span>
                </div>
                <div className="space-y-0.5">
                  {providerModels.slice(0, 5).map((m, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-xs text-text-secondary">
                      <span className="truncate flex-1">{m.display}</span>
                      {m.thinking && <span className="text-[9px] px-1 bg-phase-analyzing/20 text-phase-analyzing rounded">think</span>}
                      {m.vision && <span className="text-[9px] px-1 bg-cost-green/20 text-cost-green rounded">vision</span>}
                    </div>
                  ))}
                  {providerModels.length > 5 && (
                    <div className="text-[10px] text-text-muted">+{providerModels.length - 5} more</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Fleet Stats */}
      <div className="bg-surface-raised border border-border rounded-xl p-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Fleet Summary</h3>
        <div className="flex gap-6 text-xs">
          <span className="text-text-secondary">Total: <span className="text-text-primary font-mono">{totalModels}</span></span>
          <span className="text-text-secondary">Providers: <span className="text-text-primary font-mono">{Object.keys(grouped).length}</span></span>
          <span className="text-text-secondary">Thinking: <span className="text-text-primary font-mono">{Object.values(models).filter(m => m.thinking).length}</span></span>
          <span className="text-text-secondary">Vision: <span className="text-text-primary font-mono">{Object.values(models).filter(m => m.vision).length}</span></span>
        </div>
      </div>
    </div>
  )
}
