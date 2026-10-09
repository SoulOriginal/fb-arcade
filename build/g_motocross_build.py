# Build script for g_motocross.bin: an Excitebike-style side-view dirt-bike race, everything drawn procedurally.
# Virtual screen 256x240 "vpx" (shown 4x); sprites are stored as per-row opaque runs where one vpx is already
# expanded to 4 screen pixels (8 bytes), so the game can paste them into scanline buffers with plain slice assignment.
import math, random
from PIL import Image, ImageDraw
from buildlib import save_bundle, rgb565

VW, VH = 256, 240
WALL_H, TRACK_TOP, LANE_H, HAY_Y, HUD_Y = 38, 140, 20, 220, 228
LANE_CONTACT = [TRACK_TOP + 16 + LANE_H * i for i in range(4)]
SHEAR = 0.3           # horizontal shift per row of depth of ramps, see draw_ramp
PERIOD = 512          # horizontal period of the repeating scenery strip, in vpx
WHEEL_BASE = 18       # rear to front axle, vpx; the game uses the same number for contact tests
rng = random.Random(7)


def px8(c):
    return rgb565(*c).to_bytes(2, "little") * 4


def runs_of(img, crop=True):
    # RGBA image -> sprite dict with per-row opaque runs; ox/oy is the bounding box origin inside the source image,
    # so a sprite drawn around the canvas centre CEN is anchored at (CEN - ox, CEN - oy).
    w, h = img.size
    a = img.load()
    box = img.getbbox() if crop else (0, 0, w, h)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    rows = []
    for y in range(y0, y1):
        row, x = [], x0
        while x < x1:
            if a[x, y][3] < 128:
                x += 1
                continue
            st = x
            parts = []
            while x < x1 and a[x, y][3] >= 128:
                parts.append(px8(a[x, y][:3]))
                x += 1
            row.append((st - x0, b"".join(parts)))
        rows.append(row)
    return {"w": x1 - x0, "h": y1 - y0, "ox": x0, "oy": y0, "rows": rows}


# ---------------------------------------------------------------------------------------- palette
WALL = (128, 128, 248)
GREEN = (144, 213, 0)
TRACK = (232, 153, 0)
LANE_LINE = (176, 100, 0)
HAY_PINK = (255, 200, 165)
OLIVE = (119, 123, 2)
PINK = (239, 201, 182)
WHITE = (250, 250, 250)
BLACK = (0, 0, 0)
THEMES = [
    dict(wall=(128, 128, 248), green=(144, 213, 0), dark=(96, 96, 200)),
    dict(wall=(96, 176, 248), green=(120, 205, 20), dark=(70, 140, 210)),
    dict(wall=(240, 130, 150), green=(168, 214, 30), dark=(200, 100, 120)),
    dict(wall=(70, 70, 170), green=(70, 160, 50), dark=(50, 50, 130)),
]

# ---------------------------------------------------------------------------------------- scenery strips
def base_rows(theme):
    # One period (PERIOD vpx wide) of every virtual row: bunting, wall, infield with stumps, lanes, hay strip.
    wall, green, dark = theme["wall"], theme["green"], theme["dark"]
    img = Image.new("RGB", (PERIOD, VH), BLACK)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, PERIOD, WALL_H - 1), fill=wall)
    d.rectangle((0, WALL_H - 2, PERIOD, WALL_H - 1), fill=dark)
    d.rectangle((0, WALL_H, PERIOD, TRACK_TOP - 1), fill=green)
    for x in range(0, PERIOD, 8):
        d.rectangle((x, 0, x + 3, 1), fill=(250, 190, 40))
        d.rectangle((x + 4, 0, x + 7, 1), fill=(150, 140, 220))
    for x in range(0, PERIOD, 16):
        d.polygon([(x + 1, 2), (x + 14, 2), (x + 7, 10)], fill=WHITE)
    # track plane with edge shading, lane dashes and pebbles so that the scroll speed is readable
    d.rectangle((0, TRACK_TOP, PERIOD, HAY_Y - 1), fill=TRACK)
    d.rectangle((0, TRACK_TOP, PERIOD, TRACK_TOP + 1), fill=(200, 120, 0))
    d.rectangle((0, HAY_Y - 2, PERIOD, HAY_Y - 1), fill=(200, 120, 0))
    for i in (1, 2, 3):
        y = TRACK_TOP + LANE_H * i
        for x in range(0, PERIOD, 16):
            d.rectangle((x, y, x + 9, y), fill=LANE_LINE)
            d.rectangle((x + 12, y, x + 13, y), fill=LANE_LINE)
    for _ in range(420):
        x, y = rng.randrange(PERIOD), rng.randrange(TRACK_TOP + 3, HAY_Y - 3)
        if (y - TRACK_TOP) % LANE_H:
            d.rectangle((x, y, x + rng.choice((0, 1)), y), fill=(214, 135, 0))
    # hay-bale strip
    d.rectangle((0, HAY_Y, PERIOD, HUD_Y - 1), fill=green)
    for x in range(2, PERIOD, 24):
        d.ellipse((x, HAY_Y + 1, x + 19, HAY_Y + 7), fill=HAY_PINK, outline=(200, 130, 60))
        d.line((x + 6, HAY_Y + 2, x + 6, HAY_Y + 6), fill=(230, 120, 40))
        d.line((x + 13, HAY_Y + 2, x + 13, HAY_Y + 6), fill=(230, 120, 40))
    # stumps along the track edge (irregular spacing, repeats every PERIOD)
    x = 14
    while x < PERIOD - 20:
        stump(d, x, TRACK_TOP - 13)
        x += rng.choice((28, 36, 44, 52, 60))
    rows = []
    raw = img.tobytes()
    for y in range(VH):
        row = b"".join(rgb565(*raw[(y * PERIOD + x) * 3:(y * PERIOD + x) * 3 + 3]).to_bytes(2, "little") * 4
                       for x in range(PERIOD))
        rows.append(row)
    return rows


def stump(d, x, y):
    d.rectangle((x + 1, y + 4, x + 11, y + 11), fill=(222, 152, 5), outline=(140, 80, 0))
    d.ellipse((x, y, x + 12, y + 7), fill=(255, 185, 50), outline=(140, 80, 0))
    d.line((x + 4, y + 8, x + 4, y + 10), fill=(170, 100, 0))
    d.line((x + 8, y + 8, x + 8, y + 10), fill=(170, 100, 0))


# ---------------------------------------------------------------------------------------- obstacles
PROFILES = {
    "A": [(0, 0), (8, 3), (16, 0)],
    "B": [(0, 0), (11, 7), (22, 0)],
    "C": [(0, 0), (17, 12), (34, 0)],
    "D": [(0, 0), (24, 4), (48, 0)],
    "E": [(0, 0), (14, 14), (16, 0)],
    "F": [(0, 0), (34, 18), (36, 0)],
    "G": [(0, 0), (2, 12), (34, 0)],
    "H": [(0, 0), (18, 15), (21, 0)],
    "R": [(0, 0), (13, 10), (20, 10), (32, 20), (44, 4), (52, 0)],
}
FLAT_LEN = {"mud": 26, "grassS": 56, "grassL": 96, "dirt": 12, "bump": 6, "cool": 18}


def height_at(kind, x):
    pts = PROFILES[kind]
    for (x0, h0), (x1, h1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return h0 + (h1 - h0) * (x - x0) / max(1, x1 - x0)
    return 0


def draw_ramp(kind, l0, l1):
    L = PROFILES[kind][-1][0] + 1
    ytop, ybot = TRACK_TOP + LANE_H * l0, TRACK_TOP + LANE_H * (l1 + 1) - 1
    img = Image.new("RGBA", (L + 1, VH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in range(L):
        h = int(round(height_at(kind, x)))
        h2 = int(round(height_at(kind, min(x + 1, L - 1))))
        d.line((x, ybot - h, x, ybot), fill=PINK + (255,))
        if x % 5 == 0:
            d.line((x, ybot - h + 1, x, ybot), fill=(222, 170, 150, 255))
        rising, falling = h2 > h, h2 < h
        face = OLIVE if rising else ((240, 172, 40) if falling else (250, 190, 70))
        edge = (160, 160, 20) if rising else ((255, 215, 110) if falling else (255, 225, 140))
        d.line((x, ytop - h, x, ybot - h - 1), fill=face + (255,))
        d.line((x, ytop - h, x, ytop - h + 1), fill=edge + (255,))
        d.point((x, ytop - h - 1), fill=(70, 55, 0, 255))
        d.point((x, ybot - h), fill=(90, 75, 0, 255))
        d.point((x, ybot), fill=(160, 110, 100, 255))
        if h2 < h - 3:
            d.line((x, ytop - h, x, ybot), fill=(70, 55, 0, 255))
    # Oblique projection: rows further back (smaller y) are pushed to the right, which turns the stack of
    # vertical columns into the leaning parallelogram this genre is known for. The game offsets the ground
    # profile of each lane by the same amount, see World.__init__.
    hmax = max(h for _, h in PROFILES[kind])
    smax = int(round((ybot - (ytop - hmax - 1)) * SHEAR)) + 1
    sheared = Image.new("RGBA", (L + 1 + smax, VH), (0, 0, 0, 0))
    for y in range(VH):
        sheared.paste(img.crop((0, y, L + 1, y + 1)), (max(0, int(round((ybot - y) * SHEAR))), y))
    s = runs_of(sheared, crop=False)
    s["y0"] = 0
    return s


def lane_band(l0, l1):
    return TRACK_TOP + LANE_H * l0, TRACK_TOP + LANE_H * (l1 + 1) - 1


def draw_flat(kind, l0, l1):
    L = FLAT_LEN[kind]
    y0, y1 = lane_band(l0, l1)
    img = Image.new("RGBA", (L, VH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "mud":
        for yy in range(y0 + 3, y1 - 2):
            for xx in range(L):
                cx = (xx - L / 2) / (L / 2)
                cy = ((yy - (y0 + y1) / 2) / ((y1 - y0) / 2))
                if cx * cx + cy * cy * 0.8 < 0.95 + rng.uniform(-0.3, 0.1) and rng.random() < 0.8:
                    d.point((xx, yy), fill=(129, 121, 0, 255))
        for _ in range(L // 2):
            d.point((rng.randrange(L), rng.randrange(y0 + 4, y1 - 3)), fill=(30, 30, 0, 255))
    elif kind in ("grassS", "grassL"):
        d.rectangle((0, y0 + 2, L - 1, y1 - 1), fill=GREEN + (255,))
        for _ in range(L // 2):
            xx, yy = rng.randrange(L), rng.randrange(y0 + 3, y1 - 1)
            d.line((xx, yy, xx, yy - 2), fill=(90, 170, 0, 255))
        for yy in range(y0 + 2, y1):
            d.point((0, yy), fill=(200, 120, 0, 255))
            d.point((L - 1, yy), fill=(200, 120, 0, 255))
    elif kind == "dirt":
        yc = y0 + LANE_H - 4
        d.polygon([(0, yc), (3, yc - 8), (9, yc - 8), (11, yc)], fill=(176, 98, 10, 255), outline=(90, 45, 0, 255))
        d.line((4, yc - 7, 8, yc - 7), fill=(225, 150, 50, 255))
        d.line((3, yc - 4, 4, yc - 2), fill=(120, 60, 0, 255))
    elif kind == "bump":
        yc = y0 + LANE_H - 4
        d.rectangle((0, yc - 6, 5, yc), fill=(190, 110, 0, 255), outline=(90, 45, 0, 255))
        d.rectangle((1, yc - 6, 4, yc - 4), fill=(255, 215, 120, 255))
    elif kind == "cool":
        for i in range(2):
            ox = 2 + i * 8
            yc = y0 + LANE_H // 2 + 2
            d.polygon([(ox, yc - 6), (ox + 5, yc), (ox, yc + 6), (ox + 3, yc + 6), (ox + 8, yc), (ox + 3, yc - 6)],
                      fill=(225, 187, 151, 255), outline=(120, 70, 20, 255))
    s = runs_of(img, crop=False)
    s["y0"] = 0
    return s


# ---------------------------------------------------------------------------------------- track layouts
# (gap before, kind, first lane, last lane). Ramps carry the original design letters: A/B/C bumps, D long slope,
# E steep, F climb, G drop, H 45 degree jump, R multi-angle hill.
TRACKS = [
    dict(name="TRACK 1", theme=0, best="0:25", deco=[("flagger", 640), ("flagger", 1900), ("tree", 1250)], items=[
        (130, "A", 0, 3), (16, "A", 0, 3), (16, "A", 0, 3), (16, "A", 0, 3),
        (130, "C", 0, 3), (60, "cool", 0, 0), (30, "B", 0, 3), (10, "B", 0, 3), (10, "B", 0, 3),
        (90, "dirt", 0, 0), (20, "dirt", 2, 2), (90, "F", 0, 3), (16, "grassS", 0, 3),
        (60, "H", 0, 3), (70, "cool", 2, 2), (50, "H", 0, 3), (110, "mud", 0, 1),
        (60, "bump", 2, 3), (50, "A", 0, 3), (14, "A", 0, 3), (14, "A", 0, 3),
        (90, "D", 0, 3), (40, "D", 0, 3), (60, "dirt", 0, 0), (26, "dirt", 2, 2), (26, "dirt", 1, 1),
        (26, "dirt", 3, 3), (70, "cool", 0, 0)]),
    dict(name="TRACK 2", theme=1, best="0:26", deco=[("sign", 500), ("tree", 1000), ("sign", 1700), ("tree", 2200)], items=[
        (120, "R", 0, 3), (50, "cool", 1, 1), (60, "R", 0, 3), (60, "B", 0, 3), (10, "B", 0, 3),
        (14, "A", 0, 3), (30, "E", 0, 3), (100, "mud", 2, 3), (40, "A", 0, 3), (30, "F", 0, 1),
        (30, "grassL", 0, 1), (30, "bump", 2, 3), (40, "C", 2, 3), (10, "grassL", 2, 3), (110, "cool", 3, 3),
        (40, "D", 0, 3), (30, "D", 0, 3), (90, "dirt", 1, 1), (24, "dirt", 3, 3), (60, "mud", 0, 1),
        (60, "H", 0, 3), (80, "bump", 0, 1), (60, "C", 0, 3), (8, "C", 0, 3), (100, "cool", 0, 0)]),
    dict(name="TRACK 3", theme=2, best="0:24", deco=[("tower", 400), ("flagger", 1500), ("tower", 2300), ("sign", 1800)], items=[
        (120, "B", 0, 3), (14, "B", 0, 3), (14, "B", 0, 3), (80, "F", 0, 3), (30, "G", 0, 3),
        (60, "cool", 0, 0), (60, "grassL", 0, 3), (40, "mud", 2, 3), (60, "H", 0, 3), (60, "C", 0, 3),
        (30, "bump", 1, 1), (60, "C", 0, 3), (24, "G", 0, 3), (14, "B", 0, 3), (14, "C", 0, 3),
        (90, "cool", 0, 0), (50, "grassS", 2, 3), (20, "grassS", 0, 1), (60, "bump", 2, 3), (60, "dirt", 0, 0),
        (24, "dirt", 2, 2), (50, "E", 0, 3), (40, "mud", 0, 1), (60, "A", 0, 3), (14, "A", 0, 3), (60, "bump", 1, 2)]),
    dict(name="TRACK 4", theme=3, best="0:27", deco=[("tree", 700), ("flagger", 1300), ("tree", 2000), ("tower", 2500)], items=[
        (110, "E", 0, 3), (60, "dirt", 0, 1), (20, "dirt", 2, 3), (60, "B", 0, 3), (30, "bump", 2, 3),
        (30, "A", 0, 3), (10, "A", 0, 3), (60, "F", 0, 3), (30, "grassS", 0, 3), (60, "C", 0, 3),
        (14, "C", 0, 3), (60, "bump", 0, 1), (80, "cool", 0, 0), (60, "mud", 2, 3), (40, "grassL", 0, 1),
        (30, "H", 0, 3), (70, "C", 0, 3), (4, "C", 0, 3), (4, "C", 0, 3), (4, "C", 0, 3), (4, "C", 0, 3),
        (30, "grassL", 0, 3), (60, "cool", 3, 3), (60, "dirt", 3, 3), (26, "dirt", 1, 1), (26, "dirt", 2, 2),
        (60, "H", 0, 3), (60, "bump", 0, 3), (40, "R", 0, 3), (100, "mud", 0, 2)]),
]


def kind_len(k):
    return PROFILES[k][-1][0] + 1 if k in PROFILES else FLAT_LEN[k]


def layout(tr):
    items, s = [], 0
    for gap, k, l0, l1 in tr["items"]:
        s += gap
        items.append((k, s, l0, l1))
        s += kind_len(k)
    return items, s + 140


# ---------------------------------------------------------------------------------------- riders
SUITS = [  # helmet, suit, trim, bike
    ((255, 255, 255), (216, 40, 0), (255, 255, 255), (216, 40, 0)),
    ((120, 210, 255), (0, 112, 236), (200, 240, 255), (0, 168, 255)),
    ((210, 120, 255), (140, 50, 210), (230, 200, 255), (160, 70, 230)),
    ((255, 255, 255), (150, 72, 20), (255, 255, 255), (230, 230, 230)),
    ((210, 255, 120), (0, 150, 40), (200, 255, 200), (60, 190, 60)),
]
CAN = 58
CEN = CAN // 2


SC = 1.3      # bike drawing scale: riders are big in this genre


def rot(x, y, deg, yaw=0):
    x, y = x * SC, y * SC
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return CEN + x * c + y * s, CEN - x * s + y * c


def outline(img):
    a = img.load()
    w, h = img.size
    out = img.copy()
    o = out.load()
    for y in range(h):
        for x in range(w):
            if a[x, y][3] < 128:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and a[nx, ny][3] >= 128 and a[nx, ny][:3] != BLACK:
                        o[x, y] = (0, 0, 0, 255)
                        break
    return out


def draw_bike(ang, ci, phase, yaw=0, rider=True):
    helm, suit, trim, bike = SUITS[ci]
    img = Image.new("RGBA", (CAN, CAN), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def P(x, y, front=False):
        return rot(x, y + (yaw * 1.6 if front and x > 0 else 0), ang)

    def wheel(cx, cy, front):
        x, y = P(cx, cy, front)
        r1, r2 = 4.2 * SC, 2.4 * SC
        d.ellipse((x - r1, y - r1, x + r1, y + r1), fill=(0, 0, 0, 255))
        d.ellipse((x - r2, y - r2, x + r2, y + r2), fill=(235, 235, 235, 255))
        px, py = x + 1.6 * math.cos(math.radians(ang + phase * 90)), y + 1.6 * math.sin(math.radians(ang + phase * 90))
        d.point((round(px), round(py)), fill=(0, 0, 0, 255))

    wheel(-7, 0, False)
    wheel(7, 0, True)
    pts = [P(-7, 0), P(-2, -5), P(3, -6), P(7, -1, True)]
    d.line(pts, fill=bike + (255,), width=3)
    d.line([P(7, -8, True), P(7, 0, True)], fill=(210, 210, 210, 255), width=1)
    d.polygon([P(-9, -5), P(-3, -6), P(-2, -4), P(-9, -3)], fill=bike + (255,))
    d.polygon([P(4, -7, True), P(10, -5, True), P(9, -3, True), P(5, -4, True)], fill=bike + (255,))
    d.line([P(-2, -2), P(2, -2)], fill=(60, 60, 60, 255), width=3)
    if rider:
        lean = 3 if ang < 15 else 0
        hip, sh = P(-3, -6), P(0 + lean * 0.3, -12)
        d.line([P(-2, -3), P(1, -4), P(0, -1)], fill=suit + (255,), width=3)       # leg
        d.line([hip, sh], fill=suit + (255,), width=4)                                # torso
        d.line([sh, P(3, -10), P(6, -8, True)], fill=trim + (255,), width=2)         # arm
        hx, hy = P(1 + lean * 0.3, -15.5)
        d.ellipse((hx - 3.4, hy - 3.4, hx + 3.4, hy + 3.4), fill=helm + (255,))
        vx, vy = P(3.2 + lean * 0.3, -15.5)
        d.point((round(vx), round(vy)), fill=(20, 20, 60, 255))
    return outline(img)


def draw_man(ci, frame, pose="run", ang=0):
    helm, suit, trim, bike = SUITS[ci]
    img = Image.new("RGBA", (CAN, CAN), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if pose == "run":
        sw = [(-4, 6), (0, 7), (4, 6), (0, 7)][frame % 4]
        sw2 = [(4, 6), (0, 7), (-4, 6), (0, 7)][frame % 4]
        base = CEN + 2
        d.line([(CEN, base - 6), (CEN + sw[0], base + 2)], fill=suit + (255,), width=2)
        d.line([(CEN, base - 6), (CEN + sw2[0], base + 2)], fill=trim + (255,), width=2)
        d.line([(CEN - 1, base - 6), (CEN + 2, base - 13)], fill=suit + (255,), width=3)
        d.line([(CEN + 2, base - 11), (CEN + 4 + sw2[0] // 2, base - 8)], fill=trim + (255,), width=1)
        d.ellipse((CEN + 1, base - 19, CEN + 6, base - 14), fill=helm + (255,))
        d.point((CEN + 5, base - 17), fill=(20, 20, 60, 255))
        return outline(img)
    # tumbling body drawn upright then rotated
    d.line([(CEN, CEN + 6), (CEN - 3, CEN + 1)], fill=suit + (255,), width=2)
    d.line([(CEN, CEN + 6), (CEN + 4, CEN + 2)], fill=trim + (255,), width=2)
    d.line([(CEN, CEN + 1), (CEN, CEN - 7)], fill=suit + (255,), width=3)
    d.line([(CEN, CEN - 5), (CEN - 5, CEN - 8)], fill=trim + (255,), width=1)
    d.line([(CEN, CEN - 5), (CEN + 5, CEN - 9)], fill=trim + (255,), width=1)
    d.ellipse((CEN - 3, CEN - 13, CEN + 3, CEN - 8), fill=helm + (255,))
    img = img.rotate(ang, resample=Image.NEAREST, center=(CEN, CEN))
    return outline(img)


def draw_lying(ci):
    helm, suit, trim, bike = SUITS[ci]
    img = Image.new("RGBA", (CAN, CAN), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(CEN - 9, CEN + 4), (CEN + 4, CEN + 4)], fill=suit + (255,), width=3)
    d.line([(CEN - 9, CEN + 2), (CEN - 12, CEN + 5)], fill=trim + (255,), width=2)
    d.ellipse((CEN + 4, CEN + 1, CEN + 10, CEN + 7), fill=helm + (255,))
    return outline(img)


def draw_smoke(n):
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(3 + n):
        x, y = 4 + rng.randrange(8), 12 - n * 3 - i * 2
        r = 2 + (i % 2)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(235, 235, 235, 255), outline=(150, 150, 150, 255))
    return img


def draw_shadow():
    img = Image.new("RGBA", (20, 4), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, 19, 3), fill=(170, 98, 0, 255))
    return img


def draw_flagger(n):
    img = Image.new("RGBA", (24, 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((9, 12, 15, 22), fill=(200, 40, 20, 255), outline=BLACK + (255,))
    d.rectangle((9, 23, 11, 29), fill=(30, 30, 30, 255))
    d.rectangle((13, 23, 15, 29), fill=(30, 30, 30, 255))
    d.rectangle((8, 3, 15, 9), fill=(250, 190, 150, 255), outline=BLACK + (255,))
    d.rectangle((7, 1, 16, 4), fill=(170, 50, 20, 255), outline=BLACK + (255,))
    ay = 12 if n == 0 else 16
    d.line((9, 14, 2, ay), fill=(200, 40, 20, 255), width=2)
    d.rectangle((0, ay - 5 + 2 * n, 3, ay - 2 + 2 * n), fill=(255, 255, 255, 255), outline=BLACK + (255,))
    return img


def draw_tree():
    img = Image.new("RGBA", (30, 44), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((12, 28, 17, 43), fill=(120, 70, 20, 255), outline=BLACK + (255,))
    d.ellipse((1, 1, 28, 33), fill=(50, 150, 20, 255), outline=(20, 80, 10, 255))
    d.ellipse((6, 5, 16, 14), fill=(110, 200, 40, 255))
    return img


def draw_sign(n):
    img = Image.new("RGBA", (28, 34), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((4, 18, 6, 33), fill=(90, 60, 30, 255))
    d.rectangle((21, 18, 23, 33), fill=(90, 60, 30, 255))
    d.rectangle((0, 2, 27, 20), fill=(250, 250, 250, 255), outline=BLACK + (255,))
    col = [(220, 30, 30), (30, 60, 220)][n % 2]
    d.rectangle((3, 5, 24, 9), fill=col + (255,))
    d.rectangle((3, 12, 14, 16), fill=col + (255,))
    return img


def draw_tower():
    img = Image.new("RGBA", (22, 56), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((9, 6, 11, 55), fill=(200, 200, 200, 255), outline=BLACK + (255,))
    d.polygon([(11, 4), (21, 9), (11, 14)], fill=(250, 190, 40, 255), outline=BLACK + (255,))
    return img


def draw_gate():
    img = Image.new("RGBA", (8, 84), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((2, 0, 5, 83), fill=(250, 250, 250, 255), outline=BLACK + (255,))
    for y in range(2, 82, 8):
        d.rectangle((2, y, 5, y + 3), fill=(220, 40, 30, 255))
    return img


def draw_gate_down():
    img = Image.new("RGBA", (8, 84), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((3, 80, 4, 83), fill=(220, 40, 30, 255), outline=BLACK + (255,))
    return img


def draw_lights(n):
    img = Image.new("RGBA", (26, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 25, 9), fill=(40, 40, 40, 255), outline=BLACK + (255,))
    for i in range(3):
        on = n > i and n < 4
        col = (255, 40, 30) if on else (90, 20, 20)
        if n == 4:
            col = (60, 255, 60)
        d.ellipse((3 + i * 8, 2, 8 + i * 8, 7), fill=col + (255,), outline=BLACK + (255,))
    return img


def draw_finish():
    img = Image.new("RGBA", (6, VH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for yy in range(TRACK_TOP + 2, HAY_Y - 2):
        for xx in range(6):
            d.point((xx, yy), fill=BLACK + (255,) if ((yy // 3) + (xx // 3)) % 2 else WHITE + (255,))
    return img


GLYPHS = {
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    " ": ("00000",) * 7,
}


def main():
    out = {"K": dict(VW=VW, VH=VH, WALL_H=WALL_H, TRACK_TOP=TRACK_TOP, LANE_H=LANE_H, HAY_Y=HAY_Y, HUD_Y=HUD_Y,
                     LANE_CONTACT=LANE_CONTACT, PERIOD=PERIOD, WHEEL_BASE=WHEEL_BASE, CEN=CEN, SHEAR=SHEAR),
           "profiles": PROFILES, "flat_len": FLAT_LEN, "glyphs": GLYPHS, "px_white": px8(WHITE)}
    out["hud_black"] = px8(BLACK)
    tracks, ramp_sprites, flat_sprites = [], {}, {}
    for ti, tr in enumerate(TRACKS):
        items, lap = layout(tr)
        for k, s, l0, l1 in items:
            key = (k, l0, l1)
            if k in PROFILES:
                if key not in ramp_sprites:
                    ramp_sprites[key] = draw_ramp(k, l0, l1)
            elif key not in flat_sprites:
                flat_sprites[key] = draw_flat(k, l0, l1)
        tracks.append(dict(name=tr["name"], best=tr["best"], lap=lap, items=items, deco=tr["deco"],
                           base=base_rows(THEMES[tr["theme"]]), wall_px=px8(THEMES[tr["theme"]]["wall"])))
    out["tracks"] = tracks
    out["obs"] = {**ramp_sprites, **flat_sprites}
    bikes = {}
    for ci in range(5):
        for ang in range(-180, 180, 5):
            ai = (ang + 180) // 5
            riding = -40 <= ang <= 75
            for phase in ((0, 1) if riding else (0,)):
                for yaw in ((-1, 0, 1) if -25 <= ang <= 45 else (0,)):
                    bikes[(ci, ai, phase, yaw)] = runs_of(draw_bike(ang, ci, phase, yaw))
        for ang in range(-180, 180, 15):
            bikes[(ci, "solo", ang)] = runs_of(draw_bike(ang, ci, 0, 0, rider=False))
        for ang in range(0, 360, 30):
            bikes[(ci, "tumble", ang)] = runs_of(draw_man(ci, 0, "tumble", ang))
        for f in range(4):
            bikes[(ci, "run", f)] = runs_of(draw_man(ci, f))
        bikes[(ci, "lying")] = runs_of(draw_lying(ci))
    out["bikes"] = bikes
    out["misc"] = {
        "smoke": [runs_of(draw_smoke(n)) for n in range(3)], "shadow": runs_of(draw_shadow()),
        "flagger": [runs_of(draw_flagger(n)) for n in range(2)], "tree": runs_of(draw_tree()),
        "sign": [runs_of(draw_sign(n)) for n in range(2)], "tower": runs_of(draw_tower()),
        "gate": runs_of(draw_gate()), "gate_down": runs_of(draw_gate_down()),
        "lights": [runs_of(draw_lights(n)) for n in range(5)], "finish": runs_of(draw_finish(), crop=False)}
    save_bundle("g_motocross.bin", out)


if __name__ == "__main__":
    main()
