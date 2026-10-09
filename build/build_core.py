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
]

# Snake cells 80x80 (the board is 24x12). 0 empty; 1 + hue*16 + band body (band 0 next to the head, 15 at the
# tail; the palette is a light-to-dark gradient, hue 0 is green, the other hues are for the win flash);
# 97..100 head right/left/down/up; 101 apple. Coordinates are laid out for a 48 px cell and scaled by K.
CELL = 80
K = CELL / 48
SS = 3


def cell(draw):
    big = Image.new("RGB", (CELL * SS, CELL * SS))
    draw(ImageDraw.Draw(big), K * SS)
    return pack(big.resize((CELL, CELL), Image.LANCZOS))


def body_color(hue, band):
    f = band / 15
    base = (0.30 + hue / 6) % 1
    return tuple(int(255 * v) for v in colorsys.hsv_to_rgb(base, 0.45 + 0.5 * f, 1.0 - 0.68 * f))


snake = [pack(Image.new("RGB", (CELL, CELL)))]
for hue in range(6):
    for band in range(16):
        snake.append(cell(lambda d, k, c=body_color(hue, band): d.rounded_rectangle((2 * k, 2 * k, 45 * k, 45 * k), radius=11 * k, fill=c)))
EYES = {0: ((34, 12), (34, 35)), 1: ((13, 12), (13, 35)), 2: ((12, 34), (35, 34)), 3: ((12, 13), (35, 13))}


def head(direction):
    def draw(d, k):
        d.rounded_rectangle((1 * k, 1 * k, 46 * k, 46 * k), radius=13 * k, fill=body_color(0, 0))
        for ex, ey in EYES[direction]:
            d.ellipse(((ex - 5) * k, (ey - 5) * k, (ex + 5) * k, (ey + 5) * k), fill=(255, 255, 255))
            d.ellipse(((ex - 2) * k, (ey - 2) * k, (ex + 2) * k, (ey + 2) * k), fill=(10, 10, 10))
    return cell(draw)


for direction in range(4):
    snake.append(head(direction))


def apple(d, k):
    d.ellipse((7 * k, 10 * k, 41 * k, 44 * k), fill=(225, 40, 40), outline=(255, 140, 140), width=max(1, int(k)))
    d.line((24 * k, 12 * k, 28 * k, 3 * k), fill=(120, 200, 60), width=int(4 * k))


snake.append(cell(apple))
out["snake"] = snake
# Strip colors for the crawling animation: the head color of each hue, as RGB565.
out["snake_strip"] = [(lambda c: (c[0] >> 3) << 11 | (c[1] >> 2) << 5 | (c[2] >> 3))(body_color(h, 0)) for h in range(6)]

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
