# Pre-solves snake games offline: direction codes, food sequence (cell + kind) and brick blocks. Only games of a
# comfortable length are kept: the brick layout decides how many moves 200 apples need.
import pickle
from multiprocessing import Pool
import solver

WANT = (5200, 7600)    # moves; at 22 moves per second that is 4 to 6 minutes
KEEP = 8


def one(seed):
    moves, foods, bricks = solver.solve(seed)
    return bytes(moves), foods, bricks


if __name__ == "__main__":
    with Pool(6) as p:
        games = p.map(one, range(100, 140))
    good = [g for g in games if WANT[0] <= len(g[0]) <= WANT[1]]
    good.sort(key=lambda g: abs(len(g[0]) - 6400))
    keep = good[:KEEP]
    assert len(keep) >= 4, "too few games of the wanted length: %d" % len(keep)
    for m, f, b in keep:
        print(len(m), len(f), len(b))
    pickle.dump(keep, open("snake_games.bin", "wb"))
