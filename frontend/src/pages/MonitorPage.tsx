import { useQuery } from '@tanstack/react-query'
import { Activity, Gauge, Hash, Zap } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import EventLog from '../components/EventLog'
import HealthPanel from '../components/HealthPanel'
import LatencyChart from '../components/LatencyChart'
import { Card, CardContent } from '../components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'

export default function MonitorPage() {
  const [selectedSessionId, setSelectedSessionId] = useState('')

  const { data: sessionsData } = useQuery({
    queryKey: ['sessions', 'completed'],
    queryFn: () => api.sessions.list({ status: 'completed', page_size: 100 }),
  })

  const { data: sessionDetail } = useQuery({
    queryKey: ['session', selectedSessionId],
    queryFn: () => api.sessions.get(selectedSessionId),
    enabled: !!selectedSessionId,
  })

  const completedSessions = sessionsData?.items ?? []

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b px-8 py-5 bg-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
              <Activity size={16} className="text-emerald-600" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">Monitor</h1>
              <p className="text-muted-foreground text-sm">Dependency health and pipeline latency.</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {/* Live indicator */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Auto-refreshing
            </div>
            <Select value={selectedSessionId} onValueChange={setSelectedSessionId}>
              <SelectTrigger className="w-56 h-9 text-sm">
                <SelectValue placeholder="Select a session…" />
              </SelectTrigger>
              <SelectContent>
                {completedSessions.map((s) => (
                  <SelectItem key={s.session_id} value={s.session_id}>
                    {s.session_id.slice(5, 13)} — {s.skill_pack_name ?? 'Unknown'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8 space-y-8">
        {/* Dependency Health */}
        <section className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Dependency Health</h2>
          <HealthPanel />
        </section>

        {/* Session Stats */}
        {selectedSessionId && sessionDetail && (
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Session — {selectedSessionId.slice(5, 13)}
            </h2>
            <div className="grid grid-cols-3 gap-3">
              <Card className="border-blue-100">
                <CardContent className="p-4 flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center shrink-0">
                    <Zap size={15} className="text-blue-600" />
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Turn latency p50</div>
                    <div className="text-xl font-semibold tabular-nums text-blue-700">{sessionDetail.p50_latency_ms ?? '—'}<span className="text-sm font-normal text-muted-foreground ml-0.5">ms</span></div>
                  </div>
                </CardContent>
              </Card>
              <Card className="border-violet-100">
                <CardContent className="p-4 flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center shrink-0">
                    <Gauge size={15} className="text-violet-600" />
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Turn latency p90</div>
                    <div className="text-xl font-semibold tabular-nums text-violet-700">{sessionDetail.p90_latency_ms ?? '—'}<span className="text-sm font-normal text-muted-foreground ml-0.5">ms</span></div>
                  </div>
                </CardContent>
              </Card>
              <Card className="border-teal-100">
                <CardContent className="p-4 flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-teal-100 flex items-center justify-center shrink-0">
                    <Hash size={15} className="text-teal-600" />
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Total turns</div>
                    <div className="text-xl font-semibold tabular-nums text-teal-700">{sessionDetail.turn_count ?? '—'}</div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </section>
        )}

        {/* Turn Latency */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Turn Latency</h2>
            {sessionDetail && (
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-sm bg-primary" />
                  p50 {sessionDetail.p50_latency_ms ?? '—'}ms
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-sm bg-blue-300" />
                  p90 {sessionDetail.p90_latency_ms ?? '—'}ms
                </span>
              </div>
            )}
          </div>
          <LatencyChart
            turnLatencies={sessionDetail?.turn_latencies ?? []}
            p50={sessionDetail?.p50_latency_ms ?? null}
            p90={sessionDetail?.p90_latency_ms ?? null}
          />
        </section>

        {/* Pipeline Events */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Pipeline Events</h2>
            <span className="text-xs text-muted-foreground">
              <Activity className="w-3 h-3 inline mr-1" />
              Live
            </span>
          </div>
          <EventLog sessionId={selectedSessionId || undefined} />
        </section>
      </div>
    </div>
  )
}
