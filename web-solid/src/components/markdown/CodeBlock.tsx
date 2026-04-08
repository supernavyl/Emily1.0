import { createSignal, createResource, Show, createMemo } from 'solid-js'
import { codeToHtml } from 'shiki'
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-solid'

interface Props {
  code: string
  language?: string
}

export function CodeBlock(props: Props) {
  const [copied, setCopied] = createSignal(false)
  const [expanded, setExpanded] = createSignal(false)

  const lines = createMemo(() => props.code.split('\n'))
  const isLong = createMemo(() => lines().length > 30)
  const displayCode = createMemo(() =>
    isLong() && !expanded() ? lines().slice(0, 15).join('\n') : props.code,
  )
  const lang = createMemo(() => props.language || 'text')

  const source = createMemo(() => ({ code: displayCode(), lang: lang() }))

  const [highlighted] = createResource(source, async (src) => {
    return codeToHtml(src.code, {
      lang: src.lang,
      theme: 'one-dark-pro',
    })
  })

  const handleCopy = () => {
    navigator.clipboard.writeText(props.code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div class="my-3 rounded-xl overflow-hidden" style={{ border: '1px solid oklch(0.30 0.03 185)', background: 'oklch(0.18 0.02 185)' }}>
      <div
        class="flex items-center justify-between px-4 py-2"
        style={{ background: 'oklch(0.22 0.025 185 / 0.5)', 'border-bottom': '1px solid oklch(0.30 0.03 185)' }}
      >
        <span class="text-xs font-mono uppercase" style={{ color: 'oklch(0.50 0.04 185)' }}>
          {lang()}
        </span>
        <button
          onClick={handleCopy}
          class="flex items-center gap-1.5 text-xs transition-colors"
          style={{ color: 'oklch(0.50 0.04 185)' }}
        >
          <Show when={copied()} fallback={<><Copy size={14} /> Copy</>}>
            <Check size={14} style={{ color: 'oklch(0.72 0.15 145)' }} /> Copied
          </Show>
        </button>
      </div>

      <Show
        when={!highlighted.loading && highlighted()}
        fallback={
          <pre
            class="p-4 overflow-x-auto"
            style={{ 'font-size': '13px', 'line-height': '1.6', color: 'oklch(0.85 0.02 185)', 'font-family': 'var(--font-mono)' }}
          >
            <code>{displayCode()}</code>
          </pre>
        }
      >
        <div
          class="overflow-x-auto [&_pre]:!bg-transparent [&_pre]:!m-0 [&_pre]:!p-4"
          style={{ 'font-size': '13px', 'line-height': '1.6' }}
          innerHTML={highlighted()!}
        />
      </Show>

      <Show when={isLong()}>
        <button
          onClick={() => setExpanded(!expanded())}
          class="w-full flex items-center justify-center gap-1 py-2 text-xs transition-colors"
          style={{ color: 'oklch(0.50 0.04 185)', 'border-top': '1px solid oklch(0.30 0.03 185)' }}
        >
          <Show when={expanded()} fallback={<><ChevronDown size={12} /> Show all ({lines().length} lines)</>}>
            <ChevronUp size={12} /> Collapse
          </Show>
        </button>
      </Show>
    </div>
  )
}
