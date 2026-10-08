# Build script for the Battletoads module: draws every sprite and background strip procedurally and
# writes g_battletoads.bin. Run: python3 g_battletoads_build.py   (preview: ... sheet <group>)
import math, sys, random
from PIL import Image, ImageDraw, ImageFont
from buildlib import save_bundle, BOLD
from g_battletoads_art import *
from g_battletoads_chars import *
import g_battletoads_poses as PZ
import g_battletoads_world as WD


def render_char(pose, style, k, size, propimg=None, rot=0, flash=0.0, anchor=False):
    cw, ch, oy = size
    cv = Cv(cw, ch, oy)
    biped(cv, pose, style, k, propimg)
    if rot:
        cv.rotated(rot, (0, -style["torso"] * k - 8))
    im = to_virtual(cv)
    if anchor:
        im = reanchor(im, cv.ox, cv.oy)
    if flash:
        im = tint(im, (255, 255, 255), flash)
    return im, cv.ox, cv.oy


def sheet(frames, path, bg=(90, 70, 110), cols=8, cell=(190, 190)):
    rows = (len(frames) + cols - 1) // cols
    sh = Image.new("RGB", (cols * cell[0], rows * cell[1]), bg)
    for i, (im, ox, oy) in enumerate(frames):
        x = (i % cols) * cell[0] + cell[0] // 2 - ox
        y = (i // cols) * cell[1] + cell[1] - 12 - oy
        sh.paste(im, (x, y), im.getchannel("A"))
    sh = sh.resize((sh.width * 2 // 2, sh.height * 2 // 2))
    sh.save(path)


RAVEN_SIZE = (150, 120, 60)
RAVEN_COL = dict(body=(52, 46, 96), wing=(40, 34, 78), sheen=(110, 110, 190), beak=(238, 176, 52))


def draw_raven(wing, pitch=0, hurt=False):
    cv = Cv(*RAVEN_SIZE)
    c = RAVEN_COL

    def R(x, y):
        rx, ry = rot_pt(x, y, pitch)
        return (rx, ry)

    def wings(col, dx, up):
        a = math.radians(wing)
        root = R(-2 + dx, -4)
        tip = R(-16 + dx - 6 * abs(math.sin(a)), -4 - 40 * math.sin(a))
        mid = R(-8 + dx, -4 - 18 * math.sin(a))
        cv.capsule(root, 6, mid, 6.5, col)
        cv.capsule(mid, 6.5, tip, 2.4, col)
        for k in range(3):
            fe = R(-20 + dx - 4 * k - 6 * abs(math.sin(a)), -4 - (36 - 9 * k) * math.sin(a) + 4 * k)
            cv.capsule(mid, 2.8, fe, 1.4, shade(col, 0.9), o=0.9)
    wings(shade(c["wing"], 0.8), 3, 0)
    for k, dy in enumerate((-4, 0, 4)):
        cv.capsule(R(-14, 1), 3.4, R(-34, 2 + dy * 1.3), 1.8, c["wing"], o=1.0)
    ellipses(cv, [(*R(0, 0), 17, 10.5, pitch, c["body"]), (*R(16, -6), 8.4, 7.6, pitch, c["body"])])
    cv.poly([R(22, -10), R(38, -5), R(22, -1)], OUT)
    cv.poly([R(22, -9), R(36, -5.2), R(22, -2)], c["beak"])
    cv.line(R(22, -5.5), R(35, -5.2), 0.8, (150, 100, 20))
    if hurt:
        cv.line(R(17, -10), R(21, -6), 1.2, OUT)
        cv.line(R(21, -10), R(17, -6), 1.2, OUT)
    else:
        cv.circ(*R(18.5, -8), 2.5, (255, 255, 255))
        cv.circ(*R(19.3, -8), 1.4, (210, 20, 30))
        cv.line(R(15, -12.5), R(22, -10), 1.5, OUT)
    cv.line(R(0, 8), R(2, 14), 1.4, c["beak"])
    cv.line(R(6, 8), R(8, 14), 1.4, c["beak"])
    wings(c["wing"], 0, 1)
    return cv


def raven_frames():
    A = {}

    def mk(cv, rot=0, flash=0):
        if rot:
            cv.rotated(rot, (0, 0))
        # ravens are drawn small and enlarged about the body centre so they read at screen distance
        big = cv.im.resize((int(cv.im.width * 1.45), int(cv.im.height * 1.45)), Image.BICUBIC)
        l, t_ = (big.width - cv.im.width) // 2, (big.height - cv.im.height) // 2
        cv.im = big.crop((l, t_, l + cv.im.width, t_ + cv.im.height))
        im = to_virtual(cv)
        if flash:
            im = tint(im, (255, 255, 255), flash)
        return im, cv.ox, cv.oy
    A["fly"] = [mk(draw_raven(48 * math.sin(2 * math.pi * i / 8))) for i in range(8)]
    A["dive"] = [mk(draw_raven(-24, 38))]
    A["hurt"] = [mk(draw_raven(30, -20, True), flash=0.75), mk(draw_raven(30, -20, True))]
    A["fall"] = [mk(draw_raven(20, 0, True), rot=r) for r in (40, 130, 220, 310)]
    return A


def prop_images():
    cv = Cv(120, 120, 80)
    p = dict(POSE)
    p.update(PZ.enemy_anims("pig")["held"][0])
    p.pop("flash", None)
    biped(cv, p, PZ.PIG_A, 0.8)
    bb = cv.im.getchannel("A").getbbox()
    pig = cv.im.crop(bb)
    cv = Cv(80, 100, 60)
    m = (150, 160, 178)
    cv.capsule((0, 18), 4.6, (0, -4), 4.2, m)
    cv.circ(0, -4, 5.4, (236, 132, 44))
    cv.capsule((0, -4), 4, (3, -28), 3.6, m)
    cv.blob(7, -33, 16, 6, (84, 90, 110), rot=90)
    bb = cv.im.getchannel("A").getbbox()
    return pig, cv.im.crop(bb)


def hud_plate(st):
    w, h = 312, 50
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 8, fill=(26, 16, 34, 255), outline=(236, 184, 62, 255), width=2)
    d.rounded_rectangle((3, 3, w - 4, h - 4), 6, outline=(120, 80, 40, 255), width=1)
    d.rounded_rectangle((5, 5, 44, h - 6), 5, fill=(52, 36, 70, 255), outline=(236, 184, 62, 255))
    ic = to_virtual(WD.toad_icon(st, 38))
    im.alpha_composite(ic, (6, 7))
    return im


def block(full):
    im = Image.new("RGBA", (14, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if full:
        d.rectangle((0, 0, 13, 15), fill=(40, 10, 10, 255))
        d.rectangle((1, 1, 12, 14), fill=(224, 40, 44, 255))
        d.rectangle((1, 1, 12, 4), fill=(255, 130, 120, 255))
        d.rectangle((1, 12, 12, 14), fill=(150, 20, 30, 255))
    else:
        d.rectangle((0, 0, 13, 15), fill=(20, 14, 26, 255))
        d.rectangle((1, 1, 12, 14), fill=(52, 36, 56, 255))
    return to_sprite(im, 7, 8)


def build():
    random.seed(5)
    out = {"spr": {}, "fx": {}, "lab": {}, "hud": {}}
    pig_img, leg_img = prop_images()

    def add(name, A, sty, k, size):
        d = {}
        for anim, poses in A.items():
            frames = []
            for pz in poses:
                pz = dict(pz)
                rot = pz.pop("rot", 0)
                anc = pz.pop("anchor", False)
                fl = pz.pop("flash", 0)
                pk = pz.pop("propkind", None)
                im, ox, oy = render_char(pz, sty, k, size, propimg=(pig_img if pk == "swingpig" else leg_img) if pk else None,
                                         rot=rot, flash=fl, anchor=anc)
                frames.append(sprite_pair(im, ox, oy))
            d[anim] = frames
        out["spr"][name] = d
        print(name, sum(len(v) for v in d.values()), "frames", flush=True)
    toad = dict(PZ.toad_anims(), **PZ.toad_prop_anims())
    add("toad0", toad, PZ.TOAD_A, 1.0, PZ.TOAD_SIZE)
    add("toad1", toad, PZ.TOAD_B, 1.0, PZ.TOAD_SIZE)
    add("pig0", PZ.enemy_anims("pig"), PZ.PIG_A, 0.95, PZ.PIG_SIZE)
    add("pig1", PZ.enemy_anims("pig"), PZ.PIG_B, 1.0, PZ.PIG_SIZE)
    add("rat", PZ.enemy_anims("rat"), PZ.RAT_A, 1.0, PZ.RAT_SIZE)
    add("walker", PZ.enemy_anims("walker"), PZ.WALKER, 1.45, PZ.WALKER_SIZE)
    add("boss", PZ.enemy_anims("boss"), PZ.BOSS, 2.5, PZ.BOSS_SIZE)
    out["spr"]["raven"] = {a: [sprite_pair(*f) for f in fr] for a, fr in raven_frames().items()}
    # the walker's leg lying on the ground after the walker is destroyed
    cv = Cv(120, 60, 40)
    cv.capsule((-26, 0), 4.4, (4, -2), 4, (150, 160, 178))
    cv.circ(4, -2, 5, (236, 132, 44))
    cv.capsule((4, -2), 3.8, (28, 3), 3.4, (150, 160, 178))
    cv.blob(36, 4, 12, 5, (84, 90, 110))
    im = to_virtual(cv)
    out["spr"]["legitem"] = {"idle": [sprite_pair(im, cv.ox, cv.oy)]}
    out["fx"] = WD.effects()
    icon = to_virtual(WD.toad_icon(PZ.TOAD_A, 40))
    out["fx"]["alert"] = [WD.label("!", 30, (255, 60, 50), (255, 255, 255), 2)[0]]
    out["fx"]["oneup"] = [to_sprite(icon, icon.width // 2, icon.height - 4)]
    for pi in (0, 1):
        out["hud"]["plate%d" % pi] = to_sprite(hud_plate((PZ.TOAD_A, PZ.TOAD_B)[pi]), 156, 25)
    out["hud"]["full"] = block(True)
    out["hud"]["empty"] = block(False)
    out["hud"]["digit"] = [WD.label(str(i), 17, sw=1)[0] for i in range(10)]
    out["hud"]["x"] = WD.label("x", 15, sw=1)[0]
    out["hud"]["p"] = [WD.label("1P", 14, (140, 255, 120), sw=1)[0], WD.label("2P", 14, (130, 190, 255), sw=1)[0]]
    texts = {"title": ("RAGNAROK'S CANYON", 40), "canyon2": ("CANYON 2", 40), "canyon3": ("CANYON 3", 40),
             "go": ("GO", 46), "clear": ("STAGE CLEAR", 44), "warning": ("WARNING", 44), "blag": ("BIG BLAG", 54),
             "oneup": ("1UP", 18)}
    for key, (t, sz) in texts.items():
        out["lab"][key] = WD.label(t, sz)
    out["lab"]["warning"] = WD.label("WARNING", 44, (255, 70, 60))
    out["lab"]["oneup"] = WD.label("1UP", 18, (130, 255, 130))
    pops = {}
    for v in (100, 200, 300, 500, 1000, 2000, 10000):
        pops[v] = WD.label(str(v), 15, (255, 255, 255), (30, 20, 50), 1)
    out["pop"] = pops
    # GO arrow: two frames, bright and dim
    arr = []
    for c in ((255, 224, 60), (255, 255, 255)):
        cv = Cv(80, 60, 30)
        pts = [(-26, -10), (4, -10), (4, -22), (28, 0), (4, 22), (4, 10), (-26, 10)]
        cv.poly([(x * 1.08, y * 1.1) for x, y in pts], OUT)
        cv.poly(pts, c)
        arr.append(to_sprite(to_virtual(cv), cv.ox, cv.oy))
    out["arrow"] = arr
    out["bg"] = [WD.build_background(pi, 11 + pi) for pi in (0, 1)]
    out["shadow"] = [WD.shadow_sprites(pi) for pi in (0, 1)]
    out["meta"] = {"bands": WD.BANDS}
    save_bundle("g_battletoads.bin", out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sheet":
        frames = PZ.preview(sys.argv[2])
        sheet(frames, "sheet_%s.png" % sys.argv[2])
    else:
        build()
