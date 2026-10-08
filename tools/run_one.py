# Headless runner for one game, no sleeping, no display. Usage (after `make build`):
#   python3 tools/run_one.py <game> [max_ticks] [snapshot_every_ticks]
# Prints ticks, CPU per tick and whether the game finished by itself; writes snap_<game>_<tick>.png (needs Pillow).
import importlib, os, sys, tempfile, time

here = os.path.dirname(os.path.abspath(__file__))
dist = os.path.join(here, "..", "dist")
name = sys.argv[1]
max_ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 30 * 600
snap_every = int(sys.argv[3]) if len(sys.argv) > 3 else 0
scratch = tempfile.NamedTemporaryFile(delete=False)
scratch.write(bytes(1920 * 1080 * 2))
scratch.close()
os.environ.update(GAME_FB=scratch.name, GAME_DIR=os.path.abspath(dist), GAME_FPS="100000")
sys.path.insert(0, os.path.abspath(dist))
sys.path.insert(0, here)
mod = importlib.import_module("g_" + name)
from snap import save_snapshot

step = mod.make()
t0 = time.process_time()
ticks = 0
done = False
while ticks < max_ticks:
    ticks += 1
    if step():
        done = True
        break
    if snap_every and ticks % snap_every == 0:
        save_snapshot(scratch.name, "snap_%s_%d.png" % (name, ticks))
save_snapshot(scratch.name, "snap_%s_end.png" % name)
os.unlink(scratch.name)
cpu = time.process_time() - t0
print("%s: done=%s ticks=%d (%.0f s of play) cpu=%.1f s, %.2f ms/tick" % (name, done, ticks, ticks / 30, cpu, 1000 * cpu / ticks))
sys.exit(0 if done else 1)
