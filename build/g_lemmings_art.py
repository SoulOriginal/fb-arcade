# Lemmings sprites drawn procedurally at 1:1 virtual pixels (every virtual pixel is later shown as 5x5 screen pixels).
# A sprite is stored as run-length rows so the game can paste only opaque pixels into a row buffer: Python cannot
# afford a per-pixel transparency test, but pasting a few slices per row is cheap.
import math, random, struct
from PIL import Image, ImageDraw, ImageFont
from buildlib import BOLD, MONO

SCALE = 5
BPX = SCALE * 2          # bytes per virtual pixel in an expanded row

HAIR_D, HAIR = (0, 140, 40), (60, 225, 70)
SKIN, SKIN_D = (250, 205, 175), (210, 150, 120)
ROBE, ROBE_D, ROBE_L = (50, 70, 235), (25, 35, 170), (110, 130, 255)
WHITE = (255, 255, 255)
BRICK, BRICK_D = (235, 130, 40), (170, 80, 20)
GREY, GREY_D = (170, 170, 185), (100, 100, 120)
EYE = (20, 20, 40)


def expand(rgb):
    v = (rgb[0] >> 3) << 11 | (rgb[1] >> 2) << 5 | (rgb[2] >> 3)
    return struct.pack("<H", v) * SCALE


def to_sprite(img, ax=0, ay=0):
    # Opaque pixels (alpha >= 128) become runs of pre-expanded RGB565 bytes. (ax, ay) is the anchor inside the image.
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    cache = {}
    rows = []
    for y in range(h):
        runs, x = [], 0
        while x < w:
            if px[x, y][3] < 128:
                x += 1
                continue
            x0, buf = x, bytearray()
            while x < w and px[x, y][3] >= 128:
                c = px[x, y][:3]
                if c not in cache:
                    cache[c] = expand(c)
                buf += cache[c]
                x += 1
            runs.append((x0 * BPX, bytes(buf)))
        rows.append(runs)
    return {"w": w, "h": h, "ax": ax, "ay": ay, "runs": rows}


def flip(img):
    return img.transpose(Image.FLIP_LEFT_RIGHT)


class Canvas:
    def __init__(self, w=17, h=20):
        self.im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def p(self, x, y, c):
        if 0 <= x < self.im.width and 0 <= y < self.im.height:
            self.im.putpixel((x, y), c + (255,))

    def r(self, x0, y0, x1, y1, c):
        self.d.rectangle((x0, y0, x1, y1), fill=c + (255,))

    def l(self, x0, y0, x1, y1, c):
        self.d.line((x0, y0, x1, y1), fill=c + (255,))


CX, FY = 8, 19


def head_side(c, b):
    c.r(CX - 1, 9 + b, CX + 2, 9 + b, HAIR_D)
    c.r(CX - 2, 10 + b, CX + 2, 10 + b, HAIR)
    c.p(CX - 2, 9 + b, HAIR)
    c.r(CX, 11 + b, CX + 3, 11 + b, SKIN)
    c.p(CX + 2, 11 + b, EYE)
    c.r(CX - 1, 12 + b, CX + 2, 12 + b, SKIN)
    c.p(CX - 1, 11 + b, HAIR_D)


def head_front(c, b, mouth=False):
    c.r(CX - 1, 9 + b, CX + 1, 9 + b, HAIR_D)
    c.r(CX - 2, 10 + b, CX + 2, 10 + b, HAIR)
    c.r(CX - 2, 11 + b, CX + 2, 11 + b, SKIN)
    c.p(CX - 1, 11 + b, EYE)
    c.p(CX + 1, 11 + b, EYE)
    c.r(CX - 1, 12 + b, CX + 1, 12 + b, SKIN_D if mouth else SKIN)
    if mouth:
        c.p(CX, 12 + b, (200, 40, 60))


def robe_side(c, b, top=13, bot=16):
    c.r(CX - 2, top + b, CX + 2, top + b, ROBE)
    for y in range(top + 1, bot + 1):
        c.r(CX - 3, y + b, CX + 3, y + b, ROBE)
        c.r(CX - 3, y + b, CX - 2, y + b, ROBE_D)
    c.p(CX + 2, top + b, ROBE_L)


def robe_front(c, b, top=13, bot=16):
    c.r(CX - 2, top + b, CX + 2, top + b, ROBE)
    for y in range(top + 1, bot + 1):
        c.r(CX - 3, y + b, CX + 3, y + b, ROBE)
        c.p(CX - 3, y + b, ROBE_D)
        c.p(CX + 3, y + b, ROBE_D)
    c.p(CX, top + b + 1, ROBE_L)


def legs(c, a, b, lift_a=0, lift_b=0, top=17):
    for x, lift in ((CX + a, lift_a), (CX - a, lift_b)):
        c.l(CX, top, x, FY - lift, ROBE_D if x < CX else (30, 40, 200))
        c.p(x + 1, FY - lift, SKIN_D)
        c.p(x, FY - lift, SKIN)


def walk(f):
    c = Canvas()
    s = (-2, -1, 0, 1, 2, 1, 0, -1)[f]
    b = 1 if f in (2, 6) else 0
    head_side(c, b)
    robe_side(c, b)
    legs(c, s, b and 0 or 0, 1 if f in (6, 7, 0, 1) else 0, 1 if f in (2, 3, 4, 5) else 0, 17 + b)
    c.p(CX + 2 - s // 2, 14 + b, SKIN)
    c.p(CX + 2 - s // 2, 15 + b, SKIN_D)
    return c.im


def fall(f):
    c = Canvas()
    head_front(c, 0, mouth=True)
    robe_front(c, 0, 13, 15)
    up = f % 2
    for sx in (-1, 1):
        c.p(CX + sx * 3, 12 - up, SKIN)
        c.p(CX + sx * 4, 11 - up, SKIN)
        c.p(CX + sx * 3, 13, ROBE_L)
    c.l(CX - 1, 16, CX - 2 - up, 18, ROBE_D)
    c.l(CX + 1, 16, CX + 2 + up, 18, ROBE_D)
    return c.im


def umbrella(c, k, sway=0):
    # k = 0..3 opening progress; the dome is yellow and red like the original parasol
    half = (1, 3, 5, 7)[k]
    top = (7, 5, 3, 2)[k] if k < 3 else 1
    for i in range(-half, half + 1):
        h = int(round(math.sqrt(max(0, 1 - (i / (half + 0.5)) ** 2)) * (3 if k else 1)))
        for j in range(h + 1):
            col = (255, 70, 60) if (i // 2) % 2 == 0 else (255, 230, 80)
            c.p(CX + i + sway, top + 3 - j, col)
        c.p(CX + i + sway, top + 4, (120, 30, 20))
    if k >= 2:
        c.l(CX + sway, top + 5, CX, 9, (160, 160, 170))


def floater(f):
    c = Canvas(17, 20)
    k = min(f, 3)
    sway = 0
    if f >= 4:
        sway = 0
    b = 0
    head_front(c, b)
    robe_front(c, b, 13, 16)
    c.p(CX - 3, 12, SKIN)
    c.p(CX + 3, 12, SKIN)
    c.p(CX - 3, 11, SKIN)
    c.p(CX + 3, 11, SKIN)
    s = 1 if f % 2 else 0
    c.l(CX - 1, 17, CX - 1 - s, 19, ROBE_D)
    c.l(CX + 1, 17, CX + 1 + s, 19, ROBE_D)
    umbrella(c, k)
    return c.im


def climb(f):
    # facing right at a wall that is two pixels in front of the body; hands reach up alternately
    c = Canvas()
    b = 0
    c.r(CX - 1, 9, CX + 2, 9, HAIR_D)
    c.r(CX - 1, 10, CX + 2, 10, HAIR)
    c.r(CX, 11, CX + 3, 12, SKIN)
    c.p(CX + 2, 11, EYE)
    for y in range(13, 17):
        c.r(CX - 2, y, CX + 2, y, ROBE)
    c.r(CX - 2, 13, CX - 1, 16, ROBE_D)
    ph = f % 4
    up = (0, 2, 4, 2)[ph]
    c.l(CX + 3, 8 + up // 2 * 0 + 2 - up // 2, CX + 3, 13, SKIN)
    c.p(CX + 4, 7 + (4 - up) // 2, SKIN)
    c.l(CX + 3, 14, CX + 4, 14 + (up // 2), SKIN_D)
    for x, lift in ((CX + 1, up // 2), (CX - 1, 1 - up // 2)):
        c.l(x, 17, x + 1, 18 - lift, ROBE_D)
        c.p(x + 1, 19 - lift, SKIN_D)
    return c.im


def hoist(f):
    c = Canvas()
    y = 4 - f
    c.r(CX - 1, 12 - f, CX + 2, 13 - f, HAIR)
    c.r(CX, 14 - f, CX + 3, 14 - f, SKIN)
    for yy in range(15 - f, 19):
        c.r(CX - 2, yy, CX + 2, yy, ROBE)
    c.r(CX + 3, 15 - f, CX + 5, 15 - f, SKIN)
    c.l(CX - 1, 19, CX + 1, 19, SKIN_D)
    return c.im


def builder(f):
    # 0..7: walk-bob while carrying a brick; brick laid at frame 4
    c = Canvas()
    b = 1 if f in (2, 6) else 0
    head_side(c, b)
    robe_side(c, b)
    s = (-1, 0, 1, 0, -1, 0, 1, 0)[f]
    legs(c, s, 0, 0, 0, 17 + b)
    fx = CX + 3
    if f < 4:
        c.r(fx, 13 + b, fx + 2, 14 + b, BRICK)
        c.r(fx, 14 + b, fx + 2, 14 + b, BRICK_D)
    else:
        c.p(fx, 15 + b, SKIN)
        c.p(fx + 1, 16, SKIN)
        if f == 4:
            c.r(fx, 17 + b, fx + 3, 17 + b, BRICK)
    return c.im


def shrug(f):
    c = Canvas()
    head_front(c, 0)
    robe_front(c, 0, 13, 16)
    o = 1 if f in (1, 2) else 0
    c.p(CX - 4, 14 - o, SKIN)
    c.p(CX + 4, 14 - o, SKIN)
    c.p(CX - 3, 14, ROBE_L)
    c.p(CX + 3, 14, ROBE_L)
    legs(c, 1, 0)
    return c.im


def basher(f):
    c = Canvas()
    head_side(c, 1)
    for y in range(14, 17):
        c.r(CX - 3, y, CX + 2, y, ROBE)
    c.r(CX - 3, 14, CX - 2, 16, ROBE_D)
    sw = (0, 1, 2, 3, 4, 3, 2, 1)[f]
    c.r(CX + 2, 14, CX + 3 + sw, 14, SKIN)
    c.r(CX + 2, 15, CX + 3 + sw, 15, SKIN_D)
    legs(c, 2, 0, 0, 0, 17)
    return c.im


def miner(f):
    c = Canvas()
    head_side(c, 1)
    for y in range(14, 17):
        c.r(CX - 3, y, CX + 2, y, ROBE)
    c.r(CX - 3, 14, CX - 2, 16, ROBE_D)
    a = f % 4
    hx, hy = CX + 3, 15
    tx, ty = hx + (2, 3, 4, 3)[a], hy + (-4, -1, 3, 1)[a]
    c.l(hx, hy, tx, ty, (150, 100, 50))
    c.r(tx - 1, ty - 1, tx + 1, ty + 1, GREY)
    c.p(tx + 1, ty, WHITE)
    legs(c, 1, 0, 0, 0, 17)
    return c.im


def digger(f):
    c = Canvas()
    head_front(c, 1)
    robe_front(c, 1, 14, 16)
    s = f % 2
    c.p(CX - 3, 15, SKIN)
    c.p(CX + 3, 15, SKIN)
    c.l(CX - 3, 16, CX - 3 - s, 19, GREY)
    c.l(CX + 3, 16, CX + 3 + (1 - s), 19, GREY)
    c.r(CX - 3 - s, 18, CX - 2 - s, 19, GREY_D)
    c.l(CX - 1, 17, CX - 1, 19, ROBE_D)
    c.l(CX + 1, 17, CX + 1, 19, ROBE_D)
    if s:
        c.p(CX - 5, 19, (230, 110, 40))
    else:
        c.p(CX + 5, 19, (230, 110, 40))
    return c.im


def blocker(f):
    c = Canvas()
    head_front(c, 0)
    robe_front(c, 0, 13, 17)
    o = 1 if f in (1, 2) else 0
    c.r(CX - 6, 14 - o, CX - 3, 14 - o, ROBE)
    c.r(CX + 3, 14 - o, CX + 6, 14 - o, ROBE)
    c.p(CX - 7, 14 - o, WHITE)
    c.p(CX + 7, 14 - o, WHITE)
    c.p(CX - 7, 15 - o, WHITE)
    c.p(CX + 7, 15 - o, WHITE)
    c.l(CX - 1, 18, CX - 1, 19, ROBE_D)
    c.l(CX + 1, 18, CX + 1, 19, ROBE_D)
    return c.im


def ohno(f):
    c = Canvas()
    head_front(c, 0, mouth=True)
    robe_front(c, 0, 13, 16)
    c.l(CX + 3, 13, CX + 3, 7 - (f % 2), SKIN)
    c.p(CX - 3, 14, SKIN)
    legs(c, 1, 0)
    return c.im


def exit_frame(f):
    c = Canvas()
    head_front(c, 0, mouth=False)
    robe_front(c, 0, 13, 16)
    j = (0, 1, 2, 1, 0, 1, 2, 1)[f]
    c.l(CX - 3, 13, CX - 4, 8 - j, SKIN)
    c.l(CX + 3, 13, CX + 4, 8 - j, SKIN)
    legs(c, 1, 0, j, j)
    return c.im


def drown(f):
    c = Canvas()
    head_front(c, 5, mouth=True)
    for y in range(18, 20):
        c.r(CX - 3, y, CX + 3, y, ROBE)
    j = f % 2
    c.l(CX - 3, 17, CX - 4, 12 + j, SKIN)
    c.l(CX + 3, 17, CX + 4, 12 + (1 - j), SKIN)
    if f > 4:
        c.im.paste((0, 0, 0, 0), (0, 14, 17, 20))
    return c.im


def burn(f):
    c = Canvas()
    rnd = random.Random(f)
    c.l(CX, 10, CX, 17, (30, 20, 20))
    c.l(CX - 3, 12, CX + 3, 12, (30, 20, 20))
    c.l(CX - 1, 17, CX - 3, 19, (30, 20, 20))
    c.l(CX + 1, 17, CX + 3, 19, (30, 20, 20))
    c.r(CX - 1, 8, CX + 1, 10, (50, 40, 40))
    for _ in range(26):
        x, y = CX + rnd.randint(-4, 4), 19 - rnd.randint(0, 13)
        c.p(x, y, rnd.choice(((255, 220, 60), (255, 140, 30), (230, 60, 20))))
    return c.im


def splat(f):
    # lemming "pops" into pink and blue gibs that spread sideways along the ground
    c = Canvas(25, 20)
    rnd = random.Random(7)
    t = min(f, 7)
    for i in range(30):
        a = rnd.random() * math.pi
        r = (0.4 + rnd.random()) * (2 + t * 1.3)
        x = 12 + int(math.cos(a) * r * 1.5)
        y = 19 - int(math.sin(a) * r * 0.8)
        col = rnd.choice((SKIN, SKIN, HAIR, ROBE, ROBE_D, (230, 40, 40)))
        c.r(x, y, x + (i % 2), y, col)
        if t > 2:
            c.p(x, 19, col)
    return c.im


def explosion(f):
    # lemming parts and sparks flying out of the centre under gravity
    n = 34
    c = Canvas(41, 41)
    rnd = random.Random(11)
    t = f
    for i in range(18):
        a = rnd.random() * 2 * math.pi
        v = 0.8 + rnd.random() * 1.7
        x = 20 + math.cos(a) * v * t * 1.1
        y = 25 + math.sin(a) * v * t * 1.0 + 0.04 * t * t * 3
        col = rnd.choice(((255, 255, 255), (255, 220, 60), (255, 140, 30), HAIR, ROBE, SKIN))
        s = 1 if f < 7 else 0
        c.r(int(x), int(y), int(x) + s, int(y) + s, col)
        if f > 12 and i % 2:
            c.im.putpixel((int(max(0, min(40, x))), int(max(0, min(40, y)))), (0, 0, 0, 0))
    return c.im


def flame(f, w=8, h=14):
    c = Canvas(w, h)
    rnd = random.Random(f * 31 + 5)
    for x in range(w):
        hh = h - 3 - rnd.randint(0, 5) - (3 if x in (0, w - 1) else 0)
        for j in range(max(2, hh)):
            frac = j / max(2, hh)
            col = (255, 230, 80) if frac < 0.35 else (255, 140, 30) if frac < 0.75 else (225, 50, 20)
            c.p(x, h - 1 - j, col)
    return c.im


def torch(f):
    c = Canvas(7, 14)
    c.r(3, 6, 4, 13, (120, 70, 30))
    c.r(2, 6, 5, 7, (80, 80, 90))
    fl = flame(f, 5, 7)
    c.im.alpha_composite(fl, (1, 0))
    return c.im


def digit_sprites():
    f = ImageFont.truetype(BOLD, 10)
    out = {}
    for ch in "0123456789":
        im = Image.new("RGBA", (8, 11), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.fontmode = "1"
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            d.text((1 + dx, 0 + dy), ch, font=f, fill=(0, 0, 0, 255))
        d.text((1, 0), ch, font=f, fill=(255, 255, 255, 255))
        out[ch] = im
    return out


FONT_CACHE = {}


def glyph(ch, size, color, outline=None, mono=False):
    key = (ch, size, color, outline, mono)
    if key not in FONT_CACHE:
        f = ImageFont.truetype(MONO if mono else BOLD, size)
        w = int(f.getlength(ch)) + 3
        im = Image.new("RGBA", (w, size + 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.fontmode = "1"
        if outline:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                d.text((1 + dx, 1 + dy), ch, font=f, fill=outline + (255,))
        d.text((1, 1), ch, font=f, fill=color + (255,))
        FONT_CACHE[key] = im
    return FONT_CACHE[key]


def font_set(size, color, outline=None, mono=False):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789%-:.!',+/"
    glyphs, adv = {}, {}
    for ch in chars:
        g = glyph(ch, size, color, outline, mono)
        glyphs[ch] = to_sprite(g)
        adv[ch] = g.width - 1
    f = ImageFont.truetype(MONO if mono else BOLD, size)
    return {"glyphs": glyphs, "adv": adv, "space": int(f.getlength(" ")) + 2, "h": size + 4}


def crosshair():
    # dotted cross with a gap in the middle, green and white like the original pointer
    c = Canvas(11, 11)
    for i in range(0, 5):
        if i % 2 == 0:
            for a in ((5, i), (5, 10 - i), (i, 5), (10 - i, 5)):
                c.p(a[0], a[1], (80, 255, 80))
    c.p(5, 3, WHITE)
    c.p(5, 7, WHITE)
    c.p(3, 5, WHITE)
    c.p(7, 5, WHITE)
    return c.im


def cursor_box():
    c = Canvas(13, 13)
    for x, y in ((0, 0), (12, 0), (0, 12), (12, 12)):
        pass
    for i in range(13):
        if i < 4 or i > 8:
            for a in ((i, 0), (i, 12), (0, i), (12, i)):
                c.p(a[0], a[1], WHITE)
    return c.im


def entrance(w=40, h=24):
    # frames 0..5: closed hatch to wide open window showing sky; red curtains at both sides
    out = []
    for f in range(6):
        c = Canvas(w, h)
        c.r(0, 0, w - 1, 4, (105, 100, 120))
        c.r(0, 0, w - 1, 0, (160, 155, 175))
        c.r(0, 4, w - 1, 4, (60, 55, 70))
        inner0, inner1 = 7, w - 8
        c.r(inner0, 5, inner1, h - 7, (20, 20, 30))
        op = f / 5.0
        gap = int((inner1 - inner0 - 2) / 2 * op)
        mid = (inner0 + inner1) // 2
        # window sky inside the opened gap
        if gap > 0:
            for y in range(5, h - 7):
                for x in range(mid - gap, mid + gap):
                    t = (y - 5) / (h - 12)
                    c.p(x, y, (int(60 + 60 * t), int(120 + 80 * t), 235))
            c.r(mid - gap + 2, 8, mid - gap + 7, 9, WHITE)
            c.r(mid + gap - 8, 10, mid + gap - 3, 11, (230, 240, 255))
        # hatch halves
        c.r(inner0, 5, mid - gap - 1, h - 7, (120, 110, 130))
        c.r(mid + gap, 5, inner1, h - 7, (120, 110, 130))
        c.r(inner0, h - 8, inner1, h - 7, (70, 65, 80))
        for cxx, sgn in ((0, 1), (w - 7, -1)):
            for y in range(4, h):
                for x in range(7):
                    shade = (150, 20, 25) if (x + (y // 3)) % 3 else (205, 40, 40)
                    if x == 0 or x == 6:
                        shade = (95, 10, 15)
                    c.p(cxx + x, y, shade)
        c.r(0, h - 3, 6, h - 1, (95, 10, 15))
        c.r(w - 7, h - 3, w - 1, h - 1, (95, 10, 15))
        out.append(c.im)
    return out


def exit_door(w=30, h=26):
    # stone arch, glowing doorway and two torches; 4 flame frames
    out = []
    for f in range(4):
        c = Canvas(w, h)
        for y in range(8, h):
            c.r(2, y, 7, y, (115, 105, 110))
            c.r(w - 8, y, w - 3, y, (115, 105, 110))
            c.p(2, y, (70, 62, 70))
            c.p(w - 3, y, (70, 62, 70))
        for i in range(0, w - 4):
            ang = math.pi * i / (w - 5)
            ox = 2 + int(round((w - 5) / 2 * (1 - math.cos(ang))))
            oy = 8 - int(round(8 * math.sin(ang))) + 2
            for k in range(4):
                c.p(ox, oy + k, (140, 128, 135) if k else (170, 160, 165))
        c.r(8, 11, w - 9, h - 1, (40, 25, 15))
        for y in range(11, h):
            for x in range(8, w - 8):
                t = (y - 11) / (h - 12)
                if (x * 3 + y * 5 + f * 7) % 7 < 3 + int(4 * t):
                    c.p(x, y, (255, int(150 + 80 * t), 40) if t > .3 else (200, 70, 20))
                else:
                    c.p(x, y, (110, 40, 15))
        t = torch(f)
        c.im.alpha_composite(t, (0, 0))
        c.im.alpha_composite(torch((f + 2) % 4), (w - 7, 0))
        out.append(c.im)
    return out


def water(w, h, f):
    c = Canvas(w, h)
    for y in range(h):
        for x in range(w):
            wave = int(1.5 * math.sin((x + f * 2) * 0.55))
            if y < 1 + (wave > 0):
                col = (190, 210, 255)
            elif y < 3:
                col = (70, 110, 245)
            else:
                col = (40, 70, 215) if (x + y + f) % 9 else (70, 110, 245)
            c.p(x, y, col)
    for x in range(0, w, 7):
        c.p((x + f * 3) % w, 0, WHITE)
    return c.im


def fire_pit(w, h, f):
    c = Canvas(w, h)
    rnd = random.Random(f * 13 + w)
    for x in range(w):
        hh = h - rnd.randint(0, 5) - (2 if x % 5 == 0 else 0)
        for j in range(hh):
            fr = j / hh
            col = (255, 235, 90) if fr < 0.3 else (255, 150, 30) if fr < 0.7 else (220, 50, 20)
            c.p(x, h - 1 - j, col)
    return c.im


def crusher(f, w=16, h=52):
    # frames 0..11: stone block on a chain: raised (0-3), slams down (4-6), stays (7), rises (8-11)
    c = Canvas(w, h)
    drop = (0, 0, 2, 6, 18, 26, 26, 26, 18, 10, 4, 2)[f % 12]
    c.r(w // 2 - 1, 0, w // 2, 6 + drop, (110, 110, 120))
    c.r(0, 6 + drop, w - 1, 13 + drop, (140, 130, 130))
    c.r(0, 6 + drop, w - 1, 6 + drop, (190, 180, 180))
    c.r(0, 13 + drop, w - 1, 13 + drop, (80, 70, 75))
    for x in range(0, w, 4):
        c.p(x, 14 + drop, (210, 210, 220))
        c.p(x + 1, 15 + drop, (210, 210, 220))
    return c.im
