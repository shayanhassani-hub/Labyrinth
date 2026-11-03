"""
ServiceArm (Hero 01b) textures, hero workflow v3 (ASSET_RULES): procedural Blender materials baked in Cycles onto the
export-identical triangulated lows (env_kit_generator.triangulated_export_copy), one 2048 set for all six parts.
Same pipeline and helpers as the Gate (gate_tex.py: pre-bakes, channel bakes, 8 px dilation, checks).

  blender -b -P Tools/Blender/heroes/servicearm_tex.py -- bake [reuse]      details, pre-bakes, bakes, maps
  blender -b -P Tools/Blender/heroes/servicearm_tex.py -- check             AO black scan, PBR values, normal seams
  blender -b -P Tools/Blender/heroes/servicearm_tex.py -- renders [views] [fast]   review renders with the BAKED maps
  SA_TEX=512 (environment): bake / check / renders at 512 in their own folders, for cheap look iterations

Detail maps (numpy, from each texel's part-local position and normal; the parts are baked in the working pose, so
"down" for rust streaks and "more rust low" use the working pose's world height):
  D1  R height (bolts, panel plates, grooves, slot, cable corrugation), G bolt mask, B rust streaks, A grooves
  D2  R convex edges (pre-bake), G cavity (pre-bake), B rust blotches (bolts, panel corners), A cyan light strip
  D3  R soot (tool), G dark ports / slot floors, B world height in the working pose (0 ceiling ... 1 tool tip)
Look (STYLE_GUIDE; concept servicearm_front.jpg): arm paint sRGB 88 92 100 (sampled from the concept's lit link side
panels, median 88-95 / 89-92 / 94-98: a cool neutral grey, less blue than the Gate's gunmetal); polymer, machined
steel, ochre tool, cyan strips 70 170 255; edge wear to steel, grime, hairline scratches, rust per the rust rule.
Outputs: D:/AI_Labyrinth/Blender/Export/Heroes/ServiceArm/T_LAB_HERO_ServiceArm_{BaseColor,Normal,Mask,Emission}.png,
copied to Assets/Environment/Heroes/ServiceArm/Textures/ (2048 run only). Never saves the .blend.
"""
import bpy
import math
import os
import shutil
import sys
import time
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import servicearm as S                                   # noqa: E402
import servicearm_kin as KIN                             # noqa: E402
import gate_tex as GT                                    # noqa: E402  bake helpers (NB, run_bake, dilate, ...)
import env_kit_generator as K                            # noqa: E402

PROJ = KIN.PROJ
TEX = int(os.environ.get("SA_TEX", "2048"))
_SFX = "" if TEX == 2048 else f"_{TEX}"
WORK = os.path.join(PROJ, "Temp", "claude", "servicearm", "tex" + _SFX)
OUT = "D:/AI_Labyrinth/Blender/Export/Heroes/ServiceArm" + _SFX
REPO_TEX = os.path.join(PROJ, "Assets", "Environment", "Heroes", "ServiceArm", "Textures")
MEDIA = os.path.join(PROJ, "Documentation", "Media", "servicearm")
PARTS = list(KIN.PARTS)
H_LO, H_HI = -0.003, 0.004
BAKE_SAMPLES = dict(prebake=64, emit=4, normal=16)
RNG = np.random.default_rng(41)
lin, to_srgb = GT.lin, GT.to_srgb
GT.TEX = TEX                                             # gate_tex helpers read their module TEX (new_image, ...)

PAINT_C, POLY_C, STEEL_C = lin((88, 92, 100)), lin((35, 37, 39)), lin((188, 190, 192))
OCHRE_C, RUST_C, GRIME_C = lin((159, 120, 58)), lin((120, 62, 34)), lin((44, 41, 37))
CABLE_C = lin((84, 86, 86))
SOOT_C = lin((38, 34, 30))
CYAN_E, CYAN_OFF = lin((70, 170, 255)), lin((30, 45, 55))
RUST_DARK, RUST_EDGE = lin((66, 44, 34)), lin((112, 64, 38))
FILES = {k: f"T_LAB_HERO_ServiceArm_{k}.png" for k in ("BaseColor", "Normal", "Mask", "Emission")}


def fs(path):
    """file-system path of a Blender image path: off Windows Blender writes D:/... to /d/..."""
    if os.name != "nt" and path[:3].upper() == "D:/" and not os.path.exists(path): return "/d/" + path[3:]
    return path


def spec(v):
    return np.array((-v[0], v[2], -v[1]))


# --------------------------------------------------------------------------- scene, lows, texel maps


def open_lows(pose=None):
    bpy.ops.wm.open_mainfile(filepath=S.SAVE)
    objs = {n: bpy.data.objects[f"{S.HERO}_{n}_01"] for n in PARTS}
    if pose is not None: S.set_pose(objs, pose)
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
    """per texel: part (1..6), material slot, part-local position / face normal (spec), world height (working pose)"""
    part = np.zeros((TEX, TEX), np.int8); mat = np.full((TEX, TEX), -1, np.int8)
    P = np.zeros((TEX, TEX, 3), np.float32); N = np.zeros((TEX, TEX, 3), np.float32); WY = np.zeros((TEX, TEX), np.float32)
    for pi, (name, o) in enumerate(lows.items(), 1):
        me = o.data; uv = me.uv_layers.active.data; me.calc_loop_triangles()
        V = np.array([spec(v.co) for v in me.vertices])                        # part-local
        Wm = np.array(o.matrix_world)
        VW = np.array([spec(Wm[:3, :3] @ np.array(v.co) + Wm[:3, 3]) for v in me.vertices])
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
            iv = list(t.vertices)
            A, B, C = V[iv]; AW, BW, CW = VW[iv]
            P[ys[m], xs[m]] = w0[m, None] * A + w1[m, None] * B + w2[m, None] * C
            WY[ys[m], xs[m]] = (w0[m, None] * AW + w1[m, None] * BW + w2[m, None] * CW)[:, 1]
            N[ys[m], xs[m]] = spec(np.array(t.normal))
            part[ys[m], xs[m]] = pi; mat[ys[m], xs[m]] = me.polygons[t.polygon_index].material_index
    return part, mat, P, N, WY


# --------------------------------------------------------------------------- details

PI = {n: i for i, n in enumerate(PARTS, 1)}


def plane_sel(part, P, N, pi, axis, value, sign, tol=0.0006):
    """texels of part pi on the plane P[axis] = value with the normal along sign * axis"""
    return (part == pi) & (np.abs(P[..., axis] - value) < tol) & (N[..., axis] * sign > 0.98)


def rrect_dist(u, v, u0, u1, v0, v1, r):
    """signed distance to a rounded rectangle (negative inside)"""
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2; hu, hv = (u1 - u0) / 2 - r, (v1 - v0) / 2 - r
    du = np.abs(u - cu) - hu; dv = np.abs(v - cv) - hv
    return np.hypot(np.maximum(du, 0), np.maximum(dv, 0)) + np.minimum(np.maximum(du, dv), 0) - r


def stepped_plate(u, v, u0, u1, v0, v1, us, vs, r=0.006):
    """the concept's panel plate: a rounded rectangle whose top edge steps down by vs at u = us (45 deg)"""
    d = rrect_dist(u, v, u0, u1, v0, v1, r)
    # cut: above the line v = v1 - vs for u > us + (step ramp)
    ramp = np.clip((u - us) / max(vs, 1e-6), 0, 1)
    cut = v - (v1 - vs * ramp)
    return np.maximum(d, cut)


class Detail:
    def __init__(self, part, mat, P, N, WY):
        self.part, self.mat, self.P, self.N, self.WY = part, mat, P, N, WY
        sh = part.shape
        self.H = np.zeros(sh, np.float32); self.BOLT = np.zeros(sh, np.float32); self.STREAK = np.zeros(sh, np.float32)
        self.GROOVE = np.zeros(sh, np.float32); self.RUSTB = np.zeros(sh, np.float32); self.LIGHT = np.zeros(sh, np.float32)
        self.SOOT = np.zeros(sh, np.float32); self.DARK = np.zeros(sh, np.float32)
        self.streaks = []
        self.down = {}                                     # part-local direction of world down in the working pose
        W = KIN.fk(KIN.WORKING)
        for n in PARTS: self.down[n] = W[n][:3, :3].T @ np.array([0, -1.0, 0])

    def face(self, pname, axis, value, sign):
        """(mask, u, v, rows, cols) for a planar face: u, v = the two other axes (z before y, x before z)"""
        m = plane_sel(self.part, self.P, self.N, PI[pname], axis, value, sign)
        ys, xs = np.nonzero(m)
        oth = [a for a in (2, 1, 0) if a != axis][:2]
        return ys, xs, self.P[ys, xs, oth[0]], self.P[ys, xs, oth[1]], oth

    def bolt(self, pname, c, n, apo, washer, rust_p=0.45):
        c = np.array(c, float); n = np.array(n, float)
        P, N = self.P, self.N
        m = (self.part == PI[pname]) & (np.abs((P - c) @ n) < 0.0015) & ((N @ n) > 0.95) \
            & (np.linalg.norm(P - c, axis=2) < washer + 0.02)
        ys, xs = np.nonzero(m)
        if not len(ys): return
        up = -self.down[pname]; up = up - n * (up @ n)
        if np.linalg.norm(up) < 1e-6: up = np.cross(n, [1, 0, 0]) if abs(n[0]) < 0.9 else np.cross(n, [0, 1, 0])
        up /= np.linalg.norm(up); rt = np.cross(up, n)
        d = P[ys, xs] - c; x, y = d @ rt, d @ up
        th = RNG.uniform(0, math.pi / 3); xr, yr = x * math.cos(th) - y * math.sin(th), x * math.sin(th) + y * math.cos(th)
        r = np.hypot(x, y); dh = np.maximum(np.abs(yr), 0.866 * np.abs(xr) + 0.5 * np.abs(yr))
        w = np.clip((washer - r) / 0.0008, 0, 1); hd = np.clip((apo - dh) / 0.0010, 0, 1)
        self.H[ys, xs] = np.maximum(self.H[ys, xs], 0.0008 * w + 0.0028 * hd)
        self.BOLT[ys, xs] = np.maximum(self.BOLT[ys, xs], w)
        ring = RNG.choice((0.0, 0.5, 0.8, 1.0), p=(1 - rust_p, rust_p / 3, rust_p / 3, rust_p / 3))
        reach = RNG.uniform(0.004, 0.010); off = RNG.normal(0, 0.25, 2) * washer
        x2, y2 = x - off[0], y - off[1]; r2 = np.hypot(x2, y2) * GT.wobble(np.arctan2(y2, x2), RNG, 0.6)
        self.RUSTB[ys, xs] = np.maximum(self.RUSTB[ys, xs], ring * np.clip(1 - np.maximum(r2 - washer, 0) / reach, 0, 1) * (r > 0.8 * washer))
        if ring > 0.5 and RNG.random() < 0.55: self.streaks.append((pname, c - up * washer * 0.8, n, washer))

    def groove(self, ys, xs, dist, width=0.0016, depth=0.0010):
        self.H[ys, xs] -= depth * np.clip(1 - (np.abs(dist) / width) ** 2, 0, 1)
        self.GROOVE[ys, xs] = np.maximum(self.GROOVE[ys, xs], np.clip(1 - np.abs(dist) / (2 * width), 0, 1))

    def raise_(self, ys, xs, dist, h, soft=0.0012):
        self.H[ys, xs] += h * np.clip(-dist / soft, 0, 1)

    def blotch(self, pname, c, n, R):
        c = np.array(c, float); n = np.array(n, float)
        m = (self.part == PI[pname]) & (np.abs((self.P - c) @ n) < 0.003) & (np.linalg.norm(self.P - c, axis=2) < 2.2 * R)
        ys, xs = np.nonzero(m)
        if not len(ys): return
        up = -self.down[pname]; up = up - n * (up @ n); up /= max(np.linalg.norm(up), 1e-9); rt = np.cross(up, n)
        d = self.P[ys, xs] - c; x, y = d @ rt, d @ up
        r = np.hypot(x, y) * GT.wobble(np.arctan2(y, x), RNG, 0.9)
        self.RUSTB[ys, xs] = np.maximum(self.RUSTB[ys, xs], np.clip(1 - r / R, 0, 1) ** 0.7)
        if RNG.random() < 0.5: self.streaks.append((pname, c - up * R * 0.4, n, 0.005))

    def run_streaks(self):
        for pname, s, n, w in self.streaks:
            L = RNG.uniform(0.05, 0.22); wd = RNG.uniform(0.003, 0.006)
            up = -self.down[pname]; up = up - n * (up @ n)
            if np.linalg.norm(up) < 0.3: continue                     # face nearly horizontal in the working pose
            up /= np.linalg.norm(up); rt = np.cross(up, n)
            m = (self.part == PI[pname]) & (np.abs((self.P - s) @ n) < 0.003) & ((self.N @ n) > 0.95)
            d = self.P - s; x, y = d @ rt, -(d @ up)
            ys, xs = np.nonzero(m & (y > 0) & (y < L) & (np.abs(x) < 3 * wd))
            t = y[ys, xs] / L; ww = wd * (1 + 1.5 * t)
            val = np.clip(1 - np.abs(x[ys, xs]) / ww, 0, 1) * (1 - t) ** 1.5
            self.STREAK[ys, xs] = np.maximum(self.STREAK[ys, xs], val)


def link_side(D, pname, hx, z0, z1, hy, seams, strip, plate_step, end_bolts):
    """panels on both side faces of a link (x = +-hx): groove frame, raised stepped plate with 4 bolts, cyan strip in
    a dark slot, end-block seams across the four long faces, bolts on the end blocks"""
    for sx in (1, -1):
        ys, xs, u, v, _ = D.face(pname, 0, sx * hx, sx)                  # u = z, v = y
        zs = (min(z0, z1), max(z0, z1))
        fr = rrect_dist(u, v, zs[0], zs[1], -hy, hy, 0.008)
        D.groove(ys, xs, fr)
        pz0, pz1 = zs[0] + 0.016, zs[1] - 0.016
        us = pz0 + (pz1 - pz0) * plate_step
        pl = stepped_plate(u, v, pz0, pz1, -hy + 0.008, hy - 0.008, us, 0.010)
        D.raise_(ys, xs, pl, 0.0012)
        D.groove(ys, xs, pl, 0.0010, 0.0006)
        for bz in (pz0 + 0.012, pz1 - 0.012):
            for by in (-hy + 0.016, hy - 0.016 - (0.010 if bz > us else 0.0)):
                D.bolt(pname, (sx * hx + 0.0012 * sx, by, bz), (sx, 0, 0), 0.0045, 0.0068, 0.22)
        # cyan strip in a slot (below the step, as the concept): slot floor dark, light core emissive
        sz0, sz1, sy = strip
        sl = rrect_dist(u, v, sz0, sz1, sy - 0.0055, sy + 0.0055, 0.004)
        D.H[ys, xs] -= 0.0018 * np.clip(-sl / 0.0008, 0, 1)
        D.DARK[ys, xs] = np.maximum(D.DARK[ys, xs], np.clip(-sl / 0.0008, 0, 1))
        core = rrect_dist(u, v, sz0 + 0.003, sz1 - 0.003, sy - 0.0028, sy + 0.0028, 0.0025)
        D.LIGHT[ys, xs] = np.maximum(D.LIGHT[ys, xs], np.clip(-core / 0.0007, 0, 1))
        D.H[ys, xs] += 0.0012 * np.clip(-core / 0.0007, 0, 1)
        for bz in end_bolts:
            for by in (-0.6 * hy, 0.6 * hy):
                D.bolt(pname, (sx * hx, by, bz), (sx, 0, 0), 0.0045, 0.0068, 0.3)
        # rust blotches in some plate corners
        for cz in (pz0, pz1):
            for cy in (-hy + 0.008, hy - 0.008):
                if RNG.random() < 0.4: D.blotch(pname, (sx * hx, cy, cz), (sx, 0, 0), RNG.uniform(0.012, 0.03))
    # end-block seams round the four long faces
    for zc in seams:
        m = (D.part == PI[pname]) & (np.abs(D.N[..., 2]) < 0.2) & (np.abs(D.P[..., 2] - zc) < 0.006)
        ys, xs = np.nonzero(m)
        D.groove(ys, xs, D.P[ys, xs, 2] - zc, 0.0015, 0.0010)


def disc_bolts(D, pname, cx, c2, r, n_b, apo, washer, sign=1, ring=None):
    for k in range(n_b):
        a = 2 * math.pi * (k + 0.5) / n_b
        D.bolt(pname, (cx, c2[1] + r * math.sin(a), c2[0] + r * math.cos(a)), (sign, 0, 0), apo, washer, 0.4)
    if ring:
        ys, xs, u, v, _ = D.face(pname, 0, cx, sign)
        rr = np.hypot(u - c2[0], v - c2[1])
        sel = rr < ring + 0.006
        D.groove(ys[sel], xs[sel], rr[sel] - ring, 0.0012, 0.0008)


def cable_corrugation(D):
    for pname, ctrl in S.CABLES.items():
        path = np.array(S.catmull(ctrl()), float)
        seg = np.diff(path, axis=0); L = np.linalg.norm(seg, axis=1); s0 = np.concatenate([[0], np.cumsum(L)])
        m = (D.part == PI[pname]) & (D.mat == S.CABLE)
        ys, xs = np.nonzero(m)
        if not len(ys): continue
        Q = D.P[ys, xs]
        best = np.full(len(Q), np.inf); sv = np.zeros(len(Q))
        for i in range(len(seg)):
            a = path[i]; ab = seg[i]; t = np.clip(((Q - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
            d = np.linalg.norm(Q - (a + t[:, None] * ab), axis=1)
            b = d < best; best[b] = d[b]; sv[b] = s0[i] + t[b] * L[i]
        D.H[ys, xs] += 0.0007 * np.sin(2 * math.pi * sv / 0.0075)


def details(part, mat, P, N, WY):
    D = Detail(part, mat, P, N, WY)
    # UpperArm: side panels z 0.24 .. 0.84 (the concept's plate with a step and the strip below it)
    link_side(D, "UpperArm", S.UA_HW, 0.24, 0.86, 0.042, seams=(0.19, 0.91), strip=(0.585, 0.685, -0.006),
              plate_step=0.55, end_bolts=(0.125, 0.885))
    link_side(D, "Forearm", S.FA_HW, -0.20, -0.72, 0.034, seams=(-0.14, -0.78), strip=(-0.42, -0.50, -0.005),
              plate_step=0.45, end_bolts=(-0.095, -0.815))
    # elbow disc: 8 bolts and a ring; shoulder slotted cap: slot + ring; bracket cap and wrist cap bolts
    disc_bolts(D, "Forearm", S.ELBOW_DISC_X1, (0.0, 0.0), 0.046, 8, 0.0042, 0.0062, 1, ring=0.036)
    ys, xs, u, v, _ = D.face("UpperArm", 0, S.UA_HW + S.SLOT_CAP_T, 1)
    a = math.radians(-30); du, dv = (u * math.cos(a) + v * math.sin(a)), (-u * math.sin(a) + v * math.cos(a))
    slot = np.maximum(np.abs(du) - 0.024, np.abs(dv) - 0.0038)
    D.H[ys, xs] -= 0.0025 * np.clip(-slot / 0.0008, 0, 1); D.DARK[ys, xs] = np.maximum(D.DARK[ys, xs], np.clip(-slot / 0.0008, 0, 1) * 0.6)
    rr = np.hypot(u, v); D.groove(ys, xs, rr - 0.030, 0.0012, 0.0008)
    disc_bolts(D, "Turret", S.CHEEK_CAP_X1, (0.0, S.SHOULDER_Y), 0.028, 6, 0.0038, 0.0055, -1, ring=0.021)
    disc_bolts(D, "Wrist", S.WR_CAP_X1, (0.0, 0.0), 0.022, 4, 0.0034, 0.005, 1, ring=0.016)
    # turret: groove round the disc side, ring on the boss; neck and collar grooves
    m = (part == PI["Turret"]) & (np.abs(N[..., 1]) < 0.3) & (np.hypot(P[..., 0], P[..., 2]) > S.DISC_R - 0.004)
    ys, xs = np.nonzero(m); D.groove(ys, xs, P[ys, xs, 1] - (-0.0105), 0.0015, 0.0012)
    for pname, zc in (("Wrist", -0.051), ("Wrist", -0.057), ("ToolHead", -0.012), ("ToolHead", -0.024)):
        m = (part == PI[pname]) & (np.abs(N[..., 2]) < 0.3) & (np.abs(P[..., 2] - zc) < 0.005)
        ys, xs = np.nonzero(m); D.groove(ys, xs, P[ys, xs, 2] - zc, 0.0012, 0.0009)
    # mount: washers under the nuts, the adapter's side ports (rectangular on +Z / -Z, oval on +X / -X), small bolts
    for sx in (-1, 1):
        for sz in (-1, 1):
            c = np.array((sx * S.NUT_AT, -S.PLATE_T, sz * S.NUT_AT))
            m = (part == PI["Mount"]) & (np.abs(P[..., 1] + S.PLATE_T) < 0.0006) & (N[..., 1] < -0.98)
            ys, xs = np.nonzero(m); r = np.hypot(P[ys, xs, 0] - c[0], P[ys, xs, 2] - c[2])
            D.H[ys, xs] += 0.0010 * np.clip((0.024 - r) / 0.0008, 0, 1)
            if RNG.random() < 0.7: D.blotch("Mount", c + np.array((0, 0, 0)), (0, -1, 0), RNG.uniform(0.025, 0.04))
    m = (part == PI["Mount"]) & (N[..., 1] < -0.3) & (N[..., 1] > -0.95)            # adapter's slanted sides
    ys, xs = np.nonzero(m)
    pp = P[ys, xs]; nn = N[ys, xs]
    for ax, sgn, kind in ((2, 1, "rect"), (2, -1, "rect"), (0, 1, "oval"), (0, -1, "oval")):
        sel = nn[:, ax] * sgn > 0.5
        lat = pp[sel, 0 if ax == 2 else 2]; hgt = pp[sel, 1] + 0.035
        if kind == "rect": dd = np.maximum(np.abs(lat - 0.04 * sgn) - 0.022, np.abs(hgt) - 0.0055)
        else: dd = np.hypot(np.maximum(np.abs(lat) - 0.012, 0), hgt) - 0.0055
        y2, x2 = ys[sel], xs[sel]
        D.H[y2, x2] -= 0.0025 * np.clip(-dd / 0.0008, 0, 1)
        D.DARK[y2, x2] = np.maximum(D.DARK[y2, x2], np.clip(-dd / 0.0008, 0, 1))
    # tool: two bolts on each wide face, soot (the concept's black smudges: lower part, notch, edges)
    for sy_ in (-1, 1):
        for bx in (-0.045, -0.015):
            D.bolt("ToolHead", (bx, sy_ * S.BLOCK_HY, -0.048), (0, sy_, 0), 0.0040, 0.006, 0.3)
    m = (part == PI["ToolHead"]) & (mat == S.OCHRE)
    ys, xs = np.nonzero(m)
    low = np.clip((-P[ys, xs, 2] - 0.10) / 0.06, 0, 1)
    notch = np.clip(1 - np.hypot(P[ys, xs, 0] - 0.035, P[ys, xs, 2] + 0.10) / 0.05, 0, 1)
    edge_t = np.clip(1 - np.minimum(0.07 - np.abs(P[ys, xs, 0]), 0.05 - np.abs(P[ys, xs, 1])) / 0.012, 0, 1)
    D.SOOT[ys, xs] = np.clip(0.6 * low + 0.8 * notch + 0.25 * edge_t, 0, 1)
    cable_corrugation(D)
    D.run_streaks()
    Hn = (np.clip(D.H, H_LO, H_HI) - H_LO) / (H_HI - H_LO)
    hy = np.clip((KIN.CEILING_Y - WY) / (KIN.CEILING_Y - KIN.tip(KIN.WORKING)[1]), 0, 1) * (part > 0)
    print(f"INFO details: bolt texels {int((D.BOLT > 0.5).sum())}, streaks {len(D.streaks)}, light texels "
          f"{int((D.LIGHT > 0.5).sum())}")
    return (np.stack([Hn, D.BOLT, D.STREAK, D.GROOVE], 2), D.RUSTB, D.LIGHT,
            np.stack([D.SOOT, D.DARK, hy.astype(np.float32)], 2))


# --------------------------------------------------------------------------- procedural materials


def surface_material(slot, d1, d2, d3):
    name = S.MATS[slot][0] + "_Tex"
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != 'OUTPUT_MATERIAL': nt.nodes.remove(nd)
    b = GT.NB(nt)
    out = nt.nodes["Material Output"]
    bsdf = b.n("ShaderNodeBsdfPrincipled")
    em = b.n("ShaderNodeEmission"); em.name = "BakeEmit"
    GT.add_target(nt)
    tc = b.n("ShaderNodeTexCoord"); obj = tc.outputs["Object"]
    t1 = b.n("ShaderNodeTexImage", image=d1, interpolation='Linear'); t2 = b.n("ShaderNodeTexImage", image=d2, interpolation='Linear')
    t3 = b.n("ShaderNodeTexImage", image=d3, interpolation='Linear')
    s1, s2, s3 = b.n("ShaderNodeSeparateColor"), b.n("ShaderNodeSeparateColor"), b.n("ShaderNodeSeparateColor")
    b.link(t1.outputs["Color"], s1.inputs[0]); b.link(t2.outputs["Color"], s2.inputs[0]); b.link(t3.outputs["Color"], s3.inputs[0])
    Hn, BO, ST = s1.outputs[0], s1.outputs[1], s1.outputs[2]; GR = t1.outputs["Alpha"]
    E, C, RB = s2.outputs[0], s2.outputs[1], s2.outputs[2]; LT = t2.outputs["Alpha"]
    SOOT, DARK, HY = s3.outputs[0], s3.outputs[1], s3.outputs[2]
    nf = b.noise(obj, 90.0, 6.0); nw = b.noise(obj, 2.5, 4.0); nr = b.noise(obj, 22.0, 10.0, 0.65)
    nr2 = b.noise(obj, 140.0, 4.0)

    def hairlines(rot, scale, stretch, width, dens, lo, hi, seed):
        mp = b.n("ShaderNodeMapping"); b.link(obj, mp.inputs[0])
        mp.inputs["Scale"].default_value = (1.0, stretch, 1.0); mp.inputs["Rotation"].default_value = (math.radians(rot), 0.0, 0.0)
        mp.inputs["Location"].default_value = (seed, 0.37 * seed, 0.0)
        t = b.n("ShaderNodeTexNoise"); b.link(mp.outputs[0], t.inputs["Vector"])
        t.inputs["Scale"].default_value = scale; t.inputs["Detail"].default_value = 1.5; t.inputs["Roughness"].default_value = 0.4
        ln = b.remap(b.math('ABSOLUTE', b.sub(t.outputs["Fac"], 0.5)), 0.0, width, 1.0, 0.0)
        return b.mul(ln, b.remap(b.noise(obj, dens, 2.0), lo, hi))
    scratch = b.math('MAXIMUM', hairlines(0, 1.6, 60.0, 0.008, 1.2, 0.46, 0.56, 0.0), hairlines(25, 1.4, 60.0, 0.005, 1.4, 0.50, 0.60, 3.1))
    scratch = b.math('MAXIMUM', scratch, hairlines(-30, 1.3, 60.0, 0.005, 1.3, 0.53, 0.62, 7.7))
    grime = b.clamp(b.add(b.mul(b.sub(1.0, C), 1.4), b.mul(b.mul(HY, 0.35), nw), b.mul(GR, 0.4)))
    kind = {S.PAINT: "paint", S.OCHRE: "ochre", S.POLYMER: "polymer", S.STEEL: "steel", S.CABLE: "cable"}[slot]
    emis = b.rgb((0, 0, 0))
    if kind in ("paint", "ochre"):
        pc = PAINT_C if kind == "paint" else OCHRE_C
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.9 * c for c in pc)), b.rgb(tuple(1.1 * c for c in pc)))
        base = b.mix(b.mul(b.remap(nw, 0.35, 0.65), 0.45), base, b.rgb(tuple(0.8 * c for c in pc)))
        if kind == "ochre":                                               # soot / black smudges (concept)
            sm = b.clamp(b.mul(SOOT, b.remap(b.add(b.noise(obj, 18.0, 6.0, 0.6), b.mul(nw, 0.4)), 0.42, 0.75)))
            base = b.mix(sm, base, b.rgb(SOOT_C))
        base = b.mix(DARK, base, b.rgb(POLY_C))                           # slot floors, adapter ports
        sect = b.remap(b.noise(obj, 12.0, 3.0), 0.48, 0.62)
        wear = b.remap(b.add(b.mul(E, b.add(0.5, b.mul(sect, 0.9))), b.mul(b.sub(nr, 0.5), 0.7), b.mul(scratch, 0.25)),
                       0.63, 0.73)
        wear = b.mul(wear, b.sub(1.0, LT))
        # rust (STYLE_GUIDE rust rule): edges, bolts / corners (RB), streaks (ST), more towards the tool (HY), patches
        hb = b.mul(HY, 0.22)
        er = b.mul(E, b.remap(b.noise(obj, 9.0, 4.0), 0.44, 0.62))
        spk = b.mul(b.remap(b.noise(obj, 28.0, 6.0, 0.6), 0.60, 0.70), b.remap(b.noise(obj, 2.2, 2.0), 0.35, 0.55))
        pat = b.remap(b.noise(obj, 3.2, 5.0, 0.6), 0.54, 0.70)
        rv = b.add(b.mul(RB, 0.75), b.mul(er, 2.6), hb, spk, b.mul(pat, 0.6), b.mul(b.sub(nr, 0.5), 1.1), b.mul(b.sub(nr2, 0.5), 0.3))
        near = b.clamp(b.add(b.remap(b.sub(1.0, C), 0.04, 0.25), b.remap(E, 0.10, 0.40), GR, b.mul(RB, 2.0), b.mul(HY, 0.6)))
        rust = b.clamp(b.add(b.mul(b.remap(rv, 0.40, 0.52), near), b.mul(ST, b.remap(nf, 0.2, 0.6, 0.55, 1.0))))
        rust = b.mul(rust, b.sub(1.0, b.math('MAXIMUM', LT, DARK)))
        if kind == "ochre": rust = b.mul(rust, 0.3)          # the drone-handling ochre stays bright (STYLE_GUIDE)
        col = b.mix(b.mul(scratch, 0.6), base, (1.9, 1.9, 1.9), 'MULTIPLY')
        col = b.mix(b.mul(GR, 0.55), col, b.rgb(tuple(0.35 * c for c in pc)))                 # panel lines read dark
        col = b.mix(wear, col, b.rgb(STEEL_C))
        tip = b.mul(b.mul(b.mul(BO, b.remap(Hn, 0.86, 0.93)), b.remap(nr2, 0.60, 0.72)), b.remap(nr, 0.35, 0.55))
        col = b.mix(tip, col, b.rgb(STEEL_C))
        rcol = b.mix(b.remap(rv, 0.50, 0.85), b.rgb(RUST_EDGE), b.rgb(RUST_DARK))
        rcol = b.mix(b.mul(b.remap(nr2, 0.3, 0.8), 0.35), rcol, b.rgb(tuple(0.85 * c for c in RUST_C)))
        col = b.mix(rust, col, rcol)
        bare = b.mul(b.math('MAXIMUM', wear, tip), b.sub(1.0, rust))
        gk = 0.7 if kind == "paint" else 0.35
        col = b.mix(b.mul(b.mul(grime, gk), b.sub(1.0, b.mul(bare, 0.9))), col, b.rgb(GRIME_C))
        col = b.mix(LT, col, b.rgb(CYAN_OFF))                             # light strip: off-state albedo, emissive
        metal = b.mul(bare, b.sub(1.0, LT))
        rough = b.add(0.56 if kind == "paint" else 0.50, b.mul(b.sub(nw, 0.5), 0.3), b.mul(scratch, -0.2))
        rough = b.mixf(b.math('MAXIMUM', wear, tip), rough, b.add(0.60, b.mul(b.sub(nf, 0.5), 0.1), b.mul(grime, 0.25)))
        rough = b.mixf(rust, rough, b.add(0.85, b.mul(b.sub(nr2, 0.5), 0.1)))
        rough = b.add(rough, b.mul(grime, 0.12))
        rough = b.mixf(LT, rough, 0.4)
        e = b.rgb(CYAN_E); emis = b.mix(LT, b.rgb((0, 0, 0)), e)
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.03), b.mul(rust, b.mul(b.sub(nr2, 0.5), 0.04)), b.mul(scratch, -0.015))
    elif kind in ("polymer", "cable"):
        pc = POLY_C if kind == "polymer" else CABLE_C
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.9 * c for c in pc)), b.rgb(tuple(1.1 * c for c in pc)))
        wear = b.remap(b.add(b.mul(E, 1.1), b.mul(b.sub(nr, 0.5), 0.9)), 0.55, 0.8)
        col = b.mix(wear, base, b.rgb(tuple(1.5 * c for c in pc)))
        col = b.mix(b.mul(grime, 0.6), col, b.rgb(GRIME_C))
        metal = b.val(0.0)
        rough = b.add(0.64 if kind == "polymer" else 0.48, b.mul(b.sub(nw, 0.5), 0.2), b.mul(wear, 0.1), b.mul(grime, 0.08))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.02))
    else:                                                                  # machined steel
        base = b.mix(b.remap(nf, 0.3, 0.7), b.rgb(tuple(0.95 * c for c in STEEL_C)), b.rgb(tuple(1.04 * c for c in STEEL_C)))
        rust = b.mul(b.remap(b.add(b.mul(RB, 0.5), b.mul(b.sub(nr, 0.5), 1.1), b.mul(HY, 0.15)), 0.70, 0.86), 0.75)
        rcol = b.mix(b.remap(nr2, 0.2, 0.8), b.rgb(tuple(0.8 * c for c in RUST_C)), b.rgb(RUST_C))
        col = b.mix(rust, base, rcol)
        g2 = b.mul(grime, 0.45)
        col = b.mix(b.mul(g2, 0.15), col, b.rgb(GRIME_C))
        metal = b.sub(1.0, rust)
        rough = b.add(0.66, b.mul(b.sub(nw, 0.5), 0.2), b.mul(scratch, 0.1), b.mul(rust, 0.3), b.mul(g2, 0.35))
        hgt = b.add(Hn, b.mul(b.sub(nf, 0.5), 0.012))
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


# --------------------------------------------------------------------------- bake


def bake(args):
    os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    objs, lows = open_lows()
    part, mat, P, N, WY = texel_maps(lows)
    np.savez_compressed(os.path.join(WORK, "texels.npz"), part=part, mat=mat, P=P, N=N, WY=WY)
    cover = part > 0
    d1, rustb, light, d3 = details(part, mat, P, N, WY)
    res = {}
    prev = os.path.join(WORK, "prebakes.npz")
    old = dict(np.load(prev)) if "reuse" in args and os.path.exists(prev) else {}
    for kind in ("edge", "cavity", "ao"):
        if kind in old:
            res[kind] = old[kind]; print(f"INFO {kind}: reused"); continue
        pm = GT.prebake_material("cavity" if kind == "ao" else kind); keep = GT.swap_materials(lows, lambda i: pm)
        img = GT.new_image(f"pre_{kind}", size=TEX)
        GT.run_bake(lows, kind, img, "AO" if kind == "ao" else "EMIT", BAKE_SAMPLES["prebake"]); GT.restore(lows, keep)
        res[kind] = GT.pixels(img)[..., 0]
    np.savez_compressed(prev, **res)
    edge = np.clip(GT.blur_masked(res["edge"], cover, 1) * GT.EDGE_GAIN, 0, 1)
    cav = GT.blur_masked(res["cavity"], cover, 1)
    print(f"INFO edge mask p90 / p99 {np.percentile(edge[cover], 90):.2f} / {np.percentile(edge[cover], 99):.2f}")
    # detail maps dilated like the outputs: the bump node samples neighbouring texels, across island borders too
    d2 = np.stack([edge, cav, rustb, light], 2)
    d1, d2, d3 = (GT.dilate(a, cover) for a in (d1, d2, d3))
    D1 = GT.new_image("D1", d1, size=TEX); D2 = GT.new_image("D2", d2, size=TEX)
    D3 = GT.new_image("D3", d3, size=TEX)
    mats = [surface_material(s, D1, D2, D3) for s in range(len(S.MATS))]
    keep = GT.swap_materials(lows, lambda i: mats[i][0])
    maps = {}
    for ch, kind, smp in (("base", "EMIT", "emit"), ("rough", "EMIT", "emit"), ("metal", "EMIT", "emit"),
                          ("emis", "EMIT", "emit"), ("normal", "NORMAL", "normal")):
        for m, socks in mats: GT.set_channel(m, socks, ch)
        img = GT.new_image(f"bake_{ch}", size=TEX); GT.run_bake(lows, ch, img, kind, BAKE_SAMPLES[smp])
        maps[ch] = GT.pixels(img)
    GT.restore(lows, keep)
    Dm = {k: GT.dilate(v, cover) for k, v in maps.items()}
    ao = GT.dilate(np.repeat(res["ao"][..., None], 4, 2), cover)[..., 0]
    one = np.ones((TEX, TEX, 1))
    base = np.concatenate([to_srgb(Dm["base"][..., :3]), one], 2)
    nrm = np.concatenate([Dm["normal"][..., :3], one], 2)
    mask = np.stack([Dm["metal"][..., 0], ao, np.zeros((TEX, TEX)), 1 - Dm["rough"][..., 0]], 2)
    emis = np.concatenate([to_srgb(Dm["emis"][..., :3]), one], 2)
    for arr, k in ((base, "BaseColor"), (nrm, "Normal"), (mask, "Mask"), (emis, "Emission")):
        GT.save_png(arr, FILES[k], OUT)
    np.savez_compressed(os.path.join(WORK, "masks.npz"), edge=edge, cavity=cav, ao=res["ao"], light=light)
    if TEX == 2048:
        os.makedirs(REPO_TEX, exist_ok=True)
        for fn in FILES.values(): shutil.copy2(fs(os.path.join(OUT, fn)), os.path.join(REPO_TEX, fn))
        print("COPIED maps to", os.path.relpath(REPO_TEX, PROJ))
    print(f"INFO bake total {time.time() - t0:.0f} s")


# --------------------------------------------------------------------------- checks


def load_png(fn):
    img = bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = 'Non-Color'
    return GT.pixels(img)


def check(args):
    objs, lows = open_lows()
    tx = np.load(os.path.join(WORK, "texels.npz")); part, matix = tx["part"], tx["mat"]
    cover = part > 0
    base = load_png(FILES["BaseColor"]); mask = load_png(FILES["Mask"]); emis = load_png(FILES["Emission"])
    nrm = load_png(FILES["Normal"])
    light = np.load(os.path.join(WORK, "masks.npz"))["light"] > 0.5
    ok_all = True
    ao = mask[..., 1]
    enclosed = buried_texels(lows, part, tx["P"], tx["N"], ao < GT.AO_BLACK)
    crev = cable_crevices(lows, part, matix, tx["P"], ao < GT.AO_BLACK)
    for pi, name in enumerate(PARTS, 1):
        buried = (part == pi) & enclosed
        dark = (part == pi) & (ao < GT.AO_BLACK) & ~enclosed & ~crev
        print(f"INFO AO {name}: {int(((part == pi) & crev).sum())} dark texels in accepted crevices (cable underside and "
              f"the link face under it, < {CREVICE * 1e3:.0f} mm apart)")
        print(f"INFO AO {name}: {int(buried.sum())} dark texels buried inside the part's own shells (no ray escapes; never seen)")
        pcs = GT.components(dark) if dark.sum() < 200000 else []
        patches = [c for c in pcs if len(c) / (np.ptp(c, 0).max() + 1) > GT.LINE_MAX]
        small = [c for c in patches if len(c) < SMALL_PATCH]
        patches = [c for c in patches if len(c) >= SMALL_PATCH]
        if small: print(f"INFO AO {name}: {len(small)} small crevice patches (< {SMALL_PATCH} texels, < 0.15 cm2): "
                        + ", ".join(f"{len(c)} at {np.round(tx['P'][c[:, 0], c[:, 1]].mean(0), 3).tolist()}" for c in small[:4]))
        ok = not patches; ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} AO black {name}: {int(dark.sum())} texels AO < {GT.AO_BLACK}, "
              f"{len(pcs) - len(patches)} contact lines, {len(patches)} patches"
              + ("; " + ", ".join(f"{len(c)} at {np.round(tx['P'][c[:, 0], c[:, 1]].mean(0), 3).tolist()}" for c in sorted(patches, key=len)[::-1][:4]) if patches else ""))
    srgb = base[..., :3] * 255; met = mask[..., 0]
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
    print(f"INFO metallic: {f(metal, cover):.1f} % metal, {f(trans, cover):.2f} % transitions 0.1-0.9 (worn edges, rust, grime)")
    for s, (nm, _) in enumerate(S.MATS):
        sel = cover & (matix == s)
        if sel.any():
            print(f"INFO {nm}: albedo sRGB median {tuple(np.median(srgb[sel], 0).round().astype(int))}, smoothness median "
                  f"{np.median(mask[..., 3][sel]):.2f}, metallic mean {met[sel].mean():.2f}")
    # rust coverage on the paint (rust rule 5-15 %): rust = non-metal, orange-brown albedo, rough
    paint = cover & (matix == S.PAINT) & ~light
    r, g, bb = srgb[..., 0], srgb[..., 1], srgb[..., 2]
    rust = paint & (r > g + 12) & (g > bb + 4) & (mask[..., 3] < 0.32)
    hy = np.clip((KIN.CEILING_Y - tx["WY"]) / (KIN.CEILING_Y - 2.04), 0, 1)
    low, high = paint & (hy > 0.5), paint & (hy <= 0.5)
    pr = f(rust, paint)
    ok = 5.0 <= pr <= 15.0; ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'} rust rule: {pr:.1f} % of the painted texels (5-15 %); lower half {f(rust & low, low):.1f} %, "
          f"upper half {f(rust & high, high):.1f} %")
    em = emis[..., :3]
    lt = cover & light
    if lt.any():
        e8 = em[lt] * 255
        print(f"INFO emission (light strips, {lt.sum()} texels): median sRGB {tuple(np.median(e8, 0).round().astype(int))}; "
              f"outside the strips max {em[cover & ~light].max() * 255:.0f}")
    seams_ok = True
    for n, o in lows.items():
        seams_ok &= normal_seams(n, o, nrm)
    ok_all &= seams_ok
    print("RESULT:", "PASS" if ok_all else "FAIL")


CREVICE, SMALL_PATCH = 0.015, 40


def cable_crevices(lows, part, matix, P, cand):
    """dark texels in the narrow gap between a cable and the link face it rides on (cable underside / face under it):
    real occlusion, seen only edge-on; accepted like the Gate's rail-plate crevice"""
    from mathutils.bvhtree import BVHTree
    out = np.zeros(part.shape, bool)
    for pi, (name, o) in enumerate(lows.items(), 1):
        me = o.data
        V = [tuple(spec(v.co)) for v in me.vertices]
        groups = {True: [], False: []}
        for p in me.polygons: groups[p.material_index == S.CABLE].append(list(p.vertices))
        if not groups[True]: continue
        trees = {k: BVHTree.FromPolygons(V, f) for k, f in groups.items() if f}
        ys, xs = np.nonzero(cand & (part == pi))
        for y, x in zip(ys, xs):
            other = trees[not (matix[y, x] == S.CABLE)]
            h = other.find_nearest(Vector(P[y, x]))
            out[y, x] = h[0] is not None and h[3] < CREVICE
    return out


def buried_texels(lows, part, P, N, cand, ndir=64, reach=0.5):
    """candidate texels from which no ray (hemisphere about the face normal) leaves the part's own geometry: surface
    inside another shell of the same part (intersecting shells), never visible from anywhere"""
    from mathutils.bvhtree import BVHTree
    out = np.zeros(part.shape, bool)
    import cradle_v2 as CV
    dirs = [np.array(spec(d)) for d in CV.fib_dirs(ndir)]
    for pi, (name, o) in enumerate(lows.items(), 1):
        me = o.data
        V = [tuple(spec(v.co)) for v in me.vertices]; F = [list(p.vertices) for p in me.polygons]
        if name == "Mount":                                   # the ceiling closes the plate's open top
            k = len(V); V += [(-1, 0.0005, -1), (1, 0.0005, -1), (1, 0.0005, 1), (-1, 0.0005, 1)]; F.append([k, k + 1, k + 2, k + 3])
        tree = BVHTree.FromPolygons(V, F)
        ys, xs = np.nonzero(cand & (part == pi))
        for y, x in zip(ys, xs):
            n = N[y, x]; o_ = P[y, x] + n * 4e-4
            free = False
            for d in dirs:
                if d @ n <= 0.05: continue
                if tree.ray_cast(Vector(o_), Vector(d), reach)[0] is None: free = True; break
            out[y, x] = not free
    return out


def normal_seams(name, o, nrm, max_deg=6.0, seam_min=0.030):
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
        L = me.loops[p.loop_indices[0]]
        T = np.array(L.tangent); Nn = np.array(L.normal); B = L.bitangent_sign * np.cross(Nn, T); return T, B, Nn
    worst, bad, n = 0.0, 0, 0
    for k, fs in edge_faces.items():
        if len(fs) != 2: continue
        a, b = fs
        if a.normal.angle(b.normal, 0) > math.radians(0.5): continue
        ua, ub = uvkey(a, k), uvkey(b, k)
        if np.allclose(ua[0], ub[0], atol=1e-6) and np.allclose(ua[1], ub[1], atol=1e-6): continue
        if (me.vertices[k[0]].co - me.vertices[k[1]].co).length < seam_min: continue
        ca = np.mean([uv[li].uv for li in a.loop_indices], 0); cb = np.mean([uv[li].uv for li in b.loop_indices], 0)
        Ta, Tb = frame(a), frame(b)
        for t in (0.25, 0.5, 0.75):
            pa = ua[0] + (ua[1] - ua[0]) * t; pb = ub[0] + (ub[1] - ub[0]) * t
            pa = pa + (ca - pa) / np.linalg.norm(ca - pa) * 2.5 / TEX; pb = pb + (cb - pb) / np.linalg.norm(cb - pb) * 2.5 / TEX
            na, nb = sample(pa), sample(pb)
            wa = na[0] * Ta[0] + na[1] * Ta[1] + na[2] * Ta[2]; wb = nb[0] * Tb[0] + nb[1] * Tb[1] + nb[2] * Tb[2]
            ang = math.degrees(math.acos(np.clip(wa @ wb / (np.linalg.norm(wa) * np.linalg.norm(wb)), -1, 1)))
            worst = max(worst, ang); bad += ang > max_deg; n += 1
            if ang > max_deg: print(f"     seam sample {ang:.1f} deg at {np.round(spec(me.vertices[k[0]].co.lerp(me.vertices[k[1]].co, t)), 3).tolist()}")
    ok = bad <= max(2, n // 100)
    print(f"{'PASS' if ok else 'FAIL'} normal seams {name}: {n} samples on coplanar seams, {bad} over {max_deg} deg (worst {worst:.1f})")
    return ok


# --------------------------------------------------------------------------- renders with the baked maps

EMIT_RENDER = 1.0


def baked_material():
    m = bpy.data.materials.new("M_ServiceArm_Baked"); m.use_nodes = True; nt = m.node_tree; b = GT.NB(nt)
    bsdf = nt.nodes["Principled BSDF"]

    def tex(fn, cs):
        img = bpy.data.images.load(os.path.join(OUT, fn)); img.colorspace_settings.name = cs
        img.alpha_mode = 'CHANNEL_PACKED'
        return b.n("ShaderNodeTexImage", image=img)
    bc = tex(FILES["BaseColor"], 'sRGB'); nm = tex(FILES["Normal"], 'Non-Color')
    mk = tex(FILES["Mask"], 'Non-Color'); em = tex(FILES["Emission"], 'sRGB')
    sep = b.n("ShaderNodeSeparateColor"); b.link(mk.outputs["Color"], sep.inputs[0])
    nmap = b.n("ShaderNodeNormalMap", space='TANGENT'); b.link(nm.outputs["Color"], nmap.inputs["Color"])
    b.link(bc.outputs["Color"], bsdf.inputs["Base Color"]); b.link(sep.outputs[0], bsdf.inputs["Metallic"])
    b.link(b.sub(1.0, mk.outputs["Alpha"]), bsdf.inputs["Roughness"]); b.link(nmap.outputs[0], bsdf.inputs["Normal"])
    b.link(em.outputs["Color"], bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = EMIT_RENDER
    return m


def set_lows_pose(lows, pose):
    W = KIN.fk(pose)
    for n, o in lows.items(): o.matrix_world = S.blender_matrix(W[n])
    bpy.context.view_layer.update()


def renders(args):
    """h2 review renders: concept cameras side by side, working pose over the docked drone (room position), stowed,
    3/4, close-ups, dim facility light; maps. args: "fast" (16 samples), view names to limit"""
    import servicearm_check as SC
    objs, lows = open_lows()
    for o in objs.values(): bpy.data.objects.remove(o, do_unlink=True)
    m = baked_material()
    for o in lows.values():
        for i in range(len(o.data.materials)): o.data.materials[i] = m
    fast = "fast" in args; only = set(a for a in args if a != "fast")
    want = lambda k: not only or k in only
    tag = "servicearm_h2"
    scr = os.path.join(PROJ, "Temp", "claude", "servicearm")
    os.makedirs(MEDIA, exist_ok=True); os.makedirs(scr, exist_ok=True)
    SC.scene_setup(size=(1288, 719), samples=16 if fast else 64, bg=lin((62, 62, 64)), view='Standard')
    sc = bpy.context.scene
    SC.setup_room(drone=False)
    concept_lights = [SC.add_light("Key", (2.6, 3.6, 3.2), (0.1, 3.3, 5.4), 110, 2.5),
                      SC.add_light("Fill", (2.5, 2.2, 7.5), (0.1, 3.3, 5.4), 45, 3.0, (0.85, 0.92, 1.0)),
                      SC.add_light("Rim", (-2.0, 3.6, 7.8), (0.1, 3.3, 5.4), 60, 2.0)]
    shots = []
    if want("concept"):
        set_lows_pose(lows, dict(KIN.CONCEPT, th4=-90.0))
        SC.side_camera(SC.SIDE_FIT_PXM); p = os.path.join(scr, f"{tag}_side.png"); SC.shot(p)
        SC.side_by_side(p, SC.CONCEPT_SIDE, os.path.join(MEDIA, f"{tag}_vs_concept_side.jpg"))
        SC.front_camera(); p = os.path.join(scr, f"{tag}_front.png"); SC.shot(p)
        SC.side_by_side(p, SC.CONCEPT_FRONT, os.path.join(MEDIA, f"{tag}_vs_concept.jpg"))
    SC.add_drone(True)
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (*lin((22, 23, 25)), 1)
    set_lows_pose(lows, dict(KIN.WORKING, th4=-90.0))
    views = [("working_34", (3.2, 2.6, 2.6), (0.1, 2.75, 4.95), 35), ("working_player", (-2.6, 1.9, 1.0), (-0.1, 2.6, 4.9), 32),
             ("closeup_elbow", (1.35, 3.0, 4.6), (0.25, 2.95, 5.35), 50), ("closeup_tool", (0.75, 2.25, 3.95), (0.02, 2.28, 4.69), 50),
             ("closeup_mount", (1.0, 3.45, 4.5), (0.05, 3.88, 5.3), 50)]
    for k, loc, look, lens in views:
        if want(k): SC.camera(loc, look, lens); p = os.path.join(scr, f"{tag}_{k}.png"); SC.shot(p); shots.append(k)
    if want("dim"):                                                    # dim facility light: lamps at ~35 %
        keep = [l.data.energy for l in concept_lights]
        for l in concept_lights: l.data.energy *= 0.35
        SC.camera((-2.2, 2.2, 1.6), (0.0, 2.8, 5.0), 30); p = os.path.join(scr, f"{tag}_dim_facility.png"); SC.shot(p)
        shots.append("dim_facility")
        for l, e in zip(concept_lights, keep): l.data.energy = e
    if want("stowed"):
        set_lows_pose(lows, KIN.STOWED)
        SC.camera((3.2, 2.6, 2.6), (0.1, 3.3, 5.2), 35); p = os.path.join(scr, f"{tag}_stowed_34.png"); SC.shot(p)
        SC.camera((1.6, 3.2, 3.3), (0.1, 3.86, 5.6), 45); p2 = os.path.join(scr, f"{tag}_stowed_close.png"); SC.shot(p2)
        shots += ["stowed_34", "stowed_close"]
    for k in shots:
        SC.save_jpg(SC.load_rgb(os.path.join(scr, f"{tag}_{k}.png")), os.path.join(MEDIA, f"{tag}_{k}.jpg"))
    clip_report(scr, tag, shots)
    if want("maps"): flat_maps(tag)


def clip_report(scr, tag, shots):
    for k in shots:
        p = os.path.join(scr, f"{tag}_{k}.png")
        img = bpy.data.images.load(p); a = GT.pixels_any(img)[..., :3]
        bright = a.max(2) > 0.85; white = bright & (a.min(2) > 0.85)
        print(f"{'PASS' if white.sum() == 0 else 'FAIL'} no white clipping {k}: {int(bright.sum())} bright pixels, {int(white.sum())} white")


def flat_maps(tag):
    import servicearm_check as SC
    for k, sub, ch in (("BaseColor", "basecolor", None), ("Normal", "normal", None), ("Emission", "emission", None),
                       ("Mask", "mask_metallic", 0), ("Mask", "mask_ao", 1), ("Mask", "mask_smoothness", 3)):
        a = load_png(FILES[k])
        if ch is not None: a = np.repeat(a[..., ch:ch + 1], 4, 2)
        h = TEX // 2; d = a.reshape(h, 2, h, 2, 4).mean((1, 3))[..., :3]
        # the PNG pixels are already in their file encoding: save as is (Standard view, no transform)
        lin_ = np.where(d <= 0.04045, d / 12.92, ((d + 0.055) / 1.055) ** 2.4)        # save_jpg expects linear floats
        SC.save_jpg(lin_[::-1].astype(np.float32), os.path.join(MEDIA, f"{tag}_map_{sub}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    {"bake": bake, "check": check, "renders": renders}[argv[0]](argv[1:])
