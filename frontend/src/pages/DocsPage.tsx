import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent } from '../components/ui/card'
import { BookOpen, FileText, Code, Lightbulb } from 'lucide-react'

export default function DocsPage() {
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/skill.md', {
      headers: {
        'X-Requested-With': 'VeroFrontend'
      }
    })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load documentation')
        return res.text()
      })
      .then((text) => {
        setContent(text)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-muted-foreground">Loading documentation...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-destructive">Error: {error}</div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-auto bg-muted/30">
      {/* Header */}
      <div className="border-b bg-card px-8 py-5">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <BookOpen className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">Documentation</h1>
              <p className="text-muted-foreground text-sm">Skill Pack Guide & Reference</p>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Quick Links */}
          <div className="grid grid-cols-3 gap-4">
            <Card className="border-l-4 border-l-primary">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <FileText className="w-4 h-4 text-primary mt-0.5" />
                  <div>
                    <h3 className="font-medium text-sm">Quick Start</h3>
                    <p className="text-xs text-muted-foreground mt-1">Get started with minimal skill packs</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-l-4 border-l-emerald-500">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <Code className="w-4 h-4 text-emerald-500 mt-0.5" />
                  <div>
                    <h3 className="font-medium text-sm">Schema Reference</h3>
                    <p className="text-xs text-muted-foreground mt-1">Complete YAML schema documentation</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-l-4 border-l-amber-500">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <Lightbulb className="w-4 h-4 text-amber-500 mt-0.5" />
                  <div>
                    <h3 className="font-medium text-sm">AI Generation</h3>
                    <p className="text-xs text-muted-foreground mt-1">Generate skills from descriptions</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main Content */}
          <Card>
            <CardContent className="p-8">
              <div className="prose prose-slate max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    code({ node, inline, className, children, ...props }: {
                      node?: unknown
                      inline?: boolean
                      className?: string
                      children?: React.ReactNode
                    }) {
                      const match = /language-(\w+)/.exec(className || '')
                      return !inline && match ? (
                        <div className="rounded-lg overflow-hidden border my-4">
                          <div className="bg-muted px-4 py-2 text-xs font-medium text-muted-foreground border-b flex items-center justify-between">
                            <span>{match[1].toUpperCase()}</span>
                          </div>
                          <pre className="bg-muted/50 p-4 overflow-x-auto m-0">
                            <code className="text-sm font-mono text-foreground leading-relaxed">
                              {String(children).replace(/\n$/, '')}
                            </code>
                          </pre>
                        </div>
                      ) : (
                        <code
                          className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-primary"
                          {...props}
                        >
                          {children}
                        </code>
                      )
                    },
                    h1: ({ children }) => (
                      <h1 className="text-3xl font-bold text-foreground mb-6 pb-4 border-b">{children}</h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-xl font-semibold text-foreground mt-10 mb-4 flex items-center gap-2">
                        <span className="w-1 h-5 bg-primary rounded-full" />
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-lg font-medium text-foreground mt-6 mb-3">{children}</h3>
                    ),
                    p: ({ children }) => (
                      <p className="text-sm text-muted-foreground leading-relaxed mb-4">{children}</p>
                    ),
                    ul: ({ children }) => (
                      <ul className="space-y-2 mb-4 ml-4">{children}</ul>
                    ),
                    li: ({ children }) => (
                      <li className="text-sm text-muted-foreground flex items-start gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-primary/60 mt-2 shrink-0" />
                        {children}
                      </li>
                    ),
                    table: ({ children }) => (
                      <div className="rounded-lg border overflow-hidden my-4">
                        <table className="w-full text-sm">{children}</table>
                      </div>
                    ),
                    th: ({ children }) => (
                      <th className="bg-muted px-4 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td className="px-4 py-2 border-t text-muted-foreground">{children}</td>
                    ),
                    hr: () => <hr className="my-8 border-border" />,
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-4 border-primary/30 bg-primary/5 pl-4 py-2 my-4 rounded-r">
                        {children}
                      </blockquote>
                    ),
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
