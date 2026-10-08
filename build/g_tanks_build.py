# Build step for the Tanks (Battle City) game: draws every sprite, tile and font glyph procedurally at NES
# resolution and writes g_tanks.bin. Sprites are stored as horizontally pre-expanded opaque runs so the game
# can paste them into a strip with plain slice assignments.
import math
import random
from PIL import Image, ImageDraw
from buildlib import pack, save_bundle, rgb565

# Stage layouts 1-10 as in the original: 13x13 blocks of 16x16 pixels, one hex digit per block
# (0-3 half brick, 4 brick, 5-8 half steel, 9 steel, A water, B forest, C ice, D empty).
STAGE_MAPS = [
    'DDDDDDDDDDDDDD4D4D4D4D4D4DD4D4D4D4D4D4DD4D4D494D4D4DD4D4D3D3D4D4DD3D3D1D1D3D3D1D11D3D3D11D18D33D1D1D33D8D1D1D444D1D1DD4D4D4D4D4D4DD4D4D3D3D4D4DD4D4DDDDD4D4DDDDDDDDDDDDDD',
    'DDDD4DDD4DDDDDBBB4DDDDD6664BBBDDDDDDDDDBBBBDDD4D4442BBBB4443D4D0DBBBBDD4DDDD0DDBDDDD999DDBDD1D1DDDDDBBBB420420333BBBBDDDDD4D11BBBB4DD7DDD33BBBD44D7DDDDDBBBD944DDDDDD4DDD',
    'DDD9DDD9DDDDDD4D9DDD4D4D4DD4DDDD44D494DDDD4DDDDD9DDDBDD4DD9DD4B49BBDDD4DD9DBDDD444BBB9DDB4DDDD9B4D4D4D4D94D9D4D4DDD4DD4D4D444D494DD4D4D444DDDDDD4DDDDDDD4D4DD4D4DDDDD444D',
    'DBBDDDDDDDDBDBBDD14411DDDBBDD04444441D88DD444444442DDD03DDD344D2DAD0D7D7D42DDDDD4D11DD42DAADD44444444DDDD0444444442DDD3344444433DDD4413443144DBBD33DDDD33DBB9BDDDDDDDDBB9',
    'DDDD444DDDDDD6D1D4DDD889DD9D4DDD4DDDDDD4D444D44DAAAD3DDD3DDDDADDDDD1DAADAAAD4444DDA4D42DDDDDDDDADDDDD57DAAADAD9D4D5DDDDD11DDDDD544DDDD433341DDD443DDDDDD34DD3DDDDDDDDDDDD',
    'DDDDDDD88DDDDDD9888DDDD9DDDD9DDDBD899DDD9DDDB9DDD9DDDDDDB99DDD89DD9DB999D9DDDDD5D99DDD99DDD7DDD9D999DD5DD59DDD99BDD9DD9DDDD9BDD99DD889DDBDD9DDDDDDDDDDDD8D6966DDDDDDDDDDD',
    'DDDDDDDDDDDDDD034DDDDDD43203DD4DBBD4DD04DDD4BBBB4DD04DD04B99B42D40114AAAAAA444D444994994442DD449D4D9442DDD4444444442D4B333993333B44BBBBBBBBBBB4DDBBB111BBBBDDDD2D4D4DD2DD',
    'DDDDD0D2BBDDDD25D2DDD0B20BD25D2D4D0B20BD4DD4D9D4BD4BDDD08D4D37DBB442DDB4BDD044DDDD0BBB2DDDD944D3BBB30449888D1DBD1D888D4DD4DDD4DDDDD42DD3D3DD04BDD3DDDDDDDBBBDD1DDDDDDD1BB',
    'DDDDDD4444DDDD4441D1DD4DDDDDDD4D3DDDD44DAAAAAD42DD48DD666AD4D974D4D444AAADA44DDDDD9ADDDA8DDAAADAA44DADDDDDDDD488DAAAD444DDDDDDDDDDDD4D88DDD44D04DDDDDDDD4DD4DDDDDDDDDDDDD',
    'DDDDD9D4D44DDD04444D4DDDDDDDD2D4D44DBBBD0DDDDD9DBBBBD0D444944BB39D3339DD4DBBD00444D9BBBBBDDDDD9DDBBBBB4D94DBBBB9BBB4D04BBBBBDDDD42D4BBDDDD8444DDDBBDDDDD4D0DD1BBDDDDDDDDD',
]
# Spawn order of the 20 tanks per stage (the original's table): 0 basic, 1 fast, 2 power, 3 armor.
ENEMY_SEQ = [
    '00000000000000000011',
    '33111100000000000000',
    '00000000000000111133',
    '22222222221111100333',
    '22222330000000011111',
    '22222221100000000033',
    '00011112222220000000',
    '22222223311110000000',
    '00000011112222222333',
    '00000000000011222233',
    '11111333333222211111',
    '22222222111111333333',
    '22222222111111113333',
    '22222222221111333333',
    '00111111111133333333',
    '00000000000000001133',
    '33112222222200000000',
    '33330022222211111111',
    '11113333333300002222',
    '11111111002233333333',
    '22222222110000003333',
    '11111111000000223333',
    '33333322221111111111',
    '22223311110000000000',
    '22111111113333333333',
    '11111133333300002222',
    '22333333331111111100',
    '11300000000000000022',
    '22222222221111333333',
    '00001111111122223333',
    '22211111111333333222',
    '33333333000000221111',
    '11113333333322221111',
    '22221111111111333333',
    '22221111113333333333',
]

# ---- palette (approximation of the NES colours Battle City uses) -------------------------------
SC = 5                       # one NES pixel = 5x5 screen pixels
BLACK = (0, 0, 0)
GREY = (124, 124, 124)       # surround
WHITE = (252, 252, 252)

PAL_PLAYER = dict(hull=(228, 188, 40), hl=(252, 232, 120), sh=(168, 108, 0), trl=(196, 148, 16), trd=(88, 52, 0),
                  out=(60, 30, 0), gun=(252, 232, 120))
PAL_BASIC = dict(hull=(188, 188, 188), hl=(236, 236, 236), sh=(116, 116, 116), trl=(160, 160, 160), trd=(60, 60, 60),
                 out=(20, 20, 20), gun=(236, 236, 236))
PAL_FAST = dict(hull=(172, 196, 232), hl=(220, 236, 252), sh=(88, 104, 148), trl=(148, 172, 208), trd=(48, 56, 88),
                out=(16, 20, 40), gun=(220, 236, 252))
PAL_POWER = dict(hull=(204, 176, 188), hl=(248, 224, 232), sh=(124, 84, 100), trl=(176, 148, 160), trd=(72, 44, 56),
                 out=(32, 12, 20), gun=(248, 224, 232))
PAL_ARMOR = [  # hit points 4..1: green fades to grey as the tank takes damage
    dict(hull=(0, 168, 0), hl=(88, 232, 88), sh=(0, 88, 0), trl=(0, 136, 0), trd=(0, 56, 0), out=(0, 28, 0),
         gun=(88, 232, 88)),
    dict(hull=(152, 176, 20), hl=(216, 236, 96), sh=(84, 96, 0), trl=(124, 148, 16), trd=(52, 60, 0),
         out=(28, 32, 0), gun=(216, 236, 96)),
    dict(hull=(168, 184, 140), hl=(224, 236, 200), sh=(100, 112, 84), trl=(140, 156, 116), trd=(56, 64, 44),
         out=(24, 28, 20), gun=(224, 236, 200)),
    dict(hull=(204, 204, 204), hl=(252, 252, 252), sh=(124, 124, 124), trl=(172, 172, 172), trd=(64, 64, 64),
         out=(20, 20, 20), gun=(252, 252, 252)),
]
PAL_RED = dict(hull=(216, 40, 0), hl=(252, 136, 104), sh=(120, 12, 0), trl=(180, 28, 0), trd=(72, 8, 0),
               out=(40, 0, 0), gun=(252, 136, 104))


def new(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def put(im, x, y, c):
    if 0 <= x < im.width and 0 <= y < im.height:
        im.putpixel((x, y), tuple(c) + (255,) if len(c) == 3 else tuple(c))


def rect(im, x0, y0, x1, y1, c):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            put(im, x, y, c)


def expand(c):
    return rgb565(*c).to_bytes(2, "little") * SC


def runs_of(im):
    # Transparent pixels split a row into runs; each run is already horizontally expanded (10 bytes per pixel)
    # so the game can paste it into a strip with one slice assignment.
    rows = []
    for y in range(im.height):
        row, x = [], 0
        while x < im.width:
            if im.getpixel((x, y))[3] == 0:
                x += 1
                continue
            x0, data = x, bytearray()
            while x < im.width and im.getpixel((x, y))[3]:
                data += expand(im.getpixel((x, y))[:3])
                x += 1
            row.append((x0, bytes(data)))
        rows.append(row)
    return (im.width, im.height, rows)


def opaque_rows(im, bg=BLACK):
    # Fully expanded rows of an opaque tile (transparent pixels become bg); used for the background buffer.
    out = []
    for y in range(im.height):
        data = bytearray()
        for x in range(im.width):
            p = im.getpixel((x, y))
            data += expand(p[:3] if p[3] else bg)
        out.append(bytes(data))
    return out


def screen_sprite(im, bg):
    # Sprite for blit(): scaled SC times, transparent pixels filled with bg.
    flat = Image.new("RGB", im.size, bg)
    flat.paste(im.convert("RGB"), mask=im.split()[3])
    return pack(flat.resize((im.width * SC, im.height * SC), Image.NEAREST))


# ---- tanks -------------------------------------------------------------------------------------
def draw_tank_up(kind, pal, frame, level=0):
    im = new(16, 16)
    out, hull, hl, sh = pal["out"], pal["hull"], pal["hl"], pal["sh"]
    tw = 2 if kind == "fast" else 3
    for side in (0, 16 - tw):
        for y in range(2, 16):
            c = pal["trl"] if (y + frame) % 2 == 0 else pal["trd"]
            rect(im, side, y, side + tw - 1, y, c)
        edge = side if side == 0 else side + tw - 1
        rect(im, edge, 2, edge, 15, out)
    hx0, hx1 = tw, 15 - tw
    # hull: flat colour, dark rim on the right/bottom, lit rim on the left/top
    rect(im, hx0, 5, hx1, 14, hull)
    rect(im, hx0, 5, hx1, 5, hl)
    rect(im, hx0, 5, hx0, 14, hl)
    rect(im, hx1, 6, hx1, 14, sh)
    rect(im, hx0, 14, hx1, 14, sh)
    rect(im, hx0 + 1, 12, hx1 - 1, 12, sh)        # engine grille
    rect(im, hx0 + 1, 10 if kind == "armor" else 13, hx1 - 1, 10 if kind == "armor" else 13, sh)
    if kind == "fast":
        for dx in (0, 1):
            put(im, hx0 + dx, 5, (0, 0, 0, 0))
            put(im, hx1 - dx, 5, (0, 0, 0, 0))
        put(im, hx0, 6, (0, 0, 0, 0))
        put(im, hx1, 6, (0, 0, 0, 0))
    if kind == "armor":
        rect(im, hx0, 5, hx0, 14, hl)
        rect(im, hx0 + 1, 6, hx0 + 1, 13, out)
        rect(im, hx1 - 1, 6, hx1 - 1, 13, out)
    # turret: octagon with a dark rim so the lighter gun reads clearly against it
    for y in range(6, 12):
        for x in range(5, 11):
            if (x in (5, 10)) and (y in (6, 11)):
                continue
            rim = x in (5, 10) or y in (6, 11)
            put(im, x, y, out if rim else (hl if x + y < 14 else hull))
    rect(im, 7, 8, 8, 9, sh)
    # gun
    g, gs = pal["gun"], sh
    top = 1 if kind == "fast" else 0
    if kind == "power" or (kind == "player" and level == 3):
        rect(im, 6, top, 9, 7, g)
        rect(im, 9, top + 1, 9, 7, gs)
        rect(im, 6, top, 9, top, out)
        rect(im, 7, top + 1, 8, top + 1, out)
    elif kind == "player" and level == 2:
        rect(im, 5, top, 6, 7, g)
        rect(im, 9, top, 10, 7, g)
        rect(im, 6, top + 1, 6, 7, gs)
        rect(im, 10, top + 1, 10, 7, gs)
        rect(im, 5, top, 6, top, out)
        rect(im, 9, top, 10, top, out)
        rect(im, 5, 7, 10, 7, gs)
    else:
        rect(im, 7, top, 8, 7, g)
        rect(im, 8, top + 1, 8, 7, gs)
        rect(im, 7, top, 8, top, out)
    if kind == "armor" or (kind == "player" and level >= 1):
        rect(im, 6, 5, 9, 6, g)
        rect(im, 9, 6, 9, 6, gs)
        rect(im, 6, 5, 9, 5, hl)
    if kind == "player" and level == 3:
        rect(im, hx0 + 1, 6, hx0 + 1, 13, out)
        rect(im, hx1 - 1, 6, hx1 - 1, 13, out)
    return im


def rotated(im, d):
    # d: 0 up, 1 right, 2 down, 3 left
    return [im, im.rotate(-90), im.rotate(180), im.rotate(90)][d]


def tank_set(kind, pal, level=0):
    return [[runs_of(rotated(draw_tank_up(kind, pal, f, level), d)) for f in (0, 1)] for d in range(4)]


# ---- terrain tiles (8x8) -----------------------------------------------------------------------
BR_FACE, BR_HI, BR_LO, BR_GROUT = (200, 72, 20), (240, 128, 60), (140, 36, 8), (24, 8, 4)


def brick_tile(mask):
    # mask bits: 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right quarter (4x4 pixels each)
    im = new(8, 8)
    for y in range(8):
        for x in range(8):
            q = (1 if x < 4 else 2) if y < 4 else (4 if x < 4 else 8)
            if not mask & q:
                continue
            joint = 0 if y < 4 else 4
            if y % 4 == 3 or x % 8 == joint:
                c = BR_GROUT
            elif y % 4 == 0:
                c = BR_HI
            elif y % 4 == 2:
                c = BR_LO
            else:
                c = BR_FACE
            put(im, x, y, c)
    return im


def steel_tile():
    im = new(8, 8)
    rect(im, 0, 0, 7, 7, (188, 188, 188))
    rect(im, 0, 0, 7, 0, WHITE)
    rect(im, 0, 0, 0, 7, WHITE)
    rect(im, 7, 1, 7, 7, (96, 96, 96))
    rect(im, 1, 7, 7, 7, (96, 96, 96))
    rect(im, 2, 2, 5, 5, (232, 232, 232))
    rect(im, 5, 3, 5, 5, (130, 130, 130))
    rect(im, 3, 5, 5, 5, (130, 130, 130))
    return im


def water_tile(frame):
    im = new(8, 8)
    rect(im, 0, 0, 7, 7, (24, 100, 248))
    for y in (1, 5):
        for x in range(8):
            wave = ((x + frame * 3 + (0 if y == 1 else 4)) % 8)
            if wave < 3:
                put(im, x, y, (140, 208, 252))
            elif wave < 5:
                put(im, x, y, (60, 150, 252))
    return im


def ice_tile():
    im = new(8, 8)
    rect(im, 0, 0, 7, 7, (172, 220, 248))
    for i in range(8):
        put(im, i, 7 - i, (252, 252, 252))
        put(im, (i + 4) % 8, 7 - i, (212, 240, 252))
    put(im, 1, 1, WHITE)
    put(im, 5, 2, WHITE)
    put(im, 2, 5, WHITE)
    return im


def forest_tile():
    im = new(8, 8)
    pat = ["GgGG.gGg", "gGGgGG.G", "GG.GgGGg", "gGgGGgG.", "GGgG.GGg", ".gGGgGgG", "GGgGGG.G", "gG.gGgGG"]
    cols = {"G": (0, 148, 0), "g": (0, 72, 0), ".": None}
    for y, row in enumerate(pat):
        for x, ch in enumerate(row):
            c = cols[ch]
            if c:
                put(im, x, y, c)
                if (x * 3 + y * 5) % 7 == 0:
                    put(im, x, y, (112, 224, 96))
    return im


# ---- eagle, bullets, effects, power-ups ----------------------------------------------------------
def eagle(alive):
    im = new(16, 16)
    if alive:
        wing, hi, dk = (176, 176, 176), WHITE, (96, 96, 96)
        # wings
        for i in range(7):
            rect(im, i, 5 + i // 2, i, 11 - i // 3, wing)
            rect(im, 15 - i, 5 + i // 2, 15 - i, 11 - i // 3, wing)
        for i in range(0, 7, 2):
            rect(im, i, 5 + i // 2, i, 5 + i // 2, hi)
            rect(im, 15 - i, 5 + i // 2, 15 - i, 5 + i // 2, hi)
        # body, head, beak, tail
        rect(im, 6, 4, 9, 14, wing)
        rect(im, 7, 5, 8, 13, hi)
        rect(im, 6, 1, 9, 4, wing)
        rect(im, 7, 2, 8, 3, hi)
        put(im, 7, 3, BLACK)
        rect(im, 7, 0, 8, 0, (228, 160, 20))
        rect(im, 5, 14, 10, 15, dk)
        rect(im, 6, 12, 9, 12, dk)
        put(im, 6, 4, dk)
        put(im, 9, 4, dk)
    else:
        ash, dk = (96, 96, 96), (52, 52, 52)
        rect(im, 1, 11, 14, 15, dk)
        rect(im, 3, 9, 12, 12, ash)
        rect(im, 6, 6, 9, 10, dk)
        rect(im, 7, 4, 8, 6, ash)
        put(im, 7, 5, BLACK)
        put(im, 8, 5, BLACK)
        for x, y in ((2, 13), (5, 14), (11, 14), (13, 12), (4, 10)):
            put(im, x, y, (150, 150, 150))
        # a tattered flag on a pole
        rect(im, 12, 2, 12, 11, (170, 170, 170))
        rect(im, 13, 2, 15, 4, (204, 204, 204))
        put(im, 15, 4, BLACK)
        put(im, 14, 5, (204, 204, 204))
    return im


def bullet(d):
    im = new(3, 4)
    pat = [".W.", "WGW", ".G.", ".G."]
    col = {"W": (252, 252, 252), "G": (188, 188, 188)}
    for y, row in enumerate(pat):
        for x, ch in enumerate(row):
            if ch in col:
                put(im, x, y, col[ch])
    return rotated_any(im, d)


def rotated_any(im, d):
    return [im, im.rotate(-90, expand=True), im.rotate(180), im.rotate(90, expand=True)][d]


def disc(im, cx, cy, r, c):
    for y in range(im.height):
        for x in range(im.width):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                put(im, x, y, c)


def explosion(size, frame, nframes):
    s = size
    im = new(s, s)
    c = s // 2 - 0.5
    rng = random.Random(size * 31 + frame)
    k = (frame + 1) / nframes
    r = (0.25 + 0.75 * (k if frame < nframes - 1 else 0.85)) * (s / 2 - 0.5)
    cols = [(172, 16, 0), (252, 136, 24), (252, 224, 120), (252, 252, 252)]
    for y in range(s):
        for x in range(s):
            dd = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            jitter = rng.uniform(-0.18, 0.18) * r
            if dd <= r + jitter:
                depth = dd / max(r, 1)
                if frame == nframes - 1:
                    ci = 0 if depth > 0.55 or rng.random() < 0.5 else 1
                    if rng.random() < 0.35:
                        continue
                else:
                    ci = 3 if depth < 0.3 else 2 if depth < 0.55 else 1 if depth < 0.8 else 0
                put(im, x, y, cols[ci])
    return im


def star(frame):
    im = new(16, 16)
    r = (3, 5, 7, 8)[frame]
    w = max(1, r // 4)
    cx = 7.5
    pts = []
    for ang in range(8):
        rr = r if ang % 2 == 0 else w
        dx, dy = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)][ang]
        if ang % 2 == 0:
            pts.append((cx + dx * rr, cx + dy * rr))
        else:
            pts.append((cx + dx * rr * 0.9, cx + dy * rr * 0.9))
    d = ImageDraw.Draw(im)
    d.polygon(pts, fill=(252, 252, 252, 255))
    return im


def shield(frame):
    im = new(16, 16)
    cols = [(252, 252, 252), (148, 148, 148)]
    for a in range(0, 360, 12):
        x = 7.5 + 7.6 * math.cos(math.radians(a))
        y = 7.5 + 7.6 * math.sin(math.radians(a))
        put(im, int(round(x)), int(round(y)), cols[((a // 12) + frame) % 2])
    for a in range(0, 360, 24):
        x = 7.5 + 6.2 * math.cos(math.radians(a + 6 * frame))
        y = 7.5 + 6.2 * math.sin(math.radians(a + 6 * frame))
        put(im, int(round(x)), int(round(y)), (190, 190, 252))
    return im


def powerup_icon(kind):
    im = new(16, 16)
    rect(im, 0, 0, 15, 15, (20, 20, 20))
    rect(im, 1, 1, 14, 14, (220, 36, 12))
    rect(im, 2, 2, 13, 13, (236, 236, 236))
    if kind == 0:  # star
        d = ImageDraw.Draw(im)
        pts = [(7.5, 2.5), (9.3, 6.2), (13, 6.6), (10.2, 9.2), (11, 13), (7.5, 11), (4, 13), (4.8, 9.2), (2, 6.6),
               (5.7, 6.2)]
        d.polygon(pts, fill=(228, 64, 0, 255))
        put(im, 7, 7, (252, 190, 60))
        put(im, 8, 7, (252, 190, 60))
    elif kind == 1:  # grenade
        disc(im, 7, 9, 4, (24, 24, 24))
        put(im, 5, 7, (140, 140, 140))
        put(im, 6, 6, (140, 140, 140))
        rect(im, 7, 3, 9, 4, (24, 24, 24))
        rect(im, 10, 2, 11, 3, (200, 120, 20))
        put(im, 12, 2, (252, 60, 20))
    elif kind == 2:  # helmet
        d = ImageDraw.Draw(im)
        d.pieslice((3, 4, 12, 15), 180, 360, fill=(48, 100, 24, 255))
        rect(im, 3, 9, 12, 10, (48, 100, 24))
        rect(im, 2, 10, 13, 11, (30, 64, 14))
        put(im, 5, 6, (120, 190, 80))
        put(im, 6, 5, (120, 190, 80))
    elif kind == 3:  # shovel
        rect(im, 7, 3, 8, 8, (130, 82, 30))
        rect(im, 5, 2, 10, 3, (100, 60, 20))
        rect(im, 5, 8, 10, 12, (130, 130, 140))
        rect(im, 6, 12, 9, 13, (130, 130, 140))
        rect(im, 5, 8, 5, 12, (70, 70, 80))
    elif kind == 4:  # extra tank
        t = draw_tank_up("player", PAL_PLAYER, 0)
        small = t.resize((10, 10), Image.NEAREST)
        im.paste(small, (3, 3), small)
    else:  # timer
        disc(im, 7, 8, 5, (40, 40, 40))
        disc(im, 7, 8, 4, (250, 250, 250))
        rect(im, 7, 5, 7, 8, (30, 30, 30))
        rect(im, 7, 8, 9, 8, (30, 30, 30))
        rect(im, 6, 2, 8, 2, (40, 40, 40))
    return im


# ---- bitmap font ----------------------------------------------------------------------------------
FONT = {
    "A": [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "B": ["XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X...X", "XXXX."],
    "C": [".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."],
    "D": ["XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."],
    "E": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"],
    "F": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."],
    "G": [".XXX.", "X...X", "X....", "X.XXX", "X...X", "X...X", ".XXX."],
    "H": ["X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "I": [".XXX.", "..X..", "..X..", "..X..", "..X..", "..X..", ".XXX."],
    "J": ["..XXX", "...X.", "...X.", "...X.", "...X.", "X..X.", ".XX.."],
    "K": ["X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"],
    "L": ["X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"],
    "M": ["X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"],
    "N": ["X...X", "XX..X", "X.X.X", "X..XX", "X...X", "X...X", "X...X"],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "P": ["XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."],
    "Q": [".XXX.", "X...X", "X...X", "X...X", "X.X.X", "X..X.", ".XX.X"],
    "R": ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"],
    "S": [".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."],
    "T": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."],
    "U": ["X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "V": ["X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."],
    "W": ["X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"],
    "X": ["X...X", "X...X", ".X.X.", "..X..", ".X.X.", "X...X", "X...X"],
    "Y": ["X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."],
    "Z": ["XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"],
    "0": [".XXX.", "X...X", "X..XX", "X.X.X", "XX..X", "X...X", ".XXX."],
    "1": ["..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", ".XXX."],
    "2": [".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"],
    "3": ["XXXXX", "...X.", "..X..", "...X.", "....X", "X...X", ".XXX."],
    "4": ["...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."],
    "5": ["XXXXX", "X....", "XXXX.", "....X", "....X", "X...X", ".XXX."],
    "6": ["..XX.", ".X...", "X....", "XXXX.", "X...X", "X...X", ".XXX."],
    "7": ["XXXXX", "....X", "...X.", "..X..", ".X...", ".X...", ".X..."],
    "8": [".XXX.", "X...X", "X...X", ".XXX.", "X...X", "X...X", ".XXX."],
    "9": [".XXX.", "X...X", "X...X", ".XXXX", "....X", "...X.", ".XX.."],
    "-": [".....", ".....", ".....", "XXXXX", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".....", "..X.."],
    ":": [".....", "..X..", ".....", ".....", ".....", "..X..", "....."],
    "!": ["..X..", "..X..", "..X..", "..X..", "..X..", ".....", "..X.."],
    "<": ["...X.", "..XX.", ".XXX.", "XXXX.", ".XXX.", "..XX.", "...X."],
    " ": ["....."] * 7,
}
CHARSET = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-.:!<"


def glyph(ch, fg, bold=False):
    im = new(8, 8)
    for y, row in enumerate(FONT[ch]):
        for x, c in enumerate(row):
            if c == "X":
                put(im, x + 1, y, fg)
                if bold:
                    put(im, x + 2, y, fg)
    return im


def text_run_sprite(s, fg, outline=None):
    # With an outline the text stays readable over bricks and forest.
    im = new(8 * len(s) + 2, 10)
    for i, ch in enumerate(s):
        g = glyph(ch, fg)
        if outline:
            dark = glyph(ch, outline)
            for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2), (0, 0), (2, 2), (0, 2), (2, 0)):
                im.paste(dark, (8 * i + dx - 1 + 1, dy - 1 + 1), dark)
        im.paste(g, (8 * i + 1, 1), g)
    return runs_of(im)


# ---- HUD pictures ------------------------------------------------------------------------------------
def hud_enemy_icon():
    im = new(8, 8)
    d, m = (20, 20, 20), (70, 70, 70)
    rect(im, 0, 1, 1, 7, d)           # treads
    rect(im, 5, 1, 6, 7, d)
    rect(im, 2, 3, 4, 7, m)           # hull
    rect(im, 2, 3, 4, 3, d)
    rect(im, 3, 0, 3, 3, d)           # gun
    return im


def hud_life_icon():
    im = new(8, 8)
    t = draw_tank_up("player", PAL_PLAYER, 0).resize((8, 8), Image.NEAREST)
    im.paste(t, (0, 0), t)
    return im


def hud_flag():
    im = new(16, 16)
    rect(im, 2, 1, 3, 15, (24, 24, 24))
    rect(im, 4, 2, 13, 9, (24, 24, 24))
    rect(im, 5, 3, 12, 8, (232, 232, 232))
    rect(im, 5, 6, 12, 8, (200, 60, 24))
    rect(im, 1, 14, 6, 15, (24, 24, 24))
    return im


def main():
    data = {}
    data["player"] = [tank_set("player", PAL_PLAYER, lv) for lv in range(4)]
    en = []
    for kind, pal in (("basic", PAL_BASIC), ("fast", PAL_FAST), ("power", PAL_POWER)):
        en.append([tank_set(kind, pal), tank_set(kind, PAL_RED)])
    en.append([tank_set("armor", p) for p in PAL_ARMOR] + [tank_set("armor", PAL_RED)])
    data["enemy"] = en
    data["bullet"] = [runs_of(bullet(d)) for d in range(4)]
    data["boom_small"] = [runs_of(explosion(16, f, 3)) for f in range(3)]
    data["boom_big"] = [runs_of(explosion(32, f, 3)) for f in range(3)]
    data["star"] = [runs_of(star(f)) for f in range(4)]
    data["shield"] = [runs_of(shield(f)) for f in range(2)]
    data["powerup"] = [runs_of(powerup_icon(k)) for k in range(6)]
    data["eagle"] = [opaque_rows(eagle(False)), opaque_rows(eagle(True))]
    # terrain rows for the background buffer
    data["t_brick"] = [opaque_rows(brick_tile(m)) for m in range(16)]
    data["t_steel"] = opaque_rows(steel_tile())
    data["t_water"] = [opaque_rows(water_tile(f)) for f in range(2)]
    data["t_ice"] = opaque_rows(ice_tile())
    data["t_forest"] = opaque_rows(forest_tile())
    data["forest_runs"] = runs_of(forest_tile())[2]
    data["t_empty"] = opaque_rows(new(8, 8))
    # text: pasteable run sprites for in-field text, blit sprites for HUD text on grey / black
    data["gameover"] = text_run_sprite("GAME OVER", (252, 80, 40), (0, 0, 0))
    data["glyph"] = {}
    for name, fg, bg in (("grey", (16, 16, 16), GREY), ("black", (252, 252, 252), BLACK),
                         ("orange", (228, 120, 24), BLACK), ("red", (216, 40, 24), BLACK),
                         ("yellow", (252, 224, 60), BLACK), ("white_grey", (252, 252, 252), GREY)):
        data["glyph"][name] = [screen_sprite(glyph(ch, fg, name in ("grey", "white_grey")), bg) for ch in CHARSET]
    data["charset"] = CHARSET
    data["hud_enemy"] = screen_sprite(hud_enemy_icon(), GREY)
    data["hud_life"] = screen_sprite(hud_life_icon(), GREY)
    data["hud_flag"] = screen_sprite(hud_flag(), GREY)
    pop = {}
    for val in (100, 200, 300, 400, 500):
        pop[val] = text_run_sprite(str(val), (252, 252, 252), (0, 0, 0))
    data["popup"] = pop
    # tally icons (enemy kinds at 2x of NES pixels) are rendered from the same tank art
    data["tally_tank"] = [screen_sprite(draw_tank_up(k, p, 0), BLACK) for k, p in
                          (("basic", PAL_BASIC), ("fast", PAL_FAST), ("power", PAL_POWER), ("armor", PAL_ARMOR[0]))]
    data["stage_maps"] = STAGE_MAPS
    data["enemy_seq"] = ENEMY_SEQ
    save_bundle("g_tanks.bin", data)
    print("bundle written")


if __name__ == "__main__":
    main()
