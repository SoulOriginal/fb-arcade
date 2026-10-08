# Build script for the Turbo Tunnel game: draws every layer and sprite procedurally and writes g_turbo.bin.
# The scene is a 480x270 grid of "virtual pixels" (vpx), each 4x4 screen pixels. Backgrounds are tileable
# 480-vpx strips (stored twice, so any 480-wide window is one slice); sprites are stored as per-row opaque
# runs so the game can patch them into the row bytes with correct transparency.
# Everything is snapped to one small NES-like palette, because the look of the original is a handful of
# saturated colours with dark outlines, not smooth shading.
import math
import random
from PIL import Image, ImageDraw, ImageChops, ImageFilter, ImageEnhance
from buildlib import pack, save_bundle, rgb565

SS = 4                      # supersampling used to draw sprites
NV = 480                    # scene width in vpx
TOP, BOT = 32, 270          # first scene row (HUD above it), end row
NR = BOT - TOP
LANE_Y = (190, 214)         # wheel contact row of the far and the near lane
TRACK_TOP, TRACK_BOT = 168, 228
# name, first row, end row, parallax factor (1.0 = speed of the track the bike rides on)
BANDS = [("ceil", 32, 62, 0.55), ("wall", 62, 168, 0.30), ("track", 168, 228, 1.0), ("veins", 228, 270, 1.7)]
PULSE_ROWS = 168 - TOP      # rows of the ceiling and wall that pulse between two frames

OUT = (22, 0, 30)
PAL = [
    (0, 0, 0), OUT, (255, 255, 255),
    (84, 0, 28), (150, 16, 44), (196, 30, 60), (232, 70, 110), (250, 140, 170), (255, 205, 220),      # reds / pinks
    (56, 0, 90), (116, 24, 140), (176, 52, 190), (228, 120, 232),                                      # purples
    (130, 28, 12), (210, 66, 16), (250, 116, 36), (255, 176, 90), (255, 214, 150),                      # orange track
    (60, 4, 16), (96, 8, 28),                                                                          # dark floor
    (0, 60, 80), (0, 130, 146), (36, 204, 196), (150, 246, 236),                                       # teal
    (16, 80, 24), (56, 160, 40), (136, 226, 84),                                                       # green
    (20, 36, 130), (56, 96, 236), (140, 184, 255),                                                     # blue
    (252, 220, 60), (255, 150, 30), (120, 124, 140), (190, 194, 208), (110, 60, 30), (170, 110, 60),   # yellow, grey, brown
]
_pal_img = Image.new("P", (1, 1))
_flat = []
for _c in PAL:
    _flat += list(_c)
_pal_img.putpalette(_flat + [0] * (768 - len(_flat)))


def snap_image(img):
    return img.convert("RGB").quantize(palette=_pal_img, dither=Image.Dither.NONE).convert("RGB")


def nearest(c):
    return min(PAL, key=lambda p: (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2)


# ---- background bands -----------------------------------------------------------------------------

def worm(d, rnd, x, y, heading, steps, curl, y0, y1, outline, body, wout, wbody, hi=None, step_len=3.0):
    # One squiggle: a random walk with smoothly changing curvature, drawn three times shifted by the tile
    # width so the strip wraps without a seam. Outline first, then body, then a thin highlight.
    pts, turn = [(x, y)], 0.0
    for _ in range(steps):
        turn = max(-curl, min(curl, turn + rnd.uniform(-curl * 0.45, curl * 0.45)))
        heading += turn
        x += math.cos(heading) * step_len
        y += math.sin(heading) * step_len
        if y < y0 or y > y1:
            heading = -heading
            y = max(y0, min(y1, y))
        pts.append((x, y))
    for dx in (-NV, 0, NV):
        shifted = [(px + dx, py) for px, py in pts]
        d.line(shifted, fill=outline, width=wout, joint="curve")
        d.line(shifted, fill=body, width=wbody, joint="curve")
        if hi is not None:
            d.line([(px + dx - 1, py - 1) for px, py in pts], fill=hi, width=1)


def band_wall(rnd, bright):
    h = 168 - 62
    img = Image.new("RGB", (NV, h), (170, 22, 52))
    d = ImageDraw.Draw(img)
    for i in range(120):
        body = rnd.choice([(232, 70, 110), (232, 70, 110), (250, 140, 170), (210, 50, 90)])
        worm(d, rnd, rnd.uniform(0, NV), rnd.uniform(0, h), rnd.uniform(0, 6.28), rnd.randint(12, 26), 0.42, 2, h - 2,
             (84, 0, 28), body, 9, 6, hi=(255, 205, 220), step_len=3.5)
    # dark shadow where the wall meets the track
    for r in range(h - 7, h):
        d.line([(0, r), (NV, r)], fill=(84, 0, 28) if r >= h - 3 else (130, 8, 40))
    img = ImageEnhance.Brightness(img).enhance(1.14 if bright else 1.0)
    return snap_image(img)


def band_ceiling(rnd, bright):
    h = 62 - 32
    img = Image.new("RGB", (NV, h), (150, 16, 44))
    d = ImageDraw.Draw(img)
    base = (116, 24, 140)
    edge = [(x, h - 8 + 3.2 * math.sin(x * 2 * math.pi / 60) + 2.2 * math.sin(x * 2 * math.pi / 40 + 1.0)) for x in range(0, NV + 1, 2)]
    d.polygon([(0, 0), (NV, 0)] + edge[::-1], fill=base)
    for i in range(46):
        body = rnd.choice([(176, 52, 190), (228, 120, 232), (176, 52, 190)])
        worm(d, rnd, rnd.uniform(0, NV), rnd.uniform(2, h - 12), rnd.choice((0.0, 3.14)) + rnd.uniform(-0.5, 0.5), rnd.randint(8, 18), 0.4, 1, h - 11,
             (56, 0, 90), body, 8, 5, hi=(250, 190, 250))
    d.line(edge, fill=(56, 0, 90), width=3)
    d.line([(x, y - 3) for x, y in edge], fill=(228, 120, 232), width=1)
    img = ImageEnhance.Brightness(img).enhance(1.12 if bright else 1.0)
    return snap_image(img)


def band_track(rnd):
    h = TRACK_BOT - TRACK_TOP
    img = Image.new("RGB", (NV, h), (210, 66, 16))
    d = ImageDraw.Draw(img)
    cols = [(255, 176, 90)] * 3 + [(250, 116, 36)] * 4
    for r in range(h):
        if r == 0:
            c = (84, 0, 28)
        elif r <= 3:
            c = (255, 214, 150) if r == 1 else (255, 176, 90)
        elif r < 8:
            c = (250, 116, 36)
        else:
            f = (r - 8) / (h - 8)
            band = (r // 3) % 3
            c = [(210, 66, 16), (232, 88, 24), (210, 66, 16)][band] if f < 0.7 else [(160, 40, 14), (130, 28, 12), (160, 40, 14)][band]
        d.line([(0, r), (NV, r)], fill=c)
    for _ in range(150):
        x, y = rnd.randrange(NV), rnd.randrange(9, h)
        ln = rnd.randrange(6, 26)
        c = rnd.choice([(250, 116, 36), (160, 40, 14), (232, 88, 24)])
        for dx in (-NV, 0, NV):
            d.line([(x + dx, y), (x + dx + ln, y)], fill=c)
    # dark oval pits dotted along the track, like the one in the original
    for x in range(30, NV, 150):
        y = rnd.randrange(30, h - 8)
        for dx in (-NV, 0, NV):
            d.ellipse([x + dx - 6, y - 2, x + dx + 6, y + 3], fill=(84, 0, 28))
            d.ellipse([x + dx - 5, y - 2, x + dx + 5, y + 1], fill=(60, 4, 16))
    d.line([(0, h - 1), (NV, h - 1)], fill=(84, 0, 28))
    d.line([(0, h - 2), (NV, h - 2)], fill=(130, 28, 12))
    return snap_image(img)


def band_veins(rnd):
    h = BOT - 228
    img = Image.new("RGB", (NV, h), (96, 8, 28))
    d = ImageDraw.Draw(img)
    for _ in range(60):
        x = rnd.uniform(0, NV)
        worm(d, rnd, x, rnd.uniform(0, 6), rnd.uniform(0.3, 2.8), rnd.randint(10, 24), 0.35, 0, h - 1,
             (60, 4, 16), rnd.choice([(232, 70, 110), (250, 140, 170), (196, 30, 60)]), 4, 2)
    d.line([(0, 0), (NV, 0)], fill=(60, 4, 16))
    d.line([(0, 1), (NV, 1)], fill=(60, 4, 16))
    return snap_image(img)


def strip_rows(img):
    # 480-vpx tile -> list of byte rows of the doubled strip, every vpx expanded to 4 screen pixels.
    w, h = img.size
    dbl = Image.new("RGB", (w * 2, h))
    dbl.paste(img, (0, 0))
    dbl.paste(img, (w, 0))
    big = dbl.resize((w * 2 * 4, h), Image.NEAREST)
    pw, ph, data = pack(big)
    rb = pw * 2
    return [data[j * rb:(j + 1) * rb] for j in range(ph)]


# ---- sprites --------------------------------------------------------------------------------------------

def canvas(w, h):
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def poly(d, pts, fill):
    d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)


def line(d, pts, width, fill):
    # thick polyline with round joints/caps (PIL's own joints leave gaps at sharp angles)
    pts = [(x * SS, y * SS) for x, y in pts]
    d.line(pts, fill=fill, width=int(width * SS))
    r = width * SS / 2
    for x, y in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def disc(d, cx, cy, r, fill):
    d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=fill)


def rect(d, x0, y0, x1, y1, fill):
    d.rectangle([x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1], fill=fill)


def to_sprite(img, outline=True, threshold=110):
    w, h = img.size[0] // SS, img.size[1] // SS
    small = img.resize((w, h), Image.BOX)
    alpha = small.getchannel("A").point(lambda v: 255 if v >= threshold else 0)
    if outline:
        ring = ImageChops.subtract(alpha.filter(ImageFilter.MaxFilter(3)), alpha)
        base = Image.new("RGBA", (w, h), OUT + (255,))
        base.putalpha(ring)
        small.putalpha(alpha)
        base.alpha_composite(small)
        small = base
        alpha = small.getchannel("A")
    else:
        small.putalpha(alpha)
    px, al = small.convert("RGB").load(), alpha.load()
    cache = {}
    rows = []
    for y in range(h):
        runs, x = [], 0
        while x < w:
            if al[x, y]:
                x0, buf = x, bytearray()
                while x < w and al[x, y]:
                    c = px[x, y]
                    if c not in cache:
                        cache[c] = rgb565(*nearest(c)).to_bytes(2, "little") * 4
                    buf += cache[c]
                    x += 1
                runs.append((x0, bytes(buf)))
            else:
                x += 1
        rows.append(runs)
    return dict(w=w, h=h, rows=rows)


SKIN, SKIN_D, SKIN_L = (56, 160, 40), (16, 80, 24), (136, 226, 84)
BELLY, SHORTS, LEATHER = (255, 214, 150), (110, 60, 30), (170, 110, 60)
T0, T1, T2, T3 = (0, 60, 80), (0, 130, 146), (36, 204, 196), (150, 246, 236)
RED = (210, 30, 60)

TOAD_RIDE = dict(head=(40, 9), hip=(24, 22), shoulder=(34, 15), elbow=(42, 18), hand=(49, 21), knee=(33, 27), foot=(38, 33))
TOAD_DUCK = dict(head=(43, 17), hip=(24, 24), shoulder=(36, 21), elbow=(44, 24), hand=(51, 26), knee=(33, 29), foot=(38, 34))


def draw_toad(d, t, flutter=0, wild=False):
    hx, hy = t["head"]
    line(d, [(t["hip"][0], t["hip"][1]), (t["knee"][0], t["knee"][1]), (t["foot"][0], t["foot"][1])], 4.4, SKIN_D)
    disc(d, t["foot"][0] + 1, t["foot"][1] + 0.5, 2.6, LEATHER)
    line(d, [t["hip"], t["shoulder"]], 8.5, SKIN)
    line(d, [(t["hip"][0] + 2, t["hip"][1] - 1.5), (t["shoulder"][0] + 1, t["shoulder"][1] + 1.5)], 3.4, BELLY)
    disc(d, t["hip"][0], t["hip"][1] + 0.5, 4.6, SHORTS)
    line(d, [t["shoulder"], t["elbow"], t["hand"]], 3.8, SKIN)
    line(d, [t["shoulder"], t["elbow"]], 1.4, SKIN_L)
    disc(d, t["hand"][0], t["hand"][1], 2.8, LEATHER)
    # head: wide toad skull, eye bumps under the shades, big grin
    d.ellipse([(hx - 6.5) * SS, (hy - 4.8) * SS, (hx + 6.8) * SS, (hy + 5) * SS], fill=SKIN)
    disc(d, hx + 1, hy - 4.6, 2.3, SKIN_L)
    disc(d, hx + 5, hy - 3.6, 1.9, SKIN_L)
    poly(d, [(hx - 1.5, hy - 3), (hx + 8, hy - 2.3), (hx + 7.6, hy + 0.6), (hx + 1, hy + 0.8)], (14, 14, 22))
    line(d, [(hx + 1, hy - 2.2), (hx + 3.5, hy - 2.0)], 0.9, (190, 240, 255))
    poly(d, [(hx + 0.5, hy + 2.2), (hx + 7.8, hy + 1.4), (hx + 7, hy + 4.3), (hx + 2.2, hy + 4.4)], (96, 8, 28))
    line(d, [(hx + 1.5, hy + 2.1), (hx + 7.4, hy + 1.5)], 1.0, (255, 255, 255))
    if wild:
        poly(d, [(hx + 2, hy + 2.8), (hx + 7.2, hy + 2.3), (hx + 6.6, hy + 4.8), (hx + 3, hy + 4.8)], (96, 8, 28))


def draw_bike_body(d, spin, wreck=False):
    # Teal speeder seen from the side: long swept hull, one big rear wheel, twin exhausts, headlamp.
    for cx, cy, r in ((17, 36, 8.2), (58, 39, 5.4)):
        disc(d, cx, cy, r, (30, 24, 40))
        disc(d, cx, cy, r - 2.4, (120, 124, 140))
        disc(d, cx, cy, r - 3.6, (36, 204, 196) if r > 6 else (150, 246, 236))
        for k in range(4):
            a = math.radians(spin + k * 90)
            line(d, [(cx, cy), (cx + (r - 2.4) * math.cos(a), cy + (r - 2.4) * math.sin(a))], 0.9, (30, 24, 40))
    line(d, [(50, 25), (58, 39)], 2.0, (190, 194, 208))
    poly(d, [(3, 30), (10, 24), (26, 22), (40, 24), (54, 28), (67, 34), (63, 38), (44, 36), (26, 38), (10, 38), (3, 34)], T2)
    poly(d, [(10, 24), (26, 22), (40, 24), (54, 28), (67, 34), (50, 29), (36, 27), (20, 27)], T3)
    poly(d, [(3, 34), (10, 38), (26, 38), (44, 36), (63, 38), (67, 34), (52, 35), (36, 33), (20, 34), (8, 34)], T1)
    line(d, [(8, 31), (60, 33)], 1.0, T0)
    poly(d, [(8, 19), (24, 16), (27, 24), (10, 26)], T1)
    rect(d, 0, 28, 7, 31, (190, 194, 208))
    rect(d, 0, 32, 7, 35, (120, 124, 140))
    rect(d, 24, 32, 38, 36, T0)
    disc(d, 65, 34, 2.2, (252, 220, 60))
    line(d, [(46, 21), (50, 15)], 1.8, (190, 194, 208))
    if wreck:
        line(d, [(30, 20), (40, 12)], 1.5, (60, 60, 70))


def bike_sprite(pose, frame):
    img, d = canvas(72, 48)
    draw_bike_body(d, frame * 45)
    draw_toad(d, TOAD_DUCK if pose == "duck" else TOAD_RIDE)
    ang = {"up": 12, "down": -10, "lean_far": 5, "lean_near": -5}.get(pose, 0)
    if ang:
        img = img.rotate(ang, resample=Image.BICUBIC, center=(36 * SS, 44 * SS))
    return to_sprite(img)


def flame_sprite(length, frame, boost):
    img, d = canvas(40, 16)
    core, mid, outer = ((190, 250, 255), (80, 200, 255), (40, 90, 255)) if boost else ((255, 250, 200), (252, 220, 60), (255, 150, 30))
    cx, cy = 38, 8
    for scale, col in ((1.0, outer), (0.72, mid), (0.42, core)):
        ln = length * scale + frame * 1.5
        hw = 3.6 * scale + 0.6
        poly(d, [(cx, cy - hw), (cx - ln * 0.6, cy - hw * 0.8 + frame * 0.4), (cx - ln, cy + (frame - 0.5)), (cx - ln * 0.6, cy + hw * 0.8), (cx, cy + hw)], col)
    return to_sprite(img, outline=False, threshold=90)


def spin_sprites(draw_fn, w, h, n=8):
    out = []
    for k in range(n):
        img, d = canvas(w, h)
        draw_fn(d)
        img = img.rotate(-360 * k / n, resample=Image.BICUBIC, center=(w * SS // 2, h * SS // 2))
        out.append(to_sprite(img))
    return out


def burst_sprite(k):
    img, d = canvas(44, 44)
    pts = []
    n = 12
    for i in range(2 * n):
        r = (20 if i % 2 == 0 else 10) + (3 if (i + k) % 3 == 0 else 0)
        a = math.pi * i / n + k * 0.1
        pts.append((22 + r * math.cos(a), 22 + r * math.sin(a)))
    poly(d, pts, (255, 150, 30))
    poly(d, [(22 + (x - 22) * 0.7, 22 + (y - 22) * 0.7) for x, y in pts], (252, 220, 60))
    poly(d, [(22 + (x - 22) * 0.4, 22 + (y - 22) * 0.4) for x, y in pts], (255, 255, 255))
    return to_sprite(img, outline=False)


F_, N_ = LANE_Y


def pillar_sprite(flash):
    # Tall rounded pink pillar with a white highlight: half the track wide, so it fills one lane.
    w, h = 16, 42
    img, d = canvas(w, h)
    body, shade, hi = ((250, 140, 170), (232, 70, 110), (255, 255, 255)) if not flash else ((255, 255, 255), (252, 220, 60), (255, 255, 255))
    d.rounded_rectangle([1 * SS, 1 * SS, (w - 1) * SS - 1, (h + 7) * SS], radius=6 * SS, fill=body)
    d.rounded_rectangle([(w - 6) * SS, 3 * SS, (w - 1) * SS - 1, (h + 7) * SS], radius=3 * SS, fill=shade)
    d.rounded_rectangle([3 * SS, 4 * SS, 6 * SS, (h - 9) * SS], radius=2 * SS, fill=hi)
    d.ellipse([1 * SS, (h - 5) * SS, (w - 1) * SS, (h + 2) * SS], fill=shade)
    return to_sprite(img.crop((0, 0, w * SS, h * SS)))


def pod_sprite(frame):
    # Rat pod: a yellow capsule on a spring with a rat peeking out of the dome.
    w, h = 24, 30
    img, d = canvas(w, h)
    bob = 2 * frame
    line(d, [(12, h - 2), (12, h - 8 - bob)], 2.0, (120, 124, 140))
    d.ellipse([1 * SS, (8 - bob) * SS, (w - 1) * SS, (h - 7 - bob) * SS], fill=(252, 220, 60))
    d.pieslice([1 * SS, (8 - bob) * SS, (w - 1) * SS, (h - 7 - bob) * SS], 200, 340, fill=(255, 255, 255))
    d.ellipse([4 * SS, (11 - bob) * SS, 19 * SS, (22 - bob) * SS], fill=(20, 36, 130))
    disc(d, 11.5, 17 - bob, 4.2, (170, 110, 60))
    disc(d, 8.0, 12.5 - bob, 2.2, (250, 140, 170))
    disc(d, 15.0, 12.5 - bob, 2.2, (250, 140, 170))
    disc(d, 10, 16.5 - bob, 0.9, (255, 255, 255))
    disc(d, 14, 16.5 - bob, 0.9, (255, 255, 255))
    rect(d, 10, 19.5 - bob, 14, 21 - bob, (255, 255, 255))
    rect(d, 4, h - 5, w - 4, h - 1, (120, 124, 140))
    return to_sprite(img)


def low_wall_sprite(flash):
    # Low wall across the whole track: lies from the far lane edge to the near lane edge.
    w, h = 14, (N_ - F_) + 18
    img, d = canvas(w, h)
    a, b = ((255, 255, 255), (210, 30, 60)) if not flash else ((252, 220, 60), (255, 255, 255))
    rect(d, 1, 0, w - 1, h, a)
    for y in range(-14, h, 9):
        poly(d, [(1, y), (w - 1, y + 6), (w - 1, y + 10), (1, y + 4)], b)
    rect(d, 1, 0, 3, h, (255, 255, 255) if not flash else (252, 220, 60))
    rect(d, w - 3, 0, w - 1, h, (120, 124, 140))
    return to_sprite(img)


def float_wall_sprite():
    # Blue slab hanging in the air over the whole track: the bike has to stay low and ride under it.
    w, h = 14, (N_ - F_) + 12
    img, d = canvas(w, h)
    rect(d, 1, 0, w - 1, h, (56, 96, 236))
    rect(d, 1, 0, 4, h, (140, 184, 255))
    rect(d, w - 4, 0, w - 1, h, (20, 36, 130))
    for y in range(4, h, 8):
        rect(d, 1, y, w - 1, y + 2, (20, 36, 130))
    return to_sprite(img)


def shadow_sprite(w, h):
    img, d = canvas(w, h)
    d.ellipse([0, 0, w * SS - 1, h * SS - 1], fill=(60, 4, 16))
    return to_sprite(img, outline=False, threshold=100)


def ramp_sprite(w=50, rise=22):
    # Trampoline ramp over the whole track: teal slab sloping up to the right with chevron arrows.
    h = rise + (N_ - F_) + 2
    img, d = canvas(w, h)
    nb = h - 1
    poly(d, [(0, nb), (w, nb - rise), (w, nb - rise - (N_ - F_)), (0, nb - (N_ - F_))], T2)
    poly(d, [(0, nb), (w, nb - rise), (w, nb)], T0)
    for k in range(6, w - 6, 11):
        yk = lambda x: nb - rise * x / w
        poly(d, [(k, yk(k) - 2), (k + 5, yk(k + 5) - 2), (k + 8, yk(k + 8) - 9), (k + 4, yk(k + 4) - 9)], (255, 255, 255))
        poly(d, [(k, yk(k) - 12), (k + 5, yk(k + 5) - 12), (k + 8, yk(k + 8) - 19), (k + 4, yk(k + 4) - 19)], (252, 220, 60))
    line(d, [(0, nb - (N_ - F_)), (w, nb - rise - (N_ - F_))], 1.2, T3)
    return to_sprite(img)


def fpad_sprite(frame):
    # Floating ramp: a springy teal pad hovering above the track; touching it from the air launches the bike.
    w, h = 44, (N_ - F_) + 12
    img, d = canvas(w, h)
    a, b = ((252, 220, 60), (255, 255, 255)) if frame == 0 else ((255, 255, 255), (252, 220, 60))
    poly(d, [(6, 1), (w - 6, 1), (w - 1, h - 8), (1, h - 8)], T2)
    for i in range(5):
        x0 = 8 + i * 6
        poly(d, [(x0, 2), (x0 + 3, 2), (x0 + 2, h - 9), (x0 - 1, h - 9)], a if i % 2 == 0 else b)
    rect(d, 1, h - 8, w - 1, h - 3, T0)
    line(d, [(6, 1), (w - 6, 1)], 1.0, T3)
    return to_sprite(img)


def rocket_sprite(frame):
    # Rat on a rocket, flying to the left: rat head up front, red nose, grey body, flame trailing right.
    w, h = 54, 24
    img, d = canvas(w, h)
    poly(d, [(10, 12), (40, 6), (44, 12), (40, 18)], (190, 194, 208))
    poly(d, [(10, 12), (40, 6), (42, 8), (14, 12)], (255, 255, 255))
    poly(d, [(10, 12), (2, 12), (10, 8)], (210, 30, 60))
    poly(d, [(10, 12), (2, 12), (10, 16)], (150, 16, 44))
    poly(d, [(34, 6), (42, 2), (44, 7)], (210, 30, 60))
    poly(d, [(34, 18), (42, 22), (44, 17)], (150, 16, 44))
    disc(d, 22, 7, 4.5, (170, 110, 60))
    disc(d, 18.5, 3.6, 2.0, (250, 140, 170))
    disc(d, 25.5, 3.6, 2.0, (250, 140, 170))
    disc(d, 20, 6.5, 0.9, (255, 255, 255))
    disc(d, 24, 6.5, 0.9, (255, 255, 255))
    ln = 8 + 3 * frame
    poly(d, [(44, 9), (44 + ln, 12), (44, 15)], (255, 150, 30))
    poly(d, [(44, 10.5), (44 + ln * 0.6, 12), (44, 13.5)], (252, 220, 60))
    return to_sprite(img)


def finish_sprite():
    # Checkpoint line across the whole track, with two posts.
    w, h = 12, TRACK_BOT - TRACK_TOP
    img, d = canvas(w, h)
    for yy in range(0, h, 4):
        for xx in range(0, w, 4):
            col = (255, 255, 255) if ((xx // 4) + (yy // 4)) % 2 == 0 else (22, 0, 30)
            rect(d, xx, yy, xx + 4, yy + 4, col)
    return to_sprite(img, outline=False)


def heart(full):
    # Full hearts are solid white; empty ones keep only the outline.
    rows = ["01100110", "11111111", "11111111", "11111111", "01111110", "00111100", "00011000"]
    img = Image.new("RGB", (9, 8), (0, 0, 0))
    px = img.load()

    def on(x, y):
        return 0 <= y < len(rows) and 0 <= x < 8 and rows[y][x] == "1"
    for y in range(len(rows)):
        for x in range(8):
            if on(x, y) and (full or not (on(x - 1, y) and on(x + 1, y) and on(x, y - 1) and on(x, y + 1))):
                px[x, y] = (255, 255, 255)
    return pack(img.resize((9 * 4, 8 * 4), Image.NEAREST))


def main():
    rnd = random.Random(11)
    wall = [band_wall(random.Random(5), b) for b in (False, True)]
    ceil = [band_ceiling(random.Random(6), b) for b in (False, True)]
    track = band_track(random.Random(7))
    veins = band_veins(random.Random(8))

    def compose(w_img, c_img):
        full = Image.new("RGB", (NV, NR))
        full.paste(c_img, (0, 0))
        full.paste(w_img, (0, 62 - TOP))
        full.paste(track, (0, TRACK_TOP - TOP))
        full.paste(veins, (0, 228 - TOP))
        return full

    sheet = [compose(wall[i], ceil[i]) for i in range(2)]
    rows = strip_rows(sheet[0])
    pulse = [strip_rows(s)[:PULSE_ROWS] for s in sheet]
    prev = Image.new("RGB", (NV, NR * 2))
    prev.paste(sheet[0], (0, 0))
    prev.paste(sheet[1], (0, NR))

    spr = dict(
        bike={pose: [bike_sprite(pose, f) for f in range(2)] for pose in ("ride", "up", "down", "duck", "lean_far", "lean_near")},
        flame=[[flame_sprite(ln, f, False) for f in range(2)] for ln in (10, 16, 24)]
        + [[flame_sprite(ln, f, True) for f in range(2)] for ln in (22, 32)],
        toad_spin=spin_sprites(lambda d: draw_toad(d, dict(head=(20, 8), hip=(20, 24), shoulder=(20, 14), elbow=(10, 8),
                                                             hand=(6, 2), knee=(26, 30), foot=(32, 36)), wild=True), 40, 44),
        wreck_spin=spin_sprites(lambda d: draw_bike_body(d, 0, True), 72, 48),
        burst=[burst_sprite(k) for k in range(3)],
        pillar=[pillar_sprite(False), pillar_sprite(True)],
        pod=[pod_sprite(0), pod_sprite(1)],
        low=[low_wall_sprite(False), low_wall_sprite(True)],
        fwall=float_wall_sprite(),
        ramp=ramp_sprite(),
        fpad=[fpad_sprite(0), fpad_sprite(1)],
        rocket=[rocket_sprite(0), rocket_sprite(1)],
        finish=finish_sprite(),
        shadow={w: shadow_sprite(w, 7) for w in (44, 14, 16, 26)},
    )

    sh = Image.new("RGB", (560, 240), (150, 40, 70))
    d = ImageDraw.Draw(sh)

    def show(s, x, y):
        for j, runs in enumerate(s["rows"]):
            for xo, b in runs:
                for i in range(len(b) // 8):
                    v = int.from_bytes(b[i * 8:i * 8 + 2], "little")
                    d.point((x + xo + i, y + j), fill=((v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3))
    x = 5
    for pose in ("ride", "up", "down", "duck", "lean_far", "lean_near"):
        show(spr["bike"][pose][0], x, 5)
        x += 74
    show(spr["flame"][1][0], 460, 20)
    for k in range(3):
        show(spr["toad_spin"][k], 5 + k * 44, 60)
        show(spr["wreck_spin"][k], 150 + k * 76, 55)
    x = 5
    for key in ("pillar", "pod", "low"):
        for s in spr[key]:
            show(s, x, 130)
            x += 30
    show(spr["fwall"], x, 130)
    show(spr["ramp"], x + 20, 130)
    show(spr["fpad"][0], x + 80, 130)
    show(spr["rocket"][0], x + 130, 130)
    show(spr["finish"], x + 200, 130)

    geo = dict(top=TOP, bot=BOT, nv=NV, bands=BANDS, lane_y=LANE_Y, track=(TRACK_TOP, TRACK_BOT), pulse_rows=PULSE_ROWS)
    save_bundle("g_turbo.bin", dict(geo=geo, rows=rows, pulse=pulse, spr=spr, heart=[heart(True), heart(False)]))
    print("saved")


if __name__ == "__main__":
    main()
