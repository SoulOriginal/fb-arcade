# Build-time vector art for the temple runner: trees, ruins, obstacles, pickups, the explorer and the apes.
# Everything is drawn at PPM pixels per metre on a transparent canvas; the builder then shrinks it to every
# distance bucket, so one drawing serves all sizes.
import math
import random
from PIL import Image, ImageDraw, ImageFilter

PPM = 48


def canvas(wm, hm, ppm=PPM):
    im = Image.new("RGBA", (int(wm * ppm), int(hm * ppm)), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im, "RGBA")


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3]) + tuple(c[3:])


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def blob(d, cx, cy, rx, ry, col):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col)


# ---- scenery -----------------------------------------------------------------------------------------------
def foliage(d, rnd, cx, cy, rx, ry, pal, n):
    # three passes (shadow, body, highlight) give the clumped canopy look without any shading maths
    pts = []
    for _ in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        r = math.sqrt(rnd.random())
        pts.append((cx + math.cos(a) * rx * r, cy + math.sin(a) * ry * r, rnd.uniform(0.16, 0.3)))
    for x, y, s in pts:
        blob(d, x, y + 5, s * rx, s * ry * 1.05, pal["leaf_d"])
    for x, y, s in pts:
        blob(d, x - 2, y - 1, s * rx * 0.9, s * ry * 0.9, pal["leaf_m"])
    for x, y, s in pts:
        if y < cy + ry * 0.1:
            blob(d, x - s * rx * 0.25, y - s * ry * 0.3, s * rx * 0.5, s * ry * 0.4, pal["leaf_l"])


def vine(d, rnd, x, y0, length, pal, ppm=PPM):
    pts = []
    for i in range(0, int(length) + 1, 3):
        pts.append((x + math.sin(i * 0.09 + x) * 0.07 * ppm, y0 + i))
    if len(pts) > 1:
        d.line(pts, fill=pal["vine"], width=max(2, int(0.06 * ppm)))
    for i, (px, py) in enumerate(pts):
        if i % 3 == 1:
            blob(d, px + rnd.uniform(-3, 3), py, 0.1 * ppm, 0.07 * ppm, pal["leaf_m"])


def tree_big(pal, rnd, wm=4.2, hm=10.5):
    im, d = canvas(wm, hm)
    W, H = im.size
    cx = W // 2
    tw = 0.34 * PPM
    base = [(cx - 0.9 * PPM, H), (cx - tw * 1.4, H - 1.4 * PPM), (cx - tw, H - 4.0 * PPM), (cx - tw * 0.8, H * 0.35),
            (cx + tw * 0.8, H * 0.35), (cx + tw, H - 4.0 * PPM), (cx + tw * 1.4, H - 1.4 * PPM), (cx + 0.9 * PPM, H)]
    d.polygon(base, fill=pal["bark"])
    d.polygon([(cx + tw * 0.2, H), (cx + tw * 0.4, H - 4 * PPM), (cx + tw * 0.8, H * 0.35), (cx + tw * 1.0, H * 0.35),
               (cx + tw, H - 4.0 * PPM), (cx + tw * 1.4, H - 1.4 * PPM), (cx + 0.9 * PPM, H)], fill=pal["bark_d"])
    for _ in range(9):
        x = cx + rnd.uniform(-tw, tw)
        d.line([(x, H), (x + rnd.uniform(-4, 4), H - rnd.uniform(2, 6) * PPM)], fill=shade(pal["bark_d"], 0.8), width=2)
    for k in range(3):
        y = H - rnd.uniform(0.8, 3.0) * PPM
        d.ellipse([cx - tw * 1.6, y, cx - tw * 0.2, y + 0.2 * PPM], fill=pal["moss"])
    foliage(d, rnd, cx, H * 0.28, W * 0.46, H * 0.24, pal, 34)
    for _ in range(3):
        vine(d, rnd, cx + rnd.uniform(-1.5, 1.5) * PPM, H * 0.38, rnd.uniform(2, 4) * PPM, pal)
    return im, wm, hm


def tree_palm(pal, rnd, wm=4.0, hm=8.5):
    im, d = canvas(wm, hm)
    W, H = im.size
    cx = W // 2
    lean = rnd.uniform(-0.3, 0.3) * PPM
    pts = [(cx, H), (cx + lean * 0.4, H * 0.6), (cx + lean, H * 0.22)]
    d.line(pts, fill=pal["bark"], width=int(0.34 * PPM))
    d.line([(x + 3, y) for x, y in pts], fill=pal["bark_d"], width=int(0.12 * PPM))
    top = pts[-1]
    for i in range(9):
        a = math.pi * (0.04 + 0.92 * i / 8) + math.pi
        ln = rnd.uniform(1.4, 2.0) * PPM
        ex, ey = top[0] + math.cos(a) * ln, top[1] + math.sin(a) * ln * 0.55 + ln * 0.35
        mx, my = top[0] + math.cos(a) * ln * 0.5, top[1] + math.sin(a) * ln * 0.5 - 0.2 * PPM
        d.line([top, (mx, my), (ex, ey)], fill=pal["leaf_d"], width=int(0.34 * PPM))
        d.line([top, (mx, my - 2), (ex, ey - 3)], fill=pal["leaf_m"], width=int(0.2 * PPM))
    blob(d, top[0], top[1] + 2, 0.22 * PPM, 0.2 * PPM, pal["bark_d"])
    return im, wm, hm


def bush(pal, rnd, wm=2.6, hm=1.7):
    im, d = canvas(wm, hm)
    W, H = im.size
    foliage(d, rnd, W // 2, H * 0.62, W * 0.46, H * 0.42, pal, 16)
    for _ in range(5):
        x = rnd.uniform(0.2, 0.8) * W
        d.line([(x, H), (x + rnd.uniform(-8, 8), H * rnd.uniform(0.1, 0.4))], fill=pal["leaf_l"], width=3)
    return im, wm, hm


def fern(pal, rnd, wm=2.0, hm=1.4):
    im, d = canvas(wm, hm)
    W, H = im.size
    for i in range(9):
        a = math.pi * (0.1 + 0.8 * i / 8)
        ln = rnd.uniform(0.7, 1.2) * H
        ex, ey = W / 2 - math.cos(a) * ln * 0.8, H - math.sin(a) * ln
        d.line([(W / 2, H), (ex, ey)], fill=pal["leaf_m"], width=4)
        d.line([(W / 2, H - 2), ((W / 2 + ex) / 2, (H + ey) / 2 - 3)], fill=pal["leaf_l"], width=2)
    return im, wm, hm


def dead_tree(pal, rnd, wm=3.6, hm=8.0):
    im, d = canvas(wm, hm)
    W, H = im.size
    cx = W // 2

    def branch(x, y, ang, ln, wd, depth):
        ex, ey = x + math.sin(ang) * ln, y - math.cos(ang) * ln
        d.line([(x, y), (ex, ey)], fill=pal["bark"], width=max(2, int(wd)))
        if depth:
            branch(ex, ey, ang - rnd.uniform(0.3, 0.7), ln * 0.7, wd * 0.65, depth - 1)
            branch(ex, ey, ang + rnd.uniform(0.3, 0.7), ln * 0.7, wd * 0.65, depth - 1)
        else:
            blob(d, ex, ey, 0.4 * PPM, 0.3 * PPM, pal["leaf_d"])
    branch(cx, H, 0.0, 3.4 * PPM, 0.4 * PPM, 4)
    for _ in range(3):
        vine(d, rnd, rnd.uniform(0.3, 0.7) * W, H * 0.25, rnd.uniform(2, 3.5) * PPM, pal)
    return im, wm, hm


def stone_block(d, x0, y0, x1, y1, pal, rnd, moss=True):
    d.rectangle([x0, y0, x1, y1], fill=pal["stone"])
    d.rectangle([x0, y0, x0 + (x1 - x0) * 0.22, y1], fill=shade(pal["stone"], 1.12))
    d.rectangle([x1 - (x1 - x0) * 0.2, y0, x1, y1], fill=pal["stone_d"])
    d.line([(x0, y1), (x1, y1)], fill=shade(pal["stone_d"], 0.7), width=2)
    if moss:
        for _ in range(3):
            mx = rnd.uniform(x0, x1)
            blob(d, mx, y0 + 2, rnd.uniform(0.1, 0.25) * PPM, 0.1 * PPM, pal["moss"])


def pillar(pal, rnd, wm=1.8, hm=5.5):
    im, d = canvas(wm, hm)
    W, H = im.size
    stone_block(d, W * 0.2, H * 0.08, W * 0.8, H, pal, rnd)
    for i in range(1, 6):
        y = H * (0.08 + i * 0.15)
        d.line([(W * 0.2, y), (W * 0.8, y)], fill=pal["stone_d"], width=2)
    stone_block(d, W * 0.1, 0.0, W * 0.9, H * 0.12, pal, rnd)
    d.polygon([(W * 0.1, H * 0.12), (W * 0.9, H * 0.12), (W * 0.82, H * 0.17), (W * 0.18, H * 0.17)], fill=pal["stone_d"])
    for _ in range(3):
        vine(d, rnd, rnd.uniform(0.25, 0.75) * W, H * 0.1, rnd.uniform(1.5, 3.5) * PPM, pal)
    return im, wm, hm


def pillar_broken(pal, rnd, wm=1.8, hm=3.0):
    im, d = canvas(wm, hm)
    W, H = im.size
    pts = [(W * 0.2, H), (W * 0.2, H * 0.4), (W * 0.35, H * 0.25), (W * 0.5, H * 0.38), (W * 0.65, H * 0.18),
           (W * 0.8, H * 0.42), (W * 0.8, H)]
    d.polygon(pts, fill=pal["stone"])
    d.polygon([(W * 0.62, H * 0.2), (W * 0.8, H * 0.42), (W * 0.8, H), (W * 0.6, H)], fill=pal["stone_d"])
    for i in range(1, 4):
        d.line([(W * 0.2, H * (0.45 + i * 0.15)), (W * 0.8, H * (0.45 + i * 0.15))], fill=pal["stone_d"], width=2)
    for _ in range(4):
        blob(d, rnd.uniform(0.2, 0.8) * W, H * rnd.uniform(0.3, 0.95), 0.12 * PPM, 0.08 * PPM, pal["moss"])
    return im, wm, hm


def statue(pal, rnd, wm=2.4, hm=4.2):
    # an idol head on a plinth; the eyes glow in the dark zones
    im, d = canvas(wm, hm)
    W, H = im.size
    stone_block(d, W * 0.12, H * 0.72, W * 0.88, H, pal, rnd)
    stone_block(d, W * 0.2, H * 0.1, W * 0.8, H * 0.74, pal, rnd, moss=False)
    d.rectangle([W * 0.12, H * 0.06, W * 0.88, H * 0.14], fill=pal["stone_d"])
    for ex in (0.36, 0.64):
        d.rectangle([W * ex - 8, H * 0.3, W * ex + 8, H * 0.38], fill=pal["glow"])
    d.polygon([(W * 0.44, H * 0.4), (W * 0.56, H * 0.4), (W * 0.52, H * 0.52), (W * 0.48, H * 0.52)], fill=pal["stone_d"])
    d.rectangle([W * 0.34, H * 0.58, W * 0.66, H * 0.64], fill=pal["stone_d"])
    for k in range(5):
        d.rectangle([W * (0.36 + 0.06 * k), H * 0.58, W * (0.38 + 0.06 * k), H * 0.64], fill=shade(pal["stone"], 1.2))
    blob(d, W * 0.3, H * 0.12, 0.16 * PPM, 0.1 * PPM, pal["moss"])
    return im, wm, hm


def arch_ruin(pal, rnd, wm=5.0, hm=5.0):
    im, d = canvas(wm, hm)
    W, H = im.size
    stone_block(d, W * 0.04, H * 0.3, W * 0.22, H, pal, rnd)
    stone_block(d, W * 0.78, H * 0.55, W * 0.96, H, pal, rnd)
    d.pieslice([W * 0.04, H * 0.04, W * 0.96, H * 0.9], 180, 262, fill=pal["stone"])
    d.pieslice([W * 0.2, H * 0.2, W * 0.8, H * 0.9], 180, 262, fill=(0, 0, 0, 0))
    for _ in range(5):
        blob(d, rnd.uniform(0.1, 0.5) * W, H * rnd.uniform(0.1, 0.4), 0.12 * PPM, 0.08 * PPM, pal["moss"])
    for _ in range(3):
        vine(d, rnd, rnd.uniform(0.2, 0.6) * W, H * 0.12, rnd.uniform(1.5, 3) * PPM, pal)
    return im, wm, hm


def post(pal, rnd, wm=0.8, hm=1.3, lit=False):
    # low edge post of the path; the night zone puts a lantern on top
    im, d = canvas(wm, hm)
    W, H = im.size
    stone_block(d, W * 0.2, H * 0.32, W * 0.8, H, pal, rnd)
    stone_block(d, W * 0.1, H * 0.2, W * 0.9, H * 0.36, pal, rnd)
    if lit:
        blob(d, W * 0.5, H * 0.1, 0.2 * PPM, 0.26 * PPM, (255, 190, 80, 90))
        blob(d, W * 0.5, H * 0.1, 0.1 * PPM, 0.15 * PPM, (255, 220, 120, 255))
    else:
        blob(d, W * 0.3, H * 0.22, 0.14 * PPM, 0.08 * PPM, pal["moss"])
    return im, wm, hm


def hedge_wall(pal, rnd, wm=4.6, hm=3.6):
    # the dead end of a path: a carved temple wall with jungle spilling over its top
    im, d = canvas(wm, hm)
    W, H = im.size
    d.rectangle([W * 0.02, H * 0.42, W * 0.98, H], fill=pal["stone"])
    for r in range(7):
        y = H * (0.42 + r * 0.083)
        d.line([(W * 0.02, y), (W * 0.98, y)], fill=pal["stone_d"], width=2)
        off = 0.06 if r % 2 else 0.0
        for c in range(9):
            x = W * (0.02 + off + c * 0.13)
            d.line([(x, y), (x, y + H * 0.083)], fill=pal["stone_d"], width=2)
    d.rectangle([W * 0.3, H * 0.5, W * 0.7, H * 0.78], fill=pal["stone_d"])
    for ex in (0.4, 0.6):
        d.ellipse([W * ex - 14, H * 0.58 - 14, W * ex + 14, H * 0.58 + 14], fill=(30, 22, 16, 255))
        d.ellipse([W * ex - 6, H * 0.58 - 6, W * ex + 6, H * 0.58 + 6], fill=pal["glow"])
    d.rectangle([W * 0.45, H * 0.62, W * 0.55, H * 0.7], fill=shade(pal["stone"], 0.8))
    d.rectangle([W * 0.38, H * 0.72, W * 0.62, H * 0.76], fill=(30, 22, 16, 255))
    foliage(d, rnd, W // 2, H * 0.28, W * 0.5, H * 0.26, pal, 40)
    for _ in range(8):
        vine(d, rnd, rnd.uniform(0.05, 0.95) * W, H * 0.4, rnd.uniform(0.5, 1.4) * PPM, pal)
    return im, wm, hm


def root_small(pal, rnd, wm=1.1, hm=0.75):
    im, d = canvas(wm, hm)
    W, H = im.size
    for k in range(2):
        x0 = W * (0.04 + 0.46 * k)
        pts = [(x0, H), (x0 + W * 0.08, H * 0.4), (x0 + W * 0.22, H * 0.12), (x0 + W * 0.4, H * 0.4), (x0 + W * 0.44, H)]
        d.line(pts, fill=pal["bark"], width=int(0.2 * PPM), joint="curve")
        d.line([(x - 3, y - 3) for x, y in pts], fill=shade(pal["bark"], 1.3), width=int(0.06 * PPM), joint="curve")
    for _ in range(3):
        blob(d, rnd.uniform(0.15, 0.85) * W, H * rnd.uniform(0.1, 0.3), 0.1 * PPM, 0.06 * PPM, pal["moss"])
    return im, wm, hm


def root_big(pal, rnd, wm=2.3, hm=1.5):
    im, d = canvas(wm, hm)
    W, H = im.size
    for k in range(3):
        x0 = W * (0.0 + 0.34 * k)
        pts = [(x0, H), (x0 + W * 0.05, H * 0.35), (x0 + W * 0.16, H * 0.1 + (k % 2) * 6), (x0 + W * 0.28, H * 0.35),
               (x0 + W * 0.32, H)]
        d.line(pts, fill=pal["bark"], width=int(0.34 * PPM), joint="curve")
        d.line([(x - 4, y - 4) for x, y in pts], fill=shade(pal["bark"], 1.3), width=int(0.1 * PPM), joint="curve")
        d.line([(x + 6, y) for x, y in pts], fill=pal["bark_d"], width=int(0.09 * PPM), joint="curve")
    for _ in range(6):
        blob(d, rnd.uniform(0.05, 0.95) * W, H * rnd.uniform(0.12, 0.4), 0.12 * PPM, 0.07 * PPM, pal["moss"])
    return im, wm, hm


def overhang(pal, rnd, wm=3.4, hm=3.3):
    # a fallen trunk wedged between two pillars with a curtain of vines below it: slide under it, never jump
    im, d = canvas(wm, hm)
    W, H = im.size
    for x0 in (0.0, 0.88):
        stone_block(d, W * x0, 0, W * (x0 + 0.12), H, pal, rnd)
        for k in range(6):
            d.line([(W * x0, H * k / 6), (W * (x0 + 0.12), H * k / 6)], fill=pal["stone_d"], width=2)
    y0, y1 = H * 0.04, H * 0.38
    d.rectangle([W * 0.1, y0, W * 0.9, y1], fill=pal["bark"])
    d.rectangle([W * 0.1, y1 - 0.1 * PPM, W * 0.9, y1], fill=pal["bark_d"])
    d.rectangle([W * 0.1, y0, W * 0.9, y0 + 0.07 * PPM], fill=shade(pal["bark"], 1.3))
    for _ in range(26):
        vine(d, rnd, rnd.uniform(0.12, 0.88) * W, y1 - 4, rnd.uniform(0.5, 1.5) * PPM, pal)
    return im, wm, hm


def gate(pal, rnd, wm=3.4, hm=1.8):
    # low carved stone beam on two blocks: slide under it or hop over
    im, d = canvas(wm, hm)
    W, H = im.size
    for x0 in (0.0, 0.86):
        stone_block(d, W * x0, H * 0.1, W * (x0 + 0.14), H, pal, rnd)
        stone_block(d, W * (x0 - 0.01), 0, W * (x0 + 0.15), H * 0.16, pal, rnd)
    stone_block(d, W * 0.12, H * 0.3, W * 0.88, H * 0.62, pal, rnd)
    for k in range(6):
        d.line([(W * (0.12 + k * 0.127), H * 0.3), (W * (0.12 + k * 0.127), H * 0.62)], fill=pal["stone_d"], width=2)
    for ex in (0.34, 0.5, 0.66):
        d.rectangle([W * ex - 4, H * 0.4, W * ex + 4, H * 0.52], fill=pal["stone_d"])
    for _ in range(4):
        vine(d, rnd, rnd.uniform(0.15, 0.85) * W, H * 0.62, rnd.uniform(0.15, 0.4) * PPM, pal)
    return im, wm, hm


def fire(pal, rnd, wm=1.1, hm=1.6, frame=0):
    im, d = canvas(wm, hm)
    W, H = im.size
    stone_block(d, W * 0.1, H * 0.78, W * 0.9, H, pal, rnd, moss=False)
    d.rectangle([W * 0.3, H * 0.7, W * 0.7, H * 0.8], fill=pal["stone_d"])
    for k, (x, hh) in enumerate(((0.3, 0.6), (0.5, 0.78), (0.7, 0.56))):
        hh = hh * (0.9 + 0.12 * math.sin(frame * 2.1 + k * 1.7))
        for col, sc in (((230, 60, 10, 255), 1.0), ((255, 150, 20, 255), 0.72), ((255, 240, 150, 255), 0.4)):
            bw = W * 0.14 * (0.5 + sc * 0.5)
            cx = W * x + math.sin(frame * 1.9 + k) * 3
            top = H * (0.74 - hh * sc)
            d.polygon([(cx - bw, H * 0.76), (cx - bw * 0.6, H * 0.76 - (H * 0.76 - top) * 0.55), (cx + math.sin(frame + k) * 4, top),
                       (cx + bw * 0.6, H * 0.76 - (H * 0.76 - top) * 0.55), (cx + bw, H * 0.76)], fill=col)
    return im, wm, hm


def coin(pal, rnd, wm=0.62, hm=0.62, frame=0):
    ppm = 160
    im, d = canvas(wm, hm, ppm)
    W, H = im.size
    k = (1.0, 0.72, 0.28, 0.72)[frame % 4]
    rx = W / 2 * k - 1
    cx, cy = W / 2, H / 2
    d.ellipse([cx - rx - 2, cy - H / 2 + 2, cx + rx + 2, cy + H / 2 - 2], fill=(196, 128, 8, 255))
    d.ellipse([cx - rx, cy - H / 2 + 5, cx + rx, cy + H / 2 - 5], fill=(255, 208, 44, 255))
    if k > 0.5:
        d.ellipse([cx - rx * 0.65, cy - H * 0.33, cx + rx * 0.65, cy + H * 0.33], outline=(214, 150, 20, 255), width=3)
        d.rectangle([cx - 4, cy - H * 0.22, cx + 4, cy + H * 0.22], fill=(214, 150, 20, 255))
        d.ellipse([cx - rx * 0.7, cy - H * 0.38, cx - rx * 0.2, cy - H * 0.14], fill=(255, 248, 190, 255))
    return im, wm, hm


def token(pal, rnd, kind, wm=0.8, hm=0.8):
    ppm = 120
    im, d = canvas(wm, hm, ppm)
    W, H = im.size
    glow = {"magnet": (255, 90, 90), "boost": (255, 230, 80), "shield": (90, 190, 255), "mega": (255, 200, 40)}[kind]
    g = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([2, 2, W - 2, H - 2], fill=glow + (120,))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(im, "RGBA")
    d.ellipse([W * 0.14, H * 0.14, W * 0.86, H * 0.86], fill=(30, 36, 70, 255), outline=glow + (255,), width=5)
    c = W / 2
    if kind == "magnet":
        d.arc([W * 0.3, H * 0.28, W * 0.7, H * 0.78], 180, 360, fill=(220, 40, 50, 255), width=int(W * 0.13))
        d.rectangle([W * 0.3, H * 0.52, W * 0.43, H * 0.7], fill=(220, 40, 50, 255))
        d.rectangle([W * 0.57, H * 0.52, W * 0.7, H * 0.7], fill=(220, 40, 50, 255))
        d.rectangle([W * 0.3, H * 0.64, W * 0.43, H * 0.7], fill=(235, 235, 245, 255))
        d.rectangle([W * 0.57, H * 0.64, W * 0.7, H * 0.7], fill=(235, 235, 245, 255))
    elif kind == "boost":
        d.polygon([(c + W * 0.06, H * 0.22), (c - W * 0.18, H * 0.54), (c - W * 0.02, H * 0.54), (c - W * 0.1, H * 0.8),
                   (c + W * 0.2, H * 0.44), (c + W * 0.03, H * 0.44)], fill=(255, 235, 70, 255))
    elif kind == "shield":
        d.polygon([(c - W * 0.2, H * 0.3), (c + W * 0.2, H * 0.3), (c + W * 0.2, H * 0.55), (c, H * 0.78), (c - W * 0.2, H * 0.55)],
                  fill=(110, 200, 255, 255), outline=(235, 250, 255, 255))
        d.polygon([(c, H * 0.3), (c + W * 0.2, H * 0.3), (c + W * 0.2, H * 0.55), (c, H * 0.78)], fill=(60, 140, 230, 255))
    else:
        d.ellipse([W * 0.24, H * 0.24, W * 0.76, H * 0.76], fill=(255, 208, 44, 255), outline=(190, 120, 10, 255), width=4)
        d.polygon([(c, H * 0.32), (c + W * 0.06, H * 0.46), (c + W * 0.2, H * 0.46), (c + W * 0.09, H * 0.55),
                   (c + W * 0.13, H * 0.7), (c, H * 0.61), (c - W * 0.13, H * 0.7), (c - W * 0.09, H * 0.55),
                   (c - W * 0.2, H * 0.46), (c - W * 0.06, H * 0.46)], fill=(190, 120, 10, 255))
    return im, wm, hm


SHIRT, SHIRT_D = (238, 228, 200), (196, 182, 150)
TROUSER, TROUSER_D = (116, 80, 46), (88, 60, 34)
BOOT, BOOT_L, SKIN = (56, 38, 26), (134, 104, 76), (226, 176, 134)
HAIR, STRAP, SATCHEL = (110, 74, 40), (116, 74, 34), (150, 98, 48)


def limb(d, a, b, w, col):
    d.line([a, b], fill=col, width=w)
    r = w / 2
    d.ellipse([a[0] - r, a[1] - r, a[0] + r, a[1] + r], fill=col)
    d.ellipse([b[0] - r, b[1] - r, b[0] + r, b[1] + r], fill=col)


def explorer(pose, ppm=96):
    # seen from behind: cream shirt with rolled sleeves, a satchel strap across the back, brown trousers and boots.
    # pose: joint targets in metres (x right, y up from the feet).
    wm, hm = 2.4, 2.2
    im, d = canvas(wm, hm, ppm)
    W, H = im.size

    def P(x, y):
        return (W / 2 + x * ppm, H - 0.12 * ppm - y * ppm)

    hip_y, sh_y = pose.get("hip", 0.95), pose.get("sh", 1.5)
    hd_y = pose.get("head", sh_y + 0.2)
    tilt = pose.get("tilt", 0.0)
    shx = tilt * (sh_y - hip_y)
    for side in (-1, 1):
        i = 0 if side < 0 else 1
        foot, knee = pose["foot"][i], pose["knee"][i]
        hp = (side * 0.12, hip_y)
        limb(d, P(*hp), P(*knee), int(0.2 * ppm), TROUSER)
        limb(d, P(*knee), P(*foot), int(0.18 * ppm), TROUSER_D)
        fx, fy = foot
        sole = pose.get("sole", (0, 0))[i]
        d.rounded_rectangle([P(fx - 0.1, fy + 0.2)[0], P(fx, fy + 0.2)[1], P(fx + 0.1, fy - 0.07)[0], P(fx, fy - 0.07)[1]],
                            radius=int(0.04 * ppm), fill=BOOT_L if sole else BOOT)
    arms = pose["arm"]

    def arm(side):
        i = 0 if side < 0 else 1
        hand, el = arms[i], pose["elbow"][i]
        sp = (side * 0.23 + shx, sh_y - 0.05)
        limb(d, P(*sp), P(*el), int(0.17 * ppm), SHIRT_D)
        limb(d, P(*el), P(*hand), int(0.13 * ppm), SKIN)
        r = 0.065 * ppm
        hx, hy = P(*hand)
        d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=SKIN)
    for side in (-1, 1):
        if pose.get("back_arm") == side:
            arm(side)
    tail = hip_y - 0.12
    body = [P(-0.26 + shx, sh_y), P(0.26 + shx, sh_y), P(0.2 + shx * 0.4, hip_y), P(0.22, tail), P(-0.22, tail), P(-0.2 + shx * 0.4, hip_y)]
    d.polygon(body, fill=SHIRT)
    d.polygon([P(0.04 + shx, sh_y), P(0.26 + shx, sh_y), P(0.2 + shx * 0.4, hip_y), P(0.22, tail), P(0.05, tail)], fill=SHIRT_D)
    d.line([P(shx, sh_y - 0.05), P(0.01, tail)], fill=shade(SHIRT_D, 0.8), width=2)
    d.rectangle([P(-0.22, hip_y + 0.02)[0], P(0, hip_y + 0.02)[1], P(0.22, hip_y - 0.04)[0], P(0, hip_y - 0.04)[1]], fill=STRAP)
    # satchel at the hip and the strap crossing the back
    d.polygon([P(-0.2 + shx * 0.4, hip_y + 0.28), P(0.12 + shx * 0.4, hip_y + 0.28), P(0.16, hip_y - 0.18), P(-0.22, hip_y - 0.18)], fill=SATCHEL)
    d.polygon([P(-0.2 + shx * 0.4, hip_y + 0.28), P(0.12 + shx * 0.4, hip_y + 0.28), P(0.1, hip_y + 0.12), P(-0.18, hip_y + 0.12)], fill=shade(SATCHEL, 1.18))
    d.line([P(-0.22 + shx, sh_y), P(0.12, hip_y + 0.26)], fill=STRAP, width=int(0.06 * ppm))
    for side in (-1, 1):
        if pose.get("back_arm") != side:
            arm(side)
    hx = shx * 1.1
    d.polygon([P(-0.15 + hx, sh_y + 0.02), P(0.15 + hx, sh_y + 0.02), P(0.1 + hx, sh_y + 0.14), P(-0.1 + hx, sh_y + 0.14)], fill=SKIN)
    cx, cy = P(hx, hd_y)
    r = 0.125 * ppm
    d.ellipse([cx - r, cy - r * 1.05, cx + r, cy + r * 1.05], fill=HAIR)
    d.ellipse([cx - r * 0.5, cy + r * 0.45, cx + r * 0.5, cy + r * 1.0], fill=SKIN)
    d.ellipse([cx - r * 0.95, cy - r * 1.0, cx + r * 0.3, cy + r * 0.1], fill=shade(HAIR, 1.25))
    return im, wm, hm


def rotated(src, ang, ppm=96, shift=(0.0, 0.0), scale=1.0):
    # whole-body transforms for stumbles and falls, pivoting on the feet
    im, wm, hm = src
    W, H = im.size
    pivot = (W / 2, H - 0.12 * ppm)
    out = im.rotate(ang, resample=Image.BICUBIC, center=pivot, translate=(shift[0] * ppm, -shift[1] * ppm))
    if scale != 1.0:
        w2, h2 = max(1, int(W * scale)), max(1, int(H * scale))
        sm = out.resize((w2, h2), Image.LANCZOS)
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out.alpha_composite(sm, (int(W / 2 - w2 / 2), int(H - 0.12 * ppm - (H - 0.12 * ppm) * scale)))
    return out, wm, hm


def run_pose(phase):
    s = math.sin(phase)
    c = math.cos(phase)
    lift = (max(0.0, s) * 0.5, max(0.0, -s) * 0.5)
    foot = [(-0.14 - 0.05 * lift[0], 0.04 + 1.1 * lift[0]), (0.14 + 0.05 * lift[1], 0.04 + 1.1 * lift[1])]
    knee = [(-0.17 - 0.07 * lift[0], 0.5 + 0.7 * lift[0]), (0.17 + 0.07 * lift[1], 0.5 + 0.7 * lift[1])]
    pa = (-s, s)
    arm = [(-0.34 + 0.1 * pa[0], 1.02 + 0.3 * pa[0]), (0.34 - 0.1 * pa[1], 1.02 + 0.3 * pa[1])]
    el = [(-0.36, 1.12 + 0.12 * pa[0]), (0.36, 1.12 + 0.12 * pa[1])]
    bob = -0.03 * abs(c)
    return dict(hip=0.95 + bob, sh=1.5 + bob, foot=foot, knee=knee, arm=arm, elbow=el, sole=(lift[0] > 0.3, lift[1] > 0.3),
                tilt=0.04 * s)


POSES = {
    "jump_up": dict(hip=1.0, sh=1.55, foot=[(-0.2, 0.3), (0.16, 0.18)], knee=[(-0.24, 0.62), (0.2, 0.55)],
                    arm=[(-0.4, 1.95), (0.4, 1.9)], elbow=[(-0.36, 1.75), (0.36, 1.72)], sole=(True, True)),
    "jump_down": dict(hip=0.98, sh=1.52, foot=[(-0.24, 0.1), (0.24, 0.08)], knee=[(-0.2, 0.54), (0.2, 0.54)],
                      arm=[(-0.66, 1.5), (0.66, 1.46)], elbow=[(-0.46, 1.5), (0.46, 1.48)]),
    "slide": dict(hip=0.38, sh=0.74, head=0.9, foot=[(-0.3, 0.05), (0.3, 0.05)], knee=[(-0.4, 0.2), (0.4, 0.2)],
                  arm=[(-0.56, 0.62), (0.56, 0.62)], elbow=[(-0.4, 0.55), (0.4, 0.55)], sole=(True, True), tilt=0.0),
    "stumble_a": dict(hip=0.88, sh=1.36, head=1.5, foot=[(-0.14, 0.04), (0.2, 0.3)], knee=[(-0.2, 0.46), (0.26, 0.62)],
                      arm=[(-0.7, 1.7), (0.7, 1.4)], elbow=[(-0.5, 1.6), (0.52, 1.46)], tilt=0.3),
    "stumble_b": dict(hip=0.84, sh=1.28, head=1.42, foot=[(-0.22, 0.04), (0.1, 0.04)], knee=[(-0.26, 0.44), (0.14, 0.44)],
                      arm=[(-0.76, 1.3), (0.76, 1.8)], elbow=[(-0.5, 1.4), (0.52, 1.6)], tilt=-0.35),
}


def apes_body(rnd, frame, face=False):
    # a dark ape in a bounding gallop seen from behind; the pale skull mask turns over its shoulder
    ppm = 64
    wm, hm = 2.0, 1.9
    im, d = canvas(wm, hm, ppm)
    W, H = im.size
    b = 4 if frame else 0
    fur, fur_d, fur_l = (30, 24, 30), (16, 12, 18), (58, 46, 56)
    for side in (-1, 1):
        sx = W / 2 + side * 0.62 * ppm
        d.line([(W / 2 + side * 0.45 * ppm, H * 0.45), (sx + side * 0.1 * ppm, H * 0.78), (sx, H - 2 - (b if side > 0 else 0))],
               fill=fur_d, width=int(0.34 * ppm))
        blob(d, sx, H - 6 - (b if side > 0 else 0), 0.2 * ppm, 0.12 * ppm, fur)
        d.line([(W / 2 + side * 0.25 * ppm, H * 0.7), (W / 2 + side * 0.34 * ppm, H - 3 - (0 if side > 0 else b))], fill=fur_d, width=int(0.3 * ppm))
    blob(d, W / 2, H * 0.55 - b / 2, 0.72 * ppm, 0.55 * ppm, fur)
    blob(d, W / 2 - 0.12 * ppm, H * 0.48 - b / 2, 0.6 * ppm, 0.4 * ppm, fur_l)
    for _ in range(14):
        x = W / 2 + rnd.uniform(-0.6, 0.6) * ppm
        y = H * 0.5 + rnd.uniform(-0.3, 0.3) * ppm
        d.line([(x, y), (x + rnd.uniform(-3, 3), y + 8)], fill=fur_d, width=2)
    hx, hy = W / 2 + 0.15 * ppm, H * 0.2 - b / 2
    blob(d, hx, hy, 0.38 * ppm, 0.34 * ppm, fur_d)
    d.pieslice([hx - 0.34 * ppm, hy - 0.3 * ppm, hx + 0.34 * ppm, hy + 0.34 * ppm], 300, 400, fill=(222, 218, 200, 255))
    g = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    for ex in (hx + 0.2 * ppm, hx + 0.34 * ppm):
        gd.ellipse([ex - 9, hy - 9, ex + 9, hy + 9], fill=(255, 40, 20, 150))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(im, "RGBA")
    for ex in (hx + 0.2 * ppm, hx + 0.34 * ppm):
        d.ellipse([ex - 3.5, hy - 3.5, ex + 3.5, hy + 3.5], fill=(255, 90, 60, 255))
        d.ellipse([ex - 1.5, hy - 1.5, ex + 1.5, hy + 1.5], fill=(255, 235, 200, 255))
    for ex in (hx - 0.28 * ppm, hx - 0.05 * ppm):
        d.polygon([(ex - 4, hy - 10), (ex + 4, hy - 10), (ex, hy - 24)], fill=fur_d)
    return im, wm, hm


def ape_pounce(rnd, size):
    # front view of an ape lunging at the screen, for the moment the runner is caught
    s = 400
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im, "RGBA")
    fur, fur_d = (30, 24, 30), (14, 10, 16)
    blob(d, s / 2, s * 0.6, s * 0.48, s * 0.4, fur_d)
    for side in (-1, 1):
        d.line([(s / 2 + side * s * 0.34, s * 0.7), (s / 2 + side * s * 0.46, s * 0.3)], fill=fur, width=int(s * 0.14))
        for k in range(4):
            x = s / 2 + side * (s * 0.46 + (k - 1.5) * s * 0.025)
            d.line([(x, s * 0.3), (x + side * 4, s * 0.18)], fill=(220, 214, 196, 255), width=7)
    blob(d, s / 2, s * 0.42, s * 0.3, s * 0.3, fur)
    d.ellipse([s * 0.3, s * 0.2, s * 0.7, s * 0.62], fill=(228, 224, 206, 255))
    d.ellipse([s * 0.33, s * 0.24, s * 0.5, s * 0.36], fill=(24, 18, 20, 255))
    d.ellipse([s * 0.5, s * 0.24, s * 0.67, s * 0.36], fill=(24, 18, 20, 255))
    g = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    for ex in (0.415, 0.585):
        gd.ellipse([s * ex - 26, s * 0.3 - 26, s * ex + 26, s * 0.3 + 26], fill=(255, 30, 10, 190))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im, "RGBA")
    for ex in (0.415, 0.585):
        d.ellipse([s * ex - 11, s * 0.3 - 11, s * ex + 11, s * 0.3 + 11], fill=(255, 70, 40, 255))
    d.polygon([(s * 0.46, s * 0.4), (s * 0.54, s * 0.4), (s * 0.5, s * 0.47)], fill=(24, 18, 20, 255))
    d.rectangle([s * 0.34, s * 0.5, s * 0.66, s * 0.56], fill=(24, 18, 20, 255))
    for k in range(8):
        x = s * (0.36 + k * 0.036)
        d.polygon([(x, s * 0.5), (x + s * 0.034, s * 0.5), (x + s * 0.017, s * 0.62)], fill=(240, 236, 220, 255))
    return im


def totem(pal, rnd, wm=0.9, hm=2.1):
    # carved stone totem on the path wall: the ornamental face blocks of the real game
    im, d = canvas(wm, hm)
    W, H = im.size
    stone_block(d, W * 0.12, H * 0.55, W * 0.88, H, pal, rnd, moss=False)
    stone_block(d, W * 0.06, H * 0.3, W * 0.94, H * 0.58, pal, rnd, moss=False)
    stone_block(d, W * 0.14, H * 0.04, W * 0.86, H * 0.32, pal, rnd, moss=False)
    for ex in (0.34, 0.66):
        d.ellipse([W * ex - 7, H * 0.38 - 7, W * ex + 7, H * 0.38 + 7], fill=(36, 26, 18, 255))
        d.ellipse([W * ex - 3, H * 0.38 - 3, W * ex + 3, H * 0.38 + 3], fill=pal["glow"])
    d.polygon([(W * 0.46, H * 0.4), (W * 0.54, H * 0.4), (W * 0.52, H * 0.5), (W * 0.48, H * 0.5)], fill=pal["stone_d"])
    d.rectangle([W * 0.32, H * 0.52, W * 0.68, H * 0.57], fill=(36, 26, 18, 255))
    d.rectangle([W * 0.2, H * 0.12, W * 0.8, H * 0.2], fill=pal["stone_d"])
    for _ in range(3):
        blob(d, rnd.uniform(0.2, 0.8) * W, H * 0.04, 0.1 * PPM, 0.06 * PPM, pal["moss"])
    return im, wm, hm
