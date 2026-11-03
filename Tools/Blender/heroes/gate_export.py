"""
Gate (Hero 03) FBX export for Unity, hero mode (EXPORT_CONTRACT "Hero mode"), and a re-import check.

  blender -b --factory-startup -P Tools/Blender/heroes/gate_export.py -- [export] [check]      (default: both)

export  opens the review file (gate.SAVE, never saved), and for each part writes
        Assets/Environment/Heroes/Gate/LAB_HERO_Gate_<Part>_01.fbx via env_kit_generator.export_fbx(mode="hero"):
        triangulated copy (BEAUTY) with the corner normals carried over, custom normals ("Normals Only"),
        MikkTSpace tangents, the verified axis/scale settings. The part object is exported at identity (its mesh is
        already local to the part origin, HERO_SPEC §7), with ONE material slot: the six slots of the review file only
        drive the texture bake, and in Unity one slot = one submesh = one draw call (one texture set per hero).
check   re-imports every FBX into an empty scene and reports per part: triangle count against the export copy and
        HERO_SPEC §7, single material slot, root transform identity, local bounds (Unity axes) and the origin
        (bounds + HERO_SPEC origin = the part's world box), and the custom normals (every imported corner normal
        matches a corner of the export copy at the same position).
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
import gate as G                                         # noqa: E402
import env_kit_generator as K                            # noqa: E402

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(PROJ, "Assets", "Environment", "Heroes", "Gate")
PARTS = ["Leaf_01", "Rail_01", "ButtonPanel_01", "Button_01"]
TRIS = {"Leaf_01": 1048, "Rail_01": 272, "ButtonPanel_01": 298, "Button_01": 118}          # HERO_SPEC §7
ORIGIN = {"Leaf_01": (-0.15, 0.010, 7.91), "Rail_01": (-1.80, 2.475, 8.00),               # HERO_SPEC §7 (Unity)
          "ButtonPanel_01": (-2.00, 1.20, 8.70), "Button_01": (-1.893, 1.235, 8.70)}
REPORT = os.path.join(PROJ, "Temp", "claude", "gate", "export.json")


def spec(v):
    """Blender -> Unity (EXPORT_CONTRACT: spec x = -Bx, y = Bz, z = -By)"""
    return np.column_stack((-v[:, 0], v[:, 2], -v[:, 1]))


def export():
    bpy.ops.wm.open_mainfile(filepath=G.SAVE)
    os.makedirs(OUT, exist_ok=True)
    rep = {}
    for n in PARTS:
        src = bpy.data.objects[f"{G.HERO}_{n}"]
        world_origin = tuple(src.matrix_world.translation)
        # export copy: same mesh data copied, identity transform, one material slot
        me = src.data.copy(); me.name = src.data.name + "_exp"
        for p in me.polygons: p.material_index = 0
        keep = me.materials[0] if len(me.materials) else None
        me.materials.clear()
        if keep is not None: me.materials.append(keep)
        o = bpy.data.objects.new(src.name + "_exp", me); bpy.context.scene.collection.objects.link(o)
        name = src.name; src.name = name + "_review"; o.name = name
        path = K.export_fbx(o, OUT, f"{name}.fbx", mode="hero")
        # reference corner data of exactly what was written (triangulated copy, same function as the exporter)
        ref = K.triangulated_export_copy(o)
        ref.data.calc_loop_triangles()
        P = np.array([ref.data.vertices[ref.data.loops[li].vertex_index].co[:] for t in ref.data.loop_triangles for li in t.loops])
        Nn = np.array([ref.data.corner_normals[li].vector[:] for t in ref.data.loop_triangles for li in t.loops])
        os.makedirs(os.path.dirname(REPORT), exist_ok=True)
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
        ok = tris == rep[n]["tris"] == TRIS[n]
        ok_all &= ok and ident and len(me.materials) <= 1
        print(f"{'PASS' if ok else 'FAIL'} {n}: {tris} tris (export copy {rep[n]['tris']}, HERO_SPEC {TRIS[n]}); "
              f"node '{o.name}', mesh '{me.name}'")
        print(f"{'PASS' if ident else 'FAIL'} {n}: root transform identity; material slots {len(me.materials)}")
        V = np.array([v.co[:] for v in me.vertices]); S = spec(V)
        lo, hi = S.min(0), S.max(0); org = np.array(ORIGIN[n])
        print(f"INFO {n}: local bounds (Unity) {np.round(lo, 4).tolist()} .. {np.round(hi, 4).tolist()}; "
              f"world with the HERO_SPEC origin {np.round(lo + org, 3).tolist()} .. {np.round(hi + org, 3).tolist()}")
        bo = np.array(rep[n]["world_origin_blender"])[None]
        po = spec(bo)[0]
        same = np.allclose(po, org, atol=1e-4)
        ok_all &= same
        print(f"{'PASS' if same else 'FAIL'} {n}: review-file origin {np.round(po, 4).tolist()} = HERO_SPEC origin {org.tolist()}")
        # custom normals: imported corners vs the export copy's corners (position + normal)
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
        uv = me.uv_layers.active
        print(f"INFO {n}: UV maps {[u.name for u in me.uv_layers]}, vertex count {len(me.vertices)}")
    print("RESULT: PASS" if ok_all else "RESULT: FAIL")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    stages = argv or ["export", "check"]
    if "export" in stages: export()
    if "check" in stages: check()
