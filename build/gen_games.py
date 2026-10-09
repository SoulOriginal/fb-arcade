# Pre-solves snake games offline: direction codes, food sequence (cell + kind) and brick blocks. Only games of a
# comfortable length are kept: the brick layout decides how many moves 200 apples need.
import pickle
from multiprocessing import Pool
import solver

WANT = (6000, 8000)    # moves; at 22 moves per second that is 4 to 6 minutes
KEEP = 8
LONG_GAP = 80          # moves between two apples; longer means the snake is circling the board without a goal


DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def gaps(moves, foods):
    # Replays the game exactly as the player does and returns the number of moves spent on every apple.
    body, fk, since, out = [(2, 0), (1, 0), (0, 0)], 0, 0, []
    for m in moves:
        n = (body[0][0] + DIRS[m][0], body[0][1] + DIRS[m][1])
        eat = n == foods[fk][:2]
        for _ in range((2 if foods[fk][2] else 0) if eat else 1):
            body.pop()
        body.insert(0, n)
        since += 1
        if eat:
            out.append(since)
            since, fk = 0, fk + 1
    return out


def one(seed):
    moves, foods, bricks = solver.solve(seed)
    return bytes(moves), foods, bricks, gaps(moves, foods)


if __name__ == "__main__":
    with Pool(6) as p:
        games = p.map(one, range(100, 160))
    good = [g for g in games if WANT[0] <= len(g[0]) <= WANT[1]]
    # fewest long laps first, then the length closest to the target
    good.sort(key=lambda g: (sum(1 for x in g[3] if x > LONG_GAP), abs(len(g[0]) - 6900)))
    keep = [x[:3] for x in good[:KEEP]]
    assert len(keep) >= 4, "too few games of the wanted length: %d" % len(keep)
    for m, f, b in keep:
        print(len(m), len(f), len(b), "long laps:", sum(1 for x in gaps(m, f) if x > LONG_GAP), "longest:", max(gaps(m, f)))
    pickle.dump(keep, open("snake_games.bin", "wb"))
