# Red Ball: a self-playing run through the Red Ball 4 idiom (grass hills, box factory, lava and ice, three big-square
# bosses). One physics core is shared by the game and by the bot's look-ahead simulation, so the bot jumps where the
# real ball would land. Rendering is a frame buffer composed from scanline slices of parallax strips, runs of terrain
# tiles and span sprites, written to the framebuffer once per tick.
from fbcore import *
import math

T = 60                      # tile size in pixels
NROWS = 18
GT = 13                     # row of the ground surface in every chunk
R = 26                      # ball radius
SUB = 2                     # physics sub-steps per tick
GRAV, FALL_MAX = 0.40, 13.0
ACC_G, ACC_A, VMAX = 0.21, 0.13, 5.4
FR_G, FR_ICE, ACC_ICE = 0.04, 0.003, 0.05
JUMP_V = 10.95
SPRING_V = 16.5
COYOTE = 5
PUSH_V = 2.0
ERR_RATE = 0.07            # chance that a planned jump is mistimed, like a human misjudging it
BOTTOM = NROWS * T + 70     # below this the ball has fallen out of the world
LEVEL_TICKS = 80 * TICK_RATE
BOSS_TICKS = 100 * TICK_RATE

A = None
fr = bytearray(S * H)
SKY_H = 400                 # rows of the slowest background band: it is only rewritten when its scroll offset changes
DIRTY = bytearray(SKY_H)    # sky rows that something other than the sky was drawn on this frame
_ONES = b"\x01" * SKY_H


def mark_rows(y0, y1):
    y0, y1 = max(0, y0), min(SKY_H, y1)
    if y1 > y0:
        DIRTY[y0:y1] = _ONES[:y1 - y0]


def conv_tree(v):
    # span sprites are stored as parallel lists; turn them into (w, h, [(offset, bytes, length)]) for the blitter
    if isinstance(v, dict):
        if "b" in v and "y" in v and "w" in v:
            return (v["w"], v["h"], [(dy * S + xo * 2, b, len(b)) for dy, xo, b in zip(v["y"], v["x"], v["b"])])
        return {k: conv_tree(x) for k, x in v.items()}
    if isinstance(v, list):
        return [conv_tree(x) for x in v]
    return v


def load_art():
    global A
    if A is None:
        A = conv_tree(load_bundle("g_redball.bin"))
    return A


def put(sp, x, y):
    # Sprites are runs of opaque spans; the fast path has no clipping, the slow one trims each span to the screen.
    w, h, rows = sp
    x, y = int(x), int(y)
    if y < SKY_H:
        mark_rows(y, y + h)
    if x >= 0 and y >= 0 and x + w <= W and y + h <= H:
        base = y * S + x * 2
        for o, b, n in rows:
            o += base
            fr[o:o + n] = b
        return
    if x >= W or y >= H or x + w <= 0 or y + h <= 0:
        return
    for o, b, n in rows:
        dy, xo = divmod(o, S)
        xo //= 2
        yy = y + dy
        if yy < 0 or yy >= H:
            continue
        a, e = x + xo, x + xo + n // 2
        if a < 0:
            b, a = b[-a * 2:], 0
        if e > W:
            b, e = b[:(W - a) * 2], W
        if e > a:
            fr[yy * S + a * 2:yy * S + a * 2 + len(b)] = b


def put_clip_y(sp, x, y, ymax):
    # like put() but drops rows at or below ymax: gates sink into the ground instead of overlapping it
    w, h, rows = sp
    x, y = int(x), int(y)
    if y < SKY_H:
        mark_rows(y, y + h)
    for o, b, n in rows:
        dy, xo = divmod(o, S)
        yy = y + dy
        if yy < 0 or yy >= H or yy >= ymax:
            continue
        xo //= 2
        a, e = x + xo, x + xo + n // 2
        if a < 0:
            b, a = b[-a * 2:], 0
        if e > W:
            b, e = b[:(W - a) * 2], W
        if e > a:
            fr[yy * S + a * 2:yy * S + a * 2 + len(b)] = b


def rect_fill(x0, y0, x1, y1, c565):
    x0, x1, y0, y1 = max(0, int(x0)), min(W, int(x1)), max(0, int(y0)), min(H, int(y1))
    if x1 <= x0:
        return
    if y0 < SKY_H:
        mark_rows(y0, y1)
    row = c565.to_bytes(2, "little") * (x1 - x0)
    for y in range(y0, y1):
        o = y * S + x0 * 2
        fr[o:o + len(row)] = row


_IBLK = {}


def interior_block(tileset, off):
    # one tile row of plain interior terrain for a given sub-tile scroll offset, as a block of 60 full screen lines
    key = (tileset, off)
    b = _IBLK.get(key)
    if b is None:
        tl = A["tiles"][tileset]["0_0"]
        b = _IBLK[key] = b"".join((tl[j] * 34)[off * 2:off * 2 + S] for j in range(T))
    return b


def text_w(s, bank):
    return sum(bank[c][0] for c in s)


def draw_str(s, x, y, bank):
    for c in s:
        g = bank[c]
        put(g, x, y)
        x += g[0]


# ------------------------------------------------------------------------------------------------------ level
SOLID = {"#": 1, "I": 2, ">": 3, "<": 4}


class Mover:
    # anything whose position is a pure function of time: the bot can look ahead without copying world state
    pass


class Saw(Mover):
    def __init__(s, x1, y1, x2, y2, sp):
        s.x1, s.y1, s.x2, s.y2, s.sp = x1 * T, y1 * T, x2 * T, y2 * T, sp
        s.L = max(1.0, math.hypot(s.x2 - s.x1, s.y2 - s.y1))
        s.x = (s.x1 + s.x2) / 2

    def pos(s, ts):
        d = (s.sp * ts) % (2 * s.L)
        if d > s.L:
            d = 2 * s.L - d
        f = d / s.L
        return s.x1 + (s.x2 - s.x1) * f, s.y1 + (s.y2 - s.y1) * f


class Plat(Mover):
    # solid moving platform 150x26; (x, top) are the centre x and the top surface of the platform
    def __init__(s, x1, y1, x2, y2, sp):
        s.x1, s.y1, s.x2, s.y2, s.sp = x1 * T, y1 * T, x2 * T, y2 * T, sp
        s.L = max(1.0, math.hypot(s.x2 - s.x1, s.y2 - s.y1))
        s.x = (s.x1 + s.x2) / 2
        s.w, s.h = 150, 26

    def pos(s, ts):
        d = (s.sp * ts) % (2 * s.L)
        if d > s.L:
            d = 2 * s.L - d
        f = d / s.L
        return s.x1 + (s.x2 - s.x1) * f, s.y1 + (s.y2 - s.y1) * f

    def shape(s, ts):
        x, y = s.pos(ts)
        x2, y2 = s.pos(ts + 1)
        return (0, x - 75, y, x + 75, y + 26, 1, x2 - x, y2 - y)


class Crusher(Mover):
    def __init__(s, x, y0, drop, period, phase):
        s.x, s.y0, s.drop, s.period, s.phase = x * T + 60, y0 * T, drop, period, phase
        s.up = period - 72

    def head_y(s, tk):
        p = (tk + s.phase) % s.period
        if p < s.up:
            return s.y0
        if p < s.up + 8:
            return s.y0 + s.drop * (p - s.up) / 8
        if p < s.up + 32:
            return s.y0 + s.drop
        return s.y0 + s.drop * (1 - (p - s.up - 32) / 40)


class Laser(Mover):
    def __init__(s, x, y, d, period, on, phase, W):
        s.period, s.on, s.phase, s.d = period, on, phase, d
        cx, cy = x * T + 30, y * T + 30
        dx, dy = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}[d]
        tx, ty = x + dx, y + dy
        while 0 <= tx < W.nt and 0 <= ty < NROWS and W.sol[ty][tx] == 0:
            tx, ty = tx + dx, ty + dy
        s.cx, s.cy = cx, cy
        if dx:
            xa, xb = sorted((cx + dx * 30, (tx + (1 if dx < 0 else 0)) * T))
            s.rect = (xa, cy - 7, xb, cy + 7)
        else:
            ya, yb = sorted((cy + dy * 30, (ty + (1 if dy < 0 else 0)) * T))
            s.rect = (cx - 7, ya, cx + 7, yb)
        s.x = cx

    def active(s, tk):
        return (tk + s.phase) % s.period < s.on

    def warn(s, tk):
        p = (tk + s.phase) % s.period
        return p >= s.period - 18 and (int(tk) // 3) % 2 == 0


class Cannon(Mover):
    BV = 3.4

    def __init__(s, x, y, d, period, phase, W):
        s.cx, s.cy, s.dir, s.period, s.phase = x * T + 30, y * T + 30, 1 if d == "R" else -1, period, phase
        s.x = s.cx
        tx = x + s.dir
        while 0 <= tx < W.nt and W.sol[y][tx] == 0:
            tx += s.dir
        s.range = abs((tx + (0 if s.dir < 0 else 0)) * T + (T if s.dir < 0 else 0) - s.cx) - 36

    def bullets(s, tk):
        out = []
        k = int((tk - s.phase) // s.period)
        for kk in (k, k - 1, k - 2):
            t0 = kk * s.period + s.phase
            if t0 < 0:
                continue
            dist = (tk - t0) * 2 * s.BV
            if 0 <= dist < s.range:
                out.append((s.cx + s.dir * (36 + dist), s.cy))
        return out

    def flash(s, tk):
        return 0 <= (tk - s.phase) % s.period < 5


class FallPlat:
    def __init__(s, x, top):
        s.x0, s.top = x * T, top * T
        s.x = s.x0 + 60
        s.state, s.t, s.y, s.vy = 0, 0, s.top, 0.0

    def shape(s, ts=0):
        if s.state >= 2:
            return None
        return (0, s.x0, s.y, s.x0 + 120, s.y + 26, 1, 0, 0)


class Seesaw:
    LEN = 360
    MAXA = math.radians(15)

    def __init__(s, cx, top):
        s.cx, s.top, s.ang, s.x = cx * T, top * T + 11, 0.0, cx * T

    def shape(s, ts=0):
        h = s.LEN / 2
        dy = math.sin(s.ang) * h
        dx = math.cos(s.ang) * h
        return (1, s.cx - dx, s.top + dy, s.cx + dx, s.top - dy, 1, 0, 0)


class Minion:
    SP = {"roam": 0.9, "soldier": 1.1, "ninja": 1.0}

    def __init__(s, kind, x, y, xa, xb, off):
        s.kind, s.x0, s.y0, s.xa, s.xb = kind, x, y, xa, xb
        s.L = max(1.0, xb - xa)
        s.sp = s.SP[kind]
        s.off = off
        s.alive, s.dead_t, s.armor, s.stun = True, 0, kind == "soldier", 0
        s.x = x
        s.sp0 = None

    def pos(s, ts):
        d = (s.sp * ts + s.off) % (2 * s.L)
        fwd = d < s.L
        if not fwd:
            d = 2 * s.L - d
        x = s.xa + d
        y = s.y0
        if s.sp0 is not None:
            y -= max(0.0, 520 - 0.2 * (ts - s.sp0) ** 2)
        if s.kind == "ninja":
            p = (ts * 0.5) % 90
            if p < 40:
                u = p / 40
                y -= 4 * 80 * u * (1 - u)
        return x, y, fwd

    def box(s, ts):
        x, y, f = s.pos(ts)
        return x - 26, y - 26, x + 26, y + 26


class Level:
    def __init__(s, spec, rnd):
        s.spec = spec
        art = load_art()
        ck = art["chunks"]
        if spec.get("boss"):
            parts = [ck["boss"][spec["boss"]]]
        else:
            pool = ck[spec["pool"]]
            picks = spec.get("picks") or rnd.sample(list(pool["pool"]), 5)
            stars = set(rnd.sample(range(len(picks)), min(3, len(picks))))
            parts = [pool["start"]] + [pool["pool"][n]["1" if i in stars else "0"] for i, n in enumerate(picks)] + [pool["exit"]]
        s.world = spec["world"]
        s.liquid = spec["liquid"]
        rows = ["".join(p["g"][y] for p in parts) for y in range(NROWS)]
        s.grid = rows
        s.nt = len(rows[0])
        s.width = s.nt * T
        offs, o = [], 0
        for p in parts:
            offs.append(o)
            o += p["w"]
        s.sol = [[SOLID.get(ch, 0) for ch in row] for row in rows]
        s.build_shapes()
        s.parse(parts, offs, rnd)
        s.build_runs()
        s.build_marks()
        s.checks = []
        s.cp_active = -1
        for i in (2, 4):
            if i < len(offs) - 1:
                s.checks.append(((offs[i] + 1) * T + 30, GT * T - R - 1))
        s.start = (s.start_xy[0], s.start_xy[1])

    # --- collision geometry
    def build_shapes(s):
        s.cells = {}
        s.hz = {}
        s.box_cache = {}
        s.hz_cache = {}
        rects = []
        sol, nt = s.sol, s.nt
        for m in (1, 2, 3, 4):
            runs = []
            for y in range(NROWS):
                x = 0
                while x < nt:
                    if sol[y][x] == m:
                        x0 = x
                        while x < nt and sol[y][x] == m:
                            x += 1
                        runs.append([x0, x, y, y + 1])
                    else:
                        x += 1
            merged = []
            for r in runs:
                for q in merged:
                    if q[0] == r[0] and q[1] == r[1] and q[3] == r[2]:
                        q[3] = r[3]
                        break
                else:
                    merged.append(r)
            for x0, x1, y0, y1 in merged:
                rects.append((0, x0 * T, y0 * T, x1 * T, y1 * T, m, 0, 0))
        for y in range(NROWS):
            for x in range(nt):
                ch = s.grid[y][x]
                if ch == "/":
                    rects.append((1, x * T, (y + 1) * T, (x + 1) * T, y * T, 1, 0, 0))
                elif ch == "\\":
                    rects.append((1, x * T, y * T, (x + 1) * T, (y + 1) * T, 1, 0, 0))
        for sh in rects:
            if sh[0] == 0:
                tx0, tx1, ty0, ty1 = int(sh[1] // T), int((sh[3] - 1) // T), int(sh[2] // T), int((sh[4] - 1) // T)
            else:
                tx0, tx1 = int(min(sh[1], sh[3]) // T), int((max(sh[1], sh[3]) - 1) // T)
                ty0, ty1 = int(min(sh[2], sh[4]) // T), int((max(sh[2], sh[4]) - 1) // T)
            for ty in range(ty0, ty1 + 1):
                for tx in range(tx0, tx1 + 1):
                    s.cells.setdefault((tx, ty), []).append(sh)

    def add_hz(s, x0, y0, x1, y1):
        for ty in range(int(y0 // T), int((y1 - 1) // T) + 1):
            for tx in range(int(x0 // T), int((x1 - 1) // T) + 1):
                s.hz.setdefault((tx, ty), []).append((x0, y0, x1, y1))

    def static_shapes(s, x, y, r):
        # the answer only depends on which tiles the ball's box touches, so it is memoised per tile box
        key = (int((x - r) // T), int((x + r) // T), int((y - r) // T), int((y + r) // T))
        c = s.box_cache.get(key)
        if c is None:
            c = []
            cells = s.cells
            for ty in range(key[2], key[3] + 1):
                for tx in range(key[0], key[1] + 1):
                    l = cells.get((tx, ty))
                    if l:
                        for sh in l:
                            if sh not in c:
                                c.append(sh)
            s.box_cache[key] = c
        return c

    def hz_hit(s, x, y, r):
        key = (int((x - r) // T), int((x + r) // T), int((y - r) // T), int((y + r) // T))
        c = s.hz_cache.get(key)
        if c is None:
            c = []
            hz = s.hz
            for ty in range(key[2], key[3] + 1):
                for tx in range(key[0], key[1] + 1):
                    l = hz.get((tx, ty))
                    if l:
                        c.extend(l)
            s.hz_cache[key] = c
        if not c:
            return False
        r2 = r * r
        for x0, y0, x1, y1 in c:
            dx = x - (x0 if x < x0 else (x1 if x > x1 else x))
            dy = y - (y0 if y < y0 else (y1 if y > y1 else y))
            if dx * dx + dy * dy < r2:
                return True
        return False

    # --- object parsing
    def parse(s, parts, offs, rnd):
        art = load_art()
        g = s.grid
        s.stars, s.minions, s.crates, s.boulders = [], [], [], []
        s.buttons, s.gates, s.levers, s.springs = [], [], [], []
        s.spikes = []
        s.exit = None
        s.start_xy = (180, GT * T - R - 1)
        gate_cells = {}
        liquid_rows = {}
        for y in range(NROWS):
            for x in range(s.nt):
                ch = g[y][x]
                if ch == ".":
                    continue
                cx, cy = x * T + 30, y * T + 30
                if ch == "*":
                    s.stars.append({"x": cx, "y": cy, "got": False, "id": len(s.stars)})
                elif ch == "S":
                    s.start_xy = (cx, (y + 1) * T - R - 1)
                elif ch == "E":
                    s.exit = (cx, GT * T)
                elif ch in "mMn":
                    s.add_minion({"m": "roam", "M": "soldier", "n": "ninja"}[ch], x, y)
                elif ch in "cC":
                    s.crates.append(Crate(cx, (y + 1) * T - 28, ch == "C"))
                elif ch == "B":
                    s.boulders.append(Boulder(cx, (y + 1) * T - 36))
                elif ch in "abcd":
                    gid = "abcd".index(ch) + 1
                    s.buttons.append({"gid": gid, "x0": x * T + 4, "x1": x * T + 56, "y1": (y + 1) * T, "y0": (y + 1) * T - 16, "on": False})
                elif ch in "1234":
                    gate_cells.setdefault((x, ch), []).append(y)
                elif ch in "pqrs":
                    s.levers.append({"gid": "pqrs".index(ch) + 1, "x": cx, "y": cy, "on": False})
                elif ch == "T":
                    s.springs.append({"x0": x * T + 4, "x1": x * T + 56, "y0": (y + 1) * T - 24, "y1": (y + 1) * T, "t": 0, "x": cx})
                elif ch == "^":
                    s.add_hz(x * T + 8, (y + 1) * T - 34, x * T + 52, (y + 1) * T)
                    s.spikes.append((x, y, "up"))
                elif ch == "v":
                    s.add_hz(x * T + 8, y * T, x * T + 52, y * T + 34)
                    s.spikes.append((x, y, "down"))
                elif ch == "W":
                    liquid_rows.setdefault(y, []).append(x)
        s.gates = []
        for (x, ch), ys in gate_cells.items():
            ys.sort()
            s.gates.append(Gate(int(ch), x * T + 30, ys[0] * T, (ys[-1] + 1) * T))
        s.liquid_runs = []
        for y, xs in liquid_rows.items():
            xs.sort()
            i = 0
            while i < len(xs):
                j = i
                while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
                    j += 1
                top = y == 0 or g[y - 1][xs[i]] != "W"
                s.liquid_runs.append((xs[i], xs[j] + 1, y, top))
                if top:
                    s.add_hz(xs[i] * T, y * T + 10, (xs[j] + 1) * T, NROWS * T)
                i = j + 1
        s.saws, s.plats, s.crushers, s.lasers, s.cannons, s.falls, s.seesaws = [], [], [], [], [], [], []
        s.boss = None
        for p, off in zip(parts, offs):
            for e in p["ex"]:
                k = e[0]
                if k == "saw":
                    s.saws.append(Saw(e[1] + off, e[2], e[3] + off, e[4], e[5]))
                elif k == "plat":
                    s.plats.append(Plat(e[1] + off, e[2], e[3] + off, e[4], e[5]))
                elif k == "crush":
                    s.crushers.append(Crusher(e[1] + off, e[2], e[3], e[4], e[5]))
                elif k == "laser":
                    s.lasers.append(Laser(e[1] + off, e[2], e[3], e[4], e[5], e[6], s))
                elif k == "cannon":
                    s.cannons.append(Cannon(e[1] + off, e[2], e[3], e[4], e[5], s))
                elif k == "fall":
                    s.falls.append(FallPlat(e[1] + off, e[2]))
                elif k == "seesaw":
                    s.seesaws.append(Seesaw(e[1] + off, e[2]))
        # decor on free ground tops
        s.decor = []
        dec = art["decor"][s.world]
        for x in range(2, s.nt - 2):
            if rnd.random() < 0.3:
                for y in range(NROWS):
                    if s.sol[y][x] == 1:
                        if y == 0 or (s.sol[y - 1][x] == 0 and g[y - 1][x] in ".*"):
                            sp = rnd.choice(dec)
                            s.decor.append((x * T + rnd.randint(4, 30), y * T - sp[1] + 2, sp))
                        break
        s.ramps = [(x, y, g[y][x]) for y in range(NROWS) for x in range(s.nt) if g[y][x] in "/\\"]
        s.gear_decor = []
        if s.world == "factory":
            for x in range(6, s.nt, 14):
                s.gear_decor.append((x * T, rnd.randint(2, 6) * T, rnd.choice("sl"), rnd.choice((-1, 1))))

    def add_minion(s, kind, x, y):
        # patrol limits: walk until a wall or a ledge, at most eight tiles each way
        sol = s.sol
        row = y + 1
        xa = xb = x
        while xa > 0 and x - xa < 8 and sol[row][xa - 1] and not sol[y][xa - 1]:
            xa -= 1
        while xb < s.nt - 1 and xb - x < 8 and sol[row][xb + 1] and not sol[y][xb + 1]:
            xb += 1
        px0, px1 = xa * T + 30 + 4, xb * T + 30 - 4
        if px1 - px0 < 20:
            px0, px1 = x * T + 30 - 10, x * T + 30 + 10
        m = Minion(kind, x * T + 30, (y + 1) * T - 26, px0, px1, random.random() * (px1 - px0) * 2)
        s.minions.append(m)

    # --- terrain render runs
    def build_runs(s):
        art = load_art()
        tiles = art["tiles"]
        s.runs = [[] for _ in range(NROWS)]
        s.aruns = [[] for _ in range(NROWS)]
        sol, nt = s.sol, s.nt
        liquid = art["liquid"]
        for y in range(NROWS):
            x = 0
            while x < nt:
                m = sol[y][x]
                if m == 0:
                    x += 1
                    continue
                kind = 2 if m == 2 else (3 if m in (3, 4) else 1)
                x0 = x
                while x < nt and ((sol[y][x] == 2) == (m == 2)) and ((sol[y][x] in (3, 4)) == (m in (3, 4))) and sol[y][x] == m:
                    x += 1
                if m in (3, 4):
                    s.aruns[y].append(["conv", x0, x, "convR" if m == 3 else "convL", {}])
                    continue
                wset = tiles["ice" if m == 2 else s.world]
                lines = [[] for _ in range(T)]
                for tx in range(x0, x):
                    mask = (1 if y == 0 or sol[y - 1][tx] == 0 else 0) | (2 if y == NROWS - 1 or sol[y + 1][tx] == 0 else 0) | \
                           (4 if tx == 0 or sol[y][tx - 1] == 0 else 0) | (8 if tx == nt - 1 or sol[y][tx + 1] == 0 else 0)
                    if mask & 2 and y == NROWS - 1:
                        mask &= ~2
                    tl = wset["%d_%d" % (mask, 0 if mask == 0 else (tx * 7 + y * 3) % 3)]
                    for j in range(T):
                        lines[j].append(tl[j])
                s.runs[y].append((x0 * T, x * T, [b"".join(l) for l in lines]))
        for (x0, x1, y, top) in s.liquid_runs:
            s.aruns[y].append(["liq", x0, x1, (s.liquid, "top" if top else "deep"), {}])
        # stretches of fully interior tiles: the renderer blits whole 60-line blocks for these in one write
        s.inter = [[] for _ in range(NROWS)]
        for y in range(NROWS):
            x = 0
            while x < nt:
                if sol[y][x] in (1, 2) and s.interior(x, y):
                    x0, k = x, sol[y][x]
                    while x < nt and sol[y][x] == k and s.interior(x, y):
                        x += 1
                    s.inter[y].append((x0 * T, x * T, "ice" if k == 2 else s.world))
                else:
                    x += 1

    def interior(s, x, y):
        sol, nt = s.sol, s.nt
        return 0 < y and x > 0 and x < nt - 1 and sol[y - 1][x] and (y == NROWS - 1 or sol[y + 1][x]) and sol[y][x - 1] and sol[y][x + 1]

    def build_marks(s):
        # tile columns where something worth planning around happens; the bot only looks ahead when one is near
        n = s.nt
        m = [0] * (n + 2)
        s.sol_top = []
        for tx in range(n):
            s.sol_top.append(next((y for y in range(NROWS) if s.sol[y][tx]), NROWS))
        for tx in range(1, n):
            if s.sol_top[tx] != s.sol_top[tx - 1]:
                m[tx] = m[tx - 1] = 1
        for (x, y, k) in s.spikes:
            m[x] = 1
        for (x0, x1, y, top) in s.liquid_runs:
            for tx in range(x0 - 1, x1 + 1):
                m[tx] = 1
        for o in s.saws + s.crushers + s.lasers + s.cannons + s.plats + s.falls + s.seesaws:
            m[max(0, min(n - 1, int(o.x // T)))] = 1
            if isinstance(o, (Saw, Plat)):
                m[max(0, min(n - 1, int(min(o.x1, o.x2) // T)))] = 1
                m[max(0, min(n - 1, int(max(o.x1, o.x2) // T)))] = 1
        for o in s.minions:
            m[int(o.x0 // T)] = 1
        for sp in s.springs:
            m[int(sp["x"] // T)] = 1
        for o in s.gates + s.crates + s.boulders:
            m[int(o.x // T)] = 1
        s.mark = m
        s.starcols = [0] * (n + 2)
        for st in s.stars:
            s.starcols[int(st["x"] // T)] = 1


class Crate:
    def __init__(s, x, y, metal):
        s.x, s.y, s.vx, s.vy, s.metal = x, y, 0.0, 0.0, metal
        s.x0, s.y0 = x, y

    def shape(s, ts=0):
        return (0, s.x - 28, s.y - 28, s.x + 28, s.y + 28, 1, s.vx, 0)


class Boulder:
    def __init__(s, x, y):
        s.x, s.y, s.vx, s.vy, s.rot = x, y, 0.0, 0.0, 0.0
        s.x0, s.y0 = x, y
        s.r = 36


class Gate:
    def __init__(s, gid, x, y0, y1):
        s.gid, s.x, s.y0, s.y1, s.open = gid, x, y0, y1, 0.0
        s.tiles = int(round((y1 - y0) / T))

    def shape(s, ts=0):
        if s.open >= 0.97:
            return None
        return (0, s.x - 18, s.y0 + s.open * (s.y1 - s.y0), s.x + 18, s.y1, 1, 0, 0)


# ------------------------------------------------------------------------------------------------------ physics
class Ball:
    __slots__ = ("x", "y", "vx", "vy", "gr", "gm", "coy", "jmp", "rvx", "rvy", "impact", "face", "rot", "hp", "inv",
                 "dizzy", "dead", "gnx", "stars", "stomps", "dmg", "bosshit", "got", "killed", "squash_t")

    def __init__(s):
        s.x = s.y = s.vx = s.vy = 0.0
        s.gr, s.gm, s.coy, s.jmp, s.rvx, s.rvy, s.impact, s.gnx = False, 0, 0, False, 0.0, 0.0, 0.0, 0.0
        s.face, s.rot, s.hp, s.inv, s.dizzy, s.dead = 1, 0.0, 3, 0, 0, 0
        s.stars = s.stomps = s.dmg = s.bosshit = 0
        s.got, s.killed = set(), set()
        s.squash_t = 0

    def copy(s):
        c = Ball()
        c.x, c.y, c.vx, c.vy, c.gr, c.gm, c.coy, c.jmp, c.rvx, c.rvy, c.gnx = s.x, s.y, s.vx, s.vy, s.gr, s.gm, s.coy, s.jmp, s.rvx, s.rvy, s.gnx
        c.hp, c.inv, c.face = s.hp, s.inv, s.face
        return c


sqrt = math.sqrt


def resolve(b, shapes, r):
    # Push a circle out of rects and ramp segments. Returns (grounded, material, carry vx, carry vy, impact speed).
    gr, gm, rvx, rvy, imp, gnx = False, 0, 0.0, 0.0, 0.0, 0.0
    r2 = r * r
    for _ in range(3):
        hit = False
        for sh in shapes:
            if sh[0] == 0:
                x0, y0, x1, y1 = sh[1], sh[2], sh[3], sh[4]
                bx, by = b.x, b.y
                cx = x0 if bx < x0 else (x1 if bx > x1 else bx)
                cy = y0 if by < y0 else (y1 if by > y1 else by)
                dx, dy = bx - cx, by - cy
                d2 = dx * dx + dy * dy
                if d2 >= r2:
                    continue
                if d2 > 1e-9:
                    dist = sqrt(d2)
                    nx, ny, pen = dx / dist, dy / dist, r - dist
                else:
                    l, rr, t, bt = bx - x0, x1 - bx, by - y0, y1 - by
                    m = min(l, rr, t, bt)
                    if m == t:
                        nx, ny, pen = 0.0, -1.0, t + r
                    elif m == l:
                        nx, ny, pen = -1.0, 0.0, l + r
                    elif m == rr:
                        nx, ny, pen = 1.0, 0.0, rr + r
                    else:
                        nx, ny, pen = 0.0, 1.0, bt + r
            else:
                ax, ay, qx, qy = sh[1], sh[2], sh[3], sh[4]
                ex, ey = qx - ax, qy - ay
                L2 = ex * ex + ey * ey
                L = sqrt(L2)
                t = ((b.x - ax) * ex + (b.y - ay) * ey) / L2
                if 0 <= t <= 1:
                    nx, ny = ey / L, -ex / L
                    sd = (b.x - ax) * nx + (b.y - ay) * ny
                    if sd >= r or sd < -r * 0.8:
                        continue
                    pen = r - sd
                else:
                    tc = 0 if t < 0 else 1
                    dx, dy = b.x - (ax + ex * tc), b.y - (ay + ey * tc)
                    d2 = dx * dx + dy * dy
                    if d2 >= r2 or d2 < 1e-9:
                        continue
                    dist = sqrt(d2)
                    nx, ny, pen = dx / dist, dy / dist, r - dist
            b.x += nx * pen
            b.y += ny * pen
            hit = True
            vn = b.vx * nx + b.vy * ny
            if vn < 0:
                b.vx -= vn * nx
                b.vy -= vn * ny
                if ny < -0.5 and -vn > imp:
                    imp = -vn
            if ny < -0.5:
                gr, gm, rvx, rvy, gnx = True, sh[5], sh[6], sh[7], nx
        if not hit:
            break
    return gr, gm, rvx, rvy, imp, gnx


def ball_sub(b, d, jp, jh, shapes):
    if b.rvx or b.rvy:
        b.x += b.rvx
        b.y += b.rvy
    gr, vx, vy = b.gr, b.vx, b.vy
    if gr:
        ice = b.gm == 2
        if d:
            acc = ACC_ICE if ice else ACC_G
            if vx * d < 0:
                acc *= 1.2 if ice else 2.4
            elif b.gnx * d < -0.3 and not ice:
                acc *= 2.0           # driving up a ramp: the ball rolls on its drive, not only on its horizontal push
            vx += d * acc
            if vx * d > VMAX:
                vx = d * VMAX
        else:
            vx *= 1 - (FR_ICE if ice else FR_G)
            if -0.03 < vx < 0.03:
                vx = 0.0
        b.coy = COYOTE
    else:
        if d:
            vx += d * ACC_A
            if vx * d > VMAX:
                vx = d * VMAX
        if b.coy:
            b.coy -= 1
    if jp and (gr or b.coy):
        vy = -JUMP_V
        b.coy = 0
        b.jmp = True
    elif b.jmp and not jh and vy < -3.0:
        vy *= 0.5
        b.jmp = False
    if vy > 0:
        b.jmp = False
    vy += GRAV
    if vy > FALL_MAX:
        vy = FALL_MAX
    b.vx, b.vy = vx, vy
    b.x += vx
    b.y += vy
    g, gm, rvx, rvy, imp, gnx = resolve(b, shapes, R)
    b.gnx = gnx
    if g:
        if imp > 10.5 and b.vy >= 0:
            b.vy = -imp * 0.28
        if gm == 3:
            rvx = 0.9
        elif gm == 4:
            rvx = -0.9
        b.impact = imp
    b.gr, b.gm, b.rvx, b.rvy = g, gm, rvx, rvy
    if d:
        b.face = d


class Near:
    __slots__ = ("saws", "crush", "lasers", "cannons", "minions", "stars", "springs", "plats", "falls", "gates", "crates",
                 "boulders", "seesaws", "boss", "cache")


def near_of(W, x, rng, boss=None):
    n = Near()
    lo, hi = x - rng, x + rng
    n.saws = [o for o in W.saws if min(o.x1, o.x2) - 60 <= hi and max(o.x1, o.x2) + 60 >= lo]
    n.crush = [o for o in W.crushers if lo - 80 <= o.x <= hi + 80]
    n.lasers = [o for o in W.lasers if lo - 80 <= o.x <= hi + 80]
    n.cannons = [o for o in W.cannons if lo - 700 <= o.x <= hi + 700]
    n.minions = [o for o in W.minions if o.alive and o.xa - 60 <= hi and o.xb + 60 >= lo]
    n.stars = [o for o in W.stars if not o["got"] and lo - 60 <= o["x"] <= hi + 60]
    n.springs = [o for o in W.springs if lo - 80 <= o["x"] <= hi + 80]
    n.plats = [o for o in W.plats if min(o.x1, o.x2) - 90 <= hi and max(o.x1, o.x2) + 90 >= lo]
    n.falls = [o for o in W.falls if lo - 140 <= o.x <= hi + 140]
    n.gates = [o for o in W.gates if lo - 80 <= o.x <= hi + 80]
    n.crates = [o for o in W.crates if lo - 90 <= o.x <= hi + 90]
    n.boulders = [o for o in W.boulders if lo - 90 <= o.x <= hi + 90]
    n.seesaws = [o for o in W.seesaws if lo - 260 <= o.x <= hi + 260]
    n.boss = boss
    n.cache = {}
    return n


def dyn_shapes(n, ts, ignore_crates=False, boulders=True):
    out = [p.shape(ts) for p in n.plats]
    for f in n.falls:
        sh = f.shape()
        if sh:
            out.append(sh)
    for g in n.gates:
        sh = g.shape()
        if sh:
            out.append(sh)
    if not ignore_crates:
        for c in n.crates:
            out.append(c.shape())
        if boulders:
            for c in n.boulders:
                out.append((0, c.x - 36, c.y - 36, c.x + 36, c.y + 36, 1, 0, 0))
    for sw in n.seesaws:
        out.append(sw.shape())
    return out


def circle_rect(x, y, r, x0, y0, x1, y1):
    dx = x - (x0 if x < x0 else (x1 if x > x1 else x))
    dy = y - (y0 if y < y0 else (y1 if y > y1 else y))
    return dx * dx + dy * dy < r * r


def hurt(b, dirx):
    # one point of damage, knocked back and dizzy; being hit again while blinking does nothing
    if b.inv > 0:
        return
    b.hp -= 1
    b.dmg += 1
    b.inv = 140
    b.dizzy = 60
    b.vx = 4.5 * dirx
    b.vy = -5.5
    b.gr = False
    if b.hp <= 0:
        b.dead = 1


def movers_at(n, ts):
    # positions of everything that moves on a schedule, computed once per sub-step and shared by all look-ahead runs
    tk = ts * 0.5
    saws = [sw.pos(ts) for sw in n.saws]
    crush = []
    for c in n.crush:
        hy = c.head_y(tk)
        crush.append((c.x - 58, hy, c.x + 58, hy + 64))
    lasers = [l.rect for l in n.lasers if l.active(tk)]
    bullets = []
    for cn in n.cannons:
        for (bx, by) in cn.bullets(tk):
            bullets.append((bx, by, cn.dir))
    mins = []
    for m in n.minions:
        x0, y0, x1, y1 = m.box(ts)
        mins.append((m, x0, y0, x1, y1))
    c = (saws, crush, lasers, bullets, mins)
    n.cache[ts] = c
    return c


def interact(b, W, n, ts, live, G):
    # Everything the ball touches that is not terrain. live=True mutates the world; the bot's copy only records events.
    x, y = b.x, b.y
    if y > BOTTOM:
        b.dead = 1
        return
    if b.inv:
        b.inv -= 1
    if W.hz_hit(x, y, R - 6):
        b.dead = 1
        return
    c = n.cache.get(ts) or movers_at(n, ts)
    saws, crush, lasers, bullets, mins = c
    for sx, sy in saws:
        if (x - sx) ** 2 + (y - sy) ** 2 < (R + 31) ** 2:
            b.dead = 1
            return
    for x0, y0, x1, y1 in crush:
        if circle_rect(x, y, R - 4, x0, y0, x1, y1):
            b.dead = 1
            return
    for x0, y0, x1, y1 in lasers:
        if circle_rect(x, y, R - 5, x0, y0, x1, y1):
            b.dead = 1
            return
    for bx, by, bd in bullets:
        if (x - bx) ** 2 + (y - by) ** 2 < (R + 11) ** 2:
            hurt(b, -bd)
    for st in n.stars:
        if (x - st["x"]) ** 2 + (y - st["y"]) ** 2 < 46 ** 2:
            if live:
                if not st["got"]:
                    b.stars += 1
                    G.collect_star(st)
            elif st["id"] not in b.got:
                b.got.add(st["id"])
                b.stars += 1
    for sp in n.springs:
        if b.vy > -2 and circle_rect(x, y, R - 3, sp["x0"], sp["y0"], sp["x1"], sp["y1"]):
            b.vy = -SPRING_V
            b.gr = False
            b.jmp = False
            b.coy = 0
            if live:
                sp["t"] = 10
    for m, x0, y0, x1, y1 in mins:
        if live:
            if m.stun > ts:
                continue
        elif id(m) in b.killed:
            continue
        if circle_rect(x, y, R - 3, x0, y0, x1, y1):
            if b.vy > 0.8 and y < y0 + 16:
                b.stomps += 1
                b.vy = -9.5
                b.jmp = True
                if live:
                    G.stomp(m, ts)
                else:
                    b.killed.add(id(m))
            else:
                hurt(b, 1 if x >= (x0 + x1) / 2 else -1)
    bs = n.boss
    if bs is not None:
        bs.touch(b, ts, live, G)


def crate_step(c, W):
    solid = lambda px, py: 0 <= int(py // T) < NROWS and 0 <= int(px // T) < W.nt and W.sol[int(py // T)][int(px // T)] != 0
    c.vy = min(c.vy + GRAV, 12.0)
    y1 = c.y + c.vy
    bottom = y1 + 28
    left, right = c.x - 26, c.x + 26
    ground = False
    if c.vy > 0 and (solid(left, bottom) or solid(right, bottom)):
        c.y = int(bottom // T) * T - 28
        c.vy = 0.0
        ground = True
    else:
        c.y = y1
    if ground:
        sl, sr, sc = solid(left, c.y + 30), solid(right, c.y + 30), solid(c.x, c.y + 30)
        if not sc:
            # tips over the edge once its centre has passed it
            c.vx += 0.35 if (sl and not sr) else (-0.35 if (sr and not sl) else 0.0)
        c.vx *= 0.80
        if abs(c.vx) < 0.02:
            c.vx = 0.0
    if c.vx:
        nx = c.x + c.vx
        edge = nx + (28 if c.vx > 0 else -28)
        if solid(edge, c.y - 22) or solid(edge, c.y + 22):
            c.vx = 0.0
        else:
            c.x = nx


def boulder_step(c, W, ice_k):
    shapes = W.static_shapes(c.x, c.y, c.r + 2)
    c.vy = min(c.vy + GRAV, 12.0)
    c.x += c.vx
    c.y += c.vy
    g, gm, rvx, rvy, imp, gnx = resolve(c, shapes, c.r)
    if g:
        c.vx *= 0.998 if gm == 2 else 0.985
        if gm == 3:
            c.vx += 0.02
        if gm == 4:
            c.vx -= 0.02
    c.rot += c.vx / c.r


# ------------------------------------------------------------------------------------------------------ bosses
BX0, BX1 = 174, 1746        # boss centre range inside the arena walls
BOX = 98                    # boss hit box edge; the sprite is a little larger
GROUND = GT * T


class Press(Crusher):
    # one slam of the Mecha boss: a pure function of time like every other hazard, so the bot can read it
    def __init__(s, cx, t0):
        s.x, s.t0 = cx, t0
        s.y0, s.drop, s.period, s.phase, s.up = -80, GROUND - 14 - 64 + 80, 1, 0, 0

    def head_y(s, tk):
        d = tk - s.t0
        if d < 0:
            return s.y0 - (14 if d > -24 and int(tk) % 6 < 3 else 0) + (22 if d > -24 else 0)
        if d < 7:
            return s.y0 + s.drop * d / 7
        if d < 23:
            return s.y0 + s.drop
        if d < 53:
            return s.y0 + s.drop * (1 - (d - 23) / 30)
        return s.y0 - 200


class Boss:
    def __init__(s, kind, G):
        s.kind, s.G = kind, G
        s.x, s.y = 1500.0, GROUND - BOX / 2
        s.vx = s.vy = 0.0
        s.hp = 5 if kind == "monocle" else 6
        s.state, s.t = "intro", 0
        s.face = -1
        s.ref_ts = 0
        s.air = False
        s.done = False
        s.wave = 0
        s.jumps = 0
        s.cycle = 0
        s.presses = []
        s.stones = []
        s.sw = 1
        s.flash = 0
        s.rest_x = 1500

    # --- queries used by the physics and the bot
    @property
    def vulnerable(s):
        return s.state == "tired" and s.kind != "boulder"

    @property
    def hurts(s):
        return s.state not in ("intro", "hurt", "dying", "leave", "press", "away", "summon", "wait") or (s.kind == "boulder" and s.state != "dying")

    def box(s, ts):
        dt = ts - s.ref_ts
        x = s.x + s.vx * dt if s.state in ("leave", "away", "return") else min(BX1, max(BX0, s.x + s.vx * dt))
        y = s.y
        if s.air:
            y = min(GROUND - BOX / 2, s.y + s.vy * dt + 0.2 * dt * (dt + 1))
        h = BOX / 2
        return x - h, y - h, x + h, y + h

    def touch(s, b, ts, live, G):
        if s.state in ("away", "dying"):
            return
        x0, y0, x1, y1 = s.box(ts)
        if not circle_rect(b.x, b.y, R - 3, x0, y0, x1, y1):
            return
        if b.vy > 0.8 and b.y < y0 + 22:
            b.vy = -11.0
            b.jmp = True
            if s.vulnerable:
                b.bosshit += 1
                if live:
                    G.boss_hit()
            return
        if s.hurts:
            hurt(b, 1 if b.x >= (x0 + x1) / 2 else -1)

    # --- per-tick behaviour
    def set_state(s, st, t=0):
        s.state, s.t = st, t

    def update(s, G):
        s.t += 1
        s.ref_ts = G.ts
        b = G.ball
        if s.flash:
            s.flash -= 1
        k = s.kind
        st = s.state
        if st == "dying":
            s.vx = 0
            if s.t % 6 == 0:
                G.burst(s.x + random.randint(-50, 50), s.y + random.randint(-50, 50), big=True)
            if s.t > 90:
                s.done = True
            return
        if k == "monocle":
            s.upd_monocle(G, b)
        elif k == "mecha":
            s.upd_mecha(G, b)
        else:
            s.upd_boulder(G, b)
        if s.state in ("leave", "away", "return"):
            s.x += s.vx * SUB
        else:
            s.x = min(BX1, max(BX0, s.x + s.vx * SUB))
        if s.air:
            for _ in range(SUB):
                s.vy += 0.4
                s.y += s.vy
            if s.y >= GROUND - BOX / 2:
                s.y = GROUND - BOX / 2
                s.vy = 0.0
                s.air = False
                G.shake = 6
                G.dust(s.x, GROUND)
                s.on_land(G, b)
        if s.vx:
            s.face = 1 if s.vx > 0 else -1

    def on_land(s, G, b):
        if s.kind == "monocle" and s.state == "jumping":
            s.jumps += 1
            if s.jumps >= 3:
                s.jumps = 0
                s.set_state("tired", 0)
                s.vx = 0
            else:
                s.set_state("pause", 0)
                s.vx = 0

    def hurt_done(s, G):
        if s.state == "dying":
            return
        s.flash = 40
        s.vx = 0
        if s.hp <= 0:
            s.set_state("dying", 0)
            G.on_boss_dead()
        else:
            s.set_state("hurt", 0)

    def damage(s, n):
        s.hp -= n
        s.hurt_done(s.G)

    def upd_monocle(s, G, b):
        st = s.state
        if st == "intro":
            if s.t > 70:
                s.set_state("idle")
        elif st == "idle":
            s.vx = 0
            if s.t > 14:
                if s.hp > 3 or s.wave >= 3:
                    if s.hp > 3:
                        s.vx = 8.0 * (1 if b.x > s.x else -1)
                        s.set_state("charge")
                    else:
                        s.jumps = 0
                        s.set_state("pause")
                else:
                    s.set_state("summon_move")
        elif st == "charge":
            if s.x <= BX0 + 1 or s.x >= BX1 - 1:
                s.vx = 0
                s.set_state("tired")
        elif st == "tired":
            s.vx = 0
            if s.t > 135:
                s.set_state("idle")
        elif st == "hurt":
            s.vx = 0
            if s.t > 40:
                s.set_state("idle")
        elif st == "summon_move":
            s.vx = 5.0 * (1 if 1640 > s.x else -1)
            if abs(s.x - 1640) < 12:
                s.vx = 0
                s.set_state("summon", 0)
        elif st == "summon":
            if s.t == 12 or (s.t > 12 and s.t % 8 == 0 and not any(m.alive for m in G.W.minions if m.sp0 is not None)):
                if not any(m.alive for m in G.W.minions if m.sp0 is not None):
                    if s.wave >= 3:
                        s.set_state("idle")
                        return
                    kinds = (("roam", 1), ("roam", 2), ("ninja", 2))[s.wave]
                    G.spawn_wave(kinds[0], kinds[1])
                    s.wave += 1
                    s.t = 14
        elif st == "pause":
            s.vx = 0
            if s.t > 12:
                s.vy = -13.0
                s.vx = 3.4 * (1 if b.x > s.x else -1)
                s.air = True
                s.set_state("jumping")

    def upd_mecha(s, G, b):
        st = s.state
        if s.presses and G.ts * 0.5 > s.presses[-1].t0 + 70:
            # spent presses would only slow down every look-ahead
            G.W.crushers = [c for c in G.W.crushers if c not in s.presses]
            s.presses = []
        if st == "intro":
            if s.t > 70:
                s.set_state("leave")
                s.vx = 12.0
        elif st == "leave":
            if s.x > 2100:
                s.vx = 0
                s.set_state("away")
                s.launch_presses(G)
        elif st == "away":
            if s.t > 150 + 10 * s.cycle:
                s.x = 2050
                s.vx = -9.0
                s.set_state("return")
        elif st == "return":
            if s.x <= s.rest_x:
                s.vx = 0
                s.set_state("tired")
        elif st == "tired":
            if s.t > 130:
                s.vx = 12.0
                s.set_state("leave")
        elif st == "hurt":
            if s.t > 40:
                s.vx = 12.0
                s.set_state("leave")

    def launch_presses(s, G):
        tk = G.ts * 0.5
        n = 8
        cs = [230 + 210 * i for i in range(n)]
        pat = s.cycle % 3
        for i, cx in enumerate(cs):
            if pat == 0:
                t0 = 30 + 12 * i
            elif pat == 1:
                t0 = 30 + (0 if i % 2 == 0 else 60)
            else:
                t0 = 30 + 12 * (n - 1 - i) + (i % 3) * 8
            p = Press(cx, tk + t0)
            s.presses.append(p)
            G.W.crushers.append(p)
        if s.cycle >= 1:
            G.spawn_wave("roam", s.cycle)
        s.cycle += 1

    def upd_boulder(s, G, b):
        st = s.state
        if st == "intro":
            if s.t > 60:
                s.vx = 3.0 * random.choice((-1, 1))
                s.set_state("roll")
        elif st == "roll":
            if s.x <= BX0 + 1:
                s.vx = 3.0
            elif s.x >= BX1 - 1:
                s.vx = -3.0
        elif st == "hurt":
            if s.t > 36:
                s.set_state("roll")
        for sto in s.stones:
            sto[2] += 0.45 * SUB
            sto[1] += sto[2] * SUB
            if sto[1] + 50 >= GROUND:
                sto[3] = True
                if abs(sto[0] - s.x) < 54 + 46 and s.state != "dying":
                    s.hp -= 2
                    G.burst(sto[0], GROUND - 40, big=True)
                    G.shake = 12
                    s.flash = 40
                    s.set_state("hurt" if s.hp > 0 else "dying")
                    if s.hp <= 0:
                        G.on_boss_dead()
                else:
                    G.burst(sto[0], GROUND - 30)
        s.stones = [t for t in s.stones if not t[3]]

    def roll_at(s, tk):
        # where the rolling boss will be at absolute tick tk (it bounces between the arena walls)
        dist = (tk - s.ref_ts * 0.5) * SUB * (abs(s.vx) or 3.0)
        x, v = s.x, 1 if s.vx >= 0 else -1
        while dist > 0:
            room = (BX1 - x) if v > 0 else (x - BX0)
            step = min(room, dist)
            x += v * step
            dist -= step
            if dist > 0:
                v = -v
        return x

    def press_switch(s, gid):
        if s.state != "roll" or gid != s.sw:
            return False
        s.stones.append([930.0, -60.0, 0.0, False])
        s.sw = 3 - s.sw
        return True

    def sprite(s):
        k, st = s.kind, s.state
        f = "angry"
        if st in ("tired",):
            f = "tired"
        elif s.flash and (s.flash // 3) % 2 == 0:
            f = "hurt"
        elif st in ("intro", "hurt", "away", "leave", "return"):
            f = "calm"
        return A["boss"]["%s%s%s" % (k, f, "R" if s.face > 0 else "L")]


# ------------------------------------------------------------------------------------------------------ bot
class Res:
    __slots__ = ("dead", "dmg", "stars", "stomps", "bosshit", "x", "y", "gr", "ticks")


def simulate(G, m, horizon, n, ignore_crates=False, start=None, ts0=None):
    # Play a macro forward on a copy of the ball with the real physics. Movers are pure functions of time, so their
    # future positions are exact; crates and boulders are frozen where they stand.
    W = G.W
    b = (start or G.ball).copy()
    wait, drun, delay, hold, dair, jump = m
    tj = wait + delay
    if ts0 is None:
        ts0 = G.ts
    end_at = None
    k = 0
    # most look-ahead happens where nothing moves: skip the per-sub-step object work then
    dyn_empty = not (n.plats or n.falls or n.gates or n.crates or n.boulders or n.seesaws)
    light = not (n.saws or n.crush or n.lasers or n.cannons or n.springs or n.minions or n.stars or n.boss)
    for k in range(horizon):
        jp = jh = False
        if k < wait:
            d = 0
        elif jump and k >= tj:
            d = dair
            jp = k == tj
            jh = k - tj < hold
        else:
            d = drun
            jh = k < hold
        for sub in (0, 1):
            ts = ts0 + k * 2 + sub
            shapes = W.static_shapes(b.x, b.y, R + 4)
            if not dyn_empty:
                shapes = shapes + dyn_shapes(n, ts, ignore_crates)
            ball_sub(b, d, jp and sub == 0, jh, shapes)
            if light:
                if b.inv:
                    b.inv -= 1
                if b.y > BOTTOM or W.hz_hit(b.x, b.y, R - 6):
                    b.dead = 1
            else:
                interact(b, W, n, ts, False, None)
        if b.dead:
            break
        if jump and k > tj + 3 and b.gr and end_at is None:
            end_at = k + 7
        if end_at is not None and k >= end_at:
            break
    r = Res()
    r.dead, r.dmg, r.stars, r.stomps, r.bosshit = b.dead, b.dmg, b.stars, b.stomps, b.bosshit
    r.x, r.y, r.gr, r.ticks = b.x, b.y, b.gr, k + 1
    return r


def advance(G, n, ign, dg, ticks):
    # the ball's state after running plainly for a few ticks: the point where a time-sliced plan will take over
    W = G.W
    b = G.ball.copy()
    for k in range(ticks):
        for sub in (0, 1):
            ts = G.ts + k * 2 + sub
            shapes = W.static_shapes(b.x, b.y, R + 4) + dyn_shapes(n, ts, ign)
            ball_sub(b, dg, False, False, shapes)
            interact(b, W, n, ts, False, None)
    return b


PLAN_LAG = 5        # ticks a time-sliced plan takes: the ball keeps running while the simulations are spread out
SLICE_SIMS = 6      # simulations per tick while a plan is being worked out


class Bot:
    def __init__(s, G):
        s.G = G
        s.m = None
        s.k = 0
        s.cool = 0
        s.air_d = 1
        s.best = -1e9
        s.stall = 0
        s.rec_n = 0
        s.armed = False
        s.arm_sw = 1
        s.idle_t = 0
        s.push = False
        s.sess = None

    def reset_level(s):
        s.sess = None
        s.m = None
        s.best = -1e9
        s.stall = 0
        s.rec_n = 0
        s.armed = False
        s.idle_t = 0

    # --- scoring of a simulated macro
    def score(s, r, m, x0, dg, tx):
        sc = 0.0
        if r.dead:
            sc -= 9000
        sc -= 1200 * r.dmg
        sc += 520 * r.stars + 800 * r.stomps + 3000 * r.bosshit
        if tx is None:
            sc += (r.x - x0) * dg
        else:
            sc += abs(x0 - tx) - abs(r.x - tx)
        sc -= 0.5 * m[0]
        if not r.gr and not r.dead:
            sc -= 60
        return sc

    def macros(s, dg, urgent=False):
        # coarse set; the planner refines the delay of the winner afterwards
        L = []
        if urgent:
            # the take-off is near: only short delays matter, so look at fewer options
            for delay in (0, 4, 8, 12):
                L.append((0, dg, delay, 70, dg, True))
            L.append((0, dg, 0, 7, dg, True))
            L.append((0, dg, 6, 7, dg, True))
            L.append((0, dg, 0, 70, -dg, True))
            for wait in (10, 24, 48):
                L.append((wait, dg, 0, 0, dg, False))
            return L
        for delay in (0, 6, 12, 18):
            L.append((0, dg, delay, 70, dg, True))
        L.append((0, dg, 0, 7, dg, True))
        L.append((0, dg, 9, 7, dg, True))
        L.append((0, dg, 0, 70, -dg, True))
        L.append((0, dg, 8, 70, 0, True))
        for wait in (14, 28, 48, 80):
            L.append((wait, dg, 0, 0, dg, False))
        L.append((22, dg, 3, 70, dg, True))
        L.append((50, dg, 3, 70, dg, True))
        return L

    def search(s, ball0, ts0, dg, tx, ign, n, r0, urgent=False):
        # Generator: tries the candidate macros from a given start state, yielding between simulations so that a plan
        # can be spread over several ticks. The outcome is left in s.found.
        G = s.G
        x0 = ball0.x
        base = (0, dg, 0, 0, dg, False)
        best, bsc = None, s.score(r0, base, x0, dg, tx)
        cands = s.macros(dg, urgent)
        # jump timings aimed at the nearest stars: the apex of a full jump is about 27 sub-steps of running away
        for st in sorted(n.stars, key=lambda q: abs(q["x"] - x0))[:2]:
            dx = (st["x"] - x0) * dg
            if -30 < dx < 660:
                d0 = int((dx - VMAX * 27) / (VMAX * 2))
                for dd in sorted({max(0, v) for v in range(d0 - 2, d0 + 3)}):
                    cands.append((0, dg, dd, 70, dg, True))
        for m in cands:
            r = simulate(G, m, 90 if m[2] > 25 else 70, n, ign, ball0, ts0)
            sc = s.score(r, m, x0, dg, tx)
            if sc > bsc + 1e-6:
                best, bsc = m, sc
            yield
        if best is not None and best[5] and best[0] == 0:
            b0 = best
            for dd in (-3, -1, 1, 3):
                m = (b0[0], b0[1], max(0, b0[2] + dd), b0[3], b0[4], True)
                if m == b0:
                    continue
                r = simulate(G, m, 90 if m[2] > 25 else 70, n, ign, ball0, ts0)
                sc = s.score(r, m, x0, dg, tx)
                if sc > bsc + 1e-6:
                    best, bsc = m, sc
                yield
        s.found = (best, bsc)

    def commit(s, found, r0, dg, keep):
        best, bsc = found
        if best is None:
            if keep:
                return
            s.cool = 2 if (r0.dead or r0.dmg) else 6
            if r0.dead:
                s.m = (30, dg, 0, 0, dg, False)
                s.k = 0
            return
        if best[5] and not keep and random.random() < ERR_RATE:
            # a human misjudges a jump now and then; the mid-air correction usually saves it, not always
            best = (best[0], best[1], max(0, best[2] + random.choice((-4, -3, 3, 4, 5))), best[3], best[4], True)
        s.m = best
        s.k = 0

    def plan(s, dg, tx, force, keep=False):
        G = s.G
        b = G.ball
        n = G.near_cache
        ign = s.push
        base = (0, dg, 0, 0, dg, False)
        r0 = simulate(G, base, 34, n, ign)
        stuck = tx is None and (r0.x - b.x) * dg < 22 and not r0.dead
        want = r0.dead or r0.dmg or stuck or force
        if not want:
            if not keep:
                s.cool = 3
            return
        imminent = (r0.dead or r0.dmg) and r0.ticks <= 32
        if keep or imminent or G.boss is not None:
            for _ in s.search(b, G.ts, dg, tx, ign, n, r0, imminent):
                pass
            s.commit(s.found, r0, dg, keep)
            return
        # nothing is about to go wrong: plan from where the ball will be in a few ticks, a few simulations per tick
        ahead = advance(G, n, ign, dg, PLAN_LAG)
        ts0 = G.ts + 2 * PLAN_LAG
        r0p = simulate(G, base, 34, n, ign, ahead, ts0)
        s.sess = {"gen": s.search(ahead, ts0, dg, tx, ign, n, r0p), "ball": ahead, "left": PLAN_LAG, "dg": dg, "r0": r0p, "done": False}

    def step_session(s):
        # returns True while a time-sliced plan is still being worked out
        sess = s.sess
        G = s.G
        b = G.ball
        sess["left"] -= 1
        if not sess["done"]:
            budget = SLICE_SIMS if sess["left"] > 0 else 10 ** 6
            for _ in range(budget):
                try:
                    next(sess["gen"])
                except StopIteration:
                    sess["done"] = True
                    break
        if sess["left"] > 0:
            return True
        s.sess = None
        a = sess["ball"]
        if abs(a.x - b.x) < 2.5 and abs(a.y - b.y) < 2.5 and a.gr == b.gr and sess["done"]:
            s.commit(s.found, sess["r0"], sess["dg"], False)
        else:
            s.cool = 0
        return False

    def run_macro(s):
        G = s.G
        b = G.ball
        wait, drun, delay, hold, dair, jump = s.m
        k = s.k
        tj = wait + delay
        jp = jh = False
        if k < wait:
            d = 0
        elif jump and k >= tj:
            d = dair
            jp = k == tj
            jh = k - tj < hold
        else:
            d = drun
        if jump and wait == 0 and 3 <= tj - k <= 16 and k % 3 == 2 and b.gr and G.boss is None:
            # close to the take-off point: re-time the jump with a handful of simulations
            rem = tj - k
            bestm, bsc = None, None
            for dd in (0, -2, 2, -4, 4):
                m = (0, drun, max(0, rem + dd), hold, dair, True)
                r = simulate(G, m, 75, G.near_cache, s.push)
                sc = s.score(r, m, b.x, 1, None)
                if bsc is None or sc > bsc + 1e-6:
                    bestm, bsc = m, sc
            if bestm[2] != rem:
                s.m = (0, drun, k + bestm[2], hold, dair, True)
                wait, drun, delay, hold, dair, jump = s.m
                tj = wait + delay
        if jump and k > tj + 5 and not b.gr and k % 4 == 0:
            # mid-air correction: if the plan now ends badly, try steering the other way
            hl = max(0, hold - k)
            r = simulate(G, (0, dair, 0, hl, dair, False), 40, G.near_cache, s.push)
            if r.dead or r.dmg:
                bestd, bsc = dair, -1e9
                for dd in (1, 0, -1):
                    r = simulate(G, (0, dd, 0, hl, dd, False), 40, G.near_cache, s.push)
                    sc = -9000 * r.dead - 1200 * r.dmg + 500 * r.stars
                    if sc > bsc:
                        bestd, bsc = dd, sc
                s.m = (wait, drun, delay, hold, bestd, jump)
        s.k += 1
        if jump:
            if k > tj + 4 and b.gr:
                s.m = None
        elif k >= wait + 6:
            s.m = None
        if s.k > 160:
            s.m = None
        return d, jp, jh

    def interest(s, dg):
        W = s.G.W
        tx = int(s.G.ball.x // T)
        lo, hi = (tx - 1, tx + 9) if dg > 0 else (tx - 9, tx + 1)
        mk = W.mark
        sc = W.starcols
        force = False
        hit = False
        for c in range(max(0, lo), min(W.nt, hi + 1)):
            if mk[c]:
                hit = True
            if sc[c]:
                force = True
        return hit, force

    def stall_check(s, prog):
        if prog > s.best + 30:
            s.best = prog
            s.stall = 0
            if prog > s.rec_prog + 240:
                s.rec_n = 0
        else:
            s.stall += 1

    rec_prog = 0

    def recover(s, dg):
        G = s.G
        s.stall = 0
        s.rec_n += 1
        s.rec_prog = s.best
        if s.rec_n <= 2:
            s.m = (0, -dg, random.choice((18, 30, 44)), 70, dg, True)
            s.k = 0
        else:
            G.warp_ahead()
            s.rec_n = 0
            s.best += 300

    def input(s):
        G = s.G
        b = G.ball
        if G.mode != "play" or G.respawn_t or b.dead:
            return 0, False, False
        if G.boss is not None:
            return s.boss_input()
        dg = 1
        if s.cool > 0:
            s.cool -= 1
        s.stall_check(b.x * dg)
        if s.stall > 150:
            s.recover(dg)
        s.push = G.push_mode(b.x)
        if s.sess is not None:
            if s.step_session():
                return dg, False, False
        if s.m is not None:
            return s.run_macro()
        if s.push and b.gr:
            # shoving a crate toward a button: plain running, jumping over the crate would defeat the puzzle
            return dg, False, False
        if b.gr or b.coy:
            hit, force = s.interest(dg)
            if (hit or force) and s.cool <= 0:
                s.plan(dg, None, force and G.star_ahead(b.x))
                if s.m is not None:
                    return s.run_macro()
            return dg, False, False
        # airborne without a plan (walked off a ledge): steer by look-ahead
        if s.cool <= 0:
            s.cool = 3
            bestd, bsc = dg, -1e9
            for dd in (dg, 0, -dg):
                r = simulate(G, (0, dd, 0, 0, dd, False), 40, G.near_cache, s.push)
                sc = -9000 * r.dead - 1200 * r.dmg + 500 * r.stars + (r.x - b.x) * dg * (1 if dd else 0.4)
                if sc > bsc:
                    bestd, bsc = dd, sc
            s.air_d = bestd
        return s.air_d, False, False

    # --- boss fights
    def boss_target(s):
        G = s.G
        b, bs = G.ball, G.boss
        k = bs.kind
        live = [m for m in G.W.minions if m.alive and m.sp0 is not None]
        if bs.state == "dying":
            return b.x, False
        if k == "boulder":
            return s.boulder_target()
        if bs.vulnerable:
            return bs.x, True
        if live:
            m = min(live, key=lambda q: abs(q.pos(G.ts)[0] - b.x))
            return m.pos(G.ts)[0], True
        if k == "mecha" and bs.state in ("away", "leave"):
            # head for the gap nearest to where the boss will come back tired, so the stomp is close
            return 1385, False
        if k == "monocle":
            # the charge runs toward the ball's side and ends at that wall, so waiting near it puts the ball
            # next to the boss when it gets tired
            return (480 if b.x < 960 else 1440), False
        return b.x, False

    def boulder_target(s):
        G = s.G
        b, bs = G.ball, G.boss
        on_cat = b.y < 560
        if not on_cat:
            return (390 if b.x < 960 else 1530), True
        btn = 750 if bs.sw == 1 else 1110
        stand = btn - 130 if bs.sw == 1 else btn + 130
        if s.armed:
            if bs.sw == s.arm_sw:
                return btn, True
            s.armed = False
        if (bs.sw == 1 and b.x > 900) or (bs.sw == 2 and b.x < 960):
            return stand, True
        if abs(b.x - stand) > 18 and not s.armed:
            return stand, True
        # at the stand-by spot: start rolling onto the switch when the falling stone will meet the boss
        dist = abs(btn - b.x)
        t_go = math.sqrt(2 * max(dist, 1) / ACC_G) / 2 + 2 + 31
        px = bs.roll_at(G.ts * 0.5 + t_go)
        s.idle_t += 1
        if abs(px - 930) < 36 or s.idle_t > 700:
            s.idle_t = 0
            s.armed, s.arm_sw = True, bs.sw
            return btn, True
        return b.x, False

    def boss_input(s):
        G = s.G
        b, bs = G.ball, G.boss
        if s.cool > 0:
            s.cool -= 1
        if bs.state in ("intro",):
            return 0, False, False
        tx, hunt = s.boss_target()
        dx = tx - b.x
        dg = 1 if dx > 0 else -1
        d_default = dg if abs(dx) > (14 if hunt else 40) else 0
        if s.m is not None:
            return s.run_macro()
        if bs.kind == "boulder" and not s.boulder_fight_needed(b):
            return d_default, False, False
        threat = True
        if b.gr and s.cool <= 0:
            near_boss = abs(bs.x - b.x) < 700 or any(m.alive for m in G.W.minions)
            if near_boss:
                s.plan_boss(d_default or dg, tx, hunt, d_default)
                if s.m is not None:
                    return s.run_macro()
            else:
                s.cool = 3
        if not b.gr:
            return d_default, False, False
        return d_default, False, False

    def boulder_fight_needed(s, b):
        # on the catwalk the boss cannot reach the ball: no dodging macros needed there except to cross the gap
        return not (b.y < 560 and abs(b.x - 930) > 200)

    def plan_boss(s, dg, tx, hunt, d_default):
        G = s.G
        b = G.ball
        n = G.near_cache
        x0 = b.x
        base = (0, d_default, 0, 0, d_default, False)
        r0 = simulate(G, base, 34, n)
        opp = hunt and abs(tx - b.x) < 380
        gap = G.boss.kind == "boulder" and b.y < 560 and abs(tx - b.x) > 100 and 650 < b.x < 1270
        if not (r0.dead or r0.dmg or opp or gap):
            s.cool = 2
            return
        best, bsc = None, s.score(r0, base, x0, dg, tx)
        threat = r0.dead or r0.dmg
        # without a threat the only reason to plan is a chance to land on the boss or a minion
        macros = s.boss_macros(dg, d_default) if threat else [(0, dg, d, 70, dg, True) for d in (0, 5, 10, 16)] + [(0, dg, 0, 8, dg, True)]
        for m in macros:
            r = simulate(G, m, 48, n)
            sc = s.score(r, m, x0, dg, tx)
            if sc > bsc + 1e-6:
                best, bsc = m, sc
        if best is None:
            s.cool = 4
            if r0.dead:
                alt = (0, -dg, 6, 70, -dg, True)
                s.m, s.k = alt, 0
            return
        s.m, s.k = best, 0

    def boss_macros(s, dg, dd):
        L = []
        for delay in (0, 5, 10, 16):
            L.append((0, dg, delay, 70, dg, True))
            L.append((0, 0, delay, 70, 0, True))
        L.append((0, dg, 0, 8, dg, True))
        L.append((0, -dg, 0, 70, -dg, True))
        L.append((0, -dg, 8, 70, -dg, True))
        for wait in (12, 30):
            L.append((wait, 0, 0, 0, 0, False))
            L.append((wait, dg, 0, 0, dg, False))
            L.append((wait, -dg, 0, 0, -dg, False))
        return L


# ------------------------------------------------------------------------------------------------------ game
STAGES = [
    {"world": "grass", "pool": "w1l1", "liquid": "water", "label": "WORLD 1", "no": 1},
    {"world": "grass", "pool": "w1l2", "liquid": "water", "label": "WORLD 1", "no": 8},
    {"world": "grass", "boss": "monocle", "liquid": "water", "label": "WORLD 1", "no": 15},
    {"world": "factory", "pool": "w2l1", "liquid": "sludge", "label": "WORLD 2", "no": 16},
    {"world": "factory", "pool": "w2l2", "liquid": "sludge", "label": "WORLD 2", "no": 23},
    {"world": "factory", "boss": "mecha", "liquid": "sludge", "label": "WORLD 2", "no": 30},
    {"world": "lava", "pool": "w3l1", "liquid": "lava", "label": "WORLD 3", "no": 31},
    {"world": "ice", "pool": "w3l2", "liquid": "water", "label": "WORLD 3", "no": 38},
    {"world": "lava", "boss": "boulder", "liquid": "lava", "label": "WORLD 3", "no": 45},
]
SCORE_STAR, SCORE_MINION, SCORE_CLEAR, SCORE_BOSS = 500, 200, 1000, 5000
PANEL = rgb565(28, 26, 46)
PANEL_EDGE = rgb565(255, 210, 60)


def make_segs(bands):
    # screen rows split at band boundaries and at tile-row boundaries: one (y0, y1, band, tile row) piece each
    cuts = sorted({0, H} | {b["y0"] for b in bands} | {b["y1"] for b in bands} | {g * T for g in range(NROWS + 1)})
    out = []
    for a, e in zip(cuts, cuts[1:]):
        for i, b in enumerate(bands):
            if b["y0"] <= a < b["y1"]:
                out.append((a, e, i, a // T))
    return out


class Game:
    def __init__(s):
        load_art()
        s.rnd = random
        s.score = 0
        s.stage_i = -1
        s.tk = 0
        s.ts = 0
        s.end = EndScreen()
        s.mode = "boot"
        s.mode_t = 0
        s.ball = Ball()
        s.bot = Bot(s)
        s.parts = []
        s.hud_key = None
        s.hud_rows = None
        s.sky_ox = None
        s.sky_dirty = bytes(SKY_H)
        s.bgc = None
        s.bgc_key = None
        s.W = None
        s.boss = None
        s.shake = 0
        s.cam = 0.0
        s.cam_i = 0
        s.respawn_t = 0
        s.deaths_here = 0
        s.stage_stars = 0
        s.stage_t = 0
        s.stage_deaths = 0
        s.stage_warps = 0
        s.near_cache = None
        s.clear_info = None
        s.log = []
        s.next_stage()

    # --- stage handling
    def next_stage(s):
        s.stage_i += 1
        if s.stage_i >= len(STAGES):
            s.finish()
            return
        spec = STAGES[s.stage_i]
        s.spec = spec
        s.W = Level(spec, s.rnd)
        s.boss = Boss(spec["boss"], s) if spec.get("boss") else None
        s.bands = A["bg"][spec["world"]]
        s.segs = make_segs(s.bands)
        s.seg_rows = [s.bands[i]["rows"][a - s.bands[i]["y0"]:e - s.bands[i]["y0"]] for a, e, i, g in s.segs]
        b = s.ball
        b.x, b.y = s.W.start
        b.vx = b.vy = 0.0
        b.gr, b.coy, b.rvx, b.rvy = False, 0, 0.0, 0.0
        b.hp, b.inv, b.dizzy, b.dead = 3, 0, 0, 0
        b.face = 1
        s.cam = 0.0
        s.parts = []
        s.mode = "intro"
        s.mode_t = 0
        s.stage_t = 0
        s.stage_stars = 0
        s.respawn_t = 0
        s.deaths_here = 0
        s.cp_spawn = s.W.start
        s.bot.reset_level()
        s.hud_key = None
        s.sky_ox = None
        s.sky_dirty = bytes(SKY_H)
        s.bgc = None
        s.bgc_key = None
        s.clear_info = None
        s.stage_deaths = 0
        s.stage_warps = 0

    def finish(s):
        s.mode = "end"
        s.end.start(s.score, "ALL CLEAR" if s.stage_i >= len(STAGES) else "GAME OVER")

    # --- helpers used by the physics and the bot
    def near(s):
        s.near_cache = near_of(s.W, s.ball.x, 720, s.boss)
        return s.near_cache

    def push_mode(s, x):
        W = s.W
        for g in W.gates:
            if g.open < 0.5 and 0 < g.x - x < 1300:
                if any(x - 100 < c.x < g.x for c in W.crates + W.boulders):
                    return True
        return False

    def star_ahead(s, x):
        return any(not st["got"] and x - 40 < st["x"] < x + 660 for st in s.W.stars)

    def warp_ahead(s):
        # decisive recovery for a stuck bot: hop to the next stretch of plain ground and say so with a puff
        W, b = s.W, s.ball
        c0 = int(b.x // T) + 5
        for tx in range(c0, W.nt - 2):
            if W.sol_top[tx] == GT and not any(W.mark[max(0, tx - 1):tx + 2]) and W.sol_top[tx + 1] == GT:
                s.stage_warps += 1
                s.puff(b.x, b.y)
                b.x, b.y, b.vx, b.vy = tx * T + 30, GT * T - R - 2, 0.0, 0.0
                s.puff(b.x, b.y)
                s.bot.m = None
                s.reset_crates()
                return
        s.finish_level()

    def reset_crates(s):
        for c in s.W.crates + s.W.boulders:
            c.x, c.y, c.vx, c.vy = c.x0, c.y0, 0.0, 0.0

    # --- events
    def add_score(s, n, x, y):
        s.score += n
        s.parts.append([x, y - 30, 0.0, -1.2, 36, "text", "+%d" % n])

    def collect_star(s, st):
        st["got"] = True
        s.stage_stars += 1
        s.add_score(SCORE_STAR, st["x"], st["y"])
        s.parts.append([st["x"] - 22, st["y"] - 22, 0, 0, 14, "sparkle", 0])
        for i in range(6):
            a = i * 1.047
            s.parts.append([st["x"] - 7, st["y"] - 7, math.cos(a) * 4, math.sin(a) * 4 - 1, 16, "chip", 2])

    def stomp(s, m, ts):
        m.stun = ts + 36
        x, y, _ = m.pos(ts)
        if m.armor:
            m.armor = False
            m.kind = "roam"
            s.parts.append([x - 30, y - 30, 0, 0, 12, "puff", 0])
            s.add_score(50, x, y)
            return
        m.alive = False
        m.dead_t = 0
        m.x, m.y = x, y
        s.add_score(SCORE_MINION, x, y)
        s.parts.append([x - 30, y - 30, 0, 0, 12, "puff", 0])
        for i in range(5):
            a = i * 1.26
            s.parts.append([x - 7, y - 7, math.cos(a) * 3.5, math.sin(a) * 3.5 - 3, 20, "chip", 3])

    def boss_hit(s):
        bs = s.boss
        bs.damage(2 if bs.kind == "mecha" else 1)
        s.shake = 10
        s.parts.append([bs.x - 75, bs.y - 75, 0, 0, 12, "burst", 0])

    def on_boss_dead(s):
        s.add_score(SCORE_BOSS, s.boss.x, s.boss.y - 70)
        for m in s.W.minions:
            m.alive = False
        for p in s.boss.presses:
            p.t0 = -10 ** 9

    def burst(s, x, y, big=False):
        s.parts.append([x - 75, y - 75, 0, 0, 12, "burst", 0])
        for i in range(10 if big else 7):
            a = random.random() * 6.28
            sp = random.uniform(2, 7)
            s.parts.append([x - 7, y - 7, math.cos(a) * sp, math.sin(a) * sp - 4, random.randint(22, 38), "chip", random.choice((0, 0, 1, 2))])

    def dust(s, x, y):
        s.parts.append([x - 30, y - 50, 0, 0, 10, "puff", 0])

    def puff(s, x, y):
        s.parts.append([x - 30, y - 30, 0, 0, 12, "puff", 0])

    def spawn_wave(s, kind, count):
        bx = s.ball.x
        for i in range(count):
            # they drop in near the ball so a wave does not turn into a chase across the whole arena
            x = min(1650, max(300, bx + (i - (count - 1) / 2) * 260 + random.randint(-40, 40) + (150 if bx < 900 else -150)))
            m = Minion(kind, x, GROUND - 26, max(190, x - 220), min(1730, x + 220), 0.0)
            m.sp = 1.5 if kind == "roam" else 1.9
            m.sp0 = s.ts
            m.off = (x - m.xa) - m.sp * s.ts
            s.W.minions.append(m)

    def die(s):
        b = s.ball
        s.burst(b.x, b.y)
        s.stage_deaths += 1
        s.deaths_here += 1
        s.respawn_t = 40
        s.bot.m = None
        s.bot.sess = None

    def respawn(s):
        b = s.ball
        b.x, b.y = s.cp_spawn
        b.vx = b.vy = 0.0
        b.gr, b.coy, b.rvx, b.rvy = False, 0, 0.0, 0.0
        b.hp, b.inv, b.dizzy, b.dead = 3, 100, 40, 0
        s.reset_crates()
        s.respawn_t = 0
        if s.deaths_here >= 4 and s.boss is None:
            s.deaths_here = 0
            s.warp_ahead()

    def finish_level(s):
        if s.mode != "play":
            return
        s.mode = "clear"
        s.mode_t = 0
        secs = s.stage_t / TICK_RATE
        bonus = max(0, int(((75 if s.boss is None else 95) - secs) * 15))
        s.score += SCORE_CLEAR + bonus
        s.clear_info = (SCORE_CLEAR, bonus, s.stage_stars)
        s.log.append((s.stage_i, s.stage_t, s.stage_deaths, s.stage_stars, s.stage_warps, s.stage_t > (BOSS_TICKS if s.boss else LEVEL_TICKS)))
        s.bot.m = None

    # --- one tick
    def tick(s):
        if s.mode == "end":
            return s.end.tick()
        s.tk += 1
        if s.tk >= CAP_TICKS - 170:
            s.finish()
            return False
        W, b = s.W, s.ball
        if s.shake:
            s.shake -= 1
        if s.mode == "clear":
            s.mode_t += 1
            ex, ey = (W.exit[0], W.exit[1] - 60) if W.exit else (b.x, b.y)
            if s.boss is not None:
                s.boss.update(s)
            b.x += (ex - b.x) * 0.08
            b.y += (ey - b.y) * 0.08
            b.vx = b.vy = 0.0
            s.update_particles()
            s.render()
            if s.mode_t > 95:
                s.next_stage()
            return False
        if s.mode == "intro":
            s.mode_t += 1
            if s.mode_t > 70:
                s.mode = "play"
        d = jp = jh = 0
        if s.respawn_t:
            s.respawn_t -= 1
            if s.respawn_t == 0:
                s.respawn()
        else:
            n = s.near()
            if s.mode == "play":
                s.stage_t += 1
                d, jp, jh = s.bot.input()
                s.stage_limit()
            for sub in range(SUB):
                s.substep(d, jp and sub == 0, jh, n)
                if b.dead:
                    break
            if b.dead and s.respawn_t == 0:
                s.die()
            s.tick_objects(n)
        if s.boss is not None:
            s.boss.update(s)
            if s.boss.done and s.mode == "play":
                s.finish_level()
        s.update_particles()
        s.camera()
        s.render()
        return False

    def stage_limit(s):
        lim = BOSS_TICKS if s.boss is not None else LEVEL_TICKS
        if s.stage_t > lim:
            if s.boss is not None:
                s.boss.hp = 0
                s.boss.hurt_done(s)
            else:
                s.finish_level()

    def substep(s, d, jp, jh, n):
        W, b = s.W, s.ball
        ts = s.ts
        # pushing: the ball shoves a crate at a fixed speed instead of stalling against it
        if d:
            for c in n.crates:
                dx = c.x - b.x
                if dx * d > 0 and abs(dx) < R + 31 and abs(b.y - c.y) < 34:
                    if abs(c.vx) < PUSH_V:
                        c.vx = d * PUSH_V
                    if abs(b.vx) > PUSH_V:
                        b.vx = d * PUSH_V
        for c in n.crates:
            crate_step(c, W)
        for c in n.boulders:
            boulder_step(c, W, 0)
            dx, dy = b.x - c.x, b.y - c.y
            dist = math.hypot(dx, dy)
            if 0 < dist < R + c.r:
                nx, ny = dx / dist, dy / dist
                pen = R + c.r - dist
                b.x += nx * pen * 0.83
                b.y += ny * pen * 0.83
                c.x -= nx * pen * 0.17
                c.y -= ny * pen * 0.17
                vrel = (b.vx - c.vx) * nx + (b.vy - c.vy) * ny
                if vrel < 0:
                    j = -vrel
                    b.vx += j * nx
                    b.vy += j * ny
                    c.vx -= j * nx * 0.2
                    c.vy -= j * ny * 0.2
        for sw in n.seesaws:
            on = abs(b.x - sw.cx) < sw.LEN / 2 and sw.top - 60 < b.y < sw.top + 16 and b.gr
            target = max(-1.0, min(1.0, (b.x - sw.cx) / (sw.LEN / 2))) * sw.MAXA if on else 0.0
            sw.ang += max(-0.0045, min(0.0045, target - sw.ang))
        shapes = W.static_shapes(b.x, b.y, R + 4) + dyn_shapes(n, ts, False, False)
        ball_sub(b, d, jp, jh, shapes)
        if b.impact > 5.0 and b.gr:
            b.squash_t = 9
            if b.impact > 6.5:
                s.dust(b.x, b.y + R)
            b.impact = 0.0
        interact(b, W, n, ts, True, s)
        s.ts += 1

    def tick_objects(s, n):
        W, b = s.W, s.ball
        b.rot += b.vx * SUB / R
        if b.squash_t:
            b.squash_t -= 1
        if b.dizzy:
            b.dizzy -= 1
        # buttons, levers, gates
        boulder_arena = s.boss is not None and s.boss.kind == "boulder"
        for btn in W.buttons:
            hit = circle_rect(b.x, b.y, R - 2, btn["x0"], btn["y0"] - 3, btn["x1"], btn["y1"])
            if not hit:
                for c in n.crates:
                    if c.x + 28 > btn["x0"] and c.x - 28 < btn["x1"] and c.y + 28 >= btn["y0"] - 2:
                        hit = True
                for c in n.boulders:
                    if circle_rect(c.x, c.y, c.r - 2, btn["x0"], btn["y0"] - 3, btn["x1"], btn["y1"]):
                        hit = True
            if boulder_arena:
                if hit and not btn["on"]:
                    btn["on"] = True
                    s.boss.press_switch(btn["gid"])
                elif not hit:
                    btn["on"] = False
            elif hit and not btn["on"]:
                btn["on"] = True
                s.parts.append([(btn["x0"] + btn["x1"]) / 2 - 22, btn["y0"] - 30, 0, 0, 14, "sparkle", 0])
        for lv in W.levers:
            if not lv["on"] and (b.x - lv["x"]) ** 2 + (b.y - lv["y"]) ** 2 < 50 ** 2:
                lv["on"] = True
        for g in W.gates:
            if any(bt["on"] and bt["gid"] == g.gid for bt in W.buttons) or any(l["on"] and l["gid"] == g.gid for l in W.levers):
                g.open = min(1.0, g.open + 0.05)
        for sp in W.springs:
            if sp["t"]:
                sp["t"] -= 1
        for f in W.falls:
            if f.state == 0:
                if b.gr and abs((b.y + R) - f.y) < 4 and f.x0 - 12 < b.x < f.x0 + 132:
                    f.t += 1
                    if f.t > 10:
                        f.state, f.t = 1, 0
                else:
                    f.t = 0
            elif f.state == 1:
                f.t += 1
                if f.t > 14:
                    f.state, f.t, f.vy = 2, 0, 0.0
            elif f.state == 2:
                f.vy += 0.6
                f.y += f.vy
                if f.y > f.top + 900:
                    f.state, f.t = 3, 0
            else:
                f.t += 1
                if f.t > 140:
                    f.state, f.y, f.t = 0, f.top, 0
        for m in W.minions:
            if not m.alive:
                m.dead_t += 1
        for i, (cx, cy) in enumerate(W.checks):
            if i > W.cp_active and b.x > cx - 30:
                W.cp_active = i
                s.cp_spawn = (cx, cy)
                s.deaths_here = 0
                s.parts.append([cx - 22, cy - 80, 0, 0, 14, "sparkle", 0])
        if W.exit and s.boss is None and s.mode == "play":
            ex, ey = W.exit
            if abs(b.x - ex) < 46 and ey - 150 < b.y < ey + 10:
                s.finish_level()

    def update_particles(s):
        out = []
        for p in s.parts:
            p[4] -= 1
            if p[4] <= 0:
                continue
            p[0] += p[2]
            p[1] += p[3]
            if p[5] == "chip":
                p[3] += 0.25
            elif p[5] in ("burst", "puff", "sparkle"):
                p[6] += 1
            out.append(p)
        s.parts = out

    def camera(s):
        W, b = s.W, s.ball
        if s.boss is not None:
            s.cam = 0.0
            return
        target = b.x - 960 + b.face * 150 + b.vx * 10
        s.cam += (target - s.cam) * 0.12
        s.cam = max(0.0, min(W.width - 1920, s.cam))

    # --- rendering
    def render(s):
        W_, b = s.W, s.ball
        cam = int(s.cam)
        if s.shake and s.boss is None:
            cam = max(0, min(W_.width - 1920, cam + random.randint(-4, 4)))
        tk = s.ts // 2
        s.cam_i = cam
        oxs = []
        drift = tk * 0.15
        for i, bd in enumerate(s.bands):
            px = int(cam * bd["f"] + (drift if i == 0 else 0))
            if i == 0:
                px &= ~3        # the far sky moves in 4-pixel steps: invisible, and it lets most frames reuse the old sky
            oxs.append((px % 2560) * 2)
        wa = s.spec["world"]
        static = s.boss is not None
        key = tuple(oxs)
        if static and s.bgc_key == key:
            # an arena does not scroll: its background and walls are composed once and copied
            fr[:] = s.bgc
            s.sky_ox = None
        else:
            s.draw_base(cam, oxs, tk, not static)
            if static:
                s.bgc = bytes(fr)
                s.bgc_key = key
        if static:
            s.draw_gears(cam, tk)
        O = A["obj"]
        for btn in W_.buttons:
            if cam - 60 < btn["x0"] < cam + 1920:
                put(O["button"][btn["gid"]][1 if btn["on"] else 0], btn["x0"] - cam, btn["y1"] - (8 if btn["on"] else 16))
        for lv in W_.levers:
            if cam - 60 < lv["x"] < cam + 1920:
                put(O["lever"][lv["gid"]][1 if lv["on"] else 0], lv["x"] - 22 - cam, lv["y"] - 18)
        for sp in W_.springs:
            if cam - 60 < sp["x"] < cam + 1920:
                st = 1 if sp["t"] > 6 else (2 if sp["t"] > 0 else 0)
                put(O["spring"][st], sp["x"] - 26 - cam, sp["y1"] - 58)
        for gt in W_.gates:
            if cam - 60 < gt.x < cam + 1920:
                spg = O["gate"][gt.gid][max(2, min(5, gt.tiles))]
                put_clip_y(spg, gt.x - 18 - cam, gt.y0 + gt.open * (gt.y1 - gt.y0), gt.y1)
        if W_.exit and s.boss is None:
            ex, ey = W_.exit
            if cam - 120 < ex < cam + 1920:
                put(O["portal"][(tk // 3) % 6], ex - 55 - cam, ey - 150)
        for i, (cx, cy) in enumerate(W_.checks):
            if cam - 80 < cx < cam + 1920:
                if i <= W_.cp_active:
                    put(O["flag_on"][(tk // 4) % 4], cx - 28 - cam, cy + R - 104)
                else:
                    put(O["flag_off"][0], cx - 28 - cam, cy + R - 104)
        ts = s.ts
        tkf = ts * 0.5
        plat_sp = O["platform"][wa]
        for p in W_.plats:
            if min(p.x1, p.x2) - 100 < cam + 1920 and max(p.x1, p.x2) + 100 > cam:
                x, y = p.pos(ts)
                put(plat_sp, x - 75 - cam, y)
        fp = O["fallplat"][wa]
        for f in W_.falls:
            if cam - 140 < f.x0 < cam + 1920 and f.state < 3:
                jit = random.randint(-2, 2) if f.state == 1 else 0
                put(fp, f.x0 - cam + jit, f.y)
        for sw in W_.seesaws:
            if cam - 300 < sw.cx < cam + 2100:
                put(O["pivot"], sw.cx - 30 - cam, sw.top + 8)
                ang = max(-18, min(18, int(round(math.degrees(sw.ang) / 3.0)) * 3))
                put(O["seesaw"][ang], sw.cx - 170 - cam, sw.top - 70)
        for c in W_.crates:
            if cam - 60 < c.x < cam + 1920:
                put(O["crate"][1 if c.metal else 0], c.x - 28 - cam, c.y - 28)
        for c in W_.boulders:
            if cam - 60 < c.x < cam + 1920:
                put(O["boulder"][int(c.rot / (math.pi / 4)) % 8], c.x - 38 - cam, c.y - 38)
        for sw in W_.saws:
            if min(sw.x1, sw.x2) - 80 < cam + 1920 and max(sw.x1, sw.x2) + 80 > cam:
                s.draw_rail(sw, cam)
                x, y = sw.pos(ts)
                put(O["saw"][tk % 6], x - 38 - cam, y - 38)
        for cr in W_.crushers:
            if cam - 120 < cr.x < cam + 1920:
                hy = cr.head_y(tkf)
                ytop = -80 if isinstance(cr, Press) else cr.y0
                yy = int(hy) - 60
                while yy > -60 and yy > ytop - 60:
                    put(O["shaft"], cr.x - 18 - cam, yy)
                    yy -= 60
                put(O["crusher"], cr.x - 60 - cam, hy)
        for l in W_.lasers:
            if cam - 120 < l.x < cam + 1920:
                put(O["laser"][l.d], l.cx - 30 - cam, l.cy - 30)
                if l.active(tkf):
                    s.draw_beam(l, cam, 1)
                elif l.warn(tkf):
                    s.draw_beam(l, cam, 0)
        for cn in W_.cannons:
            if cam - 120 < cn.cx < cam + 1920:
                put(O["cannon"]["R" if cn.dir > 0 else "L"][1 if cn.flash(tkf) else 0], cn.cx - 32 - cam, cn.cy - 30)
                for (bx, by) in cn.bullets(tkf):
                    put(O["shot"], bx - 14 - cam, by - 14)
        for m in W_.minions:
            if m.alive:
                x, y, fwd = m.pos(ts)
                if cam - 80 < x < cam + 1920:
                    key = m.kind if (m.kind != "soldier" or m.armor) else "roam"
                    put(A["minion"][key]["R" if fwd else "L"][(tk // 5) % 2], x - 26 - cam, y - 30)
            elif m.dead_t < 22:
                put(A["minion"]["roam"]["dead"], m.x - 31 - cam, m.y + 6)
        for st in W_.stars:
            if not st["got"] and cam - 60 < st["x"] < cam + 1920:
                put(O["star"][(tk // 3) % 6], st["x"] - 23 - cam, st["y"] - 23 + int(3 * math.sin(tk * 0.2 + st["id"])))
        if s.boss is not None:
            bs = s.boss
            for p in bs.stones:
                put(O["stone"], p[0] - 50, p[1] - 50)
            if bs.state != "away" and (bs.state != "dying" or bs.t % 4 < 2):
                put(bs.sprite(), bs.x - 54, bs.y - 62)
        s.draw_ball()
        for p in s.parts:
            k = p[5]
            if k == "chip":
                put(O["chip"][p[6]], p[0] - cam, p[1])
            elif k == "text":
                draw_str(p[6], int(p[0] - cam - 40), int(p[1]), O["glyph"])
            elif k == "burst":
                put(O["burst"][min(5, p[6] // 2)], p[0] - cam, p[1])
            elif k == "puff":
                put(O["puff"][min(3, p[6] // 3)], p[0] - cam, p[1])
            elif k == "sparkle":
                put(O["sparkle"][min(3, p[6] // 3)], p[0] - cam, p[1])
        s.draw_hud()
        if s.mode == "intro":
            s.draw_banner()
        elif s.mode == "clear":
            s.draw_clear()
        fb[:] = fr

    def draw_base(s, cam, oxs, tk, gears):
        # everything that only depends on the camera: background, terrain, decor, ramps, spikes
        W_ = s.W
        O = A["obj"]
        # tile rows fully covered by one terrain run need no background underneath
        cov = [False] * NROWS
        blk = [None] * NROWS
        off = cam % T
        for g in range(NROWS):
            for x0, x1, ts_name in W_.inter[g]:
                if x0 <= cam and x1 >= cam + 1920:
                    blk[g] = interior_block(ts_name, off)
                    cov[g] = True
                    break
            else:
                for rx0, rx1, lines in W_.runs[g]:
                    if rx0 <= cam and rx1 >= cam + 1920:
                        cov[g] = True
                        break
        sky = s.bands[0]["rows"]
        if s.sky_ox == oxs[0]:
            # same sky as last frame: only the rows something was drawn over need their background back
            for y in [y for y in range(SKY_H) if s.sky_dirty[y]]:
                if not cov[y // T]:
                    fr[y * S:(y + 1) * S] = sky[y][oxs[0]:oxs[0] + S]
            sky_fresh = False
        else:
            sky_fresh = True
        s.sky_ox = oxs[0]
        s.sky_dirty = bytes(DIRTY)
        DIRTY[:] = bytes(SKY_H)
        for (a, e, bi, g), rows in zip(s.segs, s.seg_rows):
            if cov[g] or (bi == 0 and not sky_fresh):
                continue
            ox = oxs[bi]
            o = a * S
            for row in rows:
                fr[o:o + S] = row[ox:ox + S]
                o += S
        if gears:
            s.draw_gears(cam, tk)
        # terrain, then the animated runs (conveyors, liquids)
        for g in range(NROWS):
            y0 = g * T
            if blk[g] is not None:
                if y0 < SKY_H:
                    mark_rows(y0, y0 + T)
                fr[y0 * S:(y0 + T) * S] = blk[g]
                continue
            for rx0, rx1, lines in W_.runs[g]:
                a = rx0 if rx0 > cam else cam
                e = rx1 if rx1 < cam + 1920 else cam + 1920
                if e <= a:
                    continue
                i0, i1 = (a - rx0) * 2, (e - rx0) * 2
                ob = (a - cam) * 2
                n = i1 - i0
                if y0 < SKY_H:
                    mark_rows(y0, y0 + T)
                for j in range(T):
                    o = (y0 + j) * S + ob
                    fr[o:o + n] = lines[j][i0:i1]
            for run in W_.aruns[g]:
                x0, x1 = run[1] * T, run[2] * T
                if x1 <= cam or x0 >= cam + 1920:
                    continue
                cache = run[4]
                if run[0] == "conv":
                    f = (tk // 3) % 4
                    lines = cache.get(f)
                    if lines is None:
                        tl = A["liquid"][run[3]][f]
                        lines = cache[f] = [tl[j] * (run[2] - run[1]) for j in range(T)]
                else:
                    f = (tk // 6) % 4
                    lines = cache.get(f)
                    if lines is None:
                        tl = A["liquid"][run[3][0]][run[3][1]][f]
                        lines = cache[f] = [tl[j] * (run[2] - run[1]) for j in range(T)]
                a = x0 if x0 > cam else cam
                e = x1 if x1 < cam + 1920 else cam + 1920
                i0, i1 = (a - x0) * 2, (e - x0) * 2
                ob = (a - cam) * 2
                n = i1 - i0
                if y0 < SKY_H:
                    mark_rows(y0, y0 + T)
                for j in range(T):
                    o = (y0 + j) * S + ob
                    fr[o:o + n] = lines[j][i0:i1]
        for (x, y, sp) in W_.decor:
            if cam - 80 < x < cam + 1920:
                put(sp, x - cam, y)
        wa = s.spec["world"]
        sl = A["slope"][wa]
        for (x, y, ch) in W_.ramps:
            if cam - 60 < x * T < cam + 1920:
                put(sl[ch], x * T - cam, y * T)
        for (x, y, k) in W_.spikes:
            if cam - 60 < x * T < cam + 1920:
                if k == "up":
                    put(O["spike_up"], x * T - cam, (y + 1) * T - 40)
                else:
                    put(O["spike_down"], x * T - cam, y * T)

    def draw_gears(s, cam, tk):
        for (gx, gy, kind, dr) in s.W.gear_decor:
            sx = gx - int(cam * 0.9)
            if -200 < sx < 1920:
                put(A["obj"]["gear"][kind][(tk // 2 * dr) % 8], sx, gy)

    def draw_rail(s, sw, cam):
        # a dark rail under the saw: one rect whichever way it runs
        c = rgb565(58, 62, 78)
        if sw.y1 == sw.y2:
            rect_fill(min(sw.x1, sw.x2) - cam, sw.y1 - 4, max(sw.x1, sw.x2) - cam, sw.y1 + 4, c)
        else:
            rect_fill(sw.x1 - 4 - cam, min(sw.y1, sw.y2), sw.x1 + 4 - cam, max(sw.y1, sw.y2), c)

    def draw_beam(s, l, cam, on):
        x0, y0, x1, y1 = l.rect
        horiz = l.d in "LR"
        if on:
            rect_fill(x0 - cam - (0 if horiz else 4), y0 - (4 if horiz else 0), x1 - cam + (0 if horiz else 4), y1 + (4 if horiz else 0), rgb565(255, 150, 150))
            rect_fill(x0 - cam, y0, x1 - cam, y1, rgb565(255, 60, 60))
            if horiz:
                rect_fill(x0 - cam, (y0 + y1) / 2 - 2, x1 - cam, (y0 + y1) / 2 + 2, rgb565(255, 240, 240))
            else:
                rect_fill((x0 + x1) / 2 - 2 - cam, y0, (x0 + x1) / 2 + 2 - cam, y1, rgb565(255, 240, 240))
        elif horiz:
            rect_fill(x0 - cam, (y0 + y1) / 2 - 1, x1 - cam, (y0 + y1) / 2 + 1, rgb565(190, 90, 90))
        else:
            rect_fill((x0 + x1) / 2 - 1 - cam, y0, (x0 + x1) / 2 + 1 - cam, y1, rgb565(190, 90, 90))

    def expression(s):
        b = s.ball
        if b.dizzy > 0:
            return "dizzy"
        if s.tk % 110 < 4:
            return "blink"
        if s.tk % 4 == 0:
            s._scared = s.scared()
        return "scared" if getattr(s, "_scared", False) else "happy"

    def scared(s):
        # hazards close to the ball make it nervous
        b, W_ = s.ball, s.W
        if W_.hz_hit(b.x + 60 * b.face, b.y, 70) or W_.hz_hit(b.x, b.y, 70):
            return True
        n = s.near_cache
        if n is None:
            return False
        ts = s.ts
        for sw in n.saws:
            sx, sy = sw.pos(ts)
            if abs(sx - b.x) < 180 and abs(sy - b.y) < 130:
                return True
        for m in n.minions:
            x, y, _ = m.pos(ts)
            if abs(x - b.x) < 150 and abs(y - b.y) < 90:
                return True
        for c in n.crush:
            if abs(c.x - b.x) < 150:
                return True
        for l in n.lasers:
            if abs(l.x - b.x) < 130 and l.active(ts * 0.5):
                return True
        for cn in n.cannons:
            for (bx, by) in cn.bullets(ts * 0.5):
                if abs(bx - b.x) < 230 and abs(by - b.y) < 70:
                    return True
        bs = n.boss
        return bs is not None and bs.hurts and abs(bs.x - b.x) < 260 and bs.state != "away"

    def draw_ball(s):
        b = s.ball
        if b.dead:
            return
        if b.inv > 0 and (s.tk // 3) % 2 == 0 and s.mode == "play":
            return
        cam = s.cam_i
        sq = 0
        if b.squash_t > 6:
            sq = 3
        elif b.squash_t > 3:
            sq = 2
        elif b.squash_t == 0 and not b.gr:
            if b.vy < -5:
                sq = 1
            elif b.vy > 7:
                sq = 4
        rot = int(math.degrees(b.rot) / 30) % 12
        body = A["ball"]["body"][sq][rot]
        if b.vy < -4:
            pd = "U"
        elif b.vy > 6:
            pd = "D"
        elif b.vx > 0.4:
            pd = "R"
        elif b.vx < -0.4:
            pd = "L"
        else:
            pd = "R" if b.face > 0 else "L"
        face = A["ball"]["face"][s.expression() + pd][sq]
        w, h, _ = body
        x = int(b.x - w / 2 - cam)
        y = int(b.y + R - h) if (b.gr or sq in (2, 3)) else int(b.y - h / 2)
        put(body, x, y)
        put(face, x, y)

    def hud_text(s):
        return "%s  LEVEL %d" % (s.spec["label"], s.spec["no"])

    def draw_hud(s):
        key = (s.stage_stars, s.ball.hp, s.stage_i, s.score)
        if key != s.hud_key:
            s.hud_key = key
            O = A["obj"]
            gl = O["glyph"]
            rows = []
            edge = PANEL_EDGE.to_bytes(2, "little")
            inner = PANEL.to_bytes(2, "little")
            for panel_w in (780, 450):
                pr = []
                for y in range(66):
                    if y < 3 or y >= 63:
                        pr.append(bytearray(edge * panel_w))
                    else:
                        pr.append(bytearray(edge * 3 + inner * (panel_w - 6) + edge * 3))
                rows.append(pr)
            left, right = rows

            def paste(pr, sp, x, y):
                for o, bts, n in sp[2]:
                    dy, xo = divmod(o, S)
                    xo = xo // 2 + x
                    yy = y + dy
                    if 0 <= yy < 66 and xo >= 0 and xo * 2 + n <= len(pr[yy]):
                        pr[yy][xo * 2:xo * 2 + n] = bts
            for i in range(3):
                paste(left, O["hud_star"] if i < s.stage_stars else O["hud_star_off"], 14 + i * 44, 14)
            for i in range(3):
                paste(left, O["hud_life"] if i < s.ball.hp else O["hud_life_off"], 160 + i * 36, 18)
            x = 290
            for c in s.hud_text():
                paste(left, gl[c], x, 6)
                x += gl[c][0]
            x = 16
            for c in "SCORE %d" % s.score:
                paste(right, gl[c], x, 6)
                x += gl[c][0]
            s.hud_rows = (left, right)
        left, right = s.hud_rows
        for j in range(66):
            o = (14 + j) * S + 20 * 2
            fr[o:o + 1560] = left[j]
            o = (14 + j) * S + 1450 * 2
            fr[o:o + 900] = right[j]

    def draw_banner(s):
        gl = A["obj"]["glyph_big"]
        t = s.hud_text()
        draw_str(t, (1920 - text_w(t, gl)) // 2, 360, gl)
        if s.boss is not None:
            tt = "BOSS BATTLE!"
            draw_str(tt, (1920 - text_w(tt, gl)) // 2, 480, gl)

    def draw_clear(s):
        O = A["obj"]
        gl = O["glyph_big"]
        t = "BOSS DEFEATED!" if s.boss is not None else "LEVEL CLEAR!"
        draw_str(t, (1920 - text_w(t, gl)) // 2, 300, gl)
        if s.clear_info and s.mode_t > 20:
            base, bonus, st = s.clear_info
            g2 = O["glyph"]
            for i, line in enumerate(("STARS %d/3" % st, "TIME BONUS +%d" % bonus, "CLEAR +%d" % base)):
                draw_str(line, (1920 - text_w(line, g2)) // 2, 440 + i * 56, g2)


def make():
    g = Game()

    def step():
        return g.tick()
    return step
