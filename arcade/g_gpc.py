# Grand Prix Circuit (Accolade/Distinctive Software, 1988) played by a bot: first-person Formula One from the cockpit,
# eight circuits, qualifying lap -> grid -> four-lamp start -> race -> chequered flag -> points table (9-6-4-3-2-1).
# The picture is the 320x200 DOS look at integer scale 5 (1600x1000) centred on the 1920x1080 screen. Every video
# row is one 3840-byte line (margins included) written five times with a single slice assignment.
import math
from fbcore import *
import g_gpc_tracks as TK

D = load_bundle("g_gpc.bin")
PAL = D["pal"]
P5 = [rgb565(*c).to_bytes(2, "little") * 5 for c in PAL]
BLK, BLU, GRN, CYN, RED, MAG, BRN, LGR, DGR, LBL, LGN, LCY, LRD, LMG, YEL, WHT = range(16)
LINE, MARG, OY = 3840, 320, 40
VT, VB = 61, 109                       # dynamic road zone rows (inclusive)
A_Z, KPX, HWM = 330.0, 0.6, 7.0        # row distance = A_Z/dy, px per metre per row, road half width (m)
HWP = [KPX * HWM * dy for dy in range(80)]
ZT = [0.0] + [A_Z / dy for dy in range(1, 80)]
DT = 1.0 / TICK_RATE
BUCKET_OF = []
_b = [2, 3, 4, 5, 6, 7, 9, 11, 14, 17, 21, 26]
for _dy in range(80):
    BUCKET_OF.append(min(range(len(_b)), key=lambda i: abs(_b[i] - _dy)))
# dithered row textures: pixel x of a row uses pattern[(x + row) % 4], so the texture stays put while the road scrolls
def _dither(pat):
    n = len(pat)
    return [b"".join(P5[pat[(x + ph) % n]] for x in range(320)) for ph in range(n)]


DROW = [_dither((GRN,) * 7 + (LGN,)), _dither((DGR,)), _dither((LGR, LGR, DGR, LGR)),
        _dither((DGR, LGR, DGR, DGR)), _dither((LBL, BLU, BLU, LBL))]
GTEX = {LGR: 18, DGR: 19, BLU: 20, LBL: 20}
CENTRED = ('portal', 'gantry', 'tree', 'pine', 'sign')
CAR_W = [3, 4, 5, 6, 8, 10, 12, 15, 19, 24, 30, 38]
POINTS = [9, 6, 4, 3, 2, 1]
DRIVERS = ["TRAVIS DAYE", "BRUNO GOURO", "DON MATRELLI", "TONI BORLINI", "VITO GIUFFRE", "PETER KURTZ", "CAL TYRONE",
           "TSE SAKAMOTO", "NIGEL LEVINS"]
SKILL = [0.985, 0.975, 0.965, 0.955, 0.945, 0.935, 0.92, 0.90, 0.88]
# vtop m/s, accel m/s2, brake m/s2, grip (g), gear speeds at 11000 rpm; the McLaren is fast and nervous,
# the Ferrari slow and forgiving, as in the manual
CARS = [("MCLAREN", 100.0, 10.6, 20.0, 1.70, [21, 34, 48, 63, 80, 101]),
        ("WILLIAMS", 95.0, 9.9, 23.0, 1.82, [20, 32, 45, 59, 75, 96]),
        ("FERRARI", 92.0, 9.0, 25.0, 1.95, [24, 40, 58, 76, 93])]
MUG = 9.8 * 2.2          # arcade grip: the squeezed circuits would otherwise crawl
PIT_CHANCE = 0.12        # share of races where the bot takes a stop for tyres even without damage
MISTAKE_RATE = 0.0010    # per tick while a corner is near: the bot brakes too late for it
FATAL_CHANCE = 0.03      # per race: the bot forgets to shift until the engine blows
BOOST = 1.6              # accel and brake scale for the same reason


# ---- screen: 200 video rows, each a ready-to-write line --------------------------------------------------------
class Scr:
    def __init__(s):
        s.lines = [bytearray(LINE) for _ in range(200)]
        s.dirty = [True] * 200

    def flush(s):
        d, L = s.dirty, s.lines
        for vy in range(200):
            if d[vy]:
                o = (OY + vy * 5) * S
                fb[o:o + 19200] = L[vy] * 5
                d[vy] = False

    def put(s, x, y, data):
        o = MARG + x * 10
        s.lines[y][o:o + len(data)] = data
        s.dirty[y] = True

    def rect(s, x, y, w, h, c):
        x0, x1 = max(0, x), min(320, x + w)
        if x1 <= x0:
            return
        data = P5[c] * (x1 - x0)
        for j in range(max(0, y), min(200, y + h)):
            s.put(x0, j, data)

    def sprite(s, spr, x, y):
        # run sprite (w, h, rows[[(x0, bytes)]]) with its top-left corner at x, y; clipped to the screen
        w, h, rows = spr
        for j in range(h):
            yy = y + j
            if yy < 0 or yy >= 200:
                continue
            for x0, b in rows[j]:
                dx = x + x0
                n = len(b) // 10
                if dx >= 320 or dx + n <= 0:
                    continue
                if dx < 0:
                    b, dx, n = b[-dx * 10:], 0, n + dx
                if dx + n > 320:
                    b = b[:(320 - dx) * 10]
                o = MARG + dx * 10
                s.lines[yy][o:o + len(b)] = b
            s.dirty[yy] = True


scr = Scr()
_gcache = {}


def glyph_rows(ch, fg, bg, sc):
    k = (ch, fg, bg, sc)
    r = _gcache.get(k)
    if r is None:
        r = []
        for bits in D["font"].get(ch, D["font"][" "]):
            row = b"".join((P5[fg] if bits >> (5 - i) & 1 else P5[bg]) * sc for i in range(6))
            r.extend([row] * sc)
        _gcache[k] = r
    return r


def text(x, y, s, fg=WHT, bg=BLK, sc=1):
    for i, ch in enumerate(s):
        for j, row in enumerate(glyph_rows(ch, fg, bg, sc)):
            if 0 <= y + j < 200:
                scr.put(x + i * 6 * sc, y + j, row)


def ctext(y, s, fg=WHT, bg=BLK, sc=1):
    text((320 - len(s) * 6 * sc) // 2, y, s, fg, bg, sc)


def fmt_time(t):
    t = max(0.0, t)
    return "%02dm%04.1fs" % (int(t // 60), t % 60)


# ---- track -----------------------------------------------------------------------------------------------------
class Track:
    def __init__(s, name, rnd):
        t = TK.build(name)
        s.name, s.n, s.step, s.L = name, t["n"], t["step"], t["length"]
        s.curv, s.grad, s.tun, s.bri, s.info = t["curv"], t["grad"], t["tun"], t["bri"], t["info"]
        s.horizon = D["horizon"][name]
        s.street = s.info["street"]
        n = s.n
        th, a = [0.0], 0.0
        for c in s.curv:
            a += c * s.step
            th.append(a)
        s.th = th
        grounds = {"MONACO": ((LGR, DGR), (LBL, BLU)), "DETROIT": ((LGR, DGR), (DGR, LGR)),
                       "ITALY": ((LGN, GRN),) * 2, "CANADA": ((LGN, GRN),) * 2}
        s.ground = grounds.get(name, ((GRN, LGN), (GRN, LGN)))
        s.build_profile()
        s.objs = s.make_objects(rnd)
        s.map = s.make_map()

    def cell(s, pos):
        return int(pos / s.step) % s.n

    def corner_limit(s, car):
        # per-cell speed allowed by grip, then by braking distance to the next slow cell
        vtop, a0, br, g = car[1], car[2] * BOOST, car[3] * BOOST, car[4]
        n, c = s.n, s.curv
        vc = [min(vtop, math.sqrt(g * MUG / max(abs(c[i]), 1e-5))) for i in range(n)]
        vc = [min(vc[(i - 1) % n], vc[i], vc[(i + 1) % n]) for i in range(n)]
        vb = vc[:]
        for k in range(2 * n):
            i = (n - 1 - k) % n
            vb[i] = min(vc[i], math.sqrt(vb[(i + 1) % n] ** 2 + 2 * br * s.step))
        vf = vb[:]
        for k in range(2 * n):
            i = k % n
            v = vf[i]
            a = a0 * (1 - (v / vtop) ** 2)
            vf[(i + 1) % n] = min(vb[(i + 1) % n], math.sqrt(v * v + 2 * max(a, 0.3) * s.step))
        return vb, sum(s.step / max(v, 5.0) for v in vf)

    def build_profile(s):
        s.vb, s.ideal = {}, {}
        for i, cr in enumerate(CARS):
            s.vb[i], s.ideal[i] = s.corner_limit(cr)

    def make_objects(s, rnd):
        o = []
        L, n = s.L, s.n
        street = s.street
        # tunnel mouths, bridge, start gantry, pit garages
        o.append((0.0, 0.0, "gantry", 0))
        for key in ("tun", "bri"):
            arr = getattr(s, key)
            for i in range(n):
                if arr[i] and not arr[i - 1]:
                    o.append((i * s.step, 0.0, "portal", 0))
                if arr[i] and not arr[(i + 1) % n]:
                    o.append(((i + 1) * s.step, 0.0, "portal", 0))
        for k in range(4):
            o.append((L - 150 + k * 40, 1.85, "garage", 0))
        for side in (-1, 1):
            for k in range(3):
                o.append((20 + k * 60.0, side * 1.7, "stand", k % 4))
        # braking boards before sharp corners
        i = 0
        while i < n:
            if abs(s.curv[i]) > 1 / 130 and abs(s.curv[i - 1]) <= 1 / 130:
                for k, d in enumerate((120, 80, 40)):
                    o.append(((i * s.step - d) % L, 1.3, "sign", k))
                while i < n and abs(s.curv[i]) > 1 / 130:
                    i += 1
            i += 1
        step = 22.0
        p = 10.0
        while p < L:
            for side in (-1, 1):
                if rnd.random() < .75:
                    lat = side * rnd.uniform(1.6, 3.4)
                    r = rnd.random()
                    if street:
                        kind = "tower" if (s.name == "DETROIT" and r < .15) else "building"
                        if s.name == "MONACO" and side == 1:
                            kind = "yacht"
                            lat = side * rnd.uniform(3.2, 4.5)
                        o.append((p, lat, kind, rnd.randrange(2 if kind == "yacht" else 4) if kind != "tower" else 0))
                    elif r < .22:
                        o.append((p, lat, "board", rnd.randrange(4)))
                    elif r < .6:
                        o.append((p, lat, "tree", rnd.randrange(2)))
                    else:
                        o.append((p, lat, "pine", 0))
            p += step * rnd.uniform(.7, 1.3)
        return o

    def make_map(s):
        x = y = 0.0
        pts = []
        for i in range(0, s.n):
            a = s.th[i]
            x += math.cos(a) * s.step
            y += math.sin(a) * s.step
            pts.append((x, y))
        # the lap rarely closes exactly: spread the leftover over the whole outline
        n = len(pts)
        pts = [(px - x * (i + 1) / n, py - y * (i + 1) / n) for i, (px, py) in enumerate(pts)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        sc = min(36 / (max(xs) - min(xs) + 1), 18 / (max(ys) - min(ys) + 1))
        mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        return [(int(21 + (px - mx) * sc), int(11 + (py - my) * sc)) for px, py in pts]


# ---- cars ------------------------------------------------------------------------------------------------------
class Car:
    def __init__(s, idx, name, team, ctype, skill, is_player=False):
        s.idx, s.name, s.team, s.ct, s.skill, s.player = idx, name, team, ctype, skill, is_player
        s.car = CARS[ctype]
        s.reset(0.0, 0.0)

    def reset(s, dist, lat):
        s.dist, s.lat, s.v = dist, lat, 0.0
        s.dmg = s.tyre = s.eng = 0.0
        s.state, s.st_t = "run", 0.0
        s.fin_t = None
        s.pass_side, s.pass_t = 0, 0.0
        s.gear, s.shift_t, s.shift_rpm = 0, 0.0, 10500
        s.rpm = 3000.0
        s.steer = 0.0
        s.mistake_t, s.mistake = 0.0, 0.0
        s.pit_req, s.pit_done = False, False
        s.launch_t = 0.0
        s.lap_start, s.laps_t = 0.0, []
        s.hold = False
        s.over_rev_t = 0.0
        s.immune = 0.0
        s.skid = 0.0
        s.pace_noise = 1.0


# ---- the race simulation ---------------------------------------------------------------------------------------
class Race:
    def __init__(s, track, cars, laps, rnd):
        s.tr, s.cars, s.laps, s.rnd = track, cars, laps, rnd
        s.t = 0.0
        s.finished = []
        s.over = False

    def ahead_of(s, c, maxd=45.0):
        L = s.tr.L
        best = None
        for o in s.cars:
            if o is c or o.state == "dnf":
                continue
            d = (o.dist - c.dist)
            if 0 < d < maxd and (best is None or d < best[0]):
                best = (d, o)
        return best

    def slip(s, c):
        r = s.ahead_of(c, 28.0)
        return bool(r and abs(r[1].lat - c.lat) < 0.3)

    def drive(s, c, dt, vb):
        tr = s.tr
        L = tr.L
        pos = c.dist % L
        i = tr.cell(pos)
        look = tr.cell(pos + c.v * 0.2)
        vt = vb[look] * c.skill * c.pace_noise
        if c.mistake_t > 0:
            c.mistake_t -= dt
            vt *= c.mistake
        vtop, a0, br, g = c.car[1], c.car[2] * BOOST, c.car[3] * BOOST, c.car[4]
        lead = s.ahead_of(c, 40.0)
        c0, c1 = tr.curv[i], tr.curv[tr.cell(pos + 55)]
        # racing line: outside on the approach, inside through the corner, avoidance offset when a car is ahead
        thr = 1 / 200
        lt = 0.0
        if abs(c0) > thr:
            lt = 0.55 * (1 if c0 > 0 else -1)
        elif abs(c1) > thr:
            lt = -0.5 * (1 if c1 > 0 else -1)
        if lead and abs(lead[1].lat - c.lat) < 0.42:
            if c.pass_t <= 0:
                c.pass_side = -1 if lead[1].lat > 0.2 else 1
                c.pass_t = 1.6
            lt = max(-0.8, min(0.8, lead[1].lat + 0.62 * c.pass_side))
            if lead[0] < 14 and abs(lead[1].lat - c.lat) < 0.3:
                vt = min(vt, lead[1].v * 0.97)
        c.pass_t -= dt
        c.immune -= dt
        if c.state == "pit_in":
            lt = 1.42
        elif c.state == "pit_out":
            lt = 1.42 if pos < 60 or pos > L - 120 else 0.8
        # speed control
        if c.state == "pit_in":
            vt = 34.0 if pos < L - 30 else 0.0
        elif c.state == "pit_out":
            vt = 34.0 if (pos < 60 or pos > L - 120) else vt
        elif c.state in ("grid",) or c.hold:
            vt = 0.0
        vlim = vtop * (1.04 if s.slip(c) else 1.0) * (1 - 0.0016 * c.dmg)
        a = a0 * (1.15 if s.slip(c) else 1.0) * max(0.0, 1 - (c.v / vlim) ** 2) * (1 - 0.003 * c.tyre)
        if c.shift_t > 0:
            a *= 0.1
        if c.v > vt + 0.5:
            c.v -= br * (1 - 0.004 * c.dmg) * dt * min(1.0, (c.v - vt) / 4 + 0.35)
        elif c.v < vt:
            c.v = min(vt, c.v + max(a, 0.0) * dt)
        # grip: demand above 1 pushes the car wide
        demand = abs(c0) * c.v * c.v / (g * MUG)
        out = -1 if c0 > 0 else 1
        if demand > 1.04:
            c.lat += out * (demand - 1.04) * 1.6 * dt
            c.tyre += 3 * dt
            c.skid = 0.3
            if demand > 1.7 and c.state == "run" and c.player and c.immune <= 0:
                c.state, c.st_t, c.immune = "spin", 1.4, 3.0
                c.v *= 0.5
        else:
            c.skid = max(0.0, c.skid - dt)
        dl = max(-1.0, min(1.0, (lt - c.lat) * 2.0))
        c.lat += dl * dt
        c.steer = max(-1.0, min(1.0, demand * (1 if c0 > 0 else -1) * 1.0 + dl * 0.6))
        # off the road / barriers
        al = abs(c.lat)
        wall = 1.28 if tr.street else 2.2
        pitlane = (pos > L - 170 or pos < 45)
        if al > 1.12 and not (pitlane and al < 1.6 and c.state in ("pit_in", "pit_out")):
            lim = 38.0
            if c.v > lim:
                c.v = max(lim, c.v - 30 * dt)
            c.dmg += 1.2 * dt * (1.0 if c.player else 0.4)
            c.tyre += 2 * dt
            c.skid = 0.3
        if al > wall:
            c.lat = math.copysign(wall - 0.02, c.lat)
            c.v *= 0.5
            c.dmg += 7
            c.state, c.st_t, c.immune = "spin", 1.2, 3.0
        c.dist += c.v * dt
        c.tyre = min(100.0, c.tyre + c.v * 0.0006 * dt * 30 * 0.2)

    def player_gears(s, c, dt, shift_ok):
        gs = c.car[5]
        top = len(gs) - 1
        c.rpm = max(3200.0, c.v / gs[c.gear] * 11000) if c.v > 0.5 else 3200.0
        if c.shift_t > 0:
            c.shift_t -= dt
            return
        if c.gear < top and c.rpm >= c.shift_rpm and shift_ok:
            c.gear += 1
            c.shift_t = 0.2
            c.shift_rpm = s.rnd.uniform(10100, 10800)
            c.knob_t = 0.2
        elif c.gear > 0 and c.rpm < 5000:
            c.gear -= 1
            c.shift_t = 0.2
        if c.rpm > 11300:
            c.eng += (c.rpm - 11300) / 1000 * 25 * dt
            c.over_rev_t += dt


# ---- rendering -------------------------------------------------------------------------------------------------
def render_view(race, pc, hoff, tr, spin_x):
    """Draws the road zone, the horizon and everything on it for the player's car pc."""
    L = tr.L
    pos = pc.dist % L
    cam = pc.lat * HWM
    ci = tr.cell(pos + 70)
    shift = int(round(-tr.grad[ci] * 3.2))
    h = 78 + shift
    nrows = VB - h
    tun = tr.tun[tr.cell(pos)]
    lines = scr.lines
    # sky / horizon strip
    off = int(hoff) % 640
    j0 = h - 17
    sky_c = P5[BLK] if tun else P5[LCY]
    skyrow = sky_c * 320
    for vy in range(VT, h):
        j = vy - j0
        if tun:
            row = skyrow
        elif j >= 0:
            row = tr.horizon[j][off * 10:off * 10 + 3200]
        else:
            row = skyrow
        lines[vy][MARG:MARG + 3200] = row
        scr.dirty[vy] = True
    if tun:
        for vy in range(VT + 3, h, 6):
            scr.rect(40, vy, 240, 1, DGR)
        # ceiling lamps
        for vy in range(VT + 1, h, 8):
            for lx in range(60, 260, 40):
                scr.rect(lx + (vy % 16), vy, 6, 2, YEL)
        ex = None
        for k in range(1, 70):
            if not tr.tun[tr.cell(pos + k * 5)]:
                ex = k * 5
                break
        if ex is not None:
            dy_e = max(1, min(40, int(A_Z / ex)))
            w = int(4.2 * dy_e * 1.2)
            hh = int(min(30, 3.6 * dy_e * KPX))
            scr.rect(160 - w // 2 + int(spin_x), h - hh, w, hh, LCY)
    # road rows, nearest row first so the curve accumulates outward
    th_a = 0.0
    xw = 0.0
    zp = 0.0
    cxs = [0] * 80
    c_arr, n, step = tr.curv, tr.n, tr.step
    street = tr.street
    gl, gr = tr.ground
    pit_zone = (pos > L - 260 or pos < 90)
    row_parts = []
    for dy in range(nrows, 0, -1):
        z = ZT[dy]
        dz = z - zp
        zp = z
        s_abs = pos + z
        c = c_arr[int(s_abs / step) % n]
        th_a += c * dz
        xw += th_a * dz
        cx = 160 + spin_x + (xw - cam) * KPX * dy
        if cx > 3000:
            cx = 3000
        elif cx < -3000:
            cx = -3000
        cxs[dy] = cx
        hw = HWP[dy]
        # far rows are one pixel thick: stripes there would shimmer, so they keep a fixed phase
        near = dy > 4
        p1 = int(s_abs / 36) & 1 if near else 0
        pw = int(s_abs / 5) & 1 if near else 0
        pk = int(s_abs / 6) & 1 if near else 0
        pr = int(s_abs / 14) & 1 if near else 0
        ltun = tr.tun[int(s_abs / step) % n]
        sa = s_abs % L
        segs = []
        road_c = DGR
        if ltun:
            g0 = g1 = BLK
            ro = DGR
            kr = (DGR, LGR)[pk]
        elif street:
            g0 = gl[0] if pw == 0 else GTEX[gl[1]]
            g1 = gr[0] if pw == 0 else GTEX[gr[1]]
            ro = (WHT, LRD)[pk]
            kr = (LRD, WHT)[pk]
        else:
            g0 = g1 = tr.ground[0][0] if p1 == 0 else 16
            ro = LGR
            kr = (LRD, WHT)[pk]
        wl, wr = (1.25, 1.25) if street else (1.42, 1.42)
        rrw = wr
        rc = ro
        if pit_zone and (sa > L - 170 or sa < 45):
            rc = DGR
            rrw = 1.62
        e = cx - hw * wl
        segs.append((e, g0))
        segs.append((cx - hw * 1.12, ro))
        segs.append((cx - hw * 1.0, kr))
        segs.append((cx - hw * 0.95, WHT))
        if sa < 6.0 and dy > 1:
            for q in range(12):
                a0 = cx - hw * 0.95 + hw * 1.9 * (q + 1) / 12
                segs.append((a0, WHT if (q + (int(sa / 3))) & 1 else BLK))
        else:
            dash = (int(s_abs / 9) & 1) and dy > 3
            if dash:
                w = max(0.7, hw * 0.03)
                segs.append((cx - w, road_c))
                segs.append((cx + w, WHT))
            segs.append((cx + hw * 0.95, road_c))
        segs.append((cx + hw * 1.0, WHT))
        segs.append((cx + hw * 1.12, kr))
        segs.append((cx + hw * rrw, rc))
        if rrw > 1.5:
            segs.append((cx + hw * 1.7, WHT))
        segs.append((9999, g1))
        # compose
        prev = 0
        parts = []
        for xe, col in segs:
            xe = int(xe + 0.5)
            if xe > 320:
                xe = 320
            if xe > prev:
                parts.append(P5[col] * (xe - prev) if col < 16 else DROW[col - 16][(dy * 3) % len(DROW[col - 16])][prev * 10:xe * 10])
                prev = xe
                if prev >= 320:
                    break
        vy = h + dy
        lines[vy][MARG:MARG + 3200] = b"".join(parts)
        scr.dirty[vy] = True
    # drawables far to near: scenery and rivals ahead
    items = []
    for (op, ol, kind, var) in tr.objs:
        d = (op - pos) % L
        if 14 < d < 320:
            items.append((d, ol, kind, var, 0))
    for o in race.cars:
        if o is pc or o.state == "dnf":
            continue
        d = o.dist - pc.dist
        if 3 < d < 320:
            items.append((d, o.lat, "car", o.team, o.skid))
    items.sort(key=lambda t: -t[0])
    objs = D["objs"]
    for d, ol, kind, var, extra in items:
        dy = int(A_Z / d + 0.5)
        if dy < 1 or dy > nrows:
            continue
        cx = cxs[dy]
        if kind == "car":
            wpx = 0.27 * HWP[dy] * 2 * 0.5 * 2
            idx = min(range(len(CAR_W)), key=lambda i: abs(CAR_W[i] - wpx))
            spr = D["cars"][var][idx]
            x = int(cx + ol * HWP[dy]) - spr[0] // 2
            y = h + dy - spr[1] + 1
            scr.sprite(spr, x, y)
            if extra > 0 and dy > 6:
                scr.rect(x - 2, h + dy - 2, spr[0] + 4, 2, LGR)
        else:
            if dy > 26 and kind not in ("portal", "gantry"):
                continue
            bi = BUCKET_OF[min(dy, 79)]
            spr = objs[(kind, var)][bi]
            x = int(cx + ol * HWP[dy]) - spr[0] // 2
            if kind not in CENTRED and ol:
                # ol marks the inner edge: a 24 m stand centred on it would lie across the track
                x += int(math.copysign(spr[0] // 2, ol))
            y = h + dy - spr[1] + 1
            if y < VT:
                # clip the top: skip rows above the dynamic zone
                cut = VT - y
                spr = (spr[0], spr[1] - cut, spr[2][cut:])
                y = VT
            scr.sprite(spr, x, y)
    return h, nrows


# ---- cockpit overlay -------------------------------------------------------------------------------------------
TACH = []
for _k in range(121):
    ang = math.radians(10 + _k / 10.0 * 26.25)
    pts = set()
    for q in range(1, 31):
        r = q / 30.0
        pts.add((160 + int(round(math.cos(ang) * 28 * r)), 150 + int(round(math.sin(ang) * 19 * r))))
    TACH.append(sorted(pts))
KNOB_XY = {0: (276, 148), 1: (276, 168), 2: (288, 148), 3: (288, 168), 4: (300, 148), 5: (300, 168)}


def gauge_needle(cx, cy, frac, c):
    ang = math.radians(150 + frac * 240)
    for q in range(1, 13):
        scr.rect(cx + int(math.cos(ang) * 17 * q / 12), cy + int(math.sin(ang) * 12 * q / 12), 1, 1, c)


class Dash:
    def __init__(s):
        s.key = None
        s.mirror = [None, None]

    def invalidate(s):
        s.key = None

    def draw(s, pc, race, fire, blink, wheel_k):
        km = int(pc.v * 3.6 * 0.621 + 0.5)
        rpm = int(pc.rpm / 100)
        kn = pc.gear
        kx = getattr(pc, "knob_t", 0.0)
        mir = s.mirror_cars(pc, race)
        dm = int(pc.dmg / 4)
        key = (wheel_k, km, rpm, kn, kx > 0, dm, int(pc.eng / 10), fire, blink, mir, pc.rpm > 10300)
        if key == s.key:
            return
        s.key = key
        rows = D["dash"][wheel_k + 4]
        L = scr.lines
        for j in range(90):
            L[110 + j][MARG:MARG + 3200] = rows[j]
            scr.dirty[110 + j] = True
        text(99, 118, "%03d" % min(999, km), LRD, BLK)
        frac = min(pc.dmg, 100) / 100
        bar = int(80 * frac)
        scr.rect(135, 118, 80, 8, BLK)
        scr.rect(135, 118, bar, 8, LGN if frac < .4 else (YEL if frac < .75 else LRD))
        for k, (lx, ly) in enumerate(((221, 117), (212, 126), (225, 126))):
            if pc.rpm > (9000, 9900, 10500)[k]:
                scr.rect(lx + 1, ly + 1, 9, 4, LGN)
        scr.rect(71, 136, 6, 6, LGN)
        if pc.eng > 8 or pc.dmg > 60 or fire:
            scr.rect(244, 136, 6, 6, LRD)
        for (x, y) in TACH[min(120, rpm)]:
            scr.rect(x, y, 1, 1, WHT)
        gauge_needle(105, 157, 0.35 + 0.35 * min(1, pc.rpm / 11000) - 0.02 * min(5, pc.dmg / 20), YEL)
        gauge_needle(215, 157, 0.30 + 0.25 * min(1, pc.v / 100) + 0.004 * pc.eng + 0.003 * pc.dmg, LRD)
        kx_, ky_ = KNOB_XY[kn]
        if kx > 0:
            ky_ = 159
        scr.sprite(D["knob"], kx_ - 4, ky_ - 4)
        if fire:
            for _ in range(14):
                scr.rect(random.randrange(70, 250), random.randrange(112, 160), random.randrange(4, 14),
                         random.randrange(3, 9), random.choice((YEL, LRD, RED)))
            if blink:
                scr.rect(57, 177, 19, 9, YEL)
        for side, ms in enumerate(mir):
            mx = 2 if side == 0 else 256
            for (team, sz, px, py) in ms:
                scr.sprite(D["mcars"][team][sz], mx + px, 111 + py)

    def mirror_cars(s, pc, race):
        out = ([], [])
        for o in race.cars:
            if o is pc or o.state == "dnf":
                continue
            d = pc.dist - o.dist
            if 3 < d < 60:
                sz = 2 if d < 12 else (1 if d < 28 else 0)
                px = int(30 + (o.lat - pc.lat) * 14)
                side = 0 if o.lat <= pc.lat + 0.1 else 1
                out[side].append((o.team, sz, max(2, min(46, px)), 9 + (2 - sz) * 1))
        return (tuple(out[0][:2]), tuple(out[1][:2]))


dash = Dash()


# ---- HUD boxes -------------------------------------------------------------------------------------------------
def draw_lamps(n):
    rows = D["lamps"][n]
    for j in range(43):
        scr.put(0, 17 + j, rows[j])


def draw_info(pos, lap, t1, t2):
    rows = D["infobase"]
    for j in range(28):
        scr.put(240, 17 + j, rows[j])
    text(247, 20, "P:%02dL:%02d" % (pos, lap), WHT, LRD)
    text(247, 29, fmt_time(t1), BLK, LRD)
    text(247, 38, fmt_time(t2), BLK, LRD)


def draw_map(tr, cars, pc, blink):
    rows = D["mapbase"]
    for j in range(23):
        scr.put(47, 17 + j, rows[j])
    for (x, y) in tr.map[::2]:
        scr.rect(47 + x, 17 + y, 1, 1, BLK)
    for o in cars:
        if o is pc or o.state == "dnf":
            continue
        x, y = tr.map[tr.cell(o.dist % tr.L) % len(tr.map)]
        scr.rect(47 + x, 17 + y, 2, 2, YEL)
    x, y = tr.map[tr.cell(pc.dist % tr.L) % len(tr.map)]
    scr.rect(47 + x - 1, 17 + y - 1, 3, 3, LRD if blink else WHT)


def restore_static():
    # black bars, static sky rows and the empty cockpit; used after a full-screen table
    for vy in range(0, 17):
        scr.lines[vy][:] = bytes(LINE)
        scr.dirty[vy] = True
    for vy in range(189, 200):
        scr.lines[vy][:] = bytes(LINE)
        scr.dirty[vy] = True
    for j, row in enumerate(D["sky"]):
        scr.lines[17 + j][MARG:MARG + 3200] = row
        scr.dirty[17 + j] = True
    dash.invalidate()


def black_screen():
    for vy in range(200):
        scr.lines[vy][:] = bytes(LINE)
        scr.dirty[vy] = True


# ---- bot driver tweaks for the player --------------------------------------------------------------------------
def build_grid(race, order):
    for i, c in enumerate(order):
        row, col = divmod(i, 2)
        c.reset(-(10.0 + row * 9.0 + col * 4.5), -0.38 if col == 0 else 0.38)
        c.state = "grid"
        c.gear = 0


# ---- the whole game --------------------------------------------------------------------------------------------
def make():
    rnd = random
    clear(0)
    pcar_type = rnd.randrange(3)
    team_pool = [i for i in range(10) if i != pcar_type]
    rnd.shuffle(team_pool)
    player = Car(0, "YOU", pcar_type, pcar_type, rnd.uniform(0.935, 0.98), True)
    rivals = []
    for i in range(9):
        t = team_pool[i]
        rivals.append(Car(i + 1, DRIVERS[i], t, t % 3 if t > 2 else t, SKILL[i], False))
    allcars = [player] + rivals
    # four races of the eight-race championship, kept in the original order
    rounds = sorted(rnd.sample(range(8), 4))
    points = {c.idx: 0 for c in allcars}
    st = dict(phase="title", t=0, race_no=0, score=0, tr=None, race=None, tick=0, fire=False, hoff_spin=0.0)
    st["end"] = None
    res_hist = []
    scr.flush()

    def start_round():
        nm = TK.NAMES[rounds[st["race_no"]]]
        st["tr"] = Track(nm, rnd)
        st["round_name"] = nm
        for c in allcars:
            c.skill_base = c.skill
            c.pace_noise = rnd.uniform(0.985, 1.005)
        player.pace_noise = rnd.uniform(0.98, 1.0)
        st["fatal"] = rnd.random() < FATAL_CHANCE
        st["pit_plan"] = rnd.random() < PIT_CHANCE
        st["race"] = Race(st["tr"], allcars, 3, rnd)
        st["phase"], st["t"] = "intro", 0

    def table(title, rows, hl=None, sub=None):
        black_screen()
        ctext(24, title, YEL, BLK, 2)
        if sub:
            ctext(48, sub, LCY)
        y = 62
        for line, colr in rows:
            text(40, y, line, colr)
            y += 11
        scr.flush()

    def classification(race):
        done = [c for c in allcars if c.fin_t is not None]
        done.sort(key=lambda c: c.fin_t)
        rest = [c for c in allcars if c.fin_t is None and c.state != "dnf"]
        rest.sort(key=lambda c: -c.dist)
        dnf = [c for c in allcars if c.state == "dnf"]
        return done + rest + dnf

    def player_ai(c, race, dt):
        # the bot's own mistakes: late braking that runs wide, a missed upshift
        near = abs(race.tr.curv[race.tr.cell(c.dist % race.tr.L + 60)]) > 1 / 160
        if c.mistake_t <= 0 and c.state == "run" and st["phase"] == "race" and near and rnd.random() < MISTAKE_RATE:
            c.mistake_t, c.mistake = 1.6, rnd.uniform(1.25, 1.7)
        if st["fatal"] and c.dist > race.tr.L * 1.4 and c.state == "run":
            c.shift_rpm = 99999
        race.player_gears(c, dt, True)

    def update_state(c, race, dt):
        tr = race.tr
        if c.state == "spin":
            c.st_t -= dt
            c.v *= (1 - 1.8 * dt)
            c.dmg += 1.5 * dt
            if c.st_t <= 0:
                c.state = "run"
        if c.state == "run" and c.pit_req and not c.pit_done and st["phase"] == "race":
            pos = c.dist % tr.L
            if pos > tr.L - 175 and 40 < c.dist < tr.L * (race.laps - 1):
                c.state = "pit_in"
        if c.state == "pit_in" and c.v < 0.5 and c.dist % tr.L > tr.L - 40:
            c.state, c.st_t = "pit_stop", 5.5 if c.dmg > 40 else 3.8
            c.pit_changed = "ALL" if c.dmg > 40 else rnd.choice(("LEFT", "RIGHT"))
            c.v = 0.0
        if c.state == "pit_stop":
            c.st_t -= dt
            c.v = 0.0
            if c.st_t <= 0:
                c.dmg = 0.0 if c.pit_changed == "ALL" else c.dmg * 0.4
                c.tyre = 0.0
                c.state, c.pit_done = "pit_out", True
        if c.state == "pit_out" and c.dist % tr.L > 70 and c.dist % tr.L < tr.L - 200:
            c.state = "run"
        if c.eng >= 100 and c.state != "dnf":
            c.state, c.v = "dnf", 0.0
            st["fire"] = c.player
            st["fire_t"] = 0.0
        if c.dmg >= 100 and c.state != "dnf":
            c.state, c.v = "dnf", 0.0

    def sim_race(dt):
        race = st["race"]
        tr = race.tr
        race.t += dt
        for c in allcars:
            if c.state == "pit_stop":
                update_state(c, race, dt)
                continue
            if c.state == "dnf":
                continue
            if c.state == "grid":
                continue
            if c.fin_t is not None:
                c.hold = False
            vb = tr.vb[c.ct]
            if c.player:
                player_ai(c, race, dt)
            race.drive(c, dt, vb)
            update_state(c, race, dt)
            L = tr.L
            if c.fin_t is None and c.dist >= race.laps * L:
                c.fin_t = race.t
                if c.player:
                    st["fin_at"] = race.t
            if c.player:
                lap = int(c.dist // L)
                if lap >= 1 and len(c.laps_t) < lap:
                    c.laps_t.append(race.t)
            # pit decision once per car, on the first or second lap
            if not c.pit_req and not c.pit_done and c.dist > tr.L * 0.5 and c.dist < tr.L * (race.laps - 1):
                if c.dmg > 40 or c.tyre > 88 or (c.player and st["pit_plan"]):
                    c.pit_req = True
        # contacts
        order = sorted((c for c in allcars if c.state != "dnf"), key=lambda c: -c.dist)
        for a, b in zip(order, order[1:]):
            gap = a.dist - b.dist
            if gap < 4.2 and abs(a.lat - b.lat) < 0.26 and b.state in ("run", "grid", "pit_out") and a.state != "pit_stop":
                if b.state == "grid":
                    continue
                b.v = min(b.v, a.v * 0.96)
                b.dmg += 5 * dt * 4
                a.dmg += 2 * dt * 4
                push = 0.4 * dt
                if a.lat >= b.lat:
                    a.lat += push
                    b.lat -= push
                else:
                    a.lat -= push
                    b.lat += push
                b.dist = a.dist - 4.2

    def draw_race_frame(pc, race, hoff_extra):
        tr = race.tr
        pos = pc.dist % tr.L
        hoff = tr.th[tr.cell(pos) % len(tr.th)] * 305
        sx = hoff_extra
        render_view(race, pc, hoff + sx * 0.5, tr, sx)
        wk = int(round(pc.steer * 4))
        st["wk"] = max(-4, min(4, wk))

    def hud_race(pc, race, quali):
        tr = race.tr
        order = classification(race) if not quali else [pc]
        p = order.index(pc) + 1
        lap = min(race.laps, int(max(0, pc.dist) // tr.L) + 1)
        if quali:
            lap = 1
        t_lap = race.t - (pc.laps_t[-1] if pc.laps_t else 0.0)
        if st["tick"] % 3 == 0:
            draw_info(p, lap, max(0.0, race.t), max(0.0, t_lap))
        if st["tick"] % 4 == 0:
            draw_map(tr, allcars if not quali else [pc], pc, (st["tick"] // 8) & 1)
        blink = (st["tick"] // 5) & 1
        dash.draw(pc, race, st["fire"] and st.get("fire_t", 0) < 2.5, blink, st.get("wk", 0))

    def pit_scene(c, race):
        scr.rect(0, 17, 320, 93, DGR)
        scr.rect(0, 17, 320, 30, LCY)
        scr.rect(0, 47, 320, 14, LGR)
        scr.rect(0, 61, 320, 49, DGR)
        for x in range(0, 320, 40):
            scr.rect(x, 61, 20, 2, WHT)
        # the car from above-behind with crew
        scr.rect(120, 70, 80, 30, WHT)
        scr.rect(112, 74, 12, 22, BLK)
        scr.rect(196, 74, 12, 22, BLK)
        scr.rect(150, 80, 20, 14, LRD)
        t = int(st["t"] * 8) & 1
        for k, (x, y) in enumerate(((100, 74), (100, 90), (214, 74), (214, 90), (156, 104))):
            scr.rect(x + t * (k % 2), y, 6, 8, [LBL, YEL, LMG, LGN, LCY][k])
        ctext(22, "PIT STOP", YEL, LCY, 2)
        ctext(44, "CHANGE %s" % getattr(c, "pit_changed", "ALL"), BLK, LCY)
        ctext(52, "%02.1fS" % max(0.0, c.st_t), BLK, LCY)

    def explosion(t):
        for _ in range(26):
            r = int(10 + t * 40)
            scr.rect(random.randrange(60, 260 - 10), random.randrange(25, 100), random.randrange(6, max(8, r)),
                     random.randrange(4, max(8, r // 2 + 4)), random.choice((YEL, LRD, WHT, RED)))

    # ---- the phase machine, called once per tick ---------------------------------------------------------
    def step():
        st["tick"] += 1
        ph = st["phase"]
        st["t"] += DT
        t = st["t"]
        if ph == "title":
            if t < DT * 1.5:
                black_screen()
                ctext(18, "GRAND PRIX CIRCUIT", YEL, BLK, 2)
                ctext(44, "ACCOLADE  DISTINCTIVE SOFTWARE 1988", LGR)
                ctext(60, "TEAM %s" % CARS[pcar_type][0], WHT)
                ctext(74, "RACES " + "  ".join(TK.NAMES[r][:3] for r in rounds), LCY)
                ctext(98, "9-6-4-3-2-1 POINTS", LGN)
                scr.flush()
            if t > 2.5:
                start_round()
            return False
        if ph == "intro":
            tr = st["tr"]
            if t < DT * 1.5:
                black_screen()
                ctext(24, "ROUND %d" % (st["race_no"] + 1), LCY, BLK, 2)
                ctext(50, "%s GRAND PRIX" % tr.name, YEL, BLK, 2)
                ctext(74, tr.info["place"], WHT)
                ctext(90, "LAP %d M  3 LAPS" % tr.L, LGR)
                ctext(106, "QUALIFYING LAP FIRST", LGN)
                scr.flush()
            if t > 2.5:
                restore_static()
                race = st["race"]
                player.reset(0.0, 0.0)
                player.state = "run"
                player.gear, player.rpm = 0, 3200
                race.t = 0.0
                for c in allcars:
                    if not c.player:
                        c.state = "dnf"
                st["phase"], st["t"] = "quali", 0.0
                draw_lamps(0)
            return False
        if ph in ("quali", "race", "finish", "lights", "grid"):
            race = st["race"]
            tr = race.tr
            if ph == "quali":
                sim_race(DT)
                sim_race(DT)          # the hot lap runs at double speed to keep the whole game short
                draw_race_frame(player, race, 0.0)
                hud_race(player, race, True)
                scr.flush()
                if player.dist >= tr.L or t > 40:
                    st["qtime"] = race.t
                    # rivals set flying-lap times; the player's standing lap includes the launch
                    times = [(st["qtime"], player)]
                    for c in rivals:
                        times.append((tr.ideal[c.ct] / (c.skill * c.pace_noise) + 1.8 + rnd.uniform(0, 0.4), c))
                    times.sort(key=lambda x: x[0])
                    st["grid"] = [c for _, c in times]
                    st["gpos"] = st["grid"].index(player) + 1
                    black_screen()
                    ctext(20, "QUALIFYING", YEL, BLK, 2)
                    ctext(50, "YOUR TIME %s" % fmt_time(st["qtime"]), WHT)
                    ctext(62, "GRID POSITION %d" % st["gpos"], LGN)
                    for i, (tm, c) in enumerate(times[:10]):
                        text(60, 80 + i * 10, "%2d %-13s %s" % (i + 1, c.name, fmt_time(tm)), YEL if c.player else LGR)
                    scr.flush()
                    st["phase"], st["t"] = "quali_res", 0.0
                return False
            if ph == "lights":
                n = min(4, int(t / 0.6) + 1) if t < 2.8 else 0
                if st.get("lamps") != n:
                    st["lamps"] = n
                    draw_lamps(n)
                if t >= 2.8 and not st.get("go"):
                    st["go"] = True
                    for c in allcars:
                        c.state = "run"
                        c.launch_t = rnd.uniform(0.05, 0.45)
                        c.hold = True
                    player.launch_t = 0.2
                    st["phase"] = "race"
                    st["t"] = 0.0
                    race.t = 0.0
                    draw_lamps(0)
                draw_race_frame(player, race, 0.0)
                hud_race(player, race, False)
                scr.flush()
                return False
            if ph == "race" or ph == "finish":
                for c in allcars:
                    if c.hold and race.t >= c.launch_t:
                        c.hold = False
                sim_race(DT)
                sp = 0.0
                if player.state == "spin":
                    sp = math.sin(st["tick"] * 0.7) * 90 * min(1.0, player.st_t)
                if st["fire"]:
                    st["fire_t"] = st.get("fire_t", 0.0) + DT
                special = player.state == "pit_stop" or (player.state == "dnf" and not st["fire"])
                if st.get("special") and not special:
                    restore_static()
                    st["tick"] -= st["tick"] % 12
                st["special"] = special
                if player.state == "pit_stop":
                    pit_scene(player, race)
                    hud_race(player, race, False)
                elif player.state == "dnf" and st.get("fire_t", 0) < 2.0 and not st["fire"]:
                    explosion(max(0.05, min(1.0, (t + 1.0) / 2)))
                    hud_race(player, race, False)
                else:
                    draw_race_frame(player, race, sp)
                    if player.state == "spin" and st["tick"] % 2:
                        scr.rect(random.randrange(100, 200), random.randrange(95, 108), random.randrange(10, 40), 3, LGR)
                    if ph == "finish" and player.fin_t is not None:
                        wob = int(st["t"] * 12) % 8
                        for q in range(8):
                            for r in range(4):
                                scr.rect(200 + q * 8 + (wob if r % 2 else 0) % 3, 62 + r * 8, 8, 8,
                                         WHT if (q + r) & 1 else BLK)
                    hud_race(player, race, False)
                scr.flush()
                if ph == "race" and (player.fin_t is not None or player.state == "dnf"):
                    st["phase"], st["t"] = "finish", 0.0
                    if player.state == "dnf":
                        st["t"] = -1.0
                elif ph == "race" and race.t > 240:
                    player.state = "dnf"
                if ph == "finish" and st["t"] > 3.2:
                    order = classification(race)
                    pos_ = order.index(player) + 1
                    rows = []
                    for i, c in enumerate(order):
                        if i < 6:
                            points[c.idx] += POINTS[i]
                        tm = fmt_time(c.fin_t) if c.fin_t is not None else ("DNF" if c.state == "dnf" else "RUNNING")
                        rows.append(("%2d %-13s %-8s %-9s %s" % (i + 1, c.name, CARS[c.ct][0] if c.player else "", tm,
                                                               ("+%d" % POINTS[i]) if i < 6 else ""),
                                     YEL if c.player else WHT))
                    table("%s RESULT" % tr.name, rows)
                    st["pos"] = pos_
                    st["score"] += (11 - pos_) * 20 + (POINTS[pos_ - 1] * 100 if pos_ <= 6 else 0)
                    st["phase"], st["t"] = "result", 0.0
                    st["fire"] = False
                return False
        if ph == "quali_res":
            if t > 3.0:
                race = st["race"]
                tr = race.tr
                build_grid(race, st["grid"])
                for c in allcars:
                    c.dmg = c.tyre = c.eng = 0.0
                    c.skill = c.skill_base
                    c.pace_noise = rnd.uniform(0.985, 1.005)
                    c.pit_req = c.pit_done = False
                    c.hold = True
                    c.fin_t = None
                    c.laps_t = []
                player.pace_noise = rnd.uniform(0.98, 1.0)
                race.t = 0.0
                restore_static()
                st["lamps"] = None
                st["go"] = False
                st["fire"] = False
                st["phase"], st["t"] = "lights", 0.0
            return False
        if ph == "result":
            if t > 4.0:
                rows = []
                order = sorted(allcars, key=lambda c: -points[c.idx])
                for i, c in enumerate(order):
                    rows.append(("%2d %-13s %3d" % (i + 1, c.name, points[c.idx]), YEL if c.player else WHT))
                table("CHAMPIONSHIP", rows, sub="AFTER ROUND %d" % (st["race_no"] + 1))
                st["phase"], st["t"] = "standings", 0.0
            return False
        if ph == "standings":
            if t > 3.5:
                st["race_no"] += 1
                if st["race_no"] >= len(rounds):
                    total = st["score"]
                    st["final"] = total
                    st["phase"], st["t"] = "final", 0.0
                    black_screen()
                    scr.flush()
                    st["end"] = EndScreen()
                    st["end"].start(total, "CHAMPIONSHIP OVER")
                else:
                    start_round()
            return False
        if ph == "final":
            return st["end"].tick()
        return False

    return step
