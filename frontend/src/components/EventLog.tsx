import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table'

interface EventLogProps {
  sessionId?: string
}

const TYPE_BADGE: Record<string, string> = {
  tts_fallback: 'bg-orange-100 text-orange-800',
  stt_reconnect: 'bg-blue-100 text-blue-800',
}

export default function EventLog({ sessionId: initialSessionId }: EventLogProps) {
  const [sessionFilter, setSessionFilter] = useState(initialSessionId ?? '')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 10

  const { data, isLoading } = useQuery({
    queryKey: ['events', sessionFilter, page],
    queryFn: () =>
      api.events.list({
        session_id: sessionFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Filter by session ID…"
          value={sessionFilter}
          onChange={(e) => { setSessionFilter(e.target.value); setPage(1) }}
          className="max-w-xs"
        />
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Type</TableHead>
            <TableHead>Session ID</TableHead>
            <TableHead>Timestamp</TableHead>
            <TableHead>Detail</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground">Loading…</TableCell>
            </TableRow>
          )}
          {!isLoading && (!data?.items.length) && (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-muted-foreground">No events found.</TableCell>
            </TableRow>
          )}
          {data?.items.map((ev) => (
            <TableRow key={ev.id}>
              <TableCell>
                <Badge className={TYPE_BADGE[ev.type] ?? 'bg-gray-100 text-gray-800'}>
                  {ev.type}
                </Badge>
              </TableCell>
              <TableCell className="font-mono text-xs">
                {ev.session_id ? ev.session_id.slice(0, 8) : '—'}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {new Date(ev.timestamp).toLocaleString()}
              </TableCell>
              <TableCell className="text-xs max-w-xs truncate">
                {ev.detail ? JSON.stringify(ev.detail) : '—'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>Page {page} of {totalPages}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Prev
          </Button>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
