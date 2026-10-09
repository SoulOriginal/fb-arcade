# Contra: two bots (Bill and Lance) play co-op through the jungle, the waterfall and the alien lair.
# Native 256x240 play field drawn 4x (1024x960) in the screen centre; scoring follows the NES table (research_contra.md).
from fbcore import *
import math

B = load_bundle("g_contra.bin")
SP = B["spr"]
STAGES = B["stages"]

X0, Y0 = 448, 60
MARG = 40
ROWB = (256 + 2 * MARG) * 8
VIS0 = MARG * 8
VISW = 2048
FR = [bytearray(ROWB) for _ in range(240)]
MV = [memoryview(r)[VIS0:VIS0 + VISW] for r in FR]

SPD, WSPD, GRAV, V0, VMAX = 2.6, 2.0, 0.55, 7.4, 8.0
DIRS = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]
# weapon: cooldown ticks, bullet speed, damage, max bullets on screen per player
WEAPONS = {"N": (7, 7.0, 1, 4), "M": (4, 8.0, 1, 6), "S": (7, 7.0, 1, 10), "L": (13, 10.0, 3, 2), "F": (8, 4.5, 2, 4)}
# half width, height above the anchor, depth below it
HB = {
    "soldier": (6, 30, 0), "sniper": (6, 30, 0), "turret": (11, 23, 0), "bturret": (11, 23, 0), "cannon": (11, 15, 0),
    "sensor": (11, 23, 0), "capsule": (10, 7, 7), "item": (9, 10, 0), "scuba": (6, 18, 0), "boulder": (8, 8, 8),
    "flame": (5, 16, 0), "mouth": (12, 10, 10), "fmouth": (12, 10, 10), "bighead": (26, 20, 20), "spore": (7, 7, 7),
    "floater": (8, 5, 5), "crawler": (9, 10, 0), "cocoon": (11, 11, 11), "heart": (22, 26, 20), "core": (12, 16, 16),
    "orb": (6, 6, 6), "head": (18, 24, 24), "wsniper": (6, 30, 0),
}
POINTS = {"soldier": 100, "rsoldier": 500, "sniper": 500, "turret": 300, "bturret": 1000, "cannon": 300, "sensor": 500,
          "capsule": 500, "scuba": 1000, "boulder": 500, "mouth": 1000, "fmouth": 1000, "bighead": 5000, "spore": 100,
          "floater": 300, "crawler": 300, "cocoon": 3000, "heart": 500000, "core": 10000, "orb": 2000, "head": 10000,
          "wsniper": 500, "item": 1000}
BOSS_PARTS = {"bturret", "core", "orb", "head", "cocoon", "heart", "wsniper"}
HURT = {"soldier", "boulder", "flame", "spore", "floater", "crawler", "orb"}
BLOCK = {"sensor", "core", "orb_seg"}
STATIONARY = {"turret", "bturret", "cannon", "sensor", "core", "heart", "cocoon", "mouth", "fmouth", "bighead", "head",
              "orb", "wsniper", "sniper", "scuba"}
PRIO = {"capsule": 90, "sensor": 70, "sniper": 80, "wsniper": 85, "soldier": 75, "turret": 60, "bturret": 66, "cannon": 55,
        "scuba": 20, "boulder": 78, "spore": 82, "floater": 72, "crawler": 76, "mouth": 50, "fmouth": 50, "bighead": 52,
        "cocoon": 64, "heart": 62, "core": 62, "orb": 66, "head": 60}
CONTINUES = 3
START_LIVES = 5
# the bots sometimes struggle on a boss for minutes; the run is ended as a lost game well inside the 9 minute cap
SOFT_END_TICKS = 410 * TICK_RATE
INTRO_TICKS = 70


class E:
    def __init__(self, kind, x, y, **kw):
        self.kind, self.x, self.y = kind, x, y
        self.vx = self.vy = 0.0
        self.hp, self.t, self.vul, self.alive = 1, 0, True, True
        self.dx = 0.0
        self.owner = None
        self.__dict__.update(kw)


class Bullet:
    def __init__(self, x, y, vx, vy, owner=None, dmg=1, kind="eb", **kw):
        self.x, self.y, self.vx, self.vy, self.owner, self.dmg, self.kind = x, y, vx, vy, owner, dmg, kind
        self.t = 0
        self.g = 0.0
        self.alive = True
        self.__dict__.update(kw)


def put(spr, x, y):
    rows, w, h, ox, oy = spr
    x = int(x) - ox
    y = int(y) - oy
    if x < -MARG or x + w > 256 + MARG or y >= 240 or y + h <= 0:
        return
    bx = (x + MARG) * 8
    for j in range(max(0, -y), min(h, 240 - y)):
        r = FR[y + j]
        for o, b in rows[j]:
            r[bx + o:bx + o + len(b)] = b


def flush():
    for y in range(240):
        mv = MV[y]
        o = (Y0 + 4 * y) * S + X0 * 2
        fb[o:o + VISW] = mv
        fb[o + S:o + S + VISW] = mv
        fb[o + 2 * S:o + 2 * S + VISW] = mv
        fb[o + 3 * S:o + 3 * S + VISW] = mv


class Player:
    def __init__(self, idx):
        self.idx = idx
        self.pal = ("bill", "lance")[idx]
        self.lives = START_LIVES
        self.score = 0
        self.reset_weapon()
        self.inp = (0, 0, 0, 0, 0, 0)
        self.dead = True
        self.dt = 999
        self.out = False
        self.skill = (0.93, 0.9)[idx]
        self.rush = (110, 130)[idx]

    def reset_weapon(self):
        self.wep, self.rapid, self.barrier = "N", False, 0

    def spawn(self, x, y):
        self.x, self.y, self.vx, self.vy = x, y, 0.0, 0.0
        self.dead, self.dt, self.out = False, 0, False
        self.stand = None
        self.ground, self.face, self.aim = False, 1, 0
        self.prone = self.wade = self.dive = False
        self.inv = 120
        self.cd = 0
        self.anim = 0
        self.air = True
        self.mem = {}


def box(e):
    hw, up, dn = HB[e.kind]
    return e.x - hw, e.y - up, e.x + hw, e.y + dn


class Game:
    pass


def make():
    G = Game()
    G.players = [Player(0), Player(1)]
    G.stage_i = 0
    G.continues = CONTINUES
    G.tick = 0
    G.rnd = random
    G.phase = "intro"
    G.ptick = 0
    G.end = None
    G.hud_cache = {}
    G.frame_water = 0
    clear(0)
    load_stage(G)

    def step():
        G.tick += 1
        if G.end is not None:
            return G.end.tick()
        if G.tick >= min(CAP_TICKS, SOFT_END_TICKS):
            finish(G, "GAME OVER")
            return False
        ph = G.phase
        G.ptick += 1
        if ph == "intro":
            if G.ptick == 1:
                intro_draw(G)
            if G.ptick > INTRO_TICKS:
                G.phase, G.ptick = "play", 0
                clear(0)
                G.hud_cache = {}
            return False
        if ph == "continue":
            if G.ptick == 1:
                fill_rect(X0, Y0, 1024, 960, 0)
                draw_text_centered("GAME OVER", 330, "L", COLOR_RED)
            if G.ptick == 60:
                draw_text_centered("CONTINUE %d" % G.continues, 520, "L", COLOR_YELLOW)
            if G.ptick > 130:
                G.continues -= 1
                for p in G.players:
                    p.lives = START_LIVES
                    p.reset_weapon()
                    p.dead = True
                    p.dt = 999
                    p.out = False
                load_stage(G)
                G.phase, G.ptick = "intro", 0
            return False
        play_tick(G)
        render(G)
        if G.phase == "clear":
            # the play field is rewritten every tick, so the banner has to be drawn again after each frame
            draw_text_centered("STAGE %d CLEAR" % (1, 3, 8)[G.stage_i], 380, "L", COLOR_YELLOW)
            if G.ptick > 170:
                if G.stage_i == 2:
                    finish(G, "MISSION COMPLETE")
                    return False
                G.stage_i += 1
                load_stage(G)
                G.phase, G.ptick = "intro", 0
        elif G.phase == "play" and all(p.lives <= 0 and p.dead for p in G.players):
            if G.continues > 0:
                G.phase, G.ptick = "continue", 0
            else:
                finish(G, "GAME OVER")
        return False
    return step


def total_score(G):
    return G.players[0].score + G.players[1].score


def finish(G, title):
    G.end = EndScreen()
    G.end.start(total_score(G), title)


def intro_draw(G):
    fill_rect(X0, Y0, 1024, 960, 0)
    n = (1, 3, 8)[G.stage_i]
    draw_text_centered("STAGE %d" % n, 380, "L", COLOR_WHITE)
    draw_text_centered(G.st["name"], 500, "L", COLOR_YELLOW)


# ---- stage setup ---------------------------------------------------------------------------------------------
def load_stage(G):
    st = STAGES[G.stage_i]
    G.st = st
    G.vert = st["kind"] == "v"
    G.cam_x = 0
    G.cam_y = st["h"] - 240 if G.vert else 0
    G.en = []
    G.eb = []
    G.pb = []
    G.fx = []
    G.plats = list(st["plats"])
    G.dyn = []
    G.events = sorted(st["events"], key=(lambda e: -e[2]) if G.vert else (lambda e: e[1]))
    G.ei = 0
    G.gen_t = 0
    G.boss = None
    G.boss_active = False
    G.boss_dead = False
    G.wall_x = None
    G.stall = 0
    G.stall_mark = None
    G.stalls = 0
    G.stage_t = 0
    G.clear_t = 0
    sx, sy = st["start"]
    for b in st.get("bridges", []):
        for x in range(b[0], b[1], 16):
            e = E("bsec", x + 8, b[2], hw=8, plat=True, trig=False)
            G.en.append(e)
            G.dyn.append(e)
    if G.vert:
        x0, x1, by = st["bridge"]
        G.en.append(E("flame", 120, by, bx0=x0 + 8, bx1=x1 - 8, vx=0.8, vul=False))
        for k, (fy, fx) in enumerate(st["floats"]):
            e = E("float", fx, fy, hw=20, plat=True, bx0=40, bx1=216, vx=0.8 if k % 2 else -0.8, dx=0.0)
            G.en.append(e)
            G.dyn.append(e)
    for p in G.players:
        if p.lives > 0:
            p.spawn(sx + 24 * p.idx, sy - 4 if not G.vert else sy)
            p.ground = True
            p.inv = 60
        else:
            p.dead, p.out = True, True


# ---- collision helpers --------------------------------------------------------------------------------------
def land(G, x, y0, y1):
    """Highest platform top between the previous and the new feet position that covers x, or None."""
    best = None
    for a, b, py in G.plats:
        if a - 3 <= x <= b + 3 and y0 - 1 <= py <= y1 and (best is None or py < best):
            best = py
    for e in G.dyn:
        if e.alive and abs(e.x - x) <= e.hw + 3 and y0 - 1 <= e.y <= y1 and (best is None or e.y < best):
            best = e.y
    return best


def nearest_player(G, x, y):
    best, bd = None, 1e9
    for p in G.players:
        if p.dead:
            continue
        d = abs(p.x - x) + abs(p.y - y) * 0.5
        if d < bd:
            best, bd = p, d
    return best


def phb(p):
    if p.prone:
        return p.x - 12, p.y - 8, p.x + 12, p.y
    if p.air:
        return p.x - 6, p.y - 25, p.x + 6, p.y - 7
    return p.x - 5, p.y - 28, p.x + 5, p.y


def overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def explode(G, x, y, big=False):
    G.fx.append([x, y, 0, big])


def hurt(G, p):
    if p.dead or p.inv > 0 or p.barrier > 0:
        return
    p.dead, p.dt = True, 0
    p.vy, p.vx = -6.0, -2.2 * p.face
    p.lives -= 1
    p.prone = p.dive = False


def kill(G, e, owner):
    e.alive = False
    k = e.kind
    pts = POINTS.get("rsoldier" if (k == "soldier" and e.__dict__.get("red")) else k, 0)
    if owner is not None:
        G.players[owner].score += pts
    _, up, dn = HB[k]
    explode(G, e.x, e.y - (up - dn) / 2, big=k in ("core", "head", "heart", "bighead", "cocoon", "bturret"))
    if k == "sensor" or k == "capsule":
        G.en.append(E("item", e.x, e.y - 12, letter=e.letter, vy=-5.0, vul=False))
    if k == "soldier" and e.__dict__.get("red"):
        G.en.append(E("item", e.x, e.y - 20, letter=e.letter, vy=-4.0, vul=False))


# ---- spawning ---------------------------------------------------------------------------------------------------
def spawn_event(G, ev):
    k = ev[0]
    if k == "sniper":
        x = ev[1]
        y = ev[2] if len(ev) > 2 and G.vert else land(G, x, -50, 400)
        G.en.append(E("sniper", x, y, hp=1, bush=not G.vert, st=0, aimd=0, shots=0))
    elif k == "turret":
        x = ev[1]
        y = ev[2] if G.vert else land(G, x, -50, 400)
        G.en.append(E("turret", x, y, hp=8, step=0, fire=40))
    elif k == "cannon":
        G.en.append(E("cannon", ev[1], land(G, ev[1], -50, 400), hp=8, st=0, fire=30, vul=False))
    elif k == "sensor":
        x = ev[1]
        y = ev[2] if G.vert else land(G, x, -50, 400)
        G.en.append(E("sensor", x, y, hp=1, letter=ev[3] if G.vert else ev[2], st=0, vul=False))
    elif k == "capsule":
        letter = ev[3] if G.vert else ev[2]
        if G.vert:
            G.en.append(E("capsule", 128, G.cam_y + 250, hp=1, letter=letter, base=128, vul=True))
        else:
            G.en.append(E("capsule", G.cam_x - 20, 80, hp=1, letter=letter, base=70, vul=True))
    elif k == "scuba":
        G.en.append(E("scuba", ev[1], G.st["water_y"], hp=1, st=0, vul=False))
    elif k == "cave":
        G.en.append(E("cave", ev[1], ev[2], vul=False))
    elif k == "mouth" or k == "fmouth":
        G.en.append(E(k, ev[1], ev[2], hp=6, st=0, fire=50))
    elif k == "bighead":
        G.en.append(E("bighead", ev[1], ev[2] + 20, hp=24, st=0, fire=40))
    elif k == "crawlers":
        for i in range(4):
            x = G.cam_x + 270 + i * 26
            y = land(G, x, -50, 400)
            if y is not None:
                G.en.append(E("crawler", x, y, hp=1, vx=-2.4))


def spawn_soldier(G):
    p = nearest_player(G, G.cam_x + 128, 120)
    if p is None:
        return
    left = random.random() < 0.2
    x = G.cam_x - 12 if left else G.cam_x + 268
    y = land(G, x, -50, 400)
    if y is None:
        return
    red = random.random() < 0.12
    G.en.append(E("soldier", x, y, hp=1, vx=2.1 if left else -2.1, face=1 if left else -1, red=red,
                  letter=random.choice("MSLF"), turns=0, shoot=random.random() < 0.4, fire=random.randint(40, 90),
                  jump_t=0, ground=True))


def start_boss(G):
    G.boss_active = True
    kind = G.st["boss"]["kind"]
    if kind == "wall":
        G.wall_x = 3686
        G.bparts = []
        for cx in (3716, 3750):
            e = E("bturret", cx, 116, hp=10, step=6, fire=60 + (cx % 7) * 5, bomb=True)
            G.en.append(e)
            G.bparts.append(e)
        G.core = E("core", 3804, 188, hp=24, st=0, vul=False)
        G.en.append(G.core)
        G.en.append(E("wsniper", 3740, 44, hp=1, st=0, aimd=0, shots=0, fire=30))
    elif kind == "alien":
        G.head = E("head", 128, 86, hp=28, st=0, fire=80, vul=False)
        G.arms = []
        for side, sx in ((0, 62), (1, 194)):
            tip = E("orb", sx, 140, hp=12, side=side, sx=sx, sy=108, fire=60 + side * 40, vul=True)
            segs = [E("orb_seg", sx, 108, vul=False) for _ in range(3)]
            G.arms.append((tip, segs))
            G.en.append(tip)
            G.en += segs
        G.en.append(G.head)
    else:
        G.cocoons = []
        for cx, cy, low in ((3190, 176, 1), (3290, 176, 1), (3195, 44, 0), (3285, 44, 0)):
            e = E("cocoon", cx, cy, hp=8, st=0, low=low, fire=70 + (cx % 5) * 9)
            G.en.append(e)
            G.cocoons.append(e)
        G.heart = E("heart", 3240, 120, hp=40, vul=False, t=0)
        G.en.append(G.heart)
        G.wall_x = None


# ---- main per-tick logic ------------------------------------------------------------------------------------
def play_tick(G):
    G.stage_t += 1
    G.clear_t += 1 if G.phase == "clear" else 0
    for p in G.players:
        if G.phase == "play":
            p.inp = bot(G, p)
        else:
            p.inp = (1, 0, 0, 0, 0, 0) if not G.vert else (0, 0, 0, 0, 0, 0)
        update_player(G, p)
    spawn_logic(G)
    for e in G.en:
        if e.alive:
            UPD[e.kind](G, e)
    update_bullets(G)
    if G.tick % 2 == 0:
        for f in G.fx:
            f[2] += 1
        G.fx = [f for f in G.fx if f[2] < 5]
    G.en = [e for e in G.en if e.alive]
    G.dyn = [e for e in G.dyn if e.alive]
    camera(G)
    boss_logic(G)
    stall_check(G)


def spawn_logic(G):
    st = G.st
    ev = G.events
    while G.ei < len(ev):
        e = ev[G.ei]
        if G.vert:
            if e[2] < G.cam_y - 30 and e[0] != "capsule":
                break
            if e[0] == "capsule" and e[2] < G.cam_y + 200:
                break
            if e[2] > G.cam_y + 260 and e[0] != "capsule":
                G.ei += 1
                continue
        elif e[1] > G.cam_x + 270:
            break
        G.ei += 1
        spawn_event(G, e)
    if G.phase != "play" or G.boss_active:
        return
    if (G.vert and G.cam_y <= 0) or (not G.vert and G.cam_x >= st["lock"]):
        start_boss(G)
        return
    if G.vert:
        G.gen_t += 1
        if G.gen_t > 220 and G.cam_y > 330:
            G.gen_t = 0
            side = random.random() < 0.5
            x = -10 if side else 266
            y = land(G, x + (14 if side else -14), G.cam_y + 20, G.cam_y + 200)
            if y is not None:
                G.en.append(E("soldier", x, y, hp=1, vx=2.0 if side else -2.0, face=1 if side else -1, red=False,
                              letter="M", turns=0, shoot=random.random() < 0.35, fire=50, jump_t=0, ground=True))
        return
    for x0, x1, itv in st["gens"]:
        if x0 <= G.cam_x <= x1:
            G.gen_t += 1
            if G.gen_t >= itv + random.randint(-10, 20):
                G.gen_t = 0
                if st["name"] == "ALIEN LAIR":
                    G.en.append(E("floater", G.cam_x + 268, random.randint(70, 160), hp=1, ph=random.random() * 6))
                else:
                    spawn_soldier(G)
            break


def camera(G):
    live = [p for p in G.players if not p.dead]
    if not live:
        return
    if G.vert:
        target = min(p.y for p in live) - 120
        target = max(target, max(p.y for p in live) - 222)
        if max(p.y for p in live) < 232:
            target = 0
        G.cam_y = int(max(target, G.cam_y - 4)) if target < G.cam_y else G.cam_y
    else:
        target = max(p.x for p in live) - 100
        G.cam_x = int(min(G.st["lock"], max(G.cam_x, min(target, G.cam_x + 4))))


def boss_logic(G):
    if not G.boss_active or G.boss_dead:
        return
    k = G.st["boss"]["kind"]
    if k == "wall":
        if all(not e.alive for e in G.bparts):
            G.core.vul = True
            G.core.st = 1
        if not G.core.alive:
            boss_down(G, 3804, 150)
    elif k == "alien":
        if all(not t.alive for t, _ in G.arms):
            G.head.vul = True
            G.head.st = 2
        if not G.head.alive:
            boss_down(G, 128, 86)
    else:
        if all(not c.alive for c in G.cocoons if c.low):
            G.heart.vul = True
        if not G.heart.alive:
            boss_down(G, 3240, 120)


def boss_down(G, x, y):
    G.boss_dead = True
    G.phase, G.ptick = "clear", 0
    G.eb.clear()
    for e in G.en:
        if e.kind in ("soldier", "crawler", "floater", "spore", "turret", "bturret", "sniper", "wsniper", "cocoon",
                      "orb", "orb_seg", "head", "mouth", "fmouth", "bighead"):
            if e.alive and e.kind not in ("head",):
                e.alive = False
                explode(G, e.x, e.y - 10, True)
    for i in range(10):
        G.fx.append([x + random.randint(-30, 30), y + random.randint(-30, 30), -i * 2, True])


def stall_check(G):
    """No progress for 15 s (camera still, boss and ledge height unchanged): shove the players on, finally break the boss."""
    live = [p for p in G.players if not p.dead]
    top = min((int(p.y) // 20 for p in live), default=0) if G.vert else 0
    mark = (G.cam_x, G.cam_y, top, sum(e.hp for e in G.en if e.kind in BOSS_PARTS), G.phase)
    if mark != G.stall_mark:
        G.stall, G.stall_mark = 0, mark
        return
    G.stall += 1
    if G.stall > 450 and G.phase == "play":
        G.stall = 0
        G.stalls += 1
        G.eb.clear()
        if G.stalls >= 2:
            for e in G.en:
                if e.kind in BOSS_PARTS or e.kind in HALT:
                    e.hp = 1
                    e.vul = True
        for p in live:
            if G.vert:
                above = [q for q in G.plats if q[2] < p.y - 10]
                if above:
                    q = max(above, key=lambda t: t[2])
                    p.x, p.y, p.vy = (q[0] + q[1]) / 2, q[2], 0.0
            else:
                p.x += 40
            p.inv = 60


# ---- player ------------------------------------------------------------------------------------------------------
def update_player(G, p):
    if p.out:
        return
    st = G.st
    if p.dead:
        p.dt += 1
        if p.dt < 70:
            p.vy = min(VMAX, p.vy + GRAV)
            p.x += p.vx * 0.6
            p.y += p.vy
            ly = land(G, p.x, p.y - p.vy - 1, p.y)
            if ly is not None and p.vy > 0:
                p.y, p.vy, p.vx = ly, 0.0, 0.0
        elif p.lives > 0:
            respawn(G, p)
        else:
            p.out = True
        return
    mx, aim_in, down, jump, fire, face_in = p.inp
    p.anim += 1
    if p.inv > 0:
        p.inv -= 1
    if p.barrier > 0:
        p.barrier -= 1
    if p.cd > 0:
        p.cd -= 1
    wy = st["water_y"]
    p.wade = bool(p.ground and wy is not None and p.y >= wy)
    p.dive = p.wade and down and mx == 0
    p.prone = bool(p.ground and not p.wade and down and mx == 0)
    if face_in:
        p.face = face_in
    elif mx:
        p.face = 1 if mx > 0 else -1
    sp = WSPD if p.wade else SPD
    p.vx = 0.0 if (p.prone or p.dive) else mx * sp
    if jump and p.ground and not p.prone:
        p.vy = -V0 * (0.9 if p.wade else 1.0)
        p.ground = False
        p.air = True
        p.wade = False
    # aim index: 0 forward, 1 up-forward, 2 up, 3 down-forward, 4 down
    p.aim = aim_in
    carried = 0.0
    if p.ground:
        if p.stand is not None and p.stand.alive:
            carried = p.stand.dx
    if p.ground and not p.wade:
        ly = land(G, p.x, p.y - 2, p.y + 2)
        if ly is None:
            p.ground = False
            p.air = True
            p.vy = 0.0
        else:
            p.y = ly
            p.stand = next((e for e in G.dyn if e.alive and abs(e.x - p.x) <= e.hw + 3 and abs(e.y - ly) < 1), None)
    if not p.ground:
        oy = p.y
        p.vy = min(VMAX, p.vy + GRAV)
        p.y += p.vy
        if p.vy > 0:
            ly = land(G, p.x, oy, p.y)
            if ly is not None:
                p.y, p.vy, p.ground, p.air = ly, 0.0, True, False
                p.air = False
                p.stand = next((e for e in G.dyn if e.alive and abs(e.x - p.x) <= e.hw + 3 and abs(e.y - ly) < 1), None)
        if wy is not None and p.y >= wy:
            p.y, p.vy, p.ground, p.air = wy, 0.0, True, False
            p.stand = None
    if not p.ground:
        p.stand = None
    p.x += p.vx + carried
    lo = G.cam_x + 8 if not G.vert else 8
    hi = G.cam_x + 248 if not G.vert else 248
    if G.wall_x is not None:
        hi = min(hi, G.wall_x)
    p.x = max(lo, min(hi, p.x))
    if G.vert:
        if p.y > G.cam_y + 250:
            hurt(G, p)
            return
    elif st["water_y"] is None and p.y > 236:
        hurt(G, p)
        return
    if fire and not p.dive:
        shoot(G, p)
    # contact with enemies and bullets
    hb = phb(p)
    for e in G.en:
        if e.alive and e.kind in HURT and overlap(hb, box(e)):
            hurt(G, p)
            break
    for b in G.eb:
        if b.alive and hb[0] < b.x < hb[2] and hb[1] < b.y < hb[3] and not p.dive:
            b.alive = False
            hurt(G, p)
            break
    if p.dead:
        return
    for e in G.en:
        if e.alive and e.kind == "item" and abs(e.x - p.x) < 14 and abs((e.y - 6) - (p.y - 16)) < 18:
            collect(G, p, e)


def respawn(G, p):
    if G.vert:
        cand = [q for q in G.plats if G.cam_y + 40 < q[2] < G.cam_y + 190]
        q = min(cand, key=lambda t: abs(t[2] - (G.cam_y + 110))) if cand else (60, 200, G.cam_y + 120)
        x, y = (q[0] + q[1]) / 2, G.cam_y - 6
    else:
        x = G.cam_x + 36 + 24 * p.idx
        while land(G, x, -50, 400) is None and x < G.cam_x + 220:
            x += 8
        y = -8
    p.spawn(x, y)
    p.stand = None
    p.reset_weapon()


def collect(G, p, e):
    e.alive = False
    L = e.letter
    p.score += 1000
    if L == "R":
        p.rapid = True
    elif L == "B":
        p.barrier = 600
    else:
        p.wep = L


def shoot(G, p):
    if p.cd > 0:
        return
    cd, spd, dmg, mx = WEAPONS[p.wep]
    mine = [b for b in G.pb if b.owner == p.idx and b.alive]
    if len(mine) + (5 if p.wep == "S" else 1) > mx + (4 if p.wep == "S" else 0):
        return
    a = p.aim
    f = p.face
    if p.prone:
        d = (f, 0)
        oy = p.y - 6
    else:
        d = (f * (1, 1, 0, 1, 0)[a], (0, -1, -1, 1, 1)[a])
        if p.wade and a >= 3:
            d = (f, 0)
        oy = p.y - 22 + (d[1] * 4)
    ox = p.x + d[0] * 14
    n = math.hypot(*d)
    ux, uy = d[0] / n, d[1] / n
    kind = {"N": "pn", "M": "pm", "S": "ps", "L": "pl", "F": "pf"}[p.wep]
    p.cd = max(2, int(cd * (0.7 if p.rapid and p.wep != "L" else 1)))
    di = DIRS.index(d)
    if p.wep == "S":
        for ang in (-0.36, -0.18, 0.0, 0.18, 0.36):
            ca, sa = math.cos(ang), math.sin(ang)
            vx, vy = (ux * ca - uy * sa) * spd, (ux * sa + uy * ca) * spd
            G.pb.append(Bullet(ox, oy, vx, vy, p.idx, dmg, kind))
    else:
        b = Bullet(ox, oy, ux * spd, uy * spd, p.idx, dmg, kind, di=di, hit=set())
        if p.wep == "F":
            b.px, b.py, b.base = -uy, ux, (ox, oy)
        G.pb.append(b)


# ---- bullets ----------------------------------------------------------------------------------------------------
def update_bullets(G):
    cx0, cx1 = G.cam_x - 30, G.cam_x + 286
    cy0, cy1 = G.cam_y - 30, G.cam_y + 270
    for b in G.pb:
        if b.kind == "pf":
            b.t += 1
            b.base = (b.base[0] + b.vx, b.base[1] + b.vy)
            off = math.sin(b.t * 0.7) * 6
            b.x, b.y = b.base[0] + b.px * off, b.base[1] + b.py * off
        else:
            b.x += b.vx
            b.y += b.vy
        if not (cx0 < b.x < cx1 and cy0 < b.y < cy1):
            b.alive = False
            continue
        for e in G.en:
            if not e.alive:
                continue
            k = e.kind
            if k not in HB and k != "orb_seg" and k != "bsec":
                continue
            if k == "bsec" or k == "item":
                continue
            if k == "orb_seg":
                hw, up, dn = 7, 7, 7
            else:
                hw, up, dn = HB[k]
            if e.x - hw < b.x < e.x + hw and e.y - up < b.y < e.y + dn:
                if k == "orb_seg" or (not e.vul and k in BLOCK):
                    if b.kind != "pl":
                        b.alive = False
                    break
                if not e.vul:
                    continue
                if b.kind == "pl":
                    if id(e) in b.hit:
                        continue
                    b.hit.add(id(e))
                else:
                    b.alive = False
                e.hp -= b.dmg
                e.flash = 3
                if e.hp <= 0:
                    kill(G, e, b.owner)
                if not b.alive:
                    break
    G.pb = [b for b in G.pb if b.alive]
    for b in G.eb:
        b.t += 1
        if b.g:
            b.vy += b.g
        b.x += b.vx
        b.y += b.vy
        if b.kind == "shell" and b.vy >= 0 and b.alive:
            b.alive = False
            for vx in (-1.4, 0.0, 1.4):
                G.eb.append(Bullet(b.x, b.y, vx, 1.8, kind="eb"))
        if b.g and b.alive and b.vy > 0:
            if land(G, b.x, b.y - b.vy, b.y) is not None:
                b.alive = False
                explode(G, b.x, b.y, False)
        if not (cx0 - 20 < b.x < cx1 + 20 and cy0 - 20 < b.y < cy1 + 20):
            b.alive = False
    G.eb = [b for b in G.eb if b.alive]


def enemy_shot(G, x, y, tx, ty, speed=3.0, kind="eb", **kw):
    dx, dy = tx - x, ty - y
    n = math.hypot(dx, dy) or 1
    G.eb.append(Bullet(x, y, dx / n * speed, dy / n * speed, kind=kind, **kw))


def quant8(dx, dy):
    """Nearest of the 8 compass directions (y up) for a vector, as an index into DIRS."""
    a = math.atan2(-dy, dx)
    return int(round(a / (math.pi / 4))) % 8


def on_screen(G, e, pad=0):
    sx = e.x - G.cam_x
    sy = e.y - G.cam_y
    return -pad < sx < 256 + pad and -pad < sy < 240 + pad


# ---- enemy behaviours ---------------------------------------------------------------------------------------------
def u_soldier(G, e):
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is not None and e.t % 20 == 0 and e.turns < 2 and (e.x - p.x) * e.face < 0 and abs(e.x - p.x) > 20 and random.random() < 0.15:
        e.face, e.vx = -e.face, -e.vx
        e.turns += 1
    e.x += e.vx
    if e.ground:
        ly = land(G, e.x, e.y - 2, e.y + 2)
        if ly is None:
            e.ground, e.vy = False, 0.0
            if random.random() < 0.5 and e.vy == 0:
                e.vy = -4.0
        else:
            e.y = ly
    if not e.ground:
        oy = e.y
        e.vy = min(VMAX, e.vy + GRAV)
        e.y += e.vy
        ly = land(G, e.x, oy, e.y) if e.vy > 0 else None
        if ly is not None:
            e.y, e.vy, e.ground = ly, 0.0, True
    if e.shoot and p is not None and on_screen(G, e, -20):
        e.fire -= 1
        if e.fire <= 0:
            e.fire = random.randint(60, 120)
            enemy_shot(G, e.x + e.face * 8, e.y - 20, p.x, p.y - 16, 2.6)
    if not (G.cam_x - 60 < e.x < G.cam_x + 320) or e.y > G.cam_y + 290:
        e.alive = False


def u_sniper(G, e):
    p = nearest_player(G, e.x, e.y)
    e.t += 1
    if p is None:
        return
    near = abs(p.x - e.x) < 190 and on_screen(G, e, -8)
    if e.st == 0:
        e.vul = False
        if near and e.t > 20:
            e.st, e.t = 1, 0
    elif e.st == 1:
        e.vul = True
        e.aimd = quant8(p.x - e.x, p.y - 16 - (e.y - 20))
        if e.t % 40 == 25:
            ux, uy = DIRS[e.aimd]
            n = math.hypot(ux, uy)
            G.eb.append(Bullet(e.x + ux / n * 12, e.y - 20 + uy / n * 12, ux / n * 3.0, uy / n * 3.0))
            e.shots += 1
        if e.shots >= 3 and e.t > 110:
            e.st, e.t, e.shots = 0, -40, 0
    if not on_screen(G, e, 30) and (e.x < G.cam_x or e.y > G.cam_y + 250):
        e.alive = False


def u_wsniper(G, e):
    p = nearest_player(G, e.x, e.y)
    e.t += 1
    if p is None:
        return
    e.aimd = quant8(p.x - e.x, p.y - 16 - (e.y - 20))
    if e.t % 55 == 30:
        ux, uy = DIRS[e.aimd]
        n = math.hypot(ux, uy)
        G.eb.append(Bullet(e.x + ux / n * 12, e.y - 20 + uy / n * 12, ux / n * 3.0, uy / n * 3.0))


def u_turret(G, e):
    p = nearest_player(G, e.x, e.y)
    e.t += 1
    if p is None:
        return
    tx, ty = p.x - e.x, p.y - 16 - (e.y - 12)
    want = int(round((math.pi - math.atan2(-ty, tx)) / (2 * math.pi / 12))) % 12
    if e.t % 5 == 0 and want != e.step:
        d = (want - e.step) % 12
        e.step = (e.step + (1 if d <= 6 else -1)) % 12
    e.fire -= 1
    if e.fire <= 0 and (on_screen(G, e, -6) and abs(tx) < 230):
        e.fire = 100 if not getattr(e, "bomb", False) else 100
        a = math.pi - e.step * 2 * math.pi / 12
        vx, vy = math.cos(a), -math.sin(a)
        if getattr(e, "bomb", False):
            G.eb.append(Bullet(e.x - 10, e.y - 20, -1.0 - random.random() * 1.8, -4.8, kind="eb", g=0.22))
        else:
            G.eb.append(Bullet(e.x + vx * 14, e.y - 12 + vy * 14, vx * 2.6, vy * 2.6))
    if e.x < G.cam_x - 40 or e.y > G.cam_y + 300:
        e.alive = False


def u_cannon(G, e):
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is None:
        return
    if e.st == 0 and abs(p.x - e.x) < 150 and e.x > G.cam_x + 10:
        e.st, e.t = 1, 0
    if e.st == 1:
        if e.t > 16:
            e.st, e.t, e.vul = 2, 0, True
    elif e.st == 2:
        e.fire -= 1
        if e.fire <= 0:
            e.fire = 55
            for k in range(3):
                G.eb.append(Bullet(e.x - 12 - k * 8, e.y - 12, -3.4, 0.0))
    if e.x < G.cam_x - 40:
        e.alive = False


def u_sensor(G, e):
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is None:
        return
    if e.st == 0:
        e.vul = False
        if on_screen(G, e, -10) and abs(p.x - e.x) < 200 and e.t > 30:
            e.st, e.t = 1, 0
    elif e.st == 1:
        if e.t > 8:
            e.st, e.t = 2, 0
    elif e.st == 2:
        e.vul = True
        if e.t > 55:
            e.st, e.t, e.vul = 0, 0, False
    if e.x < G.cam_x - 40 or e.y > G.cam_y + 300:
        e.alive = False


def u_capsule(G, e):
    e.t += 1
    if G.vert:
        e.y -= 1.5
        e.x = e.base + math.sin(e.t * 0.09) * 70
        if e.y < G.cam_y - 20:
            e.alive = False
    else:
        e.x += 1.7
        e.y = e.base + math.sin(e.t * 0.1) * 24
        if e.x > G.cam_x + 280:
            e.alive = False


def u_item(G, e):
    e.t += 1
    oy = e.y
    e.vy = min(VMAX, e.vy + 0.3)
    e.y += e.vy
    if e.vy > 0:
        ly = land(G, e.x, oy, e.y)
        if ly is not None:
            e.y, e.vy = ly, 0.0
    if e.y > G.cam_y + 270 or e.x < G.cam_x - 30 or e.t > 900:
        e.alive = False


def u_scuba(G, e):
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is None:
        return
    if e.st == 0:
        e.vul = False
        if abs(p.x - e.x) < 110 and e.t > 40:
            e.st, e.t = 1, 0
    elif e.st == 1:
        e.vul = True
        if e.t == 14:
            G.eb.append(Bullet(e.x, e.y - 22, 0.0, -4.2, kind="shell", g=0.16))
        if e.t > 50:
            e.st, e.t, e.vul = 0, 0, False
    if e.x < G.cam_x - 40:
        e.alive = False


def u_boulder(G, e):
    e.t += 1
    oy = e.y
    e.vy = min(VMAX, e.vy + GRAV * 0.8)
    e.y += e.vy
    e.x += e.vx
    if e.vy > 0:
        ly = land(G, e.x, oy, e.y)
        if ly is not None:
            e.y, e.vy = ly, -3.2
    if e.x < 4 or e.x > 252:
        e.vx = -e.vx
    if e.y > G.cam_y + 270:
        e.alive = False


def u_cave(G, e):
    e.t += 1
    if on_screen(G, e, -20) and e.t % 85 == 0:
        G.en.append(E("boulder", e.x, e.y, hp=2, vx=(1.0 if e.x < 128 else -1.0) * 0.8, vy=0.0))
    if e.y > G.cam_y + 270:
        e.alive = False


def u_flame(G, e):
    e.x += e.vx
    if e.x < e.bx0 or e.x > e.bx1:
        e.vx = -e.vx
    e.t += 1


def u_float(G, e):
    e.x += e.vx
    e.dx = e.vx
    if e.x < e.bx0 or e.x > e.bx1:
        e.vx = -e.vx
    if e.y > G.cam_y + 270:
        e.alive = False


def u_bsec(G, e):
    """A bridge section: the whole bridge blows up one section at a time behind the first player who steps on it."""
    if not e.trig:
        for p in G.players:
            if not p.dead and p.ground and abs(p.x - e.x) < 14 and abs(p.y - e.y) < 3:
                e.trig = True
                e.t = 0
                for o in G.dyn:
                    if o.kind == "bsec" and o.x > e.x and not o.trig and o.x - e.x < 200:
                        o.trig = True
                        o.t = -int((o.x - e.x) / 16) * 5
        return
    e.t += 1
    if e.t == 14:
        e.alive = False
        explode(G, e.x, e.y + 4, True)


def u_mouth(G, e):
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is None:
        return
    e.fire -= 1
    on = on_screen(G, e, -10)
    e.st = 2 if (on and e.fire < 12) else (1 if (on and e.fire < 22) else 0)
    if e.fire <= 0:
        e.fire = 110
        if on and abs(e.x - G.cam_x - 128) < 120:
            G.en.append(E("spore", e.x, e.y + (8 if e.kind == "mouth" else -8), hp=1, vx=0.0, vy=1.0 if e.kind == "mouth" else -2.6))
    if e.x < G.cam_x - 60:
        e.alive = False


def u_bighead(G, e):
    e.t += 1
    e.fire -= 1
    on = on_screen(G, e, -10)
    e.st = 2 if (on and e.fire < 14) else (1 if (on and e.fire < 24) else 0)
    if e.fire <= 0:
        e.fire = 50
        if on:
            G.en.append(E("floater", e.x + random.randint(-10, 10), e.y + 14, hp=1, ph=random.random() * 6))
    if e.x < G.cam_x - 80:
        e.alive = False


def u_floater(G, e):
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is not None:
        dx, dy = p.x - e.x, p.y - 16 - e.y
        n = math.hypot(dx, dy) or 1
        e.vx += (dx / n * 1.2 - e.vx) * 0.05
        e.vy += (dy / n * 1.2 - e.vy) * 0.05
    e.x += e.vx
    e.y += e.vy + math.sin(e.t * 0.2 + e.ph) * 0.5
    if e.x < G.cam_x - 80 or e.y > G.cam_y + 280:
        e.alive = False


def u_spore(G, e):
    """Homing spore: steers toward the nearest commando at a walking pace and burns out after a few seconds."""
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is not None and 22 <= e.t < 150:
        dx, dy = p.x - e.x, p.y - 14 - e.y
        n = math.hypot(dx, dy) or 1
        e.vx += (dx / n * 1.3 - e.vx) * 0.05
        e.vy += (dy / n * 1.3 - e.vy) * 0.05
    e.x += e.vx
    e.y += e.vy
    if e.t > 150 or e.x < G.cam_x - 40:
        e.alive = False


def u_crawler(G, e):
    e.t += 1
    p = nearest_player(G, e.x, e.y)
    if p is not None:
        e.vx = 2.4 if p.x > e.x else -2.4
    e.x += e.vx
    ly = land(G, e.x, e.y - 3, e.y + 3)
    if ly is not None:
        e.y = ly
    if e.x < G.cam_x - 60 or e.x > G.cam_x + 330:
        e.alive = False


def u_cocoon(G, e):
    e.t += 1
    e.fire -= 1
    e.st = 2 if e.fire < 14 else (1 if e.fire < 26 else 0)
    if e.fire <= 0:
        e.fire = 90
        G.en.append(E("crawler", e.x, 190, hp=1, vx=-2.4 if e.x > 3240 else 2.4))


def u_heart(G, e):
    e.t += 1


def u_core(G, e):
    e.t += 1


def u_head(G, e):
    e.t += 1
    e.fire -= 1
    e.st = 2 if G.head.vul else 0
    if G.head.vul and e.fire <= 0:
        e.fire = 110
        for vx in (-1.5, 0.0, 1.5):
            G.eb.append(Bullet(e.x, e.y + 8, vx, 2.2, kind="fire"))


def u_orb(G, e):
    e.t += 1
    # the arm sweeps like a pendulum around its shoulder; the tip is the weak point
    a = math.pi / 2 + (math.sin(e.t * 0.035 + e.side * 2.0) * 0.9) * (1 if e.side else -1) + (0.5 if e.side else -0.5)
    L = 52
    e.x = e.sx + math.cos(a) * L
    e.y = e.sy + math.sin(a) * L
    for i, s in enumerate(G.arms[e.side][1]):
        f = (i + 1) / 4
        s.x = e.sx + math.cos(a) * L * f
        s.y = e.sy + math.sin(a) * L * f
    e.fire -= 1
    p = nearest_player(G, e.x, e.y)
    if e.fire <= 0 and p is not None:
        e.fire = 170
        enemy_shot(G, e.x, e.y, p.x, p.y - 14, 2.0, kind="fire")


def u_orb_seg(G, e):
    pass


UPD = {"soldier": u_soldier, "sniper": u_sniper, "wsniper": u_wsniper, "turret": u_turret, "bturret": u_turret,
       "cannon": u_cannon, "sensor": u_sensor, "capsule": u_capsule, "item": u_item, "scuba": u_scuba,
       "boulder": u_boulder, "cave": u_cave, "flame": u_flame, "float": u_float, "bsec": u_bsec, "mouth": u_mouth,
       "fmouth": u_mouth, "bighead": u_bighead, "floater": u_floater, "spore": u_spore, "crawler": u_crawler,
       "cocoon": u_cocoon, "heart": u_heart, "core": u_core, "head": u_head, "orb": u_orb, "orb_seg": u_orb_seg}
HB["orb_seg"] = (7, 7, 7)
HB["cave"] = (1, 1, 1)
HB["float"] = (20, 3, 0)
HB["bsec"] = (8, 0, 0)


# ---- rendering ----------------------------------------------------------------------------------------------------
def render(G):
    st = G.st
    if G.vert:
        fr = (G.tick // 6) % 3
        rows = st["frames"][fr]
        cy = G.cam_y
        for y in range(240):
            FR[y][VIS0:VIS0 + VISW] = rows[cy + y]
    else:
        a = G.cam_x * 8
        fg = st["fg"]
        if "sky" in st:
            sky = st["sky"]
            sa = (G.cam_x >> 2) * 8
            b0, b1 = st["blend"]
            for y in range(b0):
                FR[y][VIS0:VIS0 + VISW] = sky[y][sa:sa + VISW]
            mk = st["mask"]
            for y in range(b0, b1):
                s = int.from_bytes(sky[y][sa:sa + VISW], "little")
                f = int.from_bytes(fg[y][a:a + VISW], "little")
                m = int.from_bytes(mk[y - b0][a:a + VISW], "little")
                FR[y][VIS0:VIS0 + VISW] = (s ^ ((s ^ f) & m)).to_bytes(VISW, "little")
            wy0 = st["water_y0"]
            wat = st["water"][(G.tick // 14) & 1]
            for y in range(b1, wy0):
                FR[y][VIS0:VIS0 + VISW] = fg[y][a:a + VISW]
            for y in range(wy0, 240):
                FR[y][VIS0:VIS0 + VISW] = wat[y - wy0][a:a + VISW]
        else:
            for y in range(240):
                FR[y][VIS0:VIS0 + VISW] = fg[y][a:a + VISW]
    cx, cy = G.cam_x, G.cam_y
    for e in G.en:
        DRAW[e.kind](G, e, e.x - cx, e.y - cy)
    for p in G.players:
        draw_player(G, p, cx, cy)
    for b in G.pb:
        s = SP[b.kind]
        put(s[b.di] if b.kind == "pl" else s[(G.tick // 2) % len(s)], b.x - cx, b.y - cy)
    for b in G.eb:
        k = b.kind
        if k == "fire":
            put(SP["fireball"][(G.tick // 2) % 4], b.x - cx, b.y - cy)
        else:
            put(SP["eb"][0], b.x - cx, b.y - cy)
    for f in G.fx:
        if f[2] >= 0:
            put(SP["exp_b" if f[3] else "exp_s"][f[2]], f[0] - cx, f[1] - cy)
    hud(G)
    flush()
    hud_text(G)


def hud(G):
    for p in G.players:
        spr = SP["medal"]["blue" if p.idx == 0 else "orange"][0]
        for i in range(min(p.lives, 8)):
            x = 10 + i * 13 if p.idx == 0 else 246 - i * 13
            put(spr, x, 6)


def hud_text(G):
    c = G.hud_cache
    for p in G.players:
        key = (p.score, p.lives)
        if c.get(p.idx) != key:
            c[p.idx] = key
            x = 60 if p.idx == 0 else W - 448 + 60 - 20
            draw_text("%dP" % (p.idx + 1), x, 120, "S", COLOR_YELLOW if p.idx == 0 else COLOR_RED)
            draw_text("%07d" % p.score, x, 160, "S", COLOR_WHITE)
    n = (1, 3, 8)[G.stage_i]
    if c.get("st") != n:
        c["st"] = n
        draw_text("STAGE %d" % n, 60, 300, "S", COLOR_CYAN)
        draw_text(G.st["name"], 60, 340, "S", COLOR_GREEN)


def d_soldier(G, e, x, y):
    pal = "rsoldier" if e.red else "soldier"
    d = SP[pal][0 if e.face > 0 else 1]
    if e.ground:
        put(d["run0"][(e.t // 4) % 4], x, y)
    else:
        put(d["jump"][(e.t // 3) % 4], x, y - 14)


def d_sniper(G, e, x, y):
    d = SP["sniper"]
    if e.st == 1:
        ux = DIRS[e.aimd][0]
        side = 0 if ux >= 0 else 1
        uy = DIRS[e.aimd][1]
        aim = 2 if ux == 0 and uy < 0 else (1 if uy < 0 else (3 if uy > 0 else 0))
        put(d[side]["stand%d" % aim][0], x, y)
    elif not e.bush:
        put(d[0]["stand0"][0], x, y)
    if e.bush:
        put(SP["bush"][0], x, y + 1)


def d_wsniper(G, e, x, y):
    ux, uy = DIRS[e.aimd]
    side = 0 if ux >= 0 else 1
    aim = 2 if ux == 0 and uy < 0 else (1 if uy < 0 else (3 if uy > 0 else 0))
    put(SP["sniper"][side]["stand%d" % aim][0], x, y)


def d_turret(G, e, x, y):
    put(SP["turret" if e.kind == "turret" else "bturret"][e.step], x, y)


def d_cannon(G, e, x, y):
    if e.st:
        put(SP["cannon"][(0 if e.t < 8 and e.st == 1 else 1) if e.st == 1 else 2], x, y)


def d_sensor(G, e, x, y):
    put(SP["sensor"][e.st if e.st < 2 else (2 if (G.tick // 3) % 2 else 1)], x, y)


def d_capsule(G, e, x, y):
    put(SP["capsule"][(e.t // 4) % 2], x, y)


def d_item(G, e, x, y):
    put(SP["item"][e.letter][0], x, y)


def d_scuba(G, e, x, y):
    put(SP["scuba"][0 if e.st == 0 else 1], x, y)


def d_boulder(G, e, x, y):
    put(SP["boulder"][(e.t // 3) % 4], x, y)


def d_flame(G, e, x, y):
    put(SP["flame"][(G.tick // 3) % 2], x, y)


def d_float(G, e, x, y):
    put(SP["float"][0], x, y)


def d_bsec(G, e, x, y):
    if e.trig and e.t > 8 and e.t % 2:
        return
    x0 = int(x) - 8
    if x0 <= -MARG or x0 + 16 >= 256 + MARG:
        return
    o = (x0 + MARG) * 8
    for j, row in enumerate(BRIDGE_ROWS):
        yy = int(y) + j
        if 0 <= yy < 240:
            FR[yy][o:o + 128] = row


def _solid(rgb):
    return rgb565(*rgb).to_bytes(2, "little") * 64


def _truss(a, b):
    # 16 virtual pixels of girder: dark diagonal braces on a lighter plate
    px = [rgb565(*(b if (i % 8) in (3, 4) else a)).to_bytes(2, "little") * 4 for i in range(16)]
    return b"".join(px)


BRIDGE_ROWS = [_solid((224, 224, 232)), _solid((188, 188, 188)), _solid((100, 100, 108)), _truss((188, 188, 188), (60, 60, 70)),
               _truss((100, 100, 108), (0, 0, 0)), _truss((60, 60, 70), (0, 0, 0))]


def mouth_draw(key):
    def f(G, e, x, y):
        put(SP[key][e.st], x, y)
    return f


def d_floater(G, e, x, y):
    put(SP["floater"][0 if e.vx > 0 else 1][(e.t // 5) % 2], x, y)


def d_spore(G, e, x, y):
    put(SP["spore"][(G.tick // 3) % 2], x, y)


def d_crawler(G, e, x, y):
    put(SP["crawler"][0 if e.vx > 0 else 1][(e.t // 3) % 2], x, y)


def d_cocoon(G, e, x, y):
    put(SP["cocoon"][e.st], x, y)


def d_heart(G, e, x, y):
    put(SP["heart"][1 if (G.tick // 8) % 2 else 0], x, y)


def d_core(G, e, x, y):
    put(SP["core"][0 if not e.vul else (1 + (G.tick // 4) % 2)], x, y)


def d_head(G, e, x, y):
    put(SP["head"][e.st if e.st else 0], x, y)


def d_orb(G, e, x, y):
    put(SP["orb"][0], x, y)


def d_none(G, e, x, y):
    pass


DRAW = {"soldier": d_soldier, "sniper": d_sniper, "wsniper": d_wsniper, "turret": d_turret, "bturret": d_turret,
        "cannon": d_cannon, "sensor": d_sensor, "capsule": d_capsule, "item": d_item, "scuba": d_scuba,
        "boulder": d_boulder, "cave": d_none, "flame": d_flame, "float": d_float, "bsec": d_bsec,
        "mouth": mouth_draw("mouth"), "fmouth": mouth_draw("fmouth"), "bighead": mouth_draw("bighead"),
        "floater": d_floater, "spore": d_spore, "crawler": d_crawler, "cocoon": d_cocoon, "heart": d_heart,
        "core": d_core, "head": d_head, "orb": d_orb, "orb_seg": d_orb}


def draw_player(G, p, cx, cy):
    if p.out:
        return
    d = SP[p.pal][0 if p.face > 0 else 1]
    x, y = p.x - cx, p.y - cy
    if p.dead:
        if p.dt < 70:
            put(d["dead"][min(3, p.dt // 7)], x, y)
        return
    if p.inv > 0 and (p.inv // 3) % 2 == 0 and p.barrier == 0:
        return
    if p.dive:
        s = d["dive"][0]
    elif p.prone:
        s = d["prone"][0]
    elif p.air:
        s = d["jump"][(p.anim // 3) % 4]
    elif p.wade:
        s = d["wade%d" % (p.aim if p.aim < 3 else 0)][0]
    else:
        aim = p.aim
        if abs(p.vx) > 0.1:
            s = d["run%d" % aim][(p.anim // 3) % 4]
        else:
            s = d["stand%d" % aim][0]
    put(s, x, y)
    if p.barrier > 0:
        r = 14 + (G.tick // 3) % 2
        for dx, dy in ((-r, -22), (r, -22), (0, -22 - r), (0, -22 + r), (-10, -32), (10, -32), (-10, -12), (10, -12)):
            put(SP["pn"][0], x + dx, y + dy)


# ---- the bots ----------------------------------------------------------------------------------------------------
HALT = {"turret", "bturret", "cannon", "sniper", "wsniper", "mouth", "fmouth", "bighead"}
NOOP = (0, 0, 0, 0, 0, 0)


def aim_of(ux, uy):
    """Sprite aim index (0 forward, 1 up-forward, 2 up, 3 down-forward, 4 down) for a direction vector."""
    if uy == 0:
        return 0
    if uy < 0:
        return 2 if ux == 0 else 1
    return 4 if ux == 0 else 3


def pick_target(G, p):
    """Best enemy that can be hit now: (enemy, direction index, lined up with a straight or diagonal shot)."""
    spread = p.wep == "S"
    gx, gy = p.x, p.y - 22
    best, best_s = None, -1e9
    for e in G.en:
        k = e.kind
        if not e.alive or k not in PRIO or not (e.vul or k == "capsule") or not on_screen(G, e, -2):
            continue
        hw, up, dn = HB[k]
        dx, dy = e.x - gx, e.y - (up - dn) / 2 - gy
        dist = math.hypot(dx, dy)
        if dist > 235 or dist < 1:
            continue
        bd, bperp = None, 1e9
        for di, (ux, uy) in enumerate(DIRS):
            if p.ground and uy > 0:
                continue
            n = math.hypot(ux, uy)
            if (dx * ux + dy * uy) / n <= 0:
                continue
            perp = abs(dx * uy - dy * ux) / n
            if perp < bperp:
                bd, bperp = di, perp
        if bd is None:
            continue
        aligned = bperp <= (hw - 2 if k in STATIONARY else hw + 3) + (0.3 * dist if spread else 0)
        prone = False
        if not aligned and p.ground and not p.wade and abs(e.y - (up - dn) / 2 - (p.y - 6)) <= (up + dn) / 2 + 2:
            # a low target (ground cannon, crawler) is only hit from the prone position
            aligned, prone, bd = True, True, 0 if e.x > p.x else 4
        score = PRIO[k] - dist * 0.15 + (40 if aligned else 0)
        if score > best_s:
            best, best_s = (e, bd, aligned, prone), score
    return best


def align_x(e, gy):
    """Standing x from which a vertical or 45 degree shot reaches the enemy."""
    _, up, dn = HB[e.kind]
    h = gy - (e.y - (up - dn) / 2)
    return [e.x, e.x - h, e.x + h] if h > 0 else [e.x - 60, e.x + 60]


def bot(G, p):
    """One tick of input for a player: (move x, aim index, down, jump, fire, facing)."""
    if p.dead:
        return NOOP
    st = G.st
    mem = p.mem
    px, py = p.x, p.y
    tgt = pick_target(G, p)
    fire, aim, face, want_x = 0, 0, 0, None
    want_prone = False
    if tgt is not None:
        e, di, aligned, low = tgt
        ux, uy = DIRS[di]
        if aligned:
            fire, aim = 1, aim_of(ux, uy)
            face = 1 if ux > 0 else (-1 if ux < 0 else p.face)
            if low:
                want_prone = True
        elif e.kind in STATIONARY:
            # the spot is chosen once per target; re-choosing every tick makes the bot dither between two spots
            if mem.get("wt") is not e:
                opts = [o for o in align_x(e, py - 22) if G.vert or G.cam_x + 14 < o < min(G.cam_x + 242, G.wall_x or 1e9)]
                mem["wt"], mem["wx"] = e, (min(opts, key=lambda o: abs(o - px)) if opts else None)
            want_x = mem["wx"]
    # movement
    jump = 0
    if G.boss_active and not G.boss_dead:
        kind = st["boss"]["kind"]
        if kind == "wall":
            hold = G.wall_x - 70 - p.idx * 40
        elif kind == "alien":
            hold = 70 + p.idx * 116
        else:
            hold = st["boss"]["x"] - 90 - p.idx * 40
        mx = 1 if px < hold - 6 else (-1 if px > hold + 6 else 0)
        if want_x is not None and abs(want_x - hold) < 130:
            mx = 1 if want_x > px + 3 else (-1 if want_x < px - 3 else 0)
    elif G.vert:
        mx, jump = climb(G, p, mem)
        # shooters above are cleared from the current ledge before climbing past them: a somersault cannot dodge
        for e in G.en:
            if e.alive and e.kind in HALT and e.y > py - 160 and e.y < py + 30 and on_screen(G, e, -4):
                k = id(e)
                mem[k] = mem.get(k, 0) + 1
                if mem[k] < (260 if fire else 80) and p.ground:
                    mx, jump = 0, 0
                    cur = next(((a, b) for a, b, y in G.plats if a - 3 <= px <= b + 3 and abs(y - py) < 2), None)
                    if want_x is not None and cur is not None:
                        wx = max(cur[0] + 8, min(cur[1] - 8, want_x))
                        mx = 1 if wx > px + 3 else (-1 if wx < px - 3 else 0)
                break
    else:
        mx = 1
        for e in G.en:
            if e.alive and e.kind in HALT and 0 < e.x - px < p.rush and on_screen(G, e, -4):
                mem[id(e)] = mem.get(id(e), 0) + 1
                if mem[id(e)] < 260:
                    mx = 0
                break
        if want_x is not None and mem.get("w", 0) < 400:
            mem["w"] = mem.get("w", 0) + 1
            mx = 1 if want_x > px + 3 else (-1 if want_x < px - 3 else 0)
        if px > G.cam_x + 205 and mx > 0 and G.cam_x < st["lock"] and random.random() < 0.5:
            mx = 0
        mx, jump = terrain(G, p, mx, jump)
        # committed jumps keep their direction: stopping in mid-air over a pit is fatal
        if p.ground:
            mem["jdir"] = mx if jump else 0
        elif mem.get("jdir"):
            mx = mem["jdir"]
    for e in G.en:
        if e.alive and e.kind == "item" and abs(e.x - px) < 100 and abs(e.y - py) < 40:
            mx = 1 if e.x > px + 3 else (-1 if e.x < px - 3 else 0)
            if e.y < py - 20 and p.ground:
                jump = 1
            break
    down = 0
    # dodging: a bullet that will cross the body within 12 ticks; the decision is made once per bullet so a miss is a miss
    for b in G.eb:
        hit = None
        for t in range(0, 14):
            by = b.y + b.vy * t + 0.5 * b.g * t * t
            if abs(b.x + b.vx * t - px - mx * SPD * t) < 10 and py - 34 < by < py + 2:
                hit = (t, by)
                break
        if hit is None:
            continue
        if "dodge" not in b.__dict__:
            b.dodge = random.random() < p.skill
        if b.dodge:
            t, by = hit
            if b.vy > 0.8 * abs(b.vx) and b.vy > 0.5:
                # a steep shot passes through a crouching or jumping body as well: step out of its way
                impact = b.x + b.vx * (py - 14 - b.y) / b.vy
                mx = 1 if px >= impact else -1
                if px < 20:
                    mx = 1
                elif px > 236:
                    mx = -1
            elif p.wade:
                down, mx = 1, 0
            elif p.ground:
                if by > py - 9 and t <= 9 and not G.boss_active:
                    jump = 1
                elif by <= py - 9:
                    down, mx = 1, 0
        break
    for e in G.en:
        if e.alive and e.kind in HURT and abs(e.x - px) < 40 and e.y > py - 36 and e.y - 24 < py:
            if e.kind == "boulder":
                mx = -1 if e.x > px else 1
            elif e.kind in ("flame", "soldier", "crawler") and p.ground and random.random() < p.skill:
                jump = 1
            break
    if not fire:
        for e in G.en:
            if e.alive and e.kind in HURT and e.kind != "flame" and on_screen(G, e) and abs(e.x - px) < 200:
                fire, face = 1, (1 if e.x > px else -1)
                break
    if want_prone and not down and p.ground and not p.wade:
        down, mx = 1, 0
    return (mx, aim, down, jump, fire, face)


def terrain(G, p, mx, jump):
    """Jump gaps, step up onto higher ledges and hop across the exploding bridges."""
    if not p.ground or p.wade or mx == 0:
        return mx, jump
    px, py = p.x, p.y
    if land(G, px + mx * 6, py - 3, py + 8) is None:
        for dist in (26, 40, 56, 70):
            if land(G, px + mx * dist, py - 38, py + 46) is not None:
                return mx, 1
        return (mx, jump) if G.st["water_y"] is not None else (0, 0)
    for a, b, y in G.plats:
        edge = a if mx > 0 else b
        if py - 38 <= y <= py - 8 and 0 < mx * (edge - px) < 34:
            return mx, 1
    if random.random() < 0.9 and any(e.alive and e.kind == "bsec" and abs(e.x - px) < 9 for e in G.dyn):
        return mx, 1
    return mx, jump


def bullet_soon(G, p, horizon):
    """True if an enemy bullet will cross the body column (head to feet and a jump above) within `horizon` ticks."""
    for b in G.eb:
        for t in range(2, horizon, 3):
            by = b.y + b.vy * t + 0.5 * b.g * t * t
            if abs(b.x + b.vx * t - p.x) < 14 and p.y - 75 < by < p.y + 2:
                return True
    return False


def climb(G, p, mem):
    """Waterfall climbing: pick the highest ledge within one jump, walk under or toward it, then jump."""
    mx, jump = climb_plan(G, p, mem)
    others = [o for o in G.players if o is not p and not o.dead]
    if others and p.ground and others[0].y - p.y > 70:
        return 0, 0
    if jump and p.ground:
        # a somersault is a big slow target: wait for incoming bullets to pass, but not forever
        mem["wait"] = mem.get("wait", 0) + 1
        if mem["wait"] < 45 and bullet_soon(G, p, 26):
            return 0, 0
    else:
        mem["wait"] = 0
    return mx, jump


def climb_plan(G, p, mem):
    """Waterfall climbing: pick the highest ledge within one jump, walk under or toward it, then jump."""
    px, py = p.x, p.y
    tgt = mem.get("tgt")
    if not p.ground:
        if tgt is None:
            return 0, 0
        c = (tgt[0] + tgt[1]) / 2
        return (1 if c > px + 4 else (-1 if c < px - 4 else 0)), 0
    cur = next(((a, b, y) for a, b, y in G.plats if a - 3 <= px <= b + 3 and abs(y - py) < 2), None)
    cands = []
    lo, hi = (cur[0], cur[1]) if cur is not None else (px, px)
    for q in G.plats:
        rise = py - q[2]
        gap = max(q[0] - hi, lo - q[1], 0)
        if 8 <= rise <= 38 and gap <= 44:
            cands.append((gap * 0.5 - rise, q, gap))
    if not cands:
        for e in G.dyn:
            if e.kind == "float" and 8 <= py - e.y <= 38 and abs(e.x - px) < 60:
                return (1 if e.x > px else -1), 1
        return 0, 0
    _, q, gap = min(cands, key=lambda c: c[0])
    mem["tgt"] = q
    if gap == 0:
        c0, c1 = (cur[0], cur[1]) if cur is not None else (q[0], q[1])
        i0, i1 = max(c0, q[0]) + 8, min(c1, q[1]) - 8
        if i0 > i1:
            i0 = i1 = (max(c0, q[0]) + min(c1, q[1])) / 2
        if i0 - 2 <= px <= i1 + 2:
            return 0, 1
        return (1 if px < i0 else -1), 0
    d = 1 if q[0] > px else -1
    if cur is not None and abs((cur[1] if d > 0 else cur[0]) - px) <= 8:
        return d, 1
    return d, 0
