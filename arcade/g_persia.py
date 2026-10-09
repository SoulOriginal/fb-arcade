# Prince of Persia style self-playing game: one 10x3-tile screen at a time, rotoscope-like rig animation,
# traps, sword fights, and a bot that plans a route through each level and plays it by "pressing keys".
from fbcore import *
import math

B = load_bundle("g_persia.bin")
SPR, TILES, MISC, HUD, META = B["spr"], B["tiles"], B["misc"], B["hud"], B["meta"]
HANG_H = B["hang_h"]

SC = 5                  # screen pixels per logical pixel
OX = 160                # left margin: 320 logical px * 5 = 1600 of the 1920 screen
TW, TH, FEET = 32, 63, 54
SCR_W, SCR_H = 10, 3    # tiles per screen, as in the original
LW, LH = SCR_W * TW, SCR_H * TH
HUD_Y = LH * SC
GRAVITY, TERMINAL = 1.3, 19.0
GATE_OPEN_TICKS = 300
TICKS_PER_GAME_SECOND = 5.0     # 30 ticks/s * 1/6: the 60 minute clock runs 6x faster than real time
GAME_MINUTES = 60

# ---------------------------------------------------------------------------------------------------------------
# Screen templates (10x3 tiles). Row 2 is the ground row; every template has floor at both ends of row 2 so any
# sequence of them connects. Legend: . air  # floor  X wall  = loose floor  ^ spikes  P pillar  T torch  V chomper
# A-D gates  a-d plates  E exit door  e exit plate  h/H red potion/big red  z blue (poison)  f green (slow fall)
# S sword  M magic mirror  @ start  1 guard  3 fat guard  4 skeleton  5 shadow  6 vizier
# ---------------------------------------------------------------------------------------------------------------
E3 = ".........."
TEMPLATES = {
    "start": [E3, E3, "#@#T####T#"],
    "exit": [E3, E3, "###T#E##T#"],
    "plain": [E3, E3, "#P#####P##"],
    "plain_torch": ["..###.....", E3, "##T####T##"],
    "gap1": [E3, E3, "###T.#####"],
    "gap2": [E3, E3, "##T..#####"],
    "gap3": [E3, E3, "##T...####"],
    "spike1": [E3, E3, "###^#T####"],
    "spike2": [E3, E3, "#T^###^###"],
    "spike3": [E3, E3, "##T^^#####"],
    "loose1": [E3, E3, "##==.==###"],
    "loose2": [E3, E3, "##=#=#=T##"],
    "chomp1": [E3, E3, "##T#V#####"],
    "chomp2": [E3, E3, "##V###V###"],
    "chomp_spike": [E3, E3, "##V##^T###"],
    "wall1": [E3, "...####...", "###XXXX###"],
    "wall_sword": [E3, "...S###...", "###XXXX###"],
    "wall_potion": [E3, "...H###...", "###XXXX###"],
    "ledge_potion": [E3, ".#H#......", "##########"],
    "plate1": [E3, E3, "#a####A###"],
    "plate_gate2": [E3, E3, "##a#.#A###"],
    "plate_up": [E3, "...#a##...", "###XXXX#A#"],
    "exitplate": [E3, E3, "####e#T###"],
    "guard1": [E3, E3, "##h#T##1##"],
    "guard2": [E3, E3, "####1..###"],
    "guard_fat": [E3, E3, "##h#T#3###"],
    "skeleton": [E3, E3, "####4..###"],
    "mirror": [E3, E3, "##TM####T#"],
    "shadow_merge": [E3, E3, "##T##5#T##"],
    "vizier": [E3, E3, "##hT#6##T#"],
    "poison": [E3, E3, "##z###h###"],
}

# Curated progression: a name is fixed, a tuple is a random choice, so each game differs but every level keeps its gimmick.
RECIPES = {
    1: ["start", "wall_sword", "guard1", "exit"],
    2: ["start", ("gap1", "spike1"), "plate1", ("guard1", "guard2"), "exit"],
    3: ["start", ("spike2", "gap2"), "skeleton", "exitplate", "exit"],
    4: ["start", "mirror", ("chomp1", "spike1"), "plate_up", "guard1", "exit"],
    5: ["start", ("gap2", "loose1"), ("wall1", "ledge_potion"), ("guard2", "guard1"), "exitplate", "exit"],
    6: ["start", ("chomp2", "spike2"), "plate_gate2", ("guard2", "guard_fat"), "exit"],
    7: ["start", ("gap3", "spike3"), "wall_potion", "chomp2", ("guard2", "guard_fat"), "exitplate", "exit"],
    8: ["start", ("gap2", "loose1"), "plate_up", ("guard_fat", "guard2"), ("chomp_spike", "spike2"), "exit"],
    9: ["start", "spike3", ("chomp2", "plate_gate2"), ("guard_fat", "guard2"), ("loose1", "gap3"), "exitplate", "exit"],
    10: ["start", ("chomp_spike", "gap3"), "plate_up", "guard_fat", ("spike3", "chomp2"), "exit"],
    11: ["start", ("gap3", "loose1"), "plate_gate2", "guard_fat", "chomp_spike", "guard2", "exitplate", "exit"],
    12: ["start", "gap3", "shadow_merge", ("chomp2", "spike3"), "plate_up", "vizier", "exit"],
}
LEVELS = 12
THEME_OF = lambda n: "dungeon" if n <= 3 else "palace"


def make_rows(n):
    names = []
    for item in RECIPES[n]:
        names.append(random.choice(item) if isinstance(item, tuple) else item)
    rows = ["", "", ""]
    for nm in names:
        for r in range(3):
            rows[r] += TEMPLATES[nm][r]
    return rows, names

# ---------------------------------------------------------------------------------------------------------------
# World: tile grid plus every trap's state machine
# ---------------------------------------------------------------------------------------------------------------
FLOOR_CH = set("#=^PTVABCDabcdEeM")
PASS_CH = set("VABCD")             # tiles the bot crosses without stopping on
RUNWAY_CH = set("#PTEeabcdM")      # safe to run over
CHOMP_PERIOD = 90
CHOMP_DEADLY = (60, 78)


def chomp_state(ph):
    if ph < 58:
        return 0
    if ph < 61:
        return 1
    if ph < 64:
        return 2
    if ph < 76:
        return 3
    if ph < 79:
        return 2
    if ph < 82:
        return 1
    return 0


class Slab:
    # A loose floor tile in free fall.
    def __init__(self, x, y):
        self.x, self.y, self.vy = x, y, 0.0
        self.alive = True


class World:
    def __init__(self, n, rows=None):
        self.n = n
        self.theme = THEME_OF(n)
        self.rows = rows
        self.w, self.h = len(rows[0]), len(rows)
        self.t = [list(r) for r in rows]
        self.items = {}
        self.spawn = []
        self.start = (1, self.h - 1)
        self.gates, self.plates, self.loose, self.spikes, self.chomp = {}, {}, {}, {}, {}
        self.mirror = {}
        self.rubble = set()
        self.exit_pos = None
        self.exit_k = 0.0
        self.exit_open = False
        self.has_exit_plate = False
        self.tick = 0
        self.slabs = []
        for y in range(self.h):
            for x in range(self.w):
                c = self.t[y][x]
                if c == "@":
                    self.start = (x, y)
                    self.t[y][x] = "#"
                elif c in "1234567" or c == "6":
                    self.spawn.append((x, y, c))
                    self.t[y][x] = "#"
                elif c in "ShHzf":
                    self.items[(x, y)] = c
                    self.t[y][x] = "#"
                elif c in "ABCD":
                    self.gates[(x, y)] = [0.0, 0, c]
                elif c in "abcd":
                    self.plates[(x, y)] = c
                elif c == "e":
                    self.plates[(x, y)] = "e"
                    self.has_exit_plate = True
                elif c == "=":
                    self.loose[(x, y)] = [0, 0]
                elif c == "^":
                    self.spikes[(x, y)] = ["idle", 0, 0]
                elif c == "V":
                    self.chomp[(x, y)] = random.randrange(CHOMP_PERIOD)
                elif c == "E":
                    self.exit_pos = (x, y)
                elif c == "M":
                    self.mirror[(x, y)] = False
        self.exit_open = not self.has_exit_plate
        if self.exit_open:
            self.exit_k = 6.0
        self.pressed = set()
        self.var = {}
        for y in range(self.h):
            for x in range(self.w):
                self.var[(x, y)] = 3 if (x * 5 + y * 3 + n * 7) % 9 == 0 else (x + y * 2 + n) % 3
        self.shown = {}
        self.bloody = set()

    # ---- queries ----
    def kind(self, x, y):
        if x < 0 or x >= self.w:
            return "X"
        if y < 0 or y >= self.h:
            return "."
        return self.t[y][x]

    def has_floor(self, x, y):
        return self.kind(x, y) in FLOOR_CH

    def gate_at(self, x, y):
        return self.gates.get((x, y))

    def barrier(self, xa, xb, row, face):
        """Furthest x reachable moving from xa to xb along a row (body half width 6): walls and closed gates stop him."""
        if xb == xa:
            return xb
        if xb > xa:
            fa, fb = xa + 6, xb + 6
            for k in range(int(fa // TW), int(fb // TW) + 1):
                if k * TW > fa and self.kind(k, row) == "X":
                    return min(xb, k * TW - 6.01)
                g = self.gates.get((k, row))
                if g and g[0] < 6.5 and fa < k * TW + 16 <= fb:
                    return min(xb, k * TW + 16 - 6.01)
            return xb
        fa, fb = xa - 6, xb - 6
        for k in range(int(fa // TW), int(fb // TW) - 1, -1):
            if k * TW < fa and self.kind(k - 1, row) == "X" and fb <= k * TW:
                return max(xb, k * TW + 6.01)
            g = self.gates.get((k, row))
            if g and g[0] < 6.5 and fb <= k * TW + 16 < fa:
                return max(xb, k * TW + 16 + 6.01)
        return xb

    # ---- images ----
    def cell(self, x, y):
        c = self.t[y][x]
        v = self.var[(x, y)]
        s = "_%d" % v
        if c == ".":
            return ("pit" if y == self.h - 1 else "empty") + s, 0
        if c == "X":
            return "block" + s, 0
        if c == "#":
            it = self.items.get((x, y))
            if it:
                if it == "S":
                    return "sword" + s, (self.tick // 6) % 2
                return "potion_" + it + s, (self.tick // 9) % 2
            if (x, y) in self.rubble:
                return "rubble" + s, 0
            return "floor" + s, 0
        if c == "=":
            st = self.loose[(x, y)]
            return "loose" + s, (0 if st[0] == 0 else 1 + (self.tick // 2) % 2)
        if c == "^":
            lv = self.spikes[(x, y)][2]
            return "spikes" + s, lv
        if c == "P":
            return "pillar" + s, 0
        if c == "T":
            return "torch" + s, (self.tick // 3 + x * 2) % 6
        if c == "V":
            return "chomper" + s, self.chomp_img(x, y)
        if c in "ABCD":
            return "gate" + s, int(self.gates[(x, y)][0] + 0.5)
        if c in "abcde":
            return "plate" + s, 1 if (x, y) in self.pressed else 0
        if c == "E":
            return "exit" + s, int(self.exit_k + 0.5)
        if c == "M":
            return "mirror" + s, 1 if self.mirror[(x, y)] else 0
        return "floor" + s, 0

    def chomp_img(self, x, y):
        if (x, y) in self.bloody:
            return 5
        return chomp_state((self.tick + self.chomp[(x, y)]) % CHOMP_PERIOD)

    def chomp_deadly(self, x, y):
        ph = (self.tick + self.chomp[(x, y)]) % CHOMP_PERIOD
        return CHOMP_DEADLY[0] <= ph <= CHOMP_DEADLY[1]

    def tile_rows(self, x, y):
        name, st = self.cell(x, y)
        return TILES[self.theme][name][st]

    # ---- per tick dynamics ----
    def update(self, actors):
        self.tick += 1
        # plates
        now = set()
        for a in actors:
            if a.grounded() and not a.hidden:
                tx = int(a.x // TW)
                if (tx, a.row) in self.plates and abs(a.x - (tx * TW + 16)) <= 15:
                    now.add((tx, a.row))
        for p in now:
            if p not in self.pressed:
                letter = self.plates[p]
                if letter == "e":
                    self.exit_open = True
                else:
                    for gpos, g in self.gates.items():
                        if g[2] == letter.upper():
                            g[1] = GATE_OPEN_TICKS
        for p in now:
            letter = self.plates[p]
            if letter != "e":
                for g in self.gates.values():
                    if g[2] == letter.upper():
                        g[1] = max(g[1], GATE_OPEN_TICKS - 2)
        self.pressed = now
        for g in self.gates.values():
            if g[1] > 0:
                g[1] -= 1
                g[0] = min(8.0, g[0] + 1 / 3.0)
            else:
                g[0] = max(0.0, g[0] - 1 / 6.0)
        if self.exit_pos:
            if self.exit_open:
                self.exit_k = min(6.0, self.exit_k + 0.12)
        # spikes: wake when someone stands near, stay up a while, retract
        for pos, s in self.spikes.items():
            if s[0] == "idle":
                for a in actors:
                    if not a.hidden and a.alive_ok() and a.row == pos[1] and abs(a.x - (pos[0] * TW + 16)) < 52 and a.grounded():
                        s[0], s[1] = "up", 0
                        break
            elif s[0] == "up":
                s[1] += 1
                s[2] = min(3, 1 + s[1] // 3)
                if s[1] >= 12:
                    s[0], s[1] = "hold", 0
            elif s[0] == "hold":
                s[1] += 1
                if s[1] >= 40:
                    s[0], s[1] = "down", 0
            elif s[0] == "down":
                s[1] += 1
                s[2] = max(0, 3 - s[1] // 3)
                if s[1] >= 9:
                    s[0], s[1], s[2] = "idle", 0, 0
        # loose floor
        for pos in list(self.loose):
            st = self.loose[pos]
            if st[0] == 0:
                for a in actors:
                    if a.grounded() and not a.hidden and a.row == pos[1] and int(a.x // TW) == pos[0]:
                        st[0], st[1] = 1, 22
                        break
            else:
                st[1] -= 1
                if st[1] <= 0:
                    del self.loose[pos]
                    self.t[pos[1]][pos[0]] = "."
                    self.slabs.append(Slab(pos[0] * TW + 16, pos[1] * TH + SLAB_TOP))
        for sl in self.slabs:
            sl.vy = min(22.0, sl.vy + 1.1)
            old_bottom = sl.y + 13
            sl.y += sl.vy
            bottom = sl.y + 13
            tx = int(sl.x // TW)
            r = int((old_bottom - SLAB_TOP) // TH) + 1
            if bottom >= r * TH + SLAB_TOP + 3 and r < self.h and self.has_floor(tx, r):
                sl.alive = False
                if self.kind(tx, r) == "#" and (tx, r) not in self.items:
                    self.rubble.add((tx, r))
                if (tx, r) in self.loose:
                    self.loose[(tx, r)][0] = 1
                    self.loose[(tx, r)][1] = min(self.loose[(tx, r)][1] or 6, 6)
            elif sl.y > self.h * TH + 80:
                sl.alive = False
            else:
                for a in actors:
                    if a.alive_ok() and not a.hidden and abs(a.x - sl.x) < 14 and a.y - 50 < bottom and a.y > sl.y and not a.crushed_by(sl):
                        a.crush()
        self.slabs = [s for s in self.slabs if s.alive]


SLAB_TOP = 50

# ---------------------------------------------------------------------------------------------------------------
# Actors: the prince, guards, skeleton, shadow. One action-machine drives them all; the bot and the guard AI only
# press "keys" (direction, up, down, shift) like a human on a joystick.
# ---------------------------------------------------------------------------------------------------------------
GROUND_ST = {"stand", "start", "run", "stop", "turn", "runturn", "step", "pickup", "drink", "draw", "sheathe", "eg", "advance",
             "retreat", "strike", "parry", "hit", "land", "crouch", "sjump", "rjump"}
LOOP_LEN = {"run": 16, "eg": 14, "fall": 8, "hang": 2}
REACH = 46.0
_width_cache = {}


def spr_width(spr):
    k = id(spr)
    w = _width_cache.get(k)
    if w is None:
        w = 0
        for runs in spr[2]:
            for i in range(0, len(runs), 2):
                w = max(w, runs[i] + len(runs[i + 1]) // (2 * SC))
        _width_cache[k] = w
    return w


class Actor:
    def __init__(self, game, kind, pal, x, row, face):
        self.game = game
        self.world = game.world
        self.kind = kind
        self.pal = pal
        self.x, self.row, self.face = float(x), row, face
        self.y = row * TH + FEET
        self.ref_y = self.y
        self.st, self.seq, self.fi = "stand", "stand", 0
        self.dyoff = 0.0
        self.kdir, self.kup, self.kdown, self.kshift = 0, False, False, False
        self.act = None
        self.hp = self.maxhp = 3
        self.has_sword = False
        self.out = False
        self.speed = 1.0
        self.vy = self.vx = 0.0
        self.fall_row0 = row
        self.air = False
        self.hidden = False
        self.foe = None
        self.struck = False
        self.riposte = 0
        self.refract = 0
        self.blocked_once = False
        self.item = 0
        self.weightless = 0
        self.hang_row = row
        self.invuln = False
        self.vanish = 0
        self.crush_ids = set()
        self.carry = 1.0
        self.dead_tick = None
        self.grab = False
        self.kb_extra = 0.0
        self.stun = 0
        self.no_grab = 0

    # ---- helpers ----
    def alive_ok(self):
        return self.st not in ("dead", "dying")

    def grounded(self):
        return self.st in GROUND_ST and not self.air

    def tile(self):
        return int(self.x // TW)

    def start(self, st, seq, fi=-1):
        self.st, self.seq, self.fi = st, seq, fi

    def spr(self):
        return SPR[self.pal][self.seq]["R" if self.face > 0 else "L"][self.fi]

    def bbox(self):
        s = self.spr()
        x0 = int(round(self.x)) + s[0]
        y0 = int(round(self.y + self.dyoff)) + s[1]
        return x0, y0, x0 + spr_width(s), y0 + len(s[2])

    def keys(self, d=0, up=False, down=False, shift=False):
        self.kdir, self.kup, self.kdown, self.kshift = d, up, down, shift

    def crushed_by(self, sl):
        if id(sl) in self.crush_ids:
            return True
        self.crush_ids.add(id(sl))
        return False

    def crush(self):
        self.hurt(1, "crush")

    # ---- damage and death ----
    def hurt(self, n, how="sword"):
        if self.invuln or not self.alive_ok():
            return
        self.hp -= n
        if self.hp <= 0:
            self.hp = 0
            self.die(how)
        elif how == "sword":
            self.start("hit", "hit")
            self.refract = max(self.refract, getattr(self, "refract_len", 0))

    def die(self, how):
        self.hp = 0
        self.dead_tick = self.world.tick
        self.air = False
        self.dyoff = 0.0
        if how == "sword":
            self.start("dying", "die")
        elif how == "crush":
            self.start("dying", "die_fall")
        elif how == "spike":
            self.start("dead", "impaled", 0)
            self.dyoff = -3.0
        elif how == "chomp":
            self.start("dead", "dead_fwd", 0)
        else:
            self.start("dead", "dead_fwd", 0)
        self.game.on_death(self, how)

    # ---- falling / ledges ----
    def begin_fall(self):
        self.vx = self.face * min(2.4, self.carry)
        self.vy = 0.6
        self.fall_row0 = self.row
        self.air = False
        self.dyoff = 0.0
        self.start("fall", "fall")

    def try_grab(self):
        if self.no_grab > 0:
            self.no_grab -= 1
            return False
        if not self.kshift or self.st != "fall":
            return False
        w = self.world
        R = self.fall_row0
        if self.row != R and self.row != self.fall_row0:
            return False
        tx = self.tile()
        ahead = tx + self.face
        if w.has_floor(tx, R) or not w.has_floor(ahead, R) or w.kind(ahead, R) == "X":
            return False
        e = (tx + 1) * TW if self.face > 0 else tx * TW
        gap = (e - self.x) * self.face
        yl = R * TH + FEET
        if -2 <= gap <= 17 and yl + 44 <= self.y <= yl + 66:
            self.x = e - 7 * self.face
            self.y = yl + 2 + HANG_H
            self.row = R
            self.hang_row = R
            self.vy = self.vx = 0.0
            self.start("hang", "hang")
            return True
        return False

    def land(self, r):
        w = self.world
        self.row = r
        self.y = r * TH + FEET
        fell = r - self.fall_row0
        if self.weightless > 0:
            fell = 0
        self.dyoff = 0.0
        if w.kind(self.tile(), r) == "^":
            self.die("spike")
            return
        if self.kind != "prince":
            self.hp = 0
            self.die("crush")
            self.game.guard_fell(self)
            return
        if fell >= 3:
            self.die("crush")
        elif fell == 2:
            self.hurt(1, "fall")
            if self.alive_ok():
                self.start("land", "landhard")
        else:
            self.start("land", "landsoft")

    def update_fall(self):
        w = self.world
        grav, term = (0.12, 2.8) if self.weightless > 0 else (GRAVITY, TERMINAL)
        self.vy = min(term, self.vy + grav)
        y_old = self.y
        self.y += self.vy
        nx = self.x + self.vx
        d = 1 if self.vx >= 0 else -1
        self.x = w.barrier(self.x, nx, self.row, d) if self.vx else self.x
        if self.try_grab():
            return
        r_next = int((y_old - FEET) // TH) + 1
        if self.y >= r_next * TH + FEET:
            if r_next < w.h and w.has_floor(self.tile(), r_next):
                self.land(r_next)
                return
            self.row = min(r_next, w.h)
        if self.y > w.h * TH + 40:
            self.hidden = True
            self.die("abyss")

    # ---- decisions at action boundaries ----
    def ledge_ahead(self):
        w = self.world
        tx = self.tile()
        f = self.face
        e = (tx + 1) * TW if f > 0 else tx * TW
        return (w.has_floor(tx + f, self.row - 1) and not w.has_floor(tx, self.row - 1) and w.kind(tx + f, self.row - 1) != "X"
                and w.kind(tx, self.row - 1) != "X" and 3 <= (e - self.x) * f <= 22)

    def descent_ahead(self):
        w = self.world
        tx = self.tile()
        f = self.face
        e = (tx + 1) * TW if f > 0 else tx * TW
        if w.has_floor(tx + f, self.row) or w.kind(tx + f, self.row) == "X":
            return False
        return abs((e - self.x) * f - 8) <= 8 and (w.has_floor(tx + f, self.row + 1) or w.has_floor(tx + f, self.row + 2))

    def can_step(self, d, dist):
        w = self.world
        nx = self.x + d * dist
        if not w.has_floor(int(nx // TW), self.row):
            return False
        if w.barrier(self.x, nx, self.row, d) != nx:
            return False
        if self.foe is not None and self.foe.alive_ok() and self.foe.row == self.row:
            if d == self.face_to(self.foe) and abs(nx - self.foe.x) < 20:
                return False
        return True

    def face_to(self, o):
        return 1 if o.x > self.x else -1

    def decide(self):
        st = self.st
        if st == "stand":
            self.decide_stand()
        elif st == "run":
            if self.fi % 8 == 0 and self.fi >= 0:
                self.decide_run_contact()
        elif st == "eg":
            self.decide_eg()
        elif st == "hang":
            if self.kup:
                self.row = self.hang_row
                self.ref_y = self.hang_row * TH + FEET
                self.start("pullup", "pullup")
            elif self.kdown:
                self.vx = 0.0
                self.vy = 0.5
                self.no_grab = 20
                self.fall_row0 = self.hang_row
                self.start("fall", "fall")

    def decide_stand(self):
        a = self.act
        if a:
            self.act = None
            if a == "pickup":
                self.start("pickup", "pickup")
            elif a == "drink":
                self.start("drink", "drink%d" % self.item)
            elif a == "draw":
                self.start("draw", "draw")
            return
        d, up, dn, sh = self.kdir, self.kup, self.kdown, self.kshift
        if d and d != self.face:
            self.start("turn", "turn")
            return
        if d == self.face:
            if up:
                self.start("sjump", "standjump")
            elif sh:
                self.start("step", "step")
            else:
                self.start("start", "start")
            return
        if up and self.ledge_ahead():
            self.ref_y = self.y
            self.start("jumpup", "jumpup")
        elif dn and self.descent_ahead():
            self.ref_y = self.y
            self.start("climbdown", "climbdown")

    def decide_run_contact(self):
        d = self.kdir
        if self.kup:
            self.start("rjump", "runjump" if self.fi == 0 else "runjump_b")
            self.jump_b = self.fi != 0
        elif d == 0:
            self.start("stop", "stop" if self.fi == 0 else "stop_b")
        elif d != self.face:
            self.start("runturn", "runturn")

    def decide_eg(self):
        if self.act == "sheathe":
            self.act = None
            self.start("sheathe", "sheathe")
            return
        d = self.kdir
        if self.kshift and self.refract <= 0:
            self.struck = False
            self.start("strike", "strike")
        elif self.kup:
            self.start("parry", "parry")
        elif d and d == self.face and self.can_step(d, 12):
            self.start("advance", "advance")
        elif d and d == -self.face and self.can_step(d, 12):
            self.start("retreat", "retreat")

    # ---- sequence end ----
    def on_end(self):
        st = self.st
        w = self.world
        if st == "start":
            self.start("run", "run", 7)
        elif st == "rjump":
            self.start("run", "run", 0 if getattr(self, "jump_b", False) else 8)
            self.air = False
        elif st == "runturn":
            self.start("run", "run", 0)
        elif st == "sjump":
            self.air = False
            self.start("stand", "stand", -1)
        elif st in ("stop", "step", "turn", "land", "crouch"):
            self.start("stand", "stand", -1)
        elif st == "jumpup":
            self.row -= 1
            self.hang_row = self.row
            self.y = self.row * TH + FEET + 2 + HANG_H
            self.dyoff = 0.0
            self.start("hang", "hang")
        elif st == "pullup":
            self.y = self.row * TH + FEET
            self.dyoff = 0.0
            self.start("stand", "stand", -1)
        elif st == "climbdown":
            self.hang_row = self.row
            self.y = self.ref_y + 2 + HANG_H
            self.dyoff = 0.0
            self.start("hang", "hang")
        elif st == "pickup":
            self.has_sword = True
            w.items.pop((self.tile(), self.row), None)
            self.game.on_item(self, "S")
            self.start("stand", "stand", -1)
        elif st == "drink":
            self.finish_drink()
            self.start("stand", "stand", -1)
        elif st == "draw":
            self.out = True
            self.start("eg", "eg", -1)
        elif st == "sheathe":
            self.out = False
            self.start("stand", "stand", -1)
        elif st in ("advance", "retreat", "strike", "parry"):
            self.start("eg", "eg", -1)
        elif st == "hit":
            self.start("eg", "eg", -1)
        elif st == "dying":
            self.st = "dead"
            self.fi = META[self.seq]["n"] - 1
        else:
            self.start("stand", "stand", -1)

    def finish_drink(self):
        w = self.world
        key = (self.tile(), self.row)
        it = w.items.pop(key, None)
        if not it:
            return
        if it == "h":
            self.hp = min(self.maxhp, self.hp + 1)
        elif it == "H":
            self.maxhp += 1
            self.hp = self.maxhp
        elif it == "z":
            self.hurt(1, "poison")
        elif it == "f":
            self.weightless = 450
        self.game.on_item(self, it)

    # ---- per tick ----
    def tick(self):
        if self.st == "dead":
            return
        w = self.world
        if self.weightless > 0:
            self.weightless -= 1
        if self.st == "fall":
            self.fi = (self.fi + 1) % 8
            self.update_fall()
            return
        self.decide()
        m = META[self.seq]
        n = m["n"]
        self.fi += 1
        if self.fi >= n:
            if self.seq in LOOP_LEN and self.st in ("run", "eg", "hang", "fall"):
                self.fi = 0 if self.seq != "run" else self.fi % 16
            else:
                self.on_end()
                if self.st == "dead":
                    return
                m = META[self.seq]
                self.fi += 1
                if self.fi >= m["n"]:
                    self.fi = 0
        if self.st == "fall":
            return
        ev = m["ev"]
        dx = m["dx"][self.fi]
        if self.st in ("start", "run"):
            dx *= self.speed
        if dx:
            tgt = self.x + self.face * dx
            d = 1 if tgt > self.x else -1
            nx = w.barrier(self.x, tgt, self.row, d)
            if nx != tgt and self.st in ("run", "start", "rjump"):
                self.x = nx
                if self.st in ("run", "start"):
                    self.start("stand", "stand", 0)
                    self.dyoff = 0.0
                    return
            self.x = nx
            self.carry = abs(dx) if dx * 1 else self.carry
        self.dyoff = m["dy"][self.fi] if self.st in ("sjump", "rjump", "jumpup", "pullup", "climbdown") else 0.0
        if "flip" in ev and self.fi == ev["flip"]:
            self.face = -self.face
        if "takeoff" in ev:
            if self.fi == ev["takeoff"] + 1:
                self.air = True
            if self.fi == ev["land"]:
                self.air = False
        # support and hazards
        if self.grounded():
            tx = self.tile()
            if not w.has_floor(tx, self.row):
                self.begin_fall()
                return
            self.hazards(tx)

    def hazards(self, tx):
        w = self.world
        pos = (tx, self.row)
        c = w.kind(tx, self.row)
        cx = tx * TW + 16
        if c == "^":
            s = w.spikes[pos]
            if s[2] >= 1 and abs(self.x - cx) < 13:
                self.die("spike")
        elif c == "V":
            if abs(self.x - cx) < 9 and w.chomp_deadly(tx, self.row) and self.dyoff > -7:
                w.bloody.add(pos)
                self.die("chomp")

# ---------------------------------------------------------------------------------------------------------------
# Route planner: Dijkstra over standing positions with gate timers, broken loose floors and the exit-plate flag in the
# state. Moves are the ones the prince can actually perform (run, jump, climb), with the distances the animation
# tables dictate, so executing a plan reproduces what was planned.
# ---------------------------------------------------------------------------------------------------------------
import heapq

def _sum(name, upto):
    return sum(META[name]["dx"][:upto + 1])


SJ_D = _sum("standjump", META["standjump"]["ev"]["land"])           # distance from jump start to touch down
RJ_D = _sum("runjump", META["runjump"]["ev"]["land"])
RJ_END = sum(META["runjump"]["dx"])
START_D = sum(META["start"]["dx"])
STOP_D = sum(META["stop"]["dx"])
STEP_D = sum(META["step"]["dx"])
CYCLE_D = sum(META["run"]["dx"][:8])
WALK_COST = 11
STANDABLE_BAD = set("XV^ABCD")


class Move:
    __slots__ = ("kind", "d", "src", "dst", "cost", "info")

    def __init__(self, kind, d, src, dst, cost, info=None):
        self.kind, self.d, self.src, self.dst, self.cost, self.info = kind, d, src, dst, cost, info


class Planner:
    def __init__(self, world):
        self.w = world
        self.letters = sorted(set(g[2] for g in world.gates.values()))

    def standable(self, x, y, broken):
        w = self.w
        if (x, y) in broken:
            return False
        c = w.kind(x, y)
        return c in FLOOR_CH and c not in STANDABLE_BAD

    def runway_ok(self, x, y, broken, d, from_x, to_x):
        """Tiles from from_x..to_x (inclusive, stepping by d) must be hazard-free flat floor."""
        w = self.w
        k = from_x
        while True:
            if (k, y) in broken or w.kind(k, y) not in RUNWAY_CH:
                return False
            if k == to_x:
                return True
            k += d

    def rj_geometry(self, g):
        """Offsets (relative to the far edge e of the takeoff tile, along the jump direction) for a g-tile gap."""
        landing = 32 * g + 8
        x_contact = landing - RJ_D
        x_start = x_contact - START_D - 0.0
        return landing, x_contact, x_start

    def moves(self, node, rem, broken, exo):
        w = self.w
        x, y = node
        out = []
        loose_here = w.kind(x, y) == "="
        for d in (1, -1):
            e = (x + 1) * TW if d > 0 else x * TW
            # walk / cross hazards
            k = x + d
            cross = []
            while w.kind(k, y) in PASS_CH and (k, y) not in broken:
                cross.append(k)
                k += d
            dest = (k, y)
            if w.kind(k, y) != "X" and self.standable(k, y, broken) and not (w.kind(k, y) == "E" and not (exo or w.exit_open)):
                ok = True
                t_acc = WALK_COST
                extra = 0
                rem2 = list(rem)
                for ck in cross:
                    c = w.kind(ck, y)
                    t_acc += WALK_COST
                    if c in "ABCD":
                        i = self.letters.index(c)
                        r = rem[i] - t_acc
                        if r < 25:
                            ok = False
                            break
                    else:
                        extra += 30
                if ok:
                    cost = WALK_COST * (1 + len(cross)) + extra
                    out.append(("walk", d, dest, cost, cross))
            # standing jump over one tile
            if not loose_here:
                k1, k2 = x + d, x + 2 * d
                if w.kind(k1, y) not in "XABCD" and w.kind(k2, y) != "X" and self.standable(k2, y, broken):
                    if not (w.kind(k2, y) == "E" and not (exo or w.exit_open)):
                        if not (w.kind(k1, y) in FLOOR_CH and w.kind(k1, y) not in "^V=" and (k1, y) not in broken):
                            out.append(("sjump", d, (k2, y), 55, None))
                # running jumps over g tiles
                for g in (1, 2, 3):
                    ks = [x + d * i for i in range(1, g + 1)]
                    if any(w.kind(kk, y) in "XABCD" for kk in ks):
                        continue
                    land = (x + d * (g + 1), y)
                    if not self.standable(land[0], land[1], broken):
                        continue
                    if w.kind(land[0], y) == "E" and not (exo or w.exit_open):
                        continue
                    landing, xc, xs = self.rj_geometry(g)
                    run_tiles = int(math.ceil((-xs) / TW)) + 1 if xs < 0 else 1
                    far = x - d * (run_tiles - 1)
                    if not self.runway_ok(x, y, broken, d, far, x) and run_tiles > 1:
                        # shorter run-up is acceptable when the tiles that are there are enough for the start
                        continue
                    if g == 1 and all(w.has_floor(kk, y) and (kk, y) not in broken for kk in ks):
                        continue
                    out.append(("rjump", d, land, 75 + 6 * g, g))
            # climb up
            if not loose_here:
                if (w.has_floor(x + d, y - 1) and not w.has_floor(x, y - 1) and w.kind(x + d, y - 1) != "X" and w.kind(x, y - 1) != "X"
                        and self.standable(x + d, y - 1, broken) and y - 1 >= 0):
                    out.append(("climbup", d, (x + d, y - 1), 85, None))
                # climb down
                if (not w.has_floor(x + d, y) and w.kind(x + d, y) != "X" and y + 1 < w.h and self.standable(x + d, y + 1, broken)
                        and w.kind(x + d, y + 1) not in "E"):
                    out.append(("climbdown", d, (x + d, y + 1), 95, None))
        return out

    def search(self, start, goal_fn, rem0, broken0, exo0, budget=None):
        """Generator: yields None while searching, then yields the move list (or False when unreachable)."""
        w = self.w
        heap = [(0, 0, start, tuple(rem0), frozenset(broken0), exo0)]
        parent = {}
        seen = {}
        cnt = 0
        key0 = (start, tuple(r // 30 for r in rem0), frozenset(broken0), exo0)
        seen[key0] = 0
        parent[key0] = None
        n = 0
        while heap:
            cost, _, node, rem, broken, exo = heapq.heappop(heap)
            key = (node, tuple(r // 30 for r in rem), broken, exo)
            if seen.get(key, 1e9) < cost:
                continue
            if goal_fn(node, exo):
                moves = []
                k = key
                while parent[k] is not None:
                    pk, mv = parent[k]
                    moves.append(mv)
                    k = pk
                moves.reverse()
                yield (moves, rem, broken, exo)
                return
            n += 1
            if n % 400 == 0:
                yield None
            for kind, d, dst, c, info in self.moves(node, rem, broken, exo):
                rem2 = tuple(max(0, r - c) for r in rem)
                b2 = broken
                exo2 = exo
                dk = w.kind(dst[0], dst[1])
                if dk == "=" :
                    b2 = broken | {dst}
                if dk in "abcd":
                    i = self.letters.index(dk.upper()) if dk.upper() in self.letters else None
                    if i is not None:
                        rem2 = tuple(300 if j == i else rem2[j] for j in range(len(rem2)))
                if dk == "e":
                    exo2 = True
                nc = cost + c
                k2 = (dst, tuple(r // 30 for r in rem2), b2, exo2)
                if seen.get(k2, 1e9) <= nc:
                    continue
                seen[k2] = nc
                parent[k2] = (key, Move(kind, d, node, dst, c, info))
                cnt += 1
                heapq.heappush(heap, (nc, cnt, dst, rem2, b2, exo2))
        yield False

# ---------------------------------------------------------------------------------------------------------------
# The bot: turns a planned move list into key presses with feedback from the actor's real position
# ---------------------------------------------------------------------------------------------------------------
ITEM_CODE = {"h": 1, "H": 1, "z": 2, "f": 3}


def est_ticks(dist):
    if dist <= START_D:
        return dist / 1.6
    return 9 + (dist - START_D) / 3.6


class Bot:
    def __init__(self, game):
        self.g = game
        self.reset()

    def reset(self):
        self.gen = None
        self.moves = []
        self.mi = 0
        self.chain = []
        self.state = None
        self.target = None
        self.phase = 0
        self.timeout = 0
        self.fail = 0
        self.parried = False
        self.err = 0.0
        self.grab_flag = False
        self.progress_tick = 0
        self.replans = 0
        self.fight_cool = 0
        self.act_pending = None
        self.holding = False
        self.hold_t = 0
        self.after_fight = False
        self.planning = False
        self.mandatory_fail = False

    # ---- planning ----
    def want_chain(self, p):
        w = self.g.world
        chain = []
        px = p.tile()
        if not p.has_sword:
            sw = [pos for pos, it in w.items.items() if it == "S"]
            sw.sort(key=lambda q: abs(q[0] - px))
            chain += sw[:1]
        hs = [pos for pos, it in w.items.items() if it == "H"]
        hs.sort(key=lambda q: abs(q[0] - px))
        chain += [q for q in hs if abs(q[0] - px) < 14]
        if p.hp < p.maxhp:
            small = [pos for pos, it in w.items.items() if it == "h" and abs(pos[0] - px) < 7]
            small.sort(key=lambda q: abs(q[0] - px))
            chain += small[:1]
        if not w.exit_open:
            for pos, letter in w.plates.items():
                if letter == "e":
                    chain.append(pos)
        chain.append(w.exit_pos)
        return chain

    def start_plan(self, p):
        w = self.g.world
        self.planner = Planner(w)
        self.chain = self.want_chain(p)
        rem = [max([gt[1] for gt in w.gates.values() if gt[2] == L] or [0]) for L in self.planner.letters]
        self.state = ((p.tile(), p.row), tuple(rem), frozenset(), w.exit_open)
        self.moves, self.mi = [], 0
        self.chain_i = 0
        self.gen = None
        self.planning = True
        self.mandatory_fail = False

    def plan_step(self, p):
        """Advance the incremental search; returns True while still planning."""
        w = self.g.world
        if not self.planning:
            return False
        for _ in range(3):
            if self.gen is None:
                if self.chain_i >= len(self.chain):
                    self.planning = False
                    return False
                goal = self.chain[self.chain_i]
                node, rem, broken, exo = self.state
                self.gen = self.planner.search(node, lambda n, e, goal=goal: n == goal, rem, broken, exo)
            res = next(self.gen)
            if res is None:
                return True
            self.gen = None
            if res is False:
                if self.chain_i == len(self.chain) - 1 or w.items.get(self.chain[self.chain_i]) is None:
                    self.mandatory_fail = True
                    self.planning = False
                    self.moves = []
                    return False
                self.chain_i += 1
                continue
            mv, rem, broken, exo = res
            self.moves += [(m, self.chain[self.chain_i]) for m in mv]
            last = self.chain[self.chain_i]
            self.state = (last, rem, broken, exo)
            self.chain_i += 1
            if self.chain_i >= len(self.chain):
                self.planning = False
                return False
        return True

    # ---- geometry of preparing a move ----
    def prep(self, mv):
        sx, sy = mv.src
        d = mv.d
        e = (sx + 1) * TW if d > 0 else sx * TW
        k = mv.kind
        if k == "sjump":
            return e + d * (48 - SJ_D)
        if k == "rjump":
            g = mv.info
            landing = 32 * g + 8
            return e + d * (landing - RJ_D - START_D)
        if k == "climbup":
            return e - 17 * d
        if k == "climbdown":
            return e - 8 * d
        return None

    def center(self, tile):
        return tile[0] * TW + 16

    # ---- low level motion ----
    def goto(self, p, xt, face):
        dxs = xt - p.x
        sgn = 1 if dxs > 0 else -1
        dist = abs(dxs)
        if p.st in ("start", "run"):
            stop = False
            if p.st == "run" and p.fi % 8 == 0:
                stop = dist - CYCLE_D - STOP_D < 0 or (sgn != p.face)
            p.keys(0 if stop else p.face)
            return False
        if p.st != "stand":
            p.keys()
            return False
        if dist <= 3.3 and p.face == face:
            p.keys()
            return True
        if dist <= 3.3:
            p.keys(face)
            return False
        if p.face != sgn:
            p.keys(sgn)
            return False
        if dist >= START_D + STOP_D + 10:
            p.keys(sgn)
        else:
            p.keys(sgn, shift=True)
        return False

    def tile_of(self, p):
        return (p.tile(), p.row)

    # ---- executing the plan ----
    def next_move(self):
        return self.moves[self.mi][0] if self.mi < len(self.moves) else None

    def run(self, p):
        """Called every tick with the prince; sets his keys."""
        g = self.g
        w = g.world
        p.keys()
        if not p.alive_ok():
            return
        if self.fight(p):
            return
        if p.st == "fall":
            p.kshift = self.grab_flag
            return
        if self.holding:
            self.hold_t += 1
            if self.hold_t > 3 and p.st == "stand" and p.act is None:
                self.holding = False
            return
        if self.planning:
            self.plan_step(p)
            return
        if self.mi >= len(self.moves):
            if self.mandatory_fail:
                self.stuck(p)
            return
        mv, goal = self.moves[self.mi]
        cur = self.tile_of(p)
        if self.phase == 0:
            # validate the starting node, then decide how to prepare
            if p.st == "stand" and (p.row != mv.src[1] or abs(p.x - self.center(mv.src)) > 80):
                self.replan(p)
                return
            self.phase = 1
            self.timeout = 0
            self.err = 0.0
            self.grab_flag = random.random() < 0.55
            if mv.kind == "rjump" and mv.info >= 2 and random.random() < 0.06:
                self.err = random.uniform(15, 25)
            elif mv.kind == "sjump" and random.random() < 0.035:
                self.err = random.uniform(18, 26)
        self.timeout += 1
        if self.timeout > 900:
            self.replan(p)
            return
        k = mv.kind
        d = mv.d
        if k == "walk":
            self.exec_walk(p)
        elif k in ("sjump", "rjump"):
            self.exec_jump(p, mv)
        elif k == "climbup":
            self.exec_climb(p, mv, True)
        elif k == "climbdown":
            self.exec_climb(p, mv, False)

    def advance(self, p):
        goal = self.moves[self.mi][1]
        self.mi += 1
        self.phase = 0
        self.progress_tick = self.g.clock
        if self.mi >= len(self.moves) or self.moves[self.mi][1] != goal:
            self.arrive(p)

    def arrive(self, p):
        """End of the plan: act on the item at the final tile."""
        w = self.g.world
        it = w.items.get((p.tile(), p.row))
        if it == "S":
            p.act = "pickup"
        elif it in ITEM_CODE and it != "z":
            p.item = ITEM_CODE[it]
            p.act = "drink"
        self.holding = p.act is not None
        self.hold_t = 0

    def exec_walk(self, p):
        mv, goal = self.moves[self.mi]
        w = self.g.world
        # merge consecutive plain walks in the same direction
        j = self.mi
        last = mv
        while j + 1 < len(self.moves) and self.moves[j + 1][0].kind == "walk" and self.moves[j + 1][0].d == mv.d and not self.moves[j + 1][0].info:
            j += 1
            last = self.moves[j][0]
        nxt = self.moves[j + 1][0] if j + 1 < len(self.moves) else None
        xt = self.center(last.dst)
        pp = self.prep(nxt) if nxt is not None and nxt.src == last.dst else None
        if pp is not None:
            xt = pp
        if mv.info:
            # hazards ahead: wait for a safe moment while standing
            if p.st == "stand" and self.hazard_wait(p, mv):
                p.keys()
                return
        if p.st in ("fall", "hang"):
            return
        arrived = self.goto(p, xt, mv.d if (pp is not None) else p.face if abs(xt - p.x) <= 3.3 else mv.d)
        if arrived or (p.st == "stand" and (p.tile(), p.row) == last.dst and abs(p.x - xt) < 6):
            self.mi = j
            self.advance(p)
            return
        if p.st == "stand" and p.row != mv.dst[1]:
            self.replan(p)

    def hazard_wait(self, p, mv):
        w = self.g.world
        for ck in mv.info:
            c = w.kind(ck, mv.src[1])
            cx = ck * TW + 16
            if c == "V":
                dist = abs(cx - p.x)
                t = est_ticks(dist)
                for k in range(int(t) - 4, int(t) + 8):
                    ph = (w.tick + w.chomp[(ck, mv.src[1])] + k) % CHOMP_PERIOD
                    if 56 <= ph <= 82:
                        return True
            elif c in "ABCD":
                gt = w.gates[(ck, mv.src[1])]
                if gt[1] <= 0 and gt[0] < 6.5:
                    self.replan(p)
                    return True
                if gt[0] < 7.0:
                    return True
        return False

    def exec_jump(self, p, mv):
        d = mv.d
        xp = self.prep(mv) - d * self.err
        if self.phase == 1:
            if p.st in ("fall",):
                self.phase = 3
                return
            ok = self.goto(p, xp, d)
            if ok:
                self.phase = 2
            return
        if self.phase == 2:
            if p.st == "stand":
                if mv.kind == "sjump":
                    p.keys(d, up=True, shift=self.grab_flag)
                    self.phase = 3
                else:
                    p.keys(d)
                    self.phase = 3
                    self.run_started = True
            return
        if self.phase == 3:
            if mv.kind == "rjump":
                if p.st in ("start", "run"):
                    contact = p.st == "run" and p.fi % 8 == 0
                    if contact:
                        p.keys(d, up=True, shift=self.grab_flag)
                        self.phase = 4
                    else:
                        p.keys(d)
                    return
                if p.st == "stand":
                    self.phase = 2
                    return
            else:
                self.phase = 4
            if p.st in ("sjump", "rjump"):
                p.kshift = self.grab_flag
        if self.phase == 4:
            p.kshift = self.grab_flag and p.st in ("sjump", "rjump", "fall")
            p.keys(0, shift=p.kshift)
            if p.st == "run":
                # landed still running: stop at the next contact
                p.keys(0)
            if p.st == "stand":
                if (p.tile(), p.row) == mv.dst:
                    self.advance(p)
                else:
                    self.replan(p)

    def exec_climb(self, p, mv, up):
        d = mv.d
        xp = self.prep(mv)
        if self.phase == 1:
            if self.goto(p, xp, d):
                self.phase = 2
            return
        if self.phase == 2:
            if p.st == "stand":
                p.keys(0, up=up, down=not up)
                self.phase = 3
            return
        if self.phase == 3:
            if p.st == "hang":
                p.keys(0, up=up, down=not up)
            elif p.st == "stand" and (p.tile(), p.row) == mv.dst:
                self.advance(p)
            elif p.st == "stand" and p.row != mv.src[1] and (p.tile(), p.row) != mv.dst:
                self.replan(p)
            elif p.st == "stand" and p.row == mv.src[1] and self.timeout > 120:
                self.replan(p)

    def replan(self, p):
        self.replans += 1
        self.phase = 0
        if p.st == "stand":
            self.start_plan(p)
        else:
            self.moves, self.mi = [], 0
            self.planning = False
            self.mandatory_fail = False
            self.pending_replan = True

    def stuck(self, p):
        self.fail += 1
        p.keys()
        if self.fail % 90 == 1 and p.st == "stand":
            self.start_plan(p)

    # ---- fighting ----
    def fight(self, p):
        """Returns True while the prince is busy with a duel (the route executor must then keep its hands off)."""
        g = self.g
        if p.st in ("fall", "hang", "jumpup", "pullup", "climbdown", "sjump", "rjump", "dying", "dead"):
            return False
        foes = [q for q in g.guards if q.alive_ok() and q.row == p.row and q.alerted and q.kind == "guard" and not q.hidden]
        foe = min(foes, key=lambda q: abs(q.x - p.x)) if foes else None
        if foe is None or abs(foe.x - p.x) > 200 or not p.has_sword:
            if p.out and p.st == "eg":
                p.act = "sheathe"
                self.after_fight = True
                return True
            if p.st in ("sheathe",):
                return True
            if self.after_fight and p.st == "stand":
                self.after_fight = False
                self.start_plan(p)
            return False
        p.foe = foe
        d = abs(foe.x - p.x)
        self.after_fight = True
        if not p.out:
            if p.st in ("start", "run"):
                p.keys(0)
            elif p.st == "stand":
                if (foe.x - p.x) * p.face < 0:
                    p.keys(1 if foe.x > p.x else -1)
                else:
                    p.act = "draw"
            return True
        if p.st != "eg":
            return True
        p.face = 1 if foe.x > p.x else -1
        self.duel(p, foe, d)
        return True

    def duel(self, p, f, d):
        skill = 0.9 if not f.invuln else 0.85
        if f.st == "strike" and f.fi in (1, 2, 3) and d <= 62 and not self.parried:
            self.parried = True
            if random.random() < skill:
                p.keys(up=True)
                return
        if f.st != "strike":
            self.parried = False
        if p.riposte > 0:
            p.riposte = 0
            p.keys(shift=True)
            return
        if f.st in ("hit", "dying") and d <= REACH - 4:
            p.keys(shift=True)
            return
        if p.hp <= 1 and f.hp >= 2 and d < 62 and random.random() < 0.25:
            p.keys(-p.face)
            return
        if d > REACH - 4:
            p.keys(p.face)
        elif d < 26:
            p.keys(-p.face)
        elif f.st == "strike":
            return
        elif random.random() < (0.16 if f.refract > 0 else 0.3 if f.invuln else 0.07):
            p.keys(shift=True)


# ---------------------------------------------------------------------------------------------------------------
# Rendering: per-screen background rows (5x horizontally expanded, so one logical row is written to five scanlines),
# dirty rectangles for traps, and sprite runs composited over the restored background.
# ---------------------------------------------------------------------------------------------------------------
ROWBYTES = LW * SC * 2
DYNAMIC = set("TV=^ABCDabcdEeM")


class Renderer:
    def __init__(self, game):
        self.g = game
        self.cur = None
        self.bg = None
        self.records = {}
        self.dirty = []
        self.shown = {}
        self.hud_cache = None

    # ---- screen ----
    def enter(self, sx, sy):
        w = self.g.world
        self.cur = (sx, sy)
        self.bg = [None] * LH
        self.shown = {}
        self.records = {}
        self.dirty = []
        gx0, gy0 = sx * SCR_W, sy * SCR_H
        for ty in range(SCR_H):
            tiles_rows = []
            for tx in range(SCR_W):
                gx, gy = gx0 + tx, gy0 + ty
                if 0 <= gx < w.w and 0 <= gy < w.h:
                    name, st = w.cell(gx, gy)
                    tiles_rows.append(TILES[w.theme][name][st])
                    self.shown[(gx, gy)] = (name, st)
                else:
                    tiles_rows.append(TILES[w.theme]["empty_0"][0])
            for ly in range(TH):
                self.bg[ty * TH + ly] = bytearray(b"".join(r[ly] for r in tiles_rows))
        self.dyn = [(gx0 + tx, gy0 + ty) for ty in range(SCR_H) for tx in range(SCR_W)
                    if 0 <= gx0 + tx < w.w and 0 <= gy0 + ty < w.h and w.t[gy0 + ty][gx0 + tx] in DYNAMIC
                    or (0 <= gx0 + tx < w.w and 0 <= gy0 + ty < w.h and (gx0 + tx, gy0 + ty) in w.items)]
        self.blit_full()

    def blit_full(self):
        for ly in range(LH):
            row = self.bg[ly]
            base = ly * SC * S + OX * 2
            for k in range(SC):
                fb[base + k * S: base + k * S + ROWBYTES] = row

    def update_tiles(self):
        w = self.g.world
        sx, sy = self.cur
        gx0, gy0 = sx * SCR_W, sy * SCR_H
        for (gx, gy) in self.dyn:
            name, st = w.cell(gx, gy)
            if self.shown.get((gx, gy)) == (name, st):
                continue
            self.shown[(gx, gy)] = (name, st)
            rows = TILES[w.theme][name][st]
            tx, ty = gx - gx0, gy - gy0
            r0, r1 = (4, 40) if name.startswith("torch") else (0, TH)
            if name.startswith("potion") or name.startswith("sword"):
                r0, r1 = 30, TH
            b0 = tx * TW * SC * 2
            n = TW * SC * 2
            for ly in range(r0, r1):
                self.bg[ty * TH + ly][b0:b0 + n] = rows[ly]
            self.dirty.append((tx * TW, ty * TH + r0, tx * TW + TW, ty * TH + r1))

    # ---- objects ----
    def objects(self):
        g = self.g
        sx, sy = self.cur
        ox0, oy0 = sx * LW, sy * LH
        out = []
        for sl in g.world.slabs:
            s = MISC["slab_" + g.world.theme]
            out.append((("slab", id(sl)), s, int(sl.x) + s[0] - ox0, int(sl.y) - oy0))
        for a in g.guards:
            if not a.hidden and not (a.st == "dead" and a.vanish):
                s = a.spr()
                x0 = int(round(a.x)) + s[0] - ox0
                y0 = int(round(a.y + a.dyoff)) + s[1] - oy0
                out.append((("a", id(a)), s, x0, y0))
        p = g.prince
        if not p.hidden:
            s = p.spr()
            out.append((("a", id(p)), s, int(round(p.x)) + s[0] - ox0, int(round(p.y + p.dyoff)) + s[1] - oy0))
        res = []
        for key, s, x0, y0 in out:
            w = spr_width(s)
            if x0 + w <= 0 or x0 >= LW or y0 + len(s[2]) <= 0 or y0 >= LH:
                continue
            res.append((key, s, x0, y0, w))
        return res

    def render(self):
        objs = self.objects()
        self.update_tiles()
        dirty = self.dirty
        self.dirty = []
        seen = set()
        for key, s, x0, y0, w in objs:
            seen.add(key)
            sig = (id(s), x0, y0)
            rec = self.records.get(key)
            if rec is None or rec[0] != sig:
                if rec is not None:
                    dirty.append(rec[1])
                dirty.append((x0, y0, x0 + w, y0 + len(s[2])))
                self.records[key] = (sig, (x0, y0, x0 + w, y0 + len(s[2])))
        for key in list(self.records):
            if key not in seen:
                dirty.append(self.records.pop(key)[1])
        if not dirty:
            return
        boxes = [(max(0, a), max(0, b), min(LW, c), min(LH, d)) for a, b, c, d in dirty]
        boxes = [b for b in boxes if b[2] > b[0] and b[3] > b[1]]
        # grow to cover every sprite that touches a dirty box, then merge overlapping boxes
        changed = True
        while changed:
            changed = False
            for key, s, x0, y0, w in objs:
                ob = (x0, y0, x0 + w, y0 + len(s[2]))
                for i, b in enumerate(boxes):
                    if ob[0] < b[2] and ob[2] > b[0] and ob[1] < b[3] and ob[3] > b[1]:
                        nb = (max(0, min(b[0], ob[0])), max(0, min(b[1], ob[1])), min(LW, max(b[2], ob[2])), min(LH, max(b[3], ob[3])))
                        if nb != b:
                            boxes[i] = nb
                            changed = True
            merged = []
            for b in boxes:
                for i, m in enumerate(merged):
                    if b[0] < m[2] and b[2] > m[0] and b[1] < m[3] and b[3] > m[1]:
                        merged[i] = (min(b[0], m[0]), min(b[1], m[1]), max(b[2], m[2]), max(b[3], m[3]))
                        changed = True
                        break
                else:
                    merged.append(b)
            if len(merged) != len(boxes):
                changed = True
            boxes = merged
        for b in boxes:
            self.paint(b, objs)

    def paint(self, box, objs):
        x0, y0, x1, y1 = box
        b0, b1 = x0 * SC * 2, x1 * SC * 2
        cols = [o for o in objs if o[2] < x1 and o[2] + o[4] > x0 and o[3] < y1 and o[3] + len(o[1][2]) > y0]
        for ly in range(y0, y1):
            row = self.bg[ly][b0:b1]
            for key, s, ox, oy, w in cols:
                r = ly - oy
                if 0 <= r < len(s[2]):
                    runs = s[2][r]
                    for i in range(0, len(runs), 2):
                        xs = ox + runs[i]
                        data = runs[i + 1]
                        n = len(data) // (SC * 2)
                        if xs >= x1 or xs + n <= x0:
                            continue
                        lo = xs * SC * 2 - b0
                        if lo < 0:
                            data = data[-lo:]
                            lo = 0
                        hi = lo + len(data)
                        if hi > b1 - b0:
                            data = data[:b1 - b0 - lo]
                            hi = b1 - b0
                        row[lo:hi] = data
            base = ly * SC * S + OX * 2 + b0
            ln = len(row)
            for k in range(SC):
                fb[base + k * S: base + k * S + ln] = row

    # ---- HUD ----
    def hud(self, force=False):
        g = self.g
        p = g.prince
        foe = g.current_foe()
        mins = g.minutes_left()
        state = (p.hp, p.maxhp, foe.hp if foe else -1, foe.maxhp if foe else -1, g.n, g.score, mins)
        if not force and state == self.hud_cache:
            return
        old = self.hud_cache
        self.hud_cache = state
        if force or old is None:
            fill_rect(0, HUD_Y, W, H - HUD_Y, 0)
            fill_rect(0, HUD_Y, W, 4, rgb565(90, 90, 110))
        if force or old is None or old[:2] != state[:2]:
            fill_rect(OX, HUD_Y + 60, 8 * 40, 36, 0)
            for i in range(p.maxhp):
                blit(HUD["kid_full" if i < p.hp else "kid_empty"], OX + 10 + i * 40, HUD_Y + 62)
        if force or old is None or old[2:4] != state[2:4]:
            fill_rect(W - OX - 8 * 40 - 10, HUD_Y + 60, 8 * 40 + 10, 36, 0)
            if foe is not None:
                for i in range(foe.maxhp):
                    blit(HUD["opp_full" if i < foe.hp else "opp_empty"], W - OX - 10 - (i + 1) * 40, HUD_Y + 62)
        if force or old is None or old[4:6] != state[4:6]:
            txt = "LEVEL %d   SCORE %d" % (g.n, g.score)
            fill_rect(OX + 340, HUD_Y + 14, 920, 40, 0)
            draw_text_centered(txt, HUD_Y + 14, "S", COLOR_YELLOW)
        if force or old is None or old[6] != state[6]:
            txt = "%d MINUTES LEFT" % mins if mins != 1 else "1 MINUTE LEFT"
            fill_rect(OX + 340, HUD_Y + 74, 920, 40, 0)
            draw_text_centered(txt, HUD_Y + 74, "S", COLOR_WHITE if mins > 5 else COLOR_RED)

# ---------------------------------------------------------------------------------------------------------------
# The game: levels, guards, events, scoring, clock
# ---------------------------------------------------------------------------------------------------------------
TICKS_PER_GAME_MINUTE = 200
SCORE_TARGET = 12000
GUARD_HP = [3, 3, 4, 3, 4, 4, 5, 4, 5, 5, 5, 4]


def guard_params(n, glyph):
    lv = max(1, min(12, n))
    p = dict(hp=GUARD_HP[lv - 1], block=0.08 + 0.04 * lv, strike=0.028 + 0.0042 * lv, adv=0.16 + 0.01 * lv,
             restrike=0.08 + 0.03 * lv, refract=max(8, 26 - 2 * lv), pal="gblue" if lv % 3 else "gred", invuln=False)
    if glyph == "3":
        p.update(hp=p["hp"] + 2, pal="gfat", strike=p["strike"] * 0.8, adv=p["adv"] * 0.7, block=p["block"] * 0.8)
    elif glyph == "4":
        p.update(hp=99, pal="skel", invuln=True, block=0.0, strike=0.05, adv=0.2)
    elif glyph == "5":
        p.update(hp=1, pal="shadow", block=0.5)
    elif glyph == "6":
        p.update(hp=7, pal="vizier", block=0.7, strike=0.1, adv=0.25, restrike=0.4, refract=8)
    elif glyph == "7":
        p.update(hp=3, pal="shadow", block=0.45, strike=0.07)
    return p


class Game:
    def __init__(self):
        self.score = 0
        self.guards_killed = 0
        self.potions = 0
        self.levels_done = 0
        self.n = 1
        self.maxhp = 3
        self.has_sword = False
        self.clock = 0
        self.tick = 0
        self.phase = "card"
        self.phase_t = 0
        self.world = None
        self.guards = []
        self.rend = None
        self.bot = Bot(self)
        self.rows = None
        self.attempts = 0
        self.card_text = ""
        self.over = None
        self.level_start_clock = 0
        self.flash = 0
        self.prince = None

    # ---- time ----
    def minutes_left(self):
        return max(0, GAME_MINUTES - self.clock // TICKS_PER_GAME_MINUTE)

    # ---- level setup ----
    def new_level(self, n, regenerate=True):
        self.n = n
        if regenerate or self.rows is None:
            self.rows, self.names = make_rows(n)
        self.world = World(n, self.rows)
        self.world.bloody = set()
        self.world.slabs = []
        w = self.world
        self.prince = Actor(self, "prince", "prince", w.start[0] * TW + 16, w.start[1], 1)
        p = self.prince
        p.hp = p.maxhp = self.maxhp
        p.has_sword = self.has_sword
        p.refract_len = 0
        self.guards = []
        for (x, y, c) in w.spawn:
            self.guards.append(self.make_guard(x * TW + 16, y, c))
        self.bot.reset()
        self.bot.start_plan(p)
        self.rend = Renderer(self)
        self.rend.cur = None
        self.level_start_clock = self.clock

    def make_guard(self, x, row, glyph, face=-1):
        pr = guard_params(self.n, glyph)
        a = Actor(self, "merge" if glyph == "5" else "guard", pr["pal"], x, row, face)
        a.hp = a.maxhp = pr["hp"]
        a.p_block, a.p_strike, a.p_adv, a.p_restrike = pr["block"], pr["strike"], pr["adv"], pr["restrike"]
        a.refract_len = pr["refract"]
        a.invuln = pr["invuln"]
        a.alerted = False
        a.reacted = False
        a.glyph = glyph
        a.home = x
        if glyph != "5":
            a.out = True
            a.start("eg", "eg")
        return a

    def current_foe(self):
        p = self.prince
        best = None
        for g in self.guards:
            if g.kind == "guard" and g.alerted and g.alive_ok() and not g.hidden and g.row == p.row:
                if best is None or abs(g.x - p.x) < abs(best.x - p.x):
                    best = g
        return best

    # ---- hooks from actors ----
    def on_death(self, a, how):
        if a is self.prince:
            self.phase = "dead"
            self.phase_t = 0
        elif a.kind == "guard" and not getattr(a, "counted", False) and a.glyph != "7":
            a.counted = True
            self.guards_killed += 1
            self.score += 200

    def guard_fell(self, a):
        pass

    def on_item(self, a, it):
        if it == "S":
            self.has_sword = True
        elif it == "H":
            self.maxhp = max(self.maxhp, a.maxhp)
            self.score += 100
            self.potions += 1
        elif it == "h":
            self.score += 25
            self.potions += 1
        elif it == "f":
            self.score += 25

    # ---- guard AI ----
    def guard_ai(self, g):
        p = self.prince
        g.keys()
        if g.kind == "merge":
            if g.alive_ok() and not g.hidden and p.alive_ok() and p.row == g.row and abs(p.x - g.x) < 110:
                g.act = None
                if g.st == "stand" or g.st in ("start", "run"):
                    sgn = 1 if p.x > g.x else -1
                    if abs(p.x - g.x) < 22:
                        g.hidden = True
                        p.hp = p.maxhp
                        self.flash = 6
                        self.score += 300
                    else:
                        g.keys(sgn)
            return
        if not g.alive_ok() or g.hidden:
            return
        d = abs(p.x - g.x)
        if not g.alerted:
            if p.alive_ok() and p.row == g.row and d < 170 and not p.hidden:
                g.alerted = True
            else:
                return
        if g.st != "eg" or p.row != g.row or not p.alive_ok():
            return
        if (p.x - g.x) * g.face < 0:
            g.face = 1 if p.x > g.x else -1
        if g.refract > 0:
            return
        r = random.random
        if p.st == "strike" and p.fi <= 5 and d <= 62:
            if not g.reacted:
                g.reacted = True
                if r() < g.p_block:
                    g.keys(up=True)
                    return
        elif p.st != "strike":
            g.reacted = False
        if g.riposte > 0:
            g.riposte = 0
            if r() < g.p_restrike:
                g.keys(shift=True)
                return
        if d <= REACH - 4:
            if r() < g.p_strike:
                g.keys(shift=True)
            elif d < 24 and r() < 0.2:
                g.keys(-g.face)
        elif abs(g.x + g.face * 14 - g.home) <= 120:
            if d <= REACH + 14:
                if r() < g.p_adv * 0.4:
                    g.keys(g.face)
            elif r() < g.p_adv:
                g.keys(g.face)

    def fighters(self):
        return [self.prince] + [g for g in self.guards if g.kind == "guard"]

    def resolve_strikes(self):
        act = META["strike"]["ev"]["active"]
        pa = META["parry"]["ev"]["active"]
        for a in self.fighters():
            if a.st != "strike" or a.struck or not (act[0] <= a.fi <= act[1]):
                continue
            t = self.prince if a is not self.prince else a.foe
            if t is None or not t.alive_ok() or t.row != a.row or t.hidden:
                continue
            if abs(a.x - t.x) > REACH or (t.x - a.x) * a.face <= 0:
                continue
            a.struck = True
            if t.st == "parry" and pa[0] <= t.fi <= pa[1] and (a.x - t.x) * t.face > 0:
                a.start("hit", "hit")
                t.riposte = 20
                continue
            dmg = 2 if (t.kind == "prince" and not t.out) else 1
            shove = 6.0 + (5.0 if t.invuln else 0.0)
            nx = t.x + a.face * shove
            t.x = self.world.barrier(t.x, nx, t.row, a.face)
            if t.invuln:
                t.start("hit", "hit")
            else:
                t.hurt(dmg, "sword")

    # ---- events ----
    def events(self):
        w = self.world
        p = self.prince
        for pos in list(w.mirror):
            if not w.mirror[pos] and p.grounded() and p.row == pos[1] and abs(p.x - (pos[0] * TW + 16)) < 10:
                w.mirror[pos] = True
                s = self.make_guard(pos[0] * TW + 16 + 96 * p.face, pos[1], "7", face=-p.face)
                s.alerted = True
                self.guards.append(s)
                self.flash = 4
        if w.exit_pos and not p.hidden and p.alive_ok() and p.grounded():
            ex, ey = w.exit_pos
            if p.row == ey and p.tile() == ex and abs(p.x - (ex * TW + 16)) < 13 and w.exit_k >= 5.5 and self.phase == "play":
                p.hidden = True
                self.phase = "exiting"
                self.phase_t = 0
                w.exit_open = False

    # ---- level end ----
    def finish_level(self):
        bonus = min(500, self.minutes_left() * 8)
        self.score += 1000 + bonus
        self.levels_done += 1

    # ---- main tick ----
    def play_tick(self):
        w = self.world
        p = self.prince
        self.clock += 1
        actors = [p] + [g for g in self.guards if g.alive_ok()]
        w.update(actors)
        if p.alive_ok():
            self.bot.run(p)
        for g in self.guards:
            self.guard_ai(g)
        for a in [p] + self.guards:
            if a.refract > 0 and a.st == "eg":
                a.refract -= 1
            if a.riposte > 0:
                a.riposte -= 1
        foe = self.current_foe()
        p.foe = foe
        for gd in self.guards:
            gd.foe = p
        p.tick()
        for gd in self.guards:
            gd.tick()
        self.resolve_strikes()
        self.events()


# ---------------------------------------------------------------------------------------------------------------
# Game loop
# ---------------------------------------------------------------------------------------------------------------
def card(text, sub):
    clear()
    draw_text_centered(text, 360, "L", COLOR_YELLOW)
    draw_text_centered(sub, 520, "S", COLOR_WHITE)


def make():
    g = Game()
    end = EndScreen()
    s = {"mode": "card", "t": 0, "ticks": 0, "tries": 0, "ended": False}

    def begin_card(n):
        g.new_level(n)
        s.update(mode="card", t=0, tries=0)
        card("LEVEL %d" % n, "%d MINUTES LEFT" % g.minutes_left())

    begin_card(1)

    def camera():
        w, p = g.world, g.prince
        sx = max(0, min(w.w // SCR_W - 1, int(p.x // LW)))
        sy = max(0, min(w.h // SCR_H - 1, int((p.y - FEET + 20) // TH) // SCR_H))
        return sx, sy

    def finish(title):
        s["mode"] = "over"
        end.start(g.score, title)

    def step():
        s["ticks"] += 1
        m = s["mode"]
        if m == "over":
            return end.tick()
        if s["ticks"] >= CAP_TICKS - 120:
            finish("TIME LIMIT")
            return False
        if m == "card":
            s["t"] += 1
            more = g.bot.plan_step(g.prince)
            if g.bot.mandatory_fail and s["tries"] < 8:
                s["tries"] += 1
                g.new_level(g.n)
                return False
            if not more and s["t"] >= 60:
                s["mode"] = "play"
                g.phase = "play"
                clear()
                g.rend.enter(*camera())
                g.rend.hud(True)
            return False
        if m == "play" or m == "dead":
            if g.minutes_left() <= 0:
                finish("TIME UP")
                return False
            g.play_tick()
            g.rend.hud()
            c = camera()
            if c != g.rend.cur:
                g.rend.enter(*c)
            g.rend.render()
            if g.phase == "dead":
                s["mode"] = "dead"
                g.phase_t += 1
                if g.phase_t > 75:
                    g.new_level(g.n, regenerate=False)
                    g.phase = "play"
                    s["mode"] = "play"
                    g.rend.enter(*camera())
                    g.rend.hud(True)
            elif g.phase == "exiting":
                s["mode"] = "exiting"
                s["t"] = 0
            elif g.clock - g.level_start_clock > 30 * 120:
                # stall guard: a level that takes more than two minutes is abandoned
                g.finish_level()
                nxt = g.n + 1
                if nxt > LEVELS:
                    finish("VICTORY")
                else:
                    g.phase = "play"
                    begin_card(nxt)
            return False
        if m == "exiting":
            s["t"] += 1
            w = g.world
            w.exit_k = max(0.0, w.exit_k - 0.3)
            g.clock += 1
            g.rend.render()
            if s["t"] > 28:
                g.finish_level()
                g.phase = "play"
                nxt = g.n + 1
                if nxt > LEVELS or g.score >= SCORE_TARGET:
                    finish("VICTORY" if nxt > LEVELS else "WELL PLAYED")
                else:
                    begin_card(nxt)
            return False
        return False

    return step
