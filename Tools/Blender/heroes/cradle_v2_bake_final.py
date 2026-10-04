"""
Cradle v2 Step 6b/6c: verification bake of the production set in Blender, renders, and the Substance export.
Step 6c also: -- sliver <step> <low segments> (baked normal at the foot of the turntable / rings), -- foot <tag> <step>
(Renders/cradle_v2_s6c_turntable_foot_<tag>.png), -- top (Renders/cradle_v2_s6c_top.png).
Needs the build of cradle_v2_highpoly.py (HIGH_FINAL, BAKE_LOW, CAGE in the BAKE file).
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake_final.py -- bake      (maps -> Substance/Cradle/Bake_<STEP>)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake_final.py -- renders   (Renders/cradle_v2_s<STEP>_*)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake_final.py -- export    (Substance/Cradle/Mesh + README)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake_final.py -- verify    (re-imports the three FBX files)

Bake: per part (<Part>_bakelow = triangulated export copy, the MikkTSpace basis of Cradle_low.fbx) from
<Part>_high_final through <Part>_cage; 2048, 16 px margin. Maps: tangent normal (OpenGL, +Y), AO (per part,
64 samples, 0.25 m), curvature (convexity - concavity from two local AO lookups over 4 mm on the high; floaters in
their own object so they don't read as convex), ID (vertex colour "ID"). Checks: ray misses (white emission, no
margin) and the hit distance |P_high - P_low| per texel (foreign hits = the 5b dashed lines).
"""
import bpy
import bmesh
import json
import math
import os
import sys
import time
import numpy as np
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import cradle_v2 as V                    # noqa: E402
import cradle_v2_check as C              # noqa: E402
import cradle_v2_bake as B               # noqa: E402
import cradle_v2_bake_test as T          # noqa: E402
import cradle_v2_highpoly as H           # noqa: E402

CZ = V.CZ
STEP = "6c"                              # 6c: 32-segment turntable / rings (6b maps stay in Bake_6b)
OUT = rf"D:/AI_Labyrinth/Substance/Cradle/Bake_{STEP}"
MESH = r"D:/AI_Labyrinth/Substance/Cradle/Mesh"
OLD = os.path.join(MESH, "_superseded_5a_AI")
SCR = os.path.join(C.PROJ, "Temp", "claude", "cradle_bake")
RES, MARGIN = 2048, 16
SS = 2                                   # bake at RES * SS and box-filter down: 2x2 supersampling (Blender's bake has no AA)
RAY_MAX = 0.05
AO_SAMPLES, AO_DIST = 64, 0.25
CURV_DIST, CURV_SAMPLES = 0.004, 16
FOREIGN = 0.020                          # hit farther than this from the low point: suspect (expected <= ~15 mm)
PARTS = list(B.PARTS)


# --------------------------------------------------------------------------- helpers


def objs():
    lo = {k: bpy.data.objects[f"{k}_bakelow"] for k in PARTS}
    hi = {k: bpy.data.objects[f"{k}_high_final"] for k in PARTS}
    cg = {k: bpy.data.objects[f"{k}_cage"] for k in PARTS}
    return lo, hi, cg


def split_details(hi):
    """body / detail objects of a high (face attribute "det"); returns the list to select for the bake"""
    me = hi.data
    if "det" not in me.attributes: return [hi]
    det = np.zeros(len(me.polygons), np.int32); me.attributes["det"].data.foreach_get("value", det)
    out = []
    for tag, keep in (("body", det == 0), ("det", det == 1)):
        if not keep.any(): continue
        m2 = B.submesh(me, keep, f"{hi.name}_{tag}")
        # keep the custom normals: submesh goes through bmesh, which carries the custom_normal attribute
        o = bpy.data.objects.new(f"{hi.name}_{tag}", m2); bpy.context.scene.collection.objects.link(o)
        o.matrix_world = hi.matrix_world.copy(); o.hide_render = True; out.append(o)
    return out


def node_mat(name, build):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for x in list(nt.nodes): nt.nodes.remove(x)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs[0], out.inputs[0])
    build(nt, em)
    return m


def emit_const(c):
    return node_mat("emit_const", lambda nt, em: em.inputs["Color"].__setattr__("default_value", c))


def emit_id():
    def b(nt, em):
        a = nt.nodes.new("ShaderNodeVertexColor"); a.layer_name = "ID"; nt.links.new(a.outputs["Color"], em.inputs["Color"])
    return node_mat("emit_id", b)


def emit_position():
    def b(nt, em):
        g = nt.nodes.new("ShaderNodeNewGeometry"); add = nt.nodes.new("ShaderNodeVectorMath"); add.operation = 'ADD'
        add.inputs[1].default_value = (4.0, 8.0, 4.0)                   # keep it positive
        nt.links.new(g.outputs["Position"], add.inputs[0]); nt.links.new(add.outputs[0], em.inputs["Color"])
    return node_mat("emit_pos", b)


def emit_curvature():
    def b(nt, em):
        ai = nt.nodes.new("ShaderNodeAmbientOcclusion"); ai.inside = True; ai.only_local = True; ai.samples = CURV_SAMPLES
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion"); ao.inside = False; ao.only_local = True; ao.samples = CURV_SAMPLES
        for n in (ai, ao): n.inputs["Distance"].default_value = CURV_DIST
        sub = nt.nodes.new("ShaderNodeMath"); sub.operation = 'SUBTRACT'               # (1-AOin) - (1-AOout) = AOout - AOin
        nt.links.new(ao.outputs["AO"], sub.inputs[0]); nt.links.new(ai.outputs["AO"], sub.inputs[1])
        ma = nt.nodes.new("ShaderNodeMath"); ma.operation = 'MULTIPLY_ADD'
        nt.links.new(sub.outputs[0], ma.inputs[0]); ma.inputs[1].default_value = 0.5; ma.inputs[2].default_value = 0.5
        nt.links.new(ma.outputs[0], em.inputs["Color"])
    return node_mat("emit_curv", b)


def set_mats(objs_, m):
    keep = [list(o.data.materials) for o in objs_]
    for o in objs_: o.data.materials.clear(); o.data.materials.append(m)
    return keep


def restore_mats(objs_, keep):
    for o, ms in zip(objs_, keep):
        o.data.materials.clear()
        for m in ms: o.data.materials.append(m)


def run_bake(low, highs, cage, img, kind, clear, margin=MARGIN * SS):
    for o in bpy.context.view_layer.objects: o.select_set(False)
    for h in highs: h.hide_render = False; h.hide_set(False); h.select_set(True)
    low.hide_render = False; low.select_set(True); bpy.context.view_layer.objects.active = low
    for n in low.data.materials[0].node_tree.nodes:
        if n.type == 'TEX_IMAGE': n.image = img; low.data.materials[0].node_tree.nodes.active = n
    kw = dict(target='IMAGE_TEXTURES', use_clear=clear, margin=margin, margin_type='EXTEND')
    if highs:
        kw.update(use_selected_to_active=True, use_cage=True, cage_object=cage.name, max_ray_distance=RAY_MAX)
    t = time.time()
    if kind == "NORMAL":
        bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', normal_r='POS_X', normal_g='POS_Y', normal_b='POS_Z', **kw)
    elif kind == "AO":
        bpy.ops.object.bake(type='AO', **kw)
    else:
        bpy.ops.object.bake(type='EMIT', **kw)
    for h in highs: h.select_set(False); h.hide_render = True
    low.hide_render = True
    return time.time() - t


def pixels(img):
    n = img.size[0]; a = np.empty(n * n * 4, np.float32); img.pixels.foreach_get(a); return a.reshape(n, n, 4)


def save_down(img, fn):
    """box filter SS x SS down to RES, save as 8-bit PNG (data maps keep their values)"""
    a = pixels(img); n = a.shape[0] // SS
    d = a.reshape(n, SS, n, SS, 4).mean((1, 3))
    if img.name == "n":                                         # renormalise the averaged normals
        v = d[..., :3] * 2 - 1; v /= np.linalg.norm(v, axis=2, keepdims=True).clip(1e-6); d[..., :3] = v * 0.5 + 0.5
    o = bpy.data.images.new(fn, n, n, alpha=False); o.colorspace_settings.name = 'Non-Color'; o.pixels.foreach_set(d.ravel())
    o.filepath_raw = os.path.join(OUT, fn); o.file_format = 'PNG'; o.save(); print("SAVED", fn)


# --------------------------------------------------------------------------- bake


def bake(args):
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    os.makedirs(OUT, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = AO_SAMPLES
    sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.light_settings.distance = AO_DIST
    sc.view_settings.view_transform = 'Standard'
    for o in bpy.data.objects: o.hide_render = True
    T.RES = RES * SS
    lo, hi, cg = objs()
    for k in PARTS:
        T.target_material(lo[k], None)
        lo[k].visible_diffuse = lo[k].visible_glossy = lo[k].visible_shadow = lo[k].visible_transmission = lo[k].visible_volume_scatter = False
    parts_hi = {k: split_details(hi[k]) for k in PARTS}       # body + floaters (curvature needs them apart)
    mask = T.uv_mask(lo.values())
    imgs = {"Normal": T.new_image("n", color=(0.5, 0.5, 1.0, 1)), "AO": T.new_image("ao", color=(1, 1, 1, 1)),
            "Curvature": T.new_image("cv", color=(0.5, 0.5, 0.5, 1)), "ID": T.new_image("id", color=(0, 0, 0, 1)),
            "Miss": T.new_image("miss", color=(0, 0, 0, 1)),
            "PosHigh": T.new_image("ph", float_=True), "PosLow": T.new_image("pl", float_=True)}
    mats = {"Curvature": emit_curvature(), "ID": emit_id(), "Miss": emit_const((1, 1, 1, 1)), "PosHigh": emit_position()}
    tm = {}
    for i, k in enumerate(PARTS):
        hs = parts_hi[k]; first = i == 0
        tm["Normal"] = tm.get("Normal", 0) + run_bake(lo[k], hs, cg[k], imgs["Normal"], "NORMAL", first)
        tm["AO"] = tm.get("AO", 0) + run_bake(lo[k], hs, cg[k], imgs["AO"], "AO", first)
        for name in ("ID", "Miss", "PosHigh", "Curvature"):
            if name == "Curvature": sc.cycles.samples = 16
            keep = set_mats(hs, mats[name])
            tm[name] = tm.get(name, 0) + run_bake(lo[k], hs, cg[k], imgs[name], "EMIT", first, margin=0 if name in ("Miss", "PosHigh") else MARGIN)
            restore_mats(hs, keep); sc.cycles.samples = AO_SAMPLES
        # the low's own surface position per texel (no selected-to-active)
        keep = set_mats([lo[k]], emit_position()); T.target_material(lo[k], None)
        lm = lo[k].data.materials[0]; nt = lm.node_tree
        em = nt.nodes.new("ShaderNodeEmission"); outn = nt.nodes.new("ShaderNodeOutputMaterial"); g = nt.nodes.new("ShaderNodeNewGeometry")
        add = nt.nodes.new("ShaderNodeVectorMath"); add.operation = 'ADD'; add.inputs[1].default_value = (4.0, 8.0, 4.0)
        nt.links.new(g.outputs["Position"], add.inputs[0]); nt.links.new(add.outputs[0], em.inputs["Color"]); nt.links.new(em.outputs[0], outn.inputs[0])
        outn.is_active_output = True
        tm["PosLow"] = tm.get("PosLow", 0) + run_bake(lo[k], [], None, imgs["PosLow"], "EMIT", first, margin=0)
        T.target_material(lo[k], None)
        print(f"BAKED {k}")
    # ---- checks
    miss = pixels(imgs["Miss"])[:, :, 0] < 0.5
    missed = mask & miss
    ph, pl = pixels(imgs["PosHigh"])[:, :, :3], pixels(imgs["PosLow"])[:, :, :3]
    hit = mask & ~miss
    d = np.linalg.norm(ph - pl, axis=2)
    dh = d[hit]
    rep = dict(uv_texels=int(mask.sum()), missed_texels=int(missed.sum()), missed_pct=round(100 * missed.sum() / mask.sum(), 4),
               hit_dist_mm=dict(p50=round(1e3 * float(np.percentile(dh, 50)), 2), p99=round(1e3 * float(np.percentile(dh, 99)), 2),
                                p999=round(1e3 * float(np.percentile(dh, 99.9)), 2), max=round(1e3 * float(dh.max()), 1)),
               seconds={k: round(v, 1) for k, v in tm.items()})
    far = hit & (d > FOREIGN)
    rep["foreign_hits_texels"] = int(far.sum())
    cells = {}
    if far.any():
        P = pl[far] - np.array([4.0, 8.0, 4.0]); S = B.spec_local(P)
        for q, dv in zip(S, d[far]):
            key = tuple(np.round(q / 0.05).astype(int)); c = cells.setdefault(key, [0, 0.0, q]); c[0] += 1; c[1] = max(c[1], dv)
    rep["foreign_cells"] = [dict(n=c[0], max_mm=round(1e3 * c[1], 1), at=np.round(c[2], 3).tolist())
                            for c in sorted(cells.values(), key=lambda c: -c[0])[:15]]
    if missed.any():
        P = pl[missed] - np.array([4.0, 8.0, 4.0]); S = B.spec_local(P); mc = {}
        for q in S:
            key = tuple(np.round(q / 0.05).astype(int)); c = mc.setdefault(key, [0, q]); c[0] += 1
        rep["miss_cells"] = [dict(n=c[0], at=np.round(c[1], 3).tolist()) for c in sorted(mc.values(), key=lambda c: -c[0])[:10]]
    # ID coverage: texels per group colour
    idp = pixels(imgs["ID"])[:, :, :3][hit]
    cols = {n: np.array(c) / 255.0 for _, (n, c) in H.ID_GROUPS.items()}
    rep["id_texels"] = {n: int((np.abs(idp - c).max(1) < 0.02).sum()) for n, c in cols.items()}
    rep["id_unassigned_texels"] = int(len(idp) - sum(rep["id_texels"].values()))
    # save maps (+ the miss and hit-distance visualisations)
    for name, fn in (("Normal", f"T_Cradle_Normal_blender{STEP}.png"), ("AO", f"T_Cradle_AO_blender{STEP}.png"),
                     ("Curvature", f"T_Cradle_Curvature_blender{STEP}.png"), ("ID", f"T_Cradle_ID_blender{STEP}.png")):
        save_down(imgs[name], fn)
    R2 = RES * SS
    vis = np.zeros((R2, R2, 4), np.float32); vis[..., 3] = 1
    vis[mask] = (0.25, 0.25, 0.25, 1)
    v = np.clip(d / FOREIGN, 0, 1)
    vis[hit, 0] = v[hit]; vis[hit, 1] = v[hit] * 0.6; vis[hit, 2] = 0.25 * (1 - v[hit])
    vis[far] = (1, 0, 1, 1); vis[missed] = (1, 0, 0, 1)
    vi = bpy.data.images.new("vis", R2, R2, alpha=False); vi.pixels.foreach_set(vis.ravel())
    vi.filepath_raw = os.path.join(OUT, f"T_Cradle_RayCheck_blender{STEP}.png"); vi.file_format = 'PNG'; vi.save()
    rep["settings"] = dict(res=RES, supersampling=f"{SS}x{SS} (baked at {RES * SS})", margin=MARGIN, cage=True, max_ray_m=RAY_MAX, ao_samples=AO_SAMPLES, ao_distance_m=AO_DIST,
                           curvature=f"AO-local inside/outside, {CURV_DIST * 1e3:.0f} mm, {CURV_SAMPLES} samples")
    os.makedirs(SCR, exist_ok=True)
    json.dump(rep, open(os.path.join(SCR, f"bake_{STEP}.json"), "w"), indent=1, default=float)
    print(f"{'PASS' if rep['missed_pct'] < 0.05 else 'FAIL'} ray misses: {rep['missed_texels']} of {rep['uv_texels']} texels ({rep['missed_pct']} %)")
    print(f"{'PASS' if rep['foreign_hits_texels'] == 0 else 'CHECK'} hit distance: {rep['hit_dist_mm']}, {rep['foreign_hits_texels']} texels hit > {FOREIGN * 1e3:.0f} mm away")
    for c in rep["foreign_cells"][:10]: print(f"     far hits: {c}")
    for c in rep.get("miss_cells", [])[:6]: print(f"     misses: {c}")
    print(f"INFO ID texels: {rep['id_texels']}, unassigned {rep['id_unassigned_texels']}")
    print(f"INFO bake seconds: {rep['seconds']}")


# --------------------------------------------------------------------------- renders


VIEWS = {  # name: (camera spec cradle-local, look-at, lens or ("ortho", scale))
    "34": ([-2.9, 2.4, -3.2], [0, 0.9, 0], 40),
    "front": ([0, 1.0, -8], [0, 1.0, 0], ("ortho", 3.4)),
    "back34": ([2.9, 2.2, 3.2], [0, 0.8, 0], 40),
    "close_turntable": ([-0.95, 0.80, -0.75], [-0.41, 0.29, -0.29], 45),
    "close_pin_drum": ([1.05, 0.55, -0.85], [0.40, 0.62, -0.10], 45),
    "close_column_panel": ([0.28, 0.80, -0.95], [0.0, 0.56, -0.224], 45),
    "close_gusset": ([1.20, 1.25, -0.95], [0.78, 1.53, -0.09], 45),
}


def cam(view):
    loc, look, lens = VIEWS[view]
    if isinstance(lens, tuple): return C.camera([loc[0], loc[1], loc[2] + CZ], [look[0], look[1], look[2] + CZ], ortho=lens[1])
    return C.camera([loc[0], loc[1], loc[2] + CZ], [look[0], look[1], look[2] + CZ], lens=lens)


def renders(args):
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    sc = bpy.context.scene
    for o in bpy.data.objects: o.hide_render = True
    lo, hi, cg = objs()
    # display set: baked lows + mirrored Arm_L (shares the UVs) + left pad on the riser
    arm_l = bpy.data.objects.new("Arm_L_display", T.mirror_display(lo["Arm_R"].data, "Arm_L_display")); sc.collection.objects.link(arm_l)
    arm_l.matrix_world = Matrix.Scale(-1, 4, (1, 0, 0)) @ lo["Arm_R"].matrix_world @ Matrix.Scale(-1, 4, (1, 0, 0))
    shift = Matrix.Translation(V.to_blender((-V.PAD_X, V.PLATE_TOP + V.RISER["h"], CZ)) - V.to_blender((V.PAD_X, V.PLATE_TOP, CZ)))
    pad_l = bpy.data.objects.new("Pad_L_display", lo["Pad"].data); sc.collection.objects.link(pad_l); pad_l.matrix_world = shift @ lo["Pad"].matrix_world
    low_set = list(lo.values()) + [arm_l, pad_l]
    # high display set: same arrangement
    ml = hi["Arm_R"].data.copy(); ml.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
    bm = bmesh.new(); bm.from_mesh(ml); bmesh.ops.reverse_faces(bm, faces=bm.faces); bm.to_mesh(ml); bm.free()
    hl = bpy.data.objects.new("ArmL_high_display", ml); sc.collection.objects.link(hl)
    hpl = bpy.data.objects.new("PadL_high_display", hi["Pad"].data); sc.collection.objects.link(hpl); hpl.matrix_world = shift @ hi["Pad"].matrix_world
    high_set = list(hi.values()) + [hl, hpl]
    for o in high_set: o.hide_render = True
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 64; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000; sc.view_settings.view_transform = 'AgX'
    w = sc.world or bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.055, 0.06, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    fl = bpy.data.meshes.new("Floor"); fl.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("Floor", fl); sc.collection.objects.link(fo)
    ld = bpy.data.lights.new("Sun", 'SUN'); ld.energy = 3.5; ld.angle = math.radians(2)
    sun = bpy.data.objects.new("Sun", ld); sc.collection.objects.link(sun)
    dvec = V.to_blender((-0.55, 0.7, -0.45 + CZ)) - V.to_blender((0, 0, CZ)); dvec.normalize()
    sun.rotation_euler = (-dvec).to_track_quat('-Z', 'Y').to_euler()
    nimg = bpy.data.images.load(os.path.join(OUT, f"T_Cradle_Normal_blender{STEP}.png"))
    aimg = bpy.data.images.load(os.path.join(OUT, f"T_Cradle_AO_blender{STEP}.png"))
    baked = T.display_material("baked", nimg, aimg); grey = T.display_material("grey")
    for o in low_set: o.data.materials.clear(); o.data.materials.append(baked)
    for o in low_set: o.hide_render = False
    for v in VIEWS:
        cam(v); C.shot(f"cradle_v2_s{STEP}_{v}.png")
    # side by side: low + bake vs high, same camera
    cam("34"); files = [os.path.join(C.RENDERS, f"cradle_v2_s{STEP}_34.png")]
    for o in low_set: o.hide_render = True
    for o in high_set:
        keep = list(o.data.materials); o.data.materials.clear(); o.data.materials.append(grey); o.hide_render = False
        for p in o.data.polygons: p.material_index = 0
    C.shot(f"cradle_v2_s{STEP}_cmp_34_high.png"); files.append(os.path.join(C.RENDERS, f"cradle_v2_s{STEP}_cmp_34_high.png"))
    T.sheet(files, os.path.join(C.RENDERS, f"cradle_v2_s{STEP}_cmp_34_lowbake_vs_high.png"))
    os.remove(files[1])


# --------------------------------------------------------------------------- export


README = """Cradle (LAB_HERO_Cradle) - Substance Painter bake set, Step {step} ({date})
Generated by Tools/Blender/heroes/cradle_v2_bake_final.py (export). Units: metres, FBX axis per EXPORT_CONTRACT.
POSE: all three files are ASSEMBLED in the closed pose. The cradle origin (floor centre) is at the world origin;
Base, Arm_R (closed, 0 deg), Pad_R and Riser_L sit where they are in the game. Each part's low, high and cage got the
same transform, so they line up. Not in the bake set (shared UVs, baked once through their twin): Arm_L (= Arm_R,
mirrored) and Pad_L (= Pad_R).

FILES
  Cradle_low.fbx    the low-poly (hero mode: triangulated, custom normals, MikkTSpace tangents): the same meshes
                    Unity gets, but assembled for baking (Unity needs the parts at their own pivots: separate export
                    at the Unity import step). One material M_LAB_HERO_Cradle = one texture set. Meshes: {lows}
  Cradle_high.fbx   the high-poly bake source, one mesh per part: {highs}
                    Carries the ID vertex colour (colour set "ID") and its own normals.
  Cradle_cage.fbx   the bake cages: copies of the lows (same vertices, same order, same UVs) pushed out just far enough
                    to enclose the high. Its meshes carry the LOW names on purpose ({lows}), so the cage matches the
                    low mesh by mesh name and by vertex order.
  _superseded_5a_AI\\  the old Step 5a AI-based exports, renamed OLD_5a_*. Do not load them.
  _superseded_6b\\     the Step 6b set (16-segment turntable / rings: slivers at their foot). Do not load them.
                    Step 6c: the turntable and rings 2/3 have 32 segments in the low; the low changed, so an
                    existing Painter project needs the new low (Edit > Project configuration) and a full re-bake.

PAINTER: NEW PROJECT
  File: Cradle_low.fbx, Normal map format: OpenGL, Compute tangent space per fragment: ON (MikkTSpace),
  Document resolution 2048, UV tile workflow off.

BAKE MESH MAPS (Texture Set Settings > Bake Mesh Maps), common parameters
  Output size            2048
  Dilation width         16 px
  Antialiasing           Subsampling 4x4 (2x2 for quick tests)
  High definition meshes Cradle_high.fbx
  Match                  By Mesh Name (low suffix _low, high suffix _high)
  Use Cage               ON, Cage file: Cradle_cage.fbx (max frontal/rear distance are not used with a cage)
  Average normals        n/a with a cage
  Ignore backface        ON

MAPS TO BAKE
  Normal                 OpenGL (project setting), tangent space
  World space normal     default
  ID                     Color Source: Vertex Color (colour set "ID")
  Ambient occlusion      Self Occlusion: Only Same Mesh Name (the arms move; no baked arm shadow on the base)
  Curvature              default (from mesh)
  Position               default
  Thickness              default

ID COLOURS (sRGB, exact values)
{ids}

CHECKS DONE IN BLENDER (same set, same cage, Cycles): see Documentation/HERO_SPEC.md section 3, Steps 6b / 6c.
"""


def export(args):
    import env_kit_generator as K
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    os.makedirs(MESH, exist_ok=True)
    # (the 5a AI exports were moved to _superseded_5a_AI/OLD_5a_* once, by the first 6b export; not repeated: it
    # would now move the 6b files over them)
    sc = bpy.context.scene
    lo, hi, cg = objs()
    mat = bpy.data.materials.get("M_LAB_HERO_Cradle") or bpy.data.materials.new("M_LAB_HERO_Cradle")
    for o in list(bpy.data.objects):                     # free the export names
        if o.name.endswith("_low") or o.name.endswith("_high"): o.name = o.name + "_src"
    out = {}

    def write(objs_, fn, hero, colours=False):
        for o in bpy.data.objects: o.select_set(False)
        for o in objs_: o.select_set(True)
        bpy.context.view_layer.objects.active = objs_[0]
        s = dict(filepath=os.path.join(MESH, fn), check_existing=False, use_selection=True, object_types={'MESH'},
                 global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', use_space_transform=True,
                 bake_space_transform=True, axis_forward='-Z', axis_up='Y', add_leaf_bones=False, bake_anim=False,
                 use_mesh_modifiers=False, mesh_smooth_type='OFF', use_triangles=False, use_tspace=hero,
                 colors_type='SRGB' if colours else 'NONE')
        bpy.ops.export_scene.fbx(**s)
        out[fn] = dict(objects={o.name: dict(verts=len(o.data.vertices), tris=len(o.data.polygons)) for o in objs_},
                       mb=round(os.path.getsize(s["filepath"]) / 2 ** 20, 2))
        print(f"EXPORT {fn}: {out[fn]}")

    def at_identity(me, name):
        o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); return o
    # ASSEMBLED closed pose: every part where it sits in the game, cradle origin (floor centre) at the world origin.
    # The same transform for each part's low, cage and high (pure translations: normals, UVs, colours unchanged).
    asm = Matrix.Translation(-V.to_blender((0.0, 0.0, CZ)))
    # lows: the bake lows (triangulated export copies)
    xl = []
    for k in PARTS:
        me = lo[k].data.copy(); me.transform(asm @ lo[k].matrix_world); me.name = f"{k}_low"
        me.materials.clear(); me.materials.append(mat)
        xl.append(at_identity(me, f"{k}_low"))
    write(xl, "Cradle_low.fbx", True)
    for o in xl: bpy.data.objects.remove(o)
    # cages: same names as the lows (vertex order identical to Cradle_low.fbx)
    xc = []
    for k in PARTS:
        me = cg[k].data.copy(); me.transform(asm @ cg[k].matrix_world); me.name = f"{k}_low"
        me.materials.clear(); me.materials.append(mat)
        assert len(me.vertices) == len(lo[k].data.vertices)
        xc.append(at_identity(me, f"{k}_low"))
    write(xc, "Cradle_cage.fbx", True)
    for o in xc: bpy.data.objects.remove(o)
    # highs: assembled the same way, triangulated here (custom normals carried explicitly), ID colours kept
    xh = []
    for k in PARTS:
        me = hi[k].data.copy(); me.transform(asm @ hi[k].matrix_world)
        for a in ("idg", "det", "rf"):
            if a in me.attributes: me.attributes.remove(me.attributes[a])
        tmp = at_identity(me, f"{k}_high_tmp")
        c = K.triangulated_export_copy(tmp); bpy.data.objects.remove(tmp)
        c.name = f"{k}_high"; c.data.name = f"{k}_high"; c.data.materials.clear(); c.data.materials.append(mat)
        assert "ID" in c.data.color_attributes
        xh.append(c)
    write(xh, "Cradle_high.fbx", False, colours=True)
    ids = "\n".join(f"  {n:<24s} R {c[0]:3d}  G {c[1]:3d}  B {c[2]:3d}   #{c[0]:02X}{c[1]:02X}{c[2]:02X}" for _, (n, c) in H.ID_GROUPS.items())
    names = lambda suf: ", ".join(f"{k}{suf}" for k in PARTS)
    open(os.path.join(MESH, "README.txt"), "w", encoding="utf-8", newline="\r\n").write(
        README.format(step=STEP, date=time.strftime("%Y-%m-%d"), lows=names("_low"), highs=names("_high"), ids=ids))
    out["pose"] = "assembled closed pose, cradle origin at the world origin"
    json.dump(out, open(os.path.join(SCR, f"export_{STEP}.json"), "w"), indent=1)
    print("WROTE README.txt")


def verify(args):
    """re-import the three files into an empty scene (world space, metres): names, vertex counts, cage = low topology,
    ID colours; each low on its high (low vertices to the high surface) and the assembled placement"""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    res = {}
    for fn in ("Cradle_low.fbx", "Cradle_cage.fbx", "Cradle_high.fbx"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=os.path.join(MESH, fn))
        bpy.context.view_layer.update()
        res[fn] = {}
        for o in bpy.data.objects:
            if o.type != 'MESH': continue
            W = np.array(o.matrix_world); co = np.array([v.co[:] for v in o.data.vertices]) @ W[:3, :3].T + W[:3, 3]
            o.data.calc_loop_triangles()
            res[fn][o.name] = dict(verts=len(o.data.vertices), faces=len(o.data.polygons), uv=len(o.data.uv_layers),
                                   colours=[x.name for x in o.data.color_attributes],
                                   ngons=sum(1 for p in o.data.polygons if len(p.vertices) > 3), co=co,
                                   tris=[tuple(t.vertices) for t in o.data.loop_triangles])
    ok = True
    for k in PARTS:
        l, c, h = res["Cradle_low.fbx"].get(f"{k}_low"), res["Cradle_cage.fbx"].get(f"{k}_low"), res["Cradle_high.fbx"].get(f"{k}_high")
        good = l is not None and c is not None and h is not None and l["verts"] == c["verts"] and l["faces"] == c["faces"] \
            and "ID" in h["colours"] and l["ngons"] == 0
        if not good:
            ok = False; print(f"FAIL {k}: missing mesh, topology mismatch, n-gons or no ID colours"); continue
        push = np.linalg.norm(c["co"] - l["co"], axis=1)
        tree = BVHTree.FromPolygons(h["co"].tolist(), h["tris"], all_triangles=True)
        d = np.array([tree.find_nearest(Vector(p))[3] for p in l["co"]])
        on = float(np.median(d)) < 0.002 and float(d.max()) < 0.03          # bevel corners and the circle bulge allowed
        ok &= on
        S = np.column_stack((-l["co"][:, 0], l["co"][:, 2], -l["co"][:, 1]))  # Blender world -> spec axes, cradle origin
        a_, b_ = S.min(0), S.max(0)
        print(f"{'PASS' if on else 'FAIL'} {k}: low {l['verts']} v / {l['faces']} tris = cage {c['verts']} v "
              f"(push {1e3 * push.min():.1f}-{1e3 * push.max():.1f} mm), ID on the high; low on high: median "
              f"{1e3 * np.median(d):.2f} mm, max {1e3 * d.max():.1f} mm; bounds x {a_[0]:+.3f}..{b_[0]:+.3f}, "
              f"y {a_[1]:.3f}..{b_[1]:.3f}, z {a_[2]:+.3f}..{b_[2]:+.3f}")
    print(f"{'PASS' if ok else 'FAIL'} export verify")


# --------------------------------------------------------------------------- Step 6c: round-part foot check


# flat faces at the foot of a round wall: name -> (floor y, wall semi-axes (x, z), outer limit in wall units). The circle
# bulge of the high between two low facets bakes into the floor next to the wall as a crescent ("sliver")
FOOT_ZONES = {
    "trough floor (turntable foot)": (0.253, (0.516, 0.516), 0.66 / 0.516),
    "turntable top (ring 2 foot)": (0.333, (0.385, 0.385), 0.497 / 0.385),
    "ring 2 step (ring 3 foot)": (0.356, (0.293, 0.267), 0.385 / 0.293),
}
FOOT_BAND = 0.030                        # only the floor band this close to the low's wall foot (beyond: other bevels)
SLIVER_DEG = 20.0                        # floor texel whose baked normal tilts more than this: sliver
SEAM_ANGLES = [22.5 + 45 * k for k in range(8)]   # turntable radial seams (real grooves, excluded)


def _texel_positions(lo, faces_sel):
    """(label image, spec cradle-local position per texel) for the selected triangles of a triangulated low"""
    me = lo.data; uvd = me.uv_layers.active.data; me.calc_loop_triangles()
    W = np.array(lo.matrix_world)
    lab = np.zeros((RES, RES), np.int32); pos = np.zeros((RES, RES, 3), np.float32)
    for lt in me.loop_triangles:
        z = faces_sel(lt)
        if not z: continue
        U = np.array([uvd[li].uv[:] for li in lt.loops]) * RES
        Pw = np.array([me.vertices[v].co[:] for v in lt.vertices]) @ W[:3, :3].T + W[:3, 3]
        P = B.spec_local(Pw)
        x0, y0 = np.floor(U.min(0)).astype(int); x1, y1 = np.ceil(U.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, RES), min(y1, RES)
        if x1 <= x0 or y1 <= y0: continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        a, b, c = U; d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12: continue
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d; l3 = 1 - l1 - l2
        m = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        lab[y0:y1, x0:x1][m] = z
        pos[y0:y1, x0:x1][m] = (l1[m, None] * P[0] + l2[m, None] * P[1] + l3[m, None] * P[2])
    return lab, pos


def sliver(args):
    """-- sliver <step> <low segments>: baked normal on the floor at the foot of the turntable / rings (Base, maps of
    Substance/Cradle/Bake_<step>): texels tilting > SLIVER_DEG, their area, and how far from the low's wall foot they
    reach (the visible sliver width; the 3 mm fillet of the high accounts for ~3 mm of it). Radial seams excluded."""
    step, nseg = args[0], int(args[1])
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    lo = bpy.data.objects["Base_bakelow"]; me = lo.data
    W = np.array(lo.matrix_world); names = list(FOOT_ZONES)

    def sel(lt):
        Pw = np.array([me.vertices[v].co[:] for v in lt.vertices]) @ W[:3, :3].T + W[:3, 3]
        c = B.spec_local(Pw).mean(0); n = W[:3, :3] @ np.array(lt.normal[:])
        if n[2] / np.linalg.norm(n) < 0.99: return 0
        for i, (y, (rx, rz), lim) in enumerate(FOOT_ZONES.values()):
            e = math.hypot(c[0] / rx, c[2] / rz)
            if abs(c[1] - y) < 0.001 and 0.995 < e < lim: return i + 1
        return 0
    lab, pos = _texel_positions(lo, sel)
    img = bpy.data.images.load(os.path.join(os.path.dirname(OUT), f"Bake_{step}", f"T_Cradle_Normal_blender{step}.png"))
    img.colorspace_settings.name = 'Non-Color'
    n = pixels(img)[..., :3] * 2 - 1; n /= np.linalg.norm(n, axis=2, keepdims=True).clip(1e-6)
    tilt = np.degrees(np.arccos(np.clip(n[..., 2], -1, 1)))
    st = 2 * math.pi / nseg; texel_mm2 = 1e6 / 428.5 ** 2
    rep = {}
    for i, name in enumerate(names):
        y, (rx, rz), lim = FOOT_ZONES[name]
        m = lab == i + 1; P = pos[m]; t = tilt[m]
        phi = np.arctan2(P[:, 2] / rz, P[:, 0] / rx); rho = np.hypot(P[:, 0] / rx, P[:, 2] / rz)
        deg = np.degrees(phi) % 360
        seam = np.min(np.abs((deg[:, None] - np.array(SEAM_ANGLES)[None] + 180) % 360 - 180), 1) < 2.0   # ~13-18 mm each side (groove + its smoothed edges)
        mid = np.round(phi / st) * st                                            # facet centre (low vertices at st / 2 + k st)
        d_low = (rho * np.cos(phi - mid) - math.cos(st / 2)) * rx                # metres out from the low's wall (chord)
        keep = ~seam & (d_low < FOOT_BAND); sl = keep & (t > SLIVER_DEG)
        rep[name] = dict(texels=int(keep.sum()), sliver_texels=int(sl.sum()), sliver_area_mm2=round(float(sl.sum()) * texel_mm2, 0),
                         sliver_width_max_mm=round(1e3 * float(d_low[sl].max()), 1) if sl.any() else 0.0,
                         sliver_width_p95_mm=round(1e3 * float(np.percentile(d_low[sl], 95)), 1) if sl.any() else 0.0,
                         tilt_p99_deg=round(float(np.percentile(t[keep], 99)), 1) if keep.any() else 0.0)
        r = rep[name]
        print(f"INFO {step} {name}: {r['sliver_texels']} sliver texels (> {SLIVER_DEG:.0f} deg) of {r['texels']}, ~{r['sliver_area_mm2']:.0f} mm2, "
              f"reaching {r['sliver_width_max_mm']} mm (p95 {r['sliver_width_p95_mm']}) from the low's wall foot; tilt p99 {r['tilt_p99_deg']} deg")
    os.makedirs(SCR, exist_ok=True)
    json.dump(rep, open(os.path.join(SCR, f"sliver_{step}.json"), "w"), indent=1)


FOOT_CAM = ([-0.40, 0.98, -1.02], [-0.19, 0.26, -0.47], 60)       # front-left turntable foot from above, high sun


def foot(args):
    """-- foot <tag> <step>: the baked low (normal map only, grey) at the turntable foot -> cradle_v2_s6c_turntable_foot_<tag>.png"""
    tag, step = args[0], args[1]
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    sc = bpy.context.scene
    for o in bpy.data.objects: o.hide_render = True
    lo, hi, cg = objs()
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 64; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000; sc.view_settings.view_transform = 'AgX'
    w = sc.world or bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.055, 0.06, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    ld = bpy.data.lights.new("Sun", 'SUN'); ld.energy = 4.0; ld.angle = math.radians(1); ld.use_shadow = False
    sun = bpy.data.objects.new("Sun", ld); sc.collection.objects.link(sun)
    # shadowless, from above / along the wall / slightly behind it: the floor is lit, floor texels whose baked normal
    # tilts outward (the slivers) go dark; no cast shadow hides the foot
    dvec = V.to_blender((0.595, 0.80, 0.14 + CZ)) - V.to_blender((0, 0, CZ)); dvec.normalize()
    sun.rotation_euler = (-dvec).to_track_quat('-Z', 'Y').to_euler()
    nimg = bpy.data.images.load(os.path.join(os.path.dirname(OUT), f"Bake_{step}", f"T_Cradle_Normal_blender{step}.png"))
    mat = T.display_material("normal_only", nimg)
    for k in ("Base", "Arm_R"):
        lo[k].data.materials.clear(); lo[k].data.materials.append(mat); lo[k].hide_render = False
    loc, look, lens = FOOT_CAM
    C.camera([loc[0], loc[1], loc[2] + CZ], [look[0], look[1], look[2] + CZ], lens=lens)
    C.shot(f"cradle_v2_s6c_turntable_foot_{tag}.png")


def top(args):
    """top view of the assembled low (review file), shaded + wire -> cradle_v2_s6c_top.png"""
    objs_ = C.open_file()
    C.setup_render(size=(2000, 2000)); C.colours(objs_); C.add_wire(objs_, thickness=0.0016)
    C.camera([0, 6.0, CZ + 0.001], [0, 0, CZ], ortho=2.7)
    C.shot("cradle_v2_s6c_top.png")


def overlay(args):
    """the three files imported together, one shot: high solid (blue-grey), low wire (black), cage wire (orange)
    -> Renders/cradle_v2_s6b_export_assembled.png"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    groups = {}
    for fn in ("Cradle_low.fbx", "Cradle_high.fbx", "Cradle_cage.fbx"):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=os.path.join(MESH, fn))
        groups[fn] = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    for o in groups["Cradle_high.fbx"]: o.color = (0.45, 0.55, 0.75, 1)
    for fn, col, th in (("Cradle_low.fbx", (0.02, 0.02, 0.02, 1), 0.0025), ("Cradle_cage.fbx", (1.0, 0.5, 0.05, 1), 0.0015)):
        for o in groups[fn]:
            m = o.modifiers.new("W", 'WIREFRAME'); m.thickness = th / o.scale[0]; m.use_replace = True   # import carries a 0.01 object scale
            o.color = col
    C.setup_render(size=(2000, 1300))
    C.camera([-2.6, 2.3, -3.0], [0, 0.8, 0], lens=36)                       # cradle origin = world origin now
    C.shot("cradle_v2_s6b_export_assembled.png")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["bake"]
    {"bake": bake, "renders": renders, "export": export, "verify": verify, "overlay": overlay,
     "sliver": sliver, "foot": foot, "top": top}[argv[0]](argv[1:])
