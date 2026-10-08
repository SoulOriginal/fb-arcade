# Text font bundle: font.bin = {"S": [...], "L": [...]} where index = color * len(CHARS) + CHARS.index(ch).
from buildlib import *

CHARS = " !+-./0123456789:<>?ABCDEFGHIJKLMNOPQRSTUVWXYZ"
COLORS = [(255, 255, 255), (255, 220, 40), (255, 70, 70), (80, 230, 240), (90, 255, 110)]
SIZES = {"S": (24, 40, 32), "L": (48, 80, 64)}
out = {}
for key, (cw, ch, fs) in SIZES.items():
    font = ImageFont.truetype(MONO, fs)
    lst = []
    for col in COLORS:
        for c in CHARS:
            im = Image.new("RGB", (cw, ch))
            ImageDraw.Draw(im).text((cw // 2, ch // 2), c, font=font, fill=col, anchor="mm")
            lst.append(pack(im))
    out[key] = lst
save_bundle("font.bin", out)
print("font ok")
