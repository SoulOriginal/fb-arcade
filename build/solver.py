# Offline snake solver: dynamic Hamiltonian cycle on a spanning tree of 2x2 blocks.
# Invariant: after every move some spanning tree exists whose cycle contains the whole body as one
# contiguous piece, so the snake can always follow that cycle and can never be trapped.
import random, sys
from collections import deque

GW, GH = 40, 20
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
    def __init__(self):
        self.p, self.m = [0] * E, [0] * E

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
        comps = BASE
        for e in VALID:
            if p[e] > 0:
                if m[e] > 0:
                    return False
                ru, rv = find(EU[e]), find(EV[e])
                if ru == rv:
                    return False
                par[ru] = rv
                comps -= 1
        for e in VALID:
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
        for e in VALID:
            if self.p[e] > 0:
                par[find(EU[e])] = find(EV[e])
                edges.add(e)
        for e in VALID:
            if self.p[e] == 0 and self.m[e] == 0 and find(EU[e]) != find(EV[e]):
                par[find(EU[e])] = find(EV[e])
                edges.add(e)
        return edges


def cycle_from_tree(edges, head, neck):
    # Cell graph of the tree contour; returns the cycle as a list starting after the head.
    def has(e):
        return e in edges
    adj = {}

    def link(a, b):
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    for by in range(BH):
        for bx in range(BW):
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
    for _ in range(N):
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
    body = [(2, 0), (1, 0), (0, 0)]
    occ = set(body)
    cons = Constraints()
    for a, b in zip(body, body[1:]):
        cons.add(a, b, 1)
    assert cons.feasible()
    free = lambda: [(x, y) for y in range(GH) for x in range(GW) if (x, y) not in occ]
    food = rnd.choice(free())
    foods, moves, since, follow = [food], [], 0, None
    while True:
        head, tail = body[0], body[-1]
        if follow is not None:
            n = follow.pop(0)
        else:
            dist = bfs_from(food, occ - {tail})
            cands = []
            for k, (dx, dy) in enumerate(DIRS):
                n = (head[0] + dx, head[1] + dy)
                if 0 <= n[0] < GW and 0 <= n[1] < GH and (n not in occ or n == tail) and n in dist:
                    straight = 0 if len(body) > 1 and (head[0] - body[1][0], head[1] - body[1][1]) == (dx, dy) else 1
                    cands.append((dist[n], straight, k, n))
            cands.sort()
            n = None
            for _, _, _, c in cands:
                eat = c == food
                cons.add(head, c, 1)
                if not eat:
                    cons.add(body[-2], tail, -1)
                ok = cons.feasible()
                cons.add(head, c, -1)
                if not eat:
                    cons.add(body[-2], tail, 1)
                if ok:
                    n = c
                    break
            if n is None:
                # No proven shortcut: follow a cycle that contains the body, which always exists.
                cyc = cycle_from_tree(cons.tree(), head, body[1])
                cut = cyc.index(food)
                follow = cyc[:cut + 1]
                n = follow.pop(0)
        eat = n == food
        moves.append(DIRS.index((n[0] - head[0], n[1] - head[1])))
        cons.add(head, n, 1)
        if not eat:
            cons.add(body[-2], tail, -1)
            occ.discard(body.pop())
        body.insert(0, n)
        occ.add(n)
        if eat:
            fr = free()
            if not fr:
                return moves, foods
            food = rnd.choice(fr)
            foods.append(food)
            since, follow = 0, None
        else:
            since += 1
            if since > stall_limit and follow is None:
                cyc = cycle_from_tree(cons.tree(), body[0], body[1])
                follow = cyc[:cyc.index(food) + 1]
                since = 0
        assert n not in set(body[1:]), "died"


if __name__ == "__main__":
    import time
    t = time.time()
    moves, foods = solve(int(sys.argv[1]))
    print("seed", sys.argv[1], "WON moves", len(moves), "foods", len(foods), "sec", int(time.time() - t), flush=True)
