"""V3 protocol: official best practices applied to both games.

Sources:
- TypeSafe "How to build": decompose questions atomically, fan-out in ONE call,
  compose with code, keep deterministic work in code.
- TypeSafe "Composite scoring": combine atomic answers with fixed weights.
- TypeSafe "Parallel questions" cookbook: batching N questions = same answers,
  ~10x faster/cheaper.
- NanoJev author's game renderers (build_navigation_v3.py / snake_game.py):
  strategy-hierarchy instructions, column rulers, per-option destination
  coordinates, forced moves executed by code without a model call.

Design per game:

TETRIS (one call per piece):
  action      choice : instructions encode the POLICY HIERARCHY:
                        (1) maximize lines cleared now; (2) among ties do not
                        create holes; (3) among ties keep the stack low;
                        ties are equivalent. Option ids r{o}c{col}; each option
                        description = pure placement facts (orientation mask,
                        destination cells, resulting clears/holes/height).
  risk_deep   noul   : "Would this placement leave covered empty cells?"
  (fan-out extras are free per parallel-questions cookbook)

1024 (one call per turn):
  action      choice : hierarchy: (1) maximize merges+score now; (2) keep empty
                        cells high; ties equivalent.
  danger      noul   : "Does this board risk getting stuck soon?"
  best_value  score  : 3-level position quality (strong/neutral/weak) — recorded,
                        used for tie-breaking in code when action probs are flat.
"""
from __future__ import annotations

import json

# ---------------------------------------------------------------- Tetris v3

TETRIS_INSTR = (
    "Choose the placement that best follows this policy, in priority order: "
    "(1) maximize the number of lines cleared by this drop; "
    "(2) among ties, do not create covered empty cells (holes); "
    "(3) among ties, keep every column height low and even (low stack-height sum, "
    "low max column, low bumpiness between neighboring columns) so future pieces "
    "still fit; a flat low surface is better than one tall column with a pit. "
    "Placements that tie on all criteria are equivalent."
)


def tetris_state_v3(env):
    w, h = env.w, env.h
    ruler = "columns: " + " ".join(str(c % 10) for c in range(w))
    rows = [f"row {r}: " + " ".join("#" if v else "." for v in env.grid[r]) for r in range(h)]
    shapes = "; ".join(
        f"{oi}: " + "/".join("".join("#" if v else "." for v in mr) for mr in mask)
        for oi, mask in enumerate(_orients(env)))
    holes = env._holes()
    heights = _col_heights(env)
    nxt = env.next_piece()
    from games.tetris_v2 import PIECES_V2
    nxt_shapes = ""
    if nxt:
        nxt_shapes = "; ".join(
            f"{oi}: " + "/".join("".join("#" if v else "." for v in mr) for mr in mask)
            for oi, mask in enumerate(PIECES_V2[nxt]))
    return "\n".join([
        "Tetris state:",
        f"Grid {w}x{h}. Coordinates are zero-based (row,column); row 0 is the top. "
        "A full row clears and disappears; pieces hard-drop and never move again.",
        f"Current piece: {env.current}. Allowed orientations (index: row masks): {shapes}.",
        f"Next piece in the queue (plan one move ahead): {nxt}. Orientations: {nxt_shapes}.",
        f"Board holes (covered empties): {holes}. Column heights: {json.dumps(heights)}. "
        f"Stack-height sum: {sum(heights)}; bumpiness: {sum(abs(heights[i]-heights[i+1]) for i in range(w-1))}. "
        f"Lines cleared so far: {env.lines}. Keep the stack flat and low so future pieces still fit.",
        ruler,
        *rows,
    ])


def _orients(env):
    from games.tetris_v2 import PIECES_V2
    return PIECES_V2[env.current]


def _col_heights(env):
    out = []
    for c in range(env.w):
        hh = 0
        for r in range(env.h):
            if env.grid[r][c]:
                hh = env.h - r
                break
        out.append(hh)
    return out


def tetris_state_compact(env):
    """Compact state for token-limited engines (nanojev max_length=512):
    trims empty rows, drops the next-piece preview and feature sentence."""
    w, h = env.w, env.h
    first_filled = next((r for r in range(h) if any(env.grid[r])), h)
    top = max(0, first_filled - 2)
    rows = [f"row {r}: " + " ".join("#" if v else "." for v in env.grid[r]) for r in range(top, h)]
    shapes = "; ".join(
        f"{oi}: " + "/".join("".join("#" if v else "." for v in mr) for mr in mask)
        for oi, mask in enumerate(_orients(env)))
    return "\n".join([
        "Tetris state:",
        f"Grid {w}x{h} (showing rows {top}-{h-1}; rows above are empty). Row 0 is the top. Full rows clear.",
        f"Current piece: {env.current}. Orientations: {shapes}.",
        *rows,
    ])


def tetris_questions_v3(env):
    desc = env.action_descriptions()
    questions = {
        "action": {"type": "choice", "instructions": TETRIS_INSTR, "criteria": desc},
        "hole_free_exists": {
            "type": "noul",
            "instructions": "Does at least one offered placement keep the total hole count "
                            "from increasing (holes after <= holes before)?"},
    }
    return questions


# ---------------------------------------------------------------- 1024 v3

GAME1024_INSTR = (
    "Choose the slide that best follows this policy, in priority order: "
    "(1) maximize the points gained and the number of merges now, preferring the "
    "biggest merged tile when merge counts tie; "
    "(2) among ties, keep the number of empty cells high. "
    "Slides that tie on both are equivalent."
)

SCORE_LEVELS = [
    "Weak: scattered small tiles, low merge potential, few empty cells",
    "Neutral: some aligned equal tiles, moderate empty cells",
    "Strong: multiple mergeable pairs or a large tile formed, many empty cells",
]


def game1024_state_v3(env):
    rows = [f"row {r}: " + " ".join(f"{v}" if v else "." for v in env.grid[r]) for r in range(env.size)]
    return "\n".join([
        "1024 state:",
        f"Grid 4x4. Coordinates are zero-based (row,column). Equal tiles that collide "
        "merge once into their sum; after a changing slide a new 2 spawns in a random "
        "empty cell. Goal: build a 1024 tile. The game ends when no slide changes the board.",
        f"Score: {env.score}. Largest tile: {env.max_tile}.",
        "columns: 0 1 2 3",
        *rows,
    ])


def game1024_questions_v3(env):
    desc = env.action_descriptions()
    questions = {
        "action": {"type": "choice", "instructions": GAME1024_INSTR, "criteria": desc},
        "stuck_risk": {
            "type": "noul",
            "instructions": "If no slide merges tiles on this board, does the position risk "
                            "ending the game soon (few empty cells, no adjacent equal tiles)?"},
    }
    return questions


# ---------------------------------------------------------------- composite scoring

def compose_tetris(action_ans, noul_ans, legal, desc):
    """Code-side composition per TypeSafe composite-scoring pattern.
    Priority: use the choice argmax; if its margin is razor thin (<0.05 over the
    runner-up) AND the noul says a hole-free placement exists, re-rank legal
    options by (clears desc, holes asc, height-sum asc, bumpiness asc) parsed
    from the option descriptions."""
    probs = action_ans.get("probabilities") or {}
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    choice = action_ans.get("choice")
    if choice not in legal:
        choice = None
    margin = (ranked[0][1] - ranked[1][1]) if len(ranked) >= 2 and choice else 1.0
    hole_free_available = bool((noul_ans or {}).get("noul", 0) > 0.5)
    if choice and (margin >= 0.05 or not hole_free_available):
        return choice, {"rule": "argmax", "margin": round(margin, 3)}
    # deterministic re-rank from placement facts in the descriptions
    import re

    def parse(a, pat, cast=int):
        m = re.search(pat, desc.get(a, ""))
        return cast(m.group(1)) if m else None

    def key(a):
        d = desc.get(a, "")
        clears = sum(d.count(f"clears {n}") * n for n in (1, 2, 3, 4))
        holes = parse(a, r"total holes (\d+)")
        agg = parse(a, r"stack height sum (\d+)")
        bump = parse(a, r"bumpiness (\d+)")
        return (-clears, holes if holes is not None else 99,
                agg if agg is not None else 999, bump if bump is not None else 999)
    best = sorted(legal, key=key)[0]
    return best, {"rule": "rerank", "margin": round(margin, 3), "hole_free": hole_free_available}


def compose_1024(action_ans, noul_ans, legal, desc):
    """Same composite idea for 1024: argmax unless razor-thin AND stuck risk high,
    then re-rank by (merges, score, empties) parsed from the option descriptions."""
    probs = action_ans.get("probabilities") or {}
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    choice = action_ans.get("choice")
    if choice not in legal:
        choice = None
    margin = (ranked[0][1] - ranked[1][1]) if len(ranked) >= 2 and choice else 1.0
    stuck = bool((noul_ans or {}).get("noul", 0) > 0.5)
    if choice and (margin >= 0.05 or not stuck):
        return choice, {"rule": "argmax", "margin": round(margin, 3)}
    def key(a):
        d = desc.get(a, "")
        merges = int(d.split(" merge")[0].split(": ")[-1]) if " merge" in d else 0
        pts = int(d.split("+")[1].split(" points")[0]) if "+" in d else 0
        empt = int(d.split(" empty cells after")[0].rsplit(" ", 1)[-1]) if "empty cells after" in d else 0
        return (-merges, -pts, -empt)
    best = sorted(legal, key=key)[0]
    return best, {"rule": "rerank", "margin": round(margin, 3), "stuck_risk": stuck}
