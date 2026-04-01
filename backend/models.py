from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Card(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    suit: str  # 'spades' | 'hearts' | 'diamonds' | 'clubs'
    rank: int  # 1-13

    def model_post_init(self, __context) -> None:
        if not 1 <= self.rank <= 13:
            raise ValueError(f"rank must be 1-13, got {self.rank}")
        if self.suit not in ("spades", "hearts", "diamonds", "clubs"):
            raise ValueError(f"invalid suit: {self.suit}")


class GameState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cascades: list[list[Card]] = Field(..., description="8 columns")
    free_cells: list[Optional[Card]] = Field(
        ..., validation_alias="freeCells",
        description="4 free cells, element is None if empty",
    )
    foundations: list[list[Card]] = Field(
        ..., description="4 piles: spades, hearts, diamonds, clubs",
    )

    def model_post_init(self, __context) -> None:
        if len(self.cascades) != 8:
            raise ValueError(f"must have 8 cascades, got {len(self.cascades)}")
        if len(self.free_cells) != 4:
            raise ValueError(f"must have 4 free cells, got {len(self.free_cells)}")
        if len(self.foundations) != 4:
            raise ValueError(f"must have 4 foundations, got {len(self.foundations)}")


class Selection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str  # 'cascade' | 'freecell'
    col: Optional[int] = Field(default=None, validation_alias="col")
    from_index: Optional[int] = Field(default=None, validation_alias="fromIndex")
    slot: Optional[int] = Field(default=None, validation_alias="slot")

    def model_post_init(self, __context) -> None:
        if self.kind == "cascade":
            if self.col is None or self.from_index is None:
                raise ValueError("cascade selection needs col and fromIndex")
        elif self.kind == "freecell":
            if self.slot is None:
                raise ValueError("freecell selection needs slot")


class MoveTarget(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str  # 'foundation' | 'freecell' | 'cascade'
    suit_index: Optional[int] = Field(
        default=None, validation_alias="suitIndex",
    )
    slot: Optional[int] = Field(default=None, validation_alias="slot")
    col: Optional[int] = Field(default=None, validation_alias="col")


class MoveStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_sel: Selection = Field(validation_alias="from")
    to_target: MoveTarget = Field(validation_alias="to")


class SearchMetrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    search_time_ms: float = Field(validation_alias="searchTimeMs")
    peak_memory_bytes: int = Field(validation_alias="peakMemoryBytes")
    expanded_nodes: int = Field(validation_alias="expandedNodes")
    solution_length: int = Field(validation_alias="solutionLength")


class SolveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state: GameState


class SolveResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ok: bool
    moves: Optional[list[MoveStep]] = Field(default=None, validation_alias="moves")
    metrics: Optional[SearchMetrics] = Field(default=None, validation_alias="metrics")
    error: Optional[str] = Field(default=None, validation_alias="error")
