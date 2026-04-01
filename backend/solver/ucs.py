"""
Uniform Cost Search (UCS) solver for FreeCell.
Uses move-type-based cost function:
  - Foundation: 0.5 (encouraged)
  - Cascade: 1.0 (normal)
  - FreeCell: 1.8 (discouraged)
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
class UCSResult:
    ok: bool
    moves: list[MoveStep]
    metrics: SearchMetrics
    error: Optional[str] = None


def _estimate_move_cost(move: MoveStep) -> float:
    """
    Estimate cost of a move based on its target type.
    Lower cost = more preferred.
    """
    target_kind = move.to_target.kind
    
    cost_map = {
        "foundation": 0.5,   # Encouraged: solving the puzzle
        "cascade": 1.0,      # Normal cost
        "freecell": 1.8,     # Discouraged: consuming precious free cells
    }
    
    return cost_map.get(target_kind, 1.0)


def solve(state: State, time_limit: float = 120.0) -> UCSResult:
    """
    Uniform Cost Search from the given state.
    Uses move-type-based cost function.
    Returns solution path as list of MoveStep objects.
    """
    start_time = time.perf_counter()

    # ── Check if already won ───────────────────────────────────────────
    if state.is_won():
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        gc.collect()
        return UCSResult(
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
    visited: dict[str, float] = {}  # state_key -> min cost to reach it
    visited[state.state_key()] = 0.0

    # Priority queue: (cumulative_cost, counter, state, path)
    # counter ensures FIFO for ties (stable sort)
    pq: list = []
    counter = 0
    heapq.heappush(pq, (0.0, counter, state, []))
    counter += 1

    expanded = 0
    deadline = start_time + time_limit

    while pq:
        # ── Check timeout ──────────────────────────────────────────────
        current_time = time.perf_counter()
        if current_time >= deadline:
            elapsed_ms = (current_time - start_time) * 1000
            gc.collect()
            return UCSResult(
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

        # ── Pop lowest cost state ──────────────────────────────────────
        cum_cost, _, cur_state, path = heapq.heappop(pq)
        expanded += 1

        cur_key = cur_state.state_key()
        
        # Skip if we've found a cheaper path to this state already
        if visited.get(cur_key, float('inf')) < cum_cost:
            continue

        # ── Check goal ─────────────────────────────────────────────────
        if cur_state.is_won():
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            gc.collect()
            return UCSResult(
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
            
            # Compute cost of this move
            move_cost = _estimate_move_cost(move_step)
            new_cum_cost = cum_cost + move_cost

            # Only process if we found a cheaper path
            if next_key not in visited or visited[next_key] > new_cum_cost:
                visited[next_key] = new_cum_cost
                new_path = path + [move_step]
                heapq.heappush(pq, (new_cum_cost, counter, next_state, new_path))
                counter += 1

    # ── Exhausted search space ─────────────────────────────────────────
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    gc.collect()
    return UCSResult(
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
