# Build-time level drawing and level data for the three Contra stages (jungle, waterfall, alien lair).
# Layouts follow the stage descriptions in research_contra.md; platform tuples are (x0, x1, feet y).
import math, random
from PIL import Image, ImageDraw
from g_contra_art import C, new, strip_rows, mask_rows


def rgba(name, a=255):
    return C[name] + (a,)


def rock(d, x0, y0, x1, y1, rnd, moss=True):
    """Mossy yellow-brown boulders as in the stage 1 cliffs."""
    d.rectangle([x0, y0, x1, y1], fill=rgba("dbrown"))
    y = y0
    row = 0
    while y < y1:
        h = rnd.randint(13, 18)
        x = x0 - (row % 2) * 11 - rnd.randint(0, 6)
        while x < x1:
            w = rnd.randint(18, 28)
            fill = rnd.choice(["olive", "olive", "lolive", "brown"])
            box = [max(x, x0), y, min(x + w - 1, x1), min(y + h - 1, y1)]
            if box[2] > box[0] + 2 and box[3] > box[1] + 2:
                d.rounded_rectangle(box, radius=4, fill=rgba(fill), outline=rgba("dbrown"))
                d.line([(box[0] + 2, box[1] + 1), (box[2] - 3, box[1] + 1)], fill=rgba("lolive"))
                d.line([(box[2] - 1, box[1] + 3), (box[2] - 1, box[3] - 3)], fill=rgba("brown"))
                if moss and rnd.random() < 0.35:
                    mx = rnd.randint(box[0] + 2, max(box[0] + 3, box[2] - 6))
                    d.rectangle([mx, box[1] + 2, mx + 4, box[1] + 3], fill=rgba("green"))
            x += w
        y += h
        row += 1


def grass(d, x0, x1, y):
    d.rectangle([x0, y, x1, y], fill=rgba("lgreen"))
    d.rectangle([x0, y + 1, x1, y + 3], fill=rgba("green"))
    d.rectangle([x0, y + 4, x1, y + 4], fill=rgba("dgreen"))
    for x in range(x0 + 2, x1, 5):
        d.point([(x, y + 5), (x + 1, y + 6)], fill=rgba("dgreen"))


def palm(d, x, base, rnd):
    top = base - rnd.randint(22, 30)
    d.line([(x, base), (x + rnd.randint(-3, 3), top)], fill=rgba("dbrown"), width=2)
    for ang in (-2.7, -2.2, -1.7, -1.2, -0.7, -0.35, 0.0, 0.4):
        ex = x + math.cos(ang) * 14
        ey = top + 3 - math.sin(-ang) * 6 + (4 if abs(ang) < 0.5 or abs(ang + 3.14) < 0.5 else 0)
        d.line([(x, top), (ex, ey + 4)], fill=rgba("dgreen"), width=3)
        d.line([(x, top), (ex, ey + 2)], fill=rgba("green"), width=1)


# ---- stage 1: jungle -------------------------------------------------------------------------------------
W1, TOP, MID, LOW, WATER_SURF, WY0 = 3840, 116, 152, 188, 222, 200
GAPS1 = [(820, 1010), (1900, 2060)]
BOSS_FLOOR = 196


def ground_profile1():
    segs = [(0, 820, TOP), (1010, 1900, TOP), (2060, 3300, TOP), (3300, 3380, MID), (3380, W1, BOSS_FLOOR)]
    return segs


def stage1():
    rnd = random.Random(11)
    # parallax sky strip: night sky with snowy mountains, moves at a quarter of the camera speed
    wsky = W1 // 4 + 256
    sky = Image.new("RGB", (wsky, 104), (0, 0, 0))
    d = ImageDraw.Draw(sky)
    for _ in range(wsky // 9):
        x, y = rnd.randrange(wsky), rnd.randrange(0, 60)
        d.point([(x, y)], fill=rnd.choice([(252, 252, 252), (120, 120, 200), (252, 252, 252)]))
    x = -20
    while x < wsky:
        wd, ht = rnd.randint(70, 96), rnd.randint(40, 58)
        px, py = x + wd // 2, 102 - ht
        d.polygon([(x, 102), (px, py), (x + wd, 102)], fill=C["grey"])
        d.polygon([(px, py), (x + wd, 102), (px + 6, 102), (px + 2, py + ht // 2)], fill=C["dgrey"])
        d.polygon([(px, py), (px - wd // 5, py + ht // 3), (px - 4, py + ht // 4), (px, py + ht // 3 + 2),
                   (px + 4, py + ht // 4), (px + wd // 6, py + ht // 3)], fill=C["white"])
        d.line([(px, py + ht // 3), (px - wd // 6, 102)], fill=C["dgrey"])
        x += wd - rnd.randint(14, 30)
    d.rectangle([0, 96, wsky, 103], fill=(0, 24, 0))

    fg = new(W1, 240)
    d = ImageDraw.Draw(fg)
    segs = ground_profile1()
    # far jungle behind the gaps and below the canopy, then the cliffs on top of it
    d.rectangle([0, 100, W1, WY0], fill=(0, 40, 0, 255))
    for x in range(0, W1, 7):
        d.line([(x, 118), (x + rnd.randint(-2, 2), WY0)], fill=rgba("dgreen") if (x // 7) % 3 else (0, 20, 0, 255), width=2)
    # canopy band (alpha shape above the ground line, blended over the sky) and palm crowns
    for x in range(-10, W1, 8):
        h = rnd.randint(14, 24)
        d.ellipse([x, 112 - h, x + 16, 118], fill=rgba("dgreen"))
    for x in range(-10, W1, 14):
        h = rnd.randint(8, 16)
        d.ellipse([x, 114 - h, x + 12, 120], fill=rgba("green"))
    for x in range(10, W1, 52):
        palm(d, x + rnd.randint(-8, 8), 114, rnd)
    for x0, x1, y in segs:
        if y == TOP:
            d.rectangle([x0, TOP - 4, x1, TOP], fill=rgba("dgreen"))
        rock(d, x0, y + 5, x1 - 1, WY0 if y < BOSS_FLOOR else 239, rnd)
        grass(d, x0, x1 - 1, y)
    # grass ledges (walkable) and stair ledges at the banks of each gap
    ledges = stage1_ledges()
    for x0, x1, y in ledges:
        d.rounded_rectangle([x0, y, x1, y + 9], radius=3, fill=rgba("brown"), outline=rgba("dbrown"))
        grass(d, x0, x1, y)
        d.line([(x0 + 1, y + 10), (x1 - 1, y + 10)], fill=(0, 0, 0, 160))
    # fortress wall of the stage boss
    wall(d)
    water_frames = []
    for fr in range(2):
        w = Image.new("RGBA", (W1, 240 - WY0), rgba("blue"))
        wd = ImageDraw.Draw(w)
        for y in range(2, 240 - WY0, 5):
            for x in range(-30, W1, 26):
                off = (y * 7 + fr * 13) % 26
                wd.line([(x + off, y), (x + off + 9, y)], fill=rgba("lblue"))
        wd.line([(0, 0), (W1, 0)], fill=rgba("pblue"))
        wd.rectangle([0, 1, W1, 2], fill=rgba("dblue"))
        water_frames.append(w)
    base = Image.new("RGBA", (W1, 240), (0, 0, 0, 255))
    base.alpha_composite(fg)
    # alpha above the canopy stays transparent for the blend, so keep the shape separately
    blend_y0, blend_y1 = 82, 104
    mask = mask_rows(fg.crop((0, blend_y0, W1, blend_y1)))
    fgrows = strip_rows(base.convert("RGB"))
    wrows = []
    for w in water_frames:
        full = base.copy()
        # rock in the boss zone must survive: paste water only where the base is the generic dark background
        full.paste(w, (0, WY0))
        for x0, x1, y in segs:
            if y == BOSS_FLOOR:
                full.paste(base.crop((x0, WY0, x1, 240)), (x0, WY0))
        wrows.append(strip_rows(full.crop((0, WY0, W1, 240)).convert("RGB")))
    plats = [(x0, x1, y) for x0, x1, y in segs] + ledges
    return dict(
        name="JUNGLE", kind="h", w=W1, h=240, sky=strip_rows(sky), fg=fgrows, water=wrows, water_y0=WY0,
        blend=(blend_y0, blend_y1), mask=mask, plats=plats, water_y=WATER_SURF, lock=W1 - 256,
        start=(60, TOP), bridges=[(840, 1000, TOP), (1910, 2050, TOP)], events=events1(), gens=[
            (160, 780, 70), (1030, 1880, 55), (2080, 3300, 48)],
        boss=dict(x=3790, y=BOSS_FLOOR, kind="wall"),
    )


def stage1_ledges():
    L = []
    for _, gx1 in GAPS1:
        L += [(gx1 + 2, gx1 + 40, LOW), (gx1 + 10, gx1 + 60, MID)]
    L += [(70, 150, MID), (190, 260, MID), (330, 400, LOW), (1150, 1240, MID), (1500, 1560, LOW), (1520, 1620, MID),
          (2200, 2290, MID), (2420, 2500, LOW), (2820, 2900, MID), (3050, 3120, MID)]
    return L


def wall(d):
    x0 = 3696
    d.rectangle([x0, 24, W1 - 1, BOSS_FLOOR], fill=rgba("dgrey"))
    d.rectangle([x0 + 2, 26, W1 - 1, BOSS_FLOOR - 2], fill=rgba("grey"))
    for x in range(x0 + 2, W1, 24):
        d.line([(x, 26), (x, BOSS_FLOOR - 2)], fill=rgba("dgrey"))
    for y in range(40, BOSS_FLOOR - 2, 28):
        d.line([(x0 + 2, y), (W1 - 1, y)], fill=rgba("dgrey"))
        for x in range(x0 + 6, W1 - 4, 24):
            d.point([(x, y + 3), (x + 12, y + 3)], fill=rgba("white"))
    d.rectangle([x0 - 6, 20, W1 - 1, 38], fill=rgba("dgrey"))
    d.rectangle([x0 - 4, 22, W1 - 1, 36], fill=rgba("lgrey"))
    d.rectangle([x0 - 4, 34, W1 - 1, 36], fill=rgba("dgrey"))
    # turret sockets and the core recess
    for cx in (3716, 3750):
        d.rectangle([cx - 14, 90, cx + 14, 118], fill=rgba("black"))
        d.rectangle([cx - 12, 92, cx + 12, 116], fill=rgba("dgrey"))
    d.rectangle([3778, 150, 3830, BOSS_FLOOR], fill=rgba("black"))
    d.rectangle([3781, 153, 3827, BOSS_FLOOR], fill=rgba("dpurple"))
    d.rectangle([x0 - 2, 40, x0 + 1, BOSS_FLOOR], fill=rgba("black"))


def events1():
    E = [("sniper", 640), ("sensor", 330, "M"), ("capsule", 440, "R"), ("sniper", 760),
         ("turret", 1070), ("sniper", 1230), ("sniper", 1320), ("capsule", 1340, "S"),
         ("cannon", 1570), ("sensor", 1650, "F"), ("sniper", 1770),
         ("scuba", 900), ("scuba", 1960),
         ("turret", 2120), ("cannon", 2200), ("sniper", 2300), ("sensor", 2390, "S"), ("capsule", 2500, "L"),
         ("capsule", 2540, "R"), ("turret", 2650), ("turret", 2790), ("cannon", 2900), ("sniper", 3010),
         ("turret", 3110), ("sniper", 3200), ("capsule", 3260, "B")]
    return E


# ---- stage 3: waterfall (vertical) ---------------------------------------------------------------------
W3, H3 = 256, 2000
FLOOR3 = H3 - 14


def ledges3():
    """Zig-zag of grass rock ledges climbing the waterfall, at most 36 px apart so one somersault jump reaches the next."""
    rnd = random.Random(33)
    L = [(14, 242, FLOOR3)]
    y = FLOOR3
    side = 0
    while y > 250:
        y -= rnd.choice([32, 34, 34, 36])
        side = 1 - side if rnd.random() < 0.8 else side
        if side == 0:
            x0, x1 = 0, rnd.randint(112, 128)
        else:
            x0, x1 = rnd.randint(128, 144), 256
        L.append((x0, x1, y))
    return L


def stage3():
    P = ledges3()
    # the long flame bridge replaces the ledge nearest to the middle of the climb
    bi = min(range(1, len(P)), key=lambda i: abs(P[i][2] - 1300))
    by = P[bi][2]
    plats = P[:bi] + [(20, 236, by)] + P[bi + 1:] + [(0, 256, 216)]
    floats = [(P[i][2] - 18, 100 if i % 2 else 150) for i in (len(P) // 5, len(P) // 3, len(P) // 2 + 4)]
    frames = []
    for fr in range(3):
        img = Image.new("RGBA", (W3, H3), rgba("blue"))
        d = ImageDraw.Draw(img)
        r2 = random.Random(5)
        for x in range(0, W3, 3):
            ph = r2.randrange(24)
            ln = r2.choice([8, 12, 16])
            col = rgba(r2.choice(["lblue", "lblue", "pblue", "dblue"]))
            for y0 in range(-24, H3, 24):
                yy = y0 + (ph + fr * 8) % 24
                d.line([(x, yy), (x, yy + ln)], fill=col)
        frames.append(img)
    over = new(W3, H3)
    d = ImageDraw.Draw(over)
    rr = random.Random(4)
    for x0, x1, y in sorted(plats, key=lambda p: -p[2]):
        if y in (by, 216):
            continue
        rock(d, x0, y + 4, x1 - 1, y + 40, rr)
        grass(d, x0, x1 - 1, y)
        edge = x1 if x0 == 0 else x0
        d.line([(edge, y + 4), (edge, y + 40)], fill=rgba("dbrown"), width=2)
    d.rectangle([20, by, 236, by + 7], fill=rgba("dgrey"))
    d.rectangle([20, by, 236, by + 1], fill=rgba("lgrey"))
    for x in range(22, 236, 8):
        d.line([(x, by + 2), (x + 4, by + 7)], fill=rgba("black"))
    # boss arena (camera y = 0): dark alien cave over the water, metal floor
    d.rectangle([0, 0, 255, 239], fill=rgba("black"))
    for x in range(0, 256, 16):
        d.line([(x, 0), (x + rr.randint(-6, 6), 215)], fill=rgba("dpurple"), width=1)
    for y in range(0, 216, 18):
        d.line([(0, y), (255, y + rr.randint(-4, 4))], fill=(30, 12, 50, 255))
    d.rectangle([0, 0, 255, 14], fill=rgba("dgrey"))
    d.rectangle([0, 14, 255, 16], fill=rgba("black"))
    d.rectangle([0, 216, 255, 239], fill=rgba("dgrey"))
    d.rectangle([0, 216, 255, 218], fill=rgba("lgrey"))
    for x in range(0, 256, 16):
        d.line([(x, 219), (x + 8, 239)], fill=rgba("black"))
    d.rectangle([0, 14, 10, 215], fill=rgba("dgrey"))
    d.rectangle([245, 14, 255, 215], fill=rgba("dgrey"))
    out = []
    for f in frames:
        f.alpha_composite(over)
        out.append(strip_rows(f.convert("RGB")))
    return dict(name="WATERFALL", kind="v", w=W3, h=H3, frames=out, plats=plats, water_y=None, lock=0,
                start=(120, FLOOR3), bridge=(20, 236, by), floats=floats, events=events3(by), gens=[],
                boss=dict(x=128, y=216, kind="alien"))


def events3(by):
    P = ledges3()
    ys = [p for p in P if 400 < p[2] < FLOOR3 - 200 and abs(p[2] - by) > 60]
    E = []
    for i, (x0, x1, y) in enumerate(ys):
        cx = (x0 + x1) // 2
        k = i % 7
        if k == 1:
            E.append(("turret", min(max(cx, x0 + 14), x1 - 14), y))
        elif k == 3:
            E.append(("sniper", min(max(cx, x0 + 14), x1 - 14), y))
        elif k == 5:
            E.append(("sensor", min(max(cx, x0 + 14), x1 - 14), y, "FLMSR"[(i // 7) % 5]))
        if i % 9 == 4:
            E.append(("cave", 6 if x0 == 0 else 250, y - 20))
    E += [("capsule", 128, FLOOR3 - 300, "R"), ("capsule", 128, 1300, "B"), ("capsule", 128, 800, "S")]
    return E


# ---- stage 8: alien lair -------------------------------------------------------------------------------
W8 = 3328
FL, UP = 190, 154


def stage8():
    rnd = random.Random(88)
    plats = [(0, 620, FL), (620, 1040, UP), (1080, 1500, UP), (1500, 1900, FL), (1940, 2400, FL), (2400, 2700, UP),
             (2740, W8, FL)]
    plats.append((560, 640, 172))
    img = Image.new("RGB", (W8, 240), C["dpurple"])
    d = ImageDraw.Draw(img)
    # back wall: mottled blue-violet organic tissue with veins
    for _ in range(2600):
        x, y = rnd.randrange(W8), rnd.randrange(30, 232)
        col = rnd.choice([(40, 24, 120), (24, 8, 90), (60, 32, 150), (16, 8, 60)])
        d.ellipse([x, y, x + rnd.randint(4, 12), y + rnd.randint(3, 8)], fill=col)
    for x in range(0, W8, 36):
        d.line([(x, 36), (x + rnd.randint(-14, 14), 232)], fill=(60, 20, 90), width=1)
    # toxic bottom
    d.rectangle([0, 226, W8, 239], fill=(0, 140, 100))
    for x in range(0, W8, 6):
        d.point([(x, 226 + (x // 6) % 3)], fill=(120, 240, 200))
    # ceiling weave with fangs
    d.rectangle([0, 0, W8, 30], fill=C["dbrown"])
    for x in range(0, W8, 10):
        d.ellipse([x - 4, 2 + rnd.randint(0, 10), x + 12, 26 + rnd.randint(0, 8)], fill=rnd.choice([C["brown"], (96, 60, 70), C["dbrown"], (110, 70, 90)]))
        d.line([(x, 0), (x + 10, 30)], fill=C["dbrown"])
    for x in range(30, W8, 70):
        h = rnd.randint(10, 26)
        d.polygon([(x, 28), (x + 8, 28 + h), (x + 14, 28)], fill=C["brown"])
    # flesh slabs: crimson top, fibrous brown underside; upper slabs stand on dark supports, lower ones are solid tissue
    for x0, x1, y in plats:
        if x1 - x0 < 100:
            continue
        d.rectangle([x0, y, x1, y + 6], fill=C["pink"])
        d.rectangle([x0, y + 1, x1, y + 2], fill=(252, 160, 176))
        d.rectangle([x0, y + 7, x1, y + 9], fill=C["dpink"])
        if y == UP:
            d.rectangle([x0, y + 26, x1, 226], fill=(48, 16, 64))
            for x in range(x0, x1, 11):
                d.line([(x, y + 26), (x + rnd.randint(-5, 5), 226)], fill=(90, 30, 90))
        else:
            d.rectangle([x0, y + 10, x1, 226], fill=C["dbrown"])
        for x in range(x0, x1, 9):
            yy = y + 8 + rnd.randint(0, 6) if y == UP else y + 10 + rnd.randint(0, 40)
            d.ellipse([x, yy, x + 14, yy + 16], fill=rnd.choice([C["brown"], (96, 60, 70), C["dbrown"]]), outline=C["dbrown"])
    d.rectangle([560, 172, 640, 178], fill=C["pink"])
    d.rectangle([560, 179, 640, 184], fill=C["dpink"])
    # final chamber
    d.rectangle([3060, 30, W8, 189], fill=(50, 10, 40))
    for x in range(3060, W8, 12):
        d.line([(x, 30), (x + rnd.randint(-6, 6), 189)], fill=(100, 20, 60))
    fg = strip_rows(img)
    return dict(name="ALIEN LAIR", kind="h", w=W8, h=240, fg=fg, plats=plats, water_y=None, lock=W8 - 256,
                start=(50, FL), events=events8(), gens=[(1900, 3000, 70)], bridges=[],
                boss=dict(x=3235, y=FL, kind="heart"), pit_y=226)


def events8():
    E = [("capsule", 150, "M"), ("capsule", 190, "B"),
         ("mouth", 400, 36, 0), ("mouth", 470, 36, 0), ("bighead", 760, 40),
         ("mouth", 900, 36, 0), ("mouth", 950, 36, 0), ("mouth", 1160, 36, 0), ("capsule", 1230, "S"),
         ("mouth", 1260, 36, 0), ("fmouth", 1330, UP - 2), ("fmouth", 1400, UP - 2),
         ("mouth", 1600, 36, 0), ("fmouth", 1700, FL - 2), ("mouth", 1780, 36, 0), ("fmouth", 1840, FL - 2),
         ("crawlers", 2000, 0), ("mouth", 2060, 36, 0), ("fmouth", 2140, FL - 2), ("mouth", 2230, 36, 0),
         ("mouth", 2480, 36, 0), ("fmouth", 2560, UP - 2), ("mouth", 2620, 36, 0), ("crawlers", 2500, 0),
         ("mouth", 2900, 36, 0), ("mouth", 3000, 36, 0)]
    return E
