import { useState } from 'react'
import { Pencil, RotateCcw, Copy, Check } from 'lucide-react'
import type { Message } from '../../api/types'

export function UserMessage({ message }: { message: Message }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="flex justify-end group">
      <div className="max-w-[80%] space-y-1">
        <div className="bg-user-bubble rounded-2xl rounded-br-md px-4 py-3">
          <p className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
            {message.content}
          </p>
        </div>
        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={handleCopy}
            className="p-1 rounded text-text-muted hover:text-text-secondary transition-colors"
            title="Copy"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-cost-green" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          <button className="p-1 rounded text-text-muted hover:text-text-secondary transition-colors" title="Edit">
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button className="p-1 rounded text-text-muted hover:text-text-secondary transition-colors" title="Resend">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
