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
N = GW * GH
START = [(2, 0), (1, 0), (0, 0)]
DIR_LIST = list(DIRS)
# Full games solved offline by solver.py (dynamic Hamiltonian cycle): direction codes and food order.
SNAKE_GAMES = pickle.load(open(os.environ.get("GAME_SNAKE", os.path.join(HERE, "snake_games.bin")), "rb"))
BANDS = 16
HEAD0, APPLE = 97, 101
SWEEP = 24            # cells re-checked for a gradient change per tick: the cost does not depend on the length


def snake_game():
    sn = sp["snake"]
    strip = raw["snake_strip"]
    s = {}

    def xy(p):
        return p[0] * CS, OY + p[1] * CS

    def key_at(i, n):
        # Sprite for body index i of n: the head faces away from its neck, the rest is a gradient by index.
        body = s["body"]
        if i == 0:
            return HEAD0 + DIRS[(body[0][0] - body[1][0], body[0][1] - body[1][1])]
        return 1 + s["hue"] * BANDS + i * BANDS // n

    def show(p, key):
        if s["shown"].get(p) != key:
            blit(sn[key], *xy(p))
            s["shown"][p] = key

    def reset():
        clear()
        fill_rect(0, OY - 8, W, 4, 0x4208)
        blit(sp["label"][LBL_LENGTH], 40, 40)
        body = START[:]
        moves, foods = random.choice(SNAKE_GAMES)
        s.update(body=body, occ=set(body), phase="play", t=0, acc=0.0, hue=0, shown={}, nxt=None, count=-1,
                 moves=moves, foods=foods, k=0, fk=0, cursor=0, partial=False, added=[], removed=[])
        place_food()
        for i, p in enumerate(body):
            show(p, key_at(i, len(body)))

    def hud():
        if s["count"] != len(s["body"]):
            s["count"] = len(s["body"])
            draw_num("%d/%d" % (s["count"], N), 360, 20, 8)

    def place_food():
        s["food"] = s["foods"][s["fk"]] if s["fk"] < len(s["foods"]) else None
        s["fk"] += 1
        if s["food"]:
            blit(sn[APPLE], *xy(s["food"]))

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
        if n == s["food"]:
            place_food()
        else:
            tail = body.pop()
            occ.discard(tail)
            s["removed"].append(tail)
        body.insert(0, n)
        occ.add(n)
        s["added"].append(n)
        return True

    def draw_changes(budget):
        # Only what changed is drawn: the cells entered this tick, the old head, the freed tail cells, and a
        # fixed-size slice of the body whose gradient band may have shifted. The sweep makes the gradient lag a
        # little behind a fast snake instead of costing a frame, which a slow board cannot afford.
        body, shown, live = s["body"], s["shown"], s["occ"]
        n = len(body)
        for p in s["removed"]:
            if p not in live and p in shown:
                fill_rect(*xy(p), CS, CS, 0)
                del shown[p]
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
        if n != s["food"]:
            t, q = body[-1], body[-2]
            tx, ty = xy(t)
            qx, qy = q[0] - t[0], q[1] - t[1]
            if qx:
                fill_rect(tx if qx > 0 else tx + CS - ln, ty, ln, CS, 0)
            else:
                fill_rect(tx, ty if qy > 0 else ty + CS - ln, CS, ln, 0)

    def step():
        s["t"] += 1
        if s["phase"] == "play":
            # 0.6 cells per tick while short (smooth sub-cell crawl) up to 1.3 when the board is nearly full.
            rate = 18 + 22 * (len(s["body"]) / N) ** 2
            s["acc"] += rate / 30
            while s["acc"] >= 1 and s["phase"] == "play":
                s["acc"] -= 1
                if s["food"] is None:
                    s["phase"], s["t"] = "win", 0
                elif not move():
                    s["phase"], s["t"] = "dead", 0
                    center(LBL_OVER)
            s["partial"] = s["phase"] == "play" and rate < 30
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

    reset()
    return step


make = snake_game
