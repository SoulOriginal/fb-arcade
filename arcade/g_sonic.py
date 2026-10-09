# A self-playing Sonic-style platformer: procedurally generated acts over three zones, physics from the Sonic
# Physics Guide (60 Hz, so two physics steps per 30 Hz tick), and a bot that plays like a skilled player.
#
# Rendering: the picture is a native Mega Drive frame of 320x216 pixels shown at x5 (1600x1080) with black side bars.
# Every picture row is a full 3840-byte scanline buffer (10 bytes per pixel, starting LEFT bytes in) that is written
# once to the 5 scanlines it covers. Parallax comes from taking a different slice of a pre-rendered periodic strip
# per row; terrain is spliced in as precomputed runs; sprites are opaque runs.
from fbcore import *
import math
from bisect import bisect_left, bisect_right

D = load_bundle("g_sonic.bin")

VW, VH, PX = 320, 216, 5
SB = PX * 2
LEFT = (W - VW * PX) // 2 * 2
S5 = S * PX
BLACKROW = bytes(S)
INF = 9999
YMIN, YMAX, WH, LAVA_Y = 208, 288, 380, 320
TILE_ROWS = 64
FEET_Y = 172

ZONES = (("ghz", "GREEN HILL", (30, 90, 220)), ("mz", "MARBLE", (130, 40, 160)), ("syz", "SPRING YARD", (40, 70, 170)))
ACT_TILES = (360, 400, 440, 390, 430, 470, 420, 460, 500)
CHAIN_POINTS = (100, 200, 500, 1000)
START_LIVES = 3

# Sonic Physics Guide constants (per 60 Hz step)
ACC, DEC, FRC, TOP = 0.046875, 0.5, 0.046875, 6.0
ROLL_FRC, ROLL_DEC = 0.0234375, 0.125
SLOPE, ROLL_UP, ROLL_DOWN = 0.125, 0.078125, 0.3125
AIR_ACC, GRAV, JUMP, JUMP_CUT = 0.09375, 0.21875, 6.5, -4.0
HURT_GRAV = 0.1875
WAVE = [int(round(1.6 * math.sin(i * math.pi / 16))) for i in range(64)]


def ck(r, g, b):
    return rgb565(r, g, b).to_bytes(2, "little") * PX


def draw(rows, spr, x, y, width=VW, left=LEFT):
    # Opaque runs are patched straight into the row buffers; clipping is only computed when the sprite pokes out.
    w, h, sr = spr
    if x >= width or x + w <= 0 or y >= len(rows) or y + h <= 0:
        return
    r0, r1 = max(0, -y), min(h, len(rows) - y)
    if x >= 0 and x + w <= width:
        for r in range(r0, r1):
            row = rows[y + r]
            for off, data in sr[r]:
                a = left + (x + off) * SB
                row[a:a + len(data)] = data
        return
    for r in range(r0, r1):
        row = rows[y + r]
        for off, data in sr[r]:
            a = x + off
            n = len(data) // SB
            lo, hi = max(a, 0), min(a + n, width)
            if lo < hi:
                row[left + lo * SB:left + hi * SB] = data[(lo - a) * SB:(hi - a) * SB]


def fill_span(rows, x, y, w, h, col):
    for r in range(max(0, y), min(len(rows), y + h)):
        lo, hi = max(0, x), min(VW, x + w)
        if lo < hi:
            rows[r][LEFT + lo * SB:LEFT + hi * SB] = col * (hi - lo)


FONT = D["font"]


def text_width(s, size):
    return sum(FONT[size]["adv"].get(ch, 0) for ch in s)


def put_text(rows, s, x, y, size="S", color="white", width=VW, left=LEFT):
    f = FONT[size]
    g = f["g"][color]
    for ch in s:
        if ch != " " and ch in g:
            draw(rows, g[ch], x, y, width, left)
        x += f["adv"].get(ch, 0)


class O:
    __slots__ = ("k", "x", "y", "vx", "vy", "t", "a", "b", "alive", "skip")

    def __init__(s, k, x, y, vx=0.0, vy=0.0, a=0, b=0):
        s.k, s.x, s.y, s.vx, s.vy, s.t, s.a, s.b, s.alive, s.skip = k, x, y, vx, vy, 0, a, b, True, False


# ------------------------------------------------------------------------------------------------ level
class Level:
    # Terrain is a heightfield built from 16 px tiles whose surface is linear inside the tile. The same
    # formula (H + int(d*k/16)) is used by the build script for the tile art, so physics and picture agree.
    def __init__(self, zi, act, rng):
        self.zi, self.act, self.rng = zi, act, rng
        self.zone = ZONES[zi][0]
        self.ntiles = ACT_TILES[zi * 3 + act]
        self.spawns = []
        self.decor = []
        self.build_layout()
        self.build_arrays()
        self.stages = self.foreground_stages()

    # ---- layout ----------------------------------------------------------------------------------
    def build_layout(self):
        rng, lvl = self.rng, self.zi * 3 + self.act
        H, E, dl, sp = [252], [], [], self.spawns
        self.H, self.E, self.dl = H, E, dl

        def surf(x):
            i, k = int(x) // 16, int(x) % 16
            return H[i] + int((dl[i] or 0) * k / 16)

        def add(d):
            dl.append(d)
            E.append(H[-1] + (d or 0))
            H.append(E[-1])

        def step(dy):
            # A vertical wall between two tiles: the next tile simply starts higher or lower than this one ended.
            H[-1] += dy

        def flat(n):
            for _ in range(n):
                add(0)

        def ring_line(x0, n, y, step=14):
            for i in range(n):
                sp.append(("ring", x0 + i * step, y))

        def ring_arc(x0, x1, y, peak, n):
            for i in range(n):
                t = i / (n - 1)
                sp.append(("ring", x0 + (x1 - x0) * t, y - 8 - peak * 4 * t * (1 - t)))

        def foe(kind, x):
            sp.append((kind, x, 0))

        def decorate(t0, t1):
            zone = self.zone
            t = t0 + rng.randint(0, 2)
            while t < t1 - 1:
                if dl[t] == 0 and (t + 1 >= len(dl) or dl[t + 1] == 0):
                    x = t * 16 + 8
                    r = rng.random()
                    if zone == "ghz":
                        kind = (rng.choice(("palm1", "palm2", "palm3")) if r < 0.4 else "flower" if r < 0.62
                                else "sunflower" if r < 0.8 else "totem")
                    elif zone == "mz":
                        kind = "column" if r < 0.5 else "brazier"
                    else:
                        kind = "lamp"
                    self.decor.append((kind, x, H[t]))
                t += rng.randint(2, 5)

        counts = {"spring": 0}
        flat(14)
        while len(dl) < self.ntiles - 26:
            weights = {"flat": 26, "hill": 22 + (6 if self.zone == "mz" else 0), "pit": 12 + lvl, "ledge": 12,
                       "spikes": 6 + lvl, "gauntlet": 0 if lvl < 1 else 4 + 2 * lvl,
                       "spring": 5 if counts["spring"] < 2 else 0, "bump": 14 if self.zone == "syz" else 0}
            kind = rng.choices(list(weights), list(weights.values()))[0]
            t0 = len(dl)
            if kind == "flat":
                n = rng.randint(5, 10)
                flat(n)
                y = H[t0]
                if rng.random() < 0.42:
                    ring_line((t0 + 1) * 16, rng.randint(3, 6), y - 16)
                if rng.random() < 0.26 + 0.04 * lvl and n >= 7:
                    pool = ["moto", "moto", "crab"] if lvl >= 1 else ["moto"]
                    pool += ["buzz"] if lvl >= 2 else []
                    foe(rng.choice(pool), (t0 + rng.randint(3, n - 2)) * 16)
                if rng.random() < 0.2 and n >= 7:
                    sp.append(("monitor", (t0 + n - 2) * 16,
                               rng.choices(("ring", "shield", "shoes", "invinc", "life"), (40, 20, 15, 15, 10))[0]))
                decorate(t0, t0 + n)
            elif kind == "hill":
                rise = rng.choice((16, 24, 32, 40, 48))
                sign = 1 if H[-1] - rise >= YMIN else -1
                if H[-1] + rise > YMAX:
                    sign = 1
                steps = []
                left = rise
                while left > 0:
                    d = rng.choice((4, 4, 8)) if left >= 8 else 4
                    steps.append(d)
                    left -= d
                up = [-sign * d for d in steps]
                down = [sign * d for d in rng.sample(steps, len(steps))]
                for d in up:
                    add(d)
                flat(rng.randint(0, 3))
                for d in down:
                    add(d)
                flat(2)
                for i in range(t0 * 16 + 8, len(dl) * 16 - 24, 24):
                    sp.append(("ring", i, surf(i) - 24))
                mid = (t0 + len(up) + 1) * 16
                if rng.random() < 0.3 + 0.03 * lvl and dl[(mid // 16)] == 0:
                    foe("moto", mid)
            elif kind == "pit":
                flat(3)
                w = rng.randint(3, min(7, 4 + lvl // 2))
                y = H[-1]
                x0 = len(dl) * 16
                for _ in range(w):
                    add(None)
                x1 = len(dl) * 16
                ring_arc(x0 - 16, x1 + 16, y - 10, 46, 7 + w // 2)
                if self.zone == "ghz" and w >= 4 and rng.random() < 0.6:
                    sp.append(("chopper", (x0 + x1) // 2, y + 80))
                flat(3)
            elif kind == "ledge":
                flat(3)
                rise = rng.choice((16, 32, 48))
                up = H[-1] - rise >= YMIN or H[-1] + rise > YMAX
                dy = -rise if up else rise
                step(dy)
                n = rng.randint(4, 8)
                flat(n)
                y = H[-1]
                ring_line((t0 + 4) * 16, min(n, 5), y - 16)
                if n >= 6 and rng.random() < 0.5:
                    foe("moto", (t0 + 3 + n // 2) * 16)
                decorate(t0 + 3, t0 + 3 + n)
                step(-dy)
                flat(3)
            elif kind == "spikes":
                flat(3)
                n = rng.randint(1, 3)
                x0 = len(dl) * 16
                y = H[-1]
                flat(2 * n)
                sp.append(("spikes", x0, n))
                ring_arc(x0 - 20, x0 + 32 * n + 20, y - 10, 50, 7)
                flat(3)
            elif kind == "gauntlet":
                flat(14)
                for off in (3, 7, 11):
                    pool = ["moto", "crab"] + (["buzz"] if lvl >= 3 else [])
                    foe(rng.choice(pool), (t0 + off) * 16)
                ring_line((t0 + 1) * 16, 8, H[t0] - 16)
                decorate(t0, t0 + 14)
            elif kind == "spring":
                counts["spring"] += 1
                flat(2)
                y = H[-1]
                sx = len(dl) * 16 + 8
                sp.append(("spring", sx, "red"))
                flat(24)
                for i in range(9):
                    sp.append(("ring", sx + 50 + i * 26, y - 20 - 90 * math.sin(math.pi * i / 8)))
            else:
                flat(12)
                for off in (3, 6, 9):
                    sp.append(("bumper", (t0 + off) * 16 + 8, H[t0] - rng.randint(38, 54)))
                ring_line((t0 + 1) * 16, 9, H[t0] - 16)
        flat(8)
        self.sign_x = len(dl) * 16 + 8
        sp.append(("sign", self.sign_x, 0))
        flat(16)
        self.L = len(dl) * 16
        mid = len(dl) // 2
        while not (dl[mid] == 0 and all(d == 0 for d in dl[mid - 2:mid + 3])):
            mid += 1
        self.cp_x = mid * 16
        # Enemies and their shots near a jump are what knocks the bot into the pit, so the approach and the
        # landing zone of every pit and spike row are kept clear, and so is the start of the act.
        danger = []
        for i, d in enumerate(dl):
            if d is None and (i == 0 or dl[i - 1] is not None):
                j = i
                while dl[j] is None:
                    j += 1
                danger.append((i * 16 - 170, j * 16 + 280))
        danger += [(x - 110, x + 32 * n + 190) for k, x, n in sp if k == "spikes"]
        sp[:] = [it for it in sp if it[0] not in ("moto", "crab", "buzz")
                 or (it[1] >= 30 * 16 and not any(a < it[1] < b for a, b in danger))]

    # ---- arrays used by physics ---------------------------------------------------------------------
    def build_arrays(self):
        H, dl, L = self.H, self.dl, self.L
        lava = self.zone == "mz"
        ph, sol = [INF] * L, [WH] * L
        self.pits = []
        for i, d in enumerate(dl):
            if d is None:
                if not self.pits or self.pits[-1][1] != i * 16:
                    self.pits.append([i * 16, (i + 1) * 16])
                else:
                    self.pits[-1][1] = (i + 1) * 16
                if lava:
                    for k in range(16):
                        sol[i * 16 + k] = LAVA_Y
                continue
            for k in range(16):
                y = H[i] + int(d * k / 16)
                ph[i * 16 + k] = y
                sol[i * 16 + k] = y
        self.pits = [tuple(p) for p in self.pits]
        self.ph, self.sol = ph, sol
        sn, cs = [0.0] * L, [1.0] * L
        for x in range(L):
            a, b = ph[max(0, x - 6)], ph[min(L - 1, x + 6)]
            if a < INF and b < INF:
                ang = math.atan2(a - b, 12)
                sn[x], cs[x] = math.sin(ang), math.cos(ang)
        self.sn, self.cs = sn, cs

    # ---- pre-rendered foreground rows ---------------------------------------------------------------
    def foreground_stages(self):
        # A generator so the game can build the foreground over several ticks while the title card is shown:
        # doing it at once would be a visible hitch on the Pi.
        zt = D["zones"][self.zone]
        tiles, fill, lfill = zt["tiles"], zt["fill"], zt["lava_fill"]
        H, dl, L = self.H, self.dl, self.L
        self.rmin = (min(H + self.E) // 16) * 16 - 16
        reps = L // 32 + 1
        fgc = {}
        for wy in range(self.rmin, WH):
            fgc[wy] = bytearray((fill[wy % 32] * reps)[:L * SB])
        self.fgc = fgc
        yield
        lava = self.zone == "mz"
        n = len(dl)
        for part in range(2):
            for i in range(part * n // 2, (part + 1) * n // 2):
                d = dl[i]
                a, b = i * 16 * SB, (i + 1) * 16 * SB
                if d is None:
                    if lava:
                        for r, row in enumerate(tiles[("lava", i % 2)]):
                            if LAVA_Y + r < WH:
                                fgc[LAVA_Y + r][a:b] = row
                        for wy in range(LAVA_Y + TILE_ROWS, WH):
                            fgc[wy][a:b] = lfill[wy % 32][(i % 2) * 16 * SB:(i % 2 + 1) * 16 * SB]
                    continue
                lo = min(H[i], self.E[i])
                base = lo // 16 * 16
                rows = tiles[(i % 2, (base // 16) % 2, lo - base, d)]
                for r in range(TILE_ROWS):
                    if base + r < WH:
                        fgc[base + r][a:b] = rows[r]
            yield
        sol = self.sol
        togs = [[] for _ in range(WH)]
        for x in range(1, L):
            p, q = sol[x - 1], sol[x]
            if p != q:
                for wy in range(min(p, q), max(p, q)):
                    togs[wy].append(x)
        self.togs = togs
        self.init = [sol[0] <= wy for wy in range(WH)]
        yield


# ------------------------------------------------------------------------------------------------- game
class Game:
    def __init__(self):
        self.rng = random.Random()
        self.tick = 0
        self.score = 0
        self.lives = START_LIVES
        self.act_index = 0
        self.state = "card"
        self.state_t = 0
        self.prev = [None] * VH
        self.end = None
        self.spec = None
        self.level = None
        self.t_act = 0

    # ---- level lifecycle ---------------------------------------------------------------------------
    def load_level(self):
        zi, act = divmod(self.act_index, 3)
        self.level = Level(zi, act, self.rng)
        self.zone = self.level.zone

    def finish_load(self):
        self.spec = self.bg_spec(self.zone)
        self.mode = "speed" if self.rng.random() < 0.45 else "collect"
        self.roll_ok = self.rng.random() < 0.6
        self.checkpoint = False
        self.spawn_objects()
        self.reset_player(40)

    def bg_spec(self, zone):
        shared = {}
        out = []
        for frames, P, f, wave in D["bg"][zone]:
            fr = []
            for b in frames:
                if id(b) not in shared:
                    shared[id(b)] = bytearray(b)
                fr.append(shared[id(b)])
            out.append((fr, P, f, wave))
        return out

    def spawn_objects(self):
        lv = self.level
        ph = lv.ph
        st = {"ring": [], "monitor": [], "spring": [], "spikes": [], "bumper": [], "sign": [], "decor": []}
        self.pending = []
        for k, x, e in lv.spawns:
            x = int(x)
            if k == "ring":
                st["ring"].append(O("ring", x, e))
            elif k == "monitor":
                st["monitor"].append(O("monitor", x, ph[x], a=e))
            elif k == "spring":
                st["spring"].append(O("spring", x, ph[x], a=e))
            elif k == "spikes":
                st["spikes"].append(O("spikes", x, ph[x], a=e))
            elif k == "bumper":
                st["bumper"].append(O("bumper", x, e))
            elif k == "sign":
                st["sign"].append(O("sign", x, ph[x]))
            else:
                o = O(k, x, ph[x] if ph[x] < INF else 0)
                o.vx = 0.55 if self.rng.random() < 0.5 else -0.55
                if k == "buzz":
                    o.y = ph[x] - self.rng.randint(44, 70)
                    o.a = o.y
                elif k == "chopper":
                    o.y = o.a = e
                    o.vx = 0.0
                else:
                    o.a = x
                    if k == "crab":
                        o.vx = 0.5 * (1 if self.rng.random() < 0.5 else -1)
                self.pending.append(o)
        for k, x, y in lv.decor:
            st["decor"].append(O(k, x, y, a=self.rng.randint(0, 7)))
        self.pending.sort(key=lambda o: o.x)
        self.pend_i = 0
        self.stat = {k: sorted(v, key=lambda o: o.x) for k, v in st.items()}
        self.stat_x = {k: [o.x for o in v] for k, v in self.stat.items()}
        hz = [(p[0], p[1], "pit") for p in lv.pits]
        for o in self.stat["spikes"]:
            hz.append((o.x, o.x + 32 * o.a, "spikes"))
        for x in range(1, lv.L):
            if lv.ph[x - 1] < INF and lv.ph[x] < INF and lv.ph[x - 1] - lv.ph[x] > 14:
                hz.append((x - 2, x + 2, "wall"))
        hz.sort()
        self.hazards = hz
        self.haz_x = [h[0] for h in hz]
        self.foes, self.dyn = [], []
        self.chain = 0

    def reset_player(self, x):
        lv = self.level
        if self.checkpoint:
            x = lv.cp_x
        self.x, self.y = float(x), float(lv.ph[int(x)])
        self.xs = self.ys = self.gs = 0.0
        self.ground, self.rolling, self.jumped, self.spring_air = True, False, False, False
        self.hurt = self.dead = False
        self.facing = 1
        self.inv = 0
        self.shield = False
        self.rings = 0
        self.steps = 0
        self.air_n = 0
        self.hold_n = 0
        self.air_cmd = (1, False)
        self.back = None
        self.back_t = 0
        self.back_cd = 300
        self.snap_step = -1
        self.snap = []
        self.sn = 0.0
        self.skid = False
        self.idle_n = 0
        self.top, self.acc = TOP, ACC
        self.shoes_t = self.invinc_t = 0
        self.finishing = False
        self.sign_t = -1
        self.cam_x = max(0.0, min(self.x - 150, lv.L - VW))
        self.cam_y = max(YMIN - 176.0, min(self.y - FEET_Y, YMAX - 140.0))
        self.best_x, self.stall = self.x, 0
        self.anim = 0.0
        self.dead_t = 0
        self.t_act = 0
        self.dyn, self.foes = [], []
        self.pend_i = bisect_left([o.x for o in self.pending], self.x - 200)

    # ---- bot ----------------------------------------------------------------------------------------
    def next_hazard(self, x):
        i = bisect_right(self.haz_x, x - 40)
        lo = max(0, i - 3)
        for h in self.hazards[lo:i + 3]:
            if h[1] > x - 4:
                return h
        return None

    def hazard_near(self, x):
        # Landing right in front of spikes leaves no run-up to clear them, so the zone before spikes is wider.
        i = bisect_right(self.haz_x, x + 60)
        for h in self.hazards[max(0, i - 4):i]:
            if h[2] == "wall":
                continue
            pre = 54 if h[2] == "spikes" else 8
            if h[0] - pre < x < h[1] + 24:
                return True
        return False

    def foe_snapshot(self):
        # Everything the ball could bounce off in the next second: (x, vx, centre y, half w, half h, object).
        if self.snap_step != self.steps:
            self.snap_step = self.steps
            out = []
            for f in self.foes:
                if f.alive and abs(f.x - self.x) < 300:
                    bx, by, bw, bh = self.foe_box(f)
                    vx = f.vx if f.k == "moto" else f.vx * 0.66 if f.k == "crab" else (-1.0 if f.b >= 1 else 0.0)
                    out.append((bx, vx, by, bw, bh, f))
            for o in self.near("monitor", self.x, 300):
                if o.b == 0:
                    out.append((o.x, 0.0, o.y - 14, 14, 13, o))
            self.snap = out
        return self.snap

    def sim(self, hold_n, delay, dirn=1, target=None):
        # Forward-simulates a jump started `delay` steps from now. Returns (landing x or None, hit target, path).
        # Enemies on the way are bounced off exactly as bounce_on() does, because that changes where the arc ends.
        lv = self.level
        ph = lv.ph
        gsx = self.gs
        if self.ground:
            x = self.x + gsx * lv.cs[int(self.x)] * delay
            if x < 0 or x >= lv.L - 12 or ph[int(x)] >= INF:
                return None, False, ()
            y = float(ph[int(x)])
            sn, cs = lv.sn[int(x)], lv.cs[int(x)]
            xs, ys = gsx * cs - JUMP * sn, -gsx * sn - JUMP * cs
        else:
            x, y, xs, ys = self.x, self.y, self.xs, self.ys
        foes = [f for f in self.foe_snapshot() if abs(f[0] - x) < 340]
        alive = [True] * len(foes)
        path = []
        hit = False
        jumped_now = self.jumped
        for t in range(120):
            if t >= hold_n and ys < JUMP_CUT and (jumped_now or self.ground):
                ys = JUMP_CUT
            if dirn > 0 and xs < self.top:
                xs = min(xs + AIR_ACC, self.top)
            elif dirn < 0 and xs > -self.top:
                xs = max(xs - AIR_ACC, -self.top)
            if -4 < ys < 0 and abs(xs) >= 0.125:
                xs -= int(xs / 0.125) / 256
            x += xs
            y += ys
            vy = ys
            ys += GRAV
            ix = int(x)
            if ix < 0 or ix >= lv.L:
                return None, hit, path
            path.append((x, y))
            for i, (fx0, fvx, fy, fw, fh, obj) in enumerate(foes):
                if alive[i] and abs(x - (fx0 + fvx * (t + delay))) < fw + 7 and abs((y - 12) - fy) < fh + 12:
                    alive[i] = False
                    if obj is target:
                        hit = True
                    if ys > 0 and y - 16 < fy:
                        ys = -ys
                    else:
                        ys += 1 if ys < 0 else -1
            if vy >= 0:
                gy = ph[ix]
                if y >= gy:
                    if gy < INF and y - gy <= 20 + vy:
                        return x, hit, path
        return None, hit, path

    def landing_safe(self, lx):
        return lx is not None and not self.hazard_near(lx)

    def clears(self, hz, hold_n, delay):
        lx, _, path = self.sim(hold_n, delay)
        return lx is not None and lx >= hz[1] + 8 and self.landing_safe(lx) and not self.spikes_hit(path)

    def foe_box(self, f):
        if f.k == "moto":
            return f.x, f.y - 9, 12, 9
        if f.k == "crab":
            return f.x, f.y - 12, 14, 10
        if f.k == "monitor":
            return f.x, f.y - 15, 15, 14
        if f.k == "chopper":
            return f.x, f.y, 7, 11
        return f.x, f.y, 15, 8

    def bot(self):
        # returns (direction, jump pressed, jump held, down)
        if self.hurt or self.dead:
            return 0, False, False, False
        if self.finishing:
            return (-1 if self.gs > 1.2 else 0), False, False, False
        if not self.ground:
            self.air_n += 1
            if self.air_n % 3 == 1:
                self.air_cmd = self.plan_air()
            dirn, cut = self.air_cmd
            return dirn, False, (not cut) and self.air_n < self.hold_n, False
        self.air_n = 0
        x, gs = self.x, self.gs
        if self.stall > 300 and abs(gs) < 0.3:
            return 1, True, True, False
        back = self.backtrack(x, gs)
        if back:
            return back, False, False, False
        jump = False
        haz = self.next_hazard(x)
        if haz and gs > 0.5:
            dist = haz[0] - x
            reach = abs(gs) * 62
            if dist < reach + 20:
                for hold in (999, 6, 0):
                    if self.clears(haz, hold, 0) and not self.clears(haz, hold, 3):
                        jump = True
                        self.hold_n = hold
                        break
                if not jump and 0 < dist < max(8, gs * 2.5):
                    jump = True
                    self.hold_n = 999
        # Rolling into a ground enemy is the second way a player kills it (the first is jumping on it).
        rolling_attack = (gs >= 4 and (haz is None or haz[0] - x > 150)
                          and any(f.alive and f.b == 1 and not f.skip and 20 < f.x - x < 120 for f in self.foes))
        if not jump:
            jump = self.dodge_shot(x) or self.try_attack(x, gs, rolling_attack)
        if not jump and self.mode == "speed":
            for o in self.near("spring", x, 60):
                if 8 < o.x - x < 30 + gs * 4 and o.alive:
                    jump = True
                    self.hold_n = 999
        down = False
        if not jump and not self.rolling and (haz is None or haz[0] - x > 150):
            if rolling_attack or (gs > 2.8 and self.sn < -0.1 and self.roll_ok):
                down = True
        return 1, jump, True, down

    def backtrack(self, x, gs):
        # A collecting player turns round for a ring line that was jumped over; the braking shows the skid frames.
        if self.back_cd > 0:
            self.back_cd -= 1
        if self.back is not None:
            self.back_t += 1
            if (x <= self.back or self.back_t > 240 or self.rolling or self.hurt
                    or any(f.alive and abs(f.x - x) < 160 for f in self.foes)):
                self.back, self.back_cd = None, 900
                self.stall, self.best_x = 0, x
                return 0
            return -1
        if self.mode != "collect" or self.back_cd > 0 or self.rolling or gs < 2.0 or self.steps % 15:
            return 0
        rings = [r for r in self.near("ring", x - 100, 75) if r.alive and abs(r.y - (self.y - 16)) < 24 and x - 175 < r.x < x - 25]
        if len(rings) < 3:
            return 0
        target = min(r.x for r in rings) - 8
        blocked = any(h[1] > target - 60 and h[0] < x + 30 for h in self.hazards[max(0, bisect_right(self.haz_x, target - 400)):
                                                                                bisect_right(self.haz_x, x + 30)])
        crowded = any(self.near(k, (target + x) / 2, (x - target) / 2 + 40) for k in ("bumper", "spring", "spikes", "monitor"))
        if blocked or crowded or any(f.alive and abs(f.x - x) < 200 for f in self.foes):
            return 0
        self.back, self.back_t = target, 0
        return -1

    def dodge_shot(self, x):
        for s in self.dyn:
            if s.k == "shot" and 0 < s.x - x < 80 and abs(s.y - (self.y - 16)) < 30 and (s.vx < 0 or s.x - x < 40):
                if self.landing_safe(self.sim(4, 0)[0]):
                    self.hold_n = 4
                    return True
        return False

    def spikes_hit(self, path):
        # Feet must stay clear of spike tips and of the top edge of a wall for the whole arc, not only at takeoff.
        if not path:
            return False
        ph, top = self.level.ph, self.level.L - 1
        lo, hi = path[0][0] - 12, path[-1][0] + 12
        for x0, x1, kind in self.hazards[bisect_left(self.haz_x, lo - 200):bisect_right(self.haz_x, hi)]:
            if kind == "pit":
                continue
            edge = ph[min(x1 + 2, top)] - 4 if kind == "wall" else None
            for px, py in path:
                if kind == "wall":
                    if x0 - 9 < px < x1 + 9 and py > edge:
                        return True
                elif x0 - 10 < px < x1 + 10 and py > ph[min(int(px), top)] - 22:
                    return True
        return False

    def plan_air(self):
        # Re-planned every few steps because a bounce off an enemy or a bumper changes the arc mid-air.
        for dirn in (1, 0, -1):
            for cut in (False, True):
                if cut and not (self.jumped and self.ys < JUMP_CUT):
                    continue
                remaining = 0 if cut else max(0, self.hold_n - self.air_n)
                lx, _, path = self.sim(remaining, 0, dirn)
                if self.landing_safe(lx) and not self.spikes_hit(path):
                    return dirn, cut
        return 1, False

    def try_attack(self, x, gs, rolling_attack):
        for fx, fvx, fy, fw, fh, f in self.foe_snapshot():
            if not -6 < fx - x < 130 or f.skip and f.k != "monitor":
                continue
            if f.k != "monitor":
                if rolling_attack and f.b == 1 and f.k != "buzz":
                    continue
                if f.k == "buzz" and (f.b != 2 or any(d.k == "shot" and -10 < d.x - x < 110 for d in self.dyn)):
                    continue
                if self.y - fy > 105:
                    continue
            for hold in (0, 4, 999):
                lx, hit, path = self.sim(hold, 0, 1, f)
                if hit and self.landing_safe(lx) and not self.spikes_hit(path):
                    self.hold_n = hold
                    return True
        return False

    def near(self, kind, x, r):
        xs = self.stat_x[kind]
        return self.stat[kind][bisect_left(xs, x - r):bisect_right(xs, x + r)]

    # ---- physics ------------------------------------------------------------------------------------
    def physics(self, dirn, jump_press, jump_held, down):
        if self.dead:
            self.ys = min(self.ys + GRAV, 16)
            self.y += self.ys
            self.dead_t += 1
            return
        if self.hurt:
            self.hurt_step()
        elif self.ground:
            self.ground_step(dirn, jump_press, down)
        else:
            self.air_step(dirn, jump_held)
        self.check_bounds()

    def ground_step(self, dirn, jump_press, down):
        lv = self.level
        ix = int(self.x)
        sn, cs = lv.sn[ix], lv.cs[ix]
        self.sn = sn
        gs = self.gs
        if jump_press:
            self.xs, self.ys = gs * cs - JUMP * sn, -gs * sn - JUMP * cs
            self.ground, self.jumped, self.rolling = False, True, False
            self.air_n = 0
            return
        self.skid = False
        if gs != 0 or abs(sn) > 0.1:
            if self.rolling:
                gs -= (ROLL_UP if gs * sn > 0 else ROLL_DOWN) * sn
            else:
                gs -= SLOPE * sn
        if self.rolling:
            if dirn and dirn * gs < 0:
                gs += dirn * ROLL_DEC
            gs -= math.copysign(min(abs(gs), ROLL_FRC), gs)
            if abs(gs) < 0.5:
                self.rolling = False
                gs = 0.0
        else:
            if dirn > 0:
                self.facing = 1
                if gs < 0:
                    gs += DEC
                    self.skid = abs(gs) > 1.5
                    if gs >= 0:
                        gs = 0.5
                elif gs < self.top:
                    gs = min(self.top, gs + self.acc)
            elif dirn < 0:
                self.facing = 1 if self.finishing else -1
                if gs > 0:
                    gs -= DEC
                    self.skid = gs > 1.5
                    if gs <= 0:
                        gs = -0.5
                elif gs > -self.top:
                    gs = max(-self.top, gs - self.acc)
            else:
                gs -= math.copysign(min(abs(gs), FRC), gs)
            if down and abs(gs) >= 0.5:
                self.rolling = True
        gs = max(-16.0, min(16.0, gs))
        self.gs = gs
        if self.skid and self.steps % 6 == 0:
            self.dyn.append(O("dust", self.x - self.facing * 6, self.y))
        dx = gs * cs
        nx = self.x + dx
        if nx < 10 or nx > lv.L - 10:
            nx = max(10.0, min(lv.L - 10.0, nx))
            self.gs = 0.0
        gy = lv.ph[int(nx)]
        if gy >= INF:
            self.xs, self.ys = gs * cs, -gs * sn
            self.ground, self.jumped = False, False
            self.x = nx
            return
        limit = min(abs(dx) + 4, 14)
        diff = gy - self.y
        if diff < -limit:
            self.gs = 0.0
        elif diff > limit:
            self.xs, self.ys = gs * cs, -gs * sn
            self.ground, self.jumped = False, False
            self.x = nx
        else:
            self.x, self.y = nx, float(gy)

    def air_step(self, dirn, jump_held):
        lv = self.level
        xs, ys = self.xs, self.ys
        if self.jumped and not jump_held and ys < JUMP_CUT:
            ys = JUMP_CUT
        if dirn > 0:
            self.facing = 1
            if xs < self.top:
                xs = min(xs + AIR_ACC * (self.acc / ACC), self.top)
        elif dirn < 0:
            self.facing = -1
            if xs > -self.top:
                xs = max(xs - AIR_ACC * (self.acc / ACC), -self.top)
        if -4 < ys < 0 and abs(xs) >= 0.125:
            xs -= int(xs / 0.125) / 256
        self.move_air(xs, ys, GRAV)

    def move_air(self, xs, ys, grav):
        lv = self.level
        nx, ny = self.x + xs, self.y + ys
        if xs:
            px = int(nx + (7 if xs > 0 else -7))
            if 0 <= px < lv.L and lv.ph[px] < INF and lv.ph[px] < ny - 14:
                nx, xs = self.x, 0.0
        nx = max(10.0, min(lv.L - 10.0, nx))
        vy = ys
        self.xs, self.ys = xs, min(ys + grav, 16.0)
        self.x, self.y = nx, ny
        if vy >= 0:
            gy = lv.ph[int(nx)]
            if gy < INF and ny >= gy and ny - gy <= 20 + vy:
                self.land(gy, vy)

    def land(self, gy, vy):
        lv = self.level
        ix = int(self.x)
        sn, cs = lv.sn[ix], lv.cs[ix]
        self.y = float(gy)
        self.ground = True
        self.gs = self.xs if abs(sn) < 0.2 else self.xs * cs - vy * sn
        self.jumped = self.spring_air = False
        self.rolling = False
        self.chain = 0
        self.hold_n = 0
        if self.hurt:
            self.hurt = False
            self.gs = 0.0
            self.inv = 120

    def hurt_step(self):
        self.move_air(self.xs, self.ys, HURT_GRAV)

    def check_bounds(self):
        lv = self.level
        if self.y > YMAX + 112:
            self.die()
        elif self.zone == "mz" and self.y >= LAVA_Y - 4 and lv.ph[int(self.x)] >= INF:
            self.die()

    def die(self):
        if self.dead:
            return
        self.dead = True
        self.hurt = False
        self.ys = -7.0
        self.xs = 0.0
        self.dead_t = 0

    def take_hit(self, from_x):
        if self.inv > 0 or self.hurt or self.dead or self.finishing or self.invinc_t > 0:
            return
        if self.shield:
            self.shield = False
        elif self.rings > 0:
            self.scatter_rings()
            self.rings = 0
        else:
            self.die()
            return
        self.hurt, self.ground, self.jumped, self.rolling, self.spring_air = True, False, False, False, False
        self.xs = 2.0 if self.x >= from_x else -2.0
        self.ys = -4.0
        self.gs = 0.0

    def scatter_rings(self):
        n = min(self.rings, 20)
        for i in range(n):
            ang = math.radians(101.25 + 22.5 * (i // 2))
            sp = 4.0 if i < 16 else 2.0
            sgn = 1 if i % 2 else -1
            o = O("fring", self.x, self.y - 20, sgn * sp * math.cos(ang), -sp * math.sin(ang))
            o.t = 0
            self.dyn.append(o)

    # ---- objects --------------------------------------------------------------------------------------
    def add_score(self, n):
        self.score += n

    def collect_ring(self, n=1):
        before = self.rings // 100
        self.rings += n
        self.score += 10 * n
        if self.rings // 100 > before:
            self.lives += 1

    def kill_foe(self, f):
        f.alive = False
        self.add_score(CHAIN_POINTS[min(self.chain, 3)])
        self.chain += 1
        self.dyn.append(O("boom", f.x, f.y - 10 if f.k != "buzz" else f.y))
        animal = "bird" if (self.act_index + self.tick) % 3 else "rabbit"
        a = O("animal", f.x, f.y - 6, 1.0 if self.rng.random() < 0.5 else -1.0, -2.2, a=animal)
        self.dyn.append(a)

    def bounce_on(self, cy):
        if self.ground:
            return
        if self.ys > 0 and self.y - 16 < cy:
            self.ys = -self.ys
        else:
            self.ys += 1 if self.ys < 0 else -1

    def interact(self):
        x, y = self.x, self.y
        ball = self.jumped or self.rolling
        top = y - (24 if ball else 34)
        cy = y - (12 if ball else 17)
        for r in self.near("ring", x, 14):
            if r.alive and abs(r.x - x) < 14 and top - 4 < r.y < y + 6:
                r.alive = False
                self.collect_ring()
                self.dyn.append(O("spark", r.x, r.y))
        for o in self.near("monitor", x, 30):
            if o.b == 0 and abs(o.x - x) < 22 and y > o.y - 30 and top < o.y:
                if ball:
                    o.b = 1
                    self.bounce_on(o.y - 14)
                    self.dyn.append(O("boom", o.x, o.y - 14))
                    self.dyn.append(O("icon", o.x, o.y - 18, a=o.a))
                    self.add_score(10)
                    if o.a == "ring":
                        self.collect_ring(10)
                    elif o.a == "shield":
                        self.shield = True
                    elif o.a == "shoes":
                        self.shoes_t, self.top, self.acc = 1200, 12.0, 2 * ACC
                    elif o.a == "invinc":
                        self.invinc_t = 1200
                    else:
                        self.lives += 1
                elif self.ground:
                    self.gs = 0.0
                    self.x = o.x - 20 if x < o.x else o.x + 20
        for o in self.near("spring", x, 24):
            if abs(o.x - x) < 14 and y > o.y - 20 and top < o.y and (self.ys >= 0 or self.ground) and not self.hurt:
                o.t = 10
                self.ys = -(8.0 if o.a == "red" else 6.5)
                self.ground, self.jumped, self.spring_air, self.rolling = False, False, True, False
                self.y = o.y - 16
        for o in self.near("spikes", x, 80):
            if o.x - 8 < x < o.x + 32 * o.a + 8 and y > o.y - 15 and top < o.y:
                self.take_hit(o.x + 16 * o.a)
        for o in self.near("bumper", x, 40):
            dx, dy = x - o.x, cy - o.y
            d = math.hypot(dx, dy)
            if d < 26 and o.t == 0 and not self.hurt:
                o.t = 8
                ang = math.atan2(dy, dx)
                vx, vy = 7 * math.cos(ang), 7 * math.sin(ang)
                self.xs, self.ys = max(vx, 2.0), min(vy, -3.0)
                self.ground, self.jumped, self.rolling = False, True, False
                self.hold_n = 0
                self.add_score(10)
        for o in self.stat["sign"]:
            if self.sign_t < 0 and x >= o.x:
                self.sign_t = 0
                self.finishing = True
        for f in self.foes:
            if not f.alive:
                continue
            bx, by, bw, bh = self.foe_box(f)
            if abs(x - bx) < bw + 7 and abs(cy - by) < bh + (12 if ball else 17):
                if ball or self.invinc_t > 0:
                    self.kill_foe(f)
                    self.bounce_on(by)
                else:
                    self.take_hit(bx)
        for s in self.dyn:
            if s.k == "shot" and abs(x - s.x) < 7 and abs(cy - s.y) < 13:
                s.alive = False
                self.take_hit(s.x)
            elif s.k == "fring" and s.t > 64 and abs(x - s.x) < 14 and abs(cy - s.y) < 22 and not self.hurt:
                s.alive = False
                self.collect_ring()
                self.dyn.append(O("spark", s.x, s.y))

    def update_foes(self):
        lv = self.level
        px = self.x
        while self.pend_i < len(self.pending) and self.pending[self.pend_i].x < self.cam_x + VW + 120:
            f = self.pending[self.pend_i]
            self.pend_i += 1
            if f.x > self.cam_x - 60:
                f.skip = self.rng.random() < 0.04
                f.b = 1 if f.k in ("moto", "crab") and self.rng.random() < 0.5 else 0
                self.foes.append(f)
        for f in self.foes:
            if not f.alive:
                continue
            f.t += 1
            if f.k == "moto":
                if self.zone == "ghz" and f.t % 20 == 0:
                    self.dyn.append(O("puff", f.x - (14 if f.vx > 0 else -14), f.y - 8))
                f.x += f.vx
                ix = int(f.x)
                if abs(f.x - f.a) > 60 or lv.ph[min(max(ix + int(f.vx * 12), 0), lv.L - 1)] >= INF:
                    f.vx = -f.vx
                f.y = lv.ph[min(max(int(f.x), 0), lv.L - 1)]
            elif f.k == "chopper":
                if f.vy == 0 and f.t % 110 == 0:
                    f.vy = -7.5
                if f.vy != 0:
                    f.vy += GRAV
                    f.y += f.vy
                    if f.y >= f.a:
                        f.y, f.vy = f.a, 0.0
            elif f.k == "crab":
                if f.t % 150 < 100:
                    f.x += f.vx
                if abs(f.x - f.a) > 40:
                    f.vx = -f.vx
                    f.x += f.vx * 2
                if f.t % 180 == 90 and abs(f.x - px) < 170:
                    for sgn in (-1, 1):
                        self.dyn.append(O("shot", f.x + sgn * 12, f.y - 24, sgn * 1.1, -2.6, b=0.1))
            elif f.k == "buzz":
                if f.b == 0 and f.x - px < 230:
                    f.b = 1
                if f.b >= 1:
                    f.x -= 1.0
                    f.y = f.a + 3 * math.sin(f.t / 9)
                    if f.b == 1 and 40 < f.x - px < 120:
                        f.b = 2
                        self.dyn.append(O("shot", f.x - 14, f.y + 8, -1.1, 1.3))
        self.foes = [f for f in self.foes if f.alive and f.x > self.cam_x - 160]

    def update_dyn(self):
        lv = self.level
        for o in self.dyn:
            o.t += 1
            k = o.k
            if k == "shot":
                o.x += o.vx
                o.y += o.vy
                o.vy += o.b
                ix = min(max(int(o.x), 0), lv.L - 1)
                if o.t > 200 or o.y >= lv.ph[ix]:
                    o.alive = False
            elif k == "fring":
                o.vy += 0.09375
                o.x += o.vx
                o.y += o.vy
                ix = min(max(int(o.x), 0), lv.L - 1)
                if o.vy > 0 and o.y >= lv.ph[ix] - 6:
                    o.y = lv.ph[ix] - 6
                    o.vy *= -0.75
                if o.t > 280:
                    o.alive = False
            elif k == "animal":
                ix = min(max(int(o.x), 0), lv.L - 1)
                if o.a == "bird":
                    o.x += o.vx * 1.2
                    o.y += -0.9 + 0.4 * math.sin(o.t / 5)
                else:
                    o.x += o.vx
                    o.vy += 0.1875
                    o.y += o.vy
                    if o.y >= lv.ph[ix] and o.vy > 0:
                        o.y = lv.ph[ix]
                        o.vy = -3.0
                if o.t > 240:
                    o.alive = False
            elif k == "boom" and o.t > 30:
                o.alive = False
            elif k == "spark" and o.t > 24:
                o.alive = False
            elif k == "icon":
                o.y -= 0.7 if o.t < 24 else 0
                if o.t > 50:
                    o.alive = False
            elif k == "puff" and o.t > 24:
                o.alive = False
            elif k == "dust" and o.t > 18:
                o.alive = False
        self.dyn = [o for o in self.dyn if o.alive and abs(o.x - self.cam_x - 160) < 700]
        for k in ("spring", "bumper"):
            for o in self.near(k, self.x, 60):
                if o.t > 0:
                    o.t -= 1

    def update_camera(self):
        lv = self.level
        look = max(-1.0, min(1.0, self.gs / 6)) * 34 if self.ground else 0
        target = self.x - 160 + look
        dx = target - self.cam_x
        self.cam_x += max(-14.0, min(14.0, dx * 0.1))
        self.cam_x = max(0.0, min(lv.L - VW, self.cam_x))
        rel = self.y - self.cam_y
        if rel < 70:
            self.cam_y = self.y - 70
        elif rel > 196:
            self.cam_y = self.y - 196
        elif self.ground:
            self.cam_y += max(-2.5, min(2.5, (self.y - FEET_Y - self.cam_y) * 0.06))
        self.cam_y = max(YMIN - 176.0, min(YMAX - 140.0, self.cam_y))

    # ---- one 60 Hz step ---------------------------------------------------------------------------------
    def sim_step(self):
        self.steps += 1
        if self.state == "play" and not self.dead:
            if self.sign_t < 0:
                self.t_act += 1
        if self.sign_t >= 0:
            self.sign_t += 1
        dirn, jp, jh, down = self.bot()
        self.physics(dirn, jp, jh, down)
        if not self.dead:
            self.interact()
        self.update_foes()
        self.update_dyn()
        if self.inv > 0 and not self.hurt:
            self.inv -= 1
        if self.shoes_t > 0:
            self.shoes_t -= 1
            if self.shoes_t == 0:
                self.top, self.acc = TOP, ACC
        if self.invinc_t > 0:
            self.invinc_t -= 1
        self.idle_n = self.idle_n + 1 if self.ground and abs(self.gs) < 0.1 and not self.hurt else 0
        self.update_camera()
        if self.x > self.best_x + 2:
            self.best_x, self.stall = self.x, 0
        elif not self.finishing and self.back is None:
            self.stall += 1
        if self.stall > 420:
            self.unstick()

    def unstick(self):
        # A bot that cannot make progress is moved forward onto flat ground rather than being left to deadlock.
        lv = self.level
        x = int(self.x) + 48
        while x < lv.L - 40 and not (lv.ph[x] < INF and lv.ph[x - 20] < INF and lv.ph[x + 20] < INF):
            x += 8
        self.x, self.y = float(x), float(lv.ph[x])
        self.xs = self.ys = 0.0
        self.gs = 3.0
        self.ground, self.rolling, self.jumped, self.hurt = True, False, False, False
        self.stall = 0
        self.best_x = self.x
        self.back = None

    # ---- rendering ---------------------------------------------------------------------------------------
    def sonic_sprite(self):
        # Animation speed follows ground speed as in the original: the faster, the shorter each frame.
        gs = abs(self.gs)
        if self.dead or self.hurt:
            pose, i = "hurt", 0
        elif not self.ground:
            if self.spring_air and self.ys < 0:
                pose, i = "spring", 0
            elif self.spring_air:
                pose, i = "walk", 0
            else:
                pose = "ball"
                self.anim += 0.5
                i = int(self.anim) % 4
        elif self.rolling:
            pose = "ball"
            self.anim += 2 / max(1.5, 5 - gs)
            i = int(self.anim) % 4
        elif self.skid:
            pose = "skid"
            self.anim += 0.2
            i = int(self.anim) % 2
        elif gs < 0.1:
            if self.finishing and self.idle_n < 90:
                pose = "wave"
                self.anim += 0.12
                i = int(self.anim) % 3
            elif self.idle_n < 90:
                pose, i = "idle", 0
            else:
                n = self.idle_n - 90
                pose, i = "wait", (0 if n < 60 else 1 + (n // 14) % 2)
        elif gs < 5.8:
            self.anim += 2 / max(2.5, 9 - gs)
            pose, i = ("walk", int(self.anim) % 6) if gs < 3.2 else ("run", int(self.anim) % 4)
        else:
            pose = "blur"
            self.anim += 0.8
            i = int(self.anim) % 3
        return D["sonic" if self.facing > 0 else "sonic_l"][pose][i]

    def build_bg(self, camx, camy):
        spec = self.spec
        bgy = max(0, min(24, int((camy - 40) * 0.1)))
        t = self.tick
        rows = []
        fidx = (t // 6) % 3
        for vy in range(VH):
            r = vy + bgy
            fr, P, f, wave = spec[r]
            off = int(camx * f) % P if f else 0
            if wave:
                off = (off + WAVE[(r * 3 + t // 2) & 63]) % P
            base = fr[0] if len(fr) == 1 else fr[fidx]
            row = bytearray(BLACKROW)
            row[LEFT:LEFT + VW * SB] = base[off * SB:off * SB + VW * SB]
            rows.append(row)
        return rows

    def build_terrain(self, rows, camx, camy):
        lv = self.level
        x1 = camx + VW
        togs, init, fgc = lv.togs, lv.init, lv.fgc
        rmin = lv.rmin
        for vy in range(VH):
            wy = camy + vy
            if wy < rmin or wy >= WH:
                continue
            tg = togs[wy]
            j = bisect_right(tg, camx)
            st = init[wy] ^ (j & 1)
            row, fg, pos, n = rows[vy], fgc[wy], camx, len(tg)
            while pos < x1:
                nxt = tg[j] if j < n else x1
                if nxt > x1:
                    nxt = x1
                if st:
                    row[LEFT + (pos - camx) * SB:LEFT + (nxt - camx) * SB] = fg[pos * SB:nxt * SB]
                pos, st, j = nxt, not st, j + 1

    def draw_world(self, rows, camx, camy):
        lv = self.level
        zone = self.zone
        dec = D["decor"][zone]
        t = self.tick
        for o in self.near_range("decor", camx - 60, camx + VW + 60):
            fr = dec[o.k]
            spr = fr[((t // 12) + o.a) % len(fr)]
            draw(rows, spr, int(o.x - camx) - spr[0] // 2, int(o.y - camy) - spr[1] + 1)
        for o in self.near_range("spikes", camx - 100, camx + VW + 10):
            for i in range(o.a):
                draw(rows, D["spikes"], int(o.x - camx) + 32 * i, int(o.y - camy) - 16)
        for o in self.near_range("spring", camx - 20, camx + VW + 20):
            fr = D["spring_red" if o.a == "red" else "spring_yel"]
            draw(rows, fr[1 if o.t > 0 else 0], int(o.x - camx) - 14, int(o.y - camy) - 16)
        for o in self.near_range("monitor", camx - 20, camx + VW + 20):
            if o.b:
                draw(rows, D["monitor"]["broken"], int(o.x - camx) - 16, int(o.y - camy) - 32)
            else:
                draw(rows, D["monitor"][o.a][(t // 3) % 2], int(o.x - camx) - 16, int(o.y - camy) - 32)
        for o in self.near_range("bumper", camx - 24, camx + VW + 24):
            draw(rows, D["bumper"][1 if o.t > 0 else 0], int(o.x - camx) - 20, int(o.y - camy) - 20)
        for o in self.near_range("sign", camx - 40, camx + VW + 40):
            if self.sign_t < 0:
                fi = 0
            elif self.sign_t < 150:
                fi = (self.sign_t // 6) % 4
            else:
                fi = 4
            draw(rows, D["sign"][fi], int(o.x - camx) - 16, int(o.y - camy) - 48)
        rf = D["ring"][(t // 4) % 4]
        for o in self.near_range("ring", camx - 10, camx + VW + 10):
            if o.alive:
                draw(rows, rf, int(o.x - camx) - 8, int(o.y - camy) - 8)
        for f in self.foes:
            if not f.alive:
                continue
            sx, sy = int(f.x - camx), int(f.y - camy)
            if f.k == "moto":
                if zone == "mz":
                    draw(rows, D["cater_r" if f.vx < 0 else "cater"][(t // 8) % 2], sx - 20, sy - 22)
                elif zone == "syz":
                    draw(rows, D["roller" if f.vx < 0 else "roller_r"][(t // 3) % 2], sx - 14, sy - 24)
                else:
                    draw(rows, D["moto" if f.vx < 0 else "moto_r"][(t // 4) % 2], sx - 16, sy - 24)
            elif f.k == "chopper":
                draw(rows, D["chopper"][(t // 6) % 2], sx - 9, sy - 13)
            elif f.k == "crab":
                draw(rows, D["crab"][(t // 10) % 2], sx - 18, sy - 26)
            else:
                draw(rows, D["buzz"][(t // 2) % 2], sx - 20, sy - 13)
        for o in self.dyn:
            sx, sy = int(o.x - camx), int(o.y - camy)
            k = o.k
            if k == "shot":
                draw(rows, D["shot"][(t // 3) % 2], sx - 4, sy - 4)
            elif k == "fring":
                if o.t < 200 or t % 2:
                    draw(rows, rf, sx - 8, sy - 8)
            elif k == "boom":
                draw(rows, D["boom"][min(4, o.t // 6)], sx - 20, sy - 20)
            elif k == "spark":
                draw(rows, D["sparkle"][min(4, o.t // 5)], sx - 8, sy - 8)
            elif k == "animal":
                draw(rows, D["animal"][o.a][(o.t // 6) % 2], sx - 6, sy - 12 if o.a == "bird" else sy - 14)
            elif k == "icon":
                draw(rows, D["monitor"]["icons"][o.a], sx - 7, sy - 7)
            elif k == "dust":
                draw(rows, D["dust"][min(3, o.t // 5)], sx - 7, sy - 12)
            elif k == "puff":
                draw(rows, D["puff"][min(2, o.t // 8)], sx - 5, sy - 5)
        if not (self.inv > 0 and not self.hurt and self.tick % 2):
            spr = self.sonic_sprite()
            sx, sy = int(self.x - camx), int(self.y - camy)
            draw(rows, spr, sx - 17, sy - 38)
            if self.shield and not self.dead:
                draw(rows, D["shield"][t % 2], sx - 22, sy - 42)
            if self.invinc_t > 0:
                for k in range(3):
                    a = t * 0.35 + k * 2.1
                    draw(rows, D["sparkle"][(t // 3 + k) % 5], sx + int(14 * math.cos(a)) - 8, sy - 20 + int(16 * math.sin(a)) - 8)

    def near_range(self, kind, lo, hi):
        xs = self.stat_x[kind]
        return self.stat[kind][bisect_left(xs, lo):bisect_right(xs, hi)]

    def build_hud(self, rows):
        secs = min(self.t_act // 60, 5999)
        blink = self.rings == 0 and (self.tick // 8) % 2 == 0
        put_text(rows, "SCORE", 16, 8, "S", "yellow")
        put_text(rows, "%d" % self.score, 120 - text_width("%d" % self.score, "S"), 8, "S", "white")
        put_text(rows, "TIME", 16, 24, "S", "yellow")
        put_text(rows, "%d:%02d" % (secs // 60, secs % 60), 64, 24, "S", "white")
        put_text(rows, "RINGS", 16, 40, "S", "red" if blink else "yellow")
        put_text(rows, "%d" % self.rings, 96 - text_width("%d" % self.rings, "S"), 40, "S", "white")
        draw(rows, D["life"], 10, 190)
        put_text(rows, "SONIC", 30, 190, "S", "yellow")
        put_text(rows, "X %d" % self.lives, 34, 201, "S", "white")

    def flush(self, rows):
        prev = self.prev
        for vy in range(VH):
            r = rows[vy]
            if r != prev[vy]:
                o = vy * S5
                fb[o:o + S5] = r * PX
                prev[vy] = r

    def render_play(self):
        camx, camy = int(self.cam_x), int(self.cam_y)
        rows = self.build_bg(camx, camy)
        self.build_terrain(rows, camx, camy)
        self.draw_world(rows, camx, camy)
        self.build_hud(rows)
        self.flush(rows)

    def black_rows(self):
        return [bytearray(BLACKROW) for _ in range(VH)]

    def slab(self, rows, x, y, w, h, slant, col):
        # A parallelogram leaning right by `slant` px, as used by the original title cards.
        for r in range(h):
            fill_span(rows, x + int(slant * (1 - r / h)), y + r, w, 1, col)

    def disc(self, rows, cx, cy, rad, col):
        for r in range(-rad, rad + 1):
            hw = int(math.sqrt(rad * rad - r * r))
            fill_span(rows, cx - hw, cy + r, 2 * hw + 1, 1, col)

    def render_card(self, t):
        zi, act = divmod(self.act_index, 3)
        name = ZONES[zi][1]
        rows = self.black_rows()
        if t < 16:
            e = 1 - t / 16
        elif t > 74:
            e = -(t - 74) / 16
        else:
            e = 0.0
        off = int(e * abs(e) * 380)
        edge = ZONES[zi][2]
        self.slab(rows, 6 + off, 20, 120, 12, 16, ck(224, 224, 0))
        self.slab(rows, 30 + off, 34, 170, 5, 16, ck(224, 96, 0))
        self.slab(rows, 20 + off, 62, 276, 62, 20, ck(224, 224, 224))
        self.slab(rows, 24 + off, 65, 268, 56, 20, ck(*edge))
        self.slab(rows, 24 + off, 65, 268, 6, 20, ck(96, 128, 224))
        put_text(rows, name, 160 - text_width(name, "L") // 2 + off, 70, "L", "white")
        put_text(rows, "ZONE", 130 + off, 144, "L", "yellow")
        self.disc(rows, 60 + off, 158, 34, ck(224, 224, 224))
        self.disc(rows, 60 + off, 158, 31, ck(224, 0, 0))
        self.disc(rows, 60 + off, 158, 24, ck(224, 224, 0))
        put_text(rows, "ACT", 60 - text_width("ACT", "M") // 2 + off, 138, "M", "white")
        num = "%d" % (act + 1)
        put_text(rows, num, 60 - text_width(num, "L") // 2 + off, 152, "L", "white")
        draw(rows, D["sonic"]["wave"][(t // 6) % 3], 240 + off, 150)
        self.flush(rows)

    def render_results(self, t):
        zi, act = divmod(self.act_index, 3)
        rows = self.black_rows()
        put_text(rows, "SONIC HAS", 160 - text_width("SONIC HAS", "L") // 2, 22, "L", "white")
        put_text(rows, "PASSED", 130 - text_width("PASSED", "L") // 2, 54, "L", "white")
        self.disc(rows, 266, 82, 28, ck(224, 224, 224))
        self.disc(rows, 266, 82, 25, ck(224, 0, 0))
        put_text(rows, "ACT", 266 - text_width("ACT", "M") // 2, 62, "M", "yellow")
        put_text(rows, "%d" % (act + 1), 266 - text_width("%d" % (act + 1), "L") // 2, 76, "L", "white")
        for i, (lab, val) in enumerate((("SCORE", self.score), ("TIME BONUS", self.time_bonus_left),
                                        ("RING BONUS", self.ring_bonus_left))):
            y = 122 + i * 22
            put_text(rows, lab, 56, y, "S", "yellow")
            txt = "%d" % val
            put_text(rows, txt, 264 - text_width(txt, "S"), y, "S", "white")
        self.flush(rows)

    # ---- state machine -----------------------------------------------------------------------------------
    def time_bonus(self, secs):
        for lim, v in ((30, 50000), (45, 10000), (60, 5000), (90, 4000), (120, 3000), (180, 2000), (240, 1000), (300, 500)):
            if secs < lim:
                return v
        return 0

    def step(self):
        self.tick += 1
        if self.state == "over":
            return self.end.tick()
        if self.tick >= CAP_TICKS - 90 and self.state != "results":
            self.finish("TIME UP")
            return False
        st = self.state
        self.state_t += 1
        if st == "card":
            if self.state_t == 1:
                self.load_level()
                self.prev = [None] * VH
            elif self.level.stages is not None:
                if next(self.level.stages, True) is True:
                    self.level.stages = None
                    self.finish_load()
            self.render_card(self.state_t)
            if self.state_t >= 90:
                self.set_state("play")
        elif st == "play":
            for _ in range(2):
                self.sim_step()
            self.render_play()
            if self.dead and self.dead_t > 150:
                self.lives -= 1
                if self.lives <= 0:
                    self.finish("GAME OVER")
                    return False
                self.checkpoint = self.x > self.level.cp_x
                self.spawn_objects()
                self.reset_player(40)
                self.set_state("play")
            elif self.finishing and self.ground and (self.idle_n > 320 or self.sign_t > 900):
                self.begin_results()
        elif st == "results":
            self.results_tick()
        return False

    def set_state(self, st):
        self.state, self.state_t = st, 0
        self.prev = [None] * VH

    def begin_results(self):
        secs = self.t_act // 60
        self.time_bonus_left = self.time_bonus(secs)
        self.ring_bonus_left = self.rings * 100
        self.set_state("results")

    def results_tick(self):
        t = self.state_t
        if t > 45:
            for attr in ("time_bonus_left", "ring_bonus_left"):
                v = getattr(self, attr)
                if v > 0:
                    take = min(v, 1000)
                    setattr(self, attr, v - take)
                    self.score += take
        self.render_results(t)
        if t > 150 and self.time_bonus_left == 0 and self.ring_bonus_left == 0:
            self.act_index += 1
            if self.act_index >= 9:
                clear()
                self.finish("COURSE CLEAR")
            else:
                self.set_state("card")

    def finish(self, title):
        self.state = "over"
        self.end = EndScreen()
        self.end.start(self.score, title)


def make():
    return Game().step
