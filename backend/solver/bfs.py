"""
Breadth-First Search (BFS) solver for FreeCell.
"""

from __future__ import annotations

import gc
import sys
import time
from collections import deque
from dataclasses import dataclass, field

from game import State
from models import MoveStep, SearchMetrics, SolveResponse


@dataclass
class BFSResult:
    ok: bool
    moves: list[MoveStep]
    metrics: SearchMetrics
    error: str | None = None


def solve(state: State, time_limit: float = 120.0) -> BFSResult:
    """
    Breadth-First Search from the given state.
    Returns solution path as list of MoveStep objects.
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

    # visited[state_key] = None (just tracking, no parent needed for path)
    visited: dict[str, None] = {}
    visited[state.state_key()] = None

    # queue: deque of (state, list of moves from start to this state)
    queue: deque[tuple[State, list[MoveStep]]] = deque()
    queue.append((state, []))

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

        cur_state, path = queue.popleft()
        expanded += 1

        for move_step, next_state in cur_state.get_successors():
            key = next_state.state_key()
            if key in visited:
                continue
            visited[key] = None

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
                        expanded_nodes=expanded,
                        solution_length=len(new_path),
                    ),
                )

            queue.append((next_state, new_path))

    # Exhausted search space — unsolvable within limits
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
