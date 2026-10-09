# Build-time art, part 3: the four scanline-sliced parallax backgrounds.
#
# A background is a stack of horizontal bands. Each screen row belongs to exactly one band, and a band is a strip
# that repeats every PERIOD pixels (plus one extra screen so a slice never wraps), so the game scrolls it by
# slicing every row at a band-specific speed. Sky colour is baked into each band behind its silhouettes.
import math, random
from PIL import Image, ImageDraw
from g_redball_art import mix, shade, rows_of, OUT

PERIOD = 2560
SW = PERIOD + 1920
Q = 2  # supersampling inside bands

BANDS = {  # name -> list of (y0, y1, parallax factor)
    "grass": [(0, 400, 0.03), (400, 560, 0.08), (560, 690, 0.18), (690, 1080, 0.36)],
    "factory": [(0, 400, 0.03), (400, 560, 0.08), (560, 690, 0.18), (690, 1080, 0.36)],
    "lava": [(0, 400, 0.03), (400, 560, 0.08), (560, 690, 0.18), (690, 1080, 0.36)],
    "ice": [(0, 400, 0.03), (400, 560, 0.08), (560, 690, 0.18), (690, 1080, 0.36)],
}

SKY = {
    "grass": [(0, (60, 140, 238)), (380, (140, 200, 250)), (640, (214, 238, 248))],
    "factory": [(0, (22, 26, 46)), (380, (74, 58, 84)), (640, (150, 90, 80))],
    "lava": [(0, (40, 14, 38)), (380, (130, 40, 44)), (640, (230, 110, 50))],
    "ice": [(0, (150, 205, 245)), (380, (205, 232, 252)), (640, (240, 250, 255))],
}


def sky_at(world, y):
    stops = SKY[world]
    for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
        if y <= y1:
            return mix(c0, c1, max(0, (y - y0) / (y1 - y0)))
    return stops[-1][1]


BACK = {"grass": (120, 196, 120), "factory": (58, 60, 82), "lava": (62, 34, 44), "ice": (170, 208, 236)}


def new_band(world, y0, y1, backdrop=None):
    # the near band's valleys must show the mid layer's body colour, not sky, or the layers look cut apart
    h = y1 - y0
    im = Image.new("RGB", (SW * Q, h * Q))
    d = ImageDraw.Draw(im)
    for y in range(h):
        d.rectangle([0, y * Q, SW * Q, y * Q + Q], fill=backdrop or sky_at(world, y0 + y))
    return im, d


def wrap(fn, *a):
    for k in (-1, 0, 1, 2):
        fn(k * PERIOD, *a)


def cloud(d, x, y, w, col, sh):
    h = w * 0.34
    blobs = [(0.2, 0.62, 0.22), (0.42, 0.42, 0.28), (0.66, 0.5, 0.24), (0.82, 0.68, 0.17), (0.5, 0.72, 0.26)]
    for (bx, by, br) in blobs:
        cx, cy, r = x + bx * w, y + by * h, br * w
        d.ellipse([(cx - r) * Q, (cy - r) * Q, (cx + r) * Q, (cy + r) * Q], fill=col)
    d.rectangle([(x + 0.08 * w) * Q, (y + 0.78 * h) * Q, (x + 0.92 * w) * Q, (y + h * 1.02) * Q], fill=sh)
    for (bx, by, br) in blobs:
        cx, cy, r = x + bx * w, y + by * h - 3, br * w * 0.9
        d.ellipse([(cx - r) * Q, (cy - r) * Q, (cx + r) * Q, (cy + r * 0.8) * Q], fill=col)


def ridge_pts(rnd, y_base, amp, step, seed_period=PERIOD):
    n = seed_period // step
    vals = [rnd.uniform(-1, 1) for _ in range(n)]
    pts = []
    for i in range(-2, n + int(SW / step) + 3):
        a, b = vals[i % n], vals[(i + 1) % n]
        for k in range(step // 8):
            t = k / (step // 8)
            tt = (1 - math.cos(t * math.pi)) / 2
            pts.append((i * step + k * 8, y_base - amp * (a + (b - a) * tt)))
    return pts


def fill_ridge(d, pts, bottom, col, outline=None):
    poly = [(x * Q, y * Q) for x, y in pts] + [(pts[-1][0] * Q, bottom * Q), (pts[0][0] * Q, bottom * Q)]
    d.polygon(poly, fill=col)
    if outline:
        d.line([(x * Q, y * Q) for x, y in pts], fill=outline, width=2 * Q)


def tree_round(d, x, y, s, trunk, leaf, leaf2):
    d.rectangle([(x - 3 * s) * Q, (y - 14 * s) * Q, (x + 3 * s) * Q, y * Q], fill=trunk)
    for (ox, oy, r) in ((0, -26, 15), (-10, -18, 11), (10, -18, 11)):
        d.ellipse([(x + (ox - r) * s) * Q, (y + (oy - r) * s) * Q, (x + (ox + r) * s) * Q, (y + (oy + r) * s) * Q], fill=leaf)
    d.ellipse([(x - 9 * s) * Q, (y - 38 * s) * Q, (x + 2 * s) * Q, (y - 28 * s) * Q], fill=leaf2)


def tree_pine(d, x, y, s, trunk, leaf, leaf2, snow=None):
    d.rectangle([(x - 3 * s) * Q, (y - 10 * s) * Q, (x + 3 * s) * Q, y * Q], fill=trunk)
    for k in range(4):
        w = (22 - k * 4) * s
        yy = y - (8 + k * 15) * s
        d.polygon([((x - w) * Q, yy * Q), ((x + w) * Q, yy * Q), (x * Q, (yy - 24 * s) * Q)], fill=leaf if k % 2 == 0 else leaf2)
        if snow:
            d.polygon([((x - w * 0.55) * Q, (yy - 10 * s) * Q), ((x + w * 0.55) * Q, (yy - 10 * s) * Q), (x * Q, (yy - 24 * s) * Q)], fill=snow)


def band_grass(i, y0, y1):
    im, d = new_band("grass", y0, y1, BACK["grass"] if i == 3 else None)
    rnd = random.Random(10 + i)
    h = y1 - y0
    if i == 0:
        def sun(ox):
            for r, a in ((120, (255, 244, 190)), (84, (255, 238, 150)), (52, (255, 226, 90))):
                x, y = ox + 1500, 120
                d.ellipse([(x - r) * Q, (y - r) * Q, (x + r) * Q, (y + r) * Q], fill=a)
        wrap(sun)
        for _ in range(11):
            x, y, w = rnd.randint(0, PERIOD), rnd.randint(30, 280), rnd.randint(140, 300)
            wrap(lambda ox, x=x, y=y, w=w: cloud(d, x + ox, y, w, (255, 255, 255), (214, 232, 248)))
    elif i == 1:
        pts = ridge_pts(rnd, 110, 70, 160)
        fill_ridge(d, pts, h, (150, 178, 218))
        for (x, y) in pts[::6]:
            if y < 62:
                d.polygon([((x - 22) * Q, (y + 20) * Q), (x * Q, y * Q), ((x + 22) * Q, (y + 20) * Q)], fill=(238, 244, 252))
    elif i == 2:
        pts = ridge_pts(rnd, 50, 38, 120)
        fill_ridge(d, pts, h, (120, 196, 120), (80, 150, 90))
        for x in range(30, PERIOD, 70):
            if rnd.random() < 0.6:
                y = min(py for px, py in pts if abs(px - x) < 5) if any(abs(px - x) < 5 for px, py in pts) else 60
                wrap(lambda ox, x=x, y=y: tree_round(d, x + ox, y + 8, 0.9, (100, 80, 60), (70, 170, 90), (110, 205, 120)))
    else:
        pts = ridge_pts(rnd, 36, 24, 100)
        fill_ridge(d, pts, h, (72, 164, 72), (44, 110, 50))
        for x in range(20, PERIOD, 58):
            y = min([py for px, py in pts if abs(px - x) < 5] or [40])
            r = rnd.random()
            if r < 0.45:
                wrap(lambda ox, x=x, y=y: tree_round(d, x + ox, y + 10, 1.3, (110, 76, 52), (46, 140, 62), (84, 186, 90)))
            elif r < 0.75:
                wrap(lambda ox, x=x, y=y: tree_pine(d, x + ox, y + 10, 1.2, (110, 76, 52), (30, 112, 70), (44, 140, 84)))
        d.rectangle([0, 100 * Q, SW * Q, h * Q], fill=(80, 58, 44))
        for k in range(14):
            yy = 100 + k * 22
            d.line([(0, yy * Q), (SW * Q, yy * Q)], fill=(64, 46, 36), width=3 * Q)
        for _ in range(110):
            x, y = rnd.randint(0, SW), rnd.randint(104, h - 6)
            r = rnd.randint(3, 8)
            d.ellipse([(x - r) * Q, (y - r * .6) * Q, (x + r) * Q, (y + r * .6) * Q], fill=rnd.choice([(96, 72, 54), (68, 50, 38)]))
        d.rectangle([0, 96 * Q, SW * Q, 106 * Q], fill=(54, 120, 56))
    return im


def band_factory(i, y0, y1):
    im, d = new_band("factory", y0, y1, BACK["factory"] if i == 3 else None)
    rnd = random.Random(20 + i)
    h = y1 - y0
    if i == 0:
        def glow(ox):
            for r, a in ((260, (96, 62, 78)), (170, (130, 74, 70)), (90, (176, 96, 70))):
                x, y = ox + 800, 250
                d.ellipse([(x - r) * Q, (y - r * .5) * Q, (x + r) * Q, (y + r * .5) * Q], fill=a)
        wrap(glow)
        for _ in range(9):
            x, y, w = rnd.randint(0, PERIOD), rnd.randint(60, 300), rnd.randint(160, 320)
            wrap(lambda ox, x=x, y=y, w=w: cloud(d, x + ox, y, w, (64, 62, 78), (46, 44, 60)))
        for _ in range(60):
            x, y = rnd.randint(0, SW), rnd.randint(0, 200)
            d.rectangle([x * Q, y * Q, (x + 2) * Q, (y + 2) * Q], fill=(200, 200, 230))
    elif i == 1:
        base = (38, 40, 62)
        d.rectangle([0, 100 * Q, SW * Q, h * Q], fill=base)
        x = 0
        while x < SW + 200:
            w = rnd.randint(60, 150)
            top = rnd.randint(30, 100)
            d.rectangle([x * Q, top * Q, (x + w) * Q, h * Q], fill=base)
            if rnd.random() < 0.5:
                d.rectangle([(x + w * .3) * Q, (top - 30) * Q, (x + w * .3 + 16) * Q, top * Q], fill=base)
            for wx in range(x + 8, x + w - 10, 16):
                for wy in range(top + 10, h - 12, 18):
                    if rnd.random() < 0.18:
                        d.rectangle([wx * Q, wy * Q, (wx + 6) * Q, (wy + 8) * Q], fill=(230, 190, 80))
            x += w
    elif i == 2:
        d.rectangle([0, 0, SW * Q, h * Q], fill=(58, 60, 82))
        for yy in (20, 70, 110):
            d.rectangle([0, yy * Q, SW * Q, (yy + 12) * Q], fill=(80, 84, 108))
            d.rectangle([0, (yy + 2) * Q, SW * Q, (yy + 4) * Q], fill=(110, 116, 140))
        for x in range(0, PERIOD, 260):
            d.rectangle([x * Q, 0, (x + 22) * Q, h * Q], fill=(70, 74, 98))
            d.rectangle([(x + 3) * Q, 0, (x + 7) * Q, h * Q], fill=(100, 106, 132))
            wrap(lambda ox, x=x: d.rectangle([(x + ox) * Q, 0, (x + ox + 22) * Q, h * Q], fill=(70, 74, 98)))
        for x in range(60, PERIOD, 520):
            wrap(lambda ox, x=x: _gear(d, x + ox + 100, 60, 52, 12, (86, 90, 118)))
    else:
        d.rectangle([0, 0, SW * Q, h * Q], fill=(30, 34, 48))
        for x in range(0, SW, 80):
            d.line([(x * Q, 0), (x * Q, h * Q)], fill=(40, 46, 62), width=2 * Q)
        d.rectangle([0, 20 * Q, SW * Q, 34 * Q], fill=(54, 60, 80))
        for x in range(0, PERIOD, 160):
            wrap(lambda ox, x=x: _lamp(d, x + ox + 40, 34))
        d.rectangle([0, 96 * Q, SW * Q, 112 * Q], fill=(60, 66, 86))
        for x in range(-40, SW, 36):
            d.polygon([(x * Q, 112 * Q), ((x + 18) * Q, 112 * Q), ((x + 36) * Q, 96 * Q), ((x + 18) * Q, 96 * Q)], fill=(220, 176, 40))
        for yy in range(130, h, 40):
            d.line([(0, yy * Q), (SW * Q, yy * Q)], fill=(38, 42, 58), width=3 * Q)
        for x in range(30, SW, 120):
            d.rectangle([x * Q, 112 * Q, (x + 14) * Q, h * Q], fill=(46, 52, 70))
    return im


def _gear(d, cx, cy, r, teeth, col):
    pts = []
    for i in range(teeth * 4):
        a = i / (teeth * 4) * 2 * math.pi
        rr = r if i % 4 in (1, 2) else r * 0.82
        pts.append(((cx + math.cos(a) * rr) * Q, (cy + math.sin(a) * rr) * Q))
    d.polygon(pts, fill=col)
    d.ellipse([(cx - r * .55) * Q, (cy - r * .55) * Q, (cx + r * .55) * Q, (cy + r * .55) * Q], fill=shade(col, .75))
    d.ellipse([(cx - r * .2) * Q, (cy - r * .2) * Q, (cx + r * .2) * Q, (cy + r * .2) * Q], fill=shade(col, 1.2))


def _lamp(d, x, y):
    d.rectangle([(x - 2) * Q, y * Q, (x + 2) * Q, (y + 12) * Q], fill=(20, 22, 30))
    d.polygon([((x - 12) * Q, (y + 26) * Q), ((x + 12) * Q, (y + 26) * Q), ((x + 7) * Q, (y + 12) * Q), ((x - 7) * Q, (y + 12) * Q)], fill=(250, 220, 120))
    d.ellipse([(x - 6) * Q, (y + 20) * Q, (x + 6) * Q, (y + 30) * Q], fill=(255, 245, 190))


def band_lava(i, y0, y1):
    im, d = new_band("lava", y0, y1, BACK["lava"] if i == 3 else None)
    rnd = random.Random(30 + i)
    h = y1 - y0
    if i == 0:
        def moon(ox):
            for r, a in ((130, (150, 50, 50)), (90, (196, 70, 50)), (56, (250, 150, 70))):
                x, y = ox + 1700, 150
                d.ellipse([(x - r) * Q, (y - r) * Q, (x + r) * Q, (y + r) * Q], fill=a)
        wrap(moon)
        for _ in range(10):
            x, y, w = rnd.randint(0, PERIOD), rnd.randint(40, 300), rnd.randint(160, 320)
            wrap(lambda ox, x=x, y=y, w=w: cloud(d, x + ox, y, w, (86, 40, 56), (60, 26, 44)))
        for _ in range(70):
            x, y = rnd.randint(0, SW), rnd.randint(0, 380)
            d.rectangle([x * Q, y * Q, (x + 3) * Q, (y + 3) * Q], fill=rnd.choice([(255, 150, 60), (255, 90, 40)]))
    elif i == 1:
        for vx in (500, 1700):
            def volcano(ox, vx=vx):
                d.polygon([((vx + ox - 260) * Q, h * Q), ((vx + ox - 40) * Q, 30 * Q), ((vx + ox + 40) * Q, 30 * Q), ((vx + ox + 260) * Q, h * Q)], fill=(54, 30, 44))
                d.polygon([((vx + ox - 40) * Q, 30 * Q), ((vx + ox + 40) * Q, 30 * Q), ((vx + ox + 20) * Q, 38 * Q), ((vx + ox - 20) * Q, 38 * Q)], fill=(255, 130, 40))
                d.line([((vx + ox - 10) * Q, 36 * Q), ((vx + ox - 40) * Q, 110 * Q), ((vx + ox - 20) * Q, h * Q)], fill=(255, 120, 40), width=5 * Q)
                d.line([((vx + ox + 12) * Q, 36 * Q), ((vx + ox + 50) * Q, 90 * Q)], fill=(255, 150, 50), width=4 * Q)
            wrap(volcano)
        pts = ridge_pts(rnd, 120, 36, 130)
        fill_ridge(d, pts, h, (70, 36, 48))
    elif i == 2:
        pts = ridge_pts(rnd, 66, 40, 70)
        fill_ridge(d, pts, h, (62, 34, 44), (130, 60, 50))
        for (x, y) in pts[::5]:
            d.polygon([((x - 8) * Q, (y + 30) * Q), (x * Q, y * Q), ((x + 8) * Q, (y + 30) * Q)], fill=(78, 44, 54))
    else:
        pts = ridge_pts(rnd, 36, 20, 90)
        fill_ridge(d, pts, h, (38, 22, 30), (110, 46, 36))
        d.rectangle([0, 100 * Q, SW * Q, h * Q], fill=(34, 20, 26))
        for _ in range(16):
            x = rnd.randint(0, SW)
            y = rnd.randint(100, h - 60)
            ptsv = [(x, y)]
            for _k in range(4):
                x += rnd.randint(-24, 24)
                y += rnd.randint(14, 36)
                ptsv.append((x, y))
            d.line([(a * Q, b * Q) for a, b in ptsv], fill=(255, 110, 30), width=3 * Q)
            d.line([(a * Q, b * Q) for a, b in ptsv], fill=(255, 210, 90), width=1 * Q)
    return im


def band_ice(i, y0, y1):
    im, d = new_band("ice", y0, y1, BACK["ice"] if i == 3 else None)
    rnd = random.Random(40 + i)
    h = y1 - y0
    if i == 0:
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for (c, yy) in (((80, 230, 170, 90), 110), ((160, 120, 240, 80), 170), ((90, 200, 240, 70), 60)):
            for x in range(0, SW, 8):
                yv = yy + 36 * math.sin(x / PERIOD * 2 * math.pi * 2 + yy) + 14 * math.sin(x / 90 + yy)
                od.rectangle([x * Q, (yv - 50) * Q, (x + 8) * Q, (yv + 50) * Q], fill=c)
        im.paste(ov, (0, 0), ov)
        d = ImageDraw.Draw(im)
        for _ in range(40):
            x, y = rnd.randint(0, SW), rnd.randint(0, 300)
            d.rectangle([x * Q, y * Q, (x + 3) * Q, (y + 3) * Q], fill=(255, 255, 255))
        for _ in range(7):
            x, y, w = rnd.randint(0, PERIOD), rnd.randint(200, 340), rnd.randint(140, 260)
            wrap(lambda ox, x=x, y=y, w=w: cloud(d, x + ox, y, w, (250, 252, 255), (206, 226, 246)))
    elif i == 1:
        pts = ridge_pts(rnd, 100, 80, 150)
        fill_ridge(d, pts, h, (196, 222, 244))
        for (x, y) in pts[::6]:
            d.polygon([((x - 30) * Q, (y + 36) * Q), (x * Q, y * Q), ((x + 30) * Q, (y + 36) * Q)], fill=(250, 252, 255))
            d.polygon([(x * Q, y * Q), ((x + 30) * Q, (y + 36) * Q), ((x + 6) * Q, (y + 36) * Q)], fill=(170, 200, 232))
    elif i == 2:
        pts = ridge_pts(rnd, 54, 28, 110)
        fill_ridge(d, pts, h, (170, 208, 236), (120, 170, 214))
        for x in range(30, PERIOD, 64):
            y = min([py for px, py in pts if abs(px - x) < 5] or [50])
            wrap(lambda ox, x=x, y=y: tree_pine(d, x + ox, y + 10, 0.95, (120, 130, 150), (96, 150, 170), (120, 176, 196), (250, 252, 255)))
    else:
        pts = ridge_pts(rnd, 36, 18, 90)
        fill_ridge(d, pts, h, (120, 176, 220), (70, 120, 180))
        for x in range(20, PERIOD, 96):
            y = min([py for px, py in pts if abs(px - x) < 5] or [40])
            wrap(lambda ox, x=x, y=y: tree_pine(d, x + ox, y + 10, 1.35, (110, 120, 150), (70, 130, 150), (96, 160, 176), (250, 252, 255)))
        d.rectangle([0, 100 * Q, SW * Q, h * Q], fill=(70, 120, 180))
        for x in range(0, SW, 26):
            ln = rnd.randint(14, 56)
            d.polygon([(x * Q, 100 * Q), ((x + 22) * Q, 100 * Q), ((x + 11) * Q, (100 + ln) * Q)], fill=(200, 236, 255))
        for _ in range(60):
            x, y = rnd.randint(0, SW), rnd.randint(130, h - 6)
            r = rnd.randint(4, 14)
            d.polygon([(x * Q, (y - r) * Q), ((x + r * .6) * Q, y * Q), (x * Q, (y + r) * Q), ((x - r * .6) * Q, y * Q)], fill=rnd.choice([(96, 150, 206), (150, 206, 240)]))
    return im


MAKERS = {"grass": band_grass, "factory": band_factory, "lava": band_lava, "ice": band_ice}


def build_bg(world):
    out = []
    for i, (y0, y1, f) in enumerate(BANDS[world]):
        im = MAKERS[world](i, y0, y1).resize((SW, y1 - y0), Image.LANCZOS)
        # the last screen of the strip repeats its first one, so scrolling past PERIOD is seamless
        im.paste(im.crop((0, 0, SW - PERIOD, y1 - y0)), (PERIOD, 0))
        if i == 1:
            # distant ridges dissolve into the horizon haze instead of ending in a hard cut
            d = ImageDraw.Draw(im)
            for y in range(y1 - y0):
                k = (y - (y1 - y0 - 70)) / 70
                if k > 0:
                    px = im.load()
                    sky = sky_at(world, y0 + y)
                    for x in range(0, SW):
                        px[x, y] = mix(px[x, y], sky, k)
        out.append({"y0": y0, "y1": y1, "f": f, "rows": rows_of(im)})
    return out
