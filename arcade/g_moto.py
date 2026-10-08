# Motorbike racer seen from behind in the spirit of Hang-On / Super Hang-On: pseudo-3D road built from scanline
# colour runs (Lou Gorenfeld style curve accumulation), checkpoint gates that extend the clock, rival bikes and
# traffic, and a bot that reads the curvature ahead, leans, overtakes and rarely misjudges a sharp curve.
# One "virtual pixel" (vpx) is 5x5 screen pixels, so one screen row of the road is a few colour runs written to
# 5 scanlines at once.
import math
from bisect import bisect_left
from fbcore import *

D = load_bundle("g_moto.bin")

PX, VW, VH = 5, 384, 216
ROWB = VW * 10                 # bytes of one vpx row; equals one scanline (3840)
BLOCK = ROWB * PX              # bytes of one vrow on screen
HZ = 100                       # horizon vrow
NDY = 115                      # road rows below the horizon, the last vrow is 215
SKY_TOP, SKY_H, NEAR_H, PERIOD = 20, 81, 30, 768
HUD_H = SKY_TOP * PX
K = 1728.0                     # a row dy below the horizon sees the road at K / dy metres from the camera
ZCAM = [0.0] + [K / dy for dy in range(1, NDY + 1)]
SCALE = [dy / 6.8 for dy in range(NDY + 1)]    # vpx per metre
HALF = 10.0                    # half width of the road in metres, the unit of every lateral coordinate
CAMBACK = 16.0                 # the camera sits this far behind the bike
CELL = 20                      # curvature / feature cell length, metres
PLAYER_FOOT, PLAYER_X = 208, VW // 2
STAGES = 6

BUCKETS = [115, 93, 74, 59, 47, 38, 30, 24, 19, 15, 12, 10, 8, 6]
BIDX = [-1] * (NDY + 1)
for _dy in range(6, NDY + 1):
    BIDX[_dy] = next(i for i, b in enumerate(BUCKETS) if b <= _dy)

VTOP = 78.0                    # m/s, 281 km/h: the arcade's normal top speed
VTURBO = 90.0                  # 324 km/h with the turbo
MAXV = 0.03                    # steering authority per tick, road half-widths
KC = 1.4e-3                    # lateral push per tick from curvature * speed^2
BRAKE = 26.0                   # m/s^2 the bot is willing to shed speed at

GA, GB, RUM, ROAD, LANE, EDGE, CHK0, CHK1 = range(8)
NKEYS = 8


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def build_template(road):
    pieces = [(-1.9, GA), (-1.06, GB), (-0.92, RUM), (-0.88, EDGE)] + road + [(0.92, EDGE), (1.06, RUM), (1.9, GB)]
    keys = [k for _, k in pieces] + [GA]
    return [(b, k * 4) for (b, _), k in zip(pieces, keys)], GA * 4


def make_templates():
    plain = [(-0.36, ROAD), (-0.32, LANE), (0.32, ROAD), (0.36, LANE), (0.88, ROAD)]
    chk = [(-0.88 + (i + 1) * 1.76 / 12, CHK0 if i % 2 == 0 else CHK1) for i in range(12)]
    return {0: build_template(plain), 1: build_template(chk)}


TEMPL = make_templates()


def key_color(th, key, p1, p2):
    if key == GA:
        return th["ground"][p1]
    if key == GB:
        return th["ground"][1 - p1]
    if key == RUM:
        return th["rum"][p2]
    if key == ROAD:
        return th["road"][p1]
    if key == LANE:
        return th["lane"] if p1 == 0 else th["road"][p1]
    if key == EDGE:
        return th["edge"]
    on = (245, 245, 250) if p2 else (20, 20, 28)
    off = (20, 20, 28) if p2 else (245, 245, 250)
    return on if key == CHK0 else off


def make_palette(th):
    # Haze fades the road towards the horizon colour; it also hides distant stripe aliasing.
    pal = [None]
    haze = th["haze"]
    for dy in range(1, NDY + 1):
        f = max(0.0, 1.0 - dy / 40.0) ** 1.5
        row = []
        for key in range(NKEYS):
            for p in range(4):
                c = key_color(th, key, p >> 1, p & 1)
                c = tuple(int(c[i] + (haze[i] - c[i]) * f) for i in range(3))
                row.append(rgb565(*c).to_bytes(2, "little") * 5)
        pal.append(row)
    return pal


# ---- tracks ---------------------------------------------------------------------------------------------
class Track:
    __slots__ = ("n", "cur", "feat", "objs", "sharp", "goal")


def make_track(th, stage):
    t = Track()
    n = random.randint(122, 134)
    t.n = n
    t.goal = (n + 1) * CELL
    cur = [0.0] * (n + 70)
    i = 6
    sign = random.choice((-1, 1))
    sharp_w = min(0.34, 0.14 + 0.04 * stage)
    medium_w = 0.4
    t.sharp = []
    while i < n - 14:
        if random.random() < 0.32:
            i += random.randint(3, 9)
            continue
        length = random.randint(6, 13)
        r = random.random()
        if r < sharp_w:
            c, is_sharp = random.uniform(0.0042, 0.0055), True
        elif r < sharp_w + medium_w:
            c, is_sharp = random.uniform(0.002, 0.0035), False
        else:
            c, is_sharp = random.uniform(0.0008, 0.0016), False
        c *= sign * th["curve"] ** 0.5
        c = clamp(c, -0.0056, 0.0056)
        for k in range(length):
            j = i + k
            if j >= n - 14:
                break
            e = min(k, length - 1 - k)
            cur[j] = c * (0.45, 0.8)[e] if e < 2 else c
        if is_sharp and length >= 7:
            t.sharp.append(i)
        i += length
        sign = -sign if random.random() < 0.75 else sign
    if not t.sharp:
        i = n // 2
        for k in range(9):
            cur[i + k] = 0.0048 * (1 if k not in (0, 8) else 0.6) * (-1 if cur[i - 1] > 0 else 1)
        t.sharp.append(i)
    t.cur = cur
    t.feat = [0] * (n + 70)
    for j in (0, n, n + 1):
        t.feat[j] = 1
    # roadside objects: (distance, lateral, kind index); towers sit further out than lamps
    kinds = D["scenery"][stage % 4]
    objs = {}
    for cell in range(3, n + 6):
        if random.random() < 0.62:
            for _ in range(1 + (random.random() < 0.25)):
                ki = random.randrange(len(kinds))
                tall = kinds[ki]["w"] >= 9
                lat = random.choice((-1, 1)) * (random.uniform(2.6, 4.6) if tall else random.uniform(1.45, 2.9))
                objs.setdefault(cell, []).append((cell * CELL + random.uniform(0, CELL - 1), lat, ki))
    t.objs = objs
    return t


class Vehicle:
    __slots__ = ("dist", "lat", "lane", "v", "vmax", "lv", "kind", "color", "bump_t", "ahead", "tight", "ci")

    def __init__(self):
        self.dist = self.lat = self.lane = self.v = self.lv = 0.0
        self.vmax = 60.0
        self.kind = 0          # 0 bike, 1 car
        self.color = 0
        self.ci = 0
        self.bump_t = 0
        self.ahead = True
        self.tight = False


def make():
    th = None
    pal = None
    trk = None
    player = Vehicle()
    vehicles = []
    S = {}
    cx_row = [VW / 2.0] * (NDY + 1)
    hud_cache = {}
    banner = {"lines": [], "t": 0}
    puffs = []
    end = EndScreen()
    state = {"phase": "intro", "t": 0, "stage": 0, "score": 0, "tick": 0, "top": random.randint(180, 420) * 1000}
    sky = {"offs": None, "touched": set(), "near_starts": None}

    def curv(dist):
        idx = int(dist) // CELL
        return trk.cur[0 if idx < 0 else idx if idx < len(trk.cur) else len(trk.cur) - 1]

    # ---- stage setup -----------------------------------------------------------------------------------
    def start_stage():
        nonlocal th, pal, trk
        st = state["stage"]
        state["phase"] = "intro"
        th = D["themes"][st % 4]
        pal = make_palette(th)
        trk = make_track(th, st)
        player.dist, player.lat, player.v, player.lv = 4.0, 0.0, 0.0, 0.0
        S.update(tilt=0.0, sky_x=0.0, boost_t=0, boost_cool=60, wheelie_t=0, wobble_t=0, crash_t=0, blink_t=0, scrape=0,
                 sparks=0, gear=0, shift_t=0, offroad_t=0, mistake=None, passed=0, flame_t=0)
        if st >= 1 and random.random() < 0.2 and trk.sharp:
            # the bot misjudges one sharp curve; the trap spans the whole curve so it cannot brake halfway through
            start = random.choice(trk.sharp[len(trk.sharp) // 3:] or trk.sharp)
            end = start
            while abs(trk.cur[end]) > 1e-5:
                end += 1
            S["mistake"] = (start, end)
        if st == 0:
            S["time"] = 80 * 30
        vehicles.clear()
        for k in range(7 + st // 2):
            v = Vehicle()
            place_vehicle(v, 30 + k * 42 + random.uniform(0, 20))
            vehicles.append(v)
        for v in vehicles:
            v.ahead = True
        draw_static()
        hud_cache.clear()
        banner.update(lines=[("STAGE %d" % (st + 1), "L", COLOR_YELLOW, 560), (th["name"], "L", COLOR_CYAN, 650)], t=90)
        state["phase"], state["t"] = "intro", 0

    def place_vehicle(v, dz):
        st = state["stage"]
        v.dist = player.dist + dz
        v.kind = 1 if random.random() < th["traffic"] * 0.55 else 0
        for _ in range(8):
            v.lat = random.choice((-0.62, -0.3, 0.3, 0.62)) + random.uniform(-0.1, 0.1)
            if all(not (abs(o.dist - v.dist) < 70 and abs(o.lat - v.lat) < 0.45) for o in vehicles if o is not v):
                break
        v.lane = v.lat
        v.lv = 0.0
        v.ahead = True
        v.bump_t = 0
        v.tight = random.random() < 0.12
        if v.kind == 1:
            v.vmax = random.uniform(30.0, 42.0)
            v.ci = random.randrange(2)
            v.color = random.randrange(4)
        else:
            v.vmax = random.uniform(0.68, 0.86) * VTOP * (1.0 + 0.012 * st)
            v.color = random.randrange(1, 6)
        v.v = v.vmax if state["phase"] != "intro" else 0.0

    def draw_static():
        clear()
        sky["offs"] = None
        sky["touched"] = set()
        sky["near_starts"] = [[x0 for x0, _ in row] for row in D["near"][state["stage"] % 4]]
        sky["fresh"] = True

    # ---- other vehicles -----------------------------------------------------------------------------------
    def update_vehicles():
        ordered = sorted(vehicles + [player], key=lambda c: -c.dist)
        for k, c in enumerate(ordered):
            if c is player:
                continue
            ca = max(abs(curv(c.dist + 25)), abs(curv(c.dist + 70)))
            tv = c.vmax
            if ca > 1e-5:
                tv = min(tv, math.sqrt(0.5 * MAXV / (ca * KC)))
            # follow-the-leader: never drive through a slower vehicle in the same lane, try the neighbouring lane first
            c.lane = clamp(c.lane, -0.75, 0.75)
            for a in ordered[max(0, k - 3):k]:
                gap = a.dist - c.dist
                if 0 < gap < 30 and abs(a.lat - c.lane) < 0.4 and a.v < c.v + 3 and a is not player:
                    side = 1.0 if a.lat < 0 else -1.0
                    alt = clamp(a.lat + 0.6 * side, -0.75, 0.75)
                    if all(abs(o.lat - alt) > 0.4 or abs(o.dist - c.dist) > 25 for o in ordered if o is not c):
                        c.lane = alt
                    else:
                        tv = min(tv, a.v)
                    break
            if state["phase"] == "intro":
                tv = 0.0
            c.v = max(0.0, c.v + clamp(tv - c.v, -1.5, 0.8))
            c.lv += (clamp((c.lane - c.lat) * 0.08, -0.02, 0.02) - c.lv) * 0.3
            c.lat = clamp(c.lat + c.lv, -0.8, 0.8)
            c.dist += c.v / 30.0
            if c.bump_t:
                c.bump_t -= 1
            if c.dist < player.dist - 70 and state["phase"] != "checkpoint":
                place_vehicle(c, random.uniform(230, 330))

    # ---- the bot -------------------------------------------------------------------------------------------
    def plan_speed(p):
        vcap = VTOP
        mistake = S["mistake"] is not None and S["time"] > 30 * 25
        trap = S["mistake"] if mistake else None
        for s in range(0, 261, 20):
            c = abs(curv(p.dist + s))
            if c < 1e-5:
                continue
            vt = math.sqrt(0.68 * MAXV / (c * KC))
            if trap and trap[0] - 3 <= int(p.dist + s) // CELL < trap[1]:
                vt *= 1.9
            vcap = min(vcap, math.sqrt(vt * vt + 2.0 * BRAKE * 0.8 * s))
        return vcap

    def plan_lateral(p):
        ca = (curv(p.dist + 40) + curv(p.dist + 80) + curv(p.dist + 120)) / 3.0
        far = (curv(p.dist + 170) + curv(p.dist + 220) + curv(p.dist + 270)) / 3.0
        # inside of the coming curve; before it, swing to the outside so the entry is wider
        target = 150.0 * ca - (70.0 * far if abs(ca) < 0.0012 else 0.0)
        target = clamp(target, -0.65, 0.65)
        blocked_speed = None
        reach = clamp(p.v * 1.7, 50.0, 140.0)
        for c in vehicles:
            dz = c.dist - p.dist
            margin = 0.17 if (c.tight and c.kind == 0) else 0.42
            closing = max(0.1, (p.v - c.v) / 30.0)
            if 0 < dz < reach and (abs(c.lat - target) < margin + 0.1 or (dz < 70 and abs(c.lat - p.lat) < margin)):
                opts = [x for x in (c.lat + margin + 0.18, c.lat - margin - 0.18) if abs(x) <= 0.8]
                opts = [x for x in opts if all(abs(o.lat - x) > margin or not 0 < o.dist - p.dist < reach + 30 or o is c
                                               for o in vehicles)]
                if opts:
                    target = min(opts, key=lambda x: abs(x - target))
                    # a gap that cannot be reached before the gap closes is no gap: slow down behind the blocker
                    if abs(target - p.lat) / 0.022 > 0.9 * dz / closing and dz < 80:
                        blocked_speed = c.v - 0.5
                elif dz < 40 + max(0.0, p.v - c.v) * 1.5:
                    blocked_speed = c.v - 0.5
            elif abs(dz) < 7 and abs(c.lat - p.lat) < 0.3:
                target = p.lat + (0.35 if p.lat >= c.lat else -0.35)
        return clamp(target, -0.8, 0.8), blocked_speed

    def crash():
        S["crash_t"] = 1
        S["boost_t"] = 0
        S["wheelie_t"] = 0
        S["crash_side"] = 1.0 if player.lat >= 0 else -1.0
        S["crash_v"] = player.v

    def update_player():
        p = player
        ph = state["phase"]
        if ph == "intro":
            return
        c_here = curv(p.dist)
        if S["crash_t"]:
            S["crash_t"] += 1
            t = S["crash_t"]
            p.v *= 0.93
            p.lat = clamp(p.lat + S["crash_side"] * 0.006 * max(0.0, 1 - t / 40.0), -2.4, 2.4)
            if t > 70:
                p.lat *= 0.9
            if t >= 100:
                S["crash_t"] = 0
                S["blink_t"] = 60
                p.lat = 0.0
                p.v = 14.0
                S["tilt"] = 0.0
            p.dist += p.v / 30.0
            S["sky_x"] += curv(p.dist + 40) * p.v * 13.0
            return
        target, blocked = plan_lateral(p)
        vcap = plan_speed(p)
        trapped = S["mistake"] is not None and S["mistake"][0] <= int(p.dist) // CELL < S["mistake"][1] and S["time"] > 30 * 25
        if trapped and blocked is None:
            target = -target
        if ph == "checkpoint":
            target, vcap, blocked = 0.0, 22.0, None
        if p.lat > 1.0 or p.lat < -1.0:
            target = 0.6 if p.lat < 0 else -0.6
            S["offroad_t"] += 1
        else:
            S["offroad_t"] = 0
        if blocked is not None:
            vcap = min(vcap, blocked)
        boosting = S["boost_t"] > 0
        ahead_clear = all(not (0 < c.dist - p.dist < 140 and abs(c.lat - p.lat) < 0.6) for c in vehicles)
        calm = all(abs(curv(p.dist + s)) < 0.0006 for s in (0, 60, 120, 200, 280))
        if S["boost_cool"]:
            S["boost_cool"] -= 1
        if (not boosting and S["boost_cool"] == 0 and calm and ahead_clear and p.v > 0.95 * VTOP and ph == "race"
                and S["blink_t"] == 0 and abs(p.lat) < 0.9):
            S["boost_t"] = 75
            S["boost_cool"] = 210
            S["flame_t"] = 75
            S["wheelie_t"] = 20
            boosting = True
        if S["boost_t"]:
            S["boost_t"] -= 1
            if not calm or not ahead_clear:
                S["boost_t"] = 0
        top = VTURBO if boosting else VTOP
        vtarget = min(vcap if not boosting else max(vcap, VTOP), top)
        if p.lat > 1.0 or p.lat < -1.0:
            vtarget = min(vtarget, 24.0)
            p.v -= 0.9
        if p.v < vtarget:
            lowg = p.v < 46.0
            acc = 0.85 if lowg else 0.6 * (1.0 - 0.6 * p.v / top)
            p.v = min(vtarget, p.v + acc * (1.5 if boosting else 1.0))
        else:
            p.v = max(vtarget, p.v - BRAKE / 30.0)
        gear = 1 if p.v > (44.0 if S["gear"] == 0 else 40.0) else 0
        if gear != S["gear"]:
            S["gear"] = gear
            S["shift_t"] = 8
        if S["shift_t"]:
            S["shift_t"] -= 1
        drift = c_here * p.v * p.v * KC
        authority = MAXV * 0.7 if trapped else MAXV
        steer = clamp((target - p.lat) * 0.10 + drift, -authority, authority)
        if S["wobble_t"]:
            S["wobble_t"] -= 1
            steer *= 0.6
        p.lv += (steer - p.lv) * 0.35
        p.lat += p.lv - drift
        S["scrape"] = 0
        a = abs(p.lat)
        if 0.97 < a <= 1.06 and p.v > 40:
            S["scrape"] = 1
            p.v -= 0.15
        if S["wheelie_t"]:
            S["wheelie_t"] -= 1
        p.lat = clamp(p.lat, -2.4, 2.4)
        if S["blink_t"]:
            S["blink_t"] -= 1
        ft = 0.3 if a < 1.0 else 0.15
        S["tilt"] += (clamp(drift / MAXV * 3.0 + p.lv / MAXV * 1.3, -3.0, 3.0) - S["tilt"]) * ft
        p.dist += p.v / 30.0
        kmh = p.v * 3.6
        state["score"] += int(kmh / 6.0)
        S["sky_x"] += curv(p.dist + 40) * p.v * 13.0
        # leaving the road at speed ends in a crash once the bike is deep in the verge or hits an object
        if S["blink_t"] == 0 and ph == "race":
            if (a > 1.5 and p.v > 22.0) or (S["offroad_t"] >= 5 and p.v > 55.0):
                crash()
            elif a > 1.2:
                cell = int(p.dist) // CELL
                for ce in (cell, cell + 1):
                    for od, ol, _ in trk.objs.get(ce, ()):
                        if abs(od - p.dist) < 4.0 and abs(ol - p.lat) < 0.28 and p.v > 20:
                            crash()

    def interactions():
        p = player
        for c in vehicles:
            dz = c.dist - p.dist
            dl = c.lat - p.lat
            if (abs(dz) < 4.5 and abs(dl) < 0.19 and c.bump_t == 0 and S["crash_t"] == 0 and S["blink_t"] == 0
                    and state["phase"] == "race"):
                c.bump_t = 60
                away = 1.0 if dl > 0 else -1.0
                if abs(dl) < 0.02:
                    away = random.choice((-1.0, 1.0))
                if c.kind == 1 and p.v - c.v > 14:
                    crash()
                    continue
                p.lv -= 0.04 * away
                c.lv += 0.03 * away
                c.lane = clamp(c.lat + 0.4 * away, -0.75, 0.75)
                S["wobble_t"] = 22
                S["sparks"] = 8
                if dz > 0:
                    p.v = min(p.v, c.v + 4.0)
                else:
                    p.v += 1.0
            ahead = dz > 0
            if c.ahead and not ahead and state["phase"] == "race":
                S["passed"] += 1
                state["score"] += 400 if c.kind else 2000
            c.ahead = ahead
        if state["score"] > state["top"]:
            state["top"] = state["score"]

    # ---- smoke and sparks ----------------------------------------------------------------------------------
    def update_puffs():
        p = player
        st = state["tick"]
        sx = PLAYER_X + int(S["tilt"] * 2)
        if S["crash_t"] == 0:
            if S["boost_t"] > 60 or (S["wheelie_t"] and p.v < 50) or abs(S["tilt"]) > 2.4 and st % 2 == 0:
                puffs.append([sx + random.randint(-4, 4), PLAYER_FOOT - 2, 0, 0])
            if abs(p.lat) > 1.0 and p.v > 25:
                puffs.append([sx + random.randint(-8, 8), PLAYER_FOOT - 3, 0, 1])
        elif S["crash_t"] < 55:
            puffs.append([PLAYER_X + int(S["crash_side"] * S["crash_t"] * 1.5) + random.randint(-6, 6), PLAYER_FOOT - 2, 0, 1])
        for q in puffs:
            q[2] += 1
            q[1] += 1
        puffs[:] = [q for q in puffs if q[2] < 16]

    # ---- drawing ---------------------------------------------------------------------------------------
    def put(over, vr, x, data, m):
        # clip a run of m vpx at x into the row
        if vr < SKY_TOP or vr >= VH:
            return
        if x < 0:
            data = data[-x * 10:]
            m += x
            x = 0
        if x + m > VW:
            m = VW - x
            data = data[:m * 10]
        if m > 0:
            lst = over.get(vr)
            if lst is None:
                lst = over[vr] = []
            lst.append((x, data))

    def sprite_overlay(over, sp, cx, foot):
        w, h, rows, ax, ay = sp
        x0 = int(cx) - ax
        top = foot - ay + 1
        if x0 + w < 0 or x0 >= VW:
            return
        for j, spans in enumerate(rows):
            vr = top + j
            if vr < SKY_TOP or vr >= VH:
                continue
            for sx, data in spans:
                put(over, vr, x0 + sx, data, len(data) // 10)

    def free_sprite(over, sp, cx, cy):
        # sprite positioned by its own anchor at an arbitrary point (crash parts)
        w, h, rows, ax, ay = sp
        x0 = int(cx) - ax
        top = int(cy) - ay
        for j, spans in enumerate(rows):
            for sx, data in spans:
                put(over, top + j, x0 + sx, data, len(data) // 10)

    puff_cols = {}

    def puff_color(kind):
        c = puff_cols.get(kind)
        if c is None:
            if kind == 0:
                base = [(238, 238, 244), (200, 204, 214), (170, 176, 190)]
            else:
                g = th["ground"][0]
                base = [tuple(min(255, int(v * f)) for v in g) for f in (1.15, 1.0, 0.85)]
            c = [rgb565(*b).to_bytes(2, "little") * 5 for b in base]
            puff_cols[kind] = c
        return c

    def render():
        pos = player.dist
        lat10 = player.lat * HALF
        xo = dxo = zp = 0.0
        rows = [None] * (NDY + 1)
        cur = trk.cur
        feat = trk.feat
        ncur = len(cur) - 1
        for dy in range(NDY, 0, -1):
            z = ZCAM[dy]
            dz = z - zp
            zp = z
            w = int(pos + z - CAMBACK)
            cell = w // CELL
            cell = 0 if cell < 0 else ncur if cell > ncur else cell
            dxo += cur[cell] * dz
            xo += dxo * dz
            sc = SCALE[dy]
            cx = VW / 2 + (xo - lat10) * sc
            cx_row[dy] = cx
            hw = HALF * sc
            tpl, last = TEMPL[feat[cell]]
            p = ((w >> 4) & 1) << 1 | ((w >> 3) & 1)
            pr = pal[dy]
            prev = 0
            out = []
            for b, ko in tpl:
                x = int(cx + b * hw)
                if x > prev:
                    if x >= VW:
                        out.append(pr[ko + p] * (VW - prev))
                        prev = VW
                        break
                    out.append(pr[ko + p] * (x - prev))
                    prev = x
            if prev < VW:
                out.append(pr[last + p] * (VW - prev))
            rows[dy] = b"".join(out)

        # things, far to near
        things = []
        kinds = D["scenery"][state["stage"] % 4]
        c0 = max(0, int(pos - CAMBACK) // CELL)
        for ce in range(c0, c0 + 16):
            for od, ol, ki in trk.objs.get(ce, ()):
                zr = od - pos
                if -CAMBACK + 1 < zr < 290.0:
                    things.append((zr, 0, ol, ki, 0))
        for c in vehicles:
            zr = c.dist - pos
            if -CAMBACK + 1 < zr < 290.0:
                things.append((zr, 1, c.lat, c.kind, c))
        gz = trk.goal - pos
        if -CAMBACK + 1 < gz < 290.0:
            things.append((gz, 2, 0.0, 0, 0))
        things.sort(key=lambda t: -t[0])
        over = {}
        for zr, typ, lat, ki, c in things:
            dy = int(K / (zr + CAMBACK))
            if dy > NDY:
                continue
            bi = BIDX[dy]
            if bi < 0:
                continue
            x = cx_row[dy] + lat * HALF * SCALE[dy]
            if typ == 0:
                sprite_overlay(over, kinds[ki]["set"][bi], x, HZ + dy)
            elif typ == 1:
                if c.kind == 0:
                    ca = curv(c.dist)
                    lean = 2 if ca > 0.0015 else 0 if ca < -0.0015 else 1
                    sprite_overlay(over, D["rivals"][c.color][lean][bi], x, HZ + dy)
                else:
                    sprite_overlay(over, D["cars"][c.ci]["colors"][c.color][bi], x, HZ + dy)
            else:
                sprite_overlay(over, D["gates"][1 if state["stage"] == STAGES - 1 else 0][bi], cx_row[dy], HZ + dy)

        # the player: smoke under the bike, then the bike or the crash parts
        for q in puffs:
            age = q[2]
            size = 2 + age // 2
            col = puff_color(q[3])[0 if age < 5 else 1 if age < 10 else 2]
            side = (q[0] * 7 + age) % 3 - 1
            x0 = q[0] - size // 2 + side * (age // 3)
            for r in range(size):
                narrow = 1 if r in (0, size - 1) and size > 3 else 0
                put(over, q[1] + r - size // 2 + age // 2, x0 + narrow, col * (size - 2 * narrow), size - 2 * narrow)
        tilt = int(round(S["tilt"]))
        if S["wobble_t"]:
            tilt = int(round(S["tilt"] + 1.6 * math.sin(S["wobble_t"] * 1.1) * min(1.0, S["wobble_t"] / 12.0)))
        tilt = int(clamp(tilt, -3, 3))
        sway = int(S["tilt"] * 2)
        yel = (rgb565(255, 240, 120).to_bytes(2, "little") * 10, rgb565(255, 160, 40).to_bytes(2, "little") * 10,
               rgb565(255, 255, 255).to_bytes(2, "little") * 10)
        ct = S["crash_t"]
        if ct:
            side = S["crash_side"]
            if ct <= 34:
                rx = PLAYER_X + side * ct * 1.6
                ry = PLAYER_FOOT - 22 - 30 * math.sin(math.pi * ct / 34.0)
                ri = (ct // 2) % 12
            else:
                slide = min(30, ct - 34)
                rx = PLAYER_X + side * (54 + slide * 0.7)
                ry = PLAYER_FOOT - 8
                ri = 3 if side > 0 else 9
            bi_ = (ct // 3) % 12 if ct < 36 else (4 if side > 0 else 8)
            bx = PLAYER_X + side * min(ct, 50) * 0.5
            by = PLAYER_FOOT - 14 + min(ct, 36) * 0.15
            if ct < 90 or (ct // 3) % 2:
                free_sprite(over, D["crash_bike"][bi_], bx, by)
                free_sprite(over, D["crash_rider"][ri], rx, ry)
            if 4 < ct < 60:
                for _ in range(5):
                    vr = int(by) + random.randint(-2, 12)
                    put(over, vr, int(bx) + random.randint(-16, 16), random.choice(yel), 2)
        elif S["blink_t"] == 0 or (S["blink_t"] // 3) % 2:
            flame = 0
            if S["flame_t"]:
                S["flame_t"] -= 1
                flame = 1 + (state["tick"] & 1)
            elif S["shift_t"]:
                flame = 1
            if S["wheelie_t"] and abs(tilt) <= 1:
                sp = D["wheelie"][tilt + 1]
            else:
                sp = D["player"][tilt + 3][flame]
            sprite_overlay(over, sp, PLAYER_X + sway, PLAYER_FOOT)
            if S["scrape"] or S["sparks"]:
                S["sparks"] = max(0, S["sparks"] - 1)
                side = -1 if player.lat < 0 else 1
                if not S["scrape"]:
                    side = random.choice((-1, 1))
                for _ in range(7):
                    vr = PLAYER_FOOT - random.randint(0, 6)
                    xx = PLAYER_X + sway + side * random.randint(12, 24) + random.randint(-3, 3)
                    put(over, vr, xx, random.choice(yel), 2)

        # road rows, sprites patched in
        for dy in range(1, NDY + 1):
            vr = HZ + dy
            row = rows[dy]
            sp = over.get(vr)
            if sp:
                row = bytearray(row)
                for x, data in sp:
                    row[x * 10:x * 10 + len(data)] = data
            fb[vr * BLOCK:(vr + 1) * BLOCK] = row * PX
        paint_sky(over)

    def paint_sky(over):
        far_off = int(S["sky_x"] * 0.45) % PERIOD
        near_off = int(S["sky_x"]) % PERIOD
        dirty = sky["offs"] != (far_off, near_off)
        sky["offs"] = (far_off, near_off)
        fresh = sky.pop("fresh", False)
        idx = state["stage"] % 4
        far = D["far"][idx]
        uni = D["far_uni"][idx]
        near = D["near"][idx]
        starts = sky["near_starts"]
        prev = sky["touched"]
        touched = set()
        f10, n_end = far_off * 10, near_off + VW
        for r in range(SKY_H):
            vr = SKY_TOP + r
            sp = over.get(vr)
            if sp:
                touched.add(vr)
            static = uni[r] is not None and r < SKY_H - NEAR_H
            if static:
                if not (sp or vr in prev or fresh):
                    continue
                row = bytearray(uni[r] * VW)
            else:
                if not (dirty or sp or vr in prev):
                    continue
                row = bytearray(far[r][f10:f10 + ROWB])
                nr = r - (SKY_H - NEAR_H)
                if nr >= 0:
                    spans = near[nr]
                    i = bisect_left(starts[nr], near_off) - 1
                    for x0, data in spans[max(i, 0):]:
                        if x0 >= n_end:
                            break
                        a = x0 - near_off
                        m = len(data) // 10
                        if a < 0:
                            data = data[-a * 10:]
                            m += a
                            a = 0
                        if a + m > VW:
                            m = VW - a
                            data = data[:m * 10]
                        if m > 0:
                            row[a * 10:a * 10 + m * 10] = data
            if sp:
                for x, data in sp:
                    row[x * 10:x * 10 + len(data)] = data
            fb[vr * BLOCK:(vr + 1) * BLOCK] = row * PX
        sky["touched"] = touched

    # ---- HUD -------------------------------------------------------------------------------------------------
    def hud_init():
        fill_rect(0, 0, W, HUD_H, 0)
        fill_rect(0, HUD_H - 4, W, 4, rgb565(*th["rum"][0]))
        # the minimap: integrate the heading over the whole course once
        pts, x, y, h = [], 0.0, 0.0, 0.0
        for i in range(trk.n + 2):
            h += trk.cur[i] * CELL * 1.3
            x += math.cos(h)
            y += math.sin(h)
            pts.append((x, y))
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        sc = min(380.0 / max(1.0, x1 - x0), 80.0 / max(1.0, y1 - y0))
        ox = 1500 + (400 - (x1 - x0) * sc) / 2
        oy = 8 + (84 - (y1 - y0) * sc) / 2
        mini = [(int(ox + (px_ - x0) * sc), int(oy + (py_ - y0) * sc)) for px_, py_ in pts]
        S["mini"] = mini
        S["mini_cell"] = -1
        for i in range(len(mini)):
            mini_dot(i, 0)
        fx, fy = mini[-1]
        fill_rect(fx - 3, fy - 3, 9, 9, rgb565(250, 220, 40))

    def mini_dot(i, cell):
        mx, my = S["mini"][i]
        fill_rect(mx, my, 3, 3, rgb565(60, 90, 124) if i < cell else rgb565(120, 200, 255))

    def hud():
        if not hud_cache.get("init"):
            hud_init()
            hud_cache["init"] = True
        p = player
        secs = (S["time"] + 29) // 30
        boost = S["boost_t"] > 0
        vals = {"score": "SCORE %7d" % state["score"], "top": "TOP %9d" % state["top"],
                "stage": "STAGE %d" % (state["stage"] + 1), "name": "%-10s" % th["name"],
                "spd": "%3d KM/H" % int(p.v * 3.6), "gear": "%-5s" % ("TURBO" if boost else "HIGH" if S["gear"] else "LOW"),
                "time": "TIME %2d" % secs}
        pos = {"score": (24, 6, "S"), "top": (24, 52, "S"), "stage": (420, 6, "S"), "name": (660, 6, "S"),
               "spd": (420, 52, "S"), "gear": (660, 52, "S"), "time": (980, 10, "L")}
        for k, text in vals.items():
            if hud_cache.get(k) != text:
                hud_cache[k] = text
                x, y, sz = pos[k]
                color = COLOR_YELLOW
                if k == "time":
                    color = COLOR_RED if secs <= 10 else COLOR_YELLOW
                elif k == "gear":
                    color = COLOR_RED if boost else COLOR_CYAN
                elif k in ("score", "top", "spd"):
                    color = COLOR_WHITE
                elif k == "name":
                    color = COLOR_CYAN
                draw_text(text, x, y, sz, color)
        cell = min(trk.n + 1, max(0, int(p.dist) // CELL))
        if cell != S["mini_cell"]:
            mini = S["mini"]
            if S["mini_cell"] >= 0:
                px_, py_ = mini[S["mini_cell"]]
                fill_rect(px_ - 2, py_ - 2, 7, 7, 0)
                for i, (mx, my) in enumerate(mini):
                    if abs(mx - px_) < 6 and abs(my - py_) < 6 and i != cell:
                        mini_dot(i, cell)
            S["mini_cell"] = cell
            px_, py_ = mini[cell]
            fill_rect(px_ - 2, py_ - 2, 7, 7, rgb565(255, 50, 50))

    def draw_banner():
        if banner["t"] <= 0:
            return
        banner["t"] -= 1
        for text, size, color, y in banner["lines"]:
            draw_text(text, (W - text_width(text, size)) // 2, y, size, color, bg=False)

    def checkpoint_reached():
        st = state["stage"]
        secs = (S["time"] + 29) // 30
        bonus = secs * 1000
        state["score"] += bonus + 5000
        final = st == STAGES - 1
        if not final:
            S["time"] += 50 * 30
        lines = [("GOAL!" if final else "CHECKPOINT", "L", COLOR_YELLOW, 540),
                 ("TIME BONUS %d" % bonus, "S", COLOR_CYAN, 640)]
        if not final:
            lines.append(("EXTEND TIME +50", "S", COLOR_GREEN, 700))
        banner.update(lines=lines, t=170)
        state["phase"], state["t"] = "checkpoint", 0

    start_stage()

    def step():
        state["tick"] += 1
        if state["phase"] == "over":
            return end.tick()
        state["t"] += 1
        ph = state["phase"]
        if ph == "intro":
            t = state["t"]
            if t == 70:
                banner.update(lines=[("READY", "L", COLOR_RED, 560)], t=30)
            elif t == 100:
                banner.update(lines=[("GO!", "L", COLOR_GREEN, 560)], t=40)
                state["phase"], state["t"] = "race", 0
                S["wheelie_t"] = 30
        elif ph == "race":
            S["time"] -= 1
            if state["tick"] > CAP_TICKS - 450:
                S["time"] = max(S["time"], 60)
                trk.goal = min(trk.goal, int(player.dist) + 1200)
            if player.dist >= trk.goal:
                checkpoint_reached()
            elif S["time"] <= 0:
                end.start(int(state["score"]), "TIME UP")
                state["phase"] = "over"
                return False
        elif ph == "checkpoint":
            if state["t"] > 170:
                state["stage"] += 1
                if state["stage"] >= STAGES or state["tick"] > CAP_TICKS - 400:
                    end.start(int(state["score"]), "COURSE CLEAR")
                    state["phase"] = "over"
                    return False
                start_stage()
        update_vehicles()
        update_player()
        if state["phase"] != "intro":
            interactions()
        update_puffs()
        render()
        draw_banner()
        hud()
        return False
    return step
