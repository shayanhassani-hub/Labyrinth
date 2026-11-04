"""
ServiceArm (Hero 01b): validation, clearance sweeps and review renders (HERO_SPEC §4, ASSET_RULES hero standard,
workflow v3).
  blender -b -P Tools/Blender/heroes/servicearm_check.py -- <stage> [args]
stages:
  topo        tris and topology per part, bow-tie / concave quads, winding against the custom normals, planarity
              report, flat-face shading, UV islands, texel density, padding (Temp/claude/servicearm/topo.json)
  clearance   HERO_SPEC §4 3D rule against the docked drone (rebuilt from drone_low.fbx + DroneBaseline, as
              Proposals/ServiceArm_S4_Proposal.md): >= 100 mm from the four spinning-disc volumes, >= 50 mm from the
              drone mesh, nothing below y 2.00 inside a disc footprint -- over the working pose, the idle motion
              (turret +-10, wrist +-15, tool roll 0..360), the whole fold path from every idle extreme and the stowed
              pose; part-against-part gaps over the same set; stowed layer y 3.77 ... 3.95; released drone volume;
              ceiling; reach 1.60 needed / 1.90 available
  renders     review renders (h0 / h1): working pose over the docked drone, stowed, 3/4, concept-camera matches side
              by side with the concept (servicearm_<stage>_vs_concept*.jpg)
  shading     flat grey renders of the untextured low (normals check)
Everything opens a saved review file (servicearm.SAVE, or SAVE_H0 with "h0") and never saves it.
"""
import bpy
import bmesh
import json
import math
import os
import sys
import time
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import servicearm as S                                    # noqa: E402
import servicearm_kin as K                                # noqa: E402
import cradle_v2_check as CC                              # noqa: E402  quad_faults, blend_winding, add_wire, checker

PROJ = K.PROJ
SCR = os.path.join(PROJ, "Temp", "claude", "servicearm")
RENDERS = os.path.join(PROJ, "Renders")
MEDIA = os.path.join(PROJ, "Documentation", "Media", "servicearm")
REF = os.path.join(PROJ, "Documentation", "References", "ServiceArm")
CONCEPT_SIDE = os.path.join(REF, "servicearm_ortho_side.jpg")
CONCEPT_FRONT = os.path.join(REF, "servicearm_front.jpg")
TEX = 1024                                               # H1b: one 1024 sheet
TWIST_MAX = 0.002
FLAT_TOL = 0.5


def open_file(h0=False):
    bpy.ops.wm.open_mainfile(filepath=S.SAVE_H0 if h0 else S.SAVE)
    return {n: bpy.data.objects[f"{S.HERO}_{n}_01"] for n in K.PARTS}


# --------------------------------------------------------------------------- geometry in spec world


def local_arrays(o):
    """part-local (spec) vertices and triangles of an object"""
    me = o.data; me.calc_loop_triangles()
    v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", v); v = v.reshape(-1, 3)
    v = v @ S.C3                                          # Blender -> spec: C3.T @ b (C3 orthogonal)
    t = np.empty(len(me.loop_triangles) * 3, np.int32); me.loop_triangles.foreach_get("vertices", t)
    return v, t.reshape(-1, 3)[:, ::-1].copy()


def surface_samples(v, t, spacing=0.005):
    """vertices + points on every triangle (barycentric grid at ~spacing)"""
    pts = [v]
    A, B, C = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    L = np.maximum(np.maximum(np.linalg.norm(B - A, axis=1), np.linalg.norm(C - A, axis=1)), np.linalg.norm(C - B, axis=1))
    for m in np.unique(np.clip(np.ceil(L / spacing).astype(int), 1, 40)):
        sel = np.ceil(L / spacing).clip(1, 40).astype(int) == m
        if m < 2: pts.append((A[sel] + B[sel] + C[sel]) / 3); continue
        ws = [(i / m, j / m) for i in range(m + 1) for j in range(m + 1 - i)]
        for a, b in ws:
            pts.append(A[sel] + (B[sel] - A[sel]) * a + (C[sel] - A[sel]) * b)
    return np.vstack(pts)


class Arm:
    """the six parts as spec-local arrays; world copies per pose"""

    def __init__(self, objs, spacing=0.005):
        self.loc = {n: local_arrays(o) for n, o in objs.items()}
        self.smp = {n: surface_samples(*self.loc[n], spacing) for n in objs}

    def world(self, pose):
        W = K.fk(pose); out = {}
        for n, (v, t) in self.loc.items():
            M = W[n]; out[n] = (v @ M[:3, :3].T + M[:3, 3], t)
        return out

    def world_samples(self, pose, names=None):
        W = K.fk(pose); out = {}
        for n in (names or self.smp):
            M = W[n]; out[n] = self.smp[n] @ M[:3, :3].T + M[:3, 3]
        return out


def bvh(v, t):
    return BVHTree.FromPolygons(np.asarray(v).tolist(), np.asarray(t).tolist(), all_triangles=True)


def nearest(tree, P):
    best = (1e9, None)
    for p in P:
        h = tree.find_nearest(Vector(p))
        if h[0] is not None and h[3] < best[0]: best = (h[3], p)
    return best


# --------------------------------------------------------------------------- topology, UVs (as gate_check)


def uv_islands(me):
    uv = me.uv_layers.active.data
    parent = list(range(len(me.polygons)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    key = {}
    for p in me.polygons:
        for li in p.loop_indices:
            k = (me.loops[li].vertex_index, round(uv[li].uv[0], 6), round(uv[li].uv[1], 6))
            if k in key: parent[find(p.index)] = find(key[k])
            else: key[k] = p.index
    return [find(p.index) for p in me.polygons]


def raster_labels(objs):
    lab = np.zeros((TEX, TEX), np.int32); gid = 0
    for name, o in objs.items():
        me = o.data; me.calc_loop_triangles(); uv = me.uv_layers.active.data
        isl = uv_islands(me); ids = {}
        for r in sorted(set(isl)):
            gid += 1; ids[r] = gid
        for t in me.loop_triangles:
            P = np.array([uv[l].uv[:] for l in t.loops]) * TEX
            x0, y0 = np.floor(P.min(0)).astype(int); x1, y1 = np.ceil(P.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, TEX - 1), min(y1, TEX - 1)
            if x1 < x0 or y1 < y0: continue
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]; px = xs + 0.5; py = ys + 0.5
            (ax, ay), (bx, by), (cx, cy) = P
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12: continue
            w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
            w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (1 - w0 - w1 >= -1e-6)
            lab[ys[m], xs[m]] = ids[isl[t.polygon_index]]
    return lab


def padding(lab, gap_px=4):
    close = None
    for dy in range(-gap_px + 1, gap_px):
        for dx in range(-gap_px + 1, gap_px):
            if dx == 0 and dy == 0: continue
            a = lab[max(0, dy):TEX + min(0, dy), max(0, dx):TEX + min(0, dx)]
            b = lab[max(0, -dy):TEX + min(0, -dy), max(0, -dx):TEX + min(0, -dx)]
            if np.any((a > 0) & (b > 0) & (a != b)):
                d = max(abs(dx), abs(dy)) - 1
                close = d if close is None else min(close, d)
    ys, xs = np.nonzero(lab)
    border = int(min(xs.min(), ys.min(), TEX - 1 - xs.max(), TEX - 1 - ys.max()))
    return close, border


def flat_normals(me):
    kind = me.attributes["kind"].data
    N = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get("vector", N); N = N.reshape(-1, 3)
    bent, worst = 0, 0.0
    for p in me.polygons:
        if kind[p.index].value != S.FLAT: continue
        fn = np.array(p.normal)
        d = max(math.degrees(math.acos(max(-1.0, min(1.0, float(N[li] @ fn))))) for li in p.loop_indices)
        worst = max(worst, d); bent += d > FLAT_TOL
    return bent, worst


def topo(args):
    objs = open_file(); out = {}; total = 0; ok_all = True
    for name, o in objs.items():
        me = o.data; bm = bmesh.new(); bm.from_mesh(me)
        q = sum(1 for f in bm.faces if len(f.verts) == 4); tr = sum(1 for f in bm.faces if len(f.verts) == 3)
        ng = sum(1 for f in bm.faces if len(f.verts) > 4)
        border = sum(1 for e in bm.edges if e.is_boundary)
        nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        loose = sum(1 for v in bm.verts if not v.link_faces) + sum(1 for e in bm.edges if not e.link_faces)
        zero = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
        dup = len(bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=1e-5)["targetmap"])
        inconsistent = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
        bm.free()
        me.calc_loop_triangles(); tris = len(me.loop_triangles); total += tris
        bow, conc = CC.quad_faults(me)
        wcount, _ = CC.blend_winding(o)
        twist = []
        for p in me.polygons:
            if len(p.vertices) != 4: continue
            P = [np.array(me.vertices[v].co) for v in p.vertices]
            n = np.cross(P[2] - P[0], P[3] - P[1]); ln = np.linalg.norm(n)
            if ln > 1e-12 and abs((P[1] - P[0]) @ (n / ln)) > TWIST_MAX: twist.append(p.index)
        ok = ng == 0 and nonman == 0 and loose == 0 and zero == 0 and dup == 0 and inconsistent == 0
        ok2 = not bow and not conc and not any(wcount.values())
        bent, worst = flat_normals(me)
        ok_all &= ok and ok2 and bent == 0
        out[name] = dict(tris=tris, quads=q, tri_faces=tr, ngons=ng, open_border=border, nonmanifold=nonman, loose=loose,
                         zero_area=zero, duplicates=dup, winding_inconsistent=inconsistent, bowtie=len(bow),
                         concave=len(conc), twisted_quads=len(twist), flat_faces_bent=bent,
                         flat_bend_max_deg=round(worst, 2), **wcount)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {tris} tris ({q} quads, {tr} tris, {ng} n-gons), open border {border}, "
              f"non-manifold {nonman}, loose {loose}, dup {dup}, zero-area {zero}, winding {inconsistent}")
        print(f"{'PASS' if ok2 else 'FAIL'} {name} folds: bow-tie {len(bow)}, concave {len(conc)}, against custom normals "
              f"{wcount['vs_custom']}, folded pairs {wcount['folded_pairs']}, same-direction edges {wcount['same_direction_edges']}")
        print(f"INFO planarity {name}: {len(twist)} quads with diagonals > {TWIST_MAX * 1e3:.0f} mm apart")
        print(f"{'PASS' if bent == 0 else 'FAIL'} {name} shading: {bent} flat faces with a corner normal > "
              f"{FLAT_TOL} deg off the face normal (worst {worst:.2f} deg)")
    print(f"INFO total {total} tris")
    lab = raster_labels(objs)
    per = {}
    for name, o in objs.items():
        me = o.data; uv = me.uv_layers.active.data; isl = uv_islands(me); acc = {}
        for p in me.polygons:
            U = np.array([uv[l].uv[:] for l in p.loop_indices]); x, y = U[:, 0], U[:, 1]
            au = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            a = acc.setdefault(isl[p.index], [0.0, 0.0]); a[0] += p.area; a[1] += au
        d = [TEX * math.sqrt(v[1] / v[0]) for v in acc.values() if v[0] > 1e-6]
        a3 = sum(v[0] for v in acc.values()); a2 = sum(v[1] for v in acc.values())
        per[name] = dict(islands=len(acc), mean=round(TEX * math.sqrt(a2 / a3), 1), min=round(min(d)),
                         median=round(float(np.median(d))), max=round(max(d)))
        out[name].update(uv=per[name])
        print(f"INFO UV {name}: {len(acc)} islands, {a3:.3f} m2, mean {per[name]['mean']} px/m, island min / median / "
              f"max {per[name]['min']} / {per[name]['median']} / {per[name]['max']}")
    gap, border = padding(lab)
    fill = (lab > 0).mean()
    print(f"{'PASS' if gap is None else 'FAIL'} island padding >= 4 px (1024 sheet)" + ("" if gap is None else f" (closest {gap} px)"))
    print(f"{'PASS' if border >= 2 else 'FAIL'} sheet border >= 2 px ({border} px)")
    med = float(np.median([v["median"] for v in per.values()]))
    print(f"{'PASS' if abs(med - 512) <= 51.2 else 'FAIL'} texel density 512 px/m +-10 % (median of the part medians {med:.0f})")
    print(f"INFO packing {fill * 100:.1f} % of the {TEX} sheet")
    out["_uv"] = dict(padding_close=gap, border_px=border, fill=round(float(fill), 3))
    os.makedirs(SCR, exist_ok=True)
    np.save(os.path.join(SCR, "uv_labels.npy"), lab)
    json.dump(out, open(os.path.join(SCR, "topo.json"), "w"), indent=1)
    print("RESULT:", "PASS" if ok_all and gap is None and border >= 2 else "FAIL")


# --------------------------------------------------------------------------- clearance


def sweep_poses(n_fold=24):
    """(label, pose) over everything HERO_SPEC §4 asks for"""
    out = [("working", K.WORKING), ("stowed", K.STOWED)]
    rolls = list(range(0, 360, 15))
    for dp in (-K.IDLE_TURRET, -5.0, 0.0, 5.0, K.IDLE_TURRET):
        for dw in (-K.IDLE_WRIST, -7.5, 0.0, 7.5, K.IDLE_WRIST):
            for r in rolls:
                out.append((f"idle psi{dp:+.0f} wrist{dw:+.1f} roll{r}", K.idle_pose(K.WORKING, dp, dw, r)))
    for dp in (-K.IDLE_TURRET, 0.0, K.IDLE_TURRET):
        for dw in (-K.IDLE_WRIST, 0.0, K.IDLE_WRIST):
            for r in (0, 45, 90, 135, 180, 270):
                st = K.idle_pose(K.WORKING, dp, dw, r)
                for i in range(n_fold + 1):
                    out.append((f"fold from psi{dp:+.0f} wrist{dw:+.0f} roll{r} t={i / n_fold:.3f}", K.fold_pose(st, i / n_fold)))
    return out


PAIRS_ADJ = [("Mount", "Turret"), ("Turret", "UpperArm"), ("UpperArm", "Forearm"), ("Forearm", "Wrist"), ("Wrist", "ToolHead")]
ADJ_MIN, OTHER_MIN = 0.002, 0.010                 # owner: parts >= 2 mm


def clearance(args):
    h0 = "h0" in args
    objs = open_file(h0)
    for o in objs.values(): o.matrix_world = Matrix.Identity(4)
    arm = Arm(objs, spacing=0.006 if not h0 else 0.010)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    D = K.docked_drone(); discs = K.discs(D)
    dv = np.vstack([v for v, t in D.values()]); dt = []; k = 0
    for v, t in D.values(): dt.append(t + k); k += len(v)
    dtree = bvh(dv, np.vstack(dt))
    dlo, dhi = dv.min(0), dv.max(0)
    poses = sweep_poses()
    print(f"INFO {len(poses)} poses swept; drone rebuilt from {os.path.relpath(K.DRONE_FBX, PROJ)}: top "
          f"{dv[:, 1].max():.4f}, discs " + ", ".join(f"({d[0]:.3f}, {d[1]:.3f}) r {d[2]:.3f} y {d[3]:.3f}..{d[4]:.3f}" for d in discs))
    worst_disc = (1e9, None, None); worst_drone = (1e9, None, None); worst_low = (1e9, None, None)
    worst_pair = {}; hits = []
    t0 = time.time()
    for i, (label, pose) in enumerate(poses):
        Wd = arm.world_samples(pose)
        allp = np.vstack(list(Wd.values()))
        for d in discs:
            dd = K.disc_distance(allp, d); j = int(dd.argmin())
            if dd[j] < worst_disc[0]: worst_disc = (float(dd[j]), label, allp[j])
            fp = K.in_footprint(allp, d)
            if fp.any():
                lowy = allp[fp][:, 1]; j2 = int(lowy.argmin())
                if lowy[j2] < worst_low[0]: worst_low = (float(lowy[j2]), label, allp[fp][j2])
        # drone mesh: only samples inside the drone's box + 0.15 (cheap prune)
        near = allp[np.all((allp > dlo - 0.15) & (allp < dhi + 0.15), axis=1)]
        if len(near):
            dmin = nearest(dtree, near)
            if dmin[0] < worst_drone[0]: worst_drone = (dmin[0], label, dmin[1])
        # parts against parts: exact overlap test on the triangles, gap from the samples of one part that lie in the
        # other's box + 3 cm (key poses, every 3rd sweep pose)
        if label in ("working", "stowed") or i % 3 == 0:
            Wm = arm.world(pose)
            trees = {n: bvh(*Wm[n]) for n in Wm}
            box = {n: (Wm[n][0].min(0), Wm[n][0].max(0)) for n in Wm}
            names = list(Wm)
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    na, nb = names[a], names[b]
                    if trees[na].overlap(trees[nb]): hits.append((na, nb, label))
                    dm = 1e9
                    for x, y in ((na, nb), (nb, na)):
                        lo, hi = box[y]; P = Wd[x]
                        P = P[np.all((P > lo - 0.03) & (P < hi + 0.03), axis=1)]
                        if len(P): dm = min(dm, nearest(trees[y], P)[0])
                    key = (na, nb)
                    if dm < worst_pair.get(key, (1e9,))[0]: worst_pair[key] = (dm, label)
    print(f"INFO sweep {time.time() - t0:.0f} s")
    ok = worst_disc[0] >= K.DISC_MIN
    print(f"{'PASS' if ok else 'FAIL'} >= {K.DISC_MIN * 1e3:.0f} mm from the spinning-disc volumes: min "
          f"{worst_disc[0] * 1e3:.1f} mm ({worst_disc[1]}, at {np.round(worst_disc[2], 3).tolist()})")
    ok2 = worst_drone[0] >= K.DRONE_MIN
    print(f"{'PASS' if ok2 else 'FAIL'} >= {K.DRONE_MIN * 1e3:.0f} mm from the drone mesh: min {worst_drone[0] * 1e3:.1f} mm "
          f"({worst_drone[1]}, at {np.round(worst_drone[2], 3).tolist() if worst_drone[2] is not None else None})")
    ok3 = worst_low[0] >= K.DISC_FLOOR_Y
    print(f"{'PASS' if ok3 else 'FAIL'} nothing below y {K.DISC_FLOOR_Y:.2f} inside a disc footprint: lowest "
          f"{worst_low[0]:.4f} ({worst_low[1]})" if worst_low[1] else "PASS nothing inside a disc footprint")
    pair_ok = True
    for (na, nb), (dm, label) in sorted(worst_pair.items(), key=lambda kv: kv[1][0]):
        lim = ADJ_MIN if (na, nb) in PAIRS_ADJ or (nb, na) in PAIRS_ADJ else OTHER_MIN
        okp = dm >= lim and not any(h[0] == na and h[1] == nb for h in hits)
        pair_ok &= okp
        print(f"{'PASS' if okp else 'FAIL'} {na} - {nb}: min gap {dm * 1e3:.1f} mm (>= {lim * 1e3:.1f}; {label})")
    if hits: print("FAIL intersections:", hits[:10], f"... ({len(hits)})")
    # stowed layer, ceiling, released drone volume
    Ws = arm.world(K.STOWED)
    ys = np.vstack([Ws[n][0] for n in K.PARTS if n != "Mount"])
    y0, y1 = ys[:, 1].min(), ys[:, 1].max()
    okl = y0 >= K.STOW_Y0 - 1e-6 and y1 <= K.STOW_Y1 + 1e-6
    print(f"{'PASS' if okl else 'FAIL'} stowed layer y {K.STOW_Y0} ... {K.STOW_Y1}: arm parts y {y0:.4f} ... {y1:.4f}")
    allv = np.vstack([Ws[n][0] for n in K.PARTS])
    print(f"INFO stowed footprint x {allv[:, 0].min():.3f} ... {allv[:, 0].max():.3f}, z {allv[:, 2].min():.3f} ... "
          f"{allv[:, 2].max():.3f} (HERO_SPEC z 5.30 ... 6.30; the mount plate itself spans 5.10 ... 5.50)")
    (vx0, vx1), (vy0, vy1), (vz0, vz1) = K.DRONE_VOLUME
    inside = ((allv[:, 0] > vx0) & (allv[:, 0] < vx1) & (allv[:, 1] > vy0) & (allv[:, 1] < vy1) & (allv[:, 2] > vz0) & (allv[:, 2] < vz1)).sum()
    print(f"{'PASS' if inside == 0 else 'FAIL'} released-state rule: stowed arm vertices inside the drone volume: {inside} "
          f"(arm bottom {y0:.3f}, volume top {vy1})")
    top = max(arm.world(p)[n][0][:, 1].max() for _, p in (("w", K.WORKING), ("s", K.STOWED)) for n in K.PARTS)
    print(f"{'PASS' if top <= K.CEILING_Y + 1e-6 else 'FAIL'} nothing above the ceiling (max y {top:.4f})")
    info = K.WORKING_INFO
    okr = info["reach_needed"] <= info["reach_available"]
    print(f"{'PASS' if okr else 'FAIL'} reach: shoulder -> wrist {info['reach_needed']:.3f} needed (HERO_SPEC 1.60), "
          f"{info['reach_available']:.2f} available (elbow interior {info['elbow_interior']:.1f} deg)")
    tp = K.tip(K.WORKING)
    print(f"INFO working pose (deg) psi {K.WORKING['psi']:.2f}, shoulder {K.WORKING['th1']:.2f}, elbow {K.WORKING['th2']:.2f}, "
          f"wrist {K.WORKING['th3']:.2f}; tool tip {np.round(tp, 4).tolist()} ({(tp[1] - dv[:, 1].max()) * 1e3:.0f} mm over the drone top)")
    print("RESULT:", "PASS" if ok and ok2 and ok3 and pair_ok and not hits and okl and inside == 0 and okr else "FAIL")


# --------------------------------------------------------------------------- renders


def lin(srgb):
    c = np.asarray(srgb, float) / 255.0
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


def scene_setup(size=(1600, 1000), samples=48, bg=(0.05, 0.052, 0.056), view='AgX'):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.samples = samples; sc.cycles.use_denoising = True; sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = size; sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = view; sc.view_settings.look = 'None'
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*bg, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0


def add_light(name, loc, look, power, size=1.5, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.size = size; ld.color = color
    o = bpy.data.objects.new(name, ld); bpy.context.scene.collection.objects.link(o)
    o.location = S.to_blender(loc); t = S.to_blender(look)
    o.rotation_euler = (t - o.location).to_track_quat('-Z', 'Y').to_euler()
    return o


def simple_mat(name, rgb, rough=0.6, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    return m


def add_box(name, x0, x1, y0, y1, z0, z1, mat):
    sm = S.ArmMesh()
    ring = lambda x: [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]
    sm.tube([ring(x0), ring(x1)]); sm.f(*reversed(ring(x0))); sm.f(*ring(x1))
    me = sm.finish(name); o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    me.materials.append(mat)
    return o


def add_drone(textured=True):
    """docked drone from drone_low.fbx (HERO_SPEC §3 pose); with its base map when textured"""
    D = K.docked_drone()
    m = simple_mat("M_DroneProxy", lin((159, 120, 58)), 0.5)
    tex = os.path.join(PROJ, "Assets", "Drone_Asset", "drone_low_M_Drone_BaseMap.png")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=K.DRONE_FBX)
    new = [o for o in bpy.data.objects if o not in before]
    R1 = K.quat_matrix(K.DRONE_LOW_Q); A = K.Ry(K.DRONE_YAW)
    # world (spec) = A (s R1 p + t1) + P  with p = C3^T b  ->  Blender = C3 world
    L = np.eye(4); L[:3, :3] = S.C3 @ A @ (K.DRONE_LOW_SCALE * R1) @ S.C3.T
    L[:3, 3] = S.C3 @ (A @ K.DRONE_LOW_POS + K.DRONE_POS)
    root = Matrix(L.tolist())
    mt = None
    if textured and os.path.exists(tex):
        mt = bpy.data.materials.new("M_DroneTex"); mt.use_nodes = True
        nt = mt.node_tree; b = nt.nodes["Principled BSDF"]; tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = bpy.data.images.load(tex); nt.links.new(tn.outputs[0], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.45
    for o in new:
        if o.type != 'MESH': continue
        if o.name.startswith("ScannerGlow"): bpy.data.objects.remove(o, do_unlink=True); continue
        o.matrix_world = root @ o.matrix_world
        o.data.materials.clear(); o.data.materials.append(mt or m)
    return D


def camera(loc, look, lens=40, ortho=None, shift=(0, 0)):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("cam"); cd.clip_start = 0.01; cd.clip_end = 100; cd.sensor_width = 36
    c = bpy.data.objects.new("cam", cd); sc.collection.objects.link(c)
    c.location = S.to_blender(loc); t = S.to_blender(look)
    c.rotation_euler = (t - c.location).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else: cd.lens = lens
    cd.shift_x, cd.shift_y = shift
    sc.camera = c
    return c


def shot(path):
    sc = bpy.context.scene
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("RENDER", os.path.relpath(path, PROJ))


def load_rgb(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size; a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1, :, :3]                      # top row first


def resize(a, h):
    """nearest-neighbour + box average resize to height h (keeps aspect)"""
    H, W = a.shape[:2]; w = int(round(W * h / H))
    ys = (np.arange(h) + 0.5) * H / h; xs = (np.arange(w) + 0.5) * W / w
    return a[ys.astype(int).clip(0, H - 1)][:, xs.astype(int).clip(0, W - 1)]


def save_jpg(a, path, quality=90):
    h, w = a.shape[:2]
    img = bpy.data.images.new("out", w, h, alpha=False)
    rgba = np.concatenate([a[::-1], np.ones((h, w, 1), np.float32)], 2)
    img.pixels.foreach_set(rgba.astype(np.float32).ravel())
    sc = bpy.context.scene
    vt, lk = sc.view_settings.view_transform, sc.view_settings.look
    sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'        # pixels are already display-ready
    sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = quality
    img.save_render(path, scene=sc)
    sc.render.image_settings.file_format = 'PNG'; sc.view_settings.view_transform = vt; sc.view_settings.look = lk
    bpy.data.images.remove(img)
    print("SAVED", os.path.relpath(path, PROJ))


def side_by_side(render_png, concept_jpg, out_jpg, h=900, labels=None):
    a = load_rgb(render_png); b = load_rgb(concept_jpg)
    # the concept JPG is sRGB-encoded; Blender loads it as sRGB -> linear floats: same space as the render's PNG
    a = resize(a, h); b = resize(b, h)
    gap = np.full((h, 12, 3), 0.02, np.float32)
    save_jpg(np.concatenate([a, gap, b], 1), out_jpg)


def ceiling(mat):
    return add_box("Ceiling", -2.0, 2.0, 4.0, 4.25, 3.6, 7.2, mat)


# concept cameras (spec world). Side: orthographic along -X (camera on +X), screen right = +Z, as the ortho sheet;
# scale and centre from the sheet (plate 0.40 = 490 px of 2576, ceiling at row 40) -> 1225 px/m; "fit" frames our
# longer arm (spec links 1.00 / 0.90 vs ~0.60 in the concept) the way the concept frames its arm.
SIDE_PXM = 1225.0
SIDE_FIT_PXM = 989.0                    # ceiling -> pin tip: 1365 px in the concept = 1.38 m here (concept pose)


def side_camera(pxm, aspect=(2576, 1438), plate_px=1210, ceil_px=40):
    W, H = aspect; scale = W / pxm
    zc = K.MOUNT[2] + (W / 2 - plate_px) / pxm; yc = K.CEILING_Y - (H / 2 - ceil_px) / pxm
    return camera((6.0, yc, zc), (0.0, yc, zc), ortho=scale)


def front_camera():
    """the master view: below the plate, looking slightly up at the arm's +X side from the front-right"""
    look = np.array([0.10, 3.25, 5.55])
    d = np.array([math.cos(math.radians(-8)) * math.cos(math.radians(36)), math.sin(math.radians(-8)),
                  -math.cos(math.radians(-8)) * math.sin(math.radians(36))])
    return camera(tuple(look + 5.2 * d), tuple(look), lens=58)


def setup_room(drone=True, textured_drone=True):
    paint = simple_mat("M_Ceiling", lin((38, 39, 41)), 0.85)
    ceiling(paint)
    if drone: add_drone(textured_drone)


def lights_concept():
    add_light("Key", (2.6, 3.6, 3.2), (0.1, 3.3, 5.4), 260, 2.5)
    add_light("Fill", (2.5, 2.2, 7.5), (0.1, 3.3, 5.4), 120, 3.0, (0.85, 0.92, 1.0))
    add_light("Rim", (-2.0, 3.6, 7.8), (0.1, 3.3, 5.4), 120, 2.0)


def renders(args):
    stage = args[0] if args else "h1"
    h0 = stage == "h0"
    objs = open_file(h0)
    os.makedirs(MEDIA, exist_ok=True); os.makedirs(SCR, exist_ok=True)
    fast = "fast" in args
    scene_setup(size=(1288, 719), samples=16 if fast else 48, bg=lin((62, 62, 64)))
    sc = bpy.context.scene
    if h0:
        grey = simple_mat("M_Grey", lin((95, 104, 114)), 0.45)
        och = simple_mat("M_Och", lin((159, 120, 58)), 0.5)
        stl = simple_mat("M_Stl", lin((170, 172, 175)), 0.35, 1.0)
        pol = simple_mat("M_Pol", lin((40, 42, 44)), 0.6)
        cab = simple_mat("M_Cab", lin((110, 112, 112)), 0.4, 1.0)
        for o in objs.values():
            for i, m in enumerate([grey, pol, stl, och, cab]): o.data.materials[i] = m
    setup_room(drone=False)
    lights_concept()
    tag = f"servicearm_{stage}"
    # 1. concept side camera, concept pose (tool rolled so the notch faces the camera like the sheet)
    S.set_pose(objs, dict(K.CONCEPT, th4=-90.0))
    side_camera(SIDE_FIT_PXM)
    p = os.path.join(SCR, f"{tag}_side_concept_pose.png"); shot(p)
    side_by_side(p, CONCEPT_SIDE, os.path.join(MEDIA, f"{tag}_vs_concept_side.jpg"))
    side_camera(SIDE_PXM)
    p = os.path.join(SCR, f"{tag}_side_concept_pose_platescale.png"); shot(p)
    side_by_side(p, CONCEPT_SIDE, os.path.join(MEDIA, f"{tag}_vs_concept_side_platescale.jpg"))
    # 2. master camera, concept pose
    front_camera()
    p = os.path.join(SCR, f"{tag}_front_concept_pose.png"); shot(p)
    side_by_side(p, CONCEPT_FRONT, os.path.join(MEDIA, f"{tag}_vs_concept.jpg"))
    # 3. working pose over the docked drone, stowed (room context)
    add_drone(True)
    S.set_pose(objs, dict(K.WORKING, th4=-90.0))
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    camera((3.2, 2.6, 2.6), (0.1, 2.75, 4.95), lens=35); shot(os.path.join(SCR, f"{tag}_working_34.png"))
    side_camera(390.0, aspect=(1600, 1000), plate_px=900, ceil_px=60); shot(os.path.join(SCR, f"{tag}_working_side.png"))
    camera((-2.6, 1.9, 1.0), (-0.1, 2.6, 4.9), lens=32); shot(os.path.join(SCR, f"{tag}_working_player.png"))
    S.set_pose(objs, K.STOWED)
    camera((3.2, 2.6, 2.6), (0.1, 3.3, 5.2), lens=35); shot(os.path.join(SCR, f"{tag}_stowed_34.png"))
    camera((1.6, 3.2, 3.3), (0.1, 3.86, 5.6), lens=45); shot(os.path.join(SCR, f"{tag}_stowed_close.png"))
    side_camera(390.0, aspect=(1600, 1000), plate_px=900, ceil_px=60); shot(os.path.join(SCR, f"{tag}_stowed_side.png"))
    extra = []
    if not h0:                                                   # ASSET_RULES validation renders: wire, UV, checker
        for n in ("Ceiling",): bpy.data.objects[n].hide_render = True
        for o in bpy.data.objects:
            if o.type == 'MESH' and not o.name.startswith(S.HERO): o.hide_render = True
        S.set_pose(objs, dict(K.WORKING, th4=-90.0))
        # Cycles (no GPU / EGL here for Workbench): flat grey model, black wire overlay; checker as emission
        sc.cycles.samples = 24
        grey = simple_mat("M_WireGrey", lin((150, 154, 160)), 0.6)
        blk = simple_mat("M_Wire", (0.0, 0.0, 0.0), 0.9)
        keep = {n: list(o.data.materials) for n, o in objs.items()}
        for o in objs.values():
            for i in range(len(o.data.materials)): o.data.materials[i] = grey
        wires = CC.add_wire(objs, 0.0008)
        for _, w in wires:
            w.data = w.data.copy(); w.data.materials.clear(); w.data.materials.append(blk)
        camera((1.35, 3.0, 4.6), (0.2, 3.0, 5.35), lens=40); shot(os.path.join(SCR, f"{tag}_wire.png")); extra.append("wire")
        camera((0.9, 2.5, 4.1), (0.12, 2.35, 4.75), lens=45); shot(os.path.join(SCR, f"{tag}_wire_wrist.png")); extra.append("wire_wrist")
        for _, w in wires: bpy.data.objects.remove(w)
        img = CC.checker_image(TEX)
        mck = bpy.data.materials.new("M_Checker"); mck.use_nodes = True; nt = mck.node_tree
        tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = img
        em = nt.nodes.new("ShaderNodeEmission"); nt.links.new(tn.outputs[0], em.inputs[0])
        nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
        for o in objs.values():
            for i in range(len(o.data.materials)): o.data.materials[i] = mck
        camera((1.35, 3.0, 4.6), (0.2, 3.0, 5.35), lens=40); shot(os.path.join(SCR, f"{tag}_checker.png")); extra.append("checker")
        uv_layout(os.path.join(MEDIA, f"{tag}_uv_layout.jpg"))
    for k in ("working_34", "working_side", "working_player", "stowed_34", "stowed_close", "stowed_side", *extra):
        save_jpg(load_rgb(os.path.join(SCR, f"{tag}_{k}.png")), os.path.join(MEDIA, f"{tag}_{k}.jpg"))


def uv_layout(path):
    lab = np.load(os.path.join(SCR, "uv_labels.npy"))
    rng = np.random.default_rng(2)
    lut = rng.uniform(0.25, 0.85, (lab.max() + 1, 3)); lut[0] = (0.08, 0.08, 0.09)
    rgb = lut[lab]
    edge = np.zeros(lab.shape, bool)
    edge[:, :-1] |= lab[:, :-1] != lab[:, 1:]; edge[:-1, :] |= lab[:-1, :] != lab[1:, :]
    rgb[edge] = (0.02, 0.02, 0.02)
    h = TEX // 2
    save_jpg(rgb.reshape(h, 2, h, 2, 3).mean((1, 3))[::-1].astype(np.float32) ** 2.2, path)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"topo": topo, "clearance": clearance, "renders": renders}[argv[0]](argv[1:])
