# Dead Space: a self-playing 2D adaptation of the 2008 survival-horror classic.
# Isaac Clarke walks the USG Ishimura corridors seen from the side, cutting necromorphs apart with the Plasma
# Cutter (strategic dismemberment), freezing them with Stasis, throwing severed blades with Kinesis, stomping
# crates and corpses for loot and fighting a boss at the end of each chapter.
#
# Rendering: virtual pixels of 4x4 screen pixels (480x270). Every frame is built row by row from pre-expanded
# strips (parallax wall at half speed, floor at full speed, a lit "flashlight" ellipse cut from the bright strip
# over the dark one), then sprites are blitted as pre-expanded runs and each virtual row is written 4 times.
from fbcore import *
import re, math
from array import array

B = load_bundle("g_deadspace.bin")
VW, VH = 480, 270
RB = VW * 8                      # bytes of one virtual row (also the framebuffer scanline size)
HUD_H = 14
WALL_H = 206
WALL_STRIDE = (576 + VW) * 8
FLOOR_STRIDE = (480 + VW) * 8
WALL_TILE, FLOOR_TILE = 576, 480
GY = 236                         # feet row of Isaac; necromorphs use lanes around it for a depth hint
ELEV = (-30, -15, 0, 15, 30)
cos, sin, atan2, hypot, floor = math.cos, math.sin, math.atan2, math.hypot, math.floor

FR = [None] * VH                 # rows of the frame being composed
PREV = [None] * VH               # rows currently on the screen


def col8(r, g, b):
    return rgb565(r, g, b).to_bytes(2, "little") * 4


COL = dict(
    white=col8(240, 240, 245), cyan=col8(110, 230, 255), blue=col8(60, 150, 255), amber=col8(255, 184, 60),
    red=col8(255, 60, 50), dred=col8(120, 10, 14), blood=col8(150, 14, 18), green=col8(120, 255, 140),
    yellow=col8(255, 224, 90), spark=col8(255, 170, 60), grey=col8(150, 150, 160), dgrey=col8(60, 60, 68),
    black=col8(0, 0, 0), ice=col8(190, 235, 255), orange=col8(255, 120, 30), gore=col8(100, 20, 24),
    plasma=col8(170, 230, 255), panel=col8(14, 14, 20),
)

_RX = re.compile(b"\x01+")
_XC = {}


def _expand(spr, flip):
    """Packed sprite -> list of rows, each a tuple of (byte offset, expanded bytes) runs of opaque pixels."""
    w, h, px, mask = spr
    rows = []
    for y in range(h):
        m = mask[y * w:(y + 1) * w]
        if m.find(1) < 0:
            rows.append(())
            continue
        p = px[y * w * 2:(y + 1) * w * 2]
        if flip:
            m = m[::-1]
            a = array("H")
            a.frombytes(p)
            a.reverse()
            p = a.tobytes()
        out = bytearray(w * 8)
        lo, hi = p[0::2], p[1::2]
        out[0::8] = lo
        out[1::8] = hi
        out[2::8] = lo
        out[3::8] = hi
        out[4::8] = lo
        out[5::8] = hi
        out[6::8] = lo
        out[7::8] = hi
        rows.append(tuple((a0 * 8, bytes(out[a0 * 8:b0 * 8])) for a0, b0 in (mt.span() for mt in _RX.finditer(m))))
    return (w, h, rows)


def xs(spr, flip=False):
    k = (id(spr), flip)
    r = _XC.get(k)
    if r is None:
        r = _XC[k] = _expand(spr, flip)
    return r


def draw(spr, x, y, flip=False):
    w, h, rows = xs(spr, flip)
    j0 = -y if y < 0 else 0
    j1 = VH - y if y + h > VH else h
    if x >= 0 and x + w <= VW:
        xb = x * 8
        for j in range(j0, j1):
            runs = rows[j]
            if runs:
                r = FR[y + j]
                for o, d in runs:
                    p = xb + o
                    r[p:p + len(d)] = d
        return
    if x + w <= 0 or x >= VW:
        return
    xb = x * 8
    for j in range(j0, j1):
        r = FR[y + j]
        for o, d in rows[j]:
            p = xb + o
            if p >= RB:
                continue
            if p < 0:
                d = d[-p:]
                p = 0
            if p + len(d) > RB:
                d = d[:RB - p]
            if d:
                r[p:p + len(d)] = d


def rect(x, y, w, h, c8):
    x0, x1, y0, y1 = max(0, x), min(VW, x + w), max(0, y), min(VH, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    d = c8 * (x1 - x0)
    a, b = x0 * 8, x1 * 8
    for yy in range(y0, y1):
        FR[yy][a:b] = d


def hline(x0, x1, y, c8):
    rect(x0, y, x1 - x0, 1, c8)


GLY = B["props"]["glyph"]
GCH = B["props"]["glyph_chars"]


GK = dict(w="w", white="w", a="a", amber="a", yellow="a", r="r", red="r", c="c", cyan="c", g="g", green="g", d="d")


def text(s, x, y, ck="w"):
    g = GLY[GK[ck]]
    for i, ch in enumerate(s):
        k = GCH.find(ch)
        if k > 0:
            draw(g[k], x + i * 6, y)


def text_c(s, cx, y, ck="w"):
    text(s, cx - len(s) * 3, y, ck)


# flashlight ellipse: half-width per row (a lit pool around Isaac, mostly on the wall behind and the floor)
HW = [0] * VH
for _y in range(VH):
    _d = (_y - 190) / 120.0
    HW[_y] = int(112 * math.sqrt(1 - _d * _d)) if abs(_d) < 1 else 0
HWM = [0] * VH
for _y in range(VH):
    _d = (_y - 190) / 165.0
    HWM[_y] = int(160 * math.sqrt(1 - _d * _d)) if abs(_d) < 1 else 0


BLACKROW = bytes(RB)
DUST = [(random.randrange(VW), random.randrange(30, 250), random.choice((0.3, 0.5, 0.8)), random.randint(1, 5)) for _ in range(22)]


class Obj:
    """Plain attribute bag; every entity in the world is one of these."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def mkitem(kind, x, y, gy, vx=0.0, vy=0.0):
    return Obj(kind=kind, x=x, y=y, gy=gy, vx=vx, vy=vy, age=0)


class Node(Obj):
    """A shootable boss weak point; `gate` says whether it can be hurt right now."""

    def shootable(self):
        return self.gate()


# ---- tuning tables ---------------------------------------------------------------------------------------------
# (body hp, limb hp, score for the kill). Limb hp is two Plasma Cutter shots at base damage: the reason
# dismemberment is the efficient way to kill (a torso hit needs several times more shots).
STATS = {
    ("slasher", "pale"): (70, 20, 100), ("slasher", "enh"): (120, 36, 220), ("slasher", "grey"): (50, 15, 140),
    ("leaper", "pale"): (60, 20, 200), ("leaper", "enh"): (100, 34, 320),
    ("lurker", "pale"): (40, 14, 150), ("infector", "pale"): (14, 14, 150), ("exploder", "pale"): (80, 10, 120),
    ("pregnant", "pale"): (80, 10, 250), ("spawn", "pale"): (6, 6, 20), ("brute", "dark"): (170, 0, 500),
    ("brute", "pale"): (260, 0, 900), ("hunter", "pale"): (330, 26, 2500),
}
PIECE = dict(legF="leg", legB="leg", armF="blade", armB="blade", head="head", tail="tail", t0="tendril", t1="tendril",
             t2="tendril", bulb="bulb", s0="sack", s1="sack", s2="sack")
THROW_DMG = dict(blade=44, claw=44, tail=36, leg=24, head=14, canister=60)
KILL_NAMES = dict(slasher="SLASHER", leaper="LEAPER", lurker="LURKER", infector="INFECTOR", exploder="EXPLODER",
                  pregnant="PREGNANT", spawn="SWARMER", brute="BRUTE", hunter="HUNTER")


def mk(t, x, y=None, pal="pale", boss=False):
    st = STATS[(t, pal)]
    gy = float(GY + random.randint(-3, 4))
    e = Obj(t=t, x=float(x), y=gy if y is None else float(y), gy=gy, face=-1, vx=0.0, vy=0.0, air=False,
            dead=False, fake=False, st="walk", tm=0.0, fr=random.random() * 4, slow=0.0, ts=1.0, stun=0.0, hitf=0,
            cool=40.0, pal=pal, boss=boss, p={}, regen={}, hp=float(st[0]), hpmax=float(st[0]), lh=st[1],
            blind=0.0, infect=None, age=0, fly=20.0, hit_done=True, host=None, spd=0.0, cdir=1, loot=False, fall=False, fv=0.0)
    lh = float(st[1])
    if t == "slasher":
        e.p = dict(legF=lh, legB=lh, armF=lh, armB=lh, head=lh)
    elif t == "leaper":
        e.p = dict(tail=lh, armF=lh, armB=lh, head=lh)
    elif t == "lurker":
        e.p = dict(t0=lh, t1=lh, t2=lh)
        e.air = True
    elif t == "exploder":
        e.p = dict(bulb=lh)
    elif t == "pregnant":
        e.p = dict(s0=lh, s1=lh, s2=lh)
    elif t == "hunter":
        e.p = dict(armF=lh, armB=lh, legF=lh, legB=lh)
    return e


def hit_part(e, bx, by):
    """Which part of the necromorph a point (bx, by) in screen space hits, or None for a miss."""
    dx = bx - e.x
    f = dx * e.face
    rel = e.y - by
    t = e.t
    p = e.p
    if t == "slasher":
        if abs(dx) > 13 or rel < 0 or rel > 58:
            return None
        crawl = "legF" not in p and "legB" not in p
        if crawl:
            if rel > 20:
                return None
            if f > 6 and "armF" in p:
                return "armF"
            if f > 6 and "armB" in p:
                return "armB"
            if f > 8 and rel > 9 and "head" in p:
                return "head"
            return "torso"
        if rel < 21:
            if "legF" in p and (f >= -1 or "legB" not in p):
                return "legF"
            if "legB" in p:
                return "legB"
            return "torso"
        if rel < 34:
            return "torso"
        if "head" in p and 36 <= rel <= 47 and f >= 2:
            return "head"
        if "armF" in p and (f >= 0 or "armB" not in p):
            return "armF"
        if "armB" in p:
            return "armB"
        return "torso"
    if t == "leaper":
        if abs(dx) > 24 or rel < 0 or rel > 48:
            return None
        if f < -6 and rel > 12:
            return "tail" if "tail" in p else None
        if rel > 28:
            return None
        if f > 6 and rel >= 12 and "head" in p:
            return "head"
        if f > 2 and rel < 14:
            return "armF" if "armF" in p else ("armB" if "armB" in p else "torso")
        return "torso"
    if t == "lurker":
        if abs(dx) < 13 and abs(by - e.y) < 7:
            return "torso"
        depth = by - e.y
        if 6 <= depth <= 32:
            for i in (0, 1, 2):
                if "t%d" % i in p and abs(dx - (i - 1) * (6 + 7 * depth / 20.0)) < 4.5:
                    return "t%d" % i
        return None
    if t == "infector":
        return "torso" if abs(dx) < 11 and abs(by - (e.y - e.fly)) < 8 else None
    if t == "exploder":
        if abs(dx) > 18 or rel < 0 or rel > 48:
            return None
        if "bulb" in p and f > 6 and 12 <= rel <= 34:
            return "bulb"
        return "torso"
    if t == "pregnant":
        if abs(dx) > 14 or rel < 0 or rel > 54:
            return None
        if 13 <= rel <= 34 and abs(dx) < 11:
            best, bd = None, 99
            for i, (ox, oy) in enumerate(((4, 29), (-1, 23), (7, 20))):
                k = "s%d" % i
                if k in p:
                    d = abs(dx * e.face - ox) + abs(rel - oy)
                    if d < bd and d < 13:
                        best, bd = k, d
            if best:
                return best
        return "torso"
    if t == "spawn":
        return "torso" if abs(dx) < 9 and 0 <= rel < 12 else None
    if t == "brute":
        if abs(dx) > 26 or rel < 0 or rel > 62:
            return None
        return "weak" if (e.st == "stun" or e.slow > 0) else "armor"
    if t == "hunter":
        if abs(dx) > 26 or rel < 0 or rel > 80:
            return None
        crawl = "legF" not in p and "legB" not in p
        if rel < 38 and not crawl:
            if "legF" in p and (f >= 0 or "legB" not in p):
                return "legF"
            return "legB" if "legB" in p else "torso"
        if rel >= 60 and not crawl:
            return "torso"
        if abs(f) >= 6:
            if f > 0 and "armF" in p:
                return "armF"
            if "armB" in p:
                return "armB"
            if "armF" in p:
                return "armF"
        return "torso"
    return None


def aim_point(e, part):
    """Where the bot aims to hit `part`, led a little for movement."""
    fx = e.face
    t = e.t
    if t == "slasher":
        crawl = "legF" not in e.p and "legB" not in e.p
        if crawl:
            h = dict(armF=11, armB=11, head=10).get(part, 8)
            return e.x + fx * (8 if part != "torso" else 1), e.y - h
        h = dict(legF=11, legB=11, torso=28, head=42, armF=51, armB=51).get(part, 28)
        return e.x + fx * (5 if part in ("head", "armF", "armB") else 0), e.y - h
    if t == "leaper":
        if part == "tail":
            return e.x - fx * 12, e.y - 34
        if part == "head":
            return e.x + fx * 10, e.y - 20
        if part in ("armF", "armB"):
            return e.x + fx * 8, e.y - 6
        return e.x, e.y - 16
    if t == "lurker":
        if part == "torso":
            return e.x, e.y
        i = int(part[1])
        return e.x + (i - 1) * (6 + 7 * 16 / 20.0), e.y + 16
    if t == "infector":
        return e.x, e.y - e.fly
    if t == "exploder":
        return (e.x + fx * 13, e.y - 22) if part == "bulb" else (e.x, e.y - 28)
    if t == "pregnant":
        if part in ("s0", "s1", "s2"):
            ox, oy = ((4, 29), (-1, 23), (7, 20))[int(part[1])]
            return e.x + fx * ox, e.y - oy
        return e.x, e.y - 30
    if t == "spawn":
        return e.x, e.y - 4
    if t == "brute":
        return e.x - fx * 5, e.y - 34
    if t == "hunter":
        crawl = "legF" not in e.p and "legB" not in e.p
        h = dict(legF=18, legB=18, armF=46, armB=46, torso=48).get(part, 48)
        if crawl:
            h = min(h, 30)
        return e.x + fx * (10 if part in ("armF", "armB") else 0), e.y - h
    return e.x, e.y - 20


def sprite_of(e):
    """(sprite, flip, left, top) for a mob in its current state and limb configuration."""
    M = B["mob"][e.t]
    p = e.p
    fl = e.face < 0
    f4 = int(e.fr) & 3
    t = e.t
    if t == "slasher":
        lm = ("legF" in p) | (("legB" in p) << 1)
        am = ("armF" in p) | (("armB" in p) << 1)
        hd = 1 if "head" in p else 0
        if e.dead or e.fake:
            s = M[(e.pal, "dead", lm, am, hd, 0)]
        elif lm == 0:
            s = M[(e.pal, "crawl", 0, am or 1, hd, f4)]
        elif e.st == "attack":
            s = M[(e.pal, "attack", lm, am or 1, hd, min(2, int(e.tm / 4.7)))]
        else:
            s = M[(e.pal, "walk", lm, am or 1, hd, f4)]
        if e.dead or e.fake:
            return s, fl, int(e.x) - s[0] // 2, int(e.y) + 2 - s[1]
    elif t == "leaper":
        tl = 1 if "tail" in p else 0
        am = ("armF" in p) | (("armB" in p) << 1)
        hd = 1 if "head" in p else 0
        if e.dead:
            s = M[(e.pal, "dead", tl, am, hd, 0)]
        elif e.air:
            s = M[(e.pal, "air", tl, am or 1, hd, 0)]
        elif e.st == "whip":
            s = M[(e.pal, "whip", tl, am or 1, hd, min(1, int(e.tm / 8)))]
        else:
            s = M[(e.pal, "crawl", tl, am or 1, hd, f4)]
    elif t == "lurker":
        tm = ("t0" in p) | (("t1" in p) << 1) | (("t2" in p) << 2)
        s = M[(tm, "fire" if e.st == "fire" else "hang", int(e.fr) & 1)]
        return s, fl, int(e.x) - s[0] // 2, int(e.y) - 12
    elif t == "infector":
        s = M[f4]
        return s, fl, int(e.x) - s[0] // 2, int(e.y - e.fly) - 12
    elif t == "exploder":
        s = M[(1 if "bulb" in p else 0, f4, 1 if (e.st == "fuse" and int(e.tm) & 2) else 0)]
    elif t == "pregnant":
        sm = ("s0" in p) | (("s1" in p) << 1) | (("s2" in p) << 2)
        s = M[(sm, "attack", min(1, int(e.tm / 7)))] if e.st == "attack" else M[(sm, "walk", f4)]
    elif t == "spawn":
        s = M[int(e.fr) % 3]
    elif t == "brute":
        if e.dead:
            s = M[(e.pal, "dead", 0)]
        elif e.st in ("charge", "roar"):
            s = M[(e.pal, "charge", int(e.fr) % 3)]
        elif e.st == "stun":
            s = M[(e.pal, "charge", 2)]
        elif e.st == "attack":
            s = M[(e.pal, "attack", min(2, int(e.tm / 6)))]
        else:
            s = M[(e.pal, "walk", f4)]
    elif t == "hunter":
        am = ("armF" in p) | (("armB" in p) << 1)
        lm = ("legF" in p) | (("legB" in p) << 1)
        s = M[(am, lm, "attack", min(2, int(e.tm / 5.5)))] if e.st == "attack" else M[(am, lm, "walk", f4)]
        if lm == 0:
            return s, fl, int(e.x) - s[0] // 2, int(e.y) + 2 - s[1] + 36
    return s, fl, int(e.x) - s[0] // 2, int(e.y) + 2 - s[1]


# ---- chapter layout ---------------------------------------------------------------------------------------------
CH_LEN = (720, 760, 800, 840, 880, 920)
POOLS = [
    [("slasher", "pale")] * 5 + [("leaper", "pale")],
    [("slasher", "pale")] * 3 + [("leaper", "pale")] * 2 + [("lurker", "pale")] * 2 + [("infector", "pale")],
    [("slasher", "pale")] * 2 + [("slasher", "enh")] * 2 + [("exploder", "pale")] * 2 + [("lurker", "pale")] + [("leaper", "pale")],
    [("pregnant", "pale")] * 2 + [("slasher", "pale")] * 2 + [("leaper", "enh")] + [("exploder", "pale")] + [("lurker", "pale")]
    + [("infector", "pale")],
    [("slasher", "grey")] * 3 + [("slasher", "enh")] * 2 + [("pregnant", "pale")] + [("leaper", "enh")] + [("exploder", "pale")],
    [("slasher", "enh")] * 2 + [("leaper", "enh")] * 2 + [("pregnant", "pale")] + [("lurker", "pale")] * 2 + [("exploder", "pale")]
    + [("brute", "dark")],
]
BOSS_NAMES = ("BRUTE", "THE HUNTER", "BRUTE AND EXPLODERS", "THE LEVIATHAN", "THE HUNTER AND TWITCHERS", "THE HIVE MIND")
LOOT = [("credit", 47), ("plasma", 28), ("health", 10), ("pulse", 6), ("node", 6), ("stasis", 3)]


def pick_loot(need_ammo=False):
    if need_ammo and random.random() < 0.7:
        return "plasma"
    r = random.random() * 100
    for k, w in LOOT:
        r -= w
        if r <= 0:
            return k
    return "credit"


class Game:
    def __init__(self):
        self.t = 0
        self.score = 0
        self.credits = 0
        self.kills = {}
        self.limbs = 0
        self.ci = -1
        self.mode = "card"
        self.mt = 0
        self.end = None
        self.hudkey = None
        self.hud = None
        self.base_hp = 100
        self.upg = dict(dmg=0, clip=0, hp=0)
        self.nodes = 0
        self.I = Obj(x=60.0, y=float(GY), face=1, act="free", at=0.0, hp=100.0, packs=1, weapon="pc", mag=dict(pc=10, pulse=0),
                     res=dict(pc=30, pulse=0), stasis=100.0, inv=0, vx=0.0, cool=0.0, elev=0, look=1, kin=None,
                     target=None, aimt=0, moving=0, lastshot=-999, kincool=0, stcool=0, back=0.0,
                     deadtype="plain", walkdir=1, anim=0.0, bench=None, mcool=0, burst=0, part=None)
        self.start_chapter(0)

    # -- setup --
    def start_chapter(self, ci):
        self.ci = ci
        self.env = B["env"][ci]
        self.cfg = B["chapters"][ci]
        L = CH_LEN[ci]
        self.L = L
        self.cam0 = L + 60               # camera is locked here during the boss fight
        self.arena_l, self.arena_r = L + 82, L + 60 + VW - 18
        self.mobs, self.corpses, self.debris, self.items, self.bolts, self.parts, self.fx, self.pops = [], [], [], [], [], [], [], []
        self.crates, self.lockers, self.barrels, self.vents, self.jets, self.humans = [], [], [], [], [], []
        self.boss = None
        self.boss_done = False
        self.shake = 0
        self.flash = 0
        self.blackout = 0
        self.flick = 0
        self.flick_next = random.randint(120, 300)
        # a depressurised, gravity-less stretch (zero-G in the game): everything in it floats
        self.zerog = (int(L * 0.3), int(L * 0.3) + 270) if ci in (3, 4) else None
        self.stasis_fx = 0
        self.warn = 0
        self.fade = 0
        self.stains = []
        self.alert = False
        self.chap_t = 0
        self.last_prog = 0
        self.maxx = 0.0
        self.doorf = [0.0, 0.0]          # airlock animation frames (entry to the arena, exit)
        self.exit_walk = False
        rnd = random
        I = self.I
        I.x, I.y, I.face, I.act, I.at, I.vx = 60.0, float(GY), 1, "free", 0, 0.0
        I.inv, I.target, I.kin, I.moving = 0, None, None, 0
        I.hp = max(I.hp, 0.7 * self.base_hp)
        I.mag["pc"] = min(I.res["pc"] + I.mag["pc"], 10 + 2 * self.upg["clip"])
        self.cam = 0.0
        # vents every ~190 vpx, a mix of wall and ceiling openings; ambushes pick the one nearest to where they want it
        x = 230
        while x < L + 40:
            self.vents.append(Obj(x=x + rnd.randint(-30, 30), y=rnd.choice((148, 156, 164)), kind="wall", open=False))
            if rnd.random() < 0.5:
                self.vents.append(Obj(x=x + rnd.randint(40, 120), y=30, kind="ceil", open=False))
            x += rnd.randint(150, 230)
        for i in range(5):
            self.crates.append(Obj(x=rnd.randint(200, L - 80), y=GY - 2 + rnd.randint(0, 2), state=0))
        for i in range(3):
            self.lockers.append(Obj(x=rnd.randint(240, L - 100), y=GY - 12, state=0))
        for i in range(2 + (ci > 1)):
            self.barrels.append(Obj(x=rnd.randint(300, L - 120), y=GY - 2 + rnd.randint(0, 3), state=0))
        for i in range(4):
            self.humans.append(Obj(x=rnd.randint(260, L - 60), y=GY + rnd.randint(1, 7), kind=rnd.randrange(3), looted=False,
                                   rise=False, infect=None, human=True))
        for i in range(4):
            self.jets.append(Obj(x=rnd.randint(260, L - 40), y=GY - rnd.randint(0, 120), ph=rnd.randint(0, 90)))
        bx = int(L * 0.5)
        self.stations = [Obj(kind="save", x=170, used=False), Obj(kind="bench", x=bx, used=False),
                         Obj(kind="save", x=L - 90, used=False)]
        self.cp = 90.0
        for i in range(8):
            gy = float(GY + rnd.randint(2, 8))
            self.items.append(mkitem(pick_loot(i == 0), rnd.randint(220, L - 60), gy, gy))
        self.items.append(mkitem("health", bx + 40, GY + 4.0, GY + 4.0))
        self.items.append(mkitem("node", rnd.randint(320, L - 200), GY + 4.0, GY + 4.0))
        # ambush beats along the corridor; the first one waits a little so the player sees the corridor first
        n = 3 + (ci == 5)
        xs_ = sorted(rnd.randint(330, L - 130) for _ in range(n))
        kinds = ["vent", "vent", "wave", "rear", "corpse", "ceil", "vent", "wave"]
        self.beats = []
        pool = POOLS[ci]
        for i, bxx in enumerate(xs_):
            k = rnd.choice(kinds) if i else "vent"
            cnt = 1 + (rnd.random() < 0.5) + (ci >= 3 and rnd.random() < 0.3)
            mobs = [rnd.choice(pool) for _ in range(cnt)]
            if k == "ceil":
                mobs = [rnd.choice([m for m in pool if m[0] in ("lurker", "leaper", "slasher")] or pool)]
            self.beats.append(Obj(x=bxx, kind=k, mobs=mobs, done=False))
        self.mode = "card"
        self.mt = 0
        self.card_drawn = False

    # -- helpers --
    def in_zg(self, x):
        return self.zerog is not None and self.zerog[0] <= x <= self.zerog[1]

    def popup(self, s, x, y, ck="w", life=34):
        self.pops.append(Obj(s=s, x=x, y=y, life=life, ck=ck))
        del self.pops[:-5]

    def blood(self, x, y, n, vx=0.0, big=False):
        for _ in range(n):
            self.parts.append([x, y, vx + random.uniform(-1.6, 1.6), random.uniform(-2.8, 0.2), random.randint(10, 26),
                               "blood" if random.random() < 0.8 else "gore", 2 if big and random.random() < 0.4 else 1])
        del self.parts[:-150]

    def sparks(self, x, y, n, ck="spark"):
        for _ in range(n):
            self.parts.append([x, y, random.uniform(-2.5, 2.5), random.uniform(-2.5, 0.5), random.randint(6, 14), ck, 1])
        del self.parts[:-150]

    def add_score(self, n, x=None, y=None, label=None, ck="w"):
        self.score += n
        if label and x is not None:
            self.popup(label, int(x - self.cam) - len(label) * 3, int(y) - 6, ck)

    def spawn(self, t, pal, x, y=None, boss=False, face=None):
        e = mk(t, x, y, pal, boss)
        e.face = face if face else (1 if self.I.x > x else -1)
        self.mobs.append(e)
        return e

    def throw_piece(self, kind, pal, x, y, vx, vy, throwable=True):
        pc = B["piece"].get((kind, pal)) or B["piece"][(kind, "pale")]
        self.debris.append(Obj(kind=kind, pal=pal, pcs=pc, x=x, y=y, vx=vx, vy=vy, rot=random.randrange(8), spin=random.choice((-1, 1)) * random.uniform(0.2, 0.5),
                               ground=False, gy=GY + random.randint(1, 9), age=0, throwable=throwable))
        del self.debris[:-45]

    def hurt(self, dmg, srcx, kind, push=2.4):
        I = self.I
        if I.inv > 0 or I.act == "die":
            return
        I.hp -= dmg
        I.inv = 26
        self.shake = max(self.shake, 5)
        self.blood(I.x, I.y - 28, 7, vx=-1.5 * (1 if srcx > I.x else -1))
        if I.hp <= 0:
            I.deadtype = "bitten" if kind in ("slasher", "hunter", "leaper", "brute") and random.random() < 0.7 else "plain"
            I.act, I.at = "die", 0.0
            I.kin = None
            return
        if I.act in ("aim", "recoil", "reload", "use", "kin", "stasis", "bench"):
            I.act, I.at = "free", 0.0
            I.kin = None
        elif I.act == "free":
            I.act, I.at = "hurt", 0.0
        I.vx = -push * (1 if srcx > I.x else -1)

    # -- damage to necromorphs --
    def sever(self, e, part, vx):
        e.p.pop(part, None)
        e.hitf = 6
        e.stun = max(e.stun, 10)
        kind = PIECE.get(part)
        self.limbs += 1
        x, y = aim_point(e, part) if e.t != "lurker" else (e.x, e.y + 12)
        if kind:
            k = "claw" if (kind == "blade" and e.t in ("hunter", "leaper")) else kind
            self.throw_piece(k, e.pal if e.pal in ("pale", "enh") else "pale", x, y, vx * 1.0 + random.uniform(-1, 1), random.uniform(-3.2, -1.4))
        self.blood(x, y, 16, vx * 0.6, True)
        bonus = 80 if part == "head" else 50
        self.add_score(bonus, x, y, "+%d" % bonus, "amber")
        if e.t == "hunter":
            e.hp -= 55
            e.regen[part] = 150.0
            if e.hp <= 0:
                self.kill(e, vx)
                return
        elif e.t == "slasher":
            if "armF" not in e.p and "armB" not in e.p:
                self.kill(e, vx)
                return
            if "legF" not in e.p and "legB" not in e.p and random.random() < 0.35 and not e.fake:
                e.fake, e.tm = True, random.uniform(70, 120)
        elif e.t == "leaper":
            if e.air and part in ("armF", "armB"):
                self.kill(e, vx)
                return
            arms = ("armF" in e.p) + ("armB" in e.p)
            if arms == 0 or (arms == 1 and "tail" not in e.p):
                self.kill(e, vx)
                return
        elif e.t == "lurker":
            if not any(k in e.p for k in ("t0", "t1", "t2")):
                self.kill(e, vx)
                return
        elif e.t == "exploder" and part == "bulb":
            self.kill(e, vx)
            return
        elif e.t == "pregnant" and part in ("s0", "s1", "s2"):
            for _ in range(2):
                s = self.spawn("spawn", "pale", e.x + random.uniform(-6, 6), e.y)
                s.vx, s.vy, s.air = random.uniform(-2, 2), -2.5, True
            self.sparks(x, y, 8, "yellow")

    def kill(self, e, vx=0.0):
        if e.dead:
            return
        e.dead = True
        e.fake = False
        self.kills[e.t] = self.kills.get(e.t, 0) + 1
        sc = STATS[(e.t, e.pal)][2]
        self.add_score(sc, e.x, e.y - 30, "+%d" % sc, "yellow")
        if e.t == "pregnant":
            for k in ("s0", "s1", "s2"):
                if k in e.p:
                    for _ in range(2):
                        s = self.spawn("spawn", "pale", e.x + random.uniform(-6, 6), e.y)
                        s.vx, s.vy, s.air = random.uniform(-2, 2), -2.5, True
        if e.t == "exploder":
            self.detonate(e)
        elif e.t == "lurker":
            self.blood(e.x, e.y, 14)
            e.vy, e.air, e.fall = 0.5, True, True
            self.corpses.append(e)
            e.dead = True
        elif e.t in ("slasher", "leaper", "brute", "hunter"):
            self.corpses.append(e)
            e.air = False
            e.st = "dead"
            e.loot = True
            self.blood(e.x, e.y - 20, 18, vx * 0.5, True)
            if len(self.corpses) > 10:
                self.corpses.pop(0)
        else:
            self.blood(e.x, e.y - 8, 10)
        if e in self.mobs:
            self.mobs.remove(e)

    def detonate(self, e):
        """An Exploder going off: the blast takes limbs off its neighbours (dismemberment by explosion)."""
        if e in self.mobs:
            self.mobs.remove(e)
        e.dead = True
        self.sparks(e.x, e.y - 26, 14, "yellow")
        self.blood(e.x, e.y - 20, 14, big=True)
        self.blast(e.x, e.y - 24, 44, 30)

    def pop_barrel(self, b):
        if b.state:
            return
        b.state = 1
        self.blast(b.x, b.y - 14)

    def damage(self, e, part, dmg, vx=0.0):
        """Apply `dmg` to the part of e that was hit; limbs come off, the torso just loses hit points."""
        if e.dead or part is None:
            return
        e.hitf = 3
        if e.t == "brute":
            # the frontal plates shrug almost everything off; only the glowing back spots take full damage
            e.hp -= dmg * (0.12 if part == "armor" else 1.0)
            self.sparks(e.x, e.y - 34, 3)
            if e.hp <= 0:
                self.kill(e, vx)
            return
        if part in e.p:
            e.p[part] -= dmg
            self.blood(e.x, e.y - 30, 3, vx * 0.3)
            if e.p[part] <= 0:
                self.sever(e, part, vx * 0.8 + (1 if e.x > self.I.x else -1))
            return
        e.hp -= dmg * (0.4 if e.t == "hunter" else 1.0)
        self.blood(e.x, e.y - 28, 3, vx * 0.3)
        if e.t == "slasher" and not e.dead and e.hp < e.hpmax * 0.45 and part == "torso":
            e.stun = max(e.stun, 6)
        if e.hp <= 0:
            self.kill(e, vx)

    # ---- necromorph behaviour ---------------------------------------------------------------------------------------
    def face_to(self, e):
        e.face = 1 if self.I.x > e.x else -1

    def update_mob(self, e):
        I = self.I
        e.age += 1
        if e.slow > 0:
            e.slow -= 1
            dt = 0.12
        else:
            dt = 1.0
        e.ts = dt
        if e.hitf:
            e.hitf -= 1
        dx = I.x - e.x
        dist = abs(dx)
        t = e.t
        e.spd = 0.0
        if self.in_zg(e.x) and not e.air and t not in ("lurker", "infector") and not e.boss:
            e.y += (e.gy - 14 + 3 * sin(e.age * 0.07) - e.y) * 0.1
        elif not e.air and e.y < e.gy - 0.5 and t not in ("lurker", "infector"):
            e.y = min(e.gy, e.y + 1.5)
        if e.air and t != "lurker":
            e.vy += (0.05 if self.in_zg(e.x) else 0.25) * dt
            e.y += e.vy * dt
            e.x += e.vx * dt
            if e.t == "leaper" and not e.hit_done and abs(I.x - e.x) < 15 and e.y > e.gy - 34:
                e.hit_done = True
                self.hurt(18, e.x, "leaper")
            if e.vy > 0 and e.y >= e.gy:
                e.y, e.air, e.vx, e.vy = e.gy, False, 0.0, 0.0
                if t == "leaper":
                    e.st, e.cool = "walk", 36.0
            return
        if e.stun > 0:
            e.stun -= dt
            return
        e.cool -= dt
        if t == "slasher":
            self.ai_slasher(e, dt, dx, dist)
        elif t == "leaper":
            self.ai_leaper(e, dt, dx, dist)
        elif t == "lurker":
            self.ai_lurker(e, dt, dx, dist)
        elif t == "infector":
            self.ai_infector(e, dt, dx, dist)
        elif t == "exploder":
            self.face_to(e)
            e.fr += 0.2 * dt
            if e.st != "fuse" and dist < 46:
                e.st, e.tm = "fuse", 0.0
            if e.st == "fuse":
                e.tm += dt
            sp = (2.0 if e.st == "fuse" else 1.5)
            e.x += e.face * sp * dt
            e.spd = sp
            if dist < 12 or e.tm > 45:
                self.detonate(e)
        elif t == "pregnant":
            self.face_to(e)
            if e.st == "attack":
                e.tm += dt
                if e.tm >= 7 and not e.hit_done and dist < 32:
                    e.hit_done = True
                    self.hurt(14, e.x, "pregnant")
                if e.tm >= 14:
                    e.st, e.cool = "walk", 38.0
            elif dist < 26 and e.cool <= 0:
                e.st, e.tm, e.hit_done = "attack", 0.0, False
            else:
                e.x += e.face * 0.5 * dt
                e.spd = 0.5
                e.fr += 0.08 * dt
        elif t == "spawn":
            self.face_to(e)
            e.fr += 0.3 * dt
            if dist > 8:
                e.x += e.face * 2.1 * dt
                e.spd = 2.1
            elif e.cool <= 0:
                e.cool = 22.0
                self.hurt(4, e.x, "spawn", 1.2)
        elif t == "brute":
            self.ai_brute(e, dt, dx, dist)
        elif t == "hunter":
            self.ai_hunter(e, dt, dx, dist)
        if e.boss:
            e.x = max(self.arena_l - 20, min(self.arena_r + 12, e.x))

    def ai_slasher(self, e, dt, dx, dist):
        p = e.p
        if e.fake:
            e.tm -= dt
            if e.tm <= 0 or dist < 30:
                e.fake, e.st, e.tm = False, "rise", 0.0
                e.stun = 8
                self.shake = max(self.shake, 4)
            return
        if e.st == "rise":
            e.tm += dt
            if e.tm > 8:
                e.st = "walk"
            return
        if "head" in p:
            self.face_to(e)
        else:
            e.blind -= dt
            if e.blind <= 0:
                e.blind = random.uniform(14, 28)
                e.face = random.choice((-1, 1)) if random.random() < 0.55 else (1 if dx > 0 else -1)
        legs = ("legF" in p) + ("legB" in p)
        arms = ("armF" in p) + ("armB" in p)
        base = (0.95, 0.55, 0.34)[2 - legs]
        if e.pal == "grey":
            base *= 1.9
        elif e.pal == "enh":
            base *= 1.12
        reach = 14 if legs == 0 else 17
        if e.st == "attack":
            e.tm += dt
            if e.tm >= 9 and not e.hit_done:
                e.hit_done = True
                if abs(self.I.x - e.x) < reach + 7:
                    self.hurt(20 if e.pal == "enh" else 14, e.x, "slasher")
            if e.tm >= 14:
                e.st, e.cool = "walk", 26.0
            return
        if e.st == "roar":
            e.tm += dt
            if e.tm >= 12:
                e.st, e.tm = "charge", 0.0
            return
        if e.st == "walk" and legs == 2 and dist > 100 and random.random() < 0.01 and e.pal != "grey":
            e.st, e.tm = "roar", 0.0
            return
        if dist < reach and e.cool <= 0 and arms > 0:
            e.st, e.tm, e.hit_done = "attack", 0.0, False
            return
        sp = base
        if e.st == "charge":
            e.tm += dt
            sp = 2.5
            if e.tm > 40 or dist < 40:
                e.st = "walk"
        if e.pal == "grey" and random.random() < 0.3:
            sp *= 0.2           # twitchers stutter between bursts
        e.x += e.face * sp * dt
        e.spd = sp
        e.fr += (0.1 + sp * 0.07) * dt

    def ai_leaper(self, e, dt, dx, dist):
        p = e.p
        self.face_to(e)
        arms = ("armF" in p) + ("armB" in p)
        can = arms == 2 and "tail" in p
        short = arms == 2 and "tail" not in p
        if e.st == "whip":
            e.tm += dt
            if e.tm >= 8 and not e.hit_done and dist < 30:
                e.hit_done = True
                self.hurt(12, e.x, "leaper")
            if e.tm >= 16:
                e.st, e.cool = "walk", 30.0
            return
        if dist < 24 and e.cool <= 0:
            e.st, e.tm, e.hit_done = "whip", 0.0, False
            return
        if e.cool <= 0 and ((can and 55 < dist < 150) or (short and 25 < dist < 55)):
            e.air, e.hit_done = True, False
            zg = self.in_zg(e.x)
            e.vy = (-1.2 if zg else -3.3) if can else -2.0
            n = (48.0 if zg else 25.0) if can else 16.0
            e.vx = max(-4.6, min(4.6, dx / n))
            e.st = "air"
            return
        sp = 1.15 if arms == 2 else 0.5
        if "tail" not in p:
            sp *= 0.8
        e.x += e.face * sp * dt
        e.spd = sp
        e.fr += 0.2 * dt

    def ai_lurker(self, e, dt, dx, dist):
        self.face_to(e)
        e.y = 38.0
        e.fr += 0.06 * dt
        if dist > 125:
            e.x += (1 if dx > 0 else -1) * 0.95 * dt
        elif dist < 70:
            e.x -= (1 if dx > 0 else -1) * 0.8 * dt
        n = len(e.p)
        if e.st == "fire":
            e.tm += dt
            if e.tm >= 12:
                e.st, e.cool = "hang", 80.0 + 30 * (3 - n)
                i = random.choice([int(k[1]) for k in e.p] or [1])
                sx, sy = e.x + (i - 1) * 9, e.y + 24
                tx, ty = self.I.x, self.I.y - 30
                d = hypot(tx - sx, ty - sy) or 1
                self.bolts.append(Obj(kind="barb", hostile=True, x=sx, y=sy, vx=3.3 * (tx - sx) / d, vy=3.3 * (ty - sy) / d,
                                      dmg=9, life=120, pcs=None))
        elif e.cool <= 0 and dist < 190:
            e.st, e.tm = "fire", 0.0

    def ai_infector(self, e, dt, dx, dist):
        e.fly = 20 + 6 * sin(e.age * 0.15)
        if e.st == "attached":
            h = e.host
            if h not in self.corpses and h not in self.humans:
                e.st, e.host = "walk", None
                return
            e.x, e.fly = h.x, 5
            h.infect = (h.infect or 0) - dt
            if random.random() < 0.3:
                self.sparks(h.x, h.y - 6, 1, "green")
            if h.infect <= 0:
                (self.corpses if h in self.corpses else self.humans).remove(h)
                n = self.spawn("slasher", "enh", h.x, h.y, face=1 if self.I.x > h.x else -1)
                n.st, n.tm, n.stun = "rise", 0.0, 10
                self.shake = max(self.shake, 6)
                self.flash = 2
                self.mobs.remove(e)
            return
        hosts = [h for h in self.humans + self.corpses if h.infect is None and abs(h.x - e.x) < 500
                 and (hasattr(h, "human") or h.t == "slasher")]
        tgt = min(hosts, key=lambda h: abs(h.x - e.x)) if hosts else None
        if tgt is not None:
            d = tgt.x - e.x
            e.face = 1 if d > 0 else -1
            e.x += e.face * 1.7 * dt
            e.spd = 1.7
            e.fr += 0.3 * dt
            if abs(d) < 6:
                e.st, e.host = "attached", tgt
                tgt.infect = 60.0
            return
        self.face_to(e)
        e.x += e.face * 1.9 * dt
        e.spd = 1.9
        e.fr += 0.3 * dt
        if dist < 12 and e.cool <= 0:
            e.cool = 40.0
            self.hurt(5, e.x, "infector")

    def ai_brute(self, e, dt, dx, dist):
        if e.st != "charge":
            self.face_to(e)
        if e.st == "stun":
            e.tm += dt
            if e.tm >= 80:
                e.st, e.cool, e.tm = "walk", 50.0, 0.0
            return
        if e.st == "roar":
            e.tm += dt
            e.fr += 0.1
            if e.tm >= 24:
                e.st, e.tm, e.hit_done = "charge", 0.0, False
                e.cdir = 1 if self.I.x > e.x else -1
            return
        if e.st == "charge":
            e.tm += dt
            e.fr += 0.35 * dt
            e.x += e.cdir * 3.5 * dt
            e.spd = 3.5
            if not e.hit_done and abs(self.I.x - e.x) < 22:
                e.hit_done = True
                self.hurt(38, e.x, "brute", 7)
            past = (self.I.x - e.x) * e.cdir < -60
            edge = (self.boss and (e.x <= self.arena_l - 18 or e.x >= self.arena_r + 8))
            if e.tm >= 60 or past or edge:
                e.st, e.tm = "stun", 0.0
                self.shake = 9
                self.sparks(e.x + e.cdir * 24, e.y - 30, 12)
            return
        if e.st == "attack":
            e.tm += dt
            if e.tm >= 10 and not e.hit_done and dist < 40:
                e.hit_done = True
                self.hurt(30, e.x, "brute", 5)
            if e.tm >= 18:
                e.st, e.cool = "walk", 45.0
            return
        if dist < 32 and e.cool <= 0:
            e.st, e.tm, e.hit_done = "attack", 0.0, False
        elif dist > 80 and e.cool <= 0:
            e.st, e.tm = "roar", 0.0
        else:
            e.x += e.face * 0.55 * dt
            e.spd = 0.55
            e.fr += 0.1 * dt

    def ai_hunter(self, e, dt, dx, dist):
        p = e.p
        self.face_to(e)
        for k in list(e.regen):
            e.regen[k] -= dt
            if e.regen[k] <= 0:
                del e.regen[k]
                p[k] = e.lh
                self.sparks(e.x, e.y - 40, 8, "green")
        legs = ("legF" in p) + ("legB" in p)
        arms = ("armF" in p) + ("armB" in p)
        if e.st == "attack":
            e.tm += dt
            if e.tm >= 8 and not e.hit_done and dist < 44:
                e.hit_done = True
                self.hurt(28 if arms else 16, e.x, "hunter", 5)
            if e.tm >= 16:
                e.st, e.cool = "walk", 26.0
            return
        if dist < (36 if arms else 24) and e.cool <= 0:
            e.st, e.tm, e.hit_done = "attack", 0.0, False
            return
        sp = (0.8, 1.2, 2.0)[legs]
        e.x += e.face * sp * dt
        e.spd = sp
        e.fr += (0.12 + sp * 0.08) * dt

    # ---- projectiles, debris and pick-ups -------------------------------------------------------------------------------
    def blast(self, x, y, r=40, dmg_i=24):
        self.fx.append(Obj(kind="boom", x=x, y=y, age=0))
        self.shake = 10
        self.flash = 2
        self.sparks(x, y, 24, "orange")
        I = self.I
        if hypot(I.x - x, I.y - 20 - y) < r:
            self.hurt(dmg_i, x, "barrel", 4)
        for o in list(self.mobs):
            if not o.dead and abs(o.x - x) < r:
                o.hp -= 70
                for part in list(o.p)[:2]:
                    if o.t in ("slasher", "leaper", "hunter"):
                        self.sever(o, part, 2.5 * (1 if o.x > x else -1))
                        if o.dead:
                            break
                if not o.dead and o.hp <= 0:
                    self.kill(o)
        for b in self.barrels:
            if b.state == 0 and abs(b.x - x) < r:
                self.pop_barrel(b)

    def node_hit(self, x, y, dmg):
        """Boss weak points (Leviathan tentacle nodes and mouth bulb, Hive Mind bulbs). Returns True on a hit."""
        if not self.boss:
            return False
        for n in self.boss.nodes:
            if n.alive and hypot(x - n.x, y - n.y) < n.r:
                n.hp -= dmg * (2.0 if n.open else 1.0)
                n.hitf = 3
                self.sparks(x, y, 4, "yellow")
                self.shake = max(self.shake, 1)
                if n.hp <= 0:
                    n.alive = False
                    self.add_score(n.score, n.x, n.y, "+%d" % n.score, "yellow")
                    self.sparks(n.x, n.y, 20, "yellow")
                    self.sparks(n.x, n.y, 12, "orange")
                    self.blood(n.x, n.y, 18, big=True)
                    self.shake = 10
                    self.flash = 2
                    self.limbs += 1
                return True
        return False

    def update_bolts(self):
        I = self.I
        keep = []
        for b in self.bolts:
            alive = True
            for _ in range(3):
                b.x += b.vx / 3.0
                b.y += b.vy / 3.0
                b.life -= 1 / 3.0
                if b.hostile:
                    if abs(b.x - I.x) < 7 and abs(b.y - (I.y - 28)) < 26:
                        self.hurt(b.dmg, b.x - b.vx, "lurker")
                        alive = False
                        break
                    continue
                hit = None
                for e in self.mobs:
                    if e.dead or abs(b.x - e.x) > 34:
                        continue
                    if e.t == "lurker" or abs(b.y - e.y) < 90:
                        part = hit_part(e, b.x, b.y)
                        if part:
                            hit = (e, part)
                            break
                if hit:
                    e, part = hit
                    if b.kind == "stasis":
                        self.stasis_field(b.x, b.y)
                    elif b.kind == "throw":
                        self.thrown_hit(b, e, part)
                    else:
                        self.damage(e, part, b.dmg, b.vx)
                        self.sparks(b.x, b.y, 3, "plasma")
                    alive = False
                    break
                if self.node_hit(b.x, b.y, b.dmg if b.kind != "stasis" else 0):
                    if b.kind == "throw" and b.pcs and b.pcs.kind == "canister":
                        self.blast(b.x, b.y)
                    alive = False
                    break
                if b.kind != "stasis":
                    for br in self.barrels:
                        if br.state == 0 and abs(b.x - br.x) < 8 and 0 < br.y - b.y < 24:
                            self.pop_barrel(br)
                            alive = False
                            break
                    if not alive:
                        break
                if b.life <= 0 or b.y > GY + 6 or b.y < 0:
                    if b.kind == "stasis":
                        self.stasis_field(b.x, min(b.y, GY - 10))
                    elif b.kind == "throw":
                        self.land_thrown(b)
                    alive = False
                    break
            if alive:
                keep.append(b)
        self.bolts = keep

    def thrown_hit(self, b, e, part):
        pk = b.pcs.kind
        if pk == "canister":
            self.blast(b.x, b.y)
        else:
            dmg = THROW_DMG.get(pk, 30)
            if part in ("torso", "armor", "weak") and e.t in ("slasher", "leaper"):
                e.hp -= 200
                self.kill(e, b.vx)
            else:
                self.damage(e, part, dmg, b.vx)
            self.sparks(b.x, b.y, 6)
            self.land_thrown(b)

    def land_thrown(self, b):
        if b.pcs.kind != "canister":
            self.throw_piece(b.pcs.kind, b.pcs.pal, b.x, b.y, b.vx * 0.2, -1.0)
        else:
            self.blast(b.x, b.y)

    def stasis_field(self, x, y):
        self.stasis_fx = 40
        self.fx.append(Obj(kind="stasis", x=x, y=y, age=0))
        for e in self.mobs:
            if not e.dead and abs(e.x - x) < 46 and abs((e.y - 20) - y) < 70:
                e.slow = 150 if e.boss or e.t == "hunter" else 230
        if self.boss and self.boss.kind in ("levi", "hive") and abs(x - self.boss.x0) < 200:
            self.boss.slow = 150

    def update_debris(self):
        for d in self.debris:
            d.age += 1
            if d is self.I.kin:
                continue            # a piece held by Kinesis is carried, not falling
            if not d.ground:
                d.vy += 0.03 if self.in_zg(d.x) else 0.22
                d.x += d.vx
                d.y += d.vy
                d.rot = (d.rot + (1 if d.spin > 0 else -1) * (1 if random.random() < abs(d.spin) else 0)) & 7
                if d.y >= d.gy and d.vy > 0:
                    d.y = d.gy
                    d.ground = True
                    d.rot = random.choice((0, 4))
                    self.sparks(d.x, d.y, 2, "blood")
        # the ground keeps only a few pieces, the oldest go first
        if len(self.debris) > 30:
            gone = [d for d in self.debris if d.ground][:len(self.debris) - 30]
            self.debris = [d for d in self.debris if d not in gone]

    def update_items(self):
        I = self.I
        for it in list(self.items):
            it.age += 1
            if it.vy or it.y < it.gy:
                it.vy += 0.2
                it.y += it.vy
                it.x += it.vx
                if it.y >= it.gy:
                    it.y, it.vy = it.gy, 0.0
            if abs(it.x - I.x) < 10 and I.act != "die":
                self.collect(it)
                self.items.remove(it)

    def collect(self, it):
        I = self.I
        k = it.kind
        if k == "credit":
            v = random.choice((50, 100, 100, 200))
            self.credits += v
            self.add_score(v // 2, it.x, it.y - 12, "+%d" % v, "yellow")
        elif k == "plasma":
            I.res["pc"] = min(60, I.res["pc"] + 8)
            self.popup("PLASMA", int(it.x - self.cam) - 18, int(it.y) - 18, "cyan")
        elif k == "pulse":
            I.res["pulse"] = min(150, I.res["pulse"] + 30)
            self.popup("PULSE", int(it.x - self.cam) - 15, int(it.y) - 18, "amber")
        elif k == "health":
            I.packs = min(4, I.packs + 1)
            self.popup("HEALTH PACK", int(it.x - self.cam) - 33, int(it.y) - 18, "green")
        elif k == "node":
            self.nodes += 1
            self.add_score(100)
            self.popup("POWER NODE", int(it.x - self.cam) - 30, int(it.y) - 18, "cyan")
        elif k == "stasis":
            I.stasis = min(100.0, I.stasis + 40)
            self.popup("STASIS", int(it.x - self.cam) - 18, int(it.y) - 18, "cyan")

    def drop_loot(self, x, y, n=1, ammo_hint=False):
        for i in range(n):
            k = pick_loot(ammo_hint or (self.I.res["pc"] + self.I.mag["pc"] < 8))
            self.items.append(mkitem(k, x + random.uniform(-6, 6), y - 10.0, float(GY + random.randint(2, 8)),
                                     vx=random.uniform(-1, 1), vy=-2.6))

    def update_fx(self):
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += -0.01 if self.in_zg(p[0]) else 0.18
            p[4] -= 1
        for p in self.parts:
            if p[1] >= GY + 8 and p[5] in ("blood", "gore") and random.random() < 0.3:
                self.stains.append((int(p[0]), GY + random.randint(3, 8), random.randint(1, 4)))
        del self.stains[:-70]
        self.parts = [p for p in self.parts if p[4] > 0 and p[1] < GY + 8]
        for f in self.fx:
            f.age += 1
        self.fx = [f for f in self.fx if f.age < (14 if f.kind == "boom" else 26)]
        for q in self.pops:
            q.life -= 1
            q.y -= 0.3
        self.pops = [q for q in self.pops if q.life > 0]
        for c in list(self.corpses):
            if c.y < c.gy - 0.5:
                c.fv += 0.3
                c.y = min(c.gy, c.y + c.fv)
                if c.y >= c.gy and c.fall:
                    self.blood(c.x, c.y, 12, big=True)
                    self.corpses.remove(c)

    # ---- Isaac: actions ---------------------------------------------------------------------------------------------------
    def mag_max(self, w):
        return (10 + 2 * self.upg["clip"]) if w == "pc" else 30

    def bounds(self):
        if self.boss:
            return self.arena_l, self.arena_r - (140 if self.boss.kind in ("levi", "hive") else 20)
        if self.exit_walk:
            return self.arena_l, self.arena_r + 80
        # the airlock gates the arena; once Isaac is past it there is nothing to hold him back
        return 24.0, (float(self.arena_r) if (self.doorf[0] >= 3.5 or self.I.x > self.L - 20) else self.L - 30.0)

    def go(self, d, run=False, face=None):
        I = self.I
        lo, hi = self.bounds()
        sp = (3.3 if run else 1.9) * (0.72 if self.in_zg(I.x) else 1.0)
        if face is not None and face != d:
            sp = min(sp, 2.3)
            I.back = 1.0
        else:
            I.back = 0.0
        I.face = face if face is not None else d
        I.x = max(lo, min(hi, I.x + d * sp))
        I.moving = 2 if run else 1
        I.walkdir = d
        I.anim += sp * 0.1 * (-1 if I.back else 1)

    def begin(self, act):
        I = self.I
        I.act, I.at = act, 0.0

    def tgt_alive(self, t):
        if t is None:
            return False
        if hasattr(t, "alive"):
            return t.alive
        return (not t.dead) and t in self.mobs

    def muzzle(self, pose=None, face=None):
        """Screen-space (virtual pixels, world x) muzzle position for the current or a given pose."""
        I = self.I
        name, idx = pose or self.iso_pose()
        spr, meta = B["isaac"][name][idx]
        face = face or I.face
        hx, hy = meta["hand"]
        w = meta["wang"]
        e = 2 if w is None else min(range(5), key=lambda i: abs(ELEV[i] - w))
        wspr, grip, muz = B["weapons"][I.weapon][e]
        ix, iy = int(I.x) - 24, int(I.y) - 58
        if face > 0:
            hs = (ix + hx, iy + hy)
            tl = (hs[0] - grip[0], hs[1] - grip[1])
            return tl[0] + muz[0], tl[1] + muz[1]
        hs = (ix + 48 - hx, iy + hy)
        tl = (hs[0] - (40 - grip[0]), hs[1] - grip[1])
        return tl[0] + 40 - muz[0], tl[1] + muz[1]

    def lead_point(self, e, part):
        ax, ay = aim_point(e, part)
        sp = e.spd * e.ts
        d = abs(ax - self.I.x)
        if sp:
            ax += (1 if self.I.x > ax else -1) * sp * d / 12.0 * (1 if e.t != "lurker" else 0)
        return ax, ay

    def target_point(self):
        I = self.I
        t = I.target
        if hasattr(t, "alive"):
            return t.x, t.y
        return self.lead_point(t, I.part)

    def set_elev(self):
        I = self.I
        ax, ay = self.target_point()
        I.face = 1 if ax > I.x else -1
        mx, my = self.muzzle(("aim0", 0))
        ang = math.degrees(atan2(my - ay, max(8.0, abs(ax - mx))))
        I.elev = ELEV[min(range(5), key=lambda i: abs(ELEV[i] - ang))]

    def begin_aim(self, e, part):
        I = self.I
        I.target, I.part = e, part
        I.act, I.at = "aim", 0.0
        I.aimt = 4 if I.weapon == "pc" else 6
        I.burst = 0
        self.set_elev()

    def fire(self):
        I = self.I
        w = I.weapon
        ax, ay = self.target_point()
        I.face = 1 if ax > I.x else -1
        self.set_elev()
        mx, my = self.muzzle(("shot%d" % I.elev, 0))
        dx, dy = ax - mx, ay - my
        d = hypot(dx, dy) or 1.0
        spd = 12.0 if w == "pc" else 10.0
        dmg = 10 + 2 * self.upg["dmg"] if w == "pc" else 6
        self.bolts.append(Obj(kind="plasma" if w == "pc" else "pulse", hostile=False, x=mx, y=my, vx=spd * dx / d, vy=spd * dy / d,
                              dmg=dmg, life=45, pcs=None))
        I.mag[w] -= 1
        I.lastshot = self.t
        I.cool = 11 if w == "pc" else 20
        self.fx.append(Obj(kind="flash", x=mx, y=my, age=0))
        self.sparks(mx, my, 2, "plasma")

    def do_stomp(self):
        I = self.I
        sx = I.x + I.face * 13
        hit = False
        for c in self.crates + self.lockers:
            if c.state == 0 and abs(c.x - sx) < 16:
                c.state = 1
                self.drop_loot(c.x, c.y, 1 + (random.random() < 0.5))
                self.sparks(c.x, c.y - 8, 8, "grey")
                self.add_score(25)
                hit = True
        for h in self.humans:
            if not h.looted and abs(h.x - sx) < 20 and h.infect is None:
                h.looted = True
                self.drop_loot(h.x, h.y, 1 + (random.random() < 0.6))
                self.blood(h.x, h.y - 4, 8)
                hit = True
        for c in self.corpses:
            if c.loot and abs(c.x - sx) < 22:
                c.loot = False
                self.drop_loot(c.x, c.y, 1 + (random.random() < 0.5), True)
                self.blood(c.x, c.y - 4, 8)
                self.add_score(40, c.x, c.y - 12, "+40")
                hit = True
        for e in list(self.mobs):
            if e.dead or abs(e.x - sx) > 20 or abs(e.y - I.y) > 12:
                continue
            if e.t == "spawn":
                self.kill(e)
                hit = True
            elif e.t in ("slasher", "hunter") and "legF" not in e.p and "legB" not in e.p:
                e.hp -= 30
                e.stun = max(e.stun, 10)
                self.blood(e.x, e.y - 8, 8)
                hit = True
                if e.hp <= 0:
                    self.kill(e)
            elif e.t == "leaper" and e.slow > 0:
                for part in list(e.p)[:1]:
                    self.sever(e, part, 1.5 * I.face)
                hit = True
        if hit:
            self.shake = max(self.shake, 3)
        self.sparks(sx, I.y, 4, "grey")

    def do_melee(self):
        I = self.I
        for e in self.mobs:
            if e.dead or e.t == "exploder" or e.boss:
                continue
            if abs(e.x - (I.x + I.face * 14)) < 22:
                e.stun = max(e.stun, 22)
                e.x += I.face * 12
                e.hp -= 8
                self.blood(e.x, e.y - 30, 4, I.face * 1.5)
                if e.hp <= 0:
                    self.kill(e)
        I.mcool = 50

    def do_use(self):
        I = self.I
        if I.packs > 0:
            I.packs -= 1
            heal = 60 if I.hp < 0.35 * self.base_hp else 40
            I.hp = min(float(self.base_hp), I.hp + heal)
            self.popup("+HEALTH", int(I.x - self.cam) - 21, int(I.y) - 66, "green")
            self.sparks(I.x, I.y - 30, 8, "green")

    def start_stasis(self):
        I = self.I
        I.stasis -= 34
        I.stcool = 90
        I.act, I.at = "stasis", 0.0
        t = I.target
        if t is not None and not hasattr(t, "alive"):
            ax, ay = self.lead_point(t, I.part or "torso") if I.part else (t.x, t.y - 24)
        elif t is not None:
            ax, ay = t.x, t.y
        else:
            ax, ay = I.x + I.face * 80, I.y - 30
        I.face = 1 if ax > I.x else -1

    def fire_stasis(self):
        I = self.I
        mx, my = self.muzzle(("stasis", 0))
        t = I.target
        tx = t.x if t is not None else I.x + I.face * 80
        ty = (t.y - 28) if (t is not None and not hasattr(t, "alive")) else (t.y if t is not None else I.y - 30)
        d = hypot(tx - mx, ty - my) or 1.0
        self.bolts.append(Obj(kind="stasis", hostile=False, x=mx, y=my, vx=6 * (tx - mx) / d, vy=6 * (ty - my) / d, dmg=0, life=40,
                              pcs=None))

    def begin_kin(self, obj, target):
        I = self.I
        I.act, I.at = "kin", 0.0
        I.kin = obj
        I.target = target
        I.part = None
        obj.ground = False
        obj.vx = obj.vy = 0.0
        I.kincool = 150

    def update_kin(self):
        I = self.I
        o = I.kin
        if o is None or o not in self.debris:
            I.act = "free"
            I.kin = None
            return
        hx, hy = I.x + I.face * 16, I.y - 40
        t = I.at
        if t < 14:
            o.x += (hx - o.x) * 0.22
            o.y += (hy - o.y) * 0.22
        else:
            o.x, o.y = hx + sin(self.t * 0.4) * 1.0, hy + cos(self.t * 0.5) * 1.5
        o.rot = (o.rot + (1 if t % 4 == 0 else 0)) & 7
        if random.random() < 0.5:
            self.parts.append([o.x + random.uniform(-4, 4), o.y + random.uniform(-4, 4), 0, -0.2, 8, "cyan", 1])
        if t >= 26:
            tg = I.target
            if tg is None or not self.tgt_alive(tg):
                o.vy = 0.0
                I.act, I.kin = "free", None
                return
            if hasattr(tg, "alive"):
                ax, ay = tg.x, tg.y
            else:
                ax, ay = aim_point(tg, "torso")
            I.face = 1 if ax > I.x else -1
            d = hypot(ax - o.x, ay - o.y) or 1.0
            self.debris.remove(o)
            self.bolts.append(Obj(kind="throw", hostile=False, x=o.x, y=o.y, vx=8.5 * (ax - o.x) / d, vy=8.5 * (ay - o.y) / d,
                                  dmg=THROW_DMG.get(o.kind, 30), life=50,
                                  pcs=Obj(kind=o.kind, pal=o.pal, spr=o.pcs[o.rot])))
            I.act, I.at, I.kin = "free", 0.0, None
            self.popup("KINESIS", int(I.x - self.cam) - 21, int(I.y) - 66, "cyan", 22)

    def begin_bench(self, st):
        I = self.I
        st.used = True
        I.act, I.at = "bench", 0.0
        I.bench = st

    def do_bench(self):
        I = self.I
        st = I.bench
        if st.kind == "save":
            self.cp = st.x
            self.popup("SAVED", int(I.x - self.cam) - 15, int(I.y) - 66, "cyan", 50)
            return
        msgs = []
        order = ("dmg", "clip", "hp", "dmg", "clip", "hp", "dmg", "dmg")
        for k in order:
            if self.nodes <= 0:
                break
            if k == "dmg" and self.upg["dmg"] < 4:
                self.upg["dmg"] += 1
            elif k == "clip" and self.upg["clip"] < 3:
                self.upg["clip"] += 1
                I.mag["pc"] += 2
            elif k == "hp" and self.upg["hp"] < 3:
                self.upg["hp"] += 1
                self.base_hp = 100 + 10 * self.upg["hp"]
                I.hp = min(float(self.base_hp), I.hp + 10)
            else:
                continue
            self.nodes -= 1
            msgs.append({"dmg": "DAMAGE UP", "clip": "CLIP UP", "hp": "HEALTH UP"}[k])
        if self.credits >= 1500 and self.upg["dmg"] < 4:
            self.credits -= 1500
            self.upg["dmg"] += 1
            msgs.append("DAMAGE UP")
        if self.credits >= 1500 and self.upg["hp"] < 3:
            self.credits -= 1500
            self.upg["hp"] += 1
            self.base_hp = 100 + 10 * self.upg["hp"]
            msgs.append("RIG UP")
        if self.credits >= 600 and I.packs < 4:
            self.credits -= 600
            I.packs += 1
            msgs.append("BOUGHT PACK")
        if self.credits >= 300 and I.res["pc"] < 20:
            self.credits -= 300
            I.res["pc"] += 12
            msgs.append("BOUGHT AMMO")
        for i, m in enumerate(msgs[:3]):
            self.popup(m, int(I.x - self.cam) - len(m) * 3, int(I.y) - 70 - i * 10, "cyan", 60)

    # ---- Isaac: the bot ---------------------------------------------------------------------------------------------
    PRIO = dict(slasher=1.0, leaper=0.55, lurker=0.8, infector=0.35, exploder=0.3, pregnant=1.1, spawn=3.0, brute=1.0, hunter=0.9)
    MIN_D = dict(slasher=44, leaper=34, lurker=0, infector=30, exploder=70, pregnant=80, spawn=20, brute=125, hunter=70)

    def pick_part(self, e):
        p = e.p
        t = e.t
        if t == "slasher":
            # legs first to slow it while it is still far; once it is close, take the arms (both gone kills it)
            far = abs(e.x - self.I.x) > 70
            for k in (("legF", "legB", "armF", "armB") if far else ("armF", "armB", "legF", "legB")):
                if k in p:
                    return k
            return "torso"
        if t == "leaper":
            if "armF" in p and "armB" in p:
                return "armF"
            if "tail" in p:
                return "tail"
            for k in ("armF", "armB"):
                if k in p:
                    return k
            return "torso"
        if t == "lurker":
            for k in ("t0", "t1", "t2"):
                if k in p:
                    return k
            return "torso"
        if t == "exploder":
            return "bulb" if "bulb" in p else "torso"
        if t == "pregnant":
            for k in ("s0", "s1", "s2"):
                if k in p:
                    return k
            return "torso"
        if t == "brute":
            return "weak" if (e.st == "stun" or e.slow > 0) else None
        if t == "hunter":
            for k in ("armF", "armB", "legF", "legB"):
                if k in p:
                    return k
            return "torso"
        return "torso"

    def danger_x(self):
        """x positions of telegraphed boss slams that are about to land."""
        b = self.boss
        if not b:
            return ()
        return [w.tx for w in b.tents if w.phase == "wind" and w.tl < 40]

    def think(self):
        I = self.I
        thr = [e for e in self.mobs if not e.dead and not e.fake and e.st != "attached"]
        thr.sort(key=lambda e: abs(e.x - I.x))
        near = thr[0] if thr else None
        d0 = abs(near.x - I.x) if near else 999
        base_hp = self.base_hp
        I.moving = 0
        I.back = 0.0
        # 1. step out of a telegraphed boss slam
        for dxp in self.danger_x():
            if abs(I.x - dxp) < 40:
                lo, hi = self.bounds()
                # a fixed escape point on the side Isaac is already on (or the other side when cornered): a rule that
                # re-decided the direction every tick made him jitter inside the slam zone
                if I.x <= dxp:
                    goal = dxp - 46 if dxp - 46 >= lo else dxp + 46
                else:
                    goal = dxp + 46 if dxp + 46 <= hi else dxp - 46
                d = 1 if goal > I.x else -1
                self.go(d, True, d)
                return
        # 2. heal
        if I.packs and ((I.hp < 0.42 * base_hp and d0 > 46) or (I.hp < 0.25 * base_hp and d0 > 24)):
            self.begin("use")
            return
        # 3. reload
        w = I.weapon
        if I.mag[w] <= 0 and I.res[w] > 0 and d0 > 28:
            self.begin("reload")
            return
        if I.mag[w] < self.mag_max(w) * 0.5 and I.res[w] > 0 and d0 > 200:
            self.begin("reload")
            return
        # 4. weapon choice: the Pulse Rifle only for crowds
        crowd = sum(1 for e in thr if abs(e.x - I.x) < 150 and e.t != "spawn")
        want = "pulse" if (crowd >= 3 and I.mag["pulse"] + I.res["pulse"] > 0) else "pc"
        if I.mag[want] + I.res[want] == 0:
            want = "pc" if want == "pulse" else "pulse"
        if want != w and I.mag[want] + I.res[want] > 0:
            I.weapon = want
            w = want
        # 5. close quarters: stomp crawlers and swarmers, shove everything else off
        I.mcool = max(0, I.mcool - 1)
        for e in thr:
            dd = abs(e.x - I.x)
            crawler = e.t in ("slasher", "hunter") and "legF" not in e.p and "legB" not in e.p
            if dd < 18 and (e.t == "spawn" or crawler) and abs(e.y - I.y) < 12:
                I.face = 1 if e.x > I.x else -1
                self.begin("stomp")
                return
        if near and d0 < 21 and I.mcool <= 0 and near.t not in ("spawn", "exploder", "infector", "lurker") and not near.boss \
                and near.slow <= 0 and near.st in ("attack", "walk", "charge"):
            I.face = 1 if near.x > I.x else -1
            self.begin("melee")
            return
        # 6. stasis on what is fast or heavy
        I.stcool = max(0, I.stcool - 1)
        if I.stasis >= 34 and I.stcool <= 0:
            for e in thr:
                dd = abs(e.x - I.x)
                if e.slow > 0 or dd > 150 or dd < 24:
                    continue
                need = (e.t in ("brute", "hunter") and dd < 140) or (e.t == "leaper" and dd < 125 and "armF" in e.p and "armB" in e.p) \
                    or (e.t == "slasher" and e.st in ("roar", "charge") and dd < 130) or (crowd >= 3 and dd < 100)
                if need:
                    I.target, I.part = e, None
                    self.start_stasis()
                    return
        # 7. kinesis: throw a severed blade (or a barrel at a group) while nothing is in reach
        I.kincool = max(0, I.kincool - 1)
        if I.kincool <= 0 and (d0 > 45):
            tg = self.kin_target(thr)
            if tg is not None:
                obj, tgt = tg
                I.face = 1 if tgt.x > I.x else -1
                self.begin_kin(obj, tgt)
                return
        # 8. shoot: weakest limb of the most urgent target
        cands = []
        for e in thr:
            dd = abs(e.x - I.x)
            if dd > 200 or abs(e.x - self.cam - VW / 2) > VW / 2 + 40:
                continue
            part = self.pick_part(e)
            if part is None:
                continue
            pr = self.PRIO.get(e.t, 1.0)
            if e.t == "exploder" and dd < 55:
                pr = 4.0
            cands.append((dd * pr, e, part))
        if self.boss:
            for n in self.boss.nodes:
                if n.alive and n.shootable():
                    cands.append((abs(n.x - I.x) * 0.35 + 5, n, "node"))
        cands.sort(key=lambda c: c[0])
        have_ammo = I.mag[w] > 0
        if cands and have_ammo and I.cool <= 0:
            _, e, part = cands[0]
            self.begin_aim(e, part)
            return
        # 9. keep distance from what is dangerous at melee range
        if near:
            md = self.MIN_D.get(near.t, 60)
            if near.slow > 0:
                md *= 0.5
            if d0 < md:
                lo, hi = self.bounds()
                away = -1 if near.x > I.x else 1
                if (away < 0 and I.x > lo + 14) or (away > 0 and I.x < hi - 14):
                    self.go(away, run=d0 < md * 0.6 or near.t in ("brute", "exploder"), face=-away)
                    return
            if d0 < 200 and (have_ammo or I.res[w] > 0) and cands:
                I.face = 1 if near.x > I.x else -1
                return                       # wait for the weapon to cool down, ready to fire
        if self.boss and (cands or self.boss.kind in ("levi", "hive")):
            self.boss_position()
            return
        self.loot_or_walk(thr)

    def kin_target(self, thr):
        I = self.I
        cand = None
        if self.boss and self.boss.mouth:
            for d in self.debris:
                if d.kind == "canister" and d.ground and abs(d.x - I.x) < 110:
                    cand = (d, self.boss.bulb)
                    break
            return cand
        if not thr:
            return None
        tgt = None
        for e in thr:
            dd = abs(e.x - I.x)
            if 55 < dd < 190 and e.t not in ("infector", "lurker") and not e.boss:
                tgt = e
                break
        if tgt is None:
            return None
        for b in self.barrels:
            if b.state == 0 and abs(b.x - I.x) < 90 and abs(tgt.x - b.x) > 40:
                grp = sum(1 for e in thr if abs(e.x - tgt.x) < 50)
                if grp >= 2:
                    b.state = 2
                    d = Obj(kind="canister", pal="pale", pcs=B["piece"][("canister", "pale")], x=b.x, y=b.y - 8, vx=0.0, vy=0.0, rot=0,
                            spin=0.0, ground=True, gy=b.y, age=0, throwable=True)
                    self.debris.append(d)
                    return (d, tgt)
        for d in self.debris:
            if d.ground and d.throwable and d.kind in ("blade", "claw", "tail") and abs(d.x - I.x) < 80 and random.random() < 0.5:
                if abs(tgt.x - I.x) > 60:
                    return (d, tgt)
        return None

    def boss_position(self):
        """Stay where the boss can be shot but its slams cannot reach."""
        I = self.I
        b = self.boss
        lo, hi = self.bounds()
        goal = min(hi, max(lo, b.safe_x))
        if abs(I.x - goal) > 6:
            d = 1 if goal > I.x else -1
            self.go(d, abs(I.x - goal) > 40, 1)
        else:
            I.face = 1

    def loot_or_walk(self, thr):
        I = self.I
        goal = None
        lo, hi = self.bounds()
        # pick-ups first, then containers to stomp, then the stations. Only what Isaac can actually walk to counts:
        # once the arena door shuts, loot left in the corridor behind it would otherwise pin him against the wall forever
        best = 100
        for it in self.items:
            dd = abs(it.x - I.x)
            if dd < best and lo <= it.x <= hi:
                best, goal = dd, ("walk", it.x)
        if goal is None and not self.boss:
            for st in self.stations:
                if not st.used and abs(st.x - I.x) < 90 and lo <= st.x <= hi:
                    if abs(st.x - I.x) < 8:
                        if not thr or abs(thr[0].x - I.x) > 160:
                            self.begin_bench(st)
                            return
                    goal = ("walk", st.x)
                    break
        if goal is None and not self.boss:
            best = 55
            for c in self.crates + self.lockers:
                if c.state == 0 and abs(c.x - I.x) < best and lo <= c.x <= hi:
                    best, goal = abs(c.x - I.x), ("stomp", c.x)
            for h in self.humans:
                if not h.looted and h.infect is None and abs(h.x - I.x) < best and lo <= h.x <= hi:
                    best, goal = abs(h.x - I.x), ("stomp", h.x)
            for c in self.corpses:
                if c.loot and abs(c.x - I.x) < best and lo <= c.x <= hi:
                    best, goal = abs(c.x - I.x), ("stomp", c.x)
        if goal is not None:
            kind, gx = goal
            if kind == "stomp":
                dd = gx - I.x
                if abs(dd) < 11:
                    I.face = 1 if dd > 0 else -1
                    self.begin("stomp")
                    return
                self.go(1 if dd > 0 else -1, False)
                return
            if abs(gx - I.x) > 4:
                self.go(1 if gx > I.x else -1, abs(gx - I.x) > 60)
                return
        self.walk_goal()

    def walk_goal(self):
        I = self.I
        if self.boss:
            self.boss_position()
            return
        if self.exit_walk:
            self.go(1, True)
            return
        gx = self.L + 142.0
        hi = self.bounds()[1]
        if I.x < min(gx, hi):
            self.go(1, True)
        else:
            I.face = 1

    # ---- Isaac: per-tick update ------------------------------------------------------------------------------------
    def update_isaac(self):
        I = self.I
        I.at += 1
        if I.inv > 0:
            I.inv -= 1
        if I.cool > 0:
            I.cool -= 1
        I.stasis = min(100.0, I.stasis + 0.04)
        if abs(I.vx) > 0.15:
            lo, hi = self.bounds()
            I.x = max(lo, min(hi, I.x + I.vx))
            I.vx *= 0.8
        else:
            I.vx = 0.0
        zoff = GY - I.y + ((18.0 if self.in_zg(I.x) else 0.0) - (GY - I.y)) * 0.07
        I.y = GY - zoff - (2.5 * sin(self.t * 0.06) if zoff > 6 else 0.0)
        a = I.act
        if a == "free":
            self.think()
        elif a == "aim":
            if not self.tgt_alive(I.target) or I.target is None:
                I.act = "free"
                return
            self.set_elev()
            if I.at >= I.aimt:
                if I.mag[I.weapon] > 0:
                    self.fire()
                    I.act, I.at = "recoil", 0.0
                    I.burst = 2 if I.weapon == "pulse" else 0
                else:
                    I.act = "free"
        elif a == "recoil":
            if I.at >= 3:
                if I.burst > 0 and I.mag[I.weapon] > 0 and self.tgt_alive(I.target):
                    I.burst -= 1
                    self.fire()
                    I.at = 0.0
                else:
                    I.act = "free"
        elif a == "reload":
            if I.at >= 30:
                w = I.weapon
                need = self.mag_max(w) - I.mag[w]
                take = min(need, I.res[w])
                I.mag[w] += take
                I.res[w] -= take
                I.act = "free"
        elif a == "stomp":
            if I.at == 5:
                self.do_stomp()
            if I.at >= 12:
                I.act = "free"
        elif a == "melee":
            if I.at == 5:
                self.do_melee()
            if I.at >= 11:
                I.act = "free"
        elif a == "kin":
            self.update_kin()
        elif a == "stasis":
            if I.at == 6:
                self.fire_stasis()
            if I.at >= 14:
                I.act = "free"
        elif a == "use":
            if I.at == 14:
                self.do_use()
            if I.at >= 26:
                I.act = "free"
        elif a == "bench":
            if I.at == 14:
                self.do_bench()
            if I.at >= (44 if I.bench.kind == "bench" else 26):
                I.act = "free"
        elif a == "hurt":
            if I.at >= 10:
                I.act = "free"

    def iso_pose(self):
        I = self.I
        a = I.act
        if a == "aim":
            return ("aim%d" % I.elev, 0)
        if a == "recoil":
            return ("shot%d" % I.elev, 0)
        if a == "reload":
            return ("reload", min(2, int(I.at / 15)))
        if a == "stomp":
            return ("stomp", 0 if I.at < 4 else (1 if I.at < 8 else 2))
        if a == "melee":
            return ("melee", 0 if I.at < 4 else (1 if I.at < 7 else 2))
        if a == "kin":
            return ("kinesis", 0)
        if a == "stasis":
            return ("stasis", 0)
        if a == "use":
            return ("use", int(I.at / 7) & 1)
        if a == "bench":
            return ("bench", 0)
        if a == "hurt":
            return ("hurt", 0 if I.at < 5 else 1)
        if a == "die":
            return ("die", 0)
        if I.moving:
            if I.moving == 2 and not I.back:
                return ("run", int(I.anim * 1.6) % 6)
            return ("walk", int(I.anim * 1.6) % 6)
        return ("idle", int(I.at / 14) & 1)

    # ---- bosses --------------------------------------------------------------------------------------------------------
    def start_boss(self):
        ci = self.ci
        c0 = self.cam0
        kind = ("brute", "hunter", "brute2", "levi", "hunter2", "hive")[ci]
        b = Obj(kind=kind, t=0, nodes=[], tents=[], mouth=False, safe_x=c0 + 130.0, slow=0, mob=None, intro=0, roar=0, dying=0,
                cycle=0, x0=c0 + 340, bulb=None)
        self.boss = b
        self.alert = True
        self.warn = 100
        for i in range(3):
            self.items.append(mkitem("plasma", c0 + 60 + i * 55, GY + 5.0, GY + 5.0))
        self.items.append(mkitem("health", c0 + 40, GY + 4.0, GY + 4.0))
        if kind in ("brute", "brute2"):
            m = self.spawn("brute", "dark", self.arena_r + 40, boss=True, face=-1)
            m.hp = m.hpmax = 150.0 if b.kind == "brute" else 170.0
            m.st, m.tm = "roar", 0.0
            b.mob = m
        elif kind in ("hunter", "hunter2"):
            b.intro = 90
            self.blackout = 80
        elif kind == "levi":
            for i, ix in enumerate((c0 + 220, c0 + 285, c0 + 350, c0 + 415)):
                w = Obj(ix=float(ix), x=float(ix), phase="idle", tl=random.uniform(40, 110) + i * 25, tx=float(ix), node=None, alive=True, pose=0)
                n = Node(x=ix, y=100.0, r=7.5, hp=45.0, hpmax=45.0, alive=True, score=400, open=False, hitf=0,
                         gate=(lambda w=w: w.alive and w.phase in ("idle", "stuck", "recover")))
                w.node = n
                b.tents.append(w)
                b.nodes.append(n)
            b.bulb = Node(x=c0 + 400.0, y=180.0, r=11, hp=90.0, hpmax=90.0, alive=True, score=2500, open=True, hitf=0,
                          gate=(lambda b=b: b.mouth))
            b.nodes.append(b.bulb)
        elif kind == "hive":
            for i, ix in enumerate((c0 + 250, c0 + 330, c0 + 410)):
                b.tents.append(Obj(ix=float(ix), x=float(ix), phase="idle", tl=random.uniform(60, 130) + i * 30, tx=float(ix), node=None,
                                   alive=True, pose=0))
            for lx, ly in ((40, 150), (80, 168), (120, 172), (160, 160), (185, 138)):
                b.nodes.append(Node(x=c0 + 270.0 + lx, y=52.0 + ly, r=8, hp=36.0, hpmax=36.0, alive=True, score=600, open=False,
                                    hitf=0, gate=(lambda: True)))
            for lx, ly in ((66, 128), (90, 136)):
                b.nodes.append(Node(x=c0 + 270.0 + lx, y=52.0 + ly, r=8, hp=40.0, hpmax=40.0, alive=True, score=900, open=True,
                                    hitf=0, gate=(lambda b=b: b.roar > 0 or not any(n.alive for n in b.nodes[:5]))))

    def boss_frac(self):
        b = self.boss
        if b is None:
            return 0.0
        if b.mob is not None:
            return max(0.0, b.mob.hp / b.mob.hpmax)
        if not b.nodes:
            return 1.0
        return sum(max(0.0, n.hp) for n in b.nodes) / sum(n.hpmax for n in b.nodes)

    def update_boss(self):
        b = self.boss
        I = self.I
        b.t += 1
        c0 = self.cam0
        if b.slow > 0:
            b.slow -= 1
        dt = 0.12 if b.slow > 0 else 1.0
        # arenas resupply a dry player: running out of ammo mid-fight would stall the whole game
        if b.t % 300 == 150 and I.mag["pc"] + I.res["pc"] < 14:
            for i in range(2):
                self.items.append(mkitem("plasma", c0 + 50 + i * 40 + random.random() * 20, GY - 20.0, GY + 5.0))
        if b.intro:
            b.intro -= 1
            if b.intro == 50:
                self.shake = 12
            if b.intro == 20:
                self.shake = 14
                self.flash = 2
                m = self.spawn("hunter", "pale", self.arena_r - 60, GY - 150, boss=True, face=-1)
                m.hp = m.hpmax = 260.0
                m.air, m.vy, m.vx = True, 1.0, -0.6
                m.gy = float(GY)
                b.mob = m
            return
        if b.kind in ("brute2", "hunter2"):
            b.cycle += 1
            if b.cycle % 330 == 0:
                if b.kind == "brute2" and sum(1 for e in self.mobs if e.t == "exploder") < 2:
                    self.spawn("exploder", "pale", self.arena_r + 30, face=-1)
                if b.kind == "hunter2" and sum(1 for e in self.mobs if e.pal == "grey") < 3:
                    self.spawn("slasher", "grey", self.arena_r + 30, face=-1)
                    self.spawn("slasher", "grey", self.arena_l - 30, face=1)
        if b.mob is not None:
            m = b.mob
            if m.dead:
                self.boss_dying()
            return
        if b.kind not in ("levi", "hive"):
            return
        attackers = sum(1 for w in b.tents if w.alive and w.phase in ("wind", "slam"))
        for i, w in enumerate(b.tents):
            if not w.alive:
                continue
            w.tl -= dt
            ph = w.phase
            if ph == "idle":
                w.pose = (int(b.t / 20) + i) & 1
                if w.tl <= 0 and attackers < (2 if b.kind == "levi" else 1) and b.roar <= 0:
                    w.phase, w.tl = "wind", 30.0
                    lo, hi = c0 + 24.0, c0 + 450.0
                    w.tx = max(lo, min(hi, I.x + random.uniform(-10, 10)))
                    attackers += 1
            elif ph == "wind":
                w.pose = 2
                w.x += (w.tx - w.x) * 0.2
                if w.tl <= 0:
                    w.phase, w.tl = "slam", 6.0
            elif ph == "slam":
                w.pose = 3
                w.x = w.tx
                if w.tl <= 0:
                    self.shake = 10
                    self.sparks(w.tx, GY + 4, 14, "grey")
                    if abs(I.x - w.tx) < 24:
                        self.hurt(28 if b.kind == "levi" else 32, w.tx, "tentacle", 5)
                    w.phase, w.tl = "stuck", 38.0
            elif ph == "stuck":
                w.pose = 3
                if w.tl <= 0:
                    w.phase, w.tl = "recover", 22.0
            elif ph == "recover":
                w.pose = 2 if w.tl > 10 else 0
                w.x += (w.ix - w.x) * 0.2
                if w.tl <= 0:
                    w.phase, w.tl = "idle", random.uniform(70, 150)
            if w.node is not None:
                nx, ny = B["ctent_node"][w.pose]
                w.node.x, w.node.y = w.x - 22 + nx, 10 + ny
                if not w.node.alive and w.alive:
                    w.alive = False
                    self.blood(w.x, 120, 24, big=True)
                    self.shake = 10
        if b.kind == "levi":
            if not b.mouth and not any(w.alive for w in b.tents):
                b.mouth = True
                self.popup("MOUTH OPEN", 200, 120, "red", 70)
            if b.mouth and b.bulb.alive:
                if b.t % 130 == 0 and sum(1 for d in self.debris if d.kind == "canister") < 2:
                    x = c0 + random.uniform(40, 120)
                    self.debris.append(Obj(kind="canister", pal="pale", pcs=B["piece"][("canister", "pale")], x=x, y=GY - 30.0, vx=0.0,
                                           vy=0.0, rot=0, spin=0.0, ground=False, gy=GY + 4, age=0, throwable=True))
            if b.bulb is not None and not b.bulb.alive:
                self.boss_dying()
        else:
            b.cycle += 1
            if b.cycle % 250 == 0:
                b.roar = 90
                n = sum(1 for e in self.mobs if not e.dead)
                if n < 3:
                    kind = random.choice(("lurker", "leaper", "slasher"))
                    e = self.spawn(kind, "enh" if kind != "lurker" else "pale", c0 + 330, GY if kind != "lurker" else 38, face=-1)
                    if kind == "lurker":
                        e.air = True
                    self.shake = 6
            if b.roar > 0:
                b.roar -= 1
            if all(not n.alive for n in b.nodes):
                self.boss_dying()

    def boss_dying(self):
        b = self.boss
        b.dying += 1
        if b.dying == 1:
            self.add_score((1500, 3000, 2000, 5000, 4000, 8000)[self.ci], self.cam0 + 240, 100, "BOSS DOWN", "red")
            self.shake = 14
        if b.dying % 6 == 0 and b.kind in ("levi", "hive"):
            self.fx.append(Obj(kind="boom", x=self.cam0 + random.uniform(300, 470), y=random.uniform(90, 220), age=0))
            self.shake = 8
            self.blood(self.cam0 + random.uniform(300, 470), random.uniform(120, 220), 8, big=True)
        lim = 70 if b.kind in ("levi", "hive") else 25
        if b.dying >= lim:
            self.boss = None
            self.boss_done = True
            self.alert = False
            self.exit_walk = True
            for e in self.mobs:
                self.blood(e.x, e.y - 20, 8, big=True)
            self.mobs = []

    # ---- world triggers and flow -----------------------------------------------------------------------------------------
    def nearest_vent(self, x, kind):
        c = [v for v in self.vents if v.kind == kind and not v.open and abs(v.x - x) < 160]
        return min(c, key=lambda v: abs(v.x - x)) if c else None

    def trigger(self, bt):
        I = self.I
        if bt.kind in ("vent", "ceil"):
            v = self.nearest_vent(I.x + 170, "wall" if bt.kind == "vent" else "ceil")
            if v is None:
                bt.kind = "wave"
            else:
                v.open = True
                self.shake = 9
                self.flash = 2
                self.throw_piece("grate", "pale", v.x, v.y, random.uniform(-1.5, 1.5) + (-1 if v.x > I.x else 1), -2.0, False)
                self.sparks(v.x, v.y, 10, "grey")
                for i, (t, pal) in enumerate(bt.mobs):
                    e = self.spawn(t, pal, v.x + i * 10, v.y, face=1 if I.x > v.x else -1)
                    e.air, e.vy, e.vx = True, -1.0 - i * 0.4, (1.3 if I.x > v.x else -1.3) * (1 + 0.4 * i)
                    if t == "lurker":
                        e.air, e.y = True, 38.0
                    if bt.kind == "ceil" and t != "lurker":
                        e.y, e.vy, e.vx = 36.0, 0.0, 0.0
                return
        if bt.kind == "corpse":
            c = [h for h in self.humans if h.x > I.x + 150 and not h.looted and h.infect is None]
            if c:
                h = min(c, key=lambda h: h.x)
                h.rise = True
                return
            bt.kind = "wave"
        if bt.kind in ("wave", "rear"):
            side = 1 if bt.kind == "wave" else -1
            for i, (t, pal) in enumerate(bt.mobs):
                x = (self.cam + VW - 40 + i * 36) if side > 0 else (self.cam + 40 - i * 36)
                x = max(8.0, x)
                e = self.spawn(t, pal, x, face=-side)
                if t == "lurker":
                    e.y, e.air = 38.0, True

    def update_triggers(self):
        I = self.I
        # the next ambush waits until the previous one is mostly dealt with, so they never stack into a massacre
        busy = sum(1 for e in self.mobs if not e.dead and not e.boss) > 1
        for bt in self.beats:
            if not bt.done and I.x >= bt.x and not busy:
                bt.done = True
                self.trigger(bt)
                break
        for h in list(self.humans):
            if h.rise and abs(h.x - I.x) < 80:
                self.humans.remove(h)
                e = self.spawn("slasher", "pale", h.x, h.y, face=-1 if I.x < h.x else 1)
                e.st, e.tm, e.stun = "rise", 0.0, 6
                self.shake = 7
                self.flash = 2
                self.blood(h.x, h.y - 6, 8)
        # airlock to the arena opens when Isaac approaches and closes behind him
        want0 = self.L - 70 < I.x < self.L + 118 and not self.boss and not self.boss_done
        self.doorf[0] = max(0.0, min(4.0, self.doorf[0] + (0.15 if want0 else -0.15)))
        self.doorf[1] = max(0.0, min(4.0, self.doorf[1] + (0.15 if self.boss_done else -0.15)))
        if not self.boss and not self.boss_done and I.x > self.L + 130:
            self.start_boss()

    def update_light(self):
        self.flick_next -= 1
        if self.flick_next <= 0:
            self.flick = random.randint(6, 16)
            self.flick_next = random.randint(150, 420)
        if self.flick > 0:
            self.flick -= 1
        if self.blackout > 0:
            self.blackout -= 1
        if self.flash > 0:
            self.flash -= 1
        if self.warn > 0:
            self.warn -= 1
        if self.fade > 0:
            self.fade -= 1
        if self.stasis_fx > 0:
            self.stasis_fx -= 1
        if self.shake > 0:
            self.shake -= 1

    def update_cam(self):
        I = self.I
        if I.moving and not I.back:
            I.look += (I.walkdir - I.look) * 0.03
        if self.boss or self.exit_walk:
            tgt = float(self.cam0)
        else:
            tgt = I.x - 190 + I.look * 70
        tgt = max(0.0, min(float(self.cam0), tgt))
        self.cam += (tgt - self.cam) * 0.1

    def respawn(self):
        I = self.I
        I.hp = 0.7 * self.base_hp
        I.act, I.at = "free", 0.0
        I.inv = 60
        self.fade = 20
        I.x = float(self.arena_l + 10) if (self.boss or self.exit_walk) else self.cp
        I.packs = max(I.packs, 1)
        I.res["pc"] += 10
        I.mag["pc"] = min(self.mag_max("pc"), I.res["pc"])
        I.res["pc"] -= I.mag["pc"]
        I.stasis = max(I.stasis, 70.0)
        I.target = I.kin = None
        keep = [e for e in self.mobs if e.boss or (e.t == "hunter")]
        self.mobs = keep
        self.bolts = [b for b in self.bolts if not b.hostile]
        if not self.boss:
            self.beats = [b for b in self.beats if not (b.done and b.x < I.x + 400) or b.x > I.x]
        self.cam = max(0.0, min(float(self.cam0), I.x - 190))

    def update_play(self):
        I = self.I
        self.t += 1
        self.chap_t += 1
        self.update_light()
        if I.act == "die":
            I.at += 1
            if I.at >= 100:
                self.respawn()
            self.update_fx()
            self.update_debris()
            self.update_bolts()
            return
        if I.act != "free":
            I.moving = 0
        self.update_isaac()
        self.update_triggers()
        for e in list(self.mobs):
            if e in self.mobs:
                self.update_mob(e)
        if self.boss:
            self.update_boss()
        self.update_bolts()
        self.update_debris()
        self.update_items()
        self.update_fx()
        self.update_cam()
        if I.x > self.maxx + 6 or self.boss:
            self.maxx = max(self.maxx, I.x)
            self.last_prog = self.chap_t
        self.watchdog()

    def watchdog(self):
        """A bot must never deadlock: when a chapter drags on, thin out the enemies and finally skip the fight."""
        idle = self.chap_t - self.last_prog
        if self.boss is None and idle > 900:
            self.mobs = [e for e in self.mobs if e.boss]
            self.items = []
            if self.exit_walk:
                self.I.x = float(self.arena_r + 40)
            self.last_prog = self.chap_t
        if self.boss is not None and self.boss.t > 1800 and self.boss.t % 300 == 0:
            # a drawn-out boss fight weakens the boss step by step instead of ending abruptly
            b = self.boss
            if b.mob is not None:
                b.mob.hp *= 0.5
            for n in b.nodes:
                n.hp *= 0.5
        if self.chap_t > 6500 and self.boss is None and not self.boss_done:
            self.I.x = float(self.L + 135)

    # ---- chapter end and game flow ---------------------------------------------------------------------------------------
    def present_black(self, rows):
        for y in rows:
            PREV[y] = None
            o = y * 4 * S
            fb[o:o + 4 * S] = bytes(4 * S)

    def draw_card(self):
        c = self.cfg
        clear()
        draw_text_centered("CHAPTER %d" % (self.ci + 1), 380, "L", COLOR_RED)
        draw_text_centered(c["name"], 500, "L", COLOR_WHITE)
        draw_text_centered(c["sub"], 620, "S", COLOR_YELLOW)
        if self.ci == 0:
            draw_text_centered("USG ISHIMURA - AEGIS VII", 760, "S", COLOR_CYAN)
        for y in range(VH):
            PREV[y] = None

    def step_card(self):
        if not self.card_drawn:
            self.draw_card()
            self.card_drawn = True
        self.mt += 1
        if self.mt > 62:
            self.mode = "play"
            self.mt = 0
            self.hudkey = None

    def step_chend(self):
        self.mt += 1
        if self.mt == 1:
            self.cleared = 1000 + 500 * self.ci + max(0, (4800 - self.chap_t) // 6)
            self.add_score(self.cleared)
        if self.mt <= 20:
            self.present_black(range((self.mt - 1) * 14, min(VH, self.mt * 14)))
        elif self.mt == 21:
            clear()
            draw_text_centered("CHAPTER %d CLEAR" % (self.ci + 1), 400, "L", COLOR_GREEN)
            draw_text_centered("BONUS %d" % self.cleared, 520, "S", COLOR_YELLOW)
            draw_text_centered("SCORE %d" % self.score, 600, "S", COLOR_WHITE)
            ks = "  ".join("%s %d" % (KILL_NAMES[k], n) for k, n in sorted(self.kills.items(), key=lambda kv: -kv[1])[:4])
            draw_text_centered(ks, 720, "S", COLOR_CYAN)
            draw_text_centered("LIMBS CUT %d  CREDITS %d" % (self.limbs, self.credits), 800, "S", COLOR_RED)
        elif self.mt > 52:
            if self.ci >= len(CH_LEN) - 1:
                self.finish()
            else:
                self.start_chapter(self.ci + 1)

    def finish(self):
        clear()
        self.end = EndScreen()
        self.end.start(self.score, "ISHIMURA CLEARED" if self.ci >= len(CH_LEN) - 1 and self.boss_done else "TRANSMISSION LOST")

    def step(self):
        if self.end is not None:
            return self.end.tick()
        if self.t >= CAP_TICKS - 3:
            self.finish()
            return False
        if self.mode == "card":
            self.t += 1
            self.step_card()
            return False
        if self.mode == "chend":
            self.t += 1
            self.step_chend()
            return False
        self.update_play()
        if self.exit_walk and self.boss is None and self.I.x > self.arena_r + 36:
            self.mode, self.mt = "chend", 0
            return False
        self.render()
        return False

    # ---- rendering -----------------------------------------------------------------------------------------------------------
    def build_hud(self):
        key = (self.score, self.credits, self.nodes, self.I.packs, self.ci)
        if key == self.hudkey:
            return
        self.hudkey = key
        bg = COL["panel"] * VW
        rows = [bytearray(bg) for _ in range(HUD_H)]
        rows[HUD_H - 1] = bytearray(COL["dgrey"] * VW)
        saved = FR[:HUD_H]
        FR[:HUD_H] = rows
        text("CH%d %s" % (self.ci + 1, self.cfg["name"]), 4, 2, "a")
        s = "SCORE %06d" % self.score
        text(s, VW // 2 - len(s) * 3, 2, "w")
        cr = "CR %d" % self.credits
        text(cr, VW - 170, 2, "a")
        text("N%d" % self.nodes, VW - 100, 2, "c")
        text("H%d" % self.I.packs, VW - 70, 2, "g")
        text("X%d" % self.limbs, VW - 40, 2, "r")
        self.hud = [bytes(r) for r in FR[:HUD_H]]
        FR[:HUD_H] = saved

    def draw_isaac(self, camx):
        I = self.I
        fl = I.face < 0
        name, idx = self.iso_pose() if I.act != "die" else ("die", 0)
        ix, iy = int(I.x) - camx - 24, int(I.y) - 58
        if I.act == "die":
            self.draw_isaac_death(camx)
            return
        if I.inv > 0 and (self.t & 2):
            return
        spr, meta = B["isaac"][name][idx]
        draw(spr, ix, iy, fl)
        w = meta["wang"]
        hx, hy = meta["hand"]
        if w is not None:
            e = min(range(5), key=lambda i: abs(ELEV[i] - w))
            wspr, grip, muz = B["weapons"][I.weapon][e]
            if not fl:
                draw(wspr, ix + int(hx - grip[0]), iy + int(hy - grip[1]))
            else:
                draw(wspr, ix + 48 - int(hx) - (40 - int(grip[0])), iy + int(hy - grip[1]), True)
        # spine: the health meter on his back, segments drain from the bottom up and change colour
        (tx_, ty_), (bx_, by_) = meta["spine"]
        n = 7
        lit = int(math.ceil(max(0.0, I.hp) / self.base_hp * n - 0.01))
        frac = I.hp / self.base_hp
        ck = COL["cyan"] if frac > 0.6 else (COL["amber"] if frac > 0.3 else COL["red"])
        blink = frac <= 0.3 and (self.t & 4)
        for k in range(n):
            t = (k + 0.5) / n
            sx = tx_ + (bx_ - tx_) * t
            sy = ty_ + (by_ - ty_) * t
            on = (n - 1 - k) < lit
            c = ck if (on and not blink) else COL["dgrey"]
            px_ = ix + int(48 - sx) - 1 if fl else ix + int(sx) - 1
            rect(px_ - 0, iy + int(sy) - 1, 2, 3, c)
        # stasis charge pips beside the spine
        pips = int(I.stasis // 33.4)
        for k in range(3):
            sx = (ix + 48 - int(tx_) + 3) if fl else (ix + int(tx_) + 3)
            rect(sx - 1, iy + int(ty_) + 1 + k * 4, 2, 3, COL["blue"] if k < pips else COL["dgrey"])
        # ammo hologram near the weapon while it is raised
        if I.act in ("aim", "recoil", "reload") or self.t - I.lastshot < 70:
            w_ = I.weapon
            s = "%02d/%02d" % (I.mag[w_], I.res[w_] % 100)
            mx_ = int(self.muzzle()[0]) - camx if self.muzzle() else ix
            hx2 = ix + (10 if not fl else -8)
            hy2 = iy - 12
            rect(hx2 - 2, hy2 - 2, len(s) * 6 + 3, 12, COL["dgrey"])
            hline(hx2 - 2, hx2 + len(s) * 6 + 1, hy2 - 2, COL["cyan"])
            hline(hx2 - 2, hx2 + len(s) * 6 + 1, hy2 + 9, COL["cyan"])
            text(s, hx2, hy2 - 1, "c" if I.mag[w_] > 2 else "r")

    def draw_isaac_death(self, camx):
        I = self.I
        x = int(I.x) - camx
        t = I.at
        fl = I.face < 0
        ix, iy = x - 24, int(I.y) - 58
        if I.deadtype == "bitten":
            if t < 14:
                spr, _ = B["isaac"]["die"][0]
            elif t < 24:
                spr, _ = B["isaac"]["headless"][0]
            else:
                spr = B["isaac_lying"]["headless"]
        else:
            if t < 10:
                spr, _ = B["isaac"]["die"][0]
            elif t < 20:
                spr, _ = B["isaac"]["die"][1]
            else:
                spr = B["isaac_lying"]["body"]
        if spr is B["isaac_lying"]["headless"] or spr is B["isaac_lying"]["body"]:
            draw(spr, x - 30, int(I.y) + 4 - 48, fl)
            if t % 3 == 0 and t < 60:
                self.parts.append([I.x + random.uniform(-14, 14), I.y - 2, 0.0, -0.3, 10, "blood", 1])
        else:
            draw(spr, ix, iy, fl)
        if t == 14 and I.deadtype == "bitten":
            self.blood(I.x, I.y - 44, 22, big=True)
            self.fx.append(Obj(kind="ihead", x=I.x, y=I.y - 46, vx=-I.face * 2.2, vy=-3.0, rot=0, age=0))

    def render(self):
        I = self.I
        t = self.t
        sh = self.shake
        camx = int(self.cam) + (random.randint(-sh, sh) if sh else 0)
        camx = max(0, camx)
        env = self.env
        wo = ((camx >> 1) % WALL_TILE) * 8
        fo = (camx % FLOOR_TILE) * 8
        # lighting state: dark corridor with Isaac's lit pool; stasis, alerts, flicker and flashes change the base
        base, cone = "dark", "lit"
        use_cone = True
        if self.stasis_fx > 0:
            base, cone = "bluedark", "bluelit"
        elif self.blackout > 0:
            use_cone = False
        elif self.flash > 0:
            base = "lit"
        elif self.alert and ((t // 22) & 1):
            base = "reddark"
        elif self.flick > 0:
            r = t & 3
            if r == 0:
                use_cone = False
            elif r == 2:
                base = "lit"
        wb = env["wall_" + base][2]
        fb_ = env["floor_" + base][2]
        FR[:WALL_H] = [bytearray(wb[o:o + RB]) for o in range(wo, wo + WALL_H * WALL_STRIDE, WALL_STRIDE)]
        FR[WALL_H:] = [bytearray(fb_[o:o + RB]) for o in range(fo, fo + (VH - WALL_H) * FLOOR_STRIDE, FLOOR_STRIDE)]
        if use_cone:
            cx = int(I.x) - camx + I.face * 48
            # two nested pools: a dim wide one (soft edge) and the bright core, both cut from other lighting variants
            for hwt, var in ((HWM, "mid" if cone == "lit" else None), (HW, cone)):
                if var is None:
                    continue
                cw = env["wall_" + var][2]
                cf = env["floor_" + var][2]
                for y in range(36, VH):
                    hw = hwt[y]
                    if hw:
                        a = cx - hw
                        b = cx + hw
                        if a < 0:
                            a = 0
                        if b > VW:
                            b = VW
                        if b > a:
                            if y < WALL_H:
                                o = y * WALL_STRIDE + wo
                                FR[y][a * 8:b * 8] = cw[o + a * 8:o + b * 8]
                            else:
                                o = (y - WALL_H) * FLOOR_STRIDE + fo
                                FR[y][a * 8:b * 8] = cf[o + a * 8:o + b * 8]
        # windows: the view outside is nearly fixed on screen, so frames slide over it (parallax)
        sp = env["space"]
        sw, sh_, spx_, _ = sp
        sp_stride = sw * 8
        woff = (camx >> 1) % WALL_TILE
        for wi, (x0, y0, ww, wh) in enumerate(env["wins"]):
            for k in (0, 1):
                sx = x0 - woff + k * WALL_TILE
                lx, rx = max(0, sx), min(VW, sx + ww)
                if rx > lx:
                    so = ((camx // 12 + lx + wi * 37) % env["space_w"]) * 8
                    n8 = (rx - lx) * 8
                    for y in range(y0, y0 + wh):
                        r0 = (y - y0) * sp_stride + so
                        FR[y][lx * 8:rx * 8] = spx_[r0:r0 + n8]
        self.draw_world(camx)
        for k in range(22):
            mx = (DUST[k][0] - int(camx * DUST[k][2]) + (t * DUST[k][3]) // 8) % VW
            rect(mx, DUST[k][1] + int(sin(t * 0.03 + k) * 4), 1, 1, COL["dgrey"] if k & 1 else COL["grey"])
        if not self.boss and not self.exit_walk:
            pil = B["props"]["pillar"]
            px = 700 - (int(camx * 1.55) % 700) - 40
            if -22 < px < VW:
                draw(pil, px, 0)
        if self.in_zg(I.x) and (t & 16):
            text_c("ZERO G", VW // 2, HUD_H + 3, "c")
        if self.warn > 0:
            if (t & 8):
                text_c("WARNING", VW // 2, 70, "r")
                text_c(BOSS_NAMES[self.ci], VW // 2, 82, "a")
        if I.act == "die" and I.at > 56:
            for y in range(min(VH, int((I.at - 56) * 7))):
                FR[y] = bytearray(BLACKROW)
            if I.at > 66:
                text_c("YOU ARE DEAD", VW // 2, 120, "r")
        elif self.fade > 0:
            for y in range(VH - 1, VH - 1 - min(VH, self.fade * 14), -1):
                FR[y] = bytearray(BLACKROW)
        # HUD last, and the boss health bar under it
        self.build_hud()
        FR[:HUD_H] = self.hud
        if self.boss:
            f = self.boss_frac()
            text("BOSS", 4, HUD_H + 3, "r")
            rect(30, HUD_H + 4, 200, 5, COL["dgrey"])
            rect(31, HUD_H + 5, int(198 * f), 3, COL["red"])
            text(BOSS_NAMES[self.ci], 236, HUD_H + 3, "a")
        # present only the rows that changed
        for y in range(VH):
            r = FR[y]
            if r != PREV[y]:
                o = y * 4 * S
                fb[o:o + S] = r
                fb[o + S:o + 2 * S] = r
                fb[o + 2 * S:o + 3 * S] = r
                fb[o + 3 * S:o + 4 * S] = r
                PREV[y] = r

    def draw_world(self, camx):
        I = self.I
        t = self.t
        P = B["props"]
        for sx_, sy_, sw_ in self.stains:
            xx = sx_ - camx
            if 0 <= xx < VW - 8:
                hline(xx - sw_, xx + sw_, sy_, COL["dred"])
                hline(xx - sw_ + 1, xx + sw_ - 1, sy_ + 1, COL["gore"])
        # ---- backdrop props (behind the actors)
        for v in self.vents:
            sx = int(v.x) - camx
            if -20 < sx < VW + 20:
                draw(P["vent"][1 if v.open else 0], sx - 15, int(v.y) - 11)
        for d in (0, 1):
            x = (self.L if d == 0 else self.arena_r + 12) - camx
            fidx = int(self.doorf[d])
            if -50 < x < VW + 50:
                draw(P["door"][fidx], x - 23, GY + 6 - 82)
        for st in self.stations:
            sx = int(st.x) - camx
            if -30 < sx < VW + 30:
                if st.kind == "bench":
                    draw(P["bench"], sx - 22, GY + 8 - 52)
                else:
                    draw(P["save"][(t // 12) & 1], sx - 13, GY + 8 - 50)
        if self.ci == 5:
            mk_ = B["marker"]
            draw(mk_, 40 - camx + self.cam0 - 0, 118)
        for j in self.jets:
            sx = int(j.x) - camx
            if -20 < sx < VW + 20:
                ph = (t + j.ph) % 90
                if ph < 50:
                    for i in range(3):
                        age = ph - i * 6
                        if age >= 0:
                            sp = P["steam"][min(4, age // 10)][(t >> 1) & 1]
                            draw(sp, sx - sp[0] // 2 + (i - 1) * 3 + int(sin(age * 0.2) * 2), int(j.y) - int(age * 0.7) - sp[1] // 2)
        if self.boss and self.boss.kind in ("levi", "hive"):
            self.draw_boss_back(camx)
        # ---- actors, depth-sorted by their ground row
        dl = []
        for c in self.crates:
            dl.append((c.y, 0, c))
        for c in self.lockers:
            dl.append((c.y + 9, 1, c))
        for b in self.barrels:
            if b.state == 0:
                dl.append((b.y, 2, b))
        for h in self.humans:
            dl.append((h.y - 3, 3, h))
        for c in self.corpses:
            dl.append((c.y - 3, 4, c))
        for d in self.debris:
            dl.append((d.y if not d.ground else d.y - 2, 5, d))
        for e in self.mobs:
            dl.append((e.y if e.t != "lurker" else 300, 6, e))
        dl.append((I.y, 7, I))
        dl.sort(key=lambda a: a[0])
        for _, kind, o in dl:
            sx = int(o.x) - camx
            if sx < -70 or sx > VW + 70:
                continue
            if kind == 0:
                s = P["crate"][o.state]
                draw(s, sx - 15, int(o.y) + 3 - s[1])
            elif kind == 1:
                s = P["locker"][o.state]
                draw(s, sx - 8, int(o.y) + 9 - s[1])
            elif kind == 2:
                draw(P["barrel"], sx - 8, int(o.y) + 3 - 22)
            elif kind == 3:
                draw(P["corpse"][o.kind], sx - 22, int(o.y) - 10)
                if o.infect is not None:
                    self.sparks(o.x, o.y - 6, 1, "green")
            elif kind == 4:
                s, fl, lx, ty = sprite_of(o)
                draw(s, lx - camx, ty, fl)
            elif kind == 5:
                s = o.pcs[o.rot]
                if o.ground:
                    draw(s, sx - s[0] // 2, int(o.y) + 1 - s[1])
                else:
                    draw(s, sx - s[0] // 2, int(o.y) - s[1] // 2)
            elif kind == 6:
                s, fl, lx, ty = sprite_of(o)
                draw(s, lx - camx, ty, fl)
                if o.slow > 0:
                    r = P["ring"][2 if o.t in ("slasher", "exploder", "pregnant") else (3 if o.t in ("brute", "hunter") else 1)]
                    draw(r, sx - r[0] // 2, int(o.y) - r[1] // 2 - (20 if o.t != "spawn" else 3))
                    if t & 3 == 0:
                        self.parts.append([o.x + random.uniform(-10, 10), o.y - random.uniform(5, 45), 0, -0.2, 9, "ice", 1])
            else:
                self.draw_isaac(camx)
        for it in self.items:
            sx = int(it.x) - camx
            if -10 < sx < VW + 10:
                s = P["pickup"][it.kind]
                draw(s, sx - 7, int(it.y) - 14 + int(2 * sin(it.age * 0.15 + it.x)))
                if it.age % 20 == 0:
                    self.parts.append([it.x + random.uniform(-5, 5), it.y - random.uniform(4, 14), 0, -0.3, 8, "white", 1])
        if self.boss and self.boss.kind in ("levi", "hive"):
            self.draw_boss_front(camx)
        # ---- projectiles and effects
        for b in self.bolts:
            sx = int(b.x) - camx
            if b.kind == "plasma":
                for k in range(5):
                    xx = int(sx - b.vx * k * 0.5)
                    yy = int(b.y - b.vy * k * 0.5)
                    h = 9 - k
                    rect(xx - 1, yy - h // 2, 2, h, COL["white"] if k < 2 else (COL["plasma"] if k < 4 else COL["blue"]))
            elif b.kind == "pulse":
                for k in range(4):
                    rect(int(sx - b.vx * k * 0.5), int(b.y - b.vy * k * 0.5), 2, 2, COL["amber"] if k < 2 else COL["orange"])
            elif b.kind == "barb":
                for k in range(4):
                    rect(int(sx - b.vx * k * 0.6), int(b.y - b.vy * k * 0.6), 2, 2, COL["red"] if k < 2 else COL["amber"])
            elif b.kind == "stasis":
                r = P["ring"][0]
                draw(r, sx - r[0] // 2, int(b.y) - r[1] // 2)
            elif b.kind == "throw":
                s = b.pcs.spr
                draw(s, sx - s[0] // 2, int(b.y) - s[1] // 2)
        # aiming laser: the cutter's three blue sight lamps form a line at the target
        if I.act == "aim" and self.tgt_alive(I.target):
            ax, ay = self.target_point()
            sx = int(ax) - camx
            for k in (-4, 0, 4):
                rect(sx - 1, int(ay) + k - 1, 2, 2, COL["cyan"])
            rect(sx, int(ay) - 4, 1, 9, COL["blue"])
        for p in self.parts:
            sx = int(p[0]) - camx
            if 0 <= sx < VW - 2:
                rect(sx, int(p[1]), p[6], p[6], COL[p[5]])
        for f in self.fx:
            sx = int(f.x) - camx
            if f.kind == "boom":
                s = P["flash"][min(3, f.age // 3)]
                draw(s, sx - s[0] // 2, int(f.y) - s[1] // 2)
            elif f.kind == "flash":
                if f.age < 2:
                    s = P["flash"][1]
                    draw(s, sx - s[0] // 2, int(f.y) - s[1] // 2)
            elif f.kind == "stasis":
                r = P["ring"][min(4, f.age // 5)]
                draw(r, sx - r[0] // 2, int(f.y) - r[1] // 2)
            elif f.kind == "ihead":
                f.vy += 0.25
                f.x += f.vx
                f.y = min(f.y + f.vy, GY)
                f.rot = (f.rot + 1) & 7
                s = B["isaac_pieces"]["head"][f.rot]
                draw(s, sx - s[0] // 2, int(f.y) - s[1] // 2)
        for q in self.pops:
            text(q.s, q.x, int(q.y), q.ck)
        # boss telegraphs on the floor
        if self.boss:
            for w in self.boss.tents:
                if w.alive and w.phase == "wind":
                    sx = int(w.tx) - camx
                    c = COL["red"] if (t & 2) else COL["dred"]
                    hline(sx - 20, sx + 20, GY + 6, c)
                    hline(sx - 14, sx + 14, GY + 7, c)

    def draw_boss_back(self, camx):
        b = self.boss
        c0 = self.cam0
        if b.kind == "levi":
            draw(B["levi_body"], c0 + 330 - camx, 52)
        else:
            draw(B["hive_body"], c0 + 270 - camx, 52)

    def draw_boss_front(self, camx):
        b = self.boss
        for w in b.tents:
            if not w.alive:
                continue
            s = B["ctent"][(w.pose, 1 if w.node is not None and w.node.alive else 0)]
            draw(s, int(w.x) - 22 - camx, 10)
        t = self.t
        for n in b.nodes:
            if n.alive and (n.shootable() or b.kind == "hive"):
                glow = B["bulb"][8 if n.r >= 10 else 6]
                if b.kind == "hive" or n is b.bulb:
                    draw(glow, int(n.x) - glow[0] // 2 - camx, int(n.y) - glow[1] // 2 + int(sin(t * 0.2 + n.x)))
        if b.kind == "hive" and b.roar > 0 and (self.t & 4):
            text("ROAR", int(b.x0) - camx - 12, 40, "r")


def make():
    random.seed()
    g = Game()
    return g.step
