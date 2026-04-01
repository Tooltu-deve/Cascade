import type { Card } from '../game/types'
import { isRed } from '../game/freecell'

const RANK_LABEL: Record<number, string> = {
  1: 'A',
  11: 'J',
  12: 'Q',
  13: 'K',
}

function rankLabel(rank: number): string {
  return RANK_LABEL[rank] ?? String(rank)
}

const SUIT_SYMBOL: Record<Card['suit'], string> = {
  spades: '♠',
  hearts: '♥',
  diamonds: '♦',
  clubs: '♣',
}

type Props = {
  card: Card
  faceUp?: boolean
  selected?: boolean
  className?: string
  cardId?: string
}

export function CardFace({
  card,
  faceUp = true,
  selected = false,
  className = '',
  cardId,
}: Props) {
  const red = isRed(card.suit)
  return (
    <div
      className={`card-face ${faceUp ? 'face-up' : 'face-down'} ${selected ? 'selected' : ''} ${className}`.trim()}
      data-suit={card.suit}
      data-card-id={cardId}
    >
      {faceUp ? (
        <>
          <span className={`card-corner top ${red ? 'red' : 'black'}`}>
            <span className="rank">{rankLabel(card.rank)}</span>
            <span className="suit">{SUIT_SYMBOL[card.suit]}</span>
          </span>
          <span className={`card-center ${red ? 'red' : 'black'}`}>
            {SUIT_SYMBOL[card.suit]}
          </span>
        </>
      ) : null}
    </div>
  )
}
