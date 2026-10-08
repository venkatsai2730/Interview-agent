+:---------------------------------------------------------------:+
| **FEATURE SPEC · v0 · POC**                                     |
|                                                                 |
| **Vero**                                                        |
|                                                                 |
| *The AI Agent That Takes a Seat in Any Conversation*            |
|                                                                 |
| Interviewer · Sales Coach · Solutions Architect · Discovery     |
| Agent                                                           |
+-----------------------------------------------------------------+

+:--------------+:--------------+:--------------+:--------------+
| POC Phase     | Channel       | Status        | Updated       |
|               |               |               |               |
| **v0 --- 4    | **Microsoft   | **Draft**     | **March       |
| Weeks**       | Teams**       |               | 2026**        |
+---------------+---------------+---------------+---------------+

**01 Problem Statement**

Enterprise conversations are expensive, inconsistent, and hard to scale.
Whether it\'s a recruiter screening 50 candidates, a sales manager
running discovery calls with prospects, or a compliance officer
conducting structured audits --- the pattern is always the same: a
skilled human spends hours on conversations that follow a defined
structure, every time.

The cost is not just time. It\'s inconsistency. Every human interviewer
probes differently. Every sales rep qualifies differently. Outcomes are
hard to compare, evaluate, or improve.

There is no lightweight platform that can:

- Deploy a named, domain-aware AI participant into a live Microsoft
  Teams meeting

- Drive a full structured conversation autonomously --- no human in the
  loop

- Adapt dynamically based on what the other party actually says

- Evaluate responses in real time against a defined rubric or objective

- Produce a structured report immediately after the call

- Switch roles entirely --- interviewer today, sales coach tomorrow ---
  via config alone

+:----------------------------------------------------------------+
| **POC Goal**                                                    |
|                                                                 |
| Prove that Vero --- a configurable AI conversation agent ---    |
| can join a live Teams meeting as a named participant, drive a   |
| complete structured interaction using a loaded Skill Pack,      |
| evaluate the conversation in real time, and deliver a scored    |
| output report. Zero human involvement during the call itself.   |
+-----------------------------------------------------------------+

**02 Product Vision --- Vero**

**Vero is a configurable AI conversation agent that joins Microsoft
Teams meetings as a named participant and drives structured
conversations autonomously. It is not a meeting assistant, a
transcription bot, or a passive listener.**

*\"Real conversations, intelligently driven.\"*

What makes Vero different from point solutions like AI interview tools:

- One platform --- configurable via Skill Packs for any structured
  conversation use case

- Skills-first architecture --- swap the YAML, Vero becomes a different
  expert

- Open-source core --- built on Pipecat, pi-mono, and Recall.ai; no
  proprietary lock-in

- Enterprise-ready channel --- native Teams presence, not a web widget
  or phone dial-in

- Horizontal accelerator --- same engine, different config, every
  vertical

**Skill Pack Library --- Initial Set**

  ------------------------- -------------- ------------------ ------------------
  **Skill Pack**            **Vero         **Conversation     **Output Report**
                            Becomes**      Goal**             

  **interviewer**           **Technical    Assess candidate   Candidate
                            Recruiter**    fit for a defined  scorecard +
                                           role               hire/no-hire
                                                              recommendation

  **sales-coach**           **Sales        Roleplay prospect  Sales rep
                            Manager**      call and coach the performance
                                           rep                scorecard +
                                                              improvement areas

  **solutions-architect**   **Enterprise   Qualify client\'s  Architecture
                            Architect**    technical          requirements
                                           requirements       brief + gap
                                                              analysis

  **discovery-agent**       **Pre-sales    Structured         Qualified
                            Consultant**   BANT/MEDDIC        opportunity
                                           discovery with a   brief + next steps
                                           prospect           

  **compliance-auditor**    **Compliance   Conduct structured Audit response
                            Officer**      compliance Q&A     log + risk flags
                                           session            

  **onboarding-buddy**      **HR           Walk new joiner    Onboarding
                            Onboarding     through policies,  completion record
                            Specialist**   capture sign-offs  
  ------------------------- -------------- ------------------ ------------------

**03 Goals & Non-Goals**

**Goals (POC --- Interviewer Skill Pack)**

- Prove technical feasibility of a fully autonomous AI conversation
  agent on Teams.

- Demonstrate Skill Pack architecture --- interviewer YAML loads
  cleanly, rubric and question bank drive the full session.

- Dynamic question flow --- Vero probes deeper, clarifies, or advances
  based on actual responses.

- Real-time answer evaluation --- scores against rubric as the session
  proceeds.

- Full in-session memory --- references earlier answers in follow-up
  questions.

- End-to-end response latency: other party finishes speaking → Vero
  speaks ≤ 4 seconds.

- Post-session structured report generated automatically within 60
  seconds of call end.

- Config-only role switch --- demonstrate two Skill Packs (interviewer +
  discovery-agent) in POC demo without code changes.

- Reproducible setup in a new Azure + Teams tenant within one business
  day.

**Non-Goals (POC)**

- No ATS, CRM, or HRIS integration --- report generated but not pushed
  to any system.

- No persistent memory across sessions.

- No multi-language support --- English only.

- No custom voice persona --- standard neural TTS voice acceptable.

- No production SLAs, compliance certifications, or multi-tenant
  hardening.

- No video or facial analysis --- audio only.

**04 How It Works**

**Complete flow from session setup to report delivery:**

  -------- ----------------- ----------------------------------------------
  **\#**   **Stage**         **What Happens**

  **1**    **Load Skill      The host creates a Teams meeting and
           Pack**            configures Vero with a Skill Pack (YAML file
                             specifying role, question bank, rubric, agent
                             persona). Vero is invited as a participant
                             alongside the other party.

  **2**    **Vero Joins      At meeting start, Vero joins via Recall.ai
           Meeting**         managed bot. It appears in the Teams
                             participant list under its configured name
                             (e.g. \"Vero --- AI Interviewer\" or \"Vero
                             --- Pre-sales Consultant\"). Vero opens with
                             the skill-defined greeting.

  **3**    **Audio Capture & Recall.ai streams meeting audio to the
           Transcription**   pipeline. Deepgram Nova-3 transcribes in real
                             time with speaker diarisation --- every
                             utterance labelled as Vero or Participant with
                             timestamps.

  **4**    **Turn            Pipecat\'s end-of-utterance (EOU) detector
           Detection**       identifies when the other party has finished
                             speaking. Configurable silence threshold
                             (default: 1.5s). Handles hesitations without
                             cutting the participant off prematurely.

  **5**    **pi-mono Agent   The full transcript, Skill Pack state
           Loop**            (questions asked, scores recorded, section
                             position), and rubric are passed to the
                             pi-mono agent loop via
                             \@mariozechner/pi-agent. The agent decides:
                             (a) evaluate the response, (b) follow up or
                             clarify, or (c) advance to the next question.
                             Returns structured JSON: next_utterance +
                             score_update.

  **6**    **Vero Speaks**   The LLM\'s next utterance is converted to
                             speech by Cartesia TTS. Audio is injected back
                             into the Teams meeting via Recall.ai. The
                             participant hears Vero speak naturally, in
                             real time.

  **7**    **Session         After all Skill Pack sections are complete,
           Closes**          Vero delivers the closing statement defined in
                             the YAML and exits the meeting.

  **8**    **Report          Within 60 seconds of call end, a structured
           Generation**      report is generated using the Skill Pack\'s
                             report template: scores, verbatim excerpts,
                             competency ratings, and output recommendation.
                             Delivered via email and posted to Teams chat.
  -------- ----------------- ----------------------------------------------

**05 Technology Stack**

*Open-source-first. Azure is used only where Microsoft Teams mandates
it. All AI pipeline components are vendor-swappable via Skill Pack
config.*

  --------------- -------------------- ------------------------- --------------------------
  **Layer**       **Component**        **Technology**            **Notes**

  **Teams         **Bot Identity &     Azure AD App Reg + Bot    Mandatory for Teams. OAuth
  Integration**   Auth**               Framework                 2.0.
                                                                 Calls.AccessMedia.All +
                                                                 Calls.JoinGroupCall.All.
                                                                 Only unavoidable Azure
                                                                 dependency.

  **Teams         **Meeting Join &     Recall.ai Managed Bot     Abstracts Graph Real-time
  Integration**   Audio I/O**                                    Media Platform. Bot joins
                                                                 as named participant.
                                                                 Webhooks deliver audio
                                                                 stream. \~\$0.10/min for
                                                                 POC.

  **Audio         **Speech-to-Text**   Deepgram Nova-3           Sub-200ms first
  Pipeline**                           (Streaming)               transcript. Speaker
                                                                 diarisation. Pipecat
                                                                 native integration. Lower
                                                                 cost than Azure STT.

  **Audio         **Turn Detection**   Pipecat EOU Detector      End-of-utterance detection
  Pipeline**                                                     built into Pipecat. 1.5s
                                                                 silence threshold,
                                                                 configurable per Skill
                                                                 Pack.

  **Agent Core**  **LLM + Agent Loop** pi-mono                   Agent loop with tool
                                       \@mariozechner/pi-agent   calling, session
                                                                 management, structured
                                                                 output. Supports Claude
                                                                 (Bedrock), GPT-4o, Gemini.
                                                                 Skill Pack loaded as agent
                                                                 context.

  **Agent Core**  **Unified LLM API**  pi-mono                   Normalised interface
                                       \@mariozechner/pi-ai      across all LLM providers.
                                                                 Single API call regardless
                                                                 of backend. TypeBox schema
                                                                 validation on tool calls.

  **Agent Core**  **Conversation       Pipecat (Python) +        Pipecat manages the audio
                  Orchestration**      pi-mono SDK               frame pipeline. pi-mono
                                                                 SDK (RPC mode) drives the
                                                                 conversation logic and
                                                                 structured outputs.

  **Audio         **Text-to-Speech**   Cartesia Sonic            Fastest TTS (\<100ms first
  Pipeline**                                                     audio chunk). Critical for
                                                                 sub-4s latency. ElevenLabs
                                                                 as fallback for voice
                                                                 quality.

  **Config**      **Skill Pack**       YAML Schema               Role, persona, question
                                                                 bank, follow-up trees,
                                                                 rubric, report template,
                                                                 TTS voice. No code change
                                                                 to deploy a new skill.

  **Reporting**   **Post-Session       LLM structured output →   Triggered on meeting end.
                  Report**             PDF                       JSON scores + transcript →
                                                                 formatted PDF. Emailed via
                                                                 Resend or posted via
                                                                 Teams Bot message.

  **Infra**       **Backend API**      FastAPI (Python)          Orchestrates Recall.ai
                                                                 webhooks, Pipecat
                                                                 sessions, pi-mono agent,
                                                                 report generation.
                                                                 In-memory session state
                                                                 for POC.

  **Infra**       **Hosting**          Docker on EC2 (t3.medium) Single container.
                                                                 Pipecat + FastAPI +
                                                                 pi-mono co-hosted.
                                                                 Recall.ai handles Teams
                                                                 media --- no Windows VM
                                                                 needed.
  --------------- -------------------- ------------------------- --------------------------

+:----------------------------------------------------------------+
| **⚠ Critical Permission: Calls.AccessMedia.All**                |
|                                                                 |
| Application-level Graph API permission --- requires explicit    |
| Azure AD tenant admin consent. #1 setup blocker. Must be        |
| resolved in Week 1. Raise with IT Admin on Day 1 or everything  |
| downstream is blocked.                                          |
+-----------------------------------------------------------------+

**06 pi-mono Integration**

pi-mono (github.com/badlogic/pi-mono) is an open-source AI agent toolkit
that provides the core agent reasoning layer for Vero. It replaces a
custom LLM orchestration layer with a battle-tested, extensible
framework.

**Why pi-mono for Vero**

  --------------------------- -----------------------------------------------
  **Capability**              **How Vero Uses It**

  **\@mariozechner/pi-agent   Drives the conversation decision engine. Each
  Agent Loop**                candidate/participant turn triggers the agent
                              loop: evaluate response → decide next action →
                              return structured JSON. Session state
                              (transcript, scores, section position) passed
                              as context each turn.

  **\@mariozechner/pi-ai      Single interface for Claude 3.5 Sonnet
  Unified LLM API**           (Bedrock), GPT-4o (Azure OpenAI), or Gemini.
                              Vero\'s LLM backend is config-selectable per
                              Skill Pack --- no code change to switch
                              providers.

  **Skills System (SKILL.md   Vero\'s Skill Packs are structured as pi
  standard)**                 Skills. Each Skill Pack YAML follows the pi
                              Skills standard, enabling discovery,
                              validation, and future sharing via npm. The
                              interviewer, sales-coach, and discovery-agent
                              packs are all pi Skills.

  **SDK / RPC Mode**          Pipecat calls pi-mono in RPC mode (subprocess)
                              via JSONL. The pi agent receives transcript +
                              state, returns next_utterance + score JSON.
                              Clean process boundary between audio pipeline
                              (Pipecat/Python) and agent logic
                              (pi-mono/TypeScript).

  **Structured Output +       Tool call arguments are validated against
  TypeBox Validation**        TypeBox schemas before execution. Vero\'s score
                              output (question_id, score 1--5, competency,
                              rationale, action) is schema-enforced --- no
                              malformed JSON reaching the report generator.

  **Session Management**      Agent sessions auto-save to disk (pi default
                              behaviour). Each interview session is a
                              recoverable JSONL file --- useful for post-hoc
                              analysis, debugging, and future cross-session
                              memory feature.

  **Multi-provider Fallback** If primary LLM provider is unavailable,
                              pi-ai\'s model registry allows automatic
                              fallback to a secondary provider. Configured in
                              the Skill Pack model_preferences field.
  --------------------------- -----------------------------------------------

**pi-mono Package Breakdown**

  ------------------- ---------------------------------- ------------------------------
  **Package**         **npm**                            **Role in Vero**

  **pi-agent**        *\@mariozechner/pi-agent*          Core agent session, tool
                                                         calling loop, session
                                                         persistence, RPC server mode

  **pi-ai**           *\@mariozechner/pi-ai*             Unified LLM API, provider
                                                         registry, TypeBox tool
                                                         validation, streaming

  **pi coding agent   *\@mariozechner/pi-coding-agent*   Used during development for
  (pi CLI)**                                             Vero itself --- AI-assisted
                                                         coding of the platform
  ------------------- ---------------------------------- ------------------------------

+:----------------------------------------------------------------+
| **Architecture Note: Pipecat ↔ pi-mono Boundary**               |
|                                                                 |
| Pipecat (Python) handles the real-time audio frame pipeline:    |
| STT → turn detection → TTS injection. pi-mono (TypeScript/Node) |
| handles the conversation intelligence: agent loop, LLM calls,   |
| scoring, session persistence. These two processes communicate   |
| via pi-mono\'s RPC mode over stdin/stdout JSONL --- clean,      |
| testable, independently deployable.                             |
+-----------------------------------------------------------------+

**07 Skill Pack Architecture**

A Skill Pack is a self-contained YAML bundle that transforms Vero into a
domain expert for a specific conversation type. It follows the pi-mono
Skills standard, enabling discovery, validation, and distribution via
npm or git.

**What Changes vs. What Stays Fixed**

  ---------------------- --------------------- ---------------------
  **Layer**              **Generic Core        **Skill Pack (YAML
                         Engine**              Config)**

  **Teams join + audio   ✅ Fixed              ---
  I/O**                                        

  **STT / TTS pipeline** ✅ Fixed              Voice style hint
                                               (optional)

  **Turn detection**     ✅ Fixed              Silence threshold
                                               (configurable)

  **pi-mono agent loop** ✅ Fixed              System prompt,
                                               rubric, section
                                               definitions

  **Question /           ✅ Fixed logic        Question bank,
  conversation flow**                          follow-up probe trees

  **Report generation**  ✅ Fixed template     Report schema,
                         engine                scoring dimensions,
                                               output format

  **Agent name +         ---                   ✅ Per Skill Pack
  persona**                                    

  **Conversation goal +  ---                   ✅ Per Skill Pack
  sections**                                   

  **Rubric + evaluation  ---                   ✅ Per Skill Pack
  criteria**                                   

  **LLM provider +       ---                   ✅ Per Skill Pack
  model**                                      (default: Claude 3.5
                                               Sonnet)
  ---------------------- --------------------- ---------------------

**Skill Pack YAML Schema**

  ----------------------------------------------- ----------- -----------------------------------
  **Field**                                       **Type**    **Description**

  **skill.id**                                    *string*    Unique identifier (e.g.
                                                              interviewer-v1, discovery-agent-v1)

  **skill.name**                                  *string*    Human label used in admin UI and
                                                              reports

  **skill.version**                               *semver*    Version string for the Skill Pack

  **agent.name**                                  *string*    Vero\'s spoken name in this role
                                                              (e.g. \"Alex\", \"Vero\")

  **agent.persona**                               *string*    Instruction: professional,
                                                              consultative, encouraging, direct

  **agent.language**                              *BCP-47*    Language code. Default: en-US

  **agent.max_duration_minutes**                  *integer*   Hard stop. Vero closes session at
                                                              this limit.

  **agent.model_preferences**                     *array*     Ordered LLM preferences:
                                                              \[{provider, model}\]. pi-ai
                                                              resolves availability.

  **agent.tts_voice**                             *string*    Cartesia or ElevenLabs voice ID.
                                                              Default: cartesia:sonic-english

  **sections\[\]**                                *array*     Ordered list of conversation
                                                              sections (intro, main, close)

  **sections\[\].questions\[\]**                  *array*     Ordered questions within each
                                                              section

  **sections\[\].questions\[\].text**             *string*    The exact question Vero will ask

  **sections\[\].questions\[\].probes\[\]**       *array*     Follow-up probes if response is
                                                              incomplete or scores \< 3

  **sections\[\].questions\[\].competency**       *string*    Competency tag mapped to rubric
                                                              entry

  **sections\[\].questions\[\].max_follow_ups**   *integer*   Max follow-up turns before
                                                              advancing. Default: 2

  **rubric\[\].competency**                       *string*    Competency name matching question
                                                              tags

  **rubric\[\].scores\[1..5\]**                   *string*    Description of 1--5 answer quality
                                                              for this competency

  **report.template**                             *enum*      scorecard \| discovery-brief \|
                                                              audit-log \| coaching-report

  **report.email_to**                             *string*    Recipient email for post-session
                                                              report

  **report.include_transcript**                   *boolean*   Attach full transcript to report.
                                                              Default: true
  ----------------------------------------------- ----------- -----------------------------------

**08 LLM Conversation Engine Design**

The pi-mono agent loop handles two jobs on every participant turn in a
single structured output call.

  -------------- ------------------------------------------------------
  **Job**        **Description**

  **Evaluate**   Score the participant\'s response against the Skill
                 Pack rubric for the current question. Assign 1--5
                 score per competency. Flag incomplete, off-topic, or
                 strong-signal responses.

  **Decide**     Choose next action: (a) ask a follow-up probe, (b) ask
                 a clarifying question, (c) acknowledge and advance to
                 the next question, or (d) close the session if all
                 sections are done.
  -------------- ------------------------------------------------------

**Structured Output Schema (per turn)**

  --------------------- ----------- -------------------------------------
  **Field**             **Type**    **Description**

  **next_utterance**    *string*    Exact text Vero will speak next.
                                    Passed directly to Cartesia TTS.

  **action**            *enum*      follow_up \| clarify \| advance \|
                                    close

  **question_id**       *string*    Current question ID from the Skill
                                    Pack YAML.

  **score**             *integer    Score for this response. Null if
                        1--5*       action is follow_up or clarify.

  **score_rationale**   *string*    One-sentence justification for the
                                    score.

  **competency**        *string*    Competency being assessed (from Skill
                                    Pack rubric).

  **flags**             *array*     Optional: \[\'incomplete\',
                                    \'off_topic\', \'strong_signal\',
                                    \'redirect_needed\'\]
  --------------------- ----------- -------------------------------------

**System Prompt Components (injected by pi-mono agent)**

- Vero persona --- name, role from Skill Pack, conversation style

- Skill Pack context --- goal, sections, current position, questions
  asked so far

- Rubric --- competency descriptions and 1--5 scoring guide

- Full session transcript --- every utterance attributed to speaker

- Scores recorded so far --- running evaluation state

- Conversation rules --- max follow-ups, silence handling, off-topic
  redirect logic

- Structured output format --- TypeBox schema enforced via pi-ai tool
  validation

**09 User Stories**

  --------------- ---------------------------------------------------
  **Persona**     **Story**

  **Candidate**   As a candidate, I want to join a Teams meeting and
                  be interviewed by Vero, so that I can complete a
                  screening at a time convenient to me without
                  waiting for a recruiter\'s calendar slot.

  **Candidate**   As a candidate who gave an incomplete answer, I
                  want Vero to probe further rather than immediately
                  moving on, so that I have a fair opportunity to
                  demonstrate my knowledge.

  **Prospect      As a prospect on a discovery call, I want to be
  (Discovery)**   asked structured questions about my environment and
                  challenges, so that the pre-sales team gets
                  accurate requirements without a 90-minute call with
                  a consultant.

  **Sales Rep     As a sales rep in training, I want to roleplay a
  (Coaching)**    prospect call with Vero acting as the sales
                  manager, so that I can practise objection handling
                  without blocking a senior colleague\'s time.

  **Recruiter**   As a recruiter, I want to invite Vero to a Teams
                  meeting with a candidate exactly like inviting a
                  person, so that setup requires zero technical steps
                  on my end.

  **Recruiter**   As a recruiter, I want a structured PDF scorecard
                  in my inbox within 5 minutes of the interview
                  ending, so that I can shortlist candidates without
                  reviewing a full transcript.

  **Hiring        As a hiring manager, I want to configure the
  Manager**       question bank and rubric in a YAML file for my
                  specific role, so that Vero interviews precisely
                  for the competencies I care about.

  **HR Ops**      As an HR ops lead, I want Vero to run first-round
                  screens for 20 candidates in parallel, so that
                  time-to-shortlist drops from 2 weeks to 2 days.

  **Admin**       As a Vero admin, I want to swap the active Skill
                  Pack via a config edit and service restart, so that
                  I can deploy Vero for a new use case without any
                  code changes or redeployment.
  --------------- ---------------------------------------------------

**10 Requirements**

  --------- ------------------------------ ------------------------------
  **Pri**   **Requirement**                **Acceptance Criteria**

  **P0**    Vero joins a scheduled Teams   Bot appears in participant
            meeting as a named participant list within 10 seconds. Name
            when invited.                  and role visible to all
                                           participants.

  **P0**    Vero loads the configured      Opening statement uses skill
            Skill Pack and greets the      persona. Participant\'s name
            participant using the          used. Session format stated.
            skill-defined opening.         

  **P0**    Vero asks questions in the     100% of configured questions
            Skill Pack order, section by   asked. Order matches YAML.
            section, and advances          Section transitions announced
            autonomously.                  verbally.

  **P0**    Vero dynamically follows up    Follow-up probe used in ≥ 90%
            when a response scores \< 3 or of incomplete answers. Max
            is flagged incomplete.         follow-ups per question not
                                           exceeded.

  **P0**    pi-mono agent evaluates each   Score + rationale recorded for
            response in real time and      every question. No question
            records a structured score.    skipped. TypeBox schema
                                           validated.

  **P0**    End-to-end response latency ≤  p90 ≤ 4s across 20 test turns.
            4 seconds (participant         p50 ≤ 2.5s.
            finishes → Vero first spoken   
            word).                         

  **P0**    Post-session report generated  Report includes per-question
            and emailed within 60 seconds  scores, competency summary,
            of call end.                   transcript excerpts,
                                           recommendation.

  **P0**    Config-only Skill Pack swap    Interviewer and
            demonstrated --- two different discovery-agent Skill Packs
            skills without code change.    both run successfully in POC
                                           demo.

  **P1**    Vero handles \"can you repeat  Vero repeats last question
            that?\" gracefully.            verbatim. No scoring penalty
                                           applied.

  **P1**    Vero handles extended silence  Soft prompt used. No immediate
            (\> 8s) with a gentle prompt.  scoring penalty. Configurable
                                           per Skill Pack.

  **P1**    All Skill Pack fields          Changing any field + service
            (persona, voice, max_duration, restart produces expected
            model) are config-driven.      behaviour. No code change.

  **P1**    Vero posts a text summary to   Summary message visible in
            Teams meeting chat at session  Teams chat within 30 seconds
            end.                           of Vero leaving the meeting.

  **P2**    Vero detects off-topic         Redirect used after \> 45s on
            responses and gently           unrelated content. No score
            redirects.                     penalty for the deviation
                                           itself.

  **P2**    Report includes a competency   Visual chart in PDF.
            radar chart (scores vs.        Competencies on axes.
            benchmark).                    Candidate vs. expected
                                           benchmark plotted.
  --------- ------------------------------ ------------------------------

**11 POC Success Criteria**

Declared successful when ALL of the following pass after a 60-minute
live demo with 3+ internal observers.

  ----------------------- -------------- ---------------------------
  **Criterion**           **Pass         **Measurement**
                          Threshold**    

  **Vero joins meeting    **5 / 5 test   Manual test --- invite bot
  when invited**          joins**        5 times from separate
                                         accounts

  **Full structured       **100% of      Observer verifies against
  session completed**     questions      YAML question list
                          asked**        

  **Dynamic follow-up on  **≥ 90%        Session state log reviewed
  incomplete answers**    follow-up rate post-interview
                          on sub-3       
                          scores**       

  **Response latency ---  **≤ 4          Timestamped transcript ---
  p90**                   seconds**      EOU to first agent word

  **Response latency ---  **≤ 2.5        Same measurement
  p50**                   seconds**      

  **Skill Pack swap       **Two skills   Observer confirms
  without code change**   run cleanly in config-only change, no
                          demo**         redeployment

  **Response relevance    **≥ 3.5 / 5    3 observers rate each Vero
  --- peer rating**       average**      turn post-session

  **Scoring accuracy vs.  **≥ 80%        Same answers scored
  human rater**           agreement (±1  independently by human;
                          point)**       compare

  **Report quality ---    **≥ 3.5 / 5    Rated against pre-written
  peer rating**           average**      gold report

  **No false positive     **0 in 60-min  Observer counts unprompted
  interruptions**         demo**         Vero interruptions

  **Setup in clean        **≤ 1 business One engineer, fresh Azure +
  tenant**                day**          Teams tenant, runbook
                                         followed
  ----------------------- -------------- ---------------------------

**12 Open Questions & Risks**

  ----------------------- ------------- --------------------------------
  **Question / Risk**     **Status**    **Action**

  Calls.AccessMedia.All   🔴 Blocking   Raise with IT Admin on Day 1.
  admin consent ---                     Week 2 cannot start without
  without this the bot                  this.
  cannot receive meeting                
  audio.                                

  Recall.ai latency       🟡 Evaluate   Benchmark in Week 1 test calls.
  overhead --- does the                 Acceptable if \< 300ms
  managed bot add                       additional.
  measurable RTT?                       

  Pipecat ↔ pi-mono RPC   🟡 Mitigate   Benchmark RPC overhead vs.
  boundary --- JSONL                    direct SDK embedding. If \>
  subprocess adds a                     200ms, switch to direct
  process hop.                          \@mariozechner/pi-agent SDK
                                        calls from Python via
                                        subprocess.

  pi-mono is TypeScript / 🟡            Single Docker container with
  Node --- Pipecat is     Engineering   Node + Python installed.
  Python. Two runtimes to               FastAPI + Pipecat (Python)
  containerise.                         spawns pi-mono (Node) as child
                                        process via RPC mode.

  LLM interruption on     🟡 Mitigate   Tune Pipecat EOU silence
  long responses ---                    threshold. Add energy-level
  streaming STT may                     check to avoid mid-sentence cut.
  trigger EOU                           
  prematurely.                          

  Participant perception  🟡 Design     Upfront disclosure in meeting
  --- some candidates may               invite. Evaluate candidate
  disengage with an AI                  feedback in POC demo.
  interviewer.                          

  Legal / GDPR --- AI     🔴 Blocking   POC internal-only until Legal
  scoring of job          (external)    reviews. Flag explicitly for any
  candidates may be                     client engagement.
  regulated in certain                  
  jurisdictions.                        

  Recall.ai cost at scale 🟢 Low risk   \~\$200 for full POC test suite.
  --- \$0.10/min = \$6                  Production: evaluate direct
  for a 60-min session.                 Graph RMP integration.

  pi-mono Skills standard 🟢 Low risk   Validate Skill Pack YAML against
  compatibility --- Skill               pi Skills standard in Week 1. pi
  Pack YAML must validate               provides validator.
  against pi schema.                    
  ----------------------- ------------- --------------------------------

**13 4-Week POC Timeline**

  ---------- ---------------- ------------------------------------------
  **Week**   **Focus**        **Deliverables**

  **Week 1** **Setup &        Azure AD app registration.
             Infra**          Calls.AccessMedia.All admin consent.
                              Recall.ai account + Teams bot configured.
                              pi-mono installed and agent session
                              running locally. Docker container with
                              Node + Python. \"Hello World\" Vero joins
                              test meeting, speaks greeting, exits.
                              First Skill Pack YAML validated against pi
                              Skills standard.

  **Week 2** **Audio          Deepgram STT wired to Recall.ai audio
             Pipeline**       stream. Pipecat EOU turn detection
                              verified. Pipecat ↔ pi-mono RPC boundary
                              working. Rolling in-memory transcript
                              flowing into pi agent context. Transcript
                              accuracy test: 30-min scripted session ≥
                              85% accuracy.

  **Week 3** **Conversation   pi-mono agent loop driving full question
             Engine**         flow from Skill Pack YAML. Follow-up and
                              clarification logic working. Cartesia TTS
                              injected back into meeting via Recall.ai.
                              First end-to-end mock session: Vero runs a
                              complete interview with one internal
                              candidate. Latency baseline measured.

  **Week 4** **Polish +       Latency optimisation to hit p90 ≤ 4s.
             Demo**           Post-session report generation. Skill Pack
                              swap demonstration (interviewer →
                              discovery-agent). Edge case handling
                              (silence, off-topic, repeat). Demo script
                              prep. Internal POC demo with 3+ observers.
                              Evaluation scorecard completed.
  ---------- ---------------- ------------------------------------------

+:----------------------------------------------------------------+
| **If POC Passes --- Phase 1 Additions**                         |
|                                                                 |
| ATS / CRM / HRIS write-back (Greenhouse, Salesforce, Workday).  |
| Persistent candidate/prospect memory across sessions.           |
| Multi-language Skill Packs (Arabic, Hindi). Custom voice        |
| persona per Skill Pack. Parallel session capacity (10+          |
| simultaneous Vero instances). Twilio SIP trunk for phone call   |
| replacement. Skill Pack marketplace --- share and install skill |
| packs via npm.                                                  |
+-----------------------------------------------------------------+
