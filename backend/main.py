"""
FastAPI service — FreeCell Solver.
Endpoints: POST /solve/{bfs,dfs,ucs,astar}
"""

from __future__ import annotations

import os
import tracemalloc
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from game import State, card_total_count, is_valid_initial_state
from models import GameState, MoveStep, SearchMetrics, SolveRequest
from solver import bfs_solve, dfs_solve, astar_solve

# Start memory tracing at module load so peak captures the whole server startup
tracemalloc.start()


# ── lifetime ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    tracemalloc.stop()


# ── app ──────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="FreeCell Solver API",
    description="BFS / DFS / UCS / A* solver for FreeCell — CSC14003",
    lifespan=lifespan,
)

# CORS for development (frontend runs on a different port)
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _parse_state(req: SolveRequest) -> State:
    gs = req.state
    if not is_valid_initial_state(gs):
        raise HTTPException(
            status_code=422,
            detail="invalid_state: must have exactly 52 cards",
        )
    return State.from_pydantic(gs)


def _camel_json_response(ok: bool, moves=None, metrics=None, error=None) -> JSONResponse:
    """Build a camelCase JSON response matching the frontend contract."""
    body: dict = {"ok": ok}
    if ok and moves is not None:
        body["moves"] = [
            {
                "from": {
                    "kind": m.from_sel.kind,
                    **({"col": m.from_sel.col} if m.from_sel.kind == "cascade" else {}),
                    **({"fromIndex": m.from_sel.from_index} if m.from_sel.kind == "cascade" else {}),
                    **({"slot": m.from_sel.slot} if m.from_sel.kind == "freecell" else {}),
                },
                "to": {
                    "kind": m.to_target.kind,
                    **({"suitIndex": m.to_target.suit_index} if m.to_target.kind == "foundation" else {}),
                    **({"slot": m.to_target.slot} if m.to_target.kind == "freecell" else {}),
                    **({"col": m.to_target.col} if m.to_target.kind == "cascade" else {}),
                },
            }
            for m in moves
        ]
    if metrics is not None:
        body["metrics"] = {
            "searchTimeMs": round(metrics.search_time_ms, 2),
            "peakMemoryBytes": metrics.peak_memory_bytes,
            "expandedNodes": metrics.expanded_nodes,
            "solutionLength": metrics.solution_length,
        }
    if not ok and error is not None:
        body["error"] = error
    return JSONResponse(content=body)


# ── health ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


# ── solver endpoints ─────────────────────────────────────────────────────────


@app.post("/solve/bfs")
def solve_bfs(req: SolveRequest):
    """Breadth-First Search solver."""
    state = _parse_state(req)
    result = bfs_solve(state, time_limit=120.0)
    return _camel_json_response(
        ok=result.ok,
        moves=result.moves if result.ok else None,
        metrics=result.metrics,
        error=result.error if not result.ok else None,
    )


@app.post("/solve/dfs")
def solve_dfs(req: SolveRequest):
    """Depth-First Search solver using Iterative Deepening."""
    state = _parse_state(req)
    result = dfs_solve(state, time_limit=120.0)
    return _camel_json_response(
        ok=result.ok,
        moves=result.moves if result.ok else None,
        metrics=result.metrics,
        error=result.error if not result.ok else None,
    )

@app.post("/solve/astar")
def solve_astar(req: SolveRequest):
    """A* Search solver with critical path heuristic."""
    state = _parse_state(req)
    result = astar_solve(state, time_limit=120.0)
    return _camel_json_response(
        ok=result.ok,
        moves=result.moves if result.ok else None,
        metrics=result.metrics,
        error=result.error if not result.ok else None,
    )


@app.post("/solve/ucs")
def solve_ucs(req: SolveRequest):
    """Uniform-Cost Search solver (not yet implemented)."""
    raise HTTPException(status_code=501, detail="UCS solver not yet implemented")


# ── entry point ──────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
