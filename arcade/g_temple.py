# Endless temple runner in the spirit of Temple Run (Imangi, 2011): a third-person view from behind the explorer,
# a ground plane drawn by scanlines (rectangle/row intersections, so 90 degree corners and T-junctions swing the
# camera for real), roadside jungle sprites scaled by distance, three demon apes that close in after a stumble,
# coins, power-ups and a bot that reads the path, times jumps and slides, turns at corners and eventually dies.
# One virtual pixel (vpx) is 6x6 screen pixels: one ground row is a few colour runs written to 6 scanlines.
import gc
import math
from bisect import bisect_left, bisect_right
from fbcore import *

D = load_bundle("g_temple.bin")
# millions of sprite span tuples would make every full garbage collection a visible hitch
gc.collect()
gc.freeze()

PX, VW, VH = 6, 120, 180       # the portrait play window in virtual pixels (720x1080 screen pixels)
CX = VW // 2
ROWB = VW * 12                 # bytes of one vpx row of the window
WX = (W - VW * PX) // 2        # screen x of the window
WB = WX * 2                    # the same as a byte offset inside a scanline
F = 90.0                       # focal length in vpx
HCAM = 6.1                     # camera height in metres
K = F * HCAM                   # a ground row dy below the horizon sees depth K / dy
HZ = 50                        # horizon vrow
NDY = VH - 1 - HZ              # ground rows below the horizon
CAMBACK = 5.5                  # the camera is this far behind the explorer
ZMAX = 90.0
HALF = 1.6                     # half width of the path in metres
LANES = (-1.0, 0.0, 1.0)
WALL_H = 1.3                   # height of the carved side walls
WALL_K = HCAM / (HCAM - WALL_H)
PANO = 576                     # vpx of one full turn of the camera
DIRS = ((0, 1), (1, 0), (0, -1), (-1, 0))
TILE = 1.4                     # slab course length in metres
SLAB = 0.8                     # slab width in metres
KD = [0.0] + [K / dy for dy in range(1, NDY + 1)]
KD6 = [0.0] + [K / (dy + 0.6) for dy in range(1, NDY + 1)]
SC = [dy / HCAM for dy in range(NDY + 1)]    # vpx per metre of a ground row
ZB = D["zb"]
ZIDX = [0] * 400               # index of the distance bucket for a depth z, in half metre steps
for _i in range(400):
    ZIDX[_i] = min(len(ZB) - 1, max(0, bisect_left(ZB, _i / 2.0 + 0.25) - 1))
DT = 1.0 / TICK_RATE
GRAV, JUMP_V = 32.7, 12.3      # a jump lasts 0.75 s and peaks at 2.3 m
SLIDE_TICKS = 18


def fog_t(z):
    # same curve as the sprite builder, so ground and sprites fade together
    return min(0.92, max(0.0, (z - 12.0) / 78.0) ** 1.1)


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def speed_at(dist):
    return 8.5 + 9.0 * (1.0 - math.exp(-dist / 2200.0))


def hsh(a, b):
    return ((a * 73856093) ^ (b * 19349663)) & 0xFFFF


def make_ground_palette(tp):
    # per ground row: six water/ground variants (full rows with glow streaks), four slab tones, joint, grass, pit,
    # two wall face tones and the wall top, all already blended with the fog of that depth
    raw = tp["pal"]["raw"]
    fogc = tp["pal"]["fog"]
    rnd = random.Random(5)
    rows = [None]
    for dy in range(1, NDY + 1):
        t = fog_t(K / dy)

        def col(c):
            return rgb565(*[int(c[i] + (fogc[i] - c[i]) * t) for i in range(3)]).to_bytes(2, "little") * 6

        def cc(c):
            return tuple(int(c[i] + (fogc[i] - c[i]) * t) for i in range(3))
        g0, g1 = raw["ground"]
        variants = []
        for _ in range(6):
            base = bytearray(col(g0 if rnd.random() < 0.5 else g1) * VW)
            streak = rgb565(*cc(tuple((raw["glow"][i] + g1[i]) // 2 for i in range(3)))).to_bytes(2, "little") * 6
            if dy >= 12:
                for _ in range(max(2, VW // 14)):
                    w = max(1, int(SC[dy] * rnd.uniform(0.3, 1.1)))
                    x = rnd.randrange(VW)
                    base[x * 12:(x + w) * 12] = streak * min(w, VW - x)
            variants.append(bytes(base[:ROWB]))
        slabs = tuple(col(c) for c in raw["slab"])
        if dy < 26:
            avg = tuple(sum(c[i] for c in raw["slab"]) // 4 for i in range(3))
            slabs = (col(avg),) * 4
        rows.append((variants, slabs, col(raw["joint"]), col(raw["grass"]), col(raw["pit"]), col(raw["face"][0]),
                     col(raw["face"][1]), col(raw["wtop"]), col(raw["wjoint"])))
    return rows


# ---- the track ---------------------------------------------------------------------------------------------
class Seg:
    __slots__ = ("px", "py", "h", "L", "d0", "theme", "turn", "kids", "parent", "expanded", "obs", "obs_s", "coins",
                 "coin_s", "scen", "scen_s", "holes", "pick")


class Ob:
    # a hazard on a segment; s0..s1 along the path, lat0..lat1 across, y0..y1 above the ground
    __slots__ = ("kind", "s0", "s1", "lat0", "lat1", "y0", "y1", "hit", "alive", "acted", "slide")

    def __init__(self, kind, s0, s1, lat0, lat1, y0, y1, hit):
        self.kind, self.s0, self.s1, self.lat0, self.lat1, self.y0, self.y1, self.hit = kind, s0, s1, lat0, lat1, y0, y1, hit
        self.alive = True
        self.acted = False
        self.slide = False


# kind: (depth, y0, y1, lateral width, consequence)
OBK = {
    "root_small": (0.9, 0.0, 0.6, 1.0, "stumble"),
    "root_big": (1.0, 0.0, 1.4, 2.0, "die"),
    "overhang": (1.0, 0.55, 3.2, 3.2, "die"),
    "gate": (1.0, 0.6, 1.2, 3.2, "die"),
    "fire": (1.0, 0.0, 1.0, 1.0, "die"),
}


def seg_world(seg, s, lat):
    fx, fy = DIRS[seg.h]
    rx, ry = DIRS[(seg.h + 1) % 4]
    return seg.px + fx * s + rx * lat, seg.py + fy * s + ry * lat


def new_seg(parent, h, px, py, d0, first=False):
    sg = Seg()
    sg.px, sg.py, sg.h, sg.d0, sg.parent = px, py, h, d0, parent
    sg.theme = int(d0 // 1100) % 3
    sg.L = 150.0 if first else float(random.randint(58, 112))
    sg.turn = "T" if (not first and d0 > 250 and random.random() < 0.3) else "L"
    sg.kids = []
    sg.expanded = False
    sg.holes = []
    sg.pick = []
    fill_seg(sg, first)
    return sg


def expand(sg):
    if sg.expanded:
        return
    sg.expanded = True
    fx, fy = DIRS[sg.h]
    ex, ey = sg.px + fx * sg.L, sg.py + fy * sg.L
    d1 = sg.d0 + sg.L
    if sg.turn == "L":
        sg.kids = [new_seg(sg, (sg.h + random.choice((-1, 1))) % 4, ex, ey, d1)]
    else:
        sg.kids = [new_seg(sg, (sg.h - 1) % 4, ex, ey, d1), new_seg(sg, (sg.h + 1) % 4, ex, ey, d1)]


def extend_chain(sg):
    # keep single-exit corners expanded far enough ahead for the ground to show the path to the horizon
    total = 0.0
    cur = sg
    while cur is not None and total < 330:
        expand(cur)
        total += cur.L
        cur = cur.kids[0] if len(cur.kids) == 1 else None


def fill_seg(sg, first):
    L, d0 = sg.L, sg.d0
    obs, coins, scen = [], [], []
    v = speed_at(d0 + 40)
    mingap = v * 0.85 + 5.0
    s = 34.0 if first else 22.0
    end = L - 30.0
    while s < end:
        d = d0 + s
        pool = ["root_small", "root_small", "root_small", "overhang", "gate"]
        if d > 120:
            pool += ["gap", "root_big", "fire", "root_small"]
        if d > 400:
            pool += ["gap", "fire", "root_big"]
        kind = random.choice(pool)
        if kind == "gap":
            ln = random.choice((3.0, 3.5, 4.0, 4.5))
            side = random.random()
            lat0, lat1 = (-HALF, HALF) if side < 0.6 else (-HALF, -0.5) if side < 0.8 else (0.5, HALF)
            ob = Ob("gap", s, s + ln, lat0, lat1, 0.0, 0.0, "fall")
            obs.append(ob)
            sg.holes.append(ob)
            used = ln
        elif kind in ("root_small", "fire"):
            lanes = random.sample(LANES, 1 if kind == "root_small" or random.random() < 0.5 else 2)
            dep, y0, y1, wd, hit = OBK[kind]
            for ln in lanes:
                obs.append(Ob(kind, s, s + dep, ln - wd / 2, ln + wd / 2, y0, y1, hit))
            used = dep
        elif kind == "root_big":
            dep, y0, y1, wd, hit = OBK[kind]
            c = random.choice((-0.5, 0.5))
            obs.append(Ob(kind, s, s + dep, c - wd / 2, c + wd / 2, y0, y1, hit))
            used = dep
        else:
            dep, y0, y1, wd, hit = OBK[kind]
            ob = Ob(kind, s, s + dep, -HALF, HALF, y0, y1, hit)
            ob.slide = kind == "overhang" or random.random() < 0.5
            obs.append(ob)
            used = dep
        mid = s + used / 2
        # a coin arc follows the jump arc, so a bot that jumps well also collects it
        if kind in ("root_small", "root_big", "fire", "gap", "gate") and random.random() < 0.6 and not (kind == "gate" and obs[-1].slide):
            lane = random.choice(LANES) if kind in ("gate", "gap") else (obs[-1].lat0 + obs[-1].lat1) / 2
            lane = clamp(lane, -1.0, 1.0)
            for k in range(-3, 4):
                t = k / 3.0
                coins.append([mid + t * v * 0.3, lane, 0.55 + 1.7 * (1 - t * t), 1])
        elif kind == "overhang":
            for k in range(-2, 3):
                coins.append([mid + k * 1.6, random.choice(LANES) if k == -2 else coins[-1][1] if coins and k != -2 else 0.0, 0.35, 1])
        s += used + mingap + random.uniform(0, 22)
    # coin patterns in the gaps between the hazards
    s = 14.0
    while s < L - 14:
        lane = random.choice(LANES)
        n = random.randint(5, 15)
        zig = random.random() < 0.25
        for k in range(n):
            cs = s + k * 1.7
            if cs > L - 10:
                break
            lat = clamp(lane + (1.0 * math.sin(k * 0.55) if zig else 0.0), -1.1, 1.1)
            coins.append([cs, lat, 0.9, 1])
        s += n * 1.7 + random.uniform(16, 46)
    # drop coins that sit inside a hazard
    keep = []
    for c in coins:
        ok = True
        for ob in obs:
            if ob.kind != "gap" and ob.s0 - 1.0 < c[0] < ob.s1 + 1.0 and ob.lat0 - 0.4 < c[1] < ob.lat1 + 0.4 and c[2] < ob.y1 + 0.6 \
                    and not (ob.kind in ("root_small", "root_big", "fire", "gate") and c[2] > ob.y1 + 0.2):
                ok = False
                break
            if ob.kind == "gap" and ob.s0 - 0.3 < c[0] < ob.s1 + 0.3 and ob.lat0 < c[1] < ob.lat1 and c[2] < 1.0:
                ok = False
                break
        if ok and (c[2] >= 1.0 or c[0] > 8):
            keep.append(c)
    coins = keep
    coins.sort(key=lambda c: c[0])
    obs.sort(key=lambda o: o.s0)
    sg.obs, sg.obs_s = obs, [o.s0 for o in obs]
    sg.coins, sg.coin_s = coins, [c[0] for c in coins]
    # scenery: dense trees near the path, sparse further out, posts along both edges, the odd ruin
    x = -4.0
    while x < L + 4:
        for side in (-1, 1):
            if random.random() < 0.5 and not (L - HALF - 3.5 < x < L + HALF + 3.5) and not (-HALF - 3.5 < x < HALF + 3.5):
                lat = side * (HALF + 1.3 + random.random() ** 1.6 * 8.0)
                scen.append((x + random.uniform(-1, 1), lat, 0, random.randrange(5)))
        x += random.uniform(2.6, 5.0)
    x = 0.0
    while x < L:
        scen.append((x, -(HALF + 0.3), 2, 0))
        scen.append((x + 3.5, HALF + 0.3, 2, 0))
        x += 7.0
    x = random.uniform(8, 30)
    while x < L - HALF - 3:
        side = random.choice((-1, 1))
        scen.append((x, side * (HALF + random.uniform(1.8, 4.5)), 1, random.randrange(4)))
        x += random.uniform(25, 60)
    scen.append((L + HALF + 0.5, 0.0, 3, 0))
    scen.sort(key=lambda t: t[0])
    sg.scen, sg.scen_s = scen, [t[0] for t in scen]


def place_pickups(sg, state):
    # one power-up whenever the run passes the next pickup distance; kept clear of hazards
    nxt = state["next_pick"]
    if sg.d0 <= nxt < sg.d0 + sg.L - 40:
        s = nxt - sg.d0
        lane = random.choice(LANES)
        for _ in range(6):
            lane = random.choice(LANES)
            if all(not (o.s0 - 6 < s < o.s1 + 6 and o.lat0 - 0.5 < lane < o.lat1 + 0.5) for o in sg.obs):
                break
        kind = random.choice(("magnet", "boost", "shield", "mega", "magnet", "shield"))
        sg.pick.append([s, lane, 1.1, kind, 1])
        state["next_pick"] = nxt + random.uniform(450, 800)


# ---- the game -----------------------------------------------------------------------------------------------
def make():
    themes = D["themes"]
    gpal = [make_ground_palette(t) for t in themes]
    runner_sp = D["runner"]
    state = {"tick": 0, "phase": "run", "t": 0, "run": 0, "best": 0, "coins_all": 0, "score": 0, "next_pick": 380.0,
             "target": random.randint(33000, 40000)}
    R = {}
    cam = {"yaw": 0.0, "aligned": True, "x": 0.0, "y": 0.0}
    O = {"seg": None, "theme": -1}
    fly = []
    end = EndScreen()
    sky = {"touched": set(), "last_off": -1, "fresh": True}

    # ---- run setup ------------------------------------------------------------------------------------------
    def start_run():
        state["run"] += 1
        state["next_pick"] = random.uniform(300, 520)
        root = new_seg(None, 0, 0.0, 0.0, 0.0, first=True)
        place_pickups(root, state)
        O["seg"] = root
        extend_chain(root)
        mode = random.choice(("skip", "skip", "skip", "late_turn", "late_turn", "early_jump", "clip", "clip", "clip"))
        if state["tick"] > CAP_TICKS - 900:
            doom = 0.0
        else:
            doom = random.uniform(1300, 3000)
        R.update(s=0.0, lat=0.0, y=0.0, vy=0.0, v=0.0, slide=0, stumble=0, mg=1.0, mgv=0.015, dist=0.0, coins=0, run_t=0,
                 magnet=0, boost=0, shield=0, pose=0.0, tlat=0.0, doom_d=doom, doom_mode=mode, doom_on=False, doom_from=0.0,
                 lane_t=0, dead=None, dead_t=0, invuln=0, turned=0, fx=0)
        cam["yaw"] = 0.0
        cam["aligned"] = True
        fly.clear()
        O["theme"] = -1
        sky["fresh"] = True
        sky["last_off"] = -1
        apply_theme()

    def apply_theme():
        th = O["seg"].theme
        if th != O["theme"]:
            O["theme"] = th
            O["gp"] = gpal[th]
            O["tp"] = themes[th]
            sky["fresh"] = True
            sky["last_off"] = -1
            draw_sides(O["tp"]["side"])

    def draw_sides(side):
        # blurred, dimmed, mirrored scene in the bands beside the portrait window, and a golden window frame
        left, right = side
        n = WX * 2
        for y in range(H):
            o = y * S
            fb[o:o + n] = left[y * n:(y + 1) * n]
            fb[o + S - n:o + S] = right[y * n:(y + 1) * n]
        gold = rgb565(190, 140, 40)
        fill_rect(WX - 6, 0, 6, H, gold)
        fill_rect(WX + VW * PX, 0, 6, H, gold)

    # ---- runner physics -------------------------------------------------------------------------------------
    def kill(kind):
        R["dead"] = kind
        R["dead_t"] = 0
        R["fx"] = 0

    def stumble():
        if R["shield"]:
            R["shield"] = 0
            R["invuln"] = 20
            return
        if R["mg"] < 3.4:
            kill("caught")
            return
        R["stumble"] = 14
        R["v"] *= 0.55
        R["mg"] = 1.4
        R["mgv"] = 0.012
        R["slide"] = 0

    def hit_ob(ob):
        if R["boost"] or R["invuln"]:
            return
        if ob.hit == "stumble":
            ob.alive = False
            stumble()
        else:
            if R["shield"]:
                R["shield"] = 0
                R["invuln"] = 20
                ob.alive = False
                return
            ob.alive = False
            kill("hit")

    def do_turn(seg, kid_i):
        kid = seg.kids[kid_i]
        R["turned"] += 1
        R["dist"] = kid.d0
        for c in fly:
            R["coins"] += 1
        fly.clear()
        # unchosen arms lose their continuation so the renderer shows plain dead ends
        for k in seg.kids:
            if k is not kid:
                k.kids = []
                k.expanded = True
        O["seg"] = kid
        R["s"] = 0.0
        R["lat"] = 0.0
        extend_chain(kid)
        place_pickups(kid, state)
        for k in kid.kids:
            place_pickups(k, state)
        apply_theme()
        target = kid.h * math.pi / 2
        # unwrap so the camera always swings the short way round
        while target - cam["yaw"] > math.pi:
            target -= 2 * math.pi
        while target - cam["yaw"] < -math.pi:
            target += 2 * math.pi
        cam["target"] = target
        cam["aligned"] = False

    # ---- the bot -----------------------------------------------------------------------------------------------
    def upcoming(seg, s, reach):
        i = bisect_left(seg.obs_s, s - 3.0)
        out = []
        while i < len(seg.obs) and seg.obs[i].s0 < s + reach:
            o = seg.obs[i]
            if o.alive:
                out.append(o)
            i += 1
        return out

    def lane_cost(seg, s, v):
        reach = max(42.0, v * 2.2)
        obs = upcoming(seg, s, reach)
        cost = {ln: 0.0 for ln in LANES}
        # a doomed run stops looking at hazards, which is how the explorer ends up clipping or hitting them
        if R["doom_on"] and R["doom_mode"] != "late_turn":
            obs = []
        for ln in LANES:
            for o in obs:
                if o.lat0 < ln + 0.55 and o.lat1 > ln - 0.55 and o.s1 > s:
                    cost[ln] += 3.0 if o.kind != "gap" else 3.5
            i = bisect_left(seg.coin_s, s + 1.0)
            n = 0
            while i < len(seg.coins) and seg.coins[i][0] < s + reach and n < 16:
                c = seg.coins[i]
                if c[3] and abs(c[1] - ln) < 0.55:
                    cost[ln] -= 0.3
                    n += 1
                i += 1
            for p in seg.pick:
                if p[4] and s < p[0] < s + reach and abs(p[1] - ln) < 0.55:
                    cost[ln] -= {"magnet": 8.0, "shield": 8.0, "mega": 6.0, "boost": 5.0}[p[3]]
        return cost

    def bot(seg, v):
        s, lat = R["s"], R["lat"]
        dist_end = seg.L - s
        R["lane_t"] -= 1
        if R["lane_t"] <= 0:
            R["lane_t"] = 5
            cost = lane_cost(seg, s, v)
            cost[R["tlat"]] -= 1.0
            best = min(LANES, key=lambda ln: cost[ln] + 0.5 * abs(ln - R["tlat"]))
            if best != R["tlat"]:
                # do not slip into a lane whose hazard is already too close to clear
                danger = any(o.lat0 < best + 0.55 and o.lat1 > best - 0.55 and 0 < o.s0 - s < v * 0.5 for o in upcoming(seg, s, v * 0.6))
                if not danger and R["y"] == 0.0:
                    R["tlat"] = best
        tl = R["tlat"]
        if dist_end < 16:
            tl = 0.0
        R["aim"] = tl
        # hazards in the band the runner occupies
        doom = R["doom_on"]
        for o in upcoming(seg, s, 45.0):
            if o.acted:
                continue
            if not (o.lat0 < lat + 0.5 and o.lat1 > lat - 0.5):
                continue
            mid = (o.s0 + o.s1) / 2
            if o.kind == "gap":
                lead = v * 0.375
                if doom and R["doom_mode"] == "early_jump":
                    lead += v * 1.0
                if mid - s <= lead:
                    o.acted = True
                    if doom and R["doom_mode"] == "skip":
                        continue
                    jump()
            elif o.kind == "overhang" or (o.kind == "gate" and o.slide):
                if o.s0 - s <= v * 0.2:
                    o.acted = True
                    if skip_action(o):
                        continue
                    slide()
            else:
                if mid - s <= v * 0.36:
                    o.acted = True
                    if skip_action(o):
                        continue
                    jump()
            break
        if dist_end <= 0.15 and seg.kids:
            skip = doom and (R["doom_mode"] == "late_turn" or R["dist"] - R["doom_from"] > (600 if R["doom_mode"] == "clip" else 220))
            if not skip:
                choose_turn(seg)

    def skip_action(o):
        if R["doom_on"] and (R["doom_mode"] in ("skip", "early_jump") or (R["doom_mode"] == "clip" and (
                o.kind == "root_small" or R["mg"] < 3.4))):
            return True
        # now and then the explorer clips a small root: monkeys close in but only if they are far enough back
        if o.kind == "root_small" and R["mg"] > 5.0 and not R["stumble"] and random.random() < 0.2:
            return True
        return False

    def choose_turn(seg):
        if len(seg.kids) == 1:
            do_turn(seg, 0)
            return

        def value(k):
            sc = 0.0
            for c in k.coins[:40]:
                sc += 1.0
            for p in k.pick:
                sc += 12.0
            return sc + random.uniform(0, 14)
        do_turn(seg, max(range(len(seg.kids)), key=lambda i: value(seg.kids[i])))

    def jump():
        if R["y"] == 0.0 and R["vy"] == 0.0 and not R["stumble"]:
            R["vy"] = JUMP_V
            R["slide"] = 0

    def slide():
        if R["y"] == 0.0 and not R["stumble"]:
            R["slide"] = SLIDE_TICKS

    def update_run():
        seg = O["seg"]
        R["run_t"] += 1
        v0 = speed_at(R["dist"])
        if R["doom_d"] and not R["doom_on"] and R["dist"] >= R["doom_d"]:
            R["doom_on"] = True
            R["doom_from"] = R["dist"]
        if state["tick"] > CAP_TICKS - 240 or state["score"] >= state["target"]:
            if not R["doom_on"]:
                R["doom_on"] = True
                R["doom_from"] = R["dist"]
        # speed: boost overrides, a stumble drags it down and it recovers
        if R["boost"]:
            R["boost"] -= 1
            v0 *= 1.6
        if R["stumble"]:
            R["stumble"] -= 1
        warm = min(1.0, R["run_t"] / 45.0)
        target_v = v0 * warm
        if R["stumble"]:
            target_v *= 0.55
        R["v"] += clamp(target_v - R["v"], -0.9, 0.35)
        v = R["v"]
        bot(seg, v)
        if R["dead"]:
            return
        # lateral motion toward the lane the bot wants
        aim = R["aim"]
        dl = clamp(aim - R["lat"], -0.12, 0.12)
        R["lat"] += dl
        R["pose"] += v * DT * 0.62
        # vertical motion
        if R["vy"] != 0.0 or R["y"] > 0.0:
            R["vy"] -= GRAV * DT
            R["y"] += R["vy"] * DT
            if R["boost"]:
                R["y"] = max(R["y"], 0.9 + 0.2 * math.sin(R["run_t"] * 0.3))
                R["vy"] = 0.0
            if R["y"] <= 0.0 and not R["boost"]:
                R["y"], R["vy"] = 0.0, 0.0
        elif R["boost"]:
            R["y"], R["vy"] = 0.9, 0.0
        if R["slide"]:
            R["slide"] -= 1
        if R["invuln"]:
            R["invuln"] -= 1
        if R["magnet"]:
            R["magnet"] -= 1
        # advance
        ds = v * DT
        R["s"] += ds
        R["dist"] += ds
        state["score"] = max(state["score"], 0)
        s = R["s"]
        y = R["y"]
        lat = R["lat"]
        hr = 0.5 if R["slide"] else 1.7
        # collisions with hazards
        i = bisect_left(seg.obs_s, s - 2.5)
        while i < len(seg.obs) and seg.obs[i].s0 < s + 1.5:
            o = seg.obs[i]
            i += 1
            if not o.alive:
                continue
            if o.kind == "gap":
                if o.s0 + 0.35 < s < o.s1 - 0.35 and lat + 0.35 > o.lat0 + 0.05 and lat - 0.35 < o.lat1 - 0.05 and y <= 0.05:
                    if R["boost"]:
                        continue
                    kill("fell")
                    return
                continue
            if o.s0 - 0.3 < s < o.s1 + 0.3 and o.lat0 < lat + 0.4 and o.lat1 > lat - 0.4 and y < o.y1 and y + hr > o.y0:
                hit_ob(o)
                if R["dead"]:
                    return
        if abs(lat) > HALF + 0.15:
            kill("fell")
            return
        # a corner that was not taken ends in the jungle wall
        if s > seg.L + HALF - 0.4:
            if R["boost"]:
                choose_turn(seg)
            else:
                kill("hit")
            return
        # coins, pick-ups and the magnet
        c0 = bisect_left(seg.coin_s, s - 1.2)
        mag = R["magnet"] > 0
        while c0 < len(seg.coins) and seg.coins[c0][0] < s + (9.0 if mag else 1.2):
            c = seg.coins[c0]
            c0 += 1
            if not c[3]:
                continue
            dsx, dly = c[0] - s, c[1] - lat
            if mag and 0 < dsx < 9.0 and abs(dly) < 2.4:
                c[3] = 0
                fly.append([dsx, dly, c[2] - y, 1])
                continue
            if abs(dsx) < 0.9 and abs(dly) < 0.6 and y - 0.4 < c[2] < y + 1.9:
                c[3] = 0
                R["coins"] += 1
        for p in seg.pick:
            if p[4] and abs(p[0] - s) < 1.1 and abs(p[1] - lat) < 0.7 and y < 1.9:
                p[4] = 0
                kind = p[3]
                if kind == "magnet":
                    R["magnet"] = 8 * TICK_RATE
                elif kind == "boost":
                    R["boost"] = 5 * TICK_RATE
                    R["stumble"] = 0
                elif kind == "shield":
                    R["shield"] = 1
                else:
                    R["coins"] += 10
        # coins pulled in by the magnet fly in runner-relative coordinates
        for f in fly:
            f[0] *= 0.62
            f[1] *= 0.62
            f[2] *= 0.7
            f[3] += 1
        done = [f for f in fly if abs(f[0]) < 0.7 and abs(f[1]) < 0.7]
        if done:
            R["coins"] += len(done)
            fly[:] = [f for f in fly if f not in done]
        # the monkeys drop back while the explorer runs clean; beyond 2.6 m they are behind the camera
        if R["mg"] < 8.0:
            R["mg"] += R["mgv"]

    # ---- dying and results ------------------------------------------------------------------------------------
    def update_dying():
        R["dead_t"] += 1
        t = R["dead_t"]
        R["v"] *= 0.9
        R["s"] += R["v"] * DT
        R["pose"] += R["v"] * DT * 0.3
        kind = R["dead"]
        if kind != "fell":
            R["mg"] = max(0.15, R["mg"] - 0.2) if t > 10 else R["mg"]
        if t > 70:
            go_card()

    def go_card():
        state["phase"] = "card"
        state["t"] = 0
        run_m = int(R["dist"])
        state["best"] = max(state["best"], run_m)
        state["coins_all"] += R["coins"]
        state["score"] = state["best"] + 50 * state["coins_all"]
        x0, y0 = W // 2 - 320, H // 2 - 250
        fill_rect(x0, y0, 640, 500, 0)
        fill_rect(x0, y0, 640, 6, rgb565(226, 170, 48))
        fill_rect(x0, y0 + 494, 640, 6, rgb565(226, 170, 48))
        draw_text_centered("GAME OVER", y0 + 30, "L", COLOR_RED)
        draw_text_centered("DISTANCE", y0 + 150, "S", COLOR_WHITE)
        draw_text_centered("%d M" % run_m, y0 + 195, "L", COLOR_WHITE)
        draw_text_centered("COINS %d" % R["coins"], y0 + 305, "L", COLOR_YELLOW)
        draw_text_centered("TOTAL %d" % state["score"], y0 + 420, "S", COLOR_CYAN)

    # ---- rendering -----------------------------------------------------------------------------------------------
    def camera():
        seg = O["seg"]
        if not cam["aligned"]:
            yaw = cam["yaw"]
            nx = cam["target"]
            cam["yaw"] = yaw = yaw + (nx - yaw) * 0.2
            if abs(nx - yaw) < 0.02:
                cam["yaw"] = yaw = nx
                cam["aligned"] = True
        yaw = cam["yaw"]
        fx, fy = math.sin(yaw), math.cos(yaw)
        rx, ry = math.cos(yaw), -math.sin(yaw)
        wx, wy = seg_world(seg, R["s"], R["lat"])
        cam["x"] = wx - fx * CAMBACK - rx * 0.3 * R["lat"]
        cam["y"] = wy - fy * CAMBACK - ry * 0.3 * R["lat"]
        cam["fx"], cam["fy"], cam["rx"], cam["ry"] = fx, fy, rx, ry

    def visible(seg, s):
        out = [(seg, -s)]
        if seg.parent is not None and s < 22:
            par = seg.parent
            out.append((par, -(par.L + s)))
            for sib in par.kids:
                if sib is not seg:
                    out.append((sib, -s))
        stack = [(seg, seg.L - s)]
        while stack:
            sg, dist = stack.pop()
            if dist > 420:
                continue
            for k in sg.kids:
                out.append((k, dist))
                stack.append((k, dist + k.L))
        return out

    def rect_of(sg, pad):
        fx, fy = DIRS[sg.h]
        ex, ey = sg.px + fx * sg.L, sg.py + fy * sg.L
        return (min(sg.px, ex) - pad, min(sg.py, ey) - pad, max(sg.px, ex) + pad, max(sg.py, ey) + pad)

    def walls_of(sg):
        # carved side walls: a footprint rect plus a point on the path-facing edge, for both sides
        if sg.L < 2 * HALF + 3:
            return []
        a = HALF + 0.4 if sg.parent is not None else -HALF
        b = sg.L - HALF - 0.4
        out = []
        for side in (-1, 1):
            ax, ay = seg_world(sg, a, side * (HALF + 0.05))
            bx, by = seg_world(sg, b, side * (HALF + 0.6))
            ix, iy = seg_world(sg, a, side * (HALF + 0.05))
            out.append((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), ix, iy))
        return out

    def paint_ground(vis, pal):
        cx, cy = cam["x"], cam["y"]
        fxc, fyc, rxc, ryc = cam["fx"], cam["fy"], cam["rx"], cam["ry"]
        paths, holes, walls = [], [], []
        for sg, dist in vis:
            paths.append(rect_of(sg, HALF))
            for o in sg.holes:
                ax, ay = seg_world(sg, o.s0, o.lat0)
                bx, by = seg_world(sg, o.s1, o.lat1)
                holes.append((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)))
            if dist < 160:
                walls.extend(walls_of(sg))
        lc = cx * fxc + cy * fyc
        nrow = [0] * (NDY + 2)
        rows = [None] * (NDY + 1)
        joint = [False] * (NDY + 2)
        for dy in range(1, NDY + 1):
            z = KD[dy]
            nrow[dy] = int((lc + z) // TILE)
            rows[dy] = bytearray(pal[dy][0][(hsh(int((lc + z) // 0.9), 7) % 6) if dy > 30 else dy % 6])
            if dy >= 26:
                joint[dy] = nrow[dy] != int((lc + KD6[dy]) // TILE)

        def path_row(dy, slo, shi):
            sc = SC[dy]
            ra = int(CX + slo * sc)
            rb = int(CX + shi * sc)
            a = ra if ra > 0 else 0
            b = rb if rb < VW else VW
            if b <= a:
                return
            p = pal[dy]
            row = rows[dy]
            if dy < 26:
                row[a * 12:b * 12] = p[1][0] * (b - a)
                return
            if joint[dy]:
                row[a * 12:b * 12] = p[2] * (b - a)
                return
            n = nrow[dy]
            slabs = p[1]
            jc = p[2]
            # slab boundaries are laid out from the path's left edge, shifted by half a slab on alternate courses
            x = a
            lo = slo + (0.0 if n & 1 else SLAB * 0.5)
            k = -1 if n & 1 == 0 else 0
            while x < b:
                hi = lo + SLAB
                nx = int(CX + hi * sc)
                if nx <= x:
                    lo = hi
                    k += 1
                    continue
                if nx > b:
                    nx = b
                row[x * 12:nx * 12] = slabs[hsh(n, k) & 3] * (nx - x)
                row[x * 12:x * 12 + 12] = jc
                x = nx
                lo = hi
                k += 1
            # grass creeping in from the edges, different on every course
            g = p[3]
            gl = max(1, int((0.1 + 0.2 * (hsh(n, 5) % 5) / 4.0) * sc))
            gr = max(1, int((0.1 + 0.2 * (hsh(n, 6) % 5) / 4.0) * sc))
            if a < b - gl - gr:
                if ra >= 0:
                    row[a * 12:(a + gl) * 12] = g * gl
                if rb <= VW:
                    row[(b - gr) * 12:b * 12] = g * gr

        aligned = cam["aligned"]
        k = WALL_K
        if aligned:
            for (x0, y0, x1, y1) in paths:
                z1 = (x0 - cx) * fxc + (y0 - cy) * fyc
                z2 = (x1 - cx) * fxc + (y1 - cy) * fyc
                s1 = (x0 - cx) * rxc + (y0 - cy) * ryc
                s2 = (x1 - cx) * rxc + (y1 - cy) * ryc
                zlo, zhi = (z1, z2) if z1 < z2 else (z2, z1)
                slo, shi = (s1, s2) if s1 < s2 else (s2, s1)
                if zhi <= 0:
                    continue
                dlo = max(1, int(K / zhi) + 1)
                dhi = NDY if zlo <= K / NDY else min(NDY, int(K / zlo))
                for dy in range(dlo, dhi + 1):
                    path_row(dy, slo, shi)
            for (x0, y0, x1, y1) in holes:
                z1 = (x0 - cx) * fxc + (y0 - cy) * fyc
                z2 = (x1 - cx) * fxc + (y1 - cy) * fyc
                s1 = (x0 - cx) * rxc + (y0 - cy) * ryc
                s2 = (x1 - cx) * rxc + (y1 - cy) * ryc
                zlo, zhi = (z1, z2) if z1 < z2 else (z2, z1)
                slo, shi = (s1, s2) if s1 < s2 else (s2, s1)
                if zhi <= 0:
                    continue
                dlo = max(1, int(K / zhi) + 1)
                dhi = NDY if zlo <= K / NDY else min(NDY, int(K / zlo))
                for dy in range(dlo, dhi + 1):
                    sc = SC[dy]
                    a = max(0, int(CX + slo * sc))
                    b = min(VW, int(CX + shi * sc))
                    if b > a:
                        rows[dy][a * 12:b * 12] = pal[dy][4] * (b - a)
            for (x0, y0, x1, y1, ix, iy) in walls:
                z1 = (x0 - cx) * fxc + (y0 - cy) * fyc
                z2 = (x1 - cx) * fxc + (y1 - cy) * fyc
                zlo, zhi = (z1, z2) if z1 < z2 else (z2, z1)
                if zhi <= 0:
                    continue
                s_in = (ix - cx) * rxc + (iy - cy) * ryc
                s_out = (x0 - cx) * rxc + (y0 - cy) * ryc
                s_out2 = (x1 - cx) * rxc + (y1 - cy) * ryc
                # the path-facing face spans the footprint edge up to the same edge scaled by the wall height
                fa, fb_ = (s_in, s_in * k) if s_in < s_in * k else (s_in * k, s_in)
                dlo = max(1, int(K / (zhi * k)) + 1)
                dhi = NDY if zlo <= K / NDY else min(NDY, int(K / zlo))
                for dy in range(dlo, dhi + 1):
                    sc = SC[dy]
                    a = max(0, int(CX + fa * sc))
                    b = min(VW, int(CX + fb_ * sc))
                    if b > a:
                        p = pal[dy]
                        rows[dy][a * 12:b * 12] = (p[8] if joint[dy] else p[5 + (nrow[dy] & 1)]) * (b - a)
                so1, so2 = (s_out, s_out2) if s_out < s_out2 else (s_out2, s_out)
                dlo = max(1, int(K / (zhi * k)) + 1)
                dhi = NDY if zlo * k <= K / NDY else min(NDY, int(K / (zlo * k)))
                for dy in range(dlo, dhi + 1):
                    sc = SC[dy]
                    a = max(0, int(CX + so1 * k * sc))
                    b = min(VW, int(CX + so2 * k * sc))
                    if b > a:
                        p = pal[dy]
                        rows[dy][a * 12:b * 12] = (p[7] if nrow[dy] % 3 else p[5]) * (b - a)
        else:
            # mid-swing the rows cut the rectangles at an angle: slab clipping, with a tiny epsilon in place of a
            # division by zero when the camera is momentarily axis aligned
            if abs(rxc) < 1e-4:
                rxc = 1e-4
            if abs(ryc) < 1e-4:
                ryc = 1e-4
            irx, iry = 1.0 / rxc, 1.0 / ryc
            bxs = [cx + fxc * K / dy for dy in range(1, NDY + 1)]
            bys = [cy + fyc * K / dy for dy in range(1, NDY + 1)]
            sets = [(paths, 0), (holes, 1), ([(cx + (w[0] - cx) * k, cy + (w[1] - cy) * k, cx + (w[2] - cx) * k,
                                                cy + (w[3] - cy) * k) for w in walls], 2)]
            for rects, kind in sets:
                for (x0, y0, x1, y1) in rects:
                    for i in range(NDY):
                        bx = bxs[i]
                        by = bys[i]
                        t1 = (x0 - bx) * irx
                        t2 = (x1 - bx) * irx
                        u1 = (y0 - by) * iry
                        u2 = (y1 - by) * iry
                        if t1 > t2:
                            t1, t2 = t2, t1
                        if u1 > u2:
                            u1, u2 = u2, u1
                        lo = t1 if t1 > u1 else u1
                        hi = t2 if t2 < u2 else u2
                        if lo < hi:
                            dy = i + 1
                            if kind == 0:
                                path_row(dy, lo, hi)
                            else:
                                sc = SC[dy]
                                a = max(0, int(CX + lo * sc))
                                b = min(VW, int(CX + hi * sc))
                                if b > a:
                                    rows[dy][a * 12:b * 12] = (pal[dy][4] if kind == 1 else pal[dy][7]) * (b - a)
        return rows

    def sky_row(r, pano, off):
        rr = HZ - 1 if r >= HZ else r
        uni, data = pano[rr]
        if uni:
            return bytearray(data * VW)
        return bytearray(data[off * 12:off * 12 + ROWB])

    def put_row(vr, row):
        o = vr * PX * S + WB
        for _ in range(PX):
            fb[o:o + ROWB] = row
            o += S

    def render():
        seg = O["seg"]
        tp, gp = O["tp"], O["gp"]
        camera()
        vis = visible(seg, R["s"])
        rows = paint_ground(vis, gp)
        cx, cy = cam["x"], cam["y"]
        fxc, fyc, rxc, ryc = cam["fx"], cam["fy"], cam["rx"], cam["ry"]
        things = []
        # scenery, obstacles and coins of every visible segment
        for sg, dist in vis:
            if sg is seg:
                lo, hi = R["s"] - 10.0, R["s"] + ZMAX + 4
            elif dist < 0 and sg is seg.parent:
                lo, hi = sg.L - 14.0, sg.L + HALF + 2
            elif dist < 0:
                lo, hi = 0.0, 40.0
            else:
                lo, hi = -2.0, ZMAX + 6 - dist
            if hi <= lo:
                continue
            fx_, fy_ = DIRS[sg.h]
            rx_, ry_ = DIRS[(sg.h + 1) % 4]
            for i in range(bisect_left(sg.scen_s, lo), bisect_right(sg.scen_s, hi)):
                s_, lat_, kind, idx = sg.scen[i]
                wx = sg.px + fx_ * s_ + rx_ * lat_ - cx
                wy = sg.py + fy_ * s_ + ry_ * lat_ - cy
                z = wx * fxc + wy * fyc
                if z < 3.4 or z > ZMAX:
                    continue
                xc = wx * rxc + wy * ryc
                sx = CX + xc * F / z
                spr = tp["trees"][idx] if kind == 0 else tp["ruins"][idx] if kind == 1 else None
                if abs(sx - CX) > CX + 70 * (10.0 / z) + 24:
                    continue
                things.append((z, kind, sx, spr, 0.0))
            for o in sg.obs[bisect_left(sg.obs_s, lo - 2):bisect_right(sg.obs_s, hi)]:
                if o.kind == "gap" or not o.alive:
                    continue
                mid = (o.s0 + o.s1) / 2
                lat_ = (o.lat0 + o.lat1) / 2
                wx = sg.px + fx_ * mid + rx_ * lat_ - cx
                wy = sg.py + fy_ * mid + ry_ * lat_ - cy
                z = wx * fxc + wy * fyc
                if z < 3.4 or z > ZMAX:
                    continue
                xc = wx * rxc + wy * ryc
                things.append((z, 10, CX + xc * F / z, o.kind, 0.0))
            for c in sg.coins[bisect_left(sg.coin_s, lo):bisect_right(sg.coin_s, hi)]:
                if not c[3]:
                    continue
                wx = sg.px + fx_ * c[0] + rx_ * c[1] - cx
                wy = sg.py + fy_ * c[0] + ry_ * c[1] - cy
                z = wx * fxc + wy * fyc
                if z < 3.4 or z > ZMAX:
                    continue
                xc = wx * rxc + wy * ryc
                things.append((z, 11, CX + xc * F / z, 0, c[2]))
            for p in sg.pick:
                if not p[4] or not lo <= p[0] <= hi:
                    continue
                wx = sg.px + fx_ * p[0] + rx_ * p[1] - cx
                wy = sg.py + fy_ * p[0] + ry_ * p[1] - cy
                z = wx * fxc + wy * fyc
                if z < 3.4 or z > ZMAX:
                    continue
                xc = wx * rxc + wy * ryc
                things.append((z, 12, CX + xc * F / z, p[3], p[2] + 0.12 * math.sin(state["tick"] * 0.2)))
        # flying coins pulled by the magnet
        lat0 = R["lat"]
        for f in fly:
            z = CAMBACK + f[0]
            if z > 3.4:
                things.append((z, 11, CX + (0.3 * lat0 + f[1]) * F / z, 0, f[2] + R["y"] + 0.9))
        # the monkeys
        if R["dead"] != "fell" and R["mg"] < 2.1 + (3 if R["dead"] else 0):
            for off, (la, dz) in enumerate(((-0.9, 0.0), (0.05, 0.5), (0.95, -0.2))):
                z = CAMBACK - R["mg"] + dz
                if z > 3.4:
                    things.append((z, 20, CX + (0.3 * lat0 + la) * F / z, off, 0.0))
        things.append((CAMBACK, 30, CX + 0.3 * lat0 * (F / CAMBACK), 0, R["y"]))
        things.sort(key=lambda t: -t[0])
        tick = state["tick"]
        coin_f = (tick // 3) & 3
        yaw = cam["yaw"]
        soff = int(yaw * PANO / (2 * math.pi)) % PANO
        skyb = {}

        def patch(sp, cxp, foot):
            w, h, srows, ax, ay = sp
            x0 = cxp - ax
            top = foot - ay
            if x0 >= VW or x0 + w <= 0:
                return
            inside = x0 >= 0 and x0 + w <= VW
            for j in range(max(0, -top), min(h, VH - top)):
                spans = srows[j]
                if not spans:
                    continue
                vr = top + j
                if vr > HZ:
                    row = rows[vr - HZ]
                else:
                    row = skyb.get(vr)
                    if row is None:
                        row = skyb[vr] = sky_row(vr, tp["pano"], soff)
                if inside:
                    for sx, data in spans:
                        x = (x0 + sx) * 12
                        row[x:x + len(data)] = data
                    continue
                for sx, data in spans:
                    x = x0 + sx
                    n = len(data) // 12
                    if x < 0:
                        data = data[-x * 12:]
                        n += x
                        x = 0
                    if x + n > VW:
                        n = VW - x
                        data = data[:n * 12]
                    if n > 0:
                        row[x * 12:x * 12 + n * 12] = data

        for z, kind, sx, spr, hgt in things:
            zi = ZIDX[int(z * 2)]
            sxi = int(sx)
            foot = HZ + int((HCAM - hgt) * F / z)
            if kind <= 1:
                sp = spr["set"][zi]
            elif kind == 2:
                sp = tp["totem"][zi]
            elif kind == 3:
                sp = tp["wall"][zi]
            elif kind == 10:
                sp = tp["obst"]["fire"][(tick // 3) % 3][zi] if spr == "fire" else tp["obst"][spr][zi]
            elif kind == 11:
                sp = tp["coin"][(coin_f + int(sx)) & 3][zi]
                foot = HZ + int((HCAM - hgt + 0.31) * F / z)
            elif kind == 12:
                sp = tp["token"][spr][zi]
                foot = HZ + int((HCAM - hgt + 0.4) * F / z)
            elif kind == 20:
                sp = tp["ape"][((tick // 3) + int(sx)) & 1][zi]
            else:
                draw_runner(patch, sxi, hgt)
                continue
            if sp:
                patch(sp, sxi, foot)
        draw_hud(patch, rows, skyb)
        for dy in range(1, NDY + 1):
            put_row(HZ + dy, rows[dy])
        # sky rows: only those that move or carry a sprite
        prev = sky["touched"]
        full = sky["fresh"] or soff != sky["last_off"]
        for vr in range(0, HZ + 1):
            row = skyb.get(vr)
            if row is None:
                if not (full or vr in prev):
                    continue
                uni = tp["pano"][min(vr, HZ - 1)][0]
                if uni and not (sky["fresh"] or vr in prev):
                    continue
                row = sky_row(vr, tp["pano"], soff)
            put_row(vr, row)
        sky["touched"] = set(skyb)
        sky["last_off"] = soff
        sky["fresh"] = False

    def draw_runner(patch, sx, hgt):
        dead = R["dead"]
        t = R["dead_t"]
        foot = HZ + int(HCAM * F / CAMBACK) - int(hgt * (F / CAMBACK))
        if dead:
            if dead == "fell":
                name = "drop%d" % min(5, t // 3)
                foot += min(30, t * 2)
            else:
                name = "tumble%d" % min(5, t // 3)
            patch(runner_sp[name], sx, foot)
            if dead != "fell" and t > 24:
                n = min(2, (t - 24) // 5)
                ps = D["pounce"][n]
                patch(ps, CX, VH - 1)
            return
        if hgt > 0.05:
            sp = runner_sp["jump_up"] if R["vy"] > 0 else runner_sp["jump_down"]
            if R["boost"]:
                sp = runner_sp["jump_down"]
            patch(sp, sx, foot)
        elif R["slide"]:
            patch(runner_sp["slide"], sx, foot)
        elif R["stumble"]:
            patch(runner_sp["stumble_a" if (R["stumble"] // 4) & 1 else "stumble_b"], sx, foot)
        else:
            patch(runner_sp["run%d" % (int(R["pose"] * 1.0) & 7)], sx, foot)
        if R["shield"] or R["invuln"] and (state["tick"] & 2):
            patch(runner_sp["bubble"], sx, foot - 4)
        if R["boost"]:
            patch(runner_sp["aura"], sx, foot - 3)

    # ---- HUD: golden carved pieces patched into the rows like any sprite ---------------------------------------
    def draw_hud(patch, rows, skyb):
        hd = D["hud"]
        digits = hd["digits"]
        patch(hd["corner"], 0, 0)
        patch(hd["vines"], VW - 44, 0)
        fx = VW - 52
        patch(hd["frame"], fx, 2)

        def number(n, right, y):
            txt = str(max(0, int(n)))
            x = right - 6 * len(txt)
            for ch in txt:
                patch(digits[ord(ch) - 48], x, y)
                x += 6
        number(R["dist"], fx + 48, 5)
        patch(hd["coin"], fx + 8, 19)
        number(R["coins"], fx + 48, 19)
        patch(hd["idol"], VW - 22, VH - 36)
        number(state["score"], VW - 24, VH - 31)
        patch(hd["pause"], VW - 15, VH - 15)
        left, total, color = 0, 1, None
        if R["boost"]:
            left, total, color = R["boost"], 5 * TICK_RATE, rgb565(255, 220, 60)
        elif R["magnet"]:
            left, total, color = R["magnet"], 8 * TICK_RATE, rgb565(240, 70, 70)
        elif R["shield"]:
            left, total, color = 1, 1, rgb565(90, 180, 255)
        if color is not None:
            fillw = max(1, int(30 * left / total))
            for vr in range(66, 71):
                row = skyb.get(vr) or skyb.setdefault(vr, sky_row(vr, O["tp"]["pano"], int(cam["yaw"] * PANO / (2 * math.pi)) % PANO))
                row[26 * 12:58 * 12] = rgb565(40, 34, 20).to_bytes(2, "little") * 6 * 32
                row[27 * 12:(27 + fillw) * 12] = color.to_bytes(2, "little") * 6 * fillw

    # ---- main step -------------------------------------------------------------------------------------------------
    start_run()

    def step():
        state["tick"] += 1
        ph = state["phase"]
        if ph == "final":
            return end.tick()
        if ph == "card":
            state["t"] += 1
            if state["t"] > 110:
                over = state["score"] >= state["target"] or state["tick"] > CAP_TICKS - 360
                if over:
                    state["phase"] = "final"
                    clear(0)
                    end.start(state["score"])
                else:
                    state["phase"] = "run"
                    clear(0)
                    start_run()
            return False
        if R["dead"]:
            update_dying()
        else:
            update_run()
        if state["phase"] == "run":
            state["score"] = max(state["best"], int(R["dist"])) + 50 * (state["coins_all"] + R["coins"])
            render()
        return False
    step.R, step.state, step.cam = R, state, cam
    return step
