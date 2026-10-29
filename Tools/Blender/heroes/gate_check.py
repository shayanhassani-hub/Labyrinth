"""
Gate (Hero 03) low-poly: validation and review renders (HERO_SPEC §7, ASSET_RULES hero standard, workflow v3).
  blender -b -P Tools/Blender/heroes/gate_check.py -- <stage> [...]
stages:
  topo        tris and topology per part, bow-tie / concave quads, winding against the custom normals, planarity
              report, UV islands, texel density, padding (writes Temp/claude/gate/topo.json)
  clearance   leaf slide sweep 0 ... LEAF_TRAVEL: leaf against the rail, the room (wall, trims, doorway), hangers /
              rollers on the rail; button press against the panel
  renders     Renders/gate_g1_*.png (room side, corridor side, 3/4, open, hanger detail, button, wireframe, UV layout,
              texel checker)
Everything opens the saved review file (gate.SAVE) and never saves it.
"""
import bpy
import bmesh
import json
import math
import os
import sys
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gate as G                                         # noqa: E402
import cradle_v2_check as CC                             # noqa: E402  quad_faults, winding_faults, wire helper

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCR = os.path.join(PROJ, "Temp", "claude", "gate")
RENDERS = os.path.join(PROJ, "Renders")
PARTS = ["Leaf_01", "Rail_01", "ButtonPanel_01", "Button_01"]
TEX = 2048
TWIST_MAX = 0.002


def open_file():
    bpy.ops.wm.open_mainfile(filepath=G.SAVE)
    return {n: bpy.data.objects[f"{G.HERO}_{n}"] for n in PARTS}


def spec(v):
    return Vector((-v.x, v.z, -v.y))


def set_leaf(objs, dx):
    objs["Leaf_01"].location = G.to_blender((G.LEAF_X1 + dx, G.LEAF_Y0, (G.LEAF_Z0 + G.LEAF_Z1) / 2))
    bpy.context.view_layer.update()


# --------------------------------------------------------------------------- topology, UVs


def uv_islands(me):
    """face islands by shared UV-connected corners"""
    uv = me.uv_layers.active.data
    parent = list(range(len(me.polygons)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    key = {}
    for p in me.polygons:
        for li in p.loop_indices:
            k = (me.loops[li].vertex_index, round(uv[li].uv[0], 6), round(uv[li].uv[1], 6))
            if k in key: parent[find(p.index)] = find(key[k])
            else: key[k] = p.index
    return [find(p.index) for p in me.polygons]


def raster_labels(objs):
    lab = np.zeros((TEX, TEX), np.int32); owner = {}; gid = 0
    for name, o in objs.items():
        me = o.data; me.calc_loop_triangles(); uv = me.uv_layers.active.data
        isl = uv_islands(me); ids = {}
        for r in sorted(set(isl)):
            gid += 1; ids[r] = gid; owner[gid] = name
        for t in me.loop_triangles:
            P = np.array([uv[l].uv[:] for l in t.loops]) * TEX
            x0, y0 = np.floor(P.min(0)).astype(int); x1, y1 = np.ceil(P.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, TEX - 1), min(y1, TEX - 1)
            if x1 < x0 or y1 < y0: continue
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]; px = xs + 0.5; py = ys + 0.5
            (ax, ay), (bx, by), (cx, cy) = P
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12: continue
            w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
            w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (1 - w0 - w1 >= -1e-6)
            lab[ys[m], xs[m]] = ids[isl[t.polygon_index]]
    return lab, owner


def padding(lab, gap_px=8, border_px=4):
    """closest pixel distance (Chebyshev) between two islands, if below gap_px; border distance"""
    close = None
    for dy in range(-gap_px + 1, gap_px):
        for dx in range(-gap_px + 1, gap_px):
            if dx == 0 and dy == 0: continue
            a = lab[max(0, dy):TEX + min(0, dy), max(0, dx):TEX + min(0, dx)]
            b = lab[max(0, -dy):TEX + min(0, -dy), max(0, -dx):TEX + min(0, -dx)]
            if np.any((a > 0) & (b > 0) & (a != b)):
                d = max(abs(dx), abs(dy)) - 1
                close = d if close is None else min(close, d)
    ys, xs = np.nonzero(lab)
    border = int(min(xs.min(), ys.min(), TEX - 1 - xs.max(), TEX - 1 - ys.max()))
    return close, border


FLAT_TOL = 0.5                 # G2: a flat face's corner normals may deviate this much from its face normal


def flat_normals(me):
    """G2 shading check: every FLAT face (face attribute kind) must shade flat, i.e. all its corner normals equal its
    face normal; returns (faces over FLAT_TOL, worst deviation in degrees)"""
    kind = me.attributes["kind"].data
    N = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get("vector", N); N = N.reshape(-1, 3)
    bent, worst = 0, 0.0
    for p in me.polygons:
        if kind[p.index].value != G.FLAT: continue
        fn = np.array(p.normal)
        d = max(math.degrees(math.acos(max(-1.0, min(1.0, float(N[li] @ fn))))) for li in p.loop_indices)
        worst = max(worst, d); bent += d > FLAT_TOL
    return bent, worst


def topo(args):
    objs = open_file(); out = {}; total = 0
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
        out[name] = dict(tris=tris, quads=q, tri_faces=tr, ngons=ng, open_border=border, nonmanifold=nonman, loose=loose,
                         zero_area=zero, duplicates=dup, winding_inconsistent=inconsistent, bowtie=len(bow),
                         concave=len(conc), twisted_quads=len(twist), **wcount)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {tris} tris ({q} quads, {tr} tris, {ng} n-gons), open border {border}, "
              f"non-manifold {nonman}, loose {loose}, dup {dup}, zero-area {zero}, winding {inconsistent}")
        print(f"{'PASS' if ok2 else 'FAIL'} {name} folds: bow-tie {len(bow)}, concave {len(conc)}, against custom normals "
              f"{wcount['vs_custom']}, folded pairs {wcount['folded_pairs']}, same-direction edges {wcount['same_direction_edges']}")
        print(f"INFO planarity {name}: {len(twist)} quads with diagonals > {TWIST_MAX * 1e3:.0f} mm apart")
        bent, worst = flat_normals(me)
        out[name].update(flat_faces_bent=bent, flat_bend_max_deg=round(worst, 2))
        print(f"{'PASS' if bent == 0 else 'FAIL'} {name} shading: {bent} flat faces with a corner normal > "
              f"{FLAT_TOL} deg off the face normal (worst {worst:.2f} deg)")
    print(f"INFO total {total} tris")
    # UVs: density per part, islands, padding, overlaps
    lab, owner = raster_labels(objs)
    for name, o in objs.items():
        me = o.data; uv = me.uv_layers.active.data
        a3 = a2 = 0.0; a2_full = 0.0
        for p in me.polygons:
            U = np.array([uv[l].uv[:] for l in p.loop_indices]); x, y = U[:, 0], U[:, 1]
            au = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            a3 += p.area; a2_full += au
            if abs(p.normal.z) < 0.9 or "Leaf" not in name: a2 += au; a3_ = p.area
        isl = len(set(uv_islands(me)))
        dens = TEX * math.sqrt(a2_full / max(sum(p.area for p in me.polygons), 1e-12))
        out[name].update(islands=isl, px_per_m_mean=round(dens, 1), area_m2=round(a3, 3))
        print(f"INFO UV {name}: {isl} islands, {a3:.3f} m2, mean {dens:.0f} px/m (incl. reduced faces)")
    gap, border = padding(lab)
    fill = (lab > 0).mean()
    per = {}
    for name, o in objs.items():                                          # main density = full-density islands
        me = o.data; uv = me.uv_layers.active.data; isl = uv_islands(me); acc = {}
        for p in me.polygons:
            U = np.array([uv[l].uv[:] for l in p.loop_indices]); x, y = U[:, 0], U[:, 1]
            au = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            a = acc.setdefault(isl[p.index], [0.0, 0.0]); a[0] += p.area; a[1] += au
        d = [TEX * math.sqrt(v[1] / v[0]) for v in acc.values() if v[0] > 1e-6]
        per[name] = (round(min(d)), round(float(np.median(d))), round(max(d)))
        print(f"INFO UV {name}: island density min / median / max {per[name]} px/m")
    print(f"{'PASS' if gap is None else 'FAIL'} island padding >= 8 px" + ("" if gap is None else f" (closest {gap} px)"))
    print(f"{'PASS' if border >= 4 else 'FAIL'} sheet border >= 4 px ({border} px)")
    print(f"INFO packing {fill * 100:.1f} % of the 2048 sheet")
    out["_uv"] = dict(padding_close=gap, border_px=border, fill=round(float(fill), 3), density=per)
    os.makedirs(SCR, exist_ok=True)
    np.save(os.path.join(SCR, "uv_labels.npy"), lab)
    json.dump(out, open(os.path.join(SCR, "topo.json"), "w"), indent=1)


# --------------------------------------------------------------------------- clearances


def world_tris(objs_list):
    P, F = [], []
    for o in objs_list:
        k = len(P); W = o.matrix_world; o.data.calc_loop_triangles()
        P += [W @ v.co for v in o.data.vertices]; F += [tuple(k + i for i in t.vertices) for t in o.data.loop_triangles]
    return P, F


def min_gap(a_objs, b_objs, step=0.004):
    """smallest distance from points sampled on a (verts + face samples) to the surface of b, and back"""
    def samples(objs_):
        pts = []
        for o in objs_:
            W = o.matrix_world
            pts += [W @ v.co for v in o.data.vertices]
            pts += [W @ p.center for p in o.data.polygons]
        return pts
    Pb, Fb = world_tris(b_objs); tb = BVHTree.FromPolygons(Pb, Fb)
    Pa, Fa = world_tris(a_objs); ta = BVHTree.FromPolygons(Pa, Fa)
    best = (1e9, None)
    for p in samples(a_objs):
        h = tb.find_nearest(p)
        if h[0] is not None and h[3] < best[0]: best = (h[3], p)
    for p in samples(b_objs):
        h = ta.find_nearest(p)
        if h[0] is not None and h[3] < best[0]: best = (h[3], p)
    hit = bool(ta.overlap(tb))
    return best[0], (spec(best[1]) if best[1] is not None else None), hit


def clearance(args):
    objs = open_file()
    room = G.room_object(); bpy.context.scene.collection.objects.link(room)
    leaf, rail = objs["Leaf_01"], objs["Rail_01"]
    # the rollers ride on the rail top (1 mm by construction, reported below): rail test without the steel parts
    bm = bmesh.new(); bm.from_mesh(leaf.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index == G.STEEL], context='FACES')
    me = bpy.data.meshes.new("LeafNoSteel"); bm.to_mesh(me); bm.free()
    body = bpy.data.objects.new("LeafNoSteel", me); bpy.context.scene.collection.objects.link(body)
    body.parent = leaf
    worst = {"rail": (1e9, 0, None), "room": (1e9, 0, None)}; hits = []
    roller_x = []
    steps = [round(-G.LEAF_TRAVEL * i / 34, 4) for i in range(35)]
    for dx in steps:
        set_leaf(objs, dx)
        for k, a, other in (("rail", body, [rail]), ("room", leaf, [room])):
            d, at, hit = min_gap([a], other)
            if hit: hits.append((k, dx))
            if d < worst[k][0]: worst[k] = (d, dx, at)
        xs = [G.LEAF_X1 + dx + (hc - G.OUTLINE[2][0]) + s * (G.AXLE_DU + G.ROLLER_A / math.cos(math.pi / 12) * math.cos(math.radians(15)))
              for hc in G.HANGERS for s in (-1, 1)]
        roller_x.append((dx, min(xs), max(xs)))
    set_leaf(objs, 0.0)
    for k, (d, dx, at) in worst.items():
        print(f"{'PASS' if d > 0.004 and not any(h[0] == k for h in hits) else 'FAIL'} leaf vs {k} over the slide: "
              f"min gap {d * 1e3:.1f} mm at slide {dx:+.3f} m near spec {tuple(round(c, 3) for c in at)}")
    # specific gaps (construction values, closed pose)
    rr = G.ROLLER_A
    rows = [
        ("leaf top -> rail bottom", G.RAIL_Y0 - (G.LEAF_Y0 + G.LEAF_H)),
        ("leaf top -> rail bracket plates", G.RAIL_PLATE["y0"] - (G.LEAF_Y0 + G.LEAF_H)),
        ("leaf corridor face -> wall face", G.WALL_Z - G.LEAF_Z1),
        ("leaf corridor face -> trim face (z 7.95)", 7.95 - G.LEAF_Z1),
        ("leaf bottom -> floor", G.LEAF_Y0),
        ("strap back -> rail bracket plate front", G.RAIL_PLATE["z0"] - (G.LEAF_Z0 - G.PLATE["t"])),
        ("roller bottom -> rail top", G.LEAF_Y0 + G.AXLE_V - rr - G.RAIL_Y1),
        ("axle bottom -> bracket plate top", G.LEAF_Y0 + G.AXLE_V - G.AXLE_R - G.RAIL_PLATE["y1"]),
        ("leaf overlap past the doorway (smaller side)", min(-1.8 - G.LEAF_X0, G.LEAF_X1 + 0.2)),
        ("leaf overlap above the doorway", G.LEAF_Y0 + G.LEAF_H - 2.4),
    ]
    for n, v in rows:
        print(f"INFO {n}: {v * 1e3:.1f} mm")
    lo = G.RAIL_X0 + G.STOP["w"]; hi = G.RAIL_X1 - G.STOP["w"]
    x0 = min(r[1] for r in roller_x); x1 = max(r[2] for r in roller_x)
    ok = all(lo <= a and b <= hi for _, a, b in roller_x)
    print(f"{'PASS' if ok else 'FAIL'} rollers stay on the rail between the end stops over the whole slide: roller x "
          f"{x0:.3f} ... {x1:.3f}, rail free {lo:.3f} ... {hi:.3f} (margins {1e3 * (x0 - lo):.0f} / {1e3 * (hi - x1):.0f} mm)")
    # button press
    btn, pan = objs["Button_01"], objs["ButtonPanel_01"]
    base = btn.location.copy()
    for t, label in ((0.0, "rest"), (G.BUTTON_TRAVEL, "pressed")):
        btn.location = base + Vector((t, 0, 0))                           # spec -X = Blender +X
        bpy.context.view_layer.update()
        d, at, hit = min_gap([btn], [pan])
        print(f"{'PASS' if not hit and d > 0.001 else 'FAIL'} button {label}: min gap to the panel {d * 1e3:.1f} mm")
    btn.location = base
    front = G.button_front() - G.BUTTON_TRAVEL - (G.PANEL_C[0] + G.PANEL_SZ[0] + G.BEZEL_T)
    print(f"INFO button pressed: front {front * 1e3:.1f} mm proud of the bezel; back "
          f"{(G.button_front() - G.BUTTON_PROUD - G.BUTTON_BACK - G.BUTTON_TRAVEL - (G.PANEL_C[0] + G.PANEL_SZ[0] + G.BEZEL_T - G.HOLE_DEPTH)) * 1e3:.1f} mm above the hole floor")


# --------------------------------------------------------------------------- renders


def scene_setup(size=(1600, 1000), samples=48):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.samples = samples; sc.cycles.use_denoising = True
    sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = size; sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'None'
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.033, 0.038, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0


def add_light(name, loc_spec, look_spec, power, size=1.5, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.size = size; ld.color = color
    o = bpy.data.objects.new(name, ld); bpy.context.scene.collection.objects.link(o)
    o.location = G.to_blender(loc_spec); t = G.to_blender(look_spec)
    o.rotation_euler = (t - o.location).to_track_quat('-Z', 'Y').to_euler()
    return o


def add_room():
    room = G.room_object(); bpy.context.scene.collection.objects.link(room)
    m = bpy.data.materials.new("M_RoomProxy"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.09, 0.095, 0.10, 1)
    b.inputs["Roughness"].default_value = 0.8
    room.data.materials.append(m)
    me = bpy.data.meshes.new("Floor")                                     # floor, spec x -5 .. 2, z 3 .. 14
    me.from_pydata([G.to_blender(p) for p in ((-5, 0, 3), (2, 0, 3), (2, 0, 14.2), (-5, 0, 14.2))], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new("Floor", me); bpy.context.scene.collection.objects.link(fl); me.materials.append(m)
    return room


def camera(loc, look, lens=40, ortho=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("cam"); cd.clip_start = 0.01; cd.clip_end = 100
    c = bpy.data.objects.new("cam", cd); sc.collection.objects.link(c)
    c.location = G.to_blender(loc); t = G.to_blender(look)
    c.rotation_euler = (t - c.location).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else: cd.lens = lens
    sc.camera = c


def shot(fn):
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(RENDERS, fn); bpy.ops.render.render(write_still=True); print("RENDER", fn)


def uv_layout():
    lab = np.load(os.path.join(SCR, "uv_labels.npy"))
    rng = np.random.default_rng(2)
    lut = rng.uniform(0.25, 0.85, (lab.max() + 1, 3)); lut[0] = (0.08, 0.08, 0.09)
    rgb = lut[lab]
    edge = np.zeros(lab.shape, bool)
    edge[:, :-1] |= lab[:, :-1] != lab[:, 1:]; edge[:-1, :] |= lab[:-1, :] != lab[1:, :]
    rgb[edge] = (0.02, 0.02, 0.02)
    img = bpy.data.images.new("uvlayout", TEX, TEX, alpha=False)
    img.pixels.foreach_set(np.concatenate([rgb, np.ones((TEX, TEX, 1))], 2).astype(np.float32).ravel())
    img.filepath_raw = os.path.join(RENDERS, "gate_g1_uv_layout.png"); img.file_format = 'PNG'; img.save()
    print("RENDER gate_g1_uv_layout.png")


def renders(args):
    objs = open_file()
    only = set(args)
    scene_setup()
    add_room()
    add_light("Key", (-0.6, 3.6, 4.4), (-1.6, 1.2, 7.9), 160, 2.0)
    add_light("Fill", (1.6, 1.4, 5.0), (-1.4, 1.2, 7.9), 60, 2.5, (0.85, 0.92, 1.0))
    add_light("CorrKey", (-1.0, 2.8, 11.5), (-1.0, 1.2, 8.0), 90, 1.5)
    views = {
        "room": dict(loc=(-1.8, 1.42, 2.0), look=(-1.8, 1.42, 7.9), ortho=4.3),
        "corridor": dict(loc=(-1.0, 1.36, 12.6), look=(-1.05, 1.25, 8.0), lens=28),
        "34": dict(loc=(0.9, 1.8, 5.1), look=(-1.3, 1.35, 7.9), lens=32),
        "hanger": dict(loc=(-0.15, 2.05, 6.85), look=(-0.5, 2.55, 7.93), lens=40),
        "button": dict(loc=(-1.3, 1.40, 8.95), look=(-1.94, 1.21, 8.70), lens=45),
    }
    for k, v in views.items():
        if only and k not in only: continue
        camera(v["loc"], v["look"], v.get("lens", 40), v.get("ortho")); shot(f"gate_g1_{k}.png")
    if not only or "open" in only:
        set_leaf(objs, -G.LEAF_TRAVEL)
        camera((0.3, 1.7, 4.6), (-1.9, 1.35, 7.9), 30); shot("gate_g1_open.png")
        set_leaf(objs, 0.0)
    if not only or "wire" in only:                                        # wire on flat grey, workbench
        sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.render_aa = '16'
        sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'OBJECT'; sh.show_cavity = False
        sh.background_type = 'VIEWPORT'; sh.background_color = (0.18, 0.19, 0.21)
        sc.view_settings.view_transform = 'Standard'
        for o in objs.values(): o.color = (0.55, 0.57, 0.60, 1)
        bpy.data.objects["GateRoomProxy"].hide_render = True; bpy.data.objects["Floor"].hide_render = True
        CC.add_wire({k: o for k, o in objs.items()}, 0.0012)
        camera((0.6, 1.7, 4.0), (-1.2, 1.35, 7.9), 26); shot("gate_g1_wire.png")
        camera((-1.3, 1.40, 8.95), (-1.94, 1.21, 8.70), 45); shot("gate_g1_wire_button.png")
        for o in list(bpy.data.objects):
            if o.name.endswith("_wire"): bpy.data.objects.remove(o)
        bpy.data.objects["GateRoomProxy"].hide_render = False; bpy.data.objects["Floor"].hide_render = False
    if not only or "checker" in only:
        sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
        sh = sc.display.shading; sh.color_type = 'TEXTURE'; sh.light = 'STUDIO'
        img = CC.checker_image(TEX)
        m = bpy.data.materials.new("M_Checker"); m.use_nodes = True
        tn = m.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
        m.node_tree.links.new(tn.outputs[0], m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
        for o in objs.values():
            o.data.materials.clear(); o.data.materials.append(m)
        bpy.data.objects["GateRoomProxy"].hide_render = True; bpy.data.objects["Floor"].hide_render = True
        camera((0.9, 1.8, 5.1), (-1.3, 1.35, 7.9), 32); shot("gate_g1_checker.png")
        camera((-1.0, 1.36, 11.0), (-1.05, 1.25, 8.0), 30); shot("gate_g1_checker_corridor.png")
    if not only or "uv" in only:
        uv_layout()


SHADING_VIEWS = {
    "room": dict(loc=(-1.8, 1.42, 2.0), look=(-1.8, 1.42, 7.9), ortho=4.3),
    "34": dict(loc=(0.9, 1.8, 5.1), look=(-1.3, 1.35, 7.9), lens=32),
    "corridor": dict(loc=(-1.0, 1.36, 12.6), look=(-1.05, 1.25, 8.0), lens=28),
    "button": dict(loc=(-1.3, 1.40, 8.95), look=(-1.94, 1.21, 8.70), lens=45),
}


def shading(args):
    """G2: flat grey render of the untextured low (one glossy grey for every face): a flat face must show no
    gradient; any smear means bent normals. Renders/gate_<step>_shading_<view>.png (step = first arg, default g2)."""
    step = args[0] if args else "g2"
    objs = open_file()
    scene_setup(samples=64)
    add_room()
    add_light("Key", (-0.6, 3.6, 4.4), (-1.6, 1.2, 7.9), 160, 2.0)
    add_light("Fill", (1.6, 1.4, 5.0), (-1.4, 1.2, 7.9), 60, 2.5)
    add_light("CorrKey", (-1.0, 2.8, 11.5), (-1.0, 1.2, 8.0), 90, 1.5)
    m = bpy.data.materials.new("M_ShadingGrey"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.30, 0.30, 0.30, 1)
    b.inputs["Roughness"].default_value = 0.35
    for o in objs.values():
        for i in range(len(o.data.materials)): o.data.materials[i] = m
    for k, v in SHADING_VIEWS.items():
        camera(v["loc"], v["look"], v.get("lens", 40), v.get("ortho")); shot(f"gate_{step}_shading_{k}.png")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"topo": topo, "clearance": clearance, "renders": renders, "shading": shading}[argv[0]](argv[1:])
