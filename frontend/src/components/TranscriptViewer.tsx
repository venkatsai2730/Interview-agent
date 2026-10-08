import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api, type TurnRecord } from '../api/client'
import { Badge } from './ui/badge'
import { Button } from './ui/button'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const FLAG_STYLES: Record<string, string> = {
  incomplete: 'bg-yellow-100 text-yellow-800 border-transparent',
  off_topic: 'bg-orange-100 text-orange-800 border-transparent',
  strong_signal: 'bg-green-100 text-green-800 border-transparent',
  redirect_needed: 'bg-red-100 text-red-800 border-transparent',
}

function scoreBgText(score: number): string {
  if (score <= 2) return 'text-red-700 bg-red-100 border-transparent'
  if (score === 3) return 'text-yellow-700 bg-yellow-100 border-transparent'
  return 'text-green-700 bg-green-100 border-transparent'
}

/** Format milliseconds offset from session start as HH:MM:SS */
function formatOffset(ms: number | null, startMs: number | null): string {
  if (ms == null || startMs == null) return ''
  const diff = Math.max(0, ms - startMs)
  const totalSec = Math.floor(diff / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':')
}

// ---------------------------------------------------------------------------
// Collapsible score rationale
// ---------------------------------------------------------------------------

function Collapsible({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-1">
      <button
        className="text-xs text-muted-foreground underline-offset-2 hover:underline"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? '▲ Hide' : '▼'} {label}
      </button>
      {open && <div className="mt-1 text-xs text-muted-foreground italic">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Single turn card
// ---------------------------------------------------------------------------

function TurnCard({ turn, startMs }: { turn: TurnRecord; startMs: number | null }) {
  // Phone channel stores speaker as 'agent'; Teams channel stores as 'vero' or agent name
  const isVero = turn.speaker?.toLowerCase() === 'vero' || turn.speaker?.toLowerCase() === 'agent'
  const speakerLabel = isVero ? 'Vero' : 'Candidate'

  return (
    <div className={`flex gap-3 ${isVero ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar dot */}
      <div className={`mt-1 flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold ${
        isVero ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
      }`}>
        {speakerLabel[0]}
      </div>

      <div className={`flex flex-col gap-1 max-w-[80%] ${isVero ? 'items-end' : 'items-start'}`}>
        {/* Meta row */}
        <div className={`flex items-center gap-2 flex-wrap ${isVero ? 'flex-row-reverse' : ''}`}>
          <span className={`text-xs font-semibold ${isVero ? 'text-primary' : 'text-foreground'}`}>
            {speakerLabel}
          </span>
          {turn.timestamp_ms != null && startMs != null && (
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {formatOffset(turn.timestamp_ms, startMs)}
            </span>
          )}
          {turn.score != null && (
            <Badge className={`text-[11px] px-1.5 py-0 ${scoreBgText(turn.score)}`}>
              {turn.score}/5
            </Badge>
          )}
          {(turn.flags ?? []).map((flag) => (
            <Badge key={flag} className={`text-[11px] px-1.5 py-0 ${FLAG_STYLES[flag] ?? 'border-transparent bg-secondary text-secondary-foreground'}`}>
              {flag.replace(/_/g, ' ')}
            </Badge>
          ))}
        </div>

        {/* Bubble */}
        <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
          isVero
            ? 'bg-primary/8 text-foreground rounded-tr-sm'
            : 'bg-muted/70 text-foreground rounded-tl-sm'
        }`}>
          {turn.transcript}
        </div>

        {/* Collapsible score rationale */}
        {turn.score_rationale && (
          <Collapsible label="Score rationale">
            {turn.score_rationale}
          </Collapsible>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sidebar question list
// ---------------------------------------------------------------------------

interface Question {
  id: string
  text: string
}

function extractQuestions(turns: TurnRecord[]): Question[] {
  const seen = new Set<string>()
  const questions: Question[] = []
  for (const t of turns) {
    if (t.question_id && !seen.has(t.question_id)) {
      seen.add(t.question_id)
      questions.push({ id: t.question_id, text: t.question_id })
    }
  }
  return questions
}

interface SidebarProps {
  questions: Question[]
  activeId: string | null
  onSelect: (id: string) => void
}

function QuestionSidebar({ questions, activeId, onSelect }: SidebarProps) {
  if (questions.length === 0) return null
  return (
    <div className="w-56 shrink-0 border-r overflow-y-auto pr-2 space-y-1">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 px-2">
        Questions
      </p>
      {questions.map((q, i) => (
        <Button
          key={q.id}
          variant="ghost"
          size="sm"
          className={`w-full justify-start text-left h-auto py-2 px-2 whitespace-normal leading-snug ${
            activeId === q.id ? 'bg-secondary text-secondary-foreground' : ''
          }`}
          onClick={() => onSelect(q.id)}
        >
          <span className="mr-1 text-muted-foreground text-xs">{i + 1}.</span>
          <span className="text-xs line-clamp-3">{q.text}</span>
          {activeId === q.id && (
            <Badge variant="secondary" className="ml-auto shrink-0 text-xs">
              ●
            </Badge>
          )}
        </Button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main TranscriptViewer
// ---------------------------------------------------------------------------

interface TranscriptViewerProps {
  /** When provided, fetches its own data via TanStack Query */
  sessionId?: string
  /** When provided directly (legacy / from ReportDetailPage) */
  turns?: TurnRecord[]
  /** When true, polls for new turns every 3s and auto-scrolls to bottom */
  isLive?: boolean
}

export default function TranscriptViewer({ sessionId, turns: turnsProp, isLive }: TranscriptViewerProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['transcript', sessionId],
    queryFn: () => api.reports.getTranscript(sessionId!),
    enabled: !!sessionId && !turnsProp,
    refetchInterval: isLive ? 3000 : false,
  })

  const turns = turnsProp ?? data?.turns ?? []
  const startMs = turns.find((t) => t.timestamp_ms != null)?.timestamp_ms ?? null

  const questions = extractQuestions(turns)
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null)

  // Refs keyed by question_id for the first turn of each question
  const questionRefs = useRef<Record<string, HTMLDivElement | null>>({})

  // Auto-scroll to bottom when new turns arrive in live mode
  useEffect(() => {
    if (isLive && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [isLive, turns.length])

  function scrollToQuestion(qid: string) {
    setActiveQuestion(qid)
    questionRefs.current[qid]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // Track active question based on scroll position
  useEffect(() => {
    if (questions.length === 0) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const qid = entry.target.getAttribute('data-question-id')
            if (qid) setActiveQuestion(qid)
          }
        }
      },
      { threshold: 0.5 }
    )
    for (const el of Object.values(questionRefs.current)) {
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [turns, questions.length])

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading transcript…</p>
  if (isError) return <p className="text-sm text-destructive">Failed to load transcript.</p>
  if (turns.length === 0) return (
    <p className="text-sm text-muted-foreground">
      {isLive ? (
        <span className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />
          Waiting for conversation to start…
        </span>
      ) : 'No transcript available.'}
    </p>
  )

  // Track which question_ids have had their ref assigned already
  const assignedRefs = new Set<string>()

  return (
    <div className="flex gap-4 h-full min-h-0">
      {/* Left sidebar */}
      <QuestionSidebar
        questions={questions}
        activeId={activeQuestion}
        onSelect={scrollToQuestion}
      />

      {/* Right turn list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-4 pr-2">
        {turns.map((turn) => {
          const isFirstForQuestion =
            turn.question_id != null && !assignedRefs.has(turn.question_id)
          if (isFirstForQuestion) assignedRefs.add(turn.question_id!)

          return (
            <div
              key={turn.turn_index}
              ref={
                isFirstForQuestion
                  ? (el) => {
                      questionRefs.current[turn.question_id!] = el
                    }
                  : undefined
              }
              data-question-id={isFirstForQuestion ? turn.question_id : undefined}
            >
              <TurnCard turn={turn} startMs={startMs} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
