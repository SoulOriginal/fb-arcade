# Builds g_gpc.bin: all pictures of the Grand Prix Circuit clone (see g_gpc_art.py).
import g_gpc_art as A
import g_gpc_tracks as TK
from buildlib import save_bundle

font = A.make_font()
STYLE_SEED = {n: i * 17 + 3 for i, n in enumerate(TK.NAMES)}
bundle = dict(
    pal=A.PAL,
    font=font,
    sky=A.sky_rows(),
    lamps=A.lamp_frames(font),
    mapbase=A.mapbox_base(),
    infobase=A.infobox_base(),
    dash=[A.dash_frame(k, font) for k in range(-4, 5)],
    knob=A.knob_sprite(),
    cars=A.car_sprites(),
    mcars=A.mirror_cars(),
    objs=A.object_sprites(),
    horizon={n: A.horizon_strip(TK.CIRCUITS[n]["style"], STYLE_SEED[n]) for n in TK.NAMES},
)
save_bundle("g_gpc.bin", bundle)
import os
print("g_gpc.bin", os.path.getsize("g_gpc.bin"), "bytes")
