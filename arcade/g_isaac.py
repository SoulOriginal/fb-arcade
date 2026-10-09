# The Binding of Isaac style roguelike, played by a combat bot: floors of rooms generated like the original (grid growth
# from a start room, dead ends become boss / treasure / shop), single-screen 13x7 rooms with obstacles, enemies and bosses
# with their real attack patterns, tears, bombs, keys, hearts, items. The bot kites, aligns shots, predicts tear lines,
# bombs rocks and secret walls, and runs several lives until the score target.
# Rendering: the room shell (floor + walls) is a pre-drawn byte buffer; moving sprites are run-length sprites composed over
# dirty rectangles in a frame buffer (shadows darken by bit tricks) and only those rectangles are written to the screen.
from fbcore import *
import math
from operator import itemgetter

B = load_bundle("g_isaac.bin")
SPR, HUDS, THEMES, ENV, DOORS = B["spr"], B["hud"], B["themes"], B["env"], B["doors"]
ANCH = B["meta"]["anch"]
CELL, WALL, SW, SH = 100, 80, 1460, 860
RW, RH = 1300, 700                    # room interior in pixels
COLS, ROWS = 13, 7
SX, SY = (W - SW) // 2, 140          # where the shell sits on the screen
FS = SW * 2
TARGET_SCORE = 13000

ISAAC_R = 24
ISAAC_SPEED = 10.5
TEAR_SPEED = 16.0
TEAR_R = 13
ETEAR_SPEED = 9.0
BOMB_FUSE = 52
BLAST_R = 130
DOOR_HALF = 56                        # half width of a doorway lane
DIRS = {"u": (0, -1), "d": (0, 1), "l": (-1, 0), "r": (1, 0)}
OPP = {"u": "d", "d": "u", "l": "r", "r": "l"}
THEME_FLOORS = ["BASEMENT I", "BASEMENT II", "CAVES I", "CAVES II", "DEPTHS I", "DEPTHS II", "WOMB I", "WOMB II"]
rng = random.Random()

# per-kind data: radius, shadow (rx, ry, dy), flyer height, score
KINDS = {
    "fly": (18, (16, 5, 10), 34, 10), "spider": (20, (20, 6, 8), 0, 10), "pooter": (26, (24, 7, 20), 40, 20),
    "gaper": (30, (28, 8, 26), 0, 25), "horf": (30, (28, 8, 22), 12, 25), "clotty": (30, (30, 8, 20), 0, 30),
    "mulligan": (30, (28, 8, 28), 0, 30), "charger": (34, (34, 9, 22), 0, 40), "host": (34, (32, 9, 22), 0, 40),
    "boil": (24, (24, 7, 14), 0, 15),
    "monstro": (70, (86, 22, 56), 0, 0), "duke": (58, (62, 16, 50), 46, 0), "contusion": (58, (62, 16, 46), 0, 0),
    "suture": (38, (40, 11, 32), 0, 0), "larry": (38, (40, 11, 30), 0, 0), "chub": (56, (58, 15, 44), 0, 0),
    "gurdy": (84, (92, 22, 60), 0, 0),
}
BASE_HP = {"fly": 4, "spider": 6, "pooter": 8, "gaper": 10, "horf": 10, "clotty": 15, "mulligan": 13, "charger": 20,
           "host": 15, "boil": 10}
CONTACT = {"fly": 1, "spider": 1, "pooter": 0, "gaper": 2, "horf": 2, "clotty": 2, "mulligan": 0, "charger": 2, "host": 0,
           "boil": 2, "monstro": 2, "duke": 2, "contusion": 2, "suture": 2, "larry": 2, "chub": 2, "gurdy": 2}
COST = {"fly": 1.0, "spider": 1.0, "pooter": 1.5, "gaper": 2.0, "horf": 2.0, "clotty": 2.0, "mulligan": 2.5, "charger": 2.5,
        "host": 2.5, "boil": 1.5}
BOSS_POOL = [["monstro", "duke", "larry"], ["gemini", "chub", "larry", "monstro"], ["gurdy", "gemini", "chub", "duke"],
             ["gurdy", "monstro", "chub", "gemini"]]


# ------------------------------------------------------------------------------------------------ rendering
MASKS = {}


def shadow_mask(n):
    m = MASKS.get(n)
    if m is None:
        m = MASKS[n] = (int.from_bytes(b"\xef\x7b" * n, "little"), int.from_bytes(b"\x61\x08" * n, "little"))
    return m


class Renderer:
    # Items are tuples (sort_y, key, kind, a, x, y, w, h, obj) in shell coordinates (a identifies obj for diffing). kind 0 shadow ellipse,
    # 1 run-length sprite, 2 solid rect. Anything whose tuple changed since last tick makes its old and new
    # rectangle dirty; dirty rectangles are rebuilt from the background and rewritten to the screen.
    def __init__(self):
        self.frame = bytearray(SW * SH * 2)
        self.mv = memoryview(self.frame)
        self.base = bytearray(SW * SH * 2)
        self.bg = bytearray(SW * SH * 2)
        self.bgmv = memoryview(self.bg)
        self.basemv = memoryview(self.base)
        self.prev = {}
        self.extra = []
        self.full = True

    def load_shell(self, shell_bytes):
        self.shell = shell_bytes
        self.base[:] = shell_bytes

    def reset_base(self):
        self.base[:] = self.shell

    def reset_bg(self):
        self.bg[:] = self.base

    def stamp_base(self, spr, x, y):
        draw_runs(self.base, spr, x, y, 0, 0, SW, SH)

    def stamp_both(self, spr, x, y):
        # a decal that appears mid-fight must survive later cell restores, so it goes into the pristine copy too
        draw_runs(self.base, spr, x, y, 0, 0, SW, SH)
        draw_runs(self.bg, spr, x, y, 0, 0, SW, SH)
        self.dirty(x, y, spr[0], spr[1])

    def restore(self, x, y, w, h):
        # put the pristine background back under a rectangle (obstacle removed, door changed)
        for j in range(y, y + h):
            o = j * FS + x * 2
            self.bgmv[o:o + w * 2] = self.basemv[o:o + w * 2]

    def stamp(self, spr, x, y):
        draw_runs(self.bg, spr, x, y, 0, 0, SW, SH)

    def dirty(self, x, y, w, h):
        self.extra.append((x, y, x + w, y + h))

    def render(self, items, to_fb=True):
        prev = self.prev
        cur = {}
        rects = self.extra
        self.extra = []
        if self.full:
            rects = [(0, 0, SW, SH)]
            self.full = False
            prev.clear()
        for it in items:
            sig = it[2:8]
            cur[it[1]] = sig
            p = prev.pop(it[1], None)
            if p is None:
                rects.append((sig[2], sig[3], sig[2] + sig[4], sig[3] + sig[5]))
            elif p != sig:
                rects.append((p[2], p[3], p[2] + p[4], p[3] + p[5]))
                rects.append((sig[2], sig[3], sig[2] + sig[4], sig[3] + sig[5]))
        for p in prev.values():
            rects.append((p[2], p[3], p[2] + p[4], p[3] + p[5]))
        self.prev = cur
        if not rects:
            return
        items.sort(key=itemgetter(0))
        frame, mv, bgmv = self.frame, self.mv, self.bgmv
        for (x0, y0, x1, y1) in merge_rects(rects):
            for j in range(y0, y1):
                o = j * FS
                mv[o + x0 * 2:o + x1 * 2] = bgmv[o + x0 * 2:o + x1 * 2]
            for it in items:
                kind, ix, iy = it[2], it[4], it[5]
                if ix >= x1 or iy >= y1 or ix + it[6] <= x0 or iy + it[7] <= y0:
                    continue
                if kind == 1:
                    draw_runs(frame, it[8], ix, iy, x0, y0, x1, y1)
                elif kind == 0:
                    draw_shadow(frame, ix, iy, it[6], it[7], x0, y0, x1, y1)
                else:
                    draw_rect(frame, ix, iy, it[6], it[7], it[8], x0, y0, x1, y1)
            if to_fb:
                n = (x1 - x0) * 2
                for j in range(y0, y1):
                    o = j * FS + x0 * 2
                    fo = (SY + j) * S + (SX + x0) * 2
                    fb[fo:fo + n] = mv[o:o + n]


def merge_rects(rects):
    out = []
    for r in rects:
        x0, y0, x1, y1 = max(0, r[0]), max(0, r[1]), min(SW, r[2]), min(SH, r[3])
        if x1 <= x0 or y1 <= y0:
            continue
        r = (x0, y0, x1, y1)
        again = True
        while again:
            again = False
            for o in out:
                if r[0] <= o[2] and o[0] <= r[2] and r[1] <= o[3] and o[1] <= r[3]:
                    r = (min(r[0], o[0]), min(r[1], o[1]), max(r[2], o[2]), max(r[3], o[3]))
                    out.remove(o)
                    again = True
                    break
        out.append(r)
    return out


def draw_runs(frame, spr, x, y, cx0, cy0, cx1, cy1):
    w, h, rows = spr
    j0 = max(0, cy0 - y)
    j1 = min(h, cy1 - y)
    if x >= cx0 and x + w <= cx1:
        for j in range(j0, j1):
            base = (y + j) * FS + x * 2
            for rx, d in rows[j]:
                o = base + rx * 2
                frame[o:o + len(d)] = d
        return
    for j in range(j0, j1):
        base = (y + j) * FS
        for rx, d in rows[j]:
            a = x + rx
            b = a + (len(d) >> 1)
            if a >= cx1 or b <= cx0:
                continue
            if a < cx0:
                d = d[(cx0 - a) * 2:]
                a = cx0
            if b > cx1:
                d = d[:(cx1 - a) * 2]
            o = base + a * 2
            frame[o:o + len(d)] = d


def draw_shadow(frame, x, y, w, h, cx0, cy0, cx1, cy1):
    # elliptical dark patch: ~56% brightness via shift-and-mask on whole runs of pixels
    rx, ry = w / 2, h / 2
    cx = x + w / 2
    for j in range(max(y, cy0), min(y + h, cy1)):
        t = (j + 0.5 - (y + ry)) / ry
        hw = rx * math.sqrt(max(0.0, 1 - t * t))
        a = max(int(cx - hw), cx0)
        b = min(int(cx + hw), cx1)
        n = b - a
        if n <= 0:
            continue
        o = j * FS + a * 2
        m1, m2 = shadow_mask(n)
        v = int.from_bytes(frame[o:o + n * 2], "little")
        frame[o:o + n * 2] = (((v >> 1) & m1) + ((v >> 4) & m2)).to_bytes(n * 2, "little")


def draw_rect(frame, x, y, w, h, color, cx0, cy0, cx1, cy1):
    a, b = max(x, cx0), min(x + w, cx1)
    if b <= a:
        return
    row = color * (b - a)
    for j in range(max(y, cy0), min(y + h, cy1)):
        o = j * FS + a * 2
        frame[o:o + len(row)] = row


def rect_key(c):
    return rgb565(*c).to_bytes(2, "little")


FLASHED = {}


def flashed(spr):
    # hit feedback: the sprite lightened halfway to white, computed once per sprite with whole-run integer arithmetic
    f = FLASHED.get(id(spr))
    if f is None:
        w, h, rows = spr
        out = []
        for runs in rows:
            nr = []
            for x, d in runs:
                n = len(d) // 2
                v = int.from_bytes(d, "little")
                inv = (v ^ int.from_bytes(b"\xff\xff" * n, "little")) >> 1
                v += inv & int.from_bytes(b"\xef\x7b" * n, "little")
                nr.append((x, v.to_bytes(n * 2, "little")))
            out.append(tuple(nr))
        f = FLASHED[id(spr)] = ((w, h, out), spr)
    return f[0]


def blit_runs(spr, x, y):
    # run-length sprite straight to the screen (HUD icons on black)
    w, h, rows = spr
    for j in range(h):
        if not 0 <= y + j < H:
            continue
        for rx, d in rows[j]:
            o = (y + j) * S + (x + rx) * 2
            fb[o:o + len(d)] = d


# ------------------------------------------------------------------------------------------------ floor generation
GRID = 9


def gen_floor(depth):
    # Growth rule of the original generator: a new room may only touch ONE existing room, so the floor is a tree whose
    # leaves (dead ends) become the special rooms. The farthest dead end is the boss room.
    target = min(14, int(2.4 * depth + 5 + rng.randint(0, 1)))
    while True:
        cells = {(4, 4)}
        tries = 0
        while len(cells) < target and tries < 4000:
            tries += 1
            c = rng.choice(sorted(cells))
            dx, dy = rng.choice(list(DIRS.values()))
            n = (c[0] + dx, c[1] + dy)
            if n in cells or not (0 <= n[0] < GRID and 0 <= n[1] < GRID):
                continue
            if sum((n[0] + ax, n[1] + ay) in cells for ax, ay in DIRS.values()) != 1:
                continue
            if rng.random() < 0.35:
                continue
            cells.add(n)
        dead = [c for c in cells if c != (4, 4) and sum((c[0] + ax, c[1] + ay) in cells for ax, ay in DIRS.values()) == 1]
        if len(dead) >= 4:
            break
    dist = {(4, 4): 0}
    queue = [(4, 4)]
    for c in queue:
        for ax, ay in DIRS.values():
            n = (c[0] + ax, c[1] + ay)
            if n in cells and n not in dist:
                dist[n] = dist[c] + 1
                queue.append(n)
    dead.sort(key=lambda c: -dist[c])
    kinds = {(4, 4): "start"}
    kinds[dead[0]] = "boss"
    rest = dead[1:]
    rng.shuffle(rest)
    kinds[rest[0]] = "treasure"
    kinds[rest[1]] = "shop"
    for c in cells:
        kinds.setdefault(c, "normal")
    # secret room: an empty cell touching two or more rooms but not the boss room
    secret = None
    cand = []
    for x in range(1, GRID - 1):
        for y in range(1, GRID - 1):
            if (x, y) in cells:
                continue
            nb = [(x + ax, y + ay) for ax, ay in DIRS.values() if (x + ax, y + ay) in cells]
            if len(nb) >= 2 and all(kinds[c] != "boss" for c in nb):
                cand.append((x, y))
    if cand:
        secret = rng.choice(cand)
        kinds[secret] = "secret"
    return kinds, secret


# ------------------------------------------------------------------------------------------------ room layouts
def door_cells():
    return {(6, 0), (6, 1), (6, 6), (6, 5), (0, 3), (1, 3), (12, 3), (11, 3)}


def connected(grid):
    # spikes count as walls here: the bot never walks over them and neither should a layout require it
    free = [(c, r) for r in range(ROWS) for c in range(COLS) if grid[r][c] == "."]
    seen = {(6, 5)}
    stack = [(6, 5)]
    while stack:
        c, r = stack.pop()
        for dx, dy in DIRS.values():
            n = (c + dx, r + dy)
            if 0 <= n[0] < COLS and 0 <= n[1] < ROWS and n not in seen and grid[n[1]][n[0]] == ".":
                seen.add(n)
                stack.append(n)
    return all(p in seen for p in free) and (6, 1) in seen and (1, 3) in seen and (11, 3) in seen and (6, 5) in seen


def gen_layout(kind, depth):
    # Hand-made-feeling layouts built from symmetric motifs. Obstacles never cover door lanes, and every free cell stays
    # reachable (otherwise the bot or an enemy could be sealed off).
    if kind in ("start", "treasure", "shop", "secret"):
        style = rng.choice(["empty", "empty", "corners"]) if kind != "start" else "empty"
    elif kind == "boss":
        style = rng.choice(["empty", "corners", "pillars"])
    else:
        style = rng.choice(["empty", "scatter", "scatter", "pillars", "block", "ring", "corners", "pitcross", "rows",
                            "poop", "spikes", "mirror", "mirror", "fires"])
    reserved = door_cells()
    for _ in range(40):
        g = [["."] * COLS for _ in range(ROWS)]

        def put(c, r, ch, mirror=True):
            if (c, r) in reserved or not (0 <= c < COLS and 0 <= r < ROWS):
                return
            g[r][c] = ch
            if mirror:
                if (COLS - 1 - c, r) not in reserved:
                    g[r][COLS - 1 - c] = ch

        obstacle = rng.choice("RRRRPO") if depth < 3 else rng.choice("RRRPPOF")
        if style == "scatter":
            for _ in range(rng.randint(3, 7)):
                put(rng.randint(0, 6), rng.randint(0, ROWS - 1), "R" if rng.random() < 0.8 else obstacle)
        elif style == "pillars":
            for c in (2, 4, 8, 10):
                for r in (1, 5):
                    put(c, r, obstacle, False)
        elif style == "block":
            for c in range(5, 8):
                for r in range(2, 5):
                    if (c, r) != (6, 3) or rng.random() < 0.5:
                        put(c, r, obstacle, False)
        elif style == "ring":
            for c in range(3, 10):
                for r in (1, 5):
                    put(c, r, obstacle, False)
            for r in range(2, 5):
                put(3, r, obstacle, False)
                put(9, r, obstacle, False)
            g[3][6] = "."
        elif style == "corners":
            for (c, r) in ((1, 1), (2, 1), (1, 2), (1, 5), (2, 5), (1, 4)):
                put(c, r, obstacle)
        elif style == "pitcross":
            for c in range(3, 10):
                put(c, 3, "P", False)
            for r in (1, 2, 4, 5):
                put(6, r, "P", False)
            for c in (6,):
                g[3][c] = "."
            g[3][5] = g[3][7] = "."
        elif style == "rows":
            for c in range(2, 6):
                put(c, 2, obstacle)
                put(c, 4, obstacle)
        elif style == "poop":
            for _ in range(rng.randint(4, 9)):
                put(rng.randint(0, 6), rng.randint(0, ROWS - 1), "O")
        elif style == "spikes":
            for _ in range(rng.randint(5, 10)):
                put(rng.randint(2, 6), rng.randint(1, 5), "S")
            for _ in range(rng.randint(1, 3)):
                put(rng.randint(0, 6), rng.randint(0, ROWS - 1), "R")
        elif style == "mirror":
            for _ in range(rng.randint(4, 9)):
                put(rng.randint(0, 6), rng.randint(0, ROWS - 1), rng.choice("RRRRPOS"))
        elif style == "fires":
            for _ in range(rng.randint(2, 4)):
                put(rng.randint(1, 5), rng.randint(0, ROWS - 1), "F")
            for _ in range(rng.randint(2, 4)):
                put(rng.randint(0, 6), rng.randint(0, ROWS - 1), "R")
        grid = ["".join(r) for r in g]
        if connected(grid):
            return grid
    return ["." * COLS for _ in range(ROWS)]


# ------------------------------------------------------------------------------------------------ items
ITEM_NAMES = {
    "sad_onion": "SAD ONION", "inner_eye": "THE INNER EYE", "brimstone": "BRIMSTONE", "cricket_head": "CRICKETS HEAD",
    "spoon_bender": "SPOON BENDER", "pentagram": "PENTAGRAM", "number_one": "NUMBER ONE", "magic_mushroom": "MAGIC MUSHROOM",
    "ouija_board": "OUIJA BOARD", "roid_rage": "ROID RAGE", "lunch": "LUNCH", "the_halo": "THE HALO",
}
ITEM_POOL = list(ITEM_NAMES)


class Stats:
    # Isaac's tear stats. Formulas follow the community wiki: fire delay from the tears stat, damage with a square root so
    # damage ups have diminishing returns.
    def __init__(self):
        self.tears = 0.0
        self.dmg_up = 0.0
        self.dmg_flat = 0.0
        self.dmg_mult = 1.0
        self.speed = 0.0
        self.range_up = 0.0
        self.triple = False
        self.laser = False
        self.homing = False
        self.spectral = False
        self.rate_mult = 1.0
        self.items = []

    def damage(self):
        return (3.5 * math.sqrt(1.2 * self.dmg_up + 1) + self.dmg_flat) * self.dmg_mult

    def interval(self):
        delay = 16 - 6 * math.sqrt(1.3 * self.tears + 1)
        return max(3.0, (delay + 1) / self.rate_mult)

    def life(self):
        return max(22, 40 + 7 * self.range_up)

    def speed_px(self):
        return ISAAC_SPEED * (1 + 0.12 * self.speed)


def apply_item(g, name):
    s = g.stats
    s.items.append(name)
    if name == "sad_onion":
        s.tears += 0.7
    elif name == "inner_eye":
        s.triple = True
        s.rate_mult *= 0.55
    elif name == "brimstone":
        s.laser = True
        s.rate_mult *= 0.8
    elif name == "cricket_head":
        s.dmg_flat += 0.5
        s.dmg_mult *= 1.3
    elif name == "spoon_bender":
        s.homing = True
    elif name == "pentagram":
        s.dmg_flat += 1.0
    elif name == "number_one":
        s.tears += 1.2
        s.range_up -= 1.5
    elif name == "magic_mushroom":
        s.dmg_mult *= 1.25
        s.speed += 0.3
        s.range_up += 1
        g.maxhp += 2
        g.hp += 2
    elif name == "ouija_board":
        s.spectral = True
        s.tears += 0.2
    elif name == "roid_rage":
        s.speed += 0.5
        s.range_up += 2
    elif name == "lunch":
        g.maxhp += 2
        g.hp += 2
    elif name == "the_halo":
        s.tears += 0.2
        s.dmg_up += 0.3
        s.speed += 0.2
        g.maxhp += 2
        g.hp += 2
    g.maxhp = min(g.maxhp, 24)
    g.hp = min(g.hp, g.maxhp)


# ------------------------------------------------------------------------------------------------ world objects
class Room:
    def __init__(self, pos, kind):
        self.pos, self.kind = pos, kind
        self.grid = None
        self.cleared = kind in ("start", "treasure", "shop", "secret")
        self.visited = False
        self.seen = False
        self.doors = {}       # dir -> 'open' | 'locked' | 'hidden' | 'hole'
        self.pickups = []
        self.pedestals = []
        self.poop = {}
        self.fire = {}
        self.decals = []
        self.bonus = None
        self.trapdoor = False
        self.rubble = set()
        self.mobs = []


class Tear:
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "dmg", "friendly", "big", "spectral", "homing", "id")

    def __init__(self, x, y, vx, vy, life, dmg, friendly, big=False, spectral=False, homing=False):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.age, self.life, self.dmg, self.friendly = 0, life, dmg, friendly
        self.big, self.spectral, self.homing = big, spectral, homing
        self.id = id(self)

    def height(self):
        k = self.age / self.life
        return 34 if k < 0.6 else 34 * (1 - (k - 0.6) / 0.4) ** 1.5 + 4


class Bomb:
    __slots__ = ("x", "y", "t", "id")

    def __init__(self, x, y):
        self.x, self.y, self.t, self.id = x, y, BOMB_FUSE, id(self)


class Pickup:
    __slots__ = ("x", "y", "kind", "price", "t", "id")

    def __init__(self, x, y, kind, price=0):
        self.x, self.y, self.kind, self.price = x, y, kind, price
        self.t = rng.randrange(60)
        self.id = id(self)


class Mob:
    __slots__ = ("kind", "x", "y", "vx", "vy", "hp", "maxhp", "r", "t", "st", "face", "flying", "inv", "contact", "z",
                 "anim", "d", "boss", "hit", "id", "dead", "hidden", "mvx", "mvy")

    def __init__(self, kind, x, y, hp, boss=False):
        self.kind, self.x, self.y = kind, x, y
        self.vx = self.vy = self.mvx = self.mvy = 0.0
        self.hp = self.maxhp = hp
        self.r = KINDS[kind][0]
        self.t = rng.randrange(30, 90)
        self.st = "idle"
        self.face = "d"
        self.flying = kind in ("fly", "pooter", "horf", "duke")
        self.inv = False
        self.contact = CONTACT[kind]
        self.z = KINDS[kind][2]
        self.anim = rng.randrange(8)
        self.d = {}
        self.boss = boss
        self.hit = 0
        self.id = id(self)
        self.dead = False
        self.hidden = False


def cell_center(c, r):
    return c * CELL + CELL // 2, r * CELL + CELL // 2


def to_cell(x, y):
    return int(x // CELL), int(y // CELL)


# ------------------------------------------------------------------------------------------------ game core
DOOR_POS = {"u": (SW // 2 - 70, 0), "d": (SW // 2 - 70, SH - WALL), "l": (0, SH // 2 - 70), "r": (SW - WALL, SH // 2 - 70)}
DOOR_ENTRY = {"u": (RW // 2, RH - 50), "d": (RW // 2, 50), "l": (RW - 50, RH // 2), "r": (50, RH // 2)}
GIB_COL = rect_key((190, 40, 46))


def spr_item(g, key, name, frame, gx, gy, z=0, sort=None):
    # sprite anchored at its ground point (gx, gy) in room coordinates, lifted by z pixels
    s = SPR[name][frame % len(SPR[name])]
    ax, ay = ANCH[name]
    x, y = int(gx) + WALL - ax, int(gy) + WALL - ay - int(z)
    return (gy if sort is None else sort, key, 1, id(s), x, y, s[0], s[1], s)


def shadow_item(key, gx, gy, rx, ry, dy=0):
    return (-1, key, 0, 0, int(gx) + WALL - rx, int(gy) + WALL + dy - ry, rx * 2, ry * 2, None)


class Game:
    def __init__(self):
        self.r = Renderer()
        self.score = 0
        self.run = 0
        self.tick_n = 0
        self.phase = "card"
        self.phase_t = 0
        self.theme_loaded = -1
        self.shell_cache = {}
        self.banner = ("", 0)
        self.hud_key = None
        self.mini_key = None
        self.bot = None
        self.used_items = set()
        self.used_bosses = set()
        self.over = False
        self.prog = None
        self.prog_t = 0
        self.slide = None
        self.end = EndScreen()
        self.new_run()

    # ---------------------------------------------------------------- runs and floors
    def new_run(self):
        self.run += 1
        self.depth = 0
        self.hp = self.maxhp = 6
        self.soul = 0
        self.coins = 0
        self.bombs_n = 1
        self.keys = 0
        self.stats = Stats()
        self.used_items = set()
        self.used_bosses = set()
        self.dying = 0
        self.new_floor()

    def new_floor(self):
        self.depth += 1
        theme = ((self.depth - 1) // 2) % 4
        self.theme = theme
        kinds, secret = gen_floor(self.depth)
        self.rooms = {pos: Room(pos, k) for pos, k in kinds.items()}
        for pos, rm in self.rooms.items():
            for d, (dx, dy) in DIRS.items():
                n = (pos[0] + dx, pos[1] + dy)
                nr = self.rooms.get(n)
                if nr is None:
                    continue
                if rm.kind == "secret" or nr.kind == "secret":
                    rm.doors[d] = "hidden"
                elif (rm.kind == "shop" or nr.kind == "shop") or ((rm.kind == "treasure" or nr.kind == "treasure") and self.depth >= 2):
                    rm.doors[d] = "locked"
                else:
                    rm.doors[d] = "open"
        self.secret_pos = secret
        normal = [p for p, k in kinds.items() if k == "normal"]
        rng.shuffle(normal)
        for i, p in enumerate(normal):
            self.rooms[p].bonus = "key" if i < 2 else ("coins" if i < 4 else None)
        self.floor_start = self.tick_n
        self.cur = None
        self.card_name = THEME_FLOORS[min(self.depth - 1, 7)]
        self.phase = "card"
        self.phase_t = 0
        self.flow_tick = -99
        self.flow = {}
        self.tears, self.bombs_l, self.mobs, self.parts, self.booms = [], [], [], [], []
        self.beam = None
        self.x, self.y, self.vx, self.vy = RW / 2, RH / 2, 0.0, 0.0
        self.face = "d"
        self.walk = 0.0
        self.invuln = 0
        self.cd = 0
        self.charge = 0
        self.hurt_t = 0
        self.shoot_t = 0
        self.move_dir = "d"

    def load_theme(self):
        if self.theme_loaded != self.theme:
            th = THEMES[self.theme]
            if self.theme not in self.shell_cache:
                self.shell_cache[self.theme] = b"".join(th["shell"][2])
            self.r.load_shell(self.shell_cache[self.theme])
            self.theme_loaded = self.theme

    # ---------------------------------------------------------------- rooms
    def enter_room(self, pos, entry):
        rm = self.rooms[pos]
        self.cur = rm
        self.load_theme()
        self.tears, self.bombs_l, self.parts, self.booms = [], [], [], []
        self.beam = None
        first = not rm.visited
        rm.visited = True
        rm.seen = True
        for d, (dx, dy) in DIRS.items():
            n = self.rooms.get((pos[0] + dx, pos[1] + dy))
            if n and rm.doors.get(d) != "hidden":
                n.seen = True
        if first:
            self.setup_room(rm)
        self.mobs = rm.mobs
        if entry:
            self.x, self.y = DOOR_ENTRY[entry]
            self.vx = self.vy = 0.0
        self.flow_tick = -99
        self.rebuild_bg()
        self.mini_key = None
        self.hud_key = None
        self.cd = max(self.cd, 8)

    def setup_room(self, rm):
        rm.grid = [list(r) for r in gen_layout(rm.kind, self.depth)]
        rm.mobs = []
        for r in range(ROWS):
            for c in range(COLS):
                ch = rm.grid[r][c]
                if ch == "O":
                    rm.poop[(c, r)] = 3
                elif ch == "F":
                    rm.fire[(c, r)] = 6
        for _ in range(rng.randint(3, 6)):
            rm.decals.append((rng.randrange(6), rng.randint(120, RW - 120), rng.randint(120, RH - 120)))
        if rm.kind == "normal":
            self.spawn_wave(rm)
        elif rm.kind == "boss":
            self.spawn_boss(rm)
        elif rm.kind == "treasure":
            rm.pedestals.append([650, 350, self.pick_item(), 0])
        elif rm.kind == "shop":
            offers = [("hr", 3, None), ("bomb", 5, None), ("key", 5, None), ("item", 15, self.pick_item())]
            for i, (k, price, it) in enumerate(offers):
                x = 350 + i * 200
                if k == "item":
                    rm.pedestals.append([x, 250, it, price])
                else:
                    rm.pickups.append(Pickup(x, 250, k, price))
        elif rm.kind == "secret":
            if rng.random() < 0.4:
                rm.pedestals.append([650, 350, self.pick_item(), 0])
            else:
                for i in range(3):
                    rm.pickups.append(Pickup(500 + i * 150, 350, rng.choice(["hr", "bomb", "coin", "coin", "key"])))

    def pick_item(self):
        pool = [i for i in ITEM_POOL if i not in self.used_items] or ITEM_POOL
        it = rng.choice(pool)
        self.used_items.add(it)
        return it

    def free_cells(self, rm, min_dist_from=None):
        out = []
        for r in range(ROWS):
            for c in range(COLS):
                if rm.grid[r][c] != ".":
                    continue
                x, y = cell_center(c, r)
                if min_dist_from and math.hypot(x - min_dist_from[0], y - min_dist_from[1]) < 330:
                    continue
                out.append((x, y))
        return out

    def spawn_wave(self, rm):
        hpm = 1 + 0.2 * (self.depth - 1)
        budget = 3.4 + 2.0 * self.depth + rng.uniform(0, 2.6)
        weights = {"fly": 3, "spider": 2, "pooter": 3, "gaper": 4, "horf": 2, "clotty": 2.5, "mulligan": 1.5,
                   "charger": 2.5, "host": 1.5, "boil": 1.5}
        picks = []
        counts = {}
        while budget > 0.9 and len(picks) < 9:
            k = rng.choices(list(weights), list(weights.values()))[0]
            if COST[k] > budget + 0.6 or counts.get(k, 0) >= (2 if k in ("host", "mulligan") else 4):
                continue
            picks.append(k)
            counts[k] = counts.get(k, 0) + 1
            budget -= COST[k]
        ent = DOOR_ENTRY[rng.choice(list(rm.doors))] if rm.doors else (650, 600)
        cells = self.free_cells(rm, ent)
        if len(cells) < len(picks):
            cells = self.free_cells(rm)
        rng.shuffle(cells)
        for k in picks:
            if not cells:
                break
            x, y = cells.pop()
            rm.mobs.append(self.make_mob(k, x, y, hpm))

    def make_mob(self, kind, x, y, hpm=1.0):
        return Mob(kind, x, y, max(2, BASE_HP[kind] * hpm))

    def spawn_boss(self, rm):
        pool = BOSS_POOL[min(self.depth - 1, 3)]
        opts = [b for b in pool if b not in self.used_bosses] or pool
        name = rng.choice(opts)
        self.used_bosses.add(name)
        hm = 1 + 0.1 * (self.depth - 1)
        cx, cy = 650, 230
        m = rm.mobs
        if name == "monstro":
            e = Mob("monstro", cx, cy, 250 * 0.8 * hm, True)
            e.d.update(phase=0, hops=0)
            m.append(e)
        elif name == "duke":
            e = Mob("duke", cx, cy, 110 * hm, True)
            vx = rng.choice((-2.4, 2.4))
            e.vx, e.vy = vx, rng.choice((-2.4, 2.4))
            e.d.update(orbit=[], ang=0.0)
            m.append(e)
        elif name == "gemini":
            a = Mob("contusion", cx - 120, cy, 140 * 0.8 * hm, True)
            b = Mob("suture", cx + 120, cy, 140 * 0.8 * hm, True)
            a.d.update(mode="chase", ph=0)
            b.d.update(partner=a, ang=0.0, free=False)
            a.d["partner"] = b
            m.extend([a, b])
        elif name == "larry":
            lead = {"hist": [(cx, cy)] * 400, "dir": "r", "t": 0, "poop": 0, "sp": 4.4}
            for i in range(6):
                e = Mob("larry", cx, cy, 22 * 0.9 * hm, True)
                e.d.update(lead=lead, off=i * 18, idx=i)
                m.append(e)
        elif name == "chub":
            e = Mob("chub", cx, cy, 350 * 0.5 * hm, True)
            e.d.update(hist=[(cx, cy)] * 100, dir="r", t=0, mode="roam", cool=60, spawn=120)
            m.append(e)
        elif name == "gurdy":
            e = Mob("gurdy", cx, cy, 595 * 0.5 * hm, True)
            e.d.update(phase=0, atk=None)
            m.append(e)

    # ---------------------------------------------------------------- background baking
    def rebuild_bg(self):
        rm = self.cur
        r = self.r
        r.reset_base()
        th = THEMES[self.theme]
        for k, x, y in rm.decals:
            r.stamp_base(th["decal"][k], x + WALL - 80, y + WALL - 55)
        r.reset_bg()
        for rr in range(ROWS):
            for c in range(COLS):
                self.bake_cell(c, rr, False)
        self.bake_doors(False)
        r.full = True

    def bake_cell(self, c, rr, dirty=True):
        rm = self.cur
        th = THEMES[self.theme]
        x, y = WALL + c * CELL, WALL + rr * CELL
        if dirty:
            self.r.restore(x, y, CELL, CELL)
            self.r.dirty(x, y, CELL, CELL)
        ch = rm.grid[rr][c]
        if ch == "R":
            self.r.stamp(th["rock"][(c * 7 + rr * 3) % 3], x, y)
        elif ch == "P":
            g = rm.grid
            m = 0
            for bit, (dx, dy) in ((1, (0, -1)), (2, (1, 0)), (4, (0, 1)), (8, (-1, 0))):
                nc, nr = c + dx, rr + dy
                if 0 <= nc < COLS and 0 <= nr < ROWS and g[nr][nc] == "P":
                    m |= bit
            self.r.stamp(th["pit"][m], x, y)
        elif ch == "S":
            self.r.stamp(ENV["spikes"], x, y)
        elif ch == "O":
            hp = rm.poop.get((c, rr), 3)
            self.r.stamp(ENV["poop"][3 - max(1, min(3, hp))], x, y)
        elif ch == "." and dirty:
            if (c, rr) in rm.rubble:
                self.r.stamp(th["rubble"], x, y)

    def door_style(self, d):
        rm = self.cur
        n = self.rooms.get((rm.pos[0] + DIRS[d][0], rm.pos[1] + DIRS[d][1]))
        st = rm.doors[d]
        if st == "hole":
            return "hole", "open"
        kind = "normal"
        for k in (n.kind if n else None, rm.kind):
            if k in ("boss", "treasure", "shop"):
                kind = k
                break
        if st == "locked":
            return kind, "locked"
        return kind, "open" if rm.cleared else "closed"

    def bake_doors(self, dirty=True):
        rm = self.cur
        for d, st in rm.doors.items():
            if st == "hidden":
                continue
            kind, state = self.door_style(d)
            x, y = DOOR_POS[d]
            w, h = (140, 80) if d in "ud" else (80, 140)
            if dirty:
                self.r.restore(x, y, w, h)
                self.r.dirty(x, y, w, h)
            self.r.stamp(DOORS["%s_%s_%s" % (kind, state, d)], x, y)

    def door_open(self, d):
        return self.cur.doors.get(d) in ("open", "hole") and self.cur.cleared

    # ---------------------------------------------------------------- geometry
    def solid_cell(self, c, r, fly):
        ch = self.cur.grid[r][c]
        return ch in "ROF" or (ch == "P" and not fly)

    def blocked(self, x, y, r, fly=False):
        if x - r < 0:
            if not (self.door_open("l") and abs(y - RH / 2) <= DOOR_HALF - r * 0.5):
                return True
        if x + r > RW:
            if not (self.door_open("r") and abs(y - RH / 2) <= DOOR_HALF - r * 0.5):
                return True
        if y - r < 0:
            if not (self.door_open("u") and abs(x - RW / 2) <= DOOR_HALF - r * 0.5):
                return True
        if y + r > RH:
            if not (self.door_open("d") and abs(x - RW / 2) <= DOOR_HALF - r * 0.5):
                return True
        c0, c1 = max(0, int((x - r) // CELL)), min(COLS - 1, int((x + r) // CELL))
        r0, r1 = max(0, int((y - r) // CELL)), min(ROWS - 1, int((y + r) // CELL))
        if c0 > COLS - 1 or r0 > ROWS - 1 or c1 < 0 or r1 < 0:
            return False
        rr2 = r * 0.92
        for rr in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if self.solid_cell(c, rr, fly):
                    nx = min(max(x, c * CELL), c * CELL + CELL)
                    ny = min(max(y, rr * CELL), rr * CELL + CELL)
                    if (nx - x) ** 2 + (ny - y) ** 2 < rr2 * rr2:
                        return True
        return False

    def move_body(self, e, dx, dy, r, fly=False):
        # axis-separated so bodies slide along rocks and walls instead of sticking
        hit = False
        if dx:
            if not self.blocked(e.x + dx, e.y, r, fly):
                e.x += dx
            else:
                hit = True
        if dy:
            if not self.blocked(e.x, e.y + dy, r, fly):
                e.y += dy
            else:
                hit = True
        return hit

    def los(self, x0, y0, x1, y1, step=30):
        # tears are stopped by rocks, poop and fire (pits are flown over)
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d // step))
        g = self.cur.grid
        for i in range(1, n):
            t = i / n
            c, r = int((x0 + (x1 - x0) * t) // CELL), int((y0 + (y1 - y0) * t) // CELL)
            if 0 <= c < COLS and 0 <= r < ROWS and g[r][c] in "ROF":
                return False
        return True

    def flow_field(self):
        # BFS distance to Isaac's cell for walking enemies; refreshed every few ticks
        if self.tick_n - self.flow_tick < 6:
            return self.flow
        self.flow_tick = self.tick_n
        g = self.cur.grid
        c0, r0 = to_cell(min(max(self.x, 0), RW - 1), min(max(self.y, 0), RH - 1))
        dist = {(c0, r0): 0}
        q = [(c0, r0)]
        for c, r in q:
            for dx, dy in DIRS.values():
                n = (c + dx, r + dy)
                if 0 <= n[0] < COLS and 0 <= n[1] < ROWS and n not in dist and g[n[1]][n[0]] not in "ROFP":
                    dist[n] = dist[(c, r)] + 1
                    q.append(n)
        self.flow = dist
        return dist

    def walk_toward_isaac(self, e, speed):
        if self.los(e.x, e.y, self.x, self.y) and not self.line_has_pit(e.x, e.y, self.x, self.y):
            tx, ty = self.x, self.y
        else:
            f = self.flow_field()
            c, r = to_cell(e.x, e.y)
            best, bc = f.get((c, r), 999), None
            for dx, dy in DIRS.values():
                n = (c + dx, r + dy)
                if n in f and f[n] < best:
                    best, bc = f[n], n
            if bc is None:
                tx, ty = self.x, self.y
            else:
                tx, ty = cell_center(*bc)
        dx, dy = tx - e.x, ty - e.y
        d = math.hypot(dx, dy) or 1.0
        e.vx = e.vx * 0.5 + dx / d * speed * 0.5
        e.vy = e.vy * 0.5 + dy / d * speed * 0.5
        self.move_body(e, e.vx, e.vy, e.r * 0.8)

    def line_has_pit(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d // 30))
        g = self.cur.grid
        for i in range(n + 1):
            t = i / n
            c, r = int((x0 + (x1 - x0) * t) // CELL), int((y0 + (y1 - y0) * t) // CELL)
            if 0 <= c < COLS and 0 <= r < ROWS and g[r][c] == "P":
                return True
        return False

    # ---------------------------------------------------------------- damage
    def hurt_isaac(self, n, sx, sy):
        if self.invuln > 0 or self.dying:
            return
        self.invuln = 64
        self.hurt_t = 22
        if self.soul > 0:
            take = min(self.soul, n)
            self.soul -= take
            n -= take
        self.hp -= n
        d = math.hypot(self.x - sx, self.y - sy) or 1.0
        self.vx += (self.x - sx) / d * 7
        self.vy += (self.y - sy) / d * 7
        if self.hp <= 0 and self.soul <= 0:
            self.hp = 0
            self.dying = 1
            self.beam = None

    def hurt_mob(self, e, dmg):
        if e.dead or e.inv or e.hidden:
            return False
        e.hp -= dmg
        e.hit = 3
        if e.hp <= 0:
            self.kill_mob(e)
        return True

    def kill_mob(self, e):
        e.dead = True
        self.score += KINDS[e.kind][3]
        for _ in range(7):
            a = rng.uniform(0, 6.28)
            s = rng.uniform(3, 8)
            self.parts.append([e.x, e.y, math.cos(a) * s, math.sin(a) * s - 3, 16, 1])
        rm = self.cur
        if len(rm.decals) < 14 and not e.boss:
            k = rng.randrange(3)
            rm.decals.append((k, int(e.x), int(e.y)))
            th = THEMES[self.theme]
            self.r.stamp_both(th["decal"][k], int(e.x) + WALL - 80, int(e.y) + WALL - 55)
        if e.kind == "mulligan":
            for i in range(3):
                f = self.make_mob("fly", e.x + rng.randint(-20, 20), e.y + rng.randint(-20, 20), 1.0)
                self.mobs.append(f)
        elif e.kind == "boil":
            self.boil_burst(e)
        elif e.kind == "duke":
            for f in e.d["orbit"]:
                f.st = "idle"
                f.d.pop("owner", None)
        elif e.kind == "larry" and e.boss:
            self.score += 150
        if e.boss and not any(m.boss and not m.dead for m in self.mobs if m is not e):
            self.score += 1500 + 500 * self.depth
            # the boss's summoned minions die with it, otherwise a lone boil can stall the whole floor
            for m in self.mobs:
                if m is not e and not m.dead:
                    m.dead = True
                    self.parts.append([m.x, m.y, 0, 0, 8, 3])

    def boil_burst(self, e):
        for a in (45, 135, 225, 315) if e.d.get("diag", True) else (0, 90, 180, 270):
            self.etear(e.x, e.y, math.radians(a), 7.5, 1)

    def etear(self, x, y, ang, speed, dmg, big=False):
        speed *= 1 + 0.07 * (self.depth - 1)
        self.tears.append(Tear(x, y, math.cos(ang) * speed, math.sin(ang) * speed, 90, dmg, False, big))

    def aim(self, e, spread=0.0, tx=None, ty=None):
        tx = self.x if tx is None else tx
        ty = self.y if ty is None else ty
        return math.atan2(ty - e.y, tx - e.x) + spread


# ------------------------------------------------------------------------------------------------ simulation
def colliders(e):
    if e.kind == "chub":
        h = e.d["hist"]
        return [(h[-1][0], h[-1][1], e.r), (h[-21][0], h[-21][1], e.r * 0.9), (h[-41][0], h[-41][1], e.r * 0.85)]
    if e.kind == "larry":
        h = e.d["lead"]["hist"]
        p = h[-1 - e.d["off"]]
        return [(p[0], p[1], e.r)]
    return [(e.x, e.y, e.r)]


class Sim(Game):
    # ---------------------------------------------------------------- isaac
    def update_isaac(self, mx, my, fire, bomb):
        if self.dying:
            self.dying += 1
            return
        st = self.stats
        sp = st.speed_px()
        n = math.hypot(mx, my)
        if n > 1:
            mx, my = mx / n, my / n
        self.vx += (mx * sp - self.vx) * 0.6
        self.vy += (my * sp - self.vy) * 0.6
        ox, oy = self.x, self.y
        self.move_body(self, self.vx, self.vy, ISAAC_R)
        moved = math.hypot(self.x - ox, self.y - oy)
        if moved > 0.5:
            self.walk += moved / 15.0
            self.move_dir = ("r" if self.vx > 0 else "l") if abs(self.vx) > abs(self.vy) else ("d" if self.vy > 0 else "u")
        if self.invuln > 0:
            self.invuln -= 1
        if self.hurt_t > 0:
            self.hurt_t -= 1
        if self.shoot_t > 0:
            self.shoot_t -= 1
        self.cd -= 1
        if fire:
            self.face = fire
            if st.laser:
                if self.beam is None:
                    self.charge += 1
                    self.shoot_t = 2
                    if self.charge >= 20:
                        self.beam = {"d": fire, "t": 14}
                        self.charge = 0
            elif self.cd <= 0:
                self.fire_tears(fire)
                self.cd = st.interval() * (1.0)
        elif self.charge:
            self.charge = 0
        if self.beam is not None:
            self.beam["t"] -= 1
            self.shoot_t = 2
            self.apply_beam()
            if self.beam["t"] <= 0:
                self.beam = None
        if bomb and self.bombs_n > 0 and len(self.bombs_l) < 2:
            self.bombs_n -= 1
            self.bombs_l.append(Bomb(self.x, self.y))
        # hazards: spikes and fire hurt on contact
        c, r = to_cell(min(max(self.x, 0), RW - 1), min(max(self.y, 0), RH - 1))
        if self.cur.grid[r][c] == "S":
            self.hurt_isaac(2, self.x, self.y + 1)
        for (fc, fr) in self.cur.fire:
            fx, fy = cell_center(fc, fr)
            if self.cur.grid[fr][fc] == "F" and math.hypot(fx - self.x, fy - self.y) < 52:
                self.hurt_isaac(2, fx, fy)

    def fire_tears(self, d):
        st = self.stats
        dx, dy = DIRS[d]
        ang = math.atan2(dy, dx)
        offs = (-0.17, 0.0, 0.17) if st.triple else (0.0,)
        dmg = st.damage()
        life = st.life()
        for o in offs:
            vx = math.cos(ang + o) * TEAR_SPEED + self.vx * 0.3
            vy = math.sin(ang + o) * TEAR_SPEED + self.vy * 0.3
            self.tears.append(Tear(self.x + dx * 16, self.y + dy * 8, vx, vy, life, dmg, True, dmg > 7.5, st.spectral, st.homing))
        self.shoot_t = 8

    def apply_beam(self):
        d = self.beam["d"]
        dx, dy = DIRS[d]
        dmg = self.stats.damage() * 0.45
        for e in self.mobs:
            if e.dead or e.hidden or e.inv:
                continue
            for cx, cy, cr in colliders(e):
                fw = (cx - self.x) * dx + (cy - self.y) * dy
                lat = abs((cx - self.x) * dy - (cy - self.y) * dx)
                if fw > -cr and lat < 34 + cr:
                    self.hurt_mob(e, dmg)
                    break

    # ---------------------------------------------------------------- tears
    def splash(self, t):
        self.parts.append([t.x, t.y, 0, 0, 8, 2 if t.friendly else 3])

    def update_tears(self):
        keep = []
        rm = self.cur
        g = rm.grid
        for t in self.tears:
            t.age += 1
            if t.homing and t.friendly:
                best, bd = None, 420.0
                for e in self.mobs:
                    if not e.dead and not e.hidden:
                        d = math.hypot(e.x - t.x, e.y - t.y)
                        if d < bd:
                            best, bd = e, d
                if best is not None:
                    sp = math.hypot(t.vx, t.vy)
                    ax, ay = (best.x - t.x) / bd, (best.y - t.y) / bd
                    t.vx += ax * sp * 0.16
                    t.vy += ay * sp * 0.16
                    k = sp / (math.hypot(t.vx, t.vy) or 1)
                    t.vx *= k
                    t.vy *= k
            t.x += t.vx
            t.y += t.vy
            if t.age >= t.life:
                self.splash(t)
                continue
            if t.x < 0 or t.x >= RW or t.y < 0 or t.y >= RH:
                lane = ((t.x < 0 and self.door_open("l") or t.x > RW and self.door_open("r")) and abs(t.y - RH / 2) < DOOR_HALF) or \
                       ((t.y < 0 and self.door_open("u") or t.y > RH and self.door_open("d")) and abs(t.x - RW / 2) < DOOR_HALF)
                if not lane or t.x < -60 or t.x > RW + 60 or t.y < -60 or t.y > RH + 60:
                    if -60 < t.x < RW + 60 and -60 < t.y < RH + 60:
                        self.splash(t)
                    continue
                keep.append(t)
                continue
            c, r = int(t.x // CELL), int(t.y // CELL)
            ch = g[r][c]
            if ch in "ROF" and not t.spectral:
                if ch == "O":
                    self.hit_poop(c, r)
                elif ch == "F" and t.friendly:
                    self.hit_fire(c, r)
                self.splash(t)
                continue
            if t.friendly:
                hit = False
                for e in self.mobs:
                    if e.dead or e.hidden:
                        continue
                    for cx, cy, cr in colliders(e):
                        if (cx - t.x) ** 2 + (cy - t.y) ** 2 < (cr + TEAR_R) ** 2:
                            hit = True
                            break
                    if hit:
                        if self.hurt_mob(e, t.dmg):
                            e.vx += t.vx * 0.04
                            e.vy += t.vy * 0.04
                        break
                if hit:
                    self.splash(t)
                    continue
            elif not self.dying and (self.x - t.x) ** 2 + (self.y - t.y) ** 2 < (ISAAC_R + TEAR_R - 4) ** 2:
                self.hurt_isaac(t.dmg, t.x, t.y)
                self.splash(t)
                continue
            keep.append(t)
        self.tears = keep

    def hit_poop(self, c, r):
        rm = self.cur
        hp = rm.poop.get((c, r), 3) - 1
        rm.poop[(c, r)] = hp
        if hp <= 0:
            rm.grid[r][c] = "."
            del rm.poop[(c, r)]
            if rng.random() < 0.18:
                x, y = cell_center(c, r)
                rm.pickups.append(Pickup(x, y, rng.choice(["coin", "coin", "hh", "bomb"])))
        self.bake_cell(c, r)

    def hit_fire(self, c, r):
        rm = self.cur
        hp = rm.fire.get((c, r), 6) - 1
        rm.fire[(c, r)] = hp
        if hp <= 0:
            rm.grid[r][c] = "."
            del rm.fire[(c, r)]

    # ---------------------------------------------------------------- bombs
    def update_bombs(self):
        keep = []
        for b in self.bombs_l:
            b.t -= 1
            if b.t > 0:
                keep.append(b)
            else:
                self.explode(b)
        self.bombs_l = keep
        for b in self.booms:
            b[2] += 1
        self.booms = [b for b in self.booms if b[2] < 18]

    def explode(self, b):
        self.booms.append([b.x, b.y, 0])
        for e in self.mobs:
            if not e.dead and not e.hidden and any(math.hypot(cx - b.x, cy - b.y) < BLAST_R + cr for cx, cy, cr in colliders(e)):
                self.hurt_mob(e, 40)
        if math.hypot(self.x - b.x, self.y - b.y) < BLAST_R * 0.85:
            self.hurt_isaac(2, b.x, b.y)
        rm = self.cur
        for r in range(ROWS):
            for c in range(COLS):
                ch = rm.grid[r][c]
                if ch in "ROF":
                    x, y = cell_center(c, r)
                    if math.hypot(x - b.x, y - b.y) <= 125:
                        rm.grid[r][c] = "."
                        rm.poop.pop((c, r), None)
                        rm.fire.pop((c, r), None)
                        if ch == "R":
                            rm.rubble.add((c, r))
                        self.bake_cell(c, r)
        centers = {"u": (RW / 2, -40), "d": (RW / 2, RH + 40), "l": (-40, RH / 2), "r": (RW + 40, RH / 2)}
        for d, st in list(rm.doors.items()):
            if st == "hidden" and math.hypot(centers[d][0] - b.x, centers[d][1] - b.y) < 190:
                rm.doors[d] = "hole"
                n = self.rooms[(rm.pos[0] + DIRS[d][0], rm.pos[1] + DIRS[d][1])]
                n.doors[OPP[d]] = "hole"
                self.score += 400
                self.bake_doors()

    # ---------------------------------------------------------------- pickups
    def update_pickups(self):
        rm = self.cur
        keep = []
        for p in rm.pickups:
            p.t += 1
            if math.hypot(p.x - self.x, p.y - self.y) < 46 and not self.dying:
                if self.try_take(p):
                    continue
            keep.append(p)
        rm.pickups = keep
        for ped in rm.pedestals:
            if ped[2] and not self.dying and math.hypot(ped[0] - self.x, ped[1] - 10 - self.y) < 50:
                if ped[3] and self.coins < ped[3]:
                    continue
                self.coins -= ped[3]
                apply_item(self, ped[2])
                self.score += 400
                self.banner = (ITEM_NAMES[ped[2]], 100)
                ped[2] = None
        if rm.trapdoor and rm.cleared and not self.dying and math.hypot(650 - self.x, 250 - self.y) < 44:
            self.score += 1500
            self.new_floor()

    def try_take(self, p):
        k = p.kind
        if p.price and self.coins < p.price:
            return False
        if k == "hr" and self.hp >= self.maxhp:
            return False
        if k == "hh" and self.hp >= self.maxhp:
            return False
        if k == "hr":
            self.hp = min(self.maxhp, self.hp + 2)
        elif k == "hh":
            self.hp = min(self.maxhp, self.hp + 1)
        elif k == "hs":
            self.soul = min(8, self.soul + 2)
        elif k == "coin":
            self.coins = min(99, self.coins + 1)
            self.score += 10
        elif k == "bomb":
            self.bombs_n = min(99, self.bombs_n + 1)
        elif k == "key":
            self.keys = min(99, self.keys + 1)
        self.coins -= p.price
        return True

    # ---------------------------------------------------------------- rooms
    def clear_room(self):
        rm = self.cur
        rm.cleared = True
        self.score += 100
        self.bake_doors()
        if rm.kind == "boss":
            if rng.random() < 0.7:
                rm.pedestals.append([650, 470, self.pick_item(), 0])
            rm.trapdoor = True
            return
        drops = []
        if rm.bonus == "key":
            drops = ["key"]
        elif rm.bonus == "coins":
            drops = ["coin"] * 3
        elif rng.random() < 0.55:
            drops = [rng.choices(["coin", "hr", "hh", "bomb", "key", "hs"], [32, 9, 9, 14, 6, 2])[0]]
        cells = sorted(self.free_cells(rm), key=lambda p: math.hypot(p[0] - 650, p[1] - 350))
        for i, k in enumerate(drops):
            if cells:
                x, y = cells[min(i * 2, len(cells) - 1)]
                rm.pickups.append(Pickup(x, y, k))

    def try_doors(self):
        # unlocking by touch (costs a key), and leaving through open doorways
        rm = self.cur
        for d, st in rm.doors.items():
            if st == "locked":
                lane = abs(self.x - RW / 2) < DOOR_HALF if d in "ud" else abs(self.y - RH / 2) < DOOR_HALF
                edge = {"u": self.y < ISAAC_R + 14, "d": self.y > RH - ISAAC_R - 14, "l": self.x < ISAAC_R + 14,
                        "r": self.x > RW - ISAAC_R - 14}[d]
                if lane and edge and self.keys > 0 and rm.cleared:
                    self.keys -= 1
                    rm.doors[d] = "open"
                    n = self.rooms[(rm.pos[0] + DIRS[d][0], rm.pos[1] + DIRS[d][1])]
                    n.doors[OPP[d]] = "open"
                    self.bake_doors()
        for d in "udlr":
            if not self.door_open(d):
                continue
            if (d == "u" and self.y < 4) or (d == "d" and self.y > RH - 4) or (d == "l" and self.x < 4) or (d == "r" and self.x > RW - 4):
                n = (rm.pos[0] + DIRS[d][0], rm.pos[1] + DIRS[d][1])
                self.enter_room(n, d)
                return

    # ---------------------------------------------------------------- mobs
    def update_mobs(self):
        for e in self.mobs:
            if e.dead:
                continue
            e.anim += 1
            if e.hit:
                e.hit -= 1
            ox, oy = e.x, e.y
            UPD[e.kind](self, e)
            # measured displacement: the bot predicts every enemy (charges included) from what it actually did last tick
            e.mvx, e.mvy = e.x - ox, e.y - oy
        ms = self.mobs
        # soft separation so walkers do not stack on one pixel
        for i in range(len(ms)):
            a = ms[i]
            if a.flying or a.boss or a.dead or a.kind in ("host", "boil") or a.st == "charge":
                continue
            for j in range(i + 1, len(ms)):
                b = ms[j]
                if b.flying or b.boss or b.dead or b.kind in ("host", "boil") or b.st == "charge":
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                d2 = dx * dx + dy * dy
                m = a.r + b.r - 6
                if 0 < d2 < m * m:
                    d = math.sqrt(d2)
                    push = (m - d) * 0.25
                    self.move_body(a, -dx / d * push, -dy / d * push, a.r * 0.8)
                    self.move_body(b, dx / d * push, dy / d * push, b.r * 0.8)
        # contact damage
        if not self.dying and self.invuln <= 0:
            for e in ms:
                if e.dead or not e.contact or e.hidden or (e.kind == "monstro" and e.z > 20):
                    continue
                for cx, cy, cr in colliders(e):
                    if (cx - self.x) ** 2 + (cy - self.y) ** 2 < (ISAAC_R + cr * 0.85) ** 2:
                        self.hurt_isaac(e.contact, cx, cy)
                        break
        ms[:] = [e for e in ms if not e.dead]


# ------------------------------------------------------------------------------------------------ enemy behaviours
def depth_speed(g):
    return 1 + 0.06 * (g.depth - 1)


def move_fly(e, dx, dy):
    # flyers ignore rocks and pits, only the room walls stop them
    e.x = min(max(e.x + dx, e.r), RW - e.r)
    e.y = min(max(e.y + dy, e.r), RH - e.r)


def wander(g, e, speed, period=50):
    e.t -= 1
    if e.t <= 0 or e.d.get("blk"):
        a = rng.uniform(0, 6.283)
        e.d["wx"], e.d["wy"] = math.cos(a) * speed, math.sin(a) * speed
        e.t = rng.randint(period // 2, period)
    if e.flying:
        move_fly(e, e.d.get("wx", 0), e.d.get("wy", 0))
        e.d["blk"] = False
    else:
        e.d["blk"] = g.move_body(e, e.d.get("wx", 0), e.d.get("wy", 0), e.r * 0.8)


def u_fly(g, e):
    sp = depth_speed(g)
    if e.st == "orbit":
        o = e.d.get("owner")
        if o is None or o.dead:
            e.st = "idle"
            return
        e.d["ang"] += 0.11
        e.x = o.x + math.cos(e.d["ang"]) * 105
        e.y = o.y + math.sin(e.d["ang"]) * 105
        return
    dx, dy = g.x - e.x, g.y - e.y
    d = math.hypot(dx, dy) or 1.0
    e.vx = e.vx * 0.88 + dx / d * 0.5 * sp + rng.uniform(-0.45, 0.45)
    e.vy = e.vy * 0.88 + dy / d * 0.5 * sp + rng.uniform(-0.45, 0.45)
    cap = 3.6 * sp * (0.75 if e.d.get("big") else 1.0)
    s = math.hypot(e.vx, e.vy)
    if s > cap:
        e.vx, e.vy = e.vx / s * cap, e.vy / s * cap
    move_fly(e, e.vx, e.vy)


def u_spider(g, e):
    sp = depth_speed(g)
    e.t -= 1
    if e.st == "run":
        if g.los(e.x, e.y, g.x, g.y):
            a = math.atan2(g.y - e.y, g.x - e.x) + e.d.setdefault("jit", rng.uniform(-0.7, 0.7))
            g.move_body(e, math.cos(a) * 5.2 * sp, math.sin(a) * 5.2 * sp, e.r * 0.8)
        else:
            g.walk_toward_isaac(e, 5.2 * sp)
        if e.t <= 0:
            e.st, e.t = "idle", rng.randint(6, 14)
    elif e.t <= 0:
        e.st, e.t = "run", rng.randint(10, 18)
        e.d["jit"] = rng.uniform(-0.7, 0.7)


def u_pooter(g, e):
    wander(g, e, 0.9)
    cd = e.d.get("cd", rng.randint(40, 100)) - 1
    f = e.d.get("flash", 0)
    e.d["flash"] = max(0, f - 1)
    if cd <= 0:
        d = math.hypot(g.x - e.x, g.y - e.y)
        if d > 150:
            # deeper floors grow Super Pooters that fire two shots in a V
            for k in ((-0.2, 0.2) if g.depth >= 3 else (0.0,)):
                g.etear(e.x, e.y + 14, g.aim(e, k), ETEAR_SPEED * 0.9, 2)
            e.d["flash"] = 9
        cd = rng.randint(90, 140)
    e.d["cd"] = cd


def u_gaper(g, e):
    g.walk_toward_isaac(e, 2.8 * depth_speed(g))


def u_horf(g, e):
    wander(g, e, 0.45)
    cd = e.d.get("cd", rng.randint(30, 80)) - 1
    e.d["flash"] = max(0, e.d.get("flash", 0) - 1)
    if cd <= 0:
        if math.hypot(g.x - e.x, g.y - e.y) < 800:
            for k in ((-0.22, 0, 0.22) if g.depth >= 4 else (0.0,)):
                g.etear(e.x, e.y + 10, g.aim(e, k), ETEAR_SPEED, 2)
            e.d["flash"] = 10
        cd = rng.randint(70, 110)
    e.d["cd"] = cd


def u_clotty(g, e):
    wander(g, e, 1.5, 60)
    cd = e.d.get("cd", rng.randint(40, 100)) - 1
    if cd <= 0:
        base = rng.choice((0, math.pi / 4))
        for k in range(4):
            g.etear(e.x, e.y, base + k * math.pi / 2, 8.0, 2)
        cd = rng.randint(100, 150)
    e.d["cd"] = cd


def u_mulligan(g, e):
    sp = depth_speed(g)
    dx, dy = e.x - g.x, e.y - g.y
    d = math.hypot(dx, dy) or 1.0
    if d < 380:
        hit = g.move_body(e, dx / d * 3.0 * sp, dy / d * 3.0 * sp, e.r * 0.8)
        if hit:
            # cornered: slip sideways along the wall
            g.move_body(e, -dy / d * 3.0, dx / d * 3.0, e.r * 0.8)
    else:
        wander(g, e, 1.2)


def u_charger(g, e):
    d = e.d
    sp = depth_speed(g)
    if e.st == "charge":
        d["v"] = min(11.0 * sp, d.get("v", 3.0) + 0.9)
        dx, dy = DIRS[e.face]
        d["run"] = d.get("run", 0) + 1
        bumped = g.move_body(e, dx * d["v"], dy * d["v"], e.r * 0.8)
        # two chargers running at each other would push forever, so any crowd contact or a long run ends the charge
        for o in g.mobs:
            if o is not e and not o.dead and not o.flying and (o.x - e.x) ** 2 + (o.y - e.y) ** 2 < (e.r + o.r - 10) ** 2:
                bumped = True
        if bumped or d["run"] > 70:
            e.st, e.t = "stun", 26
            d["run"] = 0
        return
    if e.st == "stun":
        e.t -= 1
        if e.t <= 0:
            e.st = "idle"
        return
    e.t -= 1
    if e.t <= 0 or d.get("blk"):
        e.face = rng.choice("udlr")
        e.t = rng.randint(30, 70)
    dx, dy = DIRS[e.face]
    d["blk"] = g.move_body(e, dx * 1.3 * sp, dy * 1.3 * sp, e.r * 0.8)
    ax, ay = abs(g.x - e.x) < 40, abs(g.y - e.y) < 40
    if (ax or ay) and g.los(e.x, e.y, g.x, g.y):
        if ax:
            e.face = "d" if g.y > e.y else "u"
        else:
            e.face = "r" if g.x > e.x else "l"
        e.st = "charge"
        d["v"] = 3.0
        d["run"] = 0


def u_host(g, e):
    d = e.d
    e.t -= 1
    if e.st == "idle":
        e.st, e.t, e.inv = "closed", rng.randint(60, 110), True
    if e.st == "closed":
        if e.t <= 0:
            e.st, e.t, e.inv = "open", 50, False
            d["shot"] = False
    else:
        if e.t <= 30 and not d.get("shot"):
            d["shot"] = True
            for k in (-0.26, 0, 0.26):
                g.etear(e.x, e.y + 6, g.aim(e, k), ETEAR_SPEED, 2)
        if e.t <= 0:
            e.st, e.t, e.inv = "closed", rng.randint(80, 140), True


def u_boil(g, e):
    e.t -= 1
    if e.t <= 0:
        e.t = rng.randint(70, 100)
        stage = e.d.get("stage", 0) + 1
        if stage >= 3:
            g.boil_burst(e)
            stage = 0
            e.d["diag"] = not e.d.get("diag", True)
        e.d["stage"] = stage


# ------------------------------------------------------------------------------------------------ bosses
def u_monstro(g, e):
    d = e.d
    e.t -= 1
    if e.st == "idle":
        e.st, e.t = "rest", 20
    elif e.st == "rest":
        if e.t <= 0:
            if d["hops"] >= rng.randint(2, 3):
                d["hops"] = 0
                if rng.random() < 0.5:
                    e.st, e.t = "spray", 56
                else:
                    e.st, e.t = "crouch", 22
            else:
                d["hops"] += 1
                e.st, e.t = "hop", 26
                d["tx"], d["ty"] = g.x, g.y
    elif e.st == "hop":
        e.z = 46 * math.sin(math.pi * (1 - e.t / 26))
        dx, dy = d["tx"] - e.x, d["ty"] - e.y
        n = math.hypot(dx, dy) or 1.0
        s = min(5.8, n / max(1, e.t))
        g.move_body(e, dx / n * s, dy / n * s, e.r * 0.6)
        if e.t <= 0:
            e.z = 0
            e.st, e.t = "rest", 16
    elif e.st == "spray":
        if e.t % 2 == 0:
            big = rng.random() < 0.3
            g.etear(e.x, e.y + 24, g.aim(e, rng.uniform(-0.8, 0.8)), rng.uniform(5.0, 10.5), 2 if big else 1, big)
        if e.t <= 0:
            e.st, e.t = "rest", 24
    elif e.st == "crouch":
        if e.t <= 0:
            e.st, e.t, e.inv = "up", 20, True
    elif e.st == "up":
        e.z += 36
        if e.t <= 0:
            e.st, e.t, e.hidden = "air", 28, True
    elif e.st == "air":
        dx, dy = g.x - e.x, g.y - e.y
        n = math.hypot(dx, dy) or 1.0
        s = min(7.5, n)
        e.x += dx / n * s
        e.y += dy / n * s
        if e.t <= 0:
            e.st, e.t, e.hidden = "down", 9, False
    elif e.st == "down":
        e.z = max(0.0, e.z * 0.55)
        if e.t <= 0:
            e.z = 0
            e.inv = False
            e.st, e.t = "rest", 30
            for k in range(14):
                g.etear(e.x, e.y, k * math.pi / 7 + 0.3, 7.0, 1)
            if math.hypot(g.x - e.x, g.y - e.y) < e.r + ISAAC_R:
                g.hurt_isaac(2, e.x, e.y)


def u_duke(g, e):
    d = e.d
    d["t"] = d.get("t", 0) + 1
    t = d["t"]
    s = math.hypot(e.vx, e.vy) or 1.0
    k = 2.3 / s
    e.vx += (e.vx * k - e.vx) * 0.06
    e.vy += (e.vy * k - e.vy) * 0.06
    e.x += e.vx
    e.y += e.vy
    if e.x < e.r or e.x > RW - e.r:
        e.vx = -e.vx
        e.x = min(max(e.x, e.r), RW - e.r)
    if e.y < e.r or e.y > RH - e.r:
        e.vy = -e.vy
        e.y = min(max(e.y, e.r), RH - e.r)
    d["orbit"] = [f for f in d["orbit"] if not f.dead and f.st == "orbit"]
    nfly = sum(1 for m in g.mobs if m.kind == "fly" and not m.dead)
    if t % 62 == 0 and nfly < 12:
        if len(d["orbit"]) < 3:
            f = g.make_mob("fly", e.x, e.y, 1.0)
            f.hp = f.maxhp = 7 * (1 + 0.1 * (g.depth - 1))
            f.st = "orbit"
            f.d["owner"] = e
            f.d["ang"] = len(d["orbit"]) * 2.09
            d["orbit"].append(f)
            g.mobs.append(f)
        elif rng.random() < 0.5:
            f = g.make_mob("fly", e.x, e.y, 2.5)
            f.d["big"] = True
            f.r = 24
            g.mobs.append(f)
        else:
            for f in d["orbit"]:
                f.st = "idle"
            d["orbit"] = []


def u_contusion(g, e):
    d = e.d
    sp = depth_speed(g)
    d["ph"] += 1
    if d["mode"] == "chase":
        g.walk_toward_isaac(e, 2.6 * sp)
        if d["ph"] > 115:
            n = math.hypot(g.x - e.x, g.y - e.y) or 1.0
            d["cx"], d["cy"], d["v"], d["mode"], d["ph"] = (g.x - e.x) / n, (g.y - e.y) / n, 4.0, "charge", 0
    elif d["mode"] == "charge":
        d["v"] = min(11.0 * sp, d["v"] + 0.55)
        hit = g.move_body(e, d["cx"] * d["v"], d["cy"] * d["v"], e.r * 0.8)
        if hit or d["ph"] > 50:
            d["mode"], d["ph"] = "rest", 0
    elif d["ph"] > 45:
        d["mode"], d["ph"] = "chase", 0


def u_suture(g, e):
    d = e.d
    p = d["partner"]
    if p.dead:
        dx, dy = g.x - e.x, g.y - e.y
        n = math.hypot(dx, dy) or 1.0
        e.vx = e.vx * 0.97 + dx / n * 0.5
        e.vy = e.vy * 0.97 + dy / n * 0.5
        s = math.hypot(e.vx, e.vy)
        if s > 7.5:
            e.vx, e.vy = e.vx / s * 7.5, e.vy / s * 7.5
        if g.move_body(e, e.vx, e.vy, e.r * 0.8):
            e.vx, e.vy = -e.vx * 0.6, -e.vy * 0.6
        return
    d["ang"] += 0.025
    tx, ty = p.x + math.cos(d["ang"]) * 170, p.y + math.sin(d["ang"]) * 170
    dx, dy = tx - e.x, ty - e.y
    n = math.hypot(dx, dy) or 1.0
    s = min(4.6, n)
    g.move_body(e, dx / n * s, dy / n * s, e.r * 0.8)
    d["cd"] = d.get("cd", 50) - 1
    if d["cd"] <= 0 and g.los(e.x, e.y, g.x, g.y):
        g.etear(e.x, e.y, g.aim(e), ETEAR_SPEED * 0.95, 1)
        d["cd"] = 52


def lead_step(g, lead, r, speed):
    # Larry Jr's body path: one lead point walking in cardinal directions; segments sample its history.
    if lead.get("tick") == g.tick_n:
        return
    lead["tick"] = g.tick_n
    hist = lead["hist"]
    x, y = hist[-1]
    dx, dy = DIRS[lead["dir"]]
    nx, ny = x + dx * speed, y + dy * speed
    cc, rr = int((nx + dx * r) // CELL), int((ny + dy * r) // CELL)
    if 0 <= cc < COLS and 0 <= rr < ROWS and g.cur.grid[rr][cc] == "O":
        while g.cur.grid[rr][cc] == "O":
            g.hit_poop(cc, rr)
        lead["t"] = 999
    if g.blocked(nx, ny, r * 0.7):
        opts = []
        for dd in "udlr":
            ex, ey = DIRS[dd]
            if dd != lead["dir"] and not g.blocked(x + ex * 30, y + ey * 30, r * 0.7):
                opts.append((math.hypot(g.x - (x + ex * 100), g.y - (y + ey * 100)) + rng.uniform(0, 160), dd))
        if opts:
            lead["dir"] = min(opts)[1]
        else:
            # boxed in (usually by poop it dropped itself): eat the poop around the head
            c0, r0 = to_cell(x, y)
            for cc in range(max(0, c0 - 1), min(COLS, c0 + 2)):
                for rr in range(max(0, r0 - 1), min(ROWS, r0 + 2)):
                    while g.cur.grid[rr][cc] == "O":
                        g.hit_poop(cc, rr)
        nx, ny = x, y
    else:
        lead["t"] += 1
        if lead["t"] > 70:
            lead["t"] = 0
            ex = "r" if g.x > x else "l"
            ey = "d" if g.y > y else "u"
            cand = [dd for dd in (ex, ey) if dd != lead["dir"] and dd != OPP[lead["dir"]]]
            if cand and rng.random() < 0.6:
                dd = rng.choice(cand)
                if not g.blocked(x + DIRS[dd][0] * 40, y + DIRS[dd][1] * 40, r * 0.7):
                    lead["dir"] = dd
    hist.append((nx, ny))
    if len(hist) > 700:
        del hist[:200]
    lead["poop"] += 1
    if lead["poop"] > 170:
        lead["poop"] = 0
        c, rw = to_cell(*hist[-30])
        rm = g.cur
        if 0 <= c < COLS and 0 <= rw < ROWS and rm.grid[rw][c] == "." and (c, rw) not in door_cells() \
                and math.hypot(cell_center(c, rw)[0] - g.x, cell_center(c, rw)[1] - g.y) > 120 \
                and math.hypot(cell_center(c, rw)[0] - hist[-1][0], cell_center(c, rw)[1] - hist[-1][1]) > 170:
            rm.grid[rw][c] = "O"
            rm.poop[(c, rw)] = 3
            g.bake_cell(c, rw)


def u_larry(g, e):
    lead = e.d["lead"]
    lead_step(g, lead, e.r, lead["sp"] * depth_speed(g) ** 0.5)
    p = lead["hist"][-1 - e.d["off"]]
    e.x, e.y = p
    e.face = lead["dir"]
    sp = lead["sp"] * depth_speed(g) ** 0.5
    e.vx, e.vy = DIRS[e.face][0] * sp, DIRS[e.face][1] * sp


def u_chub(g, e):
    d = e.d
    sp = depth_speed(g)
    hist = d["hist"]
    d["cool"] -= 1
    if d["mode"] == "roam":
        dx, dy = DIRS[d["dir"]]
        if g.move_body(e, dx * 2.8 * sp, dy * 2.8 * sp, e.r * 0.75):
            d["dir"] = rng.choice([k for k in "udlr" if k != d["dir"]])
        d["t"] += 1
        if d["t"] > 60:
            d["t"] = 0
            d["dir"] = rng.choice("udlr")
        if d["cool"] <= 0:
            ax, ay = abs(g.x - e.x) < 60, abs(g.y - e.y) < 60
            if ax or ay:
                d["dir"] = ("d" if g.y > e.y else "u") if ax else ("r" if g.x > e.x else "l")
                d["mode"], d["v"], d["t"] = "charge", 5.0, 0
    elif d["mode"] == "charge":
        d["v"] = min(12.0 * sp, d["v"] + 0.8)
        dx, dy = DIRS[d["dir"]]
        d["t"] += 1
        if g.move_body(e, dx * d["v"], dy * d["v"], e.r * 0.75) or d["t"] > 70:
            d["mode"], d["t"], d["cool"] = "rest", 0, 90
    else:
        d["t"] += 1
        if d["t"] > 40:
            d["mode"], d["t"] = "roam", 0
    e.face = d["dir"]
    v = d["v"] if d["mode"] == "charge" else 0.0 if d["mode"] == "rest" else 2.8 * sp
    e.vx, e.vy = DIRS[e.face][0] * v, DIRS[e.face][1] * v
    hist.append((e.x, e.y))
    if len(hist) > 160:
        del hist[:60]
    d["spawn"] -= 1
    if d["spawn"] <= 0:
        d["spawn"] = rng.randint(190, 260)
        nch = sum(1 for m in g.mobs if m.kind == "charger" and not m.dead)
        for _ in range(rng.randint(1, 2)):
            if nch < 5:
                c = g.make_mob("charger", e.x + rng.randint(-50, 50), e.y + rng.randint(-50, 50), 0.6)
                if not g.blocked(c.x, c.y, c.r * 0.8):
                    g.mobs.append(c)
                    nch += 1


def u_gurdy(g, e):
    d = e.d
    e.t -= 1
    if e.st == "idle":
        e.st, e.t = "rest", 50
    elif e.st == "rest":
        dx, dy = g.x - e.x, g.y - e.y
        n = math.hypot(dx, dy) or 1.0
        g.move_body(e, dx / n * 0.9, dy / n * 0.9, e.r * 0.5)
        if e.t <= 0:
            nfl = sum(1 for m in g.mobs if m.kind == "fly" and not m.dead)
            nboil = sum(1 for m in g.mobs if m.kind == "boil" and not m.dead)
            atk = rng.choice(["volley", "volley", "pooter", "flies", "boils"])
            if atk == "flies" and nfl > 6:
                atk = "volley"
            if atk == "boils" and nboil > 3:
                atk = "volley"
            d["atk"] = atk
            e.st, e.t = ("duck", 18) if atk == "volley" else ("cast", 22)
            if atk == "pooter":
                g.mobs.append(g.make_mob("pooter", e.x + rng.randint(-60, 60), e.y + 80, 1.0))
            elif atk == "flies":
                for sx in (-1, 1):
                    f = g.make_mob("fly", e.x + sx * 70, e.y - 60, 1.0)
                    f.hp = f.maxhp = 3
                    g.mobs.append(f)
            elif atk == "boils":
                for sx in (-1, 1):
                    bx, by = min(max(e.x + sx * 110, 60), RW - 60), min(max(e.y + 110, 60), RH - 60)
                    if not g.blocked(bx, by, 24):
                        g.mobs.append(g.make_mob("boil", bx, by, 1.0))
    elif e.st == "duck":
        if e.t <= 0:
            e.st, e.t = "fire", 22
            base = g.aim(e)
            for k in range(-2, 3):
                g.etear(e.x, e.y + 24, base + k * 0.22, 7.5, 2)
    elif e.t <= 0:
        e.st, e.t = "rest", rng.randint(28, 46)


UPD = {"fly": u_fly, "spider": u_spider, "pooter": u_pooter, "gaper": u_gaper, "horf": u_horf, "clotty": u_clotty,
       "mulligan": u_mulligan, "charger": u_charger, "host": u_host, "boil": u_boil, "monstro": u_monstro, "duke": u_duke,
       "contusion": u_contusion, "suture": u_suture, "larry": u_larry, "chub": u_chub, "gurdy": u_gurdy}


# ------------------------------------------------------------------------------------------------ drawing
PICK_SPR = {"hr": ("heart_p", 0), "hh": ("heart_p", 1), "hs": ("heart_p", 2), "bomb": ("bomb_p", 0), "key": ("key", 0)}
BEAM_OUT = rect_key((150, 20, 34))
BEAM_IN = rect_key((255, 120, 96))
BEAM_HOT = rect_key((255, 236, 220))
MINI_X, MINI_Y, MINI_W, MINI_H = 1700, 24, 22, 16
KIND_DOT = {"boss": (220, 40, 40), "treasure": (240, 210, 60), "shop": (70, 200, 90), "secret": (210, 90, 220)}


class Game2(Sim):
    def mob_items(self, e, out):
        n0 = len(out)
        self.mob_items_raw(e, out)
        if e.hit:
            for i in range(n0, len(out)):
                it = out[i]
                if it[2] == 1:
                    sp = flashed(it[8])
                    out[i] = (it[0], it[1], 1, id(sp), it[4], it[5], it[6], it[7], sp)

    def mob_items_raw(self, e, out):
        k = e.kind
        key = e.id
        rx, ry, dy = KINDS[k][1]
        a = e.anim
        if k == "monstro" and e.hidden:
            f = 0.5 + 0.5 * (1 - e.t / 9) if e.st == "down" else 0.4
            out.append(shadow_item((key, "s"), e.x, e.y, int(rx * f), int(ry * f), dy))
            return
        if k in ("larry", "chub"):
            return self.worm_items(e, out)
        out.append(shadow_item((key, "s"), e.x, e.y, rx, ry, dy))
        z = e.z
        if k == "fly":
            out.append(spr_item(self, key, "fly", a // 3, e.x, e.y, z + 4 * math.sin(a * 0.3)))
        elif k == "spider":
            out.append(spr_item(self, key, "spider", a // 3 if e.st == "run" else 0, e.x, e.y + 6))
        elif k == "pooter":
            out.append(spr_item(self, key, "pooter", 1 if e.d.get("flash") else 0, e.x, e.y, z + 3 * math.sin(a * 0.15)))
        elif k == "gaper":
            out.append(spr_item(self, key, "gaper", a // 5, e.x, e.y + 10))
        elif k == "horf":
            out.append(spr_item(self, key, "horf", 1 if e.d.get("flash") else 0, e.x, e.y, z + 3 * math.sin(a * 0.12)))
        elif k == "clotty":
            out.append(spr_item(self, key, "clotty", a // 8, e.x, e.y))
        elif k == "mulligan":
            out.append(spr_item(self, key, "mulligan", a // 6 if e.vx or e.vy else 0, e.x, e.y + 10))
        elif k == "charger":
            out.append(spr_item(self, key, "charger_" + e.face, a // 5 if e.st != "stun" else 0, e.x, e.y))
        elif k == "host":
            out.append(spr_item(self, key, "host", 1 if e.st == "open" else 0, e.x, e.y))
        elif k == "boil":
            out.append(spr_item(self, key, "boil", e.d.get("stage", 0), e.x, e.y))
        elif k == "monstro":
            f = {"crouch": 1, "spray": 2}.get(e.st, 0)
            out.append(spr_item(self, key, "monstro", f, e.x, e.y, z))
        elif k == "duke":
            out.append(spr_item(self, key, "duke", a // 3, e.x, e.y, z + 5 * math.sin(a * 0.1)))
        elif k == "contusion":
            out.append(spr_item(self, key, "contusion", a // 10, e.x, e.y))
            p = e.d["partner"]
            if not p.dead:
                for i in range(1, 8):
                    t = i / 8
                    out.append(spr_item(self, (key, "c", i), "cord", 0, e.x + (p.x - e.x) * t, e.y + (p.y - e.y) * t + 4))
        elif k == "suture":
            out.append(spr_item(self, key, "suture", a // 10, e.x, e.y))
        elif k == "gurdy":
            f = 2 if e.st == "duck" else 1 if e.st in ("fire", "cast") else 0
            out.append(spr_item(self, key, "gurdy", f, e.x, e.y))

    def worm_items(self, e, out):
        key = e.id
        if e.kind == "larry":
            lead = e.d["lead"]
            first = min(m.d["idx"] for m in self.mobs if m.kind == "larry" and not m.dead)
            name = "larry_" + lead["dir"] if e.d["idx"] == first else "larry_seg"
            out.append(shadow_item((key, "s"), e.x, e.y, 40, 11, 30))
            out.append(spr_item(self, key, name, 0, e.x, e.y))
            return
        for i, (idx, name) in enumerate(((41, "chub_seg"), (21, "chub_seg"), (1, "chub_" + e.face))):
            x, y = e.d["hist"][-idx]
            out.append(shadow_item((key, "s", i), x, y, 58, 15, 44))
            out.append(spr_item(self, (key, i), name, 0, x, y))

    def build_items(self):
        out = []
        rm = self.cur
        for (c, r), hp in rm.fire.items():
            size = 2 if hp > 4 else 1 if hp > 2 else 0
            s = ENV["fire"][size][(self.tick_n // 4 + c + r) % 4]
            out.append((r * CELL + 90, ("f", c, r), 1, id(s), WALL + c * CELL, WALL + r * CELL - 10, 100, 110, s))
        if rm.trapdoor:
            out.append(spr_item(self, "trap", "trapdoor", (self.tick_n // 10) % 2, 650, 250, 0, sort=0))
        for i, ped in enumerate(rm.pedestals):
            out.append(spr_item(self, ("p", i), "pedestal", 0, ped[0], ped[1]))
            if ped[2]:
                out.append(spr_item(self, ("pi", i), "item_" + ped[2], 0, ped[0], ped[1] - 36, 4 * math.sin(self.tick_n * 0.1) + 4,
                                    sort=ped[1] + 2))
                if ped[3]:
                    out.append(spr_item(self, ("pp", i), "price_%d" % ped[3], 0, ped[0], ped[1] + 64, 0, sort=ped[1] + 3))
        for p in rm.pickups:
            z = 8 + 3 * math.sin(p.t * 0.12)
            if p.kind == "coin":
                name, f = "coin", (p.t // 5) % 4
            else:
                name, f = PICK_SPR[p.kind]
            out.append(shadow_item((p.id, "s"), p.x, p.y, 16, 5, 14))
            out.append(spr_item(self, p.id, name, f, p.x, p.y, z))
            if p.price:
                out.append(spr_item(self, (p.id, "pr"), "price_%d" % p.price, 0, p.x, p.y + 56, 0, sort=p.y + 3))
        for b in self.bombs_l:
            out.append(shadow_item((b.id, "s"), b.x, b.y, 16, 5, 12))
            out.append(spr_item(self, b.id, "bomb", (b.t // (2 if b.t < 20 else 5)) % 2, b.x, b.y + 4))
        for e in self.mobs:
            if not e.dead:
                self.mob_items(e, out)
        self.isaac_items(out)
        for t in self.tears:
            z = t.height()
            out.append(shadow_item((t.id, "s"), t.x, t.y, 9, 4, 6))
            out.append(spr_item(self, t.id, "tear" if t.friendly else "etear", 1 if t.big else 0, t.x, t.y, z, sort=t.y + 80))
        for i, pt in enumerate(self.parts):
            if pt[5] == 1:
                out.append((pt[1] + 80, ("g", id(pt)), 2, GIB_COL[0] | GIB_COL[1] << 8, int(pt[0]) + WALL - 4, int(pt[1]) + WALL - 4, 8, 8, GIB_COL))
            else:
                s = SPR["splash" if pt[5] == 2 else "esplash"][min(3, (8 - pt[4]) // 2)]
                out.append(spr_item(self, ("sp", id(pt)), "splash" if pt[5] == 2 else "esplash", min(3, (8 - pt[4]) // 2), pt[0], pt[1], 12, sort=pt[1] + 90))
        for b in self.booms:
            out.append(spr_item(self, ("bm", id(b)), "boom", b[2] // 3, b[0], b[1] - 20, 0, sort=5000))
        if self.beam is not None:
            self.beam_items(out)
        return out

    def beam_items(self, out):
        d = self.beam["d"]
        ox, oy = int(self.x) + WALL, int(self.y) + WALL - 20
        w1 = 34 + (self.tick_n % 3) * 5
        w2 = 16 + (self.tick_n % 2) * 4
        for i, (w, col) in enumerate(((w1, BEAM_OUT), (w2, BEAM_IN), (6, BEAM_HOT))):
            if d in "ud":
                if d == "u":
                    y0, y1 = WALL, oy
                else:
                    y0, y1 = oy, SH - WALL
                out.append((self.y - 2 + i * 0.1, ("beam", i), 2, col[0] | col[1] << 8, ox - w // 2, y0, w, max(1, y1 - y0), col))
            else:
                if d == "l":
                    x0, x1 = WALL, ox
                else:
                    x0, x1 = ox, SW - WALL
                out.append((self.y - 2 + i * 0.1, ("beam", i), 2, col[0] | col[1] << 8, x0, oy - w // 2, max(1, x1 - x0), w, col))

    def isaac_items(self, out):
        x, y = self.x, self.y
        if self.dying:
            if self.dying < 12:
                out.append(spr_item(self, "isaac_h", "head_dh", 0, x, y - 20 - self.dying * 2, 0, sort=y + 2))
            out.append(shadow_item("isaac_s", x, y, 26, 8, 20))
            if self.dying >= 12:
                out.append(spr_item(self, "isaac_d", "dead", 0, x, y + 18))
            else:
                out.append(spr_item(self, "isaac_b", "body_v", 0, x, y))
            return
        if self.invuln > 0 and (self.invuln // 3) % 2:
            out.append(shadow_item("isaac_s", x, y, 26, 8, 20))
            return
        mv = math.hypot(self.vx, self.vy) > 1.0
        fr = int(self.walk) % 6 if mv else 0
        bv = "body_v" if self.move_dir in "ud" else "body_" + self.move_dir
        bob = (2.5 * abs(math.sin(self.walk * math.pi / 3 * 1.0)) if mv else 0.0)
        st = "h" if self.hurt_t > 0 else "s" if self.shoot_t > 0 else "n"
        out.append(shadow_item("isaac_s", x, y, 26, 8, 20))
        out.append(spr_item(self, "isaac_b", bv, fr, x, y))
        out.append(spr_item(self, "isaac_h", "head_" + self.face + st, 0, x, y - 40 - bob, 0, sort=y + 2))

    def update_parts(self):
        keep = []
        for p in self.parts:
            p[4] -= 1
            if p[4] <= 0:
                continue
            if p[5] == 1:
                p[0] += p[2]
                p[1] += p[3]
                p[3] += 0.9
            keep.append(p)
        self.parts = keep

    # ---------------------------------------------------------------- HUD (written straight to the screen)
    def draw_hud(self):
        k = (self.hp, self.maxhp, self.soul)
        if k != self.hud_key:
            self.hud_key = k
            fill_rect(0, 12, 700, 52, 0)
            x = 20
            for i in range(self.maxhp // 2):
                v = self.hp - 2 * i
                blit_runs(HUDS["heart_" + ("full" if v >= 2 else "half" if v == 1 else "empty")], x, 16)
                x += 46
            for i in range((self.soul + 1) // 2):
                blit_runs(HUDS["heart_soul" if self.soul - 2 * i >= 2 else "heart_soul_half"], x, 16)
                x += 46
        k = (self.coins, self.bombs_n, self.keys)
        if k != getattr(self, "res_key", None):
            self.res_key = k
            fill_rect(0, 66, 480, 50, 0)
            blit_runs(HUDS["coin"], 20, 68)
            draw_text("%02d" % self.coins, 70, 70, "S", COLOR_YELLOW)
            blit_runs(HUDS["bomb"], 170, 66)
            draw_text("%02d" % self.bombs_n, 220, 70)
            blit_runs(HUDS["key"], 320, 68)
            draw_text("%02d" % self.keys, 366, 70)
        k = (self.score, self.run, self.depth)
        if k != getattr(self, "score_key", None):
            self.score_key = k
            fill_rect(700, 12, 520, 48, 0)
            fill_rect(500, 66, 560, 48, 0)
            draw_text("SCORE %d" % self.score, 720, 16, "S", COLOR_YELLOW)
            draw_text("RUN %d  %s" % (self.run, THEME_FLOORS[min(7, self.depth - 1)]), 520, 70, "S", COLOR_CYAN)
        k = len(self.stats.items)
        if k != getattr(self, "item_key", None):
            self.item_key = k
            fill_rect(0, 1020, 800, 60, 0)
            for i, n in enumerate(self.stats.items[:12]):
                blit_runs(SPR["item_" + n][0], 20 + i * 62, 1024)
        boss = [m for m in self.mobs if m.boss]
        k = int(100 * sum(m.hp for m in boss) / sum(m.maxhp for m in boss)) if boss else -1
        if k != getattr(self, "bar_key", None):
            self.bar_key = k
            fill_rect(500, 1000, 920, 24, 0)
            if k >= 0:
                fill_rect(560, 1004, 800, 14, rgb565(240, 240, 240))
                fill_rect(563, 1007, 794, 8, rgb565(40, 8, 12))
                fill_rect(563, 1007, int(794 * k / 100), 8, rgb565(214, 38, 48))
        text, t = self.banner
        if t > 0:
            if t == 100:
                draw_text_centered(text, 1030, "S", COLOR_WHITE)
            t -= 1
            self.banner = (text, t)
            if t == 0:
                fill_rect(700, 1024, 520, 48, 0)

    def draw_minimap(self):
        cur = self.cur
        key = (cur.pos, sum(r.seen for r in self.rooms.values()), tuple(r.doors.get(d) == "hole" for r in self.rooms.values() for d in r.doors), cur.cleared)
        if key == self.mini_key:
            return
        self.mini_key = key
        fill_rect(MINI_X - 6, MINI_Y - 6, MINI_W * GRID + 12, MINI_H * GRID + 12, rgb565(12, 10, 14))
        for pos, rm in self.rooms.items():
            if not rm.seen:
                continue
            if rm.kind == "secret" and not rm.visited and not any(rm.doors.get(d) == "hole" for d in rm.doors):
                continue
            x, y = MINI_X + pos[0] * MINI_W, MINI_Y + pos[1] * MINI_H
            if rm is cur:
                col = (245, 245, 245)
            elif rm.visited:
                col = (150, 146, 158)
            else:
                col = (64, 60, 72)
            fill_rect(x + 1, y + 1, MINI_W - 2, MINI_H - 2, rgb565(*col))
            dot = KIND_DOT.get(rm.kind)
            if dot:
                fill_rect(x + MINI_W // 2 - 4, y + MINI_H // 2 - 3, 8, 6, rgb565(*dot))
            elif rm.visited and not rm.cleared:
                fill_rect(x + MINI_W // 2 - 2, y + MINI_H // 2 - 2, 4, 4, rgb565(220, 60, 60))

    # ---------------------------------------------------------------- room transitions
    def enter_room(self, pos, entry):
        sliding = entry is not None and self.phase == "play" and self.cur is not None
        old = None
        if sliding:
            # Isaac walks into the new room, so the outgoing picture must not show him a second time
            items = [it for it in self.build_items() if not (isinstance(it[1], str) and it[1].startswith("isaac"))]
            self.r.render(items, to_fb=False)
            old = bytes(self.r.frame)
        super().enter_room(pos, entry)
        if sliding:
            self.r.render(self.build_items(), to_fb=False)
            self.slide = (old, bytes(self.r.frame), entry, 0)
            self.phase = "slide"

    def slide_step(self):
        # the old and the new room are stitched edge to edge and the screen window scrolls across them
        old, new, d, t = self.slide
        total = 12
        t += 1
        k = t / total
        e = k * k * (3 - 2 * k)
        if d in "ud":
            o = int(SH * e)
            for j in range(SH):
                if d == "u":
                    src, sj = (new, SH - o + j) if j < o else (old, j - o)
                else:
                    src, sj = (old, j + o) if j < SH - o else (new, j - (SH - o))
                a = sj * FS
                fb[(SY + j) * S + SX * 2:(SY + j) * S + SX * 2 + FS] = src[a:a + FS]
        else:
            o = int(SW * e) * 2
            for j in range(SH):
                a = j * FS
                if d == "l":
                    row = new[a + FS - o:a + FS] + old[a:a + FS - o]
                else:
                    row = old[a + o:a + FS] + new[a:a + o]
                fb[(SY + j) * S + SX * 2:(SY + j) * S + SX * 2 + FS] = row
        self.slide = (old, new, d, t)
        if t >= total:
            self.phase = "play"
            self.slide = None
            self.r.full = True
            self.hud_key = None

    # ---------------------------------------------------------------- stall recovery
    def recover_from_stall(self):
        # Last line of defence: nothing scored for over a minute, so some enemy is unreachable or the bot has no plan.
        self.prog_t = self.tick_n
        if self.mobs:
            for m in list(self.mobs):
                if m.boss:
                    m.hp -= m.maxhp * 0.35
                if m.hp <= 0 or not m.boss:
                    self.kill_mob(m)
            self.mobs[:] = [m for m in self.mobs if not m.dead]
        else:
            self.keys += 1
            self.bombs_n += 1
            rm = self.cur
            for d, st in list(rm.doors.items()):
                if st in ("locked", "hidden"):
                    n = self.rooms[(rm.pos[0] + DIRS[d][0], rm.pos[1] + DIRS[d][1])]
                    rm.doors[d] = n.doors[OPP[d]] = "open" if st == "locked" else "hole"
            self.bake_doors()
        self.bot.route = None

    # ---------------------------------------------------------------- main loop
    def tick(self):
        self.tick_n += 1
        if self.over:
            return self.end.tick()
        if self.score >= TARGET_SCORE or self.tick_n >= CAP_TICKS - 30:
            self.over = True
            self.end.start(self.score, "VICTORY" if self.score >= TARGET_SCORE else "GAME OVER")
            return False
        if self.phase == "slide":
            self.slide_step()
            if self.phase == "play":
                self.draw_hud()
                self.draw_minimap()
            return False
        if self.phase == "card":
            if self.phase_t == 0:
                fill_rect(SX, SY, SW, SH, 0)
                fill_rect(MINI_X - 6, MINI_Y - 6, MINI_W * GRID + 12, MINI_H * GRID + 12, 0)
                fill_rect(500, 1000, 920, 24, 0)
                self.banner = ("", 0)
                self.bar_key = None
                self.prog_t = self.tick_n
                draw_text_centered(self.card_name, 440, "L", COLOR_YELLOW)
                draw_text_centered("RUN %d" % self.run, 560, "L", COLOR_WHITE)
                if self.run > 1 and self.depth == 1:
                    draw_text_centered("YOU DIED", 330, "L", COLOR_RED)
                self.hud_key = self.res_key = self.score_key = self.item_key = None
                self.draw_hud()
            self.phase_t += 1
            if self.phase_t > 50:
                self.phase = "play"
                self.x, self.y = RW / 2, RH / 2
                self.enter_room((4, 4), None)
                self.mini_key = None
            return False
        self.step_play()
        return False

    def step_play(self):
        mx, my, fire, bomb = self.bot.decide()
        self.update_isaac(mx, my, fire, bomb)
        if self.dying:
            if self.dying > 80:
                self.new_run()
                return
        self.update_mobs()
        self.update_tears()
        self.update_bombs()
        self.update_parts()
        self.update_pickups()
        if self.phase != "play":
            return
        prog = (self.score, self.cur.pos, self.depth, self.run)
        if prog != self.prog:
            self.prog, self.prog_t = prog, self.tick_n
        elif self.tick_n - self.prog_t > 1900:
            self.recover_from_stall()
        rm = self.cur
        if not rm.cleared and rm.kind in ("normal", "boss") and not self.mobs:
            self.clear_room()
        if not self.dying:
            self.try_doors()
        if self.phase != "play" or self.phase_t < 0:
            return
        self.r.render(self.build_items())
        self.draw_hud()
        self.draw_minimap()


def make():
    g = Game2()
    g.bot = Bot(g)
    return g.tick


# ------------------------------------------------------------------------------------------------ the bot
_DIRS8 = [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (0.707, 0.707), (0.707, -0.707), (-0.707, 0.707), (-0.707, -0.707)]
# slow candidates let the bot creep up to a spot without overshooting it by a whole sampling horizon
CANDS = [(0.0, 0.0)] + _DIRS8 + [(x * 0.35, y * 0.35) for x, y in _DIRS8]
K, DT = 7, 2.0
PRIO = {"charger": 3.0, "fly": 2.4, "spider": 2.5, "gaper": 2.7, "pooter": 1.6, "horf": 1.6, "clotty": 1.6, "mulligan": 1.2,
        "host": 2.2, "boil": 1.0, "monstro": 2.4, "duke": 1.8, "contusion": 2.0, "suture": 2.6, "larry": 2.2, "chub": 2.2,
        "gurdy": 2.2}
KEEP = {"gaper": 270, "fly": 250, "spider": 280, "charger": 340, "pooter": 260, "horf": 260, "clotty": 280, "mulligan": 230,
        "host": 300, "boil": 200, "monstro": 400, "duke": 380, "contusion": 420, "suture": 360, "larry": 340, "chub": 440,
        "gurdy": 400}
LANE_GOAL = {"u": (RW / 2, -26), "d": (RW / 2, RH + 26), "l": (-26, RH / 2), "r": (RW + 26, RH / 2)}
WALL_BOMB_SPOT = {"u": (RW / 2, 80), "d": (RW / 2, RH - 80), "l": (80, RH / 2), "r": (RW - 80, RH / 2)}


class Bot:
    def __init__(self, g):
        self.g = g
        self.prev = (0.0, 0.0)
        self.held = None
        self.slip = 0
        self.route = None
        self.route_key = None
        self.route_t = -99
        self.bomb_now = False
        self.shoot_cell = None
        self.last_pos = (0, 0)
        self.last_move_t = 0
        self.wander_t = 0
        self.wander_dir = (0, 0)
        self.room_enter_t = 0
        self.room_id = None

    # ------------------------------------------------------------------ entry
    def decide(self):
        g = self.g
        if g.dying:
            return 0.0, 0.0, None, False
        rm = g.cur
        if self.room_id is not rm:
            self.room_id = rm
            self.room_enter_t = g.tick_n
            self.route = None
        mobs = [e for e in g.mobs if not e.dead]
        targets = [e for e in mobs if not e.inv and not e.hidden]
        self.bomb_now = False
        self.shoot_cell = None
        goal, gw = None, 0.0
        self.tgt = None
        cands = [e for e in mobs if not e.hidden]
        if cands:
            # an invulnerable enemy (closed host) is still worth lining up on, but only when nothing else is shootable
            self.tgt = max(cands, key=lambda e: PRIO.get(e.kind, 1.5) * (0.3 if e.inv else 1.0)
                           / (1 + math.hypot(e.x - g.x, e.y - g.y) / 500))
        if mobs:
            goal, gw = self.combat_goal(mobs)
        else:
            goal, gw = self.cleared_goal()
        fire = self.pick_fire(targets)
        if fire is None and self.shoot_cell is not None:
            fire = self.fire_at_cell(self.shoot_cell)
        # the move is re-planned every fourth tick: a human-like reaction delay, and it keeps the bot cheap
        if self.slip > 0:
            self.slip -= 1
        elif g.tick_n % 4 == 0 or self.held is None:
            self.held = self.choose_move(mobs, targets, goal, gw)
            if mobs and rng.random() < 0.035:
                # now and then the bot loses a fraction of a second, like a person glancing at the minimap
                self.slip = rng.randint(8, 16)
        mv = self.held
        self.watch_progress(mv, goal)
        mv = self.apply_wander(mv)
        self.prev = mv
        bomb = self.bomb_now or self.boss_bomb(mobs)
        return mv[0], mv[1], fire, bomb

    # ------------------------------------------------------------------ aiming
    def pick_fire(self, targets):
        g = self.g
        if not targets:
            return None
        st = g.stats
        rng_px = TEAR_SPEED * st.life()
        best, bs = None, 0.0
        near_best, nb = None, 1e9
        ivx, ivy = g.vx, g.vy
        for d, (dx, dy) in DIRS.items():
            for e in targets:
                for cx, cy, cr in colliders(e):
                    rx, ry = cx - g.x, cy - g.y
                    fw = rx * dx + ry * dy
                    if fw < 10 or fw > rng_px:
                        continue
                    along = ivx * dx + ivy * dy
                    t = fw / (TEAR_SPEED + 0.3 * along)
                    lat = rx * dy - ry * dx
                    drift = (ivx * dy - ivy * dx) * 0.3 * t
                    elat = (e.mvx * dy - e.mvy * dx) * t
                    miss = abs(lat + elat - drift)
                    if not st.spectral and not g.los(g.x, g.y, cx, cy):
                        continue
                    pr = PRIO.get(e.kind, 1.5) / (1 + fw / 600)
                    if miss < cr + TEAR_R - 2:
                        if pr > bs:
                            best, bs = d, pr
                    elif miss < nb:
                        near_best, nb = d, miss
        if best:
            return best
        if st.laser:
            return None
        if near_best is None:
            # nothing in front of any gun: face the nearest enemy anyway so the shot lands once it walks into the line
            e = min(targets, key=lambda m: (m.x - g.x) ** 2 + (m.y - g.y) ** 2)
            dx, dy = e.x - g.x, e.y - g.y
            near_best = ("r" if dx > 0 else "l") if abs(dx) > abs(dy) else ("d" if dy > 0 else "u")
        return near_best

    def fire_at_cell(self, cell):
        g = self.g
        cx, cy = cell_center(*cell)
        dx, dy = cx - g.x, cy - g.y
        if abs(dx) < 36 and abs(dy) > 10:
            return "d" if dy > 0 else "u"
        if abs(dy) < 36 and abs(dx) > 10:
            return "r" if dx > 0 else "l"
        return None

    # ------------------------------------------------------------------ goals
    def combat_goal(self, mobs):
        g = self.g
        # heal when low and a heart is within reach
        if g.hp <= 2 or g.hp < g.maxhp - 1:
            best, bd = None, 330.0
            for p in g.cur.pickups:
                if p.kind in ("hr", "hh", "hs") and not p.price and (p.kind == "hs" or g.hp < g.maxhp):
                    d = math.hypot(p.x - g.x, p.y - g.y)
                    if d < bd:
                        best, bd = p, d
            if best is not None:
                return (best.x, best.y), 0.7
        # an enemy that sits behind rocks or far away must be hunted down, otherwise the room never ends
        t = self.tgt
        if t is None:
            return None, 0.0
        if not t.boss and not g.los(g.x, g.y, t.x, t.y):
            return self.nav((t.x, t.y)), 0.8
        ag = self.align_goal(t)
        return (self.nav(ag), 1.1) if ag is not None else (None, 0.0)

    def align_goal(self, t):
        # nearest spot on one of the target's four cardinal lines at a comfortable shooting distance
        g = self.g
        dk = KEEP.get(t.kind, 300)
        if g.tick_n - self.room_enter_t > 900 and not t.boss:
            dk = 180
        dx, dy = t.x - g.x, t.y - g.y
        dist = math.hypot(dx, dy)
        if min(abs(dx), abs(dy)) < 22 and dk * 0.55 < dist < dk * 1.7 and min(g.x, RW - g.x, g.y, RH - g.y) > 85:
            return None
        # first look for a spot well away from the walls (a bot pinned against a wall cannot dodge), then settle for any
        for margin in (110, ISAAC_R + 2):
            best, bd = None, 1e9
            for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for D in (dk, dk * 0.7, dk * 0.5):
                    x = min(max(t.x + sx * D, margin), RW - margin)
                    y = min(max(t.y + sy * D, margin), RH - margin)
                    if abs(x - t.x) > 30 and abs(y - t.y) > 30 and margin > ISAAC_R + 2:
                        continue
                    if g.blocked(x, y, ISAAC_R) or not g.los(x, y, t.x, t.y) or self.hazard_at(x, y):
                        continue
                    cost = math.hypot(x - g.x, y - g.y)
                    if abs(x - t.x) > 30 and abs(y - t.y) > 30:
                        cost += 400
                    if cost < bd:
                        best, bd = (x, y), cost
            if best is not None:
                return best
        return None

    def hazard_at(self, x, y):
        g = self.g
        c, r = int(min(max(x, 0), RW - 1) // CELL), int(min(max(y, 0), RH - 1) // CELL)
        if g.cur.grid[r][c] == "S":
            return True
        return any(math.hypot(cell_center(fc, fr)[0] - x, cell_center(fc, fr)[1] - y) < 100 for (fc, fr) in g.cur.fire)

    def want_pickup(self, p):
        g = self.g
        if p.price:
            if g.coins < p.price:
                return False
            if p.kind in ("hr", "hh"):
                return g.hp < g.maxhp
            if p.kind == "key":
                return g.keys < 2
            if p.kind == "bomb":
                return g.bombs_n < 3
            return True
        if p.kind in ("hr", "hh"):
            return g.hp < g.maxhp
        return True

    def cleared_goal(self):
        g = self.g
        rm = g.cur
        px, py = g.x, g.y
        best, bd = None, 1e9
        for p in rm.pickups:
            if self.want_pickup(p):
                d = math.hypot(p.x - px, p.y - py)
                if d < bd:
                    best, bd = (p.x, p.y), d
        for ped in rm.pedestals:
            if ped[2] and (not ped[3] or g.coins >= ped[3]):
                d = math.hypot(ped[0] - px, ped[1] - 10 - py)
                if d < bd:
                    best, bd = (ped[0], ped[1] - 10), d
        if best is not None:
            return self.nav(best), 1.0
        if rm.trapdoor and not self.boss_loot_left():
            return self.nav((650, 250)), 1.0
        target = self.target_room()
        if target == rm.pos and g.secret_pos:
            for d, st in rm.doors.items():
                if st == "hidden" and (rm.pos[0] + DIRS[d][0], rm.pos[1] + DIRS[d][1]) == g.secret_pos:
                    spot = WALL_BOMB_SPOT[d]
                    if math.hypot(spot[0] - px, spot[1] - py) < 45:
                        if g.bombs_n > 0:
                            self.bomb_now = True
                        return None, 0.0
                    return self.nav(spot), 1.0
        if target is None or target == rm.pos:
            if rm.trapdoor:
                return self.nav((650, 250)), 1.0
            return None, 0.0
        step = self.next_room_step(target)
        if step is None:
            return None, 0.0
        # the secret wall must be bombed before it can be crossed
        if rm.doors.get(step) == "hidden":
            spot = WALL_BOMB_SPOT[step]
            if math.hypot(spot[0] - px, spot[1] - py) < 45:
                if g.bombs_n > 0:
                    self.bomb_now = True
                return None, 0.0
            return self.nav(spot), 1.0
        gx, gy = LANE_GOAL[step]
        return self.nav((gx, gy)), 1.0

    def boss_loot_left(self):
        rm = self.g.cur
        return any(p[2] for p in rm.pedestals) or any(self.want_pickup(p) for p in rm.pickups)

    def target_room(self):
        g = self.g
        rooms = g.rooms
        here = g.cur.pos
        dist = self.room_dists(here, allow_hidden=False)
        floor_time = g.tick_n - g.floor_start
        def reach(p):
            return p in dist
        # treasure room first: items make everything after it easier
        for pos, r in rooms.items():
            if r.kind == "treasure" and not r.visited and reach(pos):
                return pos
        normals = [p for p, r in rooms.items() if r.kind in ("normal", "start") and not r.visited and reach(p)]
        if normals and floor_time < 5200:
            return min(normals, key=lambda p: dist[p])
        for pos, r in rooms.items():
            if r.kind == "shop" and not r.visited and reach(pos) and g.coins >= 5:
                return pos
        if g.bombs_n > 0 and g.secret_pos and not rooms[g.secret_pos].visited and floor_time < 5200:
            sp = g.secret_pos
            if any(rooms[sp].doors.get(d) == "hole" for d in rooms[sp].doors):
                if sp in dist:
                    return sp
            else:
                cand = []
                for d, (dx, dy) in DIRS.items():
                    q = (sp[0] + dx, sp[1] + dy)
                    r = rooms.get(q)
                    if r and r.visited and q in dist:
                        cand.append((dist[q], q))
                if cand:
                    return min(cand)[1]
        for pos, r in rooms.items():
            if r.kind == "boss" and reach(pos):
                return pos
        return None

    def room_dists(self, start, allow_hidden):
        g = self.g
        dist = {start: 0}
        q = [start]
        for pos in q:
            r = g.rooms[pos]
            for d, st in r.doors.items():
                if st == "hidden" and not allow_hidden:
                    continue
                if st == "locked" and g.keys <= 0:
                    continue
                n = (pos[0] + DIRS[d][0], pos[1] + DIRS[d][1])
                if n not in dist:
                    dist[n] = dist[pos] + 1
                    q.append(n)
        return dist

    def next_room_step(self, target):
        g = self.g
        here = g.cur.pos
        # BFS from the target back to here so the first step is the door to take (hidden walls count: they can be bombed)
        dist = self.room_dists(target, allow_hidden=False)
        if here not in dist:
            dist = self.room_dists(target, allow_hidden=True)
        best, bd = None, 999
        for d, st in g.cur.doors.items():
            if st == "locked" and g.keys <= 0:
                continue
            if st == "hidden" and here in self.room_dists(target, allow_hidden=False):
                continue
            n = (here[0] + DIRS[d][0], here[1] + DIRS[d][1])
            if n in dist and dist[n] < bd:
                best, bd = d, dist[n]
        return best

    # ------------------------------------------------------------------ navigation inside a room
    def nav(self, goal):
        # direct line when it is clear, else follow a cell path around obstacles
        g = self.g
        gx, gy = goal
        if self.clear_line(g.x, g.y, gx, gy):
            return goal
        key = (int(gx) // 20, int(gy) // 20)
        if self.route is None or key != self.route_key or g.tick_n - self.route_t > 20:
            self.route = self.cell_path(goal)
            self.route_key = key
            self.route_t = g.tick_n
        if not self.route:
            return goal
        # skip waypoints already reached, aim at the farthest one that is still in a clear line
        while len(self.route) > 1 and math.hypot(self.route[0][0] - g.x, self.route[0][1] - g.y) < 45:
            self.route.pop(0)
        wp = self.route[0]
        for q in self.route[1:3]:
            if self.clear_line(g.x, g.y, q[0], q[1]):
                wp = q
        return wp

    def clear_line(self, x0, y0, x1, y1):
        g = self.g
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d // 28))
        grid = g.cur.grid
        for i in range(1, n + 1):
            t = i / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if y < -5 or y > RH + 5 or x < -5 or x > RW + 5:
                continue
            c, r = int(min(max(x, 0), RW - 1) // CELL), int(min(max(y, 0), RH - 1) // CELL)
            for dc in (-1, 0, 1) if abs(x1 - x0) < abs(y1 - y0) else (0,):
                for dr in (-1, 0, 1) if abs(x1 - x0) >= abs(y1 - y0) else (0,):
                    cc, rr = c + dc, r + dr
                    if 0 <= cc < COLS and 0 <= rr < ROWS and grid[rr][cc] in "ROFPS":
                        if math.hypot(cell_center(cc, rr)[0] - x, cell_center(cc, rr)[1] - y) < 82:
                            return False
        return True

    def cell_path(self, goal):
        g = self.g
        grid = g.cur.grid
        gc, gr = to_cell(min(max(goal[0], 0), RW - 1), min(max(goal[1], 0), RH - 1))
        sc, sr = to_cell(min(max(g.x, 0), RW - 1), min(max(g.y, 0), RH - 1))
        cost = {"R": None, "P": None, ".": 1, "S": None, "O": 9, "F": 14}
        import heapq
        pq = [(0, sc, sr)]
        best = {(sc, sr): 0}
        prev = {}
        while pq:
            dcur, c, r = heapq.heappop(pq)
            if (c, r) == (gc, gr):
                break
            if dcur > best.get((c, r), 1e9):
                continue
            for dx, dy in DIRS.values():
                n = (c + dx, r + dy)
                if not (0 <= n[0] < COLS and 0 <= n[1] < ROWS):
                    continue
                k = cost[grid[n[1]][n[0]]]
                if k is None:
                    continue
                nd = dcur + k
                if nd < best.get(n, 1e9):
                    best[n] = nd
                    prev[n] = (c, r)
                    heapq.heappush(pq, (nd, n[0], n[1]))
        if (gc, gr) not in best:
            return []
        path = []
        cur = (gc, gr)
        while cur != (sc, sr):
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        out = []
        for i, (c, r) in enumerate(path):
            ch = grid[r][c]
            if ch in "OF" and self.shoot_cell is None:
                # something shootable is in the way: stop in the previous cell and shoot it down
                self.shoot_cell = (c, r)
                if i == 0:
                    return [(g.x, g.y)]
                break
            out.append(cell_center(c, r))
        if not out:
            out = [goal]
        elif self.shoot_cell is None:
            out.append(goal)
        return out

    # ------------------------------------------------------------------ movement
    def choose_move(self, mobs, targets, goal, gw):
        g = self.g
        sp = g.stats.speed_px()
        inv = g.invuln > 14
        thr = []
        tear_scale = 0.25 if inv else 1.0
        for t in g.tears:
            if t.friendly:
                continue
            dx, dy = t.x - g.x, t.y - g.y
            d2 = dx * dx + dy * dy
            if d2 > 380 * 380 or (dx * t.vx + dy * t.vy > 0 and d2 > 110 * 110):
                continue
            pos = []
            for k in range(1, K + 1):
                tq = DT * k
                pos.append((t.x + t.vx * tq, t.y + t.vy * tq) if t.age + tq < t.life else None)
            thr.append((pos, ISAAC_R + TEAR_R - 1, 4000 * tear_scale))
        near_mobs = []
        for e in mobs:
            if e.hidden and e.kind != "monstro":
                continue
            if e.kind == "monstro" and e.st in ("up", "air", "down", "crouch"):
                thr.append(([(e.x, e.y)] * K, 150, 3500))
                continue
            if not e.contact and e.kind not in ("host",):
                continue
            for cx, cy, cr in colliders(e):
                dd = math.hypot(cx - g.x, cy - g.y)
                if dd > 420:
                    continue
                vx, vy = e.mvx, e.mvy
                w = 2600 * (e.contact / 2.0 if e.contact else 0.0) * tear_scale
                if w <= 0:
                    continue
                # fast movers (charges) are projected twice as far so the bot leaves their lane early
                lead = 2.0 if vx * vx + vy * vy > 64 else 1.0
                pos = [(cx + vx * DT * k * lead, cy + vy * DT * k * lead) for k in range(1, K + 1)]
                thr.append((pos, ISAAC_R + cr * 0.9 + 4, w))
                if e.kind not in ("boil",):
                    near_mobs.append((cx, cy, cr, dd))
        fires = [cell_center(c, r) for (c, r) in g.cur.fire if g.cur.grid[r][c] == "F"]
        bombs = [(b.x, b.y) for b in g.bombs_l]
        tgt = self.tgt
        dk = KEEP.get(tgt.kind, 320) if tgt else 0
        if tgt is not None and g.tick_n - self.room_enter_t > 900 and not tgt.boss:
            dk = 150
        grid = g.cur.grid
        crowd = any(dd < 320 for (_, _, _, dd) in near_mobs)
        best, bc = (0.0, 0.0), 1e18
        for (cx, cy) in CANDS:
            px, py = g.x, g.y
            cost = 0.0
            mind = 1e9
            for k in range(K):
                nx, ny = px + cx * sp * DT, py + cy * sp * DT
                if g.blocked(nx, ny, ISAAC_R):
                    if cx and not g.blocked(nx, py, ISAAC_R):
                        ny = py
                    elif cy and not g.blocked(px, ny, ISAAC_R):
                        nx = px
                    else:
                        nx, ny = px, py
                        cost += 20
                px, py = nx, ny
                if goal is not None:
                    mind = min(mind, math.hypot(goal[0] - px, goal[1] - py))
                f = 1.0 - k / (K + 3.0)
                for pos, rad, w in thr:
                    q = pos[k]
                    if q is not None:
                        ddx, ddy = q[0] - px, q[1] - py
                        if ddx * ddx + ddy * ddy < rad * rad:
                            cost += w * f
                for fx, fy in fires:
                    if (fx - px) ** 2 + (fy - py) ** 2 < 85 * 85:
                        cost += 4000
                for bx, by in bombs:
                    d = math.hypot(bx - px, by - py)
                    if d < BLAST_R + 55:
                        cost += 2500 + (BLAST_R + 55 - d) * 6
                c, r = int(min(max(px, 0), RW - 1) // CELL), int(min(max(py, 0), RH - 1) // CELL)
                if grid[r][c] == "S":
                    cost += 3000
            # walls and corners trap the bot against melee enemies
            at_goal = goal is not None and math.hypot(goal[0] - px, goal[1] - py) < 70
            if mobs and not at_goal:
                m = 90.0
                ww = 3.0 if crowd else 0.8
                for dist_wall in (px, RW - px, py, RH - py):
                    if dist_wall < m:
                        cost += (m - dist_wall) * ww
            if tgt is not None and goal is None:
                dx, dy = tgt.x - px, tgt.y - py
                dist = math.hypot(dx, dy)
                if dist < dk:
                    cost += (dk - dist) * 1.6
                elif dist > dk + 120:
                    cost += (dist - dk - 120) * 0.35
            for (cx2, cy2, cr, dd) in near_mobs:
                d = math.hypot(cx2 - px, cy2 - py)
                if d < 230:
                    cost += (230 - d) * 1.2
            if goal is not None:
                # closest approach along the path, not the end point: one 100 px sample must not overshoot a nearby goal
                cost += (mind * 0.8 + math.hypot(goal[0] - px, goal[1] - py) * 0.25) * gw * 1.4
            if (cx, cy) == self.prev:
                cost -= 18
            if cost < bc:
                best, bc = (cx, cy), cost
        return best

    def watch_progress(self, mv, goal):
        g = self.g
        if goal is None or g.tick_n - self.last_move_t < 60:
            return
        self.last_move_t = g.tick_n
        if math.hypot(g.x - self.last_pos[0], g.y - self.last_pos[1]) < 25:
            # stuck: forget the plan and shake loose in a random direction for a moment
            self.route = None
            self.wander_t = 24
            a = rng.uniform(0, 6.283)
            self.wander_dir = (math.cos(a), math.sin(a))
        self.last_pos = (g.x, g.y)

    def apply_wander(self, mv):
        if self.wander_t > 0:
            self.wander_t -= 1
            if not self.g.mobs:
                return self.wander_dir
        return mv

    def boss_bomb(self, mobs):
        g = self.g
        if g.bombs_n < 2 or g.bombs_l:
            return False
        for e in mobs:
            if e.boss and e.kind in ("gurdy", "chub", "monstro", "contusion"):
                d = math.hypot(e.x - g.x, e.y - g.y)
                if e.r + 40 < d < BLAST_R + e.r * 0.4 and math.hypot(e.vx, e.vy) < 3.5:
                    return True
        return False
