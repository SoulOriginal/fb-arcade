# Characters for the Battletoads build: a shared jointed biped rig plus per-character head/torso drawing.
# Angles follow one convention everywhere: measured from "straight down", positive towards the facing
# direction (right), so 90 is horizontal-forward and 180 is straight up.
import math
from g_battletoads_art import *

POSE = dict(lean=8, hipx=0, hx=0, hy=0, htilt=0, hs=1.0, mouth=0.0, horns=0, eyes="open", hurt=0,
            aF=(32, 105, 1.0), aB=(-6, 100, 1.0), lF=(8, 12, 1.0), lB=(-8, 14, 1.0), prop=None, hip=None)


def ellipses(cv, shapes, o=1.3):
    # Union-style cel shading: all outlines first so touching blobs do not draw a line between each other.
    for cx, cy, rx, ry, rot, base in shapes:
        cv.ell(cx, cy, rx + o, ry + o, OUT, rot)
    for cx, cy, rx, ry, rot, base in shapes:
        cv.ell(cx, cy, rx, ry, shade(base), rot)
    for cx, cy, rx, ry, rot, base in shapes:
        sx, sy = rot_pt(-0.1 * rx, -0.14 * ry, rot)
        cv.ell(cx + sx, cy + sy, rx * 0.88, ry * 0.86, base, rot)
    for cx, cy, rx, ry, rot, base in shapes:
        sx, sy = rot_pt(-0.38 * rx, -0.46 * ry, rot)
        cv.ell(cx + sx, cy + sy, rx * 0.3, ry * 0.26, light(base), rot)


def fk(origin, a, length):
    return (origin[0] + length * math.sin(math.radians(a)), origin[1] + length * math.cos(math.radians(a)))


# ---- heads ----------------------------------------------------------------------------------------------
def head_frame(c, p, k):
    s = p["hs"] * k
    cx, cy = c
    tilt = p["htilt"]

    def T(x, y):
        rx, ry = rot_pt(x * s, y * s, tilt)
        return (cx + rx, cy + ry)
    return s, T, tilt


def toad_head(cv, c, p, st, k):
    s, T, tilt = head_frame(c, p, k)
    skin = st["skin"]
    m = p["mouth"]
    if p["horns"]:
        for sgn, (x0, hx_) in enumerate(((-3, -12), (9, 5))):
            a = T(x0, -11)
            b = T(x0 - 6 + 4 * sgn, -22)
            c2 = T(x0 + 2 + 6 * sgn, -29)
            cv.capsule(a, 4.6 * s, b, 3.6 * s, (238, 224, 190))
            cv.capsule(b, 3.6 * s, c2, 1.6 * s, (238, 224, 190))
    ellipses(cv, [(*T(-2, -13), 6.6 * s, 6 * s, tilt, skin), (*T(9, -12.5), 6.6 * s, 6 * s, tilt, skin),
                  (*T(0, 0), 17 * s, 14.5 * s, tilt, skin), (*T(13, 3.5), 11 * s, 8.5 * s, tilt, skin)])
    # sunglasses, the toad's signature
    cv.line(T(-4, -8), T(-16, -9.5), 2.2 * s, (24, 24, 36))
    for lx, ly in ((2, -7), (15, -6.5)):
        cv.ell(*T(lx, ly), 8.3 * s, 6.1 * s, OUT, tilt)
        cv.ell(*T(lx, ly), 7.3 * s, 5.2 * s, (22, 24, 40), tilt)
        cv.poly([T(lx - 4.5, ly - 3), T(lx - 1.5, ly - 3.6), T(lx - 4, ly + 1.2), T(lx - 6, ly + 0.8)], (150, 205, 250))
    cv.line(T(8, -8.2), T(9.2, -7.4), 2.4 * s, (24, 24, 36))
    # grin: a long lens-shaped mouth curling up at the cheek, with a row of big teeth
    up, lo = [], []
    for i in range(13):
        t = i / 12
        x = -10 + 35 * t
        yu = 5.8 - 5.2 * (1 - t) ** 2.4
        yl = yu + (3.4 + 11 * m) * math.sin(math.pi * t) ** 0.75
        up.append(T(x, yu))
        lo.append(T(x, yl))
    cv.poly(up + lo[::-1], (96, 12, 38))
    if m > 0.3:
        cv.ell(*T(10, 5.8 + 3.4 + 10 * m - 4), 6 * s, (2 + 3 * m) * s, (232, 88, 110), tilt)
    for i in range(6):
        t = (i + 0.7) / 6.4
        x = -8 + 32 * t
        yu = 5.8 - 5.2 * (1 - t) ** 2.4
        h = 3.6 + 1.6 * m
        cv.poly([T(x - 2.2, yu - 0.3), T(x + 2.2, yu - 0.3), T(x + 2.1, yu + h), T(x - 2.1, yu + h)], (255, 252, 238))
    if m > 0.5:
        for i in range(5):
            x = -2 + 5.6 * i
            yu = 5.8 - 5.2 * (1 - (x + 10) / 35) ** 2.4
            yb = yu + (3.4 + 11 * m) * math.sin(math.pi * (x + 10) / 35) ** 0.75
            cv.poly([T(x - 2, yb + 0.3), T(x + 2, yb + 0.3), T(x + 1.8, yb - 3.4), T(x - 1.8, yb - 3.4)], (255, 252, 238))
    cv.polyline(up, 1.1 * s, OUT)
    cv.polyline(lo, 1.1 * s, OUT)
    cv.circ(*T(23.2, 0.5), 1.1 * s, OUT)


def pig_head(cv, c, p, st, k):
    s, T, tilt = head_frame(c, p, k)
    skin, hel = st["skin"], st["helmet"]
    cv.capsule(T(-6, -7), 5.2 * s, T(-17, -15), 3 * s, shade(skin, 0.85))
    ellipses(cv, [(*T(0, 0), 16 * s, 14 * s, tilt, skin), (*T(16, 4), 6.8 * s, 7.6 * s, tilt, light(skin, 0.18))])
    cv.ell(*T(19, 2.5), 1.3 * s, 1.8 * s, OUT, tilt)
    cv.ell(*T(19, 7), 1.3 * s, 1.8 * s, OUT, tilt)
    if p["hurt"]:
        cv.line(T(4, -3), T(9, 2), 1.4 * s, OUT)
        cv.line(T(9, -3), T(4, 2), 1.4 * s, OUT)
    else:
        cv.circ(*T(7, -2), 3.4 * s, (255, 255, 255))
        cv.circ(*T(8.3, -2), 1.8 * s, OUT)
        cv.line(T(2, -8), T(12, -4.6), 1.9 * s, OUT)
    m = p["mouth"]
    cv.polyline([T(6, 10), T(14, 11 + 4 * m)], 1.4 * s, OUT)
    cv.poly([T(12, 11), T(16, 11), T(15, 4), T(13.6, 4)], (255, 250, 230))
    # helmet: dome, rim band, spike, rivets
    cv.ell(*T(-1, -6), 17.5 * s, 12.5 * s, OUT, tilt)
    cv.ell(*T(-1, -6), 16.5 * s, 11.5 * s, shade(hel), tilt)
    cv.ell(*T(-2, -7.4), 14.5 * s, 9.6 * s, hel, tilt)
    cv.ell(*T(-6, -11), 6 * s, 3.6 * s, light(hel), tilt)
    cv.line(T(-16, -2), T(17, -2.8), 3.4 * s, shade(hel, 0.5))
    cv.line(T(-16, -2.8), T(17, -3.6), 1.2 * s, light(hel, 0.3))
    cv.poly([T(-3, -16), T(3, -16), T(0, -26)], st["spike"])
    cv.circ(*T(-9, -8), 1.5 * s, (240, 240, 240))
    cv.circ(*T(7, -8.5), 1.5 * s, (240, 240, 240))


def rat_head(cv, c, p, st, k):
    s, T, tilt = head_frame(c, p, k)
    fur = st["skin"]
    cv.ell(*T(-6, -12), 8.6 * s, 9.4 * s, OUT, tilt)
    cv.ell(*T(-6, -12), 7.4 * s, 8.2 * s, shade(fur), tilt)
    cv.ell(*T(-6, -12), 5.2 * s, 6 * s, (232, 150, 165), tilt)
    ellipses(cv, [(*T(0, 0), 13 * s, 11 * s, tilt, fur), (*T(15, 3), 13 * s, 6.4 * s, tilt + 8, light(fur, 0.1))])
    cv.circ(*T(28.5, 3.2), 3.4 * s, OUT)
    cv.circ(*T(28, 2.6), 2.6 * s, (238, 120, 140))
    if p["hurt"]:
        cv.line(T(6, -4), T(11, 1), 1.3 * s, OUT)
        cv.line(T(11, -4), T(6, 1), 1.3 * s, OUT)
    else:
        cv.circ(*T(9, -2), 3.1 * s, (255, 255, 255))
        cv.circ(*T(10, -2), 1.9 * s, (210, 20, 30))
        cv.line(T(4, -7), T(13, -3.5), 1.8 * s, OUT)
    m = p["mouth"]
    cv.poly([T(21, 8), T(25, 8), T(25, 12 + 2 * m), T(21, 12 + 2 * m)], (255, 250, 220))
    cv.polyline([T(10, 9), T(26, 8)], 1.2 * s, OUT)
    for dy in (-1, 3):
        cv.line(T(24, 4 + dy), T(36, 1 + dy * 1.8), 0.6 * s, (60, 50, 60))
    if st.get("scar"):
        cv.line(T(-3, -8), T(5, 4), 1.2 * s, (170, 60, 70))


def walker_head(cv, c, p, st, k):
    s, T, tilt = head_frame(c, p, k)
    cv.line(T(-4, -12), T(-10, -26), 1.4 * s, OUT)
    cv.circ(*T(-10, -26), 2.2 * s, (230, 60, 50))
    ellipses(cv, [(*T(0, 0), 15 * s, 12 * s, tilt, st["skin"])])
    cv.ell(*T(6, -1), 9.6 * s, 7.4 * s, OUT, tilt)
    cv.ell(*T(6, -1), 8.4 * s, 6.2 * s, (40, 50, 70), tilt)
    glow = (255, 90, 60) if not p["hurt"] else (255, 255, 200)
    cv.ell(*T(8, -1), 4.2 * s, 4.2 * s, glow, tilt)
    cv.circ(*T(6.8, -2.4), 1.2 * s, (255, 255, 255))
    cv.line(T(-12, 6), T(14, 8.5), 2.4 * s, st["accent"])


# ---- torsos ---------------------------------------------------------------------------------------------
def toad_torso(cv, H, top, p, st, k):
    lean = p["lean"]
    ch = (H[0] + top[0] * 0.66, H[1] + top[1] * 0.66)
    bl = (H[0] + top[0] * 0.5 + rot_pt(5 * k, 0, lean)[0], H[1] + top[1] * 0.5 + rot_pt(5 * k, 0, lean)[1])
    ellipses(cv, [(*ch, 16.5 * k, 14.5 * k, lean, st["skin"]), (H[0], H[1] - 2 * k, 14.5 * k, 9.5 * k, lean, st["pants"])])
    ellipses(cv, [(*bl, 10.5 * k, 12.5 * k, lean, st["belly"])])
    cv.line((bl[0] - 7 * k, bl[1] - 1), (bl[0] + 8 * k, bl[1] - 1), 0.7 * k, shade(st["belly"], 0.7))
    cv.line((H[0] - 12 * k, H[1] - 3 * k), (H[0] + 13 * k, H[1] - 3 * k), 2.2 * k, st["belt"])
    cv.circ(H[0] + 7 * k, H[1] - 3 * k, 2 * k, (240, 200, 70))


def pig_torso(cv, H, top, p, st, k):
    lean = p["lean"]
    ch = (H[0] + top[0] * 0.62, H[1] + top[1] * 0.62)
    ellipses(cv, [(*ch, 17 * k, 14.5 * k, lean, st["skin"]), (H[0], H[1] - 2 * k, 14.5 * k, 9.5 * k, lean, st["pants"])])
    ellipses(cv, [(ch[0] + 1 * k, ch[1] + 1 * k, 15 * k, 12 * k, lean, st["vest"])])
    cv.line((ch[0] + 5 * k, ch[1] - 8 * k), (ch[0] + 6 * k, ch[1] + 9 * k), 1.2 * k, shade(st["vest"], 0.6))
    cv.circ(ch[0] + 4 * k, ch[1] - 2 * k, 1.5 * k, (240, 210, 90))
    cv.circ(ch[0] + 4 * k, ch[1] + 4 * k, 1.5 * k, (240, 210, 90))


def rat_torso(cv, H, top, p, st, k):
    lean = p["lean"]
    ch = (H[0] + top[0] * 0.6, H[1] + top[1] * 0.6)
    ellipses(cv, [(*ch, 14 * k, 13.5 * k, lean, st["skin"]), (H[0], H[1] - 2 * k, 12.5 * k, 8.5 * k, lean, st["pants"])])
    if st.get("vest"):
        ellipses(cv, [(ch[0] + 2 * k, ch[1] + 2 * k, 12.5 * k, 11 * k, lean, st["vest"])])
        cv.line((H[0] - 12 * k, H[1] - 2 * k), (H[0] + 13 * k, H[1] - 2 * k), 3 * k, st["belt"])
        cv.ell(H[0] + 8 * k, H[1] - 2 * k, 4 * k, 3.6 * k, (255, 215, 80), 0)
    else:
        ellipses(cv, [(ch[0] + 3 * k, ch[1] + 2 * k, 8 * k, 9.5 * k, lean, light(st["skin"], 0.35))])


def walker_torso(cv, H, top, p, st, k):
    lean = p["lean"]
    ch = (H[0] + top[0] * 0.62, H[1] + top[1] * 0.62)
    ellipses(cv, [(H[0], H[1] - 3 * k, 13 * k, 8 * k, lean, st["dark"]), (*ch, 20 * k, 17 * k, lean, st["skin"])])
    cv.ell(ch[0] + 6 * k, ch[1] + 2 * k, 10 * k, 8 * k, shade(st["skin"], 0.6), lean)
    for i in range(3):
        cv.circ(ch[0] - 12 * k + i * 3.2 * k, ch[1] - 6 * k + i * 4 * k, 1.4 * k, (230, 235, 245))
    cv.line((ch[0] - 14 * k, ch[1] + 8 * k), (ch[0] + 12 * k, ch[1] + 10 * k), 3.4 * k, st["accent"])
    cv.ell(ch[0] + 7 * k, ch[1] + 1 * k, 5 * k, 5 * k, (250, 220, 100), 0)


# ---- the biped rig --------------------------------------------------------------------------------------
def boot_shape(ankle, b, fs, k, st):
    fd = (math.cos(math.radians(b)), -math.sin(math.radians(b)))
    sd = (math.sin(math.radians(b)), math.cos(math.radians(b)))
    c = (ankle[0] + fd[0] * 4.5 * k * fs + sd[0] * 2 * k, ankle[1] + fd[1] * 4.5 * k * fs + sd[1] * 2 * k)
    return c, st["bootr"][0] * k * fs, st["bootr"][1] * k * fs, -b


def biped(cv, pose, st, k=1.0, propimg=None):
    p = dict(POSE)
    p.update(pose)
    thigh, shin = st["thigh"] * k, st["shin"] * k
    uarm, farm = st["uarm"] * k, st["farm"] * k
    torso = st["torso"] * k
    lean = p["lean"]
    top = rot_pt(0, -torso, lean)

    def leg_joints(H, leg):
        a, kb, fs = leg
        knee = fk(H, a, thigh)
        b = a - kb
        ankle = fk(knee, b, shin)
        c, rx, ry, rot = boot_shape(ankle, b, fs, k, st)
        low = max(pt[1] for pt in cv.ellpts(c[0], c[1], rx, ry, rot, 16))
        return knee, ankle, b, (c, rx, ry, rot), low

    if p["hip"] is None:
        low = max(leg_joints((0, 0), p["lF"])[4], leg_joints((0, 0), p["lB"])[4])
        H = (p["hipx"] * k, -low)
    else:
        H = (p["hip"][0] * k, p["hip"][1] * k)
    sh = (H[0] + top[0], H[1] + top[1])

    def arm(ar, sho, front):
        a, bend, fs = ar
        elbow = fk(sho, a, uarm)
        b = a + bend
        wrist = fk(elbow, b, farm)
        fr = st["fistr"] * k * fs
        d = (math.sin(math.radians(b)), math.cos(math.radians(b)))
        fc = (wrist[0] + d[0] * fr * 0.55, wrist[1] + d[1] * fr * 0.55)
        rw = max(st["armr"] * k * 0.9, fr * 0.78) if fs > 1.3 else st["armr"] * k * 0.9
        cv.capsule(sho, st["armr"] * k, elbow, st["armr"] * k * 0.92, st["arm"])
        cv.capsule(elbow, st["armr"] * k * 0.92, wrist, rw, st["arm"])
        if st.get("band"):
            cv.circ(*fk(wrist, b + 180, 1.5 * k), st["armr"] * k * 0.95 + 0.4, st["band"])
        cv.blob(fc[0], fc[1], fr, fr * 0.92, st["fist"], rot=0)
        # knuckle creases and thumb make the swollen fist read as a fist
        nx, ny = d[1], -d[0]
        for i in (-1, 0, 1):
            q = (fc[0] + d[0] * fr * 0.55 + nx * fr * 0.34 * i, fc[1] + d[1] * fr * 0.55 + ny * fr * 0.34 * i)
            cv.line((q[0] - d[0] * fr * 0.34, q[1] - d[1] * fr * 0.34), q, max(0.5, fr * 0.1), shade(st["fist"], 0.5))
        return wrist, elbow

    def leg(hp, lg):
        knee, ankle, b, (c, rx, ry, rot), _ = leg_joints(hp, lg)
        cv.capsule(hp, st["legr"] * k, knee, st["legr"] * k * 0.92, st["leg"])
        cv.capsule(knee, st["legr"] * k * 0.92, ankle, st["legr"] * k * 0.8, st.get("shinc", st["leg"]))
        cv.blob(c[0], c[1], rx, ry, st["boot"], rot=rot)
        if lg[2] > 1.4:
            for i in range(3):
                q = (c[0] - rx * 0.2 + i * rx * 0.2, c[1] - ry * 0.55)
                cv.line((q[0] - 1.5, q[1] - 1), (q[0] + 1.5, q[1] + 1.4), max(0.5, 0.35 * lg[2]), st["laces"])

    hipB = (H[0] - 2.5 * k, H[1])
    hipF = (H[0] + 2.5 * k, H[1])
    shB = (sh[0] - 5 * k, sh[1] + 1)
    shF = (sh[0] + 3 * k, sh[1])
    arm(p["aB"], shB, False)
    leg(hipB, p["lB"])
    leg(hipF, p["lF"])
    st["torso_fn"](cv, H, top, p, st, k)
    hc = (sh[0] + p["hx"] * k + rot_pt(0, -st["neck"] * k, lean)[0], sh[1] + p["hy"] * k + rot_pt(0, -st["neck"] * k, lean)[1])
    st["head_fn"](cv, hc, p, st, k)
    wr, _ = arm(p["aF"], shF, True)
    if p["prop"] is not None and propimg is not None:
        # held object sits just beyond the hands, long axis along the arm direction
        ang, dist = p["prop"]
        w = fk(shF, p["aF"][0], uarm + farm)
        centre = fk(w, ang, dist * k)
        rotd = propimg.rotate(ang + 180, resample=Image.BICUBIC, expand=True)
        cv.paste(rotd, centre[0], centre[1])
        cv.circ(*fk(w, ang, 2), st["fistr"] * k, st["fist"])
        cv.circ(*fk(shB, p["aB"][0], uarm + farm), st["fistr"] * k * 0.9, st["fist"])
    return H, sh
