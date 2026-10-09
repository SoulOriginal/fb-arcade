# Pre-solves snake games offline: direction codes, apple events (spawns and removals) and brick blocks. Only games of
# a comfortable length are kept, preferring those where the snake never spends long on a single apple.
import pickle
from multiprocessing import Pool
import solver

WANT = (6200, 7800)    # moves; at 22 moves per second that is 4.7 to 6 minutes
KEEP = 8
LONG_GAP = 100         # moves between two apples; longer means a long walk without eating


def one(seed):
    moves, events, bricks, gaps = solver.solve(seed)
    return bytes(moves), events, bricks, gaps


if __name__ == "__main__":
    with Pool(6) as p:
        games = p.map(one, range(200, 260))
    good = [g for g in games if WANT[0] <= len(g[0]) <= WANT[1]]
    good.sort(key=lambda g: (sum(1 for x in g[3] if x > LONG_GAP), abs(len(g[0]) - 7000)))
    keep = good[:KEEP]
    assert len(keep) >= 4, "too few games of the wanted length: %d" % len(keep)
    for m, e, b, gp in keep:
        print(len(m), "moves,", len(gp), "apples, long walks:", sum(1 for x in gp if x > LONG_GAP), "longest:", max(gp))
    pickle.dump([x[:3] for x in keep], open("snake_games.bin", "wb"))
