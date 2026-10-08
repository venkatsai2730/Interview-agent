import { useQuery } from '@tanstack/react-query'
import { Bot, Brain, Database, Radio, Smartphone } from 'lucide-react'
import { api } from '../api/client'

const DEPS = [
  { key: 'db', label: 'PostgreSQL', icon: <Database size={15} />, iconBg: 'bg-blue-100 text-blue-600' },
  { key: 'recall', label: 'Recall.ai', icon: <Bot size={15} />, iconBg: 'bg-violet-100 text-violet-600' },
  { key: 'livekit', label: 'LiveKit', icon: <Radio size={15} />, iconBg: 'bg-primary/10 text-primary' },
  { key: 'twilio', label: 'Twilio', icon: <Smartphone size={15} />, iconBg: 'bg-orange-100 text-orange-600' },
  { key: 'sarvam', label: 'Sarvam AI', icon: <Brain size={15} />, iconBg: 'bg-teal-100 text-teal-600' },
]

const STATUS_CONFIG = {
  ok: { dot: 'bg-emerald-500', text: 'text-emerald-700', label: 'Operational', cardBorder: 'border-emerald-100' },
  degraded: { dot: 'bg-amber-400', text: 'text-amber-700', label: 'Degraded', cardBorder: 'border-amber-100' },
  down: { dot: 'bg-red-500', text: 'text-red-700', label: 'Down', cardBorder: 'border-red-100' },
  loading: { dot: 'bg-gray-300 animate-pulse', text: 'text-muted-foreground', label: '…', cardBorder: 'border-border' },
  unknown: { dot: 'bg-gray-300', text: 'text-muted-foreground', label: 'Unknown', cardBorder: 'border-border' },
}

export default function HealthPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.health.get(),
    refetchInterval: 30_000,
  })

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {DEPS.map(({ key, label, icon, iconBg }) => {
        const dep = data?.dependencies?.[key as keyof typeof data.dependencies]
        const statusKey = dep?.status ?? (isLoading ? 'loading' : 'unknown')
        const cfg = STATUS_CONFIG[statusKey as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.unknown

        return (
          <div key={key} className={`rounded-lg border ${cfg.cardBorder} bg-card p-4 flex flex-col gap-3`}>
            <div className="flex items-center justify-between">
              <div className={`w-8 h-8 rounded-lg ${iconBg} flex items-center justify-center`}>
                {icon}
              </div>
              <span className={`w-2 h-2 rounded-full ${cfg.dot} ${statusKey === 'loading' ? 'animate-pulse' : ''}`} />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">{label}</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <p className={`text-xs font-medium ${cfg.text}`}>{cfg.label}</p>
                {dep?.latency_ms != null && (
                  <p className="text-xs text-muted-foreground">· {dep.latency_ms}ms</p>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
