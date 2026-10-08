# Build-time art for the motorbike racer: background strips per stage theme, the rider's bike with lean and
# crash frames, rival bikes, traffic cars, roadside objects and the checkpoint gate. One "virtual pixel" (vpx) is
# 5x5 screen pixels, so every sprite is stored already expanded to 10 bytes per vpx as opaque spans.
import math
import random
from PIL import Image, ImageDraw, ImageFont
from buildlib import save_bundle, rgb565, BOLD

VW = 384
HZ = 100                       # horizon vrow
SKY_TOP = 20                   # first vrow below the HUD
SKY_H = HZ - SKY_TOP + 1       # rows covered by the background strips (the last one is the horizon haze row)
NEAR_H = 30                    # bottom rows of the sky that the near parallax layer may cover
P = 768                        # strip period in vpx
BUCKETS = [115, 93, 74, 59, 47, 38, 30, 24, 19, 15, 12, 10, 8, 6]   # dy values (rows below horizon) of the scale steps
SC_DIV = 6.8                   # vpx per metre = dy / SC_DIV, the same projection as the game


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


_px_cache = {}


def px10(rgb):
    v = rgb565(*rgb)
    b = _px_cache.get(v)
    if b is None:
        b = _px_cache[v] = v.to_bytes(2, "little") * 5
    return b


# ---- themes -----------------------------------------------------------------------------------------
THEMES = [
    dict(name="COAST", sky=((36, 104, 214), (110, 184, 248), (255, 226, 170)),
         ground=((236, 210, 150), (224, 196, 132)), road=((88, 90, 100), (100, 102, 112)),
         rum=((230, 40, 48), (245, 245, 245)), lane=(245, 245, 245), edge=(245, 245, 245), haze=(255, 226, 170),
         curve=1.0, traffic=0.35),
    dict(name="DESERT", sky=((30, 70, 170), (236, 150, 90), (255, 214, 140)),
         ground=((214, 148, 78), (198, 130, 62)), road=((104, 92, 90), (116, 104, 100)),
         rum=((220, 60, 30), (250, 240, 220)), lane=(250, 236, 190), edge=(250, 240, 220), haze=(255, 214, 140),
         curve=1.1, traffic=0.25),
    dict(name="SNOW", sky=((70, 120, 210), (170, 205, 242), (232, 244, 255)),
         ground=((244, 248, 255), (224, 234, 250)), road=((104, 112, 132), (116, 124, 144)),
         rum=((40, 90, 210), (250, 250, 255)), lane=(250, 250, 255), edge=(250, 250, 255), haze=(232, 244, 255),
         curve=1.2, traffic=0.2),
    dict(name="CITY NIGHT", sky=((6, 6, 36), (70, 30, 100), (220, 90, 120)),
         ground=((28, 32, 52), (22, 26, 44)), road=((54, 56, 76), (64, 66, 88)),
         rum=((250, 60, 200), (60, 220, 255)), lane=(255, 225, 110), edge=(60, 220, 255), haze=(220, 90, 120),
         curve=1.15, traffic=0.7),
]


def sky_color(th, r):
    t = r / (SKY_H - 1)
    top, mid, low = th["sky"]
    return lerp(top, mid, t / 0.65) if t < 0.65 else lerp(mid, low, (t - 0.65) / 0.35)


def wrapped(fn):
    for dx in (-P, 0, P):
        fn(dx)


def ridge(d, base, terms, color, rows=SKY_H, cap=None):
    # Heightmap silhouette; integer frequencies keep the strip seamless at the period boundary.
    for x in range(P):
        h = base + sum(a * math.sin(2 * math.pi * f * x / P + ph) for a, f, ph in terms)
        top = rows - max(1, int(h))
        d.line([(x, top), (x, rows)], fill=color)
        if cap:
            d.line([(x, top), (x, top + cap[1])], fill=cap[0])


def to_rows(im):
    raw = im.convert("RGB").tobytes()
    rows = []
    for y in range(im.height):
        line = b"".join(px10((raw[i], raw[i + 1], raw[i + 2])) for i in range(y * im.width * 3, (y + 1) * im.width * 3, 3))
        rows.append(line)
    return rows


# ---- far layer: sky gradient, sun, distant mountains / sea / skyline ------------------------------------
def make_far(th, idx, rnd):
    im = Image.new("RGB", (P, SKY_H))
    d = ImageDraw.Draw(im)
    for r in range(SKY_H):
        d.line([(0, r), (P, r)], fill=sky_color(th, r))
    low = th["sky"][2]
    if idx == 0:
        sx = rnd.randint(200, 560)
        for rad, f in ((26, 0.25), (19, 0.5), (13, 1.0)):
            col = lerp(th["sky"][1], (255, 250, 220), f)
            wrapped(lambda dx, rad=rad, col=col: d.ellipse([sx + dx - rad, 54 - rad, sx + dx + rad, 54 + rad], fill=col))
        for k in range(7):
            cx_, cy = rnd.randint(0, P), rnd.randint(8, 34)
            for j in range(4):
                ox, oy = rnd.randint(-14, 14), rnd.randint(-2, 2)
                wrapped(lambda dx, ox=ox, oy=oy, cx_=cx_, cy=cy: d.ellipse(
                    [cx_ + dx + ox - 11, cy + oy - 3, cx_ + dx + ox + 11, cy + oy + 3], fill=(250, 252, 255)))
        isl = lerp((40, 110, 150), low, 0.5)
        for ix in (90, 330, 560):
            wrapped(lambda dx, ix=ix: d.polygon([(ix + dx - 40, SKY_H - 9), (ix + dx - 14, SKY_H - 17),
                                                  (ix + dx + 6, SKY_H - 14), (ix + dx + 38, SKY_H - 9)], fill=isl))
        for r in range(SKY_H - 9, SKY_H):
            t = (r - (SKY_H - 9)) / 8
            d.line([(0, r), (P, r)], fill=lerp((120, 190, 232), (28, 110, 196), t * 0.9))
        for k in range(12):
            gy = SKY_H - 9 + k % 8
            gw = 3 + (gy - (SKY_H - 9)) * 2
            wrapped(lambda dx, gy=gy, gw=gw: d.line([(sx + dx - gw + (k * 3) % 5, gy), (sx + dx + gw - (k * 5) % 4, gy)],
                                                    fill=(255, 246, 200)))
    elif idx == 1:
        sx = rnd.randint(150, 600)
        for rad, f in ((30, 0.2), (22, 0.45), (15, 1.0)):
            col = lerp(th["sky"][1], (255, 244, 200), f)
            wrapped(lambda dx, rad=rad, col=col: d.ellipse([sx + dx - rad, 50 - rad, sx + dx + rad, 50 + rad], fill=col))
        mesa = lerp((176, 96, 60), low, 0.35)
        strata = lerp((150, 76, 48), low, 0.25)
        for mx, mw, mh in ((60, 70, 22), (260, 96, 30), (470, 60, 18), (640, 80, 26)):
            def mesa_shape(dx, mx=mx, mw=mw, mh=mh):
                d.polygon([(mx + dx - mw // 2, SKY_H), (mx + dx - mw // 2 + 8, SKY_H - mh), (mx + dx + mw // 2 - 8, SKY_H - mh),
                           (mx + dx + mw // 2, SKY_H)], fill=mesa)
                for k in range(3):
                    y = SKY_H - mh + 6 + k * 6
                    d.line([(mx + dx - mw // 2 + 6, y), (mx + dx + mw // 2 - 6, y)], fill=strata)
            wrapped(mesa_shape)
        ridge(d, 5, ((3, 3, 0.5), (2, 7, 1.0)), lerp((210, 120, 70), low, 0.3))
    elif idx == 2:
        for k in range(6):
            cx_, cy = rnd.randint(0, P), rnd.randint(10, 40)
            for j in range(4):
                ox, oy = rnd.randint(-16, 16), rnd.randint(-2, 2)
                wrapped(lambda dx, ox=ox, oy=oy, cx_=cx_, cy=cy: d.ellipse(
                    [cx_ + dx + ox - 13, cy + oy - 3, cx_ + dx + ox + 13, cy + oy + 3], fill=(246, 250, 255)))
        far = lerp((120, 160, 220), low, 0.4)
        for x0 in range(0, P, 64):
            w, h = rnd.randint(70, 110), rnd.randint(18, 38)

            def peak(dx, x0=x0, w=w, h=h):
                d.polygon([(x0 + dx, SKY_H), (x0 + dx + w // 2, SKY_H - h), (x0 + dx + w, SKY_H)], fill=far)
                d.polygon([(x0 + dx + w // 2, SKY_H - h), (x0 + dx + w // 2 - w // 6, SKY_H - h + h // 3),
                           (x0 + dx + w // 2 + w // 6, SKY_H - h + h // 3)], fill=(250, 252, 255))
            wrapped(peak)
    else:
        for _ in range(110):
            sx, sy = rnd.randint(0, P - 1), rnd.randint(0, 46)
            col = rnd.choice([(255, 255, 255), (200, 220, 255), (255, 230, 190)])
            d.point((sx, sy), fill=col)
        mx = rnd.randint(200, 560)
        wrapped(lambda dx: d.ellipse([mx + dx - 9, 18 - 9, mx + dx + 9, 18 + 9], fill=(250, 248, 224)))
        wrapped(lambda dx: d.ellipse([mx + dx - 3, 18 - 9, mx + dx + 12, 18 + 8], fill=sky_color(th, 10)))
        far = lerp((70, 40, 110), low, 0.45)
        x = 0
        while x < P:
            w, h = rnd.randint(5, 11), rnd.randint(10, 34)
            wrapped(lambda dx, x=x, w=w, h=h: d.rectangle([x + dx, SKY_H - h, x + dx + w, SKY_H], fill=far))
            x += w + rnd.randint(0, 2)
    return im


# ---- near layer: transparent silhouette that scrolls faster than the far one ---------------------------
def make_near(th, idx, rnd):
    im = Image.new("RGBA", (P, SKY_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if idx == 0:
        hill = (46, 134, 78, 255)
        ridge(d, 7, ((4, 3, 0.2), (3, 5, 1.1), (2, 11, 2.0)), hill)
        dark = (22, 86, 52, 255)
        for _ in range(16):
            x = rnd.randint(0, P)
            h = rnd.randint(9, 16)

            def palm(dx, x=x, h=h):
                d.line([(x + dx, SKY_H), (x + dx + 1, SKY_H - h)], fill=(70, 50, 30, 255), width=1)
                for ang in (-2.6, -2.0, -1.4, -0.7, -0.2):
                    ex = x + dx + 1 + int(math.cos(ang) * 6)
                    ey = SKY_H - h + int(-math.sin(ang) * 3) + 2
                    d.line([(x + dx + 1, SKY_H - h), (ex, ey)], fill=dark, width=1)
            wrapped(palm)
    elif idx == 1:
        dune = (194, 120, 64, 255)
        ridge(d, 6, ((3, 3, 0.7), (2, 8, 0.3)), dune, cap=((222, 150, 84, 255), 1))
        for _ in range(10):
            x = rnd.randint(0, P)
            h = rnd.randint(7, 15)
            if rnd.random() < 0.5:
                wrapped(lambda dx, x=x, h=h: (d.rectangle([x + dx, SKY_H - h, x + dx + 1, SKY_H], fill=(60, 110, 56, 255)),
                                              d.rectangle([x + dx - 2, SKY_H - h + 3, x + dx - 2, SKY_H - h + 6], fill=(60, 110, 56, 255)),
                                              d.rectangle([x + dx + 3, SKY_H - h + 2, x + dx + 3, SKY_H - h + 5], fill=(60, 110, 56, 255))))
            else:
                wrapped(lambda dx, x=x, h=h: d.polygon([(x + dx - h, SKY_H), (x + dx - h // 3, SKY_H - h), (x + dx + h // 2, SKY_H - h + 2),
                                                        (x + dx + h, SKY_H)], fill=(142, 78, 48, 255)))
    elif idx == 2:
        ridge(d, 5, ((3, 4, 0.9), (2, 9, 0.1)), (232, 240, 252, 255))
        x = 0
        while x < P:
            h = rnd.randint(10, 24)
            w = h // 2 + 2

            def pine(dx, x=x, h=h, w=w):
                for k in range(3):
                    top = SKY_H - h + k * (h // 3)
                    ww = w * (k + 1) // 3 + 1
                    d.polygon([(x + dx - ww, top + h // 3 + 1), (x + dx, top), (x + dx + ww, top + h // 3 + 1)], fill=(24, 84, 70, 255))
                    d.line([(x + dx - ww + 1, top + 3 + k), (x + dx, top)], fill=(250, 252, 255, 255))
            wrapped(pine)
            x += rnd.randint(4, 10)
    else:
        x = 0
        while x < P:
            w, h = rnd.randint(8, 16), rnd.randint(8, 29)
            body = rnd.choice([(18, 20, 52, 255), (26, 22, 62, 255), (14, 18, 44, 255)])

            def tower(dx, x=x, w=w, h=h, body=body):
                d.rectangle([x + dx, SKY_H - h, x + dx + w, SKY_H], fill=body)
                if h > 22:
                    d.line([(x + dx + w // 2, SKY_H - h), (x + dx + w // 2, SKY_H - h - 4)], fill=(255, 60, 60, 255))
                for wy in range(SKY_H - h + 2, SKY_H - 1, 2):
                    for wx in range(x + dx + 1, x + dx + w, 2):
                        if rnd.random() < 0.4:
                            d.point((wx, wy), fill=rnd.choice([(255, 220, 120, 255), (120, 230, 255, 255), (255, 150, 220, 255)]))
            wrapped(tower)
            x += w + rnd.randint(0, 3)
    # keep only the bottom band; also tile the first VW columns so a window never wraps
    band = im.crop((0, SKY_H - NEAR_H, P, SKY_H))
    wide = Image.new("RGBA", (P + VW, NEAR_H), (0, 0, 0, 0))
    wide.paste(band, (0, 0))
    wide.paste(band.crop((0, 0, VW, NEAR_H)), (P, 0))
    return wide


def spans_of(im, thr=110):
    w, h = im.size
    raw = im.tobytes()
    rows = []
    for y in range(h):
        row, x = [], 0
        base = y * w * 4
        while x < w:
            if raw[base + x * 4 + 3] >= thr:
                x0, buf = x, []
                while x < w and raw[base + x * 4 + 3] >= thr:
                    o = base + x * 4
                    buf.append(px10((raw[o], raw[o + 1], raw[o + 2])))
                    x += 1
                row.append((x0, b"".join(buf)))
            else:
                x += 1
        rows.append(row)
    return rows


# ---- sprite helpers -----------------------------------------------------------------------------------
def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


OUT = (16, 16, 24, 255)


def scaled(im, f, anchor, minw=2):
    w = max(minw, round(im.width * f))
    h = max(2, round(im.height * f))
    small = im.resize((w, h), Image.BOX)
    return [w, h, spans_of(small), int(anchor[0] * f), int(anchor[1] * f)]


def bucket_set(im, mpm, anchor):
    # one pre-scaled copy per distance bucket; mpm = master pixels per world metre
    return [scaled(im, (dy / SC_DIV) / mpm, anchor) for dy in BUCKETS]


# ---- the bike ----------------------------------------------------------------------------------------
BW, BH = 420, 312
CX = BW // 2
PIVOT = (CX, 282)
BIKE_MPM = 95.3           # a bike master of 6 px per vpx at the player's distance (dy 108)


def bike_layers(body, trim, suit, suit2, helm, helm2, flame):
    bike = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    d = ImageDraw.Draw(bike)
    chrome, chrome_l = (178, 184, 196, 255), (240, 244, 252, 255)
    dk = shade(body, 0.55) + (255,)
    md = body + (255,)
    lt = shade(body, 1.35) + (255,)
    for s in (-1, 1):
        d.line([(CX + s * 66, 172), (CX + s * 72, 244)], fill=OUT, width=20)
        d.line([(CX + s * 66, 172), (CX + s * 72, 244)], fill=chrome, width=14)
        d.line([(CX + s * 63, 176), (CX + s * 69, 240)], fill=chrome_l, width=4)
    d.rounded_rectangle([CX - 29, 196, CX + 29, 283], radius=16, fill=(26, 26, 32, 255), outline=OUT, width=3)
    for y in range(206, 278, 11):
        d.line([(CX - 24, y), (CX + 24, y + 2)], fill=(58, 58, 68, 255), width=3)
    for s in (-1, 1):
        d.rectangle([CX + s * 34 - 6, 200, CX + s * 34 + 6, 262], fill=(70, 74, 86, 255), outline=OUT)
    d.polygon([(CX - 44, 108), (CX + 44, 108), (CX + 66, 206), (CX - 66, 206)], fill=md, outline=OUT, width=3)
    d.polygon([(CX - 44, 108), (CX - 14, 108), (CX - 22, 206), (CX - 66, 206)], fill=dk)
    d.polygon([(CX + 14, 108), (CX + 30, 108), (CX + 46, 206), (CX + 26, 206)], fill=lt)
    d.rectangle([CX - 8, 108, CX + 8, 206], fill=trim + (255,))
    d.rectangle([CX - 40, 158, CX + 40, 176], fill=(255, 70, 60, 255), outline=OUT, width=2)
    d.rectangle([CX - 20, 161, CX + 20, 173], fill=(255, 220, 196, 255))
    d.rectangle([CX - 20, 184, CX + 20, 203], fill=(240, 240, 232, 255), outline=OUT)
    for k in range(4):
        d.rectangle([CX - 15 + k * 8, 188, CX - 11 + k * 8, 199], fill=(30, 30, 40, 255))
    d.line([(CX - 98, 70), (CX + 98, 70)], fill=OUT, width=16)
    d.line([(CX - 98, 70), (CX + 98, 70)], fill=(70, 74, 86, 255), width=9)
    for s in (-1, 1):
        d.line([(CX + s * 96, 66), (CX + s * 106, 38)], fill=OUT, width=7)
        d.ellipse([CX + s * 106 - 17, 18, CX + s * 106 + 17, 46], fill=md, outline=OUT, width=3)
        d.ellipse([CX + s * 106 - 9, 24, CX + s * 106 + 9, 40], fill=(150, 190, 230, 255))
    if flame:
        for s in (-1, 1):
            fx, fy = CX + s * 72, 248
            ln = 18 + flame * 30
            for k, col in enumerate(((255, 110, 20), (255, 196, 60), (255, 250, 220))):
                r = 18 - k * 5
                d.polygon([(fx - r, fy), (fx + r, fy), (fx + s * 4, fy + ln - k * 9)], fill=col + (255,))
                d.ellipse([fx - r, fy - r // 2, fx + r, fy + r], fill=col + (255,))
    for s in (-1, 1):
        d.ellipse([CX + s * 72 - 12, 236, CX + s * 72 + 12, 256], fill=(40, 40, 48, 255), outline=OUT, width=2)

    rider = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    d = ImageDraw.Draw(rider)
    su = suit + (255,)
    su_d = shade(suit, 0.62) + (255,)
    su_l = shade(suit, 1.25) + (255,)
    s2 = suit2 + (255,)
    for s in (-1, 1):
        d.polygon([(CX + s * 20, 124), (CX + s * 44, 126), (CX + s * 74, 170), (CX + s * 66, 204), (CX + s * 40, 206),
                   (CX + s * 24, 166)], fill=su, outline=OUT, width=3)
        d.polygon([(CX + s * 24, 166), (CX + s * 40, 206), (CX + s * 66, 204), (CX + s * 58, 186)], fill=su_d)
        d.ellipse([CX + s * 74 - 11, 164, CX + s * 74 + 8, 186], fill=trim + (255,), outline=OUT)
        d.rounded_rectangle([CX + s * 46 - 14, 198, CX + s * 46 + 14, 244], radius=6, fill=(30, 30, 38, 255), outline=OUT)
    d.polygon([(CX - 36, 150), (CX + 36, 150), (CX + 54, 100), (CX + 44, 62), (CX - 44, 62), (CX - 54, 100)], fill=su, outline=OUT, width=3)
    d.polygon([(CX - 36, 150), (CX - 54, 100), (CX - 44, 62), (CX - 12, 62), (CX - 14, 150)], fill=su_d)
    d.polygon([(CX + 24, 150), (CX + 14, 62), (CX + 44, 62), (CX + 54, 100), (CX + 36, 150)], fill=su_l)
    d.rectangle([CX - 6, 64, CX + 6, 148], fill=s2)
    d.polygon([(CX - 52, 72), (CX - 44, 62), (CX - 30, 80), (CX - 36, 96)], fill=s2)
    d.polygon([(CX + 52, 72), (CX + 44, 62), (CX + 30, 80), (CX + 36, 96)], fill=s2)
    for s in (-1, 1):
        d.line([(CX + s * 50, 88), (CX + s * 94, 70)], fill=OUT, width=28)
        d.line([(CX + s * 50, 88), (CX + s * 94, 70)], fill=su, width=21)
        d.line([(CX + s * 58, 84), (CX + s * 88, 72)], fill=s2, width=6)
        d.ellipse([CX + s * 98 - 15, 54, CX + s * 98 + 15, 84], fill=(24, 24, 30, 255), outline=OUT, width=2)
    d.rectangle([CX - 15, 62, CX + 15, 86], fill=(26, 26, 34, 255))
    d.ellipse([CX - 38, 0, CX + 38, 76], fill=helm + (255,), outline=OUT, width=3)
    d.pieslice([CX - 38, 0, CX + 38, 76], 180, 360, fill=shade(helm, 1.1) + (255,))
    d.rectangle([CX - 9, 2, CX + 9, 70], fill=helm2 + (255,))
    d.arc([CX - 30, 8, CX + 30, 62], 200, 250, fill=(255, 255, 255, 255), width=5)
    d.rectangle([CX - 26, 58, CX + 26, 72], fill=shade(helm, 0.6) + (255,))
    d.ellipse([CX - 38, 0, CX + 38, 76], outline=OUT, width=3)
    return bike, rider


def compose_bike(bike, rider, steps, shift_scale=8.0, pitch=0.0):
    a = steps * 8.0
    canvas = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    sh = ImageDraw.Draw(canvas)
    ox = int(steps * 12)
    sh.ellipse([CX - 74 + ox, 266, CX + 74 + ox, 296], fill=(18, 18, 26, 255))
    b = bike.rotate(-a, resample=Image.BICUBIC, center=PIVOT)
    r = rider.rotate(-a * 1.18, resample=Image.BICUBIC, center=PIVOT)
    if pitch:
        r = r.transform(r.size, Image.AFFINE, (1, 0, 0, 0, 1, -pitch), Image.BICUBIC)
    r = r.transform(r.size, Image.AFFINE, (1, 0, -steps * shift_scale, 0, 1, 0), Image.BICUBIC)
    canvas.alpha_composite(b)
    canvas.alpha_composite(r)
    return canvas


def tumble_part(layer, angle, center):
    return layer.rotate(angle, resample=Image.BICUBIC, center=center)


# ---- traffic cars ---------------------------------------------------------------------------------------
def draw_car(kind, body):
    w, h = (300, 190) if kind == 0 else (320, 260)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    md, dk, lt = body + (255,), shade(body, 0.55) + (255,), shade(body, 1.3) + (255,)
    glass = (70, 100, 150, 255)
    d.ellipse([10, h - 28, w - 10, h - 2], fill=(18, 18, 26, 255))
    for x0 in (22, w - 66):
        d.rounded_rectangle([x0, h - 66, x0 + 44, h - 10], radius=8, fill=(24, 24, 30, 255), outline=OUT, width=2)
    if kind == 0:
        d.polygon([(30, h - 40), (w - 30, h - 40), (w - 14, 100), (w - 50, 40), (50, 40), (14, 100)], fill=md, outline=OUT)
        d.polygon([(66, 48), (w - 66, 48), (w - 52, 100), (52, 100)], fill=glass, outline=OUT)
        d.polygon([(66, 48), (w // 2, 48), (w // 2 - 20, 100), (52, 100)], fill=(120, 160, 210, 255))
        d.rectangle([20, 108, w - 20, h - 46], fill=md, outline=OUT)
        d.rectangle([20, 108, w - 20, 118], fill=lt)
    else:
        d.rectangle([20, 10, w - 20, h - 40], fill=md, outline=OUT, width=3)
        d.rectangle([20, 10, w - 20, 30], fill=lt)
        d.rectangle([20, h - 70, w - 20, h - 40], fill=dk)
        d.line([(w // 2, 30), (w // 2, h - 70)], fill=OUT, width=4)
        d.rectangle([w - 90, 50, w - 40, 90], fill=glass)
    for x0 in (26, w - 80):
        d.rectangle([x0, h - 86, x0 + 54, h - 66], fill=(255, 60, 50, 255), outline=OUT, width=2)
    d.rectangle([w // 2 - 30, h - 80, w // 2 + 30, h - 52], fill=(240, 240, 232, 255), outline=OUT)
    for k in range(4):
        d.rectangle([w // 2 - 22 + k * 12, h - 74, w // 2 - 16 + k * 12, h - 58], fill=(30, 30, 40, 255))
    return im


# ---- roadside objects ---------------------------------------------------------------------------------
def poly_curve(p0, p1, p2, n=14):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in [i / n for i in range(n + 1)]]


def thick(d, pts, w0, w1, fill, outline=None):
    n = len(pts) - 1
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        nx, ny = pts[min(i + 1, n)][0] - pts[max(i - 1, 0)][0], pts[min(i + 1, n)][1] - pts[max(i - 1, 0)][1]
        ln = math.hypot(nx, ny) or 1
        wd = (w0 + (w1 - w0) * i / n) / 2
        left.append((x - ny / ln * wd, y + nx / ln * wd))
        right.append((x + ny / ln * wd, y - nx / ln * wd))
    d.polygon(left + right[::-1], fill=fill, outline=outline)


def art_palm():
    im = Image.new("RGBA", (210, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    trunk = poly_curve((96, 296), (88, 190), (120, 74))
    thick(d, trunk, 26, 14, (150, 104, 60, 255), OUT)
    for i in range(2, len(trunk) - 1, 2):
        x, y = trunk[i]
        d.line([(x - 12, y), (x + 12, y - 3)], fill=(110, 72, 40, 255), width=3)
    cx_, cy = trunk[-1]
    for ang, ln in ((-170, 100), (-140, 104), (-110, 80), (-70, 80), (-40, 104), (-10, 100), (-155, 70), (-25, 70)):
        a = math.radians(ang)
        end = (cx_ + math.cos(a) * ln, cy - math.sin(-a) * ln * 0.5 + ln * 0.34)
        mid = (cx_ + math.cos(a) * ln * 0.55, cy - math.sin(-a) * ln * 0.9)
        pts = poly_curve((cx_, cy), mid, end)
        thick(d, pts, 20, 2, (36, 138, 60, 255), OUT)
        thick(d, [(x, y - 2) for x, y in pts], 8, 1, (92, 190, 84, 255))
    for ox, oy in ((-8, 8), (8, 10), (0, 16)):
        d.ellipse([cx_ + ox - 8, cy + oy - 8, cx_ + ox + 8, cy + oy + 8], fill=(110, 70, 36, 255), outline=OUT)
    return im, 30


def art_billboard(text, bg, fg):
    im = Image.new("RGBA", (210, 195), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in (44, 154):
        d.rectangle([x - 7, 100, x + 7, 192], fill=(96, 96, 108, 255), outline=OUT)
    d.rectangle([6, 8, 204, 110], fill=(40, 40, 52, 255), outline=OUT, width=3)
    d.rectangle([14, 16, 196, 102], fill=bg)
    d.polygon([(14, 102), (14, 70), (110, 102)], fill=shade(bg, 0.75))
    d.polygon([(150, 16), (196, 16), (196, 50)], fill=shade(bg, 1.25))
    f = ImageFont.truetype(BOLD, 46)
    tw = d.textlength(text, font=f)
    d.text(((210 - tw) / 2, 28), text, font=f, fill=OUT)
    d.text(((210 - tw) / 2 - 2, 26), text, font=f, fill=fg)
    return im, 30


def art_rock(base, hi):
    im = Image.new("RGBA", (110, 76), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(4, 74), (10, 44), (30, 18), (58, 6), (84, 22), (104, 50), (106, 74)]
    d.polygon(pts, fill=base, outline=OUT)
    d.polygon([(30, 18), (58, 6), (84, 22), (60, 34)], fill=hi)
    d.polygon([(4, 74), (10, 44), (36, 50), (30, 74)], fill=shade(base[:3], 0.7) + (255,))
    d.line([(60, 34), (68, 74)], fill=shade(base[:3], 0.6) + (255,), width=2)
    return im, 30


def art_bush(c1, c2):
    im = Image.new("RGBA", (130, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for ox, oy, r in ((30, 40, 26), (66, 34, 32), (100, 42, 24), (50, 30, 22), (84, 26, 20)):
        d.ellipse([ox - r, oy - r + 22, ox + r, oy + r + 22], fill=c1, outline=OUT)
    for ox, oy, r in ((60, 28, 14), (88, 34, 11), (36, 38, 10)):
        d.ellipse([ox - r, oy - r + 18, ox + r, oy + r + 18], fill=c2)
    return im, 30


def art_cactus():
    im = Image.new("RGBA", (120, 196), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    g, gd, gl = (66, 140, 70, 255), (40, 102, 52, 255), (120, 190, 110, 255)
    d.rounded_rectangle([44, 8, 76, 194], radius=16, fill=g, outline=OUT, width=3)
    d.rounded_rectangle([44, 8, 58, 194], radius=8, fill=gd)
    d.rounded_rectangle([66, 14, 72, 186], radius=3, fill=gl)
    d.rounded_rectangle([8, 70, 30, 140], radius=10, fill=g, outline=OUT, width=3)
    d.rectangle([20, 118, 50, 140], fill=g, outline=OUT, width=3)
    d.rectangle([22, 120, 46, 138], fill=g)
    d.rounded_rectangle([90, 50, 112, 120], radius=10, fill=g, outline=OUT, width=3)
    d.rectangle([70, 100, 98, 122], fill=g, outline=OUT, width=3)
    d.rectangle([72, 102, 96, 120], fill=g)
    d.ellipse([52, 0, 68, 14], fill=(240, 100, 150, 255), outline=OUT)
    return im, 30


def art_chevron():
    im = Image.new("RGBA", (72, 102), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([32, 60, 40, 100], fill=(90, 90, 100, 255), outline=OUT)
    d.rectangle([4, 4, 68, 66], fill=(250, 210, 30, 255), outline=OUT, width=3)
    for k in range(2):
        y = 14 + k * 24
        d.line([(16, y), (36, y + 14), (56, y)], fill=OUT, width=7)
    return im, 30


def art_deadtree():
    im = Image.new("RGBA", (150, 168), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    br = (96, 66, 44, 255)
    thick(d, poly_curve((74, 166), (68, 110), (76, 50)), 20, 8, br, OUT)
    thick(d, poly_curve((72, 112), (40, 96), (20, 60)), 12, 3, br, OUT)
    thick(d, poly_curve((76, 90), (110, 80), (132, 40)), 12, 3, br, OUT)
    thick(d, poly_curve((76, 56), (80, 30), (60, 6)), 9, 2, br, OUT)
    return im, 30


def art_pine(big):
    im = Image.new("RGBA", (150, 270), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([66, 232, 84, 268], fill=(96, 62, 38, 255), outline=OUT)
    g, gd = (30, 108, 84, 255), (18, 74, 62, 255)
    for k in range(4):
        top = 6 + k * 56
        half = 34 + k * 14
        d.polygon([(75 - half, top + 84), (75, top), (75 + half, top + 84)], fill=g, outline=OUT)
        d.polygon([(75 - half, top + 84), (75, top), (75 - half // 3, top + 84)], fill=gd)
        d.polygon([(75, top), (75 - half // 2 - 4, top + 40), (75 - half // 4, top + 34), (75, top + 44), (75 + half // 4, top + 34),
                   (75 + half // 2 + 4, top + 40)], fill=(250, 252, 255, 255))
    return im, 30


def art_snowrock():
    im = Image.new("RGBA", (120, 78), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(4, 76), (12, 40), (38, 14), (70, 6), (100, 28), (116, 76)], fill=(110, 124, 150, 255), outline=OUT)
    d.polygon([(12, 40), (38, 14), (70, 6), (100, 28), (112, 50), (84, 40), (62, 52), (36, 42)], fill=(250, 252, 255, 255))
    d.polygon([(4, 76), (12, 40), (36, 42), (30, 76)], fill=(80, 94, 122, 255))
    return im, 30


def art_banner(c1, c2):
    im = Image.new("RGBA", (240, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in (14, 226):
        d.rectangle([x - 5, 6, x + 5, 148], fill=(100, 100, 112, 255), outline=OUT)
    pts = poly_curve((14, 14), (120, 60), (226, 14), 12)
    d.line(pts, fill=OUT, width=4)
    for i in range(1, 12):
        x, y = pts[i]
        col = c1 if i % 2 else c2
        d.polygon([(x - 10, y), (x + 10, y), (x, y + 30)], fill=col, outline=OUT)
    return im, 30


def art_snowman():
    im = Image.new("RGBA", (72, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([6, 50, 66, 95], fill=(248, 250, 255, 255), outline=OUT, width=2)
    d.ellipse([14, 24, 58, 62], fill=(248, 250, 255, 255), outline=OUT, width=2)
    d.ellipse([20, 2, 52, 32], fill=(248, 250, 255, 255), outline=OUT, width=2)
    d.rectangle([22, 0, 50, 10], fill=(40, 40, 60, 255))
    d.rectangle([16, 8, 56, 12], fill=(40, 40, 60, 255))
    d.polygon([(36, 18), (56, 22), (36, 24)], fill=(250, 130, 30, 255))
    d.rectangle([18, 30, 54, 38], fill=(220, 40, 50, 255))
    d.ellipse([27, 14, 31, 18], fill=OUT)
    d.ellipse([41, 14, 45, 18], fill=OUT)
    return im, 30


def art_lamp():
    im = Image.new("RGBA", (120, 255), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([54, 40, 66, 254], fill=(70, 74, 92, 255), outline=OUT)
    d.line([(60, 44), (100, 30)], fill=OUT, width=10)
    d.line([(60, 44), (100, 30)], fill=(70, 74, 92, 255), width=5)
    d.ellipse([60, 2, 116, 54], fill=(255, 226, 150, 255))
    d.ellipse([72, 10, 104, 40], fill=(255, 250, 220, 255))
    d.rectangle([86, 26, 114, 36], fill=(60, 64, 80, 255), outline=OUT)
    return im, 30


def art_building(rnd, body, glow):
    im = Image.new("RGBA", (270, 510), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 20, 260, 508], fill=body, outline=OUT, width=3)
    d.rectangle([10, 20, 260, 34], fill=shade(body[:3], 1.6) + (255,))
    for y in range(50, 490, 28):
        for x in range(24, 240, 30):
            if rnd.random() < 0.6:
                d.rectangle([x, y, x + 16, y + 14], fill=rnd.choice(glow))
            else:
                d.rectangle([x, y, x + 16, y + 14], fill=shade(body[:3], 0.65) + (255,))
    d.rectangle([120, 4, 124, 22], fill=(120, 120, 140, 255))
    d.ellipse([116, 0, 128, 10], fill=(255, 60, 60, 255))
    return im, 30


def art_neon(text, col):
    im = Image.new("RGBA", (150, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([68, 110, 82, 238], fill=(70, 74, 92, 255), outline=OUT)
    d.rectangle([6, 8, 144, 116], fill=(14, 12, 30, 255), outline=col + (255,), width=5)
    d.rectangle([14, 16, 136, 108], outline=shade(col, 0.55) + (255,), width=2)
    f = ImageFont.truetype(BOLD, 34)
    tw = d.textlength(text, font=f)
    d.text(((150 - tw) / 2, 40), text, font=f, fill=col + (255,))
    return im, 30


def art_hedge():
    im = Image.new("RGBA", (130, 124), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([56, 70, 74, 122], fill=(70, 50, 40, 255), outline=OUT)
    for ox, oy, r in ((40, 50, 36), (90, 46, 32), (66, 28, 34)):
        d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=(24, 70, 60, 255), outline=OUT)
    rnd = random.Random(4)
    for _ in range(14):
        x, y = rnd.randint(20, 110), rnd.randint(10, 80)
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=rnd.choice([(255, 90, 200, 255), (90, 230, 255, 255), (255, 230, 120, 255)]))
    return im, 30


def art_gate(title, c1, c2):
    # 24 m wide: two posts at the road edges and a banner beam; the middle stays open so the road is visible
    W_, H_ = 24 * 26, 9 * 26
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in (30, W_ - 30):
        d.rectangle([x - 16, 20, x + 16, H_ - 1], fill=(220, 224, 236, 255), outline=OUT, width=3)
        for y in range(40, H_ - 20, 40):
            d.rectangle([x - 16, y, x + 16, y + 20], fill=(200, 40, 50, 255))
    d.rectangle([14, 10, W_ - 14, 60], fill=(60, 64, 80, 255), outline=OUT, width=3)
    d.rectangle([60, 56, W_ - 60, 150], fill=c1, outline=OUT, width=5)
    d.rectangle([70, 66, W_ - 70, 140], outline=c2, width=4)
    f = ImageFont.truetype(BOLD, 62)
    tw = d.textlength(title, font=f)
    d.text(((W_ - tw) / 2 + 3, 72), title, font=f, fill=OUT)
    d.text(((W_ - tw) / 2, 70), title, font=f, fill=c2)
    for k in range(14):
        d.rectangle([14 + k * 44, 10, 14 + k * 44 + 22, 34], fill=(250, 250, 250, 255) if k % 2 else (20, 20, 30, 255))
    return im, 26


SCENERY = {
    0: [("palm", art_palm, (7, 10)), ("board", lambda: art_billboard("TURBO", (220, 50, 60, 255), (255, 240, 120, 255)), (7, 6.5)),
        ("rock", lambda: art_rock((126, 126, 136, 255), (190, 190, 200, 255)), (3.7, 2.5)),
        ("bush", lambda: art_bush((46, 130, 60, 255), (96, 188, 90, 255)), (4.3, 2.3))],
    1: [("cactus", art_cactus, (4, 6.5)), ("boulder", lambda: art_rock((176, 108, 64, 255), (226, 160, 100, 255)), (4.2, 2.8)),
        ("chevron", art_chevron, (2.4, 3.4)), ("deadtree", art_deadtree, (5, 5.6))],
    2: [("pine", lambda: art_pine(True), (5, 9)), ("snowrock", art_snowrock, (4, 2.6)),
        ("banner", lambda: art_banner((60, 120, 240, 255), (250, 250, 255, 255)), (8, 5)), ("snowman", art_snowman, (2.4, 3.2))],
    3: [("lamp", art_lamp, (4, 8.5)), ("neon", lambda: art_neon("CLUB", (255, 90, 210)), (5, 8)),
        ("hedge", art_hedge, (4.3, 4.1)), ("lamp2", art_lamp, (4, 8.5))],
}


def build_scenery(th_idx, rnd):
    out = []
    for name, fn, (wm, hm) in SCENERY[th_idx]:
        im, mpm = fn()
        out.append({"name": name, "w": wm, "h": hm, "set": bucket_set(im, mpm, (im.width / 2, im.height))})
    if th_idx == 3:
        glows = [(255, 220, 120, 255), (120, 230, 255, 255), (255, 150, 220, 255)]
        for body in ((24, 26, 66, 255), (40, 24, 70, 255)):
            im, mpm = art_building(rnd, body, glows)
            out.append({"name": "tower", "w": 9, "h": 17, "set": bucket_set(im, mpm, (im.width / 2, im.height))})
    return out


def build():
    rnd = random.Random(11)
    out = {"themes": [], "far": [], "far_uni": [], "near": [], "scenery": []}
    for i, th in enumerate(THEMES):
        out["themes"].append(dict(th))
        far = make_far(th, i, rnd)
        rows = to_rows(far)
        raw = far.convert("RGB").tobytes()
        uni = []
        for y in range(SKY_H):
            row = raw[y * P * 3:(y + 1) * P * 3]
            uni.append(px10(tuple(row[:3])) if row == row[:3] * P else None)
        out["far"].append([r + r[:VW * 10] for r in rows])
        out["far_uni"].append(uni)
        out["near"].append(spans_of(make_near(th, i, rnd), 128))
        out["scenery"].append(build_scenery(i, rnd))
    colors = [((226, 36, 44), (250, 250, 250), (36, 84, 214), (250, 250, 250), (250, 250, 250), (226, 36, 44)),
              ((40, 120, 240), (250, 214, 40), (250, 214, 40), (40, 120, 240), (250, 214, 40), (40, 120, 240)),
              ((250, 190, 20), (30, 30, 40), (40, 40, 52), (250, 190, 20), (40, 40, 52), (250, 190, 20)),
              ((40, 190, 90), (250, 250, 250), (236, 238, 242), (40, 190, 90), (236, 238, 242), (40, 190, 90)),
              ((170, 70, 230), (250, 150, 230), (70, 44, 120), (250, 150, 230), (250, 150, 230), (170, 70, 230)),
              ((250, 130, 24), (250, 250, 250), (74, 74, 90), (250, 130, 24), (250, 250, 250), (250, 130, 24))]
    # player (colour 0): lean -3..3 x flame 0..2, plus wheelie, plus crash parts
    bike0, rider0 = bike_layers(*colors[0][:2], *colors[0][2:4], *colors[0][4:6], 0)
    out["player"] = []
    for steps in range(-3, 4):
        per_flame = []
        for flame in range(3):
            bk, rd = bike_layers(*colors[0][:2], *colors[0][2:4], *colors[0][4:6], flame)
            per_flame.append(scaled(compose_bike(bk, rd, steps), 1 / 6, (PIVOT[0], 283)))
        out["player"].append(per_flame)
    bk, rd = bike_layers(*colors[0][:2], *colors[0][2:4], *colors[0][4:6], 1)
    out["wheelie"] = [scaled(compose_bike(bk, rd, s, pitch=14), 1 / 6, (PIVOT[0], 283)) for s in (-1, 0, 1)]
    out["crash_rider"] = [scaled(tumble_part(rider0, a, (CX, 150)), 1 / 6, (CX, 150)) for a in range(0, 360, 30)]
    out["crash_bike"] = [scaled(tumble_part(bike0, a, (CX, 200)), 1 / 6, (CX, 200)) for a in range(0, 360, 30)]
    # rivals: 6 colours x lean (-1,0,1) x 14 scales
    out["rivals"] = []
    for body, trim, suit, suit2, helm, helm2 in colors:
        bk, rd = bike_layers(body, trim, suit, suit2, helm, helm2, 0)
        per_lean = []
        for steps in (-1, 0, 1):
            im = compose_bike(bk, rd, steps).crop((0, 0, BW, 284))
            per_lean.append(bucket_set(im, BIKE_MPM, (PIVOT[0], 283)))
        out["rivals"].append(per_lean)
    out["cars"] = []
    for kind, wm, hm in ((0, 3.0, 1.9), (1, 3.2, 2.6)):
        per = []
        for body in ((60, 140, 230), (230, 200, 40), (210, 50, 60), (240, 240, 244)):
            im = draw_car(kind, body)
            per.append(bucket_set(im, im.width / wm, (im.width / 2, im.height)))
        out["cars"].append({"w": wm, "h": hm, "colors": per})
    out["gates"] = []
    for title, c1, c2 in (("EXTEND TIME", (200, 30, 40, 255), (255, 240, 100, 255)), ("GOAL", (30, 60, 190, 255), (255, 255, 255, 255))):
        im, mpm = art_gate(title, c1, c2)
        out["gates"].append(bucket_set(im, mpm, (im.width / 2, im.height)))
    save_bundle("g_moto.bin", out)


if __name__ == "__main__":
    build()
