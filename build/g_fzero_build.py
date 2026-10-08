# Build-time art for the hover-racing game: car sprites (as opaque spans), themed skylines and palettes.
# One "virtual pixel" (vpx) is 6x6 screen pixels, so every sprite is stored already expanded to 12 bytes per vpx.
import math
import random
from PIL import Image, ImageDraw
from buildlib import save_bundle, rgb565

VW = 320
SKY_TOP, SKY_BOTTOM = 14, 69          # vrows covered by the sky gradient
SKYLINE_FROM = 34                      # first vrow of the scrolling skyline strip
SKYLINE_H = SKY_BOTTOM - SKYLINE_FROM + 1
PERIOD = 640                           # skyline strip width in vpx before it repeats


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def px12(rgb):
    return rgb565(*rgb).to_bytes(2, "little") * 6


# ---- themes ---------------------------------------------------------------------------------------
THEMES = [
    dict(name="NEON CITY",
         sky=((14, 14, 64), (120, 56, 140), (255, 150, 96)), sun=(255, 196, 90),
         ground=((8, 16, 58), (14, 28, 88)), bar=((0, 236, 255), (0, 110, 200)),
         rum=((232, 40, 64), (240, 240, 250)), road=((72, 78, 112), (84, 92, 130)), lane=(230, 230, 255),
         pit=((40, 214, 100), (20, 130, 64)), plate=((255, 224, 40), (255, 130, 0)),
         jump=((255, 60, 200), (250, 250, 255)), chk=((245, 245, 250), (20, 20, 30)), fog=(255, 150, 96),
         curve=1.0),
    dict(name="ICE LAKE",
         sky=((8, 28, 96), (96, 170, 230), (214, 240, 255)), sun=(255, 255, 255),
         ground=((196, 226, 250), (160, 204, 240)), bar=((255, 255, 255), (110, 190, 255)),
         rum=((28, 84, 200), (244, 250, 255)), road=((96, 120, 164), (110, 136, 182)), lane=(240, 250, 255),
         pit=((40, 214, 100), (20, 130, 64)), plate=((255, 224, 40), (255, 130, 0)),
         jump=((255, 60, 200), (250, 250, 255)), chk=((245, 245, 250), (20, 20, 30)), fog=(214, 240, 255),
         curve=1.05),
    dict(name="DUNE SEA",
         sky=((40, 90, 190), (240, 150, 80), (255, 214, 130)), sun=(255, 250, 200),
         ground=((226, 172, 84), (204, 148, 60)), bar=((255, 240, 120), (255, 140, 30)),
         rum=((200, 56, 28), (250, 240, 220)), road=((124, 102, 92), (138, 114, 102)), lane=(250, 236, 200),
         pit=((40, 214, 100), (20, 130, 64)), plate=((255, 224, 40), (255, 130, 0)),
         jump=((255, 60, 200), (250, 250, 255)), chk=((245, 245, 250), (20, 20, 30)), fog=(255, 214, 130),
         curve=0.85),
    dict(name="EMBER FIELD",
         sky=((24, 0, 8), (150, 30, 20), (255, 110, 30)), sun=(255, 90, 30),
         ground=((70, 10, 10), (104, 22, 12)), bar=((255, 210, 40), (255, 80, 0)),
         rum=((255, 60, 20), (36, 32, 36)), road=((62, 52, 58), (76, 62, 70)), lane=(255, 200, 120),
         pit=((40, 214, 100), (20, 130, 64)), plate=((255, 224, 40), (255, 130, 0)),
         jump=((255, 60, 200), (250, 250, 255)), chk=((245, 245, 250), (20, 20, 30)), fog=(255, 110, 30),
         curve=1.15),
]


def sky_color(th, vrow):
    t = (vrow - SKY_TOP) / (SKY_BOTTOM - SKY_TOP)
    top, mid, low = th["sky"]
    return lerp(top, mid, t / 0.6) if t < 0.6 else lerp(mid, low, (t - 0.6) / 0.4)


# ---- skylines -------------------------------------------------------------------------------------
def wrapped(fn):
    for dx in (-PERIOD, 0, PERIOD):
        fn(dx)


def make_skyline(th, idx, rnd):
    im = Image.new("RGB", (PERIOD, SKYLINE_H))
    d = ImageDraw.Draw(im)
    for y in range(SKYLINE_H):
        d.line([(0, y), (PERIOD, y)], fill=sky_color(th, SKYLINE_FROM + y))
    low = th["sky"][2]
    sunx = rnd.randint(150, 480)
    # sun disc with the retro horizontal cut lines near its bottom
    d.ellipse([sunx - 13, 8, sunx + 13, 34], fill=th["sun"])
    for k in range(5):
        y = 20 + k * 3
        d.line([(sunx - 14, y), (sunx + 14, y)], fill=sky_color(th, SKYLINE_FROM + y))
    H = SKYLINE_H
    if idx == 0:
        far = lerp((24, 24, 80), low, 0.35)
        near = (12, 14, 44)
        x = 0
        while x < PERIOD:
            w, h = rnd.randint(4, 9), rnd.randint(8, 20)
            wrapped(lambda dx, x=x, w=w, h=h: d.rectangle([x + dx, H - h, x + dx + w, H], fill=far))
            x += w + rnd.randint(0, 2)
        wrapped(lambda dx: d.ellipse([dx + 300, 4, dx + 336, 26], outline=far, width=2))
        x = 2
        while x < PERIOD - 4:
            w, h = rnd.randint(4, 10), rnd.randint(7, 27)
            kind = rnd.random()

            def tower(dx, x=x, w=w, h=h, kind=kind):
                d.rectangle([x + dx, H - h, x + dx + w, H], fill=near)
                if kind < 0.3:
                    d.line([(x + dx + w // 2, H - h), (x + dx + w // 2, H - h - 5)], fill=near)
                elif kind < 0.5:
                    d.polygon([(x + dx, H - h), (x + dx + w, H - h), (x + dx + w // 2, H - h - 6)], fill=near)
                for wy in range(H - h + 2, H - 1, 2):
                    for wx in range(x + dx + 1, x + dx + w, 2):
                        if rnd.random() < 0.35:
                            d.point((wx, wy), fill=rnd.choice([(80, 230, 255), (255, 220, 120), (200, 240, 255)]))
            wrapped(tower)
            x += w + rnd.randint(1, 3)
    elif idx == 1:
        far = lerp((120, 170, 230), low, 0.4)
        near = (216, 236, 252)
        shade = (110, 150, 210)
        x = 0
        while x < PERIOD:
            w, h = rnd.randint(30, 60), rnd.randint(10, 20)
            wrapped(lambda dx, x=x, w=w, h=h: d.polygon([(x + dx, H), (x + dx + w // 2, H - h), (x + dx + w, H)], fill=far))
            x += w // 2
        x = 0
        while x < PERIOD:
            w, h = rnd.randint(22, 46), rnd.randint(8, 24)

            def peak(dx, x=x, w=w, h=h):
                d.polygon([(x + dx, H), (x + dx + w // 2, H - h), (x + dx + w, H)], fill=shade)
                d.polygon([(x + dx + w // 2, H - h), (x + dx + w, H), (x + dx + w // 2 + 2, H)], fill=near)
                d.polygon([(x + dx + w // 2, H - h), (x + dx + w // 2 - 4, H - h + 6),
                           (x + dx + w // 2 + 4, H - h + 6)], fill=(255, 255, 255))
            wrapped(peak)
            x += w * 2 // 3
    elif idx == 2:
        far = lerp((220, 130, 80), low, 0.3)
        near = (150, 82, 40)
        light = (214, 140, 70)
        for x in range(0, PERIOD, 1):
            h = 5 + 4 * math.sin(x / 31.0) + 3 * math.sin(x / 11.0 + 1)
            d.line([(x, H - int(h)), (x, H)], fill=far)
        for cx_, hh in ((90, 18), (350, 14), (530, 22)):
            wrapped(lambda dx, cx_=cx_, hh=hh: (
                d.polygon([(cx_ + dx - hh, H), (cx_ + dx, H - hh), (cx_ + dx + hh, H)], fill=light),
                d.polygon([(cx_ + dx, H - hh), (cx_ + dx + hh, H), (cx_ + dx + 1, H)], fill=near)))
        wrapped(lambda dx: d.rectangle([dx + 210, H - 12, dx + 232, H], fill=near))
        wrapped(lambda dx: d.rectangle([dx + 214, H - 15, dx + 228, H - 12], fill=near))
        for x in range(0, PERIOD):
            h = 3 + 3 * math.sin(x / 17.0 + 2) + 2 * math.sin(x / 7.0)
            d.line([(x, H - int(h)), (x, H)], fill=near)
    else:
        far = lerp((120, 20, 14), low, 0.35)
        near = (30, 8, 8)
        lava = (255, 170, 30)
        x = 0
        while x < PERIOD:
            w, h = rnd.randint(40, 80), rnd.randint(8, 24)

            def cone(dx, x=x, w=w, h=h):
                d.polygon([(x + dx, H), (x + dx + w // 2 - 3, H - h), (x + dx + w // 2 + 3, H - h),
                           (x + dx + w, H)], fill=near)
                d.line([(x + dx + w // 2 - 2, H - h), (x + dx + w // 2 - 6, H - h // 2)], fill=lava)
                d.line([(x + dx + w // 2 + 2, H - h), (x + dx + w // 2 + 5, H - h // 2 - 1)], fill=lava)
                d.ellipse([x + dx + w // 2 - 5, H - h - 3, x + dx + w // 2 + 5, H - h + 1], fill=lava)
            wrapped(cone)
            x += w * 3 // 4
        for _ in range(26):
            sx, sy = rnd.randint(0, PERIOD), rnd.randint(2, 16)
            wrapped(lambda dx, sx=sx, sy=sy: d.ellipse([sx + dx, sy, sx + dx + 3, sy + 1], fill=far))
    raw = im.tobytes()
    rows = []
    for y in range(SKYLINE_H):
        line = b"".join(px12(tuple(raw[(y * PERIOD + x) * 3:(y * PERIOD + x) * 3 + 3])) for x in range(PERIOD))
        rows.append(line + line[:VW * 12])
    return rows


# ---- cars -----------------------------------------------------------------------------------------
CW, CH = 576, 400
SHAPES = 2


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def draw_car(shape, body, accent, flame, glow):
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    out = (14, 16, 30, 255)
    dark = shade(body, 0.55) + (255,)
    mid = body + (255,)
    lite = shade(body, 1.3) + (255,)
    acc = accent + (255,)
    cx = 288

    def both(pts, **kw):
        d.polygon(pts, **kw)
        d.polygon([(2 * cx - x, y) for x, y in pts], **kw)

    d.ellipse([90, 290, 486, 330], fill=(10, 12, 30, 255))
    if shape == 0:
        both([(cx - 86, 250), (24, 196), (44, 150), (cx - 150, 176)], fill=dark, outline=out)
        both([(cx - 118, 292), (cx - 224, 214), (cx - 150, 140), (cx - 62, 140), (cx - 62, 292)], fill=mid, outline=out)
        both([(cx - 118, 292), (cx - 224, 214), (cx - 205, 205), (cx - 118, 268)], fill=dark)
        d.polygon([(cx - 66, 140), (cx + 66, 140), (cx + 44, 70), (cx - 44, 70)], fill=lite, outline=out)
        d.ellipse([cx - 52, 42, cx + 52, 142], fill=(40, 70, 130, 255), outline=out)
        d.ellipse([cx - 34, 52, cx + 10, 92], fill=(190, 240, 255, 255))
        d.polygon([(cx - 14, 70), (cx + 14, 70), (cx + 22, 6), (cx - 22, 20)], fill=acc, outline=out)
        d.rectangle([cx - 20, 150, cx + 20, 292], fill=acc)
        pods = ((cx - 112, 252), (cx + 112, 252))
    else:
        both([(cx - 70, 232), (cx - 270, 214), (cx - 258, 180), (cx - 120, 190)], fill=acc, outline=out)
        both([(cx - 100, 296), (cx - 200, 226), (cx - 140, 150), (cx - 40, 160), (cx - 40, 296)], fill=mid, outline=out)
        both([(cx - 100, 296), (cx - 200, 226), (cx - 180, 220), (cx - 100, 272)], fill=dark)
        d.polygon([(cx - 70, 160), (cx + 70, 160), (cx + 40, 96), (cx - 40, 96)], fill=lite, outline=out)
        d.ellipse([cx - 44, 74, cx + 44, 168], fill=(36, 60, 120, 255), outline=out)
        d.ellipse([cx - 28, 86, cx + 6, 120], fill=(190, 240, 255, 255))
        both([(cx - 118, 160), (cx - 96, 160), (cx - 90, 40), (cx - 124, 56)], fill=acc, outline=out)
        d.rectangle([cx - 14, 170, cx + 14, 296], fill=acc)
        pods = ((cx - 96, 262), (cx + 96, 262))
    for px_, py in pods:
        if flame:
            ln = 56 + flame * 36
            for k, col in enumerate(((255, 120, 20), (255, 200, 60), (255, 250, 220))):
                r = 40 - k * 12
                d.polygon([(px_ - r, py), (px_ + r, py), (px_, py + ln - k * 14)], fill=col + (255,))
        d.ellipse([px_ - 46, py - 46, px_ + 46, py + 46], fill=(30, 32, 44, 255), outline=out)
        d.ellipse([px_ - 34, py - 34, px_ + 34, py + 34], fill=shade(glow, 0.6) + (255,))
        d.ellipse([px_ - 22, py - 22, px_ + 22, py + 22], fill=glow + (255,))
        d.ellipse([px_ - 10, py - 10, px_ + 10, py + 10], fill=(255, 255, 255, 255))
    return im


def tilted(im, tilt):
    if tilt == 0:
        return im
    sq = 1 - 0.07 * abs(tilt)
    im = im.transform(im.size, Image.AFFINE, (1 / sq, 0, 288 - 288 / sq, 0, 1, 0), Image.BICUBIC)
    return im.rotate(-tilt * 7, resample=Image.BICUBIC, center=(288, 310))


def spans_of(im):
    w, h = im.size
    px = im.load()
    rows = []
    for y in range(h):
        row, x = [], 0
        while x < w:
            if px[x, y][3] >= 120:
                x0, buf = x, []
                while x < w and px[x, y][3] >= 120:
                    buf.append(px12(px[x, y][:3]))
                    x += 1
                row.append((x0, b"".join(buf)))
            else:
                x += 1
        rows.append(row)
    return rows


def sprite(im, w, h):
    small = im.resize((w, h), Image.BOX)
    return [w, h, spans_of(small)]


def build():
    rnd = random.Random(7)
    out = {"themes": [], "skylines": [], "sky_rows": []}
    for i, th in enumerate(THEMES):
        out["themes"].append({k: v for k, v in th.items()})
        out["skylines"].append(make_skyline(th, i, rnd))
        out["sky_rows"].append([sky_color(th, v) for v in range(SKY_TOP, SKYLINE_FROM)])
    # player: 5 bank angles x 3 flame sizes, 40 vpx wide (the canvas also holds the flame)
    out["player"] = []
    master = {}
    for flame in range(3):
        master[flame] = draw_car(0, (40, 90, 230), (240, 240, 250), flame, (80, 230, 255))
    for tilt in range(-2, 3):
        out["player"].append([sprite(tilted(master[f], tilt), 40, 28) for f in range(3)])
    # rivals: 2 shapes x 6 colour schemes x 14 scales (widths 32 .. 3 vpx)
    schemes = [((220, 40, 50), (250, 220, 60)), ((40, 190, 80), (240, 240, 240)), ((240, 200, 30), (40, 40, 60)),
               ((160, 60, 220), (250, 140, 220)), ((250, 130, 20), (250, 250, 230)), ((235, 235, 240), (200, 40, 50))]
    out["rivals"] = []
    for shape in range(SHAPES):
        per_scheme = []
        for body, accent in schemes:
            full = draw_car(shape, body, accent, 0, (255, 190, 90)).crop((0, 6, CW, 336))
            per_scheme.append([sprite(full, max(2, round(32 * 0.835 ** k)),
                                      max(2, round(32 * 0.835 ** k * 330 / CW))) for k in range(14)])
        out["rivals"].append(per_scheme)
    save_bundle("g_fzero.bin", out)


if __name__ == "__main__":
    build()
