import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './CodeBlock'
import type { Components } from 'react-markdown'

interface Props {
  content: string
}

const components: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '')
    const isInline = !match && !className

    if (isInline) {
      return (
        <code
          className="px-1.5 py-0.5 rounded bg-code-bg border border-code-border text-accent text-[13px] font-mono"
          {...props}
        >
          {children}
        </code>
      )
    }

    return (
      <CodeBlock
        code={String(children).replace(/\n$/, '')}
        language={match?.[1]}
      />
    )
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-link hover:underline"
      >
        {children}
      </a>
    )
  },
  table({ children }) {
    return (
      <div className="my-3 overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">{children}</table>
      </div>
    )
  },
  thead({ children }) {
    return <thead className="bg-surface-hover/50 text-text-secondary">{children}</thead>
  },
  th({ children }) {
    return <th className="px-3 py-2 text-left font-medium border-b border-border">{children}</th>
  },
  td({ children }) {
    return <td className="px-3 py-2 border-b border-border/50">{children}</td>
  },
  blockquote({ children }) {
    return (
      <blockquote className="my-3 border-l-3 border-accent/40 pl-4 text-text-secondary italic">
        {children}
      </blockquote>
    )
  },
  hr() {
    return <hr className="my-6 border-border" />
  },
  ul({ children }) {
    return <ul className="my-2 ml-5 list-disc space-y-1">{children}</ul>
  },
  ol({ children }) {
    return <ol className="my-2 ml-5 list-decimal space-y-1">{children}</ol>
  },
  li({ children }) {
    return <li className="text-text-primary leading-relaxed">{children}</li>
  },
  h1({ children }) {
    return <h1 className="text-xl font-semibold mt-6 mb-3 text-text-primary">{children}</h1>
  },
  h2({ children }) {
    return <h2 className="text-lg font-semibold mt-5 mb-2 text-text-primary">{children}</h2>
  },
  h3({ children }) {
    return <h3 className="text-base font-semibold mt-4 mb-2 text-text-primary">{children}</h3>
  },
  p({ children }) {
    return <p className="my-2 text-sm leading-relaxed text-text-primary">{children}</p>
  },
  img({ src, alt }) {
    return (
      <img
        src={src}
        alt={alt}
        className="my-3 rounded-lg max-w-full max-h-96 object-contain"
      />
    )
  },
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <div className="prose-emily">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
