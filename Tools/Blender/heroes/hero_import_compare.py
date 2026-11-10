"""EXPORT_CONTRACT hero-mode check (Blender side; Unity side = Tools/Unity/hero_import_dump.cs): Unity-imported vertices (Temp/claude/hero_dump/*.txt) vs the FBX corners read in
Blender, mapped to Unity axes (x -> -x, Blender z -> Unity y, Blender y -> Unity -z; as servicearm_kin.docked_drone).
Both ways: every Unity vertex matches a Blender corner (position + normal) and every corner matches a Unity vertex.
Tangent: direction compared (MikkTSpace in Blender vs the imported FBX tangent)."""
import bpy, glob, os, numpy as np
from mathutils.kdtree import KDTree

ROOT = "D:/AI_Labyrinth/UnityProject"
A = np.array([[-1, 0, 0], [0, 0, 1], [0, -1, 0]], float)     # Blender -> Unity
TOL_P, TOL_N = 1e-4, 1e-3

worst_all = []
import sys
ONLY = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
for dump in sorted(glob.glob(ROOT + "/Temp/claude/hero_dump/*.txt")):
    if ONLY and os.path.basename(dump)[:-4] not in ONLY: continue
    name = os.path.basename(dump)[:-4]; hero = name.split("_")[2]
    U = np.loadtxt(dump).reshape(-1, 12)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=f"{ROOT}/Assets/Environment/Heroes/{hero}/{name}.fbx")
    objs = [o for o in bpy.data.objects if o.type == 'MESH']
    rows = []
    for o in objs:
        me = o.data; M = np.array(o.matrix_world); R = M[:3, :3]
        me.calc_tangents(uvmap=me.uv_layers[0].name)
        co = np.array([v.co for v in me.vertices]); uvl = me.uv_layers[0].data
        for lp in me.loops:
            p = A @ (R @ co[lp.vertex_index] + M[:3, 3])
            n = A @ (R @ np.array(lp.normal)); n /= np.linalg.norm(n)
            t = A @ (R @ np.array(lp.tangent)); t /= max(np.linalg.norm(t), 1e-12)
            rows.append(np.concatenate([p, n, t, uvl[lp.index].uv]))
    B = np.array(rows)
    tris = sum(len(o.data.polygons) for o in objs)
    kd = KDTree(len(B))
    for i, r in enumerate(B): kd.insert(r[:3], i)
    kd.balance()
    dp = dn = dt = 0.0; miss_u = 0
    matched = np.zeros(len(B), bool)
    for u in U:
        best = None
        for (_, j, d) in kd.find_range(u[:3], 1e-3):
            nd = np.linalg.norm(B[j, 3:6] - u[3:6]) + 10 * np.abs(B[j, 9:11] - u[10:12]).max()
            if best is None or nd + d < best[0] + best[1]: best = (d, nd, j)
        if best is None or best[0] > TOL_P or best[1] > TOL_N: miss_u += 1; continue
        d, nd, j = best; dp = max(dp, d); dn = max(dn, nd)
        # every corner with this position and normal counts as covered
        for (_, k, d2) in kd.find_range(u[:3], TOL_P):
            if np.linalg.norm(B[k, 3:6] - u[3:6]) <= TOL_N and np.abs(B[k, 9:11] - u[10:12]).max() <= 1e-5:
                matched[k] = True
                a = float(np.degrees(np.arccos(np.clip(abs(B[k, 6:9] @ u[6:9]), -1, 1))))
                if a > 1.0: print(f"  tangent {a:.2f} deg at {np.round(u[:3],4).tolist()} uv {np.round(u[10:12],5).tolist()} corners here: {sum(1 for _ in kd.find_range(u[:3], TOL_P))}")
                dt = max(dt, a)
    miss_b = int((~matched).sum())
    for k in np.where(~matched)[0][:6]:
        near = [(round(float(np.linalg.norm(U[i,:3]-B[k,:3]))*1e3,4), round(float(np.abs(U[i,10:12]-B[k,9:11]).max()),6), round(float(np.linalg.norm(U[i,3:6]-B[k,3:6])),5)) for i in range(len(U)) if np.linalg.norm(U[i,:3]-B[k,:3])<1e-3]
        print(f"  unmatched FBX corner at {np.round(B[k,:3],4).tolist()} uv {np.round(B[k,9:11],5).tolist()}: Unity verts here (mm, duv, dn) {near}")
    ws = set(np.round(U[:, 9]).astype(int).tolist())
    ok = miss_u == 0 and miss_b == 0 and dt < 1.0
    worst_all.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}: Unity v {len(U)} / FBX corners {len(B)} (faces {tris}); unmatched Unity {miss_u}, "
          f"unmatched FBX {miss_b}; worst pos {dp * 1e3:.4f} mm, normal {dn:.1e}, tangent dir {dt:.3f} deg; tangent w {sorted(ws)}")
print("RESULT:", "PASS" if all(worst_all) else "FAIL", f"({sum(worst_all)}/{len(worst_all)} parts)")
