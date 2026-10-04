"""
Cradle v2 Step 6a/6b: production high-poly (ASSET_RULES "Hero workflow v2": high = low + controlled bevels + clean
detail, floaters allowed) and the bake cages. Starts from the 5b clean set (cradle_v2_bake_test.py).
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_highpoly.py -- build     (HIGH_FINAL + BAKE_LOW + CAGE, saves)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_highpoly.py -- renders   (Renders/cradle_v2_s6a_*)
Bake, renders and the Substance export: cradle_v2_bake_final.py (Step 6b).

Design source: Gemini/References/Cradle/cradle_concept_final.jpg + ortho views; the fitted AI model for
measurements (drum bands). Bake-size rules at 428 px/m (2.3 mm/px): grooves >= 4 mm wide (here 6 mm, the plinth
side panels 10 mm per spec), one groove profile everywhere (2.2 mm relief: edges 2.5 mm, floor 0.3 mm over the
surface), raised details >= 8 mm, bolt heads >= 15 mm (here 16 mm). Arm details on Arm_R only (Arm_L shares its
UVs). Floaters sit just over the surface; the cage (each low vertex pushed along its averaged normal just far
enough to enclose the high nearby, + CAGE_MARGIN) replaces the large ray offset of 5b.
Step 6b: round parts are true circles in the high (ring edges cut x6 = 96 segments, ring vertices on the circle
through the low's corners, revolution normals); every groove is projected onto the real bevelled surface; ID
vertex colours ("ID", ID_GROUPS); cages are built on the triangulated bake lows (same vertices as Cradle_low.fbx).
"""
import bpy
import bmesh
import json
import math
import os
import sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import cradle_v2 as V                    # noqa: E402
import cradle_v2_check as C              # noqa: E402
import cradle_v2_bake as B               # noqa: E402
import cradle_v2_bake_test as T          # noqa: E402

CZ = V.CZ
SCR = os.path.join(C.PROJ, "Temp", "claude", "cradle_bake")
LINE_W = 0.006                 # standard groove width
BOLT_D, BOLT_H = 0.016, 0.004  # bolt head diameter, height over the surface
CAGE_MARGIN = 0.0015
FILLET = 0.003                 # inside (concave) corners: 3 mm machined fillet; convex edges keep the measured radii
DETAILS = []                   # (part, name, count, size, location, reason, sample points spec-local)


def note(part, name, count, size, where, why, pts):
    DETAILS.append(dict(part=part, name=name, count=count, size=size, where=where, why=why,
                        pts=[list(map(float, p)) for p in pts]))


# --------------------------------------------------------------------------- material ID groups (Step 6b)


ID_GROUPS = {  # group: (name, sRGB 0-255) - vertex colour "ID" on the highs, one texture set M_LAB_HERO_Cradle
    1: ("painted structure", (255, 0, 0)),
    2: ("machined / bare metal", (0, 255, 0)),
    3: ("amber pads", (255, 255, 0)),
    4: ("riser", (0, 0, 255)),
    5: ("fasteners", (255, 0, 255)),
    6: ("column access panel", (0, 255, 255)),
}
G_PAINT, G_METAL, G_AMBER, G_RISER, G_FAST, G_PANEL = 1, 2, 3, 4, 5, 6
NEAREST = None                 # groove floaters: ID of the body face under them


# --------------------------------------------------------------------------- round parts (Step 6b)


ROUND_CUTS = 5                 # each 16-gon edge -> 6 pieces: 96 segments (boss arc: 5 -> 30 over 98 deg)
ROUND_TOL = 3e-4


def round_features(part):
    """surfaces of revolution of the low, spec cradle-local: origin, axis, e1, e2 (ellipse minor axis), rings
    (h along the axis, rx, rz), vertex phase and step (deg), angle range. Rings are the low's polygon rings: the
    circle (ellipse) through their vertices is the true shape."""
    X, Y, Z = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
    if part == "Base":
        f = [dict(name="turntable + rings 2/3", o=np.zeros(3), a=Y, e1=X, e2=Z,
                  rings=[(y, rx, rz) for (rx, rz), y in V.CIRCLES], phase=11.25, step=22.5, rng=None),
             dict(name="hub cap", o=np.zeros(3), a=Y, e1=X, e2=Z,
                  rings=[(y, rx, rz) for (rx, rz), y in V.HUB], phase=11.25, step=22.5, rng=None)]
        for sx in (1, -1):
            f.append(dict(name=f"drum + pin caps {'R' if sx > 0 else 'L'}", o=np.array([sx * V.PIN_X, V.PIN_Y, 0.0]),
                          a=Z, e1=X, e2=Y, rings=[(z, r, r) for r, z in V.DRUM_PROFILE], phase=11.25, step=22.5, rng=None))
        return f
    if part == "Arm_R":
        R0, R1, BZ, CH = V.BOSS_R0, V.BOSS_R1, V.BOSS_Z, V.BOSS_CH
        rings = [(-BZ, R0, R0), (-BZ, R1 - CH, R1 - CH), (-BZ + CH, R1, R1), (BZ - CH, R1, R1), (BZ, R1 - CH, R1 - CH), (BZ, R0, R0)]
        return [dict(name="root boss arc", o=np.array([V.PIN_X, V.PIN_Y, 0.0]), a=Z, e1=X, e2=Y, rings=rings, phase=V.BOSS_A0,
                     step=(V.BOSS_A1 - V.BOSS_A0) / V.BOSS_SEG, rng=(V.BOSS_A0, V.BOSS_A1))]
    return []


def w2s(v):
    return np.array([-v[0], v[2], -v[1] - CZ])


def s2w(p):
    return Vector((-p[0], -p[2] - CZ, p[1]))


def ring_member(p, F):
    """(ring index, polar angle in the ring's circle space) if spec point p lies on one of F's ring polygons"""
    d = p - F["o"]; h = d @ F["a"]; x1 = d @ F["e1"]; x2 = d @ F["e2"]
    st = math.radians(F["step"]); ph = math.radians(F["phase"])
    for i, (hi, rx, rz) in enumerate(F["rings"]):
        if abs(h - hi) > 1e-4: continue
        y2 = x2 * rx / rz; rho = math.hypot(x1, y2)
        if rho < 1e-6: continue
        phi = math.atan2(y2, x1)
        if F["rng"] is not None:
            a = math.degrees(phi)
            if not (F["rng"][0] - 0.01 <= a <= F["rng"][1] + 0.01): continue
        j = math.floor((phi - ph) / st); mid = ph + (j + 0.5) * st
        R = rho * math.cos(phi - mid) / math.cos(st / 2)
        if abs(R - rx) < ROUND_TOL or abs(rho - rx) < ROUND_TOL: return i, phi      # on the chord (low) or the circle
    return None


def roundify(bm, feats):
    """bm in world space. Every ring edge of the round features is cut ROUND_CUTS times and every ring vertex moved
    onto the circle (ellipse) through the ring's corners; faces whose vertices all lie on one feature's rings get
    the face attribute rf = feature index + 1. Returns per-feature counts."""
    rep = []
    for fi, F in enumerate(feats):
        mem = {}
        for v in bm.verts:
            m = ring_member(w2s(v.co), F)
            if m: mem[v] = m
        st = math.radians(F["step"]); edges = []
        for e in bm.edges:
            a, b = e.verts
            if a in mem and b in mem and mem[a][0] == mem[b][0]:
                dphi = abs((mem[a][1] - mem[b][1] + math.pi) % (2 * math.pi) - math.pi)
                if abs(dphi - st) < 0.1 * st: edges.append(e)
        n_v = len(mem)
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=ROUND_CUTS, use_grid_fill=False)
        moved, dmax = 0, 0.0
        for v in bm.verts:
            p = w2s(v.co); m = ring_member(p, F)
            if not m: continue
            i, phi = m; hi, rx, rz = F["rings"][i]
            q = F["o"] + F["a"] * hi + F["e1"] * (rx * math.cos(phi)) + F["e2"] * (rz * math.sin(phi))
            dmax = max(dmax, float(np.linalg.norm(q - p))); v.co = s2w(q); moved += 1
        lay = bm.faces.layers.int.get("rf") or bm.faces.layers.int.new("rf")
        n_f = 0
        for f in bm.faces:
            if f[lay] == 0 and all(ring_member(w2s(v.co), F) for v in f.verts):
                f[lay] = fi + 1; n_f += 1
        rep.append(dict(feature=F["name"], ring_verts_low=n_v, ring_edges_cut=len(edges), verts_on_circle=moved,
                        faces_tagged=n_f, max_move_mm=round(1e3 * dmax, 2),
                        segments=round(360 / (F["step"] / (ROUND_CUTS + 1))) if F["rng"] is None else
                        f"{V.BOSS_SEG * (ROUND_CUTS + 1)} over {F['rng'][1] - F['rng'][0]:.0f} deg"))
        print(f"ROUND {F['name']}: {n_v} ring verts, {len(edges)} edges cut x{ROUND_CUTS + 1}, {moved} verts on the circle "
              f"(max move {1e3 * dmax:.2f} mm), {n_f} faces tagged")
    return rep


def fix_round_normals(me, feats):
    """corner normals of the rf-tagged faces -> surface-of-revolution normals: a hardened corner (normal = its
    face normal) is turned about the axis from the face's angle to the corner's angle (ellipse: in the scaled
    space); smooth bevel corners are already revolved and stay. Undoes the faceting that harden_normals gives
    the 96 facets. Returns (loops changed, max turn deg, p99)."""
    rf = np.zeros(len(me.polygons), np.int32); me.attributes["rf"].data.foreach_get("value", rf)
    cn = np.array([c.vector[:] for c in me.corner_normals])
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    cv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", cv)
    out = cn.copy(); turned = []
    for p in me.polygons:
        if rf[p.index] == 0: continue
        F = feats[rf[p.index] - 1]
        c = w2s(p.center)
        k = 1.0
        if F["name"].startswith("turntable") and c[1] > 0.3565: k = 0.267 / 0.293       # ring 3 is an ellipse
        def frame(q):
            d = q - F["o"]; return math.atan2((d @ F["e2"]) / k, d @ F["e1"])
        phf = frame(c)
        fn = np.array(p.normal[:])
        for li in p.loop_indices:
            if cn[li] @ fn < math.cos(math.radians(0.5)): continue                  # smooth (bevel) corner: already revolved
            n = np.array([-cn[li][0], cn[li][2], -cn[li][1]])                           # world vector -> spec vector
            a = n @ F["a"]; n1 = n @ F["e1"]; n2 = (n @ F["e2"]) * k                    # scaled space (normals: S^-T)
            dphi = frame(w2s(co[cv[li]])) - phf; cs, sn = math.cos(dphi), math.sin(dphi)
            m1, m2 = n1 * cs - n2 * sn, (n1 * sn + n2 * cs) / k                          # turn about the axis, back (S^T)
            ns = F["a"] * a + F["e1"] * m1 + F["e2"] * m2; ns /= np.linalg.norm(ns)
            w = np.array([-ns[0], -ns[2], ns[1]])
            turned.append(math.degrees(math.acos(max(-1.0, min(1.0, float(w @ cn[li]))))))
            out[li] = w
    me.normals_split_custom_set(out.tolist())
    t = np.array(turned) if turned else np.zeros(1)
    return len(turned), float(t.max()), float(np.percentile(t, 99))


def round_bevel(low, rmap, rmax, name, part, concave_r=None):
    """Step 6b version of bake_test.weighted_bevel: the low copy is roundified before the bevel (same per-edge
    radii from the same dihedral rule), the round faces' normals are fixed after it. Returns (mesh, report)."""
    feats = round_features(part)
    me = low.data.copy(); me.name = name + "_src"
    M = low.matrix_world
    bm = bmesh.new(); bm.from_mesh(me); bm.transform(M)
    rrep = roundify(bm, feats)
    bm.normal_update()
    lay = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
    for e in bm.edges:
        e[lay] = 0.0
        if len(e.link_faces) != 2: continue
        if e.calc_face_angle(0.0) < math.radians(30): continue
        mid = (e.verts[0].co + e.verts[1].co) / 2
        r = concave_r if (concave_r is not None and not e.is_convex) else rmap(w2s(mid))
        e[lay] = r / rmax
    bm.transform(M.inverted()); bm.to_mesh(me); bm.free()
    if "rf" not in me.attributes:
        me.attributes.new("rf", 'INT', 'FACE')
    tmp = bpy.data.objects.new(name + "_tmp", me); bpy.context.scene.collection.objects.link(tmp); tmp.matrix_world = M
    for p in me.polygons: p.use_smooth = True
    m = tmp.modifiers.new("bev", 'BEVEL'); m.segments = 3; m.width = rmax; m.limit_method = 'WEIGHT'
    m.use_clamp_overlap = True; m.offset_type = 'OFFSET'; m.harden_normals = True
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg)); out.name = name
    out.transform(M)
    bpy.data.objects.remove(tmp); bpy.data.meshes.remove(me)
    nl, tmax, t99 = fix_round_normals(out, feats) if feats else (0, 0.0, 0.0)
    print(f"NORMALS {name}: {nl} corner normals of round faces set to revolution normals (turn max {tmax:.2f} deg, p99 {t99:.2f})")
    return out, dict(features=rrep, normals_fixed=nl, normal_turn_max_deg=round(tmax, 2), normal_turn_p99_deg=round(t99, 2))


# --------------------------------------------------------------------------- body surface (projection, ID lookup)


class Body:
    """the bevelled body of a high (before details), spec cradle-local: BVH for projecting details onto the real
    rounded surface, and the per-face ID group for the groove floaters"""

    def __init__(self, me, groups):
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
        P = np.column_stack((-co[:, 0], co[:, 2], -co[:, 1] - CZ))
        me.calc_loop_triangles()
        tv = np.empty(len(me.loop_triangles) * 3, np.int32); me.loop_triangles.foreach_get("vertices", tv)
        tp = np.empty(len(me.loop_triangles), np.int32); me.loop_triangles.foreach_get("polygon_index", tp)
        # spec axes are a mirror of Blender's (det -1): reversed winding keeps the normals outward
        self.tree = BVHTree.FromPolygons(P.tolist(), tv.reshape(-1, 3)[:, ::-1].tolist(), all_triangles=True)
        self.tri_poly = tp; self.groups = groups

    def group_at(self, p):
        r = self.tree.find_nearest(Vector(p))
        return int(self.groups[self.tri_poly[r[2]]]) if r[0] is not None else G_PAINT

    def project(self, p, n, reach=0.02):
        """surface point and face normal under p along -n (ray from p + reach n); nearest point as fallback"""
        p = np.array(p, float); n = np.array(n, float); n /= np.linalg.norm(n)
        hit = self.tree.ray_cast(Vector(p + n * reach), Vector(-n), 2 * reach)
        if hit[0] is not None and (np.array(hit[0]) - p) @ (np.array(hit[0]) - p) < 0.015 ** 2:
            return np.array(hit[0]), np.array(hit[1])
        r = self.tree.find_nearest(Vector(p))
        if r[0] is not None and r[3] < 0.015: return np.array(r[0]), np.array(r[1])
        return p, n


BODY = None
GROOVE_DEV = {}                # groove name: max distance (mm) of the 6a path from the real high surface


def _smooth(vecs, s, sigma):
    if sigma <= 0 or len(vecs) < 3: return [v / np.linalg.norm(v) for v in vecs]
    V_ = np.array(vecs); out = []
    for i in range(len(V_)):
        w = np.exp(-0.5 * ((s - s[i]) / sigma) ** 2); v = (V_ * w[:, None]).sum(0); out.append(v / np.linalg.norm(v))
    return out


def pgroove(bm, path, normals, width, closed, name, group=None, sigma_in=0.0, step=0.003):
    """bake_test.groove, projected onto the real (rounded) high surface: the path is densified (<= step), each
    point cast onto BODY along its normal (normals smoothed over sigma_in first, so the rays sweep round edges),
    the floater follows the hit points with the surface normals (smoothed over 4 mm). New faces get the ID of
    the body face under them unless group is given."""
    P = [np.array(p, float) for p in path]; N = [np.array(n, float) for n in normals]
    segs = list(zip(range(len(P)), list(range(1, len(P))) + ([0] if closed else [])))
    if not closed: segs = segs[:len(P) - 1]
    dp, dn = [], []
    for i, j in segs:
        k = max(1, int(math.ceil(np.linalg.norm(P[j] - P[i]) / step)))
        for t in np.linspace(0, 1, k, endpoint=False):
            dp.append(P[i] + (P[j] - P[i]) * t); dn.append(N[i] + (N[j] - N[i]) * t)
    if not closed: dp.append(P[-1]); dn.append(N[-1])
    s = np.concatenate([[0], np.cumsum([np.linalg.norm(b - a) for a, b in zip(dp, dp[1:])])])
    dn = _smooth(dn, s, sigma_in)
    hits = [BODY.project(p, n) for p, n in zip(dp, dn)]
    q = [h[0] for h in hits]
    dev = max(float(np.linalg.norm(a - b)) for a, b in zip(q, dp))
    GROOVE_DEV[name] = round(max(GROOVE_DEV.get(name, 0.0), 1e3 * dev), 1)
    hn = _smooth([h[1] for h in hits], s, 0.004)
    bm.faces.ensure_lookup_table(); n0 = len(bm.faces)
    T.groove(bm, q, hn, width, closed)
    tag_new(bm, n0, group)


def tag_new(bm, n0, group):
    bm.faces.ensure_lookup_table(); lay = bm.faces.layers.int["idg"]
    for f in bm.faces[n0:]:
        if group is not None: f[lay] = group
        else: f[lay] = BODY.group_at(w2s(f.calc_center_median()))


# --------------------------------------------------------------------------- primitives (spec cradle-local)


def circle(c, u, v, r, n=96):
    return [c + u * (r * math.cos(2 * math.pi * k / n)) + v * (r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def bolt(bm, c, nrm, d=BOLT_D, h=BOLT_H, seg=24, lift=0.0):
    """domed bolt head floater: cylinder side then a dome, base 0.3 mm (+ lift) over the real surface under c"""
    c, nrm = BODY.project(c, nrm); c = c + nrm * lift
    nrm = np.array(nrm, float); nrm /= np.linalg.norm(nrm)
    u = np.cross(nrm, [0, 1, 0] if abs(nrm[1]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(nrm, u)
    r = d / 2
    prof = [(r, 0.0003), (r, h * 0.55), (r * 0.85, h * 0.85), (r * 0.5, h), (0.0, h * 1.03)]
    bm.faces.ensure_lookup_table(); n0 = len(bm.faces)
    rings = []
    for rr, hh in prof[:-1]:
        rings.append([bm.verts.new(T.spec_pt(c + nrm * hh + u * rr * math.cos(2 * math.pi * k / seg) + v * rr * math.sin(2 * math.pi * k / seg)))
                      for k in range(seg)])
    top = bm.verts.new(T.spec_pt(c + nrm * prof[-1][1]))
    for a, b in zip(rings, rings[1:]):
        for k in range(seg):
            bm.faces.new((b[k], b[(k + 1) % seg], a[(k + 1) % seg], a[k]))       # spec frame is mirrored: outward in Blender
    for k in range(seg):
        bm.faces.new((top, rings[-1][(k + 1) % seg], rings[-1][k]))
    tag_new(bm, n0, G_FAST)


def band(bm, centre_xy, z0, z1, r0, r1, ch, seg=96):
    """raised ring around the pin axis (axis = spec z): r0 surface, r1 top, chamfer ch at both ends"""
    cx, cy = centre_xy
    prof = [(z0, r0), (z0 + ch, r1), (z1 - ch, r1), (z1, r0)]
    bm.faces.ensure_lookup_table(); n0 = len(bm.faces)
    rings = [[bm.verts.new(T.spec_pt((cx + r * math.cos(2 * math.pi * k / seg), cy + r * math.sin(2 * math.pi * k / seg), z)))
              for k in range(seg)] for z, r in prof]
    for a, b in zip(rings, rings[1:]):
        for k in range(seg):
            bm.faces.new((b[k], b[(k + 1) % seg], a[(k + 1) % seg], a[k]))       # spec frame is mirrored: outward in Blender
    tag_new(bm, n0, G_METAL)


def id_fill(bm, pts, nrm, lift, group):
    """flat ID floater (one n-gon) lift over a flat face: carries an ID region, bakes flat in the normal map"""
    nrm = np.array(nrm, float)
    bm.faces.ensure_lookup_table(); n0 = len(bm.faces)
    f = bm.faces.new([bm.verts.new(T.spec_pt(np.array(p) + nrm * lift)) for p in pts]); f.normal_update()
    if f.normal.dot(T.spec_pt(nrm) - T.spec_pt((0, 0, 0))) < 0: f.normal_flip()
    tag_new(bm, n0, group)


# --------------------------------------------------------------------------- base details


def base_details(bm, base_low):
    # plinth side panels and tray outlines: the bake_test builders, re-routed through the projection
    T.groove = _proj_groove("plinth side panels")
    n = T.plinth_panels(bm)
    note("Base", "plinth side panels", n, "10 mm groove outline, y 0.052-0.126; 0.60 (Z) / 0.56 (X) / 0.36 m (diagonal) long, r 18 mm corners",
         "tier-1 wall, all 8 faces", "spec 'side panels: outline groove 10 mm'; concept shows them on every face",
         [(0, 0.089, -1.214), (1.214, 0.089, 0), (0.83, 0.089, -0.83)])
    n = tray_outlines(bm, base_low)
    note("Base", "tray outlines", n, f"6 mm groove, {TRAY_OFF * 1e3:.0f} mm outside the tray edge (U: outer side + both ends); 6b: was 12 mm, "
         "measured along the corner diagonal, which left it 2-4 mm from the edge on the 10.1 mm bevel (comb artefact)", "sunken ring y 0.176, all 8 trays",
         "concept/AI: lip around every tray opening", [(0, 0.176, -1.04), (1.04, 0.176, 0)])
    # pin caps: retaining ring grooves (machined)
    for sx in (1, -1):
        c = np.array([sx * V.PIN_X, V.PIN_Y, -0.2404])
        pgroove(bm, circle(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.045), [np.array([0, 0, -1.0])] * 96, LINE_W, True,
                "pin cap retaining rings", G_METAL)
        c = np.array([sx * V.PIN_X, V.PIN_Y, 0.2219])
        pgroove(bm, circle(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.060), [np.array([0, 0, 1.0])] * 96, LINE_W, True,
                "pin cap retaining rings", G_METAL)
    note("Base", "pin cap retaining rings", 4, "6 mm groove ring, r 45 mm (front cap, face r 65) / r 60 mm (back cap, face r 85)",
         "front and back pin caps, both hinges", "reads as a retained pin; concept caps are plain discs, a ring adds the mechanical cue",
         [(0.385, 0.637 + 0.045, -0.2404), (0.385, 0.637 + 0.06, 0.2219)])
    # drum bands (measured on the AI: two bands ~76 mm wide, 13 mm proud, 4 mm chamfers)
    for sx in (1, -1):
        for z0, z1 in ((-0.150, -0.072), (0.074, 0.152)):
            band(bm, (sx * V.PIN_X, V.PIN_Y), z0, z1, V.DRUM_R + 0.0003, V.DRUM_R + 0.013, 0.004)
    note("Base", "drum raised bands", 4, "76 mm wide, 13 mm proud, 4 mm chamfers (AI measurement); high-poly only",
         "both drums, z -0.150..-0.072 and +0.074..+0.152", "owner list; in the AI model; the low keeps the plain drum (boss clearance)",
         [(0.385, 0.637 - 0.13, -0.11), (0.385 + 0.13, 0.637, 0.11)])
    # hub cap concentric groove
    c = np.array([0.0, V.HUB[-1][1], 0.0])
    pgroove(bm, circle(c, np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), 0.085), [np.array([0, 1.0, 0])] * 96, LINE_W, True, "hub cap groove")
    note("Base", "hub cap groove", 1, "6 mm groove ring, r 85 mm", "hub top, y 0.884", "owner list; concept hub has a stepped/inset top",
         [(0.085, 0.884, 0)])
    # column access panel + 4 screws (front face z -0.224): outline groove, flat ID fill to the groove centre line
    zf = -0.224; c = np.array([0.0, 0.56, zf])
    pts = T.rounded_rect(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.17, 0.20, 0.015)
    pgroove(bm, pts, [np.array([0, 0, -1.0])] * len(pts), LINE_W, True, "column access panel", G_PANEL)
    id_fill(bm, pts, (0, 0, -1), 0.00025, G_PANEL)
    for x in (-0.063, 0.063):
        for y in (0.482, 0.638):
            bolt(bm, np.array([x, y, zf]), (0, 0, -1), lift=0.0002)
    note("Base", "column access panel + 4 screws", 1, "panel 170 x 200 mm, 6 mm groove, r 15 mm corners; screws 16 mm domed heads, 22 mm in from the corners; "
         "flat ID floater 0.25 mm over the face inside the groove centre line", "column front face (z -0.224), y 0.46-0.66",
         "owner list: service access on the column, the most visible flat face of the hub", [(0, 0.56, zf), (0.063, 0.482, zf)])
    # turntable radial seams: 8, over the top annulus, the rounded top edge (16.9 mm) and down the outer wall.
    # The path follows the low's profile; the rays sweep the rounded edge (normals smoothed over 8 mm), so the
    # floater lies on the real high surface without a break.
    up = np.array([0, 1.0, 0])
    r_top, y_top = V.CIRCLES[2][0][0], V.CIRCLES[2][1]
    r_ch, y_ch = V.CIRCLES[1][0][0], V.CIRCLES[1][1]
    for k in range(8):
        a = math.radians(22.5 + 45 * k); d = np.array([math.cos(a), 0, math.sin(a)])
        t = np.array([r_ch - r_top, y_ch - y_top]); nc = np.array([-t[1], t[0]]); nc /= np.linalg.norm(nc)
        if nc[0] < 0: nc = -nc
        chn = d * nc[0] + up * nc[1]
        prof = [(0.392, y_top), (r_top, y_top), (r_ch, y_ch), (0.516, 0.262)]
        P2, N2 = [], []
        for (r0, y0), (r1, y1), nn in zip(prof, prof[1:], (up, chn, d)):
            q0, q1 = d * r0 + up * y0, d * r1 + up * y1
            k_ = max(2, int(math.ceil(np.linalg.norm(q1 - q0) / 0.002)))
            for t_ in np.linspace(0, 1, k_, endpoint=False): P2.append(q0 + (q1 - q0) * t_); N2.append(nn)
        P2.append(d * 0.516 + up * 0.262); N2.append(d)
        pgroove(bm, P2, N2, LINE_W, False, "turntable radial seams", None, sigma_in=0.008, step=0.002)
    note("Base", "turntable radial seams", 8, "6 mm grooves at 22.5 + k*45 deg, top annulus r 0.392-0.497, over the rounded top edge and down the outer wall to y 0.262",
         "turntable", "owner list: segment joints make the turntable read as a rotating part",
         [(0.44 * math.cos(math.radians(22.5)), 0.333, 0.44 * math.sin(math.radians(22.5)))])


_GROOVE = T.groove
TRAY_OFF = 0.016               # groove centre, perpendicular to the tray edge: 10.1 mm bevel + 3 mm half width + 2.9 mm flat


def tray_outlines(bm, base_low):
    """bake_test.tray_outlines with the offset TRAY_OFF, projected (U outline outside each tray floor's outer edge
    and ends, on the sunken ring y 0.176)"""
    me = base_low.data; M = base_low.matrix_world; n_made = 0
    for p in me.polygons:
        if p.normal.z < 0.99: continue
        P = B.spec_local([M @ me.vertices[i].co for i in p.vertices])
        if abs(P[:, 1].mean() - V.TRAY_FLOOR) > 0.002 or len(P) != 4: continue
        r = np.hypot(P[:, 0], P[:, 2]); inner = np.argsort(r)[:2]
        outer = [i for i in range(4) if i not in inner]
        cyc = list(range(4)); start = next(i for i in cyc if i in inner and cyc[(i + 1) % 4] in outer)
        q = [P[(start + k) % 4] for k in range(4)]
        # each edge of the U offset perpendicular (outward, in plan) by TRAY_OFF, corners mitred. (6a/bake_test
        # offset the corners along the centre diagonal: on the long narrow trays that left the groove only 2-4 mm
        # from the tray edge, on its 10.1 mm bevel.)
        cen = np.mean(q, 0)[[0, 2]]; Q = [x[[0, 2]] for x in q]
        lines = []
        for a_, b_ in zip(Q, Q[1:]):
            t = (b_ - a_) / np.linalg.norm(b_ - a_); n = np.array([t[1], -t[0]])
            if n @ ((a_ + b_) / 2 - cen) < 0: n = -n
            lines.append((a_ + n * TRAY_OFF, t))
        pts2 = [lines[0][0]]
        for (p0, t0), (p1, t1) in zip(lines, lines[1:]):
            A = np.array([t0, -t1]).T; u = np.linalg.solve(A, p1 - p0)[0]; pts2.append(p0 + t0 * u)
        pts2.append(Q[-1] + (lines[-1][0] - Q[-2]))
        path = [np.array([x[0], V.RING_Y, x[1]]) for x in pts2]
        pgroove(bm, path, [np.array([0, 1.0, 0])] * len(path), T.TRAY_W, False, "tray outlines")
        n_made += 1
    return n_made


def _proj_groove(name):
    def g(bm, path, normals, width, closed):
        T.groove = _GROOVE
        try:
            pgroove(bm, path, normals, width, closed, name)
        finally:
            T.groove = g
    return g


# --------------------------------------------------------------------------- arm details (Arm_R; spec cradle-local, closed pose)


def arm_details(bm):
    st = V.ARM_ST
    # elbow joint groove (station 3) on the front and back faces, strip and body parts
    pin, pst, pout = (np.array(p) for p in st[3][:3])
    for sz in (-1, 1):
        for a, b, z in ((pin + (pst - pin) * ((V.CH_IN + 0.006) / np.linalg.norm(pst - pin)), pst - (pst - pin) * 0.04, V.STRIP_Z), (pst + (pout - pst) * 0.03, pout - (pout - pst) * 0.06, V.BODY_Z)):
            pts = [np.array([*(a + (b - a) * s), sz * z]) for s in np.linspace(0, 1, 8)]
            pgroove(bm, pts, [np.array([0, 0, sz * 1.0])] * len(pts), LINE_W, False, "elbow joint groove")
    note("Arm_R", "elbow joint groove", 4, "6 mm groove across the strip and body faces", "front and back faces at the elbow (spec station 3)",
         "concept/AI: the lower and upper segments meet at a joint line", [(0.47, 0.982, -0.11), (0.62, 0.995, -0.151)])
    # panel line along each strip (front and back), stations 2..8, mid-way between the rail chamfer and the step
    for sz in (-1, 1):
        pts = []
        for s in st[2:9]:
            pin, pst = np.array(s[0]), np.array(s[1])
            q = pin + (pst - pin) * 0.55
            pts.append(np.array([q[0], q[1], sz * V.STRIP_Z]))
        pgroove(bm, pts, [np.array([0, 0, sz * 1.0])] * len(pts), LINE_W, False, "strip panel lines")
    note("Arm_R", "strip panel lines", 2, "6 mm groove along the strip, stations 2-8 (y 0.90-1.50)", "front and back strip faces (z +-0.110)",
         "owner list; concept arms show long panel lines on the strips", [(0.46, 1.2, -0.11)])
    # gusset bolts (web faces z +-0.095)
    for sz in (-1, 1):
        for x in (0.72, 0.86):
            bolt(bm, np.array([x, 1.552, sz * V.WEB_Z]), (0, 0, sz))
    note("Arm_R", "gusset bolts", 4, "16 mm domed heads", "web/gusset under the plate, (x 0.72 / 0.86, y 1.552), front and back",
         "owner list: the plate is visibly bolted to the arm", [(0.72, 1.552, -0.095), (0.86, 1.552, 0.095)])
    # outer face inset panel on the upper segment (concept, right arm)
    ys = [s[2][1] for s in st]; xs = [s[2][0] for s in st]

    def outer(y):
        return float(np.interp(y, ys, xs))

    def onrm(y):
        d = np.array([outer(y + 0.005) - outer(y - 0.005), 0.01]); d /= np.linalg.norm(d)
        return np.array([d[1], -d[0], 0.0])
    yc, L, W, r = 1.31, 0.14, 0.08, 0.012
    pts2 = T.rounded_rect(np.array([yc, 0.0, 0.0]), np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), L, W, r)
    pts = [np.array([outer(p[0]), p[0], p[2]]) for p in pts2]; nr = [onrm(p[0]) for p in pts2]
    pgroove(bm, pts, nr, LINE_W, True, "outer face inset panel")
    note("Arm_R", "outer face inset panel", 1, "140 x 80 mm, 6 mm groove, r 12 mm corners", "outer face of the upper segment, y 1.24-1.38",
         "visible in the concept on the right arm's outer face", [(outer(1.31), 1.31, 0.0)])
    # plate top outline
    x0, x1, z = V.PLATE_X0 + V.PLATE_IN_CH[0] + 0.022, V.PLATE_X1 - 0.035 - 0.022, V.PLATE_Z - 0.035 - 0.022
    c = np.array([(x0 + x1) / 2, V.PLATE_TOP, 0.0])
    pts = T.rounded_rect(c, np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), x1 - x0, 2 * z, 0.02)
    pgroove(bm, pts, [np.array([0, 1.0, 0])] * len(pts), LINE_W, True, "plate top outline")
    note("Arm_R", "plate top outline", 1, f"6 mm groove, {x1 - x0:.3f} x {2 * z:.3f} m, 22 mm in from the top flat, r 20 mm corners",
         "rest plate top (pad stays inside)", "concept top view: inset outline on both plates", [((x0 + x1) / 2, V.PLATE_TOP, z)])


def riser_details(bm, riser_low):
    M = riser_low.matrix_world
    for sz in (-1, 1):
        for x in (-0.08, 0.08):
            p = M @ Vector((x, sz * V.RISER["hz"], V.RISER["h"] / 2))            # Blender local: y = -spec z
            c = B.spec_local([p])[0]
            nb = (M.to_3x3() @ Vector((0, sz, 0))).normalized(); n_spec = np.array([-nb.x, nb.z, -nb.y])
            bolt(bm, c, n_spec)
    note("Riser", "riser bolts", 4, "16 mm domed heads", "long side faces, 80 mm from the centre, mid-height",
         "owner list ('4 corner bolts'); the top is covered by the pad (5 mm rim), so they sit on the long faces near the corners",
         [])


def drop_hidden_details(me, n_body, lows, name):
    """detail faces (index >= n_body) whose centre sees no open space (rays blocked by the assembled lows in every
    direction of its hemisphere, review box as in cradle_v2.delete_hidden) are buried (e.g. a drum band inside the
    beam): removed. Returns the number of faces removed."""
    tree = V.scene_bvh(lows); dirs = V.fib_dirs(64)
    box = ((-2.0, -CZ - 2.0, -1.0), (2.0, -CZ + 2.0, 2.6))
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table(); bm.normal_update()
    kill = []
    for f in bm.faces[n_body:]:
        if len(f.verts) > 8: continue                                     # ID fill n-gons: kept with their outline
        n = f.normal; o = f.calc_center_median() + n * 5e-4; seen = False
        for d in dirs:
            if d.dot(n) <= 0.05: continue
            ts = []
            for k, lo, hi in ((0, box[0][0], box[1][0]), (1, box[0][1], box[1][1]), (2, box[0][2], box[1][2])):
                if d[k] > 1e-9: ts.append((hi - o[k]) / d[k])
                elif d[k] < -1e-9: ts.append((lo - o[k]) / d[k])
            te = min(ts)
            if d.z < -1e-9 and -o.z / d.z < te: continue
            if tree.ray_cast(o, d, te)[0] is None: seen = True; break
        if not seen: kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]; bmesh.ops.delete(bm, geom=loose, context='VERTS')
    # orientation: a detail face must not face into the body under it. Only the tray outline ends do (their last
    # row lies on the 3 mm fillet at the tier-2 wall foot): those faces are removed, the groove ends ~2 mm earlier
    bm.verts.index_update(); bm.normal_update(); bm_faces = list(bm.faces)
    btree = BVHTree.FromPolygons([v.co[:] for v in bm.verts], [[v.index for v in f.verts] for f in bm_faces[:n_body]])
    inward = []
    for f in bm_faces[n_body:]:
        r = btree.find_nearest(f.calc_center_median())
        if r[0] is not None and f.normal.dot(r[1]) < -0.2: inward.append(f)
    bmesh.ops.delete(bm, geom=inward, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]; bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(me); bm.free()
    print(f"HIDDEN {name}: {len(kill)} buried detail faces removed; {len(inward)} detail faces facing into the body removed")
    return len(kill)


# --------------------------------------------------------------------------- body ID groups


def base_body_groups(me):
    """painted structure, except the machined pin caps (front r <= 80 mm beyond z -0.190, back r <= 100 mm beyond
    z 0.203) and the turntable top annulus (flat top between ring 2 and the rounded edge)"""
    rf = np.zeros(len(me.polygons), np.int32); me.attributes["rf"].data.foreach_get("value", rf)
    feats = round_features("Base"); g = np.full(len(me.polygons), G_PAINT, np.int32)
    for p in me.polygons:
        if rf[p.index] == 0: continue
        F = feats[rf[p.index] - 1]; c = w2s(p.center); n = np.array([-p.normal.x, p.normal.z, -p.normal.y])
        if F["name"].startswith("drum"):
            d = c - F["o"]; z = d[2]; rho = math.hypot(d[0], d[1])
            if (z < -0.1905 and rho < 0.0812) or (z > 0.2035 and rho < 0.1012): g[p.index] = G_METAL
        elif F["name"].startswith("turntable"):
            rho = math.hypot(c[0], c[2])
            if abs(c[1] - 0.333) < 0.002 and 0.385 < rho < 0.50 and n[1] > 0.95: g[p.index] = G_METAL
    return g


def write_id_colours(me):
    """face group "idg" -> corner colour "ID" (byte, sRGB, exact 0/255 values), the only colour attribute"""
    for a in list(me.color_attributes): me.color_attributes.remove(a)
    g = np.zeros(len(me.polygons), np.int32); me.attributes["idg"].data.foreach_get("value", g)
    lt = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("loop_total", lt)
    per_loop = np.repeat(g, lt)
    rgb = np.array([[0, 0, 0]] + [ID_GROUPS[k][1] for k in sorted(ID_GROUPS)], np.float32) / 255.0
    col = np.ones((len(per_loop), 4), np.float32); col[:, :3] = rgb[per_loop]
    ca = me.color_attributes.new("ID", 'BYTE_COLOR', 'CORNER'); ca.data.foreach_set("color_srgb", col.ravel())
    me.color_attributes.active_color = ca; me.color_attributes.render_color_index = 0
    return {ID_GROUPS[k][0]: int((g == k).sum()) for k in ID_GROUPS if (g == k).any()}


def set_det(me, n_body):
    """face attribute det: 0 body, 1 detail floater (the bake splits them for the curvature map)"""
    a = me.attributes.get("det") or me.attributes.new("det", 'INT', 'FACE')
    v = np.zeros(len(me.polygons), np.int32); v[n_body:] = 1; a.data.foreach_set("value", v)


def set_groups(me, groups):
    a = me.attributes.get("idg") or me.attributes.new("idg", 'INT', 'FACE')
    a.data.foreach_set("value", np.asarray(groups, np.int32))


# --------------------------------------------------------------------------- cage


def bake_low(low, coll_):
    """triangulated export copy of a low (the MikkTSpace basis of Cradle_low.fbx), in the low's frame"""
    import env_kit_generator as K
    c = K.triangulated_export_copy(low)
    for cl in list(c.users_collection): cl.objects.unlink(c)
    coll_.objects.link(c); c.matrix_world = low.matrix_world.copy()
    c.name = c.data.name = low.name.replace("_low", "_bakelow")
    return c


def make_cage(low, high, name, coll):
    """the triangulated bake low (same vertices, order, UVs, normals) pushed along its averaged vertex normals: per
    vertex just far enough that the high points nearest to its faces lie inside, + CAGE_MARGIN, one ring of
    max-smoothing; then up to 6 passes that push the faces under any high vertex still outside. Returns
    (object, max push, p95 push, high verts outside, passes)."""
    bm = bmesh.new(); bm.from_mesh(low.data); bm.transform(low.matrix_world); bm.normal_update()
    bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    base = np.array([v.co[:] for v in bm.verts]); vn = np.array([v.normal[:] for v in bm.verts])
    need = np.zeros(len(bm.verts))
    hm = high.data; hv = np.empty(len(hm.vertices) * 3); hm.vertices.foreach_get("co", hv); hv = hv.reshape(-1, 3)
    Mh = np.array(high.matrix_world); hv = hv @ Mh[:3, :3].T + Mh[:3, 3]
    for p in hv:
        loc, nrm, fi, d = tree.find_nearest(Vector(p))
        if loc is None or d > 0.03: continue
        s = (Vector(p) - loc).dot(nrm)
        if s <= 0: continue
        for v in bm.faces[fi].verts:
            cosang = max(v.normal.dot(nrm), 0.5)
            need[v.index] = max(need[v.index], s / cosang)
    sm = need.copy()
    for v in bm.verts:
        for e in v.link_edges: sm[v.index] = max(sm[v.index], need[e.other_vert(v).index] * 0.5)
    push = sm + CAGE_MARGIN
    faces = [[v.index for v in f.verts] for f in bm.faces]
    # each high vertex is checked against the cage face over its nearest low face (the face its rays come from),
    # not the nearest cage face: separate intersecting shells (drum/beam, column/rings) would mismatch
    owner = []
    for p in hv:
        loc, nrm, fi, d = tree.find_nearest(Vector(p))
        if loc is not None and d <= 0.03: owner.append((p, fi))
    passes = 0
    while True:
        P = base + vn * push[:, None]
        outs = []
        for p, fi in owner:
            a_, b_, c_ = (P[i] for i in faces[fi])
            n = np.cross(b_ - a_, c_ - a_); n /= np.linalg.norm(n)
            if n @ vn[faces[fi]].sum(0) < 0: n = -n
            s = (p - a_) @ n
            if s > 0.0002: outs.append((p, s, fi))
        if not outs or passes >= 6: break
        passes += 1
        for p, s, fi in outs:
            for vi in faces[fi]: push[vi] += s + 0.0005
    for v, p in zip(bm.verts, P): v.co = Vector(p)
    bm.transform(low.matrix_world.inverted())
    me = low.data.copy(); me.name = name; bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); coll.objects.link(o); o.matrix_world = low.matrix_world.copy()
    o.display_type = 'WIRE'
    return o, float(push.max()), float(np.percentile(push, 95)), len(outs), passes, [p for p, _, _ in outs]


# --------------------------------------------------------------------------- UV seam crossing


def seam_report(lows):
    """for every detail: the low UV islands under its sample points (nearest low face); more than one = crosses"""
    out = []
    isl = {}; trees = {}
    for k, lo in lows.items():
        me = lo.data; groups = C.uv_islands(me); f2i = {}
        for gi, g in enumerate(groups):
            for f in g: f2i[f] = gi
        isl[k] = f2i
        bm = bmesh.new(); bm.from_mesh(me); bm.transform(lo.matrix_world); trees[k] = BVHTree.FromBMesh(bm); bm.free()
    return isl, trees


# --------------------------------------------------------------------------- build


def build(args):
    global BODY
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    hf = B.coll("HIGH_FINAL"); cg = B.coll("CAGE"); bl = B.coll("BAKE_LOW")
    for c in (hf, cg, bl):
        for o in list(c.objects): bpy.data.objects.remove(o)
    low = {k: bpy.data.objects[f"{k}_low"] for k in B.PARTS}
    t1 = B.BASE_ZONES["T1 diagonal faces: openings into the hollow shell + bowing"]

    def rbase(p):
        if t1(p): return T.R_T1
        if 0.24 < p[1] < 0.36 and 0.30 < math.hypot(p[0], p[2]) < 0.56: return T.R_TT
        return T.R_BASE
    lows_all = list(low.values())
    rep = {"tris": {}, "cage": {}, "round": {}, "id_faces": {}}
    highs, hid = {}, {}
    # Base: round bevel, body groups, details on the real surface
    me, rep["round"]["Base"] = round_bevel(low["Base"], rbase, T.R_TT, "Base_high_final", "Base", concave_r=FILLET)
    nb = len(me.polygons); set_groups(me, base_body_groups(me)); BODY = Body(me, base_body_groups(me))
    bm = bmesh.new(); bm.from_mesh(me); base_details(bm, low["Base"]); bm.to_mesh(me); bm.free(); set_det(me, nb)
    hid["Base"] = drop_hidden_details(me, nb, lows_all, "Base")
    highs["Base"] = B.add_obj(me, "Base_high_final", hf)
    # Arm_R
    me, rep["round"]["Arm_R"] = round_bevel(low["Arm_R"], lambda p: T.R_ARM, T.R_ARM, "Arm_R_high_final", "Arm_R", concave_r=FILLET)
    nb = len(me.polygons); set_groups(me, [G_PAINT] * nb); BODY = Body(me, np.full(nb, G_PAINT))
    bm = bmesh.new(); bm.from_mesh(me); arm_details(bm); bm.to_mesh(me); bm.free(); set_det(me, nb)
    hid["Arm_R"] = drop_hidden_details(me, nb, lows_all, "Arm_R")
    highs["Arm_R"] = B.add_obj(me, "Arm_R_high_final", hf)
    # Pad, Riser: 1.5 mm bevels with hardened normals (6a: plain smooth, which bent the flat faces' normals)
    me = T.weighted_bevel(low["Pad"], lambda p: 0.0015, 0.0015, "Pad_high_final"); set_groups(me, [G_AMBER] * len(me.polygons))
    highs["Pad"] = B.add_obj(me, "Pad_high_final", hf)
    me = T.weighted_bevel(low["Riser"], lambda p: 0.0015, 0.0015, "Riser_high_final"); nb = len(me.polygons)
    set_groups(me, [G_RISER] * nb); BODY = Body(me, np.full(nb, G_RISER))
    bm = bmesh.new(); bm.from_mesh(me); riser_details(bm, low["Riser"]); bm.to_mesh(me); bm.free(); set_det(me, nb)
    highs["Riser"] = B.add_obj(me, "Riser_high_final", hf)
    rep["buried_detail_faces_removed"] = hid
    rep["groove_projection_max_mm"] = GROOVE_DEV
    for k, o in highs.items():
        for p in o.data.polygons: p.use_smooth = True
        if "rf" in o.data.attributes: o.data.attributes.remove(o.data.attributes["rf"])
        rep["id_faces"][k] = write_id_colours(o.data)
        o.data.calc_loop_triangles(); rep["tris"][k] = len(o.data.loop_triangles); o.color = (0.55, 0.56, 0.6, 1)
        print(f"HIGH {o.name}: {rep['tris'][k]} tris, ID faces {rep['id_faces'][k]}")
    for name, mm in GROOVE_DEV.items(): print(f"GROOVE {name}: 6a path up to {mm} mm off the real high surface (now projected)")
    # cages on the triangulated bake lows (identical vertices to Cradle_low.fbx)
    for k in B.PARTS:
        blo = bake_low(low[k], bl)
        cobj, mx, p95, out, passes, outs = make_cage(blo, highs[k], f"{k}_cage", cg)
        rep["cage"][k] = dict(max_push_mm=round(1e3 * mx, 1), p95_push_mm=round(1e3 * p95, 1), high_verts_outside=out, fix_passes=passes,
                              verts_low=len(blo.data.vertices), verts_cage=len(cobj.data.vertices))
        print(f"{'PASS' if out == 0 else 'FAIL'} cage {k}: max push {1e3*mx:.1f} mm, p95 {1e3*p95:.1f} mm, {out} high vertices outside "
              f"({passes} fix passes), verts low/cage {len(blo.data.vertices)}/{len(cobj.data.vertices)}")
        if outs:
            P = B.spec_local(outs); cells = {}
            for q in P: cells.setdefault(tuple(np.round(q / 0.05).astype(int)), []).append(q)
            for key, qs in sorted(cells.items(), key=lambda kv: -len(kv[1]))[:8]:
                print(f"     outside: {len(qs)} verts near cradle-local {np.round(np.mean(qs, 0), 3).tolist()}")
        blo.hide_render = True; cobj.hide_render = True
    # UV seam crossings of the details
    f2i, trees = seam_report(low)
    rep["details"] = []
    for d in DETAILS:
        part = d["part"]; ids = set()
        for p in d["pts"]:
            q = T.spec_pt(p); r = trees[part].find_nearest(q)
            if r[0] is not None: ids.add(f2i[part].get(r[2], -1))
        d2 = {k: v for k, v in d.items() if k != "pts"}; d2["uv_islands_at_samples"] = len(ids)
        rep["details"].append(d2)
    rep["id_groups"] = {str(k): dict(name=n, srgb=c) for k, (n, c) in ID_GROUPS.items()}
    os.makedirs(SCR, exist_ok=True)
    json.dump(rep, open(os.path.join(SCR, "highpoly.json"), "w"), indent=1)
    for o in hf.objects: o.hide_render = False
    bpy.ops.wm.save_as_mainfile(filepath=B.BAKE, compress=True)
    print("SAVED", B.BAKE)


# --------------------------------------------------------------------------- seam crossing (dense, per detail geometry)


def crossings(args):
    """every floater strip / bolt of the finals: which low UV islands lie under its vertices (nearest low face);
    a detail over 2+ islands crosses a UV seam. Reported with the islands' shared border type (hard / soft)."""
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    low = {k: bpy.data.objects[f"{k}_low"] for k in B.PARTS}
    f2i, trees = seam_report(low)
    for k in ("Base", "Arm_R", "Riser"):
        hi = bpy.data.objects[f"{k}_high_final"]
        bm = bmesh.new(); bm.from_mesh(hi.data); bm.transform(hi.matrix_world)
        # loose parts = detail pieces; the bevelled body is the largest part
        bm.verts.ensure_lookup_table(); seen = set(); parts = []
        for v in bm.verts:
            if v in seen: continue
            st = [v]; seen.add(v); comp = []
            while st:
                x = st.pop(); comp.append(x)
                for e in x.link_edges:
                    w = e.other_vert(x)
                    if w not in seen: seen.add(w); st.append(w)
            parts.append(comp)
        parts.sort(key=len, reverse=True)
        n_cross = 0
        for comp in parts[1:]:
            ids = set()
            for v in comp:
                r = trees[k].find_nearest(v.co)
                if r[0] is not None and r[3] < 0.02: ids.add(f2i[k].get(r[2], -1))
            if len(ids) > 1:
                n_cross += 1
                c = B.spec_local([sum((v.co for v in comp), Vector()) / len(comp)])[0]
                print(f"CROSS {k}: detail piece of {len(comp)} verts at cradle-local ({c[0]:+.3f}, {c[1]:.3f}, {c[2]:+.3f}) spans {len(ids)} UV islands")
        print(f"INFO {k}: {len(parts) - 1} detail pieces, {n_cross} cross a UV seam")
        bm.free()


# --------------------------------------------------------------------------- renders


CLOSE = {  # name: (camera spec cradle-local, look-at, lens)
    "plinth_panel": ([-0.95, 0.35, -2.05], [-0.45, 0.10, -1.21], 45),
    "tray_outline": ([0.55, 1.05, -1.75], [0.45, 0.17, -0.95], 45),
    "pin_drum": ([1.05, 0.55, -0.85], [0.40, 0.62, -0.10], 45),
    "hub_column": ([0.25, 1.20, -0.95], [0.0, 0.62, -0.22], 45),
    "turntable": ([-0.95, 0.80, -0.75], [-0.41, 0.29, -0.29], 45),
    "arm_strip": ([0.10, 1.35, -1.05], [0.50, 1.15, -0.11], 45),
    "arm_outer": ([1.55, 1.35, -0.55], [0.66, 1.31, 0.0], 45),
    "gusset": ([1.20, 1.25, -0.95], [0.78, 1.53, -0.09], 45),
    "plate_top": ([0.70, 2.55, -0.85], [0.70, 1.70, 0.0], 40),
    "riser": ([-0.55, 1.95, -0.75], [-0.50, 1.73, -0.07], 45),
}


def renders(args):
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    for o in bpy.data.objects: o.hide_render = True
    C.setup_render(size=(1800, 1200))
    bpy.data.objects["RenderFloor"].hide_render = False
    sc = bpy.context.scene
    hi = {k: bpy.data.objects[f"{k}_high_final"] for k in B.PARTS}
    for o in hi.values(): o.hide_render = False; o.color = (0.55, 0.56, 0.6, 1)
    # display only: mirrored Arm_L high and the left pad on the riser (the real Arm_L shares Arm_R's UVs/bake)
    ml = hi["Arm_R"].data.copy(); ml.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
    bm = bmesh.new(); bm.from_mesh(ml); bmesh.ops.reverse_faces(bm, faces=bm.faces); bm.to_mesh(ml); bm.free()
    al = bpy.data.objects.new("ArmL_display", ml); sc.collection.objects.link(al); al.color = (0.55, 0.56, 0.6, 1)
    pl = bpy.data.objects.new("PadL_display", hi["Pad"].data); sc.collection.objects.link(pl)
    pl.matrix_world = Matrix.Translation(V.to_blender((-V.PAD_X, V.PLATE_TOP + V.RISER["h"], CZ)) - V.to_blender((V.PAD_X, V.PLATE_TOP, CZ))) @ hi["Pad"].matrix_world
    pl.color = (1.0, 0.55, 0.05, 1); hi["Pad"].color = (1.0, 0.55, 0.05, 1)
    C.camera([0, 1.0, CZ - 8], [0, 1.0, CZ], ortho=3.4); C.shot("cradle_v2_s6a_high_front.png")
    C.camera([-2.9, 2.4, CZ - 3.2], [0, 0.9, CZ]); C.shot("cradle_v2_s6a_high_34.png")
    C.camera([2.9, 2.2, CZ + 3.2], [0, 0.8, CZ]); C.shot("cradle_v2_s6a_high_back34.png")
    for name, (loc, look, lens) in CLOSE.items():
        C.camera([loc[0], loc[1], loc[2] + CZ], [look[0], look[1], look[2] + CZ], lens=lens)
        C.shot(f"cradle_v2_s6a_close_{name}.png")
    # low wireframe over the high at the hinge (scale reference)
    for k in ("Base", "Arm_R"):
        lo = bpy.data.objects[f"{k}_low"]; w = lo.copy(); w.data = lo.data; sc.collection.objects.link(w)
        m = w.modifiers.new("Wire", 'WIREFRAME'); m.thickness = 0.0015; m.use_replace = True; m.use_even_offset = True
        w.hide_render = False; w.color = (0.02, 0.02, 0.02, 1)
    loc, look, lens = CLOSE["pin_drum"]
    C.camera([loc[0], loc[1], loc[2] + CZ], [look[0], look[1], look[2] + CZ], lens=lens)
    C.shot("cradle_v2_s6a_overlay_hinge.png")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["build"]
    {"build": build, "renders": renders, "crossings": crossings}[argv[0]](argv[1:])
