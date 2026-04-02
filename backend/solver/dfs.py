"""
IDA* (Iterative Deepening A*) solver for FreeCell.
Uses f(n) = g(n) + h(n) thresholds for iterative deepening.
Admissible like A*, memory-efficient like DFS.
"""

from __future__ import annotations

import gc
import time
from dataclasses import dataclass
from typing import Optional

from game import State
from models import MoveStep, SearchMetrics


@dataclass
class DFSResult:
    ok: bool
    moves: list[MoveStep]
    metrics: SearchMetrics
    error: Optional[str] = None


def _estimate_heuristic(state: State) -> float:
    """Critical Path heuristic. Lower = closer to goal."""
    cards_in_foundation = sum(len(f) for f in state.foundations)
    cards_left = 52 - cards_in_foundation
    h = cards_left * 0.5

    for cascade in state.cascades:
        for i in range(len(cascade) - 1):
            h += (len(cascade) - i - 1) * 0.3

    free_empty = sum(1 for fc in state.free_cells if fc is None)
    if free_empty < 1 and cards_left > 0:
        h += 3.0
    elif free_empty < 2 and cards_left > 5:
        h += 1.0

    return h


def _move_cost(move: MoveStep) -> float:
    """Cost of executing a move."""
    target = move.to_target.kind
    if target == "foundation":
        return 0.5
    elif target == "freecell":
        return 1.8
    return 1.0


def solve(state: State, time_limit: float = 120.0) -> DFSResult:
    """IDA* search from the given state."""
    start_time = time.perf_counter()

    if state.is_won():
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        gc.collect()
        return DFSResult(
            ok=True, moves=[],
            metrics=SearchMetrics(
                search_time_ms=round(elapsed_ms, 2),
                peak_memory_bytes=_get_memory_bytes(),
                expanded_nodes=0, solution_length=0,
            ),
        )

    # Initial threshold = h(start)
    threshold = _estimate_heuristic(state)
    total_expanded = 0
    max_threshold = 500.0  # safety limit

    while threshold <= max_threshold:
        current_time = time.perf_counter()
        if current_time >= (start_time + time_limit):
            elapsed_ms = (current_time - start_time) * 1000
            gc.collect()
            return DFSResult(
                ok=False, moves=[], error="timeout",
                metrics=SearchMetrics(
                    search_time_ms=round(elapsed_ms, 2),
                    peak_memory_bytes=_get_memory_bytes(),
                    expanded_nodes=total_expanded, solution_length=0,
                ),
            )

        visited: set[str] = {state.state_key()}
        result = _ida_search(
            state, g=0.0, threshold=threshold,
            path=[], visited=visited,
            start_time=start_time, time_limit=time_limit,
            expanded=0, last_move=None,
        )
        total_expanded += result.expanded

        if result.solution is not None:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            gc.collect()
            return DFSResult(
                ok=True, moves=result.solution,
                metrics=SearchMetrics(
                    search_time_ms=round(elapsed_ms, 2),
                    peak_memory_bytes=_get_memory_bytes(),
                    expanded_nodes=total_expanded,
                    solution_length=len(result.solution),
                ),
            )

        # No solution at this threshold; next threshold = min f that exceeded
        if result.next_threshold is None or result.next_threshold > max_threshold:
            break
        threshold = result.next_threshold

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    gc.collect()
    return DFSResult(
        ok=False, moves=[], error="no_solution",
        metrics=SearchMetrics(
            search_time_ms=round(elapsed_ms, 2),
            peak_memory_bytes=_get_memory_bytes(),
            expanded_nodes=total_expanded, solution_length=0,
        ),
    )


@dataclass
class IdaResult:
    solution: Optional[list[MoveStep]]
    expanded: int
    next_threshold: Optional[float]  # minimum f that exceeded threshold


def _ida_search(
    state: State, g: float, threshold: float,
    path: list[MoveStep], visited: set[str],
    start_time: float, time_limit: float,
    expanded: int, last_move: Optional[MoveStep],
) -> IdaResult:
    """Recursive IDA* search."""

    if time.perf_counter() - start_time >= time_limit:
        return IdaResult(solution=None, expanded=expanded, next_threshold=None)

    if state.is_won():
        return IdaResult(solution=path, expanded=expanded, next_threshold=None)

    h = _estimate_heuristic(state)
    f = g + h

    # Prune if f exceeds threshold
    if f > threshold:
        return IdaResult(solution=None, expanded=expanded, next_threshold=f)

    min_next_threshold = None

    # Get and sort successors
    successors = state.get_successors(prune=True)

    def sort_key(item):
        move, next_state = item
        # Sort by f of child (most promising first)
        child_g = g + _move_cost(move)
        child_h = _estimate_heuristic(next_state)
        child_f = child_g + child_h
        return child_f

    successors.sort(key=sort_key)

    for move_step, next_state in successors:
        key = next_state.state_key()

        if key in visited:
            continue

        # Skip undoing last move
        if last_move is not None and _is_undoing(last_move, move_step):
            continue

        visited.add(key)
        child_g = g + _move_cost(move_step)
        result = _ida_search(
            next_state, child_g, threshold,
            path + [move_step], visited,
            start_time, time_limit,
            expanded + 1, move_step,
        )
        visited.discard(key)

        if result.solution is not None:
            return result

        expanded = result.expanded
        if result.next_threshold is not None:
            if min_next_threshold is None or result.next_threshold < min_next_threshold:
                min_next_threshold = result.next_threshold

    return IdaResult(solution=None, expanded=expanded, next_threshold=min_next_threshold)


def _is_undoing(last_move: MoveStep, current_move: MoveStep) -> bool:
    """Returns True if current_move immediately undoes last_move."""
    # Freecell -> Cascade, then Cascade -> Freecell same slot
    if (
        last_move.from_sel.kind == "freecell"
        and last_move.to_target.kind == "cascade"
        and current_move.from_sel.kind == "cascade"
        and current_move.to_target.kind == "freecell"
    ):
        if (
            last_move.to_target.col == current_move.from_sel.col
            and last_move.from_sel.slot == current_move.to_target.slot
        ):
            return True

    # Cascade -> Freecell, then Freecell -> Cascade same slot
    if (
        last_move.from_sel.kind == "cascade"
        and last_move.to_target.kind == "freecell"
        and current_move.from_sel.kind == "freecell"
        and current_move.to_target.kind == "cascade"
    ):
        if (
            last_move.from_sel.slot == current_move.to_target.slot
            and last_move.to_target.col == current_move.from_sel.col
        ):
            return True

    # Cascade <-> Cascade back-and-forth
    if (
        last_move.from_sel.kind == "cascade"
        and last_move.to_target.kind == "cascade"
        and current_move.from_sel.kind == "cascade"
        and current_move.to_target.kind == "cascade"
    ):
        if (
            last_move.from_sel.col == current_move.to_target.col
            and last_move.to_target.col == current_move.from_sel.col
        ):
            return True

    return False


def _get_memory_bytes() -> int:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        pass
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except Exception:
        return 0
