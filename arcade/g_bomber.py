# Bomberman-style self-playing game. The bot plans in tile steps against a timeline of predicted flames:
# bombs (with chain reactions) are turned into per-cell "flame windows", and every move, wait and bomb
# placement is only taken if a path into a cell that stays safe forever exists inside those windows.
from fbcore import *

D = load_bundle("g_bomber.bin")
CW, CH, TS = 15, 13, 72
N = CW * CH
OX, OY = (W - CW * TS) // 2, (H - CH * TS) // 2
FUSE = 72
FLAME_T = 18
BURN_T = 18
TB = (10, 8, 7, 6)            # ticks per tile for speed levels 0..3
LEVEL_TICKS = 200 * TICK_RATE
MARGIN = 2                    # ticks of slack on both sides of every flame window
ENEMY_HORIZON = 150           # ticks of enemy reach the planner looks at
ENEMY_GAP = 6                 # ticks of slack before an enemy can arrive: its touch radius is 46 px
INF = 1 << 30
TARGET_SCORE = 13000
START_LIVES = 3
LEFT, RIGHT, UP, DOWN = range(4)
DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))     # index == flame-mask bit position
SPR_DIR = (2, 3, 1, 0)                        # DIRS index -> sprite row (d, u, l, r)
STEP = tuple(dy * CW + dx for dx, dy in DIRS)
OPPOSITE = (RIGHT, LEFT, DOWN, UP)
CORNERS = ((1, 1), (13, 1), (1, 11), (13, 11))
WALK_CYCLE = (1, 0, 2, 0)

ENEMY_TICKS = {"balloon": 22, "onil": 17, "dahl": 13, "ovape": 26}
ENEMY_SCORE = {"balloon": 100, "onil": 200, "dahl": 300, "ovape": 400}
CHASE_P = {"balloon": 0.0, "onil": 0.6, "dahl": 0.15, "ovape": 0.5}
THEME_NAMES = ("GARDEN", "DESERT", "ICE", "FACTORY")

NBR = [[] for _ in range(N)]
for _i in range(N):
    _x, _y = _i % CW, _i // CW
    for _d, (_dx, _dy) in enumerate(DIRS):
        if 0 < _x + _dx < CW - 1 and 0 < _y + _dy < CH - 1:
            NBR[_i].append((_i + STEP[_d], _d))


def roster(level):
    table = ({"balloon": 5}, {"balloon": 3, "onil": 2}, {"balloon": 2, "onil": 3, "dahl": 1},
             {"onil": 3, "dahl": 2, "ovape": 1})
    if level <= len(table):
        return table[level - 1]
    return {"balloon": 1, "onil": 2, "dahl": 3, "ovape": min(1 + (level - 4) // 2, 3)}


def blocked(wins, a, b):
    for s, e in wins:
        if s - MARGIN < b and e + MARGIN > a:
            return True
    return False


class Enemy:
    def __init__(self, kind, idx):
        self.kind = kind
        self.x, self.y = idx % CW, idx // CW
        self.nx, self.ny = self.x, self.y
        self.prog = 0
        self.dur = 1
        self.dir = random.choice((LEFT, RIGHT, UP, DOWN))
        self.state = "alive"
        self.dead_t = 0
        self.ghost = kind == "ovape"
        self.speed = ENEMY_TICKS[kind]

    def tile(self):
        return (self.ny * CW + self.nx) if self.prog * 2 >= self.dur else (self.y * CW + self.x)

    def pos(self):
        return (self.x * TS + (self.nx - self.x) * TS * self.prog // self.dur,
                self.y * TS + (self.ny - self.y) * TS * self.prog // self.dur)


class Game:
    def __init__(self):
        self.t = 0
        self.score = 0
        self.lives = START_LIVES
        self.level = 0
        self.bombs_max, self.power, self.speed_lv = 1, 2, 0
        self.phase = "intro"
        self.phase_t = 0
        self.hud_shown = {}
        self.end = EndScreen()
        self.next_level()

    # ---------------------------------------------------------------------------------------------- level setup
    def next_level(self, same=False):
        if not same:
            self.level += 1
        lv = self.level
        self.theme = D["themes"][(lv - 1) % 4]
        grid = [0] * N
        for i in range(N):
            x, y = i % CW, i // CW
            if x in (0, CW - 1) or y in (0, CH - 1) or (x % 2 == 0 and y % 2 == 0):
                grid[i] = 1
        sx, sy = (1, 1) if lv == 1 else random.choice(CORNERS)
        self.start = (sx, sy)
        ix, iy = (1 if sx == 1 else -1), (1 if sy == 1 else -1)
        safe = {(sx, sy), (sx + ix, sy), (sx, sy + iy)}
        density = min(0.34 + 0.02 * lv, 0.42)
        bricks = []
        for i in range(N):
            if grid[i] == 0 and (i % CW, i // CW) not in safe and random.random() < density:
                grid[i] = 2
                bricks.append(i)
        random.shuffle(bricks)
        far = [i for i in bricks if abs(i % CW - sx) + abs(i // CW - sy) >= 8] or bricks
        self.door = far[0]
        self.hidden = {}
        rest = [i for i in bricks if i != self.door]
        loot = ["F", "F", "B", "B", "S"] if lv < 3 else ["F", "B", "S", "F", "B"]
        for i, k in zip(rest, loot):
            self.hidden[i] = k
        self.grid = grid
        self.burn = {}
        self.flames = {}
        self.bombs = []
        self.items = {}
        self.door_open_cell = False
        self.pending_kill = set()
        self.spawn_cooldown = 0
        self.enemies = []
        spots = [i for i in range(N) if grid[i] == 0 and abs(i % CW - sx) + abs(i // CW - sy) >= 7]
        random.shuffle(spots)
        for kind, n in roster(lv).items():
            for _ in range(n):
                if spots:
                    self.enemies.append(Enemy(kind, spots.pop()))
        self.bx, self.by = sx, sy
        self.bnx, self.bny = sx, sy
        self.bprog, self.bdur = 0, TB[self.speed_lv]
        self.bdir = DOWN
        self.bstate = "alive"
        self.btime = 0
        self.invuln = 0
        self.level_t = 0
        self.last_score_t = 0
        self.idle = 0
        self.cur_ewin = {}
        self.shown = {}
        self.dyn_prev = set()
        self.ent_prev = set()
        self.phase = "intro"
        self.phase_t = 0
        self.intro_drawn = False
        for e in self.enemies:
            self.enemy_choose(e)

    # ---------------------------------------------------------------------------------------------- simulation
    def bomber_idx(self):
        return (self.bny * CW + self.bnx) if self.bprog * 2 >= self.bdur else (self.by * CW + self.bx)

    def add_score(self, v):
        self.score += v
        self.last_score_t = self.t

    def detonate(self, first_idx):
        queue = [first_idx]
        seen = set()
        while queue:
            i = queue.pop()
            if i in seen:
                continue
            seen.add(i)
            bomb = next((b for b in self.bombs if b["idx"] == i), None)
            if bomb is None:
                continue
            self.bombs.remove(bomb)
            masks = {i: 0}
            for d in range(4):
                run = []
                for s in range(1, bomb["power"] + 1):
                    c = i + STEP[d] * s
                    g = self.grid[c]
                    if g == 1:
                        break
                    if g in (2, 3):
                        if g == 2:
                            self.grid[c] = 3
                            self.burn[c] = BURN_T
                            self.pending_kill.add(c)
                            self.add_score(10)
                        break
                    run.append(c)
                    if any(b["idx"] == c for b in self.bombs):
                        queue.append(c)
                        break
                if run:
                    masks[i] |= 1 << d
                for k, c in enumerate(run):
                    masks[c] = masks.get(c, 0) | (1 << OPPOSITE[d]) | ((1 << d) if k < len(run) - 1 else 0)
            for c, m in masks.items():
                old = self.flames.get(c)
                self.flames[c] = [FLAME_T, m | (old[1] if old else 0)]
                self.items.pop(c, None)
                if c == self.door and self.door_open_cell and self.spawn_cooldown <= 0 and len(self.enemies) < 14:
                    self.spawn_cooldown = 90
                    self.enemies.append(Enemy(random.choice(("balloon", "onil")), c))
                    self.enemy_choose(self.enemies[-1])

    def world_tick(self):
        if self.spawn_cooldown > 0:
            self.spawn_cooldown -= 1
        for b in list(self.bombs):
            b["fuse"] -= 1
            if b["fuse"] <= 0 and b in self.bombs:
                self.detonate(b["idx"])
        for i in list(self.flames):
            self.flames[i][0] -= 1
            if self.flames[i][0] <= 0:
                del self.flames[i]
        for i in list(self.burn):
            self.burn[i] -= 1
            if self.burn[i] <= 0:
                del self.burn[i]
                self.grid[i] = 0
                if i == self.door:
                    self.door_open_cell = True
                elif i in self.hidden:
                    self.items[i] = self.hidden.pop(i)

    def kill_enemies(self):
        for e in self.enemies:
            if e.state == "alive":
                t = e.tile()
                if t in self.flames or t in self.pending_kill:
                    e.state = "dying"
                    e.dead_t = 0
                    self.add_score(ENEMY_SCORE[e.kind])
        self.pending_kill.clear()

    def enemy_choose(self, e):
        bomb_cells = {b["idx"] for b in self.bombs}
        idx = e.ny * CW + e.nx
        e.x, e.y = e.nx, e.ny
        opts = []
        for n, d in NBR[idx]:
            g = self.grid[n]
            if g == 1 or (g in (2, 3) and not e.ghost) or n in bomb_cells:
                continue
            opts.append((n, d))
        if not opts:
            e.dur, e.prog = 8, 0
            return
        fwd = [o for o in opts if o[1] != OPPOSITE[e.dir]] or opts
        if self.bstate == "alive" and random.random() < CHASE_P[e.kind]:
            tx, ty = self.bx, self.by
            n, d = min(fwd, key=lambda o: abs(o[0] % CW - tx) + abs(o[0] // CW - ty))
        elif any(o[1] == e.dir for o in fwd) and random.random() < 0.75:
            d = e.dir
            n = idx + STEP[d]
        else:
            n, d = random.choice(fwd)
        e.dir = d
        e.nx, e.ny = n % CW, n // CW
        e.prog, e.dur = 0, e.speed

    def enemies_tick(self):
        for e in self.enemies:
            if e.state == "dying":
                e.dead_t += 1
                continue
            e.prog += 1
            if e.prog >= e.dur:
                self.enemy_choose(e)
        self.enemies = [e for e in self.enemies if e.state == "alive" or e.dead_t < 22]

    def alive_enemies(self):
        return [e for e in self.enemies if e.state == "alive"]

    def pickup(self, idx):
        k = self.items.pop(idx, None)
        if k is None:
            return
        self.add_score(50)
        if k == "B":
            self.bombs_max = min(5, self.bombs_max + 1)
        elif k == "F":
            self.power = min(6, self.power + 1)
        else:
            self.speed_lv = min(3, self.speed_lv + 1)

    # ---------------------------------------------------------------------------------------------- bot: prediction
    def predict(self):
        """Flame windows per cell, in ticks from now, including chain reactions and bricks that burn away."""
        win = {}
        for i, fr in self.flames.items():
            win.setdefault(i, []).append((0, fr[0]))
        gone = dict(self.burn)
        pend = {b["idx"]: [b["fuse"], b["power"]] for b in self.bombs}
        done = set()
        while True:
            cand = [(f[0], i) for i, f in pend.items() if i not in done]
            if not cand:
                break
            t, i = min(cand)
            done.add(i)
            win.setdefault(i, []).append((t, t + FLAME_T))
            for d in range(4):
                for s in range(1, pend[i][1] + 1):
                    c = i + STEP[d] * s
                    g = self.grid[c]
                    if g == 1:
                        break
                    if g in (2, 3):
                        if gone.get(c, 1 << 30) <= t:
                            pass
                        else:
                            gone.setdefault(c, t + BURN_T)
                            break
                    if c in pend:
                        if c not in done:
                            pend[c][0] = min(pend[c][0], t)
                        break
                    win.setdefault(c, []).append((t, t + FLAME_T))
        return win

    def enemy_times(self):
        """Earliest tick at which any enemy could stand on each cell: the bomber must be gone before then."""
        times = {}
        for e in self.alive_enemies():
            rem = max(1, e.dur - e.prog)
            front = e.ny * CW + e.nx
            back = e.y * CW + e.x
            # The tile it is leaving still overlaps it right now, so a swap with the bomber is a collision.
            dist = {front: rem}
            if back != front:
                dist[back] = 0
            todo = [front]
            while todo:
                nxt = []
                for c in todo:
                    t = dist[c] + e.dur
                    if t > ENEMY_HORIZON:
                        continue
                    for n, _ in NBR[c]:
                        if n not in dist and self.grid[n] != 1 and (e.ghost or self.grid[n] == 0):
                            dist[n] = t
                            nxt.append(n)
                todo = nxt
            # Contact starts well before the enemy's centre reaches the tile (46 px touch radius, 72 px tiles).
            lead = int(0.7 * e.dur)
            for c, t in dist.items():
                t = max(0, t - lead)
                if t < times.get(c, 1 << 30):
                    times[c] = t
        return times

    def search(self, start, win, ewin, tb, depth, escape_only=False, calm=0):
        half = tb // 2
        parent = {(start, 0): None}
        first = {start: 0}      # cells the bomber can arrive at and also stay on: valid goals
        seen = {start}          # every cell entered at all, goal or not
        cur = {start}
        bomb_cells = {b["idx"] for b in self.bombs}
        quiet_cache = {}

        def quiet(c):
            q = quiet_cache.get(c)
            if q is None:
                q = c not in win and c not in ewin and all(n not in win and n not in ewin for n, _ in NBR[c])
                quiet_cache[c] = q
            return q

        for k in range(depth):
            t0 = k * tb
            nxt = set()
            for c in cur:
                wc = win.get(c)
                ec = ewin.get(c, INF) - ENEMY_GAP
                if not (wc and blocked(wc, t0, t0 + tb)) and ec >= t0 + tb:
                    if not quiet(c) and (c, k + 1) not in parent:
                        nxt.add(c)
                        parent[(c, k + 1)] = (c, k)
                if (wc and blocked(wc, t0, t0 + half)) or (k > 0 and ec < t0 + half):
                    continue
                for n, _ in NBR[c]:
                    if self.grid[n] != 0 or n in bomb_cells or (n, k + 1) in parent:
                        continue
                    wn = win.get(n)
                    if wn and blocked(wn, t0 + half, t0 + tb):
                        continue
                    if ewin.get(n, INF) - ENEMY_GAP < t0 + tb:
                        continue
                    if n in seen and quiet(n):
                        continue
                    nxt.add(n)
                    seen.add(n)
                    parent[(n, k + 1)] = (c, k)
                    # A cell we could enter but not survive on is only a stepping stone, never a destination.
                    if not (wn and any(e + MARGIN > t0 + half for s, e in wn)) \
                            and ewin.get(n, INF) - ENEMY_GAP >= t0 + 2 * tb:
                        first.setdefault(n, k + 1)
                    # calm: a bomb placement also wants the refuge to stay enemy-free for a while after arrival.
                    if escape_only and not (wn and any(e + MARGIN > t0 + half for s, e in wn)) \
                            and ewin.get(n, INF) - ENEMY_GAP >= t0 + tb + calm:
                        return first, parent, (n, k + 1)
            cur = nxt
            if not cur:
                break
        return first, parent, None

    @staticmethod
    def first_step(parent, state):
        # Walk back to the layer-1 state: its cell is the first action (the start cell means "wait").
        while parent[state][1] != 0:
            state = parent[state]
        return state[0]

    def can_escape(self, c, ewin):
        # The hypothetical bomb is registered for real so the walk cannot step back onto its own tile.
        self.place_bomb(c)
        try:
            tb = TB[self.speed_lv]
            _, _, esc = self.search(c, self.predict(), ewin, tb, FUSE // tb + 4, escape_only=True, calm=3 * tb)
        finally:
            self.bombs.pop()
        return esc is not None

    def blast(self, c, power):
        bricks, cells = 0, [c]
        for d in range(4):
            for s in range(1, power + 1):
                n = c + STEP[d] * s
                g = self.grid[n]
                if g == 1 or g == 3:
                    break
                if g == 2:
                    bricks += 1
                    break
                cells.append(n)
                if any(b["idx"] == n for b in self.bombs):
                    break
        return bricks, cells

    def site_value(self, c, enemies):
        bricks, cells = self.blast(c, self.power)
        v = bricks * 12
        cellset = set(cells)
        for e in enemies:
            if e.tile() in cellset:
                v += ENEMY_SCORE[e.kind] // 3 + 20
        for n in cells:
            if n in self.items:
                v -= 50
            if n == self.door and self.door_open_cell:
                v -= 60
        return v

    # ---------------------------------------------------------------------------------------------- bot: decision
    def decide(self):
        """Pick the next tile (or a wait) at a tile centre; returns the target cell index."""
        here = self.by * CW + self.bx
        tb = TB[self.speed_lv]
        win = self.predict()
        soft = self.enemy_times()
        enemies = self.alive_enemies()
        wh = win.get(here)
        self.cur_ewin = soft

        if wh and any(e + MARGIN > 0 for s, e in wh):
            first, parent, esc = self.search(here, win, soft, tb, 14, escape_only=True)
            if esc is None:
                first, parent, esc = self.search(here, win, {}, tb, 14, escape_only=True)
            if esc is None:
                far = max(first.items(), key=lambda kv: kv[1])
                return here if far[0] == here else self.first_step(parent, (far[0], far[1]))
            return self.first_step(parent, esc)

        first, parent, _ = self.search(here, win, soft, tb, 26)
        if len(first) == 1 and soft.get(here, INF) < 4 * tb:
            return self.flee(here, win, enemies)
        bombs_free = self.bombs_max - len(self.bombs)

        if self.door_open_cell and not enemies and self.door in first:
            return self.step_to(self.door, first, parent, here)

        goals = []
        for i in self.items:
            if i in first:
                goals.append((130 - 4 * first[i], i, False))
        sites = []
        if not (here in self.items):
            starving = self.t - self.last_score_t > 20 * TICK_RATE
            for c, k in first.items():
                v = self.site_value(c, enemies)
                if v >= (0 if starving and enemies else 10) and (v >= 30 or not enemies or starving or v >= 10):
                    sites.append((v - 3 * k, c))
            sites.sort(reverse=True)
            checked = 0
            for score, c in sites:
                if checked >= 6:
                    break
                checked += 1
                if c == here and bombs_free <= 0:
                    goals.append((score, c, False))
                    break
                if self.can_escape(c, soft):
                    goals.append((score, c, True))
                    break

        if goals:
            score, target, bomb = max(goals, key=lambda g: g[0])
            if target == here and bomb:
                self.place_bomb(here)
                return self.decide()
            return self.step_to(target, first, parent, here)

        if enemies:
            ex = min(enemies, key=lambda e: abs(e.x - self.bx) + abs(e.y - self.by))
            best = min((c for c in first), key=lambda c: abs(c % CW - ex.x) + abs(c // CW - ex.y) + first[c] * 0.1)
            return self.step_to(best, first, parent, here)
        return here

    def flee(self, here, win, enemies):
        # Boxed in by the enemy zone: take the hard-safe neighbour that ends up farthest from every enemy.
        tb = TB[self.speed_lv]
        bomb_cells = {b["idx"] for b in self.bombs}

        def gap(c):
            return min((abs(c % CW - e.nx) + abs(c // CW - e.ny) + abs(c % CW - e.x) + abs(c // CW - e.y) for e in enemies),
                       default=99)

        best, best_gap = here, gap(here)
        for n, _ in NBR[here]:
            if self.grid[n] != 0 or n in bomb_cells:
                continue
            wn = win.get(n)
            if wn and any(e + MARGIN > tb // 2 for _, e in wn):
                continue
            if gap(n) > best_gap:
                best, best_gap = n, gap(n)
        return best

    def waiting_spot(self, first, here):
        # Idle time is spent on a junction that is far from the enemies: dead ends are where the bomber got cornered.
        bomb_cells = {b["idx"] for b in self.bombs}
        best, best_score = here, None
        for c, k in first.items():
            if k > 6:
                continue
            deg = sum(1 for n, _ in NBR[c] if self.grid[n] == 0 and n not in bomb_cells)
            score = deg * 12 + min(self.cur_ewin.get(c, 200), 200) * 0.25 - k * 4 + (8 if c == here else 0)
            if best_score is None or score > best_score:
                best, best_score = c, score
        return best

    def step_to(self, target, first, parent, here):
        if target == here:
            tb = TB[self.speed_lv]
            if self.cur_ewin.get(here, INF) - ENEMY_GAP < tb:
                # Waiting here would let an enemy walk into us: sidestep to the neighbour it reaches last.
                opts = [n for n, _ in NBR[here] if (n, 1) in parent]
                if opts:
                    return max(opts, key=lambda n: self.cur_ewin.get(n, INF))
                return here
            if self.alive_enemies():
                spot = self.waiting_spot(first, here)
                if spot != here:
                    return self.first_step(parent, (spot, first[spot]))
            self.idle += 1
            if self.idle > 12:
                self.idle = 0
                opts = [n for n, _ in NBR[here] if n in first and first[n] == 1]
                if opts:
                    return random.choice(opts)
            return here
        self.idle = 0
        return self.first_step(parent, (target, first[target]))

    def place_bomb(self, idx):
        self.bombs.append({"idx": idx, "fuse": FUSE, "power": self.power})

    def bomber_arrive(self):
        self.bx, self.by = self.bnx, self.bny
        self.bprog = 0
        idx = self.by * CW + self.bx
        self.pickup(idx)
        if self.door_open_cell and idx == self.door and not self.alive_enemies():
            self.phase = "clear"
            self.phase_t = 0
            return
        tgt = self.decide()
        self.bdur = TB[self.speed_lv]
        if tgt != idx:
            self.bdir = DIRS.index(((tgt % CW) - self.bx, (tgt // CW) - self.by))
        self.bnx, self.bny = tgt % CW, tgt // CW

    def bomber_tick(self):
        self.bprog += 1
        if self.bprog >= self.bdur:
            self.bomber_arrive()

    def check_bomber_death(self):
        if self.bstate != "alive" or self.invuln > 0:
            return
        bi = self.bomber_idx()
        dead = bi in self.flames or bi in self.pending_kill
        if not dead:
            bx = self.bx * TS + (self.bnx - self.bx) * TS * self.bprog // self.bdur
            by = self.by * TS + (self.bny - self.by) * TS * self.bprog // self.bdur
            for e in self.enemies:
                if e.state == "alive":
                    ex, ey = e.pos()
                    if (ex - bx) ** 2 + (ey - by) ** 2 < 46 * 46:
                        dead = True
                        break
        if dead:
            self.bstate = "dying"
            self.btime = 0

    # ---------------------------------------------------------------------------------------------- rendering
    def tile_bytes(self, idx):
        x, y = idx % CW, idx // CW
        v = (x + y) & 1
        g = self.grid[idx]
        if idx in self.flames:
            f = self.flames[idx]
            key = "flame%d_%d_%d" % (f[1], (self.t // 2) % 3, v)
        elif any(b["idx"] == idx for b in self.bombs):
            fuse = next(b["fuse"] for b in self.bombs if b["idx"] == idx)
            if fuse < 26:
                fr = 3 if (self.t // 3) % 2 else 1
            else:
                fr = (0, 1, 0, 2)[(self.t // 5) % 4]
            key = "bomb%d_%d" % (fr, v)
        elif g == 3:
            key = "crumb%d" % min(4, (BURN_T - self.burn[idx]) * 5 // BURN_T)
        elif g == 2:
            key = "brick"
        elif g == 1:
            key = "wall" if x in (0, CW - 1) or y in (0, CH - 1) else "pillar"
        elif idx in self.items:
            key = "item%s%d_%d" % (self.items[idx], (self.t // 10) % 2, v)
        elif idx == self.door and self.door_open_cell:
            key = "door%d_%d" % (1 + (self.t // 8) % 2 if not self.alive_enemies() else 0, v)
        else:
            key = "floor%d" % v
        return self.theme[key]

    def entity_list(self):
        ents = []
        for e in self.enemies:
            px, py = e.pos()
            if e.state == "alive":
                rows = D["enemy"][e.kind]["walk"][SPR_DIR[e.dir]][(self.t // 8) % 2]
            else:
                rows = D["enemy"][e.kind]["die"][min(4, e.dead_t // 4)]
            ents.append((py, rows, px, py))
        bpx = self.bx * TS + (self.bnx - self.bx) * TS * self.bprog // self.bdur
        bpy = self.by * TS + (self.bny - self.by) * TS * self.bprog // self.bdur
        if self.phase == "clear":
            ents.append((bpy, D["win"][(self.phase_t // 8) % 2], bpx, bpy))
        elif self.bstate == "dying":
            ents.append((bpy, D["die"][min(9, self.btime // 5)], bpx, bpy))
        elif self.bstate == "alive" and not (self.invuln > 0 and (self.t // 3) % 2):
            moving = (self.bnx, self.bny) != (self.bx, self.by)
            f = WALK_CYCLE[(self.t // 3) % 4] if moving else 0
            ents.append((bpy, D["walk"][SPR_DIR[self.bdir]][f], bpx, bpy))
        ents.sort(key=lambda e: e[0])
        return [(r, x, y) for _, r, x, y in ents]

    def paint(self, idx, tile, ents):
        cx, cy = idx % CW, idx // CW
        x0, y0 = OX + cx * TS, OY + cy * TS
        if ents:
            buf = bytearray(tile)
            for rows, px, py in ents:
                px += OX
                py += OY
                for ry, runs in rows:
                    ty = py + ry - y0
                    if ty < 0 or ty >= TS:
                        continue
                    base = ty * TS * 2
                    for rx, data in runs:
                        a = px + rx - x0
                        n = len(data) >> 1
                        if a >= TS or a + n <= 0:
                            continue
                        if a < 0:
                            data = data[-a * 2:]
                            a = 0
                        if a * 2 + len(data) > TS * 2:
                            data = data[:TS * 2 - a * 2]
                        buf[base + a * 2:base + a * 2 + len(data)] = data
            tile = buf
        mv = memoryview(tile)
        for r in range(TS):
            o = (y0 + r) * S + x0 * 2
            fb[o:o + TS * 2] = mv[r * TS * 2:(r + 1) * TS * 2]

    def draw_all(self):
        clear()
        self.shown = {}
        tiles = [self.tile_bytes(i) for i in range(N)]
        for cy in range(CH):
            for r in range(TS):
                row = b"".join(tiles[cy * CW + cx][r * TS * 2:(r + 1) * TS * 2] for cx in range(CW))
                write_row(OY + cy * TS + r, row, OX)
        for i in range(N):
            self.shown[i] = (tiles[i], ())
        self.dyn_prev = set()
        self.ent_prev = set()
        self.hud_shown = {}

    def draw_frame(self):
        ents = self.entity_list()
        dyn = set(self.flames) | {b["idx"] for b in self.bombs} | set(self.burn) | set(self.items)
        if self.door_open_cell:
            dyn.add(self.door)
        per_cell = {}
        for ent in ents:
            rows, px, py = ent
            for cy in range(max(0, py // TS), min(CH - 1, (py + TS - 1) // TS) + 1):
                for cx in range(max(0, px // TS), min(CW - 1, (px + TS - 1) // TS) + 1):
                    per_cell.setdefault(cy * CW + cx, []).append(ent)
        ent_cells = set(per_cell)
        for idx in dyn | self.dyn_prev | ent_cells | self.ent_prev:
            tile = self.tile_bytes(idx)
            es = per_cell.get(idx, ())
            sig = (tile, tuple((id(r), x, y) for r, x, y in es))
            if self.shown.get(idx) != sig:
                self.shown[idx] = sig
                self.paint(idx, tile, es)
        self.dyn_prev = dyn
        self.ent_prev = ent_cells

    def hud_value(self, key, text, x, y, size="L", color=COLOR_WHITE):
        if self.hud_shown.get(key) != text:
            self.hud_shown[key] = text
            fill_rect(x, y, 8 * CELL[size][0], CELL[size][1], 0)
            draw_text(text, x, y, size, color, bg=False)

    def draw_hud(self):
        lx, rx = 36, OX + CW * TS + 36
        if not self.hud_shown.get("static"):
            self.hud_shown["static"] = True
            draw_text("SCORE", lx, 120, "S", COLOR_YELLOW)
            draw_text("LIVES", lx, 330, "S", COLOR_YELLOW)
            draw_text("BOMBS", lx, 520, "S", COLOR_CYAN)
            draw_text("FIRE", lx, 620, "S", COLOR_RED)
            draw_text("SPEED", lx, 720, "S", COLOR_GREEN)
            draw_text("STAGE", rx, 120, "S", COLOR_YELLOW)
            draw_text("TIME", rx, 330, "S", COLOR_YELLOW)
            draw_text("WORLD", rx, 520, "S", COLOR_CYAN)
        self.hud_value("score", "%d" % self.score, lx, 166)
        if self.hud_shown.get("lives") != self.lives:
            self.hud_shown["lives"] = self.lives
            fill_rect(lx, 380, 336, 48, 0)
            for i in range(max(0, self.lives)):
                blit(D["head"], lx + i * 56, 380)
        left = max(0, (LEVEL_TICKS - self.level_t) // TICK_RATE)
        self.hud_value("time", "%d:%02d" % (left // 60, left % 60), rx, 376)
        self.hud_value("level", "%d" % self.level, rx, 166)
        self.hud_value("world", THEME_NAMES[(self.level - 1) % 4], rx, 566, "S", COLOR_WHITE)
        for key, y, val, icon in (("b", 560, self.bombs_max, 0), ("f", 660, self.power, 1), ("s", 760, self.speed_lv + 1, 2)):
            if self.hud_shown.get(key) != val:
                self.hud_shown[key] = val
                fill_rect(lx, y, 336, 48, 0)
                for i in range(val):
                    blit(D["icons"][icon], lx + i * 52 if val <= 6 else lx + i * 44, y)

    # ---------------------------------------------------------------------------------------------- flow
    def finish_level_or_game(self):
        if self.score >= TARGET_SCORE:
            self.phase = "end"
            self.end.start(self.score, "ALL CLEAR")
        else:
            self.next_level()

    def step(self):
        self.t += 1
        if self.phase == "end":
            return self.end.tick()
        if self.t >= CAP_TICKS - 5:
            self.phase = "end"
            self.end.start(self.score, "GAME OVER")
            return False
        self.phase_t += 1
        if self.phase == "intro":
            if not self.intro_drawn:
                self.intro_drawn = True
                clear()
                draw_text_centered("STAGE %d" % self.level, 420, "L", COLOR_YELLOW)
                draw_text_centered(THEME_NAMES[(self.level - 1) % 4], 530, "L", COLOR_CYAN)
            elif self.phase_t > 70:
                self.draw_all()
                self.phase = "play"
                self.phase_t = 0
            return False
        if self.phase == "play":
            self.level_t += 1
            self.world_tick()
            self.kill_enemies()
            if self.bstate == "alive":
                self.enemies_tick()
                self.bomber_tick()
                if self.invuln > 0:
                    self.invuln -= 1
                self.check_bomber_death()
                if self.level_t >= LEVEL_TICKS and self.bstate == "alive":
                    self.bstate, self.btime = "dying", 0
            else:
                self.enemies_tick()
                self.btime += 1
                if self.btime > 56:
                    self.lives -= 1
                    if self.lives <= 0:
                        self.draw_frame()
                        self.phase = "end"
                        self.end.start(self.score, "GAME OVER")
                        return False
                    timed_out = self.level_t >= LEVEL_TICKS
                    if timed_out:
                        self.next_level(same=True)
                    else:
                        self.respawn()
            self.pending_kill.clear()
        elif self.phase == "clear":
            self.world_tick()
            if self.phase_t == 1:
                left = max(0, (LEVEL_TICKS - self.level_t) // TICK_RATE)
                self.add_score(1000 + 10 * left)
                self.draw_frame()
                draw_text_centered("STAGE CLEAR", 400, "L", COLOR_YELLOW)
                draw_text_centered("BONUS %d" % (1000 + 10 * left), 500, "L", COLOR_CYAN)
            elif self.phase_t > 110:
                self.finish_level_or_game()
            self.draw_hud()
            return False
        if self.phase == "play":
            self.draw_frame()
            self.draw_hud()
        return False

    def respawn(self):
        sx, sy = self.start
        self.bx, self.by, self.bnx, self.bny = sx, sy, sx, sy
        self.bprog = 0
        self.bdur = TB[self.speed_lv]
        self.bstate = "alive"
        self.invuln = 90


def make():
    g = Game()
    return g.step
