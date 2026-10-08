import { useState, useEffect, useCallback } from 'react'
import { api, GenerateSkillPackResponse } from '../api/client'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Textarea } from './ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { Card, CardContent } from './ui/card'
import { Badge } from './ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs'
import { Plus, Trash2, ChevronDown, ChevronUp, HelpCircle, Sparkles } from 'lucide-react'
import { Checkbox } from './ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'

interface InputSchemaField {
  name: string
  type: 'string' | 'text' | 'number' | 'boolean' | 'enum'
  required: boolean
  description: string
  values?: string[]
}

interface Question {
  id: string
  text: string
  probes: string[]
  competency: string
  max_follow_ups: number
}

interface RubricEntry {
  competency: string
  scores: Record<number, string>
}

interface Section {
  id: string
  title: string
  mode: 'guided' | 'intelligent'
  objectives?: string
  questions?: Question[]
}

interface SkillFormData {
  skill_id: string
  name: string
  version: string
  persona: string
  language: string
  max_duration_minutes: number
  model: string
  tts_voice: string
  channels: string[]
  input_schema: InputSchemaField[]
  sections: Section[]
  questions: Question[]  // Keep for backward compatibility
  rubric: RubricEntry[]
  report_template: string
  email_to: string
  include_transcript: boolean
}

const DEFAULT_FORM_DATA: SkillFormData = {
  skill_id: '',
  name: '',
  version: '1.0.0',
  persona: '',
  language: 'en-IN',
  max_duration_minutes: 30,
  model: 'sarvam-30b',
  tts_voice: 'shubh',
  channels: ['teams', 'phone'],
  input_schema: [],
  sections: [
    {
      id: 'main',
      title: 'Main Section',
      mode: 'guided',
      questions: [
        {
          id: 'q1',
          text: '',
          probes: ['Can you tell me more about that?'],
          competency: 'communication',
          max_follow_ups: 2,
        },
      ],
    },
  ],
  questions: [
    {
      id: 'q1',
      text: '',
      probes: ['Can you tell me more about that?'],
      competency: 'communication',
      max_follow_ups: 2,
    },
  ],
  rubric: [
    {
      competency: 'communication',
      scores: {
        1: 'Poor communication',
        2: 'Below average',
        3: 'Adequate communication',
        4: 'Good communication',
        5: 'Excellent communication',
      },
    },
  ],
  report_template: 'scorecard',
  email_to: '',
  include_transcript: true,
}

// Sarvam Bulbul v3 voices
const VOICE_OPTIONS = [
  { value: 'shubh', label: 'Shubh — warm, professional (masculine)' },
  { value: 'aditya', label: 'Aditya — confident, clear (masculine)' },
  { value: 'ritu', label: 'Ritu — friendly, engaging (feminine)' },
  { value: 'priya', label: 'Priya — professional, calm (feminine)' },
  { value: 'neha', label: 'Neha — energetic, approachable (feminine)' },
  { value: 'rahul', label: 'Rahul — authoritative (masculine)' },
  { value: 'pooja', label: 'Pooja — soft, empathetic (feminine)' },
  { value: 'rohan', label: 'Rohan — conversational (masculine)' },
  { value: 'simran', label: 'Simran — bright, articulate (feminine)' },
  { value: 'kavya', label: 'Kavya — clear, precise (feminine)' },
]

// LLM models
const MODEL_OPTIONS = [
  { value: 'sarvam-30b', label: 'Sarvam 30B — fast, efficient' },
  { value: 'sarvam-105b', label: 'Sarvam 105B — most capable' },
  { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash — best quality' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini — balanced' },
  { value: 'gpt-4o', label: 'GPT-4o — premium quality' },
]

const LANGUAGE_OPTIONS = [
  { value: 'en-IN', label: 'English (India)' },
  { value: 'hi-IN', label: 'Hindi' },
  { value: 'ta-IN', label: 'Tamil' },
  { value: 'te-IN', label: 'Telugu' },
  { value: 'kn-IN', label: 'Kannada' },
  { value: 'ml-IN', label: 'Malayalam' },
  { value: 'bn-IN', label: 'Bengali' },
  { value: 'gu-IN', label: 'Gujarati' },
  { value: 'mr-IN', label: 'Marathi' },
]

const REPORT_TEMPLATES = [
  { value: 'scorecard', label: 'Scorecard' },
  { value: 'coaching-report', label: 'Coaching Report' },
  { value: 'discovery-brief', label: 'Discovery Brief' },
  { value: 'audit-log', label: 'Audit Log' },
]

/** Derive agent display name from voice selection */
function voiceToName(voice: string): string {
  return voice.charAt(0).toUpperCase() + voice.slice(1)
}

function generateYaml(data: SkillFormData): string {
  const agentName = voiceToName(data.tts_voice)

  const inputSchemaYaml = data.input_schema.length > 0
    ? `\ninput_schema:\n${data.input_schema.map(f => {
        let field = `  - name: ${f.name}\n    type: ${f.type}\n    required: ${f.required}\n    description: "${f.description}"`
        if (f.type === 'enum' && f.values) {
          field += `\n    values: [${f.values.join(', ')}]`
        }
        return field
      }).join('\n')}`
    : ''

  const sectionsYaml = data.sections.map((section, sIdx) => {
    const sectionId = section.id || `section${sIdx + 1}`
    const mode = section.mode || 'guided'

    if (mode === 'intelligent') {
      return `  - id: ${sectionId}
    title: ${section.title}
    mode: intelligent
    objectives: |
${(section.objectives || '').split('\n').map(l => `      ${l}`).join('\n')}`
    } else {
      const questionsYaml = (section.questions || []).map((q, idx) => `      - id: ${q.id || `q${idx + 1}`}
        text: "${q.text}"
        probes:
${q.probes.map(p => `          - "${p}"`).join('\n')}
        competency: ${q.competency}
        max_follow_ups: ${q.max_follow_ups}`).join('\n\n')

      return `  - id: ${sectionId}
    title: ${section.title}
    mode: guided
    questions:
${questionsYaml}`
    }
  }).join('\n\n')

  const rubricYaml = data.rubric.map(r => `  - competency: ${r.competency}
    scores:
${Object.entries(r.scores).map(([score, desc]) => `      ${score}: "${desc}"`).join('\n')}`).join('\n')

  return `skill:
  id: ${data.skill_id}
  name: ${data.name}
  version: ${data.version}
  channels: [${data.channels.join(', ')}]

agent:
  name: ${agentName}
  persona: >
    ${data.persona.replace(/\n/g, '\n    ')}
  language: ${data.language}
  max_duration_minutes: ${data.max_duration_minutes}
  model_preferences:
    - provider: sarvam
      model: ${data.model}
  tts_voice: sarvam:${data.tts_voice}
${inputSchemaYaml}
sections:
${sectionsYaml}

rubric:
${rubricYaml}

report:
  template: ${data.report_template}
  email_to:
    - ${data.email_to || 'admin@example.com'}
  include_transcript: ${data.include_transcript}`
}

interface Props {
  onSaved?: () => void
  onCancel?: () => void
  editingId?: string
  initialYaml?: string
}

// Parse YAML content back to form data (basic parser)
function parseYamlToFormData(yaml: string): Partial<SkillFormData> {
  const data: Partial<SkillFormData> = {}

  // Extract skill info
  const skillMatch = yaml.match(/skill:[\s\S]*?id:\s*(.+?)[\r\n]+  name:\s*(.+?)[\r\n]+  version:\s*(.+?)(?:[\r\n]|$)/)
  if (skillMatch) {
    data.skill_id = skillMatch[1].trim()
    data.name = skillMatch[2].trim()
    data.version = skillMatch[3].trim()
  }

  // Extract channels (both list and inline formats)
  const channelsInlineMatch = yaml.match(/channels:\s*\[([^\]]+)\]/)
  if (channelsInlineMatch) {
    data.channels = channelsInlineMatch[1].split(',').map(c => c.trim())
  } else {
    const channelsBlockMatch = yaml.match(/channels:[\s\S]*?(?=\n\w|$)/)
    if (channelsBlockMatch) {
      const channelList = channelsBlockMatch[0].match(/- (\w+)/g)
      if (channelList) {
        data.channels = channelList.map(m => m.replace('- ', ''))
      }
    }
  }

  // Extract agent info — derive name from tts_voice, not agent.name
  const voiceMatch = yaml.match(/tts_voice:\s*sarvam:(.+?)(?:[\r\n]|$)/)
  if (voiceMatch) data.tts_voice = voiceMatch[1].trim()

  const personaMatch = yaml.match(/persona:\s*>\s*\n([\s\S]*?)(?=\n\w|\n  \w|$)/)
  if (personaMatch) {
    data.persona = personaMatch[1].replace(/^    /gm, '').trim()
  }

  const langMatch = yaml.match(/language:\s*(.+?)(?:[\r\n]|$)/)
  if (langMatch) data.language = langMatch[1].trim()

  const durationMatch = yaml.match(/max_duration_minutes:\s*(\d+)/)
  if (durationMatch) data.max_duration_minutes = parseInt(durationMatch[1])

  const modelMatch = yaml.match(/model:\s*(sarvam-\w+)/)
  if (modelMatch) data.model = modelMatch[1].trim()

  // Extract input_schema
  const inputSchemaMatch = yaml.match(/input_schema:[\s\S]*?(?=\n\w|$)/)
  if (inputSchemaMatch && !inputSchemaMatch[0].includes('undefined')) {
    const fields: InputSchemaField[] = []
    const fieldBlocks = inputSchemaMatch[0].split(/\n  - /).slice(1)
    for (const block of fieldBlocks) {
      const nameMatch = block.match(/name:\s*(.+?)(?:[\r\n]|$)/)
      const typeMatch = block.match(/type:\s*(.+?)(?:[\r\n]|$)/)
      const requiredMatch = block.match(/required:\s*(true|false)/)
      const descMatch = block.match(/description:\s*"(.+?)"/)
      const valuesMatch = block.match(/values:\s*\[(.+?)\]/)

      if (nameMatch && typeMatch) {
        fields.push({
          name: nameMatch[1].trim(),
          type: typeMatch[1].trim() as InputSchemaField['type'],
          required: requiredMatch ? requiredMatch[1] === 'true' : true,
          description: descMatch ? descMatch[1] : '',
          values: valuesMatch ? valuesMatch[1].split(',').map(v => v.trim()) : undefined,
        })
      }
    }
    if (fields.length > 0) data.input_schema = fields
  }

  // Extract sections (supports both guided and intelligent modes)
  const sectionsMatch = yaml.match(/sections:[\s\S]*?(?=\nrubric:|$)/)
  if (sectionsMatch) {
    const sections: Section[] = []
    const sectionBlocks = sectionsMatch[0].split(/\n  - /).slice(1)

    for (const block of sectionBlocks) {
      const idMatch = block.match(/id:\s*(.+?)(?:[\r\n]|$)/)
      const titleMatch = block.match(/title:\s*(.+?)(?:[\r\n]|$)/)
      const modeMatch = block.match(/mode:\s*(.+?)(?:[\r\n]|$)/)

      if (idMatch && titleMatch) {
        const mode = (modeMatch ? modeMatch[1].trim() : 'guided') as 'guided' | 'intelligent'

        if (mode === 'intelligent') {
          // Extract objectives — handle both | (literal) and > (folded) styles
          const objMatch = block.match(/objectives:\s*[|>]\s*\n([\s\S]*?)(?=\n\s{0,4}\w|$)/)
          const objectives = objMatch
            ? objMatch[1].split('\n').map(l => l.replace(/^      /, '')).join('\n').trim()
            : ''

          sections.push({
            id: idMatch[1].trim(),
            title: titleMatch[1].trim(),
            mode: 'intelligent',
            objectives,
          })
        } else {
          const questions: Question[] = []
          const qBlocks = block.split(/\n      - /).slice(1)

          for (const qBlock of qBlocks) {
            const qIdMatch = qBlock.match(/id:\s*(.+?)(?:[\r\n]|$)/)
            const textMatch = qBlock.match(/text:\s*"(.+?)"/)
            const competencyMatch = qBlock.match(/competency:\s*(.+?)(?:[\r\n]|$)/)
            const maxFuMatch = qBlock.match(/max_follow_ups:\s*(\d+)/)

            if (qIdMatch && textMatch) {
              const probesMatch = qBlock.match(/probes:[\s\S]*?(?=\n\s*\w|$)/)
              const probes = probesMatch
                ? probesMatch[0].match(/- "(.+?)"/g)?.map(p => p.replace(/- "|"/g, '')) || []
                : []
              questions.push({
                id: qIdMatch[1].trim(),
                text: textMatch[1],
                competency: competencyMatch ? competencyMatch[1].trim() : 'communication',
                max_follow_ups: maxFuMatch ? parseInt(maxFuMatch[1]) : 2,
                probes: probes.length > 0 ? probes : ['Can you elaborate?'],
              })
            }
          }

          sections.push({
            id: idMatch[1].trim(),
            title: titleMatch[1].trim(),
            mode: 'guided',
            questions,
          })
        }
      }
    }

    if (sections.length > 0) {
      data.sections = sections
      const firstGuided = sections.find(s => s.mode === 'guided')
      if (firstGuided?.questions) {
        data.questions = firstGuided.questions
      }
    }
  }

  // Extract rubric
  const rubricSection = yaml.match(/rubric:[\s\S]*?(?=\nreport:|$)/)
  if (rubricSection) {
    const rubric: RubricEntry[] = []
    const rBlocks = rubricSection[0].split(/\n  - /).slice(1)
    for (const block of rBlocks) {
      const competencyMatch = block.match(/competency:\s*(.+?)(?:[\r\n]|$)/)
      if (competencyMatch) {
        const scores: Record<number, string> = {}
        const scoreMatches = block.matchAll(/(\d+):\s*"(.+?)"/g)
        for (const match of scoreMatches) {
          scores[parseInt(match[1])] = match[2]
        }
        rubric.push({ competency: competencyMatch[1].trim(), scores })
      }
    }
    if (rubric.length > 0) data.rubric = rubric
  }

  // Extract report settings
  const templateMatch = yaml.match(/template:\s*(.+?)(?:[\r\n]|$)/)
  if (templateMatch) data.report_template = templateMatch[1].trim()

  const emailMatch = yaml.match(/email_to:[\s\S]*?- (.+?)(?:[\r\n]|$)/)
  if (emailMatch) data.email_to = emailMatch[1].trim()

  const transcriptMatch = yaml.match(/include_transcript:\s*(true|false)/)
  if (transcriptMatch) data.include_transcript = transcriptMatch[1] === 'true'

  return data
}

export default function SkillBuilder({ onSaved, onCancel, editingId, initialYaml }: Props) {
  const [formData, setFormData] = useState<SkillFormData>(DEFAULT_FORM_DATA)
  const [activeTab, setActiveTab] = useState<'form' | 'yaml'>('form')
  const [yamlContent, setYamlContent] = useState('')
  const [yamlError, setYamlError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['basic']))

  // AI Generation dialog state
  const [showAiDialog, setShowAiDialog] = useState(false)
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiDescription, setAiDescription] = useState('')

  // Load initial data if editing
  useEffect(() => {
    if (initialYaml) {
      const parsed = parseYamlToFormData(initialYaml)
      setFormData(prev => ({ ...prev, ...parsed }))
      setYamlContent(initialYaml)
    }
  }, [initialYaml])

  // When switching to YAML tab, regenerate from form
  const handleTabChange = useCallback((tab: string) => {
    if (tab === 'yaml') {
      setYamlContent(generateYaml(formData))
      setYamlError(null)
    } else if (tab === 'form') {
      // Parse YAML back to form
      try {
        const parsed = parseYamlToFormData(yamlContent)
        setFormData(prev => ({ ...prev, ...parsed }))
        setYamlError(null)
      } catch {
        setYamlError('Could not parse YAML — check syntax before switching to form.')
        return
      }
    }
    setActiveTab(tab as 'form' | 'yaml')
  }, [formData, yamlContent])

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(section)) {
      newExpanded.delete(section)
    } else {
      newExpanded.add(section)
    }
    setExpandedSections(newExpanded)
  }

  const updateField = <K extends keyof SkillFormData>(field: K, value: SkillFormData[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const addInputField = () => {
    setFormData(prev => ({
      ...prev,
      input_schema: [
        ...prev.input_schema,
        { name: '', type: 'string', required: true, description: '' },
      ],
    }))
  }

  const updateInputField = (index: number, updates: Partial<InputSchemaField>) => {
    setFormData(prev => ({
      ...prev,
      input_schema: prev.input_schema.map((f, i) => i === index ? { ...f, ...updates } : f),
    }))
  }

  const removeInputField = (index: number) => {
    setFormData(prev => ({
      ...prev,
      input_schema: prev.input_schema.filter((_, i) => i !== index),
    }))
  }

  const addQuestion = () => {
    setFormData(prev => ({
      ...prev,
      questions: [
        ...prev.questions,
        {
          id: `q${prev.questions.length + 1}`,
          text: '',
          probes: ['Can you elaborate?'],
          competency: 'communication',
          max_follow_ups: 2,
        },
      ],
    }))
  }

  const updateQuestion = (index: number, updates: Partial<Question>) => {
    setFormData(prev => ({
      ...prev,
      questions: prev.questions.map((q, i) => i === index ? { ...q, ...updates } : q),
    }))
  }

  const removeQuestion = (index: number) => {
    setFormData(prev => ({
      ...prev,
      questions: prev.questions.filter((_, i) => i !== index),
    }))
  }

  const addProbe = (questionIndex: number) => {
    setFormData(prev => ({
      ...prev,
      questions: prev.questions.map((q, i) =>
        i === questionIndex ? { ...q, probes: [...q.probes, ''] } : q
      ),
    }))
  }

  const updateProbe = (questionIndex: number, probeIndex: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      questions: prev.questions.map((q, i) =>
        i === questionIndex
          ? { ...q, probes: q.probes.map((p, pi) => pi === probeIndex ? value : p) }
          : q
      ),
    }))
  }

  const removeProbe = (questionIndex: number, probeIndex: number) => {
    setFormData(prev => ({
      ...prev,
      questions: prev.questions.map((q, i) =>
        i === questionIndex
          ? { ...q, probes: q.probes.filter((_, pi) => pi !== probeIndex) }
          : q
      ),
    }))
  }

  const handleAiGenerate = async () => {
    setAiGenerating(true)
    try {
      const response: GenerateSkillPackResponse = await api.skillPacks.generate({
        description: aiDescription,
      })
      const parsed = parseYamlToFormData(response.yaml_content)
      setFormData(prev => ({ ...prev, ...parsed }))
      setShowAiDialog(false)
      setAiDescription('')
    } catch (err: unknown) {
      const msg = (err as Error).message ?? 'AI generation failed'
      setSaveError(msg)
    } finally {
      setAiGenerating(false)
    }
  }

  const handleSave = async () => {
    setIsSaving(true)
    setSaveError(null)
    try {
      let yaml: string
      if (activeTab === 'yaml') {
        yaml = yamlContent
      } else {
        if (formData.sections[0]?.mode === 'intelligent') {
          const objectives = formData.sections[0]?.objectives?.trim()
          if (!objectives) {
            throw new Error('Conversation Objectives are required for Intelligent mode')
          }
        }
        yaml = generateYaml(formData)
      }

      if (editingId) {
        await api.skillPacks.update(editingId, yaml)
      } else {
        await api.skillPacks.create(yaml)
      }
      onSaved?.()
    } catch (err: unknown) {
      const msg = (err as Error).message ?? 'Save failed'
      setSaveError(msg)
    } finally {
      setIsSaving(false)
    }
  }

  const SectionHeader = ({ title, section, badge }: { title: string; section: string; badge?: string }) => (
    <button
      onClick={() => toggleSection(section)}
      className="flex items-center justify-between w-full py-3 px-4 bg-muted/50 hover:bg-muted rounded-lg transition-colors"
    >
      <div className="flex items-center gap-2">
        <span className="font-medium">{title}</span>
        {badge && <Badge variant="secondary" className="text-xs">{badge}</Badge>}
      </div>
      {expandedSections.has(section) ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
    </button>
  )

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{editingId ? 'Edit Skill' : 'Skill Builder'}</h2>
          <p className="text-sm text-muted-foreground">
            {editingId ? 'Update the skill pack using the form or YAML editor below' : 'Create a new skill pack using the form or YAML editor below'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" asChild>
            <a href="/skill.md" target="_blank" rel="noopener noreferrer">
              <HelpCircle className="w-4 h-4 mr-1" /> Help
            </a>
          </Button>
          <Button variant="outline" onClick={onCancel} size="sm">Cancel</Button>
          <Button onClick={handleSave} disabled={isSaving} size="sm">
            {isSaving ? 'Saving…' : editingId ? 'Update Skill' : 'Create Skill'}
          </Button>
        </div>
      </div>

      {saveError && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive">
          {saveError}
        </div>
      )}

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="form">Form</TabsTrigger>
          <TabsTrigger value="yaml">YAML</TabsTrigger>
        </TabsList>

        {/* ------------------------------------------------------------------ */}
        {/* FORM TAB                                                             */}
        {/* ------------------------------------------------------------------ */}
        <TabsContent value="form" className="space-y-6 mt-4">

          {/* Basic Info */}
          <Card>
            <SectionHeader title="Basic Information" section="basic" />
            {expandedSections.has('basic') && (
              <CardContent className="space-y-4 pt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="skill_id">Skill ID <span className="text-destructive">*</span></Label>
                    <Input
                      id="skill_id"
                      value={formData.skill_id}
                      onChange={(e) => updateField('skill_id', e.target.value)}
                      placeholder="my-skill-v1"
                    />
                    <p className="text-xs text-muted-foreground">Unique identifier, e.g., complaint-handler-v1</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="name">Display Name <span className="text-destructive">*</span></Label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={(e) => updateField('name', e.target.value)}
                      placeholder="My Skill"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Channels</Label>
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2">
                      <Checkbox
                        checked={formData.channels.includes('teams')}
                        onCheckedChange={(checked: boolean) => {
                          const newChannels = checked
                            ? [...formData.channels, 'teams']
                            : formData.channels.filter(c => c !== 'teams')
                          updateField('channels', newChannels)
                        }}
                      />
                      <span className="text-sm">Teams</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <Checkbox
                        checked={formData.channels.includes('phone')}
                        onCheckedChange={(checked: boolean) => {
                          const newChannels = checked
                            ? [...formData.channels, 'phone']
                            : formData.channels.filter(c => c !== 'phone')
                          updateField('channels', newChannels)
                        }}
                      />
                      <span className="text-sm">Phone</span>
                    </label>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="max_duration">Max Duration (minutes)</Label>
                    <Input
                      id="max_duration"
                      type="number"
                      min={1}
                      max={120}
                      value={formData.max_duration_minutes}
                      onChange={(e) => updateField('max_duration_minutes', parseInt(e.target.value) || 30)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Language</Label>
                    <Select value={formData.language} onValueChange={(v) => updateField('language', v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {LANGUAGE_OPTIONS.map(l => (
                          <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Voice</Label>
                    <Select value={formData.tts_voice} onValueChange={(v) => updateField('tts_voice', v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {VOICE_OPTIONS.map(v => (
                          <SelectItem key={v.value} value={v.value}>{v.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Agent name: <span className="font-medium">{voiceToName(formData.tts_voice)}</span>
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label>AI Model</Label>
                    <Select value={formData.model} onValueChange={(v) => updateField('model', v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {MODEL_OPTIONS.map(m => (
                          <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="persona">Agent Persona <span className="text-destructive">*</span></Label>
                  <Textarea
                    id="persona"
                    value={formData.persona}
                    onChange={(e) => updateField('persona', e.target.value)}
                    placeholder={`You are ${voiceToName(formData.tts_voice)}, a professional AI assistant. You are warm, thorough, and genuinely curious. Ask one question at a time and listen carefully before responding.`}
                    rows={4}
                  />
                  <p className="text-xs text-muted-foreground">Use {'{{variable_name}}'} to reference input schema fields</p>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Input Schema */}
          <Card>
            <SectionHeader title="Input Schema" section="inputs" badge={`${formData.input_schema.length} fields`} />
            {expandedSections.has('inputs') && (
              <CardContent className="space-y-4 pt-4">
                <p className="text-sm text-muted-foreground">
                  Define inputs shown in the session launcher UI. Values are injected into the agent's context.
                </p>
                {formData.input_schema.map((field, index) => (
                  <div key={index} className="border rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Field {index + 1}</span>
                      <Button variant="ghost" size="sm" onClick={() => removeInputField(index)}>
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-2">
                        <Label className="text-xs">Field Name</Label>
                        <Input
                          value={field.name}
                          onChange={(e) => updateInputField(index, { name: e.target.value })}
                          placeholder="customer_name"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs">Type</Label>
                        <Select
                          value={field.type}
                          onValueChange={(v) => updateInputField(index, { type: v as InputSchemaField['type'] })}
                        >
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="string">String (single line)</SelectItem>
                            <SelectItem value="text">Text (multi-line)</SelectItem>
                            <SelectItem value="number">Number</SelectItem>
                            <SelectItem value="boolean">Boolean (Yes/No)</SelectItem>
                            <SelectItem value="enum">Enum (dropdown)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    {field.type === 'enum' && (
                      <div className="space-y-2">
                        <Label className="text-xs">Values (comma-separated)</Label>
                        <Input
                          value={field.values?.join(', ') || ''}
                          onChange={(e) => updateInputField(index, { values: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                          placeholder="option1, option2, option3"
                        />
                      </div>
                    )}
                    <div className="space-y-2">
                      <Label className="text-xs">Description</Label>
                      <Input
                        value={field.description}
                        onChange={(e) => updateInputField(index, { description: e.target.value })}
                        placeholder="Help text shown in UI"
                      />
                    </div>
                    <label className="flex items-center gap-2">
                      <Checkbox
                        checked={field.required}
                        onCheckedChange={(checked: boolean) => updateInputField(index, { required: checked })}
                      />
                      <span className="text-sm">Required field</span>
                    </label>
                  </div>
                ))}
                <Button variant="outline" size="sm" onClick={addInputField} className="w-full">
                  <Plus className="w-4 h-4 mr-2" /> Add Input Field
                </Button>
              </CardContent>
            )}
          </Card>

          {/* Conversation Flow */}
          <Card>
            <SectionHeader
              title="Conversation Flow"
              section="questions"
              badge={formData.sections[0]?.mode === 'intelligent' ? 'Intelligent' : `${formData.questions.length} questions`}
            />
            {expandedSections.has('questions') && (
              <CardContent className="space-y-4 pt-4">
                <div className="space-y-2">
                  <Label>Conversation Mode</Label>
                  <Select
                    value={formData.sections[0]?.mode || 'guided'}
                    onValueChange={(value: 'guided' | 'intelligent') => {
                      setFormData(prev => ({
                        ...prev,
                        sections: [{
                          ...prev.sections[0],
                          mode: value,
                          objectives: value === 'intelligent' ? prev.sections[0]?.objectives || '' : undefined,
                          questions: value === 'guided' ? prev.sections[0]?.questions || prev.questions : undefined,
                        }],
                      }))
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="guided">
                        <span className="flex items-center gap-2">
                          <span>📋</span>
                          <span>Guided — Fixed questions with probes</span>
                        </span>
                      </SelectItem>
                      <SelectItem value="intelligent">
                        <span className="flex items-center gap-2">
                          <span>🧠</span>
                          <span>Intelligent — Context-aware objectives</span>
                        </span>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {formData.sections[0]?.mode === 'intelligent'
                      ? 'The agent guides the conversation naturally to meet the objectives. Ask one question at a time.'
                      : 'The agent follows the predefined questions in order, using probes to deepen answers.'}
                  </p>
                </div>

                {formData.sections[0]?.mode === 'intelligent' ? (
                  <div className="space-y-2">
                    <Label htmlFor="objectives">
                      Conversation Objectives
                      <span className="text-destructive ml-1">*</span>
                    </Label>
                    <Textarea
                      id="objectives"
                      value={formData.sections[0]?.objectives || ''}
                      onChange={(e) => {
                        setFormData(prev => ({
                          ...prev,
                          sections: [{
                            ...prev.sections[0],
                            objectives: e.target.value,
                          }],
                        }))
                      }}
                      placeholder="Describe what the agent should uncover through natural conversation. Number each objective. Example:&#10;1. Understand the customer's current pain points and situation&#10;2. Identify decision-maker and buying process&#10;3. Assess urgency and budget&#10;4. Agree on clear next steps"
                      rows={8}
                      className={!formData.sections[0]?.objectives?.trim() ? 'border-destructive' : ''}
                    />
                    <p className="text-xs text-muted-foreground">
                      The agent will adapt its questions dynamically and check off objectives as they are covered.
                    </p>
                  </div>
                ) : (
                  <>
                    {formData.questions.map((question, qIndex) => (
                      <div key={qIndex} className="border rounded-lg p-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">Question {qIndex + 1}</span>
                          <Button variant="ghost" size="sm" onClick={() => removeQuestion(qIndex)}>
                            <Trash2 className="w-4 h-4 text-destructive" />
                          </Button>
                        </div>
                        <div className="space-y-2">
                          <Label className="text-xs">Question Text</Label>
                          <Textarea
                            value={question.text}
                            onChange={(e) => updateQuestion(qIndex, { text: e.target.value })}
                            placeholder="What would you like to ask?"
                            rows={2}
                          />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="space-y-2">
                            <Label className="text-xs">Competency</Label>
                            <Input
                              value={question.competency}
                              onChange={(e) => updateQuestion(qIndex, { competency: e.target.value })}
                              placeholder="communication"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label className="text-xs">Max Follow-ups</Label>
                            <Input
                              type="number"
                              min={0}
                              max={10}
                              value={question.max_follow_ups}
                              onChange={(e) => updateQuestion(qIndex, { max_follow_ups: parseInt(e.target.value) || 0 })}
                            />
                          </div>
                        </div>
                        <div className="space-y-2">
                          <Label className="text-xs">Probes (follow-up prompts if answer is shallow)</Label>
                          {question.probes.map((probe, pIndex) => (
                            <div key={pIndex} className="flex gap-2">
                              <Input
                                value={probe}
                                onChange={(e) => updateProbe(qIndex, pIndex, e.target.value)}
                                placeholder={`Probe ${pIndex + 1}`}
                              />
                              <Button variant="ghost" size="sm" onClick={() => removeProbe(qIndex, pIndex)}>
                                <Trash2 className="w-4 h-4 text-destructive" />
                              </Button>
                            </div>
                          ))}
                          <Button variant="outline" size="sm" onClick={() => addProbe(qIndex)}>
                            <Plus className="w-4 h-4 mr-2" /> Add Probe
                          </Button>
                        </div>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addQuestion} className="w-full">
                      <Plus className="w-4 h-4 mr-2" /> Add Question
                    </Button>
                  </>
                )}
              </CardContent>
            )}
          </Card>

          {/* Report Settings */}
          <Card>
            <SectionHeader title="Report Settings" section="report" />
            {expandedSections.has('report') && (
              <CardContent className="space-y-4 pt-4">
                <div className="space-y-2">
                  <Label>Report Template</Label>
                  <Select value={formData.report_template} onValueChange={(v) => updateField('report_template', v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {REPORT_TEMPLATES.map(t => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email_to">Report Email</Label>
                  <Input
                    id="email_to"
                    value={formData.email_to}
                    onChange={(e) => updateField('email_to', e.target.value)}
                    placeholder="admin@example.com"
                  />
                </div>
                <label className="flex items-center gap-2">
                  <Checkbox
                    checked={formData.include_transcript}
                    onCheckedChange={(checked: boolean) => updateField('include_transcript', checked)}
                  />
                  <span className="text-sm">Include transcript in report</span>
                </label>
              </CardContent>
            )}
          </Card>

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setShowAiDialog(true)}
              className="mr-auto"
            >
              <Sparkles className="w-4 h-4 mr-2" />
              Generate with AI
            </Button>
            <Button variant="outline" onClick={onCancel}>Cancel</Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? 'Saving…' : editingId ? 'Update Skill' : 'Create Skill'}
            </Button>
          </div>
        </TabsContent>

        {/* ------------------------------------------------------------------ */}
        {/* YAML TAB                                                             */}
        {/* ------------------------------------------------------------------ */}
        <TabsContent value="yaml" className="mt-4 space-y-3">
          <p className="text-xs text-muted-foreground">
            Edit the raw YAML directly. Switch back to Form to sync changes into the form fields.
          </p>
          {yamlError && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive">
              {yamlError}
            </div>
          )}
          <Textarea
            value={yamlContent}
            onChange={(e) => setYamlContent(e.target.value)}
            className="font-mono text-xs min-h-[600px] resize-y"
            spellCheck={false}
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onCancel}>Cancel</Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? 'Saving…' : editingId ? 'Update Skill' : 'Create Skill'}
            </Button>
          </div>
        </TabsContent>
      </Tabs>

      {/* AI Generation Dialog */}
      <Dialog open={showAiDialog} onOpenChange={setShowAiDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5" />
              Generate Skill with AI
            </DialogTitle>
            <DialogDescription>
              Describe your skill and AI will generate questions, rubric, and persona automatically.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="ai-description">What should this skill do? *</Label>
              <Textarea
                id="ai-description"
                value={aiDescription}
                onChange={(e) => setAiDescription(e.target.value)}
                placeholder="Example: A technical interview for senior backend engineers covering system design, API design, and debugging. 45 minutes. Guided mode with specific questions. Hire/no-hire scorecard."
                rows={6}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAiDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAiGenerate}
              disabled={aiGenerating || !aiDescription.trim()}
            >
              {aiGenerating ? 'Generating…' : 'Generate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
