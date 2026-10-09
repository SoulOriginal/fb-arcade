# Build-time only: a 2D skeletal rig that draws side-view fighters (prince, guards, skeleton, shadow) at
# 320x200 logical resolution. Poses are joint angles, so in-between frames are plain interpolation - this is
# what gives the rotoscope-like fluidity without any hand-drawn bitmaps.
import math
from PIL import Image, ImageDraw

SS = 4                       # supersampling factor before the down-scale to logical pixels
CW, CH = 112, 112            # logical canvas
GX, GY = 56, 96              # hip x anchor and ground line inside the canvas

NAMES = ["lean", "head", "ra_s", "ra_e", "fa_s", "fa_e", "rl_t", "rl_k", "fl_t", "fl_k", "swa", "swl", "item"]
STAND = dict(lean=2, head=0, ra_s=-6, ra_e=10, fa_s=7, fa_e=12, rl_t=-4, rl_k=0, fl_t=5, fl_k=-2,
             swa=0, swl=0, item=0)


def P(**kw):
    d = dict(STAND)
    for k, v in kw.items():
        if k not in d:
            raise KeyError(k)
        d[k] = v
    return d


def mirror_limbs(p):
    # Swaps near and far limbs: the second half of every walk/run cycle.
    q = dict(p)
    for a, b in (("ra_s", "fa_s"), ("ra_e", "fa_e"), ("rl_t", "fl_t"), ("rl_k", "fl_k")):
        q[a], q[b] = p[b], p[a]
    return q


def lerp_pose(a, b, t):
    # Smoothstep keeps limbs from snapping at key poses.
    t = t * t * (3 - 2 * t)
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


def sequence(keys, loop=False):
    """keys: [(pose, frames_to_next), ...] -> list of poses. Last key is appended unless the cycle loops."""
    out = []
    n = len(keys)
    for i, (p, f) in enumerate(keys):
        nxt = keys[(i + 1) % n][0] if (loop or i + 1 < n) else None
        if nxt is None:
            out.append(dict(p))
            continue
        for j in range(f):
            out.append(lerp_pose(p, nxt, j / f))
    return out


class Palette:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


PRINCE = Palette(kind="human", shirt=(238, 238, 244), pants=(226, 226, 236), vest=(176, 48, 40), sash=(196, 52, 44),
                 skin=(224, 172, 122), turban=(248, 248, 252), shoes=(132, 78, 44), hair=(34, 28, 28),
                 outline=(46, 34, 44), girth=1.0, scale=1.0, mustache=False, blade=(214, 224, 236))
GUARD_BLUE = Palette(kind="human", shirt=(52, 70, 150), pants=(206, 200, 184), vest=(30, 36, 86), sash=(214, 176, 60),
                     skin=(176, 124, 86), turban=(46, 62, 138), shoes=(70, 46, 30), hair=(24, 20, 20),
                     outline=(24, 20, 32), girth=1.15, scale=1.03, mustache=True, blade=(206, 214, 226))
GUARD_RED = Palette(kind="human", shirt=(166, 40, 40), pants=(196, 188, 170), vest=(90, 20, 24), sash=(214, 176, 60),
                    skin=(176, 124, 86), turban=(150, 34, 36), shoes=(70, 46, 30), hair=(24, 20, 20),
                    outline=(32, 14, 18), girth=1.15, scale=1.03, mustache=True, blade=(206, 214, 226))
GUARD_FAT = Palette(kind="human", shirt=(150, 96, 40), pants=(180, 170, 140), vest=(100, 56, 20), sash=(210, 60, 50),
                    skin=(190, 134, 94), turban=(190, 150, 60), shoes=(70, 46, 30), hair=(24, 20, 20),
                    outline=(40, 26, 12), girth=1.85, scale=1.14, mustache=True, blade=(206, 214, 226))
SKELETON = Palette(kind="skel", bone=(228, 226, 204), dark=(30, 28, 30), outline=(20, 18, 24), girth=1.0, scale=1.03,
                   blade=(190, 196, 206))
SHADOW = Palette(kind="human", shirt=(24, 26, 56), pants=(20, 22, 48), vest=(14, 16, 36), sash=(40, 44, 90),
                 skin=(34, 36, 70), turban=(28, 30, 62), shoes=(14, 14, 30), hair=(10, 10, 20),
                 outline=(96, 110, 200), girth=1.0, scale=1.0, mustache=False, blade=(120, 140, 230))

L_THIGH, L_SHIN, L_TORSO, L_ARM, L_FORE = 10.5, 10.5, 15.0, 7.2, 7.2
HEAD_R = 4.9


def _dir_down(a):
    r = math.radians(a)
    return math.sin(r), math.cos(r)


def skeleton_points(p, sc):
    """Joint positions relative to the hip in logical px (y down)."""
    lt, ls, tor, la, lf = (v * sc for v in (L_THIGH, L_SHIN, L_TORSO, L_ARM, L_FORE))
    pts = {"hip": (0.0, 0.0)}
    lr = math.radians(p["lean"])
    sh = (tor * math.sin(lr), -tor * math.cos(lr))
    pts["sho"] = sh
    hr = math.radians(p["lean"] + p["head"])
    hl = (3.2 + HEAD_R) * sc
    pts["head"] = (sh[0] + hl * math.sin(hr), sh[1] - hl * math.cos(hr))
    for side in ("r", "f"):
        t, k = p[side + "l_t"], p[side + "l_k"]
        dx, dy = _dir_down(t)
        kn = (lt * dx, lt * dy)
        dx, dy = _dir_down(t + k)
        fo = (kn[0] + ls * dx, kn[1] + ls * dy)
        a = math.radians(t + k)
        toe = (fo[0] + 5.5 * sc * math.cos(a), fo[1] - 5.5 * sc * math.sin(a))
        heel = (fo[0] - 1.5 * sc * math.cos(a), fo[1] + 1.5 * sc * math.sin(a))
        pts[side + "knee"], pts[side + "foot"], pts[side + "toe"], pts[side + "heel"] = kn, fo, toe, heel
        s, e = p[side + "a_s"], p[side + "a_e"]
        dx, dy = _dir_down(s)
        el = (sh[0] + la * dx, sh[1] + la * dy)
        dx, dy = _dir_down(s + e)
        wr = (el[0] + lf * dx, el[1] + lf * dy)
        pts[side + "elb"], pts[side + "wri"] = el, wr
    return pts


def _poly_limb(d, p0, p1, w0, w1, col):
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / n, dx / n
    d.polygon([(x0 + nx * w0 / 2, y0 + ny * w0 / 2), (x1 + nx * w1 / 2, y1 + ny * w1 / 2),
               (x1 - nx * w1 / 2, y1 - ny * w1 / 2), (x0 - nx * w0 / 2, y0 - ny * w0 / 2)], fill=col)
    for (x, y, w) in ((x0, y0, w0), (x1, y1, w1)):
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=col)


def render(p, pal, flip=False):
    """Returns (RGBA logical image CWxCH, hang_height). Ground line at GY, hip x at GX."""
    sc = pal.scale
    pts = skeleton_points(p, sc)
    low = max(max(pts[k][1] for k in ("rfoot", "ffoot", "rtoe", "ftoe", "rheel", "fheel")) + 1.6,
              pts["rwri"][1] + 1.5, pts["fwri"][1] + 1.5, pts["hip"][1] + 4, pts["sho"][1] + 4, pts["head"][1] + HEAD_R,
              pts["rknee"][1] + 2, pts["fknee"][1] + 2)
    ox, oy = GX, GY - low
    big = Image.new("RGBA", (CW * SS, CH * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)

    def T(pt):
        return ((ox + pt[0]) * SS, (oy + pt[1]) * SS)

    def limb(a, b, w0, w1, col):
        _poly_limb(d, T(a), T(b), w0 * SS, w1 * SS, col)

    def disc(c, r, col):
        x, y = T(c)
        d.ellipse([x - r * SS, y - r * SS, x + r * SS, y + r * SS], fill=col)

    g = pal.girth
    if pal.kind == "skel":
        bone, dark = pal.bone, pal.dark

        def leg(side, k):
            limb(pts["hip"], pts[side + "knee"], 2.4, 2.0, shade(bone, k))
            limb(pts[side + "knee"], pts[side + "foot"], 2.0, 1.8, shade(bone, k))
            limb(pts[side + "heel"], pts[side + "toe"], 2.0, 2.0, shade(bone, k))
            disc(pts[side + "knee"], 1.7, shade(bone, k))

        def arm(side, k):
            limb(pts["sho"], pts[side + "elb"], 2.0, 1.8, shade(bone, k))
            limb(pts[side + "elb"], pts[side + "wri"], 1.8, 1.5, shade(bone, k))
            disc(pts[side + "wri"], 1.6, shade(bone, k))
            disc(pts[side + "elb"], 1.5, shade(bone, k))

        arm("r", 0.72)
        leg("r", 0.72)
        limb(pts["hip"], pts["sho"], 2.0, 2.0, bone)
        sx, sy = pts["sho"]
        hx, hy = pts["hip"]
        dxn, dyn = sx - hx, sy - hy
        nrm = math.hypot(dxn, dyn) or 1
        px_, py_ = -dyn / nrm, dxn / nrm
        for i in range(1, 6):
            f = i / 6.2
            cx, cy = hx + dxn * f, hy + dyn * f
            wdt = 4.2 - abs(f - 0.5) * 2.0
            limb((cx - px_ * wdt, cy - py_ * wdt), (cx + px_ * wdt, cy + py_ * wdt), 1.5, 1.5, bone)
        limb((hx - px_ * 3.4, hy - py_ * 3.4), (hx + px_ * 3.4, hy + py_ * 3.4), 2.6, 2.6, bone)
        leg("f", 1.0)
        hc = pts["head"]
        disc(hc, 4.6 * sc, bone)
        hxv = math.radians(p["lean"] + p["head"])
        fx, fy = math.cos(hxv), math.sin(hxv)
        disc((hc[0] + 2.4 * fx, hc[1] + 0.6 - 0.4 * fy), 1.3, dark)
        limb((hc[0] + 1.0, hc[1] + 3.4), (hc[0] + 3.4, hc[1] + 3.6), 1.8, 1.8, shade(bone, 0.85))
        arm("f", 1.0)
        col_blade = pal.blade
    else:
        cs = pal
        gl = 1.0 + (g - 1.0) * 0.45

        def leg(side, k):
            limb(pts["hip"], pts[side + "knee"], 6.5 * gl, 5.5 * gl, shade(cs.pants, k))
            limb(pts[side + "knee"], pts[side + "foot"], 5.3 * gl, 4.0, shade(cs.pants, k))
            limb(pts[side + "heel"], pts[side + "toe"], 3.0, 2.6, shade(cs.shoes, k))

        def arm(side, k):
            limb(pts["sho"], pts[side + "elb"], 4.7 * gl, 4.1 * gl, shade(cs.shirt, k))
            limb(pts[side + "elb"], pts[side + "wri"], 3.8 * gl, 3.1, shade(cs.skin, k))
            disc(pts[side + "wri"], 2.2, shade(cs.skin, k))

        arm("r", 0.74)
        leg("r", 0.76)
        hx, hy = pts["hip"]
        sx, sy = pts["sho"]
        limb((hx, hy), (sx, sy), 9.2 * g, 10.6 * g, cs.shirt)
        dxn, dyn = sx - hx, sy - hy
        nrm = math.hypot(dxn, dyn) or 1
        px_, py_ = -dyn / nrm, dxn / nrm
        # Vest: a darker panel on the front half of the torso.
        a0 = (hx + dxn * 0.12 + px_ * 0.0, hy + dyn * 0.12)
        limb((a0[0] + 0.3 * g, a0[1]), (sx - dxn * 0.05 + 0.6 * g, sy - dyn * 0.05), 4.2 * g, 4.4 * g, cs.vest)
        disc((hx + dxn * 0.1, hy + dyn * 0.1), 4.2 * g, cs.sash)
        leg("f", 1.0)
        hc = pts["head"]
        hr = math.radians(p["lean"] + p["head"])
        up = (math.sin(hr), -math.cos(hr))
        fw = (math.cos(hr), math.sin(hr))
        limb((sx, sy), (hc[0] - up[0] * 1.0, hc[1] - up[1] * 1.0), 3.0, 3.0, cs.skin)
        disc(hc, HEAD_R * sc, cs.skin)
        disc((hc[0] - fw[0] * 2.2 - up[0] * 0.6, hc[1] - fw[1] * 2.2 - up[1] * 0.6), 2.6, cs.hair)
        disc((hc[0] + fw[0] * 4.0 + up[0] * 0.2, hc[1] + fw[1] * 4.0), 1.2 * sc, cs.skin)
        disc((hc[0] + fw[0] * 2.2 - up[0] * 0.8, hc[1] + fw[1] * 2.2 - up[1] * 0.8), 0.75, (20, 20, 24))
        if cs.mustache:
            limb((hc[0] + fw[0] * 3.0 + up[0] * -1.8, hc[1] + fw[1] * 3.0 - up[1] * 1.8),
                 (hc[0] + fw[0] * 4.6 + up[0] * -1.6, hc[1] + fw[1] * 4.6 - up[1] * 1.6), 1.1, 1.1, (20, 16, 16))
        # Turban: a wrapped cloth dome plus a band.
        tc = (hc[0] + up[0] * 2.0 - fw[0] * 0.5, hc[1] + up[1] * 2.0 - fw[1] * 0.5)
        disc(tc, 5.5 * sc, cs.turban)
        limb((tc[0] - fw[0] * 4.2 - up[0] * 0.2, tc[1] - fw[1] * 4.2 - up[1] * 0.2),
             (tc[0] + fw[0] * 4.4 - up[0] * 0.6, tc[1] + fw[1] * 4.4 - up[1] * 0.6), 1.4, 1.4, shade(cs.turban, 0.78))
        arm("f", 1.0)
        col_blade = cs.blade
    # Item (potion flask) and sword are held in the near hand.
    wr = pts["fwri"]
    if p["swl"] > 0.02:
        a = math.radians(p["swa"])
        bl = 27.0 * p["swl"]
        dxv, dyv = math.sin(a), math.cos(a)
        tip = (wr[0] + bl * dxv, wr[1] + bl * dyv)
        limb(wr, tip, 1.9, 1.0, col_blade)
        gx_, gy_ = wr[0] + 1.5 * dxv, wr[1] + 1.5 * dyv
        limb((gx_ - dyv * 3.0, gy_ + dxv * 3.0), (gx_ + dyv * 3.0, gy_ - dxv * 3.0), 1.4, 1.4, (214, 176, 60))
    if p["item"] > 0.5:
        fx, fy = wr
        flask = {1: (214, 40, 40), 2: (60, 90, 230), 3: (60, 200, 90)}[int(round(p["item"]))] if p["item"] < 3.5 else (214, 40, 40)
        d.ellipse([(ox + fx - 2.4) * SS, (oy + fy - 4.8) * SS, (ox + fx + 2.4) * SS, (oy + fy + 0.6) * SS], fill=flask)
        d.rectangle([(ox + fx - 0.9) * SS, (oy + fy - 7.2) * SS, (ox + fx + 0.9) * SS, (oy + fy - 4.2) * SS], fill=(230, 230, 230))
    small = big.resize((CW, CH), Image.BOX)
    px = small.load()
    outline = pal.outline
    solid = [[False] * CW for _ in range(CH)]
    for y in range(CH):
        for x in range(CW):
            r, gg, b, a = px[x, y]
            if a >= 120:
                px[x, y] = (r, gg, b, 255)
                solid[y][x] = True
            else:
                px[x, y] = (0, 0, 0, 0)
    for y in range(1, CH - 1):
        for x in range(1, CW - 1):
            if not solid[y][x] and (solid[y - 1][x] or solid[y + 1][x] or solid[y][x - 1] or solid[y][x + 1]):
                px[x, y] = outline + (255,)
    if flip:
        small = small.transpose(Image.FLIP_LEFT_RIGHT)
    hang_h = low - min(pts["rwri"][1], pts["fwri"][1])
    return small, hang_h
