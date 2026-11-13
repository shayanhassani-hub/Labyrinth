"""
Cradle v2 (Hero 01) textures, Step C-T1 (owner decision 2026-11-12: textured in Blender like the v3 heroes; the
Substance Painter project stays as it is). Procedural Blender materials baked in Cycles onto the export-identical
triangulated low (<Part>_bakelow in the BAKE file = Cradle_low.fbx, 6g), one 2048 set for the four bake parts
(Arm_L shares Arm_R's UVs mirrored, Pad_L = Pad_R).

  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_tex.py -- bake [reuse]   pre-bakes, details, final bakes
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_tex.py -- check          AO black, PBR, rust, normal seams,
                                                                                          emission
  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2_tex.py -- renders [views] [fast]   review JPGs + map previews
  CRADLE_TEX=512 (environment): bake / check / renders at 512 in their own folders, for cheap look iterations

Pipeline (bake):
 1. high-poly maps from the verified Step 6g bake (cradle_v2_bake_final.py -- bake: Cycles, high -> export-identical
    triangulated low through the cage, 2048 at 2x2 supersampling, AO per part = Painter "only same mesh name"):
    tangent Normal (OpenGL), AO, ID (vertex colour "ID"). Read from D:/AI_Labyrinth/Substance/Cradle/Bake_6g.
 2. texel maps from the lows: part, cradle-local position and face normal per texel; material kind per texel from the
    ID map (painted structure, machined steel, ochre pads, riser, fasteners, column access panel).
 3. mask pre-bakes from the HIGH through the cage (the high carries the real chamfers): convex edges (AO node, inside,
    8 mm, local), cavity (AO node, 50 mm, local), ray-miss mask (missed texels filled from their neighbours).
 4. detail maps (numpy; C-T1b owner review): normal-map hex bolts (plinth side-panel ends, rest-plate corners), rust
    rings round some bolts / modelled fasteners, small irregular rust spots placed only on features (edges, recesses,
    joints, more towards the floor), run-off streaks, joint / under-pad rust weight, the hazard band (45 deg ochre /
    black on the tier-1 top chamfer), the cyan status strip in a recessed polymer frame (tier-2 front wall), height
    factor, the pads' limb-contact scuff band.
 5. final bakes on the low from one procedural material (kinds mixed by the ID masks): BaseColor, Smoothness,
    Metallic, detail Normal (bump only: fine noise, rust relief, scratches); the detail normal is combined with the
    6g high-poly normal (reoriented normal mapping). Margin 0, one 16 px dilation of the composite.
Outputs (outside the repo until the owner's look review, no Unity yet):
  D:/AI_Labyrinth/Blender/Export/Heroes/Cradle/T_LAB_HERO_Cradle_{BaseColor,Normal,Mask,Emission}.png
  (BaseColor sRGB, Normal OpenGL, Mask linear R metallic G AO B 0 A smoothness, Emission sRGB: one cyan status strip, C-T1b)
Review JPGs: Documentation/Media/cradle/<TAG>_*.jpg (C-T1 cradle_ct1_, C-T1b cradle_ct1b_). Never saves a .blend.
Palette (STYLE_GUIDE): paint = dark gunmetal sRGB 80 94 106 (C-T1 pick inside the heroes' gunmetal family: Gate
90 104 115, Terminal 72 86 98), access panel = paint x0.8 linear, ochre 159 120 58 (pads), machined steel 188 190 192
(pins, drum bands, turntable annulus, riser rougher), rust 120 62 34, grime 44 41 37.
"""
import bpy
import math
import os
import sys
import time
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import cradle_v2 as V                                    # noqa: E402
import cradle_v2_bake as B                               # noqa: E402
import cradle_v2_bake_final as BF                        # noqa: E402  objs, split_details, node_mat, run_bake (cage)
import cradle_v2_bake_test as T                          # noqa: E402  target_material, new_image
import gate_tex as GT                                    # noqa: E402  NB, run_bake, dilate, blur, save_png, components

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CZ = V.CZ
TEX = int(os.environ.get("CRADLE_TEX", "2048"))
_SFX = "" if TEX == 2048 else f"_{TEX}"
WORK = os.path.join(PROJ, "Temp", "claude", "cradle", "tex" + _SFX)
OUT = "D:/AI_Labyrinth/Blender/Export/Heroes/Cradle" + _SFX
MEDIA = os.path.join(PROJ, "Documentation", "Media", "cradle")
BAKE6G = "D:/AI_Labyrinth/Substance/Cradle/Bake_6g"
SRC6G = {k: os.path.join(BAKE6G, f"T_Cradle_{k}_blender6g.png") for k in ("Normal", "AO", "ID")}
PARTS = list(B.PARTS)                                    # Base, Arm_R, Pad, Riser (bake set)
FILES = {k: f"T_LAB_HERO_Cradle_{k}.png" for k in ("BaseColor", "Normal", "Mask", "Emission")}
TAG = os.environ.get("CRADLE_TAG", "cradle_ct1b")
DILATE = 16                                              # README / Painter bake: 16 px dilation
H_LO, H_HI = -0.002, 0.005
EDGE_DIST, EDGE_GAIN, CAV_DIST = 0.008, 2.2, 0.05
BAKE_SAMPLES = dict(prebake=32, emit=4, normal=16)
RNG = np.random.default_rng(47)
lin = GT.lin

PAINT_SRGB = (80, 94, 106)
PAINT_C = lin(PAINT_SRGB)
PANEL_C = tuple(0.8 * c for c in PAINT_C)
STEEL_C, OCHRE_C, RUST_C, GRIME_C = lin((188, 190, 192)), lin((159, 120, 58)), lin((120, 62, 34)), lin((44, 41, 37))
RUST_DARK, RUST_EDGE = lin((66, 44, 34)), lin((112, 64, 38))
BLACK_C, POLY_C = lin((35, 37, 39)), lin((28, 30, 32))      # hazard black (Gate), strip frame polymer
CYAN_E, CYAN_OFF = GT.CYAN_E, GT.CYAN_OFF                   # STYLE_GUIDE cyan (70 170 255), off-state albedo

# ID groups (HERO_SPEC §3 / README), kind index
ID_COLS = [((1, 0, 0), "paint"), ((0, 1, 0), "steel"), ((1, 1, 0), "ochre"), ((0, 0, 1), "riser"),
           ((1, 0, 1), "fastener"), ((0, 1, 1), "panel")]
KPAINT, KSTEEL, KOCHRE, KRISER, KFAST, KPANEL = range(6)
KNAMES = [n for _, n in ID_COLS]


def local(P):
    """spec world -> cradle-local (origin floor centre)"""
    return np.asarray(P, float) - np.array((0.0, 0.0, CZ))


# --------------------------------------------------------------------------- scene, texel maps, 6g maps


def open_bake():
    bpy.ops.wm.open_mainfile(filepath=B.BAKE)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
    sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
    for o in bpy.data.objects: o.hide_render = True
    for o in bpy.context.view_layer.objects: o.select_set(False)       # the file keeps a selected AI mesh
    lows = {k: bpy.data.objects[f"{k}_bakelow"] for k in PARTS}
    for o in lows.values():
        o.hide_render = False; o.hide_set(False); o.hide_viewport = False
    return lows


def texel_maps(lows):
    GT.TEX = TEX
    part, mat, P, N = GT.texel_maps(lows)
    P = np.where((part > 0)[..., None], P - np.array((0.0, 0.0, CZ), np.float32), 0).astype(np.float32)
    return part, P, N


def load_img(path):
    img = bpy.data.images.load(path, check_existing=False); img.colorspace_settings.name = 'Non-Color'
    a = GT.pixels_any(img); bpy.data.images.remove(img)
    return a


def down(a, n):
    s = a.shape[0] // n
    return a if s == 1 else a.reshape(n, s, n, s, a.shape[2]).mean((1, 3))


def load_6g():
    out = {k: down(load_img(p), TEX) for k, p in SRC6G.items()}
    nrm = out["Normal"][..., :3] * 2 - 1
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True).clip(1e-6)
    return dict(normal=nrm * 0.5 + 0.5, ao=out["AO"][..., 0], id=out["ID"][..., :3])


def classify(idm, cover):
    """kind per texel: nearest ID colour; black (no high hit) -> paint"""
    cols = np.array([c for c, _ in ID_COLS] + [(0, 0, 0)], np.float32)
    d = np.linalg.norm(idm[..., None, :] - cols[None, None], axis=3)
    k = d.argmin(2)
    k[k == len(ID_COLS)] = KPAINT
    k[~cover] = -1
    return k.astype(np.int8)


# --------------------------------------------------------------------------- pre-bakes from the high (cage)


def ao_emit(inside, dist):
    def b(nt, em):
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion"); ao.inside = inside; ao.only_local = True; ao.samples = 16
        ao.inputs["Distance"].default_value = dist
        if inside:
            inv = nt.nodes.new("ShaderNodeMath"); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
            nt.links.new(ao.outputs["AO"], inv.inputs[1]); nt.links.new(inv.outputs[0], em.inputs["Color"])
        else:
            nt.links.new(ao.outputs["AO"], em.inputs["Color"])
    return BF.node_mat(f"pre_{'edge' if inside else 'cav'}", b)


def prebakes(lows, cover):
    sc = bpy.context.scene
    lo, hi, cg = BF.objs()
    for o in list(hi.values()) + list(cg.values()):
        o.hide_set(False); o.hide_viewport = False
    for o in lo.values():
        o.visible_diffuse = o.visible_glossy = o.visible_shadow = o.visible_transmission = o.visible_volume_scatter = False
    parts_hi = {k: BF.split_details(hi[k]) for k in PARTS}
    for hs in parts_hi.values():
        for h in hs: h.hide_set(False); h.hide_viewport = False
    keep_lo = {k: list(o.data.materials) for k, o in lo.items()}
    T.RES = TEX
    res = {}
    for kind, mat, smp in (("edge", ao_emit(True, EDGE_DIST), BAKE_SAMPLES["prebake"]),
                           ("cavity", ao_emit(False, CAV_DIST), BAKE_SAMPLES["prebake"]),
                           ("miss", BF.emit_const((1, 1, 1, 1)), 1)):
        sc.cycles.samples = smp
        img = T.new_image(f"pre_{kind}", color=(0, 0, 0, 1)); t = time.time()
        for i, k in enumerate(PARTS):
            T.target_material(lo[k], img)
            keep = BF.set_mats(parts_hi[k], mat)
            BF.run_bake(lo[k], parts_hi[k], cg[k], img, "EMIT", i == 0)
            BF.restore_mats(parts_hi[k], keep)
        res[kind] = GT.pixels(img)[..., 0].copy()
        print(f"PREBAKE {kind}: {time.time() - t:.0f} s")
    for k, o in lo.items():
        o.data.materials.clear()
        for m in keep_lo[k]: o.data.materials.append(m)
        o.visible_diffuse = o.visible_glossy = o.visible_shadow = o.visible_transmission = o.visible_volume_scatter = True
        o.hide_render = False
    for hs in parts_hi.values():
        for h in hs: h.hide_render = True
    for o in list(hi.values()) + list(cg.values()): o.hide_render = True
    miss = cover & (res["miss"] < 0.5)
    good = cover & ~miss
    edge, cav = res["edge"].copy(), res["cavity"].copy()
    edge[miss] = 0.0; cav[miss] = 1.0
    edge = GT.dilate(edge[..., None], good, DILATE)[..., 0]; cav = GT.dilate(cav[..., None], good, DILATE)[..., 0]
    print(f"INFO pre-bake ray misses {int(miss.sum())} texels ({100 * miss.sum() / cover.sum():.2f} %; 6g: buried drum texels)")
    return dict(edge=edge, cavity=cav, miss=miss)


# --------------------------------------------------------------------------- detail maps


def wobble(th, amp=0.35, ks=(2, 3, 5)):
    f = np.ones_like(th)
    for k in ks:
        f += RNG.uniform(0.3, 1.0) * amp / k * np.sin(k * th + RNG.uniform(0, 2 * math.pi))
    return f


def frame(n):
    up = np.array((0.0, 1.0, 0.0)) if abs(n[1]) < 0.9 else np.array((0.0, 0.0, 1.0))
    up = up - n * (up @ n); up /= np.linalg.norm(up)
    return up, np.cross(up, n)


def fastener_clusters(part, kind, P, N):
    out = []
    for pi in range(1, len(PARTS) + 1):
        ys, xs = np.nonzero((part == pi) & (kind == KFAST))
        if not len(ys): continue
        pts, nn = P[ys, xs].astype(float), N[ys, xs].astype(float)
        left = np.ones(len(pts), bool)
        while left.any():
            i = np.flatnonzero(left)[0]
            c = pts[(np.linalg.norm(pts - pts[i], axis=1) < 0.03) & left].mean(0)
            sel = left & (np.linalg.norm(pts - c, axis=1) < 0.03)
            left[sel] = False
            if sel.sum() < 8 * (TEX / 2048) ** 2: continue
            c = pts[sel].mean(0); n = nn[sel].mean(0); n /= max(np.linalg.norm(n), 1e-6)
            d = pts[sel] - c; w = float(np.percentile(np.linalg.norm(d - np.outer(d @ n, n), axis=1), 95))
            out.append((pi, c, n, max(w, 0.006)))
    return out


# C-T1b texture details (HERO_SPEC §3 "Dimensions"): plinth side panels (outline groove y 0.052 ... 0.126; lengths
# 0.60 on the Z faces, 0.56 on the X faces, 0.37 on the diagonal faces, measured from the 6g normal), rest-plate top flat
# (y 1.699, x 0.322 ... 1.104, z +-0.176), tier-1 top chamfer (y 0.162 ... 0.203), tier-2 front wall (z -0.84, visible
# y 0.176 ... 0.246)
PANEL_LEN = {0: 0.60, 180: 0.60, 90: 0.56, 270: 0.56, 45: 0.37, 135: 0.37, 225: 0.37, 315: 0.37}
PANEL_Y = (0.066, 0.112)
PLATE_BOLTS = [(x, z) for x in (0.352, 1.074) for z in (-0.146, 0.146)]
PAD_FOOT = (0.39, 0.61, -0.068, 0.072)                    # pad footprint on the plate top (x0, x1, z0, z1), closed pose
STRIP = dict(z=-0.843, y=0.211, hw=0.09, hh=0.005, frame=0.004)   # cyan status strip on the tier-2 front wall
HAZ_Y, HAZ_PITCH = (0.158, 0.207), 0.11
PIVOT_R, ELBOW_R = (0.385, 0.637), (0.563, 0.96)


def bolts(part, P, N):
    """(part index, centre, normal, hex apothem, washer radius): plinth panel ends, plate-top corners"""
    out = []
    base = part == 1; r = np.hypot(P[..., 0], P[..., 2])
    wall = base & (np.abs(N[..., 1]) < 0.2) & (r > 1.0) & (P[..., 1] > 0.04) & (P[..., 1] < 0.14)
    for a0, L in PANEL_LEN.items():
        n = np.array((math.sin(math.radians(a0)), 0.0, -math.cos(math.radians(a0)))); tg = np.array((-n[2], 0.0, n[0]))
        sel = wall & ((N @ n) > 0.99)
        if not sel.any(): continue
        dist = float(np.median(P[sel] @ n))
        for s in (-(L / 2 + 0.022), L / 2 + 0.022):
            for y in PANEL_Y:
                out.append((1, n * dist + tg * s + np.array((0, y, 0)), n, 0.0065, 0.0095))
    yt = float(P[(part == 2) & (N[..., 1] > 0.99)][:, 1].max())
    out += [(2, np.array((x, yt, z)), np.array((0.0, 1.0, 0.0)), 0.0075, 0.011) for x, z in PLATE_BOLTS]
    return out


def details(part, kind, P, N, cav, edge):
    cover = part > 0
    Z = lambda: np.zeros((TEX, TEX), np.float32)
    RB, ST, SCUFF, H, BOLT, HAZ, STRIPE, LIGHT, LFRAME, JOINT = (Z() for _ in range(10))
    HY = (np.clip(1 - P[..., 1] / 0.9, 0, 1) * cover).astype(np.float32)
    paintlike = (kind == KPAINT) | (kind == KPANEL) | (kind == KFAST)
    streaks = []
    # ---- normal-map bolts (hex head + washer, random turn), rust round some, a streak below some
    bl = bolts(part, P, N); nring = 0
    for pi, c, n, a, w in bl:
        m = (part == pi) & (np.abs((P - c) @ n) < 0.003) & ((N @ n) > 0.95)
        ys, xs = np.nonzero(m & (np.linalg.norm(P - c, axis=2) < w + 0.03))
        if not len(ys): continue
        up, rt = frame(n)
        d = P[ys, xs] - c; x, y = d @ rt, d @ up
        th = RNG.uniform(0, math.pi / 3); xr, yr = x * math.cos(th) - y * math.sin(th), x * math.sin(th) + y * math.cos(th)
        rr = np.hypot(x, y); dh = np.maximum(np.abs(yr), 0.866 * np.abs(xr) + 0.5 * np.abs(yr))
        washer = np.clip((w - rr) / 0.0007, 0, 1); head = np.clip((a - dh) / 0.0012, 0, 1)
        H[ys, xs] = np.maximum(H[ys, xs], 0.0010 * washer + 0.0035 * head)
        BOLT[ys, xs] = np.maximum(BOLT[ys, xs], washer)
        ring = RNG.choice((0.0, 0.45, 0.75, 1.0), p=(0.4, 0.2, 0.2, 0.2))
        if ring == 0: continue
        nring += 1
        reach = RNG.uniform(0.008, 0.020); off = RNG.normal(0, 0.25, 2) * w
        x2, y2 = x - off[0], y - off[1]; r2 = np.hypot(x2, y2) * wobble(np.arctan2(y2, x2), 0.6)
        RB[ys, xs] = np.maximum(RB[ys, xs], ring * np.clip(1 - np.maximum(r2 - w, 0) / reach, 0, 1) * (rr > 0.8 * w))
        if abs(n[1]) < 0.3 and ring > 0.5 and RNG.random() < 0.6: streaks.append((pi, c - up * w * 0.8, n, up, 0.004))
    # ---- the modelled fasteners (column hatch, plate necks, riser top): rust round some
    fc = fastener_clusters(part, kind, P, N)
    for pi, c, n, w in fc:
        ring = RNG.choice((0.0, 0.45, 0.75, 1.0), p=(0.45, 0.2, 0.2, 0.15))
        if ring == 0: continue
        nring += 1
        reach = RNG.uniform(0.008, 0.018); d = P - c
        m = (part == pi) & paintlike & (np.abs(d @ n) < 0.015) & ((N @ n) > 0.8) & (np.linalg.norm(d, axis=2) < w + reach + 0.01)
        ys, xs = np.nonzero(m)
        if not len(ys): continue
        up, rt = frame(n)
        dd = d[ys, xs]; x, y = dd @ rt, dd @ up
        off = RNG.normal(0, 0.25, 2) * w; x2, y2 = x - off[0], y - off[1]
        rr = np.hypot(x, y); r2 = np.hypot(x2, y2) * wobble(np.arctan2(y2, x2), 0.6)
        RB[ys, xs] = np.maximum(RB[ys, xs], ring * np.clip(1 - np.maximum(r2 - w, 0) / reach, 0, 1) * (rr > 0.8 * w))
        if abs(n[1]) < 0.3 and ring > 0.5 and RNG.random() < 0.5: streaks.append((pi, c - up * w * 0.8, n, up, 0.004))
    # ---- joints and under the pads (rust weight for the shader): arm root round the pin, elbow, drums; a ring round
    # the pad footprint on the plate top
    ar = part == 2
    dpiv = np.hypot(P[..., 0] - PIVOT_R[0], P[..., 1] - PIVOT_R[1]); delb = np.hypot(P[..., 0] - ELBOW_R[0], P[..., 1] - ELBOW_R[1])
    JOINT[ar] = np.maximum(np.clip(1 - (dpiv[ar] - 0.10) / 0.08, 0, 1), 0.7 * np.clip(1 - (delb[ar] - 0.06) / 0.06, 0, 1))
    drum = (part == 1) & (np.abs(P[..., 0]) > 0.26) & (P[..., 1] > 0.48) & (P[..., 1] < 0.78)
    JOINT[drum] = 0.4
    top = ar & (N[..., 1] > 0.99) & (P[..., 1] > 1.69)
    x0, x1, z0, z1 = PAD_FOOT
    dx = np.maximum(np.maximum(x0 - P[..., 0], P[..., 0] - x1), 0); dz = np.maximum(np.maximum(z0 - P[..., 2], P[..., 2] - z1), 0)
    dfoot = np.hypot(dx, dz)
    JOINT[top] = np.maximum(JOINT[top], np.clip(1 - dfoot[top] / 0.018, 0, 1))
    # ---- small irregular rust spots on features (edges, seams, outer corners, joints), never on flat face centres
    ef = edge.ravel(); cf = np.clip(1 - cav.ravel(), 0, 1)
    cand = np.flatnonzero((paintlike & cover).ravel())
    feat = np.clip(2.0 * ef[cand] + 3.0 * cf[cand] + 1.2 * JOINT.ravel()[cand], 0, None)
    wgt = (feat * (0.3 + 2.0 * HY.ravel()[cand])) ** 2 * np.where(part.ravel()[cand] == 2, 2.5, 1.0)
    wgt[(ef[cand] < 0.05) & (cf[cand] < 0.07) & (JOINT.ravel()[cand] < 0.1)] = 0
    nsp = 150
    picks = RNG.choice(cand, size=nsp, replace=False, p=wgt / wgt.sum())
    for f in picks:
        y0, x0_ = divmod(int(f), TEX); c = P[y0, x0_].astype(float); n = N[y0, x0_].astype(float); pi = part[y0, x0_]
        R = RNG.uniform(0.008, 0.025) * (1 + 0.5 * HY[y0, x0_])
        d = P - c
        m = (part == pi) & paintlike & (np.linalg.norm(d, axis=2) < 2.5 * R) & ((N @ n) > 0.3)
        ys, xs = np.nonzero(m)
        up, rt = frame(n)
        dd = d[ys, xs]; x, y = dd @ rt, dd @ up
        rr = np.hypot(x, y) * wobble(np.arctan2(y, x), 1.1, (2, 3, 5, 7, 11))
        RB[ys, xs] = np.maximum(RB[ys, xs], np.clip(1 - rr / R, 0, 1) ** 1.3)
        if abs(n[1]) < 0.3 and RNG.random() < 0.35: streaks.append((pi, c - up * R * 0.3, n, up, 0.004))
    for pi, s, n, up, w in streaks:
        L = RNG.uniform(0.05, 0.20); wd = RNG.uniform(0.0025, 0.005)
        rt = np.cross(up, n); d = P - s; x, y = d @ rt, -(d @ up)
        sel = (part == pi) & paintlike & (np.abs(d @ n) < 0.004) & ((N @ n) > 0.95) & (y > 0) & (y < L) & (np.abs(x) < 3 * wd)
        ys, xs = np.nonzero(sel)
        t = y[ys, xs] / L; ww = wd * (1 + 1.5 * t)
        ST[ys, xs] = np.maximum(ST[ys, xs], np.clip(1 - np.abs(x[ys, xs]) / ww, 0, 1) * (1 - t) ** 1.5)
    # ---- pads: limb contact band along the pad's long axis (X in the closed pose), on the top face
    pp = PARTS.index("Pad") + 1
    ptop = (part == pp) & (N[..., 1] > 0.9)
    if ptop.any():
        ytop = P[ptop][:, 1].max(); ptop &= P[..., 1] > ytop - 0.002
        zc = float(np.median(P[ptop][:, 2]))
        band = np.clip(1 - (np.abs(P[..., 2] - zc) - 0.045) / 0.015, 0, 1)
        SCUFF[ptop] = band[ptop]
    # ---- hazard band: tier-1 top chamfer all round, 45 deg stripes (perimeter coordinate + down-slope distance)
    r = np.hypot(P[..., 0], P[..., 2])
    hz = (part == 1) & (N[..., 1] > 0.45) & (N[..., 1] < 0.8) & (r > 0.95) & (P[..., 1] > HAZ_Y[0]) & (P[..., 1] < HAZ_Y[1])
    HAZ[hz] = 1.0
    s = np.arctan2(P[..., 0], -P[..., 2]) * 1.17 + (HAZ_Y[1] - P[..., 1]) * 1.32
    ph = (s / HAZ_PITCH) % 1.0
    aa = 1.0 / (HAZ_PITCH * 435.0 * TEX / 2048)                               # ~1 texel of antialiasing (phase units)
    st = np.clip((np.abs(ph - 0.5) - 0.25) / aa + 0.5, 0, 1)                  # 1 = ochre half, 0 = black half
    STRIPE[hz] = st[hz]
    # ---- cyan status strip (emissive) in a dark polymer frame on the tier-2 front wall
    fw = (part == 1) & (N[..., 2] < -0.98) & (np.abs(P[..., 2] - STRIP["z"]) < 0.008)
    ex = np.abs(P[..., 0]) - STRIP["hw"]; ey = np.abs(P[..., 1] - STRIP["y"]) - STRIP["hh"]
    px = 1.0 / (435.0 * TEX / 2048)
    LIGHT[fw] = (np.clip(0.5 - ex / px, 0, 1) * np.clip(0.5 - ey / px, 0, 1))[fw]
    LFRAME[fw] = (np.clip(0.5 - (ex - STRIP["frame"]) / px, 0, 1) * np.clip(0.5 - (ey - STRIP["frame"]) / px, 0, 1))[fw]
    H[fw] -= 0.0012 * LFRAME[fw]                                               # recessed slot
    Hn = (np.clip(H, H_LO, H_HI) - H_LO) / (H_HI - H_LO)
    print(f"INFO details: {len(bl)} normal-map bolts, {len(fc)} modelled fasteners, {nring} with rust rings, {nsp} feature "
          f"rust spots, {len(streaks)} streaks; hazard texels {int(hz.sum())}, strip texels {int((LIGHT > 0.5).sum())}, "
          f"pad scuff {int((SCUFF > 0.5).sum())}")
    return (np.stack([RB, ST, HY, SCUFF], 2), np.stack([Hn, BOLT, HAZ, STRIPE], 2),
            np.stack([LIGHT, LFRAME, JOINT, (part == 2).astype(np.float32)], 2))


# --------------------------------------------------------------------------- procedural material


def surface_material(d1, d2, d3, d4, d5):
    m = bpy.data.materials.new("M_Cradle_Tex"); m.use_nodes = True; nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
    b = GT.NB(nt)
    out = nt.nodes["Material Output"]
    bsdf = b.n("ShaderNodeBsdfPrincipled")
    em = b.n("ShaderNodeEmission"); em.name = "BakeEmit"
    GT.add_target(nt)
    tc = b.n("ShaderNodeTexCoord"); obj = tc.outputs["Object"]
    geo = b.n("ShaderNodeNewGeometry"); gn = b.n("ShaderNodeSeparateXYZ"); b.link(geo.outputs["Normal"], gn.inputs[0])
    ims = []
    for d in (d1, d2, d3, d4, d5):
        t = b.n("ShaderNodeTexImage", image=d, interpolation='Linear'); s = b.n("ShaderNodeSeparateColor")
        b.link(t.outputs["Color"], s.inputs[0]); ims.append((s, t))
    (s1, t1), (s2, t2), (s3, t3), (s4, t4), (s5, t5) = ims
    RB, ST, HY, SC = s1.outputs[0], s1.outputs[1], s1.outputs[2], t1.outputs["Alpha"]
    E, C, RISER = s2.outputs[0], s2.outputs[1], t2.outputs["Alpha"]
    STEEL, OCHRE, PANEL, FAST = s3.outputs[0], s3.outputs[1], s3.outputs[2], t3.outputs["Alpha"]
    Hn, BO, HAZ, STR = s4.outputs[0], s4.outputs[1], s4.outputs[2], t4.outputs["Alpha"]
    LT, LF, JOINT, WB = s5.outputs[0], s5.outputs[1], s5.outputs[2], t5.outputs["Alpha"]
    nf = b.noise(obj, 90.0, 6.0); nw = b.noise(obj, 2.5, 4.0); nr = b.noise(obj, 22.0, 10.0, 0.65)
    nr2 = b.noise(obj, 140.0, 4.0); nr3 = b.noise(obj, 55.0, 8.0, 0.7)

    # hairline scratches: noise stretched along one object axis; faces facing along that axis are masked out
    def hairlines(axis, rot_axis, rot_deg, scale, stretch, width, dens, lo, hi, seed):
        mp = b.n("ShaderNodeMapping"); b.link(obj, mp.inputs[0])
        sv = [1.0, 1.0, 1.0]; sv[axis] = stretch; mp.inputs["Scale"].default_value = sv
        rv = [0.0, 0.0, 0.0]; rv[rot_axis] = math.radians(rot_deg); mp.inputs["Rotation"].default_value = rv
        mp.inputs["Location"].default_value = (seed, 0.37 * seed, 0.11 * seed)
        t = b.n("ShaderNodeTexNoise"); b.link(mp.outputs[0], t.inputs["Vector"])
        t.inputs["Scale"].default_value = scale; t.inputs["Detail"].default_value = 1.5; t.inputs["Roughness"].default_value = 0.4
        ln = b.remap(b.math('ABSOLUTE', b.sub(t.outputs["Fac"], 0.5)), 0.0, width, 1.0, 0.0)
        return b.mul(ln, b.remap(b.noise(obj, dens, 2.0), lo, hi))
    sz = b.math('MAXIMUM', hairlines(2, 1, 0, 1.6, 70.0, 0.008, 1.2, 0.46, 0.56, 0.0), hairlines(2, 1, 28, 1.4, 70.0, 0.005, 1.4, 0.50, 0.60, 3.1))
    sz = b.math('MAXIMUM', sz, hairlines(2, 1, -35, 1.3, 70.0, 0.005, 1.3, 0.53, 0.62, 7.7))
    sx = b.math('MAXIMUM', hairlines(0, 2, 15, 1.5, 70.0, 0.006, 1.2, 0.48, 0.58, 5.3), hairlines(0, 2, -30, 1.3, 70.0, 0.005, 1.3, 0.52, 0.61, 9.9))
    mz = b.remap(b.math('ABSOLUTE', gn.outputs[2]), 0.5, 0.9, 1.0, 0.0)
    mx = b.remap(b.math('ABSOLUTE', gn.outputs[0]), 0.5, 0.9, 1.0, 0.0)
    clean = b.sub(1.0, b.clamp(b.add(LF, LT)))                                     # strip and its frame stay clean
    scratch = b.mul(b.math('MAXIMUM', b.mul(sz, mz), b.mul(sx, mx)), clean)
    # grime: recesses (cavity), a little towards the floor; the same on arms, plates and column
    grime = b.clamp(b.add(b.mul(b.sub(1.0, C), 2.6), b.mul(b.remap(HY, 0.2, 1.0, 0.0, 0.5), nw)))

    # ---- paint family: structure paint, access panel, ochre pads, fasteners / bolts (painted like their surface)
    pcol = b.mix(PANEL, b.rgb(PAINT_C), b.rgb(PANEL_C))
    pcol = b.mix(OCHRE, pcol, b.rgb(OCHRE_C))
    g = b.add(0.88, b.mul(b.remap(nf, 0.3, 0.7), 0.24))
    g = b.mul(g, b.sub(1.0, b.mul(b.remap(nw, 0.35, 0.65), 0.10)))                 # large mottling
    base = b.mix(1.0, pcol, g, 'MULTIPLY')
    # hazard band (Gate style): 45 deg ochre / black stripes, worn more at the band's edges (convex chamfer edges)
    ochre = b.mix(b.remap(nw, 0.3, 0.7), b.rgb(tuple(0.85 * c for c in OCHRE_C)), b.rgb(tuple(1.08 * c for c in OCHRE_C)))
    hzc = b.mix(STR, b.rgb(BLACK_C), ochre)
    chip = b.clamp(b.add(b.remap(b.add(b.mul(E, 1.5), b.mul(b.sub(nr, 0.5), 1.2)), 0.30, 0.50),
                         b.remap(b.add(b.mul(scratch, 0.8), b.mul(b.sub(nr, 0.5), 0.8)), 0.55, 0.7)))
    base = b.mix(b.mul(HAZ, b.sub(1.0, chip)), base, hzc)                          # worn: the gunmetal under-paint shows
    sect = b.remap(b.noise(obj, 12.0, 3.0), 0.42, 0.60)
    ew = b.add(b.mul(E, b.add(0.55, b.mul(sect, 0.9))), b.mul(b.mul(E, FAST), 0.6), b.mul(b.mul(E, OCHRE), 0.35))
    wear = b.remap(b.add(ew, b.mul(b.sub(nr, 0.5), 0.7), b.mul(scratch, 0.25), b.mul(WB, 0.07)), 0.54, 0.64)
    wear = b.mul(wear, clean)
    scuff = b.mul(SC, b.remap(b.add(b.noise(obj, 30.0, 6.0, 0.6), b.mul(b.sub(nw, 0.5), 0.6)), 0.40, 0.70))
    wear = b.clamp(b.add(wear, b.mul(b.mul(SC, b.remap(nr, 0.62, 0.72)), 0.45)))    # limb contact: paint rubbed through (few spots)
    # rust (STYLE_GUIDE rule, Gate G2c): on features only - edges, seams / recesses (low cavity), bolts and fasteners,
    # spots (RB), joints and under the pads (JOINT), the plinth's bottom edge; streaks (ST). Flat face centres stay
    # clean. nr2 / nr3 break the outlines into small irregular pieces.
    bot = b.mul(b.remap(HY, 0.93, 0.985, 0.0, 0.9), b.remap(b.noise(obj, 6.0, 4.0), 0.40, 0.62))
    er = b.mul(b.mul(E, b.add(1.0, b.mul(HY, 0.6))), b.remap(b.noise(obj, 9.0, 4.0), 0.42, 0.62))
    spk = b.mul(b.remap(nr3, 0.62, 0.72), b.remap(b.noise(obj, 2.2, 2.0), 0.40, 0.60))
    rvv = b.add(b.mul(RB, 0.95), b.mul(er, 1.6), bot, b.mul(spk, 0.5), b.mul(JOINT, b.remap(nr3, 0.35, 0.75, 0.0, 0.5)),
                b.mul(HY, 0.30), b.mul(b.sub(nr, 0.5), 1.0), b.mul(b.sub(nr2, 0.5), 0.45), b.mul(b.sub(nr3, 0.5), 0.35))
    near = b.clamp(b.add(b.remap(b.sub(1.0, C), 0.05, 0.25), b.remap(E, 0.12, 0.40), b.mul(RB, 2.0), JOINT,
                         b.remap(HY, 0.93, 0.97)))
    rust = b.clamp(b.add(b.mul(b.remap(rvv, 0.42, 0.50), near), b.mul(ST, b.remap(nf, 0.2, 0.6, 0.55, 1.0))))
    rust = b.mul(rust, b.sub(1.0, b.mul(OCHRE, 0.7)))                              # the drone-handling ochre stays bright
    rust = b.mul(rust, b.sub(1.0, b.mul(HAZ, 0.4)))
    rust = b.mul(rust, clean)
    col = b.mix(b.mul(scratch, 0.6), base, (1.9, 1.9, 1.9), 'MULTIPLY')            # hairlines read lighter
    col = b.mix(b.mul(scuff, 0.75), col, b.rgb(tuple(0.40 * c for c in OCHRE_C)))  # dark rubbing marks on the pads
    col = b.mix(wear, col, b.rgb(STEEL_C))
    tip = b.mul(b.mul(b.mul(BO, b.remap(Hn, 0.86, 0.93)), b.remap(nr2, 0.60, 0.72)), b.remap(nr, 0.35, 0.55))
    col = b.mix(tip, col, b.rgb(STEEL_C))                                          # some bolt heads chipped to steel
    rcol = b.mix(b.remap(rvv, 0.60, 0.95), b.rgb(RUST_EDGE), b.rgb(RUST_DARK))
    rcol = b.mix(b.mul(b.remap(nr2, 0.3, 0.8), 0.35), rcol, b.rgb(tuple(0.85 * c for c in RUST_C)))
    col = b.mix(rust, col, rcol)
    bare = b.mul(b.math('MAXIMUM', wear, tip), b.sub(1.0, rust))
    col = b.mix(b.mul(b.mul(b.mul(grime, 0.8), b.sub(1.0, b.mul(bare, 0.9))), clean), col, b.rgb(GRIME_C))
    col = b.mix(LF, col, b.rgb(POLY_C))                                            # strip frame: dark polymer
    col = b.mix(LT, col, b.rgb(CYAN_OFF))                                          # strip: off-state albedo
    p_col = col
    p_metal = b.mul(bare, clean)
    rough = b.add(0.56, b.mul(b.sub(nw, 0.5), 0.3), b.mul(scratch, -0.2), b.mul(OCHRE, -0.04))
    rough = b.mixf(b.math('MAXIMUM', wear, tip), rough, b.add(0.60, b.mul(b.sub(nf, 0.5), 0.1), b.mul(grime, 0.25)))
    rough = b.mixf(rust, rough, b.add(0.85, b.mul(b.sub(nr2, 0.5), 0.1)))
    rough = b.add(rough, b.mul(grime, 0.12), b.mul(scuff, 0.08))
    rough = b.mixf(LF, rough, 0.62); p_rough = b.mixf(LT, rough, 0.35)
    p_hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.03), b.mul(rust, b.mul(b.sub(nr2, 0.5), 0.04)), b.mul(scratch, -0.015))

    # ---- machined steel (pins, caps, drum bands, annulus) and the riser: worn steel, not chrome - rough, polished
    # only on the edges, dielectric grime in the recesses (albedo of the clean steel stays >= 180)
    sbase = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.96 * c for c in STEEL_C)), b.rgb(tuple(1.03 * c for c in STEEL_C)))
    srust = b.mul(b.remap(b.add(b.mul(RB, 0.5), b.mul(b.sub(nr, 0.5), 1.1), b.mul(HY, 0.15), b.mul(b.sub(1.0, C), 0.4),
                                b.mul(JOINT, 0.2)), 0.70, 0.86), 0.75)
    srcol = b.mix(b.remap(nr2, 0.2, 0.8), b.rgb(tuple(0.8 * c for c in RUST_C)), b.rgb(RUST_C))
    scol = b.mix(srust, sbase, srcol)
    sgr = b.clamp(b.mul(b.remap(b.sub(1.0, C), 0.02, 0.20), b.remap(b.add(nw, b.mul(b.sub(nr3, 0.5), 0.6)), 0.25, 0.55)))
    smg = b.mul(b.remap(b.add(b.noise(obj, 7.0, 5.0, 0.6), b.mul(b.sub(nr3, 0.5), 0.4)), 0.52, 0.70), 0.45)
    sgr = b.clamp(b.add(sgr, smg))
    s_col = b.mix(b.mul(sgr, 0.85), scol, b.rgb(GRIME_C))                          # grime in recesses, smudges
    s_metal = b.mul(b.sub(1.0, srust), b.sub(1.0, b.mul(sgr, 0.95)))
    s_rough = b.add(0.68, b.mul(RISER, 0.10), b.mul(b.sub(nw, 0.5), 0.25), b.mul(b.sub(nr3, 0.5), 0.10),
                    b.mul(E, -0.14), b.mul(scratch, 0.08), b.mul(srust, 0.25), b.mul(sgr, 0.25))
    s_hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), b.add(0.012, b.mul(RISER, 0.02))))

    km = b.clamp(b.add(STEEL, RISER))
    col = b.mix(km, p_col, s_col)
    metal = b.mixf(km, p_metal, s_metal)
    rough = b.mixf(km, p_rough, s_rough)
    hgt = b.mixf(km, p_hgt, s_hgt)
    bump = b.n("ShaderNodeBump"); bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = H_HI - H_LO
    b.link(hgt, bump.inputs["Height"])
    b.link(col, bsdf.inputs["Base Color"]); b.link(b.clamp(metal), bsdf.inputs["Metallic"])
    b.link(b.clamp(rough), bsdf.inputs["Roughness"]); b.link(bump.outputs[0], bsdf.inputs["Normal"])
    emis = b.mix(LT, b.rgb((0, 0, 0)), b.rgb(CYAN_E))
    b.link(emis, bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = 1.0
    sockets = dict(base=col, rough=b.clamp(rough), metal=b.clamp(metal), emis=emis, scratch=b.clamp(scratch))
    m["_bsdf"] = bsdf.name
    b.link(bsdf.outputs[0], out.inputs["Surface"])
    return m, sockets


def rnm(base, detail):
    """reoriented normal mapping (both encoded 0..1, OpenGL tangent space) -> encoded"""
    t = base * 2 - 1; t[..., 2] += 1
    u = detail * 2 - 1; u[..., :2] *= -1
    r = t * (t * u).sum(2, keepdims=True) / t[..., 2:3].clip(1e-4) - u
    r /= np.linalg.norm(r, axis=2, keepdims=True).clip(1e-6)
    return r * 0.5 + 0.5


# --------------------------------------------------------------------------- bake stage


def bake(args):
    os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    lows = open_bake()
    part, P, N = texel_maps(lows)
    cover = part > 0
    m6 = load_6g()
    kind = classify(m6["id"], cover)
    print("INFO kinds: " + ", ".join(f"{n} {100 * (kind == i).sum() / cover.sum():.1f} %" for i, n in enumerate(KNAMES)))
    prev = os.path.join(WORK, "prebakes.npz")
    if "reuse" in args and os.path.exists(prev):
        pre = dict(np.load(prev)); print("INFO pre-bakes reused")
    else:
        pre = prebakes(lows, cover); np.savez_compressed(prev, **pre)
    edge = np.clip(GT.blur_masked(pre["edge"], cover, 1) * EDGE_GAIN, 0, 1)
    cav = GT.blur_masked(pre["cavity"], cover, 1)
    print(f"INFO edge mask p90 / p99 {np.percentile(edge[cover], 90):.2f} / {np.percentile(edge[cover], 99):.2f}")
    d1, d4, d5 = details(part, kind, P, N, cav, edge)
    f = lambda k: (kind == k).astype(np.float32)
    d2 = np.stack([edge, cav, m6["ao"], f(KRISER)], 2)
    d3 = np.stack([f(KSTEEL), f(KOCHRE), f(KPANEL), f(KFAST)], 2)
    np.savez_compressed(os.path.join(WORK, "texels.npz"), part=part, P=P, N=N, kind=kind, miss=pre["miss"])
    ds = [GT.dilate(a, cover, DILATE) for a in (d1, d2, d3, d4, d5)]
    mat, socks = surface_material(*(GT.new_image(f"D{i + 1}", a, size=TEX) for i, a in enumerate(ds)))
    keep = GT.swap_materials(lows, lambda i: mat)
    maps = {}
    for ch, kd, smp in (("base", "EMIT", "emit"), ("rough", "EMIT", "emit"), ("metal", "EMIT", "emit"),
                        ("emis", "EMIT", "emit"), ("scratch", "EMIT", "emit"), ("normal", "NORMAL", "normal")):
        GT.set_channel(mat, socks, ch)
        img = GT.new_image(f"bake_{ch}", size=TEX); GT.run_bake(lows, ch, img, kd, BAKE_SAMPLES[smp])
        maps[ch] = GT.pixels(img).copy()
    GT.restore(lows, keep)
    Dm = {k: GT.dilate(v, cover, DILATE) for k, v in maps.items()}
    one = np.ones((TEX, TEX, 1))
    nrm = rnm(m6["normal"], Dm["normal"][..., :3])
    base = np.concatenate([GT.to_srgb(Dm["base"][..., :3]), one], 2)
    mask = np.stack([Dm["metal"][..., 0], m6["ao"], np.zeros((TEX, TEX)), 1 - Dm["rough"][..., 0]], 2)
    emis = np.concatenate([GT.to_srgb(Dm["emis"][..., :3]), one], 2)
    for arr, k in ((base, "BaseColor"), (np.concatenate([nrm, one], 2), "Normal"), (mask, "Mask"), (emis, "Emission")):
        GT.save_png(arr, FILES[k], OUT)
    np.savez_compressed(os.path.join(WORK, "masks.npz"), edge=edge, cavity=cav, ao=m6["ao"], rb=d1[..., 0],
                        scratch=maps["scratch"][..., 0], bolt=d4[..., 1], haz=d4[..., 2], light=d5[..., 0],
                        lframe=d5[..., 1])
    print(f"INFO bake total {time.time() - t0:.0f} s")


# --------------------------------------------------------------------------- checks


SEAM_MIN, SMALL_PATCH = 0.030, 40


def load_out(fn):
    return load_img(os.path.join(OUT, fn))


def check(args):
    lows = open_bake()
    tx = np.load(os.path.join(WORK, "texels.npz")); part, kind, P, N = tx["part"], tx["kind"], tx["P"], tx["N"]
    cover = part > 0
    base = load_out(FILES["BaseColor"]); mask = load_out(FILES["Mask"]); emis = load_out(FILES["Emission"])
    nrm = load_out(FILES["Normal"])
    ok_all = True
    print(f"INFO texel density: UVs unchanged since Step 6f (HERO_SPEC §3: 435.1 px/m at 2048, Cradle v2 UV rules)")
    # AO black scan; visibility = the Cradle's own hero check c (cradle_v2_bake_final._visible_texels: not buried in
    # the low's other shells, not in an enclosed void such as the pocket between arm top and plate)
    BF.RES = TEX
    ao = mask[..., 1]
    dark_all = cover & (ao < GT.AO_BLACK)
    for pi, name in enumerate(PARTS, 1):
        vis, _ = BF._visible_texels(lows[name], dark_all & (part == pi))
        dark = (part == pi) & dark_all & vis
        print(f"INFO AO {name}: {int(((part == pi) & dark_all & ~vis).sum())} dark texels hidden (buried or enclosed)")
        pcs = GT.components(dark) if dark.sum() < 200000 else []
        patches = [c for c in pcs if len(c) / (np.ptp(c, 0).max() + 1) > GT.LINE_MAX]
        small = [c for c in patches if len(c) < SMALL_PATCH]
        patches = [c for c in patches if len(c) >= SMALL_PATCH]
        if small: print(f"INFO AO {name}: {len(small)} small crevice patches (< {SMALL_PATCH} texels): "
                        + ", ".join(f"{len(c)} at {np.round(P[c[:, 0], c[:, 1]].mean(0).astype(float), 3).tolist()}" for c in small[:4]))
        ok = not patches; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} AO black {name}: {int(dark.sum())} texels AO < {GT.AO_BLACK}, "
              f"{len(pcs) - len(patches) - len(small)} contact lines, {len(patches)} patches"
              + ("; " + ", ".join(f"{len(c)} at {np.round(P[c[:, 0], c[:, 1]].mean(0).astype(float), 3).tolist()}"
                                  for c in sorted(patches, key=len)[::-1][:4]) if patches else ""))
    # PBR values
    srgb = base[..., :3] * 255; met = mask[..., 0]
    nonmetal = cover & (met < 0.1); metal = cover & (met > 0.9); trans = cover & (met >= 0.1) & (met <= 0.9)
    lo = (srgb.min(2) < 29.5) & nonmetal; hi = (srgb.max(2) > 240.5) & nonmetal
    mlow = metal & (srgb.mean(2) < 180)
    f = lambda m, d: 100.0 * m.sum() / max(d.sum(), 1)
    ok = f(lo, nonmetal) < 0.5 and f(hi, nonmetal) < 0.5; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} PBR non-metal albedo sRGB 30-240: {f(lo, nonmetal):.2f} % below, {f(hi, nonmetal):.2f} % above "
          f"(of {nonmetal.sum()} texels)")
    ok = f(mlow, metal) < 1.0; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} PBR metal albedo >= 180 sRGB: {f(mlow, metal):.2f} % below (of {metal.sum()} metal texels)")
    print(f"INFO metallic: {f(metal, cover):.1f} % metal, {f(trans, cover):.2f} % transitions 0.1-0.9 (worn edges, rust, grime)")
    for k, nm in enumerate(KNAMES):
        sel = cover & (kind == k)
        if sel.any():
            print(f"INFO {nm}: albedo sRGB median {tuple(int(v) for v in np.median(srgb[sel], 0).round())}, smoothness median "
                  f"{np.median(mask[..., 3][sel]):.2f}, metallic mean {met[sel].mean():.2f}")
    # rust rule on the painted structure (paint + access panel + fasteners; the ochre pads are kept bright)
    mk = np.load(os.path.join(WORK, "masks.npz"))
    haz, light = mk["haz"] > 0.5, mk["light"] > 0.05
    paint = cover & ((kind == KPAINT) | (kind == KPANEL) | (kind == KFAST)) & ~haz & ~grow(mk["lframe"] > 0.05, 1)
    r, g, bb = srgb[..., 0], srgb[..., 1], srgb[..., 2]
    rust = paint & (r > g + 12) & (g > bb + 4) & (mask[..., 3] < 0.32)
    low_, high_ = paint & (P[..., 1] < 0.45), paint & (P[..., 1] >= 0.45)
    pr = f(rust, paint); ok = 5.0 <= pr <= 15.0; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} rust rule: {pr:.1f} % of the painted texels (5-15 %); below y 0.45 {f(rust & low_, low_):.1f} %, "
          f"above {f(rust & high_, high_):.1f} % (hazard band and strip frame excluded)")
    # C-T1b: the same wear everywhere - rust / bare-steel wear / grime per region of the painted structure
    wear_ = paint & (met > 0.5)
    grime_ = paint & (srgb.max(2) < 52) & ~rust
    for nm, sel in (("plinth y<0.40", paint & (part == 1) & (P[..., 1] < 0.40)),
                    ("column+beam", paint & (part == 1) & (P[..., 1] >= 0.40)),
                    ("arm", paint & (part == 2) & (P[..., 1] < 1.58)),
                    ("rest plate", paint & (part == 2) & (P[..., 1] >= 1.58)), ("riser", paint & (part == 4))):
        if sel.any():
            print(f"INFO {nm}: rust {f(rust & sel, sel):.1f} %, bare-steel wear {f(wear_ & sel, sel):.1f} %, "
                  f"dark grime {f(grime_ & sel, sel):.1f} %")
    # rust layout: on features, off flat face centres (texels > 25 mm from any edge / recess)
    edge, cav = mk["edge"], mk["cavity"]
    feat = grow((edge > 0.10) | (cav < 0.93), int(round(0.025 * 435.0 * TEX / 2048)))
    print(f"INFO rust on features (within 25 mm of an edge / recess): {f(rust & feat, rust):.1f} % of the rust; "
          f"flat face centres rusty {f(rust & ~feat, paint & ~feat):.1f} %")
    hz = cover & haz
    print(f"INFO hazard band: {hz.sum()} texels, ochre {f(hz & (r > bb + 60), hz):.0f} %, black {f(hz & (srgb.max(2) < 50), hz):.0f} %, "
          f"worn / rusty rest {f(hz & ~(r > bb + 60) & ~(srgb.max(2) < 50), hz):.0f} %")
    och = cover & (kind == KOCHRE)
    print(f"INFO ochre pads: rust-coloured {f(och & (mask[..., 3] < 0.32) & (r > g + 40), och):.1f} %, bare steel {f(och & metal, och):.1f} %")
    # emission: one cyan status strip only (STYLE_GUIDE cyan 70 170 255); outside the strip black; never white
    e = emis[..., :3] * 255
    outside = cover & ~grow(light, 2)
    core = cover & (mk["light"] > 0.95)
    med = np.median(e[core], 0) if core.any() else np.zeros(3)
    white = cover & (e.min(2) > 0.85 * 255)
    ok = core.sum() > 100 and e[outside].max() < 0.5 and not white.any() and abs(med - (70, 170, 255)).max() < 6
    ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} emission: cyan strip {int(core.sum())} texels, median sRGB {tuple(int(v) for v in med)}, "
          f"max outside the strip {e[outside].max():.0f}, white texels {int(white.sum())}")
    # normal seams (same-point method, interpolated MikkTSpace frame), final map vs the 6g high-poly bake
    n6 = load_6g()["normal"]
    scr = np.load(os.path.join(WORK, "masks.npz"))["scratch"] > 0.15
    relief = grow(rust | scr | (cover & (kind == KFAST)) | (mk["bolt"] > 0.05) | (mk["lframe"] > 0.05), 4)
    # rust / scratch / fastener / normal-map bolt / strip-slot relief, 4 px
    for n, o in lows.items():
        ok_all &= normal_seams(n, o, nrm, n6, part, P, relief, (srgb, mask[..., 3]))
    print("RESULT:", "PASS" if ok_all else "FAIL")


def grow(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def normal_seams(name, o, nrm, n6, part, P, relief, look, max_deg=6.0, add_deg=2.0):
    """normal-map continuity across UV seams between coplanar faces (terminal_tex same-point method: both samples
    1.5 px from the seam, perpendicular to the edge in each island). Cradle: the low is smooth-shaded across its
    chamfers (custom normals), so each sample is decoded with the MikkTSpace frame interpolated at its own texel
    (barycentric in its loop triangle), not the face's first-loop frame. Skipped: hidden surfaces (hero check c
    visibility), the 4 mm zone along real mesh edges, deliberate relief within 4 px (rust patches, hairline scratches, fasteners; the
    terminal check skips its grooves and bolts the same way). The normal is the 6g high-poly bake plus the C-T1 detail layer:
    measured on both, C-T1 must not add more than add_deg to the 6g break at any sample (FAIL otherwise); the absolute
    count over max_deg is reported for both (the 6g part belongs to the verified high-poly bake)."""
    me = o.data; W = o.matrix_world
    ef = {}
    for p in me.polygons:
        for k in p.edge_keys: ef.setdefault(k, []).append(p)
    VL = np.array([local(GT.spec(W @ v.co)) for v in me.vertices])
    segs = [(VL[k[0]], VL[k[1]]) for k, fs in ef.items() if not (len(fs) == 2 and fs[0].normal.angle(fs[1].normal, 0) < math.radians(1.0))]
    SA = np.array([a for a, _ in segs]); SB = np.array([b_ for _, b_ in segs])

    def near_edge(q, r=0.004):
        ab = SB - SA; t = np.clip(((q - SA) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
        return np.min(np.linalg.norm(SA + ab * t[:, None] - q, axis=1)) < r
    me.calc_tangents(); uv = me.uv_layers.active.data; me.calc_loop_triangles()
    BF.RES = TEX
    lab, _ = BF._texel_positions(o, lambda lt: lt.index + 1)
    LT = me.loop_triangles

    def frame_at(y, x):
        lt = LT[lab[y, x] - 1]
        U = np.array([uv[li].uv[:] for li in lt.loops]) * TEX; q = np.array((x + 0.5, y + 0.5))
        (ax, ay), (bx, by), (cx, cy) = U; den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        w0 = ((by - cy) * (q[0] - cx) + (cx - bx) * (q[1] - cy)) / den; w1 = ((cy - ay) * (q[0] - cx) + (ax - cx) * (q[1] - cy)) / den
        bc = (w0, w1, 1 - w0 - w1)
        Nn = sum(w * np.array(me.loops[li].normal) for w, li in zip(bc, lt.loops)); Nn /= np.linalg.norm(Nn)
        Tt = sum(w * np.array(me.loops[li].tangent) for w, li in zip(bc, lt.loops)); Tt -= Nn * (Tt @ Nn); Tt /= np.linalg.norm(Tt)
        return Tt, me.loops[lt.loops[0]].bitangent_sign * np.cross(Nn, Tt), Nn

    def side(p, k):
        d = {me.loops[li].vertex_index: np.array(uv[li].uv) for li in p.loop_indices}
        a, b_ = d[k[0]], d[k[1]]; c = np.mean([uv[li].uv for li in p.loop_indices], 0)
        e = b_ - a; nperp = np.array((-e[1], e[0])) / max(np.linalg.norm(e), 1e-12)
        if (c - a) @ nperp < 0: nperp = -nperp
        return a, b_, nperp
    short = 0; samples = []
    for k, fs in ef.items():
        if len(fs) != 2: continue
        a, b_ = fs
        if a.normal.angle(b_.normal, 0) > math.radians(0.5): continue
        A, Bs = side(a, k), side(b_, k)
        if np.allclose(A[0], Bs[0], atol=1e-6) and np.allclose(A[1], Bs[1], atol=1e-6): continue
        if np.linalg.norm(VL[k[0]] - VL[k[1]]) < SEAM_MIN: short += 1; continue
        for t in (0.2, 0.4, 0.6, 0.8):
            pa = A[0] + (A[1] - A[0]) * t + A[2] * 1.5 / TEX; pb = Bs[0] + (Bs[1] - Bs[0]) * t + Bs[2] * 1.5 / TEX
            ya, xa = int(np.clip(pa[1] * TEX, 0, TEX - 1)), int(np.clip(pa[0] * TEX, 0, TEX - 1))
            yb, xb = int(np.clip(pb[1] * TEX, 0, TEX - 1)), int(np.clip(pb[0] * TEX, 0, TEX - 1))
            samples.append((k, t, ya, xa, yb, xb))
    sm = np.zeros(part.shape, bool)
    for s in samples: sm[s[2], s[3]] = sm[s[4], s[5]] = True
    vis, _ = BF._visible_texels(o, sm)

    def ang(img, ya, xa, yb, xb):
        Fa, Fb = frame_at(ya, xa), frame_at(yb, xb)
        na, nb = img[ya, xa, :3] * 2 - 1, img[yb, xb, :3] * 2 - 1
        wa = na[0] * Fa[0] + na[1] * Fa[1] + na[2] * Fa[2]; wb = nb[0] * Fb[0] + nb[1] * Fb[1] + nb[2] * Fb[2]
        return math.degrees(math.acos(np.clip(wa @ wb / (np.linalg.norm(wa) * np.linalg.norm(wb)), -1, 1)))
    n = hidden = skipped = rel = bad = bad6 = added = 0; worst = worst6 = wadd = 0.0; where = []
    for k, t, ya, xa, yb, xb in samples:
        if not (vis[ya, xa] and vis[yb, xb]) or not (lab[ya, xa] and lab[yb, xb]): hidden += 1; continue
        if near_edge(P[ya, xa]) or near_edge(P[yb, xb]): skipped += 1; continue
        if relief[ya, xa] or relief[yb, xb]: rel += 1; continue
        a1, a6 = ang(nrm, ya, xa, yb, xb), ang(n6, ya, xa, yb, xb)
        n += 1; bad += a1 > max_deg; bad6 += a6 > max_deg; worst = max(worst, a1); worst6 = max(worst6, a6)
        added += a1 - a6 > add_deg; wadd = max(wadd, a1 - a6)
        if a1 - a6 > add_deg:
            print(f"     added {a1 - a6:.1f} deg at {np.round(VL[k[0]] + (VL[k[1]] - VL[k[0]]) * t, 3).tolist()}; albedo / "
                  f"smoothness {look[0][ya, xa].round().astype(int).tolist()} {look[1][ya, xa]:.2f} | "
                  f"{look[0][yb, xb].round().astype(int).tolist()} {look[1][yb, xb]:.2f}")
        if a1 > max_deg: where.append((round(a1, 1), round(a6, 1), np.round(VL[k[0]] + (VL[k[1]] - VL[k[0]]) * t, 3).tolist()))
    ok = added == 0
    for a1, a6, q in sorted(where, reverse=True)[:4]:
        print(f"     seam sample {a1} deg (6g bake alone {a6}) at cradle-local {q}")
    print(f"{'PASS' if ok else 'FAIL'} normal seams {name}: {n} samples on visible coplanar seams; C-T1 adds > {add_deg} deg "
          f"at {added} (max added {wadd:.1f}); over {max_deg} deg: final {bad} (worst {worst:.1f}), 6g bake alone {bad6} "
          f"(worst {worst6:.1f}); skipped {hidden} hidden, {skipped} in the 4 mm edge zone, {rel} on rust / scratch / fastener relief, {short} seam edges < "
          f"{SEAM_MIN * 1e3:.0f} mm")
    return ok


# --------------------------------------------------------------------------- renders


C3 = np.array([[-1, 0, 0], [0, 0, -1], [0, 1, 0]], float)          # spec -> Blender
C4 = np.eye(4); C4[:3, :3] = C3
PIVOT_X, PIVOT_Y, OPEN = 0.385, 0.637, 75.0
# Terminal: built in the cloud (no local .blend; terminal.py imports scipy): its hero-mode FBX files from Assets, each
# at its own pivot, placed at the part origins of HERO_SPEC §5 (terminal-local)
TERM_PARTS = {"Body_01": (0, 0, 0), "Button_01": (0, 1.031, 0.521), "Indicators_01": (0, 0, 0),
              "Beacon_01": (1.02, 1.272, 0.33), "Display_01": (0, 1.10, 0.15)}


def baked_material(name, folder, prefix, emis_strength=1.0, emis_tint=(1, 1, 1)):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; b = GT.NB(nt)
    bsdf = nt.nodes["Principled BSDF"]

    def tex(k, cs):
        img = bpy.data.images.load(os.path.join(folder, f"{prefix}_{k}.png")); img.colorspace_settings.name = cs
        img.alpha_mode = 'CHANNEL_PACKED'
        return b.n("ShaderNodeTexImage", image=img)
    bc = tex("BaseColor", 'sRGB'); nm = tex("Normal", 'Non-Color'); mk = tex("Mask", 'Non-Color'); em = tex("Emission", 'sRGB')
    sep = b.n("ShaderNodeSeparateColor"); b.link(mk.outputs["Color"], sep.inputs[0])
    nmap = b.n("ShaderNodeNormalMap", space='TANGENT'); b.link(nm.outputs["Color"], nmap.inputs["Color"])
    b.link(bc.outputs["Color"], bsdf.inputs["Base Color"]); b.link(sep.outputs[0], bsdf.inputs["Metallic"])
    b.link(b.sub(1.0, mk.outputs["Alpha"]), bsdf.inputs["Roughness"]); b.link(nmap.outputs[0], bsdf.inputs["Normal"])
    b.link(b.mix(1.0, em.outputs["Color"], tuple(emis_tint), 'MULTIPLY'), bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = emis_strength
    return m


def holo_material(path, strength=0.8):
    m = bpy.data.materials.new("M_Holo_Review"); m.use_nodes = True; nt = m.node_tree; b = GT.NB(nt)
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
    img = bpy.data.images.load(path); img.alpha_mode = 'STRAIGHT'
    t = b.n("ShaderNodeTexImage", image=img)
    em = b.n("ShaderNodeEmission"); b.link(t.outputs["Color"], em.inputs["Color"]); em.inputs["Strength"].default_value = strength
    tr = b.n("ShaderNodeBsdfTransparent"); mx = b.n("ShaderNodeMixShader")
    b.link(t.outputs["Alpha"], mx.inputs[0]); b.link(tr.outputs[0], mx.inputs[1]); b.link(em.outputs[0], mx.inputs[2])
    b.link(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def spec_rot_about(p, deg):
    """Blender 4x4 for a Unity rotation of deg about the spec Z axis through spec point p"""
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    R = np.eye(4); R[:2, :2] = [[c, -s], [s, c]]
    Tp = np.eye(4); Tp[:3, 3] = p; Tm = np.eye(4); Tm[:3, 3] = -np.asarray(p)
    return Matrix((C4 @ Tp @ R @ Tm @ C4.T).tolist())


def build_cradle(lows):
    """full cradle from the bake set: Arm_L / Pad_L as mirror copies (spec x -> -x = Blender x -> -x), Pad_L on the riser"""
    sc = bpy.context.scene
    Mx = Matrix.Diagonal((-1, 1, 1, 1))

    def twin(src, name, dz=0.0):
        o = bpy.data.objects.new(name, src.data); sc.collection.objects.link(o)
        o.matrix_world = Matrix.Translation((0, 0, dz)) @ Mx @ src.matrix_world
        return o
    zr = max((lows["Riser"].matrix_world @ v.co).z for v in lows["Riser"].data.vertices)
    zp = min((lows["Pad"].matrix_world @ v.co).z for v in lows["Pad"].data.vertices)
    arm_l = twin(lows["Arm_R"], "Arm_L_review"); pad_l = twin(lows["Pad"], "Pad_L_review", zr - zp)
    groups = {"L": [arm_l, pad_l, lows["Riser"]], "R": [lows["Arm_R"], lows["Pad"]]}
    rest = {o.name: o.matrix_world.copy() for g in groups.values() for o in g}
    return groups, rest


def set_open(groups, rest, deg):
    for side, objs in groups.items():
        sgn = 1 if side == "L" else -1
        M = spec_rot_about((sgn * -PIVOT_X, PIVOT_Y, CZ), sgn * deg)
        for o in objs: o.matrix_world = M @ rest[o.name]
    bpy.context.view_layer.update()


def append_hero(path, names):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in names]
    out = []
    for o in dst.objects:
        if o is None: continue
        bpy.context.scene.collection.objects.link(o); o.hide_render = False; out.append(o)
    return out


def spec_bbox(objs):
    pts = np.array([GT.spec(o.matrix_world @ v.co) for o in objs for v in o.data.vertices])
    return pts.min(0), pts.max(0)


def place(objs, target_x, target_z, turn=False):
    """move a hero group (spec bbox centre) to (target_x, ., target_z), optionally turned 180 deg about spec Y"""
    lo, hi = spec_bbox(objs); c = (lo + hi) / 2
    R = np.eye(4)
    if turn: R[:3, :3] = C3 @ np.diag((-1, 1, -1)) @ C3.T
    Tc = np.eye(4); Tc[:3, 3] = C3 @ np.array((c[0], 0, c[2])); Tm = np.eye(4); Tm[:3, 3] = -Tc[:3, 3]
    Tt = np.eye(4); Tt[:3, 3] = C3 @ np.array((target_x, 0, target_z))
    M = Matrix((Tt @ R @ Tm).tolist())
    for o in objs: o.matrix_world = M @ o.matrix_world
    return spec_bbox(objs)


def lineup(sc_mod):
    """Terminal | Cradle | Gate side by side at the cradle's z, all facing -Z, baked looks (Assets textures)"""
    import gate as G
    root = os.path.join(PROJ, "Assets", "Environment", "Heroes")
    gate = append_hero(G.SAVE, [f"{G.HERO}_{n}" for n in GT.PARTS])
    term = []
    for n, org in TERM_PARTS.items():
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=os.path.join(root, "Terminal", f"LAB_HERO_Terminal_{n}.fbx"))
        for o in [o for o in bpy.data.objects if o not in before]:
            if o.type != 'MESH': bpy.data.objects.remove(o, do_unlink=True); continue
            o.matrix_world = Matrix.Translation(Vector(C3 @ np.array(org, float))) @ o.matrix_world
            o.name = f"LAB_HERO_Terminal_{n}"; term.append(o)
    mg = baked_material("M_Gate_Review", os.path.join(root, "Gate", "Textures"), "T_LAB_HERO_Gate")
    mt = baked_material("M_Term_Review", os.path.join(root, "Terminal", "Textures"), "T_LAB_HERO_Terminal")
    mb = baked_material("M_Term_Beacon", os.path.join(root, "Terminal", "Textures"), "T_LAB_HERO_Terminal", 0.0)
    mi = baked_material("M_Term_Ind", os.path.join(root, "Terminal", "Textures"), "T_LAB_HERO_Terminal", 1.0, GT.CYAN_E)
    for o in gate:
        for i in range(len(o.data.materials)): o.data.materials[i] = mg
    for o in term:
        if o.name.endswith("Display_01"):
            o.data.materials.clear()
            o.data.materials.append(holo_material(os.path.join(root, "Terminal", "Textures", "T_LAB_HERO_Terminal_Holo.png"))); continue
        m = mb if o.name.endswith("Beacon_01") else mi if o.name.endswith("Indicators_01") else mt
        for i in range(len(o.data.materials)): o.data.materials[i] = m
    lo_t, hi_t = spec_bbox(term); lo_g, hi_g = spec_bbox(gate)
    place(term, -1.45 - (hi_t[0] - lo_t[0]) / 2, CZ, turn=True)
    place(gate, 1.45 + (hi_g[0] - lo_g[0]) / 2, CZ + 0.3)
    print(f"INFO lineup: Terminal {np.round(hi_t - lo_t, 2).tolist()} m, Gate group {np.round(hi_g - lo_g, 2).tolist()} m")
    return gate + term


def renders(args):
    """review renders with the baked maps (JPG in Documentation/Media/cradle). args: view names to limit; "fast" """
    import servicearm_check as SC
    lows = open_bake()
    m = baked_material("M_Cradle_Baked", OUT, "T_LAB_HERO_Cradle")
    for o in lows.values():
        o.data.materials.clear(); o.data.materials.append(m)
        o.visible_diffuse = o.visible_glossy = o.visible_shadow = o.visible_transmission = True
    groups, rest = build_cradle(lows)
    fast = "fast" in args; only = set(a for a in args if a != "fast")
    want = lambda k: not only or k in only
    scr = os.path.join(WORK, "renders"); os.makedirs(scr, exist_ok=True); os.makedirs(MEDIA, exist_ok=True)
    SC.scene_setup(size=(1600, 1000), samples=16 if fast else 64, bg=lin((22, 23, 25)), view='Standard')
    sc = bpy.context.scene
    if fast: sc.render.resolution_percentage = 50
    floor = SC.add_box("Floor", -6, 6, -0.05, 0.0, -2, 12, SC.simple_mat("M_Floor", lin((52, 53, 55)), 0.85))
    wall = SC.add_box("Wall", -6, 6, 0, 4.2, 7.0, 7.2, SC.simple_mat("M_Wall", lin((38, 40, 43)), 0.85))
    before = set(bpy.data.objects); SC.add_drone(True); drone = [o for o in bpy.data.objects if o not in before]
    lights = [SC.add_light("Key", (-1.6, 3.6, 2.6), (0.0, 0.9, CZ), 150, 2.5, (0.92, 0.96, 1.0)),
              SC.add_light("Fill", (2.4, 1.6, 2.8), (0.0, 0.8, CZ), 70, 3.0, (0.8, 0.88, 1.0)),
              SC.add_light("Rim", (1.8, 3.2, 7.0), (0.0, 1.0, CZ), 120, 2.0, (1.0, 0.9, 0.8))]
    shots = []

    def shot(k, loc, look, lens=40, ortho=None, show_drone=True):
        if not want(k): return
        for o in drone: o.hide_render = not show_drone
        SC.camera(loc, look, lens, ortho); p = os.path.join(scr, f"{TAG}_{k}.png"); SC.shot(p); shots.append(k)
    z = CZ
    shot("34", (-2.9, 2.3, z - 3.2), (0, 0.85, z), 40, show_drone=False)
    shot("front", (0, 1.0, z - 8), (0, 1.0, z), ortho=3.0, show_drone=False)
    shot("back34", (2.9, 2.2, z + 3.2), (0, 0.8, z), 40, show_drone=False)
    shot("close_pad", (1.05, 2.05, z - 0.75), (0.5, 1.70, z), 45, show_drone=False)
    shot("close_pad_left", (-1.05, 2.1, z - 0.75), (-0.5, 1.72, z), 45, show_drone=False)
    shot("close_hinge", (1.05, 0.55, z - 0.85), (0.40, 0.62, z - 0.10), 45, show_drone=False)
    shot("close_plinth", (-0.95, 0.80, z - 0.75), (-0.41, 0.29, z - 0.29), 45, show_drone=False)
    shot("close_column", (0.28, 0.80, z - 0.95), (0.0, 0.56, z - 0.224), 45, show_drone=False)
    # the plinth-tier corner where the 6g high-poly bake itself has a normal break at a UV seam (seam check info)
    shot("close_plinth_seam", (-1.75, 0.80, z - 1.10), (-1.05, 0.18, z - 0.33), 45, show_drone=False)
    shot("docked_closed", (-1.7, 1.75, z - 2.7), (0.0, 1.15, z), 32)
    if want("docked_open"):
        set_open(groups, rest, OPEN)
        shot("docked_open", (-1.7, 1.75, z - 2.7), (0.0, 1.0, z), 32)
        shot("open_34", (2.6, 2.0, z - 3.0), (0.0, 0.7, z), 35, show_drone=False)
        set_open(groups, rest, 0.0)
    if want("dim"):
        keep = [l.data.energy for l in lights]
        for l in lights: l.data.energy *= 0.35
        shot("dim_facility", (-1.7, 1.75, z - 2.7), (0.0, 1.15, z), 32)
        for l, e in zip(lights, keep): l.data.energy = e
    if want("lineup"):
        others = lineup(SC)
        for o in drone: o.hide_render = True
        SC.camera((0.6, 1.9, z - 9.0), (0.6, 1.05, z), 28); p = os.path.join(scr, f"{TAG}_lineup.png"); SC.shot(p)
        shots.append("lineup")
        for o in others: o.hide_render = True
    for k in shots:
        SC.save_jpg(SC.load_rgb(os.path.join(scr, f"{TAG}_{k}.png")), os.path.join(MEDIA, f"{TAG}_{k}.jpg"))
    for k in shots:
        a = SC.load_rgb(os.path.join(scr, f"{TAG}_{k}.png"))
        white = (a.min(2) > 0.85).sum()
        print(f"INFO render {k}: {int(white)} near-white pixels (all channels > 0.85; specular highlights or a clipping cyan strip)")
    if want("maps"): flat_maps(SC)


def flat_maps(SC):
    os.makedirs(MEDIA, exist_ok=True)
    for k, sub, ch in (("BaseColor", "basecolor", None), ("Normal", "normal", None), ("Mask", "mask_metallic", 0),
                       ("Mask", "mask_ao", 1), ("Mask", "mask_smoothness", 3)):
        a = load_out(FILES[k])
        if ch is not None: a = np.repeat(a[..., ch:ch + 1], 4, 2)
        h = min(TEX, 1024); d = down(a, h)[..., :3]
        lin_ = np.where(d <= 0.04045, d / 12.92, ((d + 0.055) / 1.055) ** 2.4)
        SC.save_jpg(lin_[::-1].astype(np.float32), os.path.join(MEDIA, f"{TAG}_map_{sub}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"bake": bake, "check": check, "renders": renders}[argv[0]](argv[1:])
