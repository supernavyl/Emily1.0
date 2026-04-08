import { createSignal, Show } from 'solid-js'
import { Copy, Check, Pencil, RotateCcw } from 'lucide-solid'
import type { Message } from '../../api/types'

interface Props {
  message: Message
}

export function UserMessage(props: Props) {
  const [copied, setCopied] = createSignal(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(props.message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div class="flex justify-end group">
      <div class="max-w-[80%] space-y-1">
        <div
          class="rounded-2xl rounded-br-sm px-4 py-3"
          style={{ background: 'oklch(0.24 0.03 185)', border: '1px solid oklch(0.30 0.03 185 / 0.6)' }}
        >
          <p
            class="whitespace-pre-wrap leading-relaxed"
            style={{ 'font-size': 'var(--text-body)', color: 'oklch(0.93 0.01 90)', 'font-family': 'var(--font-body)' }}
          >
            {props.message.content}
          </p>
        </div>
        <div class="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={handleCopy}
            class="p-1 rounded transition-colors"
            style={{ color: 'oklch(0.50 0.04 185)' }}
            title="Copy"
          >
            <Show
              when={copied()}
              fallback={<Copy size={14} />}
            >
              <Check size={14} style={{ color: 'oklch(0.72 0.15 145)' }} />
            </Show>
          </button>
          <button
            class="p-1 rounded transition-colors"
            style={{ color: 'oklch(0.50 0.04 185)' }}
            title="Edit"
          >
            <Pencil size={14} />
          </button>
          <button
            class="p-1 rounded transition-colors"
            style={{ color: 'oklch(0.50 0.04 185)' }}
            title="Resend"
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}
