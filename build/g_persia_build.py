# Build script for the Prince of Persia style game. Run from this directory: python3 g_persia_build.py
# Produces g_persia.bin: fighter sprite sequences (as opaque-run lists, already expanded 5x horizontally),
# tile cell images for two themes (already expanded 5x in both axes' row layout), HUD sprites and motion tables.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from array import array
from PIL import Image, ImageDraw
from buildlib import pack, save_bundle
import g_persia_rig as rig
import g_persia_poses as ps
import g_persia_tiles as tiles
from g_persia_rig import mirror_limbs

SCALE = 5


def fit(lst, n, pad=0.0):
    lst = list(lst)[:n]
    return lst + [pad] * (n - len(lst))


def rgb565_row(pixels):
    a = array("H", ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3) for r, g, b in pixels))
    return a.tobytes()


def expand(b, k=SCALE):
    # every 2-byte pixel is repeated k times
    out = bytearray(len(b) * k)
    for i in range(0, len(b), 2):
        px = b[i:i + 2]
        out[i * k:i * k + 2 * k] = px * k
    return bytes(out)


def sprite_from_image(img, anchor_x):
    """RGBA logical image -> [ox, oy, rows]; rows[y] is a flat list [x0, bytes, x1, bytes, ...] of opaque runs."""
    px = img.load()
    box = img.getchannel("A").point(lambda v: 255 if v else 0).getbbox()
    if box is None:
        return [0, 0, []]
    x0, y0, x1, y1 = box
    rows = []
    for y in range(y0, y1):
        runs = []
        x = x0
        while x < x1:
            if px[x, y][3]:
                s = x
                cols = []
                while x < x1 and px[x, y][3]:
                    cols.append(px[x, y][:3])
                    x += 1
                runs += [s - x0, expand(rgb565_row(cols))]
            else:
                x += 1
        rows.append(runs)
    return [x0 - anchor_x, y0 - rig.GY, rows]


def render_frames(poses, pal):
    r_list, l_list, hh = [], [], 0
    for p in poses:
        img, h = rig.render(p, pal, flip=False)
        r_list.append(sprite_from_image(img, rig.GX))
        img2 = img.transpose(Image.FLIP_LEFT_RIGHT)
        l_list.append(sprite_from_image(img2, rig.CW - 1 - rig.GX))
        hh = max(hh, h)
    return r_list, l_list, hh


def smooth_ramp(n, a, b, start, end):
    # absolute dy ramp from a to b between frame indices start..end (smoothstep), flat elsewhere
    out = []
    for i in range(n):
        if i <= start:
            out.append(a)
        elif i >= end:
            out.append(b)
        else:
            t = (i - start) / (end - start)
            t = t * t * (3 - 2 * t)
            out.append(a + (b - a) * t)
    return out


_, HH = rig.render(ps.HANG1, rig.PRINCE)
HH = round(HH, 1)

# name -> (poses, dx, dy, events)
SEQ = {}


def add(name, poses, dx=None, dy=None, **ev):
    n = len(poses)
    SEQ[name] = (poses, fit(dx if dx is not None else [0.0] * n, n), fit(dy if dy is not None else [0.0] * n, n), ev)


add("stand", [ps.stand])
add("start", ps.START, ps.START_DX)
add("run", ps.RUN_CYCLE, [ps.RUN_DX] * 16)
add("stop", ps.STOP, ps.STOP_DX)
add("stop_b", [mirror_limbs(p) for p in ps.STOP], ps.STOP_DX)
add("turn", ps.TURN, [0] * 7, flip=ps.TURN_FLIP)
add("runturn", ps.RUNTURN, ps.RUNTURN_DX, flip=ps.RUNTURN_FLIP)
add("step", ps.STEP, ps.STEP_DX)
add("standjump", ps.STAND_JUMP, ps.SJ_DX, ps.SJ_DY, takeoff=ps.SJ_TAKEOFF_AT, land=ps.SJ_LAND_AT)
add("runjump", ps.RUN_JUMP, ps.RJ_DX, ps.RJ_DY, takeoff=ps.RJ_TAKEOFF_AT, land=ps.RJ_LAND_AT)
add("runjump_b", [mirror_limbs(p) for p in ps.RUN_JUMP], ps.RJ_DX, ps.RJ_DY, takeoff=ps.RJ_TAKEOFF_AT, land=ps.RJ_LAND_AT)
nj = len(ps.JUMPUP)
add("jumpup", ps.JUMPUP, ps.JUMPUP_DX, smooth_ramp(nj, 0, HH - 61, 2, nj - 1))
npu = len(ps.PULLUP)
pu_dx = [0, 0, 0.5, 0.5, 1, 1, 1.5, 2, 2.5, 3, 3, 2, 1, 0.5][:npu]
add("pullup", ps.PULLUP, pu_dx, smooth_ramp(npu, 2 + HH, 0, 1, npu - 2))
ncd = len(ps.CLIMBDOWN)
cd_dx = [0, 0, 0, 0.5, 1, 1.5, -1, -2, -2, -3, -2, -2][:ncd]
add("climbdown", ps.CLIMBDOWN, cd_dx, smooth_ramp(ncd, 0, 2 + HH, 4, ncd - 1), flip=6)
add("hang", [ps.HANG1, ps.HANG2], [0, 0])
add("fall", ps.FALL, [0] * len(ps.FALL))
add("landsoft", ps.LAND_SOFT)
add("landhard", ps.LAND_HARD)
add("crouch", ps.CROUCH_SEQ)
add("rise", ps.RISE_SEQ)
add("die_fall", ps.DIE_FALL, [1.5, 2, 2, 1, 1, 0, 0][:len(ps.DIE_FALL)])
add("dead_fwd", [ps.DEAD_FWD])
add("dead_back", [ps.DEAD_BACK])
add("impaled", [ps.IMPALED])
add("pickup", ps.PICKUP)
add("draw", ps.DRAW, [0] * len(ps.DRAW))
add("sheathe", ps.SHEATHE, [0] * len(ps.SHEATHE))
for item in (1, 2, 3):
    add("drink%d" % item, ps.drink_seq(item))
add("eg", ps.IDLE_EG, [0] * len(ps.IDLE_EG))
add("advance", ps.ADVANCE, ps.ADVANCE_DX)
add("retreat", ps.RETREAT, ps.RETREAT_DX)
add("strike", ps.STRIKE, ps.STRIKE_DX, active=list(ps.STRIKE_ACTIVE))
add("parry", ps.PARRY, [0] * len(ps.PARRY), active=list(ps.PARRY_ACTIVE))
add("hit", ps.HIT_SEQ, ps.HIT_DX)
add("die", ps.DIE_SWORD, ps.DIE_SWORD_DX)
add("dead", [ps.DEAD_BACK])

PRINCE_ONLY = [k for k in SEQ]
FIGHT_SET = ["eg", "advance", "retreat", "strike", "parry", "hit", "die", "dead", "stand", "run", "stop", "turn", "step", "start",
             "fall", "landsoft", "dead_fwd", "impaled", "die_fall"]
VIZIER = rig.Palette(**{**rig.GUARD_RED.__dict__, "shirt": (88, 28, 110), "turban": (214, 176, 60), "vest": (44, 14, 60),
                        "pants": (50, 40, 60), "scale": 1.08, "girth": 1.4, "outline": (20, 10, 30)})
PALS = {"prince": rig.PRINCE, "gblue": rig.GUARD_BLUE, "gred": rig.GUARD_RED, "gfat": rig.GUARD_FAT,
        "skel": rig.SKELETON, "shadow": rig.SHADOW, "vizier": VIZIER}


def build_sprites():
    out = {}
    for pname, pal in PALS.items():
        names = PRINCE_ONLY if pname == "prince" else FIGHT_SET
        d = {}
        for nm in names:
            poses = SEQ[nm][0]
            r, l, _ = render_frames(poses, pal)
            d[nm] = {"R": r, "L": l}
        out[pname] = d
        print("sprites", pname, sum(len(v["R"]) for v in d.values()))
    return out


def cell_rows(img):
    px = img.load()
    return [expand(rgb565_row([px[x, y] for x in range(img.width)])) for y in range(img.height)]


def build_tiles():
    out = {}
    for theme in tiles.THEMES:
        th = {}
        for name, states in tiles.build_theme(theme).items():
            th[name] = [cell_rows(im) for im in states]
        out[theme] = th
    return out


def runs_from_rgb(img):
    rgba = img.convert("RGBA")
    return sprite_from_image(rgba, 0)


def build_misc():
    misc = {}
    for theme in tiles.THEMES:
        p = tiles.Painter(theme, 0)
        im = p.floor_cell().crop((0, tiles.SLAB_TOP, 32, tiles.TH)).convert("RGBA")
        misc["slab_" + theme] = sprite_from_image(im, 16)
    # HUD triangles at screen resolution (opaque, black background).
    def tri(color, filled):
        im = Image.new("RGB", (36, 32), (0, 0, 0))
        d = ImageDraw.Draw(im)
        pts = [(18, 2), (34, 29), (2, 29)]
        if filled:
            d.polygon(pts, fill=color)
            d.line(pts + [pts[0]], fill=tuple(min(255, v + 70) for v in color), width=2)
        else:
            d.line(pts + [pts[0]], fill=tuple(v // 2 for v in color), width=2)
        return pack(im)
    hud = {"kid_full": tri((220, 40, 40), True), "kid_empty": tri((220, 40, 40), False),
           "opp_full": tri((70, 110, 240), True), "opp_empty": tri((70, 110, 240), False)}
    return misc, hud


def main():
    spr = build_sprites()
    tl = build_tiles()
    misc, hud = build_misc()
    meta = {n: {"n": len(v[0]), "dx": [round(x, 2) for x in v[1]], "dy": [round(x, 2) for x in v[2]], "ev": v[3]}
            for n, v in SEQ.items()}
    save_bundle("g_persia.bin",
                {"spr": spr, "tiles": tl, "misc": misc, "hud": hud, "meta": meta, "hang_h": HH})
    print("hang_h", HH, "bin", os.path.getsize("g_persia.bin"))


if __name__ == "__main__":
    main()
