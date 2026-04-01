import type { GameState } from '../game/types'
import {
  gameStateToRequestBody,
  solvePath,
  type SearchMetricsJson,
  type SolveResponseJson,
  type MoveStepJson,
  type SolverMethod,
} from './contract'

const DEFAULT_BASE = 'http://localhost:8000'
const DEFAULT_TIMEOUT_MS = 120_000

function apiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL?.trim()
  if (!raw) return DEFAULT_BASE
  return raw.replace(/\/$/, '')
}

function extractErrorMessage(data: unknown, status: number): string {
  if (data && typeof data === 'object') {
    if ('detail' in data) {
      const d = (data as { detail: unknown }).detail
      if (typeof d === 'string') return d
      if (Array.isArray(d)) return d.map(String).join('; ')
    }
    if ('error' in data && typeof (data as { error: unknown }).error === 'string') {
      return (data as { error: string }).error
    }
  }
  return `HTTP ${status}`
}

/**
 * Gọi POST /solve/{method} với body { state }.
 * Timeout mặc định 120s. Khi backend chưa sẵn sàng sẽ throw (network / JSON error).
 */
export async function postSolve(
  method: SolverMethod,
  state: GameState,
): Promise<SolveResponseJson> {
  const url = `${apiBase()}${solvePath(method)}`
  const body = JSON.stringify(gameStateToRequestBody(state))

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      signal: controller.signal,
    })

    const text = await res.text()
    let data: unknown = null
    if (text) {
      try {
        data = JSON.parse(text) as unknown
      } catch {
        throw new Error(
          res.ok ? 'Invalid JSON' : `HTTP ${res.status}: ${text.slice(0, 200)}`,
        )
      }
    }

    if (!res.ok) {
      throw new Error(extractErrorMessage(data, res.status))
    }

    if (!data || typeof data !== 'object' || !('ok' in data)) {
      throw new Error('Invalid solver response')
    }

    return data as SolveResponseJson
  } catch (e) {
    const aborted =
      (e instanceof Error || e instanceof DOMException) && e.name === 'AbortError'
    if (aborted) throw new Error('Request timed out (120s)')
    throw e
  } finally {
    window.clearTimeout(timeoutId)
  }
}

export function getApiBaseUrl(): string {
  return apiBase()
}

type StreamHandlers = {
  onStart?: (method: SolverMethod) => void
  onMetrics?: (metrics: SearchMetricsJson) => void
  onMove?: (move: MoveStepJson) => void
  onError?: (error: string) => void
  onDone?: (ok: boolean) => void
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  const lines = block.split('\n')
  let event = 'message'
  let dataText = ''
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataText += line.slice(5).trim()
  }
  if (!dataText) return null
  try {
    return { event, data: JSON.parse(dataText) as unknown }
  } catch {
    return null
  }
}

/**
 * Stream solver events via SSE-like response from POST /solve/stream/{method}.
 * Backend emits events: start, metrics, move, error, done.
 */
export async function postSolveStream(
  method: SolverMethod,
  state: GameState,
  handlers: StreamHandlers,
): Promise<void> {
  const url = `${apiBase()}/solve/stream/${method}`
  const body = JSON.stringify(gameStateToRequestBody(state))
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      signal: controller.signal,
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `HTTP ${res.status}`)
    }
    if (!res.body) throw new Error('Stream body is empty')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary).trim()
        buffer = buffer.slice(boundary + 2)
        if (block) {
          const parsed = parseSseBlock(block)
          if (parsed) {
            const payload = parsed.data as Record<string, unknown>
            if (parsed.event === 'start') handlers.onStart?.(method)
            if (parsed.event === 'metrics')
              handlers.onMetrics?.(payload as unknown as SearchMetricsJson)
            if (parsed.event === 'move')
              handlers.onMove?.(payload as unknown as MoveStepJson)
            if (parsed.event === 'error')
              handlers.onError?.(String(payload.error ?? 'solver_error'))
            if (parsed.event === 'done') handlers.onDone?.(Boolean(payload.ok))
          }
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
  } catch (e) {
    const aborted =
      (e instanceof Error || e instanceof DOMException) && e.name === 'AbortError'
    if (aborted) throw new Error('Request timed out (120s)')
    throw e
  } finally {
    window.clearTimeout(timeoutId)
  }
}
