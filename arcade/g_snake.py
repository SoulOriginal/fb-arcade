# Snake: replay of games solved offline (solver.py), gradient body, smooth crawl while short.
from fbcore import *

core = load_bundle("games.bin")
sp = {k: v for k, v in core.items() if k != "snake_strip"}
raw = {"snake_strip": core["snake_strip"]}
LBL_LENGTH, LBL_SCORE, LBL_LINES, LBL_LEVEL, LBL_NEXT, LBL_WIN, LBL_OVER, LBL_APPLES = range(8)
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
# Games solved offline by solver.py (dynamic Hamiltonian cycle over the free 2x2 blocks): direction codes, the apple
# sequence (cell and kind: 0 grows the snake, 1 shortens it) and the brick blocks of the board.
SNAKE_GAMES = pickle.load(open(os.environ.get("GAME_SNAKE", os.path.join(HERE, "snake_games.bin")), "rb"))
BANDS = 16
NS = 103              # sprites per floor variant: empty floor, 96 body, 4 heads, 2 apples
HEAD0, APPLE0 = 97, 101
SWEEP = 24            # cells re-checked for a gradient change per tick: the cost does not depend on the length
RATE = 22             # moves per second: about 0.7 cell per tick, so the crawl between cells stays smooth


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
            blit(sp["snake_brick"][0], bx * 2 * CS, OY + by * 2 * CS)

    def reset():
        clear()
        fill_rect(0, OY - 8, W, 4, 0x4208)
        blit(sp["label"][LBL_LENGTH], 40, 40)
        blit(sp["label"][LBL_APPLES], 720, 40)
        body = START[:]
        moves, foods, bricks = random.choice(SNAKE_GAMES)
        s.update(body=body, occ=set(body), phase="play", t=0, acc=0.0, hue=0, shown={}, nxt=None, count=-1,
                 moves=moves, foods=foods, k=0, fk=0, cursor=0, partial=False, added=[], removed=[], eaten=-1)
        draw_board(bricks)
        place_food()
        for i, p in enumerate(body):
            show(p, key_at(i, len(body)))

    def hud():
        if s["count"] != len(s["body"]) or s["eaten"] != s["shown_eaten"]:
            s["count"] = len(s["body"])
            s["shown_eaten"] = s["eaten"]
            draw_num(str(s["count"]), 360, 20, 4)
            draw_num("%d/%d" % (max(0, s["eaten"]), len(s["foods"])), 1060, 20, 8)

    def place_food():
        s["eaten"] += 1
        s["food"] = s["foods"][s["fk"]] if s["fk"] < len(s["foods"]) else None
        s["fk"] += 1
        f = s["food"]
        if f:
            blit(sn[APPLE0 + f[2] + variant(f)], *xy(f))

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
        food = s["food"]
        eat = food is not None and n == food[:2]
        # A growing apple keeps the tail, a shortening one drops two cells, a plain step drops one. The tail goes
        # first: the head may step into the very cell the tail is leaving.
        drop = (2 if food[2] else 0) if eat else 1
        for _ in range(drop):
            tail = body.pop()
            occ.discard(tail)
            s["removed"].append(tail)
        body.insert(0, n)
        occ.add(n)
        s["added"].append(n)
        if eat:
            place_food()
        return True

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
        food = s["food"]
        if not (food is not None and n == food[:2] and not food[2]):
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
                if s["food"] is None:
                    s["phase"], s["t"] = "win", 0
                elif not move():
                    s["phase"], s["t"] = "dead", 0
                    center(LBL_OVER)
            s["partial"] = s["phase"] == "play" and s["food"] is not None
            draw_changes(SWEEP)
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

    s["shown_eaten"] = -2
    reset()
    return step


make = snake_game
