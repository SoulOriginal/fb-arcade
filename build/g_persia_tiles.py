# Build-time only: procedural tile art. One 32x63 logical cell per tile state; every level gets its own theme
# (background mode, stone palette, decorations, flame colours) so levels are recognisable by look alone.
# Layout follows the original screen: a thin lit ledge face at the bottom of each row, dark depth above it.
import random
from PIL import Image, ImageDraw

TW, TH = 32, 63
SLAB_TOP, FEET = 37, 44      # ledge top face spans y 37..47 (the prince stands at y 44); a 15 px brick course is its front face


def mul(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def theme(name, bg, face, top, flame, decor, gold=(186, 146, 0), rug=None, column="plain", bgcols=None, marks=(28, 48, 77),
          sconce=(170, 170, 170), door=(121, 134, 150), density=0.18):
    return dict(name=name, bg=bg, face=face, top=top, flame=flame, decor=decor, gold=gold, rug=rug, column=column,
                bgcols=bgcols or (mul(face, 0.45), mul(face, 0.38)), marks=marks, sconce=sconce, door=door, density=density)


ORANGE = ((255, 134, 0), (255, 200, 0), (255, 255, 180))
THEMES = {
    1: theme("dungeon", "void", (121, 134, 150), (69, 93, 113), ORANGE, "grille"),
    2: theme("dungeon_moss", "void", (112, 146, 132), (58, 100, 92), ORANGE, "chain", marks=(20, 60, 50), density=0.22),
    3: theme("crypt", "void", (128, 118, 150), (74, 64, 100), ((120, 255, 100), (200, 255, 120), (240, 255, 220)), "skull",
             marks=(50, 40, 76), density=0.24),
    4: theme("sandstone", "brick", (232, 196, 140), (168, 128, 80), ORANGE, "banner", rug=(186, 0, 0), column="deco",
             bgcols=((150, 110, 70), (132, 96, 60)), density=0.2),
    5: theme("rose_hall", "arch", (236, 170, 140), (176, 100, 90), ORANGE, "window", rug=(186, 0, 0), column="deco",
             bgcols=((140, 78, 70), (122, 66, 62)), gold=(255, 219, 0), density=0.26),
    6: theme("potion_cellar", "void", (96, 150, 170), (52, 100, 120), ((80, 220, 255), (170, 255, 255), (255, 255, 255)), "shelf",
             marks=(20, 60, 80), density=0.26),
    7: theme("marble", "panel", (214, 222, 238), (140, 156, 190), ORANGE, "window", rug=(73, 100, 220), column="deco",
             bgcols=((96, 110, 150), (84, 96, 136)), gold=(255, 219, 80), density=0.22),
    8: theme("gold_hall", "brick", (255, 214, 110), (190, 140, 50), ((255, 255, 200), (255, 255, 120), (255, 255, 255)), "banner",
             rug=(130, 20, 100), column="deco", bgcols=((160, 110, 30), (140, 96, 24)), gold=(255, 255, 120), density=0.24),
    9: theme("garden_cistern", "arch", (150, 184, 140), (84, 124, 84), ORANGE, "window", column="plain",
             bgcols=((60, 90, 64), (50, 78, 56)), marks=(30, 70, 40), density=0.26),
    10: theme("royal_blue", "panel", (160, 170, 232), (88, 100, 170), ((150, 170, 255), (210, 220, 255), (255, 255, 255)), "banner",
              rug=(231, 0, 0), column="deco", bgcols=((40, 56, 120), (32, 46, 104)), gold=(255, 219, 0), density=0.28),
    11: theme("tower", "void", (150, 110, 180), (96, 64, 130), ((255, 100, 255), (255, 170, 255), (255, 240, 255)), "window",
              marks=(60, 30, 90), column="deco", gold=(255, 170, 255), density=0.24),
    12: theme("vizier", "void", (100, 100, 124), (56, 56, 80), ((150, 200, 255), (210, 240, 255), (255, 255, 255)), "banner",
              rug=(186, 0, 0), column="deco", gold=(255, 219, 0), marks=(40, 40, 64), density=0.28),
}


class Painter:
    def __init__(self, level, variant):
        self.t = THEMES[level]
        self.v = variant
        self.rng = random.Random(level * 7919 + variant * 131)

    # ---- backgrounds ----
    def bg(self):
        t, v, rng = self.t, self.v, self.rng
        im = Image.new("RGB", (TW, TH), (0, 0, 0))
        d = ImageDraw.Draw(im)
        mode = t["bg"]
        if mode == "void":
            # Dark back wall: courses of deep-toned bricks, so a room reads as masonry rather than empty space.
            face = t["face"]
            base, mort = mul(t["top"], 0.52), mul(t["top"], 0.3)
            d.rectangle([0, 0, TW, TH], fill=mort)
            for r in range(7):
                y0 = r * 10
                off = 10 if (r + v) % 2 else 0
                for k in range(-1, 3):
                    x0 = k * 21 + off
                    col = mul(base, 1.0 if rng.random() > 0.35 else 1.18)
                    d.rectangle([x0, y0, x0 + 19, y0 + 8], fill=col)
            for _ in range(2):
                x, y = rng.randrange(2, 22), rng.randrange(6, 44)
                d.line([x, y, x + 6, y], fill=mul(t["top"], 0.8))
                d.line([x + 3, y, x + 3, y + 2], fill=mul(t["top"], 0.8))
                d.point((x - 2, y + 6), fill=mul(t["top"], 0.8))
        elif mode in ("brick", "arch"):
            b1, b2 = t["bgcols"]
            mort = mul(b2, 0.7)
            for r in range(9):
                y0 = r * 7
                off = 8 if (r + v) % 2 else 0
                d.rectangle([0, y0, TW, y0 + 6], fill=mort)
                for k in range(-1, 3):
                    x0 = k * 16 + off
                    col = b1 if (r + k + v) % 3 else b2
                    d.rectangle([x0, y0, x0 + 14, y0 + 5], fill=col)
        else:  # panel: vertical marble panels with a gilt moulding
            b1, b2 = t["bgcols"]
            d.rectangle([0, 0, TW, TH], fill=b1)
            for x in (0, 15, 31):
                d.line([x, 0, x, TH], fill=b2)
            d.rectangle([3, 8, 12, 46], outline=b2)
            d.rectangle([18, 8, 28, 46], outline=b2)
            d.line([0, 4, TW, 4], fill=t["gold"])
        px = im.load()
        if True:
            for y, f in enumerate((0.45, 0.6, 0.78, 0.9)):
                for x in range(TW):
                    px[x, y] = mul(px[x, y], f)
        if v >= 1:
            layer = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
            self.decor(ImageDraw.Draw(layer))
            if v == 2:
                layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
            im.paste(layer, (0 if v == 1 else 5, 0), layer)
        return im

    def decor(self, d):
        t = self.t
        k = t["decor"]
        gold = t["gold"]
        if k == "grille":
            d.rectangle([9, 6, 22, 26], fill=(12, 20, 40))
            for x in range(10, 22, 3):
                d.line([x, 6, x, 26], fill=(170, 170, 170))
            d.line([9, 15, 22, 15], fill=(85, 85, 85))
            d.rectangle([8, 5, 23, 6], fill=(85, 85, 85))
        elif k == "chain":
            for y in range(0, 28, 4):
                d.rectangle([14, y, 16, y + 2], outline=(150, 150, 150))
            d.rectangle([12, 28, 18, 33], fill=(85, 85, 85))
        elif k == "skull":
            d.ellipse([11, 14, 20, 22], fill=(240, 236, 214))
            d.rectangle([13, 21, 18, 25], fill=(240, 236, 214))
            d.rectangle([13, 17, 14, 18], fill=(0, 0, 0))
            d.rectangle([17, 17, 18, 18], fill=(0, 0, 0))
            d.line([8, 30, 24, 32], fill=(200, 196, 170))
            d.line([10, 32, 22, 29], fill=(200, 196, 170))
        elif k == "shelf":
            d.rectangle([5, 24, 27, 26], fill=(121, 93, 56))
            for i, col in enumerate(((231, 0, 0), (73, 146, 255), (60, 200, 90), (231, 0, 0))):
                x = 7 + i * 5
                d.rectangle([x, 18, x + 3, 23], fill=col)
                d.rectangle([x + 1, 16, x + 2, 18], fill=(230, 230, 230))
        elif k == "banner":
            col = t["rug"] or (186, 0, 0)
            d.rectangle([9, 0, 22, 26], fill=col)
            d.rectangle([9, 0, 22, 2], fill=gold)
            d.polygon([(9, 26), (22, 26), (16, 33)], fill=col)
            d.rectangle([14, 6, 17, 18], fill=gold)
            d.line([9, 3, 9, 25], fill=mul(col, 0.7))
        else:  # window: an arch of sky behind a gilt frame
            sky = (73, 146, 255) if t["bg"] != "void" else (60, 30, 90)
            d.rectangle([8, 4, 23, 34], fill=gold)
            d.rectangle([10, 8, 21, 34], fill=sky)
            d.pieslice([10, 3, 21, 15], 180, 360, fill=sky)
            d.line([16, 4, 16, 34], fill=gold)
            d.line([10, 21, 21, 21], fill=gold)

    # ---- structures ----
    def brick_course(self, d, y0, h, odd, shade=1.0):
        """One course of big stones (about one tile wide each), staggered on odd courses."""
        face = self.t["face"]
        base = mul(face, shade)
        d.rectangle([0, y0, TW - 1, y0 + h - 1], fill=mul(self.t["top"], 0.62 * shade))
        xs = [(-14, 29), (17, 29)] if odd else [(1, 29)]
        for x0, w in xs:
            d.rectangle([x0, y0, x0 + w - 1, y0 + h - 2], fill=base)
            d.line([x0, y0, x0 + w - 1, y0], fill=mul(base, 1.1))
            d.line([x0, y0 + h - 2, x0 + w - 1, y0 + h - 2], fill=mul(base, 0.76))
            rng = self.rng
            if rng.random() < 0.5:
                d.point((x0 + rng.randrange(2, max(3, w - 2)), y0 + rng.randrange(2, max(3, h - 3))), fill=mul(base, 0.7))

    def top_face(self, im, dy=0, cracks=False, rubble=False):
        t = self.t
        d = ImageDraw.Draw(im)
        y0, y1 = SLAB_TOP + dy, 47 + dy
        face = t["face"]
        top = tuple(int(a + (b - a) * 0.5) for a, b in zip(t["top"], face))
        top_lo, hi = mul(top, 0.8), mul(top, 1.18)
        self.brick_course(d, y1 + 1, TH - (y1 + 1), True)
        d.rectangle([TW - 3, y1 + 1, TW - 1, TH - 1], fill=mul(face, 0.55))
        d.rectangle([0, y0, TW - 1, y1], fill=top)
        d.line([0, y0, TW - 1, y0], fill=hi)
        d.line([0, y1, TW - 1, y1], fill=top_lo)
        rng = random.Random(self.v * 17 + 3)
        for _ in range(7):
            d.point((rng.randrange(1, 31), rng.randrange(y0 + 2, y1)), fill=top_lo)
        if t["rug"] and self.v >= 1:
            d.rectangle([0, y0 + 3, TW - 1, y0 + 6], fill=t["rug"])
            d.line([0, y0 + 3, TW - 1, y0 + 3], fill=t["gold"])
            d.line([0, y0 + 6, TW - 1, y0 + 6], fill=t["gold"])
        if cracks:
            d.line([9, y0, 12, y0 + 3, 10, y1], fill=top_lo)
            d.line([22, y0 + 1, 20, y1], fill=top_lo)
        if rubble:
            for _ in range(12):
                x, y = rng.randrange(2, 30), rng.randrange(y0 + 1, y1)
                d.rectangle([x, y, x + rng.randrange(1, 4), y + rng.randrange(1, 3)], fill=rng.choice([top_lo, hi, mul(top, 0.55)]))

    def floor_cell(self, dy=0, cracks=False, rubble=False):
        im = self.bg()
        self.top_face(im, dy, cracks, rubble)
        return im

    def wall_cell(self):
        face = self.t["face"]
        im = Image.new("RGB", (TW, TH), mul(self.t["top"], 0.62))
        d = ImageDraw.Draw(im)
        for r in range(4):
            self.brick_course(d, r * 16, 15, r % 2 == 1)
        d.rectangle([0, 60, TW, TH], fill=mul(self.t["top"], 0.62))
        return im

    def wall_side_cell(self):
        im = self.wall_cell()
        d = ImageDraw.Draw(im)
        face = self.t["face"]
        d.rectangle([TW - 9, 0, TW - 1, TH], fill=mul(face, 0.55))
        for y in range(15, TH, 16):
            d.line([TW - 9, y, TW - 1, y], fill=mul(self.t["top"], 0.5))
        d.line([TW - 9, 0, TW - 9, TH], fill=mul(self.t["top"], 0.45))
        return im

    def under_band(self):
        """Ceiling edge on the top row of a screen: one shallow course of stones."""
        im = Image.new("RGB", (TW, 5), mul(self.t["face"], 0.4))
        d = ImageDraw.Draw(im)
        self.brick_course(d, 0, 4, False, 0.9)
        d.line([0, 4, TW, 4], fill=mul(self.t["face"], 0.25))
        return im

    def pillar_cell(self):
        t = self.t
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        base = t["face"]
        gold = t["gold"] if t["column"] == "deco" else mul(base, 0.8)
        # Heavy square pier: lit front, shaded right side, capital and plinth.
        d.rectangle([7, 4, 24, 10], fill=gold)
        d.rectangle([7, 4, 24, 5], fill=mul(gold, 1.25))
        d.rectangle([9, 11, 22, SLAB_TOP - 5], fill=base)
        d.rectangle([9, 11, 11, SLAB_TOP - 5], fill=mul(base, 1.15))
        d.rectangle([18, 11, 22, SLAB_TOP - 5], fill=mul(base, 0.55))
        for y in range(19, SLAB_TOP - 5, 9):
            d.line([9, y, 22, y], fill=mul(base, 0.6))
        d.rectangle([7, SLAB_TOP - 6, 24, SLAB_TOP], fill=gold)
        d.line([7, SLAB_TOP - 6, 24, SLAB_TOP - 6], fill=mul(gold, 1.25))
        return im

    def torch_cell(self, frame):
        t = self.t
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        cx, fy = 16, 17
        o, m, c = t["flame"]
        px = im.load()
        for y in range(0, 30):
            for x in range(6, 26):
                dist = ((x - cx) ** 2 + ((y - 10) * 1.2) ** 2) ** 0.5
                if dist < 11:
                    f = (1 - dist / 11.0) * 0.3
                    r, g, b = px[x, y]
                    px[x, y] = (min(255, int(r + (o[0] - r) * f)), min(255, int(g + (o[1] - g) * f)), min(255, int(b + (o[2] - b) * f)))
        d.rectangle([cx - 1, fy + 4, cx + 1, fy + 14], fill=(85, 85, 85))
        d.rectangle([cx - 3, fy, cx + 3, fy + 4], fill=t["sconce"])
        d.line([cx - 3, fy, cx + 3, fy], fill=(255, 255, 255))
        rng = random.Random(frame * 5 + 1)
        h = [11, 13, 12, 14, 12, 13][frame % 6]
        sw = [0, 1, 0, -1, 0, 1][frame % 6]
        d.polygon([(cx - 3, fy), (cx - 2 + sw, fy - h // 2), (cx + sw * 2, fy - h), (cx + 2 + sw, fy - h // 2), (cx + 3, fy)], fill=o)
        d.polygon([(cx - 2, fy), (cx + sw, fy - h // 2 - 1), (cx + sw, fy - h + 3), (cx + 2, fy)], fill=m)
        d.polygon([(cx - 1, fy), (cx + sw, fy - h // 2 - 2), (cx + 1, fy)], fill=c)
        d.point((cx + sw * 3 + rng.randrange(-1, 2), fy - h - 1), fill=o)
        return im

    def spikes_cell(self, level):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        hs = [0, 5, 11, 17][level]
        base = FEET + 1
        for x in (6, 12, 18, 24):
            if hs == 0:
                d.point((x, base), fill=(85, 85, 85))
                d.point((x + 1, base), fill=(85, 85, 85))
            else:
                d.polygon([(x - 1, base), (x + 2, base), (x, base - hs)], fill=(190, 199, 207))
                d.line([(x, base), (x, base - hs)], fill=(255, 255, 255))
        return im

    def plate_cell(self, down):
        im = self.floor_cell()
        t = self.t
        d = ImageDraw.Draw(im)
        y = 44 if down else 42
        d.rectangle([8, y, 24, 46], fill=mul(t["top"], 1.3))
        d.line([8, y, 24, y], fill=(255, 255, 255) if not down else mul(t["top"], 0.6))
        d.line([8, 47, 24, 47], fill=mul(t["top"], 0.4))
        return im

    def gate_cell(self, k):
        t = self.t
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        bottom = int(7 + (SLAB_TOP - 7) * (1 - k / 8.0))
        d.rectangle([7, 0, 9, SLAB_TOP + 1], fill=(85, 85, 85))
        d.rectangle([22, 0, 24, SLAB_TOP + 1], fill=(85, 85, 85))
        for x in (11, 14, 17, 20):
            d.line([x, 7, x, bottom], fill=(170, 170, 170))
            d.line([x + 1, 7, x + 1, bottom], fill=(85, 85, 85))
            d.polygon([(x, bottom), (x + 1, bottom), (x, bottom + 3)], fill=(255, 255, 255))
        for y in range(bottom - 4, 8, -10):
            d.line([10, y, 21, y], fill=(121, 134, 150))
        d.rectangle([6, 0, 25, 6], fill=(121, 134, 150) if t["bg"] == "void" else t["face"])
        d.line([6, 6, 25, 6], fill=(48, 69, 89))
        d.line([6, 0, 25, 0], fill=(255, 255, 255))
        return im

    def chomper_cell(self, st):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        jt = [3, 8, 17, 28, 28, 28][st]
        steel, dark = (170, 170, 170), (85, 85, 85)
        d.rectangle([4, 0, 27, 1], fill=self.t["face"])
        d.line([4, 1, 27, 1], fill=dark)
        d.rectangle([6, 2, 25, jt], fill=steel)
        d.line([6, jt, 25, jt], fill=dark)
        for x in (7, 11, 15, 19, 23):
            d.polygon([(x, jt + 1), (x + 3, jt + 1), (x + 1, jt + 9)], fill=(255, 255, 255))
        d.rectangle([6, FEET - 4, 25, FEET], fill=dark)
        for x in (9, 13, 17, 21):
            d.polygon([(x, FEET - 4), (x + 3, FEET - 4), (x + 1, FEET - 13)], fill=(255, 255, 255))
        if st == 5:
            for x, y in ((9, 30), (14, 34), (19, 32), (22, 35), (12, 38)):
                d.rectangle([x, y, x + 2, y + 2], fill=(186, 0, 0))
            d.rectangle([8, FEET - 2, 24, FEET], fill=(231, 0, 0))
        return im

    def exit_cell(self, k):
        t = self.t
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        frame = t["door"] if t["bg"] == "void" else t["gold"]
        d.rectangle([2, 0, 29, SLAB_TOP + 1], fill=frame)
        d.rectangle([5, 4, 26, SLAB_TOP + 1], fill=(0, 0, 0))
        d.pieslice([5, 0, 26, 14], 180, 360, fill=(0, 0, 0))
        for i in range(5):
            y = SLAB_TOP - i * 6
            d.rectangle([6 + i * 3, y - 4, 26, y], fill=mul((255, 219, 120), 0.6 + 0.08 * i))
            d.line([6 + i * 3, y - 4, 26, y - 4], fill=(255, 255, 219))
        bottom = int(5 + (SLAB_TOP - 5) * (1 - k / 6.0))
        if bottom > 6:
            d.rectangle([6, 4, 25, bottom], fill=(85, 85, 85))
            for y in range(6, bottom, 4):
                d.line([6, y, 25, y], fill=(48, 69, 89))
            d.line([6, bottom, 25, bottom], fill=(190, 199, 207))
            for x in range(8, 25, 6):
                d.line([x, 4, x, bottom], fill=(121, 134, 150))
        return im

    def potion_cell(self, kind, frame):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        col = {"h": (231, 0, 0), "H": (231, 0, 0), "z": (73, 146, 255), "f": (60, 200, 90)}[kind]
        big = kind == "H"
        w, h = (12, 14) if big else (8, 9)
        cx, y1 = 16, FEET + 1
        y0 = y1 - h
        d.ellipse([cx - w // 2, y0, cx + w // 2, y1], fill=col)
        d.ellipse([cx - w // 2 + 2, y0 + 2, cx - w // 2 + 3, y0 + 3], fill=(255, 255, 255))
        d.rectangle([cx - 1, y0 - 4, cx + 1, y0 + 1], fill=(230, 230, 230))
        by = y0 + 3 + (frame * 3) % 4
        d.point((cx + 1 - frame, by), fill=(255, 255, 255))
        if frame:
            d.point((cx - 1, y0 - 6), fill=col)
            d.point((cx + 1, y0 - 8), fill=col)
        return im

    def sword_cell(self, frame):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        d.line([7, FEET, 25, FEET - 5], fill=(255, 255, 255), width=1)
        d.line([7, FEET + 1, 25, FEET - 4], fill=(190, 199, 207))
        d.rectangle([4, FEET - 2, 7, FEET + 1], fill=(186, 146, 0))
        d.line([9, FEET - 3, 9, FEET + 2], fill=(255, 255, 0), width=1)
        if frame:
            d.line([26, FEET - 11, 26, FEET - 5], fill=(255, 255, 255))
            d.line([23, FEET - 8, 29, FEET - 8], fill=(255, 255, 255))
        return im

    def mirror_cell(self, broken):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        gold = (186, 146, 0)
        d.rectangle([6, 1, 25, SLAB_TOP], fill=gold)
        d.rectangle([8, 3, 23, SLAB_TOP - 2], fill=(73, 146, 255) if not broken else (0, 0, 0))
        if not broken:
            for k in range(0, 30, 9):
                d.line([8, 3 + k + 8, 23, 3 + k - 4], fill=(190, 230, 255))
        else:
            for pts in (((8, 3), (14, 14), (9, 24)), ((23, 3), (17, 16), (22, 28)), ((12, 38), (16, 28), (21, 37))):
                d.polygon(pts, fill=(73, 146, 255))
        return im

    def shaft_cell(self):
        # Open shaft above a pit: a dark cavity rather than the lit back wall.
        im = self.bg()
        px = im.load()
        for y in range(TH):
            for x in range(TW):
                px[x, y] = mul(px[x, y], 0.3)
        return im

    def pit_cell(self):
        im = self.bg()
        px = im.load()
        for y in range(TH):
            f = max(0.0, 0.8 - y * 0.0125)
            for x in range(TW):
                px[x, y] = mul(px[x, y], f)
        return im


def build_theme(level):
    """name -> list of images (states). Variant 0 is a plain background, variants 1 and 2 carry decoration and rugs (the second mirrored)."""
    out = {}
    for v in range(3):
        p = Painter(level, v)
        s = f"_{v}"
        out["empty" + s] = [p.bg()]
        out["pit" + s] = [p.pit_cell()]
        out["shaft" + s] = [p.shaft_cell()]
        out["floor" + s] = [p.floor_cell()]
        out["pillar" + s] = [p.pillar_cell()]
        out["block" + s] = [p.wall_cell()]
        out["blockr" + s] = [p.wall_side_cell()]
        out["loose" + s] = [p.floor_cell(cracks=True), p.floor_cell(dy=-1, cracks=True), p.floor_cell(dy=1, cracks=True)]
        out["rubble" + s] = [p.floor_cell(rubble=True)]
        out["torch" + s] = [p.torch_cell(f) for f in range(6)]
        out["spikes" + s] = [p.spikes_cell(k) for k in range(4)]
        out["plate" + s] = [p.plate_cell(False), p.plate_cell(True)]
        out["gate" + s] = [p.gate_cell(k) for k in range(9)]
        out["chomper" + s] = [p.chomper_cell(k) for k in range(6)]
        out["exit" + s] = [p.exit_cell(k) for k in range(7)]
        for kind in "hHzf":
            out["potion_" + kind + s] = [p.potion_cell(kind, f) for f in range(2)]
        out["sword" + s] = [p.sword_cell(0), p.sword_cell(1)]
        out["mirror" + s] = [p.mirror_cell(False), p.mirror_cell(True)]
    out["under"] = [Painter(level, 0).under_band()]
    return out
