"""
Breadth-First Search (BFS) solver for FreeCell.
With move pruning and smart successor ordering.
"""

from __future__ import annotations

import gc
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from game import State
from models import MoveStep, SearchMetrics


@dataclass
class BFSResult:
    ok: bool
    moves: list[MoveStep]
    metrics: SearchMetrics
    error: str | None = None


def _heuristic(state: State) -> float:
    """
    Heuristic for BFS: estimate remaining moves to goal.
    Lower = better (closer to goal).
    """
    cards_in_f = sum(len(f) for f in state.foundations)
    cards_left = 52 - cards_in_f
    h = cards_left * 0.5

    # Depth penalty for blocked cards
    for cascade in state.cascades:
        for i in range(len(cascade) - 1):
            h += (len(cascade) - i - 1) * 0.3

    # Free cell scarcity penalty
    free_empty = sum(1 for fc in state.free_cells if fc is None)
    if free_empty < 1 and cards_left > 0:
        h += 3.0
    elif free_empty < 2 and cards_left > 5:
        h += 1.0

    return h


def _move_priority(move: MoveStep) -> float:
    """Lower = more preferred move."""
    target = move.to_target.kind
    if target == "foundation":
        return 0.5
    elif target == "freecell":
        return 1.8
    return 1.0


def _should_prune_deep(state: State, move: MoveStep, next_state: State) -> bool:
    """
    Aggressive pruning rules for BFS (beyond King pruning in get_successors).
    Returns True if the move should be skipped.
    """
    # ── RULE 1: Don't move a card that belongs in its foundation ─────────────
    # If a card is the next card needed for its foundation pile, don't move it
    # somewhere else (except to foundation)
    if move.from_sel.kind == "freecell":
        card = state.free_cells[move.from_sel.slot]
        if card:
            suit_idx = {"spades": 0, "hearts": 1, "diamonds": 2, "clubs": 3}[card.suit]
            pile = state.foundations[suit_idx]
            # If this card completes the run to foundation, it shouldn't leave freecell
            if pile and card.rank == pile[-1].rank + 1 and card.rank < 13:
                # Don't move to cascade if card can go to foundation
                if move.to_target.kind == "cascade":
                    return True
            # Also: don't move low cards (A-5) from freecell to cascade unnecessarily
            if card.rank <= 5 and move.to_target.kind == "cascade":
                return True

    # ── RULE 2: Don't remove a useful card from cascade top ─────────────────
    # If the top card of a cascade can go to foundation, don't move it to freecell
    if move.from_sel.kind == "cascade" and move.to_target.kind == "freecell":
        col = move.from_sel.col
        cascade = state.cascades[col]
        if cascade:
            top_card = cascade[-1]
            suit_idx = {"spades": 0, "hearts": 1, "diamonds": 2, "clubs": 3}[top_card.suit]
            pile = state.foundations[suit_idx]
            if pile and top_card.rank == pile[-1].rank + 1:
                # Moving it to freecell delays the foundation move
                return True

    # ── RULE 3: Don't bury cards deeper in cascades ─────────────────────────
    # Adding to a cascade that already has 8+ cards is rarely helpful
    if move.to_target.kind == "cascade":
        dest_col = move.to_target.col
        if len(state.cascades[dest_col]) >= 8:
            return True

    # ── RULE 4: Prefer empty cascades ───────────────────────────────────────
    # If moving to cascade, prefer empty ones (already enforced by tableau rules)
    # But also: don't stack cards on a cascade that already has 6+ cards unless necessary

    # ── RULE 5: Moving card that could go to foundation from cascade to cascade ──
    if move.from_sel.kind == "cascade" and move.to_target.kind == "cascade":
        col = move.from_sel.col
        cascade = state.cascades[col]
        if cascade:
            top_card = cascade[-1]
            suit_idx = {"spades": 0, "hearts": 1, "diamonds": 2, "clubs": 3}[top_card.suit]
            pile = state.foundations[suit_idx]
            if pile and top_card.rank == pile[-1].rank + 1:
                # This card can go to foundation! Don't move it to cascade.
                return True

    # ── RULE 6: Cascade -> freecell is usually wasteful unless freeing a key card ─
    # Skip cascade -> freecell if we already have 2+ free cells
    if move.from_sel.kind == "cascade" and move.to_target.kind == "freecell":
        free_empty = sum(1 for fc in state.free_cells if fc is None)
        if free_empty >= 2:
            # Already have plenty of free cells, skip storing in freecell
            return True

    # ── RULE 7: Skip cascade->cascade that buries low cards (A-7) ────────────
    # Moving a low card to cascade when it could eventually go to foundation
    if move.from_sel.kind == "cascade" and move.to_target.kind == "cascade":
        col = move.from_sel.col
        cascade = state.cascades[col]
        if cascade:
            top_card = cascade[-1]
            dest_col = move.to_target.col
            # Skip if: moving a low card to a non-empty cascade with 4+ cards
            if top_card.rank <= 7 and len(state.cascades[dest_col]) >= 4:
                return True

    # ── RULE 8: Prefer moving to cascade destination that exposes foundation cards ─
    # (handled by heuristic sorting, but add as tie-breaker here)

    return False


def solve(
    state: State,
    time_limit: float = 120.0,
    prune_undo: bool = True,
    max_depth: int = 0,
    prune_moves: bool = True,
) -> BFSResult:
    """
    Breadth-First Search from the given state.
    Enhanced with heuristic-guided ordering and aggressive pruning.
    """
    start_time = time.perf_counter()

    if state.is_won():
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        gc.collect()
        return BFSResult(
            ok=True,
            moves=[],
            metrics=SearchMetrics(
                search_time_ms=round(elapsed_ms, 2),
                peak_memory_bytes=_get_memory_bytes(),
                expanded_nodes=0,
                solution_length=0,
            ),
        )

    visited: dict[str, int] = {}
    visited[state.state_key()] = 0

    queue: deque[tuple[State, list[MoveStep], tuple | None]] = deque()
    queue.append((state, [], None))

    expanded = 0
    deadline = start_time + time_limit

    while queue:
        current_time = time.perf_counter()
        if current_time >= deadline:
            elapsed_ms = (current_time - start_time) * 1000
            gc.collect()
            return BFSResult(
                ok=False,
                moves=[],
                error="timeout",
                metrics=SearchMetrics(
                    search_time_ms=round(elapsed_ms, 2),
                    peak_memory_bytes=_get_memory_bytes(),
                    expanded_nodes=expanded,
                    solution_length=0,
                ),
            )

        cur_state, path, last_move = queue.popleft()
        depth = len(path)

        if max_depth > 0 and depth >= max_depth:
            continue

        successors = cur_state.get_successors(prune=prune_moves)

        def sort_key(item):
            move, next_state = item
            h = _heuristic(next_state)
            p = _move_priority(move)
            return (h, p)

        successors.sort(key=sort_key)

        for move_step, next_state in successors:
            key = next_state.state_key()
            new_depth = depth + 1

            if key in visited and visited[key] <= new_depth:
                continue

            if prune_undo and last_move is not None:
                if _is_undoing(last_move, move_step):
                    continue

            if _should_prune_deep(cur_state, move_step, next_state):
                continue

            visited[key] = new_depth
            new_path = path + [move_step]

            if next_state.is_won():
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                gc.collect()
                return BFSResult(
                    ok=True,
                    moves=new_path,
                    metrics=SearchMetrics(
                        search_time_ms=round(elapsed_ms, 2),
                        peak_memory_bytes=_get_memory_bytes(),
                        expanded_nodes=expanded + 1,
                        solution_length=len(new_path),
                    ),
                )

            queue.append((next_state, new_path, move_step))
            expanded += 1

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    gc.collect()
    return BFSResult(
        ok=False,
        moves=[],
        error="unsolvable",
        metrics=SearchMetrics(
            search_time_ms=round(elapsed_ms, 2),
            peak_memory_bytes=_get_memory_bytes(),
            expanded_nodes=expanded,
            solution_length=0,
        ),
    )


def _is_undoing(last_move: MoveStep, current_move: MoveStep) -> bool:
    """
    Returns True if current_move immediately undoes last_move.
    Example: last_move = cascade[0] -> freecell[0]
             current_move = freecell[0] -> cascade[0]  (undoing!)
    """
    # Free cell <-> Cascade swap
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

    # Cascade -> Free cell -> Cascade same column (different column undo)
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

    # Same cascade back-and-forth (cascade[0] -> cascade[1] then cascade[1] -> cascade[0])
    if (
        last_move.from_sel.kind == "cascade"
        and last_move.to_target.kind == "cascade"
        and current_move.from_sel.kind == "cascade"
        and current_move.to_target.kind == "cascade"
    ):
        if (
            last_move.from_sel.col == current_move.to_target.col
            and last_move.to_target.col == current_move.from_sel.col
            and last_move.from_sel.col == current_move.from_sel.col
        ):
            return True

    return False


def _get_memory_bytes() -> int:
    """Return current RSS memory usage in bytes."""
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
