# Isaac Clarke in his engineer RIG, drawn procedurally: skeleton poses -> shaded RGBA -> packed sprites.
# Every frame lives on the same 48x60 canvas with the feet at (24, 58), so the game can swap poses freely.
import math
from g_deadspace_art import *

CW, CH = 48, 60
FOOT = (24, 58)
ELEV = (-30, -15, 0, 15, 30)   # aim elevation in degrees, as pre-baked arm poses


def pt(o, a, l):
    """Point at angle a (degrees from straight down, positive = forward) and length l."""
    r = math.radians(a)
    return (o[0] + math.sin(r) * l, o[1] + math.cos(r) * l)


def draw_leg(cv, hip, a1, a2, front):
    base = SUIT if front else shade(SUIT, 0.72)
    knee = pt(hip, a1, 8.6)
    foot = pt(knee, a2, 8.4)
    cv.limb([hip, knee], 6.2, base, SUIT_D, SUIT_L)
    cv.limb([knee, foot], 5.2, shade(base, 0.92), SUIT_D, SUIT_L)
    cv.ell(knee[0], knee[1], 3.1, 3.1, shade(base, 1.15), SUIT_D, 0.6)
    # orange hazard band on the shin: the engineer-class RIG marking
    mid = pt(knee, a2, 3.2)
    cv.ell(mid[0], mid[1], 2.3, 1.0, ORANGE)
    # boot points forward (+x) regardless of the shin angle
    cv.poly([(foot[0] - 2.2, foot[1] - 1.8), (foot[0] + 4.4, foot[1] - 0.6), (foot[0] + 4.6, foot[1] + 1.4),
             (foot[0] - 2.4, foot[1] + 1.4)], shade(base, 0.7), OUTLINE, 0.6)
    return knee, foot


def draw_arm(cv, sh, a1, a2, front):
    base = SUIT_L if front else shade(SUIT_L, 0.7)
    el = pt(sh, a1, 7.0)
    hand = pt(el, a2, 7.2)
    cv.limb([sh, el], 4.7, shade(base, 0.8), SUIT_D, SUIT_L)
    cv.limb([el, hand], 4.2, shade(base, 0.7), SUIT_D, SUIT_L)
    cv.ell(hand[0], hand[1], 2.1, 2.1, shade(SUIT_D, 1.6), OUTLINE, 0.5)
    return el, hand


def draw_head(cv, c, tilt=0.0, nohead=False):
    cx, cy = c
    # neck ring
    cv.rect(cx - 2.4, cy + 3.2, cx + 2.4, cy + 6.2, SUIT_D, OUTLINE)
    if nohead:
        cv.ell(cx, cy + 4.6, 2.6, 1.3, MUSCLE, BLOOD, 0.5)
        return
    cv.ell(cx, cy, 5.8, 6.2, shade(SUIT, 1.25), OUTLINE, 0.9)
    cv.ell(cx - 0.8, cy - 1.0, 4.0, 4.2, shade(SUIT_L, 1.0))
    # visor: a narrow lit slit with a bright core; it is Isaac's face, the glow is what the eye finds first
    vx, vy = cx + 2.6, cy - 0.3
    cv.glow(vx, vy, 5.0, VISOR, 0.8)
    cv.ell(vx, vy, 2.2, 3.0, shade(VISOR, 0.55), OUTLINE, 0.45)
    cv.ell(vx + 0.2, vy - 0.4, 1.3, 2.1, VISOR)
    cv.ell(vx + 0.4, vy - 0.9, 0.6, 1.0, (235, 255, 255))
    # helmet lamp on the crown
    cv.ell(cx + 0.8, cy - 5.2, 1.6, 0.9, (255, 244, 200), OUTLINE, 0.4)


def draw_torso(cv, hip, sh, lean):
    # chest plate: wide at the shoulder, narrow at the hip, with the back edge on the left
    bx_hip, bx_sh = hip[0] - 5.0, sh[0] - 6.2
    fx_hip, fx_sh = hip[0] + 4.2, sh[0] + 5.8
    poly = [(bx_hip, hip[1]), (bx_sh, sh[1] + 1), (sh[0] - 3.0, sh[1] - 2.2), (sh[0] + 3.4, sh[1] - 2.2),
            (fx_sh, sh[1] + 1.5), (fx_hip + 0.8, hip[1] - 4), (fx_hip, hip[1])]
    cv.poly(poly, SUIT, OUTLINE, 0.9)
    # chest highlight and plate seam
    cv.poly([(sh[0] - 2.6, sh[1] - 0.8), (sh[0] + 3.8, sh[1] - 0.6), (sh[0] + 3.6, sh[1] + 5), (sh[0] - 2.0, sh[1] + 5.4)],
            shade(SUIT_L, 0.9))
    cv.line([(sh[0] - 4.8, sh[1] + 6.6), (sh[0] + 4.2, sh[1] + 6.2)], SUIT_D, 0.7)
    # belt with the engineer orange stripe
    cv.line([(bx_hip, hip[1] - 1.2), (fx_hip, hip[1] - 1.2)], ORANGE, 1.6)
    # pauldron
    cv.ell(sh[0] - 0.4, sh[1] + 0.6, 3.4, 3.2, shade(SUIT_L, 0.95), OUTLINE, 0.7)
    # spine channel along the back edge: the game fills it with the health segments
    top = (bx_sh + 0.9, sh[1] - 2.0)
    bot = (bx_hip + 0.4, hip[1] - 0.5)
    cv.limb([top, bot], 2.6, shade(SUIT_D, 0.9), OUTLINE, shade(SUIT_D, 1.8))
    return top, bot


def isaac(pose):
    cv = Cv(CW, CH)
    crouch = pose.get("crouch", 0.0)
    hip = (24.0 + pose.get("hipdx", 0.0), 40.0 + crouch)
    lean = pose.get("lean", 0.0)
    sh = (hip[0] + lean, hip[1] - 13.0 + pose.get("sh_dy", 0.0))
    head_c = (sh[0] + 1.0 + lean * 0.35 + pose.get("headdx", 0.0), sh[1] - 7.0)
    lb, lf = pose.get("legs", ((0, 0, 0, 0), (0, 0, 0, 0)))[0], pose.get("legs", ((0, 0, 0, 0), (0, 0, 0, 0)))[1]
    ab, af = pose.get("arms", ((20, 40), (30, 45)))
    dead_legs = pose.get("nolegs", False)
    # back arm and back leg are drawn first so the body overlaps them
    sh_arm = (sh[0] - 0.5, sh[1] + 1.3)
    draw_arm(cv, sh_arm, ab[0], ab[1], False)
    if not dead_legs:
        draw_leg(cv, (hip[0] - 1.0, hip[1]), lb[0], lb[1], False)
    top, bot = draw_torso(cv, hip, sh, lean)
    draw_head(cv, head_c, nohead=pose.get("nohead", False))
    if not dead_legs:
        draw_leg(cv, (hip[0] + 0.8, hip[1]), lf[0], lf[1], True)
    el, hand = draw_arm(cv, sh_arm, af[0], af[1], True)
    if pose.get("blood"):
        splat(cv, sh[0], sh[1], 5, BLOOD, 12, pose.get("seed", 1))
    meta = {"hand": (hand[0], hand[1]), "wang": pose.get("wang", None), "spine": (top, bot), "head": head_c,
            "shoulder": sh}
    return cv, meta


def leg_pair(phase, amp, bend):
    """Two legs (back, front) for a walk/run phase in [0,1)."""
    out = []
    for k in (0.5, 0.0):
        s = math.sin((phase + k) * 2 * math.pi)
        c = math.cos((phase + k) * 2 * math.pi)
        hipa = s * amp
        # the knee bends most while the leg swings forward
        kneea = hipa - bend * max(0.0, c) - 6
        out.append((hipa, kneea, 0, 0))
    return tuple((o[0], o[1]) for o in out)


def build_frames():
    """Returns {name: [(sprite, meta), ...]} facing right."""
    fr = {}

    def add(name, pose):
        cv, meta = isaac(pose)
        fr.setdefault(name, []).append((rgb565_bytes(cv.done()), meta))

    ready = ((24, 62), (34, 68))
    for i in range(2):
        add("idle", {"legs": ((-4, 0), (6, 0)), "arms": ((18, 40), (30 + i, 62)), "wang": -20, "sh_dy": 0.4 * i,
                     "headdx": 0.2 * i})
    for i in range(6):
        ph = i / 6
        add("walk", {"legs": leg_pair(ph, 24, 30), "arms": ((14 + 6 * math.sin(ph * 6.28), 40), (30, 62)),
                     "wang": -15, "lean": 1.0, "sh_dy": 0.5 * abs(math.sin(ph * 6.28))})
    for i in range(6):
        ph = i / 6
        add("run", {"legs": leg_pair(ph, 42, 60), "arms": ((-30 + 40 * math.sin(ph * 6.28), 70), (40, 80)),
                    "wang": 10, "lean": 3.4, "crouch": 1.0, "sh_dy": 1.0 * abs(math.sin(ph * 6.28))})
    for e in ELEV:
        a = 90 + e
        for rec in (0, 1):
            add("aim%d" % e if not rec else "shot%d" % e,
                {"legs": ((-8, -8), (8, 6)), "arms": ((a - 8, a + 2 - rec * 8), (a - rec * 5, a - rec * 5)), "wang": e,
                 "lean": 1.2 - rec * 1.0})
    # crouch-aim while the bot is firing at crawlers on the floor
    for i in range(3):
        add("reload", {"legs": ((-6, -6), (6, 4)), "arms": ((40, 100 + 25 * i), (70 + 10 * i, 150 - 20 * i)),
                       "wang": 70 + 15 * i, "lean": 0.5})
    st = [(0, 0), (60, 20), (-4, 0)]
    for i, hipa in enumerate((0, 78, 10)):
        legf = ((-10, -10), (hipa, -hipa * 0.1 + (30 if i == 1 else 0)))
        add("stomp", {"legs": legf, "arms": ((10, 30), (20, 50)), "wang": -30, "lean": -1.5 if i == 1 else 1.5,
                      "crouch": 0.8 if i == 2 else 0})
    for i, a in enumerate((150, 100, 40)):
        add("melee", {"legs": ((-8, -8), (8, 4)), "arms": ((a - 10, a), (a + 10, a + 20)), "wang": a - 90,
                      "lean": [-2, 1, 3][i]})
    add("hurt", {"legs": ((-14, -10), (14, 8)), "arms": ((-20, -10), (50, 20)), "lean": -3.5, "wang": -50, "headdx": -1.5})
    add("hurt", {"legs": ((-10, -8), (10, 6)), "arms": ((-10, 10), (40, 30)), "lean": -2.0, "wang": -40})
    add("kinesis", {"legs": ((-8, -8), (8, 6)), "arms": ((20, 50), (105, 110)), "wang": None, "lean": 1.0})
    add("stasis", {"legs": ((-8, -8), (8, 6)), "arms": ((60, 90), (95, 95)), "wang": None, "lean": 1.4})
    add("use", {"legs": ((-4, -4), (6, 4)), "arms": ((20, 60), (24, 130)), "wang": None})
    add("use", {"legs": ((-4, -4), (6, 4)), "arms": ((20, 60), (14, 150)), "wang": None})
    add("bench", {"legs": ((-4, -4), (6, 4)), "arms": ((50, 70), (80, 90)), "wang": None})
    # death: stagger, drop, the two ways Isaac is cut (head bitten off / torso split) and the body lying
    add("die", {"legs": ((-16, -16), (14, 10)), "arms": ((-30, -10), (60, 40)), "lean": -4.5, "wang": None, "blood": True})
    add("die", {"legs": ((-30, -50), (20, 40)), "arms": ((-60, -40), (50, 80)), "lean": -6, "crouch": 7, "wang": None,
                "blood": True})
    add("headless", {"legs": ((-16, -16), (14, 10)), "arms": ((-30, -10), (60, 40)), "lean": -1.5, "wang": None,
                     "nohead": True, "blood": True})
    return fr


def lying_bodies(headless):
    """The body lying on the floor, head to the left (he falls backwards)."""
    cv, meta = isaac({"legs": ((-4, 0), (6, 0)), "arms": ((8, 20), (20, 40)), "wang": None, "nohead": headless,
                      "blood": True, "seed": 4})
    im = cv.done()
    big = Image.new("RGBA", (CH, CH), (0, 0, 0, 0))
    big.paste(im, (6, 0))
    return big.rotate(90, resample=Image.BICUBIC)


def head_piece():
    cv = Cv(16, 16)
    draw_head(cv, (8, 8))
    return cv


def arm_piece():
    cv = Cv(20, 10)
    cv.limb([(2, 5), (9, 5), (16, 4)], 3.6, SUIT_L, SUIT_D, SUIT_L)
    cv.ell(16.5, 4, 2.2, 2.2, SUIT_D, OUTLINE, 0.4)
    splat(cv, 2, 5, 2.5, BLOOD, 5, 3)
    return cv


def weapon(kind, ang):
    """Weapon sprite pointing right at elevation ang (degrees), pivot at the grip; returns (sprite, grip_xy, muzzle_xy)."""
    cv = Cv(40, 40)
    cx, cy = 14.0, 20.0
    if kind == "pc":
        # Plasma Cutter 211-V: compact body, two alignment blades, three blue sight lamps on the front
        cv.poly([(cx - 5, cy - 3), (cx + 6, cy - 3.6), (cx + 12, cy - 2.4), (cx + 12, cy + 2.0), (cx + 6, cy + 3.4),
                 (cx - 5, cy + 3)], STEEL, OUTLINE, 0.8)
        cv.poly([(cx - 4, cy - 2.6), (cx + 10, cy - 2.4), (cx + 10, cy - 0.6), (cx - 4, cy - 0.6)], STEEL_L)
        cv.poly([(cx - 3, cy + 3), (cx + 1, cy + 3), (cx + 0.5, cy + 8), (cx - 3.5, cy + 8)], STEEL_D, OUTLINE, 0.6)
        cv.rect(cx + 12, cy - 5.2, cx + 15.5, cy - 3.6, STEEL_L, OUTLINE)
        cv.rect(cx + 12, cy + 2.4, cx + 15.5, cy + 4.0, STEEL_L, OUTLINE)
        for dy in (-4.4, -0.2, 3.2):
            cv.ell(cx + 13.2, cy + dy, 0.9, 0.9, (150, 220, 255))
        cv.ell(cx + 4, cy - 0.3, 2.0, 1.2, ORANGE)
        muz = (cx + 16, cy)
    else:
        # Pulse Rifle: long body, magazine drum below, hand guard
        cv.poly([(cx - 9, cy - 3), (cx + 8, cy - 4), (cx + 17, cy - 2.6), (cx + 17, cy + 1.8), (cx + 8, cy + 3.4),
                 (cx - 9, cy + 3.4)], shade(STEEL, 0.85), OUTLINE, 0.8)
        cv.poly([(cx - 8, cy - 2.6), (cx + 15, cy - 3.2), (cx + 15, cy - 1.2), (cx - 8, cy - 1.0)], STEEL_L)
        cv.ell(cx + 3, cy + 6.2, 3.8, 3.6, STEEL_D, OUTLINE, 0.7)
        cv.rect(cx + 8, cy - 1.6, cx + 17, cy + 0.2, ORANGE)
        cv.rect(cx + 17, cy - 2.2, cx + 20, cy + 1.0, STEEL_D, OUTLINE)
        cv.rect(cx - 12, cy - 2.4, cx - 8, cy + 2.4, STEEL_D, OUTLINE)
        muz = (cx + 20, cy - 0.6)
    im = cv.im.rotate(ang, resample=Image.BICUBIC, center=(cx * SS, cy * SS))
    # muzzle position after rotation (PIL rotates counter-clockwise for positive angles)
    r = math.radians(ang)
    dx, dy = muz[0] - cx, muz[1] - cy
    mx = cx + dx * math.cos(r) + dy * math.sin(r)
    my = cy - dx * math.sin(r) + dy * math.cos(r)
    return rgb565_bytes(downsample(im)), (cx, cy), (mx, my)
