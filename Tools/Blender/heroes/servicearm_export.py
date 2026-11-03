"""
ServiceArm (Hero 01b) FBX export for Unity, hero mode (EXPORT_CONTRACT "Hero mode"), and a re-import check.
Same procedure as gate_export.py.

  blender -b --factory-startup -P Tools/Blender/heroes/servicearm_export.py -- [export] [check]      (default: both)

export  opens the review file (servicearm.SAVE, never saved) and for each part writes
        Assets/Environment/Heroes/ServiceArm/LAB_HERO_ServiceArm_<Part>_01.fbx via env_kit_generator.export_fbx(
        mode="hero"): triangulated copy (BEAUTY) with the corner normals carried over, custom normals, MikkTSpace
        tangents, the verified axis / scale settings. Each part is exported at identity (its mesh is already local to
        its hinge, modelled in the stowed pose) with ONE material slot (the five review slots only drive the bake).
check   re-imports every FBX into an empty scene: triangle count (export copy = the build table), one slot, root
        transform identity, local bounds (Unity axes), custom normals (every imported corner matches the export copy),
        UV map present; and the hierarchy numbers ServiceArmBuilder.cs uses (local hinge offsets) against
        servicearm_kin.
"""
import bpy
import json
import math
import os
import sys
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import servicearm as S                                   # noqa: E402
import servicearm_kin as KIN                             # noqa: E402
import env_kit_generator as K                            # noqa: E402

PROJ = KIN.PROJ
OUT = os.path.join(PROJ, "Assets", "Environment", "Heroes", "ServiceArm")
PARTS = list(KIN.PARTS)
TRIS = {"Mount": 420, "Turret": 936, "UpperArm": 1628, "Forearm": 1425, "Wrist": 564, "ToolHead": 272}   # BUILD.md H1b
REPORT = os.path.join(PROJ, "Temp", "claude", "servicearm", "export.json")
# local positions ServiceArmBuilder.cs uses (Unity, parent space) -- must equal the kinematic chain
BUILDER_LOCAL = {"Mount": (0.0, 4.00, 5.30), "Turret": (0.0, -0.07, 0.0), "UpperArm": (0.0, -0.16, 0.0),
                 "Forearm": (0.12, 0.0, 1.00), "Wrist": (0.10, 0.0, -0.90), "ToolHead": (0.0, 0.0, -0.078)}


def spec(v):
    return np.column_stack((-v[:, 0], v[:, 2], -v[:, 1]))


def export():
    bpy.ops.wm.open_mainfile(filepath=S.SAVE)
    os.makedirs(OUT, exist_ok=True); os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    rep = {}
    for n in PARTS:
        src = bpy.data.objects[f"{S.HERO}_{n}_01"]
        me = src.data.copy(); me.name = src.data.name + "_exp"
        for p in me.polygons: p.material_index = 0
        keep = me.materials[0] if len(me.materials) else None
        me.materials.clear()
        if keep is not None: me.materials.append(keep)
        o = bpy.data.objects.new(src.name + "_exp", me); bpy.context.scene.collection.objects.link(o)
        name = src.name; src.name = name + "_review"; o.name = name
        path = K.export_fbx(o, OUT, f"{name}.fbx", mode="hero")
        ref = K.triangulated_export_copy(o)
        ref.data.calc_loop_triangles()
        P = np.array([ref.data.vertices[ref.data.loops[li].vertex_index].co[:] for t in ref.data.loop_triangles for li in t.loops])
        Nn = np.array([ref.data.corner_normals[li].vector[:] for t in ref.data.loop_triangles for li in t.loops])
        np.savez(os.path.join(os.path.dirname(REPORT), f"ref_{n}.npz"), P=P, N=Nn)
        rep[n] = dict(fbx=os.path.relpath(path, PROJ), tris=len(ref.data.loop_triangles))
        bpy.data.objects.remove(ref, do_unlink=True)
        bpy.data.objects.remove(o, do_unlink=True); src.name = name
        print(f"EXPORTED {rep[n]['fbx']}: {rep[n]['tris']} tris")
    json.dump(rep, open(REPORT, "w"), indent=1)


def check():
    ok_all = True
    rep = json.load(open(REPORT))
    for n in PARTS:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        path = os.path.join(PROJ, rep[n]["fbx"])
        bpy.ops.import_scene.fbx(filepath=path, axis_forward='-Z', axis_up='Y', bake_space_transform=True,
                                 use_custom_normals=True)
        objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        if len(objs) != 1:
            print(f"FAIL {n}: {len(objs)} mesh objects in the FBX"); ok_all = False; continue
        o = objs[0]; me = o.data; me.calc_loop_triangles()
        tris = len(me.loop_triangles)
        ident = (o.location.length < 1e-6 and max(abs(a) for a in o.rotation_euler) < 1e-6
                 and (o.scale - Vector((1, 1, 1))).length < 1e-6)
        ok = tris == rep[n]["tris"] == TRIS[n]
        ok_all &= ok and ident and len(me.materials) <= 1 and len(me.uv_layers) == 1
        print(f"{'PASS' if ok else 'FAIL'} {n}: {tris} tris (export copy {rep[n]['tris']}, build table {TRIS[n]}); "
              f"node '{o.name}', mesh '{me.name}'")
        print(f"{'PASS' if ident else 'FAIL'} {n}: root transform identity; material slots {len(me.materials)}; "
              f"UV maps {[u.name for u in me.uv_layers]}")
        V = np.array([v.co[:] for v in me.vertices]); Sv = spec(V)
        print(f"INFO {n}: local bounds (Unity) {np.round(Sv.min(0), 4).tolist()} .. {np.round(Sv.max(0), 4).tolist()}")
        ref = np.load(os.path.join(os.path.dirname(REPORT), f"ref_{n}.npz"))
        P = np.array([me.vertices[me.loops[li].vertex_index].co[:] for t in me.loop_triangles for li in t.loops])
        Nn = np.array([me.corner_normals[li].vector[:] for t in me.loop_triangles for li in t.loops])
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
    # hierarchy numbers in the builder = kinematic chain
    for n in PARTS:
        ok = np.allclose(BUILDER_LOCAL[n], KIN.local_position(n), atol=1e-6); ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {n}: builder local position {BUILDER_LOCAL[n]} = chain {tuple(round(x, 4) for x in KIN.local_position(n))}")
    print("RESULT: PASS" if ok_all else "RESULT: FAIL")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    stages = argv or ["export", "check"]
    if "export" in stages: export()
    if "check" in stages: check()
