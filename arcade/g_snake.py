# Snake: replay of games solved offline (solver.py), gradient body, smooth crawl while short.
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


CS, OY = 80, 120
DIRS = {(1, 0): 0, (-1, 0): 1, (0, 1): 2, (0, -1): 3}
GW, GH = 24, 12
START = [(2, 0), (1, 0), (0, 0)]
DIR_LIST = list(DIRS)
# Games solved offline by solver.py (dynamic Hamiltonian cycle over the free 2x2 blocks): direction codes, apple events
# and the brick blocks of the board. An event is (move, cell, kind, expires): kind 0 red apple (grows the snake),
# 1 blue apple (shortens it by one), 2 golden apple (bonus); kind -1 removes the apple at that cell.
SNAKE_GAMES = pickle.load(open(os.environ.get("GAME_SNAKE", os.path.join(HERE, "snake_games.bin")), "rb"))
POINTS = (15, -10, 100)
BANDS = 16
NS = 104              # sprites per floor variant: empty floor, 96 body, 4 heads, 3 apples
HEAD0, APPLE0 = 97, 101
SWEEP = 24            # cells re-checked for a gradient change per tick: the cost does not depend on the length
RATE = 22             # moves per second: about 0.7 cell per tick, so the crawl between cells stays smooth
BLINK = 24            # an apple that is about to disappear blinks for its last moves


def mirrored(game, fx, fy):
    # Every stored game can be flipped horizontally and/or vertically, which turns each board into four different
    # ones. Direction codes: 0 right, 1 left, 2 down, 3 up; blocks are 2x2 cells on a 12x6 grid.
    moves, events, bricks = game
    swap = {0: 1 if fx else 0, 1: 0 if fx else 1, 2: 3 if fy else 2, 3: 2 if fy else 3}
    cell = lambda c: ((GW - 1 - c[0]) if fx else c[0], (GH - 1 - c[1]) if fy else c[1])
    return (bytes(swap[m] for m in moves),
            [(k, cell(c), kind, exp) for k, c, kind, exp in events],
            [((GW // 2 - 1 - bx) if fx else bx, (GH // 2 - 1 - by) if fy else by) for bx, by in bricks],
            [cell(c) for c in START])


def snake_game():
    sn = sp["snake"]
    strip = raw["snake_strip"]
    s = {}

    def xy(p):
        return p[0] * CS, OY + p[1] * CS

    def variant(p):
        return ((p[0] & 1) + 2 * (p[1] & 1)) * NS

    def key_at(i, n):
        # Sprite for body index i of n: the head faces away from its neck, the rest is a gradient by index.
        body = s["body"]
        if i == 0:
            return HEAD0 + DIRS[(body[0][0] - body[1][0], body[0][1] - body[1][1])]
        return 1 + s["hue"] * BANDS + i * BANDS // n

    def show(p, key):
        if s["shown"].get(p) != key:
            blit(sn[key + variant(p)], *xy(p))
            s["shown"][p] = key

    def erase(p):
        blit(sn[variant(p)], *xy(p))
        s["shown"].pop(p, None)

    def patch_floor(p, x0, y0, w, h):
        # Restore a cell-local rectangle from the floor tile (used while the tail is eaten away during a crawl).
        tile = sn[variant(p)][2]
        X, Y = xy(p)
        for j in range(y0, y0 + h):
            write_row(Y + j, tile[j][x0 * 2:(x0 + w) * 2], X + x0)

    def draw_board(bricks):
        # Two full-width scanline sets (even and odd cell rows) cover the whole floor in 960 row writes.
        lines = []
        for yp in (0, 1):
            lines.append([b"".join(sn[((x & 1) + 2 * yp) * NS][2][j] for x in range(GW)) for j in range(CS)])
        for y in range(GH):
            for j in range(CS):
                write_row(OY + y * CS + j, lines[y & 1][j])
        for bx, by in bricks:
            blit(sp["brick"][0], bx * 2 * CS, OY + by * 2 * CS)

    def draw_apple(c, kind, visible):
        blit(sn[(APPLE0 + kind if visible else 0) + variant(c)], *xy(c))

    def advance_events():
        # Apples spawn and vanish exactly as the solver scheduled them, before the move with that index.
        ev = s["events"]
        while s["ev_i"] < len(ev) and ev[s["ev_i"]][0] <= s["k"]:
            _, c, kind, exp = ev[s["ev_i"]]
            s["ev_i"] += 1
            if kind >= 0:
                s["apples"][c] = [kind, exp, True]
                draw_apple(c, kind, True)
            else:
                s["apples"].pop(c, None)
                if c not in s["occ"]:
                    erase(c)

    def reset():
        clear()
        fill_rect(0, OY - 8, W, 4, 0x4208)
        blit(sp["label"][LBL_LENGTH], 40, 40)
        blit(sp["label"][LBL_SCORE], 760, 40)
        moves, events, bricks, body = mirrored(random.choice(SNAKE_GAMES), random.random() < 0.5, random.random() < 0.5)
        s.update(body=body, occ=set(body), phase="play", t=0, acc=0.0, hue=0, shown={}, nxt=None, count=-1,
                 moves=moves, events=events, k=0, ev_i=0, apples={}, cursor=0, partial=False, added=[], removed=[],
                 score=0, shown_score=-1)
        draw_board(bricks)
        advance_events()
        for i, p in enumerate(body):
            show(p, key_at(i, len(body)))

    def hud():
        if s["count"] != len(s["body"]):
            s["count"] = len(s["body"])
            draw_num(str(s["count"]), 360, 20, 4)
        if s["shown_score"] != s["score"]:
            s["shown_score"] = s["score"]
            draw_num(str(s["score"]), 1100, 20, 7)

    def next_cell():
        if s["nxt"] is None:
            dx, dy = DIR_LIST[s["moves"][s["k"]]]
            s["nxt"] = (s["body"][0][0] + dx, s["body"][0][1] + dy)
        return s["nxt"]

    def move():
        body, occ = s["body"], s["occ"]
        n = next_cell()
        s["nxt"] = None
        s["k"] += 1
        if n in occ and n != body[-1]:
            return False
        apple = s["apples"].pop(n, None)
        # A red or golden apple keeps the tail, a blue one drops two cells, a plain step drops one. The tail goes
        # first: the head may step into the very cell the tail is leaving.
        drop = (2 if apple[0] == 1 else 0) if apple else 1
        for _ in range(drop):
            tail = body.pop()
            occ.discard(tail)
            s["removed"].append(tail)
        body.insert(0, n)
        occ.add(n)
        s["added"].append(n)
        if apple:
            s["score"] = max(0, s["score"] + POINTS[apple[0]])
        advance_events()
        return True

    def blink_apples():
        for c, a in s["apples"].items():
            left = a[1] - s["k"]
            visible = left > BLINK or (left // 3) % 2 == 0
            if visible != a[2]:
                a[2] = visible
                draw_apple(c, a[0], visible)

    def draw_changes(budget):
        # Only what changed is drawn: the cells entered this tick, the old head, the freed tail cells, and a
        # fixed-size slice of the body whose gradient band may have shifted. The sweep makes the gradient lag a
        # little behind a fast snake instead of costing a frame, which a slow board cannot afford.
        body, shown, live = s["body"], s["shown"], s["occ"]
        n = len(body)
        for p in s["removed"]:
            if p not in live and p in shown:
                erase(p)
        m = len(s["added"])
        for j, p in enumerate(s["added"]):
            i = m - 1 - j
            if i < n and body[i] == p:
                show(p, key_at(i, n))
        if 0 < m < n:
            show(body[m], key_at(m, n))
        skip = body[-1] if s["partial"] else None
        for _ in range(min(budget, n)):
            i = s["cursor"] % n
            s["cursor"] += 1
            p = body[i]
            if p != skip:
                show(p, key_at(i, n))
        s["added"] = []
        s["removed"] = []

    def crawl(frac):
        # Sub-cell motion: the head grows into the next cell while the tail cell is eaten away.
        body = s["body"]
        n = next_cell()
        ln = int(frac * CS)
        if ln <= 0:
            return
        x, y = xy(n)
        hx, hy = n[0] - body[0][0], n[1] - body[0][1]
        col = strip[s["hue"]]
        if hx:
            fill_rect(x if hx > 0 else x + CS - ln, y + 3, ln, CS - 6, col)
        else:
            fill_rect(x + 3, y if hy > 0 else y + CS - ln, CS - 6, ln, col)
        apple = s["apples"].get(n)
        if not (apple and apple[0] != 1):
            t, q = body[-1], body[-2]
            qx, qy = q[0] - t[0], q[1] - t[1]
            if qx:
                patch_floor(t, 0 if qx > 0 else CS - ln, 0, ln, CS)
            else:
                patch_floor(t, 0, 0 if qy > 0 else CS - ln, CS, ln)

    def step():
        s["t"] += 1
        if s["phase"] == "play":
            s["acc"] += RATE / 30
            while s["acc"] >= 1 and s["phase"] == "play":
                s["acc"] -= 1
                if s["k"] >= len(s["moves"]):
                    s["phase"], s["t"] = "win", 0
                elif not move():
                    s["phase"], s["t"] = "dead", 0
                    center(LBL_OVER)
            s["partial"] = s["phase"] == "play" and s["k"] < len(s["moves"])
            draw_changes(SWEEP)
            blink_apples()
            if s["partial"]:
                crawl(s["acc"])
            hud()
        elif s["phase"] == "win":
            s["partial"] = False
            if s["t"] % 9 == 0 and s["t"] < 150:
                s["hue"] = (s["hue"] + 1) % 6
            if s["t"] < 150:
                draw_changes(96)
            if s["t"] == 150:
                center(LBL_WIN)
            if s["t"] > 400:
                return True
        elif s["t"] > 90:
            reset()
        return False

    reset()
    return step


make = snake_game
