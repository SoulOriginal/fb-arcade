# Necromorph art. Every limb is a flag so that strategic dismemberment is shown by sprite choice:
# a shot-off arm is simply missing from the next frame and appears as a separate flying piece.
import math
from g_deadspace_art import *

PALS = {
    "pale": dict(flesh=(150, 118, 100), dark=(84, 56, 54), light=(184, 150, 128), muscle=(140, 30, 34), eye=(255, 232, 150)),
    "enh": dict(flesh=(66, 82, 60), dark=(26, 34, 28), light=(110, 130, 86), muscle=(150, 70, 30), eye=(255, 150, 40)),
    "grey": dict(flesh=(124, 126, 120), dark=(56, 58, 56), light=(168, 170, 160), muscle=(120, 40, 44), eye=(200, 255, 170)),
    "dark": dict(flesh=(96, 70, 72), dark=(44, 26, 30), light=(140, 104, 100), muscle=(160, 36, 30), eye=(255, 80, 60)),
}


def blade(cv, p0, ang, ln, wd, pal, curve=0.0):
    """Bone scythe growing out of an arm; ang in degrees from straight up, positive = forward (+x)."""
    r = math.radians(ang)
    dx, dy = math.sin(r), -math.cos(r)
    nx, ny = -dy, dx
    pts = []
    n = 6
    for i in range(n + 1):
        t = i / n
        bend = curve * t * t * ln
        pts.append((p0[0] + dx * ln * t + nx * bend, p0[1] + dy * ln * t + ny * bend))
    w = [wd * (1 - t / n * 0.92) for t in range(n + 1)]
    left = [(p[0] + nx * ww / 2, p[1] + ny * ww / 2) for p, ww in zip(pts, w)]
    right = [(p[0] - nx * ww / 2, p[1] - ny * ww / 2) for p, ww in zip(pts, w)]
    cv.poly(left + right[::-1], BONE, OUTLINE, 0.6)
    cv.line([(a[0], a[1]) for a in pts[:-1]], BONE_D, 0.5)
    cv.line([pts[1], pts[-1]], (240, 236, 214), 0.45)
    return pts[-1]


def skull(cv, c, pal, jaw=True, big=1.0, eyes=True):
    cx, cy = c
    cv.ell(cx, cy, 4.3 * big, 4.6 * big, pal["flesh"], OUTLINE, 0.7)
    cv.ell(cx - 0.6, cy - 1.0, 2.6 * big, 2.6 * big, pal["light"])
    # torn face: dark mouth cavity with bone spikes where the lower jaw should be
    cv.poly([(cx + 0.5, cy + 1.0), (cx + 4.6 * big, cy + 1.6), (cx + 4.0 * big, cy + 4.4), (cx + 0.6, cy + 3.6)],
            MUSCLE_D, OUTLINE, 0.4)
    for i in range(4):
        x = cx + 1.0 + i * 0.95 * big
        cv.poly([(x, cy + 1.6), (x + 0.5, cy + 1.6), (x + 0.2, cy + 3.2)], BONE)
    if eyes:
        cv.glow(cx + 2.2, cy - 0.8, 3.2, pal["eye"], 0.7)
        cv.ell(cx + 2.4, cy - 0.8, 1.0, 1.0, pal["eye"])


def sl_leg(cv, hip, ph, pal, front, crouch=0.0):
    """Digitigrade leg: thigh forward, shin back, long fused foot peg."""
    sw = math.sin(ph * 2 * math.pi) * (1 if front else -1)
    knee = (hip[0] + 4.0 + 3.5 * sw, hip[1] + 9.0)
    ank = (knee[0] - 5.5 + 3.0 * sw, knee[1] + 8.0 - 1.5 * max(0, -sw))
    toe = (ank[0] + 6.0, ank[1] + 1.8)
    col = pal["flesh"] if front else shade(pal["flesh"], 0.78)
    cv.limb([hip, knee], 4.6, col, pal["dark"], pal["light"])
    cv.limb([knee, ank], 3.2, shade(col, 0.95), pal["dark"], pal["light"])
    cv.limb([ank, toe], 1.9, shade(col, 0.8), pal["dark"], pal["light"])
    cv.ell(knee[0], knee[1], 2.5, 2.5, pal["muscle"], OUTLINE, 0.4)


def sl_torso(cv, hip, sh, pal, lying=False):
    mid = ((hip[0] + sh[0]) / 2, (hip[1] + sh[1]) / 2)
    cv.poly([(hip[0] - 3.5, hip[1] + 1), (sh[0] - 5.0, sh[1] + 1), (sh[0] + 1, sh[1] - 2), (sh[0] + 4.5, sh[1] + 3),
             (hip[0] + 3.5, hip[1] - 2)], pal["flesh"], OUTLINE, 0.8)
    # opened belly: red muscle with rib arcs
    cv.poly([(mid[0] - 0.5, mid[1] - 5), (mid[0] + 4.0, mid[1] - 4), (mid[0] + 3.0, mid[1] + 4), (mid[0] - 1.0, mid[1] + 3)],
            MUSCLE, MUSCLE_D, 0.6)
    for k in range(4):
        y = mid[1] - 4 + k * 2.3
        cv.line([(mid[0] - 4.0, y), (mid[0] + 1.5, y + 1.0)], BONE, 0.65)
    # exposed spine knobs along the back
    for k in range(5):
        t = k / 4
        x = hip[0] - 3.7 + (sh[0] - hip[0] - 1.3) * t
        y = hip[1] + (sh[1] - hip[1]) * t
        cv.ell(x, y, 1.1, 1.0, BONE_D, OUTLINE, 0.3)


def slasher(legs, arms, head, mode, ph, pal, atk=0.0):
    """legs/arms are (front, back) booleans. mode: walk, attack, crawl, lying."""
    cv = Cv(60, 60)
    pal = PALS[pal]
    if mode in ("walk", "attack"):
        bob = abs(math.sin(ph * math.pi * 2)) * 0.8
        hip = (26.0, 36.0 + bob)
        sh = (33.0, 22.0 + bob)
        hd = (37.5, 17.0 + bob)
        if legs[1]:
            sl_leg(cv, (hip[0] - 1, hip[1]), ph, pal, False)
        if arms[1]:
            draw_sl_arm(cv, sh, mode, ph + 0.5, atk, pal, False)
        for k in (0, 1):
            ex = hip[0] - 1 + 3 * k
            cv.limb([(ex + 1, hip[1] - 5), (ex + 5 + k * 2, hip[1] - 1 + math.sin(ph * 6.28 + k) * 1.5)], 1.3, pal["flesh"])
        sl_torso(cv, hip, sh, pal)
        if head:
            skull(cv, hd, pal)
        else:
            cv.ell(sh[0] + 2, sh[1] - 2, 2.3, 1.5, MUSCLE, BLOOD, 0.4)
        if legs[0]:
            sl_leg(cv, (hip[0] + 1, hip[1]), ph, pal, True)
        if arms[0]:
            draw_sl_arm(cv, sh, mode, ph, atk, pal, True)
        if not (legs[0] or legs[1]):
            return None
    elif mode == "crawl":
        sway = math.sin(ph * 2 * math.pi)
        hip = (14.0, 49.0)
        sh = (31.0, 46.0 - abs(sway))
        hd = (38.0, 44.0 - abs(sway))
        # abdominal arms act as backup legs when the legs are gone (wiki: they propel the body)
        for k in (0, 1):
            s = math.sin(ph * 6.283 + k * 3.14)
            x0 = 24 + k * 4
            cv.limb([(x0, 47), (x0 + 5 + 4 * s, 54), (x0 + 9 + 6 * s, 57.5)], 1.7, pal["flesh"], pal["dark"])
        if legs[1]:
            cv.limb([(hip[0], hip[1]), (hip[0] - 5, hip[1] + 4)], 3.4, pal["flesh"], pal["dark"])
        else:
            cv.ell(hip[0], hip[1] + 1, 3.4, 2.6, MUSCLE, BLOOD, 0.5)
        if arms[1]:
            blade(cv, (sh[0], sh[1] - 1), 55 + 10 * sway, 17, 4.2, pal, 0.2)
        sl_torso(cv, (hip[0], hip[1]), (sh[0], sh[1]), pal)
        if head:
            skull(cv, hd, pal)
        if arms[0]:
            cv.limb([(sh[0] + 2, sh[1] + 1), (sh[0] + 7 + 2 * sway, sh[1] + 6)], 3.3, pal["flesh"], pal["dark"])
            blade(cv, (sh[0] + 7 + 2 * sway, sh[1] + 5), 75 - 20 * sway, 18, 4.6, pal, 0.1)
    return cv


def draw_sl_arm(cv, sh, mode, ph, atk, pal, front):
    """Blade arm; walking raises the scythes above the head (the 'opening' the wiki mentions), attacking swings them down."""
    if mode == "attack":
        a = 150 - 175 * atk if front else 120 - 140 * atk
    else:
        a = 12 + 20 * math.sin(ph * 6.283) if front else 22 * math.sin(ph * 6.283 + 1)
    r = math.radians(a)
    # a = degrees from vertical-up, forward positive
    el = (sh[0] + math.sin(r) * 6.5, sh[1] - math.cos(r) * 6.5 + 1)
    col = pal["flesh"] if front else shade(pal["flesh"], 0.78)
    cv.limb([(sh[0] + (1 if front else -1), sh[1] + 1), el], 3.6, col, pal["dark"], pal["light"])
    blade(cv, el, a * 0.95 + 8, 20, 4.8, pal, 0.18 if front else -0.1)


def slasher_dead(legs, arms, head, pal):
    cv = Cv(64, 20)
    pal = PALS[pal]
    # lying on its back, feet to the left
    cv.poly([(16, 12), (22, 7), (38, 7.5), (44, 11), (44, 15), (16, 16)], pal["flesh"], OUTLINE, 0.8)
    cv.poly([(26, 9), (36, 9), (35, 14), (27, 14)], MUSCLE, MUSCLE_D, 0.6)
    for k in range(3):
        cv.line([(27 + k * 3, 9.5), (28 + k * 3, 13.5)], BONE, 0.6)
    if legs[1]:
        cv.limb([(17, 13), (9, 12), (3, 15.5)], 4.0, shade(pal["flesh"], 0.85), pal["dark"])
    else:
        cv.ell(16, 13.5, 3, 2.4, MUSCLE, BLOOD, 0.4)
    if legs[0]:
        cv.limb([(18, 14), (11, 16), (4, 17.5)], 4.0, pal["flesh"], pal["dark"])
    if head:
        skull(cv, (50, 11), pal, eyes=False)
    else:
        cv.ell(45, 12, 2.5, 3.2, MUSCLE, BLOOD, 0.5)
    if arms[1]:
        cv.limb([(40, 9), (48, 6.5)], 3.0, shade(pal["flesh"], 0.8), pal["dark"])
        blade(cv, (47, 6.5), 80, 14, 3.8, pal)
    else:
        cv.ell(41, 9, 2, 1.6, MUSCLE, BLOOD, 0.4)
    if arms[0]:
        cv.limb([(38, 13), (46, 16)], 3.2, pal["flesh"], pal["dark"])
        blade(cv, (46, 16), 100, 16, 3.8, pal)
    else:
        cv.ell(39, 13, 2, 1.8, MUSCLE, BLOOD, 0.4)
    splat(cv, 30, 17, 9, BLOOD, 10, 5)
    return cv


# ---- Leaper -----------------------------------------------------------------------------------------
def leaper(tail, arms, head, mode, ph, pal, atk=0.0):
    """Low scorpion-tailed crawler; modes crawl, air, whip."""
    cv = Cv(64, 52)
    pal = PALS[pal]
    air = mode == "air"
    sway = math.sin(ph * 2 * math.pi)
    if air:
        hip, sh, hd = (22.0, 34.0), (38.0, 28.0), (46.0, 25.0)
    else:
        hip, sh, hd = (20.0, 42.0 - abs(sway) * 1.2), (35.0, 38.0 - abs(sway)), (43.0, 36.0 - abs(sway))
    # tail: the fused legs curve up and over the back, ending in a barbed blade
    if tail:
        if mode == "whip":
            t = atk
            pts = [(hip[0] - 1, hip[1] + 1), (hip[0] - 8, hip[1] - 4 - 8 * t), (hip[0] - 4 + 14 * t, hip[1] - 18 + 4 * t),
                   (hip[0] + 6 + 26 * t, hip[1] - 14 + 14 * t)]
        elif air:
            pts = [(hip[0], hip[1] + 1), (hip[0] - 9, hip[1] + 4), (hip[0] - 17, hip[1] + 2), (hip[0] - 24, hip[1] - 4)]
        else:
            pts = [(hip[0] - 1, hip[1] + 1), (hip[0] - 8, hip[1] - 3), (hip[0] - 7, hip[1] - 14 + sway * 2),
                   (hip[0] + 2, hip[1] - 20 + sway * 2)]
        cv.limb(pts, 4.2, pal["flesh"], pal["dark"], pal["light"])
        cv.limb(pts[1:], 2.6, shade(pal["flesh"], 0.85), pal["dark"])
        e = pts[-1]
        d = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
        ang = math.degrees(math.atan2(d[0], -d[1]))
        blade(cv, e, ang, 11, 3.8, pal)
    else:
        cv.ell(hip[0] - 1, hip[1] + 1, 3.6, 3.0, MUSCLE, BLOOD, 0.5)
    # rear haunches / back arm
    if arms[1]:
        if air:
            cv.limb([(sh[0] - 2, sh[1] + 1), (sh[0] + 9, sh[1] - 6), (sh[0] + 17, sh[1] - 9)], 3.2, shade(pal["flesh"], 0.8), pal["dark"])
        else:
            s = math.sin(ph * 6.283 + 3)
            cv.limb([(sh[0] - 3, sh[1]), (sh[0] + 2 + 2 * s, sh[1] + 7), (sh[0] + 5 + 5 * s, 50.5)], 3.2, shade(pal["flesh"], 0.8), pal["dark"])
            cv.poly([(sh[0] + 5 + 5 * s, 50.5), (sh[0] + 11 + 5 * s, 51), (sh[0] + 10 + 5 * s, 52)], BONE)
    # torso: a thin arched spine
    cv.poly([(hip[0] - 3, hip[1] + 1), (hip[0] + 3, hip[1] - 4), (sh[0] + 1, sh[1] - 3), (sh[0] + 4, sh[1] + 3),
             (hip[0] + 4, hip[1] + 3)], pal["flesh"], OUTLINE, 0.8)
    cv.poly([(hip[0] + 5, hip[1] - 1), (sh[0] - 3, sh[1] - 0.5), (sh[0] - 3, sh[1] + 3), (hip[0] + 5, hip[1] + 2)], MUSCLE, MUSCLE_D, 0.5)
    for k in range(6):
        t = k / 5
        cv.ell(hip[0] + (sh[0] - hip[0]) * t, hip[1] - 3 - math.sin(t * 3.14) * 2 + (sh[1] - hip[1]) * t, 1.0, 0.9, BONE_D, OUTLINE, 0.3)
    if head:
        cv.ell(hd[0], hd[1], 4.2, 3.6, pal["flesh"], OUTLINE, 0.7)
        # four bone fangs on multi-jointed jaw arms (wiki: two upper appendages + split lower jaw)
        for k, dy in enumerate((-0.5, 0.8, 2.0, 3.0)):
            cv.poly([(hd[0] + 2.5, hd[1] + dy), (hd[0] + 8.5, hd[1] + dy + 1.8), (hd[0] + 3.5, hd[1] + dy + 1.4)], BONE, OUTLINE, 0.3)
        cv.glow(hd[0] + 1.5, hd[1] - 1.0, 3, pal["eye"], 0.7)
        cv.ell(hd[0] + 1.5, hd[1] - 1.0, 0.9, 0.9, pal["eye"])
    else:
        cv.ell(sh[0] + 4, sh[1] - 1, 2.2, 2.6, MUSCLE, BLOOD, 0.5)
    if arms[0]:
        if air:
            cv.limb([(sh[0] + 2, sh[1] + 1), (sh[0] + 11, sh[1] - 1), (sh[0] + 18, sh[1] - 3)], 3.4, pal["flesh"], pal["dark"])
        else:
            s = math.sin(ph * 6.283)
            cv.limb([(sh[0] + 2, sh[1]), (sh[0] + 7 + 2 * s, sh[1] + 7), (sh[0] + 10 + 5 * s, 50.5)], 3.4, pal["flesh"], pal["dark"])
            cv.poly([(sh[0] + 10 + 5 * s, 50.5), (sh[0] + 16 + 5 * s, 51), (sh[0] + 15 + 5 * s, 52.5)], BONE)
    return cv


def leaper_dead(tail, arms, head, pal):
    cv = Cv(60, 16)
    p = PALS[pal]
    cv.poly([(20, 10), (26, 5), (42, 6), (46, 10), (44, 14), (20, 14)], p["flesh"], OUTLINE, 0.8)
    cv.poly([(28, 7), (40, 7.5), (39, 11), (29, 11)], MUSCLE, MUSCLE_D, 0.5)
    if tail:
        cv.limb([(20, 11), (12, 12), (5, 9)], 3.8, p["flesh"], p["dark"])
        blade(cv, (5, 9), -40, 9, 3.2, p)
    else:
        cv.ell(19, 11, 2.5, 2.6, MUSCLE, BLOOD, 0.4)
    if head:
        cv.ell(50, 9, 4.2, 3.4, p["flesh"], OUTLINE, 0.7)
        for dy in (0, 1.6, 3):
            cv.poly([(52, 8 + dy), (58, 9.5 + dy), (53, 9.3 + dy)], BONE)
    else:
        cv.ell(46, 10, 2, 2.6, MUSCLE, BLOOD, 0.4)
    if arms[0]:
        cv.limb([(40, 12), (47, 14.5), (52, 14.5)], 3.2, p["flesh"], p["dark"])
    if arms[1]:
        cv.limb([(38, 8), (44, 5.5), (48, 5)], 3.0, shade(p["flesh"], 0.8), p["dark"])
    splat(cv, 30, 14, 8, BLOOD, 9, 2)
    return cv


# ---- Lurker: ceiling crawler with three tendrils ------------------------------------------------------
def lurker(tendrils, mode, ph, pal="grey"):
    """Hangs upside-down from the ceiling; tendrils (3 flags) fan out behind and fire barbs. mode: hang, fire."""
    cv = Cv(56, 40)
    p = PALS[pal]
    sw = math.sin(ph * 2 * math.pi)
    body = (28.0, 12.0 + sw * 0.8)
    # clinging legs hooked up to the ceiling
    for k, dx in enumerate((-9, -4, 5, 10)):
        s = math.sin(ph * 6.283 + k * 1.7)
        cv.limb([(body[0] + dx * 0.6, body[1] - 1), (body[0] + dx + s * 1.5, body[1] - 6), (body[0] + dx * 1.3 + s * 3, 0.8)],
                2.0, shade(p["flesh"], 0.8), p["dark"])
    for i, ok in enumerate(tendrils):
        if not ok:
            cv.ell(body[0] - 5 + i * 5, body[1] + 3, 1.8, 1.8, MUSCLE, BLOOD, 0.4)
            continue
        base = (body[0] - 6 + i * 6, body[1] + 3)
        reach = 20 + (6 if mode == "fire" else 0)
        pts = [base]
        for k in range(1, 6):
            t = k / 5
            pts.append((base[0] + (i - 1) * 7 * t + math.sin(t * 5 + ph * 6.28 + i) * 3, base[1] + reach * t))
        cv.limb(pts, 2.2, p["flesh"], p["dark"], p["light"])
        e = pts[-1]
        cv.poly([(e[0] - 1.6, e[1] - 1), (e[0] + 1.6, e[1] - 1), (e[0], e[1] + 5)], BONE, OUTLINE, 0.4)
    cv.poly([(body[0] - 9, body[1] - 1), (body[0] + 8, body[1] - 3), (body[0] + 10, body[1] + 3), (body[0] - 8, body[1] + 5)],
            p["flesh"], OUTLINE, 0.8)
    cv.poly([(body[0] - 6, body[1] + 0), (body[0] + 6, body[1] - 1), (body[0] + 6, body[1] + 3), (body[0] - 5, body[1] + 3.6)],
            MUSCLE, MUSCLE_D, 0.5)
    cv.ell(body[0] + 11, body[1] + 2, 3.8, 3.6, p["flesh"], OUTLINE, 0.7)
    cv.glow(body[0] + 12.5, body[1] + 1.5, 3.2, p["eye"], 0.8)
    cv.ell(body[0] + 12.5, body[1] + 1.5, 0.9, 0.9, p["eye"])
    return cv


def infector(ph, pal="enh"):
    cv = Cv(30, 20)
    p = PALS[pal]
    sw = math.sin(ph * 2 * math.pi)
    pts = [(4, 11), (9, 10 + sw * 2), (15, 10 - sw * 2), (21, 10 + sw), (25, 9)]
    cv.limb(pts, 6.0, (110, 120, 70), (30, 36, 20), (170, 190, 100))
    for k in range(5):
        cv.ell(pts[k][0], pts[k][1] - 2.6, 1.0, 1.3, (200, 190, 90), OUTLINE, 0.3)
    cv.limb([(25, 9), (28.5, 8)], 1.2, (230, 220, 120), (60, 50, 20))
    cv.glow(24, 8.4, 3, (255, 220, 80), 0.9)
    cv.ell(24, 8.4, 1.1, 1.1, (255, 240, 140))
    for k in range(3):
        cv.limb([(7 + k * 5, 13), (6 + k * 5 + sw * 2, 17)], 1.0, (90, 100, 50))
    return cv


def exploder(bulb, ph, mode="run", pul=0.0):
    cv = Cv(44, 56)
    p = PALS["pale"]
    s = math.sin(ph * 6.283)
    hip, sh, hd = (20.0, 38.0), (24.0, 24.0), (28.0, 18.0)
    for front in (False, True):
        sw = s if front else -s
        knee = (hip[0] + 2 + 4 * sw, hip[1] + 8)
        foot = (knee[0] - 3 + 3 * sw, 56 - 1.5 + (0 if (sw < 0.5) else -3))
        col = p["flesh"] if front else shade(p["flesh"], 0.8)
        cv.limb([hip, knee, foot], 4.0, col, p["dark"], p["light"])
    cv.poly([(hip[0] - 4, hip[1] + 2), (sh[0] - 5, sh[1] + 2), (sh[0] + 3, sh[1] - 2), (sh[0] + 5, sh[1] + 4), (hip[0] + 4, hip[1])],
            p["flesh"], OUTLINE, 0.8)
    cv.poly([(hip[0] - 2, hip[1] - 3), (hip[0] + 3, hip[1] - 4), (hip[0] + 3, hip[1] - 12), (hip[0] - 1, hip[1] - 12)], MUSCLE, MUSCLE_D, 0.5)
    skull(cv, hd, p)
    # the left arm is a swollen, glowing yellow bulb: the thing that makes it an Exploder
    if bulb:
        r = 7.0 + pul * 2.2
        ax = (sh[0] + 7, sh[1] + 5)
        cv.limb([(sh[0] + 3, sh[1] + 1), ax], 3.4, p["flesh"], p["dark"])
        cv.glow(ax[0] + 6, ax[1] + 3, r + 3, (255, 200, 40), 0.9 + pul)
        cv.ell(ax[0] + 6, ax[1] + 3, r, r * 0.95, (230, 170, 30), (110, 60, 10), 0.8)
        cv.ell(ax[0] + 5, ax[1] + 1.4, r * 0.6, r * 0.55, (255, 226, 90))
        cv.ell(ax[0] + 4, ax[1], r * 0.28, r * 0.25, (255, 255, 200))
    else:
        cv.ell(sh[0] + 4, sh[1] + 3, 2.4, 2.4, MUSCLE, BLOOD, 0.4)
    cv.limb([(sh[0] - 3, sh[1] + 2), (sh[0] - 1 + s * 3, sh[1] + 11), (sh[0] + 2 + s * 4, sh[1] + 17)], 3.0, shade(p["flesh"], 0.8), p["dark"])
    return cv


def pregnant(sacks, mode, ph):
    """sacks: 3 booleans (yellow egg sacks on the chest and belly)."""
    cv = Cv(56, 60)
    p = PALS["grey"]
    s = math.sin(ph * 6.283)
    hip, sh, hd = (28.0, 40.0), (30.0, 22.0), (33.0, 14.0)
    for front in (False, True):
        sw = s if front else -s
        knee = (hip[0] + 1 + 3 * sw, hip[1] + 9)
        foot = (knee[0] - 2 + 3 * sw, 58.0)
        col = p["flesh"] if front else shade(p["flesh"], 0.8)
        cv.limb([(hip[0] - 1 + front * 3, hip[1]), knee, foot], 5.0, col, p["dark"], p["light"])
    # long arms hang to the knees, claw hands
    for front in (False, True):
        a = 14 + (30 if mode == "attack" and front else 0) + 8 * (s if front else -s)
        r = math.radians(a)
        shd = (sh[0] + (2 if front else -2), sh[1] + 1)
        el = (shd[0] + math.sin(r) * 9, shd[1] + math.cos(r) * 9)
        hand = (el[0] + math.sin(r + 0.4) * 10, el[1] + math.cos(r + 0.4) * 10)
        col = p["flesh"] if front else shade(p["flesh"], 0.75)
        cv.limb([shd, el, hand], 3.4, col, p["dark"], p["light"])
        for k in (-1, 0, 1):
            cv.line([hand, (hand[0] + 3 + k * 1.2, hand[1] + 4 + abs(k))], BONE, 0.7)
    cv.poly([(hip[0] - 7, hip[1] + 3), (sh[0] - 7, sh[1] + 2), (sh[0] + 3, sh[1] - 3), (sh[0] + 8, sh[1] + 6), (hip[0] + 9, hip[1] + 2)],
            p["flesh"], OUTLINE, 0.9)
    cv.poly([(hip[0] - 3, hip[1] - 14), (hip[0] + 4, hip[1] - 14), (hip[0] + 5, hip[1] - 2), (hip[0] - 2, hip[1] - 2)], MUSCLE, MUSCLE_D, 0.5)
    spots = [(sh[0] + 2, sh[1] + 7, 4.4), (sh[0] - 3, sh[1] + 13, 4.8), (sh[0] + 5, sh[1] + 16, 3.6)]
    for ok, (x, y, r) in zip(sacks, spots):
        if ok:
            cv.glow(x, y, r + 3, (255, 210, 60), 0.9)
            cv.ell(x, y, r, r, (232, 180, 40), (120, 70, 10), 0.7)
            cv.ell(x - 0.9, y - 1.0, r * 0.55, r * 0.5, (255, 232, 110))
            cv.ell(x - 1.4, y - 1.6, r * 0.2, r * 0.2, (255, 255, 220))
        else:
            cv.ell(x, y, r * 0.55, r * 0.5, MUSCLE, BLOOD, 0.4)
    skull(cv, hd, p, big=1.0)
    return cv


def spawn(ph):
    cv = Cv(20, 12)
    p = PALS["enh"]
    s = math.sin(ph * 6.283)
    cv.poly([(3, 8), (6, 4), (13, 4), (17, 7), (14, 10), (4, 10)], (150, 130, 60), OUTLINE, 0.6)
    cv.ell(14, 6.5, 1.0, 1.0, (255, 220, 80))
    for k in range(3):
        cv.line([(5 + k * 4, 9.5), (4 + k * 4 + s * 1.6, 11.5)], (90, 76, 30), 0.8)
    return cv


def brute(mode, ph, pal="dark", atk=0.0):
    """Armoured hulk made of several corpses. Armour faces +x (toward Isaac); weak glowing spots on the back."""
    cv = Cv(84, 76)
    p = PALS[pal]
    s = math.sin(ph * 6.283)
    low = 1 if mode == "charge" else 0
    hip = (38.0, 48.0 + (1.5 if low else 0))
    sh = (46.0 + low * 7, 28.0 + low * 8)
    for front in (False, True):
        sw = s if front else -s
        knee = (hip[0] + 4 + 7 * sw, hip[1] + 11)
        foot = (knee[0] - 3 + 4 * sw, 74.0 - (0 if sw < 0.3 else 3))
        col = p["flesh"] if front else shade(p["flesh"], 0.8)
        cv.limb([(hip[0] + (3 if front else -3), hip[1]), knee, foot], 8.0, col, p["dark"], p["light"])
        cv.poly([(foot[0] - 3, foot[1] - 3), (foot[0] + 9, foot[1] - 1), (foot[0] + 9, foot[1] + 2), (foot[0] - 3, foot[1] + 2)], shade(col, 0.7), OUTLINE, 0.5)
    # back arm (smaller, behind)
    cv.limb([(sh[0] - 6, sh[1] + 3), (sh[0] - 8 + s * 3, sh[1] + 15), (sh[0] - 3 + s * 6, sh[1] + 26)], 6.0, shade(p["flesh"], 0.75), p["dark"])
    # hunched torso mass
    cv.poly([(hip[0] - 12, hip[1] + 4), (sh[0] - 18, sh[1] + 2), (sh[0] - 8, sh[1] - 12), (sh[0] + 8, sh[1] - 11),
             (sh[0] + 15, sh[1] + 6), (hip[0] + 11, hip[1] + 3)], p["flesh"], OUTLINE, 1.0)
    cv.poly([(hip[0] - 4, hip[1] - 4), (hip[0] + 9, hip[1] - 2), (hip[0] + 6, hip[1] - 16), (hip[0] - 3, hip[1] - 14)], MUSCLE, MUSCLE_D, 0.6)
    # glowing yellow weak spots on the back and shoulder: only these hurt it (design from the Brute fight)
    for (x, y, r) in ((sh[0] - 14, sh[1] + 2, 2.8), (sh[0] - 11, sh[1] + 10, 2.4), (hip[0] - 9, hip[1] - 4, 2.2)):
        cv.glow(x, y, r + 3, (255, 210, 60), 0.9)
        cv.ell(x, y, r, r, (255, 214, 70), (140, 80, 10), 0.5)
    # head, low and wedge-shaped between the shoulders
    hd = (sh[0] + 8 + low * 3, sh[1] - 4 + low * 3)
    cv.ell(hd[0], hd[1], 5.4, 5.0, p["flesh"], OUTLINE, 0.8)
    cv.glow(hd[0] + 2.5, hd[1] - 1, 4, p["eye"], 0.8)
    cv.ell(hd[0] + 2.6, hd[1] - 1, 1.2, 1.2, p["eye"])
    # front armour: slabs of bone plate on the forearm and shoulder
    a = 8 + 55 * atk if mode == "attack" else 25 + 10 * s
    r = math.radians(a)
    el = (sh[0] + 5 + math.sin(r) * 10, sh[1] + 5 + math.cos(r) * 10)
    hand = (el[0] + math.sin(r + 0.3) * 11, el[1] + math.cos(r + 0.3) * 11)
    cv.limb([(sh[0] + 4, sh[1] + 3), el], 8.0, p["flesh"], p["dark"], p["light"])
    cv.limb([el, hand], 7.0, shade(p["flesh"], 0.95), p["dark"], p["light"])
    cv.poly([(el[0] - 4, el[1] - 4), (hand[0] + 5, hand[1] - 4), (hand[0] + 6, hand[1] + 3), (el[0] - 3, el[1] + 4)], BONE, OUTLINE, 0.8)
    cv.poly([(el[0] - 2, el[1] - 2), (hand[0] + 3, hand[1] - 3), (hand[0] + 3, hand[1]), (el[0] - 1, el[1] + 1)], (236, 230, 208))
    cv.poly([(sh[0] + 2, sh[1] - 10), (sh[0] + 14, sh[1] - 4), (sh[0] + 14, sh[1] + 8), (sh[0] + 2, sh[1] + 6)], BONE_D, OUTLINE, 0.8)
    for k in range(3):
        cv.line([(sh[0] + 4, sh[1] - 6 + k * 4), (sh[0] + 12, sh[1] - 3 + k * 4)], BONE, 0.7)
    return cv


def hunter(arms, legs, mode, ph, atk=0.0):
    """Tall, regenerating hunter: huge claws, dripping flesh. arms/legs = (front, back) flags."""
    cv = Cv(76, 90)
    p = dict(flesh=(108, 112, 104), dark=(44, 48, 44), light=(160, 166, 150), muscle=(156, 40, 40), eye=(255, 220, 90))
    s = math.sin(ph * 6.283)
    hip, sh, hd = (34.0, 52.0), (42.0, 30.0), (48.0, 21.0)
    for front in (False, True):
        ok = legs[1 if not front else 0]
        if not ok:
            continue
        sw = s if front else -s
        knee = (hip[0] + 5 + 6 * sw, hip[1] + 14)
        ank = (knee[0] - 7 + 4 * sw, knee[1] + 14)
        toe = (ank[0] + 8, 88.0)
        ank = (ank[0], min(ank[1], 85))
        col = p["flesh"] if front else shade(p["flesh"], 0.8)
        cv.limb([(hip[0] + (2 if front else -2), hip[1]), knee, ank, toe], 5.4, col, p["dark"], p["light"])
    for front in (False, True):
        if not arms[0 if front else 1]:
            continue
        if mode == "attack":
            a = (160 - 150 * atk) if front else (140 - 120 * atk)
        else:
            a = 40 + 30 * (s if front else -s) + (0 if front else 10)
        r = math.radians(a)
        shd = (sh[0] + (2 if front else -3), sh[1] + 2)
        el = (shd[0] + math.sin(r) * 15, shd[1] + math.cos(r) * 15) if mode != "attack" else (shd[0] + math.sin(r) * 15, shd[1] - math.cos(r) * 15 * 0.0 + math.cos(r) * 15)
        hand = (el[0] + math.sin(r + 0.5) * 17, el[1] + math.cos(r + 0.5) * 17)
        col = p["flesh"] if front else shade(p["flesh"], 0.75)
        cv.limb([shd, el, hand], 4.2, col, p["dark"], p["light"])
        for k in (-1, 0, 1):
            d = (hand[0] + math.sin(r + 0.5 + k * 0.45) * 12, hand[1] + math.cos(r + 0.5 + k * 0.45) * 12)
            cv.limb([hand, d], 1.8, BONE_D, OUTLINE, BONE)
    cv.poly([(hip[0] - 5, hip[1] + 3), (sh[0] - 7, sh[1] + 2), (sh[0] + 1, sh[1] - 5), (sh[0] + 6, sh[1] + 5), (hip[0] + 5, hip[1] + 2)],
            p["flesh"], OUTLINE, 0.9)
    cv.poly([(hip[0] - 2, hip[1] - 4), (hip[0] + 3, hip[1] - 4), (hip[0] + 4, hip[1] - 14), (hip[0] - 1, hip[1] - 14)], MUSCLE, MUSCLE_D, 0.5)
    cv.ell(hd[0], hd[1], 5.0, 5.6, p["flesh"], OUTLINE, 0.8)
    for k in range(3):
        cv.line([(hd[0] - 1 + k * 1.8, hd[1] + 2), (hd[0] - 1.5 + k * 1.8, hd[1] + 7 + k)], BONE, 0.6)
    cv.glow(hd[0] + 2.4, hd[1] - 1.4, 3.6, p["eye"], 0.9)
    cv.ell(hd[0] + 2.4, hd[1] - 1.4, 1.1, 1.1, p["eye"])
    return cv


# ---- bosses ----------------------------------------------------------------------------------------------------
def leviathan_body():
    cv = Cv(150, 190)
    c = dict(flesh=(78, 62, 68), dark=(28, 18, 24), light=(130, 100, 102))
    # a vast mass pushing out of the wall, with a ragged mouth
    cv.ell(100, 120, 62, 82, c["dark"])
    cv.ell(104, 118, 56, 76, c["flesh"], c["dark"], 1.2)
    cv.ell(94, 96, 36, 46, c["light"])
    cv.ell(96, 104, 32, 40, c["flesh"])
    cv.ell(70, 128, 30, 40, (22, 8, 12), (60, 20, 24), 1.4)
    for k in range(14):
        a = k / 14 * 6.28
        cv.poly([(70 + math.cos(a) * 28, 128 + math.sin(a) * 38), (70 + math.cos(a + 0.2) * 28, 128 + math.sin(a + 0.2) * 38),
                 (70 + math.cos(a + 0.1) * 18, 128 + math.sin(a + 0.1) * 26)], BONE, OUTLINE, 0.3)
    for k in range(9):
        cv.ell(112 + (k % 3) * 11, 60 + k * 12, 3.2, 3.2, (50, 30, 36), (20, 10, 14), 0.5)
    return cv


def hive_body():
    cv = Cv(210, 190)
    c = dict(flesh=(96, 56, 62), dark=(32, 14, 20), light=(160, 96, 96))
    cv.ell(110, 110, 96, 84, c["dark"])
    cv.ell(110, 108, 90, 78, c["flesh"], c["dark"], 1.4)
    cv.ell(100, 84, 62, 44, c["light"])
    cv.ell(104, 90, 56, 38, c["flesh"])
    # dozens of eye-like nodules and veins: the Hive Mind is a mass of fused bodies
    import random
    rnd = random.Random(5)
    for k in range(36):
        x, y = 30 + rnd.random() * 160, 20 + rnd.random() * 150
        r = rnd.random() * 3 + 1.6
        cv.ell(x, y, r, r, (200, 60, 60), (60, 10, 16), 0.5)
        cv.ell(x, y, r * 0.4, r * 0.4, (255, 220, 160))
    for k in range(7):
        cv.limb([(110, 60 + k * 14), (80 + rnd.random() * 60, 70 + k * 12), (50 + rnd.random() * 110, 90 + k * 10)], 1.5, (150, 50, 60), (50, 10, 20))
    # mouth with fangs low on the body
    cv.ell(78, 130, 40, 30, (24, 6, 10), (70, 16, 20), 1.5)
    for k in range(16):
        a = 3.14 + k / 16 * 6.28
        cv.poly([(78 + math.cos(a) * 38, 130 + math.sin(a) * 28), (78 + math.cos(a + 0.2) * 38, 130 + math.sin(a + 0.2) * 28),
                 (78 + math.cos(a + 0.1) * 24, 130 + math.sin(a + 0.1) * 18)], BONE, OUTLINE, 0.3)
    return cv


def bulb(size=8):
    cv = Cv(size * 2 + 6, size * 2 + 6)
    c = size + 3
    cv.glow(c, c, size + 2, (255, 190, 50), 1.0)
    cv.ell(c, c, size * 0.8, size * 0.8, (240, 180, 40), (110, 60, 10), 0.8)
    cv.ell(c - 1, c - 1, size * 0.5, size * 0.45, (255, 232, 120))
    cv.ell(c - 1.6, c - 1.8, size * 0.2, size * 0.18, (255, 255, 220))
    return cv


# ---- flying pieces ---------------------------------------------------------------------------------------------
def piece(kind, pal="pale"):
    p = PALS[pal]
    if kind == "blade":
        cv = Cv(34, 12)
        cv.limb([(2, 6), (9, 6)], 3.6, p["flesh"], p["dark"], p["light"])
        blade(cv, (8, 6), 90, 24, 4.6, p, 0.1)
        cv.ell(2, 6, 2.0, 2.4, MUSCLE, BLOOD, 0.4)
    elif kind == "leg":
        cv = Cv(30, 14)
        cv.limb([(3, 4), (12, 7), (20, 5), (27, 8)], 3.6, p["flesh"], p["dark"], p["light"])
        cv.ell(3, 4, 2.2, 2.4, MUSCLE, BLOOD, 0.4)
    elif kind == "head":
        cv = Cv(16, 14)
        skull(cv, (8, 7), p, eyes=False)
        cv.ell(4, 10, 2.2, 2.0, MUSCLE, BLOOD, 0.4)
    elif kind == "claw":
        cv = Cv(34, 14)
        cv.limb([(3, 7), (14, 7), (22, 6)], 3.6, p["flesh"], p["dark"], p["light"])
        for k in (-1, 0, 1):
            cv.limb([(22, 6), (32, 6 + k * 3)], 1.5, BONE_D, OUTLINE, BONE)
        cv.ell(3, 7, 2.2, 2.4, MUSCLE, BLOOD, 0.4)
    elif kind == "tail":
        cv = Cv(34, 14)
        cv.limb([(3, 8), (11, 6), (20, 8)], 3.8, p["flesh"], p["dark"], p["light"])
        blade(cv, (19, 8), 90, 13, 3.6, p)
    elif kind == "tendril":
        cv = Cv(30, 10)
        cv.limb([(2, 5), (10, 3), (18, 6), (25, 4)], 2.2, p["flesh"], p["dark"], p["light"])
        cv.poly([(24, 2), (24, 6.4), (30, 4.2)], BONE, OUTLINE, 0.3)
    elif kind == "bulb":
        cv = Cv(18, 18)
        cv.glow(9, 9, 8, (255, 190, 50), 0.9)
        cv.ell(9, 9, 5.5, 5.5, (240, 180, 40), (110, 60, 10), 0.8)
        cv.ell(8, 8, 3, 2.8, (255, 232, 120))
    elif kind == "sack":
        cv = Cv(14, 14)
        cv.ell(7, 7, 5, 5, (232, 180, 40), (120, 70, 10), 0.7)
        cv.ell(6, 6, 2.8, 2.6, (255, 232, 110))
    elif kind == "canister":
        cv = Cv(14, 20)
        cv.rect(2, 3, 12, 19, (150, 50, 40), OUTLINE)
        cv.rect(2, 7, 12, 10, (230, 190, 40))
        cv.rect(4, 0.5, 10, 3, STEEL_D, OUTLINE)
        cv.rect(3.4, 12, 6.4, 18, (190, 90, 70))
    else:
        raise ValueError(kind)
    return cv


def rot_variants(cv, n=8):
    """n rotations of a piece about its centre, trimmed; each as a packed sprite."""
    out = []
    w, h = cv.w, cv.h
    side = int(math.hypot(w, h)) + 2
    big = Image.new("RGBA", (side * SS, side * SS), (0, 0, 0, 0))
    big.paste(cv.im, ((side - w) * SS // 2, (side - h) * SS // 2))
    for i in range(n):
        im = big.rotate(i * 360 / n, resample=Image.BICUBIC)
        sp, _ = crop_pack(downsample(im))
        out.append(sp)
    return out


def ctentacle(pose, node=True):
    """Tentacle hanging from the ceiling. pose 0/1 idle sway, 2 drawn up (wind-up), 3 slammed onto the floor."""
    cv = Cv(44, 232)
    c = dict(flesh=(88, 70, 74), dark=(34, 22, 28), light=(140, 108, 106))
    paths = [
        [(22, 0), (26, 40), (18, 80), (24, 120), (20, 150)],
        [(22, 0), (18, 40), (26, 80), (20, 120), (24, 152)],
        [(22, 0), (30, 22), (12, 48), (30, 66), (24, 84)],
        [(22, 0), (22, 60), (21, 130), (22, 190), (22, 228)],
    ]
    pts = paths[pose]
    dense = []
    for i in range(len(pts) - 1):
        for k in range(10):
            t = k / 10
            dense.append((pts[i][0] * (1 - t) + pts[i + 1][0] * t, pts[i][1] * (1 - t) + pts[i + 1][1] * t))
    dense.append(pts[-1])
    n = len(dense)
    for i in range(n - 1):
        w = 13 * (1 - i / n * 0.7) + 3
        cv.line([dense[i], dense[i + 1]], c["dark"], w + 1.2)
    for i in range(n - 1):
        w = 13 * (1 - i / n * 0.7) + 3
        cv.line([dense[i], dense[i + 1]], c["flesh"], w - 0.6)
        if i % 5 == 0:
            cv.ell(dense[i][0] - w * 0.2, dense[i][1], w * 0.24, 1.0, c["light"])
    for i in range(3, n - 4, 5):
        cv.ell(dense[i][0] + 2.5, dense[i][1], 0.9, 0.9, (66, 40, 44))
    tip = dense[-1]
    cv.poly([(tip[0] - 2.4, tip[1] - 1), (tip[0] + 2.4, tip[1] - 1), (tip[0] + 0.5, tip[1] + 6)], BONE, OUTLINE, 0.4)
    cv.node = dense[int(n * 0.62)]
    if node:
        x, y = cv.node
        cv.glow(x, y, 8.5, (255, 200, 40), 0.9)
        cv.ell(x, y, 4.4, 4.4, (240, 190, 40), (110, 60, 10), 0.7)
        cv.ell(x - 0.8, y - 0.8, 2.6, 2.4, (255, 235, 120))
    return cv
