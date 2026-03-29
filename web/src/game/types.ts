export type Suit = 'spades' | 'hearts' | 'diamonds' | 'clubs'

export interface Card {
  suit: Suit
  rank: number
}

export interface GameState {
  cascades: Card[][]
  freeCells: (Card | null)[]
  foundations: [Card[], Card[], Card[], Card[]]
}

/** Where the player selected cards from */
export type Selection =
  | { kind: 'cascade'; col: number; fromIndex: number }
  | { kind: 'freecell'; slot: number }
