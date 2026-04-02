"""
FreeCell game engine — pure Python.
Logic mirrors frontend in web/src/game/freecell.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models import Card, GameState


# ── helpers ──────────────────────────────────────────────────────────────────


def _is_red(suit: str) -> bool:
    return suit in ("hearts", "diamonds")


def _opposite_color(a: Card, b: Card) -> bool:
    return _is_red(a.suit) != _is_red(b.suit)


def _suit_index(suit: str) -> int:
    return {"spades": 0, "hearts": 1, "diamonds": 2, "clubs": 3}[suit]


def _foundation_index_for_card(card: Card) -> int:
    return _suit_index(card.suit)


# ── GameState dataclass (mutable for performance) ────────────────────────────


@dataclass
class State:
    """Internal state used by the solver. Same layout as GameState Pydantic model."""

    cascades: list[list[Card]]         # 8 columns, index 0 = bottom, last = top
    free_cells: list[Optional[Card]]    # 4 slots, None = empty
    foundations: list = field(default_factory=lambda: [[], [], [], []])
    # spades=0, hearts=1, diamonds=2, clubs=3

    @classmethod
    def from_pydantic(cls, gs: GameState) -> State:
        return cls(
            cascades=[list(c) for c in gs.cascades],
            free_cells=list(gs.free_cells),
            foundations=[list(f) for f in gs.foundations],
        )

    def to_pydantic(self) -> GameState:
        return GameState(
            cascades=[list(c) for c in self.cascades],
            free_cells=list(self.free_cells),
            foundations=[list(f) for f in self.foundations],
        )

    def clone(self) -> State:
        return State(
            cascades=[list(c) for c in self.cascades],
            free_cells=list(self.free_cells),
            foundations=[list(f) for f in self.foundations],
        )

    # ── game rules ──────────────────────────────────────────────────────────

    def is_won(self) -> bool:
        return all(len(p) == 13 for p in self.foundations)

    def _empty_free_cells(self) -> int:
        return sum(1 for c in self.free_cells if c is None)

    def _empty_cascades(self) -> int:
        return sum(1 for col in self.cascades if len(col) == 0)

    def _max_sequence_movable(self) -> int:
        f = self._empty_free_cells()
        e = self._empty_cascades()
        return 2 ** (f + 2 * e) - 1

    def _can_place_on_foundation(self, card: Card, pile: list[Card]) -> bool:
        if not pile:
            return card.rank == 1
        top = pile[-1]
        return top.suit == card.suit and card.rank == top.rank + 1

    def _can_place_on_tableau(self, bottom: Card, col: list[Card]) -> bool:
        if not col:
            return True
        top = col[-1]
        return _opposite_color(bottom, top) and bottom.rank == top.rank - 1

    def _is_valid_tableau_run(self, cards: list[Card]) -> bool:
        if len(cards) <= 1:
            return True
        for i in range(len(cards) - 1):
            lower = cards[i]
            upper = cards[i + 1]
            if lower.rank != upper.rank + 1:
                return False
            if not _opposite_color(lower, upper):
                return False
        return True

    # ── move generation ─────────────────────────────────────────────────────

    def get_successors(self, prune: bool = False) -> list[tuple[MoveStep, State]]:
        """
        Generate all legal atomic moves from this state.
        Each move moves exactly ONE card (or a valid tableau run).
        Deduplicates by resulting state key to avoid redundant successors.

        Args:
            prune: If True, apply pruning rules to reduce branching factor:
                - Skip freecell→cascade if card can go to foundation
                - Skip freecell→cascade if moving a King
                - Skip cascade→freecell for Kings (they belong in foundation)
                - Skip cascade→cascade if it blocks a King below
        """
        raw: list[tuple[MoveStep, State]] = []

        # ── Precompute: which Kings are blocked below in each cascade ──────────
        blocked_kings: dict[int, bool] = {}
        if prune:
            for col_idx, col in enumerate(self.cascades):
                blocked_kings[col_idx] = False
                if col:
                    # Check if top card is King blocked by card below
                    for pos in range(len(col) - 1):
                        if col[pos].rank == 13:  # King is not on top
                            blocked_kings[col_idx] = True
                            break

        # 1. Moves FROM free cells
        for slot in range(4):
            card = self.free_cells[slot]
            if card is None:
                continue

            # Free cell → Foundation
            suit_idx = _foundation_index_for_card(card)
            pile = self.foundations[suit_idx]
            if self._can_place_on_foundation(card, pile):
                nxt = self.clone()
                nxt.free_cells[slot] = None
                nxt.foundations[suit_idx] = pile + [card]
                raw.append((
                    MoveStep(
                        from_sel=Selection(kind="freecell", slot=slot),
                        to_target=MoveTarget(kind="foundation", suit_index=suit_idx),
                    ),
                    nxt,
                ))

            # Free cell → cascade (valid tableau placement; empty cascade always valid)
            for col in range(8):
                if self._can_place_on_tableau(card, self.cascades[col]):
                    # PRUNE: never move King from free cell to cascade
                    if prune and card.rank == 13:
                        continue
                    nxt = self.clone()
                    nxt.free_cells[slot] = None
                    nxt.cascades[col] = self.cascades[col] + [card]
                    raw.append((
                        MoveStep(
                            from_sel=Selection(kind="freecell", slot=slot),
                            to_target=MoveTarget(kind="cascade", col=col),
                        ),
                        nxt,
                    ))

        # 2. Moves FROM cascades
        for col in range(8):
            cascade = self.cascades[col]
            if not cascade:
                continue

            # The TOP card (always index len-1) can ALWAYS be moved
            # to foundation, free cell, or another cascade.
            top_index = len(cascade) - 1
            top_card = cascade[top_index]

            # 2a. Top card → foundation (always allowed if legal)
            suit_idx = _foundation_index_for_card(top_card)
            pile = self.foundations[suit_idx]
            if self._can_place_on_foundation(top_card, pile):
                nxt = self.clone()
                nxt.cascades[col] = cascade[:-1]
                nxt.foundations[suit_idx] = pile + [top_card]
                raw.append((
                    MoveStep(
                        from_sel=Selection(kind="cascade", col=col, from_index=top_index),
                        to_target=MoveTarget(kind="foundation", suit_index=suit_idx),
                    ),
                    nxt,
                ))

            # 2b. Top card → free cell (if empty)
            for slot in range(4):
                if self.free_cells[slot] is None:
                    # PRUNE: never move King from cascade to free cell
                    if prune and top_card.rank == 13:
                        continue
                    nxt = self.clone()
                    nxt.cascades[col] = cascade[:-1]
                    nxt.free_cells[slot] = top_card
                    raw.append((
                        MoveStep(
                            from_sel=Selection(kind="cascade", col=col, from_index=top_index),
                            to_target=MoveTarget(kind="freecell", slot=slot),
                        ),
                        nxt,
                    ))

            # 2c. Top card → another cascade
            for dest_col in range(8):
                if dest_col == col:
                    continue
                if self._can_place_on_tableau(top_card, self.cascades[dest_col]):
                    # PRUNE: never move King to cascade
                    if prune and top_card.rank == 13:
                        continue
                    nxt = self.clone()
                    nxt.cascades[col] = cascade[:-1]
                    nxt.cascades[dest_col] = self.cascades[dest_col] + [top_card]
                    raw.append((
                        MoveStep(
                            from_sel=Selection(kind="cascade", col=col, from_index=top_index),
                            to_target=MoveTarget(kind="cascade", col=dest_col),
                        ),
                        nxt,
                    ))

            # 2d. Tableau runs (from deeper in the column) → empty cascade
            # Find the deepest start of a valid tableau run
            run_start = len(cascade) - 1
            while run_start > 0:
                run = cascade[run_start:]
                if self._is_valid_tableau_run(run):
                    break
                run_start -= 1

            max_seq = self._max_sequence_movable()

            # Moves from tableau runs (start < top_index only, top moves already handled)
            for start in range(run_start, top_index):
                cards_to_move = cascade[start:]
                bottom_card = cards_to_move[0]
                run_len = len(cards_to_move)

                # Tableau run → empty cascade
                if run_len <= max_seq:
                    for dest_col in range(8):
                        if dest_col == col:
                            continue
                        if not self.cascades[dest_col]:
                            nxt = self.clone()
                            nxt.cascades[col] = cascade[:start]
                            nxt.cascades[dest_col] = cascade[start:]
                            raw.append((
                                MoveStep(
                                    from_sel=Selection(kind="cascade", col=col, from_index=start),
                                    to_target=MoveTarget(kind="cascade", col=dest_col),
                                ),
                                nxt,
                            ))

                # Tableau run → valid tableau (cascades[dst])
                if run_len <= max_seq:
                    for dest_col in range(8):
                        if dest_col == col:
                            continue
                        if self._can_place_on_tableau(bottom_card, self.cascades[dest_col]):
                            nxt = self.clone()
                            nxt.cascades[col] = cascade[:start]
                            nxt.cascades[dest_col] = self.cascades[dest_col] + cards_to_move
                            raw.append((
                                MoveStep(
                                    from_sel=Selection(kind="cascade", col=col, from_index=start),
                                    to_target=MoveTarget(kind="cascade", col=dest_col),
                                ),
                                nxt,
                            ))

        # Deduplicate by state key (same destination state from different paths)
        seen: set[str] = set()
        successors: list[tuple[MoveStep, State]] = []
        for step, nxt in raw:
            key = nxt.state_key()
            if key not in seen:
                seen.add(key)
                successors.append((step, nxt))

        return successors

    # ── hashing ─────────────────────────────────────────────────────────────

    def state_key(self) -> str:
        """Serialize state to a hashable string for visited set."""
        parts = []
        for col in self.cascades:
            col_str = ",".join(f"{c.suit[0]}{c.rank}" for c in col)
            parts.append(f"c:{col_str}")
        for slot, card in enumerate(self.free_cells):
            parts.append(f"f{slot}:{f'{card.suit[0]}{card.rank}' if card else '_'}")
        for i, pile in enumerate(self.foundations):
            pile_str = ",".join(f"{c.suit[0]}{c.rank}" for c in pile)
            parts.append(f"p{i}:{pile_str}")
        return "|".join(parts)


# Import here to avoid circular
from models import MoveStep, MoveTarget, Selection


# ── API-facing helpers ───────────────────────────────────────────────────────


def state_to_api(s: State) -> GameState:
    return s.to_pydantic()


def card_total_count(state: GameState) -> int:
    total = sum(len(c) for c in state.cascades)
    total += sum(1 for c in state.free_cells if c is not None)
    total += sum(len(f) for f in state.foundations)
    return total


def is_valid_initial_state(state: GameState) -> bool:
    return card_total_count(state) == 52
