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


CS, OY = 48, 120
DIRS = {(1, 0): 0, (-1, 0): 1, (0, 1): 2, (0, -1): 3}
GW, GH = 40, 20
N = GW * GH
START = [(2, 0), (1, 0), (0, 0)]
DIR_LIST = list(DIRS)
# Full games solved offline by solver.py (dynamic Hamiltonian cycle): direction codes and food order.
SNAKE_GAMES = pickle.load(open(os.environ.get("GAME_SNAKE", os.path.join(HERE, "snake_games.bin")), "rb"))
BANDS = 16
HEAD0, APPLE = 97, 101


def snake_game():
    sn = sp["snake"]
    strip = raw["snake_strip"]
    s = {}

    def xy(p):
        return p[0] * CS, OY + p[1] * CS

    def reset():
        clear()
        fill_rect(0, OY - 8, W, 4, 0x4208)
        blit(sp["label"][LBL_LENGTH], 40, 40)
        body = START[:]
        moves, foods = random.choice(SNAKE_GAMES)
        s.update(body=body, occ=set(body), phase="play", t=0, acc=0.0, hue=0, shown={}, nxt=None, count=-1,
                 moves=moves, foods=foods, k=0, fk=0)
        place_food()

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
            occ.discard(body.pop())
        body.insert(0, n)
        occ.add(n)
        return True

    def draw_body():
        # Gradient from the head to the tail: only cells whose band changed are redrawn.
        body, shown = s["body"], s["shown"]
        skip = body[-1] if s["partial"] else None
        want = {}
        n = len(body)
        for i, p in enumerate(body):
            if i == 0:
                d = (p[0] - body[1][0], p[1] - body[1][1])
                want[p] = HEAD0 + DIRS[d]
            else:
                want[p] = 1 + s["hue"] * BANDS + i * BANDS // n
        for p in [p for p in shown if p not in want]:
            fill_rect(*xy(p), CS, CS, 0)
            del shown[p]
        for p, k in want.items():
            if shown.get(p) != k and p != skip:
                blit(sn[k], *xy(p))
                shown[p] = k

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
            fill_rect(x if hx > 0 else x + CS - ln, y + 2, ln, CS - 4, col)
        else:
            fill_rect(x + 2, y if hy > 0 else y + CS - ln, CS - 4, ln, col)
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
            # Slow and smooth while short, fast once the long walks along the route start.
            rate = 20 + 1500 * (len(s["body"]) / N) ** 2
            s["acc"] += rate / 30
            s["partial"] = False
            while s["acc"] >= 1 and s["phase"] == "play":
                s["acc"] -= 1
                if s["food"] is None:
                    s["phase"], s["t"] = "win", 0
                elif not move():
                    s["phase"], s["t"] = "dead", 0
                    center(LBL_OVER)
            if s["phase"] == "play":
                s["partial"] = rate < 45
                draw_body()
                if s["partial"]:
                    crawl(s["acc"])
                hud()
            elif s["phase"] == "win":
                s["partial"] = False
                draw_body()
                hud()
        elif s["phase"] == "win":
            s["partial"] = False
            if s["t"] % 3 == 0 and s["t"] < 150:
                s["hue"] = (s["hue"] + 1) % 6
                draw_body()
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
