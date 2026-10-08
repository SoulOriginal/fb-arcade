# Build-time art for the "Space Frog" Frogger. Everything is drawn procedurally (supersampled) and packed to RGB565.
# Output: g_frogger.bin with the static field, the scrolling lane strips, RLE overlay sprites and the lane layout
# (the layout lives here so that what is drawn and what the game collides with can never drift apart).
import math, random, re
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from buildlib import save_bundle

T = 72                     # tile size in screen px
FW, FH = 13 * T, 14 * T    # playfield size
SS = 4                     # supersampling factor for sprites
FRAMES = 4                 # animation frames of water / paddling / glow


def to565(img):
    r, g, b = img.convert("RGB").split()
    lo = ImageChops.add(g.point(lambda v: ((v >> 2) & 7) << 5), b.point(lambda v: v >> 3))
    hi = ImageChops.add(r.point(lambda v: (v >> 3) << 3), g.point(lambda v: v >> 5))
    out = bytearray(img.width * img.height * 2)
    out[0::2] = lo.tobytes()
    out[1::2] = hi.tobytes()
    return bytes(out)


def pack(img):
    return (img.width, img.height, to565(img))


def rle(img, thr=110):
    # Overlay sprite: per scanline, the opaque runs as (x, rgb565 bytes). Opaque-only on purpose: the game
    # composites runs into a row buffer with plain slice assignment.
    img = img.convert("RGBA")
    w, h = img.size
    a = img.getchannel("A").point(lambda v: 1 if v >= thr else 0).tobytes()
    data = to565(img)
    rows = []
    for y in range(h):
        row = a[y * w:(y + 1) * w]
        rows.append([(m.start(), data[(y * w + m.start()) * 2:(y * w + m.end()) * 2])
                     for m in re.finditer(b"\x01+", row)])
    return {"w": w, "h": h, "rows": rows}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def down(img, size):
    # Premultiplied resampling: otherwise transparent black bleeds into the edge colours.
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


class Cv:
    # Supersampled RGBA canvas addressed in final pixels.
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def s(self, v):
        return [int(round(c * SS)) for c in v]

    def ell(self, cx, cy, rx, ry, fill, outline=None, width=0):
        self.d.ellipse(self.s((cx - rx, cy - ry, cx + rx, cy + ry)), fill=fill, outline=outline, width=int(width * SS))

    def rrect(self, box, r, fill, outline=None, width=0):
        self.d.rounded_rectangle(self.s(box), int(r * SS), fill=fill, outline=outline, width=int(width * SS))

    def rect(self, box, fill):
        self.d.rectangle(self.s(box), fill=fill)

    def poly(self, pts, fill, outline=None):
        self.d.polygon(self.s([c for p in pts for c in p]), fill=fill, outline=outline)

    def line(self, pts, fill, width):
        flat = self.s([c for p in pts for c in p])
        self.d.line(flat, fill=fill, width=int(width * SS), joint="curve")
        r = width / 2
        for p in (pts[0], pts[-1]):
            self.ell(p[0], p[1], r, r, fill)

    def grad(self, shape, box, top, bot):
        # Vertical gradient clipped by a shape drawn on a mask: shape(draw, scale) paints white.
        m = Image.new("L", self.img.size, 0)
        shape(ImageDraw.Draw(m))
        x0, y0, x1, y1 = self.s(box)
        g = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for y in range(max(0, y0), min(self.img.height, y1)):
            t = (y - y0) / max(1, y1 - y0)
            gd.line([(0, y), (self.img.width, y)], fill=lerp(top, bot, t) + (255,))
        g.putalpha(ImageChops.multiply(g.getchannel("A"), m))
        self.img = Image.alpha_composite(self.img, g)
        self.d = ImageDraw.Draw(self.img)

    def grad_rrect(self, box, r, top, bot):
        sb = self.s(box)
        self.grad(lambda d: d.rounded_rectangle(sb, int(r * SS), fill=255), box, top, bot)

    def grad_ell(self, cx, cy, rx, ry, top, bot):
        sb = self.s((cx - rx, cy - ry, cx + rx, cy + ry))
        self.grad(lambda d: d.ellipse(sb, fill=255), (cx - rx, cy - ry, cx + rx, cy + ry), top, bot)

    def glow(self, painter, radius, alpha=1.0):
        # painter draws bright shapes on an RGBA layer; blurred and put underneath what is already drawn.
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        painter(ImageDraw.Draw(layer))
        layer = layer.filter(ImageFilter.GaussianBlur(radius * SS))
        if alpha < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
        self.img = Image.alpha_composite(layer, self.img)
        self.d = ImageDraw.Draw(self.img)

    def out(self):
        return down(self.img, (self.w, self.h))


def flip(img):
    return img.transpose(Image.FLIP_LEFT_RIGHT)


# ---------------------------------------------------------------- frog
OL = (6, 52, 30)
G1, G2, G3 = (96, 238, 110), (44, 176, 78), (170, 255, 150)


def frog_img(leap):
    cv = Cv(T, T)
    if leap:
        body = (36, 38, 14, 25)
        legs = [([(26, 50), (14, 58), (13, 70)], 7), ([(46, 50), (58, 58), (59, 70)], 7),
                ([(27, 24), (19, 14), (17, 4)], 5), ([(45, 24), (53, 14), (55, 4)], 5)]
        feet = [(13, 70), (59, 70), (17, 4), (55, 4)]
        cv.glow(lambda d: [d.polygon(cv.s((30, 58, 42, 58, 36, 71)), fill=(255, 170, 60, 255))], 3, 0.9)
    else:
        body = (36, 40, 17, 22)
        legs = [([(22, 46), (11, 54), (16, 63)], 12), ([(50, 46), (61, 54), (56, 63)], 12),
                ([(24, 26), (17, 22), (14, 27)], 7), ([(48, 26), (55, 22), (58, 27)], 7)]
        feet = [(16, 63), (56, 63), (14, 27), (58, 27)]
    cx, cy, rx, ry = body
    for pts, wd in legs:
        cv.line(pts, OL, wd + 4)
    cv.ell(cx, cy, rx + 2, ry + 2, OL)
    cv.ell(cx, cy - ry * 0.7, 15 + 2, 12 + 2, OL)
    for p in feet:
        cv.ell(p[0], p[1], 7, 5, OL)
    for pts, wd in legs:
        cv.line(pts, G2, wd)
    for p in feet:
        cv.ell(p[0], p[1], 5.5, 3.6, G3)
    cv.grad_ell(cx, cy, rx, ry, G1, G2)
    cv.ell(cx, cy - ry * 0.7, 15, 12, G1)
    # neon back stripes and spots: the "space" part of the frog
    cv.line([(cx - 6, cy - 6), (cx - 7, cy + ry - 6)], (110, 240, 255), 2.6)
    cv.line([(cx + 6, cy - 6), (cx + 7, cy + ry - 6)], (110, 240, 255), 2.6)
    for p in ((cx - 10, cy + 2), (cx + 10, cy + 2), (cx, cy + 8)):
        cv.ell(p[0], p[1], 2.2, 2.2, (255, 90, 200))
    ey = cy - ry * 0.75
    for sx in (-1, 1):
        ex = cx + sx * 10
        cv.ell(ex, ey, 8.5, 8.5, OL)
        cv.ell(ex, ey, 7, 7, (255, 245, 190))
        cv.ell(ex, ey - 1.3, 3.8, 4.4, (10, 10, 30))
        cv.ell(ex - 1.4, ey - 2.8, 1.3, 1.3, (255, 255, 255))
    # glass helmet ring
    cv.d.arc(cv.s((cx - 24, ey - 17, cx + 24, ey + 22)), 180 * SS // SS, 360, fill=(130, 235, 255, 255), width=int(2.2 * SS))
    cv.d.arc(cv.s((cx - 24, ey - 17, cx + 24, ey + 22)), 200, 250, fill=(255, 255, 255, 255), width=int(2.2 * SS))
    return cv.img


def frog_sprites():
    res = []
    for rot in (None, Image.ROTATE_90, Image.ROTATE_270, Image.ROTATE_180):   # up, left, right, down
        pair = []
        for leap in (0, 1):
            im = frog_img(leap)
            if rot is not None:
                im = im.transpose(rot)
            pair.append(rle(down(im, (T, T))))
        res.append(pair)
    return res


def life_icon():
    im = down(frog_img(0), (T, T)).resize((44, 44), Image.LANCZOS)
    bg = Image.new("RGBA", (44, 44), (0, 0, 0, 255))
    return pack(Image.alpha_composite(bg, im))


def squash_sprites():
    res = []
    for k in range(3):
        cv = Cv(96, 72)
        a = 1.0 - k * 0.0
        cv.ell(48, 38, 36, 20, OL)
        cv.ell(48, 38, 33, 17, (60, 200, 80))
        for bx, by, r in ((18, 30, 7), (78, 44, 8), (30, 52, 6), (70, 24, 5), (48, 58, 6)):
            cv.ell(bx, by, r + 1, r - 1, OL)
            cv.ell(bx, by, r, r - 2, (70, 210, 90))
        for ex in (36, 60):
            cv.line([(ex - 5, 30), (ex + 5, 40)], (20, 20, 30), 2.6)
            cv.line([(ex - 5, 40), (ex + 5, 30)], (20, 20, 30), 2.6)
        if k < 2:
            for sx, sy in ((14, 10), (82, 12), (48, 6)):
                s = 7 + 2 * ((k + sx) % 2)
                cv.poly([(sx, sy - s), (sx + s * 0.3, sy - s * 0.3), (sx + s, sy), (sx + s * 0.3, sy + s * 0.3),
                         (sx, sy + s), (sx - s * 0.3, sy + s * 0.3), (sx - s, sy), (sx - s * 0.3, sy - s * 0.3)],
                        (255, 240, 90) if k == 0 else (255, 150, 60))
        res.append(rle(down(cv.img, (96, 72))))
    return res


def splash_sprites():
    res = []
    rng = random.Random(5)
    drops = [(rng.uniform(0, 6.28), rng.uniform(0.6, 1.0)) for _ in range(9)]
    for k in range(5):
        cv = Cv(120, 120)
        c = 60
        for j in range(min(3, k + 1)):
            r = 10 + 11 * (k - j) + 6 * j if k - j >= 0 else 0
            if r > 0 and r < 56:
                col = lerp((190, 250, 255), (70, 150, 230), min(1, (k - j) / 4))
                cv.d.ellipse(cv.s((c - r, c - r * 0.78, c + r, c + r * 0.78)), outline=col + (255,), width=int(3 * SS))
        if k < 4:
            for ang, sp in drops:
                dist = (6 + 11 * k) * sp
                h = math.sin(min(1, (k + 0.5) / 4) * math.pi) * 22 * sp
                x, y = c + math.cos(ang) * dist, c + math.sin(ang) * dist * 0.7 - h
                cv.ell(x, y, 4.2 - k * 0.5, 4.8 - k * 0.5, (200, 245, 255))
        if k < 2:
            cv.ell(c - 8, c - 4, 5, 5, (255, 245, 190))
            cv.ell(c + 8, c - 4, 5, 5, (255, 245, 190))
            cv.ell(c - 8, c - 3, 2.4, 2.8, (10, 10, 30))
            cv.ell(c + 8, c - 3, 2.4, 2.8, (10, 10, 30))
            cv.d.arc(cv.s((c - 15, c - 14, c + 15, c + 12)), 190, 350, fill=(60, 200, 80, 255), width=int(4 * SS))
        res.append(rle(down(cv.img, (120, 120))))
    return res


def pop_sprites():
    res = []
    for k in range(4):
        cv = Cv(120, 120)
        c = 60
        n = 10
        r1, r2 = 10 + 14 * k, 4 + 6 * k
        pts = []
        for i in range(n * 2):
            r = r1 if i % 2 == 0 else r2
            a = i * math.pi / n + k * 0.2
            pts.append((c + r * math.cos(a), c + r * math.sin(a)))
        col = [(255, 250, 160), (255, 200, 70), (255, 120, 60), (200, 70, 90)][k]
        cv.poly(pts, col)
        if k < 2:
            cv.ell(c, c, 14, 11, OL)
            cv.ell(c, c, 12, 9, (80, 210, 100))
        res.append(rle(down(cv.img, (120, 120))))
    return res


# ---------------------------------------------------------------- lane objects
def thrusters(cv, ys, x_end, f, col, length):
    # Engine glow at the rear (x=0 side, sprite faces right). Flame length breathes with the frame.
    for y in ys:
        ln = length * (0.55 + 0.45 * ((f * 7 + int(y)) % 4) / 3)
        cv.glow(lambda d, y=y, ln=ln: d.polygon(cv.s((x_end, y - 5, x_end - ln - 4, y, x_end, y + 5)),
                                                 fill=col + (255,)), 3, 0.85)
        cv.poly([(x_end, y - 3.6), (x_end - ln, y), (x_end, y + 3.6)], (255, 245, 210))
        cv.poly([(x_end, y - 5), (x_end - ln * 0.7, y), (x_end, y + 5)], col + (170,))


def hover_discs(cv, pts, f, col):
    for i, (x, y) in enumerate(pts):
        a = 150 + 105 * (((f + i) % FRAMES) / (FRAMES - 1))
        cv.ell(x, y, 5.2, 5.2, (10, 12, 30))
        cv.ell(x, y, 3.8, 3.8, col + (int(a),))


CAR_LEN = {"pod": 72, "racer": 80, "truck": 144, "lorry": 216}


def car_img(kind, body, f):
    ln = CAR_LEN[kind]
    cv = Cv(ln, T)
    dark = lerp(body, (0, 0, 0), 0.45)
    light = lerp(body, (255, 255, 255), 0.35)
    cv.glow(lambda d: d.rounded_rectangle(cv.s((12, 12, ln - 2, 60)), 10 * SS, fill=body + (230,)), 5, 0.9)
    if kind == "pod":
        cv.rrect((13, 13, ln - 3, 59), 15, dark)
        cv.grad_rrect((14, 14, ln - 4, 58), 14, light, body)
        cv.rrect((34, 22, 58, 50), 8, (12, 20, 48))
        cv.rrect((38, 24, 56, 31), 4, (120, 190, 255))
        cv.line([(16, 36), (30, 36)], dark, 2)
        hover_discs(cv, [(24, 14), (24, 58), (52, 14), (52, 58)], f, (120, 240, 255))
        thrusters(cv, (25, 47), 13, f, (255, 150, 60), 9)
        cv.ell(ln - 4, 23, 3.6, 3.6, (255, 250, 200))
        cv.ell(ln - 4, 49, 3.6, 3.6, (255, 250, 200))
    elif kind == "racer":
        cv.poly([(12, 18), (52, 15), (ln - 1, 33), (ln - 1, 39), (52, 57), (12, 54)], dark)
        cv.poly([(14, 20), (52, 17), (ln - 4, 34), (ln - 4, 38), (52, 55), (14, 52)], body)
        cv.poly([(16, 24), (50, 21), (ln - 12, 35), (ln - 12, 37), (50, 51), (16, 48)], light)
        cv.rrect((30, 28, 52, 44), 6, (14, 18, 40))
        cv.rect((12, 12, 20, 60), dark)
        cv.rect((13, 12, 18, 60), (255, 230, 90))
        cv.line([(20, 36), (ln - 14, 36)], (255, 255, 255), 2.4)
        hover_discs(cv, [(44, 12), (44, 60)], f, (255, 210, 90))
        thrusters(cv, (30, 42), 12, f, (255, 90, 70), 11)
    else:
        n_trailers = 1 if kind == "truck" else 2
        cab_x = ln - 56
        cv.rrect((cab_x, 13, ln - 3, 59), 12, dark)
        cv.grad_rrect((cab_x + 1, 14, ln - 4, 58), 11, light, body)
        cv.rrect((ln - 26, 21, ln - 10, 51), 6, (12, 20, 48))
        cv.rrect((ln - 24, 23, ln - 14, 31), 3, (120, 190, 255))
        cv.ell(ln - 4, 22, 3.4, 3.4, (255, 250, 200))
        cv.ell(ln - 4, 50, 3.4, 3.4, (255, 250, 200))
        seg_w = (cab_x - 16) / n_trailers
        panel = lerp(body, (90, 100, 130), 0.7)
        for i in range(n_trailers):
            x0 = 14 + i * seg_w
            cv.rrect((x0, 12, x0 + seg_w - 4, 60), 6, (30, 34, 58))
            cv.grad_rrect((x0 + 1.5, 13.5, x0 + seg_w - 5.5, 58.5), 5, lerp(panel, (255, 255, 255), 0.25), panel)
            for g in range(1, 4):
                gx = x0 + g * (seg_w - 4) / 4
                cv.line([(gx, 16), (gx, 56)], (40, 46, 74), 1.6)
            cv.rect((x0 + 4, 33, x0 + seg_w - 9, 39), body)
        cv.rect((cab_x - 6, 32, cab_x + 2, 40), (30, 34, 58))
        hover_discs(cv, [(cab_x + 16, 14), (cab_x + 16, 58), (30, 14), (30, 58)], f, (150, 255, 160))
        thrusters(cv, (24, 48), 14, f, (255, 140, 60), 10)
    return cv.out()


def log_img(ln, seed):
    rng = random.Random(seed)
    cv = Cv(ln, T)
    cv.glow(lambda d: d.rounded_rectangle(cv.s((4, 18, ln - 4, 62)), 14 * SS, fill=(0, 0, 0, 200)), 4, 0.8)
    cv.rrect((2, 11, ln - 2, 61), 22, (52, 28, 14))
    cv.grad_rrect((3, 12, ln - 3, 59), 21, (176, 118, 64), (96, 58, 30))
    for _ in range(max(5, ln // 12)):
        x = rng.uniform(18, ln - 18)
        y = rng.uniform(18, 54)
        w = rng.uniform(10, 26)
        cv.line([(x, y), (x + w, y + rng.uniform(-1.2, 1.2))], (70, 40, 20), 1.7)
    for _ in range(max(1, ln // 70)):
        x, y = rng.uniform(40, ln - 40), rng.uniform(26, 46)
        cv.ell(x, y, 5, 3.4, (58, 32, 16))
        cv.ell(x, y, 2.6, 1.6, (120, 76, 40))
    for ex in (23, ln - 23):
        cv.ell(ex, 36, 15, 21, (214, 158, 92))
        for r, c in ((13, (170, 112, 60)), (9, (214, 158, 92)), (5, (150, 96, 50))):
            cv.d.ellipse(cv.s((ex - r * 0.72, 36 - r * 1.3, ex + r * 0.72, 36 + r * 1.3)), outline=c + (255,), width=SS)
    cv.line([(30, 15), (ln - 30, 15)], (110, 230, 255), 2.0)
    for cxp in (ln * 0.3, ln * 0.7):
        cv.poly([(cxp, 14), (cxp + 4, 5), (cxp + 8, 14)], (120, 230, 255))
        cv.poly([(cxp + 4, 14), (cxp + 8, 8), (cxp + 11, 14)], (190, 120, 255))
    return cv.out()


def turtle_img(f, state):
    # Faces right. state: 0 floating, 1/2 sinking, 3 submerged (only ripples).
    cv = Cv(T, T)
    ph = f * math.pi / 2
    if state < 3:
        for side in (-1, 1):
            sw = math.sin(ph + (0 if side < 0 else math.pi))
            cv.line([(42, 36 + side * 15), (50 + 5 * sw, 36 + side * (25 + 3 * sw))], (28, 128, 96), 8)
            cv.line([(22, 36 + side * 15), (16 - 3 * sw, 36 + side * (26 - 2 * sw))], (28, 128, 96), 7)
        cv.ell(58, 36, 9, 8, (60, 170, 120))
        cv.ell(62, 33, 2, 2, (10, 20, 30))
        cv.ell(62, 39, 2, 2, (10, 20, 30))
        cv.ell(34, 36, 27, 23, (10, 60, 56))
        cv.grad_ell(34, 36, 25, 21, (80, 210, 140), (28, 120, 96))
        cv.ell(34, 36, 13, 11, (36, 134, 104))
        cv.d.ellipse(cv.s((21, 25, 47, 47)), outline=(14, 80, 66, 255), width=2 * SS)
        for a in range(0, 360, 60):
            r = math.radians(a + 30)
            cv.line([(34 + 13 * math.cos(r), 36 + 11 * math.sin(r)), (34 + 25 * math.cos(r), 36 + 21 * math.sin(r))],
                    (14, 80, 66), 1.8)
        cv.ell(28, 28, 4, 2.6, (190, 255, 210))
        for p in ((26, 36), (40, 30), (40, 43)):
            cv.ell(p[0], p[1], 1.8, 1.8, (110, 235, 255))
    img = cv.img
    if state == 1:
        img = down(img, (T, T))
        im2 = img.resize((60, 60), Image.LANCZOS)
        base = Image.new("RGBA", (T, T), (0, 0, 0, 0))
        base.paste(im2, (6, 8))
        base.putalpha(base.getchannel("A").point(lambda v: int(v * 0.9)))
        rings = Cv(T, T)
        rings.d.ellipse(rings.s((8, 10, 66, 62)), outline=(190, 245, 255, 220), width=int(1.6 * SS))
        return Image.alpha_composite(base, down(rings.img, (T, T)))
    if state == 2:
        img = down(img, (T, T))
        im2 = img.resize((46, 46), Image.LANCZOS)
        base = Image.new("RGBA", (T, T), (0, 0, 0, 0))
        base.paste(im2, (13, 15))
        base.putalpha(base.getchannel("A").point(lambda v: int(v * 0.42)))
        rings = Cv(T, T)
        rings.d.ellipse(rings.s((6, 8, 68, 64)), outline=(190, 245, 255, 235), width=int(1.8 * SS))
        rings.d.ellipse(rings.s((16, 18, 58, 54)), outline=(150, 220, 255, 200), width=int(1.4 * SS))
        return Image.alpha_composite(base, down(rings.img, (T, T)))
    if state == 3:
        rings = Cv(T, T)
        r = 14 + 4 * (f % 2)
        rings.d.ellipse(rings.s((36 - r, 36 - r * 0.8, 36 + r, 36 + r * 0.8)), outline=(170, 235, 255, 200), width=int(1.4 * SS))
        for k in range(3):
            y = 44 - ((f * 5 + k * 9) % 22)
            rings.ell(24 + k * 10, y, 2, 2, (200, 245, 255, 220))
        return down(rings.img, (T, T))
    return down(img, (T, T))


def gator_img(open_mouth):
    ln = 4 * T
    cv = Cv(ln, T)
    dark, mid, lite = (20, 70, 30), (60, 130, 50), (120, 190, 70)
    for lx in (96, 176):
        for sy in (-1, 1):
            cv.line([(lx, 36 + sy * 18), (lx + 14, 36 + sy * 31)], dark, 11)
            cv.line([(lx, 36 + sy * 18), (lx + 14, 36 + sy * 31)], mid, 7)
    cv.poly([(0, 34), (60, 22), (110, 17), (190, 17), (212, 24), (212, 48), (190, 55), (110, 55), (60, 50), (0, 38)], dark)
    cv.grad(lambda d: d.polygon(cv.s((3, 35, 60, 25, 110, 20, 190, 20, 210, 26, 210, 46, 190, 52, 110, 52, 60, 47, 3, 37)), fill=255),
            (0, 18, 1, 54), lite, mid)
    for i in range(7):
        x = 40 + i * 24
        h = 5 + 4 * (1 - abs(i - 3) / 4)
        cv.rrect((x - 7, 36 - h, x + 7, 36 + h), 3, dark)
        cv.rrect((x - 5, 36 - h + 1.5, x + 5, 36 + h - 1.5), 2, (80, 150, 60))
        cv.poly([(x - 4, 36 - h), (x, 36 - h - 5), (x + 4, 36 - h)], (230, 210, 120))
    if not open_mouth:
        cv.poly([(204, 20), (250, 24), (ln - 2, 29), (ln - 2, 43), (250, 48), (204, 52)], dark)
        cv.poly([(206, 23), (250, 26), (ln - 5, 31), (ln - 5, 41), (250, 46), (206, 49)], mid)
        for i in range(6):
            x = 232 + i * 8
            cv.poly([(x, 28 + i * 0.5), (x + 3, 33), (x + 6, 28 + i * 0.5)], (250, 250, 235))
            cv.poly([(x, 44 - i * 0.5), (x + 3, 39), (x + 6, 44 - i * 0.5)], (250, 250, 235))
    else:
        cv.poly([(204, 30), (ln - 4, 8), (ln - 2, 20), (230, 36)], dark)
        cv.poly([(206, 31), (ln - 7, 12), (ln - 6, 19), (232, 35)], mid)
        cv.poly([(204, 42), (ln - 4, 64), (ln - 2, 52), (230, 36)], dark)
        cv.poly([(206, 41), (ln - 7, 60), (ln - 6, 53), (232, 37)], mid)
        cv.poly([(220, 34), (ln - 6, 22), (ln - 6, 50), (220, 38)], (190, 40, 70))
        for i in range(5):
            x = 238 + i * 9
            cv.poly([(x, 28 - i * 1.2 + 6), (x + 3, 34), (x + 6, 28 - i * 1.2 + 6)], (250, 250, 235))
            cv.poly([(x, 44 + i * 1.2 - 6), (x + 3, 38), (x + 6, 44 + i * 1.2 - 6)], (250, 250, 235))
    for sy in (-1, 1):
        cv.ell(226, 36 + sy * 14, 8.5, 8.5, dark)
        cv.ell(226, 36 + sy * 14, 6.6, 6.6, (255, 230, 70))
        cv.ell(227, 36 + sy * 14, 1.8, 5, (20, 20, 20))
    return cv.out()


def snake_img(phase):
    ln, h = 180, 44
    cv = Cv(ln, h)
    pts = [(10 + i * 9.5, 22 + 9 * math.sin(i * 0.62 + phase * math.pi / 2)) for i in range(16)]
    for i, (x, y) in enumerate(pts):
        r = 7.5 - (1.5 if i < 3 else 0)
        cv.ell(x, y, r + 1.8, r + 1.8, (60, 6, 20))
    for i, (x, y) in enumerate(pts):
        r = 7.5 - (1.5 if i < 3 else 0)
        cv.ell(x, y, r, r, (235, 60, 90) if (i // 2) % 2 == 0 else (250, 210, 60))
    hx, hy = pts[-1]
    cv.ell(hx + 8, hy, 11, 8.5, (60, 6, 20))
    cv.ell(hx + 8, hy, 9.6, 7, (200, 40, 90))
    for sy in (-1, 1):
        cv.ell(hx + 11, hy + sy * 4, 2.6, 2.6, (255, 250, 150))
        cv.ell(hx + 12, hy + sy * 4, 1.1, 1.1, (10, 10, 10))
    if phase % 2 == 0:
        cv.line([(hx + 17, hy), (hx + 25, hy), (hx + 29, hy - 3)], (255, 60, 60), 1.6)
        cv.line([(hx + 25, hy), (hx + 29, hy + 3)], (255, 60, 60), 1.6)
    return cv.out()


def fly_sprites():
    res = []
    for k in range(2):
        cv = Cv(48, 48)
        wy = 7 if k == 0 else 15
        for sx in (-1, 1):
            cv.ell(24 + sx * 11, wy + 8, 9, 5.5 if k == 0 else 8, (170, 235, 255))
            cv.d.ellipse(cv.s((24 + sx * 11 - 9, wy + 8 - (5.5 if k == 0 else 8), 24 + sx * 11 + 9, wy + 8 + (5.5 if k == 0 else 8))),
                         outline=(255, 255, 255, 255), width=SS)
        cv.ell(24, 28, 6.5, 10, (30, 30, 50))
        cv.ell(24, 17, 6.5, 5.5, (60, 60, 90))
        cv.ell(21.5, 16, 2.4, 2.4, (255, 60, 80))
        cv.ell(26.5, 16, 2.4, 2.4, (255, 60, 80))
        for i in range(3):
            cv.line([(24, 24 + i * 4), (24 + 5, 24 + i * 4)], (255, 90, 200), 1.6)
        res.append(rle(down(cv.img, (48, 48))))
    return res


def croc_sprites():
    # Head of a crocodile lurking in a bay, facing down at the player.
    res = []
    for k in range(2):
        cv = Cv(110, 72)
        dark, mid = (20, 70, 30), (74, 150, 56)
        cv.ell(55, 22, 44, 30, dark)
        cv.grad_ell(55, 22, 41, 27, (130, 200, 80), mid)
        for sx in (-1, 1):
            cv.ell(55 + sx * 24, 12, 11, 11, dark)
            cv.ell(55 + sx * 24, 12, 8.6, 8.6, (255, 230, 70))
            cv.ell(55 + sx * 24, 13, 4.4, 2, (20, 20, 20))
        if k == 0:
            cv.rrect((38, 34, 72, 68), 8, dark)
            cv.rrect((40, 36, 70, 66), 7, mid)
            for i in range(4):
                cv.poly([(42 + i * 7, 62), (45 + i * 7, 56), (48 + i * 7, 62)], (250, 250, 235))
        else:
            cv.rrect((34, 34, 76, 70), 10, dark)
            cv.rrect((37, 38, 73, 68), 8, (190, 40, 70))
            for i in range(5):
                cv.poly([(37 + i * 8, 38), (41 + i * 8, 46), (45 + i * 8, 38)], (250, 250, 235))
                cv.poly([(37 + i * 8, 68), (41 + i * 8, 60), (45 + i * 8, 68)], (250, 250, 235))
        res.append(rle(down(cv.img, (110, 72))))
    return res


# ---------------------------------------------------------------- lane layout
# object tuples: ("car", x_tile, kind, colour_index) | ("log", x_tile, len_tiles) | ("turtle", x_tile, n, diver)
#                ("gator", x_tile)
CAR_COLORS = [(255, 70, 180), (60, 230, 255), (255, 200, 60), (255, 120, 40), (170, 110, 255)]
LANES = {
    11: dict(kind="road", dir=-1, speed=1.7, period=13, objs=[("car", 1.0, "pod", 0), ("car", 5.0, "pod", 0), ("car", 9.5, "pod", 0)]),
    10: dict(kind="road", dir=1, speed=3.3, period=14, objs=[("car", 2.0, "racer", 2), ("car", 9.0, "racer", 2)]),
    9: dict(kind="road", dir=-1, speed=2.0, period=13, objs=[("car", 0.0, "pod", 1), ("car", 4.5, "pod", 1), ("car", 8.5, "pod", 1)]),
    8: dict(kind="road", dir=1, speed=1.5, period=15, objs=[("car", 2.0, "truck", 3), ("car", 9.0, "truck", 3)]),
    7: dict(kind="road", dir=-1, speed=2.5, period=14, objs=[("car", 3.0, "lorry", 4), ("car", 9.5, "lorry", 4)]),
    5: dict(kind="river", dir=-1, speed=1.3, period=13, objs=[("turtle", 0.0, 3, 1), ("turtle", 4.5, 3, 1), ("turtle", 9.0, 3, 0)], dphase=0),
    4: dict(kind="river", dir=1, speed=1.5, period=14, objs=[("log", 1.0, 3), ("log", 5.5, 3), ("log", 10.0, 3)]),
    3: dict(kind="river", dir=1, speed=2.3, period=15, objs=[("log", 1.0, 5), ("log", 9.0, 5)],
            alt=[("log", 1.0, 5), ("gator", 9.0)]),
    2: dict(kind="river", dir=-1, speed=1.7, period=13, objs=[("turtle", 1.0, 2, 1), ("turtle", 5.0, 2, 0), ("turtle", 9.5, 2, 1)], dphase=70),
    1: dict(kind="river", dir=1, speed=1.1, period=13, objs=[("log", 0.5, 2), ("log", 4.5, 2), ("log", 8.5, 2)]),
}
BAY_W, BAY_GAP = 115, 60
BAYS = [(BAY_GAP + i * (BAY_W + BAY_GAP), BAY_GAP + i * (BAY_W + BAY_GAP) + BAY_W) for i in range(5)]


# ---------------------------------------------------------------- backgrounds
def road_color(yy):
    s = math.sin(math.pi * yy / T)
    return (int(20 + 10 * s), int(22 + 11 * s), int(44 + 18 * s))


WATER_TOP, WATER_BOT = (14, 58, 140), (6, 26, 84)


def water_color(yy):
    return lerp(WATER_TOP, WATER_BOT, yy / T)


def water_pattern(period, f, seed):
    # One period of the drifting current; waves and sparkles are laid out once per lane and shifted per frame.
    rng = random.Random(seed)
    w = period * T
    im = Image.new("RGBA", (w, T), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    for y in range(T):
        d.line([(0, y), (w, y)], fill=water_color(y) + (255,))
    ov = Image.new("RGBA", (w, T), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i in range(period * 5):
        x0, y, ln = rng.randrange(w), rng.randrange(6, T - 6), rng.randrange(18, 56)
        x = (x0 + f * 7 + (i % 3) * f * 2) % w
        a = 70 + 60 * ((i + f) % 3 == 0)
        for xx, ll in ((x, ln), (x - w, ln)):
            od.line([(xx, y), (xx + ll, y)], fill=(120, 210, 255, a), width=2)
    for i in range(period * 3):
        x, y = rng.randrange(w), rng.randrange(4, T - 4)
        if (i + f) % 4 < 2:
            od.rectangle((x, y, x + 1, y + 1), fill=(230, 250, 255, 220))
    return Image.alpha_composite(im, ov)


def tile_strip(pattern, period, width):
    im = Image.new("RGBA", (width, pattern.height))
    for k in range(width // pattern.width + 2):
        im.paste(pattern, (k * pattern.width, 0))
    return im


def strip_with_objects(base, period, items):
    # items: (sprite_rgba, x_px). Placed with wrap copies so slicing at any offset sees complete objects.
    pw = period * T
    for sp, x in items:
        for k in (-1, 0, 1, 2):
            xx = int(round(x)) + k * pw
            if xx < base.width and xx + sp.width > 0:
                base.alpha_composite(sp, (max(0, xx), 0), (max(0, -xx), 0))
    return base


def build_lane_strips(row, lane, variant_objs, vi):
    period = lane["period"]
    sw = period * T + FW
    seed = row * 31 + 7
    kind = lane["kind"]
    out = []
    if kind == "road":
        frames = []
        for f in range(FRAMES):
            base = Image.new("RGBA", (sw, T))
            d = ImageDraw.Draw(base)
            for y in range(T):
                d.line([(0, y), (sw, y)], fill=road_color(y) + (255,))
            items = []
            for o in variant_objs:
                _, x0, ck, ci = o
                sp = car_img(ck, CAR_COLORS[ci], f)
                if lane["dir"] < 0:
                    sp = flip(sp)
                items.append((sp, x0 * T))
            im = strip_with_objects(base, period, items).crop((0, 6, sw, 66))
            frames.append(pack(im))
        out.append(frames)
        return out
    n_states = 4 if any(o[0] == "turtle" for o in variant_objs) else 1
    for state in range(n_states):
        frames = []
        for f in range(FRAMES):
            base = tile_strip(water_pattern(period, f, seed), period, sw)
            items = []
            for j, o in enumerate(variant_objs):
                if o[0] == "log":
                    sp = log_img(int(o[2] * T), seed + j)
                    items.append((sp, o[1] * T))
                elif o[0] == "gator":
                    sp = gator_img(f >= 2)
                    if lane["dir"] < 0:
                        sp = flip(sp)
                    items.append((sp, o[1] * T))
                else:
                    _, x0, n, diver = o
                    grp = Image.new("RGBA", (n * T, T), (0, 0, 0, 0))
                    for i in range(n):
                        st = state if diver else 0
                        grp.alpha_composite(turtle_img((f + i) % FRAMES, st), (i * T, 0))
                    if lane["dir"] < 0:
                        grp = flip(grp)
                    items.append((grp, x0 * T))
            frames.append(pack(strip_with_objects(base, period, items)))
        out.append(frames)
    return out


def build_field():
    im = Image.new("RGB", (FW, FH), (0, 0, 0))
    d = ImageDraw.Draw(im, "RGBA")
    rng = random.Random(3)
    for r in range(14):
        y0 = r * T
        if r in range(1, 6):
            for yy in range(T):
                d.line([(0, y0 + yy), (FW, y0 + yy)], fill=water_color(yy))
        elif r in range(7, 12):
            for yy in range(T):
                d.line([(0, y0 + yy), (FW, y0 + yy)], fill=road_color(yy))
        elif r == 6:
            for yy in range(T):
                d.line([(0, y0 + yy), (FW, y0 + yy)], fill=lerp((38, 18, 70), (24, 10, 48), yy / T))
            for hx in range(-1, 14):
                for hy in range(2):
                    cx = hx * 62 + (31 if hy else 0)
                    cy = y0 + 20 + hy * 33
                    pts = [(cx + 30 * math.cos(math.radians(60 * k + 30)), cy + 20 * math.sin(math.radians(60 * k + 30))) for k in range(6)]
                    d.polygon(pts, outline=(70, 40, 124, 255))
            for _ in range(40):
                x, y = rng.randrange(FW), y0 + rng.randrange(6, T - 6)
                d.rectangle((x, y, x + 1, y + 1), fill=(220, 180, 255, rng.randrange(120, 255)))
            for k in range(0, FW, 144):
                d.polygon([(k + 40, y0 + 62), (k + 44, y0 + 46), (k + 48, y0 + 62)], fill=(110, 230, 255, 255))
                d.polygon([(k + 50, y0 + 62), (k + 55, y0 + 50), (k + 59, y0 + 62)], fill=(200, 110, 255, 255))
        elif r == 12:
            for yy in range(T):
                d.line([(0, y0 + yy), (FW, y0 + yy)], fill=lerp((18, 26, 66), (10, 14, 40), yy / T))
            for x in range(0, FW, T):
                d.line([(x, y0), (x, y0 + T)], fill=(34, 48, 100, 255), width=2)
            for x in range(T // 2, FW, 2 * T):
                cx, cy = x, y0 + 36
                d.line([(cx - 14, cy + 8), (cx, cy - 8), (cx + 14, cy + 8)], fill=(80, 200, 255, 255), width=4)
                d.line([(cx - 14, cy + 22), (cx, cy + 6), (cx + 14, cy + 22)], fill=(60, 140, 220, 255), width=3)
            for _ in range(30):
                x, y = rng.randrange(FW), y0 + rng.randrange(T)
                d.rectangle((x, y, x + 1, y + 1), fill=(200, 220, 255, 160))
        elif r == 13:
            d.rectangle((0, y0, FW, y0 + T), fill=(0, 0, 0))
    # neon lane edges: the road lanes' separating lines live in rows the scrolling strips never touch.
    for lane_row in range(7, 12):
        y0 = lane_row * T
        for x in range(0, FW, 72):
            if lane_row < 11:
                d.rectangle((x, y0 + 69, x + 38, y0 + 71), fill=(170, 200, 255, 255))
            if lane_row > 7:
                d.rectangle((x, y0, x + 38, y0 + 2), fill=(170, 200, 255, 255))
    d.rectangle((0, 7 * T, FW, 7 * T + 5), fill=(255, 70, 190))
    d.rectangle((0, 7 * T + 6, FW, 7 * T + 8), fill=(120, 30, 100))
    d.rectangle((0, 12 * T - 6, FW, 12 * T - 1), fill=(60, 230, 255))
    d.rectangle((0, 12 * T - 9, FW, 12 * T - 7), fill=(20, 100, 130))
    d.rectangle((0, 6 * T, FW, 6 * T + 2), fill=(255, 70, 190))
    d.rectangle((0, 7 * T - 3, FW, 7 * T - 1), fill=(255, 70, 190))
    d.rectangle((0, 12 * T, FW, 12 * T + 3), fill=(60, 230, 255))
    d.rectangle((0, 13 * T, FW, 13 * T + 2), fill=(255, 70, 190))
    # home row: crystal hedge with glowing bays
    for yy in range(T):
        d.line([(0, yy), (FW, yy)], fill=lerp((52, 24, 104), (22, 10, 56), yy / T))
    for x in range(0, FW, 18):
        h = rng.randrange(14, 40)
        w = rng.randrange(10, 20)
        c = rng.choice([(150, 90, 240), (110, 70, 210), (90, 200, 255), (200, 90, 230)])
        d.polygon([(x, 0), (x + w / 2, h), (x + w, 0)], fill=c + (255,))
        d.polygon([(x + w / 2, 0), (x + w / 2 + 3, h * 0.7), (x + w, 0)], fill=(255, 255, 255, 60))
    d.rectangle((0, T - 8, FW, T - 1), fill=(255, 70, 190))
    d.rectangle((0, T - 11, FW, T - 9), fill=(110, 30, 110))
    for (l, r_) in BAYS:
        for yy in range(T):
            d.line([(l, yy), (r_, yy)], fill=lerp((8, 40, 110), (4, 20, 70), yy / T))
        d.rectangle((l - 3, 0, l - 1, T - 1), fill=(110, 230, 255))
        d.rectangle((r_ + 1, 0, r_ + 3, T - 1), fill=(110, 230, 255))
        d.rectangle((l, T - 4, r_, T - 1), fill=(80, 170, 230))
        for _ in range(7):
            x, y = rng.randrange(l + 4, r_ - 4), rng.randrange(8, T - 8)
            d.rectangle((x, y, x + 1, y), fill=(210, 240, 255))
    return pack(im)


def build_screen():
    rng = random.Random(11)
    w, h = 1920, 1080
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp((3, 2, 16), (16, 6, 44), y / h))
    neb = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    nd = ImageDraw.Draw(neb)
    for _ in range(26):
        cx, cy = rng.randrange(w), rng.randrange(h)
        rx, ry = rng.randrange(120, 320), rng.randrange(80, 220)
        col = rng.choice([(120, 40, 200), (30, 120, 220), (210, 40, 140), (40, 180, 190)])
        nd.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=col + (rng.randrange(30, 60),))
    neb = neb.filter(ImageFilter.GaussianBlur(70))
    im = Image.alpha_composite(im.convert("RGBA"), neb)
    d = ImageDraw.Draw(im)
    for _ in range(900):
        x, y = rng.randrange(w), rng.randrange(h)
        b = rng.randrange(90, 255)
        c = rng.choice([(b, b, b), (b, b, 255), (255, b, b), (255, 255, b // 2)])
        d.point((x, y), fill=c)
        if rng.random() < 0.25:
            d.point((x + 1, y), fill=c)
            d.point((x, y + 1), fill=c)
    for _ in range(40):
        x, y = rng.randrange(w), rng.randrange(h)
        d.line([(x - 6, y), (x + 6, y)], fill=(230, 240, 255, 200))
        d.line([(x, y - 6), (x, y + 6)], fill=(230, 240, 255, 200))
        d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(255, 255, 255))

    def planet(cx, cy, r, c1, c2, bands=0, ring=None, seed=0):
        pr = random.Random(seed)
        ss = 3
        layer = Image.new("RGBA", (int(r * 5 * ss), int(r * 5 * ss)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        c = r * 2.5 * ss
        if ring:
            ld.ellipse((c - r * 2.1 * ss, c - r * 0.55 * ss, c + r * 2.1 * ss, c + r * 0.55 * ss), outline=ring + (255,), width=int(r * 0.22 * ss))
        body = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(body)
        n = int(r * ss * 2)
        for i in range(n):
            t = i / n
            col = lerp(c1, c2, t)
            if bands:
                col = lerp(col, (255, 255, 255), 0.12 * math.sin(t * bands * 6.28))
            y = c - r * ss + i
            half = math.sqrt(max(0, (r * ss) ** 2 - (y - c) ** 2))
            bd.line([(c - half, y), (c + half, y)], fill=col + (255,))
        shade = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        for k in range(30):
            sd.ellipse((c - r * ss + k * r * ss * 0.05 + r * ss * 0.5, c - r * ss, c + r * ss * 2.2, c + r * ss), fill=(0, 0, 20, 7))
        mask = Image.new("L", layer.size, 0)
        ImageDraw.Draw(mask).ellipse((c - r * ss, c - r * ss, c + r * ss, c + r * ss), fill=255)
        shade.putalpha(ImageChops.multiply(shade.getchannel("A"), mask))
        body = Image.alpha_composite(body, shade)
        layer = Image.alpha_composite(layer, body)
        if ring:
            front = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            fd = ImageDraw.Draw(front)
            fd.arc((c - r * 2.1 * ss, c - r * 0.55 * ss, c + r * 2.1 * ss, c + r * 0.55 * ss), 0, 180, fill=ring + (255,), width=int(r * 0.22 * ss))
            layer = Image.alpha_composite(layer, front)
        layer = layer.resize((layer.width // ss, layer.height // ss), Image.LANCZOS)
        im.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))

    planet(250, 880, 120, (230, 190, 120), (120, 70, 50), bands=4, ring=(210, 180, 140), seed=1)
    planet(1700, 170, 90, (255, 140, 70), (120, 40, 60), bands=3, seed=2)
    planet(1640, 930, 46, (110, 200, 230), (30, 70, 140), seed=3)
    planet(120, 150, 30, (200, 200, 210), (80, 80, 100), seed=4)
    d = ImageDraw.Draw(im)
    for x0 in (30, 1470):
        d.rounded_rectangle((x0, 60, x0 + 420, 560), 14, fill=(0, 0, 0), outline=(90, 220, 255), width=3)
        d.rounded_rectangle((x0 + 8, 68, x0 + 412, 552), 10, outline=(255, 70, 190), width=1)
    for xe in (484, 1428):
        d.rectangle((xe, 30, xe + 7, 1050), fill=(60, 230, 255))
        d.rectangle((xe + 2, 30, xe + 4, 1050), fill=(220, 255, 255))
    return pack(im.convert("RGB"))


def main():
    data = {}
    data["screen"] = build_screen()
    data["field"] = build_field()
    data["bays"] = BAYS
    data["car_len"] = CAR_LEN
    data["lanes"] = LANES
    data["frog"] = frog_sprites()
    data["life"] = life_icon()
    data["squash"] = squash_sprites()
    data["splash"] = splash_sprites()
    data["pop"] = pop_sprites()
    data["fly"] = fly_sprites()
    data["croc"] = croc_sprites()
    snakes = []
    for ph in range(4):
        im = snake_img(ph)
        snakes.append([rle(flip(im)), rle(im)])      # [moving left, moving right]
    data["snake"] = snakes
    bay_frog = rle(down(frog_img(0).transpose(Image.ROTATE_180), (T, T)))
    data["bayfrog"] = bay_frog
    strips = {}
    for row, lane in LANES.items():
        variants = [lane["objs"]] + ([lane["alt"]] if "alt" in lane else [])
        strips[row] = [build_lane_strips(row, lane, v, vi) for vi, v in enumerate(variants)]
        print("lane", row, "done", flush=True)
    data["strips"] = strips
    save_bundle("g_frogger.bin", data)


if __name__ == "__main__":
    main()
