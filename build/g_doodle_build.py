# Builds g_doodle.bin: notebook-paper tile, decorative side margins and every sprite of the Doodle Jump reproduction.
import math, random
from PIL import Image, ImageDraw
from buildlib import save_bundle, rgb565
import g_doodle_art as A
from g_doodle_art import K, U, INK, PAPER, GRID, Pic, sprite

PW = 640
PERIOD = 16 * U            # grid pitch in pixels: 16 logical units
rnd = random.Random(99)


def raw565(im):
    it = iter(im.convert("RGB").tobytes())
    return b"".join(rgb565(r, g, b).to_bytes(2, "little") for r, g, b in zip(it, it, it))


def paper_tile():
    # Exactly PERIOD rows tall, so the game scrolls by slicing a repeated strip at (offset mod PERIOD).
    im = Image.new("RGB", (PW, PERIOD), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, PW, 1), fill=GRID)
    for x in range(0, PW, PERIOD):
        d.rectangle((x, 0, x + 1, PERIOD), fill=GRID)
    return raw565(im)


def margin(left):
    # Decorative page edges. They do not scroll: the play area is the "page" and these are the desk-side bits of the
    # notebook, so a small mismatch of the ruling with the scrolling grid reads as a different sheet.
    im = Image.new("RGB", (PW, 1080), (244, 240, 206))
    d = ImageDraw.Draw(im)
    for y in range(40, 1080, 48):
        d.line((0, y, PW, y), fill=(176, 206, 214), width=2)
    pencil = (92, 92, 88)

    def scribble(cx, cy, kind):
        p = Pic(80, 80)
        if kind == "star":
            pts = [(40 + (30 if k % 2 == 0 else 13) * math.cos(k * math.pi / 5 - 1.57),
                    40 + (30 if k % 2 == 0 else 13) * math.sin(k * math.pi / 5 - 1.57)) for k in range(10)]
            p.poly(pts, None, pencil, 1.1, 0.7)
        elif kind == "spiral":
            pts = [(40 + (1.2 + t * 0.55) * math.cos(t * 0.5), 40 + (1.2 + t * 0.55) * math.sin(t * 0.5)) for t in range(60)]
            p.line(pts, pencil, 1.1, 0.25)
        elif kind == "arrow":
            p.line([(8, 60), (30, 38), (50, 44), (72, 14)], pencil, 1.2, 0.8)
            p.line([(60, 14), (72, 14), (70, 28)], pencil, 1.2, 0.5)
        elif kind == "face":
            p.blob(40, 40, 26, 26, None, pencil, 1.1, 0.7)
            p.dot(31, 34, 2.5, pencil)
            p.dot(49, 34, 2.5, pencil)
            p.line([(28, 50), (40, 58), (52, 50)], pencil, 1.1, 0.4)
        elif kind == "cloud":
            for i, (x, y, r) in enumerate(((28, 46, 12), (42, 38, 15), (56, 46, 11), (40, 50, 14))):
                p.blob(x, y, r, r * 0.8, None, pencil, 1.0, 0.5)
        im2 = A.final(p)
        im.paste(im2, (cx - im2.width // 2, cy - im2.height // 2), im2)

    if left:
        edge = PW - 70
        d.line((edge, 0, edge, 1080), fill=(226, 90, 90), width=3)
        d.line((edge + 10, 0, edge + 10, 1080), fill=(226, 90, 90), width=3)
        for y in (180, 540, 900):
            d.ellipse((60, y - 30, 120, y + 30), fill=(62, 58, 52))
            d.ellipse((66, y - 25, 116, y + 27), fill=(120, 116, 104))
            d.ellipse((70, y - 22, 114, y + 22), fill=(40, 40, 38))
        for y, k in ((90, "star"), (330, "face"), (730, "spiral"), (1000, "cloud")):
            scribble(rnd.randint(230, 400), y, k)
    else:
        for y, k in ((130, "cloud"), (320, "arrow"), (560, "star"), (780, "face"), (980, "spiral")):
            scribble(rnd.randint(200, 460), y, k)
    out = im.copy()
    px = out.load()
    # soft shadow of the page edge next to the play area
    for i in range(18):
        f = 0.22 * (1 - i / 18)
        x = PW - 1 - i if left else i
        for y in range(1080):
            r, g, b = px[x, y]
            px[x, y] = (int(r * (1 - f)), int(g * (1 - f)), int(b * (1 - f)))
    return raw565(out)


def main():
    D = {}
    D["tile"] = paper_tile()
    D["margin_l"] = margin(True)
    D["margin_r"] = margin(False)

    legs = (4, 10, 16)
    dj = [[], []]
    base_mid = A.doodler(10)
    for pose, leg in enumerate(legs):
        r = A.doodler(leg, 0)
        dj[1].append(A.spans(A.final(r)))
        dj[0].append(A.spans(A.final(A.flip(r))))
    for leg in legs:
        r = A.doodler(leg, -82)
        dj[1].append(A.spans(A.final(r)))
        dj[0].append(A.spans(A.final(A.flip(r))))
    D["dj"] = dj
    D["hat"] = [[A.spans(A.final(A.flip(A.doodler(10, 0, hat=f)))) for f in (1, 2)],
                [A.spans(A.final(A.doodler(10, 0, hat=f))) for f in (1, 2)]]
    D["pack"] = [[A.spans(A.final(A.flip(A.doodler(10, 0, pack=f)))) for f in (1, 2)],
                 [A.spans(A.final(A.doodler(10, 0, pack=f))) for f in (1, 2)]]
    D["spin"] = [A.spin_frames(A.flip(base_mid)), A.spin_frames(base_mid)]
    D["suck"] = [A.spin_frames(base_mid, 12, s) for s in (0.75, 0.5, 0.3)]
    D["shield"] = [A.shield(0), A.shield(1)]
    D["stars"] = [A.stars(0), A.stars(1)]

    D["plat"] = {k: [A.platform(k, 0)] for k in ("green", "blue", "gray", "white", "yellow")}
    D["plat"]["red"] = [A.platform("red", 0), A.platform("red", 1)]
    D["plat"]["brown"] = [A.platform("brown", f) for f in range(4)]
    D["spring"] = [A.spring(False), A.spring(True)]
    D["tramp"] = [A.trampoline(False), A.trampoline(True)]
    D["i_prop"], D["i_jet"], D["i_shield"] = A.item_propeller(), A.item_jetpack(), A.item_shield()
    D["mon"] = [[A.monster(k, f) for f in (0, 1)] for k in range(3)]
    D["ufo"] = [A.ufo(0), A.ufo(1)]
    D["hole"] = [A.blackhole(f) for f in range(4)]
    D["puff"] = [A.puff(f) for f in range(3)]
    D["boom"] = [A.boom(f) for f in range(3)]
    D["bullet"] = A.bullet()

    D["digits_s"] = A.digit_sprites(18)
    D["digits_l"] = A.digit_sprites(24)
    D["t_gameover"] = A.text_sprite("game over!", 34)
    D["t_score"] = A.text_sprite("your score:", 19)
    D["t_high"] = A.text_sprite("your high score:", 19)
    D["t_hs"] = A.text_sprite("high score", 10, (90, 90, 86))
    D["b_again"] = A.button("play again")

    p = Pic(18, 18)
    p.rrect(3, 2, 7.5, 16, 1.5, (70, 78, 70), None)
    p.rrect(10.5, 2, 15, 16, 1.5, (70, 78, 70), None)
    D["pause"] = sprite(p)
    save_bundle("g_doodle.bin", D)


main()
