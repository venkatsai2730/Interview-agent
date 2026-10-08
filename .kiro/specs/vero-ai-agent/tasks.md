# Implementation Plan: Vero AI Agent

## Overview

Four-week POC implementation. Week 1 covers infrastructure and project scaffolding. Week 2 covers the audio pipeline. Week 3 covers the conversation engine and first end-to-end session. Week 4 covers latency optimisation, report generation, and demo polish.

Python (Hypothesis) for backend/pipeline PBTs. TypeScript (fast-check) for pi_agent PBTs.

## Tasks

- [x] 1. Week 1 — Setup & Infrastructure

  - [x] 1.1 Scaffold project structure and Docker Compose
    - Create `/app` directory layout: `backend/`, `pipeline/`, `agent/`
    - Write `Dockerfile` with Python 3.12-slim base, Node.js 20 LTS install, pip + npm ci steps, and configurable `PORT` env var
    - Write `docker-compose.yml` with `vero` app service and `postgres:16-alpine` sidecar with healthcheck
    - Add `.env.example` listing all required environment variables from the design
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 1.2 Implement startup environment variable validation
    - In `backend/main.py`, add a startup check that reads all required env vars on FastAPI lifespan start
    - Log every missing variable by name and call `sys.exit(1)` if any are absent
    - `AWS_PROFILE` is optional (EC2 uses instance IAM role); exclude it from the required set
    - _Requirements: 15.4_

  - [ ]* 1.3 Write property test for missing env vars (Property 16)
    - **Property 16: Missing environment variable causes startup failure**
    - Use `hypothesis` with `st.sets(st.sampled_from(REQUIRED_ENV_VARS), min_size=1)` to generate subsets of missing vars
    - Assert `exit_code != 0` and that every missing var name appears in the log output
    - Tag: `# Feature: vero-ai-agent, Property 16`
    - **Validates: Requirements 15.4**

  - [x] 1.4 Set up SQLAlchemy async engine and ORM models
    - In `backend/db.py`, create async SQLAlchemy engine from `DATABASE_URL` env var and an `AsyncSession` factory
    - In `backend/models.py`, define `Session`, `Turn`, and `Report` ORM models matching the PostgreSQL schema in the design
    - Add Alembic (or inline `create_all`) for table creation on startup
    - _Requirements: 15.1_

  - [x] 1.5 Implement Skill Pack YAML validator
    - In `backend/skill_pack_validator.py`, implement `parse_skill_pack_yaml(raw: str) -> SkillPack` using PyYAML
    - Raise a structured `ParseError` with line number on YAML syntax errors (Requirements 16.2)
    - Implement `validate_skill_pack(sp: dict) -> ValidationResult` that checks all required fields, enum values, and `max_duration_minutes` in [1, 120]
    - Return a `ValidationResult` with `is_valid: bool` and `errors: list[str]` listing every invalid field
    - _Requirements: 2.1, 2.2, 2.3, 16.1, 16.2, 16.3, 16.5_

  - [ ]* 1.6 Write property test for Skill Pack YAML round-trip (Property 1)
    - **Property 1: Skill Pack YAML round-trip**
    - Use `hypothesis` with `st.from_schema(SKILL_PACK_JSON_SCHEMA)` to generate valid SkillPack dicts
    - Assert `parse_skill_pack_yaml(yaml.dump(parsed_once)) == parsed_once`
    - Tag: `# Feature: vero-ai-agent, Property 1`
    - **Validates: Requirements 16.4**

  - [ ]* 1.7 Write property test for max_duration_minutes boundary (Property 11)
    - **Property 11: max_duration_minutes boundary enforcement**
    - Use `hypothesis` with `st.integers()` to generate arbitrary durations
    - Assert valid for [1, 120], invalid (with `max_duration_minutes` in errors) for all other values
    - Tag: `# Feature: vero-ai-agent, Property 11`
    - **Validates: Requirements 16.5**

  - [ ]* 1.8 Write property test for validation error completeness (Property 10)
    - **Property 10: Validation error lists all invalid fields**
    - Generate SkillPack dicts with a known set of missing/invalid fields F
    - Assert the error response lists every field in F and no field outside F
    - Tag: `# Feature: vero-ai-agent, Property 10`
    - **Validates: Requirements 2.2, 16.3**

  - [ ]* 1.9 Write property test for YAML syntax error line number (Property 18)
    - **Property 18: YAML syntax error includes line number**
    - Generate YAML strings with an injected syntax error at a known line L
    - Assert the `ParseError` message contains L
    - Tag: `# Feature: vero-ai-agent, Property 18`
    - **Validates: Requirements 16.2**

  - [x] 1.10 Implement Backend API skeleton and `/skill-packs/validate` endpoint
    - In `backend/main.py`, initialise FastAPI app with lifespan (env check + DB init)
    - Implement `POST /skill-packs/validate` — parse + validate Skill Pack YAML, return 200 or 422 with field-level errors
    - Implement `GET /health` — return dependency status (DB reachable, env vars present)
    - _Requirements: 2.1, 2.2, 15.4_

  - [x] 1.11 Implement Recall.ai client and `POST /sessions` endpoint
    - In `backend/recall_client.py`, implement `create_bot(meeting_url, bot_name, api_key) -> bot_id` calling the Recall.ai REST API
    - Implement one retry after 10s timeout; raise `RecallJoinError` if retry also fails
    - In `backend/session_manager.py`, implement `create_session(skill_pack, meeting_url) -> SessionState` — validate Skill Pack, call Recall client, persist to DB, return session
    - Implement `POST /sessions` endpoint wiring these together; return `session_id` and `status: pending`
    - _Requirements: 1.1, 1.3, 1.4, 2.1_

  - [x] 1.12 Implement Recall.ai webhook handler
    - Implement `POST /recall/webhook` in `backend/main.py`
    - Handle `bot_joined` event: transition session to `ACTIVE`, record `started_at`, spawn Pipecat pipeline subprocess
    - Handle `bot_left` event: transition session to `COMPLETED`, trigger report generation
    - Handle `audio_ready` event: forward audio stream reference to the active Pipecat pipeline
    - _Requirements: 1.1, 1.2_

- [x] 2. Checkpoint — Week 1 complete
  - Ensure `docker-compose up` starts both containers cleanly, `/health` returns 200, `/skill-packs/validate` accepts and rejects sample YAMLs correctly. Ask the user if questions arise.


- [-] 3. Week 2 — Audio Pipeline

  - [x] 3.1 Implement RPC Bridge serialisation/deserialisation
    - In `pipeline/rpc_bridge.py`, implement `serialize_rpc_message(msg: dataclass) -> str` (dataclass → JSON + newline)
    - Implement `parse_rpc_message(line: str) -> dataclass` with schema validation; log and send `{"type":"error"}` on invalid input
    - Define all message dataclasses: `TurnMessage`, `SessionStartMessage`, `SessionEndMessage`, `SilenceTimeoutMessage`, `TurnOutputMessage`, `SessionSummaryMessage`
    - _Requirements: 13.1, 13.4_

  - [ ]* 3.2 Write property test for RPC Bridge JSONL round-trip (Property 2)
    - **Property 2: RPC Bridge JSONL round-trip**
    - Use `hypothesis` with strategies for each message type to generate valid message instances
    - Assert `parse_rpc_message(serialize_rpc_message(parse_rpc_message(serialize_rpc_message(msg)))) == parse_rpc_message(serialize_rpc_message(msg))`
    - Tag: `# Feature: vero-ai-agent, Property 2`
    - **Validates: Requirements 13.5**

  - [x] 3.3 Implement Deepgram Nova-3 streaming STT integration
    - In `pipeline/pipeline.py`, integrate Deepgram Nova-3 WebSocket streaming using the Deepgram Python SDK
    - Enable speaker diarisation (`diarize=True`) and produce per-speaker transcript segments
    - Label each segment with the `speaker` field from Deepgram diarisation output
    - Implement reconnect logic: on WebSocket disconnect, attempt reconnect within 2s, buffer audio frames during the window, log interruption with `session_id` and timestamp
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.4 Write property test for transcript segment speaker labelling (Property 13)
    - **Property 13: Transcript segment speaker labelling**
    - Generate arbitrary Deepgram diarisation response payloads with a non-empty speaker field
    - Assert every segment produced by the pipeline has a non-empty `speaker` field
    - Tag: `# Feature: vero-ai-agent, Property 13`
    - **Validates: Requirements 4.4**

  - [x] 3.5 Implement EOU Detector
    - In `pipeline/eou_detector.py`, implement silence energy monitoring with a 1.5s threshold
    - Emit `turn_complete` event after 1.5s continuous silence following participant speech
    - Implement `vero_speaking` flag suppression: while flag is set, do not emit `turn_complete` regardless of silence duration
    - Reset silence timer on any non-silence audio frame
    - _Requirements: 5.1, 5.2, 5.4_

  - [ ]* 3.6 Write property test for EOU suppression while Vero is speaking (Property 12)
    - **Property 12: EOU suppression while Vero is speaking**
    - Generate audio frame sequences of arbitrary length with `vero_speaking = True`
    - Assert the EOU detector emits zero `turn_complete` events for any such sequence regardless of silence duration
    - Tag: `# Feature: vero-ai-agent, Property 12`
    - **Validates: Requirements 5.4**

  - [x] 3.7 Wire EOU → RPC Bridge send
    - In `pipeline/pipeline.py`, on `turn_complete` event, accumulate the transcript segment for that turn and send a `TurnMessage` over the RPC Bridge to pi_agent
    - Suppress EOU events while `vero_speaking` flag is set (double-guard at pipeline level)
    - _Requirements: 5.3_

  - [x] 3.8 Implement TTS Injector with Cartesia primary and ElevenLabs fallback
    - In `pipeline/tts_injector.py`, implement `synthesise_and_inject(utterance: str, voice_id: str)` calling Cartesia Sonic
    - Set `vero_speaking = True` before first audio chunk, `False` after last chunk
    - On Cartesia HTTP error or timeout >500ms, fall back to ElevenLabs; log fallback event with timestamp and error reason
    - Inject synthesised audio into the Recall.ai audio stream
    - _Requirements: 3.2, 3.4_

  - [x] 3.9 Wire RPC Bridge receive → TTS Injector
    - In `pipeline/pipeline.py`, on receiving a `TurnOutputMessage` from pi_agent over the RPC Bridge, pass `next_utterance` and `agent.tts_voice` to the TTS Injector
    - Record `first_audio_chunk_ms` timestamp immediately when the first audio chunk is ready for injection
    - _Requirements: 5.3, 9.3, 9.4_

- [x] 4. Checkpoint — Week 2 complete
  - Verify audio flows from a mock Recall.ai stream through Deepgram STT → EOU → RPC Bridge send, and that TTS injection works with Cartesia (and falls back to ElevenLabs). Ask the user if questions arise.


- [x] 5. Week 3 — Conversation Engine & First End-to-End Session

  - [x] 5.1 Scaffold pi_agent Node.js project
    - Create `agent/package.json` with dependencies: `@mariozechner/pi-agent`, `@mariozechner/pi-ai`, `@sinclair/typebox`, `fast-check` (dev), `tsx` (dev)
    - Create `agent/agent.ts` as the RPC server entry point: read JSONL from `stdin`, write JSONL to `stdout`
    - Implement the `session_start` message handler: initialise a pi_agent session with the provided SkillPack
    - _Requirements: 6.1, 13.1_

  - [x] 5.2 Define TypeBox schemas for SkillPack and Turn_Output in pi_agent
    - In `agent/agent.ts` (or a shared types file), define `SkillPackSchema` and `TurnOutputSchema` using TypeBox as specified in the design
    - Implement `validateTurnOutput(raw: unknown): TurnOutput` — validate against `TurnOutputSchema`, throw typed error on failure
    - _Requirements: 6.2, 6.3_

  - [x] 5.3 Implement Skill Pack state machine in pi_agent
    - In `agent/skill_pack_state.ts`, implement `SkillPackState` class tracking: current question index, follow-up count per question, scores accumulated, questions not reached
    - Implement `applyTurnOutput(output: TurnOutput): void` — update state based on `action` (follow_up increments counter, advance moves to next question, close marks session done)
    - Enforce `max_follow_ups`: when follow-up count reaches limit, force `action = advance` on next turn
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.3_

  - [ ]* 5.4 Write property test for follow-up limit enforcement (Property 5)
    - **Property 5: Follow-up limit enforcement**
    - Use `fast-check` with `fc.integer({ min: 1, max: 5 }).chain(...)` to generate sessions with varying `max_follow_ups`
    - Assert that after exactly N follow-up turns, the next output has `action === 'advance'`
    - Tag: `// Feature: vero-ai-agent, Property 5`
    - **Validates: Requirements 7.2, 7.3**

  - [x] 5.5 Implement per-turn LLM call via pi_ai (Amazon Bedrock)
    - In `agent/agent.ts`, implement `processTurn(msg: TurnMessage): Promise<TurnOutput>`:
      1. Append transcript to in-session memory
      2. Build LLM prompt: `agent.persona` + Skill Pack state + rubric + full transcript + scoring history
      3. Call LLM via `pi_ai` using `agent.model_preferences[0].provider = 'bedrock'` and the specified model ID
      4. Validate response against `TurnOutputSchema`; on failure, retry once with the validation error appended to the prompt
      5. Apply conversation flow rules from `SkillPackState`
      6. Return validated `TurnOutput`
    - AWS credential chain: boto3/AWS SDK uses `AWS_PROFILE` locally, EC2 instance role on EC2 — no explicit credential handling needed
    - _Requirements: 6.1, 6.3, 6.4, 6.5_

  - [ ]* 5.6 Write property test for Turn_Output schema conformance (Property 3)
    - **Property 3: Turn_Output schema conformance**
    - Use `fast-check` with `fc.record({ transcript: fc.string({ minLength: 1 }) })` to generate turn inputs
    - Assert every output passes `Value.Check(TurnOutputSchema, output) === true`
    - Tag: `// Feature: vero-ai-agent, Property 3`
    - **Validates: Requirements 6.2**

  - [ ]* 5.7 Write property test for follow-up rate on weak responses (Property 4)
    - **Property 4: Follow-up rate >= 90% on weak/incomplete turns**
    - Use `fast-check` with `fc.array(weakTurnArbitrary(), { minLength: 10, maxLength: 50 })` to generate batches of weak turns
    - Assert `followUpCount / total >= 0.9`
    - Tag: `// Feature: vero-ai-agent, Property 4`
    - **Validates: Requirements 7.6**

  - [ ]* 5.8 Write property test for score completeness on advance/close (Property 6)
    - **Property 6: Score completeness on advance/close**
    - Generate Turn_Outputs where `action` is `advance` or `close`
    - Assert `score` is an integer in [1, 5] and `score_rationale` is a non-empty string
    - Tag: `// Feature: vero-ai-agent, Property 6`
    - **Validates: Requirements 8.1, 8.4**

  - [x] 5.9 Implement silence handling in pi_agent
    - Handle `silence_timeout` message with `consecutive_count = 1`: generate a gentle prompt utterance referencing the topic (not verbatim question)
    - Handle `silence_timeout` with `consecutive_count = 2`: set `action = advance`, move to next question
    - Handle "can you repeat that" semantic match: repeat or rephrase the previous utterance
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 5.10 Implement session opening and closing utterances
    - On `session_start`, generate opening utterance using `agent.persona` and first section of Skill Pack; utterance must contain `agent.name`
    - On `action = close` (all questions done or `max_duration_minutes` reached), generate closing utterance per `agent.persona`; note unreached questions in `session_summary`
    - _Requirements: 3.1, 3.3, 11.1, 11.2, 11.4_

  - [ ]* 5.11 Write property test for Skill Pack drives agent name (Property 7)
    - **Property 7: Skill Pack drives agent name**
    - Generate SkillPacks with arbitrary `agent.name` values
    - Assert the bot display name sent to Recall.ai equals `agent.name` and the opening utterance contains `agent.name`
    - Tag: `// Feature: vero-ai-agent, Property 7`
    - **Validates: Requirements 1.2, 3.3**

  - [ ]* 5.12 Write property test for Skill Pack persona in system prompt (Property 8)
    - **Property 8: Skill Pack persona in system prompt**
    - Generate SkillPacks with arbitrary `agent.persona` and `model_preferences`
    - Assert every LLM call's system prompt contains `agent.persona` and targets the specified Bedrock model
    - Tag: `// Feature: vero-ai-agent, Property 8`
    - **Validates: Requirements 2.4, 6.4**

  - [x] 5.13 Implement session state isolation (multi-session support)
    - In `backend/session_manager.py`, ensure each session holds its own `SkillPackState` instance keyed by `session_id`
    - In `agent/agent.ts`, maintain a `Map<sessionId, SessionContext>` so concurrent sessions never share state
    - _Requirements: 2.5, 14.1, 14.3_

  - [ ]* 5.14 Write property test for session state isolation (Property 9)
    - **Property 9: Session state isolation**
    - Generate two concurrent sessions S1 and S2 with different SkillPacks
    - Assert Turn_Outputs for S1 reference only S1's SkillPack state and vice versa
    - Tag: `// Feature: vero-ai-agent, Property 9`
    - **Validates: Requirements 2.5, 14.3**

  - [x] 5.15 Wire pi_agent child process into Pipecat pipeline
    - In `pipeline/pipeline.py`, spawn `node agent/agent.ts` as a child process on session start
    - Send `session_start` message with full SkillPack over RPC Bridge
    - On RPC Bridge interruption (process death), attempt to restart pi_agent and resume; log failure and close session if restart fails
    - On `session_end`, send `session_end` message and await `session_summary` response
    - _Requirements: 13.2, 13.3_

- [x] 6. Checkpoint — Week 3 complete
  - Run a full mock end-to-end session: session create → bot join → opening utterance → 3 turns with scoring → close → session_summary received. Verify latency records are populated. Ask the user if questions arise.


- [x] 7. Week 4 — Polish, Report Generation & Demo

  - [x] 7.1 Implement per-turn latency logging
    - In `pipeline/pipeline.py`, record `eou_timestamp_ms` when the EOU detector fires and `first_audio_chunk_ms` when the first audio chunk is ready for injection
    - Persist a `TurnLatency` record to the `turns` table in PostgreSQL after each turn
    - Expose p50/p90 calculation in `GET /sessions/{session_id}` response
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 7.2 Write property test for latency logging per turn (Property 17)
    - **Property 17: Latency logging per turn**
    - For any turn in a mock session, after first audio chunk injection, assert the session state contains a `TurnLatency` record with both `eou_timestamp_ms` and `first_audio_chunk_ms` populated
    - Tag: `# Feature: vero-ai-agent, Property 17`
    - **Validates: Requirements 9.4**

  - [x] 7.3 Implement Report Generator
    - In `backend/report_generator.py`, implement `generate_report(session_summary: SessionSummaryMessage, skill_pack: SkillPack) -> Report`
    - Support all four template types: `scorecard`, `discovery-brief`, `audit-log`, `coaching-report`
    - For `scorecard`: include per-question scores, score rationales, competency averages, hire/no-hire recommendation
    - For questions skipped due to `max_follow_ups`: record score=1 with rationale "insufficient response"
    - When `report.include_transcript` is true, include full turn-by-turn transcript with speaker labels
    - List unreached questions in `questions_not_reached`
    - _Requirements: 12.3, 12.4, 12.5, 11.4_

  - [ ]* 7.4 Write property test for report completeness (Property 14)
    - **Property 14: Report completeness**
    - Generate completed sessions with `scorecard` template and arbitrary question sets
    - Assert every reached question has a score and score_rationale, every rubric competency appears in the competency summary, and a hire/no-hire recommendation is present
    - When `include_transcript` is true, assert the transcript contains all turns with speaker labels
    - Tag: `# Feature: vero-ai-agent, Property 14`
    - **Validates: Requirements 12.3, 12.4, 12.5**

  - [x] 7.5 Implement Resend email delivery and Bot Framework Teams summary
    - In `backend/report_generator.py`, implement `deliver_report(report: Report, skill_pack: SkillPack)`:
      - Call Resend API once per address in `report.email_to`; on failure, retry once after 30s and log
      - Post a text summary to the Teams meeting chat via Bot Framework
      - Persist `email_sent` and `chat_posted` flags to the `reports` table
    - _Requirements: 12.6, 12.7, 12.8_

  - [ ]* 7.6 Write property test for report delivery to all recipients (Property 15)
    - **Property 15: Report delivery to all recipients**
    - Generate SkillPacks with `report.email_to` lists of varying length N (1–5)
    - Assert the Resend API is called exactly N times, each call targeting one of the listed addresses
    - Tag: `# Feature: vero-ai-agent, Property 15`
    - **Validates: Requirements 12.6**

  - [x] 7.7 Wire report generation into session close flow
    - In `backend/session_manager.py`, on receiving `session_summary` from pi_agent (triggered by `bot_left` webhook), call `generate_report` and then `deliver_report` within 5 seconds of session end
    - Transition session status to `COMPLETED` after delivery; transition to `FAILED` with partial report on unrecoverable error
    - Ensure report is generated and delivered within 60s of session end (log a warning if exceeded)
    - _Requirements: 12.1, 12.2_

  - [x] 7.8 Implement `GET /sessions/{session_id}` and `DELETE /sessions/{session_id}`
    - `GET`: return session status, current turn count, p50/p90 latency from accumulated `turn_latencies`, and report delivery status
    - `DELETE`: send `session_end` with `reason: manual` over RPC Bridge, trigger close flow
    - _Requirements: 11.3_

  - [x] 7.9 Implement Skill Pack config-only role switch validation
    - Verify `POST /sessions` accepts both `scorecard` and `discovery-brief` template SkillPacks without code changes
    - Ensure no session-specific behaviour is hardcoded in `backend/` or `pipeline/` — all behaviour driven by SkillPack fields
    - Write unit tests: run two sequential sessions with different SkillPacks, assert each uses its own persona, question bank, and rubric
    - _Requirements: 14.1, 14.2, 14.4_

  - [x] 7.10 Implement Azure AD OAuth 2.0 authentication for Teams
    - In `backend/recall_client.py`, add OAuth 2.0 token acquisition using `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` with scopes `Calls.JoinGroupCall.All` and `Calls.AccessMedia.All`
    - Pass the token to Recall.ai bot creation so the bot joins as an authenticated Teams participant
    - Handle invalid/expired meeting URL: catch Recall.ai 4xx and return HTTP 400 with descriptive message within 5s
    - _Requirements: 1.3, 1.5_

  - [x] 7.11 Write unit tests for key integration points
    - `POST /sessions` with valid SkillPack → returns `session_id`, status `pending`
    - `POST /sessions` with missing required field → returns 422 with field name in error
    - `POST /recall/webhook` with `bot_joined` → session transitions to `ACTIVE`
    - Recall.ai join timeout → one retry, then 503
    - Cartesia failure → ElevenLabs called, fallback logged
    - EOU fires after exactly 1.5s silence; does NOT fire during `vero_speaking = True`
    - Turn_Output schema failure → LLM retried once with error in prompt
    - Two consecutive silence timeouts → `action = advance`
    - All questions complete → `action = close`
    - `scorecard` report → contains scores, competency summary, hire/no-hire
    - `include_transcript: true` → report contains full transcript with speaker labels
    - Resend failure → one retry after 30s, then log and continue
    - YAML syntax error at line 7 → error response includes "line 7"
    - `max_duration_minutes: 0` rejected; `1` accepted; `120` accepted; `121` rejected
    - _Requirements: 1.1, 1.3, 2.1, 2.2, 3.4, 5.2, 5.4, 6.3, 10.4, 11.1, 12.4, 12.5, 12.8, 16.2, 16.5_

- [x] 8. Final Checkpoint — Demo Ready
  - Ensure all non-optional tests pass. Run a full mock end-to-end session covering: join → opening → 3+ turns with follow-ups → close → report emailed. Verify p50/p90 latency records are populated. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use `@settings(max_examples=100)` (Hypothesis) and `{ numRuns: 100 }` (fast-check)
- All LLM calls go through Amazon Bedrock — no direct Anthropic/OpenAI/Google API keys needed
- AWS credentials: `AWS_PROFILE` for local dev (SSO), EC2 instance IAM role in production
ol

- [x] 9. Skill Pack Manager — Backend & Frontend

  - [x] 9.1 Add skill_packs and skill_pack_versions tables to PostgreSQL schema
    - Add ORM models `SkillPack` and `SkillPackVersion` to `backend/models.py`
    - Add `skill_packs` and `skill_pack_versions` tables to Alembic migration / create_all
    - _Requirements: 17.3_

  - [x] 9.2 Implement Skill Pack CRUD endpoints
    - `GET /skill-packs` — list all (id, name, skill_id, version, is_active, created_at)
    - `POST /skill-packs` — validate YAML, store in skill_packs table, create initial version record
    - `PUT /skill-packs/{id}` — validate YAML, update skill_packs row, insert new skill_pack_versions record
    - `DELETE /skill-packs/{id}` — delete from skill_packs (cascade deletes versions); return 404 if not found
    - _Requirements: 17.1, 17.2, 17.3, 17.5_

  - [x] 9.3 Implement POST /skill-packs/{id}/activate endpoint
    - In a single transaction: set is_active=false for all rows, then is_active=true for the specified id
    - Return 404 if id not found
    - _Requirements: 18.1, 18.3_

  - [ ]* 9.4 Write property test for activation exclusivity (Property 19)
    - **Property 19: Skill Pack activation exclusivity**
    - Use `hypothesis` to generate sets of 2–5 Skill Packs, activate each one in turn
    - Assert after each activation exactly one row has is_active=true
    - Tag: `# Feature: vero-ai-agent, Property 19`
    - **Validates: Requirements 18.1, 18.3**

  - [x] 9.5 Implement GET /skill-packs/{id}/versions endpoint
    - Return all version records for the given skill_pack_id ordered by version_number descending
    - Each record: version_number, yaml_content, created_at, change_summary
    - _Requirements: 19.1, 19.2_

  - [ ]* 9.6 Write property test for version monotonicity (Property 20)
    - **Property 20: Skill Pack version monotonicity**
    - Generate a Skill Pack, call PUT N times, assert version_numbers are 1..N+1 in order and prior records are unchanged
    - Tag: `# Feature: vero-ai-agent, Property 20`
    - **Validates: Requirements 19.3, 19.4**

  - [x] 9.7 Update POST /sessions to accept skill_pack_id
    - Allow session creation with either inline yaml_content or a stored skill_pack_id
    - If skill_pack_id provided, load YAML from skill_packs table; return 404 if not found
    - If neither provided and an active Skill Pack exists, use the active one; else return 400
    - _Requirements: 17.4, 18.2, 18.4_

  - [x] 9.8 Scaffold React + Vite frontend
    - Create `frontend/package.json` with: react, react-dom, @monaco-editor/react, @tanstack/react-query, tailwindcss, vite, typescript
    - Create `frontend/vite.config.ts` with proxy to backend API on port 8000 for local dev
    - Create `frontend/index.html` and `frontend/src/main.tsx` entry point
    - Create `frontend/src/api/client.ts` with typed fetch wrappers for all Skill Pack endpoints
    - _Requirements: 21.6_

  - [x] 9.9 Implement SkillPackEditor component
    - Monaco Editor configured for YAML language with dark theme
    - Debounced validation: on content change, wait 500ms then call POST /skill-packs/validate
    - Display validation errors as Monaco markers (`editor.setModelMarkers`) in the gutter
    - Show green "Valid" / red "Invalid" status badge
    - Disable Save button while invalid
    - On Save: call POST /skill-packs (new) or PUT /skill-packs/{id} (edit)
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

  - [x] 9.10 Implement SkillPackLibrary component
    - Fetch and display list from GET /skill-packs using TanStack Query
    - Show columns: name, skill.id, version, active status badge, created_at
    - Activate button: calls POST /skill-packs/{id}/activate, invalidates query cache
    - Delete button: shows confirmation dialog, calls DELETE /skill-packs/{id}, invalidates cache
    - Edit button: loads Skill Pack YAML into SkillPackEditor
    - New button: opens SkillPackEditor with empty content
    - _Requirements: 21.1, 21.2, 21.3_

  - [x] 9.11 Implement VersionHistory component
    - Triggered by "View History" button in SkillPackLibrary
    - Fetches GET /skill-packs/{id}/versions
    - Displays timeline list: version number, created_at, change_summary
    - Clicking a version loads its yaml_content into a read-only Monaco editor panel
    - _Requirements: 21.4, 21.5_

  - [x] 9.12 Wire frontend build into Docker and FastAPI static serving
    - Add frontend build step to Dockerfile: `npm ci && npm run build` in `frontend/`
    - In `backend/main.py`, mount `frontend/dist` as StaticFiles at "/" after all API routes
    - Verify GET / serves the React SPA and API routes still work at /sessions, /skill-packs, etc.
    - _Requirements: 21.6_

  - [ ]* 9.13 Write property test for live validation debounce (Property 21)
    - **Property 21: Live validation debounce correctness**
    - Use `fast-check` to generate sequences of keystrokes with random inter-key delays
    - Assert the validation API is called at most once per 500ms idle window
    - Tag: `// Feature: vero-ai-agent, Property 21`
    - **Validates: Requirements 20.2**


- [x] 10. Session Dashboard — Backend & Frontend

  - [x] 10.1 Update frontend stack to shadcn/ui
    - Add `shadcn/ui` to `frontend/package.json` (via `npx shadcn-ui@latest init`)
    - Configure `components.json` for the project (style: default, baseColor: slate, cssVariables: true)
    - Install required shadcn components: Button, Badge, Input, Select, Table, Card, Alert, AlertDialog, Sheet, Tabs, Dialog
    - Update `SkillPackEditor`, `SkillPackLibrary`, `VersionHistory` to use shadcn components in place of raw Tailwind
    - _Requirements: 20.1, 21.1_

  - [x] 10.2 Add GET /sessions list endpoint to Backend API
    - In `backend/main.py`, implement `GET /sessions` with query params: `status` (optional), `page` (default 1), `page_size` (default 20)
    - Return paginated response: `items[]`, `total`, `page`, `page_size`
    - Each item: `session_id`, `skill_pack_name`, `skill_pack_id`, `status`, `created_at`, `started_at`, `ended_at`, `duration_minutes`, `has_report`
    - _Requirements: 24.5_

  - [x] 10.3 Extend GET /sessions/{session_id} with live monitor fields
    - Add `current_question_text`, `current_question_index`, `turn_count`, `elapsed_seconds` to the existing GET /sessions/{session_id} response
    - Derive `current_question_text` from the session's Skill Pack state and current question index
    - Derive `elapsed_seconds` from `started_at` to now (or `ended_at` if completed)
    - _Requirements: 23.1, 23.2_

  - [x] 10.4 Add react-router-dom and set up page routing
    - Add `react-router-dom` to `frontend/package.json`
    - Create `frontend/src/pages/SessionsPage.tsx` and `frontend/src/pages/SkillPacksPage.tsx`
    - Configure routes in `App.tsx`: `/` → SessionsPage, `/sessions/:sessionId` → LiveSessionMonitor, `/skill-packs` → SkillPacksPage
    - Add top-level navigation using shadcn `Tabs` or a simple nav bar
    - _Requirements: 22.1, 23.1_

  - [x] 10.5 Implement SessionLauncher component
    - shadcn `Select` populated from GET /skill-packs; pre-select the active Skill Pack
    - shadcn `Input` for Teams meeting URL with basic URL format validation
    - shadcn `Button` disabled until both fields are valid
    - On submit: call POST /sessions; on success navigate to `/sessions/{session_id}`
    - On error: display shadcn `Alert` with the API error message inline
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5_

  - [x] 10.6 Implement LiveSessionMonitor component
    - Use TanStack Query with `refetchInterval: 3000` to poll GET /sessions/{session_id}
    - Display shadcn `Badge` for status (blue=ACTIVE, green=COMPLETED, red=FAILED, yellow=JOINING/PENDING)
    - Display current question text, turn count, elapsed time (mm:ss formatted)
    - Stop polling when status is COMPLETED or FAILED (`refetchInterval: false` on terminal status)
    - Show report link (shadcn `Button` variant="link") when `has_report` is true
    - "Terminate Session" shadcn `Button` variant="destructive" with shadcn `AlertDialog` confirmation → calls DELETE /sessions/{session_id}
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5_

  - [x] 10.7 Implement PastSessionsList component
    - shadcn `Table` with columns: Session ID (truncated to 8 chars), Skill Pack, Status badge, Created, Duration, Report
    - shadcn `Select` for status filter (ALL / ACTIVE / COMPLETED / FAILED); updates query param
    - Pagination: prev/next shadcn `Button` controls; display "Page X of Y"
    - TanStack Query with `placeholderData: keepPreviousData` for smooth page transitions
    - Report column: shadcn `Button` variant="link" → opens report JSON in shadcn `Sheet` side panel
    - Clicking a session row navigates to `/sessions/{session_id}`
    - _Requirements: 24.1, 24.2, 24.3, 24.4_

  - [ ]* 10.8 Write property test for session list completeness (Property 22)
    - **Property 22: Session list reflects all sessions**
    - Use `hypothesis` to generate N sessions (1–20), assert GET /sessions returns exactly N total items across pages
    - Assert each item has the correct session_id and status
    - Tag: `# Feature: vero-ai-agent, Property 22`
    - **Validates: Requirements 24.1, 24.5**


- [x] 11. Report Viewer — Backend & Frontend

  - [x] 11.1 Implement GET /reports endpoint
    - In `backend/main.py`, implement `GET /reports` with query params: `template` (optional), `from_date` (optional ISO date), `to_date` (optional ISO date), `page` (default 1), `page_size` (default 20)
    - Query the `reports` table joined with `sessions` to get `skill_pack_name`
    - Return paginated response: `items[]` (session_id, skill_pack_name, template, generated_at, recommendation), `total`, `page`, `page_size`
    - _Requirements: 25.1, 25.4_

  - [x] 11.2 Implement GET /sessions/{session_id}/transcript endpoint
    - In `backend/main.py`, implement `GET /sessions/{session_id}/transcript`
    - Query all rows from the `turns` table for the given session_id ordered by `turn_index` ascending
    - Return `{ session_id, turns[] }` where each turn includes all fields: turn_index, speaker, transcript, timestamp_ms, question_id, score, score_rationale, competency, flags, action
    - Return 404 if session_id not found
    - _Requirements: 27.5_

  - [ ]* 11.3 Write property test for transcript turn completeness (Property 25)
    - **Property 25: Transcript turn completeness**
    - Use `hypothesis` to generate N turns (1–30) for a mock session, persist them, then call GET /sessions/{session_id}/transcript
    - Assert exactly N turns returned in ascending turn_index order, each with non-empty speaker and transcript
    - Tag: `# Feature: vero-ai-agent, Property 25`
    - **Validates: Requirements 27.1, 27.5**

  - [x] 11.4 Implement ReportList component
    - shadcn `Table` with columns: Session ID (truncated to 8 chars), Skill Pack, Template badge, Generated At, View button
    - shadcn `Select` for template filter (ALL / scorecard / discovery-brief / audit-log / coaching-report)
    - Two shadcn `Input type="date"` fields for from/to date range filter
    - Pagination using shadcn `Button` prev/next; display "Page X of Y"
    - View button navigates to `/reports/{session_id}`
    - TanStack Query with `keepPreviousData` for smooth pagination
    - _Requirements: 25.1, 25.2, 25.3, 25.5_

  - [x] 11.5 Implement ScorecardView component
    - Hire/no-hire shadcn `Badge` at top (green=hire, red=no-hire)
    - Per-competency score bars using shadcn `Progress` (colour-coded: 1–2 red, 3 yellow, 4–5 green)
    - Per-question shadcn `Accordion`: question text, score badge, score rationale
    - Session metadata in shadcn `Card`: Skill Pack name, date, duration
    - Support all four template types with appropriate field layouts (scorecard, discovery-brief, audit-log, coaching-report)
    - _Requirements: 26.1, 26.2, 26.4_

  - [x] 11.6 Implement ReportDetailPage and wire "View Transcript" button
    - Create `frontend/src/pages/ReportDetailPage.tsx` — fetches report content and renders `ScorecardView`
    - Add "View Transcript" shadcn `Button` that opens `TranscriptViewer` in a shadcn `Sheet` (side panel) when `report.include_transcript` is true
    - Add routes `/reports` → `ReportsPage` and `/reports/:sessionId` → `ReportDetailPage` in `App.tsx`
    - Extend `frontend/src/api/client.ts` with typed wrappers for `GET /reports` and `GET /sessions/{session_id}/transcript`
    - _Requirements: 25.5, 26.3_

  - [ ]* 11.7 Write property test for report list completeness (Property 24)
    - **Property 24: Report list reflects all generated reports**
    - Use `hypothesis` to generate N completed sessions with reports (1–10), assert GET /reports returns exactly N items across all pages with correct session_id, template, and generated_at
    - Tag: `# Feature: vero-ai-agent, Property 24`
    - **Validates: Requirements 25.1, 25.4**


- [x] 12. Session Transcript Viewer — Frontend

  - [x] 12.1 Implement TranscriptViewer component
    - Create `frontend/src/components/TranscriptViewer.tsx`
    - Fetches `GET /sessions/{session_id}/transcript` via TanStack Query
    - Two-column layout: left sidebar (question navigation) + right panel (turn list) using shadcn `ScrollArea` for both
    - Vero turns: right-aligned shadcn `Card` with muted background
    - Participant turns: left-aligned shadcn `Card` with default background
    - Each turn: speaker label, timestamp (HH:MM:SS from session start), transcript text
    - _Requirements: 27.1, 27.2, 27.6_

  - [x] 12.2 Add per-turn score badges and flag badges
    - For scored turns: shadcn `Badge` with score (1–5), colour-coded (1–2 red, 3 yellow, 4–5 green)
    - Score rationale in a shadcn `Collapsible` section below the turn text
    - Flag badges: `incomplete` (yellow), `off_topic` (orange), `strong_signal` (green), `redirect_needed` (red) as shadcn `Badge` variants
    - _Requirements: 27.2, 27.3_

  - [x] 12.3 Implement jump-to-question sidebar navigation
    - Left sidebar lists all Skill Pack questions in order (question text + question_id)
    - Clicking a question calls `element.scrollIntoView({ behavior: 'smooth' })` on the first turn with that `question_id`
    - Active question highlighted with shadcn `Badge` variant="secondary"
    - Sidebar uses shadcn `ScrollArea` with shadcn `Button` variant="ghost" for each question
    - _Requirements: 27.4_

  - [x] 12.4 Wire TranscriptViewer into Report Viewer and Past Sessions
    - In `ReportDetailPage`, the "View Transcript" button opens `TranscriptViewer` in a shadcn `Sheet`
    - In `PastSessionsList`, add a "Transcript" shadcn `Button` variant="link" column that opens `TranscriptViewer` in a shadcn `Sheet` for completed sessions
    - `TranscriptViewer` accepts `sessionId` as a prop and fetches its own data
    - _Requirements: 26.3, 27.1_


- [x] 13. Latency & Health Monitor — Backend & Frontend

  - [x] 13.1 Add events table and event logging to pipeline
    - Add `Event` ORM model to `backend/models.py` and `events` table to Alembic migration / create_all
    - In `pipeline/tts_injector.py`, on Cartesia fallback, write a `tts_fallback` event record (session_id, timestamp, detail with error reason and latency)
    - In `pipeline/pipeline.py`, on Deepgram reconnect, write a `stt_reconnect` event record (session_id, timestamp, detail with reconnect duration)
    - _Requirements: 29.1, 29.2_

  - [x] 13.2 Implement GET /events endpoint
    - In `backend/main.py`, implement `GET /events` with query params: `session_id` (optional), `type` (optional), `page` (default 1), `page_size` (default 50)
    - Return paginated response: `items[]` (id, type, session_id, timestamp, detail), `total`, `page`, `page_size`
    - _Requirements: 29.2_

  - [x] 13.3 Extend GET /health with per-dependency status
    - In `backend/main.py`, extend `GET /health` to probe each dependency and return per-dependency status
    - DB probe: `SELECT 1` via SQLAlchemy; Recall/Deepgram/Cartesia: HTTP HEAD or lightweight status endpoint
    - Response: `{ status, dependencies: { db, recall, deepgram, cartesia } }` each with `status: ok|degraded|down` and `latency_ms`
    - `status` at top level is `ok` if all dependencies are ok, `degraded` if any are degraded, `down` if any are down
    - _Requirements: 29.3, 29.4_

  - [ ]* 13.4 Write property test for health endpoint coverage (Property 26)
    - **Property 26: Health endpoint covers all dependencies**
    - Use `hypothesis` to generate mock dependency probe results (any combination of ok/degraded/down)
    - Assert GET /health response always includes all four keys (db, recall, deepgram, cartesia) each with a valid status and non-negative latency_ms
    - Tag: `# Feature: vero-ai-agent, Property 26`
    - **Validates: Requirements 29.4**

  - [x] 13.5 Implement LatencyChart component
    - Add `recharts` to `frontend/package.json`
    - Create `frontend/src/components/LatencyChart.tsx`
    - Recharts `BarChart`: X-axis = turn index, Y-axis = latency ms
    - Recharts `ReferenceLine` for p50 and p90 values
    - Bars > 4000ms rendered in red (`fill="#ef4444"`)
    - Two shadcn `Card` stat cards above chart: p50 and p90 aggregate values
    - Data from `turn_latencies` in `GET /sessions/{session_id}`
    - _Requirements: 28.1, 28.2, 28.3, 28.4_

  - [x] 13.6 Implement EventLog component
    - Create `frontend/src/components/EventLog.tsx`
    - shadcn `Table`: Type badge, Session ID (truncated), Timestamp, Detail
    - Type badge: `tts_fallback` (orange), `stt_reconnect` (blue)
    - Optional session_id filter using shadcn `Input`
    - Pagination using shadcn `Button` prev/next
    - TanStack Query fetching `GET /events`
    - _Requirements: 29.1, 29.2_

  - [x] 13.7 Implement HealthPanel component
    - Create `frontend/src/components/HealthPanel.tsx`
    - shadcn `Card` grid (2×2): PostgreSQL, Recall.ai, Deepgram, Cartesia
    - Each card: dependency name, coloured status dot (green=ok, yellow=degraded, red=down), latency_ms
    - TanStack Query with `refetchInterval: 30000` for auto-refresh every 30 seconds
    - Data from `GET /health`
    - _Requirements: 29.3, 29.4, 29.5_

  - [x] 13.8 Implement MonitorPage and wire routing
    - Create `frontend/src/pages/MonitorPage.tsx` — renders `LatencyChart` (with session selector), `EventLog`, and `HealthPanel`
    - Session selector: shadcn `Select` populated from `GET /sessions` (completed sessions only) to drive `LatencyChart` and `EventLog` session filter
    - Add route `/monitor` → `MonitorPage` in `App.tsx`
    - Add "Monitor" nav link to the top-level navigation bar
    - Extend `frontend/src/api/client.ts` with typed wrappers for `GET /events` and extended `GET /health`
    - _Requirements: 28.1, 29.1, 29.3_
