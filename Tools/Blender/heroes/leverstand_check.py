"""
LeverStand (Hero 02b): validation and review renders (HERO_SPEC §6, ASSET_RULES hero standard, workflow v3).
  blender -b -P Tools/Blender/heroes/leverstand_check.py -- <stage> [...]
stages:
  concept <tag> [blockout]  renders from the two matched concept cameras (3/4 perspective, side orthographic) next to
                            the concept: Documentation/Media/leverstand/leverstand_<tag>_vs_concept.jpg (2 x 2: renders
                            left, concept right). Lever in the concept's pose (pulled, leaning to the front).
  topo                      tris and topology per part, folds, winding, planarity, shading (flat faces), UV islands,
                            texel density, padding (Temp/claude/leverstand/topo.json)
  clearance                 lever sweep rest ... pulled against the body; labyrinth panel tilt cone (12 deg) against
                            the stand (>= 0.15 from the panel's +X edge); hidden faces over the lever poses; player reach
  renders [tag]             room position next to the labyrinth panel, 3/4, close-ups, wire, UV layout, texel checker
  shading [tag]             flat grey renders of the untextured low (no gradients on flat faces)
Opens the saved review file and never saves it.

Concept cameras (fitted to the concept images, Temp fit: 6 landmark points on the pedestal's corner edges, 6 px rms):
  3/4:   camera at stand-local (-2.555, 1.608, 3.442), yaw 143.0 deg, pitch -13.0 deg, 62.2 mm (36 mm sensor width)
  side:  orthographic, looking +X at the -X side face (front on the image's left), centre y 0.634, ortho scale 2.40
         (the image width; from the concept's pedestal height 1020 px of 2576 = 0.95 m)
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
import leverstand as L                                   # noqa: E402
import cradle_v2 as CV                                   # noqa: E402
import cradle_v2_check as CC                             # noqa: E402  quad_faults, winding, wire, checker

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCR = os.path.join(PROJ, "Temp", "claude", "leverstand")
MEDIA = os.path.join(PROJ, "Documentation", "Media", "leverstand")
REF = os.path.join(PROJ, "Documentation", "References", "LeverStand")
PARTS = ["Body_01", "Lever_01", "Lamp_01"]
TWIST_MAX = 0.002
CONCEPT_BG = 67

CAM34 = dict(loc=(-2.555, 1.608, 3.442), yaw=143.04, pitch=-13.01, lens=62.2)
CAMSIDE = dict(loc=(-3.0, 0.634, 0.0088), look=(0.0, 0.634, 0.0088), ortho=2.40)


def lin(v):
    c = v / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def open_file(path=None):
    bpy.ops.wm.open_mainfile(filepath=path or L.SAVE)
    return {n: bpy.data.objects[f"{L.HERO}_{n}"] for n in PARTS if f"{L.HERO}_{n}" in bpy.data.objects}


def spec(v):
    return Vector((-v.x, v.z, -v.y))


# --------------------------------------------------------------------------- render helpers


def scene_setup(size=(1288, 719), samples=64, engine='CYCLES'):
    sc = bpy.context.scene
    sc.render.engine = engine
    if engine == 'CYCLES':
        sc.cycles.samples = samples; sc.cycles.use_denoising = True; sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = size; sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.033, 0.038, 1)
    return sc


def concept_world(strength=0.55):
    """camera rays see the concept's flat mid grey; the world lights the object with the same grey (ambient)"""
    sc = bpy.context.scene; bg = lin(CONCEPT_BG)
    wt = sc.world.node_tree; wb = wt.nodes["Background"]
    wb.inputs[0].default_value = (bg, bg, bg, 1); wb.inputs[1].default_value = strength
    cam_bg = wt.nodes.new("ShaderNodeBackground"); cam_bg.inputs[0].default_value = (bg, bg, bg, 1)
    lp = wt.nodes.new("ShaderNodeLightPath"); mx = wt.nodes.new("ShaderNodeMixShader")
    wt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0]); wt.links.new(wb.outputs[0], mx.inputs[1])
    wt.links.new(cam_bg.outputs[0], mx.inputs[2])
    wt.links.new(mx.outputs[0], wt.nodes["World Output"].inputs["Surface"])


def add_light(name, loc, look, power, size=1.0, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.size = size; ld.color = color
    o = bpy.data.objects.new(name, ld); bpy.context.scene.collection.objects.link(o)
    o.location = L.to_blender(loc); t = L.to_blender(look)
    o.rotation_euler = (t - o.location).to_track_quat('-Z', 'Y').to_euler()
    return o


def concept_lights():
    """soft neutral key from above the front-left (the concept's top-lit look), a weak fill from the camera side"""
    return [add_light("CKey", (0.9, 2.6, 1.6), (0.0, 0.7, 0.0), 110, 2.5),
            add_light("CFill", (-2.2, 1.2, 2.6), (0.0, 0.6, 0.0), 30, 3.0),
            add_light("CRim", (-1.0, 2.0, -2.0), (0.0, 0.8, 0.0), 25, 2.0)]


def camera(loc, look=None, lens=40, ortho=None, yaw=None, pitch=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("cam"); cd.clip_start = 0.01; cd.clip_end = 100; cd.sensor_fit = 'HORIZONTAL'
    cd.sensor_width = 36.0
    c = bpy.data.objects.new("cam", cd); sc.collection.objects.link(c)
    c.location = L.to_blender(loc)
    if look is None:                                           # Unity yaw / pitch (forward = (sin y cos p, sin p, cos y cos p))
        y, p = math.radians(yaw), math.radians(pitch)
        look = (loc[0] + math.sin(y) * math.cos(p), loc[1] + math.sin(p), loc[2] + math.cos(y) * math.cos(p))
    t = L.to_blender(look)
    c.rotation_euler = (t - c.location).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else: cd.lens = lens
    sc.camera = c
    return c


def shot(path):
    sc = bpy.context.scene
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("RENDER", os.path.relpath(path, PROJ))
    return path


def pixels_any(img):
    w, h = img.size; a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a); return a.reshape(h, w, 4)


def save_jpg(arr, path, quality=90):
    """arr (h, w, 3|4) float 0..1, display-referred (already sRGB): written as JPG through a Non-Color image"""
    h, w = arr.shape[:2]
    a = np.ones((h, w, 4), np.float32); a[..., :3] = arr[..., :3]
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=False)
    img.colorspace_settings.name = 'Non-Color'
    img.pixels.foreach_set(np.clip(a, 0, 1).ravel())
    sc = bpy.context.scene
    s = sc.render.image_settings; s.file_format = 'JPEG'; s.quality = quality; s.color_mode = 'RGB'
    keep = sc.view_settings.view_transform; sc.view_settings.view_transform = 'Standard'
    img.save_render(path, scene=sc)
    sc.view_settings.view_transform = keep; s.file_format = 'PNG'
    print("SAVED", os.path.relpath(path, PROJ))


def load_srgb(path, height):
    img = bpy.data.images.load(path); img.colorspace_settings.name = 'Non-Color'
    img.scale(int(round(img.size[0] * height / img.size[1])), height)
    return pixels_any(img)[..., :3]


def grid(rows, gap=16, bg=0.12):
    """rows: list of lists of (h, w, 3) arrays of equal height per row -> one array"""
    out = []
    width = None
    for r in rows:
        parts = []
        for k, a in enumerate(r):
            if k: parts.append(np.full((a.shape[0], gap, 3), bg, np.float32))
            parts.append(a)
        row = np.concatenate(parts, 1); out.append(row); width = max(width or 0, row.shape[1])
    res = []
    for k, row in enumerate(out):
        if row.shape[1] < width:
            row = np.concatenate([row, np.full((row.shape[0], width - row.shape[1], 3), bg, np.float32)], 1)
        if k: res.append(np.full((gap, width, 3), bg, np.float32))
        res.append(row)
    return np.concatenate(res, 0)


def flip(a):
    return a[::-1]                                           # Blender pixels are bottom-up; the grid is built bottom-up


# --------------------------------------------------------------------------- concept comparison


def concept(args):
    tag = args[0] if args else "h0"
    blockout = "blockout" in args
    tex = "textured" in args
    objs = open_file(L.SAVE_BLOCKOUT if blockout else None)
    if tex:
        import leverstand_tex as T
        T.apply_baked(objs)
    L.set_lever(objs["Lever_01"], L.PULLED_DEG)               # the concept shows the lever leaning to the front
    sc = scene_setup(samples=96)
    concept_world(); concept_lights()
    os.makedirs(SCR, exist_ok=True); os.makedirs(MEDIA, exist_ok=True)
    camera(CAM34["loc"], lens=CAM34["lens"], yaw=CAM34["yaw"], pitch=CAM34["pitch"])
    p34 = shot(os.path.join(SCR, f"{tag}_concept34.png"))
    camera(CAMSIDE["loc"], CAMSIDE["look"], ortho=CAMSIDE["ortho"])
    pside = shot(os.path.join(SCR, f"{tag}_conceptside.png"))
    H = 719
    r34 = load_srgb(p34, H); rside = load_srgb(pside, H)
    c34 = load_srgb(os.path.join(REF, "leverstand_front.jpg"), H); cside = load_srgb(os.path.join(REF, "leverstand_ortho_side.jpg"), H)
    # rows bottom-up (Blender pixel order): side row first
    out = grid([[rside, cside], [r34, c34]])
    save_jpg(out, os.path.join(MEDIA, f"leverstand_{tag}_vs_concept.jpg"))
    # zoomed top (housing, lever, lamp) from both cameras: crop the upper part of each image
    def crop(a, y0, y1, x0, x1):                             # fractions, top-down
        h, w = a.shape[:2]
        return a[int(h * (1 - y1)):int(h * (1 - y0)), int(w * x0):int(w * x1)]
    zr34 = crop(r34, 0.0, 0.42, 0.33, 0.72); zc34 = crop(c34, 0.0, 0.42, 0.33, 0.72)
    zrs = crop(rside, 0.0, 0.42, 0.28, 0.67); zcs = crop(cside, 0.0, 0.42, 0.28, 0.67)
    out = grid([[zrs, zcs], [zr34, zc34]])
    save_jpg(out, os.path.join(MEDIA, f"leverstand_{tag}_vs_concept_top.jpg"))


# --------------------------------------------------------------------------- topology, UVs


def uv_islands(me):
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


def raster_labels(objs, tex):
    lab = np.zeros((tex, tex), np.int32); owner = {}; gid = 0; overlap = 0
    for name, o in objs.items():
        me = o.data; me.calc_loop_triangles(); uv = me.uv_layers.active.data
        isl = uv_islands(me); ids = {}
        for r in sorted(set(isl)):
            gid += 1; ids[r] = gid; owner[gid] = name
        for t in me.loop_triangles:
            P = np.array([uv[l].uv[:] for l in t.loops]) * tex
            x0, y0 = np.floor(P.min(0)).astype(int); x1, y1 = np.ceil(P.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, tex - 1), min(y1, tex - 1)
            if x1 < x0 or y1 < y0: continue
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]; px = xs + 0.5; py = ys + 0.5
            (ax, ay), (bx, by), (cx, cy) = P
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12: continue
            w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
            w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
            m = (w0 >= 1e-4) & (w1 >= 1e-4) & (1 - w0 - w1 >= 1e-4)
            cur = lab[ys[m], xs[m]]
            overlap += int(((cur > 0) & (cur != ids[isl[t.polygon_index]])).sum())
            lab[ys[m], xs[m]] = ids[isl[t.polygon_index]]
    return lab, owner, overlap


def padding(lab, gap_px, border_px):
    tex = lab.shape[0]; close = None
    for dy in range(-gap_px + 1, gap_px):
        for dx in range(-gap_px + 1, gap_px):
            if dx == 0 and dy == 0: continue
            a = lab[max(0, dy):tex + min(0, dy), max(0, dx):tex + min(0, dx)]
            b = lab[max(0, -dy):tex + min(0, -dy), max(0, -dx):tex + min(0, -dx)]
            if np.any((a > 0) & (b > 0) & (a != b)):
                d = max(abs(dx), abs(dy)) - 1
                close = d if close is None else min(close, d)
    ys, xs = np.nonzero(lab)
    border = int(min(xs.min(), ys.min(), tex - 1 - xs.max(), tex - 1 - ys.max()))
    return close, border


FLAT_TOL = 0.5


def flat_normals(me):
    kind = me.attributes["kind"].data
    N = np.empty(len(me.loops) * 3); me.corner_normals.foreach_get("vector", N); N = N.reshape(-1, 3)
    bent, worst = 0, 0.0
    for p in me.polygons:
        if kind[p.index].value != L.FLAT: continue
        fn = np.array(p.normal)
        d = max(math.degrees(math.acos(max(-1.0, min(1.0, float(N[li] @ fn))))) for li in p.loop_indices)
        worst = max(worst, d); bent += d > FLAT_TOL
    return bent, worst


def topo(args):
    objs = open_file(); out = {}; total = 0; ok_all = True
    tex = L.UV_TEX
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
        bent, worst = flat_normals(me)
        ok_all &= ok and ok2 and bent == 0
        out[name] = dict(tris=tris, quads=q, tri_faces=tr, ngons=ng, open_border=border, nonmanifold=nonman, loose=loose,
                         zero_area=zero, duplicates=dup, winding_inconsistent=inconsistent, bowtie=len(bow),
                         concave=len(conc), twisted_quads=len(twist), flat_faces_bent=bent,
                         flat_bend_max_deg=round(worst, 2), **wcount)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {tris} tris ({q} quads, {tr} tris, {ng} n-gons), open border {border}, "
              f"non-manifold {nonman}, loose {loose}, dup {dup}, zero-area {zero}, winding {inconsistent}")
        print(f"{'PASS' if ok2 else 'FAIL'} {name} folds: bow-tie {len(bow)}, concave {len(conc)}, against custom normals "
              f"{wcount['vs_custom']}, folded pairs {wcount['folded_pairs']}, same-direction edges {wcount['same_direction_edges']}")
        print(f"INFO planarity {name}: {len(twist)} quads with diagonals > {TWIST_MAX * 1e3:.0f} mm apart")
        print(f"{'PASS' if bent == 0 else 'FAIL'} {name} shading: {bent} flat faces with a corner normal > "
              f"{FLAT_TOL} deg off the face normal (worst {worst:.2f} deg)")
    print(f"INFO total {total} tris")
    lab, owner, overlap = raster_labels(objs, tex)
    per = {}
    for name, o in objs.items():
        me = o.data; uv = me.uv_layers.active.data; isl = uv_islands(me); acc = {}
        for p in me.polygons:
            U = np.array([uv[l].uv[:] for l in p.loop_indices]); x, y = U[:, 0], U[:, 1]
            au = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            a = acc.setdefault(isl[p.index], [0.0, 0.0]); a[0] += p.area; a[1] += au
        d = [tex * math.sqrt(v[1] / v[0]) for v in acc.values() if v[0] > 1e-6]
        per[name] = (len(acc), round(min(d)), round(float(np.median(d))), round(max(d)))
        print(f"INFO UV {name}: {len(acc)} islands, island density min / median / max {per[name][1:]} px/m at {tex}")
    gap_px, border_px = UV.PAD_PX, UV.BORDER_PX
    gap, border = padding(lab, gap_px, border_px)
    fill = (lab > 0).mean()
    ok = gap is None and border >= border_px and overlap == 0
    ok_all &= ok
    print(f"{'PASS' if gap is None else 'FAIL'} island padding >= {gap_px} px" + ("" if gap is None else f" (closest {gap} px)"))
    print(f"{'PASS' if border >= border_px else 'FAIL'} sheet border >= {border_px} px ({border} px)")
    print(f"{'PASS' if overlap == 0 else 'FAIL'} no overlapping UVs ({overlap} texels claimed twice)")
    print(f"INFO packing {fill * 100:.1f} % of the {tex} sheet")
    out["_uv"] = dict(tex=tex, padding_close=gap, border_px=border, fill=round(float(fill), 3), density=per)
    os.makedirs(SCR, exist_ok=True)
    np.save(os.path.join(SCR, "uv_labels.npy"), lab)
    json.dump(out, open(os.path.join(SCR, "topo.json"), "w"), indent=1)
    print("RESULT topo:", "PASS" if ok_all else "FAIL")


import cradle_v2_uv as UV                                # noqa: E402  (padding constants)


# --------------------------------------------------------------------------- clearances


def world_tris(objs_list):
    P, F = [], []
    for o in objs_list:
        k = len(P); W = o.matrix_world; o.data.calc_loop_triangles()
        P += [W @ v.co for v in o.data.vertices]; F += [tuple(k + i for i in t.vertices) for t in o.data.loop_triangles]
    return P, F


def samples(objs_, step=0.004):
    """vertices, face centres and points on every triangle (spacing ~step)"""
    pts = []
    for o in objs_:
        W = o.matrix_world; me = o.data; me.calc_loop_triangles()
        V = [W @ v.co for v in me.vertices]
        pts += V
        for t in me.loop_triangles:
            a, b, c = (V[i] for i in t.vertices)
            n = max(1, int(max((b - a).length, (c - a).length, (c - b).length) / step))
            for i in range(n + 1):
                for j in range(n + 1 - i):
                    pts.append(a + (b - a) * (i / n) + (c - a) * (j / n))
    return pts


_SAMPLE_CACHE = {}


def local_samples(o, step):
    key = (o.name, step)
    if key not in _SAMPLE_CACHE:
        W = o.matrix_world.inverted()
        _SAMPLE_CACHE[key] = [W @ p for p in samples([o], step)]
    return _SAMPLE_CACHE[key]


def min_gap(a_objs, b_objs, step=0.004, reach=0.30):
    """smallest distance between the surfaces of a and b (points sampled on each, nearest on the other's BVH);
    only points within `reach` of the other's bounding box are tested"""
    Pb, Fb = world_tris(b_objs); tb = BVHTree.FromPolygons(Pb, Fb)
    Pa, Fa = world_tris(a_objs); ta = BVHTree.FromPolygons(Pa, Fa)
    def bbox(P):
        A = np.array([p[:] for p in P]); return A.min(0) - reach, A.max(0) + reach
    ba, bb = bbox(Pa), bbox(Pb)
    best = (1e9, None)
    for objs_, tree, (lo, hi) in ((a_objs, tb, bb), (b_objs, ta, ba)):
        for o in objs_:
            W = o.matrix_world
            for q in local_samples(o, step):
                p = W @ q
                if p.x < lo[0] or p.y < lo[1] or p.z < lo[2] or p.x > hi[0] or p.y > hi[1] or p.z > hi[2]: continue
                h = tree.find_nearest(p, reach)
                if h[0] is not None and h[3] < best[0]: best = (h[3], p)
    hit = bool(ta.overlap(tb))
    return best[0], (spec(best[1]) if best[1] is not None else None), hit


# labyrinth panel v2 (HERO_SPEC §8), world: pivot (0.025, 1.00, 1.225), plate 1.05 x 0.025 x 1.05 (origin at the
# underside centre), outer rim 0.05 thick x 0.08 high on the plate; handle bar on the front edge (player side)
PANEL_PIVOT = (0.025, 1.00, 1.225)
PANEL_HALF, PLATE_T, RIM_W, RIM_H = 0.525, 0.025, 0.05, 0.08
TILT_MAX = 12.0


def world_to_local(p):
    """world (Unity) -> stand-local (yaw 180 about the stand origin)"""
    ox, oy, oz = L.WORLD_ORIGIN
    return (-(p[0] - ox), p[1] - oy, -(p[2] - oz))


def panel_object():
    """the panel as boxes in PANEL-LOCAL Unity coordinates (pivot at the origin), as a Blender object whose matrix is
    set per tilt; returns (object, function(tilt_dir_deg, tilt_deg) -> sets matrix_world in the stand-local frame)"""
    sm = L.Mesh()
    h = PANEL_HALF
    def box(x0, x1, y0, y1, z0, z1):
        r = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
        sm.tube([L.ring(r, y0), L.ring(r, y1)]); sm.f(*L.ring(r, y1)); sm.f(*reversed(L.ring(r, y0)))
    box(-h, h, 0.0, PLATE_T, -h, h)
    y0, y1 = PLATE_T, PLATE_T + RIM_H
    box(h - RIM_W, h, y0, y1, -h, h); box(-h, -h + RIM_W, y0, y1, -h, h)
    box(-h + RIM_W, h - RIM_W, y0, y1, h - RIM_W, h); box(-h + RIM_W, h - RIM_W, y0, y1, -h, -h + RIM_W)
    # handle: bar 0.035 x 0.25 along X on the front edge (-Z), standing 0.08 off the rim
    box(-0.125, 0.125, y0 + 0.02, y0 + 0.055, -h - 0.08 - 0.0175, -h - 0.08 + 0.0175)
    me = sm.finish("PanelProxy")
    o = bpy.data.objects.new("PanelProxy", me); bpy.context.scene.collection.objects.link(o)

    def pose(phi, theta):
        """tilt: the panel's up vector leans theta from world up toward azimuth phi (world XZ), cone-clamped"""
        a = math.radians(phi); t = math.radians(theta)
        # axis in world (Unity) XZ, perpendicular to the lean direction (cos a, 0, sin a)
        ax_u = np.array((-math.sin(a), 0.0, math.cos(a)))
        # Unity world -> stand-local: x -> -x, z -> -z (yaw 180); stand-local -> Blender: (x, y, z) -> (-x, -z, y)
        def u2b_world(v):
            lx, ly, lz = -v[0], v[1], -v[2]
            return Vector((-lx, -lz, ly))
        axis_b = u2b_world(ax_u).normalized()
        # rotation sense: lean the up vector toward (cos a, 0, sin a): check the sign numerically
        R = Matrix.Rotation(t, 4, axis_b)
        lean = u2b_world((math.cos(a), 0.0, math.sin(a)))
        if (R @ Vector((0, 0, 1))).dot(lean) < 0: R = Matrix.Rotation(-t, 4, axis_b)
        piv = L.to_blender(world_to_local(PANEL_PIVOT))
        # panel-local Unity -> Blender: the mesh was authored in Unity axes and mapped x -> -x; the world panel axes are
        # Unity world axes; the stand-local frame is the world turned 180 deg about Y: turn the mesh by 180 about Blender z
        o.matrix_world = Matrix.Translation(piv) @ R @ Matrix.Rotation(math.pi, 4, 'Z')
        bpy.context.view_layer.update()
    return o, pose


def reach_report(objs):
    """player at the labyrinth operating position (world 0, 0, 0; ENVIRONMENT_SPEC), eye 1.36; shoulders estimated
    at y 1.40, +-0.18 to the sides; arm reach ~0.65 m (comfortable grab ~0.55)"""
    lever = objs["Lever_01"]
    for deg, lab in ((L.REST_DEG, "rest"), (L.PULLED_DEG, "pulled")):
        L.set_lever(lever, deg)
        tip = lever.matrix_world @ (Vector((0, 0, L.SHAFT_L + L.GRIP_L * 0.5)))     # grip centre (Blender local z = up)
        w = spec(tip)                                                                 # stand-local
        world = (L.WORLD_ORIGIN[0] - w.x, w.y, L.WORLD_ORIGIN[2] - w.z)
        sh = np.array((0.18, 1.40, 0.0))
        d = np.linalg.norm(np.array(world) - sh)
        horiz = math.hypot(world[0], world[2])
        print(f"INFO reach {lab}: grip centre world {tuple(round(c, 3) for c in world)}, {d:.2f} m from the right "
              f"shoulder at the operating position ({horiz:.2f} m horizontal from the player's centre); "
              f"one step of {max(0.0, d - 0.55):.2f} m brings it to a comfortable 0.55 m")
    L.set_lever(lever, L.REST_DEG)


def clearance(args):
    objs = open_file()
    body, lever, lamp = objs["Body_01"], objs["Lever_01"], objs["Lamp_01"]
    ok_all = True
    # 1. lever sweep rest -> pulled (61 poses, 1 deg) against the body and the lamp
    worst = (1e9, 0, None); hits = []
    for k in range(61):
        deg = L.REST_DEG + (L.PULLED_DEG - L.REST_DEG) * k / 60
        L.set_lever(lever, deg)
        d, at, hit = min_gap([lever], [body, lamp], 0.003, 0.05)
        if hit: hits.append(round(deg, 1))
        if d < worst[0]: worst = (d, deg, at)
    ok = not hits and worst[0] >= 0.004
    ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} lever sweep {L.REST_DEG:+.0f} ... {L.PULLED_DEG:+.0f} deg vs body + lamp: min gap "
          f"{worst[0] * 1e3:.1f} mm at {worst[1]:+.0f} deg near stand-local {tuple(round(c, 3) for c in worst[2])}"
          + (f"; intersections at {hits}" if hits else ""))
    trig = L.REST_DEG + (L.PULLED_DEG - L.REST_DEG) * L.TRIGGER_FRAC
    print(f"INFO trigger angle: {trig:+.1f} deg stand-local (80 % of {L.PULLED_DEG - L.REST_DEG:.0f} deg)")
    # lever vs the slot edges at the extremes (shaft against the slot ends) and the hinge depth
    for deg in (L.REST_DEG, L.PULLED_DEG):
        t = math.radians(abs(deg))
        exit_off = (L.HY1 - L.HINGE[1]) * math.tan(t) + L.SHAFT_R / math.cos(t)
        end = (L.HINGE[2] - L.SLOT["z0"]) if deg < 0 else (L.SLOT["z1"] - L.HINGE[2])
        print(f"INFO slot at {deg:+.0f} deg: shaft edge {exit_off * 1e3:.1f} mm from the hinge at the top face, slot end "
              f"{end * 1e3:.1f} mm -> {(end - exit_off) * 1e3:.1f} mm clear")
    L.set_lever(lever, L.REST_DEG)
    # 2. labyrinth panel tilt cone vs the stand (body, lamp, lever at rest and pulled)
    panel, pose = panel_object()
    edge_best = (1e9, None, None)
    rows = []
    for deg in (L.REST_DEG, L.PULLED_DEG):
        L.set_lever(lever, deg)
        for theta in (0.0, 4.0, 8.0, 12.0):
            for phi in ([0.0] if theta == 0 else range(0, 360, 15)):
                pose(phi, theta)
                d, at, hit = min_gap([panel], [body, lever, lamp], 0.006, 0.25)
                if hit: d = -1.0
                if d < edge_best[0]: edge_best = (d, (phi, theta, deg), at)
        rows.append(edge_best)
    pose(0.0, 0.0)
    d0, at0, _ = min_gap([panel], [body], 0.004)
    # HERO_SPEC §6: 0.15 from the panel's +X edge when level (the pedestal face vs the plate/rim edge, horizontally);
    # under tilt the 80 mm rim swings ~5 mm outward (§8 assumes up/down only): gate = no contact with >= 0.10,
    # the tilt minimum is reported for the owner (BUILD.md, open question)
    edge_gap = (L.WORLD_ORIGIN[0] - L.PW / 2) - (PANEL_PIVOT[0] + PANEL_HALF)
    ok0 = edge_gap >= 0.15 - 1e-6 and d0 >= 0.15 - 1e-4
    ok = ok0 and edge_best[0] >= 0.10
    ok_all &= ok
    phi, theta, ldeg = edge_best[1]
    print(f"{'PASS' if ok0 else 'FAIL'} panel level: pedestal face -> panel +X edge {edge_gap * 1e3:.1f} mm (spec 150); "
          f"min surface gap {d0 * 1e3:.1f} mm near stand-local {tuple(round(c, 3) for c in at0)}")
    print(f"{'PASS' if ok else 'FAIL'} (no contact, >= 100 mm; {'meets' if edge_best[0] >= 0.15 else 'BELOW'} 150 mm) panel tilt cone (theta 0-{TILT_MAX:.0f} deg, every 15 deg azimuth; lever rest and "
          f"pulled) vs the stand: min gap {edge_best[0] * 1e3:.1f} mm at azimuth {phi} deg, tilt {theta} deg, "
          f"lever {ldeg:+.0f} deg, near stand-local {tuple(round(c, 3) for c in edge_best[2])}")
    bpy.data.objects.remove(panel)
    # 3. hidden faces over the lever's poses (ray test; nothing is deleted here, the generator builds none)
    parts = [body, lever, lamp]
    dirs = CV.fib_dirs(96)
    box = ((-0.6, -0.6, -0.1), (0.6, 0.6, 1.6))
    keep = {o.name: set() for o in parts}
    for deg in (L.REST_DEG, 0.0, L.PULLED_DEG):
        L.set_lever(lever, deg)
        tree = CV.scene_bvh(parts)
        for o in parts: keep[o.name] |= CV.visible_faces(o, tree, dirs, box)
    L.set_lever(lever, L.REST_DEG)
    for o in parts:
        hid = [p.index for p in o.data.polygons if p.index not in keep[o.name]]
        where = [tuple(round(c, 3) for c in spec(o.matrix_world @ o.data.polygons[i].center)) for i in hid[:6]]
        print(f"{'PASS' if not hid else 'INFO'} hidden faces {o.name.replace(L.HERO + '_', '')}: {len(hid)} never seen "
              f"in 96 directions over rest / upright / pulled" + (f" (e.g. {where})" if hid else ""))
    # 4. released-state drone volume (HERO_SPEC §2) and the labyrinth cylinder exception (§6)
    lo, hi = np.array([1e9] * 3), np.array([-1e9] * 3)
    for o in parts:
        for v in o.data.vertices:
            s = spec(o.matrix_world @ v.co); w = np.array((L.WORLD_ORIGIN[0] - s.x, s.y, L.WORLD_ORIGIN[2] - s.z))
            lo, hi = np.minimum(lo, w), np.maximum(hi, w)
    clear = hi[2] < 2.84 or lo[1] > 3.48 or hi[1] < 1.19
    ok_all &= clear
    print(f"{'PASS' if clear else 'FAIL'} drone volume (released): stand world box {np.round(lo, 3).tolist()} .. "
          f"{np.round(hi, 3).tolist()} is outside X -2.45..2.39, Y 1.19..3.48, Z 2.84..6.32")
    c = np.array((0.03, 1.23))
    r = min(np.hypot(x - c[0], z - c[1]) for x in (lo[0], hi[0]) for z in (lo[2], hi[2]))
    print(f"INFO labyrinth protected cylinder r 1.24 around (0.03, 1.23): nearest stand corner at {r:.2f} m (inside, the "
          f"deliberate exception of HERO_SPEC §6); distance origin -> operating position (0, 0, 0): "
          f"{math.hypot(*L.WORLD_ORIGIN[::2]):.2f} m (spec 1.04)")
    reach_report(objs)
    print("RESULT clearance:", "PASS" if ok_all else "FAIL")


# --------------------------------------------------------------------------- review renders


def add_room(objs):
    """floor and the labyrinth panel (level) around the stand, in the stand-local frame"""
    m = bpy.data.materials.new("M_RoomProxy"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.05, 0.055, 0.06, 1)
    b.inputs["Roughness"].default_value = 0.8
    me = bpy.data.meshes.new("Floor")
    me.from_pydata([L.to_blender(p) for p in ((-3, 0, -3), (3, 0, -3), (3, 0, 3), (-3, 0, 3))], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new("Floor", me); bpy.context.scene.collection.objects.link(fl); me.materials.append(m)
    panel, pose = panel_object(); pose(0.0, 0.0)
    pm = bpy.data.materials.new("M_PanelProxy"); pm.use_nodes = True
    pb = pm.node_tree.nodes["Principled BSDF"]; pb.inputs["Base Color"].default_value = (0.03, 0.035, 0.04, 1)
    pb.inputs["Roughness"].default_value = 0.5
    panel.data.materials.append(pm)
    # labyrinth stand (cone, HERO_SPEC §8) as a simple cylinder proxy under the pivot
    piv = world_to_local(PANEL_PIVOT)
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.2, radius2=0.02, depth=0.97,
                                    location=L.to_blender((piv[0], 0.485, piv[2])))
    cone = bpy.context.active_object; cone.data.materials.append(pm)
    return fl, panel


def room_lights(scale=1.0):
    return [add_light("Key", (-0.8, 2.6, 1.2), (0.0, 0.8, 0.0), 70 * scale, 1.5, (0.85, 0.92, 1.0)),
            add_light("Fill", (0.6, 1.3, 2.0), (0.0, 0.7, 0.0), 14 * scale, 2.0, (0.7, 0.85, 1.0)),
            add_light("Rim", (1.2, 2.2, -1.5), (0.0, 0.9, 0.0), 18 * scale, 1.0, (1.0, 0.85, 0.7))]


def player_cam():
    """the player's eye at the labyrinth operating position (world 0, 1.36, 0) looking at the lever grip"""
    eye = world_to_local((0.0, 1.36, 0.0))
    return dict(loc=eye, look=(L.HINGE[0], 1.05, 0.0), lens=24)


VIEWS = {
    "room": None,                                                       # player view, set at runtime
    "34": dict(loc=(-1.2, 1.55, 1.6), look=(0.0, 0.62, 0.0), lens=35),
    "front": dict(loc=(0.0, 0.62, 3.0), look=(0.0, 0.62, 0.0), ortho=1.45),
    "side": dict(loc=(-3.0, 0.62, 0.0), look=(0.0, 0.62, 0.0), ortho=1.45),
    "top": dict(loc=(-0.25, 1.32, 0.38), look=(0.0, 1.02, -0.01), lens=40),
    "lever": dict(loc=(-0.35, 1.18, 0.30), look=(0.03, 1.08, -0.02), lens=50),
    "lamp": dict(loc=(-0.25, 1.15, -0.25), look=(-0.055, 1.06, -0.035), lens=70),
    "base": dict(loc=(-0.55, 0.45, 0.75), look=(0.0, 0.15, 0.0), lens=35),
}


def renders(args):
    tag = args[0] if args else "h1"
    only = set(args[1:])
    objs = open_file()
    tex = "textured" in only; only.discard("textured")
    if tex:
        import leverstand_tex as T
        T.apply_baked(objs)
    sc = scene_setup(size=(1400, 1000), samples=96)
    add_room(objs); room_lights()
    VIEWS["room"] = player_cam()
    for k, v in VIEWS.items():
        if only and k not in only: continue
        camera(v["loc"], v["look"], v.get("lens", 40), v.get("ortho"))
        p = shot(os.path.join(SCR, f"{tag}_{k}.png"))
        save_jpg(load_srgb(p, 1000), os.path.join(MEDIA, f"leverstand_{tag}_{k}.jpg"))
    if not only or "pulled" in only:
        L.set_lever(objs["Lever_01"], L.PULLED_DEG)
        camera(**{k: v for k, v in VIEWS["side"].items()})
        p = shot(os.path.join(SCR, f"{tag}_side_pulled.png"))
        save_jpg(load_srgb(p, 1000), os.path.join(MEDIA, f"leverstand_{tag}_side_pulled.jpg"))
        L.set_lever(objs["Lever_01"], L.REST_DEG)
    def flat_mat(name, rgb, rough=0.5, emit=False, image=None):
        m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
        bs = nt.nodes["Principled BSDF"]; bs.inputs["Base Color"].default_value = (*rgb, 1); bs.inputs["Roughness"].default_value = rough
        if image is not None:                                          # flat (emission) checker: no shading
            tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = image; e = nt.nodes.new("ShaderNodeEmission")
            nt.links.new(tn.outputs[0], e.inputs[0]); nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
        return m
    def set_all(objs_, m):
        for o in objs_.values():
            for i in range(len(o.data.materials)): o.data.materials[i] = m
    hide = [bpy.data.objects[n] for n in ("Floor", "PanelProxy", "Cone") if n in bpy.data.objects]
    if not tex and (not only or "wire" in only):                     # Cycles (no OpenGL in the cloud container)
        for o in hide: o.hide_render = True
        set_all(objs, flat_mat("M_WireBase", (0.32, 0.33, 0.35), 0.6))
        dark = flat_mat("M_Wire", (0.01, 0.01, 0.012), 0.9)
        for o, w in CC.add_wire({k: o for k, o in objs.items()}, 0.0006):
            for sl in w.material_slots: sl.link = 'OBJECT'; sl.material = dark
        for k in ("34", "top"):
            camera(VIEWS[k]["loc"], VIEWS[k]["look"], VIEWS[k].get("lens", 40))
            p = shot(os.path.join(SCR, f"{tag}_wire_{k}.png"))
            save_jpg(load_srgb(p, 1000), os.path.join(MEDIA, f"leverstand_{tag}_wire_{k}.jpg"))
        for o in list(bpy.data.objects):
            if o.name.endswith("_wire"): bpy.data.objects.remove(o)
        for o in hide: o.hide_render = False
    if not tex and (not only or "checker" in only):
        for o in hide: o.hide_render = True
        set_all(objs, flat_mat("M_Checker", (1, 1, 1), image=CC.checker_image(L.UV_TEX)))
        for k in ("34", "top"):
            camera(VIEWS[k]["loc"], VIEWS[k]["look"], VIEWS[k].get("lens", 40))
            p = shot(os.path.join(SCR, f"{tag}_checker_{k}.png"))
            save_jpg(load_srgb(p, 1000), os.path.join(MEDIA, f"leverstand_{tag}_checker_{k}.jpg"))
    if not tex and (not only or "uv" in only):
        uv_layout(tag)


def uv_layout(tag):
    lab = np.load(os.path.join(SCR, "uv_labels.npy"))
    rng = np.random.default_rng(2)
    lut = rng.uniform(0.25, 0.85, (lab.max() + 1, 3)); lut[0] = (0.08, 0.08, 0.09)
    rgb = lut[lab]
    edge = np.zeros(lab.shape, bool)
    edge[:, :-1] |= lab[:, :-1] != lab[:, 1:]; edge[:-1, :] |= lab[:-1, :] != lab[1:, :]
    rgb[edge] = (0.02, 0.02, 0.02)
    save_jpg(rgb.astype(np.float32), os.path.join(MEDIA, f"leverstand_{tag}_uv_layout.jpg"))


def shading(args):
    tag = args[0] if args else "h1"
    objs = open_file()
    scene_setup(size=(1400, 1000), samples=64)
    add_room(objs); room_lights(1.6)
    m = bpy.data.materials.new("M_ShadingGrey"); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.30, 0.30, 0.30, 1)
    b.inputs["Roughness"].default_value = 0.35
    for o in objs.values():
        for i in range(len(o.data.materials)): o.data.materials[i] = m
    for k in ("34", "top", "lever", "base"):
        v = VIEWS[k]
        camera(v["loc"], v["look"], v.get("lens", 40), v.get("ortho"))
        p = shot(os.path.join(SCR, f"{tag}_shading_{k}.png"))
        save_jpg(load_srgb(p, 1000), os.path.join(MEDIA, f"leverstand_{tag}_shading_{k}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"concept": concept, "topo": topo, "clearance": clearance, "renders": renders, "shading": shading}[argv[0]](argv[1:])
