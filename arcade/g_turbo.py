# Turbo Tunnel (Battletoads): a toad on a teal speeder races through a fleshy tunnel in pure side view. Five
# bike courses of rising speed, two lanes (far/near on the track band), jumps, ramps, chasms, floating walls,
# rat rockets and rat pods; a bot reads the course ahead and plays it.
# Scene = 480x270 virtual pixels (vpx, 4x4 screen px). Each tick the scene is rebuilt row by row from parallax
# strips (one slice per row, written to 4 scanlines at once) with sprites patched into the row bytes.
from fbcore import *
import math

B = load_bundle("g_turbo.bin")
GEO, SPR = B["geo"], B["spr"]
TOP, BOT, NV = GEO["top"], GEO["bot"], GEO["nv"]
LANE_Y = GEO["lane_y"]
TRACK_TOP, TRACK_BOT = GEO["track"]
NR = BOT - TOP
BAND_ROWS = []              # per scene row: index into the band factor list
FACTORS = []
for _i, (_n, _a, _b, _f) in enumerate(GEO["bands"]):
    FACTORS.append(_f)
    BAND_ROWS += [_i] * (_b - _a)
RB = NV * 8                 # bytes per scene row (480 vpx * 4 px * 2 bytes)

# --- rules -----------------------------------------------------------------------------------------
BX = 100                    # screen x of the bike sprite's left edge
HL, HR, CXO = 10, 56, 33    # hitbox left/right and centre, relative to BX
HULLW = HR - HL
BODY_H = 24
FGAP = 30                   # height of the floating wall's underside above the track
GRAV, V_HOP, V_HIGH, V_RAMP, V_PAD = 0.6, 5.4, 6.9, 10.0, 10.0
RAMP_RISE = 22
SW = 6                      # ticks the bike needs to change lane
SPEEDS = [4.4, 5.2, 6.0, 6.9, 8.0]          # vpx per tick, one entry per course
MARGINS = [5.0, 4.0, 3.4, 3.0, 2.6]         # spare ticks the course generator leaves between actions
COURSE_TICKS = 950
SPEED_CAP = 11.5
LIVES = 5
PIPS = 6
TARGET = 230000             # score at which the run ends (two laps of the stage, about five minutes)
LOOK = 46                   # bot lookahead in ticks: scales with speed because it is time, not distance
P_MISS = 0.0025             # chance that the bot misjudges one action (a crash makes a good show)
NOISE = True                # tests switch the bot's human noise off to prove every course is clearable
DIM = {"pillar": (14, 30), "pod": (20, 24), "low": (12, 16), "fwall": (12, 0), "ramp": (50, 0), "fpad": (44, 0),
       "chasm": (0, 0), "finish": (12, 0)}
LANEK = ("pillar", "pod")
CLEAR = {"low": 18.0, "chasm": 3.0}
ROCKET_X = 340              # screen x where a rocket lets go of its wall
POINTS = {"pillar": 1, "pod": 1, "low": 1, "fwall": 1, "ramp": 3, "chasm": 3}


class Ob:
    # u: per-object scratch for the bot (noise / decisions), flash: blinks as a warning, drop: held by a rocket
    __slots__ = ("k", "x", "w", "h", "lane", "u", "flash", "need_ramp", "hold", "rel", "fall", "done")

    def __init__(self, k, x, w, h, lane=None):
        self.k, self.x, self.w, self.h, self.lane = k, x, w, h, lane
        self.u = None
        self.flash = False
        self.need_ramp = False
        self.hold = False
        self.rel = 0.0
        self.fall = 0
        self.done = False


def window_roots(v0, c):
    # Ticks after launch at which the bike hull crosses height c: h(t) = (v0+g/2) t - g t^2 / 2 (semi-implicit Euler).
    b = v0 + GRAV / 2
    disc = b * b - 2 * GRAV * c
    if disc <= 0:
        return None
    s = math.sqrt(disc)
    return (b - s) / GRAV, (b + s) / GRAV


def lane_y(ly):
    return LANE_Y[0] + (LANE_Y[1] - LANE_Y[0]) * ly


class Sim:
    def __init__(self):
        self.rnd = random.Random()
        self.t = 0
        self.cam = 0.0
        self.speed = 0.0
        self.vb = 0.0
        self.course = 1
        self.loop = 0
        self.target = self.course_speed(1, 0)
        self.score = 0
        self.lives = LIVES
        self.next_extra = 100000
        self.health = PIPS
        self.health_t = 0
        self.ly = 1.0
        self.lane_t = 1
        self.h = 0.0
        self.vy = 0.0
        self.riding = False
        self.big_air = False
        self.crash_t = 0
        self.crash_pit = False
        self.inv = 0
        self.shake = 0.0
        self.flash = 0
        self.banner = 0
        self.banner_text = ("", "")
        self.finished = None
        self.parts = []
        self.bodies = []
        self.crashes = 0
        self.haz = []
        self.gx = 330.0
        self.last_jumpy = False
        self.gcourse, self.gloop = 1, 0
        self.gcourse_end = self.gx + COURSE_TICKS * self.course_speed(1, 0)
        self.generate()

    @staticmethod
    def course_speed(course, loop):
        return min(SPEED_CAP, SPEEDS[course - 1] * (1 + 0.10 * loop))

    # ---- course generator ------------------------------------------------------------------------
    def add(self, k, left, w=None, lane=None):
        dw, dh = DIM[k]
        o = Ob(k, left, dw if w is None else w, dh, lane)
        self.haz.append(o)
        return o

    def half(self, k, v):
        # Ticks from the middle of a hazard to the end of the action it demands.
        if k in LANEK:
            return (DIM[k][0] + HULLW) / (2 * v)
        if k == "fwall":
            return (DIM[k][0] + HULLW) / (2 * v) + 1.5
        return 12.5

    def chain(self, specs, x, v, mg):
        # Hazards spaced so that the action for one ends (landing / lane change) before the next one must begin.
        cx, prev, last = None, None, None
        for k, lane, w in specs:
            dw = DIM[k][0] if w is None else w
            if prev is None:
                cx = x + dw / 2.0
            else:
                gap = self.half(prev[0], v) + self.half(k, v) + mg
                if prev[0] in LANEK and k in LANEK:
                    gap += SW if prev[1] != lane else 0
                elif prev[0] in LANEK or k in LANEK:
                    gap += SW * 0.5
                cx += gap * v
            last = self.add(k, cx - dw / 2.0, w, lane)
            if k in LANEK or k == "low":
                last.flash = self.gcourse <= 2
            prev = (k, lane)
        return last.x + last.w

    def lanes_alternating(self, n, repeat, kinds=("pillar",)):
        lane = self.rnd.randrange(2)
        specs = []
        for i in range(n):
            if i and self.rnd.random() >= repeat:
                lane = 1 - lane
            specs.append((self.rnd.choice(kinds), lane, None))
        return specs

    def pat_zigzag(self, x, v, mg):
        c = self.gcourse
        n = {1: (4, 6), 2: (3, 5), 3: (3, 5), 4: (3, 5), 5: (6, 10)}[c]
        return self.chain(self.lanes_alternating(self.rnd.randint(*n), 0.2 if c == 1 else 0.0), x, v, mg)

    def pat_pods(self, x, v, mg):
        specs = self.lanes_alternating(self.rnd.randint(3, 5), 0.0, ("pod", "pod", "pillar"))
        return self.chain(specs, x, v, mg)

    def pat_floats(self, x, v, mg):
        return self.chain([("fwall", None, None)] * self.rnd.randint(1, 3), x, v, mg)

    def pat_lows(self, x, v, mg):
        return self.chain([("low", None, None)] * self.rnd.randint(1, 3), x, v, mg)

    def pat_mixed(self, x, v, mg):
        pool = [("low", None, None), ("fwall", None, None), ("pillar", 0, None), ("pillar", 1, None)]
        specs = [self.rnd.choice(pool) for _ in range(self.rnd.randint(3, 5))]
        return self.chain(specs, x, v, mg)

    def pat_chasm(self, x, v, mg):
        # Needs a plain jump: wider than a short gap but well inside what a full hop crosses.
        w = int(self.rnd.uniform(11, 15) * v)
        return self.chain([("chasm", None, w)], x, v, mg)

    def pat_short_gap(self, x, v, mg):
        # Short enough to ride over without a jump.
        w = self.rnd.randrange(20, 30)
        return self.add("chasm", x + 10, w).x + w

    def pat_ramp(self, x, v, mg):
        ramp = self.add("ramp", x + 10)
        xe = ramp.x + ramp.w
        w = int(23 * v + 22)
        gap = self.add("chasm", xe + 20, w)
        gap.need_ramp = True
        return max(gap.x + gap.w, xe - 16 + 35.7 * v) + 10

    def pat_pad(self, x, v, mg):
        pad = self.add("fpad", x + 10)
        w = int(23 * v + 16)
        gap = self.add("chasm", pad.x + 16, w)
        gap.need_ramp = True
        return max(gap.x + gap.w, pad.x - 22 + 35.1 * v) + 10

    def pat_rockets(self, x, v, mg):
        end = self.chain(self.lanes_alternating(self.rnd.randint(2, 4), 0.0), x, v, mg)
        for o in self.haz:
            if o.k == "pillar" and o.x >= x and not o.hold:
                o.hold = True
                o.rel = o.x - ROCKET_X
                o.fall = 110
                o.flash = False
        return end

    JUMPY_START = ("lows", "chasm", "mixed", "pad")
    PATTERNS = {
        1: (("zigzag", 1),),
        2: (("zigzag", 3), ("floats", 2), ("lows", 2), ("ramp", 3), ("short_gap", 1), ("mixed", 2)),
        3: (("zigzag", 2), ("floats", 1), ("lows", 1), ("ramp", 2), ("pad", 3), ("rockets", 3), ("mixed", 1)),
        4: (("zigzag", 2), ("pods", 3), ("chasm", 3), ("floats", 1), ("lows", 1), ("rockets", 1), ("mixed", 1)),
        5: (("zigzag", 7), ("chasm", 1), ("floats", 1)),
    }

    def generate(self):
        while self.gx < self.cam + NV + 500:
            if self.gx >= self.gcourse_end:
                self.place_finish()
                continue
            c = self.gcourse
            v = self.course_speed(c, self.gloop)
            mg = MARGINS[c - 1]
            names = self.PATTERNS[c]
            pick = self.rnd.uniform(0, sum(w for _, w in names))
            for n, w in names:
                pick -= w
                if pick <= 0:
                    break
            # a jump needs half its airtime on each side of its hazard, so rest ticks grow around jumps
            rest = self.rnd.uniform(14, 26) + (12.5 if self.last_jumpy else 0.0) + (12.5 if n in self.JUMPY_START else 0.0)
            end = getattr(self, "pat_" + n)(self.gx + rest * v, v, mg)
            last = self.haz[-1]
            self.last_jumpy = last.k == "low" or (last.k == "chasm" and last.w >= 34 and not last.need_ramp)
            self.gx = end

    def place_finish(self):
        o = self.add("finish", self.gx)
        o.h = 1 if self.gcourse == 5 else 0
        self.gcourse += 1
        if self.gcourse > 5:
            self.gcourse, self.gloop = 1, self.gloop + 1
        v = self.course_speed(self.gcourse, self.gloop)
        self.gx += 12 + 80 * v
        self.gcourse_end = self.gx + COURSE_TICKS * v

    # ---- bot ---------------------------------------------------------------------------------------
    def window(self, o, v):
        cx = self.cam + BX
        if o.k == "chasm":
            c = cx + CXO
            return (o.x + 6 - c) / v, (o.x + o.w - 6 - c) / v, CLEAR["chasm"]
        return (o.x - (cx + HR)) / v, (o.x + o.w - (cx + HL)) / v, CLEAR[o.k]

    def plan_jump(self, a, b, c, profiles):
        # Choose the smaller hop when it leaves enough timing slack, else the full jump.
        # Returns (profile, ticks until the ideal launch, slack in ticks).
        best = None
        for prof in profiles:
            roots = window_roots(prof, c)
            if roots is None:
                continue
            dlo, dhi = b - roots[1], a - roots[0]
            tol = (dhi - dlo) / 2
            best = (prof, (dlo + dhi) / 2, tol)
            if tol >= 2.0:
                break
        return best

    def noise(self, o, spread, miss):
        # Human timing noise, drawn once per hazard; a rare large error is a deliberate crash.
        if o.u is None:
            o.u = max(-1.0, min(1.4, self.rnd.gauss(0.3, spread))) if NOISE else 0.0
            if NOISE and self.rnd.random() < P_MISS:
                o.u = miss
        return o.u

    def bot(self):
        # Returns the jump velocity or None; may also start a lane change. The bot only uses what a player could
        # see: the hazards within LOOK ticks of travel, their positions and the current speed.
        if self.crash_t:
            return None
        v = max(self.speed, 1.0)
        cx = self.cam + BX
        walls, todo = [], []
        for o in self.haz:
            if o.x > cx + HR + LOOK * v:
                break
            if o.hold and o.rel > self.cam:
                continue
            a = (o.x - (cx + HR)) / v
            b = (o.x + o.w - (cx + HL)) / v
            if b < -1.0:
                continue
            if o.k in LANEK:
                walls.append((o, a, b))
            elif o.k == "low" or (o.k == "chasm" and o.w >= 34 and not o.need_ramp):
                if self.window(o, v)[1] > 0.2:
                    todo.append(o)
            elif o.k == "fpad" and not o.done:
                todo.append(o)
        if self.ly == self.lane_t:
            self.steer(walls)
        if self.riding or self.h > 0.01:
            return None
        return self.plan_action(todo, v)

    def steer(self, walls):
        cur = self.lane_t
        ahead = [w for w in walls if w[0].lane == cur and w[2] > 0.3]
        if not ahead:
            return
        o, a, b = ahead[0]
        u = self.noise(o, 0.5, -3.0)
        if a > 0.6 * SW + 1.0 + u:
            return
        for p, pa, pb in walls:
            if p.lane != cur and pa <= SW + 1 and pb >= 0.4 * SW - 1:
                return
        self.lane_t = 1 - cur

    def plan_action(self, todo, v):
        if not todo:
            return None
        o = todo[0]
        if o.k == "fpad":
            a = (o.x - (self.cam + BX + HR)) / v
            return V_HOP if a <= 4.5 + self.noise(o, 0.7, -3.0) else None
        a, b, c = self.window(o, v)
        for p in todo[1:]:
            if p.k != "low" or o.k != "low":
                break
            a2, b2, c2 = self.window(p, v)
            merged = window_roots(V_HIGH, c)
            if merged is None or (b2 - a) > (merged[1] - merged[0]) - 4.0:
                break
            b = b2
        plan = self.plan_jump(a, b, c, (V_HIGH,) if o.k == "chasm" else (V_HOP, V_HIGH))
        if plan is None:
            return None
        prof, dstar, tol = plan
        u = self.noise(o, 0.45, tol + 2.0 if self.rnd.random() < 0.5 else -(tol + 2.0))
        return prof if dstar <= 0.5 + u else None

    # ---- step --------------------------------------------------------------------------------------
    def spark(self, x, y, n, col, spread=3.0, up=3.0):
        for _ in range(n):
            self.parts.append([x, y, self.rnd.uniform(-spread, spread), -self.rnd.uniform(0, up), self.rnd.randint(8, 18), col])

    def crash(self, pit):
        self.crash_t = 1
        self.crashes += 1
        self.lives -= 1
        self.health = 0
        self.shake = 8.0
        gy = lane_y(self.ly)
        self.bodies = [
            dict(k="toad", x=BX + 34.0, y=self.h + 22, vx=5.0 + self.speed * 0.25, vy=8.5, a=0.0, gy=gy),
            dict(k="wreck", x=float(BX), y=self.h + 4, vx=2.0 + self.speed * 0.15, vy=5.0, a=0.0, gy=gy),
        ]
        self.crash_pit = pit
        self.spark(BX + 30, gy - self.h - 12, 26, (255, 214, 60), 6.0, 7.0)

    def respawn(self):
        if self.lives <= 0:
            self.finished = "GAME OVER"
            return
        self.crash_t = 0
        self.bodies = []
        self.h = self.vy = 0.0
        self.riding = self.big_air = False
        self.lane_t = self.rnd.randrange(2)
        self.ly = float(self.lane_t)
        self.vb = self.target * 0.5
        self.inv = 75
        self.health_t = self.t
        # clear the stretch in front of the bike so the respawn is not an instant second crash
        clear_to = self.cam + BX + 330
        self.haz = [o for o in self.haz if o.x > clear_to]

    def surface(self):
        wx = self.cam + BX + HR - 8
        for o in self.haz:
            if o.k == "ramp" and o.x <= wx <= o.x + o.w:
                return RAMP_RISE * (wx - o.x) / o.w
            if o.x > wx:
                break
        return 0.0

    def tick(self):
        self.t += 1
        if self.crash_t:
            self.vb *= 0.8
            self.crash_t += 1
            for b in self.bodies:
                b["x"] += b["vx"] - (self.speed if b["y"] <= 0.5 else 0)
                b["y"] += b["vy"]
                b["vy"] -= GRAV * 1.2
                b["a"] += 1
                if b["y"] < 0 and not self.crash_pit:
                    b["y"] = 0.0
                    b["vy"] = -b["vy"] * 0.45 if b["vy"] < -2 else 0.0
                    b["vx"] *= 0.7
                    if abs(b["vy"]) > 1.5:
                        self.spark(b["x"] + 10, b["gy"] - 2, 5, (190, 194, 208), 2.0, 2.0)
            if self.crash_t == 46:
                self.respawn()
        else:
            self.vb += max(-0.15, min(0.05, self.target - self.vb))
        self.speed = self.vb
        if self.finished:
            return
        if not self.crash_t:
            jump = self.bot()
            if jump is not None and self.h <= 0.01 and not self.riding:
                self.vy = jump
                self.h = 0.001
            step = 1.0 / SW
            self.ly = min(self.lane_t, self.ly + step) if self.lane_t > self.ly else max(self.lane_t, self.ly - step)
        self.cam += self.speed
        if not self.crash_t:
            self.physics()
            self.collide()
        if self.inv:
            self.inv -= 1
        if self.health < PIPS and not self.crash_t and (self.t - self.health_t) % 5 == 0:
            self.health += 1
        self.shake *= 0.82
        if self.flash:
            self.flash -= 1
        if self.banner:
            self.banner -= 1
        for o in self.haz:
            if o.hold and o.rel <= self.cam and o.fall > 0:
                o.fall = max(0, o.fall - 11)
        self.update_parts()
        self.generate()
        while self.haz and self.haz[0].x + self.haz[0].w < self.cam - 80:
            self.haz.pop(0)

    def physics(self):
        floor = self.surface()
        if self.riding and floor == 0:
            # rode off the end of the ramp: the launch keeps the ramp-top height
            self.riding = False
            self.vy = V_RAMP
            self.big_air = True
            self.shake = max(self.shake, 4.0)
        if self.h > floor + 0.01 or self.vy > 0:
            self.h += self.vy
            self.vy -= GRAV
            floor = self.surface()
            if self.h <= floor and self.vy <= 0:
                hard = self.vy < -4
                self.h, self.vy = floor, 0.0
                self.riding = floor > 0
                if hard:
                    self.spark(BX + 20, lane_y(self.ly) - 2, 7, (255, 214, 150), 3.0, 2.0)
                    self.shake = max(self.shake, 3.0 if self.big_air else 1.5)
                if not self.riding:
                    self.big_air = False
        else:
            self.h = floor
            self.riding = floor > 0

    def collide(self):
        cx = self.cam + BX
        lft, rgt = cx + HL, cx + HR
        top = self.h + BODY_H
        for o in self.haz:
            if o.x >= rgt:
                break
            if o.hold and (o.rel > self.cam or o.fall > 0):
                continue
            k = o.k
            if o.x + o.w <= lft:
                if not o.done and k in POINTS and not self.crash_t:
                    o.done = True
                    self.score += 100 * POINTS[k] * self.course
                    self.extra_life()
                continue
            if k == "finish":
                if cx + CXO > o.x + 6 and not o.done:
                    o.done = True
                    self.pass_finish(o)
                continue
            if self.inv:
                continue
            if k in LANEK:
                if abs(self.ly - o.lane) < 0.6 and self.h < o.h - 2:
                    return self.crash(False)
            elif k == "low":
                if self.h < o.h - 2:
                    return self.crash(False)
            elif k == "fwall":
                if top > FGAP:
                    return self.crash(False)
            elif k == "chasm":
                if o.w >= 34 and o.x + 6 < cx + CXO < o.x + o.w - 6 and self.h <= 2:
                    return self.crash(True)
            elif k == "fpad":
                if not o.done and 6 < self.h < 40:
                    o.done = True
                    self.vy = V_PAD
                    self.big_air = True
                    self.score += 500
                    self.shake = max(self.shake, 5.0)
                    self.spark(BX + 30, lane_y(self.ly) - self.h, 14, (255, 214, 60), 4.0, 4.0)

    def extra_life(self):
        if self.score >= self.next_extra:
            self.next_extra += 100000
            self.lives = min(LIVES, self.lives + 1)

    def pass_finish(self, o):
        final = o.h == 1
        self.score += 3000 * self.course + (10000 if final else 0)
        self.shake = 9.0
        self.flash = 3
        self.course += 1
        if self.course > 5:
            self.course, self.loop = 1, self.loop + 1
        self.target = self.course_speed(self.course, self.loop)
        self.banner = 90
        self.banner_text = ("STAGE CLEAR", "SPEED UP") if final else ("CHECKPOINT", "COURSE %d" % self.course)
        self.spark(BX + 30, lane_y(self.ly) - 20, 24, (232, 70, 110), 6.0, 6.0)
        self.spark(BX + 30, lane_y(self.ly) - 20, 16, (255, 214, 60), 6.0, 6.0)

    def update_parts(self):
        keep = []
        for p in self.parts:
            p[0] += p[2] - self.speed * 0.6
            p[1] += p[3]
            p[3] += 0.35
            p[4] -= 1
            if p[4] > 0 and p[1] < BOT:
                keep.append(p)
        self.parts = keep[-90:]
        if not self.crash_t and self.h <= 0.01 and self.t % 2 == 0:
            self.parts.append([BX + 4, lane_y(self.ly) - 1, -self.speed * 0.1, -self.rnd.uniform(0.4, 1.4), 7, (255, 176, 90)])


def make():
    sim = Sim()
    rows_static, pulse = B["rows"], B["pulse"]
    hearts = B["heart"]

    def vp(rgb):
        return rgb565(*rgb).to_bytes(2, "little") * 4
    pit_rows = [vp((int(70 * (1 - f)), 0, int(24 * (1 - f)))) for f in (i / (TRACK_BOT - TRACK_TOP) for i in range(TRACK_BOT - TRACK_TOP))]
    lip = vp((255, 214, 150))
    lip_d = vp((84, 0, 28))
    shade = vp((150, 36, 14))
    flash_row = [vp((255, 255, 255)) * NV, vp((255, 214, 220)) * NV]
    part_cache = {}
    bike_spr, flame_spr = SPR["bike"], SPR["flame"]
    state = dict(phase="play", score=-1, health=-1, lives=-1)
    clear()
    p2x = 1010

    def hud_static():
        for i in range(5):
            blit(hearts[1], p2x + i * 44, 20)
        draw_text("000000", p2x + 250, 8, "S", COLOR_WHITE)
        for i in range(PIPS):
            fill_rect(p2x + 250 + i * 24, 62, 20, 16, rgb565(90, 20, 40))
    hud_static()

    def hud():
        if sim.score != state["score"] and sim.t % 3 == 0:
            state["score"] = sim.score
            draw_text("%06d" % min(sim.score, 999999), 32, 8, "S", COLOR_WHITE)
        if sim.health != state["health"]:
            state["health"] = sim.health
            for i in range(PIPS):
                fill_rect(32 + i * 24, 62, 20, 16, rgb565(232, 40, 70) if i < sim.health else rgb565(90, 20, 40))
        if sim.lives != state["lives"]:
            state["lives"] = sim.lives
            fill_rect(220, 16, 44 * LIVES, 40, 0)
            for i in range(max(0, sim.lives)):
                blit(hearts[0], 220 + i * 44, 20)

    def draw_scene():
        cam = sim.cam
        patches = [[] for _ in range(NR)]

        def put(spr, x, y):
            for j, runs in enumerate(spr["rows"]):
                r = y + j - TOP
                if 0 <= r < NR:
                    pl = patches[r]
                    for xo, b in runs:
                        x0 = x + xo
                        n = len(b) >> 3
                        if x0 + n <= 0 or x0 >= NV:
                            continue
                        if x0 < 0:
                            b = b[-x0 * 8:]
                            x0 = 0
                        if x0 + (len(b) >> 3) > NV:
                            b = b[:(NV - x0) * 8]
                        pl.append((x0 * 8, b))

        def rect(x, y, w, h, col):
            for yy in range(y, y + h):
                r = yy - TOP
                if 0 <= r < NR:
                    x0, x1 = max(0, x), min(NV, x + w)
                    if x1 > x0:
                        patches[r].append((x0 * 8, col * (x1 - x0)))

        t = sim.t
        cur_y = int(round(lane_y(sim.ly)))
        draw = []            # (order key, sprite, x, y): painter's order by the ground row the thing stands on
        for o in sim.haz:
            sx = int(o.x - cam)
            if sx > NV + 10 or sx + o.w < -60:
                continue
            k = o.k
            if k == "chasm":
                if o.w < 34:
                    rect(sx, TRACK_TOP + 6, o.w, TRACK_BOT - TRACK_TOP - 6, shade)
                    continue
                for yy in range(TRACK_TOP + 1, TRACK_BOT):
                    rect(sx, yy, o.w, 1, pit_rows[yy - TRACK_TOP])
                rect(sx, TRACK_TOP + 1, o.w, 1, lip_d)
                rect(sx - 2, TRACK_TOP + 1, 2, TRACK_BOT - TRACK_TOP - 1, lip)
                rect(sx + o.w, TRACK_TOP + 1, 2, TRACK_BOT - TRACK_TOP - 1, lip)
                rect(sx - 3, TRACK_TOP + 1, 1, TRACK_BOT - TRACK_TOP - 1, lip_d)
                rect(sx + o.w + 2, TRACK_TOP + 1, 1, TRACK_BOT - TRACK_TOP - 1, lip_d)
            elif k == "finish":
                draw.append((-50, SPR["finish"], sx, TRACK_TOP))
            elif k == "ramp":
                s = SPR["ramp"]
                draw.append((-40, s, sx, LANE_Y[1] - (s["h"] - 1)))
            elif k == "low":
                draw.append((-30, SPR["low"][1 if o.flash and (t // 4) & 1 else 0], sx - 1, LANE_Y[0] - 18))
            elif k == "fpad":
                rect(sx + 2, (LANE_Y[0] + LANE_Y[1]) // 2 - 2, o.w - 4, 5, shade)
                draw.append((-20, SPR["fpad"][(t // 3) & 1], sx, LANE_Y[0] - 15))
            elif k == "fwall":
                rect(sx, (LANE_Y[0] + LANE_Y[1]) // 2 - 3, o.w, 8, shade)
                draw.append((2000, SPR["fwall"], sx - 1, LANE_Y[0] - FGAP - 12))
            elif k == "pillar":
                if o.hold and o.rel > cam:
                    continue
                gy = LANE_Y[o.lane]
                fl = o.flash and (t // 4) & 1
                draw.append((gy, SPR["pillar"][1 if fl else 0], sx - 1, gy - 38 - o.fall))
            elif k == "pod":
                gy = LANE_Y[o.lane]
                draw.append((gy, SPR["pod"][((t >> 3) + int(o.x)) & 1], sx - 2, gy - 27))
        for o in sim.haz:
            if o.hold:
                rx = int(ROCKET_X + 0.6 * (o.rel - cam))
                if -30 < rx < 500:
                    draw.append((3000, SPR["rocket"][(t >> 1) & 1], rx - 27, 62 + (int(o.x) * 7) % 14))
        # the bike and its rider
        if not sim.crash_t and (not sim.inv or (t // 3) % 2 == 0):
            moving = sim.ly != sim.lane_t
            fwall_near = any(o.k == "fwall" and -30 < o.x - (cam + BX + HR) < 70 for o in sim.haz) and sim.h < 1
            if sim.riding:
                pose = "up"
            elif sim.h > 0.01:
                pose = "up" if sim.vy > 1.5 else ("down" if sim.vy < -2.5 else "ride")
            elif fwall_near:
                pose = "duck"
            elif moving:
                pose = "lean_far" if sim.lane_t == 0 else "lean_near"
            else:
                pose = "ride"
            top_y = cur_y - int(sim.h) - 44
            draw.append((cur_y - 0.5, SPR["shadow"][44], BX + 6, cur_y - 4))
            fl = 0 if sim.speed < 5.5 else (1 if sim.speed < 8 else 2)
            draw.append((cur_y, flame_spr[fl][t & 1], BX - 36, top_y + 27 + (6 if pose == "up" else 0)))
            draw.append((cur_y + 0.1, bike_spr[pose][(t // 2) & 1], BX, top_y))
        for b in sim.bodies:
            by = int(b["gy"])
            if b["k"] == "toad":
                draw.append((by + 5, SPR["toad_spin"][int(b["a"] // 2) % 8], int(b["x"]) - 20, by - int(b["y"]) - 22))
            else:
                draw.append((by + 4, SPR["wreck_spin"][int(b["a"] // 3) % 8], int(b["x"]) - 10, by - int(b["y"]) - 30))
        if 0 < sim.crash_t < 10:
            draw.append((5000, SPR["burst"][sim.crash_t % 3], BX + 12, cur_y - 50))
        draw.sort(key=lambda e: e[0])
        for _, spr, x, y in draw:
            put(spr, x, y)
        for p in sim.parts:
            col = part_cache.get(p[5])
            if col is None:
                col = part_cache[p[5]] = vp(p[5])
            rect(int(p[0]), int(p[1]), 2, 2, col)

        # compose the frame: one slice per row, written to its 4 scanlines in a single assignment
        offs = [(int(cam * f) % NV) * 8 for f in FACTORS]
        frame = (t // 10) & 1
        shift = int(round(sim.shake * random.uniform(-1, 1))) if sim.shake > 0.4 else 0
        white = flash_row[0 if sim.flash >= 2 else 1] if sim.flash else None
        pr = pulse[frame]
        for r in range(NR):
            sr = r + shift
            sr = 0 if sr < 0 else (NR - 1 if sr >= NR else sr)
            if white is not None:
                row = white
            else:
                o = offs[BAND_ROWS[sr]]
                row = (pr[sr] if sr < len(pr) else rows_static[sr])[o:o + RB]
                pl = patches[sr]
                if pl:
                    row = bytearray(row)
                    for xo, b in pl:
                        row[xo:xo + len(b)] = b
            off = (TOP + r) * 4 * S
            fb[off:off + 4 * S] = row * 4
        if sim.banner and (sim.banner // 4) % 2 == 0:
            title, sub = sim.banner_text
            draw_text(title, (W - text_width(title, "L")) // 2, 330, "L", COLOR_YELLOW if sim.banner % 8 < 4 else COLOR_WHITE, bg=False)
            draw_text(sub, (W - text_width(sub, "S")) // 2, 430, "S", COLOR_CYAN, bg=False)

    end = EndScreen()

    def step():
        if state["phase"] == "end":
            return end.tick()
        sim.tick()
        draw_scene()
        hud()
        if sim.score >= TARGET and not sim.finished:
            sim.finished = "STAGE CLEAR"
        if sim.finished or sim.t >= CAP_TICKS - 160:
            state["phase"] = "end"
            end.start(min(sim.score, 999999), sim.finished or "TIME UP")
        return False

    step.sim = sim
    return step
