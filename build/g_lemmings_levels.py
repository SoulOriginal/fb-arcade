# Hand-designed Lemmings levels. Each function paints terrain and returns the metadata the game and the bot use.
# Coordinates are virtual pixels; "ground y" is the first solid row, so a lemming standing there has foot row y-1.
# A plan step tells the bot: which skill, near which x, for a lemming walking in direction dx. Builder/basher
# numbers are tuned to the simulated physics: a builder rises 1 px per 2 px, a stint is 12 bricks.
from g_lemmings_terrain import Painter, DIRT, STEEL, GOLD, MARBLE


def scenery(P, specs):
    for cx, cy, rx, ry in specs:
        P.blob(cx, cy, rx, ry, DIRT)


def level1():
    P = Painter(1600, 11)
    P.wavy(0, 1600, 0, 14, 6, DIRT)
    P.rect(60, 64, 1560, 84, DIRT)
    P.rect(60, 20, 84, 64, STEEL)
    P.rect(1536, 20, 1560, 64, STEEL)
    P.rect(60, 84, 84, 116, DIRT)
    P.rect(1536, 84, 1560, 116, DIRT)
    P.rect(60, 116, 1560, 160, DIRT)
    scenery(P, [(330, 90, 20, 8), (760, 92, 26, 7), (1000, 88, 18, 8), (1300, 91, 24, 8)])
    return P, dict(
        name="JUST DIG!", rating="FUN", n=20, save=12, time=240, rr=55,
        skills=dict(di=3), cam0=130, entrance=(230, 16), exit=(1150, 116), objs=[],
        plan=[dict(s="di", at=620, dx=1, slack=4, ymin=50, ymax=64)])


def level2():
    P = Painter(1600, 12)
    P.wavy(0, 1600, 0, 12, 6, DIRT)
    P.rect(100, 56, 420, 118, DIRT)
    P.rect(100, 56, 124, 118, STEEL)
    P.rect(420, 72, 760, 118, DIRT)
    P.blob(260, 126, 130, 16, DIRT)
    P.blob(590, 128, 140, 14, DIRT)
    scenery(P, [(900, 60, 40, 14), (1100, 100, 60, 18), (1320, 70, 36, 12), (1420, 118, 50, 16)])
    return P, dict(
        name="NOT AS HARD AS IT LOOKS", rating="FUN", n=20, save=13, time=240, rr=50,
        skills=dict(bl=2, bu=2), cam0=250, entrance=(540, 24), exit=(200, 56), objs=[],
        plan=[dict(s="bl", at=740, dx=1, slack=6, ymin=60, ymax=72),
              dict(s="bu", at=442, dx=-1, slack=6, ymin=60, ymax=72)])


def level3():
    P = Painter(1600, 13)
    P.wavy(0, 1600, 0, 14, 7, DIRT)
    P.rect(40, 112, 560, 160, DIRT)
    P.rect(40, 60, 60, 112, STEEL)
    P.rect(260, 64, 310, 112, DIRT)
    P.poly([(560, 112), (602, 70), (602, 112)], DIRT)
    P.rect(602, 70, 1170, 125, DIRT)
    P.rect(560, 112, 640, 160, DIRT)
    P.rect(640, 155, 1170, 160, DIRT)
    P.rect(1130, 40, 1150, 70, STEEL)
    scenery(P, [(1300, 100, 60, 30), (1450, 70, 40, 24)])
    return P, dict(
        name="BASH AND MINE YOUR WAY", rating="TRICKY", n=20, save=14, time=300, rr=60,
        skills=dict(ba=2, mi=2), cam0=0, entrance=(100, 56), exit=(1050, 155), objs=[],
        plan=[dict(s="ba", at=257, dx=1, slack=3, ymin=90, ymax=112),
              dict(s="mi", at=690, dx=1, slack=10, ymin=50, ymax=70)])


def level4():
    P = Painter(1600, 14)
    P.wavy(0, 1600, 0, 12, 5, DIRT)
    P.rect(80, 90, 560, 160, DIRT)
    P.rect(80, 50, 104, 90, STEEL)
    P.rect(578, 90, 602, 160, DIRT)
    P.rect(620, 90, 1100, 160, DIRT)
    P.rect(560, 152, 620, 160, DIRT)
    P.rect(1080, 50, 1100, 90, STEEL)
    scenery(P, [(1300, 90, 50, 20), (1450, 120, 40, 18)])
    return P, dict(
        name="WATER, WATER EVERYWHERE", rating="TAXING", n=14, save=10, time=300, rr=35,
        skills=dict(bl=1, bu=3, bo=1), cam0=250, entrance=(220, 28), exit=(900, 90),
        objs=[dict(kind="water", x=560, y=136, w=18, h=24), dict(kind="water", x=602, y=136, w=18, h=24)],
        plan=[dict(s="bu", at=556, dx=1, slack=3, ymin=60, ymax=90),
              dict(s="bl", at=530, dx=1, slack=22, ymin=60, ymax=90, after=[0]),
              dict(s="bu", at=598, dx=1, slack=3, ymin=60, ymax=90, same=0),
              dict(s="bo", at=530, dx=1, slack=40, ymin=60, ymax=90, target="blocker", when_x=640, after=[2])])


def level5():
    P = Painter(1600, 15)
    P.wavy(0, 1600, 0, 12, 5, DIRT)
    P.rect(60, 50, 500, 160, DIRT)
    P.rect(60, 16, 80, 50, STEEL)
    P.rect(500, 150, 1250, 160, DIRT)
    P.rect(1230, 100, 1250, 150, STEEL)
    P.rect(620, 150, 640, 157, 0)
    P.rect(748, 90, 786, 104, STEEL)
    scenery(P, [(900, 14, 40, 14), (1100, 20, 30, 12)])
    return P, dict(
        name="FIRE AND CRUSH", rating="TAXING", n=16, save=6, time=300, rr=55,
        skills=dict(fl=16, bu=2), cam0=100, entrance=(140, 16), exit=(900, 150),
        objs=[dict(kind="crusher", x=760, y=103), dict(kind="fire", x=620, y=143, w=20, h=14, ky=150)],
        plan=[dict(s="fl", at=480, dx=1, slack=24, ymin=20, ymax=90, n=16),
              dict(s="bu", at=616, dx=1, slack=3, ymin=120, ymax=150, pre=True, reach=45)])


def level6():
    P = Painter(1800, 16)
    P.wavy(0, 1800, 0, 12, 5, DIRT)
    P.rect(60, 120, 640, 160, DIRT)
    P.rect(60, 80, 80, 120, STEEL)
    P.rect(640, 92, 1300, 160, DIRT)
    P.rect(900, 46, 960, 92, DIRT)
    P.rect(1280, 60, 1300, 92, STEEL)
    scenery(P, [(1500, 100, 60, 26), (1650, 60, 40, 20)])
    return P, dict(
        name="STAIRWAY TO THE PLATEAU", rating="TAXING", n=18, save=12, time=360, rr=50,
        skills=dict(bu=3, ba=2), cam0=250, entrance=(300, 62), exit=(1200, 92), objs=[],
        plan=[dict(s="bu", at=593, dx=1, slack=2, ymin=100, ymax=120),
              dict(s="bu", at=0, dx=1, slack=999, ymin=60, ymax=120, same=0),
              dict(s="ba", at=892, dx=1, slack=4, ymin=70, ymax=92)])


def level7():
    P = Painter(1600, 17)
    P.rect(0, 0, 1600, 5, GOLD)
    P.rect(250, 5, 650, 12, GOLD)
    P.rect(330, 48, 600, 51, GOLD)
    P.rect(380, 84, 660, 87, GOLD)
    P.rect(656, 56, 666, 87, GOLD)
    P.rect(340, 120, 600, 123, GOLD)
    P.rect(100, 150, 470, 160, GOLD)
    P.rect(458, 100, 470, 160, GOLD)
    P.rect(200, 100, 250, 125, STEEL)
    P.rect(200, 125, 250, 150, MARBLE)
    P.rect(90, 20, 100, 160, GOLD)
    return P, dict(
        name="TEMPLE ZIGZAG", rating="MAYHEM", n=20, save=15, time=300, rr=55,
        skills=dict(ba=2), cam0=200, entrance=(420, 14), exit=(130, 150), objs=[],
        plan=[dict(s="ba", at=253, dx=-1, slack=3, ymin=130, ymax=150)])


LEVELS = [level1, level2, level3, level4, level5, level6, level7]
