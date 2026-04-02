"""
Parse games.txt -> API JSON payloads for testing.

Format games.txt:
  ## <game name>
  cascades:
  <card>,<card>,...    # cascade 0
  <card>,<card>        # cascade 1
  ...                  # up to 8 cascades (empty lines = empty cascade)

  freecells: <slot0>,<slot1>,<slot2>,<slot3>   # _ = empty

  foundations:
  <s1>,<s2>,...        # spades
  <h1>,<h2>,...         # hearts
  <d1>,<d2>,...         # diamonds
  <c1>,<c2>,...         # clubs

Card format: <suit><rank>
  suit: s/spades, h/hearts, d/diamonds, c/clubs
  rank: 1=Ace, 2..10, 11=J, 12=Q, 13=K

Run:
  python3 parser.py           # print all games
  python3 parser.py 1         # print game 1 only
  python3 parser.py 1 3       # print games 1 and 3
  python3 parser.py --test    # test both BFS and DFS
"""

import sys
import json
import os

SUIT_MAP = {'s': 'spades', 'h': 'hearts', 'd': 'diamonds', 'c': 'clubs'}
RANK_MAP = {
    'a': 1, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
    '7': 7, '8': 8, '9': 9, '10': 10, 'j': 11, 'q': 12, 'k': 13,
}


def parse_card(s: str) -> dict:
    s = s.strip().lower()
    if not s or s == '_':
        return None
    suit = SUIT_MAP[s[0]]
    rank_str = s[1:].lower()
    if rank_str in ('a', 'ace'):
        rank = 1
    elif rank_str in ('j', 'jack'):
        rank = 11
    elif rank_str in ('q', 'queen'):
        rank = 12
    elif rank_str in ('k', 'king'):
        rank = 13
    else:
        rank = int(rank_str)
    return {'suit': suit, 'rank': rank}


def parse_line(line: str) -> list:
    line = line.strip()
    if not line:
        return []
    return [c for c in (parse_card(p) for p in line.split(',')) if c is not None]


def parse_games(filepath: str):
    with open(filepath) as f:
        raw = f.read()

    # Split into game blocks (separated by ##)
    blocks = raw.split('\n##')
    games = []

    for block in blocks:
        block = block.strip()
        if not block or block.startswith('# FreeCell'):
            continue

        lines = block.split('\n')
        name = lines[0].lstrip('#').strip()

        cascades = []
        free_cells = [None] * 4
        foundations = [[], [], [], []]

        section = None
        found_idx = 0

        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if line.endswith(':'):
                key = line.rstrip(':').strip().lower()
                if key == 'cascades':
                    section = 'cascades'
                    cascades = []
                elif key == 'freecells':
                    section = 'freecells'
                elif key == 'foundations':
                    section = 'foundations'
                    found_idx = 0
                continue

            if section == 'cascades':
                # games.txt: first card = TOP (moveable), last = BOTTOM
                # State: index 0 = BOTTOM, last = TOP
                # So reverse the line when parsing
                cards = parse_line(line)
                cascades.append(list(reversed(cards)))

            elif section == 'freecells':
                parts = [p.strip() for p in line.split(',')]
                for i, p in enumerate(parts[:4]):
                    free_cells[i] = parse_card(p)

            elif section == 'foundations':
                if found_idx < 4:
                    foundations[found_idx] = parse_line(line)
                    found_idx += 1

        # Fill cascades to exactly 8
        while len(cascades) < 8:
            cascades.append([])

        games.append((name, {
            'state': {
                'cascades': cascades,
                'freeCells': free_cells,
                'foundations': foundations,
            }
        }))

    return games


def test_game(payload: dict, name: str, time_limit: float = 30.0,
              solvers=None):
    """Test a game with BFS, DFS, and UCS (or custom solver list)."""
    sys.path.insert(0, os.path.dirname(__file__))
    from models import SolveRequest
    from game import State
    from solver.bfs import solve as bfs_solve
    from solver.dfs import solve as dfs_solve
    from solver.ucs import solve as ucs_solve
    from solver.a_star import solve as astar_solve

    if solvers is None:
        solvers = [('BFS', bfs_solve), ('DFS', dfs_solve), ('UCS', ucs_solve), ('A*', astar_solve)]

    s = State.from_pydantic(SolveRequest.model_validate(payload).state)
    total = (sum(len(c) for c in s.cascades)
             + sum(len(f) for f in s.foundations)
             + sum(1 for fc in s.free_cells if fc))

    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    print(f"  Total cards: {total}/52")
    print(f"  Cascade cards: {sum(len(c) for c in s.cascades)}")
    for i, col in enumerate(s.cascades):
        if col:
            print(f"    cascade[{i}]: {','.join(f'{c.suit[0]}{c.rank}' for c in col)}")

    for label, fn in solvers:
        r = fn(s, time_limit=time_limit)
        status = '✓' if r.ok else '✗'
        print(f"  {status} {label}: ok={r.ok}, moves={r.metrics.solution_length}, "
              f"expanded={r.metrics.expanded_nodes}, time={r.metrics.search_time_ms:.0f}ms")
        if r.error:
            print(f"      error: {r.error}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, 'games.txt')

    args = sys.argv[1:]

    # Parse --test and --solvers flags
    do_test = '--test' in args
    time_limit = 30.0
    selected_solvers = None

    # Parse --timeout
    for a in args:
        if a.startswith('--timeout='):
            time_limit = float(a.split('=', 1)[1])

    # --solvers=bfs,dfs,ucs or --solvers=all
    for a in args:
        if a.startswith('--solvers='):
            val = a.split('=', 1)[1]
            sys.path.insert(0, script_dir)
            from solver.bfs import solve as bfs_solve
            from solver.dfs import solve as dfs_solve
            from solver.ucs import solve as ucs_solve
            from solver.a_star import solve as astar_solve
            if val == 'all':
                selected_solvers = [('BFS', bfs_solve), ('DFS', dfs_solve), ('UCS', ucs_solve), ('A*', astar_solve)]
            else:
                parts = val.split(',')
                name_map = {
                    'bfs': ('BFS', bfs_solve), 'dfs': ('DFS', dfs_solve),
                    'ucs': ('UCS', ucs_solve), 'astar': ('A*', astar_solve),
                }
                selected_solvers = [name_map[p.strip().lower()] for p in parts if p.strip().lower() in name_map]

    args = [a for a in args if not a.startswith('--solvers=') and not a.startswith('--timeout=')]
    args = [a for a in args if a != '--test']

    games = parse_games(filepath)

    if not args:
        # Print all
        for i, (name, payload) in enumerate(games, 1):
            print(f"\n{'='*60}")
            print(f"GAME {i}: {name}")
            print(f"{'='*60}")
            print(json.dumps(payload, indent=2))
            if do_test:
                test_game(payload, f"Game {i}: {name}", solvers=selected_solvers, time_limit=time_limit)
    else:
        indices = [int(a) - 1 for a in args]
        for idx in indices:
            if 0 <= idx < len(games):
                name, payload = games[idx]
                print(json.dumps(payload, indent=2))
                if do_test:
                    test_game(payload, name, solvers=selected_solvers, time_limit=time_limit)
            else:
                print(f"Game {idx+1} not found. Available: 1-{len(games)}", file=sys.stderr)


if __name__ == '__main__':
    main()
