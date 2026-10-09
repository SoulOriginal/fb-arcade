# Excitebike-style dirt-bike racing played by a bot: four lanes, ramps, mud, turbo with engine temperature, CPU riders.
# 256x240 virtual screen drawn 4x (1024x960) in the middle of the 1920x1080 frame. The scenery is a long pre-built
# strip per virtual row; every tick the visible window of each changing row is sliced out, riders are pasted on top
# as opaque runs and the row is written to its four scanlines. Rows nothing touches are not rewritten.
from fbcore import *
import math

B = load_bundle("g_motocross.bin")
K = B["K"]
VW, VH, TRACK_TOP, HAY_Y, HUD_Y = K["VW"], K["VH"], K["TRACK_TOP"], K["HAY_Y"], K["HUD_Y"]
LANE_Y = K["LANE_CONTACT"]
CEN, WHEEL = K["CEN"], K["WHEEL_BASE"]
PROF = B["profiles"]
X0, Y0 = (W - VW * 4) // 2, (H - VH * 4) // 2
ROWB = VW * 8                       # bytes of one virtual row: 256 vpx * 4 px * 2 bytes
SLACK = 300                         # strip tail that repeats the start so the camera can cross the lap boundary
LINE_X = 60                         # start/finish line, vpx from the strip origin
LAPS = 3
GRAV = 0.25
VA, VB = 2.2, 3.5                   # top speeds of the slow gear and the turbo, vpx per tick
HOT, COOLED = 32.0, 9.0             # engine overheat limit and the temperature at which a stopped bike restarts
GO_TICK = 110                       # tick at which the start gate drops
POINTS = (10, 6, 4, 2, 1)
NAMES = ("RED", "BLUE", "PURPLE", "BROWN", "GREEN")
HAZARD = {1: 7.0, 2: 10.0, 3: 8.0, 4: 3.0}
BIKE = B["bikes"]
MISC = B["misc"]
RACES = 4


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class World:
    def __init__(self, ti):
        tr = B["tracks"][ti]
        self.ti, self.name, self.lap, self.deco = ti, tr["name"], tr["lap"], tr["deco"]
        self.best, self.wall_px = tr["best"], tr["wall_px"]
        n = self.lap + SLACK
        self.G = [[0.0] * (n + 2) for _ in range(4)]
        self.surf = [bytearray(n + 2) for _ in range(4)]
        self.air = [bytearray(n + 2) for _ in range(4)]
        self.strip = []
        for row in tr["base"]:
            reps = n // K["PERIOD"] + 2
            self.strip.append(bytearray((row * reps)[:n * 8]))
        codes = {"mud": 1, "grassS": 2, "grassL": 2, "dirt": 3, "bump": 4, "cool": 5}
        for kind, s, l0, l1 in tr["items"]:
            sp = B["obs"][(kind, l0, l1)]
            for base in (s, s + self.lap):
                if base + sp["w"] < n:
                    self.paste(sp, base, 0)
            for l in range(l0, l1 + 1):
                for base in (s, s + self.lap):
                    if kind in PROF:
                        pts = PROF[kind]
                        length = pts[-1][0] + 1
                        sh = int(round((TRACK_TOP + K["LANE_H"] * (l1 + 1) - 1 - LANE_Y[l]) * K["SHEAR"]))
                        for dx in range(length):
                            if base + sh + dx < n:
                                self.G[l][base + sh + dx] = self.profile(pts, dx)
                        if max(h for _, h in pts) >= 8:
                            for p in range(base + sh + length + 12, min(n, base + sh + length + 80)):
                                self.air[l][p] = 1
                    else:
                        for dx in range(B["flat_len"][kind]):
                            if base + dx < n:
                                self.surf[l][base + dx] = codes[kind]
        for base in (LINE_X, LINE_X + self.lap):
            self.paste(MISC["finish"], base, 0)
        # Rows whose strip is one repeated colour never scroll visibly; they are drawn once and only rebuilt
        # when a sprite sticks into them.
        self.dyn, self.static = [], {}
        for y in range(VH):
            row = self.strip[y]
            first = bytes(row[:8])
            if row == first * (len(row) // 8):
                self.static[y] = bytearray(first * VW)
            else:
                self.dyn.append(y)

    @staticmethod
    def profile(pts, x):
        for (x0, h0), (x1, h1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                return h0 + (h1 - h0) * (x - x0) / max(1, x1 - x0)
        return 0.0

    def paste(self, sp, x, y0):
        for j, row in enumerate(sp["rows"]):
            if row:
                buf = self.strip[y0 + j]
                for rx, b in row:
                    buf[(x + rx) * 8:(x + rx) * 8 + len(b)] = b

    def ground(self, lane, x):
        x %= self.lap
        i = int(x)
        f = x - i
        lane = clamp(lane, 0.0, 3.0)
        li = int(lane)
        lf = lane - li
        if li >= 3:
            li, lf = 2, 1.0
        a, b = self.G[li], self.G[li + 1]
        h0 = a[i] + (a[i + 1] - a[i]) * f
        h1 = b[i] + (b[i + 1] - b[i]) * f
        return h0 + (h1 - h0) * lf

    def surface(self, lane, x):
        return self.surf[clamp(int(lane + 0.5), 0, 3)][int(x) % self.lap]


class Rider:
    def __init__(self, ci, lane, s, kind, rnd):
        self.ci, self.kind = ci, kind
        self.lane, self.tl = float(lane), lane
        self.s, self.v, self.z, self.vz, self.vzg = float(s), 0.0, 0.0, 0.0, 0.0
        self.th = 0.0
        self.air, self.wheelie, self.wh_x, self.wh_t = False, False, -1.0, 0
        self.temp, self.cool = 8.0, False
        self.mode, self.mt = "ride", 0
        self.done, self.ft, self.laps_t = False, None, []
        self.dl = 0.0
        self.perr = 0.0
        self.greedy_p = 0.0007
        self.wh_skip = -1.0
        self.greedy = 0
        self.pace = 1.0
        self.sig, self.mistake, self.thr, self.wh_p, self.blind = 5.0, 0.03, 26.0, 0.97, 0.05
        self.pref = lane
        self.gas = "B"
        self.crashes = 0
        self.why = None
        self.rnd = rnd
        self.last_surf = 0
        # crash state: bike and thrown rider move separately
        self.bs = self.bz = self.bv = self.bvz = self.bth = self.bspin = 0.0
        self.rs = self.rz = self.rvx = self.rvz = self.rth = self.rspin = 0.0
        self.run_t = 0


class Race:
    def __init__(self, ti, game_rnd, idx):
        self.rnd = game_rnd
        self.W = World(ti)
        self.t = 0
        self.idx = idx
        self.phase = "gate"
        rnd = self.rnd
        lanes = [0, 1, 2, 3]
        rnd.shuffle(lanes)
        cols = [0, 1, 2, 3, 4]
        kinds = ["player", "normal", "pursuer", "normal", "pursuer"]
        starts = [(lanes[0], 26), (lanes[1], 26), (lanes[2], 26), (lanes[3], 26), (lanes[0], 8)]
        self.riders = []
        for i, ci in enumerate(cols):
            lane, s = starts[i]
            r = Rider(ci, lane, s, kinds[i], rnd)
            if i == 0:
                r.sig, r.mistake, r.thr, r.wh_p, r.blind = 2.5, 0.05, rnd.uniform(25, 28), 0.995, 0.02
            else:
                skill = rnd.uniform(0.0, 1.0)
                r.sig = 3 + 6 * (1 - skill)
                r.mistake = 0.01 + 0.04 * (1 - skill)
                r.thr = rnd.uniform(22, 27)
                r.greedy_p = 0.0012
                r.wh_p = 0.9 + 0.09 * skill
                r.blind = 0.05 + 0.2 * (1 - skill)
                r.pace = rnd.uniform(0.96, 1.05) + 0.01 * ti
            r.pref = rnd.choice((0, 1, 2, 3))
            self.riders.append(r)
        self.player = self.riders[0]
        self.cam = 0.0
        self.finish_s = LINE_X + LAPS * self.W.lap
        self.player_done_t = None
        self.laptime_show = 0
        self.best_lap = None

    # ------------------------------------------------------------------ bot / CPU decisions
    def lane_cost(self, r, l, others):
        W = self.W
        S, A = W.surf[l], W.air[l]
        x = int(r.s) % W.lap
        c = abs(l - r.pref) * 0.15 + abs(l - r.lane) * 0.3
        for k in range(10, 100, 8):
            p = x + k
            sf = S[p]
            if sf in HAZARD:
                w = HAZARD[sf] * (1.25 - k / 130.0)
                if A[p]:
                    w *= 0.15
                c += w
            elif sf == 5 and r.temp > 15:
                c -= 4.0 * (1.2 - k / 120.0)
        for o in others:
            if o is r or o.mode != "ride":
                continue
            ds = o.s - r.s
            if abs(o.lane - l) < 0.75:
                if 0 < ds < 60 and o.v < r.v + 0.4:
                    c += 16.0 - ds * 0.2
                elif -16 < ds <= 0 and l != int(round(r.lane)):
                    c += 5.0
        if r.kind == "pursuer" and r is not self.player:
            p = self.player
            if 8 < p.s - r.s < 90 and p.mode == "ride":
                c += abs(l - p.lane) * 1.5
        return c

    def decide(self, r):
        W = self.W
        t = self.t
        x = r.s
        # Lane and gear are re-planned every few ticks; staggering by colour spreads the work over ticks.
        if r.greedy > 0:
            r.greedy -= 1
        elif r.rnd.random() < r.greedy_p:
            r.greedy = 130
        if (t + r.ci) % 5 == 0:
            # a distracted rider skips the replanning now and then; nobody changes lanes while climbing a ramp
            on_ramp = not r.air and W.ground(r.lane, x) > 1.5 and W.ground(r.lane, x + 6) > 1.5
            if r.rnd.random() >= r.blind * 0.15 and not on_ramp:
                best, bc = r.tl, 1e9
                for l in range(4):
                    cl = self.lane_cost(r, l, self.riders)
                    if cl < bc:
                        best, bc = l, cl
                r.tl = best
            thr = r.thr
            xi = int(x) % W.lap
            S = W.surf[clamp(int(r.lane + 0.5), 0, 3)]
            for k in range(4, 60, 8):
                if S[xi + k] == 5:
                    thr += 5
                    break
            if r.greedy > 0:
                thr = HOT + 3
            r.gas = "B" if r.temp < thr else "A"
            if r.air:
                r.gas = "A"
        if not r.wheelie and not r.air and r.wh_skip < x:
            # a speed bump needs a wheelie raised before the front wheel gets there; a careless CPU rider forgets it
            xi = int(x) % W.lap
            S = W.surf[clamp(int(r.lane + 0.5), 0, 3)]
            for k in range(10, 14 + int(r.v * 9), 2):
                if S[xi + k] == 4:
                    if r.rnd.random() < r.wh_p:
                        r.wheelie, r.wh_x, r.wh_t = True, x + k + 9, 0
                    else:
                        r.wh_skip = x + k + 12
                    break
        if r.wheelie:
            r.wh_t += 1
            if x > r.wh_x or r.wh_t > 34:
                r.wheelie = False
        pitch = 0
        if r.air:
            # Walk the ballistic path forward until it meets the ground; a closed form is fooled by ramps that
            # rise under the predicted landing spot.
            xg, zg, vzg, vg = x, r.z, r.vz, r.v
            for _ in range(70):
                vzg += -GRAV + 0.0012 * r.th
                vg = clamp(vg - 0.004 * r.th, 0.0, VB * 1.12)
                zg += vzg
                xg += vg
                if zg <= W.ground(r.lane, xg):
                    break
            alpha = self.surface_angle(r.lane, xg)
            target = clamp(alpha + r.perr, -60, 60)
            if target - r.th > 3:
                pitch = 1
            elif target - r.th < -3:
                pitch = -1
        return pitch

    # ------------------------------------------------------------------ physics
    def start_fall(self, r, why, harsh=1.0):
        r.mode, r.mt = "crash", 0
        r.crashes += 1
        r.why = why
        W = self.W
        r.bs, r.bv, r.bth = r.s, r.v * 0.8, r.th
        r.bz, r.bvz = r.z, max(r.vz, 0.8)
        r.bspin = r.rnd.choice((-1, 1)) * (10 + 6 * r.v)
        r.rs, r.rz, r.rvx = r.s + 6, r.z + 10, r.v * 1.05 + 0.4
        r.rvz, r.rth, r.rspin = 2.0 + 0.5 * r.v * harsh, 0.0, 34 + 10 * r.v
        r.run_t = 26 + r.rnd.randrange(0, 12) if r.kind == "player" else 24 + r.rnd.randrange(0, 22)
        r.air = False
        r.wheelie = False
        r.v = 0.0
        r.dl = 0.0

    def surface_angle(self, lane, x):
        # The angle a bike resting with its rear wheel at x would take: the chord between both wheels. Using the same
        # measure for planning and for judging the landing keeps the bot consistent, and the sheer back edge of a
        # jump is not mistaken for a landing slope.
        W = self.W
        return math.degrees(math.atan2(W.ground(lane, x + WHEEL) - W.ground(lane, x), float(WHEEL)))

    def land(self, r):
        W = self.W
        alpha = self.surface_angle(r.lane, r.s)
        e = r.th - alpha
        slope = math.tan(math.radians(alpha))
        rel = slope * r.v - r.vz
        loss = 0.0
        if e < -42 or e > 56 or rel > 7.0:
            self.start_fall(r, "landing")
            return
        if abs(e) > 22:
            loss = 0.45
        elif abs(e) > 10:
            loss = 0.15
        loss += 0.04 * max(0.0, rel - 1.5)
        r.v *= 1.0 - loss
        r.air = False
        r.z = W.ground(r.lane, r.s)
        r.vzg = slope * r.v
        r.th = alpha

    def ride(self, r):
        W = self.W
        pitch = 0
        if r.done:
            r.gas = None
            r.wheelie = False
        elif r.cool:
            r.gas = None
        else:
            pitch = self.decide(r)
        gas = r.gas
        if r.cool:
            r.v *= 0.9
        if not r.air:
            if gas == "B":
                r.temp += 0.14
            elif gas == "A":
                r.temp += (17 - r.temp) * 0.02
            else:
                r.temp = max(COOLED - 1, r.temp - (0.28 if r.cool else 0.05))
            if r.cool and r.temp <= COOLED:
                r.cool = False
            if r.temp >= HOT and not r.cool:
                r.cool = True
            if r.done:
                r.v *= 0.965
            elif gas:
                top = (VB if gas == "B" else VA) * r.pace
                if r.v < top:
                    r.v = min(top, r.v + (0.085 if gas == "B" else 0.05))
                else:
                    r.v = max(top, r.v - 0.04)
            elif not r.cool:
                r.v = max(0.0, r.v - 0.015)
            if r.kind != "pursuer":
                for o in self.riders:
                    if o is not r and o.mode == "ride" and 0 < o.s - r.s < 26 and abs(o.lane - r.lane) < 0.7 and r.v > o.v - 0.1:
                        r.v -= 0.12
                        break
            sf = W.surface(r.lane, r.s + 7)
            if sf in (1, 2, 3):
                cap = {1: 0.95, 2: 1.25, 3: 1.0}[sf]
                if r.v > cap:
                    r.v += (cap - r.v) * 0.2
            elif sf == 5:
                r.temp = COOLED - 1
            front = W.surface(r.lane, r.s + WHEEL)
            if front == 4 and r.last_surf != 4:
                if r.th < 14:
                    if r.v > 1.6:
                        self.start_fall(r, "bump")
                        return
                    r.v *= 0.4
            r.last_surf = front
            chord = (W.ground(r.lane, r.s + WHEEL - 1) - W.ground(r.lane, r.s)) / (WHEEL - 1)
            if gas and not r.cool:
                # a bike restarting from a standstill on a steep face must still be able to climb it
                r.v = max(r.v, 0.25)
            if chord > 0:
                r.v -= 0.07 * chord
            else:
                r.v = min(VB * 1.1, r.v - 0.05 * chord)
            r.v = max(0.0, r.v)
            target = 30.0 if r.wheelie else math.degrees(math.atan(chord))
            r.th += clamp(target - r.th, -8.0, 8.0)
            if r.wheelie and r.th > 58:
                self.start_fall(r, "wheelie")
                return
            nx = r.s + r.v
            gn = W.ground(r.lane, nx)
            if r.z + r.vzg - GRAV > gn + 0.5 and r.v > 0.3 and not r.cool:
                r.air, r.vz = True, r.vzg
                r.perr = r.rnd.gauss(0.0, r.sig)
                if r.vz > 1.2 and r.rnd.random() < r.mistake:
                    r.perr += r.rnd.choice((-1, 1)) * r.rnd.uniform(26, 44)
                r.s = nx
            else:
                r.vzg = gn - r.z
                r.z = gn
                r.s = nx
            r.dl = clamp(r.tl - r.lane, -0.13, 0.13)
        else:
            r.th = clamp(r.th + pitch * 4.5 - 0.4, -85.0, 85.0)
            r.v = clamp(r.v - 0.004 * r.th, 0.0, VB * 1.12)
            r.vz += -GRAV + 0.0012 * r.th
            r.z += r.vz
            r.s += r.v
            r.dl = clamp(r.tl - r.lane, -0.05, 0.05)
            xf = r.s + WHEEL * math.cos(math.radians(r.th))
            zf = r.z + WHEEL * math.sin(math.radians(r.th))
            if r.z <= W.ground(r.lane, r.s):
                self.land(r)
            elif zf <= W.ground(r.lane, xf):
                self.land(r)
        r.lane = clamp(r.lane + r.dl, 0.0, 3.0)
        if r.s >= self.finish_s and not r.done:
            r.done, r.ft = True, self.t

    def crash_step(self, r):
        W = self.W
        r.mt += 1
        # bike: tumbles through the air, then slides to a stop
        r.bz += r.bvz
        r.bvz -= GRAV
        g = W.ground(r.lane, r.bs)
        if r.bz <= g:
            r.bz, r.bvz = g, 0.0
            r.bv *= 0.86
            r.bspin *= 0.6
        r.bs += r.bv
        r.bth += r.bspin
        r.s = r.bs
        r.rs += r.rvx
        r.rz += r.rvz
        r.rvz -= GRAV
        r.rth += r.rspin
        gr = W.ground(r.lane, r.rs)
        if r.rz <= gr:
            r.rz = gr
            if r.rvz < -1.0:
                r.rvz = -r.rvz * 0.35
            else:
                r.rvz = 0.0
            r.rvx *= 0.8
            r.rspin *= 0.5
        if r.mt > 30 and r.rz <= gr + 0.01 and r.bv < 0.2:
            r.mode, r.mt = "run", 0
            r.th = 0.0
            r.bth = 0.0

    def other_steps(self, r):
        if r.mode == "crash":
            self.crash_step(r)
        elif r.mode == "run":
            r.mt += 1
            if r.mt < 8:
                return
            d = r.bs - r.rs
            sp = max(0.5, abs(d) / max(1, r.run_t - 8)) * (1 if d >= 0 else -1)
            if abs(d) > abs(sp):
                r.rs += sp
            if r.mt > r.run_t:
                r.mode, r.mt = "mount", 0
        elif r.mode == "mount":
            r.mt += 1
            if r.mt > 5:
                r.mode = "ride"
                r.air, r.z, r.v, r.vzg, r.th = False, self.W.ground(r.lane, r.s), 0.0, 0.0, 0.0
                r.gas = "B"
                r.wheelie = False

    def collisions(self):
        rs = [r for r in self.riders if r.mode == "ride" and not r.done]
        for a in rs:
            for b in rs:
                if a is b:
                    continue
                ds = b.s - a.s
                # The rider behind falls: his front wheel hits the rear wheel of the one ahead.
                if 0 < ds < 12 and abs(a.lane - b.lane) < 0.55 and abs(a.z - b.z) < 6 and a.v >= b.v - 0.15:
                    self.start_fall(a, "collision", 0.7)
                    break

    # ------------------------------------------------------------------ flow
    def update(self):
        t = self.t
        self.t += 1
        if self.phase == "gate":
            if t >= GO_TICK:
                self.phase = "run"
            return
        for r in self.riders:
            if r.mode == "ride":
                self.ride(r)
            else:
                self.other_steps(r)
        self.collisions()
        p = self.player
        if p.done and self.player_done_t is None:
            self.player_done_t = self.t
        # lap timing for the BEST banner
        done_laps = LAPS if p.done else max(0, int((p.s - LINE_X) // self.W.lap))
        while len(p.laps_t) < done_laps:
            p.laps_t.append(self.t - GO_TICK)
            lt = p.laps_t[-1] - (p.laps_t[-2] if len(p.laps_t) > 1 else 0)
            if self.best_lap is None or lt < self.best_lap:
                self.best_lap = lt
            self.laptime_show = 90
        self.cam = max(0.0, p.s - 70.0)

    def over(self):
        if self.player_done_t is not None and self.t - self.player_done_t > 100:
            return True
        return self.t > 30 * 240

    def standings(self):
        def key(r):
            if r.ft is not None:
                return (0, r.ft)
            return (1, -r.s)
        return sorted(self.riders, key=key)


def mmss(ticks):
    s = max(0, ticks) // TICK_RATE
    return "%d:%02d" % (s // 60, s % 60)


def parse_mmss(txt):
    m, s = txt.split(":")
    return (int(m) * 60 + int(s)) * TICK_RATE


class Screen:
    # Owns the framebuffer side of the game: strip slicing, sprite pasting and HUD.
    def __init__(self):
        self.prev_static = set()
        self.hud_key = None
        self.W = None

    def new_track(self, W, best_txt):
        self.W = W
        self.prev_static = set()
        self.hud_key = None
        self.best_txt = best_txt
        self.paint_banner("BEST " + best_txt)
        for y in W.static:
            self.put_row(y, W.static[y])
        for y in W.dyn:
            self.put_row(y, W.strip[y][:ROWB])
        fill_rect(X0, Y0 + HUD_Y * 4, VW * 4, (VH - HUD_Y) * 4, 0)

    def paint_banner(self, txt):
        W = self.W
        x0, y0 = 172, 14
        white = B["px_white"]
        for j in range(7):
            row = W.static[y0 + j]
            row[x0 * 8:(x0 + len(txt) * 7) * 8] = W.wall_px * (len(txt) * 7)
            for i, ch in enumerate(txt):
                bits = B["glyphs"][ch][j]
                for c, bit in enumerate(bits):
                    if bit == "1":
                        o = (x0 + i * 7 + c) * 8
                        row[o:o + 8] = white
            self.put_row(y0 + j, row)

    def put_row(self, y, buf):
        o = (Y0 + y * 4) * S + X0 * 2
        n = len(buf)
        fb[o:o + n] = buf
        fb[o + S:o + S + n] = buf
        fb[o + 2 * S:o + 2 * S + n] = buf
        fb[o + 3 * S:o + 3 * S + n] = buf

    def draw(self, race):
        W = race.W
        t = race.t
        lap = W.lap
        cam = race.cam
        xs = int(cam) % lap
        o = xs * 8
        strip, static = W.strip, W.static
        rows = {y: bytearray(strip[y][o:o + ROWB]) for y in W.dyn}
        touched = set()
        sprites = []        # (sprite, left, top) in paint order
        # world decoration inside the green band
        for kind, s in W.deco:
            dx = (s - cam) % lap
            if dx > lap - 60:
                dx -= lap
            if -40 < dx < VW:
                if kind == "flagger":
                    sp = MISC["flagger"][(t // 9) % 2]
                elif kind == "sign":
                    sp = MISC["sign"][(s // 100) % 2]
                else:
                    sp = MISC[kind]
                sprites.append((sp, int(dx), TRACK_TOP - 5 - sp["h"] - (8 if kind == "tree" else 0)))
        if cam < LINE_X + 20:
            gx = LINE_X - cam
            if t < GO_TICK:
                sprites.append((MISC["gate"], int(gx) - 3, TRACK_TOP - 2))
                n = 0 if t < 40 else 1 if t < 62 else 2 if t < 84 else 3
                sprites.append((MISC["lights"][n], int(gx) - 9, TRACK_TOP - 14))
            elif t < GO_TICK + 50:
                sprites.append((MISC["gate_down"], int(gx) - 3, TRACK_TOP - 2))
                sprites.append((MISC["lights"][4], int(gx) - 9, TRACK_TOP - 14))
        order = sorted(race.riders, key=lambda r: (r.lane, r.s))
        for r in order:
            self.rider_sprites(r, race, cam, sprites)
        for sp, px, py in sprites:
            rws = sp["rows"]
            w = sp["w"]
            if px + w <= 0 or px >= VW:
                continue
            for j, row in enumerate(rws):
                y = py + j
                if y < 0 or y >= HUD_Y or not row:
                    continue
                buf = rows.get(y)
                if buf is None:
                    buf = rows[y] = bytearray(static[y])
                    touched.add(y)
                for rx, b in row:
                    xx = px + rx
                    n = len(b) >> 3
                    if xx >= 0 and xx + n <= VW:
                        buf[xx * 8:xx * 8 + n * 8] = b
                    elif xx + n > 0 and xx < VW:
                        if xx < 0:
                            b = b[-xx * 8:]
                            xx = 0
                        if xx + (len(b) >> 3) > VW:
                            b = b[:(VW - xx) * 8]
                        buf[xx * 8:xx * 8 + len(b)] = b
        for y in self.prev_static - touched:
            self.put_row(y, static[y])
        self.prev_static = touched
        put = self.put_row
        for y, buf in rows.items():
            put(y, buf)
        self.hud(race)

    def rider_sprites(self, r, race, cam, out):
        W = race.W
        t = race.t
        ci = r.ci
        lane_y = LANE_Y[0] + 20 * r.lane
        if r.mode in ("ride", "mount"):
            x = r.s - cam
            if x < -40 or x > VW + 20:
                return
            th = r.th
            ang = clamp(int(round(th / 5.0)) * 5, -180, 175)
            ai = (ang + 180) // 5
            phase = (t // 2) % 2 if r.v > 0.3 else 0
            yaw = 0
            if not r.air and r.mode == "ride":
                yaw = -1 if r.dl < -0.03 else 1 if r.dl > 0.03 else 0
            sp = BIKE.get((ci, ai, phase, yaw)) or BIKE.get((ci, ai, 0, 0)) or BIKE.get((ci, ai, 0, yaw))
            if sp is None:
                sp = BIKE[(ci, "solo", int(round(th / 15.0)) * 15)]
            a = math.radians(th)
            cx = x + WHEEL / 2 * math.cos(a)
            cy = lane_y - r.z - 5 - WHEEL / 2 * math.sin(a)
            if r.z > 3:
                gh = W.ground(r.lane, r.s + 7)
                out.append((MISC["shadow"], int(x), int(lane_y - gh - 1)))
            out.append((sp, int(round(cx - (CEN - sp["ox"]))), int(round(cy - (CEN - sp["oy"])))))
            if r.cool:
                sm = MISC["smoke"][(t // 4) % 3]
                out.append((sm, int(x) + 2, int(cy) - 24))
        else:
            bx = r.bs - cam
            gb = lane_y - r.bz
            if -40 < bx < VW + 20:
                if r.mode == "crash" and (r.bv > 0.25 or r.bz > W.ground(r.lane, r.bs) + 0.1):
                    sp = BIKE[(ci, "solo", (int(round(r.bth / 15.0)) * 15 + 180) % 360 - 180)]
                else:
                    sp = BIKE[(ci, "solo", 165)]
                out.append((sp, int(round(bx - (CEN - sp["ox"]))), int(round(gb - 6 - (CEN - sp["oy"])))))
            rx = r.rs - cam
            if -40 < rx < VW + 20:
                gr = lane_y - r.rz
                if r.mode == "crash" and (r.rz > W.ground(r.lane, r.rs) + 0.1 or r.rvx > 0.8):
                    sp = BIKE[(ci, "tumble", int(round(r.rth / 30.0)) * 30 % 360)]
                    out.append((sp, int(round(rx - (CEN - sp["ox"]))), int(round(gr - 6 - (CEN - sp["oy"])))))
                elif r.mode == "run" and r.mt >= 8:
                    sp = BIKE[(ci, "run", (r.mt // 3) % 4)]
                    out.append((sp, int(rx - sp["w"] // 2), int(gr - sp["h"] + 2)))
                else:
                    sp = BIKE[(ci, "lying")]
                    out.append((sp, int(rx - sp["w"] // 2), int(gr - sp["h"] + 1)))

    def hud(self, race):
        p = race.player
        t = race.t
        stand = race.standings()
        place = stand.index(p) + 1
        lap_no = clamp(int((p.s - LINE_X) // race.W.lap) + 1, 1, LAPS) if p.s >= LINE_X else 1
        shown = mmss(max(0, t - GO_TICK))
        if race.laptime_show > 0:
            race.laptime_show -= 1
            shown = mmss(p.laps_t[-1] - (p.laps_t[-2] if len(p.laps_t) > 1 else 0))
        seg = int(clamp((p.temp - 8) / (HOT - 8) * 20, 0, 20))
        key = (seg, place, lap_no, shown, race.laptime_show > 0, p.cool and (t // 6) % 2, race.W.ti)
        if key == self.hud_key:
            return
        self.hud_key = key
        y = Y0 + HUD_Y * 4 + 4
        x = X0 + 8
        fill_rect(X0, Y0 + HUD_Y * 4, VW * 4, (VH - HUD_Y) * 4, 0)
        draw_text("TEMP", x, y, "S", COLOR_RED if key[5] else COLOR_WHITE, bg=False)
        bx = x + 108
        fill_rect(bx - 4, y + 4, 20 * 11 + 8, 32, 0xFFFF)
        fill_rect(bx - 2, y + 6, 20 * 11 + 4, 28, 0)
        for i in range(seg):
            col = rgb565(60, 220, 60) if i < 10 else rgb565(240, 220, 40) if i < 16 else rgb565(240, 50, 30)
            fill_rect(bx + i * 11, y + 8, 9, 24, col)
        draw_text("LAP %d/%d" % (lap_no, LAPS), X0 + 372, y, "S", COLOR_WHITE, bg=False)
        draw_text("P%d" % place, X0 + 580, y, "S", COLOR_CYAN, bg=False)
        draw_text(shown, X0 + 660, y, "S", COLOR_YELLOW if race.laptime_show > 0 else COLOR_WHITE, bg=False)
        third = mmss(parse_mmss(self.best_txt) + 8 * TICK_RATE)
        draw_text("3RD " + third, X0 + 790, y, "S", COLOR_GREEN, bg=False)


def make():
    rnd = random.Random()
    clear(0)
    scr = Screen()
    state = {"race": None, "idx": 0, "score": 0, "tick": 0, "mode": "intro", "hold": 0, "end": None,
             "best": [t["best"] for t in B["tracks"]]}

    def start_race():
        ti = state["idx"] % len(B["tracks"])
        race = Race(ti, rnd, state["idx"])
        state["race"] = race
        scr.new_track(race.W, state["best"][ti])
        state["mode"] = "race"

    def finish_race():
        race = state["race"]
        stand = race.standings()
        p = race.player
        place = stand.index(p) + 1
        pts = POINTS[place - 1]
        par = race.W.lap * LAPS / 2.5
        bonus = 0
        if p.ft is not None:
            bonus = int(max(0.0, par - (p.ft - GO_TICK)) / TICK_RATE * 10)
        state["score"] += pts * 100 + bonus
        ti = state["idx"] % len(B["tracks"])
        if race.best_lap is not None and race.best_lap < parse_mmss(state["best"][ti]):
            state["best"][ti] = mmss(race.best_lap)
        fill_rect(X0 + 96, Y0 + 280, 832, 420, 0)
        fill_rect(X0 + 96, Y0 + 280, 832, 6, 0xFFFF)
        fill_rect(X0 + 96, Y0 + 694, 832, 6, 0xFFFF)
        draw_text("RACE %d  %s" % (state["idx"] + 1, race.W.name), X0 + 130, Y0 + 304, "S", COLOR_YELLOW)
        for i, r in enumerate(stand):
            tm = mmss(r.ft - GO_TICK) if r.ft is not None else "---"
            col = COLOR_RED if r is p else COLOR_WHITE
            draw_text("%d  %-7s %s  +%d" % (i + 1, NAMES[r.ci], tm, POINTS[i]), X0 + 130, Y0 + 360 + i * 46, "S", col)
        draw_text("SCORE %d" % state["score"], X0 + 130, Y0 + 610, "S", COLOR_CYAN)
        state["mode"], state["hold"] = "results", 0

    def step():
        state["tick"] += 1
        m = state["mode"]
        if m == "end":
            return state["end"].tick()
        if state["tick"] >= CAP_TICKS - 240 and m != "results":
            m = state["mode"] = "results"
            state["hold"] = 10 ** 6
        if m == "intro":
            start_race()
            return False
        if m == "race":
            race = state["race"]
            race.update()
            scr.draw(race)
            if race.t < 70:
                draw_text("RACE %d  %s" % (state["idx"] + 1, race.W.name), X0 + 330, Y0 + 120, "S", COLOR_YELLOW, bg=False)
            elif race.t == 70:
                # static rows are not repainted by the frame loop, so the banner text has to be wiped explicitly
                for y in range(28, 42):
                    scr.put_row(y, race.W.static[y])
            if race.over():
                finish_race()
            return False
        if m == "results":
            state["hold"] += 1
            if state["hold"] > 170:
                state["idx"] += 1
                if state["idx"] >= RACES or state["tick"] >= CAP_TICKS - 240:
                    state["mode"] = "end"
                    clear(0)
                    state["end"] = EndScreen()
                    state["end"].start(state["score"])
                else:
                    state["mode"] = "intro"
                    clear(0)
            return False
        return False

    return step
