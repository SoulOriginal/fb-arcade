# Styles and animation poses for every character; build functions return {anim: [pose, ...]}.
import math
from g_battletoads_art import *
from g_battletoads_chars import *

TOAD_SIZE = (200, 200, 168)
PIG_SIZE = (180, 170, 140)
WALKER_SIZE = (250, 250, 215)
RAT_SIZE = (140, 120, 90)
BOSS_SIZE = (360, 360, 310)

TOAD_A = dict(skin=(84, 192, 70), arm=(84, 192, 70), fist=(100, 205, 84), leg=(150, 92, 44), boot=(108, 64, 34),
              laces=(240, 232, 205), belly=(238, 210, 154), pants=(150, 92, 44), belt=(64, 38, 22), band=(196, 138, 52),
              thigh=18, shin=17, uarm=15, farm=14, torso=24, neck=10, armr=5.4, legr=6.3, fistr=7.2, bootr=(9.8, 6.4),
              head_fn=toad_head, torso_fn=toad_torso)
TOAD_B = dict(TOAD_A, skin=(70, 150, 235), arm=(70, 150, 235), fist=(92, 170, 245), leg=(46, 118, 84), pants=(46, 118, 84),
              boot=(40, 40, 70), belly=(246, 226, 176), band=(240, 190, 60), belt=(30, 60, 50))
PIG_A = dict(skin=(238, 156, 170), arm=(238, 156, 170), fist=(246, 176, 186), leg=(92, 112, 72), boot=(70, 50, 44),
             laces=(220, 220, 200), pants=(92, 112, 72), vest=(62, 94, 176), helmet=(150, 162, 184), spike=(210, 215, 225),
             thigh=16, shin=15, uarm=13, farm=12, torso=21, neck=9, armr=5, legr=5.8, fistr=6.6, bootr=(9, 6),
             head_fn=pig_head, torso_fn=pig_torso)
PIG_B = dict(PIG_A, skin=(222, 140, 150), arm=(222, 140, 150), fist=(236, 160, 170), vest=(46, 40, 52), helmet=(204, 54, 46),
             spike=(250, 210, 80), leg=(40, 40, 54), pants=(40, 40, 54), boot=(110, 40, 36), band=(250, 210, 80))
RAT_A = dict(skin=(150, 132, 122), arm=(150, 132, 122), fist=(170, 150, 140), leg=(90, 76, 70), pants=(90, 76, 70),
             boot=(70, 56, 52), laces=(200, 200, 190), thigh=13, shin=12, uarm=10, farm=9, torso=15, neck=7, armr=3.8, legr=4.4,
             fistr=5, bootr=(7, 4.6), head_fn=rat_head, torso_fn=rat_torso)
BOSS = dict(RAT_A, skin=(120, 106, 138), arm=(120, 106, 138), fist=(142, 126, 160), pants=(70, 60, 90), leg=(70, 60, 90),
            boot=(60, 44, 40), vest=(214, 168, 54), belt=(150, 40, 40), scar=True, band=(230, 190, 70))
WALKER = dict(skin=(176, 186, 202), arm=(150, 160, 178), fist=(70, 76, 96), leg=(110, 120, 140), shinc=(150, 160, 178),
              boot=(84, 90, 110), laces=(250, 140, 50), dark=(70, 76, 96), accent=(236, 132, 44), thigh=22, shin=24, uarm=13,
              farm=14, torso=22, neck=12, armr=3.4, legr=4.4, fistr=4.6, bootr=(14, 5.4), head_fn=walker_head,
              torso_fn=walker_torso)


def mixp(a, b, t):
    out = dict(a)
    for key, bv in b.items():
        av = a.get(key, bv)
        if isinstance(bv, tuple) and isinstance(av, tuple) and len(av) == len(bv):
            out[key] = tuple(av[i] + (bv[i] - av[i]) * t for i in range(len(bv)))
        elif isinstance(bv, (int, float)) and isinstance(av, (int, float)) and not isinstance(bv, bool):
            out[key] = av + (bv - av) * t
        else:
            out[key] = bv
    return out


def seq(keys, per):
    # Smoothly interpolated frames through the key poses; per = frames in each segment.
    frames = []
    for i in range(len(keys) - 1):
        n = per[i] if isinstance(per, (list, tuple)) else per
        for j in range(n):
            frames.append(mixp(keys[i], keys[i + 1], j / n))
    frames.append(keys[-1])
    return frames


def walk_frames(n, amp=36, arm=26, lean=10, base=None, speedlean=0):
    base = base or {}
    out = []
    for i in range(n):
        f = 2 * math.pi * i / n
        s, c = math.sin(f), math.cos(f)
        s2, c2 = -s, -c
        d = dict(lean=lean + speedlean, lF=(amp * s, 10 + 40 * max(0, c), 1.0), lB=(amp * s2, 10 + 40 * max(0, c2), 1.0),
                 aF=(-arm * s + 18, 88, 1.0), aB=(arm * s + 8, 96, 1.0), hy=0.8 * abs(s) - 0.8, mouth=0.0)
        d.update(base)
        out.append(d)
    return out


def toad_anims():
    G = dict(lF=(14, 16, 1.0), lB=(-14, 20, 1.0), aF=(26, 112, 1.0), aB=(-6, 104, 1.0))
    A = {}
    A["idle"] = [dict(G, lean=8 + 2 * math.sin(2 * math.pi * i / 6), hy=0.7 * math.sin(2 * math.pi * i / 6),
                      aF=(26 + 4 * math.sin(2 * math.pi * i / 6), 112, 1.0), mouth=0.1 * (i % 3 == 2)) for i in range(6)]
    A["walk"] = walk_frames(8, base=dict(mouth=0.12))
    # jabs: wind up, snap out, return
    j1 = [dict(G, lean=0, aF=(-30, 100, 1.1), hx=-3), dict(G, lean=16, aF=(86, 6, 1.25), hx=6, hipx=3, lF=(30, 40, 1.0), lB=(-24, 12, 1.0), mouth=0.5),
          dict(G, lean=14, aF=(86, 6, 1.3), hx=6, hipx=3, lF=(30, 40, 1.0), lB=(-24, 12, 1.0), mouth=0.5), dict(G, lean=10, aF=(50, 60, 1.0))]
    A["jab1"] = j1
    A["jab2"] = [dict(G, lean=0, aB=(-35, 100, 1.1), hx=-3), dict(G, lean=18, aB=(88, 4, 1.25), aF=(-10, 120, 1.0), hx=7, hipx=3, lF=(-16, 14, 1.0), lB=(30, 40, 1.0), mouth=0.5),
                 dict(G, lean=17, aB=(88, 4, 1.3), aF=(-10, 120, 1.0), hx=7, hipx=3, lF=(-16, 14, 1.0), lB=(30, 40, 1.0), mouth=0.5), dict(G, lean=10, aB=(40, 70, 1.0))]
    lunge = dict(lF=(52, 78, 1.0), lB=(-34, 6, 1.0), hipx=8)
    A["bigfist"] = seq([
        dict(G, lean=-6, aF=(-70, 40, 1.0), aB=(-30, 80, 1.0), lF=(20, 50, 1.0), lB=(-30, 60, 1.0), hx=-4, mouth=0.2),
        dict(G, lean=-10, aF=(-95, 25, 1.1), aB=(-40, 70, 1.0), lF=(26, 60, 1.0), lB=(-34, 66, 1.0), hx=-6, mouth=0.4),
        dict(G, **lunge, lean=10, aF=(70, 14, 1.9), hx=6, mouth=0.9),
        dict(G, **lunge, lean=22, aF=(88, 2, 3.4), aB=(-40, 90, 1.0), hx=10, mouth=1.0),
        dict(G, **lunge, lean=24, aF=(90, 0, 3.8), aB=(-44, 90, 1.0), hx=11, mouth=1.0),
        dict(G, lean=14, aF=(70, 20, 2.2), lF=(30, 50, 1.0), lB=(-20, 20, 1.0), hx=6, mouth=0.4),
        dict(G, lean=10, aF=(40, 70, 1.2))], [1, 1, 1, 1, 1, 1])
    kick = dict(lF=(92, 4, 1.0), lB=(-4, 26, 1.0))
    A["bigboot"] = seq([
        dict(G, lean=0, aF=(-30, 70, 1.0), aB=(30, 90, 1.0), lF=(-10, 80, 1.0), lB=(-4, 28, 1.0), mouth=0.3),
        dict(G, lean=-8, aF=(-40, 60, 1.0), aB=(60, 40, 1.0), lF=(50, 70, 1.4), lB=(-4, 30, 1.0), hx=-3, mouth=0.6),
        dict(G, lean=-14, aF=(-50, 50, 1.0), aB=(70, 30, 1.0), lF=(86, 8, 2.4), lB=(-4, 32, 1.0), hx=-4, mouth=1.0),
        dict(G, lean=-18, aF=(-56, 50, 1.0), aB=(76, 30, 1.0), lF=(92, 2, 3.4), lB=(-4, 34, 1.0), hx=-5, mouth=1.0),
        dict(G, lean=-18, aF=(-56, 50, 1.0), aB=(76, 30, 1.0), lF=(92, 2, 3.8), lB=(-4, 34, 1.0), hx=-5, mouth=1.0),
        dict(G, lean=-4, lF=(50, 70, 1.8), lB=(-4, 30, 1.0), mouth=0.4),
        dict(G, lean=6)], [1, 1, 1, 1, 1, 1])
    A["ram"] = seq([
        dict(G, lean=-6, hx=-4, hs=1.0, aF=(-20, 90, 1.0), horns=0),
        dict(G, lean=10, hx=2, hs=1.35, aF=(-10, 100, 1.0), horns=1, mouth=0.4, **lunge),
        dict(G, lean=24, hx=12, hy=2, hs=1.8, aF=(-30, 100, 1.0), horns=1, mouth=1.0, **lunge),
        dict(G, lean=28, hx=16, hy=3, hs=2.15, aF=(-36, 100, 1.0), horns=1, mouth=1.0, **lunge),
        dict(G, lean=28, hx=16, hy=3, hs=2.25, aF=(-36, 100, 1.0), horns=1, mouth=1.0, **lunge),
        dict(G, lean=16, hx=8, hs=1.5, horns=1, mouth=0.5),
        dict(G, lean=8, hs=1.1)], [1, 1, 1, 1, 1, 1])
    A["headbutt"] = [dict(G, lean=-4, hx=-3), dict(G, lean=34, hx=10, hy=2, hs=1.15, mouth=0.8, lF=(30, 50, 1.0), lB=(-24, 12, 1.0)),
                     dict(G, lean=36, hx=11, hy=2, hs=1.2, mouth=0.8, lF=(30, 50, 1.0), lB=(-24, 12, 1.0)), dict(G, lean=12)]
    up = dict(aF=(150, 40, 1.0), aB=(130, 50, 1.0), mouth=0.8)
    A["jumpup"] = [dict(lean=6, lF=(34, 88, 1.0), lB=(8, 70, 1.0), **up)]
    A["jumppeak"] = [dict(lean=4, lF=(46, 96, 1.0), lB=(14, 90, 1.0), aF=(120, 50, 1.0), aB=(100, 60, 1.0), mouth=0.5)]
    A["jumpfall"] = [dict(lean=4, lF=(12, 30, 1.0), lB=(-12, 40, 1.0), aF=(150, 30, 1.0), aB=(140, 36, 1.0), mouth=0.3)]
    A["land"] = [dict(lean=22, hx=3, lF=(40, 108, 1.0), lB=(-20, 100, 1.0), aF=(40, 60, 1.0), aB=(10, 70, 1.0), mouth=0.2),
                 dict(lean=14, lF=(24, 60, 1.0), lB=(-14, 54, 1.0), aF=(30, 90, 1.0), aB=(0, 90, 1.0))]
    A["jkick"] = seq([dict(lean=-6, lF=(60, 60, 1.2), lB=(-20, 100, 1.0), aF=(-40, 60, 1.0), aB=(60, 40, 1.0), mouth=0.6),
                      dict(lean=-18, lF=(92, 6, 2.6), lB=(-24, 80, 1.0), aF=(-60, 50, 1.0), aB=(70, 40, 1.0), mouth=1.0, hx=-4),
                      dict(lean=-20, lF=(94, 2, 3.0), lB=(-28, 80, 1.0), aF=(-64, 50, 1.0), aB=(74, 40, 1.0), mouth=1.0, hx=-5)], [1, 1])
    hurt = dict(lean=-22, hx=-7, hy=-2, htilt=-10, mouth=1.0, aF=(-50, 40, 1.0), aB=(40, 60, 1.0), lF=(26, 40, 1.0), lB=(-22, 20, 1.0))
    A["hurt"] = [hurt, dict(hurt, lean=-16, hx=-5)]
    A["fall"] = [dict(hurt, aF=(-70, 30, 1.0), aB=(70, 50, 1.0), lF=(50, 60, 1.0), lB=(10, 80, 1.0), rot=r) for r in (22, 62, 100, 150)]
    A["lie"] = [dict(hurt, aF=(-40, 60, 1.0), aB=(20, 80, 1.0), lF=(20, 40, 1.0), lB=(-10, 30, 1.0), rot=92, anchor=True, mouth=0.3)]
    A["getup"] = [dict(lean=52, hx=6, lF=(60, 110, 1.0), lB=(30, 100, 1.0), aF=(40, 20, 1.0), aB=(30, 20, 1.0), mouth=0.2),
                  dict(lean=30, lF=(34, 70, 1.0), lB=(-8, 50, 1.0), aF=(36, 60, 1.0), aB=(8, 70, 1.0))]
    A["grab"] = [dict(G, lean=28, hx=4, aF=(62, 14, 1.0), aB=(54, 16, 1.0), lF=(34, 60, 1.0), lB=(-24, 52, 1.0), mouth=0.6),
                 dict(G, lean=18, aF=(110, 12, 1.0), aB=(104, 12, 1.0), lF=(20, 40, 1.0), lB=(-18, 36, 1.0))]
    A["win"] = [dict(G, lean=0, aF=(160, 30, 1.0), aB=(150, 40, 1.0), mouth=1.0, hy=-1), dict(G, lean=2, aF=(170, 20, 1.0), aB=(160, 30, 1.0), mouth=1.0, hy=-2)]
    return A


def toad_prop_anims():
    # Swing frames with a held object: both arms straight along the swing angle, body counter-leans.
    out = {}
    for name, dist, n, start, step in (("swingpig", 30, 10, 170, 40), ("swingleg", 36, 8, -150, 38)):
        fr = []
        for i in range(n):
            ang = start + step * i if name == "swingpig" else start + step * i
            lean = -0.22 * math.sin(math.radians(ang)) * 40
            fr.append(dict(lean=lean, aF=(ang, 0, 1.0), aB=(ang, 0, 1.0), lF=(16, 24, 1.0), lB=(-16, 26, 1.0), mouth=0.9, hx=0,
                           prop=(ang, dist), propkind=name))
        out[name] = fr
    out["holdpig"] = [dict(lean=-6, aF=(168, 0, 1.0), aB=(168, 0, 1.0), lF=(16, 30, 1.0), lB=(-16, 30, 1.0), mouth=0.6,
                           prop=(168, 30), propkind="swingpig")]
    out["holdleg"] = [dict(lean=-4, aF=(-140, 0, 1.0), aB=(-140, 0, 1.0), lF=(16, 30, 1.0), lB=(-16, 30, 1.0), mouth=0.3,
                           prop=(-140, 36), propkind="swingleg")]
    out["throw"] = [dict(lean=16, aF=(96, 0, 1.0), aB=(96, 0, 1.0), lF=(34, 50, 1.0), lB=(-26, 20, 1.0), mouth=1.0, hx=4)]
    return out


def enemy_anims(kind):
    """Pose lists for the humanoid enemies. kind: pig, rat, walker, boss."""
    A = {}
    G = dict(lF=(10, 14, 1.0), lB=(-10, 16, 1.0), aF=(20, 100, 1.0), aB=(-8, 96, 1.0))
    if kind == "pig":
        A["idle"] = [dict(G, lean=6 + 1.5 * math.sin(i * math.pi / 3), hy=0.6 * math.sin(i * math.pi / 3)) for i in range(6)]
        A["walk"] = walk_frames(8, amp=30, arm=22, lean=8, base=dict(mouth=0.1))
        A["windup"] = [dict(G, lean=-6, aF=(-70, 80, 1.1), hx=-3, mouth=0.4), dict(G, lean=-9, aF=(-95, 70, 1.2), hx=-4, mouth=0.6, hy=-1)]
        A["punch"] = [dict(G, lean=18, aF=(88, 4, 1.4), hx=5, hipx=3, lF=(30, 40, 1.0), lB=(-24, 12, 1.0), mouth=0.7),
                      dict(G, lean=12, aF=(60, 40, 1.1), mouth=0.3)]
        A["kickwind"] = [dict(G, lean=-4, lF=(-10, 80, 1.0), aF=(-20, 80, 1.0), aB=(40, 80, 1.0))]
        A["kick"] = [dict(G, lean=-12, lF=(90, 4, 1.7), lB=(-4, 30, 1.0), aF=(-50, 60, 1.0), aB=(60, 40, 1.0), mouth=0.8)]
        hurt = dict(lean=-20, hx=-6, htilt=-12, mouth=1.0, hurt=1, aF=(-50, 40, 1.0), aB=(40, 60, 1.0), lF=(26, 40, 1.0), lB=(-22, 20, 1.0))
        A["hurt"] = [dict(hurt, flash=0.75), hurt]
        A["dazed"] = [dict(G, lean=14 + 4 * (i % 2), hx=3, htilt=10 - 20 * (i % 2), hurt=1, mouth=0.3, aF=(10, 50, 1.0), aB=(0, 50, 1.0),
                           lF=(14, 30, 1.0), lB=(-14, 30, 1.0)) for i in range(4)]
        A["fall"] = [dict(hurt, rot=r, aF=(-70, 30, 1.0), aB=(70, 50, 1.0), lF=(50, 60, 1.0), lB=(10, 80, 1.0)) for r in (30, 90, 160, 220)]
        A["lie"] = [dict(hurt, rot=92, anchor=True)]
        A["getup"] = [dict(lean=50, lF=(60, 110, 1.0), lB=(30, 100, 1.0), aF=(40, 20, 1.0), aB=(30, 20, 1.0)), dict(lean=28, lF=(34, 70, 1.0), lB=(-8, 50, 1.0))]
        A["held"] = [dict(hurt, hip=(0, -30), lean=0, aF=(160, 30, 1.0), aB=(150, 30, 1.0), lF=(30, 50, 1.0), lB=(-30, 50, 1.0), mouth=1.0)]
    elif kind == "rat":
        A["idle"] = [dict(G, lean=18 + (i % 2) * 3, hy=0.5 * (i % 2)) for i in range(4)]
        A["walk"] = walk_frames(6, amp=34, arm=26, lean=22, base=dict(mouth=0.2))
        A["crouch"] = [dict(G, lean=40, hx=4, lF=(50, 100, 1.0), lB=(20, 100, 1.0), aF=(60, 40, 1.0), aB=(50, 40, 1.0), mouth=0.6)]
        A["leap"] = [dict(G, lean=34, hx=5, lF=(70, 20, 1.2), lB=(-30, 90, 1.0), aF=(98, 6, 1.5), aB=(70, 20, 1.0), mouth=1.0)]
        hurt = dict(lean=-20, hx=-5, htilt=-12, mouth=1.0, hurt=1, aF=(-50, 40, 1.0), aB=(40, 60, 1.0), lF=(26, 40, 1.0), lB=(-22, 20, 1.0))
        A["hurt"] = [dict(hurt, flash=0.75), hurt]
        A["fall"] = [dict(hurt, rot=r) for r in (40, 110, 190, 260)]
        A["lie"] = [dict(hurt, rot=92, anchor=True)]
        A["getup"] = [dict(lean=50, lF=(60, 110, 1.0), lB=(30, 100, 1.0))]
        A["dazed"] = [dict(G, lean=24 + 4 * (i % 2), hurt=1, htilt=10 - 20 * (i % 2)) for i in range(2)]
    elif kind == "walker":
        A["idle"] = [dict(G, lean=4, hy=0.8 * (i % 2), lF=(8, 20, 1.0), lB=(-8, 24, 1.0), aF=(10, 60, 1.0), aB=(-6, 60, 1.0)) for i in range(4)]
        A["walk"] = walk_frames(8, amp=26, arm=14, lean=4, base=dict(aF=(10, 40, 1.0), aB=(-5, 40, 1.0)))
        A["windup"] = [dict(G, lean=-10, lF=(-12, 70, 1.0), aF=(-30, 60, 1.0), aB=(20, 60, 1.0), hx=-3),
                       dict(G, lean=-14, lF=(-24, 100, 1.0), aF=(-40, 60, 1.0), aB=(30, 60, 1.0), hx=-4, hurt=0)]
        A["stomp"] = [dict(G, lean=-6, lF=(92, 2, 1.8), lB=(-6, 26, 1.0), aF=(-40, 50, 1.0), aB=(50, 40, 1.0)),
                      dict(G, lean=4, lF=(30, 30, 1.2), lB=(-10, 24, 1.0))]
        hurt = dict(lean=-12, hx=-5, hurt=1, aF=(-30, 40, 1.0), aB=(30, 40, 1.0), lF=(20, 40, 1.0), lB=(-16, 24, 1.0))
        A["hurt"] = [dict(hurt, flash=0.75), hurt]
        A["fall"] = [dict(hurt, rot=r) for r in (25, 60, 100, 140)]
        A["lie"] = [dict(hurt, rot=92, anchor=True)]
        A["getup"] = [dict(lean=40, lF=(50, 100, 1.0), lB=(30, 90, 1.0)), dict(lean=20, lF=(30, 60, 1.0), lB=(-8, 40, 1.0))]
        A["dazed"] = [dict(G, lean=8, hurt=1, htilt=8 - 16 * (i % 2)) for i in range(2)]
    else:
        A["idle"] = [dict(G, lean=8 + 2 * math.sin(i * math.pi / 3), hy=0.7 * math.sin(i * math.pi / 3), aF=(24, 70, 1.0), aB=(-8, 70, 1.0)) for i in range(6)]
        A["walk"] = walk_frames(8, amp=28, arm=20, lean=12, base=dict(mouth=0.2))
        A["windup"] = [dict(G, lean=-8, aF=(-80, 70, 1.3), aB=(-30, 80, 1.0), hx=-3, mouth=0.5),
                       dict(G, lean=-12, aF=(-110, 60, 1.6), aB=(-30, 80, 1.0), hx=-4, mouth=0.8)]
        A["punch"] = [dict(G, lean=22, aF=(90, 4, 2.2), aB=(60, 30, 1.2), hx=6, hipx=3, lF=(30, 40, 1.0), lB=(-24, 12, 1.0), mouth=1.0),
                      dict(G, lean=16, aF=(70, 30, 1.6), mouth=0.5)]
        A["slamup"] = [dict(lean=-4, aF=(170, 10, 1.6), aB=(165, 10, 1.6), lF=(30, 90, 1.0), lB=(10, 80, 1.0), mouth=1.0)]
        A["slam"] = [dict(lean=26, aF=(50, 10, 2.4), aB=(40, 10, 2.4), lF=(30, 60, 1.0), lB=(-20, 60, 1.0), mouth=1.0)]
        A["charge"] = walk_frames(4, amp=40, arm=30, lean=34, base=dict(mouth=1.0, aF=(70, 20, 1.5), aB=(60, 30, 1.5)))
        hurt = dict(lean=-18, hx=-5, htilt=-10, mouth=1.0, hurt=1, aF=(-40, 40, 1.0), aB=(30, 60, 1.0), lF=(24, 40, 1.0), lB=(-20, 20, 1.0))
        A["hurt"] = [dict(hurt, flash=0.7), hurt]
        A["fall"] = [dict(hurt, rot=r) for r in (25, 60, 100, 140)]
        A["lie"] = [dict(hurt, rot=92, anchor=True)]
        A["getup"] = [dict(lean=44, lF=(50, 100, 1.0), lB=(30, 90, 1.0)), dict(lean=20, lF=(30, 60, 1.0), lB=(-8, 40, 1.0))]
        A["dazed"] = [dict(G, lean=12, hurt=1, htilt=8 - 16 * (i % 2)) for i in range(2)]
    return A


def preview(group):
    from g_battletoads_build import render_char
    frames = []
    spec = {"toad": (toad_anims, TOAD_A, 1.0, TOAD_SIZE), "toadp": (toad_prop_anims, TOAD_A, 1.0, TOAD_SIZE)}
    for kind, sty, k, size in (("pig", PIG_A, 0.95, PIG_SIZE), ("rat", RAT_A, 1.0, RAT_SIZE), ("walker", WALKER, 1.25, WALKER_SIZE), ("boss", BOSS, 1.75, BOSS_SIZE)):
        spec[kind] = ((lambda kd=kind: enemy_anims(kd)), sty, k, size)
    fn, sty, k, size = spec[group.split(":")[0]]
    A = fn()
    for name in group.split(":")[1:] or A:
        for pz in A[name][:12]:
            pz = dict(pz)
            r = pz.pop("rot", 0)
            an = pz.pop("anchor", False)
            fl = pz.pop("flash", 0)
            pz.pop("propkind", None)
            frames.append(render_char(pz, sty, k, size, rot=r, anchor=an, flash=fl))
    return frames
