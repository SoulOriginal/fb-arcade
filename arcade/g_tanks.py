# Tanks (Battle City): self-playing run through the real stage layouts with the original enemy mix,
# power-ups and scoring. The field is rendered from a pre-expanded background buffer in 8x8-pixel cells; only
# cells touched by a moving sprite or a changed brick are recomposed and written.
from fbcore import *
import heapq

SC = 5                        # screen pixels per NES pixel
FX, FY = 400, 20              # top-left of the 208x208 NES-pixel field on screen
PX = FX + 208 * SC            # right-hand HUD panel
GREY565 = rgb565(124, 124, 124)
BLACK565 = 0
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))     # up, right, down, left (sprite sets use the same order)
OPPOSITE = (2, 3, 0, 1)

D = load_bundle("g_tanks.bin")
GLYPH, CHARSET = D["glyph"], D["charset"]
STAGE_MAPS, ENEMY_SEQ = D["stage_maps"], D["enemy_seq"]
FOREST_RUNS = D["forest_runs"]

# terrain kinds per 8x8 sub-tile
EMPTY, BRICK, STEEL, WATER, FOREST, ICE, EAGLE = range(7)
SUBS = 26                      # sub-tiles per side
QUARTERS = 52                  # 4x4-pixel brick quarters per side
EAGLE_X, EAGLE_Y = 96, 192
PLAYER_START = (64, 192)
SPAWN_X = (0, 96, 192)
BASE_WALLS = ([(sx, 23) for sx in range(11, 15)] + [(11, sy) for sy in (24, 25)] + [(14, sy) for sy in (24, 25)])
BASE_WALL_SET = frozenset(BASE_WALLS)

ENEMY_SPEED = (1.0, 2.0, 1.5, 1.5)          # pixels per tick (30 ticks/s): basic, fast, power, armor
ENEMY_BULLET = (4, 4, 8, 4)
ENEMY_FIRE = (0.024, 0.03, 0.042, 0.03)       # chance per tick to fire while no bullet is in flight
ENEMY_SCORE = (100, 200, 300, 400)
PLAYER_SPEED = 2
ICE_SLIDE = 7
SHIELD_SPAWN, SHIELD_HELMET = 90, 300
FREEZE_TICKS, SHOVEL_TICKS = 300, 540
SPAWN_STAR_TICKS = 36
STAR_SEQ = (0, 1, 2, 3, 2, 1)
SCORE_TARGET = 15000
START_LIVES = 3
MAX_ON_SCREEN = 4
HOME_ROW = 19
LANE_COST = 10                 # extra path cost per cell in front of an enemy gun
PLAYER_BIAS = 0.15             # share of enemy turns that head for the player
EAGLE_BIAS = 0.3               # share of enemy turns that head for the base
HUNT_RANGE = 250               # Manhattan pixels from the eagle inside which the bot goes after a tank


def text(s, x, y, variant):
    g = GLYPH[variant]
    for i, ch in enumerate(s):
        blit(g[CHARSET.find(ch)], x + i * 40, y)


class Tank:
    __slots__ = ("x", "y", "d", "kind", "hp", "flash", "acc", "dist", "spawn", "bullets", "slide", "shield",
                 "level", "blocked", "cool")

    def __init__(self, x, y, d, kind):
        self.x, self.y, self.d, self.kind = x, y, d, kind
        self.hp = 4 if kind == 3 else 1
        self.flash = False
        self.acc = 0.0
        self.dist = 0
        self.spawn = SPAWN_STAR_TICKS     # > 0 while the spawn sparkle plays; the tank is not yet in the game
        self.bullets = 0
        self.slide = 0
        self.shield = 0
        self.level = 0
        self.blocked = False
        self.cool = 0                    # ticks to wait before the next turn decision: no spinning in place


class Bullet:
    __slots__ = ("x", "y", "d", "speed", "power", "owner", "age")

    def __init__(self, x, y, d, speed, power, owner):
        self.x, self.y, self.d, self.speed, self.power, self.owner = x, y, d, speed, power, owner
        self.age = 0


class Game:
    def __init__(self):
        self.t = 0
        self.score = 0
        self.hi = 20000
        self.lives = START_LIVES
        self.stage = 0
        self.next_life = 20000
        self.p_level = 0              # upgrades survive stages and are lost only with a life
        self.es = EndScreen()
        self.state = "intro"
        self.phase_t = 0
        self.shown = {}
        self.dirty = set()
        self.last_score = None
        self.hud_enemies = -1
        self.hud_lives = -1
        self.start_stage(1)

    # ---- screen furniture ---------------------------------------------------------------------------
    def draw_screen(self):
        clear(GREY565)
        text("HI-SCORE", 40, 60, "grey")
        text("SCORE", 40, 300, "grey")
        text("ENEMY", 40, 520, "grey")
        text("TANKS", 40, 570, "grey")
        text("BATTLE", 40, 860, "white_grey")
        text("CITY", 40, 910, "white_grey")
        self.last_score = None
        self.hud_enemies = -1
        self.hud_lives = -1

    def hud_score(self):
        if self.score > self.hi:
            self.hi = self.score
        key = (self.score, self.hi)
        if key != self.last_score:
            self.last_score = key
            text("%7d" % self.hi, 40, 108, "grey")
            text("%7d" % self.score, 40, 348, "grey")

    def hud_panel(self):
        left = len(self.queue)
        if left != self.hud_enemies:
            for i in range(20):
                x = PX + (8 + 8 * (i % 2)) * SC
                y = FY + (16 + 8 * (i // 2)) * SC
                if i < left:
                    blit(D["hud_enemy"], x, y)
                else:
                    fill_rect(x, y, 8 * SC, 8 * SC, GREY565)
            self.hud_enemies = left
            text("%2d" % left, 40, 620, "grey")
        if self.lives != self.hud_lives:
            self.hud_lives = self.lives
            text("IP", PX + 8 * SC, FY + 136 * SC, "grey")
            blit(D["hud_life"], PX + 8 * SC, FY + 144 * SC)
            text("%d" % max(self.lives, 0), PX + 16 * SC, FY + 144 * SC, "grey")

    def hud_flag(self):
        blit(D["hud_flag"], PX + 8 * SC, FY + 176 * SC)
        text("%2d" % self.stage, PX + 8 * SC, FY + 196 * SC, "grey")

    # ---- stage setup --------------------------------------------------------------------------------
    def start_stage(self, n):
        self.stage = n
        self.t_stage = 0
        self.water_frame = 0
        self.go_y = None
        self.kind = [[EMPTY] * SUBS for _ in range(SUBS)]
        self.bq = [bytearray(QUARTERS) for _ in range(QUARTERS)]
        self.blk = [[False] * SUBS for _ in range(SUBS)]       # blocks tanks
        self.bblk = [[False] * SUBS for _ in range(SUBS)]      # blocks bullets (water does not)
        self.terrain_version = 0
        self.cost_version = None
        rows = STAGE_MAPS[n - 1] if n <= len(STAGE_MAPS) else self.generate_map(n)
        self.load_map(rows)
        self.set_base_walls(False, False)
        for sx, sy in ((12, 24), (13, 24), (12, 25), (13, 25)):
            self.kind[sy][sx] = EAGLE
            self.blk[sy][sx] = self.bblk[sy][sx] = True
        self.eagle_alive = True
        self.build_bg()
        seq = [int(c) for c in ENEMY_SEQ[(n - 1) % 35]]
        self.queue = seq
        self.spawned = 0
        self.spawn_cd = 12
        self.spawn_delay = max(24, (186 - 4 * n) // 2)
        self.enemies = []
        self.bullets = []
        self.effects = []
        self.pu = None
        self.freeze = 0
        self.shovel = 0
        self.kills = [0, 0, 0, 0]
        self.p = None
        self.respawn = 0
        self.spawn_player()
        self.state, self.phase_t = "intro", 0
        self.path = []
        self.path_age = 99
        self.bot_goal_enemy = None
        self.hold = 0
        self.stuck = 0
        self.last_pos = None
        self.spin_hist = []
        self.calm = 0
        self.calm_dir = 0
        self.wander = 0
        self.wander_dir = 0
        self.home_cell = None
        self.shown = {}
        self.dirty = set()
        self.draw_screen()
        self.hud_flag()
        self.hud_score()
        self.hud_panel()
        text("STAGE %2d" % n, FX + 104 * SC - 160, FY + 104 * SC - 20, "grey")

    def load_map(self, rows):
        for by in range(13):
            for bx in range(13):
                code = int(rows[by * 13 + bx], 16)
                if code >= 13:
                    continue
                subs = ((2 * bx, 2 * by), (2 * bx + 1, 2 * by), (2 * bx, 2 * by + 1), (2 * bx + 1, 2 * by + 1))
                if code <= 4:
                    pick, kind = code, BRICK
                elif code <= 9:
                    pick, kind = code - 5, STEEL
                else:
                    pick, kind = 4, (WATER, FOREST, ICE)[code - 10]
                # TL, TR, BL, BR picks: right half, bottom half, left half, top half, everything
                idx = {0: (1, 3), 1: (2, 3), 2: (0, 2), 3: (0, 1), 4: (0, 1, 2, 3)}[pick]
                for i in idx:
                    self.put_terrain(subs[i][0], subs[i][1], kind)
        for sx, sy in ((0, 0), (12, 0), (24, 0), (8, 24), (16, 24)):      # spawn and start squares stay open
            for dx in (0, 1):
                for dy in (0, 1):
                    self.put_terrain(sx + dx, sy + dy, EMPTY)

    def put_terrain(self, sx, sy, kind):
        self.kind[sy][sx] = kind
        full = 1 if kind == BRICK else 0
        for qy in (2 * sy, 2 * sy + 1):
            for qx in (2 * sx, 2 * sx + 1):
                self.bq[qy][qx] = full
        self.blk[sy][sx] = kind in (BRICK, STEEL, WATER, EAGLE)
        self.bblk[sy][sx] = kind in (BRICK, STEEL, EAGLE)
        self.terrain_version += 1

    def set_base_walls(self, steel, redraw=True):
        for sx, sy in BASE_WALLS:
            self.put_terrain(sx, sy, STEEL if steel else BRICK)
            if redraw:
                self.redraw_sub(sx, sy)

    def generate_map(self, n):
        g = [["D"] * 13 for _ in range(13)]
        feats = 13 + n % 6

        def stamp(cells, ch):
            for x, y in cells:
                if 0 <= x < 13 and 0 <= y < 11:
                    g[y][x] = ch
                    if random.random() < 0.8:
                        g[y][12 - x] = ch
        for _ in range(feats):
            r = random.random()
            x, y = random.randrange(0, 7), random.randrange(1, 10)
            if r < 0.34:
                stamp([(x, y + k) for k in range(random.randint(2, 4))], random.choice("4444130"))
            elif r < 0.5:
                stamp([(x + k, y) for k in range(random.randint(2, 4))], "4")
            elif r < 0.62:
                stamp([(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)], "9" if random.random() < 0.5 else "4")
            elif r < 0.74:
                stamp([(x + a, y + b) for a in range(random.randint(1, 3)) for b in range(random.randint(1, 2))], "A")
            elif r < 0.88:
                stamp([(x + a, y + b) for a in range(random.randint(2, 3)) for b in range(random.randint(2, 3))], "B")
            else:
                stamp([(x + a, y + b) for a in range(random.randint(2, 3)) for b in range(random.randint(1, 3))], "C")
        for x in (0, 6, 12):
            g[0][x] = g[1][x] = "D"
        for x in range(4, 9):
            g[12][x] = "D"
        for x in range(5, 8):
            g[11][x] = "D"
        # keep a way from the spawn points to the base: bricks can be shot, water and steel cannot
        for _ in range(60):
            seen, todo = {(0, 0)}, [(0, 0)]
            while todo:
                x, y = todo.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < 13 and 0 <= ny < 13 and (nx, ny) not in seen and g[ny][nx] not in "A9":
                        seen.add((nx, ny))
                        todo.append((nx, ny))
            if (6, 11) in seen and (12, 0) in seen and (0, 12) in seen:
                break
            walls = [(x, y) for y in range(13) for x in range(13) if g[y][x] in "A9"]
            if not walls:
                break
            x, y = random.choice(walls)
            g[y][x] = "D"
        return "".join("".join(r) for r in g)

    # ---- background buffer ----------------------------------------------------------------------------
    def build_bg(self):
        self.bg = [bytearray(208 * SC * 2) for _ in range(208)]
        self.forest = [[self.kind[sy][sx] == FOREST for sx in range(SUBS)] for sy in range(SUBS)]
        self.water_cells = [(sx, sy) for sy in range(SUBS) for sx in range(SUBS) if self.kind[sy][sx] == WATER]
        for sy in range(SUBS):
            for sx in range(SUBS):
                self.paint_sub(sx, sy)
        self.paint_eagle()

    def sub_mask(self, sx, sy):
        bq = self.bq
        a, b = bq[2 * sy], bq[2 * sy + 1]
        return a[2 * sx] | a[2 * sx + 1] << 1 | b[2 * sx] << 2 | b[2 * sx + 1] << 3

    def paint_sub(self, sx, sy):
        k = self.kind[sy][sx]
        if k == EAGLE:
            return
        if k == BRICK:
            rows = D["t_brick"][self.sub_mask(sx, sy)]
        elif k == STEEL:
            rows = D["t_steel"]
        elif k == WATER:
            rows = D["t_water"][self.water_frame]
        elif k == FOREST:
            rows = D["t_forest"]
        elif k == ICE:
            rows = D["t_ice"]
        else:
            rows = D["t_empty"]
        y0 = sy * 8
        w = 8 * SC * 2
        bg = self.bg
        for r in range(8):
            bg[y0 + r][sx * w:sx * w + w] = rows[r]

    def paint_eagle(self):
        rows = D["eagle"][1 if self.eagle_alive else 0]
        for r in range(16):
            self.bg[EAGLE_Y + r][EAGLE_X * 10:EAGLE_X * 10 + 160] = rows[r]
        self.mark(EAGLE_X, EAGLE_Y, 16, 16)

    def redraw_sub(self, sx, sy):
        if self.kind[sy][sx] == BRICK and not self.sub_mask(sx, sy):
            self.put_terrain(sx, sy, EMPTY)
        self.paint_sub(sx, sy)
        self.dirty.add(sy * SUBS + sx)

    def mark(self, x, y, w, h):
        x0, x1 = max(0, x >> 3), min(SUBS - 1, (x + w - 1) >> 3)
        y0, y1 = max(0, y >> 3), min(SUBS - 1, (y + h - 1) >> 3)
        if x1 < x0 or y1 < y0:
            return
        dirty = self.dirty
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                dirty.add(cy * SUBS + cx)

    # ---- compositing ----------------------------------------------------------------------------------
    def compose(self, cy, cx0, cx1, over):
        # One horizontal strip of cells [cx0, cx1) in cell row cy: background rows, sprite runs pasted on top,
        # forest leaves over the sprites, then every row written five times (the 5x pixel scale).
        X0, X1 = cx0 * 8, cx1 * 8
        ys0 = cy * 8
        ox0, ox1 = X0 * 10, X1 * 10
        mine = [d for d in over if d[0] < X1 and d[0] + d[2][0] > X0 and d[1] < ys0 + 8 and d[1] + d[2][1] > ys0]
        fcx = [cx for cx in range(cx0, cx1) if self.forest[cy][cx]] if mine else ()
        bg = self.bg
        base = (FX + X0 * SC) * 2
        for ry in range(8):
            y = ys0 + ry
            line = bg[y][ox0:ox1]
            touched = False
            for dx, dy, spr in mine:
                r = y - dy
                if 0 <= r < spr[1]:
                    for rx, data in spr[2][r]:
                        ax = dx + rx
                        n = len(data) // 10
                        lo, hi = max(ax, X0), min(ax + n, X1)
                        if lo < hi:
                            if lo == ax and hi == ax + n:
                                line[(lo - X0) * 10:(hi - X0) * 10] = data
                            else:
                                line[(lo - X0) * 10:(hi - X0) * 10] = data[(lo - ax) * 10:(hi - ax) * 10]
                            touched = True
            if touched:
                for cx in fcx:
                    for rx, data in FOREST_RUNS[ry]:
                        a = (cx * 8 + rx - X0) * 10
                        line[a:a + len(data)] = data
            o = (FY + y * SC) * S + base
            n = len(line)
            for k in range(SC):
                fb[o:o + n] = line
                o += S

    def flush(self, over):
        if not self.dirty:
            return
        rows = {}
        for c in self.dirty:
            rows.setdefault(c // SUBS, []).append(c % SUBS)
        self.dirty = set()
        for cy, cxs in rows.items():
            cxs.sort()
            start = prev = cxs[0]
            for cx in cxs[1:]:
                if cx != prev + 1:
                    self.compose(cy, start, prev + 1, over)
                    start = cx
                prev = cx
            self.compose(cy, start, prev + 1, over)

    def drawables(self):
        cur = {}
        if self.pu and (self.t // 7) % 2 == 0:
            cur["pu"] = (self.pu[1], self.pu[2], D["powerup"][self.pu[0]])
        flick = (self.t // 5) % 2
        for e in self.enemies:
            if e.spawn:
                spr = D["star"][STAR_SEQ[(SPAWN_STAR_TICKS - e.spawn) // 3 % 6]]
            else:
                if e.kind == 3:
                    variant = 4 if (e.flash and flick) else 4 - e.hp
                else:
                    variant = 1 if (e.flash and flick) else 0
                spr = D["enemy"][e.kind][variant][e.d][(e.dist >> 2) & 1]
            cur[id(e)] = (e.x, e.y, spr)
        p = self.p
        if p:
            if p.spawn:
                cur[id(p)] = (p.x, p.y, D["star"][STAR_SEQ[(SPAWN_STAR_TICKS - p.spawn) // 3 % 6]])
            else:
                cur[id(p)] = (p.x, p.y, D["player"][p.level][p.d][(p.dist >> 2) & 1])
                if p.shield:
                    cur["sh"] = (p.x, p.y, D["shield"][(self.t >> 1) & 1])
        for b in self.bullets:
            spr = D["bullet"][b.d]
            if b.d == 0:
                pos = (b.x - 1, b.y)
            elif b.d == 2:
                pos = (b.x - 1, b.y - 3)
            elif b.d == 1:
                pos = (b.x - 3, b.y - 1)
            else:
                pos = (b.x, b.y - 1)
            cur[id(b)] = (pos[0], pos[1], spr)
        for ef in self.effects:
            frames = ef[2]
            i = min(ef[4] // ef[3], len(frames) - 1)
            cur[id(ef)] = (ef[0], ef[1], frames[i])
        if self.state == "gameover" and self.go_y is not None:
            cur["go"] = (68, int(self.go_y), D["gameover"])
        return cur

    def render(self):
        cur = self.drawables()
        old = self.shown
        for key, v in cur.items():
            o = old.get(key)
            if o is None or o[0] != v[0] or o[1] != v[1] or o[2] is not v[2]:
                if o is not None:
                    self.mark(o[0], o[1], o[2][0], o[2][1])
                self.mark(v[0], v[1], v[2][0], v[2][1])
        for key, o in old.items():
            if key not in cur:
                self.mark(o[0], o[1], o[2][0], o[2][1])
        self.shown = cur
        self.flush(list(cur.values()))

    # ---- movement and collision -----------------------------------------------------------------------
    def terrain_ok(self, nx, ny):
        if nx < 0 or ny < 0 or nx > 192 or ny > 192:
            return False
        blk = self.blk
        for sy in range(ny >> 3, ((ny + 15) >> 3) + 1):
            row = blk[sy]
            for sx in range(nx >> 3, ((nx + 15) >> 3) + 1):
                if row[sx]:
                    return False
        return True

    def can_place(self, t, nx, ny):
        if not self.terrain_ok(nx, ny):
            return False
        for o in self.enemies:
            if o is not t and abs(nx - o.x) < 16 and abs(ny - o.y) < 16:
                if abs(nx - o.x) + abs(ny - o.y) < abs(t.x - o.x) + abs(t.y - o.y) or \
                        not (abs(t.x - o.x) < 16 and abs(t.y - o.y) < 16):
                    return False
        p = self.p
        if p is not None and p is not t and abs(nx - p.x) < 16 and abs(ny - p.y) < 16:
            if abs(nx - p.x) + abs(ny - p.y) < abs(t.x - p.x) + abs(t.y - p.y) or \
                    not (abs(t.x - p.x) < 16 and abs(t.y - p.y) < 16):
                return False
        return True

    def turn(self, t, d):
        if d == t.d:
            return
        if (d & 1) != (t.d & 1):
            # tanks always sit on the 8-pixel grid across their axis of travel
            if d & 1:
                ay = (t.y + 4) >> 3 << 3
                if ay != t.y:
                    if not self.can_place(t, t.x, ay):
                        return
                    t.y = ay
            else:
                ax = (t.x + 4) >> 3 << 3
                if ax != t.x:
                    if not self.can_place(t, ax, t.y):
                        return
                    t.x = ax
        t.d = d

    def move(self, t, d, steps):
        dx, dy = DIRS[d]
        moved = 0
        for _ in range(steps):
            nx, ny = t.x + dx, t.y + dy
            if not self.can_place(t, nx, ny):
                break
            t.x, t.y = nx, ny
            moved += 1
        t.dist += moved
        return moved

    def on_ice(self, t):
        return self.kind[(t.y + 8) >> 3][(t.x + 8) >> 3] == ICE

    # ---- bullets ----------------------------------------------------------------------------------------
    def fire(self, t, speed, power, owner):
        x, y = t.x, t.y
        if t.d == 0:
            bx, by = x + 8, y
        elif t.d == 1:
            bx, by = x + 15, y + 8
        elif t.d == 2:
            bx, by = x + 8, y + 15
        else:
            bx, by = x, y + 8
        t.bullets += 1
        self.bullets.append(Bullet(bx, by, t.d, speed, power, owner))

    def boom_small(self, x, y):
        self.effects.append([x - 8, y - 8, D["boom_small"], 3, 0, 9])

    def boom_big(self, cx, cy):
        self.effects.append([cx - 16, cy - 16, D["boom_big"], 5, 0, 15])

    def popup(self, cx, cy, value):
        spr = D["popup"][value]
        self.effects.append([min(max(cx - spr[0] // 2, 0), 208 - spr[0]), cy - 4, [spr], 99, 0, 24])

    def bullet_terrain(self, b):
        # Probes span 10 pixels across the line of flight, like the original; every brick quarter found in the
        # tip layer is cleared, steel only gives way to a fully upgraded shot.
        x, y, d = b.x, b.y, b.d
        if d & 1:
            qx = x >> 2
            if not 0 <= qx < QUARTERS:
                return False
            qs = sorted({(y - 5) >> 2, (y - 1) >> 2, y >> 2, (y + 4) >> 2})
            cells = [(qx, q) for q in qs if 0 <= q < QUARTERS]
        else:
            qy = y >> 2
            if not 0 <= qy < QUARTERS:
                return False
            qs = sorted({(x - 5) >> 2, (x - 1) >> 2, x >> 2, (x + 4) >> 2})
            cells = [(q, qy) for q in qs if 0 <= q < QUARTERS]
        hit = False
        touched = set()
        for qx, qy in cells:
            sx, sy = qx >> 1, qy >> 1
            k = self.kind[sy][sx]
            if k == EAGLE:
                self.kill_eagle()
                return True
            if k == BRICK and self.bq[qy][qx]:
                hit = True
                self.bq[qy][qx] = 0
                touched.add((sx, sy))
                if b.power >= 3:
                    nqx, nqy = qx + (DIRS[d][0]), qy + (DIRS[d][1])
                    if 0 <= nqx < QUARTERS and 0 <= nqy < QUARTERS and self.bq[nqy][nqx]:
                        self.bq[nqy][nqx] = 0
                        touched.add((nqx >> 1, nqy >> 1))
            elif k == STEEL:
                hit = True
                if b.power >= 3:
                    self.put_terrain(sx, sy, EMPTY)
                    touched.add((sx, sy))
        for sx, sy in touched:
            self.redraw_sub(sx, sy)
        if touched:
            self.terrain_version += 1
        return hit

    def update_bullets(self):
        dead = []
        bullets = self.bullets
        for b in list(bullets):
            if b in dead:
                continue
            b.age += 1
            dx, dy = DIRS[b.d]
            for _ in range(b.speed // 2):
                b.x += 2 * dx
                b.y += 2 * dy
                if not (0 <= b.x < 208 and 0 <= b.y < 208):
                    b.x = min(max(b.x, 0), 207)
                    b.y = min(max(b.y, 0), 207)
                    self.boom_small(b.x, b.y)
                    dead.append(b)
                    break
                if self.bullet_terrain(b):
                    self.boom_small(b.x, b.y)
                    dead.append(b)
                    break
                if b.owner is self.p:
                    hit = None
                    for e in self.enemies:
                        if not e.spawn and e.x - 1 <= b.x <= e.x + 16 and e.y - 1 <= b.y <= e.y + 16:
                            hit = e
                            break
                    if hit is not None:
                        self.damage_enemy(hit)
                        dead.append(b)
                        break
                    other = [o for o in bullets if o is not b and o.owner is not self.p and o not in dead
                             and abs(o.x - b.x) < 6 and abs(o.y - b.y) < 6]
                    if other:
                        dead.append(b)
                        dead.append(other[0])
                        break
                else:
                    p = self.p
                    if p is not None and not p.spawn and p.x - 1 <= b.x <= p.x + 16 and p.y - 1 <= b.y <= p.y + 16:
                        if not p.shield:
                            self.kill_player()
                        dead.append(b)
                        break
        for b in set(dead):
            if b in bullets:
                bullets.remove(b)
                b.owner.bullets -= 1

    # ---- combat results ----------------------------------------------------------------------------------
    def damage_enemy(self, e):
        if e.flash:
            e.flash = False
            self.drop_powerup()
        e.hp -= 1
        if e.hp <= 0:
            self.destroy_enemy(e, True)

    def destroy_enemy(self, e, by_bullet):
        if e in self.enemies:
            self.enemies.remove(e)
        self.boom_big(e.x + 8, e.y + 8)
        self.score += ENEMY_SCORE[e.kind]
        self.popup(e.x + 8, e.y + 8, ENEMY_SCORE[e.kind])
        if by_bullet:
            self.kills[e.kind] += 1
        for b in [b for b in self.bullets if b.owner is e]:
            self.bullets.remove(b)
        self.check_life()

    def check_life(self):
        if self.score >= self.next_life:
            self.next_life += 20000
            self.lives += 1

    def drop_powerup(self):
        grid = (16, 64, 112, 160)
        self.pu = [random.choice((0, 0, 0, 1, 2, 2, 3, 4, 5)), random.choice(grid), random.choice(grid)]

    def kill_player(self):
        p = self.p
        self.boom_big(p.x + 8, p.y + 8)
        for b in [b for b in self.bullets if b.owner is p]:
            self.bullets.remove(b)
        self.p = None
        self.p_level = 0
        self.lives -= 1
        if self.lives <= 0:
            self.begin_gameover()
        else:
            self.respawn = 45

    def kill_eagle(self):
        if not self.eagle_alive:
            return
        self.eagle_alive = False
        self.boom_big(EAGLE_X + 8, EAGLE_Y + 8)
        self.paint_eagle()
        self.begin_gameover()

    def begin_gameover(self):
        if self.state != "gameover":
            self.state = "gameover"
            self.phase_t = 0
            self.go_y = 208.0

    def spawn_player(self):
        p = Tank(PLAYER_START[0], PLAYER_START[1], 0, -1)
        p.level = self.p_level
        p.shield = SHIELD_SPAWN + SPAWN_STAR_TICKS
        self.p = p

    def collect(self):
        p, pu = self.p, self.pu
        if p is None or pu is None or p.spawn:
            return
        if abs(p.x - pu[1]) < 13 and abs(p.y - pu[2]) < 13:
            kind = pu[0]
            self.pu = None
            self.score += 500
            self.popup(pu[1] + 8, pu[2] + 8, 500)
            self.mark(pu[1], pu[2], 16, 16)
            if kind == 0:
                p.level = min(3, p.level + 1)
                self.p_level = p.level
            elif kind == 1:
                for e in list(self.enemies):
                    if not e.spawn:
                        self.destroy_enemy(e, False)
            elif kind == 2:
                p.shield = SHIELD_HELMET
            elif kind == 3:
                self.shovel = SHOVEL_TICKS
                self.set_base_walls(True)
            elif kind == 4:
                self.lives += 1
            else:
                self.freeze = FREEZE_TICKS
            self.check_life()

    def timers(self):
        p = self.p
        if p is not None and p.shield:
            p.shield -= 1
        if self.freeze:
            self.freeze -= 1
        if self.shovel:
            self.shovel -= 1
            if self.shovel == 0:
                self.set_base_walls(False)
            elif self.shovel < 90 and self.shovel % 10 == 0:
                self.set_base_walls((self.shovel // 10) % 2 == 0)
        if self.t % 24 == 0 and self.water_cells:
            self.water_frame ^= 1
            for sx, sy in self.water_cells:
                self.paint_sub(sx, sy)
                self.dirty.add(sy * SUBS + sx)
        for ef in self.effects:
            ef[4] += 1
        self.effects = [ef for ef in self.effects if ef[4] < ef[5]]

    # ---- enemies ----------------------------------------------------------------------------------------------
    def spawn_enemy(self):
        self.spawn_cd -= 1
        if self.spawn_cd > 0 or not self.queue or len(self.enemies) >= MAX_ON_SCREEN:
            return
        order = [(self.spawned + i) % 3 for i in range(3)]
        for pt in order:
            x = SPAWN_X[pt]
            clear_spot = True
            for o in self.enemies + ([self.p] if self.p else []):
                if abs(o.x - x) < 16 and o.y < 16:
                    clear_spot = False
            if clear_spot:
                kind = self.queue.pop(0)
                e = Tank(x, 0, 2, kind)
                e.flash = self.spawned in (3, 10, 17)
                self.spawned += 1
                self.enemies.append(e)
                self.spawn_cd = self.spawn_delay
                return
        self.spawn_cd = 4

    def enemy_choose_dir(self, t):
        r = random.random()
        p = self.p
        if r < EAGLE_BIAS:
            tx, ty = EAGLE_X, EAGLE_Y
        elif r < EAGLE_BIAS + PLAYER_BIAS and p is not None:
            tx, ty = p.x, p.y
        else:
            return random.randrange(4)
        dx, dy = tx - t.x, ty - t.y
        vert = 2 if dy > 0 else 0
        horiz = 1 if dx > 0 else 3
        if dx == 0:
            return vert
        if dy == 0:
            return horiz
        first, second = (vert, horiz) if abs(dy) >= abs(dx) else (horiz, vert)
        return first if random.random() < 0.7 else second

    def step_free(self, t, d):
        return self.can_place(t, t.x + DIRS[d][0], t.y + DIRS[d][1])

    def enemy_turn(self, e):
        # Only directions that lead somewhere: picking a blocked one every tick made tanks spin on the spot.
        free = [d for d in range(4) if d != e.d and self.step_free(e, d)]
        if not free:
            e.cool = 15
            return
        nd = self.enemy_choose_dir(e)
        if nd not in free:
            nd = random.choice(free)
        self.turn(e, nd)
        e.cool = 4

    def update_enemies(self):
        frozen = self.freeze > 0
        for e in self.enemies:
            if e.spawn:
                e.spawn -= 1
                continue
            if frozen:
                continue
            if e.cool:
                e.cool -= 1
            e.acc += ENEMY_SPEED[e.kind]
            steps = int(e.acc)
            e.acc -= steps
            for _ in range(steps):
                if not self.move(e, e.d, 1):
                    # only a wall justifies the hail of shots; a tank in the way is just a traffic jam
                    e.blocked = not self.terrain_ok(e.x + DIRS[e.d][0], e.y + DIRS[e.d][1])
                    if e.cool:
                        pass
                    elif not e.blocked:
                        e.cool = 12                  # another tank is in the way: wait for it instead of turning round
                    elif e.x & 7 == 0 and e.y & 7 == 0:
                        self.enemy_turn(e)
                    elif random.random() < 0.3:
                        e.d = OPPOSITE[e.d]          # off the grid a sideways turn is impossible, backing out is not
                        e.cool = 6
                    break
                e.blocked = False
                if e.x & 7 == 0 and e.y & 7 == 0 and random.random() < 0.1:
                    self.turn(e, self.enemy_choose_dir(e))
            if e.bullets == 0:
                prob = ENEMY_FIRE[e.kind]
                if e.blocked:
                    prob *= 2
                elif self.p is not None and not self.p.spawn and self.aligned_facing(e, self.p):
                    prob *= 1.5
                if random.random() < prob:
                    self.fire(e, ENEMY_BULLET[e.kind], 1 if e.kind == 2 else 0, e)

    def aligned_facing(self, e, p):
        if e.d & 1 == 0:
            return abs(e.x - p.x) < 12 and ((e.d == 2 and p.y > e.y) or (e.d == 0 and p.y < e.y))
        return abs(e.y - p.y) < 12 and ((e.d == 1 and p.x > e.x) or (e.d == 3 and p.x < e.x))

    # ---- player -------------------------------------------------------------------------------------------------
    def update_player(self, want_dir, want_fire):
        p = self.p
        if p is None:
            if self.respawn:
                self.respawn -= 1
                if self.respawn == 0 and self.free_start():
                    self.spawn_player()
                elif self.respawn == 0:
                    self.respawn = 3
            return
        if p.spawn:
            p.spawn -= 1
            return
        moved = 0
        if want_dir is not None:
            self.turn(p, want_dir)
            moved = self.move(p, want_dir, PLAYER_SPEED)
            p.slide = ICE_SLIDE if self.on_ice(p) else 0
        elif p.slide:
            p.slide -= 1
            if not self.move(p, p.d, PLAYER_SPEED):
                p.slide = 0
        if want_fire and p.bullets < (2 if p.level >= 2 else 1):
            self.fire(p, 4 if p.level == 0 else 8, 3 if p.level == 3 else 1, p)

    def free_start(self):
        for o in self.enemies:
            if abs(o.x - PLAYER_START[0]) < 16 and abs(o.y - PLAYER_START[1]) < 16:
                return False
        return True

    # ---- bot: navigation helpers --------------------------------------------------------------------------------
    def cell_costs(self):
        steel_ok = self.p is not None and self.p.level >= 3
        if self.cost_version == (self.terrain_version, steel_ok):
            return
        self.cost_version = (self.terrain_version, steel_ok)
        kind = self.kind
        cost = [0] * 625
        for gy in range(25):
            for gx in range(25):
                c = 2
                for sx, sy in ((gx, gy), (gx + 1, gy), (gx, gy + 1), (gx + 1, gy + 1)):
                    k = kind[sy][sx]
                    if (sx, sy) in BASE_WALL_SET:      # even a breached base wall is not a way through
                        c = 0
                        break
                    if k == BRICK:
                        c += 5
                    elif k == STEEL:
                        if not steel_ok:
                            c = 0
                            break
                        c += 9
                    elif k in (WATER, EAGLE):
                        c = 0
                        break
                    elif k == ICE:
                        c += 1
                cost[gy * 25 + gx] = c
        self.cost = cost
        self.home_cell = self.nearest_open(12, HOME_ROW)

    def nearest_open(self, tx, ty):
        best = None
        for gy in range(25):
            for gx in range(25):
                if self.cost[gy * 25 + gx] == 2:
                    score = abs(gx - tx) + abs(gy - ty)
                    if best is None or score < best[0]:
                        best = (score, gx, gy)
        return (best[1], best[2]) if best else (8, 24)

    def dijkstra(self, start, extra):
        cost = self.cost
        dist = [9999] * 625
        par = [-1] * 625
        dist[start] = 0
        heap = [(0, start)]
        pop, push = heapq.heappop, heapq.heappush
        while heap:
            d0, u = pop(heap)
            if d0 > dist[u]:
                continue
            ux = u % 25
            for v, ok in ((u - 25, u >= 25), (u + 25, u < 600), (u - 1, ux > 0), (u + 1, ux < 24)):
                if ok:
                    c = cost[v]
                    if c:
                        c += extra[v]
                        if d0 + c < dist[v]:
                            dist[v] = d0 + c
                            par[v] = u
                            push(heap, (d0 + c, v))
        return dist, par

    def lane_clear(self, x, y, d, dist):
        dx, dy = DIRS[d]
        bb = self.bblk
        for s in range(0, max(dist, 0) + 1, 4):
            px, py = x + dx * s, y + dy * s
            if not (0 <= px < 208 and 0 <= py < 208):
                return True
            if bb[py >> 3][px >> 3]:
                return False
        return True

    # ---- bot: decisions ------------------------------------------------------------------------------------------
    def reach(self, b):
        # How far (pixels) a bullet flies before a wall or the field edge stops it.
        dx, dy = DIRS[b.d]
        bb = self.bblk
        for s in range(0, 260, 4):
            px, py = b.x + dx * s, b.y + dy * s
            if not (0 <= px < 208 and 0 <= py < 208) or bb[py >> 3][px >> 3]:
                return s
        return 260

    def danger_infos(self, p, with_ghosts, reaction):
        # Enemy bullets, plus the shots a tank that could fire right now would send. A human needs about
        # 100 ms to notice a fresh bullet (reaction), but never walks into a lane he is already watching.
        infos = []
        for b in self.bullets:
            if b.owner is not p and (b.age >= 3 or not reaction):
                infos.append((b, self.reach(b)))
        if with_ghosts and self.hold < 60 and not self.freeze:
            for e in self.enemies:
                if e.spawn or e.bullets or abs(e.x - p.x) + abs(e.y - p.y) > 130:
                    continue
                muzzle = (e.x + 8 + DIRS[e.d][0] * 8, e.y + 8 + DIRS[e.d][1] * 8)
                ghost = Bullet(muzzle[0], muzzle[1], e.d, 4, 0, e)
                infos.append((ghost, self.reach(ghost)))
        return infos

    def unsafe_time(self, p, d, infos, horizon=18):
        # First tick at which a hull that keeps moving along d (None: stands still) meets one of the bullets.
        x, y = p.x, p.y
        for t in range(1, horizon + 1):
            if d is not None:
                nx, ny = x + DIRS[d][0] * PLAYER_SPEED, y + DIRS[d][1] * PLAYER_SPEED
                if self.can_place(p, nx, ny):
                    x, y = nx, ny
            for b, reach in infos:
                trav = b.speed * t
                if trav <= reach:
                    bx, by = b.x + DIRS[b.d][0] * trav, b.y + DIRS[b.d][1] * trav
                    if x - 1 <= bx <= x + 16 and y - 1 <= by <= y + 16:
                        return t
        return None

    def bot(self):
        p = self.p
        if p is None or p.spawn:
            return None, False
        can_fire = p.bullets < (2 if p.level >= 2 else 1)
        self.spin_check(p)
        if self.calm:
            self.calm -= 1
            want, fire = self.calm_dir, False
        else:
            want, fire = self.desire(p, can_fire)
        # shooting first beats ducking: a tank we are about to hit does not count as a threat
        infos = self.danger_infos(p, not (fire and want is None), want is None)
        if not infos:
            self.hold = 0
            return want, fire
        self.hold += 1
        if self.unsafe_time(p, want, infos) is None:
            return want, fire
        # a head-on bullet can be shot out of the air
        if can_fire:
            for b, _ in infos:
                if p.d == OPPOSITE[b.d] and b.age >= 3:
                    off = (b.x - (p.x + 8)) if b.d & 1 == 0 else (b.y - (p.y + 8))
                    gap = abs(b.y - p.y) if b.d & 1 == 0 else abs(b.x - p.x)
                    mx, my = p.x + 8 + DIRS[p.d][0] * 8, p.y + 8 + DIRS[p.d][1] * 8
                    if abs(off) < 6 and gap > 3 * b.speed and self.unsafe_time(p, None, infos) is not None \
                            and not self.points_at_base(mx, my, p.d):
                        return None, True
        options = [want, None] if want is not None else [None]
        options += [d for d in range(4) if d != want]
        # A direction into a wall only turns the hull on the spot: dodging that way looked like spinning.
        options = [d for d in options if d is None or d == want or self.step_free(p, d)]
        best, best_t = None, -1
        for d in options:
            t = self.unsafe_time(p, d, infos)
            if t is None:
                return d, False
            if t > best_t:
                best, best_t = d, t
        return best, False

    def spin_check(self, p):
        # Turning back and forth without getting anywhere looks broken: when it happens, walk off in a direction
        # that is actually open for a moment, then let the planner take over again.
        h = self.spin_hist
        h.append((p.x, p.y, p.d))
        if len(h) > 24:
            h.pop(0)
        if len(h) < 24:
            return
        moved = abs(h[-1][0] - h[0][0]) + abs(h[-1][1] - h[0][1])
        turns = sum(1 for a, b in zip(h, h[1:]) if a[2] != b[2])
        if moved <= 2 and turns >= 4:
            tried = {x[2] for x in h}
            open_dirs = [d for d in range(4) if self.step_free(p, d)]
            fresh = [d for d in open_dirs if d not in tried]
            choice = fresh or open_dirs
            if choice:
                self.calm_dir = random.choice(choice)
                self.calm = 14
                self.path = []
                self.path_age = 99
            del h[:]

    def desire(self, p, can_fire):
        # What the bot would do with nobody shooting at it: take a clean shot, otherwise walk the plan.
        target = self.shot_target(p)
        if target is not None:
            if can_fire:
                return (None, True) if p.d == target else (target, False)
            return None, False
        d = self.navigate(p)
        if d is not None and p.d == d and can_fire and \
                not self.can_place(p, p.x + DIRS[d][0], p.y + DIRS[d][1]) and self.wall_worth_shooting(p):
            return d, True
        return d, False

    def wall_worth_shooting(self, p):
        # The wall straight ahead of the muzzle, but never the base walls or the eagle behind them.
        dx, dy = DIRS[p.d]
        mx, my = p.x + 8 + dx * 8, p.y + 8 + dy * 8
        for s in range(0, 16, 4):
            px, py = mx + dx * s, my + dy * s
            if not (0 <= px < 208 and 0 <= py < 208):
                return False
            sx, sy = px >> 3, py >> 3
            if self.bblk[sy][sx]:
                k = self.kind[sy][sx]
                return (sx, sy) not in BASE_WALL_SET and (k == BRICK or (k == STEEL and p.level >= 3))
        return False

    def shot_target(self, p):
        # Direction to turn to (or keep) for a shot that should connect, judged from where the hull will sit
        # after the turn (turning across the current axis snaps the tank to the 8-pixel grid) and where the
        # enemy will be when the bullet gets there.
        best = None
        bullet_speed = 4 if p.level == 0 else 8
        moving = self.freeze == 0
        for e in self.enemies:
            for d in range(4):
                vertical = d & 1 == 0
                px, py = p.x, p.y
                if p.d & 1 != d & 1:
                    if vertical:
                        px = (px + 4) >> 3 << 3
                    else:
                        py = (py + 4) >> 3 << 3
                ex, ey = e.x, e.y
                if e.spawn:
                    # a tank cannot be hurt while it sparkles: time the shot to land just as the sparkle ends
                    flight = (abs(ex - px) + abs(ey - py)) / bullet_speed
                    if not e.spawn - 1 <= flight <= e.spawn + 6:
                        continue
                elif moving and not e.blocked:
                    flight = (abs(ex - px) + abs(ey - py)) / bullet_speed
                    ex += DIRS[e.d][0] * ENEMY_SPEED[e.kind] * flight
                    ey += DIRS[e.d][1] * ENEMY_SPEED[e.kind] * flight
                dx, dy = ex - px, ey - py
                cross, along = (dx, dy) if vertical else (dy, dx)
                if abs(cross) > 6 or (along > 0) != (d in (1, 2)) or abs(along) < 4:
                    continue
                dist = abs(along)
                tip = (px + 8 + (0 if vertical else (8 if d == 1 else -8)),
                       py + 8 + ((8 if d == 2 else -8) if vertical else 0))
                # past the target the bullet flies on: toward the base only point-blank at a tank that is really there
                now = (e.x - px, e.y - py) if vertical else (e.y - py, e.x - px)
                safe = not self.points_at_base(tip[0], tip[1], d) or (abs(now[0]) <= 6 and 4 <= abs(now[1]) <= 28)
                if dist <= 170 and safe and self.lane_clear(tip[0], tip[1], d, int(dist) - 8):
                    if best is None or dist < best[0]:
                        best = (dist, d)
        return best[1] if best else None

    def points_at_base(self, x, y, d):
        # A bullet that misses its target flies on; one that would end in the base walls (its 10-pixel swath
        # counts, not just the centre line) must not be fired.
        dx, dy = DIRS[d]
        for s in range(0, 260, 4):
            for off in (-5, 0, 4):
                px, py = (x + dx * s, y + dy * s + off) if dx else (x + dx * s + off, y + dy * s)
                if not (0 <= px < 208 and 0 <= py < 208):
                    continue
                sx, sy = px >> 3, py >> 3
                if self.bblk[sy][sx]:
                    if (sx, sy) in BASE_WALL_SET or self.kind[sy][sx] == EAGLE:
                        return True
                    if off == 0:
                        return False
            cx, cy = x + dx * s, y + dy * s
            if not (0 <= cx < 208 and 0 <= cy < 208):
                return False
        return False

    def cell_of(self, x, y):
        return min(max((x + 4) >> 3, 0), 24), min(max((y + 4) >> 3, 0), 24)

    def navigate(self, p):
        self.cell_costs()
        self.stuck_check(p)
        if self.wander:
            self.wander -= 1
            return self.wander_dir
        self.path_age += 1
        close = any(not e.spawn and abs(e.x - p.x) + abs(e.y - p.y) < 56 for e in self.enemies)
        if self.path_age >= (2 if close else 6) or not self.path:
            self.plan(p)
        return self.follow(p)

    def stuck_check(self, p):
        pos = (p.x, p.y)
        if pos == self.last_pos:
            self.stuck += 1
        else:
            self.stuck = 0
        self.last_pos = pos
        if self.stuck > 45:
            self.stuck = 0
            self.wander = 14
            self.wander_dir = random.randrange(4)
            self.path = []
            self.path_age = 99

    def plan(self, p):
        self.path_age = 0
        gx, gy = self.cell_of(p.x, p.y)
        start = gy * 25 + gx
        extra = [0] * 625
        for e in self.enemies:
            if e.spawn:
                continue
            ex, ey = self.cell_of(e.x, e.y)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if 0 <= ex + dx < 25 and 0 <= ey + dy < 25:
                        extra[(ey + dy) * 25 + ex + dx] += 10
            # the muzzle's lane is three cells wide; right in front of the gun it is deadly
            sx_, sy_ = DIRS[e.d]
            for k in range(1, 9):
                fx, fy = ex + sx_ * k, ey + sy_ * k
                if not (0 <= fx < 25 and 0 <= fy < 25) or self.bblk[fy + 1][fx + 1]:
                    break
                for w in (-1, 0, 1):
                    wx, wy = (fx + w, fy) if sx_ == 0 else (fx, fy + w)
                    if 0 <= wx < 25 and 0 <= wy < 25:
                        extra[wy * 25 + wx] += (LANE_COST if k <= 4 else 4) if w == 0 else (LANE_COST // 2 if k <= 4 else 2)
        dist, par = self.dijkstra(start, extra)
        goal, best = None, 9999
        # The base is what matters: tanks that have not come down yet are left to come to us.
        enemies = [e for e in self.enemies if not e.spawn and abs(e.x - EAGLE_X) + abs(e.y - EAGLE_Y) <= HUNT_RANGE]
        near_eagle = min([abs(e.x - EAGLE_X) + abs(e.y - EAGLE_Y) for e in enemies] or [999])
        threats = [e for e in enemies if self.threatens_base(e)]
        if threats:
            enemies = threats
        if self.pu:
            c = (self.pu[2] >> 3) * 25 + (self.pu[1] >> 3)
            if dist[c] < 9999 and (near_eagle > 70 or dist[c] < 20) and dist[c] < 140:
                goal, best = c, dist[c] - 30
        for e in enemies:
            ex, ey = self.cell_of(e.x, e.y)
            danger = max(0, 28 - (abs(ex - 12) + abs(ey - 24))) * 0.7
            bonus = 3 if e is self.bot_goal_enemy else 0
            # aim at where the tank will be by the time we arrive, not where it is now
            away = dist[ey * 25 + ex]
            lead = min(6, int((away if away < 9999 else 40) / 2 * ENEMY_SPEED[e.kind] / PLAYER_SPEED))
            lx0, ly0 = ex, ey
            for _ in range(lead):
                nx, ny = lx0 + DIRS[e.d][0], ly0 + DIRS[e.d][1]
                if not (0 <= nx < 25 and 0 <= ny < 25) or self.cost[ny * 25 + nx] == 0:
                    break
                lx0, ly0 = nx, ny
            for d in range(4):
                dx, dy = DIRS[d]
                for k in range(1, 10):
                    cx, cy = lx0 + dx * k, ly0 + dy * k
                    lx, ly = cx + 1, cy + 1        # sub-tile under the hull centre: the line of fire
                    if not (0 <= cx < 25 and 0 <= cy < 25) or self.bblk[ly][lx]:
                        break
                    c = cy * 25 + cx
                    if self.cost[c] == 0:
                        break
                    if k < 2 or dist[c] >= 9999:
                        continue
                    score = dist[c] - danger - bonus + abs(k - 4) * 0.5
                    if d == e.d:
                        score += 5
                    if cy <= 3:
                        score += 14        # the spawn corners are a shooting gallery
                    if score < best:
                        best, goal = score, c
                        self.bot_goal_enemy = e
        if goal is None:
            ix, iy = self.home_cell
            goal = iy * 25 + ix
            self.bot_goal_enemy = None
            if dist[goal] >= 9999:
                goal = start
        path = []
        u = goal
        while u != -1 and u != start:
            path.append((u % 25, u // 25))
            u = par[u]
        path.append((gx, gy))
        path.reverse()
        self.path = path

    def threatens_base(self, e):
        # Close enough to the base walls that two or three shots finish the eagle.
        if abs(e.x - EAGLE_X) < 24 and 120 <= e.y < 184:
            return True
        return e.y >= 168 and abs(e.x - EAGLE_X) < 112

    def follow(self, p):
        path = self.path
        while path and abs(p.x - path[0][0] * 8) + abs(p.y - path[0][1] * 8) <= 2:
            path.pop(0)
        if not path:
            return None
        tx, ty = path[0][0] * 8, path[0][1] * 8
        dx, dy = tx - p.x, ty - p.y
        if p.x & 7 and dx:
            d = 1 if dx > 0 else 3
        elif p.y & 7 and dy:
            d = 2 if dy > 0 else 0
        elif dx:
            d = 1 if dx > 0 else 3
        else:
            d = 2 if dy > 0 else 0
        if self.on_ice(p):
            remaining = abs(dx) + abs(dy)
            straight = len(path) > 1 and (path[1][0] - path[0][0], path[1][1] - path[0][1]) == DIRS[d]
            if remaining < 12 and p.d == d and not straight:
                return None
        return d

    # ---- state machine ------------------------------------------------------------------------------------------------
    def play_tick(self):
        self.t_stage += 1
        want_dir, want_fire = self.bot()
        self.update_player(want_dir, want_fire)
        self.spawn_enemy()
        self.update_enemies()
        self.update_bullets()
        self.collect()
        self.timers()
        self.hud_score()
        self.hud_panel()
        if self.t_stage > 7200 and self.enemies:
            for e in list(self.enemies):
                self.destroy_enemy(e, False)
            self.queue = []
        self.render()

    def step(self):
        self.t += 1
        st = self.state
        self.phase_t += 1
        if self.t >= CAP_TICKS - 5 and st != "end":
            self.state = "end"
            self.es.start(self.score, "GAME OVER")
            return False
        if st == "intro":
            if self.phase_t == 40:
                self.state, self.phase_t = "opening", 0
        elif st == "opening":
            if self.phase_t % 3 == 1 and self.phase_t // 3 < 13:
                k = self.phase_t // 3
                self.compose(12 - k, 0, SUBS, [])
                self.compose(13 + k, 0, SUBS, [])
            if self.phase_t >= 42:
                self.state, self.phase_t = "play", 0
                self.render()
        elif st == "play":
            self.play_tick()
            if not self.queue and not self.enemies and self.state == "play":
                self.state, self.phase_t = "clearing", 0
        elif st == "clearing":
            self.play_tick_quiet()
            if self.phase_t > 110 and self.state == "clearing":
                self.state, self.phase_t = "closing", 0
        elif st == "closing":
            j = (self.phase_t - 1) // 2
            if self.phase_t % 2 == 1 and j < 13:
                fill_rect(FX, FY + j * 40, 208 * SC, 40, GREY565)
                fill_rect(FX, FY + (25 - j) * 40, 208 * SC, 40, GREY565)
            if self.phase_t >= 30:
                self.begin_tally()
        elif st == "tally":
            self.tally_tick()
        elif st == "gameover":
            self.gameover_tick()
        elif st == "end":
            return self.es.tick()
        return False

    def play_tick_quiet(self):
        # After the last enemy falls the bot keeps its position and the effects finish.
        self.update_player(None, False)
        self.update_bullets()
        self.timers()
        self.hud_score()
        self.render()

    def gameover_tick(self):
        self.timers()
        self.update_bullets()
        if self.go_y > 92:
            self.go_y -= 2
        self.hud_score()
        self.render()
        if self.phase_t > 70 + 120:
            self.state = "end"
            self.es.start(self.score, "GAME OVER")

    # ---- tally screen -------------------------------------------------------------------------------------------------
    def begin_tally(self):
        self.state, self.phase_t = "tally", 0
        clear(BLACK565)
        ox, oy = 320, 20
        self.tal_origin = (ox, oy)
        text("HI-SCORE", ox + 8 * 40, oy + 1 * 40, "red")
        text("%7d" % max(self.hi, self.score), ox + 17 * 40, oy + 1 * 40, "orange")
        text("STAGE %2d" % self.stage, ox + 11 * 40, oy + 3 * 40, "black")
        text("I-PLAYER", ox + 3 * 40, oy + 5 * 40, "red")
        self.tal_score = self.score - sum(k * v for k, v in zip(self.kills, ENEMY_SCORE))
        text("%7d" % self.tal_score, ox + 3 * 40, oy + 6 * 40 + 10, "orange")
        for i in range(4):
            y = oy + (9 + 3 * i) * 40
            text("PTS", ox + 9 * 40, y, "black")
            text("<", ox + 15 * 40, y, "black")
            blit(D["tally_tank"][i], ox + 17 * 40, y - 20)
        self.tal_row, self.tal_n, self.tal_total, self.tal_wait = 0, 0, 0, 20

    def tally_tick(self):
        if self.tal_wait:
            self.tal_wait -= 1
            return
        ox, oy = self.tal_origin
        i = self.tal_row
        if i < 4:
            y = oy + (9 + 3 * i) * 40
            if self.tal_n < self.kills[i]:
                self.tal_n += 1
                self.tal_total += 1
                self.tal_score += ENEMY_SCORE[i]
                text("%7d" % self.tal_score, ox + 3 * 40, oy + 6 * 40 + 10, "orange")
                text("%4d" % (self.tal_n * ENEMY_SCORE[i]), ox + 4 * 40, y, "orange")
                text("%2d" % self.tal_n, ox + 13 * 40, y, "black")
                self.tal_wait = 3
            else:
                if self.tal_n == 0:
                    text("   0", ox + 4 * 40, y, "orange")
                    text(" 0", ox + 13 * 40, y, "black")
                self.tal_row += 1
                self.tal_n = 0
                self.tal_wait = 12
        elif i == 4:
            fill_rect(ox + 11 * 40, oy + 21 * 40 + 14, 160, 8, 0xFFFF)
            text("TOTAL", ox + 6 * 40, oy + 22 * 40, "black")
            text("%2d" % self.tal_total, ox + 13 * 40, oy + 22 * 40, "black")
            self.tal_row = 5
            self.tal_wait = 60
        else:
            self.finish_stage()

    def finish_stage(self):
        if self.score >= SCORE_TARGET:
            self.state = "end"
            clear(BLACK565)
            self.es.start(self.score, "VICTORY")
            return
        self.start_stage(self.stage + 1)


def make():
    g = Game()

    def step():
        return g.step()
    step.game = g
    return step
