#!/usr/bin/env python3
"""
Grid maze router for finishing individual unrouted connections on a 2-layer board.

Run with KiCad's Python:
  python.exe route_net.py <board.kicad_pcb> <NET> <REF> <PAD> <X> <Y> [...]

For each (NET, REF, PAD, X, Y) it routes from that pad to the copper island of
the same net containing the track at page position (X, Y) mm -- take these
from the DRC "unconnected items" report. It uses A* on a grid over
F.Cu and B.Cu with vias. Clearance is respected against every other net's
tracks, vias and pads, rule-area keep-outs, holes and the board outline.
GND pours are ignored (refill zones afterwards). Saves the board in place.
"""
import heapq
import math
import sys

import pcbnew
from pcbnew import FromMM, ToMM

GRID = 0.2          # mm
TRACK_W = 0.25      # mm
CLR = 0.27          # mm: above the Power netclass 0.25 mm, plus grid margin
VIA_D, VIA_DRILL = 0.8, 0.4
VIA_COST = 25.0
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


class Router:
    def __init__(self, board):
        self.b = board
        bb = board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = ToMM(bb.GetLeft()), ToMM(bb.GetTop())
        self.nx = int(ToMM(bb.GetWidth()) / GRID) + 2
        self.ny = int(ToMM(bb.GetHeight()) / GRID) + 2
        poly = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(poly, True)
        o = poly.Outline(0)
        self.edge = [(ToMM(o.CPoint(k).x), ToMM(o.CPoint(k).y)) for k in range(o.PointCount())]

    def xy(self, i, j):
        return self.x0 + i * GRID, self.y0 + j * GRID

    def ij(self, x, y):
        return int(round((x - self.x0) / GRID)), int(round((y - self.y0) / GRID))

    def build(self, net):
        """blocked[layer][j][i] for a route of `net` with TRACK_W; via_ok[j][i]."""
        nx, ny = self.nx, self.ny
        blk = {L: [bytearray(nx) for _ in range(ny)] for L in LAYERS}
        hw = TRACK_W / 2

        def mark_seg(L, x1, y1, x2, y2, r):
            rr = r + hw + CLR
            i0, j0 = self.ij(min(x1, x2) - rr, min(y1, y2) - rr)
            i1, j1 = self.ij(max(x1, x2) + rr, max(y1, y2) + rr)
            for j in range(max(0, j0), min(ny, j1 + 1)):
                row = blk[L][j]
                y = self.y0 + j * GRID
                for i in range(max(0, i0), min(nx, i1 + 1)):
                    if not row[i] and seg_dist(self.x0 + i * GRID, y, x1, y1, x2, y2) <= rr:
                        row[i] = 1

        def mark_box(L, l, t, r, btm, extra):
            i0, j0 = self.ij(l - extra, t - extra)
            i1, j1 = self.ij(r + extra, btm + extra)
            for j in range(max(0, j0), min(ny, j1 + 1)):
                row = blk[L][j]
                for i in range(max(0, i0), min(nx, i1 + 1)):
                    row[i] = 1

        # board outline: block cells outside (or too close to) the edge
        for j in range(ny):
            for i in range(nx):
                x, y = self.xy(i, j)
                if not self._inside(x, y) or self._edge_close(x, y, 0.5 + hw):
                    for L in LAYERS:
                        blk[L][j][i] = 1
        # tracks and vias of other nets
        for t in self.b.GetTracks():
            if t.GetNetname() == net:
                continue
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                for L in LAYERS:
                    mark_seg(L, ToMM(p.x), ToMM(p.y), ToMM(p.x), ToMM(p.y), ToMM(t.GetWidth(pcbnew.F_Cu)) / 2)
            else:
                L = t.GetLayer()
                if L in LAYERS:
                    a, c = t.GetStart(), t.GetEnd()
                    mark_seg(L, ToMM(a.x), ToMM(a.y), ToMM(c.x), ToMM(c.y), ToMM(t.GetWidth()) / 2)
        # pads of other nets (+ all holes)
        for fp in self.b.GetFootprints():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                l, tp, r, bt = ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())
                same = pad.GetNetname() == net and net != ""
                for L in LAYERS:
                    if pad.IsOnLayer(L) and not same:
                        shp = pad.GetShape(L) if pad.GetShape.__code__.co_argcount > 1 else pad.GetShape()
                        round_pad = shp == pcbnew.PAD_SHAPE_CIRCLE or (
                            shp == pcbnew.PAD_SHAPE_OVAL and abs((r - l) - (bt - tp)) < 0.05)
                        if round_pad:
                            cx, cy = (l + r) / 2, (tp + bt) / 2
                            mark_seg(L, cx, cy, cx, cy, (r - l) / 2)
                        else:
                            mark_box(L, l, tp, r, bt, hw + CLR)
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    for L in LAYERS:
                        mark_box(L, l, tp, r, bt, hw + 0.5)
        # rule-area keep-outs (tracks)
        for z in self.b.Zones():
            if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                bb = z.GetBoundingBox()
                for L in LAYERS:
                    if z.IsOnLayer(L):
                        mark_box(L, ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()),
                                 ToMM(bb.GetBottom()), hw + 0.05)
        self.blk = blk
        # via allowed where a via-sized circle clears both layers: approximate by
        # requiring the cell and its neighbours within (via_r - hw) to be free
        k = int(math.ceil((VIA_D / 2 - hw) / GRID))
        via = [bytearray(nx) for _ in range(ny)]
        for j in range(k, ny - k):
            for i in range(k, nx - k):
                ok = True
                for L in LAYERS:
                    for dj in range(-k, k + 1):
                        row = blk[L][j + dj]
                        for di in range(-k, k + 1):
                            if di * di + dj * dj <= k * k and row[i + di]:
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        break
                via[j][i] = 1 if ok else 0
        self.via = via

    def _inside(self, x, y):
        e, n, c = self.edge, len(self.edge), False
        for k in range(n):
            (x1, y1), (x2, y2) = e[k], e[(k + 1) % n]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                c = not c
        return c

    def _edge_close(self, x, y, d):
        e, n = self.edge, len(self.edge)
        for k in range(n):
            (x1, y1), (x2, y2) = e[k], e[(k + 1) % n]
            if seg_dist(x, y, x1, y1, x2, y2) < d:
                return True
        return False

    def astar(self, sources, targets):
        """sources/targets: set of (L, i, j). Returns list of (L, i, j)."""
        tgt_pts = [(i, j) for (_, i, j) in targets]
        ti = sum(p[0] for p in tgt_pts) / len(tgt_pts)
        tj = sum(p[1] for p in tgt_pts) / len(tgt_pts)

        def h(i, j):
            return math.hypot(i - ti, j - tj) * 0.5   # weak heuristic (targets spread)

        dirs = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        g = {}
        prev = {}
        pq = []
        for s in sources:
            g[s] = 0.0
            heapq.heappush(pq, (h(s[1], s[2]), 0.0, s))
        other = {LAYERS[0]: LAYERS[1], LAYERS[1]: LAYERS[0]}
        while pq:
            f, gc, cur = heapq.heappop(pq)
            if gc > g.get(cur, 1e18):
                continue
            if cur in targets:
                path = [cur]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            L, i, j = cur
            nbrs = []
            for di, dj, c in dirs:
                ni, nj = i + di, j + dj
                if 0 <= ni < self.nx and 0 <= nj < self.ny:
                    if not self.blk[L][nj][ni] or (L, ni, nj) in targets:
                        if di and dj and (self.blk[L][j][ni] and self.blk[L][nj][i]):
                            continue
                        nbrs.append(((L, ni, nj), c))
            if self.via[j][i]:
                nbrs.append(((other[L], i, j), VIA_COST))
            for nxt, c in nbrs:
                ng = gc + c
                if ng < g.get(nxt, 1e18):
                    g[nxt] = ng
                    prev[nxt] = cur
                    heapq.heappush(pq, (ng + h(nxt[1], nxt[2]), ng, nxt))
        return None


def connected_items(board, pad):
    """Copper items of pad's net connected to the pad (by endpoint touch)."""
    net = pad.GetNetname()
    items = [t for t in board.GetTracks() if t.GetNetname() == net]
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == net]
    def touches(a, b):
        return a.HitTest(b.GetStart() if hasattr(b, "GetStart") else b.GetPosition()) or \
            (hasattr(b, "GetEnd") and a.HitTest(b.GetEnd()))
    group = {id(pad): pad}
    changed = True
    allitems = items + pads
    while changed:
        changed = False
        for it in allitems:
            if id(it) in group:
                continue
            for g in list(group.values()):
                if touches(g, it) or touches(it, g):
                    group[id(it)] = it
                    changed = True
                    break
    return group


def track_cluster(board, net, seed):
    """All tracks/vias of `net` connected (end-to-end) to the seed track."""
    items = [t for t in board.GetTracks() if t.GetNetname() == net]

    def ends(t):
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            return [(p.x, p.y)]
        return [(t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)]

    cl, frontier = {id(seed): seed}, [seed]
    tol = FromMM(0.05)
    while frontier:
        cur = frontier.pop()
        ce = ends(cur)
        for t in items:
            if id(t) in cl:
                continue
            if any(abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol for a in ce for b in ends(t)) \
                    or any(t.HitTest(pcbnew.VECTOR2I(int(a[0]), int(a[1]))) for a in ce) \
                    or any(cur.HitTest(pcbnew.VECTOR2I(int(b[0]), int(b[1]))) for b in ends(t)):
                cl[id(t)] = t
                frontier.append(t)
    return list(cl.values())


def route(board, R, net, ref, padnum, tx, ty):
    """Route from REF.PAD to the copper island of `net` that contains point (tx, ty) mm."""
    fp = board.FindFootprintByReference(ref)
    pad = [p for p in fp.Pads() if p.GetNumber() == padnum][0]
    assert pad.GetNetname() == net, (pad.GetNetname(), net)
    seeds = [t for t in board.GetTracks() if t.GetNetname() == net and t.GetClass() != "PCB_VIA"
             and seg_dist(tx, ty, ToMM(t.GetStart().x), ToMM(t.GetStart().y),
                          ToMM(t.GetEnd().x), ToMM(t.GetEnd().y)) < 0.1]
    if not seeds:
        print(net, "no track of this net at", tx, ty)
        return False
    island = track_cluster(board, net, seeds[0])
    island_ids = {id(t) for t in island}
    group = {id(t): t for t in board.GetTracks() if id(t) not in island_ids}   # everything else = exclude
    print("%s: target island has %d items" % (net, len(island)))
    R.build(net)
    # sources: cells inside the source pad (on any copper layer it has)
    pc = pad.GetPosition()
    px, py = ToMM(pc.x), ToMM(pc.y)
    si, sj = R.ij(px, py)
    sources = set()
    for L in LAYERS:
        if pad.IsOnLayer(L):
            for dj in range(-2, 3):
                for di in range(-2, 3):
                    sources.add((L, si + di, sj + dj))
    # targets: centre-line cells of same-net copper not in the pad's group
    targets = set()
    for t in board.GetTracks():
        if t.GetNetname() != net or id(t) in group:
            continue
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            i, j = R.ij(ToMM(p.x), ToMM(p.y))
            for L in LAYERS:
                targets.add((L, i, j))
            continue
        a, c = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = ToMM(a.x), ToMM(a.y), ToMM(c.x), ToMM(c.y)
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / GRID))
        for k in range(n + 1):
            i, j = R.ij(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n)
            # only cells exactly on the centre line (within 0.05 mm)
            cx, cy = R.xy(i, j)
            if seg_dist(cx, cy, x1, y1, x2, y2) <= 0.05:
                targets.add((t.GetLayer(), i, j))
    # never terminate inside the source pad's own area
    targets -= sources
    if not targets:
        print(net, "nothing to connect to")
        return False
    path = R.astar(sources, targets)
    if not path:
        print(net, "NO ROUTE FOUND")
        return False
    # emit: compress into segments, vias at layer changes; start at the pad centre
    netinfo = board.FindNet(net)
    pts = [(path[0][0], px, py)] + [(L,) + R.xy(i, j) for (L, i, j) in path]
    added_tracks = added_vias = 0
    k = 0
    while k < len(pts) - 1:
        L = pts[k][0]
        # extend while same layer and same direction
        m = k + 1
        if pts[m][0] != L:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I_MM(pts[k][1], pts[k][2]))
            v.SetWidth(FromMM(VIA_D))
            v.SetDrill(FromMM(VIA_DRILL))
            v.SetNet(netinfo)
            board.Add(v)
            added_vias += 1
            k = m
            continue
        d0 = (round(pts[m][1] - pts[k][1], 4), round(pts[m][2] - pts[k][2], 4))
        while m + 1 < len(pts) and pts[m + 1][0] == L and \
                (round(pts[m + 1][1] - pts[m][1], 4), round(pts[m + 1][2] - pts[m][2], 4)) == d0 and k > 0:
            m += 1
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(pcbnew.VECTOR2I_MM(pts[k][1], pts[k][2]))
        tr.SetEnd(pcbnew.VECTOR2I_MM(pts[m][1], pts[m][2]))
        tr.SetWidth(FromMM(TRACK_W))
        tr.SetLayer(L)
        tr.SetNet(netinfo)
        board.Add(tr)
        added_tracks += 1
        k = m
    length = sum(math.hypot(pts[q + 1][1] - pts[q][1], pts[q + 1][2] - pts[q][2])
                 for q in range(len(pts) - 1) if pts[q][0] == pts[q + 1][0])
    print("%s: routed %s.%s, %d segments, %d vias, %.1f mm" % (net, ref, padnum, added_tracks, added_vias, length))
    return True


def main():
    path = sys.argv[1]
    jobs = sys.argv[2:]
    board = pcbnew.LoadBoard(path)
    R = Router(board)
    ok = True
    for q in range(0, len(jobs), 5):
        ok &= route(board, R, jobs[q], jobs[q + 1], jobs[q + 2], float(jobs[q + 3]), float(jobs[q + 4]))
    board.Save(path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
