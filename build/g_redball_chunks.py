# Hand-designed level chunks in the Red Ball idiom (build-time only; the result is stored in g_redball.bin).
#
# A chunk is a 18-row tile grid plus a list of parametrised objects. Every chunk begins and ends with at least two flat
# ground columns at row GT, so any order of chunks makes a continuous level.
#
# Grid legend: # solid  I ice  > < conveyor  / \ ramps  ^ v spikes  W liquid  * star  c C crates  B boulder
#   a-d buttons  1-4 gates  p-s levers  T spring pad  m M n minions  S start  E exit
# Objects: [saw cx cy cx2 cy2 speed] [plat cx top cx2 top2 speed] [crush x y0 drop period phase]
#   [cannon x y dir period phase] [laser x y dir period on phase] [fall x top w] [seesaw cx top] [gear cx cy r speed]
GT = 13
H = 18


class Ch:
    def __init__(self, name, w, ground="#", star=True):
        self.name, self.w, self.ground, self.star = name, w, ground, star
        self.g = [["."] * w for _ in range(H)]
        for x in range(w):
            for y in range(GT, H):
                self.g[y][x] = ground
        self.ex = []

    def put(self, x, y, c):
        self.g[y][x] = c

    def fill(self, x0, x1, y0, y1, c):
        for x in range(x0, x1):
            for y in range(y0, y1):
                self.g[y][x] = c

    def hole(self, x0, x1, liquid=True):
        self.fill(x0, x1, GT, H, ".")
        if liquid:
            self.fill(x0, x1, H - 2, H, "W")

    def bump(self, x0, x1, n, c=None):
        self.fill(x0, x1, GT - n, GT, c or self.ground)

    def top(self, x0, x1, y, c=None):
        self.fill(x0, x1, y, y + 1, c or self.ground)

    def star_at(self, x, y):
        if self.star:
            self.g[y][x] = "*"

    def obj(self, *a):
        self.ex.append(list(a))

    def out(self):
        for x in (0, 1, self.w - 2, self.w - 1):
            assert self.g[GT][x] in "#I", (self.name, x)
        return {"name": self.name, "w": self.w, "g": ["".join(r) for r in self.g], "ex": self.ex}


# ------------------------------------------------------------------------------------------------ start / exit
def start(g="#"):
    c = Ch("start", 12, g)
    c.put(3, 12, "S")
    return c


def exitc(g="#"):
    c = Ch("exit", 12, g)
    c.put(8, 11, "E")
    return c


# ------------------------------------------------------------------------------------------------ shared builders
def c_flat(star, g="#"):
    c = Ch("flat", 18, g, star)
    c.put(9, 12, "m")
    c.star_at(13, 10)
    return c


def c_hop(star, g="#"):
    c = Ch("hop", 20, g, star)
    c.hole(6, 9)
    c.hole(12, 15)
    c.star_at(13, 10)
    return c


def c_steps(star, g="#"):
    c = Ch("steps", 22, g, star)
    c.bump(5, 8, 1)
    c.bump(8, 11, 2)
    c.bump(11, 14, 1)
    c.put(15, 12, "m")
    c.star_at(4, 10)
    return c


def c_slopes(star, g="#"):
    c = Ch("slopes", 22, g, star)
    c.put(5, 12, "/")
    c.bump(6, 10, 1)
    c.put(10, 12, "\\")
    c.put(13, 12, "/")
    c.bump(14, 17, 1)
    c.put(17, 12, "\\")
    c.star_at(8, 9)
    return c


def c_spikes(star, g="#"):
    c = Ch("spikes", 20, g, star)
    for x in (8, 9, 10):
        c.put(x, 12, "^")
    c.put(14, 12, "m")
    c.star_at(9, 10)
    return c


def c_plat(star, g="#"):
    c = Ch("plat", 24, g, star)
    c.hole(6, 16)
    c.obj("plat", 8.0, GT, 14.0, GT, 1.5)
    c.star_at(11, 10)
    return c


def c_crate(star, g="#", crate="c", gid=1):
    c = Ch("crate", 26, g, star)
    c.put(9, 13, "abcd"[gid - 1])
    c.put(10, 13, "abcd"[gid - 1])
    c.put(4, 12, crate)
    for y in range(9, 13):
        c.put(16, y, str(gid))
    c.star_at(20, 10)
    return c


def c_saw(star, g="#"):
    c = Ch("saw", 22, g, star)
    c.obj("saw", 7.5, 12.37, 14.5, 12.37, 1.5)
    c.star_at(11, 10)
    return c


def c_springs(star, g="#"):
    c = Ch("springs", 22, g, star)
    c.top(9, 16, 8)
    c.put(5, 12, "T")
    c.star_at(12, 6)
    return c


def c_wallspring(star, g="#"):
    c = Ch("wallspring", 24, g, star)
    c.put(8, 12, "T")
    c.fill(13, 15, 9, GT, g)
    c.star_at(12, 6)
    return c


def c_fall(star, g="#"):
    c = Ch("fall", 24, g, star)
    c.hole(6, 17)
    for x in (6.0, 8.75, 11.5, 14.25):
        c.obj("fall", x, GT, 2)
    c.star_at(11, 10)
    return c


def c_soldier(star, g="#", kind="M"):
    c = Ch("soldier", 22, g, star)
    c.hole(8, 11)
    c.put(15, 12, kind)
    c.star_at(9, 10)
    return c


def c_seesaw(star, g="#"):
    c = Ch("seesaw", 22, g, star)
    c.hole(6, 12)
    c.obj("seesaw", 9.0, GT)
    c.star_at(9, 10)
    return c


def c_conv(star, g="#"):
    c = Ch("conv", 24, g, star)
    for x in range(5, 11):
        c.put(x, GT, ">")
    c.hole(11, 14)
    for x in range(14, 19):
        c.put(x, GT, "<")
    c.star_at(12, 10)
    return c


def c_crush(star, g="#"):
    c = Ch("crush", 22, g, star)
    c.fill(4, 18, 3, 5, "#")
    for i, x in enumerate((6, 10, 14)):
        c.obj("crush", x, 5, 400, 140, i * 47)
    c.star_at(12, 10)
    return c


def c_laser(star, g="#"):
    c = Ch("laser", 22, g, star)
    c.fill(5, 17, 3, 5, "#")
    for i, x in enumerate((7, 11, 15)):
        c.put(x, 5, "#")
        # phases step back by the time the ball needs to run one gap, so a run-through window opens every cycle
        c.obj("laser", x, 5, "D", 120, 50, (-22 * i) % 120)
    c.star_at(13, 10)
    return c


def c_cannon(star, g="#"):
    c = Ch("cannon", 24, g, star)
    c.put(15, 12, "#")
    c.obj("cannon", 15, 12, "L", 100, 0)
    c.fill(20, 21, 0, 10, "#")
    c.put(20, 10, "#")
    c.obj("cannon", 20, 10, "L", 130, 40)
    c.star_at(11, 10)
    return c


def c_vsaw(star, g="#"):
    c = Ch("vsaw", 22, g, star)
    c.obj("saw", 8.5, 12.4, 8.5, 9.0, 1.4)
    c.obj("saw", 13.5, 9.0, 13.5, 12.4, 1.4)
    c.star_at(11, 10)
    return c


def c_lift(star, g="#"):
    c = Ch("lift", 24, g, star)
    c.fill(6, 10, GT, 15, ".")
    c.bump(10, 16, 4)
    c.obj("plat", 8.0, 14.0, 8.0, 9.0, 1.3)
    c.star_at(12, 7)
    return c


def c_pressm(star, g="#"):
    c = Ch("pressm", 22, g, star)
    c.fill(8, 14, 3, 5, "#")
    c.obj("crush", 10, 5, 400, 140, 0)
    c.put(16, 12, "M")
    c.star_at(11, 10)
    return c


def c_hops(star, g="#"):
    c = Ch("hops", 24, g, star)
    c.hole(5, 19)
    for x in (7, 11, 15):
        c.fill(x, x + 2, GT, H, g)
    c.star_at(13, 10)
    return c


def c_spring(star, g="#"):
    c = Ch("spring", 26, g, star)
    c.hole(8, 13)
    c.put(7, 12, "T")
    c.star_at(10, 6)
    return c


def c_minions(star, g="#"):
    c = Ch("minions", 24, g, star)
    c.hole(7, 10)
    c.put(14, 12, "n")
    c.hole(17, 19)
    c.star_at(8, 10)
    return c


def c_slide(star, g="I"):
    c = Ch("slide", 24, g, star)
    for x in (16, 17):
        c.put(x, 12, "^")
    c.star_at(9, 10)
    return c


def c_islands(star, g="I"):
    c = Ch("islands", 28, g, star)
    c.hole(5, 21)
    for x in (7, 12, 17):
        c.fill(x, x + 3, GT, H, g)
    c.star_at(12, 10)
    return c


def c_boulder(star, g="I"):
    c = Ch("boulder", 26, g, star)
    c.put(4, 12, "B")
    c.put(11, 12, "a")
    for y in range(9, 13):
        c.put(17, y, "1")
    c.star_at(20, 10)
    return c


# ------------------------------------------------------------------------------------------------ boss arenas
def arena(kind):
    c = Ch("boss", 32, "#", False)
    for y in range(0, GT):
        for x in (0, 1, 30, 31):
            c.put(x, y, "#")
    c.put(3, 12, "S")
    c.obj("boss", kind)
    if kind == "boulder":
        for x, n in ((3, 1), (4, 2), (5, 3), (26, 3), (27, 2), (28, 1)):
            c.fill(x, x + 1, GT - n, GT, "#")
        c.top(6, 14, 9)
        c.top(17, 26, 9)
        c.put(12, 8, "a")
        c.put(18, 8, "b")
    return c


LEVEL_POOLS = {
    # key: (ground, builder list); builders take (star, ground)
    "w1l1": ("#", ["flat", "hop", "steps", "slopes", "spikes", "soldier", "plat"]),
    "w1l2": ("#", ["crate", "saw", "wallspring", "fall", "plat", "seesaw", "springs", "soldier", "spikes"]),
    "w2l1": ("#", ["conv", "crush", "laser", "vsaw", "fall", "lift", "pressm"]),
    "w2l2": ("#", ["gate", "cannon", "crush", "laser", "vsaw", "lift", "conv", "fall"]),
    "w3l1": ("#", ["hops", "vsaw", "spring", "fall", "minions", "gate"]),
    "w3l2": ("I", ["slide", "islands", "cannon", "boulder", "crush", "spring", "vsaw"]),
}

BUILDERS = {
    "flat": c_flat, "hop": c_hop, "steps": c_steps, "slopes": c_slopes, "spikes": c_spikes, "plat": c_plat,
    "crate": c_crate, "saw": c_saw, "springs": c_springs, "wallspring": c_wallspring, "fall": c_fall,
    "soldier": c_soldier, "seesaw": c_seesaw, "conv": c_conv, "crush": c_crush, "laser": c_laser, "cannon": c_cannon,
    "vsaw": c_vsaw, "lift": c_lift, "pressm": c_pressm, "hops": c_hops, "spring": c_spring, "minions": c_minions,
    "slide": c_slide, "islands": c_islands, "boulder": c_boulder,
    "gate": lambda s, g="#": c_crate(s, g, "C", 2),
}


def all_chunks():
    out = {}
    for key, (g, names) in LEVEL_POOLS.items():
        out[key] = {"start": start(g).out(), "exit": exitc(g).out(), "pool": {}}
        for n in names:
            out[key]["pool"][n] = {"1": BUILDERS[n](True, g).out(), "0": BUILDERS[n](False, g).out()}
    out["boss"] = {k: arena(k).out() for k in ("monocle", "mecha", "boulder")}
    return out
