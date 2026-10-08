# Space Frog: classic Frogger rules played by a look-ahead bot.
# Rendering: every moving lane is a pre-rendered strip sliced per scanline; the frog and other sprites are
# composited into the row buffer as RLE runs. The bot searches (A*) over (tick, row, x) states with the very
# same collision functions the game uses, so its plans are exact until it deliberately makes a human-like slip.
from fbcore import *
import heapq, math

B = load_bundle("g_frogger.bin")
T_ = 72                                  # tile
FWP = 13 * T_                            # playfield width
PX0 = (W - FWP) // 2
PY0 = (H - 14 * T_) // 2
ROWB = FWP * 2                           # bytes per playfield row
HOP = 6                                  # ticks per hop
LIFE_TICKS = 900                         # 30 s per frog
HW = 24                                  # real frog half-width for collisions
TARGET = 14000
BAYS = B["bays"]
BAY_C = [(l + r) // 2 for l, r in BAYS]
CAR_LEN = B["car_len"]
FIELD = B["field"][2]
SCREEN = B["screen"][2]
DIRS = ((0, -1), (-1, 0), (1, 0), (0, 1))     # up, left, right, down: same order as the frog sprites
CAR, LOG, TURTLE, GATOR = range(4)
FRAME_TICKS = 6


class Lane:
    def __init__(self, row, spec, strips):
        self.row = row
        self.road = spec["kind"] == "road"
        self.dir = spec["dir"]
        self.base = spec["speed"]
        self.pp = spec["period"] * T_
        self.dphase = spec.get("dphase", 0)
        self.strips = strips
        self.variants = []
        for objs in [spec["objs"]] + ([spec["alt"]] if "alt" in spec else []):
            lst = []
            for o in objs:
                if o[0] == "car":
                    lst.append((o[1] * T_, CAR_LEN[o[2]], CAR, 0))
                elif o[0] == "log":
                    lst.append((o[1] * T_, o[2] * T_, LOG, 0))
                elif o[0] == "turtle":
                    lst.append((o[1] * T_, o[2] * T_, TURTLE, o[3]))
                else:
                    lst.append((o[1] * T_, 4 * T_, GATOR, 0))
            self.variants.append(lst)
        self.has_dive = any(o[2] == TURTLE and o[3] for o in self.variants[0])
        self.variant = 0
        self.pos0 = random.uniform(0, self.pp)
        self.t0 = 0
        self.v = 0.0
        self.normal = 130
        self.cache = {}

    def configure(self, now, scale, normal, variant):
        # Rebase so the picture does not jump when the speed changes.
        self.pos0 = self.off(now)
        self.t0 = now
        self.v = self.dir * self.base * scale * T_ / 30.0
        self.normal = normal
        self.variant = min(variant, len(self.variants) - 1)
        self.cache = {}

    def off(self, t):
        return (self.pos0 + self.v * (t - self.t0)) % self.pp

    def dive_state(self, t):
        # 0 floating, 1 sinking, 2 nearly gone (unsafe), 3 under water.
        under = 40
        cyc = self.normal + 32 + under
        p = (t + self.dphase) % cyc
        if p < self.normal:
            return 0
        p -= self.normal
        if p < 8:
            return 1
        if p < 16:
            return 2
        if p < 16 + under:
            return 3
        p -= 16 + under
        return 2 if p < 8 else 1

    def hits(self, t):
        # Road: list of (lo, hi) car intervals. River: (lo, hi, code) with code 1 = safe to stand, 2 = deadly.
        r = self.cache.get(t)
        if r is not None:
            return r
        if len(self.cache) > 3000:
            self.cache.clear()
        off = self.off(t)
        pp = self.pp
        res = []
        ds = self.dive_state(t) if self.has_dive else 0
        for a0, ln, typ, diver in self.variants[self.variant]:
            a = (a0 + off) % pp
            for k in (-1, 0, 1):
                s = a + k * pp
                if s + ln < -40 or s > FWP + 40:
                    continue
                if typ == CAR:
                    res.append((s + 5, s + ln - 5))
                elif typ == LOG:
                    res.append((s + 8, s + ln - 8, 1))
                elif typ == TURTLE:
                    if not (diver and ds >= 2):
                        res.append((s + 10, s + ln - 10, 1))
                elif self.dir > 0:
                    res.append((s + 8, s + ln - T_, 1))
                    res.append((s + ln - T_, s + ln, 2))
                else:
                    res.append((s, s + T_, 2))
                    res.append((s + T_, s + ln - 8, 1))
        res = tuple(res)
        self.cache[t] = res
        return res


def road_hit(lane, x, t, hw):
    lo, hi = x - hw, x + hw
    for a, b in lane.hits(t):
        if a < hi and b > lo:
            return True
    return False


def river_dead(lane, x, t):
    ok = False
    for a, b, code in lane.hits(t):
        if a <= x <= b:
            if code == 2:
                return True
            ok = True
    return not ok


class World:
    # Everything the game and the planner must agree on lives here.
    def __init__(self):
        self.lanes = {r: Lane(r, spec, B["strips"][r]) for r, spec in B["lanes"].items()}
        self.level = 1
        self.filled = [False] * 5
        self.events = []
        self.snake_phase = random.randrange(420)
        self.apply_level(0)

    def apply_level(self, now):
        lv = self.level
        scale = min(1.9, 1 + 0.1 * (lv - 1))
        normal = max(70, 130 - 14 * (lv - 1))
        for lane in self.lanes.values():
            lane.configure(now, scale, normal, 1 if lv >= 3 else 0)

    # --- median snake: a deterministic function of time, so the bot can plan around it
    def snake(self, t):
        if self.level < 2:
            return None
        c = 420
        k, p = divmod(t + self.snake_phase, c)
        if p >= 210:
            return None
        sx = -90 + p * 4.32
        return (sx, 1) if k % 2 == 0 else (FWP - sx, -1)

    def snake_hit(self, x, t):
        s = self.snake(t)
        return s is not None and abs(x - s[0]) < 74

    # --- bay events (fly / crocodile), scheduled ahead so the bot can see them coming
    def ensure_events(self, t):
        while not self.events or self.events[-1]["t1"] < t + 900:
            last = self.events[-1]["t1"] if self.events else t
            t0 = max(t, last) + random.randint(60, 200)
            free = [i for i in range(5) if not self.filled[i]] or list(range(5))
            croc = self.level >= 3 and random.random() < 0.45
            dur = random.randint(150, 240) if croc else random.randint(170, 260)
            self.events.append({"bay": random.choice(free), "kind": "croc" if croc else "fly", "t0": t0, "t1": t0 + dur})
        while self.events and self.events[0]["t1"] < t - 5:
            self.events.pop(0)

    def bay_event(self, i, t):
        for e in self.events:
            if e["bay"] == i and e["t0"] <= t < e["t1"]:
                return e
        return None

    def bay_at(self, x):
        for i, (l, r) in enumerate(BAYS):
            if l + 14 <= x <= r - 14:
                return i
        return -1

    # --- one hop, shared by the game and the planner. Returns None when the frog dies, else (row, x, bay).
    def sim_hop(self, row, x, d, t, hw):
        dx, dy = DIRS[d]
        row2 = row + dy
        x2 = x + dx * T_
        if row2 < 0 or row2 > 12 or not 24 <= x2 <= FWP - 24:
            return None
        lanes = self.lanes
        for k in range(1, HOP):
            er = row if k <= 3 else row2
            ex = x + (x2 - x) * k / HOP
            if 7 <= er <= 11:
                if road_hit(lanes[er], ex, t + k, hw):
                    return None
            elif er == 6 and self.snake_hit(ex, t + k):
                return None
        tl = t + HOP
        if row2 == 0:
            i = self.bay_at(x2)
            if i < 0 or self.filled[i]:
                return None
            e = self.bay_event(i, tl)
            if e is not None and e["kind"] == "croc":
                return None
            return (0, BAY_C[i], i)
        if 7 <= row2 <= 11:
            if road_hit(lanes[row2], x2, tl, hw):
                return None
        elif row2 == 6:
            if self.snake_hit(x2, tl):
                return None
        elif 1 <= row2 <= 5:
            if river_dead(lanes[row2], x2, tl):
                return None
        return (row2, x2, -1)

    def sim_rest(self, row, x, t, n, hw):
        # n ticks standing still; rivers carry the frog. Returns the new x or None when it dies.
        lane = self.lanes.get(row)
        for i in range(1, n + 1):
            tt = t + i
            if 1 <= row <= 5:
                x += lane.v
                if not 12 <= x <= FWP - 12 or river_dead(lane, x, tt):
                    return None
            elif 7 <= row <= 11:
                if road_hit(lane, x, tt, hw):
                    return None
            elif row == 6 and self.snake_hit(x, tt):
                return None
        return x


class Search:
    # Weighted A* over (tick, row, x); goal is the median strip or a free bay.
    MAX_NODES = 20000

    def __init__(self, world, row, x, t0, home, hw, deadline):
        self.w = world
        self.t0 = t0
        self.home = home
        self.hw = hw
        self.deadline = deadline
        self.nodes = [(t0, row, x, -1, 0, 0)]
        self.heap = [(self.h(row), 0, 0)]
        self.closed = set()
        self.expanded = 0
        self.plan = None
        self.failed = False
        fly = [e for e in world.events if e["kind"] == "fly" and e["t1"] > t0 and not world.filled[e["bay"]]]
        self.fly = fly

    def h(self, row):
        return 4 * HOP * (row if self.home else max(0, row - 6))

    def bay_penalty(self, bay, t):
        # A fly is worth waiting a few seconds for; a bay is otherwise as good as any other.
        if not self.fly:
            return 0
        for e in self.fly:
            if e["bay"] == bay and e["t0"] - 20 <= t < e["t1"] - 10:
                return 0
        return 100

    def run(self, budget):
        heap, nodes, closed, w = self.heap, self.nodes, self.closed, self.w
        limit = min(self.deadline, self.t0 + 700)
        while budget > 0 and heap:
            _, _, i = heapq.heappop(heap)
            t, row, x, par, act, g = nodes[i]
            # On the median the frog will idle while the next plan is computed: the spot must stay snake-free
            # for that long, otherwise the "safe" strip is where it dies.
            if (row == 0 and self.home) or (row == 6 and not self.home and par >= 0
                                            and w.sim_rest(6, x, t, 40, self.hw) is not None):
                plan = []
                while par >= 0:
                    pt = nodes[par][0]
                    if act >= 0:
                        plan.append((pt, act))
                    i, (t, row, x, par, act, g) = par, nodes[par]
                plan.reverse()
                self.plan = plan
                return True
            key = (row, int(x) // 12, t)
            if key in closed:
                continue
            closed.add(key)
            budget -= 1
            self.expanded += 1
            if self.expanded > self.MAX_NODES:
                break
            if row == 0:
                continue
            if t + 2 <= limit and row != 13:
                nx = w.sim_rest(row, x, t, 2, self.hw)
                if nx is not None:
                    nodes.append((t + 2, row, nx, i, -1, g + 2))
                    heapq.heappush(heap, (g + 2 + self.h(row), len(nodes), len(nodes) - 1))
            if t + HOP > limit:
                continue
            for d in (0, 1, 2, 3):
                if d == 3 and row == 12:
                    continue
                r = w.sim_hop(row, x, d, t, self.hw)
                if r is None:
                    continue
                cost = g + HOP + (10 if d == 3 else 2 if d else 0)
                if r[0] == 0:
                    cost += self.bay_penalty(r[2], t + HOP)
                nodes.append((t + HOP, r[0], r[1], i, d, cost))
                heapq.heappush(heap, (cost + self.h(r[0]), len(nodes), len(nodes) - 1))
        if not heap or self.expanded > self.MAX_NODES:
            self.failed = True
        return self.failed


EXP_PER_TICK = 100
JITTER = 0.012


class Bot:
    def __init__(self, game):
        self.g = game
        self.plan = []
        self.search = None
        self.lead = 0
        self.late = 0
        self.start_t = 0
        self.retry_at = 0
        self.risky = False

    def reset(self):
        self.plan = []
        self.search = None
        self.late = 0

    def decide(self, t):
        # Returns a hop direction or None. Called only when the frog is resting on a tile.
        g = self.g
        fr = g.frog
        horizon = min(14, self.plan[0][0] - t) if self.plan else 14
        if fr["row"] == 6 and horizon > 0 and g.world.sim_rest(6, fr["x"], t, horizon, HW + 3) is None:
            # The median snake is about to arrive while the frog is still waiting: dodge it like a human would.
            for d in (1, 2, 3, 0):
                r = g.world.sim_hop(6, fr["x"], d, t, HW + 3)
                if r is not None and g.world.sim_rest(r[0], r[1], t + HOP, 12, HW + 3) is not None:
                    self.search = None
                    self.plan = []
                    return d
        if self.plan:
            pt, d = self.plan[0]
            if t > pt + 8:
                self.plan = []
            elif t >= pt:
                self.plan.pop(0)
                if random.random() < JITTER and fr["row"] not in (6, 12):
                    # A human slip: the hop comes a moment late while everything else keeps moving.
                    self.plan.insert(0, (t + random.choice((1, 2)), d))
                    return None
                return d
            else:
                return None
        if fr["row"] in (6, 12):
            if t < self.retry_at:
                return None
            if self.search is None:
                home = fr["row"] == 6
                self.lead = (30 if home else 12) + self.late
                if random.random() < 0.75:
                    self.lead += random.randint(15, 90)
                g.world.ensure_events(t)
                self.start_t = t + self.lead
                self.risky = random.random() < 0.15
                hw = 24 if self.risky else 27
                self.search = Search(g.world, fr["row"], fr["x"], self.start_t, home, hw, g.life_start + LIFE_TICKS - 20)
            s = self.search
            done = s.run(EXP_PER_TICK)
            if done:
                self.search = None
                if s.plan is None or s.failed:
                    self.retry_at = t + 20
                elif s.plan and s.plan[0][0] >= t:
                    self.plan = s.plan
                else:
                    # Planning took longer than the lead: the first hop is already in the past.
                    self.late += 20
                    self.retry_at = t
            return None
        return self.emergency(t)

    def emergency(self, t):
        # Off the safe strips with no plan (should not happen): take any survivable hop, preferably forward.
        fr = self.g.frog
        w = self.g.world
        for d in (0, 1, 2, 3):
            if w.sim_hop(fr["row"], fr["x"], d, t, HW + 2) is not None:
                return d
        return None


class Game:
    def __init__(self):
        self.t = 0
        self.world = World()
        self.score = 0
        self.hi = random.randint(90, 140) * 100
        self.lives = 3
        self.next_life = 20000
        self.phase = "play"
        self.phase_t = 0
        self.rows_sig = [None] * 13
        self.bot = Bot(self)
        self.end = EndScreen()
        self.shown = {}
        self.spawn()
        self.draw_static()

    # ------------------------------------------------------------------ state
    def spawn(self):
        self.frog = {"row": 12, "x": 6 * T_ + 36.0, "dir": 0, "hop": 0, "from": None, "to": None}
        self.best_row = 12
        self.life_start = self.t
        self.bot.reset()
        self.phase = "play"
        self.death = None

    def die(self, kind):
        self.phase = "dying"
        self.phase_t = 0
        self.death = kind
        self.lives -= 1
        fr = self.frog
        fr["hop"] = 0
        self.bot.reset()

    def add_score(self, n):
        self.score += n
        if self.score >= self.next_life:
            self.lives += 1
            self.next_life += 20000
        self.hi = max(self.hi, self.score)

    # ------------------------------------------------------------------ rules
    def start_hop(self, d):
        fr = self.frog
        dx, dy = DIRS[d]
        fr["dir"] = d
        fr["hop"] = 1
        fr["from"] = (fr["row"], fr["x"])
        fr["to"] = (fr["row"] + dy, fr["x"] + dx * T_)

    def frog_tick(self):
        fr, w, t = self.frog, self.world, self.t
        if fr["hop"]:
            k = fr["hop"]
            r0, x0 = fr["from"]
            r1, x1 = fr["to"]
            if k < HOP:
                er = r0 if k <= 3 else r1
                ex = x0 + (x1 - x0) * k / HOP
                if 7 <= er <= 11 and road_hit(w.lanes[er], ex, t, HW):
                    return self.die("squash")
                if er == 6 and w.snake_hit(ex, t):
                    return self.die("pop")
                fr["hop"] = k + 1
                return
            fr["hop"] = 0
            fr["row"], fr["x"] = r1, x1
            return self.land()
        row = fr["row"]
        if 1 <= row <= 5:
            lane = w.lanes[row]
            fr["x"] += lane.v
            if not 12 <= fr["x"] <= FWP - 12 or river_dead(lane, fr["x"], t):
                return self.die("splash")
        elif 7 <= row <= 11:
            if road_hit(w.lanes[row], fr["x"], t, HW):
                return self.die("squash")
        elif row == 6 and w.snake_hit(fr["x"], t):
            return self.die("pop")

    def land(self):
        fr, w, t = self.frog, self.world, self.t
        row, x = fr["row"], fr["x"]
        if row < self.best_row:
            self.best_row = row
            self.add_score(10)
        if row == 0:
            i = w.bay_at(x)
            e = w.bay_event(i, t) if i >= 0 else None
            if i < 0 or w.filled[i] or (e and e["kind"] == "croc"):
                return self.die("pop")
            w.filled[i] = True
            fr["x"] = BAY_C[i]
            gain = 50 + 10 * max(0, (self.life_start + LIFE_TICKS - t) // 30)
            if e and e["kind"] == "fly":
                gain += 200
                e["t1"] = t
            self.add_score(gain)
            if all(w.filled):
                self.add_score(1000)
                self.phase = "levelup"
            else:
                self.phase = "homed"
            self.phase_t = 0
            return
        if 1 <= row <= 5:
            if river_dead(w.lanes[row], x, t):
                return self.die("splash")
        elif 7 <= row <= 11 and road_hit(w.lanes[row], x, t, HW):
            return self.die("squash")
        elif row == 6 and w.snake_hit(x, t):
            return self.die("pop")

    # ------------------------------------------------------------------ main step
    def step(self):
        self.t += 1
        t = self.t
        w = self.world
        w.ensure_events(t)
        if t >= CAP_TICKS and self.phase != "over":
            self.finish()
        ph = self.phase
        if ph == "play":
            self.frog_tick()
            if self.phase == "play" and not self.frog["hop"]:
                if t - self.life_start >= LIFE_TICKS:
                    self.die("pop")
                else:
                    d = self.bot.decide(t)
                    if d is not None:
                        self.start_hop(d)
            elif self.phase == "play" and t - self.life_start >= LIFE_TICKS:
                self.die("pop")
        elif ph == "dying":
            self.phase_t += 1
            if self.phase_t > 44:
                if self.lives < 0:
                    self.finish()
                else:
                    self.spawn()
        elif ph == "homed":
            self.phase_t += 1
            if self.phase_t > 36:
                if self.score >= TARGET:
                    self.finish()
                else:
                    self.spawn()
        elif ph == "levelup":
            self.phase_t += 1
            if self.phase_t > 70:
                if self.score >= TARGET:
                    self.finish()
                else:
                    w.filled = [False] * 5
                    w.level += 1
                    w.apply_level(t)
                    self.spawn()
        elif ph == "over":
            return self.end.tick()
        self.render()
        return False

    def finish(self):
        self.phase = "over"
        self.render()
        self.end.start(self.score)

    # ------------------------------------------------------------------ drawing
    def draw_static(self):
        for y in range(H):
            fb[y * S:(y + 1) * S] = SCREEN[y]
        draw_text("SPACE FROG", 120, 84, "S", COLOR_CYAN)
        draw_text("SCORE", 60, 160, "S", COLOR_YELLOW)
        draw_text("HI SCORE", 60, 330, "S", COLOR_YELLOW)
        draw_text("LEVEL", 1500, 100, "S", COLOR_YELLOW)
        draw_text("LIVES", 1500, 270, "S", COLOR_YELLOW)
        draw_text("HOME", 1500, 420, "S", COLOR_YELLOW)
        for yy in range(T_):
            fb[(PY0 + 13 * T_ + yy) * S + PX0 * 2:(PY0 + 13 * T_ + yy) * S + PX0 * 2 + ROWB] = FIELD[13 * T_ + yy]
        draw_text("TIME", PX0 + 10, PY0 + 13 * T_ + 16, "S", COLOR_YELLOW)

    def hud(self):
        w = self.world
        sh = self.shown
        if sh.get("score") != self.score:
            sh["score"] = self.score
            draw_text("%06d" % self.score, 60, 210, "L", COLOR_WHITE)
        if sh.get("hi") != self.hi:
            sh["hi"] = self.hi
            draw_text("%06d" % self.hi, 60, 380, "L", COLOR_WHITE)
        if sh.get("level") != w.level:
            sh["level"] = w.level
            draw_text("%02d" % w.level, 1500, 150, "L", COLOR_GREEN)
        lives = max(0, self.lives)
        if sh.get("lives") != lives:
            sh["lives"] = lives
            fill_rect(1495, 320, 380, 60, 0)
            for i in range(min(lives, 6)):
                blit(B["life"], 1500 + i * 58, 326)
        if sh.get("filled") != tuple(w.filled):
            sh["filled"] = tuple(w.filled)
            for i in range(5):
                fill_rect(1500 + i * 70, 480, 54, 54, 0x07E0 if w.filled[i] else 0x2104)
        left = max(0, LIFE_TICKS - (self.t - self.life_start)) if self.phase == "play" else sh.get("tleft", 0)
        wd = int(790 * left / LIFE_TICKS) // 6
        if sh.get("tbar") != wd:
            sh["tbar"] = wd
            sh["tleft"] = left
            x0, y0 = PX0 + 130, PY0 + 13 * T_ + 23
            fill_rect(x0, y0, 790, 28, 0x2104)
            col = 0x07E0 if left > LIFE_TICKS * 0.5 else 0xFFE0 if left > LIFE_TICKS * 0.25 else 0xF800
            fill_rect(x0, y0, wd * 6, 28, col)

    def overlays(self):
        w, t = self.world, self.t
        ovs = [[] for _ in range(13)]

        def add(sp, ox, oy):
            top = max(0, oy // T_)
            bot = min(12, (oy + sp["h"] - 1) // T_)
            for r in range(top, bot + 1):
                ovs[r].append((sp, ox, oy))

        for i in range(5):
            if w.filled[i]:
                add(B["bayfrog"], BAY_C[i] - 36, 0)
            else:
                e = w.bay_event(i, t)
                if e is not None:
                    if e["kind"] == "fly":
                        add(B["fly"][(t // 3) % 2], BAY_C[i] - 24, 10 + int(3 * math.sin(t / 5.0)))
                    else:
                        add(B["croc"][(t // 12) % 2], BAY_C[i] - 55, 0)
        s = w.snake(t)
        if s is not None:
            add(B["snake"][(t // 5) % 4][1 if s[1] > 0 else 0], int(s[0]) - 90, 6 * T_ + 14)
        fr = self.frog
        if self.phase == "dying":
            cx, cy = int(fr["x"]), fr["row"] * T_ + 36
            k = self.phase_t
            kind = self.death
            if kind == "squash":
                add(B["squash"][min(2, k // 12)], cx - 48, cy - 36)
            elif kind == "splash":
                add(B["splash"][min(4, k // 7)], cx - 60, cy - 60)
            elif k < 32:
                add(B["pop"][min(3, k // 8)], cx - 60, cy - 60)
        elif self.phase == "play":
            if fr["hop"]:
                k = fr["hop"]
                r0, x0 = fr["from"]
                r1, x1 = fr["to"]
                p = k / HOP
                cx = x0 + (x1 - x0) * p
                cy = (r0 + (r1 - r0) * p) * T_ + 36 - 14 * math.sin(math.pi * p)
                sp = B["frog"][fr["dir"]][1]
            else:
                cx, cy = fr["x"], fr["row"] * T_ + 36
                sp = B["frog"][fr["dir"]][0]
            add(sp, int(cx) - 36, int(cy) - 36)
        return ovs

    def render(self):
        t = self.t
        w = self.world
        ovs = self.overlays()
        f = (t // FRAME_TICKS) % 4
        sigs = self.rows_sig
        lanes = w.lanes
        for r in range(13):
            lane = lanes.get(r)
            ol = ovs[r]
            osig = tuple((id(sp), ox, oy) for sp, ox, oy in ol)
            if lane is None:
                sig = osig
                s0 = 0
                strip = None
            else:
                s0 = int((-lane.off(t)) % lane.pp)
                state = lane.dive_state(t) if lane.has_dive else 0
                sig = (s0, state, f, lane.variant, osig)
                strip = lane.strips[lane.variant][state][f][2]
            if sigs[r] == sig:
                continue
            sigs[r] = sig
            self.draw_row(r, lane, strip, s0, ol)
        self.hud()

    def draw_row(self, r, lane, strip, s0, ol):
        base = r * T_
        a, b = s0 * 2, s0 * 2 + ROWB
        road = lane is not None and lane.road
        for yy in range(T_):
            y = base + yy
            if strip is None:
                data = FIELD[y]
            elif road:
                data = strip[yy - 6][a:b] if 6 <= yy < 66 else FIELD[y]
            else:
                data = strip[yy][a:b]
            for sp, ox, oy in ol:
                j = y - oy
                if 0 <= j < sp["h"]:
                    runs = sp["rows"][j]
                    if runs:
                        if type(data) is bytes:
                            data = bytearray(data)
                        for x0, bts in runs:
                            xs = (ox + x0) * 2
                            if xs >= ROWB or xs + len(bts) <= 0:
                                continue
                            if xs < 0:
                                bts = bts[-xs:]
                                xs = 0
                            if xs + len(bts) > ROWB:
                                bts = bts[:ROWB - xs]
                            if bts:
                                data[xs:xs + len(bts)] = bts
            o = (PY0 + y) * S + PX0 * 2
            fb[o:o + ROWB] = data


def make():
    g = Game()
    return g.step
