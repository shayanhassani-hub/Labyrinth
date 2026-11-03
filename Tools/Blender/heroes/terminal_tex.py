"""
Terminal (Hero 02) textures, hero workflow v3 (ASSET_RULES): procedural Blender materials baked in Cycles onto the
export-identical triangulated low (env_kit_generator.triangulated_export_copy, the hero export function), as for the
Gate (gate_tex.py: its node builder, bake, dilation and check helpers are reused unchanged).

  python (bpy 5.2.2) Tools/Blender/heroes/terminal_tex.py -- bake [reuse]   detail maps, pre-bakes, final bakes, maps
  ... -- check                                   AO black scan, PBR values, normal seams on the Body's flat faces
  ... -- renders [views] [fast]                  review renders with the BAKED maps (+ the holo screen texture)
  TERMINAL_TEX=512 runs bake / check / renders at 512 in their own folders (cheap look iterations)

Pipeline (bake), per texel of the one 2048 set (Body, Button, Indicators, Beacon; the Display has its own holo
texture, terminal_holo.py):
 1. texel maps: part, material slot, face zone (terminal.py: recess floor / walls, beacon cage), Unity position and
    face normal, rasterised from the triangulated lows.
 2. detail maps (numpy; positions from terminal.py's layout functions): bolts (hex heads + washers: plate, panel and
    desk-panel corners, pillar tops, top chamfers, display bar), grooves (desk panel frame with 45 deg cut ends and
    four dividers, the pillar cap seam), hazard stripes (45 deg, 85 mm pitch, across the outer chamfers) and their
    worn edges, the steel cup ring under the button, rust blotches (bolts, panel corners, plinth / body corners) and
    run-off streaks.
 3. pre-bakes per part (others hidden): convex edges (AO inside, 8 mm), cavity (AO 50 mm), AO (0.3 m, self only).
 4. final bakes from the procedural materials (STYLE_GUIDE palette and wear, rust rule): BaseColor, Normal (OpenGL),
    Smoothness, Metallic, Emission; margin 0, one 8 px dilation. Mask = R metallic, G AO, A smoothness (linear).
Switching parts: the Indicators' strips and the Beacon lens carry WHITE emission texels; at runtime a
MaterialPropertyBlock sets _EmissionColor (cyan / red / black). The Body's cyan strips carry STYLE_GUIDE cyan.
Outputs: D:/AI_Labyrinth/Blender/Export/Heroes/Terminal/T_LAB_HERO_Terminal_{BaseColor,Normal,Mask,Emission}.png,
copied to Assets/Environment/Heroes/Terminal/Textures/ (Git LFS) at 2048. Never saves the .blend.
"""
import bpy
import math
import os
import shutil
import sys
import time
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import terminal as TM                                    # noqa: E402
import gate_tex as GT                                    # noqa: E402  NB, bake / dilate / save / check helpers
import env_kit_generator as K                            # noqa: E402

PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TEX = int(os.environ.get("TERMINAL_TEX", "2048"))
_SFX = "" if TEX == 2048 else f"_{TEX}"
WORK = os.path.abspath("D:/AI_Labyrinth/Blender/Work/Terminal/tex" + _SFX)
OUT = os.path.abspath("D:/AI_Labyrinth/Blender/Export/Heroes/Terminal" + _SFX)
RENDERS = os.path.abspath(os.environ.get("TERMINAL_RENDERS", "D:/AI_Labyrinth/Renders/Terminal"))
ASSET_TEX = os.path.join(PROJ, "Assets", "Environment", "Heroes", "Terminal", "Textures")
HOLO = os.path.join(ASSET_TEX, "T_LAB_HERO_Terminal_Holo.png")
PARTS = ["Body_01", "Button_01", "Indicators_01", "Beacon_01"]
TAG = "h2"
H_LO, H_HI = -0.002, 0.005
BAKE_SAMPLES = dict(prebake=64, emit=4, normal=32)
RNG = np.random.default_rng(31)
GT.TEX = TEX                                             # GT helpers read their module TEX (normal seams, new_image)

lin = GT.lin
PAINT_C, POLY_C, STEEL_C = lin((90, 104, 115)), lin((35, 37, 39)), lin((188, 190, 192))
OCHRE_C, BLACK_C, RUST_C, GRIME_C = lin((159, 120, 58)), lin((35, 37, 39)), lin((120, 62, 34)), lin((44, 41, 37))
RUST_DARK, RUST_EDGE = lin((66, 44, 34)), lin((112, 64, 38))
CYAN_E, CYAN_OFF = lin((70, 170, 255)), lin((30, 45, 55))
RED_E = lin((230, 35, 25))
REDCAP_C = lin((168, 40, 30))                            # arming button cap: red polymer (HERO_SPEC exception)
LENS_C = lin((96, 20, 16))                               # beacon lens, off: dark red glass
RECESS_SHADE = 0.72                                      # recess floors / walls: gunmetal x 0.72 (linear), concept depth
CAGE_SHADE = 0.55
SLOTS = TM.MATS
PAINT, POLYMER, STEEL, HAZARD, CYAN, SWITCH, REDCAP, LENS = range(8)


def local(P):
    return P - np.array((TM.OX, 0.0, TM.OZ), np.float32)


# --------------------------------------------------------------------------- scene, lows, texel maps


def open_lows():
    bpy.ops.wm.open_mainfile(filepath=TM.SAVE)
    objs = {n: bpy.data.objects[f"{TM.HERO}_{n}"] for n in PARTS}
    lows = {}
    for n, o in objs.items():
        c = K.triangulated_export_copy(o)
        c.matrix_world = o.matrix_world.copy(); c.name = f"{n}_bakelow"
        lows[n] = c
        o.hide_render = True; o.hide_set(True)
    disp = bpy.data.objects.get(f"{TM.HERO}_Display_01")
    if disp: disp.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.light_settings.distance = 0.3
    return objs, lows


def texel_maps(lows):
    part = np.zeros((TEX, TEX), np.int8); mat = np.full((TEX, TEX), -1, np.int8); zone = np.zeros((TEX, TEX), np.int8)
    P = np.zeros((TEX, TEX, 3), np.float32); N = np.zeros((TEX, TEX, 3), np.float32)
    for pi, (name, o) in enumerate(lows.items(), 1):
        me = o.data; W = o.matrix_world; uv = me.uv_layers.active.data; me.calc_loop_triangles()
        V = np.array([GT.spec(W @ v.co) for v in me.vertices]); R = W.to_3x3()
        zl = me.attributes["zone"].data if "zone" in me.attributes else None
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
            N[ys[m], xs[m]] = GT.spec((R @ t.normal).normalized())
            part[ys[m], xs[m]] = pi; mat[ys[m], xs[m]] = me.polygons[t.polygon_index].material_index
            if zl is not None: zone[ys[m], xs[m]] = zl[t.polygon_index].value
    return part, mat, zone, P, N


# --------------------------------------------------------------------------- detail maps


def corners(poly, inset, lo=75.0, hi=105.0):
    """convex corners of a CCW polygon (u, v) with an angle in [lo, hi], moved inside by inset"""
    ins = TM.offset(poly, inset); n = len(ins); out = []
    for i in range(n):
        a, b, c = np.array(ins[i - 1]), np.array(ins[i]), np.array(ins[(i + 1) % n])
        u1, u2 = a - b, c - b
        ang = math.degrees(math.acos(np.clip(u1 @ u2 / (np.linalg.norm(u1) * np.linalg.norm(u2)), -1, 1)))
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if lo <= ang <= hi and cr > 0: out.append(tuple(b))
    return out


DESK_FRAME_IN, DESK_CUT = 0.045, 0.06
GROOVE_W, GROOVE_D = 0.0024, 0.0012               # groove profile half-width (~2.5 px at 512 px/m), depth
DESK_DIV = (-0.663, -0.203, 0.203, 0.663)


def desk_frame_poly():
    u0, u1 = -TM.PIL_IN + DESK_FRAME_IN, TM.PIL_IN - DESK_FRAME_IN
    s0, s1 = TM.CH + DESK_FRAME_IN, TM.SLOPE_L - DESK_FRAME_IN
    c = DESK_CUT
    return [(u0 + c, s0), (u1 - c, s0), (u1, s0 + c), (u1, s1 - c), (u1 - c, s1), (u0 + c, s1), (u0, s1 - c), (u0, s0 + c)]


def bolts():
    """[(centre (Unity), normal, hex apothem, washer radius, part index)]"""
    out = []
    W = lambda p: np.array(p, float)
    for sx in (1, -1):
        fs = TM.hull_faces(TM.pillar_halfspaces(), (1.05, 0.7, 0.4))
        fr = TM.front_frame(sx); lay = TM.front_layout(fs["front"])
        d_plate = 0.018 - 0.012
        for u, v in corners(TM.offset(lay["plate"], 0.003), 0.020):
            out.append((W(fr.p(u, v, d_plate)), fr.n, 0.0075, 0.0105, 1))
        f = lay["field"]; vt = lay["top_y"] - 0.028
        for u in (f[0][0] + 0.012, f[1][0] - 0.012):                          # cap band above the field
            out.append((W(fr.p(u, vt, 0.0)), fr.n, 0.0075, 0.0105, 1))
        fo = TM.outer_frame(sx); lo = TM.outer_layout(fs["outer"])
        for pnl, keep in zip(lo["panels"], ("top", None, "bottom")):
            if keep is None: continue
            cs = corners(TM.offset(pnl, 0.003), 0.020)
            vs = [c[1] for c in cs]
            sel = [c for c in cs if (c[1] > np.mean(vs)) == (keep == "top")]
            for u, v in sel: out.append((W(fo.p(u, v, 0.008)), fo.n, 0.0075, 0.0105, 1))
        for u, v in corners(lo["field"], -0.015):                             # frame band corners
            out.append((W(fo.p(u, v, 0.0)), fo.n, 0.0075, 0.0105, 1))
        for x, z in ((1.0, 0.035), (1.10, 0.035), (0.96, 0.60), (1.14, 0.60)):  # pillar top
            if sx > 0 and math.hypot(x - TM.BEACON["x"], z - TM.BEACON["z"]) < 0.09: continue
            out.append((W(TM.T((x, TM.PIL_H, z), sx)), np.array((0, 1, 0.0)), 0.008, 0.0115, 1))
        tf = TM.PIL_TF                                                        # top-front chamfer, mid-height
        for x in (0.975, 1.125):
            out.append((W(TM.T((x, TM.PIL_H - tf / 2, TM.DEPTH - tf / 2), sx)), np.array((0, 1, 1.0)) / math.sqrt(2), 0.008, 0.0115, 1))
    dfr = TM.desk_frame()
    fp = desk_frame_poly(); s0, s1 = fp[0][1], fp[4][1]
    edges = [fp[6][0]] + list(DESK_DIV) + [fp[2][0]]
    for i, (a, b) in enumerate(zip(edges, edges[1:])):
        for u in (a + 0.024, b - 0.024):
            if (i == 0 and u < a + 0.03) or (i == 4 and u > b - 0.03): continue  # end panels: inner corners only
            for s in (s0 + 0.024, s1 - 0.024):
                out.append((W(dfr.p(u, s, 0.0)), dfr.n, 0.0075, 0.0105, 1))
    lfr = TM.lower_frame()
    for f in TM.lower_layout():
        for pnl, keep in zip(f["panels"], ("top", "bottom")):
            cs = corners(TM.offset(pnl, 0.003), 0.020)
            vs = [c[1] for c in cs]
            for u, v in [c for c in cs if (c[1] > np.mean(vs)) == (keep == "top")]:
                out.append((W(lfr.p(u, v, 0.008)), lfr.n, 0.0075, 0.0105, 1))
    for x in (-0.77, 0.77):                                                   # display bar ends
        out.append((W(TM.T((x, TM.BAR["y1"], (TM.BAR["z0"] + TM.BAR["z1"]) / 2))), np.array((0, 1, 0.0)), 0.007, 0.010, 1))
    return out


def seg_dist(pts, poly, closed=True):
    d = np.full(len(pts), np.inf)
    n = len(poly)
    for i in range(n if closed else n - 1):
        a, b = np.array(poly[i]), np.array(poly[(i + 1) % n])
        ab = b - a; t = np.clip(((pts - a) @ ab) / (ab @ ab), 0, 1)
        d = np.minimum(d, np.linalg.norm(pts - (a + t[:, None] * ab), axis=1))
    return d


def details(part, mat, zone, P, N):
    H = np.zeros((TEX, TEX), np.float32); BOLT = np.zeros_like(H); STREAK = np.zeros_like(H); GROOVE = np.zeros_like(H)
    RUSTB = np.zeros_like(H); BANDE = np.zeros_like(H); STRIPE = np.zeros_like(H); CUP = np.zeros_like(H)
    PL = local(P)
    body = part == 1
    streaks = []
    bl = bolts()
    for c, n, a, w, pi in bl:
        n = np.asarray(n, float); n /= np.linalg.norm(n)
        m = (part == pi) & (np.abs((P - c) @ n) < 0.003) & ((N @ n) > 0.95)
        ys, xs = np.nonzero(m & (np.linalg.norm(P - c, axis=2) < w + 0.02))
        if not len(ys): continue
        up = np.array((0.0, 1.0, 0.0)); up = up - n * (up @ n)
        if np.linalg.norm(up) < 1e-6: up = np.array((0.0, 0.0, -1.0))
        up /= np.linalg.norm(up); rt = np.cross(up, n)
        d = P[ys, xs] - c; x, y = d @ rt, d @ up
        th = RNG.uniform(0, math.pi / 3); xr, yr = x * math.cos(th) - y * math.sin(th), x * math.sin(th) + y * math.cos(th)
        r = np.hypot(x, y); dh = np.maximum(np.abs(yr), 0.866 * np.abs(xr) + 0.5 * np.abs(yr))
        washer = np.clip((w - r) / 0.0007, 0, 1); head = np.clip((a - dh) / 0.0012, 0, 1)
        H[ys, xs] = np.maximum(H[ys, xs], 0.0010 * washer + 0.0035 * head)
        BOLT[ys, xs] = np.maximum(BOLT[ys, xs], washer)
        ring = RNG.choice((0.0, 0.45, 0.75, 1.0), p=(0.4, 0.2, 0.2, 0.2))
        reach = RNG.uniform(0.010, 0.024); off = RNG.normal(0, 0.25, 2) * w
        x2, y2 = x - off[0], y - off[1]; r2 = np.hypot(x2, y2) * GT.wobble(np.arctan2(y2, x2), RNG, 0.6)
        RUSTB[ys, xs] = np.maximum(RUSTB[ys, xs], ring * np.clip(1 - np.maximum(r2 - w, 0) / reach, 0, 1) * (r > 0.8 * w))
        if abs(n[1]) < 0.3 and ring > 0.5 and RNG.random() < 0.6: streaks.append((pi, c - up * w * 0.8, n, up))
    # grooves: desk panel frame + dividers; pillar cap seam (front-facing pillar faces)
    dfr = TM.desk_frame(); dn = np.array(dfr.n); da = np.array(dfr.a); db = np.array(dfr.b); do = np.array(dfr.o)
    on_desk = body & (np.abs((P - do) @ dn) < 0.0006) & ((N @ dn) > 0.99)
    ys, xs = np.nonzero(on_desk)
    uv = np.column_stack(((P[ys, xs] - do) @ da, (P[ys, xs] - do) @ db))
    fp = desk_frame_poly(); s0, s1 = fp[0][1], fp[4][1]
    dist = seg_dist(uv, fp)
    for u in DESK_DIV: dist = np.minimum(dist, seg_dist(uv, [(u, s0), (u, s1)], closed=False))
    H[ys, xs] -= GROOVE_D * np.clip(1 - (dist / GROOVE_W) ** 2, 0, 1)
    GROOVE[ys, xs] = np.maximum(GROOVE[ys, xs], np.clip(1 - dist / 0.004, 0, 1))
    for u, v in [q for q in fp if q[1] < 0.2]:                               # streaks from the front frame corners
        if RNG.random() < 0.5: streaks.append((1, np.array(dfr.p(u, v)), dn, -db))
    fs = TM.hull_faces(TM.pillar_halfspaces(), (1.05, 0.7, 0.4))
    yseam = TM.front_layout(fs["front"])["top_y"] - 0.028 - 0.016
    cap = body & (np.abs(PL[..., 0]) > TM.PIL_IN - 1e-3) & (N[..., 2] > 0.5) & (np.abs(PL[..., 1] - yseam) < GROOVE_W)
    ys, xs = np.nonzero(cap)
    dd = np.abs(PL[ys, xs, 1] - yseam)
    H[ys, xs] -= GROOVE_D * np.clip(1 - (dd / GROOVE_W) ** 2, 0, 1); GROOVE[ys, xs] = np.maximum(GROOVE[ys, xs], np.clip(1 - dd / 0.004, 0, 1))
    # hazard stripes and worn band edges (outer vertical chamfers): across = position over the 40 mm chamfer
    hz = mat == HAZARD
    ys, xs = np.nonzero(hz)
    ax = np.abs(PL[ys, xs, 0]); yy = PL[ys, xs, 1]
    t = np.clip((ax - (TM.HALF_W - TM.PIL_OF)) / TM.PIL_OF, 0, 1)
    across = t * TM.PIL_OF * math.sqrt(2)
    STRIPE[ys, xs] = (np.mod((yy + across) / 0.085, 1.0) > 0.5).astype(np.float32)
    de = np.minimum(np.minimum(across, TM.PIL_OF * math.sqrt(2) - across), np.minimum(yy - TM.HAZ_Y[0], TM.HAZ_Y[1] - yy))
    BANDE[ys, xs] = np.clip(1 - de / 0.010, 0, 1)
    # steel cup ring under the button (flange plane, r < guard inner radius)
    g = TM.GUARD; bc = np.array(dfr.p(*TM.BUTTON_US, -g["flange_h"]))
    ys, xs = np.nonzero(body & (np.abs((P - bc) @ dn) < 0.0006))
    r = np.linalg.norm((P[ys, xs] - bc) - np.outer((P[ys, xs] - bc) @ dn, dn), axis=1)
    CUP[ys, xs] = (r < g["inner"] + 0.0005).astype(np.float32)
    # rust blotches: plinth and body corners at the floor, pillar front bottom corners, desk front corners
    spots = []
    for sx in (1, -1):
        spots += [((sx * x, y, z), R) for (x, y, z), R in (((1.19, 0.03, 0.78), 0.10), ((0.93, 0.03, 0.78), 0.07),
                                                            ((1.19, 0.20, 0.79), 0.06), ((0.90, 0.88, 0.75), 0.05),
                                                            ((1.19, 1.20, 0.70), 0.05))]
    spots += [((x, 0.02, 0.64), 0.07) for x in (-0.88, -0.30, 0.30, 0.88)]
    for c, R0 in spots:
        if RNG.random() < 0.25: continue
        c = np.array(c); R = R0 * RNG.uniform(0.8, 1.3)
        dd = PL - c; m = body & (np.linalg.norm(dd, axis=2) < 2.2 * R)
        ys, xs = np.nonzero(m)
        q = dd[ys, xs]; ang = np.arctan2(q[:, 1], q[:, 0] + q[:, 2])
        rr = np.linalg.norm(q, axis=1) * GT.wobble(ang, RNG, 0.9)
        RUSTB[ys, xs] = np.maximum(RUSTB[ys, xs], np.clip(1 - rr / R, 0, 1) ** 0.7)
    for pi, s, n, up in streaks:                                              # run-off streaks
        L = RNG.uniform(0.06, 0.26); wd = RNG.uniform(0.003, 0.007)
        m = (part == pi) & (np.abs((P - s) @ n) < 0.003) & ((N @ n) > 0.95)
        rt = np.cross(up, n); d = P - s; x, y = d @ rt, -(d @ up)
        sel = m & (y > 0) & (y < L) & (np.abs(x) < 3 * wd)
        ys, xs = np.nonzero(sel)
        tt = y[ys, xs] / L; ww = wd * (1 + 1.5 * tt)
        STREAK[ys, xs] = np.maximum(STREAK[ys, xs], np.clip(1 - np.abs(x[ys, xs]) / ww, 0, 1) * (1 - tt) ** 1.5)
    REC = (zone == TM.Z_RECESS).astype(np.float32); CAGE = (zone == TM.Z_CAGE).astype(np.float32)
    Hn = (np.clip(H, H_LO, H_HI) - H_LO) / (H_HI - H_LO)
    print(f"INFO details: {len(bl)} bolts, {len(streaks)} rust streaks, hazard texels {int(hz.sum())}, cup texels "
          f"{int(CUP.sum())}, recess texels {int(REC.sum())}")
    return np.stack([Hn, BOLT, STREAK, GROOVE], 2), RUSTB, BANDE, np.stack([STRIPE, REC, CUP, CAGE], 2)


# --------------------------------------------------------------------------- procedural materials


def surface_material(slot, d1, d2, d3):
    name = SLOTS[slot][0] + "_Tex"
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
    def img(i):
        t = b.n("ShaderNodeTexImage", image=i, interpolation='Linear'); sp = b.n("ShaderNodeSeparateColor")
        b.link(t.outputs["Color"], sp.inputs[0]); return sp.outputs, t.outputs["Alpha"]
    (o1, GR), (o2, BE), (o3, CAGE) = img(d1), img(d2), img(d3)
    Hn, BO, ST = o1[0], o1[1], o1[2]
    E, C, RB = o2[0], o2[1], o2[2]
    STR, REC, CUP = o3[0], o3[1], o3[2]
    nf = b.noise(obj, 90.0, 6.0); nw = b.noise(obj, 2.5, 4.0); nr = b.noise(obj, 22.0, 10.0, 0.65); nr2 = b.noise(obj, 140.0, 4.0)
    def hairlines(rot, scale, stretch, width, dens, lo, hi, seed, axis=1):
        mp = b.n("ShaderNodeMapping"); b.link(obj, mp.inputs[0])
        sc_ = [1.0, 1.0, 1.0]; sc_[2] = stretch
        mp.inputs["Scale"].default_value = sc_; rr = [0.0, 0.0, 0.0]; rr[axis] = math.radians(rot)
        mp.inputs["Rotation"].default_value = rr; mp.inputs["Location"].default_value = (seed, 0.37 * seed, 0.11 * seed)
        t = b.n("ShaderNodeTexNoise"); b.link(mp.outputs[0], t.inputs["Vector"])
        t.inputs["Scale"].default_value = scale; t.inputs["Detail"].default_value = 1.5; t.inputs["Roughness"].default_value = 0.4
        ln = b.remap(b.math('ABSOLUTE', b.sub(t.outputs["Fac"], 0.5)), 0.0, width, 1.0, 0.0)
        return b.mul(ln, b.remap(b.noise(obj, dens, 2.0), lo, hi))
    scratch = b.math('MAXIMUM', hairlines(0, 1.6, 70.0, 0.0080, 1.2, 0.46, 0.56, 0.0),
                     hairlines(28, 1.4, 70.0, 0.0050, 1.4, 0.50, 0.60, 3.1))
    scratch = b.math('MAXIMUM', scratch, hairlines(-35, 1.3, 70.0, 0.0050, 1.3, 0.53, 0.62, 7.7, 0))
    sy = pos.outputs[2]
    grime = b.clamp(b.add(b.mul(b.sub(1.0, C), 1.4), b.mul(b.remap(sy, 0.0, 0.8, 0.7, 0.0), nw), b.mul(GR, 0.5)))
    kind = {PAINT: "paint", HAZARD: "paint", POLYMER: "polymer", STEEL: "steel", CYAN: "light", SWITCH: "light",
            REDCAP: "redcap", LENS: "lens"}[slot]
    if kind == "paint":
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.88 * c for c in PAINT_C)), b.rgb(tuple(1.12 * c for c in PAINT_C)))
        base = b.mix(b.mul(b.remap(nw, 0.35, 0.65), 0.5), base, b.rgb(tuple(0.8 * c for c in PAINT_C)))
        base = b.mix(REC, base, (RECESS_SHADE,) * 3, 'MULTIPLY')                 # recess floors / walls darker
        base = b.mix(CAGE, base, (CAGE_SHADE,) * 3, 'MULTIPLY')
        if slot == HAZARD:
            ochre = b.mix(b.remap(nw, 0.3, 0.7), b.rgb(tuple(0.85 * c for c in OCHRE_C)), b.rgb(tuple(1.08 * c for c in OCHRE_C)))
            hz = b.mix(STR, b.rgb(BLACK_C), ochre)
            chip = b.clamp(b.add(b.remap(b.add(b.mul(BE, 1.5), b.mul(b.sub(nr, 0.5), 1.2)), 0.26, 0.46),
                                 b.remap(b.add(b.mul(scratch, 0.8), b.mul(b.sub(nr, 0.5), 0.8)), 0.55, 0.7)))
            base = b.mix(chip, hz, base)
        sect = b.remap(b.noise(obj, 12.0, 3.0), 0.48, 0.62)
        wear = b.remap(b.add(b.mul(E, b.add(0.5, b.mul(sect, 0.9))), b.mul(b.sub(nr, 0.5), 0.7), b.mul(scratch, 0.25)), 0.63, 0.73)
        hb = b.remap(sy, 0.0, 0.7, 0.12, 0.0)                                   # more towards the floor
        bot = b.mul(b.remap(sy, 0.01, 0.18, 0.45, 0.0), b.remap(b.noise(obj, 4.5, 3.0), 0.48, 0.66))   # patchy, no band
        er = b.mul(E, b.remap(b.noise(obj, 9.0, 4.0), 0.44, 0.62))
        spk = b.mul(b.remap(b.noise(obj, 28.0, 6.0, 0.6), 0.60, 0.70), b.remap(b.noise(obj, 2.2, 2.0), 0.35, 0.55))
        pat = b.remap(b.noise(obj, 3.2, 5.0, 0.6), 0.54, 0.70)
        rv = b.add(b.mul(RB, 0.95), b.mul(er, 1.7), hb, bot, b.mul(spk, 1.0), b.mul(pat, 0.6),
                   b.mul(b.sub(nr, 0.5), 1.1), b.mul(b.sub(nr2, 0.5), 0.3))
        if slot == HAZARD: rv = b.add(rv, b.mul(b.remap(b.noise(obj, 6.0, 4.0), 0.4, 0.7), 0.3))
        near = b.clamp(b.add(b.remap(b.sub(1.0, C), 0.04, 0.25), b.remap(E, 0.10, 0.40), GR, b.mul(RB, 2.0),
                             b.mul(b.remap(sy, 0.0, 0.25, 1.0, 0.0), b.remap(b.noise(obj, 3.0, 3.0), 0.40, 0.60))))
        rust = b.clamp(b.add(b.mul(b.remap(rv, 0.345, 0.465), near), b.mul(ST, b.remap(nf, 0.2, 0.6, 0.55, 1.0))))
        rust = b.mul(rust, b.sub(1.0, CUP))
        col = b.mix(b.mul(scratch, 0.6), base, (1.9, 1.9, 1.9), 'MULTIPLY')
        col = b.mix(wear, col, b.rgb(STEEL_C))
        tip = b.mul(b.mul(b.mul(BO, b.remap(Hn, 0.86, 0.93)), b.remap(nr2, 0.60, 0.72)), b.remap(nr, 0.35, 0.55))
        col = b.mix(tip, col, b.rgb(STEEL_C))
        col = b.mix(CUP, col, b.rgb(STEEL_C))                                    # steel cup ring under the button
        rcol = b.mix(b.remap(rv, 0.62, 0.95), b.rgb(RUST_EDGE), b.rgb(RUST_DARK))
        rcol = b.mix(b.mul(b.remap(nr2, 0.3, 0.8), 0.35), rcol, b.rgb(tuple(0.85 * c for c in RUST_C)))
        col = b.mix(rust, col, rcol)
        bare = b.clamp(b.add(b.mul(b.math('MAXIMUM', wear, tip), b.sub(1.0, rust)), CUP))
        col = b.mix(b.mul(b.mul(grime, 0.7), b.sub(1.0, bare)), col, b.rgb(GRIME_C))      # grime spares bare steel
        metal = bare
        rough = b.add(0.58, b.mul(b.sub(nw, 0.5), 0.35), b.mul(scratch, -0.25))
        rough = b.mixf(bare, rough, b.add(0.58, b.mul(b.sub(nf, 0.5), 0.1), b.mul(grime, 0.25)))
        rough = b.mixf(rust, rough, b.add(0.85, b.mul(b.sub(nr2, 0.5), 0.1)))
        rough = b.add(rough, b.mul(grime, 0.12))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.03), b.mul(rust, b.mul(b.sub(nr2, 0.5), 0.04)), b.mul(scratch, -0.015))
    elif kind in ("polymer", "redcap"):
        pc = POLY_C if kind == "polymer" else REDCAP_C
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.9 * c for c in pc)), b.rgb(tuple(1.1 * c for c in pc)))
        wear = b.remap(b.add(b.mul(E, 1.1), b.mul(b.sub(nr, 0.5), 0.9)), 0.55, 0.8)
        col = b.mix(wear, base, b.rgb(tuple(min(1.0, (1.8 if kind == "polymer" else 1.35) * c) for c in pc)))
        col = b.mix(b.mul(grime, 0.6 if kind == "polymer" else 0.35), col, b.rgb(GRIME_C))
        metal = b.val(0.0)
        r0 = 0.64 if kind == "polymer" else 0.50
        rough = b.add(r0, b.mul(b.sub(nw, 0.5), 0.2), b.mul(wear, 0.1), b.mul(grime, 0.08))
        emis = b.rgb((0, 0, 0))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.02))
    elif kind == "steel":
        col = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.95 * c for c in STEEL_C)), b.rgb(tuple(1.04 * c for c in STEEL_C)))
        metal = b.val(1.0); rough = b.add(0.45, b.mul(b.sub(nw, 0.5), 0.2)); emis = b.rgb((0, 0, 0)); hgt = Hn
    elif kind == "lens":
        col = b.rgb(LENS_C); metal = b.val(0.0); rough = b.add(0.12, b.mul(b.sub(nw, 0.5), 0.06))
        emis = b.rgb((1.0, 1.0, 1.0)); hgt = Hn                                  # white: the runtime sets the colour
    else:
        sw = slot == SWITCH
        col = b.rgb(CYAN_OFF); metal = b.val(0.0)
        rough = b.add(0.35, b.mul(b.sub(nw, 0.5), 0.1))
        emis = b.rgb((1.0, 1.0, 1.0) if sw else CYAN_E)
        hgt = Hn
    bev = b.n("ShaderNodeBevel", samples=16); bev.inputs["Radius"].default_value = 0.0015
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


# --------------------------------------------------------------------------- bake


def maps_names():
    return {k: f"T_LAB_HERO_Terminal_{k}.png" for k in ("BaseColor", "Normal", "Mask", "Emission")}


def bake(args):
    os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    objs, lows = open_lows()
    part, mat, zone, P, N = texel_maps(lows)
    np.savez_compressed(os.path.join(WORK, "texels.npz"), part=part, mat=mat, zone=zone, P=P, N=N)
    cover = part > 0
    d1, rustb, bande, d3 = details(part, mat, zone, P, N)
    res = {}
    prev = os.path.join(WORK, "prebakes.npz")
    old = dict(np.load(prev)) if "reuse" in args and os.path.exists(prev) else {}
    for kind in ("edge", "cavity", "ao"):
        if kind in old: res[kind] = old[kind]; print(f"INFO {kind}: reused"); continue
        pm = GT.prebake_material("cavity" if kind == "ao" else kind); keep = GT.swap_materials(lows, lambda i: pm)
        img = GT.new_image(f"pre_{kind}", size=TEX)
        GT.run_bake(lows, kind, img, "AO" if kind == "ao" else "EMIT", BAKE_SAMPLES["prebake"]); GT.restore(lows, keep)
        res[kind] = GT.pixels(img)[..., 0]
    np.savez_compressed(prev, **res)
    edge = np.clip(GT.blur_masked(res["edge"], cover, 1) * GT.EDGE_GAIN, 0, 1)
    cav = GT.blur_masked(res["cavity"], cover, 1)
    # detail inputs dilated 6 px past the island borders: the bump node reads neighbouring texels, so a groove or bolt
    # that crosses a UV seam would otherwise bend the normal at the island edge
    d2 = np.stack([edge, cav, rustb, bande], 2)
    d1, d2, d3 = (GT.dilate(a, cover, 6) for a in (d1, d2, d3))
    D1 = GT.new_image("D1", d1, TEX); D2 = GT.new_image("D2", d2, TEX); D3 = GT.new_image("D3", d3, TEX)
    mats = [surface_material(s, D1, D2, D3) for s in range(len(SLOTS))]
    keep = GT.swap_materials(lows, lambda i: mats[i][0])
    maps = {}
    for ch, kind, smp in (("base", "EMIT", "emit"), ("rough", "EMIT", "emit"), ("metal", "EMIT", "emit"),
                          ("emis", "EMIT", "emit"), ("normal", "NORMAL", "normal")):
        for m, socks in mats: GT.set_channel(m, socks, ch)
        img = GT.new_image(f"bake_{ch}", size=TEX); GT.run_bake(lows, ch, img, kind, BAKE_SAMPLES[smp])
        maps[ch] = GT.pixels(img)
    GT.restore(lows, keep)
    D = {k: GT.dilate(v, cover) for k, v in maps.items()}
    ao = GT.dilate(np.repeat(res["ao"][..., None], 4, 2), cover)[..., 0]
    one = np.ones((TEX, TEX, 1))
    base = np.concatenate([GT.to_srgb(D["base"][..., :3]), one], 2)
    nrm = np.concatenate([D["normal"][..., :3], one], 2)
    mask = np.stack([D["metal"][..., 0], ao, np.zeros((TEX, TEX)), 1 - D["rough"][..., 0]], 2)
    emis = np.concatenate([GT.to_srgb(D["emis"][..., :3]), one], 2)
    nm = maps_names()
    for arr, k in ((base, "BaseColor"), (nrm, "Normal"), (mask, "Mask"), (emis, "Emission")):
        GT.save_png(arr, nm[k], OUT)
    np.savez_compressed(os.path.join(WORK, "maps.npz"), cover=cover, metal=D["metal"][..., 0], rough=D["rough"][..., 0], ao=ao)
    if TEX == 2048:
        os.makedirs(ASSET_TEX, exist_ok=True)
        for k, fn in nm.items(): shutil.copyfile(os.path.join(OUT, fn), os.path.join(ASSET_TEX, fn))
        print(f"COPIED maps to {os.path.relpath(ASSET_TEX, PROJ)}")
    print(f"INFO bake total {time.time() - t0:.0f} s")


# --------------------------------------------------------------------------- checks


def load_png(fn):
    img = bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = 'Non-Color'
    return GT.pixels(img)


def check(args):
    objs, lows = open_lows()
    tx = np.load(os.path.join(WORK, "texels.npz")); part, matix, zone = tx["part"], tx["mat"], tx["zone"]
    cover = part > 0; nm = maps_names()
    base = load_png(nm["BaseColor"]); mask = load_png(nm["Mask"]); emis = load_png(nm["Emission"]); nrm = load_png(nm["Normal"])
    ok_all = True
    ao = mask[..., 1]
    for pi, name in enumerate(PARTS, 1):
        dark = (part == pi) & (ao < GT.AO_BLACK)
        pcs = GT.components(dark) if dark.sum() < 200000 else []
        patches = [c for c in pcs if len(c) / (np.ptp(c, 0).max() + 1) > GT.LINE_MAX]
        # accepted: deep narrow crevices by design - the 4 mm gaps beside the pillar light strips and the 8 mm gaps
        # beside the desk strips (polymer slot and strip walls, 15 mm deep), seen only straight into the gap
        acc = [c for c in patches if (matix[c[:, 0], c[:, 1]] == POLYMER).mean() > 0.9]
        patches = [c for c in patches if not any(c is a for a in acc)]
        ok = not patches; ok_all &= ok
        where = ""
        if patches:
            big = max(patches, key=len); where = f" (largest {len(big)} texels at {tuple(np.round(local(tx['P'][big[:, 0], big[:, 1]].mean(0)), 3))} local)"
        print(f"{'PASS' if ok else 'FAIL'} AO black {name}: {int(dark.sum())} texels AO < {GT.AO_BLACK}, "
              f"{len(pcs) - len(patches) - len(acc)} contact lines, {len(acc)} accepted crevices "
              f"({sum(len(c) for c in acc)} texels), {len(patches)} patches{where}")
    srgb = base[..., :3] * 255; met = mask[..., 0]
    light = np.isin(matix, (CYAN, SWITCH, LENS))
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
    print(f"INFO metallic: {f(metal, cover):.2f} % metal, {f(trans, cover):.2f} % transitions 0.1-0.9")
    for s, (nme, _) in enumerate(SLOTS):
        sel = cover & (matix == s)
        if sel.any():
            print(f"INFO {nme}: albedo sRGB median {tuple(np.median(srgb[sel], 0).round().astype(int))}, smoothness median "
                  f"{np.median(mask[..., 3][sel]):.2f}, metallic mean {met[sel].mean():.2f}, emission max channel "
                  f"{int(emis[..., :3][sel].max() * 255)}")
    # rust coverage on the paint (texels whose albedo is rust-coloured and non-metal)
    paint = cover & (matix == PAINT) & (part == 1)
    r, g, bb = srgb[..., 0], srgb[..., 1], srgb[..., 2]
    rusty = paint & (r > g + 12) & (r > bb + 20) & (met < 0.1)
    PL = local(tx["P"])
    low = paint & (PL[..., 1] < 0.6); high = paint & (PL[..., 1] > 1.0)
    print(f"INFO rust: {f(rusty, paint):.1f} % of the Body paint ({f(rusty & low, low):.1f} % below y 0.6, "
          f"{f(rusty & high, high):.1f} % above y 1.0); STYLE_GUIDE guide 5-15 %")
    em = emis[..., :3]
    sw = cover & np.isin(matix, (SWITCH, LENS)); cy = cover & (matix == CYAN)
    print(f"INFO emission: switching texels white (median {tuple((np.median(em[sw], 0) * 255).round().astype(int))}), "
          f"cyan strips median {tuple((np.median(em[cy], 0) * 255).round().astype(int))} (STYLE_GUIDE 70 170 255)")
    ok_all &= normal_seams(lows["Body_01"], nrm, part, tx["P"], tx["N"], matix, zone)
    print("PASS all texture checks" if ok_all else "FAIL some texture checks")


SEAM_MIN = 0.040


def normal_seams(o, nrm, part, P, N, matix, zone, max_deg=6.0):
    """normal-map continuity across UV seams on the Body's flat faces (coplanar neighbours in different islands).
    Unlike gate_tex.normal_seams (2.5 px toward each face's centroid, so on an oblique seam the two samples can land
    ~5 mm apart and one in a groove), both samples are taken at the same 3D point: 1.5 px from the seam,
    perpendicular to the edge in each island. Samples are skipped where the surface carries deliberate relief within
    4 px (grooves, bolts: the detail height map) or the 1.5 mm bevel zone of an edge (edge / cavity pre-bakes): the
    check is about tangent-space mismatches on flat paint, which show as a visible line across a flat face."""
    d1, rustb, bande, d3 = details(part, matix, zone, P, N)
    relief = np.abs(d1[..., 0] - (0 - H_LO) / (H_HI - H_LO)) > 0.01
    from scipy.ndimage import maximum_filter
    relief = maximum_filter(relief, size=9)
    # bevel zone: within 4 mm of a real (non-coplanar) mesh edge, where the 1.5 mm bevel shading acts
    me0 = o.data; W = o.matrix_world
    segs = []
    lf = {}
    for p in me0.polygons:
        for k in p.edge_keys: lf.setdefault(k, []).append(p)
    for k, fs in lf.items():
        if len(fs) == 2 and fs[0].normal.angle(fs[1].normal, 0) < math.radians(1.0): continue
        segs.append((GT.spec(W @ me0.vertices[k[0]].co), GT.spec(W @ me0.vertices[k[1]].co)))
    SA = np.array([a for a, _ in segs]); SB = np.array([b for _, b in segs])
    def near_edge(q, r=0.004):
        ab = SB - SA; t = np.clip(((q - SA) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
        return np.min(np.linalg.norm(SA + ab * t[:, None] - q, axis=1)) < r
    me = o.data; me.calc_tangents(); uv = me.uv_layers.active.data
    ef = {}
    for p in me.polygons:
        for k in p.edge_keys: ef.setdefault(k, []).append(p)
    def side(p, k):
        d = {me.loops[li].vertex_index: np.array(uv[li].uv) for li in p.loop_indices}
        a, b = d[k[0]], d[k[1]]; c = np.mean([uv[li].uv for li in p.loop_indices], 0)
        e = b - a; nperp = np.array((-e[1], e[0])) / max(np.linalg.norm(e), 1e-12)
        if (c - a) @ nperp < 0: nperp = -nperp
        return a, b, nperp
    def frame(p):
        L = me.loops[p.loop_indices[0]]
        T = np.array(L.tangent); Nn = np.array(L.normal); B = L.bitangent_sign * np.cross(Nn, T); return T, B, Nn
    worst, bad, n, skipped, short = 0.0, 0, 0, 0, 0; where = []
    for k, fs in ef.items():
        if len(fs) != 2: continue
        a, b = fs
        if a.normal.angle(b.normal, 0) > math.radians(0.5): continue
        A, B_ = side(a, k), side(b, k)
        if np.allclose(A[0], B_[0], atol=1e-6) and np.allclose(A[1], B_[1], atol=1e-6): continue
        if (me.vertices[k[0]].co - me.vertices[k[1]].co).length < SEAM_MIN: short += 1; continue
        Fa, Fb = frame(a), frame(b)
        for t in (0.2, 0.4, 0.6, 0.8):
            pa = A[0] + (A[1] - A[0]) * t + A[2] * 1.5 / TEX; pb = B_[0] + (B_[1] - B_[0]) * t + B_[2] * 1.5 / TEX
            ya, xa = int(np.clip(pa[1] * TEX, 0, TEX - 1)), int(np.clip(pa[0] * TEX, 0, TEX - 1))
            yb, xb = int(np.clip(pb[1] * TEX, 0, TEX - 1)), int(np.clip(pb[0] * TEX, 0, TEX - 1))
            if relief[ya, xa] or relief[yb, xb] or near_edge(P[ya, xa]) or near_edge(P[yb, xb]): skipped += 1; continue
            na, nb = nrm[ya, xa, :3] * 2 - 1, nrm[yb, xb, :3] * 2 - 1
            wa = na[0] * Fa[0] + na[1] * Fa[1] + na[2] * Fa[2]; wb = nb[0] * Fb[0] + nb[1] * Fb[1] + nb[2] * Fb[2]
            ang = math.degrees(math.acos(np.clip(wa @ wb / (np.linalg.norm(wa) * np.linalg.norm(wb)), -1, 1)))
            worst = max(worst, ang); bad += ang > max_deg; n += 1
            if ang > max_deg:
                q = o.matrix_world @ (me.vertices[k[0]].co.lerp(me.vertices[k[1]].co, t))
                where.append((round(ang, 1), tuple(np.round(local(GT.spec(q)), 3))))
    ok = bad <= max(2, n // 200)
    for a_, q in sorted(where, reverse=True)[:8]:
        print(f"     seam sample {a_} deg at local {q}")
    print(f"{'PASS' if ok else 'FAIL'} normal seams on the Body's flat faces: {n} samples on coplanar seams, {bad} over "
          f"{max_deg} deg (worst {worst:.1f} deg); {skipped} samples skipped (groove / bolt relief or edge bevel zone "
          f"within 4 px), {short} seam edges < {SEAM_MIN * 1e3:.0f} mm skipped")
    return ok


# --------------------------------------------------------------------------- baked materials, renders


EMIT_RENDER = 1.0


def baked_material(name, emis_tint=(1, 1, 1), emis_strength=EMIT_RENDER):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; b = GT.NB(nt)
    bsdf = nt.nodes["Principled BSDF"]; nm = maps_names()
    def tex(fn, cs):
        img = bpy.data.images.get(fn) or bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = cs
        img.alpha_mode = 'CHANNEL_PACKED'
        return b.n("ShaderNodeTexImage", image=img)
    bc = tex(nm["BaseColor"], 'sRGB'); nmp = tex(nm["Normal"], 'Non-Color')
    mk = tex(nm["Mask"], 'Non-Color'); em = tex(nm["Emission"], 'sRGB')
    sep = b.n("ShaderNodeSeparateColor"); b.link(mk.outputs["Color"], sep.inputs[0])
    nmap = b.n("ShaderNodeNormalMap", space='TANGENT'); b.link(nmp.outputs["Color"], nmap.inputs["Color"])
    b.link(bc.outputs["Color"], bsdf.inputs["Base Color"]); b.link(sep.outputs[0], bsdf.inputs["Metallic"])
    b.link(b.sub(1.0, mk.outputs["Alpha"]), bsdf.inputs["Roughness"]); b.link(nmap.outputs[0], bsdf.inputs["Normal"])
    b.link(b.mix(1.0, em.outputs["Color"], tuple(emis_tint), 'MULTIPLY'), bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = emis_strength
    return m


def holo_material(strength=1.0):
    m = bpy.data.materials.new("M_Holo_Review"); m.use_nodes = True; nt = m.node_tree; b = GT.NB(nt)
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
    img = bpy.data.images.load(HOLO); img.alpha_mode = 'STRAIGHT'
    t = b.n("ShaderNodeTexImage", image=img)
    em = b.n("ShaderNodeEmission"); b.link(t.outputs["Color"], em.inputs["Color"]); em.inputs["Strength"].default_value = strength
    tr = b.n("ShaderNodeBsdfTransparent"); mx = b.n("ShaderNodeMixShader")
    b.link(t.outputs["Alpha"], mx.inputs[0]); b.link(tr.outputs[0], mx.inputs[1]); b.link(em.outputs[0], mx.inputs[2])
    b.link(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def apply_baked(objs, armed=False, beacon_on=None, holo_strength=0.8):
    """review objects -> baked look; Indicators cyan (red when armed), Beacon off (red when armed or beacon_on)"""
    beacon_on = armed if beacon_on is None else beacon_on
    mb = baked_material("M_Term_Baked")
    mi = baked_material("M_Term_Ind", CYAN_E if not armed else RED_E)
    ml = baked_material("M_Term_Lens", RED_E if beacon_on else (0, 0, 0), 1.6)
    for k, o in objs.items():
        if k == "Display_01":
            o.data.materials.clear(); o.data.materials.append(holo_material(holo_strength)); o.hide_render = False; continue
        m = mi if k == "Indicators_01" else ml if k == "Beacon_01" else mb
        for i in range(len(o.data.materials)): o.data.materials[i] = m


VIEWS = {
    "room": dict(loc=(0.6, 1.60, 2.6), look=(-2.2, 1.0, -1.6), lens=30),
    "34": dict(loc=TM.T((-1.3, 1.75, 2.4)), look=TM.T((0.0, 0.95, 0.40)), lens=35),
    "player": dict(loc=TM.T((0.0, 1.60, 1.25)), look=TM.T((0.0, 1.0, 0.40)), lens=24),
    "button": dict(loc=TM.T((-0.25, 1.30, 1.00)), look=TM.T((0.0, 0.98, 0.55)), lens=50),
    "beacon": dict(loc=TM.T((0.70, 1.55, 1.10)), look=TM.T((1.05, 1.30, 0.33)), lens=50),
    "pillar": dict(loc=TM.T((1.9, 1.10, 1.6)), look=TM.T((1.10, 0.70, 0.55)), lens=35),
    "lower": dict(loc=TM.T((-0.6, 0.55, 1.7)), look=TM.T((0.0, 0.45, 0.6)), lens=30),
    "side": dict(loc=TM.T((-1.75, 1.0, 1.5)), look=TM.T((-1.15, 0.65, 0.4)), lens=35),
}


def renders(args):
    import terminal_check as TC
    fast = "fast" in args
    only = set(a for a in args if a not in ("fast",))
    objs = TC.open_file()
    apply_baked(objs)
    sc = TC.scene(samples=16 if fast else 64, size=(1280, 800))
    if fast: sc.render.resolution_percentage = 50
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.006, 0.008, 0.011, 1)
    room, fl = TC.facility_room(); lights = TC.standard_lights()
    def cam(v):
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA': bpy.data.objects.remove(o)
        c = TC.cam_obj(v["lens"]); TC.look(c, v["loc"], v["look"])
    for k, v in VIEWS.items():
        if only and k not in only: continue
        cam(v); TC.shot(f"{TAG}_{k}.png", RENDERS)
    if not only or "armed" in only:
        apply_baked(objs, armed=True)
        cam(VIEWS["34"]); TC.shot(f"{TAG}_armed_34.png", RENDERS)
        cam(VIEWS["beacon"]); TC.shot(f"{TAG}_armed_beacon.png", RENDERS)
        apply_baked(objs)
    if not only or "dim" in only:
        keep = [l.data.energy for l in lights]
        for l in lights: l.data.energy *= 0.4
        cam(VIEWS["room"]); TC.shot(f"{TAG}_dim_facility.png", RENDERS)
        for l, e in zip(lights, keep): l.data.energy = e
    clip_report()
    if not only or "maps" in only: flat_maps()


def clip_report():
    """STYLE_GUIDE: emission must never clip to white. Emissive pixels = blue-dominant light (strips, holo) or red
    (Armed lights); their lowest channel must stay below 0.85 (no white core). White pixels elsewhere are specular
    glints on worn bare steel and are reported, not failed."""
    for k in ("room", "34", "player", "button", "dim_facility", "armed_34", "armed_beacon", "concept_34"):
        p = os.path.join(RENDERS, f"{TAG}_{k}.png")
        if not os.path.exists(p): continue
        img = bpy.data.images.load(p); a = GT.pixels_any(img)[..., :3]
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        emis = ((b > 0.6) & (b - r > 0.25)) | ((r > 0.6) & (r - g > 0.35))
        core = float(a.min(2)[emis].max()) if emis.any() else 0.0
        white = (a.min(2) > 0.85) & ~emis
        print(f"{'PASS' if core < 0.85 else 'FAIL'} no white clipping {k}: {int(emis.sum())} emissive pixels, brightest "
              f"core min-channel {core:.2f} (< 0.85); {int(white.sum())} white specular glints on bare steel (info)")


def flat_maps():
    nm = maps_names()
    for fn, tag, ch in ((nm["BaseColor"], "basecolor", None), (nm["Normal"], "normal", None), (nm["Emission"], "emission", None),
                        (nm["Mask"], "mask_metallic", 0), (nm["Mask"], "mask_ao", 1), (nm["Mask"], "mask_smoothness", 3)):
        a = load_png(fn)
        if ch is not None: a = np.repeat(a[..., ch:ch + 1], 4, 2)
        a[..., 3] = 1
        h = TEX // 2; d = a.reshape(h, 2, h, 2, 4).mean((1, 3))
        GT.save_png(d, f"{TAG}_map_{tag}.png", RENDERS, 'RGB')


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"bake": bake, "check": check, "renders": renders}[argv[0]](argv[1:])
