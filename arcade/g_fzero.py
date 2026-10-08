# Hover racing seen from behind: pseudo-3D road (Lou Gorenfeld style curve accumulation), a bot that drives a
# racing line, overtakes rivals, grabs dash plates and uses the pit lane. One "virtual pixel" (vpx) is 6x6
# screen pixels, so a whole screen row is a few colour runs repeated and written to 6 scanlines at once.
import math
from fbcore import *

D = load_bundle("g_fzero.bin")

VW, PX = 320, 6
ROWB = VW * 12                  # bytes of one vpx row (12 bytes per vpx)
BLOCK = ROWB * PX               # bytes of one vrow on screen (6 scanlines)
HZ = 70                         # horizon vrow
NDY = 109                       # road rows below the horizon (last vrow is 179)
SKYLINE_FROM, SKYLINE_H = 34, 36
PERIOD = 640
HUD_H = 14 * PX                 # top bar in screen pixels, never touched by the road renderer

# Projection: a row at dy below the horizon sees the road at distance ZCAM[dy] metres from the camera.
ZCAM = [0.0] + [1760.0 / dy for dy in range(1, NDY + 1)]
SCALE = [dy / 8.8 for dy in range(NDY + 1)]            # vpx per metre
HALF = 10.0                                             # road half width, metres
CAMBACK = 17.0                                          # camera sits this far behind the player car
CELL = 20                                               # track cell length, metres
LAPS = 3
RACES = 4
GRID = 20

# colour keys; every key has 4 variants selected by the two distance parities
GA, GB, BAR, RUM, ROAD, LANE, PIT, PLATE, JUMP, CHK0, CHK1 = range(11)
NKEYS = 11
F_NONE, F_PIT, F_START, F_DASH_L, F_DASH_C, F_DASH_R, F_JUMP = range(7)
DASH_LAT = {F_DASH_L: -0.55, F_DASH_C: 0.0, F_DASH_R: 0.55}
SPAN_L, SPAN_C, SPAN_R = (-0.92, -0.36), (-0.32, 0.32), (0.36, 0.92)


def build_template(road):
    # road: [(from, to, key)] contiguous lateral intervals between the rumble strips. Result: (bound, key) pairs where
    # the piece ENDING at bound has that key (x*4 is the palette offset), plus the key of the last piece.
    starts = ([(-5.64, GB), (-4.14, GA), (-2.64, GB), (-1.14, BAR), (-1.04, RUM)] + [(a, k) for a, b, k in road]
              + [(0.92, RUM), (1.04, BAR), (1.14, GB), (2.64, GA), (4.14, GB), (5.64, GA)])
    keys = [GA] + [k for _, k in starts]
    return [(b, k * 4) for (b, _), k in zip(starts, keys)], keys[-1] * 4


def make_templates():
    def spans(l, c, r):
        return [(-0.92, -0.36, l), (-0.36, -0.32, LANE), (-0.32, 0.32, c), (0.32, 0.36, LANE), (0.36, 0.92, r)]

    def split(center, key, half=0.17):
        # a plate on top of a road span: road, plate, road
        spans_ = {-0.55: (-0.92, -0.36), 0.0: (-0.32, 0.32), 0.55: (0.36, 0.92)}[center]
        return [(spans_[0], center - half, ROAD), (center - half, center + half, key), (center + half, spans_[1], ROAD)]

    t = {F_NONE: spans(ROAD, ROAD, ROAD)}
    t[F_PIT] = spans(PIT, ROAD, ROAD)
    t[F_JUMP] = [(-0.92, 0.92, JUMP)]
    chk = [(-0.92 + i * 1.84 / 12, -0.92 + (i + 1) * 1.84 / 12, CHK0 if i % 2 == 0 else CHK1) for i in range(12)]
    t[F_START] = chk
    for code, lat in DASH_LAT.items():
        base = spans(ROAD, ROAD, ROAD)
        out = []
        for a, b, k in base:
            if a <= lat <= b and k == ROAD:
                out.extend(split(lat, PLATE))
            else:
                out.append((a, b, k))
        t[code] = out
    return {code: build_template(r) for code, r in t.items()}


TEMPL = make_templates()


def rgb_fog(c, fog, f):
    return (int(c[0] + (fog[0] - c[0]) * f), int(c[1] + (fog[1] - c[1]) * f), int(c[2] + (fog[2] - c[2]) * f))


def px12(c):
    return rgb565(*c).to_bytes(2, "little") * 6


def key_color(th, key, p1, p2):
    if key == GA:
        return th["ground"][p1]
    if key == GB:
        return th["ground"][1 - p1]
    if key == BAR:
        return th["bar"][p2]
    if key == RUM:
        return th["rum"][p2]
    if key == ROAD:
        return th["road"][p1]
    if key == LANE:
        return th["lane"] if p1 == 0 else th["road"][1]
    if key == PIT:
        return th["pit"][p2]
    if key == PLATE:
        return th["plate"][p2]
    if key == JUMP:
        return th["jump"][p2]
    if key == CHK0:
        return th["chk"][p2]
    return th["chk"][1 - p2]


def make_palette(th):
    # Fog fades the checker and road towards the horizon colour, which also hides distant stripe aliasing.
    pal = [None]
    for dy in range(1, NDY + 1):
        f = max(0.0, 1.0 - dy / 46.0) ** 1.4
        row = []
        for key in range(NKEYS):
            for p in range(4):
                row.append(px12(rgb_fog(key_color(th, key, p >> 1, p & 1), th["fog"], f)))
        pal.append(row)
    return pal


# ---- track ------------------------------------------------------------------------------------------
def make_track(th):
    n = random.randint(104, 116)
    cur = [0.0] * n
    i = 6
    ramp = (0.4, 0.8)
    sign = random.choice((-1, 1))
    while i < n - 26:
        if random.random() < 0.45:
            i += random.randint(3, 7)
            continue
        length = random.randint(5, 11)
        c = sign * random.uniform(0.0014, 0.0033) * th["curve"]
        for k in range(length):
            j = i + k
            if j >= n - 26:
                break
            e = min(k, length - 1 - k)
            cur[j] = c * (ramp[e] if e < 2 else 1.0)
        i += length
        sign = -sign if random.random() < 0.7 else sign
    feat = [F_NONE] * n
    feat[0] = F_START
    for j in range(n - 22, n - 14):
        feat[j] = F_PIT
    runs, j = [], 0
    while j < n:
        if cur[j] == 0.0:
            k = j
            while k < n and cur[k] == 0.0:
                k += 1
            runs.append((j, k - j))
            j = k
        else:
            j += 1
    dash_slots = list(DASH_LAT)
    placed = 0
    for start, length in runs:
        if start < 2 or start + length > n - 26 + 2 or length < 5:
            continue
        if random.random() < 0.6:
            feat[start + 1] = random.choice(dash_slots)
            placed += 1
        if length >= 8 and random.random() < 0.5:
            feat[start + 5] = random.choice(dash_slots)
            placed += 1
        elif length >= 8 and random.random() < 0.45:
            feat[start + 5] = F_JUMP
    if placed < 2:
        feat[n - 10 if feat[n - 10] == F_NONE else n - 11] = F_DASH_C
        feat[n - 30 if cur[n - 30] == 0 else n - 24] = F_DASH_L
    return n, cur, feat


class Car:
    __slots__ = ("dist", "lat", "v", "lv", "vmax", "color", "shape", "lane", "base", "avoid_t", "bump_t",
                 "ahead", "cool", "num")

    def __init__(self, num):
        self.num = num
        self.dist = 0.0
        self.lat = 0.0
        self.v = 0.0
        self.lv = 0.0
        self.vmax = 100.0
        self.color = num % 6
        self.shape = (num // 6) % 2
        self.lane = 0.0
        self.base = random.uniform(-0.6, 0.6)
        self.avoid_t = 0
        self.bump_t = 0
        self.ahead = True
        self.cool = 0


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


KC = 7e-4            # lateral push per tick from curvature * speed^2
MAXV = 0.045         # steering authority, lateral units per tick
VBASE = 104.0        # player top speed, m/s

# scale step (0 = biggest) of a rival whose feet are dy rows below the horizon: width is ~0.295*dy vpx
SPRITE_IDX = [-1] * (NDY + 1)
for _dy in range(8, NDY + 1):
    _w = min(32.0, max(3.0, 0.295 * _dy))
    SPRITE_IDX[_dy] = int(clamp(round(math.log(32.0 / _w) / math.log(1 / 0.835)), 0, 13))


def make():
    th = None
    pal = None
    n = 0
    cur, feat = [], []
    track_len = 0.0
    player = Car(99)
    cars = []
    S = {}
    cx_row = [160.0] * (NDY + 40)
    hud_cache = {}
    banner = {"lines": [], "t": 0}
    end = EndScreen()
    state = {"phase": "intro", "t": 0, "race": 0, "score": 0, "tick": 0}

    def curve_at(dist):
        return cur[(int(dist) // CELL) % n]

    # ---- race setup ------------------------------------------------------------------------------
    def start_race():
        nonlocal th, pal, n, cur, feat, track_len, cars
        th = D["themes"][state["race"] % len(D["themes"])]
        pal = make_palette(th)
        n, cur, feat = make_track(th)
        track_len = n * CELL
        r = state["race"]
        cars = []
        mine = random.randint(11, 19)
        rivals = []
        for num in range(GRID - 1):
            c = Car(num)
            c.vmax = (108.0 + 1.0 * r) * random.uniform(0.92, 1.04)
            c.dist = 0.0
            rivals.append(c)
        # the grid is two columns, 14 m between rows, behind the start line
        gi = 0
        for slot in range(GRID):
            lat = -0.45 if slot % 2 == 0 else 0.45
            d = -14.0 * (slot // 2) - (7.0 if slot % 2 else 0.0)
            if slot == mine:
                player.dist, player.lat = d, lat
            else:
                c = rivals[gi]
                gi += 1
                c.dist, c.lat, c.lane = d, lat, lat
                cars.append(c)
        random.shuffle(cars)
        for k, c in enumerate(cars):
            c.num = k
            c.color = k % 6
            c.shape = (k // 6) % 2
        player.v = 0.0
        player.lv = 0.0
        S.update(energy=100.0, boost_t=0, boost_cool=0, air_t=0, spin_t=0, tilt=0.0, sky_x=0.0, sky_shown=-1,
                 rank=GRID, overtakes=0, laps_done=0, race_t=0, pit=False, scrape=0, finished=False, spark=0,
                 fin_rank=0)
        draw_static()
        hud_cache.clear()
        banner.update(lines=[(th["name"], "L", COLOR_YELLOW, 236), ("RACE %d/%d" % (r + 1, RACES), "S", COLOR_CYAN, 340)],
                      t=170)
        state["phase"], state["t"] = "intro", 0

    def draw_static():
        clear()
        for k, c in enumerate(D["sky_rows"][state["race"] % len(D["themes"])]):
            fill_rect(0, (14 + k) * PX, W, PX, rgb565(*c))
        for _ in range(60 if state["race"] % 4 in (0, 3) else 25):
            sx, sy = random.randrange(0, W, PX), random.randrange(14 * PX, 34 * PX, PX)
            fill_rect(sx, sy, PX, PX, 0xFFFF if random.random() < 0.6 else rgb565(*th["bar"][0]))
        fill_rect(0, HZ * PX, W, PX, rgb565(*th["fog"]))
        S["sky_shown"] = -1

    # ---- rivals ----------------------------------------------------------------------------------
    def update_rivals():
        everyone = sorted(cars + [player], key=lambda c: -c.dist)
        for k, c in enumerate(everyone):
            if c is player:
                continue
            ca = (curve_at(c.dist + 40) + curve_at(c.dist + 90)) * 0.5
            tv = c.vmax * (1.0 - 22.0 * abs(ca))
            # mild rubber band: cars far behind the player chase, cars far ahead ease off, so a pack stays visible
            gap = c.dist - player.dist
            tv *= 1.0 + min(0.10, -gap / 3000.0) if gap < 0 else 1.0 - min(0.05, gap / 4000.0)
            inside = clamp(ca * 190, -0.55, 0.55)
            if c.avoid_t > 0:
                c.avoid_t -= 1
            else:
                c.lane = clamp(0.45 * c.base + 0.55 * inside, -0.75, 0.75)
                for a in everyone[max(0, k - 2):k]:
                    ahead_gap = a.dist - c.dist
                    if 0 < ahead_gap < 34 and abs(a.lat - c.lat) < 0.5 and a.v < c.v + 6:
                        side = 1.0 if a.lat < 0 else -1.0
                        if abs(a.lat) < 0.15:
                            side = random.choice((-1.0, 1.0))
                        c.lane = clamp(a.lat + 0.62 * side, -0.78, 0.78)
                        c.avoid_t = 50
                        if ahead_gap < 12:
                            tv = min(tv, a.v - 1.0)
                        break
            # never slide sideways into a car that is alongside; if already overlapping, part from it
            for a in everyone[max(0, k - 3):k + 4]:
                if a is c or abs(a.dist - c.dist) >= 12:
                    continue
                if abs(a.lat - c.lat) < 0.4:
                    c.lane = clamp(c.lat + (0.3 if c.lat >= a.lat else -0.3), -0.78, 0.78)
                    break
                if abs(a.lat - c.lane) < 0.45:
                    c.lane = c.lat
                    break
            if state["phase"] == "intro":
                tv = 0.0
            dv = clamp(tv - c.v, -2.0, 0.85)
            c.v = max(0.0, c.v + dv)
            c.lv += (clamp((c.lane - c.lat) * 0.08, -0.03, 0.03) - c.lv) * 0.3
            c.lat = clamp(c.lat + c.lv, -0.85, 0.85)
            c.dist += c.v / 30.0
            if c.bump_t:
                c.bump_t -= 1
            if c.cool:
                c.cool -= 1

    # ---- the bot ---------------------------------------------------------------------------------
    def plan_target():
        p = player.dist
        pi = int(p)
        ca = sum(cur[((pi + d) // CELL) % n] for d in (30, 60, 90, 120, 150)) / 5.0
        target = clamp(ca * 190, -0.55, 0.55)
        # pit lane when power is low
        in_pit = feat[(pi // CELL) % n] == F_PIT
        if S["pit"] and (S["energy"] > 94 or not (in_pit or any(feat[((pi + d) // CELL) % n] == F_PIT for d in (40, 200)))):
            S["pit"] = False
        if not S["pit"] and S["energy"] < 60:
            for d in range(40, 500, 20):
                if feat[((pi + d) // CELL) % n] == F_PIT:
                    S["pit"] = True
                    break
        if S["pit"]:
            target = -0.64
        else:
            # dash plates within reach
            best = None
            for d in range(30, 200, 20):
                code = feat[((pi + d) // CELL) % n]
                if code in DASH_LAT:
                    ticks = d / max(10.0, player.v / 30.0)
                    if abs(DASH_LAT[code] - player.lat) <= MAXV * 0.55 * ticks:
                        best = DASH_LAT[code]
                        break
            if best is not None:
                target = best
        # rivals: slip around the nearest blocker, step away from one alongside
        blocker = None
        for c in cars:
            dz = c.dist - p
            if 0 < dz < 110 and abs(c.lat - target) < 0.52 and (blocker is None or dz < blocker.dist - p):
                blocker = c
            elif -9 < dz <= 0 or 0 < dz < 9:
                if abs(c.lat - player.lat) < 0.5:
                    away = 1.0 if player.lat >= c.lat else -1.0
                    target = player.lat + 0.5 * away
        if blocker is not None:
            right, left = blocker.lat + 0.68, blocker.lat - 0.68
            options = [x for x in (right, left) if abs(x) <= 0.8]
            if options:
                target = min(options, key=lambda x: abs(x - target))
        return clamp(target, -0.8, 0.8), ca

    def update_player():
        p = player
        if state["phase"] == "intro":
            return
        pi = int(p.dist)
        code = feat[(pi // CELL) % n]
        target, ca = plan_target()
        c_here = cur[(pi // CELL) % n]
        spin = S["spin_t"] > 0
        if spin:
            S["spin_t"] -= 1
            p.v = max(0.0, p.v - 2.5)
        boosting = S["boost_t"] > 0
        vmax = VBASE * (1.0 - 20.0 * abs(ca)) * (1.3 if boosting else 1.0)
        if S["boost_cool"]:
            S["boost_cool"] -= 1
        if (not boosting and not spin and S["boost_cool"] == 0 and S["energy"] > 40 and abs(ca) < 0.0007
                and abs(c_here) < 0.0007 and p.v > 0.9 * VBASE and S["air_t"] == 0):
            S["boost_t"] = 45
            S["boost_cool"] = 150
            S["energy"] -= 4.0
        if code in DASH_LAT and abs(p.lat - DASH_LAT[code]) < 0.3 and S["air_t"] == 0:
            S["boost_t"] = max(S["boost_t"], 38)
        if S["boost_t"]:
            S["boost_t"] -= 1
        if code == F_JUMP and S["air_t"] == 0 and p.v > 30:
            S["air_t"] = 26
        if S["air_t"]:
            S["air_t"] -= 1
        if not spin:
            acc = 1.7 if S["boost_t"] else 0.9
            p.v += clamp(vmax - p.v, -1.6, acc)
        drift = c_here * p.v * p.v * KC
        steer = clamp((target - p.lat) * 0.10 + drift, -MAXV, MAXV)
        if S["air_t"] or spin:
            steer = 0.0
        p.lv += (steer - p.lv) * 0.35
        p.lat += p.lv - drift
        S["scrape"] = 0
        if abs(p.lat) > 0.9:
            p.lat = clamp(p.lat, -0.93, 0.93)
            p.lv = -p.lv * 0.4
            p.v *= 0.985
            S["energy"] -= 0.3
            S["scrape"] = 1
        if code == F_PIT and p.lat < -0.3 and S["air_t"] == 0:
            S["energy"] = min(100.0, S["energy"] + 1.2)
        S["tilt"] += (clamp(p.lv / MAXV * 2.2 + drift / MAXV * 0.8, -2.0, 2.0) - S["tilt"]) * 0.3
        p.dist += p.v / 30.0
        state["score"] += p.v / 30.0 / 10.0
        S["sky_x"] += curve_at(p.dist + 40) * p.v * 10.0
        if S["energy"] <= 0:
            S["energy"] = 38.0
            S["spin_t"] = 60
            banner.update(lines=[("POWER OUT", "L", COLOR_RED, 250)], t=60)

    def interactions():
        p = player
        for c in cars:
            dz = c.dist - p.dist
            dl = c.lat - p.lat
            if abs(dz) < 6.0 and abs(dl) < 0.21 and c.bump_t == 0 and S["air_t"] == 0:
                c.bump_t = 24
                away = 1.0 if dl > 0 else -1.0
                if abs(dl) < 0.02:
                    away = random.choice((-1.0, 1.0))
                S["energy"] -= 2.5
                p.lv -= 0.03 * away
                c.lv += 0.03 * away
                if dz > 0:
                    p.v = min(p.v, c.v * 0.97)
                else:
                    c.v = min(c.v, p.v * 0.98)
                    p.v += 1.0
                S["spark"] = 8
            ahead = dz > 0
            if c.ahead and not ahead and c.cool == 0 and state["phase"] != "intro":
                S["overtakes"] += 1
                state["score"] += 100
                c.cool = 240
            c.ahead = ahead
        S["rank"] = 1 + sum(1 for c in cars if c.dist > p.dist)
        laps = int(max(0.0, p.dist) // track_len)
        if laps > S["laps_done"]:
            S["laps_done"] = laps
            state["score"] += 500
            if laps < LAPS:
                banner.update(lines=[("FINAL LAP" if laps == LAPS - 1 else "LAP %d" % (laps + 1), "L", COLOR_CYAN, 250)], t=60)

    # ---- drawing ---------------------------------------------------------------------------------
    def sprite_overlay(over, sp, cx, foot, lift=0):
        w, h, rows = sp
        x0 = int(cx - w / 2)
        top = foot - h + 1 - lift
        for j, spans in enumerate(rows):
            vr = top + j
            if vr < HZ or vr >= 180:
                continue
            lst = over.get(vr)
            if lst is None:
                lst = over[vr] = []
            for sx, data in spans:
                px = x0 + sx
                m = len(data) // 12
                if px < 0:
                    data = data[-px * 12:]
                    m += px
                    px = 0
                if px + m > VW:
                    m = VW - px
                    data = data[:m * 12]
                if m > 0:
                    lst.append((px, data))

    def render():
        pos = player.dist
        lat10 = player.lat * HALF
        xo = dxo = zp = 0.0
        rows = [None] * (NDY + 1)
        for dy in range(NDY, 0, -1):
            z = ZCAM[dy]
            dz = z - zp
            zp = z
            w = int(pos + z - CAMBACK)
            cell = (w // CELL) % n
            dxo += cur[cell] * dz
            xo += dxo * dz
            sc = SCALE[dy]
            cx = 160 + (xo - lat10) * sc
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
                    if x > VW:
                        x = VW
                    out.append(pr[ko + p] * (x - prev))
                    prev = x
            if prev < VW:
                out.append(pr[last + p] * (VW - prev))
            rows[dy] = b"".join(out)
        for dy in range(NDY + 1, NDY + 40):
            cx_row[dy] = cx_row[NDY]
        # sprites: far to near, patched into the finished rows
        over = {}
        visible = []
        for c in cars:
            zr = c.dist - pos
            if -3.0 < zr < 190.0:
                visible.append((zr, c))
        visible.sort(key=lambda t: -t[0])
        for zr, c in visible:
            dy = int(1760.0 / (zr + CAMBACK))
            idx = SPRITE_IDX[min(dy, NDY)]
            if idx < 0 or dy < 8:
                continue
            sc = SCALE[min(dy, NDY)]
            sprite_overlay(over, D["rivals"][c.shape][c.color][idx], cx_row[dy] + (c.lat) * HALF * sc, HZ + dy)
        tilt = int(round(S["tilt"]))
        flame = (1 + (state["tick"] & 1)) if S["boost_t"] else 0
        lift = 0
        if S["air_t"]:
            lift = int(10 * math.sin(math.pi * (26 - S["air_t"]) / 26.0))
        sway = int(S["tilt"] * 1.5)
        sprite_overlay(over, D["player"][tilt + 2][flame], 160 + sway, 172, lift)
        if S["scrape"] or S["spark"]:
            S["spark"] = max(0, S["spark"] - 1)
            side = -1 if player.lat < 0 else 1
            if not S["scrape"]:
                side = random.choice((-1, 1))
            yel = (px12((255, 240, 120)), px12((255, 160, 40)), px12((255, 255, 255)))
            for _ in range(7):
                vr = random.randint(160, 176)
                xx = 160 + side * random.randint(14, 24) + random.randint(-3, 3)
                over.setdefault(vr, []).append((xx, random.choice(yel) * random.randint(1, 2)))
        for dy in range(1, NDY + 1):
            vr = HZ + dy
            row = rows[dy]
            sp = over.get(vr)
            if sp:
                row = bytearray(row)
                for x, data in sp:
                    row[x * 12:x * 12 + len(data)] = data
            fb[vr * BLOCK:(vr + 1) * BLOCK] = row * PX
        off = int(S["sky_x"]) % PERIOD
        if off != S["sky_shown"]:
            S["sky_shown"] = off
            sk = D["skylines"][state["race"] % len(D["themes"])]
            o12 = off * 12
            for j in range(SKYLINE_H):
                vr = SKYLINE_FROM + j
                fb[vr * BLOCK:(vr + 1) * BLOCK] = sk[j][o12:o12 + ROWB] * PX

    def hud():
        if state["phase"] == "intro" and hud_cache.get("init"):
            return
        lap = min(LAPS, S["laps_done"] + 1)
        vals = {"lap": "LAP %d/%d" % (lap, LAPS), "pos": "POS %2d/%d" % (S["rank"], GRID),
                "score": "SCORE %6d" % state["score"], "name": "%-11s" % th["name"],
                "spd": "%4d KM/H" % int(player.v * 4.2), "time": "TIME %d:%02d" % divmod(S["race_t"] // 30, 60)}
        pos_x = {"lap": 24, "pos": 330, "score": 700, "name": 1380, "spd": 24, "time": 1380}
        pos_y = {"lap": 6, "pos": 6, "score": 6, "name": 6, "spd": 46, "time": 46}
        if not hud_cache.get("init"):
            fill_rect(0, 0, W, HUD_H, 0)
            fill_rect(0, HUD_H - 4, W, 4, rgb565(*th["bar"][0]))
            draw_text("POWER", 480, 46, "S", COLOR_CYAN)
            fill_rect(640, 48, 4 + 520, 34, 0xFFFF)
            hud_cache["init"] = True
        for k, text in vals.items():
            if hud_cache.get(k) != text:
                hud_cache[k] = text
                draw_text(text, pos_x[k], pos_y[k], "S", COLOR_YELLOW if k == "name" else COLOR_WHITE)
        e = int(clamp(S["energy"], 0, 100))
        if hud_cache.get("e") != e:
            hud_cache["e"] = e
            col = rgb565(60, 220, 90) if e > 50 else rgb565(250, 210, 40) if e > 25 else rgb565(240, 50, 50)
            fill_rect(644, 52, 512, 26, 0x0000)
            fill_rect(644, 52, int(512 * e / 100), 26, col)

    def draw_banner():
        if banner["t"] <= 0:
            return
        banner["t"] -= 1
        S["sky_shown"] = -1    # the text sits on the skyline rows, which are otherwise skipped when the scroll is idle
        for text, size, color, y in banner["lines"]:
            draw_text_centered_nobg(text, y, size, color)

    def draw_text_centered_nobg(text, y, size, color):
        draw_text(text, (W - text_width(text, size)) // 2, y, size, color, bg=False)

    def finish_race():
        pos = S["rank"]
        S["fin_rank"] = pos
        bonus = max(0, (GRID + 1 - pos)) * 100
        state["score"] += bonus
        suffix = {1: "ST", 2: "ND", 3: "RD"}.get(pos, "TH")
        banner.update(lines=[("FINISH", "L", COLOR_YELLOW, 236), ("%d%s PLACE  +%d" % (pos, suffix, bonus), "S", COLOR_CYAN, 340)],
                      t=190)
        state["phase"], state["t"] = "finish", 0

    start_race()

    def step():
        state["tick"] += 1
        if state["phase"] == "over":
            return end.tick()
        state["t"] += 1
        ph = state["phase"]
        if ph == "intro":
            t = state["t"]
            if t == 60:
                banner.update(lines=[("3", "L", COLOR_RED, 250)], t=30)
            elif t == 90:
                banner.update(lines=[("2", "L", COLOR_RED, 250)], t=30)
            elif t == 120:
                banner.update(lines=[("1", "L", COLOR_YELLOW, 250)], t=30)
            elif t == 150:
                banner.update(lines=[("GO!", "L", COLOR_GREEN, 250)], t=40)
                state["phase"], state["t"] = "race", 0
        elif ph == "race":
            S["race_t"] += 1
            if S["energy"] < 25 and S["race_t"] % 30 == 0 and banner["t"] <= 0 and not S["pit"]:
                banner.update(lines=[("POWER LOW", "S", COLOR_RED, 250)], t=24)
        update_rivals()
        update_player()
        if ph != "intro":
            interactions()
        if ph == "race" and (S["laps_done"] >= LAPS or S["race_t"] > 30 * 170 or state["tick"] > CAP_TICKS - 200):
            finish_race()
        elif ph == "finish" and state["t"] > 190:
            state["race"] += 1
            if state["race"] >= RACES or state["tick"] > CAP_TICKS - 400:
                end.start(int(state["score"]))
                state["phase"] = "over"
                return False
            start_race()
        render()
        draw_banner()
        hud()
        return False
    return step
