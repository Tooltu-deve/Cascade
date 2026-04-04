from __future__ import annotations

import gc
import heapq
import time
from dataclasses import dataclass
from typing import Optional

from game import State, _is_red
from models import Card, MoveStep, MoveTarget, SearchMetrics, Selection


@dataclass
class UCSResult:
    ok: bool
    moves: list[MoveStep]
    metrics: SearchMetrics
    error: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# OPTIMIZATION 1: Symmetry Breaking - Canonical State Keys
# ══════════════════════════════════════════════════════════════════════════════


def _card_to_str(card: Optional[Card]) -> str:
    """Convert card to string for hashing."""
    if card is None:
        return "_"
    return f"{card.suit[0]}{card.rank}"


def _canonical_state_key(state: State) -> str:
    """
    Create a canonical state key that treats symmetric states as identical.
    
    Symmetries in FreeCell:
      - Free cells are interchangeable (order doesn't matter)
      - Empty cascades are interchangeable
      - Non-empty cascades can be sorted for canonical form
    
    This dramatically reduces the visited set size.
    """
    # Sort freecells (treat as a set, not ordered slots)
    freecell_cards = sorted(
        _card_to_str(fc) for fc in state.free_cells
    )
    fc_part = ",".join(freecell_cards)
    
    # Sort cascades by their string representation
    # This treats cascade positions as interchangeable
    cascade_strs = []
    for col in state.cascades:
        col_str = ",".join(_card_to_str(c) for c in col)
        cascade_strs.append(col_str)
    cascade_strs.sort()
    casc_part = "|".join(cascade_strs)
    
    # Foundations are fixed by suit (spades=0, hearts=1, etc.)
    # Just record the top rank for each
    found_part = ",".join(str(len(f)) for f in state.foundations)
    
    return f"F:{fc_part}|C:{casc_part}|P:{found_part}"


# ══════════════════════════════════════════════════════════════════════════════
# OPTIMIZATION 2: Safe Move Pruning (Auto-play safe foundation moves)
# ══════════════════════════════════════════════════════════════════════════════


def _get_min_foundation_rank(state: State, color: str) -> int:
    """
    Get the minimum rank among foundations of a given color.
    color: 'red' or 'black'
    """
    if color == "red":
        # hearts (1) and diamonds (2)
        return min(len(state.foundations[1]), len(state.foundations[2]))
    else:
        # spades (0) and clubs (3)
        return min(len(state.foundations[0]), len(state.foundations[3]))


def _is_safe_foundation_move(card: Card, state: State) -> bool:
    """
    Determine if moving a card to foundation is "safe" (always optimal).
    
    A move is safe if:
      - Aces (rank 1) are always safe
      - Twos (rank 2) are always safe
      - For rank N >= 3: safe if both opposite-color (N-2) cards are in foundation
    
    This is because cards rank N-1 of opposite color could be placed on card N,
    but if N-2 of opposite color are already in foundation, N-1 will go to
    foundation anyway, so we don't need to keep N in play.
    """
    if card.rank <= 2:
        return True
    
    # For rank >= 3, check opposite color foundations
    card_is_red = _is_red(card.suit)
    opposite_color = "black" if card_is_red else "red"
    
    # We need rank N-1 of opposite color to eventually go to foundation
    # This is safe if N-2 of opposite color is already there
    min_opposite = _get_min_foundation_rank(state, opposite_color)
    
    # Safe if opposite color has at least (rank - 2) cards
    # e.g., for 5♥, need 3♠ and 3♣ already in foundation
    return min_opposite >= card.rank - 2


def _apply_safe_moves(state: State, path: list[MoveStep]) -> tuple[State, list[MoveStep]]:
    """
    Apply all safe foundation moves automatically.
    Returns the new state and extended path.
    
    This is a key optimization that reduces branching factor significantly.
    """
    current = state
    current_path = list(path)
    changed = True
    
    while changed:
        changed = False
        
        # Check freecells for safe moves
        for slot in range(4):
            card = current.free_cells[slot]
            if card is None:
                continue
            
            suit_idx = {"spades": 0, "hearts": 1, "diamonds": 2, "clubs": 3}[card.suit]
            foundation = current.foundations[suit_idx]
            
            # Can place on foundation?
            can_place = (len(foundation) == 0 and card.rank == 1) or \
                        (len(foundation) > 0 and foundation[-1].rank == card.rank - 1)
            
            if can_place and _is_safe_foundation_move(card, current):
                # Apply the move
                new_state = current.clone()
                new_state.free_cells[slot] = None
                new_state.foundations[suit_idx] = foundation + [card]
                
                move = MoveStep(
                    from_sel=Selection(kind="freecell", slot=slot),
                    to_target=MoveTarget(kind="foundation", suit_index=suit_idx),
                )
                current_path.append(move)
                current = new_state
                changed = True
                break
        
        if changed:
            continue
        
        # Check cascade tops for safe moves
        for col in range(8):
            cascade = current.cascades[col]
            if not cascade:
                continue
            
            card = cascade[-1]
            suit_idx = {"spades": 0, "hearts": 1, "diamonds": 2, "clubs": 3}[card.suit]
            foundation = current.foundations[suit_idx]
            
            # Can place on foundation?
            can_place = (len(foundation) == 0 and card.rank == 1) or \
                        (len(foundation) > 0 and foundation[-1].rank == card.rank - 1)
            
            if can_place and _is_safe_foundation_move(card, current):
                # Apply the move
                new_state = current.clone()
                new_state.cascades[col] = cascade[:-1]
                new_state.foundations[suit_idx] = foundation + [card]
                
                move = MoveStep(
                    from_sel=Selection(kind="cascade", col=col, from_index=len(cascade) - 1),
                    to_target=MoveTarget(kind="foundation", suit_index=suit_idx),
                )
                current_path.append(move)
                current = new_state
                changed = True
                break
    
    return current, current_path


# ══════════════════════════════════════════════════════════════════════════════
# Cost Function
# ══════════════════════════════════════════════════════════════════════════════


def _estimate_move_cost(move: MoveStep, state: State) -> float:
    """
    Estimate cost of a move based on its tactical value.
    Lower cost = more preferred.
    Same as A* cost function for fair comparison.
    """
    target_kind = move.to_target.kind
    
    if target_kind == "foundation":
        return 0.2
        
    if target_kind == "freecell":
        return 2.5
        
    if target_kind == "cascade":
        from_sel = move.from_sel
        if from_sel.kind == "cascade":
            # Moving the bottom-most card (index 0) clears the column
            if from_sel.from_index == 0:
                return 0.4
        
        # Moving onto a non-empty cascade builds a sequence
        target_col = move.to_target.col
        if len(state.cascades[target_col]) > 0:
            return 0.8
            
        # Normal cascade move (e.g. moving a non-clearing stack to an empty cascade)
        return 1.2
        
    return 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Main Solver
# ══════════════════════════════════════════════════════════════════════════════


def solve(state: State, time_limit: float = 120.0) -> UCSResult:
    """
    Uniform Cost Search from the given state with optimizations.
    
    Optimizations:
      1. Safe Move Pruning: Auto-play forced foundation moves
      2. Symmetry Breaking: Canonical state keys reduce visited set
    
    Returns solution path as list of MoveStep objects.
    """
    start_time = time.perf_counter()

    # ── Apply safe moves to initial state ──────────────────────────────
    state, initial_path = _apply_safe_moves(state, [])

    # ── Check if already won ───────────────────────────────────────────
    if state.is_won():
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        gc.collect()
        return UCSResult(
            ok=True,
            moves=initial_path,
            metrics=SearchMetrics(
                search_time_ms=round(elapsed_ms, 2),
                peak_memory_bytes=_get_memory_bytes(),
                expanded_nodes=0,
                solution_length=len(initial_path),
            ),
        )

    # ── Initialize visited set and priority queue ──────────────────────
    # Use canonical state key for symmetry breaking
    visited: dict[str, float] = {}
    canonical_key = _canonical_state_key(state)
    visited[canonical_key] = 0.0

    # Priority queue: (cumulative_cost, counter, state, path)
    # counter ensures FIFO for ties (stable sort)
    pq: list = []
    counter = 0
    heapq.heappush(pq, (0.0, counter, state, initial_path))
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

        # Use canonical key for visited check (symmetry breaking)
        cur_key = _canonical_state_key(cur_state)
        
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
            # Apply safe moves to the successor state (Safe Move Pruning)
            safe_state, safe_path_ext = _apply_safe_moves(next_state, [move_step])
            
            # Compute cost: base move cost + minimal cost for auto-played safe moves
            move_cost = _estimate_move_cost(move_step, cur_state)
            for safe_move in safe_path_ext[1:]:  # Skip first which is move_step
                move_cost += 0.2  # Foundation moves cost 0.2
            
            new_cum_cost = cum_cost + move_cost
            
            # Use canonical key for symmetry breaking
            next_key = _canonical_state_key(safe_state)

            # Only process if we found a cheaper path
            if next_key not in visited or visited[next_key] > new_cum_cost:
                visited[next_key] = new_cum_cost
                new_path = path + safe_path_ext
                heapq.heappush(pq, (new_cum_cost, counter, safe_state, new_path))
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
