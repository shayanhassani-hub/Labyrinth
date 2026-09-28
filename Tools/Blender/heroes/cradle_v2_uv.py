"""
Cradle v2 low-poly: hard edges, UV seams, unwrap and packing (ASSET_RULES hero standard, Step 4).
Used by cradle_v2.build(). Works on Blender meshes (Blender axes: z = spec y = up).

Hard edges: an edge is hard (and a seam) where its faces meet at >= SHARP_DEG, except chamfer borders
  (<= CHAMFER_MAX_DEG next to a narrow face), which stay smooth so the chamfer gives the highlight.
  Nothing else is hard: no angle-only sharps below SHARP_DEG.
Seams: hard edges, open borders, and cuts:
  - closed rings (islands with two border loops) are cut radially into arcs of <= ARC_LEN;
  - islands the unwrap cannot flatten within the stretch limits are split at their chamfer borders.
Unwrap: planar islands = exact planar projection (no distortion); curved islands = angle based, then
  straightened with follow-active-quads where they are all quads and it stays within the limits.
Orientation: each island's minimum-area rectangle is turned so its long side runs along U (bands and
  strips horizontal, arms along their length); world up points to +V (or +U when up runs along the
  long side). Packing keeps that orientation (no rotation).
"""
import bpy
import bmesh
import math
import numpy as np
from mathutils import Vector
from heapq import heappush, heappop

SHARP_DEG = 40.0
CHAMFER_MAX_DEG = 55.0
NARROW = 0.025                 # face "width" (area / longest edge) below this = chamfer strip
PLANAR_DEG = 2.0
ARC_LEN = 0.9                  # max arc length of a round ring piece (m)
CORNER_DEG = 30.0              # ring outline turns >= this are corners: rings are cut there (one piece per side)
STRETCH_MAX = 1.20             # per-island face area ratio limits (max / median, median / min)
ANGLE_MAX = 12.0               # per-island max corner angle deviation (deg), faces > 2 cm2
FILL_MIN = 0.6                # islands filling less of their min-area rectangle are cut in two
SPLIT_MIN_LEN = 0.20           # ... when their long side exceeds this (m)
ROUNDS = 14                    # unwrap / split rounds
TEX = 2048
PAD_PX, BORDER_PX = 16, 8


def face_width(f):
    lmax = max(e.calc_length() for e in f.edges)
    return f.calc_area() / lmax if lmax > 0 else 0.0


def is_chamfer_border(e):
    if len(e.link_faces) != 2: return False
    f1, f2 = e.link_faces
    ang = math.degrees(e.calc_face_angle(0.0))
    return 1.0 < ang <= CHAMFER_MAX_DEG and ((face_width(f1) < NARROW) != (face_width(f2) < NARROW))


def mark_edges(me):
    """hard edges + base seams (in place). Returns number of hard edges."""
    bm = bmesh.new(); bm.from_mesh(me); n = 0
    for e in bm.edges:
        e.smooth = True; e.seam = False
        if len(e.link_faces) != 2:
            e.seam = True; continue
        if math.degrees(e.calc_face_angle(0.0)) >= SHARP_DEG and not is_chamfer_border(e):
            e.smooth = False; e.seam = True; n += 1
    bm.to_mesh(me); bm.free()
    return n


def islands(bm):
    seen = set(); out = []
    for f in bm.faces:
        if f.index in seen: continue
        stack = [f]; seen.add(f.index); isl = []
        while stack:
            g = stack.pop(); isl.append(g)
            for e in g.edges:
                if e.seam: continue
                for h in e.link_faces:
                    if h.index not in seen: seen.add(h.index); stack.append(h)
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


def _path(isl, src, dst):
    """shortest inner-edge path from vertex set src to vertex set dst; list of edges"""
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
            w = e.other_vert(v); nd = d + e.calc_length()
            if nd < dist.get(w, 1e9): dist[w] = nd; prev[w] = (v, e); heappush(heap, (nd, w.index, w))
    return None


def cut_rings(me):
    """islands with 2+ border loops: radial cuts. Two loops -> ceil(outer length / ARC_LEN) cuts (>= 1),
    evenly spaced in angle about the ring axis; more loops -> connect them with single paths.
    Returns number of cuts."""
    cuts = 0
    for _ in range(60):
        bm = bmesh.new(); bm.from_mesh(me)
        changed = False
        for isl in islands(bm):
            loops = border_loops(isl)
            if len(loops) < 2: continue
            lens = [sum(e.calc_length() for e in L) for L in loops]
            order = np.argsort(lens)
            inner, outer = loops[order[0]], loops[order[-1]]
            if len(loops) == 2:
                P = np.array([v.co[:] for e in outer for v in e.verts])
                c = P.mean(0); w, vec = np.linalg.eigh((P - c).T @ (P - c)); ax = vec[:, 0]
                a1 = vec[:, 2]; a2 = np.cross(ax, a1)
                ang = lambda v: math.atan2(np.dot(np.array(v.co[:]) - c, a2), np.dot(np.array(v.co[:]) - c, a1))
                ivs = list({v for e in inner for v in e.verts}); ovs = {v for e in outer for v in e.verts}
                oset = set(outer)

                def turn(v):                                # direction change of the outer loop at v (deg)
                    es = [e for e in v.link_edges if e in oset]
                    if len(es) != 2: return 0.0
                    d1 = (es[0].other_vert(v).co - v.co).normalized(); d2 = (es[1].other_vert(v).co - v.co).normalized()
                    return 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, d1.dot(d2)))))
                corners = [v for v in ovs if turn(v) >= CORNER_DEG]
                # a chamfer strip between two sides stays with one of them: cut on one of its corners only
                claimed = set(); keep = []
                for v in sorted(corners, key=lambda v: ang(v)):
                    fs_ = {f for e in v.link_edges if e in oset for f in e.link_faces if f in set(isl)}
                    narrow = [f for f in fs_ if face_width(f) < NARROW]
                    if narrow and any(f in claimed for f in narrow): continue
                    claimed.update(narrow); keep.append(v)
                corners = keep
                if len(corners) >= 3:
                    starts = corners                        # octagon rings: one piece per side
                else:
                    n = max(1, math.ceil(lens[order[-1]] / ARC_LEN))
                    v0 = max(ovs, key=turn); a0 = ang(v0)
                    starts = [min(ovs, key=lambda v: abs((ang(v) - (a0 + 2 * math.pi * k / n) + math.pi) % (2 * math.pi) - math.pi))
                              for k in range(n)]
                for o in starts:
                    p = _path(isl, {o}, set(ivs))
                    if p:
                        for e in p: e.seam = True
                        cuts += 1
            else:
                src = {v for e in loops[0] for v in e.verts}
                dst = {v for L in loops[1:] for e in L for v in e.verts}
                p = _path(isl, src, dst)
                if p:
                    for e in p: e.seam = True
                    cuts += 1
            changed = True
            break
        bm.to_mesh(me); bm.free()
        if not changed: break
    return cuts


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


def island_quality(isl, uvl):
    """(area ratio max/median, median/min, max angle deviation) over faces > 2 cm2"""
    r = []; ang = []
    for f in isl:
        a3 = f.calc_area()
        if a3 < 2e-4: continue
        U = [np.array(l[uvl].uv[:]) for l in f.loops]; P = [np.array(l.vert.co[:]) for l in f.loops]
        r.append(abs(_poly_area(U)) / a3)
        ang.append(np.abs(_corner_angles(P) - _corner_angles(U)).max())
    if not r: return 1.0, 1.0, 0.0
    r = np.array(r); m = np.median(r)
    return r.max() / m, m / max(r.min(), 1e-12), max(ang)


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


def split_chamfers(isl):
    """seam the chamfer borders of a badly flattened island (the side towards the smaller wide face)"""
    n = 0
    for f in isl:
        if face_width(f) >= NARROW: continue
        bs = [e for e in f.edges if is_chamfer_border(e) and not e.seam]
        if not bs: continue
        e = min(bs, key=lambda e: next(g for g in e.link_faces if g is not f).calc_area())
        e.seam = True; n += 1
    if n == 0:                                     # no chamfers: cut the strongest smooth folds
        es = sorted({e for f in isl for e in f.edges if not e.seam and len(e.link_faces) == 2},
                    key=lambda e: -e.calc_face_angle(0.0))
        for e in es[:max(1, len(es) // 8)]:
            if e.calc_face_angle(0.0) > math.radians(10): e.seam = True; n += 1
    return n


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


def unwrap_object(o):
    """unwrap one object in edit mode on its seams; returns stats"""
    view = bpy.context.view_layer
    for x in view.objects: x.select_set(False)
    o.select_set(True); view.objects.active = o
    stats = dict(split_rounds=0, straightened=0, planar=0, curved=0)
    for rnd in range(ROUNDS):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=False, margin=0.001)
        bm = bmesh.from_edit_mesh(o.data); uvl = bm.loops.layers.uv.active
        bm.faces.ensure_lookup_table()
        isls = islands(bm)
        quads = []
        for isl in isls:
            pl, n = is_planar(isl)
            if pl: planar_project(isl, uvl, n)
            elif len(isl) > 1 and all(len(f.verts) == 4 for f in isl): quads.append(isl)
        bmesh.update_edit_mesh(o.data)
        straightened = 0
        for isl in quads:
            idx = [f.index for f in isl]
            bm = bmesh.from_edit_mesh(o.data); uvl = bm.loops.layers.uv.active; bm.faces.ensure_lookup_table()
            isl = [bm.faces[i] for i in idx]
            before = {(f.index, k): l[uvl].uv.copy() for f in isl for k, l in enumerate(f.loops)}
            q0 = island_quality(isl, uvl)
            for f in bm.faces: f.select = False
            for f in isl: f.select = True
            act = max(isl, key=lambda f: f.calc_area()); bm.faces.active = act
            ls = list(act.loops); a = ls[0].edge.calc_length(); b = ls[1].edge.calc_length(); p0 = ls[0][uvl].uv.copy()
            ls[1][uvl].uv = p0 + Vector((a, 0)); ls[2][uvl].uv = p0 + Vector((a, b)); ls[3][uvl].uv = p0 + Vector((0, b))
            bmesh.update_edit_mesh(o.data)
            try:
                bpy.ops.uv.follow_active_quads(mode='LENGTH_AVERAGE')
                ok = True
            except RuntimeError:
                ok = False
            bm = bmesh.from_edit_mesh(o.data); uvl = bm.loops.layers.uv.active; bm.faces.ensure_lookup_table()
            isl = [bm.faces[i] for i in idx]
            q1 = island_quality(isl, uvl) if ok else (9, 9, 90)
            if ok and q1[0] <= STRETCH_MAX and q1[1] <= STRETCH_MAX and q1[2] <= ANGLE_MAX:
                straightened += 1
            else:
                for f in isl:
                    for k, l in enumerate(f.loops): l[uvl].uv = before[(f.index, k)]
            bmesh.update_edit_mesh(o.data)
        # quality: split what could not be flattened within the limits
        bm = bmesh.from_edit_mesh(o.data); uvl = bm.loops.layers.uv.active
        isls = islands(bm); bad = 0
        for isl in isls:
            q = island_quality(isl, uvl)
            if q[0] > STRETCH_MAX or q[1] > STRETCH_MAX or q[2] > ANGLE_MAX:
                bad += split_chamfers(isl) > 0
            else:
                fill, long_m = island_fill(isl, uvl)
                if len(isl) > 1 and (self_overlap(isl, uvl) or (fill < FILL_MIN and long_m > SPLIT_MIN_LEN)):
                    bad += split_median(isl, uvl) > 0
                    stats["fill_splits"] = stats.get("fill_splits", 0) + 1
        bmesh.update_edit_mesh(o.data)
        stats.update(straightened=straightened, islands=len(isls))
        if bad == 0 or rnd == ROUNDS - 1:
            break
        stats["split_rounds"] = rnd + 1
    bm = bmesh.from_edit_mesh(o.data); uvl = bm.loops.layers.uv.active
    for isl in islands(bm):
        orient(isl, uvl)
        if is_planar(isl)[0]: stats["planar"] += 1
        else: stats["curved"] += 1
    bmesh.update_edit_mesh(o.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    return stats


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


def _skyline(rects, W, H):
    """bottom-left skyline packing of integer rects [(w, h)] (no rotation) into W x H.
    Returns positions [(x, y)] or None if they do not fit."""
    sky = [[0, W, 0]]                                  # segments [x, width, y]
    pos = [None] * len(rects)
    order = sorted(range(len(rects)), key=lambda i: (-rects[i][1], -rects[i][0]))
    for i in order:
        w, h = rects[i]
        if w > W: return None
        best = None
        for s in range(len(sky)):
            x = sky[s][0]
            if x + w > W: break
            y = 0; j = s
            while j < len(sky) and sky[j][0] < x + w:
                y = max(y, sky[j][2]); j += 1
            if y + h > H: continue
            key = (y + h, x)
            if best is None or key < best[0]: best = (key, x, y)
        if best is None: return None
        _, x, y = best
        pos[i] = (x, y)
        # update the skyline: replace [x, x+w) with height y+h
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
    """pack all islands of objs into one TEX x TEX sheet without rotation, one texel density for all
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
    lo, hi = 50.0, 2000.0; best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        p = _skyline(rects(mid), TEX, TEX)
        if p: lo, best = mid, (mid, p)
        else: hi = mid
        if hi - lo < 0.25: break
    d, pos = best
    for (uvl, isl, mn, sz), (x, y) in zip(isls, pos):
        ox = (x + PAD_PX // 2 + 0.5) / TEX; oy = (y + PAD_PX // 2 + 0.5) / TEX
        for f in isl:
            for l in f.loops:
                u, v = l[uvl].uv
                l[uvl].uv = (ox + (u - mn[0]) * d / TEX, oy + (v - mn[1]) * d / TEX)
    for o, bm, uvl in bms:
        bm.to_mesh(o.data); bm.free()
    return d


def unwrap_and_pack(objs, dens_fn=None):
    """objs: objects whose UVs share one 0-1 space (each mesh once)."""
    rep = {}
    for o in objs:
        me = o.data
        if not me.uv_layers: me.uv_layers.new(name="UVMap")
        hard = mark_edges(me); cuts = cut_rings(me)
        st = unwrap_object(o)
        st.update(hard_edges=hard, ring_cuts=cuts)
        scale_islands(o, (lambda isl, o=o: dens_fn(o, isl)) if dens_fn else None)
        rep[o.name] = st
    rep["px_per_m"] = round(pack(objs), 1)
    return rep
