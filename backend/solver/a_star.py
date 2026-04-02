"""
A* Search solver for FreeCell.
Uses:
  - g(n): move-type-based cost function from UCS
  - h(n): critical path heuristic
  - f(n) = g(n) + h(n)
"""

from __future__ import annotations

import gc
import heapq
import time
from dataclasses import dataclass
from typing import Optional

from game import State
from models import MoveStep, SearchMetrics


@dataclass
class AStarResult:
    ok: bool
    moves: list[MoveStep]
    metrics: SearchMetrics
    error: Optional[str] = None


def _estimate_move_cost(move: MoveStep) -> float:
    """
    Estimate cost of a move based on its target type.
    Lower cost = more preferred.
    (Same as UCS)
    """
    target_kind = move.to_target.kind
    
    cost_map = {
        "foundation": 0.5,   # Encouraged: solving the puzzle
        "cascade": 1.0,      # Normal cost
        "freecell": 1.8,     # Discouraged: consuming precious free cells
    }
    
    return cost_map.get(target_kind, 1.0)


def _estimate_heuristic(state: State) -> float:
    """
    Critical Path heuristic for FreeCell.
    
    Estimates the minimum cost to reach goal from current state.
    Considers:
      1. Cards not yet in foundation
      2. Depth penalty for cards blocked in cascades
      3. Free cell availability
    
    Admissibility: h(n) <= actual_cost_to_goal
    This is guaranteed because:
      - Each card needs at least 1 move (0.5) to foundation
      - Blocked cards need cascade moves (1.0 each) before foundation
      - Free cells can be optimized away in best case
    """
    # ── Count cards in foundation ───────────────────────────────────────
    cards_in_foundation = sum(len(f) for f in state.foundations)
    cards_left = 52 - cards_in_foundation
    
    # Base cost: each remaining card needs at least 1 move to foundation
    h_value = cards_left * 0.5
    
    # ── Add depth penalty for blocked cards in cascades ──────────────────
    # Cards that are not at the top of their cascade must be moved first
    for cascade in state.cascades:
        # For each card except the top one, add penalty
        # The deeper the card, the more moves needed to expose it
        for i in range(len(cascade) - 1):
            # cascade[i] is blocked by (len(cascade) - i - 1) cards above it
            blocked_depth = len(cascade) - i - 1
            
            # Each card blocking requires a cascade move (cost 1.0) to move away
            # But we use 0.5 as conservative estimate (some might eventually free)
            h_value += blocked_depth * 0.3
    
    # ── Free cell penalty ───────────────────────────────────────────────
    # If free cells are scarce, we need more cascade moves to juggle cards
    free_cells_empty = sum(1 for fc in state.free_cells if fc is None)
    
    if free_cells_empty < 1 and cards_left > 0:
        # Very few free cells → need extra cascade moves for juggling
        h_value += 3.0
    elif free_cells_empty < 2 and cards_left > 5:
        # Limited free cells
        h_value += 1.0
    
    return h_value


def solve(state: State, time_limit: float = 120.0) -> AStarResult:
    """
    A* Search from the given state.
    Uses g(n) = cumulative move cost, h(n) = critical path heuristic.
    f(n) = g(n) + h(n)
    
    Returns solution path as list of MoveStep objects.
    """
    start_time = time.perf_counter()

    # ── Check if already won ───────────────────────────────────────────
    if state.is_won():
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        gc.collect()
        return AStarResult(
            ok=True,
            moves=[],
            metrics=SearchMetrics(
                search_time_ms=round(elapsed_ms, 2),
                peak_memory_bytes=_get_memory_bytes(),
                expanded_nodes=0,
                solution_length=0,
            ),
        )

    # ── Initialize visited set and priority queue ──────────────────────
    # visited maps state_key -> minimum g(n) cost we've seen to reach it
    visited: dict[str, float] = {}
    visited[state.state_key()] = 0.0

    # Priority queue: (f_value, g_value, counter, state, path)
    # f_value = g_value + h_value → ensures A* ordering
    # We also store g_value for visited dict comparisons
    # counter ensures FIFO for ties (stable sort)
    pq: list = []
    counter = 0
    
    h_start = _estimate_heuristic(state)
    f_start = 0.0 + h_start  # g(start) = 0
    heapq.heappush(pq, (f_start, 0.0, counter, state, []))
    counter += 1

    expanded = 0
    deadline = start_time + time_limit

    while pq:
        # ── Check timeout ──────────────────────────────────────────────
        current_time = time.perf_counter()
        if current_time >= deadline:
            elapsed_ms = (current_time - start_time) * 1000
            gc.collect()
            return AStarResult(
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

        # ── Pop state with lowest f(n) ─────────────────────────────────
        f_value, g_value, _, cur_state, path = heapq.heappop(pq)
        expanded += 1

        cur_key = cur_state.state_key()
        
        # Skip if we've found a cheaper path to this state already
        # (use g_value, not f_value, because f includes heuristic)
        if visited.get(cur_key, float('inf')) < g_value:
            continue

        # ── Check goal ─────────────────────────────────────────────────
        if cur_state.is_won():
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            gc.collect()
            return AStarResult(
                ok=True,
                moves=path,
                metrics=SearchMetrics(
                    search_time_ms=round(elapsed_ms, 2),
                    peak_memory_bytes=_get_memory_bytes(),
                    expanded_nodes=expanded,
                    solution_length=len(path),
                ),
            )

        # ── Expand successors ──────────────────────────────────────────
        for move_step, next_state in cur_state.get_successors():
            next_key = next_state.state_key()
            
            # Compute g(next) = g(current) + cost(move)
            move_cost = _estimate_move_cost(move_step)
            new_g = g_value + move_cost
            
            # Compute h(next) = heuristic estimate
            new_h = _estimate_heuristic(next_state)
            
            # Compute f(next) = g(next) + h(next)
            new_f = new_g + new_h

            # Only process if we found a cheaper path to next_state
            if next_key not in visited or visited[next_key] > new_g:
                visited[next_key] = new_g
                new_path = path + [move_step]
                heapq.heappush(pq, (new_f, new_g, counter, next_state, new_path))
                counter += 1

    # ── Exhausted search space ─────────────────────────────────────────
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    gc.collect()
    return AStarResult(
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


def _get_memory_bytes() -> int:
    """Return current RSS memory usage in bytes."""
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        pass

    try:
        import psutil

        process = psutil.Process()
        return process.memory_info().rss
    except Exception:
        pass

    return 0
