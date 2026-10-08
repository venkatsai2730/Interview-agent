import {
    Bar,
    BarChart,
    CartesianGrid,
    ReferenceLine,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'

interface TurnLatency {
  turn_index: number
  latency_ms: number
}

interface LatencyChartProps {
  turnLatencies: TurnLatency[]
  p50: number | null
  p90: number | null
}

function calcPercentile(values: number[], p: number): number | null {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const rank = Math.min(Math.floor((sorted.length * p) / 100), sorted.length - 1)
  return sorted[rank]
}

export default function LatencyChart({ turnLatencies, p50, p90 }: LatencyChartProps) {
  const values = turnLatencies.map((t) => t.latency_ms)
  const computedP50 = p50 ?? calcPercentile(values, 50)
  const computedP90 = p90 ?? calcPercentile(values, 90)

  const data = turnLatencies.map((t) => ({
    turn: t.turn_index,
    latency: t.latency_ms,
    fill: t.latency_ms > 4000 ? '#ef4444' : '#6366f1',
  }))

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">p50 Latency</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {computedP50 != null ? `${computedP50} ms` : '—'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">p90 Latency</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {computedP90 != null ? `${computedP90} ms` : '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      {data.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">No latency data yet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="turn" label={{ value: 'Turn', position: 'insideBottom', offset: -2 }} />
            <YAxis unit=" ms" />
            <Tooltip formatter={(v: number) => [`${v} ms`, 'Latency']} />
            {computedP50 != null && (
              <ReferenceLine y={computedP50} stroke="#22c55e" strokeDasharray="4 2" label={{ value: 'p50', fill: '#22c55e', fontSize: 11 }} />
            )}
            {computedP90 != null && (
              <ReferenceLine y={computedP90} stroke="#f59e0b" strokeDasharray="4 2" label={{ value: 'p90', fill: '#f59e0b', fontSize: 11 }} />
            )}
            <Bar dataKey="latency" fill="#6366f1" isAnimationActive={false}
              shape={(props: any) => {
                const { x, y, width, height, latency } = props
                return <rect x={x} y={y} width={width} height={height} fill={latency > 4000 ? '#ef4444' : '#6366f1'} />
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
