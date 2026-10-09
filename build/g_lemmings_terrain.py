# Procedural terrain painting for the Lemmings levels: one L image holds a material id per pixel, a renderer then
# turns it into the orange cavern / riveted steel / gold temple / marble look with moss on top and roots below.
import math, random
from PIL import Image, ImageDraw

AIR, DIRT, STEEL, GOLD, MARBLE = range(5)
H = 160


class Painter:
    def __init__(self, w, seed=1):
        self.w = w
        self.im = Image.new("L", (w, H), 0)
        self.d = ImageDraw.Draw(self.im)
        self.rnd = random.Random(seed)

    def rect(self, x0, y0, x1, y1, m):
        # x1/y1 exclusive, so a platform "x0..x1, top..bottom" reads like the numbers in the level notes
        self.d.rectangle((x0, y0, x1 - 1, y1 - 1), fill=m)

    def poly(self, pts, m):
        self.d.polygon(pts, fill=m)

    def ellipse(self, cx, cy, rx, ry, m):
        self.d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=m)

    def wavy(self, x0, x1, y_top, y_bottom_base, amp, m, period=37.0, phase=0.0, flat=None):
        # solid band whose lower edge undulates: cavern ceilings. flat=(a, b) keeps that x range at the base line
        r = self.rnd
        ph1, ph2 = r.random() * 6, r.random() * 6
        for x in range(x0, x1):
            off = amp * (0.6 * math.sin(x / period * 2 + ph1 + phase) + 0.4 * math.sin(x / (period * 0.43) + ph2))
            if flat and flat[0] <= x < flat[1]:
                off = 0
            yb = int(y_bottom_base + off)
            self.d.line((x, y_top, x, yb), fill=m)

    def blob(self, cx, cy, rx, ry, m, bumps=7):
        pts = []
        r = self.rnd
        ph = [r.random() * 6 for _ in range(3)]
        for i in range(48):
            a = i / 48 * 2 * math.pi
            k = 1 + 0.12 * math.sin(a * 3 + ph[0]) + 0.08 * math.sin(a * 5 + ph[1]) + 0.05 * math.sin(a * bumps + ph[2])
            pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
        self.d.polygon(pts, fill=m)

    def clear(self, x0, y0, x1, y1):
        self.rect(x0, y0, x1, y1, AIR)


DIRT_PAL = [(112, 22, 10), (156, 38, 14), (196, 64, 18), (222, 98, 26), (238, 130, 36), (248, 166, 60)]
MOSS = [(8, 70, 14), (24, 120, 22), (52, 170, 34), (110, 210, 60)]


def render(P, style_hint=None):
    w = P.w
    mat = list(P.im.getdata())
    rnd = random.Random(99)
    g = lambda x, y: mat[y * w + x] if 0 <= x < w and 0 <= y < H else AIR

    # distance to the nearest air pixel straight up / down / left / right (capped), used for shading and moss
    cap = 40
    up = [0] * (w * H)
    dn = [0] * (w * H)
    lf = [0] * (w * H)
    rt = [0] * (w * H)
    for x in range(w):
        run = 0
        for y in range(H):
            run = run + 1 if mat[y * w + x] else 0
            up[y * w + x] = min(run, cap)
        run = 0
        for y in range(H - 1, -1, -1):
            run = run + 1 if mat[y * w + x] else 0
            dn[y * w + x] = min(run, cap)
    for y in range(H):
        run = 0
        for x in range(w):
            run = run + 1 if mat[y * w + x] else 0
            lf[y * w + x] = min(run, cap)
        run = 0
        for x in range(w - 1, -1, -1):
            run = run + 1 if mat[y * w + x] else 0
            rt[y * w + x] = min(run, cap)

    # low-resolution random field gives the dirt its mottled blobs
    fw, fh = w // 9 + 3, H // 7 + 3
    field = Image.frombytes("L", (fw, fh), bytes(rnd.randrange(256) for _ in range(fw * fh)))
    field = field.resize((fw * 9, fh * 7), Image.BICUBIC)
    fld = field.load()
    out = Image.new("RGB", (w, H), (0, 0, 0))
    px = out.load()
    mask = bytearray(w * H)

    for y in range(H):
        for x in range(w):
            m = mat[y * w + x]
            if not m:
                continue
            i = y * w + x
            u, d, l, r = up[i], dn[i], lf[i], rt[i]
            if m == DIRT:
                v = fld[x, y] / 255.0 + (rnd.random() - 0.5) * 0.16
                v += 0.12 * math.sin(y * 0.35 + x * 0.05)
                k = int(max(0, min(5.99, 2.3 + (v - 0.5) * 6.0)))
                col = DIRT_PAL[k]
                if d <= 1 or r <= 1 and not (g(x + 1, y) == STEEL):
                    col = DIRT_PAL[max(0, k - 2)]
                if u <= 1:
                    col = MOSS[2] if rnd.random() < 0.5 else MOSS[3]
                elif u == 2:
                    col = MOSS[1]
                elif u == 3:
                    col = MOSS[0] if rnd.random() < 0.55 else MOSS[1]
                elif u == 4 and rnd.random() < 0.25:
                    col = MOSS[0]
                mask[i] = 1
            elif m == STEEL:
                tx, ty = x % 16, y % 16
                base = 128 + int(8 * math.sin((x * 0.7 + y * 0.3)))
                col = (base, base + 2, base + 12)
                if rnd.random() < 0.12:
                    col = (base - 14, base - 12, base - 2)
                if ty == 0 or tx == 0:
                    col = (178, 180, 192)
                if ty == 15 or tx == 15:
                    col = (70, 72, 84)
                if (tx, ty) in ((3, 3), (12, 3), (3, 12), (12, 12), (4, 3), (13, 3), (4, 12), (13, 12)):
                    col = (176, 52, 36)
                if (tx, ty) in ((3, 4), (12, 4), (3, 13), (12, 13)):
                    col = (110, 24, 20)
                if u <= 1:
                    col = MOSS[0] if rnd.random() < 0.5 else MOSS[1]
                elif u == 2 and rnd.random() < 0.5:
                    col = MOSS[1]
                mask[i] = 2
            elif m == GOLD:
                if u <= 1:
                    col = (255, 236, 130)
                elif d <= 1:
                    col = (140, 88, 14)
                else:
                    band = (y // 2 + x // 7) % 3
                    col = ((226, 170, 36), (206, 146, 28), (240, 190, 56))[band]
                    if l <= 1:
                        col = (250, 214, 90)
                    if r <= 1:
                        col = (150, 98, 18)
                mask[i] = 1
            else:  # marble brick wall
                bx = (x + (8 if (y // 8) % 2 else 0)) % 16
                by = y % 8
                v = fld[x, y] / 255.0
                base = 196 + int(24 * v)
                col = (base - 10, base, base + 12)
                if by == 0 or bx == 0:
                    col = (112, 120, 142)
                elif by == 1 or bx == 1:
                    col = (230, 236, 246)
                if u <= 1:
                    col = MOSS[0] if rnd.random() < 0.5 else MOSS[1]
                elif u == 2 and rnd.random() < 0.4:
                    col = MOSS[2]
                mask[i] = 1
            px[x, y] = col

    # tufts of moss on top of dirt/steel/marble surfaces and roots hanging under overhangs: decoration only
    for x in range(w):
        for y in range(1, H - 1):
            m = mat[y * w + x]
            if m in (DIRT, MARBLE, STEEL) and not mat[(y - 1) * w + x]:
                if rnd.random() < 0.10:
                    for k in range(1, rnd.randint(2, 3)):
                        if not mat[(y - k) * w + x]:
                            px[x, y - k] = MOSS[1 + (k & 1)]
            if m in (DIRT, STEEL, MARBLE) and y + 1 < H and not mat[(y + 1) * w + x] and rnd.random() < 0.07:
                ln = rnd.randint(3, 10)
                for k in range(1, ln):
                    yy = y + k
                    if yy >= H or mat[yy * w + x]:
                        break
                    px[x, yy] = MOSS[1] if k < ln - 2 else MOSS[3]
                    if k > 2 and rnd.random() < 0.3 and not mat[yy * w + x + 1 if x + 1 < w else 0]:
                        px[min(w - 1, x + 1), yy] = MOSS[0]
    return out, mask
