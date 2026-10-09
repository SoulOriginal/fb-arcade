# Build-time drawing helpers for the Isaac game: supersampled PIL canvas, run-length sprite packing, colour helpers.
# Sprites are stored as (w, h, rows) where rows[y] is a tuple of (x, rgb565-bytes) opaque runs, so the runtime can
# composite them over any background with plain slice assignments.
import math, random
from array import array
from PIL import Image, ImageDraw

SS = 4
OUT = (42, 24, 30, 255)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3]) + (255,)


def mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)) + (255,)


class Pen:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def ell(self, cx, cy, rx, ry, fill=None, outline=None, w=0):
        self.d.ellipse([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS], fill=fill, outline=outline,
                       width=max(0, int(w * SS)))

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=0, r=0):
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, fill=fill, outline=outline,
                                 width=max(0, int(w * SS)))

    def poly(self, pts, fill=None, outline=None, w=0):
        p = [(x * SS, y * SS) for x, y in pts]
        self.d.polygon(p, fill=fill)
        if outline:
            self.d.line(p + [p[0]], fill=outline, width=max(1, int(w * SS)), joint="curve")

    def line(self, pts, fill, w):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=max(1, int(w * SS)), joint="curve")

    def arc(self, cx, cy, rx, ry, a0, a1, fill, w):
        self.d.arc([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS], a0, a1, fill=fill,
                   width=max(1, int(w * SS)))

    def blob(self, cx, cy, rx, ry, fill, outline=OUT, ow=2.2):
        # outlined ellipse: the outline is drawn as a slightly larger dark ellipse underneath
        self.ell(cx, cy, rx + ow, ry + ow, fill=outline)
        self.ell(cx, cy, rx, ry, fill=fill)

    def done(self):
        im = self.img.convert("RGBa").resize((self.w, self.h), Image.BOX).convert("RGBA")
        return im


def flip(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


def rle(im, alpha_cut=110):
    # Opaque runs per row. Fully transparent rows give empty tuples.
    w, h = im.size
    px = array("H", ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3) for r, g, b, a in im.getdata()))
    al = [a >= alpha_cut for r, g, b, a in im.getdata()]
    rows = []
    for y in range(h):
        runs = []
        x = 0
        base = y * w
        while x < w:
            if al[base + x]:
                x0 = x
                while x < w and al[base + x]:
                    x += 1
                runs.append((x0, px[base + x0:base + x].tobytes()))
            else:
                x += 1
        rows.append(tuple(runs))
    return (w, h, rows)


def opaque(im):
    # (w, h, bytes) for load_bundle's own sprite type: used for full backgrounds
    w, h = im.size
    it = iter(im.convert("RGB").tobytes())
    a = array("H", ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3) for r, g, b in zip(it, it, it)))
    return (w, h, a.tobytes())
