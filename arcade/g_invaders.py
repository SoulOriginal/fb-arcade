# Space Invaders played by an expert bot. Game pixels are K=4 screen pixels; the 224x256 playfield
# is centred on the 1920x1080 screen (black pillarboxes), colours follow the cellophane overlay.
from fbcore import *

B = load_bundle("g_invaders.bin")
K = 4
FW, FH = 224, 256
X0, Y0 = (W - FW * K) // 2, 28
WHITE_ZONES = 4
RED_ZONE, GREEN_ZONE = 4, 5
GREEN565 = rgb565(70, 255, 70)
ZONE_RGB565 = [rgb565(255, 255, 255), rgb565(120, 255, 255), rgb565(255, 255, 120), rgb565(230, 170, 255),
               rgb565(255, 48, 48), GREEN565]

PY = 216                  # top of the cannon
GROUND = 239
SY = 192                  # top of the shields
SHIELD_X = [34, 79, 124, 169]
SW, SH = 22, 16
CEIL = 24                 # shots die here (below the header)
UFO_Y = 26
PX_LO, PX_HI = 2, 209
PSPEED = 3
SHOT_V = 12
TARGET_SCORE = 10000
POINTS = [30, 20, 10]     # squid, crab, octopus
BODY_W = [8, 11, 12]
UFO_TABLE = [100, 50, 50, 100, 150, 100, 100, 50, 300, 100, 100, 100, 50, 150, 100]
BOMB_SPEED = [2.4, 3.2, 3.0]
START_Y = [128, 136, 144, 152, 160, 168]
HI = 0

SHIELD_MASK = [[1 if c == "X" else 0 for c in row] for row in B["shield_mask"]]
SHIELD_ON = GREEN565.to_bytes(2, "little") * K
SHIELD_OFF = bytes(2 * K)


def zone(gy, wave):
    if gy < 64:
        return RED_ZONE
    if gy >= 184:
        return GREEN_ZONE
    return (wave - 1) % WHITE_ZONES


def blit_g(sp, gx, gy):
    blit(sp, X0 + gx * K, Y0 + gy * K)


def blit_clip(sp, gx, gy):
    # Sprites sliding in from the playfield edge must not show up in the pillarbox.
    w, h, rows = sp
    c0, c1 = max(0, -gx), min(w // K, FW - gx)
    if c1 <= c0:
        return
    if c0 == 0 and c1 == w // K:
        blit_g(sp, gx, gy)
        return
    for j in range(h):
        write_row(Y0 + gy * K + j, rows[j][c0 * K * 2:c1 * K * 2], X0 + (gx + c0) * K)


def erase_g(gx, gy, gw, gh):
    fill_rect(X0 + gx * K, Y0 + gy * K, gw * K, gh * K, 0)


class Game:
    def __init__(self):
        global HI
        self.t = 0
        self.score = 0
        self.lives = 3
        self.wave = 0
        self.extra_given = False
        self.shots = 0
        self.last_shot_t = 0
        self.end = EndScreen()
        self.phase = "play"
        self.fx = []
        self.ufo_text = None
        clear()
        fill_rect(X0, Y0 + GROUND * K, FW * K, K, GREEN565)
        draw_text("SCORE<1>", X0 + 24, Y0)
        draw_text("HI-SCORE", X0 + (FW * K - 192) // 2, Y0)
        draw_text("WAVE", X0 + FW * K - 120, Y0)
        self.shown = {}
        self.new_wave()

    # ---- setup ---------------------------------------------------------------------------------
    def new_wave(self):
        self.wave += 1
        base_y = START_Y[(self.wave - 1) % len(START_Y)]
        self.ax = [24 + (i % 11) * 16 for i in range(55)]
        self.ay = [base_y - (i // 11) * 16 for i in range(55)]
        self.kind = [2 if i < 22 else 1 if i < 44 else 0 for i in range(55)]
        self.alive = [True] * 55
        self.frame = [0] * 55
        self.nalive = 55
        self.last_alive = 54
        self.ptr = 0
        self.sign = 1
        self.dropping = False
        self.bombs = []
        self.shot = None
        self.shot_drawn = None
        self.ufo = None
        self.ufo_timer = 420
        self.ufo_dir = 1
        self.fire_timer = 40
        self.next_bomb = 0
        self.fx = []
        self.px = 105
        self.invuln = 0
        self.phase = "play"
        fill_rect(X0, Y0 + 22 * K, FW * K, (GROUND - 22) * K, 0)
        self.shields = [bytearray(v for row in SHIELD_MASK for v in row) for _ in SHIELD_X]
        for si in range(4):
            self.draw_shield(si, 0, SW - 1, 0, SH - 1)
        for i in range(55):
            self.draw_alien(i)
        self.draw_player()
        self.draw_lives()
        self.hud()

    def hud(self):
        global HI
        HI = max(HI, self.score)
        for key, text, x, y in (("score", "%04d" % self.score, X0 + 48, Y0 + 44),
                                ("hi", "%04d" % HI, X0 + (FW * K - 192) // 2 + 24, Y0 + 44),
                                ("wave", "%02d" % self.wave, X0 + FW * K - 96, Y0 + 44)):
            if self.shown.get(key) != text:
                self.shown[key] = text
                draw_text(text, x, y, color=COLOR_GREEN if key == "wave" else COLOR_WHITE)

    def draw_lives(self):
        fill_rect(X0, Y0 + 242 * K, 200 * K, 14 * K, 0)
        draw_text(str(self.lives), X0 + 24, Y0 + 242 * K, color=COLOR_GREEN)
        for k in range(max(0, self.lives - 1)):
            blit_g(B["player"], 22 + k * 16 - 4, 244)

    # ---- shields -------------------------------------------------------------------------------
    def draw_shield(self, si, x0, x1, y0, y1):
        sh = self.shields[si]
        sx = SHIELD_X[si]
        for ly in range(y0, y1 + 1):
            row = b"".join([SHIELD_ON if sh[ly * SW + lx] else SHIELD_OFF for lx in range(x0, x1 + 1)])
            sy = Y0 + (SY + ly) * K
            for k in range(K):
                write_row(sy + k, row, X0 + (sx + x0) * K)

    def shield_at(self, gx, gy):
        # Index and local coordinates of the shield pixel under a game pixel, or None.
        if not SY <= gy < SY + SH:
            return None
        for si, sx in enumerate(SHIELD_X):
            if sx <= gx < sx + SW:
                return si, gx - sx, gy - SY
        return None

    def erode(self, si, cx, cy, r):
        sh = self.shields[si]
        x0, x1 = max(0, int(cx - r) - 1), min(SW - 1, int(cx + r) + 1)
        y0, y1 = max(0, int(cy - r) - 1), min(SH - 1, int(cy + r) + 1)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                d = (x - cx) ** 2 + (y - cy) ** 2
                if d <= r * r * 0.5 or (d <= r * r and random.random() < 0.6):
                    sh[y * SW + x] = 0
        self.draw_shield(si, x0, x1, y0, y1)

    def column_blocked(self, gx):
        got = self.shield_at(gx, SY)
        if got is None:
            return False
        si, lx, _ = got
        sh = self.shields[si]
        return any(sh[ly * SW + lx] for ly in range(SH))

    def alien_clears_shields(self, x0, y0, x1, y1):
        # Aliens wipe whatever shield pixels they touch; the bitmap is redrawn before the alien is.
        for si, sx in enumerate(SHIELD_X):
            lx0, lx1 = max(0, x0 - sx), min(SW - 1, x1 - 1 - sx)
            ly0, ly1 = max(0, y0 - SY), min(SH - 1, y1 - 1 - SY)
            if lx0 > lx1 or ly0 > ly1:
                continue
            sh = self.shields[si]
            for ly in range(ly0, ly1 + 1):
                for lx in range(lx0, lx1 + 1):
                    sh[ly * SW + lx] = 0
            self.draw_shield(si, lx0, lx1, ly0, ly1)

    # ---- drawing helpers -----------------------------------------------------------------------
    def draw_alien(self, i):
        blit_g(B["alien"][self.kind[i]][self.frame[i]][zone(self.ay[i], self.wave)], self.ax[i], self.ay[i])

    def draw_player(self):
        blit_g(B["player"], self.px - 4, PY)

    def add_fx(self, life, gx, gy, gw, gh):
        self.fx.append((self.t + life, gx, gy, gw, gh))

    def expire_fx(self):
        if self.fx and any(f[0] <= self.t for f in self.fx):
            for f in [f for f in self.fx if f[0] <= self.t]:
                erase_g(f[1], f[2], f[3], f[4])
            self.fx = [f for f in self.fx if f[0] > self.t]

    # ---- the bot -------------------------------------------------------------------------------
    def bottoms(self):
        out = []
        for c in range(11):
            for r in range(5):
                if self.alive[r * 11 + c]:
                    out.append(r * 11 + c)
                    break
        return out

    def threats(self):
        out = []
        for kind, x, y, v in self.bombs:
            n_lo = max(0, int((PY - 7 - y) / v))
            n_hi = int((PY + 8 - y) / v) + 1
            if n_hi < 0 or n_lo > 45 or self.bomb_absorbed(x, y):
                continue
            out.append((x, n_lo, n_hi))
        return out

    def bomb_absorbed(self, x, y):
        # A bomb above intact shield pixels in its columns never reaches the cannon.
        row0 = max(0, int(y) + 7 - SY)
        for si, sx in enumerate(SHIELD_X):
            if x + 3 <= sx or x >= sx + SW:
                continue
            sh = self.shields[si]
            for lx in range(max(0, x - sx), min(SW, x + 3 - sx)):
                if any(sh[ly * SW + lx] for ly in range(row0, SH)):
                    return True
        return False

    def hidden(self, p):
        for si, sx in enumerate(SHIELD_X):
            if sx <= p + 1 and p + 12 <= sx + SW:
                sh = self.shields[si]
                if all(any(sh[ly * SW + lx] for ly in range(6)) for lx in range(p + 1 - sx, p + 12 - sx)):
                    return True
        return False

    def plan_position(self, aim, threats):
        # Pick the reachable standing position that dodges every bomb already falling and is closest
        # to where the gun wants to be; positions under intact shields are preferred while bombs fly.
        px = self.px
        cands = set(range(px % PSPEED + (PX_LO // PSPEED) * PSPEED, PX_HI + 1, PSPEED))
        cands.update((PX_LO, PX_HI, px))
        cands = [c for c in cands if PX_LO <= c <= PX_HI]
        near_bombs = any(PY - y < 90 for _, _, y, _ in self.bombs)
        best = None
        for tx in cands:
            dist = abs(tx - px)
            sgn = 1 if tx >= px else -1
            hits = 0
            for bx, n_lo, n_hi in threats:
                for n in range(n_lo, n_hi + 1):
                    p = px + sgn * min(PSPEED * n, dist)
                    if p - 2 < bx + 3 and p + 15 > bx:
                        hits += 1
                        break
            cost = abs(tx - aim) + 0.15 * dist
            if near_bombs and self.hidden(tx):
                cost -= 10
            key = (hits, cost)
            if best is None or key < best[0]:
                best = (key, tx)
        return best[1]

    def bot(self):
        # Returns (target x for the cannon's left edge, fire flag evaluated after moving).
        n = self.nalive
        gun = self.px + 6
        pc = [0] * 56
        for i in range(55):
            pc[i + 1] = pc[i] + self.alive[i]
        rp = pc[self.ptr]
        speed = 3 if n == 1 else 2
        dxs = 0 if self.dropping else self.sign * speed
        flight_top = PY - 4
        wait = (self.shot[1] - CEIL) / SHOT_V if self.shot else 0.0

        def alien_x(i, ticks):
            ahead = (pc[i] - rp) % n
            u = int(2 * ticks)
            moves = 0 if u <= ahead else 1 + (u - ahead - 1) // n
            return self.ax[i] + (16 - BODY_W[self.kind[i]]) // 2 + dxs * moves

        targets = []   # (left_pred(ticks), width, flight_ticks, bonus)
        for i in self.bottoms():
            flight = (flight_top - (self.ay[i] + 8)) / SHOT_V
            targets.append((lambda tk, i=i: alien_x(i, tk), BODY_W[self.kind[i]], flight,
                            -(self.ay[i] - 60) / 10.0, False))
        if self.ufo is not None:
            value = UFO_TABLE[(self.shots + 1) % 15]
            ux, ud = self.ufo
            if value >= 100 and 0 <= ux + 12 <= FW:
                flight = (flight_top - (UFO_Y + 8)) / SHOT_V
                targets.append((lambda tk: ux + 4 + ud * 2 * tk, 16, flight, value / 12.0, True))

        def aim_for(tgt):
            left, width, flight, bonus, _ = tgt
            tm = 0.0
            g = gun
            for _ in range(3):
                g = left(max(tm, wait) + flight) + width // 2
                tm = abs(g - 6 - self.px) / PSPEED
            return g, max(tm, wait) + 0.5 * flight - bonus

        best = None
        for relax in (False, True):
            for tgt in targets:
                g, cost = aim_for(tgt)
                if not PX_LO + 6 <= g <= PX_HI + 6:
                    continue
                if not relax and self.column_blocked(int(g)):
                    continue
                if best is None or cost < best[0]:
                    best = (cost, g)
            if best:
                break
        aim = int(best[1]) - 6 if best else 105
        aim = max(PX_LO, min(PX_HI, aim))
        tx = self.plan_position(aim, self.threats())
        step = max(-PSPEED, min(PSPEED, tx - self.px))

        fire = False
        if self.shot is None:
            g = self.px + step + 6
            stalled = self.t - self.last_shot_t > 150
            for left, width, flight, _, is_ufo in targets:
                if left(flight) + 1 <= g <= left(flight) + width - 2:
                    if stalled or not self.column_blocked(g):
                        fire = True
                        break
        return step, fire

    # ---- the game ------------------------------------------------------------------------------
    def kill_alien(self, i):
        self.alive[i] = False
        self.nalive -= 1
        self.score += POINTS[self.kind[i]]
        ax, ay = self.ax[i], self.ay[i]
        erase_g(ax, ay, 16, 8)
        blit_g(B["alien_explosion"][zone(ay, self.wave)], ax, ay)
        self.add_fx(8, ax, ay, 16, 8)
        self.last_alive = max((j for j in range(55) if self.alive[j]), default=0)
        if self.nalive == 0:
            self.phase = "clear"
            self.clear_t = 0

    def move_shot(self):
        s = self.shot
        x = s[0]
        if self.shot_drawn is not None:
            erase_g(x, self.shot_drawn, 1, 4)
            self.shot_drawn = None
        y = s[1]
        rack_top, rack_bottom = min(self.ay), max(self.ay) + 8
        for _ in range(SHOT_V):
            y -= 1
            if y <= CEIL:
                self.shot = None
                self.add_fx(8, x - 3, CEIL - 2, 8, 8)
                blit_g(B["shot_burst"][RED_ZONE], x - 3, CEIL - 2)
                return
            got = self.shield_at(x, y)
            if got and self.shields[got[0]][got[2] * SW + got[1]]:
                self.erode(got[0], got[1], got[2], 2.8)
                self.shot = None
                return
            for b in self.bombs:
                if b[1] <= x < b[1] + 3 and b[2] < y + 4 and b[2] + 7 > y:
                    erase_g(b[1], int(b[2]), 3, 7)
                    self.bombs.remove(b)
                    self.shot = None
                    return
            if self.ufo is not None and UFO_Y <= y < UFO_Y + 8 and self.ufo[0] + 4 <= x < self.ufo[0] + 20:
                self.hit_ufo()
                self.shot = None
                return
            if rack_top <= y < rack_bottom:
                for i in range(55):
                    if self.alive[i]:
                        left = self.ax[i] + (16 - BODY_W[self.kind[i]]) // 2
                        if left <= x < left + BODY_W[self.kind[i]] and self.ay[i] <= y < self.ay[i] + 8:
                            self.kill_alien(i)
                            self.shot = None
                            return
        s[1] = y
        self.shot_drawn = y
        fill_rect(X0 + x * K, Y0 + y * K, K, 4 * K, ZONE_RGB565[zone(y, self.wave)])

    def hit_ufo(self):
        ux = self.ufo[0]
        value = UFO_TABLE[self.shots % 15]
        self.score += value
        self.ufo = None
        erase_g(max(0, ux), UFO_Y - 1, min(24, FW - max(0, ux)), 10)
        blit_clip(B["ufo_explosion"][RED_ZONE], ux, UFO_Y)
        self.fx.append((self.t + 10, max(0, ux), UFO_Y, 24, 8))
        self.ufo_text = (self.t + 36, str(value), max(0, min(ux, FW - 18)))
        self.ufo_timer = 600

    def update_ufo(self):
        if self.ufo is None:
            self.ufo_timer -= 1
            if self.ufo_timer <= 0 and self.nalive >= 8:
                self.ufo_dir = -self.ufo_dir
                self.ufo = [-20 if self.ufo_dir > 0 else FW - 4, self.ufo_dir]
            return
        self.ufo[0] += 2 * self.ufo[1]
        if self.ufo[0] < -24 or self.ufo[0] > FW:
            erase_g(0 if self.ufo[0] < 0 else FW - 24, UFO_Y, 24, 8)
            self.ufo = None
            self.ufo_timer = 600
            return
        blit_clip(B["ufo"][RED_ZONE], self.ufo[0], UFO_Y)

    def update_ufo_text(self):
        pending = self.ufo_text
        if pending is None:
            return
        until, text, gx = pending
        if self.t == until - 35:
            draw_text(text, X0 + gx * K, Y0 + UFO_Y * K - 8, color=COLOR_RED)
        if self.t >= until:
            erase_g(gx, UFO_Y - 2, 18, 12)
            self.ufo_text = None

    def update_aliens(self):
        for _ in range(2):
            if self.nalive == 0 or self.phase != "play":
                return
            i = self.ptr
            while not self.alive[i]:
                i = (i + 1) % 55
            self.move_alien(i)
            if i >= self.last_alive:
                self.end_sweep()
            else:
                self.ptr = i + 1

    def move_alien(self, i):
        ax, ay = self.ax[i], self.ay[i]
        speed = 3 if self.nalive == 1 else 2
        if self.dropping:
            erase_g(ax, ay, 16, 8)
            ay += 8
            self.ay[i] = ay
        elif self.sign > 0:
            erase_g(ax, ay, speed, 8)
            ax += speed
            self.ax[i] = ax
        else:
            ax -= speed
            self.ax[i] = ax
            erase_g(ax + 16, ay, speed, 8)
        self.frame[i] ^= 1
        if ay + 8 > SY:
            self.alien_clears_shields(ax - 3, ay, ax + 19, ay + 8)
        self.draw_alien(i)
        if ay + 8 >= PY:
            self.game_over()

    def end_sweep(self):
        self.ptr = 0
        if self.dropping:
            self.dropping = False
            return
        for i in range(55):
            if self.alive[i]:
                left = self.ax[i] + (16 - BODY_W[self.kind[i]]) // 2
                if (self.sign > 0 and left + BODY_W[self.kind[i]] >= FW - 3) or (self.sign < 0 and left <= 3):
                    self.dropping = True
                    self.sign = -self.sign
                    return

    def spawn_bomb(self):
        bottoms = self.bottoms()
        if not bottoms:
            return
        for _ in range(3):
            kind = self.next_bomb
            self.next_bomb = (self.next_bomb + 1) % 3
            if all(b[0] != kind for b in self.bombs):
                break
        else:
            return
        if kind == 0:
            gun = self.px + 6
            i = min(bottoms, key=lambda j: abs(self.ax[j] + 8 - gun))
        else:
            i = random.choice(bottoms)
        speed = BOMB_SPEED[kind] * (1 + 0.05 * (self.wave - 1))
        self.bombs.append([kind, self.ax[i] + 7, float(self.ay[i] + 8), speed])

    def update_bombs(self):
        for b in self.bombs[:]:
            kind, x, y, v = b
            ny = y + v
            for yy in range(int(y) + 1, int(ny) + 1):
                if yy + 7 >= GROUND:
                    self.bomb_gone(b, int(y))
                    blit_g(B["splat"], x - 2, GROUND - 4)
                    self.add_fx(6, x - 2, GROUND - 4, 8, 4)
                    break
                got = None
                for cx in range(x, x + 3):
                    got = self.shield_at(cx, yy + 6)
                    if got and self.shields[got[0]][got[2] * SW + got[1]]:
                        break
                    got = None
                if got:
                    self.bomb_gone(b, int(y))
                    self.erode(got[0], got[1], got[2] + 1, 3.3)
                    break
                if (self.phase == "play" and not self.invuln and x < self.px + 13 and x + 3 > self.px + 1
                        and yy + 7 > PY and yy < PY + 8):
                    self.bomb_gone(b, int(y))
                    self.kill_player()
                    return
            else:
                b[2] = ny
                strip = int(ny) - int(y)
                if strip > 0:
                    erase_g(x, int(y), 3, strip)
                blit_g(B["bomb"][kind][(self.t // 2 + kind) % 4][zone(int(ny), self.wave)], x, int(ny))

    def bomb_gone(self, b, y):
        self.bombs.remove(b)
        erase_g(b[1], y, 3, 7)

    def kill_player(self):
        self.phase = "dying"
        self.die_t = 0

    def update_dying(self):
        self.die_t += 1
        blit_g(B["player_explosion"][(self.die_t // 4) % 2], self.px - 4, PY)
        if self.die_t < 64:
            return
        self.lives -= 1
        erase_g(self.px - 4, PY, 21, 8)
        if self.lives <= 0:
            self.draw_lives()
            self.game_over()
            return
        for b in self.bombs:
            erase_g(b[1], int(b[2]), 3, 7)
        self.bombs = []
        if self.shot_drawn is not None:
            erase_g(self.shot[0], self.shot_drawn, 1, 4)
        self.shot = None
        self.shot_drawn = None
        self.px = 105
        self.invuln = 45
        self.phase = "play"
        self.draw_player()
        self.draw_lives()

    def game_over(self):
        if self.phase != "over":
            self.phase = "over"
            self.over_t = 0

    # ---- one tick ------------------------------------------------------------------------------
    def step(self):
        self.t += 1
        if self.phase == "end":
            return self.end.tick()
        if self.t >= CAP_TICKS - 60 or self.score >= TARGET_SCORE:
            self.game_over()
        if self.phase == "over":
            self.over_t += 1
            self.expire_fx()
            if self.over_t >= 60:
                self.hud()
                self.end.start(self.score)
                self.phase = "end"
            return False
        self.expire_fx()
        self.update_ufo_text()
        if self.phase == "dying":
            self.update_dying()
            return False
        if self.phase == "clear":
            self.clear_t += 1
            if self.shot is not None:
                self.move_shot()
            if self.clear_t > 45:
                self.new_wave()
            return False

        step, fire = self.bot()
        if self.invuln:
            self.invuln -= 1
        if step:
            self.px += step
            self.draw_player()
        if fire:
            self.shot = [self.px + 6, PY - 4]
            self.shots += 1
            self.last_shot_t = self.t
        if self.shot is not None:
            self.move_shot()
        self.update_aliens()
        if self.phase != "play":
            return False
        self.update_bombs()
        if self.phase != "play":
            return False
        self.update_ufo()
        self.fire_timer -= 1
        if self.fire_timer <= 0:
            self.spawn_bomb()
            base = max(14, 38 - 3 * (self.wave - 1))
            self.fire_timer = int(base * (0.7 if self.nalive <= 8 else 1.0) * random.uniform(0.7, 1.3))
        if not self.extra_given and self.score >= 1500:
            self.extra_given = True
            self.lives += 1
            self.draw_lives()
        self.hud()
        return False


def make():
    return Game().step
