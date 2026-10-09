# Offline snake solver: dynamic Hamiltonian cycle on a spanning tree of 2x2 blocks.
# Invariant: after every move some spanning tree exists whose cycle contains the whole body as one
# contiguous piece, so the snake can always follow that cycle and can never be trapped.
import os, random, sys
from collections import deque

GW, GH = int(os.environ.get("SNAKE_W", "24")), int(os.environ.get("SNAKE_H", "12"))
BW, BH = GW // 2, GH // 2
N = GW * GH
BASE = BW * BH
E = 2 * BASE
# Block-graph edges: h(bx,by) joins (bx,by)-(bx+1,by); v(bx,by) joins (bx,by)-(bx,by+1).
EU, EV, VALID = [0] * E, [0] * E, []
for by in range(BH):
    for bx in range(BW):
        if bx < BW - 1:
            EU[by * BW + bx], EV[by * BW + bx] = by * BW + bx, by * BW + bx + 1
            VALID.append(by * BW + bx)
        if by < BH - 1:
            EU[BASE + by * BW + bx], EV[BASE + by * BW + bx] = by * BW + bx, (by + 1) * BW + bx
            VALID.append(BASE + by * BW + bx)
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
APPLES = int(os.environ.get("SNAKE_APPLES", "200"))
SHRINK_SHARE = 0.4
MIN_SHRINK_LEN = 6


def pick_bricks(rnd):
    # Bricks are whole 2x2 blocks so that a Hamiltonian cycle through the remaining blocks still exists; the blocks
    # under the start position stay free and the rest must stay connected.
    for _ in range(1000):
        n = rnd.randint(5, 9)
        cand = [(bx, by) for bx in range(BW) for by in range(BH) if (bx, by) not in ((0, 0), (1, 0), (0, 1))]
        bricks = set(rnd.sample(cand, n))
        # no two bricks touching: they would merge into walls that cut the board into corridors
        if any(((bx + dx, by + dy) in bricks) for bx, by in bricks for dx, dy in DIRS):
            continue
        seen, queue = {(0, 0)}, [(0, 0)]
        for bx, by in queue:
            for dx, dy in DIRS:
                q = (bx + dx, by + dy)
                if 0 <= q[0] < BW and 0 <= q[1] < BH and q not in bricks and q not in seen:
                    seen.add(q)
                    queue.append(q)
        if len(seen) == BW * BH - len(bricks):
            return bricks
    raise RuntimeError("no brick layout found")


def constraint(a, b):
    # Which tree edge a body step between adjacent cells a and b forces: (+1, id) present, (-1, id) absent.
    (x, y), (x2, y2) = a, b
    bx, by, bx2, by2 = x // 2, y // 2, x2 // 2, y2 // 2
    if (bx, by) != (bx2, by2):
        if bx2 != bx:
            return (1, by * BW + min(bx, bx2))
        return (1, BASE + min(by, by2) * BW + bx)
    if y == y2:                      # horizontal link inside a block: top or bottom row
        if y % 2 == 0:
            return (-1, BASE + (by - 1) * BW + bx) if by > 0 else None      # no edge up
        return (-1, BASE + by * BW + bx) if by < BH - 1 else None            # no edge down
    if x % 2 == 0:                   # vertical link: left or right column
        return (-1, by * BW + bx - 1) if bx > 0 else None                   # no edge left
    return (-1, by * BW + bx) if bx < BW - 1 else None                       # no edge right


class Constraints:
    def __init__(self, bricks):
        self.p, self.m = [0] * E, [0] * E
        self.present = [i for i in range(BASE) if (i % BW, i // BW) not in bricks]
        pres = set(self.present)
        self.valid = [e for e in VALID if EU[e] in pres and EV[e] in pres]

    def add(self, a, b, d):
        c = constraint(a, b)
        if c:
            (self.p if c[0] > 0 else self.m)[c[1]] += d

    def feasible(self):
        p, m = self.p, self.m
        par = list(range(BASE))

        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        comps = len(self.present)
        for e in self.valid:
            if p[e] > 0:
                if m[e] > 0:
                    return False
                ru, rv = find(EU[e]), find(EV[e])
                if ru == rv:
                    return False
                par[ru] = rv
                comps -= 1
        for e in self.valid:
            if p[e] == 0 and m[e] == 0:
                ru, rv = find(EU[e]), find(EV[e])
                if ru != rv:
                    par[ru] = rv
                    comps -= 1
        return comps == 1

    def tree(self):
        par = list(range(BASE))

        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        edges = set()
        for e in self.valid:
            if self.p[e] > 0:
                par[find(EU[e])] = find(EV[e])
                edges.add(e)
        for e in self.valid:
            if self.p[e] == 0 and self.m[e] == 0 and find(EU[e]) != find(EV[e]):
                par[find(EU[e])] = find(EV[e])
                edges.add(e)
        return edges


def cycle_from_tree(edges, head, neck, bricks):
    # Cell graph of the tree contour; returns the cycle as a list starting after the head.
    def has(e):
        return e in edges
    adj = {}

    def link(a, b):
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    for by in range(BH):
        for bx in range(BW):
            if (bx, by) in bricks:
                continue
            x, y = bx * 2, by * 2
            up = by > 0 and has(BASE + (by - 1) * BW + bx)
            down = by < BH - 1 and has(BASE + by * BW + bx)
            left = bx > 0 and has(by * BW + bx - 1)
            right = bx < BW - 1 and has(by * BW + bx)
            if not up:
                link((x, y), (x + 1, y))
            if not down:
                link((x, y + 1), (x + 1, y + 1))
            if not left:
                link((x, y), (x, y + 1))
            if not right:
                link((x + 1, y), (x + 1, y + 1))
            if right:
                link((x + 1, y), (x + 2, y))
                link((x + 1, y + 1), (x + 2, y + 1))
            if down:
                link((x, y + 1), (x, y + 2))
                link((x + 1, y + 1), (x + 1, y + 2))
    prev, cur, out = neck, head, []
    for _ in range(4 * (BW * BH - len(bricks))):
        nxt = [c for c in adj[cur] if c != prev]
        assert len(adj[cur]) == 2, "cell degree is not 2"
        prev, cur = cur, nxt[0]
        out.append(cur)
    assert cur == head or out[-1] == head, "cycle is not closed"
    return out


def bfs_from(food, blocked):
    d = {food: 0}
    q = deque([food])
    while q:
        p = q.popleft()
        for dx, dy in DIRS:
            n = (p[0] + dx, p[1] + dy)
            if 0 <= n[0] < GW and 0 <= n[1] < GH and n not in d and n not in blocked:
                d[n] = d[p] + 1
                q.append(n)
    return d


def solve(seed, stall_limit=500):
    rnd = random.Random(seed)
    bricks = pick_bricks(rnd)
    brick_cells = {(bx * 2 + i, by * 2 + j) for bx, by in bricks for i in (0, 1) for j in (0, 1)}
    body = [(2, 0), (1, 0), (0, 0)]
    occ = set(body)
    cons = Constraints(bricks)
    for a, b in zip(body, body[1:]):
        cons.add(a, b, 1)
    assert cons.feasible()

    def free_cells():
        return [(x, y) for y in range(GH) for x in range(GW) if (x, y) not in occ and (x, y) not in brick_cells]

    def new_food():
        kind = 1 if len(body) >= MIN_SHRINK_LEN and rnd.random() < SHRINK_SHARE else 0
        c = rnd.choice(free_cells())
        return (c[0], c[1], kind)

    food = new_food()
    foods, moves, since, follow = [food], [], 0, None
    eaten = 0

    def tail_edges(drop):
        # the edges that disappear when `drop` tail cells are removed
        return [(body[-1 - k - 1], body[-1 - k]) for k in range(drop)]

    while True:
        head, tail = body[0], body[-1]
        fcell = food[:2]
        if follow is not None:
            n = follow.pop(0)
        else:
            dist = bfs_from(fcell, (occ - {tail}) | brick_cells)
            cands = []
            for k, (dx, dy) in enumerate(DIRS):
                n = (head[0] + dx, head[1] + dy)
                if 0 <= n[0] < GW and 0 <= n[1] < GH and n not in brick_cells and (n not in occ or n == tail) and n in dist:
                    straight = 0 if len(body) > 1 and (head[0] - body[1][0], head[1] - body[1][1]) == (dx, dy) else 1
                    cands.append((dist[n], straight, k, n))
            cands.sort()
            n = None
            for _, _, _, c in cands:
                eat = c == fcell
                drop = 0 if eat and food[2] == 0 else (2 if eat else 1)
                removed = tail_edges(drop)
                cons.add(head, c, 1)
                for a, b in removed:
                    cons.add(a, b, -1)
                ok = cons.feasible()
                cons.add(head, c, -1)
                for a, b in removed:
                    cons.add(a, b, 1)
                if ok:
                    n = c
                    break
            if n is None:
                # No proven shortcut: follow a cycle that contains the body, which always exists.
                cyc = cycle_from_tree(cons.tree(), head, body[1], bricks)
                follow = cyc[:cyc.index(fcell) + 1]
                n = follow.pop(0)
        eat = n == fcell
        moves.append(DIRS.index((n[0] - head[0], n[1] - head[1])))
        cons.add(head, n, 1)
        drop = 0 if eat and food[2] == 0 else (2 if eat else 1)
        for a, b in tail_edges(drop):
            cons.add(a, b, -1)
        # free the tail first: the head may enter the very cell the tail is leaving
        for _ in range(drop):
            occ.discard(body.pop())
        body.insert(0, n)
        occ.add(n)
        if eat:
            eaten += 1
            if eaten >= APPLES:
                return moves, foods, sorted(bricks)
            food = new_food()
            foods.append(food)
            since, follow = 0, None
        else:
            since += 1
            if since > stall_limit and follow is None:
                cyc = cycle_from_tree(cons.tree(), body[0], body[1], bricks)
                follow = cyc[:cyc.index(food[:2]) + 1]
                since = 0
        assert n not in set(body[1:]), "died"


if __name__ == "__main__":
    import time
    t = time.time()
    moves, foods, bricks = solve(int(sys.argv[1]))
    print("seed", sys.argv[1], "moves", len(moves), "apples", len(foods), "bricks", len(bricks), "sec", int(time.time() - t), flush=True)
