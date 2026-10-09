# Build script for the Red Ball game: draws every sprite, tile and background with PIL and writes g_redball.bin.
# Run from this directory: python3 g_redball_build.py
import sys, time
from buildlib import save_bundle
from g_redball_art import *
from g_redball_art2 import *
import g_redball_bg as bgmod
import g_redball_chunks as chunks


def main():
    t0 = time.time()
    out = {}
    out["ball"] = build_ball()
    out["minion"] = build_minions()
    out["boss"] = build_bosses()
    out["tiles"] = build_tiles()
    out["liquid"] = build_liquids()
    out["slope"] = {w: {k: sprite(slope_img(w, k)) for k in "/\\"} for w in WORLDS}
    out["decor"] = {w: decor(w) for w in WORLDS}
    out["bg"] = {w: bgmod.build_bg(w) for w in WORLDS}
    o = {}
    o["star"] = [sprite(star_img(k)) for k in (1.0, 0.8, 0.5, 0.2, 0.5, 0.8)]
    o["flag_off"] = [sprite(flag_img("off", 0))]
    o["flag_on"] = [sprite(flag_img("on", f)) for f in range(4)]
    o["portal"] = [sprite(portal_img(f)) for f in range(6)]
    o["spike_up"] = sprite(spikes_img("up"))
    o["spike_down"] = sprite(spikes_img("down"))
    o["saw"] = [sprite(saw_img(f)) for f in range(6)]
    o["crusher"] = sprite(crusher_img())
    o["shaft"] = sprite(shaft_img())
    o["cannon"] = {d: [sprite(cannon_img(d, f)) for f in (0, 1)] for d in "LR"}
    o["shot"] = sprite(ball_shot())
    o["laser"] = {d: sprite(laser_emit(d)) for d in "LRUD"}
    o["button"] = {g: [sprite(button_img(g, p)) for p in (0, 1)] for g in (1, 2, 3, 4)}
    o["gate"] = {g: {n: sprite(gate_img(g, n)) for n in (2, 3, 4, 5)} for g in (1, 2, 3, 4)}
    o["lever"] = {g: [sprite(lever_img(g, p)) for p in (0, 1)] for g in (1, 2, 3, 4)}
    o["spring"] = [sprite(spring_img(s)) for s in (0, 1, 2)]
    o["crate"] = [sprite(crate_img(m)) for m in (0, 1)]
    o["boulder"] = [sprite(boulder_img(f)) for f in range(8)]
    o["platform"] = {w: sprite(platform_img(w)) for w in WORLDS}
    o["fallplat"] = {w: sprite(fallplat_img(w)) for w in WORLDS}
    o["seesaw"] = {a: sprite(seesaw_plank(a)) for a in range(-18, 19, 3)}
    o["pivot"] = sprite(pivot_img())
    o["stone"] = sprite(stone_img())
    o["gear"] = {c: [sprite(gear_img(f, r, 12, col)) for f in range(8)] for c, (r, col) in {"s": (50, (96, 104, 134)), "l": (90, (84, 92, 120))}.items()}
    o["burst"] = [sprite(burst_img(f)) for f in range(6)]
    o["puff"] = [sprite(puff_img(f)) for f in range(4)]
    o["sparkle"] = [sprite(sparkle_img(f)) for f in range(4)]
    o["chip"] = [sprite(chip_img(c)) for c in ((228, 34, 38), (255, 170, 60), (255, 230, 120), (250, 250, 250))]
    o["glyph"] = glyphs(40)
    o["glyph_big"] = glyphs(84)
    o.update(hud_icons())
    out["obj"] = o
    out["chunks"] = chunks.all_chunks()
    save_bundle("g_redball.bin", out)
    print("built in %.0f s" % (time.time() - t0))


main()
