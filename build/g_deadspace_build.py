# Build script for the Dead Space game: draws every sprite and strip and writes g_deadspace.bin.
# Run from this directory: python3 g_deadspace_build.py
import itertools, time
from buildlib import save_bundle
from g_deadspace_art import *
import g_deadspace_isaac as I
import g_deadspace_mobs as M
import g_deadspace_env as E

t0 = time.time()
out = {}


def sp(cv):
    return rgb565_bytes(cv.done() if hasattr(cv, "done") else cv)


def log(msg):
    print("%5.1fs %s" % (time.time() - t0, msg), flush=True)


# ---- Isaac -----------------------------------------------------------------------------------------------
frames = I.build_frames()
out["isaac"] = {k: [[s, m] for s, m in v] for k, v in frames.items()}
out["isaac_lying"] = {"body": sp(I.lying_bodies(False)), "headless": sp(I.lying_bodies(True))}
out["isaac_pieces"] = {"head": M.rot_variants(I.head_piece()), "arm": M.rot_variants(I.arm_piece())}
out["weapons"] = {k: [list(I.weapon(k, e)) for e in I.ELEV] for k in ("pc", "pulse")}
log("isaac done")

# ---- necromorphs -------------------------------------------------------------------------------------------
mob = {}
sl = {}
for pal in ("pale", "enh", "grey"):
    for lm, am, hd in itertools.product(range(1, 4), range(1, 4), (0, 1)):
        legs, arms = (bool(lm & 1), bool(lm & 2)), (bool(am & 1), bool(am & 2))
        for f in range(4):
            cv = M.slasher(legs, arms, bool(hd), "walk", f / 4, pal)
            sl[(pal, "walk", lm, am, hd, f)] = sp(cv)
        for f in range(3):
            cv = M.slasher(legs, arms, bool(hd), "attack", 0.2 + f * 0.3, pal, atk=f / 2)
            sl[(pal, "attack", lm, am, hd, f)] = sp(cv)
    for am, hd in itertools.product(range(1, 4), (0, 1)):
        arms = (bool(am & 1), bool(am & 2))
        for f in range(4):
            sl[(pal, "crawl", 0, am, hd, f)] = sp(M.slasher((False, False), arms, bool(hd), "crawl", f / 4, pal))
    for lm, am, hd in itertools.product(range(4), range(4), (0, 1)):
        legs, arms = (bool(lm & 1), bool(lm & 2)), (bool(am & 1), bool(am & 2))
        sl[(pal, "dead", lm, am, hd, 0)] = sp(M.slasher_dead(legs, arms, bool(hd), pal))
mob["slasher"] = sl
log("slasher %d" % len(sl))

lp = {}
for pal in ("pale", "enh"):
    for tl, am, hd in itertools.product((0, 1), range(1, 4), (0, 1)):
        arms = (bool(am & 1), bool(am & 2))
        for f in range(4):
            lp[(pal, "crawl", tl, am, hd, f)] = sp(M.leaper(bool(tl), arms, bool(hd), "crawl", f / 4, pal))
        lp[(pal, "air", tl, am, hd, 0)] = sp(M.leaper(bool(tl), arms, bool(hd), "air", 0, pal))
        for f in range(2):
            lp[(pal, "whip", tl, am, hd, f)] = sp(M.leaper(bool(tl), arms, bool(hd), "whip", 0.1, pal, atk=0.2 + 0.6 * f))
    for tl, am, hd in itertools.product((0, 1), range(4), (0, 1)):
        arms = (bool(am & 1), bool(am & 2))
        lp[(pal, "dead", tl, am, hd, 0)] = sp(M.leaper_dead(bool(tl), arms, bool(hd), pal))
mob["leaper"] = lp
log("leaper %d" % len(lp))

lk = {}
for tm in range(8):
    tend = (bool(tm & 1), bool(tm & 2), bool(tm & 4))
    for mode in ("hang", "fire"):
        for f in range(2):
            lk[(tm, mode, f)] = sp(M.lurker(tend, mode, f / 2))
mob["lurker"] = lk
mob["infector"] = {f: sp(M.infector(f / 4)) for f in range(4)}
mob["exploder"] = {(b, f, p): sp(M.exploder(bool(b), f / 4, pul=p)) for b in (0, 1) for f in range(4) for p in (0, 1)}
pg = {}
for sm in range(8):
    sk = (bool(sm & 1), bool(sm & 2), bool(sm & 4))
    for f in range(4):
        pg[(sm, "walk", f)] = sp(M.pregnant(sk, "walk", f / 4))
    for f in range(2):
        pg[(sm, "attack", f)] = sp(M.pregnant(sk, "attack", 0.3 + f * 0.3))
mob["pregnant"] = pg
mob["spawn"] = {f: sp(M.spawn(f / 3)) for f in range(3)}
br = {}
for pal in ("dark", "pale"):
    for f in range(4):
        br[(pal, "walk", f)] = sp(M.brute("walk", f / 4, pal))
    for f in range(3):
        br[(pal, "charge", f)] = sp(M.brute("charge", f / 3, pal))
        br[(pal, "attack", f)] = sp(M.brute("attack", 0.3, pal, atk=f / 2))
    cv = Cv(90, 30)
    p = M.PALS[pal]
    cv.poly([(6, 18), (20, 6), (60, 5), (80, 14), (84, 24), (6, 26)], p["flesh"], OUTLINE, 1.0)
    cv.poly([(26, 10), (50, 9), (52, 20), (28, 20)], MUSCLE, MUSCLE_D, 0.6)
    cv.poly([(56, 14), (82, 14), (84, 22), (56, 22)], BONE_D, OUTLINE, 0.8)
    splat(cv, 40, 26, 14, BLOOD, 16, 3)
    br[(pal, "dead", 0)] = sp(cv)
mob["brute"] = br
hn = {}
for am, lm in itertools.product(range(4), range(4)):
    arms, legs = (bool(am & 1), bool(am & 2)), (bool(lm & 1), bool(lm & 2))
    for f in range(4):
        hn[(am, lm, "walk", f)] = sp(M.hunter(arms, legs, "walk", f / 4))
    for f in range(3):
        hn[(am, lm, "attack", f)] = sp(M.hunter(arms, legs, "attack", 0.2, atk=f / 2))
mob["hunter"] = hn
out["mob"] = mob
log("mobs done")

# bosses and large set pieces
out["ctent"] = {(pose, node): sp(M.ctentacle(pose, bool(node))) for pose in range(4) for node in (0, 1)}
out["ctent_node"] = {pose: M.ctentacle(pose, True).node for pose in range(4)}
out["levi_body"] = sp(M.leviathan_body())
out["hive_body"] = sp(M.hive_body())
out["bulb"] = {r: sp(M.bulb(r)) for r in (4, 6, 8)}
out["marker"] = sp(E.marker_prop())

pieces = {}
for kind in ("blade", "leg", "head", "claw", "tail"):
    for pal in ("pale", "enh"):
        pieces[(kind, pal)] = M.rot_variants(M.piece(kind, pal))
for kind in ("tendril", "bulb", "sack", "canister"):
    pieces[(kind, "pale")] = M.rot_variants(M.piece(kind))
pieces[("grate", "pale")] = M.rot_variants(E.grate_piece())
out["piece"] = pieces
log("pieces done")

# ---- environment -------------------------------------------------------------------------------------------------
out["env"] = []
for i in range(len(E.CHAPTERS)):
    out["env"].append(E.build_chapter(i))
    log("chapter %d art" % i)
out["chapters"] = [dict(name=c["name"], sub=c["sub"], kind=c["kind"]) for c in E.CHAPTERS]

props = {
    "vent": [sp(E.vent(0)), sp(E.vent(1))],
    "crate": [sp(E.crate(0)), sp(E.crate(1))],
    "locker": [sp(E.locker(0)), sp(E.locker(1))],
    "door": [sp(E.door(i)) for i in range(5)],
    "bench": sp(E.bench()),
    "save": [sp(E.savepoint(i)) for i in range(2)],
    "pickup": {k: sp(E.pickup(k)) for k in ("health", "plasma", "pulse", "credit", "node", "stasis")},
    "corpse": [sp(E.corpse(i)) for i in range(3)],
    "barrel": sp(E.barrel()),
    "steam": [[rgb565_bytes(E.steam_puff(r, d)) for d in (0, 1)] for r in (3, 5, 7, 9, 12)],
    "ring": [rgb565_bytes(E.ring(r, (110, 200, 255))) for r in (8, 12, 17, 23, 30)],
    "flash": [sp(E.flash(r)) for r in (3, 5, 8, 12)],
    "pillar": sp(E.pillar()),
}
chars, gl = E.glyph_font()
props["glyph_chars"] = chars
props["glyph"] = gl
out["props"] = props
save_bundle("g_deadspace.bin", out)
log("saved")
