"""
LeverStand (Hero 02b) textures, hero workflow v3 (ASSET_RULES): procedural Blender materials baked in Cycles onto the
export-identical triangulated low (env_kit_generator.triangulated_export_copy), one 1024 set for the three parts.
Same pipeline and bake helpers as the Gate (gate_tex.py, the reference implementation); LeverStand-specific: detail
maps (bolts, grooves, grip ribs, rust blotches and streaks, band edge), materials and checks.

  blender -b -P Tools/Blender/heroes/leverstand_tex.py -- bake [reuse]   texel maps, details, pre-bakes, final bakes
  blender -b -P Tools/Blender/heroes/leverstand_tex.py -- check          AO black scan, PBR values, rust coverage,
                                                                         normal seams on the pedestal's flat faces
  blender -b -P Tools/Blender/heroes/leverstand_tex.py -- renders [views] [fast]   review renders with the baked maps
  LEVERSTAND_TEX=512 (environment) bakes / checks at 512 in their own folders, for cheap look iterations

Outputs: Assets/Environment/Heroes/LeverStand/Textures/T_LAB_HERO_LeverStand_{BaseColor,Normal,Mask,Emission}.png
(BaseColor sRGB, Normal OpenGL, Mask linear R metallic G AO B 0 A smoothness, Emission sRGB colour). The bake runs with
the lever UPRIGHT (its modelled pose). Never saves the .blend.
Palette (STYLE_GUIDE + this hero's design step, BUILD.md): paint = cool steel grey sRGB 86 88 94 (sampled from the
concept: lit panels 87 84 90, neutral; kept slightly cool, B > R, per the style guide's dark painted metal), polymer
35 37 39, machined steel 188 190 192, ochre 159 120 58 (grip, hazard stripes), hazard black 35 37 39, rust 120 62 34,
cyan emission 70 170 255, amber 240 150 60.
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
import leverstand as L                                   # noqa: E402
import gate_tex as GT                                    # noqa: E402  bake helpers (NB, run_bake, prebakes, dilate ...)
import env_kit_generator as K                            # noqa: E402

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TEX = int(os.environ.get("LEVERSTAND_TEX", str(L.UV_TEX)))
_SFX = "" if TEX == L.UV_TEX else f"_{TEX}"
WORK = os.path.join(PROJ, "Temp", "claude", "leverstand", "tex" + _SFX)
OUT = os.path.join(PROJ, "Assets", "Environment", "Heroes", "LeverStand", "Textures") if not _SFX else WORK
MEDIA = os.path.join(PROJ, "Documentation", "Media", "leverstand")
PARTS = ["Body_01", "Lever_01", "Lamp_01"]
FN = {k: f"T_LAB_HERO_LeverStand_{k}.png" for k in ("BaseColor", "Normal", "Mask", "Emission")}
DILATE = 8
H_LO, H_HI = -0.002, 0.005
BAKE_SAMPLES = dict(prebake=64, emit=4, normal=16)
EDGE_GAIN = 2.2
RNG = np.random.default_rng(41)
lin = GT.lin

PAINT_C, POLY_C, STEEL_C = lin((86, 88, 94)), lin((35, 37, 39)), lin((188, 190, 192))
OCHRE_C, BLACK_C, RUST_C, GRIME_C = lin((159, 120, 58)), lin((35, 37, 39)), lin((120, 62, 34)), lin((44, 41, 37))
CYAN_E, AMBER_E = lin((70, 170, 255)), lin((240, 150, 60))
CYAN_OFF, AMBER_OFF = lin((30, 45, 55)), lin((60, 46, 32))
RUST_DARK, RUST_EDGE = lin((66, 44, 34)), lin((112, 64, 38))


def spec(v):
    return np.array((-v[0], v[2], -v[1]))


# --------------------------------------------------------------------------- scene, lows


def open_lows(path=None):
    bpy.ops.wm.open_mainfile(filepath=path or L.SAVE)
    objs = {n: bpy.data.objects[f"{L.HERO}_{n}"] for n in PARTS}
    L.set_lever(objs["Lever_01"], 0.0)                                   # bake in the modelled (upright) pose
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
    """per texel: part (1..3, 0 empty), material slot, stand-local position (lever upright), face normal"""
    part = np.zeros((TEX, TEX), np.int8); mat = np.full((TEX, TEX), -1, np.int8)
    P = np.zeros((TEX, TEX, 3), np.float32); N = np.zeros((TEX, TEX, 3), np.float32)
    for pi, (name, o) in enumerate(lows.items(), 1):
        me = o.data; W = o.matrix_world; uv = me.uv_layers.active.data; me.calc_loop_triangles()
        V = np.array([spec(W @ v.co) for v in me.vertices]); R = W.to_3x3()
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
    """(part, centre, normal, hex apothem, washer radius) in stand-local space (lever upright)"""
    out = []
    F = L.FACES
    nrm = {"front": (0, 0, 1), "back": (0, 0, -1), "px": (1, 0, 0), "nx": (-1, 0, 0)}
    for face in F:
        if face == "front":
            pts = [(u, v) for u in (-0.066, 0.066) for v in (0.765, 0.122)]
        else:
            pts = [(u, v) for u in (-0.072, 0.072) for v in (0.772, 0.113)]
        out += [(1, F[face](u, v, L.PANEL_D), nrm[face], 0.0062, 0.0088) for u, v in pts]
    out += [(1, (x, L.PH, z), (0, 1, 0), 0.0055, 0.008) for x in (-0.118, 0.118) for z in (-0.118, 0.118)]   # cap top
    out += [(1, (x, 0.972, L.HZ), (0, 0, 1), 0.0045, 0.0065) for x in (-0.078, 0.078)]                    # housing front
    for s in (1, -1):
        out += [(1, (s * L.HX, 0.972, z), (s, 0, 0), 0.0045, 0.0065) for z in (0.050, -0.055)]           # housing sides
    return out


def seg_dist(pts, poly):
    return GT.seg_dist(pts, poly)


def wobble(th, rng, amp=0.35):
    return GT.wobble(th, rng, amp)


def outer_shell(P, tol=0.0006):
    """texels on the pedestal's outer skin (side planes, corner chamfers, cap, plinth): not in the recessed fields"""
    ax, az = np.abs(P[..., 0]), np.abs(P[..., 2])
    h = L.PW / 2
    return (np.maximum(ax, az) > h - tol) | (ax + az > 2 * h - L.CORNER - tol * 1.5)


def details(part, mat, P, N):
    H = np.zeros((TEX, TEX), np.float32); BOLT = np.zeros_like(H); STREAK = np.zeros_like(H); GROOVE = np.zeros_like(H)
    RUSTB = np.zeros_like(H); BANDE = np.zeros_like(H); RIB = np.zeros_like(H); LOW = np.zeros_like(H)
    bl = bolts(); streak_starts = []
    for k, (pi, c, n, a, w) in enumerate(bl):
        c = np.array(c, float); n = np.array(n, float)
        m = (part == pi) & (np.abs((P - c) @ n) < 0.003) & ((N @ n) > 0.95)
        ys, xs = np.nonzero(m & (np.linalg.norm(P - c, axis=2) < w + 0.02))
        if not len(ys): continue
        up = np.array((0.0, 1.0, 0.0)) if abs(n[1]) < 0.5 else np.array((0.0, 0.0, 1.0))
        up = up - n * (up @ n); up /= np.linalg.norm(up); rt = np.cross(up, n)
        d = P[ys, xs] - c; x, y = d @ rt, d @ up
        th = RNG.uniform(0, math.pi / 3); xr, yr = x * math.cos(th) - y * math.sin(th), x * math.sin(th) + y * math.cos(th)
        r = np.hypot(x, y); dh = np.maximum(np.abs(yr), 0.866 * np.abs(xr) + 0.5 * np.abs(yr))
        washer = np.clip((w - r) / 0.0006, 0, 1); head = np.clip((a - dh) / 0.0010, 0, 1)
        H[ys, xs] = np.maximum(H[ys, xs], 0.0009 * washer + 0.0030 * head)
        BOLT[ys, xs] = np.maximum(BOLT[ys, xs], washer)
        ring = RNG.choice((0.0, 0.5, 0.8, 1.0), p=(0.35, 0.2, 0.25, 0.2))
        reach = RNG.uniform(0.008, 0.020); off = RNG.normal(0, 0.25, 2) * w
        x2, y2 = x - off[0], y - off[1]; r2 = np.hypot(x2, y2) * wobble(np.arctan2(y2, x2), RNG, 0.6)
        RUSTB[ys, xs] = np.maximum(RUSTB[ys, xs], ring * np.clip(1 - np.maximum(r2 - w, 0) / reach, 0, 1) * (r > 0.8 * w))
        if abs(n[1]) < 0.3 and ring > 0.5 and RNG.random() < 0.65: streak_starts.append((pi, c - up * w * 0.8, n, up, w))
    body = part == 1
    # rust blotches in plate corners (front I-plate, side and back plates) and at the plinth corners
    for face, fn in L.FACES.items():
        n = np.array({"front": (0, 0, 1), "back": (0, 0, -1), "px": (1, 0, 0), "nx": (-1, 0, 0)}[face], float)
        up = np.array((0.0, 1.0, 0.0)); rt = np.cross(up, n)
        sel = body & ((N @ n) > 0.99)
        corners = [(u, v) for p in L.face_plates(face) for (u, v) in L.offset(p, L.PANEL_SLOPE + 0.01)]
        for u, v in corners:
            if RNG.random() > 0.25: continue
            c = np.array(fn(u, v, L.PANEL_D)); R = RNG.uniform(0.014, 0.032) * (1.3 if v < 0.3 else 1.0)
            ys, xs = np.nonzero(sel & (np.linalg.norm(P - c, axis=2) < 2.2 * R))
            if not len(ys): continue
            d = P[ys, xs] - c; x, y = d @ rt, d @ up
            r = np.hypot(x, y) * wobble(np.arctan2(y, x), RNG, 0.9)
            RUSTB[ys, xs] = np.maximum(RUSTB[ys, xs], np.clip(1 - r / R, 0, 1) ** 0.7)
            if RNG.random() < 0.5: streak_starts.append((1, c - up * R * 0.4, n, up, 0.005))
    for sx in (-1, 1):                                                    # the four plinth corners (all faces near)
        for sz in (-1, 1):
            c2 = np.array((sx * (L.PW / 2 - 0.01), sz * (L.PW / 2 - 0.01))); R = RNG.uniform(0.045, 0.07)
            ys, xs = np.nonzero(body & (P[..., 1] < 0.25) & (np.hypot(P[..., 0] - c2[0], P[..., 2] - c2[1]) < 0.06))
            y = P[ys, xs, 1]; th = np.arctan2(P[ys, xs, 2] - c2[1], P[ys, xs, 0] - c2[0])
            r = (y + 0.02) * wobble(th * 3 + y * 20, RNG, 0.8)
            RUSTB[ys, xs] = np.maximum(RUSTB[ys, xs], np.clip(1 - r / R, 0, 1) ** 0.7)
    # grooves: plinth / body and ledge / body joints on the outer skin, the slot frame on the housing top
    sh = body & outer_shell(P) & (mat == L.PAINT) & (np.abs(N[..., 1]) < 0.3)
    for yg in (0.065, 0.825):
        ys, xs = np.nonzero(sh & (np.abs(P[..., 1] - yg) < 0.004))
        d = np.abs(P[ys, xs, 1] - yg)
        H[ys, xs] -= 0.0007 * np.clip(1 - (d / 0.0016) ** 2, 0, 1)
        GROOVE[ys, xs] = np.maximum(GROOVE[ys, xs], np.clip(1 - d / 0.003, 0, 1))
        if yg < 0.1: continue
    top = body & (np.abs(P[..., 1] - L.HY1) < 0.0005) & (N[..., 1] > 0.99)
    ys, xs = np.nonzero(top)
    fr = [(L.SLOT["x0"] - 0.007, L.SLOT["z0"] - 0.007), (L.SLOT["x1"] + 0.007, L.SLOT["z0"] - 0.007),
          (L.SLOT["x1"] + 0.007, L.SLOT["z1"] + 0.007), (L.SLOT["x0"] - 0.007, L.SLOT["z1"] + 0.007)]
    d = seg_dist(np.column_stack((P[ys, xs, 0], P[ys, xs, 2])), fr)
    H[ys, xs] -= 0.0010 * np.clip(1 - (d / 0.0014) ** 2, 0, 1)
    inside = (P[ys, xs, 0] > fr[0][0]) & (P[ys, xs, 0] < fr[1][0]) & (P[ys, xs, 2] > fr[0][1]) & (P[ys, xs, 2] < fr[2][1])
    H[ys[inside], xs[inside]] += 0.0006                                    # slot lip: a raised frame round the opening
    GROOVE[ys, xs] = np.maximum(GROOVE[ys, xs], np.clip(1 - d / 0.003, 0, 1))
    # grip ribs (16 shallow grooves along the grip) and the collar line; the shaft gets nothing
    lv = part == 2
    hx, hy, hz = L.HINGE
    g = lv & (mat == L.OCHRE)
    ys, xs = np.nonzero(g)
    yy = P[ys, xs, 1] - hy; th = np.arctan2(P[ys, xs, 2] - hz, P[ys, xs, 0] - hx)
    rr = np.hypot(P[ys, xs, 2] - hz, P[ys, xs, 0] - hx)
    on_side = (rr > L.GRIP_R - 0.0015) & (yy > L.SHAFT_L + 0.020) & (yy < L.SHAFT_L + L.GRIP_L - L.GRIP_DOME - 0.004)
    ph = (th / (2 * math.pi) * 16 + 0.5) % 1.0
    rib = np.clip(1 - np.abs(ph - 0.5) / 0.14, 0, 1) * on_side
    H[ys, xs] -= 0.0008 * rib
    RIB[ys, xs] = rib
    col = np.abs(yy - (L.SHAFT_L + 0.012)) < 0.0018
    H[ys, xs] -= 0.0009 * col * np.clip(1 - np.abs(yy - (L.SHAFT_L + 0.012)) / 0.0018, 0, 1)
    for pi, s, n, up, w in streak_starts:
        Ls = RNG.uniform(0.06, 0.24); wd = RNG.uniform(0.0025, 0.006)
        m = (part == pi) & (np.abs((P - s) @ n) < 0.003) & ((N @ n) > 0.95)
        rt = np.cross(up, n)
        d = P - s; x, y = d @ rt, -(d @ up)
        sel = m & (y > 0) & (y < Ls) & (np.abs(x) < 3 * wd)
        ys, xs = np.nonzero(sel)
        t = y[ys, xs] / Ls; ww = wd * (1 + 1.5 * t)
        val = np.clip(1 - np.abs(x[ys, xs]) / ww, 0, 1) * (1 - t) ** 1.5
        STREAK[ys, xs] = np.maximum(STREAK[ys, xs], val)
    # hazard band paint edge (distance to the band's top / bottom edges), low-density faces (no detail)
    bt = body & (mat == L.HAZARD)
    ys, xs = np.nonzero(bt)
    dd = np.minimum(np.abs(P[ys, xs, 1] - L.BAND_Y0), np.abs(P[ys, xs, 1] - L.BAND_Y1))
    BANDE[ys, xs] = np.clip(1 - dd / 0.008, 0, 1)
    Hn = (np.clip(H, H_LO, H_HI) - H_LO) / (H_HI - H_LO)
    print(f"INFO details: {len(bl)} bolts, {len(streak_starts)} rust streaks, grip rib texels {int((RIB > 0.5).sum())}")
    return np.stack([Hn, BOLT, STREAK, GROOVE], 2), RUSTB, BANDE, np.stack([RIB, LOW], 2)


# --------------------------------------------------------------------------- procedural materials


def surface_material(slot, d1, d2, d3):
    name = L.MATS[slot][0] + "_Tex"
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
    b = GT.NB(nt)
    out = nt.nodes["Material Output"]
    bsdf = b.n("ShaderNodeBsdfPrincipled")
    em = b.n("ShaderNodeEmission"); em.name = "BakeEmit"
    GT.add_target(nt)
    tc = b.n("ShaderNodeTexCoord"); obj = tc.outputs["Object"]
    geo = b.n("ShaderNodeNewGeometry"); pos = b.n("ShaderNodeSeparateXYZ"); b.link(geo.outputs["Position"], pos.inputs[0])
    nrm = b.n("ShaderNodeSeparateXYZ"); b.link(geo.outputs["True Normal"], nrm.inputs[0])
    t1 = b.n("ShaderNodeTexImage", image=d1, interpolation='Linear'); t2 = b.n("ShaderNodeTexImage", image=d2, interpolation='Linear')
    s1 = b.n("ShaderNodeSeparateColor"); s2 = b.n("ShaderNodeSeparateColor")
    b.link(t1.outputs["Color"], s1.inputs[0]); b.link(t2.outputs["Color"], s2.inputs[0])
    Hn, BO, ST = s1.outputs[0], s1.outputs[1], s1.outputs[2]; GR = t1.outputs["Alpha"]
    E, C, RB = s2.outputs[0], s2.outputs[1], s2.outputs[2]; BE = t2.outputs["Alpha"]
    t3 = b.n("ShaderNodeTexImage", image=d3, interpolation='Linear'); s3 = b.n("ShaderNodeSeparateColor")
    b.link(t3.outputs["Color"], s3.inputs[0]); RIB = s3.outputs[0]
    # noise scales are ~1.6 x the Gate's (a smaller object: the same breakup per metre would read as large blotches)
    nf = b.noise(obj, 140.0, 6.0); nw = b.noise(obj, 4.0, 4.0); nr = b.noise(obj, 35.0, 10.0, 0.65)
    nr2 = b.noise(obj, 220.0, 4.0)

    def hairlines(rot_deg, scale, stretch, width, dens, lo, hi, seed):
        mp = b.n("ShaderNodeMapping"); b.link(obj, mp.inputs[0])
        mp.inputs["Scale"].default_value = (1.0, 1.0, stretch); mp.inputs["Rotation"].default_value = (0.0, math.radians(rot_deg), 0.0)
        mp.inputs["Location"].default_value = (seed, 0.37 * seed, 0.0)
        t = b.n("ShaderNodeTexNoise"); b.link(mp.outputs[0], t.inputs["Vector"])
        t.inputs["Scale"].default_value = scale; t.inputs["Detail"].default_value = 1.5; t.inputs["Roughness"].default_value = 0.4
        ln = b.remap(b.math('ABSOLUTE', b.sub(t.outputs["Fac"], 0.5)), 0.0, width, 1.0, 0.0)
        return b.mul(ln, b.remap(b.noise(obj, dens, 2.0), lo, hi))
    scratch = b.math('MAXIMUM', hairlines(0, 2.6, 60.0, 0.0080, 2.0, 0.46, 0.56, 0.0),
                     hairlines(28, 2.2, 60.0, 0.0050, 2.2, 0.50, 0.60, 3.1))
    scratch = b.math('MAXIMUM', scratch, hairlines(-35, 2.0, 60.0, 0.0050, 2.0, 0.53, 0.62, 7.7))
    # vertical drips / streak wear as in the concept's front corners (light vertical wipes on the paint)
    mpv = b.n("ShaderNodeMapping"); b.link(obj, mpv.inputs[0]); mpv.inputs["Scale"].default_value = (14.0, 14.0, 0.6)
    tv = b.n("ShaderNodeTexNoise"); b.link(mpv.outputs[0], tv.inputs["Vector"]); tv.inputs["Scale"].default_value = 3.0
    tv.inputs["Detail"].default_value = 3.0
    wipes = b.remap(tv.outputs["Fac"], 0.56, 0.70)
    sy = pos.outputs[2]                                                       # Unity y (height)
    grime = b.clamp(b.add(b.mul(b.sub(1.0, C), 1.4), b.mul(b.remap(sy, 0.0, 0.5, 0.75, 0.0), nw), b.mul(GR, 0.6)))
    kind = {L.PAINT: "paint", L.HAZARD: "paint", L.POLYMER: "polymer", L.STEEL: "steel", L.CYAN: "light",
            L.AMBER: "light", L.OCHRE: "ochre"}[slot]
    if kind == "paint":
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.88 * c for c in PAINT_C)), b.rgb(tuple(1.12 * c for c in PAINT_C)))
        base = b.mix(b.mul(b.remap(nw, 0.35, 0.65), 0.5), base, b.rgb(tuple(0.78 * c for c in PAINT_C)))
        base = b.mix(b.mul(wipes, 0.35), base, b.rgb(tuple(0.72 * c for c in PAINT_C)))     # darker vertical wipes
        if slot == L.HAZARD:                                                  # 45 deg ochre / black stripes, "\\" per face
            # u = viewer's right on each face, from the object-space normal (Blender: front -y, px -x, nx +x, back +y)
            u = b.add(b.mul(b.math('MULTIPLY', nrm.outputs[1], -1.0), pos.outputs[0]), b.mul(nrm.outputs[0], pos.outputs[1]))
            ph = b.math('FRACT', b.math('DIVIDE', b.add(u, sy), 0.075))
            stripe = b.math('GREATER_THAN', ph, 0.5)
            ochre = b.mix(b.remap(nw, 0.3, 0.7), b.rgb(tuple(0.85 * c for c in OCHRE_C)), b.rgb(tuple(1.08 * c for c in OCHRE_C)))
            hz = b.mix(stripe, b.rgb(BLACK_C), ochre)
            chip = b.clamp(b.add(b.remap(b.add(b.mul(BE, 1.5), b.mul(b.sub(nr, 0.5), 1.2)), 0.26, 0.46),
                                 b.remap(b.add(b.mul(scratch, 0.8), b.mul(b.sub(nr, 0.5), 0.8)), 0.55, 0.7)))
            base = b.mix(chip, hz, base)
        sect = b.remap(b.noise(obj, 20.0, 3.0), 0.48, 0.62)
        wear = b.remap(b.add(b.mul(E, b.add(0.5, b.mul(sect, 0.9))), b.mul(b.sub(nr, 0.5), 0.7), b.mul(scratch, 0.25)),
                       0.63, 0.73)
        # rust (STYLE_GUIDE "Rust rule", concept: heavy at the plinth and on the band, patchy on edges and corners)
        hb = b.remap(sy, 0.0, 0.9, 0.10, 0.0)                                                         # more towards the floor
        bot = b.mul(b.remap(sy, 0.0, 0.08, 0.50, 0.0), b.remap(b.noise(obj, 7.0, 3.0), 0.45, 0.65))   # patchy plinth
        er = b.mul(E, b.remap(b.noise(obj, 14.0, 4.0), 0.44, 0.62))
        spk = b.mul(b.remap(b.noise(obj, 45.0, 6.0, 0.6), 0.60, 0.70), b.remap(b.noise(obj, 3.5, 2.0), 0.35, 0.55))
        pat = b.remap(b.noise(obj, 5.0, 5.0, 0.6), 0.54, 0.70)
        rv = b.add(b.mul(RB, 0.95), b.mul(er, 0.8), hb, bot, b.mul(spk, 1.0), b.mul(pat, 0.6),
                   b.mul(b.sub(nr, 0.5), 1.1), b.mul(b.sub(nr2, 0.5), 0.3))
        if slot == L.HAZARD:
            rv = b.add(rv, b.mul(b.remap(b.noise(obj, 9.0, 4.0), 0.4, 0.7), 0.35))
        near = b.clamp(b.add(b.mul(b.remap(b.sub(1.0, C), 0.10, 0.40), 0.30), b.remap(E, 0.10, 0.40), b.mul(GR, 0.5), b.mul(RB, 2.0),
                             b.remap(sy, 0.0, 0.20, 0.8, 0.0), b.mul(wipes, 0.6)))
        # concept: small scattered spots and vertical run-off on the plates (not only at the seams)
        dots = b.mul(b.remap(b.noise(obj, 90.0, 3.0, 0.5), 0.64, 0.72), b.remap(b.noise(obj, 6.0, 2.0), 0.45, 0.65))
        drip = b.mul(wipes, b.remap(b.noise(obj, 11.0, 3.0), 0.55, 0.70))
        rust = b.clamp(b.add(b.mul(b.remap(rv, 0.40, 0.52), near), b.mul(ST, b.remap(nf, 0.2, 0.6, 0.55, 1.0)),
                             b.mul(dots, 2.2), b.mul(drip, 1.0)))
        col = b.mix(b.mul(scratch, 0.6), base, (1.9, 1.9, 1.9), 'MULTIPLY')
        col = b.mix(wear, col, b.rgb(STEEL_C))
        tip = b.mul(b.mul(b.mul(BO, b.remap(Hn, 0.80, 0.86)), b.remap(nr2, 0.60, 0.72)), b.remap(nr, 0.35, 0.55))
        col = b.mix(tip, col, b.rgb(STEEL_C))
        rcol = b.mix(b.remap(rv, 0.62, 0.95), b.rgb(RUST_EDGE), b.rgb(RUST_DARK))
        rcol = b.mix(b.mul(b.remap(nr2, 0.3, 0.8), 0.35), rcol, b.rgb(tuple(0.85 * c for c in RUST_C)))
        col = b.mix(rust, col, rcol)
        bare = b.mul(b.math('MAXIMUM', wear, tip), b.sub(1.0, rust))
        col = b.mix(b.mul(b.mul(grime, 0.7), b.sub(1.0, b.mul(bare, 0.9))), col, b.rgb(GRIME_C))
        metal = bare
        rough = b.add(0.56, b.mul(b.sub(nw, 0.5), 0.35), b.mul(scratch, -0.25), b.mul(wipes, 0.06))
        rough = b.mixf(b.math('MAXIMUM', wear, tip), rough, b.add(0.58, b.mul(b.sub(nf, 0.5), 0.1), b.mul(grime, 0.25)))
        rough = b.mixf(rust, rough, b.add(0.85, b.mul(b.sub(nr2, 0.5), 0.1)))
        rough = b.add(rough, b.mul(grime, 0.12))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.03), b.mul(rust, b.mul(b.sub(nr2, 0.5), 0.04)), b.mul(scratch, -0.015))
    elif kind == "polymer":
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.9 * c for c in POLY_C)), b.rgb(tuple(1.1 * c for c in POLY_C)))
        wear = b.remap(b.add(b.mul(E, 1.1), b.mul(b.sub(nr, 0.5), 0.9)), 0.55, 0.8)
        col = b.mix(wear, base, b.rgb(tuple(1.8 * c for c in POLY_C)))
        col = b.mix(b.mul(grime, 0.6), col, b.rgb(GRIME_C))
        metal = b.val(0.0)
        rough = b.add(0.64, b.mul(b.sub(nw, 0.5), 0.2), b.mul(wear, 0.1), b.mul(grime, 0.08))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.02))
    elif kind == "steel":
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.95 * c for c in STEEL_C)), b.rgb(tuple(1.04 * c for c in STEEL_C)))
        rust = b.mul(b.remap(b.add(b.mul(b.remap(sy, 1.00, 1.06, 1.0, 0.0), 0.5), b.mul(b.sub(nr, 0.5), 1.1)), 0.72, 0.88), 0.6)
        rcol = b.mix(b.remap(nr2, 0.2, 0.8), b.rgb(tuple(0.8 * c for c in RUST_C)), b.rgb(RUST_C))
        col = b.mix(rust, base, rcol)
        g2 = b.mul(grime, 0.45)
        col = b.mix(b.mul(g2, 0.15), col, b.rgb(GRIME_C))
        metal = b.sub(1.0, rust)
        rough = b.add(0.48, b.mul(b.sub(nw, 0.5), 0.2), b.mul(scratch, 0.1), b.mul(rust, 0.3), b.mul(g2, 0.35))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.012))
    elif kind == "ochre":                                                     # grip: ochre polymer, hand wear, no rust
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.9 * c for c in OCHRE_C)), b.rgb(tuple(1.06 * c for c in OCHRE_C)))
        base = b.mix(b.mul(RIB, 0.35), base, b.rgb(tuple(0.75 * c for c in OCHRE_C)))         # dirt in the rib grooves
        wear = b.remap(b.add(b.mul(E, 1.1), b.mul(b.sub(nr, 0.5), 0.9)), 0.55, 0.8)
        col = b.mix(b.mul(wear, 0.6), base, b.rgb(tuple(1.15 * c for c in OCHRE_C)))         # polished where held
        col = b.mix(b.mul(grime, 0.4), col, b.rgb(GRIME_C))
        metal = b.val(0.0)
        rough = b.add(0.50, b.mul(b.sub(nw, 0.5), 0.15), b.mul(wear, -0.12), b.mul(RIB, 0.10))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.015))
    else:
        cyan = slot == L.CYAN
        col = b.rgb(CYAN_OFF if cyan else AMBER_OFF)
        metal = b.val(0.0)
        rough = b.add(0.35, b.mul(b.sub(nw, 0.5), 0.1))
        emis = b.rgb(CYAN_E if cyan else AMBER_E)
        hgt = Hn
    bev = b.n("ShaderNodeBevel", samples=8); bev.inputs["Radius"].default_value = 0.0012
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


# --------------------------------------------------------------------------- bake stage


def save_png(arr, fn, folder=None, mode='RGBA'):
    return GT.save_png(arr, fn, folder or OUT, mode)


def new_image(name, arr=None):
    return GT.new_image(name, arr, TEX)


def bake(args):
    os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    objs, lows = open_lows()
    part, mat, P, N = texel_maps(lows)
    np.savez_compressed(os.path.join(WORK, "texels.npz"), part=part, mat=mat, P=P, N=N)
    cover = part > 0
    d1, rustb, bande, d3 = details(part, mat, P, N)
    res = {}
    prev = os.path.join(WORK, "prebakes.npz")
    old = dict(np.load(prev)) if "reuse" in args and os.path.exists(prev) else {}
    for kind in ("edge", "cavity", "ao"):
        if kind in old:
            res[kind] = old[kind]; print(f"INFO {kind}: reused"); continue
        pm = GT.prebake_material("cavity" if kind == "ao" else kind); keep = GT.swap_materials(lows, lambda i: pm)
        img = new_image(f"pre_{kind}")
        GT.run_bake(lows, kind, img, "AO" if kind == "ao" else "EMIT", BAKE_SAMPLES["prebake"]); GT.restore(lows, keep)
        res[kind] = GT.pixels(img)[..., 0]
    np.savez_compressed(prev, **res)
    edge = np.clip(GT.blur_masked(res["edge"], cover, 1) * EDGE_GAIN, 0, 1)
    cav = GT.blur_masked(res["cavity"], cover, 1)
    print(f"INFO edge mask p90 / p99 {np.percentile(edge[cover], 90):.2f} / {np.percentile(edge[cover], 99):.2f}")
    np.savez_compressed(os.path.join(WORK, "masks.npz"), edge=edge, cavity=cav, ao=res["ao"], d1=d1, rustb=rustb)
    # detail maps dilated before the bake: bilinear lookups at island borders must not pull in the empty (0) texels,
    # which would bake as false slopes along every UV seam (normal-seam check)
    d2 = np.stack([edge, cav, rustb, bande], 2)
    d1, d2, d3 = (GT.dilate(a, cover, 4) for a in (d1, d2, d3))
    D1 = new_image("D1", d1); D2 = new_image("D2", d2); D3 = new_image("D3", d3)
    mats = [surface_material(s, D1, D2, D3) for s in range(len(L.MATS))]
    keep = GT.swap_materials(lows, lambda i: mats[i][0])
    maps = {}
    for ch, kind, smp in (("base", "EMIT", "emit"), ("rough", "EMIT", "emit"), ("metal", "EMIT", "emit"),
                          ("emis", "EMIT", "emit"), ("normal", "NORMAL", "normal")):
        for m, socks in mats: GT.set_channel(m, socks, ch)
        img = new_image(f"bake_{ch}"); GT.run_bake(lows, ch, img, kind, BAKE_SAMPLES[smp])
        maps[ch] = GT.pixels(img)
    GT.restore(lows, keep)
    D = {k: GT.dilate(v, cover, DILATE) for k, v in maps.items()}
    ao = GT.dilate(np.repeat(res["ao"][..., None], 4, 2), cover, DILATE)[..., 0]
    base = np.concatenate([GT.to_srgb(D["base"][..., :3]), np.ones((TEX, TEX, 1))], 2)
    nrm = np.concatenate([D["normal"][..., :3], np.ones((TEX, TEX, 1))], 2)
    mask = np.stack([D["metal"][..., 0], ao, np.zeros((TEX, TEX)), 1 - D["rough"][..., 0]], 2)
    emis = np.concatenate([GT.to_srgb(D["emis"][..., :3]), np.ones((TEX, TEX, 1))], 2)
    for arr, k in ((base, "BaseColor"), (nrm, "Normal"), (mask, "Mask"), (emis, "Emission")):
        save_png(arr, FN[k])
    np.savez_compressed(os.path.join(WORK, "maps.npz"), cover=cover, metal=D["metal"][..., 0], rough=D["rough"][..., 0],
                        ao=ao, base=D["base"][..., :3])
    print(f"INFO bake total {time.time() - t0:.0f} s")


# --------------------------------------------------------------------------- checks


AO_BLACK, LINE_MAX = 0.05, 2.0


def load_png(fn):
    img = bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = 'Non-Color'
    return GT.pixels(img)


def check(args):
    objs, lows = open_lows()
    tx = np.load(os.path.join(WORK, "texels.npz")); part, matix, P = tx["part"], tx["mat"], tx["P"]
    cover = part > 0
    base = load_png(FN["BaseColor"]); mask = load_png(FN["Mask"]); nrm = load_png(FN["Normal"])
    ok_all = True
    ao = mask[..., 1]
    for pi, name in enumerate(PARTS, 1):
        dark = (part == pi) & (ao < AO_BLACK)
        pcs = GT.components(dark) if dark.sum() < 200000 else []
        patches = [c for c in pcs if len(c) / (np.ptp(c, 0).max() + 1) > LINE_MAX]
        # accepted: the slot pocket's floor and lower walls (a 42 mm wide, 65 mm deep pocket: truly dark)
        acc = [c for c in patches if pi == 1 and P[c[:, 0], c[:, 1]].mean(0)[1] < L.HY1 - 0.01
               and matix[c[0, 0], c[0, 1]] == L.POLYMER]
        patches = [c for c in patches if not any(c is a for a in acc)]
        ok = not patches; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} AO black {name}: {int(dark.sum())} texels AO < {AO_BLACK}, {len(pcs) - len(patches) - len(acc)} "
              f"contact lines, {len(acc)} accepted (slot pocket, {sum(len(c) for c in acc)} texels), {len(patches)} patches"
              + (f" (largest {max(len(c) for c in patches)} texels at {tuple(np.round(P[max(patches, key=len)[:, 0], max(patches, key=len)[:, 1]].mean(0), 3))})" if patches else ""))
    srgb = base[..., :3] * 255; met = mask[..., 0]
    light = (matix == L.CYAN) | (matix == L.AMBER)
    nonmetal = cover & (met < 0.1) & ~light; metal = cover & (met > 0.9)
    lo = (srgb.min(2) < 29.5) & nonmetal; hi = (srgb.max(2) > 240.5) & nonmetal
    mlow = metal & (srgb.mean(2) < 180)
    trans = cover & (met >= 0.1) & (met <= 0.9)
    f = lambda m, d: 100.0 * m.sum() / max(d.sum(), 1)
    ok = f(lo, nonmetal) < 0.5 and f(hi, nonmetal) < 0.5; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} PBR non-metal albedo sRGB 30-240: {f(lo, nonmetal):.2f} % below, {f(hi, nonmetal):.2f} % above "
          f"(of {nonmetal.sum()} texels)")
    ok = f(mlow, metal) < 1.0; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} PBR metal albedo >= 180 sRGB: {f(mlow, metal):.2f} % below (of {metal.sum()} metal texels)")
    print(f"INFO metallic: {f(metal, cover):.1f} % metal, {f(trans, cover):.2f} % transitions 0.1-0.9")
    for s, nm in enumerate(n for n, _ in L.MATS):
        sel = cover & (matix == s)
        if sel.any():
            print(f"INFO {nm}: albedo sRGB median {tuple(np.median(srgb[sel], 0).round().astype(int))}, smoothness median "
                  f"{np.median(mask[..., 3][sel]):.2f}, metallic mean {met[sel].mean():.2f}")
    # rust coverage (STYLE_GUIDE rust rule: 5-15 % of a painted surface, more toward the bottom)
    paint = cover & (part == 1) & (matix == L.PAINT)
    r, g, bch = srgb[..., 0], srgb[..., 1], srgb[..., 2]
    rusty = paint & (met < 0.1) & (r > bch + 14) & (r > g + 6)
    for lab, sel in (("all paint", paint), ("below y 0.3", paint & (P[..., 1] < 0.3)), ("y 0.3-0.8", paint & (P[..., 1] >= 0.3) & (P[..., 1] < 0.8)),
                     ("above y 0.8", paint & (P[..., 1] >= 0.8))):
        print(f"INFO rust {lab}: {f(rusty & sel, sel):.1f} %")
    cov = f(rusty, paint); ok = 5.0 <= cov <= 15.0; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} rust coverage of the pedestal / housing paint {cov:.1f} % (rule 5-15 %)")
    mk = np.load(os.path.join(WORK, "masks.npz"))
    detail = np.maximum(mk["d1"][..., 1], mk["d1"][..., 3]) > 0.05                     # bolt washers, grooves
    near = detail.copy()
    for dy in range(-3, 4):
        for dx in range(-3, 4): near |= np.roll(np.roll(detail, dy, 0), dx, 1)
    near |= (mk["edge"] > 0.30) | (mk["cavity"] < 0.50)                                # at a geometry edge / wall foot (bevel zone)
    ok_all &= normal_seams(lows["Body_01"], nrm, near)
    print("PASS all texture checks" if ok_all else "FAIL some texture checks")


SEAM_MIN = 0.030


def normal_seams(o, nrm, near=None, max_deg=6.0):
    """Gate check (gate_tex.normal_seams) on the body: coplanar faces split over two UV islands"""
    me = o.data; me.calc_tangents(); uv = me.uv_layers.active.data
    edge_faces = {}
    for p in me.polygons:
        for k in p.edge_keys: edge_faces.setdefault(k, []).append(p)
    def uvkey(p, k):
        d = {me.loops[li].vertex_index: np.array(uv[li].uv) for li in p.loop_indices}
        return d[k[0]], d[k[1]]
    def sample(u):
        x = int(np.clip(u[0] * TEX, 0, TEX - 1)); y = int(np.clip(u[1] * TEX, 0, TEX - 1)); return nrm[y, x, :3] * 2 - 1
    def frame(p):
        li = p.loop_indices[0]; Lp = me.loops[li]
        T = np.array(Lp.tangent); Nn = np.array(Lp.normal); B = Lp.bitangent_sign * np.cross(Nn, T); return T, B, Nn
    worst, bad, n, short = 0.0, 0, 0, 0; where = []; skipped = 0
    for k, fs in edge_faces.items():
        if len(fs) != 2: continue
        a, b = fs
        if a.normal.angle(b.normal, 0) > math.radians(0.5): continue
        ua, ub = uvkey(a, k), uvkey(b, k)
        if np.allclose(ua[0], ub[0], atol=1e-6) and np.allclose(ua[1], ub[1], atol=1e-6): continue
        if (me.vertices[k[0]].co - me.vertices[k[1]].co).length < SEAM_MIN:
            short += 1; continue
        ca = np.mean([uv[li].uv for li in a.loop_indices], 0); cb = np.mean([uv[li].uv for li in b.loop_indices], 0)
        Ta, Tb = frame(a), frame(b)
        for t in (0.2, 0.4, 0.6, 0.8):
            pa = ua[0] + (ua[1] - ua[0]) * t; pb = ub[0] + (ub[1] - ub[0]) * t
            pa = pa + (ca - pa) / np.linalg.norm(ca - pa) * 2.5 / TEX; pb = pb + (cb - pb) / np.linalg.norm(cb - pb) * 2.5 / TEX
            if near is not None and any(near[int(np.clip(u_[1] * TEX, 0, TEX - 1)), int(np.clip(u_[0] * TEX, 0, TEX - 1))] for u_ in (pa, pb)):
                skipped += 1; continue
            na, nb = sample(pa), sample(pb)
            wa = na[0] * Ta[0] + na[1] * Ta[1] + na[2] * Ta[2]; wb = nb[0] * Tb[0] + nb[1] * Tb[1] + nb[2] * Tb[2]
            ang = math.degrees(math.acos(np.clip(wa @ wb / (np.linalg.norm(wa) * np.linalg.norm(wb)), -1, 1)))
            worst = max(worst, ang); bad += ang > max_deg; n += 1
            if ang > max_deg:
                q = o.matrix_world @ (me.vertices[k[0]].co.lerp(me.vertices[k[1]].co, t))
                where.append((round(ang, 1), tuple(np.round(spec(q), 3))))
    for a_, q in sorted(where, reverse=True)[:12]:
        print(f"     seam sample {a_} deg at stand-local {q}")
    ok = bad <= max(2, n // 200)
    print(f"{'PASS' if ok else 'FAIL'} normal seams on the body's coplanar faces: {n} samples, {bad} over {max_deg} deg "
          f"(worst {worst:.1f} deg); {skipped} samples within 3 px of a groove, bolt or geometry edge skipped; {short} seam edges < {SEAM_MIN * 1e3:.0f} mm skipped")
    return ok


# --------------------------------------------------------------------------- baked material for renders


EMIT_RENDER = 1.0


def baked_material(lamp_level=1.0):
    m = bpy.data.materials.new(f"M_LeverStand_Baked_{lamp_level}"); m.use_nodes = True; nt = m.node_tree; b = GT.NB(nt)
    bsdf = nt.nodes["Principled BSDF"]
    def tex(fn, cs):
        img = bpy.data.images.get(fn) or bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = cs
        img.alpha_mode = 'CHANNEL_PACKED'
        return b.n("ShaderNodeTexImage", image=img)
    bc = tex(FN["BaseColor"], 'sRGB'); nm = tex(FN["Normal"], 'Non-Color')
    mk = tex(FN["Mask"], 'Non-Color'); em = tex(FN["Emission"], 'sRGB')
    sep = b.n("ShaderNodeSeparateColor"); b.link(mk.outputs["Color"], sep.inputs[0])
    nmap = b.n("ShaderNodeNormalMap", space='TANGENT'); b.link(nm.outputs["Color"], nmap.inputs["Color"])
    b.link(bc.outputs["Color"], bsdf.inputs["Base Color"]); b.link(sep.outputs[0], bsdf.inputs["Metallic"])
    b.link(b.sub(1.0, mk.outputs["Alpha"]), bsdf.inputs["Roughness"]); b.link(nmap.outputs[0], bsdf.inputs["Normal"])
    b.link(em.outputs["Color"], bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = EMIT_RENDER * lamp_level
    return m


def apply_baked(objs, lamp_level=1.0):
    """review renders (leverstand_check): the baked set on every part; the lamp at lamp_level (LeverLamp intensity)"""
    m = baked_material(); ml = baked_material(lamp_level) if lamp_level != 1.0 else m
    for n, o in objs.items():
        o.data.materials.clear(); o.data.materials.append(ml if n == "Lamp_01" else m)
        for p in o.data.polygons: p.material_index = 0


def flat_maps():
    import leverstand_check as C
    for fn, tag, ch in ((FN["BaseColor"], "basecolor", None), (FN["Normal"], "normal", None),
                        (FN["Emission"], "emission", None), (FN["Mask"], "mask_metallic", 0),
                        (FN["Mask"], "mask_ao", 1), (FN["Mask"], "mask_smoothness", 3)):
        a = load_png(fn)
        if ch is not None: a = np.repeat(a[..., ch:ch + 1], 4, 2)
        C.save_jpg(a[..., :3], os.path.join(MEDIA, f"leverstand_h2_map_{tag}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"bake": bake, "check": check, "maps": lambda a: (open_lows(), flat_maps())}[argv[0]](argv[1:])
