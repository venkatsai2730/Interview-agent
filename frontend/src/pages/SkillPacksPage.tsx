import { Layers } from 'lucide-react'
import SkillPackLibrary from '../components/SkillPackLibrary'

export default function SkillPacksPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-8 py-5 bg-card">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center">
            <Layers size={16} className="text-amber-600" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Skill Packs</h1>
            <p className="text-muted-foreground text-sm">Manage agent personas, questions, and scoring rubrics.</p>
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-8">
        <SkillPackLibrary />
      </div>
    </div>
  )
}
