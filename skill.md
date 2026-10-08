# Skill Pack Guide

## Overview

Skill Packs define conversation blueprints for AI agents. They are written in YAML and uploaded via the Vero UI or API. Each skill pack defines:

- **Agent persona** — How the AI should behave and introduce itself
- **Conversation flow** — Questions to ask and competencies to assess
- **Scoring rubric** — How to evaluate responses (1–5 scale)
- **Report template** — Output format for post-session summaries
- **Input schema** (optional) — Dynamic parameters filled at session launch

The AI engine runs on **Sarvam AI** (speech recognition, language model, and text-to-speech). Voices and language are selected in the UI when launching a session.

---

## Quick Start

### Minimal Skill Pack (Guided Mode)

```yaml
skill:
  id: my-skill-v1
  name: My First Skill
  version: 1.0.0

channels:
  - teams
  - phone

agent:
  name: Priya
  persona: You are a helpful assistant conducting a structured conversation.
  max_duration_minutes: 30

sections:
  - id: intro
    title: Introduction
    mode: guided
    questions:
      - id: q1
        text: "Tell me about yourself."
        probes:
          - "Can you elaborate on that?"
          - "What specific examples can you share?"
        competency: communication
        max_follow_ups: 2
    max_duration_seconds: 1800

rubric:
  - competency: communication
    scores:
      1: "Poor communication, unclear responses"
      2: "Below average, hard to follow"
      3: "Adequate, mostly clear"
      4: "Good communication, well structured"
      5: "Excellent, concise and compelling"

report:
  template: audit-log
  email_to:
    - admin@example.com
  include_transcript: true
```

### Intelligent Mode Skill Pack

```yaml
skill:
  id: coaching-skill-v1
  name: Coaching Session
  version: 1.0.0

channels:
  - teams
  - phone

agent:
  name: Aditya
  persona: You are an empathetic coach helping people work through challenges.

sections:
  - id: main
    title: Coaching Session
    mode: intelligent
    objectives: |
      - Understand the participant's current situation and challenges
      - Identify underlying concerns and root causes
      - Explore potential solutions and approaches
      - Provide supportive guidance and next steps
      - Ensure the participant feels heard and supported
    max_duration_seconds: 3600

rubric:
  - competency: engagement
    scores:
      1: "Minimal engagement, one-word answers"
      3: "Moderate engagement, participates adequately"
      5: "High engagement, reflective and open"

report:
  template: coaching-report
  email_to: []
  include_transcript: true
```

---

## Full Schema Reference

### Skill Definition

```yaml
skill:
  id: unique-skill-id-v1      # Unique identifier (required)
  name: Display Name           # Human-readable name (required)
  version: 1.0.0              # Semantic version (required)
```

### Channels

```yaml
channels:
  - teams    # Microsoft Teams (via Recall.ai bot)
  - phone    # Outbound phone call (via LiveKit SIP + Twilio)
```

Omitting `channels` defaults to both `teams` and `phone`.

### Input Schema (Optional)

Define dynamic inputs that appear in the launch form when starting a session:

```yaml
input_schema:
  - name: field_name          # Variable name for templates (required)
    type: string              # Type: string, text, number, boolean, enum (required)
    required: true            # Whether field is mandatory (default: true)
    description: "Help text"  # Shown in UI below the field
    values: [a, b, c]         # For enum type only — dropdown options
```

**Available Types:**

| Type | UI Component | Example Use |
|------|--------------|-------------|
| `string` | Single-line text input | Names, IDs, reference numbers |
| `text` | Multi-line textarea | Complaints, descriptions, notes |
| `number` | Number input | Age, score, quantity |
| `boolean` | Yes/No dropdown | Flags, confirmations |
| `enum` | Dropdown select | Categories, priorities, statuses |

### Agent Configuration

```yaml
agent:
  name: Priya                 # How the agent introduces itself (matched to voice in UI)
  persona: >                  # System prompt / personality (supports Jinja2 templates)
    You are {{agent_name}}, a professional interviewer.
    Today you are speaking with {{candidate_name}}.
  max_duration_minutes: 30    # Session timeout in minutes
```

**Voice & Language** are selected per-session in the UI (not in the YAML). Available Sarvam Bulbul v3 voices:

| Voice | Gender | Style |
|-------|--------|-------|
| `shubh` | Masculine | Neutral, professional |
| `aditya` | Masculine | Warm, conversational |
| `ritu` | Feminine | Clear, authoritative |
| `priya` | Feminine | Friendly, empathetic |
| `neha` | Feminine | Energetic, engaging |
| `rahul` | Masculine | Calm, measured |

Supported languages: English (Indian), Hindi, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Odia, Urdu.

> **Tip:** Name the agent in YAML to match the voice you plan to select in the UI — e.g., agent `name: Priya` with voice `priya`.

### Sections and Conversation Modes

Sections support two conversation modes:

**Guided Mode** — Fixed question sequence (interviews, assessments, surveys):
```yaml
sections:
  - id: section-id
    title: Section Title
    mode: guided              # Fixed question sequence
    questions:
      - id: q1
        text: "Question text?"
        probes:               # Follow-up prompts if answer is short
          - "Can you elaborate?"
          - "Tell me more about that."
        competency: skill_name  # Must match a rubric competency
        max_follow_ups: 2     # Max probe rounds per question
    max_duration_seconds: 1800
```

**Intelligent Mode** — Objectives-based adaptive conversation (coaching, discovery, advisory):
```yaml
sections:
  - id: section-id
    title: Section Title
    mode: intelligent         # Adaptive, objectives-driven
    objectives: |
      - Objective 1: Description of what to achieve
      - Objective 2: Another goal for the conversation
      - Objective 3: Final objective
    max_duration_seconds: 3600
```

| Mode | Use Case | Structure | Agent Behaviour |
|------|----------|-----------|----------------|
| `guided` | Interviews, assessments, surveys | Fixed question sequence with probes | Asks each question in order, uses probes for clarification |
| `intelligent` | Coaching, discovery, advisory | Objectives-based | Adaptively steers conversation to achieve objectives, natural flow |

### Rubric Scoring

```yaml
rubric:
  - competency: competency_name   # Must match question competency fields
    scores:
      1: "Description of score 1 (lowest)"
      2: "Description of score 2"
      3: "Description of score 3 (mid)"
      4: "Description of score 4"
      5: "Description of score 5 (highest)"
```

Scores are evaluated per candidate turn. The report summarises per-competency averages.

### Report Configuration

```yaml
report:
  template: scorecard         # Template type (see below)
  email_to:
    - recipient@example.com   # Auto-email on session close
  include_transcript: true    # Whether to embed conversation in report
```

**Report Templates:**

| Template | Best For | Content |
|----------|----------|---------|
| `scorecard` | Structured interviews | Competency scores, per-question ratings, overall assessment |
| `discovery-brief` | Discovery / sales calls | Key themes, insights, next steps |
| `audit-log` | Compliance / investigations | Chronological facts, flags, verbatim quotes |
| `coaching-report` | Coaching sessions | Goals achieved, areas for growth, action items |

---

## Examples

### Example 1: Complaint Investigator

Investigates customer complaints by calling internal staff or customers.

```yaml
skill:
  id: complaint-investigator-v1
  name: Complaint Investigator
  version: 1.0.0

channels:
  - phone

input_schema:
  - name: call_target
    type: enum
    required: true
    values: [internal, customer]
    description: "Who are you calling — internal staff or the customer who filed the complaint?"
  - name: complaint_summary
    type: text
    required: true
    description: "Full details of the complaint — includes caller info, incident details, and all relevant context"

agent:
  name: Neha
  persona: >
    You are Neha, a professional complaint investigator with expertise in gathering
    facts and understanding both sides of a situation.

    INVESTIGATION CONTEXT:
    - Complaint: {{complaint_summary}}

    {% if call_target == 'internal' %}
    YOU ARE CALLING AN INTERNAL STAFF MEMBER:
    - Be respectful of their time and role
    - Frame this as fact-gathering, not an interrogation
    - Ask open-ended questions first, then specific follow-ups
    {% else %}
    YOU ARE CALLING THE CUSTOMER:
    - Show empathy for their experience
    - Acknowledge you have the complaint details — don't make them repeat everything
    - Ask clarifying questions to fill gaps in your understanding
    {% endif %}
  max_duration_minutes: 20

sections:
  - id: intro
    title: Introduction
    mode: guided
    questions:
      - id: intro-1
        text: "Hello, I'm calling about a complaint we received. Do you have a few minutes to speak?"
        competency: professionalism
        max_follow_ups: 1

  - id: facts
    title: Fact Finding
    mode: guided
    questions:
      - id: facts-1
        text: "{% if call_target == 'internal' %}What do you remember about this incident?{% else %}Can you walk me through what happened from your perspective?{% endif %}"
        probes:
          - "Were there any unusual circumstances?"
          - "Is there anything else I should know?"
        competency: information_gathering
        max_follow_ups: 3

rubric:
  - competency: professionalism
    scores:
      1: "Unprofessional, defensive or dismissive"
      3: "Professional and cooperative"
      5: "Exceptional — proactive and transparent"
  - competency: information_gathering
    scores:
      1: "Missed key facts, vague answers"
      3: "Good information gathered, mostly complete"
      5: "Comprehensive fact-finding, no gaps"

report:
  template: audit-log
  email_to:
    - investigations@example.com
  include_transcript: true
```

### Example 2: Technical Interviewer

Conducts structured technical interviews with dynamic candidate context.

```yaml
skill:
  id: tech-interviewer-v1
  name: Technical Interviewer
  version: 1.0.0

channels:
  - teams
  - phone

input_schema:
  - name: candidate_name
    type: string
    required: true
    description: "Candidate's full name"
  - name: position
    type: string
    required: true
    description: "Role they're interviewing for"
  - name: experience_level
    type: enum
    required: true
    values: [junior, mid, senior, staff]
    description: "Expected experience level"

agent:
  name: Rahul
  persona: >
    You are Rahul, a senior engineer conducting technical interviews.

    Candidate: {{candidate_name}}
    Position: {{position}}
    Level: {{experience_level}}

    Be thorough but respectful. Adapt question depth to {{experience_level}} level.
    Do not reveal scores or rubric criteria during the interview.
  max_duration_minutes: 45

sections:
  - id: background
    title: Background
    mode: guided
    questions:
      - id: bg-1
        text: "Hi {{candidate_name}}, thanks for joining. Can you start by telling me about your background and what draws you to this {{position}} role?"
        competency: communication
        max_follow_ups: 2

  - id: technical
    title: Technical Assessment
    mode: guided
    questions:
      - id: tech-1
        text: "Describe a complex technical problem you solved recently. Walk me through your approach."
        probes:
          - "What alternatives did you consider?"
          - "How did you validate your solution?"
          - "What would you do differently now?"
        competency: problem_solving
        max_follow_ups: 3

      - id: tech-2
        text: "How do you approach system design when requirements are still evolving?"
        probes:
          - "Can you give a real example from your experience?"
        competency: system_design
        max_follow_ups: 2

rubric:
  - competency: communication
    scores:
      1: "Unclear and disorganised, hard to follow"
      2: "Somewhat unclear, lacks structure"
      3: "Clear and structured, easy to follow"
      4: "Well articulated with good examples"
      5: "Exceptional clarity, concise and compelling"
  - competency: problem_solving
    scores:
      1: "No structured approach, guesses"
      2: "Some structure but incomplete"
      3: "Solid approach, covers main points"
      4: "Strong analysis with trade-off awareness"
      5: "Rigorous analysis, considers edge cases"
  - competency: system_design
    scores:
      1: "No design awareness"
      2: "Basic awareness, misses key concerns"
      3: "Sound design with reasonable trade-offs"
      4: "Strong design, good scalability thinking"
      5: "Outstanding — covers scale, failure, and evolution"

report:
  template: scorecard
  email_to:
    - hiring@example.com
  include_transcript: true
```

### Example 3: Sales Coach

Role-play sales coaching with dynamic scenarios.

```yaml
skill:
  id: sales-coach-v1
  name: Sales Coach
  version: 1.0.0

channels:
  - teams
  - phone

input_schema:
  - name: scenario
    type: enum
    required: true
    values: [discovery, demo, negotiation, objection_handling]
    description: "Type of sales scenario to practice"
  - name: prospect_type
    type: enum
    required: true
    values: [enterprise, smb, startup]
    description: "Prospect company size"
  - name: product_focus
    type: string
    required: false
    description: "Specific product or feature to focus on (optional)"

agent:
  name: Shubh
  persona: >
    You are Shubh, an experienced sales coach running a role-play session.

    Scenario: {{scenario}}
    Prospect: {{prospect_type}} company
    {% if product_focus %}Focus area: {{product_focus}}{% endif %}

    Run a realistic role-play — act as the prospect. After the call, give
    constructive feedback on what went well and what to improve.
  max_duration_minutes: 30

sections:
  - id: roleplay
    title: Role-play
    mode: intelligent
    objectives: |
      - Run a realistic {{scenario}} scenario with a {{prospect_type}} prospect
      - Challenge the rep with realistic objections appropriate to the scenario
      - Assess how well they build rapport, uncover needs, and handle pushback
      - Close the role-play naturally and provide brief in-call coaching

rubric:
  - competency: opening
    scores:
      1: "Weak opening, no rapport built"
      3: "Good rapport, clear purpose stated"
      5: "Exceptional hook, immediately engaging"
  - competency: adaptability
    scores:
      1: "Rigid, follows a script regardless of responses"
      3: "Adapts reasonably to the conversation"
      5: "Highly adaptive, picks up on every cue"

report:
  template: coaching-report
  email_to:
    - sales-manager@example.com
  include_transcript: true
```

### Example 4: Customer Onboarding (No Inputs)

Simple skill without input_schema for standardised flows.

```yaml
skill:
  id: onboarding-v1
  name: Customer Onboarding
  version: 1.0.0

channels:
  - phone

agent:
  name: Ritu
  persona: >
    You are Ritu, a friendly customer success specialist. Your goal is to
    welcome new customers, confirm their setup is complete, and answer
    any initial questions they have.
  max_duration_minutes: 15

sections:
  - id: onboarding
    title: Onboarding Call
    mode: intelligent
    objectives: |
      - Welcome the customer and confirm their account is set up
      - Walk through the key features they should try first
      - Address any immediate questions or concerns
      - Set expectations for next steps and support channels

rubric:
  - competency: satisfaction
    scores:
      1: "Customer confused or frustrated"
      3: "Customer comfortable, basic questions answered"
      5: "Customer confident and enthusiastic"

report:
  template: discovery-brief
  email_to:
    - success@example.com
  include_transcript: false
```

---

## Creating a Skill Pack

### Via Skill Builder UI (Recommended)

The Skill Builder provides a visual form-based interface for creating and editing skills without writing YAML:

1. Go to **Skill Packs** in the navigation
2. Click **+ Skill Builder** to create a new skill
3. Fill in the sections:
   - **Basic Information**: Skill ID, name, channels (Teams/Phone), agent name, persona
   - **Input Schema**: Define dynamic inputs that appear when launching a session
   - **Questions**: Add questions with probes and competencies (guided mode)
   - **Objectives**: Describe goals for intelligent mode sections
   - **Report Settings**: Choose template and email recipients
4. Click **Create Skill** to save

#### Editing Existing Skills

1. Go to **Skill Packs**
2. Find the skill you want to edit
3. Click **Edit Builder** to open in Skill Builder
4. Modify any fields
5. Click **Update Skill** to save changes

> **Note:** The Skill Builder parses YAML into form fields. Complex Jinja2 template logic (conditionals, loops) is best maintained via the YAML Editor.

### Via YAML Editor

For advanced users who prefer direct YAML editing:

1. Go to **Skill Packs**
2. Click **+ YAML Editor**
3. Paste your YAML content
4. Add a change summary
5. Click **Create**

To edit existing skills via YAML:
1. Find the skill
2. Click **Edit YAML**
3. Modify the YAML
4. Save

### Via API

```bash
curl -X POST http://localhost:8000/skill-packs \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "yaml_content": "skill:\n  id: my-skill-v1\n  name: My Skill\n  version: 1.0.0\n...",
    "change_summary": "Initial version"
  }'
```

### Activation

After creating, click **Activate** to make the skill available for sessions. Only one version of a skill can be active at a time. Activating a new version automatically deactivates the previous one.

---

## AI-Powered Skill Generation

Generate complete skills from a plain description using Sarvam AI:

1. Go to **Skill Packs**
2. Click **Skill Builder**
3. Click **Generate with AI**
4. Describe what you want, for example:
   > "Create a sales discovery call skill that asks about budget, authority, needs, and timeline. Should work for both phone calls and Teams meetings."
5. AI will generate:
   - Appropriate mode (`guided` or `intelligent`)
   - Channels (`teams` / `phone` / both)
   - Complete questions or objectives
   - Rubric competencies with 1–5 scoring descriptors
   - Agent persona
   - Report template
6. Review and modify as needed
7. Save the skill

---

## Skill Cloning

Clone an existing skill to create a variation:

1. Go to **Skill Packs**
2. Find the skill you want to clone
3. Click **Clone**
4. The cloned skill appears with:
   - New ID (appends `-clone`)
   - Name: "Original Name (Clone)"
   - Version: 1.0.0
   - Status: Inactive
5. Edit as needed and activate when ready

---

## Template Syntax

Use Jinja2-like syntax in `persona` and question `text` fields to inject dynamic values from `input_schema`:

```yaml
# Variable substitution
Hello {{candidate_name}}, I understand you're applying for {{position}}.

# Conditionals
{% if experience_level == 'senior' %}
Focus on architecture and leadership questions.
{% else %}
Focus on fundamentals and problem-solving approach.
{% endif %}

# Default values
Product focus: {{product_focus | default('general portfolio')}}
```

Variables are populated from `input_schema` values entered at session launch.

---

## Tips

1. **Start simple** — Create a basic skill first, then add `input_schema` once the core flow works
2. **Match agent name to voice** — Name the agent `Priya` if you plan to select the `priya` voice in the UI
3. **Use competencies** — Every question should map to a rubric competency for scoring
4. **Be specific in personas** — The more precise the persona instructions, the more consistent the agent behaviour
5. **Guided for structure, intelligent for flow** — Use `guided` for assessments where every question matters; use `intelligent` for open-ended conversations
6. **Validate YAML** — Use consistent 2-space indentation; YAML is whitespace-sensitive
7. **Test before activating** — Launch a test session before using in production

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| UI inputs not showing | Check `input_schema` indentation and that field `type` is a valid value |
| Template variables not substituted | Ensure variable names match `input_schema` `name` fields exactly |
| Agent ignores persona | Make instructions explicit; avoid vague guidance like "be professional" |
| Questions not being asked | Verify `sections` → `questions` structure and that `id` fields are unique |
| Scoring not working | Ensure `competency` values in questions match `competency` values in rubric |
| Session times out early | Increase `max_duration_minutes` or `max_duration_seconds` in the section |
| Agent switches language | Set language explicitly in the UI when launching; keep persona instructions in the target language |
