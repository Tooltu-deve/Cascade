import type { Card, GameState, Suit } from './types'
import { cloneState } from './freecell'

const SUIT_MAP: Record<string, Suit> = {
  s: 'spades',
  h: 'hearts',
  d: 'diamonds',
  c: 'clubs',
}

function parseCard(token: string): Card | null {
  const raw = token.trim().toLowerCase()
  if (!raw || raw === '_') return null
  const m = raw.match(/^([shdc])(\d+)$/)
  if (!m) return null
  const rank = Number(m[2])
  if (rank < 1 || rank > 13) return null
  const suit = SUIT_MAP[m[1]]
  if (!suit) return null
  return { suit, rank }
}

function parseCardRow(line: string): Card[] {
  const tokens = line
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
  const cards: Card[] = []
  for (const token of tokens) {
    const card = parseCard(token)
    if (card) cards.push(card)
  }
  return cards
}

function countCards(state: GameState): number {
  return (
    state.cascades.reduce((acc, col) => acc + col.length, 0) +
    state.freeCells.filter((c) => c !== null).length +
    state.foundations.reduce((acc, pile) => acc + pile.length, 0)
  )
}

/**
 * Parse one block after "## Game N" — lines until next "## Game" or EOF.
 * File format: FIRST card in row = TOP (moveable); internal state is bottom → top.
 */
function parseGameBlock(block: string): GameState | null {
  const lines = block.split(/\r?\n/)
  let mode: 'none' | 'cascades' | 'freecells' | 'foundations' = 'none'
  const cascades: Card[][] = []
  let freeCells: (Card | null)[] = [null, null, null, null]
  const foundations: [Card[], Card[], Card[], Card[]] = [[], [], [], []]
  let foundationLine = 0

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('##')) break
    if (!trimmed || trimmed.startsWith('#')) continue

    if (trimmed === 'cascades:') {
      mode = 'cascades'
      continue
    }
    if (trimmed === 'freecells:') {
      mode = 'freecells'
      continue
    }
    if (trimmed === 'foundations:') {
      mode = 'foundations'
      foundationLine = 0
      continue
    }

    if (mode === 'cascades') {
      const topToBottom = parseCardRow(trimmed)
      cascades.push([...topToBottom].reverse())
      continue
    }
    if (mode === 'freecells') {
      const values = trimmed.split(',').map((t) => t.trim())
      if (values.length !== 4) return null
      freeCells = values.map((v) => parseCard(v))
      continue
    }
    if (mode === 'foundations') {
      if (foundationLine >= 4) continue
      foundations[foundationLine] = parseCardRow(trimmed)
      foundationLine += 1
      continue
    }
  }

  while (cascades.length < 8) cascades.push([])
  if (cascades.length !== 8) return null
  if (freeCells.length !== 4) return null

  const state: GameState = { cascades, freeCells, foundations }
  if (countCards(state) !== 52) return null
  return state
}

/**
 * Lấy game đầu tiên trong file (sau "## Game …") parse được và đủ 52 lá.
 */
export function parseFirstGameFromGamesTxt(text: string): GameState | null {
  const blocks = text.split(/^##\s*Game\s+\d+/gm)
  for (let i = 1; i < blocks.length; i++) {
    const parsed = parseGameBlock(blocks[i])
    if (parsed) return cloneState(parsed)
  }
  return null
}

/**
 * Parse file đầy đủ: ưu tiên block `## Game …`, không có thì parse từ `cascades:`.
 */
export function parseGameStateFromText(text: string): GameState | null {
  const fromGame = parseFirstGameFromGamesTxt(text)
  if (fromGame) return fromGame
  const cascadesIdx = text.search(/^\s*cascades:\s*$/m)
  if (cascadesIdx >= 0) {
    const parsed = parseGameBlock(text.slice(cascadesIdx))
    if (parsed) return cloneState(parsed)
  }
  return null
}
