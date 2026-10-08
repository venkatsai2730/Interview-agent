import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowRight, FileText, MessageSquare, Phone } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const PAGE_SIZE = 10
const TEMPLATE_OPTIONS = ['ALL', 'scorecard', 'discovery-brief', 'audit-log', 'coaching-report'] as const
const CHANNEL_OPTIONS = ['ALL', 'teams', 'phone'] as const

const TEMPLATE_STYLES: Record<string, string> = {
  scorecard: 'bg-blue-50 text-blue-700 border-blue-200',
  'discovery-brief': 'bg-violet-50 text-violet-700 border-violet-200',
  'audit-log': 'bg-orange-50 text-orange-700 border-orange-200',
  'coaching-report': 'bg-teal-50 text-teal-700 border-teal-200',
}

const TEMPLATE_LABELS: Record<string, string> = {
  'ALL': 'All templates',
  'scorecard': 'Scorecard',
  'discovery-brief': 'Discovery brief',
  'audit-log': 'Audit log',
  'coaching-report': 'Coaching',
}

const CHANNEL_LABELS: Record<string, string> = {
  'ALL': 'All channels',
  'teams': 'Teams',
  'phone': 'Phone',
}

function TemplateBadge({ template }: { template: string }) {
  return (
    <Badge variant="outline" className={TEMPLATE_STYLES[template] ?? 'border-border'}>
      {template}
    </Badge>
  )
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

export default function ReportsPage() {
  const navigate = useNavigate()
  const [templateFilter, setTemplateFilter] = useState('ALL')
  const [channelFilter, setChannelFilter] = useState('ALL')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['reports', templateFilter, channelFilter, fromDate, toDate, page],
    queryFn: () => api.reports.list({
      template: templateFilter === 'ALL' ? undefined : templateFilter,
      channel: channelFilter === 'ALL' ? undefined : channelFilter,
      from_date: fromDate || undefined,
      to_date: toDate || undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
  })

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1

  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-8 py-5 bg-card">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-100 flex items-center justify-center">
            <FileText size={16} className="text-teal-600" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Reports</h1>
            <p className="text-muted-foreground text-sm">Post-session scorecards and summaries.</p>
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-8 space-y-6">
        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Template filters */}
          <div className="flex flex-wrap items-center gap-2">
            {TEMPLATE_OPTIONS.map((t) => (
              <button
                key={t}
                onClick={() => { setTemplateFilter(t); setPage(1) }}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                  templateFilter === t
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card text-muted-foreground border-border hover:bg-muted'
                }`}
              >
                {TEMPLATE_LABELS[t]}
              </button>
            ))}
          </div>
          
          {/* Channel filters */}
          <div className="flex flex-wrap items-center gap-2 border-l pl-3">
            {CHANNEL_OPTIONS.map((c) => (
              <button
                key={c}
                onClick={() => { setChannelFilter(c); setPage(1) }}
                className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                  channelFilter === c
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card text-muted-foreground border-border hover:bg-muted'
                }`}
              >
                {c === 'teams' && <MessageSquare size={10} />}
                {c === 'phone' && <Phone size={10} />}
                {CHANNEL_LABELS[c]}
              </button>
            ))}
          </div>
          
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm text-muted-foreground">From</span>
            <Input type="date" className="w-32 h-8 text-xs" value={fromDate}
              onChange={(e) => { setFromDate(e.target.value); setPage(1) }} />
            <span className="text-sm text-muted-foreground">to</span>
            <Input type="date" className="w-32 h-8 text-xs" value={toDate}
              onChange={(e) => { setToDate(e.target.value); setPage(1) }} />
          </div>
        </div>

        {isLoading && <div className="py-12 text-center text-sm text-muted-foreground">Loading reports…</div>}
        {isError && <div className="py-12 text-center text-sm text-destructive">Failed to load reports.</div>}

        {data && (
          <>
            <div className="rounded-xl border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40 hover:bg-muted/40">
                    <TableHead className="w-28">Session</TableHead>
                    <TableHead>Skill Pack</TableHead>
                    <TableHead className="w-32">Template</TableHead>
                    <TableHead className="w-36">Generated</TableHead>
                    <TableHead className="w-20 text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground py-12">No reports found.</TableCell>
                    </TableRow>
                  ) : data.items.map((report) => (
                    <TableRow key={report.session_id}
                      className="cursor-pointer hover:bg-muted/30 transition-colors"
                      onClick={() => navigate(`/reports/${report.session_id}`)}>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {report.session_id.slice(5, 13)}
                      </TableCell>
                      <TableCell className="font-medium text-sm">{report.skill_pack_name ?? '—'}</TableCell>
                      <TableCell><TemplateBadge template={report.template} /></TableCell>
                      <TableCell className="text-sm text-muted-foreground">{formatDate(report.generated_at)}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 text-primary hover:text-primary"
                          onClick={(e) => { e.stopPropagation(); navigate(`/reports/${report.session_id}`) }}>
                          View <ArrowRight size={11} />
                        </Button>
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
      </div>
    </div>
  )
}
