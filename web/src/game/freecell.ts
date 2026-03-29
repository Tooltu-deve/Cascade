import type { Card, GameState, Selection } from './types'

export const SUITS: Card['suit'][] = [
  'spades',
  'hearts',
  'diamonds',
  'clubs',
]

export function isRed(suit: Card['suit']): boolean {
  return suit === 'hearts' || suit === 'diamonds'
}

export function oppositeColor(a: Card, b: Card): boolean {
  return isRed(a.suit) !== isRed(b.suit)
}

/** Bottom → top in one cascade: ranks decrease, colors alternate */
export function isValidTableauRun(cards: Card[]): boolean {
  if (cards.length <= 1) return true
  for (let i = 0; i < cards.length - 1; i++) {
    const lower = cards[i]
    const upper = cards[i + 1]
    if (lower.rank !== upper.rank + 1) return false
    if (!oppositeColor(lower, upper)) return false
  }
  return true
}

export function suitIndex(suit: Card['suit']): number {
  return SUITS.indexOf(suit)
}

export function createDeck(): Card[] {
  const deck: Card[] = []
  for (const suit of SUITS) {
    for (let rank = 1; rank <= 13; rank++) {
      deck.push({ suit, rank })
    }
  }
  return deck
}

function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5)
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function shuffleDeck(deck: Card[], seed?: number): Card[] {
  const arr = [...deck]
  const rnd = seed !== undefined ? mulberry32(seed) : () => Math.random()
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

/**
 * Deal: 52 cards into 8 columns left-to-right, top-to-bottom.
 * Columns 0–3 end with 7 cards; columns 4–7 with 6.
 */
export function dealInitialState(seed?: number): GameState {
  const deck = shuffleDeck(createDeck(), seed)
  const cascades: Card[][] = Array.from({ length: 8 }, () => [])
  for (let i = 0; i < 52; i++) {
    cascades[i % 8].push(deck[i])
  }
  return {
    cascades,
    freeCells: [null, null, null, null],
    foundations: [[], [], [], []],
  }
}

export function cloneState(s: GameState): GameState {
  return {
    cascades: s.cascades.map((c) => [...c]),
    freeCells: [...s.freeCells],
    foundations: [
      [...s.foundations[0]],
      [...s.foundations[1]],
      [...s.foundations[2]],
      [...s.foundations[3]],
    ],
  }
}

export function countEmptyFreeCells(state: GameState): number {
  return state.freeCells.filter((c) => c === null).length
}

export function countEmptyCascades(state: GameState): number {
  return state.cascades.filter((col) => col.length === 0).length
}

/**
 * Max length of a tableau run that can be moved at once (standard FreeCell).
 * m = emptyFreeCells + 2 * emptyColumns; max = 2^m - 1.
 * Single-card moves are always allowed when destination is legal.
 */
export function maxSequenceMovable(state: GameState): number {
  const f = countEmptyFreeCells(state)
  const e = countEmptyCascades(state)
  return 2 ** (f + 2 * e) - 1
}

export function canPlaceOnFoundation(card: Card, pile: Card[]): boolean {
  if (pile.length === 0) return card.rank === 1
  const top = pile[pile.length - 1]
  return top.suit === card.suit && card.rank === top.rank + 1
}

export function canPlaceOnTableau(runBottom: Card, targetColumn: Card[]): boolean {
  if (targetColumn.length === 0) return true
  const targetTop = targetColumn[targetColumn.length - 1]
  return (
    oppositeColor(runBottom, targetTop) && runBottom.rank === targetTop.rank - 1
  )
}

export function isWin(state: GameState): boolean {
  return state.foundations.every((p) => p.length === 13)
}

function getRunFromSelection(state: GameState, sel: Selection): Card[] | null {
  if (sel.kind === 'freecell') {
    const c = state.freeCells[sel.slot]
    return c ? [c] : null
  }
  const col = state.cascades[sel.col]
  if (sel.fromIndex < 0 || sel.fromIndex >= col.length) return null
  const run = col.slice(sel.fromIndex)
  return isValidTableauRun(run) ? run : null
}

export type MoveTarget =
  | { kind: 'foundation'; suitIndex: number }
  | { kind: 'freecell'; slot: number }
  | { kind: 'cascade'; col: number }

/** Try to apply move; returns new state or null if illegal */
export function applyMove(
  state: GameState,
  sel: Selection,
  target: MoveTarget,
): GameState | null {
  const run = getRunFromSelection(state, sel)
  if (!run || run.length === 0) return null

  const next = cloneState(state)

  const removeFromSource = () => {
    if (sel.kind === 'freecell') {
      if (run.length !== 1) return false
      if (state.freeCells[sel.slot] === null) return false
      next.freeCells[sel.slot] = null
      return true
    }
    const col = next.cascades[sel.col]
    const n = run.length
    if (col.length < n) return false
    col.splice(sel.fromIndex, n)
    return true
  }

  const topCard = run[run.length - 1]

  if (target.kind === 'foundation') {
    if (run.length !== 1) return null
    if (sel.kind === 'cascade' && sel.fromIndex !== state.cascades[sel.col].length - 1)
      return null
    const si = target.suitIndex
    const pile = next.foundations[si]
    if (!canPlaceOnFoundation(topCard, pile)) return null
    if (!removeFromSource()) return null
    next.foundations[si] = [...pile, topCard]
    return next
  }

  if (target.kind === 'freecell') {
    if (run.length !== 1) return null
    if (next.freeCells[target.slot] !== null) return null
    if (!removeFromSource()) return null
    next.freeCells[target.slot] = topCard
    return next
  }

  const destCol = next.cascades[target.col]
  const runBottom = run[0]

  if (!canPlaceOnTableau(runBottom, destCol)) return null

  if (sel.kind === 'cascade' && sel.col === target.col) return null

  if (run.length > 1 && run.length > maxSequenceMovable(state)) return null

  if (!removeFromSource()) return null
  next.cascades[target.col] = [...destCol, ...run]
  return next
}

/** Auto-pick foundation pile index for a card (same suit) */
export function foundationIndexForCard(card: Card): number {
  return suitIndex(card.suit)
}
