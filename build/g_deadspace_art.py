# Build-time drawing kit for the Dead Space game: supersampled canvases, soft limbs, sprite packing.
# One virtual pixel (vpx) is 4x4 screen pixels; every sprite is stored at vpx resolution as
# (w, h, rgb565 bytes, mask bytes) and expanded to screen width lazily by the game.
import math
from array import array
from PIL import Image, ImageDraw, ImageFilter

SS = 4   # supersampling factor: drawing at 4x then box-filtering gives the soft, shaded look

# ---- palette ------------------------------------------------------------------------------------
FLESH = (142, 112, 96)
FLESH_D = (84, 56, 54)
FLESH_L = (178, 146, 124)
MUSCLE = (138, 30, 34)
MUSCLE_D = (76, 12, 18)
BONE = (214, 204, 168)
BONE_D = (130, 118, 92)
BLOOD = (104, 8, 12)
OUTLINE = (18, 10, 12)
SUIT = (74, 84, 96)
SUIT_D = (34, 40, 50)
SUIT_L = (130, 142, 156)
ORANGE = (214, 120, 30)
VISOR = (120, 230, 255)
STEEL = (92, 96, 104)
STEEL_D = (40, 42, 48)
STEEL_L = (160, 166, 176)


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


class Cv:
    """RGBA canvas addressed in vpx coordinates (floats), drawn at SS x resolution."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def p(self, pts):
        return [(x * SS, y * SS) for x, y in pts]

    def poly(self, pts, fill, outline=None, ow=0.7):
        self.d.polygon(self.p(pts), fill=fill + (255,))
        if outline:
            self.d.line(self.p(list(pts) + [pts[0]]), fill=outline + (255,), width=max(1, int(ow * SS)), joint="curve")

    def ell(self, cx, cy, rx, ry, fill, outline=None, ow=0.7):
        box = [(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS]
        if outline:
            self.d.ellipse(box, fill=outline + (255,))
            k = ow
            box = [(cx - rx + k) * SS, (cy - ry + k) * SS, (cx + rx - k) * SS, (cy + ry - k) * SS]
        self.d.ellipse(box, fill=fill + (255,))

    def rect(self, x0, y0, x1, y1, fill, outline=None):
        self.d.rectangle([x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1], fill=fill + (255,),
                         outline=(outline + (255,)) if outline else None)

    def line(self, pts, col, w):
        self.d.line(self.p(pts), fill=col + (255,), width=max(1, int(w * SS)), joint="curve")
        r = w * SS / 2
        for x, y in (pts[0], pts[-1]):
            self.d.ellipse([x * SS - r, y * SS - r, x * SS + r, y * SS + r], fill=col + (255,))

    def limb(self, pts, w, base, dark=None, light=None, taper=None):
        """Soft tube: dark outline pass, base pass, light highlight pass shifted up-left."""
        dark = dark or shade(base, 0.45)
        light = light or shade(base, 1.45)
        self.line(pts, dark, w)
        self.line(pts, base, max(0.8, w - 1.4))
        sh = [(x - w * 0.14, y - w * 0.14) for x, y in pts]
        self.line(sh, light, max(0.6, w * 0.30))

    def glow(self, cx, cy, r, col, strength=1.0):
        g = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for i in range(8, 0, -1):
            rr = r * SS * i / 8
            a = int(255 * strength * (1 - i / 8) ** 1.5 * 0.55)
            gd.ellipse([cx * SS - rr, cy * SS - rr, cx * SS + rr, cy * SS + rr], fill=col + (a,))
        self.im = Image.alpha_composite(self.im, g)
        self.d = ImageDraw.Draw(self.im)

    def done(self):
        return downsample(self.im)


def downsample(im):
    w, h = im.width // SS, im.height // SS
    return im.resize((w, h), Image.BOX)


def rgb565_bytes(img):
    """RGBA vpx image -> (w, h, px bytes, mask bytes). Alpha under 110 is transparent."""
    img = img.convert("RGBA")
    w, h = img.size
    px = array("H")
    mask = bytearray()
    for r, g, b, a in zip(*[iter(img.tobytes())] * 4):
        if a >= 110:
            px.append((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
            mask.append(1)
        else:
            px.append(0)
            mask.append(0)
    return (w, h, px.tobytes(), bytes(mask))


def crop_pack(img, pad=0):
    """Trim transparent border; returns (packed sprite, (left, top)) so anchors can be kept."""
    a = img.getchannel("A").point(lambda v: 255 if v >= 110 else 0)
    bb = a.getbbox()
    if bb is None:
        return rgb565_bytes(Image.new("RGBA", (1, 1), (0, 0, 0, 0))), (0, 0)
    bb = (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))
    return rgb565_bytes(img.crop(bb)), (bb[0], bb[1])


def tint_rgba(img, mul=(1, 1, 1), add=(0, 0, 0)):
    r, g, b, a = img.split()
    r = r.point(lambda v: max(0, min(255, int(v * mul[0] + add[0]))))
    g = g.point(lambda v: max(0, min(255, int(v * mul[1] + add[1]))))
    b = b.point(lambda v: max(0, min(255, int(v * mul[2] + add[2]))))
    return Image.merge("RGBA", (r, g, b, a))


def tint_rgb(img, mul, add=(0, 0, 0)):
    return tint_rgba(img.convert("RGBA"), mul, add).convert("RGB")


def pack_rgb(img):
    """Opaque RGB strip -> bytes expanded 4x horizontally (matches the screen scale), row-major."""
    img = img.convert("RGB")
    w, h = img.size
    px = array("H")
    for r, g, b in zip(*[iter(img.tobytes())] * 3):
        px.append((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
    src = px.tobytes()
    out = bytearray(len(src) * 4)
    for k in range(4):
        out[2 * k::8] = src[0::2]
        out[2 * k + 1::8] = src[1::2]
    return (w, h, bytes(out), b"")


def splat(cv, cx, cy, r, col, n=10, seed=0):
    """Blood/gore splatter blobs."""
    import random
    rnd = random.Random(seed)
    for _ in range(n):
        a = rnd.random() * 6.28
        d = rnd.random() * r
        rr = rnd.random() * r * 0.35 + 0.5
        cv.ell(cx + math.cos(a) * d, cy + math.sin(a) * d, rr, rr * 0.8, col)
