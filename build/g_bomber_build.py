# Build-time art for the Bomberman-style game: tiles for four themes, bomber / enemy sprites as run-length
# rows (so they can be composited over any tile without per-pixel work at runtime), HUD icons.
import math, random
from array import array
from PIL import Image, ImageDraw, ImageChops
from buildlib import pack, save_bundle

T = 72
SS = 4
OL = (28, 22, 48, 255)
rnd = random.Random(7)


def canvas(w=T, h=T):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def down(img):
    # Premultiplied resize: a plain RGBA box filter would pull transparent black into the edge colours.
    return img.convert("RGBa").resize((img.width // SS, img.height // SS), Image.BOX).convert("RGBA")


class Pen:
    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img)

    def ell(self, cx, cy, rx, ry, fill=None, outline=None, w=0):
        self.d.ellipse([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS], fill=fill, outline=outline,
                       width=max(0, int(w * SS)))

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=0, r=0):
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, fill=fill, outline=outline,
                                 width=max(0, int(w * SS)))

    def poly(self, pts, fill=None, outline=None, w=0):
        p = [(x * SS, y * SS) for x, y in pts]
        self.d.polygon(p, fill=fill)
        if outline:
            self.d.line(p + [p[0]], fill=outline, width=max(1, int(w * SS)), joint="curve")

    def line(self, pts, fill, w):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=max(1, int(w * SS)), joint="curve")


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3]) + (255,)


# ---------------------------------------------------------------------------------------------- themes
THEMES = [
    dict(name="garden", floor=((72, 168, 72), (64, 156, 66)), speck=(48, 130, 52), pil=(176, 182, 196),
         brick=(214, 112, 62), brick_mortar=(140, 66, 42), wall=(70, 78, 104), wall_hi=(104, 114, 146)),
    dict(name="desert", floor=((222, 190, 122), (212, 180, 112)), speck=(190, 156, 92), pil=(190, 150, 100),
         brick=(168, 104, 70), brick_mortar=(104, 60, 44), wall=(120, 78, 52), wall_hi=(160, 112, 76)),
    dict(name="ice", floor=((176, 218, 240), (166, 210, 236)), speck=(140, 190, 224), pil=(120, 160, 214),
         brick=(240, 246, 255), brick_mortar=(150, 176, 214), wall=(60, 92, 150), wall_hi=(100, 140, 200)),
    dict(name="factory", floor=((88, 96, 112), (80, 88, 104)), speck=(64, 70, 86), pil=(140, 146, 160),
         brick=(232, 168, 40), brick_mortar=(60, 52, 40), wall=(48, 52, 66), wall_hi=(84, 92, 112)),
]


def floor_tile(th, v):
    base = th["floor"][v]
    im = Image.new("RGBA", (T, T), base + (255,))
    d = ImageDraw.Draw(im)
    hi = tuple(min(255, int(c * 1.10)) for c in base)
    lo = tuple(int(c * 0.88) for c in base)
    d.rectangle([0, 0, T - 1, 1], fill=hi)
    d.rectangle([0, 0, 1, T - 1], fill=hi)
    d.rectangle([0, T - 2, T - 1, T - 1], fill=lo)
    d.rectangle([T - 2, 0, T - 1, T - 1], fill=lo)
    r = random.Random(v * 31 + len(th["name"]))
    for _ in range(9):
        x, y = r.randrange(6, T - 10), r.randrange(6, T - 10)
        d.line([(x, y), (x + 2, y - 3)], fill=th["speck"] + (255,), width=1)
        d.line([(x + 3, y), (x + 3, y - 4)], fill=th["speck"] + (255,), width=1)
    return im


def block(th, top, front, line, hi, brick_pattern=False, rivets=False):
    # A 3D-looking cube: lit top face and darker front face, same footprint as a floor tile.
    im = floor_tile(th, 0)
    p = Pen(canvas())
    p.rect(2, 2, 70, 70, fill=OL, r=7)
    p.rect(4, 4, 68, 44, fill=hi, r=6)
    p.rect(4, 36, 68, 68, fill=front, r=6)
    p.rect(4, 4, 68, 46, fill=top, r=6)
    p.rect(8, 7, 64, 14, fill=shade(top, 1.15), r=3)
    if brick_pattern:
        for (y0, y1, off) in ((16, 28, 0), (29, 43, 18)):
            p.d.line([(6 * SS, y1 * SS), (66 * SS, y1 * SS)], fill=line, width=2 * SS)
            x = 6 + off
            while x < 66:
                p.d.line([(x * SS, y0 * SS), (x * SS, y1 * SS)], fill=line, width=2 * SS)
                x += 36
        for (y0, y1, off) in ((48, 57, 8), (58, 67, 26)):
            p.d.line([(6 * SS, y1 * SS), (66 * SS, y1 * SS)], fill=line, width=2 * SS)
            x = 6 + off
            while x < 66:
                p.d.line([(x * SS, y0 * SS), (x * SS, y1 * SS)], fill=line, width=2 * SS)
                x += 30
    else:
        p.rect(10, 18, 62, 34, fill=shade(top, 0.9), r=4)
        p.rect(10, 18, 62, 31, fill=shade(top, 1.08), r=4)
        p.rect(10, 50, 62, 64, fill=shade(front, 0.88), r=4)
    if rivets:
        for (x, y) in ((11, 11), (61, 11), (11, 61), (61, 61)):
            p.ell(x, y, 2.4, 2.4, fill=shade(front, 1.4), outline=OL, w=0.8)
    im.alpha_composite(down(p.img))
    return im


def pillar_tile(th):
    c = th["pil"] + (255,)
    return block(th, shade(c, 1.12), shade(c, 0.78), shade(c, 0.6), shade(c, 1.3), rivets=True)


def brick_tile(th):
    c = th["brick"] + (255,)
    return block(th, shade(c, 1.1), shade(c, 0.82), th["brick_mortar"] + (255,), shade(c, 1.28), brick_pattern=True)


def wall_tile(th):
    c = th["wall"] + (255,)
    im = Image.new("RGBA", (T, T), shade(c, 0.9))
    p = Pen(canvas())
    p.rect(1, 1, 71, 71, fill=OL, r=5)
    p.rect(3, 3, 69, 69, fill=c, r=4)
    p.rect(3, 3, 69, 24, fill=th["wall_hi"] + (255,), r=4)
    p.rect(8, 30, 64, 62, fill=shade(c, 0.78), r=6)
    p.rect(10, 32, 62, 40, fill=shade(c, 0.95), r=4)
    for (x, y) in ((12, 12), (60, 12)):
        p.ell(x, y, 2.5, 2.5, fill=shade(c, 0.5), outline=OL, w=0.7)
    im.alpha_composite(down(p.img))
    return im


def crumble_tile(th, frame, brick, floor):
    # The brick splits into a 3x3 set of shards that fly apart, shrink and fade over the flame time.
    t = (frame + 1) / 5.0
    out = floor.copy()
    if frame == 0:
        flash = Image.new("RGBA", (T, T), (255, 240, 200, 120))
        b = brick.copy()
        b.alpha_composite(flash)
        return b
    n = 3
    s = T // n
    for gy in range(n):
        for gx in range(n):
            shard = brick.crop((gx * s, gy * s, (gx + 1) * s, (gy + 1) * s))
            cx, cy = gx - 1, gy - 1
            k = t * 16
            scale = max(0.15, 1 - t * 0.85)
            sz = max(2, int(s * scale))
            sh = shard.resize((sz, sz), Image.BILINEAR)
            alpha = sh.getchannel("A").point(lambda a: int(a * (1 - t * 0.7)))
            sh.putalpha(alpha)
            dy = k * 0.9 + t * t * 14 * (1 if cy >= 0 else 0.4)
            px = int(gx * s + (s - sz) // 2 + cx * k)
            py = int(gy * s + (s - sz) // 2 + cy * k * 0.9 + (dy if cy > 0 else 0) * 0.3)
            out.alpha_composite(sh, (max(0, min(T - 1, px)), max(0, min(T - 1, py))))
    return out


# ---------------------------------------------------------------------------------------------- bomb, items, flames, door
def bomb_sprite(frame):
    scale, red = [(1.0, 0), (1.12, 0), (0.9, 0), (1.1, 1)][frame]
    p = Pen(canvas())
    p.ell(36, 62, 22 * scale, 5, fill=(0, 0, 0, 90))
    body = (34, 34, 58, 255) if not red else (120, 24, 40, 255)
    r = 24 * scale
    cy = 42 - (scale - 1) * 20
    p.ell(36, cy, r, r * 0.97, fill=OL)
    p.ell(36, cy, r - 2.5, r * 0.97 - 2.5, fill=body)
    p.ell(36 - r * 0.3, cy - r * 0.35, r * 0.34, r * 0.24, fill=(210, 220, 250, 255) if not red else (255, 190, 170, 255))
    p.ell(36 + r * 0.2, cy + r * 0.3, r * 0.5, r * 0.34, fill=shade(body, 1.25))
    p.rect(30, cy - r - 4, 42, cy - r + 4, fill=(120, 120, 140, 255), outline=OL, w=1.2, r=2)
    p.line([(36, cy - r - 3), (44, cy - r - 11)], (150, 110, 60, 255), 2.4)
    sp = 4 + frame % 2 * 2
    p.poly([(44 - sp, cy - r - 11), (44, cy - r - 11 - sp * 1.3), (44 + sp, cy - r - 11), (44, cy - r - 11 + sp * 0.8)],
           fill=(255, 220, 60, 255))
    p.ell(44, cy - r - 11, 2.2, 2.2, fill=(255, 255, 255, 255))
    return down(p.img)


def item_sprite(kind, bounce):
    p = Pen(canvas())
    dy = -6 if bounce else 0
    p.ell(36, 64, 18, 4, fill=(0, 0, 0, 80))
    cols = {"F": (232, 60, 40), "B": (60, 80, 200), "S": (40, 170, 220)}[kind]
    p.rect(12, 12 + dy, 60, 60 + dy, fill=OL, r=11)
    p.rect(14, 14 + dy, 58, 58 + dy, fill=shade(cols, 0.8), r=9)
    p.rect(14, 14 + dy, 58, 44 + dy, fill=cols + (255,), r=9)
    p.rect(18, 17 + dy, 54, 24 + dy, fill=shade(cols, 1.35), r=4)
    if kind == "F":
        pts = [(36, 18), (46, 32), (44, 40), (50, 36), (51, 46), (44, 54), (28, 54), (21, 46), (22, 36), (28, 40), (27, 30),
               (33, 33)]
        p.poly([(x, y + dy) for x, y in pts], fill=(255, 190, 40, 255), outline=OL, w=1.2)
        pts2 = [(36, 34), (42, 44), (40, 52), (32, 52), (30, 44)]
        p.poly([(x, y + dy) for x, y in pts2], fill=(255, 250, 190, 255))
    elif kind == "B":
        p.ell(36, 38 + dy, 13, 13, fill=OL)
        p.ell(36, 38 + dy, 11, 11, fill=(40, 40, 70, 255))
        p.ell(32, 33 + dy, 4, 3, fill=(200, 210, 250, 255))
        p.line([(36, 25 + dy), (42, 19 + dy)], (240, 220, 160, 255), 2.4)
        p.ell(43, 18 + dy, 3, 3, fill=(255, 220, 60, 255))
        p.rect(44, 40 + dy, 56, 44 + dy, fill=(255, 255, 255, 255))
        p.rect(48, 36 + dy, 52, 48 + dy, fill=(255, 255, 255, 255))
    else:
        boot = [(26, 20), (38, 20), (38, 36), (52, 42), (52, 50), (24, 50), (24, 34)]
        p.poly([(x, y + dy) for x, y in boot], fill=(255, 255, 255, 255), outline=OL, w=1.4)
        p.rect(24, 46 + dy, 52, 51 + dy, fill=(230, 60, 60, 255))
        p.ell(30, 54 + dy, 4, 4, fill=OL)
        p.ell(46, 54 + dy, 4, 4, fill=OL)
        p.line([(12, 26 + dy), (22, 26 + dy)], (255, 255, 255, 255), 2)
        p.line([(10, 33 + dy), (21, 33 + dy)], (255, 255, 255, 255), 2)
    return down(p.img)


def door_sprite(state, th):
    # state 0: sealed, 1/2: open and pulsing (all enemies dead)
    p = Pen(canvas())
    glow = [0, 0.35, 0.8][state]
    p.rect(8, 8, 64, 66, fill=OL, r=8)
    p.rect(11, 11, 61, 63, fill=(70, 70, 92, 255) if state == 0 else (60, 80, 150, 255), r=6)
    inner = (24, 24, 40, 255) if state == 0 else (int(80 + 150 * glow), int(180 + 70 * glow), 255, 255)
    p.rect(17, 18, 55, 62, fill=OL, r=14)
    p.rect(19, 20, 53, 62, fill=inner, r=12)
    if state:
        p.rect(24, 26, 48, 62, fill=(255, 255, 255, int(255 * glow)), r=9)
        for i in range(4):
            y = 58 - i * 9
            p.rect(22 + i * 2, y, 50 - i * 2, y + 5, fill=(120, 160, 255, 255))
    else:
        for i in range(4):
            y = 58 - i * 9
            p.rect(22 + i * 2, y, 50 - i * 2, y + 5, fill=(50, 50, 70, 255))
        p.rect(30, 36, 42, 50, fill=(150, 150, 170, 255), outline=OL, w=1.2, r=3)
        p.ell(36, 43, 2.5, 2.5, fill=OL)
    return down(p.img)


def flame_sprite(mask, frame):
    # mask bits: 1 left, 2 right, 4 up, 8 down - which neighbours the flame continues into.
    p = Pen(canvas())
    th = [1.0, 0.84, 0.92][frame]
    layers = [((226, 62, 24, 255), 31 * th), ((255, 150, 24, 255), 24 * th), ((255, 232, 70, 255), 15 * th),
              ((255, 255, 235, 255), 7 * th)]
    for col, r in layers:
        # Arms overshoot the tile edge so the rounded corners fall outside and neighbouring tiles join seamlessly.
        if mask & 1:
            p.rect(-12, 36 - r, 37, 36 + r, fill=col, r=r * 0.6)
        if mask & 2:
            p.rect(35, 36 - r, 84, 36 + r, fill=col, r=r * 0.6)
        if mask & 4:
            p.rect(36 - r, -12, 36 + r, 37, fill=col, r=r * 0.6)
        if mask & 8:
            p.rect(36 - r, 35, 36 + r, 84, fill=col, r=r * 0.6)
        p.ell(36, 36, r, r, fill=col)
    return down(p.img)


# ---------------------------------------------------------------------------------------------- bomber
WHITE = (250, 250, 252, 255)
WSH = (206, 214, 238, 255)
BLUE = (52, 112, 236, 255)
BLUE_D = (28, 62, 156, 255)
SKIN = (255, 218, 196, 255)
PINK = (255, 104, 148, 255)


def bomber_sprite(dirn, f, pose="walk", t=0.0):
    p = Pen(canvas())
    bob = -2 if f in (1, 2) else 0
    p.ell(36, 66, 21, 4.5, fill=(0, 0, 0, 95))
    side = dirn in ("l", "r")
    sgn = -1 if dirn == "l" else 1
    # feet
    if side:
        a = 6 if f == 1 else (-6 if f == 2 else 0)
        for x, lift in ((30 + a, 0 if f != 1 else -3), (44 - a, 0 if f != 2 else -3)):
            p.ell(x, 62 + lift, 9, 6, fill=OL)
            p.ell(x, 62 + lift, 7.5, 4.6, fill=BLUE)
    else:
        for x, lift in ((27, -4 if f == 1 else 0), (45, -4 if f == 2 else 0)):
            p.ell(x, 62 + lift, 10, 6.5, fill=OL)
            p.ell(x, 62 + lift, 8.4, 5, fill=BLUE)
            p.ell(x - 2, 60 + lift, 4, 2, fill=shade(BLUE, 1.3))
    # body
    p.rect(23, 42 + bob, 49, 62 + bob, fill=OL, r=9)
    p.rect(25, 44 + bob, 47, 60 + bob, fill=BLUE, r=7)
    p.rect(25, 44 + bob, 47, 50 + bob, fill=shade(BLUE, 1.25), r=4)
    p.rect(30, 52 + bob, 42, 58 + bob, fill=WHITE, r=3)
    # arms (hands swing opposite to the feet)
    if pose == "win":
        for sx in (-1, 1):
            p.line([(36 + sx * 15, 46 + bob), (36 + sx * 19, 26 + bob + (t % 2) * 3)], OL, 9)
            p.line([(36 + sx * 15, 46 + bob), (36 + sx * 19, 26 + bob + (t % 2) * 3)], WHITE, 6)
            p.ell(36 + sx * 19, 23 + bob + (t % 2) * 3, 5, 5, fill=PINK, outline=OL, w=1)
    elif side:
        sw = 5 if f == 1 else (-5 if f == 2 else 0)
        x = 36 + sw * sgn
        p.ell(x, 50 + bob, 6, 8, fill=OL)
        p.ell(x, 50 + bob, 4.6, 6.6, fill=WHITE)
        p.ell(x, 56 + bob, 4, 4, fill=PINK, outline=OL, w=1)
    else:
        for sx, s2 in ((-1, 1 if f == 2 else 0), (1, 1 if f == 1 else 0)):
            x = 36 + sx * 17
            lift = -4 * s2
            p.ell(x, 51 + bob + lift, 6.5, 8.5, fill=OL)
            p.ell(x, 51 + bob + lift, 5, 7, fill=WHITE)
            p.ell(x, 58 + bob + lift, 4.6, 4.6, fill=PINK, outline=OL, w=1)
    # head
    hx = 36 + (2 * sgn if side else 0)
    p.ell(hx, 29 + bob, 22.5, 21.5, fill=OL)
    p.ell(hx, 29 + bob, 20.5, 19.5, fill=WHITE)
    p.ell(hx + 5, 33 + bob, 17, 15, fill=WSH)
    p.ell(hx - 3, 29 + bob, 17.5, 17, fill=WHITE)
    p.ell(hx - 9, 18 + bob, 6, 3.5, fill=(255, 255, 255, 255))
    if dirn == "d":
        p.rect(hx - 15, 22 + bob, hx + 15, 42 + bob, fill=OL, r=10)
        p.rect(hx - 13.5, 23.5 + bob, hx + 13.5, 40.5 + bob, fill=SKIN, r=9)
        for ex in (-6, 6):
            p.ell(hx + ex, 32 + bob, 3.4, 5.6, fill=OL)
            p.ell(hx + ex - 0.8, 30 + bob, 1.2, 1.8, fill=WHITE)
    elif dirn in ("l", "r"):
        fx0 = hx + sgn * 2
        p.rect(min(fx0 - 1, fx0 + sgn * 17), 22 + bob, max(fx0 + 12, fx0 + sgn * 17) if sgn > 0 else fx0 + 1, 42 + bob,
               fill=OL, r=10)
        x0, x1 = (hx - 17, hx + 1) if sgn < 0 else (hx - 1, hx + 17)
        p.rect(x0 + 1.5, 23.5 + bob, x1 - 1.5, 40.5 + bob, fill=SKIN, r=8.5)
        for ex in (4, 12):
            e = hx + sgn * ex
            p.ell(e, 32 + bob, 3.2, 5.4, fill=OL)
            p.ell(e - 0.7 * sgn, 30 + bob, 1.1, 1.7, fill=WHITE)
    else:
        p.rect(hx - 10, 36 + bob, hx + 10, 40 + bob, fill=WSH, r=2)
    # antenna
    p.line([(hx, 9 + bob), (hx + 1, 4 + bob)], OL, 3)
    p.ell(hx + 1, 4 + bob, 4.4, 4.4, fill=OL)
    p.ell(hx + 1, 4 + bob, 3.2, 3.2, fill=PINK)
    p.ell(hx, 3 + bob, 1.1, 1.1, fill=WHITE)
    return down(p.img)


def spin_death(frames=10):
    # Bomber spins on the spot while sinking and fading, the classic death twirl.
    base = bomber_sprite("d", 0)
    out = []
    for i in range(frames):
        t = i / (frames - 1)
        im = base.copy()
        im = im.rotate(-t * 720, resample=Image.BICUBIC)
        sc = 1 - 0.55 * t
        sz = max(8, int(T * sc))
        im = im.resize((sz, sz), Image.BILINEAR)
        c = Image.new("RGBA", (T, T), (0, 0, 0, 0))
        c.alpha_composite(im, ((T - sz) // 2, T - sz - 4))
        if i >= frames - 3:
            a = c.getchannel("A").point(lambda v: int(v * (1.0 - (i - (frames - 4)) * 0.3)))
            c.putalpha(a)
        out.append(c)
    return out


# ---------------------------------------------------------------------------------------------- enemies
def eyes(p, cx, cy, look, spread, size=6.5, angry=False):
    dx, dy = {"d": (0, 1.8), "u": (0, -2), "l": (-2.4, 0), "r": (2.4, 0)}[look]
    for sx in (-1, 1):
        x = cx + sx * spread
        p.ell(x, cy, size, size * 1.15, fill=OL)
        p.ell(x, cy, size - 1.3, size * 1.15 - 1.3, fill=WHITE)
        p.ell(x + dx, cy + dy, size * 0.5, size * 0.6, fill=OL)
        p.ell(x + dx - 1, cy + dy - 1.5, 1.2, 1.2, fill=WHITE)
        if angry:
            p.line([(x - sx * 7, cy - size - 3 + (3 if sx > 0 else 0) * 0), (x + sx * 5, cy - size + 3)], OL, 3)


def balloon(look, f):
    p = Pen(canvas())
    sq = [0, 1][f]
    rx, ry = (26 - sq * 2, 23 + sq * 2)
    p.ell(36, 65, 20, 4, fill=(0, 0, 0, 90))
    p.ell(36, 38, rx + 2, ry + 2, fill=OL)
    p.ell(36, 38, rx, ry, fill=(255, 120, 168, 255))
    p.ell(40, 46, rx - 5, ry - 7, fill=(246, 92, 146, 255))
    p.ell(26, 24, 8, 5, fill=(255, 205, 225, 255))
    eyes(p, 36, 36, look, 9)
    p.ell(36, 49, 4.4, 2.8, fill=OL)
    p.poly([(36, 61), (31, 68), (41, 68)], fill=(255, 100, 150, 255), outline=OL, w=1.2)
    return down(p.img)


def onil(look, f):
    p = Pen(canvas())
    wob = [-1.5, 1.5][f]
    p.ell(36, 65, 20, 4, fill=(0, 0, 0, 90))
    pts = [(36 + wob, 3), (29, 22), (17, 34), (14, 46), (22, 60), (36, 64), (50, 60), (58, 46), (55, 34), (43, 22)]
    p.poly(pts, fill=(82, 150, 255, 255), outline=OL, w=3)
    p.ell(36, 46, 20, 15, fill=(60, 120, 235, 255))
    p.ell(27, 30, 5, 8, fill=(180, 215, 255, 255))
    eyes(p, 36, 40, look, 8.5, 6, angry=True)
    p.rect(30, 53, 42, 58, fill=OL, r=2)
    return down(p.img)


def dahl(look, f):
    p = Pen(canvas())
    p.ell(36, 65, 21, 4, fill=(0, 0, 0, 90))
    lift = [0, -3][f]
    p.ell(26, 62 + (lift if f == 0 else 0), 8, 5, fill=OL)
    p.ell(46, 62 + (lift if f == 1 else 0), 8, 5, fill=OL)
    p.ell(36, 38, 27, 24, fill=OL)
    p.ell(36, 38, 25, 22, fill=(255, 150, 30, 255))
    p.ell(36, 46, 22, 14, fill=(240, 118, 20, 255))
    for x in (20, 36, 52):
        p.poly([(x - 6, 20), (x, 3 + (x == 36) * -1), (x + 6, 20)], fill=(255, 220, 40, 255), outline=OL, w=2)
    p.ell(26, 26, 7, 4, fill=(255, 220, 140, 255))
    eyes(p, 36, 37, look, 9, 6.2, angry=True)
    p.rect(27, 49, 45, 55, fill=OL, r=2)
    for x in (31, 36, 41):
        p.rect(x - 1, 49, x + 1, 52, fill=WHITE)
    return down(p.img)


def ovape(look, f):
    p = Pen(canvas())
    bob = [0, -2][f]
    p.ell(36, 67, 18, 3.5, fill=(0, 0, 0, 70))
    top = 12 + bob
    pts = [(12, 40 + bob)]
    for i in range(0, 11):
        a = math.pi + math.pi * i / 10
        pts.append((36 + 24 * math.cos(a), 38 + bob + 26 * math.sin(a)))
    pts.append((60, 40 + bob))
    base = 62 + bob
    waves = 5
    for i in range(waves * 2 + 1):
        x = 60 - i * 48 / (waves * 2)
        y = base + (5 if (i + f) % 2 == 0 else -3)
        pts.append((x, y))
    p.poly(pts, fill=(176, 100, 236, 255), outline=OL, w=3)
    p.ell(36, 38 + bob, 18, 14, fill=(196, 128, 248, 255))
    p.ell(26, 26 + bob, 6, 4, fill=(236, 210, 255, 255))
    dx = {"l": -2, "r": 2}.get(look, 0)
    for sx in (-1, 1):
        p.ell(36 + sx * 9 + dx, 38 + bob, 5.8, 8, fill=OL)
        p.ell(36 + sx * 9 + dx, 38 + bob, 4.4, 6.6, fill=(255, 240, 70, 255))
        p.ell(36 + sx * 9 + dx + dx * 0.4, 38 + bob + 1, 2, 3.4, fill=OL)
    p.ell(36 + dx, 53 + bob, 4, 3, fill=OL)
    return down(p.img)


ENEMIES = {"balloon": balloon, "onil": onil, "dahl": dahl, "ovape": ovape}


def enemy_death(img):
    # White flash, then squash, then a puff of sparks.
    w = img.copy()
    a = w.getchannel("A")
    white = Image.merge("RGBA", (a.point(lambda v: 255), a.point(lambda v: 255), a.point(lambda v: 255), a))
    out = []
    flash = img.copy()
    flash = Image.composite(white, flash, a.point(lambda v: 150 if v else 0))
    out.append(flash)
    for sx, sy in ((1.12, 0.62), (1.3, 0.3)):
        sz = (int(T * sx), max(4, int(T * sy)))
        s = white.resize(sz, Image.BILINEAR)
        c = Image.new("RGBA", (T, T), (0, 0, 0, 0))
        c.alpha_composite(s.crop((max(0, (sz[0] - T) // 2), 0, max(0, (sz[0] - T) // 2) + min(T, sz[0]), sz[1])),
                          (max(0, (T - sz[0]) // 2), T - sz[1] - 4))
        out.append(c)
    for rad, sz in ((20, 5), (28, 4)):
        c = Image.new("RGBA", (T * SS, T * SS), (0, 0, 0, 0))
        p = Pen(c)
        for k in range(8):
            ang = k * math.pi / 4 + 0.4
            x, y = 36 + math.cos(ang) * rad, 44 + math.sin(ang) * rad * 0.8
            col = (255, 240, 120, 255) if k % 2 else (255, 255, 255, 255)
            p.poly([(x, y - sz), (x + sz * 0.5, y), (x, y + sz), (x - sz * 0.5, y)], fill=col)
        out.append(down(c))
    return out


# ---------------------------------------------------------------------------------------------- packing
def to_rle(img):
    # Opaque runs per row; the runtime copies each run into the tile buffer, transparent pixels stay untouched.
    a = img.getchannel("A").point(lambda v: 255 if v >= 120 else 0)
    rgb = img.convert("RGB")
    px = array("H")
    it = iter(rgb.tobytes())
    for r, g, b in zip(it, it, it):
        px.append((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
    al = a.tobytes()
    rows = []
    for y in range(img.height):
        runs = []
        x = 0
        while x < img.width:
            if al[y * img.width + x]:
                x0 = x
                while x < img.width and al[y * img.width + x]:
                    x += 1
                runs.append((x0, px[y * img.width + x0:y * img.width + x].tobytes()))
            else:
                x += 1
        if runs:
            rows.append((y, runs))
    return rows


def flat(img, bg=(0, 0, 0)):
    base = Image.new("RGBA", img.size, bg + (255,))
    base.alpha_composite(img)
    return pack(base.convert("RGB"))[2]


def main():
    out = {"themes": []}
    for th in THEMES:
        fl = [floor_tile(th, 0), floor_tile(th, 1)]
        br = brick_tile(th)
        d = {}
        for v in (0, 1):
            d["floor%d" % v] = flat(fl[v])
        d["pillar"] = flat(pillar_tile(th))
        d["wall"] = flat(wall_tile(th))
        d["brick"] = flat(br)
        for i in range(5):
            d["crumb%d" % i] = flat(crumble_tile(th, i, br, fl[0]))
        for v in (0, 1):
            for fr in range(4):
                s = fl[v].copy()
                s.alpha_composite(bomb_sprite(fr))
                d["bomb%d_%d" % (fr, v)] = flat(s)
            for k in "FBS":
                for b in (0, 1):
                    s = fl[v].copy()
                    s.alpha_composite(item_sprite(k, b))
                    d["item%s%d_%d" % (k, b, v)] = flat(s)
            for st in range(3):
                s = fl[v].copy()
                s.alpha_composite(door_sprite(st, th))
                d["door%d_%d" % (st, v)] = flat(s)
            for m in range(16):
                for fr in range(3):
                    s = fl[v].copy()
                    s.alpha_composite(flame_sprite(m, fr))
                    d["flame%d_%d_%d" % (m, fr, v)] = flat(s)
        out["themes"].append(d)

    dirs = "dulr"
    out["walk"] = [[to_rle(bomber_sprite(dr, f)) for f in range(3)] for dr in dirs]
    out["win"] = [to_rle(bomber_sprite("d", 0, "win", t)) for t in range(2)]
    out["die"] = [to_rle(i) for i in spin_death()]
    out["enemy"] = {}
    for name, fn in ENEMIES.items():
        out["enemy"][name] = {"walk": [[to_rle(fn(dr, f)) for f in range(2)] for dr in dirs],
                              "die": [to_rle(i) for i in enemy_death(fn("d", 0))]}
    head = bomber_sprite("d", 0).crop((8, 0, 64, 52)).resize((48, 44), Image.LANCZOS)
    out["head"] = pack(Image.alpha_composite(Image.new("RGBA", head.size, (0, 0, 0, 255)), head).convert("RGB"))
    out["icons"] = []
    for k in "BFS":
        ic = item_sprite(k, 0).resize((48, 48), Image.LANCZOS)
        out["icons"].append(pack(Image.alpha_composite(Image.new("RGBA", ic.size, (0, 0, 0, 255)), ic).convert("RGB")))
    save_bundle("g_bomber.bin", out)
    import os
    print("g_bomber.bin", os.path.getsize("g_bomber.bin"), "bytes")


if __name__ == "__main__":
    main()
