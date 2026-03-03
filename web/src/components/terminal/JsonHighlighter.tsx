interface Props {
  text: string
}

export function JsonHighlighter({ text }: Props) {
  // Try to detect and highlight JSON
  try {
    JSON.parse(text)
    // It's valid JSON — highlight it
    return <pre className="whitespace-pre-wrap">{highlightJson(text)}</pre>
  } catch {
    return <span>{text}</span>
  }
}

function highlightJson(json: string): JSX.Element[] {
  const elements: JSX.Element[] = []
  let i = 0

  const regex = /("(?:[^"\\]|\\.)*")\s*:/g
  const valueRegex = /:\s*("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g
  const stringRegex = /("(?:[^"\\]|\\.)*")/g

  // Simple line-by-line coloring
  const lines = json.split('\n')
  for (const [li, line] of lines.entries()) {
    const colored = line
      .replace(/"([^"\\]|\\.)*"\s*:/g, (match) => `\x01KEY${match}\x01END`)
      .replace(/:\s*("(?:[^"\\]|\\.)*")/g, (match, val) => `: \x01STR${val}\x01END`)
      .replace(/:\s*(true|false)/g, (_, val) => `: \x01BOOL${val}\x01END`)
      .replace(/:\s*(null)/g, (_, val) => `: \x01NULL${val}\x01END`)
      .replace(/:\s*(-?\d+(?:\.\d+)?)/g, (_, val) => `: \x01NUM${val}\x01END`)

    const parts = colored.split(/\x01(KEY|STR|BOOL|NULL|NUM|END)/g)
    let mode = ''

    elements.push(
      <span key={li}>
        {parts.map((part, pi) => {
          if (['KEY', 'STR', 'BOOL', 'NULL', 'NUM'].includes(part)) { mode = part; return null }
          if (part === 'END') { mode = ''; return null }
          const cls = mode === 'KEY' ? 'text-phase-analyzing' :
                     mode === 'STR' ? 'text-cost-green' :
                     mode === 'BOOL' ? 'text-warning-amber' :
                     mode === 'NULL' ? 'text-text-muted' :
                     mode === 'NUM' ? 'text-phase-comparing' : ''
          return <span key={pi} className={cls}>{part}</span>
        })}
        {li < lines.length - 1 && '\n'}
      </span>
    )
  }

  return elements
}
