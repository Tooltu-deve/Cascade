import { useCallback, useMemo, useState } from 'react'
import type { DragEvent } from 'react'
import type { GameState, Selection } from '../game/types'
import {
  SUITS,
  applyMove,
  cloneState,
  dealInitialState,
  isValidTableauRun,
  isWin,
  maxSequenceMovable,
  type MoveTarget,
} from '../game/freecell'
import { CardFace } from './CardFace'

function randomSeed(): number {
  return Math.floor(Math.random() * 0x7fffffff)
}

export function GameBoard() {
  const [seed, setSeed] = useState(() => randomSeed())
  const [game, setGame] = useState<GameState>(() => dealInitialState(seed))
  const [initialDeal, setInitialDeal] = useState<GameState>(() =>
    cloneState(dealInitialState(seed)),
  )
  const [undoStack, setUndoStack] = useState<GameState[]>([])
  const [draggingKey, setDraggingKey] = useState<string | null>(null)

  const won = useMemo(() => isWin(game), [game])

  const startNewGame = useCallback(() => {
    const s = randomSeed()
    setSeed(s)
    const next = dealInitialState(s)
    setGame(next)
    setInitialDeal(cloneState(next))
    setUndoStack([])
  }, [])

  const restart = useCallback(() => {
    setGame(cloneState(initialDeal))
    setUndoStack([])
  }, [initialDeal])

  const undo = useCallback(() => {
    setUndoStack((stack) => {
      if (stack.length === 0) return stack
      const prevState = stack[stack.length - 1]
      setGame(prevState)
      return stack.slice(0, -1)
    })
  }, [])

  const pushUndo = useCallback((prev: GameState) => {
    setUndoStack((s) => [...s, cloneState(prev)])
  }, [])

  const tryApply = useCallback(
    (sel: Selection, target: MoveTarget) => {
      const prev = cloneState(game)
      const next = applyMove(game, sel, target)
      if (next) {
        pushUndo(prev)
        setGame(next)
        return true
      }
      return false
    },
    [game, pushUndo],
  )

  const parseSelection = useCallback((e: DragEvent) => {
    const raw =
      e.dataTransfer.getData('application/json') ||
      e.dataTransfer.getData('text/plain')
    if (!raw) return null
    try {
      return JSON.parse(raw) as Selection
    } catch {
      return null
    }
  }, [])

  const onDragStart = useCallback(
    (e: DragEvent, sel: Selection, key: string) => {
      const payload = JSON.stringify(sel)
      e.dataTransfer.setData('application/json', payload)
      e.dataTransfer.setData('text/plain', payload)
      e.dataTransfer.effectAllowed = 'move'
      setDraggingKey(key)
    },
    [],
  )

  const onDragEnd = useCallback(() => {
    setDraggingKey(null)
  }, [])

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (e: DragEvent, target: MoveTarget) => {
      e.preventDefault()
      e.stopPropagation()
      const sel = parseSelection(e)
      if (!sel) return
      tryApply(sel, target)
    },
    [parseSelection, tryApply],
  )

  const canDragCascade = (col: number, fromIndex: number) => {
    const run = game.cascades[col].slice(fromIndex)
    return run.length > 0 && isValidTableauRun(run)
  }

  const maxMove = maxSequenceMovable(game)

  return (
    <div className={`game-board${draggingKey ? ' is-dragging' : ''}`}>
      <header className="game-toolbar">
        <div className="brand">
          <h1>FreeCell</h1>
          <p className="tagline">Local play · Solvers coming soon</p>
        </div>
        <div className="toolbar-actions">
          <button type="button" className="btn primary" onClick={startNewGame}>
            New game
          </button>
          <button type="button" className="btn" onClick={restart}>
            Restart
          </button>
          <button
            type="button"
            className="btn"
            onClick={undo}
            disabled={undoStack.length === 0}
          >
            Undo
          </button>
        </div>
        <div className="solver-placeholder" aria-label="Solver actions">
          <span className="solver-label">Solvers</span>
          <button type="button" className="btn ghost" disabled title="Python API later">
            BFS
          </button>
          <button type="button" className="btn ghost" disabled title="Python API later">
            DFS
          </button>
          <button type="button" className="btn ghost" disabled title="Python API later">
            UCS
          </button>
          <button type="button" className="btn ghost" disabled title="Python API later">
            A*
          </button>
        </div>
      </header>

      {won ? (
        <div className="win-banner" role="status">
          You win — all suits built to King.
        </div>
      ) : null}

      <div className="hud">
        <span>
          Max run move: <strong>{maxMove}</strong>
        </span>
        <span className="muted">Seed: {seed}</span>
      </div>

      <div className="top-row">
        <div className="freecells">
          {game.freeCells.map((card, i) =>
            card ? (
              <div
                key={`fc-${i}`}
                className={`cell slot filled${draggingKey === `fc-${i}` ? ' drag-source' : ''}`}
                draggable
                onDragStart={(e) =>
                  onDragStart(e, { kind: 'freecell', slot: i }, `fc-${i}`)
                }
                onDragEnd={onDragEnd}
                aria-label={`Free cell ${i + 1}, drag to move`}
              >
                <CardFace card={card} />
              </div>
            ) : (
              <div
                key={`fc-${i}`}
                className="cell slot empty"
                onDragOver={onDragOver}
                onDrop={(e) => onDrop(e, { kind: 'freecell', slot: i })}
                aria-label={`Empty free cell ${i + 1}`}
              >
                <span className="placeholder">Free</span>
              </div>
            ),
          )}
        </div>
        <div className="foundations">
          {SUITS.map((suit, suitIndex) => {
            const pile = game.foundations[suitIndex]
            const top = pile.length > 0 ? pile[pile.length - 1] : null
            return (
              <div
                key={suit}
                className={`cell foundation ${top ? 'filled' : 'empty'}`}
                onDragOver={onDragOver}
                onDrop={(e) => onDrop(e, { kind: 'foundation', suitIndex })}
                aria-label={`Foundation ${suit}, drop matching suit`}
              >
                {top ? (
                  <CardFace card={top} />
                ) : (
                  <span className={`foundation-suit hint ${suit}`}>
                    {suit === 'spades'
                      ? '♠'
                      : suit === 'hearts'
                        ? '♥'
                        : suit === 'diamonds'
                          ? '♦'
                          : '♣'}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="cascades">
        {game.cascades.map((column, col) => (
          <div key={`col-${col}`} className="cascade-column">
            {column.length === 0 ? (
              <div
                className="cell cascade-empty"
                onDragOver={onDragOver}
                onDrop={(e) => onDrop(e, { kind: 'cascade', col })}
              >
                <span className="placeholder">Empty</span>
              </div>
            ) : (
              column.map((card, idx) => {
                const dragKey = `c-${col}-${idx}`
                const canDrag = canDragCascade(col, idx)
                return (
                  <div
                    key={`${col}-${idx}-${card.suit}-${card.rank}`}
                    className={`cascade-card${draggingKey === dragKey ? ' drag-source' : ''}`}
                    style={{ zIndex: idx + 1 }}
                    draggable={canDrag}
                    onDragStart={(e) => {
                      if (!canDrag) {
                        e.preventDefault()
                        return
                      }
                      onDragStart(
                        e,
                        { kind: 'cascade', col, fromIndex: idx },
                        dragKey,
                      )
                    }}
                    onDragEnd={onDragEnd}
                    onDragOver={onDragOver}
                    onDrop={(e) => onDrop(e, { kind: 'cascade', col })}
                    aria-label={`Column ${col + 1}, drag from rank ${card.rank}`}
                  >
                    <CardFace card={card} />
                  </div>
                )
              })
            )}
          </div>
        ))}
      </div>

      <footer className="help">
        <p>
          Kéo một lá hoặc một chuỗi hợp lệ, thả lên cột cascade, ô trống hoặc
          foundation đúng chất. Chỉ lá trên cùng lên foundation. Có thể hoàn
          tác không giới hạn.
        </p>
      </footer>
    </div>
  )
}
