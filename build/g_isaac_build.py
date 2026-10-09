# Build script for the Isaac game: draws every sprite procedurally with PIL and writes g_isaac.bin.
# Run from the games directory: python3 g_isaac_build.py
from g_isaac_art import *
from g_isaac_chars import *
from g_isaac_mobs import *
import g_isaac_env as E
from buildlib import save_bundle

DIRS = "dur"


def cardinal_set(fn, *args, frames=(None,)):
    # Builds d/u/r images and a mirrored l image so a creature can face four ways from three drawings.
    out = {}
    for d in DIRS:
        out[d] = fn(d, *args)
    out["l"] = flip(out["r"])
    return out


def main():
    spr = {}
    anch = {}

    def put(name, imgs, anchor=None):
        spr[name] = [rle(i) for i in imgs]
        w, h = imgs[0].size
        anch[name] = anchor or (w // 2, h // 2)

    # Isaac
    heads = {}
    for st in "nsh":
        sets = cardinal_set(head, st)
        for d in "dulr":
            heads[d + st] = sets[d]
    for k, im in heads.items():
        put("head_" + k, [im], HEAD_C)
    bv = [body("v", f) for f in range(6)]
    bh = [body("h", f) for f in range(6)]
    put("body_v", bv, (30, 34))
    put("body_r", bh, (30, 34))
    put("body_l", [flip(i) for i in bh], (30, 34))
    put("dead", [dead()], (85, 80))
    put("tear", [tear_img(10, TEARC, TEAR_HI, (40, 70, 140, 255)), tear_img(15, TEARC, TEAR_HI, (40, 70, 140, 255))])
    put("etear", [tear_img(9, BLOOD, BLOOD_HI, BLOOD_DK), tear_img(15, BLOOD, BLOOD_HI, BLOOD_DK)])
    put("splash", [splash(10, f, TEARC, (40, 70, 140, 255)) for f in range(4)])
    put("esplash", [splash(10, f, BLOOD, BLOOD_DK) for f in range(4)])
    put("bomb", [bomb_img(0), bomb_img(1)], (30, 44))
    put("boom", [explosion(f) for f in range(6)])
    put("heart_p", [pickup_heart("red"), pickup_heart("redhalf"), pickup_heart("soul")])
    put("coin", [coin(f) for f in range(4)])
    put("key", [key_img()])
    put("bomb_p", [bomb_pickup()])
    put("pedestal", [pedestal()], (42, 30))
    put("trapdoor", [trapdoor(0), trapdoor(1)])
    for n in ITEMS:
        put("item_" + n, [item_icon(n)])
    for n in (3, 5, 10, 15):
        put("price_%d" % n, [price_tag(n)])
    hud = {}
    for k in ("full", "half", "empty", "soul", "soul_half", "soul_empty"):
        hud["heart_" + k] = rle(heart_icon(k, 44))
    hud["coin"] = rle(stat_icon("coin"))
    hud["bomb"] = rle(stat_icon("bomb"))
    hud["key"] = rle(stat_icon("key"))

    # enemies
    put("fly", [fly(0), fly(1)])
    put("pooter", [pooter(0), pooter(1)])
    put("gaper", [gaper(f) for f in range(4)], (44, 64))
    put("horf", [horf(0), horf(1)])
    put("clotty", [clotty(0), clotty(1)])
    put("mulligan", [mulligan(0), mulligan(1)], (45, 70))
    ch = {}
    for d in "dur":
        ch[d] = [charger(d, f) for f in (0, 1)]
    ch["l"] = [flip(i) for i in ch["r"]]
    for d in "dulr":
        put("charger_" + d, ch[d])
    put("host", [host(False), host(True)], (44, 52))
    put("boil", [boil(0), boil(1), boil(2)], (38, 48))
    put("spider", [spider(0), spider(1)], (34, 32))
    put("monstro", [monstro(s) for s in range(3)], (110, 112))
    put("duke", [duke(0), duke(1)], (88, 92))
    put("contusion", [contusion(0), contusion(1)])
    put("suture", [suture(0), suture(1)])
    put("cord", [cord_dot()])
    for d in "dulr":
        pass
    lh = cardinal_set(larry, "head")
    ls = larry("d", "seg")
    ch_h = cardinal_set(chub, "head")
    cs = chub("d", "seg")
    for d in "dulr":
        put("larry_" + d, [lh[d]])
        put("chub_" + d, [ch_h[d]])
    put("larry_seg", [ls])
    put("chub_seg", [cs])
    put("gurdy", [gurdy(s) for s in range(3)], (120, 120))

    themes = []
    for ti, th in enumerate(E.THEMES):
        themes.append(dict(
            shell=opaque(E.shell(th, ti)),
            rock=[rle(E.rock(v, th)) for v in range(3)],
            rubble=rle(E.rubble(th)),
            pit=[rle(E.pit(m, th)) for m in range(16)],
            decal=[rle(E.decal(k, v)) for k, v in ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (2, 0))],
        ))
    env = dict(
        poop=[rle(E.poop(s)) for s in range(3)],
        fire=[[rle(E.fire(f, s)) for f in range(4)] for s in range(3)],
        spikes=rle(E.spikes()),
    )
    doors = {}
    for kind, states in (("normal", ("closed", "open")), ("boss", ("closed", "open")),
                         ("treasure", ("closed", "locked", "open")), ("shop", ("closed", "locked", "open")),
                         ("hole", ("open",))):
        for st in states:
            base = E.door(kind, st)
            variants = {"u": base, "d": base.transpose(Image.ROTATE_180), "l": base.transpose(Image.ROTATE_90),
                        "r": base.transpose(Image.ROTATE_270)}
            for d, im in variants.items():
                doors["%s_%s_%s" % (kind, st, d)] = rle(im)
    # fixed-position shell-space layout, shared with the runtime
    meta = dict(cell=E.CELL, wall=E.WALL, shell_w=E.SHELL_W, shell_h=E.SHELL_H, anch=anch,
                theme_names=[t["name"] for t in E.THEMES])
    save_bundle("g_isaac.bin", dict(spr=spr, hud=hud, themes=themes, env=env, doors=doors, meta=meta))


if __name__ == "__main__":
    main()
