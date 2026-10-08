import { useState } from 'react'
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom'
import DocsPage from './pages/DocsPage'
import LandingPage from './pages/LandingPage'
import MonitorPage from './pages/MonitorPage'
import ReportDetailPage from './pages/ReportDetailPage'
import ReportsPage from './pages/ReportsPage'
import SessionsHistoryPage from './pages/SessionsHistoryPage'
import SessionsPage from './pages/SessionsPage'
import SkillPacksPage from './pages/SkillPacksPage'
import { Activity, BookOpen, ChevronLeft, ChevronRight, Clock, FileText, Layers, Play } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/sessions', label: 'Sessions', icon: <Play size={16} />, color: 'text-primary' },
  { to: '/sessions-history', label: 'History', icon: <Clock size={16} />, color: 'text-violet-600' },
  { to: '/skill-packs', label: 'Skill Packs', icon: <Layers size={16} />, color: 'text-amber-600' },
  { to: '/reports', label: 'Reports', icon: <FileText size={16} />, color: 'text-teal-600' },
  { to: '/monitor', label: 'Monitor', icon: <Activity size={16} />, color: 'text-emerald-600' },
  { to: '/docs', label: 'Docs', icon: <BookOpen size={16} />, color: 'text-orange-600' },
]

function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { pathname } = useLocation()
  const isActive = (to: string) => pathname === to || pathname.startsWith(to + '/')

  return (
    <aside className={[
      'flex flex-col border-r bg-card transition-all duration-200 shrink-0',
      collapsed ? 'w-14' : 'w-52',
    ].join(' ')}>
      {/* Logo */}
      <div className="h-14 flex items-center px-3 border-b gap-2.5 shrink-0">
        <Link to="/" className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shrink-0 shadow-sm">
            <span className="text-primary-foreground text-xs font-bold">V</span>
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <span className="font-bold text-sm tracking-tight truncate text-foreground">Vero</span>
              <span className="block text-[10px] text-muted-foreground leading-none">AI Interviewer</span>
            </div>
          )}
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon, color }) => {
          const active = isActive(to)
          return (
            <Link
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              className={[
                'relative flex items-center gap-2.5 px-2 py-2 rounded-md text-sm font-medium transition-all duration-150',
                active
                  ? 'bg-primary/10 text-primary'
                  : `text-muted-foreground hover:text-foreground hover:bg-muted`,
              ].join(' ')}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-primary rounded-full" />
              )}
              <span className={`shrink-0 ${active ? 'text-primary' : color}`}>{icon}</span>
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="h-10 flex items-center justify-center border-t text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
    </aside>
  )
}

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="h-screen flex overflow-hidden">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Routes>
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/sessions-history" element={<SessionsHistoryPage />} />
          <Route path="/skill-packs" element={<SkillPacksPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/reports/:sessionId" element={<ReportDetailPage />} />
          <Route path="/monitor" element={<MonitorPage />} />
          <Route path="/docs" element={<DocsPage />} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </BrowserRouter>
  )
}
