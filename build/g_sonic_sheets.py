# Slices sprite frames out of the owner's reference sheets (used only when the sheets are present next to the build,
# see g_sonic_build.py). Nothing from the sheets is stored in source files: only the frame index mapping lives there.
import os
from PIL import Image, ImageDraw, ImageFilter

SHEET_DIR = os.environ.get("SONIC_SHEETS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))
SONIC_SHEET = "sonic2_sheet_ref.png"
DARK_SHEET = "spritesheet_ref.png"


def sheet_path(name):
    p = os.path.join(SHEET_DIR, name)
    return p if os.path.exists(p) else None


def key_sonic(im):
    # The green background of the Sonic sheet is noisy (JPEG-like), so it is keyed by hue, not by one colour.
    rgb = im.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if g > 100 and r < 60 and b < 70 and g > r + 70 and g > b + 60:
                continue
            op[x, y] = (r, g, b, 255)
    # frame border, title strip and the credits box are not sprites
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, w, 24], fill=(0, 0, 0, 0))
    d.rectangle([410, 765, w, h], fill=(0, 0, 0, 0))
    for box in ([0, 0, 3, h], [w - 4, 0, w, h], [0, h - 4, w, h]):
        d.rectangle(box, fill=(0, 0, 0, 0))
    return out


def key_dark(im):
    return im.convert("RGBA")


def components(img, dilate=2, min_area=14):
    # 8-connected clusters of opaque pixels after dilating by `dilate` px so loops and effects that nearly touch stay one frame.
    alpha = img.getchannel("A").point(lambda v: 255 if v > 0 else 0)
    big = alpha.filter(ImageFilter.MaxFilter(2 * dilate + 1)) if dilate else alpha
    w, h = img.size
    bp = big.load()
    ap = alpha.load()
    seen = bytearray(w * h)
    boxes = []
    for y0 in range(h):
        for x0 in range(w):
            if bp[x0, y0] and not seen[y0 * w + x0]:
                st = [(x0, y0)]
                seen[y0 * w + x0] = 1
                x1 = x2 = x0
                y1 = y2 = y0
                area = 0
                while st:
                    x, y = st.pop()
                    if ap[x, y]:
                        area += 1
                    x1, x2, y1, y2 = min(x1, x), max(x2, x), min(y1, y), max(y2, y)
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < w and 0 <= ny < h and bp[nx, ny] and not seen[ny * w + nx]:
                                seen[ny * w + nx] = 1
                                st.append((nx, ny))
                if area >= min_area:
                    boxes.append((x1, y1, x2 + 1, y2 + 1, area))
    return boxes


def merge_fragments(boxes, small=60, reach=14):
    # Sparks and flame bits are separate clusters; they belong to the nearest real frame.
    big = [list(b[:4]) for b in boxes if b[4] >= small]
    for b in boxes:
        if b[4] >= small:
            continue
        best, bd = None, reach + 1
        for t in big:
            dx = max(t[0] - b[2], b[0] - t[2], 0)
            dy = max(t[1] - b[3], b[1] - t[3], 0)
            if max(dx, dy) < bd:
                best, bd = t, max(dx, dy)
        if best is not None:
            best[0], best[1] = min(best[0], b[0]), min(best[1], b[1])
            best[2], best[3] = max(best[2], b[2]), max(best[3], b[3])
    return [tuple(b) for b in big]


def order(boxes, row_gap):
    # reading order: rows by vertical centre, then left to right
    items = sorted(boxes, key=lambda b: (b[1] + b[3]) / 2)
    rows, cur, ref = [], [], None
    for b in items:
        cy = (b[1] + b[3]) / 2
        if ref is None or abs(cy - ref) <= row_gap:
            cur.append(b)
            ref = cy if ref is None else (ref * (len(cur) - 1) + cy) / len(cur)
        else:
            rows.append(cur)
            cur, ref = [b], cy
    if cur:
        rows.append(cur)
    return [b for r in rows for b in sorted(r, key=lambda b: b[0])], [len(r) for r in rows]


def slice_sheet(kind):
    name = SONIC_SHEET if kind == "sonic" else DARK_SHEET
    p = sheet_path(name)
    if p is None:
        return None
    im = Image.open(p)
    img = key_sonic(im) if kind == "sonic" else key_dark(im)
    if kind == "dark":
        # the dark sheet is a 2x pixel-doubled sheet: halve it to get native Mega Drive pixels
        img = img.resize((img.width // 2, img.height // 2), Image.NEAREST)
        boxes = merge_fragments(components(img, 1, 3))
        boxes, rows = order(boxes, 16)
    else:
        boxes = [b[:4] for b in components(img, 1, 14)]
        boxes, rows = order(boxes, 26)
    frames = [img.crop(b) for b in boxes]
    return frames, boxes, rows


def contact_sheet(frames, path, cols=14, scale=2):
    cw = max(f.width for f in frames) + 6
    chh = max(f.height for f in frames) + 14
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cw * cols, chh * rows), (40, 40, 60))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(frames):
        x, y = (i % cols) * cw, (i // cols) * chh
        sheet.paste(f, (x + 3, y + 12), f)
        d.text((x + 3, y + 1), str(i), fill=(255, 255, 0))
    sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST).save(path)
