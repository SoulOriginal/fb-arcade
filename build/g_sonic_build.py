# Build-time art for the Sonic-style platformer (runs on the dev machine with PIL, writes g_sonic.bin).
#
# Everything is drawn procedurally. One "virtual pixel" (vpx) is a 6x6 block of screen pixels, so a sprite
# row is stored as a list of opaque runs whose bytes are already expanded 6x horizontally (12 bytes per vpx):
# the game then patches runs into per-scanline byte rows without any per-pixel Python.
import math, random, struct, sys
from PIL import Image, ImageDraw, ImageFont
from buildlib import save_bundle, rgb565, BOLD, MONO

K = 6
_chunks = {}


def chunk(rgb):
    c = _chunks.get(rgb)
    if c is None:
        c = _chunks[rgb] = struct.pack("<H", rgb565(*rgb)) * K
    return c


def img_rows(im):
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    return [b"".join(chunk(px[x, y]) for x in range(w)) for y in range(h)]


def run_sprite(im):
    # RGBA -> (w, h, rows) where rows[y] = [(x_offset_vpx, bytes), ...] of opaque runs.
    w, h = im.size
    px = im.load()
    rows = []
    for y in range(h):
        runs, x = [], 0
        while x < w:
            if px[x, y][3] < 128:
                x += 1
                continue
            x0, buf = x, []
            while x < w and px[x, y][3] >= 128:
                buf.append(chunk(px[x, y][:3]))
                x += 1
            runs.append((x0, b"".join(buf)))
        rows.append(runs)
    return (w, h, rows)


def flip(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


def down(im, w, h):
    r = im.convert("RGBa").resize((w, h), Image.BOX).convert("RGBA")
    r.putalpha(r.getchannel("A").point(lambda v: 255 if v >= 110 else 0))
    return r


OUT = (14, 18, 64)
BL, BLD, BLL = (36, 96, 224), (22, 58, 170), (110, 170, 255)
SK, SKD = (248, 200, 150), (214, 152, 104)
RD, RDD = (224, 36, 36), (146, 16, 34)
WH = (250, 250, 250)
GRN = (30, 170, 70)
GOLD, GOLDD, GOLDL = (255, 208, 32), (176, 96, 0), (255, 246, 160)


class C:
    # Hi-res canvas addressed in vpx units; every shape gets an outline so limbs separate from each other.
    def __init__(s, w, h, S=8):
        s.w, s.h, s.S = w, h, S
        s.im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        s.d = ImageDraw.Draw(s.im)

    def ell(s, cx, cy, rx, ry, fill, out=OUT, ow=0.8):
        S = s.S
        if out:
            s.d.ellipse([(cx - rx - ow) * S, (cy - ry - ow) * S, (cx + rx + ow) * S, (cy + ry + ow) * S], fill=out)
        s.d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill)

    def hole(s, cx, cy, rx, ry):
        S = s.S
        s.d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=(0, 0, 0, 0))

    def poly(s, pts, fill, out=OUT, ow=0.8):
        P = [(x * s.S, y * s.S) for x, y in pts]
        if out:
            s.d.polygon(P, fill=out)
            s.d.line(P + [P[0]], fill=out, width=max(1, int(2 * ow * s.S)), joint="curve")
        s.d.polygon(P, fill=fill)

    def line(s, a, b, w, fill, out=OUT, ow=0.8):
        S = s.S
        for col, ww in ((out, w + 2 * ow), (fill, w)):
            if col is None:
                continue
            s.d.line([(a[0] * S, a[1] * S), (b[0] * S, b[1] * S)], fill=col, width=max(1, int(ww * S)))
            for p in (a, b):
                r = ww / 2
                s.d.ellipse([(p[0] - r) * S, (p[1] - r) * S, (p[0] + r) * S, (p[1] + r) * S], fill=col)

    def rect(s, x0, y0, x1, y1, fill, out=OUT, ow=0.7):
        S = s.S
        if out:
            s.d.rectangle([(x0 - ow) * S, (y0 - ow) * S, (x1 + ow) * S - 1, (y1 + ow) * S - 1], fill=out)
        s.d.rectangle([x0 * S, y0 * S, x1 * S - 1, y1 * S - 1], fill=fill)

    def done(s):
        return down(s.im, s.w, s.h)


# ---------------------------------------------------------------------------------------------- Sonic
def head(c, hx, hy, eye="open", mouth=False, trail=0.0):
    q = [[(hx - 2, hy - 9), (hx - 9, hy - 2), (hx - 18 - trail * 3, hy - 10 + trail * 2)],
         [(hx - 8, hy - 5), (hx - 8, hy + 6), (hx - 20 - trail * 3, hy + 3 + trail * 3)],
         [(hx - 6, hy + 3), (hx - 1, hy + 9.5), (hx - 15 - trail * 3, hy + 13 + trail * 2)]]
    for p in q:
        c.poly(p, BL)
    c.poly([(hx - 3, hy - 8), (hx, hy - 15), (hx + 5, hy - 7)], BL)
    c.ell(hx, hy, 9.6, 9.2, BL)
    c.ell(hx + 5.6, hy + 3.6, 5.6, 4.6, SK)
    c.ell(hx + 11, hy + 1.8, 1.7, 1.4, OUT, out=None)
    c.ell(hx + 3.2, hy - 2.6, 4.2, 5.4, WH)
    if eye == "open":
        c.ell(hx + 4.6, hy - 2.2, 1.9, 2.9, GRN, out=None)
        c.ell(hx + 4.9, hy - 2.1, 1.0, 1.7, OUT, out=None)
        c.ell(hx + 4.3, hy - 3.6, 0.6, 0.7, WH, out=None)
    else:
        c.line((hx + 1.2, hy - 5), (hx + 5.4, hy), 0.7, OUT, out=None)
        c.line((hx + 5.4, hy - 5), (hx + 1.2, hy), 0.7, OUT, out=None)
    if mouth:
        c.ell(hx + 7.4, hy + 6.8, 2.2, 1.9, RDD, out=None)
    else:
        c.line((hx + 5.5, hy + 6.8), (hx + 9.5, hy + 6.2), 0.5, OUT, out=None)


def shoe(c, ax, ay):
    c.ell(ax + 1.3, ay - 0.6, 5.5, 3.1, RD)
    c.ell(ax - 0.6, ay - 1.9, 1.5, 1.2, WH, out=None)
    c.line((ax - 3.8, ay + 1.9), (ax + 6.0, ay + 1.9), 0.9, (230, 230, 240), out=None)


def leg(c, hip, ankle):
    c.line(hip, ankle, 3.6, BL)
    shoe(c, *ankle)


def arm(c, sh, hand):
    c.line(sh, hand, 2.6, SK)
    c.ell(hand[0], hand[1], 2.6, 2.6, (245, 245, 250))


def torso(c, tx, ty):
    c.ell(tx, ty, 6.3, 8.4, BL)
    c.ell(tx + 2.4, ty + 1.8, 3.5, 5.6, SK, out=None)


def sonic_frame(kind, ph=0.0):
    c = C(40, 44)
    if kind == "ball":
        cx, cy = 20, 29.5
        for k in range(5):
            a = ph + k * 2 * math.pi / 5
            c.poly([(cx + 9 * math.cos(a - 0.35), cy + 9 * math.sin(a - 0.35)),
                    (cx + 9 * math.cos(a + 0.35), cy + 9 * math.sin(a + 0.35)),
                    (cx + 14.4 * math.cos(a), cy + 14.4 * math.sin(a))], BLD)
        c.ell(cx, cy, 12, 12, BL)
        c.ell(cx + 6 * math.cos(ph + 1), cy + 6 * math.sin(ph + 1), 3.6, 3.6, SK, out=None)
        c.ell(cx + 7 * math.cos(ph + 3.9), cy + 7 * math.sin(ph + 3.9), 3.3, 2.7, RD, out=None)
        c.ell(cx + 6 * math.cos(ph + 2.5), cy + 6 * math.sin(ph + 2.5), 2.2, 2.2, BLL, out=None)
        return c.done()
    hx, hy, tx, ty = 22, 15, 19.5, 27
    hip = (19.5, 33)
    eye, mouth, trail = "open", False, 0.0
    far_leg, near_leg = (15.5, 40.6), (23.8, 40.6)
    far_arm, near_arm = (14.2, 33), (25, 33.5)
    blur = False
    if kind == "walk":
        s, co = math.sin(ph), math.cos(ph)
        far_leg = (19.5 - 5.5 * s, 40.6 - 3.2 * max(0, -co))
        near_leg = (19.5 + 5.5 * s, 40.6 - 3.2 * max(0, co))
        far_arm, near_arm = (19.5 + 5 * s, 33.5), (19.5 - 5 * s, 33.5)
        hy += 0.6 * abs(math.sin(2 * ph))
        ty += 0.4 * abs(math.sin(2 * ph))
    elif kind == "run":
        s, co = math.sin(ph), math.cos(ph)
        far_leg = (19.5 - 8 * s, 40.4 - 7 * max(0, -co))
        near_leg = (19.5 + 8 * s, 40.4 - 7 * max(0, co))
        hx, hy, tx, ty, trail = 25, 16, 21, 28, 1.0
        hip = (20.5, 34)
        far_arm, near_arm = (11.5, 29 + 2 * s), (13.5, 31 - 2 * s)
        mouth = False
    elif kind == "blur":
        hx, hy, tx, ty, trail = 26, 16.5, 22, 28.5, 1.4
        hip = (21, 34)
        far_arm, near_arm = (10, 28), (12, 30.5)
        blur = True
    elif kind == "skid":
        hx, hy, tx, ty = 19, 16.5, 17.5, 27.5
        hip = (17.5, 33.5)
        far_leg, near_leg = (11.5 + (ph > 0) * 1.5, 40.6), (25, 40.6 - (ph > 0) * 1.2)
        far_arm, near_arm = (24.5, 29), (27.5, 32)
        mouth = True
    elif kind == "hurt":
        hx, hy, tx, ty = 20, 15, 19, 27.5
        far_leg, near_leg = (13.5, 39.5), (26, 38.5)
        far_arm, near_arm = (12.5, 16.5), (27, 17)
        eye, mouth = "x", True
    elif kind == "spring":
        far_leg, near_leg = (18, 40.6), (21.8, 40.6)
        far_arm, near_arm = (17, 8.5), (26, 9.5)
        mouth = True
    elif kind == "wave":
        near_arm = (28.5 + 1.5 * math.sin(ph), 21 - 1.5 * abs(math.sin(ph)))
    elif kind != "idle":
        raise ValueError(kind)
    head(c, hx, hy, eye, mouth, trail)
    arm(c, (tx - 1, ty - 3), far_arm)
    if blur:
        c.ell(hip[0] - 1.5, 38.2, 8.4, 5.3, RD)
        for k in range(3):
            a = ph * 1.7 + k * 2.1
            c.line((hip[0] - 1.5 + 5 * math.cos(a), 38.2 + 3.2 * math.sin(a)),
                   (hip[0] - 1.5 + 7.6 * math.cos(a + 0.7), 38.2 + 4.8 * math.sin(a + 0.7)), 1.2, WH, out=None)
    else:
        leg(c, hip, far_leg)
        leg(c, hip, near_leg)
    torso(c, tx, ty)
    arm(c, (tx + 1.5, ty - 3), near_arm)
    return c.done()


def sonic_sets():
    right = {
        "idle": [sonic_frame("idle")],
        "walk": [sonic_frame("walk", i * math.pi / 3) for i in range(6)],
        "run": [sonic_frame("run", i * math.pi / 2) for i in range(4)],
        "blur": [sonic_frame("blur", i * 0.9) for i in range(2)],
        "ball": [sonic_frame("ball", i * math.pi / 5) for i in range(5)],
        "skid": [sonic_frame("skid", 0), sonic_frame("skid", 1)],
        "hurt": [sonic_frame("hurt")],
        "spring": [sonic_frame("spring")],
        "wave": [sonic_frame("wave", i * 1.4) for i in range(3)],
    }
    return ({k: [run_sprite(f) for f in v] for k, v in right.items()},
            {k: [run_sprite(flip(f)) for f in v] for k, v in right.items()})


def life_icon():
    c = C(40, 44)
    head(c, 22, 15, "open", False, 0)
    return run_sprite(down(c.im.crop((6 * 8, 0, 34 * 8, 28 * 8)), 14, 14))


# ------------------------------------------------------------------------------------- small objects
def ring_frames():
    out = []
    for w in (14, 10, 3, 10):
        c = C(16, 16)
        c.ell(8, 8, w / 2, 7, GOLD, out=GOLDD, ow=0.8)
        if w > 4:
            c.hole(8, 8, max(0.4, w / 2 - 2.9), 4.1)
            c.d.arc([(8 - w / 2 + 0.9) * 8, 1.9 * 8, (8 + w / 2 - 0.9) * 8, 14.1 * 8], 200, 290, fill=GOLDL, width=10)
        out.append(run_sprite(c.done()))
    return out


def sparkle_frames():
    out = []
    for r in (3, 6, 7, 5, 3):
        c = C(16, 16)
        c.poly([(8, 8 - r), (8 + r * 0.28, 8 - r * 0.28), (8 + r, 8), (8 + r * 0.28, 8 + r * 0.28), (8, 8 + r),
                (8 - r * 0.28, 8 + r * 0.28), (8 - r, 8), (8 - r * 0.28, 8 - r * 0.28)], (255, 255, 200), out=GOLD, ow=0.5)
        out.append(run_sprite(c.done()))
    return out


def spring_frames(top):
    out = []
    for h in (15, 8):
        c = C(20, 16)
        c.rect(1, 13, 19, 16, (70, 74, 90))
        n = 4
        for i in range(n):
            c.line((4, 13 - i * (h - 5) / n), (16, 13 - (i + 0.5) * (h - 5) / n), 1.8, (225, 228, 238))
            c.line((16, 13 - (i + 0.5) * (h - 5) / n), (4, 13 - (i + 1) * (h - 5) / n), 1.8, (180, 184, 200))
        c.rect(1, 16 - h - 0.5, 19, 16 - h + 3, top)
        out.append(run_sprite(c.done()))
    return out


def spikes_sprite():
    c = C(32, 16)
    for i in range(4):
        x = i * 8
        c.poly([(x + 1, 14), (x + 4, 0.8), (x + 7, 14)], (222, 226, 238), out=(40, 44, 70))
        c.line((x + 4, 2), (x + 4, 13), 0.7, (150, 156, 180), out=None)
    c.rect(0, 13.5, 32, 16, (80, 84, 110))
    return run_sprite(c.done())


def monitor_frames():
    out = {}
    for kind in ("ring", "shield"):
        fr = []
        for lit in (0, 1):
            c = C(28, 28)
            c.rect(1, 3, 27, 26, (176, 182, 200))
            c.rect(3.5, 5.5, 24.5, 21.5, (18, 24, 60) if lit else (30, 44, 100), out=(80, 90, 120))
            if kind == "ring":
                c.ell(14, 13.5, 5, 5, GOLD, out=GOLDD)
                c.hole(14, 13.5, 2.4, 2.4)
            else:
                c.ell(14, 13.5, 5.6, 5.6, (80, 150, 255), out=(180, 220, 255))
                c.ell(12.5, 11.5, 1.6, 1.6, WH, out=None)
            if lit:
                c.line((5, 7), (9, 7), 0.8, (200, 230, 255), out=None)
            c.rect(2, 23, 26, 27, (110, 116, 140))
            fr.append(run_sprite(c.done()))
        out[kind] = fr
    c = C(28, 28)
    c.rect(1, 3, 27, 26, (150, 154, 170))
    c.rect(3.5, 5.5, 24.5, 21.5, (28, 28, 40), out=(70, 74, 96))
    c.rect(2, 23, 26, 27, (96, 100, 120))
    out["broken"] = run_sprite(c.done())
    icons = {}
    for kind in ("ring", "shield"):
        c = C(14, 14)
        if kind == "ring":
            c.ell(7, 7, 5.5, 5.5, GOLD, out=GOLDD)
            c.hole(7, 7, 2.8, 2.8)
        else:
            c.ell(7, 7, 6, 6, (80, 150, 255), out=(180, 220, 255))
            c.ell(5.4, 5, 1.6, 1.6, WH, out=None)
        icons[kind] = run_sprite(c.done())
    out["icons"] = icons
    return out


def shield_frames():
    out = []
    for f in range(2):
        c = C(44, 48, 6)
        for i in range(34):
            a = i * 2 * math.pi / 34
            if (i + f) % 3 == 0:
                continue
            r = (200, 235, 255) if (i + f) % 2 else (90, 160, 255)
            x, y = 22 + 20.5 * math.cos(a), 25 + 22.5 * math.sin(a)
            c.ell(x, y, 1.5, 1.5, r, out=None)
        out.append(run_sprite(c.done()))
    return out


def sign_frames():
    out = []
    for kind, w in (("evil", 28), ("edge", 5), ("back", 28), ("edge", 5), ("goal", 28)):
        c = C(32, 48)
        c.rect(14, 18, 18, 47, (190, 194, 210))
        c.ell(16, 46, 5, 2.4, (120, 124, 150))
        x0, x1 = 16 - w / 2, 16 + w / 2
        if kind == "edge":
            c.rect(x0, 1, x1, 21, (230, 230, 240))
        else:
            col = {"evil": (190, 30, 50), "back": (150, 156, 176), "goal": (30, 86, 214)}[kind]
            c.rect(x0, 1, x1, 21, col, out=(250, 250, 250), ow=1.0)
            if kind == "evil":
                c.ell(16, 11, 7, 6.5, (250, 150, 40))
                c.line((10, 8), (14, 10), 1.3, OUT, out=None)
                c.line((22, 8), (18, 10), 1.3, OUT, out=None)
                c.line((10, 14), (22, 14), 1.4, OUT, out=None)
            elif kind == "back":
                for rx in (x0 + 3, x1 - 3):
                    for ry in (4, 18):
                        c.ell(rx, ry, 1, 1, (90, 94, 110), out=None)
            else:
                c.poly([(16 + 7.5 * math.sin(i * math.pi / 5) * (1 if i % 2 == 0 else 0.45),
                         11 - 7.5 * math.cos(i * math.pi / 5) * (1 if i % 2 == 0 else 0.45)) for i in range(10)],
                       GOLD, out=GOLDD, ow=0.6)
        out.append(run_sprite(c.done()))
    return out


def bumper_frames():
    out = []
    for r in (16.5, 18.5):
        c = C(40, 40)
        c.ell(20, 20, r, r, (40, 48, 150))
        c.ell(20, 20, r - 3, r - 3, (230, 50, 60), out=(255, 255, 255), ow=0.6)
        c.ell(20, 20, r - 8, r - 8, (250, 250, 255), out=None)
        c.ell(20, 20, r - 11, r - 11, (60, 90, 230), out=None)
        c.ell(14, 13, 2.4, 1.6, WH, out=None)
        out.append(run_sprite(c.done()))
    return out


def dust_frames():
    out = []
    for r, n in ((2, 2), (3, 3), (4, 3), (3, 2)):
        c = C(14, 12)
        for i in range(n):
            c.ell(4 + i * 3.2, 9 - i * 1.2 - r * 0.3, r * 0.8, r * 0.8, (236, 226, 200), out=None)
        out.append(run_sprite(c.done()))
    return out


# ------------------------------------------------------------------------------------------ enemies
def motobug_frames():
    out = []
    for f in range(2):
        c = C(32, 24)
        c.ell(11, 20 - f * 0.4, 5, 5, (30, 30, 40), out=OUT)
        c.ell(11, 20 - f * 0.4, 2, 2, (170, 174, 190), out=None)
        a = f * 1.2
        c.line((11, 20 - f * 0.4), (11 + 4 * math.cos(a), 20 - f * 0.4 + 4 * math.sin(a)), 0.9, (170, 174, 190), out=None)
        c.ell(17, 13 - f * 0.5, 13, 9, (226, 38, 44))
        c.rect(7, 18 - f * 0.5, 28, 21, (60, 62, 80), out=OUT)
        for sx, sy, sr in ((18, 8, 2.4), (23, 12, 2.1), (13, 12, 1.8)):
            c.ell(sx, sy - f * 0.5, sr, sr, OUT, out=None)
        c.ell(6, 12, 4.2, 4.6, (240, 230, 200))
        c.ell(5.2, 11.2, 1.5, 1.8, OUT, out=None)
        c.line((4, 7), (1.5, 3), 0.7, OUT, out=None)
        c.ell(27.5, 15, 1.6, 1.6, (150, 150, 160), out=None)
        out.append(c.done())
    return out


def crab_frames():
    out = []
    for f in range(2):
        c = C(36, 26)
        for side in (-1, 1):
            cx = 18 + side * 1
            for i in range(3):
                x0 = cx + side * (6 + i * 2.5)
                y1 = 25 - (1.2 if (i + f) % 2 else 0)
                c.line((cx + side * (4 + i), 19), (x0 + side * 1.5, y1), 1.2, (210, 70, 30))
        c.ell(18, 15, 12, 8.5, (226, 82, 40))
        c.ell(18, 17, 8, 4.5, (250, 170, 90), out=None)
        for side in (-1, 1):
            ex = 18 + side * 5
            c.line((ex, 8), (ex + side * 1, 3.5), 1.1, (210, 70, 30))
            c.ell(ex + side * 1, 3.5, 2.4, 2.4, WH)
            c.ell(ex + side * 1.4, 3.5, 1, 1, OUT, out=None)
            ky = 15 if f == 0 else 21
            c.line((18 + side * 11, 15), (18 + side * 14.5, ky - 4 * (1 - f)), 1.8, (226, 82, 40))
            c.ell(18 + side * 15, ky - 4 * (1 - f) - 1.5, 3.4, 3.4, (226, 82, 40))
            c.poly([(18 + side * 15, ky - 8 * (1 - f) - 5 + 4 * f), (18 + side * 12.5, ky - 4 * (1 - f)),
                    (18 + side * 17.5, ky - 4 * (1 - f))], (226, 82, 40))
        out.append(c.done())
    return out


def buzz_frames():
    out = []
    for f in range(2):
        c = C(40, 26)
        wy = (3, 8)[f]
        c.poly([(18, 10), (22, wy), (31, wy + 1), (26, 10)], (205, 235, 255), out=(70, 100, 160))
        c.poly([(15, 10), (14, wy + 1), (20, wy), (22, 10)], (230, 245, 255), out=(70, 100, 160))
        c.ell(27, 15, 9, 5.5, (250, 200, 30))
        for sx in (23, 27, 31):
            c.rect(sx - 1, 10.5, sx + 0.6, 19.5, (30, 28, 40), out=None)
        c.poly([(34, 14), (39, 17), (34, 18)], (60, 62, 80))
        c.ell(15, 15, 6.5, 6, (60, 170, 160))
        c.ell(11.5, 13.8, 3.1, 3.3, (255, 70, 60))
        c.ell(11, 13.2, 1.1, 1.2, WH, out=None)
        c.poly([(8, 18), (11, 22), (13, 18)], (90, 94, 110))
        out.append(c.done())
    return out


def shot_frames():
    out = []
    for r in (3.4, 2.6):
        c = C(8, 8)
        c.ell(4, 4, r, r, (255, 120, 40), out=(150, 20, 20), ow=0.5)
        c.ell(4, 4, r - 1.5, r - 1.5, (255, 250, 190), out=None)
        out.append(run_sprite(c.done()))
    return out


def explosion_frames():
    out = []
    spec = [(5, 0), (11, 3), (15, 7), (17, 12), (18, 15)]
    for i, (r, hole) in enumerate(spec):
        c = C(40, 40)
        c.ell(20, 20, r, r, (255, 180, 40) if i > 0 else (255, 250, 220), out=(230, 90, 20), ow=0.9)
        if i > 0:
            c.ell(20, 20, max(1, r - 4), max(1, r - 4), (255, 244, 170), out=None)
        if hole:
            c.hole(20, 20, hole, hole)
        if i >= 2:
            for k in range(5):
                a = k * 1.26 + i
                c.ell(20 + (r + 2) * math.cos(a), 20 + (r + 2) * math.sin(a), 2.2, 2.2, (255, 220, 120), out=None)
        out.append(run_sprite(c.done()))
    return out


def animal_frames():
    out = {}
    fr = []
    for f in range(2):
        c = C(12, 12)
        c.ell(6, 7, 3.4, 3, (60, 150, 240))
        c.ell(9, 5.2, 2.2, 2.2, (60, 150, 240))
        c.poly([(10.5, 5), (12, 5.6), (10.6, 6.4)], (255, 190, 40), out=None)
        c.poly([(3, 6), (0.3, 5), (3.2, 8)], (30, 90, 180))
        wy = (2.5, 8.5)[f]
        c.poly([(4, 6), (6, wy), (8, 6)], (150, 200, 255), out=OUT)
        fr.append(run_sprite(c.done()))
    out["bird"] = fr
    fr = []
    for f in range(2):
        c = C(12, 14)
        c.ell(6, 10 - f, 3.6, 3, (236, 170, 110))
        c.ell(8, 6.6 - f, 2.4, 2.4, (236, 170, 110))
        c.ell(7.4, 2 - f, 0.9, 2.6, (236, 170, 110))
        c.ell(9.2, 2.4 - f, 0.9, 2.4, (236, 170, 110))
        c.ell(9, 6 - f, 0.5, 0.5, OUT, out=None)
        c.ell(3, 11.6 - f * 1.5, 1.4, 1.6, WH)
        fr.append(run_sprite(c.done()))
    out["rabbit"] = fr
    return out


# ------------------------------------------------------------------------------------------- decor
def palm_frames():
    out = []
    for f in range(2):
        c = C(48, 76)
        pts = [(24, 76), (22, 60), (21.5, 44), (24, 30), (28, 20)]
        for a, b in zip(pts, pts[1:]):
            c.line(a, b, 4.4, (170, 100, 40), out=(80, 40, 10))
        for i in range(1, 11):
            y = 76 - i * 5.6
            xx = 24 - 2.5 * math.sin(i / 4.2)
            c.line((xx - 2.3, y), (xx + 2.3, y - 0.6), 0.9, (110, 60, 20), out=None)
        tx, ty = 28, 19
        sw = 0.18 * (f * 2 - 1)
        for ang in (-2.7, -2.1, -1.5, -0.9, -0.35, 0.2):
            a = ang + sw
            ex, ey = tx + 21 * math.cos(a), ty + 12 * math.sin(a) + 11 * (1 - abs(math.sin(a)))
            mx, my = tx + 11 * math.cos(a), ty + 12 * math.sin(a) - 5
            c.poly([(tx, ty), (mx - 1.5, my - 3.5), (ex, ey), (mx + 1.5, my + 2.5)], (36, 160, 60), out=(10, 70, 30))
            c.line((tx, ty), (ex, ey), 0.7, (130, 220, 90), out=None)
        c.ell(tx - 1, ty + 2.5, 2.4, 2.4, (120, 70, 30))
        c.ell(tx + 2.2, ty + 3, 2.4, 2.4, (120, 70, 30))
        out.append(run_sprite(c.done()))
    return out


def totem_sprite():
    c = C(20, 49)
    cols = [((220, 60, 40), (250, 220, 60)), ((60, 130, 220), (250, 250, 250)), ((250, 190, 40), (190, 40, 40))]
    for i, (a, b) in enumerate(cols):
        y = 4 + i * 15
        c.rect(3, y, 17, y + 14, (150, 90, 40), out=(60, 30, 10))
        c.poly([(3, y + 3), (10, y), (17, y + 3), (17, y + 11), (10, y + 14), (3, y + 11)], a, out=(60, 30, 10), ow=0.6)
        c.ell(7, y + 6, 1.7, 1.9, WH, out=OUT, ow=0.4)
        c.ell(13, y + 6, 1.7, 1.9, WH, out=OUT, ow=0.4)
        c.ell(7.3, y + 6.2, 0.7, 0.8, OUT, out=None)
        c.ell(12.7, y + 6.2, 0.7, 0.8, OUT, out=None)
        c.poly([(8, y + 8.2), (12, y + 8.2), (10, y + 12)], b, out=OUT, ow=0.4)
    c.poly([(1, 4), (10, 1), (19, 4), (10, 6)], (250, 220, 60), out=(60, 30, 10))
    return run_sprite(c.done())


def flower_frames():
    out = []
    for f in range(2):
        c = C(16, 24)
        c.line((8, 24), (8 + f * 0.6, 11), 1.2, (30, 130, 40), out=None)
        c.poly([(8, 20), (13, 15), (10, 21)], (40, 160, 50), out=None)
        for k in range(8):
            a = k * math.pi / 4 + f * 0.4
            c.ell(8 + f * 0.6 + 4.6 * math.cos(a), 8 + 4.6 * math.sin(a), 2.2, 2.2, (255, 220, 40), out=(170, 90, 10), ow=0.5)
        c.ell(8 + f * 0.6, 8, 3, 3, (130, 70, 30), out=(70, 30, 10), ow=0.5)
        out.append(run_sprite(c.done()))
    return out


def bush_sprite():
    c = C(26, 14)
    for cx, cy, r in ((7, 9, 6), (14, 7, 7), (20, 10, 5.5)):
        c.ell(cx, cy, r, r * 0.9, (30, 150, 50), out=(8, 70, 30))
    for cx, cy in ((6, 8), (13, 5), (19, 9), (10, 10)):
        c.ell(cx, cy, 1.3, 1.3, (250, 90, 150), out=None)
    return run_sprite(c.done())


def column_sprite():
    c = C(30, 52)
    c.rect(4, 6, 26, 52, (124, 96, 160), out=(40, 20, 70))
    for x in (8, 13, 18, 23):
        c.line((x, 8), (x, 51), 1.0, (96, 70, 130), out=None)
    c.rect(1, 0, 29, 7, (146, 116, 184), out=(40, 20, 70))
    c.rect(1, 46, 29, 52, (146, 116, 184), out=(40, 20, 70))
    c.poly([(4, 6), (10, 12), (6, 18), (4, 15)], (40, 20, 70), out=None)
    return run_sprite(c.done())


def brazier_frames():
    out = []
    for f in range(2):
        c = C(20, 36)
        c.rect(8, 18, 12, 36, (110, 84, 150), out=(40, 20, 70))
        c.poly([(2, 12), (18, 12), (14, 20), (6, 20)], (146, 116, 184), out=(40, 20, 70))
        for k, (w, h, col) in enumerate(((7, 14, (255, 90, 30)), (5, 10, (255, 190, 50)), (3, 6, (255, 250, 190)))):
            sway = (1.2 if f else -1.2) * (1 - k * 0.3)
            c.poly([(10 - w / 2, 13), (10 + sway, 12 - h), (10 + w / 2, 13)], col, out=None if k else (150, 30, 10), ow=0.5)
        out.append(run_sprite(c.done()))
    return out


def lamp_frames():
    out = []
    for f in range(2):
        c = C(18, 46)
        c.rect(7, 12, 11, 46, (70, 80, 130), out=(10, 10, 40))
        c.rect(4, 42, 14, 46, (90, 100, 150), out=(10, 10, 40))
        c.ell(9, 8, 6.4, 6.4, (255, 240, 150) if f else (255, 215, 90), out=(10, 10, 40))
        c.ell(7.4, 6.2, 2, 2, WH, out=None)
        out.append(run_sprite(c.done()))
    return out


# ----------------------------------------------------------------------------------- terrain tiles
def hsh(a, b):
    return ((a * 73856093) ^ (b * 19349663) ^ (a * b * 83492791)) & 0xFFFF


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def texel_ghz(wx, wy, d):
    if d < 0:
        return None
    edge = 6 + (0, 1, 2, 1)[(wx // 2) % 4]
    if d < edge:
        if d == 0:
            return (120, 236, 70)
        if d == 1:
            return (70, 200, 40)
        if d < edge - 1:
            return (30, 156, 36) if (wx + d) % 7 else (60, 184, 50)
        return (14, 96, 30)
    cell = ((wx // 16) + (wy // 16)) % 2
    c = (216, 128, 48) if cell else (146, 78, 30)
    lx, ly = wx % 16, wy % 16
    if lx == 0 or ly == 0:
        c = mix(c, (250, 190, 100), 0.45)
    elif lx == 15 or ly == 15:
        c = mix(c, (70, 30, 10), 0.4)
    if hsh(wx, wy) % 29 == 0:
        c = mix(c, (60, 28, 10), 0.5)
    return c


def texel_mz(wx, wy, d):
    if d < 0:
        return None
    edge = 3 + (wx // 3) % 2
    if d < edge:
        return (60, 190, 70) if d < 1 else (28, 128, 50)
    row = wy // 8
    xo = wx + (8 if row % 2 else 0)
    bx, by = xo % 16, wy % 8
    pal = ((128, 76, 176), (104, 58, 150), (146, 92, 196), (88, 46, 132))
    c = pal[hsh(xo // 16, row) % 4]
    if bx == 0 or by == 0:
        c = (34, 16, 56)
    elif bx == 1 or by == 1:
        c = mix(c, (200, 160, 240), 0.35)
    elif bx == 15 or by == 7:
        c = mix(c, (30, 10, 50), 0.35)
    return c


def texel_syz(wx, wy, d):
    if d < 0:
        return None
    if d < 2:
        return (190, 240, 255) if d == 0 else (110, 190, 230)
    if d < 4:
        return (60, 90, 170)
    cell = ((wx // 16) + (wy // 16)) % 2
    c = (52, 66, 130) if cell else (38, 48, 104)
    lx, ly = wx % 16, wy % 16
    if lx == 0 or ly == 0:
        c = mix(c, (130, 150, 230), 0.4)
    elif lx == 15 or ly == 15:
        c = mix(c, (10, 14, 50), 0.5)
    if lx in (7, 8) and ly in (7, 8):
        c = (255, 226, 100) if cell else (255, 140, 200)
    return c


def texel_lava(wx, wy, d):
    if d < 0:
        return None
    v = math.sin(2 * math.pi * wx / 32 + (wy % 16) * 0.8) + math.sin(2 * math.pi * wx / 16 - (wy % 16) * 0.4)
    t = max(0.0, min(1.0, 0.5 + v * 0.25))
    c = mix((200, 30, 10), (255, 190, 40), t)
    if d == 0:
        c = (255, 240, 130)
    return c


TEXELS = {"ghz": texel_ghz, "mz": texel_mz, "syz": texel_syz}
LAVA_Y = 320


def tile_image(fn, px, base, a, d, lava=False):
    im = Image.new("RGB", (16, 32))
    pxl = im.load()
    for k in range(16):
        surf = a + int(d * k / 16)
        for r in range(32):
            wx, wy = px * 16 + k, base + r
            col = fn(wx, wy, r - surf)
            pxl[k, r] = col if col else fn(wx, wy, 99)
    return img_rows(im)


def zone_tiles(name):
    fn = TEXELS[name]
    tiles = {}
    for px in (0, 1):
        for py in (0, 1):
            base = py * 16
            for ph in (0, 4, 8, 12):
                for d in (-8, -4, 0, 4, 8):
                    a = ph if d >= 0 else ph - d
                    tiles[(px, py, ph, d)] = tile_image(fn, px, base, a, d)
        tiles[("lava", px)] = tile_image(texel_lava, px, LAVA_Y, 0, 0)
    fill = []
    for wy in range(32):
        im = Image.new("RGB", (32, 1))
        for wx in range(32):
            im.putpixel((wx, 0), fn(wx, wy, 99))
        fill.append(img_rows(im)[0])
    lava_fill = []
    for wy in range(32):
        im = Image.new("RGB", (32, 1))
        for wx in range(32):
            im.putpixel((wx, 0), texel_lava(wx, wy, 99))
        lava_fill.append(img_rows(im)[0])
    return {"tiles": tiles, "fill": fill, "lava_fill": lava_fill}


# ------------------------------------------------------------------------------------- backgrounds
BG_ROWS = 204


def grad(stops, r):
    for (r0, c0), (r1, c1) in zip(stops, stops[1:]):
        if r <= r1:
            return mix(c0, c1, (r - r0) / max(1, r1 - r0))
    return stops[-1][1]


def make_layer(r0, r1, P, factor, colour_fn, draw_fn=None, frames=1, wave=False):
    # Rows r0..r1 of the background share one scroll speed. The image is periodic in x and extended by one screen
    # width so a plain slice can be taken at any offset.
    h = r1 - r0
    outs = []
    for f in range(frames):
        im = Image.new("RGB", (P, h))
        d = ImageDraw.Draw(im)
        for y in range(h):
            d.line([(0, y), (P, y)], fill=colour_fn(r0 + y))
        if draw_fn:
            for dx in (-P, 0, P):
                draw_fn(d, dx, r0, f)
        ext = Image.new("RGB", (P + 320, h))
        for x in range(0, P + 320, P):
            ext.paste(im, (x, 0))
        outs.append(img_rows(ext))
    spec = []
    for y in range(h):
        fr = [outs[f][y] for f in range(frames)]
        if all(x == fr[0] for x in fr):
            fr = fr[:1]
        spec.append((fr, P, factor, wave))
    return spec


def cloud(d, x, y, s, col=(252, 252, 255), sh=(196, 222, 250)):
    for dx, dy, rx, ry in ((0, 0, 9, 4), (8, -3, 8, 5), (16, 0, 10, 4), (-6, 1, 6, 3), (24, 1, 6, 3)):
        d.ellipse([x + (dx - rx) * s, y + (dy - ry) * s + 2, x + (dx + rx) * s, y + (dy + ry) * s + 2], fill=sh)
    for dx, dy, rx, ry in ((0, 0, 9, 4), (8, -3, 8, 5), (16, 0, 10, 4), (-6, 1, 6, 3), (24, 1, 6, 3)):
        d.ellipse([x + (dx - rx) * s, y + (dy - ry) * s, x + (dx + rx) * s, y + (dy + ry) * s], fill=col)


def bg_ghz():
    rnd = random.Random(11)
    sky = [(0, (30, 110, 228)), (50, (110, 190, 250)), (80, (170, 226, 252))]
    sk = lambda r: grad(sky, r)
    spec = []
    spec += make_layer(0, 8, 320, 0, sk)

    def clouds(n, y0, s):
        pos = [(rnd.randrange(0, 400), y0 + rnd.randrange(-1, 3)) for _ in range(n)]
        return lambda d, dx, r0, f: [cloud(d, x + dx, y - r0, s) for x, y in pos]
    spec += make_layer(8, 20, 400, 0.05, sk, clouds(4, 14, 0.9))
    spec += make_layer(20, 32, 320, 0.1, sk, clouds(4, 26, 0.8))
    spec += make_layer(32, 44, 288, 0.17, sk, clouds(3, 38, 0.7))
    spec += make_layer(44, 48, 320, 0, sk)
    mts = []
    x = 0
    while x < 384:
        w = rnd.randrange(50, 90)
        mts.append((x, w, rnd.randrange(20, 34)))
        x += w - 14

    def mount(d, dx, r0, f):
        for x, w, hgt in mts:
            xs = x + dx
            d.polygon([(xs, 76 - r0), (xs + w // 2, 76 - hgt - r0), (xs + w, 76 - r0)], fill=(112, 134, 200))
            d.polygon([(xs + w // 2, 76 - hgt - r0), (xs + w, 76 - r0), (xs + w * 0.62, 76 - r0)], fill=(88, 108, 176))
            d.polygon([(xs + w // 2 - 4, 76 - hgt + 5 - r0), (xs + w // 2, 76 - hgt - r0), (xs + w // 2 + 4, 76 - hgt + 5 - r0)],
                      fill=(240, 246, 255))
    spec += make_layer(48, 76, 384, 0.2, sk, mount)
    sea = lambda r: mix((50, 120, 220), (24, 80, 190), (r - 76) / 20)

    def waves(seed):
        wr = random.Random(seed)
        pts = [(wr.randrange(0, 256), wr.randrange(0, 6)) for _ in range(40)]
        return lambda d, dx, r0, f: [d.line([(x + dx, y), (x + dx + wr.randrange(5, 10), y)], fill=(170, 220, 255)) for x, y in pts]
    spec += make_layer(76, 82, 256, 0.28, sea, waves(1), wave=True)
    spec += make_layer(82, 88, 256, 0.34, sea, waves(2), wave=True)
    spec += make_layer(88, 94, 256, 0.42, sea, waves(3), wave=True)
    hill = lambda r: mix((70, 170, 70), (40, 130, 56), (r - 94) / 40)

    def hills(d, dx, r0, f):
        for cx, rr in ((40, 26), (120, 34), (200, 24), (290, 36), (370, 28), (450, 30)):
            d.ellipse([cx - rr * 1.4 + dx, 112 - rr - r0 + 6, cx + rr * 1.4 + dx, 112 + rr * 2 - r0], fill=(52, 150, 62))
            d.ellipse([cx - rr * 1.4 + dx + 4, 112 - rr - r0 + 8, cx + rr * 0.2 + dx, 112 + rr * 2 - r0], fill=(70, 172, 76))
        for wx in (96, 292):
            d.rectangle([wx + dx, 100 - r0, wx + 9 + dx, 134 - r0], fill=(220, 236, 250))
            for yy in range(100, 134):
                if (yy + 2 * f) % 5 < 2:
                    d.line([(wx + 1 + dx, yy - r0), (wx + 8 + dx, yy - r0)], fill=(120, 190, 250))
                for sx in (2, 5, 7):
                    if (yy * 3 + sx * 5 + f * 3) % 7 == 0:
                        d.point((wx + sx + dx, yy - r0), fill=(255, 255, 255))
            d.ellipse([wx - 4 + dx, 131 - r0, wx + 13 + dx, 138 - r0], fill=(220, 240, 255))
    spec += make_layer(94, 134, 448, 0.55, hill, hills, frames=3)
    bush = lambda r: mix((34, 126, 44), (20, 92, 36), (r - 134) / 30)

    def bushes(d, dx, r0, f):
        br = random.Random(5)
        for x in range(0, 256, 18):
            rr = br.randrange(8, 15)
            d.ellipse([x + dx, 140 - rr - r0, x + 24 + dx, 140 + rr * 2 - r0], fill=(26, 112, 40))
            d.ellipse([x + dx + 3, 142 - rr - r0, x + 12 + dx, 150 - r0], fill=(52, 156, 60))
    spec += make_layer(134, 168, 256, 0.75, bush, bushes)
    spec += make_layer(168, BG_ROWS, 320, 0, lambda r: mix((110, 64, 24), (60, 30, 12), (r - 168) / 36))
    return spec


def bg_mz():
    rnd = random.Random(23)
    sky = [(0, (14, 8, 40)), (70, (66, 24, 78)), (130, (120, 40, 70))]
    sk = lambda r: grad(sky, r)
    spec = make_layer(0, 24, 320, 0, sk)

    def smoke(d, dx, r0, f):
        for x in range(0, 320, 53):
            cloud(d, x + dx, 20 - r0 + rnd.randrange(-3, 3), 0.8, col=(70, 36, 90), sh=(50, 24, 72))
    spec += make_layer(24, 46, 360, 0.06, sk, smoke)

    def pillars(d, dx, r0, f):
        for x, w in ((20, 14), (84, 20), (150, 12), (210, 18), (280, 14)):
            d.rectangle([x + dx, 52 - r0, x + w + dx, 130 - r0], fill=(52, 28, 84))
            d.rectangle([x - 3 + dx, 48 - r0, x + w + 3 + dx, 54 - r0], fill=(66, 38, 100))
            d.rectangle([x + dx, 52 - r0, x + 3 + dx, 130 - r0], fill=(70, 40, 106))
    spec += make_layer(46, 100, 320, 0.15, sk, pillars)

    def arches(d, dx, r0, f):
        for x in range(0, 256, 64):
            d.rectangle([x + dx, 90 - r0, x + 64 + dx, 134 - r0], fill=(38, 20, 62))
            d.pieslice([x + 8 + dx, 78 - r0, x + 56 + dx, 126 - r0], 180, 360, fill=(66, 30, 84))
            d.rectangle([x + 8 + dx, 102 - r0, x + 56 + dx, 134 - r0], fill=(66, 30, 84))
            d.ellipse([x + 20 + dx, 98 - r0, x + 44 + dx, 122 - r0], fill=(120, 40, 60))
    spec += make_layer(100, 134, 256, 0.32, sk, arches)
    glow = lambda r: mix((170, 40, 20), (255, 140, 30), (r - 134) / 26)

    def lava_bands(seed):
        wr = random.Random(seed)
        pts = [(wr.randrange(0, 256), wr.randrange(0, 8)) for _ in range(34)]
        return lambda d, dx, r0, f: [d.line([(x + dx, y), (x + dx + wr.randrange(5, 12), y)], fill=(255, 224, 90)) for x, y in pts]
    spec += make_layer(134, 142, 256, 0.45, glow, lava_bands(4), wave=True)
    spec += make_layer(142, 150, 256, 0.55, glow, lava_bands(5), wave=True)
    spec += make_layer(150, 160, 256, 0.68, glow, lava_bands(6), wave=True)

    def bricks(d, dx, r0, f):
        for y in range(160, BG_ROWS, 8):
            d.line([(0, y - r0), (400, y - r0)], fill=(26, 10, 40))
            for x in range(-8 + (y // 8 % 2) * 8, 320, 16):
                d.line([(x + dx, y - r0), (x + dx, y + 8 - r0)], fill=(26, 10, 40))
    spec += make_layer(160, BG_ROWS, 320, 0.9, lambda r: (70, 34, 100), bricks)
    return spec


def bg_syz():
    rnd = random.Random(31)
    sky = [(0, (6, 6, 34)), (80, (48, 24, 100)), (140, (110, 50, 140))]
    sk = lambda r: grad(sky, r)

    def stars(d, dx, r0, f):
        sr = random.Random(2)
        for _ in range(50):
            x, y = sr.randrange(0, 320), sr.randrange(0, 70)
            d.point((x + dx, y - r0), fill=(255, 255, 255) if sr.random() < 0.5 else (170, 190, 255))
        d.ellipse([236 + dx, 14 - r0, 258 + dx, 36 - r0], fill=(250, 244, 200))
        d.ellipse([242 + dx, 12 - r0, 262 + dx, 32 - r0], fill=sk(20))
    spec = make_layer(0, 56, 320, 0, sk, stars)

    def skyline(col, win, top, bot, seed, glowcol):
        sr = random.Random(seed)
        bs = []
        x = 0
        while x < 384:
            w = sr.randrange(18, 40)
            bs.append((x, w, sr.randrange(top, top + 36)))
            x += w + sr.randrange(0, 4)

        def fn(d, dx, r0, f):
            for x, w, y in bs:
                d.rectangle([x + dx, y - r0, x + w + dx, bot - r0], fill=col)
                d.rectangle([x + dx, y - r0, x + w + dx, y + 1 - r0], fill=glowcol)
                for wy in range(y + 5, bot - 4, 6):
                    for wx in range(x + 3, x + w - 3, 5):
                        if sr.random() < 0.42:
                            d.rectangle([wx + dx, wy - r0, wx + 1 + dx, wy + 2 - r0], fill=win)
        return fn
    spec += make_layer(56, 100, 384, 0.12, sk, skyline((26, 22, 74), (200, 190, 120), 60, 150, 3, (80, 70, 160)))
    spec += make_layer(100, 140, 320, 0.3, sk, skyline((44, 34, 110), (255, 220, 90), 90, 190, 4, (255, 90, 200)))

    def bokeh(d, dx, r0, f):
        for x in range(0, 256, 11):
            y = 143 + rnd.randrange(0, 20)
            col = rnd.choice(((255, 90, 200), (90, 220, 255), (255, 230, 100), (140, 255, 140)))
            d.ellipse([x + dx, y - r0, x + 3 + dx, y + 3 - r0], fill=col)
    spec += make_layer(140, 170, 256, 0.5, lambda r: mix((50, 30, 110), (20, 14, 60), (r - 140) / 30), bokeh)
    spec += make_layer(170, BG_ROWS, 320, 0, lambda r: (16, 12, 52))
    return spec


# ------------------------------------------------------------------------------------------- fonts
CHARS = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:!+-./X"


def make_font(px):
    f = ImageFont.truetype(MONO, px)
    l, t, r, b = f.getbbox("0")
    cw = int(round(f.getlength("0")))
    chh = int(b - min(t, 0)) + 2
    cols = {"white": (250, 250, 250), "yellow": (252, 220, 40), "red": (240, 50, 50), "blue": (80, 160, 255)}
    out = {c: {} for c in cols}
    for ch in CHARS:
        m = Image.new("L", (cw, chh), 0)
        d = ImageDraw.Draw(m)
        d.fontmode = "1"
        d.text((0, 0), ch, font=f, fill=255)
        for cname, rgb in cols.items():
            im = Image.new("RGBA", (cw, chh), rgb + (0,))
            im.putalpha(m)
            out[cname][ch] = run_sprite(im)
    return {"cw": cw, "ch": chh, "g": out}


# ------------------------------------------------------------------------------------------- main
def main():
    right, left = sonic_sets()
    mon = monitor_frames()
    data = {
        "sonic": right, "sonic_l": left, "life": life_icon(),
        "ring": ring_frames(), "sparkle": sparkle_frames(),
        "spring_red": spring_frames((230, 50, 50)), "spring_yel": spring_frames((250, 210, 40)),
        "spikes": spikes_sprite(), "monitor": mon, "shield": shield_frames(), "sign": sign_frames(),
        "bumper": bumper_frames(), "dust": dust_frames(), "shot": shot_frames(), "boom": explosion_frames(),
        "animal": animal_frames(),
        "moto": [run_sprite(f) for f in motobug_frames()], "moto_r": [run_sprite(flip(f)) for f in motobug_frames()],
        "crab": [run_sprite(f) for f in crab_frames()],
        "buzz": [run_sprite(f) for f in buzz_frames()], "buzz_r": [run_sprite(flip(f)) for f in buzz_frames()],
        "decor": {"ghz": {"palm": palm_frames(), "totem": [totem_sprite()], "flower": flower_frames(), "bush": [bush_sprite()]},
                  "mz": {"column": [column_sprite()], "brazier": brazier_frames()},
                  "syz": {"lamp": lamp_frames()}},
        "zones": {"ghz": zone_tiles("ghz"), "mz": zone_tiles("mz"), "syz": zone_tiles("syz")},
        "bg": {"ghz": bg_ghz(), "mz": bg_mz(), "syz": bg_syz()},
        "font": {"S": make_font(12), "L": make_font(26)},
    }
    save_bundle("g_sonic.bin", data)
    print("wrote g_sonic.bin")


if __name__ == "__main__":
    main()
