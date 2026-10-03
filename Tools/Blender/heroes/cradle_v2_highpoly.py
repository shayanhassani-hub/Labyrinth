"""
Cradle v2 Step 6a: production high-poly (ASSET_RULES "Hero workflow v2": high = low + controlled bevels + clean
detail, floaters allowed) and the bake cages. Starts from the 5b clean set (cradle_v2_bake_test.py).
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_highpoly.py -- build     (HIGH_FINAL + CAGE, saves)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_highpoly.py -- renders   (Renders/cradle_v2_s6a_*)

Design source: Gemini/References/Cradle/cradle_concept_final.jpg + ortho views; the fitted AI model for
measurements (drum bands). Bake-size rules at 428 px/m (2.3 mm/px): grooves >= 4 mm wide (here 6 mm, the plinth
side panels 10 mm per spec), one groove profile everywhere (2.2 mm relief: edges 2.5 mm, floor 0.3 mm over the
surface), raised details >= 8 mm, bolt heads >= 15 mm (here 16 mm). Arm details on Arm_R only (Arm_L shares its
UVs). Floaters sit just over the surface; the cage (each low vertex pushed along its averaged normal just far
enough to enclose the high nearby, + CAGE_MARGIN) replaces the large ray offset of 5b.
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


# --------------------------------------------------------------------------- primitives (spec cradle-local)


def circle(c, u, v, r, n=32):
    return [c + u * (r * math.cos(2 * math.pi * k / n)) + v * (r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def bolt(bm, c, nrm, d=BOLT_D, h=BOLT_H, seg=16):
    """domed bolt head floater: cylinder side then a dome, base 0.3 mm over the surface"""
    nrm = np.array(nrm, float); nrm /= np.linalg.norm(nrm)
    u = np.cross(nrm, [0, 1, 0] if abs(nrm[1]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(nrm, u)
    r = d / 2
    prof = [(r, 0.0003), (r, h * 0.55), (r * 0.85, h * 0.85), (r * 0.5, h), (0.0, h * 1.03)]
    rings = []
    for rr, hh in prof[:-1]:
        rings.append([bm.verts.new(T.spec_pt(c + nrm * hh + u * rr * math.cos(2 * math.pi * k / seg) + v * rr * math.sin(2 * math.pi * k / seg)))
                      for k in range(seg)])
    top = bm.verts.new(T.spec_pt(c + nrm * prof[-1][1]))
    for a, b in zip(rings, rings[1:]):
        for k in range(seg):
            bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))
    for k in range(seg):
        bm.faces.new((rings[-1][k], rings[-1][(k + 1) % seg], top))


def band(bm, centre_xy, z0, z1, r0, r1, ch, seg=48):
    """raised ring around the pin axis (axis = spec z): r0 surface, r1 top, chamfer ch at both ends"""
    cx, cy = centre_xy
    prof = [(z0, r0), (z0 + ch, r1), (z1 - ch, r1), (z1, r0)]
    rings = [[bm.verts.new(T.spec_pt((cx + r * math.cos(2 * math.pi * k / seg), cy + r * math.sin(2 * math.pi * k / seg), z)))
              for k in range(seg)] for z, r in prof]
    for a, b in zip(rings, rings[1:]):
        for k in range(seg):
            bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))


# --------------------------------------------------------------------------- base details


def base_details(bm, base_low):
    n = T.plinth_panels(bm)
    note("Base", "plinth side panels", n, "10 mm groove outline, y 0.052-0.126; 0.60 (Z) / 0.56 (X) / 0.36 m (diagonal) long, r 18 mm corners",
         "tier-1 wall, all 8 faces", "spec 'side panels: outline groove 10 mm'; concept shows them on every face",
         [(0, 0.089, -1.214), (1.214, 0.089, 0), (0.83, 0.089, -0.83)])
    n = T.tray_outlines(bm, base_low)
    note("Base", "tray outlines", n, "6 mm groove, 12 mm outside the tray edge (U: outer side + both ends)", "sunken ring y 0.176, all 8 trays",
         "concept/AI: lip around every tray opening", [(0, 0.176, -1.04), (1.04, 0.176, 0)])
    # pin caps: retaining ring grooves
    for sx in (1, -1):
        c = np.array([sx * V.PIN_X, V.PIN_Y, -0.2404])
        T.groove(bm, circle(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.045), [np.array([0, 0, -1.0])] * 32, LINE_W, True)
        c = np.array([sx * V.PIN_X, V.PIN_Y, 0.2219])
        T.groove(bm, circle(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.060), [np.array([0, 0, 1.0])] * 32, LINE_W, True)
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
    T.groove(bm, circle(c, np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), 0.085), [np.array([0, 1.0, 0])] * 32, LINE_W, True)
    note("Base", "hub cap groove", 1, "6 mm groove ring, r 85 mm", "hub top, y 0.884", "owner list; concept hub has a stepped/inset top",
         [(0.085, 0.884, 0)])
    # column access panel + 4 screws (front face z -0.224)
    zf = -0.224; c = np.array([0.0, 0.56, zf])
    pts = T.rounded_rect(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.17, 0.20, 0.015)
    T.groove(bm, pts, [np.array([0, 0, -1.0])] * len(pts), LINE_W, True)
    for x in (-0.063, 0.063):
        for y in (0.482, 0.638):
            bolt(bm, np.array([x, y, zf]), (0, 0, -1))
    note("Base", "column access panel + 4 screws", 1, "panel 170 x 200 mm, 6 mm groove, r 15 mm corners; screws 16 mm domed heads, 22 mm in from the corners",
         "column front face (z -0.224), y 0.46-0.66", "owner list: service access on the column, the most visible flat face of the hub",
         [(0, 0.56, zf), (0.063, 0.482, zf)])
    # turntable radial seams: 8, over the top annulus, the top chamfer and down the outer wall
    for k in range(8):
        a = math.radians(22.5 + 45 * k); d = np.array([math.cos(a), 0, math.sin(a)])
        up = np.array([0, 1.0, 0]); ch = d * math.cos(math.radians(30)) + up * math.sin(math.radians(30))
        prof = [(0.392, 0.333, up), (0.440, 0.333, up), (0.486, 0.333, up), (0.503, 0.320, ch), (0.5155, 0.300, d),
                (0.5155, 0.280, d), (0.5155, 0.262, d)]
        fc = math.cos(math.radians(11.25))            # seam at a 16-gon facet centre: the flat face is at r * cos(11.25)
        path = [d * r * fc + up * y for r, y, _ in prof]; nrm = [nn for _, _, nn in prof]
        T.groove(bm, path, nrm, LINE_W, False)
    note("Base", "turntable radial seams", 8, "6 mm grooves at 22.5 + k*45 deg, top annulus r 0.392-0.49 and down the outer wall to y 0.262",
         "turntable", "owner list: segment joints make the turntable read as a rotating part",
         [(0.44 * math.cos(math.radians(22.5)), 0.333, 0.44 * math.sin(math.radians(22.5)))])


# --------------------------------------------------------------------------- arm details (Arm_R; spec cradle-local, closed pose)


def arm_details(bm):
    st = V.ARM_ST
    # elbow joint groove (station 3) on the front and back faces, strip and body parts
    pin, pst, pout = (np.array(p) for p in st[3][:3])
    for sz in (-1, 1):
        for a, b, z in ((pin + (pst - pin) * ((V.CH_IN + 0.006) / np.linalg.norm(pst - pin)), pst - (pst - pin) * 0.04, V.STRIP_Z), (pst + (pout - pst) * 0.03, pout - (pout - pst) * 0.06, V.BODY_Z)):
            pts = [np.array([*(a + (b - a) * s), sz * z]) for s in np.linspace(0, 1, 8)]
            T.groove(bm, pts, [np.array([0, 0, sz * 1.0])] * len(pts), LINE_W, False)
    note("Arm_R", "elbow joint groove", 4, "6 mm groove across the strip and body faces", "front and back faces at the elbow (spec station 3)",
         "concept/AI: the lower and upper segments meet at a joint line", [(0.47, 0.982, -0.11), (0.62, 0.995, -0.151)])
    # panel line along each strip (front and back), stations 2..8, mid-way between the rail chamfer and the step
    for sz in (-1, 1):
        pts = []
        for s in st[2:9]:
            pin, pst = np.array(s[0]), np.array(s[1])
            q = pin + (pst - pin) * 0.55
            pts.append(np.array([q[0], q[1], sz * V.STRIP_Z]))
        dense = []
        for a, b in zip(pts, pts[1:]):
            for t in np.linspace(0, 1, 5, endpoint=False): dense.append(a + (b - a) * t)
        dense.append(pts[-1])
        T.groove(bm, dense, [np.array([0, 0, sz * 1.0])] * len(dense), LINE_W, False)
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
    T.groove(bm, pts, nr, LINE_W, True)
    note("Arm_R", "outer face inset panel", 1, "140 x 80 mm, 6 mm groove, r 12 mm corners", "outer face of the upper segment, y 1.24-1.38",
         "visible in the concept on the right arm's outer face", [(outer(1.31), 1.31, 0.0)])
    # plate top outline
    x0, x1, z = V.PLATE_X0 + V.PLATE_IN_CH[0] + 0.022, V.PLATE_X1 - 0.035 - 0.022, V.PLATE_Z - 0.035 - 0.022
    c = np.array([(x0 + x1) / 2, V.PLATE_TOP, 0.0])
    pts = T.rounded_rect(c, np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), x1 - x0, 2 * z, 0.02)
    T.groove(bm, pts, [np.array([0, 1.0, 0])] * len(pts), LINE_W, True)
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
    bm.to_mesh(me); bm.free()
    print(f"HIDDEN {name}: {len(kill)} buried detail faces removed")
    return len(kill)


# --------------------------------------------------------------------------- cage


def make_cage(low, high, name, coll):
    """low pushed along its averaged (angle-weighted) vertex normals: per vertex, just far enough that the high
    points nearest to its faces lie inside, + CAGE_MARGIN; one ring of max-smoothing. Returns (object, max push)."""
    bm = bmesh.new(); bm.from_mesh(low.data); bm.transform(low.matrix_world); bm.normal_update()
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    need = np.zeros(len(bm.verts))
    hm = high.data; hv = np.empty(len(hm.vertices) * 3); hm.vertices.foreach_get("co", hv); hv = hv.reshape(-1, 3)
    Mh = np.array(high.matrix_world); hv = hv @ Mh[:3, :3].T + Mh[:3, 3]
    for p in hv:
        loc, nrm, fi, d = tree.find_nearest(Vector(p))
        if loc is None or d > 0.025: continue
        s = (Vector(p) - loc).dot(nrm)
        if s <= 0: continue
        for v in bm.faces[fi].verts:
            cosang = max(v.normal.dot(nrm), 0.5)
            need[v.index] = max(need[v.index], s / cosang)
    sm = need.copy()
    for v in bm.verts:
        for e in v.link_edges: sm[v.index] = max(sm[v.index], need[e.other_vert(v).index] * 0.5)
    push = sm + CAGE_MARGIN
    for v in bm.verts: v.co += v.normal * push[v.index]
    bm.transform(low.matrix_world.inverted())
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); coll.objects.link(o); o.matrix_world = low.matrix_world.copy()
    o.display_type = 'WIRE'
    return o, float(push.max()), float(np.percentile(push, 95))


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
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    hf = B.coll("HIGH_FINAL"); cg = B.coll("CAGE")
    for c in (hf, cg):
        for o in list(c.objects): bpy.data.objects.remove(o)
    low = {k: bpy.data.objects[f"{k}_low"] for k in B.PARTS}
    t1 = B.BASE_ZONES["T1 diagonal faces: openings into the hollow shell + bowing"]

    def rbase(p):
        if t1(p): return T.R_T1
        if 0.24 < p[1] < 0.36 and 0.30 < math.hypot(p[0], p[2]) < 0.56: return T.R_TT
        return T.R_BASE
    # Base
    lows_all = list(low.values())
    me = T.weighted_bevel(low["Base"], rbase, T.R_TT, "Base_high_final", concave_r=FILLET); nb = len(me.polygons)
    bm = bmesh.new(); bm.from_mesh(me); base_details(bm, low["Base"]); bm.to_mesh(me); bm.free()
    hid = {"Base": drop_hidden_details(me, nb, lows_all, "Base")}
    highs = {"Base": B.add_obj(me, "Base_high_final", hf)}
    # Arm_R
    me = T.weighted_bevel(low["Arm_R"], lambda p: T.R_ARM, T.R_ARM, "Arm_R_high_final", concave_r=FILLET); nb = len(me.polygons)
    bm = bmesh.new(); bm.from_mesh(me); arm_details(bm); bm.to_mesh(me); bm.free()
    hid["Arm_R"] = drop_hidden_details(me, nb, lows_all, "Arm_R")
    highs["Arm_R"] = B.add_obj(me, "Arm_R_high_final", hf)
    # Pad, Riser (bevelled lows, 1.5 mm; riser bolts)
    me = B.bevelled(low["Pad"], 0.0015, "Pad_high_final"); highs["Pad"] = B.add_obj(me, "Pad_high_final", hf)
    me = B.bevelled(low["Riser"], 0.0015, "Riser_high_final")
    bm = bmesh.new(); bm.from_mesh(me); riser_details(bm, low["Riser"]); bm.to_mesh(me); bm.free()
    highs["Riser"] = B.add_obj(me, "Riser_high_final", hf)
    rep = {"tris": {}, "cage": {}, "buried_detail_faces_removed": hid}
    for k, o in highs.items():
        for p in o.data.polygons: p.use_smooth = True
        o.data.calc_loop_triangles(); rep["tris"][k] = len(o.data.loop_triangles); o.color = (0.55, 0.56, 0.6, 1)
        print(f"HIGH {o.name}: {rep['tris'][k]} tris")
    # cages
    for k in B.PARTS:
        cobj, mx, p95 = make_cage(low[k], highs[k], f"{k}_cage", cg)
        rep["cage"][k] = dict(max_push_mm=round(1e3 * mx, 1), p95_push_mm=round(1e3 * p95, 1))
        print(f"CAGE {k}: max push {1e3*mx:.1f} mm, p95 {1e3*p95:.1f} mm")
        # check: high vertices outside the cage (should be none)
        bm = bmesh.new(); bm.from_mesh(cobj.data); bm.transform(cobj.matrix_world); bm.normal_update(); tr = BVHTree.FromBMesh(bm)
        hv = [highs[k].matrix_world @ v.co for v in highs[k].data.vertices]
        outs = [p for p in hv if (lambda r: r[0] is not None and (p - r[0]).dot(r[1]) > 0.0002)(tr.find_nearest(p))]
        out = len(outs)
        bm.free(); rep["cage"][k]["high_verts_outside"] = out
        print(f"{'PASS' if out == 0 else 'FAIL'} cage {k}: {out} high vertices outside the cage")
        if outs:
            P = B.spec_local(outs); cells = {}
            for q in P: cells.setdefault(tuple(np.round(q / 0.05).astype(int)), []).append(q)
            for key, qs in sorted(cells.items(), key=lambda kv: -len(kv[1]))[:8]:
                print(f"     outside: {len(qs)} verts near cradle-local {np.round(np.mean(qs, 0), 3).tolist()}")
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
