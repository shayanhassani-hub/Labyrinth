"""
Cradle v2 Step 5b: high-poly COMPARISON TEST - the 5a AI-based highs vs a "clean" set built from the low-poly.
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake_test.py -- clean     (adds HIGH_CLEAN to the BAKE file)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake_test.py -- bake      (Cycles bakes -> Bake_test/*.png)
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_bake_test.py -- renders   (Renders/cradle_v2_s5b_*)

Clean set: Base_high_clean / Arm_R_high_clean = the low + bevel (3 segments, harden normals; per-edge widths from
the 5a measurements via bevel weights: Base 10.1 mm, tier-1 diagonals 14.0 mm, turntable 16.9 mm, arm 12.0 mm) plus
groove floaters (loose strips 0.3-2.5 mm in front of the surface whose concave profile bakes as a groove):
  plinth side panels on all 8 tier-1 faces (y 0.052-0.126; Z 0.60 m, X 0.56 m, diagonals 0.36 m long), a U-shaped
  outline around each tray, the arm's elbow joint groove (front and back faces, spec station 3). No AI geometry.
Bakes (both sets, same settings): Base_low and Arm_R_low (triangulated export copies: the MikkTSpace basis of
Cradle_low.fbx), tangent normal (OpenGL) + AO, 2048, 16 px margin, cage extrusion CAGE_EXT, max ray RAY_MAX.
Ray misses: an extra emission bake (white high, black image, no margin); black texels inside the low's UV islands.
Colour test: base colour of the tex_txt / tex_img colour highs, emission bake onto the low UVs.
"""
import bpy
import bmesh
import json
import math
import os
import sys
import time
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import cradle_v2 as V                    # noqa: E402
import cradle_v2_check as C              # noqa: E402
import cradle_v2_bake as B               # noqa: E402

OUT = r"D:/AI_Labyrinth/Substance/Cradle/Bake_test"
SCR = os.path.join(C.PROJ, "Temp", "claude", "cradle_bake")
CZ = V.CZ
RES, MARGIN = 2048, 16
CAGE_EXT, RAY_MAX = 0.025, 0.06          # rays start 25 mm outside the low and search 60 mm (5a: max 26.5 mm)
AO_SAMPLES, AO_DIST = 64, 0.25
R_BASE, R_T1, R_TT, R_ARM = 0.0101, 0.0140, 0.0169, 0.0120
GROOVE_W, TRAY_W = 0.010, 0.006
LIFT_EDGE, LIFT_BOTTOM = 0.0025, 0.0003


# --------------------------------------------------------------------------- clean highs


def spec_pt(p):
    """spec cradle-local -> Blender world"""
    return V.to_blender((p[0], p[1], p[2] + CZ))


def weighted_bevel(low, rmap, rmax, name):
    """low + bevel (3 seg, harden normals), width per edge = rmap(spec point, dihedral) via bevel weights"""
    me = low.data.copy(); me.name = name + "_src"
    bm = bmesh.new(); bm.from_mesh(me)
    lay = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
    M = low.matrix_world
    for e in bm.edges:
        e[lay] = 0.0
        if len(e.link_faces) != 2: continue
        th = e.calc_face_angle(0.0)
        if th < math.radians(30): continue
        mid = M @ ((e.verts[0].co + e.verts[1].co) / 2)
        e[lay] = rmap(B.spec_local([mid])[0]) / rmax
    bm.to_mesh(me); bm.free()
    tmp = bpy.data.objects.new(name + "_tmp", me); bpy.context.scene.collection.objects.link(tmp); tmp.matrix_world = M
    for p in me.polygons: p.use_smooth = True
    m = tmp.modifiers.new("bev", 'BEVEL'); m.segments = 3; m.width = rmax; m.limit_method = 'WEIGHT'
    m.use_clamp_overlap = True; m.offset_type = 'OFFSET'; m.harden_normals = True
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg)); out.name = name
    out.transform(M)
    bpy.data.objects.remove(tmp); bpy.data.meshes.remove(me)
    return out


def groove(bm, path, normals, width, closed):
    """concave strip along a polyline on a surface (spec cradle-local points, outward normals): edges LIFT_EDGE,
    bottom LIFT_BOTTOM in front of the surface, side slopes over a quarter of the width each"""
    prof = [(-width / 2, LIFT_EDGE), (-width / 4, LIFT_BOTTOM), (width / 4, LIFT_BOTTOM), (width / 2, LIFT_EDGE)]
    n = len(path); rows = []
    for i in range(n):
        p = np.array(path[i]); nn = np.array(normals[i]); nn /= np.linalg.norm(nn)
        a = np.array(path[(i - 1) % n] if (closed or i > 0) else path[i]); b = np.array(path[(i + 1) % n] if (closed or i < n - 1) else path[i])
        t = b - a; t -= nn * (t @ nn); t /= np.linalg.norm(t)
        s = np.cross(nn, t)
        rows.append([bm.verts.new(spec_pt(p + s * u + nn * h)) for u, h in prof])
    for i in range(n if closed else n - 1):
        r0, r1 = rows[i], rows[(i + 1) % n]
        for j in range(3):
            bm.faces.new((r0[j], r0[j + 1], r1[j + 1], r1[j]))


def rounded_rect(c, u, v, length, height, rad, seg=4):
    """closed outline of a rounded rectangle in the plane (u along, v up) centred at c"""
    pts = []
    hl, hh = length / 2 - rad, height / 2 - rad
    for cx, cy, a0 in ((hl, hh, 0), (-hl, hh, 90), (-hl, -hh, 180), (hl, -hh, 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append(c + u * (cx + rad * math.cos(a)) + v * (cy + rad * math.sin(a)))
    return pts


def plinth_panels(bm):
    t1 = V.mirror_quadrants(V.T1_Q); types = V.T1_EDGE_TYPES
    up = np.array([0.0, 1.0, 0.0]); n_made = 0
    for i, t in enumerate(types):
        if t == "F": continue
        p0 = np.array([t1[i][0], 0, t1[i][1]]); p1 = np.array([t1[(i + 1) % 16][0], 0, t1[(i + 1) % 16][1]])
        L = np.linalg.norm(p1 - p0); u = (p1 - p0) / L
        nrm = np.cross(u, up); nrm /= np.linalg.norm(nrm)
        if nrm @ ((p0 + p1) / 2) < 0: nrm = -nrm                       # outward
        length = {"Z": 0.60, "X": 0.56, "D": 0.36}[t]
        c = (p0 + p1) / 2 + up * 0.089
        pts = rounded_rect(c, u, up, length, 0.074, 0.018)
        groove(bm, pts, [nrm] * len(pts), GROOVE_W, True); n_made += 1
    return n_made


def tray_outlines(bm, base_low):
    """U outline 10 mm outside each tray floor's outer edge and ends, on the sunken ring (y 0.176)"""
    me = base_low.data; M = base_low.matrix_world; n_made = 0
    for p in me.polygons:
        if p.normal.z < 0.99: continue
        P = B.spec_local([M @ me.vertices[i].co for i in p.vertices])
        if abs(P[:, 1].mean() - V.TRAY_FLOOR) > 0.002 or len(P) != 4: continue
        r = np.hypot(P[:, 0], P[:, 2]); inner = np.argsort(r)[:2]
        outer = [i for i in range(4) if i not in inner]
        # order: inner_a -> outer_a -> outer_b -> inner_b (follow the quad's cycle)
        cyc = list(range(4)); start = next(i for i in cyc if i in inner and cyc[(i + 1) % 4] in outer)
        q = [P[(start + k) % 4] for k in range(4)]
        cen = np.mean(q, 0)
        path = []
        for k, pt in enumerate(q):
            d = pt - cen; d[1] = 0; d /= np.linalg.norm(d)
            off = pt + d * 0.012
            off[1] = V.RING_Y
            path.append(off)
        # pull the two inner ends back to 6 mm from the tier-2 wall (they run along the tray ends)
        dense = []
        for a, b in zip(path, path[1:]):
            for s in np.linspace(0, 1, 6, endpoint=False): dense.append(a + (b - a) * s)
        dense.append(path[-1])
        groove(bm, dense, [np.array([0, 1.0, 0])] * len(dense), TRAY_W, False); n_made += 1
    return n_made


def arm_elbow_groove(bm):
    """elbow joint across the front and back faces (spec station 3, right arm): strip part at z +-STRIP_Z,
    body part at z +-BODY_Z"""
    s3 = V.ARM_ST[3]; pin, pst, pout = (np.array(p) for p in s3[:3])
    for sz in (-1, 1):
        for a, b, z in ((pin + (pst - pin) * 0.04, pst - (pst - pin) * 0.04, V.STRIP_Z), (pst + (pout - pst) * 0.03, pout - (pout - pst) * 0.06, V.BODY_Z)):
            pts = [np.array([*(a + (b - a) * s), sz * z]) for s in np.linspace(0, 1, 8)]
            pts = [np.array([p[0], p[1], p[2]]) for p in pts]
            groove(bm, pts, [np.array([0, 0, sz * 1.0])] * len(pts), 0.008, False)
    return 4


def clean(args):
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    hc = B.coll("HIGH_CLEAN")
    for o in list(hc.objects): bpy.data.objects.remove(o)
    low = {k: bpy.data.objects[f"{k}_low"] for k in B.PARTS}
    t1 = B.BASE_ZONES["T1 diagonal faces: openings into the hollow shell + bowing"]

    def rbase(p):
        if t1(p): return R_T1
        if 0.24 < p[1] < 0.36 and 0.30 < math.hypot(p[0], p[2]) < 0.56: return R_TT     # turntable
        return R_BASE
    base = weighted_bevel(low["Base"], rbase, R_TT, "Base_high_clean")
    bm = bmesh.new(); bm.from_mesh(base)
    n_p = plinth_panels(bm); n_t = tray_outlines(bm, low["Base"])
    bm.to_mesh(base); bm.free()
    B.add_obj(base, "Base_high_clean", hc)
    arm = weighted_bevel(low["Arm_R"], lambda p: R_ARM, R_ARM, "Arm_R_high_clean")
    bm = bmesh.new(); bm.from_mesh(arm); n_a = arm_elbow_groove(bm); bm.to_mesh(arm); bm.free()
    B.add_obj(arm, "Arm_R_high_clean", hc)
    for o in hc.objects:
        o.color = (0.55, 0.56, 0.6, 1); o.data.calc_loop_triangles()
        print(f"CLEAN {o.name}: {len(o.data.loop_triangles)} tris")
    print(f"CLEAN floaters: {n_p} plinth panels, {n_t} tray outlines, {n_a} arm groove strips")
    for o in bpy.data.objects: o.hide_render = True
    C.setup_render(size=(1800, 1200))
    for o in hc.objects: o.hide_render = False
    bpy.data.objects["RenderFloor"].hide_render = False
    C.camera([-2.9, 2.4, CZ - 3.2], [0, 0.9, CZ]); C.shot("clean_34.png", SCR)
    C.camera([-1.75, 0.55, CZ - 1.75], [-0.80, 0.08, CZ - 0.80], lens=45); C.shot("clean_diag.png", SCR)
    bpy.data.objects.remove(bpy.data.objects["RenderFloor"])
    for o in list(bpy.data.objects):
        if o.type == 'CAMERA': bpy.data.objects.remove(o)
    bpy.ops.wm.save_as_mainfile(filepath=B.BAKE, compress=True)
    print("SAVED", B.BAKE)


# --------------------------------------------------------------------------- bake


def bake_lows():
    """triangulated export copies of Base_low and Arm_R_low in the world (closed pose)"""
    import env_kit_generator as K
    out = {}
    for k in ("Base", "Arm_R"):
        lo = bpy.data.objects[f"{k}_low"]; M = lo.matrix_world.copy()
        lo.matrix_world = Matrix.Identity(4); bpy.context.view_layer.update()
        c = K.triangulated_export_copy(lo); c.name = f"{k}_bakelow"
        lo.matrix_world = M; c.matrix_world = M
        out[k] = c
    return out


def new_image(name, data=True, float_=False, color=(0, 0, 0, 1)):
    im = bpy.data.images.get(name)
    if im: bpy.data.images.remove(im)
    im = bpy.data.images.new(name, RES, RES, alpha=False, float_buffer=float_)
    im.generated_color = color
    if data: im.colorspace_settings.name = 'Non-Color'
    return im


def target_material(obj, img):
    m = bpy.data.materials.new(f"bake_{obj.name}"); m.use_nodes = True
    n = m.node_tree.nodes.new("ShaderNodeTexImage"); n.image = img; m.node_tree.nodes.active = n
    obj.data.materials.clear(); obj.data.materials.append(m)
    return n


def emission_material(color=None, img=None, name="emit"):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for x in list(nt.nodes): nt.nodes.remove(x)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs[0], out.inputs[0])
    if img is not None:
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = img; nt.links.new(tx.outputs["Color"], em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = color
    return m


def run_bake(low, highs, img, kind, clear):
    for o in bpy.context.view_layer.objects: o.select_set(False)
    for h in highs: h.hide_render = False; h.hide_set(False); h.select_set(True)
    low.hide_render = False; low.select_set(True); bpy.context.view_layer.objects.active = low
    for n in low.data.materials[0].node_tree.nodes:
        if n.type == 'TEX_IMAGE': n.image = img; low.data.materials[0].node_tree.nodes.active = n
    kw = dict(use_selected_to_active=True, cage_extrusion=CAGE_EXT, max_ray_distance=RAY_MAX, target='IMAGE_TEXTURES',
              use_clear=clear, margin=0 if kind == "MISS" else MARGIN, margin_type='EXTEND')
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


def uv_mask(objs):
    lab = np.zeros((RES, RES), np.int32)
    for o in objs:
        me = o.data; uvd = me.uv_layers.active.data; me.calc_loop_triangles()
        tris = np.array([[uvd[li].uv[:] for li in lt.loops] for lt in me.loop_triangles])
        C.raster(tris, RES, 1, lab)
    return lab > 0


def save_png(img, fn, sixteen=False):
    """plain save (no view transform): data maps keep their values"""
    img.filepath_raw = os.path.join(OUT, fn); img.file_format = 'PNG'
    img.save()
    print("SAVED", fn)


def bake(args):
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    os.makedirs(OUT, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = AO_SAMPLES
    sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.light_settings.distance = AO_DIST
    sc.view_settings.view_transform = 'Standard'
    for o in bpy.data.objects: o.hide_render = True
    lows = bake_lows()
    for k, lo in lows.items():
        target_material(lo, None)
        # the low must not occlude its own high in the AO bake
        lo.visible_diffuse = lo.visible_glossy = lo.visible_shadow = lo.visible_transmission = lo.visible_volume_scatter = False
    mask = uv_mask(lows.values())
    white = emission_material((1, 1, 1, 1), name="emit_white")
    sets = {"ai": {"Base": [bpy.data.objects["Base_high"]], "Arm_R": [bpy.data.objects["Arm_R_high"]]},
            "clean": {"Base": [bpy.data.objects["Base_high_clean"]], "Arm_R": [bpy.data.objects["Arm_R_high_clean"]]}}
    rep = {}
    for sname, hs in sets.items():
        r = rep.setdefault(sname, {})
        nimg = new_image(f"normal_{sname}", color=(0.5, 0.5, 1.0, 1)); aimg = new_image(f"ao_{sname}", color=(1, 1, 1, 1))
        mimg = new_image(f"miss_{sname}", color=(0, 0, 0, 1))
        tN = tA = tM = 0.0
        for i, k in enumerate(("Base", "Arm_R")):
            tN += run_bake(lows[k], hs[k], nimg, "NORMAL", clear=(i == 0))
            tA += run_bake(lows[k], hs[k], aimg, "AO", clear=(i == 0))
            keep = [list(h.data.materials) for h in hs[k]]
            for h in hs[k]: h.data.materials.clear(); h.data.materials.append(white)
            tM += run_bake(lows[k], hs[k], mimg, "MISS", clear=(i == 0))
            for h, ms in zip(hs[k], keep):
                h.data.materials.clear()
                for m in ms: h.data.materials.append(m)
        px = np.empty(RES * RES * 4, np.float32); mimg.pixels.foreach_get(px); px = px.reshape(RES, RES, 4)
        missed = mask & (px[:, :, 0] < 0.5)
        r.update(normal_s=round(tN, 1), ao_s=round(tA, 1), miss_bake_s=round(tM, 1), uv_texels=int(mask.sum()),
                 missed_texels=int(missed.sum()), missed_pct=round(100 * missed.sum() / max(mask.sum(), 1), 3))
        print(f"BAKE {sname}: normal {tN:.0f} s, AO {tA:.0f} s; ray misses {missed.sum()} of {mask.sum()} texels ({r['missed_pct']} %)")
        save_png(nimg, f"T_Cradle_Normal_{sname}.png", sixteen=True); save_png(aimg, f"T_Cradle_AO_{sname}.png")
        vis = np.zeros((RES, RES, 4), np.float32); vis[..., 3] = 1; vis[mask] = (0.25, 0.25, 0.25, 1); vis[missed] = (1, 0, 0, 1)
        mimg.pixels.foreach_set(vis.ravel()); save_png(mimg, f"T_Cradle_RayMiss_{sname}.png")
    # colour test
    for tag in ("TXT", "IMG"):
        cimg = new_image(f"color_{tag.lower()}", data=False, color=(0.5, 0.5, 0.5, 1))
        tt = 0.0
        for i, k in enumerate(("Base", "Arm_R")):
            h = bpy.data.objects[f"{k}_high_col{tag}"]
            keep = list(h.data.materials)
            src = B.base_color_image(keep[0]) if keep and keep[0].node_tree else None
            h.data.materials.clear()
            h.data.materials.append(emission_material(img=src, name="emit_tex") if src else emission_material(B.GREY))
            h.data.materials.append(emission_material(B.GREY, name="emit_grey"))
            tt += run_bake(lows[k], [h], cimg, "EMIT", clear=(i == 0))
            h.data.materials.clear()
            for m in keep: h.data.materials.append(m)
        save_png(cimg, f"T_Cradle_BaseColor_{tag.lower()}.png")
        rep[f"colour_{tag.lower()}_s"] = round(tt, 1)
        print(f"BAKE colour {tag}: {tt:.0f} s")
    rep["settings"] = dict(res=RES, margin=MARGIN, cage_extrusion_m=CAGE_EXT, max_ray_m=RAY_MAX, ao_samples=AO_SAMPLES, ao_distance_m=AO_DIST)
    os.makedirs(SCR, exist_ok=True)
    json.dump(rep, open(os.path.join(SCR, "bake_test.json"), "w"), indent=1)


# --------------------------------------------------------------------------- renders


VIEWS = {"34": ([-2.9, 2.4, -3.2], [0, 0.8, 0], 40), "plinth_front": ([-0.35, 0.55, -2.35], [0.0, 0.12, -1.2], 45),
         "turntable": ([-0.95, 0.80, -0.75], [-0.41, 0.29, -0.29], 45), "arm_root": ([1.05, 0.95, -0.95], [0.42, 0.72, 0.0], 45),
         "beam_top": ([0.75, 1.25, -0.75], [0.28, 0.74, 0.0], 45)}


def display_material(name, normal=None, ao=None, color=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    b = nt.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.45; b.inputs["Metallic"].default_value = 0.3
    base = (0.5, 0.5, 0.5, 1)
    col_out = None
    if color is not None:
        tc = nt.nodes.new("ShaderNodeTexImage"); tc.image = color; col_out = tc.outputs["Color"]
        b.inputs["Metallic"].default_value = 0.0
    if ao is not None:
        ta = nt.nodes.new("ShaderNodeTexImage"); ta.image = ao; ta.image.colorspace_settings.name = 'Non-Color'
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        sock = lambda coll, ident: next(x for x in coll if x.identifier == ident)
        sock(mix.inputs, "Factor_Float").default_value = 1.0
        if col_out is not None: nt.links.new(col_out, sock(mix.inputs, "A_Color"))
        else: sock(mix.inputs, "A_Color").default_value = base
        nt.links.new(ta.outputs["Color"], sock(mix.inputs, "B_Color")); col_out = sock(mix.outputs, "Result_Color")
    if col_out is not None: nt.links.new(col_out, b.inputs["Base Color"])
    else: b.inputs["Base Color"].default_value = base
    if normal is not None:
        tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = normal; tn.image.colorspace_settings.name = 'Non-Color'
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.space = 'TANGENT'
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def mirror_display(src, name):
    """x-mirrored copy with the corner normals and UVs mirrored too (winding reversed)"""
    src.calc_loop_triangles()
    verts = [(-v.co.x, v.co.y, v.co.z) for v in src.vertices]
    cn = [tuple(c.vector) for c in src.corner_normals]; uv = src.uv_layers.active.data
    faces, nrm, uvs = [], [], []
    for p in src.polygons:
        li = list(p.loop_indices)[::-1]
        faces.append([src.loops[i].vertex_index for i in li])
        nrm += [(-cn[i][0], cn[i][1], cn[i][2]) for i in li]; uvs += [tuple(uv[i].uv) for i in li]
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    lay = me.uv_layers.new(name="UVMap")
    for i, u in enumerate(uvs): lay.data[i].uv = u
    for p in me.polygons: p.use_smooth = True
    me.normals_split_custom_set(nrm)
    return me


def sheet(files, out):
    ims = [bpy.data.images.load(f) for f in files]
    w, h = ims[0].size; gap = 12
    px = np.ones((h, w * len(ims) + gap * (len(ims) - 1), 4), np.float32)
    for i, im in enumerate(ims):
        a = np.empty(w * h * 4, np.float32); im.pixels.foreach_get(a)
        px[:, i * (w + gap): i * (w + gap) + w] = a.reshape(h, w, 4)
    o = bpy.data.images.new("sheet", px.shape[1], h, alpha=False); o.pixels.foreach_set(px.ravel())
    o.filepath_raw = out; o.file_format = 'PNG'; o.save(); print("SHEET", os.path.basename(out))


def renders(args):
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    sc = bpy.context.scene
    for o in bpy.data.objects: o.hide_render = True
    lows = bake_lows()
    # display set: baked Base + Arm_R, the mirrored Arm_L (shares the UVs), pads and riser in plain grey
    arm_l_me = mirror_display(lows["Arm_R"].data, "Arm_L_display")
    arm_l = bpy.data.objects.new("Arm_L_display", arm_l_me); sc.collection.objects.link(arm_l)
    arm_l.location = V.to_blender((-V.PIN_X, V.PIN_Y, CZ))
    pad_l = bpy.data.objects.new("Pad_L_display", bpy.data.objects["Pad_low"].data); sc.collection.objects.link(pad_l)
    pad_l.location = V.to_blender((-V.PAD_X, V.PLATE_TOP + V.RISER["h"], CZ))
    grey = display_material("grey_plain")
    others = [bpy.data.objects["Pad_low"], bpy.data.objects["Riser_low"], pad_l]
    baked = [lows["Base"], lows["Arm_R"], arm_l]
    for o in others: o.data.materials.clear(); o.data.materials.append(grey)
    for o in others + baked: o.hide_render = False
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 64; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000; sc.view_settings.view_transform = 'AgX'
    w = sc.world or bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.055, 0.06, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    fl = bpy.data.meshes.new("Floor"); fl.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("Floor", fl); sc.collection.objects.link(fo)
    ld = bpy.data.lights.new("Sun", 'SUN'); ld.energy = 3.5; ld.angle = math.radians(2)
    sun = bpy.data.objects.new("Sun", ld); sc.collection.objects.link(sun)
    d = V.to_blender((-0.55, 0.7, -0.45 + CZ)) - V.to_blender((0, 0, CZ)); d.normalize()
    sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    imgs = {}
    for s in ("ai", "clean"):
        imgs[s] = (bpy.data.images.load(os.path.join(OUT, f"T_Cradle_Normal_{s}.png")), bpy.data.images.load(os.path.join(OUT, f"T_Cradle_AO_{s}.png")))
    mats = {s: display_material(f"disp_{s}", *imgs[s]) for s in imgs}
    for view, (loc, look, lens) in VIEWS.items():
        C.camera([loc[0], loc[1], loc[2] + CZ], [look[0], look[1], look[2] + CZ], lens=lens)
        files = []
        for s in ("ai", "clean"):
            for o in baked: o.data.materials.clear(); o.data.materials.append(mats[s])
            fn = f"cradle_v2_s5b_cmp_{view}_{s}.png"; C.shot(fn); files.append(os.path.join(C.RENDERS, fn))
        sheet(files, os.path.join(C.RENDERS, f"cradle_v2_s5b_cmp_{view}.png"))
    C.camera([-2.9, 2.4, -3.2 + CZ], [0, 0.8, CZ], lens=40)
    for tag in ("txt", "img"):
        col = bpy.data.images.load(os.path.join(OUT, f"T_Cradle_BaseColor_{tag}.png"))
        m = display_material(f"col_{tag}", imgs["clean"][0], imgs["clean"][1], col)
        for o in baked: o.data.materials.clear(); o.data.materials.append(m)
        C.shot(f"cradle_v2_s5b_color_{tag}_34.png")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["clean"]
    {"clean": clean, "bake": bake, "renders": renders}[argv[0]](argv[1:])
