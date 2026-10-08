# Shared runtime for the framebuffer games (1920x1080, RGB565 little-endian, 3840 bytes per scanline).
# Every game module imports * from here and exposes make() -> step(); step() is called once per tick
# (30 per second) and returns True when the game is over and its result screen has been shown.
import mmap, os, pickle, random, time, zlib

W, H, S = 1920, 1080, 3840
TICK_RATE = 30
HEADLESS = "GAME_FB" in os.environ
FPS = float(os.environ.get("GAME_FPS", "30"))
HERE = os.environ.get("GAME_DIR", os.path.dirname(os.path.abspath(__file__)))


def _check_framebuffer():
    # The games draw raw 1920x1080 RGB565 scanlines; any other mode would produce garbage, so fail loudly.
    base = "/sys/class/graphics/fb0"
    try:
        size = open(base + "/virtual_size").read().strip()
        bpp = int(open(base + "/bits_per_pixel").read())
        stride = int(open(base + "/stride").read())
    except OSError:
        return
    if (size, bpp, stride) != ("1920,1080", 16, 3840):
        raise SystemExit("fb-arcade needs a 1920x1080 16 bpp framebuffer (stride 3840); found %s, %d bpp, stride %d. "
                         "Set the resolution and colour depth in your boot configuration." % (size, bpp, stride))


if not HEADLESS:
    _check_framebuffer()
fd = os.open(os.environ.get("GAME_FB", "/dev/fb0"), os.O_RDWR)
fb = mmap.mmap(fd, S * H)


def prep(t):
    w, h, b = t
    return (w, h, [b[j * w * 2:(j + 1) * w * 2] for j in range(h)])


def load_bundle(name):
    # name: file in HERE, e.g. "g_bomber.bin". Lists of (w, h, bytes) become sprites (w, h, rows);
    # everything else (ints, strings, nested data) is returned unchanged.
    raw = pickle.loads(zlib.decompress(open(os.path.join(HERE, name), "rb").read()))

    def conv(v):
        if isinstance(v, tuple) and len(v) == 3 and isinstance(v[2], (bytes, bytearray)):
            return prep(v)
        if isinstance(v, list):
            return [conv(i) for i in v]
        if isinstance(v, dict):
            return {k: conv(i) for k, i in v.items()}
        return v
    return {k: conv(v) for k, v in raw.items()}


def rgb565(r, g, b):
    return (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)


def clear(c565=0):
    if c565 == 0:
        fb[:] = bytes(S * H)
    else:
        fb[:] = c565.to_bytes(2, "little") * (W * H)


def blit(s, x, y):
    # Clipped at the screen edges: a write past the right edge would wrap into the next scanline.
    w, h, rows = s
    x0, x1, y0, y1 = max(0, -x), min(w, W - x), max(0, -y), min(h, H - y)
    if x1 <= x0 or y1 <= y0:
        return
    for j in range(y0, y1):
        o = (y + j) * S + (x + x0) * 2
        fb[o:o + (x1 - x0) * 2] = rows[j][x0 * 2:x1 * 2]


def fill_rect(x, y, w, h, c565):
    x0, x1, y0, y1 = max(0, x), min(W, x + w), max(0, y), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    row = c565.to_bytes(2, "little") * (x1 - x0)
    for j in range(y0, y1):
        fb[j * S + x0 * 2:j * S + x1 * 2] = row


def write_row(y, data, x=0):
    # data: bytes of RGB565 pixels; clipped to the screen.
    if not 0 <= y < H:
        return
    x0 = max(0, -x)
    n = min(len(data) // 2 - x0, W - max(x, 0))
    if n > 0:
        o = y * S + (x + x0) * 2
        fb[o:o + n * 2] = data[x0 * 2:(x0 + n) * 2]


# ---- text -------------------------------------------------------------------------------------
CHARS = " !+-./0123456789:<>?ABCDEFGHIJKLMNOPQRSTUVWXYZ"
COLOR_WHITE, COLOR_YELLOW, COLOR_RED, COLOR_CYAN, COLOR_GREEN = range(5)
CELL = {"S": (24, 40), "L": (48, 80)}
_font = load_bundle("font.bin")


def text_width(s, size="S"):
    return len(s) * CELL[size][0]


def draw_text(s, x, y, size="S", color=COLOR_WHITE, bg=True):
    # bg=True clears the text box first so a changing number does not leave old digits behind.
    cw, ch = CELL[size]
    if bg:
        fill_rect(x, y, cw * len(s), ch, 0)
    for i, c in enumerate(s.upper()):
        k = CHARS.find(c)
        if k > 0:
            blit(_font[size][color * len(CHARS) + k], x + i * cw, y)


def draw_text_centered(s, y, size="L", color=COLOR_WHITE):
    draw_text(s, (W - text_width(s, size)) // 2, y, size, color)


# ---- game flow ----------------------------------------------------------------------------------
CAP_SECONDS = float(os.environ.get("GAME_CAP", "540"))   # 9 minutes: hard limit per game
CAP_TICKS = int(CAP_SECONDS * TICK_RATE)


class EndScreen:
    # Result screen: call start(score) once, then tick() every step until it returns True.
    def __init__(self, hold_ticks=150):
        self.t = None
        self.hold = hold_ticks

    def start(self, score, title="GAME OVER"):
        fill_rect(W // 2 - 520, H // 2 - 170, 1040, 340, 0)
        fill_rect(W // 2 - 520, H // 2 - 170, 1040, 6, 0xFFFF)
        fill_rect(W // 2 - 520, H // 2 + 164, 1040, 6, 0xFFFF)
        draw_text_centered(title, H // 2 - 130, "L", COLOR_RED)
        draw_text_centered("SCORE %d" % score, H // 2 + 10, "L", COLOR_YELLOW)
        self.t = 0

    def tick(self):
        self.t += 1
        return self.t > self.hold
