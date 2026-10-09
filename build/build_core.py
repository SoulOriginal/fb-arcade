# Builds sprites for the snake and tetris games into games.bin (the Pi has no PIL).
import colorsys, pickle, zlib
from array import array
from PIL import Image, ImageDraw, ImageFont

from buildlib import BOLD, MONO


def pack(img):
    it = iter(img.convert("RGB").tobytes())
    a = array("H", ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3) for r, g, b in zip(it, it, it)))
    return (img.width, img.height, a.tobytes())


def label(text, size, color, pad=0):
    f = ImageFont.truetype(BOLD, size)
    l, t, r, b = f.getbbox(text)
    img = Image.new("RGB", (r - l + 2 * pad, b - t + 2 * pad))
    ImageDraw.Draw(img).text((pad - l, pad - t), text, font=f, fill=color)
    return img


out = {}

# Glyphs 40x80 for numbers: 0-9 and "/".
g = []
font = ImageFont.truetype(MONO, 64)
for ch in "0123456789/":
    im = Image.new("RGB", (40, 80))
    ImageDraw.Draw(im).text((20, 40), ch, font=font, fill=(255, 255, 255), anchor="mm")
    g.append(pack(im))
out["glyph"] = g

# Labels, index order is shared with games.py.
out["label"] = [
    pack(label("LENGTH", 44, (150, 160, 190))),
    pack(label("SCORE", 44, (150, 160, 190))),
    pack(label("LINES", 44, (150, 160, 190))),
    pack(label("LEVEL", 44, (150, 160, 190))),
    pack(label("NEXT", 44, (150, 160, 190))),
    pack(label("YOU WIN", 210, (255, 215, 0), 24)),
    pack(label("GAME OVER", 150, (240, 60, 60), 24)),
    pack(label("APPLES", 44, (150, 160, 190))),
]

# Snake board: 80x80 cells over a dark garden floor. Four floor variants (by cell parity, two of them with small
# decorations) and every sprite is pre-composited on each variant, so erasing a cell just blits its empty tile.
# Per variant: 0 empty floor; 1 + hue*16 + band body (band 0 next to the head, 15 at the tail; the palette is a
# light-to-dark gradient, hue 0 is green, the other hues are for the win flash); 97..100 head right/left/down/up;
# 101 growing apple; 102 shrinking apple. Coordinates are laid out for a 48 px cell and scaled by K.
import random as _random
CELL = 80
K = CELL / 48
SS = 3
VARIANTS = 4
PER_VARIANT = 103


def floor_tile(v):
    rnd = _random.Random(100 + v)
    light = v in (0, 3)
    base = (22, 46, 40) if light else (17, 37, 33)
    img = Image.new("RGB", (CELL, CELL), base)
    d = ImageDraw.Draw(img)
    for y in range(CELL):       # soft top-to-bottom light falloff
        f = 1.0 + 0.10 * (1 - y / CELL)
        d.line((0, y, CELL, y), fill=tuple(min(255, int(c * f)) for c in base))
    for _ in range(40):         # grain
        x, y = rnd.randrange(CELL), rnd.randrange(CELL)
        shade = rnd.choice((-5, 4))
        d.point((x, y), fill=tuple(max(0, min(255, c + shade)) for c in base))
    d.rectangle((0, 0, CELL - 1, CELL - 1), outline=tuple(c + 7 for c in base))
    d.line((1, 1, CELL - 2, 1), fill=tuple(c + 12 for c in base))
    d.line((1, 1, 1, CELL - 2), fill=tuple(c + 9 for c in base))
    if v == 2:                  # tiny flowers
        for fx, fy, col in ((18, 56, (230, 210, 90)), (55, 22, (240, 240, 250)), (62, 62, (200, 120, 220))):
            d.ellipse((fx - 3, fy - 3, fx + 3, fy + 3), fill=col)
            d.ellipse((fx - 1, fy - 1, fx + 1, fy + 1), fill=(250, 190, 60))
            d.line((fx, fy + 3, fx, fy + 9), fill=(40, 110, 60))
    if v == 3:                  # pebbles
        for px, py, r in ((20, 24, 5), (58, 52, 4), (34, 62, 3)):
            d.ellipse((px - r, py - r + 1, px + r, py + r + 1), fill=(10, 24, 22))
            d.ellipse((px - r, py - r, px + r, py + r), fill=(58, 82, 78), outline=(36, 58, 54))
    return img


FLOORS = [floor_tile(v) for v in range(VARIANTS)]


def cell(draw, v):
    # Shapes are drawn on a transparent supersampled layer with a soft shadow, then laid over the floor tile.
    layer = Image.new("RGBA", (CELL * SS, CELL * SS), (0, 0, 0, 0))
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    draw(ImageDraw.Draw(layer), K * SS, False)
    draw(ImageDraw.Draw(shadow), K * SS, True)
    shadow = shadow.resize((CELL, CELL), Image.LANCZOS)
    layer = layer.resize((CELL, CELL), Image.LANCZOS)
    tile = FLOORS[v].convert("RGBA")
    tile = Image.alpha_composite(tile, shadow.transform(shadow.size, Image.AFFINE, (1, 0, -3, 0, 1, -4)))
    return pack(Image.alpha_composite(tile, layer).convert("RGB"))


def body_color(hue, band):
    f = band / 15
    base = (0.30 + hue / 6) % 1
    return tuple(int(255 * v) for v in colorsys.hsv_to_rgb(base, 0.45 + 0.5 * f, 1.0 - 0.68 * f))


def shape_fill(col, shadow):
    return (0, 0, 0, 120) if shadow else col + (255,)


def body_shape(c):
    return lambda d, k, sh: d.rounded_rectangle((2 * k, 2 * k, 45 * k, 45 * k), radius=11 * k, fill=shape_fill(c, sh))


EYES = {0: ((34, 12), (34, 35)), 1: ((13, 12), (13, 35)), 2: ((12, 34), (35, 34)), 3: ((12, 13), (35, 13))}


def head_shape(direction):
    def draw(d, k, sh):
        d.rounded_rectangle((1 * k, 1 * k, 46 * k, 46 * k), radius=13 * k, fill=shape_fill(body_color(0, 0), sh))
        if sh:
            return
        for ex, ey in EYES[direction]:
            d.ellipse(((ex - 5) * k, (ey - 5) * k, (ex + 5) * k, (ey + 5) * k), fill=(255, 255, 255, 255))
            d.ellipse(((ex - 2) * k, (ey - 2) * k, (ex + 2) * k, (ey + 2) * k), fill=(10, 10, 10, 255))
    return draw


def apple_shape(kind):
    body, rim, hi = ((225, 40, 40), (255, 140, 140), (255, 210, 210)) if kind == 0 else ((60, 90, 235), (150, 170, 255), (210, 220, 255))

    def draw(d, k, sh):
        d.ellipse((7 * k, 10 * k, 41 * k, 44 * k), fill=(0, 0, 0, 120) if sh else body + (255,),
                  outline=None if sh else rim + (255,), width=max(1, int(k)))
        if sh:
            return
        d.ellipse((13 * k, 15 * k, 20 * k, 22 * k), fill=hi + (255,))
        d.line((24 * k, 12 * k, 28 * k, 3 * k), fill=(120, 200, 60, 255), width=int(4 * k))
        if kind == 1:           # a white bar marks the apple that makes the snake shorter
            d.rectangle((16 * k, 26 * k, 32 * k, 30 * k), fill=(255, 255, 255, 255))
    return draw


snake = []
for v in range(VARIANTS):
    snake.append(pack(FLOORS[v]))
    for hue in range(6):
        for band in range(16):
            snake.append(cell(body_shape(body_color(hue, band)), v))
    for direction in range(4):
        snake.append(cell(head_shape(direction), v))
    snake.append(cell(apple_shape(0), v))
    snake.append(cell(apple_shape(1), v))
assert len(snake) == VARIANTS * PER_VARIANT
out["snake"] = snake
# Strip colors for the crawling animation: the head color of each hue, as RGB565.
out["snake_strip"] = [(lambda c: (c[0] >> 3) << 11 | (c[1] >> 2) << 5 | (c[2] >> 3))(body_color(h, 0)) for h in range(6)]


def brick_block():
    # A 2x2-cell wall: staggered bricks with light top and left edges and dark mortar.
    size = CELL * 2
    img = Image.new("RGB", (size, size), (74, 44, 36))
    d = ImageDraw.Draw(img)
    rows, bw = 6, size // 3
    bh = size // rows
    rnd = _random.Random(7)
    for r in range(rows):
        off = (bw // 2) if r % 2 else 0
        for c in range(-1, 4):
            x0, y0 = c * bw + off, r * bh
            shade = rnd.randint(-14, 14)
            col = (178 + shade, 78 + shade // 2, 52 + shade // 3)
            d.rectangle((x0 + 2, y0 + 2, x0 + bw - 3, y0 + bh - 3), fill=col)
            d.line((x0 + 2, y0 + 2, x0 + bw - 3, y0 + 2), fill=(225 + shade // 2, 130, 90))
            d.line((x0 + 2, y0 + 2, x0 + 2, y0 + bh - 3), fill=(210 + shade // 2, 110, 76))
            d.line((x0 + 2, y0 + bh - 3, x0 + bw - 3, y0 + bh - 3), fill=(120, 48, 34))
            d.line((x0 + bw - 3, y0 + 2, x0 + bw - 3, y0 + bh - 3), fill=(130, 52, 36))
    d.rectangle((0, 0, size - 1, size - 1), outline=(40, 22, 18), width=3)
    return img


out["snake_brick"] = [pack(brick_block())]

# Tetris cells 48x48: 0 empty, 1..7 pieces, 8 white (line flash).
cells = []
EMPTY = (25, 25, 25)
for c in [EMPTY, (0, 220, 230), (240, 220, 0), (170, 60, 220), (60, 200, 60), (230, 50, 50), (50, 80, 230), (240, 140, 30), (255, 255, 255)]:
    im = Image.new("RGB", (48, 48))
    d = ImageDraw.Draw(im)
    if c == EMPTY:
        d.rectangle((0, 0, 47, 47), outline=c)
    else:
        d.rectangle((1, 1, 46, 46), fill=c, outline=tuple(v // 2 for v in c))
        light = tuple(min(255, v + 90) for v in c)
        d.line((2, 2, 45, 2), fill=light, width=3)
        d.line((2, 2, 2, 45), fill=light, width=3)
    cells.append(pack(im))
out["tetris"] = cells

data = zlib.compress(pickle.dumps(out, protocol=4), 9)
open("games.bin", "wb").write(data)
print(len(data) // 1024, "KiB")
