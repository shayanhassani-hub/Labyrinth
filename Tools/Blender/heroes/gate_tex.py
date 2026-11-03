"""
Gate (Hero 03) textures, hero workflow v3 (ASSET_RULES): procedural Blender materials baked in Cycles onto the
export-identical triangulated low (env_kit_generator.triangulated_export_copy, the hero export function: the same
triangles and custom normals, so the baked tangent-space normals match MikkTSpace in Unity).

  blender -b -P Tools/Blender/heroes/gate_tex.py -- bake      details, mask pre-bakes, final bakes, maps
  blender -b -P Tools/Blender/heroes/gate_tex.py -- check     AO black scan, PBR values, normal seams on the leaf faces
  blender -b -P Tools/Blender/heroes/gate_tex.py -- renders [views] [fast]   Renders/gate_g2b_*.png with the BAKED maps
  GATE_TEX=512 (environment) runs bake / check / renders at 512 in their own folders, for cheap look iterations

Pipeline (bake):
 1. texel maps: for every texel of the 2048 sheet its part, material slot, Unity-space position and face normal
    (rasterised from the triangulated lows, closed pose).
 2. detail maps (numpy, from those positions; STYLE_GUIDE / HERO_SPEC §7): bolt heights and masks (frame corners and
    frame, panel corners, 4 per hanger plate, rail brackets, button panel), fine seams (frame groove, panel grooves),
    rust streaks below some bolts and seam corners, rust base (round the bolts, the leaf's bottom edge), the hazard
    band's paint edge.
 3. mask pre-bakes per part (others hidden, margin 0): convex edges (AO node, inside, 8 mm), cavity (AO node, 50 mm,
    self), AO (bake type AO, 0.3 m, self only).
 4. final bakes per part from the procedural materials (noise breakup, edge wear to bare steel, scratches, grime, rust,
    stripes, bevel + bump normal): BaseColor, Normal (OpenGL), Smoothness, Metallic, Emission; margin 0, then one
    8 px dilation of the composite. Mask = R metallic, G AO, A smoothness (linear).
Outputs: D:/AI_Labyrinth/Blender/Export/Heroes/Gate/T_LAB_HERO_Gate_{BaseColor,Normal,Mask,Emission}.png
Never saves the .blend.
"""
import bpy
import math
import os
import sys
import time
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import gate as G                                         # noqa: E402
import env_kit_generator as K                            # noqa: E402

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TEX = int(os.environ.get("GATE_TEX", "2048"))             # GATE_TEX=512 for cheap look iterations (own folders)
_SFX = "" if TEX == 2048 else f"_{TEX}"
WORK = os.path.join(PROJ, "Temp", "claude", "gate", "tex" + _SFX)
RENDERS = os.path.join(PROJ, "Renders")
OUT = "D:/AI_Labyrinth/Blender/Export/Heroes/Gate" + _SFX
CONCEPT = os.path.join(PROJ, "Documentation", "References", "Gate", "gate_front.jpg")   # owner's concept (in the repo)
PARTS = ["Leaf_01", "Rail_01", "ButtonPanel_01", "Button_01"]
RENDER_TAG = "gate_g2b"                                  # review render prefix (G2b look revision)
DILATE = 8
H_LO, H_HI = -0.002, 0.005                               # detail height range (m) in the D1 map
BAKE_SAMPLES = dict(prebake=64, emit=4, normal=16)
EDGE_DIST, EDGE_GAIN = 0.008, 2.2                       # convex-edge pre-bake: AO inside distance, mask gain
RNG = np.random.default_rng(29)


def lin(srgb):
    c = np.asarray(srgb, float) / 255.0
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


# STYLE_GUIDE palette (linear). G2b: the Gate's paint is gunmetal, sampled from the concept's door panels
# (median of the blue-grey panel pixels, brightness of the fully lit top zone): sRGB 90 104 115
PAINT_C, POLY_C, STEEL_C = lin((90, 104, 115)), lin((35, 37, 39)), lin((188, 190, 192))
OCHRE_C, BLACK_C, RUST_C, GRIME_C = lin((159, 120, 58)), lin((35, 37, 39)), lin((120, 62, 34)), lin((44, 41, 37))
CYAN_E, AMBER_E = lin((70, 170, 255)), lin((240, 150, 60))
CYAN_OFF, AMBER_OFF = lin((30, 45, 55)), lin((60, 46, 32))
RUST_DARK, RUST_EDGE = lin((66, 44, 34)), lin((112, 64, 38))   # rust centre brown-black, patch edge orange-brown


def spec(v):
    return np.array((-v[0], v[2], -v[1]))


# --------------------------------------------------------------------------- scene, lows


def open_lows():
    bpy.ops.wm.open_mainfile(filepath=G.SAVE)
    objs = {n: bpy.data.objects[f"{G.HERO}_{n}"] for n in PARTS}
    lows = {}
    for n, o in objs.items():
        c = K.triangulated_export_copy(o)
        c.matrix_world = o.matrix_world.copy(); c.name = f"{n}_bakelow"
        lows[n] = c
        o.hide_render = True; o.hide_set(True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.light_settings.distance = 0.3
    return objs, lows


def texel_maps(lows):
    """per texel: part (1..4, 0 empty), material slot, Unity position, Unity face normal"""
    part = np.zeros((TEX, TEX), np.int8); mat = np.full((TEX, TEX), -1, np.int8)
    P = np.zeros((TEX, TEX, 3), np.float32); N = np.zeros((TEX, TEX, 3), np.float32)
    for pi, (name, o) in enumerate(lows.items(), 1):
        me = o.data; W = o.matrix_world; uv = me.uv_layers.active.data; me.calc_loop_triangles()
        V = np.array([spec(W @ v.co) for v in me.vertices])
        R = W.to_3x3()
        for t in me.loop_triangles:
            U = np.array([uv[l].uv[:] for l in t.loops]) * TEX
            x0, y0 = np.floor(U.min(0)).astype(int); x1, y1 = np.ceil(U.max(0)).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, TEX - 1), min(y1, TEX - 1)
            if x1 < x0 or y1 < y0: continue
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]; px, py = xs + 0.5, ys + 0.5
            (ax, ay), (bx, by), (cx, cy) = U
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12: continue
            w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
            w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
            w2 = 1 - w0 - w1
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not m.any(): continue
            A, B, C = V[list(t.vertices)]
            P[ys[m], xs[m]] = w0[m, None] * A + w1[m, None] * B + w2[m, None] * C
            N[ys[m], xs[m]] = spec((R @ t.normal).normalized())
            part[ys[m], xs[m]] = pi; mat[ys[m], xs[m]] = me.polygons[t.polygon_index].material_index
    return part, mat, P, N


# --------------------------------------------------------------------------- detail maps


def bolts():
    """(part index, centre, normal, hex apothem, washer radius) in Unity space"""
    out = []
    lx, ly = G.LEAF_X0, G.LEAF_Y0
    frame = [(0.058, v) for v in (0.20, 0.72, 1.24, 1.76, 2.28)] + [(u, 2.35) for u in (0.24, 0.62, 0.88, 1.14)] \
        + [(u, 0.06) for u in (0.24, 0.62, 0.88, 1.14, 1.40)] + [(1.58, 0.05), (1.58, 2.40)]
    pnl = []
    for p in G.panels():
        top = G.offset(p, G.PANEL_SLOPE); ins = G.offset(top, 0.024); n = len(ins); own = []
        for i in range(n):
            a, b, c = np.array(ins[i - 1]), np.array(ins[i]), np.array(ins[(i + 1) % n])
            u1, u2 = a - b, c - b
            ang = math.degrees(math.acos(np.clip(u1 @ u2 / (np.linalg.norm(u1) * np.linalg.norm(u2)), -1, 1)))
            cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if 60 <= ang <= 140 and cr > 0 and all(math.dist(b, q) > 0.03 for q in own): own.append(tuple(b))
        pnl += own                                                           # corners incl. the 45 deg field cuts
    for side, z0, zp in ((1, G.LEAF_Z0, G.LEAF_Z0 + G.PANEL_D), (-1, G.LEAF_Z1, G.LEAF_Z1 - G.PANEL_D)):
        nrm = (0, 0, -side)
        out += [(1, (lx + u, ly + v, z0), nrm, 0.0095, 0.0135) for u, v in frame]
        out += [(1, (lx + u, ly + v, zp), nrm, 0.007, 0.010) for u, v in pnl]
    for hc in G.HANGERS:                                                     # 4 per hanger plate (room side)
        zf = G.LEAF_Z0 - G.PLATE["t"]
        out += [(1, (lx + hc + du, ly + v, zf), (0, 0, -1), 0.0085, 0.012) for du in (-0.055, 0.055) for v in (2.305, 2.405)]
    for c in G.RAIL_PLATES:
        out += [(2, (c + dx, y, G.RAIL_PLATE["z0"]), (0, 0, -1), 0.008, 0.0115) for dx in (-0.03, 0.03) for y in (2.497, 2.553)]
    xf = G.PANEL_C[0] + G.PANEL_SZ[0]
    out += [(3, (xf, y, z), (1, 0, 0), 0.006, 0.0085) for y in (1.075, 1.325) for z in (8.615, 8.785)]
    return out, pnl


def seg_dist(pts, poly):
    """distance from 2D points (n, 2) to a closed polygon outline"""
    d = np.full(len(pts), np.inf)
    for i in range(len(poly)):
        a, b = np.array(poly[i]), np.array(poly[(i + 1) % len(poly)])
        ab = b - a; t = np.clip(((pts - a) @ ab) / (ab @ ab), 0, 1)
        d = np.minimum(d, np.linalg.norm(pts - (a + t[:, None] * ab), axis=1))
    return d


def wobble(th, rng, amp=0.35):
    """irregular outline factor for blotches (no perfect rings): 1 + a few low angular harmonics"""
    f = np.ones_like(th)
    for k in (2, 3, 5):
        f += rng.uniform(0.3, 1.0) * amp / k * np.sin(k * th + rng.uniform(0, 2 * math.pi))
    return f


def details(part, mat, P, N):
    H = np.zeros((TEX, TEX), np.float32); BOLT = np.zeros_like(H); STREAK = np.zeros_like(H); GROOVE = np.zeros_like(H)
    RUSTB = np.zeros_like(H); BANDE = np.zeros_like(H)
    bl, pnl = bolts()
    streak_starts = []
    for k, (pi, c, n, a, w) in enumerate(bl):
        c = np.array(c); n = np.array(n, float)
        m = (part == pi) & (np.abs((P - c) @ n) < 0.003) & ((N @ n) > 0.95)
        ys, xs = np.nonzero(m & (np.linalg.norm(P - c, axis=2) < w + 0.02))
        if not len(ys): continue
        up = np.array((0.0, 1.0, 0.0)); up = up - n * (up @ n); up /= np.linalg.norm(up); rt = np.cross(up, n)
        d = P[ys, xs] - c; x, y = d @ rt, d @ up
        th = RNG.uniform(0, math.pi / 3); xr, yr = x * math.cos(th) - y * math.sin(th), x * math.sin(th) + y * math.cos(th)
        r = np.hypot(x, y); dh = np.maximum(np.abs(yr), 0.866 * np.abs(xr) + 0.5 * np.abs(yr))
        washer = np.clip((w - r) / 0.0007, 0, 1); head = np.clip((a - dh) / 0.0012, 0, 1)
        H[ys, xs] = np.maximum(H[ys, xs], 0.0010 * washer + 0.0035 * head)
        BOLT[ys, xs] = np.maximum(BOLT[ys, xs], washer)
        ring = RNG.choice((0.0, 0.45, 0.75, 1.0), p=(0.4, 0.2, 0.2, 0.2))    # per bolt: many clean, some rusty
        reach = RNG.uniform(0.010, 0.024); off = RNG.normal(0, 0.25, 2) * w   # irregular, off-centre, no rings
        x2, y2 = x - off[0], y - off[1]; r2 = np.hypot(x2, y2) * wobble(np.arctan2(y2, x2), RNG, 0.6)
        RUSTB[ys, xs] = np.maximum(RUSTB[ys, xs], ring * np.clip(1 - np.maximum(r2 - w, 0) / reach, 0, 1) * (r > 0.8 * w))
        if abs(n[1]) < 0.3 and ring > 0.5 and RNG.random() < 0.6: streak_starts.append((pi, c - up * w * 0.8, n, up, w))
    # rust blotches in some panel corners (both faces), each with a chance of a run-off streak below it
    lf0 = part == 1
    for side, zp in ((1, G.LEAF_Z0 + G.PANEL_D), (-1, G.LEAF_Z1 - G.PANEL_D)):
        n = np.array((0.0, 0.0, -side)); up = np.array((0.0, 1.0, 0.0)); rt = np.cross(up, n)
        sel = lf0 & (np.abs(P[..., 2] - zp) < 0.0005) & (np.abs(N[..., 2]) > 0.99)
        for u, v in pnl:
            if RNG.random() > 0.45: continue
            c = np.array((G.LEAF_X0 + u, G.LEAF_Y0 + v, zp)); R = RNG.uniform(0.03, 0.075) * (1.25 if v < 0.9 else 1.0)
            ys, xs = np.nonzero(sel & (np.linalg.norm(P - c, axis=2) < 2.2 * R))
            if not len(ys): continue
            d = P[ys, xs] - c; x, y = d @ rt, d @ up
            r = np.hypot(x, y) * wobble(np.arctan2(y, x), RNG, 0.9)
            RUSTB[ys, xs] = np.maximum(RUSTB[ys, xs], np.clip(1 - r / R, 0, 1) ** 0.7)
            if RNG.random() < 0.5: streak_starts.append((1, c - up * R * 0.4, n, up, 0.006))
    # fine seams: frame groove (both leaf faces) and one groove round each panel
    lf = part == 1
    face_groups = [(G.LEAF_Z0, [G.offset(G.OUTLINE, 0.024)]), (G.LEAF_Z1, [G.offset(G.OUTLINE, 0.024)]),
                   (G.LEAF_Z0 + G.PANEL_D, [G.offset(G.offset(p, G.PANEL_SLOPE), 0.040) for p in G.panels()]),
                   (G.LEAF_Z1 - G.PANEL_D, [G.offset(G.offset(p, G.PANEL_SLOPE), 0.040) for p in G.panels()])]
    for zf, polys in face_groups:
        m = lf & (np.abs(P[..., 2] - zf) < 0.0005) & (np.abs(N[..., 2]) > 0.99)
        ys, xs = np.nonzero(m)
        uv = np.column_stack((P[ys, xs, 0] - G.LEAF_X0, P[ys, xs, 1] - G.LEAF_Y0))
        d = np.min([seg_dist(uv, p) for p in polys], axis=0)
        H[ys, xs] -= 0.0012 * np.clip(1 - (d / 0.0016) ** 2, 0, 1)
        GROOVE[ys, xs] = np.maximum(GROOVE[ys, xs], np.clip(1 - d / 0.003, 0, 1))
        for p in polys:                                                      # streaks from the lowest groove corners
            for u, v in sorted(p, key=lambda q: q[1])[:2]:
                if RNG.random() < 0.6:
                    nrm = np.array((0, 0, -1.0 if zf < 7.91 else 1.0))
                    streak_starts.append((1, np.array((G.LEAF_X0 + u, G.LEAF_Y0 + v, zf)), nrm, np.array((0, 1.0, 0)), 0.004))
    for pi, s, n, up, w in streak_starts:                                     # rust streaks running down
        L = RNG.uniform(0.08, 0.32); wd = RNG.uniform(0.003, 0.007)
        m = (part == pi) & (np.abs((P - s) @ n) < 0.003) & ((N @ n) > 0.95)
        rt = np.cross(up, n)
        d = P - s; x, y = d @ rt, -(d @ up)
        sel = m & (y > 0) & (y < L) & (np.abs(x) < 3 * wd)
        ys, xs = np.nonzero(sel)
        t = y[ys, xs] / L; ww = wd * (1 + 1.5 * t)
        val = np.clip(1 - np.abs(x[ys, xs]) / ww, 0, 1) * (1 - t) ** 1.5
        STREAK[ys, xs] = np.maximum(STREAK[ys, xs], val)
    # rust base along the leaf's bottom edge; hazard band paint edge
    v = P[..., 1] - G.LEAF_Y0
    # (G2b: the bottom-edge rust is a patchy shader term, see surface_material)
    bm = lf & (mat >= 0) & ((np.abs(P[..., 2] - G.LEAF_Z0) < 0.0005) | (np.abs(P[..., 2] - G.LEAF_Z1) < 0.0005))
    ys, xs = np.nonzero(bm)
    uv = np.column_stack((P[ys, xs, 0] - G.LEAF_X0, P[ys, xs, 1] - G.LEAF_Y0))
    BANDE[ys, xs] = np.clip(1 - seg_dist(uv, G.BAND) / 0.010, 0, 1)
    Hn = (np.clip(H, H_LO, H_HI) - H_LO) / (H_HI - H_LO)
    print(f"INFO details: {len(bl)} bolts ({len(pnl)} panel corners per face), {len(streak_starts)} rust streaks")
    return np.stack([Hn, BOLT, STREAK, GROOVE], 2), RUSTB, BANDE


def new_image(name, arr=None, size=TEX):
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'; img.alpha_mode = 'CHANNEL_PACKED'
    if arr is not None:
        a = np.ones((size, size, 4), np.float32); a[..., :arr.shape[2]] = arr
        img.pixels.foreach_set(a.ravel())
    return img


def pixels(img):
    n = img.size[0]; a = np.empty(n * n * 4, np.float32); img.pixels.foreach_get(a); return a.reshape(n, n, 4)


# --------------------------------------------------------------------------- baking


def run_bake(lows, name, img, kind, samples):
    """bake every part on its own (others hidden), margin 0, into img; returns seconds"""
    sc = bpy.context.scene; sc.cycles.samples = samples
    t = time.time()
    for i, (n, o) in enumerate(lows.items()):
        for x in lows.values(): x.hide_render = x is not o; x.select_set(x is o)
        bpy.context.view_layer.objects.active = o
        for m in o.data.materials:
            for nd in m.node_tree.nodes:
                if nd.type == 'TEX_IMAGE' and nd.name == "BakeTarget": nd.image = img; m.node_tree.nodes.active = nd
        kw = dict(target='IMAGE_TEXTURES', use_clear=(i == 0), margin=0)
        if kind == "NORMAL":
            bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', normal_r='POS_X', normal_g='POS_Y', normal_b='POS_Z', **kw)
        elif kind == "AO":
            bpy.ops.object.bake(type='AO', **kw)
        else:
            bpy.ops.object.bake(type='EMIT', **kw)
    for x in lows.values(): x.hide_render = False
    dt = time.time() - t
    print(f"BAKE {name}: {dt:.0f} s")
    return dt


def add_target(nt):
    t = nt.nodes.new("ShaderNodeTexImage"); t.name = "BakeTarget"; t.location = (1400, -600)
    return t


def prebake_material(kind):
    m = bpy.data.materials.new(f"M_Pre_{kind}"); m.use_nodes = True; nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
    out = nt.nodes["Material Output"]; em = nt.nodes.new("ShaderNodeEmission")
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion"); ao.only_local = True; ao.samples = 16
    if kind == "edge":
        ao.inside = True; ao.inputs["Distance"].default_value = EDGE_DIST
        inv = nt.nodes.new("ShaderNodeMath"); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
        nt.links.new(ao.outputs["AO"], inv.inputs[1]); nt.links.new(inv.outputs[0], em.inputs["Color"])
    else:
        ao.inputs["Distance"].default_value = 0.05
        nt.links.new(ao.outputs["AO"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    add_target(nt)
    return m


def swap_materials(lows, mats_by_slot):
    keep = {n: list(o.data.materials) for n, o in lows.items()}
    for n, o in lows.items():
        for i in range(len(o.data.materials)):
            o.data.materials[i] = mats_by_slot(i)
    return keep


def restore(lows, keep):
    for n, o in lows.items():
        for i, m in enumerate(keep[n]): o.data.materials[i] = m


def blur_masked(a, mask, n=1):
    for _ in range(n):
        acc = np.zeros_like(a); cnt = np.zeros_like(a)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                f = np.roll(np.roll(mask, dy, 0), dx, 1).astype(np.float32)
                acc += np.roll(np.roll(a, dy, 0), dx, 1) * f; cnt += f
        a = np.where(mask, acc / np.maximum(cnt, 1), a)
    return a


def dilate(a, mask, n=DILATE):
    """extend the texels of mask outward by n pixels (empty pixels with filled 8-neighbours take their mean)"""
    a = a.copy(); filled = mask.copy()
    for _ in range(n):
        acc = np.zeros_like(a); cnt = np.zeros(a.shape[:2], np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0: continue
                f = np.roll(np.roll(filled, dy, 0), dx, 1)
                acc += np.roll(np.roll(a, dy, 0), dx, 1) * f[..., None]; cnt += f
        new = ~filled & (cnt > 0)
        if not new.any(): break
        a[new] = acc[new] / cnt[new][:, None]; filled |= new
    return a


# --------------------------------------------------------------------------- procedural materials


class NB:
    """small node builder"""

    def __init__(self, nt):
        self.nt = nt; self.x = 0

    def n(self, kind, **props):
        nd = self.nt.nodes.new(kind); self.x += 1; nd.location = (200 * (self.x % 8), -200 * (self.x // 8))
        for k, v in props.items(): setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.nt.links.new(a, b)

    def val(self, x):
        if isinstance(x, (int, float)):
            v = self.n("ShaderNodeValue"); v.outputs[0].default_value = float(x); return v.outputs[0]
        return x

    def math(self, op, a, b=None, clamp=False):
        m = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, x in enumerate((a, b)):
            if x is None: continue
            if isinstance(x, (int, float)): m.inputs[i].default_value = float(x)
            else: self.link(x, m.inputs[i])
        return m.outputs[0]

    def add(self, *xs):
        r = xs[0]
        for x in xs[1:]: r = self.math('ADD', r, x)
        return r

    def mul(self, a, b): return self.math('MULTIPLY', a, b)

    def sub(self, a, b): return self.math('SUBTRACT', a, b)

    def clamp(self, a): return self.math('ADD', a, 0.0, clamp=True)

    def remap(self, x, a, b, c=0.0, d=1.0):
        m = self.n("ShaderNodeMapRange", clamp=True)
        self.link(x, m.inputs["Value"]) if not isinstance(x, (int, float)) else None
        m.inputs["From Min"].default_value = a; m.inputs["From Max"].default_value = b
        m.inputs["To Min"].default_value = c; m.inputs["To Max"].default_value = d
        return m.outputs["Result"]

    def rgb(self, c):
        n = self.n("ShaderNodeRGB"); n.outputs[0].default_value = (*c, 1.0); return n.outputs[0]

    def mix(self, fac, a, b, blend='MIX'):
        m = self.n("ShaderNodeMix", data_type='RGBA', blend_type=blend, clamp_result=False)
        for sock, x in ((m.inputs[0], fac), (m.inputs[6], a), (m.inputs[7], b)):
            if isinstance(x, (int, float)): sock.default_value = x
            elif isinstance(x, tuple): sock.default_value = (*x, 1.0)
            else: self.link(x, sock)
        return m.outputs[2]

    def mixf(self, fac, a, b):
        m = self.n("ShaderNodeMix", data_type='FLOAT', clamp_result=False)
        for sock, x in ((m.inputs[0], fac), (m.inputs[2], a), (m.inputs[3], b)):
            if isinstance(x, (int, float)): sock.default_value = x
            else: self.link(x, sock)
        return m.outputs[0]

    def noise(self, vec, scale, detail=4.0, rough=0.55, stretch=None):
        if stretch:
            mp = self.n("ShaderNodeMapping"); mp.inputs["Scale"].default_value = stretch; self.link(vec, mp.inputs[0]); vec = mp.outputs[0]
        t = self.n("ShaderNodeTexNoise"); self.link(vec, t.inputs["Vector"])
        t.inputs["Scale"].default_value = scale; t.inputs["Detail"].default_value = detail
        t.inputs["Roughness"].default_value = rough
        return t.outputs["Fac"]


def surface_material(slot, d1, d2, ao_img):
    """the procedural material of one slot; returns the material with sockets named for the channel bakes"""
    name = G.MATS[slot][0] + "_Tex"
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
    b = NB(nt)
    out = nt.nodes["Material Output"]
    bsdf = b.n("ShaderNodeBsdfPrincipled")
    em = b.n("ShaderNodeEmission"); em.name = "BakeEmit"
    add_target(nt)
    tc = b.n("ShaderNodeTexCoord"); obj = tc.outputs["Object"]
    geo = b.n("ShaderNodeNewGeometry"); pos = b.n("ShaderNodeSeparateXYZ"); b.link(geo.outputs["Position"], pos.inputs[0])
    t1 = b.n("ShaderNodeTexImage", image=d1, interpolation='Linear'); t2 = b.n("ShaderNodeTexImage", image=d2, interpolation='Linear')
    s1 = b.n("ShaderNodeSeparateColor"); s2 = b.n("ShaderNodeSeparateColor")
    b.link(t1.outputs["Color"], s1.inputs[0]); b.link(t2.outputs["Color"], s2.inputs[0])
    Hn, BO, ST = s1.outputs[0], s1.outputs[1], s1.outputs[2]; GR = t1.outputs["Alpha"]
    E, C, RB = s2.outputs[0], s2.outputs[1], s2.outputs[2]; BE = t2.outputs["Alpha"]
    nf = b.noise(obj, 90.0, 6.0); nw = b.noise(obj, 2.5, 4.0); nr = b.noise(obj, 22.0, 10.0, 0.65)
    nr2 = b.noise(obj, 140.0, 4.0)
    # scratches (G2b): long fine hairlines, mostly horizontal / diagonal, plus a few longer streaks; no short dashes.
    # Object coords: Blender z = up and the leaf faces lie in Blender x-z, so a rotation about Blender y turns the
    # lines within the face; stretching z makes the noise change fast across the line and slowly along it.
    def hairlines(rot_deg, scale, stretch, width, dens, lo, hi, seed):
        mp = b.n("ShaderNodeMapping"); b.link(obj, mp.inputs[0])
        mp.inputs["Scale"].default_value = (1.0, 1.0, stretch); mp.inputs["Rotation"].default_value = (0.0, math.radians(rot_deg), 0.0)
        mp.inputs["Location"].default_value = (seed, 0.37 * seed, 0.0)
        t = b.n("ShaderNodeTexNoise"); b.link(mp.outputs[0], t.inputs["Vector"])
        t.inputs["Scale"].default_value = scale; t.inputs["Detail"].default_value = 1.5; t.inputs["Roughness"].default_value = 0.4
        ln = b.remap(b.math('ABSOLUTE', b.sub(t.outputs["Fac"], 0.5)), 0.0, width, 1.0, 0.0)
        return b.mul(ln, b.remap(b.noise(obj, dens, 2.0), lo, hi))
    scratch = b.math('MAXIMUM', hairlines(0, 1.6, 70.0, 0.0080, 1.2, 0.46, 0.56, 0.0),
                     hairlines(28, 1.4, 70.0, 0.0050, 1.4, 0.50, 0.60, 3.1))
    scratch = b.math('MAXIMUM', scratch, hairlines(-35, 1.3, 70.0, 0.0050, 1.3, 0.53, 0.62, 7.7))
    scratch = b.math('MAXIMUM', scratch, b.mul(hairlines(8, 0.6, 30.0, 0.0120, 0.9, 0.58, 0.68, 11.3), 0.8))   # few long streaks
    sy = pos.outputs[2]                                                       # Unity y (height)
    grime = b.clamp(b.add(b.mul(b.sub(1.0, C), 1.4), b.mul(b.remap(sy, 0.0, 0.8, 0.7, 0.0), nw), b.mul(GR, 0.5)))
    kind = {G.PAINT: "paint", G.HAZARD: "paint", G.POLYMER: "polymer", G.STEEL: "steel", G.CYAN: "light", G.AMBER: "light"}[slot]
    zero = 0.0
    if kind == "paint":
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.88 * c for c in PAINT_C)), b.rgb(tuple(1.12 * c for c in PAINT_C)))
        base = b.mix(b.mul(b.remap(nw, 0.35, 0.65), 0.5), base, b.rgb(tuple(0.8 * c for c in PAINT_C)))      # large mottling
        if slot == G.HAZARD:                                                  # 45 deg ochre / black stripes, 85 mm pitch
            sx = b.math('MULTIPLY', pos.outputs[0], -1.0)
            ph = b.math('FRACT', b.math('DIVIDE', b.add(sx, sy), 0.12))
            stripe = b.math('GREATER_THAN', ph, 0.5)
            ochre = b.mix(b.remap(nw, 0.3, 0.7), b.rgb(tuple(0.85 * c for c in OCHRE_C)), b.rgb(tuple(1.08 * c for c in OCHRE_C)))
            hz = b.mix(stripe, b.rgb(BLACK_C), ochre)
            chip = b.clamp(b.add(b.remap(b.add(b.mul(BE, 1.5), b.mul(b.sub(nr, 0.5), 1.2)), 0.26, 0.46),   # G2b: worn more at its edges
                                 b.remap(b.add(b.mul(scratch, 0.8), b.mul(b.sub(nr, 0.5), 0.8)), 0.55, 0.7)))
            base = b.mix(chip, hz, base)                                       # worn band edge: charcoal under-paint
        # edge wear (G2b): no continuous outline. A coarse noise switches whole edge sections on/off, so bare steel
        # shows on exposed corners (strongest edge mask) and some edge sections only, 1-6 mm wide.
        sect = b.remap(b.noise(obj, 7.0, 3.0), 0.42, 0.60)
        wear = b.remap(b.add(b.mul(E, b.add(0.5, b.mul(sect, 0.9))), b.mul(b.sub(nr, 0.5), 0.7), b.mul(scratch, 0.25)),
                       0.58, 0.70)
        # rust (G2b, STYLE_GUIDE "Rust rule"): patchy on exposed edges / corners and the bottom, blotches in some panel
        # corners and round some bolts (RB), run-off streaks (ST); more towards the floor. rv = rust "depth".
        hb = b.remap(sy, 0.0, 1.3, 0.18, 0.0)                                                         # more towards the floor
        bot = b.mul(b.remap(sy, 0.01, 0.16, 0.75, 0.0), b.remap(b.noise(obj, 4.5, 3.0), 0.42, 0.62))   # patchy bottom edge
        er = b.mul(E, b.remap(b.noise(obj, 9.0, 4.0), 0.44, 0.62))                                     # exposed edge sections
        spk = b.mul(b.remap(b.noise(obj, 28.0, 6.0, 0.6), 0.60, 0.70), b.remap(b.noise(obj, 2.2, 2.0), 0.35, 0.55))   # specks
        pat = b.remap(b.noise(obj, 3.2, 5.0, 0.6), 0.54, 0.70)                                         # irregular patches
        rv = b.add(b.mul(RB, 0.95), b.mul(er, 1.7), hb, bot, b.mul(spk, 1.0), b.mul(pat, 0.6),
                   b.mul(b.sub(nr, 0.5), 1.1), b.mul(b.sub(nr2, 0.5), 0.3))
        if slot == G.HAZARD:                                                  # the band is worn and rusty, as in the concept
            rv = b.add(rv, b.mul(b.remap(b.noise(obj, 6.0, 4.0), 0.4, 0.7), 0.3))
        rust = b.clamp(b.add(b.remap(rv, 0.40, 0.52), b.mul(ST, b.remap(nf, 0.2, 0.6, 0.55, 1.0))))
        col = b.mix(b.mul(scratch, 0.8), base, b.rgb(tuple(2.4 * c for c in PAINT_C)))                    # hairlines read lighter
        col = b.mix(wear, col, b.rgb(STEEL_C))
        col = b.mix(BO, col, b.rgb(tuple(0.95 * c for c in STEEL_C)))
        rcol = b.mix(b.remap(rv, 0.62, 0.95), b.rgb(RUST_EDGE), b.rgb(RUST_DARK))                         # dark centres
        rcol = b.mix(b.mul(b.remap(nr2, 0.3, 0.8), 0.35), rcol, b.rgb(tuple(0.85 * c for c in RUST_C)))
        col = b.mix(rust, col, rcol)
        bare = b.mul(b.math('MAXIMUM', wear, BO), b.sub(1.0, rust))
        col = b.mix(b.mul(b.mul(grime, 0.7), b.sub(1.0, b.mul(bare, 0.9))), col, b.rgb(GRIME_C))   # grime spares bare steel
        metal = bare                                                                                    # metallic 1 on bare steel
        rough = b.add(0.58, b.mul(b.sub(nw, 0.5), 0.35), b.mul(scratch, -0.25))
        rough = b.mixf(b.math('MAXIMUM', wear, BO), rough, b.add(0.50, b.mul(b.sub(nf, 0.5), 0.1), b.mul(grime, 0.25)))
        rough = b.mixf(rust, rough, b.add(0.85, b.mul(b.sub(nr2, 0.5), 0.1)))
        rough = b.add(rough, b.mul(grime, 0.12))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.03), b.mul(rust, b.mul(b.sub(nr2, 0.5), 0.04)), b.mul(scratch, -0.015))   # gentle relief: no seam breaks
    elif kind == "polymer":
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.9 * c for c in POLY_C)), b.rgb(tuple(1.1 * c for c in POLY_C)))
        wear = b.remap(b.add(b.mul(E, 1.1), b.mul(b.sub(nr, 0.5), 0.9)), 0.55, 0.8)
        col = b.mix(wear, base, b.rgb(tuple(1.8 * c for c in POLY_C)))
        col = b.mix(b.mul(grime, 0.6), col, b.rgb(GRIME_C))
        metal = b.val(zero)
        rough = b.add(0.64, b.mul(b.sub(nw, 0.5), 0.2), b.mul(wear, 0.1), b.mul(grime, 0.08))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.02))
    elif kind == "steel":
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.95 * c for c in STEEL_C)), b.rgb(tuple(1.04 * c for c in STEEL_C)))
        rust = b.mul(b.remap(b.add(b.mul(RB, 0.5), b.mul(b.sub(nr, 0.5), 1.1)), 0.72, 0.88), 0.7)
        rcol = b.mix(b.remap(nr2, 0.2, 0.8), b.rgb(tuple(0.8 * c for c in RUST_C)), b.rgb(RUST_C))
        col = b.mix(rust, base, rcol)
        g2 = b.mul(grime, 0.45)
        col = b.mix(b.mul(g2, 0.15), col, b.rgb(GRIME_C))                    # G2b: grime mostly in roughness, albedo stays >= 180
        metal = b.sub(1.0, rust)
        rough = b.add(0.48, b.mul(b.sub(nw, 0.5), 0.2), b.mul(scratch, 0.1), b.mul(rust, 0.4), b.mul(g2, 0.45))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.012))
    else:
        cyan = slot == G.CYAN
        col = b.rgb(CYAN_OFF if cyan else AMBER_OFF)
        metal = b.val(zero)
        rough = b.add(0.35, b.mul(b.sub(nw, 0.5), 0.1))
        emis = b.rgb(CYAN_E if cyan else AMBER_E)
        hgt = Hn
    # normal: bevel (soft 1.5 mm edges) + bump (details, fine noise)
    bev = b.n("ShaderNodeBevel", samples=8); bev.inputs["Radius"].default_value = 0.0015
    bump = b.n("ShaderNodeBump"); bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = H_HI - H_LO
    b.link(hgt, bump.inputs["Height"]); b.link(bev.outputs[0], bump.inputs["Normal"])
    b.link(col, bsdf.inputs["Base Color"]); b.link(metal, bsdf.inputs["Metallic"])
    b.link(b.clamp(rough), bsdf.inputs["Roughness"]); b.link(bump.outputs[0], bsdf.inputs["Normal"])
    b.link(emis, bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = 1.0
    sockets = dict(base=col, rough=b.clamp(rough), metal=b.clamp(metal), emis=emis)
    m["_bsdf"] = bsdf.name
    b.link(bsdf.outputs[0], out.inputs["Surface"])
    return m, sockets


def set_channel(m, sockets, ch):
    nt = m.node_tree; out = nt.nodes["Material Output"]; em = nt.nodes["BakeEmit"]
    if ch == "normal":
        nt.links.new(nt.nodes[m["_bsdf"]].outputs[0], out.inputs["Surface"]); return
    s = sockets[ch]
    for l in list(em.inputs["Color"].links): nt.links.remove(l)
    nt.links.new(s, em.inputs["Color"]); em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs["Surface"])


# --------------------------------------------------------------------------- bake stage


def save_png(arr, fn, folder=OUT, mode='RGBA'):
    """arr (n, n, 4) float 0..1 (already in the file's colour encoding) -> 8-bit PNG, alpha straight"""
    n = arr.shape[0]
    img = bpy.data.images.new(fn, n, n, alpha=(mode == 'RGBA'))
    img.colorspace_settings.name = 'Non-Color'; img.alpha_mode = 'STRAIGHT'
    img.pixels.foreach_set(np.clip(arr, 0, 1).astype(np.float32).ravel())
    img.filepath_raw = os.path.join(folder, fn); img.file_format = 'PNG'
    img.save()
    print("SAVED", fn)
    return img


def bake(args):
    os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    objs, lows = open_lows()
    part, mat, P, N = texel_maps(lows)
    np.savez_compressed(os.path.join(WORK, "texels.npz"), part=part, mat=mat, P=P, N=N)
    cover = part > 0
    d1, rustb, bande = details(part, mat, P, N)
    # pre-bakes: edges, cavity, AO (self only)
    # "-- bake reuse [edge]": cavity and AO (and with "edge" the edge mask) from the last run's pre-bakes, when their
    # inputs (geometry, EDGE_DIST) did not change
    res = {}
    prev = os.path.join(WORK, "prebakes.npz")
    old = dict(np.load(prev)) if "reuse" in args and os.path.exists(prev) else {}
    for kind in ("edge", "cavity", "ao"):
        if kind in old and (kind != "edge" or "edge" in args):
            res[kind] = old[kind]; print(f"INFO {kind}: reused"); continue
        pm = prebake_material("cavity" if kind == "ao" else kind); keep = swap_materials(lows, lambda i: pm)
        img = new_image(f"pre_{kind}")
        run_bake(lows, kind, img, "AO" if kind == "ao" else "EMIT", BAKE_SAMPLES["prebake"]); restore(lows, keep)
        res[kind] = pixels(img)[..., 0]
    np.savez_compressed(prev, **res)
    edge = np.clip(blur_masked(res["edge"], cover, 1) * EDGE_GAIN, 0, 1)
    cav = blur_masked(res["cavity"], cover, 1)
    print(f"INFO edge mask p90 / p99 {np.percentile(edge[cover], 90):.2f} / {np.percentile(edge[cover], 99):.2f}")
    np.savez_compressed(os.path.join(WORK, "masks.npz"), edge=edge, cavity=cav, ao=res["ao"], d1=d1, rustb=rustb, bande=bande)
    D1 = new_image("D1", d1); D2 = new_image("D2", np.stack([edge, cav, rustb, bande], 2))
    mats = [surface_material(s, D1, D2, None) for s in range(len(G.MATS))]
    keep = swap_materials(lows, lambda i: mats[i][0])
    maps = {}
    for ch, kind, smp in (("base", "EMIT", "emit"), ("rough", "EMIT", "emit"), ("metal", "EMIT", "emit"),
                          ("emis", "EMIT", "emit"), ("normal", "NORMAL", "normal")):
        for m, socks in mats: set_channel(m, socks, ch)
        img = new_image(f"bake_{ch}"); run_bake(lows, ch, img, kind, BAKE_SAMPLES[smp])
        maps[ch] = pixels(img)
    restore(lows, keep)
    # composite: one 8 px dilation of every map from the texel raster's coverage (the bake's cleared background is
    # not distinguishable from baked texels), pack, encode, save
    m_cov = cover
    print(f"INFO bake coverage {m_cov.sum()} texels, raster {cover.sum()} (differ {int((m_cov != cover).sum())})")
    D = {k: dilate(v, m_cov) for k, v in maps.items()}
    ao = dilate(np.repeat(res["ao"][..., None], 4, 2), m_cov)[..., 0]
    base = np.concatenate([to_srgb(D["base"][..., :3]), np.ones((TEX, TEX, 1))], 2)
    nrm = np.concatenate([D["normal"][..., :3], np.ones((TEX, TEX, 1))], 2)
    mask = np.stack([D["metal"][..., 0], ao, np.zeros((TEX, TEX)), 1 - D["rough"][..., 0]], 2)
    emis = np.concatenate([to_srgb(D["emis"][..., :3]), np.ones((TEX, TEX, 1))], 2)
    for arr, fn in ((base, "T_LAB_HERO_Gate_BaseColor.png"), (nrm, "T_LAB_HERO_Gate_Normal.png"),
                    (mask, "T_LAB_HERO_Gate_Mask.png"), (emis, "T_LAB_HERO_Gate_Emission.png")):
        save_png(arr, fn)
    np.savez_compressed(os.path.join(WORK, "maps.npz"), cover=m_cov, metal=D["metal"][..., 0], rough=D["rough"][..., 0],
                        ao=ao, emis=D["emis"][..., :3], base=D["base"][..., :3])
    print(f"INFO bake total {time.time() - t0:.0f} s")


# --------------------------------------------------------------------------- checks


AO_BLACK, LINE_MAX = 0.05, 2.0


def load_png(fn):
    img = bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = 'Non-Color'
    return pixels(img)


def components(mask):
    left = set(zip(*np.nonzero(mask))); out = []
    while left:
        s = left.pop(); st, comp = [s], [s]
        while st:
            y, x = st.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = (y + dy, x + dx)
                    if q in left: left.remove(q); st.append(q); comp.append(q)
        out.append(np.array(comp))
    return out


def behind_plate(p):
    return (any(abs(p[0] - c) < G.RAIL_PLATE["hw"] + 0.005 for c in G.RAIL_PLATES)
            and G.RAIL_Z0 - 0.002 < p[2] < G.RAIL_PROFILE[4][1] + 0.002)


def behind_strap(p):
    """leaf face between a hanger plate's top and the leaf top, behind the strap (10 mm gap, open only upward)"""
    return (any(abs(p[0] - (G.LEAF_X0 + hc)) < G.STRAP["hw"] + 0.004 for hc in G.HANGERS)
            and G.LEAF_Y0 + G.PLATE["v1"] - 0.002 < p[1] < G.LEAF_Y0 + G.LEAF_H + 0.002 and p[2] < G.LEAF_Z0 + 0.002)


def check(args):
    objs, lows = open_lows()
    tx = np.load(os.path.join(WORK, "texels.npz")); part, matix = tx["part"], tx["mat"]
    cover = part > 0
    base = load_png("T_LAB_HERO_Gate_BaseColor.png"); mask = load_png("T_LAB_HERO_Gate_Mask.png")
    emis = load_png("T_LAB_HERO_Gate_Emission.png"); nrm = load_png("T_LAB_HERO_Gate_Normal.png")
    ok_all = True
    # AO black scan
    ao = mask[..., 1]
    for pi, name in enumerate(PARTS, 1):
        dark = (part == pi) & (ao < AO_BLACK)
        pcs = components(dark) if dark.sum() < 200000 else []
        patches = [c for c in pcs if len(c) / (np.ptp(c, 0).max() + 1) > LINE_MAX]
        # accepted: the groove behind the rail's bracket plates (plate backs over the groove, the groove under them):
        # enclosed on four sides, seen only by looking along the groove
        acc = [c for c in patches if (pi == 2 and behind_plate(tx["P"][c[:, 0], c[:, 1]].mean(0)))
               or (pi == 1 and behind_strap(tx["P"][c[:, 0], c[:, 1]].mean(0)))]
        patches = [c for c in patches if not any(c is a for a in acc)]
        ok = not patches
        ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} AO black {name}: {int(dark.sum())} texels AO < {AO_BLACK}, {len(pcs) - len(patches) - len(acc)} "
              f"contact lines, {len(acc)} accepted crevices ({sum(len(c) for c in acc)} texels), "
              f"{len(patches)} patches" + (f" (largest {max(len(c) for c in patches)} texels at "
              f"{tuple(np.round(tx['P'][max(patches, key=len)[:, 0], max(patches, key=len)[:, 1]].mean(0), 3))})" if patches else ""))
        print(f"INFO AO {name}: min {ao[part == pi].min():.3f}, mean {ao[part == pi].mean():.3f}")
    # PBR values (8-bit sRGB albedo, linear metallic)
    srgb = base[..., :3] * 255; met = mask[..., 0]; em = emis[..., :3].max(2)
    light = (matix == G.CYAN) | (matix == G.AMBER)
    nonmetal = cover & (met < 0.1) & ~light; metal = cover & (met > 0.9)
    lo = (srgb.min(2) < 29.5) & nonmetal; hi = (srgb.max(2) > 240.5) & nonmetal
    mlow = metal & (srgb.mean(2) < 180)                  # ASSET_RULES: metal albedo sRGB >= 180
    trans = cover & (met >= 0.1) & (met <= 0.9)
    f = lambda m, d: 100.0 * m.sum() / max(d.sum(), 1)
    ok = f(lo, nonmetal) < 0.5 and f(hi, nonmetal) < 0.5
    ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} PBR non-metal albedo sRGB 30-240: {f(lo, nonmetal):.2f} % below, {f(hi, nonmetal):.2f} % above "
          f"(of {nonmetal.sum()} texels)")
    ok = f(mlow, metal) < 1.0; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} PBR metal albedo >= 180 sRGB: {f(mlow, metal):.2f} % below (of {metal.sum()} metal texels)")
    print(f"INFO metallic: {f(metal, cover):.1f} % metal, {f(nonmetal | (cover & light & (met < 0.1)), cover):.1f} % non-metal, "
          f"{f(trans, cover):.2f} % transitions 0.1-0.9 (worn edges, rust, grime)")
    for s, nm in enumerate(n for n, _ in G.MATS):
        sel = cover & (matix == s)
        if sel.any():
            print(f"INFO {nm}: albedo sRGB median {tuple(np.median(srgb[sel], 0).round().astype(int))}, smoothness median "
                  f"{np.median(mask[..., 3][sel]):.2f}, metallic mean {met[sel].mean():.2f}")
    # normal seams across UV islands on the leaf faces (flat faces split over two islands)
    ok_all &= normal_seams(lows["Leaf_01"], nrm)
    print("PASS all texture checks" if ok_all else "FAIL some texture checks")


SEAM_MIN = 0.040


def normal_seams(o, nrm, max_deg=6.0):
    """for every seam edge between two coplanar leaf faces: sample the baked normal 2.5 px inside each side, turn both
    into object space with the face's tangent frame (MikkTSpace on the triangulated low), compare"""
    me = o.data; me.calc_tangents(); uv = me.uv_layers.active.data
    edge_faces = {}
    for p in me.polygons:
        for k, li in zip(p.edge_keys, p.loop_indices): edge_faces.setdefault(k, []).append(p)
    def uvkey(p, k):
        d = {me.loops[li].vertex_index: np.array(uv[li].uv) for li in p.loop_indices}
        return d[k[0]], d[k[1]]
    def sample(u):
        x = int(np.clip(u[0] * TEX, 0, TEX - 1)); y = int(np.clip(u[1] * TEX, 0, TEX - 1)); return nrm[y, x, :3] * 2 - 1
    def frame(p):
        li = p.loop_indices[0]; L = me.loops[li]
        T = np.array(L.tangent); Nn = np.array(L.normal); B = L.bitangent_sign * np.cross(Nn, T); return T, B, Nn
    worst, bad, n, short = 0.0, 0, 0, 0; where = []
    for k, fs in edge_faces.items():
        if len(fs) != 2: continue
        a, b = fs
        if a.normal.angle(b.normal, 0) > math.radians(0.5): continue
        ua, ub = uvkey(a, k), uvkey(b, k)
        if np.allclose(ua[0], ub[0], atol=1e-6) and np.allclose(ua[1], ub[1], atol=1e-6): continue   # not a seam
        if (me.vertices[k[0]].co - me.vertices[k[1]].co).length < SEAM_MIN:
            short += 1; continue                       # across a 20 mm panel gap: inside the walls' bevel zone
        ca = np.mean([uv[li].uv for li in a.loop_indices], 0); cb = np.mean([uv[li].uv for li in b.loop_indices], 0)
        Ta, Tb = frame(a), frame(b)
        for t in (0.2, 0.4, 0.6, 0.8):
            pa = ua[0] + (ua[1] - ua[0]) * t; pb = ub[0] + (ub[1] - ub[0]) * t
            pa = pa + (ca - pa) / np.linalg.norm(ca - pa) * 2.5 / TEX; pb = pb + (cb - pb) / np.linalg.norm(cb - pb) * 2.5 / TEX
            na, nb = sample(pa), sample(pb)
            wa = na[0] * Ta[0] + na[1] * Ta[1] + na[2] * Ta[2]; wb = nb[0] * Tb[0] + nb[1] * Tb[1] + nb[2] * Tb[2]
            ang = math.degrees(math.acos(np.clip(wa @ wb / (np.linalg.norm(wa) * np.linalg.norm(wb)), -1, 1)))
            worst = max(worst, ang); bad += ang > max_deg; n += 1
            if ang > max_deg:
                q = o.matrix_world @ (me.vertices[k[0]].co.lerp(me.vertices[k[1]].co, t))
                where.append((round(ang, 1), tuple(np.round(spec(q), 3))))
    ok = bad <= max(2, n // 200)
    for a, q in sorted(where, reverse=True)[:8]:
        print(f"     seam sample {a} deg at Unity {q}")
    print(f"{'PASS' if ok else 'FAIL'} normal seams on the leaf faces: {n} samples on coplanar seams, {bad} over {max_deg} deg "
          f"(worst {worst:.1f} deg; bolts / grooves crossing a seam count too); {short} seam edges < {SEAM_MIN * 1e3:.0f} mm skipped")
    return ok


# --------------------------------------------------------------------------- renders with the baked maps


EMIT_RENDER = 1.0                     # emission strength in the review renders: the blue stays visible (2.2 read pale)


def baked_material():
    m = bpy.data.materials.new("M_Gate_Baked"); m.use_nodes = True; nt = m.node_tree; b = NB(nt)
    bsdf = nt.nodes["Principled BSDF"]
    def tex(fn, cs):
        img = bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = cs
        img.alpha_mode = 'CHANNEL_PACKED'
        return b.n("ShaderNodeTexImage", image=img)
    bc = tex("T_LAB_HERO_Gate_BaseColor.png", 'sRGB'); nm = tex("T_LAB_HERO_Gate_Normal.png", 'Non-Color')
    mk = tex("T_LAB_HERO_Gate_Mask.png", 'Non-Color'); em = tex("T_LAB_HERO_Gate_Emission.png", 'sRGB')
    sep = b.n("ShaderNodeSeparateColor"); b.link(mk.outputs["Color"], sep.inputs[0])
    nmap = b.n("ShaderNodeNormalMap", space='TANGENT'); b.link(nm.outputs["Color"], nmap.inputs["Color"])
    b.link(bc.outputs["Color"], bsdf.inputs["Base Color"]); b.link(sep.outputs[0], bsdf.inputs["Metallic"])
    b.link(b.sub(1.0, mk.outputs["Alpha"]), bsdf.inputs["Roughness"]); b.link(nmap.outputs[0], bsdf.inputs["Normal"])
    b.link(em.outputs["Color"], bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = EMIT_RENDER
    return m


def renders(args):
    """review renders with the baked maps. args: view names to limit the set; "fast" = 24 samples, half size
    (look iterations); views: room (front), corridor, 34, hanger, button, detail, open, dim, concept"""
    import gate_check as GC
    objs, lows = open_lows()
    m = baked_material()
    for o in lows.values():
        for i in range(len(o.data.materials)): o.data.materials[i] = m
    sc = bpy.context.scene
    fast = "fast" in args
    only = set(a for a in args if a != "fast")
    GC.scene_setup(samples=24 if fast else 96)
    if fast: sc.render.resolution_percentage = 50
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.006, 0.008, 0.011, 1)
    room = GC.add_room(); floor = bpy.data.objects["Floor"]
    lights = [GC.add_light("Key", (-0.9, 3.7, 4.6), (-1.6, 1.2, 7.9), 95, 1.2, (0.85, 0.92, 1.0)),
              GC.add_light("Fill", (1.6, 1.6, 5.2), (-1.4, 1.2, 7.9), 18, 2.0, (0.7, 0.85, 1.0)),
              GC.add_light("Rim", (-4.0, 3.0, 7.2), (-1.6, 1.6, 7.9), 12, 1.0, (1.0, 0.85, 0.7)),
              GC.add_light("CorrKey", (-1.0, 2.8, 11.5), (-1.0, 1.2, 8.0), 35, 1.2, (0.85, 0.92, 1.0))]
    leaf = lows["Leaf_01"]; base_loc = leaf.location.copy()
    views = {
        "room": dict(loc=(-1.8, 1.42, 2.0), look=(-1.8, 1.42, 7.9), ortho=4.3),
        "corridor": dict(loc=(-1.0, 1.36, 12.6), look=(-1.05, 1.25, 8.0), lens=28),
        "34": dict(loc=(0.9, 1.8, 5.1), look=(-1.3, 1.35, 7.9), lens=32),
        "hanger": dict(loc=(-0.15, 2.05, 6.85), look=(-0.5, 2.55, 7.93), lens=40),
        "button": dict(loc=(-1.3, 1.40, 8.95), look=(-1.94, 1.21, 8.70), lens=45),
        "detail": dict(loc=(-0.55, 1.0, 6.9), look=(-0.25, 0.35, 7.88), lens=40),
    }
    for k, v in views.items():
        if only and k not in only: continue
        GC.camera(v["loc"], v["look"], v.get("lens", 40), v.get("ortho")); GC.shot(f"{RENDER_TAG}_{k}.png")
    if not only or "open" in only:
        leaf.location = base_loc + Vector((G.LEAF_TRAVEL, 0, 0))                # spec -X = Blender +X
        GC.camera((0.3, 1.7, 4.6), (-1.9, 1.35, 7.9), 30); GC.shot(f"{RENDER_TAG}_open.png"); leaf.location = base_loc
    if not only or "dim" in only:                                           # dim facility light: lamps at ~40 %
        keep = [l.data.energy for l in lights]
        for l in lights: l.data.energy *= 0.4
        GC.camera((-0.2, 1.5, 3.4), (-1.6, 1.35, 7.9), 30); GC.shot(f"{RENDER_TAG}_dim_facility.png")
        for l, e in zip(lights, keep): l.data.energy = e
    if not only or "concept" in only:                                       # lit like the concept: neutral, even
        for o in (room, floor, *lights, lows["ButtonPanel_01"], lows["Button_01"]): o.hide_render = True
        bg = lin((67, 67, 67))                                              # concept background, sRGB 67
        wt = sc.world.node_tree; wb = wt.nodes["Background"]
        wb.inputs[0].default_value = (*bg, 1); wb.inputs[1].default_value = 0.5           # ambient light
        cam_bg = wt.nodes.new("ShaderNodeBackground"); cam_bg.inputs[0].default_value = (*bg, 1)
        lp = wt.nodes.new("ShaderNodeLightPath"); mx = wt.nodes.new("ShaderNodeMixShader")
        wt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0]); wt.links.new(wb.outputs[0], mx.inputs[1])
        wt.links.new(cam_bg.outputs[0], mx.inputs[2])
        wt.links.new(mx.outputs[0], wt.nodes["World Output"].inputs["Surface"])         # camera sees the flat grey
        GC.add_light("CKey", (-1.7, 5.2, 5.4), (-1.7, 1.6, 7.9), 140, 3.0)   # soft neutral key from above: top-lit gradient
        GC.add_light("CFill", (-1.7, 1.4, 3.0), (-1.7, 1.3, 7.9), 25, 5.0)
        sc.render.film_transparent = False
        GC.camera((-1.8, 1.42, 2.0), (-1.8, 1.42, 7.9), 40, 4.3); GC.shot(f"{RENDER_TAG}_concept_light.png")
        compare()
    clip_report()
    if not only or "maps" in only: flat_maps()


def clip_report():
    """emission must not clip to white: light-strip pixels in the room / corridor renders"""
    for k in ("room", "corridor", "button", "dim_facility", "concept_light"):
        p = os.path.join(RENDERS, f"{RENDER_TAG}_{k}.png")
        if not os.path.exists(p): continue
        img = bpy.data.images.load(p); a = pixels_any(img)[..., :3]
        bright = a.max(2) > 0.85
        white = bright & (a.min(2) > 0.85)
        print(f"{'PASS' if white.sum() == 0 else 'FAIL'} no white clipping {k}: {int(bright.sum())} bright pixels, "
              f"{int(white.sum())} white (all channels > 0.85)")


def pixels_any(img):
    w, h = img.size; a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a); return a.reshape(h, w, 4)


def compare():
    r = bpy.data.images.load(os.path.join(RENDERS, f"{RENDER_TAG}_concept_light.png")); c = bpy.data.images.load(CONCEPT)
    H = 1000
    c.scale(int(c.size[0] * H / c.size[1]), H); r.scale(int(r.size[0] * H / r.size[1]), H)
    A, B = pixels_any(r), pixels_any(c)
    gap = np.full((H, 24, 4), 1.0, np.float32); gap[..., :3] = 0.12
    out = np.concatenate([A, gap, B], 1)
    img = bpy.data.images.new("cmp", out.shape[1], H, alpha=False)
    img.pixels.foreach_set(out.astype(np.float32).ravel())
    img.filepath_raw = os.path.join(RENDERS, f"{RENDER_TAG}_room_vs_concept.png"); img.file_format = 'PNG'; img.save()
    print(f"RENDER {RENDER_TAG}_room_vs_concept.png")


def flat_maps():
    for fn, tag, chans in (("T_LAB_HERO_Gate_BaseColor.png", "basecolor", None), ("T_LAB_HERO_Gate_Normal.png", "normal", None),
                           ("T_LAB_HERO_Gate_Emission.png", "emission", None), ("T_LAB_HERO_Gate_Mask.png", "mask_metallic", 0),
                           ("T_LAB_HERO_Gate_Mask.png", "mask_ao", 1), ("T_LAB_HERO_Gate_Mask.png", "mask_smoothness", 3)):
        a = load_png(fn)
        if chans is not None: a = np.repeat(a[..., chans:chans + 1], 4, 2); a[..., 3] = 1
        a[..., 3] = 1
        h = TEX // 2; d = a.reshape(h, 2, h, 2, 4).mean((1, 3))
        save_png(d, f"{RENDER_TAG}_map_{tag}.png", RENDERS, 'RGB')


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"bake": bake, "check": check, "renders": renders}[argv[0]](argv[1:])
