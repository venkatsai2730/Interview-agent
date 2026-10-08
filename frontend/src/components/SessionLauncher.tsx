import { useQuery } from '@tanstack/react-query'
import { Brain, ChevronDown, ChevronRight, Globe, Layers, MessageSquare, Mic, Phone, Sparkles, Zap } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type InputSchemaField } from '../api/client'
import { Alert, AlertDescription } from './ui/alert'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs'
import { Textarea } from './ui/textarea'

// Maps Sarvam voice value → display name used as the agent's identity
const PHONE_VOICE_NAMES: Record<string, string> = {
  shubh: 'Shubh',
  aditya: 'Aditya',
  ritu: 'Ritu',
  priya: 'Priya',
  neha: 'Neha',
  rahul: 'Rahul',
}

// Sarvam Bulbul v3 voices for Teams channel
const TEAMS_VOICE_NAMES: Record<string, string> = {
  'shubh': 'Shubh',
  'aditya': 'Aditya',
  'ritu': 'Ritu',
  'priya': 'Priya',
  'neha': 'Neha',
  'rahul': 'Rahul',
  'pooja': 'Pooja',
  'rohan': 'Rohan',
  'simran': 'Simran',
  'kavya': 'Kavya',
}

// Sarvam supported languages (for STT and TTS)
const SARVAM_LANGUAGES = [
  { value: 'en-IN', label: 'English (Indian)' },
  { value: 'hi-IN', label: 'Hindi' },
  { value: 'bn-IN', label: 'Bengali' },
  { value: 'ta-IN', label: 'Tamil' },
  { value: 'te-IN', label: 'Telugu' },
  { value: 'mr-IN', label: 'Marathi' },
  { value: 'gu-IN', label: 'Gujarati' },
  { value: 'kn-IN', label: 'Kannada' },
  { value: 'ml-IN', label: 'Malayalam' },
  { value: 'pa-IN', label: 'Punjabi' },
  { value: 'or-IN', label: 'Odia' },
  { value: 'ur-IN', label: 'Urdu' },
]

function isValidUrl(v: string) {
  return v.startsWith('https://') && v.length > 8
}
function isValidPhone(v: string) {
  return /^\+[1-9]\d{6,14}$/.test(v.trim())
}

function parseInputSchema(yamlContent: string): InputSchemaField[] | null {
  try {
    // Simple YAML parsing for input_schema section
    const inputSchemaMatch = yamlContent.match(/input_schema:\s*([\s\S]*?)(?:\n\w|$)/)
    if (!inputSchemaMatch) return null
    
    const lines = inputSchemaMatch[1].split('\n')
    const fields: InputSchemaField[] = []
    let currentField: Partial<InputSchemaField> = {}
    
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      
      // Check for new field entry (starts with -)
      const fieldMatch = trimmed.match(/^-\s*(\w+):\s*(.+)/)
      if (fieldMatch) {
        if (currentField.name) {
          fields.push(currentField as InputSchemaField)
        }
        currentField = { [fieldMatch[1]]: fieldMatch[2].replace(/^["']|["']$/g, '') }
      } else {
        // Property of current field
        const propMatch = trimmed.match(/^(\w+):\s*(.+)/)
        if (propMatch && currentField) {
          const [, key, value] = propMatch
          if (key === 'required') {
            (currentField as Record<string, unknown>)[key] = value === 'true'
          } else if (key === 'values') {
            // Parse array values
            const values = value.match(/\[(.*)\]/)?.[1]?.split(',').map(v => v.trim().replace(/^["']|["']$/g, ''))
            ;(currentField as Record<string, unknown>)[key] = values || []
          } else {
            (currentField as Record<string, unknown>)[key] = value.replace(/^["']|["']$/g, '')
          }
        }
      }
    }
    if (currentField.name) {
      fields.push(currentField as InputSchemaField)
    }
    return fields.length > 0 ? fields : null
  } catch {
    return null
  }
}

interface GuidedQuestion {
  id: string
  text: string
}

interface SkillSections {
  guided: GuidedQuestion[]
  intelligent: string | null
}


function ModePreview({ sections, mode }: { sections: SkillSections; mode: 'guided' | 'intelligent' }) {
  const [expanded, setExpanded] = useState(false)
  if (mode === 'guided') {
    if (sections.guided.length === 0) return null
    return (
      <div className="rounded-lg border bg-muted/20 overflow-hidden">
        <button
          type="button"
          className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted/40 transition-colors"
          onClick={() => setExpanded(e => !e)}
        >
          <span className="flex items-center gap-1.5"><Layers size={11} className="text-amber-500" /> {sections.guided.length} question{sections.guided.length !== 1 ? 's' : ''} in this session</span>
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
        {expanded && (
          <ol className="px-3 pb-3 space-y-1.5 list-none">
            {sections.guided.map((q, i) => (
              <li key={q.id} className="flex gap-2 text-xs">
                <span className="shrink-0 w-4 h-4 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold flex items-center justify-center mt-0.5">{i + 1}</span>
                <span className="text-foreground/80 leading-snug">{q.text}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    )
  }
  // intelligent
  if (!sections.intelligent) return null
  return (
    <div className="rounded-lg border bg-muted/20 overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted/40 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="flex items-center gap-1.5"><Sparkles size={11} className="text-violet-500" /> Adaptive objectives for this session</span>
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>
      {expanded && (
        <div className="px-3 pb-3">
          <pre className="text-xs text-foreground/75 whitespace-pre-wrap font-sans leading-relaxed max-h-52 overflow-y-auto">{sections.intelligent}</pre>
        </div>
      )}
    </div>
  )
}

function ContextInputFields({
  inputSchema, 
  values, 
  onChange,
  onFileChange,
}: { 
  inputSchema: InputSchemaField[] 
  values: Record<string, unknown>
  onChange: (name: string, value: unknown) => void
  onFileChange?: (name: string, file: File | null) => void
}) {
  return (
    <div className="space-y-4 border rounded-lg p-4 bg-muted/30">
      <h4 className="text-sm font-medium text-muted-foreground">Session Context</h4>
      {inputSchema.map((field) => (
        <div key={field.name} className="space-y-1.5">
          <Label htmlFor={field.name} className="text-sm">
            {field.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            {field.required !== false && <span className="text-destructive ml-1">*</span>}
          </Label>
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
          {field.type === 'file' ? (
            <div>
              <Input
                id={field.name}
                type="file"
                accept=".pdf"
                onChange={(e) => {
                  const file = e.target.files?.[0] || null
                  if (onFileChange) onFileChange(field.name, file)
                  onChange(field.name, file?.name || '')
                }}
                className="cursor-pointer"
              />
              {values[field.name] && (
                <p className="text-xs text-green-600 mt-1">✓ {String(values[field.name])}</p>
              )}
            </div>
          ) : field.type === 'text' ? (
            <Textarea
              id={field.name}
              value={String(values[field.name] || '')}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange(field.name, e.target.value)}
              placeholder={`Enter ${field.name.replace(/_/g, ' ')}...`}
              rows={4}
            />
          ) : field.type === 'enum' ? (
            <Select
              value={String(values[field.name] || '')}
              onValueChange={(v) => onChange(field.name, v)}
            >
              <SelectTrigger>
                <SelectValue placeholder={`Select ${field.name.replace(/_/g, ' ')}...`} />
              </SelectTrigger>
              <SelectContent>
                {field.values?.map((v) => (
                  <SelectItem key={v} value={v}>{v}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : field.type === 'boolean' ? (
            <Select
              value={String(values[field.name] || 'false')}
              onValueChange={(v) => onChange(field.name, v === 'true')}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">Yes</SelectItem>
                <SelectItem value="false">No</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <Input
              id={field.name}
              type={field.type === 'number' ? 'number' : 'text'}
              value={String(values[field.name] || '')}
              onChange={(e) => onChange(field.name, field.type === 'number' ? Number(e.target.value) : e.target.value)}
              placeholder={`Enter ${field.name.replace(/_/g, ' ')}...`}
            />
          )}
        </div>
      ))}
    </div>
  )
}

export default function SessionLauncher() {
  const navigate = useNavigate()
  const { data: skillPacks = [] } = useQuery({
    queryKey: ['skill-packs'],
    queryFn: () => api.skillPacks.list(),
  })

  // Filter skills by channel support - show ALL active skills for the channel
  const teamsSkillPacks = skillPacks.filter((sp) => 
    sp.is_active && (sp.channels || ['teams', 'phone']).includes('teams')
  )
  const phoneSkillPacks = skillPacks.filter((sp) => 
    sp.is_active && (sp.channels || ['teams', 'phone']).includes('phone')
  )
  
  const [activeTab, setActiveTab] = useState<'teams' | 'phone'>('teams')
  const [conversationMode, setConversationMode] = useState<'guided' | 'intelligent'>('guided')
  // No default selection - user must explicitly choose
  const [skillPackId, setSkillPackId] = useState('')
  const [meetingUrl, setMeetingUrl] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [voice, setVoice] = useState('shubh')
  const [phoneModel, setPhoneModel] = useState('sarvam-30b')
  const [phoneLanguage, setPhoneLanguage] = useState('en-IN')
  const [teamsVoice, setTeamsVoice] = useState('shubh')
  const [teamsModel, setTeamsModel] = useState('sarvam-30b')
  const [teamsLanguage, setTeamsLanguage] = useState('en-IN')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [contextData, setContextData] = useState<Record<string, unknown>>({})
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, File>>({})
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<Record<string, string> | null>(null)
  const lastSubmitTime = useRef<number>(0)

  const selectedId = skillPackId
  
  // Parse input_schema from selected skill pack
  const selectedSkillPack = useMemo(() => {
    return skillPacks.find((sp) => sp.id === selectedId)
  }, [skillPacks, selectedId])
  
  const inputSchema = useMemo(() => {
    if (!selectedSkillPack?.yaml_content) return null
    return parseInputSchema(selectedSkillPack.yaml_content)
  }, [selectedSkillPack])

  const skillSections = useMemo((): SkillSections | null => {
    if (!selectedSkillPack?.sections_summary?.length) return null
    const guided = selectedSkillPack.sections_summary
      .filter(s => s.mode === 'guided')
      .flatMap(s => s.questions.map((text, i) => ({ id: `q-${i + 1}`, text })))
    const intelligentSection = selectedSkillPack.sections_summary.find(s => s.mode === 'intelligent')
    return { guided, intelligent: intelligentSection?.objectives ?? null }
  }, [selectedSkillPack])
  
  // Reset context data when skill pack changes
  const handleSkillPackChange = (id: string) => {
    setSkillPackId(id)
    setContextData({})
  }
  
  const handleContextChange = (name: string, value: unknown) => {
    setContextData(prev => ({ ...prev, [name]: value }))
  }

  const handleFileChange = (name: string, file: File | null) => {
    if (file) {
      setUploadedFiles(prev => ({ ...prev, [name]: file }))
    } else {
      setUploadedFiles(prev => {
        const next = { ...prev }
        delete next[name]
        return next
      })
    }
    // Reset analysis when files change
    setAnalysisResult(null)
  }

  // Run resume/JD analysis when both files are uploaded
  const runAnalysis = async () => {
    const resumeFile = uploadedFiles['resume'] || uploadedFiles['resume_pdf']
    const jdFile = uploadedFiles['job_description'] || uploadedFiles['jd_pdf']
    const jdText = String(contextData['job_description'] || contextData['jd_text'] || '')

    if (!resumeFile) {
      setError('Please upload a resume PDF first')
      return
    }
    if (!jdFile && !jdText) {
      setError('Please provide a job description (PDF or text)')
      return
    }

    setAnalyzing(true)
    setError(null)
    try {
      const result = await api.sessions.analyzeResume(resumeFile, jdFile || undefined, jdText || undefined)
      setAnalysisResult(result.analysis)
      // Inject analysis into context_data so it goes to the agent
      setContextData(prev => ({
        ...prev,
        ...result.analysis,
        _resume_analyzed: 'true',
      }))
    } catch (err: unknown) {
      setError(`Analysis failed: ${(err as Error).message}`)
    } finally {
      setAnalyzing(false)
    }
  }
  
  // Check if all required context fields are filled
  const isContextValid = useMemo(() => {
    if (!inputSchema) return true
    return inputSchema.every(field => {
      if (field.required === false) return true
      const value = contextData[field.name]
      return value !== undefined && value !== '' && value !== null
    })
  }, [inputSchema, contextData])

  async function handleTeams(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedId || !isValidUrl(meetingUrl) || submitting || !isContextValid) return
    
    // Debounce: prevent rapid double-clicks (minimum 2 seconds between submissions)
    const now = Date.now()
    if (now - lastSubmitTime.current < 2000) {
      console.log('Debounced: submission too soon')
      return
    }
    lastSubmitTime.current = now
    
    setError(null)
    setSubmitting(true)
    try {
      const agentName = TEAMS_VOICE_NAMES[teamsVoice]
      const contextToSend = { ...contextData, _mode: conversationMode }
      await api.sessions.create(selectedId, meetingUrl, `sarvam:${teamsVoice}`, teamsModel, agentName, contextToSend, teamsLanguage)
      navigate('/sessions-history')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setSubmitting(false)
    }
  }

  async function handlePhone(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedId || !isValidPhone(phoneNumber) || submitting || !isContextValid) return
    
    // Debounce: prevent rapid double-clicks (minimum 2 seconds between submissions)
    const now = Date.now()
    if (now - lastSubmitTime.current < 2000) {
      console.log('Debounced: submission too soon')
      return
    }
    lastSubmitTime.current = now
    
    setError(null)
    setSubmitting(true)
    try {
      const agentName = PHONE_VOICE_NAMES[voice] || voice
      const contextToSend = { ...contextData, _mode: conversationMode }
      await api.sessions.createPhoneLiveKit(selectedId, phoneNumber.trim(), `sarvam:${voice}`, phoneModel, agentName, contextToSend, phoneLanguage)
      navigate('/sessions-history')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to place call')
    } finally {
      setSubmitting(false)
    }
  }

  const contextFieldsSection = inputSchema && inputSchema.length > 0 && (
    <div className="space-y-3">
      <ContextInputFields
        inputSchema={inputSchema}
        values={contextData}
        onChange={handleContextChange}
        onFileChange={handleFileChange}
      />
      {/* Show Analyze button when resume file type fields exist */}
      {inputSchema.some(f => f.type === 'file') && (
        <div className="space-y-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={runAnalysis}
            disabled={analyzing || !uploadedFiles['resume'] && !uploadedFiles['resume_pdf']}
            className="w-full"
          >
            {analyzing ? (
              <><Sparkles size={14} className="animate-spin mr-2" /> Analyzing Resume vs JD...</>
            ) : analysisResult ? (
              <><Sparkles size={14} className="text-green-500 mr-2" /> Re-analyze</>
            ) : (
              <><Sparkles size={14} className="mr-2" /> Analyze Resume &amp; Generate Weightage</>
            )}
          </Button>
          {analysisResult && (
            <div className="rounded-lg border bg-green-50 dark:bg-green-950/20 p-3 space-y-1">
              <p className="text-xs font-medium text-green-700 dark:text-green-400">✓ Analysis complete</p>
              {analysisResult.candidate_summary && (
                <p className="text-xs text-muted-foreground">{analysisResult.candidate_summary}</p>
              )}
              {analysisResult.key_gaps && (
                <p className="text-xs text-orange-600">Gaps: {analysisResult.key_gaps}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )

  const modeSelector = selectedSkillPack && (
    <div className="space-y-2">
      <label className="text-sm font-medium flex items-center gap-1.5">
        <Sparkles size={13} className="text-violet-500" /> Conversation Mode
      </label>
      <div className="flex rounded-lg border overflow-hidden h-8">
        <button
          type="button"
          onClick={() => setConversationMode('guided')}
          className={[
            'flex-1 flex items-center justify-center gap-1.5 text-xs font-medium transition-colors',
            conversationMode === 'guided'
              ? 'bg-amber-500 text-white'
              : 'bg-card text-muted-foreground hover:bg-muted',
          ].join(' ')}
        >
          <Layers size={11} /> Guided
        </button>
        <button
          type="button"
          onClick={() => setConversationMode('intelligent')}
          className={[
            'flex-1 flex items-center justify-center gap-1.5 text-xs font-medium transition-colors border-l',
            conversationMode === 'intelligent'
              ? 'bg-violet-600 text-white'
              : 'bg-card text-muted-foreground hover:bg-muted',
          ].join(' ')}
        >
          <Sparkles size={11} /> Intelligent
        </button>
      </div>
      {skillSections && (
        <ModePreview sections={skillSections} mode={conversationMode} />
      )}
    </div>
  )

  return (
    <div className="max-w-lg">
      <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v as 'teams' | 'phone'); setSkillPackId(''); setContextData({}); setConversationMode('guided'); }}>
        <TabsList className="mb-5 w-full h-11 p-1">
          <TabsTrigger value="teams" className="flex-1 gap-2 text-sm">
            <MessageSquare size={14} className="text-violet-500" />
            Microsoft Teams
          </TabsTrigger>
          <TabsTrigger value="phone" className="flex-1 gap-2 text-sm">
            <Phone size={14} className="text-orange-500" />
            Phone Call
          </TabsTrigger>
        </TabsList>

        <TabsContent value="teams">
          <form onSubmit={handleTeams} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Layers size={13} className="text-amber-500" /> Skill Pack
              </label>
              <Select value={selectedId} onValueChange={handleSkillPackChange}>
                <SelectTrigger>
                  <SelectValue placeholder="No active skill pack…" />
                </SelectTrigger>
                <SelectContent>
                  {teamsSkillPacks.map((sp) => (
                    <SelectItem key={sp.id} value={sp.id}>{sp.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {teamsSkillPacks.length === 0 && (
                <p className="text-xs text-destructive">No active skill pack. Activate one in Skill Packs.</p>
              )}
            </div>
            {modeSelector}
            {contextFieldsSection}
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <MessageSquare size={13} className="text-violet-500" /> Teams Meeting URL
              </label>
              <Input
                type="url"
                placeholder="https://teams.microsoft.com/l/meetup-join/…"
                value={meetingUrl}
                onChange={(e) => setMeetingUrl(e.target.value)}
              />
              {meetingUrl && !isValidUrl(meetingUrl) && (
                <p className="text-xs text-destructive">Must start with https://</p>
              )}
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Brain size={13} className="text-teal-500" /> LLM Model
              </label>
              <Select value={teamsModel} onValueChange={setTeamsModel}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="gemini-2.5-flash">Gemini 2.5 Flash — latest, best</SelectItem>
                  <SelectItem value="gpt-4o-mini">GPT-4o Mini — balanced</SelectItem>
                  <SelectItem value="gpt-4o">GPT-4o — premium</SelectItem>
                  <SelectItem value="sarvam-30b">Sarvam 30B — Indian languages</SelectItem>
                  <SelectItem value="sarvam-105b">Sarvam 105B — Indian, capable</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Globe size={13} className="text-blue-500" /> Conversation Language
              </label>
              <Select value={teamsLanguage} onValueChange={setTeamsLanguage}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SARVAM_LANGUAGES.map(lang => (
                    <SelectItem key={lang.value} value={lang.value}>{lang.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Language for speech recognition and synthesis.</p>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Mic size={13} className="text-primary" /> Agent Voice
              </label>
              <Select value={teamsVoice} onValueChange={setTeamsVoice}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="shubh">Shubh — Hindi/English (masculine)</SelectItem>
                  <SelectItem value="aditya">Aditya — Hindi/English (masculine)</SelectItem>
                  <SelectItem value="ritu">Ritu — Hindi/English (feminine)</SelectItem>
                  <SelectItem value="priya">Priya — Hindi/English (feminine)</SelectItem>
                  <SelectItem value="neha">Neha — Hindi/English (feminine)</SelectItem>
                  <SelectItem value="rahul">Rahul — Hindi/English (masculine)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Agent will introduce itself using this voice name.</p>
            </div>
            {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
            <Button type="submit" className="w-full gap-2 h-10" disabled={!selectedId || !isValidUrl(meetingUrl) || submitting || !isContextValid}>
              <Zap size={15} />
              {submitting ? 'Launching…' : 'Launch Session'}
            </Button>
          </form>
        </TabsContent>

        <TabsContent value="phone">
          <form onSubmit={handlePhone} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Layers size={13} className="text-amber-500" /> Skill Pack
              </label>
              <Select value={selectedId} onValueChange={handleSkillPackChange}>
                <SelectTrigger>
                  <SelectValue placeholder="No active skill pack…" />
                </SelectTrigger>
                <SelectContent>
                  {phoneSkillPacks.map((sp) => (
                    <SelectItem key={sp.id} value={sp.id}>{sp.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {phoneSkillPacks.length === 0 && (
                <p className="text-xs text-destructive">No active skill pack. Activate one in Skill Packs.</p>
              )}
            </div>
            {modeSelector}
            {contextFieldsSection}
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Phone size={13} className="text-orange-500" /> Phone Number
              </label>
              <Input
                type="tel"
                placeholder="+919966933336"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
              />
              {phoneNumber && !isValidPhone(phoneNumber) && (
                <p className="text-xs text-destructive">Use E.164 format: +[country][number]</p>
              )}
              <p className="text-xs text-muted-foreground">
                The agent will call this number via LiveKit SIP. Answer to start the session.
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Brain size={13} className="text-teal-500" /> LLM Model
              </label>
              <Select value={phoneModel} onValueChange={setPhoneModel}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="gemini-2.5-flash">Gemini 2.5 Flash — latest, best</SelectItem>
                  <SelectItem value="gpt-4o-mini">GPT-4o Mini — balanced</SelectItem>
                  <SelectItem value="gpt-4o">GPT-4o — premium</SelectItem>
                  <SelectItem value="sarvam-30b">Sarvam 30B — Indian languages</SelectItem>
                  <SelectItem value="sarvam-105b">Sarvam 105B — Indian, capable</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Globe size={13} className="text-blue-500" /> Conversation Language
              </label>
              <Select value={phoneLanguage} onValueChange={setPhoneLanguage}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SARVAM_LANGUAGES.map(lang => (
                    <SelectItem key={lang.value} value={lang.value}>{lang.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Language for speech recognition and synthesis.</p>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium flex items-center gap-1.5">
                <Mic size={13} className="text-primary" /> Agent Voice
              </label>
              <Select value={voice} onValueChange={setVoice}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="shubh">Shubh — Hindi/English (masculine)</SelectItem>
                  <SelectItem value="aditya">Aditya — Hindi/English (masculine)</SelectItem>
                  <SelectItem value="ritu">Ritu — Hindi/English (feminine)</SelectItem>
                  <SelectItem value="priya">Priya — Hindi/English (feminine)</SelectItem>
                  <SelectItem value="neha">Neha — Hindi/English (feminine)</SelectItem>
                  <SelectItem value="rahul">Rahul — Hindi/English (masculine)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Agent will introduce itself using this voice name.</p>
            </div>
            {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
            <Button type="submit" className="w-full gap-2 h-10 bg-orange-600 hover:bg-orange-700 text-white" disabled={!selectedId || !isValidPhone(phoneNumber) || submitting || !isContextValid}>
              <Phone size={15} />
              {submitting ? 'Calling…' : 'Call Now'}
            </Button>
          </form>
        </TabsContent>
      </Tabs>
    </div>
  )
}
