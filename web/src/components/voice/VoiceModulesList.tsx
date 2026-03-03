import { Check, X } from 'lucide-react'

interface Props {
  modules: string[]
  ttsAvailable: boolean
  sttAvailable: boolean
}

export function VoiceModulesList({ modules, ttsAvailable, sttAvailable }: Props) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Modules</h3>
      <div className="space-y-1">
        {[
          { label: 'STT', ok: sttAvailable },
          { label: 'TTS', ok: ttsAvailable },
          ...modules.map(m => ({ label: m, ok: true })),
        ].map(({ label, ok }) => (
          <div key={label} className="flex items-center gap-2 text-xs">
            {ok ? <Check className="w-3 h-3 text-cost-green" /> : <X className="w-3 h-3 text-error-red" />}
            <span className={ok ? 'text-text-secondary' : 'text-text-muted'}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
