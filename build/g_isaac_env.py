# Build-time art, part 3: room shells (floor + walls) for four themes, doors, rocks, poop, fire, pits, spikes, decals.
import math, random
from PIL import Image, ImageDraw, ImageFilter
from g_isaac_art import *

CELL = 100
WALL = 80
SHELL_W = 13 * CELL + 2 * WALL
SHELL_H = 7 * CELL + 2 * WALL

THEMES = [
    dict(name="basement", floor=(176, 150, 118), floor2=(164, 138, 108), stain=(120, 84, 62), wall=(98, 66, 50),
         wall_hi=(150, 108, 80), rock=(138, 124, 112), pit=(24, 14, 14)),
    dict(name="caves", floor=(150, 136, 126), floor2=(138, 124, 116), stain=(96, 82, 80), wall=(82, 72, 78),
         wall_hi=(130, 118, 124), rock=(120, 112, 124), pit=(14, 12, 20)),
    dict(name="depths", floor=(132, 102, 98), floor2=(120, 92, 90), stain=(84, 48, 52), wall=(70, 42, 52),
         wall_hi=(120, 76, 88), rock=(110, 92, 104), pit=(20, 8, 12)),
    dict(name="womb", floor=(206, 120, 122), floor2=(194, 108, 112), stain=(140, 52, 66), wall=(140, 50, 70),
         wall_hi=(206, 100, 120), rock=(160, 110, 130), pit=(46, 8, 24)),
]


def noise_layer(w, h, rnd, base, amp, count, size):
    # Many soft speckles, lighter or darker than the base, give a hand-painted floor look without per-pixel work.
    im = Image.new("RGBA", (w, h), base + (255,))
    d = ImageDraw.Draw(im)
    for _ in range(count):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r = rnd.randrange(2, size)
        k = 1 + rnd.uniform(-amp, amp)
        d.ellipse([x - r, y - r * 0.7, x + r, y + r * 0.7], fill=tuple(max(0, min(255, int(v * k))) for v in base) + (255,))
    return im


def shell(th, variant):
    rnd = random.Random(variant * 977 + len(th["name"]) * 13)
    w, h = SHELL_W, SHELL_H
    im = Image.new("RGBA", (w, h), th["wall"] + (255,))
    # wall texture: stone blocks
    d = ImageDraw.Draw(im)
    for y in range(0, h, 40):
        off = (y // 40 % 2) * 30
        for x in range(-off, w, 60):
            k = 1 + rnd.uniform(-0.1, 0.1)
            c = tuple(max(0, min(255, int(v * k))) for v in th["wall"])
            d.rectangle([x + 2, y + 2, x + 57, y + 37], fill=c)
            d.line([(x + 2, y + 2), (x + 57, y + 2)], fill=tuple(min(255, int(v * 1.18)) for v in c), width=2)
    # floor
    fl = noise_layer(13 * CELL, 7 * CELL, rnd, th["floor"], 0.07, 2600, 14)
    fd = ImageDraw.Draw(fl)
    for cx in range(13):
        for cy in range(7):
            if (cx + cy) % 2:
                fd.rectangle([cx * CELL, cy * CELL, cx * CELL + CELL - 1, cy * CELL + CELL - 1],
                             fill=th["floor2"] + (255,))
    fl2 = noise_layer(13 * CELL, 7 * CELL, rnd, th["floor"], 0.05, 1800, 10)
    mask = Image.new("L", fl.size, 0)
    ImageDraw.Draw(mask).rectangle([0, 0, fl.width, fl.height], fill=0)
    # keep the checker faint: blend two noise layers
    fl = Image.blend(fl, fl2, 0.5)
    fd = ImageDraw.Draw(fl)
    sc = th["stain"] + (255,)
    for _ in range(18):
        x, y = rnd.randrange(fl.width), rnd.randrange(fl.height)
        r = rnd.randrange(14, 46)
        ov = Image.new("RGBA", fl.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse([x - r, y - r * 0.7, x + r, y + r * 0.7], fill=sc[:3] + (46,))
        fl = Image.alpha_composite(fl, ov)
    fd = ImageDraw.Draw(fl)
    for _ in range(26):
        x, y = rnd.randrange(30, fl.width - 30), rnd.randrange(30, fl.height - 30)
        pts = [(x, y)]
        for _ in range(4):
            x += rnd.randrange(-18, 19)
            y += rnd.randrange(-14, 15)
            pts.append((x, y))
        fd.line(pts, fill=tuple(int(v * 0.72) for v in th["floor"]) + (255,), width=2)
    # inner shadow under the walls
    sh = Image.new("RGBA", fl.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    for i in range(34):
        a = int(110 * (1 - i / 34) ** 2)
        sd.rectangle([i, i, fl.width - 1 - i, fl.height - 1 - i], outline=(20, 8, 8, a))
    fl = Image.alpha_composite(fl, sh)
    im.paste(fl, (WALL, WALL))
    # wall lip: light edge on the top/left, dark on bottom/right gives the room depth
    d = ImageDraw.Draw(im)
    hi = th["wall_hi"] + (255,)
    lo = shade(th["wall"], 0.5)
    d.rectangle([WALL - 14, WALL - 14, w - WALL + 13, h - WALL + 13], outline=lo, width=14)
    d.line([(WALL - 14, WALL - 14), (w - WALL + 13, WALL - 14)], fill=hi, width=3)
    d.line([(WALL - 14, WALL - 14), (WALL - 14, h - WALL + 13)], fill=hi, width=3)
    # outer edge
    d.rectangle([0, 0, w - 1, h - 1], outline=shade(th["wall"], 0.35), width=6)
    # blood on the walls
    for _ in range(5):
        x = rnd.randrange(120, w - 120)
        side = rnd.choice((0, 1))
        y = 14 if side == 0 else h - 60
        d.rounded_rectangle([x, y, x + 6, y + rnd.randrange(24, 44)], radius=3, fill=(120, 24, 30, 255))
    return im.convert("RGB")


def door(kind, state):
    # drawn in "up" orientation: 140 wide, 80 tall (wall thickness); the doorway faces down into the room
    p = Pen(140, 80)
    frame = {"normal": (118, 84, 62, 255), "boss": (170, 48, 52, 255), "treasure": (214, 170, 56, 255),
             "shop": (70, 150, 84, 255), "hole": (96, 84, 80, 255)}[kind]
    p.rect(0, 0, 139, 79, fill=OUT, r=10)
    p.rect(3, 3, 137, 90, fill=frame, r=10)
    p.rect(3, 3, 137, 14, fill=shade(frame, 1.25), r=6)
    if kind == "hole":
        # blown-open rubble hole
        p.rect(26, 14, 114, 90, fill=(8, 4, 6, 255), r=14)
        for x, y, r in ((22, 70, 9), (118, 66, 8), (34, 76, 7), (106, 74, 10), (16, 56, 6)):
            p.ell(x, y, r, r * 0.8, fill=(110, 100, 96, 255), outline=OUT, w=1.4)
        return p.done()
    if state == "open":
        p.rect(28, 12, 112, 90, fill=(8, 4, 6, 255), r=16)
        p.rect(34, 66, 106, 90, fill=(26, 16, 16, 255))
    else:
        p.rect(26, 12, 114, 90, fill=OUT, r=16)
        p.rect(30, 16, 110, 90, fill=shade(frame, 0.72), r=14)
        for x in (44, 70, 96):
            p.line([(x, 18), (x, 80)], shade(frame, 0.5), 2)
        for y in (30, 56):
            p.rect(30, y, 110, y + 6, fill=(90, 90, 104, 255))
        for x in range(36, 110, 14):
            p.poly([(x, 80), (x + 5, 66), (x + 10, 80)], fill=(176, 176, 190, 255), outline=OUT, w=1)
        if state == "locked":
            p.rect(58, 28, 82, 52, fill=OUT, r=4)
            p.rect(60, 30, 80, 50, fill=(236, 200, 70, 255), r=3)
            p.ell(70, 38, 3.4, 3.4, fill=OUT)
            p.rect(68.5, 38, 71.5, 46, fill=OUT)
            p.arc(70, 28, 7, 8, 180, 360, OUT, 3)
    if kind == "boss":
        p.ell(70, 9, 9, 8, fill=(240, 234, 220, 255), outline=OUT, w=1.4)
        p.ell(67, 8, 2, 2.4, fill=OUT)
        p.ell(73, 8, 2, 2.4, fill=OUT)
    if kind == "treasure":
        p.ell(70, 9, 6, 6, fill=(255, 240, 150, 255), outline=OUT, w=1.2)
    if kind == "shop":
        p.rect(62, 3, 78, 14, fill=(230, 226, 190, 255), outline=OUT, w=1, r=2)
        p.line([(70, 5), (70, 12)], OUT, 1.6)
    return p.done()


def rock(variant, th):
    rnd = random.Random(variant * 31 + len(th["name"]))
    p = Pen(100, 100)
    base = th["rock"] + (255,)
    p.ell(50, 86, 42, 9, fill=(0, 0, 0, 0))
    pts = []
    n = 11
    for i in range(n):
        a = i / n * 2 * math.pi
        r = 41 + rnd.uniform(-6, 5)
        pts.append((50 + math.cos(a) * r, 52 + math.sin(a) * r * 0.86))
    p.poly(pts, fill=base, outline=OUT, w=3.4)
    inner = [(50 + (x - 50) * 0.8 - 3, 52 + (y - 52) * 0.8 - 5) for x, y in pts]
    p.poly(inner, fill=shade(base, 1.18))
    low = [(50 + (x - 50) * 0.9, 56 + (y - 52) * 0.5) for x, y in pts]
    p.poly(pts[2:7] + [(50, 80)], fill=shade(base, 0.82))
    p.poly(inner, fill=shade(base, 1.14))
    for _ in range(3):
        x, y = rnd.uniform(30, 70), rnd.uniform(28, 62)
        p.line([(x, y), (x + rnd.uniform(-9, 9), y + rnd.uniform(5, 13)), (x + rnd.uniform(-12, 12), y + rnd.uniform(14, 22))],
               shade(base, 0.55), 2)
    p.ell(36, 32, 8, 5, fill=shade(base, 1.4))
    return p.done()


def rubble(th):
    p = Pen(100, 100)
    rnd = random.Random(5)
    base = th["rock"] + (255,)
    for _ in range(7):
        x, y, r = rnd.uniform(24, 76), rnd.uniform(50, 80), rnd.uniform(5, 11)
        p.ell(x, y, r + 1.4, r * 0.7 + 1.4, fill=OUT)
        p.ell(x, y, r, r * 0.7, fill=shade(base, rnd.uniform(0.8, 1.15)))
    return p.done()


def poop(stage):
    p = Pen(100, 100)
    brown = (130, 84, 52, 255)
    p.ell(50, 84, 38, 8, fill=(0, 0, 0, 0))
    tiers = [(50, 72, 36, 17), (50, 52, 27, 15), (50, 34, 17, 12)][:3 - stage]
    for i, (cx, cy, rx, ry) in enumerate(tiers):
        p.blob(cx, cy, rx, ry, shade(brown, 1.0 - i * 0.04), ow=2.6)
        p.arc(cx, cy, rx - 6, ry - 4, 200, 330, shade(brown, 1.35), 3)
    cx, cy, rx, ry = tiers[-1]
    p.poly([(cx - rx * 0.4, cy - ry * 0.4), (cx, cy - ry - 11), (cx + rx * 0.4, cy - ry * 0.4)], fill=shade(brown, 0.95),
           outline=OUT, w=2.2)
    p.ell(cx - rx * 0.35, cy - ry * 0.2, 3.6, 2.2, fill=(220, 180, 130, 255))
    return p.done()


def fire(frame, size):
    p = Pen(100, 110)
    p.ell(50, 96, 40, 9, fill=(0, 0, 0, 0))
    # stone ring and logs
    p.blob(50, 86, 34, 12, (110, 104, 114, 255), ow=2.6)
    p.line([(28, 84), (72, 80)], (96, 60, 40, 255), 7)
    p.line([(28, 80), (72, 86)], (116, 76, 50, 255), 7)
    k = (0.55, 0.8, 1.0)[size]
    wob = [0, 4, -3, 2][frame]
    for col, f, dx in (((226, 60, 30, 255), 1.0, 0), ((255, 150, 40, 255), 0.72, wob * 0.3), ((255, 236, 130, 255), 0.42, -wob * 0.2)):
        h = 70 * k * f
        wd = 26 * k * f
        pts = [(50 - wd, 80), (50 - wd * 0.9, 80 - h * 0.35), (50 - wd * 0.3 + dx, 80 - h * 0.7),
               (50 + wob * 0.9 + dx, 80 - h), (50 + wd * 0.3 + dx, 80 - h * 0.65), (50 + wd * 0.95, 80 - h * 0.3), (50 + wd, 80)]
        p.poly(pts, fill=col, outline=OUT if f == 1.0 else None, w=2)
        p.ell(50, 80, wd, 8 * k, fill=col)
    return p.done()


def pit(mask, th):
    # mask bits: 1 = pit to the north, 2 = east, 4 = south, 8 = west. A rim is drawn only on open sides.
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pc = th["pit"] + (255,)
    d.rectangle([0, 0, 99, 99], fill=pc)
    rim = shade(th["floor"], 0.55)
    lip = shade(th["floor"], 0.8)
    t = 9
    if not mask & 1:
        d.rectangle([0, 0, 99, t], fill=rim)
        d.rectangle([0, 0, 99, 3], fill=lip)
    if not mask & 2:
        d.rectangle([99 - t, 0, 99, 99], fill=rim)
    if not mask & 4:
        d.rectangle([0, 99 - t, 99, 99], fill=shade(th["floor"], 0.95))
    if not mask & 8:
        d.rectangle([0, 0, t, 99], fill=rim)
    inner = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(inner).rectangle([t + 2, t + 2, 99 - t - 2, 99 - t - 2], fill=(0, 0, 0, 70))
    im = Image.alpha_composite(im, inner)
    return im


def spikes():
    p = Pen(100, 100)
    p.rect(6, 6, 94, 94, fill=OUT, r=6)
    p.rect(9, 9, 91, 91, fill=(120, 116, 126, 255), r=5)
    for gx in range(3):
        for gy in range(3):
            x, y = 24 + gx * 26, 28 + gy * 26
            p.poly([(x - 8, y + 10), (x, y - 12), (x + 8, y + 10)], fill=(210, 212, 222, 255), outline=OUT, w=1.8)
            p.poly([(x - 1, y - 10), (x, y - 12), (x + 8, y + 10), (x + 3, y + 10)], fill=(150, 152, 166, 255))
    return p.done()


def decal(kind, variant):
    rnd = random.Random(kind * 100 + variant)
    p = Pen(160, 110)
    if kind == 0:
        col = (150, 52, 56, 255)
        p.ell(80, 55, rnd.uniform(26, 44), rnd.uniform(18, 30), fill=col)
        for _ in range(10):
            a = rnd.uniform(0, 6.28)
            d = rnd.uniform(34, 62)
            r = rnd.uniform(3, 9)
            p.ell(80 + math.cos(a) * d, 55 + math.sin(a) * d * 0.6, r, r * 0.8, fill=col)
        p.ell(70, 48, 8, 5, fill=(176, 72, 74, 255))
    elif kind == 1:
        # bones
        col = (226, 218, 200, 255)
        p.line([(40, 70), (110, 44)], OUT, 8)
        p.line([(40, 70), (110, 44)], col, 5)
        for (x, y) in ((38, 66), (42, 76), (108, 40), (114, 48)):
            p.ell(x, y, 6, 6, fill=col, outline=OUT, w=1.2)
        if variant:
            p.ell(100, 76, 17, 14, fill=col, outline=OUT, w=1.6)
            p.ell(94, 74, 4, 5, fill=OUT)
            p.ell(107, 74, 4, 5, fill=OUT)
    else:
        col = (96, 70, 56, 255)
        for _ in range(8):
            p.ell(rnd.uniform(40, 120), rnd.uniform(30, 80), rnd.uniform(5, 12), rnd.uniform(3, 8), fill=col)
    return p.done()
