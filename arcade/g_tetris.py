# Tetris played by a two-ply search bot until 150 lines.
from fbcore import *

core = load_bundle("games.bin")
sp = {k: v for k, v in core.items() if k != "snake_strip"}
raw = {"snake_strip": core["snake_strip"]}
LBL_LENGTH, LBL_SCORE, LBL_LINES, LBL_LEVEL, LBL_NEXT, LBL_WIN, LBL_OVER = range(7)
GRAY = 0xD69A


def draw_num(text, x, y, width):
    fill_rect(x, y, width * 40, 80, 0)
    for i, ch in enumerate(text):
        blit(sp["glyph"]["0123456789/".index(ch)], x + i * 40, y)


def center(label_index):
    s = sp["label"][label_index]
    blit(s, (W - s[0]) // 2, (H - s[1]) // 2)


TC, TR, GOAL = 10, 20, 150
FULL = (1 << TC) - 1
SHAPES = {1: [(0, 1), (1, 1), (2, 1), (3, 1)], 2: [(1, 0), (2, 0), (1, 1), (2, 1)], 3: [(1, 0), (0, 1), (1, 1), (2, 1)],
          4: [(1, 0), (2, 0), (0, 1), (1, 1)], 5: [(0, 0), (1, 0), (1, 1), (2, 1)], 6: [(0, 0), (0, 1), (1, 1), (2, 1)],
          7: [(2, 0), (0, 1), (1, 1), (2, 1)]}


def _norm(cells):
    mx, my = min(x for x, y in cells), min(y for x, y in cells)
    return tuple(sorted((x - mx, y - my) for x, y in cells))


def _rotations(cells):
    seen, cur = [], _norm(cells)
    for _ in range(4):
        if cur not in seen:
            seen.append(cur)
        cur = _norm([(-y, x) for x, y in cur])
    return seen


ROT = {k: _rotations(v) for k, v in SHAPES.items()}
LINE_POINTS = (0, 40, 100, 300, 1200)


def fits(g, shape, x, y):
    for cx, cy in shape:
        gx, gy = x + cx, y + cy
        if gx < 0 or gx >= TC or gy >= TR or (gy >= 0 and g[gy] >> gx & 1):
            return False
    return True


def settle(g, shape, x, y):
    ng = g[:]
    for cx, cy in shape:
        ng[y + cy] |= 1 << (x + cx)
    keep = [r for r in ng if r != FULL]
    lines = TR - len(keep)
    return [0] * lines + keep, lines


def evaluate(g, lines):
    # Well-known weights: low and flat, no holes, many lines.
    seen, holes, heights = 0, 0, [0] * TC
    for r in range(TR):
        row = g[r]
        new = row & ~seen
        if new:
            for c in range(TC):
                if new >> c & 1:
                    heights[c] = TR - r
        holes += bin(seen & ~row).count("1")
        seen |= row
    bump = sum(abs(heights[i] - heights[i + 1]) for i in range(TC - 1))
    return -0.51 * sum(heights) + 0.76 * lines - 0.36 * holes - 0.18 * bump


def reachable(g, kind):
    # BFS over (x, y, rotation) with moves C (rotate), L, R, D: finds tucks and slides, not only drops.
    rots = ROT[kind]
    x0 = (TC - (max(c[0] for c in rots[0]) + 1)) // 2
    start = (x0, 0, 0)
    if not fits(g, rots[0], x0, 0):
        return None, []
    par, queue, locks = {start: None}, [start], []
    for st in queue:
        x, y, r = st
        if not fits(g, rots[r], x, y + 1):
            locks.append(st)
        for m, ns in (("C", (x, y, (r + 1) % len(rots))), ("L", (x - 1, y, r)), ("R", (x + 1, y, r)), ("D", (x, y + 1, r))):
            if ns not in par and fits(g, rots[ns[2]], ns[0], ns[1]):
                par[ns] = (st, m)
                queue.append(ns)
    return par, locks


def best_drop(g, kind):
    best = None
    for shape in ROT[kind]:
        for x in range(TC - max(c[0] for c in shape)):
            if not fits(g, shape, x, 0):
                continue
            y = 0
            while fits(g, shape, x, y + 1):
                y += 1
            ng, lines = settle(g, shape, x, y)
            v = evaluate(ng, lines)
            if best is None or v > best:
                best = v
    return best


def plan(g, kind, next_kind):
    # Two-ply search: top 10 placements of this piece, each scored with the best drop of the next one.
    par, locks = reachable(g, kind)
    if not locks:
        return None
    rots = ROT[kind]
    scored = []
    for st in locks:
        ng, lines = settle(g, rots[st[2]], st[0], st[1])
        scored.append((evaluate(ng, lines), st, ng))
    scored.sort(key=lambda t: -t[0])
    best = None
    for v1, st, ng in scored[:6]:
        v2 = best_drop(ng, next_kind)
        total = v1 + (v2 if v2 is not None else -1000)
        if best is None or total > best[0]:
            best = (total, st)
    moves, st = [], best[1]
    while par[st]:
        st, m = par[st]
        moves.append(m)
    moves.reverse()
    return moves


def tetris_game():
    cells = sp["tetris"]
    FX, FY = 470, 60
    PX = FX + TC * 48 + 120
    s = {}

    def reset():
        clear()
        fill_rect(FX - 8, FY - 8, 4, TR * 48 + 16, GRAY)
        fill_rect(FX + TC * 48 + 4, FY - 8, 4, TR * 48 + 16, GRAY)
        fill_rect(FX - 8, FY - 8, TC * 48 + 16, 4, GRAY)
        fill_rect(FX - 8, FY + TR * 48 + 4, TC * 48 + 16, 4, GRAY)
        for lbl, y in ((LBL_NEXT, 60), (LBL_SCORE, 380), (LBL_LINES, 560), (LBL_LEVEL, 740)):
            blit(sp["label"][lbl], PX, y)
        s.update(grid=[0] * TR, col=[[0] * TC for _ in range(TR)], lines=0, score=0, level=0, queue=[],
                 cur=None, moves=[], phase="play", acc=0.0, t=0, shown=None, flash=[], hue=0, burst=0)
        hud()
        spawn()

    def hud():
        draw_num(str(s["score"]), PX, 440, 7)
        draw_num("%d/%d" % (s["lines"], GOAL), PX, 620, 7)
        draw_num(str(s["level"]), PX, 800, 7)

    def spawn():
        while len(s["queue"]) < 3:
            bag = list(range(1, 8))
            random.shuffle(bag)
            s["queue"] += bag
        kind = s["queue"].pop(0)
        nxt = s["queue"][0]
        fill_rect(PX, 140, 4 * 48, 4 * 48, 0)
        for cx, cy in ROT[nxt][0]:
            blit(cells[nxt], PX + cx * 48, 140 + cy * 48)
        moves = plan(s["grid"], kind, nxt)
        if moves is None:
            s["phase"], s["t"] = "over", 0
            center(LBL_OVER)
            return
        rots = ROT[kind]
        s["cur"] = {"k": kind, "r": 0, "x": (TC - (max(c[0] for c in rots[0]) + 1)) // 2, "y": 0}
        s["moves"] = moves

    def render(view):
        old = s["shown"]
        for r in range(TR):
            for c in range(TC):
                if old is None or old[r][c] != view[r][c]:
                    blit(cells[view[r][c]], FX + c * 48, FY + r * 48)
        s["shown"] = [row[:] for row in view]

    def view(white=None, recolor=0):
        v = [[(k - 1 + recolor) % 7 + 1 if k else 0 for k in row] for row in s["col"]]
        p = s["cur"]
        if p:
            for cx, cy in ROT[p["k"]][p["r"]]:
                v[p["y"] + cy][p["x"] + cx] = p["k"]
        for r in white or ():
            v[r] = [8] * TC
        return v

    def lock():
        p = s["cur"]
        for cx, cy in ROT[p["k"]][p["r"]]:
            s["grid"][p["y"] + cy] |= 1 << (p["x"] + cx)
            s["col"][p["y"] + cy][p["x"] + cx] = p["k"]
        s["cur"] = None
        s["flash"] = [r for r in range(TR) if s["grid"][r] == FULL]
        if s["flash"]:
            s["phase"], s["t"] = "flash", 0
        else:
            spawn()

    def finish_clear():
        n = len(s["flash"])
        keep = [r for r in range(TR) if r not in s["flash"]]
        s["grid"] = [0] * n + [s["grid"][r] for r in keep]
        s["col"] = [[0] * TC for _ in range(n)] + [s["col"][r] for r in keep]
        s["score"] += LINE_POINTS[n] * (s["level"] + 1)
        s["lines"] += n
        s["level"] = s["lines"] // 10
        s["flash"] = []
        hud()
        if s["lines"] >= GOAL:
            s["phase"], s["t"] = "win", 0
        else:
            s["phase"] = "play"
            spawn()

    def do_move():
        p = s["cur"]
        if not s["moves"]:
            lock()
            return
        m = s["moves"].pop(0)
        while m == "D" and s["moves"] and s["moves"][0] == "D" and s["burst"] < 3:
            # Falling is 4x faster than steering: consecutive drops are merged.
            s["burst"] += 1
            p["y"] += 1
            m = s["moves"].pop(0)
        s["burst"] = 0
        if m == "L":
            p["x"] -= 1
        elif m == "R":
            p["x"] += 1
        elif m == "C":
            p["r"] = (p["r"] + 1) % len(ROT[p["k"]])
        else:
            p["y"] += 1

    def step():
        s["t"] += 1
        ph = s["phase"]
        if ph == "play":
            # Rate grows with the level: 30 actions per second at the start, 90 at level 15.
            s["acc"] += min(90, 30 + s["level"] * 4) / 30
            while s["acc"] >= 1 and s["phase"] == "play":
                s["acc"] -= 1
                do_move()
            if s["phase"] == "play":
                render(view())
        elif ph == "flash":
            render(view(s["flash"] if (s["t"] // 2) % 2 == 0 else None))
            if s["t"] >= 9:
                finish_clear()
                render(view())
        elif ph == "win":
            if s["t"] % 3 == 0 and s["t"] < 150:
                render(view(recolor=s["t"] // 3))
            if s["t"] == 150:
                center(LBL_WIN)
            if s["t"] > 400:
                return True
        elif s["t"] > 90:
            reset()
        return False

    reset()
    return step



make = tetris_game
