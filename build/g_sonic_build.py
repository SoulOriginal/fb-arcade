# Build-time art for the Sonic-style platformer (runs on the dev machine with PIL, writes g_sonic.bin).
#
# The game renders a native 320x216 picture and shows it at x5 (1600x1080, black side bars), so everything here is
# drawn at Mega Drive scale: a sprite row is stored as a list of opaque runs whose bytes are already expanded 5x
# horizontally (10 bytes per pixel). All colours are snapped to the Mega Drive's 8 levels per channel (steps of 32),
# which is what gives the picture its look; the game then patches runs into per-scanline byte rows without any
# per-pixel Python.
import math, random, struct
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from buildlib import save_bundle, rgb565

K = 5
FONT_MONO = "/usr/share/fonts/TTF/DejaVuSansMono-BoldOblique.ttf"
FONT_BIG = "/usr/share/fonts/TTF/DejaVuSans-BoldOblique.ttf"
_chunks = {}


def snap(rgb):
    return tuple(min(224, (v + 16) // 32 * 32) for v in rgb[:3])


def chunk(rgb, snapped=True):
    # snapped=False keeps the exact 565 colour: used for frames sliced from the owner's sheets
    rgb = snap(rgb) if snapped else tuple(rgb[:3])
    key = (rgb, snapped)
    c = _chunks.get(key)
    if c is None:
        c = _chunks[key] = struct.pack("<H", rgb565(*rgb)) * K
    return c


def img_rows(im):
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    return [b"".join(chunk(px[x, y]) for x in range(w)) for y in range(h)]


def run_sprite(im, snapped=True):
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
                buf.append(chunk(px[x, y][:3], snapped))
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



OUT = (0, 0, 96)
BL, BLD, BLL = (32, 64, 224), (32, 32, 160), (96, 128, 224)
SK, SKD = (224, 160, 128), (192, 128, 96)
RD, RDD = (224, 32, 0), (160, 0, 0)
WH = (224, 224, 224)
GRN = (0, 160, 0)
GOLD, GOLDD, GOLDL = (224, 192, 0), (160, 96, 0), (224, 224, 128)


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


def arm(c, sh, hand):
    c.line(sh, hand, 2.6, SK)
    c.ell(hand[0], hand[1], 2.6, 2.6, (245, 245, 250))


def leg(c, hip, ankle):
    c.line(hip, ankle, 3.6, BL)
    shoe(c, *ankle)


def head_front(c, hx, hy, mouth=False):
    # Facing the viewer: used by the impatient "waiting" animation.
    for s in (-1, 1):
        c.poly([(hx + s * 5, hy - 8), (hx + s * 11, hy - 2), (hx + s * 19, hy - 9)], BL)
        c.poly([(hx + s * 8, hy - 3), (hx + s * 9, hy + 6), (hx + s * 20, hy + 3)], BL)
    c.poly([(hx - 3, hy - 8), (hx, hy - 15), (hx + 3, hy - 8)], BL)
    c.ell(hx, hy, 9.6, 9.2, BL)
    c.ell(hx, hy + 4.5, 5.6, 4.4, SK)
    for s in (-1, 1):
        c.ell(hx + s * 3.3, hy - 2.4, 3.3, 4.8, WH)
        c.ell(hx + s * 3.0, hy - 1.6, 1.4, 2.6, GRN, out=None)
        c.ell(hx + s * 3.0, hy - 1.5, 0.8, 1.6, OUT, out=None)
    c.ell(hx, hy + 2.6, 1.6, 1.3, OUT, out=None)
    if mouth:
        c.ell(hx, hy + 7, 2.2, 1.6, RDD, out=None)
    else:
        c.line((hx - 3, hy + 7), (hx + 3, hy + 7), 0.5, OUT, out=None)


def shoe(c, ax, ay):
    c.ell(ax + 1.3, ay - 0.6, 5.8, 3.3, RD)
    c.rect(ax - 1.8, ay - 3.0, ax + 0.8, ay + 0.6, WH, out=None)
    c.rect(ax - 0.9, ay - 2.2, ax + 0.1, ay - 0.6, GOLD, out=None)
    c.line((ax - 4.0, ay + 2.0), (ax + 6.4, ay + 2.0), 0.9, (224, 224, 224), out=None)


def torso(c, tx, ty):
    c.ell(tx, ty, 5.8, 7.8, BL)
    c.ell(tx + 2.2, ty + 1.6, 3.2, 5.2, SK, out=None)


def sonic_frame(kind, ph=0.0, who="sonic"):
    c = C(40, 44)
    if kind == "glide":
        return finish(glide_frame(c, ph), who)
    if kind == "climb":
        return finish(climb_frame(c, ph), who)
    if kind == "ball":
        cx, cy = 20, 29.5
        for k in range(5):
            a = ph + k * 2 * math.pi / 5
            c.poly([(cx + 9 * math.cos(a - 0.35), cy + 9 * math.sin(a - 0.35)),
                    (cx + 9 * math.cos(a + 0.35), cy + 9 * math.sin(a + 0.35)),
                    (cx + 14.4 * math.cos(a), cy + 14.4 * math.sin(a))], BLD)
        c.ell(cx, cy, 12, 12, BL)
        for k in range(3):
            a0 = math.degrees(ph) * 2 + k * 120
            c.d.pieslice([(cx - 10) * 8, (cy - 10) * 8, (cx + 10) * 8, (cy + 10) * 8], a0, a0 + 50, fill=WH)
        c.ell(cx, cy, 3.5, 3.5, BLL, out=None)
        return finish(down(c.im, 34, 38), who)
    hx, hy, tx, ty = 22, 15, 19.5, 27
    hip = (19.5, 33)
    eye, mouth, trail = "open", False, 0.0
    far_leg, near_leg = (15.5, 40.6), (23.8, 40.6)
    far_arm, near_arm = (14.2, 33), (25, 33.5)
    blur = False
    ghost = None
    front = False
    if kind == "walk":
        s, co = math.sin(ph), math.cos(ph)
        hx, hy, tx, ty, trail = 23, 15.5, 20.5, 27.3, 0.4
        hip = (20, 33)
        far_leg = (20 - 7 * s, 40.6 - 4 * max(0, -co))
        near_leg = (20 + 7 * s, 40.6 - 4 * max(0, co))
        far_arm, near_arm = (20 + 6 * s, 33), (20 - 6 * s, 33)
        hy += 0.6 * abs(math.sin(2 * ph))
    elif kind == "run":
        # jog: clear forward lean, long scissor stride, legs smeared by a lighter red ghost between them
        s, co = math.sin(ph), math.cos(ph)
        hx, hy, tx, ty, trail = 28, 18, 23, 29, 1.4
        hip = (21.5, 34.5)
        far_leg = (21.5 - 11 * s, 40.4 - 7 * max(0, -co))
        near_leg = (21.5 + 11 * s, 40.4 - 7 * max(0, co))
        far_arm, near_arm = (8, 28 + 2 * s), (10, 31 - 2 * s)
        ghost = ((far_leg[0] + near_leg[0]) / 2, 39.5)
    elif kind == "blur":
        # full-speed run: legs become a figure-8 wheel of red loops, body leans hard forward, spines stream back
        hx, hy, tx, ty, trail = 31, 21, 24.5, 31, 2.6
        hip = (22, 35)
        far_arm, near_arm = (7, 32), (9, 34.5)
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
        far_arm, near_arm = (7.5, 24), (32, 24)
        eye, mouth = "x", True
    elif kind == "spring":
        far_leg, near_leg = (18, 40.6), (21.8, 40.6)
        far_arm, near_arm = (17, 8.5), (26, 9.5)
        mouth = True
    elif kind == "wave":
        near_arm = (28.5 + 1.5 * math.sin(ph), 21 - 1.5 * abs(math.sin(ph)))
    elif kind == "wait":
        # frame 0: looks at the viewer, hand on hip; frames 1 and 2: foot taps
        front = True
        hx, hy, tx = 20, 15, 19
        near_arm = (27, 32)
        far_arm = (12, 32)
        if ph == 1:
            near_leg = (24.5, 38.6)
    elif kind == "fly":
        far_leg, near_leg = (18, 40.6), (21.8, 40.6)
        far_arm, near_arm = (16, 36), (25, 36)
        hip = (19.5, 33)
    elif kind != "idle":
        raise ValueError(kind)
    if who == "tails":
        tails_behind(c, tx, ty, ph, kind == "fly")
    if front:
        head_front(c, hx, hy, False)
    elif who == "tails":
        head_tails(c, hx, hy, eye, mouth, trail)
    elif who == "knuckles":
        head_knux(c, hx, hy, eye, mouth, trail)
    else:
        head(c, hx, hy, eye, mouth, trail)
    arm(c, (tx - 1, ty - 3), far_arm)
    if blur:
        for k in range(3):
            c.line((1 + k * 2, 36 + k * 2), (9 + k * 2, 36 + k * 2), 0.7, (160, 192, 224), out=None)
        for dxp, dyp in ((3, 41), (7, 39.5)):
            c.ell(dxp, dyp, 2.2, 1.6, (224, 224, 192), out=None)
        pts = [(hip[0] - 1 + 9.5 * math.sin(t * math.pi / 12), 39.2 + 4.6 * math.sin(t * math.pi / 6)) for t in range(25)]
        f = int(round(ph / 2.1))
        for i, (q0, q1) in enumerate(zip(pts, pts[1:])):
            c.line(q0, q1, 3.0, (RD, RDD, (224, 128, 96))[(i // 2 + f) % 3])
        for i, (q0, q1) in enumerate(zip(pts, pts[1:])):
            if (i // 2 + f) % 3 == 0:
                c.line(q0, q1, 1.0, WH, out=None)
        for k in range(2):
            t = ph * 1.3 + k * math.pi
            sx, sy = hip[0] - 1 + 9.5 * math.sin(t), 39.2 + 4.6 * math.sin(2 * t)
            c.ell(sx + 0.8, sy, 3.6, 2.4, RD)
            c.rect(sx - 1.4, sy - 2.6, sx + 0.4, sy + 1.2, WH, out=None)
            c.rect(sx - 0.8, sy - 1.8, sx - 0.1, sy - 0.4, GOLD, out=None)
    else:
        if ghost:
            c.ell(ghost[0], ghost[1], 8, 3.6, (224, 96, 64), out=None)
        leg(c, hip, far_leg)
        leg(c, hip, near_leg)
    torso(c, tx, ty)
    if kind == "wait":
        arm(c, (tx + 1.5, ty - 3), (tx + 8, ty + 2))
        c.line((tx + 8, ty + 2), near_arm, 2.4, SK)
        c.ell(near_arm[0], near_arm[1], 2.6, 2.6, (224, 224, 224))
    else:
        arm(c, (tx + 1.5, ty - 3), near_arm)
    if who == "knuckles":
        for hand in (far_arm, near_arm):
            for dxs in (-1.2, 1.2):
                c.poly([(hand[0] + dxs - 0.9, hand[1] - 2), (hand[0] + dxs, hand[1] - 4.6), (hand[0] + dxs + 0.9, hand[1] - 2)],
                       (224, 224, 224), out=OUT, ow=0.3)
        c.poly([(tx - 3, ty - 4), (tx + 1, ty - 1), (tx + 4, ty - 4), (tx + 1, ty - 6.5)], (224, 224, 224), out=None)
    return finish(down(c.im, 34, 38), who)


# ---------------------------------------------------------------------------------------- characters
# Tails and Knuckles have no sheet: they reuse the hedgehog pose skeleton (same hip, arm and leg positions) with their
# own head, tails and palette. Frames are drawn in Sonic's colours and recoloured per character after downscaling.
PAL = {
    "dark": {"body": (40, 40, 48), "shade": (16, 16, 24), "light": (224, 32, 0), "line": (0, 0, 0),
             "skin": (224, 160, 128), "shoe": None},
    "tails": {"body": (224, 128, 0), "shade": (160, 64, 0), "light": (224, 192, 64), "line": (96, 32, 0),
              "skin": (224, 224, 224), "shoe": None},
    "knuckles": {"body": (224, 32, 0), "shade": (160, 0, 0), "light": (224, 96, 64), "line": (64, 0, 0),
                 "skin": (224, 160, 128), "shoe": ((224, 192, 0), (160, 128, 0))},
}


def finish(im, who):
    if who == "sonic":
        return im
    pal = PAL[who]
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if not a:
                continue
            if b > r + 24 and b >= g - 10:
                lum = (r + g + b) / 3
                col = pal["line"] if lum < 48 else pal["shade"] if lum < 92 else pal["body"] if lum < 132 else pal["light"]
                px[x, y] = col + (255,)
            elif r > 130 and g < 90 and b < 70:
                if pal["shoe"]:
                    px[x, y] = (pal["shoe"][0] if r > 190 else pal["shoe"][1]) + (255,)
            elif r > 170 and 100 < g < 200 and b < 170 and r - b > 50 and g > b + 15:
                px[x, y] = pal["skin"] + (255,)
    return im


def tails_behind(c, tx, ty, ph, fly):
    base = (tx - 3, ty + 7)
    if fly:
        # the two tails spin like a rotor behind the hanging body
        cx, cy = tx - 2, ty + 3
        for k in range(2):
            a = ph * 1.7 + k * 1.57
            ry = 1.6 + 3.8 * abs(math.sin(a))
            c.ell(cx, cy - 4 * k, 13, ry, BL)
        for sx in (-12.5, 12.5):
            c.ell(cx + sx, cy, 2.6, 2.6, WH)
        return
    for k, s in enumerate((0.55, -0.35)):
        a = s + 0.35 * math.sin(ph * 0.5 + k)
        mid = (base[0] - 8 * math.cos(a), base[1] + 4 * math.sin(a) + 1)
        tip = (base[0] - 16 * math.cos(a), base[1] + 8 * math.sin(a) + 1)
        c.line(base, mid, 5.4, BL)
        c.line(mid, tip, 4.4, BL)
        c.ell(tip[0], tip[1], 3.0, 3.0, WH)


def head_tails(c, hx, hy, eye="open", mouth=False, trail=0.0):
    c.poly([(hx - 6, hy - 6), (hx - 15, hy - 3 + trail * 2), (hx - 7, hy + 3)], BL)
    c.poly([(hx - 7, hy + 2), (hx - 14, hy + 7 + trail * 2), (hx - 3, hy + 7)], BL)
    c.poly([(hx - 7, hy - 7), (hx - 6, hy - 17), (hx - 0.5, hy - 8)], BL)
    c.poly([(hx - 1, hy - 8), (hx + 3, hy - 16), (hx + 6, hy - 6)], BL)
    c.poly([(hx - 5.5, hy - 9), (hx - 5.5, hy - 14), (hx - 2.5, hy - 9)], SK, out=None)
    c.ell(hx, hy, 9.6, 9.2, BL)
    c.poly([(hx + 1, hy + 7), (hx + 5, hy + 12), (hx + 10, hy + 6)], WH)
    c.ell(hx + 6, hy + 3.8, 5.4, 4.4, SK)
    c.ell(hx + 10.8, hy + 2, 1.6, 1.3, OUT, out=None)
    c.ell(hx + 3.4, hy - 2.4, 4.0, 5.2, WH)
    if eye == "open":
        c.ell(hx + 4.8, hy - 2.0, 1.8, 2.8, OUT, out=None)
        c.ell(hx + 4.4, hy - 3.4, 0.6, 0.7, WH, out=None)
    else:
        c.line((hx + 1.4, hy - 5), (hx + 5.6, hy), 0.7, OUT, out=None)
        c.line((hx + 5.6, hy - 5), (hx + 1.4, hy), 0.7, OUT, out=None)
    if mouth:
        c.ell(hx + 7.6, hy + 7.2, 2.0, 1.7, RDD, out=None)
    else:
        c.line((hx + 5.5, hy + 7), (hx + 9.5, hy + 6.4), 0.5, OUT, out=None)


def head_knux(c, hx, hy, eye="open", mouth=False, trail=0.0):
    for dy, ln in ((-6, 15), (-1, 17), (4, 14)):
        c.poly([(hx - 5, hy + dy - 3), (hx - 6, hy + dy + 3), (hx - ln - trail * 2, hy + dy + 2 + trail)], BL)
    c.poly([(hx - 3, hy - 8), (hx + 1, hy - 14), (hx + 5, hy - 7)], BL)
    c.ell(hx, hy, 9.6, 9.2, BL)
    c.ell(hx + 5.8, hy + 3.8, 5.4, 4.4, SK)
    c.ell(hx + 10.8, hy + 2, 1.7, 1.4, OUT, out=None)
    c.ell(hx + 3.4, hy - 2.2, 4.0, 4.6, WH)
    if eye == "open":
        c.ell(hx + 4.8, hy - 1.8, 1.7, 2.6, GRN, out=None)
        c.ell(hx + 5.0, hy - 1.7, 0.9, 1.5, OUT, out=None)
        c.line((hx + 0.5, hy - 6), (hx + 7, hy - 3.6), 1.1, OUT, out=None)
    else:
        c.line((hx + 1.4, hy - 5), (hx + 5.6, hy), 0.7, OUT, out=None)
        c.line((hx + 5.6, hy - 5), (hx + 1.4, hy), 0.7, OUT, out=None)
    if mouth:
        c.ell(hx + 7.4, hy + 7, 2.0, 1.7, RDD, out=None)
    else:
        c.line((hx + 5.5, hy + 6.8), (hx + 9.5, hy + 6.2), 0.5, OUT, out=None)


def glide_frame(c, ph):
    # Knuckles gliding: body nearly horizontal, arms stretched forward, legs trailing
    hx, hy = 31, 20
    c.poly([(hx - 5, hy - 6), (hx - 15, hy - 3), (hx - 6, hy + 2)], BL)
    c.poly([(hx - 6, hy + 2), (hx - 16, hy + 5), (hx - 5, hy + 7)], BL)
    for hand in ((38, 25 + math.sin(ph)), (36, 17 - math.sin(ph))):
        c.line((26, 24), hand, 2.6, SK)
        c.ell(hand[0], hand[1], 2.6, 2.6, WH)
    c.line((16, 27), (7, 30 + math.sin(ph) * 2), 3.4, BL)
    c.line((17, 28), (6, 34 - math.sin(ph) * 2), 3.4, BL)
    shoe(c, 5, 31)
    shoe(c, 4, 36)
    c.ell(21, 25, 9, 5.5, BL)
    c.ell(22, 27, 5, 3, SK, out=None)
    head_knux(c, hx, hy, "open", False, 0.8)
    return down(c.im, 34, 38)


def climb_frame(c, ph):
    # Knuckles climbing a wall to his right: hands high on the wall, legs bent below
    up = math.sin(ph)
    hx, hy = 19, 12
    c.poly([(hx - 5, hy - 4), (hx - 15, hy - 1), (hx - 6, hy + 3)], BL)
    c.line((20, 22), (14, 33 + up), 3.4, BL)
    c.line((20, 22), (24, 32 - up), 3.4, BL)
    shoe(c, 13, 35 + up)
    shoe(c, 25, 34 - up)
    for hand in ((28, 5 + 2 * up), (29, 15 - 2 * up)):
        c.line((22, 18), hand, 2.6, SK)
        c.ell(hand[0], hand[1], 2.6, 2.6, WH)
    c.ell(20, 22, 6, 8, BL)
    c.ell(22, 23, 3, 5, SK, out=None)
    head_knux(c, hx, hy, "open", False, 0.2)
    return down(c.im, 34, 38)


def anchor_of(im):
    # Frames are anchored at their feet: the bottom edge, and the horizontal centre of mass of the upper body so
    # that walk cycles with wide strides do not make the body jitter.
    w, h = im.size
    px = im.load()
    xs = [x for y in range(max(1, int(h * 0.6))) for x in range(w) if px[x, y][3] > 0]
    ax = int(round(sum(xs) / len(xs))) if xs else w // 2
    return ax, h


def frame5(im, snapped, ax=None, ay=None):
    if ax is None:
        ax, ay = anchor_of(im)
    w, h, rows = run_sprite(im, snapped)
    return (w, h, rows, ax, ay)


def both_facings(frames_rgba, snapped):
    # [(RGBA image, ax, ay)] -> (right-facing frames, left-facing frames), mirrored about the anchor
    right, left = [], []
    for im, ax, ay in frames_rgba:
        right.append(frame5(im, snapped, ax, ay))
        left.append(frame5(flip(im), snapped, im.width - 1 - ax, ay))
    return right, left


def with_anchor(im):
    ax, ay = anchor_of(im)
    return (im, ax, ay)


def clean_sonic_fringe(im):
    # keying residue: greenish dark pixels around the outline become outline-coloured
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a and g > r + 8 and g > b + 8 and max(r, g, b) < 130:
                px[x, y] = (10, 10, 30, 255)
    return im


SONIC_MAP = {"idle": [0], "wait": [6, 7, 8, 9], "walk": [14, 15, 16, 17, 18, 19, 20, 21], "run": [22, 23, 24, 25],
             "blur": [74, 75, 76, 77], "ball": [86, 87, 88, 89], "skid": [98, 99, 100], "spring": [97],
             "hurt": [127, 128], "death": [132], "wave": [10], "balance": [108, 109, 110, 111], "charge": [4]}
DARK_MAP = {"idle": [0], "wait": [10, 11, 12, 11], "walk": [16, 17, 18, 19, 20, 21, 22, 15], "run": [24, 25, 26, 27],
            "blur": [34, 35, 36, 37], "ball": [120, 121, 122, 123], "skid": [51, 52, 53], "spring": [80],
            "hurt": [103], "death": [74], "wave": [12], "balance": [4], "charge": [124, 125, 126, 127]}


def sheet_character(kind, mapping):
    # Returns {"R": {pose: [frame5]}, "L": {...}} built from the owner's sheet, or None when the sheet is missing.
    try:
        import g_sonic_sheets
    except ImportError:
        return None
    sliced = g_sonic_sheets.slice_sheet(kind)
    if sliced is None:
        return None
    frames = sliced[0]
    out = {"R": {}, "L": {}, "_snapped": False}
    for pose, idxs in mapping.items():
        ims = []
        for i in idxs:
            im = frames[i].copy()
            if kind == "sonic":
                clean_sonic_fringe(im)
            ims.append(with_anchor(im))
        out["R"][pose], out["L"][pose] = both_facings(ims, False)
        if pose == "blur":
            out["_blur"] = ims
        if pose == "idle":
            top = ims[0][0].crop((0, 0, ims[0][0].width, min(ims[0][0].height, 17)))
            out["icon"] = frame5(top, False, 0, 0)
    return out


def procedural_character(who):
    kinds = {"idle": [("idle", 0)], "wait": [("wait", i) for i in range(3)],
             "walk": [("walk", i * math.pi / 3) for i in range(6)], "run": [("run", i * math.pi / 2) for i in range(4)],
             "blur": [("blur", i * 2.1) for i in range(3)], "ball": [("ball", i * math.pi / 5) for i in range(4)],
             "skid": [("skid", 0), ("skid", 1)], "hurt": [("hurt", 0)], "death": [("hurt", 0)],
             "spring": [("spring", 0)], "wave": [("wave", i * 1.4) for i in range(3)],
             "balance": [("idle", 0)], "charge": [("ball", i * math.pi / 5) for i in range(4)]}
    if who == "tails":
        kinds["fly"] = [("fly", i * 1.3) for i in range(4)]
    if who == "knuckles":
        kinds["glide"] = [("glide", i * 1.5) for i in range(2)]
        kinds["climb"] = [("climb", i * math.pi) for i in range(2)]
    out = {"R": {}, "L": {}, "_snapped": True}
    for pose, specs in kinds.items():
        ims = [(sonic_frame(k, ph, who), 17, 38) for k, ph in specs]
        out["R"][pose], out["L"][pose] = both_facings(ims, True)
        if pose == "blur":
            out["_blur"] = ims
    out["icon"] = frame5(head_icon_who(who), True, 0, 0)
    return out


def head_icon_who(who):
    c = C(40, 44)
    fn = {"tails": head_tails, "knuckles": head_knux}.get(who, head)
    fn(c, 22, 15, "open", False, 0)
    return finish(down(c.im.crop((6 * 8, 0, 34 * 8, 28 * 8)), 16, 16), who)


def rotated_set(char, deg_steps=16, nframes=2):
    # Pre-rotated copies of the full-speed run frames for loops: rotation is about the feet anchor, so the game just
    # places the anchor on the track and picks the frame for the current angle.
    frames = char["_blur"][:nframes]
    out = []
    for k in range(deg_steps):
        row = []
        for im, ax, ay in frames:
            S2 = 2 * max(im.size) + 8
            cv = Image.new("RGBA", (S2, S2), (0, 0, 0, 0))
            cv.paste(im, (S2 // 2 - ax, S2 // 2 - ay), im)
            r = cv.rotate(k * 360 / deg_steps, resample=Image.NEAREST, center=(S2 // 2, S2 // 2))
            bb = r.getbbox()
            r = r.crop(bb)
            row.append(frame5(r, char["_snapped"], S2 // 2 - bb[0], S2 // 2 - bb[1]))
        out.append(row)
    return out


def build_chars():
    chars = {}
    chars["sonic"] = sheet_character("sonic", SONIC_MAP) or procedural_character("sonic")
    chars["shadow"] = sheet_character("dark", DARK_MAP) or procedural_character("dark")
    chars["tails"] = procedural_character("tails")
    chars["knuckles"] = procedural_character("knuckles")
    src = {}
    for name, ch in chars.items():
        ch["rot"] = rotated_set(ch)
        src[name] = "sheet" if not ch["_snapped"] else "procedural"
        del ch["_blur"], ch["_snapped"]
    return chars, src


def loop_sprite(R=40, T=12, S=24):
    # A checkered earth tube (spiral by S px so entry and exit are apart); the part below the ground line is cut away.
    W = S + 2 * R + 2 * T
    H = 2 * R + T
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = im.load()
    for k in range(0, 720):
        phi = k * math.pi / 360
        cx = T + R + S * phi / (2 * math.pi)
        for rr in range(R - 1, R + T + 1):
            x = int(round(cx + rr * math.sin(phi)))
            y = int(round(R + T + rr * math.cos(phi)))
            if 0 <= x < W and 0 <= y < H:
                u = int(phi * R / 12)
                v = (rr - R) // 6
                if rr < R + 1 or rr >= R + T:
                    col = (32, 0, 0)
                elif rr == R + 1:
                    col = (224, 160, 32)
                else:
                    col = (192, 96, 0) if (u + v) % 2 else (128, 64, 0)
                    if (u * 7 + rr * 3) % 17 == 0:
                        col = (96, 32, 0)
                px[x, y] = col + (255,)
    for y in range(H):
        for x in range(W):
            if px[x, y][3] and y > H - 3:
                px[x, y] = (0, 0, 0, 0)
    return run_sprite(im)


def log_sprite():
    im = Image.new("RGBA", (12, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 1, 11, 8], fill=(160, 96, 0), outline=(64, 32, 0))
    d.line([(1, 2), (10, 2)], fill=(224, 160, 32))
    d.line([(1, 7), (10, 7)], fill=(96, 48, 0))
    d.point((5, 4), fill=(96, 48, 0))
    return run_sprite(im)


def flash_frames():
    out = []
    for r in (6, 12, 19, 26):
        im = Image.new("RGBA", (56, 56), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([28 - r, 28 - r, 28 + r, 28 + r], outline=(224, 224, 224), width=3)
        d.ellipse([28 - r + 3, 28 - r + 3, 28 + r - 3, 28 + r - 3], outline=(224, 32, 0), width=2)
        out.append(run_sprite(im))
    return out


def head_icon(size):
    c = C(40, 44)
    head(c, 22, 15, "open", False, 0)
    return down(c.im.crop((6 * 8, 0, 34 * 8, 28 * 8)), size, size)


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


def spikes_sprite():
    c = C(32, 16)
    for i in range(4):
        x = i * 8
        c.poly([(x + 1, 14), (x + 4, 0.8), (x + 7, 14)], (222, 226, 238), out=(40, 44, 70))
        c.line((x + 4, 2), (x + 4, 13), 0.7, (150, 156, 180), out=None)
    c.rect(0, 13.5, 32, 16, (80, 84, 110))
    return run_sprite(c.done())


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
        c.ell(6, 12, 4.2, 4.6, (160, 160, 192))
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


def spring_frames(top):
    out = []
    for h in (14, 7):
        c = C(28, 16)
        c.rect(2, 13, 26, 16, (128, 128, 160))
        n = 3
        for i in range(n):
            y1 = 13 - i * (h - 4) / n
            y2 = 13 - (i + 1) * (h - 4) / n
            ym = (y1 + y2) / 2
            c.line((6, y1), (22, ym), 2.0, (224, 224, 224))
            c.line((22, ym), (6, y2), 2.0, (160, 160, 192))
        c.rect(1, 16 - h - 1, 27, 16 - h + 3, top)
        out.append(run_sprite(c.done()))
    return out


def item_icon(kind):
    c = C(14, 14)
    if kind == "ring":
        c.ell(7, 7, 5.5, 5.5, GOLD, out=GOLDD)
        c.hole(7, 7, 2.8, 2.8)
    elif kind == "shield":
        c.ell(7, 7, 6, 6, (32, 96, 224), out=(160, 192, 224))
        c.ell(5.4, 5, 1.6, 1.6, WH, out=None)
    elif kind == "shoes":
        c.ell(7, 8.5, 5.5, 3.2, RD, out=OUT)
        c.rect(5, 5.5, 7, 9, WH, out=None)
        c.poly([(1, 4), (6, 2), (5, 6)], WH, out=(160, 192, 224), ow=0.4)
    elif kind == "invinc":
        c.poly([(7, 0.5), (8.7, 5.3), (13.5, 7), (8.7, 8.7), (7, 13.5), (5.3, 8.7), (0.5, 7), (5.3, 5.3)],
               (224, 224, 128), out=(224, 96, 128), ow=0.5)
    else:
        return head_icon(14)
    return down(c.im, 14, 14)


ITEMS = ("ring", "shield", "shoes", "invinc", "life")


def monitor_frames():
    out = {}
    for kind in ITEMS:
        fr = []
        icon = item_icon(kind)
        for lit in (0, 1):
            c = C(32, 32)
            c.rect(1, 2, 31, 30, (160, 160, 192), out=(32, 32, 96))
            c.rect(3.5, 4.5, 28.5, 24.5, (0, 0, 0), out=(96, 96, 128))
            c.rect(2, 26, 30, 31, (96, 96, 128), out=None)
            im = down(c.im, 32, 32)
            px = im.load()
            for y in range(6, 24):
                for x in range(5, 27):
                    if (y + x * 0 + lit) % 4 == 0:
                        px[x, y] = (32, 32, 160, 255)
            im.paste(icon, (9, 8), icon)
            fr.append(run_sprite(im))
        out[kind] = fr
    c = C(32, 32)
    c.rect(1, 2, 31, 30, (128, 128, 160), out=(32, 32, 96))
    c.rect(3.5, 4.5, 28.5, 24.5, (32, 32, 32), out=(64, 64, 96))
    c.rect(2, 26, 30, 31, (96, 96, 128), out=None)
    out["broken"] = run_sprite(c.done())
    out["icons"] = {k: run_sprite(item_icon(k)) for k in ITEMS}
    return out


def sign_frames():
    out = []
    for kind, w in (("evil", 30), ("edge", 5), ("back", 30), ("edge", 5), ("goal", 30)):
        c = C(32, 48)
        c.rect(14.5, 20, 17.5, 47, (160, 160, 192))
        c.ell(16, 46, 5, 2.4, (96, 96, 128))
        x0, x1 = 16 - w / 2, 16 + w / 2
        if kind == "edge":
            c.rect(x0, 1, x1, 22, (224, 224, 224))
        else:
            col = {"evil": (224, 224, 224), "back": (160, 160, 192), "goal": (32, 64, 224)}[kind]
            c.rect(x0, 1, x1, 22, col, out=(224, 96, 0), ow=1.2)
            if kind == "evil":
                c.ell(16, 11.5, 8.5, 8, SK)
                for sx in (-3.4, 3.4):
                    c.ell(16 + sx, 9, 2.8, 2.8, (160, 160, 192))
                    c.ell(16 + sx, 9, 1.1, 1.1, OUT, out=None)
                c.poly([(7, 13), (16, 11.5), (25, 13), (22, 17), (16, 14.5), (10, 17)], (160, 64, 0), out=OUT, ow=0.4)
            elif kind == "back":
                for rx in (x0 + 3, x1 - 3):
                    for ry in (4, 19):
                        c.ell(rx, ry, 1, 1, (96, 96, 128), out=None)
            else:
                for s in (-1, 1):
                    c.poly([(16 + s * 4, 4), (16 + s * 11, 7), (16 + s * 5, 10)], BLL, out=OUT, ow=0.4)
                c.ell(16, 12, 8, 8, BL, out=OUT, ow=0.5)
                c.ell(19, 14.5, 5, 3.6, SK, out=None)
                c.ell(18.5, 9.5, 3, 3.6, WH, out=OUT, ow=0.4)
                c.ell(19.5, 9.8, 1.2, 1.8, GRN, out=None)
        out.append(run_sprite(c.done()))
    return out


def puff_frames():
    out = []
    for r in (2, 3, 4):
        c = C(10, 10)
        c.ell(5, 5, r, r, (192, 192, 192), out=None)
        c.ell(4, 4, max(1, r - 2), max(1, r - 2), (224, 224, 224), out=None)
        out.append(run_sprite(c.done()))
    return out


def caterkiller_frames():
    out = []
    for f in range(2):
        c = C(40, 22)
        for i in range(4):
            x = 8 + i * 8.5
            y = 14 - (2.2 if (i + f) % 2 else 0)
            c.poly([(x - 2, y - 4), (x, y - 9), (x + 2, y - 4)], (224, 224, 160), out=OUT, ow=0.4)
            c.ell(x, y, 5.2, 5.2, (160, 32, 160))
            c.ell(x - 1.4, y - 1.6, 1.7, 1.7, (224, 128, 224), out=None)
        c.ell(37, 13, 4.6, 4.6, (224, 192, 0))
        c.ell(36, 11.5, 1.4, 1.4, WH, out=OUT, ow=0.3)
        c.ell(36.4, 11.7, 0.6, 0.6, OUT, out=None)
        out.append(c.done())
    return out


def roller_frames():
    out = []
    for f in range(2):
        c = C(28, 24)
        c.ell(14, 13, 10.5, 10.5, (32, 96, 224))
        for k in range(4):
            a = f * 0.8 + k * math.pi / 2
            c.line((14 + 3 * math.cos(a), 13 + 3 * math.sin(a)), (14 + 9 * math.cos(a), 13 + 9 * math.sin(a)), 1.6, (160, 192, 224), out=None)
        c.ell(14, 13, 3, 3, (224, 32, 0), out=OUT, ow=0.4)
        c.ell(6, 9, 3.4, 3.4, (224, 224, 224))
        c.ell(5.3, 9, 1.2, 1.2, OUT, out=None)
        out.append(c.done())
    return out


def chopper_frames():
    out = []
    for f in range(2):
        c = C(18, 26)
        c.poly([(9, 24), (3, 17), (15, 17)], (224, 32, 0))
        c.ell(9, 12, 6.5, 9, (224, 32, 0))
        c.ell(9, 15, 4.2, 5, (224, 160, 96), out=None)
        c.ell(7, 6.5, 2.4, 2.4, WH, out=OUT, ow=0.4)
        c.ell(6.6, 6.7, 1, 1, OUT, out=None)
        my = 3 if f == 0 else 1
        c.poly([(3, my + 3), (9, 0.5 + my), (15, my + 3), (13, my + 5.5), (9, my + 4), (5, my + 5.5)], (224, 224, 224), out=OUT, ow=0.5)
        c.poly([(1, 18), (4, 15), (5, 21)], (160, 0, 0), out=OUT, ow=0.4)
        c.poly([(17, 18), (14, 15), (13, 21)], (160, 0, 0), out=OUT, ow=0.4)
        out.append(run_sprite(c.done()))
    return out


# ------------------------------------------------------------------------------------------- decor
def palm_sprite(trunk, f, seed):
    # Drawn pixel by pixel with hard edges, like the original's palms: a segmented orange trunk and angular fronds.
    W = 112
    top = 58
    h = trunk + top
    im = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = 56
    for y in range(h - 1, top, -1):
        t = (h - y) / trunk
        x = cx + int(round(3 * math.sin(t * 1.6 + seed)))
        d.line([(x - 3, y), (x + 3, y)], fill=(224, 128, 0))
        d.point((x - 3, y), fill=(224, 192, 64))
        d.point((x + 3, y), fill=(128, 64, 0))
        d.point((x + 2, y), fill=(160, 96, 0))
        if y % 8 == 0:
            d.line([(x - 3, y), (x + 3, y)], fill=(96, 32, 0))
        elif y % 8 == 1:
            d.line([(x - 1, y), (x + 1, y)], fill=(0, 160, 0))
    kx, ky = cx + int(round(3 * math.sin(trunk / trunk * 1.6 + seed))), top
    d.ellipse([kx - 7, ky - 6, kx + 7, ky + 6], fill=(128, 64, 0), outline=(32, 0, 0))
    for i in range(-6, 7, 3):
        d.line([(kx + i, ky - 5), (kx + i + 2, ky + 5)], fill=(96, 32, 0))
    sway = 3 * (f * 2 - 1)
    for deg, ln in ((185, 46), (212, 52), (242, 46), (298, 46), (328, 52), (355, 46), (155, 30), (25, 30)):
        a = math.radians(deg)
        dx, dy = math.cos(a), math.sin(a)
        side = 1 if dx > 0 else -1
        tipx = kx + ln * dx + sway * side * 0.6
        tipy = ky + ln * dy * 0.45 + 24 + sway * 0.3
        mx, my = kx + ln * 0.5 * dx, ky + ln * 0.5 * dy * 0.8 - 11
        lx, ly = kx + ln * 0.55 * dx, ky + ln * 0.55 * dy * 0.6 + 9
        d.polygon([(kx, ky), (mx, my), (tipx, tipy), (lx, ly)], fill=(64, 160, 0))
        d.polygon([(kx, ky), (lx, ly), (tipx, tipy)], fill=(0, 96, 0))
        d.line([(kx, ky), (mx, my), (tipx, tipy)], fill=(128, 224, 0))
        d.line([(mx, my + 1), (tipx, tipy)], fill=(224, 224, 224))
    return run_sprite(im)


def flower_sprite():
    im = Image.new("RGBA", (40, 44), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([19, 18, 21, 43], fill=(0, 128, 0))
    for s in (-1, 1):
        for k, (ln, hh) in enumerate(((16, 8), (11, 14))):
            d.polygon([(20, 43 - k * 4), (20 + s * ln, 43 - hh - k * 6), (20 + s * 2, 38 - k * 4)], fill=(64, 160, 0), outline=(0, 96, 0))
    d.ellipse([9, 2, 31, 24], fill=(128, 96, 224), outline=(96, 64, 192))
    d.ellipse([12, 5, 28, 21], fill=(160, 128, 224))
    d.ellipse([16, 9, 24, 17], fill=(128, 224, 0), outline=(0, 128, 0))
    return run_sprite(im)


def sunflower_frames():
    out = []
    for f in range(2):
        im = Image.new("RGBA", (34, 50), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([16, 26, 18, 49], fill=(0, 128, 0))
        for s in (-1, 1):
            d.polygon([(17, 46), (17 + s * 14, 40), (17 + s * 2, 40)], fill=(64, 160, 0), outline=(0, 96, 0))
        for k in range(12):
            a = k * math.pi / 6 + f * 0.26
            pts = [(17 + 8 * math.cos(a - 0.25), 16 + 8 * math.sin(a - 0.25)), (17 + 16 * math.cos(a), 16 + 16 * math.sin(a)),
                   (17 + 8 * math.cos(a + 0.25), 16 + 8 * math.sin(a + 0.25))]
            d.polygon(pts, fill=(224, 224, 0), outline=(224, 128, 0))
        d.ellipse([9, 8, 25, 24], fill=(0, 96, 0), outline=(0, 64, 0))
        d.ellipse([12, 11, 19, 18], fill=(64, 128, 0))
        out.append(run_sprite(im))
    return out


def hsh(a, b):
    return ((a * 73856093) ^ (b * 19349663) ^ (a * b * 83492791)) & 0xFFFF


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


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


# ----------------------------------------------------------------------------------- terrain tiles
TILE_ROWS = 64
RAG = (2, 3, 1, 4, 2, 0, 3, 1, 4, 2, 3, 0, 1, 4, 2, 3)


def texel_ghz(wx, wy, d):
    # Grass strip with a ragged lower edge, a shadowed band of dark checker squares, then the orange checkered earth.
    if d < 0:
        return None
    g = 11 + RAG[wx % 16]
    if d < g:
        if d == 0:
            return (128, 224, 0)
        if d >= g - 2:
            return (0, 96, 0)
        if (wx * 3 + d * 5) % 7 == 0:
            return (128, 224, 0)
        if (wx + d) % 5 == 0:
            return (0, 128, 0)
        return (64, 160, 0)
    cell = ((wx // 16) + (wy // 16)) % 2
    lx, ly = wx % 16, wy % 16
    if d < 31:
        c = (96, 32, 0) if cell else (32, 0, 0)
        if lx == 0 or ly == 0:
            c = (128, 64, 0) if cell else (64, 32, 0)
        return c
    c = (192, 96, 0) if cell else (128, 64, 0)
    if lx == 15 or ly == 15:
        c = (96, 32, 0)
    elif lx == 0 or ly == 0:
        c = (224, 160, 32) if cell else (160, 96, 0)
    elif hsh(wx, wy) % 19 == 0:
        c = (128, 64, 0) if cell else (96, 32, 0)
    return c


def texel_mz(wx, wy, d):
    if d < 0:
        return None
    g = 4 + (wx // 3) % 2
    if d < g:
        return (64, 192, 0) if d < 1 else (0, 128, 0)
    bx, by = wx % 32, wy % 32
    blk = hsh(wx // 32, wy // 32) % 3
    c = ((128, 64, 192), (96, 32, 160), (160, 96, 224))[blk]
    if bx < 2 or by < 2:
        c = (192, 128, 224)
    elif bx > 29 or by > 29:
        c = (64, 0, 96)
    elif (bx + by * 2) % 23 == 0:
        c = (64, 0, 128)
    return c


def texel_syz(wx, wy, d):
    if d < 0:
        return None
    if d < 2:
        return (224, 224, 160) if d == 0 else (192, 160, 64)
    cell = ((wx // 16) + (wy // 16)) % 2
    lx, ly = wx % 16, wy % 16
    c = (160, 128, 64) if cell else (128, 96, 32)
    if lx == 0 or ly == 0:
        c = (224, 192, 96)
    elif lx == 15 or ly == 15:
        c = (64, 32, 0)
    if (lx - 8) ** 2 + (ly - 8) ** 2 < 10:
        c = (0, 160, 224) if cell else (0, 192, 96)
    return c


def texel_lava(wx, wy, d):
    if d < 0:
        return None
    v = math.sin(2 * math.pi * wx / 32 + (wy % 16) * 0.8) + math.sin(2 * math.pi * wx / 16 - (wy % 16) * 0.4)
    t = max(0.0, min(1.0, 0.5 + v * 0.25))
    c = mix((192, 32, 0), (224, 192, 32), t)
    return (224, 224, 128) if d == 0 else c


TEXELS = {"ghz": texel_ghz, "mz": texel_mz, "syz": texel_syz}
LAVA_Y = 320


def tile_image(fn, px, base, a, d):
    im = Image.new("RGB", (16, TILE_ROWS))
    pxl = im.load()
    for k in range(16):
        surf = a + int(d * k / 16)
        for r in range(TILE_ROWS):
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

    def fill_rows(f):
        rows = []
        for wy in range(32):
            im = Image.new("RGB", (32, 1))
            for wx in range(32):
                im.putpixel((wx, 0), f(wx, wy, 99))
            rows.append(img_rows(im)[0])
        return rows
    return {"tiles": tiles, "fill": fill_rows(fn), "lava_fill": fill_rows(texel_lava)}


# ------------------------------------------------------------------------------------- backgrounds
BG_ROWS = 240
SKYB = (32, 0, 160)


def const(c):
    return lambda r: c


def cloud(d, x, y, s):
    shapes = ((0, 0, 10, 5), (11, -3, 9, 6), (22, 0, 11, 5), (-8, 2, 7, 3), (32, 2, 7, 3))
    for dx, dy, rx, ry in shapes:
        d.ellipse([x + (dx - rx) * s, y + (dy - ry) * s + 3, x + (dx + rx) * s, y + (dy + ry) * s + 3], fill=(96, 128, 224))
    for dx, dy, rx, ry in shapes:
        d.ellipse([x + (dx - rx) * s, y + (dy - ry) * s + 1, x + (dx + rx) * s, y + (dy + ry) * s + 1], fill=(160, 192, 224))
    for dx, dy, rx, ry in shapes:
        d.ellipse([x + (dx - rx) * s, y + (dy - ry) * s - 1, x + (dx + rx) * s - 2, y + (dy + ry) * s - 2], fill=(224, 224, 224))


def ripples(seed, density, longest):
    def fn(d, dx, r0, f):
        rr = random.Random(seed)
        for _ in range(density):
            x, y = rr.randrange(0, 512), rr.randrange(0, 60)
            n = rr.randrange(2, longest)
            d.line([(x + dx, y), (x + dx + n, y)], fill=(160, 192, 224) if rr.random() < 0.4 else (96, 128, 224))
        for _ in range(density):
            d.point((rr.randrange(0, 512) + dx, rr.randrange(0, 60)), fill=(32, 64, 192))
    return fn


def bg_ghz():
    cr = random.Random(11)
    spec = make_layer(0, 3, 320, 0, const(SKYB))

    def clouds(n, y0, s, P):
        pos = [(cr.randrange(0, P), y0 + cr.randrange(-2, 3)) for _ in range(n)]
        return lambda d, dx, r0, f: [cloud(d, x + dx, y - r0, s) for x, y in pos]
    spec += make_layer(3, 20, 384, 0.06, const(SKYB), clouds(4, 12, 1.0, 384))
    spec += make_layer(20, 36, 320, 0.12, const(SKYB), clouds(4, 28, 0.8, 320))
    spec += make_layer(36, 56, 288, 0.2, const(SKYB), clouds(3, 46, 0.7, 288))
    spec += make_layer(56, 62, 320, 0, const(SKYB))
    sr = random.Random(5)
    spikes, x = [], 0
    while x < 512:
        spikes.append((x, sr.randrange(12, 40)))
        x += sr.randrange(7, 13)

    def hills(d, dx, r0, f):
        base = 100 - r0
        d.rectangle([dx, base - 6, dx + 512, base + 2], fill=(32, 0, 0))
        for x, hgt in spikes:
            top = base - hgt
            d.polygon([(x - 7 + dx, base), (x - 1 + dx, top + 4), (x + dx, top), (x + 1 + dx, top + 4), (x + 7 + dx, base)], fill=(32, 0, 0))
            d.line([(x + 2 + dx, top + 6), (x + 2 + dx, base)], fill=(96, 32, 0))
            d.line([(x - 3 + dx, top + 14), (x - 3 + dx, base)], fill=(64, 32, 0))
            d.point((x + dx, top + 1), fill=(128, 64, 0))
    spec += make_layer(62, 100, 512, 0.28, const(SKYB), hills)
    br = random.Random(9)
    clumps = [(x + br.randrange(-3, 4), br.randrange(-3, 4), br.randrange(8, 12)) for x in range(0, 384, 17)]
    clumps2 = [(x + 8 + br.randrange(-3, 4), br.randrange(4, 9), br.randrange(7, 10)) for x in range(0, 384, 17)]

    def bushes(d, dx, r0, f):
        for row in (clumps, clumps2):
            for cx, oy, r in row:
                cy = (116 if row is clumps else 126) + oy - r0
                x = cx + dx
                d.ellipse([x - r - 1, cy - r - 1, x + r + 1, cy + r + 1], fill=(0, 64, 0))
                d.ellipse([x - r, cy - r, x + r, cy + r], fill=(0, 96, 0))
                d.ellipse([x - r + 2, cy - r + 1, x + r - 3, cy + r - 4], fill=(64, 160, 0))
                for k in range(5):
                    d.point((x - r // 2 + k * 2, cy - r // 2 + (k * 3) % 5), fill=(128, 224, 0))
                d.ellipse([x - 3, cy - r + 2, x + 1, cy - r + 5], fill=(128, 224, 0))
        for wx in (250,):
            for y in range(112 - r0, 140 - r0):
                for xx in range(wx, wx + 30):
                    c = (160, 192, 224) if (xx + y + f * 2) % 2 == 0 else (96, 128, 224)
                    if (y + f) % 5 == 0:
                        c = (224, 224, 224)
                    d.point((xx + dx, y), fill=c)
        d.rectangle([dx, 138 - r0, dx + 384, 141 - r0], fill=(96, 32, 0))
        d.rectangle([dx, 141 - r0, dx + 384, 142 - r0], fill=(32, 0, 0))
    spec += make_layer(100, 143, 384, 0.42, const((32, 0, 0)), bushes, frames=3)
    water = const((0, 128, 224))
    spec += make_layer(143, 152, 256, 0.5, water, ripples(1, 20, 7), wave=True)
    spec += make_layer(152, 163, 256, 0.56, water, ripples(2, 26, 9), wave=True)
    spec += make_layer(163, 176, 256, 0.64, water, ripples(3, 30, 11), wave=True)
    spec += make_layer(176, 192, 256, 0.74, water, ripples(4, 36, 13), wave=True)
    spec += make_layer(192, 214, 256, 0.86, water, ripples(5, 44, 15), wave=True)
    spec += make_layer(214, BG_ROWS, 256, 1.0, water, ripples(6, 50, 16), wave=True)
    return spec


def bg_mz():
    sky = [(0, (0, 0, 32)), (90, (64, 0, 64)), (160, (128, 32, 64))]
    sk = lambda r: grad(sky, r)
    spec = make_layer(0, 30, 320, 0, sk)

    def smoke(d, dx, r0, f):
        for x in range(0, 360, 61):
            cloud(d, x + dx, 24 - r0, 0.8)
    spec += make_layer(30, 56, 360, 0.06, sk, smoke)

    def pillars(d, dx, r0, f):
        for x, w in ((20, 16), (96, 22), (170, 14), (236, 20), (300, 16)):
            d.rectangle([x + dx, 64 - r0, x + w + dx, 150 - r0], fill=(64, 0, 96))
            d.rectangle([x - 3 + dx, 58 - r0, x + w + 3 + dx, 66 - r0], fill=(96, 32, 128))
            d.rectangle([x + dx, 64 - r0, x + 3 + dx, 150 - r0], fill=(96, 32, 128))
    spec += make_layer(56, 120, 320, 0.15, sk, pillars)

    def arches(d, dx, r0, f):
        for x in range(0, 256, 64):
            d.rectangle([x + dx, 110 - r0, x + 64 + dx, 160 - r0], fill=(32, 0, 64))
            d.pieslice([x + 8 + dx, 96 - r0, x + 56 + dx, 144 - r0], 180, 360, fill=(64, 0, 96))
            d.rectangle([x + 8 + dx, 120 - r0, x + 56 + dx, 160 - r0], fill=(64, 0, 96))
            d.ellipse([x + 20 + dx, 116 - r0, x + 44 + dx, 140 - r0], fill=(160, 32, 0))
    spec += make_layer(120, 160, 256, 0.32, sk, arches)
    glow = lambda r: mix((160, 32, 0), (224, 128, 0), (r - 160) / 40)

    def bands(seed):
        wr = random.Random(seed)
        pts = [(wr.randrange(0, 256), wr.randrange(0, 12)) for _ in range(40)]
        return lambda d, dx, r0, f: [d.line([(x + dx, y), (x + dx + wr.randrange(5, 12), y)], fill=(224, 224, 64)) for x, y in pts]
    spec += make_layer(160, 170, 256, 0.45, glow, bands(4), wave=True)
    spec += make_layer(170, 182, 256, 0.55, glow, bands(5), wave=True)
    spec += make_layer(182, 196, 256, 0.68, glow, bands(6), wave=True)

    def bricks(d, dx, r0, f):
        for y in range(196, BG_ROWS, 8):
            d.line([(0, y - r0), (400, y - r0)], fill=(32, 0, 64))
            for x in range(-8 + (y // 8 % 2) * 8, 320, 16):
                d.line([(x + dx, y - r0), (x + dx, y + 8 - r0)], fill=(32, 0, 64))
    spec += make_layer(196, BG_ROWS, 320, 0.9, const((96, 32, 128)), bricks)
    return spec


def bg_syz():
    rnd = random.Random(31)
    sky = [(0, (0, 0, 64)), (90, (64, 32, 128)), (170, (160, 64, 160))]
    sk = lambda r: grad(sky, r)

    def stars(d, dx, r0, f):
        sr = random.Random(2)
        for _ in range(60):
            x, y = sr.randrange(0, 320), sr.randrange(0, 80)
            d.point((x + dx, y - r0), fill=(224, 224, 224) if sr.random() < 0.5 else (160, 192, 224))
        d.ellipse([240 + dx, 18 - r0, 264 + dx, 42 - r0], fill=(224, 224, 160))
        d.ellipse([246 + dx, 16 - r0, 268 + dx, 38 - r0], fill=sk(28))
    spec = make_layer(0, 66, 320, 0, sk, stars)

    def skyline(col, win, top, bot, seed, glowcol):
        sr = random.Random(seed)
        bs, x = [], 0
        while x < 384:
            w = sr.randrange(18, 40)
            bs.append((x, w, sr.randrange(top, top + 40)))
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
    spec += make_layer(66, 120, 384, 0.12, sk, skyline((32, 32, 96), (224, 192, 96), 72, 170, 3, (96, 64, 160)))
    spec += make_layer(120, 170, 320, 0.3, sk, skyline((64, 32, 128), (224, 224, 96), 110, 220, 4, (224, 96, 192)))

    def bokeh(d, dx, r0, f):
        for x in range(0, 256, 11):
            y = 175 + rnd.randrange(0, 22)
            col = rnd.choice(((224, 96, 192), (96, 224, 224), (224, 224, 96), (128, 224, 128)))
            d.ellipse([x + dx, y - r0, x + 3 + dx, y + 3 - r0], fill=col)
    spec += make_layer(170, 204, 256, 0.5, lambda r: mix((64, 32, 128), (32, 0, 64), (r - 170) / 34), bokeh)
    spec += make_layer(204, BG_ROWS, 320, 0, const((32, 0, 64)))
    return spec


# ------------------------------------------------------------------------------------------- fonts
CHARS = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:!+-./X"


def make_font(path, px, colours, outline=0, shadow=None):
    # Glyphs are rendered without anti-aliasing. colours: name -> (fill, edge colour); the edge is either a
    # 1 px drop shadow (outline == 0) or a full outline of `outline` pixels.
    f = ImageFont.truetype(path, px)
    ascent, descent = f.getmetrics()
    chh = ascent + descent + 2 * outline + 1
    adv, g = {}, {c: {} for c in colours}
    for ch in CHARS:
        a = int(round(f.getlength(ch)))
        adv[ch] = a + outline
        w = a + 2 * outline + 2
        m = Image.new("L", (w, chh), 0)
        d = ImageDraw.Draw(m)
        d.fontmode = "1"
        d.text((outline, outline), ch, font=f, fill=255)
        edge = m.copy()
        if outline:
            edge = m.filter(ImageFilter.MaxFilter(2 * outline + 1))
        else:
            edge = Image.new("L", (w, chh), 0)
            edge.paste(m, (1, 1))
        for name, (fill, ecol) in colours.items():
            im = Image.new("RGBA", (w, chh), (0, 0, 0, 0))
            im.paste(Image.new("RGBA", (w, chh), ecol + (255,)), (0, 0), edge)
            im.paste(Image.new("RGBA", (w, chh), fill + (255,)), (0, 0), m)
            g[name][ch] = run_sprite(im)
    return {"ch": chh, "adv": adv, "g": g}


def main():
    chars, source = build_chars()
    data = {
        "chars": chars, "loop": loop_sprite(), "log": log_sprite(), "flash": flash_frames(),
        "ring": ring_frames(), "sparkle": sparkle_frames(),
        "spring_red": spring_frames((224, 32, 0)), "spring_yel": spring_frames((224, 224, 0)),
        "spikes": spikes_sprite(), "monitor": monitor_frames(), "shield": shield_frames(), "sign": sign_frames(),
        "bumper": bumper_frames(), "dust": dust_frames(), "shot": shot_frames(), "boom": explosion_frames(),
        "puff": puff_frames(), "animal": animal_frames(),
        "moto": [run_sprite(f) for f in motobug_frames()], "moto_r": [run_sprite(flip(f)) for f in motobug_frames()],
        "cater": [run_sprite(f) for f in caterkiller_frames()], "cater_r": [run_sprite(flip(f)) for f in caterkiller_frames()],
        "roller": [run_sprite(f) for f in roller_frames()], "roller_r": [run_sprite(flip(f)) for f in roller_frames()],
        "crab": [run_sprite(f) for f in crab_frames()],
        "buzz": [run_sprite(f) for f in buzz_frames()], "buzz_r": [run_sprite(flip(f)) for f in buzz_frames()],
        "chopper": chopper_frames(),
        "decor": {"ghz": {"palm1": [palm_sprite(110, f, 0.3) for f in (0, 1)], "palm2": [palm_sprite(130, f, 1.4) for f in (0, 1)],
                          "palm3": [palm_sprite(150, f, 2.6) for f in (0, 1)], "flower": [flower_sprite()],
                          "sunflower": sunflower_frames(), "totem": [totem_sprite()]},
                  "mz": {"column": [column_sprite()], "brazier": brazier_frames()},
                  "syz": {"lamp": lamp_frames()}},
        "zones": {"ghz": zone_tiles("ghz"), "mz": zone_tiles("mz"), "syz": zone_tiles("syz")},
        "bg": {"ghz": bg_ghz(), "mz": bg_mz(), "syz": bg_syz()},
        "font": {
            "S": make_font(FONT_MONO, 13, {"yellow": ((224, 224, 0), (160, 64, 0)), "white": ((224, 224, 224), (96, 96, 96)),
                                           "red": ((224, 0, 0), (96, 0, 0))}),
            "M": make_font(FONT_BIG, 17, {"white": ((224, 224, 224), (0, 0, 96)), "yellow": ((224, 224, 0), (160, 64, 0))}, outline=1),
            "L": make_font(FONT_BIG, 30, {"white": ((224, 224, 224), (0, 0, 96)), "yellow": ((224, 224, 0), (160, 64, 0))}, outline=2),
        },
    }
    save_bundle("g_sonic.bin", data)
    print("wrote g_sonic.bin; character art:", source)


if __name__ == "__main__":
    main()


