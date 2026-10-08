# Skill Packs — Authoring Guide

Skill Packs are YAML files that define everything about a Vero conversation: who the agent is, what it asks, how it scores responses, and what report it produces. The same agent runtime loads whichever Skill Pack you choose — different skills create completely different expert behaviours.

---

## Full YAML Reference

```yaml
skill:
  id: interviewer-v1          # Unique identifier (snake-case, version suffix)
  name: Technical Interviewer  # Display name shown in UI
  version: 1.0.0               # Semantic version
  channels: [teams, phone]     # Optional: restrict to one channel (default: both)

agent:
  name: Alex                   # Agent introduces itself with this name
  persona: professional and encouraging  # One-line personality description
  language: en-IN              # BCP-47 language code (see Languages section)
  max_duration_minutes: 45     # Hard limit; agent closes session gracefully
  opening_utterance: "Hello, I'm Alex. Thanks for joining me today!"  # Optional custom greeting
  model_preferences:
    - provider: sarvam
      model: sarvam-30b        # sarvam-30b (fast) or sarvam-105b (most capable)
  tts_voice: sarvam:shubh      # See Voices section

sections:
  - id: intro
    title: Introduction
    mode: guided               # guided (default) or intelligent
    max_duration_seconds: 300  # Optional: auto-advance after 5 minutes
    questions:                 # Guided mode — fixed sequence
      - id: q1
        text: "Can you walk me through your background?"
        probes:
          - "What was your most recent role?"
          - "What technologies did you work with day to day?"
        competency: communication
        max_follow_ups: 2

  - id: discovery
    title: Needs Discovery
    mode: intelligent          # Intelligent mode — objectives-based
    objectives:
      - "Understand the customer's current workflow and pain points"
      - "Identify decision-making process and stakeholders"
      - "Assess timeline and budget constraints"
    competency: discovery

rubric:
  - competency: communication
    scores:
      1: "Unclear, disorganised, hard to follow"
      3: "Clear and structured with some gaps"
      5: "Concise, well-structured, compelling"
  - competency: discovery
    scores:
      1: "No meaningful information uncovered"
      3: "Key facts gathered but gaps remain"
      5: "Complete picture with next steps clear"

report:
  template: scorecard          # See Report Templates section
  email_to: hiring@example.com
  include_transcript: true

# Optional: pre-session context fields shown in the launcher UI
input_schema:
  - name: candidate_name
    type: string
    required: true
    description: "Full name of the candidate"
  - name: role_applied_for
    type: string
    required: true
    description: "The role being assessed"
  - name: interview_level
    type: enum
    values: [junior, mid, senior, staff]
    required: false
```

---

## Conversation Modes

### Guided Mode

The agent follows a fixed question sequence. After each answer it may ask probes or follow-ups before advancing. Best for structured interviews, assessments, and compliance workflows.

```yaml
sections:
  - id: technical
    title: Technical Assessment
    mode: guided
    questions:
      - id: q_system_design
        text: "Walk me through how you'd design a URL shortener."
        probes:
          - "How would you handle 10 million requests per day?"
          - "What database would you choose and why?"
        competency: system_design
        max_follow_ups: 2      # Probes attempted before advancing (default: 2)
```

**Agent behaviour in guided mode:**
- Asks the question exactly as written
- Uses probes if the answer is incomplete or shallow
- Scores the answer against the rubric
- Decides `advance` (next question), `clarify` (ask a probe), or `follow_up` (dig deeper)

### Intelligent Mode

The agent pursues a set of objectives through natural conversation rather than a fixed script. Best for sales discovery, coaching, and exploratory conversations.

```yaml
sections:
  - id: discovery
    title: Needs Discovery
    mode: intelligent
    objectives:
      - "Understand the customer's current workflow and pain points"
      - "Identify the decision-maker and buying process"
      - "Assess urgency and budget"
    competency: discovery
```

**Agent behaviour in intelligent mode:**
- Adapts questions dynamically based on what the participant says
- Checks off objectives as they are naturally covered
- Closes the section when all objectives are met or time is up

---

## Rubric Design

Each competency gets a rubric with anchored score descriptions. Scores are always 1–5 integers.

```yaml
rubric:
  - competency: problem_solving
    scores:
      1: "No structured approach; jumps to conclusions"
      2: "Some structure but key steps missing"
      3: "Reasonable approach with minor gaps"
      4: "Systematic and clear with good trade-off awareness"
      5: "Exceptional clarity, considers edge cases and constraints"
```

**Tips:**
- Name competencies in `snake_case` and reference them consistently in questions
- Write score anchors as observable behaviours, not abstract qualities
- Score 3 should represent "meets expectations" — calibrate 1 and 5 as extremes

---

## Report Templates

| Template | Best for | Key fields |
|---|---|---|
| `scorecard` | Interviews | Competency scores, hire/no-hire, per-question rationale |
| `discovery-brief` | Sales discovery | Opportunity summary, pain points, next steps |
| `coaching-report` | Sales coaching | Strengths, development areas, specific feedback |
| `audit-log` | Compliance | Response log, risk flags, attestation |
| `onboarding-record` | HR onboarding | Completion status, open items, follow-up actions |
| `investigation-report` | Customer complaints | Complaint summary, root cause, resolution actions |

```yaml
report:
  template: scorecard
  email_to: hiring@example.com
  include_transcript: true     # Append full turn-by-turn transcript to report
```

---

## Languages

Set `agent.language` to a BCP-47 code. Vero uses Sarvam AI for all speech processing.

| Code | Language |
|---|---|
| `en-IN` | English (Indian accent) |
| `hi-IN` | Hindi |
| `ta-IN` | Tamil |
| `te-IN` | Telugu |
| `kn-IN` | Kannada |
| `ml-IN` | Malayalam |
| `bn-IN` | Bengali |
| `gu-IN` | Gujarati |
| `mr-IN` | Marathi |
| `pa-IN` | Punjabi |
| `or-IN` | Odia |
| `ur-IN` | Urdu |

---

## Voices (Sarvam Bulbul v3)

Set `agent.tts_voice` to `sarvam:<voice-name>`. The agent introduces itself using the voice name.

| Voice | Gender | Character |
|---|---|---|
| `sarvam:meera` | Feminine | Warm, professional |
| `sarvam:arjun` | Masculine | Confident, clear |
| `sarvam:ananya` | Feminine | Friendly, engaging |
| `sarvam:rahul` | Masculine | Authoritative |
| `sarvam:priya` | Feminine | Professional, calm |
| `sarvam:vikram` | Masculine | Energetic, approachable |
| `sarvam:pooja` | Feminine | Soft, empathetic |
| `sarvam:rohan` | Masculine | Conversational |
| `sarvam:simran` | Feminine | Bright, articulate |
| `sarvam:kavya` | Feminine | Clear, precise |

---

## Input Schema (Session Context)

The `input_schema` section adds dynamic fields to the Session Launcher UI. These values are injected into the agent's context at session start (e.g. candidate name, role, customer account).

```yaml
input_schema:
  - name: candidate_name
    type: string
    required: true
    description: "Full name of the candidate"

  - name: experience_years
    type: number
    required: false
    description: "Years of relevant experience"

  - name: interview_level
    type: enum
    values: [junior, mid, senior, staff]
    required: true
    description: "Seniority level being assessed"

  - name: background_notes
    type: text              # Multi-line textarea
    required: false
    description: "Any notes about the candidate's background"
```

**Supported field types:** `string`, `number`, `boolean`, `enum`, `text`

Alternative UI-friendly schema format:

```yaml
input_schema:
  - name: candidate_name
    type: text
    label: "Candidate Name"
    required: true
  - name: experience_level
    type: select
    label: "Experience Level"
    options: ["junior", "mid", "senior"]
    required: true
  - name: call_target
    type: select
    label: "Call Target"
    options: ["internal", "customer"]
    required: true
  - name: include_feedback
    type: checkbox
    label: "Include peer feedback section"
    required: false
```

**UI field types:** `text`, `number`, `select`, `textarea`, `checkbox`

---

## Context Data

Values from `input_schema` are passed as `context_data` at session launch. These values are available in persona text and question templates using Jinja2 syntax.

### How It Works

1. Define fields in `input_schema`
2. User fills values in Session Launcher UI
3. Values injected into templates as `{{ variable_name }}`
4. Agent uses resolved text at runtime

### Template Variables in Persona

```yaml
agent:
  name: Sarah
  persona: |
    You are interviewing {{ candidate_name }} for the {{ role_applied_for }} position.
    They have {{ experience_years | default('unknown') }} years of experience.
    Tailor your questions to the {{ experience_level }} level.
```

### Template Variables in Questions

```yaml
questions:
  - id: q_intro
    text: "Hi {{ candidate_name }}, tell me about your experience with {{ primary_skill }}."
    competency: communication
```

### Section Filtering with `_mode`

Use the special `_mode` key in context_data to filter which sections are included based on their `mode` field:

```yaml
# In skill pack:
sections:
  - id: internal_review
    title: Internal Team Review
    mode: internal
    questions: [...]
  - id: customer_interview  
    title: Customer Interview
    mode: customer
    questions: [...]
  - id: common_questions
    title: General Questions
    mode: all
    questions: [...]

# At session launch, context_data with _mode: "internal" 
# includes only sections where mode is "internal" or "all"
```

---

## Jinja2 Template Syntax

Vero uses Jinja2 for template rendering. Common patterns:

### Variable Substitution

```yaml
text: "Welcome {{ candidate_name }}, let's discuss the {{ role_applied_for }} role."
```

### Default Values

```yaml
text: "You have {{ experience_years | default('several') }} years of experience."
```

### Conditionals

```yaml
persona: |
  {% if call_target == 'internal' %}
  Focus on team dynamics, collaboration, and internal processes.
  Ask about department relationships and workflow improvements.
  {% else %}
  Focus on service quality, satisfaction, and customer experience.
  Ask about product usage and support interactions.
  {% endif %}
```

### Conditional Questions

```yaml
text: |
  {% if experience_level == 'senior' %}
  Describe a time you led a complex architectural decision.
  {% else %}
  Tell me about a challenging bug you debugged.
  {% endif %}
```

---

## Opening Utterance

Customize the agent's greeting with `opening_utterance` in the agent configuration:

```yaml
agent:
  name: Sarah
  persona: HR investigator conducting employee complaint interviews
  opening_utterance: "Hello, I'm Sarah from HR. Thank you for taking the time to speak with me today about the complaint."
```

**Behavior:**
- If provided, the agent speaks this exact text at conversation start
- If not provided, the agent generates a greeting from the persona description
- Must be at the top level of `agent` configuration, not nested in sections

---

## Section Time Limits

Set `max_duration_seconds` on any section to enforce a time limit:

```yaml
sections:
  - id: technical
    title: Technical Assessment
    mode: guided
    max_duration_seconds: 300  # 5 minutes
    questions: [...]
```

**Behavior:**
- When time limit is reached, agent gracefully wraps up the section
- Agent moves to the next section automatically
- Useful for timed assessments or keeping conversations on track

---

## Channel Restrictions

By default a Skill Pack is available on both Teams and Phone channels. Restrict if needed:

```yaml
skill:
  channels: [teams]    # Teams only
  # channels: [phone]  # Phone only
  # channels: [teams, phone]  # Both (default)
```

---

## AI-Generated Skill Packs

The UI includes an AI generation feature. Describe the skill in plain English and Vero generates a complete YAML:

> "A technical interview for senior backend engineers focused on system design, API design, and distributed systems. 45 minutes, hire/no-hire scorecard."

The generator determines: conversation mode, sections, questions/objectives, rubric competencies, report template, and agent persona. Review and edit the output before activating.

---

## Version History

Every save creates a new version. The UI shows full version history with diffs. You can view any past version but not roll back automatically — copy the YAML from history and save it as a new version if needed.

---

## Seeded Skill Packs

The following Skill Packs are included out of the box (via `backend/seed_skill_packs.py`):

| ID | Name | Mode | Report |
|---|---|---|---|
| `interviewer-v1` | Technical Interviewer | Guided | Scorecard |
| `sales-coach-v1` | Sales Coach | Guided | Coaching report |
| `solutions-architect-v1` | Solutions Architect | Intelligent | Requirements brief |
| `discovery-agent-v1` | Discovery Agent | Intelligent | Discovery brief |
| `compliance-auditor-v1` | Compliance Auditor | Guided | Audit log |
| `onboarding-buddy-v1` | Onboarding Buddy | Guided | Onboarding record |
| `complaint-investigator-v1` | Complaint Investigator | Guided | Investigation report |

Activate any of these from the Skill Packs page, then launch a session.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Template variables not substituting | Ensure variable names in `{{ ... }}` match `input_schema` field names exactly (case-sensitive) |
| Sections not appearing | Check the `mode` field on sections matches the `_mode` value in context_data |
| Opening utterance ignored | Verify `opening_utterance` is at the top level of agent configuration, not nested in sections |
| Context data not available | Confirm values were provided in Session Launcher and field names match schema |
| Time limit not triggering | Ensure `max_duration_seconds` is set on the section, not at agent level |
