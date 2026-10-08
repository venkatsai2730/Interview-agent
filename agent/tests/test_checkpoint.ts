/**
 * Unit tests for agent checkpointing module
 */
import { describe, it, expect, beforeEach, afterEach } from '@jest/globals'
import * as fs from 'fs/promises'
import * as path from 'path'
import * as os from 'os'

// Import the checkpoint functions
import {
  saveCheckpoint,
  loadCheckpoint,
  deleteCheckpoint,
  cleanupOldCheckpoints,
} from '../checkpoint.js'

// Mock SessionContext type for testing
interface TestSessionContext {
  session_id: string
  skill_pack: any
  state: any
  transcript_history: any[]
  lastVeroUtterance: string
}

describe('Checkpoint Module', () => {
  const testSessionId = 'test_session_123'
  const testCheckpointDir = path.join(os.tmpdir(), 'vero-test-checkpoints')

  // Set up test environment
  beforeEach(async () => {
    process.env.CHECKPOINT_DIR = testCheckpointDir
    try {
      await fs.mkdir(testCheckpointDir, { recursive: true })
    } catch (err) {
      // Directory might already exist
    }
  })

  // Clean up after tests
  afterEach(async () => {
    try {
      const files = await fs.readdir(testCheckpointDir)
      for (const file of files) {
        await fs.unlink(path.join(testCheckpointDir, file))
      }
      await fs.rmdir(testCheckpointDir)
    } catch (err) {
      // Directory might not exist or be empty
    }
    delete process.env.CHECKPOINT_DIR
  })

  describe('saveCheckpoint', () => {
    it('should save a checkpoint to disk', async () => {
      const ctx: TestSessionContext = {
        session_id: testSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [],
        lastVeroUtterance: 'Hello',
      }

      await saveCheckpoint(ctx as any)

      // Verify file was created
      const checkpointPath = path.join(testCheckpointDir, `${testSessionId}.json`)
      const data = await fs.readFile(checkpointPath, 'utf-8')
      const checkpoint = JSON.parse(data)

      expect(checkpoint.session_id).toBe(testSessionId)
      expect(checkpoint.context.skill_pack.skill.id).toBe('test-skill')
      expect(checkpoint.timestamp).toBeDefined()
    })

    it('should overwrite existing checkpoint', async () => {
      const ctx: TestSessionContext = {
        session_id: testSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [{ speaker: 'user', text: 'Hello' }],
        lastVeroUtterance: 'Hello',
      }

      // Save first checkpoint
      await saveCheckpoint(ctx as any)

      // Modify and save again
      ctx.lastVeroUtterance = 'Updated'
      await saveCheckpoint(ctx as any)

      // Verify it was updated
      const checkpointPath = path.join(testCheckpointDir, `${testSessionId}.json`)
      const data = await fs.readFile(checkpointPath, 'utf-8')
      const checkpoint = JSON.parse(data)

      expect(checkpoint.context.lastVeroUtterance).toBe('Updated')
    })
  })

  describe('loadCheckpoint', () => {
    it('should load a saved checkpoint', async () => {
      const ctx: TestSessionContext = {
        session_id: testSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [{ speaker: 'user', text: 'Hello' }],
        lastVeroUtterance: 'Hello',
      }

      await saveCheckpoint(ctx as any)

      const loaded = await loadCheckpoint(testSessionId)

      expect(loaded).not.toBeNull()
      expect(loaded!.session_id).toBe(testSessionId)
      expect(loaded!.lastVeroUtterance).toBe('Hello')
      expect(loaded!.transcript_history).toHaveLength(1)
    })

    it('should return null for non-existent checkpoint', async () => {
      const loaded = await loadCheckpoint('non_existent_session')
      expect(loaded).toBeNull()
    })

    it('should return null for expired checkpoint', async () => {
      const ctx: TestSessionContext = {
        session_id: testSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [],
        lastVeroUtterance: 'Hello',
      }

      await saveCheckpoint(ctx as any)

      // Modify the checkpoint to be 25 hours old
      const checkpointPath = path.join(testCheckpointDir, `${testSessionId}.json`)
      const data = await fs.readFile(checkpointPath, 'utf-8')
      const checkpoint = JSON.parse(data)
      checkpoint.timestamp = Date.now() - (25 * 60 * 60 * 1000) // 25 hours ago
      await fs.writeFile(checkpointPath, JSON.stringify(checkpoint), 'utf-8')

      const loaded = await loadCheckpoint(testSessionId)
      expect(loaded).toBeNull()
    })

    it('should reject checkpoint with mismatched session_id', async () => {
      const ctx: TestSessionContext = {
        session_id: testSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [],
        lastVeroUtterance: 'Hello',
      }

      await saveCheckpoint(ctx as any)

      // Try to load with different session_id
      const loaded = await loadCheckpoint('different_session_id')
      expect(loaded).toBeNull()
    })
  })

  describe('deleteCheckpoint', () => {
    it('should delete an existing checkpoint', async () => {
      const ctx: TestSessionContext = {
        session_id: testSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [],
        lastVeroUtterance: 'Hello',
      }

      await saveCheckpoint(ctx as any)

      // Verify it exists
      let loaded = await loadCheckpoint(testSessionId)
      expect(loaded).not.toBeNull()

      // Delete it
      await deleteCheckpoint(testSessionId)

      // Verify it's gone
      loaded = await loadCheckpoint(testSessionId)
      expect(loaded).toBeNull()
    })

    it('should not throw for non-existent checkpoint', async () => {
      await expect(deleteCheckpoint('non_existent')).resolves.not.toThrow()
    })
  })

  describe('cleanupOldCheckpoints', () => {
    it('should remove old checkpoints', async () => {
      // Create a fresh checkpoint
      const freshCtx: TestSessionContext = {
        session_id: 'fresh_session',
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [],
        lastVeroUtterance: 'Hello',
      }
      await saveCheckpoint(freshCtx as any)

      // Create an old checkpoint by manipulating the file
      const oldCtx: TestSessionContext = {
        session_id: 'old_session',
        skill_pack: { skill: { id: 'test-skill' } },
        state: { currentQuestion: { id: 'q1' } },
        transcript_history: [],
        lastVeroUtterance: 'Old',
      }
      await saveCheckpoint(oldCtx as any)

      const oldCheckpointPath = path.join(testCheckpointDir, 'old_session.json')
      const data = await fs.readFile(oldCheckpointPath, 'utf-8')
      const checkpoint = JSON.parse(data)
      checkpoint.timestamp = Date.now() - (25 * 60 * 60 * 1000) // 25 hours ago
      await fs.writeFile(oldCheckpointPath, JSON.stringify(checkpoint), 'utf-8')

      // Run cleanup
      await cleanupOldCheckpoints(24 * 60 * 60 * 1000) // 24 hours

      // Verify old checkpoint is gone
      const oldExists = await loadCheckpoint('old_session')
      expect(oldExists).toBeNull()

      // Verify fresh checkpoint remains
      const freshExists = await loadCheckpoint('fresh_session')
      expect(freshExists).not.toBeNull()
    })
  })

  describe('Failover scenarios', () => {
    it('should recover session state after simulated crash', async () => {
      // Simulate a session in progress
      const ctx: TestSessionContext = {
        session_id: testSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: {
          currentQuestion: { id: 'q2', text: 'How are you?' },
          scores: [{ question_id: 'q1', score: 5 }],
        },
        transcript_history: [
          { speaker: 'vero', text: 'Hello' },
          { speaker: 'user', text: 'Hi there' },
        ],
        lastVeroUtterance: 'Hello',
      }

      // Save checkpoint (simulating periodic save)
      await saveCheckpoint(ctx as any)

      // Simulate crash - process restarts, new SessionContext would be created
      // But we can restore from checkpoint
      const restored = await loadCheckpoint(testSessionId)

      expect(restored).not.toBeNull()
      expect(restored!.session_id).toBe(testSessionId)
      expect(restored!.state.currentQuestion.id).toBe('q2')
      expect(restored!.transcript_history).toHaveLength(2)
      expect(restored!.state.scores).toHaveLength(1)
    })

    it('should handle checkpoint corruption gracefully', async () => {
      // Create a corrupted checkpoint file
      const checkpointPath = path.join(testCheckpointDir, `${testSessionId}.json`)
      await fs.writeFile(checkpointPath, 'not valid json', 'utf-8')

      // Should return null, not throw
      const loaded = await loadCheckpoint(testSessionId)
      expect(loaded).toBeNull()
    })
  })

  describe('Session ID sanitization', () => {
    it('should sanitize session IDs with special characters', async () => {
      const maliciousSessionId = '../../../etc/passwd'
      const ctx: TestSessionContext = {
        session_id: maliciousSessionId,
        skill_pack: { skill: { id: 'test-skill' } },
        state: {},
        transcript_history: [],
        lastVeroUtterance: '',
      }

      await saveCheckpoint(ctx as any)

      // The file should be created in the checkpoint dir, not escaping it
      const files = await fs.readdir(testCheckpointDir)
      const checkpointFile = files.find(f => f.includes('etc_passwd'))
      expect(checkpointFile).toBeDefined()
    })
  })
})
