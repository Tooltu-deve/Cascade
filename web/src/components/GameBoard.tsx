import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import type { GameState, Selection } from '../game/types'
import {
  SUITS,
  applyMove,
  foundationIndexForCard,
  cloneState,
  dealInitialState,
  isValidTableauRun,
  isWin,
  type MoveTarget,
} from '../game/freecell'
import { postSolve } from '../api/solveClient'
import { applyMoveSequence } from '../api/applyMoveSequence'
import type { SearchMetricsJson, SolverMethod } from '../api/contract'
import { parseGameStateFromText } from '../game/parseGamesTxt'
import {
  buildSolverStepLines,
  solverMethodLabel,
} from '../game/formatSolverMoves'
import { resolveStateText } from '../game/stateFiles'
import { CardFace } from './CardFace'

const SOLVER_STEP_DELAY_MS = 180
const CARD_MOVE_ANIM_MS = 220

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  const digits = i === 0 ? 0 : 1
  return `${v.toFixed(digits)} ${units[i]}`
}

function randomSeed(): number {
  return Math.floor(Math.random() * 0x7fffffff)
}

function stateFromConfig(): GameState {
  const resolved = resolveStateText()
  if (resolved) {
    const parsed = parseGameStateFromText(resolved.text)
    if (parsed) return parsed
  }
  return dealInitialState(randomSeed())
}

export function GameBoard() {
  const boardRef = useRef<HTMLDivElement | null>(null)
  const [game, setGame] = useState<GameState>(() => stateFromConfig())
  const [initialDeal, setInitialDeal] = useState<GameState>(() =>
    cloneState(game),
  )
  const [undoStack, setUndoStack] = useState<GameState[]>([])
  const [draggingKey, setDraggingKey] = useState<string | null>(null)
  const [solvingMethod, setSolvingMethod] = useState<SolverMethod | null>(null)
  const [solverError, setSolverError] = useState<string | null>(null)
  const [solverPlan, setSolverPlan] = useState<{
    method: SolverMethod
    lines: string[]
  } | null>(null)
  const [solverModal, setSolverModal] = useState<{
    ok: boolean
    method: SolverMethod
    metrics: SearchMetricsJson | null
    error?: string | null
  } | null>(null)

  const won = useMemo(() => isWin(game), [game])
  const isSolving = solvingMethod !== null
  const isSolverModalOpen = solverModal !== null

  const setGameWithAnimation = useCallback(async (next: GameState) => {
    const root = boardRef.current
    if (!root) {
      setGame(next)
      return
    }

    const before = new Map<string, DOMRect>()
    root.querySelectorAll<HTMLElement>('.card-face[data-card-id]').forEach((el) => {
      const id = el.dataset.cardId
      if (id) before.set(id, el.getBoundingClientRect())
    })

    setGame(next)
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

    root.querySelectorAll<HTMLElement>('.card-face[data-card-id]').forEach((el) => {
      const id = el.dataset.cardId
      if (!id) return
      const prev = before.get(id)
      if (!prev) return
      const now = el.getBoundingClientRect()
      const dx = prev.left - now.left
      const dy = prev.top - now.top
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return
      el.animate(
        [
          { transform: `translate(${dx}px, ${dy}px)` },
          { transform: 'translate(0, 0)' },
        ],
        {
          duration: CARD_MOVE_ANIM_MS,
          easing: 'cubic-bezier(0.2, 0.7, 0.2, 1)',
        },
      )
    })

    await new Promise<void>((resolve) =>
      window.setTimeout(resolve, CARD_MOVE_ANIM_MS),
    )
  }, [])

  const startNewGame = useCallback(() => {
    const next = stateFromConfig()
    void setGameWithAnimation(next)
    setInitialDeal(cloneState(next))
    setUndoStack([])
    setSolverError(null)
    setSolverPlan(null)
    setSolverModal(null)
  }, [setGameWithAnimation])

  const restart = useCallback(() => {
    void setGameWithAnimation(cloneState(initialDeal))
    setUndoStack([])
    setSolverError(null)
    setSolverPlan(null)
    setSolverModal(null)
  }, [initialDeal, setGameWithAnimation])

  const undo = useCallback(() => {
    setUndoStack((stack) => {
      if (stack.length === 0) return stack
      const prevState = stack[stack.length - 1]
      void setGameWithAnimation(prevState)
      return stack.slice(0, -1)
    })
  }, [setGameWithAnimation])

  const pushUndo = useCallback((prev: GameState) => {
    setUndoStack((s) => [...s, cloneState(prev)])
  }, [])

  const tryApply = useCallback(
    (sel: Selection, target: MoveTarget) => {
      const prev = cloneState(game)
      const next = applyMove(game, sel, target)
      if (next) {
        pushUndo(prev)
        void setGameWithAnimation(next)
        return true
      }
      return false
    },
    [game, pushUndo, setGameWithAnimation],
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

  const autoMoveToFoundation = useCallback(
    (sel: Selection) => {
      const card =
        sel.kind === 'freecell'
          ? game.freeCells[sel.slot]
          : game.cascades[sel.col][game.cascades[sel.col].length - 1] ?? null
      if (!card) return
      void tryApply(sel, {
        kind: 'foundation',
        suitIndex: foundationIndexForCard(card),
      })
    },
    [game, tryApply],
  )

  const runSolver = useCallback(
    async (method: SolverMethod) => {
      if (isSolving) return
      setSolvingMethod(method)
      setSolverError(null)
      setSolverPlan(null)
      setSolverModal(null)
      const snapshot = cloneState(game)

      try {
        const result = await postSolve(method, snapshot)

        if (!result.ok) {
          const metrics = result.metrics ?? null
          const error = result.error ?? 'Solver failed'
          setSolverError(error)
          setSolverPlan(null)
          setSolverModal({
            ok: false,
            method,
            metrics,
            error,
          })
          return
        }

        const okMetrics = result.metrics ?? null
        const moves = result.moves ?? []
        setSolverPlan({
          method,
          lines: buildSolverStepLines(snapshot, moves),
        })
        // Validate full sequence first, then animate applying each step.
        applyMoveSequence(snapshot, moves)
        pushUndo(snapshot)
        let current = snapshot
        for (const move of moves) {
          const next = applyMoveSequence(current, [move])
          current = next
          await setGameWithAnimation(next)
          await new Promise((resolve) =>
            window.setTimeout(resolve, SOLVER_STEP_DELAY_MS),
          )
        }
        setSolverModal({
          ok: true,
          method,
          metrics: okMetrics,
        })
      } catch (e) {
        const error = e instanceof Error ? e.message : 'Cannot reach solver API'
        setSolverError(error)
        setSolverModal({
          ok: false,
          method,
          metrics: null,
          error,
        })
      } finally {
        setSolvingMethod(null)
      }
    },
    [game, isSolving, pushUndo, setGameWithAnimation],
  )

  useEffect(() => {
    if (!solverModal) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSolverModal(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [solverModal])

  const canDragCascade = (col: number, fromIndex: number) => {
    const run = game.cascades[col].slice(fromIndex)
    return run.length > 0 && isValidTableauRun(run)
  }

  return (
    <div
      ref={boardRef}
      className={`game-board${draggingKey ? ' is-dragging' : ''}`}
    >
      <header className="game-toolbar">
        <div className="brand">
          <h1>FreeCell</h1>
          <p className="tagline">Local play + Python solver API</p>
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
          <button
            type="button"
            className="btn ghost"
            onClick={() => void runSolver('bfs')}
            disabled={isSolving}
          >
            BFS
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => void runSolver('dfs')}
            disabled={isSolving}
          >
            DFS
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => void runSolver('ucs')}
            disabled={isSolving}
          >
            UCS
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => void runSolver('astar')}
            disabled={isSolving}
          >
            A*
          </button>
        </div>
      </header>

      {isSolving ? (
        <div className="solver-status" role="status">
          Solving with <strong>{solvingMethod?.toUpperCase()}</strong>...
        </div>
      ) : null}

      {solverError && !isSolverModalOpen ? (
        <div className="solver-error" role="alert">
          Solver error: {solverError}
        </div>
      ) : null}

      {won && !isSolverModalOpen ? (
        <div className="win-banner" role="status">
          You win — all suits built to King.
        </div>
      ) : null}

      <div className="top-row">
        <div className="freecells">
          {game.freeCells.map((card, i) =>
            card ? (
              <div
                key={`fc-${i}`}
                className={`cell slot filled${draggingKey === `fc-${i}` ? ' drag-source' : ''}`}
                draggable
                onClick={() => autoMoveToFoundation({ kind: 'freecell', slot: i })}
                onDragStart={(e) =>
                  onDragStart(e, { kind: 'freecell', slot: i }, `fc-${i}`)
                }
                onDragEnd={onDragEnd}
                aria-label={`Free cell ${i + 1}, drag to move`}
              >
                <CardFace card={card} cardId={`${card.suit}-${card.rank}`} />
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
                  <CardFace card={top} cardId={`${top.suit}-${top.rank}`} />
                ) : null}
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
                const isTop = idx === column.length - 1
                return (
                  <div
                    key={`${col}-${idx}-${card.suit}-${card.rank}`}
                    className={`cascade-card${draggingKey === dragKey ? ' drag-source' : ''}`}
                    style={{ zIndex: idx + 1 }}
                    draggable={canDrag}
                    onClick={() => {
                      if (!isTop) return
                      autoMoveToFoundation({ kind: 'cascade', col, fromIndex: idx })
                    }}
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
                    <CardFace card={card} cardId={`${card.suit}-${card.rank}`} />
                  </div>
                )
              })
            )}
          </div>
        ))}
      </div>

      {solverPlan ? (
        <section
          className="solver-steps-panel"
          aria-label="Các bước thuật toán trả về"
        >
          <h2 className="solver-steps-title">
            Lời giải ({solverMethodLabel(solverPlan.method)})
            {solverPlan.lines.length > 0 ? (
              <span className="solver-steps-count">
                {' '}
                · {solverPlan.lines.length} bước
              </span>
            ) : null}
          </h2>
          <div className="solver-steps-body">
            {solverPlan.lines.length > 0 ? (
              <ol className="solver-steps-list">
                {solverPlan.lines.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ol>
            ) : (
              <p className="solver-steps-empty">
                Trạng thái đã thắng — không cần nước đi.
              </p>
            )}
          </div>
        </section>
      ) : null}

      {solverModal ? (
        <div
          className="solver-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Solver results"
          onClick={() => setSolverModal(null)}
        >
          <div className="solver-modal" onClick={(e) => e.stopPropagation()}>
            <div className="solver-modal-header">
              <h2 className="solver-modal-title">
                {solverModal.ok ? 'Win!' : 'Solver result'}
              </h2>
              <button
                type="button"
                className="solver-modal-close"
                aria-label="Close"
                onClick={() => setSolverModal(null)}
              >
                ×
              </button>
            </div>

            <p className="solver-modal-message">
              {solverModal.ok
                ? 'Solver đã tìm được lời giải. Chúc mừng!'
                : solverModal.error ?? 'Solver không tìm được lời giải.'}
            </p>

            <div className="solver-modal-grid" role="group" aria-label="Metrics">
              <div className="solver-modal-stat">
                <span className="solver-modal-stat-label">Time</span>
                <span className="solver-modal-stat-value">
                  {solverModal.metrics
                    ? `${Math.round(solverModal.metrics.searchTimeMs)} ms`
                    : '—'}
                </span>
              </div>
              <div className="solver-modal-stat">
                <span className="solver-modal-stat-label">Memory</span>
                <span className="solver-modal-stat-value">
                  {solverModal.metrics
                    ? `${formatBytes(solverModal.metrics.peakMemoryBytes)}`
                    : '—'}
                </span>
              </div>
              <div className="solver-modal-stat">
                <span className="solver-modal-stat-label">Expanded Nodes</span>
                <span className="solver-modal-stat-value">
                  {solverModal.metrics ? solverModal.metrics.expandedNodes : '—'}
                </span>
              </div>
              <div className="solver-modal-stat">
                <span className="solver-modal-stat-label">Search Length</span>
                <span className="solver-modal-stat-value">
                  {solverModal.metrics ? solverModal.metrics.solutionLength : '—'}
                </span>
              </div>
            </div>

            <div className="solver-modal-actions">
              <button
                type="button"
                className="btn"
                onClick={() => setSolverModal(null)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      ) : null}

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
