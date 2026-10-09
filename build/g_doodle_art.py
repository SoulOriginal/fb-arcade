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
DW, DH, FEET, BODYX = 64, 84, 80, 27     # canvas, feet baseline, x of the body centre when facing right
GREEN = (164, 204, 52)
GREEN_D = (104, 150, 30)


def doodler(leg, snout_deg=0, hat=None, pack=None):
    p = Pic(DW, DH)
    bt = FEET - leg                     # body bottom
    top = bt - 36
    # legs are drawn first so that the body overlaps their roots
    for x in (13, 19, 30, 36):
        bend = (leg < 8) * 5
        pts = [(x, bt - 3), (x - bend - 1, bt + leg * 0.5), (x + 1, FEET - 2)]
        p.line(pts, INK, 1.7, 0.1)
        p.line([(x + 1, FEET - 2), (x + 6, FEET - 0.5)], INK, 1.7, 0.1)
    if pack:
        p.rrect(-1, bt - 30, 11, bt - 4, 3, (200, 70, 60), INK, 1.4)
        p.rrect(1, bt - 26, 9, bt - 18, 2, (235, 200, 70), None)
        p.line([(0, bt - 10), (10, bt - 10)], INK, 1.2)
        fl = 14 if pack == 1 else 22
        p.poly([(1.5, bt - 4), (9.5, bt - 4), (5.5, bt - 4 + fl)], (255, 150, 30), INK, 1.0)
        p.poly([(3.5, bt - 4), (7.5, bt - 4), (5.5, bt - 4 + fl * 0.6)], (255, 230, 90), None)
    body = smooth([(17, top - 7), (29, top + 6), (37, top + 18), (37, bt - 5), (30, bt), (15, bt), (10, bt - 7),
                   (10, top + 22), (14, top + 6)], 3)
    p.poly(body, GREEN, INK, 1.7, 0.2)
    # darker belly stripes, clipped to the body so they never leak over the outline
    stripes = Pic(DW, DH)
    for k in range(3):
        y = bt - 6 - k * 6
        stripes.line([(8, y + 2), (22, y - 1.5), (40, y + 2)], GREEN_D, 2.2, 0.1)
    mask = Image.new("L", p.im.size, 0)
    ImageDraw.Draw(mask).polygon([(x * K, y * K) for x, y in body], fill=255)
    layer = stripes.im
    layer.putalpha(ImageChops.darker(layer.getchannel("A"), mask))
    p.im.alpha_composite(layer)
    # snout: a tube whose base sits on the head, rotated by snout_deg (0 = forward, -85 = straight up while shooting)
    a = math.radians(snout_deg)
    bx, by = 33.0, top + 14.0
    ln, wd = 22.0, 4.6
    ux, uy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
    tube = [(bx + nx * wd * s + ux * t, by + ny * wd * s + uy * t) for s, t in ((-1, 0), (-1, ln), (1, ln), (1, 0))]
    p.poly(tube, GREEN, INK, 1.6, 0.12)
    ex, ey = bx + ux * (ln + 0.5), by + uy * (ln + 0.5)
    p.blob(ex, ey, wd * 1.05, wd * 1.05, (88, 126, 28), INK, 1.5, 0.1)
    p.blob(32.5, top + 7.5, 3.6, 4.0, (255, 255, 255), INK, 1.1, 0.05)
    p.dot(33.8, top + 8.0, 1.6)
    p.line([(26, top + 11), (30, top + 12.5)], INK, 1.0, 0.05)
    if hat:
        hx, hy = 18, top - 4
        p.poly([(hx - 9, hy + 2), (hx - 7, hy - 6), (hx + 6, hy - 7), (hx + 10, hy + 2)], (70, 130, 220), INK, 1.5)
        p.poly([(hx - 3, hy - 6.5), (hx + 1.5, hy - 6.8), (hx + 3, hy + 2), (hx - 5, hy + 2)], (240, 90, 70), None)
        p.line([(hx - 9, hy + 2), (hx + 10, hy + 2)], INK, 1.5)
        p.line([(hx, hy - 7), (hx, hy - 12)], INK, 1.4)
        bw = 13 if hat == 1 else 5
        p.blob(hx, hy - 12.5, bw, 1.8, (230, 230, 236), INK, 1.2, 0.1)
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
    fills = {"green": (118, 196, 62), "blue": (96, 168, 236), "gray": (152, 172, 192), "white": (252, 252, 250),
             "yellow": (240, 204, 56), "red": (232, 70, 50), "brown": (160, 100, 52)}
    f = fills[kind]
    if kind == "brown":
        if frame == 0:
            p.rrect(2, 3, 60, 15, 4, f, INK, 1.5)
            p.line([(30, 3), (27, 7), (33, 10), (29, 15)], INK, 1.5)
            p.line([(10, 7), (18, 8)], shade(f, 0.7), 1.2)
        else:
            gap = 3 * frame
            drop = 4 * frame * frame
            p.poly([(2, 3 + drop), (28 - gap, 3 + drop), (25 - gap, 8 + drop), (29 - gap, 15 + drop), (2, 15 + drop)], f, INK, 1.5)
            p.poly([(32 + gap, 3 + drop), (60, 3 + drop), (60, 15 + drop), (31 + gap, 15 + drop), (35 + gap, 9 + drop)], f, INK, 1.5)
        return sprite(p)
    p.rrect(2, 3, 60, 15, 5, f, INK, 1.5)
    p.line([(8, 6.5), (54, 6.5)], shade(f, 1.15) if kind != "white" else (225, 228, 232), 1.4, 0.1)
    p.line([(8, 12.5), (54, 12.5)], shade(f, 0.82), 1.0, 0.1)
    if kind == "gray":
        for x in (10, 51):
            p.line([(x, 8), (x, 11)], INK, 1.0)
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
    ink = INK
    if kind == 0:       # green blob with eye stalks and a toothy grin
        p = Pic(54, 50)
        lift = frame * 2
        p.poly(smooth([(5, 42), (4, 26), (12, 12), (27, 8), (42, 12), (50, 26), (49, 42), (38, 46), (27, 44), (16, 46)], 3),
               (110, 190, 80), ink, 1.7)
        for ex in (17, 37):
            p.line([(ex, 14), (ex + (ex < 27 and -2 or 2), 5 - lift)], ink, 1.5)
            p.blob(ex + (ex < 27 and -2 or 2), 4 - lift, 5, 5, (255, 255, 255), ink, 1.4)
            p.dot(ex + (ex < 27 and -1 or 1), 4.5 - lift, 2.0)
        p.poly(smooth([(11, 27), (27, 33), (43, 27), (41, 37), (27, 41), (13, 37)], 2), (70, 40, 50), ink, 1.4)
        for tx in (17, 24, 31, 38):
            p.poly([(tx - 2, 29 + (tx == 24 or tx == 31)), (tx + 2, 30), (tx, 34)], (255, 255, 255), None)
        for lx in (12, 42):
            p.line([(lx, 43), (lx + (frame * 3 - 1), 49)], ink, 1.8)
        return sprite(p)
    if kind == 1:       # blue flyer, two big eyes, flapping wings
        p = Pic(58, 44)
        wy = 8 + frame * 9
        for sx in (1, -1):
            x0 = 29 + sx * 14
            p.poly([(x0, 22), (x0 + sx * 12, wy - 2), (x0 + sx * 20, wy + 6), (x0 + sx * 8, 26)], (170, 210, 250), ink, 1.5)
        p.blob(29, 25, 16, 14, (84, 140, 230), ink, 1.7)
        for ex in (23, 36):
            p.blob(ex, 22, 5.2, 6, (255, 255, 255), ink, 1.3)
            p.dot(ex + 0.7, 23, 2.2)
        p.line([(22, 31), (29, 34), (36, 31)], ink, 1.5)
        p.line([(24, 12), (21, 4)], ink, 1.4)
        p.line([(34, 12), (37, 4)], ink, 1.4)
        p.dot(21, 3.5, 2.2, (240, 90, 70))
        p.dot(37, 3.5, 2.2, (240, 90, 70))
        return sprite(p)
    p = Pic(58, 54)     # purple six-armed
    for i in range(6):
        a = math.radians(190 + i * 32 + (frame * 9 if i % 2 else -frame * 9))
        c, sn = math.cos(a), -math.sin(a)
        p.line([(29, 32), (29 + 13 * c, 32 + 13 * sn), (29 + 24 * c, 32 + 24 * sn)], ink, 2.0)
    p.blob(29, 27, 15, 15, (150, 90, 190), ink, 1.7)
    p.poly([(17, 17), (14, 6), (23, 13)], (150, 90, 190), ink, 1.5)
    p.poly([(41, 17), (44, 6), (35, 13)], (150, 90, 190), ink, 1.5)
    p.blob(29, 25, 8, 8, (255, 255, 255), ink, 1.4)
    p.dot(29.5 + frame, 25.5, 3.4)
    p.line([(21, 36), (29, 39), (37, 36)], ink, 1.5)
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
