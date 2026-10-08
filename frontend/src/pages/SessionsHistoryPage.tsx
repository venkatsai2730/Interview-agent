import { Clock, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import PastSessionsList from '../components/PastSessionsList'

export default function SessionsHistoryPage() {
  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="border-b px-8 py-5 bg-card flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center">
            <Clock size={16} className="text-violet-600" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Sessions History</h1>
            <p className="text-muted-foreground text-sm">View all sessions — active ones refresh automatically.</p>
          </div>
        </div>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-primary bg-primary/10 hover:bg-primary/15 px-3 py-1.5 rounded-lg transition-colors"
        >
          <Plus size={14} /> New Session
        </Link>
      </div>

      {/* Full-width sessions list */}
      <div className="flex-1 overflow-y-auto p-6">
        <PastSessionsList />
      </div>
    </div>
  )
}
