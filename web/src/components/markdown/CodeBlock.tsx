import { useState } from 'react'
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface Props {
  code: string
  language?: string
}

export function CodeBlock({ code, language }: Props) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const lines = code.split('\n')
  const isLong = lines.length > 30
  const displayCode = isLong && !expanded ? lines.slice(0, 15).join('\n') : code
  const lang = language || 'text'

  const handleCopy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="my-3 rounded-xl border border-code-border overflow-hidden bg-code-bg">
      <div className="flex items-center justify-between px-4 py-2 bg-surface-hover/50 border-b border-code-border">
        <span className="text-xs font-mono text-text-muted uppercase">{lang}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-cost-green" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              Copy
            </>
          )}
        </button>
      </div>

      <SyntaxHighlighter
        language={lang}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: '1rem',
          background: 'transparent',
          fontSize: '13px',
          lineHeight: '1.6',
        }}
        showLineNumbers={lines.length > 5}
        lineNumberStyle={{ color: '#555570', fontSize: '11px', paddingRight: '1rem' }}
      >
        {displayCode}
      </SyntaxHighlighter>

      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-center gap-1 py-2 text-xs text-text-muted hover:text-text-secondary border-t border-code-border transition-colors"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-3 h-3" />
              Collapse
            </>
          ) : (
            <>
              <ChevronDown className="w-3 h-3" />
              Show all ({lines.length} lines)
            </>
          )}
        </button>
      )}
    </div>
  )
}
