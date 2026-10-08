// SkillPackState — tracks question index, follow-up counts, and scores per session

import type { SkillPack, TurnOutput } from './agent.js'

// Re-export the Question type shape for internal use
type Question = NonNullable<SkillPack['sections'][number]['questions']>[number]

export interface QuestionScore {
  question_id: string
  competency: string
  score: number
  rationale: string
}

export class SkillPackState {
  private skillPack: SkillPack
  private currentQuestionIndex: number = 0
  private followUpCounts: Map<string, number> = new Map()
  private scores: QuestionScore[] = []
  private done: boolean = false

  constructor(skillPack: SkillPack) {
    this.skillPack = skillPack
  }

  /** Flat ordered list of all questions across all sections.
   * Intelligent-mode sections have no questions array — those are skipped. */
  get allQuestions(): Question[] {
    return this.skillPack.sections.flatMap((s: SkillPack['sections'][number]) => s.questions ?? [])
  }

  get currentQuestion() {
    const questions = this.allQuestions
    if (this.currentQuestionIndex >= questions.length) return null
    return questions[this.currentQuestionIndex]
  }

  get isComplete(): boolean {
    if (this.done) return true
    const questions = this.allQuestions
    // Intelligent-only mode (no questions) — only close via explicit LLM decision
    if (questions.length === 0) return false
    return this.currentQuestionIndex >= questions.length
  }

  getFollowUpCount(questionId: string): number {
    return this.followUpCounts.get(questionId) ?? 0
  }

  incrementFollowUp(questionId: string): void {
    const count = this.getFollowUpCount(questionId)
    this.followUpCounts.set(questionId, count + 1)
  }

  hasReachedFollowUpLimit(questionId: string): boolean {
    const question = this.allQuestions.find((q: Question) => q.id === questionId)
    if (!question) return false
    const maxFollowUps = question.max_follow_ups ?? 2
    return this.getFollowUpCount(questionId) >= maxFollowUps
  }

  advance(): void {
    this.currentQuestionIndex++
  }

  close(): void {
    this.done = true
  }

  recordScore(score: QuestionScore): void {
    // Replace existing score for same question_id if present
    const idx = this.scores.findIndex(s => s.question_id === score.question_id)
    if (idx >= 0) {
      this.scores[idx] = score
    } else {
      this.scores.push(score)
    }
  }

  getScores(): QuestionScore[] {
    return [...this.scores]
  }

  private turnCount: number = 0

  getTurnCount(): number {
    return this.turnCount
  }

  /**
   * Apply a TurnOutput to the state machine.
   * Handles follow-up limit enforcement, score recording, and question advancement.
   * Returns the (possibly mutated) output.
   */
  applyTurnOutput(output: TurnOutput): TurnOutput {
    this.turnCount++

    if (output.action === 'follow_up' || output.action === 'clarify') {
      this.incrementFollowUp(output.question_id)
      if (this.hasReachedFollowUpLimit(output.question_id)) {
        output = { ...output, action: 'advance' }
      }
    }

    if (output.action === 'advance') {
      if (output.score !== null) {
        this.recordScore({
          question_id: output.question_id,
          competency: output.competency,
          score: output.score,
          rationale: output.score_rationale ?? ''
        })
      }
      this.advance()
    } else if (output.action === 'close') {
      if (output.score !== null) {
        this.recordScore({
          question_id: output.question_id,
          competency: output.competency,
          score: output.score,
          rationale: output.score_rationale ?? ''
        })
      }
      this.close()
    }

    return output
  }

  getQuestionsNotReached(): string[] {
    const questions = this.allQuestions
    const reached = new Set(this.scores.map(s => s.question_id))
    return questions
      .slice(this.currentQuestionIndex)
      .filter((q: Question) => !reached.has(q.id))
      .map((q: Question) => q.id)
  }
}
