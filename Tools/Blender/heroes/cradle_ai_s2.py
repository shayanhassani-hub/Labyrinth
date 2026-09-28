"""Cradle v2 STEP 2 - apply option A in the AI working file, symmetrize the plinth, render.
  blender -b --python cradle_ai_study.py -- s2 apply     (writes LAB_HERO_Cradle_AI.blend)
  blender -b --python cradle_ai_study.py -- s2 render    (Renders/cradle_v2_s2_*.png, file not saved)

Applied copies (collection AI_FIT_A, transforms applied, Blender = spec mapping per EXPORT_CONTRACT):
  AI_A_TexImg_sym  - tex_img mesh + UVs/texture, plinth symmetrized (bake source for colour)
  AI_A_Static_sym  - split part_0, plinth symmetrized (per-part deviation source)
  AI_A_Arm_L / AI_A_Arm_R - split arms
Originals stay untouched under AI_Root (now scaled to option A)."""
import bpy, bmesh, os, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import cradle_ai_study as S
from cradle_ai_analyze import OUT, DSP, spec_affine_to_blender, yaw_matrix, axis_matrix, box, spec_mesh, load, to_spec, bvh, nearest, sample_surface
from cradle_ai_saddle import saddle_parts, docked_drone, limb_frames, VARIANTS, FRONT_Y, BACK_Y, GAP

Y_CUT_SPEC = 0.415        # plinth region = spec y below this (column walls are vertical here)
PAD_VARIANT = "P1 plain pads r0.39-0.61 (outboard of pin)"


def choose_side(R):
    """which back diagonal face agrees better with its front counterpart (mirror across z = cz)?"""
    cx, cy = R["centre_native"]; s = R["options"]["A"]["s"]
    v, t = to_spec(*load("AI_split_part_0"), s, cx, cy)
    tree = bvh(v, t)
    p = sample_surface(v, t, 200000)
    res = {}
    for side, sg in (("+X (right)", 1), ("-X (left)", -1)):
        m = (p[:, 0] * sg > 0.3) & (p[:, 2] > S.CZ + 0.3) & (p[:, 1] < 0.21) & (np.hypot(p[:, 0], p[:, 2] - S.CZ) > 0.85)
        q = p[m].copy(); q[:, 2] = 2 * S.CZ - q[:, 2]
        d = nearest(tree, q)
        res[side] = dict(n=int(m.sum()), mean_mm=round(1e3 * d.mean(), 2), p99_mm=round(1e3 * np.percentile(d, 99), 1), max_mm=round(1e3 * d.max(), 1))
    print("SIDE CHECK back diagonal vs front counterpart:", res)
    keep = "-X (left)" if res["-X (left)"]["mean_mm"] <= res["+X (right)"]["mean_mm"] else "+X (right)"
    return keep, res


def symmetrize_lower(me_src, name, c_native, z_cut_native, keep_negative):
    """copy of mesh: region below z_cut mirrored across native x = c (keep one side), region above untouched"""
    me = me_src.copy(); me.name = name
    bm = bmesh.new(); bm.from_mesh(me)
    for v in bm.verts: v.co.x -= c_native
    # 1 cut at z_cut and split into lower / upper
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=(0, 0, z_cut_native), plane_no=(0, 0, 1))
    upper = [f for f in bm.faces if all(v.co.z >= z_cut_native - 1e-6 for v in f.verts)]
    us = set(upper)
    lower = [f for f in bm.faces if f not in us]
    bm_up = bmesh.new(); bm_lo = bmesh.new()
    me_up = bpy.data.meshes.new("tmp_up"); me_lo = bpy.data.meshes.new("tmp_lo")
    # write each half through a duplicate so UVs/attributes are kept
    for keepset, target in ((set(upper), me_up), (set(lower), me_lo)):
        b2 = bm.copy()
        kill = [f for f, f0 in zip(b2.faces, bm.faces) if f0 not in keepset]
        bmesh.ops.delete(b2, geom=kill, context='FACES')
        b2.to_mesh(target); b2.free()
    bm.free()
    # 2 symmetrize the lower half about x = 0 (shifted frame)
    bl = bmesh.new(); bl.from_mesh(me_lo)
    bmesh.ops.symmetrize(bl, input=bl.verts[:] + bl.edges[:] + bl.faces[:], direction='-X' if keep_negative else 'X', dist=1e-5)
    bl.to_mesh(me_lo); bl.free()
    # 3 join lower + upper, weld the seam at z_cut (1 mm)
    bu = bmesh.new(); bu.from_mesh(me_up); bu.from_mesh(me_lo)
    seam = [v for v in bu.verts if abs(v.co.z - z_cut_native) < 1e-5]
    bmesh.ops.remove_doubles(bu, verts=seam, dist=0.001 / 2.589)
    for v in bu.verts: v.co.x += c_native
    bu.to_mesh(me); bu.free()
    bpy.data.meshes.remove(me_up); bpy.data.meshes.remove(me_lo)
    return me


def symmetrize_direction_test():
    """bmesh symmetrize enum: find which value keeps the negative-x side"""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        if v.co.x < 0 and v.co.y < 0 and v.co.z < 0: v.co.x -= 0.5          # mark the -x side
    bmesh.ops.symmetrize(bm, input=bm.verts[:] + bm.edges[:] + bm.faces[:], direction='-X', dist=1e-5)
    mx = max(abs(v.co.x) for v in bm.verts); bm.free()
    return mx > 0.9            # True: '-X' keeps the negative side (mark survived and was mirrored)


def apply(args):
    R = json.load(open(OUT)); cx, cy = R["centre_native"]; o = R["options"]["A"]; s = o["s"]
    keep, side_res = choose_side(R)
    neg_ok = symmetrize_direction_test()
    print("SYMMETRIZE '-X' keeps negative side:", neg_ok)
    bpy.ops.wm.open_mainfile(filepath=S.BLEND)
    sc = bpy.context.scene
    root = bpy.data.objects["AI_Root"]; root.scale = (s,) * 3
    bpy.context.view_layer.update()
    for n in [c.name for c in bpy.data.collections if c.name.startswith("AI_FIT_A")]:
        coll = bpy.data.collections[n]
        for ob in list(coll.objects): bpy.data.objects.remove(ob)
        bpy.data.collections.remove(coll)
    fit = bpy.data.collections.new("AI_FIT_A"); sc.collection.children.link(fit)
    # native: keep side '-X (left)' in spec = native x < c ; spec X = s*(x - cx)
    c_native = R["symmetry"]["plane_x_native"]
    keep_negative = keep.startswith("-X")
    z_cut = Y_CUT_SPEC / s
    info = B = json.load(open(os.path.join(S.CACHE, "build.json")))
    tex = bpy.data.objects[B["objects"]["tex_img"][0]]; st = bpy.data.objects["AI_split_part_0"]
    made = {}
    for src, name in ((tex, "AI_A_TexImg_sym"), (st, "AI_A_Static_sym")):
        # source mesh data is native only if the object has an identity basis; otherwise bake it first
        basis = src.matrix_basis.copy()
        me0 = src.data.copy(); me0.transform(basis)
        me = symmetrize_lower(me0, name, c_native, z_cut, keep_negative if neg_ok else not keep_negative)
        bpy.data.meshes.remove(me0)
        ob = bpy.data.objects.new(name, me); fit.objects.link(ob)
        # world = AI_Root @ parent_inverse(-c) applied into the mesh
        W = root.matrix_world @ Matrix.Translation((-cx, -cy, 0))
        me.transform(W); ob.matrix_world = Matrix.Identity(4)
        made[name] = (len(me.vertices), len(me.polygons))
    for part, name in (("AI_split_part_1", "AI_A_Arm_L"), ("AI_split_part_2", "AI_A_Arm_R")):
        src = bpy.data.objects[part]; me = src.data.copy(); me.name = name
        me.transform(src.matrix_world); ob = bpy.data.objects.new(name, me); fit.objects.link(ob)
        made[name] = (len(me.vertices), len(me.polygons))
    # pads (P1), mirror images of each other in outline, thickness per side
    D, T = docked_drone(o); lim = limb_frames(D)
    kind, P = VARIANTS[PAD_VARIANT]
    floor = {"R": FRONT_Y - GAP - o["plate_top"]["R"], "L": BACK_Y - GAP - o["plate_top"]["L"]}
    for sd in ("L", "R"):
        pr = saddle_parts(kind, lim[sd]["o"], lim[sd]["a"], o["plate_top"][sd], floor[sd], P)[0]
        v, t = pr.mesh(); ob = spec_mesh(f"STUDY_Pad_{sd}", v, t, fit, (1.0, 0.55, 0.05, 1))
    # drone into the docking pose (both copies)
    P0 = np.array([0.0, 2.0, 4.76]); P1 = np.array(o["DroneAI2_new"]); A = yaw_matrix(o["yaw_deg"])
    Md = spec_affine_to_blender(A, P1 - A @ P0)
    dp = bpy.data.objects["DRONE_DockPose"]; dp.matrix_world = Md
    for ob in bpy.data.collections["DRONE_FBX"].objects:
        if ob.parent is None: ob.matrix_world = Md @ ob.matrix_world
    # hide heavy originals in the viewport, keep them in the file
    lc = bpy.context.view_layer.layer_collection.children["AI_SOURCES"]
    for ch in lc.children: ch.hide_viewport = ch.name not in ("SRC_split",)
    bpy.ops.wm.save_as_mainfile(filepath=S.BLEND, compress=False)
    json.dump(dict(keep_side=keep, side_check=side_res, y_cut_spec=Y_CUT_SPEC, plane_x_native=c_native, made=made),
              open(os.path.join(S.CACHE, "s2_apply.json"), "w"), indent=1)
    print("APPLY done", made, "kept", keep)


def verify_sym(args):
    """mirror deviation of the plinth region after symmetrizing (applied static copy)"""
    bpy.ops.wm.open_mainfile(filepath=S.BLEND)
    ob = bpy.data.objects["AI_A_Static_sym"]; me = ob.data
    v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", v); v = v.reshape(-1, 3)
    me.calc_loop_triangles(); t = np.empty(len(me.loop_triangles) * 3, np.int32); me.loop_triangles.foreach_get("vertices", t)
    t = t.reshape(-1, 3)
    tree = BVHTree.FromPolygons(v.tolist(), t.tolist(), all_triangles=True)
    p = sample_surface(v, t, 120000)
    m = p[:, 2] < Y_CUT_SPEC - 0.01                      # Blender z = spec y
    A = json.load(open(os.path.join(S.CACHE, "s2_apply.json"))); R = json.load(open(OUT))
    xb = -R["options"]["A"]["s"] * (A["plane_x_native"] - R["centre_native"][0])   # mirror plane in Blender x
    q = p[m].copy(); q[:, 0] = 2 * xb - q[:, 0]
    d = nearest(tree, q)
    print(f"SYM plinth after: mean {1e3*d.mean():.3f} mm, p99 {1e3*np.percentile(d,99):.2f} mm, max {1e3*d.max():.2f} mm (n {m.sum()})")
    q = p[~m].copy(); q[:, 0] = 2 * xb - q[:, 0]; d2 = nearest(tree, q)
    print(f"SYM above cut (untouched): mean {1e3*d2.mean():.3f} mm, max {1e3*d2.max():.2f} mm")
    top = np.argsort(d2)[-8:]
    for i in top:
        pb = p[~m][i]; print("   worst above cut, spec (x, y, z) =", np.round([-pb[0], pb[2], -pb[1]], 3), f"{1e3*d2[i]:.1f} mm")
    json.dump(dict(plinth_mean_mm=1e3 * d.mean(), plinth_max_mm=1e3 * d.max(), upper_mean_mm=1e3 * d2.mean(), upper_max_mm=1e3 * d2.max()),
              open(os.path.join(S.CACHE, "s2_sym_verify.json"), "w"))


def render(args):
    R = json.load(open(OUT)); o = R["options"]["A"]
    rel_deg = 75.0
    bpy.ops.wm.open_mainfile(filepath=S.BLEND)
    sc = bpy.context.scene
    for c in bpy.data.collections:
        c.hide_render = c.name not in ("AI_FIT_A", "DRONE_FBX")
    fit = bpy.data.collections["AI_FIT_A"]
    bpy.data.objects["AI_A_TexImg_sym"].hide_render = True
    GREY, ARM, AMBER, YEL = (0.30, 0.31, 0.34, 1), (0.42, 0.43, 0.47, 1), (1.0, 0.55, 0.05, 1), (0.95, 0.80, 0.20, 1)
    bpy.data.objects["AI_A_Static_sym"].color = GREY
    for n in ("AI_A_Arm_L", "AI_A_Arm_R"): bpy.data.objects[n].color = ARM
    for ob in bpy.data.collections["DRONE_FBX"].objects:
        if ob.type == 'MESH': ob.color = (0.75, 0.8, 0.85, 1) if "Propellor" in ob.name else YEL
    fv, ft = box(np.array([0, -0.005, S.CZ]), (8, 0.01, 8)); spec_mesh("STUDY_Floor", fv, ft, fit, (0.55, 0.55, 0.57, 1))
    sh = sc.display.shading
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.render.resolution_x, sc.render.resolution_y = 2400, 1500
    sc.render.resolution_percentage = 100; sc.display.render_aa = '16'
    sh.light = 'STUDIO'; sh.color_type = 'OBJECT'; sh.show_cavity = True; sh.cavity_type = 'BOTH'
    sh.show_object_outline = True; sh.show_shadows = True; sh.shadow_intensity = 0.35
    sh.background_type = 'VIEWPORT'; sh.background_color = (0.18, 0.19, 0.21)

    def cam(name, loc_spec, look_spec, ortho=None, lens=40):
        cd = bpy.data.cameras.new(name); cd.clip_end = 100
        c = bpy.data.objects.new(name, cd); sc.collection.objects.link(c)
        c.location = Vector(DSP @ np.array(loc_spec)); t = Vector(DSP @ np.array(look_spec))
        c.rotation_euler = (t - c.location).to_track_quat('-Z', 'Y').to_euler()
        if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
        else: cd.lens = lens
        sc.camera = c

    def shot(fn):
        sc.render.filepath = os.path.join(S.RENDERS, fn); bpy.ops.render.render(write_still=True); print("RENDER", fn)
    cz = S.CZ
    cam("F", [0, 1.0, cz - 8], [0, 1.0, cz], ortho=3.4); shot("cradle_v2_s2_dock_front.png")
    cam("Q", [-2.9, 2.5, cz - 3.4], [0, 0.95, cz]); shot("cradle_v2_s2_dock_34.png")
    cam("T", [0, 8, cz + 0.001], [0, 0, cz], ortho=4.0); sc.camera.rotation_euler[2] += math.pi; shot("cradle_v2_s2_dock_top.png")
    # pads close-up, front ortho, drone hidden in one shot and shown in the other
    cam("PF", [0, 1.73, cz - 6], [0, 1.73, cz], ortho=2.5); shot("cradle_v2_s2_pads_front.png")
    for ob in bpy.data.collections["DRONE_FBX"].objects: ob.hide_render = True
    shot("cradle_v2_s2_pads_front_nodrone.png")
    cam("PQ", [-1.2, 2.3, cz - 1.5], [0, 1.72, cz], lens=35); shot("cradle_v2_s2_pads_34_nodrone.png")
    for ob in bpy.data.collections["DRONE_FBX"].objects: ob.hide_render = False
    # plinth symmetrized: back-right diagonal close-up
    for n in ("AI_A_Arm_L", "AI_A_Arm_R", "STUDY_Pad_L", "STUDY_Pad_R"): bpy.data.objects[n].hide_render = True
    for ob in bpy.data.collections["DRONE_FBX"].objects: ob.hide_render = True
    cam("SYM", [2.4, 1.0, cz + 2.4], [0.45, 0.1, cz + 0.45], lens=45); shot("cradle_v2_s2_plinth_sym_backright.png")
    bpy.data.objects["AI_A_Static_sym"].hide_render = True
    orig = bpy.data.objects["AI_split_part_0"]; orig.hide_render = False; orig.color = GREY
    bpy.data.collections["SRC_split"].hide_render = False
    for n in ("AI_split_part_1", "AI_split_part_2"): bpy.data.objects[n].hide_render = True
    shot("cradle_v2_s2_plinth_orig_backright.png")
    bpy.data.collections["SRC_split"].hide_render = True
    bpy.data.objects["AI_A_Static_sym"].hide_render = False
    for n in ("AI_A_Arm_L", "AI_A_Arm_R", "STUDY_Pad_L", "STUDY_Pad_R"): bpy.data.objects[n].hide_render = False
    for ob in bpy.data.collections["DRONE_FBX"].objects: ob.hide_render = False
    # release 75 deg, drone lifted 0.5 m
    for sd, arm in (("L", "AI_A_Arm_L"), ("R", "AI_A_Arm_R")):
        f = np.array(o["pins_spec"][sd]["front"]); ax = np.array(o["release"][sd]["axis_dir"]); sgn = 1 if sd == "L" else -1
        Ar = axis_matrix(ax, sgn * rel_deg); Mr = spec_affine_to_blender(Ar, f - Ar @ f)
        for n in (arm, f"STUDY_Pad_{sd}"):
            ob = bpy.data.objects[n]; ob.matrix_world = Mr @ ob.matrix_world
    Ml = spec_affine_to_blender(np.eye(3), np.array([0, 0.5, 0]))
    for ob in bpy.data.collections["DRONE_FBX"].objects:
        if ob.parent is None: ob.matrix_world = Ml @ ob.matrix_world
    RED = (0.9, 0.1, 0.1, 1)
    for i, (c, sz) in enumerate(((np.array([0, 1.19, cz - 1.4]), (2.9, 0.012, 0.012)), (np.array([0, 1.19, cz + 1.4]), (2.9, 0.012, 0.012)),
                                 (np.array([-1.45, 1.19, cz]), (0.012, 0.012, 2.8)), (np.array([1.45, 1.19, cz]), (0.012, 0.012, 2.8)))):
        bv, bt = box(c, sz); spec_mesh(f"STUDY_Vol119_{i}", bv, bt, fit, RED)
    cam("RF", [0, 1.1, cz - 8], [0, 1.1, cz], ortho=3.6); shot("cradle_v2_s2_release_front.png")
    cam("RQ", [-2.9, 2.5, cz - 3.4], [0, 0.95, cz]); shot("cradle_v2_s2_release_34.png")


def saddle_render(args):
    """the rejected identical-saddle variant (S1), front view with the drone - shows the prop conflict"""
    from cradle_ai_saddle import saddle_parts
    R = json.load(open(OUT)); o = R["options"]["A"]
    bpy.ops.wm.open_mainfile(filepath=S.BLEND)
    sc = bpy.context.scene
    for c in bpy.data.collections: c.hide_render = c.name not in ("AI_FIT_A", "DRONE_FBX")
    fit = bpy.data.collections["AI_FIT_A"]
    for n in ("AI_A_TexImg_sym", "STUDY_Pad_L", "STUDY_Pad_R"): bpy.data.objects[n].hide_render = True
    D, T = docked_drone(o); lim = limb_frames(D)
    kind, P = VARIANTS["S1 full saddle r0.29-0.61 H80"]
    floor = {"R": FRONT_Y - GAP - o["plate_top"]["R"], "L": BACK_Y - GAP - o["plate_top"]["L"]}
    for sd in ("L", "R"):
        for i, pr in enumerate(saddle_parts(kind, lim[sd]["o"], lim[sd]["a"], o["plate_top"][sd], floor[sd], P)):
            v, t = pr.mesh(); spec_mesh(f"STUDY_Saddle_{sd}{i}", v, t, fit, (1.0, 0.55, 0.05, 1))
    bpy.data.objects["AI_A_Static_sym"].color = (0.30, 0.31, 0.34, 1)
    for n in ("AI_A_Arm_L", "AI_A_Arm_R"): bpy.data.objects[n].color = (0.42, 0.43, 0.47, 1)
    for ob in bpy.data.collections["DRONE_FBX"].objects:
        if ob.type == 'MESH': ob.color = (0.75, 0.8, 0.85, 1) if "Propellor" in ob.name else (0.95, 0.80, 0.20, 1)
    sh = sc.display.shading
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.render.resolution_x, sc.render.resolution_y = 2400, 1500
    sh.light = 'STUDIO'; sh.color_type = 'OBJECT'; sh.show_cavity = True; sh.show_object_outline = True
    sh.background_type = 'VIEWPORT'; sh.background_color = (0.18, 0.19, 0.21); sc.display.render_aa = '16'
    cd = bpy.data.cameras.new("c"); cd.type = 'ORTHO'; cd.ortho_scale = 2.5
    c = bpy.data.objects.new("c", cd); sc.collection.objects.link(c)
    c.location = Vector(DSP @ np.array([0, 1.73, S.CZ - 6])); c.rotation_euler = (Vector(DSP @ np.array([0, 1.73, S.CZ])) - c.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = c
    sc.render.filepath = os.path.join(S.RENDERS, "cradle_v2_s2_saddle_rejected_front.png"); bpy.ops.render.render(write_still=True)
    print("RENDER cradle_v2_s2_saddle_rejected_front.png")


def run(args):
    {"apply": apply, "verify": verify_sym, "render": render, "saddle_render": saddle_render}[args[0]](args[1:])
