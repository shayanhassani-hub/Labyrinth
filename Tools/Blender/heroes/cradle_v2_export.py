"""
Cradle v2 (Hero 01) FBX export for Unity, hero mode (EXPORT_CONTRACT "Hero mode"), and a re-import check.
Step C-T2 (2026-11-13), on the gate_export.py pattern.

  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_export.py -- [export] [check]      (default: both)

export  opens the bake file (cradle_v2_bake.BAKE, never saved). Source = the export-identical triangulated lows
        <Part>_bakelow (the meshes the 6g maps and the C-T1b textures were baked on; HERO_SPEC §3 Step 6g lesson), so
        the Unity mesh, its UVs and its tangent basis are exactly the baked ones. Per part (HERO_SPEC §3 "Parts"):
          LAB_HERO_Cradle_Base_01      origin floor centre (0, 0, 4.69)
          LAB_HERO_Cradle_Arm_R_01     origin on the right pin axis (+0.385, 0.637, 4.69)
          LAB_HERO_Cradle_Arm_L_01     Arm_R mirrored in x (real mirrored mesh: winding reversed, corner normals
                                       mirrored, the same UVs), origin (-0.385, 0.637, 4.69)
          LAB_HERO_Cradle_Pad_01       one mesh for both pads, origin its own bottom centre
          LAB_HERO_Cradle_Riser_L_01   origin its own bottom centre
        each at identity with ONE material slot, written with env_kit_generator.export_fbx(mode="hero") (triangulation
        of an already triangulated mesh is a no-op; custom normals carried; MikkTSpace tangents) to
        Assets/Environment/Heroes/Cradle/. The report (Temp/claude/cradle/export/export.json) holds the part origins
        and the pads' / riser's local positions on their arms (the Unity builder's constants).
check   re-imports every FBX into an empty scene: triangle count (= the bake low = HERO_SPEC), one mesh, one material
        slot, root identity, local bounds and origin (Unity axes), custom normals (every imported corner matches a
        corner of the export copy at the same position), Arm_L = Arm_R mirrored, UV count.
"""
import bpy
import json
import math
import os
import sys
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import cradle_v2 as V                                     # noqa: E402
import cradle_v2_bake as B                                # noqa: E402
import cradle_v2_bake_test as T                           # noqa: E402
import env_kit_generator as K                             # noqa: E402

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(PROJ, "Assets", "Environment", "Heroes", "Cradle")
SCR = os.path.join(PROJ, "Temp", "claude", "cradle", "export")
REPORT = os.path.join(SCR, "export.json")
HERO = "LAB_HERO_Cradle_"
CZ = V.CZ
PIVOT = (0.385, 0.637)                                    # HERO_SPEC §3 Pivots: build value x +-0.385, y 0.637, axis || Z
# part -> (bake low, origin rule, mirrored)
PARTS = {
    "Base_01": ("Base", (0.0, 0.0, CZ), False),
    "Arm_R_01": ("Arm_R", (PIVOT[0], PIVOT[1], CZ), False),
    "Arm_L_01": ("Arm_R", (-PIVOT[0], PIVOT[1], CZ), True),
    "Pad_01": ("Pad", "bottom", False),
    "Riser_L_01": ("Riser", "bottom", False),
}
TRIS = {"Base_01": 2800, "Arm_R_01": 500, "Arm_L_01": 500, "Pad_01": 38, "Riser_L_01": 38}   # HERO_SPEC §3 Step 6c


def spec(v):
    """Blender -> Unity (EXPORT_CONTRACT: spec x = -Bx, y = Bz, z = -By)"""
    v = np.asarray(v, float).reshape(-1, 3)
    return np.column_stack((-v[:, 0], v[:, 2], -v[:, 1]))


def to_blender(p):
    return Vector((-p[0], -p[2], p[1]))


def world_mesh(o, name):
    """copy of o's mesh in world space; the bake lows sit at translations only (asserted), so normals are unchanged"""
    m = o.matrix_world
    assert np.abs(np.array(m.to_3x3()) - np.eye(3)).max() < 1e-9, o.name
    me = o.data.copy(); me.name = name
    me.transform(Matrix.Translation(m.translation))
    return me


def corners(me):
    me.calc_loop_triangles()
    P = np.array([me.vertices[me.loops[li].vertex_index].co[:] for t in me.loop_triangles for li in t.loops])
    N = np.array([me.corner_normals[li].vector[:] for t in me.loop_triangles for li in t.loops])
    return P, N


def export():
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    for o in bpy.data.objects: o.hide_render = True
    os.makedirs(OUT, exist_ok=True); os.makedirs(SCR, exist_ok=True)
    lows = {k: bpy.data.objects[f"{k}_bakelow"] for k in ("Base", "Arm_R", "Pad", "Riser")}
    mat = bpy.data.materials.get("M_LAB_HERO_Cradle") or bpy.data.materials.new("M_LAB_HERO_Cradle")
    rep = {}
    for n, (src, rule, mirrored) in PARTS.items():
        me = world_mesh(lows[src], f"{HERO}{n}_w")
        if mirrored:                                       # spec x -> -x  ==  Blender x -> -x
            me2 = T.mirror_display(me, f"{HERO}{n}_m"); bpy.data.meshes.remove(me); me = me2
        V_ = np.array([v.co[:] for v in me.vertices]); S = spec(V_)
        if rule == "bottom":                                # own bottom centre (spec)
            lo, hi = S.min(0), S.max(0)
            org = np.array(((lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2))
        else:
            org = np.array(rule, float)
        me.transform(Matrix.Translation(-to_blender(org)))
        me.materials.clear(); me.materials.append(mat)
        for p in me.polygons: p.material_index = 0
        o = bpy.data.objects.new(f"{HERO}{n}", me); bpy.context.scene.collection.objects.link(o)
        path = K.export_fbx(o, OUT, f"{HERO}{n}.fbx", mode="hero")
        ref = K.triangulated_export_copy(o)                 # exactly what export_fbx wrote
        P, N = corners(ref.data)
        np.savez(os.path.join(SCR, f"ref_{n}.npz"), P=P, N=N)
        rep[n] = dict(fbx=os.path.relpath(path, PROJ).replace("\\", "/"), tris=len(ref.data.loop_triangles),
                      origin=[round(float(c), 5) for c in org],
                      bounds_local=[np.round(S.min(0) - org, 5).tolist(), np.round(S.max(0) - org, 5).tolist()])
        bpy.data.objects.remove(ref, do_unlink=True); bpy.data.objects.remove(o, do_unlink=True)
        print(f"EXPORTED {rep[n]['fbx']}: {rep[n]['tris']} tris, origin {rep[n]['origin']}, "
              f"local bounds {rep[n]['bounds_local']}")
    # children on the arms (Unity local = world offset: the arms are at rotation 0 in the closed pose)
    ar, al = np.array(rep["Arm_R_01"]["origin"]), np.array(rep["Arm_L_01"]["origin"])
    pad_r = np.array(rep["Pad_01"]["origin"]); riser = np.array(rep["Riser_L_01"]["origin"])
    riser_top = riser[1] + rep["Riser_L_01"]["bounds_local"][1][1]
    pad_l = np.array((-pad_r[0], riser_top, pad_r[2]))
    rep["children"] = {"Pad_R_on_Arm_R": np.round(pad_r - ar, 5).tolist(), "Pad_L_on_Arm_L": np.round(pad_l - al, 5).tolist(),
                       "Riser_L_on_Arm_L": np.round(riser - al, 5).tolist(),
                       "pad_r_world": np.round(pad_r, 5).tolist(), "pad_l_world": np.round(pad_l, 5).tolist(),
                       "riser_world": np.round(riser, 5).tolist()}
    print(f"CHILDREN {rep['children']}")
    json.dump(rep, open(REPORT, "w"), indent=1)


def check():
    ok_all = True
    rep = json.load(open(REPORT))
    imported = {}
    for n in PARTS:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=os.path.join(PROJ, rep[n]["fbx"]), axis_forward='-Z', axis_up='Y',
                                 bake_space_transform=True, use_custom_normals=True)
        objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        if len(objs) != 1:
            print(f"FAIL {n}: {len(objs)} mesh objects in the FBX"); ok_all = False; continue
        o = objs[0]; me = o.data; me.calc_loop_triangles()
        tris = len(me.loop_triangles)
        ident = (o.location.length < 1e-6 and max(abs(a) for a in o.rotation_euler) < 1e-6
                 and (o.scale - Vector((1, 1, 1))).length < 1e-6)
        ok = tris == rep[n]["tris"] == TRIS[n]; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {n}: {tris} tris (export copy {rep[n]['tris']}, HERO_SPEC {TRIS[n]}); "
              f"node '{o.name}', mesh '{me.name}'")
        ok = ident and len(me.materials) <= 1 and o.name == f"{HERO}{n}"; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {n}: root transform identity, material slots {len(me.materials)}, node name = asset ID")
        S = spec(np.array([v.co[:] for v in me.vertices])); lo, hi = S.min(0), S.max(0)
        ok = np.allclose(lo, rep[n]["bounds_local"][0], atol=2e-4) and np.allclose(hi, rep[n]["bounds_local"][1], atol=2e-4)
        ok_all &= ok
        org = np.array(rep[n]["origin"])
        print(f"{'PASS' if ok else 'FAIL'} {n}: local bounds (Unity) {np.round(lo, 4).tolist()} .. {np.round(hi, 4).tolist()} "
              f"= export; origin {org.tolist()} -> world {np.round(lo + org, 3).tolist()} .. {np.round(hi + org, 3).tolist()}")
        ref = np.load(os.path.join(SCR, f"ref_{n}.npz"))
        P, Nn = corners(me)
        key = lambda p: tuple(np.round(p, 4))
        table = {}
        for p, nn in zip(ref["P"], ref["N"]): table.setdefault(key(p), []).append(nn)
        worst = 0.0; miss = 0
        for p, nn in zip(P, Nn):
            c = table.get(key(p))
            if c is None: miss += 1; continue
            worst = max(worst, min(math.degrees(math.acos(np.clip(np.dot(nn, q) / (np.linalg.norm(nn) * np.linalg.norm(q)), -1, 1))) for q in c))
        ok = miss == 0 and worst < 0.5; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {n}: custom normals, {len(P)} corners, {miss} without a matching position, "
              f"worst normal difference {worst:.3f} deg (< 0.5)")
        ok = len(me.uv_layers) == 1; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {n}: UV maps {[u.name for u in me.uv_layers]}, vertices {len(me.vertices)}")
        uv = me.uv_layers[0].data if me.uv_layers else None
        imported[n] = dict(S=S + org, P=spec(P) + org, N=spec(Nn),
                           UV=np.array([uv[li].uv[:] for t in me.loop_triangles for li in t.loops]) if uv else None)
    # Arm_L = Arm_R mirrored (world, Unity x -> -x): positions, normals, UVs per corner
    if "Arm_R_01" in imported and "Arm_L_01" in imported:
        r, l = imported["Arm_R_01"], imported["Arm_L_01"]
        key = lambda p: tuple(np.round(p, 4))
        table = {}
        for p, nn, u in zip(r["P"] * (-1, 1, 1), r["N"] * (-1, 1, 1), r["UV"]): table.setdefault(key(p), []).append((nn, u))
        worst_n = worst_uv = 0.0; miss = 0
        for p, nn, u in zip(l["P"], l["N"], l["UV"]):
            c = table.get(key(p))
            if c is None: miss += 1; continue
            best = min(c, key=lambda q: np.linalg.norm(q[0] - nn) + np.linalg.norm(q[1] - u))
            worst_n = max(worst_n, float(np.linalg.norm(best[0] - nn))); worst_uv = max(worst_uv, float(np.abs(best[1] - u).max()))
        deg = math.degrees(2 * math.asin(min(worst_n / 2, 1.0)))
        ok = miss == 0 and deg < 0.5 and worst_uv < 1e-5; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} Arm_L = Arm_R mirrored in x: {len(l['P'])} corners, {miss} unmatched, worst normal "
              f"{deg:.3f} deg (< 0.5, FBX float precision), worst UV {worst_uv:.1e}")
    print("RESULT: PASS" if ok_all else "RESULT: FAIL")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    stages = argv or ["export", "check"]
    if "export" in stages: export()
    if "check" in stages: check()
