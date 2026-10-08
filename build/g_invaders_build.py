# Build-time art for the Space Invaders module: every sprite is drawn here from ASCII bitmaps and
# scaled by K screen pixels per game pixel. Output: g_invaders.bin.
import random
from PIL import Image, ImageDraw
from buildlib import pack, save_bundle

K = 4
# Colour slots 0-3 are the per-wave tints of the middle band, 4 is the red top strip of the cellophane
# overlay and 5 the green bottom strip.
COLORS = [(255, 255, 255), (120, 255, 255), (255, 255, 120), (230, 170, 255), (255, 48, 48), (70, 255, 70)]

SQUID = [
    ["...XX...", "..XXXX..", ".XXXXXX.", "XX.XX.XX", "XXXXXXXX", "..X..X..", ".X.XX.X.", "X.X..X.X"],
    ["...XX...", "..XXXX..", ".XXXXXX.", "XX.XX.XX", "XXXXXXXX", ".X.XX.X.", "X......X", ".X....X."],
]
CRAB = [
    ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX", "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."],
    ["..X.....X..", "X..X...X..X", "X.XXXXXXX.X", "XXX.XXX.XXX", "XXXXXXXXXXX", ".XXXXXXXXX.", "..X.....X..", ".X.......X."],
]
OCTOPUS = [
    ["....XXXX....", ".XXXXXXXXXX.", "XXXXXXXXXXXX", "XXX..XX..XXX", "XXXXXXXXXXXX", "...XX..XX...", "..XX.XX.XX..", "XX........XX"],
    ["....XXXX....", ".XXXXXXXXXX.", "XXXXXXXXXXXX", "XXX..XX..XXX", "XXXXXXXXXXXX", "..XXX..XXX..", ".XX..XX..XX.", "..XX....XX.."],
]
ALIEN_EXPLOSION = ["..X...X...X..", "...X..X..X...", "....X...X....", "XX.........XX",
                   "....X...X....", "...X..X..X...", "..X...X...X..", "............."]
UFO = [".....XXXXXX.....", "...XXXXXXXXXX...", "..XXXXXXXXXXXX..", ".XX.XX.XX.XX.XX.",
       "XXXXXXXXXXXXXXXX", "..XXX..XX..XXX..", "...X........X..."]
UFO_EXPLOSION = ["..X..X..XX..X..X", ".X...X.XXXX.X...", "..X.XXXXXXXXX.X.", "XX.XXXXXXXXXX.XX",
                 ".X.XXXXXXXXXXX..", "..X.XXXXXXXX.X..", ".X..X.XXXX.X..X.", "X..X..X..X..X..."]
PLAYER = ["......X......", ".....XXX.....", ".....XXX.....", ".XXXXXXXXXXX.",
          "XXXXXXXXXXXXX", "XXXXXXXXXXXXX", "XXXXXXXXXXXXX", "XXXXXXXXXXXXX"]
SHOT_BURST = ["X..X..X.", ".X.X.X..", "..XXX...", "XXX.XXX.", "..XXX...", ".X.X.X..", "X..X..X.", "........"]
SPLAT = ["..X..X..", "X..XX..X", ".X.XX.X.", "..XXXX.."]
SHIELD = ["....XXXXXXXXXXXXXX....", "..XXXXXXXXXXXXXXXXXX..", ".XXXXXXXXXXXXXXXXXXXX."] + \
         ["XXXXXXXXXXXXXXXXXXXXXX"] * 9 + \
         ["XXXXXXXX......XXXXXXXX", "XXXXXXX........XXXXXXX", "XXXXXX..........XXXXXX", "XXXXXX..........XXXXXX"]


def bombs():
    # Rolling: wide corkscrew; plunger: stem with a moving crossbar; squiggly: thin zigzag.
    # Each has four animation frames.
    rolling = [["XX.", ".XX"][(r + f) % 2] for f in range(4) for r in range(7)]
    rolling = [rolling[f * 7:(f + 1) * 7] for f in range(4)]
    plunger = []
    for f in range(4):
        rows = [".X."] * 7
        rows[(1, 3, 5, 3)[f]] = "XXX"
        plunger.append(rows)
    pat = [".X.", "X..", ".X.", "..X"]
    squiggly = [[pat[(r + f) % 4] for r in range(7)] for f in range(4)]
    return [rolling, plunger, squiggly]


def render(rows, w, h, ox, oy, color):
    img = Image.new("RGB", (w * K, h * K), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c == "X":
                d.rectangle([(ox + x) * K, (oy + y) * K, (ox + x + 1) * K - 1, (oy + y + 1) * K - 1], fill=color)
    return pack(img)


def all_colors(rows, w, h, ox=0, oy=0):
    return [render(rows, w, h, ox, oy, c) for c in COLORS]


def player_explosion(seed):
    rnd = random.Random(seed)
    rows = []
    for y in range(8):
        r = ""
        for x in range(15):
            reach = 7 - abs(x - 7) * 0.6 - (7 - y) * 0.2
            r += "X" if rnd.random() < max(0.0, min(1.0, reach / 5.5)) else "."
        rows.append(r)
    return rows


bundle = {
    "alien": [[all_colors(f, 16, 8, (16 - len(f[0])) // 2) for f in t] for t in (SQUID, CRAB, OCTOPUS)],
    "alien_explosion": all_colors(ALIEN_EXPLOSION, 16, 8, 1),
    "ufo": all_colors(UFO, 24, 8, 4, 1),
    "ufo_explosion": all_colors(UFO_EXPLOSION, 24, 8, 4),
    "player": render(PLAYER, 21, 8, 4, 0, COLORS[5]),
    "player_explosion": [render(player_explosion(s), 21, 8, 3, 0, COLORS[5]) for s in (1, 2)],
    "shot_burst": all_colors(SHOT_BURST, 8, 8),
    "splat": render(SPLAT, 8, 4, 0, 0, COLORS[5]),
    "bomb": [[all_colors(f, 3, 7) for f in kind] for kind in bombs()],
    "shield_mask": SHIELD,
}
save_bundle("g_invaders.bin", bundle)
print("ok")
