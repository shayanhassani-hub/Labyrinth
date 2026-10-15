"""
Cradle v2 Step 6f: keep the previous UVs after a local geometry change of the generator (cradle_v2.py).
A full cradle_v2.py run re-unwraps and repacks every island; after a small fix (6f: hub-collar corner 0.167 -> 0.164,
8 vertices, the 4 bow-tie ledge quads re-split) only the touched loops should change. Geometry, faces, hard edges and
custom normals come from the new build; UVs and seams from the old file:
  - parts with identical topology and positions: UVs and seams copied unchanged
  - Base: unchanged faces keep their loops. The re-split faces, plus each face with a moved vertex across a cut that
    existed only because the edge was hard and no longer is (6f: the fold's hard edges; the 36 mm2 ledge slivers), form
    "pieces": each becomes its own island, LSCM-unwrapped at its source island's density and orientation, and placed
    in the nearest free sheet space with PAD_PX + 1 clearance (6f: the old flipped triangles were one-face islands
    already, and the ledge strips have no spare padding). Moved vertices of kept islands are solved in place by LSCM
    with every other vertex pinned. Seams = old seams on surviving edges, minus the dissolved soft cuts inside a piece,
    plus the piece borders.
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_uvkeep.py -- <old.blend> <new.blend> <out.blend>
"""
import bpy
import sys
import numpy as np

PX = 2048
PAD_PX, BORDER_PX = 8, 4                 # cradle_v2_uv.PAD_PX / BORDER_PX


def mesh_arrays(me):
    P = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", P)
    U = np.empty(len(me.loops) * 2); me.uv_layers[0].data.foreach_get("uv", U)
    faces = [list(p.vertices) for p in me.polygons]
    floops = [list(p.loop_indices) for p in me.polygons]
    seams = {tuple(sorted(e.vertices)) for e in me.edges if e.use_seam}
    return P.reshape(-1, 3), U.reshape(-1, 2), faces, floops, seams


def sharp_edges(me):
    return {tuple(sorted(e.vertices)) for e in me.edges if e.use_edge_sharp}


def edge_map(faces):
    e2f = {}
    for fi, f in enumerate(faces):
        for k in range(len(f)): e2f.setdefault(tuple(sorted((f[k], f[(k + 1) % len(f)]))), []).append(fi)
    return e2f


def islands(faces, cuts):
    """face -> island id (faces connected through non-cut edges)"""
    e2f = edge_map(faces)
    isl = [-1] * len(faces); n = 0
    for s in range(len(faces)):
        if isl[s] >= 0: continue
        stack = [s]; isl[s] = n
        while stack:
            f = faces[stack.pop()]
            for k in range(len(f)):
                e = tuple(sorted((f[k], f[(k + 1) % len(f)])))
                if e in cuts: continue
                for g in e2f[e]:
                    if isl[g] < 0: isl[g] = n; stack.append(g)
        n += 1
    return isl


def uv_split_edges(faces, floops, U, tol=1e-6):
    """edges whose two faces disagree on the UV of an end vertex (the real UV cuts, seam flag or not)"""
    seen, out = {}, set()
    for f, ls in zip(faces, floops):
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]; e = tuple(sorted((a, b)))
            uvs = {a: U[ls[k]], b: U[ls[(k + 1) % len(f)]]}
            if e in seen:
                if any(np.abs(seen[e][v] - uvs[v]).max() > tol for v in e): out.add(e)
            else: seen[e] = uvs
    return out


def wedges(faces, cuts):
    """corner (face, vertex) -> wedge id: the corners at a vertex joined through its non-cut edges"""
    parent = {}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for fi, f in enumerate(faces):
        for v in f: parent[(fi, v)] = (fi, v)
    for e, fs in edge_map(faces).items():
        if e in cuts or len(fs) != 2: continue
        for v in e: parent[find((fs[0], v))] = find((fs[1], v))
    return {c: find(c) for c in parent}


def lscm_solve(P, tris, known, unknown, mirror=None):
    """complex LSCM: per triangle (w_b - w_a)(z_c - z_a) - (w_c - w_a)(z_b - z_a) = 0, known UVs pinned. P: position
    per key. The island's orientation (mirrored or not) comes from its known triangles unless given."""
    def local(t):
        a, b, c = (np.asarray(P[i], float) for i in t); x = b - a; L = np.linalg.norm(x); x /= L
        n = np.cross(b - a, c - a); A = np.linalg.norm(n) / 2; n /= np.linalg.norm(n); y = np.cross(n, x)
        return np.array([0, L + 0j, complex((c - a) @ x, (c - a) @ y)]), A
    if mirror is None:
        sgn = []
        for t in tris:
            if all(i in known for i in t):
                z, _ = local(t); w = [complex(*known[i]) for i in t]
                sgn.append(np.sign(((w[1] - w[0]).conjugate() * (w[2] - w[0])).imag * ((z[1] - z[0]).conjugate() * (z[2] - z[0])).imag))
        mirror = sum(sgn) < 0
    col = {v: k for k, v in enumerate(sorted(unknown))}
    rows, rhs = [], []
    for t in tris:
        z, A = local(t)
        if mirror: z = z.conjugate()
        coef = {t[0]: -(z[2] - z[0]) + (z[1] - z[0]), t[1]: z[2] - z[0], t[2]: -(z[1] - z[0])}
        r = np.zeros(len(col), complex); b = 0j; s = 1 / np.sqrt(A)
        for v, c in coef.items():
            if v in col: r[col[v]] += c * s
            else: b -= c * s * complex(*known[v])
        rows.append(r); rhs.append(b)
    sol = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0]
    return {v: np.array([sol[k].real, sol[k].imag]) for v, k in col.items()}, mirror


def seg_dist(P, A, B):
    """distance of each point P (n, 2) to each segment A-B (m, 2) -> (n, m)"""
    ab = B - A; t = np.clip(np.einsum("nmk,mk->nm", P[:, None] - A[None], ab) / np.maximum((ab * ab).sum(1), 1e-18), 0, 1)
    return np.linalg.norm(P[:, None] - (A[None] + t[..., None] * ab[None]), axis=2)


def poly_gap(polys_a, polys_b):
    """exact UV gap (px) between two sets of polygons (lists of (k, 2) arrays)"""
    def segs(Q): return np.vstack(Q), np.vstack([np.roll(q, -1, 0) for q in Q])
    A1, B1 = segs(polys_a); A2, B2 = segs(polys_b)
    return PX * min(seg_dist(A1, A2, B2).min(), seg_dist(A2, A1, B1).min())


def raster_occupancy(uv_tris, size=PX):
    """bool (size, size) image: pixels whose centre is inside a UV triangle or that its edges cross (u -> x, v -> y)"""
    occ = np.zeros((size, size), bool)
    for t in uv_tris:
        T = np.asarray(t) * size - 0.5
        x0, y0 = np.floor(T.min(0)).astype(int).clip(0, size - 1); x1, y1 = np.ceil(T.max(0)).astype(int).clip(0, size - 1)
        X, Y = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        a, b, c = T; d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12: occ[Y, X] = True; continue
        l1 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / d
        l2 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / d
        inside = (l1 >= -0.02) & (l2 >= -0.02) & (1 - l1 - l2 >= -0.02)
        occ[Y[inside], X[inside]] = True
        for p, q in ((a, b), (b, c), (c, a)):                 # edges too: sub-pixel slivers cover no pixel centre
            n = int(np.ceil(np.linalg.norm(q - p) * 4)) + 1
            E = np.rint(p + np.linspace(0, 1, n)[:, None] * (q - p)).astype(int).clip(0, size - 1)
            occ[E[:, 1], E[:, 0]] = True
    return occ


def dilate(m, n):
    """square (Chebyshev) growth by n px, as the padding check in cradle_v2_check.uv grows its islands"""
    m = m.copy()
    for _ in range(n):
        g = m.copy(); g[1:] |= m[:-1]; g[:-1] |= m[1:]; m = g
        g = m.copy(); g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]; m = g
    return m


def place(piece_tris, occ, near, clear_px, border_px):
    """translation (UV) that puts a piece (UV triangles) into free sheet space, its raster clear_px + 1 from every
    occupied pixel and border_px + 1 from the sheet edge; candidates on square rings around `near` (UV), nearest first"""
    size = occ.shape[0]
    s0 = 0.5 - np.mean([np.asarray(t) for t in piece_tris], axis=(0, 1))     # rasterize at the sheet centre (no clipping)
    ys, xs = np.nonzero(raster_occupancy([np.asarray(t) + s0 for t in piece_tris], size))
    blocked = dilate(occ, clear_px + 1); b = border_px + 1
    blocked[:b] = True; blocked[-b:] = True; blocked[:, :b] = True; blocked[:, -b:] = True
    cy, cx = int(round(ys.mean())), int(round(xs.mean())); ny, nx = int(near[1] * size), int(near[0] * size)
    for r in range(0, size, 2):
        if r == 0: cand = [(ny, nx)]
        else:
            cand = [(ny + dy, nx + dx) for dy in range(-r, r + 1, 2) for dx in (-r, r)]
            cand += [(ny + dy, nx + dx) for dy in (-r, r) for dx in range(-r + 2, r - 1, 2)]
        cand.sort(key=lambda p: (p[0] - ny) ** 2 + (p[1] - nx) ** 2)
        for py, px in cand:
            Y, X = ys + py - cy, xs + px - cx
            if Y.min() < 0 or X.min() < 0 or Y.max() >= size or X.max() >= size: continue
            if not blocked[Y, X].any(): return s0 + np.array([px - cx, py - cy]) / size
    raise RuntimeError("no free sheet space for a piece")


def keep_base(me_new, me_old, sheet_tris):
    """sheet_tris: UV triangles of the other unique meshes on the same texture sheet (occupied space)"""
    Pn, _, fn, ln, _ = mesh_arrays(me_new)
    Po, Uo, fo, lo, so = mesh_arrays(me_old)
    assert len(fn) == len(fo) and len(Pn) == len(Po)
    moved = set(np.flatnonzero(np.linalg.norm(Pn - Po, axis=1) > 1e-7).tolist())
    changed = [fi for fi in range(len(fn)) if fn[fi] != fo[fi]]
    split = uv_split_edges(fo, lo, Uo)
    cut_old = so | split
    iso = islands(fo, cut_old)
    e2f = edge_map(fn); edges_new = set(e2f)
    # soft cuts: hard before, not now (the fold); slivers = faces with a moved vertex across one from a re-split face
    soft = (sharp_edges(me_old) - sharp_edges(me_new)) & edges_new
    extra = sorted({g for e in soft for g in e2f[e] if g not in changed and moved & set(fn[g]) and any(h in changed for h in e2f[e])})
    regroup = set(changed) | set(extra)
    inner = {e for e, fs in e2f.items() if len(fs) == 2 and all(g in regroup for g in fs) and (e not in cut_old or e in soft)}
    isl = list(iso); nid = max(iso) + 1; pieces = []; seen = set()
    for s0 in sorted(regroup):
        if s0 in seen: continue
        stack, comp = [s0], [s0]; isl[s0] = nid; seen.add(s0)
        while stack:
            f = fn[stack.pop()]
            for k in range(len(f)):
                e = tuple(sorted((f[k], f[(k + 1) % len(f)])))
                if e not in inner: continue
                for g in e2f[e]:
                    if g not in seen: isl[g] = nid; seen.add(g); stack.append(g); comp.append(g)
        pieces.append((nid, sorted(comp), iso[s0])); nid += 1
    cut = ({e for e in cut_old if e in edges_new} - inner)
    added = {e for e, fs in e2f.items() if len(fs) == 2 and isl[fs[0]] != isl[fs[1]] and e not in cut}
    cut |= added
    chk = islands(fn, cut)
    for i in set(chk):
        assert len({isl[fi] for fi in range(len(fn)) if chk[fi] == i}) == 1, f"new island {i} mixes island ids"
    # corners -> wedges; known UV per wedge from the kept faces at unmoved vertices
    W = wedges(fn, cut); known = {}
    for fi in range(len(fn)):
        if fi in regroup: continue
        for k, v in enumerate(fn[fi]):
            if v in moved: continue
            w = W[(fi, v)]; u = Uo[lo[fi][k]]
            if w in known: assert np.abs(known[w] - u).max() < 1e-6, f"wedge {w} has two UVs"
            else: known[w] = u
    unknown = {W[(fi, v)] for fi in range(len(fn)) for v in fn[fi]} - set(known)
    old_uv = {}
    for fi in range(len(fn)):
        if fi in regroup: continue
        for k, v in enumerate(fn[fi]):
            if W[(fi, v)] in unknown: old_uv.setdefault(W[(fi, v)], Uo[lo[fi][k]])

    def tris_of(F): return [tuple(W[(fi, fn[fi][j])] for j in (0, k, k + 1)) for fi in F for k in range(1, len(fn[fi]) - 1)]
    def pos_of(F): return {W[(fi, v)]: Pn[v] for fi in F for v in fn[fi]}
    solved, rep = {}, []
    # kept islands with moved vertices: LSCM with every other vertex pinned
    for I in sorted({isl[fi] for fi in range(len(fn)) if fi not in regroup and any(W[(fi, v)] in unknown for v in fn[fi])}):
        F = [fi for fi in range(len(fn)) if isl[fi] == I and any(W[(fi, v)] in unknown for v in fn[fi])]
        T = tris_of(F); kn = {w: known[w] for t in T for w in t if w in known}
        sol, mirror = lscm_solve(pos_of(F), T, kn, {w for t in T for w in t if w in unknown})
        for w, u in sol.items():
            solved[w] = u; rep.append((I, w[1], float(np.linalg.norm(u - old_uv[w]) * PX), mirror))
    # pieces: free LSCM (two pins on the longest edge, source island density and orientation), placed in free space
    occ_tris = list(sheet_tris)
    for fi in range(len(fn)):
        if fi in regroup: continue
        Uf = [solved[W[(fi, v)]] if W[(fi, v)] in solved else known[W[(fi, v)]] for v in fn[fi]]
        occ_tris += [(Uf[0], Uf[k], Uf[k + 1]) for k in range(1, len(Uf) - 1)]
    occ = raster_occupancy(occ_tris)
    placed = []
    for I, F, src in pieces:
        S = [fi for fi in range(len(fo)) if iso[fi] == src and fi not in regroup] or [fi for fi in F if fn[fi] == fo[fi]]
        a3 = a2 = 0.0; wind = 0.0
        for fi in S:
            f, l_ = fo[fi], lo[fi]
            for k in range(1, len(f) - 1):
                n3 = np.cross(Po[f[k]] - Po[f[0]], Po[f[k + 1]] - Po[f[0]]); a3 += np.linalg.norm(n3) / 2
                c2 = np.cross(Uo[l_[k]] - Uo[l_[0]], Uo[l_[k + 1]] - Uo[l_[0]]); a2 += abs(c2) / 2; wind += c2
        dens = np.sqrt(a2 / a3); mirror = wind < 0                     # UV winding against the face winding
        T = tris_of(F); P_ = pos_of(F)
        ea, eb = max(((t[i], t[(i + 1) % 3]) for t in T for i in range(3)), key=lambda ab: np.linalg.norm(P_[ab[0]] - P_[ab[1]]))
        kn = {ea: np.zeros(2), eb: np.array([np.linalg.norm(P_[ea] - P_[eb]) * dens, 0.0])}
        sol, _ = lscm_solve(P_, T, kn, {w for t in T for w in t} - set(kn), mirror=mirror); sol.update(kn)
        ptris = [tuple(sol[w] for w in t) for t in T]
        near = np.mean([Uo[l_] for fi in F for l_ in lo[fi]], axis=0)        # where the old faces were
        d = place(ptris, occ, near, PAD_PX + 3, BORDER_PX)          # +3: raster quantisation (exact gap checked below)
        sol = {w: u + d for w, u in sol.items()}; solved.update(sol)
        occ |= raster_occupancy([tuple(sol[w] for w in t) for t in T])
        c = np.mean(list(sol.values()), 0)
        placed.append((I, F, round(float(dens * PX), 1), np.round(c * PX, 1).tolist(), round(float(np.linalg.norm(c - near) * PX), 1)))
    Un = np.empty((len(me_new.loops), 2)); nchg = 0
    for fi in range(len(fn)):
        for k, v in enumerate(fn[fi]):
            w = W[(fi, v)]
            if w in solved: Un[ln[fi][k]] = solved[w]; nchg += 1
            else: Un[ln[fi][k]] = known[w]
    me_new.uv_layers[0].data.foreach_set("uv", Un.ravel())
    seams_out = ({e for e in so if e in edges_new} - inner) | added
    for e in me_new.edges: e.use_seam = tuple(sorted(e.vertices)) in seams_out
    # exact gap of every touched island to all other islands and parts nearby (the raster check needs ~PAD_PX + 1)
    gaps = []
    for I in sorted({r[0] for r in rep} | {p[0] for p in placed}):
        A = [Un[ln[fi]] for fi in range(len(fn)) if isl[fi] == I]
        lo_, hi_ = np.vstack(A).min(0) - 0.03, np.vstack(A).max(0) + 0.03
        B = [Un[ln[fi]] for fi in range(len(fn)) if isl[fi] != I] + [np.asarray(t) for t in sheet_tris]
        B = [q for q in B if (q.max(0) >= lo_).all() and (q.min(0) <= hi_).all()]
        gaps.append((I, round(poly_gap(A, B), 2) if B else 99.0))
    return dict(moved_verts=sorted(moved), changed_faces=changed, regrouped=extra, loops_changed=nchg,
                uv_cuts_not_seams=len(split - so), pieces=placed, gaps=gaps, seams_removed=sorted(so - seams_out),
                seams_added=sorted(added), solved=sorted(rep, key=lambda r: r[1]))


def main():
    old_fn, new_fn, out_fn = sys.argv[sys.argv.index("--") + 1:][:3]
    bpy.ops.wm.open_mainfile(filepath=new_fn)
    with bpy.data.libraries.load(old_fn, link=False) as (s, d):
        d.meshes = [n for n in s.meshes if n.startswith("LAB_HERO_Cradle_")]
    old = {m.name.rsplit(".", 1)[0]: m for m in d.meshes}
    mine = sorted({o.data for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith("LAB_HERO_Cradle_")}, key=lambda m: m.name)
    todo = []
    for me in mine:
        mo = old[me.name]
        Pn, _, fn, _, _ = mesh_arrays(me); Po, Uo, fo, _, so = mesh_arrays(mo)
        if fn == fo and np.allclose(Pn, Po, atol=1e-7):
            me.uv_layers[0].data.foreach_set("uv", Uo.ravel())
            for e in me.edges: e.use_seam = tuple(sorted(e.vertices)) in so
            print(f"KEEP {me.name}: UVs and seams copied unchanged ({len(Uo)} loops)")
        else:
            todo.append((me, mo))
    for me, mo in todo:
        sheet = []                                   # occupied sheet space: the other unique meshes (Arm_L = Arm_R's UVs)
        for m in mine:
            if m is me or m.name.endswith("Arm_L_01"): continue
            _, U, _, fl, _ = mesh_arrays(m)
            sheet += [(U[l_[0]], U[l_[k]], U[l_[k + 1]]) for l_ in fl for k in range(1, len(l_) - 1)]
        r = keep_base(me, mo, sheet)
        print(f"KEEP {me.name}: moved verts {r['moved_verts']}, re-split faces {r['changed_faces']}, slivers {r['regrouped']}, "
              f"loops with new UVs {r['loops_changed']}")
        print(f"     seams removed {r['seams_removed']}, added {len(r['seams_added'])} (UV cuts without seam flag in the old mesh: {r['uv_cuts_not_seams']})")
        for I, F, dens, c, dist in r["pieces"]:
            print(f"     piece island {I}: faces {F}, {dens} px/m, centre {c} px, {dist} px from the old faces")
        for I, v, px, mir in r["solved"]:
            print(f"     solved in place: island {I} vert {v} moved {px:.2f} px" + (" (mirrored island)" if mir else ""))
        bad = [g for g in r["gaps"] if g[1] < PAD_PX + 1]
        print(f"{'PASS' if not bad else 'FAIL'} exact gap of the touched islands >= {PAD_PX + 1} px: min {min(g for _, g in r['gaps'])} px" + (f" {bad}" if bad else ""))
    for m in d.meshes: bpy.data.meshes.remove(m)
    bpy.ops.wm.save_as_mainfile(filepath=out_fn, compress=True)
    print("SAVED", out_fn)


if __name__ == "__main__":
    main()
