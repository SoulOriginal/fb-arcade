# Build-time script for the temple runner: renders every sprite at every distance bucket (already fogged and
# expanded to 6x6 screen pixels per virtual pixel), the panoramas, the side panels, the HUD pieces and the
# palettes into g_temple.bin. The play window is portrait (120x180 vpx), like the phone game.
import math
import random
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from buildlib import save_bundle, rgb565, BOLD
import g_temple_art as A

F = 90.0                       # focal length in vpx; must match g_temple.py
HZ = 50                        # horizon vrow
VW, VH = 120, 180
PW = 576                       # a full turn of the camera in vpx (2 * pi * F, rounded to a multiple of 8)
CAMBACK = 5.5
ZB = []
_z = 3.4
while _z < 100:
    ZB.append(round(_z, 3))
    _z *= 1.16
RUN_SCALE = F / CAMBACK

THEMES = [
    dict(name="TEMPLE BRIDGE", sky=((24, 70, 82), (96, 156, 150)), fog=(88, 148, 142), sun=(190, 240, 210),
         ground=((14, 54, 62), (22, 82, 84)), glow=(60, 190, 140), slab=((206, 164, 98), (190, 148, 84), (214, 176, 112), (176, 136, 78)),
         joint=(88, 60, 32), grass=(86, 128, 48), pit=(4, 20, 26), face=((140, 98, 50), (118, 80, 40)), wtop=(150, 160, 78),
         wjoint=(84, 58, 30), hills=((60, 112, 112), (38, 86, 88), (22, 58, 62)),
         leaf_d=(20, 72, 36), leaf_m=(36, 112, 50), leaf_l=(88, 160, 70), bark=(88, 62, 40), bark_d=(56, 38, 26),
         stone=(176, 132, 76), stone_d=(118, 82, 44), moss_c=(96, 140, 60), vine=(44, 96, 44), eye=(255, 190, 80), lit=False),
    dict(name="JUNGLE RUINS", sky=((70, 130, 190), (176, 210, 200)), fog=(170, 204, 186), sun=(255, 244, 200),
         ground=((34, 82, 38), (40, 94, 44)), glow=(110, 190, 80), slab=((196, 162, 104), (180, 146, 90), (206, 174, 116), (168, 134, 82)),
         joint=(84, 62, 36), grass=(88, 140, 52), pit=(10, 20, 12), face=((136, 98, 54), (114, 80, 44)), wtop=(130, 164, 70),
         wjoint=(80, 60, 34), hills=((92, 140, 130), (60, 110, 84), (36, 84, 52)),
         leaf_d=(20, 72, 36), leaf_m=(36, 112, 50), leaf_l=(88, 160, 70), bark=(88, 62, 40), bark_d=(56, 38, 26),
         stone=(168, 130, 80), stone_d=(112, 84, 50), moss_c=(84, 130, 60), vine=(44, 96, 44), eye=(255, 190, 80), lit=False),
    dict(name="NIGHT TEMPLE", sky=((8, 12, 40), (60, 72, 126)), fog=(50, 62, 106), sun=(230, 236, 255),
         ground=((10, 22, 34), (14, 30, 46)), glow=(50, 190, 190), slab=((130, 136, 164), (116, 122, 150), (140, 146, 174), (104, 110, 136)),
         joint=(36, 40, 62), grass=(54, 110, 100), pit=(2, 4, 12), face=((74, 82, 114), (62, 70, 100)), wtop=(78, 124, 120),
         wjoint=(34, 38, 58), hills=((36, 48, 92), (24, 34, 70), (14, 22, 46)),
         leaf_d=(12, 38, 50), leaf_m=(22, 62, 72), leaf_l=(54, 110, 110), bark=(52, 46, 62), bark_d=(34, 30, 44),
         stone=(110, 116, 146), stone_d=(66, 72, 100), moss_c=(54, 120, 110), vine=(34, 80, 84), eye=(90, 255, 200), lit=True),
]


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def fog_t(z):
    # the same curve is evaluated by the game for the ground rows (z = K / dy)
    return min(0.92, max(0.0, (z - 12.0) / 78.0) ** 1.1)


def px12(rgb):
    return rgb565(*rgb).to_bytes(2, "little") * 6


def to_spans(im, fog, fogc, anchor=None):
    # opaque runs only; transparent pixels stay untouched when the sprite is patched into a row
    w, h = im.size
    px = im.load()
    cache = {}
    rows = []
    for y in range(h):
        spans = []
        x = 0
        while x < w:
            if px[x, y][3] < 120:
                x += 1
                continue
            x0 = x
            parts = []
            while x < w and px[x, y][3] >= 120:
                r, g, b, _ = px[x, y]
                key = (r >> 2, g >> 2, b >> 2)
                v = cache.get(key)
                if v is None:
                    v = cache[key] = px12(lerp((r, g, b), fogc, fog))
                parts.append(v)
                x += 1
            spans.append((x0, b"".join(parts)))
        rows.append(spans)
    ax, ay = anchor if anchor else (w // 2, h - 1)
    return (w, h, rows, ax, ay)


def buckets(src, fogc, zmin=3.4, foot=0.0):
    # src = (image, width m, height m); foot = metres of empty canvas under the object's base
    im, wm, hm = src
    out = []
    for z in ZB:
        if z < zmin:
            out.append(None)
            continue
        sc = F / z
        w, h = int(round(wm * sc)), int(round(hm * sc))
        if w < 1 or h < 2:
            out.append(None)
            continue
        small = im.resize((w, h), Image.LANCZOS)
        out.append(to_spans(small, fog_t(z), fogc, (w // 2, max(0, h - 1 - int(round(foot * sc))))))
    return out


def one(src, scale, fogc, foot=0.0):
    im, wm, hm = src
    w, h = int(round(wm * scale)), int(round(hm * scale))
    small = im.resize((w, h), Image.LANCZOS)
    return to_spans(small, 0.0, fogc, (w // 2, h - 1 - int(round(foot * scale))))


def silhouette_scene(th, rnd, w, h, horizon):
    # fog gradient with a giant gnarled tree and temple ruins fading into the haze, as in the real game's background
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    top, low = th["sky"]
    for y in range(horizon):
        d.line([(0, y), (w, y)], fill=lerp(top, low, (y / horizon) ** 1.3))
    sx = rnd.randrange(w)
    glow = Image.new("RGB", im.size, (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([sx - h * 0.1, horizon * 0.45 - h * 0.1, sx + h * 0.1, horizon * 0.45 + h * 0.1],
                                 fill=tuple(c // 3 for c in th["sun"]))
    im = ImageChops.add(im, glow.filter(ImageFilter.GaussianBlur(h * 0.05)))
    d = ImageDraw.Draw(im)
    if th["lit"]:
        for _ in range(w // 5):
            d.point((rnd.randrange(w), rnd.randrange(int(horizon * 0.7))), fill=rnd.choice(((255, 255, 255), (200, 220, 255))))
    for li, col in enumerate(th["hills"]):
        amp = horizon * (0.34, 0.24, 0.14)[li]
        y0 = horizon - horizon * (0.1, 0.04, 0.0)[li]
        ph = [rnd.uniform(0, 6.28) for _ in range(3)]
        pts = [(0, horizon + 2)]
        for x in range(0, w + 1, 3):
            u = x / w * 2 * math.pi
            y = y0 - amp * (0.5 + 0.25 * math.sin(u * (3 + li * 2) + ph[0]) + 0.15 * math.sin(u * (7 + li * 3) + ph[1]) +
                           0.1 * math.sin(u * (19 + li * 5) + ph[2]))
            pts.append((x, y))
        pts.append((w, horizon + 2))
        d.polygon(pts, fill=col)
        if li == 0:
            for _ in range(3):
                tx = rnd.randrange(w)
                tw = rnd.randint(int(w * 0.04), int(w * 0.07))
                ty = y0 - amp * 0.4
                for k in range(5):
                    d.rectangle([tx - tw + k * tw * 0.14, ty - (k + 1) * tw * 0.3, tx + tw - k * tw * 0.14, ty - k * tw * 0.3],
                                fill=lerp(col, th["hills"][2], 0.5))
    # the giant tree: a trunk with a few heavy branches and a dark crown
    tx = rnd.randrange(w)
    col = lerp(th["hills"][1], th["hills"][2], 0.5)
    tw = w * 0.025
    d.polygon([(tx - tw * 2, horizon), (tx - tw, horizon * 0.5), (tx + tw, horizon * 0.5), (tx + tw * 2, horizon)], fill=col)
    for k in range(4):
        ang = rnd.uniform(-1.2, 1.2)
        ex, ey = tx + math.sin(ang) * horizon * 0.5, horizon * 0.5 - math.cos(ang) * horizon * 0.3
        d.line([(tx, horizon * 0.55), (ex, ey)], fill=col, width=int(tw * 1.2))
        d.ellipse([ex - tw * 3, ey - tw * 2, ex + tw * 3, ey + tw * 2], fill=col)
    return im


def panorama(th, rnd):
    ss = 3
    im = silhouette_scene(th, rnd, PW * ss, HZ * ss, HZ * ss).resize((PW, HZ), Image.LANCZOS)
    rows = []
    px = im.load()
    for y in range(HZ):
        line = [px[x % PW, y] for x in range(PW + VW)]
        if all(p == line[0] for p in line):
            rows.append((1, px12(line[0])))
        else:
            rows.append((0, b"".join(px12(p) for p in line)))
    return rows


def side_panels(th, rnd):
    # the scene blurred, dimmed and mirrored into the two 600 px bands beside the portrait window
    w, h = 150, 270
    scene = silhouette_scene(th, rnd, w, h, int(h * 0.42))
    d = ImageDraw.Draw(scene)
    for y in range(int(h * 0.42), h):
        t = (y - h * 0.42) / (h * 0.58)
        d.line([(0, y), (w, y)], fill=lerp(lerp(th["ground"][1], th["fog"], 0.25), th["ground"][0], t))
    for _ in range(40):
        x, y = rnd.randrange(w), rnd.randrange(int(h * 0.45), h)
        d.line([(x, y), (x + rnd.randint(6, 22), y)], fill=lerp(th["ground"][1], th["glow"], 0.5), width=1)
    scene = scene.resize((600, 1080), Image.BICUBIC).filter(ImageFilter.GaussianBlur(14))
    shade = Image.new("L", scene.size)
    sd = ImageDraw.Draw(shade)
    for x in range(600):
        sd.line([(x, 0), (x, 1080)], fill=int(150 + 80 * (x / 600) ** 1.5))
    scene = Image.composite(scene, Image.new("RGB", scene.size, (0, 0, 0)), shade)
    left = scene.transpose(Image.FLIP_LEFT_RIGHT)

    def raw(im):
        return b"".join(rgb565(r, g, b).to_bytes(2, "little") for r, g, b in im.getdata())
    return raw(left), raw(scene)


def ground_pal(th):
    return dict(fog=th["fog"], raw={k: th[k] for k in ("ground", "glow", "slab", "joint", "grass", "pit", "face", "wtop", "wjoint")})


def build_theme(ti):
    th = THEMES[ti]
    pal = dict(th)
    pal["moss"] = th["moss_c"]
    pal["glow"] = th["eye"]
    fogc = th["fog"]
    rnd = random.Random(1000 + ti)
    out = {"name": th["name"], "pal": ground_pal(th), "pano": panorama(th, rnd)}
    out["side"] = side_panels(th, random.Random(2000 + ti))
    if ti == 0:
        mk = [A.dead_tree, A.tree_big, A.dead_tree, A.bush, A.fern]
    elif ti == 1:
        mk = [A.tree_big, A.tree_big, A.tree_palm, A.bush, A.fern]
    else:
        mk = [A.tree_big, A.dead_tree, A.tree_palm, A.bush, A.fern]
    trees = []
    for i, fn in enumerate(mk):
        src = fn(pal, random.Random(ti * 100 + i))
        trees.append(dict(w=src[1], h=src[2], set=buckets(src, fogc, 5.0 if src[2] > 5 else 3.4)))
    out["trees"] = trees
    ruins = []
    for fn in (A.pillar, A.pillar_broken, A.statue, A.arch_ruin):
        src = fn(pal, random.Random(ti * 100 + 50))
        ruins.append(dict(w=src[1], h=src[2], set=buckets(src, fogc, 4.0)))
    out["ruins"] = ruins
    out["totem"] = buckets(A.totem(pal, random.Random(7)), fogc)
    out["wall"] = buckets(A.hedge_wall(pal, random.Random(ti + 9)), fogc, 4.5)
    ob = {}
    ob["root_small"] = buckets(A.root_small(pal, random.Random(3)), fogc)
    ob["root_big"] = buckets(A.root_big(pal, random.Random(4)), fogc)
    ob["overhang"] = buckets(A.overhang(pal, random.Random(5)), fogc, 4.0)
    ob["gate"] = buckets(A.gate(pal, random.Random(6)), fogc, 4.0)
    ob["fire"] = [buckets(A.fire(pal, random.Random(8), frame=f), fogc) for f in range(3)]
    out["obst"] = ob
    out["coin"] = [buckets(A.coin(pal, None, frame=f), fogc) for f in range(4)]
    out["token"] = {k: buckets(A.token(pal, None, k), fogc) for k in ("magnet", "boost", "shield", "mega")}
    out["ape"] = [buckets(A.apes_body(random.Random(11 + f), f), fogc, 3.3) for f in range(2)]
    return out


# ---- HUD: golden carved style, drawn at vpx resolution ---------------------------------------------------------
GOLD_L, GOLD, GOLD_D, DARK = (255, 232, 130), (226, 170, 48), (140, 92, 20), (28, 40, 34)


def hud_sprite(draw_fn, w, h, ss=8):
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(im), w * ss, h * ss, ss)
    return to_spans(im.resize((w, h), Image.LANCZOS), 0.0, (0, 0, 0), (0, 0))


def digit_sprite(ch, w=6, h=9):
    ss = 8
    font = ImageFont.truetype(BOLD, 9 * ss)
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), ch, font=font)
    x = (w * ss - (bb[2] - bb[0])) // 2 - bb[0]
    y = (h * ss - (bb[3] - bb[1])) // 2 - bb[1]
    for dx, dy in ((-5, 0), (5, 0), (0, -5), (0, 5), (-4, -4), (4, 4), (-4, 4), (4, -4)):
        d.text((x + dx, y + dy), ch, font=font, fill=DARK + (255,))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).text((x, y), ch, font=font, fill=255)
    grad = Image.new("RGBA", im.size)
    gd = ImageDraw.Draw(grad)
    for yy in range(im.size[1]):
        gd.line([(0, yy), (im.size[0], yy)], fill=lerp(GOLD_L, GOLD_D, yy / im.size[1]) + (255,))
    im.paste(grad, (0, 0), mask)
    return to_spans(im.resize((w, h), Image.LANCZOS), 0.0, (0, 0, 0), (0, 0))


def draw_frame(d, W, H, ss):
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=3 * ss, fill=GOLD_D)
    d.rounded_rectangle([ss, ss, W - ss - 1, H - ss - 1], radius=2 * ss, fill=GOLD)
    d.rounded_rectangle([2 * ss, 2 * ss, W - 2 * ss - 1, H - 2 * ss - 1], radius=ss, fill=DARK)
    d.line([(2 * ss, ss), (W - 3 * ss, ss)], fill=GOLD_L, width=ss // 2)


def draw_coin_icon(d, W, H, ss):
    d.ellipse([0, 0, W - 1, H - 1], fill=GOLD_D)
    d.ellipse([ss * 0.6, ss * 0.6, W - ss * 0.6, H - ss * 0.6], fill=GOLD)
    d.ellipse([ss * 1.2, ss * 1.0, W * 0.55, H * 0.5], fill=GOLD_L)


def draw_idol(d, W, H, ss):
    # the golden monkey idol of the real game's counter, as a carved gold face
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=5 * ss, fill=GOLD_D)
    d.rounded_rectangle([ss, ss, W - ss - 1, H - ss - 1], radius=4 * ss, fill=GOLD)
    d.rounded_rectangle([ss * 2, ss * 2, W * 0.5, H * 0.45], radius=3 * ss, fill=GOLD_L)
    for ex in (0.3, 0.7):
        d.ellipse([W * ex - 3 * ss, H * 0.35 - 3 * ss, W * ex + 3 * ss, H * 0.35 + 3 * ss], fill=DARK)
        d.ellipse([W * ex - 1.4 * ss, H * 0.35 - 1.4 * ss, W * ex + 1.4 * ss, H * 0.35 + 1.4 * ss], fill=GOLD_L)
    d.rectangle([W * 0.46, H * 0.4, W * 0.54, H * 0.62], fill=GOLD_D)
    d.rounded_rectangle([W * 0.22, H * 0.68, W * 0.78, H * 0.88], radius=2 * ss, fill=DARK)
    for k in range(5):
        x = W * (0.26 + k * 0.1)
        d.rectangle([x, H * 0.7, x + W * 0.07, H * 0.8], fill=GOLD_L)


def draw_pause(d, W, H, ss):
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=3 * ss, fill=GOLD_D)
    d.rounded_rectangle([ss, ss, W - ss - 1, H - ss - 1], radius=2 * ss, fill=GOLD)
    d.rounded_rectangle([2 * ss, 2 * ss, W - 2 * ss - 1, H - 2 * ss - 1], radius=ss, fill=DARK)
    for x in (0.34, 0.58):
        d.rectangle([W * x, H * 0.28, W * (x + 0.1), H * 0.72], fill=GOLD_L)


def draw_corner(d, W, H, ss):
    # golden carved ornament hugging the top-left edge, with vines hanging off it
    d.rounded_rectangle([0, 0, W * 0.34, H * 0.8], radius=3 * ss, fill=GOLD_D)
    d.rounded_rectangle([ss, ss, W * 0.34 - ss, H * 0.8 - ss], radius=2 * ss, fill=GOLD)
    for k in range(5):
        y = H * (0.06 + k * 0.14)
        d.rounded_rectangle([2 * ss, y, W * 0.34 - 2 * ss, y + H * 0.07], radius=ss, fill=GOLD_L if k % 2 else GOLD_D)
    for k in range(7):
        x0 = W * (0.3 + k * 0.1)
        pts = [(x0, 0)]
        for j in range(1, 12):
            pts.append((x0 + math.sin(j * 0.7 + k) * 2.5 * ss, j * H * 0.07))
        d.line(pts, fill=(36, 92, 44, 255), width=int(ss * 1.3))
        for j in range(2, 12, 2):
            px, py = pts[j]
            d.ellipse([px - 2 * ss, py - ss, px + 2 * ss, py + ss], fill=(60, 130, 56, 255))


def draw_vines(d, W, H, ss):
    for k in range(9):
        x0 = W * (0.1 + k * 0.1)
        ln = H * (0.35 + 0.5 * ((k * 5) % 7) / 7)
        pts = [(x0, 0)]
        for j in range(1, 10):
            pts.append((x0 + math.sin(j * 0.8 + k) * 2.5 * ss, j * ln / 9))
        d.line(pts, fill=(34, 86, 42, 255), width=int(ss * 1.3))
        for j in range(2, 10, 2):
            px, py = pts[j]
            d.ellipse([px - 2 * ss, py - ss, px + 2 * ss, py + ss], fill=(58, 126, 54, 255))


def build():
    data = {"themes": [build_theme(i) for i in range(3)], "zb": ZB}
    fc = (170, 190, 175)
    runner = {}
    for i in range(8):
        runner["run%d" % i] = one(A.explorer(A.run_pose(i / 8 * 2 * math.pi)), RUN_SCALE, fc, foot=0.12)
    for k, p in A.POSES.items():
        runner[k] = one(A.explorer(p), RUN_SCALE, fc, foot=0.12)
    st = A.explorer(A.POSES["stumble_b"])
    for i, ang in enumerate((-20, -45, -70, -90, -98, -95)):
        runner["tumble%d" % i] = one(A.rotated(st, ang), RUN_SCALE, fc, foot=0.12)
    for i, sc in enumerate((0.85, 0.7, 0.55, 0.4, 0.28, 0.16)):
        runner["drop%d" % i] = one(A.rotated(A.explorer(A.POSES["jump_down"]), 0, scale=sc), RUN_SCALE, fc, foot=0.12)
    for name, col in (("bubble", (110, 200, 255)), ("aura", (255, 170, 50))):
        im = Image.new("RGBA", (40, 36), (0, 0, 0, 0))
        dd = ImageDraw.Draw(im)
        dd.ellipse([1, 1, 38, 34], outline=col + (255,), width=2)
        dd.arc([5, 4, 34, 30], 200, 260, fill=(255, 255, 255, 255), width=2)
        runner[name] = to_spans(im, 0.0, fc, (20, 33))
    data["runner"] = runner
    data["pounce"] = [one((A.ape_pounce(None, s), 1.0, 1.0), s, fc) for s in (50, 74, 100)]
    data["hud"] = dict(
        digits=[digit_sprite(str(i)) for i in range(10)],
        frame=hud_sprite(draw_frame, 50, 15),
        coin=hud_sprite(draw_coin_icon, 7, 7),
        idol=hud_sprite(draw_idol, 20, 17),
        pause=hud_sprite(draw_pause, 13, 13),
        corner=hud_sprite(draw_corner, 24, 62),
        vines=hud_sprite(draw_vines, 44, 30),
    )
    save_bundle("g_temple.bin", data)


if __name__ == "__main__":
    build()
    print("ok")
