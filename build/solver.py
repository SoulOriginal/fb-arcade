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
APPLES = int(os.environ.get("SNAKE_APPLES", "360"))
AHEAD = 56            # how far ahead along the cycle an apple may appear
SHRINK_SHARE = 0.4
MIN_SHRINK_LEN = 6


def _shape(rnd, style):
    # Returns a set of 2x2 blocks forming one obstacle of the given style.
    bx, by = rnd.randrange(BW), rnd.randrange(BH)
    if style == "bar":
        n = rnd.randint(3, 5)
        return {(bx + i, by) for i in range(n)}
    if style == "post":
        n = rnd.randint(2, 4)
        return {(bx, by + i) for i in range(n)}
    if style == "ell":
        n, m = rnd.randint(2, 3), rnd.randint(2, 3)
        dx, dy = rnd.choice((1, -1)), rnd.choice((1, -1))
        return {(bx + dx * i, by) for i in range(n)} | {(bx, by + dy * j) for j in range(m)}
    if style == "plus":
        return {(bx, by), (bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)}
    if style == "block":
        return {(bx, by), (bx + 1, by), (bx, by + 1), (bx + 1, by + 1)}
    return {(bx, by)}       # "dot"


STYLES = ("dot", "bar", "post", "ell", "plus", "block")
MAX_BRICKS = 13


def pick_bricks(rnd):
    # Every game gets a new arrangement: a few obstacles of random kinds (single bricks, bars, posts, L-corners,
    # plus signs, blocks), mirrored by the player later. The blocks under the start stay free and the remaining
    # blocks must stay connected, which is all a Hamiltonian cycle through them needs.
    free_start = {(0, 0), (1, 0), (0, 1)}
    for _ in range(5000):
        bricks = set()
        for _ in range(rnd.randint(2, 4)):
            bricks |= _shape(rnd, rnd.choice(STYLES))
        bricks = {c for c in bricks if 0 <= c[0] < BW and 0 <= c[1] < BH}
        if not 5 <= len(bricks) <= MAX_BRICKS or bricks & free_start:
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

    def tree(self, rnd=None):
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
        others = [e for e in self.valid if self.p[e] == 0 and self.m[e] == 0]
        if rnd is not None:
            rnd.shuffle(others)
        for e in others:
            if find(EU[e]) != find(EV[e]):
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


LIFE = (150, 150, 60)       # moves an apple stays on the board: red, blue, golden
POINTS = (15, -10, 100)    # eating a blue apple costs points: shrinking is a price, not a gift
RED_STOP = 40               # no new red apples while the snake is at least this long
BLUE_MIN = 24               # the snake never steps on a blue apple while shorter than this
TARGET = int(os.environ.get("SNAKE_TARGET", "5800"))


def solve(seed):
    rnd = random.Random(seed)
    bricks = pick_bricks(rnd)
    brick_cells = {(bx * 2 + i, by * 2 + j) for bx, by in bricks for i in (0, 1) for j in (0, 1)}
    body = [(2, 0), (1, 0), (0, 0)]
    occ = set(body)
    cons = Constraints(bricks)
    for a, b in zip(body, body[1:]):
        cons.add(a, b, 1)
    assert cons.feasible()
    plan = {}
    apples = {}                 # cell -> [kind, expires at move k]
    events = []                 # (k, cell, kind, expires) spawns; (k, cell, -1, 0) removals
    state = {"score": 0, "blue_gone": -99, "target": None}

    def free_cells():
        return [(x, y) for y in range(GH) for x in range(GW)
                if (x, y) not in occ and (x, y) not in brick_cells and (x, y) not in apples]

    def spawn(kind, k):
        # An apple appears on the stretch of a valid cycle just ahead of the head (never in the first few cells), so
        # that it is always within reach of a plan that cannot loop round the board.
        edges = cons.tree(rnd)
        cyc = cycle_from_tree(edges, body[0], body[1], bricks)
        ahead = [c for c in cyc[4:AHEAD] if c not in occ and c not in apples]
        c = rnd.choice(ahead or free_cells())
        apples[c] = [kind, k + LIFE[kind]]
        events.append((k, c, kind, k + LIFE[kind]))
        plan["tree"] = edges

    def tail_edges(drop):
        return [(body[-1 - k - 1], body[-1 - k]) for k in range(drop)]

    def drop_for(cell):
        # grow: keep the tail; blue apple: drop two cells (net -1); a plain step drops one
        if cell in apples:
            return 2 if apples[cell][0] == 1 else 0
        return 1

    gaps, since = [], 0
    while True:
        k = len(moves := plan.setdefault("moves", []))
        for c in [c for c, a in apples.items() if a[1] <= k]:
            kind = apples.pop(c)[0]
            events.append((k, c, -1, 0))
            if kind == 1:
                state["blue_gone"] = k
        have = [a[0] for a in apples.values()]
        # A long snake is cramped: more blue apples show up and no new red ones until it has shrunk again.
        want_blue = 0 if len(body) < BLUE_MIN else 1      # at most one apple of each kind on the board
        if have.count(0) == 0 and len(body) < RED_STOP:
            spawn(0, k)
        if have.count(1) < want_blue and k - state["blue_gone"] >= 5:
            spawn(1, k)
        if 2 not in have and k > 120 and rnd.random() < 0.012:
            spawn(2, k)
        if not apples:
            spawn(0 if len(body) < RED_STOP else 1, k)
        head = body[0]
        cyc = cycle_from_tree(plan["tree"], head, body[1], bricks)
        reach = {c: cyc.index(c) + 1 for c in apples}

        def value(c):
            kind, exp = apples[c]
            if reach[c] > exp - k:
                return None                       # it would be gone before we get there
            length = len(body)
            # a long snake is cramped: it stops wanting red apples and goes for the blue ones; a short one avoids blue
            bonus = (-max(0, length - 28), 18 + max(0, length - 20) if length >= 10 else -60, 40)[kind]
            return reach[c] - bonus

        target = state["target"]
        options = sorted((value(c), c) for c in apples if value(c) is not None)
        if target not in apples or value(target) is None:
            target = options[0][1] if options else min(apples, key=lambda c: reach[c])
        elif options and apples[options[0][1]][0] == 2 and options[0][1] != target and options[0][0] < value(target) - 10:
            target = options[0][1]                # a golden apple is worth a detour
        state["target"] = target
        n, new_tree, best = cyc[0], None, (reach[target] - 1, 1)
        for kk, (dx, dy) in enumerate(DIRS):
            c = (head[0] + dx, head[1] + dy)
            if not (0 <= c[0] < GW and 0 <= c[1] < GH) or c in brick_cells or (c in occ and c != body[-1]):
                continue
            if c in apples and apples[c][0] == 1 and len(body) < BLUE_MIN:
                continue
            removed = tail_edges(drop_for(c))
            cons.add(head, c, 1)
            for a, b in removed:
                cons.add(a, b, -1)
            tree = cons.tree() if cons.feasible() else None
            cons.add(head, c, -1)
            for a, b in removed:
                cons.add(a, b, 1)
            if tree is None:
                continue
            left = 0 if c == target else cycle_from_tree(tree, c, head, bricks).index(target) + 1
            straight = 0 if len(body) > 1 and (head[0] - body[1][0], head[1] - body[1][1]) == (dx, dy) else 1
            if (left, straight) < best:
                best, n, new_tree = (left, straight), c, tree
        if new_tree is not None:
            plan["tree"] = new_tree
        moves.append(DIRS.index((n[0] - head[0], n[1] - head[1])))
        drop = drop_for(n)
        eaten = apples.pop(n) if n in apples else None
        cons.add(head, n, 1)
        for a, b in tail_edges(drop):
            cons.add(a, b, -1)
        # free the tail first: the head may enter the very cell the tail is leaving
        for _ in range(drop):
            occ.discard(body.pop())
        body.insert(0, n)
        occ.add(n)
        assert n not in set(body[1:]), "died"
        since += 1
        state["maxlen"] = max(state.get("maxlen", 0), len(body))
        if eaten:
            state["score"] = max(0, state["score"] + POINTS[eaten[0]])
            gaps.append(since)
            since = 0
            if eaten[0] == 1:
                state["blue_gone"] = k + 1
            if state["score"] >= TARGET:
                if os.environ.get("SNAKE_STATS"):
                    print("   max length", state["maxlen"])
                return moves, events, sorted(bricks), gaps


if __name__ == "__main__":
    import time
    t = time.time()
    moves, events, bricks, gaps = solve(int(sys.argv[1]))
    print("seed", sys.argv[1], "moves", len(moves), "apples", len(gaps), "longest gap", max(gaps), "sec", int(time.time() - t), flush=True)
