# Backgrounds (parallax strips), effects, pickups, HUD and labels for the Battletoads build.
import math, random
from PIL import Image, ImageDraw, ImageFont
from g_battletoads_art import *
from buildlib import BOLD

VW, VH = 960, 540
# (first row, last row exclusive, parallax speed, tile period) - rows share one scroll offset
BANDS = [(0, 150, 0.04, 1920), (150, 215, 0.12, 1920), (215, 262, 0.28, 1920), (262, 305, 0.40, 1920),
         (305, 345, 0.55, 1920), (345, 540, 1.0, 960)]

PALS = [
    dict(sky=((16, 8, 58), (236, 118, 92)), star=(255, 240, 220), planet=(214, 150, 110), mesa=(116, 60, 112),
         walls=((146, 68, 76), (176, 86, 64), (206, 112, 68)), ground=(166, 108, 76), gdark=(122, 78, 62), glight=(200, 146, 96),
         crack=(78, 46, 44)),
    dict(sky=((4, 10, 38), (46, 160, 150)), star=(210, 255, 250), planet=(120, 170, 230), mesa=(24, 64, 104),
         walls=((66, 58, 112), (94, 68, 122), (128, 80, 124)), ground=(104, 82, 112), gdark=(72, 56, 88), glight=(140, 112, 150),
         crack=(40, 28, 56)),
]


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def sky_color(pal, y):
    return lerp(pal["sky"][0], pal["sky"][1], min(1.0, y / 205.0) ** 1.6)


def strip_rows(img):
    data = pack565(img)
    w = img.width
    return [data[y * w * 4:(y + 1) * w * 4] for y in range(img.height)]


def wrapped(draw_fn, P, x):
    # Draw a periodic feature so its overhang reappears on the opposite side of the tile.
    for k in (-1, 0, 1):
        draw_fn(x + k * P)


def make_tile(P, h, painter):
    im = Image.new("RGB", (P, h))
    painter(im, ImageDraw.Draw(im))
    full = Image.new("RGB", (P + VW, h))
    full.paste(im, (0, 0))
    full.paste(im, (P, 0))
    return full


def sky_band(pal, rnd, y0, y1, P):
    def paint(im, d):
        for y in range(y1 - y0):
            d.line((0, y, P, y), fill=sky_color(pal, y + y0))
        for _ in range(240):
            x, y = rnd.randrange(P), rnd.randrange(0, 125)
            d.point((x, y), fill=lerp(sky_color(pal, y), pal["star"], rnd.choice((0.5, 0.8, 1.0, 1.0))))
            if rnd.random() < 0.12:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    d.point((x + dx, y + dy), fill=lerp(sky_color(pal, y), pal["star"], 0.45))
        # big ringed planet and a pitted moon
        cx, cy, r = 700, 70, 34
        for yy in range(-r, r + 1):
            w = int(math.sqrt(r * r - yy * yy))
            for xx in range(-w, w + 1):
                lit = 0.5 + 0.5 * (-(xx * 0.7 + yy * 0.7) / r)
                base = pal["planet"]
                d.point((cx + xx, cy + yy), fill=lerp(shade(base, 0.45), light(base, 0.25), max(0, min(1, lit))))
        d.ellipse((cx - 62, cy - 9, cx + 62, cy + 9), outline=light(pal["planet"], 0.5), width=2)
        for xx in range(-r, r + 1):
            yy = int(9 * math.sqrt(max(0, 1 - (xx / 62) ** 2)))
            d.point((cx + xx, cy + yy), fill=light(pal["planet"], 0.5))
            d.point((cx + xx, cy + yy + 1), fill=light(pal["planet"], 0.5))
        mx, my = 250, 52
        d.ellipse((mx - 20, my - 20, mx + 20, my + 20), fill=(222, 222, 236))
        d.ellipse((mx - 4, my - 20, mx + 26, my + 20), fill=sky_color(pal, my))
        for ox, oy, rr in ((-11, -4, 4), (-6, 8, 3), (-14, 9, 2)):
            d.ellipse((mx + ox - rr, my + oy - rr, mx + ox + rr, my + oy + rr), fill=(190, 190, 205))
    return make_tile(P, y1 - y0, paint)


def mesa_band(pal, rnd, y0, y1, P):
    haze = lerp(pal["mesa"], sky_color(pal, 200), 0.35)
    h = y1 - y0

    def paint(im, d):
        for y in range(h):
            d.line((0, y, P, y), fill=sky_color(pal, y + y0))
        x = 0
        while x < P:
            w = rnd.randrange(110, 260)
            top = h - rnd.randrange(24, 60)

            def draw(xx):
                d.polygon([(xx, h), (xx + 8, top + 8), (xx + 20, top), (xx + w - 24, top), (xx + w - 8, top + 10), (xx + w, h)], fill=haze)
                d.line((xx + 20, top, xx + w - 24, top), fill=light(haze, 0.35))
                for sx in range(xx + 30, xx + w - 20, 34):
                    d.line((sx, top + 4, sx - 4, h), fill=shade(haze, 0.8))
            wrapped(draw, P, x)
            x += w - rnd.randrange(10, 50)
    return make_tile(P, h, paint)


def wall_band(pal, rnd, y0, y1, P, idx):
    base = pal["walls"][idx]
    h = y1 - y0

    def paint(im, d):
        for y in range(h):
            d.line((0, y, P, y), fill=lerp(light(base, 0.1), shade(base, 0.78), y / h))
        x = 0
        while x < P:
            w = rnd.randrange(40, 150)
            col = rnd.choice((shade(base, 0.84), base, light(base, 0.08), shade(base, 0.92)))
            step = rnd.randrange(9, 15)

            def draw(xx):
                d.rectangle((xx, 3, xx + w - 2, h - 1), fill=col)
                d.line((xx, 3, xx, h), fill=shade(base, 0.6))
                d.line((xx + 1, 3, xx + 1, h), fill=light(col, 0.18))
                for sy in range(8 + step % 5, h - 4, step):
                    d.line((xx + 3, sy, xx + w - 6, sy), fill=shade(col, 0.82))
            wrapped(draw, P, x)
            x += w
        for _ in range(60):
            cx, cy = rnd.randrange(P), rnd.randrange(8, h - 8)
            d.line((cx, cy, cx + rnd.randrange(-3, 4), cy + rnd.randrange(6, 16)), fill=shade(base, 0.55))
        d.rectangle((0, 0, P, 2), fill=light(base, 0.45))
        d.rectangle((0, 3, P, 4), fill=shade(base, 0.6))
        d.rectangle((0, h - 3, P, h), fill=shade(base, 0.5))
    return make_tile(P, h, paint)


def ground_band(pal, rnd, y0, y1, P):
    h = y1 - y0

    def paint(im, d):
        for y in range(h):
            t = y / h
            c = lerp(shade(pal["ground"], 0.7), pal["ground"], t / 0.3) if t < 0.3 else lerp(pal["ground"], light(pal["ground"], 0.05), t)
            d.line((0, y, P, y), fill=c)
        for _ in range(26):
            x, y, ln = rnd.randrange(P), rnd.randrange(30, h), rnd.randrange(20, 70)
            wrapped(lambda xx: d.line((xx, y, xx + ln, y), fill=pal["glight"]), P, x)
        for cx in (150, 600, 800):
            cy, rx, ry = rnd.randrange(60, h - 30), rnd.randrange(34, 56), rnd.randrange(8, 13)

            def draw(xx):
                d.ellipse((xx - rx, cy - ry, xx + rx, cy + ry), fill=shade(pal["ground"], 0.78), outline=pal["gdark"])
                d.arc((xx - rx - 2, cy - ry - 2, xx + rx + 2, cy + ry + 2), 190, 350, fill=pal["glight"])
            wrapped(draw, P, cx)
        for _ in range(60):
            x, y, rr = rnd.randrange(P), rnd.randrange(24, h - 3), rnd.randrange(2, 6)

            def draw(xx):
                d.ellipse((xx - rr, y - rr // 2, xx + rr, y + rr // 2 + 1), fill=pal["gdark"])
                d.ellipse((xx - rr, y - rr // 2 - 1, xx + rr - 1, y + rr // 2 - 1), fill=pal["glight"])
            wrapped(draw, P, x)
        for _ in range(16):
            x, y = rnd.randrange(P), rnd.randrange(30, h - 5)
            pts = [(0, 0)]
            for _ in range(4):
                pts.append((pts[-1][0] + rnd.randrange(4, 14), pts[-1][1] + rnd.randrange(-3, 4)))
            wrapped(lambda xx: d.line([(p[0] + xx, p[1] + y) for p in pts], fill=pal["crack"]), P, x)
    return make_tile(P, h, paint)


def build_background(pi, seed):
    rnd = random.Random(seed)
    pal = PALS[pi]
    out = []
    for bi, (y0, y1, spd, P) in enumerate(BANDS):
        if bi == 0:
            im = sky_band(pal, rnd, y0, y1, P)
        elif bi == 1:
            im = mesa_band(pal, rnd, y0, y1, P)
        elif bi < 5:
            im = wall_band(pal, rnd, y0, y1, P, bi - 2)
        else:
            im = ground_band(pal, rnd, y0, y1, P)
        out.append(strip_rows(im))
    return out


def shadow_sprites(pi):
    col = shade(PALS[pi]["ground"], 0.52)
    res = []
    for w, h in ((50, 11), (38, 9), (28, 7), (74, 14), (112, 20)):
        im = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((1, 1, w, h), fill=col + (255,))
        res.append(to_sprite(im, (w + 2) // 2, (h + 2) // 2))
    return res


# ---- effects --------------------------------------------------------------------------------------------
def star_pts(cx, cy, r1, r2, n, rot=0):
    pts = []
    for i in range(n * 2):
        a = math.radians(rot + i * 180 / n - 90)
        r = r1 if i % 2 == 0 else r2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def fx_canvas(size, fn):
    cv = Cv(size, size, size // 2)
    fn(cv)
    return to_sprite(to_virtual(cv), cv.ox, cv.oy)


def effects():
    fx = {"spark": [], "pow": [], "stars": [], "dust": [], "ring": [], "boom": [], "fly": []}
    for i in range(6):
        r = 7 + i * 4

        def f(cv, i=i, r=r):
            if i < 5:
                cv.poly(star_pts(0, 0, r, r * 0.38, 8, i * 11), OUT)
                cv.poly(star_pts(0, 0, r - 1.8, r * 0.34, 8, i * 11), (255, 214, 60))
                cv.poly(star_pts(0, 0, r * 0.55, r * 0.2, 8, i * 11), (255, 255, 240))
            else:
                for k in range(6):
                    a = math.radians(k * 60 + 15)
                    cv.circ(r * 0.9 * math.cos(a), r * 0.9 * math.sin(a), 1.6, (255, 230, 120))
        fx["spark"].append(fx_canvas(80, f))
    for i in range(7):
        r = 14 + i * 6

        def f(cv, i=i, r=r):
            rnd = random.Random(i)
            pts = []
            for k in range(14):
                a = math.radians(k * 360 / 14 + i * 9)
                rr = r * (1.0 if k % 2 == 0 else 0.55) * (0.88 + 0.24 * rnd.random())
                pts.append((rr * math.cos(a), rr * math.sin(a) * 0.85))
            cv.poly([(x * 1.1, y * 1.1) for x, y in pts], OUT)
            cv.poly(pts, (230, 40, 40) if i < 6 else (240, 140, 60))
            cv.poly([(x * 0.7, y * 0.7) for x, y in pts], (255, 200, 40))
            cv.poly([(x * 0.38, y * 0.38) for x, y in pts], (255, 255, 235))
        fx["pow"].append(fx_canvas(160, f))
    for i in range(6):
        def f(cv, i=i):
            for k in range(3):
                a = math.radians(i * 60 + k * 120)
                x, y = 17 * math.cos(a), 5 * math.sin(a)
                cv.poly(star_pts(x, y, 5.5, 2.2, 5, i * 20), OUT)
                cv.poly(star_pts(x, y, 4.3, 1.8, 5, i * 20), (255, 224, 70))
        fx["stars"].append(fx_canvas(60, f))
    for i in range(5):
        def f(cv, i=i):
            for k in range(5):
                a = math.radians(k * 72 + 20)
                d = 4 + i * 4
                cv.circ(d * math.cos(a) * 1.3, d * math.sin(a) * 0.5, 5 + i * 0.6 - k % 2, (216, 190, 160))
            cv.circ(0, 0, 4 + i, (236, 214, 184))
        fx["dust"].append(fx_canvas(80, f))
    for i in range(7):
        def f(cv, i=i):
            r = 8 + i * 15
            for rr, w, col in ((r, 5.5, OUT), (r, 3.4, (255, 214, 80)), (r - 1.5, 1.2, (255, 255, 230))):
                pts = cv.ellpts(0, 0, rr, rr * 0.28, 0, 48)
                cv.polyline(pts + [pts[0]], w, col)
        fx["ring"].append(fx_canvas(240, f))
    for i in range(8):
        def f(cv, i=i):
            rnd = random.Random(3)
            balls = []
            for k in range(7):
                a = math.radians(k * 51)
                d = 6 + i * 3.4
                r = (12 - abs(i - 3) * 1.3) * (0.7 + 0.5 * rnd.random())
                if r > 1:
                    balls.append((d * math.cos(a), d * math.sin(a), r))
            for x, y, r in balls:
                cv.circ(x, y, r + 1.2, OUT)
            for x, y, r in balls:
                cv.circ(x, y, r, (240, 100, 40))
                cv.circ(x - 1, y - 1, r * 0.6, (255, 210, 70))
            cv.circ(0, 0, max(1, 14 - i * 1.4), (255, 250, 220))
        fx["boom"].append(fx_canvas(120, f))
    for i in range(2):
        def f(cv, i=i):
            cv.circ(0, 0, 14, (60, 120, 70))
            cv.circ(0, 0, 12, (24, 70, 40))
            cv.ell(0, 0, 5.5, 3.8, OUT)
            cv.ell(0, 0, 4.4, 2.8, (30, 30, 40))
            cv.circ(3.6, -0.6, 1.9, (230, 50, 50))
            wy = -6 if i == 0 else -3
            cv.ell(-1, wy, 5.2, 2.8, OUT, -20 if i == 0 else 10)
            cv.ell(-1, wy, 4.3, 2.0, (225, 240, 255), -20 if i == 0 else 10)
        fx["fly"].append(fx_canvas(40, f))
    return fx


def toad_icon(st, size=36):
    # Head-and-shoulders portrait used by the HUD and the 1UP pickup.
    from g_battletoads_chars import toad_head, POSE
    cv = Cv(size, size, size - 4)
    p = dict(POSE)
    p.update(mouth=0.7)
    cv.ell(0, -2, size * 0.46, 8, OUT)
    toad_head(cv, (-1, -size * 0.42), p, st, 1.0)
    return cv


def label(text, size, fill=(255, 224, 70), stroke=(40, 20, 10), sw=2):
    font = ImageFont.truetype(BOLD, size * SS)
    bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=font, stroke_width=sw * SS)
    vw, vh = (bb[2] - bb[0]) // SS + 6, (bb[3] - bb[1]) // SS + 6
    im = Image.new("RGBA", (vw * SS, vh * SS), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((3 * SS - bb[0], 3 * SS - bb[1]), text, font=font, fill=fill, stroke_width=sw * SS, stroke_fill=stroke)
    v = im.resize((vw, vh), Image.BOX)
    v.putalpha(v.getchannel("A").point(lambda a: 255 if a >= 110 else 0))
    return to_sprite(v, vw // 2, vh // 2), vw, vh
