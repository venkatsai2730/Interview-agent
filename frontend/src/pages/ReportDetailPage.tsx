import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, MessageSquare } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import ScorecardView from '../components/ScorecardView'
import TranscriptViewer from '../components/TranscriptViewer'
import { Button } from '../components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../components/ui/sheet'

export default function ReportDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [transcriptOpen, setTranscriptOpen] = useState(false)

  const { data: report, isLoading, isError } = useQuery({
    queryKey: ['report', sessionId],
    queryFn: () => api.reports.get(sessionId!),
    enabled: !!sessionId,
  })

  const includeTranscript = !!(report?.content as Record<string, unknown> | undefined)?.include_transcript

  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-8 py-4 bg-card flex items-center gap-3">
        <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground hover:text-foreground -ml-2 h-8"
          onClick={() => navigate('/reports')}>
          <ArrowLeft size={13} /> Reports
        </Button>
        <span className="text-muted-foreground">/</span>
        <h1 className="text-base font-semibold tracking-tight">Report</h1>
        <span className="font-mono text-sm text-muted-foreground bg-muted px-2 py-0.5 rounded">{sessionId?.slice(5, 13)}</span>
        {report && (
          <Button size="sm" variant="outline" className="ml-auto gap-1.5 h-8 text-xs"
            onClick={() => setTranscriptOpen(true)}>
            <MessageSquare size={12} /> View Transcript
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-8 max-w-3xl">
        {isLoading && <div className="py-12 text-center text-sm text-muted-foreground">Loading report…</div>}
        {isError && <div className="py-12 text-center text-sm text-destructive">Failed to load report.</div>}
        {report && (
          <ScorecardView
            report={report}
            onViewTranscript={includeTranscript ? () => setTranscriptOpen(true) : undefined}
          />
        )}
      </div>

      <Sheet open={transcriptOpen} onOpenChange={(v) => !v && setTranscriptOpen(false)}>
        <SheetContent className="w-[560px] sm:w-[700px] flex flex-col">
          <SheetHeader>
            <SheetTitle>Session Transcript</SheetTitle>
          </SheetHeader>
          <div className="mt-4 flex-1 min-h-0">
            {sessionId && <TranscriptViewer sessionId={sessionId} />}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
