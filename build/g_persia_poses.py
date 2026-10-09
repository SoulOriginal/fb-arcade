# Build-time only: key poses and the animation sequences made of them. Every sequence carries its own per-frame
# horizontal deltas (dx, pixels in the facing direction) and vertical offsets (dy, absolute from the sequence
# start), so motion speed and animation are authored in one place and exported to the game as data.
import math
from g_persia_rig import P, STAND, sequence, mirror_limbs

stand = P()

# ---- running -------------------------------------------------------------------------------------------------
RC = P(lean=14, head=-4, ra_s=38, ra_e=75, fa_s=-38, fa_e=45, rl_t=-34, rl_k=-38, fl_t=40, fl_k=-6)
RP = P(lean=15, head=-4, ra_s=10, ra_e=70, fa_s=-8, fa_e=60, rl_t=12, rl_k=-88, fl_t=4, fl_k=0)
RC2, RP2 = mirror_limbs(RC), mirror_limbs(RP)
RUN_CYCLE = sequence([(RC, 4), (RP, 4), (RC2, 4), (RP2, 4)], loop=True)          # 16 frames, contacts at 0 and 8
RUN_DX = 3.6

S1 = P(lean=8, head=-2, ra_s=-10, ra_e=40, fa_s=14, fa_e=40, rl_t=-14, rl_k=-14, fl_t=18, fl_k=-4)
START = sequence([(stand, 3), (S1, 3), (RP, 3), (RC2, 0)])[:-1]                      # 9 frames, then cycle at 8
START_DX = [0.5, 0.9, 1.3, 1.7, 2.1, 2.5, 2.9, 3.2, 3.5]

STOP1 = P(lean=-2, head=0, ra_s=26, ra_e=40, fa_s=-26, fa_e=30, rl_t=-18, rl_k=-20, fl_t=28, fl_k=-4)
STOP2 = P(lean=0, ra_s=4, ra_e=24, fa_s=-4, fa_e=24, rl_t=-6, rl_k=-6, fl_t=12, fl_k=0)
STOP = sequence([(RC, 2), (STOP1, 3), (STOP2, 3), (stand, 1)])
STOP_DX = [3.4, 3.0, 2.6, 2.1, 1.6, 1.1, 0.7, 0.4, 0.1]

NARROW = P(lean=0, ra_s=2, ra_e=18, fa_s=-2, fa_e=18, rl_t=1, rl_k=0, fl_t=-1, fl_k=0)
TURN = sequence([(stand, 1), (NARROW, 2), (NARROW, 0)]) + sequence([(NARROW, 2), (stand, 0)])
TURN_FLIP = 3

SKID = P(lean=-10, head=2, ra_s=60, ra_e=30, fa_s=-50, fa_e=20, rl_t=-18, rl_k=-22, fl_t=36, fl_k=0)
RUNTURN = sequence([(RC, 3), (SKID, 3), (NARROW, 1), (NARROW, 0)]) + sequence([(NARROW, 1), (S1, 2), (RC, 0)])
RUNTURN_DX = [3.2, 3.0, 2.8, 2.4, 1.8, 1.2, 0.0, 0.0, 1.0, 2.0, 3.0, 3.4]
RUNTURN_FLIP = 7

STEP1 = P(lean=3, ra_s=-12, ra_e=14, fa_s=12, fa_e=14, rl_t=-12, rl_k=-6, fl_t=22, fl_k=-6)
STEP2 = P(lean=2, ra_s=-4, ra_e=12, fa_s=4, fa_e=12, rl_t=14, rl_k=-30, fl_t=10, fl_k=0)
STEP = sequence([(stand, 2), (STEP1, 2), (STEP2, 2), (stand, 0)])
STEP_DX = [0.0, 0.5, 1.5, 2.0, 1.0, 0.8, 0.5, 0.0, 0.0][:len(STEP)]


# ---- jumping -------------------------------------------------------------------------------------------------
CROUCH = P(lean=26, head=-8, ra_s=-30, ra_e=70, fa_s=36, fa_e=70, rl_t=-34, rl_k=-100, fl_t=50, fl_k=-104)
SJ_PUSH = P(lean=14, head=-6, ra_s=-50, ra_e=10, fa_s=60, fa_e=40, rl_t=-30, rl_k=-10, fl_t=34, fl_k=-70)
SJ_AIR1 = P(lean=6, head=-4, ra_s=-40, ra_e=0, fa_s=125, fa_e=10, rl_t=-26, rl_k=-14, fl_t=62, fl_k=-30)
SJ_AIR2 = P(lean=16, head=-2, ra_s=40, ra_e=60, fa_s=70, fa_e=50, rl_t=24, rl_k=-100, fl_t=44, fl_k=-110)
SJ_LAND = P(lean=18, head=-4, ra_s=20, ra_e=50, fa_s=40, fa_e=50, rl_t=-14, rl_k=-60, fl_t=40, fl_k=-30)
LAND_C = P(lean=30, head=-10, ra_s=10, ra_e=60, fa_s=30, fa_e=60, rl_t=-24, rl_k=-90, fl_t=50, fl_k=-96)


def arc(n, peak):
    return [-4 * peak * (i / (n - 1)) * (1 - i / (n - 1)) if n > 1 else 0.0 for i in range(n)]


STAND_JUMP = (sequence([(stand, 2), (CROUCH, 2), (SJ_PUSH, 2), (SJ_AIR1, 3), (SJ_AIR2, 3), (SJ_LAND, 3), (LAND_C, 2), (stand, 0)]))
n_sj = len(STAND_JUMP)           # 18
SJ_DX = [0, 0, 0, 0, 2, 3, 9, 11, 12, 12, 11, 10, 5, 2, 1, 0, 0, 0]
SJ_TAKEOFF_AT, SJ_LAND_AT = 5, 12  # last grounded frame before the leap, first frame with feet down again
SJ_DY = [0] * 5 + arc(8, 14) + [0] * (n_sj - 13)

RJ_PUSH = P(lean=22, head=-8, ra_s=-36, ra_e=20, fa_s=62, fa_e=44, rl_t=-38, rl_k=-6, fl_t=34, fl_k=-74)
RJ_AIR1 = P(lean=8, head=-4, ra_s=-50, ra_e=0, fa_s=128, fa_e=6, rl_t=-30, rl_k=-16, fl_t=66, fl_k=-26)
RJ_AIR2 = P(lean=18, head=-2, ra_s=36, ra_e=60, fa_s=64, fa_e=50, rl_t=28, rl_k=-104, fl_t=46, fl_k=-116)
RJ_LAND = P(lean=24, head=-6, ra_s=30, ra_e=60, fa_s=-20, fa_e=40, rl_t=-26, rl_k=-50, fl_t=44, fl_k=-22)
RUN_JUMP = sequence([(RC, 3), (RJ_PUSH, 3), (RJ_AIR1, 4), (RJ_AIR2, 3), (RJ_LAND, 3), (LAND_C, 3), (RC2, 0)])
n_rj = len(RUN_JUMP)             # 20
RJ_DX = [3.6, 3.6, 3.6, 3.6, 4.0, 6.0, 14, 15, 15, 14, 16, 15, 14, 9, 5, 3, 1.5, 0.8, 1.8, 3.0]
RJ_TAKEOFF_AT, RJ_LAND_AT = 5, 13
RJ_DY = [0] * 5 + arc(9, 15) + [0] * (n_rj - 14)

# ---- ledges ----------------------------------------------------------------------------------------------------
REACH = P(lean=-2, head=-10, ra_s=165, ra_e=6, fa_s=172, fa_e=4, rl_t=-6, rl_k=-20, fl_t=8, fl_k=-30)
HANG1 = P(lean=-4, head=-12, ra_s=172, ra_e=2, fa_s=176, fa_e=2, rl_t=-8, rl_k=-14, fl_t=-2, fl_k=-26)
HANG2 = P(lean=-6, head=-12, ra_s=170, ra_e=4, fa_s=174, fa_e=4, rl_t=-14, rl_k=-20, fl_t=-8, fl_k=-30)
JUMPUP = sequence([(stand, 3), (CROUCH, 3), (REACH, 3), (HANG1, 0)])   # ends on the hanging pose
JUMPUP_DX = [0, 0, 0, 0, 0, 1, 2, 2, 2, 3][:len(JUMPUP)]
PULL1 = P(lean=-2, head=-12, ra_s=140, ra_e=60, fa_s=150, fa_e=70, rl_t=-6, rl_k=-40, fl_t=10, fl_k=-70)
PULL2 = P(lean=10, head=-6, ra_s=96, ra_e=96, fa_s=100, fa_e=110, rl_t=-6, rl_k=-60, fl_t=60, fl_k=-100)
PULL3 = P(lean=26, head=-4, ra_s=40, ra_e=90, fa_s=44, fa_e=100, rl_t=-24, rl_k=-90, fl_t=40, fl_k=-72)
PULLUP = sequence([(HANG1, 2), (PULL1, 3), (PULL2, 3), (PULL3, 3), (CROUCH, 2), (stand, 0)])
CLIMBDOWN = sequence([(stand, 2), (CROUCH, 3), (P(lean=40, head=-14, ra_s=100, ra_e=30, fa_s=120, fa_e=20, rl_t=-40, rl_k=-100,
                                                    fl_t=30, fl_k=-60), 3), (REACH, 3), (HANG1, 0)])

# ---- falling and landing -------------------------------------------------------------------------------------------
FALL_A = P(lean=-6, head=-8, ra_s=140, ra_e=20, fa_s=160, fa_e=10, rl_t=10, rl_k=-40, fl_t=-14, fl_k=-30)
FALL_B = P(lean=-2, head=-6, ra_s=120, ra_e=10, fa_s=135, fa_e=26, rl_t=-6, rl_k=-20, fl_t=14, fl_k=-46)
FALL = sequence([(FALL_A, 4), (FALL_B, 4)], loop=True)           # 8 frames, looped while airborne
LAND_SOFT = sequence([(LAND_C, 2), (stand, 0)])
LAND_HARD = sequence([(P(lean=40, head=-14, ra_s=60, ra_e=60, fa_s=70, fa_e=60, rl_t=-40, rl_k=-110, fl_t=70, fl_k=-116), 4),
                      (P(lean=44, head=-18, ra_s=70, ra_e=60, fa_s=80, fa_e=60, rl_t=-46, rl_k=-110, fl_t=76, fl_k=-110), 6),
                      (CROUCH, 3), (stand, 0)])
CROUCH_SEQ = sequence([(stand, 3), (CROUCH, 0)])
RISE_SEQ = sequence([(CROUCH, 3), (stand, 0)])

# ---- deaths --------------------------------------------------------------------------------------------------
DEAD_BACK = P(lean=-84, head=-14, ra_s=-90, ra_e=0, fa_s=-70, fa_e=8, rl_t=86, rl_k=-4, fl_t=84, fl_k=-6)
DEAD_FWD = P(lean=84, head=14, ra_s=100, ra_e=0, fa_s=130, fa_e=-10, rl_t=-86, rl_k=4, fl_t=-84, fl_k=6)
IMPALED = P(lean=-62, head=-22, ra_s=-60, ra_e=0, fa_s=-40, fa_e=10, rl_t=60, rl_k=-20, fl_t=40, fl_k=-30)
DIE_FALL = sequence([(FALL_B, 2), (P(lean=60, head=10, ra_s=100, ra_e=0, fa_s=120, fa_e=0, rl_t=-60, rl_k=-20, fl_t=-30, fl_k=-30), 3),
                     (DEAD_FWD, 0)])
HITB = P(lean=-14, head=-12, ra_s=46, ra_e=30, fa_s=20, fa_e=40, rl_t=-34, rl_k=-20, fl_t=10, fl_k=-4, swa=100, swl=1)
KNEEL = P(lean=-34, head=-16, ra_s=40, ra_e=20, fa_s=-20, fa_e=40, rl_t=-14, rl_k=-100, fl_t=52, fl_k=-110, swa=60, swl=0.6)

# ---- potion, sword -------------------------------------------------------------------------------------------------
def drink_seq(item):
    base = dict(stand)
    up = P(lean=0, head=-6, fa_s=60, fa_e=60, item=item)
    mouth = P(lean=-3, head=-22, fa_s=120, fa_e=90, item=item)
    tilt = P(lean=-6, head=-30, fa_s=140, fa_e=80, item=item)
    return sequence([(dict(base, item=item), 2), (up, 3), (mouth, 3), (tilt, 3), (mouth, 2), (up, 2), (dict(base, item=item), 0)])


PICKUP = sequence([(stand, 2), (P(lean=42, head=14, fa_s=50, fa_e=40, ra_s=-30, ra_e=40, fl_t=34, fl_k=-70, rl_t=-18, rl_k=-60), 4),
                   (P(lean=55, head=18, fa_s=24, fa_e=14, ra_s=-30, ra_e=40, fl_t=40, fl_k=-90, rl_t=-20, rl_k=-70), 3),
                   (P(lean=30, head=6, fa_s=40, fa_e=60, swa=165, swl=1, ra_s=-20, ra_e=30, fl_t=20, fl_k=-30, rl_t=-14, rl_k=-30), 3),
                   (stand, 0)])

EG = P(lean=6, head=0, ra_s=-28, ra_e=55, fa_s=62, fa_e=35, rl_t=-24, rl_k=-14, fl_t=26, fl_k=-6, swa=132, swl=1)
EG2 = P(lean=7, head=0, ra_s=-24, ra_e=52, fa_s=58, fa_e=38, rl_t=-23, rl_k=-14, fl_t=25, fl_k=-6, swa=126, swl=1)
DRAW = sequence([(stand, 2), (P(fa_s=14, fa_e=50, swl=0.35, swa=170, lean=3), 2), (P(fa_s=40, fa_e=60, swl=1, swa=150, lean=4, fl_t=18, fl_k=-4, rl_t=-14), 2), (EG, 0)])
SHEATHE = sequence([(EG, 2), (P(fa_s=40, fa_e=60, swl=1, swa=150, lean=4, fl_t=18, fl_k=-4, rl_t=-14), 2),
                    (P(fa_s=14, fa_e=50, swl=0.35, swa=170, lean=3), 2), (stand, 0)])
IDLE_EG = sequence([(EG, 7), (EG2, 7)], loop=True)

# ---- sword fight ----------------------------------------------------------------------------------------------------
ADV1 = P(lean=7, ra_s=-30, ra_e=55, fa_s=60, fa_e=36, rl_t=-14, rl_k=-40, fl_t=36, fl_k=-16, swa=130, swl=1)
ADV2 = P(lean=7, ra_s=-26, ra_e=55, fa_s=60, fa_e=36, rl_t=20, rl_k=-40, fl_t=30, fl_k=-8, swa=130, swl=1)
ADVANCE = sequence([(EG, 2), (ADV1, 3), (ADV2, 3), (EG, 0)])
ADVANCE_DX = [0.6, 1.0, 1.6, 2.0, 2.2, 1.8, 1.4, 0.8, 0.0][:len(ADVANCE)]
RET1 = P(lean=3, ra_s=-24, ra_e=55, fa_s=60, fa_e=36, rl_t=-34, rl_k=-20, fl_t=14, fl_k=-30, swa=134, swl=1)
RET2 = P(lean=4, ra_s=-24, ra_e=55, fa_s=60, fa_e=36, rl_t=-12, rl_k=-40, fl_t=34, fl_k=-14, swa=134, swl=1)
RETREAT = sequence([(EG, 2), (RET1, 3), (RET2, 3), (EG, 0)])
RETREAT_DX = [-v for v in ADVANCE_DX[:len(RETREAT)]]

WIND = P(lean=1, head=2, ra_s=-34, ra_e=55, fa_s=22, fa_e=62, rl_t=-22, rl_k=-16, fl_t=24, fl_k=-8, swa=172, swl=1)
THRUST = P(lean=22, head=-2, ra_s=-60, ra_e=30, fa_s=92, fa_e=0, rl_t=-36, rl_k=-8, fl_t=54, fl_k=-8, swa=90, swl=1)
STRIKE = sequence([(EG, 2), (WIND, 3), (THRUST, 2), (THRUST, 3), (P(lean=14, ra_s=-50, ra_e=34, fa_s=84, fa_e=10, rl_t=-30, rl_k=-8,
                                                                     fl_t=44, fl_k=-8, swa=100, swl=1), 3), (EG, 0)])
STRIKE_DX = [0, 0, 0, 0, 0, 2.5, 3.5, 1.5, 0, 0, 0, -1.5, -2.5, -3.0, 0][:len(STRIKE)]
STRIKE_ACTIVE = (6, 8)              # frames in which the point can hurt
PARRY_POSE = P(lean=-2, head=-3, ra_s=-30, ra_e=50, fa_s=56, fa_e=46, rl_t=-26, rl_k=-16, fl_t=20, fl_k=-6, swa=174, swl=1)
PARRY = sequence([(EG, 2), (PARRY_POSE, 4), (PARRY_POSE, 0)]) + sequence([(PARRY_POSE, 2), (EG, 0)])
PARRY_ACTIVE = (2, 7)
HIT_SEQ = sequence([(EG, 2), (HITB, 3), (HITB, 0)]) + sequence([(HITB, 2), (EG, 0)])
HIT_DX = [-1.5, -3, -3, -2, -1, -0.5, 0, 0, 0][:len(HIT_SEQ)]
DIE_SWORD = sequence([(HITB, 3), (KNEEL, 4), (P(lean=-60, head=-22, ra_s=30, ra_e=20, fa_s=-40, fa_e=30, rl_t=30, rl_k=-60,
                                                 fl_t=70, fl_k=-90, swl=0), 3), (DEAD_BACK, 0)])
DIE_SWORD_DX = [-1.5, -2.0, -2.0, -1.5, -1.0, -0.8, -0.6, -0.5, -0.5, -0.4, -0.2, 0, 0][:len(DIE_SWORD)]

# Sequences rendered for every fighter palette.
FIGHT = {
    "eg": (IDLE_EG, True), "advance": (ADVANCE, False), "retreat": (RETREAT, False), "strike": (STRIKE, False),
    "parry": (PARRY, False), "hit": (HIT_SEQ, False), "die": (DIE_SWORD, False),
}
