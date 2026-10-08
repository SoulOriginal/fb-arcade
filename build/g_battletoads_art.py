# Procedural art toolkit for the Battletoads build script: a supersampled vector canvas with cel-shaded
# blobs, a jointed biped rig shared by all humanoid characters, and packing of the result into
# transparent row-run sprites. Everything is drawn on a "virtual pixel" grid; one virtual pixel is 2x2
# screen pixels, which keeps the chunky console look and halves the per-tick compositing work.
import math, re
from PIL import Image, ImageDraw, ImageChops, ImageFilter

SS = 5
OUT = (26, 16, 34)


def shade(c, f=0.66):
    return (int(c[0] * f), int(c[1] * f * 0.98), int(c[2] * f * 1.04 if f < 1 else c[2] * f))


def light(c, f=0.42):
    return tuple(int(v + (255 - v) * f) for v in c)


def rot_pt(x, y, deg):
    r = math.radians(deg)
    return (x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r))


class Cv:
    def __init__(self, cw, ch, oy):
        # Canvas is symmetric around the anchor column so a horizontal mirror keeps the anchor in place.
        self.cw, self.ch, self.ox, self.oy = cw, ch, cw // 2, oy
        self.im = Image.new("RGBA", (cw * SS, ch * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def P(self, x, y):
        return ((self.ox + x) * SS, (self.oy + y) * SS)

    def poly(self, pts, col):
        self.d.polygon([self.P(*p) for p in pts], fill=col)

    def circ(self, x, y, r, col):
        px, py = self.P(x, y)
        self.d.ellipse((px - r * SS, py - r * SS, px + r * SS, py + r * SS), fill=col)

    def ellpts(self, cx, cy, rx, ry, rot=0, n=36):
        pts = []
        for i in range(n):
            t = 2 * math.pi * i / n
            x, y = rot_pt(rx * math.cos(t), ry * math.sin(t), rot)
            pts.append((cx + x, cy + y))
        return pts

    def ell(self, cx, cy, rx, ry, col, rot=0):
        self.poly(self.ellpts(cx, cy, rx, ry, rot), col)

    def line(self, p0, p1, w, col):
        self.d.line([self.P(*p0), self.P(*p1)], fill=col, width=max(1, int(w * SS)))
        self.circ(p0[0], p0[1], w / 2, col)
        self.circ(p1[0], p1[1], w / 2, col)

    def polyline(self, pts, w, col):
        for a, b in zip(pts, pts[1:]):
            self.line(a, b, w, col)

    def _cap(self, p0, r0, p1, r1, col):
        self.circ(p0[0], p0[1], r0, col)
        self.circ(p1[0], p1[1], r1, col)
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 0.01:
            return
        nx, ny = -dy / L, dx / L
        self.poly([(p0[0] + nx * r0, p0[1] + ny * r0), (p1[0] + nx * r1, p1[1] + ny * r1),
                   (p1[0] - nx * r1, p1[1] - ny * r1), (p0[0] - nx * r0, p0[1] - ny * r0)], col)

    def capsule(self, p0, r0, p1, r1, base, o=1.3, ol=OUT):
        # Three-tone cel shading by drawing shifted, shrinking copies; no clipping needed.
        self._cap(p0, r0 + o, p1, r1 + o, ol)
        self._cap(p0, r0, p1, r1, shade(base))
        self._cap((p0[0] - 0.14 * r0, p0[1] - 0.18 * r0), r0 * 0.84, (p1[0] - 0.14 * r1, p1[1] - 0.18 * r1), r1 * 0.84, base)
        self._cap((p0[0] - 0.34 * r0, p0[1] - 0.42 * r0), r0 * 0.3, (p1[0] - 0.34 * r1, p1[1] - 0.42 * r1), r1 * 0.3, light(base))

    def blob(self, cx, cy, rx, ry, base, rot=0, o=1.3, ol=OUT, hi=True):
        self.ell(cx, cy, rx + o, ry + o, ol, rot)
        self.ell(cx, cy, rx, ry, shade(base), rot)
        sx, sy = rot_pt(-0.12 * rx, -0.15 * ry, rot)
        self.ell(cx + sx, cy + sy, rx * 0.86, ry * 0.86, base, rot)
        if hi:
            sx, sy = rot_pt(-0.38 * rx, -0.45 * ry, rot)
            self.ell(cx + sx, cy + sy, rx * 0.34, ry * 0.3, light(base), rot)

    def paste(self, img, cx, cy):
        # img is a supersampled RGBA picture centred on (cx, cy) in virtual units.
        px, py = self.P(cx, cy)
        self.im.alpha_composite(img, (int(px - img.width / 2), int(py - img.height / 2)))

    def rotated(self, deg, about=(0, -40)):
        px, py = self.P(*about)
        self.im = self.im.rotate(deg, resample=Image.BICUBIC, center=(px, py))
        self.d = ImageDraw.Draw(self.im)


# ---- packing ------------------------------------------------------------------------------------------
_RUN = re.compile(rb"\xff+")


def tint(img, col, amount):
    # Blend all opaque pixels towards col (hit flash).
    a = img.getchannel("A")
    over = Image.new("RGBA", img.size, col + (255,))
    out = Image.blend(img, over, amount)
    out.putalpha(a)
    return out


def to_virtual(cv):
    im = cv.im.resize((cv.cw, cv.ch), Image.BOX)
    a = im.getchannel("A").point(lambda v: 255 if v >= 120 else 0)
    im.putalpha(a)
    return im


def pack565(im):
    # RGB565 pairs per virtual pixel, doubled horizontally so a run is directly copyable to the row buffer.
    r, g, b = im.convert("RGB").split()
    hi = ImageChops.add(r.point(lambda v: v & 0xF8), g.point(lambda v: v >> 5))
    lo = ImageChops.add(g.point(lambda v: ((v >> 2) & 7) << 5), b.point(lambda v: v >> 3))
    n = im.width * im.height
    out = bytearray(4 * n)
    lb, hb = lo.tobytes(), hi.tobytes()
    out[0::4] = lb
    out[1::4] = hb
    out[2::4] = lb
    out[3::4] = hb
    return bytes(out)


def to_sprite(im, ox, oy):
    # im: RGBA virtual image whose anchor is (ox, oy). Returns (top, left, rows) relative to the anchor;
    # rows is a tuple of tuples of (byte_offset, bytes) runs, one entry per scanline.
    w, h = im.size
    data = pack565(im)
    al = im.getchannel("A").tobytes()
    runs_rows = []
    xmin, first, last = w, None, None
    for y in range(h):
        row = al[y * w:(y + 1) * w]
        runs = [(m.start(), m.end()) for m in _RUN.finditer(row)]
        runs_rows.append(runs)
        if runs:
            if first is None:
                first = y
            last = y
            xmin = min(xmin, runs[0][0])
    if first is None:
        return (0, 0, ())
    rows = []
    for y in range(first, last + 1):
        rows.append(tuple(((s - xmin) * 4, data[(y * w + s) * 4:(y * w + e) * 4]) for s, e in runs_rows[y]))
    return (first - oy, xmin - ox, tuple(rows))


def sprite_pair(im, ox, oy):
    # Right-facing sprite and its mirror image.
    return [to_sprite(im, ox, oy), to_sprite(im.transpose(Image.FLIP_LEFT_RIGHT), ox, oy)]


def reanchor(im, ox, oy):
    # Move the bottom-centre of the opaque bbox to the anchor (for lying / rotated sprites).
    bb = im.getchannel("A").getbbox()
    if not bb:
        return im
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    cx = (bb[0] + bb[2]) // 2
    out.paste(im, (ox - cx, oy - bb[3]))
    return out
