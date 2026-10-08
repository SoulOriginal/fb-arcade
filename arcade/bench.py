# On-device benchmark: runs one game headless against a scratch file and prints CPU time per tick.
# Usage (from the install directory): python3 bench.py <game> [ticks]
import importlib, os, sys, tempfile, time

name = sys.argv[1]
ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 1800
here = os.path.dirname(os.path.abspath(__file__))
scratch = tempfile.NamedTemporaryFile(delete=False)
scratch.write(bytes(1920 * 1080 * 2))
scratch.close()
os.environ.update(GAME_FB=scratch.name, GAME_DIR=here, GAME_FPS="100000")
sys.path.insert(0, here)
step = importlib.import_module("g_" + name).make()
worst = total = 0.0
n = 0
done = False
while n < ticks and not done:
    t0 = time.process_time()
    done = step()
    dt = time.process_time() - t0
    total += dt
    worst = max(worst, dt)
    n += 1
os.unlink(scratch.name)
print("%-12s ticks=%d avg=%.1f ms worst=%.1f ms done=%s" % (name, n, 1000 * total / n, 1000 * worst, done))
