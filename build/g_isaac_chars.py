# Build-time art, part 1: Isaac himself, tears, bombs, explosions, pickups, HUD icons. Everything is drawn from scratch.
import math, random
from PIL import Image, ImageDraw
from g_isaac_art import *

SKIN = (247, 224, 208, 255)
SKIN_SH = (226, 190, 176, 255)
BLUSH = (240, 150, 150, 255)
TEARC = (150, 205, 255, 255)
TEAR_HI = (230, 246, 255, 255)
WHITE = (252, 250, 248, 255)
SHIRT = (236, 234, 238, 255)
SHIRT_SH = (196, 192, 204, 255)
BLOOD = (196, 36, 40, 255)
BLOOD_DK = (120, 16, 26, 255)
BLOOD_HI = (240, 96, 90, 255)

HEAD_W, HEAD_H = 96, 92
HEAD_C = (48, 48)


def eye(p, cx, cy, rx, ry, look=(0, 0), wide=False, squint=False):
    if squint:
        # hurt: eyes squeezed into "> <" strokes
        p.line([(cx - rx, cy - ry * 0.7), (cx + rx * 0.5, cy), (cx - rx, cy + ry * 0.7)], OUT, 2.6)
        return
    p.ell(cx, cy, rx + 1.8, ry + 1.8, fill=OUT)
    p.ell(cx, cy, rx, ry, fill=WHITE)
    px, py = cx + look[0] * rx * 0.45, cy + look[1] * ry * 0.4
    pr = rx * (0.62 if wide else 0.5)
    p.ell(px, py, pr, pr * 1.25, fill=(18, 12, 20, 255))
    p.ell(px - pr * 0.3, py - pr * 0.45, pr * 0.28, pr * 0.28, fill=WHITE)
    # heavy upper lid: gives the permanently sad Isaac look
    p.poly([(cx - rx - 1, cy - ry * 0.2), (cx + rx + 1, cy - ry * 0.2), (cx + rx + 1, cy - ry - 2),
            (cx - rx - 1, cy - ry - 2)], fill=None)
    p.line([(cx - rx - 1, cy - ry * 0.55), (cx + rx + 1, cy - ry * 0.25)], OUT, 1.6)


def tear_stream(p, x, y0, y1, w=3.4):
    p.line([(x, y0), (x + 0.5, y1)], TEARC, w)
    p.line([(x - 0.6, y0 + 2), (x - 0.4, y1 - 3)], TEAR_HI, 1.1)
    p.ell(x + 0.5, y1, w * 0.62, w * 0.8, fill=TEARC, outline=OUT, w=0.7)


def head(direction, state):
    p = Pen(HEAD_W, HEAD_H)
    cx, cy = HEAD_C
    squint = state == "h"
    wide = state == "s"
    p.blob(cx, cy, 39, 35, SKIN)
    p.arc(cx, cy, 33, 29, 20, 160, SKIN_SH, 4)
    if direction == "d":
        look = (0, 0.4 if wide else 0.2)
        eye(p, cx - 15, cy - 1, 11, 14, look, wide, squint)
        eye(p, cx + 15, cy - 1, 11, 14, look, wide, squint)
        for sx in (-1, 1):
            p.ell(cx + sx * 27, cy + 13, 6, 3.6, fill=BLUSH)
            tear_stream(p, cx + sx * 20, cy + 14, cy + 29 if not wide else cy + 25)
        if state == "n":
            p.arc(cx, cy + 25, 8, 5, 200, 340, OUT, 2)
        elif state == "s":
            p.ell(cx, cy + 25, 5.5, 6.5, fill=(90, 20, 34, 255), outline=OUT, w=1.4)
        else:
            p.ell(cx, cy + 25, 9, 7, fill=(90, 20, 34, 255), outline=OUT, w=1.6)
        for dx in (-9, 0, 8):
            p.line([(cx + dx, cy - 33), (cx + dx * 1.2, cy - 41)], OUT, 1.6)
    elif direction == "u":
        p.ell(cx - 38, cy + 2, 7, 10, fill=SKIN, outline=OUT, w=1.6)
        p.ell(cx + 38, cy + 2, 7, 10, fill=SKIN, outline=OUT, w=1.6)
        p.arc(cx, cy, 30, 26, 200, 340, SKIN_SH, 3)
        for dx in (-14, -4, 6, 15):
            p.line([(cx + dx, cy - 20), (cx + dx * 1.1, cy - 33)], OUT, 1.7)
        if squint:
            p.line([(cx - 10, cy + 20), (cx + 10, cy + 20)], OUT, 2)
    else:
        # right-facing profile: one big eye near the front edge, nose bump, ear at the back
        p.ell(cx - 24, cy + 6, 8, 11, fill=SKIN_SH, outline=OUT, w=1.6)
        eye(p, cx + 14, cy - 1, 12, 15, (0.8, 0.2), wide, squint)
        p.ell(cx + 36, cy + 9, 6, 5, fill=SKIN, outline=OUT, w=1.5)
        p.ell(cx + 23, cy + 16, 5.5, 3.5, fill=BLUSH)
        tear_stream(p, cx + 20, cy + 15, cy + 30)
        if state == "s":
            p.ell(cx + 29, cy + 23, 4.5, 5.5, fill=(90, 20, 34, 255), outline=OUT, w=1.3)
        else:
            p.arc(cx + 25, cy + 25, 7, 4, 200, 340, OUT, 2)
        for dx in (-12, -2, 7):
            p.line([(cx + dx, cy - 33), (cx + dx * 1.1, cy - 41)], OUT, 1.6)
    return p.done()


def body(view, frame):
    p = Pen(60, 60)
    ph = frame / 6 * 2 * math.pi
    s = math.sin(ph)
    cx = 30
    if view == "v":
        # legs under the shirt
        for sx, lift in ((-1, s), (1, -s)):
            y = 46 - max(0.0, lift) * 5
            p.blob(cx + sx * 7, y, 5.2, 6.2, SKIN, ow=1.6)
        p.blob(cx, 32, 14, 14, SHIRT)
        p.arc(cx, 32, 10, 9, 20, 160, SHIRT_SH, 3)
        for sx in (-1, 1):
            p.blob(cx + sx * 17, 32 + s * sx * 3, 4, 7, SKIN, ow=1.6)
    else:
        for sgn, lift in ((1, s), (-1, -s)):
            x = cx + sgn * s * 7
            p.blob(x, 46 - max(0.0, lift * sgn) * 4, 5.4, 6.2, SKIN, ow=1.6)
        p.blob(cx, 32, 11, 14, SHIRT)
        p.blob(cx + s * -4, 32, 3.8, 7, SKIN, ow=1.6)
    return p.done()


def dead():
    # Isaac collapsed on the floor, crying a puddle
    p = Pen(170, 130)
    p.ell(85, 100, 66, 16, fill=(150, 200, 250, 255))
    p.ell(85, 98, 56, 11, fill=TEARC)
    p.blob(128, 86, 11, 15, SHIRT)
    p.blob(142, 90, 6, 6, SKIN, ow=1.6)
    h = head("d", "h").rotate(70, resample=Image.BICUBIC, expand=True)
    im = p.done()
    im.alpha_composite(h, (4, 12))
    return im


def tear_img(r, color, hi, dark):
    n = int(r * 2 + 8)
    p = Pen(n, n)
    c = n / 2
    # a teardrop: round bottom, small point at the top
    p.poly([(c, 1.5), (c - r * 0.75, c), (c + r * 0.75, c)], fill=dark)
    p.ell(c, c + 1, r + 1.4, r + 1.4, fill=dark)
    p.poly([(c, 3.2), (c - r * 0.65, c), (c + r * 0.65, c)], fill=color)
    p.ell(c, c + 1, r, r, fill=color)
    p.ell(c - r * 0.35, c - r * 0.1, r * 0.3, r * 0.4, fill=hi)
    return p.done()


def splash(r, frame, color, dark):
    n = int(r * 4 + 10)
    p = Pen(n, n)
    c = n / 2
    k = (frame + 1) / 4
    for i in range(7):
        a = i / 7 * 2 * math.pi + 0.3
        d = r * (0.9 + 1.2 * k)
        sz = max(1.4, r * 0.45 * (1.15 - k * 0.6))
        p.ell(c + math.cos(a) * d, c + math.sin(a) * d * 0.8, sz + 0.9, sz + 0.9, fill=dark)
        p.ell(c + math.cos(a) * d, c + math.sin(a) * d * 0.8, sz, sz, fill=color)
    p.ell(c, c, r * (1.1 - 0.3 * k), r * (0.8 - 0.2 * k), fill=color)
    return p.done()


def bomb_img(frame):
    p = Pen(60, 64)
    p.ell(30, 56, 17, 5, fill=(0, 0, 0, 0))
    body_c = (46, 44, 56, 255) if frame % 2 == 0 else (150, 40, 40, 255)
    p.blob(30, 38, 17, 16, body_c)
    p.ell(24, 31, 5, 4, fill=(120, 120, 140, 255) if frame % 2 == 0 else (255, 160, 140, 255))
    p.rect(26, 15, 34, 24, fill=(96, 84, 80, 255), outline=OUT, w=1.4, r=2)
    p.line([(30, 15), (36, 8), (40, 9)], (210, 190, 150, 255), 2.2)
    p.ell(41, 8, 3.6, 3.6, fill=(255, 220, 90, 255))
    p.ell(41, 8, 1.8, 1.8, fill=(255, 255, 230, 255))
    # skull mark
    p.ell(30, 40, 4.2, 4.2, fill=(230, 226, 220, 255))
    p.rect(28, 43, 32, 47, fill=(230, 226, 220, 255))
    return p.done()


def explosion(frame):
    n = 300
    p = Pen(n, n)
    c = n / 2
    k = [0.35, 0.65, 0.9, 1.0, 0.85, 0.6][frame]
    rr = 118 * k
    cols = [(255, 250, 210), (255, 214, 90), (255, 140, 40), (200, 60, 30), (90, 40, 36)]
    rnd = random.Random(frame * 17 + 3)
    if frame < 4:
        for i in range(5):
            f = 1 - i * 0.17
            p.ell(c, c, rr * f * 1.05, rr * f * 0.9, fill=cols[min(4, i + (1 if frame > 2 else 0))] + (255,))
    for i in range(12):
        a = i / 12 * 2 * math.pi + rnd.random()
        d = rr * (0.9 + 0.5 * rnd.random())
        s = 14 * (1.2 - k * 0.5)
        p.ell(c + math.cos(a) * d, c + math.sin(a) * d * 0.85, s, s, fill=(60, 50, 56, 255))
    if frame >= 4:
        for i in range(10):
            a = i / 10 * 2 * math.pi
            p.ell(c + math.cos(a) * rr * 0.8, c + math.sin(a) * rr * 0.7, 26, 22, fill=(70, 64, 72, 255))
    return p.done()


def heart_shape(p, cx, cy, s, fill, outline=OUT, ow=1.6, hi=True):
    pts = []
    for i in range(60):
        t = i / 60 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * s / 36, cy + (y - 2.5) * s / 36))
    big = [(cx + (x - cx) * 1.13, cy + (y - cy) * 1.13) for x, y in pts]
    p.poly(big, fill=outline)
    p.poly(pts, fill=fill)
    if hi:
        p.ell(cx - s * 0.38, cy - s * 0.3, s * 0.13, s * 0.19, fill=mix(fill, (255, 255, 255), 0.7))


def heart_icon(kind, size=44):
    # kind: full, half, empty (red), soul, soul_half, soul_empty not needed
    p = Pen(size, size)
    c = size / 2
    s = size * 0.9
    red, redd = (214, 38, 48, 255), (110, 16, 26, 255)
    if kind in ("full", "half", "empty"):
        heart_shape(p, c, c + 1, s, (70, 30, 36, 255) if kind != "full" else red, hi=kind == "full")
        if kind == "half":
            half = Pen(size, size)
            heart_shape(half, c, c + 1, s, red)
            im = half.done()
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).rectangle([0, 0, size // 2, size], fill=255)
            base = p.done()
            base.paste(im, (0, 0), Image.composite(im.split()[3], Image.new("L", (size, size), 0), mask))
            return base
    else:
        col = (150, 190, 255, 255)
        heart_shape(p, c, c + 1, s, (50, 60, 90, 255) if kind == "soul_empty" else col, hi=kind == "soul")
        if kind == "soul_half":
            half = Pen(size, size)
            heart_shape(half, c, c + 1, s, col)
            im = half.done()
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).rectangle([0, 0, size // 2, size], fill=255)
            base = p.done()
            base.paste(im, (0, 0), Image.composite(im.split()[3], Image.new("L", (size, size), 0), mask))
            return base
    return p.done()


def pickup_heart(kind):
    # floor pickups are 56 px
    p = Pen(56, 56)
    heart_shape(p, 28, 29, 50, (214, 38, 48, 255) if kind.startswith("red") else (150, 190, 255, 255))
    im = p.done()
    if kind.endswith("half"):
        small = im.resize((38, 38), Image.LANCZOS)
        out = Image.new("RGBA", (56, 56), (0, 0, 0, 0))
        out.alpha_composite(small, (9, 12))
        return out
    return im


def coin(frame):
    p = Pen(44, 44)
    w = [17, 12, 5, 12][frame]
    p.ell(22, 22, w + 2, 19, fill=OUT)
    p.ell(22, 22, w, 17, fill=(236, 196, 52, 255))
    if w > 8:
        p.ell(22, 22, w - 5, 11, fill=None, outline=(190, 140, 30, 255), w=2)
        p.ell(18, 15, 2.5, 3.5, fill=(255, 250, 200, 255))
    return p.done()


def key_img():
    p = Pen(48, 56)
    p.ell(24, 16, 12, 12, fill=OUT)
    p.ell(24, 16, 9, 9, fill=(236, 200, 70, 255))
    p.ell(24, 16, 4, 4, fill=OUT)
    p.rect(21, 22, 28, 52, fill=OUT, r=1)
    p.rect(22.5, 24, 26.5, 50, fill=(236, 200, 70, 255))
    for y in (38, 46):
        p.rect(26, y - 1, 36, y + 5, fill=OUT)
        p.rect(26, y, 34, y + 3.5, fill=(236, 200, 70, 255))
    return p.done()


def bomb_pickup():
    p = Pen(48, 52)
    p.blob(24, 31, 14, 13, (60, 60, 76, 255))
    p.ell(19, 25, 4, 3, fill=(140, 140, 160, 255))
    p.rect(20, 11, 28, 17, fill=(96, 84, 80, 255), outline=OUT, w=1.2, r=2)
    p.line([(24, 11), (30, 5), (33, 6)], (210, 190, 150, 255), 2)
    p.ell(34, 5, 2.8, 2.8, fill=(255, 220, 90, 255))
    return p.done()


def stat_icon(kind):
    p = Pen(44, 44)
    if kind == "coin":
        return coin(0)
    if kind == "bomb":
        return bomb_pickup().resize((44, 48))
    if kind == "key":
        return key_img().resize((36, 42))
    return p.done()


ITEM_COLORS = {}


def item_icon(name):
    # 56 px icons, one distinctive glyph each
    p = Pen(56, 56)
    if name == "sad_onion":
        p.blob(28, 32, 17, 15, (236, 226, 196, 255))
        p.poly([(22, 20), (28, 6), (34, 20)], fill=(120, 170, 70, 255), outline=OUT, w=1.5)
        p.ell(22, 34, 3, 4, fill=OUT)
        p.ell(34, 34, 3, 4, fill=OUT)
        p.line([(22, 40), (22, 46)], TEARC, 3)
        p.line([(34, 40), (34, 48)], TEARC, 3)
    elif name == "inner_eye":
        p.blob(28, 28, 22, 14, WHITE)
        p.ell(28, 28, 10, 10, fill=(60, 120, 200, 255), outline=OUT, w=1.5)
        p.ell(28, 28, 5, 5, fill=OUT)
        p.ell(25, 25, 2, 2, fill=WHITE)
        for dx in (-14, 0, 14):
            p.line([(28 + dx, 12), (28 + dx * 1.3, 4)], OUT, 2)
    elif name == "brimstone":
        p.blob(28, 30, 18, 20, (196, 40, 40, 255))
        p.poly([(28, 6), (12, 30), (44, 30)], fill=(120, 16, 24, 255), outline=OUT, w=1.5)
        p.ell(21, 33, 4, 5, fill=(255, 220, 60, 255))
        p.ell(35, 33, 4, 5, fill=(255, 220, 60, 255))
        p.rect(20, 44, 36, 48, fill=OUT)
    elif name == "cricket_head":
        p.blob(28, 30, 18, 17, (150, 120, 70, 255))
        for dx in (-1, 1):
            p.poly([(28 + dx * 8, 16), (28 + dx * 22, 4), (28 + dx * 14, 22)], fill=(110, 84, 50, 255), outline=OUT, w=1.5)
        p.ell(21, 29, 3.5, 4, fill=(240, 230, 120, 255))
        p.ell(35, 29, 3.5, 4, fill=(240, 230, 120, 255))
        p.line([(21, 40), (35, 40)], OUT, 2)
    elif name == "spoon_bender":
        p.line([(28, 52), (28, 28)], (190, 190, 200, 255), 4)
        p.arc(28, 16, 14, 12, 0, 360, (200, 200, 214, 255), 4)
        p.line([(18, 12), (12, 6)], (190, 120, 240, 255), 2)
        p.line([(38, 12), (44, 6)], (190, 120, 240, 255), 2)
    elif name == "pentagram":
        p.ell(28, 28, 22, 22, fill=(60, 16, 24, 255), outline=OUT, w=1.5)
        pts = [(28 + 17 * math.sin(i * 4 * math.pi / 5), 29 - 17 * math.cos(i * 4 * math.pi / 5)) for i in range(5)]
        p.line(pts + [pts[0]], (240, 70, 60, 255), 2.6)
    elif name == "number_one":
        p.blob(28, 28, 20, 20, (250, 224, 80, 255))
        p.line([(22, 20), (30, 14), (30, 42)], OUT, 4)
        p.line([(22, 42), (38, 42)], OUT, 4)
    elif name == "magic_mushroom":
        p.ell(28, 22, 21, 15, fill=OUT)
        p.ell(28, 22, 19, 13, fill=(214, 40, 50, 255))
        for dx, dy, r in ((-9, 18, 4), (4, 14, 5), (12, 22, 3.5)):
            p.ell(28 + dx, dy, r, r, fill=WHITE)
        p.rect(21, 30, 35, 50, fill=OUT, r=4)
        p.rect(23, 30, 33, 48, fill=(240, 226, 196, 255), r=3)
    elif name == "ouija_board":
        p.rect(6, 12, 50, 46, fill=(150, 104, 60, 255), outline=OUT, w=2, r=3)
        p.arc(28, 30, 14, 9, 180, 360, (240, 220, 170, 255), 2.5)
        p.ell(28, 34, 4, 4, fill=(240, 220, 170, 255))
    elif name == "roid_rage":
        p.blob(28, 32, 18, 14, (210, 60, 60, 255))
        p.rect(10, 22, 46, 34, fill=(250, 230, 220, 255), outline=OUT, w=1.5, r=6)
        p.poly([(30, 8), (22, 22), (28, 22), (24, 32), (36, 18), (30, 18)], fill=(255, 220, 60, 255), outline=OUT, w=1)
    elif name == "lunch":
        p.rect(8, 22, 48, 48, fill=(210, 160, 90, 255), outline=OUT, w=2, r=4)
        p.rect(18, 12, 38, 24, fill=None, outline=OUT, w=2.4, r=4)
        p.rect(12, 32, 44, 38, fill=(232, 90, 90, 255))
    elif name == "the_halo":
        p.ell(28, 26, 22, 9, fill=None, outline=OUT, w=7)
        p.ell(28, 26, 22, 9, fill=None, outline=(255, 230, 110, 255), w=4)
    return p.done()


ITEMS = ["sad_onion", "inner_eye", "brimstone", "cricket_head", "spoon_bender", "pentagram", "number_one",
         "magic_mushroom", "ouija_board", "roid_rage", "lunch", "the_halo"]


def pedestal():
    p = Pen(84, 52)
    p.ell(42, 44, 38, 8, fill=(0, 0, 0, 90))
    p.rect(8, 22, 76, 46, fill=OUT, r=6)
    p.rect(10, 24, 74, 44, fill=(150, 144, 156, 255), r=5)
    p.rect(10, 24, 74, 31, fill=(190, 184, 196, 255), r=4)
    p.rect(2, 12, 82, 26, fill=OUT, r=6)
    p.rect(4, 14, 80, 24, fill=(176, 170, 184, 255), r=5)
    return p.done()


def trapdoor(frame):
    p = Pen(104, 104)
    p.rect(6, 6, 98, 98, fill=OUT, r=10)
    p.rect(10, 10, 94, 94, fill=(60, 40, 30, 255) if frame == 0 else (74, 50, 36, 255), r=8)
    p.rect(16, 16, 88, 88, fill=(14, 8, 10, 255), r=6)
    for i in range(3):
        y = 26 + i * 22
        p.rect(24, y, 80, y + 6, fill=(110, 76, 50, 255))
    p.rect(8, 8, 96, 96, fill=None, outline=(110, 80, 56, 255), w=2, r=8)
    return p.done()


def price_tag(n):
    # shop price: a small gold coin followed by the number, drawn with the bold build-time font
    from PIL import ImageFont
    from buildlib import BOLD
    f = ImageFont.truetype(BOLD, 30)
    im = Image.new("RGBA", (70, 36), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    txt = str(n)
    d.text((4, 2), txt, font=f, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(30, 16, 20, 255))
    x = 8 + int(d.textlength(txt, font=f))
    d.ellipse([x, 8, x + 20, 28], fill=(236, 196, 52, 255), outline=(30, 16, 20, 255), width=2)
    return im
