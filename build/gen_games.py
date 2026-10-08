# Pre-solves several full snake games offline: moves (0..3 direction codes) and the food sequence.
import pickle, sys
from multiprocessing import Pool
import solver


def one(seed):
    moves, foods = solver.solve(seed)
    return bytes(moves), foods


if __name__ == "__main__":
    with Pool(6) as p:
        games = p.map(one, range(11, 17))
    for m, f in games:
        print(len(m), len(f))
    pickle.dump(games, open("snake_games.bin", "wb"))
