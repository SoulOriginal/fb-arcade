# Builds g_lemmings.bin: lemming and object sprites, fonts, the bottom panel, and the rendered terrain of every level.
# Run from the games directory: python3 g_lemmings_build.py
import zlib, struct
from array import array
from PIL import Image, ImageDraw
from buildlib import save_bundle
import g_lemmings_art as A
from g_lemmings_art import to_sprite, flip, BPX
import g_lemmings_terrain as T
import g_lemmings_levels as LV

M = 40                      # horizontal margin (virtual px) around every row so sprites can be pasted unclipped
PANEL_W = 320


def expand_row(pix565):
    # list of RGB565 ints -> bytes with every pixel repeated 5 times (the 5x integer upscale)
    n = len(pix565)
    lo = bytes(v & 255 for v in pix565)
    hi = bytes(v >> 8 for v in pix565)
    out = bytearray(n * BPX)
    for k in range(A.SCALE):
        out[2 * k::BPX] = lo
        out[2 * k + 1::BPX] = hi
    return bytes(out)


def image_rows(img, pad=True):
    w, h = img.size
    rgb = img.convert("RGB").tobytes()
    rows = []
    blank = bytes(M * BPX)
    for y in range(h):
        row = rgb[y * w * 3:(y + 1) * w * 3]
        it = iter(row)
        pix = array("H", ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3) for r, g, b in zip(it, it, it)))
        e = expand_row(pix.tolist())
        rows.append(blank + e + blank if pad else e)
    return rows


def lem_set(frames, ax=8, ay=19, symmetric=False):
    r = [to_sprite(f, ax, ay) for f in frames]
    if symmetric:
        return {"R": r, "L": r}
    w = frames[0].width
    l = [to_sprite(flip(f), w - 1 - ax, ay) for f in frames]
    return {"R": r, "L": l}


def build_lemmings():
    S = {}
    S["walk"] = lem_set([A.walk(i) for i in range(8)])
    S["fall"] = lem_set([A.fall(i) for i in range(4)], symmetric=True)
    S["float"] = lem_set([A.floater(i) for i in range(6)], symmetric=True)
    S["climb"] = lem_set([A.climb(i) for i in range(4)])
    S["hoist"] = lem_set([A.hoist(i) for i in range(4)])
    S["build"] = lem_set([A.builder(i) for i in range(8)])
    S["shrug"] = lem_set([A.shrug(i) for i in range(2)], symmetric=True)
    S["bash"] = lem_set([A.basher(i) for i in range(8)])
    S["mine"] = lem_set([A.miner(i) for i in range(4)])
    S["dig"] = lem_set([A.digger(i) for i in range(2)], symmetric=True)
    S["block"] = lem_set([A.blocker(i) for i in range(4)], symmetric=True)
    S["ohno"] = lem_set([A.ohno(i) for i in range(2)], symmetric=True)
    S["exit"] = lem_set([A.exit_frame(i) for i in range(8)], symmetric=True)
    S["drown"] = lem_set([A.drown(i) for i in range(8)], symmetric=True)
    S["burn"] = lem_set([A.burn(i) for i in range(8)], symmetric=True)
    S["splat"] = lem_set([A.splat(i) for i in range(8)], ax=12, symmetric=True)
    S["boom"] = [to_sprite(A.explosion(i), 20, 25) for i in range(16)]
    return S


def icon(kind):
    # 16x15 skill icons for the panel buttons, built from the lemming poses
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    src = {"cl": A.climb(1), "fl": A.floater(5), "bo": None, "bl": A.blocker(0), "bu": A.builder(1),
           "ba": A.basher(3), "mi": A.miner(1), "di": A.digger(0)}[kind]
    if kind == "bo":
        d = ImageDraw.Draw(im)
        for r, col in ((7, (255, 80, 30)), (5, (255, 170, 40)), (3, (255, 245, 150))):
            d.ellipse((8 - r, 8 - r, 8 + r, 8 + r), fill=col + (255,))
        for a in range(0, 360, 45):
            import math
            d.line((8, 8, 8 + 8 * math.cos(math.radians(a)), 8 + 8 * math.sin(math.radians(a))), fill=(255, 220, 60, 255))
        return im
    bb = src.getbbox()
    crop = src.crop(bb)
    if crop.height > 16:
        crop = crop.resize((max(1, crop.width * 15 // crop.height), 15), Image.NEAREST)
    im.alpha_composite(crop, ((16 - crop.width) // 2, 16 - crop.height))
    return im


def build_panel():
    img = Image.new("RGBA", (PANEL_W, 40), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    skills = ["rr-", "rr+", "cl", "fl", "bo", "bl", "bu", "ba", "mi", "di", "pause", "nuke"]
    for i, k in enumerate(skills):
        x0, y0 = i * 16, 16
        d.rectangle((x0, y0, x0 + 15, y0 + 23), fill=(74, 80, 118, 255))
        d.line((x0, y0, x0 + 15, y0), fill=(140, 146, 180, 255))
        d.line((x0, y0, x0, y0 + 23), fill=(140, 146, 180, 255))
        d.line((x0 + 15, y0, x0 + 15, y0 + 23), fill=(36, 40, 66, 255))
        d.line((x0, y0 + 23, x0 + 15, y0 + 23), fill=(36, 40, 66, 255))
        for sx, sy in ((x0 + 2, y0 + 12), (x0 + 13, y0 + 12), (x0 + 2, y0 + 21), (x0 + 13, y0 + 21)):
            d.point((sx, sy), fill=(150, 70, 50, 255))
        if k in ("rr-", "rr+"):
            d.rectangle((x0 + 3, y0 + 17, x0 + 12, y0 + 18), fill=(40, 220, 60, 255))
            if k == "rr+":
                d.rectangle((x0 + 7, y0 + 13, x0 + 8, y0 + 22), fill=(40, 220, 60, 255))
        elif k == "pause":
            for ox in (3, 9):
                d.ellipse((x0 + ox, y0 + 15, x0 + ox + 4, y0 + 19), fill=(30, 30, 30, 255))
                for t in range(3):
                    d.ellipse((x0 + ox - 1 + t * 2, y0 + 12 + (t % 2), x0 + ox + t * 2, y0 + 13 + (t % 2)), fill=(30, 30, 30, 255))
        elif k == "nuke":
            d.ellipse((x0 + 3, y0 + 14, x0 + 12, y0 + 19), fill=(230, 60, 30, 255))
            d.rectangle((x0 + 6, y0 + 18, x0 + 9, y0 + 23), fill=(200, 40, 20, 255))
            d.ellipse((x0 + 5, y0 + 12, x0 + 10, y0 + 16), fill=(255, 200, 60, 255))
        else:
            img.alpha_composite(icon(k), (x0, y0 + 7))
    # moss decoration and minimap frame
    d.rectangle((192, 16, 205, 39), fill=(70, 56, 52, 255))
    for yy in range(18, 38, 3):
        d.line((194, yy, 203, yy + 2), fill=(40, 170, 50, 255))
    d.rectangle((206, 16, 313, 39), fill=(200, 40, 32, 255))
    d.rectangle((208, 18, 311, 37), fill=(0, 0, 0, 255))
    d.rectangle((314, 16, 319, 39), fill=(40, 120, 40, 255))
    return image_rows(img)


def box_sprite(w, h, col=(255, 255, 255)):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((0, 0, w - 1, h - 1), outline=col + (255,))
    return to_sprite(im)


def object_sprites(o, ex, ey):
    k = o["kind"]
    if k == "water":
        return dict(o, frames=[to_sprite(A.water(o["w"], o["h"], f)) for f in range(8)], per=3)
    if k == "fire":
        return dict(o, frames=[to_sprite(A.fire_pit(o["w"], o["h"], f)) for f in range(8)], per=2)
    if k == "crusher":
        return dict(o, frames=[to_sprite(A.crusher(f)) for f in range(12)], per=9)
    raise ValueError(k)


def build_level(fn):
    P, m = fn()
    img, mask = T.render(P)
    w = P.w
    rows = image_rows(img)
    ex, ey = m["entrance"]
    xx, xy = m["exit"]
    objs = [object_sprites(o, ex, ey) for o in m["objs"]]
    entr = A.entrance()
    exits = A.exit_door()
    f = -(-w // 300)
    prev = img.resize((w // f, 160 // f), Image.BOX)
    skills = [m["skills"].get(k, 0) for k in ("cl", "fl", "bo", "bl", "bu", "ba", "mi", "di")]
    return {"name": m["name"], "rating": m["rating"], "n": m["n"], "save": m["save"], "time": m["time"],
            "rr": m["rr"], "skills": skills, "cam0": m["cam0"], "w": w, "entrance": (ex, ey), "exit": (xx, xy),
            "entr": [to_sprite(e) for e in entr], "exitspr": [to_sprite(e) for e in exits],
            "objs": objs, "plan": m["plan"], "mask": zlib.compress(bytes(mask), 9),
            "rows": zlib.compress(b"".join(rows), 9), "stride": (w + 2 * M) * BPX,
            "preview": to_sprite(prev), "preview_f": f}


def main():
    data = {}
    data["lem"] = build_lemmings()
    data["digits"] = {ch: to_sprite(im) for ch, im in A.digit_sprites().items()}
    data["cross"] = to_sprite(A.crosshair(), 5, 5)
    data["box"] = to_sprite(A.cursor_box(), 6, 6)
    data["hi"] = box_sprite(16, 24)
    data["panel"] = build_panel()
    data["font_big"] = A.font_set(12, (255, 220, 235), (60, 20, 40))
    data["font_red"] = A.font_set(12, (255, 90, 80), (60, 10, 10))
    data["font_hud"] = A.font_set(12, (70, 240, 70), (0, 70, 0), mono=True)
    data["font_cnt"] = A.font_set(8, (130, 255, 130), (0, 50, 0), mono=True)
    data["levels"] = [build_level(fn) for fn in LV.LEVELS]
    save_bundle("g_lemmings.bin", data)


if __name__ == "__main__":
    main()
