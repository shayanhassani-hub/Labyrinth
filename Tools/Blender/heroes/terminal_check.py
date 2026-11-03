"""
Terminal (Hero 02) low-poly: validation and review renders (HERO_SPEC §5, ASSET_RULES hero standard, workflow v3).
  python (bpy 5.2.2) Tools/Blender/heroes/terminal_check.py -- <stage> [args]
stages:
  topo        tris and topology per part, bow-tie / concave quads, winding against the custom normals, planarity, flat
              shading (corner normals of flat faces), UV islands, texel density, padding (writes <WORK>/topo.json)
  clearance   button press sweep (cap vs guard / desk), terminal vs room (wall, trim, side wall, floor), display vs
              desk / wall, player reach and the spec sizes measured on the meshes
  concept <tag> [flat|baked]   concept-matched renders: the four concept cameras (3/4 master perspective, ortho
              front / top / side) fitted to the concept's framing, each saved side by side with the concept as
              <tag>_vs_concept_<view>.jpg and one sheet <tag>_vs_concept.jpg
  renders <tag>  review renders (room position, 3/4, close-ups, wireframe, UV layout, texel checker)
  shading <tag>  flat grey renders of the untextured low (no gradients on flat faces)
Everything opens the saved review file (terminal.SAVE) and never saves it. Output: <OUT_DIR> (default
D:/AI_Labyrinth/Renders/Terminal; review JPGs are copied to Documentation/Media/terminal/ by hand).
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terminal as TM                                    # noqa: E402
import gate_check as GC                                  # noqa: E402  raster labels, padding, light / scene helpers
import cradle_v2_check as CC                             # noqa: E402  quad_faults, winding, wire, checker

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WORK = "D:/AI_Labyrinth/Blender/Work/Terminal"
OUT_DIR = os.path.abspath(os.environ.get("TERMINAL_RENDERS", "D:/AI_Labyrinth/Renders/Terminal"))   # Blender maps a bare "D:/" to /d/ on Linux
REF = os.path.join(PROJ, "Documentation", "References", "Terminal")
PARTS = ["Body_01", "Button_01", "Indicators_01", "Beacon_01"]
TEX = 2048
TWIST_MAX = 0.002


def open_file():
    bpy.ops.wm.open_mainfile(filepath=TM.SAVE)
    return {n: bpy.data.objects[f"{TM.HERO}_{n}"] for n in PARTS + ["Display_01"] if f"{TM.HERO}_{n}" in bpy.data.objects}


def L(p):
    """terminal-local -> Unity world"""
    return TM.T(p)


def spec(v):
    return Vector((-v.x, v.z, -v.y))


# --------------------------------------------------------------------------- topology, UVs


def topo(args):
    objs = {k: v for k, v in open_file().items() if k != "Display_01"}
    out = {}; total = 0; ok_all = True
    for name, o in objs.items():
        me = o.data; bm = bmesh.new(); bm.from_mesh(me)
        q = sum(1 for f in bm.faces if len(f.verts) == 4); tr = sum(1 for f in bm.faces if len(f.verts) == 3)
        ng = sum(1 for f in bm.faces if len(f.verts) > 4)
        border = sum(1 for e in bm.edges if e.is_boundary)
        nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        loose = sum(1 for v in bm.verts if not v.link_faces) + sum(1 for e in bm.edges if not e.link_faces)
        zero = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
        dup = len(bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=1e-5)["targetmap"])
        inconsistent = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
        bm.free()
        me.calc_loop_triangles(); tris = len(me.loop_triangles); total += tris
        bow, conc = CC.quad_faults(me)
        wcount, _ = CC.blend_winding(o)
        twist = []
        for p in me.polygons:
            if len(p.vertices) != 4: continue
            P = [np.array(me.vertices[v].co) for v in p.vertices]
            n = np.cross(P[2] - P[0], P[3] - P[1]); ln = np.linalg.norm(n)
            if ln > 1e-12 and abs((P[1] - P[0]) @ (n / ln)) > TWIST_MAX: twist.append(p.index)
        ok = ng == 0 and nonman == 0 and loose == 0 and zero == 0 and dup == 0 and inconsistent == 0
        ok2 = not bow and not conc and not any(wcount.values())
        ok_all &= ok and ok2
        out[name] = dict(tris=tris, quads=q, tri_faces=tr, ngons=ng, open_border=border, nonmanifold=nonman, loose=loose,
                         zero_area=zero, duplicates=dup, winding_inconsistent=inconsistent, bowtie=len(bow),
                         concave=len(conc), twisted_quads=len(twist), **wcount)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {tris} tris ({q} quads, {tr} tris, {ng} n-gons), open border {border}, "
              f"non-manifold {nonman}, loose {loose}, dup {dup}, zero-area {zero}, winding {inconsistent}")
        print(f"{'PASS' if ok2 else 'FAIL'} {name} folds: bow-tie {len(bow)}, concave {len(conc)}, against custom normals "
              f"{wcount['vs_custom']}, folded pairs {wcount['folded_pairs']}, same-direction edges {wcount['same_direction_edges']}")
        print(f"INFO planarity {name}: {len(twist)} quads with diagonals > {TWIST_MAX * 1e3:.0f} mm apart")
        bent, worst = GC.flat_normals(me)
        ok_all &= bent == 0
        out[name].update(flat_faces_bent=bent, flat_bend_max_deg=round(worst, 2))
        print(f"{'PASS' if bent == 0 else 'FAIL'} {name} shading: {bent} flat faces with a corner normal > "
              f"{GC.FLAT_TOL} deg off the face normal (worst {worst:.2f} deg)")
        hidden = hidden_scan(o, objs)
        print(f"{'PASS' if not hidden else 'FAIL'} {name} hidden faces: {len(hidden)} faces fully inside another part "
              f"or behind the wall / under the floor")
        ok_all &= not hidden
    print(f"INFO total {total} tris (no LOD needed below ~10k, ASSET_RULES)")
    GC.TEX = TEX
    lab, owner = GC.raster_labels(objs)
    per = {}
    for name, o in objs.items():
        me = o.data; uv = me.uv_layers.active.data; isl = GC.uv_islands(me); acc = {}
        for p in me.polygons:
            U = np.array([uv[l].uv[:] for l in p.loop_indices]); x, y = U[:, 0], U[:, 1]
            au = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            a = acc.setdefault(isl[p.index], [0.0, 0.0]); a[0] += p.area; a[1] += au
        d = [TEX * math.sqrt(v[1] / v[0]) for v in acc.values() if v[0] > 1e-6]
        per[name] = (round(min(d)), round(float(np.median(d))), round(max(d)))
        out[name].update(islands=len(acc), area_m2=round(sum(v[0] for v in acc.values()), 3))
        print(f"INFO UV {name}: {len(acc)} islands, {out[name]['area_m2']} m2, island density min / median / max {per[name]} px/m")
    gap, border = GC.padding(lab)
    fill = (lab > 0).mean()
    ok_all &= gap is None and border >= 4
    print(f"{'PASS' if gap is None else 'FAIL'} island padding >= 8 px" + ("" if gap is None else f" (closest {gap} px)"))
    print(f"{'PASS' if border >= 4 else 'FAIL'} sheet border >= 4 px ({border} px)")
    print(f"INFO packing {fill * 100:.1f} % of the 2048 sheet")
    out["_uv"] = dict(padding_close=gap, border_px=border, fill=round(float(fill), 3), density=per)
    os.makedirs(WORK, exist_ok=True)
    np.save(os.path.join(WORK, "uv_labels.npy"), lab)
    json.dump(out, open(os.path.join(WORK, "topo.json"), "w"), indent=1)
    print("RESULT: PASS" if ok_all else "RESULT: FAIL")


def hidden_scan(o, objs):
    """faces whose centre lies inside another closed part (Body pillars / body) or behind the wall / below the floor"""
    bad = []
    W = o.matrix_world
    for p in o.data.polygons:
        c = spec(W @ p.center)
        if c.z < TM.OZ - 1e-4 or c.y < -1e-4: bad.append(p.index)
    return bad


# --------------------------------------------------------------------------- clearances


def min_gap(a_objs, b_objs):
    return GC.min_gap(a_objs, b_objs)


def clearance(args):
    objs = open_file()
    body, btn = objs["Body_01"], objs["Button_01"]
    room = TM.room_object(); bpy.context.scene.collection.objects.link(room)
    fr = TM.desk_frame(); n = Vector(fr.n)
    base = btn.location.copy()
    press = TM.to_blender(tuple(-n * TM.BUTTON_TRAVEL)) - TM.to_blender((0, 0, 0))
    worst = (1e9, None); hits = []
    for k in range(11):                                                      # press sweep 0 ... 15 mm
        btn.location = base + press * (k / 10); bpy.context.view_layer.update()
        d, at, hit = GC.min_gap([btn], [body])
        if hit: hits.append(k)
        if d < worst[0]: worst = (d, k / 10 * TM.BUTTON_TRAVEL)
    btn.location = base; bpy.context.view_layer.update()
    print(f"{'PASS' if not hits and worst[0] > 0.001 else 'FAIL'} button press sweep 0 ... {TM.BUTTON_TRAVEL * 1e3:.0f} mm "
          f"(11 steps along the desk normal): min gap cap -> body {worst[0] * 1e3:.1f} mm at {worst[1] * 1e3:.1f} mm")
    g = TM.GUARD
    rows = [("cap side -> guard hole wall (radial)", g["hole"] - TM.BUTTON_R),
            ("cap side -> collar inner wall (radial)", g["inner"] - TM.BUTTON_R),
            ("cap top above the collar top, rest", TM.BUTTON_TOP - g["top_h"]),
            ("cap top above the collar top, pressed (negative = below: guarded)", TM.BUTTON_TOP - TM.BUTTON_TRAVEL - g["top_h"]),
            ("cap above the cup floor, rest (spec 0.04)", TM.BUTTON_TOP - g["flange_h"]),
            ("cap bottom -> hole floor, pressed", (TM.BUTTON_BOTTOM - TM.BUTTON_TRAVEL) - g["hole_floor"])]
    for nme, v in rows:
        print(f"{'PASS' if v > 0 or 'pressed (negative' in nme else 'FAIL'} {nme}: {v * 1e3:.1f} mm")
    # terminal vs room
    parts = [o for k, o in objs.items() if k != "Display_01"]
    room.data.polygons.foreach_set("select", [False] * len(room.data.polygons))
    side = TM.room_object(); bpy.context.scene.collection.objects.link(side)
    bm = bmesh.new(); bm.from_mesh(side.data)                                 # trim + side wall only (the back
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if (side.matrix_world @ f.calc_center_median()).y > 2.0 - 1e-4
                               and (side.matrix_world @ f.calc_center_median()).z > 0.15 + 1e-4], context='FACES')
    bm.to_mesh(side.data); bm.free()                                          # wall face is touched by design)
    d, at, hit = GC.min_gap(parts, [side])
    print(f"{'PASS' if not hit and d > 0.004 else 'FAIL'} terminal vs floor trim and side wall: min gap {d * 1e3:.1f} mm")
    allv = np.array([tuple(spec(o.matrix_world @ v.co)) for o in parts for v in o.data.vertices])
    lo, hi = allv.min(0), allv.max(0)
    print(f"INFO terminal bounds (Unity) x {lo[0]:.3f} ... {hi[0]:.3f}, y {lo[1]:.3f} ... {hi[1]:.3f}, z {lo[2]:.3f} ... {hi[2]:.3f}")
    ok = lo[0] >= -3.4 - 1e-4 and hi[0] <= -1.0 + 1e-4 and lo[2] >= -2.0 - 1e-5 and hi[2] <= -1.2 + 1e-4 and lo[1] >= -1e-6
    print(f"{'PASS' if ok else 'FAIL'} footprint inside x -3.4 ... -1.0, z -2.0 ... -1.2 (HERO_SPEC §5); nothing behind the "
          f"wall face or below the floor (backs touch the wall face)")
    # trim clearance: nothing in x -3.4..-1.0, y 0..0.15, z -2.0..-1.95 (+ 5 mm)
    trim = [v for v in allv if v[1] < 0.15 + 1e-4 and v[2] < -1.95 + 0.005 - 1e-6]
    print(f"{'PASS' if not trim else 'FAIL'} floor trim (y 0 ... 0.15, z -2.0 ... -1.95): {len(trim)} vertices within 5 mm")
    # display
    disp = objs.get("Display_01")
    if disp:
        dv = np.array([tuple(spec(disp.matrix_world @ v.co)) for v in disp.data.vertices])
        print(f"INFO display corners (Unity): y {dv[:, 1].min():.3f} ... {dv[:, 1].max():.3f}, z {dv[:, 2].min():.3f} ... "
              f"{dv[:, 2].max():.3f}; width {np.ptp(dv[:, 0]):.3f}; spec bottom 1.10 at z 0.15 local, 8 deg lean")
        print(f"{'PASS' if dv[:, 2].min() > TM.OZ + 0.01 else 'FAIL'} display top edge {1e3 * (dv[:, 2].min() - TM.OZ):.0f} mm from the wall")
    # spec sizes measured on the mesh (vertices, terminal-local)
    bv = np.array([tuple(spec(body.matrix_world @ v.co)) for v in body.data.vertices]) - np.array((TM.OX, 0.0, TM.OZ))
    mid = np.abs(bv[:, 0]) < 0.9001
    front = bv[mid & (np.abs(bv[:, 2] - TM.DESK_FRONT_Z) < 1e-4)][:, 1].max()
    back = bv[mid & (np.abs(bv[:, 2] - TM.SLOPE_BACK_Z) < 1e-4)][:, 1].max()
    pil = bv[np.abs(bv[:, 0]) > 0.95][:, 1]
    print(f"INFO desk front edge {front:.3f} (spec 0.92; the 8 mm chamfer starts at {front:.3f}), back of the slope "
          f"{back:.3f} (spec 1.05), slope {TM.SLOPE:.0f} deg; pillar top {pil[pil < 1.2501].max():.3f} (spec 1.25)")
    # reach: standing player 0.30 in front of the pillars, shoulder 1.40 high (eye ~1.60)
    bt = Vector(TM.button_top()); sh = Vector(L((0.0, 1.40, TM.DEPTH + 0.30)))
    sh2 = Vector(L((0.0, 1.40, TM.DEPTH + 0.15)))
    print(f"INFO reach shoulder -> button top: {(bt - sh).length:.2f} m standing 0.30 in front of the pillars, "
          f"{(bt - sh2).length:.2f} m at 0.15 (comfortable arm reach ~0.60-0.70); the button is also selectable by ray")
    ind = objs.get("Indicators_01")
    if ind:
        iv = np.array([tuple(spec(ind.matrix_world @ v.co)) for v in ind.data.vertices])
        print(f"INFO switching indicators (player's right, -X): x {iv[:, 0].min():.3f} ... {iv[:, 0].max():.3f}")


# --------------------------------------------------------------------------- render helpers


def scene(samples=48, size=(1600, 1000)):
    GC.scene_setup(size, samples)
    sc = bpy.context.scene
    sc.view_settings.view_transform = 'Standard'
    return sc


def cam_obj(lens=50, ortho=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("cam"); cd.clip_start = 0.01; cd.clip_end = 100; cd.sensor_fit = 'HORIZONTAL'
    cd.sensor_width = 36.0
    c = bpy.data.objects.new("cam", cd); sc.collection.objects.link(c); sc.camera = c
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else: cd.lens = lens
    return c


def look(c, loc, target, up=(0, 1, 0)):
    """loc / target / up in Unity world"""
    lb = TM.to_blender(loc); tb = TM.to_blender(target)
    ub = Vector((-up[0], -up[2], up[1]))
    f = (tb - lb).normalized(); r = f.cross(ub).normalized(); u = r.cross(f)
    M = Matrix((r, u, -f)).transposed()
    c.matrix_world = Matrix.Translation(lb) @ M.to_4x4()
    bpy.context.view_layer.update()


def project(c, pts):
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    return np.array([tuple(world_to_camera_view(sc, c, TM.to_blender(p)))[:2] for p in pts])


def all_points(objs):
    pts = []
    for o in objs.values():
        W = o.matrix_world
        pts += [tuple(spec(W @ v.co)) for v in o.data.vertices]
    return pts


def fit(c, pts, box, tgt, iters=30):
    """contain-fit: move the camera along the line to tgt (perspective) or set the ortho scale so the projected bbox
    of pts fits box = (x0, x1, y0, y1) (normalized image coords, y up) on its tighter axis, then shift so the bbox
    is centred horizontally and sits on the box's bottom line (the floor line of the concept). The spec model is
    taller than the concept, so it usually fits the height and comes out narrower."""
    cd = c.data; sc = bpy.context.scene
    W, H = sc.render.resolution_x, sc.render.resolution_y
    tw, th = box[1] - box[0], (box[3] - box[2]) * H / W
    tb = TM.to_blender(tgt)
    for _ in range(iters):
        P = project(c, pts); r = max(np.ptp(P[:, 0]) / tw, np.ptp(P[:, 1]) * H / W / th)
        if abs(r - 1) < 1e-4: break
        if cd.type == 'ORTHO': cd.ortho_scale *= r
        else: c.location = tb + (c.location - tb) * r
        bpy.context.view_layer.update()
    P = project(c, pts)
    cd.shift_x += (P[:, 0].min() + P[:, 0].max()) / 2 - (box[0] + box[1]) / 2
    cd.shift_y += (P[:, 1].min() - box[2]) * H / W
    bpy.context.view_layer.update()


def shot(fn, folder=OUT_DIR):
    os.makedirs(folder, exist_ok=True)
    sc = bpy.context.scene
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = os.path.join(folder, fn); bpy.ops.render.render(write_still=True); print("RENDER", fn)
    return os.path.join(folder, fn)


def concept_room(bg=67):
    """neutral concept-like light: flat grey camera background, soft key from above front-right, fill"""
    sc = bpy.context.scene
    lin = lambda v: ((v / 255.0 + 0.055) / 1.055) ** 2.4
    g = lin(bg)
    wt = sc.world.node_tree; wb = wt.nodes["Background"]
    wb.inputs[0].default_value = (g, g, g, 1); wb.inputs[1].default_value = 0.35
    cam_bg = wt.nodes.new("ShaderNodeBackground"); cam_bg.inputs[0].default_value = (g, g, g, 1)
    lp = wt.nodes.new("ShaderNodeLightPath"); mx = wt.nodes.new("ShaderNodeMixShader")
    wt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0]); wt.links.new(wb.outputs[0], mx.inputs[1])
    wt.links.new(cam_bg.outputs[0], mx.inputs[2])
    wt.links.new(mx.outputs[0], wt.nodes["World Output"].inputs["Surface"])
    GC.add_light("CKey", L((-0.8, 3.4, 2.6)), L((0.0, 1.0, 0.4)), 75, 2.5)
    GC.add_light("CFill", L((1.6, 1.6, 3.4)), L((0.0, 0.9, 0.4)), 30, 3.0)
    GC.add_light("CTop", L((0.0, 4.0, 0.6)), L((0.0, 1.0, 0.4)), 35, 3.0)
    GC.add_light("CSide", L((-3.5, 1.4, 0.6)), L((0.0, 0.9, 0.4)), 20, 2.0)
    hide_lights()


# concept framing: terminal bbox in each concept image (pixels of the 2576 x 1438 originals, measured by eye on the
# 2000 px previews x 1.288); views: camera (azimuth to the player's right, elevation, lens) or ortho direction
CONCEPT = {
    "34": dict(img="terminal_front.jpg", az=22.0, el=15.0, lens=50.0, box_px=(152, 2435, 70, 1340)),
    "front": dict(img="terminal_ortho_front.jpg", ortho="front", box_px=(157, 2445, 84, 1205)),
    "top": dict(img="terminal_ortho_top.jpg", ortho="top", box_px=(157, 2445, 393, 1088)),
    "side": dict(img="terminal_ortho_side.jpg", ortho="side", box_px=(1003, 1617, 32, 1333)),
}
IMG_W, IMG_H = 2576, 1438


def concept_camera(view, objs):
    v = CONCEPT[view]
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1288, 719
    pts = all_points(objs)
    tgt = L((0.0, 0.95, 0.40))
    if "ortho" in v:
        c = cam_obj(ortho=4.0)
        d = {"front": ((0, 0.95, 6.0), (0, 1, 0)), "top": ((0, 6.0, 0.40), (0, 0, -1)), "side": ((-6.0, 0.95, 0.40), (0, 1, 0))}[v["ortho"]]
        look(c, L(d[0]), tgt if v["ortho"] != "top" else L((0.0, 0.0, 0.40)), d[1])
    else:
        c = cam_obj(lens=v["lens"])
        az, el = math.radians(v["az"]), math.radians(v["el"]); r = 4.5
        loc = (-r * math.cos(el) * math.sin(az), 0.95 + r * math.sin(el), 0.40 + r * math.cos(el) * math.cos(az))
        look(c, L(loc), tgt)
    x0, x1, y0, y1 = v["box_px"]
    box = (x0 / IMG_W, x1 / IMG_W, 1 - y1 / IMG_H, 1 - y0 / IMG_H)
    fit(c, pts, box, tgt if "ortho" not in v else L((0.0, 0.0, 0.40)))
    bpy.context.view_layer.update()
    return c


def side_by_side(render_png, concept_jpg, out_jpg, label_h=0):
    from PIL import Image
    a = Image.open(render_png).convert("RGB"); b = Image.open(concept_jpg).convert("RGB")
    H = 719
    a = a.resize((int(a.width * H / a.height), H)); b = b.resize((int(b.width * H / b.height), H))
    out = Image.new("RGB", (a.width + b.width + 16, H), (30, 30, 30))
    out.paste(a, (0, 0)); out.paste(b, (a.width + 16, 0))
    out.save(out_jpg, quality=90); print("COMPOSITE", os.path.basename(out_jpg))
    return out_jpg


def sheet(files, out_jpg):
    from PIL import Image
    ims = [Image.open(f).convert("RGB") for f in files]
    w = max(i.width for i in ims); H = sum(i.height for i in ims) + 12 * (len(ims) - 1)
    out = Image.new("RGB", (w, H), (30, 30, 30)); y = 0
    for i in ims: out.paste(i, (0, y)); y += i.height + 12
    out = out.resize((w // 2, H // 2)); out.save(out_jpg, quality=88); print("SHEET", os.path.basename(out_jpg))


def concept(args):
    tag = args[0] if args else "h0"
    mode = args[1] if len(args) > 1 else "flat"
    objs = open_file()
    if mode == "baked":
        import terminal_tex as TT
        TT.apply_baked(objs, beacon_on=True)                                 # the concept shows the beacon lit
    scene(samples=64 if mode == "baked" else 32)
    concept_room()
    comps = []
    for view in ("34", "front", "top", "side"):
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA': bpy.data.objects.remove(o)
        concept_camera(view, {k: o for k, o in objs.items()})
        png = shot(f"{tag}_concept_{view}.png")
        comps.append(side_by_side(png, os.path.join(REF, CONCEPT[view]["img"]),
                                  os.path.join(OUT_DIR, f"{tag}_vs_concept_{view}.jpg")))
    sheet(comps, os.path.join(OUT_DIR, f"{tag}_vs_concept.jpg"))


# --------------------------------------------------------------------------- review renders (untextured)


def facility_room():
    """room proxy: back wall, trim, side wall, floor (dark grey)"""
    room = TM.room_object(); bpy.context.scene.collection.objects.link(room)
    m = bpy.data.materials.new("M_RoomProxy"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.05, 0.055, 0.06, 1)
    b.inputs["Roughness"].default_value = 0.8
    room.data.materials.append(m)
    me = bpy.data.meshes.new("Floor")
    me.from_pydata([TM.to_blender(p) for p in ((-4.0, 0, -2.0), (1.0, 0, -2.0), (1.0, 0, 3.0), (-4.0, 0, 3.0))], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new("Floor", me); bpy.context.scene.collection.objects.link(fl); me.materials.append(m)
    return room, fl


VIEWS = {
    "room": dict(loc=(0.6, 1.60, 2.6), look=(-2.2, 1.0, -1.6), lens=30),          # from the room, teleport side
    "34": dict(loc=L((-1.3, 1.75, 2.4)), look=L((0.0, 0.95, 0.40)), lens=35),
    "front": dict(loc=L((0.0, 1.60, 1.55)), look=L((0.0, 1.00, 0.40)), lens=24),   # player position
    "button": dict(loc=L((-0.25, 1.35, 1.05)), look=L((0.0, 0.98, 0.55)), lens=45),
    "beacon": dict(loc=L((0.75, 1.55, 1.25)), look=L((1.05, 1.30, 0.38)), lens=50),
    "pillar": dict(loc=L((1.9, 1.10, 1.6)), look=L((1.10, 0.70, 0.55)), lens=35),
    "lower": dict(loc=L((-0.6, 0.55, 1.7)), look=L((0.0, 0.45, 0.6)), lens=30),
}


def hide_lights():
    """area lights are visible to camera rays in Cycles (a black slab seen from behind): hide them from the camera"""
    for o in bpy.data.objects:
        if o.type == 'LIGHT': o.visible_camera = False


def standard_lights():
    return [GC.add_light("Key", L((0.8, 3.2, 2.2)), L((0.0, 1.0, 0.4)), 95, 1.6, (0.85, 0.92, 1.0)),      # Gate review levels
            GC.add_light("Fill", L((-1.8, 1.6, 2.4)), L((0.0, 0.9, 0.4)), 22, 2.0, (0.7, 0.85, 1.0)),
            GC.add_light("Rim", L((2.4, 2.6, 0.6)), L((1.0, 1.0, 0.4)), 15, 1.0, (1.0, 0.85, 0.7))]


def _hide_after(f):
    def g(*a, **k):
        r = f(*a, **k); hide_lights(); return r
    return g


standard_lights = _hide_after(standard_lights)


def renders(args):
    tag = args[0] if args else "h1"
    objs = open_file()
    scene(samples=32, size=(1280, 800))
    sc = bpy.context.scene
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.006, 0.008, 0.011, 1)
    room, fl = facility_room(); standard_lights()
    for k, v in VIEWS.items():
        if "nocolour" in args: break
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA': bpy.data.objects.remove(o)
        c = cam_obj(v["lens"]); look(c, v["loc"], v["look"]); shot(f"{tag}_{k}.png")
    # wireframe on flat grey (Cycles: the Workbench engine needs EGL, missing in the headless container)
    if "colour" in args: return
    flat = lambda name, rgb, rough=0.6: _flat(name, rgb, rough)
    grey = flat("M_WireBase", (0.30, 0.31, 0.33)); dark = flat("M_Wire", (0.01, 0.01, 0.012), 0.9)
    for k, o in objs.items():
        if k == "Display_01": o.hide_render = True; continue
        for i in range(len(o.data.materials)): o.data.materials[i] = grey
    room.hide_render = True; fl.hide_render = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.10, 0.105, 0.115, 1)
    wires = CC.add_wire({k: o for k, o in objs.items() if k != "Display_01"}, 0.0010)
    for o, w in wires:
        w.data = o.data.copy(); w.data.materials.clear(); w.data.materials.append(dark)
        w.modifiers["Wire"].material_offset = 0
        w.modifiers["Wire"].use_even_offset = False       # even offset spikes at the acute corners of flat fills
    for k in ("34", "button", "beacon"):
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA': bpy.data.objects.remove(o)
        v = VIEWS[k]; c = cam_obj(v["lens"]); look(c, v["loc"], v["look"]); shot(f"{tag}_wire_{k}.png")
    for o in list(bpy.data.objects):
        if o.name.endswith("_wire"): bpy.data.objects.remove(o)
    # texel checker (emission: unlit, so the cells read evenly)
    img = CC.checker_image(TEX)
    m = bpy.data.materials.new("M_Checker"); m.use_nodes = True; nt = m.node_tree
    tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = img
    em = nt.nodes.new("ShaderNodeEmission"); nt.links.new(tn.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    for k, o in objs.items():
        if k == "Display_01": continue
        for i in range(len(o.data.materials)): o.data.materials[i] = m
    for k in ("34", "pillar"):
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA': bpy.data.objects.remove(o)
        v = VIEWS[k]; c = cam_obj(v["lens"]); look(c, v["loc"], v["look"]); shot(f"{tag}_checker_{k}.png")
    uv_layout(tag)


def _flat(name, rgb, rough):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
    return m


def uv_layout(tag):
    p = os.path.join(WORK, "uv_labels.npy")
    if not os.path.exists(p): return
    lab = np.load(p)
    rng = np.random.default_rng(2)
    lut = rng.uniform(0.25, 0.85, (lab.max() + 1, 3)); lut[0] = (0.08, 0.08, 0.09)
    rgb = lut[lab]
    edge = np.zeros(lab.shape, bool)
    edge[:, :-1] |= lab[:, :-1] != lab[:, 1:]; edge[:-1, :] |= lab[:-1, :] != lab[1:, :]
    rgb[edge] = (0.02, 0.02, 0.02)
    from PIL import Image
    Image.fromarray((np.flipud(rgb) * 255).astype(np.uint8)).resize((1024, 1024)).save(
        os.path.join(OUT_DIR, f"{tag}_uv_layout.png")); print("RENDER", f"{tag}_uv_layout.png")


def shading(args):
    tag = args[0] if args else "h1"
    fast = "fast" in args
    objs = open_file()
    scene(samples=16 if fast else 32, size=(1280, 800))
    if fast: bpy.context.scene.render.resolution_percentage = 50
    sc = bpy.context.scene
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.022, 0.025, 1)
    facility_room(); standard_lights()
    m = bpy.data.materials.new("M_ShadingGrey"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.30, 0.30, 0.30, 1)
    b.inputs["Roughness"].default_value = 0.30
    for k, o in objs.items():
        if k == "Display_01": o.hide_render = True; continue
        for i in range(len(o.data.materials)): o.data.materials[i] = m
    for k in ("34", "button", "pillar", "lower"):
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA': bpy.data.objects.remove(o)
        v = VIEWS[k]; c = cam_obj(v["lens"]); look(c, v["loc"], v["look"]); shot(f"{tag}_shading_{k}.png")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"topo": topo, "clearance": clearance, "concept": concept, "renders": renders, "shading": shading}[argv[0]](argv[1:])
