# Build-time only: a 2D skeletal rig that draws side-view fighters in the flat, outline-free pixel-art style of the
# 1989 DOS game (cream clothes, pink skin, gold hair, hard 1-pixel shadows). Poses are joint angles, so in-between
# frames are plain interpolation. Everything here is drawn procedurally; no pixel of the original is copied.
import math
from PIL import Image, ImageDraw

SS = 4                       # supersampling; downsampled with NEAREST so edges stay crisp like pixel art
CW, CH = 96, 96              # logical canvas
GX, GY = 48, 84              # hip x anchor and ground line inside the canvas

NAMES = ["lean", "head", "ra_s", "ra_e", "fa_s", "fa_e", "rl_t", "rl_k", "fl_t", "fl_k", "swa", "swl", "item"]
STAND = dict(lean=1, head=0, ra_s=-4, ra_e=8, fa_s=5, fa_e=10, rl_t=-3, rl_k=0, fl_t=3, fl_k=-1,
             swa=0, swl=0, item=0)


def P(**kw):
    d = dict(STAND)
    for k, v in kw.items():
        if k not in d:
            raise KeyError(k)
        d[k] = v
    return d


def mirror_limbs(p):
    q = dict(p)
    for a, b in (("ra_s", "fa_s"), ("ra_e", "fa_e"), ("rl_t", "fl_t"), ("rl_k", "fl_k")):
        q[a], q[b] = p[b], p[a]
    return q


def lerp_pose(a, b, t):
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


# Palette values are the 16-colour VGA-style tones read off the reference frames (cream, pink skin, gold hair).
SKIN, SKIN_D = (223, 130, 109), (178, 113, 97)
PRINCE = Palette(kind="human", style="prince", cloth=(255, 255, 219), cloth_d=(214, 208, 172), skin=SKIN, skin_d=SKIN_D,
                 hair=(121, 93, 56), hair_hi=(186, 146, 0), belt=(186, 146, 0), shoes=SKIN, scale=1.0, girth=1.0,
                 blade=(255, 255, 255))


def guard_pal(coat, sleeve, trousers, sash, turban=(255, 255, 255), fat=False, beard=False):
    return Palette(kind="human", style="guard", coat=coat, coat_d=shade(coat, 0.8), sleeve=sleeve, trousers=trousers,
                   trousers_d=shade(trousers, 0.72), sash=sash, turban=turban, turban_d=shade(turban, 0.8), skin=SKIN,
                   skin_d=SKIN_D, shoes=(235, 186, 113), hair=(40, 30, 30), scale=1.04 if not fat else 1.1,
                   girth=1.7 if fat else 1.0, beard=beard, blade=(255, 255, 255))


GUARDS = {
    "g_blue": guard_pal((255, 219, 255), (73, 146, 255), (73, 146, 255), (130, 40, 121)),
    "g_red": guard_pal((231, 100, 100), (255, 219, 200), (186, 40, 40), (255, 219, 0), beard=True),
    "g_green": guard_pal((120, 200, 120), (255, 255, 219), (48, 130, 80), (186, 146, 0)),
    "g_dark": guard_pal((100, 100, 140), (170, 170, 190), (60, 60, 100), (231, 0, 0), turban=(200, 200, 215), beard=True),
    "g_gold": guard_pal((235, 186, 113), (255, 255, 219), (186, 70, 40), (130, 40, 121), turban=(255, 219, 255)),
    "g_fat": guard_pal((255, 134, 60), (255, 219, 162), (170, 100, 60), (231, 0, 0), turban=(255, 219, 0), fat=True, beard=True),
    "g_vizier": guard_pal((130, 40, 121), (60, 20, 90), (40, 20, 70), (255, 255, 0), turban=(186, 146, 0), beard=True),
}
SKELETON = Palette(kind="skel", bone=(240, 236, 214), dark=(30, 28, 30), scale=1.04, girth=1.0, blade=(190, 199, 207))
SHADOW = Palette(kind="human", style="prince", cloth=(28, 48, 77), cloth_d=(12, 32, 60), skin=(48, 73, 110), skin_d=(28, 48, 77),
                 hair=(12, 32, 60), hair_d=(12, 32, 60), belt=(48, 73, 110), shoes=(48, 73, 110), scale=1.0, girth=1.0,
                 blade=(105, 130, 178), rim=(105, 130, 178))

L_THIGH, L_SHIN, L_TORSO, L_ARM, L_FORE = 8.4, 8.4, 12.5, 6.0, 6.0
HEAD_R = 3.4


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
    hl = (2.4 + HEAD_R) * sc
    pts["head"] = (sh[0] + hl * math.sin(hr), sh[1] - hl * math.cos(hr))
    for side in ("r", "f"):
        t, k = p[side + "l_t"], p[side + "l_k"]
        dx, dy = _dir_down(t)
        kn = (lt * dx, lt * dy)
        dx, dy = _dir_down(t + k)
        fo = (kn[0] + ls * dx, kn[1] + ls * dy)
        a = math.radians(t + k)
        toe = (fo[0] + 4.4 * sc * math.cos(a), fo[1] - 4.4 * sc * math.sin(a))
        heel = (fo[0] - 1.2 * sc * math.cos(a), fo[1] + 1.2 * sc * math.sin(a))
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
    low = max(max(pts[k][1] for k in ("rfoot", "ffoot", "rtoe", "ftoe", "rheel", "fheel")) + 0.8,
              pts["rwri"][1] + 1.2, pts["fwri"][1] + 1.2, pts["hip"][1] + 3, pts["sho"][1] + 3, pts["head"][1] + HEAD_R,
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
    hr = math.radians(p["lean"] + p["head"])
    up = (math.sin(hr), -math.cos(hr))
    fw = (math.cos(hr), math.sin(hr))
    hc = pts["head"]
    hx, hy = pts["hip"]
    sx, sy = pts["sho"]
    if pal.kind == "skel":
        bone, dark = pal.bone, pal.dark

        def leg(side, k):
            limb(pts["hip"], pts[side + "knee"], 2.2, 1.8, shade(bone, k))
            limb(pts[side + "knee"], pts[side + "foot"], 1.8, 1.6, shade(bone, k))
            limb(pts[side + "heel"], pts[side + "toe"], 1.6, 1.6, shade(bone, k))
            disc(pts[side + "knee"], 1.5, shade(bone, k))

        def arm(side, k):
            limb(pts["sho"], pts[side + "elb"], 1.8, 1.6, shade(bone, k))
            limb(pts[side + "elb"], pts[side + "wri"], 1.6, 1.4, shade(bone, k))
            disc(pts[side + "wri"], 1.4, shade(bone, k))

        arm("r", 0.7)
        leg("r", 0.7)
        limb(pts["hip"], pts["sho"], 1.8, 1.8, bone)
        dxn, dyn = sx - hx, sy - hy
        nrm = math.hypot(dxn, dyn) or 1
        px_, py_ = -dyn / nrm, dxn / nrm
        for i in range(1, 6):
            f = i / 6.2
            cx, cy = hx + dxn * f, hy + dyn * f
            wdt = 3.6 - abs(f - 0.5) * 1.6
            limb((cx - px_ * wdt, cy - py_ * wdt), (cx + px_ * wdt, cy + py_ * wdt), 1.3, 1.3, bone)
        limb((hx - px_ * 3.0, hy - py_ * 3.0), (hx + px_ * 3.0, hy + py_ * 3.0), 2.2, 2.2, bone)
        leg("f", 1.0)
        disc(hc, 3.9 * sc, bone)
        disc((hc[0] + fw[0] * 1.9, hc[1] + fw[1] * 1.9 - 0.4), 1.1, dark)
        limb((hc[0] + fw[0] * 1.2 - up[0] * 2.8, hc[1] + fw[1] * 1.2 - up[1] * 2.8),
             (hc[0] + fw[0] * 3.2 - up[0] * 2.8, hc[1] + fw[1] * 3.2 - up[1] * 2.8), 1.6, 1.6, shade(bone, 0.85))
        arm("f", 1.0)
        col_blade = pal.blade
    elif pal.style == "prince":
        c = pal

        def leg(side, k):
            kn, fo = pts[side + "knee"], pts[side + "foot"]
            col = c.cloth if k >= 1 else c.cloth_d
            limb(pts["hip"], kn, 6.0, 5.4, col)
            limb(kn, fo, 5.4, 3.4, col)
            mid = (kn[0] * 0.45 + fo[0] * 0.55, kn[1] * 0.45 + fo[1] * 0.55 - 0.2)
            disc(mid, 3.0, col)
            limb(pts[side + "heel"], pts[side + "toe"], 2.2, 2.0, c.skin if k >= 1 else c.skin_d)
            disc(fo, 1.8, c.skin if k >= 1 else c.skin_d)

        def arm(side, k):
            col = c.skin if k >= 1 else c.skin_d
            limb(pts["sho"], pts[side + "elb"], 2.8, 2.4, col)
            limb(pts[side + "elb"], pts[side + "wri"], 2.4, 2.0, col)
            disc(pts[side + "wri"], 1.5, col)

        arm("r", 0)
        leg("r", 0)
        limb((hx, hy), (sx, sy), 6.2, 7.0, c.cloth)
        bx0, by0 = T((hx - 3.2, hy - 1.6))
        bx1, by1 = T((hx + 3.4, hy - 0.2))
        d.rectangle([bx0, by0, bx1, by1], fill=c.belt)
        leg("f", 1)
        limb((sx, sy), (hc[0] - up[0] * 0.8, hc[1] - up[1] * 0.8), 2.6, 2.6, c.skin)
        disc(hc, HEAD_R * sc, c.skin)
        disc((hc[0] - fw[0] * 0.9 + up[0] * 1.1, hc[1] - fw[1] * 0.9 + up[1] * 1.1), 3.2 * sc, c.hair)
        limb((hc[0] - fw[0] * 3.0 + up[0] * 0.2, hc[1] - fw[1] * 3.0 + up[1] * 0.2),
             (hc[0] - fw[0] * 2.4 - up[0] * 2.4, hc[1] - fw[1] * 2.4 - up[1] * 2.4), 2.0, 1.8, c.hair)
        if hasattr(c, "hair_hi"):
            disc((hc[0] + up[0] * 2.4 + fw[0] * 0.2, hc[1] + up[1] * 2.4 + fw[1] * 0.2), 1.7, c.hair_hi)
        disc((hc[0] + fw[0] * 2.6 + up[0] * 0.2, hc[1] + fw[1] * 2.6 + up[1] * 0.2), 1.1, c.skin)
        disc((hc[0] + fw[0] * 1.7 - up[0] * 0.5, hc[1] + fw[1] * 1.7 - up[1] * 0.5), 0.55, (40, 20, 10))
        arm("f", 1)
        col_blade = c.blade
    else:
        c = pal
        gl = 1.0 + (g - 1.0) * 0.5

        def leg(side, k):
            col = c.trousers if k >= 1 else c.trousers_d
            kn, fo = pts[side + "knee"], pts[side + "foot"]
            limb(pts["hip"], kn, 5.0 * gl, 4.4 * gl, col)
            limb(kn, fo, 4.2 * gl, 3.0, col)
            limb(pts[side + "heel"], pts[side + "toe"], 2.4, 2.0, c.shoes)
            disc(fo, 1.9, c.shoes)

        def arm(side, k):
            col = c.sleeve if k >= 1 else shade(c.sleeve, 0.75)
            limb(pts["sho"], pts[side + "elb"], 3.2 * gl, 2.8 * gl, col)
            limb(pts[side + "elb"], pts[side + "wri"], 2.8 * gl, 2.2, col)
            disc(pts[side + "wri"], 1.5, c.skin)

        arm("r", 0)
        leg("r", 0)
        limb((hx, hy), (sx, sy), 7.0 * g, 8.0 * g, c.coat)
        kavg = ((pts["rknee"][0] + pts["fknee"][0]) / 2 * 0.85, (pts["rknee"][1] + pts["fknee"][1]) / 2 * 0.85 + 1.0)
        wsk = 5.6 * g
        d.polygon([T((hx - wsk * 0.8, hy - 1)), T((hx + wsk * 0.8, hy - 1)), T((kavg[0] + wsk, kavg[1])), T((kavg[0] - wsk, kavg[1]))],
                  fill=c.coat_d)
        limb((hx - 0.2, hy - 1.2), (hx + 0.2, hy - 0.8), 7.6 * g, 7.6 * g, c.sash)
        leg("f", 1)
        limb((sx, sy), (hc[0] - up[0] * 0.5, hc[1] - up[1] * 0.5), 2.6, 2.6, c.skin)
        disc(hc, 3.2 * sc, c.skin)
        if c.beard:
            disc((hc[0] + fw[0] * 1.6 - up[0] * 1.8, hc[1] + fw[1] * 1.6 - up[1] * 1.8), 1.7, (50, 30, 30))
        disc((hc[0] + fw[0] * 2.0 - up[0] * 0.3, hc[1] + fw[1] * 2.0 - up[1] * 0.3), 0.55, (30, 20, 10))
        disc((hc[0] + fw[0] * 3.0, hc[1] + fw[1] * 3.0), 0.9, c.skin)
        tc = (hc[0] + up[0] * 1.7, hc[1] + up[1] * 1.7)
        disc(tc, 4.6 * sc, c.turban)
        limb((tc[0] - fw[0] * 3.6 - up[0] * 1.2, tc[1] - fw[1] * 3.6 - up[1] * 1.2),
             (tc[0] + fw[0] * 3.6 - up[0] * 1.6, tc[1] + fw[1] * 3.6 - up[1] * 1.6), 1.3, 1.3, c.turban_d)
        arm("f", 1)
        col_blade = c.blade
    wr = pts["fwri"]
    if p["swl"] > 0.02:
        a = math.radians(p["swa"])
        bl = 24.0 * p["swl"]
        dxv, dyv = math.sin(a), math.cos(a)
        tip = (wr[0] + bl * dxv, wr[1] + bl * dyv)
        limb(wr, tip, 1.5, 0.9, col_blade)
        gx_, gy_ = wr[0] + 1.2 * dxv, wr[1] + 1.2 * dyv
        limb((gx_ - dyv * 2.2, gy_ + dxv * 2.2), (gx_ + dyv * 2.2, gy_ - dxv * 2.2), 1.2, 1.2, (186, 146, 0))
    if p["item"] > 0.5:
        fx, fy = wr
        flask = {1: (231, 0, 0), 2: (73, 146, 255), 3: (60, 200, 90)}[int(round(p["item"]))] if p["item"] < 3.5 else (231, 0, 0)
        d.ellipse([(ox + fx - 2.0) * SS, (oy + fy - 4.0) * SS, (ox + fx + 2.0) * SS, (oy + fy + 0.6) * SS], fill=flask)
        d.rectangle([(ox + fx - 0.8) * SS, (oy + fy - 6.0) * SS, (ox + fx + 0.8) * SS, (oy + fy - 3.6) * SS], fill=(230, 230, 230))
    small = big.resize((CW, CH), Image.NEAREST)
    px = small.load()
    rim = getattr(pal, "rim", None)
    if rim:
        solid = [[px[x, y][3] > 0 for x in range(CW)] for y in range(CH)]
        for y in range(1, CH - 1):
            for x in range(1, CW - 1):
                if solid[y][x] and not (solid[y - 1][x] and solid[y][x - 1] and solid[y][x + 1] and solid[y + 1][x]):
                    px[x, y] = rim + (255,)
    if flip:
        small = small.transpose(Image.FLIP_LEFT_RIGHT)
    hang_h = low - min(pts["rwri"][1], pts["fwri"][1])
    return small, hang_h
