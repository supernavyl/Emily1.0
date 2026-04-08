import { createMemo } from 'solid-js'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkRehype from 'remark-rehype'
import rehypeStringify from 'rehype-stringify'
import DOMPurify from 'dompurify'

interface Props {
  content: string
}

const processor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeStringify, { allowDangerousHtml: true })

export function MarkdownRenderer(props: Props) {
  const html = createMemo(() => {
    const content = props.content
    if (!content) return ''
    const result = processor.processSync(content)
    return DOMPurify.sanitize(String(result))
  })

  return <div class="prose-emily" innerHTML={html()} />
}
