# Lemmings (DMA Design, 1991) played by a bot. Virtual 320x200 screen shown at 5x (1600x1000, centred).
# Rendering: every level is kept as pre-expanded RGB565 rows (one virtual pixel = 10 bytes); a tick re-composes only
# the virtual rows touched by moving sprites or carved terrain and writes each of them to five scanlines.
# The game logic follows the original at 15 steps/s; the bot runs it at 2 steps per 30 Hz tick, i.e. 2x speed,
# so a game of seven levels fits the 4-7 minute window.
from fbcore import *
import zlib, math

B = load_bundle("g_lemmings.bin")
LEM, DIGITS, LEVELS = B["lem"], B["digits"], B["levels"]
M = 40                      # row margin in virtual px (see g_lemmings_build)
BPX = 10                    # bytes per virtual pixel after the 5x horizontal expansion
OX, OY = 160, 40            # screen position of virtual pixel (0, 0)
VW, FH, PANEL = 320, 160, 40
ROWB = VW * BPX
BLACK10 = bytes(BPX)
BRICK10 = (((232 >> 3) << 11) | ((138 >> 2) << 5) | (40 >> 3)).to_bytes(2, "little") * 5
WHITE10 = b"\xff\xff" * 5
GREEN10 = (((80 >> 3) << 11) | ((255 >> 2) << 5) | (80 >> 3)).to_bytes(2, "little") * 5
GREY10 = (((150 >> 3) << 11) | ((150 >> 2) << 5) | (160 >> 3)).to_bytes(2, "little") * 5
ORANGE10 = (((232 >> 3) << 11) | ((120 >> 2) << 5) | (30 >> 3)).to_bytes(2, "little") * 5

(WALK, FALL, FLOAT, CLIMB, HOIST, BUILD, SHRUG, BASH, MINE, DIG, BLOCK, OHNO, EXIT, DROWN, BURN, SPLAT) = range(16)
DYING = (EXIT, DROWN, BURN, SPLAT)
SKILLS = ("cl", "fl", "bo", "bl", "bu", "ba", "mi", "di")
BTN = {"cl": 2, "fl": 3, "bo": 4, "bl": 5, "bu": 6, "ba": 7, "mi": 8, "di": 9, "nuke": 11}
LABEL = {WALK: "WALKER", FALL: "FALLER", FLOAT: "FLOATER", CLIMB: "CLIMBER", HOIST: "CLIMBER", BUILD: "BUILDER",
         SHRUG: "BUILDER", BASH: "BASHER", MINE: "MINER", DIG: "DIGGER", BLOCK: "BLOCKER", OHNO: "BOMBER"}
FATAL_FALL = 60
BOMB_STEPS = 75             # 5 seconds at 15 steps/s
SPRITE_NAME = {WALK: "walk", FALL: "fall", FLOAT: "float", CLIMB: "climb", HOIST: "hoist", BUILD: "build",
               SHRUG: "shrug", BASH: "bash", MINE: "mine", DIG: "dig", BLOCK: "block", OHNO: "ohno", EXIT: "exit",
               DROWN: "drown", BURN: "burn", SPLAT: "splat"}


class Lem:
    __slots__ = ("id", "x", "y", "dx", "st", "t", "fall", "cl", "fl", "bomb", "bricks", "ty", "alive")

    def __init__(self, i, x, y):
        self.id, self.x, self.y, self.dx = i, x, y, 1
        self.st, self.t, self.fall = FALL, 0, 0
        self.cl = self.fl = False
        self.bomb = self.bricks = self.ty = 0
        self.alive = True


class World:
    def __init__(self, lv):
        self.lv = lv
        self.w = lv["w"]
        self.mask = bytearray(zlib.decompress(lv["mask"]))
        raw = zlib.decompress(lv["rows"])
        st = lv["stride"]
        self.rows = [bytearray(raw[i * st:(i + 1) * st]) for i in range(FH)]
        self.tdirty = set()
        self.tchanged = True
        self.lems = []
        self.blockers = []
        self.booms = []
        self.n, self.save_need = lv["n"], lv["save"]
        self.rr = lv["rr"]
        self.skills = dict(zip(SKILLS, lv["skills"]))
        self.spawned = self.saved = self.dead = 0
        self.time = 0
        self.time_left = lv["time"] * 15
        self.spawn_t = 45
        self.nuked = False
        self.timeup = False
        self.last_event = 0
        self.ex, self.ey = lv["entrance"][0] + 20, lv["entrance"][1] + 22
        self.exx, self.exy = lv["exit"]
        self.waters = [o for o in lv["objs"] if o["kind"] == "water"]
        self.fires = [o for o in lv["objs"] if o["kind"] == "fire"]
        self.crushers = [o for o in lv["objs"] if o["kind"] == "crusher"]
        self.selected = None

    # ---- terrain ---------------------------------------------------------------------------------
    def solid(self, x, y):
        if x < 0 or x >= self.w:
            return True
        if y < 0 or y >= FH:
            return False
        return self.mask[y * self.w + x] != 0

    def carve_span(self, y, x0, x1):
        # Removes diggable pixels of one row; steel stays. Returns how many pixels were removed.
        if y < 0 or y >= FH:
            return 0
        x0, x1 = max(0, x0), min(self.w, x1)
        if x1 <= x0:
            return 0
        a = y * self.w
        seg = self.mask[a + x0:a + x1]
        n1 = seg.count(1)
        if n1 == 0:
            return 0
        row = self.rows[y]
        if 2 in seg:
            for x in range(x0, x1):
                if self.mask[a + x] == 1:
                    self.mask[a + x] = 0
                    row[(x + M) * BPX:(x + M + 1) * BPX] = BLACK10
        else:
            n = x1 - x0
            self.mask[a + x0:a + x1] = bytes(n)
            row[(x0 + M) * BPX:(x1 + M) * BPX] = bytes(n * BPX)
        self.tdirty.add(y)
        self.tchanged = True
        return n1

    def has_steel(self, y0, y1, x0, x1):
        x0, x1 = max(0, x0), min(self.w, x1)
        for y in range(max(0, y0), min(FH, y1)):
            if 2 in self.mask[y * self.w + x0:y * self.w + x1]:
                return True
        return False

    def add_brick(self, y, x0, x1):
        if y < 0 or y >= FH:
            return
        row = self.rows[y]
        a = y * self.w
        for x in range(max(0, x0), min(self.w, x1 + 1)):
            if self.mask[a + x] == 0:
                self.mask[a + x] = 1
                row[(x + M) * BPX:(x + M + 1) * BPX] = BRICK10
        self.tdirty.add(y)
        self.tchanged = True

    def wall_ahead(self, x, y, dx):
        # basher/miner only make sense when diggable ground is within a few pixels in front of the chest
        for k in range(1, 7):
            if self.solid(x + dx * k, y - 5):
                return True
        return False

    # ---- lemming behaviour -----------------------------------------------------------------------
    def kill(self, l):
        l.alive = False
        if l in self.blockers:
            self.blockers.remove(l)
        self.dead += 1
        self.last_event = self.time

    def set_state(self, l, st):
        if l.st == BLOCK and st != BLOCK and l in self.blockers:
            self.blockers.remove(l)
        l.st, l.t = st, 0

    def start_fall(self, l):
        self.set_state(l, FALL)
        l.fall = 0

    def walk(self, l):
        x, y, dx = l.x, l.y, l.dx
        sol = self.solid
        for k in range(4):
            if sol(x, y + 1 + k):
                break
        else:
            self.start_fall(l)
            return
        y += k
        nx = x + dx
        for b in self.blockers:
            if b is not l and abs(nx - b.x) <= 5 and abs(y - b.y) <= 6 and (b.x - x) * dx > 0:
                l.dx, l.y = -dx, y
                return
        if sol(nx, y):
            for k in range(1, 7):
                if not sol(nx, y - k):
                    l.x, l.y = nx, y - k
                    return
            l.y = y
            if l.cl and 0 < nx < self.w - 1:
                self.set_state(l, CLIMB)
            else:
                l.dx = -dx
            return
        for k in range(4):
            if sol(nx, y + 1 + k):
                l.x, l.y = nx, y + k
                return
        l.x, l.y = nx, y
        self.start_fall(l)

    def falling(self, l):
        if l.st == FALL and l.fl and l.fall >= 12:
            self.set_state(l, FLOAT)
        for _ in range(2 if l.st == FLOAT else 3):
            if self.solid(l.x, l.y + 1):
                if l.st != FLOAT and l.fall > FATAL_FALL:
                    self.set_state(l, SPLAT)
                else:
                    self.set_state(l, WALK)
                return
            l.y += 1
            l.fall += 1
        if l.y > FH + 10:
            self.kill(l)

    def climb(self, l):
        x, y, dx = l.x, l.y, l.dx
        if self.solid(x, y - 10):
            l.dx = -dx
            self.start_fall(l)
            return
        if not self.solid(x + dx, y - 9):
            for yy in range(y - 9, y + 2):
                if self.solid(x + dx, yy):
                    l.ty = yy - 1
                    self.set_state(l, HOIST)
                    return
            l.dx = -dx
            self.start_fall(l)
            return
        if l.t % 2 == 0:
            l.y -= 1

    def hoist(self, l):
        if l.t >= 4:
            l.x += l.dx
            l.y = l.ty
            self.set_state(l, WALK)

    def build(self, l):
        c = (l.t - 1) % 16
        dx, x, y = l.dx, l.x, l.y
        if c == 8:
            if dx > 0:
                self.add_brick(y, x + 1, x + 6)
            else:
                self.add_brick(y, x - 6, x - 1)
        elif c == 15:
            x2, y2 = x + 2 * dx, y - 1
            if self.solid(x2, y2) or self.solid(x2, y2 - 9):
                if self.solid(x2, y2 - 9) and not self.solid(x2, y2):
                    l.dx = -dx
                self.set_state(l, WALK)
                return
            l.x, l.y = x2, y2
            l.bricks -= 1
            if l.bricks == 0:
                self.set_state(l, SHRUG)

    def bash(self, l):
        c = (l.t - 1) % 16
        dx, x, y = l.dx, l.x, l.y
        if c == 0 and not self.wall_ahead(x, y, dx):
            self.set_state(l, WALK)
        elif c == 5:
            x0, x1 = (x + 1, x + 10) if dx > 0 else (x - 9, x)
            if self.has_steel(y - 9, y + 1, x0, x1):
                l.dx = -dx
                self.set_state(l, WALK)
                return
            for yy in range(y - 9, y + 1):
                self.carve_span(yy, x0, x1)
        elif 6 <= c <= 9:
            nx = x + dx
            if self.solid(nx, y):
                return
            for k in range(4):
                if self.solid(nx, y + 1 + k):
                    l.x, l.y = nx, y + k
                    return
            l.x = nx
            self.start_fall(l)
        elif c == 15 and not self.wall_ahead(x, y, dx):
            self.set_state(l, WALK)

    def mine(self, l):
        c = (l.t - 1) % 6
        dx, x, y = l.dx, l.x, l.y
        if c == 2:
            x0, x1 = (x, x + 9) if dx > 0 else (x - 8, x + 1)
            if self.has_steel(y - 9, y + 2, x0, x1):
                l.dx = -dx
                self.set_state(l, WALK)
                return
            removed = sum(self.carve_span(yy, x0, x1) for yy in range(y - 9, y + 2))
            if removed == 0:
                self.set_state(l, WALK)
        elif c == 5:
            nx, ny = x + 2 * dx, y + 1
            if self.solid(nx, ny):
                self.set_state(l, WALK)
                return
            l.x, l.y = nx, ny
            if not self.solid(nx, ny + 1):
                self.start_fall(l)

    def dig(self, l):
        if l.t % 4:
            return
        x, y = l.x, l.y
        if not self.solid(x, y + 1):
            self.start_fall(l)
            return
        if self.has_steel(y + 1, y + 2, x - 4, x + 4):
            self.set_state(l, WALK)
            return
        self.carve_span(y + 1, x - 4, x + 4)
        l.y = y + 1
        if not self.solid(x, l.y + 1):
            self.start_fall(l)

    def explode(self, l):
        x, y = l.x, l.y
        for yy in range(y - 16, y + 7):
            f = (yy - (y - 5)) / 11.0
            half = int(math.sqrt(max(0.0, 1 - f * f)) * 8)
            if half:
                self.carve_span(yy, x - half, x + half + 1)
        self.booms.append([x, y, 0])
        self.kill(l)

    def traps(self, l):
        x, y = l.x, l.y
        for o in self.waters:
            if o["x"] <= x < o["x"] + o["w"] and y >= o["y"]:
                l.y = o["y"] + 4
                self.set_state(l, DROWN)
                self.last_event = self.time
                return
        for o in self.fires:
            if o["x"] <= x < o["x"] + o["w"] and y >= o["ky"]:
                self.set_state(l, BURN)
                self.last_event = self.time
                return
        for o in self.crushers:
            if 5 <= (self.time // o["per"]) % 12 <= 6 and o["x"] + 4 <= x < o["x"] + 12 and y > o["y"] + 40:
                self.set_state(l, SPLAT)
                self.last_event = self.time
                return
        if abs(x - self.exx) <= 4 and self.exy - 8 <= y <= self.exy and l.st != BLOCK and l.st != OHNO:
            self.set_state(l, EXIT)

    def step_lem(self, l):
        l.t += 1
        st = l.st
        if l.bomb and st not in DYING and st != OHNO:
            l.bomb -= 1
            if l.bomb == 0:
                if st in (FALL, FLOAT):
                    self.explode(l)
                    return
                self.set_state(l, OHNO)
                return
        if st == WALK:
            self.walk(l)
        elif st in (FALL, FLOAT):
            self.falling(l)
        elif st == BUILD:
            self.build(l)
        elif st == BASH:
            self.bash(l)
        elif st == MINE:
            self.mine(l)
        elif st == DIG:
            self.dig(l)
        elif st == CLIMB:
            self.climb(l)
        elif st == HOIST:
            self.hoist(l)
        elif st == SHRUG:
            if l.t >= 8:
                self.set_state(l, WALK)
        elif st == BLOCK:
            if not self.solid(l.x, l.y + 1):
                self.start_fall(l)
        elif st == OHNO:
            if l.t >= 16:
                self.explode(l)
            return
        elif st == EXIT:
            if l.t >= 8:
                l.alive = False
                self.saved += 1
                self.last_event = self.time
            return
        else:
            if l.t >= 16:
                self.kill(l)
            return
        if l.alive and l.st not in DYING:
            self.traps(l)

    def step(self):
        self.time += 1
        if not self.timeup:
            self.time_left -= 1
            if self.time_left <= 0:
                self.timeup = True
                self.nuke()
        if self.spawned < self.n and not self.nuked:
            self.spawn_t -= 1
            if self.spawn_t <= 0:
                self.spawned += 1
                l = Lem(self.spawned, self.ex, self.ey)
                self.lems.append(l)
                self.spawn_t = 4 + int((99 - self.rr) * 0.5)
        for l in self.lems:
            if l.alive:
                self.step_lem(l)
        if any(not l.alive for l in self.lems):
            self.lems = [l for l in self.lems if l.alive]
        for b in self.booms:
            b[2] += 1
        if self.booms and self.booms[0][2] >= 16:
            self.booms = [b for b in self.booms if b[2] < 16]

    def nuke(self):
        self.nuked = True
        for i, l in enumerate(self.lems):
            if not l.bomb and l.st not in DYING:
                l.bomb = 20 + (i * 7) % 50
        self.dead += self.n - self.spawned
        self.spawned = self.n

    def finished(self):
        return self.spawned >= self.n and not self.lems

    # ---- player actions ----------------------------------------------------------------------------
    def assign(self, l, s):
        if self.skills[s] <= 0 or l.st in DYING or l.st == OHNO:
            return False
        st = l.st
        if s == "cl":
            if l.cl:
                return False
            l.cl = True
        elif s == "fl":
            if l.fl:
                return False
            l.fl = True
        elif s == "bo":
            if l.bomb:
                return False
            l.bomb = BOMB_STEPS
        elif st not in (WALK, SHRUG if s == "bu" else WALK):
            return False
        elif s == "bl":
            self.set_state(l, BLOCK)
            self.blockers.append(l)
        elif s == "bu":
            l.bricks = 12
            self.set_state(l, BUILD)
        elif s == "ba":
            self.set_state(l, BASH)
        elif s == "mi":
            self.set_state(l, MINE)
        elif s == "di":
            self.set_state(l, DIG)
        self.skills[s] -= 1
        self.last_event = self.time
        return True


# ---- rendering ------------------------------------------------------------------------------------
class Renderer:
    def __init__(self):
        self.panel_static = [bytearray(r) for r in B["panel"]]
        self.panel = [bytearray(r) for r in self.panel_static]
        self.prev = set()
        self.cam_drawn = None
        self.pdirty = set(range(PANEL))
        self.status_key = self.btn_key = None
        self.mm_cam = None
        self.prev_list = []
        self.f_hud, self.f_cnt, self.f_big = B["font_hud"], B["font_cnt"], B["font_big"]
        self.mm_rows = None

    def new_level(self, world):
        self.world = world
        self.prev = set()
        self.cam_drawn = None
        self.status_key = self.btn_key = None
        self.mm_cam = None
        self.prev_list = []
        self.panel = [bytearray(r) for r in self.panel_static]
        self.pdirty = set(range(PANEL))
        self.mm_scale = max(1, -(-world.w // 104))
        self.mm_rows = None
        for y in range(FH):
            world.tdirty.add(y)

    @staticmethod
    def paste(rowbuf, spr, sx, j):
        base = (sx + M) * BPX
        for off, data in spr["runs"][j]:
            rowbuf[base + off:base + off + len(data)] = data

    def text_width(self, font, s):
        return sum(font["adv"].get(c, font["space"]) for c in s)

    def draw_text(self, rows, font, s, x, y):
        for c in s:
            g = font["glyphs"].get(c)
            if g is not None:
                for j in range(g["h"]):
                    if 0 <= y + j < len(rows):
                        self.paste(rows[y + j], g, x, j)
                x += font["adv"][c]
            else:
                x += font["space"]

    def restore(self, y0, y1, x0=0, x1=VW):
        for p in range(y0, y1):
            a, b = (x0 + M) * BPX, (x1 + M) * BPX
            self.panel[p][a:b] = self.panel_static[p][a:b]
            self.pdirty.add(p)

    def update_panel(self, w, cursor_label, cam):
        out = len(w.lems)
        pct = w.saved * 100 // w.n
        tl = max(0, w.time_left // 15)
        key = (out, pct, tl, cursor_label)
        if key != self.status_key:
            self.status_key = key
            self.restore(0, 16)
            if cursor_label:
                self.draw_text(self.panel, self.f_cnt, cursor_label, 2, 2)
            self.draw_text(self.panel, self.f_hud, "OUT %d" % out, 100, 0)
            self.draw_text(self.panel, self.f_hud, "IN %d%%" % pct, 170, 0)
            self.draw_text(self.panel, self.f_hud, "TIME %d-%02d" % (tl // 60, tl % 60), 236, 0)
        key = (w.rr, tuple(w.skills.values()), w.selected)
        if key != self.btn_key:
            self.btn_key = key
            self.restore(16, 40, 0, 192)
            counts = [w.rr, w.rr] + [w.skills[s] for s in SKILLS]
            for i, c in enumerate(counts):
                if c > 0 or i < 2:
                    t = "%02d" % c if c < 100 else "99"
                    self.draw_text(self.panel, self.f_cnt, t, i * 16 + 3, 17)
            if w.selected in BTN:
                sp = B["hi"]
                for j in range(sp["h"]):
                    self.paste(self.panel[16 + j], sp, BTN[w.selected] * 16, j)
        self.update_minimap(w, cam)

    def update_minimap(self, w, cam):
        s = self.mm_scale
        if not w.tchanged and cam // s == self.mm_cam and w.time & 3:
            return
        if self.mm_rows is None or w.tchanged:
            self.mm_rows = []
            cols = -(-w.w // s)
            for r in range(20):
                row = bytearray(104 * BPX)
                a = min(FH - 1, r * 8 + 4) * w.w
                for c in range(cols):
                    v = w.mask[a + min(w.w - 1, c * s + s // 2)]
                    if v:
                        row[c * BPX:(c + 1) * BPX] = ORANGE10 if v == 1 else GREY10
                self.mm_rows.append(row)
            w.tchanged = False
        self.mm_cam = cam // s
        x0, wd = cam // s, VW // s
        dots = [(l.x // s, l.y // 8) for l in w.lems if l.st != BLOCK]
        for r in range(20):
            row = bytearray(self.mm_rows[r])
            if r in (0, 19):
                for c in range(x0, min(104, x0 + wd + 1)):
                    row[c * BPX:(c + 1) * BPX] = WHITE10
            else:
                row[x0 * BPX:(x0 + 1) * BPX] = WHITE10
                e = min(103, x0 + wd)
                row[e * BPX:(e + 1) * BPX] = WHITE10
            for dxx, dyy in dots:
                if dyy == r and 0 <= dxx < 104:
                    row[dxx * BPX:(dxx + 1) * BPX] = GREEN10
            p = 18 + r
            self.panel[p][(208 + M) * BPX:(208 + M + 104) * BPX] = row
            self.pdirty.add(p)

    def lemming_sprite(self, l):
        name = SPRITE_NAME[l.st]
        fr = LEM[name]["R" if l.dx > 0 else "L"]
        t, st = l.t, l.st
        if st == WALK:
            i = t % 8
        elif st == FALL:
            i = (t // 2) % 4
        elif st == FLOAT:
            i = min(t, 3) if t < 4 else 4 + (t // 3) % 2
        elif st == CLIMB:
            i = (t // 2) % 4
        elif st == HOIST:
            i = min(t, 3)
        elif st == BUILD:
            i = ((t - 1) % 16) // 2
        elif st == SHRUG:
            i = (t // 4) % 2
        elif st == BASH:
            i = ((t - 1) % 16) // 2
        elif st == MINE:
            i = ((t - 1) % 6) * 4 // 6
        elif st == DIG:
            i = (t // 2) % 2
        elif st == BLOCK:
            i = (t // 5) % 4
        elif st == OHNO:
            i = (t // 3) % 2
        elif st == EXIT:
            i = min(t, 7)
        else:
            i = min(t // 2, 7)
        return fr[i]

    def instances(self, w, cam, cursor):
        out = []
        lv = w.lv
        t = w.time
        ex, ey = lv["entrance"]
        k = 0 if t < 20 else min(5, (t - 20) // 4)
        out.append((lv["entr"][k], ex - cam, ey))
        out.append((lv["exitspr"][(t // 4) % 4], w.exx - 15 - cam, w.exy - 26))
        for o in lv["objs"]:
            out.append((o["frames"][(t // o["per"]) % len(o["frames"])], o["x"] - cam, o["y"]))
        for l in w.lems:
            spr = self.lemming_sprite(l)
            out.append((spr, l.x - cam - spr["ax"], l.y - spr["ay"]))
            if l.bomb and l.st not in DYING and l.st != OHNO:
                d = DIGITS[str((l.bomb + 14) // 15)]
                out.append((d, l.x - cam - 4, l.y - 23))
        for bx, by, bt in w.booms:
            spr = LEM["boom"][min(bt, 15)]
            out.append((spr, bx - cam - spr["ax"], by - spr["ay"]))
        cx, cy, over = cursor
        spr = B["box"] if over else B["cross"]
        out.append((spr, int(cx) - spr["ax"], int(cy) - spr["ay"]))
        return out

    def render(self, w, cam, cursor, label):
        self.update_panel(w, label, cam)
        insts = self.instances(w, cam, cursor)
        cur = {(id(s), sx, sy) for s, sx, sy in insts}
        if cam != self.cam_drawn:
            dirty = set(range(FH))
            self.cam_drawn = cam
        else:
            dirty = set()
            changed = cur ^ self.prev
            if changed:
                for s, sx, sy in insts + self.prev_list:
                    if (id(s), sx, sy) in changed:
                        dirty.update(range(max(0, sy), min(FH + PANEL, sy + s["h"])))
        dirty.update(w.tdirty)
        w.tdirty.clear()
        self.prev, self.prev_list = cur, insts
        dirty.update(FH + p for p in self.pdirty)
        self.pdirty.clear()
        if not dirty:
            return
        pointer = (B["cross"], B["box"])
        rowmap = {}
        for s, sx, sy in insts:
            if sx < -M or sx + s["w"] > VW + M:
                continue
            field_only = s is not pointer[0] and s is not pointer[1]
            for j in range(s["h"]):
                vy = sy + j
                if vy in dirty and (vy < FH or not field_only) and vy >= 0:
                    rowmap.setdefault(vy, []).append((s, sx, j))
        a = cam * BPX
        for vy in sorted(dirty):
            if vy < 0 or vy >= FH + PANEL:
                continue
            if vy < FH:
                buf = w.rows[vy][a:a + (VW + 2 * M) * BPX]
            else:
                buf = bytearray(self.panel[vy - FH])
            for s, sx, j in rowmap.get(vy, ()):
                base = (sx + M) * BPX
                for off, data in s["runs"][j]:
                    buf[base + off:base + off + len(data)] = data
            mv = memoryview(buf)[M * BPX:M * BPX + ROWB]
            o = (OY + vy * 5) * S + OX * 2
            for k in range(5):
                fb[o + k * S:o + k * S + ROWB] = mv


# ---- the bot ----------------------------------------------------------------------------------------
class Bot:
    # Plays like a person: picks a skill button, moves the pointer to the lemming, clicks when it is under the
    # pointer. Level scripts say where each skill is needed; the bot works on whichever step has a lemming about
    # to arrive and, when the script is used up, analyses the terrain itself.
    def __init__(self, world, rnd):
        self.w = world
        self.rnd = rnd
        self.plan = [dict(p) for p in world.lv["plan"]]
        self.done = [False] * len(self.plan)
        self.cur = None
        self.phase = "select"
        self.cx, self.cy = 160.0, 100.0
        self.cam_f = float(world.lv["cam0"])
        self.moving_cam = True
        self.ids = {}
        self.dwell = 0
        self.t0 = 0
        self.timer = 0
        self.ff = 1
        self.cooldown = 0
        self.acted = set()
        self.nuke_dwell = 0
        self.focus = world.lv["entrance"][0]

    def cam(self):
        return int(round(self.cam_f))

    def move_pointer(self, tx, ty):
        dx, dy = tx - self.cx, ty - self.cy
        d = math.hypot(dx, dy)
        if d > 0.4:
            sp = min(d, max(1.6, d * 0.4), 14.0)
            self.cx += dx / d * sp
            self.cy += dy / d * sp
        self.cx = min(VW - 1.0, max(0.0, self.cx))
        self.cy = min(FH + PANEL - 1.0, max(0.0, self.cy))

    def update_camera(self):
        tgt = max(0.0, min(self.w.w - VW, self.focus - VW / 2))
        diff = tgt - self.cam_f
        if abs(diff) > 36:
            self.moving_cam = True
        elif abs(diff) < 3:
            self.moving_cam = False
        if self.moving_cam:
            self.cam_f += max(-6.0, min(6.0, diff * 0.12 + (1 if diff > 0 else -1) * 0.6))

    def eligible(self, l, st, strict=False):
        s, w = st["s"], self.w
        if "who" in st and l.id != st["who"]:
            return False
        if "same" in st:
            # the lemming is selected as soon as it exists, so the skill button is ready before it finishes building
            return l.id == self.ids.get(st["same"]) and l.st not in DYING and st["ymin"] <= l.y <= st["ymax"]
        if st.get("target") == "blocker":
            return l.st == BLOCK
        elif l.dx != st["dx"]:
            return False
        if not st["ymin"] <= l.y <= st["ymax"]:
            return False
        k = l.st
        if s == "cl":
            return k == WALK and not l.cl
        if s == "fl":
            return k in (WALK, FALL) and not l.fl
        if s == "bo":
            return not l.bomb and k not in DYING and k != OHNO
        if s == "bu":
            return k in (WALK, SHRUG)
        if s == "ba":
            return k == WALK and (not strict or w.wall_ahead(l.x, l.y, l.dx))
        return k == WALK

    def candidates(self, st, strict=False):
        w = self.w
        if "when_x" in st and not any(l.x >= st["when_x"] for l in w.lems):
            return []
        return [l for l in w.lems if self.eligible(l, st, strict)]

    def active(self, st):
        # a lemming that fits the step is on its way (or already there)
        if "same" in st and not self.done[st["same"]] or not all(self.done[j] for j in st.get("after", ())):
            return False
        return any(abs(l.x - st["at"]) < st.get("reach", 130) or st["slack"] > 130 for l in self.candidates(st))

    def choose(self):
        for i, st in enumerate(self.plan):
            if st.get("pre") and not self.done[i] and self.active(st):
                if i != self.cur:
                    self.cur, self.phase, self.dwell = i, "select", 0
                return i
        if self.cur is not None and not self.done[self.cur] and self.active(self.plan[self.cur]):
            return self.cur
        for i, st in enumerate(self.plan):
            if not self.done[i] and self.active(st):
                if i != self.cur:
                    self.cur, self.phase, self.dwell = i, "select", 0
                return i
        self.cur = None
        return None

    def finish_step(self, i):
        self.done[i] = True
        self.phase, self.dwell, self.cur = "select", 0, None

    def run_step(self, i):
        st = self.plan[i]
        w, s = self.w, st["s"]
        if w.skills[s] <= 0:
            self.finish_step(i)
            return None
        if self.phase == "select":
            st.setdefault("left", st.get("n", 1))
            if w.selected == s:
                self.phase = "seek"
            else:
                tx, ty = BTN[s] * 16 + 8, 188
                if math.hypot(tx - self.cx, ty - self.cy) < 2.5:
                    self.dwell += 1
                    if self.dwell >= 4:
                        w.selected = s
                        self.phase, self.dwell = "seek", 0
                return tx, ty
        cam = self.cam()
        cands = self.candidates(st)
        near = [l for l in self.candidates(st, True) if abs(l.x - st["at"]) <= st["slack"]]
        if near:
            l = min(near, key=lambda m: (m.st == FALL, abs(m.x - st["at"])))
            self.focus = st["at"] if st["at"] > 0 else l.x
            tgt = (l.x - cam, l.y - 5)
            if math.hypot(tgt[0] - self.cx, tgt[1] - self.cy) <= 3.0:
                self.dwell += 1
                if self.dwell >= self.rnd.randint(1, 3) and w.assign(l, s):
                    self.ids[i] = l.id
                    st["left"] -= 1
                    self.dwell = 0
                    self.cooldown = 5
                    if st["left"] <= 0:
                        self.finish_step(i)
            else:
                self.dwell = 0
            return tgt
        coming = [l for l in cands if (st["at"] - l.x) * st["dx"] > 0] or cands
        l = min(coming, key=lambda m: (m.st == FALL, abs(m.x - st["at"])))
        self.focus = st["at"] if st["at"] > 0 else l.x
        return l.x - cam, l.y - 5

    def idle_target(self):
        # nothing to click right now: wait next to the spot where the next skill will be needed
        w = self.w
        best = None
        for i, p in enumerate(self.plan):
            if self.done[i] or p["at"] <= 0 or ("same" in p and not self.done[p["same"]]):
                continue
            if not all(self.done[j] for j in p.get("after", ())):
                continue
            lems = w.lems
            if "same" in p:
                lems = [l for l in lems if l.id == self.ids.get(p["same"])]
            elif p.get("target") == "blocker":
                lems = [l for l in lems if l.st == BLOCK]
            etas = [(p["at"] - l.x) * p["dx"] for l in lems if (p["at"] - l.x) * p["dx"] > -10]
            eta = min(etas) if etas else 99999
            if best is None or eta < best[0]:
                best = (eta, p)
        if best:
            eta, p = best
            self.focus = p["at"]
            gy = next((y for y in range(p["ymin"], FH) if w.solid(p["at"], y)), p["ymax"])
            if eta > 150:
                self.ff = 2
            return p["at"] - self.cam(), gy - 6
        if w.lems:
            self.focus = sum(l.x for l in w.lems) / len(w.lems)
        return None

    def analyse(self):
        # No script left (or it failed): look at what the walkers are about to meet and ask for a fitting skill.
        w = self.w
        for l in w.lems:
            if l.st != WALK or l.id in self.acted:
                continue
            x, y, dx = l.x, l.y, l.dx
            wall = next((k for k in range(1, 13) if w.solid(x + dx * k, y)), None)
            skill = None
            if wall is not None:
                h = 0
                while h < 50 and w.solid(x + dx * wall, y - h):
                    h += 1
                if h > 6:
                    if w.skills["ba"] > 0 and wall <= 4 and not w.has_steel(y - 9, y, x, x + dx * 10 if dx > 0 else x - 10):
                        skill = "ba"
                    elif w.skills["bu"] > 0 and h <= 22 and wall >= 2 * (h - 4) - 2:
                        skill = "bu"
                    elif w.skills["cl"] > 0 and h <= 45 and wall <= 3 and not l.cl:
                        skill = "cl"
            elif not any(w.solid(x + dx * 3, y + 1 + k) for k in range(4)):
                depth = next((k for k in range(1, 100) if w.solid(x + dx * 3, y + k)), 100)
                if depth > FATAL_FALL - 6:
                    if w.skills["fl"] > 0 and not l.fl:
                        skill = "fl"
                    elif w.skills["bl"] > 0 and not w.blockers:
                        skill = "bl"
            if skill:
                self.acted.add(l.id)
                self.plan.append(dict(s=skill, at=l.x, dx=l.dx, slack=8, ymin=l.y - 5, ymax=l.y + 5, who=l.id))
                self.done.append(False)
                return

    def tick(self):
        w = self.w
        self.timer += 1
        self.ff = 1
        tgt = None
        if self.cooldown:
            self.cooldown -= 1
        else:
            i = self.choose()
            if i is not None:
                tgt = self.run_step(i)
            else:
                self.ff = 2
                tgt = self.idle_target()
                if all(self.done) and self.timer % 12 == 0 and not w.nuked:
                    self.analyse()
                if w.spawned >= w.n and w.lems and w.time - w.last_event > 1000 and not w.nuked:
                    tx, ty = BTN["nuke"] * 16 + 8, 188
                    tgt = (tx, ty)
                    if math.hypot(tx - self.cx, ty - self.cy) < 2.5:
                        self.nuke_dwell += 1
                        if self.nuke_dwell >= 6:
                            w.nuke()
                            w.selected = "nuke"
        if tgt is None:
            tgt = (self.cx + math.sin(self.timer * 0.07) * 0.8, self.cy + math.cos(self.timer * 0.05) * 0.6)
        self.move_pointer(*tgt)
        self.update_camera()


# ---- game flow ----------------------------------------------------------------------------------------
def page(rend, lines, preview=None):
    # Full-screen text page: lines are (text, y, font); drawn into virtual rows, then written once.
    rows = [bytearray((VW + 2 * M) * BPX) for _ in range(FH + PANEL)]
    for text, y, font in lines:
        x = (VW - rend.text_width(font, text)) // 2
        rend.draw_text(rows, font, text, x, y)
    if preview is not None:
        x = (VW - preview["w"]) // 2
        for j in range(preview["h"]):
            rend.paste(rows[6 + j], preview, x, j)
    for vy, buf in enumerate(rows):
        mv = memoryview(buf)[M * BPX:M * BPX + ROWB]
        o = (OY + vy * 5) * S + OX * 2
        for k in range(5):
            fb[o + k * S:o + k * S + ROWB] = mv


def make():
    rnd = random.Random()
    clear(0)
    order = [int(i) for i in os.environ.get("LEMMINGS_LEVELS", "0,1,2,3,4,5,6").split(",")]
    rend = Renderer()
    big, red = B["font_big"], B["font_red"]
    st = dict(phase="intro", n=0, t=0, world=None, bot=None, score=0, tick=0, lvl_ticks=0, end=None, pct=0)

    def level_intro():
        lv = LEVELS[order[st["n"]]]
        pv = lv["preview"]
        need = lv["save"] * 100 // lv["n"]
        y0 = 6 + pv["h"] + 8
        page(rend, [("LEVEL %d  %s" % (st["n"] + 1, lv["name"]), y0, big),
                    ("NUMBER OF LEMMINGS %d" % lv["n"], y0 + 24, big),
                    ("%d%% TO BE SAVED" % need, y0 + 42, big),
                    ("RELEASE RATE %d" % lv["rr"], y0 + 60, big),
                    ("TIME %d MINUTES" % (lv["time"] // 60), y0 + 78, big),
                    ("RATING %s" % lv["rating"], y0 + 96, big)], pv)
        st["phase"], st["t"] = "intro", 0

    def start_play():
        lv = LEVELS[order[st["n"]]]
        w = World(lv)
        st["world"] = w
        st["bot"] = Bot(w, rnd)
        st["lvl_ticks"] = 0
        rend.new_level(w)
        st["phase"] = "play"

    def level_result():
        w, lv = st["world"], st["world"].lv
        pct = w.saved * 100 // w.n
        need = lv["save"] * 100 // lv["n"]
        ok = w.saved >= lv["save"]
        if ok:
            st["score"] += w.saved * 100 + 1000 + max(0, w.time_left // 15) * 3
        else:
            st["score"] += w.saved * 100
        lines = [("YOUR TIME RAN OUT!" if w.timeup else "ALL LEMMINGS ACCOUNTED FOR.", 34, big),
                 ("YOU RESCUED %d%%" % pct, 64, big), ("YOU NEEDED %d%%" % need, 84, big)]
        if ok:
            lines.append(("SUPERB! YOU RESCUED THEM ALL!" if w.saved == w.n else "YOU MADE IT!", 120, red))
            lines.append(("ROCK ON!" if pct >= need + 20 else "WELL DONE!", 142, red))
        else:
            lines.append(("YOU DIDN'T MAKE IT!", 120, red))
            lines.append(("BETTER LUCK NEXT TIME!", 142, red))
        page(rend, lines)
        st["phase"], st["t"] = "result", 0

    level_intro()
    endscr = EndScreen()

    def step():
        st["tick"] += 1
        ph = st["phase"]
        if ph == "end":
            return endscr.tick()
        if st["tick"] > CAP_TICKS - 120:
            clear(0)
            endscr.start(st["score"])
            st["phase"] = "end"
            return False
        if ph == "intro":
            st["t"] += 1
            if st["t"] > 75:
                start_play()
        elif ph == "play":
            w, bot = st["world"], st["bot"]
            st["lvl_ticks"] += 1
            bot.tick()
            for _ in range(bot.ff):
                w.step()
            if st["lvl_ticks"] > 30 * 170 and not w.nuked:
                w.nuke()
            cam = bot.cam()
            over = None
            wx, wy = bot.cx + cam, bot.cy
            for l in w.lems:
                if abs(l.x - wx) <= 7 and -2 <= (l.y - 5) - wy <= 6 and l.st not in DYING:
                    over = l
                    break
            rend.render(w, cam, (bot.cx, bot.cy, over is not None), LABEL.get(over.st) if over else None)
            if w.finished():
                level_result()
        elif ph == "result":
            st["t"] += 1
            if st["t"] > 110:
                st["n"] += 1
                if st["n"] >= len(order) or st["tick"] > 30 * 60 * 6.2:
                    clear(0)
                    endscr.start(st["score"])
                    st["phase"] = "end"
                else:
                    level_intro()
        return False
    return step
