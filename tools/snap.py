# Converts a raw RGB565 framebuffer dump to a 1280x720 PNG (for looking at what a game draws).
import sys
from PIL import Image


def save_snapshot(raw_path, png_path, size=(1280, 720)):
    d = open(raw_path, "rb").read()
    im = Image.frombuffer("RGB", (1920, 1080), b"".join(
        bytes(((v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3)) for v in memoryview(d).cast("H")), "raw", "RGB", 0, 1)
    im.resize(size).save(png_path)


if __name__ == "__main__":
    save_snapshot(sys.argv[1], sys.argv[2])
