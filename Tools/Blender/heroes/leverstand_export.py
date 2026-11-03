"""
LeverStand (Hero 02b) FBX export for Unity, hero mode (EXPORT_CONTRACT "Hero mode"), and a re-import check.

  blender -b --factory-startup -P Tools/Blender/heroes/leverstand_export.py -- [export] [check]      (default: both)

export  opens the review file (leverstand.SAVE, never saved) and writes for each part
        Assets/Environment/Heroes/LeverStand/LAB_HERO_LeverStand_<Part>_01.fbx via env_kit_generator.export_fbx(
        mode="hero"): triangulated copy (BEAUTY) with the corner normals carried over, custom normals, MikkTSpace
        tangents, the verified axis/scale settings. Each part is exported at identity (its mesh is local to its origin,
        the lever UPRIGHT) with ONE material slot (one draw per part; the seven review slots only drive the bake).
check   re-imports every FBX into an empty scene: triangle count (= export copy = TRIS), one slot, root transform
        identity, local bounds (Unity axes), origin (review file = ORIGIN), custom normals (every imported corner
        matches a corner of the export copy).
Origins are STAND-LOCAL (the builder places them under HERO_LeverStand at world (0.85, 0, 0.60), yaw 180).
"""
import bpy
import json
import math
import os
import sys
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import leverstand as L                                   # noqa: E402
import env_kit_generator as K                            # noqa: E402

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(PROJ, "Assets", "Environment", "Heroes", "LeverStand")
PARTS = ["Body_01", "Lever_01", "Lamp_01"]
ORIGIN = {"Body_01": (0.0, 0.0, 0.0), "Lever_01": L.HINGE, "Lamp_01": L.lamp_origin()}
REPORT = os.path.join(PROJ, "Temp", "claude", "leverstand", "export.json")


def spec(v):
    return np.column_stack((-v[:, 0], v[:, 2], -v[:, 1]))


def export():
    bpy.ops.wm.open_mainfile(filepath=L.SAVE)
    os.makedirs(OUT, exist_ok=True); os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    rep = {}
    for n in PARTS:
        src = bpy.data.objects[f"{L.HERO}_{n}"]
        world_origin = tuple(src.matrix_world.translation)
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
        rep[n] = dict(fbx=os.path.relpath(path, PROJ), tris=len(ref.data.loop_triangles), world_origin_blender=world_origin)
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
        ok = tris == rep[n]["tris"]
        ok_all &= ok and ident and len(me.materials) <= 1
        print(f"{'PASS' if ok else 'FAIL'} {n}: {tris} tris (export copy {rep[n]['tris']}); node '{o.name}', mesh '{me.name}'")
        print(f"{'PASS' if ident else 'FAIL'} {n}: root transform identity; material slots {len(me.materials)}")
        V = np.array([v.co[:] for v in me.vertices]); S = spec(V)
        lo, hi = S.min(0), S.max(0); org = np.array(ORIGIN[n])
        print(f"INFO {n}: local bounds (Unity) {np.round(lo, 4).tolist()} .. {np.round(hi, 4).tolist()}; "
              f"stand-local box {np.round(lo + org, 3).tolist()} .. {np.round(hi + org, 3).tolist()}")
        po = spec(np.array(rep[n]["world_origin_blender"])[None])[0]
        same = np.allclose(po, org, atol=1e-4)
        ok_all &= same
        print(f"{'PASS' if same else 'FAIL'} {n}: review-file origin {np.round(po, 4).tolist()} = builder origin "
              f"{np.round(org, 4).tolist()}")
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
        ok = miss == 0 and worst < 0.5
        ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {n}: custom normals, {len(P)} corners, {miss} without a matching position, "
              f"worst normal difference {worst:.3f} deg (< 0.5)")
        print(f"INFO {n}: UV maps {[u.name for u in me.uv_layers]}, vertex count {len(me.vertices)}")
    print("RESULT: PASS" if ok_all else "RESULT: FAIL")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    stages = argv or ["export", "check"]
    if "export" in stages: export()
    if "check" in stages: check()
