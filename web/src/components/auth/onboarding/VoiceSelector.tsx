import { Volume2, Check } from 'lucide-react'

interface VoiceOption {
  id: string
  label: string
  desc: string
}

const VOICES: VoiceOption[] = [
  { id: 'en-US-JennyNeural', label: 'Jenny', desc: 'Warm & conversational' },
  { id: 'en-US-AriaNeural', label: 'Aria', desc: 'Expressive & clear' },
  { id: 'en-US-MichelleNeural', label: 'Michelle', desc: 'Professional & smooth' },
  { id: 'en-US-SaraNeural', label: 'Sara', desc: 'Young & friendly' },
  { id: 'en-GB-SoniaNeural', label: 'Sonia', desc: 'British & elegant' },
]

interface Props {
  selected: string
  onSelect: (id: string) => void
  onPreview: (id: string) => void
  previewing: string | null
}

export function VoiceSelector({ selected, onSelect, onPreview, previewing }: Props) {
  return (
    <div className="animate-fade-up grid max-h-[220px] gap-1.5 overflow-y-auto pr-1">
      {VOICES.map((v) => {
        const active = v.id === selected
        return (
          <button
            key={v.id}
            onClick={() => onSelect(v.id)}
            className="group flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-left transition-all"
            style={{
              backdropFilter: 'blur(12px)',
              background: active ? 'rgba(124,106,247,0.1)' : 'rgba(255,255,255,0.02)',
              border: active
                ? '1px solid rgba(124,106,247,0.35)'
                : '1px solid rgba(255,255,255,0.05)',
              boxShadow: active ? '0 0 20px rgba(124,106,247,0.1)' : 'none',
            }}
          >
            <div className="min-w-0 flex-1">
              <p
                className={`text-sm font-medium ${active ? 'text-text-primary' : 'text-text-secondary'}`}
              >
                {v.label}
              </p>
              <p className="truncate text-xs text-text-muted">{v.desc}</p>
            </div>

            <button
              onClick={(e) => {
                e.stopPropagation()
                onPreview(v.id)
              }}
              className="flex-shrink-0 rounded-lg p-1.5 transition-colors hover:bg-white/10"
              aria-label={`Preview ${v.label} voice`}
            >
              <Volume2
                className={`h-3.5 w-3.5 transition-colors ${
                  previewing === v.id
                    ? 'animate-pulse text-accent'
                    : 'text-text-muted group-hover:text-text-secondary'
                }`}
              />
            </button>

            {active && <Check className="h-4 w-4 flex-shrink-0 text-accent" />}
          </button>
        )
      })}
    </div>
  )
}

export { VOICES }
export type { VoiceOption }
