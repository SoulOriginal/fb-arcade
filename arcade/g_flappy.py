# Flappy Bird played by a physics-lookahead bot. Native 144x256 play field drawn 4x (576x1024) in the screen centre.
from fbcore import *
import math

B = load_bundle("g_flappy.bin")

X0, Y0, PW, PH, SC = 672, 28, 576, 1024, 4
RB = PW * 2
BASE = Y0 * S + X0 * 2

# Physics in native pixels per 60 Hz frame (constants of the 288x512 HTML5 clone halved); one game tick is two frames.
GRAVITY, FLAP_V, FALL_CAP = 0.125, -2.3, 4.0
PIPE_SPEED, PIPE_SPACING, PIPE_W, GAP = 1.222, 102.0, 26, 48
GAP_TOP_MIN, GAP_TOP_MAX = 38, 114
GROUND = 200
BIRD_X, BIRD_W, BIRD_H = 48, 17, 12
LAYER_PERIOD, HATCH_PERIOD = 288, 12
LAYER_SPEED = 0.3            # city layer moves at 0.3x of the ground, as in the clone (39 vs 133 px/s)
READY_TICKS = 60
# A pipe moves about 10 screen px per tick; the flat-colour strip behind it must be wider than one step.
SLIVER = 16
SCORE_BOX = (128, 56, 448, 144)   # x0, y0, x1, y1 in play-field screen px: the erase area of the big score

BODY, CAP = B["pipe"]["body"], B["pipe"]["cap"]
ANGLES = B["angles"]
BIRD_FRAMES = (0, 1, 2, 1)
MEDALS = ((40, "platinum"), (30, "gold"), (20, "silver"), (10, "bronze"))
YELLOW_BIAS = ("yellow", "yellow", "red", "blue")


class Theme:
    # Everything that depends on day/night, expanded once into play-field sized rows.
    def __init__(self, d):
        self.side = d["side"]
        self.rowfull = []
        self.static = []
        for r in range(256):
            col = d["rowcol"][r]
            full = col * PW if col else None
            self.rowfull += [full] * 4
            self.static += [col is not None] * 4
        self.lay = [(r * 4, strip) for r, strip in sorted(d["lay"].items())]
        self.gnd = [(r * 4, strip) for r, strip in sorted(d["gnd"].items())]
        # Runs of equal kind above the ground, used to know where a pipe's trailing sliver can be erased with a flat colour.
        self.kruns = []
        y = 0
        while y < GROUND * 4:
            col = d["rowcol"][y // 4]
            e = y
            while e < GROUND * 4 and d["rowcol"][e // 4] == col:
                e += 4
            self.kruns.append((y, e, (col * SLIVER) if col else None))
            y = e


THEMES = {k: Theme(B[k]) for k in ("day", "night")}


def put(sp, x, y):
    # Blit a run sprite with its origin at play-field screen px (x, y); lines past the play field bottom are skipped.
    x0, y0, h, rows = sp[0], sp[1], sp[2], sp[3]
    o = BASE + (y + y0) * S + x * 2
    ya = y + y0
    for row in rows:
        if 0 <= ya < PH:
            for xo, b in row:
                fb[o + xo:o + xo + len(b)] = b
        o += S
        ya += 1


def put_centered(sp, cx, y):
    put(sp, cx - (sp[0] + sp[4] // 2), y)


def write_sides(theme):
    rows = theme.side
    for r in range(270):
        row = rows[r]
        for k in range(4):
            y = r * 4 + k
            if Y0 <= y < Y0 + PH:
                o = y * S
                fb[o:o + X0 * 2] = row[:X0 * 2]
                fb[o + (X0 + PW) * 2:o + S] = row[(X0 + PW) * 2:]
            else:
                fb[y * S:(y + 1) * S] = row


def make():
    st = {}
    big = B["digits"]
    small = B["small"]
    best = 0
    total = 0
    target = random.randint(170, 235)
    rnd = random.Random()

    # ---- drawing --------------------------------------------------------------------------------------------
    def draw_scenery(th, lay_off, gnd_off):
        a, g = lay_off * 8, gnd_off * 8
        for y4, strip in th.lay:
            seg = strip[a:a + RB]
            o = BASE + y4 * S
            fb[o:o + RB] = seg
            fb[o + S:o + S + RB] = seg
            fb[o + 2 * S:o + 2 * S + RB] = seg
            fb[o + 3 * S:o + 3 * S + RB] = seg
        for y4, strip in th.gnd:
            seg = strip[g:g + RB]
            o = BASE + y4 * S
            fb[o:o + RB] = seg
            fb[o + S:o + S + RB] = seg
            fb[o + 2 * S:o + 2 * S + RB] = seg
            fb[o + 3 * S:o + 3 * S + RB] = seg

    def draw_static_rows(th):
        rf = th.rowfull
        for y in range(PH):
            r = rf[y]
            if r is not None:
                o = BASE + y * S
                fb[o:o + RB] = r

    def erase_box(th, x0, y0, x1, y1):
        rf, o = th.rowfull, BASE + y0 * S + x0 * 2
        for y in range(max(y0, 0), min(y1, PH)):
            r = rf[y]
            if r is not None:
                fb[o:o + (x1 - x0) * 2] = r[x0 * 2:x1 * 2]
            o += S

    def pipe_runs(gap_top):
        # Per pipe: (first line, last line, row bytes, x offset, width) runs; caps are 4 identical lines each.
        runs = []
        body_h = (gap_top - 13) * 4
        runs.append((0, body_h, BODY, 8, 88))
        for i, row in enumerate(CAP):
            runs.append((body_h + i * 4, body_h + i * 4 + 4, row, 0, 104))
        gb = (gap_top + GAP) * 4
        for i, row in enumerate(CAP):
            runs.append((gb + i * 4, gb + i * 4 + 4, row, 0, 104))
        runs.append((gb + 52, GROUND * 4, BODY, 8, 88))
        return runs

    def draw_pipe(th, p):
        sx = int(round(p[0] * 2)) * 2
        for ys, ye, data, xoff, wpx in p[3]:
            left = sx + xoff
            right = left + wpx
            da, db = max(left, 0), min(right, PW)
            sa, sb = max(right, 0), min(right + SLIVER, PW)
            d = data[(da - left) * 2:(db - left) * 2] if db > da else b""
            for ka, kb, sl in th.kruns:
                if kb <= ys:
                    continue
                if ka >= ye:
                    break
                a, b = max(ka, ys), min(kb, ye)
                buf, start = d, da
                if sl is not None and sb > sa:
                    if d:
                        buf = d + sl[:(sb - sa) * 2]
                    else:
                        buf, start = sl[:(sb - sa) * 2], sa
                if not buf:
                    continue
                o = BASE + a * S + start * 2
                n = len(buf)
                for _ in range(b - a):
                    fb[o:o + n] = buf
                    o += S

    def bird_geometry():
        ang = st["rot"]
        i = min(range(len(ANGLES)), key=lambda k: abs(ANGLES[k] - ang))
        fr = BIRD_FRAMES[st["wing"] % 4] if st["flying"] else 1
        sp = B["bird"][st["colour"]][i][fr]
        qy = int(round(st["y"] * 2)) * 2
        return sp, qy - 48

    def draw_bird():
        sp, oy = bird_geometry()
        put(sp, BIRD_X * 4 - 48, oy)
        st["bird_rows"] = (oy, oy + 96)

    def draw_score():
        s = str(st["score"])
        pitch = 13
        total_w = (len(s) - 1) * pitch + 16
        x = int((72 - total_w / 2) * 4)
        for i, ch in enumerate(s):
            put(big[int(ch)], x + i * pitch * 4, 14 * 4)

    def render(full):
        th = st["theme"]
        if full:
            draw_static_rows(th)
        elif st["bird_rows"]:
            erase_box(th, BIRD_X * 4 - 48, st["bird_rows"][0], BIRD_X * 4 + 48, st["bird_rows"][1])
        near = False
        for p in st["pipes"]:
            sx = int(round(p[0] * 2)) * 2
            if sx < SCORE_BOX[2] + 16 and sx + 104 > SCORE_BOX[0] - 16:
                near = True
        if st["score_dirty"] or near or st["near_prev"] or full:
            erase_box(th, *SCORE_BOX)
        draw_scenery(th, int(st["lay_pos"]) % LAYER_PERIOD, int(st["gnd_pos"]) % HATCH_PERIOD)
        for p in st["pipes"]:
            draw_pipe(th, p)
        if st["score_dirty"] or near or st["near_prev"] or full:
            draw_score()
        st["near_prev"] = near
        st["score_dirty"] = False
        if st["phase"] == "ready":
            put_centered(B["get_ready"], PW // 2, 50 * 4)
            put(B["tap"], 86 * 4, 104 * 4)
        draw_bird()

    def flash():
        row = c_white * PW
        for y in range(PH):
            o = BASE + y * S
            fb[o:o + RB] = row

    c_white = rgb565(255, 255, 255).to_bytes(2, "little")

    # ---- game logic -------------------------------------------------------------------------------------------
    def new_run():
        theme = rnd.choice(("day", "day", "night"))
        st.update(theme=THEMES[theme], colour=rnd.choice(YELLOW_BIAS), phase="ready", t=0, y=104.0, v=0.0, rot=0.0,
                  wing=0, flying=True, pipes=[], score=0, score_dirty=True, near_prev=False, bird_rows=None,
                  lay_pos=rnd.random() * LAYER_PERIOD, gnd_pos=0.0, cooldown=0, delay=None, failed=False,
                  fail_at=plan_failure(), fail_mode=0, bias=10.0, last_target=None, dead_tick=0)
        write_sides(st["theme"])
        render(True)

    def plan_failure():
        # The run ends at a pipe index drawn from a long-tailed spread: mostly dozens of pipes, now and then a quick fail.
        n = int(rnd.lognormvariate(math.log(42), 0.65))
        return max(4, min(n, 150))

    def box():
        r = abs(st["rot"])
        bw = BIRD_W - math.sin(r / 90.0) * 4
        rad = math.radians(r)
        bh = (BIRD_H + BIRD_H * math.cos(rad) + BIRD_W * math.sin(rad)) / 2
        return bw, bh

    def bot_wants_flap():
        y, v = st["y"], st["v"]
        target = None
        for p in st["pipes"]:
            if not p[2]:
                target = p
                break
        if target is None:
            aim = 100.0
        else:
            if target is not st["last_target"]:
                st["last_target"] = target
                st["bias"] = rnd.uniform(8.5, 12.5)
                st["fail_mode"] = 0
                if st["score"] >= st["fail_at"] and not st["failed"]:
                    st["fail_mode"] = rnd.choice((34, 34, -44))
                    st["failed"] = True
            aim = target[1] + GAP / 2 + st["bias"] + st["fail_mode"]
        ny = y + min(v + GRAVITY, FALL_CAP)
        return ny > aim

    def physics_frame():
        # One 60 Hz frame of the original loop: bird first, then pipes and scenery.
        st["flapped"] = False
        if st["phase"] == "play" and st["cooldown"] > 0:
            st["cooldown"] -= 1
        if st["phase"] == "play" and st["cooldown"] == 0 and bot_wants_flap():
            if st["delay"] is None:
                st["delay"] = rnd.choice((0, 0, 0, 0, 0, 1, 1, 2))
            if st["delay"] == 0:
                st["v"] = FLAP_V
                st["cooldown"] = rnd.choice((5, 6, 6, 7))
                st["delay"] = None
            else:
                st["delay"] -= 1
        elif st["delay"] is not None and not bot_wants_flap():
            st["delay"] = None
        v = min(st["v"] + GRAVITY, FALL_CAP if st["phase"] != "dying" else 6.0)
        st["v"] = v
        st["y"] += v
        if st["phase"] == "play":
            st["rot"] = max(-25.0, min(v * 30.0, 90.0))
        else:
            st["rot"] = min(90.0, st["rot"] + 12.0)
        bw, bh = box()
        if st["y"] - bh / 2 <= 0:
            st["y"] = bh / 2
        if st["phase"] == "play":
            for p in st["pipes"]:
                p[0] -= PIPE_SPEED
            st["gnd_pos"] += PIPE_SPEED
            st["lay_pos"] += PIPE_SPEED * LAYER_SPEED
            if st["pipes"] and st["pipes"][0][0] < -PIPE_W - 12:
                st["pipes"].pop(0)
            if not st["pipes"] or st["pipes"][-1][0] + PIPE_SPACING <= 146:
                gt = rnd.randint(GAP_TOP_MIN, GAP_TOP_MAX)
                x = 146.0 if not st["pipes"] else st["pipes"][-1][0] + PIPE_SPACING
                st["pipes"].append([x, gt, False, pipe_runs(gt)])
            hit = False
            for p in st["pipes"]:
                left = p[0] - 1
                right = left + PIPE_W
                if BIRD_X - bw / 2 > right:
                    if not p[2]:
                        p[2] = True
                        st["score"] += 1
                        st["score_dirty"] = True
                        st["scored_now"] = True
                    continue
                if BIRD_X + bw / 2 > left:
                    top, bottom = st["y"] - bh / 2, st["y"] + bh / 2
                    if not (top > p[1] and bottom < p[1] + GAP):
                        hit = True
                break
            if st["y"] + bh / 2 >= GROUND:
                st["y"] = GROUND - bh / 2
                die(False)
            elif hit:
                die(True)
        elif st["phase"] == "dying":
            if st["y"] + bh / 2 >= GROUND:
                st["y"] = GROUND - bh / 2
                st["v"] = 0.0
                st["landed"] = True

    def die(pipe):
        st["phase"] = "dying"
        st["flying"] = False
        st["landed"] = False
        st["v"] = 0.0 if pipe else st["v"]
        st["dead_tick"] = 0

    # ---- end-of-run card ----------------------------------------------------------------------------------------
    def card_begin():
        nonlocal best
        old = best
        best = max(best, st["score"])
        st.update(phase="card", ct=0, shown=0, is_new=st["score"] > old, medal=None)
        for need, name in MEDALS:
            if st["score"] >= need:
                st["medal"] = name
                break

    def draw_number(value, right_x, y):
        s = str(value)
        x = right_x - len(s) * 6
        for i, ch in enumerate(s):
            put(small[int(ch)], (x + i * 6) * 4, y * 4)

    def compose_card(ct):
        render(True)
        # Lettering drops in with a small bounce, then the panel rises from below the screen.
        drop = (22, 30, 38, 44, 46, 44, 42, 42, 43, 44)
        put_centered(B["game_over"], PW // 2, drop[min(ct, len(drop) - 1)] * 4)
        pa = (ct - 6) / 12.0
        if pa <= 0:
            return
        u = 1 - (1 - min(pa, 1.0)) ** 3
        ox, oy = (PW - B["panel"][4]) // 2, int(256 * 4 + (92 * 4 - 256 * 4) * u)
        put(B["panel"], ox, oy)
        put(B["lbl_medal"], ox + 10 * 4, oy + 8 * 4)
        put(B["lbl_score"], ox + 72 * 4, oy + 8 * 4)
        put(B["lbl_best"], ox + 79 * 4, oy + 33 * 4)
        put(B["slot"], ox + 10 * 4, oy + 21 * 4)
        for i, ch in enumerate(str(st["shown"])):
            put(small[int(ch)], ox + (102 - len(str(st["shown"])) * 6 + i * 6) * 4, oy + 18 * 4)
        for i, ch in enumerate(str(best)):
            put(small[int(ch)], ox + (102 - len(str(best)) * 6 + i * 6) * 4, oy + 43 * 4)
        if st["shown"] >= st["score"]:
            if st["is_new"]:
                put(B["new"], ox + 48 * 4, oy + 44 * 4)
            if st["medal"]:
                put(B["medal"][st["medal"]], ox + 10 * 4, oy + 21 * 4)
        if ct > 26:
            put(B["ok"], 22 * 4, 162 * 4)
            put(B["share"], 74 * 4, 162 * 4)

    # ---- tick -------------------------------------------------------------------------------------------------------
    new_run()
    state = {"ticks": 0, "end": None}

    def step():
        nonlocal total
        state["ticks"] += 1
        if state["end"] is not None:
            return state["end"].tick()
        if state["ticks"] >= CAP_TICKS - 5:
            state["end"] = EndScreen()
            state["end"].start(total + st["score"])
            return False
        ph = st["phase"]
        if ph == "ready":
            st["t"] += 1
            st["y"] = 104 + 3 * math.sin(st["t"] / 4.0)
            st["wing"] = st["t"] // 4
            st["gnd_pos"] += PIPE_SPEED * 2
            st["lay_pos"] += PIPE_SPEED * 2 * LAYER_SPEED
            render(False)
            if st["t"] >= READY_TICKS:
                st["phase"] = "play"
                st["v"] = FLAP_V
                st["cooldown"] = 6
                render(True)
            return False
        if ph == "play":
            st["t"] += 1
            st["wing"] = st["t"] // 2
            st["scored_now"] = False
            for _ in range(2):
                physics_frame()
                if st["phase"] != "play":
                    break
            if st["scored_now"]:
                if total + st["score"] >= target:
                    render(False)
                    state["end"] = EndScreen()
                    state["end"].start(total + st["score"])
                    return False
            if st["phase"] == "dying":
                flash()
                st["need_full"] = True
            else:
                render(False)
            return False
        if ph == "dying":
            for _ in range(2):
                physics_frame()
            st["dead_tick"] += 1
            render(st.pop("need_full", False))
            if st["landed"] and st["dead_tick"] > 14:
                total += st["score"]
                card_begin()
                compose_card(0)
            return False
        if ph == "card":
            st["ct"] += 1
            ct = st["ct"]
            if ct > 18 and st["shown"] < st["score"]:
                st["shown"] = min(st["score"], st["shown"] + max(1, st["score"] // 25))
            if ct <= 40 or st["shown"] < st["score"]:
                compose_card(ct)
            elif st["medal"] and ct % 2 == 0:
                # The twinkle tiles are opaque, so after the card is settled only this tile is rewritten.
                ox, oy = (PW - B["panel"][4]) // 2, 92 * 4
                put(B["sparkle"][st["medal"]][(ct // 2) % 8], ox + 10 * 4, oy + 21 * 4)
            if ct > 40 + 75:
                if total >= target:
                    state["end"] = EndScreen()
                    state["end"].start(total)
                    return False
                new_run()
            return False
        return False

    return step
