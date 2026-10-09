# Build-time drawing helpers and sprite art for the Red Ball game (PIL only, never imported on the Pi).
#
# Every sprite is drawn 4x supersampled, shrunk, and then cut into rows of opaque spans (hard edge, dark outline):
# the game blits sprites by assigning those spans into a frame buffer, so there is no per-pixel work at runtime.
import math, random, re
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from buildlib import pack, BOLD

SS = 4
OUT = (38, 18, 24)


def canvas(w, h):
    im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def fin(im, w, h):
    return im.resize((w, h), Image.LANCZOS)


def P(*pts):
    return [(v * SS) for p in pts for v in p]


def sprite(im, thr=128):
    # RGBA image -> span sprite dict: parallel lists y, x, b of opaque horizontal runs.
    im = im.convert("RGBA")
    w, h = im.size
    data = pack(im.convert("RGB"))[2]
    a = im.getchannel("A").point(lambda v: 255 if v >= thr else 0).tobytes()
    ys, xs, bs = [], [], []
    for y in range(h):
        row = a[y * w:(y + 1) * w]
        for m in re.finditer(b"\xff+", row):
            ys.append(y)
            xs.append(m.start())
            bs.append(data[(y * w + m.start()) * 2:(y * w + m.end()) * 2])
    return {"w": w, "h": h, "y": ys, "x": xs, "b": bs}


def rows_of(im):
    # opaque RGB image -> list of RGB565 row bytes
    w, h = im.size
    d = pack(im.convert("RGB"))[2]
    return [d[y * w * 2:(y + 1) * w * 2] for y in range(h)]


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---------------------------------------------------------------------------------------------- the ball
def ball_body(rot, size=56):
    im, d = canvas(size, size)
    n = size * SS
    c = n / 2
    r = c - 2 * SS
    d.ellipse([c - r, c - r, c + r, c + r], fill=OUT)
    r2 = r - 3 * SS
    # vertical gradient made of nested discs, lit from the upper left
    for i in range(24):
        t = i / 23
        rr = r2 * (1 - t * 0.9)
        ox = -t * r2 * 0.28
        oy = -t * r2 * 0.30
        col = mix((176, 14, 28), (255, 96, 84), t ** 1.4)
        d.ellipse([c + ox - rr, c + oy - rr, c + ox + rr, c + oy + rr], fill=col)
    # rotating dark patch and seam: the only thing that tells the roll
    a = math.radians(rot * 30)
    for k in range(8):
        t = k / 7
        pr = r2 * (0.34 - 0.2 * t)
        px = c + math.cos(a) * r2 * 0.58
        py = c + math.sin(a) * r2 * 0.58
        d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=mix((196, 24, 34), (150, 8, 22), t))
    qx, qy = c - math.cos(a) * r2 * 0.62, c - math.sin(a) * r2 * 0.62
    d.ellipse([qx - r2 * .14, qy - r2 * .14, qx + r2 * .14, qy + r2 * .14], fill=(255, 130, 110))
    # glossy highlight (screen fixed)
    hl = Image.new("RGBA", im.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.ellipse([c - r2 * .62, c - r2 * .78, c - r2 * .05, c - r2 * .32], fill=(255, 255, 255, 190))
    hd.ellipse([c - r2 * .50, c - r2 * .70, c - r2 * .26, c - r2 * .50], fill=(255, 255, 255, 255))
    im.alpha_composite(hl)
    # rim shade
    d.arc([c - r2, c - r2, c + r2, c + r2], 20, 160, fill=(120, 6, 20), width=3 * SS)
    return fin(im, size, size)


PUPIL = {"L": (-3.5, 0), "C": (0, 0), "R": (3.5, 0), "U": (0, -3.5), "D": (0, 3.5)}


def ball_face(expr, pup, size=56):
    im, d = canvas(size, size)
    s = SS
    ex, ey = 14.5, 21
    px, py = PUPIL[pup]
    for sx in (-1, 1):
        cx = size / 2 + sx * 9.2
        if expr == "blink":
            d.arc([(cx - 6) * s, 16 * s, (cx + 6) * s, 28 * s], 200, 340, fill=OUT, width=int(2.6 * s))
            continue
        w2, h2 = (7.2, 9.2) if expr != "scared" else (7.8, 10.4)
        d.ellipse([(cx - w2 - 1.4) * s, (ey - h2 - 1.4) * s, (cx + w2 + 1.4) * s, (ey + h2 + 1.4) * s], fill=OUT)
        d.ellipse([(cx - w2) * s, (ey - h2) * s, (cx + w2) * s, (ey + h2) * s], fill=(255, 255, 255))
        if expr == "dizzy":
            pts = []
            for i in range(60):
                t = i / 59
                ang = t * 3.2 * 2 * math.pi
                rr = t * 6.2
                pts += [(cx + math.cos(ang) * rr) * s, (ey + math.sin(ang) * rr * 1.1) * s]
            d.line(pts, fill=(20, 20, 30), width=int(1.6 * s))
            continue
        pr = 3.7 if expr != "scared" else 2.6
        ox = px * (0.8 if sx == 1 else 0.8)
        d.ellipse([(cx + ox - pr) * s, (ey + py - pr) * s, (cx + ox + pr) * s, (ey + py + pr) * s], fill=(15, 12, 20))
        d.ellipse([(cx + ox - pr * .2 + 0.2) * s, (ey + py - pr * .7) * s, (cx + ox + pr * .35) * s, (ey + py - pr * .1) * s], fill=(255, 255, 255))
    my = 34
    if expr == "happy" or expr == "blink":
        d.chord([(size / 2 - 9) * s, (my - 6) * s, (size / 2 + 9) * s, (my + 10) * s], 0, 180, fill=(90, 8, 20), outline=OUT, width=int(1.8 * s))
        d.chord([(size / 2 - 6) * s, (my + 2) * s, (size / 2 + 6) * s, (my + 9) * s], 0, 180, fill=(240, 100, 110))
    elif expr == "scared":
        d.ellipse([(size / 2 - 4.6) * s, (my) * s, (size / 2 + 4.6) * s, (my + 10) * s], fill=(70, 4, 16), outline=OUT, width=int(1.8 * s))
        d.polygon(P((44, 8), (47, 14), (41, 14)), fill=(120, 200, 255), outline=(30, 80, 160))
    else:
        pts = []
        for i in range(21):
            t = i / 20
            pts += [(size / 2 - 9 + t * 18) * s, (my + 4 + math.sin(t * 3 * math.pi) * 2.2) * s]
        d.line(pts, fill=OUT, width=int(2.2 * s))
    return fin(im, size, size)


SQUASH = [(56, 56), (48, 66), (66, 46), (74, 38), (44, 70)]


def build_ball():
    out = {"body": [], "face": {}, "sq": SQUASH}
    bodies = [ball_body(r) for r in range(12)]
    for s, (w, h) in enumerate(SQUASH):
        out["body"].append([sprite(b.resize((w, h), Image.LANCZOS)) for b in bodies])
    for e in ("happy", "scared", "dizzy", "blink"):
        for p in "LCRUD":
            f = ball_face(e, p)
            out["face"][e + p] = [sprite(f.resize(sq, Image.LANCZOS)) for sq in SQUASH]
    return out


# ---------------------------------------------------------------------------------------------- minions
def cube_img(kind, flip, frame, size=52):
    im, d = canvas(size, size + 8)
    s = SS
    bob = 0 if frame == 0 else 2
    top = 6 + bob
    bodyc = {"roam": (58, 62, 78), "soldier": (50, 54, 70), "ninja": (44, 46, 66), "robo": (110, 118, 128), "sentry": (66, 58, 74)}[kind]
    x0, y0, x1, y1 = 1, top, size - 1, size + 6
    d.rounded_rectangle([x0 * s, y0 * s, x1 * s, y1 * s], 7 * s, fill=OUT)
    d.rounded_rectangle([(x0 + 2) * s, (y0 + 2) * s, (x1 - 2) * s, (y1 - 2) * s], 6 * s, fill=bodyc)
    d.rounded_rectangle([(x0 + 2) * s, (y0 + 2) * s, (x1 - 2) * s, (y0 + 12) * s], 6 * s, fill=shade(bodyc, 1.35))
    d.rectangle([(x0 + 4) * s, (y0 + 8) * s, (x1 - 4) * s, (y0 + 14) * s], fill=bodyc)
    if kind == "soldier":
        d.pieslice([2 * s, (top - 8) * s, (size - 2) * s, (top + 22) * s], 180, 360, fill=(170, 176, 190), outline=OUT, width=2 * s)
        d.rectangle([2 * s, (top + 5) * s, (size - 2) * s, (top + 9) * s], fill=(120, 126, 140), outline=OUT, width=s)
    if kind == "ninja":
        d.rectangle([1 * s, (top + 5) * s, (size - 1) * s, (top + 14) * s], fill=(40, 90, 200), outline=OUT, width=s)
        tx = 3 if flip else size - 3
        d.polygon(P((tx, top + 8), (tx + (-12 if flip else 12), top + 3 + bob), (tx + (-10 if flip else 10), top + 14)), fill=(40, 90, 200), outline=OUT)
    if kind == "robo":
        d.line(P((size / 2, top), (size / 2, top - 6)), fill=OUT, width=2 * s)
        d.ellipse(P((size / 2 - 3, top - 9), (size / 2 + 3, top - 3)), fill=(255, 50, 40) if frame == 0 else (255, 200, 60), outline=OUT)
        for rx in (6, size - 6):
            d.ellipse(P((rx - 2, top + 30), (rx + 2, top + 34)), fill=(70, 70, 80))
    dirx = -1 if flip else 1
    for sx in (-1, 1):
        cx = size / 2 + sx * 11
        cy = top + 18
        d.ellipse([(cx - 7) * s, (cy - 7) * s, (cx + 7) * s, (cy + 7) * s], fill=OUT)
        d.ellipse([(cx - 5.6) * s, (cy - 5.6) * s, (cx + 5.6) * s, (cy + 5.6) * s], fill=(255, 250, 235))
        d.ellipse([(cx + dirx * 1.8 - 3) * s, (cy + 0.5 - 3) * s, (cx + dirx * 1.8 + 3) * s, (cy + 0.5 + 3) * s], fill=(10, 10, 14))
        # angry brow, slanted down toward the nose
        bx0, bx1 = cx - 8, cx + 8
        by0, by1 = (cy - 12, cy - 5) if sx == -1 else (cy - 5, cy - 12)
        d.polygon(P((bx0, by0), (bx1, by1), (bx1, by1 + 4), (bx0, by0 + 4)), fill=OUT)
    d.line(P((size / 2 - 8, top + 36), (size / 2 - 3, top + 33), (size / 2 + 3, top + 33), (size / 2 + 8, top + 36)), fill=OUT, width=int(2.4 * s))
    return fin(im, size, size + 8)


def cube_dead(kind, size=52):
    im, d = canvas(size + 10, 22)
    s = SS
    d.rounded_rectangle([0, 2 * s, (size + 10) * s, 21 * s], 6 * s, fill=OUT)
    d.rounded_rectangle([2 * s, 4 * s, (size + 8) * s, 19 * s], 5 * s, fill=(58, 62, 78))
    for cx in (20, size - 4):
        d.line(P((cx - 4, 8), (cx + 4, 15)), fill=(255, 250, 235), width=2 * s)
        d.line(P((cx - 4, 15), (cx + 4, 8)), fill=(255, 250, 235), width=2 * s)
    return fin(im, size + 10, 22)


def build_minions():
    out = {}
    for k in ("roam", "soldier", "ninja", "robo", "sentry"):
        out[k] = {f: [sprite(cube_img(k, fl, fr)) for fr in (0, 1)] for f, fl in (("L", True), ("R", False))}
        out[k]["dead"] = sprite(cube_dead(k))
    return out


# ---------------------------------------------------------------------------------------------- bosses
BS = 108


def boss_img(kind, face, flip):
    im, d = canvas(BS, BS + 10)
    s = SS
    pal = {"monocle": ((70, 60, 90), (170, 150, 200)), "mecha": ((100, 108, 120), (200, 208, 220)), "boulder": ((110, 84, 60), (190, 150, 110))}[kind]
    base, hi = pal
    if face == "hurt":
        base, hi = (240, 240, 250), (255, 255, 255)
    d.rounded_rectangle([1 * s, 8 * s, (BS - 1) * s, (BS + 9) * s], 12 * s, fill=OUT)
    d.rounded_rectangle([5 * s, 12 * s, (BS - 5) * s, (BS + 5) * s], 10 * s, fill=base)
    d.rounded_rectangle([5 * s, 12 * s, (BS - 5) * s, 36 * s], 10 * s, fill=hi)
    d.rectangle([8 * s, 24 * s, (BS - 8) * s, 40 * s], fill=base)
    if kind == "mecha":
        for (rx, ry) in ((12, 18), (BS - 12, 18), (12, BS - 6), (BS - 12, BS - 6)):
            d.ellipse(P((rx - 3, ry - 3), (rx + 3, ry + 3)), fill=(60, 60, 70), outline=OUT)
        d.rectangle(P((BS / 2 - 3, 0), (BS / 2 + 3, 12)), fill=OUT)
        d.ellipse(P((BS / 2 - 6, -2), (BS / 2 + 6, 10)), fill=(255, 60, 40), outline=OUT)
    if kind == "boulder":
        d.line(P((20, 20), (34, 44), (28, 60), (44, 80)), fill=(60, 40, 30), width=3 * s)
        d.line(P((86, 24), (70, 46), (78, 70)), fill=(60, 40, 30), width=3 * s)
    ey = 52
    ec = {"angry": (255, 60, 40), "tired": (255, 220, 60), "hurt": (255, 220, 60), "calm": (255, 220, 60)}[face]
    dirx = -1 if flip else 1
    for sx in (-1, 1):
        cx = BS / 2 + sx * 22
        d.ellipse([(cx - 14) * s, (ey - 14) * s, (cx + 14) * s, (ey + 14) * s], fill=OUT)
        if face == "tired":
            d.ellipse([(cx - 11.5) * s, (ey - 11.5) * s, (cx + 11.5) * s, (ey + 11.5) * s], fill=ec)
            d.rectangle([(cx - 14) * s, (ey - 14) * s, (cx + 14) * s, (ey - 2) * s], fill=base)
            d.line(P((cx - 13, ey - 2), (cx + 13, ey - 2)), fill=OUT, width=3 * s)
        else:
            d.ellipse([(cx - 11.5) * s, (ey - 11.5) * s, (cx + 11.5) * s, (ey + 11.5) * s], fill=ec)
            d.ellipse([(cx + dirx * 3 - 5) * s, (ey - 5) * s, (cx + dirx * 3 + 5) * s, (ey + 5) * s], fill=(10, 10, 14))
        by0, by1 = (ey - 24, ey - 12) if sx == -1 else (ey - 12, ey - 24)
        if face != "tired":
            d.polygon(P((cx - 18, by0), (cx + 18, by1), (cx + 18, by1 + 7), (cx - 18, by0 + 7)), fill=OUT)
    if face == "tired":
        d.ellipse(P((BS / 2 - 12, 78), (BS / 2 + 12, 96)), fill=(30, 10, 14), outline=OUT)
        d.ellipse(P((BS - 14, 28), (BS - 6, 42)), fill=(120, 200, 255), outline=(30, 80, 160))
    else:
        d.line(P((BS / 2 - 22, 92), (BS / 2 - 10, 82), (BS / 2 + 10, 82), (BS / 2 + 22, 92)), fill=OUT, width=4 * s)
        for tx in (-12, -4, 4, 12):
            d.rectangle(P((BS / 2 + tx - 2, 83), (BS / 2 + tx + 2, 90)), fill=(240, 240, 230))
    if kind == "monocle":
        mx = BS / 2 + (22 if not flip else -22) * 1
        d.ellipse([(mx - 20) * s, (ey - 20) * s, (mx + 20) * s, (ey + 20) * s], outline=(235, 190, 40), width=4 * s)
        d.line(P((mx + 14, ey + 14), (mx + 22, ey + 34), (mx + 12, ey + 46)), fill=(235, 190, 40), width=2 * s)
        d.arc([(mx - 14) * s, (ey - 14) * s, (mx + 14) * s, (ey + 14) * s], 200, 260, fill=(255, 255, 255), width=3 * s)
    return fin(im, BS, BS + 10)


def build_bosses():
    out = {}
    for k in ("monocle", "mecha", "boulder"):
        for f in ("angry", "tired", "hurt", "calm"):
            for fl, tag in ((True, "L"), (False, "R")):
                out[k + f + tag] = sprite(boss_img(k, f, fl))
    return out
