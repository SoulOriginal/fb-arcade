# Battletoads, level 1 "Ragnarok's Canyon": two toads (one green, one blue) played by a belt-scroller combat bot
# against Psyko Pigs, Ratkins, Mutant Ravens, Walkers and the boss Big Blag; the canyon then loops with a new palette.
# Rendering: parallax background strips are sliced per scanline band, depth-sorted run-length sprites are overlaid in
# a row buffer, and each virtual row (2x2 screen pixels) is written twice.
from fbcore import *
import math

B = load_bundle("g_battletoads.bin")
SPR, FX, LAB, HUDS, POP, ARROW, BG, SHADOW = B["spr"], B["fx"], B["lab"], B["hud"], B["pop"], B["arrow"], B["bg"], B["shadow"]
BANDS = B["meta"]["bands"]
VW, VH = 960, 540
PAD = 300
PADB = PAD * 4
ROWB = VW * 4
LY0, LY1 = 392, 516          # lane limits (feet y)
GRAV = 0.55
TARGET_SCORE = 72000
LOOP_FRAMES = ("idle", "walk", "dazed", "charge", "fly")


# ---- renderer ----------------------------------------------------------------------------------------------
class Renderer:
    def __init__(self):
        self.buf = bytearray(PADB * 2 + ROWB)
        self.mv = memoryview(self.buf)
        self.mvrows = [[[memoryview(r) for r in band] for band in pal] for pal in BG]
        self.prev_off = [None] * len(BANDS)
        self.prev_rows = set()
        self.pal = 0
        self.force = True

    def fill(self, c565):
        row = c565.to_bytes(2, "little") * W
        for y in range(H):
            fb[y * S:(y + 1) * S] = row
        self.force = True

    def render(self, cam, items):
        buf, mv = self.buf, self.mv
        lists = {}
        for fr, vx, vy in items:
            top, left, rows = fr
            x = vx + left
            if x >= VW or x < -240:
                continue
            xb = PADB + x * 4
            y = vy + top
            for runs in rows:
                if 0 <= y < VH and runs:
                    if y in lists:
                        lists[y].append((xb, runs))
                    else:
                        lists[y] = [(xb, runs)]
                y += 1
        touched = self.prev_rows | lists.keys()
        self.prev_rows = set(lists)
        pal_rows = self.mvrows[self.pal]
        force = self.force
        self.force = False
        for bi, (y0, y1, spd, P) in enumerate(BANDS):
            off = int(cam * spd) % P
            full = force or off != self.prev_off[bi]
            self.prev_off[bi] = off
            xo = off * 4
            rows = pal_rows[bi]
            ys = range(y0, y1) if full else [y for y in touched if y0 <= y < y1]
            for y in ys:
                src = rows[y - y0][xo:xo + ROWB]
                lst = lists.get(y)
                if lst:
                    buf[PADB:PADB + ROWB] = src
                    for xb, runs in lst:
                        for xr, b in runs:
                            a = xb + xr
                            buf[a:a + len(b)] = b
                    src = mv[PADB:PADB + ROWB]
                o = y * 2 * S
                fb[o:o + S] = src
                fb[o + S:o + 2 * S] = src


# ---- entities ----------------------------------------------------------------------------------------------
HALFW = {"toad": 14, "pig": 15, "rat": 11, "walker": 24, "raven": 14, "boss": 46}


class Ent:
    def __init__(self, kind, spr, x, y):
        self.kind, self.spr = kind, spr
        self.x, self.y, self.z = x, y, 0.0
        self.vx = self.vy = self.vz = 0.0
        self.face = 1
        self.st, self.t = "move", 0
        self.anim, self.af = "idle", 0.0
        self.hp = self.maxhp = 1
        self.inv = 0
        self.cd = 0
        self.hitset = set()
        self.reach = 40
        self.poise = 0
        self.flash = 0
        self.hw = HALFW.get(kind, 14)
        self.bounced = False
        self.src = None


def setanim(e, name):
    if e.anim != name:
        e.anim, e.af = name, 0.0


def frame_of(e):
    anims = SPR[e.spr]
    frames = anims.get(e.anim) or anims["fly"]
    n = len(frames)
    i = int(e.af)
    i = i % n if e.anim in LOOP_FRAMES else min(i, n - 1)
    return frames[i][0 if e.face > 0 else 1]


def sgn(v):
    return 1 if v >= 0 else -1


def clamp(v, a, b):
    return a if v < a else b if v > b else v


class Game:
    def __init__(self):
        self.r = Renderer()
        self.cam = 0.0
        self.tick = 0
        self.freeze = 0
        self.shake = 0
        self.enemies, self.items, self.fx, self.pops = [], [], [], []
        self.canyon = 0
        self.phase = "intro"
        self.pt = 0
        self.world_base = 0.0
        self.sec = 0
        self.locks = []
        self.lock_x = None
        self.queue = []
        self.wave_t = 0
        self.arrow_on = False
        self.boss = None
        self.oneup_drop = False
        self.over = False
        self.end = EndScreen()
        self.end_started = False
        self.toads = [self.make_toad(0, 180, 450), self.make_toad(1, 110, 420)]
        self.setup_canyon()

    # ---- construction ---------------------------------------------------------------------------------------
    def make_toad(self, idx, x, y):
        t = Ent("toad", "toad%d" % idx, x, y)
        t.idx = idx
        t.hp = t.maxhp = 8
        t.lives = 3
        t.score = 0
        t.combo = 0
        t.combo_win = 0
        t.connected = False
        t.atk = None
        t.prop = None
        t.uses = 0
        t.react = 0
        t.dodge = 0
        t.dodge_dir = 0
        t.flee = 0
        t.swing_t = 0
        t.held = None
        t.alive = True
        t.respawn = 0
        t.goal = None
        t.wander = random.random() * 6
        t.dying = False
        t.kick = False
        t.tgt = None
        return t

    def setup_canyon(self):
        c = self.canyon
        self.r.pal = c % 2
        self.pigspr = "pig%d" % (c % 2)
        gaps = [150, 560, 580, 600, 620, 640]
        self.locks = []
        x = self.world_base
        for g in gaps:
            x += g
            self.locks.append(x)
        self.sec = 0
        self.lock_x = None
        self.phase = "walk"
        self.title_t = 120 if c == 0 else 90

    def wave_spec(self, i):
        c = self.canyon
        base = [
            [("pig", "r", 0), ("pig", "l", 25), ("pig", "r", 80)],
            [("pig", "r", 0), ("pig", "l", 15), ("raven", "r", 120), ("raven", "l", 200)],
            [("walker", "r", 0), ("pig", "l", 70), ("pig", "r", 140)],
            [("rat", "l", 0), ("rat", "r", 15), ("rat", "l", 45), ("raven", "r", 90), ("raven", "l", 170), ("pig", "r", 230)],
            [("walker", "r", 0), ("pig", "l", 60), ("pig", "r", 110), ("walker", "l", 240)],
            [("boss", "r", 0)],
        ][i]
        spec = list(base)
        if i < 5 and c >= 1:
            spec += [("pig", "r", 300 + 40 * c), ("raven", "l", 260)]
            if i in (2, 4):
                spec.append(("rat", "l", 330))
        if i < 5 and c >= 2:
            spec += [("pig", "l", 360), ("rat", "r", 380)]
        return spec

    # ---- effects ---------------------------------------------------------------------------------------------
    def add_fx(self, name, x, y, rate=0.5, anchor_up=0):
        self.fx.append([x, y - anchor_up, FX[name], 0.0, rate])

    def popup(self, x, y, pts):
        key = min(POP, key=lambda k: abs(k - pts))
        self.pops.append([x + random.randint(-14, 14), y - 90 - random.randint(0, 16), 0, POP[key][0]])

    def award(self, t, pts, x, y, show=True):
        if t is None:
            return
        t.score += pts
        if show and pts >= 200:
            self.popup(x, y, pts)

    # ---- spawning --------------------------------------------------------------------------------------------
    def spawn(self, kind, side):
        c = self.canyon
        x = self.cam + (VW + 60 if side == "r" else -60)
        y = random.randint(LY0 + 8, LY1 - 8)
        if kind == "pig":
            e = Ent("pig", self.pigspr, x, y)
            e.hp = e.maxhp = 5 + (c >= 2)
            e.speed = 1.45 + 0.18 * min(c, 3)
            e.reach = 44
            e.dmg = 1
        elif kind == "rat":
            e = Ent("rat", "rat", x, y)
            e.hp = e.maxhp = 3
            e.speed = 2.7 + 0.2 * min(c, 3)
            e.reach = 34
            e.dmg = 1
        elif kind == "walker":
            e = Ent("walker", "walker", x, y)
            e.hp = e.maxhp = 10 + 2 * c
            e.speed = 0.95
            e.reach = 66
            e.dmg = 2
            e.poise = 3
        elif kind == "raven":
            e = Ent("raven", "raven", x, y)
            e.hp = e.maxhp = 2
            e.z = 90
            e.speed = 2.6 + 0.2 * min(c, 3)
            e.reach = 30
            e.dmg = 1
            e.anim = "fly"
        else:
            e = Ent("boss", "boss", x, 460)
            e.hp = e.maxhp = 42 + 16 * c
            e.speed = 1.2 + 0.15 * min(c, 3)
            e.reach = 118
            e.dmg = 2
            e.poise = 6
            e.enraged = False
            e.summoned = False
            self.boss = e
        e.face = -1 if side == "r" else 1
        self.enemies.append(e)
        return e

    def spawn_item(self, kind, x, y):
        it = Ent("item", kind, x, y)
        it.z = 150 if kind == "oneup" else 0
        it.t = 0
        self.items.append(it)

    # ---- combat ------------------------------------------------------------------------------------------------
    def targets(self):
        return [e for e in self.enemies if e.hp > 0 and e.st not in ("held", "lie", "dying", "launched", "getup")]

    def in_reach(self, a, e, reach, zr=52):
        dx = (e.x - a.x) * a.face
        return -12 <= dx <= reach + e.hw and abs(e.y - a.y) <= 15 and a.z - 44 <= e.z <= a.z + zr

    def damage_enemy(self, e, dmg, kind, src, pts):
        # kind: light (stun), launch (knock away), swing (launch with smaller speed)
        e.hp -= dmg
        e.flash = 4
        face = src.face if src is not None else 1
        self.award(src, pts, e.x, e.y - e.z)
        self.add_fx("spark" if kind == "light" else "pow", e.x + face * -4, e.y - e.z - (46 if e.kind != "raven" else 8), 0.55 if kind == "light" else 0.5)
        if kind != "light":
            self.freeze = max(self.freeze, 3)
            self.shake = 7
        e.src = src
        if e.hp <= 0:
            self.kill(e, face, kind)
            return
        big = e.kind in ("walker", "boss")
        if kind == "light":
            if big:
                e.poise -= 1
                e.vx = face * 0.8
                if e.poise > 0:
                    return
                e.poise = 3 if e.kind == "walker" else 6
            setanim(e, "hurt")
            e.st, e.t = "hurt", 0
            e.vx = face * 2.8
            e.cd = max(e.cd, 24)
            if e.kind == "raven":
                e.vz = 0
        else:
            if e.kind == "boss":
                setanim(e, "hurt")
                e.st, e.t = "hurt", 0
                e.vx = face * 3.5
                e.cd = 20
            else:
                self.launch(e, face, 5 if big else 9.5, 5 if big else 6.5)

    def launch(self, e, face, vx, vz):
        e.st, e.t = "launched", 0
        setanim(e, "fall")
        e.vx, e.vz = face * vx, vz
        e.face = -face
        e.bounced = False
        e.hitset = set()

    def kill(self, e, face, kind):
        pts = {"pig": 500, "rat": 500, "raven": 1000, "walker": 2000, "boss": 10000}[e.kind]
        src = e.src
        self.award(src, pts, e.x, e.y - e.z)
        if e.kind in ("boss", "walker") and kind == "light":
            e.st, e.t = "dying", 0
            setanim(e, "hurt")
            return
        if e.kind == "boss":
            e.st, e.t = "dying", 0
            setanim(e, "hurt")
            return
        self.launch(e, face, 15, 7)

    def drop_loot(self, e):
        r = random.random()
        if e.kind == "walker":
            self.items.append(self.make_leg(e.x))
        if (e.kind == "walker" and r < 0.5) or (e.kind in ("pig", "rat") and r < 0.14):
            self.spawn_item("fly", clamp(e.x, self.cam + 50, self.cam + VW - 50), clamp(e.y, LY0, LY1))

    def make_leg(self, x):
        it = Ent("item", "legitem", clamp(x, self.cam + 60, self.cam + VW - 60), 470)
        it.t = 0
        return it

    def hurt_toad(self, t, dmg, face, heavy):
        if t.inv > 0 or t.st in ("down", "lie", "getup", "dead") or not t.alive:
            return False
        if t.st == "hold":
            self.drop_held(t, False)
        t.hp -= dmg
        t.inv = 48
        t.atk = None
        t.combo = 0
        t.dodge = 0
        t.flash = 3
        self.add_fx("spark", t.x + face * 8, t.y - t.z - 56, 0.55)
        self.shake = max(self.shake, 4)
        if t.hp <= 0:
            t.hp = 0
            t.lives -= 1
            t.st, t.t = "down", 0
            t.dying = True
            t.vx, t.vz = face * 4.5, 5.5
            setanim(t, "fall")
            return True
        if heavy:
            t.st, t.t = "down", 0
            t.dying = False
            t.vx, t.vz = face * 4.5, 5.0
            setanim(t, "fall")
        else:
            t.st, t.t = "hurt", 0
            t.vx = face * 2.5
            setanim(t, "hurt")
        return True

    def drop_held(self, t, throw):
        pig = t.held
        t.held = None
        t.prop = None
        if pig is not None:
            pig.x, pig.y = t.x + t.face * 30, t.y
            pig.z = 40
            self.launch(pig, t.face, 12 if throw else 3, 3)
            pig.src = t

    # ---- toad update ----------------------------------------------------------------------------------------------
    ATK = {"jab1": (10, 4, 6, 46, 1, "light", 2, 100), "jab2": (11, 4, 6, 46, 1, "light", 2, 100),
           "bigfist": (26, 11, 14, 84, 3, "launch", 6, 200), "bigboot": (26, 11, 14, 88, 3, "launch", 4, 200),
           "ram": (28, 12, 15, 70, 3, "launch", 8, 200), "headbutt": (12, 4, 6, 40, 2, "light", 2, 100)}

    def start_attack(self, t, name):
        t.st, t.t, t.atk = "atk", 0, name
        t.hitset = set()
        t.connected = False
        setanim(t, name)
        t.af = 0

    def start_jump(self, t, vx, kick=False):
        t.st, t.t = "jump", 0
        t.vx, t.vz = vx, 7.6
        t.kick = kick
        t.hitset = set()
        setanim(t, "jumpup")

    def toad_move(self, t, dx, dy, speed=2.7):
        d = math.hypot(dx, dy)
        if d < 0.5:
            setanim(t, "idle")
            return
        k = min(1.0, d / speed)
        t.x += dx / d * speed * k
        t.y += dy / d * speed * 0.75 * k
        if abs(dx) > 1:
            t.face = sgn(dx)
        setanim(t, "walk")

    def clamp_toad(self, t):
        lo = self.cam + 40
        hi = self.cam + VW - 40
        t.x = clamp(t.x, lo, hi)
        t.y = clamp(t.y, LY0, LY1)

    def toad_update(self, t):
        if t.inv > 0:
            t.inv -= 1
        if t.flash:
            t.flash -= 1
        st = t.st
        if st == "dead":
            t.t += 1
            if t.t == 1:
                t.x = clamp(t.x, self.cam + 40, self.cam + VW - 40)
            if t.lives > 0 and t.t > 80:
                self.respawn(t)
            return
        if st in ("idle", "walk", "move"):
            self.bot(t)
        elif st == "atk":
            self.update_attack(t)
        elif st == "jump":
            self.update_jump(t)
        elif st == "hurt":
            t.t += 1
            t.x += t.vx
            t.vx *= 0.85
            t.af += 0.18
            if t.t >= 14:
                t.st = "idle"
        elif st == "down":
            self.update_down(t)
        elif st == "lie":
            t.t += 1
            if t.t > 28:
                t.st, t.t = "getup", 0
                setanim(t, "getup")
        elif st == "getup":
            t.t += 1
            t.af = t.t / 7.0
            if t.t >= 14:
                t.st = "idle"
                t.inv = max(t.inv, 40)
        elif st == "grab":
            t.t += 1
            t.af = t.t / 7.0
            if t.t == 8 and t.held is not None:
                t.st, t.t = "hold", 0
                t.swing_t = 0
                t.prop = "pig"
                t.hitset = set()
            elif t.t > 16:
                t.st = "idle"
                if t.held:
                    t.held.st = "dazed"
                    t.held = None
        elif st == "hold":
            self.update_hold(t)
        elif st == "throw":
            t.t += 1
            if t.t == 4 and t.held is not None:
                self.drop_held(t, True)
            if t.t > 12:
                t.st = "idle"
        self.clamp_toad(t)
        if t.combo_win > 0 and t.st in ("idle", "walk"):
            t.combo_win -= 1
            if t.combo_win == 0:
                t.combo = 0
        if t.st in ("idle", "walk"):
            t.af += 0.28 if t.anim == "walk" else 0.17

    def respawn(self, t):
        mate = [m for m in self.toads if m is not t and m.alive and m.st != "dead"]
        t.x = (mate[0].x - 60) if mate else self.cam + 200
        t.y = random.randint(LY0 + 10, LY1 - 10)
        t.z = 220
        t.vz = 0
        t.hp = t.maxhp
        t.st, t.t = "jump", 0
        t.kick = False
        t.vx = 0
        t.inv = 110
        t.prop = None
        setanim(t, "jumpfall")

    def update_attack(self, t):
        total, h0, h1, reach, dmg, kind, lunge, pts = self.ATK[t.atk]
        t.t += 1
        n = len(SPR[t.spr][t.atk])
        t.af = min(n - 1, t.t * n // total)
        if t.t == h0:
            t.x += t.face * lunge
        if h0 <= t.t <= h1:
            for e in self.targets():
                if id(e) in t.hitset or not self.in_reach(t, e, reach):
                    continue
                t.hitset.add(id(e))
                t.connected = True
                self.damage_enemy(e, dmg, kind, t, pts)
                if kind == "light":
                    self.freeze = max(self.freeze, 1)
        if t.t >= total:
            t.st = "idle"
            if t.connected and t.combo < 2:
                t.combo += 1
                t.combo_win = 16
            else:
                t.combo = 0
                t.combo_win = 0

    def update_jump(self, t):
        t.t += 1
        t.x += t.vx
        t.z += t.vz
        t.vz -= GRAV
        if t.kick:
            setanim(t, "jkick")
            t.af = 1 if t.vz > -2 else 2
            for e in self.targets():
                if id(e) in t.hitset:
                    continue
                dx = (e.x - t.x) * t.face
                if -10 <= dx <= 62 + e.hw and abs(e.y - t.y) <= 16 and abs(e.z - (t.z + 20)) < 60:
                    t.hitset.add(id(e))
                    self.damage_enemy(e, 2, "light", t, 200)
                    t.vz = max(t.vz, 2.5)
        else:
            setanim(t, "jumpup" if t.vz > 3 else "jumppeak" if t.vz > -3 else "jumpfall")
        if t.z <= 0 and t.vz < 0:
            t.z = 0
            t.st, t.t = "idle", 0
            t.vx = 0
            self.add_fx("dust", t.x, t.y, 0.5)
            if t.inv < 20:
                t.inv = 20

    def update_down(self, t):
        t.t += 1
        t.x += t.vx
        t.z += t.vz
        t.vz -= GRAV
        t.af = min(3, t.t // 4)
        if t.z <= 0 and t.vz < 0:
            t.z = 0
            if not t.bounced and t.vz < -3:
                t.bounced = True
                t.vz = -t.vz * 0.35
                t.vx *= 0.5
                self.add_fx("dust", t.x, t.y, 0.5)
            else:
                t.bounced = False
                t.vx = 0
                self.add_fx("dust", t.x, t.y, 0.5)
                if t.dying:
                    t.st, t.t = "dead", 0
                    t.alive = t.lives > 0
                    setanim(t, "lie")
                else:
                    t.st, t.t = "lie", 0
                    setanim(t, "lie")

    def update_hold(self, t):
        t.swing_t += 1
        if t.prop == "pig":
            period, frames, anim, spins = 2, 10, "swingpig", 2
        else:
            period, frames, anim, spins = 2, 8, "swingleg", 1
        total = period * frames * (spins if t.prop == "pig" else t.uses)
        setanim(t, anim)
        i = (t.swing_t // period) % frames
        t.af = i
        if t.swing_t % (period * frames) == 1:
            t.hitset = set()
        ang = (170 + 40 * i) % 360 if t.prop == "pig" else (-150 + 38 * i) % 360
        fwd = 40 <= ang <= 140
        back = 220 <= ang <= 320 and t.prop == "pig"
        if t.swing_t % period == 0 and (fwd or back):
            d = t.face if fwd else -t.face
            for e in self.targets():
                if id(e) in t.hitset:
                    continue
                dx = (e.x - t.x) * d
                if -10 <= dx <= 84 + e.hw and abs(e.y - t.y) <= 16 and e.z <= t.z + 60:
                    t.hitset.add(id(e))
                    e.face = -d if e.face == d else e.face
                    saved = t.face
                    t.face = d
                    self.damage_enemy(e, 3 if t.prop == "leg" else 2, "launch" if t.prop == "leg" else "swing", t, 200)
                    t.face = saved
        if t.swing_t >= total:
            if t.prop == "pig":
                t.st, t.t = "throw", 0
                setanim(t, "throw")
            else:
                t.prop = None
                t.st = "idle"

    # ---- the bot ------------------------------------------------------------------------------------------------------
    def threat_on(self, t):
        # Returns (enemy, kind) for the most urgent incoming attack, or None.
        best = None
        for e in self.enemies:
            if e.hp <= 0:
                continue
            if e.kind == "raven" and e.st == "dive":
                if abs(e.tx - t.x) < 70 and abs(e.ty - t.y) < 26:
                    best = (e, "air")
            elif e.kind == "rat" and e.st in ("crouch", "leap"):
                if abs(e.x - t.x) < 130 and abs(e.y - t.y) < 22:
                    best = best or (e, "air")
            elif e.kind == "boss" and e.st == "slam" and abs(e.x - t.x) < 190:
                best = (e, "slam")
            elif e.kind == "boss" and e.st in ("charge", "chargewind") and abs(e.y - t.y) < 26 and (t.x - e.x) * e.face > -20:
                best = best or (e, "line")
            elif e.st in ("windup",):
                if (t.x - e.x) * e.face > -16 and abs(t.x - e.x) < e.reach + 30 and abs(e.y - t.y) < 24:
                    best = best or (e, "melee")
        return best

    def bot(self, t):
        if self.phase == "stageclear":
            setanim(t, "win")
            t.af = (self.tick // 8) % 2
            return
        free = [e for e in self.enemies if e.hp > 0 and e.st not in ("lie", "dying", "held", "launched")]
        t.react = max(0, t.react - 1)
        if t.dodge > 0:
            t.dodge -= 1
            t.y += t.dodge_dir * 3.4
            t.x -= t.face * 0.6
            setanim(t, "walk")
            return
        if t.flee > 0:
            t.flee -= 1
            self.toad_move(t, t.goal[0] - t.x, t.goal[1] - t.y, 3.0)
            if t.flee == 0 or abs(t.goal[0] - t.x) < 8:
                t.flee = 0
            return
        th = self.threat_on(t)
        if th and t.react == 0 and random.random() < 0.8:
            e, kind = th
            t.react = 18
            if kind in ("air", "slam"):
                if kind == "slam" and not (16 <= e.t <= 24):
                    pass
                elif kind == "air" and e.kind == "raven" and random.random() < 0.5 and abs(e.x - t.x) < 80:
                    pass
                else:
                    self.start_jump(t, 0)
                    return
            if kind == "melee" and e.kind == "pig" and abs(e.x - t.x) < 54 and e.t < 8 and random.random() < 0.8:
                t.face = sgn(e.x - t.x)
                self.start_attack(t, "jab1")
                return
            if kind in ("melee", "line", "air"):
                t.dodge = 12
                t.dodge_dir = -1 if t.y > e.y else 1
                if t.y + t.dodge_dir * 40 < LY0 or t.y + t.dodge_dir * 40 > LY1:
                    t.dodge_dir = -t.dodge_dir
                return
        # pickups: 1UPs always, flies when hurt, a dropped walker leg when there is a crowd to hit
        near_pick = None
        for it in self.items:
            d = math.hypot(it.x - t.x, (it.y - t.y) * 1.5)
            want = (it.spr == "oneup" and d < 700) or (it.spr == "fly" and t.hp <= 6 and d < 520) or \
                   (it.spr == "legitem" and len(free) >= 2 and d < 360 and t.prop is None)
            if want and (near_pick is None or d < near_pick[0]):
                near_pick = (d, it)
        if near_pick and not (th and th[1] == "melee"):
            it = near_pick[1]
            self.toad_move(t, it.x - t.x, it.y - t.y)
            return
        if not free:
            self.idle_walk(t)
            return
        # pinned: break out with a jump kick when cornered, run to open space when hurt
        crowd = [e for e in free if abs(e.x - t.x) < 120 and abs(e.y - t.y) < 60 and e.kind != "raven"]
        if len(crowd) >= 3 and t.hp <= 4 and t.flee == 0 and t.react == 0:
            mean = sum(e.x for e in crowd) / len(crowd)
            gx = clamp(t.x + (-sgn(mean - t.x)) * 260, self.cam + 70, self.cam + VW - 70)
            t.goal = (gx, (LY0 + LY1) / 2 + random.randint(-30, 30))
            t.flee = 40
            t.react = 30
            return
        mates = [m for m in self.toads if m is not t]
        # pick a target
        best, bs = None, 1e9
        for e in free:
            dx, dy = e.x - t.x, e.y - t.y
            s = abs(dx) + 2.2 * abs(dy)
            if e.kind == "raven":
                s += 70 if e.st != "dive" else -140
                if e.z > 60 and e.st != "dive":
                    s += 40
            if e.st == "dazed" and e.kind == "pig":
                s -= 50
            if e.st == "windup":
                s -= 30
            if e.x < self.cam - 20 or e.x > self.cam + VW + 20:
                s += 500
            for m in mates:
                if getattr(m, "tgt", None) is e:
                    s += 70
            if e.kind == "walker" and len(free) > 2:
                s += 40
            if s < bs:
                best, bs = e, s
        t.tgt = best
        e = best
        d = (e.x - t.x)
        face = sgn(d)
        dy = e.y - t.y
        ad = abs(d)
        # holding a leg: swing at anything near
        if t.prop == "leg":
            if ad < 110 and abs(dy) < 18:
                t.face = face
                t.st, t.t, t.swing_t = "hold", 0, 0
                return
        # jump kick for ravens and for closing distance
        if e.kind == "raven" and e.st != "dive":
            if ad < 110 and abs(dy) < 14 and e.z < 105:
                t.face = face
                self.start_jump(t, face * 2.6, True)
                return
            self.toad_move(t, d - face * 55, dy)
            return
        if 120 < ad < 190 and abs(dy) < 12 and random.random() < 0.015 and e.kind in ("pig", "rat"):
            t.face = face
            self.start_jump(t, face * 3.4, True)
            return
        a_reach = 34 if t.combo < 2 else 62
        want = e.x - face * (a_reach + (26 if e.kind in ("walker", "boss") else 0))
        # step in only when the lanes line up, so attacks connect instead of whiffing
        if abs(dy) > 9 or ad > a_reach + 26 + (26 if e.kind in ("walker", "boss") else 0):
            self.toad_move(t, want - t.x, dy)
            return
        t.face = face
        if e.kind == "pig" and e.hp <= 3 and (e.st == "dazed" or (e.st == "hurt" and t.combo >= 2)) and t.prop is None \
                and ad < 54 and random.random() < 0.5:
            t.st, t.t = "grab", 0
            t.held = e
            e.st = "held"
            setanim(t, "grab")
            return
        if t.combo >= 2:
            name = random.choices(("bigfist", "bigboot", "ram"), (0.4, 0.35, 0.25))[0]
            if ad > 60 and name == "ram":
                name = "bigfist"
            self.start_attack(t, name)
        elif t.combo == 1:
            self.start_attack(t, "jab2")
        else:
            self.start_attack(t, "headbutt" if ad < 28 and random.random() < 0.2 else "jab1")

    def idle_walk(self, t):
        # nobody to fight: walk right with the camera, keep clear of the screen edges and the other toad
        gx = self.cam + 400 + 90 * t.idx
        gy = 440 + 30 * (t.idx * 2 - 1) + 10 * math.sin(t.wander + self.tick / 40)
        t.face = 1
        if abs(gx - t.x) < 12 and abs(gy - t.y) < 8:
            setanim(t, "idle")
        else:
            self.toad_move(t, gx - t.x, gy - t.y, 3.0)

    # ---- enemies ------------------------------------------------------------------------------------------------------------
    def nearest_toad(self, e):
        best, bd = None, 1e9
        for t in self.toads:
            if not t.alive or t.st in ("dead",) or t.z > 100:
                continue
            d = abs(t.x - e.x) + 2 * abs(t.y - e.y)
            if d < bd:
                best, bd = t, d
        return best

    def attackers(self):
        return sum(1 for e in self.enemies if e.hp > 0 and e.st in ("windup", "attack", "slam", "chargewind", "charge", "crouch", "leap", "dive"))

    def hit_toads(self, e, reach, dmg, heavy, zmax=30):
        face = e.face
        for t in self.toads:
            if not t.alive or t.st in ("dead", "down", "lie", "getup"):
                continue
            dx = (t.x - e.x) * face
            if -14 <= dx <= reach + t.hw and abs(t.y - e.y) <= (18 if e.kind == "boss" else 14) and t.z < zmax:
                if self.hurt_toad(t, dmg, face, heavy):
                    return True
        return False

    def enemy_update(self, e):
        if e.flash:
            e.flash -= 1
        e.t += 1
        st = e.st
        k = e.kind
        if st == "held":
            return
        if st == "launched":
            self.update_launched(e)
            return
        if st == "lie":
            e.af = 0
            if e.t > (50 if k in ("walker", "boss") else 30) and e.hp > 0:
                e.st, e.t = "getup", 0
                setanim(e, "getup")
            elif e.hp <= 0 and e.t > 22:
                self.finish_enemy(e)
            return
        if st == "getup":
            e.af = e.t / 7.0
            if e.t >= 14:
                e.st, e.t, e.cd = "move", 0, 20
            return
        if st == "dying":
            self.update_dying(e)
            return
        if st == "hurt":
            e.x += e.vx
            e.vx *= 0.8
            e.af = 0 if e.t < 3 else 1
            if k == "raven":
                e.z = max(40, e.z - 1.5)
            if e.t >= (14 if k != "boss" else 22):
                if k == "pig" and e.hp <= 3:
                    e.st, e.t = "dazed", 0
                    setanim(e, "dazed")
                else:
                    e.st, e.t = "move", 0
            return
        if st == "dazed":
            e.af += 0.14
            e.vx *= 0.8
            if e.t > 90 or (k == "boss" and e.t > 50):
                e.st, e.t, e.cd = "move", 0, 10
            return
        tg = self.nearest_toad(e)
        if tg is None:
            setanim(e, "idle")
            e.af += 0.15
            return
        getattr(self, "ai_" + k)(e, tg)
        lim_lo, lim_hi = self.cam - 320, self.cam + VW + 320
        e.x = clamp(e.x, lim_lo, lim_hi)
        e.y = clamp(e.y, LY0, LY1)

    def approach(self, e, gx, gy, speed):
        # goals are kept on screen: a toad pinned at the edge must not make an enemy wait off-screen forever
        gx = clamp(gx, self.cam + 30, self.cam + VW - 30)
        dx, dy = gx - e.x, gy - e.y
        d = math.hypot(dx, dy)
        if d < 1:
            return True
        s = min(speed, d)
        e.x += dx / d * s
        e.y += dy / d * s * 0.7
        return d < speed + 2

    def walkanim(self, e, rate=0.26):
        setanim(e, "walk")
        e.af += rate

    def ai_pig(self, e, tg):
        d = tg.x - e.x
        e.cd = max(0, e.cd - 1)
        if e.st == "move":
            e.face = sgn(d)
            ok = e.cd == 0 and self.attackers() < 2 + (self.canyon >= 1)
            if ok:
                gx = tg.x - e.face * (e.reach - 14)
                self.approach(e, gx, tg.y, e.speed)
                self.walkanim(e)
                if abs(tg.y - e.y) <= 7 and abs(gx - e.x) <= 6 and tg.st not in ("down", "lie", "dead"):
                    e.st, e.t = "windup", 0
                    e.kick = random.random() < 0.4
                    setanim(e, "kickwind" if e.kick else "windup")
            else:
                side = -1 if (e.x < tg.x) else 1
                gx = tg.x + side * (150 + 30 * (id(e) % 3))
                gy = tg.y + 38 * math.sin(self.tick / 35 + id(e) % 7)
                if abs(gx - e.x) > 10:
                    self.approach(e, gx, gy, e.speed * 0.8)
                    self.walkanim(e)
                else:
                    setanim(e, "idle")
                    e.af += 0.15
        elif e.st == "windup":
            e.af = min(1, e.t // 8)
            if e.t >= (14 if not e.kick else 16):
                e.st, e.t = "attack", 0
                setanim(e, "kick" if e.kick else "punch")
                e.af = 0
                e.hitset = set()
        elif e.st == "attack":
            if e.t == 1:
                e.x += e.face * 3
            if e.t in (1, 2, 3, 4):
                if self.hit_toads(e, 54 if e.kick else e.reach, e.dmg, False):
                    e.t = max(e.t, 5)
            if e.t >= 6:
                e.af = 1 if not e.kick else 0
            if e.t >= 18:
                e.st, e.t = "move", 0
                e.cd = 34 + random.randint(0, 36)

    def ai_rat(self, e, tg):
        d = tg.x - e.x
        e.cd = max(0, e.cd - 1)
        if e.st == "move":
            e.face = sgn(d)
            if e.cd == 0 and self.attackers() < 3:
                gx = tg.x - e.face * 105
                self.approach(e, gx, tg.y, e.speed)
                self.walkanim(e, 0.4)
                if abs(gx - e.x) < 10 and abs(tg.y - e.y) < 8:
                    e.st, e.t = "crouch", 0
                    setanim(e, "crouch")
            else:
                gx = tg.x - e.face * 190
                self.approach(e, gx, tg.y + 36 * math.sin(self.tick / 20 + id(e) % 5), e.speed * 0.9)
                self.walkanim(e, 0.4)
        elif e.st == "crouch":
            if e.t >= 11:
                e.st, e.t = "leap", 0
                setanim(e, "leap")
                e.vx = e.face * 6.2
                e.vz = 5.0
                e.hitset = set()
        elif e.st == "leap":
            e.x += e.vx
            e.z += e.vz
            e.vz -= GRAV * 0.9
            if not e.hitset and self.hit_toads(e, 24, e.dmg, False, 45):
                e.hitset.add(1)
            if e.z <= 0:
                e.z = 0
                e.st, e.t = "recover", 0
                setanim(e, "crouch")
                self.add_fx("dust", e.x, e.y, 0.5)
        elif e.st == "recover":
            if e.t > 22:
                e.st, e.t = "move", 0
                e.cd = 45 + random.randint(0, 40)

    def ai_walker(self, e, tg):
        d = tg.x - e.x
        e.cd = max(0, e.cd - 1)
        if e.st == "move":
            e.face = sgn(d)
            if e.cd == 0 and self.attackers() < 2:
                gx = tg.x - e.face * (e.reach - 18)
                self.approach(e, gx, tg.y, e.speed)
                self.walkanim(e, 0.2)
                if abs(tg.y - e.y) <= 8 and abs(gx - e.x) <= 8:
                    e.st, e.t = "windup", 0
                    setanim(e, "windup")
            else:
                gx = tg.x - e.face * 160
                self.approach(e, gx, tg.y, e.speed)
                self.walkanim(e, 0.2)
        elif e.st == "windup":
            e.af = min(1, e.t // 11)
            if e.t >= 24:
                e.st, e.t = "attack", 0
                setanim(e, "stomp")
        elif e.st == "attack":
            if e.t == 2:
                self.add_fx("dust", e.x + e.face * 56, e.y, 0.5)
                self.shake = max(self.shake, 4)
            if 2 <= e.t <= 6:
                if self.hit_toads(e, e.reach, e.dmg, True):
                    e.t = 7
            if e.t >= 8:
                e.af = 1
            if e.t >= 26:
                e.st, e.t = "move", 0
                e.cd = 45 + random.randint(0, 40)

    def ai_raven(self, e, tg):
        e.cd = max(0, e.cd - 1)
        e.af += 0.45
        if e.st == "move":
            e.face = sgn(tg.x - e.x)
            gx = tg.x - e.face * 190
            e.z += (86 + 12 * math.sin(self.tick / 17 + id(e) % 9) - e.z) * 0.12
            self.approach(e, gx, tg.y + 20 * math.sin(self.tick / 23), e.speed)
            if e.cd == 0 and abs(tg.x - e.x) < 220 and self.attackers() < 2 and e.t > 30:
                e.st, e.t = "windup", 0
        elif e.st == "windup":
            e.x += math.sin(e.t) * 1.2
            e.z += 1.0
            if e.t >= 16:
                e.st, e.t = "dive", 0
                e.tx, e.ty = tg.x, tg.y
                e.face = sgn(e.tx - e.x)
                setanim(e, "dive")
                e.hitset = set()
        elif e.st == "dive":
            e.x += (e.tx - e.x) * 0.1 + e.face * 1.2
            e.y += (e.ty - e.y) * 0.1
            e.z += (14 - e.z) * 0.1
            if not e.hitset and abs(e.x - e.tx) < 40 and e.z < 50:
                if self.hit_toads(e, 30, e.dmg, False, 60):
                    e.hitset.add(1)
            if e.t >= 22:
                e.st, e.t = "climb", 0
                setanim(e, "fly")
        elif e.st == "climb":
            e.x += e.face * 3.4
            e.z += 3.4
            if e.t >= 22:
                e.st, e.t = "move", 0
                e.cd = 70 + random.randint(0, 50)
        if e.st != "dive" and e.anim != "fly":
            setanim(e, "fly")

    def ai_boss(self, e, tg):
        d = tg.x - e.x
        e.cd = max(0, e.cd - 1)
        if e.hp < e.maxhp * 0.5 and not e.enraged:
            e.enraged = True
            e.speed *= 1.25
        if e.enraged and not e.summoned and e.st == "move":
            e.summoned = True
            for side in ("l", "r"):
                self.spawn("rat", side)
        if e.st == "move":
            e.face = sgn(d)
            if e.cd == 0:
                gx = tg.x - e.face * 100
                self.approach(e, gx, tg.y, e.speed)
                self.walkanim(e, 0.22)
                far = abs(d) > 200
                if abs(tg.y - e.y) <= 9 and abs(gx - e.x) <= 10:
                    e.st, e.t = "windup", 0
                    setanim(e, "windup")
                elif far and random.random() < 0.02:
                    if e.enraged and random.random() < 0.5:
                        e.st, e.t = "chargewind", 0
                        setanim(e, "windup")
                    else:
                        e.st, e.t = "slam", 0
                        setanim(e, "slamup")
                        e.vz = 9.5
                        e.vx = clamp((tg.x - e.x) / 34.0, -7, 7)
                        e.hitset = set()
            else:
                gx = tg.x - e.face * 220
                self.approach(e, gx, tg.y, e.speed * 0.8)
                self.walkanim(e, 0.22)
        elif e.st == "windup":
            e.af = min(1, e.t // 10)
            if e.t >= 20:
                e.st, e.t = "attack", 0
                setanim(e, "punch")
        elif e.st == "attack":
            if 2 <= e.t <= 7 and self.hit_toads(e, e.reach, e.dmg, True):
                e.t = 8
            if e.t >= 8:
                e.af = 1
            if e.t >= 30:
                e.st, e.t = "move", 0
                e.cd = 40 + random.randint(0, 30)
                if random.random() < 0.35 and abs(d) < 160:
                    e.st, e.t = "slam", 0
                    setanim(e, "slamup")
                    e.vz = 9.5
                    e.vx = clamp((tg.x - e.x) / 34.0, -7, 7)
        elif e.st == "slam":
            e.x += e.vx
            e.z += e.vz
            e.vz -= GRAV
            if e.vz < 0:
                setanim(e, "slam")
            if e.z <= 0 and e.vz < 0:
                e.z = 0
                self.add_fx("ring", e.x, e.y, 0.5)
                self.shake = 10
                for t in self.toads:
                    if t.alive and t.st not in ("dead", "down", "lie") and t.z < 14 and abs(t.x - e.x) < 150 and abs(t.y - e.y) < 34:
                        self.hurt_toad(t, 2, sgn(t.x - e.x), True)
                e.st, e.t = "recover", 0
        elif e.st == "recover":
            if e.t > 26:
                e.st, e.t, e.cd = "move", 0, 36
        elif e.st == "chargewind":
            e.af = min(1, e.t // 12)
            e.flash = 2 if e.t % 4 < 2 else 0
            e.face = sgn(d)
            if e.t >= 26:
                e.st, e.t = "charge", 0
                setanim(e, "charge")
                e.hitset = set()
        elif e.st == "charge":
            e.x += e.face * 8.5
            e.y += clamp(tg.y - e.y, -1, 1)
            e.af += 0.4
            if self.hit_toads(e, 50, 3, True):
                pass
            edge = e.x < self.cam + 40 or e.x > self.cam + VW - 40
            if e.t > 44 or edge:
                self.shake = 8 if edge else 0
                e.st, e.t = "dazed", 0
                setanim(e, "dazed")
                e.af = 0

    def update_launched(self, e):
        e.t += 1
        e.x += e.vx
        e.z += e.vz
        e.vz -= GRAV
        e.af = min(3, e.t // 4) if abs(e.vx) > 3 else 3
        if e.kind == "raven":
            e.af = (e.t // 3) % 4
        speed = abs(e.vx)
        if speed > 3:
            for o in self.targets():
                if o is e or id(o) in e.hitset:
                    continue
                if abs(o.x - e.x) < 26 and abs(o.y - e.y) < 18 and abs(o.z - e.z) < 40:
                    e.hitset.add(id(o))
                    o.face = 1 if e.vx < 0 else -1
                    self.damage_enemy(o, 3, "launch" if o.kind not in ("walker",) else "swing", e.src, 200)
        offscreen = e.x < self.cam - 90 or e.x > self.cam + VW + 90
        if e.hp <= 0 and offscreen:
            self.add_fx("spark", clamp(e.x, self.cam + 16, self.cam + VW - 16), e.y - e.z - 40, 0.5)
            self.add_fx("pow", clamp(e.x, self.cam + 30, self.cam + VW - 30), e.y - e.z - 40, 0.5)
            self.finish_enemy(e)
            return
        if e.z <= 0 and e.vz < 0:
            e.z = 0
            if not e.bounced and e.vz < -3.5:
                e.bounced = True
                e.vz = -e.vz * 0.4
                e.vx *= 0.55
                self.add_fx("dust", e.x, e.y, 0.5)
            else:
                e.vx = 0
                self.add_fx("dust", e.x, e.y, 0.5)
                e.st, e.t = "lie", 0
                setanim(e, "lie")
                if e.kind == "raven":
                    setanim(e, "fall")
                    e.af = 3

    def update_dying(self, e):
        e.af = 0
        if e.t % 4 == 0:
            self.add_fx("boom", e.x + random.randint(-30, 30) * (1 if e.kind == "walker" else 2), e.y - 30 - random.randint(0, 50) * (1 if e.kind == "walker" else 2), 0.45)
        self.shake = max(self.shake, 3)
        if e.t > (28 if e.kind == "walker" else 90):
            self.add_fx("boom", e.x, e.y - 50, 0.35)
            self.finish_enemy(e)

    def finish_enemy(self, e):
        if e in self.enemies:
            self.enemies.remove(e)
        self.drop_loot(e)

    # ---- level flow ----------------------------------------------------------------------------------------------------------------
    def alive_enemies(self):
        return [e for e in self.enemies if e.hp > 0]

    def update_flow(self):
        if self.title_t > 0:
            self.title_t -= 1
        living = [t for t in self.toads if t.alive]
        if self.phase == "walk":
            # camera follows the lead toad, never beyond the next lock point
            # forced scroll like the original belt-scrollers: the screen edge pushes a lagging toad along, so a
            # toad stuck on a pickup can never deadlock the level
            nxt = self.locks[self.sec] if self.sec < len(self.locks) else None
            limit = nxt if nxt is not None else 1e12
            self.cam = min(self.cam + 2.8, limit)
            self.arrow_on = self.title_t <= 0 and self.cam < limit - 2
            if nxt is not None and self.cam >= nxt - 0.5:
                self.lock_x = nxt
                self.start_wave(self.sec)
        elif self.phase == "fight":
            self.wave_t += 1
            self.arrow_on = False
            while self.queue and self.queue[0][2] <= self.wave_t:
                kind, side, _ = self.queue.pop(0)
                self.spawn(kind, side)
            if not self.queue and not self.alive_enemies():
                self.wave_cleared()
            elif self.wave_t > 2600:
                for e in self.alive_enemies():
                    e.hp = 0
                    e.st, e.t = "dying", 0
                    setanim(e, "hurt")
        elif self.phase == "clear":
            self.arrow_on = self.pt > 20
            self.pt += 1
            if self.pt == 40 and self.oneup_drop:
                self.oneup_drop = False
                self.spawn_item("oneup", self.cam + VW // 2, 460)
            if self.pt >= 50:
                self.phase = "walk"
                self.lock_x = None
        elif self.phase == "stageclear":
            self.pt += 1
            if self.pt == 150:
                self.r.fill(0xFFFF)
            if self.pt >= 158:
                self.canyon += 1
                self.world_base = self.locks[-1] + 400
                self.setup_canyon()
                self.cam = self.world_base - 150 + 0.0
                for t in living:
                    t.x = self.cam + 120 + 70 * t.idx
                    t.inv = 60
                self.enemies, self.items = [], []
                self.r.force = True

    def start_wave(self, i):
        self.phase = "fight"
        self.wave_t = 0
        self.queue = sorted(self.wave_spec(i), key=lambda q: q[2])
        low = [t for t in self.toads if t.alive and t.hp <= 3]
        if low:
            self.spawn_item("fly", self.cam + 480, 470)

    def wave_cleared(self):
        if self.sec == 5:
            self.phase = "stageclear"
            self.pt = 0
            self.boss = None
            return
        self.sec += 1
        self.phase = "clear"
        self.pt = 0
        self.oneup_drop = self.sec == 5

    # ---- items and misc updates ----------------------------------------------------------------------------------------------------
    def update_items(self):
        for it in self.items[:]:
            it.t += 1
            it.x = clamp(it.x, self.cam + 50, self.cam + VW - 50)
            if it.t > 900:
                self.items.remove(it)
                continue
            if it.spr == "oneup":
                it.z = max(30, it.z - 2) if it.z > 30 else 30 + 5 * math.sin(it.t / 8)
            if it.spr == "fly":
                it.af = it.t * 0.4
            for t in self.toads:
                if t.alive and t.st not in ("dead", "down", "lie") and abs(it.x - t.x) < 26 and abs(it.y - t.y) < 16:
                    if it.spr == "fly":
                        t.hp = min(t.maxhp, t.hp + 3)
                        self.add_fx("spark", t.x, t.y - 60, 0.5)
                        self.items.remove(it)
                    elif it.spr == "oneup":
                        t.lives = min(9, t.lives + 1)
                        self.award(t, 1000, t.x, t.y, False)
                        self.pops.append([t.x, t.y - 110, 0, LAB["oneup"][0]])
                        self.items.remove(it)
                    elif it.spr == "legitem" and t.prop is None and t.st in ("idle", "walk"):
                        t.prop = "leg"
                        t.uses = 3
                        t.st, t.t = "idle", 0
                        t.face = t.face
                        setanim(t, "holdleg")
                        self.items.remove(it)
                    break

    def update_misc(self):
        for f in self.fx[:]:
            f[3] += f[4]
            if f[3] >= len(f[2]):
                self.fx.remove(f)
        for p in self.pops[:]:
            p[2] += 1
            p[1] -= 0.8
            if p[2] > 36:
                self.pops.remove(p)
        if self.shake > 0:
            self.shake -= 1

    # ---- frame --------------------------------------------------------------------------------------------------------------------------
    def tick_logic(self):
        self.tick += 1
        if self.freeze > 0:
            self.freeze -= 1
            self.update_misc()
            return
        self.update_flow()
        for t in self.toads:
            if t.alive or t.st == "dead":
                self.toad_update(t)
                if t.prop == "leg" and t.st in ("idle", "walk"):
                    setanim(t, "holdleg")
                    t.af = 0
        for e in self.enemies[:]:
            self.enemy_update(e)
        self.update_items()
        self.update_misc()
        self.over = all((not t.alive) and t.t > 40 for t in self.toads)

    def shadow_for(self, e):
        k = e.kind
        i = 4 if k == "boss" else 3 if k == "walker" else 2 if k in ("raven",) else 1 if k in ("rat",) else 0
        if k == "raven":
            return SHADOW[self.r.pal][2]
        return SHADOW[self.r.pal][i]

    def build_items(self):
        cam = int(self.cam)
        if self.shake:
            cam += random.randint(-3, 3)
        items = []
        ents = []
        for t in self.toads:
            if t.alive or (t.st == "dead" and t.t < 70):
                ents.append(t)
        ents += self.enemies
        for e in ents:
            if e.st == "held":
                continue
            items.append((self.shadow_for(e), int(e.x) - cam, int(e.y)))
        for it in self.items:
            items.append((SHADOW[self.r.pal][2], int(it.x) - cam, int(it.y)))
        ents.sort(key=lambda e: e.y)
        for e in ents:
            if e.st == "held":
                continue
            if e.kind == "toad":
                if e.st == "dead" and e.t > 50 and (e.t // 3) % 2:
                    continue
                if e.inv > 0 and e.st not in ("hurt", "down", "lie", "dead") and (e.inv // 2) % 2:
                    continue
            if e.kind in ("pig", "rat", "walker", "boss") and e.st == "lie" and e.hp <= 0 and (e.t // 2) % 2:
                continue
            if e.kind != "toad" and e.st == "dying" and (e.t // 2) % 2 and e.kind == "walker":
                continue
            fr = frame_of(e)
            if e.kind == "raven":
                items.append((fr, int(e.x) - cam, int(e.y - e.z - 6)))
            else:
                items.append((fr, int(e.x) - cam, int(e.y - e.z)))
            if e.kind != "toad" and e.st in ("windup", "chargewind") and (e.t // 3) % 2 == 0:
                items.append((FX["alert"][0], int(e.x) - cam, int(e.y - e.z - (150 if e.kind == "boss" else 118 if e.kind == "walker" else 96))))
            if e.kind != "toad" and e.st == "dazed":
                items.append((FX["stars"][int(self.tick * 0.35) % 6], int(e.x) - cam, int(e.y - 92 * (1.7 if e.kind == "boss" else 1.0) * (0.9 if e.kind == "rat" else 1))))
        for it in self.items:
            if it.spr == "fly":
                items.append((FX["fly"][int(it.af) % 2], int(it.x) - cam, int(it.y - 24 - 4 * math.sin(it.t / 6))))
            elif it.spr == "oneup":
                items.append((FX["oneup"][0], int(it.x) - cam, int(it.y - it.z)))
            else:
                items.append((SPR["legitem"]["idle"][0][0], int(it.x) - cam, int(it.y)))
        for f in self.fx:
            items.append((f[2][int(f[3])], int(f[0]) - cam, int(f[1])))
        for p in self.pops:
            items.append((p[3], int(p[0]) - cam, int(p[1])))
        # HUD
        for t in self.toads:
            self.hud(t, items)
        if self.title_t > 0 and self.phase == "walk":
            key = "title" if self.canyon == 0 else "canyon2" if self.canyon % 2 == 1 else "canyon3"
            if (self.title_t // 4) % 6 != 5 or self.title_t > 100:
                items.append((LAB[key][0], VW // 2, 130))
        if self.phase == "fight" and self.sec == 5 and self.wave_t < 90 and (self.wave_t // 6) % 2 == 0:
            items.append((LAB["warning"][0], VW // 2, 100))
        if self.phase == "fight" and self.sec == 5 and 90 <= self.wave_t < 190:
            items.append((LAB["blag"][0], VW // 2, 110))
        if self.phase == "stageclear" and self.pt < 140:
            items.append((LAB["clear"][0], VW // 2, 150))
        if self.arrow_on:
            items.append((ARROW[(self.tick // 10) % 2], VW - 70, 130))
            items.append((LAB["go"][0], VW - 70, 100))
        return cam, items

    def hud(self, t, items):
        x0 = 8 if t.idx == 0 else VW - 8 - 312
        y0 = 4
        items.append((HUDS["plate%d" % t.idx], x0 + 156, y0 + 25))
        items.append((HUDS["p"][t.idx], x0 + 288, y0 + 14))
        for i in range(8):
            items.append((HUDS["full"] if i < t.hp else HUDS["empty"], x0 + 52 + i * 17 + 7, y0 + 17))
        s = "%d" % t.score
        for i, ch in enumerate(s):
            items.append((HUDS["digit"][int(ch)], x0 + 56 + i * 13, y0 + 37))
        items.append((HUDS["x"], x0 + 262, y0 + 37))
        items.append((HUDS["digit"][max(0, t.lives)], x0 + 276, y0 + 37))

    def total_score(self):
        return sum(t.score for t in self.toads)

    def step(self):
        if self.end_started:
            return self.end.tick()
        self.tick_logic()
        cam, items = self.build_items()
        self.r.render(cam, items)
        if self.over or self.total_score() >= TARGET_SCORE and self.phase in ("clear", "walk", "stageclear") or self.tick >= CAP_TICKS - 160:
            self.end_started = True
            self.end.start(self.total_score(), "GAME OVER" if self.over else "STAGE COMPLETE")
        return False


def make():
    g = Game()
    return g.step
