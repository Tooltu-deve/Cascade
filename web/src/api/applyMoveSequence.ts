import { applyMove, cloneState } from '../game/freecell'
import type { GameState, Selection } from '../game/types'
import type { MoveTarget } from '../game/freecell'
import type { MoveStepJson } from './contract'

/** Áp dụng lần lượt các bước từ API; throw nếu có bước không hợp lệ với luật client. */
export function applyMoveSequence(
  state: GameState,
  moves: MoveStepJson[],
): GameState {
  let s = cloneState(state)
  for (const step of moves) {
    const next = applyMove(
      s,
      step.from as Selection,
      step.to as MoveTarget,
    )
    if (!next) {
      throw new Error(`Illegal move at step: ${JSON.stringify(step)}`)
    }
    s = next
  }
  return s
}
