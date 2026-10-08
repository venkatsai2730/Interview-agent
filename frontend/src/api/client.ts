const BASE = '/api'

export interface SectionSummary {
  mode: string
  questions: string[]
  objectives: string | null
}

export interface SkillPackSummary {
  id: string
  name: string
  skill_id: string
  version: string
  is_active: boolean
  channels: string[]
  created_at: string
  yaml_content: string
  sections_summary: SectionSummary[]
}

export interface SkillPackVersionRecord {
  version_number: number
  yaml_content: string
  created_at: string
  change_summary: string | null
}

export interface GenerateSkillPackRequest {
  description: string
}

export interface GenerateSkillPackResponse {
  yaml_content: string
}

export interface SessionCreated {
  session_id: string
  status: string
}

export interface SessionDetail {
  session_id: string
  status: 'PENDING' | 'JOINING' | 'ACTIVE' | 'CLOSING' | 'COMPLETED' | 'FAILED'
  current_question_text: string | null
  turn_count: number
  elapsed_seconds: number
  has_report: boolean
  error: string | null
}

export interface SessionDetail {
  session_id: string
  status: 'PENDING' | 'JOINING' | 'ACTIVE' | 'CLOSING' | 'COMPLETED' | 'FAILED'
  channel: 'teams' | 'phone' | null
  current_question_text: string | null
  current_question_index: number
  turn_count: number
  elapsed_seconds: number
  has_report: boolean
  error: string | null
  turn_latencies: Array<{ turn_index: number; latency_ms: number }>
  p50_latency_ms: number | null
  p90_latency_ms: number | null
  skill_pack_name: string | null
  recording_url: string | null
}

export interface SessionListItem {
  session_id: string
  skill_pack_name: string
  skill_pack_id: string
  status: string
  channel: 'teams' | 'phone' | null
  created_at: string
  started_at: string | null
  ended_at: string | null
  duration_minutes: number | null
  has_report: boolean
  recording_url: string | null
  recall_recording_url: string | null
}

export interface SessionListResponse {
  items: SessionListItem[]
  total: number
  page: number
  page_size: number
}

export interface ReportListItem {
  session_id: string
  skill_pack_name: string | null
  template: string
  generated_at: string
  recommendation: string | null
}

export interface ReportListResponse {
  items: ReportListItem[]
  total: number
  page: number
  page_size: number
}

export interface QuestionScore {
  question_id: string
  question_text: string
  competency: string
  score: number
  score_rationale: string
  follow_up_count: number
  skipped: boolean
}

export interface ReportContent {
  recommendation?: string
  scores?: QuestionScore[]
  competency_summary?: Record<string, number>
  transcript?: Array<{ speaker: string; text: string; timestamp_ms: number }>
  questions_not_reached?: string[]
  duration_minutes?: number
  skill_pack_name?: string
  // discovery-brief / audit-log / coaching-report fields
  [key: string]: unknown
}

export interface ReportDetail {
  session_id: string
  template: string
  content: ReportContent
  generated_at: string
  email_sent: boolean
  chat_posted: boolean
}

export interface TurnRecord {
  turn_index: number
  speaker: string
  transcript: string
  timestamp_ms: number | null
  question_id: string | null
  score: number | null
  score_rationale: string | null
  competency: string | null
  flags: string[] | null
  action: string | null
}

export interface TranscriptResponse {
  session_id: string
  turns: TurnRecord[]
}

export interface RecordingInfo {
  recording_sid: string
  call_sid: string
  duration_sec: number
  status: string
  date_created: string
  uri: string
}

export interface RecordingListResponse {
  session_id: string
  twilio_call_sid: string | null
  recordings: RecordingInfo[]
}

export interface EventListItem {
  id: number
  type: string
  session_id: string | null
  timestamp: string
  detail: Record<string, unknown> | null
}

export interface EventListResponse {
  items: EventListItem[]
  total: number
  page: number
  page_size: number
}

export interface DependencyStatus {
  status: 'ok' | 'degraded' | 'down'
  latency_ms: number
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'down'
  dependencies: {
    db: DependencyStatus
    recall: DependencyStatus
    sarvam: DependencyStatus
  }
}

// API token for authentication - in production, this should come from env or auth flow
// Vite replaces import.meta.env at build time
export const API_TOKEN = import.meta.env.VITE_API_TOKEN || 'vero-dev-token-change-in-production'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_TOKEN}`,
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    // 422 on validate is expected — don't throw a noisy Error, just reject with structured body
    const err = Object.assign(new Error(body.detail ?? res.statusText), { status: res.status, body })
    return Promise.reject(err)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export interface InputSchemaField {
  name: string
  type: 'string' | 'number' | 'boolean' | 'enum' | 'text' | 'file'
  required?: boolean
  description?: string
  values?: string[]  // For enum type
}

export const api = {
  sessions: {
    create: (skill_pack_id: string, meeting_url: string, tts_voice?: string, llm_model?: string, agent_name?: string, context_data?: Record<string, unknown>, language?: string) =>
      request<SessionCreated>('/sessions', {
        method: 'POST',
        body: JSON.stringify({ skill_pack_id, meeting_url, tts_voice, llm_model, agent_name, context_data, language }),
      }),
    createPhone: (skill_pack_id: string, phone_number: string, context_data?: Record<string, unknown>) =>
      request<SessionCreated>('/sessions/phone', {
        method: 'POST',
        body: JSON.stringify({ skill_pack_id, phone_number, context_data }),
      }),
    createPhoneLiveKit: (skill_pack_id: string, phone_number: string, tts_voice?: string, llm_model?: string, agent_name?: string, context_data?: Record<string, unknown>, language?: string) =>
      request<SessionCreated>('/sessions/phone-livekit', {
        method: 'POST',
        body: JSON.stringify({ skill_pack_id, phone_number, tts_voice, llm_model, agent_name, context_data, language }),
      }),
    analyzeResume: async (resumeFile: File, jdFile?: File, jdText?: string): Promise<{ analysis: Record<string, string>; resume_text: string; jd_text: string }> => {
      const formData = new FormData()
      formData.append('resume', resumeFile)
      if (jdFile) formData.append('job_description', jdFile)
      if (jdText) formData.append('job_description_text', jdText)
      const res = await fetch(`${BASE}/sessions/analyze-resume`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${API_TOKEN}` },
        body: formData,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(body.detail ?? res.statusText)
      }
      return res.json()
    },
    get: (sessionId: string) =>
      request<SessionDetail>(`/sessions/${sessionId}`),
    delete: (sessionId: string) =>
      request<void>(`/sessions/${sessionId}`, { method: 'DELETE' }),
    list: (params: { status?: string; page?: number; page_size?: number } = {}) => {
      const qs = new URLSearchParams()
      if (params.status) qs.set('status', params.status)
      if (params.page) qs.set('page', String(params.page))
      if (params.page_size) qs.set('page_size', String(params.page_size))
      const query = qs.toString()
      return request<SessionListResponse>(`/sessions${query ? `?${query}` : ''}`)
    },
  },
  reports: {
    list: (params: { template?: string; channel?: string; from_date?: string; to_date?: string; page?: number; page_size?: number } = {}) => {
      const qs = new URLSearchParams()
      if (params.template) qs.set('template', params.template)
      if (params.channel) qs.set('channel', params.channel)
      if (params.from_date) qs.set('from_date', params.from_date)
      if (params.to_date) qs.set('to_date', params.to_date)
      if (params.page) qs.set('page', String(params.page))
      if (params.page_size) qs.set('page_size', String(params.page_size))
      const query = qs.toString()
      return request<ReportListResponse>(`/reports${query ? `?${query}` : ''}`)
    },
    get: (sessionId: string) =>
      request<ReportDetail>(`/reports/${sessionId}`),
    getTranscript: (sessionId: string) =>
      request<TranscriptResponse>(`/sessions/${sessionId}/transcript`),
    getRecordings: (sessionId: string) =>
      request<RecordingListResponse>(`/sessions/${sessionId}/recordings`),
    downloadRecording: (sessionId: string, recordingSid: string) =>
      `${BASE}/sessions/${sessionId}/recordings/${recordingSid}/download`,
  },
  skillPacks: {
    list: () => request<SkillPackSummary[]>('/skill-packs'),
    create: (yaml_content: string, change_summary?: string) =>
      request<SkillPackSummary>('/skill-packs', {
        method: 'POST',
        body: JSON.stringify({ yaml_content, change_summary }),
      }),
    update: (id: string, yaml_content: string, change_summary?: string) =>
      request<SkillPackSummary>(`/skill-packs/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ yaml_content, change_summary }),
      }),
    delete: (id: string) =>
      request<void>(`/skill-packs/${id}`, { method: 'DELETE' }),
    activate: (id: string) =>
      request<SkillPackSummary>(`/skill-packs/${id}/activate`, { method: 'POST' }),
    deactivate: (id: string) =>
      request<SkillPackSummary>(`/skill-packs/${id}/deactivate`, { method: 'POST' }),
    versions: (id: string) =>
      request<SkillPackVersionRecord[]>(`/skill-packs/${id}/versions`),
    validate: (yaml_content: string) =>
      request<{ valid: boolean }>('/skill-packs/validate', {
        method: 'POST',
        body: JSON.stringify({ yaml_content }),
      }),
    generate: (params: GenerateSkillPackRequest) =>
      request<GenerateSkillPackResponse>('/skill-packs/generate', {
        method: 'POST',
        body: JSON.stringify(params),
      }),
    clone: (id: string) =>
      request<SkillPackSummary>(`/skill-packs/${id}/clone`, { method: 'POST' }),
  },
  events: {
    list: (params: { session_id?: string; type?: string; page?: number; page_size?: number } = {}) => {
      const qs = new URLSearchParams()
      if (params.session_id) qs.set('session_id', params.session_id)
      if (params.type) qs.set('type', params.type)
      if (params.page) qs.set('page', String(params.page))
      if (params.page_size) qs.set('page_size', String(params.page_size))
      const query = qs.toString()
      return request<EventListResponse>(`/events${query ? `?${query}` : ''}`)
    },
  },
  health: {
    get: () => request<HealthResponse>('/health'),
  },
}
