/**
 * Wire types — khớp shared/API.md (JSON camelCase).
 */
import type { GameState } from '../game/types'

export type Suit = 'spades' | 'hearts' | 'diamonds' | 'clubs'

export interface CardJson {
  suit: Suit
  rank: number
}

export interface GameStateJson {
  cascades: CardJson[][]
  freeCells: (CardJson | null)[]
  foundations: [CardJson[], CardJson[], CardJson[], CardJson[]]
}

export type SelectionJson =
  | { kind: 'cascade'; col: number; fromIndex: number }
  | { kind: 'freecell'; slot: number }

export type MoveTargetJson =
  | { kind: 'foundation'; suitIndex: number }
  | { kind: 'freecell'; slot: number }
  | { kind: 'cascade'; col: number }

export interface MoveStepJson {
  from: SelectionJson
  to: MoveTargetJson
}

export interface SearchMetricsJson {
  searchTimeMs: number
  peakMemoryBytes: number
  expandedNodes: number
  solutionLength: number
}

export interface SolveRequestJson {
  state: GameStateJson
}

export interface SolveResponseJson {
  ok: boolean
  moves?: MoveStepJson[]
  metrics?: SearchMetricsJson
  error?: string
}

export type SolverMethod = 'bfs' | 'dfs' | 'ucs' | 'astar'

/** GameState trong game đã khớp GameStateJson; không cần map khi gửi API */
export function gameStateToRequestBody(state: GameState): SolveRequestJson {
  return { state }
}

export function solvePath(method: SolverMethod): string {
  return `/solve/${method}`
}
