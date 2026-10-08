import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, SkillPackSummary } from '../api/client'
import SkillBuilder from './SkillBuilder'
import VersionHistory from './VersionHistory'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from './ui/alert-dialog'
import { Badge } from './ui/badge'
import { Button } from './ui/button'

type ViewState =
  | { type: 'list' }
  | { type: 'builder'; pack?: SkillPackSummary }
  | { type: 'history'; pack: SkillPackSummary }

// Helper to determine skill mode from YAML content
function getSkillMode(yamlContent: string): 'guided' | 'intelligent' | 'unknown' {
  // Check for mode: intelligent in sections
  if (yamlContent.includes('mode: intelligent')) return 'intelligent'
  // Check for mode: guided or default (no mode specified means guided)
  if (yamlContent.includes('mode: guided') || yamlContent.includes('questions:')) return 'guided'
  return 'unknown'
}

function SkillPackCard({
  pack,
  onEdit,
  onHistory,
  onActivate,
  onDeactivate,
  onDelete,
  onClone,
  activating,
  deactivating,
  cloning,
}: {
  pack: SkillPackSummary
  onEdit: () => void
  onHistory: () => void
  onActivate: () => void
  onDeactivate: () => void
  onDelete: () => void
  onClone: () => void
  activating: boolean
  deactivating: boolean
  cloning: boolean
}) {
  const mode = getSkillMode(pack.yaml_content)
  
  return (
    <div className={[
      'rounded-xl border bg-card p-5 flex flex-col gap-4 transition-shadow hover:shadow-sm',
      pack.is_active ? 'border-primary/40 ring-1 ring-primary/20' : '',
    ].join(' ')}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-sm truncate">{pack.name}</p>
          <p className="text-xs text-muted-foreground mt-0.5 font-mono truncate">{pack.skill_id}</p>
        </div>
        <div className="flex gap-2 shrink-0">
          {mode === 'intelligent' ? (
            <Badge className="bg-purple-100 text-purple-700 border-transparent">🧠 Intelligent</Badge>
          ) : mode === 'guided' ? (
            <Badge className="bg-blue-100 text-blue-700 border-transparent">📋 Guided</Badge>
          ) : null}
          {pack.is_active ? (
            <Badge className="bg-emerald-100 text-emerald-700 border-transparent">Active</Badge>
          ) : (
            <Badge variant="secondary">Inactive</Badge>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>v{pack.version}</span>
        <span>·</span>
        <span>{new Date(pack.created_at).toLocaleDateString()}</span>
      </div>

      <div className="flex items-center gap-2 flex-wrap mt-auto pt-3 border-t">
        {!pack.is_active && (
          <Button size="sm" variant="outline" className="h-7 text-xs px-2.5"
            onClick={onActivate} disabled={activating}>
            {activating ? 'Activating…' : 'Activate'}
          </Button>
        )}
        {pack.is_active && (
          <Button size="sm" variant="outline" className="h-7 text-xs px-2.5"
            onClick={onDeactivate} disabled={deactivating}>
            {deactivating ? 'Deactivating…' : 'Deactivate'}
          </Button>
        )}
        <Button size="sm" variant="ghost" className="h-7 text-xs px-2.5" onClick={onEdit}>Edit</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs px-2.5" onClick={onHistory}>History</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs px-2.5" onClick={onClone} disabled={cloning}>
          {cloning ? 'Cloning…' : 'Clone'}
        </Button>
        <Button size="sm" variant="ghost"
          className="h-7 text-xs px-2.5 text-destructive hover:text-destructive ml-auto"
          onClick={onDelete}>
          Delete
        </Button>
      </div>
    </div>
  )
}

export default function SkillPackLibrary() {
  const qc = useQueryClient()
  const [view, setView] = useState<ViewState>({ type: 'list' })
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  const { data: packs = [], isLoading, error } = useQuery({
    queryKey: ['skill-packs'],
    queryFn: () => api.skillPacks.list(),
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.skillPacks.activate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-packs'] }),
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => api.skillPacks.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-packs'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.skillPacks.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skill-packs'] })
      setDeleteConfirm(null)
    },
  })

  const cloneMutation = useMutation({
    mutationFn: (id: string) => api.skillPacks.clone(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-packs'] }),
  })

  if (view.type === 'builder') {
    return (
      <div>
        <Button variant="link" className="mb-4 px-0" onClick={() => setView({ type: 'list' })}>
          ← Back to library
        </Button>
        <SkillBuilder
          editingId={view.pack?.id}
          initialYaml={view.pack?.yaml_content}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['skill-packs'] })
            setView({ type: 'list' })
          }}
          onCancel={() => setView({ type: 'list' })}
        />
      </div>
    )
  }

  if (view.type === 'history') {
    return (
      <div>
        <Button variant="link" className="mb-4 px-0" onClick={() => setView({ type: 'list' })}>
          ← Back to library
        </Button>
        <VersionHistory packId={view.pack.id} packName={view.pack.name} />
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <p className="text-sm text-muted-foreground">
          {packs.length} pack{packs.length !== 1 ? 's' : ''} · {packs.filter(p => p.is_active).length} active
        </p>
        <Button size="sm" onClick={() => setView({ type: 'builder' })}>
          + New Skill
        </Button>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="rounded-xl border bg-card p-5 h-40 animate-pulse" />
          ))}
        </div>
      )}

      {error && <p className="text-destructive text-sm">Failed to load skill packs.</p>}

      {!isLoading && packs.length === 0 && (
        <div className="rounded-xl border border-dashed bg-muted/30 p-12 text-center">
          <p className="text-sm text-muted-foreground">No skill packs yet.</p>
          <Button size="sm" className="mt-3" onClick={() => setView({ type: 'builder' })}>
            Create your first skill
          </Button>
        </div>
      )}

      {packs.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {packs.map((pack) => (
            <SkillPackCard
              key={pack.id}
              pack={pack}
              onEdit={() => setView({ type: 'builder', pack })}
              onHistory={() => setView({ type: 'history', pack })}
              onActivate={() => activateMutation.mutate(pack.id)}
              onDeactivate={() => deactivateMutation.mutate(pack.id)}
              onDelete={() => setDeleteConfirm(pack.id)}
              onClone={() => cloneMutation.mutate(pack.id)}
              activating={activateMutation.isPending && activateMutation.variables === pack.id}
              deactivating={deactivateMutation.isPending && deactivateMutation.variables === pack.id}
              cloning={cloneMutation.isPending && cloneMutation.variables === pack.id}
            />
          ))}
        </div>
      )}

      <AlertDialog open={!!deleteConfirm} onOpenChange={(open) => !open && setDeleteConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Skill Pack?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the skill pack and all its version history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm)}
              disabled={deleteMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
