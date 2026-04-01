"""
Depth-First Search (DFS) solver for FreeCell.
Uses Iterative Deepening Search (IDS) — explores level by level (depth 0, 1, 2, ...).
IDS guarantees optimal solution depth without the memory overhead of BFS.
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


def solve(state: State, time_limit: float = 120.0) -> DFSResult:
    """
    Iterative Deepening DFS.
    Repeatedly runs depth-limited search with increasing depth bounds until
    a solution is found or time runs out.
    """
    start_time = time.perf_counter()

    if state.is_won():
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        gc.collect()
        return DFSResult(
            ok=True,
            moves=[],
            metrics=SearchMetrics(
                search_time_ms=round(elapsed_ms, 2),
                peak_memory_bytes=_get_memory_bytes(),
                expanded_nodes=0,
                solution_length=0,
            ),
        )

    total_expanded = 0
    depth = 0

    while True:
        current_time = time.perf_counter()
        if current_time >= (start_time + time_limit):
            elapsed_ms = (current_time - start_time) * 1000
            gc.collect()
            return DFSResult(
                ok=False,
                moves=[],
                error="timeout",
                metrics=SearchMetrics(
                    search_time_ms=round(elapsed_ms, 2),
                    peak_memory_bytes=_get_memory_bytes(),
                    expanded_nodes=total_expanded,
                    solution_length=0,
                ),
            )

        # Run DLS at depth 'depth' — clears visited per iteration
        result = _dls(state, depth, start_time, time_limit)

        total_expanded += result.expanded

        if result.solution is not None:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            gc.collect()
            return DFSResult(
                ok=True,
                moves=result.solution,
                metrics=SearchMetrics(
                    search_time_ms=round(elapsed_ms, 2),
                    peak_memory_bytes=_get_memory_bytes(),
                    expanded_nodes=total_expanded,
                    solution_length=len(result.solution),
                ),
            )

        depth += 1

        # Safety cap
        if depth > 500:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            gc.collect()
            return DFSResult(
                ok=False,
                moves=[],
                error="depth_limit",
                metrics=SearchMetrics(
                    search_time_ms=round(elapsed_ms, 2),
                    peak_memory_bytes=_get_memory_bytes(),
                    expanded_nodes=total_expanded,
                    solution_length=0,
                ),
            )


@dataclass
class DLSResult:
    solution: Optional[list[MoveStep]]  # None = no solution at this depth
    expanded: int


def _dls(state: State, limit: int, start_time: float, time_limit: float) -> DLSResult:
    """
    Depth-Limited Search with cycle detection.
    Uses a visited set cleared per call (per depth iteration) to avoid
    revisiting the same state at the same depth level.
    Skips cycles on the current path via path_keys.
    """
    visited: set[str] = {state.state_key()}
    return _recurse(state, limit, [], visited, start_time, time_limit, 0)


def _recurse(
    state: State,
    limit: int,
    path: list[MoveStep],
    visited: set[str],
    start_time: float,
    time_limit: float,
    expanded: int,
) -> DLSResult:
    """Recursive DFS with depth limit."""

    # Time check every 200 recursive calls
    if expanded > 0 and expanded % 200 == 0:
        elapsed = time.perf_counter() - start_time
        if elapsed >= time_limit:
            return DLSResult(solution=None, expanded=expanded)

    if state.is_won():
        return DLSResult(solution=path, expanded=expanded)

    if limit <= 0:
        return DLSResult(solution=None, expanded=expanded)

    for move_step, next_state in state.get_successors():
        key = next_state.state_key()

        # Skip if already visited at this depth level
        if key in visited:
            continue

        # Add to visited, recurse, remove on backtrack
        visited.add(key)
        result = _recurse(
            next_state, limit - 1, path + [move_step],
            visited, start_time, time_limit, expanded + 1,
        )
        visited.discard(key)

        if result.solution is not None:
            return result

        expanded = result.expanded

    return DLSResult(solution=None, expanded=expanded)


def _get_memory_bytes() -> int:
    """Return current RSS memory usage in bytes (Unix/macOS)."""
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
