import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, SkillPackVersionRecord } from '../api/client'
import { cn } from '../lib/utils'
import SkillPackEditor from './SkillPackEditor'
import { Button } from './ui/button'
import { Card, CardContent } from './ui/card'

interface Props {
  packId: string
  packName: string
}

export default function VersionHistory({ packId, packName }: Props) {
  const [selected, setSelected] = useState<SkillPackVersionRecord | null>(null)

  const { data: versions = [], isLoading, error } = useQuery({
    queryKey: ['skill-pack-versions', packId],
    queryFn: () => api.skillPacks.versions(packId),
  })

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Version History — {packName}</h2>

      <div className="flex gap-6">
        {/* Timeline list */}
        <div className="w-64 flex-shrink-0">
          {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
          {error && <p className="text-destructive text-sm">Failed to load versions.</p>}
          {!isLoading && versions.length === 0 && (
            <p className="text-muted-foreground text-sm">No versions found.</p>
          )}
          <ul className="space-y-2">
            {versions.map((v) => (
              <li key={v.version_number}>
                <Button
                  variant="outline"
                  onClick={() => setSelected(v)}
                  className={cn(
                    'w-full justify-start h-auto py-2 px-3 text-left',
                    selected?.version_number === v.version_number && 'border-primary bg-primary/5'
                  )}
                >
                  <div>
                    <div className="font-medium text-sm">v{v.version_number}</div>
                    <div className="text-muted-foreground text-xs">
                      {new Date(v.created_at).toLocaleString()}
                    </div>
                    {v.change_summary && (
                      <div className="text-muted-foreground text-xs mt-0.5 truncate">{v.change_summary}</div>
                    )}
                  </div>
                </Button>
              </li>
            ))}
          </ul>
        </div>

        {/* Read-only editor panel */}
        <div className="flex-1">
          {selected ? (
            <div>
              <Card className="mb-3">
                <CardContent className="py-3 px-4 flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">v{selected.version_number}</span>
                  <span className="text-muted-foreground text-sm">·</span>
                  <span className="text-muted-foreground text-sm">
                    {new Date(selected.created_at).toLocaleString()}
                  </span>
                  {selected.change_summary && (
                    <>
                      <span className="text-muted-foreground text-sm">·</span>
                      <span className="text-muted-foreground text-sm">{selected.change_summary}</span>
                    </>
                  )}
                </CardContent>
              </Card>
              <SkillPackEditor
                initialContent={selected.yaml_content}
                readOnly={true}
              />
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 text-muted-foreground text-sm border border-dashed border-border rounded">
              Select a version to view its content
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
