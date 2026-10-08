# Build-time helpers (run on the dev machine with PIL, never on the Pi).
import os, pickle, zlib
from array import array
from PIL import Image, ImageDraw, ImageFont



def _find_font(name):
    # DejaVu ships in a different directory on each distribution; FONT_DIR overrides the search.
    dirs = [os.environ.get("FONT_DIR", ""), "/usr/share/fonts/TTF", "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/dejavu", "/usr/share/fonts/dejavu-sans-fonts", "/Library/Fonts", "C:/Windows/Fonts"]
    for d in dirs:
        path = os.path.join(d, name)
        if d and os.path.exists(path):
            return path
    raise SystemExit("Font %s not found. Install DejaVu fonts or set FONT_DIR to the directory containing it." % name)


BOLD = _find_font("DejaVuSans-Bold.ttf")
MONO = _find_font("DejaVuSansMono-Bold.ttf")


def rgb565(r, g, b):
    return (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)


def pack(img):
    # PIL image -> (w, h, RGB565 little-endian bytes). Black (0,0,0) is the "background" colour:
    # sprites are blitted as opaque rectangles, so draw them on a background that matches the scene.
    it = iter(img.convert("RGB").tobytes())
    a = array("H", ((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3) for r, g, b in zip(it, it, it)))
    return (img.width, img.height, a.tobytes())


def save_bundle(path, data):
    open(path, "wb").write(zlib.compress(pickle.dumps(data, protocol=4), 9))
