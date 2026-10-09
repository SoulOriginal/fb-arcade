# Build-time pixel art for the Contra module: every sprite is drawn procedurally at 1 virtual pixel per pixel.
# Colours follow the NES palette as seen in the owner's reference screenshots (used as visual reference only).
import math, random
from PIL import Image, ImageDraw, ImageOps

PAL = dict(
    black=(0, 0, 0), white=(252, 252, 252), grey=(188, 188, 188), dgrey=(100, 100, 108), lgrey=(224, 224, 232),
    blue=(36, 96, 248), dblue=(0, 40, 170), lblue=(80, 190, 252), pblue=(168, 228, 252),
    red=(216, 40, 0), dred=(140, 16, 0), orange=(240, 120, 16), yellow=(252, 200, 0), lyellow=(252, 236, 168),
    green=(0, 168, 0), dgreen=(0, 96, 0), lgreen=(176, 248, 24), skin=(252, 188, 140), dskin=(212, 124, 72),
    brown=(124, 60, 0), dbrown=(64, 28, 0), olive=(172, 124, 8), lolive=(216, 184, 40),
    pink=(240, 112, 140), dpink=(168, 40, 80), purple=(88, 40, 140), dpurple=(36, 16, 80),
)
C = PAL


def new(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def mirror(im):
    return ImageOps.mirror(im)


# ---- conversion to span sprites -------------------------------------------------------------------
_chunk = {}


def chunk(rgb):
    # One virtual pixel is 4 screen pixels wide: 4 RGB565 values, 8 bytes.
    v = _chunk.get(rgb)
    if v is None:
        r, g, b = rgb
        c = ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)).to_bytes(2, "little")
        v = _chunk[rgb] = c * 4
    return v


def sprite(im, ox, oy):
    # (rows, w, h, ox, oy); rows[j] = [(byte offset, bytes), ...] for each opaque run. ox, oy = anchor inside the image.
    w, h = im.size
    px = im.load()
    rows = []
    for y in range(h):
        spans = []
        x = 0
        while x < w:
            if px[x, y][3] < 128:
                x += 1
                continue
            s = x
            buf = []
            while x < w and px[x, y][3] >= 128:
                buf.append(chunk(px[x, y][:3]))
                x += 1
            spans.append((s * 8, b"".join(buf)))
        rows.append(spans)
    return (rows, w, h, ox, oy)


def strip_rows(im):
    # Opaque RGB image -> list of per-row bytes, every pixel 8 bytes wide.
    w, h = im.size
    data = im.convert("RGB").tobytes()
    out = []
    for y in range(h):
        base = y * w * 3
        out.append(b"".join(chunk((data[base + i], data[base + i + 1], data[base + i + 2])) for i in range(0, w * 3, 3)))
    return out


def mask_rows(im):
    # Alpha channel -> rows of 0xFF/0x00 bytes in the same expanded layout, for the canopy blend.
    w, h = im.size
    a = im.split()[3].tobytes()
    return [b"".join((b"\xff" * 8) if a[y * w + x] >= 128 else (b"\x00" * 8) for x in range(w)) for y in range(h)]


# ---- people -----------------------------------------------------------------------------------------------
CW, CH, FX, FY = 40, 48, 20, 47
LEGS = [
    ((3, 38, 7, 46), (-2, 38, -7, 43)),
    ((1, 39, 1, 46), (3, 36, -2, 41)),
    ((-2, 38, -7, 43), (3, 38, 7, 46)),
    ((3, 36, -2, 41), (1, 39, 1, 46)),
]
STAND_LEGS = ((2, 39, 3, 46), (-2, 39, -3, 46))
AIMS = [(1, 0), (1, -1), (0, -1), (1, 1), (0, 1)]       # forward, up-forward, up, down-forward, down

PEOPLE = {
    "bill": dict(top=None, pants="blue", dpants="dblue", band="red", hair="dbrown", shoe="dbrown", chest=True),
    "lance": dict(top=None, pants="red", dpants="dred", band="red", hair="dbrown", shoe="dbrown", chest=True),
    "soldier": dict(top="lgrey", dtop="grey", pants="grey", dpants="dgrey", band=None, hair="dgrey", shoe="dgrey", chest=False),
    "rsoldier": dict(top="red", dtop="dred", pants="dred", dpants="brown", band=None, hair="dbrown", shoe="dbrown", chest=False),
    "sniper": dict(top="olive", dtop="brown", pants="brown", dpants="dbrown", band=None, hair="dbrown", shoe="dbrown", chest=False),
}


def _line(d, a, b, col, w=1):
    d.line([a, b], fill=C[col] + (255,), width=w)


def person_upper(d, p, aim, arm=True, y0=0):
    """Head, chest, arm and rifle of a standing person facing right (feet anchor at 20,47)."""
    skin, dskin = C["skin"] + (255,), C["dskin"] + (255,)
    # torso
    if p["chest"]:
        d.rectangle([15, 17 + y0, 24, 29 + y0], fill=skin)
        d.line([(19, 20 + y0), (19, 25 + y0)], fill=dskin)
        d.line([(15, 17 + y0), (15, 28 + y0)], fill=dskin)
    else:
        d.rectangle([15, 17 + y0, 24, 29 + y0], fill=C[p["top"]] + (255,))
        d.line([(15, 17 + y0), (15, 29 + y0)], fill=C[p["dtop"]] + (255,))
        d.line([(15, 28 + y0), (24, 28 + y0)], fill=C[p["dtop"]] + (255,))
    d.rectangle([15, 29 + y0, 24, 31 + y0], fill=C[p["pants"]] + (255,))
    # head
    d.rectangle([17, 8 + y0, 23, 15 + y0], fill=skin)
    d.rectangle([16, 5 + y0, 24, 8 + y0], fill=C[p["hair"]] + (255,))
    d.point([(22, 11 + y0), (23, 11 + y0)], fill=C["black"] + (255,))
    d.line([(17, 15 + y0), (23, 15 + y0)], fill=dskin)
    if p["band"]:
        d.rectangle([16, 8 + y0, 24, 9 + y0], fill=C[p["band"]] + (255,))
        d.line([(12, 9 + y0), (16, 9 + y0)], fill=C[p["band"]] + (255,))
        d.line([(13, 11 + y0), (16, 10 + y0)], fill=C[p["band"]] + (255,))
    if arm:
        ax, ay = AIMS[aim]
        n = math.hypot(ax, ay)
        sx, sy = 21, 20 + y0
        hx, hy = sx + ax / n * 5, sy + ay / n * 5
        _line(d, (sx, sy), (round(hx), round(hy)), "skin", 3)
        gx0, gy0 = sx + ax / n * 3, sy + ay / n * 3
        gx1, gy1 = sx + ax / n * 15, sy + ay / n * 15
        _line(d, (round(gx0), round(gy0)), (round(gx1), round(gy1)), "black", 3)
        _line(d, (round(gx0), round(gy0)), (round(gx1), round(gy1)), "dgrey", 1)
        d.point([(round(hx), round(hy))], fill=skin)


def person_legs(d, p, legs):
    for k, (kx, ky, fx, fy) in enumerate(legs):
        col = p["pants"] if k == 0 else p["dpants"]
        _line(d, (20, 30), (20 + kx, ky), col, 4)
        _line(d, (20 + kx, ky), (20 + fx, fy), col, 3)
        d.rectangle([20 + fx - 1, fy - 1, 20 + fx + 2, fy + 1], fill=C[p["shoe"]] + (255,))


def person(pal, pose, fr=0, aim=0):
    p = PEOPLE[pal]
    im = new(CW, CH)
    d = ImageDraw.Draw(im)
    if pose in ("run", "stand"):
        person_legs(d, p, LEGS[fr % 4] if pose == "run" else STAND_LEGS)
        person_upper(d, p, aim)
    elif pose == "prone":
        d.rectangle([3, 41, 14, 46], fill=C[p["pants"]] + (255,))
        d.rectangle([2, 44, 4, 46], fill=C[p["shoe"]] + (255,))
        d.rectangle([14, 40, 25, 46], fill=(C["skin"] if p["chest"] else C[p["top"]]) + (255,))
        d.rectangle([14, 40, 16, 46], fill=C[p["pants"]] + (255,))
        d.rectangle([26, 39, 33, 46], fill=C["skin"] + (255,))
        d.rectangle([26, 38, 33, 40], fill=C[p["hair"]] + (255,))
        if p["band"]:
            d.rectangle([26, 40, 33, 41], fill=C[p["band"]] + (255,))
        _line(d, (24, 43), (39, 43), "black", 3)
        _line(d, (26, 43), (39, 43), "dgrey", 1)
    elif pose == "jump":
        a = fr * math.pi / 2 + 0.6
        cx, cy = 20, 33
        d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=C[p["dpants"]] + (255,))
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=C[p["pants"]] + (255,))
        hx, hy = cx + 5 * math.cos(a), cy + 5 * math.sin(a)
        d.ellipse([hx - 3, hy - 3, hx + 3, hy + 3], fill=C["skin"] + (255,))
        if p["band"]:
            d.point([(round(hx + 2 * math.cos(a)), round(hy + 2 * math.sin(a)))], fill=C[p["band"]] + (255,))
        tx, ty = cx - 3 * math.cos(a), cy - 3 * math.sin(a)
        d.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], fill=(C["skin"] if p["chest"] else C[p["top"]]) + (255,))
        d.point([(round(cx + 6 * math.cos(a + 2.2)), round(cy + 6 * math.sin(a + 2.2)))], fill=C["black"] + (255,))
    elif pose == "wade":
        person_upper(d, p, aim, y0=8)
        im = im.crop((0, 0, CW, 40))
        out = new(CW, CH)
        out.paste(im, (0, 8))
        d = ImageDraw.Draw(out)
        # the lower body is hidden by the water: ripple band over the hips
        d.rectangle([8, 43, 32, 44], fill=C["pblue"] + (255,))
        d.rectangle([8, 45, 32, 47], fill=C["blue"] + (255,))
        d.point([(11, 43), (19, 43), (27, 43)], fill=C["white"] + (255,))
        im = out
    elif pose == "dive":
        d.ellipse([15, 42, 25, 46], fill=C["blue"] + (255,))
        d.ellipse([16, 43, 24, 45], fill=C["pblue"] + (255,))
        d.point([(19, 39), (23, 37), (21, 34)], fill=C["white"] + (255,))
    elif pose == "dead":
        base = person(pal, "stand", 1, 0)
        ang = (35, 75, 115, 160)[fr]
        im = base.rotate(ang, resample=Image.NEAREST, center=(20, 30))
    return im


# ---- weapon letters and items ---------------------------------------------------------------------------
LETTERS = {
    "S": ["01110", "10000", "01110", "00001", "11110"],
    "M": ["10001", "11011", "10101", "10001", "10001"],
    "L": ["10000", "10000", "10000", "10000", "11111"],
    "F": ["11111", "10000", "11110", "10000", "10000"],
    "R": ["11110", "10001", "11110", "10100", "10010"],
    "B": ["11110", "10001", "11110", "10001", "11110"],
    "?": ["01110", "10001", "00110", "00000", "00100"],
}


def falcon(letter):
    im = new(26, 16)
    d = ImageDraw.Draw(im)
    for sx in (0, 1):
        pts = [(13, 3), (3, 0), (0, 6), (4, 10), (13, 12)] if sx == 0 else [(13, 3), (22, 0), (25, 6), (21, 10), (13, 12)]
        d.polygon(pts, fill=C["brown"] + (255,), outline=C["dbrown"] + (255,))
        d.line([(pts[1][0], pts[1][1] + 3), (13, 8)], fill=C["orange"] + (255,))
    d.ellipse([7, 1, 18, 14], fill=C["dgrey"] + (255,), outline=C["black"] + (255,))
    d.ellipse([8, 2, 17, 13], fill=C["red"] + (255,))
    bm = LETTERS[letter]
    for j, row in enumerate(bm):
        for i, ch in enumerate(row):
            if ch == "1":
                d.point([(10 + i, 4 + j)], fill=C["white"] + (255,))
    return im


def capsule(fr):
    im = new(24, 14)
    d = ImageDraw.Draw(im)
    wy = 2 if fr == 0 else 6
    d.polygon([(4, 6), (0, wy), (7, wy + 1), (9, 6)], fill=C["lgrey"] + (255,), outline=C["dgrey"] + (255,))
    d.polygon([(20, 6), (23, wy), (16, wy + 1), (14, 6)], fill=C["lgrey"] + (255,), outline=C["dgrey"] + (255,))
    d.ellipse([6, 3, 17, 12], fill=C["red"] + (255,), outline=C["dred"] + (255,))
    d.rectangle([9, 6, 14, 9], fill=C["yellow"] + (255,))
    d.point([(8, 5)], fill=C["white"] + (255,))
    return im


def medal(col):
    im = new(10, 18)
    d = ImageDraw.Draw(im)
    main, dark = (C["lblue"], C["dblue"]) if col == "blue" else (C["orange"], C["dred"])
    d.polygon([(1, 0), (5, 0), (7, 8), (4, 8)], fill=dark + (255,))
    d.polygon([(8, 0), (4, 0), (2, 8), (5, 8)], fill=main + (255,))
    d.ellipse([0, 8, 9, 17], fill=main + (255,), outline=dark + (255,))
    d.ellipse([2, 10, 7, 15], fill=C["white"] + (255,))
    d.ellipse([3, 11, 6, 14], fill=dark + (255,))
    return im


# ---- projectiles and explosions ----------------------------------------------------------------------------
def dot(size, core, edge):
    im = new(size, size)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, size - 1, size - 1], fill=C[edge] + (255,))
    if size > 3:
        d.ellipse([1, 1, size - 2, size - 2], fill=C[core] + (255,))
    else:
        d.point([(1, 1)], fill=C[core] + (255,))
    return im


def laser(dirv, length=22):
    s = length + 6
    im = new(s * 2, s * 2)
    d = ImageDraw.Draw(im)
    n = math.hypot(*dirv)
    ux, uy = dirv[0] / n, dirv[1] / n
    cx = cy = s
    a, b = (cx - ux * length / 2, cy - uy * length / 2), (cx + ux * length / 2, cy + uy * length / 2)
    d.line([a, b], fill=C["lblue"] + (255,), width=4)
    d.line([a, b], fill=C["white"] + (255,), width=2)
    return im.crop(im.getbbox())


def explosion(frame, big):
    """The yellow-orange burst: a white core growing into rings of yellow, orange and red with flying sparks."""
    r = ((5, 9, 13, 11, 7) if big else (3, 6, 8, 7, 4))[frame]
    s = r * 2 + 6
    im = new(s, s)
    d = ImageDraw.Draw(im)
    cols = [C["white"], C["yellow"], C["orange"], C["red"], C["dred"]]
    c = s // 2
    rnd = random.Random(frame * 7 + big)
    for i, col in enumerate(cols[max(0, frame - 1):] if frame else cols[:3]):
        rr = max(1, r - i * max(1, r // 4))
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=col + (255,))
    for k in range(6 + frame * 2):
        a = rnd.random() * 6.28
        l = r + rnd.randint(0, 3)
        x, y = c + math.cos(a) * l, c + math.sin(a) * l
        d.rectangle([x - 1, y - 1, x, y], fill=(C["yellow"] if k % 2 else C["white"]) + (255,))
    return im


# ---- enemies -----------------------------------------------------------------------------------------------
def turret(step, steps=12, kind="grey"):
    """A wall/rock turret box with a barrel at angle step/steps of a turn, 0 = pointing left, clockwise."""
    im = new(24, 24)
    d = ImageDraw.Draw(im)
    body, dark, lite = (C["grey"], C["dgrey"], C["lgrey"]) if kind == "grey" else (C["red"], C["dred"], C["orange"])
    d.rectangle([2, 4, 21, 21], fill=dark + (255,))
    d.rectangle([3, 5, 20, 20], fill=body + (255,))
    d.line([(3, 5), (20, 5)], fill=lite + (255,))
    d.line([(3, 5), (3, 20)], fill=lite + (255,))
    d.rectangle([2, 20, 21, 21], fill=C["black"] + (255,))
    a = math.pi - step * 2 * math.pi / steps
    cx, cy = 12, 12
    ex, ey = cx + math.cos(a) * 11, cy - math.sin(a) * 11
    _line(d, (cx, cy), (round(ex), round(ey)), "black", 5)
    _line(d, (cx, cy), (round(ex), round(ey)), "dgrey", 3)
    d.ellipse([8, 8, 16, 16], fill=C["black"] + (255,))
    d.ellipse([9, 9, 15, 15], fill=C["red"] + (255,))
    d.point([(10, 10)], fill=C["white"] + (255,))
    return im


def sensor(state):
    """Wall sensor box with the red eagle emblem; state 0 closed, 1 opening, 2 open/flashing."""
    im = new(24, 24)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 23, 23], fill=C["black"] + (255,))
    d.rectangle([1, 1, 22, 22], fill=C["lgrey"] + (255,))
    d.line([(1, 22), (22, 22)], fill=C["dgrey"] + (255,))
    d.line([(22, 1), (22, 22)], fill=C["dgrey"] + (255,))
    d.rectangle([3, 3, 20, 20], fill=C["dgrey"] + (255,))
    if state == 0:
        d.rectangle([4, 4, 19, 19], fill=C["grey"] + (255,))
        d.polygon([(12, 6), (17, 12), (12, 18), (7, 12)], fill=C["dred"] + (255,))
    else:
        col = C["red"] if state == 1 else C["orange"]
        d.rectangle([4, 4, 19, 19], fill=C["dred"] + (255,))
        d.polygon([(12, 5), (18, 12), (12, 19), (6, 12)], fill=col + (255,))
        d.polygon([(12, 8), (15, 12), (12, 16), (9, 12)], fill=C["lyellow" if state == 2 else "white"] + (255,))
        d.rectangle([4, 11, 8, 12], fill=col + (255,))
        d.rectangle([15, 11, 19, 12], fill=col + (255,))
    return im


def bush():
    im = new(26, 14)
    d = ImageDraw.Draw(im)
    rnd = random.Random(5)
    for i in range(22):
        x, y = rnd.randint(1, 20), rnd.randint(2, 9)
        d.ellipse([x, y, x + 6, y + 6], fill=(C["dgreen"] if i % 3 else C["green"]) + (255,))
    d.rectangle([0, 10, 25, 13], fill=C["dgreen"] + (255,))
    for x in range(1, 25, 4):
        d.point([(x, 8), (x + 1, 9)], fill=C["lgreen"] + (255,))
    return im


def ground_cannon(fr):
    im = new(26, 18)
    d = ImageDraw.Draw(im)
    h = (4, 10, 16)[fr]
    d.rectangle([2, 18 - h, 22, 17], fill=C["dgrey"] + (255,))
    d.rectangle([3, 19 - h, 21, 17], fill=C["grey"] + (255,))
    d.rectangle([0, 20 - h, 5, 22 - h], fill=C["black"] + (255,))
    d.rectangle([2, 22 - h, 6, 23 - h], fill=C["dgrey"] + (255,))
    d.line([(3, 19 - h), (21, 19 - h)], fill=C["lgrey"] + (255,))
    return im


def scuba(fr):
    im = new(16, 22)
    d = ImageDraw.Draw(im)
    if fr == 0:
        d.ellipse([2, 14, 13, 19], fill=C["blue"] + (255,))
        d.rectangle([3, 15, 12, 15], fill=C["pblue"] + (255,))
        d.rectangle([7, 12, 8, 15], fill=C["black"] + (255,))
    else:
        d.rectangle([5, 5, 11, 14], fill=C["dgrey"] + (255,))
        d.rectangle([5, 1, 11, 6], fill=C["skin"] + (255,))
        d.rectangle([4, 0, 11, 2], fill=C["dgrey"] + (255,))
        d.rectangle([7, 0, 8, -3 + 4], fill=C["black"] + (255,))
        d.rectangle([2, 15, 13, 19], fill=C["blue"] + (255,))
        d.rectangle([2, 15, 13, 15], fill=C["pblue"] + (255,))
    return im


def boulder(fr):
    im = new(18, 18)
    d = ImageDraw.Draw(im)
    d.ellipse([1, 1, 16, 16], fill=C["dbrown"] + (255,))
    d.ellipse([2, 2, 15, 15], fill=C["olive"] + (255,))
    for k, (x, y) in enumerate([(5, 5), (10, 9), (6, 11), (11, 4)]):
        rot = (fr * 2) % 4
        d.rectangle([x, y, x + 2, y + 1], fill=(C["dbrown"] if (k + rot) % 2 else C["lolive"]) + (255,))
    return im


def flame(fr):
    im = new(14, 18)
    d = ImageDraw.Draw(im)
    h = 14 + fr * 2
    d.polygon([(1, 17), (7, 17 - h), (13, 17)], fill=C["red"] + (255,))
    d.polygon([(3, 17), (7, 17 - h + 4), (11, 17)], fill=C["orange"] + (255,))
    d.polygon([(5, 17), (7, 17 - h + 8), (9, 17)], fill=C["yellow"] + (255,))
    return im


def floating_rock():
    im = new(40, 22)
    d = ImageDraw.Draw(im)
    d.polygon([(0, 6), (6, 2), (34, 2), (40, 6), (34, 16), (26, 21), (14, 21), (6, 16)], fill=C["dgrey"] + (255,))
    d.polygon([(2, 6), (7, 3), (33, 3), (38, 6), (32, 14), (25, 19), (15, 19), (8, 14)], fill=C["grey"] + (255,))
    d.polygon([(6, 4), (33, 4), (36, 6), (4, 6)], fill=C["white"] + (255,))
    d.line([(10, 10), (16, 16)], fill=C["dgrey"] + (255,))
    d.line([(26, 9), (22, 17)], fill=C["dgrey"] + (255,))
    return im


def mouth(fr):
    im = new(28, 22)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 27, 21], fill=C["dpink"] + (255,))
    d.ellipse([2, 2, 25, 19], fill=C["pink"] + (255,))
    ry = (2, 5, 8)[fr]
    d.ellipse([5, 11 - ry, 22, 11 + ry], fill=C["black"] + (255,))
    if fr:
        d.polygon([(8, 11 - ry + 1), (10, 11 - ry + 4), (12, 11 - ry + 1)], fill=C["white"] + (255,))
        d.polygon([(16, 11 + ry - 1), (18, 11 + ry - 4), (20, 11 + ry - 1)], fill=C["white"] + (255,))
    return im


def spore(fr):
    im = new(10, 10)
    d = ImageDraw.Draw(im)
    d.ellipse([1, 1, 8, 8], fill=C["lgrey"] + (255,))
    for i in range(8):
        a = i * math.pi / 4 + fr * 0.4
        d.point([(5 + round(math.cos(a) * 4.5), 5 + round(math.sin(a) * 4.5))], fill=C["white"] + (255,))
    d.ellipse([3, 3, 6, 6], fill=C["pink"] + (255,))
    return im


def floater(fr):
    im = new(18, 12)
    d = ImageDraw.Draw(im)
    d.ellipse([2, 3, 15, 9], fill=C["pink"] + (255,))
    d.ellipse([3, 4, 14, 8], fill=C["dpink"] + (255,))
    d.point([(13, 5)], fill=C["white"] + (255,))
    for i in range(4):
        d.line([(3 + i * 2, 8), (2 + i * 2 + (fr * 2 - 1), 11)], fill=C["pink"] + (255,))
    return im


def crawler(fr):
    im = new(22, 14)
    d = ImageDraw.Draw(im)
    d.ellipse([3, 4, 17, 11], fill=C["lgrey"] + (255,))
    d.ellipse([4, 5, 16, 10], fill=C["pink"] + (255,))
    d.ellipse([15, 3, 20, 8], fill=C["lgrey"] + (255,))
    d.line([(4, 5), (1, 1)], fill=C["lgrey"] + (255,), width=2)
    for i in range(4):
        x = 5 + i * 3
        d.line([(x, 10), (x + (fr * 2 - 1) * 2, 13)], fill=C["lgrey"] + (255,))
    d.point([(18, 5)], fill=C["black"] + (255,))
    return im


def cocoon(fr):
    im = new(26, 26)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 25, 25], fill=C["dpurple"] + (255,))
    d.ellipse([2, 2, 23, 23], fill=C["dpink"] + (255,))
    d.ellipse([4, 4, 21, 21], fill=C["pink"] + (255,))
    ry = (1, 4, 7)[fr]
    d.ellipse([8, 13 - ry, 17, 13 + ry], fill=C["black"] + (255,))
    return im


def heart(fr):
    im = new(56, 60)
    d = ImageDraw.Draw(im)
    g = fr
    d.ellipse([2 - g, 6 - g, 32 + g, 40 + g], fill=C["dred"] + (255,))
    d.ellipse([24 - g, 6 - g, 54 + g, 40 + g], fill=C["dred"] + (255,))
    d.polygon([(3, 28), (28, 58), (53, 28)], fill=C["dred"] + (255,))
    d.ellipse([5, 9, 29, 36], fill=C["red"] + (255,))
    d.ellipse([27, 9, 51, 36], fill=C["red"] + (255,))
    d.polygon([(7, 30), (28, 54), (49, 30)], fill=C["red"] + (255,))
    d.ellipse([10, 13, 18, 22], fill=C["pink"] + (255,))
    for (a, b, c2, e) in [(28, 12, 28, 40), (16, 24, 24, 44), (40, 24, 32, 44)]:
        d.line([(a, b), (c2, e)], fill=C["dpurple"] + (255,))
    d.ellipse([22, 20, 34, 30], fill=C["orange"] + (255,))
    d.ellipse([25, 23, 31, 28], fill=C["yellow"] + (255,))
    return im


def orb(fr=0):
    im = new(14, 14)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 13, 13], fill=C["dgrey"] + (255,))
    d.ellipse([1, 1, 12, 12], fill=C["grey"] + (255,))
    d.ellipse([3, 3, 7, 7], fill=C["white"] + (255,))
    d.ellipse([6, 6, 11, 11], fill=C["dgrey"] + (255,))
    return im


def alien_head(fr):
    """Waterfall boss head: a metal skull with a mouth that opens (fr 0 closed .. 2 wide)."""
    im = new(48, 52)
    d = ImageDraw.Draw(im)
    d.polygon([(4, 12), (14, 0), (34, 0), (44, 12), (44, 36), (34, 50), (14, 50), (4, 36)], fill=C["dgrey"] + (255,), outline=C["black"] + (255,))
    d.polygon([(7, 13), (15, 3), (33, 3), (41, 13), (41, 35), (33, 47), (15, 47), (7, 35)], fill=C["grey"] + (255,))
    d.rectangle([11, 12, 19, 18], fill=C["red"] + (255,))
    d.rectangle([29, 12, 37, 18], fill=C["red"] + (255,))
    d.point([(13, 14), (31, 14)], fill=C["yellow"] + (255,))
    ry = (2, 6, 10)[fr]
    d.ellipse([14, 32 - ry, 34, 32 + ry], fill=C["black"] + (255,))
    if fr:
        d.ellipse([20, 32 - ry // 2, 28, 32 + ry // 2], fill=C["orange"] + (255,))
    d.line([(24, 3), (24, 12)], fill=C["dgrey"] + (255,))
    return im


def fireball(fr):
    im = new(10, 10)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 9, 9], fill=C["red"] + (255,))
    d.ellipse([2, 2, 7, 7], fill=C["orange"] + (255,))
    d.ellipse([3 + fr % 2, 3, 6 + fr % 2, 6], fill=C["yellow"] + (255,))
    return im
