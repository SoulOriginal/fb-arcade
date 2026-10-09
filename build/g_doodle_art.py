# Drawing helpers and sprite painters for the Doodle Jump reproduction (build time only, needs PIL).
# Sprites are painted at 8 px per logical unit and shrunk to 2 px per unit: the 4x supersampling gives smooth pencil
# outlines that a direct 2 px/unit draw cannot.
import math, random
from PIL import Image, ImageDraw, ImageChops, ImageFont
from buildlib import rgb565, BOLD

SS, U = 4, 2
K = SS * U
INK = (36, 36, 30)
PAPER = (250, 246, 216)
GRID = (186, 216, 214)
rng = random.Random(2009)


class Pic:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * K, h * K), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def _wob(self, pts, amp, closed=True):
        # Hand-drawn wobble: split long edges and push every point a little, so outlines are never perfectly straight.
        out = []
        n = len(pts)
        for i in range(n if closed else n - 1):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / 3))
            for s in range(steps):
                t = s / steps
                out.append((x0 + (x1 - x0) * t + rng.uniform(-amp, amp), y0 + (y1 - y0) * t + rng.uniform(-amp, amp)))
        if not closed:
            out.append(pts[-1])
        return out

    def poly(self, pts, fill=None, ink=INK, width=1.5, amp=0.25, closed=True):
        pts = self._wob(pts, amp, closed)
        px = [(x * K, y * K) for x, y in pts]
        if fill is not None and closed:
            self.d.polygon(px, fill=fill)
        if ink is not None:
            if closed:
                px = px + [px[0]]
            self.d.line(px, fill=ink, width=int(width * K), joint="curve")
            r = width * K / 2
            for x, y in px[::2]:
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=ink)

    def blob(self, cx, cy, rx, ry, fill=None, ink=INK, width=1.5, amp=0.25, rot=0.0):
        pts = []
        for i in range(28):
            a = 2 * math.pi * i / 28
            x, y = rx * math.cos(a), ry * math.sin(a)
            pts.append((cx + x * math.cos(rot) - y * math.sin(rot), cy + x * math.sin(rot) + y * math.cos(rot)))
        self.poly(pts, fill, ink, width, amp)

    def line(self, pts, color=INK, width=1.5, amp=0.15):
        self.poly(pts, None, color, width, amp, closed=False)

    def dot(self, x, y, r, color=INK):
        self.d.ellipse(((x - r) * K, (y - r) * K, (x + r) * K, (y + r) * K), fill=color)

    def rrect(self, x0, y0, x1, y1, r, fill=None, ink=INK, width=1.5, amp=0.2):
        pts = []
        for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            for k in range(7):
                a = math.radians(a0 + 15 * k)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.poly(pts, fill, ink, width, amp)


def smooth(pts, rounds=2):
    # Chaikin corner cutting: turns a handful of control points into a soft closed outline.
    for _ in range(rounds):
        out = []
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        pts = out
    return pts


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def final(im_or_pic):
    im = im_or_pic.im if isinstance(im_or_pic, Pic) else im_or_pic
    return im.resize((im.width // SS, im.height // SS), Image.LANCZOS)


def spans(im):
    # RGBA image -> (w, h, rows); a row is a list of (x offset, RGB565 bytes) opaque runs. The game copies runs
    # straight into its frame buffer, which gives transparency without a per-pixel loop at run time.
    w, h = im.size
    px = im.load()
    rows = []
    for y in range(h):
        runs, x = [], 0
        while x < w:
            if px[x, y][3] >= 110:
                x0, buf = x, bytearray()
                while x < w and px[x, y][3] >= 110:
                    r, g, b, _ = px[x, y]
                    buf += rgb565(r, g, b).to_bytes(2, "little")
                    x += 1
                runs.append((x0, bytes(buf)))
            else:
                x += 1
        rows.append(runs)
    return (w, h, rows)


def sprite(p):
    return spans(final(p))


# ---- Doodler ----------------------------------------------------------------------------------------------------------
DW, DH, FEET, BODYX = 72, 84, 80, 27     # canvas, feet baseline, x of the body centre when facing right
GREEN = (186, 200, 40)         # olive-yellow body of the original Doodler
STRIPE = (110, 164, 58)
DINK = (22, 22, 18)            # the original outlines are near-black and thick
BX0, BX1, BH = 10, 44, 43      # body is one dome-topped block: head and torso are the same shape


def doodler(leg, snout_deg=0, hat=None, pack=None):
    p = Pic(DW, DH)
    bt = FEET - leg                     # body bottom
    top = bt - BH
    # four thin black legs, evenly spaced, each ending in a small foot that points forward
    for i, f in enumerate((0.12, 0.38, 0.64, 0.90)):
        x = BX0 + (BX1 - BX0) * f
        bend = 2.5 if leg < 8 else 0.0
        p.line([(x, bt - 2), (x - bend, bt + leg * 0.5), (x, FEET - 1.2)], DINK, 2.3, 0.08)
        p.line([(x - 0.5, FEET - 1.0), (x + 3.8, FEET - 1.0)], DINK, 2.3, 0.08)
    if pack:
        p.rrect(3, bt - 28, 13, bt - 4, 3, (200, 70, 60), DINK, 1.4)
        p.rrect(5, bt - 24, 11, bt - 16, 2, (235, 200, 70), None)
        p.line([(3.5, bt - 10), (12.5, bt - 10)], DINK, 1.2)
        fl = 14 if pack == 1 else 22
        p.poly([(5, bt - 4), (11, bt - 4), (8, bt - 4 + fl)], (255, 150, 30), DINK, 1.0)
        p.poly([(6.5, bt - 4), (9.5, bt - 4), (8, bt - 4 + fl * 0.6)], (255, 230, 90), None)
    r = 14
    pts = [(BX0, top + r)]
    for k in range(1, 8):                       # domed head: both top corners are big arcs, the head leans forward a touch
        a = math.pi + k * math.pi / 14
        pts.append((BX0 + r + 1 + (r + 1) * math.cos(a), top + r + (r) * math.sin(a)))
    for k in range(0, 8):
        a = -math.pi / 2 + k * math.pi / 14
        pts.append((BX1 - r + r * math.cos(a), top + r + r * math.sin(a)))
    pts += [(BX1, bt - 3), (BX1 - 3, bt), (BX0 + 3, bt - 0.5), (BX0 + 0.5, bt - 3)]
    p.poly(pts, GREEN, DINK, 2.4, 0.18)
    # belly stripes: a black line on top, then two green bands separated by another black line
    sz = 18.0
    y0 = bt - sz
    for y1, y2 in ((y0 + 1.5, y0 + 7.6), (y0 + 9.6, bt - 1.8)):
        p.poly([(BX0 + 1.2, y1), (BX1 - 0.8, y1), (BX1 - 0.8, y2), (BX0 + 1.2, y2)], STRIPE, None, 0, 0.0)
    p.line([(BX0, y0), (BX1, y0)], DINK, 1.7, 0.1)
    p.line([(BX0, y0 + 8.6), (BX1, y0 + 8.6)], DINK, 1.7, 0.1)
    # horn-shaped snout flaring into an oval opening; rotated about its base for the shooting pose
    a = math.radians(snout_deg)
    sy = top + 17.0
    bx = BX1 - (4.0 if snout_deg else 0.0)
    by = sy - (4.0 if snout_deg else 0.0)
    ux, uy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)

    def at(t, w):
        return (bx + ux * t + nx * w, by + uy * t + ny * w)
    horn = [at(-1, -5.6), at(8, -4.4), at(15, -4.2), at(20, -6.8), at(21.5, -6.8), at(21.5, 6.8), at(20, 6.8), at(15, 4.2), at(8, 4.4),
            at(-1, 5.6)]
    p.poly(horn, GREEN, DINK, 2.4, 0.12)
    ox, oy = at(21.0, 0)
    p.blob(ox, oy, 2.4, 6.2, (96, 112, 20), DINK, 1.3, 0.05, rot=a)
    # two tiny black eyes just above the snout base
    ex, ey = BX1 - 6.5, top + 11.5
    for dx in (0.0, 6.0):
        p.blob(ex - dx, ey, 1.2, 2.1, DINK, None, 0, 0.0)
    if hat:
        hx, hy = (BX0 + BX1) / 2 - 2, top - 1
        p.poly([(hx - 8, hy + 3), (hx - 6, hy - 5), (hx + 6, hy - 6), (hx + 9, hy + 3)], (70, 130, 220), DINK, 1.5)
        p.poly([(hx - 3, hy - 5.5), (hx + 1.5, hy - 5.8), (hx + 3, hy + 3), (hx - 5, hy + 3)], (240, 90, 70), None)
        p.line([(hx - 8, hy + 3), (hx + 9, hy + 3)], DINK, 1.5)
        p.line([(hx, hy - 6), (hx, hy - 11)], DINK, 1.4)
        bw = 13 if hat == 1 else 5
        p.blob(hx, hy - 11.5, bw, 1.8, (230, 230, 236), DINK, 1.2, 0.1)
    return p.im


def flip(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


def spin_frames(base, n=12, scale=1.0):
    # Rotation frames around the body centre on a square canvas: the trampoline flip and the death tumble.
    side = 104
    sq = Image.new("RGBA", (side * K, side * K), (0, 0, 0, 0))
    cx, cy = BODYX + 2, FEET - 10 - 18
    sq.paste(base, ((side // 2 - cx) * K, (side // 2 - cy) * K), base)
    out = []
    for i in range(n):
        r = sq.rotate(-360 * i / n, resample=Image.BICUBIC)
        if scale != 1.0:
            r = r.resize((int(r.width * scale), int(r.height * scale)), Image.LANCZOS)
        out.append(spans(final(r)))
    return out


def shield(frame):
    p = Pic(64, 64)
    r = 29 + frame * 1.5
    p.d.ellipse(((32 - r) * K, (32 - r) * K, (32 + r) * K, (32 + r) * K), fill=(140, 200, 255, 70), outline=(60, 130, 230, 255),
                width=int(2.2 * K))
    p.d.arc(((32 - r + 5) * K, (32 - r + 5) * K, (32 + r - 5) * K, (32 + r - 5) * K), 200, 260, fill=(255, 255, 255, 255),
            width=int(2 * K))
    return sprite(p)


# ---- platforms ----------------------------------------------------------------------------------------------------------
PLW, PLH, PLTOP = 62, 18, 3


def platform(kind, frame=0):
    p = Pic(PLW, PLH)
    fills = {"green": (160, 210, 84), "blue": (96, 168, 236), "gray": (152, 172, 192), "white": (252, 252, 250),
             "yellow": (240, 204, 56), "red": (232, 70, 50), "brown": (160, 100, 52)}
    f = fills[kind]
    ink = shade(f, 0.5) if kind != "white" else (150, 150, 150)
    if kind == "brown":
        if frame == 0:
            p.rrect(2, 3, 60, 15, 4, f, ink, 1.3)
            p.line([(30, 3), (27, 7), (33, 10), (29, 15)], ink, 1.3)
            p.line([(10, 7), (18, 8)], shade(f, 0.7), 1.2)
        else:
            gap = 3 * frame
            drop = 4 * frame * frame
            p.poly([(2, 3 + drop), (28 - gap, 3 + drop), (25 - gap, 8 + drop), (29 - gap, 15 + drop), (2, 15 + drop)], f, ink, 1.3)
            p.poly([(32 + gap, 3 + drop), (60, 3 + drop), (60, 15 + drop), (31 + gap, 15 + drop), (35 + gap, 9 + drop)], f, ink, 1.3)
        return sprite(p)
    p.rrect(2, 3, 60, 15, 5, f, ink, 1.3)
    p.line([(8, 6.5), (54, 6.5)], shade(f, 1.15) if kind != "white" else (225, 228, 232), 1.4, 0.1)
    p.line([(8, 12.5), (54, 12.5)], shade(f, 0.82), 1.0, 0.1)
    if kind == "gray":
        for x in (10, 51):
            p.line([(x, 8), (x, 11)], ink, 1.0)
    if kind == "red" and frame:
        p.line([(14, 4), (48, 14)], (255, 220, 120), 1.3)
    return sprite(p)


def spring(compressed):
    h = 10 if compressed else 24
    p = Pic(16, h)
    top = 1.5
    p.rrect(2, h - 4, 14, h - 0.8, 1.5, (200, 200, 206), INK, 1.3)
    turns = 3 if compressed else 5
    for k in range(turns):
        y = top + 3 + k * (h - 8 - top) / max(1, turns - 1) if turns > 1 else top + 3
        p.line([(3, y + 1.2), (13, y - 1.2)], (230, 70, 60), 2.0, 0.05)
        p.line([(3, y + 1.2), (13, y - 1.2)], INK, 0.7, 0.05)
    p.rrect(1, top - 1, 15, top + 2.6, 1.5, (236, 90, 80), INK, 1.3)
    return sprite(p)


def trampoline(compressed):
    h = 8 if compressed else 16
    p = Pic(38, h)
    y = 2.5 if compressed else 3
    p.line([(8, y + 2), (6, h - 1)], INK, 1.5)
    p.line([(30, y + 2), (32, h - 1)], INK, 1.5)
    p.rrect(3, y - 1.5, 35, y + 3.5, 2.5, (232, 70, 60), INK, 1.5)
    p.line([(8, y), (30, y)], (255, 170, 150), 1.2, 0.05)
    return sprite(p)


def item_propeller():
    p = Pic(28, 20)
    p.poly([(4, 17), (6, 8), (22, 7), (25, 17)], (70, 130, 220), INK, 1.5)
    p.poly([(11, 8), (16, 7.5), (17, 17), (9, 17)], (240, 90, 70), None)
    p.line([(4, 17), (25, 17)], INK, 1.5)
    p.line([(14, 7), (14, 3)], INK, 1.4)
    p.blob(14, 2.8, 11, 1.6, (230, 230, 236), INK, 1.2, 0.1)
    return sprite(p)


def item_jetpack():
    p = Pic(22, 30)
    p.rrect(3, 2, 19, 28, 4, (200, 70, 60), INK, 1.5)
    p.rrect(6, 5, 16, 14, 2, (235, 200, 70), None)
    p.line([(3, 18), (19, 18)], INK, 1.3)
    p.line([(11, 18), (11, 28)], INK, 1.2)
    return sprite(p)


def item_shield():
    p = Pic(30, 30)
    p.blob(15, 15, 12, 12, (150, 205, 255), (50, 120, 220), 1.8, 0.15)
    p.blob(15, 15, 7, 7, (210, 235, 255), None)
    p.line([(9, 9), (12, 7)], (255, 255, 255), 1.6, 0.05)
    return sprite(p)


# ---- monsters -----------------------------------------------------------------------------------------------------------
def monster(kind, frame):
    # Thin-lined, colourful cartoon monsters as on the original's artwork: a blue one-eyed blob with a pink toothy mouth, a
    # purple striped winged insect on eyeball antennae, and a six-armed purple one-eyed creature.
    if kind == 0:
        p = Pic(54, 50)
        ink = (30, 50, 110)
        lift = frame * 2
        p.poly(smooth([(6, 44), (6, 26), (14, 12), (27, 8), (40, 12), (48, 26), (48, 44), (38, 47), (27, 45), (16, 47)], 3),
               (92, 168, 226), ink, 1.3)
        for ex, d in ((19, -1), (35, 1)):
            p.line([(ex, 12), (ex + d * 3, 4 - lift)], ink, 1.2)
            p.dot(ex + d * 3, 3.5 - lift, 2.3, (250, 215, 60))
        p.blob(27, 24, 8, 8.5, (255, 255, 255), ink, 1.3)
        p.dot(27.5 + frame * 0.8, 25, 3.4, ink)
        p.poly(smooth([(11, 35), (27, 40), (43, 35), (41, 43), (27, 46), (13, 43)], 2), (232, 90, 150), ink, 1.1)
        for tx in (16, 22, 28, 34, 40):
            p.poly([(tx - 2, 37.5), (tx + 2, 38), (tx, 42.5)], (255, 255, 255), ink, 0.6)
        for lx in (14, 40):
            p.line([(lx, 45), (lx + (frame * 3 - 1), 49.5)], ink, 1.4)
        return sprite(p)
    if kind == 1:
        p = Pic(58, 44)
        ink = (60, 40, 110)
        wy = 8 + frame * 9
        for sx in (1, -1):
            x0 = 29 + sx * 8
            p.poly([(x0, 22), (x0 + sx * 11, wy - 2), (x0 + sx * 21, wy + 6), (x0 + sx * 11, 28)], (150, 120, 220), ink, 1.2)
        p.blob(29, 26, 9, 14, (96, 150, 230), ink, 1.3)
        for k in range(3):
            y = 20 + k * 6
            p.line([(21, y), (37, y)], (230, 120, 70), 2.2, 0.05)
        for sx in (-1, 1):
            p.line([(29 + sx * 3, 13), (29 + sx * 8, 4)], ink, 1.1)
            p.blob(29 + sx * 8.5, 3.5, 3.2, 3.2, (255, 255, 255), ink, 1.0)
            p.dot(29 + sx * 8.5, 3.8, 1.2, ink)
        p.line([(26, 38), (25, 43)], ink, 1.2)
        p.line([(32, 38), (33, 43)], ink, 1.2)
        return sprite(p)
    p = Pic(58, 54)
    ink = (70, 30, 100)
    for i in range(6):
        a = math.radians(190 + i * 32 + (frame * 9 if i % 2 else -frame * 9))
        c, sn = math.cos(a), -math.sin(a)
        p.line([(29, 32), (29 + 13 * c, 32 + 13 * sn), (29 + 24 * c, 32 + 24 * sn)], ink, 1.5)
    p.blob(29, 27, 15, 15, (160, 100, 200), ink, 1.3)
    p.poly([(17, 17), (14, 6), (23, 13)], (160, 100, 200), ink, 1.2)
    p.poly([(41, 17), (44, 6), (35, 13)], (160, 100, 200), ink, 1.2)
    p.blob(29, 25, 8, 8, (255, 255, 255), ink, 1.2)
    p.dot(29.5 + frame, 25.5, 3.4, ink)
    p.line([(21, 36), (29, 39), (37, 36)], ink, 1.2)
    return sprite(p)


def ufo(frame):
    p = Pic(68, 36)
    p.poly(smooth([(26, 16), (28, 4), (40, 4), (42, 16)], 2), (170, 230, 245), INK, 1.5)
    p.blob(34, 22, 31, 9, (110, 190, 90), INK, 1.7)
    for i, x in enumerate((14, 24, 34, 44, 54)):
        on = (i + frame) % 2 == 0
        p.dot(x, 22.5, 2.3, (255, 235, 90) if on else (200, 120, 60))
    p.blob(34, 8.5, 3, 2.6, (240, 90, 70), INK, 1.1)
    return sprite(p)


def blackhole(frame):
    p = Pic(64, 64)
    pts = []
    for i in range(40):
        a = 2 * math.pi * i / 40
        r = 27 + rng.uniform(-3.2, 3.2)
        pts.append((32 + r * math.cos(a), 32 + r * math.sin(a)))
    p.poly(pts, (18, 18, 24), INK, 2.2, 0.3)
    ring = [(32 + (31 + rng.uniform(-1.5, 1.5)) * math.cos(2 * math.pi * i / 40),
             32 + (31 + rng.uniform(-1.5, 1.5)) * math.sin(2 * math.pi * i / 40)) for i in range(40)]
    p.line(ring + [ring[0]], (205, 195, 160), 1.6, 0.1)
    for k in range(3):
        a0 = frame * 0.9 + k * 2.09
        pts = [(32 + (4 + t * 3.2) * math.cos(a0 + t * 0.55), 32 + (4 + t * 3.2) * math.sin(a0 + t * 0.55)) for t in range(8)]
        p.line(pts, (90, 90, 110), 1.6, 0.05)
    return sprite(p)


def puff(frame):
    r = (8, 14, 18)[frame]
    p = Pic(44, 44)
    for k in range(7):
        a = k * 0.9
        rr = r * (0.55 + 0.1 * (k % 2))
        p.blob(22 + math.cos(a) * r * 0.55, 22 + math.sin(a) * r * 0.55, rr * 0.7, rr * 0.7, (250, 250, 250), INK, 1.3, 0.1)
    p.blob(22, 22, r * 0.62, r * 0.62, (250, 250, 250), None)
    return sprite(p)


def boom(frame):
    r = (14, 22, 28)[frame]
    p = Pic(62, 62)
    pts = []
    for i in range(16):
        a = 2 * math.pi * i / 16
        rr = r if i % 2 else r * 0.55
        pts.append((31 + rr * math.cos(a), 31 + rr * math.sin(a)))
    p.poly(pts, (255, 120, 30), INK, 1.6, 0.4)
    p.blob(31, 31, r * 0.4, r * 0.4, (255, 230, 90), None)
    return sprite(p)


def bullet():
    p = Pic(9, 9)
    p.blob(4.5, 4.5, 3.3, 3.3, (250, 250, 240), INK, 1.3, 0.05)
    return sprite(p)


def stars(frame):
    p = Pic(40, 14)
    for i in range(3):
        a = frame * 1.0 + i * 2.1
        x, y = 20 + 14 * math.cos(a), 7 + 3.5 * math.sin(a)
        pts = [(x + (5 if k % 2 == 0 else 2) * math.cos(k * math.pi / 5 - 1.57),
                y + (5 if k % 2 == 0 else 2) * math.sin(k * math.pi / 5 - 1.57)) for k in range(10)]
        p.poly(pts, (250, 220, 60), INK, 0.9, 0.05)
    return sprite(p)


# ---- text ---------------------------------------------------------------------------------------------------------------
def marker(text, height, color=INK, jitter=1.0, pad=4):
    # Chunky felt-pen lettering: DejaVu Bold with per-glyph rotation and offset and a doubled stroke.
    big = height * K
    font = ImageFont.truetype(BOLD, int(big))
    glyphs = []
    wtot = pad * K
    for ch in text:
        w = int(font.getlength(ch)) + int(2 * K)
        glyphs.append((ch, w))
        wtot += w
    img = Image.new("RGBA", (wtot + pad * K, int(big * 1.45) + pad * K), (0, 0, 0, 0))
    x = pad * K
    for ch, w in glyphs:
        g = Image.new("RGBA", (w + 8 * K, int(big * 1.45)), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for dx, dy in ((0, 0), (K * 0.5, 0), (0, K * 0.5)):
            gd.text((4 * K + dx, K * 2 + dy), ch, font=font, fill=color + (255,))
        g = g.rotate(rng.uniform(-4, 4) * jitter, resample=Image.BICUBIC)
        img.paste(g, (int(x - 4 * K), int(rng.uniform(-1, 1) * jitter * K)), g)
        x += w
    bbox = img.getbbox()
    img = img.crop((max(0, bbox[0] - K), max(0, bbox[1] - K), bbox[2] + K, bbox[3] + K))
    w, h = img.width // SS * SS, img.height // SS * SS
    return img.crop((0, 0, w, h))


def text_sprite(text, height, color=INK):
    return spans(final(marker(text, height, color)))


def digit_sprites(height, color=INK):
    # One fixed-size cell per digit so the game can lay a number out without measuring.
    ims = [marker(c, height, color) for c in "0123456789"]
    cw = max(i.width for i in ims)
    ch = max(i.height for i in ims)
    out = []
    for i in ims:
        c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        c.paste(i, ((cw - i.width) // 2, (ch - i.height) // 2), i)
        out.append(spans(final(c)))
    return out


def button(label):
    p = Pic(130, 40)
    p.rrect(3, 4, 126, 34, 9, (136, 204, 70), INK, 2.0, 0.35)
    p.rrect(6, 7, 123, 16, 5, (170, 226, 110), None)
    t = marker(label, 14, INK, 0.6)
    p.im.paste(t, ((p.im.width - t.width) // 2, (p.im.height - t.height) // 2 - K), t)
    return sprite(p)
