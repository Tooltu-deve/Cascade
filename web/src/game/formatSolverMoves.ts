import type { MoveStepJson, SolverMethod } from '../api/contract'
import { applyMoveSequence } from '../api/applyMoveSequence'
import type { Card, GameState } from './types'
import { SUITS, cloneState } from './freecell'

const RANK_LABEL: Record<number, string> = {
  1: 'A',
  11: 'J',
  12: 'Q',
  13: 'K',
}

const SUIT_SYM: Record<Card['suit'], string> = {
  spades: '♠',
  hearts: '♥',
  diamonds: '♦',
  clubs: '♣',
}

function cardShort(c: Card): string {
  const r = RANK_LABEL[c.rank] ?? String(c.rank)
  return `${r}${SUIT_SYM[c.suit]}`
}

function formatTarget(to: MoveStepJson['to']): string {
  if (to.kind === 'foundation') {
    const sym = SUIT_SYM[SUITS[to.suitIndex]]
    return `Foundation ${sym}`
  }
  if (to.kind === 'freecell') return `Ô trống ${to.slot + 1}`
  return `Cột ${to.col + 1}`
}

function formatSource(
  from: MoveStepJson['from'],
  state: GameState,
): { src: string; cards: string } {
  if (from.kind === 'freecell') {
    const c = state.freeCells[from.slot]
    return {
      src: `Ô trống ${from.slot + 1}`,
      cards: c ? cardShort(c) : '?',
    }
  }
  const col = state.cascades[from.col]
  const run = col.slice(from.fromIndex)
  if (run.length === 0) return { src: `Cột ${from.col + 1}`, cards: '?' }
  if (run.length === 1)
    return { src: `Cột ${from.col + 1}`, cards: cardShort(run[0]) }
  return {
    src: `Cột ${from.col + 1}`,
    cards: `${run.length} lá (${cardShort(run[0])} → ${cardShort(run[run.length - 1])})`,
  }
}

/** Một dòng mô tả bước (số thứ tự do `<ol>` hiển thị). */
function formatStepLine(state: GameState, move: MoveStepJson): string {
  const { src, cards } = formatSource(move.from, state)
  const dst = formatTarget(move.to)
  return `${cards} · ${src} → ${dst}`
}

export function buildSolverStepLines(
  start: GameState,
  moves: MoveStepJson[],
): string[] {
  const lines: string[] = []
  let s = cloneState(start)
  for (let i = 0; i < moves.length; i++) {
    lines.push(formatStepLine(s, moves[i]))
    s = applyMoveSequence(s, [moves[i]])
  }
  return lines
}

const METHOD_LABEL: Record<SolverMethod, string> = {
  bfs: 'BFS',
  dfs: 'DFS',
  ucs: 'UCS',
  astar: 'A*',
}

export function solverMethodLabel(method: SolverMethod): string {
  return METHOD_LABEL[method]
}
