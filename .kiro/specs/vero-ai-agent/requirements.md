# Requirements Document

## Introduction

Vero is a configurable AI conversation agent that joins Microsoft Teams meetings as a named participant and drives structured conversations autonomously. Unlike meeting assistants or transcription bots, Vero takes an active seat in the conversation — asking questions, evaluating responses in real time, adapting dynamically based on what the other party says, and generating a structured report at session end.

The POC targets the Interviewer Skill Pack: Vero joins a live Teams meeting, conducts a full technical screening using a YAML-defined question bank and rubric, scores candidate responses per-turn, and emails a hire/no-hire scorecard within 60 seconds of call end — with zero human involvement during the call.

The system is designed for config-only role switching: the same Vero runtime can operate as a recruiter, sales coach, solutions architect, discovery agent, compliance auditor, or onboarding specialist by swapping the loaded Skill Pack YAML.

---

## Glossary

- **Vero**: The AI conversation agent — the named participant that joins Teams meetings and drives structured conversations.
- **Skill_Pack**: A YAML configuration file that defines Vero's persona, question bank, rubric, and report template for a specific role (e.g., interviewer, sales-coach).
- **Session**: A single end-to-end conversation from Vero joining a meeting to Vero exiting and the report being delivered.
- **Recall_Bot**: The Recall.ai managed bot instance that joins the Teams meeting, captures audio, and injects Vero's synthesised speech.
- **Audio_Pipeline**: The real-time audio processing chain: Recall.ai audio capture → Deepgram STT → Pipecat EOU detection.
- **Pipecat**: The Python-based real-time audio frame pipeline that handles STT, EOU detection, and TTS injection.
- **pi_agent**: The @mariozechner/pi-agent TypeScript module that runs the conversation intelligence loop — receives transcript context, returns structured per-turn output.
- **pi_ai**: The @mariozechner/pi-ai TypeScript module providing a unified LLM API across Claude Bedrock, GPT-4o, and Gemini.
- **RPC_Bridge**: The stdin/stdout JSONL communication channel between Pipecat (Python) and pi_agent (Node.js).
- **EOU_Detector**: The Pipecat End-of-Utterance detector that signals turn completion after 1.5 seconds of silence.
- **Turn**: A single speaker's complete utterance, bounded by EOU detection.
- **Utterance**: The exact text string Vero speaks in response to a Turn.
- **Rubric**: The per-competency scoring criteria defined in the Skill Pack, with scores 1–5.
- **Competency**: A named evaluation dimension defined in the Skill Pack rubric (e.g., "system-design", "communication").
- **Score**: An integer 1–5 assigned by pi_agent to a candidate response against a Competency.
- **Turn_Output**: The structured JSON object pi_agent returns per turn: `next_utterance`, `action`, `question_id`, `score`, `score_rationale`, `competency`, `flags`.
- **Action**: An enum value in Turn_Output: `follow_up | clarify | advance | close`.
- **Report**: The post-session structured document (scorecard, discovery brief, audit log, or coaching report) generated within 60 seconds of session end.
- **Cartesia_TTS**: The primary text-to-speech service (Cartesia Sonic) used to synthesise Vero's voice.
- **Deepgram_STT**: The Deepgram Nova-3 streaming speech-to-text service with speaker diarisation.
- **Backend_API**: The FastAPI (Python) service that orchestrates Recall.ai webhooks, Pipecat sessions, pi_agent, and report generation.
- **Host**: The human operator who creates the Teams meeting and configures Vero with a Skill Pack before the session.
- **Participant**: The human taking part in the Vero-led conversation (e.g., job candidate, sales rep, prospect).
- **Teams_Meeting**: A Microsoft Teams meeting that Vero joins as a named bot participant.

---

## Requirements

### Requirement 1: Teams Meeting Join

**User Story:** As a Host, I want Vero to join a scheduled Teams meeting as a named participant, so that the Participant sees a real agent in the meeting rather than an anonymous bot.

#### Acceptance Criteria

1. WHEN a session is initiated via the Backend_API, THE Recall_Bot SHALL join the Teams_Meeting within 10 seconds of the API call.
2. WHEN the Recall_Bot joins, THE Teams_Meeting participant list SHALL display Vero's configured agent name from the Skill_Pack.
3. IF the Teams_Meeting link is invalid or expired, THEN THE Backend_API SHALL return an error response with a descriptive message within 5 seconds.
4. IF the Recall_Bot fails to join within 10 seconds, THEN THE Backend_API SHALL retry the join attempt once and log the failure.
5. THE Backend_API SHALL authenticate with Microsoft Teams using OAuth 2.0 with the `Calls.JoinGroupCall.All` and `Calls.AccessMedia.All` permissions granted by the Azure AD tenant admin.

---

### Requirement 2: Skill Pack Loading

**User Story:** As a Host, I want to configure Vero with a YAML Skill Pack before a session, so that Vero adopts the correct persona, question bank, and rubric without any code changes.

#### Acceptance Criteria

1. WHEN a Skill_Pack YAML file is provided to the Backend_API, THE Backend_API SHALL validate the YAML against the Skill_Pack schema before the session starts.
2. IF a required Skill_Pack field is missing or invalid, THEN THE Backend_API SHALL return a validation error listing all missing or invalid fields.
3. THE Skill_Pack SHALL define the following fields: `skill.id`, `skill.name`, `skill.version`, `agent.name`, `agent.persona`, `agent.language`, `agent.max_duration_minutes`, `agent.model_preferences`, `agent.tts_voice`, `sections[].questions[].text`, `sections[].questions[].probes[]`, `sections[].questions[].competency`, `sections[].questions[].max_follow_ups`, `rubric[].competency`, `rubric[].scores[1..5]`, `report.template`, `report.email_to`, `report.include_transcript`.
4. WHEN a valid Skill_Pack is loaded, THE pi_agent SHALL use the `agent.persona` field as the system prompt context for all LLM calls in the Session.
5. WHEN two different Skill_Packs are loaded in separate sessions on the same Vero runtime, THE Backend_API SHALL run each Session with its own isolated Skill_Pack state without code changes.

---

### Requirement 3: Session Opening

**User Story:** As a Participant, I want Vero to greet me with a natural, role-appropriate opening when the session starts, so that I understand who Vero is and what to expect.

#### Acceptance Criteria

1. WHEN the Recall_Bot has successfully joined the Teams_Meeting, THE pi_agent SHALL generate an opening Utterance using the `agent.persona` and the first section of the Skill_Pack.
2. THE Cartesia_TTS SHALL synthesise the opening Utterance and inject it into the Teams_Meeting audio within 5 seconds of the Recall_Bot joining.
3. THE opening Utterance SHALL introduce Vero by the `agent.name` defined in the Skill_Pack.
4. IF the Cartesia_TTS service is unavailable, THEN THE Audio_Pipeline SHALL fall back to ElevenLabs TTS and log the fallback event.

---

### Requirement 4: Audio Capture and Transcription

**User Story:** As a system operator, I want Participant speech to be accurately transcribed in real time with speaker identification, so that Vero can respond to the correct speaker's words.

#### Acceptance Criteria

1. WHILE a Session is active, THE Recall_Bot SHALL stream audio from the Teams_Meeting to the Audio_Pipeline continuously.
2. WHILE a Session is active, THE Deepgram_STT SHALL transcribe the audio stream with speaker diarisation, producing per-speaker transcript segments.
3. THE Deepgram_STT SHALL produce transcript segments with a latency of 200 milliseconds or less from audio input to transcript output.
4. THE Audio_Pipeline SHALL label each transcript segment with the speaker identity provided by Deepgram_STT diarisation.
5. IF the Deepgram_STT connection drops during a Session, THEN THE Audio_Pipeline SHALL attempt to reconnect within 2 seconds and log the interruption.

---

### Requirement 5: Turn Detection

**User Story:** As a system operator, I want Vero to detect when the Participant has finished speaking before responding, so that Vero does not interrupt mid-sentence.

#### Acceptance Criteria

1. WHILE a Session is active, THE EOU_Detector SHALL monitor the audio stream for silence periods.
2. WHEN the EOU_Detector detects 1.5 seconds of continuous silence following a Participant utterance, THE EOU_Detector SHALL signal a Turn completion event to the Audio_Pipeline.
3. WHEN a Turn completion event is signalled, THE Audio_Pipeline SHALL pass the accumulated transcript segment for that Turn to the RPC_Bridge.
4. WHILE Vero is speaking, THE EOU_Detector SHALL suppress Turn completion signals to prevent Vero from triggering a response to its own speech.

---

### Requirement 6: Conversation Intelligence Loop

**User Story:** As a Host, I want Vero to autonomously decide what to say next based on the Participant's response and the Skill Pack state, so that the conversation flows naturally without human intervention.

#### Acceptance Criteria

1. WHEN a Turn completion event is received, THE pi_agent SHALL process the transcript, current Skill_Pack state, and rubric context to produce a Turn_Output within the latency budget.
2. THE Turn_Output SHALL conform to the TypeBox-validated schema containing: `next_utterance` (string), `action` (enum: `follow_up | clarify | advance | close`), `question_id` (string), `score` (integer 1–5 or null), `score_rationale` (string), `competency` (string), `flags` (array of: `incomplete | off_topic | strong_signal | redirect_needed`).
3. IF the Turn_Output fails TypeBox schema validation, THEN THE pi_agent SHALL log the validation error and retry the LLM call once with the validation error appended to the prompt.
4. THE pi_agent SHALL use the `agent.model_preferences` field from the Skill_Pack to select the LLM provider via pi_ai.
5. WHILE a Session is active, THE pi_agent SHALL maintain full in-session memory, referencing earlier Turns when generating subsequent Utterances.

---

### Requirement 7: Dynamic Question Flow

**User Story:** As a Host, I want Vero to ask follow-up questions when a Participant's response is weak or incomplete, so that the conversation surfaces genuine signal rather than accepting shallow answers.

#### Acceptance Criteria

1. WHEN a Turn_Output `score` is less than 3 or `flags` contains `incomplete`, THE pi_agent SHALL set `action` to `follow_up` and generate a follow-up Utterance using the relevant `probes[]` from the Skill_Pack.
2. WHEN a Turn_Output `action` is `follow_up`, THE pi_agent SHALL track the follow-up count for the current question against `max_follow_ups` defined in the Skill_Pack.
3. WHEN the follow-up count for a question reaches `max_follow_ups`, THE pi_agent SHALL set `action` to `advance` regardless of the Score.
4. WHEN a Turn_Output `action` is `advance`, THE pi_agent SHALL move to the next question in the Skill_Pack `sections[].questions[]` order.
5. WHEN a Turn_Output `flags` contains `off_topic`, THE pi_agent SHALL set `action` to `follow_up` with a redirect Utterance that steers the Participant back to the current question.
6. FOR ALL Sessions using the same Skill_Pack, THE pi_agent SHALL produce a `follow_up` action for 90% or more of Turns where `score` is less than 3 or `flags` contains `incomplete`.

---

### Requirement 8: Real-Time Response Scoring

**User Story:** As a Host, I want each Participant response to be scored against the rubric as the session proceeds, so that the final report reflects an accurate, per-turn evaluation rather than a post-hoc summary.

#### Acceptance Criteria

1. WHEN a Turn_Output `action` is `advance` or `close`, THE pi_agent SHALL assign a `score` integer between 1 and 5 inclusive for the completed question against the relevant `rubric[].competency`.
2. THE pi_agent SHALL use the `rubric[].scores[1..5]` descriptors from the Skill_Pack as the scoring criteria for each LLM scoring call.
3. WHILE a Session is active, THE pi_agent SHALL accumulate all per-question scores in session memory for use in Report generation.
4. THE pi_agent SHALL record a `score_rationale` string for every Score assigned, referencing specific Participant statements from the transcript.
5. IF a question is skipped due to reaching `max_follow_ups` without an `advance` action, THEN THE pi_agent SHALL record a score of 1 with a `score_rationale` indicating insufficient response.

---

### Requirement 9: End-to-End Response Latency

**User Story:** As a Participant, I want Vero to respond within a few seconds of me finishing speaking, so that the conversation feels natural and not robotic.

#### Acceptance Criteria

1. WHEN a Turn completion event is signalled, THE system SHALL deliver the first audio chunk of Vero's Utterance to the Teams_Meeting within 4 seconds at the 90th percentile across all Turns in a Session.
2. WHEN a Turn completion event is signalled, THE system SHALL deliver the first audio chunk of Vero's Utterance to the Teams_Meeting within 2.5 seconds at the 50th percentile across all Turns in a Session.
3. THE latency measurement SHALL be taken from the moment the EOU_Detector signals Turn completion to the moment the first audio chunk is injected into the Teams_Meeting by the Recall_Bot.
4. THE Backend_API SHALL log per-Turn latency measurements for every Session to enable p50 and p90 calculation.

---

### Requirement 10: Silence and Repeat Handling

**User Story:** As a Participant, I want Vero to handle awkward silences and repeat requests gracefully, so that the session doesn't stall or feel broken.

#### Acceptance Criteria

1. WHEN 8 seconds of silence passes after a Turn completion event with no Participant speech detected, THE pi_agent SHALL generate a gentle prompt Utterance to re-engage the Participant.
2. WHEN a Participant utterance contains a phrase semantically equivalent to "can you repeat that", THE pi_agent SHALL repeat the previous Utterance verbatim or rephrase it for clarity.
3. THE gentle prompt Utterance SHALL not repeat the question verbatim but SHALL reference the topic of the current question.
4. WHEN a silence prompt has been issued twice consecutively with no Participant response, THE pi_agent SHALL set `action` to `advance` and move to the next question.

---

### Requirement 11: Session Closing

**User Story:** As a Participant, I want Vero to close the session with a clear, professional closing statement, so that I know the conversation has ended and what happens next.

#### Acceptance Criteria

1. WHEN all questions in the Skill_Pack `sections[].questions[]` have been completed or `agent.max_duration_minutes` is reached, THE pi_agent SHALL set `action` to `close` and generate a closing Utterance.
2. THE closing Utterance SHALL thank the Participant and set expectations for next steps as defined in the Skill_Pack `agent.persona`.
3. WHEN the closing Utterance has been fully delivered, THE Recall_Bot SHALL exit the Teams_Meeting.
4. IF `agent.max_duration_minutes` is reached before all questions are completed, THEN THE pi_agent SHALL set `action` to `close` and note in the Report which questions were not reached.

---

### Requirement 12: Post-Session Report Generation

**User Story:** As a Host, I want a structured report delivered within 60 seconds of the session ending, so that I can act on the results immediately without manual write-up.

#### Acceptance Criteria

1. WHEN the Recall_Bot exits the Teams_Meeting, THE Backend_API SHALL trigger report generation within 5 seconds.
2. THE Report SHALL be generated and delivered within 60 seconds of the Recall_Bot exiting the Teams_Meeting.
3. THE Report SHALL use the template type defined in `report.template` (one of: `scorecard | discovery-brief | audit-log | coaching-report`).
4. THE Report SHALL include all per-question scores, score rationales, competency summaries, and a final hire/no-hire recommendation (for the `scorecard` template).
5. WHEN `report.include_transcript` is true in the Skill_Pack, THE Report SHALL include the full session transcript with speaker labels.
6. THE Backend_API SHALL email the Report to all addresses listed in `report.email_to` using Resend.
7. THE Backend_API SHALL post a text summary of the Report to the Teams_Meeting chat via the Bot Framework.
8. IF the Resend email delivery fails, THEN THE Backend_API SHALL log the failure and retry delivery once after 30 seconds.

---

### Requirement 13: RPC Bridge (Pipecat ↔ pi_agent)

**User Story:** As a system operator, I want the Python audio pipeline and the Node.js conversation engine to communicate reliably, so that transcript data flows into pi_agent and Turn_Output flows back to Pipecat without data loss.

#### Acceptance Criteria

1. THE RPC_Bridge SHALL communicate via stdin/stdout JSONL between the Pipecat process and the pi_agent Node.js process.
2. WHEN Pipecat sends a Turn transcript over the RPC_Bridge, THE pi_agent SHALL acknowledge receipt and return a Turn_Output within the latency budget defined in Requirement 9.
3. IF the RPC_Bridge connection is interrupted, THEN THE Backend_API SHALL log the interruption, attempt to restart the pi_agent process, and resume the Session.
4. THE RPC_Bridge message format SHALL be validated on both the Pipecat send side and the pi_agent receive side to ensure schema consistency.
5. FOR ALL valid Turn transcripts sent over the RPC_Bridge, parsing the JSONL message then serialising it then parsing it again SHALL produce an equivalent object (round-trip property).

---

### Requirement 14: Skill Pack Config-Only Role Switch

**User Story:** As a Host, I want to switch Vero's role from interviewer to discovery agent (or any other Skill Pack) without changing any code, so that the same Vero runtime serves multiple use cases.

#### Acceptance Criteria

1. WHEN a different Skill_Pack YAML is provided to the Backend_API for a new Session, THE Backend_API SHALL load the new Skill_Pack and run the Session with the new persona, question bank, and rubric without redeploying the application.
2. THE Backend_API SHALL support at minimum the following Skill_Pack `report.template` values in the POC: `scorecard` (interviewer) and `discovery-brief` (discovery-agent).
3. WHEN two Sessions are run sequentially with different Skill_Packs on the same runtime, THE pi_agent SHALL produce Turn_Outputs consistent with each respective Skill_Pack's persona and rubric.
4. THE Skill_Pack schema SHALL be the sole source of truth for all session-specific behaviour — no session behaviour SHALL be hardcoded in the Backend_API or Pipecat pipeline.

---

### Requirement 15: Infrastructure and Deployment

**User Story:** As a system operator, I want the full Vero stack to be deployable in a new Azure and AWS environment within one business day, so that the POC can be reproduced reliably.

#### Acceptance Criteria

1. THE Backend_API, Pipecat pipeline, and pi_agent SHALL be co-hosted in a single Docker container deployable on an AWS EC2 t3.medium instance.
2. THE Docker container SHALL expose the Backend_API on a configurable port via environment variable.
3. THE system SHALL be fully configurable via environment variables for all secrets and service endpoints (Azure AD credentials, Recall.ai API key, Deepgram API key, Cartesia API key, Resend API key, LLM provider keys).
4. IF any required environment variable is missing at container startup, THEN THE Backend_API SHALL log a descriptive error listing all missing variables and exit with a non-zero status code.
5. THE deployment SHALL require no more than one business day to reproduce from scratch in a new Azure AD tenant and AWS account, given all API credentials are available.

---

### Requirement 16: Skill Pack YAML Parsing

**User Story:** As a Host, I want the Skill Pack YAML to be parsed reliably and validated completely, so that misconfigured Skill Packs are caught before a session starts rather than causing mid-session failures.

#### Acceptance Criteria

1. WHEN a Skill_Pack YAML file is submitted to the Backend_API, THE Backend_API SHALL parse the YAML into a structured Skill_Pack object.
2. IF a Skill_Pack YAML file contains a syntax error, THEN THE Backend_API SHALL return a parse error with the line number and description of the syntax issue.
3. THE Backend_API SHALL validate all required fields are present and all enum values (e.g., `report.template`, Turn_Output `action`) match the defined set.
4. FOR ALL valid Skill_Pack YAML files, parsing the YAML then serialising it to YAML then parsing it again SHALL produce an equivalent Skill_Pack object (round-trip property).
5. THE Backend_API SHALL reject Skill_Pack files where `agent.max_duration_minutes` is less than 1 or greater than 120.

---

### Requirement 17: Skill Pack Storage

**User Story:** As a Host, I want Skill Packs to be stored persistently so I can reuse them across sessions without re-uploading the YAML each time.

#### Acceptance Criteria

1. THE Backend_API SHALL provide CRUD endpoints for Skill Packs: GET /skill-packs, POST /skill-packs, PUT /skill-packs/{id}, DELETE /skill-packs/{id}
2. Each stored Skill_Pack SHALL have a unique ID, name, version, created_at, updated_at, and is_active flag
3. THE Backend_API SHALL store Skill Pack YAML content in the skill_packs PostgreSQL table
4. WHEN a session is created, the Host MAY reference a stored Skill_Pack by ID instead of providing the full YAML inline
5. IF a referenced Skill_Pack ID does not exist, THEN THE Backend_API SHALL return HTTP 404

---

### Requirement 18: Skill Pack Activation

**User Story:** As a Host, I want to mark one Skill Pack as active so that new sessions use it by default without specifying an ID each time.

#### Acceptance Criteria

1. WHEN POST /skill-packs/{id}/activate is called, THE Backend_API SHALL set is_active=true for the specified Skill_Pack and is_active=false for all others
2. WHEN GET /sessions is called with no skill_pack_id, THE Backend_API SHALL use the currently active Skill_Pack
3. THE Backend_API SHALL ensure only one Skill_Pack is active at a time
4. IF no Skill_Pack is active and no skill_pack_id is provided, THEN THE Backend_API SHALL return HTTP 400 with a descriptive error

---

### Requirement 19: Skill Pack Version History

**User Story:** As a Host, I want to see the version history of a Skill Pack so I can track changes and roll back if needed.

#### Acceptance Criteria

1. WHEN GET /skill-packs/{id}/versions is called, THE Backend_API SHALL return all historical versions of the Skill_Pack ordered by created_at descending
2. Each version record SHALL include: version_number (auto-incremented integer), yaml_content, created_at, and a change_summary
3. WHEN PUT /skill-packs/{id} is called, THE Backend_API SHALL create a new version record rather than overwriting the existing content
4. THE current version SHALL always be the most recently created version

---

### Requirement 20: Skill Pack Manager UI — YAML Editor

**User Story:** As a Host, I want a web UI with a YAML editor that validates my Skill Pack in real time so I can catch errors before saving.

#### Acceptance Criteria

1. THE UI SHALL provide a Monaco-based YAML editor for creating and editing Skill Packs
2. WHILE the user types, THE UI SHALL call POST /skill-packs/validate and display inline validation errors within 500ms of the user stopping typing (debounced)
3. Validation errors SHALL be displayed as inline markers in the editor gutter with descriptive messages
4. THE UI SHALL display a green "Valid" or red "Invalid" status indicator
5. THE UI SHALL disable the Save button while the Skill Pack is invalid

---

### Requirement 21: Skill Pack Manager UI — Library and Version History

**User Story:** As a Host, I want to browse my saved Skill Packs, activate one, delete unused ones, and view version history so I can manage my Skill Pack library efficiently.

#### Acceptance Criteria

1. THE UI SHALL display a list of all stored Skill Packs showing: name, skill.id, version, is_active status, and created_at
2. Each Skill Pack in the list SHALL have an Activate button that calls POST /skill-packs/{id}/activate
3. Each Skill Pack in the list SHALL have a Delete button with a confirmation dialog that calls DELETE /skill-packs/{id}
4. Each Skill Pack in the list SHALL have a View History button that opens a version history panel showing all versions with timestamps
5. WHEN a version is selected in the history panel, THE UI SHALL load that version's yaml_content into the editor in read-only view
6. THE Backend_API SHALL serve the UI as a static SPA at the root path /

---

### Requirement 22: Session Dashboard — Session Launcher

**User Story:** As a Host, I want to launch a new Vero session from the UI by selecting a Skill Pack and pasting a Teams meeting URL, so that I don't need to use the API directly.

#### Acceptance Criteria

1. THE UI SHALL provide a session launcher form with a Skill Pack selector (dropdown populated from GET /skill-packs) and a Teams meeting URL text input
2. WHEN the Host submits the form, THE UI SHALL call POST /sessions and display the returned session_id and initial status
3. IF the Teams meeting URL field is empty or the Skill Pack selector has no selection, THE UI SHALL disable the Launch button and show inline validation messages
4. WHEN POST /sessions returns an error, THE UI SHALL display the error message inline without navigating away
5. THE Skill Pack selector SHALL show the currently active Skill Pack pre-selected by default

---

### Requirement 23: Session Dashboard — Live Session Monitor

**User Story:** As a Host, I want to see the live status of an active session including the current question and turn count, so that I can monitor the conversation without being in the meeting.

#### Acceptance Criteria

1. WHEN a session is in ACTIVE status, THE UI SHALL poll GET /sessions/{session_id} every 3 seconds and update the display without a full page reload
2. THE live monitor SHALL display: session status badge (PENDING / JOINING / ACTIVE / CLOSING / COMPLETED / FAILED), current question text, turn count, and elapsed time
3. WHEN session status transitions to COMPLETED or FAILED, THE UI SHALL stop polling and display a final status with a link to the report
4. THE UI SHALL display a "Terminate Session" button that calls DELETE /sessions/{session_id} with a confirmation dialog
5. WHEN the session status is FAILED, THE UI SHALL display the error message from the session state

---

### Requirement 24: Session Dashboard — Past Sessions List

**User Story:** As a Host, I want to browse all past sessions with their outcomes so that I can track history and access reports.

#### Acceptance Criteria

1. THE UI SHALL display a paginated list of all sessions from GET /sessions ordered by created_at descending
2. Each session row SHALL show: session_id (truncated), Skill Pack name, status badge, created_at, duration (if completed), and a Report link (if report exists)
3. THE UI SHALL support filtering the list by status (ALL / ACTIVE / COMPLETED / FAILED)
4. WHEN the Report link is clicked, THE UI SHALL open the report content in a side panel or modal
5. THE Backend_API SHALL expose GET /sessions returning a paginated list of sessions with summary fields

---

### Requirement 25: Report Viewer — Report List

**User Story:** As a Host, I want to browse all post-session reports in the UI filtered by template type and date, so that I can find and review any report without checking email.

#### Acceptance Criteria

1. THE UI SHALL display a list of all reports from GET /reports ordered by generated_at descending
2. Each report row SHALL show: session_id (truncated), Skill Pack name, template type badge, generated_at, and a View button
3. THE UI SHALL support filtering by template type (ALL / scorecard / discovery-brief / audit-log / coaching-report) and by date range
4. THE Backend_API SHALL expose GET /reports returning a paginated list of report summaries
5. WHEN the View button is clicked, THE UI SHALL open the full report in a dedicated report detail view

---

### Requirement 26: Report Viewer — Inline Scorecard View

**User Story:** As a Host, I want to read a scorecard report inline in the UI with competency scores and a hire/no-hire badge, so that I can evaluate results immediately without opening an email attachment.

#### Acceptance Criteria

1. WHEN a scorecard report is opened, THE UI SHALL display: overall hire/no-hire recommendation badge, per-competency score bars (1–5), per-question scores with score rationale text, and session metadata (duration, Skill Pack name, date)
2. THE competency score bars SHALL use colour coding: scores 1–2 red, 3 yellow, 4–5 green
3. WHEN `report.include_transcript` is true, THE UI SHALL show a "View Transcript" button that opens the full transcript inline
4. THE UI SHALL support all four report template types with appropriate layouts: scorecard, discovery-brief, audit-log, coaching-report

---

### Requirement 27: Session Transcript Viewer

**User Story:** As a Host, I want to read the full turn-by-turn transcript of any completed session with speaker labels, timestamps, per-turn scores, and flags, so that I can review exactly what was said and how it was evaluated.

#### Acceptance Criteria

1. THE UI SHALL display the full transcript from GET /sessions/{session_id}/transcript as a chronological list of turns
2. Each turn SHALL show: speaker label (Vero / Participant), timestamp, transcript text, and — for scored turns — the score badge (1–5) and score rationale
3. WHEN a turn has flags (incomplete, off_topic, strong_signal, redirect_needed), THE UI SHALL display the flag as a coloured badge on that turn
4. THE UI SHALL provide jump-to-question navigation: a sidebar listing all Skill Pack questions; clicking a question scrolls to the first turn for that question_id
5. THE Backend_API SHALL expose GET /sessions/{session_id}/transcript returning the full turn list with all Turn fields
6. THE UI SHALL highlight Vero turns and Participant turns with distinct background colours

---

### Requirement 28: Latency & Health Monitor — Per-Session Latency

**User Story:** As a system operator, I want to see p50/p90 latency charts per session so that I can verify the system is meeting the 4s response target.

#### Acceptance Criteria

1. THE UI SHALL display a bar or line chart of per-turn latency (ms) for any selected session, with p50 and p90 reference lines
2. THE UI SHALL show aggregate p50 and p90 values as stat cards above the chart
3. THE chart data SHALL come from the `turn_latencies` field in GET /sessions/{session_id}
4. WHEN any turn latency exceeds 4000ms, THE UI SHALL highlight that bar in red

---

### Requirement 29: Latency & Health Monitor — Event Log and System Health

**User Story:** As a system operator, I want to see TTS fallback events, STT reconnect events, and live system health status so that I can diagnose issues without reading raw logs.

#### Acceptance Criteria

1. THE UI SHALL display a chronological event log showing TTS fallback events and Deepgram reconnect events with session_id, timestamp, and reason
2. THE Backend_API SHALL expose GET /events returning a paginated list of system events (type, session_id, timestamp, detail)
3. THE UI SHALL display a system health panel showing the current status of: PostgreSQL DB, Recall.ai API, Deepgram API, Cartesia API — each as a green/red status indicator
4. THE Backend_API SHALL extend GET /health to return per-dependency status: `db`, `recall`, `deepgram`, `cartesia` each with `status: ok | degraded | down` and `latency_ms`
5. THE health panel SHALL auto-refresh every 30 seconds
