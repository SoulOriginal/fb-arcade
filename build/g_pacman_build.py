# Build-time script for the Pac-Man game: draws the maze and every sprite procedurally and writes g_pacman.bin.
# Sprites are stored as (w, h, pixels, mask) tuples: pixels are RGB565 (zero outside the shape), the mask holds
# 0xFFFF per covered pixel so the game can composite them over the maze without reading the framebuffer.
import math
from array import array
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont
from buildlib import pack, save_bundle, BOLD

TILE = 32
MAZE = [
    "############################",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#o####.#####.##.#####.####o#",
    "#.####.#####.##.#####.####.#",
    "#..........................#",
    "#.####.##.########.##.####.#",
    "#.####.##.########.##.####.#",
    "#......##....##....##......#",
    "######.##### ## #####.######",
    "XXXXX#.##### ## #####.#XXXXX",
    "XXXXX#.##          ##.#XXXXX",
    "XXXXX#.## ###--### ##.#XXXXX",
    "######.## #      # ##.######",
    "      .   #      #   .      ",
    "######.## #      # ##.######",
    "XXXXX#.## ######## ##.#XXXXX",
    "XXXXX#.##          ##.#XXXXX",
    "XXXXX#.## ######## ##.#XXXXX",
    "######.## ######## ##.######",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#.####.#####.##.#####.####.#",
    "#o..##.......  .......##..o#",
    "###.##.##.########.##.##.###",
    "###.##.##.########.##.##.###",
    "#......##....##....##......#",
    "#.##########.##.##########.#",
    "#.##########.##.##########.#",
    "#..........................#",
    "############################",
]
COLS, ROWS = 28, 31
assert all(len(r) == COLS for r in MAZE) and len(MAZE) == ROWS
assert sum(r.count(".") for r in MAZE) == 240 and sum(r.count("o") for r in MAZE) == 4, "the arcade maze has 240 dots and 4 energizers"

BLUE = (33, 33, 255)
WALL_BLUE = (40, 60, 255)
PEACH = (255, 184, 174)
GHOST_COLORS = [(255, 0, 0), (255, 184, 255), (0, 255, 255), (255, 184, 82)]
DIRS = [(0, -1), (-1, 0), (0, 1), (1, 0)]  # up, left, down, right: the same order the game uses


def sprite(img):
    # RGBA -> (w, h, pixels, mask); the alpha channel is thresholded so edges stay clean over any background.
    img = img.convert("RGBA")
    alpha = img.getchannel("A").point(lambda a: 255 if a >= 110 else 0)
    rgb = Image.new("RGB", img.size, (0, 0, 0))
    rgb.paste(img.convert("RGB"), (0, 0), alpha)
    w, h, pix = pack(rgb)
    m = array("H", (0xFFFF if v else 0 for v in alpha.tobytes()))
    return (w, h, pix, m.tobytes())


def canvas(size, ss=4):
    return Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))


def down(img, size):
    return img.resize((size, size), Image.LANCZOS)


# ---- maze -----------------------------------------------------------------------------------------------------
def maze_lines(ss=2):
    # Wall tiles are padded with open space so the outer border gets lines on both sides; the tunnel walls are
    # extended into the padding so they run on to the screen edge instead of ending in a rounded cap.
    pad = 2
    t = ss * TILE
    m = Image.new("L", ((COLS + 2 * pad) * t, (ROWS + 2 * pad) * t), 0)
    d = ImageDraw.Draw(m)
    for y, row in enumerate(MAZE):
        for x, ch in enumerate(row):
            if ch in "#X":
                d.rectangle(((x + pad) * t, (y + pad) * t, (x + pad + 1) * t - 1, (y + pad + 1) * t - 1), fill=255)
    # Only the side blocks above and below the tunnel (cols 0-5 and 22-27) run on to the screen edge; filling
    # the whole row would wall off the house interior and the vertical corridors that cross row 14.
    for y in list(range(9, 14)) + list(range(15, 20)):
        d.rectangle((0, (y + pad) * t, (pad + 6) * t - 1, (y + pad + 1) * t - 1), fill=255)
        d.rectangle(((pad + 22) * t, (y + pad) * t, m.width, (y + pad + 1) * t - 1), fill=255)
    # Round the block corners once, then offset the outline inward by alternating square and cross erosions
    # (an octagon approximates a disc): that keeps the double line at a constant distance, with round corners.
    cur = m.filter(ImageFilter.GaussianBlur(12 * ss)).point(lambda v: 255 if v >= 128 else 0)
    inset, lw, gap = 4, 3, 3
    marks = {inset: None, inset + lw: None, inset + lw + gap: None, inset + 2 * lw + gap: None}
    for k in range(1, max(marks) * ss + 1):
        if k % 2:
            cur = cur.filter(ImageFilter.MinFilter(3))
        else:
            cur = ImageChops.darker(
                ImageChops.darker(cur, ImageChops.offset(cur, 1, 0)),
                ImageChops.darker(ImageChops.darker(ImageChops.offset(cur, -1, 0), ImageChops.offset(cur, 0, 1)),
                                  ImageChops.offset(cur, 0, -1)))
        if k % ss == 0 and k // ss in marks:
            marks[k // ss] = cur.filter(ImageFilter.GaussianBlur(ss)).point(lambda v: 255 if v >= 128 else 0)
    s1, s2, s3, s4 = (marks[k] for k in sorted(marks))
    lines = ImageChops.lighter(ImageChops.subtract(s1, s2), ImageChops.subtract(s3, s4))
    box = (pad * t, pad * t, (pad + COLS) * t, (pad + ROWS) * t)
    return lines.crop(box).resize((COLS * TILE, ROWS * TILE), Image.LANCZOS)


def build_maze(lines, line_color):
    img = Image.new("RGB", lines.size, (0, 0, 0))
    img.paste(Image.new("RGB", lines.size, line_color), (0, 0), lines)
    # ghost house door: a pink bar across the two door tiles
    ImageDraw.Draw(img).rectangle((13 * TILE + 2, 12 * TILE + 13, 15 * TILE - 3, 12 * TILE + 18), fill=(255, 184, 255))
    return img


# ---- Pac-Man ----------------------------------------------------------------------------------------------------
def pac_frame(half_angle, direction, size=64, radius=26):
    ss = 4
    im = canvas(size, ss)
    d = ImageDraw.Draw(im)
    c = size * ss // 2
    r = radius * ss
    box = (c - r, c - r, c + r, c + r)
    if half_angle <= 0:
        d.ellipse(box, fill=(255, 255, 0, 255))
    else:
        d.pieslice(box, half_angle, 360 - half_angle, fill=(255, 255, 0, 255))
    rot = {3: 0, 0: 90, 1: 180, 2: 270}[direction]
    return down(im.rotate(rot, resample=Image.BICUBIC), size)


def pac_death(k, n=11, size=64):
    ss = 4
    im = canvas(size, ss)
    d = ImageDraw.Draw(im)
    c = size * ss // 2
    r = 26 * ss
    box = (c - r, c - r, c + r, c + r)
    if k < n:
        a = 8 + (180 - 8) * k / (n - 1)
        a = min(a, 179)
        d.pieslice(box, (270 + a) % 360, (270 - a) % 360, fill=(255, 255, 0, 255))
    else:
        for i in range(8):
            ang = i * math.pi / 4
            px, py = c + math.cos(ang) * 22 * ss, c + math.sin(ang) * 22 * ss
            d.ellipse((px - 3 * ss, py - 3 * ss, px + 3 * ss, py + 3 * ss), fill=(255, 255, 0, 255))
    return down(im, size)


# ---- ghosts ---------------------------------------------------------------------------------------------------------
def draw_ghost_body(d, ss, feet, color):
    # Dome + straight sides + zig-zag skirt; the two animation frames swap which zigs are down.
    x0, x1, top, bot = 4, 60, 4, 60
    r = (x1 - x0) / 2
    d.pieslice((x0 * ss, top * ss, x1 * ss, (top + 2 * r) * ss), 180, 360, fill=color)
    n = 7
    skirt = []
    for i in range(n):
        low = (i % 2 == 0) == (feet == 0)
        skirt.append((x0 + (x1 - x0) * i / (n - 1), bot if low else bot - 7))
    d.polygon([(x * ss, y * ss) for x, y in [(x0, top + r)] + skirt + [(x1, top + r)]], fill=color)


def draw_eyes(d, ss, direction, cx=32, cy=26):
    dx, dy = DIRS[direction]
    for sx in (-1, 1):
        ex, ey = cx + sx * 11 + dx * 2, cy + dy * 2
        d.ellipse(((ex - 7) * ss, (ey - 9) * ss, (ex + 7) * ss, (ey + 9) * ss), fill=(255, 255, 255, 255))
        px, py = ex + dx * 4.5, ey + dy * 6
        d.ellipse(((px - 4) * ss, (py - 4.5) * ss, (px + 4) * ss, (py + 4.5) * ss), fill=(33, 33, 255, 255))


def ghost(color_i, feet, direction):
    ss = 4
    im = canvas(64, ss)
    d = ImageDraw.Draw(im)
    draw_ghost_body(d, ss, feet, GHOST_COLORS[color_i] + (255,))
    draw_eyes(d, ss, direction)
    return sprite(down(im, 64))


def frightened(flash, feet):
    ss = 4
    im = canvas(64, ss)
    d = ImageDraw.Draw(im)
    body = (255, 255, 255, 255) if flash else BLUE + (255,)
    face = (255, 0, 0, 255) if flash else PEACH + (255,)
    draw_ghost_body(d, ss, feet, (222, 222, 255, 255) if flash else body)
    for ex in (24, 40):
        d.rectangle(((ex - 3) * ss, 22 * ss, (ex + 3) * ss, 28 * ss), fill=face)
    zig = [(10 + i * 44 / 8, (44 if i % 2 == 0 else 39)) for i in range(9)]
    d.line([(x * ss, y * ss) for x, y in zig], fill=face, width=3 * ss, joint="curve")
    return sprite(down(im, 64))


def eyes_only(direction):
    ss = 4
    im = canvas(64, ss)
    draw_eyes(ImageDraw.Draw(im), ss, direction, cy=32)
    return sprite(down(im, 64))


# ---- fruit ------------------------------------------------------------------------------------------------------------
def fruit(kind, size=64):
    ss = 4
    im = canvas(size, ss)
    d = ImageDraw.Draw(im)

    def e(cx, cy, rx, ry, col):
        d.ellipse(((cx - rx) * ss, (cy - ry) * ss, (cx + rx) * ss, (cy + ry) * ss), fill=col)

    def ln(pts, col, w):
        d.line([(x * ss, y * ss) for x, y in pts], fill=col, width=int(w * ss), joint="curve")

    RED, GREEN, STEM = (255, 0, 0, 255), (0, 200, 40, 255), (150, 90, 30, 255)
    if kind == 0:  # cherry
        ln([(22, 40), (34, 14), (46, 38)], STEM, 2.5)
        ln([(34, 14), (44, 12)], GREEN, 3)
        for cx, cy in ((22, 44), (45, 42)):
            e(cx, cy, 10, 10, RED)
            e(cx - 3, cy - 3, 3, 3, (255, 200, 200, 255))
    elif kind == 1:  # strawberry
        d.polygon([(x * ss, y * ss) for x, y in [(12, 22), (32, 16), (52, 22), (46, 40), (32, 56), (18, 40)]], fill=RED)
        e(20, 28, 9, 9, RED)
        e(44, 28, 9, 9, RED)
        d.polygon([(x * ss, y * ss) for x, y in [(20, 20), (32, 8), (44, 20), (32, 24)]], fill=GREEN)
        for sx, sy in ((24, 32), (36, 30), (30, 42), (42, 38), (22, 24)):
            e(sx, sy, 1.8, 2.4, (255, 255, 150, 255))
    elif kind == 2:  # orange
        e(32, 36, 22, 21, (255, 150, 30, 255))
        e(25, 28, 5, 4, (255, 200, 110, 255))
        d.polygon([(x * ss, y * ss) for x, y in [(32, 16), (40, 6), (48, 14), (38, 20)]], fill=GREEN)
    elif kind == 3:  # apple
        e(24, 36, 17, 19, RED)
        e(41, 36, 17, 19, RED)
        e(32, 40, 18, 17, RED)
        e(22, 28, 4, 5, (255, 170, 170, 255))
        ln([(32, 20), (32, 10)], STEM, 3)
        d.polygon([(x * ss, y * ss) for x, y in [(34, 12), (46, 6), (44, 16)]], fill=GREEN)
    elif kind == 4:  # melon
        e(32, 36, 22, 21, (90, 200, 70, 255))
        for i in range(-3, 4):
            ln([(32 + i * 6, 17), (32 + i * 7.5, 55)], (190, 255, 170, 255), 1.4)
        for j in range(-1, 3):
            ln([(12, 36 + j * 8), (52, 36 + j * 8)], (190, 255, 170, 255), 1.4)
        d.rectangle((30 * ss, 8 * ss, 34 * ss, 16 * ss), fill=STEM)
    elif kind == 5:  # galaxian flagship
        Y, B, R = (255, 235, 0, 255), (60, 90, 255, 255), (255, 0, 0, 255)
        d.polygon([(x * ss, y * ss) for x, y in [(8, 12), (22, 24), (32, 8), (42, 24), (56, 12), (50, 32), (14, 32)]], fill=B)
        d.polygon([(x * ss, y * ss) for x, y in [(24, 26), (32, 14), (40, 26), (32, 54)]], fill=Y)
        d.rectangle((30 * ss, 24 * ss, 34 * ss, 56 * ss), fill=R)
        e(32, 20, 4, 4, R)
    elif kind == 6:  # bell
        Y = (255, 220, 0, 255)
        d.pieslice((14 * ss, 8 * ss, 50 * ss, 44 * ss), 180, 360, fill=Y)
        d.polygon([(x * ss, y * ss) for x, y in [(14, 26), (50, 26), (56, 46), (8, 46)]], fill=Y)
        e(32, 52, 6, 5, (255, 255, 255, 255))
        e(24, 20, 3, 6, (255, 255, 200, 255))
        d.rectangle((8 * ss, 44 * ss, 56 * ss, 48 * ss), fill=(40, 200, 255, 255))
    else:  # key
        G = (255, 215, 60, 255)
        d.ellipse((16 * ss, 4 * ss, 48 * ss, 30 * ss), outline=G, width=5 * ss)
        d.rectangle((29 * ss, 28 * ss, 35 * ss, 58 * ss), fill=G)
        d.rectangle((35 * ss, 44 * ss, 46 * ss, 49 * ss), fill=G)
        d.rectangle((35 * ss, 53 * ss, 44 * ss, 58 * ss), fill=G)
    return down(im, size)


def small(img, size):
    return sprite(img.resize((size, size), Image.LANCZOS))


# ---- text ---------------------------------------------------------------------------------------------------------------
def text_sprite(s, size, color):
    f = ImageFont.truetype(BOLD, size * 3)
    w = int(f.getlength(s) / 3) + 6
    im = Image.new("RGBA", (w * 3, (size + 8) * 3), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((3 * 3, 2 * 3), s, font=f, fill=color + (255,))
    return sprite(im.resize((w, size + 8), Image.LANCZOS))


def dot_sprites():
    dot = Image.new("RGBA", (8, 8), PEACH + (255,))
    ss = 4
    en = canvas(24, ss)
    ImageDraw.Draw(en).ellipse((0, 0, 24 * ss - 1, 24 * ss - 1), fill=PEACH + (255,))
    return sprite(dot), sprite(down(en, 24))


def main():
    out = {}
    out["maze"] = MAZE
    lines = maze_lines()
    out["maze_blue"] = pack(build_maze(lines, WALL_BLUE))
    out["maze_white"] = pack(build_maze(lines, (235, 235, 255)))
    # frames: 0 wide open, 1 half open, 2 closed
    out["pac"] = [sprite(pac_frame(a, dr)) for dr in range(4) for a in (46, 22, 0)]
    out["pac_death"] = [sprite(pac_death(k)) for k in range(12)]
    out["ghost"] = [ghost(c, f, dr) for c in range(4) for f in range(2) for dr in range(4)]
    out["fright"] = [frightened(fl, f) for fl in (0, 1) for f in range(2)]
    out["eyes"] = [eyes_only(dr) for dr in range(4)]
    fr = [fruit(k) for k in range(8)]
    out["fruit"] = [sprite(f) for f in fr]
    out["fruit_small"] = [small(f, 48) for f in fr]
    out["life"] = sprite(pac_frame(40, 1).resize((44, 44), Image.LANCZOS))
    labels = [("100", (255, 184, 255)), ("200", (0, 255, 255)), ("300", (255, 184, 255)), ("400", (0, 255, 255)),
              ("500", (255, 184, 255)), ("700", (255, 184, 255)), ("800", (0, 255, 255)),
              ("1000", (255, 184, 255)), ("1600", (0, 255, 255)), ("2000", (255, 184, 255)),
              ("3000", (255, 184, 255)), ("5000", (255, 184, 255))]
    out["popup_keys"] = [k for k, _ in labels]
    out["popup"] = [text_sprite(k, 26, c) for k, c in labels]
    out["ready"] = text_sprite("READY!", 34, (255, 255, 0))
    out["gameover"] = text_sprite("GAME  OVER", 34, (255, 0, 0))
    out["dot"], out["energizer"] = dot_sprites()
    save_bundle("g_pacman.bin", out)


if __name__ == "__main__":
    main()
