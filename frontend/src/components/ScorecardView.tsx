import { useState } from 'react'
import type { ReportContent, ReportDetail } from '../api/client'
import { Badge } from './ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function scoreColor(score: number): string {
  if (score <= 2) return 'bg-red-500'
  if (score === 3) return 'bg-yellow-500'
  return 'bg-green-500'
}

function scoreBgText(score: number): string {
  if (score <= 2) return 'text-red-700 bg-red-100'
  if (score === 3) return 'text-yellow-700 bg-yellow-100'
  return 'text-green-700 bg-green-100'
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// ---------------------------------------------------------------------------
// Score bar (replaces shadcn Progress — not installed)
// ---------------------------------------------------------------------------

function ScoreBar({ score }: { score: number }) {
  const pct = (score / 5) * 100
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${scoreColor(score)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${scoreBgText(score)}`}>
        {score}/5
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Accordion item (replaces shadcn Accordion — not installed)
// ---------------------------------------------------------------------------

function AccordionItem({
  title,
  score,
  children,
}: {
  title: string
  score: number | null
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border rounded-md">
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-medium hover:bg-muted/50 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{title}</span>
        <div className="flex items-center gap-2">
          {score != null && (
            <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${scoreBgText(score)}`}>
              {score}/5
            </span>
          )}
          <span className="text-muted-foreground">{open ? '▲' : '▼'}</span>
        </div>
      </button>
      {open && <div className="px-4 pb-4 text-sm text-muted-foreground">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Template-specific layouts
// ---------------------------------------------------------------------------

function ScorecardLayout({ content }: { content: ReportContent }) {
  const scores = content.scores ?? []
  const competencySummary = content.competency_summary ?? {}

  return (
    <div className="space-y-6">
      {/* Hire/no-hire badge */}
      {content.recommendation && (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Recommendation:</span>
          <Badge
            className={
              content.recommendation.toLowerCase().includes('hire')
                ? 'bg-green-100 text-green-800 border-transparent text-sm px-3 py-1'
                : 'bg-red-100 text-red-800 border-transparent text-sm px-3 py-1'
            }
          >
            {content.recommendation}
          </Badge>
        </div>
      )}

      {/* Competency summary */}
      {Object.keys(competencySummary).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Competency Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(competencySummary).map(([competency, avg]) => (
              <div key={competency}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium capitalize">{competency}</span>
                  <span className="text-muted-foreground">{avg.toFixed(1)}</span>
                </div>
                <ScoreBar score={Math.round(avg)} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Per-question scores */}
      {scores.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Per-Question Scores</h3>
          {scores.map((qs) => (
            <AccordionItem
              key={qs.question_id}
              title={qs.question_text}
              score={qs.score}
            >
              <p className="mb-1">
                <span className="font-medium text-foreground">Competency:</span>{' '}
                {qs.competency}
              </p>
              {qs.skipped && (
                <Badge className="mb-2 bg-orange-100 text-orange-800 border-transparent">
                  Skipped
                </Badge>
              )}
              <p>{qs.score_rationale}</p>
            </AccordionItem>
          ))}
        </div>
      )}
    </div>
  )
}

// Keys already shown in the metadata card — skip in GenericLayout
const METADATA_KEYS = new Set([
  'session_id', 'skill_pack_id', 'skill_pack_name', 'template',
  'generated_at', 'duration_minutes', 'include_transcript',
])

function TranscriptBlock({ turns }: { turns: { speaker: string; text: string; timestamp_ms?: number }[] }) {
  const nonEmpty = turns.filter((t) => t.text?.trim())
  if (nonEmpty.length === 0) return <p className="text-xs text-muted-foreground italic">No transcript available.</p>
  return (
    <div className="space-y-2">
      {nonEmpty.map((t, i) => (
        <div key={i} className={`flex gap-2 ${t.speaker === 'agent' ? 'flex-row-reverse' : ''}`}>
          <span className={`text-[10px] font-semibold shrink-0 mt-0.5 uppercase tracking-wide ${
            t.speaker === 'agent' ? 'text-violet-600' : 'text-blue-600'
          }`}>
            {t.speaker === 'agent' ? 'Vero' : 'Candidate'}
          </span>
          <p className={`text-xs rounded-lg px-3 py-2 max-w-[80%] leading-relaxed ${
            t.speaker === 'agent'
              ? 'bg-violet-50 text-violet-900 ml-auto'
              : 'bg-blue-50 text-blue-900'
          }`}>
            {t.text}
          </p>
        </div>
      ))}
    </div>
  )
}

function GenericLayout({ content }: { content: ReportContent }) {
  // Render scores + competency summary the same way as ScorecardLayout when present
  const scores = content.scores ?? []
  const competencySummary = content.competency_summary ?? {}

  return (
    <div className="space-y-6">
      {/* Recommendation (if present) */}
      {content.recommendation && (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Recommendation:</span>
          <Badge className={
            content.recommendation.toLowerCase().includes('hire')
              ? 'bg-green-100 text-green-800 border-transparent text-sm px-3 py-1'
              : 'bg-red-100 text-red-800 border-transparent text-sm px-3 py-1'
          }>
            {content.recommendation}
          </Badge>
        </div>
      )}

      {/* Competency summary */}
      {Object.keys(competencySummary).length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Competency Summary</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(competencySummary).map(([competency, avg]) => (
              <div key={competency}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium capitalize">{competency}</span>
                  <span className="text-muted-foreground">{(avg as number).toFixed(1)}</span>
                </div>
                <ScoreBar score={Math.round(avg as number)} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Per-question scores */}
      {scores.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Per-Question Scores</h3>
          {scores.map((qs) => (
            <AccordionItem key={qs.question_id} title={qs.question_text} score={qs.score}>
              <p className="mb-1"><span className="font-medium text-foreground">Competency:</span>{' '}{qs.competency}</p>
              {qs.skipped && <Badge className="mb-2 bg-orange-100 text-orange-800 border-transparent">Skipped</Badge>}
              <p>{qs.score_rationale}</p>
            </AccordionItem>
          ))}
        </div>
      )}

      {/* All other fields */}
      {Object.entries(content).map(([key, value]) => {
        if (METADATA_KEYS.has(key)) return null
        if (key === 'scores' || key === 'competency_summary' || key === 'recommendation') return null
        if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return null
        if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) return null

        const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

        // Transcript array
        if (key === 'transcript' && Array.isArray(value)) {
          return (
            <div key={key}>
              <h3 className="text-sm font-semibold mb-2">{label}</h3>
              <TranscriptBlock turns={value} />
            </div>
          )
        }

        // Array of strings or simple items
        if (Array.isArray(value)) {
          return (
            <div key={key}>
              <h3 className="text-sm font-semibold mb-1">{label}</h3>
              <ul className="list-disc list-inside space-y-1">
                {value.map((item, i) => (
                  <li key={i} className="text-sm text-muted-foreground">
                    {typeof item === 'string' ? item : JSON.stringify(item)}
                  </li>
                ))}
              </ul>
            </div>
          )
        }

        // Plain string
        if (typeof value === 'string') {
          return (
            <div key={key}>
              <h3 className="text-sm font-semibold mb-1">{label}</h3>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{value}</p>
            </div>
          )
        }

        // Number / boolean
        if (typeof value === 'number' || typeof value === 'boolean') {
          return (
            <div key={key} className="flex gap-2 items-baseline">
              <span className="text-sm font-semibold">{label}:</span>
              <span className="text-sm text-muted-foreground">{String(value)}</span>
            </div>
          )
        }

        // Object — render key/value pairs
        return (
          <div key={key}>
            <h3 className="text-sm font-semibold mb-2">{label}</h3>
            <div className="space-y-1 pl-2 border-l-2 border-muted">
              {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                <div key={k} className="flex gap-2 text-sm">
                  <span className="font-medium capitalize text-foreground min-w-[120px]">{k.replace(/_/g, ' ')}</span>
                  <span className="text-muted-foreground">{typeof v === 'string' ? v : JSON.stringify(v)}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main ScorecardView
// ---------------------------------------------------------------------------

interface ScorecardViewProps {
  report: ReportDetail
  onViewTranscript?: () => void
}

export default function ScorecardView({ report, onViewTranscript }: ScorecardViewProps) {
  const content = report.content

  return (
    <div className="space-y-6">
      {/* Session metadata card */}
      <Card>
        <CardContent className="pt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-muted-foreground">Skill Pack</span>
            <p className="font-medium">{content.skill_pack_name ?? '—'}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Template</span>
            <p className="font-medium capitalize">{report.template}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Generated</span>
            <p className="font-medium">{formatDate(report.generated_at)}</p>
          </div>
          {content.duration_minutes != null && (
            <div>
              <span className="text-muted-foreground">Duration</span>
              <p className="font-medium">{content.duration_minutes.toFixed(1)} min</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Template-specific content */}
      {report.template === 'scorecard' ? (
        <ScorecardLayout content={content} />
      ) : (
        <GenericLayout content={content} />
      )}

      {/* View Transcript button */}
      {onViewTranscript && (
        <button
          className="text-sm text-primary underline-offset-4 hover:underline"
          onClick={onViewTranscript}
        >
          View Transcript
        </button>
      )}
    </div>
  )
}
