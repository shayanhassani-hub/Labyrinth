"""Cradle v2 (AI transfer workflow) - STEP 1 import, fit and docking study.

Run headless, one stage per call:
  blender -b --factory-startup --python cradle_ai_study.py -- build
  blender -b --factory-startup --python cradle_ai_study.py -- analyze
  blender -b --factory-startup --python cradle_ai_study.py -- render <option>

Sources (never modified): D:\\AI_Labyrinth\\Hunyuan\\Downloads\\Cradle\\*
Working file:             D:\\AI_Labyrinth\\Blender\\Source\\Heroes\\Cradle\\LAB_HERO_Cradle_AI.blend
Drone: live world-space dump from Unity (Temp/claude/drone_world_spec.obj, spec coordinates) plus
the project FBX (Assets/Drone_Asset/drone_low.fbx, read-only) fitted onto it.

Frames. "native" = the AI mesh as Blender imports it (Z up, arms along X, caps front = -Y).
"spec" = Unity axes (EXPORT_CONTRACT). native -> spec:
    spec = (s*(xn-cx), s*zn, CZ + s*(yn-cy))
which in Blender is a 180 deg turn about Z, uniform scale s and a move to the cradle origin.
"""
import bpy, bmesh, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

SRC = r"D:\AI_Labyrinth\Hunyuan\Downloads\Cradle"
BLEND = r"D:\AI_Labyrinth\Blender\Source\Heroes\Cradle\LAB_HERO_Cradle_AI.blend"
PROJ = r"D:\AI_Labyrinth\UnityProject"
DRONE_OBJ = os.path.join(PROJ, r"Temp\claude\drone_world_spec.obj")
DRONE_FBX = os.path.join(PROJ, r"Assets\Drone_Asset\drone_low.fbx")
CACHE = os.path.join(PROJ, r"Temp\claude\cradle_ai")
RENDERS = os.path.join(PROJ, "Renders")
CZ = 4.69                      # cradle origin z (spec), x = 0
SOURCES = [("geo1p5m", "cradle_hy_geo1p5m.fbx"),
           ("tex_img", "cradle_hy_geo1p5m_tex_img.glb"),
           ("tex_txt", "cradle_hy_geo1p5m_tex_txt.glb"),
           ("split", "cradle_hy_split.fbx"),
           ("retopo_low", "cradle_hy_retopo_low.fbx")]


def spec2b(p):
    return Vector((-p[0], -p[2], p[1]))


def world_np(o):
    me = o.data
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(o.matrix_world)
    return co @ M[:3, :3].T + M[:3, 3]


def tris_np(o):
    me = o.data
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", t)
    return t.reshape(-1, 3)


def read_drone_obj():
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


def new_coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


# ----------------------------------------------------------------------------- build
def stage_build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 1.0
    os.makedirs(CACHE, exist_ok=True)
    root = bpy.data.objects.new("AI_Root", None); sc.collection.objects.link(root)
    src_parent = new_coll("AI_SOURCES")
    info = {}
    for key, fn in SOURCES:
        before = set(bpy.data.objects)
        p = os.path.join(SRC, fn)
        if fn.endswith(".fbx"): bpy.ops.import_scene.fbx(filepath=p)
        else: bpy.ops.import_scene.gltf(filepath=p)
        new = [o for o in bpy.data.objects if o not in before]
        coll = new_coll("SRC_" + key, src_parent)
        for o in new:
            for c in o.users_collection: c.objects.unlink(o)
            coll.objects.link(o)
            o.name = f"AI_{key}_{o.name}"
        meshes = [o for o in new if o.type == 'MESH']
        info[key] = [o.name for o in meshes]
        if key in ("geo1p5m", "split"):
            for o in meshes:
                np.savez(os.path.join(CACHE, o.name + ".npz"), v=world_np(o), t=tris_np(o))
        if key in ("tex_txt", "retopo_low"):
            coll.hide_render = True
            bpy.context.view_layer.layer_collection.children["AI_SOURCES"].children[coll.name].hide_viewport = True
    # centre of the design: plinth footprint centre (bottom 2 cm of the raw mesh)
    raw = np.load(os.path.join(CACHE, info["geo1p5m"][0] + ".npz"))["v"]
    low = raw[raw[:, 2] < 0.02]
    cx = (low[:, 0].min() + low[:, 0].max()) / 2; cy = (low[:, 1].min() + low[:, 1].max()) / 2
    for key, names in info.items():
        for n in names:
            o = bpy.data.objects[n]
            mw = o.matrix_world.copy()
            o.parent = root
            o.matrix_parent_inverse = Matrix.Translation((-cx, -cy, 0))
            o.matrix_basis = mw
    root.location = (0, -CZ, 0); root.rotation_euler = (0, 0, math.pi); root.scale = (1, 1, 1)
    json.dump({"cx": cx, "cy": cy, "objects": info}, open(os.path.join(CACHE, "build.json"), "w"), indent=1)

    # drone, live world dump (spec) -> Blender
    dc = new_coll("DRONE_Live")
    droot = bpy.data.objects.new("DRONE_DockPose", None); sc.collection.objects.link(droot)
    for name, (v, f) in read_drone_obj().items():
        me = bpy.data.meshes.new(name)
        me.from_pydata([spec2b(p) for p in v], [], [list(map(int, t)) for t in f])
        for poly in me.polygons: poly.flip()          # the spec->Blender mapping is a mirror
        me.update()
        o = bpy.data.objects.new("DRONE_" + name, me); dc.objects.link(o); o.parent = droot
    # drone, project FBX (read-only) fitted onto the live dump
    fitted = fit_drone_fbx(new_coll("DRONE_FBX"))
    json.dump(fitted, open(os.path.join(CACHE, "drone_fbx_fit.json"), "w"), indent=1)
    os.makedirs(os.path.dirname(BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=False)
    print("BUILD cx cy", cx, cy); print("BUILD fbx fit", fitted)


def fit_drone_fbx(coll):
    """Import drone_low.fbx and find the one similarity transform (signed axis permutation,
    uniform scale, translation) that puts it onto the live dump. Report the residual."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=DRONE_FBX)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in o.users_collection: c.objects.unlink(o)
        coll.objects.link(o)
    live = {n: np.array([spec2b(p) for p in v]) for n, (v, f) in read_drone_obj().items()}
    fbx = {}
    for o in new:
        if o.type != 'MESH': continue
        base = o.name.split(".")[0]
        if base in live: fbx[base] = (o, world_np(o))
    L = np.vstack([live[k] for k in fbx]); F = np.vstack([fbx[k][1] for k in fbx])
    kd = KDTree(len(L))
    for i, p in enumerate(L): kd.insert(p, i)
    kd.balance()
    best = None
    import itertools
    for perm in itertools.permutations(range(3)):
        for sg in itertools.product((1, -1), repeat=3):
            Q = np.zeros((3, 3))
            for i in range(3): Q[i, perm[i]] = sg[i]
            G = F @ Q.T
            s = np.linalg.norm(L.max(0) - L.min(0)) / np.linalg.norm(G.max(0) - G.min(0))
            t = (L.max(0) + L.min(0)) / 2 - s * (G.max(0) + G.min(0)) / 2
            H = s * G + t
            sub = H[:: max(1, len(H) // 1500)]
            err = np.mean([kd.find(p)[2] for p in sub])
            if best is None or err < best[0]: best = (err, Q, s, t)
    err, Q, s, t = best
    H = s * (F @ Q.T) + t
    d = np.array([kd.find(p)[2] for p in H])
    M = Matrix.Identity(4)
    for i in range(3):
        for j in range(3): M[i][j] = s * Q[i, j]
        M[i][3] = t[i]
    top = [o for o in new if o.parent is None]
    for o in top:
        o.matrix_world = M @ o.matrix_world
    return {"det": float(np.linalg.det(Q)), "scale": float(s), "fit_mean_m": float(d.mean()),
            "fit_max_m": float(d.max()), "parts_matched": len(fbx)}


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    stage = argv[0] if argv else "build"
    if stage == "build": stage_build()
    elif stage == "analyze":
        import cradle_ai_analyze; cradle_ai_analyze.run(argv[1:])
    elif stage == "dock":
        import cradle_ai_analyze; cradle_ai_analyze.docking(argv[1:])
    elif stage == "saddle":
        import cradle_ai_saddle; cradle_ai_saddle.run(argv[1:])
    elif stage == "sections":
        import cradle_ai_sections; getattr(cradle_ai_sections, argv[1])(argv[2:])
    elif stage == "sheet":
        import cradle_ai_sheet; cradle_ai_sheet.run(argv[1:])
    elif stage == "probe":
        import cradle_ai_probe; cradle_ai_probe.run(argv[1:])
    elif stage == "probe2":
        import cradle_ai_probe2; cradle_ai_probe2.run(argv[1:])
    elif stage == "look":
        import cradle_ai_look; cradle_ai_look.run(argv[1:])
    elif stage == "probe3":
        import cradle_ai_probe3; cradle_ai_probe3.run(argv[1:])
    elif stage == "s2":
        import cradle_ai_s2; cradle_ai_s2.run(argv[1:])
    elif stage == "render":
        import cradle_ai_analyze; cradle_ai_analyze.render(argv[1:])
