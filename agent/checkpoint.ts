// Session checkpointing - persist agent state to disk for crash recovery
import * as fs from 'fs/promises'
import * as path from 'path'
import { SessionContext } from './agent.js'

const CHECKPOINT_DIR = process.env.CHECKPOINT_DIR || './checkpoints'
const CHECKPOINT_INTERVAL_MS = 5000 // Save every 5 seconds

interface Checkpoint {
  session_id: string
  timestamp: number
  context: SessionContext
}

/**
 * Ensure checkpoint directory exists
 */
async function ensureCheckpointDir(): Promise<void> {
  try {
    await fs.mkdir(CHECKPOINT_DIR, { recursive: true })
  } catch (err) {
    console.error(`[checkpoint] Failed to create checkpoint directory: ${err}`)
  }
}

/**
 * Get checkpoint file path for a session
 */
function getCheckpointPath(session_id: string): string {
  // Sanitize session_id to prevent directory traversal
  const safeId = session_id.replace(/[^a-zA-Z0-9_-]/g, '_')
  return path.join(CHECKPOINT_DIR, `${safeId}.json`)
}

/**
 * Save session checkpoint to disk
 */
export async function saveCheckpoint(ctx: SessionContext): Promise<void> {
  await ensureCheckpointDir()

  const checkpoint: Checkpoint = {
    session_id: ctx.session_id,
    timestamp: Date.now(),
    context: ctx
  }

  const checkpointPath = getCheckpointPath(ctx.session_id)
  const tempPath = `${checkpointPath}.tmp`

  try {
    // Write to temp file first, then rename for atomicity
    await fs.writeFile(tempPath, JSON.stringify(checkpoint, null, 2), 'utf-8')
    await fs.rename(tempPath, checkpointPath)
    console.error(`[checkpoint] Saved checkpoint for session ${ctx.session_id}`)
  } catch (err) {
    console.error(`[checkpoint] Failed to save checkpoint: ${err}`)
    // Clean up temp file if it exists
    try {
      await fs.unlink(tempPath)
    } catch {
      // Ignore cleanup errors
    }
  }
}

/**
 * Load session checkpoint from disk
 */
export async function loadCheckpoint(session_id: string): Promise<SessionContext | null> {
  const checkpointPath = getCheckpointPath(session_id)

  try {
    const data = await fs.readFile(checkpointPath, 'utf-8')
    const checkpoint: Checkpoint = JSON.parse(data)

    // Validate checkpoint data
    if (checkpoint.session_id !== session_id) {
      console.error(`[checkpoint] Session ID mismatch in checkpoint`)
      return null
    }

    // Check if checkpoint is not too old (24 hours)
    const ageMs = Date.now() - checkpoint.timestamp
    const maxAgeMs = 24 * 60 * 60 * 1000
    if (ageMs > maxAgeMs) {
      console.error(`[checkpoint] Checkpoint for ${session_id} is too old (${Math.round(ageMs / 1000 / 60)} minutes)`)
      await deleteCheckpoint(session_id)
      return null
    }

    console.error(`[checkpoint] Loaded checkpoint for session ${session_id} (age: ${Math.round(ageMs / 1000)}s)`)
    return checkpoint.context
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== 'ENOENT') {
      console.error(`[checkpoint] Failed to load checkpoint: ${err}`)
    }
    return null
  }
}

/**
 * Delete session checkpoint
 */
export async function deleteCheckpoint(session_id: string): Promise<void> {
  const checkpointPath = getCheckpointPath(session_id)
  try {
    await fs.unlink(checkpointPath)
    console.error(`[checkpoint] Deleted checkpoint for session ${session_id}`)
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== 'ENOENT') {
      console.error(`[checkpoint] Failed to delete checkpoint: ${err}`)
    }
  }
}

/**
 * Clean up old checkpoints (older than maxAgeMs)
 */
export async function cleanupOldCheckpoints(maxAgeMs: number = 24 * 60 * 60 * 1000): Promise<void> {
  try {
    await ensureCheckpointDir()
    const files = await fs.readdir(CHECKPOINT_DIR)
    const now = Date.now()

    for (const file of files) {
      if (!file.endsWith('.json')) continue

      const filePath = path.join(CHECKPOINT_DIR, file)
      try {
        const data = await fs.readFile(filePath, 'utf-8')
        const checkpoint: Checkpoint = JSON.parse(data)

        if (now - checkpoint.timestamp > maxAgeMs) {
          await fs.unlink(filePath)
          console.error(`[checkpoint] Cleaned up old checkpoint for ${checkpoint.session_id}`)
        }
      } catch (err) {
        console.error(`[checkpoint] Failed to process checkpoint file ${file}: ${err}`)
      }
    }
  } catch (err) {
    console.error(`[checkpoint] Failed to cleanup checkpoints: ${err}`)
  }
}

// Auto-cleanup on module load (don't block)
cleanupOldCheckpoints().catch(() => {})
