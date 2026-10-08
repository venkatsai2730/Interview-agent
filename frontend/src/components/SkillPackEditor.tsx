import Editor, { OnMount } from '@monaco-editor/react'
import type * as Monaco from 'monaco-editor'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { Badge } from './ui/badge'
import { Button } from './ui/button'

interface Props {
  initialContent?: string
  editingId?: string        // if set, PUT; otherwise POST
  onSaved?: (id: string) => void
  readOnly?: boolean
}

export default function SkillPackEditor({ initialContent = '', editingId, onSaved, readOnly = false }: Props) {
  const [content, setContent] = useState(initialContent)
  const [isValid, setIsValid] = useState<boolean | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<typeof Monaco | null>(null)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco
    // Validate existing content immediately on mount
    if (initialContent.trim()) {
      validate(initialContent)
    }
  }

  const validate = useCallback(async (value: string) => {
    if (!editorRef.current || !monacoRef.current) return
    const monaco = monacoRef.current
    const model = editorRef.current.getModel()
    if (!model) return

    try {
      await api.skillPacks.validate(value)
      monaco.editor.setModelMarkers(model, 'vero-validation', [])
      setIsValid(true)
    } catch (err: unknown) {
      setIsValid(false)
      const body = (err as { body?: { detail?: string | { errors?: string[] } } }).body
      const detail = body?.detail
      const markers: Monaco.editor.IMarkerData[] = []

      if (typeof detail === 'string') {
        const lineMatch = detail.match(/line (\d+)/i)
        const lineNumber = lineMatch ? parseInt(lineMatch[1], 10) : 1
        markers.push({
          severity: monaco.MarkerSeverity.Error,
          message: detail,
          startLineNumber: lineNumber,
          startColumn: 1,
          endLineNumber: lineNumber,
          endColumn: 100,
        })
      } else if (detail && typeof detail === 'object' && Array.isArray(detail.errors)) {
        detail.errors.forEach((msg: string) => {
          markers.push({
            severity: monaco.MarkerSeverity.Error,
            message: msg,
            startLineNumber: 1,
            startColumn: 1,
            endLineNumber: 1,
            endColumn: 100,
          })
        })
      }

      monaco.editor.setModelMarkers(model, 'vero-validation', markers)
    }
  }, [])

  const handleChange = useCallback((value: string | undefined) => {
    const v = value ?? ''
    setContent(v)
    setIsValid(null)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => validate(v), 500)
  }, [validate])

  useEffect(() => () => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
  }, [])

  const handleSave = async () => {
    if (!isValid) return
    setIsSaving(true)
    setSaveError(null)
    try {
      let result: { id: string }
      if (editingId) {
        result = await api.skillPacks.update(editingId, content) as { id: string }
      } else {
        result = await api.skillPacks.create(content) as { id: string }
      }
      onSaved?.(result.id)
    } catch (err: unknown) {
      const msg = (err as Error).message ?? 'Save failed'
      setSaveError(msg)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isValid === true && (
            <Badge variant="success">Valid</Badge>
          )}
          {isValid === false && (
            <Badge variant="destructive">Invalid</Badge>
          )}
          {isValid === null && content.length > 0 && (
            <Badge variant="secondary">Validating…</Badge>
          )}
        </div>
        {!readOnly && (
          <Button
            onClick={handleSave}
            disabled={!isValid || isSaving}
            size="sm"
          >
            {isSaving ? 'Saving…' : editingId ? 'Update' : 'Save'}
          </Button>
        )}
      </div>

      <div className="border border-border rounded overflow-hidden" style={{ height: '500px' }}>
        <Editor
          height="100%"
          language="yaml"
          theme="vs-dark"
          value={content}
          onChange={handleChange}
          onMount={handleMount}
          options={{
            readOnly,
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            wordWrap: 'on',
          }}
        />
      </div>

      {saveError && (
        <p className="text-sm text-destructive">{saveError}</p>
      )}
    </div>
  )
}
