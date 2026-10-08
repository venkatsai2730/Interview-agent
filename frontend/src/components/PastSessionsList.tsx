import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { CheckCircle2, FileText, Loader2, MessageSquare, Mic, Phone, Radio, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import RecordingPlayer from './RecordingPlayer'
import TranscriptViewer from './TranscriptViewer'
import { Button } from './ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table'

const PAGE_SIZE = 10
const STATUS_OPTIONS = ['ALL', 'ACTIVE', 'COMPLETED', 'FAILED'] as const
const LIVE_STATUSES = new Set(['active', 'joining', 'pending', 'closing', 'ACTIVE', 'JOINING', 'PENDING', 'CLOSING'])

const STATUS_CONFIG: Record<string, {
  label: string
  classes: string
  icon: React.ReactNode
}> = {
  ACTIVE:    {
    label: 'Active',
    classes: 'bg-blue-50 text-blue-700 border-blue-200',
    icon: <Radio size={11} className="animate-pulse" />,
  },
  COMPLETED: {
    label: 'Completed',
    classes: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    icon: <CheckCircle2 size={11} />,
  },
  FAILED:    {
    label: 'Failed',
    classes: 'bg-red-50 text-red-700 border-red-200',
    icon: <XCircle size={11} />,
  },
  JOINING:   {
    label: 'Joining',
    classes: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: <Loader2 size={11} className="animate-spin" />,
  },
  PENDING:   {
    label: 'Pending',
    classes: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: <Loader2 size={11} className="animate-spin" />,
  },
  CLOSING:   {
    label: 'Closing',
    classes: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: <Loader2 size={11} className="animate-spin" />,
  },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status.toUpperCase()]
  if (!cfg) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border bg-muted text-muted-foreground border-border">
        {status.toLowerCase()}
      </span>
    )
  }
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${cfg.classes}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  )
}

function formatDuration(minutes: number | null) {
  if (minutes == null) return '—'
  const m = Math.floor(minutes)
  const s = Math.round((minutes - m) * 60)
  return `${m}m ${s}s`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

export default function PastSessionsList() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [page, setPage] = useState(1)
  const [transcriptSessionId, setTranscriptSessionId] = useState<string | null>(null)
  const [recordingSession, setRecordingSession] = useState<{ id: string; channel: string | null; recallUrl: string | null; recordingUrl: string | null } | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['sessions', statusFilter, page],
    queryFn: () => api.sessions.list({
      status: statusFilter === 'ALL' ? undefined : statusFilter,
      page,
      page_size: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      return items.some((s) => LIVE_STATUSES.has(s.status)) ? 3000 : false
    },
  })

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">Status</span>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1) }}>
          <SelectTrigger className="w-36 h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
        {data && (
          <span className="text-xs text-muted-foreground ml-auto">{data.total} session{data.total !== 1 ? 's' : ''}</span>
        )}
      </div>

      {isLoading && (
        <div className="py-12 text-center text-sm text-muted-foreground">Loading sessions…</div>
      )}
      {isError && (
        <div className="py-12 text-center text-sm text-destructive">Failed to load sessions.</div>
      )}

      {data && (
        <>
          <div className="rounded-xl border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="w-28">ID</TableHead>
                  <TableHead>Skill Pack</TableHead>
                  <TableHead className="w-24">Channel</TableHead>
                  <TableHead className="w-28">Status</TableHead>
                  <TableHead className="w-36">Created</TableHead>
                  <TableHead className="w-24">Duration</TableHead>
                  <TableHead className="w-28 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground py-16">
                      No sessions found.
                    </TableCell>
                  </TableRow>
                ) : data.items.map((session) => (
                  <TableRow
                    key={session.session_id}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {session.session_id.slice(5, 13)}
                    </TableCell>
                    <TableCell className="font-medium text-sm">{session.skill_pack_name ?? '—'}</TableCell>
                    <TableCell>
                      {session.channel === 'phone' ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-orange-700 bg-orange-50 border border-orange-100 px-2 py-0.5 rounded-full">
                          <Phone size={11} /> Phone
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-violet-700 bg-violet-50 border border-violet-100 px-2 py-0.5 rounded-full">
                          <MessageSquare size={11} /> Teams
                        </span>
                      )}
                    </TableCell>
                    <TableCell><StatusBadge status={session.status} /></TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(session.created_at)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDuration(session.duration_minutes)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                        {session.has_report && (
                          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 text-teal-600 hover:text-teal-700 hover:bg-teal-50"
                            onClick={() => navigate(`/reports/${session.session_id}`)}>
                            <FileText size={11} /> Report
                          </Button>
                        )}
                        {LIVE_STATUSES.has(session.status) ? (
                          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                            onClick={() => setTranscriptSessionId(session.session_id)}>
                            <Radio size={11} className="animate-pulse" /> Live
                          </Button>
                        ) : !LIVE_STATUSES.has(session.status) && (
                          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 text-muted-foreground hover:text-foreground"
                            onClick={() => setTranscriptSessionId(session.session_id)}>
                            <MessageSquare size={11} /> Transcript
                          </Button>
                        )}
                        {session.status.toLowerCase() === 'completed' && (
                          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                            onClick={(e) => { e.stopPropagation(); setRecordingSession({ id: session.session_id, channel: session.channel, recallUrl: session.recall_recording_url, recordingUrl: session.recording_url }) }}>
                            <Mic size={11} /> Recording
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Page {page} of {totalPages || 1}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="h-8" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</Button>
              <Button variant="outline" size="sm" className="h-8" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next →</Button>
            </div>
          </div>
        </>
      )}

      <Sheet open={!!transcriptSessionId} onOpenChange={(v) => !v && setTranscriptSessionId(null)}>
        <SheetContent className="w-full sm:w-[780px] sm:max-w-[90vw] flex flex-col p-0">
          <SheetHeader className="px-6 py-5 border-b">
            <SheetTitle className="text-base">
              {transcriptSessionId && LIVE_STATUSES.has(
                data?.items.find(s => s.session_id === transcriptSessionId)?.status ?? ''
              ) ? (
                <span className="flex items-center gap-2">
                  Live Transcript
                  <span className="inline-flex items-center gap-1 text-xs font-normal text-blue-600">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                    live
                  </span>
                </span>
              ) : 'Session Transcript'}
            </SheetTitle>
          </SheetHeader>
          <div className="flex-1 min-h-0 overflow-hidden px-6 py-4">
            {transcriptSessionId && (
              <TranscriptViewer
                sessionId={transcriptSessionId}
                isLive={LIVE_STATUSES.has(
                  data?.items.find(s => s.session_id === transcriptSessionId)?.status ?? ''
                )}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={!!recordingSession} onOpenChange={(v) => { if (!v) setRecordingSession(null) }}>
        <SheetContent className="w-full sm:w-[780px] sm:max-w-[90vw] flex flex-col p-0">
          <SheetHeader className="px-6 py-5 border-b">
            <SheetTitle className="text-base flex items-center gap-2">
              <Mic size={15} className="text-orange-500" /> Session Recording
            </SheetTitle>
          </SheetHeader>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
            {recordingSession && (
              <RecordingPlayer
                sessionId={recordingSession.id}
                channel={recordingSession.channel}
                recallRecordingUrl={recordingSession.recallUrl}
                recordingUrl={recordingSession.recordingUrl}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
