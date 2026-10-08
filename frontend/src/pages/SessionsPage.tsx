import { Zap } from 'lucide-react'
import SessionLauncher from '../components/SessionLauncher'

export default function SessionsPage() {
  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="border-b px-8 py-5 bg-card">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Zap size={16} className="text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">New Session</h1>
            <p className="text-muted-foreground text-sm">Launch an AI interviewer session.</p>
          </div>
        </div>
      </div>

      {/* Single-column layout for session launcher */}
      <div className="flex-1 overflow-y-auto p-6">
        <SessionLauncher />
      </div>
    </div>
  )
}
