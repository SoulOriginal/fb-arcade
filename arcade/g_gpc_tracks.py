# Track data for the eight circuits of the DOS game, in the original championship order.
# Each circuit is a list of pieces designed from the real layout (see research_gpc.md); lengths are scaled down
# so a lap takes about 18-22 seconds of play. ("S", metres) straight, ("R"|"L", radius m, angle deg) arc.
# An optional last element holds flags: t = tunnel, b = bridge crossing, u = uphill, d = downhill.
import math

NAMES = ["BRAZIL", "MONACO", "CANADA", "DETROIT", "BRITAIN", "GERMANY", "ITALY", "JAPAN"]
CIRCUITS = {
    "BRAZIL": dict(
        place="RIO DE JANEIRO", real_laps=61, mi=3.126, style="hills", street=False, net=360,
        pieces=[("S", 230), ("R", 70, 100), ("S", 50), ("L", 90, 55), ("S", 90, 0, "u"), ("R", 120, 70),
                ("S", 130, 0, "u"), ("L", 80, 70), ("R", 70, 60, "d"), ("S", 150, 0, "d"), ("R", 60, 140),
                ("S", 70), ("L", 140, 35), ("S", 150), ("R", 100, 150), ("S", 60)]),
    "MONACO": dict(
        place="MONTE CARLO", real_laps=78, mi=2.068, style="harbour", street=True, net=360,
        pieces=[("S", 150), ("R", 30, 75), ("S", 100, 0, "u"), ("L", 50, 40, "u"), ("R", 60, 35), ("S", 40, 0, "d"),
                ("R", 40, 55, "d"), ("R", 14, 120), ("S", 40), ("R", 40, 50), ("S", 120, 0, "t"),
                ("L", 45, 40, "t"), ("R", 45, 65, "t"), ("L", 45, 40, "t"), ("S", 50), ("R", 50, 60),
                ("S", 40), ("L", 35, 60), ("R", 35, 50), ("L", 25, 60), ("R", 18, 90)]),
    "CANADA": dict(
        place="MONTREAL", real_laps=69, mi=2.740, style="trees", street=False, net=360,
        pieces=[("S", 260), ("R", 55, 100), ("S", 60), ("L", 70, 60), ("S", 50), ("R", 90, 60), ("L", 100, 40),
                ("S", 150), ("R", 80, 80), ("S", 60), ("R", 70, 60), ("S", 220), ("R", 28, 150),
                ("S", 200), ("L", 70, 30), ("R", 70, 40), ("S", 90)]),
    "DETROIT": dict(
        place="DETROIT", real_laps=65, mi=2.500, style="city", street=True, net=360,
        pieces=[("S", 220), ("R", 22, 90), ("S", 80), ("L", 25, 90), ("S", 70), ("R", 30, 90), ("S", 80, 0, "t"),
                ("R", 18, 180, "t"), ("S", 100), ("L", 30, 90), ("S", 60), ("R", 30, 90), ("S", 50),
                ("L", 30, 90), ("S", 50), ("R", 28, 45), ("S", 150), ("R", 40, 45), ("S", 60), ("R", 40, 90),
                ("S", 30)]),
    "BRITAIN": dict(
        place="SILVERSTONE", real_laps=65, mi=2.969, style="hills", street=False, net=360,
        pieces=[("S", 220), ("R", 140, 70), ("S", 70), ("R", 400, 20), ("L", 300, 30), ("R", 200, 40),
                ("S", 60), ("R", 120, 130), ("S", 90), ("L", 160, 50), ("S", 90), ("R", 220, 60),
                ("S", 120), ("R", 70, 120), ("S", 80), ("L", 90, 40), ("R", 90, 40), ("S", 90)]),
    "GERMANY": dict(
        place="HOCKENHEIM", real_laps=44, mi=4.223, style="trees", street=False, net=360,
        pieces=[("S", 360), ("R", 50, 90), ("S", 260), ("L", 50, 40), ("R", 50, 40), ("S", 220), ("R", 150, 120),
                ("S", 160), ("L", 40, 30), ("R", 40, 30), ("S", 160), ("R", 80, 100), ("S", 70),
                ("L", 60, 50), ("R", 60, 90), ("S", 60)]),
    "ITALY": dict(
        place="MONZA", real_laps=50, mi=3.604, style="trees", street=False, net=360,
        pieces=[("S", 300), ("L", 40, 35), ("R", 40, 35), ("R", 280, 50), ("S", 60), ("L", 45, 35), ("R", 45, 40),
                ("S", 100), ("R", 110, 55), ("R", 120, 45), ("S", 200), ("L", 50, 40), ("R", 50, 40),
                ("S", 420), ("R", 260, 200), ("S", 110)]),
    "JAPAN": dict(
        place="SUZUKA", real_laps=51, mi=3.499, style="mountain", street=False, net=0,
        pieces=[("S", 240), ("R", 90, 90), ("R", 70, 40), ("L", 60, 70), ("R", 60, 70), ("L", 80, 90),
                ("S", 70, 0, "u"), ("R", 100, 100), ("R", 30, 150), ("L", 200, 90), ("S", 100),
                ("L", 80, 90, "d"), ("S", 30, 0, "b"), ("S", 80, 0, "b"), ("R", 60, 100),
                ("S", 110), ("L", 70, 100), ("L", 120, 110), ("S", 130, 0, "b")]),
}
STEP = 4.0        # metres per track cell before scaling
TARGET = {"BRAZIL": 900, "MONACO": 520, "CANADA": 880, "DETROIT": 600, "BRITAIN": 1050, "GERMANY": 1000,
          "ITALY": 1150, "JAPAN": 950}


def build(name):
    # Returns per-cell curvature (rad/m, + = right), gradient, tunnel/bridge flags and the lap length in cells.
    c = CIRCUITS[name]
    arcs = []
    for p in c["pieces"]:
        flags = p[3] if len(p) > 3 else ""
        if p[0] == "S":
            arcs.append(("S", p[1], 0.0, flags))
        else:
            sgn = 1 if p[0] == "R" else -1
            arcs.append(("A", p[1] * math.radians(p[2]), sgn / p[1], flags))
    turn = sum(a[1] * a[2] for a in arcs)
    target = math.radians(c["net"])
    # scale curvature so the lap really closes its heading; a length stays what the designer chose
    k = target / turn if c["net"] else 1.0
    curv, grad, tun, bri = [], [], [], []
    for kind, ln, cc, fl in arcs:
        n = max(1, round(ln / STEP))
        for _ in range(n):
            curv.append(cc * k)
            grad.append(0.9 if "u" in fl else (-0.9 if "d" in fl else 0.0))
            tun.append("t" in fl)
            bri.append("b" in fl)
    # smooth gradients so the horizon eases instead of jumping
    sm = []
    n = len(grad)
    for i in range(n):
        sm.append(sum(grad[(i + j) % n] for j in range(-6, 7)) / 13.0)
    # uniform squeeze to the target lap length: the shape and the heading change stay, radii shrink with it
    sc = TARGET[name] / (n * STEP)
    step = STEP * sc
    curv = [x / sc for x in curv]
    return dict(name=name, curv=curv, grad=sm, tun=tun, bri=bri, n=n, step=step, length=n * step, info=c)


if __name__ == "__main__":
    for nm in NAMES:
        t = build(nm)
        print(nm, t["n"], t["length"], round(t["step"], 2))
