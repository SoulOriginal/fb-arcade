# Build-time only: procedural tile art, one 32x63 logical cell per tile state, in two themes
# (dungeon: blue-grey stone, palace: beige stone with gold trim).
import random
from PIL import Image, ImageDraw

TW, TH = 32, 63
FEET = 54          # y of the standing line inside a cell: the front edge of the slab top face
SLAB_TOP = 50      # top face of the slab spans SLAB_TOP..FEET, the front face FEET+1..TH-1

THEMES = {
    "dungeon": dict(bricks=[(68, 76, 112), (60, 68, 102), (74, 82, 118), (54, 62, 94)], mortar=(26, 30, 48),
                    hi=(96, 106, 146), top=(166, 168, 196), top2=(142, 146, 176), front=(104, 108, 142),
                    front2=(84, 88, 120), seam=(40, 44, 68), edge=(204, 206, 226), trim=(150, 150, 190),
                    deco=(24, 26, 44), deco2=(46, 50, 78), pillar=(150, 154, 186), pillar_d=(96, 100, 134),
                    pillar_l=(190, 194, 220), block=[(88, 96, 132), (80, 88, 124)], block_m=(30, 34, 54),
                    glow=(255, 190, 90)),
    "palace": dict(bricks=[(206, 186, 148), (196, 176, 140), (212, 192, 154), (188, 168, 132)], mortar=(120, 100, 74),
                   hi=(238, 222, 186), top=(240, 228, 192), top2=(222, 206, 168), front=(176, 154, 114),
                   front2=(150, 128, 92), seam=(104, 84, 60), edge=(252, 244, 214), trim=(226, 186, 66),
                   deco=(40, 52, 130), deco2=(180, 40, 44), pillar=(232, 216, 176), pillar_d=(168, 146, 104),
                   pillar_l=(250, 240, 208), block=[(224, 206, 168), (214, 196, 158)], block_m=(130, 108, 80),
                   glow=(255, 214, 120)),
}


def mul(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


class Painter:
    def __init__(self, theme, variant):
        self.t = THEMES[theme]
        self.theme = theme
        self.v = variant
        self.rng = random.Random(variant * 977 + (1 if theme == "palace" else 0))

    def wall(self):
        t, v = self.t, self.v
        im = Image.new("RGB", (TW, TH), t["mortar"])
        d = ImageDraw.Draw(im)
        for r in range(9):
            y0 = r * 7
            off = 8 if (r + v) % 2 else 0
            for k in range(-1, 3):
                x0 = k * 16 + off
                col = t["bricks"][self.rng.randrange(4)]
                shade = 0.94 + 0.012 * ((r * 3 + k * 5 + v) % 7)
                col = mul(col, shade)
                d.rectangle([x0, y0, x0 + 14, y0 + 5], fill=col)
                d.line([x0, y0, x0 + 14, y0], fill=t["hi"])
                for _ in range(2):
                    px, py = x0 + self.rng.randrange(1, 14), y0 + self.rng.randrange(1, 6)
                    d.point((px, py), fill=mul(col, 0.86))
        if v == 3:
            self.decor(d)
        px = im.load()
        for y, f in enumerate((0.5, 0.66, 0.8, 0.92)):
            for x in range(TW):
                px[x, y] = mul(px[x, y], f)
        return im

    def pit_cell(self):
        # Bottomless drop below the lowest row: the wall fades to black so the gap reads as deadly.
        im = self.wall()
        px = im.load()
        for y in range(TH):
            f = max(0.0, 0.75 - y * 0.0125)
            for x in range(TW):
                px[x, y] = mul(px[x, y], f)
        return im

    def decor(self, d):
        t = self.t
        if self.theme == "dungeon":
            d.rectangle([8, 12, 23, 49], fill=t["deco"])
            d.rectangle([10, 10, 21, 12], fill=t["deco2"])
            d.rectangle([8, 14, 8, 49], fill=t["deco2"])
            d.rectangle([23, 14, 23, 49], fill=t["deco2"])
            d.ellipse([8, 8, 23, 22], fill=t["deco"])
            d.arc([8, 8, 23, 22], 180, 360, fill=t["deco2"])
        else:
            d.rectangle([9, 5, 22, 40], fill=t["deco"])
            d.rectangle([9, 5, 22, 7], fill=t["trim"])
            d.polygon([(9, 40), (22, 40), (16, 47)], fill=t["deco"])
            d.rectangle([13, 12, 18, 30], fill=t["trim"])
            d.rectangle([14, 14, 17, 28], fill=t["deco2"])
            d.line([9, 5, 9, 40], fill=t["trim"])
            d.line([22, 5, 22, 40], fill=t["trim"])

    def slab(self, im, dy=0, cracks=False, rubble=False):
        t = self.t
        d = ImageDraw.Draw(im)
        top0, feet = SLAB_TOP + dy, FEET + dy
        d.rectangle([0, top0, TW - 1, feet], fill=t["top"])
        d.line([0, top0, TW - 1, top0], fill=t["edge"])
        for x in range(0, TW, 8):
            d.point((x + (self.v * 3) % 5, top0 + 2), fill=t["top2"])
        d.line([0, feet, TW - 1, feet], fill=t["top2"])
        d.rectangle([0, feet + 1, TW - 1, TH - 1], fill=t["front"])
        d.line([0, feet + 1, TW - 1, feet + 1], fill=t["trim"] if self.theme == "palace" else t["top2"])
        d.line([0, TH - 1, TW - 1, TH - 1], fill=t["seam"])
        mid = feet + 5
        d.line([0, mid, TW - 1, mid], fill=t["front2"])
        d.line([0, feet + 1, 0, TH - 1], fill=t["seam"])
        d.line([16 + (self.v % 2) * 4, feet + 1, 16 + (self.v % 2) * 4, mid], fill=t["seam"])
        d.line([5, mid, 5, TH - 1], fill=t["seam"])
        if self.theme == "palace":
            d.line([0, feet + 3, TW - 1, feet + 3], fill=mul(t["trim"], 0.8))
        if cracks:
            d.line([9, top0, 12, top0 + 2, 10, feet, 14, feet + 4], fill=t["seam"])
            d.line([22, top0 + 1, 20, feet, 23, feet + 3], fill=t["seam"])
        if rubble:
            rng = random.Random(5 + self.v)
            for _ in range(14):
                x, y = rng.randrange(2, 30), rng.randrange(top0 + 1, feet)
                d.rectangle([x, y, x + rng.randrange(1, 4), y + rng.randrange(1, 3)], fill=rng.choice([t["front"], t["top2"], t["seam"], t["edge"]]))

    def floor_cell(self, dy=0, cracks=False, rubble=False):
        im = self.wall()
        self.slab(im, dy, cracks, rubble)
        return im

    def pillar_cell(self):
        im = self.floor_cell()
        t = self.t
        d = ImageDraw.Draw(im)
        d.rectangle([8, 0, 23, 5], fill=t["pillar"])
        d.line([8, 5, 23, 5], fill=t["pillar_d"])
        d.rectangle([8, 0, 23, 0], fill=t["pillar_l"])
        d.rectangle([11, 6, 20, 45], fill=t["pillar"])
        d.rectangle([11, 6, 13, 45], fill=t["pillar_l"])
        d.rectangle([18, 6, 20, 45], fill=t["pillar_d"])
        for y in (14, 24, 34):
            d.line([11, y, 20, y], fill=t["pillar_d"])
        d.rectangle([8, 45, 23, SLAB_TOP + 1], fill=t["pillar"])
        d.line([8, 45, 23, 45], fill=t["pillar_l"])
        d.line([8, SLAB_TOP + 1, 23, SLAB_TOP + 1], fill=t["pillar_d"])
        if self.theme == "palace":
            d.rectangle([8, 3, 23, 3], fill=t["trim"])
        return im

    def block_cell(self):
        t = self.t
        im = Image.new("RGB", (TW, TH), t["block_m"])
        d = ImageDraw.Draw(im)
        rng = random.Random(self.v * 31 + 7)
        for r in range(5):
            y0 = r * 13
            off = 10 if (r + self.v) % 2 else 0
            for k in range(-1, 3):
                x0 = k * 20 + off
                col = mul(t["block"][rng.randrange(2)], 0.9 + 0.04 * rng.randrange(4))
                d.rectangle([x0, y0, x0 + 18, y0 + 11], fill=col)
                d.line([x0, y0, x0 + 18, y0], fill=mul(col, 1.2))
                d.line([x0, y0 + 11, x0 + 18, y0 + 11], fill=mul(col, 0.7))
        d.line([0, 0, 0, TH], fill=t["block_m"])
        d.line([TW - 1, 0, TW - 1, TH], fill=t["block_m"])
        return im

    def torch_cell(self, frame):
        im = self.floor_cell()
        t = self.t
        d = ImageDraw.Draw(im)
        rng = random.Random(frame * 13 + self.v)
        # glow on the bricks around the flame
        px = im.load()
        for y in range(6, 34):
            for x in range(4, 28):
                dist = ((x - 16) ** 2 + ((y - 20) * 1.1) ** 2) ** 0.5
                if dist < 13:
                    f = (1 - dist / 13) * (0.34 + 0.05 * (frame % 3))
                    r, g, b = px[x, y]
                    gr, gg, gb = t["glow"]
                    px[x, y] = (min(255, int(r + (gr - r) * f)), min(255, int(g + (gg - g) * f)), min(255, int(b + (gb - b) * f)))
        d.rectangle([14, 27, 18, 36], fill=(54, 40, 30))          # sconce
        d.rectangle([12, 25, 20, 27], fill=(86, 64, 40))
        d.line([13, 25, 13, 27], fill=(130, 100, 60))
        sway = [0, 1, 0, -1, 0, 1][frame % 6]
        h = [9, 11, 10, 12, 10, 11][frame % 6]
        pts = [(16 - 4, 25), (16 - 3 + sway, 25 - h // 2), (16 + sway * 2, 25 - h), (16 + 3 + sway, 25 - h // 2), (16 + 4, 25)]
        d.polygon(pts, fill=(224, 80, 20))
        pts2 = [(16 - 3, 25), (16 - 2 + sway, 25 - h // 2 + 1), (16 + sway * 2, 25 - h + 3), (16 + 2 + sway, 25 - h // 2 + 1), (16 + 3, 25)]
        d.polygon(pts2, fill=(255, 168, 30))
        d.polygon([(16 - 1, 25), (16 + sway, 25 - h // 2 - 1), (16 + 1, 25)], fill=(255, 240, 150))
        if frame % 2 == 0:
            d.point((16 + sway * 3, 25 - h - 1), fill=(255, 200, 60))
        return im

    def spikes_cell(self, level):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        hs = [0, 5, 11, 17][level]
        for x in (5, 11, 17, 23):
            if hs == 0:
                d.rectangle([x, FEET - 1, x + 2, FEET - 1], fill=(30, 30, 40))
            else:
                d.polygon([(x, FEET - 1), (x + 3, FEET - 1), (x + 1, FEET - 1 - hs)], fill=(206, 212, 226))
                d.line([(x + 1, FEET - 1), (x + 1, FEET - 1 - hs)], fill=(246, 248, 255))
                d.line([(x + 3, FEET - 1), (x + 1, FEET - 1 - hs)], fill=(110, 116, 136))
        return im

    def plate_cell(self, down):
        im = self.floor_cell()
        t = self.t
        d = ImageDraw.Draw(im)
        y = FEET - (0 if down else 3)
        d.rectangle([8, y - 1, 24, FEET], fill=mul(t["edge"], 0.85 if not down else 0.7))
        d.line([8, y - 1, 24, y - 1], fill=(255, 255, 255) if not down else t["top2"])
        d.line([8, FEET, 24, FEET], fill=t["seam"])
        return im

    def gate_cell(self, k):
        t = self.t
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        bottom = int(7 + (SLAB_TOP - 7) * (1 - k / 8.0))
        d.rectangle([9, 0, 10, SLAB_TOP], fill=mul(t["pillar_d"], 0.85))
        d.rectangle([21, 0, 22, SLAB_TOP], fill=mul(t["pillar_d"], 0.85))
        for x in (12, 15, 18):
            d.rectangle([x, 7, x + 1, bottom], fill=(150, 156, 172))
            d.line([x, 7, x, bottom], fill=(212, 218, 232))
            d.polygon([(x, bottom), (x + 1, bottom), (x, bottom + 3), (x + 1, bottom + 3)], fill=(110, 114, 130))
        for y in range(bottom - 3, 8, -9):
            d.rectangle([11, y, 20, y + 1], fill=(120, 126, 142))
        d.rectangle([7, 0, 24, 6], fill=t["pillar"])
        d.line([7, 6, 24, 6], fill=t["pillar_d"])
        d.line([7, 0, 24, 0], fill=t["pillar_l"])
        return im

    def chomper_cell(self, st):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        jt = [6, 14, 27, 40, 40, 40][st]
        steel, dark = (176, 182, 198), (92, 98, 116)
        blood = st == 5
        d.rectangle([4, 0, 27, 4], fill=self.t["pillar"])
        d.line([4, 4, 27, 4], fill=self.t["pillar_d"])
        d.rectangle([6, 5, 25, jt], fill=steel)
        d.line([6, jt, 25, jt], fill=dark)
        for x in (7, 11, 15, 19, 23):
            d.polygon([(x, jt + 1), (x + 3, jt + 1), (x + 1, jt + 9)], fill=(236, 240, 250) if not blood else (210, 220, 230))
            d.line([(x + 3, jt + 1), (x + 1, jt + 9)], fill=dark)
        d.rectangle([6, FEET - 5, 25, FEET - 1], fill=dark)
        for x in (9, 13, 17, 21):
            d.polygon([(x, FEET - 5), (x + 3, FEET - 5), (x + 1, FEET - 14)], fill=(226, 230, 242))
            d.line([(x + 3, FEET - 5), (x + 1, FEET - 14)], fill=dark)
        if blood:
            for x, y in ((9, 42), (14, 46), (19, 44), (22, 47), (12, 50)):
                d.rectangle([x, y, x + 2, y + 2], fill=(170, 20, 24))
            d.rectangle([8, FEET - 2, 24, FEET - 1], fill=(130, 16, 20))
        return im

    def exit_cell(self, k):
        t = self.t
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        d.rectangle([2, 4, 29, SLAB_TOP + 1], fill=t["pillar"])
        d.rectangle([2, 4, 29, 6], fill=t["pillar_l"])
        d.rectangle([5, 9, 26, SLAB_TOP + 1], fill=(20, 18, 26))
        d.pieslice([5, 3, 26, 22], 180, 360, fill=(20, 18, 26))
        # warm stairs behind the door, visible once it is open
        for i in range(7):
            y = SLAB_TOP - i * 5
            col = mul((255, 214, 120), 0.62 + 0.06 * i)
            d.rectangle([6 + i * 2, y - 3, 26, y], fill=col)
            d.line([6 + i * 2, y - 3, 26, y - 3], fill=(255, 244, 190))
        bottom = int(9 + (SLAB_TOP - 9) * (1 - k / 6.0))
        if bottom > 10:
            d.rectangle([6, 9, 25, bottom], fill=(86, 88, 104))
            for y in range(10, bottom, 4):
                d.line([6, y, 25, y], fill=(52, 54, 68))
            d.line([6, bottom, 25, bottom], fill=(150, 154, 170))
            for x in range(8, 25, 6):
                d.line([x, 9, x, bottom], fill=(116, 120, 136))
        d.rectangle([2, 4, 4, SLAB_TOP + 1], fill=t["pillar_d"])
        d.rectangle([27, 4, 29, SLAB_TOP + 1], fill=t["pillar_d"])
        if self.theme == "palace":
            d.line([2, 4, 29, 4], fill=t["trim"])
        return im

    def potion_cell(self, kind, frame):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        col = {"h": (214, 40, 52), "H": (222, 36, 60), "z": (64, 92, 232), "f": (64, 204, 96)}[kind]
        big = kind == "H"
        w, h = (12, 14) if big else (9, 10)
        cx = 16
        y1 = FEET - 1
        y0 = y1 - h
        d.ellipse([cx - w // 2, y0, cx + w // 2, y1], fill=col)
        d.ellipse([cx - w // 2 + 2, y0 + 2, cx - w // 2 + 4, y0 + 4], fill=mul(col, 1.5))
        d.rectangle([cx - 2, y0 - 4, cx + 1, y0 + 1], fill=(220, 224, 236))
        d.rectangle([cx - 3, y0 - 5, cx + 2, y0 - 4], fill=(120, 80, 50))
        d.line([cx - w // 2, y1, cx + w // 2, y1], fill=mul(col, 0.55))
        by = y0 + 3 + (frame * 3) % 5
        d.point((cx + 1 - frame, by), fill=(255, 255, 255))
        d.point((cx + 2, by + 3 - frame), fill=mul(col, 1.7))
        if frame:
            d.point((cx - 1, y0 - 6), fill=mul(col, 1.7))
        return im

    def sword_cell(self, frame):
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        d.line([6, FEET - 3, 24, FEET - 9], fill=(214, 224, 238), width=2)
        d.line([6, FEET - 4, 24, FEET - 10], fill=(250, 252, 255))
        d.rectangle([3, FEET - 5, 6, FEET - 2], fill=(150, 100, 40))
        d.line([8, FEET - 7, 9, FEET - 1], fill=(226, 180, 60), width=2)
        if frame:
            d.line([25, FEET - 14, 25, FEET - 6], fill=(255, 255, 255))
            d.line([21, FEET - 10, 29, FEET - 10], fill=(255, 255, 255))
        return im

    def mirror_cell(self, broken):
        t = self.t
        im = self.floor_cell()
        d = ImageDraw.Draw(im)
        gold = (226, 186, 66)
        d.rectangle([6, 4, 25, SLAB_TOP], fill=gold)
        d.rectangle([8, 6, 23, SLAB_TOP - 2], fill=(140, 196, 232) if not broken else (24, 26, 40))
        if not broken:
            for k in range(0, 40, 9):
                d.line([8, 6 + k + 8, 23, 6 + k - 4], fill=(214, 238, 255))
            d.line([10, 8, 10, SLAB_TOP - 4], fill=(190, 226, 250))
        else:
            for pts in (((8, 6), (14, 18), (9, 30)), ((23, 6), (17, 20), (22, 34)), ((12, 48), (16, 36), (21, 47))):
                d.polygon(pts, fill=(150, 200, 235))
            d.line([(8, 6), (16, 26), (23, 50)], fill=(10, 10, 16))
        return im


def build_theme(theme):
    """name -> list of images (states). Wall variants 0..3 are baked into the name suffix."""
    out = {}
    for v in range(4):
        p = Painter(theme, v)
        s = f"_{v}"
        out["empty" + s] = [p.wall()]
        out["pit" + s] = [p.pit_cell()]
        out["floor" + s] = [p.floor_cell()]
        out["pillar" + s] = [p.pillar_cell()]
        out["block" + s] = [p.block_cell()]
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
    return out
