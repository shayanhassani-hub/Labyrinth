"""
Cradle v2 low-poly: validation and review renders (HERO_SPEC §3, ASSET_RULES hero standard).
  blender -b -P Tools/Blender/heroes/cradle_v2_check.py -- <stage> [...]
stages:
  topo        tri counts and topology stats per part
  deviation   distance low-poly <-> fitted AI high-poly (Temp/claude/cradle_ai/fit_*.npz), per part and
              class (edge zone / flat), clusters over the limits, heatmap render
  clearance   docked drone clearances, fold sweep 0..75 deg (arms + pads + riser vs the docked drone),
              arm/boss vs base over the sweep, release height and floor
  renders     cradle_v2_s3_* review renders (shaded, wire on shaded, dock, release)
  quick       a few shaded views into Temp/claude/cradle_v2/ for construction checks
Everything opens the saved review file (cradle_v2.SAVE) and never saves it.
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
from mathutils.kdtree import KDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cradle_v2 as V                                   # noqa: E402

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CACHE = os.path.join(PROJ, "Temp", "claude", "cradle_ai")
SCR = os.path.join(PROJ, "Temp", "claude", "cradle_v2")
RENDERS = os.path.join(PROJ, "Renders")
DRONE_OBJ = os.path.join(PROJ, "Temp", "claude", "drone_world_spec.obj")
PARTS = ["Base_01", "Arm_L_01", "Arm_R_01", "Pad_R_01", "Pad_L_01", "Riser_L_01"]
LIMIT_EDGE, LIMIT_FLAT = 0.005, 0.003
RNG = np.random.default_rng(3)


def open_file():
    bpy.ops.wm.open_mainfile(filepath=V.SAVE)
    return {p: bpy.data.objects[f"{V.HERO}_{p}"] for p in PARTS}


def spec_world(v_blender):
    v = np.asarray(v_blender)
    return np.column_stack((-v[:, 0], v[:, 2], -v[:, 1]))


def obj_arrays(o):
    """world-space triangles of an object, spec axes"""
    me = o.data; me.calc_loop_triangles()
    v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", v); v = v.reshape(-1, 3)
    M = np.array(o.matrix_world); v = v @ M[:3, :3].T + M[:3, 3]
    t = np.empty(len(me.loop_triangles) * 3, np.int32); me.loop_triangles.foreach_get("vertices", t)
    # Blender -> spec is a mirror: reverse the winding so spec-space normals stay outward
    return spec_world(v), t.reshape(-1, 3)[:, ::-1].copy()


def bvh(v, t):
    return BVHTree.FromPolygons(np.asarray(v).tolist(), np.asarray(t).tolist(), all_triangles=True)


def sample(v, t, n=None, spacing=0.004):
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    if n is None: n = int(area.sum() / spacing ** 2) + 100
    idx = RNG.choice(len(t), n, p=area / area.sum())
    r1 = np.sqrt(RNG.random(n)); r2 = RNG.random(n)
    p = (1 - r1)[:, None] * a[idx] + (r1 * (1 - r2))[:, None] * b[idx] + (r1 * r2)[:, None] * c[idx]
    return p, idx


def nearest(tree, pts):
    return np.array([tree.find_nearest(Vector(p))[3] for p in pts])


def set_pose(objs, deg):
    objs["Arm_L_01"].rotation_euler = (0, math.radians(deg), 0)
    objs["Arm_R_01"].rotation_euler = (0, -math.radians(deg), 0)
    bpy.context.view_layer.update()


# --------------------------------------------------------------------------- topology


def topo(args):
    objs = open_file()
    out = {}; total = 0
    seen = set()
    for name, o in objs.items():
        me = o.data
        bm = bmesh.new(); bm.from_mesh(me)
        q = sum(1 for f in bm.faces if len(f.verts) == 4); tr = sum(1 for f in bm.faces if len(f.verts) == 3)
        ng = sum(1 for f in bm.faces if len(f.verts) > 4)
        border = sum(1 for e in bm.edges if e.is_boundary)
        nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        wire = sum(1 for e in bm.edges if len(e.link_faces) == 0)
        loose = sum(1 for v in bm.verts if not v.link_faces)
        zero = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
        dup = len(bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=1e-5)["targetmap"])
        # winding: every edge shared by two faces must be walked in opposite directions
        inconsistent = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
        # flipped: face normals pointing into the part (ray from the face centre along +normal hits
        # the same part within 1 mm while the reverse ray escapes) are rare; count normals facing the
        # part centroid on closed shells only is unreliable, so use the contiguity check above
        sharp = sum(1 for e in bm.edges if not e.smooth)
        bm.free()
        me.calc_loop_triangles(); tris = len(me.loop_triangles)
        first = me.name not in seen; seen.add(me.name)
        if first: total += tris
        out[name] = dict(mesh=me.name, tris=tris, quads=q, tris_faces=tr, ngons=ng, open_border_edges=border,
                         nonmanifold=nonman, wire_edges=wire, loose_verts=loose, zero_area=zero, duplicates=dup,
                         winding_inconsistent=inconsistent, sharp_edges=sharp, verts=len(me.vertices))
        ok = ng == 0 and nonman == 0 and wire == 0 and loose == 0 and zero == 0 and dup == 0 and inconsistent == 0
        out[name]["topology_pass"] = ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: {tris} tris ({q} quads, {tr} tris, {ng} n-gons), open border {border}, "
              f"non-manifold {nonman}, loose {loose}, dup {dup}, zero-area {zero}, winding errors {inconsistent}, sharp {sharp}")
    # Arm_L must be the exact mirror of Arm_R (object-local, Blender x -> -x)
    def local(o):
        v = np.empty(len(o.data.vertices) * 3); o.data.vertices.foreach_get("co", v); return v.reshape(-1, 3)
    lv, rv = local(objs["Arm_L_01"]), local(objs["Arm_R_01"]); rv[:, 0] *= -1
    from mathutils.kdtree import KDTree as KD
    kd = KD(len(rv))
    for i, q in enumerate(rv): kd.insert(q, i)
    kd.balance()
    md = max(kd.find(q)[2] for q in lv) if len(lv) == len(rv) else float("inf")
    mirror_ok = len(lv) == len(rv) and md < 1e-6 and len(objs["Arm_L_01"].data.polygons) == len(objs["Arm_R_01"].data.polygons)
    print(f"{'PASS' if mirror_ok else 'FAIL'} Arm_L is the exact mirror of Arm_R (verts {len(lv)}/{len(rv)}, max offset {md:.2e} m)")
    out["_arm_mirror_ok"] = bool(mirror_ok)
    holes, nb = hole_test(objs)
    for name in PARTS:
        hs = holes.get(name, [])
        print(f"{'PASS' if not hs else 'FAIL'} hole test {name}: {nb[name]} open border edges, {len(hs)} hole edges")
        for h in hs[:20]: print(f"     HOLE at cradle-local {h['at_cradle_local']} (pose {h['pose_deg']:.0f} deg)")
        out[name]["hole_edges"] = hs
        if hs: out[name]["topology_pass"] = False
    inst = sum(v["tris"] for k, v in out.items() if not k.startswith("_"))
    print(f"TOTAL unique meshes {total} tris; in the scene (pad instanced twice) {inst} tris")
    out["_total_unique"] = total; out["_total_scene"] = inst
    os.makedirs(SCR, exist_ok=True)
    json.dump(out, open(os.path.join(SCR, "topo.json"), "w"), indent=1)


# --------------------------------------------------------------------------- deviation


def ai_ref():
    ref = {}
    for key, name in (("Base_01", "AI_A_Static_sym"), ("Arm_L_01", "AI_A_Arm_L"), ("Arm_R_01", "AI_A_Arm_R")):
        d = np.load(os.path.join(CACHE, f"fit_{name}.npz")); ref[key] = (d["v"], d["t"])
    return ref


def feature_points(o, deg=20.0, step=0.004):
    """points along feature edges (dihedral > deg) and open borders, spec world"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    M = o.matrix_world; pts = []
    for e in bm.edges:
        if e.is_boundary or (len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(deg)):
            a, b = M @ e.verts[0].co, M @ e.verts[1].co
            n = max(2, int((b - a).length / step) + 1)
            for i in range(n):
                pts.append(a.lerp(b, i / (n - 1)))
    bm.free()
    return spec_world(np.array(pts)) if pts else np.zeros((0, 3))


def fib_dirs(n):
    out = []
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n; r = math.sqrt(max(0, 1 - y * y)); th = math.pi * (3 - math.sqrt(5)) * i
        out.append(np.array([r * math.cos(th), y, r * math.sin(th)]))
    return out


def visible_samples(p, v, t, fi, tree, ndir=64):
    """spec-space visibility of surface samples: a sample counts if one ray leaves the review box
    (|x|, |z - 4.69| < 2, y < 2.6) without hitting the assembly; rays reaching the floor are blocked"""
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    n = np.cross(b - a, c - a); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    dirs = fib_dirs(ndir); out = np.zeros(len(p), bool)
    lo = np.array([-2.0, -1.0, V.CZ - 2.0])          # below the floor: floor hits always count
    hi = np.array([2.0, 2.6, V.CZ + 2.0])
    for i, (q, fidx) in enumerate(zip(p, fi)):
        nn = n[fidx]; o = q + nn * 5e-4
        for d in dirs:
            if d @ nn <= 0.05: continue
            ts = [((hi[k] if d[k] > 0 else lo[k]) - o[k]) / d[k] for k in range(3) if abs(d[k]) > 1e-9]
            te = min(ts)
            if d[1] < -1e-9 and -o[1] / d[1] < te: continue
            if tree.ray_cast(Vector(o), Vector(d), te)[0] is None:
                out[i] = True; break
    return out


def hole_test(objs, ndir=64):
    """every open border edge must be explained: floor contact, or the border of a face deleted as hidden.
    Test: a point just inside the solid, under the missing side (2 mm across the edge, 3 mm below the adjacent
    face). If a ray from there reaches open space (review box; floor hits blocked) in the closed or the released
    pose, the interior can be seen through the gap -> HOLE."""
    parts = [objs[n] for n in PARTS]
    dirs = [Vector(d) for d in fib_dirs(ndir)]
    dirs = [Vector((-d.x, -d.z, d.y)) for d in dirs]          # spec -> Blender axes (a direction set, any order)
    box = ((-2.0, -V.CZ - 2.0, -1.0), (2.0, -V.CZ + 2.0, 2.6))
    report = {}
    cand = {}
    for name in PARTS:
        o = objs[name]; bm = bmesh.new(); bm.from_mesh(o.data)
        items = []
        for e in bm.edges:
            if not e.is_boundary: continue
            f = e.link_faces[0]
            a, b = e.verts[0].co, e.verts[1].co
            mid = (a + b) / 2; t = (b - a).normalized(); n = f.normal.normalized()
            away = mid - f.calc_center_median(); away = (away - t * away.dot(t)).normalized()
            items.append((mid.copy(), n.copy(), away.copy()))
        bm.free(); cand[name] = items
    for deg in (0.0, V.RELEASE_DEG):
        set_pose(objs, deg)
        tree = V.scene_bvh(parts)
        for name in PARTS:
            o = objs[name]; M = o.matrix_world; R = M.to_3x3()
            for i, (mid, n, away) in enumerate(cand[name]):
                w = M @ mid
                if w.z < 0.002: continue                         # floor contact
                nw = (R @ n).normalized(); aw = (R @ away).normalized()
                pin = w + aw * 0.002 - nw * 0.003
                for d in dirs:
                    ts = []
                    for k, lo, hi in ((0, box[0][0], box[1][0]), (1, box[0][1], box[1][1]), (2, box[0][2], box[1][2])):
                        if d[k] > 1e-9: ts.append((hi - pin[k]) / d[k])
                        elif d[k] < -1e-9: ts.append((lo - pin[k]) / d[k])
                    te = min(ts)
                    if d.z < -1e-9 and -pin.z / d.z < te: continue
                    if tree.ray_cast(pin, d, te)[0] is None:
                        sp = V.to_blender((0, 0, 0))
                        loc = (round(-w.x, 3), round(w.z, 3), round(-w.y - V.CZ, 3))
                        report.setdefault(name, {})[i] = dict(at_cradle_local=loc, pose_deg=deg)
                        break
    set_pose(objs, 0.0)
    return {k: list(v.values()) for k, v in report.items()}, {k: len(v) for k, v in cand.items()}


def deviation(args):
    objs = open_file()
    ref = ai_ref(); res = {}
    heat = {}
    allp = [obj_arrays(objs[n]) for n in PARTS]
    VV = np.vstack([v for v, t in allp]); TT = []; off = 0
    for v, t in allp: TT.append(t + off); off += len(v)
    scene_tree = bvh(VV, np.vstack(TT))
    for key in ("Base_01", "Arm_L_01", "Arm_R_01"):
        o = objs[key]
        lv, lt = obj_arrays(o)
        rv, rt = ref[key]
        rtree = bvh(rv, rt); ltree = bvh(lv, lt)
        p, fi = sample(lv, lt, spacing=0.006)
        vis = visible_samples(p, lv, lt, fi, scene_tree)
        hidden_share = 1 - vis.mean()
        p, fi = p[vis], fi[vis]
        d = nearest(rtree, p)
        fp = feature_points(o)
        kd = KDTree(len(fp))
        for i, q in enumerate(fp): kd.insert(q, i)
        kd.balance()
        edge = np.array([kd.find(q)[2] < 0.012 for q in p]) if len(fp) else np.zeros(len(p), bool)
        # AI -> low: AI detail the low-poly leaves to the bake (only AI points near the low-poly's reach)
        q, _ = sample(rv, rt, n=60000)
        d2 = nearest(ltree, q)
        r = {}
        for cls, m, lim in (("edge", edge, LIMIT_EDGE), ("flat", ~edge, LIMIT_FLAT)):
            dd = d[m]
            r[cls] = dict(n=int(m.sum()), mean_mm=round(1e3 * dd.mean(), 2), p95_mm=round(1e3 * np.percentile(dd, 95), 2),
                          max_mm=round(1e3 * dd.max(), 1), over_limit_pct=round(100 * float((dd > lim).mean()), 2))
        r["hidden_sample_share_pct"] = round(100 * hidden_share, 1)
        r["ai_to_low"] = dict(mean_mm=round(1e3 * d2.mean(), 2), p95_mm=round(1e3 * np.percentile(d2, 95), 2),
                              max_mm=round(1e3 * d2.max(), 1))
        # clusters over the limit (5 cm bins)
        over = ((d > LIMIT_EDGE) & edge) | ((d > LIMIT_FLAT) & ~edge)
        cats = {}
        for pt, dv, e in zip(p[over], d[over], edge[over]):
            q = pt - np.array([0, 0, V.CZ])
            lab = categorize(q, dv, bool(e), key)
            c = cats.setdefault(lab, [0, 0.0, None]); c[0] += 1
            if dv > c[1]: c[1] = dv; c[2] = np.round(q, 3).tolist()
        n_vis = len(p)
        r["categories"] = {k: dict(share_of_visible_pct=round(100 * v[0] / n_vis, 2), max_mm=round(1e3 * v[1], 1), at=v[2])
                           for k, v in sorted(cats.items())}
        for k, v in r["categories"].items():
            print(f"   CAT {key} | {k}: {v['share_of_visible_pct']}% of visible surface, max {v['max_mm']} mm at {v['at']}")
        bins = {}
        for pt, dv, e in zip(p[over], d[over], edge[over]):
            k = tuple(np.floor(pt / 0.05).astype(int))
            b = bins.setdefault(k, [0, 0.0, pt, e]); b[0] += 1
            if dv > b[1]: b[1] = dv; b[2] = pt; b[3] = e
        cl = sorted(bins.values(), key=lambda b: -b[1])
        r["clusters"] = [dict(n=b[0], max_mm=round(1e3 * b[1], 1), at=np.round(b[2] - np.array([0, 0, V.CZ]), 3).tolist(),
                              cls="edge" if b[3] else "flat") for b in cl if b[0] >= 3][:25]
        res[key] = r
        heat[key] = (rtree,)
        print(f"DEV {key}: edge zone mean {r['edge']['mean_mm']} / p95 {r['edge']['p95_mm']} / max {r['edge']['max_mm']} mm "
              f"(> 5 mm: {r['edge']['over_limit_pct']}%); flat mean {r['flat']['mean_mm']} / p95 {r['flat']['p95_mm']} / "
              f"max {r['flat']['max_mm']} mm (> 3 mm: {r['flat']['over_limit_pct']}%); AI->low mean {r['ai_to_low']['mean_mm']} "
              f"p95 {r['ai_to_low']['p95_mm']} max {r['ai_to_low']['max_mm']}")
        for c in r["clusters"][:12]:
            print(f"   over limit: {c['max_mm']} mm {c['cls']} at cradle-local {c['at']} ({c['n']} samples)")
    os.makedirs(SCR, exist_ok=True)
    json.dump(res, open(os.path.join(SCR, "deviation.json"), "w"), indent=1)
    if args and args[0] == "render":
        heatmap(objs, heat)


def heat_color(d):
    """0 -> blue, 3 mm -> green, 5 mm -> yellow, >= 10 mm -> red"""
    stops = [(0.0, (0.10, 0.25, 0.90)), (0.0015, (0.10, 0.60, 0.90)), (0.003, (0.15, 0.80, 0.25)),
             (0.005, (0.95, 0.85, 0.10)), (0.010, (0.90, 0.10, 0.10))]
    if d >= stops[-1][0]: return stops[-1][1]
    for (d0, c0), (d1, c1) in zip(stops, stops[1:]):
        if d <= d1:
            t = (d - d0) / (d1 - d0); return tuple(c0[i] + (c1[i] - c0[i]) * t for i in range(3))
    return stops[-1][1]


def heatmap(objs, heat):
    sc = bpy.context.scene
    for key, (rtree,) in heat.items():
        o = objs[key]
        mod = o.modifiers.new("sub", 'SUBSURF'); mod.subdivision_type = 'SIMPLE'; mod.levels = mod.render_levels = 3
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        o.modifiers.remove(mod)
        attr = me.color_attributes.new("dev", 'FLOAT_COLOR', 'POINT')
        M = o.matrix_world
        for i, v in enumerate(me.vertices):
            w = M @ v.co
            d = rtree.find_nearest(Vector((-w.x, w.z, -w.y)))[3]
            c = heat_color(d); attr.data[i].color = (*c, 1.0)
        me.color_attributes.active_color = attr
        o.data = me
    for n in ("Pad_R_01", "Pad_L_01", "Riser_L_01"): objs[n].hide_render = True
    setup_render(color='VERTEX')
    cam = camera([0, 1.0, V.CZ - 8], [0, 1.0, V.CZ], ortho=3.4)
    shot("cradle_v2_s3_deviation_front.png")
    camera([-2.9, 2.4, V.CZ - 3.2], [0, 0.9, V.CZ]); shot("cradle_v2_s3_deviation_34.png")
    camera([2.9, 2.4, V.CZ + 3.2], [0, 0.9, V.CZ]); shot("cradle_v2_s3_deviation_back34.png")


# --------------------------------------------------------------------------- render helpers


def setup_render(color='OBJECT', size=(2400, 1500)):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 100; sc.display.render_aa = '16'
    sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = color; sh.show_cavity = True
    sh.cavity_type = 'BOTH'; sh.show_object_outline = True; sh.show_shadows = False
    sh.background_type = 'VIEWPORT'; sh.background_color = (0.18, 0.19, 0.21)
    sc.view_settings.view_transform = 'Standard'
    if "RenderFloor" not in bpy.data.objects:
        me = bpy.data.meshes.new("RenderFloor")
        me.from_pydata([(-20, -20, -0.0005), (20, -20, -0.0005), (20, 20, -0.0005), (-20, 20, -0.0005)], [], [(0, 1, 2, 3)])
        f = bpy.data.objects.new("RenderFloor", me); sc.collection.objects.link(f); f.color = (0.42, 0.42, 0.44, 1)
        a = me.color_attributes.new("dev", 'FLOAT_COLOR', 'POINT')
        for d in a.data: d.color = (0.42, 0.42, 0.44, 1)


def camera(loc_spec, look_spec, ortho=None, lens=40):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("cam"); cd.clip_start = 0.01; cd.clip_end = 100
    c = bpy.data.objects.new("cam", cd); sc.collection.objects.link(c)
    c.location = V.to_blender(loc_spec); t = V.to_blender(look_spec)
    c.rotation_euler = (t - c.location).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else: cd.lens = lens
    sc.camera = c
    return c


def shot(fn, folder=RENDERS):
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(folder, fn); bpy.ops.render.render(write_still=True); print("RENDER", fn)


def colours(objs):
    objs["Base_01"].color = (0.34, 0.35, 0.38, 1)
    for n in ("Arm_L_01", "Arm_R_01"): objs[n].color = (0.46, 0.47, 0.51, 1)
    objs["Riser_L_01"].color = (0.40, 0.41, 0.45, 1)
    for n in ("Pad_R_01", "Pad_L_01"): objs[n].color = (1.0, 0.55, 0.05, 1)


def add_wire(objs, thickness=0.0022):
    wires = []
    for name, o in objs.items():
        w = bpy.data.objects.new(o.name + "_wire", o.data)
        bpy.context.scene.collection.objects.link(w)
        w.parent = o.parent; w.matrix_parent_inverse = o.matrix_parent_inverse; w.matrix_basis = o.matrix_basis
        m = w.modifiers.new("Wire", 'WIREFRAME'); m.thickness = thickness; m.use_even_offset = True
        m.use_replace = True; m.offset = 0.7; m.use_boundary = True
        w.color = (0.03, 0.03, 0.03, 1)
        wires.append((o, w))
    return wires


def quick(args):
    objs = open_file(); colours(objs); setup_render(size=(1600, 1000))
    os.makedirs(SCR, exist_ok=True)
    cz = V.CZ
    camera([0, 1.0, cz - 8], [0, 1.0, cz], ortho=3.4); shot("q_front.png", SCR)
    camera([-2.9, 2.4, cz - 3.2], [0, 0.9, cz]); shot("q_34.png", SCR)
    camera([0, 8, cz + 0.001], [0, 0, cz], ortho=3.0); bpy.context.scene.camera.rotation_euler[2] += math.pi; shot("q_top.png", SCR)
    camera([1.2, 1.0, cz - 1.1], [0.42, 0.72, cz], lens=45); shot("q_hinge.png", SCR)
    set_pose(objs, 75); camera([-2.9, 2.4, cz - 3.2], [0, 0.9, cz]); shot("q_release.png", SCR)


# --------------------------------------------------------------------------- clearances


def read_drone():
    parts = {}; cur = None; verts = []; faces = []; off = 0
    for line in open(DRONE_OBJ):
        t = line.split()
        if not t: continue
        if t[0] == 'o':
            if cur: parts[cur] = (np.array(verts), np.array(faces) - off); off += len(verts)
            cur = t[1]; verts = []; faces = []
        elif t[0] == 'v': verts.append([float(a) for a in t[1:4]])
        elif t[0] == 'f': faces.append([int(a) - 1 for a in t[1:4]])
    parts[cur] = (np.array(verts), np.array(faces) - off)
    return parts


def docked_drone():
    """drone meshes in the v2 docking pose (HERO_SPEC §3), spec world"""
    R = json.load(open(os.path.join(CACHE, "analysis.json")))["options"]["A"]
    th = math.radians(R["yaw_deg"]); c, s = math.cos(th), math.sin(th)
    A = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    P0 = np.array([0.0, 2.0, 4.76]); P1 = np.array(R["DroneAI2_new"])
    return {k: ((v - P0) @ A.T + P1, t) for k, (v, t) in read_drone().items() if k != "ScannerGlow"}


def disc_cloud(c, rad, y0, y1, n=48):
    pts = []
    for rr in np.linspace(0, rad, 10):
        for a in np.linspace(0, 2 * math.pi, max(6, int(n * rr / rad)), endpoint=False):
            for y in (y0, y1): pts.append([c[0] + rr * math.cos(a), y, c[2] + rr * math.sin(a)])
    return np.array(pts)


def drone_groups(D):
    G = {}
    for g, ms in (("limbs", ["ArmLeft_low", "ArmRight_low"]), ("engines", ["Engine1_low", "Engline2_low", "Engine3_low", "Engine4_low"]),
                  ("body", ["Body_low", "Ring_low", "Top_low", "ToShoot_low"])):
        G[g] = np.vstack([sample(*D[m], n=8000)[0] for m in ms] + [D[m][0] for m in ms])
    discs = []
    for pn, en in (("Propellor1_low", "Engine1_low"), ("Propellor2_low", "Engline2_low"), ("Propellor3_low", "Engine3_low"), ("Propellor4_low", "Engine4_low")):
        e = D[en][0]; c = (e.min(0) + e.max(0)) / 2; p = D[pn][0]
        discs.append(disc_cloud(c, np.hypot(p[:, 0] - c[0], p[:, 2] - c[2]).max(), p[:, 1].min(), p[:, 1].max()))
    G["props"] = np.vstack(discs)
    return G


def mesh_overlap(va, ta, vb, tb):
    return len(bvh(va, ta).overlap(bvh(vb, tb)))


def clearance(args):
    objs = open_file(); D = docked_drone(); G = drone_groups(D)
    moving = {"arm_L": ["Arm_L_01"], "arm_R": ["Arm_R_01"], "pad_L": ["Pad_L_01"], "pad_R": ["Pad_R_01"], "riser_L": ["Riser_L_01"]}
    angles = list(range(0, 16)) + list(range(20, 76, 5))
    rows = []
    drone_mesh = {k: v for k, v in D.items()}
    base_v, base_t = obj_arrays(objs["Base_01"]); base_tree = bvh(base_v, base_t)
    for deg in angles:
        set_pose(objs, deg)
        row = {"deg": deg}
        arr = {k: [obj_arrays(objs[n]) for n in ns][0] for k, ns in moving.items()}
        trees = {k: bvh(*v) for k, v in arr.items()}
        for g, pts in G.items():
            for k, tr in trees.items():
                row[f"{g}->{k}"] = round(1e3 * float(nearest(tr, pts).min()), 1)
        # intersections drone <-> moving parts
        hits = 0
        for dk, (dv, dt) in drone_mesh.items():
            for k, (v, t) in arr.items():
                hits += mesh_overlap(dv, dt, v, t)
        row["drone_intersections"] = hits
        # arm (with boss) vs base: distance and intersections
        for side in ("L", "R"):
            av, at = arr[f"arm_{side}"]
            ap, _ = sample(av, at, spacing=0.01)
            row[f"arm_{side}->base"] = round(1e3 * float(nearest(base_tree, ap).min()), 1)
            row[f"arm_{side}xbase"] = mesh_overlap(av, at, base_v, base_t)
        allv = np.vstack([v for v, t in arr.values()])
        row["max_y"] = round(float(allv[:, 1].max()), 4); row["min_y"] = round(float(allv[:, 1].min()), 4)
        rows.append(row)
    set_pose(objs, 0)
    # contact: limb underside -> first cradle surface below (docked)
    parts_all = [obj_arrays(objs[n]) for n in PARTS]
    V_ = np.vstack([v for v, t in parts_all]); T_ = []; off = 0
    for v, t in parts_all: T_.append(t + off); off += len(v)
    ctree = bvh(V_, np.vstack(T_))
    ltree = bvh(np.vstack([D["ArmLeft_low"][0], D["ArmRight_low"][0]]),
                np.vstack([D["ArmLeft_low"][1], D["ArmRight_low"][1] + len(D["ArmLeft_low"][0])]))
    bc = (D["Body_low"][0].min(0) + D["Body_low"][0].max(0)) / 2
    contact = {}
    for lab, en in (("front-right limb (Pad_R)", "Engine1_low"), ("back-left limb (Pad_L)", "Engine4_low")):
        e = D[en][0]; ec = (e.min(0) + e.max(0)) / 2
        u = np.array([ec[0] - bc[0], ec[2] - bc[2]]); u /= np.linalg.norm(u); nrm = np.array([-u[1], u[0]])
        gaps = []
        for r in np.linspace(0.40, 0.60, 11):
            for w in np.linspace(-0.045, 0.045, 7):
                x, z = np.array([bc[0], bc[2]]) + u * r + nrm * w
                hu = ltree.ray_cast(Vector((x, 0.5, z)), Vector((0, 1, 0)), 3)
                if hu[0] is None: continue
                hd = ctree.ray_cast(Vector((x, hu[0].y - 1e-4, z)), Vector((0, -1, 0)), 3)
                if hd[0] is not None: gaps.append(hu[0].y - hd[0].y)
        g = np.array(gaps)
        contact[lab] = dict(min_mm=round(1e3 * g.min(), 2), max_mm=round(1e3 * g.max(), 2), n=len(g))
    out = dict(rows=rows, contact=contact)
    keys = [k for k in rows[0] if k != "deg"]
    summ = {}
    for k in keys:
        vals = [(r[k], r["deg"]) for r in rows]
        if k in ("max_y",):
            summ[k] = [r[k] for r in rows if r["deg"] == 75][0]
        else:
            summ[k] = min(vals) if not k.endswith("xbase") and k != "drone_intersections" else max(vals)
    out["docked"] = rows[0]; out["sweep_extremes"] = summ
    json.dump(out, open(os.path.join(SCR, "clearance.json"), "w"), indent=1)
    print("CONTACT", contact)
    print("DOCKED", {k: v for k, v in rows[0].items() if k != "deg"})
    print("SWEEP extremes (value, deg)", summ)


# --------------------------------------------------------------------------- review renders


def drone_objects(lift=0.0):
    """docked drone (live mesh dump) as Blender objects, optional lift in spec y"""
    objs = []
    for name, (v, t) in docked_drone().items():
        v = v + np.array([0, lift, 0])
        me = bpy.data.meshes.new("drone_" + name)
        me.from_pydata([V.to_blender((p[0], p[1], p[2])) for p in v], [], [tuple(int(i) for i in f[::-1]) for f in t])
        me.update()
        o = bpy.data.objects.new("drone_" + name, me); bpy.context.scene.collection.objects.link(o)
        o.color = (0.75, 0.8, 0.85, 1) if "Propellor" in name else (0.95, 0.80, 0.20, 1)
        objs.append(o)
    return objs


def renders(args):
    objs = open_file(); colours(objs); setup_render()
    cz = V.CZ
    views = [("front", dict(loc=[0, 1.0, cz - 8], look=[0, 1.0, cz], ortho=3.4)),
             ("34", dict(loc=[-2.9, 2.4, cz - 3.2], look=[0, 0.9, cz])),
             ("top", dict(loc=[0, 8, cz + 0.001], look=[0, 0, cz], ortho=2.9, spin=True)),
             ("hinge", dict(loc=[1.15, 1.0, cz - 1.05], look=[0.42, 0.72, cz], lens=45))]
    def cam(v):
        c = camera(v["loc"], v["look"], ortho=v.get("ortho"), lens=v.get("lens", 40))
        if v.get("spin"): c.rotation_euler[2] += math.pi
    for name, v in views:
        cam(v); shot(f"cradle_v2_s3_shaded_{name}.png")
    wires = add_wire(objs)
    for name, v in views:
        cam(v); shot(f"cradle_v2_s3_wire_{name}.png")
    for o, w in wires: bpy.data.objects.remove(w)
    # dock and release
    drone = drone_objects()
    cam(views[0][1]); shot("cradle_v2_s3_dock_front.png")
    cam(views[1][1]); shot("cradle_v2_s3_dock_34.png")
    camera([0.2, 2.0, cz - 1.6], [0.45, 1.70, cz], lens=40); shot("cradle_v2_s3_dock_pads.png")
    for o in drone: bpy.data.objects.remove(o)
    set_pose(objs, V.RELEASE_DEG)
    drone = drone_objects(lift=0.5)
    cam(dict(loc=[0, 1.1, cz - 8], look=[0, 1.1, cz], ortho=3.6)); shot("cradle_v2_s3_release_front.png")
    cam(views[1][1]); shot("cradle_v2_s3_release_34.png")


# --------------------------------------------------------------------------- deviation categories (Step 3b)
PIN = (0.385, 0.637)


def _diag(p):
    """distance along the diagonal normal and along-face coordinate, in the point's quadrant (cradle-local x, z)"""
    ax, az = abs(p[0]), abs(p[2])
    return (ax + az) / math.sqrt(2), (ax - az) / math.sqrt(2)


def _rpin(p):
    return math.hypot(abs(p[0]) - PIN[0], p[1] - PIN[1])


# c) AI junk that must not be baked (tested on AI geometry and on low-poly samples)
def _tt_fin(p):
    a = math.degrees(math.atan2(abs(p[2]), abs(p[0])))
    return 0.25 < p[1] < 0.30 and 0.49 < math.hypot(p[0], p[2]) < 0.63 and 50 < a < 68


JUNK = {    # (test, applies to "base" / "arm")
    "T1 diagonal faces: openings into the hollow shell + bowing": (lambda p: _diag(p)[0] > 1.00 and p[1] < 0.165 and abs(_diag(p)[1]) < 0.36, "base"),
    "T2 diagonal faces: bowed ~20 mm": (lambda p: 0.78 < _diag(p)[0] < 0.90 and 0.20 < p[1] < 0.28 and abs(_diag(p)[1]) < 0.36, "base"),
    "turntable rim: thin broken radial fins (hollow shell)": (_tt_fin, "base"),
    "turntable rim notches (read as damage; owner decision 3c)": (lambda p: 0.25 < p[1] < 0.34 and 0.47 < math.hypot(p[0], p[2]) < 0.53
        and any(abs((math.degrees(math.atan2(p[2], p[0])) - c + 180) % 360 - 180) < 15 for c in (35, 145, 215, 325)), "base"),
    "old arm-root fins / shoe under the new boss": (lambda p: (_rpin(p) < 0.20 and 0.60 < p[1] < 0.86)
                                                    or (0.15 < abs(p[0]) < 0.34 and 0.735 < p[1] < 0.80), "arm"),
    "splitter cut faces on the hinge beam top": (lambda p: 0.20 < abs(p[0]) < 0.36 and 0.72 < p[1] < 0.77 and abs(p[2]) < 0.16, "base"),
    "arm front/back asymmetric recess (z- side only)": (lambda p: 0.62 < abs(p[0]) < 0.68 and 1.28 < p[1] < 1.40 and p[2] < -0.12, "arm"),
}
# b) deliberate design differences (low-poly samples)
DESIGN = {
    "root boss replaces the AI root": lambda p, part: part != "Base_01" and _rpin(p) < 0.175 and p[1] < 0.86,
    "drum raised bands (13 mm) not modelled - boss slides over the drum": lambda p, part: part == "Base_01" and 0.10 < _rpin(p) < 0.15 and 0.06 < abs(p[2]) < 0.17 and abs(p[0]) > 0.40,
}
# a) features modelled as geometry in Step 3 / 3b (residual deviation reported)
MODELLED = {
    "tier-1 top: band / slope / sunken ring / trays": lambda p, part: part == "Base_01" and 0.155 < p[1] < 0.21 and 0.80 < math.hypot(p[0], p[2]) < 1.22,
    "arm inner channel + rails": lambda p, part: part != "Base_01" and abs(p[2]) < 0.075 and 0.97 < p[1] < 1.57 and abs(p[0]) < 0.48,
    "arm root full depth": lambda p, part: part != "Base_01" and 0.74 < p[1] < 0.92 and abs(p[2]) > 0.09 and abs(p[0]) < 0.55,
    "hinge-beam fillet": lambda p, part: part == "Base_01" and 0.14 < abs(p[0]) < 0.33 and 0.43 < p[1] < 0.51 and abs(p[2]) < 0.07,
}


def categorize(p, d, edge, part):
    """returns category label for one over-limit sample (cradle-local spec p)"""
    kind = "base" if part == "Base_01" else "arm"
    for k, f in DESIGN.items():                       # the boss surface counts as design even where AI fins lay under it
        if f(p, part): return "b: " + k
    for k, (f, where) in JUNK.items():
        if where == kind and f(p): return "c: " + k
    for k, f in DESIGN.items():
        if f(p, part): return "b: " + k
    for k, f in MODELLED.items():
        if f(p, part): return "a: " + k
    if d <= 0.015:
        return "b: chamfer vs AI rounded edge (<= 15 mm)" if edge else "detail <= 15 mm (normal map by rule)"
    return "other > 15 mm"


def bake_junk(args):
    """AI high-poly with the c) zones in red -> Renders/cradle_v2_s3b_bake_junk.png"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ref = ai_ref()
    for key, (v, t) in ref.items():
        loc = v - np.array([0, 0, V.CZ])
        kind = "base" if key == "Base_01" else "arm"
        junk = np.array([any(f(q) for f, where in JUNK.values() if where == kind) for q in loc])
        me = bpy.data.meshes.new("AI_" + key)
        bv = np.column_stack((-v[:, 0], -v[:, 2], v[:, 1]))
        me.vertices.add(len(bv)); me.vertices.foreach_set("co", bv.ravel())
        tt = t[:, ::-1]
        me.loops.add(tt.size); me.loops.foreach_set("vertex_index", tt.ravel())
        me.polygons.add(len(tt)); me.polygons.foreach_set("loop_start", np.arange(0, tt.size, 3)); me.polygons.foreach_set("loop_total", np.full(len(tt), 3))
        me.update(); me.validate()
        col = me.color_attributes.new("dev", 'FLOAT_COLOR', 'POINT')
        c = np.tile(np.array([0.55, 0.56, 0.60, 1.0]), (len(bv), 1)); c[junk] = (0.95, 0.12, 0.10, 1.0)
        col.data.foreach_set("color", c.ravel())
        me.color_attributes.active_color = col
        o = bpy.data.objects.new("AI_" + key, me); bpy.context.scene.collection.objects.link(o)
        print("JUNK", key, int(junk.sum()), "of", len(junk), "vertices")
    setup_render(color='VERTEX')
    cz = V.CZ
    camera([-2.3, 1.7, cz - 2.5], [0, 0.55, cz], lens=38); shot("cradle_v2_s3b_bake_junk.png")
    camera([2.3, 1.2, cz + 2.4], [0, 0.45, cz], lens=38); shot("cradle_v2_s3b_bake_junk_back.png")
    camera([0.9, 0.95, cz - 1.2], [0.38, 0.72, cz], lens=40); shot("cradle_v2_s3b_bake_junk_root.png")



def renders_3b(args):
    """cradle_v2_s3b_*: shaded + wire (34, top, corner pocket, turntable notch)"""
    objs = open_file(); colours(objs); setup_render()
    cz = V.CZ
    views = [("34", dict(loc=[-2.9, 2.4, cz - 3.2], look=[0, 0.9, cz])),
             ("top", dict(loc=[0, 8, cz + 0.001], look=[0, 0, cz], ortho=2.9, spin=True)),
             ("pocket", dict(loc=[0.95, 0.95, cz - 1.55], look=[0.45, 0.18, cz - 0.85], lens=40)),
             ("notch", dict(loc=[0.66, 0.66, cz - 0.95], look=[0.40, 0.31, cz - 0.28], lens=45))]
    def cam(v):
        c = camera(v["loc"], v["look"], ortho=v.get("ortho"), lens=v.get("lens", 40))
        if v.get("spin"): c.rotation_euler[2] += math.pi
    for name, v in views:
        cam(v); shot(f"cradle_v2_s3b_shaded_{name}.png")
    wires = add_wire(objs)
    for name, v in views:
        cam(v); shot(f"cradle_v2_s3b_wire_{name}.png")
    camera([-0.15, 1.30, cz - 0.95], [0.40, 1.15, cz], lens=45); shot("cradle_v2_s3b_wire_channel.png")



def renders_3c(args):
    """cradle_v2_s3c_*: wire close-ups (turntable at the s3b notch angle, a tier-1 corner) and a hole check
    render: backface culling on, bright red background, no floor"""
    objs = open_file(); colours(objs); setup_render()
    cz = V.CZ
    wires = add_wire(objs)
    camera([0.66, 0.66, cz - 0.95], [0.40, 0.31, cz - 0.28], lens=45); shot("cradle_v2_s3c_wire_turntable.png")
    camera([0.95, 0.95, cz - 1.55], [0.45, 0.18, cz - 0.85], lens=40); shot("cradle_v2_s3c_wire_corner.png")
    camera([1.35, 0.85, cz + 0.2], [0.93, 0.18, cz + 0.40], lens=40); shot("cradle_v2_s3c_wire_corner_x.png")
    camera([1.0, 1.0, cz - 0.9], [0.40, 0.62, cz], lens=45); shot("cradle_v2_s3c_wire_beam_drum.png")
    for o, w in wires: bpy.data.objects.remove(w)
    bpy.data.objects.remove(bpy.data.objects["RenderFloor"])
    sh = bpy.context.scene.display.shading
    sh.show_backface_culling = True; sh.background_color = (1.0, 0.0, 0.0)
    for name, loc, look, lens in (("front", [0, 1.2, cz - 4.5], [0, 0.6, cz], 35), ("34", [-2.9, 2.4, cz - 3.2], [0, 0.9, cz], 40),
                                  ("back34", [2.9, 2.0, cz + 3.2], [0, 0.8, cz], 40), ("top", [0, 6.0, cz + 0.01], [0, 0, cz], 30),
                                  ("low", [-2.2, 0.35, cz - 2.2], [0, 0.45, cz], 35)):
        camera(loc, look, lens=lens); shot(f"cradle_v2_s3c_holes_{name}.png")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["topo"]
    {"topo": topo, "deviation": deviation, "quick": quick, "clearance": clearance, "renders": renders, "bake_junk": bake_junk, "renders_3b": renders_3b, "renders_3c": renders_3c}.get(argv[0], lambda a: print("unknown stage"))(argv[1:])
