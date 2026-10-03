"""
Cradle v2 Step 5a: bake sources (<Part>_low / <Part>_high) whose shape matches the current design, so the bake
transfers detail only, never shape decisions (HERO_SPEC §3, ASSET_RULES hero workflow v1, step 6).

  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake.py -- build     (build + save BAKE file)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake.py -- check     (distances, coverage, junk)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake.py -- renders   (Renders/cradle_v2_s5a_*)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake.py -- export    (FBX for Substance)

BAKE file (D:/AI_Labyrinth/Blender/Source/Heroes/Cradle/LAB_HERO_Cradle_v2_bake.blend), everything in the
assembled closed pose (world = cradle at spec (0, 0, 4.69)):
  LOW        Base_low, Arm_R_low, Pad_low, Riser_low   (cradle_v2.build(); Arm_L shares Arm_R's UVs: not baked)
  HIGH       Base_high  = fitted, symmetrized AI static body (AI_A_Static_sym) minus the c) junk zones
                          (cradle_v2_check.JUNK), each hole filled with a patch = bevelled low-poly (3 segments,
                          radius estimated from the AI's own edges next to the zone), cut 20 mm beyond the hole and
                          sunk 1 mm, so it overlaps under the remaining AI surface (no gaps for rays)
             Arm_R_high = fitted AI right arm minus the root fins / shoe (patch: bevelled low root + boss) and
                          minus the one-sided recess (patch: the AI's own +Z side mirrored to -Z)
             Pad_high, Riser_high = bevelled lows
  COLOR_IMG / COLOR_TXT  the textured AI model (tex_img, tex_txt; plinth symmetrized as in Step 2) split per part
                          (each face to the nearest split part), same junk zones removed, the same patches added in
                          flat neutral grey. UVs + texture kept, base colour also written to a corner colour
                          attribute ("Col") for a vertex-colour bake.
The AI working file is only read (objects appended), never saved.
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
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import cradle_v2 as V                    # noqa: E402
import cradle_v2_check as C              # noqa: E402

AI_BLEND = r"D:/AI_Labyrinth/Blender/Source/Heroes/Cradle/LAB_HERO_Cradle_AI.blend"
BAKE = r"D:/AI_Labyrinth/Blender/Source/Heroes/Cradle/LAB_HERO_Cradle_v2_bake.blend"
EXPORT_DIR = r"D:/AI_Labyrinth/Substance/Cradle/Mesh"
CACHE = os.path.join(C.PROJ, "Temp", "claude", "cradle_ai")
SCR = os.path.join(C.PROJ, "Temp", "claude", "cradle_bake")
CZ = V.CZ
PATCH_MARGIN = 0.020              # patch reaches this far beyond the removed AI region
PATCH_SINK = 0.001                # and sits this far under the surface
PATCH_REACH = 0.040               # patch faces with a vertex this close to a removed AI face are kept too
DILATE = 0.012                    # AI removal grown by this around each zone (no torn fringes at the border)
FRAGMENT_FACES = 300              # disconnected AI pieces smaller than this near a zone are removed
BEVEL_SEG = 3
GREY = (0.5, 0.5, 0.5, 1.0)
PARTS = {"Base": "LAB_HERO_Cradle_Base_01", "Arm_R": "LAB_HERO_Cradle_Arm_R_01",
         "Pad": "LAB_HERO_Cradle_Pad_R_01", "Riser": "LAB_HERO_Cradle_Riser_L_01"}
BASE_ZONES = {k: f for k, (f, w) in C.JUNK.items() if w == "base"}
ARM_ZONES = {k: f for k, (f, w) in C.JUNK.items() if w == "arm"}
RECESS = "arm front/back asymmetric recess (z- side only)"
ARM_Z0 = 0.002                    # arm mid-plane (spec z 4.692, cradle-local)


# --------------------------------------------------------------------------- frames and mesh arrays


def spec_local(P):
    """Blender world (N,3) -> spec cradle-local"""
    P = np.asarray(P, float)
    return np.column_stack((-P[:, 0], P[:, 2], -P[:, 1] - CZ))


def in_zone(fn, pts, margin=0.0):
    """zone test on spec cradle-local points; margin: also true within margin (box offsets)"""
    offs = [(0.0, 0.0, 0.0)]
    if margin > 0:
        offs = [(a, b, c) for a in (-margin, 0, margin) for b in (-margin, 0, margin) for c in (-margin, 0, margin)]
    out = np.zeros(len(pts), bool)
    for i, p in enumerate(pts):
        out[i] = any(fn((p[0] + a, p[1] + b, p[2] + c)) for a, b, c in offs)
    return out


def zone_mask_fast(fns, pts):
    """any zone, no margin, many points (vectorised by chunks of the scalar test, with a cheap bbox prefilter)"""
    out = np.zeros(len(pts), bool)
    for fn in fns:
        for i, p in enumerate(pts):
            if not out[i] and fn(p): out[i] = True
    return out


def poly_centres(me):
    c = np.empty(len(me.polygons) * 3); me.polygons.foreach_get("center", c)
    return c.reshape(-1, 3)


def submesh(me, keep, name):
    """new mesh with the faces where keep is True (vertices compacted, UVs, colours, materials kept)"""
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    kill = [f for f, k in zip(bm.faces, keep) if not k]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    out = bpy.data.meshes.new(name); bm.to_mesh(out); bm.free()
    for m in me.materials: out.materials.append(m)
    return out


def world_mesh(obj, name):
    me = obj.data.copy(); me.name = name; me.transform(obj.matrix_world)
    return me


def tris_of(me):
    me.calc_loop_triangles()
    v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", v)
    t = np.empty(len(me.loop_triangles) * 3, np.int32); me.loop_triangles.foreach_get("vertices", t)
    return v.reshape(-1, 3), t.reshape(-1, 3)


def bvh_of(me):
    v, t = tris_of(me)
    return BVHTree.FromPolygons(v.tolist(), t.tolist(), all_triangles=True)


# --------------------------------------------------------------------------- patches


def bevelled(obj, width, name, subdiv=0):
    """world-space copy of a low with a 3-segment bevel (angle limit 30 deg, clamped), modifiers applied"""
    tmp = bpy.data.objects.new(name + "_tmp", obj.data.copy()); bpy.context.scene.collection.objects.link(tmp)
    tmp.matrix_world = obj.matrix_world
    m = tmp.modifiers.new("bev", 'BEVEL'); m.segments = BEVEL_SEG; m.width = width; m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(30); m.use_clamp_overlap = True; m.offset_type = 'OFFSET'; m.harden_normals = False
    if subdiv:
        sd = tmp.modifiers.new("sub", 'SUBSURF'); sd.subdivision_type = 'SIMPLE'; sd.levels = sd.render_levels = subdiv
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg)); me.name = name
    me.transform(tmp.matrix_world)
    tm = tmp.data; bpy.data.objects.remove(tmp); bpy.data.meshes.remove(tm)
    return me


def edge_radius(low, ai_tree, zone_fn, near=True):
    """AI edge rounding next to a zone: for convex low edges >= 60 deg within 0.3 m of the zone (outside it), the
    gap g from the sharp low corner to the AI surface gives r = g / (sec(theta/2) - 1). Median, 2..20 mm."""
    bm = bmesh.new(); bm.from_mesh(low.data); bm.transform(low.matrix_world)
    rs = []
    for e in bm.edges:
        if len(e.link_faces) != 2 or not e.is_convex: continue
        th = e.calc_face_angle(0.0)
        if th < math.radians(60): continue
        mid = (e.verts[0].co + e.verts[1].co) / 2
        p = spec_local([mid])[0]
        if zone_fn(p) or (near and not in_zone(zone_fn, [p], 0.3)[0]): continue
        hit = ai_tree.find_nearest(mid)
        if hit[0] is None or hit[3] > 0.03: continue
        rs.append(hit[3] / (1 / math.cos(th / 2) - 1))
    bm.free()
    rs = [r for r in rs if 0.001 < r < 0.05]
    return (float(np.clip(np.median(rs), 0.002, 0.020)), len(rs)) if rs else (0.006, 0)


def patch_from_low(low, zone_fn, width, name, removed=None):
    """bevelled low (subdivided twice, so the selection is fine-grained): the faces whose centre is in the zone +
    margin, or with any vertex within PATCH_REACH of a removed AI face (so holes at the zone border are covered
    even where the low face is large or the removed junk bowed away from the low); sunk PATCH_SINK"""
    me = bevelled(low, width, name, subdiv=2)
    keep = in_zone(zone_fn, spec_local(poly_centres(me)), PATCH_MARGIN)
    if removed is not None and len(removed):
        kd = KDTree(len(removed))
        for i, q in enumerate(removed): kd.insert(q, i)
        kd.balance()
        near = np.array([kd.find(v.co)[2] < PATCH_REACH for v in me.vertices])
        pv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", pv)
        ls = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("loop_start", ls)
        lt = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("loop_total", lt)
        keep |= np.array([near[pv[a:a + n]].any() for a, n in zip(ls, lt)])
    sub = submesh(me, keep, name); bpy.data.meshes.remove(me)
    bm = bmesh.new(); bm.from_mesh(sub); bm.normal_update()
    for v in bm.verts: v.co -= v.normal * PATCH_SINK
    bm.to_mesh(sub); bm.free()
    return sub


def mirrored_recess_patch(arm_me, name):
    """the AI arm's +Z side of the recess region (grown by the margin) mirrored to -Z about the arm mid-plane"""
    fn = ARM_ZONES[RECESS]
    P = spec_local(poly_centres(arm_me))
    mir = P.copy(); mir[:, 2] = 2 * ARM_Z0 - mir[:, 2]                  # source faces: their mirror lies in the zone
    keep = in_zone(fn, mir, PATCH_MARGIN)
    sub = submesh(arm_me, keep, name)
    bm = bmesh.new(); bm.from_mesh(sub)
    zb = -(ARM_Z0 + CZ)                                                    # mid-plane in Blender y
    for v in bm.verts: v.co.y = 2 * zb - v.co.y
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.normal_update()
    for v in bm.verts: v.co -= v.normal * PATCH_SINK
    bm.to_mesh(sub); bm.free()
    return sub


def dilate(centres, removed_mask, dist):
    """also remove the faces whose centre lies within dist of a removed face centre (clean zone borders)"""
    rem = centres[removed_mask]
    if not len(rem): return removed_mask
    kd = KDTree(len(rem))
    for i, q in enumerate(rem): kd.insert(q, i)
    kd.balance()
    out = removed_mask.copy()
    for i in np.nonzero(~removed_mask)[0]:
        if kd.find(centres[i])[2] < dist: out[i] = True
    return out


def components(me):
    """face component labels (faces sharing a vertex), numpy union-find with pointer jumping"""
    v, t = tris_of(me)
    pv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", pv)
    ls = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("loop_start", ls)
    a = pv[ls]; b = pv[ls + 1]; c = pv[ls + 2]
    parent = np.arange(len(me.vertices))
    for _ in range(200):
        old = parent.copy()
        for u, w in ((a, b), (b, c), (a, c)):
            pu, pw = parent[u], parent[w]
            lo = np.minimum(pu, pw); hi = np.maximum(pu, pw)
            np.minimum.at(parent, hi, lo)
        while True:
            nxt = parent[parent]
            if np.array_equal(nxt, parent): break
            parent = nxt
        if np.array_equal(parent, old): break
    return parent[a]


def drop_fragments(me, near_pts, min_faces, reach):
    """faces of small disconnected pieces (< min_faces) near the zones: returns a keep mask"""
    lab = components(me)
    ids, cnt = np.unique(lab, return_counts=True)
    small = set(ids[cnt < min_faces].tolist())
    keep = np.ones(len(lab), bool)
    if not small or not len(near_pts): return keep
    kd = KDTree(len(near_pts))
    for i, q in enumerate(near_pts): kd.insert(q, i)
    kd.balance()
    cen = poly_centres(me)
    for i in np.nonzero(np.isin(lab, list(small)))[0]:
        if kd.find(cen[i])[2] < reach: keep[i] = False
    return keep


def join_meshes(meshes, name):
    bm = bmesh.new()
    for m in meshes: bm.from_mesh(m)
    out = bpy.data.meshes.new(name); bm.to_mesh(out); bm.free()
    return out


def tag_patch(me, is_patch):
    a = me.attributes.new("patch", 'INT', 'FACE'); a.data.foreach_set("value", [int(is_patch)] * len(me.polygons))


# --------------------------------------------------------------------------- colour meshes


def base_color_image(mat):
    for n in mat.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            l = n.inputs["Base Color"].links
            if l and l[0].from_node.type == 'TEX_IMAGE': return l[0].from_node.image
    return None


def write_vertex_colour(me, img, grey=False):
    """corner colour "Col" = base colour texture at the corner UV (nearest pixel), or flat grey"""
    n = len(me.loops)
    col = me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
    if grey or img is None or not me.uv_layers:
        col.data.foreach_set("color_srgb", np.tile(GREY, n).astype(np.float32)); return
    w, h = img.size; px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(h, w, 4)
    uv = np.empty(n * 2); me.uv_layers.active.data.foreach_get("uv", uv); uv = uv.reshape(-1, 2) % 1.0
    xi = np.clip((uv[:, 0] * w).astype(int), 0, w - 1); yi = np.clip((uv[:, 1] * h).astype(int), 0, h - 1)
    c = px[yi, xi].copy(); c[:, 3] = 1.0
    col.data.foreach_set("color_srgb", c.ravel())
    me.color_attributes.active_color = col


def grey_material():
    m = bpy.data.materials.get("M_BakePatchGrey") or bpy.data.materials.new("M_BakePatchGrey")
    m.use_nodes = True; m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = GREY
    m.diffuse_color = GREY
    return m


def symmetrized_tex_txt():
    """tex_txt mesh, world frame, plinth symmetrized exactly as Step 2 did for tex_img (cradle_ai_s2.apply)"""
    import cradle_ai_s2 as S2
    R = json.load(open(os.path.join(CACHE, "analysis.json"))); A = json.load(open(os.path.join(CACHE, "s2_apply.json")))
    B = json.load(open(os.path.join(CACHE, "build.json")))
    cx, cy = R["centre_native"]; s = R["options"]["A"]["s"]
    src = bpy.data.objects[B["objects"]["tex_txt"][0]]; root = bpy.data.objects["AI_Root"]
    neg_ok = S2.symmetrize_direction_test(); keep_negative = A["keep_side"].startswith("-X")
    me0 = src.data.copy(); me0.transform(src.matrix_basis.copy())
    me = S2.symmetrize_lower(me0, "AI_A_TexTxt_sym", A["plane_x_native"], S2.Y_CUT_SPEC / s,
                             keep_negative if neg_ok else not keep_negative)
    bpy.data.meshes.remove(me0)
    me.transform(root.matrix_world @ Matrix.Translation((-cx, -cy, 0)))
    return me


# --------------------------------------------------------------------------- build


def append_ai(names):
    with bpy.data.libraries.load(AI_BLEND, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in names]
    out = {}
    for o in dst.objects:
        if o is None: continue
        out[o.name] = o
    return out


def coll(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(c)
    return c


def add_obj(me, name, collection, mat=None):
    o = bpy.data.objects.new(name, me); collection.objects.link(o)
    if mat is not None and not me.materials: me.materials.append(mat)
    return o


def build(args):
    report = {}
    parts, arms, removed, uv_report = V.build()
    objs = {k: bpy.data.objects[v] for k, v in PARTS.items()}
    low_c = coll("LOW"); high_c = coll("HIGH"); ci_c = coll("COLOR_IMG"); ct_c = coll("COLOR_TXT"); src_c = coll("AI_SRC")
    # lows: world copies (closed pose), named <Part>_low; the cradle_v2 objects are removed afterwards
    lows = {}
    for k, o in objs.items():
        me = o.data.copy(); me.name = f"{k}_low"
        lo = bpy.data.objects.new(f"{k}_low", me); low_c.objects.link(lo); lo.matrix_world = o.matrix_world.copy()
        lows[k] = lo
    for o in list(bpy.data.objects):
        if o.name.startswith("LAB_HERO_Cradle_"): bpy.data.objects.remove(o)
    bpy.context.view_layer.update()
    # AI sources
    B = json.load(open(os.path.join(CACHE, "build.json")))
    ai = append_ai(["AI_A_Static_sym", "AI_A_Arm_R", "AI_A_Arm_L", "AI_A_TexImg_sym", "AI_Root", B["objects"]["tex_txt"][0]])
    for o in ai.values():
        if o.name not in src_c.objects: src_c.objects.link(o)
        o.hide_render = True
    static = world_mesh(ai["AI_A_Static_sym"], "AI_static_world"); arm = world_mesh(ai["AI_A_Arm_R"], "AI_armR_world")
    grey = grey_material(); patches = {"Base": [], "Arm_R": []}
    # ---- Base_high
    st_tree = bvh_of(static)
    P = spec_local(poly_centres(static))
    junk = np.zeros(len(P), bool); zrep = {}
    r_all, n_all = edge_radius(lows["Base"], st_tree, lambda p: any(f(p) for f in BASE_ZONES.values()), near=False)
    print(f"RADIUS Base, all convex edges outside the zones: {1e3*r_all:.1f} mm ({n_all} edges)")
    for zname, fn in BASE_ZONES.items():
        m = zone_mask_fast([fn], P); junk |= m
        r, n = edge_radius(lows["Base"], st_tree, fn)
        if n < 8: r = r_all                                   # too few edges next to the zone: the part's median
        rem = poly_centres(static)[m][::4]
        pm = patch_from_low(lows["Base"], fn, r, "patch_" + zname[:20], rem)
        patches["Base"].append(pm)
        zrep[zname] = dict(ai_faces_removed=int(m.sum()), bevel_radius_mm=round(1e3 * r, 1), radius_samples=n,
                           patch_faces=len(pm.polygons))
        print(f"ZONE Base | {zname}: removed {int(m.sum())} AI faces, patch {len(pm.polygons)} faces, bevel r {1e3*r:.1f} mm ({n} edges)")
    cen = poly_centres(static); junk = dilate(cen, junk, DILATE)
    clean = submesh(static, ~junk, "AI_static_clean")
    kf = drop_fragments(clean, cen[junk][::8], FRAGMENT_FACES, 0.10)
    if (~kf).any():
        c2 = submesh(clean, kf, "AI_static_clean"); bpy.data.meshes.remove(clean); clean = c2
    report["Base_cleanup"] = dict(dilated_total_removed=int(junk.sum()), fragment_faces_removed=int((~kf).sum()))
    print(f"CLEAN Base: {int(junk.sum())} AI faces removed after dilation, {int((~kf).sum())} fragment faces")
    tag_patch(clean, False)
    for pm in patches["Base"]: tag_patch(pm, True)
    base_high = add_obj(join_meshes([clean] + patches["Base"], "Base_high"), "Base_high", high_c)
    report["Base"] = zrep
    # ---- Arm_R_high
    ar_tree = bvh_of(arm)
    P = spec_local(poly_centres(arm))
    junk = np.zeros(len(P), bool); zrep = {}
    for zname, fn in ARM_ZONES.items():
        m = zone_mask_fast([fn], P); junk |= m
        if zname == RECESS:
            pm = mirrored_recess_patch(arm, "patch_recess"); r, n = 0.0, 0
        else:
            r, n = edge_radius(lows["Arm_R"], ar_tree, fn)
            if n < 8: r = edge_radius(lows["Arm_R"], ar_tree, lambda p: any(f(p) for f in ARM_ZONES.values()), near=False)[0]
            pm = patch_from_low(lows["Arm_R"], fn, r, "patch_root", poly_centres(arm)[m][::4])
        patches["Arm_R"].append(pm)
        zrep[zname] = dict(ai_faces_removed=int(m.sum()), bevel_radius_mm=round(1e3 * r, 1), radius_samples=n,
                           patch_faces=len(pm.polygons))
        print(f"ZONE Arm_R | {zname}: removed {int(m.sum())} AI faces, patch {len(pm.polygons)} faces, bevel r {1e3*r:.1f} mm")
    cen = poly_centres(arm); junk = dilate(cen, junk, DILATE)
    clean = submesh(arm, ~junk, "AI_armR_clean")
    kf = drop_fragments(clean, cen[junk][::4], FRAGMENT_FACES, 0.10)
    if (~kf).any():
        c2 = submesh(clean, kf, "AI_armR_clean"); bpy.data.meshes.remove(clean); clean = c2
    report["Arm_cleanup"] = dict(dilated_total_removed=int(junk.sum()), fragment_faces_removed=int((~kf).sum()))
    print(f"CLEAN Arm_R: {int(junk.sum())} AI faces removed after dilation, {int((~kf).sum())} fragment faces")
    tag_patch(clean, False)
    for pm in patches["Arm_R"]: tag_patch(pm, True)
    add_obj(join_meshes([clean] + patches["Arm_R"], "Arm_R_high"), "Arm_R_high", high_c)
    report["Arm_R"] = zrep
    # ---- Pad_high, Riser_high: bevelled lows
    for k, w in (("Pad", 0.0015), ("Riser", 0.0015)):
        me = bevelled(lows[k], w, f"{k}_high"); tag_patch(me, True)
        add_obj(me, f"{k}_high", high_c)
    # ---- colour meshes
    kd = {}
    for k, nm in (("Base", "AI_A_Static_sym"), ("Arm_R", "AI_A_Arm_R"), ("Arm_L", "AI_A_Arm_L")):
        me = world_mesh(ai[nm], "kd_" + k); v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3)[::2]; t = KDTree(len(v))
        for i, p in enumerate(v): t.insert(p, i)
        t.balance(); kd[k] = t; bpy.data.meshes.remove(me)
    txt_me = symmetrized_tex_txt()
    for tag, me_src, c_ in (("IMG", world_mesh(ai["AI_A_TexImg_sym"], "AI_teximg_world"), ci_c), ("TXT", txt_me, ct_c)):
        img = base_color_image(me_src.materials[0]) if me_src.materials else None
        Cc = poly_centres(me_src); owner = np.empty(len(Cc), np.int8)
        for i, p in enumerate(Cc):
            d = [kd[k].find(p)[2] for k in ("Base", "Arm_R", "Arm_L")]; owner[i] = int(np.argmin(d))
        P = spec_local(Cc)
        for oi, (k, zones) in enumerate((("Base", BASE_ZONES), ("Arm_R", ARM_ZONES))):
            keep = owner == oi
            keep &= ~zone_mask_fast(list(zones.values()), P) if keep.any() else keep
            part = submesh(me_src, keep, f"{k}_col_{tag}")
            write_vertex_colour(part, img)
            gp = []
            for pm in patches[k]:
                g = pm.copy(); g.materials.clear(); g.materials.append(grey); write_vertex_colour(g, None, grey=True); gp.append(g)
            # join keeps per-mesh materials by slot order: AI material slot 0, grey slot 1
            bm = bmesh.new(); bm.from_mesh(part)
            out = bpy.data.meshes.new(f"{k}_high_col{tag}")
            for g in gp:
                for f in g.polygons: f.material_index = 1
                bm.from_mesh(g)
            bm.to_mesh(out); bm.free()
            for m in part.materials: out.materials.append(m)
            if not out.materials: out.materials.append(grey)
            out.materials.append(grey)
            add_obj(out, f"{k}_high_col{tag}", c_)
            report.setdefault("colour", {})[f"{k}_{tag}"] = dict(ai_faces=int(keep.sum()), owner_counts=np.bincount(owner, minlength=3).tolist())
            print(f"COLOUR {tag} {k}: {int(keep.sum())} AI faces + {sum(len(g.polygons) for g in gp)} grey patch faces")
        for k in ("Pad", "Riser"):
            me = bevelled(lows[k], 0.0015, f"{k}_high_col{tag}"); me.materials.clear(); me.materials.append(grey)
            write_vertex_colour(me, None, grey=True); add_obj(me, f"{k}_high_col{tag}", c_)
    # tidy: free the temporary meshes; AI sources stay (hidden) for the before/after renders
    for me in list(bpy.data.meshes):
        if me.users == 0: bpy.data.meshes.remove(me)
    for o in high_c.objects: o.color = (0.55, 0.56, 0.6, 1)
    os.makedirs(SCR, exist_ok=True)
    json.dump(report, open(os.path.join(SCR, "build.json"), "w"), indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=BAKE, compress=True)
    print("SAVED", BAKE)


# --------------------------------------------------------------------------- check


def spec_arrays(obj):
    return C.obj_arrays(obj)


def check(args):
    bpy.ops.wm.open_mainfile(filepath=BAKE)
    lows = {k: bpy.data.objects[f"{k}_low"] for k in PARTS}
    highs = {k: bpy.data.objects[f"{k}_high"] for k in PARTS}
    allp = [spec_arrays(o) for o in lows.values()]
    VV = np.vstack([v for v, t in allp]); TT = []; off = 0
    for v, t in allp: TT.append(t + off); off += len(v)
    scene_tree = C.bvh(VV, np.vstack(TT))
    res = {}; ok_all = True
    for k in PARTS:
        lv, lt = spec_arrays(lows[k]); hv, ht = spec_arrays(highs[k])
        htree = C.bvh(hv, ht)
        p, fi = C.sample(lv, lt, spacing=0.005)
        vis = C.visible_samples(p, lv, lt, fi, scene_tree)
        p = p[vis]
        d = C.nearest(htree, p)
        bins = {}
        for q, dv in zip(p[d > 0.020], d[d > 0.020]):
            key = tuple(np.floor(q / 0.05).astype(int)); b = bins.setdefault(key, [0, 0.0, None]); b[0] += 1
            if dv > b[1]: b[1] = dv; b[2] = q
        over = sorted(bins.values(), key=lambda b: -b[1])
        fails = [b for b in over if b[1] > 0.030]
        r = dict(visible_samples=int(len(p)), max_mm=round(1e3 * d.max(), 1), p99_mm=round(1e3 * np.percentile(d, 99), 1),
                 mean_mm=round(1e3 * d.mean(), 2), over20_share_pct=round(100 * float((d > 0.02).mean()), 3),
                 over20=[dict(n=b[0], max_mm=round(1e3 * b[1], 1), at=np.round(b[2] - np.array([0, 0, CZ]), 3).tolist()) for b in over[:30]],
                 coverage_fail=[dict(n=b[0], max_mm=round(1e3 * b[1], 1), at=np.round(b[2] - np.array([0, 0, CZ]), 3).tolist()) for b in fails])
        res[k] = r
        ok = not fails; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {k}: low->high max {r['max_mm']} mm, p99 {r['p99_mm']} mm, mean {r['mean_mm']} mm, "
              f"> 20 mm on {r['over20_share_pct']} % of visible samples ({len(over)} 5 cm cells), coverage fails (> 30 mm) {len(fails)}")
        for b in r["over20"][:12]: print(f"     > 20 mm: {b['max_mm']} mm at cradle-local {b['at']} ({b['n']} samples)")
    # junk left: AI (non-patch) faces of the highs with their centre in a c) zone
    for k, zones in (("Base", BASE_ZONES), ("Arm_R", ARM_ZONES)):
        me = highs[k].data; pa = np.zeros(len(me.polygons), np.int32); me.attributes["patch"].data.foreach_get("value", pa)
        pa = pa.astype(bool)
        P = spec_local(poly_centres(me) @ np.array(highs[k].matrix_world)[:3, :3].T + np.array(highs[k].matrix_world)[:3, 3])
        left = zone_mask_fast(list(zones.values()), P[~pa])
        print(f"{'PASS' if left.sum() == 0 else 'FAIL'} {k}_high: AI faces left in the c) zones: {int(left.sum())}")
        res[k]["junk_left"] = int(left.sum())
    for k in PARTS:
        me = highs[k].data; me.calc_loop_triangles()
        res[k]["high_tris"] = len(me.loop_triangles); res[k]["high_verts"] = len(me.vertices)
        print(f"INFO {k}_high: {len(me.loop_triangles)} tris, {len(me.vertices)} verts")
    json.dump(res, open(os.path.join(SCR, "check.json"), "w"), indent=1)


# --------------------------------------------------------------------------- renders


ZONE_VIEWS = {   # zone: (part, camera spec cradle-local, look-at)
    "T1 diagonal faces: openings into the hollow shell + bowing": ("Base", [-1.75, 0.55, -1.75], [-0.80, 0.08, -0.80]),
    "T2 diagonal faces: bowed ~20 mm": ("Base", [-1.35, 0.85, -1.35], [-0.60, 0.24, -0.60]),
    "turntable rim: thin broken radial fins (hollow shell)": ("Base", [0.95, 0.85, 1.05], [0.33, 0.27, 0.42]),
    "turntable rim notches (read as damage; owner decision 3c)": ("Base", [-0.95, 0.80, -0.75], [-0.41, 0.29, -0.29]),
    "splitter cut faces on the hinge beam top": ("Base", [0.75, 1.25, -0.75], [0.28, 0.74, 0.0]),
    "old arm-root fins / shoe under the new boss": ("Arm_R", [1.05, 0.95, -0.95], [0.42, 0.72, 0.0]),
    "arm front/back asymmetric recess (z- side only)": ("Arm_R", [1.15, 1.55, -1.0], [0.65, 1.34, -0.15]),
}
SLUG = {"T1": "t1_diag", "T2": "t2_diag", "turntable rim: thin": "tt_fins", "turntable rim notches": "tt_notches",
        "splitter": "beam_top", "old arm-root": "arm_root", "arm front/back": "arm_recess"}


def slug(z):
    return next(v for k, v in SLUG.items() if z.startswith(k))


def renders(args):
    bpy.ops.wm.open_mainfile(filepath=BAKE)
    sc = bpy.context.scene
    for o in bpy.data.objects: o.hide_render = True
    C.setup_render(size=(1800, 1200))
    floor = bpy.data.objects["RenderFloor"]; floor.hide_render = False
    ai = {"Base": bpy.data.objects["AI_A_Static_sym"], "Arm_R": bpy.data.objects["AI_A_Arm_R"]}
    hi = {k: bpy.data.objects[f"{k}_high"] for k in PARTS}
    for o in list(ai.values()) + list(hi.values()): o.color = (0.55, 0.56, 0.6, 1)
    for z, (part, loc, look) in ZONE_VIEWS.items():
        cam = C.camera([loc[0], loc[1], loc[2] + CZ], [look[0], look[1], look[2] + CZ], lens=45)
        for tag, ob in (("before", ai[part]), ("after", hi[part])):
            ob.hide_render = False; C.shot(f"cradle_v2_s5a_zone_{slug(z)}_{tag}.png"); ob.hide_render = True
    for o in hi.values(): o.hide_render = False
    C.camera([0, 1.0, CZ - 8], [0, 1.0, CZ], ortho=3.4); C.shot("cradle_v2_s5a_high_front.png")
    C.camera([-2.9, 2.4, CZ - 3.2], [0, 0.9, CZ]); C.shot("cradle_v2_s5a_high_34.png")
    # low wireframe over the high
    for k in PARTS:
        lo = bpy.data.objects[f"{k}_low"]; w = lo.copy(); w.data = lo.data; sc.collection.objects.link(w)
        m = w.modifiers.new("Wire", 'WIREFRAME'); m.thickness = 0.0015; m.use_replace = True; m.use_even_offset = True
        w.hide_render = False; w.color = (0.02, 0.02, 0.02, 1)
    C.camera([1.0, 1.0, CZ - 0.9], [0.40, 0.62, CZ], lens=45); C.shot("cradle_v2_s5a_overlay_hinge.png")
    C.camera([-1.45, 0.75, CZ - 1.45], [-0.85, 0.12, CZ - 0.85], lens=40); C.shot("cradle_v2_s5a_overlay_corner.png")


# --------------------------------------------------------------------------- export


def export(args):
    import env_kit_generator as K
    bpy.ops.wm.open_mainfile(filepath=BAKE)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    sc = bpy.context.scene
    lows = {k: bpy.data.objects[f"{k}_low"] for k in PARTS}
    frame = {k: o.matrix_world.copy() for k, o in lows.items()}          # each part's own frame (pivot, closed pose)
    mat = bpy.data.materials.get("M_LAB_HERO_Cradle") or bpy.data.materials.new("M_LAB_HERO_Cradle")
    out = {}

    def write(objs, fn, hero):
        for o in bpy.data.objects: o.select_set(False)
        for o in objs: o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        s = dict(filepath=os.path.join(EXPORT_DIR, fn), check_existing=False, use_selection=True, object_types={'MESH'},
                 global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', use_space_transform=True,
                 bake_space_transform=True, axis_forward='-Z', axis_up='Y', add_leaf_bones=False, bake_anim=False,
                 use_mesh_modifiers=False)
        if hero: s.update(mesh_smooth_type='OFF', use_tspace=True, use_triangles=False)
        else: s.update(mesh_smooth_type='FACE', use_tspace=False, use_triangles=True, path_mode='COPY', embed_textures=False,
                       colors_type='SRGB')
        bpy.ops.export_scene.fbx(**s)
        tris = 0
        for o in objs: o.data.calc_loop_triangles(); tris += len(o.data.loop_triangles)
        out[fn] = dict(objects=[o.name for o in objs], tris=tris, mb=round(os.path.getsize(s["filepath"]) / 2 ** 20, 1))
        print(f"EXPORT {fn}: {out[fn]}")

    # lows: hero mode (identity transform at the part's pivot, triangulated, custom normals, MikkTSpace), one material
    ex = []
    for k, o in lows.items():
        o.matrix_world = Matrix.Identity(4); bpy.context.view_layer.update()
        c = K.triangulated_export_copy(o); c.name = f"{k}_low_x"; c.data.materials.clear(); c.data.materials.append(mat)
        ex.append((k, c))
    for k, c in ex: lows[k].name = f"{k}_low_src"; c.name = f"{k}_low"; c.data.name = f"{k}_low"
    write([c for _, c in ex], "Cradle_low.fbx", True)
    # highs and colour highs: moved into the part frames, names <Part>_high
    for coll_name, fn in (("HIGH", "Cradle_high.fbx"), ("COLOR_IMG", "Cradle_high_color_img.fbx"), ("COLOR_TXT", "Cradle_high_color_txt.fbx")):
        objs = []
        for o in bpy.data.collections[coll_name].objects:
            k = o.name.split("_high")[0]
            me = o.data.copy(); me.transform(frame[k].inverted() @ o.matrix_world)
            for x in [x for x in bpy.data.objects if x.name.startswith(f"{k}_high")]: x.name = x.name + "_src"
            c = bpy.data.objects.new(f"{k}_high", me); sc.collection.objects.link(c); me.name = f"{k}_high"
            objs.append(c)
        write(objs, fn, False)
        for c in objs:
            bpy.data.objects.remove(c)
        for x in [x for x in bpy.data.objects if x.name.endswith("_src") and "_high" in x.name]: x.name = x.name[:-4]
    # AI base colour textures next to the colour FBX files (the meshes reference them by UV)
    for tag in ("IMG", "TXT"):
        o = bpy.data.objects.get(f"Base_high_col{tag}")
        img = base_color_image(o.data.materials[0]) if o and o.data.materials else None
        if img is not None:
            fp = os.path.join(EXPORT_DIR, f"T_Cradle_AI_tex_{tag.lower()}_BaseColor.png")
            img2 = img.copy(); img2.filepath_raw = fp; img2.file_format = 'PNG'; img2.save(); out[os.path.basename(fp)] = dict(size=list(img.size))
            print("EXPORT", os.path.basename(fp))
    json.dump(out, open(os.path.join(SCR, "export.json"), "w"), indent=1)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["build"]
    {"build": build, "check": check, "renders": renders, "export": export}[argv[0]](argv[1:])
