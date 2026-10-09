# Build-time art, part 2: terrain tiles, liquids, objects, effects and text glyphs.
import math, random
from PIL import Image, ImageDraw, ImageFont
from buildlib import BOLD
from g_redball_art import *

T = 60
WORLDS = ("grass", "factory", "lava", "ice")


def noise_dots(d, rnd, n, box, cols, rmax=3):
    x0, y0, x1, y1 = box
    for _ in range(n):
        x, y = rnd.randint(x0, x1), rnd.randint(y0, y1)
        r = rnd.randint(1, rmax)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice(cols))


def tile_img(world, mask, var):
    rnd = random.Random(hash((world, mask, var)) & 0xFFFF)
    im = Image.new("RGB", (T, T))
    d = ImageDraw.Draw(im)
    U, D, L, R = mask & 1, mask & 2, mask & 4, mask & 8
    if world == "grass":
        base, dark, light, edge = (128, 88, 54), (102, 68, 42), (156, 112, 70), (62, 38, 26)
        d.rectangle([0, 0, T, T], fill=base)
        noise_dots(d, rnd, 14, (2, 8, 57, 57), [dark, dark, light], 4)
        for _ in range(3):
            x, y = rnd.randint(8, 50), rnd.randint(20, 50)
            d.ellipse([x, y, x + 8, y + 5], fill=(170, 165, 150), outline=(110, 104, 94))
        if U:
            d.rectangle([0, 0, T, 17], fill=(88, 192, 62))
            d.rectangle([0, 3, T, 8], fill=(132, 224, 84))
            for x in range(0, T):
                yy = 15 + int(3 * math.sin(x / 60 * 2 * math.pi * 3))
                d.line([x, 12, x, yy], fill=(88, 192, 62))
                d.line([x, yy + 1, x, yy + 3], fill=(60, 140, 44))
            d.rectangle([0, 0, T, 2], fill=(30, 100, 40))
        if D:
            d.rectangle([0, T - 4, T, T], fill=edge)
        if L:
            d.rectangle([0, 0, 2, T], fill=edge if not U else (30, 100, 40))
            d.rectangle([0, 17 if U else 0, 2, T], fill=edge)
        if R:
            d.rectangle([T - 3, 0, T, T], fill=edge)
            if U:
                d.rectangle([T - 3, 0, T, 17], fill=(30, 100, 40))
    elif world == "factory":
        base, dark, light, edge = (78, 88, 104), (56, 64, 78), (122, 134, 152), (20, 24, 34)
        d.rectangle([0, 0, T, T], fill=base)
        d.rectangle([4, 4, T - 5, T - 5], outline=dark, width=2)
        d.rectangle([6, 6, T - 7, 20], fill=shade(base, 1.1))
        for (bx, by) in ((9, 9), (T - 10, 9), (9, T - 10), (T - 10, T - 10)):
            d.ellipse([bx - 3, by - 3, bx + 3, by + 3], fill=light, outline=edge)
        if var == 1:
            for k in range(6):
                d.line([14, 22 + k * 5, T - 14, 22 + k * 5], fill=dark, width=2)
        if var == 2:
            d.line([T // 2, 6, T // 2, T - 6], fill=dark, width=3)
            d.line([6, T // 2, T - 6, T // 2], fill=dark, width=3)
        if U:
            d.rectangle([0, 0, T, 14], fill=(138, 150, 168))
            d.rectangle([0, 0, T, 3], fill=(200, 210, 224))
            for x in range(-20, T, 20):
                d.polygon([(x, 14), (x + 10, 14), (x + 20, 8), (x + 10, 8)], fill=(238, 190, 40))
            d.rectangle([0, 14, T, 16], fill=edge)
        if D:
            d.rectangle([0, T - 4, T, T], fill=edge)
        if L:
            d.rectangle([0, 0, 2, T], fill=edge)
        if R:
            d.rectangle([T - 3, 0, T, T], fill=edge)
    elif world == "lava":
        base, dark, light, edge = (70, 48, 56), (52, 34, 42), (104, 74, 80), (22, 10, 14)
        d.rectangle([0, 0, T, T], fill=base)
        noise_dots(d, rnd, 16, (2, 2, 57, 57), [dark, dark, light], 5)
        if var:
            pts = [(rnd.randint(4, 20), 4), (rnd.randint(22, 38), rnd.randint(20, 30)), (rnd.randint(10, 30), rnd.randint(36, 44)), (rnd.randint(30, 50), 56)]
            d.line(pts, fill=(255, 126, 30), width=3)
            d.line(pts, fill=(255, 210, 90), width=1)
        if U:
            d.rectangle([0, 0, T, 13], fill=(112, 80, 84))
            d.rectangle([0, 0, T, 3], fill=(150, 112, 110))
            for _ in range(4):
                x = rnd.randint(4, 54)
                d.ellipse([x, 5, x + 3, 8], fill=(255, 150, 40))
        if D:
            d.rectangle([0, T - 4, T, T], fill=edge)
        if L:
            d.rectangle([0, 0, 2, T], fill=edge)
        if R:
            d.rectangle([T - 3, 0, T, T], fill=edge)
    else:
        base, dark, light, edge = (150, 212, 244), (112, 178, 228), (214, 242, 255), (44, 100, 160)
        d.rectangle([0, 0, T, T], fill=base)
        for _ in range(5):
            x = rnd.randint(-10, 50)
            d.polygon([(x, T), (x + 14, T), (x + 44, 0), (x + 30, 0)], fill=rnd.choice([dark, light]))
        d.rectangle([0, 0, T, T], outline=None)
        if U:
            d.rectangle([0, 0, T, 12], fill=(226, 248, 255))
            d.rectangle([0, 0, T, 3], fill=(255, 255, 255))
            d.line([10, 7, 30, 7], fill=(190, 230, 250), width=2)
        if D:
            d.rectangle([0, T - 4, T, T], fill=edge)
        if L:
            d.rectangle([0, 0, 2, T], fill=edge)
        if R:
            d.rectangle([T - 3, 0, T, T], fill=edge)
        # ice that is part of a lump of rock in the lava world is darker so slippery tiles are recognisable
    return im


def build_tiles():
    out = {}
    for w in WORLDS:
        out[w] = {}
        for m in range(16):
            for v in range(3):
                out[w]["%d_%d" % (m, v)] = rows_of(tile_img(w, m, v))
    return out


LIQ = {"water": ((40, 130, 230), (24, 90, 190), (170, 225, 255)),
       "sludge": ((110, 190, 40), (70, 140, 30), (210, 245, 120)),
       "lava": ((255, 120, 30), (210, 60, 20), (255, 230, 120))}


def liquid_tile(kind, top, frame):
    c, dk, hi = LIQ[kind]
    im = Image.new("RGB", (T, T), c)
    d = ImageDraw.Draw(im)
    ph = frame / 4 * 2 * math.pi
    for y in range(T):
        k = y / T
        d.line([0, y, T, y], fill=mix(c, dk, k * 0.8))
    for i in range(3):
        yy = 14 + i * 16
        pts = [(x, yy + 3 * math.sin(x / 60 * 2 * math.pi * 2 + ph + i)) for x in range(0, T + 1, 3)]
        d.line(pts, fill=mix(c, hi, 0.45), width=2)
    if kind == "lava":
        rnd = random.Random(frame)
        for _ in range(3):
            x, y = rnd.randint(4, 54), rnd.randint(8, 50)
            d.ellipse([x, y, x + 6, y + 6], fill=(255, 220, 90))
    if top:
        d.rectangle([0, 0, T, 9], fill=mix(c, hi, 0.6))
        for x in range(0, T, 12):
            xx = (x + frame * 3) % T
            d.rectangle([xx, 0, xx + 6, 3], fill=(255, 255, 255) if kind != "lava" else (255, 250, 200))
        d.line([0, 9, T, 9], fill=mix(c, dk, .5), width=2)
    return im


def conv_tile(frame, direction):
    im = Image.new("RGB", (T, T), (60, 66, 80))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, T, 20], fill=(34, 38, 48))
    off = (frame * 15 * direction) % 30
    for x in range(-30, T + 30, 30):
        xx = x + off
        d.polygon([(xx, 3), (xx + 14, 10), (xx, 17), (xx + 6, 17), (xx + 20, 10), (xx + 6, 3)], fill=(238, 190, 40))
    d.rectangle([0, 0, T, 2], fill=(150, 160, 180))
    d.rectangle([0, 20, T, 23], fill=(20, 24, 34))
    d.rectangle([4, 26, T - 5, T - 5], outline=(40, 46, 58), width=2, fill=(78, 88, 104))
    for cx in (14, 46):
        d.ellipse([cx - 6, 36, cx + 6, 48], fill=(150, 160, 180), outline=(20, 24, 34))
    return im


def build_liquids():
    out = {}
    for k in LIQ:
        out[k] = {"top": [rows_of(liquid_tile(k, 1, f)) for f in range(4)], "deep": [rows_of(liquid_tile(k, 0, f)) for f in range(4)]}
    out["convR"] = [rows_of(conv_tile(f, 1)) for f in range(4)]
    out["convL"] = [rows_of(conv_tile(f, -1)) for f in range(4)]
    return out


# ---------------------------------------------------------------------------------------------- objects
def star_img(widthk, size=46):
    im, d = canvas(size, size)
    c = size * SS / 2
    pts = []
    for i in range(10):
        r = (size / 2 - 3) * SS * (1 if i % 2 == 0 else 0.46)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((c + math.cos(a) * r * widthk, c + math.sin(a) * r))
    d.polygon(pts, fill=(255, 208, 40), outline=OUT, width=3 * SS)
    ip = [(c + (px - c) * 0.55, c + (py - c) * 0.55) for px, py in pts]
    d.polygon(ip, fill=(255, 240, 130))
    d.ellipse([c - 5 * SS * widthk, c - 12 * SS, c + 2 * SS * widthk, c - 5 * SS], fill=(255, 255, 255))
    return fin(im, size, size)


def flag_img(kind, frame):
    im, d = canvas(56, 104)
    s = SS
    d.rectangle(P((10, 8), (16, 104)), fill=(210, 210, 220), outline=OUT, width=2)
    d.ellipse(P((6, 2), (20, 14)), fill=(250, 220, 80), outline=OUT, width=2)
    col = (150, 150, 160) if kind == "off" else (60, 200, 80)
    wob = [0, 3, 0, -3][frame]
    pts = [(16, 14), (50, 20 + wob), (40, 30 + wob / 2), (50, 40 - wob), (16, 44)]
    d.polygon(P(*pts), fill=col, outline=OUT)
    if kind == "on":
        d.polygon(P((26, 24), (30, 30), (38, 30), (32, 34), (34, 40), (26, 36)), fill=(255, 255, 255))
    return fin(im, 56, 104)


def portal_img(frame):
    w, h = 110, 150
    im, d = canvas(w, h)
    s = SS
    for i in range(6):
        k = i / 5
        col = mix((120, 70, 230), (20, 10, 90), k)
        d.ellipse(P((6 + i * 7, 6 + i * 9), (w - 6 - i * 7, h - 6 - i * 9)), fill=col, outline=OUT if i == 0 else None, width=3)
    a0 = frame * 30
    for j in range(3):
        d.arc(P((22, 30), (w - 22, h - 30)), a0 + j * 120, a0 + j * 120 + 80, fill=(240, 220, 255), width=4 * s)
        d.arc(P((34, 48), (w - 34, h - 48)), -a0 + j * 120, -a0 + j * 120 + 70, fill=(190, 160, 255), width=3 * s)
    d.ellipse(P((w / 2 - 6, h / 2 - 6), (w / 2 + 6, h / 2 + 6)), fill=(255, 255, 255))
    d.arc(P((2, 2), (w - 2, h - 2)), 0, 360, fill=(255, 230, 120), width=3 * s)
    return fin(im, w, h)


def spikes_img(direction):
    im, d = canvas(60, 40)
    s = SS
    d.rectangle(P((0, 30), (60, 40)), fill=(90, 94, 110), outline=OUT, width=2)
    for i in range(3):
        x = i * 20
        d.polygon(P((x + 1, 32), (x + 10, 2), (x + 19, 32)), fill=(206, 214, 228), outline=OUT)
        d.polygon(P((x + 10, 2), (x + 19, 32), (x + 13, 32)), fill=(140, 150, 170))
    im = fin(im, 60, 40)
    if direction == "down":
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
    return im


def saw_img(frame, size=76):
    im, d = canvas(size, size)
    s = SS
    c = size / 2
    teeth = 12
    pts = []
    for i in range(teeth * 2):
        a = (i / (teeth * 2)) * 2 * math.pi + frame * (2 * math.pi / teeth / 6)
        r = c - 1 if i % 2 == 0 else c - 9
        pts.append(((c + math.cos(a) * r) * s, (c + math.sin(a) * r) * s))
    d.polygon(pts, fill=(196, 204, 216), outline=OUT, width=3 * s)
    d.ellipse(P((c - 20, c - 20), (c + 20, c + 20)), fill=(150, 160, 178), outline=OUT, width=2 * s)
    for k in range(3):
        a = k * 2.094 + frame * 0.2
        d.pieslice(P((c - 18, c - 18), (c + 18, c + 18)), math.degrees(a), math.degrees(a) + 40, fill=(120, 128, 148))
    d.ellipse(P((c - 7, c - 7), (c + 7, c + 7)), fill=(60, 66, 80), outline=OUT, width=2 * s)
    d.ellipse(P((c - 3, c - 3), (c + 3, c + 3)), fill=(220, 224, 236))
    return fin(im, size, size)


def crusher_img():
    im, d = canvas(120, 66)
    s = SS
    d.rounded_rectangle(P((2, 2), (118, 52)), 6 * s, fill=(96, 104, 120), outline=OUT, width=3 * s)
    d.rectangle(P((6, 6), (114, 16)), fill=(140, 150, 168))
    for x in range(-20, 120, 24):
        d.polygon(P((x, 52), (x + 12, 52), (x + 24, 40), (x + 12, 40)), fill=(238, 190, 40))
    for i in range(6):
        x = 12 + i * 19
        d.polygon(P((x, 52), (x + 8, 64), (x + 16, 52)), fill=(206, 214, 228), outline=OUT)
    for bx in (12, 108):
        d.ellipse(P((bx - 4, 12), (bx + 4, 20)), fill=(60, 66, 80), outline=OUT)
    return fin(im, 120, 66)


def shaft_img():
    im, d = canvas(36, 60)
    d.rectangle(P((4, 0), (32, 60)), fill=(120, 128, 146), outline=OUT, width=2 * SS)
    d.rectangle(P((9, 0), (15, 60)), fill=(176, 186, 204))
    for y in (10, 40):
        d.rectangle(P((2, y), (34, y + 6)), fill=(70, 76, 92), outline=OUT, width=SS)
    return fin(im, 36, 60)


def cannon_img(dirn, flash):
    im, d = canvas(64, 60)
    s = SS
    kick = 5 if flash else 0
    d.rounded_rectangle(P((14, 12), (60 - kick, 46)), 8 * s, fill=(70, 78, 96), outline=OUT, width=3 * s)
    d.rectangle(P((14, 16), (56 - kick, 24)), fill=(110, 120, 140))
    d.rectangle(P((44 - kick, 8), (62 - kick, 50)), fill=(54, 60, 76), outline=OUT, width=3 * s)
    d.ellipse(P((2, 34), (34, 62)), fill=(60, 50, 44), outline=OUT, width=3 * s)
    d.ellipse(P((10, 42), (26, 56)), fill=(150, 130, 110))
    if flash:
        d.polygon(P((62, 29), (64, 14), (58, 24), (56, 10)), fill=(255, 220, 80))
    im = fin(im, 64, 60)
    return im.transpose(Image.FLIP_LEFT_RIGHT) if dirn == "L" else im


def ball_shot(size=28):
    im, d = canvas(size, size)
    c = size * SS / 2
    d.ellipse([2 * SS, 2 * SS, (size - 2) * SS, (size - 2) * SS], fill=(36, 36, 44), outline=OUT, width=2 * SS)
    d.ellipse([c - 9 * SS, c - 10 * SS, c - 2 * SS, c - 3 * SS], fill=(120, 124, 140))
    return fin(im, size, size)


def laser_emit(dirn):
    im, d = canvas(60, 60)
    s = SS
    d.rounded_rectangle(P((4, 6), (40, 54)), 6 * s, fill=(72, 80, 98), outline=OUT, width=3 * s)
    d.rectangle(P((36, 18), (58, 42)), fill=(50, 56, 70), outline=OUT, width=3 * s)
    d.ellipse(P((44, 24), (56, 36)), fill=(255, 70, 60), outline=OUT, width=2 * s)
    d.rectangle(P((9, 12), (18, 48)), fill=(130, 140, 160))
    im = fin(im, 60, 60)
    return {"R": im, "L": im.transpose(Image.FLIP_LEFT_RIGHT), "D": im.rotate(-90), "U": im.rotate(90)}[dirn]


BTN = {1: (240, 70, 60), 2: (70, 140, 250), 3: (70, 210, 90), 4: (250, 210, 50)}


def button_img(gid, pressed):
    h = 8 if pressed else 16
    im, d = canvas(52, 16)
    s = SS
    d.rounded_rectangle(P((0, 0 + 16 - h), (52, 16)), 4 * s, fill=(90, 94, 110), outline=OUT, width=2 * s)
    d.rounded_rectangle(P((6, 16 - h + 1), (46, 16 - 2)), 4 * s, fill=BTN[gid], outline=OUT, width=2 * s)
    d.rectangle(P((12, 16 - h + 3), (30, 16 - h + 5)), fill=mix(BTN[gid], (255, 255, 255), .5))
    return fin(im, 52, 16)


def gate_img(gid, tiles):
    h = tiles * T
    im, d = canvas(36, h)
    s = SS
    d.rectangle(P((0, 0), (36, h)), fill=(80, 70, 84), outline=OUT, width=3 * s)
    for i in range(3):
        x = 5 + i * 11
        d.rectangle(P((x, 4), (x + 7, h - 2)), fill=(178, 184, 200), outline=OUT, width=s)
    for y in range(18, h, 40):
        d.rectangle(P((2, y), (34, y + 8)), fill=BTN[gid], outline=OUT, width=s)
    return fin(im, 36, h)


def lever_img(gid, on):
    im, d = canvas(44, 48)
    s = SS
    d.rounded_rectangle(P((4, 34), (40, 48)), 4 * s, fill=(90, 94, 110), outline=OUT, width=2 * s)
    tip = (32, 8) if on else (12, 8)
    d.line(P((22, 38), tip), fill=OUT, width=7 * s)
    d.line(P((22, 38), tip), fill=(190, 196, 210), width=4 * s)
    d.ellipse(P((tip[0] - 7, tip[1] - 7), (tip[0] + 7, tip[1] + 7)), fill=BTN[gid], outline=OUT, width=2 * s)
    return fin(im, 44, 48)


def spring_img(state):
    h = {0: 40, 1: 24, 2: 56}[state]
    im, d = canvas(52, 58)
    s = SS
    top = 58 - h
    d.rounded_rectangle(P((2, 50), (50, 58)), 3 * s, fill=(90, 94, 110), outline=OUT, width=2 * s)
    n = 4
    for i in range(n):
        y0 = top + 6 + i * (h - 16) / n
        d.line(P((8, y0 + 4), (44, y0 + (h - 16) / n - 1)), fill=OUT, width=7 * s)
        d.line(P((8, y0 + 4), (44, y0 + (h - 16) / n - 1)), fill=(230, 230, 240), width=4 * s)
    d.rounded_rectangle(P((2, top), (50, top + 8)), 4 * s, fill=(240, 70, 60), outline=OUT, width=2 * s)
    d.rectangle(P((8, top + 2), (28, top + 4)), fill=(255, 160, 150))
    return fin(im, 52, 58)


def crate_img(metal):
    im, d = canvas(56, 56)
    s = SS
    base, hi, lo = ((196, 144, 78), (226, 176, 104), (130, 90, 48)) if not metal else ((126, 136, 154), (172, 182, 200), (80, 88, 104))
    d.rectangle(P((0, 0), (56, 56)), fill=OUT)
    d.rectangle(P((3, 3), (53, 53)), fill=base)
    d.rectangle(P((3, 3), (53, 9)), fill=hi)
    d.rectangle(P((3, 47), (53, 53)), fill=lo)
    d.rectangle(P((3, 3), (9, 53)), fill=lo)
    d.rectangle(P((47, 3), (53, 53)), fill=lo)
    d.line(P((6, 6), (50, 50)), fill=lo, width=5 * s)
    d.line(P((50, 6), (6, 50)), fill=lo, width=5 * s)
    d.line(P((6, 6), (50, 50)), fill=OUT, width=s)
    for (bx, by) in ((6, 6), (50, 6), (6, 50), (50, 50)):
        d.ellipse(P((bx - 2, by - 2), (bx + 2, by + 2)), fill=hi, outline=OUT)
    return fin(im, 56, 56)


def boulder_img(frame, size=76):
    im, d = canvas(size, size)
    s = SS
    c = size / 2
    d.ellipse(P((1, 1), (size - 1, size - 1)), fill=OUT)
    d.ellipse(P((4, 4), (size - 4, size - 4)), fill=(128, 126, 134))
    a = frame * math.pi / 4
    for k in range(5):
        ang = a + k * 1.3
        rr = 18 + (k % 2) * 8
        x, y = c + math.cos(ang) * rr, c + math.sin(ang) * rr
        d.ellipse(P((x - 6, y - 5), (x + 6, y + 5)), fill=(98, 96, 106), outline=(70, 68, 78))
    d.ellipse(P((10, 8), (30, 24)), fill=(176, 174, 184))
    d.arc(P((6, 6), (size - 6, size - 6)), 20, 160, fill=(80, 78, 88), width=3 * s)
    return fin(im, size, size)


def platform_img(world, w=150, h=26):
    im, d = canvas(w, h)
    s = SS
    pal = {"grass": ((176, 128, 66), (214, 166, 96), (110, 74, 36)), "factory": ((110, 120, 140), (160, 170, 190), (66, 74, 90)),
           "lava": ((96, 70, 76), (140, 106, 108), (56, 38, 44)), "ice": ((170, 222, 248), (230, 250, 255), (96, 160, 214))}[world]
    base, hi, lo = pal
    d.rounded_rectangle(P((0, 0), (w, h)), 8 * s, fill=OUT)
    d.rounded_rectangle(P((3, 3), (w - 3, h - 3)), 6 * s, fill=base)
    d.rounded_rectangle(P((3, 3), (w - 3, 11)), 5 * s, fill=hi)
    d.rectangle(P((6, h - 8), (w - 6, h - 4)), fill=lo)
    if world in ("grass",):
        for x in range(30, w - 20, 40):
            d.line(P((x, 5), (x, h - 5)), fill=lo, width=2 * s)
    if world == "factory":
        for x in range(14, w - 10, 28):
            d.ellipse(P((x - 3, 12), (x + 3, 18)), fill=(60, 66, 80), outline=OUT)
    return fin(im, w, h)


def fallplat_img(world):
    im = platform_img(world, 120, 26)
    d = ImageDraw.Draw(im)
    d.line([30, 4, 40, 14, 34, 22], fill=OUT, width=2)
    d.line([84, 4, 76, 12, 90, 21], fill=OUT, width=2)
    return im


def seesaw_plank(angle):
    L = 300
    im = Image.new("RGBA", (L + 40, L + 40), (0, 0, 0, 0))
    plank, d = canvas(L, 22)
    d.rounded_rectangle(P((0, 0), (L, 22)), 8 * SS, fill=OUT)
    d.rounded_rectangle(P((3, 3), (L - 3, 19)), 6 * SS, fill=(188, 138, 72))
    d.rectangle(P((8, 5), (L - 8, 9)), fill=(222, 176, 104))
    for x in range(40, L - 20, 50):
        d.line(P((x, 4), (x, 18)), fill=(120, 84, 44), width=2 * SS)
    plank = fin(plank, L, 22)
    pr = plank.rotate(angle, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(pr, ((L + 40 - pr.width) // 2, (L + 40 - pr.height) // 2))
    return im.crop((0, (L + 40) // 2 - 70, L + 40, (L + 40) // 2 + 70))


def pivot_img():
    im, d = canvas(60, 50)
    d.polygon(P((30, 4), (58, 48), (2, 48)), fill=(110, 112, 128), outline=OUT, width=3 * SS)
    d.polygon(P((30, 12), (46, 44), (18, 44)), fill=(150, 154, 170))
    return fin(im, 60, 50)


def stone_img(size=100):
    im, d = canvas(size, size)
    s = SS
    pts = [(10, 40), (30, 8), (70, 6), (94, 36), (88, 80), (56, 94), (18, 84)]
    d.polygon(P(*pts), fill=(122, 116, 126), outline=OUT, width=4 * s)
    d.polygon(P((30, 8), (70, 6), (60, 34), (34, 36)), fill=(160, 154, 164))
    d.line(P((40, 40), (52, 62), (44, 84)), fill=(80, 74, 84), width=3 * s)
    d.line(P((70, 38), (64, 56)), fill=(80, 74, 84), width=3 * s)
    return fin(im, size, size)


def gear_img(frame, r, teeth, col):
    size = r * 2 + 8
    im, d = canvas(size, size)
    s = SS
    c = size / 2
    pts = []
    for i in range(teeth * 4):
        a = i / (teeth * 4) * 2 * math.pi + frame * 2 * math.pi / teeth / 8
        k = i % 4
        rr = r if k in (1, 2) else r - r * 0.16
        pts.append(((c + math.cos(a) * rr) * s, (c + math.sin(a) * rr) * s))
    d.polygon(pts, fill=col, outline=shade(col, 0.4), width=3 * s)
    d.ellipse(P((c - r * .72, c - r * .72), (c + r * .72, c + r * .72)), outline=shade(col, 0.7), width=int(r * .12 * s))
    for k in range(5):
        a = k / 5 * 2 * math.pi + frame * 2 * math.pi / teeth / 8
        d.line(P((c, c), (c + math.cos(a) * r * .7, c + math.sin(a) * r * .7)), fill=shade(col, 0.75), width=int(r * .14 * s))
    d.ellipse(P((c - r * .22, c - r * .22), (c + r * .22, c + r * .22)), fill=shade(col, 1.2), outline=shade(col, .4), width=2 * s)
    return fin(im, size, size)


# ---------------------------------------------------------------------------------------------- decor
def decor(world):
    out = []
    if world == "grass":
        im, d = canvas(36, 24)
        for x, hh in ((6, 14), (14, 22), (22, 16), (30, 10)):
            d.polygon(P((x - 4, 24), (x, 24 - hh), (x + 4, 24)), fill=(70, 170, 56), outline=(30, 100, 40))
        out.append(fin(im, 36, 24))
        im, d = canvas(30, 40)
        d.line(P((15, 40), (15, 18)), fill=(40, 130, 50), width=3 * SS)
        for k in range(5):
            a = k * 1.2566
            d.ellipse(P((15 + math.cos(a) * 7 - 5, 12 + math.sin(a) * 7 - 5), (15 + math.cos(a) * 7 + 5, 12 + math.sin(a) * 7 + 5)), fill=(255, 250, 250), outline=OUT)
        d.ellipse(P((10, 7), (20, 17)), fill=(255, 200, 40), outline=OUT)
        out.append(fin(im, 30, 40))
        im, d = canvas(64, 44)
        for (cx, cy, r) in ((20, 30, 16), (42, 28, 18), (32, 22, 15)):
            d.ellipse(P((cx - r, cy - r), (cx + r, cy + r)), fill=(60, 160, 60), outline=(30, 100, 40), width=3 * SS)
        out.append(fin(im, 64, 44))
    elif world == "factory":
        im, d = canvas(40, 80)
        d.rectangle(P((16, 20), (24, 80)), fill=(70, 76, 92), outline=OUT, width=SS)
        d.polygon(P((4, 20), (36, 20), (30, 6), (10, 6)), fill=(255, 230, 120), outline=OUT, width=2 * SS)
        out.append(fin(im, 40, 80))
        im, d = canvas(60, 60)
        d.rectangle(P((24, 0), (36, 60)), fill=(100, 108, 126), outline=OUT, width=2 * SS)
        d.ellipse(P((12, 20), (48, 50)), fill=(220, 60, 50), outline=OUT, width=3 * SS)
        d.line(P((30, 35), (42, 25)), fill=(255, 255, 255), width=3 * SS)
        out.append(fin(im, 60, 60))
        im, d = canvas(50, 30)
        d.rectangle(P((2, 2), (48, 28)), fill=(238, 190, 40), outline=OUT, width=2 * SS)
        for x in range(-10, 50, 14):
            d.polygon(P((x, 28), (x + 7, 28), (x + 17, 2), (x + 10, 2)), fill=(40, 40, 50))
        out.append(fin(im, 50, 30))
    elif world == "lava":
        im, d = canvas(40, 50)
        d.polygon(P((2, 50), (10, 12), (20, 2), (30, 14), (38, 50)), fill=(88, 62, 70), outline=OUT, width=2 * SS)
        d.line(P((20, 8), (20, 40)), fill=(255, 130, 30), width=2 * SS)
        out.append(fin(im, 40, 50))
        im, d = canvas(30, 24)
        d.ellipse(P((2, 6), (28, 28)), fill=(70, 50, 56), outline=OUT, width=2 * SS)
        d.ellipse(P((8, 10), (14, 16)), fill=(255, 150, 40))
        out.append(fin(im, 30, 24))
        im, d = canvas(44, 30)
        d.polygon(P((2, 30), (12, 6), (22, 20), (32, 2), (42, 30)), fill=(100, 76, 80), outline=OUT, width=2 * SS)
        out.append(fin(im, 44, 30))
    else:
        im, d = canvas(30, 50)
        d.polygon(P((4, 50), (10, 14), (16, 0), (22, 14), (28, 50)), fill=(190, 236, 255), outline=(50, 110, 170), width=2 * SS)
        d.line(P((16, 6), (14, 40)), fill=(255, 255, 255), width=2 * SS)
        out.append(fin(im, 30, 50))
        im, d = canvas(60, 40)
        for (cx, r) in ((20, 18), (40, 20)):
            d.ellipse(P((cx - r, 40 - r), (cx + r, 40 + r)), fill=(240, 250, 255), outline=(150, 190, 225), width=2 * SS)
        out.append(fin(im, 60, 40))
        im, d = canvas(40, 36)
        d.polygon(P((20, 2), (38, 34), (2, 34)), fill=(60, 120, 120), outline=OUT, width=2 * SS)
        d.polygon(P((20, 2), (30, 18), (10, 18)), fill=(250, 252, 255))
        out.append(fin(im, 40, 36))
    return [sprite(i) for i in out]


# ---------------------------------------------------------------------------------------------- effects
def burst_img(frame, size=150):
    im, d = canvas(size, size)
    s = SS
    c = size / 2
    k = (frame + 1) / 6
    n = 14
    pts = []
    for i in range(n * 2):
        a = i / (n * 2) * 2 * math.pi + frame * 0.12
        r = (size / 2 - 4) * k * (1 if i % 2 == 0 else 0.55)
        pts.append(((c + math.cos(a) * r) * s, (c + math.sin(a) * r) * s))
    d.polygon(pts, fill=(255, 220, 60), outline=OUT, width=3 * s)
    ip = [(c * s + (x - c * s) * 0.62, c * s + (y - c * s) * 0.62) for x, y in pts]
    d.polygon(ip, fill=(255, 140, 40))
    ip2 = [(c * s + (x - c * s) * 0.3, c * s + (y - c * s) * 0.3) for x, y in pts]
    d.polygon(ip2, fill=(255, 250, 200))
    return fin(im, size, size)


def puff_img(frame, size=60, col=(240, 240, 245)):
    im, d = canvas(size, size)
    s = SS
    k = 0.4 + frame * 0.2
    c = size / 2
    for (ox, oy, r) in ((-10, 4, 12), (10, 4, 12), (0, -6, 13), (0, 8, 10)):
        rr = r * k * size / 50
        d.ellipse([(c + ox * k - rr) * s, (c + oy * k - rr) * s, (c + ox * k + rr) * s, (c + oy * k + rr) * s], fill=col, outline=(120, 120, 130), width=2 * s)
    for (ox, oy, r) in ((-10, 4, 12), (10, 4, 12), (0, -6, 13), (0, 8, 10)):
        rr = (r * k - 1.6) * size / 50
        d.ellipse([(c + ox * k - rr) * s, (c + oy * k - rr) * s, (c + ox * k + rr) * s, (c + oy * k + rr) * s], fill=col)
    return fin(im, size, size)


def sparkle_img(frame, size=44):
    im, d = canvas(size, size)
    s = SS
    c = size / 2
    r = (size / 2 - 2) * [0.5, 0.9, 1.0, 0.6][frame]
    d.polygon([(c * s, (c - r) * s), ((c + r * .2) * s, (c - r * .2) * s), ((c + r) * s, c * s), ((c + r * .2) * s, (c + r * .2) * s), (c * s, (c + r) * s),
               ((c - r * .2) * s, (c + r * .2) * s), ((c - r) * s, c * s), ((c - r * .2) * s, (c - r * .2) * s)], fill=(255, 250, 200), outline=(255, 190, 40), width=2 * s)
    return fin(im, size, size)


def chip_img(col, size=14):
    im, d = canvas(size, size)
    d.ellipse([SS, SS, (size - 1) * SS, (size - 1) * SS], fill=col, outline=OUT, width=2 * SS)
    return fin(im, size, size)


# ---------------------------------------------------------------------------------------------- glyphs
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ :-+!x/."


def glyphs(px):
    font = ImageFont.truetype(BOLD, px * SS)
    out = {}
    for ch in CHARS:
        if ch == " ":
            out[ch] = {"w": int(px * 0.4), "h": px, "y": [], "x": [], "b": []}
            continue
        w = int(font.getlength(ch) / SS) + 8
        im = Image.new("RGBA", (w * SS, int(px * 1.5) * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((4 * SS, 2 * SS), ch, font=font, fill=(255, 255, 255), stroke_width=max(2, px // 10) * SS, stroke_fill=OUT)
        d.text((4 * SS, 2 * SS), ch, font=font, fill=(255, 255, 255))
        sm = fin(im, w, int(px * 1.5))
        sp = sprite(sm)
        sp["w"] = int(font.getlength(ch) / SS) + 2
        out[ch] = sp
    return out


def hud_icons():
    out = {}
    im = star_img(1.0, 38)
    out["hud_star"] = sprite(im)
    g = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gray = im.convert("L").point(lambda v: min(255, int(v * 0.55) + 30)).convert("RGBA")
    gray.putalpha(im.getchannel("A"))
    out["hud_star_off"] = sprite(gray)
    b = ball_body(0, 30)
    out["hud_life"] = sprite(b)
    bg = b.convert("L").point(lambda v: int(v * 0.5) + 20).convert("RGBA")
    bg.putalpha(b.getchannel("A"))
    out["hud_life_off"] = sprite(bg)
    return out


def slope_img(world, kind):
    # kind "/" rises to the right, "\" rises to the left; cap colour runs along the diagonal
    cols = {"grass": ((128, 88, 54), (88, 192, 62), (30, 100, 40)), "factory": ((78, 88, 104), (150, 160, 178), (20, 24, 34)),
            "lava": ((70, 48, 56), (112, 80, 84), (22, 10, 14)), "ice": ((150, 212, 244), (226, 248, 255), (44, 100, 160))}[world]
    body, cap, edge = cols
    im, d = canvas(T, T)
    s = SS
    A, B, C = ((0, T), (T, T), (T, 0)) if kind == "/" else ((0, 0), (0, T), (T, T))
    d.polygon(P(A, B, C), fill=edge)
    d.polygon(P(*[(x + (T / 2 - x) * 0.04, y + (T / 2 - y) * 0.04) for x, y in (A, B, C)]), fill=body)
    # cap band parallel to the hypotenuse
    k = 15
    if kind == "/":
        d.polygon(P((0, T), (T, 0), (T, k * 1.4), (k * 1.4 - 0, T)), fill=cap)
        d.line(P((0, T), (T, 0)), fill=edge, width=4 * s)
    else:
        d.polygon(P((0, 0), (T, T), (T - k * 1.4, T), (0, k * 1.4)), fill=cap)
        d.line(P((0, 0), (T, T)), fill=edge, width=4 * s)
    return fin(im, T, T)
