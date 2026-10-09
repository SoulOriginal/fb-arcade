# Build-time art for the Flappy Bird module: everything is drawn procedurally at the game's native 144x256
# resolution and expanded 4x (576x1024) so it fits 1080 lines. Writes g_flappy.bin.
import math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from buildlib import BOLD, save_bundle

SC = 4
NW, NH = 144, 256
GROUND_Y = 200
LAYER_H = 72                    # city layer covers native rows 128..199
LAYER_Y = GROUND_Y - LAYER_H
LAYER_PERIOD = 288
HATCH_PERIOD = 12

K = (84, 56, 71)                # the dark outline colour of the original art
WHITE = (255, 255, 255)
ORANGE = (252, 115, 40)

THEMES = {
    "day": dict(sky=(78, 192, 202), cloud=(228, 249, 236), bld=(210, 240, 200), shade=(176, 218, 186),
                win=(190, 226, 190), bush=(114, 196, 52), bushdk=(78, 142, 40), bushhi=(158, 229, 89)),
    "night": dict(sky=(14, 52, 84), cloud=(40, 86, 118), bld=(32, 86, 112), shade=(24, 66, 92),
                  win=(52, 108, 128), bush=(30, 98, 62), bushdk=(20, 66, 44), bushhi=(48, 128, 78)),
}


def c565(c):
    return ((c[0] >> 3) << 11 | (c[1] >> 2) << 5 | (c[2] >> 3)).to_bytes(2, "little")


def row_bytes(img, y, scale=SC, x0=0, x1=None):
    px = img.load()
    x1 = img.width if x1 is None else x1
    out = bytearray()
    for x in range(x0, x1):
        out += c565(px[x, y][:3]) * scale
    return bytes(out)


def runsprite(img, scale=SC):
    # Transparent sprite -> opaque runs per scanline [x_bytes, bytes]; the game blits only the runs.
    img = img.convert("RGBA")
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    box = img.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox()
    if not box:
        return [0, 0, 1, [[]], 1]
    x0, y0, x1, y1 = box
    px = img.load()
    rows = []
    for y in range(y0, y1):
        row, x = [], x0
        while x < x1:
            if px[x, y][3] >= 128:
                s, buf = x, bytearray()
                while x < x1 and px[x, y][3] >= 128:
                    buf += c565(px[x, y][:3])
                    x += 1
                row.append([s * 2, bytes(buf)])
            else:
                x += 1
        rows.append(row)
    return [x0, y0, y1 - y0, rows, x1 - x0]


# ---- bird -------------------------------------------------------------------------------------------------
BIRD_BODY = [
    "....KKKKKK.......",
    "..KKYYYYYKKKKKKK.",
    ".KYYYYYYYKWWWWWK.",
    "KYYYYYYYYKWWWBBK.",
    "KYYYYYYYYKWWWBBK.",
    "KYYYYYYYYKWWWWWK.",
    "KYYYYYYYYYKKKKKKK",
    "KYYYYYYYYKRRRRRRK",
    ".KYYYYYYYKKKKKKKK",
    ".KOYYYYYYYKRRRRK.",
    "..KKOOOOOOKKKKK..",
    "....KKKKKKK......",]
BIRD_COLORS = {
    "yellow": dict(Y=(248, 200, 56), O=(240, 150, 40), L=(255, 232, 130)),
    "red": dict(Y=(236, 84, 64), O=(190, 52, 52), L=(255, 150, 120)),
    "blue": dict(Y=(84, 168, 232), O=(48, 116, 190), L=(160, 214, 250)),
}
WING = [
    ".KKKKK.",
    "KWWWWWK",
    "KWWWLK.",
    ".KKKK..",
]
WING_Y = [2, 4, 6]   # wing up, middle, down: first body row the wing covers


def bird_image(colour, frame):
    pal = dict(BIRD_COLORS[colour])
    pal.update(K=K, W=WHITE, B=(30, 20, 30), R=(244, 81, 30))
    im = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    px = im.load()
    ox, oy = 3, 6
    for y, line in enumerate(BIRD_BODY):
        assert len(line) == 17, (y, len(line))
        for x, ch in enumerate(line):
            if ch != ".":
                px[ox + x, oy + y] = pal[ch] + (255,)
    wy = WING_Y[frame]
    for y, line in enumerate(WING):
        for x, ch in enumerate(line):
            if ch != ".":
                col = {"K": K, "W": WHITE, "L": (255, 232, 130)}[ch]
                px[ox + 2 + x, oy + wy + y] = col + (255,)
    # highlight on the back
    for x in range(4, 8):
        px[ox + x, oy + 2] = pal["L"] + (255,)
    return im


ANGLES = [-25, -12, 0, 15, 30, 45, 60, 75, 90]


def bird_sprites():
    out = {}
    for colour in BIRD_COLORS:
        per_angle = []
        for ang in ANGLES:
            frames = []
            for f in range(3):
                big = bird_image(colour, f).resize((24 * SC, 24 * SC), Image.NEAREST)
                big = big.rotate(-ang, resample=Image.NEAREST, center=(12 * SC, 12 * SC))
                frames.append(runsprite(big, 1))
            per_angle.append(frames)
        out[colour] = per_angle
    return out


# ---- fonts -------------------------------------------------------------------------------------------------
GLYPHS = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".####|#....|#....|#....|#....|#....|.####", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####", "3": ".###.|#...#|....#|..##.|....#|#...#|.###.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": "..##.|.#...|#....|####.|#...#|#...#|.###.", "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.", "9": ".###.|#...#|#...#|.####|....#|...#.|.##..",
}


def pixel_text(s, colour, outline=None, space=1):
    # 5x7 bitmap text; outline=True adds the dark 1 px rim the original uses for small white numbers.
    w = len(s) * (5 + space) - space
    pad = 1 if outline else 0
    im = Image.new("RGBA", (w + 2 * pad, 7 + 2 * pad), (0, 0, 0, 0))
    mask = Image.new("L", im.size, 0)
    mp = mask.load()
    for i, ch in enumerate(s):
        for y, line in enumerate(GLYPHS[ch].split("|")):
            for x, v in enumerate(line):
                if v == "#":
                    mp[pad + i * (5 + space) + x, pad + y] = 255
    if outline:
        rim = mask.filter(ImageFilter.MaxFilter(3))
        im.paste(Image.new("RGBA", im.size, K + (255,)), (0, 0), rim)
    im.paste(Image.new("RGBA", im.size, colour + (255,)), (0, 0), mask)
    return im


def ttf_mask(text, size):
    f = ImageFont.truetype(BOLD, size)
    probe = Image.new("L", (400, 80), 0)
    d = ImageDraw.Draw(probe)
    d.fontmode = "1"
    d.text((4, 4), text, font=f, fill=255)
    return probe.crop(probe.getbbox())


def outlined(mask, fill, rings):
    # rings: [(dilation steps, colour)] from the outside in, then the fill; draws the stacked rim of the card lettering.
    pad = 1 + max(r for r, _ in rings)
    canvas = Image.new("RGBA", (mask.width + 2 * pad, mask.height + 2 * pad), (0, 0, 0, 0))
    m = Image.new("L", canvas.size, 0)
    m.paste(mask, (pad, pad))
    for steps, col in rings:
        grown = m
        for _ in range(steps):
            grown = grown.filter(ImageFilter.MaxFilter(3))
        canvas.paste(Image.new("RGBA", canvas.size, col + (255,)), (0, 0), grown)
    canvas.paste(Image.new("RGBA", canvas.size, fill + (255,)), (0, 0), m)
    return canvas


def big_digits():
    # Score font: thick white digits with a dark rim, all on the same canvas so the pitch is constant.
    out = []
    for d in "0123456789":
        m = ttf_mask(d, 26)
        im = outlined(m, WHITE, [(2, K)])
        canvas = Image.new("RGBA", (16, 22), (0, 0, 0, 0))
        canvas.paste(im, ((16 - im.width) // 2, (22 - im.height) // 2), im)
        out.append(runsprite(canvas))
    return out


def card_text(text):
    m = ttf_mask(text, 15)
    return outlined(m, ORANGE, [(2, K), (1, WHITE)])


# ---- scenery -------------------------------------------------------------------------------------------------
def make_layer(t, seed):
    rnd = random.Random(seed)
    im = Image.new("RGB", (LAYER_PERIOD, LAYER_H), t["sky"])
    d = ImageDraw.Draw(im)

    def wrap(fn):
        for off in (-LAYER_PERIOD, 0, LAYER_PERIOD):
            fn(off)

    x = 0
    clouds = []
    while x < LAYER_PERIOD:
        clouds.append((x + rnd.randint(0, 10), rnd.randint(-3, 3), rnd.randint(7, 11)))
        x += rnd.randint(34, 56)
    for cx, dy, r in clouds:
        def cloud(off, cx=cx, dy=dy, r=r):
            by = LAYER_H - 40 + dy
            for k, (ddx, rr) in enumerate([(0, r), (r, r + 2), (2 * r + 3, r - 1), (-r + 2, r - 3)]):
                d.ellipse((cx + off + ddx - rr, by - rr, cx + off + ddx + rr, by + rr), fill=t["cloud"])
            d.rectangle((cx + off - r, by, cx + off + 2 * r + 3, LAYER_H - 20), fill=t["cloud"])
        wrap(cloud)
    x = 0
    blds = []
    while x < LAYER_PERIOD:
        w = rnd.randint(11, 24)
        if LAYER_PERIOD - x - w < 11:
            w = LAYER_PERIOD - x
        blds.append((x, w, rnd.randint(16, 38)))
        x += w
    for bx, w, h in blds:
        def bld(off, bx=bx, w=w, h=h):
            top = LAYER_H - 14 - h
            d.rectangle((bx + off, top, bx + off + w - 1, LAYER_H), fill=t["bld"])
            d.rectangle((bx + off + w - max(3, w // 4), top, bx + off + w - 1, LAYER_H), fill=t["shade"])
            for wy in range(top + 4, LAYER_H - 16, 6):
                for wx in range(bx + off + 3, bx + off + w - max(3, w // 4) - 2, 5):
                    d.rectangle((wx, wy, wx + 1, wy + 2), fill=t["win"])
        wrap(bld)
    x = 0
    while x < LAYER_PERIOD:
        r = rnd.randint(6, 10)

        def bush(off, x=x, r=r):
            cy = LAYER_H - 8
            d.ellipse((x + off - r, cy - r, x + off + r, cy + r), fill=t["bushdk"])
            d.ellipse((x + off - r + 1, cy - r, x + off + r - 1, cy + r - 2), fill=t["bush"])
            d.ellipse((x + off - r + 3, cy - r + 2, x + off - 1, cy - 2), fill=t["bushhi"])
        wrap(bush)
        x += rnd.randint(9, 16)
    d.rectangle((0, LAYER_H - 4, LAYER_PERIOD, LAYER_H), fill=t["bush"])
    return im


def ground_rows():
    # (kind, data) for native rows 0..55 of the ground; hatch rows are generated per x so they can scroll.
    return [("c", K), ("c", (168, 235, 98)), ("h", 0), ("h", 1), ("h", 2), ("h", 3), ("c", (85, 128, 34)),
            ("c", (213, 167, 80)), ("c", (240, 230, 160))] + [("c", (222, 216, 149))] * 46 + [("c", (213, 167, 80))]


def hatch_pixel(x, r):
    return (115, 191, 46) if ((x - r) % HATCH_PERIOD) < HATCH_PERIOD // 2 else (168, 235, 98)


def scene_rows(theme, seed):
    # Per native row: colour bytes (uniform rows) or a scrollable strip. Returns the dict stored in the bundle plus a PIL
    # picture of the unscrolled scene used for the side bars.
    t = THEMES[theme]
    layer = make_layer(t, seed)
    wide = Image.new("RGB", (LAYER_PERIOD + NW, LAYER_H))
    wide.paste(layer, (0, 0))
    wide.paste(layer.crop((0, 0, NW, LAYER_H)), (LAYER_PERIOD, 0))
    rowcol = [None] * NH
    lay, gnd = {}, {}
    scene = Image.new("RGB", (NW, NH), t["sky"])
    for y in range(NH):
        if y < LAYER_Y:
            rowcol[y] = c565(t["sky"])
        elif y < GROUND_Y:
            r = y - LAYER_Y
            px = layer.load()
            first = px[0, r]
            if all(px[x, r] == first for x in range(LAYER_PERIOD)):
                rowcol[y] = c565(first)
            else:
                lay[y] = row_bytes(wide, r)
            scene.paste(layer.crop((0, r, NW, r + 1)), (0, y))
        else:
            kind, data = ground_rows()[y - GROUND_Y]
            if kind == "c":
                rowcol[y] = c565(data)
                scene.paste(Image.new("RGB", (NW, 1), data), (0, y))
            else:
                strip = Image.new("RGB", (NW + HATCH_PERIOD, 1))
                for x in range(NW + HATCH_PERIOD):
                    strip.putpixel((x, 0), hatch_pixel(x, data))
                gnd[y] = row_bytes(strip, 0)
                scene.paste(strip.crop((0, 0, NW, 1)), (0, y))
    return dict(rowcol=rowcol, lay=lay, gnd=gnd), scene


def side_rows(scene):
    # The 1920x1080 screen is wider and taller than the 576x1024 play field: the scene is mirror-tiled around it and dimmed, so the
    # play field reads as a bright window. Returned as one full 1920 px row per native row (4 screen lines each).
    cols, rows = 1920 // SC, 1080 // SC           # 480 x 270 native
    ox, oy = (cols - NW) // 2, (rows - NH) // 2   # 168, 7 (the play field is shifted by 28 lines: 7 native rows)
    big = Image.new("RGB", (cols, rows))
    for c in range(cols):
        u = (c - ox) % (2 * NW)
        if u >= NW:
            u = 2 * NW - 1 - u
        for r in range(rows):
            y = min(max(r - oy, 0), NH - 1)
            big.putpixel((c, r), scene.getpixel((u, y)))
    big = Image.eval(big, lambda v: int(v * 0.42))
    out = []
    for r in range(rows):
        out.append(row_bytes(big, r, SC))
    return out


# ---- pipes ---------------------------------------------------------------------------------------------------
PIPE_W, CAP_H, BODY_W = 26, 13, 22


def pipe_column_colours(w):
    cols = [K, (224, 250, 140), (224, 250, 140), (158, 229, 89), (158, 229, 89), (158, 229, 89)]
    mid = w - len(cols) - 5
    cols += [(115, 191, 46)] * mid
    cols += [(85, 128, 34)] * 4 + [K]
    assert len(cols) == w
    return cols


def pipe_art():
    cap = Image.new("RGB", (PIPE_W, CAP_H))
    cc = pipe_column_colours(PIPE_W)
    for y in range(CAP_H):
        for x in range(PIPE_W):
            col = cc[x]
            if y in (0, CAP_H - 1):
                col = K
            elif y in (CAP_H - 2,):
                col = tuple(int(v * 0.8) for v in col)
            cap.putpixel((x, y), col)
    bc = pipe_column_colours(BODY_W)
    body = Image.new("RGB", (BODY_W, 1))
    for x in range(BODY_W):
        body.putpixel((x, 0), bc[x])
    return dict(body=row_bytes(body, 0), cap=[row_bytes(cap, y) for y in range(CAP_H)])


# ---- cards ---------------------------------------------------------------------------------------------------
def panel_image():
    w, h = 112, 58
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 4, fill=K)
    d.rounded_rectangle((1, 1, w - 2, h - 2), 3, fill=(255, 250, 215))
    d.rounded_rectangle((2, 2, w - 3, h - 3), 3, fill=(222, 216, 149))
    d.rectangle((3, h - 5, w - 4, h - 3), fill=(213, 190, 110))
    return im


SLOT_BG = (206, 199, 132)
MEDAL_COLOURS = {
    "bronze": ((140, 78, 36), (205, 127, 50), (243, 180, 110)),
    "silver": ((106, 112, 124), (192, 197, 208), (238, 241, 248)),
    "gold": ((176, 116, 8), (243, 190, 40), (255, 235, 130)),
    "platinum": ((92, 146, 178), (186, 224, 242), (248, 253, 255)),
}


def medal_image(kind):
    rim, mid, hi = MEDAL_COLOURS[kind]
    im = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, 21, 21), fill=K)
    d.ellipse((1, 1, 20, 20), fill=rim)
    d.ellipse((2, 2, 19, 19), fill=mid)
    d.ellipse((4, 4, 17, 17), fill=rim)
    d.ellipse((5, 5, 16, 16), fill=mid)
    for i in range(4):
        d.point((4 + i, 8 - i // 2 + 0), fill=hi)
    d.line((5, 6, 9, 4), fill=hi)
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = 5 if i % 2 == 0 else 2.2
        pts.append((10.5 + r * math.cos(a), 11 + r * math.sin(a)))
    d.polygon(pts, fill=hi)
    return im


def sparkle(frame):
    s = [0, 1, 2, 1][frame]
    im = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if s == 0:
        d.point((3, 3), fill=WHITE)
    else:
        d.line((3 - s - 1, 3, 3 + s + 1, 3), fill=WHITE)
        d.line((3, 3 - s - 1, 3, 3 + s + 1), fill=WHITE)
    return im


def medal_frames(kind):
    # Opaque 26x26 tiles (medal + slot background + twinkle) so the game never has to erase a sparkle.
    frames = []
    for f in range(8):
        tile = Image.new("RGBA", (26, 26), SLOT_BG + (255,))
        tile.paste(medal_image(kind), (2, 2), medal_image(kind))
        a = f / 8 * 2 * math.pi
        sx, sy = 13 + 9 * math.cos(a) - 3, 13 + 9 * math.sin(a) - 3
        sp = sparkle(f % 4)
        tile.paste(sp, (int(sx), int(sy)), sp)
        frames.append(runsprite(tile))
    return frames


def slot_tile(kind=None):
    tile = Image.new("RGBA", (26, 26), SLOT_BG + (255,))
    if kind:
        tile.paste(medal_image(kind), (2, 2), medal_image(kind))
    return runsprite(tile)


def button(label):
    w, h = 48, 17
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 3, fill=K)
    d.rounded_rectangle((1, 1, w - 2, h - 2), 2, fill=(255, 190, 120))
    d.rounded_rectangle((2, 2, w - 3, h - 3), 2, fill=ORANGE)
    d.rectangle((2, h - 6, w - 3, h - 3), fill=(222, 82, 20))
    t = pixel_text(label, WHITE, outline=True)
    im.paste(t, ((w - t.width) // 2, (h - t.height) // 2), t)
    return im


def tap_hint():
    # Hand with tap rings, the picture under the Get Ready lettering.
    im = Image.new("RGBA", (40, 46), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.arc((8, 0, 32, 20), 200, 340, fill=K)
    d.arc((12, 4, 28, 16), 200, 340, fill=WHITE)
    d.polygon([(16, 14), (22, 14), (22, 24), (35, 26), (36, 44), (14, 44), (11, 32), (16, 28)], fill=K)
    d.polygon([(17, 15), (21, 15), (21, 27), (34, 28), (35, 43), (15, 43), (12, 32), (17, 29)], fill=WHITE)
    d.line((21, 28, 21, 36), fill=(200, 200, 205))
    d.line((26, 29, 26, 36), fill=(200, 200, 205))
    d.line((30, 29, 30, 36), fill=(200, 200, 205))
    d.rectangle((15, 40, 34, 43), fill=(214, 214, 222))
    return im


def build():
    data = {}
    for name, seed in (("day", 11), ("night", 23)):
        rows, scene = scene_rows(name, seed)
        rows["side"] = side_rows(scene)
        data[name] = rows
    data["pipe"] = pipe_art()
    data["bird"] = bird_sprites()
    data["angles"] = ANGLES
    data["digits"] = big_digits()
    data["small"] = [runsprite(pixel_text(c, WHITE, outline=True)) for c in "0123456789"]
    data["get_ready"] = runsprite(card_text("GET READY"))
    data["game_over"] = runsprite(card_text("GAME OVER"))
    data["tap"] = runsprite(tap_hint())
    data["panel"] = runsprite(panel_image())
    label = lambda s: runsprite(pixel_text(s, (232, 98, 40)))
    data["lbl_medal"], data["lbl_score"], data["lbl_best"] = label("MEDAL"), label("SCORE"), label("BEST")
    new = Image.new("RGBA", (21, 9), (0, 0, 0, 0))
    ImageDraw.Draw(new).rounded_rectangle((0, 0, 20, 8), 2, fill=(228, 40, 40))
    t = pixel_text("NEW", WHITE)
    new.paste(t, (3, 1), t)
    data["new"] = runsprite(new)
    data["ok"], data["share"] = runsprite(button("OK")), runsprite(button("SHARE"))
    data["slot"] = slot_tile()
    data["medal"] = {k: slot_tile(k) for k in MEDAL_COLOURS}
    data["sparkle"] = {k: medal_frames(k) for k in MEDAL_COLOURS}
    save_bundle("g_flappy.bin", data)


def preview():
    # Contact sheet for eyeballing the hand-drawn art, never shipped.
    sheet = Image.new("RGB", (900, 700), (78, 192, 202))
    x = 4
    for colour in BIRD_COLORS:
        for f in range(3):
            im = bird_image(colour, f).resize((24 * 6, 24 * 6), Image.NEAREST)
            sheet.paste(im, (x, 4), im)
            x += 150
    y = 160
    for img in (card_text("GET READY"), card_text("GAME OVER"), tap_hint(), panel_image(), button("OK"), button("SHARE")):
        im = img.resize((img.width * 3, img.height * 3), Image.NEAREST)
        sheet.paste(im, (4, y), im)
        y += im.height + 6
        if y > 600:
            break
    sheet.save("flappy_art_preview.png")


if __name__ == "__main__":
    preview()
    build()
