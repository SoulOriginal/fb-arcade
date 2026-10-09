# Procedural art for the Grand Prix Circuit clone: every picture is drawn here at 320x200 EGA resolution
# with the 16-colour palette of the DOS version. Nothing is copied from the original game.
import random
from PIL import Image, ImageDraw, ImageFont

BLK, BLU, GRN, CYN, RED, MAG, BRN, LGR, DGR, LBL, LGN, LCY, LRD, LMG, YEL, WHT = range(16)
PAL = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
       (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255), (255, 85, 85), (255, 85, 255), (255, 255, 85),
       (255, 255, 255)]
TR = 16                                    # transparent index in sprite images
MONO = "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf"


def pimage(w, h, fill=0):
    im = Image.new("P", (w, h), fill)
    flat = []
    for c in PAL:
        flat += list(c)
    flat += [255, 0, 255] * (256 - 16)
    im.putpalette(flat)
    return im


def px565(c):
    r, g, b = PAL[c]
    return ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)).to_bytes(2, "little") * 5


P5 = [px565(c) for c in range(16)]


def rows_expanded(im, y0, y1):
    # one bytes row of 320 vpx x 10 bytes for every image row in [y0, y1)
    out = []
    for y in range(y0, y1):
        out.append(b"".join(P5[i] for i in im.crop((0, y, im.width, y + 1)).tobytes()))
    return out


def to_runs(im):
    # opaque horizontal spans per row: [(x0, bytes)]; transparency = index TR
    w, h = im.size
    data = im.tobytes()
    rows = []
    for y in range(h):
        r = data[y * w:(y + 1) * w]
        spans, x = [], 0
        while x < w:
            if r[x] == TR:
                x += 1
                continue
            x0 = x
            while x < w and r[x] != TR:
                x += 1
            spans.append((x0, b"".join(P5[i] for i in r[x0:x])))
        rows.append(spans)
    return (w, h, rows)


def scaled(im, w, h):
    return im.resize((max(1, w), max(1, h)), Image.NEAREST)


# ---- font: 6x9 cells cut from a bold monospace face, no anti-aliasing ----------------------------------
def make_font():
    f = ImageFont.truetype(MONO, 10)
    glyphs = {}
    for code in range(32, 123):
        ch = chr(code)
        im = Image.new("1", (6, 9), 0)
        d = ImageDraw.Draw(im)
        d.fontmode = "1"
        d.text((0, -1), ch, font=f, fill=1)
        px = im.load()
        glyphs[ch] = [sum(1 << (5 - x) for x in range(6) if px[x, y]) for y in range(9)]
    return glyphs


MINI = {"0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
        "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001010010010",
        "8": "111101111101111", "9": "111101111001111"}


def mini_text(d, s, x, y, c):
    for ch in s:
        for i, bit in enumerate(MINI[ch]):
            if bit == "1":
                d.point((x + i % 3, y + i // 3), fill=c)
        x += 4


def glyph_text(d, s, x, y, c, font):
    for ch in s:
        for j, bits in enumerate(font[ch]):
            for i in range(6):
                if bits >> (5 - i) & 1:
                    d.point((x + i, y + j), fill=c)
        x += 6


# ---- viewport static sky ---------------------------------------------------------------------------------
def sky_rows():
    im = pimage(320, 200, 0)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 17, 319, 109), fill=LCY)
    return rows_expanded(im, 17, 61)


def lamp_frames(font):
    # start-light gantry panel 47x43: four lamps in two rows; frame n has n lamps lit
    out = []
    for n in range(5):
        im = pimage(47, 43, BLK)
        d = ImageDraw.Draw(im)
        for i, (cx, cy) in enumerate([(12, 11), (34, 11), (12, 27), (34, 27)]):
            lit = i < n
            if lit:
                d.ellipse((cx - 8, cy - 7, cx + 8, cy + 7), fill=LRD)
                d.ellipse((cx - 5, cy - 5, cx - 2, cy - 3), fill=WHT)
            else:
                d.arc((cx - 8, cy - 7, cx + 8, cy + 7), 190, 350, fill=DGR)
        d.point((1, 41), fill=DGR)
        d.point((45, 41), fill=DGR)
        out.append(rows_expanded(im, 0, 43))
    return out


def mapbox_base():
    im = pimage(42, 23, CYN)
    return rows_expanded(im, 0, 23)


def infobox_base():
    im = pimage(75, 28, LRD)
    d = ImageDraw.Draw(im)
    for y in range(28):
        for x in range(75):
            if x < 3 or x >= 72 or y < 3 or y >= 25:
                im.putpixel((x, y), DGR if (x + y) % 2 else LGR)
    return rows_expanded(im, 0, 28)


# ---- cockpit ---------------------------------------------------------------------------------------------
def ell_pt(cx, cy, rx, ry, deg):
    import math
    a = math.radians(deg)
    return cx + rx * math.cos(a), cy + ry * math.sin(a)


def draw_gauge(d, cx, cy, rx, ry, label, font, ticks):
    d.ellipse((cx - rx - 2, cy - ry - 2, cx + rx + 2, cy + ry + 2), fill=LGR)
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=BLK)
    for k in range(ticks):
        x, y = ell_pt(cx, cy, rx - 3, ry - 3, 150 + k * 240 / (ticks - 1))
        d.point((round(x), round(y)), fill=YEL)
        d.point((round(x) + 1, round(y)), fill=YEL)
    glyph_text(d, label, cx - len(label) * 3, cy + 1, LGR, font)


def dash_frame(k, font):
    import math
    th = k * 15.0
    im = pimage(320, 200, BLK)
    d = ImageDraw.Draw(im)
    # road seen over the nose between the mirrors
    d.rectangle((0, 110, 319, 188), fill=DGR)
    # dark cockpit sides below a pale kerb line
    d.polygon([(0, 150), (58, 128), (58, 189), (0, 189)], fill=BLK)
    d.polygon([(319, 150), (261, 128), (261, 189), (319, 189)], fill=BLK)
    d.line([(0, 148), (58, 126)], fill=WHT, width=2)
    d.line([(319, 148), (261, 126)], fill=WHT, width=2)
    d.line([(0, 140), (60, 118)], fill=LGR, width=2)
    d.line([(319, 140), (259, 118)], fill=LGR, width=2)
    # mirrors
    for mx, flip in ((1, False), (255, True)):
        d.rectangle((mx, 110, mx + 63, 131), fill=RED)
        d.rectangle((mx + 1, 111, mx + 62, 130), fill=LCY)
        d.polygon([(mx + 1, 121), (mx + 12, 115), (mx + 20, 119), (mx + 31, 114), (mx + 40, 119), (mx + 52, 116),
                   (mx + 62, 120), (mx + 62, 124), (mx + 1, 124)], fill=LGR)
        d.rectangle((mx + 1, 122, mx + 62, 125), fill=GRN)
        d.polygon([(mx + 1, 125), (mx + 62, 125), (mx + 62, 130), (mx + 1, 130)], fill=DGR)
        d.polygon([(mx + 24, 125), (mx + 38, 125), (mx + 44, 130), (mx + 18, 130)], fill=LGR)
        d.line([(mx + (1 if not flip else 62), 129), (mx + (13 if not flip else 50), 125)], fill=WHT)
    # side vents
    for vx0 in (67, 237):
        d.rectangle((vx0, 110, vx0 + 19, 124), fill=BLK)
        for i in range(0, 20, 3):
            d.rectangle((vx0 + i, 112 + (i % 2), vx0 + i + 1, 123), fill=RED)
    # dash wing with rim
    wing = [(62, 124), (90, 113), (230, 113), (258, 124), (262, 150), (258, 189), (62, 189), (58, 150)]
    d.polygon(wing, fill=LGR)
    inner = [(65, 125), (92, 116), (228, 116), (255, 125), (259, 150), (255, 189), (65, 189), (61, 150)]
    d.polygon(inner, fill=DGR)
    # LCD speed window, damage bar window, lamp bezels
    d.rectangle((97, 116, 127, 128), fill=BLK, outline=RED)
    d.rectangle((134, 117, 216, 126), fill=BLK, outline=LGR)
    for lx, ly in ((221, 117), (212, 126), (225, 126)):
        d.rectangle((lx, ly, lx + 10, ly + 5), fill=GRN, outline=BLK)
    d.ellipse((69, 134, 79, 144), fill=GRN, outline=LGR)
    d.ellipse((242, 134, 252, 144), fill=RED, outline=LGR)
    # steering wheel: black ring, grips and marker rotate with the wheel angle
    d.ellipse((70, 119, 250, 221), fill=BLK)
    d.ellipse((82, 128, 238, 214), fill=DGR)
    for i in range(-6, 7):
        x, y = ell_pt(160, 170, 85, 48, -90 + i * 12 + th)
        if y < 189:
            d.point((round(x), round(y)), fill=DGR)
            d.point((round(x), round(y) + 1), fill=DGR)
    for sgn in (-1, 1):
        x, y = ell_pt(160, 170, 85, 48, -90 + sgn * 62 + th)
        if y < 186:
            d.rectangle((round(x) - 2, round(y) - 3, round(x) + 2, round(y) + 3), fill=LGR)
    mx_, my_ = ell_pt(160, 170, 85, 48, -90 + th)
    d.polygon([(mx_, my_ - 3), (mx_ + 3, my_), (mx_, my_ + 3), (mx_ - 3, my_)], fill=LRD)
    # tachometer 0..12 sweeping clockwise from just below three o'clock, like the original dial
    cx, cy, rx, ry = 160, 150, 32, 22
    d.ellipse((cx - rx - 1, cy - ry - 1, cx + rx + 1, cy + ry + 1), fill=LGR)
    d.ellipse((cx - rx + 1, cy - ry + 1, cx + rx - 1, cy + ry - 1), fill=BLK)
    for n in range(13):
        deg = 10 + n * 26.25
        x1, y1 = ell_pt(cx, cy, rx - 3, ry - 3, deg)
        x2, y2 = ell_pt(cx, cy, rx - 6, ry - 6, deg)
        d.line([(round(x1), round(y1)), (round(x2), round(y2))], fill=YEL)
        if n >= 2:
            x, y = ell_pt(cx, cy, rx - 12, ry - 10, deg)
            s = str(n)
            mini_text(d, s, round(x) - 2 * len(s) + 1, round(y) - 2, YEL)
    for n in range(110, 121):
        x, y = ell_pt(cx, cy, rx - 3, ry - 3, 10 + n / 10 * 26.25)
        d.point((round(x), round(y)), fill=LRD)
    glyph_text(d, "rpm", cx - 9, cy - 13, LGR, font)
    d.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=LGR)
    draw_gauge(d, 105, 157, 20, 15, "OIL", font, 9)
    draw_gauge(d, 215, 157, 20, 15, "TEMP", font, 9)
    # fire extinguisher pod
    d.polygon([(50, 150), (58, 140), (82, 140), (82, 189), (50, 189)], fill=LGR)
    d.rectangle((52, 144, 56, 170), fill=WHT)
    d.rectangle((52, 164, 82, 172), fill=DGR)
    glyph_text(d, "FIRE", 54, 163, LGR, font)
    d.rectangle((56, 176, 77, 186), fill=RED, outline=BLK)
    for x in range(58, 77, 2):
        d.line([(x, 177), (x, 185)], fill=LRD)
    # ignition switches
    glyph_text(d, "ON", 247, 150, WHT, font)
    d.rectangle((247, 160, 262, 168), fill=RED)
    glyph_text(d, "IGN", 246, 160, WHT, font)
    d.rectangle((244, 176, 266, 186), fill=RED)
    glyph_text(d, "FUEL", 243, 177, WHT, font)
    # gear shift box
    d.rectangle((262, 138, 315, 181), fill=BLK)
    d.rectangle((265, 142, 311, 178), fill=LGR, outline=WHT)
    for gx in (276, 288, 300):
        d.rectangle((gx - 2, 148, gx + 2, 170), fill=BLK)
    d.line([(274, 159), (302, 159)], fill=DGR)
    # lower white switch panel with three round buttons
    d.rectangle((115, 173, 203, 188), fill=WHT)
    d.rectangle((135, 173, 185, 175), fill=LGR)
    for bx in (137, 160, 183):
        d.ellipse((bx - 5, 177, bx + 5, 185), fill=LGR, outline=DGR)
    d.rectangle((0, 189, 319, 199), fill=BLK)
    return rows_expanded(im, 110, 200)


def knob_sprite():
    im = pimage(9, 9, TR)
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, 8, 8), fill=BLK)
    d.ellipse((1, 1, 7, 7), fill=RED)
    d.point((3, 2), fill=LRD)
    return to_runs(im)


# ---- cars seen from behind -------------------------------------------------------------------------------
TEAMS = [  # main colour, accent, tyre/wing colour
    (WHT, LRD, BLK), (WHT, LBL, BLK), (LRD, WHT, BLK), (LCY, GRN, BLK), (YEL, BLK, BLK),
    (LBL, WHT, BLK), (BLU, YEL, BLK), (MAG, WHT, BLK), (LMG, BLU, BLK), (BRN, YEL, BLK)]
CAR_W = [3, 4, 5, 6, 8, 10, 12, 15, 19, 24, 30, 38]


def car_master(team):
    main, acc, dark = TEAMS[team]
    im = pimage(40, 18, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 39, 4), fill=acc)
    d.rectangle((0, 0, 1, 7), fill=dark)
    d.rectangle((38, 0, 39, 7), fill=dark)
    d.rectangle((2, 5, 37, 5), fill=dark)
    d.rectangle((0, 8, 8, 17), fill=dark)
    d.rectangle((31, 8, 39, 17), fill=dark)
    d.rectangle((1, 9, 7, 10), fill=DGR)
    d.rectangle((32, 9, 38, 10), fill=DGR)
    d.polygon([(11, 6), (28, 6), (26, 17), (13, 17)], fill=main)
    d.rectangle((17, 3, 22, 9), fill=main)
    d.rectangle((18, 4, 21, 7), fill=LGR if main != LGR else WHT)
    d.rectangle((9, 12, 30, 14), fill=acc)
    d.rectangle((18, 15, 21, 17), fill=DGR)
    return im


def car_sprites():
    out = {}
    for t in range(len(TEAMS)):
        m = car_master(t)
        out[t] = [to_runs(scaled(m, w, max(1, round(w * 18 / 40)))) for w in CAR_W]
    return out


# ---- roadside objects: master drawn at 16 px per metre, then shrunk to the row buckets ---------------------
BUCKETS = [2, 3, 4, 5, 6, 7, 9, 11, 14, 17, 21, 26]
PM_ROW = 0.6                 # screen px per metre per row below the horizon (matches the road projection)
PM_MASTER = 16.0
CROWD = [DGR, DGR, BLU, BLU, RED, WHT, LGR, BLK]   # calm dark tones like the original, no loud colours


def obj_tree(v, rnd):
    im = pimage(64, 96, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((28, 62, 35, 95), fill=BRN)
    d.ellipse((0, 0, 63, 70), fill=BLK)
    d.ellipse((2, 2, 61, 68), fill=GRN)
    d.pieslice((2, 2, 61, 68), 100, 200, fill=LGN)
    for _ in range(14):
        x, y = rnd.randrange(8, 44), rnd.randrange(6, 50)
        d.ellipse((x, y, x + 8, y + 6), fill=LGN if x + y < 60 else GRN)
    d.pieslice((2, 2, 61, 68), 300, 60, fill=BLK if v else GRN)
    d.rectangle((26, 62, 28, 95), fill=BRN)
    d.rectangle((29, 62, 36, 95), fill=BLK)
    return im


def obj_pine(v, rnd):
    im = pimage(48, 128, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((21, 100, 26, 127), fill=BRN)
    for i in range(4):
        y0 = i * 24
        d.polygon([(24, y0), (46 - i * 2, y0 + 44), (2 + i * 2, y0 + 44)], fill=GRN if i % 2 == 0 else LGN)
    return im


def obj_board(v, rnd):
    im = pimage(128, 72, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((16, 44, 22, 71), fill=DGR)
    d.rectangle((106, 44, 112, 71), fill=DGR)
    bg = [LRD, YEL, LBL, WHT][v]
    d.rectangle((0, 0, 127, 47), fill=bg, outline=BLK)
    d.rectangle((2, 2, 125, 45), outline=WHT)
    x = 6
    while x < 118:
        w = rnd.randrange(6, 22)
        d.rectangle((x, 8, x + w, 38), fill=[BLK, WHT, LRD, BLU][(v + x) % 4] if bg != BLK else WHT)
        x += w + rnd.randrange(4, 10)
    return im


def obj_stand(v, rnd):
    im = pimage(384, 96, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 383, 9), fill=WHT)
    d.rectangle((0, 10, 383, 13), fill=DGR)
    d.rectangle((0, 14, 383, 95), fill=DGR)
    for y in range(16, 78, 6):
        d.rectangle((0, y + 4, 383, y + 5), fill=BLK)
        x = 2
        while x < 382:
            c = rnd.choice(CROWD)
            w = rnd.choice((4, 6, 8))
            d.rectangle((x, y, x + w - 1, y + 3), fill=c)
            d.rectangle((x + 1, y, x + 1, y + 1), fill=WHT if c != WHT else LGR)
            x += w + rnd.choice((0, 2))
    d.rectangle((0, 80, 383, 95), fill=[BLU, DGR, LGR, BLU][v % 4])
    d.rectangle((0, 86, 383, 87), fill=WHT)
    for x in range(0, 384, 48):
        d.rectangle((x, 14, x + 2, 79), fill=LGR)
    return im


def obj_sign(v, rnd):
    im = pimage(24, 40, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((11, 24, 13, 39), fill=DGR)
    d.rectangle((0, 0, 23, 24), fill=WHT, outline=BLK)
    for i in range(v + 1):
        d.rectangle((3 + i * 7 - (v * 3), 3, 5 + i * 7 - (v * 3), 21), fill=LRD)
    return im


def obj_building(v, rnd):
    im = pimage(160, 224, TR)
    d = ImageDraw.Draw(im)
    wall = [LGR, WHT, YEL, LRD][v % 4]
    d.rectangle((0, 8, 159, 223), fill=wall)
    d.rectangle((126, 8, 159, 223), fill=LGR if wall != LGR else DGR)
    d.rectangle((0, 0, 159, 12), fill=DGR)
    d.rectangle((0, 8, 159, 223), outline=BLK)
    for y in range(24, 210, 28):
        for x in range(10, 150, 26):
            d.rectangle((x, y, x + 12, y + 14), fill=LBL if rnd.random() < .6 else DGR)
    return im


def obj_yacht(v, rnd):
    im = pimage(192, 112, TR)
    d = ImageDraw.Draw(im)
    d.polygon([(8, 70), (184, 70), (160, 108), (30, 108)], fill=WHT)
    d.rectangle((8, 70, 184, 76), fill=BLU if v == 0 else LRD)
    d.rectangle((60, 40, 120, 69), fill=WHT, outline=LGR)
    d.rectangle((70, 46, 110, 56), fill=LBL)
    d.line([(150, 70), (150, 4)], fill=DGR, width=3)
    d.polygon([(148, 8), (148, 64), (112, 64)], fill=WHT)
    return im


def obj_tower(v, rnd):
    im = pimage(64, 352, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((6, 10, 57, 351), fill=LGR)
    d.rectangle((0, 0, 63, 14), fill=DGR)
    for y in range(24, 340, 16):
        for x in range(10, 54, 12):
            d.rectangle((x, y, x + 6, y + 7), fill=BLK if (x + y) % 3 else LBL)
    return im


def obj_portal(v, rnd):
    im = pimage(320, 160, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 319, 40), fill=LGR, outline=DGR)
    d.rectangle((0, 0, 30, 159), fill=LGR, outline=DGR)
    d.rectangle((289, 0, 319, 159), fill=LGR, outline=DGR)
    for x in range(20, 300, 40):
        d.rectangle((x, 30, x + 16, 36), fill=YEL)
    return im


def obj_gantry(v, rnd):
    im = pimage(352, 144, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 20, 19, 143), fill=WHT, outline=LGR)
    d.rectangle((332, 20, 351, 143), fill=WHT, outline=LGR)
    d.rectangle((0, 0, 351, 40), fill=WHT, outline=DGR)
    for i in range(6):
        d.rectangle((24 + i * 52, 8, 24 + i * 52 + 24, 32), fill=BLK if i % 2 == 0 else LRD)
    return im


def obj_garage(v, rnd):
    im = pimage(320, 64, TR)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 319, 63), fill=WHT, outline=LGR)
    for i in range(6):
        d.rectangle((10 + i * 52, 14, 52 + i * 52, 63), fill=[LBL, LRD, YEL, LGN, LMG, LCY][i])
        d.rectangle((14 + i * 52, 20, 48 + i * 52, 63), fill=DGR)
    return im


OBJ_MAKERS = {"tree": (obj_tree, 2), "pine": (obj_pine, 1), "board": (obj_board, 4), "stand": (obj_stand, 4),
              "sign": (obj_sign, 3), "building": (obj_building, 4), "yacht": (obj_yacht, 2),
              "tower": (obj_tower, 1), "portal": (obj_portal, 1), "gantry": (obj_gantry, 1),
              "garage": (obj_garage, 1)}


def object_sprites():
    rnd = random.Random(11)
    out = {}
    for kind, (fn, nvar) in OBJ_MAKERS.items():
        for v in range(nvar):
            m = fn(v, rnd)
            sizes = []
            for b in BUCKETS:
                f = PM_ROW * b / PM_MASTER
                sizes.append(to_runs(scaled(m, round(m.width * f), round(m.height * f))))
            out[(kind, v)] = sizes
    return out


# ---- horizon strips: 17 rows x 960 vpx (640 wraps) ----------------------------------------------------------
def horizon_strip(style, seed):
    rnd = random.Random(seed)
    im = pimage(960, 17, LCY)
    d = ImageDraw.Draw(im)

    def both(fn):
        fn(0)
        fn(640)

    if style in ("mountain", "harbour", "hills"):
        def peaks(off):
            x = -40
            while x < 680:
                w = rnd.randrange(40, 90)
                h = rnd.randrange(5, 13) if style != "hills" else rnd.randrange(2, 6)
                col = LGR if style == "mountain" else (LGN if style == "hills" else LGR)
                d.polygon([(x + off, 17), (x + w // 2 + off, 17 - h), (x + w + off, 17)], fill=col)
                if style == "mountain" and h > 8:
                    d.polygon([(x + w // 2 + off - 4, 17 - h + 3), (x + w // 2 + off, 17 - h),
                               (x + w // 2 + off + 4, 17 - h + 3)], fill=WHT)
                x += w - 10
        state = rnd.getstate()
        both(lambda o: (rnd.setstate(state), peaks(o)))
    if style == "city":
        def sky(off):
            rnd.seed(seed + 99)
            x = 0
            while x < 640:
                w, h = rnd.randrange(8, 20), rnd.randrange(5, 15)
                d.rectangle((x + off, 17 - h, x + off + w, 17), fill=[LGR, DGR, LBL][rnd.randrange(3)])
                for wy in range(17 - h + 2, 15, 3):
                    for wx in range(x + off + 2, x + off + w - 1, 3):
                        d.point((wx, wy), fill=YEL if rnd.random() < .3 else BLK)
                x += w + rnd.randrange(0, 4)
            for tx in (120, 400):
                d.rectangle((tx + off, 0, tx + off + 7, 17), fill=LGR)
                d.rectangle((tx + off, 0, tx + off + 7, 1), fill=DGR)
                for wy in range(3, 16, 3):
                    d.line([(tx + off + 1, wy), (tx + off + 6, wy)], fill=BLK)
        both(sky)
    if style == "harbour":
        def town(off):
            rnd.seed(seed + 5)
            x = 0
            while x < 640:
                w, h = rnd.randrange(6, 14), rnd.randrange(3, 8)
                d.rectangle((x + off, 12 - h, x + off + w, 13), fill=[WHT, YEL, LRD, LGR][rnd.randrange(4)])
                x += w + 1
            d.rectangle((off, 13, off + 640, 16), fill=LBL)
            for _ in range(14):
                sx = rnd.randrange(0, 640)
                d.polygon([(sx + off, 15), (sx + off + 3, 15), (sx + off + 1, 11)], fill=WHT)
        both(town)
    if style == "trees":
        def trees(off):
            rnd.seed(seed + 3)
            for _ in range(90):
                x = rnd.randrange(0, 640)
                h = rnd.randrange(2, 5)
                d.ellipse((x + off, 17 - h * 2, x + off + 7, 17), fill=GRN if rnd.random() < .7 else LGN)
        both(trees)
    # far grandstand ahead of the start, as in the opening picture
    def stand(off):
        d.rectangle((95 + off, 5, 230 + off, 7), fill=WHT)
        d.rectangle((95 + off, 8, 230 + off, 14), fill=LGR)
        for yy in range(8, 14, 2):
            for xx in range(96 + off, 230 + off, 2):
                d.point((xx, yy), fill=rnd.choice(CROWD) if rnd.random() < .8 else BLK)
        d.rectangle((55 + off, 10, 95 + off, 13), fill=LGR)
        d.rectangle((230 + off, 10, 275 + off, 13), fill=LGR)
        for xx in range(56 + off, 275 + off, 3):
            d.point((xx, 11), fill=rnd.choice(CROWD))
    stand(0)
    stand(640)
    d.rectangle((0, 14, 959, 16), fill=GRN)
    if style == "harbour":
        d.rectangle((0, 14, 959, 16), fill=LBL)
        d.rectangle((0, 16, 959, 16), fill=BLU)
    return rows_expanded_strip(im)


def rows_expanded_strip(im):
    w, h = im.size
    return [b"".join(P5[i] for i in im.crop((0, y, w, y + 1)).tobytes()) for y in range(h)]


# ---- mirror car sprites ----------------------------------------------------------------------------------
def mirror_cars():
    out = []
    for t in range(len(TEAMS)):
        m = car_master(t)
        out.append([to_runs(scaled(m, w, max(1, round(w * 18 / 40)))) for w in (4, 7, 11)])
    return out
