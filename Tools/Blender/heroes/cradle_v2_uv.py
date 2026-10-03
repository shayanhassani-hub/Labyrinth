"""
Cradle v2 low-poly: hard edges, UV seams, unwrap and packing (ASSET_RULES hero standard, Step 4 / 4b).
Used by cradle_v2.build(). Works on Blender meshes (Blender axes: z = spec y = up, -y = spec +z = back).

Step 4b: fewer, larger islands.
Hard edges (always UV seams): only where shading needs them. Corners < SMOOTH_DEG stay smooth (face-area weighted
  normals); corners >= HARD_DEG are hard; in between they stay smooth when one side is a chamfer strip (narrow and
  long face), otherwise hard.
Cap / wall split: an island whose longest border loop is planar is split between the faces facing along that loop's
  axis (caps: tops, floors, round end faces) and the faces around it (walls); chamfer strips go with their larger
  neighbour.
Rings (islands with two border loops: tier walls, turntable, collars, flat annuli): ONE cut at the back (+Z spec,
  preferring a corner), straightened with follow-active-quads; a second cut opposite (on a corner) only when the
  strip is longer than MAX_STRIP. A ring that cannot be flattened within the stretch limits that way is split into
  2, 4 or 8 sectors at corners (the fewest that pass). Islands with more loops are first joined by one cut per extra
  loop.
Everything else: planar islands = exact projection; curved = angle based, straightened with follow-active-quads
  where all quads and within the limits; islands outside the limits are split at a chamfer border (the chamfer stays
  with the larger face) or across their long axis.
Orientation: each island's minimum-area rectangle is turned so its long side runs along U; world up points to +V
  (or +U when up runs along the long side). Packing may turn an island by 90 deg (stays aligned to U/V).
"""
import bpy
import bmesh
import math
import numpy as np
from mathutils import Vector
from heapq import heappush, heappop

SMOOTH_DEG = 55.0              # dihedral below this: smooth
HARD_DEG = 75.0                # dihedral at or above this: hard; between: smooth next to a chamfer strip
STRIP_W = 0.040                # chamfer strip: width (area / longest edge) below this ...
STRIP_ASPECT = 2.5             # ... and longest edge > this x width
CAP_DOT = 0.80                 # cap face: |normal . loop axis| >= this
PLANAR_DEG = 2.0
STRETCH_MAX = 1.20             # per-island face area ratio limits (max / median, median / min)
ANGLE_MAX = 12.0               # per-island max corner angle deviation (deg), faces > 2 cm2
RING_ANGLE_MAX = 25.0          # ... for straightened ring strips: a trapezoid at a 45 deg octagon corner shears by 22.5 deg
FILL_MIN = 0.5                 # islands filling less of their min-area rectangle are cut in two
SPLIT_MIN_LEN = 0.20           # ... when their long side exceeds this (m)
MAX_STRIP = 4.1                # longest island (m): fits the 2048 sheet up to ~495 px/m
CORNER_DEG = 15.0              # ring outline turn that counts as a corner for cuts
RING_SECTORS = (1, 2, 4, 8)
ROUNDS = 14
TEX = 2048
PAD_PX, BORDER_PX = 16, 8
LOG = None                     # debug: list -> ring trial log
FAQ_LOG = None                 # debug: list -> follow-active-quads results


def face_width(f):
    lmax = max(e.calc_length() for e in f.edges)
    return f.calc_area() / lmax if lmax > 0 else 0.0


def is_strip(f):
    lmax = max(e.calc_length() for e in f.edges)
    w = f.calc_area() / lmax if lmax > 0 else 0.0
    return w < STRIP_W and lmax > STRIP_ASPECT * w


def dihedral(e):
    return math.degrees(e.calc_face_angle(0.0)) if len(e.link_faces) == 2 else 180.0


def is_hard(e):
    if len(e.link_faces) != 2: return False
    a = dihedral(e)
    if a < SMOOTH_DEG: return False
    if a < HARD_DEG and any(is_strip(f) for f in e.link_faces): return False
    return True


def is_chamfer_border(e):
    """smooth inner edge between a chamfer strip and a wider face"""
    if len(e.link_faces) != 2 or e.seam: return False
    f1, f2 = e.link_faces
    return dihedral(e) > 1.0 and is_strip(f1) != is_strip(f2)


def mark_edges(bm):
    """hard edges + base seams (open borders). Returns number of hard edges."""
    n = 0
    for e in bm.edges:
        e.smooth = True; e.seam = len(e.link_faces) != 2
        if is_hard(e):
            e.smooth = False; e.seam = True; n += 1
    return n


def islands(bm, faces=None):
    """seam-bounded islands (restricted to the given faces, if given)"""
    pool = set(faces) if faces is not None else None
    seen = set(); out = []
    for f in (faces if faces is not None else bm.faces):
        if f in seen: continue
        stack = [f]; seen.add(f); isl = []
        while stack:
            g = stack.pop(); isl.append(g)
            for e in g.edges:
                if e.seam: continue
                for h in e.link_faces:
                    if h not in seen and (pool is None or h in pool): seen.add(h); stack.append(h)
        out.append(isl)
    return out


def border_loops(isl):
    fs = set(isl)
    bedges = list({e for f in isl for e in f.edges
                   if e.seam or len(e.link_faces) < 2 or any(g not in fs for g in e.link_faces)})
    adj = {}
    for e in bedges:
        for v in e.verts: adj.setdefault(v, []).append(e)
    seen = set(); loops = []
    for e in bedges:
        if e in seen: continue
        stack = [e]; seen.add(e); comp = []
        while stack:
            x = stack.pop(); comp.append(x)
            for v in x.verts:
                for y in adj[v]:
                    if y not in seen: seen.add(y); stack.append(y)
        loops.append(comp)
    return loops


def order_loop(L):
    """vertices of a simple closed edge loop in order (None if the loop is not simple)"""
    adj = {}
    for e in L:
        for v in e.verts: adj.setdefault(v, []).append(e)
    if any(len(x) != 2 for x in adj.values()): return None
    e = L[0]; v0 = e.verts[0]; out = [v0]; v = v0
    while True:
        w = e.other_vert(v)
        if w is v0: break
        out.append(w); e = adj[w][0] if adj[w][1] is e else adj[w][1]; v = w
        if len(out) > len(adj): return None
    return out if len(out) == len(adj) else None


def _path(isl, src, dst):
    """cheapest inner-edge path from vertex set src to vertex set dst (prefers corner edges); list of edges"""
    fs = set(isl)
    inner = {e for f in isl for e in f.edges if not e.seam and all(g in fs for g in e.link_faces)}
    dist = {v: 0.0 for v in src}; prev = {}; heap = [(0.0, v.index, v) for v in src]
    while heap:
        d, _, v = heappop(heap)
        if d > dist.get(v, 1e9): continue
        if v in dst:
            out = []
            while v in prev:
                u, e = prev[v]; out.append(e); v = u
            return out
        for e in v.link_edges:
            if e not in inner: continue
            w = e.other_vert(v); nd = d + e.calc_length() * (2.0 - min(dihedral(e), 40.0) / 40.0)
            if nd < dist.get(w, 1e9): dist[w] = nd; prev[w] = (v, e); heappush(heap, (nd, w.index, w))
    return None


def class_split(bm):
    """cap / wall split per island (see module doc). Returns number of new seam edges."""
    n = 0
    for isl in islands(bm):
        loops = border_loops(isl)
        if not loops or len(isl) < 3: continue
        best = max(loops, key=lambda L: sum(e.calc_length() for e in L))
        P = np.array([v.co[:] for e in best for v in e.verts]); c = P.mean(0)
        w, vec = np.linalg.eigh((P - c).T @ (P - c))
        if w[0] <= 0.02 * w[1]:
            ax = Vector(vec[:, 0])                               # planar loop: its axis
        else:                                                    # else the main axis that classifies most clearly
            def decisive(a):
                return sum(f.calc_area() for f in isl if abs(f.normal.dot(a)) >= CAP_DOT or abs(f.normal.dot(a)) <= 0.25)
            ax = max((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), key=decisive)
        fs = set(isl)
        own = {f: abs(f.normal.dot(ax)) >= CAP_DOT for f in isl}
        cap = dict(own)
        for f in isl:                                            # chamfer strips join their larger neighbour:
            if not is_strip(f): continue                         # the largest wide one, else the largest strip
            nb = [g for e in f.edges if not e.seam for g in e.link_faces if g is not f and g in fs]
            wide = [g for g in nb if not is_strip(g)]
            if wide: cap[f] = own[max(wide, key=lambda g: g.calc_area())]
            elif nb: cap[f] = own[max(nb, key=lambda g: g.calc_area())]
        a = sum(f.calc_area() for f in isl); ac = sum(f.calc_area() for f in isl if cap[f])
        if ac < 0.03 * a or ac > 0.97 * a: continue
        for f in isl:
            for e in f.edges:
                if not e.seam and len(e.link_faces) == 2 and all(g in fs for g in e.link_faces) \
                        and cap[e.link_faces[0]] != cap[e.link_faces[1]]:
                    e.seam = True; n += 1
    return n


def join_loops(bm):
    """islands with more than two border loops: cut from the shortest loop to another one until two remain"""
    cuts = 0
    for _ in range(200):
        done = True
        for isl in islands(bm):
            loops = border_loops(isl)
            if len(loops) <= 2: continue
            lens = [sum(e.calc_length() for e in L) for L in loops]
            i = int(np.argmin(lens))
            src = {v for e in loops[i] for v in e.verts}
            dst = {v for j, L in enumerate(loops) if j != i for e in L for v in e.verts}
            p = _path(isl, src, dst)
            if p:
                for e in p: e.seam = True
                cuts += 1; done = False
                break
        if done: break
    return cuts


# --------------------------------------------------------------------------- quality measures


def _poly_area(uvs):
    s = 0.0
    for i in range(len(uvs)):
        a, b = uvs[i], uvs[(i + 1) % len(uvs)]; s += a[0] * b[1] - b[0] * a[1]
    return s / 2


def _corner_angles(pts):
    n = len(pts); out = []
    for i in range(n):
        a = pts[i - 1] - pts[i]; b = pts[(i + 1) % n] - pts[i]
        c = np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12)
        out.append(math.degrees(math.acos(max(-1.0, min(1.0, c)))))
    return np.array(out)


def island_quality(isl, uvl, strips=True):
    """(area ratio max/median, median/min, max angle deviation) over faces > 2 cm2; strips=False leaves chamfer
    strips out of the angle (straightened rings: the shear inside a narrow chamfer strip is accepted, reported)"""
    r = []; ang = [0.0]
    for f in isl:
        a3 = f.calc_area()
        if a3 < 2e-4: continue
        U = [np.array(l[uvl].uv[:]) for l in f.loops]; P = [np.array(l.vert.co[:]) for l in f.loops]
        r.append(abs(_poly_area(U)) / a3)
        if strips or not is_strip(f):
            ang.append(np.abs(_corner_angles(P) - _corner_angles(U)).max())
    if not r: return 1.0, 1.0, 0.0
    r = np.array(r); m = np.median(r)
    return r.max() / m, m / max(r.min(), 1e-12), max(ang)


def within_limits(q, angle_max=ANGLE_MAX):
    return q[0] <= STRETCH_MAX and q[1] <= STRETCH_MAX and q[2] <= angle_max


def is_planar(isl):
    n = sum((f.normal * f.calc_area() for f in isl), Vector()); n.normalize()
    return all(f.normal.angle(n, 0.0) < math.radians(PLANAR_DEG) for f in isl), n


def planar_project(isl, uvl, n):
    up = Vector((0, 0, 1))
    if abs(n.z) < 0.7:
        V = (up - n * up.dot(n)).normalized(); U = V.cross(n)
    else:
        U = Vector((1, 0, 0)); U = (U - n * U.dot(n)).normalized(); V = n.cross(U)
    for f in isl:
        for l in f.loops:
            l[uvl].uv = (l.vert.co.dot(U), l.vert.co.dot(V))


def _hull(p):
    p = sorted(set(map(tuple, np.round(p, 9))))
    if len(p) < 3: return np.array(p)
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for q in p:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0: lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], q) <= 0: hi.pop()
        hi.append(q)
    return np.array(lo[:-1] + hi[:-1])


def orient(isl, uvl):
    """min-area rectangle, long side along U; world up to +V (or +U if up runs along the long side)"""
    loops = [l for f in isl for l in f.loops]
    U = np.array([l[uvl].uv[:] for l in loops]); Z = np.array([l.vert.co.z for l in loops])
    c = U.mean(0); H = _hull(U - c)
    best = None
    for i in range(len(H)):
        e = H[(i + 1) % len(H)] - H[i]
        if np.linalg.norm(e) < 1e-12: continue
        th = -math.atan2(e[1], e[0]); R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        Q = H @ R.T; w, h = np.ptp(Q[:, 0]), np.ptp(Q[:, 1])
        if best is None or w * h < best[0] - 1e-12:
            best = (w * h, th if w >= h else th + math.pi / 2)
    th = best[1] if best else 0.0
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    Q = (U - c) @ R.T
    if np.ptp(Z) > 1e-4:
        g = np.linalg.lstsq(np.column_stack((Q, np.ones(len(Q)))), Z, rcond=None)[0][:2]
        if abs(g[1]) >= abs(g[0]) * 0.5:
            if g[1] < 0: Q = -Q
        elif g[0] < 0: Q = -Q
    for l, q in zip(loops, Q):
        l[uvl].uv = (q[0], q[1])


def _min_rect(U):
    """(angle that puts the long side of the minimum-area rectangle along U, rect area, long side)"""
    c = U.mean(0); H = _hull(U - c); best = None
    for i in range(len(H)):
        e = H[(i + 1) % len(H)] - H[i]
        if np.linalg.norm(e) < 1e-12: continue
        th = -math.atan2(e[1], e[0]); R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        Q = H @ R.T; w, h = np.ptp(Q[:, 0]), np.ptp(Q[:, 1])
        if best is None or w * h < best[1] - 1e-15:
            best = (th if w >= h else th + math.pi / 2, w * h, max(w, h))
    return best or (0.0, 0.0, 0.0)


def island_fill(isl, uvl):
    """(UV area / minimum-rectangle area, long side in metres)"""
    U = np.array([l[uvl].uv[:] for f in isl for l in f.loops])
    a2 = abs(sum(_poly_area([l[uvl].uv for l in f.loops]) for f in isl)); a3 = sum(f.calc_area() for f in isl)
    th, ra, lng = _min_rect(U)
    return (a2 / ra if ra > 0 else 1.0), lng * math.sqrt(a3 / max(a2, 1e-15))


def self_overlap(isl, uvl):
    """True if the island's UV outline crosses itself (proper segment intersections)"""
    sa = [_poly_area([l[uvl].uv for l in f.loops]) for f in isl]
    if min(sa) < 0 < max(sa): return True                          # a face folded over inside the island
    fs = set(isl); seg = []
    for f in isl:
        for l in f.loops:
            e = l.edge
            if e.seam or len(e.link_faces) != 2 or any(g not in fs for g in e.link_faces):
                seg.append((np.array(l[uvl].uv[:]), np.array(l.link_loop_next[uvl].uv[:])))
    if len(seg) < 4: return False
    A = np.array([s[0] for s in seg]); B = np.array([s[1] for s in seg])
    eps = 1e-9 * max(np.ptp(np.vstack((A, B)), 0).max(), 1e-12)

    def orient_(p, q, r): return (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0])
    for i in range(len(seg)):
        a, b = A[i], B[i]
        d1 = orient_(a, b, A); d2 = orient_(a, b, B); d3 = orient_(A, B, a); d4 = orient_(A, B, b)
        hit = (d1 * d2 < -eps * eps) & (d3 * d4 < -eps * eps)
        if hit.any(): return True
    return False


def piece_ok(isl, uvl, angle_max=ANGLE_MAX):
    """(passes, quality, fill, long side m): within the stretch limits, no self overlap, compact or short, not too long"""
    q = island_quality(isl, uvl, strips=angle_max == ANGLE_MAX)
    fill, long_m = island_fill(isl, uvl)
    ok = within_limits(q, angle_max) and not (len(isl) > 1 and self_overlap(isl, uvl)) \
        and (fill >= FILL_MIN or long_m <= SPLIT_MIN_LEN) and long_m <= MAX_STRIP
    return ok, q, fill, long_m


# --------------------------------------------------------------------------- splitting


def split_chamfers(isl):
    """seam the chamfer borders of a badly flattened island (the side towards the smaller wide face)"""
    n = 0
    for f in isl:
        if not is_strip(f): continue
        bs = [e for e in f.edges if is_chamfer_border(e)]
        if not bs: continue
        e = min(bs, key=lambda e: next(g for g in e.link_faces if g is not f).calc_area())
        e.seam = True; n += 1
    if n == 0:                                     # no chamfers: cut the strongest smooth folds
        es = sorted({e for f in isl for e in f.edges if not e.seam and len(e.link_faces) == 2},
                    key=lambda e: -e.calc_face_angle(0.0))
        for e in es[:max(1, len(es) // 8)]:
            if e.calc_face_angle(0.0) > math.radians(10): e.seam = True; n += 1
    return n


def split_median(isl, uvl):
    """cut a bent or sprawling island in two across its long axis (at the area median)"""
    U = np.array([l[uvl].uv[:] for f in isl for l in f.loops])
    th = _min_rect(U)[0]; d = np.array([math.cos(-th), math.sin(-th)])
    cs = np.array([np.mean([l[uvl].uv[:] for l in f.loops], 0) @ d for f in isl])
    w = np.array([f.calc_area() for f in isl]); o = np.argsort(cs)
    cum = np.cumsum(w[o])[:-1]                                  # split after rank k (1 .. n-1 faces on side A)
    k = int(np.argmin(np.abs(cum - w.sum() / 2))) + 1
    rank = np.empty(len(isl), int); rank[o] = np.arange(len(isl))
    side = {f: rank[i] < k for i, f in enumerate(isl)}
    n = 0
    for f in isl:
        for e in f.edges:
            if e.seam or len(e.link_faces) != 2: continue
            g = e.link_faces[0] if e.link_faces[1] is f else e.link_faces[1]
            if g in side and side[g] != side[f]: e.seam = True; n += 1
    return n


# --------------------------------------------------------------------------- unwrap (edit mode)


def _edit_bm(o):
    bm = bmesh.from_edit_mesh(o.data)
    bm.faces.index_update(); bm.edges.index_update(); bm.verts.index_update()
    bm.faces.ensure_lookup_table(); bm.edges.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    return bm, bm.loops.layers.uv.active


def grid_coords(isl):
    """integer (i, j) per face corner of an all-quad island that is a topological grid (seams respected);
    None if the quads do not form a consistent grid"""
    fs = set(isl)
    f0 = max(isl, key=lambda f: f.calc_area())
    ij = {}
    for l, c in zip(f0.loops, ((0, 0), (1, 0), (1, 1), (0, 1))): ij[(f0, l.vert)] = c
    queue = [f0]; done = {f0}
    while queue:
        f = queue.pop()
        for lp in f.loops:
            e = lp.edge
            if e.seam or len(e.link_faces) != 2: continue
            g = e.link_faces[0] if e.link_faces[1] is f else e.link_faces[1]
            if g not in fs or g in done: continue
            a, b = lp.vert, lp.link_loop_next.vert                 # f walks a -> b; g walks b -> a
            fa = lp.link_loop_prev.vert                             # f's corner next to a (off the edge)
            A, B, Fa = ij[(f, a)], ij[(f, b)], ij[(f, fa)]
            if abs(A[0] - B[0]) + abs(A[1] - B[1]) != 1: return None
            d = (A[0] - Fa[0], A[1] - Fa[1])
            gl = next(x for x in g.loops if x.vert is b)          # g: b -> a -> c -> d'
            la = gl.link_loop_next; lc = la.link_loop_next; ld = lc.link_loop_next
            if la.vert is not a: return None
            ij[(g, b)] = B; ij[(g, a)] = A
            ij[(g, lc.vert)] = (A[0] + d[0], A[1] + d[1]); ij[(g, ld.vert)] = (B[0] + d[0], B[1] + d[1])
            done.add(g); queue.append(g)
    if len(done) != len(isl): return None
    for f in isl:                                                   # every inner edge must agree on both sides
        for lp in f.loops:
            e = lp.edge
            if e.seam or len(e.link_faces) != 2: continue
            g = e.link_faces[0] if e.link_faces[1] is f else e.link_faces[1]
            if g not in fs: continue
            for v in e.verts:
                if ij[(f, v)] != ij[(g, v)]: return None
    return ij


def grid_straighten(isl, uvl):
    """straight strip: column widths / row heights = average 3D edge length per grid column / row. False if no grid."""
    ij = grid_coords(isl)
    if ij is None: return False
    du, dv = {}, {}
    for f in isl:
        for lp in f.loops:
            a, b = lp.vert, lp.link_loop_next.vert
            A, B = ij[(f, a)], ij[(f, b)]; ln = (a.co - b.co).length
            if A[1] == B[1]: du.setdefault(min(A[0], B[0]), []).append(ln)
            else: dv.setdefault(min(A[1], B[1]), []).append(ln)
    def cum(d):
        ks = sorted(d); out = {ks[0]: 0.0}; x = 0.0
        for k in range(ks[0], ks[-1] + 1):
            x += float(np.mean(d[k])) if k in d else 0.0; out[k + 1] = x
        return out
    U, V = cum(du), cum(dv)
    for f in isl:
        for lp in f.loops:
            i, j = ij[(f, lp.vert)]; lp[uvl].uv = (U[i], V[j])
    return True


def _straighten(o, idx, angle_max=ANGLE_MAX):
    """straight strip on one all-quad island (grid straightener, else Blender follow-active-quads); kept only if
    within the limits. Returns True if kept."""
    bm, uvl = _edit_bm(o)
    isl = [bm.faces[i] for i in idx]
    before = {(f.index, k): l[uvl].uv.copy() for f in isl for k, l in enumerate(f.loops)}
    if grid_straighten(isl, uvl):
        q = island_quality(isl, uvl, strips=angle_max == ANGLE_MAX)
        if FAQ_LOG is not None: FAQ_LOG[tuple(idx)] = [round(float(x), 2) for x in q]
        ok = within_limits(q, angle_max) and not self_overlap(isl, uvl)
        if not ok:
            for f in isl:
                for k, l in enumerate(f.loops): l[uvl].uv = before[(f.index, k)]
        bmesh.update_edit_mesh(o.data)
        return ok
    for f in bm.faces: f.select = False
    for f in isl: f.select = True
    act = max(isl, key=lambda f: f.calc_area()); bm.faces.active = act
    ls = list(act.loops); a = ls[0].edge.calc_length(); b = ls[1].edge.calc_length(); p0 = ls[0][uvl].uv.copy()
    ls[1][uvl].uv = p0 + Vector((a, 0)); ls[2][uvl].uv = p0 + Vector((a, b)); ls[3][uvl].uv = p0 + Vector((0, b))
    bmesh.update_edit_mesh(o.data)
    try:
        bpy.ops.uv.follow_active_quads(mode='LENGTH_AVERAGE'); ok = True
    except RuntimeError:
        ok = False
    bm, uvl = _edit_bm(o)
    isl = [bm.faces[i] for i in idx]
    if ok:
        q = island_quality(isl, uvl)
        if FAQ_LOG is not None: FAQ_LOG[tuple(idx)] = [round(float(x), 2) for x in q]
        ok = within_limits(q, angle_max) and not self_overlap(isl, uvl)
    if not ok:
        for f in isl:
            for k, l in enumerate(f.loops): l[uvl].uv = before[(f.index, k)]
    bmesh.update_edit_mesh(o.data)
    return ok


def unwrap_pieces(o, idx, stats, ring=False):
    """unwrap the faces idx on their seams: planar islands projected exactly, all-quad islands straightened where
    that stays within the limits, the rest angle based. Returns [(face indices, passes, fill, long m)] per island."""
    bm, uvl = _edit_bm(o)
    for f in bm.faces: f.select = False
    for i in idx: bm.faces[i].select = True
    bmesh.update_edit_mesh(o.data)
    bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=False, margin=0.001)
    bm, uvl = _edit_bm(o)
    pieces = [[f.index for f in isl] for isl in islands(bm, [bm.faces[i] for i in idx])]
    quads = []
    for pid in pieces:
        isl = [bm.faces[i] for i in pid]
        pl, n = is_planar(isl)
        if pl: planar_project(isl, uvl, n)
        if len(isl) > 1 and all(len(f.verts) == 4 for f in isl) and (not pl or island_fill(isl, uvl)[0] < FILL_MIN):
            quads.append(pid)
    bmesh.update_edit_mesh(o.data)
    straight = set()
    for pid in quads:
        if _straighten(o, pid, RING_ANGLE_MAX if ring else ANGLE_MAX): straight.add(tuple(pid))
    bm, uvl = _edit_bm(o)
    out = []
    for pid in pieces:
        ok, q, fill, long_m = piece_ok([bm.faces[i] for i in pid], uvl,
                                       RING_ANGLE_MAX if ring and tuple(pid) in straight else ANGLE_MAX)
        out.append((pid, ok, fill, long_m, tuple(pid) in straight))
    return out


def ring_trial(o, idx, stats):
    """one ring island (two border loops): cut at the back (+ opposite if too long), else 2 / 4 / 8 sectors at
    corners; keeps the first variant whose pieces all pass. Returns the face index lists of the accepted pieces
    (or None: the last variant's cuts stay, the pieces go to the generic loop)."""
    bm, _ = _edit_bm(o)
    isl = [bm.faces[i] for i in idx]
    loops = border_loops(isl)
    lens = [sum(e.calc_length() for e in L) for L in loops]
    outer, inner = (loops[0], loops[1]) if lens[0] >= lens[1] else (loops[1], loops[0])
    ov = order_loop(outer)
    if ov is None: ov = order_loop(inner); outer, inner = inner, outer
    if ov is None: return None
    oset = set(outer); ivs = {v for e in inner for v in e.verts}
    n = len(ov)
    seg = [(ov[(i + 1) % n].co - ov[i].co).length for i in range(n)]
    cum = np.concatenate(([0.0], np.cumsum(seg)[:-1])); L = float(sum(seg))

    def turn(v):
        es = [e for e in v.link_edges if e in oset]
        if len(es) != 2: return 0.0
        d1 = (es[0].other_vert(v).co - v.co).normalized(); d2 = (es[1].other_vert(v).co - v.co).normalized()
        return 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, d1.dot(d2)))))
    tv = [turn(v) for v in ov]
    span = max(np.ptp([v.co.y for v in ov]), 1e-6)
    s0 = max(range(n), key=lambda i: -ov[i].co.y / span + 0.05 * min(tv[i], 45.0) / 45.0)
    ov_idx = [v.index for v in ov]; iv_idx = [v.index for v in ivs]
    last = None
    for k in RING_SECTORS:
        if k == 1 and L > MAX_STRIP * 1.02: continue
        starts = [s0]
        for j in range(1, k):
            t = (cum[s0] + j * L / k) % L
            starts.append(min(range(n), key=lambda i: min(abs(cum[i] - t), L - abs(cum[i] - t))
                              + (0.0 if tv[i] >= CORNER_DEG else 0.15 * L / k)))
        bm, _ = _edit_bm(o)
        isl = [bm.faces[i] for i in idx]
        added = []
        for s in starts:
            p = _path(isl, {bm.verts[ov_idx[s]]}, {bm.verts[i] for i in iv_idx})
            for e in (p or []):
                if not e.seam: e.seam = True; added.append(e.index)
        bmesh.update_edit_mesh(o.data)
        res = unwrap_pieces(o, idx, stats, ring=True)
        last = (k, added)
        if LOG is not None:
            bm, uvl = _edit_bm(o)
            c = sum((bm.faces[i].calc_center_median() for i in idx), Vector()) / len(idx)
            LOG.append(dict(obj=o.name[-9:], at=(round(-c.x, 2), round(c.z, 3), round(-c.y, 2)), faces=len(idx), L=round(L, 2), k=k,
                            pieces=[(len(r[0]), r[1], [round(float(x), 2) for x in island_quality([bm.faces[i] for i in r[0]], uvl)], (FAQ_LOG or {}).get(tuple(r[0])),
                                     round(r[2], 2), round(r[3], 2), r[4]) for r in res]))
        if all(r[1] for r in res):
            stats.setdefault("rings", {}); stats["rings"][k] = stats["rings"].get(k, 0) + 1
            stats["straightened"] = stats.get("straightened", 0) + sum(1 for r in res if r[4])
            return [r[0] for r in res]
        if k == RING_SECTORS[-1]: break
        bm, _ = _edit_bm(o)
        for i in added: bm.edges[i].seam = False
        bmesh.update_edit_mesh(o.data)
    stats.setdefault("rings", {}); stats["rings"]["failed"] = stats["rings"].get("failed", 0) + 1
    return None



def merge_pass(o, stats, sweeps=4):
    """greedy island merging, smallest first: remove the soft seams (not hard edges, not open borders) to a
    neighbour island, re-unwrap the union, keep it when it is one piece that passes (else restore seams and UVs)"""
    total = 0
    for _ in range(sweeps):
        bm, _u = _edit_bm(o)
        isls = islands(bm)
        owner = {f.index: k for k, isl in enumerate(isls) for f in isl}
        order = sorted(range(len(isls)), key=lambda k: sum(f.calc_area() for f in isls[k]))
        ids = [[f.index for f in isl] for isl in isls]
        dead = set(); merged = 0
        for k in order:
            if k in dead: continue
            bm, uvl = _edit_bm(o)
            shared = {}
            for i in ids[k]:
                for e in bm.faces[i].edges:
                    if not e.seam or not e.smooth or len(e.link_faces) != 2: continue
                    for g in e.link_faces:
                        m = owner[g.index]
                        if m != k: shared.setdefault(m, []).append(e)
            cands = sorted(((m, es) for m, es in shared.items() if m not in dead),
                           key=lambda t: -sum(e.calc_length() for e in t[1]))
            for m, es in cands:
                bm, uvl = _edit_bm(o)
                union = ids[k] + ids[m]
                before = {(i, j): l[uvl].uv.copy() for i in union for j, l in enumerate(bm.faces[i].loops)}
                eidx = [e.index for e in es]
                for i in eidx: bm.edges[i].seam = False
                if len(border_loops([bm.faces[i] for i in union])) != 1:
                    for i in eidx: bm.edges[i].seam = True
                    bmesh.update_edit_mesh(o.data); continue
                bmesh.update_edit_mesh(o.data)
                res = unwrap_pieces(o, union, stats)
                if len(res) == 1 and res[0][1]:
                    dead.update((k, m)); merged += 1
                    break
                bm, uvl = _edit_bm(o)
                for i in eidx: bm.edges[i].seam = True
                for (i, j), uv in before.items(): bm.faces[i].loops[j][uvl].uv = uv
                bmesh.update_edit_mesh(o.data)
        total += merged
        if merged == 0: break
    stats["merges"] = total
    return total


def unwrap_object(o):
    """hard edges, seams, unwrap of one object (edit mode); returns stats"""
    view = bpy.context.view_layer
    for x in view.objects: x.select_set(False)
    o.select_set(True); view.objects.active = o
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    stats = {}
    bm, _ = _edit_bm(o)
    stats["hard_edges"] = mark_edges(bm)
    stats["class_seams"] = class_split(bm) + class_split(bm)
    stats["loop_joins"] = join_loops(bm)
    bmesh.update_edit_mesh(o.data)
    locked = set()
    bm, _ = _edit_bm(o)
    rings = [[f.index for f in isl] for isl in islands(bm) if len(border_loops(isl)) == 2]
    for idx in rings:
        acc = ring_trial(o, idx, stats)
        if acc: locked.update(i for p in acc for i in p)
    # generic rounds for everything else
    for rnd in range(ROUNDS):
        bm, _ = _edit_bm(o)
        todo = [f.index for f in bm.faces if f.index not in locked]
        if not todo: break
        res = unwrap_pieces(o, todo, stats)
        bm, uvl = _edit_bm(o)
        bad = 0
        for pid, ok, fill, long_m, st in res:
            isl = [bm.faces[i] for i in pid]
            if ok or rnd == ROUNDS - 1 or len(isl) == 1:
                locked.update(pid); stats["straightened"] = stats.get("straightened", 0) + int(st); continue
            q = island_quality(isl, uvl)
            if not within_limits(q):
                bad += split_chamfers(isl) > 0
            else:
                bad += split_median(isl, uvl) > 0
                stats["median_splits"] = stats.get("median_splits", 0) + 1
        bmesh.update_edit_mesh(o.data)
        stats["generic_rounds"] = rnd + 1
        if bad == 0: break
    merge_pass(o, stats)
    bm, uvl = _edit_bm(o)
    isls = islands(bm)
    stats["planar"] = stats["curved"] = 0
    for isl in isls:
        orient(isl, uvl)
        stats["planar" if is_planar(isl)[0] else "curved"] += 1
    stats["islands"] = len(isls)
    bmesh.update_edit_mesh(o.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    return stats


# --------------------------------------------------------------------------- scale and pack


def scale_islands(o, dens_fn=None):
    """every island to 1 UV unit per metre (x the density factor dens_fn(island faces) if given)"""
    bm = bmesh.new(); bm.from_mesh(o.data); uvl = bm.loops.layers.uv.active
    for isl in islands(bm):
        a3 = sum(f.calc_area() for f in isl)
        a2 = abs(sum(_poly_area([l[uvl].uv for l in f.loops]) for f in isl))
        s = math.sqrt(a3 / max(a2, 1e-12)) * (dens_fn(isl) if dens_fn else 1.0)
        for f in isl:
            for l in f.loops: l[uvl].uv = l[uvl].uv * s
    bm.to_mesh(o.data); bm.free()


ORDERS = (lambda r: (-max(r), -min(r)), lambda r: (-r[1], -r[0]), lambda r: (-r[0] * r[1],), lambda r: (-(r[0] + r[1]),))


def _skyline(rects, W, H, order_key=ORDERS[0]):
    """bottom-left skyline packing of integer rects [(w, h)] into W x H, each placed as is or turned 90 deg
    (whichever ends lower). Returns [(x, y, turned)] or None if they do not fit."""
    sky = [[0, W, 0]]                                  # segments [x, width, y]
    pos = [None] * len(rects)
    order = sorted(range(len(rects)), key=lambda i: order_key(rects[i]))
    for i in order:
        best = None
        for turned in (False, True):
            w, h = rects[i][::-1] if turned else rects[i]
            if w > W: continue
            for s in range(len(sky)):
                x = sky[s][0]
                if x + w > W: break
                y = 0; j = s
                while j < len(sky) and sky[j][0] < x + w:
                    y = max(y, sky[j][2]); j += 1
                if y + h > H: continue
                key = (y + h, x, turned)
                if best is None or key < best[0]: best = (key, x, y, turned, w, h)
        if best is None: return None
        _, x, y, turned, w, h = best
        pos[i] = (x, y, turned)
        new = []
        for sx, sw, sy in sky:
            e = sx + sw
            if e <= x or sx >= x + w: new.append([sx, sw, sy]); continue
            if sx < x: new.append([sx, x - sx, sy])
            if e > x + w: new.append([x + w, e - x - w, sy])
        new.append([x, w, y + h])
        new.sort()
        merged = []
        for seg in new:
            if merged and merged[-1][2] == seg[2] and merged[-1][0] + merged[-1][1] == seg[0]: merged[-1][1] += seg[1]
            else: merged.append(seg)
        sky = merged
    return pos


def pack(objs):
    """pack all islands of objs into one TEX x TEX sheet (90 deg turns allowed), one texel density for all
    (island scale factors from scale_islands kept): skyline packing of the island bounding boxes grown by
    PAD_PX / 2 per side (= BORDER_PX, so the sheet border and the island gap both hold), highest density
    that fits (bisection). Returns the density in px per UV unit (= px/m at factor 1)."""
    assert PAD_PX // 2 == BORDER_PX
    bms = []; isls = []
    for o in objs:
        bm = bmesh.new(); bm.from_mesh(o.data); uvl = bm.loops.layers.uv.active
        bms.append((o, bm, uvl))
        for isl in islands(bm):
            U = np.array([l[uvl].uv[:] for f in isl for l in f.loops])
            isls.append((uvl, isl, U.min(0), np.ptp(U, 0)))

    def rects(d):
        return [(int(math.ceil(sz[0] * d)) + PAD_PX + 1, int(math.ceil(sz[1] * d)) + PAD_PX + 1) for _, _, _, sz in isls]
    best = None
    for key in ORDERS:                                   # several placement orders, the densest wins
        lo, hi = (best[0] if best else 50.0), 2000.0
        for _ in range(40):
            mid = (lo + hi) / 2
            p = _skyline(rects(mid), TEX, TEX, key)
            if p: lo, best = mid, (mid, p)
            else: hi = mid
            if hi - lo < 0.25: break
    d, pos = best
    for (uvl, isl, mn, sz), (x, y, turned) in zip(isls, pos):
        ox = (x + PAD_PX // 2 + 0.5) / TEX; oy = (y + PAD_PX // 2 + 0.5) / TEX
        for f in isl:
            for l in f.loops:
                u, v = l[uvl].uv[0] - mn[0], l[uvl].uv[1] - mn[1]
                if turned: u, v = sz[1] - v, u                  # 90 deg counter-clockwise, kept in the box
                l[uvl].uv = (ox + u * d / TEX, oy + v * d / TEX)
    for o, bm, uvl in bms:
        bm.to_mesh(o.data); bm.free()
    return d


def unwrap_and_pack(objs, dens_fn=None):
    """objs: objects whose UVs share one 0-1 space (each mesh once)."""
    rep = {}
    for o in objs:
        me = o.data
        if not me.uv_layers: me.uv_layers.new(name="UVMap")
        st = unwrap_object(o)
        scale_islands(o, (lambda isl, o=o: dens_fn(o, isl)) if dens_fn else None)
        rep[o.name] = st
    rep["px_per_m"] = round(pack(objs), 1)
    return rep
