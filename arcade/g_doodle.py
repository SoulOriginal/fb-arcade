# Doodle Jump (Lima Sky, 2009) played by a bot on graph paper. See research_doodle.md for the sources of the rules.
# Rendering: the whole 640x1080 play area is composed in a bytearray every tick (paper strip slice + span sprites)
# and copied to the framebuffer row by row; the decorative side margins are drawn once.
from fbcore import *
import math

D = load_bundle("g_doodle.bin")

# ---- geometry: logical 320x540 units at 2 px per unit, centred on the 1920x1080 screen ------------------------------
LW, LH, UP = 320, 540, 2
PW, PH = LW * UP, LH * UP
PS = PW * 2
PX0 = (W - PW) // 2
PERIOD = 32
STRIP = memoryview(D["tile"] * (PH // PERIOD + 2))
SCREEN_STRIDE = S

# ---- physics (units per tick, 30 ticks/s); apexes follow the wiki: jump 190, spring 352, trampoline 700 -------------
G = 1.394
V0, VS, VT = 23.0, 31.3, 44.1
MAXVX = 9.0
PROP_SPEED, PROP_TICKS = 12.0, 167          # 2000 points
JET_SPEED, JET_TICKS = 26.0, 115            # 3000 points
SHIELD_TICKS = 150
CAM_LINE = 300                              # the Doodler never climbs above this height on screen
PLAT_HALF, FEET_HALF = 29, 12
TARGET_SCORE = int(os.environ.get("DOODLE_TARGET", "30000"))
MIN_TICKS, MAX_TICKS = 270 * TICK_RATE, 390 * TICK_RATE      # the game lasts 4.5 to 6.5 minutes
BULLET_SPEED = 16.0
BODYX = (45, 27)                            # x of the body centre inside the sprite for facing left / right
CARD_TICKS = 100

DIGIT_CELL = D["digits_s"][0][0]
HUD_H = 62
HUD_BYTES = HUD_H * PW * 2
HUD_MASK = int.from_bytes(b"\xef\x7b" * (HUD_H * PW), "little")
HUD_TINT = int.from_bytes((((0xB6F6 >> 1) & 0x7BEF).to_bytes(2, "little")) * (HUD_H * PW), "little")


def wrapd(a, b):
    # Signed shortest horizontal distance a -> b on a screen whose edges are glued together.
    d = (b - a) % LW
    return d - LW if d > LW / 2 else d


class Plat:
    __slots__ = ("kind", "x", "h", "vx", "base", "amp", "ph", "ext", "ext_x", "ext_t", "item", "item_x", "t", "brk", "gone", "used", "dh")

    def __init__(self, kind, x, h):
        self.kind, self.x, self.h = kind, x, h
        self.vx = self.base = self.amp = self.ph = 0.0
        self.ext = self.item = None
        self.ext_x = self.item_x = 0.0
        self.ext_t = self.t = self.brk = 0
        self.gone = self.used = False
        self.dh = 0.0


class Mon:
    __slots__ = ("kind", "x", "h", "hp", "vx", "t", "shots")

    def __init__(self, kind, x, h):
        self.kind, self.x, self.h, self.t, self.shots = kind, x, h, 0, 0
        self.hp = (2, 1, 3, 1, 99)[kind]
        self.vx = 0.0


# monster kinds: 0 green blob, 1 blue flyer, 2 purple six-armed, 3 UFO, 4 black hole
MON_BOX = ((22, 20), (26, 18), (24, 22), (30, 12), (22, 22))     # half width, half height of the hit box


def make():
    S = type("State", (), {})()
    fr = bytearray(PW * PH * 2)
    mv = memoryview(fr)
    best = [0]
    phase = ["run"]
    es = EndScreen()

    # ---- drawing primitives -------------------------------------------------------------------------------------------
    def put(sp, x, y):
        w, h, rows = sp
        if y >= PH or y + h <= 0 or x >= PW or x + w <= 0:
            return
        r0, r1 = max(0, -y), min(h, PH - y)
        if 0 <= x and x + w <= PW:
            for j in range(r0, r1):
                runs = rows[j]
                if runs:
                    base = (y + j) * PS + x * 2
                    for xo, b in runs:
                        o = base + xo * 2
                        fr[o:o + len(b)] = b
        else:
            for j in range(r0, r1):
                base = (y + j) * PS
                for xo, b in rows[j]:
                    a, e = x + xo, x + xo + len(b) // 2
                    lo, hi = max(a, 0), min(e, PW)
                    if hi > lo:
                        fr[base + lo * 2:base + hi * 2] = b[(lo - a) * 2:(hi - a) * 2]

    def put_wrapped(sp, x, y):
        put(sp, x, y)
        if x < 0:
            put(sp, x + PW, y)
        elif x + sp[0] > PW:
            put(sp, x - PW, y)

    def number(digits, text, x, y, step):
        for ch in text:
            put(digits[ord(ch) - 48], x, y)
            x += step
        return x

    def blend_half(y0, y1, x0, x1, color):
        # 50% blend of a colour over a pixel rectangle, done on big integers: RGB565 halves never carry across fields
        # once masked, so one shift/mask/add handles many pixels at a time.
        c = (color >> 1) & 0x7BEF
        n = x1 - x0
        cm = int.from_bytes((c.to_bytes(2, "little")) * n, "little")
        mask = int.from_bytes(b"\xef\x7b" * n, "little")
        for y in range(max(0, y0), min(PH, y1)):
            o = y * PS + x0 * 2
            v = int.from_bytes(fr[o:o + n * 2], "little")
            fr[o:o + n * 2] = (((v >> 1) & mask) + cm).to_bytes(n * 2, "little")

    def show():
        for y in range(PH):
            o = y * SCREEN_STRIDE + PX0 * 2
            fb[o:o + PS] = mv[y * PS:(y + 1) * PS]

    def sy(h):
        return LH - (h - S.cam)

    # ---- world ---------------------------------------------------------------------------------------------------------
    def dif(h):
        return min(1.0, h / 22000.0)

    def pick_kind(h):
        # Platform mix by height: green fades out, the other types phase in at the heights the wiki implies
        # (broken near the start, moving early, white / yellow / vertical later).
        d = dif(h)
        w = [("green", 100 - 62 * d)]
        if h > 700:
            w.append(("blue", 4 + 16 * d))
        if h > 3000:
            w.append(("white", 3 + 8 * d))
        if h > 4500:
            w.append(("gray", 3 + 7 * d))
        if h > 6500:
            w.append(("yellow", 2 + 6 * d))
        tot = sum(v for _, v in w)
        r = random.random() * tot
        for k, v in w:
            r -= v
            if r <= 0:
                return k
        return "green"

    def new_plat(h, kind=None, x=None):
        kind = kind or pick_kind(h)
        d = dif(h)
        if kind != "brown":
            for m in S.mons:
                if m.kind == 4 and abs(m.h - h) < 80 and abs(wrapd(m.x, x)) < 80:
                    x = (m.x + (140 if m.x < LW / 2 else -140) + random.uniform(-25, 25)) % LW
                    x = min(max(x, PLAT_HALF + 2), LW - PLAT_HALF - 2)
        p = Plat(kind, x, h)
        if kind == "blue":
            p.vx = random.choice((-1, 1)) * (1.0 + 2.4 * d + random.random() * 0.6)
        elif kind == "gray":
            p.base, p.amp, p.ph = h, random.uniform(24, 40), random.uniform(0, 6.28)
            p.vx = 0.05 + 0.04 * d
        elif kind == "green":
            r = random.random()
            if h > 250 and r < 0.07:
                p.ext, p.ext_x = "spring", random.uniform(-18, 18)
            elif h > 900 and r < 0.088:
                p.ext, p.ext_x = "tramp", random.uniform(-8, 8)
            elif h > 1500 and r < 0.093:
                p.item, p.item_x = "prop", random.uniform(-14, 14)
            elif h > 4500 and r < 0.0955:
                p.item, p.item_x = "jet", random.uniform(-14, 14)
        S.plats.append(p)
        return p

    def new_mon(h):
        d = dif(h)
        r = random.random()
        if h > 9000 and r < 0.14:
            kind = 4
        elif h > 7000 and r < 0.3:
            kind = 3
        elif h > 4500 and r < 0.55:
            kind = 2
        elif h > 2500 and r < 0.6:
            kind = 1
        else:
            kind = 0
        x = random.uniform(40, LW - 40)
        m = Mon(kind, x, h)
        if kind == 1:
            m.vx = random.choice((-1, 1)) * 0.9
        elif kind == 3:
            m.vx = random.choice((-1, 1)) * 0.7
        S.mons.append(m)
        # a shield lies on the nearest platform below the monster, as in the original
        if kind != 4 and random.random() < 0.4:
            below = [p for p in S.plats if p.h < h and p.kind == "green" and not p.item and not p.ext]
            if below:
                p = max(below, key=lambda q: q.h)
                p.item, p.item_x = "shield", random.uniform(-14, 14)

    def generate(top):
        while S.gen_h < top:
            d = dif(S.gen_h)
            gap = random.uniform(26 + 34 * d, 60 + 80 * d)
            S.gen_h += gap
            h = S.gen_h
            if h > 350 and random.random() < 0.06 + 0.2 * d:
                dh = h - gap * random.uniform(0.35, 0.65)
                for _ in range(8):
                    x = random.uniform(PLAT_HALF + 2, LW - PLAT_HALF - 2)
                    if all(abs(p.h - dh) > 30 or abs(p.x - x) > 70 for p in S.plats[-4:]):
                        new_plat(dh, "brown", x)
                        break
            # the next platform stays within what the Doodler can travel sideways during a jump of this height
            reach = max(50.0, 150.0 - 0.6 * gap)
            S.prev_x = min(max(S.prev_x + random.uniform(-reach, reach), PLAT_HALF + 2), LW - PLAT_HALF - 2)
            new_plat(h, None, S.prev_x)
            if h > S.next_mon:
                new_mon(h + gap * 0.5)
                S.next_mon = h + random.uniform(700, 1500) * (1 - 0.5 * d)

    def reset_run():
        S.plats, S.mons, S.bullets, S.fx = [], [], [], []
        S.cam = 0.0
        S.gen_h = 0.0
        S.prev_x = LW / 2
        S.next_mon = 1700.0
        p = Plat("green", LW / 2, 0)
        S.plats.append(p)
        S.x, S.h, S.vy, S.vx = LW / 2, 0.0, V0, 0.0
        S.face = 1
        S.maxh = 0.0
        S.fly_kind = None
        S.fly = S.shield_t = S.squash = S.flip_t = S.shoot_t = S.cool = 0
        S.state = "play"
        S.dead_t = 0
        S.stall = 0
        S.target = None
        S.aim_off = 0.0
        S.tick = 0
        S.hit_by = None
        generate(LH + 300)

    # ---- bot -----------------------------------------------------------------------------------------------------------
    def landing_time(h_now, vy, h_to):
        # Ticks until the feet fall to h_to on the way down (continuous approximation of the integrator).
        up = max(0.0, vy / G)
        apex = h_now + (vy * vy / (2 * G) if vy > 0 else 0.0)
        if apex < h_to:
            return None
        return up + math.sqrt(2 * (apex - h_to) / G)

    def safe(p):
        if p.kind == "brown" or p.gone:
            return False
        if p.kind == "yellow" and p.t >= 45:
            return False
        return True

    def predict_x(p, t):
        if p.kind != "blue":
            return p.x
        x = p.x + p.vx * t
        lo, hi = PLAT_HALF, LW - PLAT_HALF
        span = hi - lo
        x = (x - lo) % (2 * span)
        return lo + (x if x <= span else 2 * span - x)

    def new_aim():
        # Aiming error is redrawn on every bounce, not on every re-plan: a human misjudges a jump, not each frame.
        d = dif(S.h)
        S.aim_off = random.uniform(-1, 1) * (4 + 14 * d)
        if random.random() < 0.006 + 0.012 * d:
            S.aim_off = random.choice((-1, 1)) * random.uniform(40, 54)

    def bot():
        dx_in, shoot = 0.0, None
        flying = S.fly > 0
        visible = [m for m in S.mons if S.cam - 40 < m.h < S.cam + LH + 20]
        # --- shooting
        if not flying and S.cool == 0:
            for m in visible:
                if m.kind == 4 or m.h < S.h + 25 or m.shots > 6:
                    continue
                if m.h > S.cam + LH - 30:
                    continue
                lead = m.vx * 10
                shoot = (m.x + lead, m.h + 4)
                break
        # --- target choice
        best, best_s = None, -1e9
        for p in S.plats:
            if not safe(p):
                continue
            t = landing_time(S.h, S.vy, p.h + 2)
            if t is None or p.h < S.h - 260:
                continue
            px = predict_x(p, t)
            dx = wrapd(S.x, px)
            ratio = (abs(dx) - 18) / (MAXVX * max(t, 1))
            if ratio > 1.0:
                continue
            sc = p.h - 0.6 * abs(dx) - 220 * max(0.0, ratio - 0.5)
            if p.ext == "spring":
                sc += 70
            elif p.ext == "tramp":
                sc += 190
            if p.item in ("prop", "jet"):
                sc += 300 if p.item == "jet" else 240
            elif p.item == "shield" and visible:
                sc += 120
            if p.kind in ("white", "yellow"):
                sc -= 25
            if p.kind == "blue":
                sc -= 10
            for m in S.mons:
                if m.kind != 4 and S.shield_t == 0 and 0 < p.h - m.h + 60 and abs(m.h - p.h) < 70 and abs(wrapd(m.x, px)) < 55:
                    sc -= 220
                if m.kind == 4 and abs(m.h - p.h) < 90 and abs(wrapd(m.x, px)) < 60:
                    sc -= 400
            if sc > best_s:
                best, best_s = p, sc
        # stomping a monster below is as good as a platform
        stomp = None
        if S.vy < 0 and not flying:
            for m in visible:
                if m.kind in (0, 1, 2) and 0 < S.h - m.h < 140 and abs(wrapd(S.x, m.x)) < 60:
                    stomp = m
        tx = None
        if stomp is not None:
            tx = stomp.x + stomp.vx * 4
            S.target = None
        elif best is not None:
            S.target = best
            t = landing_time(S.h, S.vy, best.h + 2) or 1
            tx = predict_x(best, t) + S.aim_off
        else:
            tx = LW / 2
        err = wrapd(S.x, tx)
        dx_in = max(-1.0, min(1.0, (err - S.vx * 2.4) / 16.0))
        # --- avoidance of what kills: monsters (unless shielded or flying through them), UFO beams, black holes
        for m in visible:
            if m.kind != 4 and (S.shield_t > 0 or flying):
                continue
            dh = m.h - S.h
            reach = 70 + 6 * max(S.vy, 0)
            if m.kind == 3:
                beam_top, beam_bot = m.h, m.h - 160
                if not (beam_bot - 30 < S.h + S.vy * 4 < beam_top + 60):
                    continue
                halfw = 52
            elif -40 < dh < reach:
                halfw = 62 if m.kind == 4 else 50
            else:
                continue
            mx = m.x
            side = wrapd(mx, S.x)
            if abs(side) < halfw:
                # kill-able monsters in front of the nose are shot first; everything else is steered around
                dx_in = (1.0 if side >= 0 else -1.0) * (0.6 + 0.4 * (1 - abs(side) / halfw)) + 0.4 * dx_in
        return max(-1.0, min(1.0, dx_in)), shoot

    # ---- simulation ----------------------------------------------------------------------------------------------------
    def kill_player(why, mon=None):
        S.state = "dead"
        S.dead_t = 0
        S.hit_by = (why, mon)
        S.fly = S.shield_t = 0
        S.vy = 8.0 if why == "monster" else 0.0

    def collect(p):
        if p.item == "prop":
            S.fly, S.fly_kind = PROP_TICKS, "prop"
        elif p.item == "jet":
            S.fly, S.fly_kind = JET_TICKS, "jet"
        elif p.item == "shield":
            S.shield_t = SHIELD_TICKS
        p.item = None

    def sim(dirx, shoot):
        S.tick += 1
        # horizontal control with the inertia of tilt steering; wrap-around at the screen edges
        S.vx += (dirx * MAXVX - S.vx) * 0.4
        S.x = (S.x + S.vx) % LW
        if S.vx > 0.8:
            S.face = 1
        elif S.vx < -0.8:
            S.face = 0
        prev_h = S.h
        if S.fly > 0:
            S.vy = PROP_SPEED if S.fly_kind == "prop" else JET_SPEED
            S.fly -= 1
            if S.fly == 0:
                S.vy = 8.0
        else:
            S.vy -= G
        S.h += S.vy
        if S.squash:
            S.squash -= 1
        if S.flip_t:
            S.flip_t -= 1
        if S.shoot_t:
            S.shoot_t -= 1
        if S.cool:
            S.cool -= 1
        if S.shield_t:
            S.shield_t -= 1
        if shoot and S.cool == 0 and S.fly == 0:
            ax, ah = shoot
            nose_h = S.h + 42
            dxs = wrapd(S.x, ax)
            dhs = ah - nose_h
            n = math.hypot(dxs, dhs) or 1.0
            S.bullets.append([S.x + dxs / n * 14, nose_h + dhs / n * 14, dxs / n * BULLET_SPEED, dhs / n * BULLET_SPEED])
            S.cool, S.shoot_t = 9, 7
            S.face = 1 if dxs >= 0 else 0
        # platforms: motion, timers, landing
        for p in S.plats:
            if p.kind == "blue":
                p.x += p.vx
                if p.x < PLAT_HALF or p.x > LW - PLAT_HALF:
                    p.vx = -p.vx
                    p.x = min(max(p.x, PLAT_HALF), LW - PLAT_HALF)
            elif p.kind == "gray":
                p.ph += p.vx * 2
                nh = p.base + p.amp * math.sin(p.ph)
                p.dh, p.h = nh - p.h, nh
            elif p.kind == "yellow" and p.h < S.cam + LH:
                p.t += 1
                if p.t == 75:
                    p.gone = True
                    S.fx.append(["boom", p.x, p.h + 6, 0])
            if p.brk and p.brk < 20:
                p.brk += 1
            if p.ext_t:
                p.ext_t -= 1
            if p.item and S.fly == 0 and abs(wrapd(S.x, p.x + p.item_x)) < 22 and p.h - 8 < S.h + 42 and p.h + 28 > S.h:
                collect(p)
        if S.vy < 0 and S.fly == 0:
            for p in S.plats:
                if p.gone or p.used or p.brk:
                    continue
                if prev_h >= p.h - p.dh - 1 and S.h <= p.h + 1 and abs(wrapd(S.x, p.x)) < PLAT_HALF + FEET_HALF:
                    if p.kind == "brown":
                        p.brk = 1
                        continue
                    v = V0
                    if p.ext == "spring" and abs(wrapd(S.x, p.x + p.ext_x)) < 16:
                        v, p.ext_t = VS, 8
                    elif p.ext == "tramp" and abs(wrapd(S.x, p.x + p.ext_x)) < 22:
                        v, p.ext_t, S.flip_t = VT, 8, 18
                    S.vy, S.h, S.squash = v, p.h, 3
                    new_aim()
                    if p.kind == "white":
                        p.used = True
                        S.fx.append(["puff", p.x, p.h + 6, 0])
                    break
        # monsters
        for m in S.mons:
            m.t += 1
            if m.kind == 1:
                m.x += m.vx
                m.h += math.sin(m.t * 0.12) * 0.8
                if m.x < 30 or m.x > LW - 30:
                    m.vx = -m.vx
            elif m.kind == 3:
                m.x += m.vx
                if m.x < 40 or m.x > LW - 40:
                    m.vx = -m.vx
            hw, hh = MON_BOX[m.kind]
            if m.hp <= 0:
                continue
            touching = abs(wrapd(S.x, m.x)) < hw + 12 and m.h - hh - 4 < S.h + 42 and m.h + hh > S.h + 4
            if touching:
                if m.kind == 4:
                    kill_player("hole", m)
                    return
                if S.vy < 0 and prev_h >= m.h + hh - 10 and S.fly == 0:
                    S.vy, S.h, S.squash = V0, m.h + hh, 3
                elif S.fly > 0 or (S.shield_t > 0 and m.kind != 3):
                    pass
                else:
                    kill_player("ufo" if m.kind == 3 else "monster", m)
                    return
                m.hp = 0
                S.fx.append(["puff", m.x, m.h, 0])
            elif m.kind == 3 and S.fly == 0 and abs(wrapd(S.x, m.x)) < 22 and m.h - 160 < S.h < m.h - 10:
                kill_player("ufo", m)
                return
        S.mons = [m for m in S.mons if m.hp > 0 and m.h > S.cam - 80]
        # bullets
        keep = []
        for b in S.bullets:
            b[0] += b[2]
            b[1] += b[3]
            hit = False
            for m in S.mons:
                if m.kind == 4 or m.hp <= 0:
                    continue
                hw, hh = MON_BOX[m.kind]
                if abs(wrapd(b[0], m.x)) < hw + 3 and abs(b[1] - m.h) < hh + 3:
                    m.hp -= 1
                    m.shots += 1
                    hit = True
                    if m.hp <= 0:
                        S.fx.append(["puff", m.x, m.h, 0])
                    break
            if not hit and -10 < b[0] < LW + 10 and S.cam - 20 < b[1] < S.cam + LH + 20:
                keep.append(b)
        S.bullets = keep
        # camera and score
        if S.h - S.cam > CAM_LINE:
            S.cam = S.h - CAM_LINE
        if S.h > S.maxh:
            S.maxh = S.h
            S.stall = 0
        else:
            S.stall += 1
        S.plats = [p for p in S.plats if p.h > S.cam - 70 and not (p.gone) and not (p.used and p.h < S.h - 60) and p.brk < 20]
        generate(S.cam + LH + 200)
        for f in S.fx:
            f[3] += 1
        S.fx = [f for f in S.fx if f[3] < 9]
        if S.h < S.cam - 20:
            kill_player("fall")
        elif S.stall > 600:
            kill_player("fall")

    def sim_dead():
        S.dead_t += 1
        why, m = S.hit_by
        if why in ("ufo", "hole"):
            S.x += wrapd(S.x, m.x) * 0.18
            S.h += (m.h - (20 if why == "hole" else -10) - S.h) * 0.18
            return S.dead_t > 42
        S.vy -= G
        S.h += S.vy
        S.x = (S.x + S.vx * 0.3) % LW
        for f in S.fx:
            f[3] += 1
        S.fx = [f for f in S.fx if f[3] < 9]
        return S.h < S.cam - 70 and S.dead_t > 12

    # ---- rendering -----------------------------------------------------------------------------------------------------
    def draw_world():
        off = int(S.cam * UP) % PERIOD
        start = (PERIOD - off) % PERIOD * PS
        fr[:] = STRIP[start:start + PH * PS]
        cam = S.cam
        # high-score ledge: a pencil line at the best height reached so far
        if best[0] > 0 and cam - 20 < best[0] < cam + LH + 20:
            y = int((LH - (best[0] - cam)) * UP)
            if 0 <= y < PH - 2:
                for x in range(0, PW, 28):
                    for yy in (y, y + 1):
                        o = yy * PS + x * 2
                        fr[o:o + 32] = b"\x8b\x4a" * 16
                put(D["t_hs"], 8, y - D["t_hs"][1] - 2)
        for p in S.plats:
            y = int(sy(p.h) * UP)
            if y < -80 or y > PH + 80:
                continue
            xl = int((p.x - 31) * UP)
            if p.kind == "brown":
                put(D["plat"]["brown"][min(p.brk, 3) if p.brk else 0], xl, y - 6)
            elif p.kind == "yellow":
                put(D["plat"]["red" if p.t >= 45 else "yellow"][(p.t // 3) % 2 if p.t >= 45 else 0], xl, y - 6)
            else:
                put(D["plat"][p.kind][0], xl, y - 6)
            if p.ext == "spring":
                sp = D["spring"][1 if p.ext_t else 0]
                put(sp, int((p.x + p.ext_x - 8) * UP), y - sp[1] + 2)
            elif p.ext == "tramp":
                sp = D["tramp"][1 if p.ext_t else 0]
                put(sp, int((p.x + p.ext_x - 19) * UP), y - sp[1] + 2)
            elif p.item:
                sp = D[{"prop": "i_prop", "jet": "i_jet", "shield": "i_shield"}[p.item]]
                put(sp, int((p.x + p.item_x) * UP - sp[0] // 2), y - sp[1] + 2)
        for m in S.mons:
            y = int(sy(m.h) * UP)
            if y < -120 or y > PH + 120:
                continue
            if m.kind == 3:
                # tractor beam: a half-transparent trapezoid under the saucer
                top = y + 24
                for k in range(0, 150, 2):
                    wdt = int((22 + k * 0.12) * UP)
                    blend_half(top + k * UP, top + k * UP + 2, int(m.x * UP) - wdt, int(m.x * UP) + wdt, 0xFFE0)
                sp = D["ufo"][(m.t // 6) % 2]
            elif m.kind == 4:
                sp = D["hole"][(m.t // 4) % 4]
            else:
                sp = D["mon"][m.kind][(m.t // 7) % 2]
            put(sp, int(m.x * UP) - sp[0] // 2, y - sp[1] // 2)
        for f in S.fx:
            sp = D[f[0]][min(2, f[3] // 3)]
            put(sp, int(f[1] * UP) - sp[0] // 2, int(sy(f[2]) * UP) - sp[1] // 2)
        for b in S.bullets:
            sp = D["bullet"]
            put(sp, int(b[0] * UP) - 9, int(sy(b[1]) * UP) - 9)
        draw_doodler()

    def draw_doodler():
        x, y = int(S.x * UP), int(sy(S.h) * UP)
        face = S.face
        if S.state == "dead":
            why, m = S.hit_by
            if why in ("ufo", "hole"):
                lvl = min(2, S.dead_t // 10)
                sp = D["suck"][lvl][(S.dead_t * 2) % 12]
                put_wrapped(sp, x - sp[0] // 2, y - 56 - sp[1] // 2)
            else:
                sp = D["spin"][face][(S.dead_t * 2) % 12]
                put_wrapped(sp, x - 104, y - 56 - 104)
                if why == "monster" and S.dead_t < 26:
                    st = D["stars"][(S.dead_t // 3) % 2]
                    put(st, x - st[0] // 2, y - 150)
            return
        if S.flip_t:
            sp = D["spin"][face][(18 - S.flip_t) * 12 // 18 % 12]
            put_wrapped(sp, x - 104, y - 56 - 104)
        elif S.fly > 0 and S.fly_kind == "prop":
            sp = D["hat"][face][S.tick % 2]
            put_wrapped(sp, x - BODYX[face] * UP, y - 80 * UP)
        elif S.fly > 0:
            sp = D["pack"][face][S.tick % 2]
            put_wrapped(sp, x - BODYX[face] * UP, y - 80 * UP)
        else:
            if S.squash:
                pose = 0
            elif S.vy > 3:
                pose = 2
            else:
                pose = 1
            if S.shoot_t:
                pose += 3
            sp = D["dj"][face][pose]
            put_wrapped(sp, x - BODYX[face] * UP, y - 80 * UP)
        if S.shield_t > 0 and (S.shield_t > 40 or S.tick % 4 < 2):
            sh = D["shield"][S.tick // 3 % 2]
            put_wrapped(sh, x - 64, y - 56 - 64)

    def draw_hud():
        # the bar rows are contiguous in the frame, so the whole translucent bar is one big-integer operation
        v = int.from_bytes(fr[:HUD_BYTES], "little")
        fr[:HUD_BYTES] = (((v >> 1) & HUD_MASK) + HUD_TINT).to_bytes(HUD_BYTES, "little")
        fr[HUD_H * PS:HUD_H * PS + PS] = b"\x8b\x4a" * PW
        number(D["digits_s"], str(int(S.maxh)), 14, 9, DIGIT_CELL - 2)
        put(D["pause"], PW - 52, 12)

    def draw_card():
        fr[:] = STRIP[:PH * PS]
        put(D["t_gameover"], (PW - D["t_gameover"][0]) // 2, 130)
        put(D["t_score"], 40, 330)
        number(D["digits_l"], str(int(S.maxh)), 40 + D["t_score"][0] + 16, 322, D["digits_l"][0][0] - 2)
        put(D["t_high"], 40, 440)
        number(D["digits_l"], str(int(best[0])), 40 + D["t_high"][0] + 12, 432, D["digits_l"][0][0] - 2)
        put(D["b_again"], (PW - D["b_again"][0]) // 2, 640)
        put(D["plat"]["green"][0], 150, 960)
        put(D["dj"][1][0], 150 + 30, 960 - 160 + 18)
        st = D["stars"][0]
        put(st, 164, 850)
        show()

    # ---- main ----------------------------------------------------------------------------------------------------------
    for name, x0 in (("margin_l", 0), ("margin_r", PX0 + PW)):
        m = D[name]
        for y in range(H):
            fb[y * SCREEN_STRIDE + x0 * 2:y * SCREEN_STRIDE + (x0 + PX0) * 2] = m[y * PX0 * 2:(y + 1) * PX0 * 2]
    S.ticks_total = 0
    # Each game ends at a random moment inside the 4.5-6.5 minute window (or at the target score): the bot then
    # simply "slips" off its platform, which looks like any other death and leads to the game-over card.
    S.deadline = random.randint(MIN_TICKS, min(MAX_TICKS, CAP_TICKS - 2 * CARD_TICKS - 120))
    S.finishing = False
    reset_run()

    def to_card():
        best[0] = max(best[0], int(S.maxh))
        phase[0] = "card"
        S.dead_t = 0
        draw_card()

    def step():
        S.ticks_total += 1
        if phase[0] == "final":
            return es.tick()
        if phase[0] == "card":
            S.dead_t += 1
            if S.dead_t >= CARD_TICKS:
                if S.finishing:
                    es.start(int(best[0]))
                    phase[0] = "final"
                else:
                    reset_run()
                    phase[0] = "run"
            return False
        if S.state == "play":
            if not S.finishing and (S.ticks_total >= S.deadline or S.maxh >= TARGET_SCORE):
                S.finishing = True
                kill_player("fall")
            else:
                sim(*bot())
        elif sim_dead():
            to_card()
            return False
        draw_world()
        draw_hud()
        show()
        return False

    return step
