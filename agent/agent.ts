// pi_agent RPC server — reads JSONL from stdin, writes JSONL to stdout
// Manages one pi_agent session per Vero session
// Uses Sarvam AI for LLM (OpenAI-compatible API)

import { Static, Type } from '@sinclair/typebox'
import { Value } from '@sinclair/typebox/value'
import * as readline from 'readline'
import { SkillPackState } from './skill_pack_state.js'
import { saveCheckpoint, loadCheckpoint, deleteCheckpoint } from './checkpoint.js'

// ── TypeBox schemas ──────────────────────────────────────────────────────────

const ModelPreference = Type.Object({
  provider: Type.Literal('sarvam'),
  model: Type.String()  // e.g., "sarvam-30b", "sarvam-105b"
})

const Question = Type.Object({
  id: Type.String(),
  text: Type.String(),
  probes: Type.Array(Type.String()),
  competency: Type.String(),
  max_follow_ups: Type.Integer({ minimum: 0, maximum: 10, default: 2 })
})

const Section = Type.Object({
  id: Type.String(),
  title: Type.String(),
  mode: Type.Optional(Type.String()),
  questions: Type.Optional(Type.Array(Question)),
  objectives: Type.Optional(Type.String()),
})

const RubricEntry = Type.Object({
  competency: Type.String(),
  scores: Type.Object({
    '1': Type.String(),
    '2': Type.String(),
    '3': Type.String(),
    '4': Type.String(),
    '5': Type.String()
  })
})

const ReportConfig = Type.Object({
  template: Type.Union([
    Type.Literal('scorecard'),
    Type.Literal('discovery-brief'),
    Type.Literal('audit-log'),
    Type.Literal('coaching-report')
  ]),
  email_to: Type.Array(Type.String()),
  include_transcript: Type.Boolean({ default: true })
})

export const SkillPackSchema = Type.Object({
  skill: Type.Object({
    id: Type.String(),
    name: Type.String(),
    version: Type.String()
  }),
  agent: Type.Object({
    name: Type.String(),
    persona: Type.String(),
    language: Type.String({ default: 'en-US' }),
    max_duration_minutes: Type.Integer({ minimum: 1, maximum: 120 }),
    model_preferences: Type.Array(ModelPreference),
    tts_voice: Type.String({ default: 'sarvam:shubh' }),
    eou_threshold_seconds: Type.Number({ minimum: 0.5, maximum: 5.0, default: 2.5 })
  }),
  sections: Type.Array(Section),
  rubric: Type.Array(RubricEntry),
  report: ReportConfig
})

export type SkillPack = Static<typeof SkillPackSchema>

const ActionEnum = Type.Union([
  Type.Literal('follow_up'),
  Type.Literal('clarify'),
  Type.Literal('advance'),
  Type.Literal('close')
])

const FlagEnum = Type.Union([
  Type.Literal('incomplete'),
  Type.Literal('off_topic'),
  Type.Literal('strong_signal'),
  Type.Literal('redirect_needed')
])

export const TurnOutputSchema = Type.Object({
  next_utterance: Type.String({ minLength: 1 }),
  action: ActionEnum,
  question_id: Type.String(),
  score: Type.Union([Type.Integer({ minimum: 1, maximum: 5 }), Type.Null()]),
  score_rationale: Type.Union([Type.String(), Type.Null()]),
  competency: Type.String(),
  flags: Type.Array(FlagEnum)
})

export type TurnOutput = Static<typeof TurnOutputSchema>

// ── Validation ───────────────────────────────────────────────────────────────

export function validateTurnOutput(raw: unknown): TurnOutput {
  if (Value.Check(TurnOutputSchema, raw)) {
    return raw as TurnOutput
  }
  const errors = [...Value.Errors(TurnOutputSchema, raw)]
    .map(e => `${e.path}: ${e.message}`)
    .join('; ')
  throw new Error(`TurnOutput validation failed: ${errors}`)
}

// ── Inbound RPC message types ────────────────────────────────────────────────

export interface SessionStartMessage {
  type: 'session_start'
  session_id: string
  skill_pack: SkillPack
}

export interface TurnMessage {
  type: 'turn'
  session_id: string
  speaker: string
  transcript: string
  turn_index: number
  timestamp_ms: number
}

export interface SessionEndMessage {
  type: 'session_end'
  session_id: string
  reason: 'all_questions_complete' | 'max_duration_reached' | 'manual'
}

export interface SilenceTimeoutMessage {
  type: 'silence_timeout'
  session_id: string
  silence_duration_ms: number
  consecutive_count: number
}

export type InboundMessage =
  | SessionStartMessage
  | TurnMessage
  | SessionEndMessage
  | SilenceTimeoutMessage

// ── Outbound RPC message types ───────────────────────────────────────────────

export interface TurnOutputMessage extends TurnOutput {
  type: 'turn_output'
  session_id: string
  turn_index: number
}

export interface SessionSummaryMessage {
  type: 'session_summary'
  session_id: string
  scores: Array<{
    question_id: string
    competency: string
    score: number
    rationale: string
  }>
  transcript: Array<{
    speaker: string
    transcript: string
    turn_index: number
    timestamp_ms: number
  }>
  questions_not_reached: string[]
}

export interface ErrorMessage {
  type: 'error'
  session_id?: string
  message: string
}

// ── Session context ──────────────────────────────────────────────────────────

export interface SessionContext {
  session_id: string
  skill_pack: SkillPack
  state: SkillPackState
  transcript_history: TurnMessage[]
  lastVeroUtterance: string
  context_data?: Record<string, unknown>  // Input data for skills with input_schema
}

// ── Session map (multi-session isolation) ────────────────────────────────────

const sessions = new Map<string, SessionContext>()

// ── Output helper ────────────────────────────────────────────────────────────

function send(msg: object): void {
  process.stdout.write(JSON.stringify(msg) + '\n')
}

// ── Sarvam AI LLM Client ─────────────────────────────────────────────────────

const SARVAM_API_URL = 'https://api.sarvam.ai/v1/chat/completions'
const SARVAM_API_KEY = process.env.SARVAM_API_KEY || ''
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || ''
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY || ''
const GCP_PROJECT = process.env.GOOGLE_CLOUD_PROJECT || ''
const GCP_LOCATION = process.env.GOOGLE_CLOUD_LOCATION || 'us-central1'

// Vertex AI model mapping
const VERTEX_AI_MODELS: Record<string, string> = {
  'gemini-2.5-flash': 'gemini-2.5-flash',
  'gemini-2.5-pro': 'gemini-2.5-pro',
}

// OpenRouter model mapping (fallback)
const OPENROUTER_MODELS: Record<string, string> = {
  'gemini-2.5-flash': 'google/gemini-2.5-flash',
  'gpt-4o-mini': 'openai/gpt-4o-mini',
  'gpt-4o': 'openai/gpt-4o',
}

// Cache for Vertex AI access token
let _vertexToken: string | null = null
let _vertexTokenExpiry = 0

async function getVertexAIToken(): Promise<string> {
  const now = Date.now()
  if (_vertexToken && now < _vertexTokenExpiry - 60000) {
    return _vertexToken
  }
  const { GoogleAuth } = await import('google-auth-library')
  const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] })
  const client = await auth.getClient()
  const tokenResponse = await client.getAccessToken()
  _vertexToken = tokenResponse.token || ''
  _vertexTokenExpiry = now + 3500000 // ~58 minutes
  return _vertexToken
}

interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

interface SarvamChatResponse {
  id: string
  choices: Array<{
    index: number
    message: {
      role: string
      content: string
    }
    finish_reason: string
  }>
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
}

/**
 * Call Sarvam LLM via OpenAI-compatible API.
 */
async function callLLM(
  model: string,
  systemPrompt: string,
  messages: Array<{ role: 'user' | 'assistant'; content: string; timestamp?: number }>,
  extraUserMessage?: string
): Promise<string> {
  const chatMessages: ChatMessage[] = [
    { role: 'system', content: systemPrompt }
  ]

  for (const msg of messages) {
    chatMessages.push({ role: msg.role, content: msg.content })
  }

  if (extraUserMessage) {
    chatMessages.push({ role: 'user', content: extraUserMessage })
  }

  const payload = {
    model: model,
    messages: chatMessages,
    temperature: 0.5,
    max_tokens: 2000
  }

  // Route to the right provider based on model name
  let apiUrl: string
  let headers: Record<string, string> = { 'Content-Type': 'application/json' }
  let actualModel = model

  if (VERTEX_AI_MODELS[model] && GCP_PROJECT) {
    // Use Vertex AI directly (gcloud ADC auth, no API key cost)
    const vertexModel = VERTEX_AI_MODELS[model]
    const token = await getVertexAIToken()
    apiUrl = `https://${GCP_LOCATION}-aiplatform.googleapis.com/v1/projects/${GCP_PROJECT}/locations/${GCP_LOCATION}/publishers/google/models/${vertexModel}:generateContent`
    headers['Authorization'] = `Bearer ${token}`
    // Vertex AI uses a different payload format
    const vertexPayload = {
      contents: chatMessages
        .filter(m => m.role !== 'system')
        .map(m => ({ role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] })),
      systemInstruction: { parts: [{ text: chatMessages.find(m => m.role === 'system')?.content || '' }] },
      generationConfig: { temperature: 0.5, maxOutputTokens: 2000 },
    }
    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(vertexPayload)
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Vertex AI error ${response.status}: ${errorText.slice(0, 500)}`)
      }
      const data = await response.json() as any
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text
      if (!text) throw new Error('No text in Vertex AI response')
      return text
    } catch (err) {
      console.error(`Vertex AI call failed: ${(err as Error).message}, falling back to OpenRouter`)
      // Fall through to OpenRouter
    }
  }

  if (OPENROUTER_MODELS[model] && OPENROUTER_API_KEY) {
    apiUrl = 'https://openrouter.ai/api/v1/chat/completions'
    headers['Authorization'] = `Bearer ${OPENROUTER_API_KEY}`
    actualModel = OPENROUTER_MODELS[model]
  } else if (model.startsWith('gpt-') && OPENAI_API_KEY) {
    apiUrl = 'https://api.openai.com/v1/chat/completions'
    headers['Authorization'] = `Bearer ${OPENAI_API_KEY}`
  } else {
    apiUrl = SARVAM_API_URL
    headers['api-subscription-key'] = SARVAM_API_KEY
  }

  // Override model in payload if mapped
  payload.model = actualModel

  try {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`LLM API error ${response.status}: ${errorText.slice(0, 500)}`)
    }

    const data = await response.json() as SarvamChatResponse

    if (!data.choices || data.choices.length === 0) {
      throw new Error('No choices returned from LLM API')
    }

    return data.choices[0].message.content
  } catch (err) {
    throw new Error(`LLM call failed: ${(err as Error).message}`)
  }
}

// ── Message handlers ─────────────────────────────────────────────────────────

/**
 * Substitute template variables in a string with values from context_data.
 * Supports {{variable}} syntax.
 */
function substituteContextTemplates(text: string, context_data?: Record<string, unknown>): string {
  if (!context_data) return text
  
  return text.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    const value = context_data[key]
    return value !== undefined ? String(value) : match
  })
}

/**
 * Build the system prompt for a turn, incorporating persona, current question,
 * rubric, and scoring history.
 */
function buildSystemPrompt(ctx: SessionContext): string {
  const { skill_pack, state, context_data } = ctx
  // Substitute context variables in persona
  const persona = substituteContextTemplates(skill_pack.agent.persona, context_data)
  const currentQuestion = state.currentQuestion

  let prompt = `${persona}\n\n`
  
  // Add context data section if available
  if (context_data && Object.keys(context_data).length > 0) {
    prompt += `## Context Information\n`
    for (const [key, value] of Object.entries(context_data)) {
      prompt += `- ${key}: ${value}\n`
    }
    prompt += `\n`
  }

  if (currentQuestion) {
    prompt += `## Current Question\n`
    prompt += `ID: ${currentQuestion.id}\n`
    prompt += `Text: ${currentQuestion.text}\n`
    if (currentQuestion.probes.length > 0) {
      prompt += `Probes: ${currentQuestion.probes.join(' | ')}\n`
    }
    prompt += `Competency: ${currentQuestion.competency}\n\n`
    
    // Add follow-up count info
    const followUpCount = state.getFollowUpCount(currentQuestion.id)
    const maxFollowUps = currentQuestion.max_follow_ups ?? 2
    if (followUpCount > 0) {
      prompt += `Follow-up attempt: ${followUpCount} of ${maxFollowUps}\n\n`
    }

    // Include rubric for current competency
    const rubricEntry = skill_pack.rubric.find(r => r.competency === currentQuestion.competency)
    if (rubricEntry) {
      prompt += `## Scoring Rubric for "${rubricEntry.competency}"\n`
      for (const [score, desc] of Object.entries(rubricEntry.scores)) {
        prompt += `Score ${score}: ${desc}\n`
      }
      prompt += '\n'
    }
  }

  // Include scoring history
  const scores = state.getScores()
  if (scores.length > 0) {
    prompt += `## Scoring History\n`
    for (const s of scores) {
      prompt += `- ${s.question_id} (${s.competency}): score=${s.score} — ${s.rationale}\n`
    }
    prompt += '\n'
  }

  prompt += `## Conversation History\n`
  if (ctx.transcript_history.length > 0) {
    // Show last 10 turns to give context without overwhelming
    const recentHistory = ctx.transcript_history.slice(-10)
    for (const turn of recentHistory) {
      prompt += `- [${turn.speaker}]: ${turn.transcript}\n`
    }
  } else {
    prompt += `(No previous conversation)\n`
  }
  prompt += `\n`

  prompt += `## Instructions\n`
  prompt += `1. Read the conversation history carefully - DO NOT ask a question that has already been asked or answered.\n`
  prompt += `2. NEVER re-introduce yourself. The session has already started. Do NOT say "Hi", "Hello", "I'm [name]", or "Thanks for joining" again.\n`
  prompt += `3. ACTION SELECTION - Choose EXACTLY ONE:\n`
  prompt += `   - "advance": Use when the user has PROVIDED AN ANSWER to the current question, even if brief. Score 1-5 based on quality.\n`
  prompt += `   - "clarify": Use ONLY when the user's response is COMPLETELY UNCLEAR or OFF-TOPIC (max ${currentQuestion?.max_follow_ups ?? 2} times per question).\n`
  prompt += `   - "follow_up": Use ONLY when the user asked YOU to repeat or clarify YOUR previous statement.\n`
  prompt += `   - "close": Use when ALL questions are complete.\n\n`
  prompt += `4. CRITICAL: If the user said ANYTHING relevant to the current question, use "advance" with an appropriate score. Do NOT clarify unless their response was completely unrelated.\n`
  prompt += `5. SPEECH FRAGMENTS: The STT system sometimes delivers incomplete phrases (e.g., "in the trucks and excavators", "difficult patterns in the data"). These are continuations of earlier speech, NOT new complete answers. When you see such fragments, COMBINE them with the previous turns in your mental model before deciding. Score based on the TOTAL picture across all turns for this question, not just the last fragment.\n`
  prompt += `6. If the user says "hello", "hi", "yes", "sure", "okay" — these are acknowledgments. Accept them and ask your NEXT question. Do NOT re-greet.\n`
  prompt += `7. AVOID REPETITION: Do not ask the same question or sub-question more than once. If you have already asked about "type of encoders" and not received detail, accept whatever was given and advance.\n`
  prompt += `8. Progress naturally through questions - don't go backwards.\n`
  prompt += `9. If all questions are complete, use "close" to end the session.\n`
  prompt += `10. PHONE CALLS: When you use "close", the call will automatically hang up after your closing statement.\n`
  prompt += `11. Keep responses to 1-2 sentences. Be concise and conversational.\n\n`

  prompt += `## Response Format\n`
  prompt += `You MUST respond with a single JSON object matching this schema exactly:\n`
  prompt += `{\n`
  prompt += `  "next_utterance": "<string, what Vero says next, non-empty - be natural and conversational>",\n`
  prompt += `  "action": "<follow_up|clarify|advance|close>",\n`
  prompt += `  "question_id": "<string, current question id>",\n`
  prompt += `  "score": <integer 1-5 or null — only set when action is advance or close>,\n`
  prompt += `  "score_rationale": "<string or null — required when score is set>",\n`
  prompt += `  "competency": "<string, competency being evaluated>",\n`
  prompt += `  "flags": ["incomplete"|"off_topic"|"strong_signal"|"redirect_needed"]\n`
  prompt += `}\n`
  prompt += `Respond with ONLY the JSON object, no markdown, no explanation.`

  return prompt
}

/**
 * Calculate simple string similarity (0-1) using Jaccard similarity of word sets.
 */
function calculateSimilarity(a: string, b: string): number {
  if (!a || !b) return 0
  const wordsA = new Set(a.toLowerCase().split(/\s+/))
  const wordsB = new Set(b.toLowerCase().split(/\s+/))
  const intersection = new Set([...wordsA].filter(x => wordsB.has(x)))
  const union = new Set([...wordsA, ...wordsB])
  return intersection.size / union.size
}

/**
 * Generate a varied version of an utterance to avoid repetition.
 */
async function generateVariedUtterance(ctx: SessionContext, originalUtterance: string): Promise<string> {
  const modelPref = ctx.skill_pack.agent.model_preferences[0]
  const model = modelPref.model

  const variationPrompt = 
    `You are ${ctx.skill_pack.agent.name}. Rephrase the following message to convey the same meaning ` +
    `but using different words. Be natural and conversational:\n\n` +
    `Original: "${originalUtterance}"\n\n` +
    `Respond with ONLY the rephrased message — no quotes, no explanation.`

  const messages: Array<{ role: 'user' | 'assistant'; content: string }> = []

  return await callLLM(model, variationPrompt, messages)
}

/**
 * Extract JSON from LLM response text (handles cases where the model wraps in markdown).
 */
function extractJson(text: string): unknown {
  // Try direct parse first
  try {
    return JSON.parse(text.trim())
  } catch {
    // Try to extract from markdown code block
    const match = text.match(/```(?:json)?\s*([\s\S]*?)```/)
    if (match) {
      return JSON.parse(match[1].trim())
    }
    // Try to find first { ... } block
    const start = text.indexOf('{')
    const end = text.lastIndexOf('}')
    if (start !== -1 && end !== -1) {
      return JSON.parse(text.slice(start, end + 1))
    }
    throw new Error('No JSON found in LLM response')
  }
}

/**
 * Process a turn: call LLM, validate output, apply state, return TurnOutput.
 * Transcript must already be appended to ctx.transcript_history before calling.
 */
export async function processTurn(ctx: SessionContext, msg: TurnMessage): Promise<TurnOutput> {
  console.error(`[${ctx.session_id}] processTurn: currentQuestion=${ctx.state.currentQuestion?.id ?? 'NONE'}, totalQuestions=${ctx.state.allQuestions.length}`)
  
  const systemPrompt = buildSystemPrompt(ctx)
  const modelPref = ctx.skill_pack.agent.model_preferences[0]
  const model = modelPref.model

  // Build messages from transcript history.
  // Vero turns → role:'assistant' so the LLM recognises what it already said and
  // never re-introduces itself. Participant turns → role:'user'.
  const messages = ctx.transcript_history.map(t => ({
    role: (t.speaker === 'vero' ? 'assistant' : 'user') as 'user' | 'assistant',
    content: t.speaker === 'vero' ? t.transcript : `[candidate]: ${t.transcript}`
  }))

  // First attempt
  let responseText: string
  try {
    responseText = await callLLM(model, systemPrompt, messages)
  } catch (err) {
    throw new Error(`LLM call failed: ${(err as Error).message}`)
  }

  let parsed: unknown
  try {
    parsed = extractJson(responseText)
  } catch (err) {
    // Retry with parse error appended
    const retryMessage = `Your previous response could not be parsed as JSON. Error: ${(err as Error).message}. Please respond with ONLY a valid JSON object.`
    responseText = await callLLM(model, systemPrompt, messages, retryMessage)
    parsed = extractJson(responseText)
  }

  let output: TurnOutput
  try {
    output = validateTurnOutput(parsed)
  } catch (validationErr) {
    // Retry once with validation error appended
    const retryMessage = `Your previous response failed schema validation. Error: ${(validationErr as Error).message}. Please fix and respond with ONLY a valid JSON object.`
    const retryText = await callLLM(model, systemPrompt, messages, retryMessage)
    const retryParsed = extractJson(retryText)
    output = validateTurnOutput(retryParsed)
  }

  // Apply state machine (handles follow-up limits, scoring, advancement)
  output = ctx.state.applyTurnOutput(output)

  // For guided mode: if all questions are done, force close
  if (ctx.state.isComplete && output.action !== 'close') {
    console.error(`[${ctx.session_id}] All questions complete, forcing action to 'close'`)
    output = { ...output, action: 'close' }
  }

  // For guided mode: if no more questions remain, force close
  // NOTE: allQuestions.length === 0 means intelligent-only mode — DO NOT force close there
  if (!ctx.state.currentQuestion && ctx.state.allQuestions.length > 0 && output.action !== 'close') {
    console.error(`[${ctx.session_id}] No more questions available, forcing action to 'close'`)
    output = { ...output, action: 'close' }
  }

  return output
}

/**
 * Generate a closing utterance via LLM (Req 11.1, 11.2).
 * Thanks the participant and sets expectations for next steps per the persona.
 * Channel-aware: different messaging for phone vs teams sessions.
 */
async function generateClosingUtterance(ctx: SessionContext): Promise<string> {
  // Determine channel from skill_pack (defaults to 'teams')
  const rawSkillPack = ctx.skill_pack as any
  const channel = rawSkillPack.channel || 'teams'
  const modelPref = ctx.skill_pack.agent.model_preferences[0]
  const model = modelPref.model

  let closingSystemPrompt =
    `${ctx.skill_pack.agent.persona}\n\n` +
    `The session is now complete. Generate a warm, professional closing statement. ` +
    `Thank the participant for their time and set expectations for next steps as described in your persona. `

  // Channel-specific instructions
  if (channel === 'phone') {
    closingSystemPrompt +=
      `This is a PHONE CALL. End by clearly stating the call is ending. ` +
      `Example: "Thank you for your time. That concludes our session. Goodbye!" `
  } else {
    closingSystemPrompt +=
      `This is a TEAMS MEETING. End by telling the participant they can disconnect. ` +
      `Example: "Thank you for your time. That concludes our session. You can now disconnect from the call. Have a great day!" `
  }

  closingSystemPrompt +=
    `Respond with ONLY the plain text closing statement — no JSON, no markdown, no explanation.`

  const messages = [{ role: 'user' as const, content: 'Please close the session.' }]

  return await callLLM(model, closingSystemPrompt, messages)
}

async function handleSessionStart(msg: SessionStartMessage): Promise<void> {
  if (sessions.has(msg.session_id)) {
    send({ type: 'error', session_id: msg.session_id, message: 'Session already exists' } satisfies ErrorMessage)
    return
  }

  // Try to restore from checkpoint first
  const checkpoint = await loadCheckpoint(msg.session_id)
  if (checkpoint) {
    console.error(`[${msg.session_id}] Restored from checkpoint`)
    sessions.set(msg.session_id, checkpoint)
    // Send a recovery message
    send({
      type: 'turn_output',
      session_id: msg.session_id,
      turn_index: checkpoint.transcript_history.length,
      next_utterance: "I apologize for the interruption. Let's continue.",
      action: 'follow_up',
      question_id: checkpoint.state.currentQuestion?.id ?? '',
      score: null,
      score_rationale: null,
      competency: checkpoint.state.currentQuestion?.competency ?? '',
      flags: []
    } satisfies TurnOutputMessage)
    return
  }

  // Extract context_data from skill_pack if present
  const rawSkillPack = msg.skill_pack as any
  const context_data = rawSkillPack.context_data as Record<string, unknown> | undefined

  const context: SessionContext = {
    session_id: msg.session_id,
    skill_pack: msg.skill_pack,
    state: new SkillPackState(msg.skill_pack),
    transcript_history: [],
    lastVeroUtterance: '',
    context_data
  }

  sessions.set(msg.session_id, context)

  // Start periodic checkpointing
  startCheckpointing(msg.session_id)

  // Generate opening utterance via LLM (Req 3.1, 3.3)
  const agentName = msg.skill_pack.agent.name
  const firstSection = msg.skill_pack.sections[0]
  const firstSectionTitle = firstSection?.title ?? 'the session'
  const modelPref = msg.skill_pack.agent.model_preferences[0]
  const model = modelPref.model
  
  // Substitute context variables in persona for opening prompt
  const personaWithContext = substituteContextTemplates(msg.skill_pack.agent.persona, context_data)

  const openingSystemPrompt =
    `${personaWithContext}\n\n` +
    `You are about to start a session. Generate a warm, natural opening greeting as ${agentName}. ` +
    `Introduce yourself by name (${agentName}) and briefly set expectations for what the participant can expect. ` +
    `The first topic will be: "${firstSectionTitle}". ` +
    `Respond with ONLY the plain text greeting — no JSON, no markdown, no explanation.`

  const messages = [{ role: 'user' as const, content: 'Begin the session.' }]

  let openingUtterance: string
  try {
    openingUtterance = await callLLM(model, openingSystemPrompt, messages)
  } catch (err) {
    // Fallback to a safe default if LLM call fails
    openingUtterance = `Hi, I'm ${agentName}. ${msg.skill_pack.agent.persona.split('.')[0]}. Let's get started with ${firstSectionTitle}.`
  }

  // Ensure the utterance contains agent.name (Req 3.3)
  if (!openingUtterance.includes(agentName)) {
    openingUtterance = `Hi, I'm ${agentName}. ${openingUtterance}`
  }

  const openingOutput: TurnOutputMessage = {
    type: 'turn_output',
    session_id: msg.session_id,
    turn_index: 0,
    next_utterance: openingUtterance,
    action: 'follow_up',
    question_id: context.state.currentQuestion?.id ?? '',
    score: null,
    score_rationale: null,
    competency: context.state.currentQuestion?.competency ?? '',
    flags: []
  }

  send(openingOutput)
  context.lastVeroUtterance = openingUtterance
}

async function handleTurn(msg: TurnMessage): Promise<void> {
  const ctx = sessions.get(msg.session_id)
  if (!ctx) {
    send({ type: 'error', session_id: msg.session_id, message: `Unknown session: ${msg.session_id}` } satisfies ErrorMessage)
    return
  }

  // Check for "repeat that" semantic match before calling LLM
  const repeatPatterns = [
    'can you repeat',
    'could you repeat',
    'say that again',
    'what did you say',
    'pardon',
    'please repeat'
  ]
  const lowerTranscript = msg.transcript.toLowerCase()
  const isRepeatRequest = repeatPatterns.some(p => lowerTranscript.includes(p))

  if (isRepeatRequest && ctx.lastVeroUtterance) {
    const repeatMsg: TurnOutputMessage = {
      type: 'turn_output',
      session_id: msg.session_id,
      turn_index: msg.turn_index,
      next_utterance: ctx.lastVeroUtterance,
      action: 'follow_up',
      question_id: ctx.state.currentQuestion?.id ?? '',
      score: null,
      score_rationale: null,
      competency: ctx.state.currentQuestion?.competency ?? '',
      flags: []
    }
    send(repeatMsg)
    // lastVeroUtterance stays the same — we just repeated it
    return
  }

  ctx.transcript_history.push(msg)

  let output: TurnOutput
  try {
    output = await processTurn(ctx, msg)
  } catch (err) {
    send({ type: 'error', session_id: msg.session_id, message: `processTurn failed: ${(err as Error).message}` } satisfies ErrorMessage)
    return
  }

  const turnOutputMsg: TurnOutputMessage = {
    type: 'turn_output',
    session_id: msg.session_id,
    turn_index: msg.turn_index,
    ...output
  }

  // Deduplication: if the utterance is very similar to the last one, generate a variation
  const similarity = calculateSimilarity(turnOutputMsg.next_utterance, ctx.lastVeroUtterance)
  if (similarity > 0.8 && ctx.lastVeroUtterance && !isRepeatRequest) {
    try {
      const variedUtterance = await generateVariedUtterance(ctx, turnOutputMsg.next_utterance)
      turnOutputMsg.next_utterance = variedUtterance
      output = { ...output, next_utterance: variedUtterance }
    } catch (err) {
      // Keep original utterance if variation fails
    }
  }

  // If action is 'close', generate a proper closing utterance (Req 11.1, 11.2)
  if (output.action === 'close') {
    try {
      const closingUtterance = await generateClosingUtterance(ctx)
      turnOutputMsg.next_utterance = closingUtterance
      output = { ...output, next_utterance: closingUtterance }
    } catch (err) {
      // Keep whatever utterance the LLM produced for the turn — still close
    }
  }

  console.error(`[${ctx.session_id}] Sending turn_output: action=${turnOutputMsg.action}, question=${turnOutputMsg.question_id}`)
  
  send(turnOutputMsg)
  ctx.lastVeroUtterance = turnOutputMsg.next_utterance

  // After sending the close utterance, emit session_summary (Req 11.1)
  // NOTE: Do NOT delete the session here — the Python side may still send turns
  // while the TTS is speaking the goodbye. The session will be cleaned up when
  // the Python side sends session_end.
  if (output.action === 'close') {
    const summary: SessionSummaryMessage = {
      type: 'session_summary',
      session_id: msg.session_id,
      scores: ctx.state.getScores(),
      transcript: ctx.transcript_history.map(t => ({
        speaker: t.speaker,
        transcript: t.transcript,
        turn_index: t.turn_index,
        timestamp_ms: t.timestamp_ms
      })),
      questions_not_reached: ctx.state.getQuestionsNotReached()
    }
    send(summary)
    // Session stays alive — cleaned up by handleSessionEnd
  }
}

async function handleSessionEnd(msg: SessionEndMessage): Promise<void> {
  const ctx = sessions.get(msg.session_id)
  if (!ctx) {
    send({ type: 'error', session_id: msg.session_id, message: `Unknown session: ${msg.session_id}` } satisfies ErrorMessage)
    return
  }

  const summary: SessionSummaryMessage = {
    type: 'session_summary',
    session_id: msg.session_id,
    scores: ctx.state.getScores(),
    transcript: ctx.transcript_history.map(t => ({
      speaker: t.speaker,
      transcript: t.transcript,
      turn_index: t.turn_index,
      timestamp_ms: t.timestamp_ms
    })),
    questions_not_reached: ctx.state.getQuestionsNotReached()
  }

  send(summary)
  sessions.delete(msg.session_id)
  stopCheckpointing(msg.session_id)
  await deleteCheckpoint(msg.session_id)
}

// Checkpointing timers
const checkpointTimers = new Map<string, NodeJS.Timeout>()

function startCheckpointing(session_id: string): void {
  // Save checkpoint every 5 seconds
  const timer = setInterval(async () => {
    const ctx = sessions.get(session_id)
    if (ctx) {
      await saveCheckpoint(ctx)
    }
  }, 5000)
  checkpointTimers.set(session_id, timer)
}

function stopCheckpointing(session_id: string): void {
  const timer = checkpointTimers.get(session_id)
  if (timer) {
    clearInterval(timer)
    checkpointTimers.delete(session_id)
  }
}

/**
 * Generate a gentle re-engagement prompt for consecutive_count === 1.
 * Calls the LLM to produce a topic-referencing (not verbatim) nudge.
 */
async function generateSilencePrompt(ctx: SessionContext): Promise<TurnOutput> {
  const currentQuestion = ctx.state.currentQuestion
  const topicHint = currentQuestion
    ? `The topic is: "${currentQuestion.competency}" — the current question is about ${currentQuestion.text.split(' ').slice(0, 8).join(' ')}...`
    : 'the current topic'
  const modelPref = ctx.skill_pack.agent.model_preferences[0]
  const model = modelPref.model

  const systemPrompt =
    `${ctx.skill_pack.agent.persona}\n\n` +
    `The participant has been silent. Generate a single gentle, encouraging utterance to re-engage them. ` +
    `Reference the topic without repeating the question verbatim. ${topicHint}\n\n` +
    `Respond with ONLY a JSON object:\n` +
    `{"next_utterance":"<gentle re-engagement>","action":"follow_up","question_id":"${currentQuestion?.id ?? ''}","score":null,"score_rationale":null,"competency":"${currentQuestion?.competency ?? ''}","flags":[]}`

  const messages = [{ role: 'user' as const, content: 'The participant is silent.' }]

  const responseText = await callLLM(model, systemPrompt, messages)
  const parsed = extractJson(responseText)
  return validateTurnOutput(parsed)
}

/**
 * Generate an advance-on-silence output for consecutive_count === 2.
 * No LLM call needed — returns a fixed transition utterance.
 */
function generateAdvanceOnSilence(ctx: SessionContext): TurnOutput {
  const currentQuestion = ctx.state.currentQuestion
  const advanceOutput: TurnOutput = {
    next_utterance: "Let's move on to the next topic.",
    action: 'advance',
    question_id: currentQuestion?.id ?? '',
    score: null,
    score_rationale: null,
    competency: currentQuestion?.competency ?? '',
    flags: []
  }
  // Apply state machine so the question index advances
  return ctx.state.applyTurnOutput(advanceOutput)
}

function handleSilenceTimeout(msg: SilenceTimeoutMessage): void {
  const ctx = sessions.get(msg.session_id)
  if (!ctx) {
    send({ type: 'error', session_id: msg.session_id, message: `Unknown session: ${msg.session_id}` } satisfies ErrorMessage)
    return
  }

  if (msg.consecutive_count === 1) {
    // Generate a gentle LLM prompt referencing the topic
    generateSilencePrompt(ctx)
      .then(output => {
        const outMsg: TurnOutputMessage = {
          type: 'turn_output',
          session_id: msg.session_id,
          turn_index: ctx.transcript_history.length,
          ...output
        }
        send(outMsg)
        ctx.lastVeroUtterance = output.next_utterance
      })
      .catch(err => {
        send({ type: 'error', session_id: msg.session_id, message: `silence prompt failed: ${(err as Error).message}` } satisfies ErrorMessage)
      })
  } else if (msg.consecutive_count >= 2) {
    // Force advance to next question
    const output = generateAdvanceOnSilence(ctx)
    const outMsg: TurnOutputMessage = {
      type: 'turn_output',
      session_id: msg.session_id,
      turn_index: ctx.transcript_history.length,
      ...output
    }
    send(outMsg)
    ctx.lastVeroUtterance = output.next_utterance
  }
}

function dispatch(raw: unknown): void {
  if (typeof raw !== 'object' || raw === null || !('type' in raw)) {
    send({ type: 'error', message: 'Invalid message: missing type field' } satisfies ErrorMessage)
    return
  }

  const msg = raw as InboundMessage

  switch (msg.type) {
    case 'session_start':
      handleSessionStart(msg).catch(err =>
        send({ type: 'error', session_id: msg.session_id, message: `session_start error: ${(err as Error).message}` } satisfies ErrorMessage)
      )
      break
    case 'turn':
      handleTurn(msg).catch(err =>
        send({ type: 'error', session_id: msg.session_id, message: `turn error: ${(err as Error).message}` } satisfies ErrorMessage)
      )
      break
    case 'session_end':
      handleSessionEnd(msg).catch(err =>
        send({ type: 'error', session_id: msg.session_id, message: `session_end error: ${(err as Error).message}` } satisfies ErrorMessage)
      )
      break
    case 'silence_timeout':
      handleSilenceTimeout(msg)
      break
    default:
      send({ type: 'error', message: `Unknown message type: ${(msg as any).type}` } satisfies ErrorMessage)
  }
}

// ── stdin readline loop ──────────────────────────────────────────────────────

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false
})

rl.on('line', (line: string) => {
  const trimmed = line.trim()
  if (!trimmed) return

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (err) {
    send({ type: 'error', message: `JSON parse error: ${(err as Error).message}` } satisfies ErrorMessage)
    return
  }

  dispatch(parsed)
})

rl.on('close', () => {
  process.exit(0)
})
