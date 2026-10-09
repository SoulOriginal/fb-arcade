# Ishimura environments: parallax wall tiles, floors, window views and props, one look per chapter.
import math, random
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from g_deadspace_art import *

WALL_W, WALL_H = 576, 206      # wall tile (vpx), repeats; the strip adds one screen width for slicing
FLOOR_W, FLOOR_H = 480, 64
SCREEN_W = 480

CHAPTERS = [
    dict(name="NEW ARRIVALS", sub="LANDING BAY", wall=(66, 76, 72), wall2=(48, 56, 54), accent=(224, 176, 40),
         lamp=(255, 190, 90), floor=(54, 58, 58), kind="bay", space="planet"),
    dict(name="INTENSIVE CARE", sub="MEDICAL DECK", wall=(78, 104, 108), wall2=(54, 74, 80), accent=(200, 50, 50),
         lamp=(200, 235, 255), floor=(70, 82, 86), kind="medical", space="stars"),
    dict(name="COURSE CORRECTION", sub="ENGINEERING", wall=(112, 70, 44), wall2=(76, 46, 30), accent=(255, 120, 30),
         lamp=(255, 150, 60), floor=(62, 48, 40), kind="engine", space="reactor"),
    dict(name="ENVIRONMENTAL HAZARD", sub="HYDROPONICS", wall=(42, 84, 56), wall2=(30, 60, 42), accent=(180, 255, 120),
         lamp=(230, 150, 255), floor=(40, 56, 44), kind="hydro", space="planet"),
    dict(name="LETHAL DEVOTION", sub="CREW DECK", wall=(92, 66, 56), wall2=(64, 44, 40), accent=(220, 90, 50),
         lamp=(255, 170, 100), floor=(60, 46, 44), kind="crew", space="stars"),
    dict(name="DEAD SPACE", sub="THE MARKER", wall=(70, 46, 56), wall2=(46, 28, 38), accent=(255, 50, 50),
         lamp=(255, 80, 70), floor=(48, 34, 40), kind="hive", space="marker"),
]


def lin_grad(w, h, top, bot):
    g = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bot), Image.new("RGB", (w, h), top), g)


def noise(img, rnd, amount=10, density=0.08):
    d = ImageDraw.Draw(img)
    w, h = img.size
    for _ in range(int(w * h * density)):
        x, y = rnd.randrange(w), rnd.randrange(h)
        k = rnd.randint(-amount, amount)
        r, g, b = img.getpixel((x, y))[:3]
        d.point((x, y), (max(0, min(255, r + k)), max(0, min(255, g + k)), max(0, min(255, b + k))))


def pipe_h(d, y, th, col, w, x0=0, x1=None, rivets=True):
    x1 = w if x1 is None else x1
    d.rectangle([x0, y, x1, y + th], fill=shade(col, 0.55))
    d.rectangle([x0, y + 1, x1, y + th - 1], fill=col)
    d.rectangle([x0, y + 1, x1, y + max(1, th // 4)], fill=shade(col, 1.45))
    d.rectangle([x0, y + th - max(1, th // 4), x1, y + th - 1], fill=shade(col, 0.7))
    if rivets:
        for x in range(x0 + 20, x1, 72):
            d.rectangle([x, y - 2, x + 5, y + th + 2], fill=shade(col, 0.5))
            d.rectangle([x + 1, y - 1, x + 2, y + th + 1], fill=shade(col, 1.2))


def pipe_v(d, x, th, col, y0, y1):
    d.rectangle([x, y0, x + th, y1], fill=shade(col, 0.55))
    d.rectangle([x + 1, y0, x + th - 1, y1], fill=col)
    d.rectangle([x + 1, y0, x + max(1, th // 4), y1], fill=shade(col, 1.45))
    d.rectangle([x + th - max(1, th // 4), y0, x + th - 1, y1], fill=shade(col, 0.7))


def panels(d, x0, x1, y0, y1, pw, col, seam=None):
    seam = seam or shade(col, 0.55)
    for x in range(x0, x1, pw):
        d.rectangle([x, y0, x + pw - 1, y1], fill=col if ((x // pw) % 2) else shade(col, 0.93))
        d.line([x, y0, x, y1], fill=seam)
        d.line([x + 1, y0, x + 1, y1], fill=shade(col, 1.25))
        for yy in (y0 + 3, y1 - 3):
            d.point((x + 4, yy), shade(col, 1.5))
            d.point((x + pw - 4, yy), shade(col, 1.5))


def window(d, x, y, w, h, frame):
    d.rectangle([x - 5, y - 5, x + w + 4, y + h + 4], fill=shade(frame, 0.5))
    d.rectangle([x - 4, y - 4, x + w + 3, y + h + 3], fill=frame)
    d.rectangle([x - 4, y - 4, x + w + 3, y - 3], fill=shade(frame, 1.5))
    d.rectangle([x - 1, y - 1, x + w, y + h], fill=(0, 0, 0))
    # frame bolts
    for bx in range(x, x + w, 18):
        d.rectangle([bx, y - 3, bx + 1, y - 2], fill=shade(frame, 0.4))
        d.rectangle([bx, y + h + 1, bx + 1, y + h + 2], fill=shade(frame, 0.4))


def lamp(d, em, x, y, col, w=18):
    d.rectangle([x - w // 2 - 1, y, x + w // 2 + 1, y + 5], fill=(30, 30, 34))
    d.rectangle([x - w // 2, y + 1, x + w // 2, y + 4], fill=shade(col, 1.0))
    d.rectangle([x - w // 2 + 2, y + 1, x + w // 2 - 2, y + 2], fill=(255, 255, 240))
    # emissive layer: a soft cone of light under the fixture
    for i in range(10, 0, -1):
        a = int(55 * (1 - i / 10) ** 1.4 + 6)
        em.ellipse([x - w // 2 - i * 4, y - 6, x + w // 2 + i * 4, y + 6 + i * 9], fill=col + (a,))
    em.rectangle([x - w // 2, y + 1, x + w // 2, y + 4], fill=col + (255,))


def hazard(d, x0, x1, y0, y1, col=(224, 176, 40)):
    d.rectangle([x0, y0, x1, y1], fill=(24, 24, 26))
    for x in range(x0 - (y1 - y0), x1, 10):
        d.polygon([(x, y1), (x + 5, y1), (x + 5 + (y1 - y0), y0), (x + (y1 - y0), y0)], fill=col)
    d.rectangle([x0, y0, x1, y0], fill=shade(col, 0.5))


def grime(img, rnd, n, col=(0, 0, 0), alpha=40):
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for _ in range(n):
        x = rnd.randrange(img.width)
        y = rnd.randrange(img.height // 2)
        h = rnd.randint(14, 60)
        for k in range(h):
            a = int(alpha * (1 - k / h))
            d.point((x, y + k), col + (a,))
            d.point((x + 1, y + k), col + (a // 2,))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def bloodsmear(d, x, y, rnd, scale=1.0, col=(96, 8, 12)):
    for _ in range(int(14 * scale)):
        dx = rnd.randint(-int(8 * scale), int(8 * scale))
        dy = rnd.randint(-int(5 * scale), int(5 * scale))
        d.ellipse([x + dx - 2, y + dy - 1, x + dx + 2, y + dy + 1], fill=col)
    for k in range(int(3 * scale) + 1):
        x2 = x + rnd.randint(-6, 6)
        d.line([x2, y, x2, y + rnd.randint(8, 34)], fill=col, width=1)


def make_wall(cfg, rnd):
    w, h = WALL_W, WALL_H
    img = lin_grad(w, h, shade(cfg["wall2"], 0.8), shade(cfg["wall"], 1.0))
    d = ImageDraw.Draw(img)
    em = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ed = ImageDraw.Draw(em)
    kind = cfg["kind"]
    wins = []
    # ceiling beams and bulkhead panels are common to every deck
    panels(d, 0, w, 24, 188, 96, cfg["wall"])
    d.rectangle([0, 0, w, 22], fill=shade(cfg["wall2"], 0.7))
    for x in range(0, w, 48):
        d.rectangle([x, 0, x + 3, 22], fill=shade(cfg["wall2"], 0.45))
    d.rectangle([0, 22, w, 25], fill=shade(cfg["wall2"], 1.3))
    pipe_h(d, 6, 5, shade(cfg["wall2"], 1.5), w)
    pipe_h(d, 14, 3, shade(cfg["wall"], 1.2), w, rivets=False)
    # skirting
    d.rectangle([0, 186, w, h], fill=shade(cfg["wall2"], 0.6))
    d.rectangle([0, 186, w, 188], fill=shade(cfg["wall2"], 1.4))
    hazard(d, 0, w, 196, 204, cfg["accent"] if kind in ("bay", "engine") else (150, 140, 60))
    for x in (40, 232, 424):
        lamp(d, ed, x, 26, cfg["lamp"])

    if kind == "bay":
        for x0 in (46, 334):
            window(d, x0, 52, 140, 62, (86, 92, 90))
            wins.append((x0, 52, 140, 62))
        for x in (210, 498):   # big clamp doors with numbers
            d.rectangle([x, 80, x + 54, 186], fill=shade(cfg["wall2"], 0.8), outline=(30, 34, 34))
            d.rectangle([x + 4, 84, x + 50, 182], fill=shade(cfg["wall"], 0.9))
            d.rectangle([x + 22, 84, x + 32, 182], fill=shade(cfg["wall2"], 0.7))
            hazard(d, x + 4, x + 50, 168, 180)
            d.rectangle([x + 10, 90, x + 44, 104], fill=(20, 22, 22))
            ed.rectangle([x + 12, 92, x + 42, 102], fill=(255, 190, 60, 90))
        for x in (6, 290):
            pipe_v(d, x, 8, (120, 124, 120), 25, 186)
        pipe_h(d, 150, 6, (110, 114, 106), w)
    elif kind == "medical":
        # white tiled lower wall and glass-fronted rooms
        d.rectangle([0, 120, w, 186], fill=(150, 176, 178))
        for x in range(0, w, 10):
            d.line([x, 120, x, 186], fill=(110, 138, 142))
        for y in range(120, 186, 10):
            d.line([0, y, w, y], fill=(110, 138, 142))
        d.rectangle([0, 118, w, 121], fill=(60, 84, 90))
        for x0 in (60, 340):
            window(d, x0, 44, 130, 58, (104, 128, 130))
            wins.append((x0, 44, 130, 58))
        for x in (230, 500):   # red cross panels
            d.rectangle([x, 56, x + 30, 86], fill=(220, 226, 226), outline=(60, 80, 84))
            d.rectangle([x + 12, 60, x + 18, 82], fill=(200, 40, 40))
            d.rectangle([x + 4, 68, x + 26, 74], fill=(200, 40, 40))
            ed.rectangle([x + 6, 70, x + 24, 72], fill=(255, 80, 80, 70))
        for x in (170, 440):
            d.rectangle([x, 130, x + 26, 186], fill=(60, 84, 90), outline=(30, 44, 48))
            d.rectangle([x + 3, 134, x + 23, 170], fill=(30, 48, 54))
    elif kind == "engine":
        for y, th, col in ((34, 14, (150, 96, 56)), (58, 9, (126, 80, 46)), (92, 18, (160, 100, 60)), (138, 10, (110, 70, 44))):
            pipe_h(d, y, th, col, w)
        for x in (70, 262, 454):
            pipe_v(d, x, 12, (170, 108, 64), 24, 186)
            d.ellipse([x - 8, 70, x + 20, 98], fill=(40, 36, 34), outline=(120, 80, 50))
            ed.ellipse([x - 5, 73, x + 17, 95], fill=(255, 120, 30, 90))
            d.line([x + 6, 84, x + 12, 76], fill=(255, 220, 140), width=1)
        wins.append((140, 106, 100, 38))
        window(d, 140, 106, 100, 38, (130, 84, 50))
        wins.append((326, 106, 100, 38))
        window(d, 326, 106, 100, 38, (130, 84, 50))
        for x in range(30, w, 96):
            d.rectangle([x, 150, x + 60, 156], fill=(70, 66, 62))
    elif kind == "hydro":
        for x0 in (40, 320):
            window(d, x0, 40, 150, 62, (70, 120, 90))
            wins.append((x0, 40, 150, 62))
        # planters with overgrown plants
        for x in range(10, w, 58):
            d.rectangle([x, 160, x + 40, 186], fill=(70, 56, 44), outline=(30, 26, 22))
            for k in range(7):
                px = x + 4 + k * 5
                top = 120 + rnd.randint(0, 24)
                d.line([px, 160, px + rnd.randint(-4, 4), top], fill=(40, rnd.randint(110, 170), 56), width=2)
                d.ellipse([px - 3, top - 3, px + 4, top + 3], fill=(60, rnd.randint(150, 210), 70))
        for x in range(20, w, 70):   # hanging vines from the ceiling
            for k in range(4):
                vx = x + k * 5
                ln = rnd.randint(18, 60)
                d.line([vx, 25, vx + rnd.randint(-3, 3), 25 + ln], fill=(34, 110 + k * 12, 50), width=2)
        for x in (110, 400):
            ed.ellipse([x - 40, 20, x + 40, 90], fill=(220, 120, 255, 36))
    elif kind == "crew":
        for x in range(30, w, 144):   # cabin doors with numbers
            d.rectangle([x, 92, x + 40, 186], fill=shade(cfg["wall2"], 0.7), outline=(26, 20, 20))
            d.rectangle([x + 4, 98, x + 36, 180], fill=shade(cfg["wall"], 0.8))
            d.rectangle([x + 8, 84, x + 32, 91], fill=(20, 18, 18))
            ed.rectangle([x + 10, 86, x + 30, 89], fill=(255, 170, 80, 140))
            d.ellipse([x + 30, 140, x + 34, 144], fill=(180, 160, 90))
        for x0 in (140, 428):
            window(d, x0, 50, 90, 58, (84, 70, 62))
            wins.append((x0, 50, 90, 58))
        for x in (300, 560):    # Unitology sigil + hand-written warning
            d.ellipse([x - 12, 60, x + 12, 84], outline=(150, 40, 40))
            d.line([x, 60, x, 84], fill=(150, 40, 40))
            d.line([x - 12, 72, x + 12, 72], fill=(150, 40, 40))
    else:   # hive: steel scaffold swallowed by flesh
        for x0 in (60, 350):
            window(d, x0, 44, 120, 60, (70, 40, 50))
            wins.append((x0, 44, 120, 60))
        for x in range(0, w, 72):
            d.line([x, 25, x + 36, 186], fill=shade(cfg["wall2"], 0.5), width=3)
        for _ in range(26):
            x, y = rnd.randrange(w), rnd.randrange(30, 186)
            r = rnd.randint(4, 14)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(rnd.randint(90, 130), 36, 44), outline=(40, 12, 18))
            if r > 8:
                ed.ellipse([x - r // 2, y - r // 2, x + r // 2, y + r // 2], fill=(255, 40, 40, 90))
        for x in range(10, w, 40):
            d.line([x, 25, x + rnd.randint(-6, 6), 25 + rnd.randint(30, 120)], fill=(120, 36, 46), width=3)

    for _ in range(5):
        bloodsmear(d, rnd.randrange(w), rnd.randint(110, 180), rnd, 1.0 + rnd.random())
    img = grime(img, rnd, 80)
    noise(img, rnd, 8, 0.06)
    return img, em, wins


def make_floor(cfg, rnd):
    w, h = FLOOR_W, FLOOR_H
    img = lin_grad(w, h, shade(cfg["floor"], 1.15), shade(cfg["floor"], 0.55))
    d = ImageDraw.Draw(img)
    em = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ed = ImageDraw.Draw(em)
    # plates with seams, perspective: vertical seams lean with depth
    for x in range(0, w, 48):
        d.line([x, 0, x - 10, h], fill=shade(cfg["floor"], 0.4))
        d.line([x + 1, 0, x - 9, h], fill=shade(cfg["floor"], 1.35))
    for y in (10, 26, 46):
        d.line([0, y, w, y], fill=shade(cfg["floor"], 0.4))
    # grating strip glowing from below along the far edge
    d.rectangle([0, 0, w, 5], fill=shade(cfg["floor"], 0.35))
    for x in range(0, w, 6):
        d.line([x, 1, x, 4], fill=shade(cfg["floor"], 1.2))
        ed.line([x, 1, x, 4], fill=cfg["lamp"] + (70,))
    d.rectangle([0, 0, w, 0], fill=shade(cfg["floor"], 1.7))
    hazard(d, 0, w, h - 4, h - 1, (150, 120, 30))
    for _ in range(4):
        bloodsmear(d, rnd.randrange(w), rnd.randint(14, 54), rnd, 1.6)
    noise(img, rnd, 8, 0.1)
    return img, em


def make_space(cfg, rnd):
    """The view through the windows: slow-scrolling space with the planet / reactor / Marker glow."""
    w, h = 720, 66
    sp = cfg["space"]
    if sp == "reactor":
        img = lin_grad(w, h, (60, 14, 6), (230, 110, 30))
        d = ImageDraw.Draw(img)
        for k in range(40):
            x, y = rnd.randrange(w), rnd.randrange(h)
            d.ellipse([x, y, x + rnd.randint(4, 22), y + rnd.randint(2, 10)], fill=(255, rnd.randint(160, 230), 60))
        return img
    img = Image.new("RGB", (w, h), (4, 6, 14))
    d = ImageDraw.Draw(img)
    for _ in range(190):
        x, y = rnd.randrange(w), rnd.randrange(h)
        v = rnd.randint(110, 255)
        d.point((x, y), (v, v, min(255, v + 20)))
    if sp in ("planet", "marker"):
        col = (170, 100, 70) if sp == "planet" else (90, 30, 40)
        if sp == "planet":
            for rr in range(150, 0, -2):
                t = rr / 150
                d.ellipse([260 - rr, 190 - rr, 260 + rr, 190 + rr], fill=tuple(int(c * (0.45 + 0.7 * (1 - t))) for c in col))
            for _ in range(24):
                x, y = rnd.randint(130, 400), rnd.randint(60, 140)
                d.ellipse([x, y, x + rnd.randint(6, 20), y + rnd.randint(2, 6)], fill=(120, 70, 50))
        else:
            # distant rocks and the red Marker pulsing at the horizon
            for _ in range(14):
                x, y = rnd.randrange(w), rnd.randrange(h)
                r = rnd.randint(3, 11)
                d.ellipse([x - r, y - r // 2, x + r, y + r // 2], fill=(50, 40, 44))
            g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gd = ImageDraw.Draw(g)
            for i in range(14, 0, -1):
                gd.ellipse([340 - i * 9, 33 - i * 4, 340 + i * 9, 33 + i * 4], fill=(255, 40, 40, int(26 + 10 * (14 - i))))
            img = Image.alpha_composite(img.convert("RGBA"), g).convert("RGB")
            d = ImageDraw.Draw(img)
            d.polygon([(334, 12), (346, 12), (344, 54), (336, 54)], fill=(255, 90, 80))
            d.polygon([(337, 14), (343, 14), (342, 40), (338, 40)], fill=(255, 210, 190))
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return img


def tint_variants(lit, em):
    """Five lighting states of the same tile: lit, dark with glowing lamps, red alert, blue stasis (lit and dark)."""
    base = lit.convert("RGBA")
    with_em = Image.alpha_composite(base, em)
    out = {"lit": with_em.convert("RGB")}
    dark = tint_rgb(base.convert("RGB"), (0.30, 0.31, 0.36))
    out["dark"] = Image.alpha_composite(dark.convert("RGBA"), em).convert("RGB")
    mid = tint_rgb(base.convert("RGB"), (0.58, 0.60, 0.66))
    out["mid"] = Image.alpha_composite(mid.convert("RGBA"), em).convert("RGB")
    red = tint_rgb(base.convert("RGB"), (0.62, 0.14, 0.12))
    out["reddark"] = Image.alpha_composite(red.convert("RGBA"), tint_rgba(em, (1.0, 0.3, 0.25))).convert("RGB")
    out["bluelit"] = tint_rgb(with_em.convert("RGB"), (0.55, 0.82, 1.3))
    out["bluedark"] = tint_rgb(base.convert("RGB"), (0.16, 0.30, 0.50))
    return out


def strip(img, extra):
    w, h = img.size
    s = Image.new("RGB", (w + extra, h))
    s.paste(img, (0, 0))
    s.paste(img.crop((0, 0, extra, h)), (w, 0))
    return s


def build_chapter(i):
    cfg = CHAPTERS[i]
    rnd = random.Random(100 + i)
    wall, em, wins = make_wall(cfg, rnd)
    floor, fem = make_floor(cfg, rnd)
    space = make_space(cfg, rnd)
    wv = tint_variants(wall, em)
    fv = tint_variants(floor, fem)
    out = {"wins": wins, "space": pack_rgb(strip(space, 200)), "space_w": space.width}
    for k in wv:
        out["wall_" + k] = pack_rgb(strip(wv[k], SCREEN_W))
        out["floor_" + k] = pack_rgb(strip(fv[k], SCREEN_W))
    return out


# ---- props ------------------------------------------------------------------------------------------------------------
def vent(open_state):
    """Wall vent: 0 closed grate, 1 grate bent open (dark hole), used as the necromorph burst point."""
    cv = Cv(30, 22)
    cv.rect(0, 0, 30, 22, (46, 50, 54), OUTLINE)
    cv.rect(2, 2, 28, 20, (14, 14, 16))
    if open_state == 0:
        for k in range(5):
            cv.rect(3, 3 + k * 3.4, 27, 4.6 + k * 3.4, (96, 100, 108))
        for x in (1.4, 28.6):
            for y in (1.4, 20.6):
                cv.ell(x, y, 0.8, 0.8, (150, 150, 160))
    else:
        cv.rect(2, 2, 28, 20, (8, 6, 8))
        cv.glow(15, 11, 9, (255, 40, 40), 0.35)
        cv.poly([(2, 2), (7, 3), (6, 8), (2, 7)], (96, 100, 108), OUTLINE, 0.4)
        cv.poly([(28, 20), (22, 18), (24, 14), (28, 15)], (96, 100, 108), OUTLINE, 0.4)
    return cv


def grate_piece():
    cv = Cv(22, 16)
    cv.rect(1, 1, 21, 15, (96, 100, 108), OUTLINE)
    for k in range(4):
        cv.rect(2, 2.4 + k * 3.2, 20, 3.6 + k * 3.2, (40, 42, 46))
    return cv


def crate(state):
    cv = Cv(30, 26)
    if state == 0:
        cv.rect(1, 2, 29, 25, (96, 84, 60), OUTLINE)
        cv.rect(3, 4, 27, 23, (122, 106, 74))
        cv.line([(3, 4), (27, 23)], (86, 72, 50), 1.2)
        cv.line([(27, 4), (3, 23)], (86, 72, 50), 1.2)
        cv.rect(1, 2, 29, 5, (150, 130, 90), OUTLINE)
        cv.rect(12, 11, 18, 16, (220, 180, 40))
    else:
        for (x, y, r) in ((6, 22, 5), (15, 23, 5), (24, 22, 4)):
            cv.poly([(x - r, y + 2), (x, y - r * 0.7), (x + r, y + 2)], (110, 94, 66), OUTLINE, 0.5)
    return cv


def locker(state):
    cv = Cv(16, 44)
    if state == 0:
        cv.rect(0, 0, 16, 44, (78, 88, 94), OUTLINE)
        cv.rect(2, 2, 14, 20, (60, 70, 76))
        cv.rect(2, 24, 14, 42, (60, 70, 76))
        for k in range(3):
            cv.rect(4, 4 + k * 3, 12, 5 + k * 3, (30, 34, 38))
        cv.rect(11, 20, 13, 24, (190, 190, 120))
    else:
        cv.rect(0, 0, 16, 44, (66, 76, 82), OUTLINE)
        cv.poly([(2, 2), (16, 6), (16, 40), (2, 42)], (10, 12, 14))
        cv.poly([(16, 6), (22, 12), (22, 38), (16, 40)], (88, 98, 104), OUTLINE, 0.5)
    return cv


def door(frame):
    """Airlock door, frame 0..3 = closed ... open (slides up into the ceiling)."""
    cv = Cv(46, 82)
    cv.rect(0, 0, 46, 82, (50, 56, 60), OUTLINE)
    cv.rect(4, 4, 42, 82, (6, 6, 8))
    h = 78 - frame * 20
    if h > 0:
        cv.rect(4, 4, 42, 4 + h, (84, 92, 98), OUTLINE)
        cv.rect(20, 4, 26, 4 + h, (60, 68, 74))
        for y in range(10, 4 + h - 4, 12):
            cv.rect(6, y, 18, y + 2, (120, 130, 136))
            cv.rect(28, y, 40, y + 2, (120, 130, 136))
        cv.rect(4, 4 + h - 8, 42, 4 + h, (224, 176, 40))
        for x in range(6, 42, 8):
            cv.poly([(x, 4 + h), (x + 4, 4 + h), (x + 7, 4 + h - 8), (x + 3, 4 + h - 8)], (24, 24, 26))
    col = (255, 60, 50) if frame == 0 else (80, 255, 120)
    cv.ell(40, 8, 2.2, 2.2, col, OUTLINE, 0.4)
    cv.glow(40, 8, 5, col, 0.8)
    return cv


def bench():
    cv = Cv(44, 52)
    cv.rect(4, 26, 40, 52, (72, 80, 88), OUTLINE)
    cv.rect(6, 28, 38, 36, (100, 110, 118))
    cv.rect(2, 22, 42, 28, (130, 140, 146), OUTLINE)
    cv.rect(10, 38, 34, 50, (36, 40, 46), OUTLINE)
    for k in range(4):
        cv.ell(14 + k * 5.5, 44, 1.3, 1.3, (80, 220, 255) if k % 2 else (255, 150, 40))
    cv.poly([(10, 22), (14, 6), (30, 6), (34, 22)], (60, 68, 76), OUTLINE, 0.6)
    cv.glow(22, 14, 10, (80, 200, 255), 0.7)
    cv.ell(22, 14, 6, 4, (50, 150, 200), (160, 230, 255), 0.7)
    return cv


def savepoint(frame):
    cv = Cv(26, 50)
    cv.rect(8, 26, 18, 50, (70, 78, 86), OUTLINE)
    cv.rect(4, 22, 22, 28, (110, 120, 128), OUTLINE)
    cv.ell(13, 16 - frame % 2, 4.5, 5.5, (60, 180, 255), (200, 240, 255), 0.6)
    cv.glow(13, 14, 11, (80, 200, 255), 0.9)
    cv.line([(13, 10), (13, 20)], (240, 255, 255), 0.8)
    cv.line([(8, 15), (18, 15)], (240, 255, 255), 0.8)
    cv.ell(13, 36 + 0 * frame, 1.6, 1.6, (80, 255, 120))
    return cv


def pickup(kind):
    cv = Cv(14, 14)
    if kind == "health":
        cv.rect(1, 3, 13, 12, (230, 232, 236), OUTLINE)
        cv.rect(5.5, 4.4, 8.5, 11, (210, 40, 40))
        cv.rect(3.2, 6.2, 10.8, 9.2, (210, 40, 40))
    elif kind == "plasma":
        cv.rect(4, 1.5, 10, 12.5, (50, 90, 150), OUTLINE)
        cv.rect(5, 3, 9, 10.5, (120, 220, 255))
        cv.rect(4.6, 0.6, 9.4, 2.4, (170, 176, 186), OUTLINE)
    elif kind == "pulse":
        cv.rect(2, 4, 12, 11, (110, 70, 30), OUTLINE)
        cv.rect(3, 5, 11, 7, (255, 170, 50))
        for k in range(4):
            cv.rect(3.4 + k * 2, 8, 4.4 + k * 2, 10.4, (230, 220, 150))
    elif kind == "credit":
        cv.rect(2, 4, 12, 11, (210, 180, 60), OUTLINE)
        cv.rect(3.4, 5.4, 10.6, 9.6, (250, 226, 110))
        cv.rect(5, 6.4, 9, 8.2, (150, 120, 30))
    elif kind == "node":
        cv.glow(7, 7, 7, (80, 190, 255), 0.9)
        cv.poly([(7, 1), (12, 7), (7, 13), (2, 7)], (60, 150, 230), (210, 240, 255), 0.6)
        cv.ell(7, 7, 2, 2, (230, 250, 255))
    elif kind == "stasis":
        cv.rect(3, 2, 11, 12, (40, 70, 130), OUTLINE)
        cv.rect(4.4, 3.4, 9.6, 10.6, (110, 160, 255))
        cv.ell(7, 7, 2.2, 2.2, (230, 240, 255))
    return cv


def corpse(kind):
    """Human crewman lying on the floor (decor and loot for stomping, and the host an Infector revives)."""
    cv = Cv(44, 12)
    cols = [(60, 90, 120), (120, 90, 60), (110, 110, 118)][kind % 3]
    cv.poly([(8, 4), (30, 3), (31, 8), (8, 9)], cols, OUTLINE, 0.7)
    cv.limb([(8, 7), (1, 8), (-1, 10)], 3.4, shade(cols, 0.8))
    cv.limb([(30, 6), (36, 7)], 3.0, (190, 150, 120))
    cv.ell(38, 7, 3.6, 3.4, (190, 150, 120), OUTLINE, 0.6)
    splat(cv, 20, 9, 9, BLOOD, 12, kind + 7)
    return cv


def barrel():
    cv = Cv(16, 22)
    cv.rect(1, 1, 15, 21, (150, 54, 44), OUTLINE)
    cv.rect(1, 6, 15, 9, (230, 190, 40))
    cv.rect(2, 3, 5, 20, (190, 90, 72))
    cv.ell(8, 12, 3.2, 3.2, (255, 220, 60), OUTLINE, 0.5)
    return cv


def steam_puff(r, phase_dither):
    """Dithered grey puff: the platform has no alpha, so 'transparent' is a checkerboard."""
    cv = Cv(int(r * 2 + 2), int(r * 2 + 2))
    cv.ell(r + 1, r + 1, r, r, (196, 204, 210))
    cv.ell(r + 0.2, r, r * 0.6, r * 0.6, (230, 236, 240))
    im = cv.done()
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if (x + y + phase_dither) % 2:
                r_, g_, b_, a = px[x, y]
                px[x, y] = (r_, g_, b_, 0)
    return im


def glyph_font():
    f = ImageFont.load_default_imagefont()
    chars = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:./-+%!<>xX"
    cols = {"w": (236, 236, 240), "a": (255, 184, 60), "r": (255, 70, 60), "c": (110, 230, 255), "g": (120, 255, 140),
            "d": (150, 150, 160)}
    out = {}
    for key, col in cols.items():
        lst = []
        for ch in chars:
            im = Image.new("L", (6, 9), 0)
            ImageDraw.Draw(im).text((0, -1), ch, font=f, fill=255)
            rgba = Image.new("RGBA", (6, 9), col + (0,))
            rgba.putalpha(im.point(lambda v: 255 if v > 90 else 0))
            lst.append(rgb565_bytes(rgba))
        out[key] = lst
    return chars, out


def ring(r, col):
    cv = Cv(r * 2 + 2, r * 2 + 2)
    cv.d.ellipse([1 * SS, 1 * SS, (2 * r + 1) * SS, (2 * r + 1) * SS], outline=col + (255,), width=SS)
    cv.d.ellipse([3 * SS, 3 * SS, (2 * r - 1) * SS, (2 * r - 1) * SS], outline=col + (120,), width=SS)
    im = cv.done()
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if (x + y) % 2:
                px[x, y] = px[x, y][:3] + (0,)
    return im


def flash(r, col=(255, 250, 220)):
    cv = Cv(r * 2, r * 2)
    cv.glow(r, r, r, col, 1.0)
    cv.ell(r, r, r * 0.35, r * 0.35, (255, 255, 255))
    return cv


def marker_prop():
    """The Marker: a tall black-red monolith with a pulsing glow, backdrop of the final chapter."""
    cv = Cv(40, 110)
    cv.glow(20, 55, 36, (255, 30, 30), 0.8)
    cv.poly([(10, 6), (30, 6), (34, 100), (6, 100)], (24, 8, 12), (255, 70, 60), 0.9)
    cv.poly([(15, 12), (25, 12), (27, 90), (13, 90)], (60, 14, 20))
    for y in range(20, 90, 10):
        cv.line([(14, y), (26, y + 3)], (255, 90, 70), 0.7)
    return cv


def pillar():
    """Foreground pipe hanging from the ceiling, drawn closer to the camera than the action: depth without hiding Isaac."""
    cv = Cv(22, 150)
    cv.rect(3, 0, 17, 138, (14, 15, 18))
    cv.rect(4, 0, 7, 138, (34, 36, 42))
    cv.rect(14, 0, 17, 138, (8, 8, 10))
    for y in (24, 64, 104):
        cv.rect(1, y, 19, y + 5, (44, 46, 52), OUTLINE)
        cv.ell(4, y + 2.5, 0.9, 0.9, (100, 104, 112))
        cv.ell(16, y + 2.5, 0.9, 0.9, (100, 104, 112))
    cv.rect(0, 136, 20, 143, (30, 32, 38), OUTLINE)
    for k, x in enumerate((5, 10, 15)):
        cv.limb([(x, 141), (x + (k - 1) * 3, 146), (x + (k - 1) * 2, 150)], 1.2, (16, 16, 18), (6, 6, 8), (50, 50, 56))
    return cv
