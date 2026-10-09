# Build script for the Contra module: draws every sprite and level strip procedurally and writes g_contra.bin.
# Usage: python3 g_contra_build.py
from PIL import Image, ImageDraw
from buildlib import save_bundle
import g_contra_art as A
import g_contra_levels as L
from g_contra_art import C, new, mirror, sprite, person, ImageDraw as _ID

AIM_COUNT = 5


def people(pal):
    out = []
    for flip in (0, 1):
        dd = {}
        ox = 20 if not flip else 19
        f = (lambda im: mirror(im)) if flip else (lambda im: im)
        for aim in range(AIM_COUNT):
            dd["run%d" % aim] = [sprite(f(person(pal, "run", k, aim)), ox, 47) for k in range(4)]
            dd["stand%d" % aim] = [sprite(f(person(pal, "stand", 0, aim)), ox, 47)]
        dd["jump"] = [sprite(f(person(pal, "jump", k)), ox, 47) for k in range(4)]
        dd["prone"] = [sprite(f(person(pal, "prone")), ox, 47)]
        dd["dead"] = [sprite(f(person(pal, "dead", k)), ox, 47) for k in range(4)]
        for aim in range(3):
            dd["wade%d" % aim] = [sprite(f(person(pal, "wade", 0, aim)), ox, 47)]
        dd["dive"] = [sprite(f(person(pal, "dive")), ox, 47)]
        out.append(dd)
    return out


def core(fr):
    im = new(28, 34)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 27, 33], fill=C["black"] + (255,))
    d.rectangle([2, 2, 25, 31], fill=C["dgrey"] + (255,))
    if fr == 0:
        d.rectangle([4, 4, 23, 29], fill=C["grey"] + (255,))
        for y in range(6, 28, 4):
            d.line([(4, y), (23, y)], fill=C["dgrey"] + (255,))
    else:
        col = C["red"] if fr == 1 else C["orange"]
        d.rectangle([4, 4, 23, 29], fill=C["dred"] + (255,))
        d.ellipse([5, 8, 22, 26], fill=col + (255,))
        d.ellipse([9, 12, 18, 22], fill=C["yellow"] + (255,))
        d.ellipse([12, 15, 15, 19], fill=C["white"] + (255,))
    return im


def flipv(im):
    return im.transpose(Image.FLIP_TOP_BOTTOM)


def main():
    S = {}
    for pal in ("bill", "lance", "soldier", "rsoldier", "sniper"):
        S[pal] = people(pal)
    S["turret"] = [sprite(A.turret(k), 12, 23) for k in range(12)]
    S["bturret"] = [sprite(A.turret(k, kind="red"), 12, 23) for k in range(12)]
    S["sensor"] = [sprite(A.sensor(k), 12, 23) for k in range(3)]
    S["bush"] = [sprite(A.bush(), 13, 13)]
    S["cannon"] = [sprite(A.ground_cannon(k), 13, 17) for k in range(3)]
    S["scuba"] = [sprite(A.scuba(k), 8, 19) for k in range(2)]
    S["boulder"] = [sprite(A.boulder(k), 9, 9) for k in range(4)]
    S["flame"] = [sprite(A.flame(k), 7, 17) for k in range(2)]
    S["float"] = [sprite(A.floating_rock(), 20, 3)]
    S["mouth"] = [sprite(A.mouth(k), 14, 11) for k in range(3)]
    S["fmouth"] = [sprite(flipv(A.mouth(k)), 14, 11) for k in range(3)]
    S["bighead"] = [sprite(A.mouth(k).resize((56, 44), Image.NEAREST), 28, 22) for k in range(3)]
    S["spore"] = [sprite(A.spore(k), 5, 5) for k in range(2)]
    S["floater"] = [[sprite(A.floater(k), 9, 6) for k in range(2)], [sprite(mirror(A.floater(k)), 9, 6) for k in range(2)]]
    S["crawler"] = [[sprite(A.crawler(k), 11, 13) for k in range(2)], [sprite(mirror(A.crawler(k)), 11, 13) for k in range(2)]]
    S["cocoon"] = [sprite(A.cocoon(k), 13, 13) for k in range(3)]
    S["heart"] = [sprite(A.heart(k), 28, 30) for k in range(3)]
    S["orb"] = [sprite(A.orb(), 7, 7)]
    S["head"] = [sprite(A.alien_head(k), 24, 26) for k in range(3)]
    S["fireball"] = [sprite(A.fireball(k), 5, 5) for k in range(4)]
    S["core"] = [sprite(core(k), 14, 17) for k in range(3)]
    S["capsule"] = [sprite(A.capsule(k), 12, 7) for k in range(2)]
    S["item"] = {ch: [sprite(A.falcon(ch), 13, 8)] for ch in "SMLFRB"}
    S["medal"] = {"blue": [sprite(A.medal("blue"), 5, 0)], "orange": [sprite(A.medal("orange"), 5, 0)]}
    S["eb"] = [sprite(A.dot(4, "white", "red"), 2, 2)]
    S["pn"] = [sprite(A.dot(3, "white", "lgrey"), 1, 1)]
    S["pm"] = [sprite(A.dot(3, "yellow", "white"), 1, 1)]
    S["ps"] = [sprite(A.dot(5, "yellow", "red"), 2, 2)]
    S["pf"] = [sprite(A.dot(6, "yellow", "orange"), 3, 3), sprite(A.dot(6, "white", "red"), 3, 3)]
    dirs = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]
    S["pl"] = []
    for dv in dirs:
        im = A.laser(dv)
        S["pl"].append(sprite(im, im.size[0] // 2, im.size[1] // 2))
    S["exp_s"] = [sprite(A.explosion(k, 0), A.explosion(k, 0).size[0] // 2, A.explosion(k, 0).size[1] // 2) for k in range(5)]
    S["exp_b"] = [sprite(A.explosion(k, 1), A.explosion(k, 1).size[0] // 2, A.explosion(k, 1).size[1] // 2) for k in range(5)]
    stages = [L.stage1(), L.stage3(), L.stage8()]
    save_bundle("g_contra.bin", {"spr": S, "stages": stages})
    print("built", sum(len(st.get("fg", [])) for st in stages))


if __name__ == "__main__":
    main()
