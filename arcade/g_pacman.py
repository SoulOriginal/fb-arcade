# Pac-Man: arcade maze, ghost AI and level tables after the Pac-Man Dossier; a search bot plays it by itself.
from fbcore import *
from math import floor, ceil

B = load_bundle("g_pacman.bin")

TARGET_SCORE = 30000
# The arcade logic runs at 60 Hz; the screen gets 30 ticks per second. Three logic frames per tick plays the game at 1.5x
# so a run reaches the target score within a few minutes (all timers scale together, relative speeds stay arcade).
FRAMES_PER_TICK = 3
OX, OY = 512, 44          # maze origin on screen
MW, MH = 896, 992         # maze size in pixels (28 x 31 tiles of 32)
MS = MW * 2               # bytes per maze row
COLS, ROWS, NCOL = 28, 31, 30   # NCOL: tile columns incl. the two virtual tunnel tiles (-1 and 28)
DX = (0, -1, 0, 1)        # up, left, down, right: also the ghosts' tie-break order
DY = (-1, 0, 1, 0)
OPP = (2, 3, 0, 1)
BASE = 9.47 / 60          # 100% speed in tiles per 60 Hz frame
INF = 10 ** 9


def ix(x, y):
    return y * NCOL + x + 1


MAZE = B["maze"]
WALLS = set()
for _y, _row in enumerate(MAZE):
    for _x, _ch in enumerate(_row):
        if _ch in "#X":
            WALLS.add((_x, _y))
DOOR = {(13, 12), (14, 12)}
HOME_DOOR_TILES = ((13, 11), (14, 11))
NOUP = {ix(12, 11), ix(15, 11), ix(12, 23), ix(15, 23)}   # ghosts may not turn upward here


def _tiles():
    for y in range(ROWS):
        for x in range(COLS):
            if (x, y) not in WALLS and (x, y) not in DOOR:
                yield x, y
    for x in (-1, 28):
        yield x, 14


FREE = set(_tiles())
# Neighbour tile index per direction (-1 = wall) and the ghosts' turn options per real tile. The tunnel is the chain
# 0 - (-1) - 28 - 27 of tiles: two virtual tiles outside the maze where actors only keep going straight.
NEIGH = {}
OPTS = {}
for (_x, _y) in FREE:
    nb = []
    for _d in range(4):
        nx, ny = _x + DX[_d], _y + DY[_d]
        if nx < -1:
            nx = 28
        elif nx > 28:
            nx = -1
        nb.append(ix(nx, ny) if (nx, ny) in FREE else -1)
    NEIGH[ix(_x, _y)] = nb
    if 0 <= _x < COLS:
        OPTS[ix(_x, _y)] = [(_d, _x + DX[_d], _y + DY[_d]) for _d in range(4) if (_x + DX[_d], _y + DY[_d]) in FREE]
NIDX = ROWS * NCOL + 2
TILE_OF = {ix(x, y): (x, y) for (x, y) in FREE}
TUNNEL_TILES = {i for i, (x, y) in TILE_OF.items() if y == 14 and (x < 6 or x > 21)}
FRUIT_TILES = (ix(13, 17), ix(14, 17))
# tile coordinates and centres by tile index, for the bot's inner loops
XT = [0] * NIDX
YT = [0] * NIDX
XC = [0.0] * NIDX
YC = [0.0] * NIDX
for _i, (_x, _y) in TILE_OF.items():
    XT[_i], YT[_i], XC[_i], YC[_i] = _x, _y, _x + 0.5, _y + 0.5

# ---- level tables (Pac-Man Dossier), indexed by level - 1 up to level 21 --------------------------------------
PAC_PCT = [80, 90, 90, 90] + [100] * 16 + [90]
PAC_FR_PCT = [90, 95, 95, 95] + [100] * 16 + [90]
GHOST_PCT = [75, 85, 85, 85] + [95] * 17
TUN_PCT = [40, 45] + [50] * 19
GHOST_FR_PCT = [50, 55, 55, 55] + [60] * 17
FRIGHT_SEC = [6, 5, 4, 3, 2, 5, 2, 2, 1, 5, 2, 1, 1, 3, 1, 1, 0, 1] + [0] * 3
FLASHES = [5, 5, 5, 5, 5, 5, 5, 5, 3, 5, 5, 3, 3, 5, 3, 3, 0, 3] + [0] * 3
ELROY_DOTS = [20, 30, 40, 40, 40, 50, 50, 50, 60, 60, 60, 80, 80, 80, 100, 100, 100, 100] + [120] * 3
FRUIT_KIND = [0, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7]
FRUIT_POINTS = [100, 300, 500, 500, 700, 700, 1000, 1000, 2000, 2000, 3000, 3000, 5000]
POPUP_INDEX = {k: i for i, k in enumerate(B["popup_keys"])}
SCATTER_CORNER = ((25, -3), (2, -3), (27, 31), (0, 31))
INF_FRAMES = 10 ** 9


def waves(level):
    if level == 1:
        w = [7, 20, 7, 20, 5, 20, 5]
    elif level <= 4:
        w = [7, 20, 7, 20, 5, 1033, 1 / 60]
    else:
        w = [5, 20, 5, 20, 5, 1037, 1 / 60]
    return [max(1, round(s * 60)) for s in w] + [INF_FRAMES]


def level_row(table, level):
    return table[min(level, 21) - 1]


# ---- ghost steering shared by the game and the bot's simulation -----------------------------------------------
def choose(tile, d, gx, gy, restrict=True):
    # The arcade rule: of the tiles ahead (never a U-turn) take the one nearest to the target; ties go up, left,
    # down, right. A ghost with no option at all turns back, which cannot happen in this maze but is safe.
    best, bd, back = -1, INF, OPP[d]
    noup = restrict and tile in NOUP
    for nd, nx, ny in OPTS[tile]:
        if nd == back or (noup and nd == 0):
            continue
        dd = (nx - gx) ** 2 + (ny - gy) ** 2
        if dd < bd:
            bd, best = dd, nd
    return best if best >= 0 else back


def chase_target(gid, tx, ty, ptx, pty, pd, btx, bty):
    if gid == 0:
        return ptx, pty
    if gid == 1:
        # the arcade overflow bug: "four tiles up" is also four tiles left
        return ptx + 4 * DX[pd] - (4 if pd == 0 else 0), pty + 4 * DY[pd]
    if gid == 2:
        ax, ay = ptx + 2 * DX[pd] - (2 if pd == 0 else 0), pty + 2 * DY[pd]
        return 2 * ax - btx, 2 * ay - bty
    if (tx - ptx) ** 2 + (ty - pty) ** 2 > 64:
        return ptx, pty
    return SCATTER_CORNER[3]


# ---- sprites ---------------------------------------------------------------------------------------------------------
def prep(t):
    # (w, h, pixels, mask) -> rows of (pixel int, mask int) so compositing is a few big-int operations per row
    w, h, pix, mk = t
    n = w * 2
    return (w, h, [(int.from_bytes(pix[r * n:(r + 1) * n], "little"), int.from_bytes(mk[r * n:(r + 1) * n], "little"))
                   for r in range(h)])


def prep_all(v):
    return [prep(s) for s in v]


PAC = prep_all(B["pac"])
PAC_DEATH = prep_all(B["pac_death"])
GHOST = prep_all(B["ghost"])
FRIGHT = prep_all(B["fright"])
EYES = prep_all(B["eyes"])
FRUIT = prep_all(B["fruit"])
POPUP = prep_all(B["popup"])
READY = prep(B["ready"])
GAMEOVER = prep(B["gameover"])
DOT = prep(B["dot"])
ENERGIZER = prep(B["energizer"])


def blit_masked(buf, spr, x, y):
    w, h, rows = spr
    n = w * 2
    for j in range(h):
        pv, mk = rows[j]
        o = (y + j) * MS + x * 2
        cur = int.from_bytes(buf[o:o + n], "little")
        buf[o:o + n] = (cur ^ ((cur ^ pv) & mk)).to_bytes(n, "little")


def _plain(t):
    return (t[0], t[1], [t[2][j * t[0] * 2:(j + 1) * t[0] * 2] for j in range(t[1])])


LIFE_S = _plain(B["life"])
FRUIT_SMALL_S = [_plain(s) for s in B["fruit_small"]]
MAZE_BLUE = bytes().join(B["maze_blue"][2])
MAZE_WHITE = bytes().join(B["maze_white"][2])


# ---- actors ----------------------------------------------------------------------------------------------------------
class Actor:
    __slots__ = ("x", "y", "d", "stop", "tile", "pause", "anim")

    def __init__(self):
        self.x = self.y = 0.0
        self.d = 1
        self.stop = False
        self.tile = (0, 0)
        self.pause = 0
        self.anim = 0.0


HOUSE, LEAVE, NORMAL, EYES_MODE, ENTER = range(5)


class Ghost:
    __slots__ = ("i", "x", "y", "d", "mode", "fright", "rev", "wp", "hx", "hy", "bob", "stop")

    def __init__(self, i):
        self.i = i
        self.wp = []
        self.bob = 1
        self.stop = False
        self.hx, self.hy = ((14.0, 11.5), (14.0, 14.5), (12.0, 14.5), (16.0, 14.5))[i]
        self.reset()

    def reset(self):
        self.x, self.y = self.hx, self.hy
        self.d = 1 if self.i == 0 else 2
        self.mode = NORMAL if self.i == 0 else HOUSE
        self.fright = False
        self.rev = False
        self.wp = []


def advance(e, dist, arrive):
    # Moves along the current direction, calling arrive(e) each time a tile centre is reached; arrive may turn the
    # actor or set e.stop. Centres sit at k + 0.5; the tunnel wraps at x = -1.0 / 29.0 (outside the visible maze).
    while dist > 1e-9:
        d = e.d
        if d & 1:
            u = e.x - 0.5
            if d == 3:
                nc = floor(u + 1e-9) + 1
                gap = nc - u
            else:
                nc = ceil(u - 1e-9) - 1
                gap = u - nc
            if dist < gap - 1e-9:
                e.x += dist if d == 3 else -dist
                if e.x < -1.0:
                    e.x += 30.0
                elif e.x > 29.0:
                    e.x -= 30.0
                return
            e.x = nc + 0.5
        else:
            u = e.y - 0.5
            if d == 2:
                nc = floor(u + 1e-9) + 1
                gap = nc - u
            else:
                nc = ceil(u - 1e-9) - 1
                gap = u - nc
            if dist < gap - 1e-9:
                e.y += dist if d == 2 else -dist
                return
            e.y = nc + 0.5
        dist -= gap
        arrive(e)
        if e.stop:
            return


def ghost_state(g):
    # (tile index, heading, progress towards the next tile) of a ghost on the maze graph
    d = g.d
    if d & 1:
        u = g.x - 0.5
        if d == 3:
            tx = floor(u + 1e-9)
            prog = u - tx
        else:
            tx = ceil(u - 1e-9)
            prog = tx - u
        # just past the tunnel seam the last centre lies on the far side: -2 is tile 28 and 29 is tile -1
        return (tx + 1) % 30 - 1, floor(g.y), d, prog
    u = g.y - 0.5
    if d == 2:
        ty = floor(u + 1e-9)
        prog = u - ty
    else:
        ty = ceil(u - 1e-9)
        prog = ty - u
    return floor(g.x), ty, d, prog


# ---- bot ---------------------------------------------------------------------------------------------------------
GAMMA = 0.97
LEAF_W = 0.6
DEATH = -1000.0
NODE_BUDGET = 450   # expansions per decision over all deepening stages: keeps one tick under ~10 ms
COLLIDE = 1.2     # Manhattan distance in tiles that counts as a hit in the simulation (wider than the arcade: margin for error)
HIT_RANGE = 2 * COLLIDE + 2.4   # the pair distance changes by <= ~2.2 tiles per step: farther pairs cannot meet


def field(srcs):
    # multi-source BFS on the tile graph; srcs: (tile index, starting offset)
    dist = [INF] * NIDX
    buckets = [[] for _ in range(130)]
    for i, d0 in srcs:
        if d0 < dist[i]:
            dist[i] = d0
            buckets[d0].append(i)
    for d in range(128):
        for i in buckets[d]:
            if dist[i] != d:
                continue
            for n in NEIGH[i]:
                if n >= 0 and dist[n] > d + 1:
                    dist[n] = d + 1
                    buckets[d + 1].append(n)
    return dist


def hit(r0x, r0y, r1x, r1y):
    # Does the segment r0 -> r1 (ghost minus Pac-Man, moving linearly) come closer than COLLIDE in the L1 sense?
    # The L1 norm is piecewise linear, so its minimum sits at an end or where a component crosses zero.
    if abs(r0x) + abs(r0y) < COLLIDE or abs(r1x) + abs(r1y) < COLLIDE:
        return True
    dx, dy = r1x - r0x, r1y - r0y
    if dx:
        s = -r0x / dx
        if 0 < s < 1 and abs(r0y + s * dy) < COLLIDE:
            return True
    if dy:
        s = -r0y / dy
        if 0 < s < 1 and abs(r0x + s * dx) < COLLIDE:
            return True
    return False


class Bot:
    def __init__(self, game):
        self.g = game
        self.pick = 0

    def decide(self):
        g = self.g
        p = g.pac
        here = ix(floor(p.x), floor(p.y))
        nb = NEIGH[here]
        opts = [d for d in range(4) if nb[d] >= 0]
        if not opts:
            return p.d
        if len(opts) == 1:
            return opts[0]
        return self.search(here, p.d, opts)

    def search(self, here, d0, opts):
        g = self.g
        tf = 1.0 / g.pac_speed()
        # ---- ghosts: lethal ones are simulated, frightened ones are hunted ---------------------------------------
        lethal, prey = [], []
        px, py = XT[here], YT[here]
        for gh in g.ghosts:
            if gh.mode == NORMAL and not gh.fright:
                tx, ty, d, pr = ghost_state(gh)
                if abs(tx - px) + abs(ty - py) <= 22:
                    gi = ix(tx, ty)
                    lethal.append((gh.i, gi, d, pr, gh.rev, XC[gi] + DX[d] * pr, YC[gi] + DY[d] * pr, 0))
            elif gh.mode == LEAVE:
                # still inside the house: it pops out at the door after the remaining walk, at house speed
                delay = (abs(gh.x - 14.0) + abs(gh.y - 11.5)) * 0.5 / g.ghost_pct()
                if abs(14 - px) + abs(11 - py) <= 22:
                    gi = ix(14, 11)
                    pr = 0.5 - delay
                    lethal.append((gh.i, gi, 1, pr, False, XC[gi] - pr, YC[gi], 0))
            elif gh.mode == NORMAL and gh.fright:
                prey.append(gh)
                # harmless now, but deadly again when the fright timer runs out: it must not be walked into then
                tx, ty, d, pr = ghost_state(gh)
                gi = ix(tx, ty)
                if abs(tx - px) + abs(ty - py) <= 22:
                    lethal.append((gh.i, gi, d, pr, gh.rev, XC[gi] + DX[d] * pr, YC[gi] + DY[d] * pr, g.fright_t))
        bl = g.ghosts[0]
        bt = (floor(bl.x), floor(bl.y))
        gsp = g.ghost_pct() * BASE
        frsp = level_row(GHOST_FR_PCT, g.level) / 100 * BASE
        tun = g.tunnel_pct * BASE
        elroy = g.elroy_active()
        elroy_sp = g.elroy_speed_pct() * BASE
        chase_now = g.chase_mode()
        t_switch = g.wave_t if g.fright_t <= 0 else INF_FRAMES
        # ---- reward fields -----------------------------------------------------------------------------------
        pellets = g.pellets
        pac_field = field([(here, 0)])
        # How many ghosts a frightening energizer would catch right now: ghosts close behind are worth the most.
        quality = 0.0
        for ls in lethal:
            gd = pac_field[ls[1]]
            if gd < 10:
                quality += 1.0 - gd / 10.0
        fright_on = g.fright_t > 90
        srcs = []
        energizers = []
        dots = 0
        for i, kind in pellets.items():
            if kind == 1:
                srcs.append((i, 0))
                dots += 1
            else:
                energizers.append(i)
        stalled = g.no_dot_t > 600
        # The last energizer is the only escape hatch left for the end of the level: spend it only on a big catch.
        need = 2.0 if len(energizers) <= 2 and dots > 10 else 1.0
        wanted = not fright_on and (quality >= need or g.no_dot_t > 360)
        # An energizer nobody is chasing us around is wasted: step on it only when it pays or when the level needs it.
        r_energizer = 6.0 + 14.0 * quality if wanted else (3.0 if dots == 0 else -2.0)
        for i in energizers:
            if wanted or dots == 0:
                srcs.append((i, 0))
            elif dots <= 12:
                srcs.append((i, 8))
        fruit_on = g.fruit_t > 0
        fruit_r = FRUIT_POINTS[g.fruit_idx] / 10.0
        if fruit_on:
            for i in FRUIT_TILES:
                srcs.append((i, 2))
        dist_p = field(srcs)
        hunt = None
        catch = {}
        if prey:
            hs = []
            for gh in prey:
                tx, ty, _d, _pr = ghost_state(gh)
                gi = ix(tx, ty)
                if gi in TILE_OF and pac_field[gi] * tf < g.fright_t * 0.8:
                    hs.append((gi, 0))
                    reward = 18.0 * (2 ** min(g.chain, 3))
                    catch[gi] = reward
                    for nn in NEIGH[gi]:
                        if nn >= 0:
                            catch.setdefault(nn, reward)
            if hs:
                hunt = field(hs)
        # When nothing was eaten for ten seconds the ghosts keep the bot circling: take more risk for the dots.
        pen_w = 0.4 if stalled else 3.0
        leaf_w = 1.2 if stalled else LEAF_W
        eaten = set()
        caught = set()
        nodes = [0]
        cap = [0]

        def adv(gs, dt, t2, ni, pd):
            # One simulation step for all lethal ghosts, in the order of the game (Blinky first: Inky needs him).
            ptx, pty = XT[ni], YT[ni]
            out = []
            btx, bty = bt
            late = t2 >= t_switch
            crossing = late and t2 - dt < t_switch
            chasing_base = chase_now != late
            for (gid, i, d, prog, rev, _gx, _gy, arm) in gs:
                if i in TUNNEL_TILES:
                    sp = tun
                elif t2 < arm:
                    sp = frsp
                else:
                    sp = elroy_sp if gid == 0 and elroy else gsp
                if crossing:
                    rev = True
                prog += sp * dt
                while prog >= 1.0:
                    prog -= 1.0
                    i = NEIGH[i][d]
                    if rev:
                        d = OPP[d]
                        rev = False
                    elif i in OPTS:
                        if chasing_base or (gid == 0 and elroy):
                            gx, gy = chase_target(gid, XT[i], YT[i], ptx, pty, pd, btx, bty)
                        else:
                            gx, gy = SCATTER_CORNER[gid]
                        d = choose(i, d, gx, gy)
                out.append((gid, i, d, prog, rev, XC[i] + DX[d] * prog, YC[i] + DY[d] * prog, arm))
                if gid == 0:
                    btx, bty = XT[i], YT[i]
            return out

        def rec(i, d, k, t, gs, depth_max):
            # best value obtainable from here; the caller adds the reward of reaching this node
            if k >= depth_max or nodes[0] > cap[0]:
                if hunt is not None and hunt[i] < INF:
                    return -0.9 * hunt[i]
                v = dist_p[i]
                return -leaf_w * v if v < INF else -leaf_w * 99
            nodes[0] += 1
            best = -1e18
            nb = NEIGH[i]
            back = OPP[d]
            ax, ay = XC[i], YC[i]
            for nd in range(4):
                ni = nb[nd]
                if ni < 0 or (nd == back and k > 0):
                    continue
                r = 0.0
                pause = 0
                kind = pellets.get(ni, 0)
                took = False
                if kind and ni not in eaten:
                    took = True
                    if kind == 1:
                        r = 1.0
                        pause = 1
                    else:
                        r = r_energizer
                        pause = 3
                    eaten.add(ni)
                ck = ni in catch and ni not in caught
                if ck:
                    r += catch[ni]
                    caught.add(ni)
                ftook = fruit_on and ni in FRUIT_TILES and "f" not in eaten
                if ftook:
                    r += fruit_r
                    eaten.add("f")
                dt = tf + pause
                t2 = t + dt
                if gs:
                    ngs = adv(gs, dt, t2, ni, nd)
                    bx, by = XC[ni], YC[ni]
                    dead = False
                    near = 99.0
                    for j in range(len(gs)):
                        og = gs[j]
                        ng = ngs[j]
                        r1x, r1y = ng[5] - bx, ng[6] - by
                        r0x, r0y = og[5] - ax, og[6] - ay
                        # the tunnel joins the left and right edges: distances wrap around the 30-tile ring
                        if r1x > 15.0:
                            r1x -= 30.0
                        elif r1x < -15.0:
                            r1x += 30.0
                        if r0x > 15.0:
                            r0x -= 30.0
                        elif r0x < -15.0:
                            r0x += 30.0
                        m1 = abs(r1x) + abs(r1y)
                        if t2 < ng[7]:
                            continue
                        if m1 + abs(r0x) + abs(r0y) < HIT_RANGE and hit(r0x, r0y, r1x, r1y):
                            dead = True
                            break
                        if m1 < near:
                            near = m1
                    if dead:
                        v = DEATH + t2 * 0.5
                    else:
                        v = r + GAMMA * rec(ni, nd, k + 1, t2, ngs, depth_max)
                        if near < 3.0:
                            v -= (3.0 - near) * pen_w
                else:
                    v = r + GAMMA * rec(ni, nd, k + 1, t2, gs, depth_max)
                if took:
                    eaten.discard(ni)
                if ck:
                    caught.discard(ni)
                if ftook:
                    eaten.discard("f")
                if k == 0:
                    v += random.random() * 1e-3
                    if v > best:
                        best = v
                        self.pick = nd
                elif v > best:
                    best = v
            return best

        # Iterative deepening: a deeper stage only replaces the result when it finished inside its node budget,
        # because a search cut short by the budget has only looked at the first branches.
        stages = (8, 14, 20, 26) if lethal else ((12, 18) if hunt is not None else (12,))
        choice = opts[0]
        used = 0
        lethal_t = tuple(lethal)
        for depth in stages:
            nodes[0] = 0
            cap[0] = NODE_BUDGET - used
            self.pick = choice
            rec(here, d0, 0, 0.0, lethal_t, depth)
            used += nodes[0]
            if nodes[0] > cap[0]:
                break
            choice = self.pick
        return choice


# ---- the game -----------------------------------------------------------------------------------------------------
class Game:
    def __init__(self):
        self.score = 0
        self.high = 20000
        self.lives = 3
        self.level = 1
        self.extra_given = False
        self.fc = 0
        self.ticks = 0
        self.pac = Actor()
        self.ghosts = [Ghost(i) for i in range(4)]
        self.bot = Bot(self)
        self.shown = {}
        self.dirty = []
        self.bg = None
        self.hud_cache = {}
        self.fruit_history = []
        self.end = None
        self.pop = None
        self.overlay = None
        self.hide_ghosts = False
        self.hide_pac = False
        self.state = "ready"
        self.global_mode = False
        self.global_counter = 0
        self.new_level(first=True)

    # ---- per-level setup --------------------------------------------------------------------------------------
    def new_level(self, first=False):
        L = self.level
        self.pellets = {}
        for y, row in enumerate(MAZE):
            for x, ch in enumerate(row):
                if ch == ".":
                    self.pellets[ix(x, y)] = 1
                elif ch == "o":
                    self.pellets[ix(x, y)] = 2
        self.dots_left = len(self.pellets)
        self.dots_eaten = 0
        self.pac_pct = level_row(PAC_PCT, L)
        self.pacsp = self.pac_pct * BASE / 100
        self.pacfr = level_row(PAC_FR_PCT, L) * BASE / 100
        self.tunnel_pct = level_row(TUN_PCT, L) / 100
        self.fright_frames = level_row(FRIGHT_SEC, L) * 60
        self.flash_frames = level_row(FLASHES, L) * 28
        self.elroy1 = level_row(ELROY_DOTS, L)
        self.elroy2 = self.elroy1 // 2
        self.waves = waves(L)
        self.fruit_idx = min(L, len(FRUIT_KIND)) - 1
        self.fruit_kind = FRUIT_KIND[self.fruit_idx]
        self.fruit_t = 0
        self.personal = [0, 0, 0, 0]
        self.limits = [0, 0, 30, 60] if L == 1 else ([0, 0, 0, 50] if L == 2 else [0, 0, 0, 0])
        self.global_mode = False
        self.fruit_history = (self.fruit_history + [self.fruit_kind])[-7:]
        self.build_bg()
        self.reset_positions()
        self.state = "ready"
        self.timer = 150 if first else 100
        self.overlay = READY
        self.hud_dirty = True
        self.full_redraw = True

    def build_bg(self):
        self.clean = bytearray(MAZE_BLUE)
        self.bg = bytearray(MAZE_BLUE)
        for i, kind in self.pellets.items():
            x, y = TILE_OF[i]
            if kind == 1:
                blit_masked(self.bg, DOT, x * 32 + 12, y * 32 + 12)
            else:
                blit_masked(self.bg, ENERGIZER, x * 32 + 4, y * 32 + 4)
        self.energizer_on = True

    def reset_positions(self):
        p = self.pac
        p.x, p.y, p.d, p.stop, p.pause = 14.0, 23.5, 1, False, 0
        p.tile = (14, 23)
        for g in self.ghosts:
            g.reset()
        self.wave_i = 0
        self.wave_t = self.waves[0]
        self.fright_t = 0
        self.chain = 0
        self.no_dot_t = 0
        self.fruit_t = 0
        self.elroy_off = self.global_mode
        self.pop = None
        self.hide_ghosts = False
        self.hide_pac = False

    # ---- derived speeds ----------------------------------------------------------------------------------------
    def pac_speed(self):
        return self.pacfr if self.fright_t > 0 else self.pacsp

    def chase_mode(self):
        return self.wave_i & 1 == 1

    def elroy_active(self):
        if self.elroy_off:
            return 0
        if self.dots_left <= self.elroy2:
            return 2
        if self.dots_left <= self.elroy1:
            return 1
        return 0

    def elroy_speed_pct(self):
        L = self.level
        base = 80 if L == 1 else (90 if L <= 4 else 100)
        return (base + (5 if self.elroy_active() == 2 else 0)) / 100

    def ghost_pct(self):
        return level_row(GHOST_PCT, self.level) / 100

    def current_ghost_speed(self, g):
        m = g.mode
        if m == EYES_MODE:
            return 1.7 * BASE
        if m == HOUSE or m == LEAVE or m == ENTER:
            return 0.5 * BASE
        if ix(floor(g.x), floor(g.y)) in TUNNEL_TILES:
            return self.tunnel_pct * BASE
        if g.fright:
            return level_row(GHOST_FR_PCT, self.level) / 100 * BASE
        if g.i == 0 and self.elroy_active():
            return self.elroy_speed_pct() * BASE
        return self.ghost_pct() * BASE

    # ---- scoring ------------------------------------------------------------------------------------------------
    def add_score(self, n):
        self.score += n
        if self.score > self.high:
            self.high = self.score
        if not self.extra_given and self.score >= 10000:
            self.extra_given = True
            self.lives += 1
            self.hud_dirty = True

    # ---- Pac-Man ------------------------------------------------------------------------------------------------
    def pac_arrive(self, p):
        tx, ty = floor(p.x), floor(p.y)
        if tx < 0 or tx > 27:
            p.stop = False
            return
        want = self.bot.decide()
        i = ix(tx, ty)
        if NEIGH[i][want] >= 0:
            p.d = want
            p.stop = False
        elif NEIGH[i][p.d] >= 0:
            p.stop = False
        else:
            p.stop = True

    def move_pac(self):
        p = self.pac
        if p.pause > 0:
            p.pause -= 1
            return
        if p.stop:
            self.pac_arrive(p)
            if p.stop:
                return
        sp = self.pac_speed()
        advance(p, sp, self.pac_arrive)
        p.anim += sp
        tile = (floor(p.x), floor(p.y))
        if tile != p.tile:
            p.tile = tile
            self.eat(tile)

    def eat(self, tile):
        i = ix(*tile)
        kind = self.pellets.get(i)
        if kind:
            del self.pellets[i]
            self.dots_left -= 1
            self.dots_eaten += 1
            self.no_dot_t = 0
            x, y = tile
            if kind == 1:
                self.add_score(10)
                self.pac.pause = 1
                self.erase(x * 32 + 12, y * 32 + 12, 8, 8)
            else:
                self.add_score(50)
                self.pac.pause = 3
                self.erase(x * 32 + 4, y * 32 + 4, 24, 24)
                self.start_fright()
            self.dot_released()
            if self.dots_eaten in (70, 170):
                self.fruit_t = 600 + random.randint(0, 40)
            if self.dots_left == 0:
                self.state, self.timer = "clear_wait", 70
                return
        if self.fruit_t > 0 and tile in ((13, 17), (14, 17)):
            pts = FRUIT_POINTS[self.fruit_idx]
            self.add_score(pts)
            self.fruit_t = 0
            self.pop = [POPUP[POPUP_INDEX[str(pts)]], 14.0, 17.5, 120]

    def erase(self, x, y, w, h):
        n = w * 2
        for j in range(h):
            o = (y + j) * MS + x * 2
            self.bg[o:o + n] = self.clean[o:o + n]
        self.dirty.append((x, y, x + w, y + h))

    def start_fright(self):
        self.chain = 0
        if self.fright_frames <= 0:
            for g in self.ghosts:
                if g.mode == NORMAL:
                    g.rev = True
            return
        self.fright_t = self.fright_frames
        for g in self.ghosts:
            if g.mode in (HOUSE, LEAVE, NORMAL):
                g.fright = True
                if g.mode == NORMAL:
                    g.rev = True

    # ---- ghosts -------------------------------------------------------------------------------------------------
    def ghost_arrive_factory(self):
        pac = self.pac
        bl = self.ghosts[0]
        chase = self.chase_mode()
        elroy = self.elroy_active()

        def arrive(g):
            tx, ty = floor(g.x), floor(g.y)
            if tx < 0 or tx > 27:
                return
            i = ix(tx, ty)
            if g.mode == EYES_MODE:
                if (tx, ty) in HOME_DOOR_TILES:
                    g.mode = ENTER
                    g.wp = [(14.0, 11.5), (14.0, 14.5)]
                    return
                g.d = choose(i, g.d, 13, 11, False)
                return
            if g.rev:
                g.d = OPP[g.d]
                g.rev = False
                return
            if g.fright:
                back = OPP[g.d]
                opts = [nd for nd, nx, ny in OPTS[i] if nd != back]
                g.d = random.choice(opts) if opts else back
                return
            if chase or (g.i == 0 and elroy):
                gx, gy = chase_target(g.i, tx, ty, floor(pac.x), floor(pac.y), pac.d, floor(bl.x), floor(bl.y))
            else:
                gx, gy = SCATTER_CORNER[g.i]
            g.d = choose(i, g.d, gx, gy)
        return arrive

    def move_ghost(self, g, arrive):
        sp = self.current_ghost_speed(g)
        m = g.mode
        if m == NORMAL or m == EYES_MODE:
            advance(g, sp, arrive)
        elif m == HOUSE:
            g.y += g.bob * sp
            if g.y < g.hy - 0.3:
                g.y, g.bob = g.hy - 0.3, 1
            elif g.y > g.hy + 0.3:
                g.y, g.bob = g.hy + 0.3, -1
            g.d = 0 if g.bob < 0 else 2
        else:
            self.follow_waypoints(g, sp)

    def follow_waypoints(self, g, dist):
        while dist > 1e-9 and g.wp:
            wx, wy = g.wp[0]
            dx, dy = wx - g.x, wy - g.y
            gap = abs(dx) + abs(dy)
            if gap <= dist:
                g.x, g.y = wx, wy
                g.wp.pop(0)
                dist -= gap
                continue
            if dx:
                g.x += dist if dx > 0 else -dist
                g.d = 3 if dx > 0 else 1
            else:
                g.y += dist if dy > 0 else -dist
                g.d = 2 if dy > 0 else 0
            return
        if g.wp:
            return
        if g.mode == ENTER:
            g.fright = False
            g.mode = LEAVE
            g.wp = [(14.0, 11.5)]
            g.d = 0
        else:
            g.mode = NORMAL
            g.x, g.y, g.d, g.rev = 14.0, 11.5, 1, False
            if g.i == 3:
                self.elroy_off = False

    def release(self, i):
        g = self.ghosts[i]
        g.mode = LEAVE
        g.wp = [(14.0, g.y), (14.0, 11.5)]
        self.no_dot_t = 0

    def dot_released(self):
        if self.global_mode:
            self.global_counter += 1
            for i, lim in ((1, 7), (2, 17), (3, 32)):
                if self.ghosts[i].mode == HOUSE and self.global_counter == lim:
                    self.release(i)
                    if i == 3:
                        self.global_mode = False
            return
        for i in (1, 2, 3):
            if self.ghosts[i].mode == HOUSE:
                self.personal[i] += 1
                break

    def release_check(self):
        self.no_dot_t += 1
        limit = 240 if self.level < 5 else 180
        for i in (1, 2, 3):
            g = self.ghosts[i]
            if g.mode != HOUSE:
                continue
            if self.no_dot_t >= limit:
                self.release(i)
            elif not self.global_mode and self.personal[i] >= self.limits[i]:
                self.release(i)
            break

    # ---- main frame ---------------------------------------------------------------------------------------------
    def play_frame(self):
        if self.fright_t > 0:
            self.fright_t -= 1
            if self.fright_t == 0:
                for g in self.ghosts:
                    g.fright = False
        else:
            self.wave_t -= 1
            if self.wave_t <= 0 and self.wave_i < len(self.waves) - 1:
                self.wave_i += 1
                self.wave_t = self.waves[self.wave_i]
                for g in self.ghosts:
                    if g.mode == NORMAL:
                        g.rev = True
        self.move_pac()
        if self.state != "play":
            return
        arrive = self.ghost_arrive_factory()
        for g in self.ghosts:
            self.move_ghost(g, arrive)
        self.release_check()
        if self.fruit_t > 0:
            self.fruit_t -= 1
        self.check_collisions()

    def check_collisions(self):
        pt = (floor(self.pac.x), floor(self.pac.y))
        for g in self.ghosts:
            if g.mode not in (NORMAL,) or (floor(g.x), floor(g.y)) != pt:
                continue
            if g.fright:
                pts = 200 * (2 ** self.chain)
                self.chain = min(self.chain + 1, 3)
                self.add_score(pts)
                g.mode = EYES_MODE
                g.fright = False
                self.pop = [POPUP[POPUP_INDEX[str(pts)]], g.x, g.y, 60]
                self.state, self.timer = "eat_ghost", 60
                self.hide_pac = True
                return
            self.state, self.timer = "dying", 50
            return

    def frame(self):
        self.fc += 1
        if self.pop:
            self.pop[3] -= 1
            if self.pop[3] <= 0:
                self.pop = None
        st = self.state
        if st == "play":
            self.play_frame()
        elif st == "ready":
            self.timer -= 1
            if self.timer <= 0:
                self.overlay = None
                self.state = "play"
        elif st == "eat_ghost":
            self.timer -= 1
            if self.timer <= 0:
                self.hide_pac = False
                self.state = "play"
        elif st == "dying":
            self.timer -= 1
            if self.timer <= 0:
                self.hide_ghosts = True
                self.fruit_t = 0
                self.state, self.timer = "death_anim", 96
        elif st == "death_anim":
            self.timer -= 1
            if self.timer <= 0:
                self.lives -= 1
                self.hud_dirty = True
                if self.lives <= 0:
                    self.hide_pac = True
                    self.overlay = GAMEOVER
                    self.state, self.timer = "over", 100
                else:
                    self.global_mode = True
                    self.global_counter = 0
                    self.reset_positions()
                    self.state, self.timer = "ready", 100
                    self.overlay = READY
        elif st == "clear_wait":
            self.timer -= 1
            if self.timer <= 0:
                self.hide_ghosts = True
                self.state, self.timer = "flash", 100
        elif st == "flash":
            self.timer -= 1
            if self.timer % 12 == 0:
                data = MAZE_WHITE if (self.timer // 12) & 1 else MAZE_BLUE
                self.flash_write(data)
            if self.timer <= 0:
                self.level += 1
                self.new_level()
        elif st == "over":
            self.timer -= 1
            if self.timer <= 0:
                return True
        return False

    def flash_write(self, data):
        for r in range(MH):
            fb[(OY + r) * S + OX * 2:(OY + r) * S + (OX + MW) * 2] = data[r * MS:(r + 1) * MS]
        self.shown = {}

    # ---- drawing ------------------------------------------------------------------------------------------------
    def sprites(self):
        out = []
        fc = self.fc
        if self.fruit_t > 0 and self.state in ("play", "eat_ghost"):
            out.append(("f", FRUIT[self.fruit_kind], 14 * 32 - 32, int(17.5 * 32) - 32))
        if not self.hide_pac:
            p = self.pac
            if self.state == "death_anim":
                s = PAC_DEATH[min(11, (96 - self.timer) // 8)]
            else:
                s = PAC[p.d * 3 + (1, 0, 1, 2)[int(p.anim * 3) & 3]]
            out.append(("p", s, round(p.x * 32) - 32, round(p.y * 32) - 32))
        if not self.hide_ghosts:
            foot = (fc >> 3) & 1
            for g in reversed(self.ghosts):
                if g.mode == EYES_MODE or g.mode == ENTER:
                    s = EYES[g.d]
                elif g.fright:
                    flashing = self.fright_t <= self.flash_frames and (self.fright_t // 14) & 1 == 0 and g.mode == NORMAL
                    s = FRIGHT[(2 if flashing else 0) + foot]
                else:
                    s = GHOST[(g.i * 2 + foot) * 4 + g.d]
                out.append(("g%d" % g.i, s, round(g.x * 32) - 32, round(g.y * 32) - 32))
        if self.pop:
            s, x, y, _ = self.pop
            out.append(("pop", s, round(x * 32) - s[0] // 2, round(y * 32) - s[1] // 2))
        if self.overlay:
            s = self.overlay
            out.append(("ov", s, 14 * 32 - s[0] // 2, int(17.5 * 32) - s[1] // 2))
        return out

    def render(self):
        if self.full_redraw:
            self.full_redraw = False
            self.shown = {}
            self.dirty = [(0, 0, MW, MH)]
        blink = (self.fc // 14) & 1 == 0
        if blink != self.energizer_on and self.state != "flash":
            self.energizer_on = blink
            for i, kind in self.pellets.items():
                if kind == 2:
                    x, y = TILE_OF[i]
                    if blink:
                        blit_masked(self.bg, ENERGIZER, x * 32 + 4, y * 32 + 4)
                    else:
                        self.erase(x * 32 + 4, y * 32 + 4, 24, 24)
                    self.dirty.append((x * 32 + 4, y * 32 + 4, x * 32 + 28, y * 32 + 28))
        if self.state == "flash":
            return
        cur = self.sprites()
        curd = {k: (s, x, y) for k, s, x, y in cur}
        rects = list(self.dirty)
        self.dirty = []
        for k in set(curd) | set(self.shown):
            a, b = curd.get(k), self.shown.get(k)
            if a is b or (a and b and a[0] is b[0] and a[1] == b[1] and a[2] == b[2]):
                continue
            for r in (a, b):
                if r:
                    rects.append((r[1], r[2], r[1] + r[0][0], r[2] + r[0][1]))
        self.shown = curd
        if not rects:
            return
        boxes = []
        for r in rects:
            r = [max(0, r[0]), max(0, r[1]), min(MW, r[2]), min(MH, r[3])]
            if r[2] > r[0] and r[3] > r[1]:
                boxes.append(r)
        sp_boxes = [(max(0, x), max(0, y), min(MW, x + s[0]), min(MH, y + s[1])) for _, s, x, y in cur]
        sp_boxes = [b for b in sp_boxes if b[2] > b[0] and b[3] > b[1]]
        merged = True
        while merged:
            merged = False
            boxes2 = []
            for r in boxes:
                for q in boxes2:
                    if r[0] < q[2] and q[0] < r[2] and r[1] < q[3] and q[1] < r[3]:
                        q[0], q[1], q[2], q[3] = min(q[0], r[0]), min(q[1], r[1]), max(q[2], r[2]), max(q[3], r[3])
                        merged = True
                        break
                else:
                    boxes2.append(r)
            boxes = boxes2
            for q in boxes:
                for b in sp_boxes:
                    if b[0] < q[2] and q[0] < b[2] and b[1] < q[3] and q[1] < b[3] and not (
                            b[0] >= q[0] and b[1] >= q[1] and b[2] <= q[2] and b[3] <= q[3]):
                        q[0], q[1] = max(0, min(q[0], b[0])), max(0, min(q[1], b[1]))
                        q[2], q[3] = min(MW, max(q[2], b[2])), min(MH, max(q[3], b[3]))
                        merged = True
        bg = self.bg
        for x0, y0, x1, y1 in boxes:
            wb = (x1 - x0) * 2
            full = (1 << (8 * wb)) - 1
            sps = [(s[2], x, y, s[1]) for _, s, x, y in cur if x < x1 and x + s[0] > x0 and y < y1 and y + s[1] > y0]
            for r in range(y0, y1):
                o = r * MS + x0 * 2
                row = int.from_bytes(bg[o:o + wb], "little")
                for rows, sx, sy, sh_ in sps:
                    j = r - sy
                    if 0 <= j < sh_:
                        pv, mk = rows[j]
                        sh = (sx - x0) * 16
                        if sh >= 0:
                            pv <<= sh
                            mk <<= sh
                        else:
                            pv >>= -sh
                            mk >>= -sh
                        row ^= (row ^ pv) & mk & full
                so = (OY + r) * S + (OX + x0) * 2
                fb[so:so + wb] = row.to_bytes(wb, "little")

    def hud(self):
        c = self.hud_cache

        def text(key, s, x, y, size="S", color=COLOR_WHITE):
            if c.get(key) != s:
                c[key] = s
                draw_text(s, x, y, size, color)

        if self.hud_dirty:
            self.hud_dirty = False
            draw_text("SCORE", 60, 90, "S", COLOR_WHITE)
            draw_text("HIGH SCORE", 60, 280, "S", COLOR_RED)
            draw_text("LEVEL", 60, 470, "S", COLOR_WHITE)
            draw_text("LIVES", 1510, 90, "S", COLOR_YELLOW)
            draw_text("FRUIT", 1510, 470, "S", COLOR_GREEN)
            fill_rect(1510, 140, 460, 50, 0)
            for i in range(min(self.lives - 1, 8)):
                blit(LIFE_S, 1510 + i * 52, 142)
            fill_rect(1510, 520, 460, 52, 0)
            for i, k in enumerate(self.fruit_history):
                blit(FRUIT_SMALL_S[k], 1510 + i * 52, 520)
        text("score", "%d" % self.score, 60, 140, "L", COLOR_WHITE)
        text("high", "%d" % self.high, 60, 330, "L", COLOR_WHITE)
        text("level", "%d" % self.level, 60, 520, "L", COLOR_YELLOW)

    def step(self):
        self.ticks += 1
        if self.end is not None:
            return self.end.tick()
        over = False
        for _ in range(FRAMES_PER_TICK):
            if self.frame():
                over = True
        if self.score >= TARGET_SCORE or over or self.ticks >= CAP_TICKS - 200:
            self.render()
            self.hud()
            self.end = EndScreen()
            self.end.start(self.score, "GAME OVER" if self.lives <= 0 else "WELL PLAYED")
            return False
        self.render()
        self.hud()
        return False


def make():
    clear(0)
    game = Game()
    game.hud()
    return game.step
