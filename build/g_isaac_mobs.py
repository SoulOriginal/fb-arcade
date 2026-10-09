# Build-time art, part 2: enemies and bosses. Original drawings in a "cute-gross" cartoon style (round shapes, dark
# outlines, big hollow eyes); nothing here is traced from the real game's sprites.
import math, random
from PIL import Image
from g_isaac_art import *

FLESH = (232, 176, 160, 255)
FLESH_DK = (190, 120, 110, 255)
PALE = (240, 214, 196, 255)
HOLLOW = (28, 14, 20, 255)
RED = (200, 50, 54, 255)
RED_DK = (122, 24, 34, 255)
WINGC = (206, 214, 226, 255)
WHITE = (252, 250, 248, 255)
TOOTH = (250, 246, 232, 255)


def hollow_eye(p, cx, cy, rx, ry, glint=True):
    p.ell(cx, cy, rx, ry, fill=HOLLOW)
    if glint:
        p.ell(cx - rx * 0.25, cy - ry * 0.3, rx * 0.25, rx * 0.25, fill=(255, 255, 255, 255))


def fly(frame):
    p = Pen(56, 52)
    up = frame == 0
    for sx in (-1, 1):
        p.ell(28 + sx * 12, 14 if up else 22, 9, 13 if up else 8, fill=WINGC, outline=OUT, w=1.2)
    p.blob(28, 30, 11, 10, (60, 52, 64, 255), ow=1.8)
    p.ell(23, 28, 3.6, 4, fill=RED)
    p.ell(33, 28, 3.6, 4, fill=RED)
    p.ell(24, 27, 1.2, 1.2, fill=WHITE)
    return p.done()


def pooter(frame):
    p = Pen(84, 76)
    flap = frame == 0
    for sx in (-1, 1):
        p.ell(42 + sx * 27, 22 if flap else 30, 13, 16 if flap else 10, fill=WINGC, outline=OUT, w=1.3)
    p.blob(42, 38, 24, 21, (198, 92, 84, 255))
    p.ell(36, 28, 7, 4, fill=(230, 140, 130, 255))
    # nose tube; swells when it shoots
    r = 7 if flap else 10
    p.blob(42, 60, r, 8, (150, 56, 60, 255))
    p.ell(42, 63, r * 0.55, 4, fill=HOLLOW)
    for sx in (-1, 1):
        hollow_eye(p, 42 + sx * 10, 36, 5.2, 6.5)
    return p.done()


def gaper(frame):
    p = Pen(88, 108)
    ph = frame / 4 * 2 * math.pi
    s = math.sin(ph)
    bob = abs(s) * 3
    for sx, l in ((-1, s), (1, -s)):
        p.blob(44 + sx * 9, 96 - max(0, l) * 6, 6.5, 8, FLESH_DK, ow=1.8)
    p.blob(44, 72 - bob, 18, 20, (186, 90, 88, 255))
    p.poly([(30, 62 - bob), (58, 62 - bob), (62, 86 - bob), (26, 86 - bob)], fill=None)
    p.line([(32, 82 - bob), (38, 74 - bob), (46, 84 - bob), (54, 74 - bob)], RED_DK, 2)
    for sx in (-1, 1):
        p.blob(44 + sx * 24, 70 - bob + s * sx * 5, 5.5, 11, FLESH, ow=1.8)
    p.blob(44, 36 - bob, 32, 29, PALE)
    p.arc(44, 36 - bob, 26, 22, 25, 155, FLESH_DK, 4)
    for sx in (-1, 1):
        hollow_eye(p, 44 + sx * 14, 30 - bob, 8, 11, glint=False)
        p.line([(44 + sx * 14, 41 - bob), (44 + sx * 15, 52 - bob)], RED, 2.4)
    p.ell(44, 50 - bob, 11, 9, fill=HOLLOW)
    p.ell(44, 52 - bob, 6, 4, fill=(140, 30, 40, 255))
    return p.done()


def horf(frame):
    p = Pen(88, 84)
    p.blob(44, 46, 32, 28, (156, 170, 156, 255))
    p.arc(44, 46, 26, 22, 25, 155, (118, 132, 120, 255), 4)
    # torn-off top of the head
    p.poly([(16, 26), (24, 12), (32, 22), (44, 8), (56, 22), (66, 12), (72, 26)], fill=(210, 110, 110, 255), outline=OUT, w=1.6)
    for sx in (-1, 1):
        hollow_eye(p, 44 + sx * 15, 38, 6.5, 8)
    m = 12 if frame else 7
    p.ell(44, 58, 12, m, fill=HOLLOW)
    p.ell(44, 58 + m * 0.3, 7, m * 0.5, fill=(140, 30, 40, 255))
    return p.done()


def clotty(frame):
    p = Pen(84, 80)
    sq = 3 if frame else 0
    p.blob(42, 44 + sq, 30 + sq, 26 - sq, (176, 44, 52, 255))
    p.ell(30, 32, 9, 5, fill=(230, 100, 100, 255))
    for sx in (-1, 1):
        p.blob(42 + sx * 13, 42 + sq, 7, 8, WHITE, ow=1.6)
        p.ell(42 + sx * 13, 44 + sq, 3.6, 4.4, fill=HOLLOW)
    p.arc(42, 58 + sq, 10, 6, 200, 340, OUT, 2.4)
    return p.done()


def mulligan(frame):
    p = Pen(90, 108)
    w = 3 if frame else 0
    for sx in (-1, 1):
        p.blob(45 + sx * 10, 98, 7, 7, FLESH_DK, ow=1.8)
    p.blob(45, 70, 24, 24, (204, 150, 150, 255))
    p.arc(45, 70, 18, 17, 20, 160, FLESH_DK, 4)
    for sx in (-1, 1):
        p.blob(45 + sx * 27, 66 + w * sx, 5.5, 13, FLESH, ow=1.8)
    p.blob(45, 32, 26, 25, (232, 190, 176, 255))
    for sx in (-1, 1):
        p.blob(45 + sx * 12, 24, 8.5, 10, WHITE, ow=1.8)
        p.ell(45 + sx * 12 + sx * -1, 26, 4, 5, fill=HOLLOW)
    p.ell(45, 44, 10, 9 + w, fill=HOLLOW)
    p.ell(45, 49 + w, 6, 3, fill=(150, 40, 50, 255))
    return p.done()


def charger(direction, frame):
    p = Pen(100, 100)
    c = (176, 78, 76, 255)
    k = 3 if frame else -3
    segs = []
    if direction == "r":
        segs = [(26, 52 + k), (50, 52 - k), (74, 52)]
    elif direction == "d":
        segs = [(50 + k, 24), (50 - k, 48), (50, 72)]
    else:
        segs = [(50 + k, 76), (50 - k, 52), (50, 28)]
    for i, (x, y) in enumerate(segs):
        r = 17 if i < 2 else 21
        p.blob(x, y, r, r, c if i < 2 else (196, 98, 92, 255))
        p.arc(x, y, r - 5, r - 5, 30, 150, RED_DK, 3)
    hx, hy = segs[2]
    ex = {"r": 0, "d": 0, "u": 0}[direction]
    if direction == "u":
        p.arc(hx, hy, 12, 10, 200, 340, RED_DK, 3)
        return p.done()
    dx = 5 if direction == "r" else 0
    for sx in (-1, 1):
        if direction == "r":
            p.blob(hx + 5, hy + sx * 9, 5.5, 6.5, WHITE, ow=1.5)
            p.ell(hx + 8, hy + sx * 9, 3, 3.6, fill=HOLLOW)
        else:
            p.blob(hx + sx * 9, hy + 2, 5.5, 6.5, WHITE, ow=1.5)
            p.ell(hx + sx * 9, hy + 5, 3, 3.6, fill=HOLLOW)
    return p.done()


def host(opened):
    p = Pen(88, 92)
    if opened:
        p.blob(44, 66, 20, 18, (210, 110, 110, 255))
        for sx in (-1, 1):
            hollow_eye(p, 44 + sx * 9, 64, 4.5, 6)
        p.blob(44, 34, 32, 22, (232, 226, 210, 255))
        p.poly([(18, 40), (70, 40), (64, 52), (24, 52)], fill=(120, 20, 30, 255))
        for x in range(24, 66, 8):
            p.rect(x, 40, x + 5, 48, fill=TOOTH, outline=OUT, w=0.8)
        p.rect(18, 20, 40, 28, fill=None)
    else:
        p.blob(44, 52, 33, 28, (236, 230, 214, 255))
        p.arc(44, 52, 26, 22, 25, 155, (200, 192, 176, 255), 4)
        for sx in (-1, 1):
            p.ell(44 + sx * 14, 44, 9, 11, fill=HOLLOW)
        p.poly([(44, 54), (40, 62), (48, 62)], fill=HOLLOW)
        p.rect(24, 64, 64, 74, fill=(236, 230, 214, 255), outline=OUT, w=1.6, r=3)
        for x in range(30, 62, 7):
            p.line([(x, 64), (x, 74)], OUT, 1.4)
    return p.done()


def boil(stage):
    p = Pen(76, 72)
    r = (16, 22, 28)[stage]
    p.ell(38, 56, r + 8, 8, fill=(40, 20, 24, 110))
    p.blob(38, 48, r, r * 0.8, (206, 96, 92, 255))
    p.ell(38 - r * 0.3, 44 - r * 0.2, r * 0.45, r * 0.3, fill=(240, 150, 140, 255))
    if stage >= 1:
        p.ell(38, 40, r * 0.35, r * 0.28, fill=(246, 226, 140, 255), outline=(190, 150, 70, 255), w=1.2)
    if stage == 2:
        p.line([(30, 52), (36, 44), (42, 52)], RED_DK, 1.6)
    return p.done()


def spider(frame):
    p = Pen(68, 56)
    k = 4 if frame else -4
    for sx in (-1, 1):
        for i, a in enumerate((-30, -10, 12, 34)):
            y0 = 30 + a * 0.2
            kk = k * (1 if i % 2 else -1)
            p.line([(34, y0), (34 + sx * 14, y0 - 12 + kk), (34 + sx * 26, y0 + 8 + kk * 0.5)], OUT, 2.4)
    p.blob(34, 32, 13, 11, (40, 36, 48, 255), ow=1.8)
    for sx in (-1, 1):
        p.ell(34 + sx * 5, 28, 3, 3.6, fill=(240, 60, 60, 255))
    return p.done()


# ------------------------------------------------------------------------------------------------ bosses
def monstro(state):
    p = Pen(220, 200)
    sq = {0: 0, 1: 12, 2: 0}[state]
    p.ell(110, 176, 80, 14, fill=(0, 0, 0, 0))
    p.blob(110, 112 + sq, 86, 70 - sq, (232, 176, 168, 255), ow=3)
    p.arc(110, 112 + sq, 70, 56 - sq, 30, 150, (190, 128, 124, 255), 7)
    p.ell(78, 78 + sq, 22, 12, fill=(248, 214, 204, 255))
    for sx in (-1, 1):
        p.blob(110 + sx * 36, 76 + sq, 11, 13, WHITE, ow=2.2)
        p.ell(110 + sx * 36, 80 + sq, 5, 7, fill=HOLLOW)
    # the huge mouth is the whole point of Monstro
    mw = 56 if state == 2 else 46
    mh = 34 if state == 2 else 20
    p.ell(110, 128 + sq, mw, mh, fill=(60, 10, 22, 255), outline=OUT, w=3)
    p.ell(110, 142 + sq, mw * 0.6, mh * 0.45, fill=(176, 50, 70, 255))
    for i in range(7):
        x = 110 - mw * 0.8 + i * mw * 1.6 / 6
        p.poly([(x - 4, 128 + sq - mh * 0.7), (x + 4, 128 + sq - mh * 0.7), (x, 128 + sq - mh * 0.7 + 12)],
               fill=TOOTH, outline=OUT, w=1)
    if state == 1:
        p.line([(40, 60), (28, 40)], OUT, 4)
        p.line([(180, 60), (192, 40)], OUT, 4)
    return p.done()


def duke(frame):
    p = Pen(176, 160)
    up = frame == 0
    for sx in (-1, 1):
        p.ell(88 + sx * 62, 40 if up else 56, 28, 36 if up else 22, fill=WINGC, outline=OUT, w=2)
        p.line([(88 + sx * 50, 56), (88 + sx * 74, 30 if up else 50)], (150, 160, 180, 255), 2)
    p.blob(88, 92, 54, 50, (170, 150, 128, 255), ow=3)
    p.arc(88, 92, 44, 40, 25, 155, (130, 112, 96, 255), 6)
    p.blob(88, 62, 36, 28, (214, 188, 160, 255), ow=2.4)
    for sx in (-1, 1):
        p.blob(88 + sx * 16, 58, 11, 13, WHITE, ow=2)
        p.ell(88 + sx * 16, 62, 5, 7, fill=HOLLOW)
    p.ell(88, 82, 14, 10, fill=HOLLOW)
    for x in (-8, 0, 8):
        p.rect(88 + x - 2.5, 76, 88 + x + 2.5, 82, fill=TOOTH)
    p.line([(60, 110), (70, 118), (80, 110), (96, 118), (108, 110), (118, 116)], (110, 90, 76, 255), 2.4)
    return p.done()


def contusion(frame):
    p = Pen(156, 140)
    s = 3 if frame else 0
    p.blob(78, 74, 56 + s, 52 - s, (228, 130, 128, 255), ow=3)
    p.arc(78, 74, 44, 40, 25, 155, (184, 90, 92, 255), 6)
    for sx in (-1, 1):
        p.line([(78 + sx * 14, 66), (78 + sx * 34, 70)], OUT, 3)
        p.ell(78 + sx * 24, 78, 7, 4, fill=OUT)
    p.poly([(60, 40), (96, 44)], fill=None)
    p.line([(54, 44), (66, 52), (78, 42), (90, 52), (102, 44)], (120, 30, 40, 255), 3)
    p.ell(78, 100, 22, 11 + s, fill=HOLLOW)
    p.ell(78, 103 + s, 13, 5, fill=(170, 50, 66, 255))
    return p.done()


def suture(frame):
    p = Pen(100, 92)
    s = 2 if frame else 0
    p.blob(50, 48, 34 + s, 31 - s, (238, 160, 150, 255), ow=2.6)
    for sx in (-1, 1):
        p.blob(50 + sx * 14, 42, 8.5, 10, WHITE, ow=1.8)
        p.ell(50 + sx * 14, 45, 4, 5.4, fill=HOLLOW)
    p.ell(50, 66, 11, 7 + s, fill=HOLLOW)
    p.line([(30, 28), (36, 22), (44, 28)], (140, 40, 50, 255), 2.2)
    return p.done()


def cord_dot():
    p = Pen(18, 18)
    p.blob(9, 9, 5, 5, (206, 96, 100, 255), ow=1.6)
    return p.done()


def larry(direction, kind):
    # kind: head or seg. Four cardinal facing directions because Larry only moves in cardinals.
    p = Pen(100, 100)
    c = (214, 128, 112, 255)
    if kind == "seg":
        p.blob(50, 50, 38, 38, c, ow=3)
        p.arc(50, 50, 30, 30, 30, 150, (166, 84, 80, 255), 6)
        for a in range(0, 360, 90):
            r = math.radians(a + 45)
            p.ell(50 + math.cos(r) * 22, 50 + math.sin(r) * 22, 5, 5, fill=(246, 190, 170, 255))
        return p.done()
    p.blob(50, 50, 42, 40, (224, 140, 118, 255), ow=3)
    if direction == "u":
        p.arc(50, 50, 30, 30, 200, 340, (166, 84, 80, 255), 5)
        return p.done()
    ex = {"d": [(-15, 0), (15, 0)], "r": [(12, -14), (12, 14)], "l": [(-12, -14), (-12, 14)]}[direction]
    for dx, dy in ex:
        p.blob(50 + dx, 44 + dy * 0.6, 9, 11, WHITE, ow=2)
        p.ell(50 + dx + (4 if direction == "r" else -4 if direction == "l" else 0), 47 + dy * 0.6, 4.4, 5.6, fill=HOLLOW)
    mx = {"d": 0, "r": 18, "l": -18}[direction]
    p.ell(50 + mx, 68, 13, 8, fill=HOLLOW)
    p.ell(50 + mx, 70, 7, 3.5, fill=(170, 50, 66, 255))
    return p.done()


def chub(direction, kind):
    p = Pen(140, 140)
    c = (214, 210, 190, 255)
    if kind == "seg":
        p.blob(70, 70, 54, 54, c, ow=3.4)
        p.arc(70, 70, 44, 44, 30, 150, (160, 156, 140, 255), 8)
        for a in range(0, 360, 60):
            r = math.radians(a)
            p.ell(70 + math.cos(r) * 34, 70 + math.sin(r) * 34, 6, 6, fill=(150, 90, 84, 255))
        return p.done()
    p.blob(70, 70, 58, 56, (222, 218, 196, 255), ow=3.6)
    if direction == "u":
        p.arc(70, 70, 40, 40, 200, 340, (160, 156, 140, 255), 6)
        return p.done()
    ex = {"d": [(-20, 0), (20, 0)], "r": [(16, -20), (16, 20)], "l": [(-16, -20), (-16, 20)]}[direction]
    for dx, dy in ex:
        p.blob(70 + dx, 62 + dy * 0.6, 13, 15, WHITE, ow=2.4)
        p.ell(70 + dx + (5 if direction == "r" else -5 if direction == "l" else 0), 66 + dy * 0.6, 6, 8, fill=HOLLOW)
    mx = {"d": 0, "r": 22, "l": -22}[direction]
    p.ell(70 + mx, 96, 22, 12, fill=HOLLOW)
    for x in (-12, -4, 4, 12):
        p.rect(70 + mx + x - 2, 86, 70 + mx + x + 2, 92, fill=TOOTH)
    return p.done()


def gurdy(state):
    p = Pen(240, 220)
    duck = state == 2
    oy = 26 if duck else 0
    p.blob(120, 120 + oy, 100, 78 - oy * 0.5, (206, 140, 130, 255), ow=3.4)
    p.arc(120, 120 + oy, 84, 62 - oy * 0.4, 30, 150, (160, 100, 100, 255), 8)
    # stitched seams and horns
    p.line([(120, 40 + oy), (120, 70 + oy)], RED_DK, 4)
    for sx in (-1, 1):
        p.poly([(120 + sx * 46, 52 + oy), (120 + sx * 74, 14 + oy), (120 + sx * 66, 64 + oy)], fill=(230, 220, 190, 255), outline=OUT, w=2.4)
    for sx in (-1, 1):
        p.blob(120 + sx * 38, 90 + oy, 17, 20, WHITE, ow=2.6)
        p.ell(120 + sx * 38, 96 + oy, 8, 11, fill=HOLLOW)
        p.line([(120 + sx * 38, 112 + oy), (120 + sx * 41, 128 + oy)], RED, 3)
    mh = 38 if state == 1 else 24
    p.ell(120, 146 + oy, 54, mh, fill=(60, 10, 22, 255), outline=OUT, w=3)
    for i in range(8):
        x = 120 - 46 + i * 92 / 7
        p.poly([(x - 5, 146 + oy - mh * 0.75), (x + 5, 146 + oy - mh * 0.75), (x, 146 + oy - mh * 0.75 + 15)],
               fill=TOOTH, outline=OUT, w=1.2)
    p.ell(120, 160 + oy, 30, mh * 0.4, fill=(176, 50, 70, 255))
    return p.done()
