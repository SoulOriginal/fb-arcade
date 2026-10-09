# Launcher: plays the games in turn, each until it reports it is over, with a transition between them.
# Headless check: GAME_FB=<4147200-byte file> GAME_DIR=<dir with bundles> GAME_FPS=100000 GAME_ONLY=<name>
import gc, importlib, os, signal, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fbcore import *

def _tick():
    time.sleep(1 / FPS)


def tr_crt():
    # Old-TV switch-off: bars close to a bright line, the line shrinks to a dot.
    half, prev = H // 2 - 2, 0
    for i in range(1, 21):
        t = int(half * i / 20)
        fill_rect(0, prev, W, t - prev, 0)
        fill_rect(0, H - t, W, t - prev, 0)
        prev = t
        _tick()
    fill_rect(0, half, W, H - 2 * half, 0xFFFF)
    pw = W
    for i in range(1, 15):
        w = int(W * (1 - i / 14))
        fill_rect((W - pw) // 2, half, (pw - w) // 2, H - 2 * half, 0)
        fill_rect((W + w) // 2, half, (pw - w) // 2 + 1, H - 2 * half, 0)
        pw = w
        _tick()
    fill_rect(0, half, W, H - 2 * half, 0)


def tr_wipe():
    bar = random.choice((0x07FF, 0xF81F, 0xFFE0, 0xFFFF))
    step = H // 30
    for y in range(0, H + step, step):
        fill_rect(0, y, W, step, 0)
        fill_rect(0, y + step, W, 8, bar)
        _tick()
    fill_rect(0, 0, W, H, 0)


def tr_dissolve():
    blocks = [(x, y) for x in range(0, W, 64) for y in range(0, H, 64)]
    random.shuffle(blocks)
    per = len(blocks) // 28 + 1
    for i in range(0, len(blocks), per):
        for x, y in blocks[i:i + per]:
            fill_rect(x, y, 64, 64, 0)
        _tick()


def tr_blinds():
    n, sw = 16, W // 16
    closed = [0] * n
    for i in range(46):
        for k in range(n):
            target = int(H * max(0.0, min(1.0, (i - 2 * k) / 14)))
            if target > closed[k]:
                fill_rect(k * sw, closed[k], sw, target - closed[k], 0)
                closed[k] = target
        _tick()



TRANSITIONS = [tr_crt, tr_wipe, tr_dissolve, tr_blinds]
ONLY = os.environ.get("GAME_ONLY")
NEXT_FILE = "/run/fb-arcade-next"
skip_flag = []


def on_skip(signum, frame):
    # SIGUSR1 ends the current game at once; /run/fb-arcade-next may name the game to play next.
    skip_flag.append(1)


signal.signal(signal.SIGUSR1, on_skip)
ALL = ["snake", "tetris", "bomber", "sonic", "fzero", "moto", "pacman", "invaders", "frogger", "battletoads", "turbo", "tanks", "isaac", "persia", "deadspace", "flappy", "doodle", "redball"]
# A game whose files are not deployed yet is skipped instead of crashing the whole carousel.
NAMES = [n for n in ALL if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "g_%s.py" % n))]
mods = {}
last_tr = last_game = None
FIRST = os.environ.get("GAME_FIRST")
forced = None
while True:
    order = [ONLY] if ONLY else random.sample(NAMES, len(NAMES))
    if forced:
        order, forced = [forced], None
    if len(order) > 1 and order[0] == last_game:
        order.append(order.pop(0))
    if FIRST in order and last_game is None:
        # The very first game after a start is the favourite one; later rounds are shuffled.
        order.remove(FIRST)
        order.insert(0, FIRST)
    for name in order:
        print(name, flush=True)
        if name not in mods:
            mods[name] = importlib.import_module("g_" + name)
        step = mods[name].make()
        while True:
            t0 = time.monotonic()
            if step() or skip_flag:
                break
            time.sleep(max(0, 1 / FPS - (time.monotonic() - t0)))
        print(name, "finished", flush=True)
        # Drop the finished game: sprite bundles are large and several of them together do not fit in a small board's RAM.
        step = None
        mods.pop(name, None)
        sys.modules.pop("g_" + name, None)
        gc.collect()
        last_game = name
        if skip_flag:
            skip_flag.clear()
            wanted = None
            try:
                wanted = open(NEXT_FILE).read().strip()
                os.remove(NEXT_FILE)
            except OSError:
                pass
            forced = wanted if wanted in NAMES else None
        last_tr = random.choice([t for t in TRANSITIONS if t is not last_tr])
        last_tr()
        if forced:
            break
