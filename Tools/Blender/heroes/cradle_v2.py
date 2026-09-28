"""
Labyrinth VR -- Hero 01 v2, docking cradle (LAB_HERO_Cradle_*), clean hero low-poly by construction.

Source of every number: Documentation/HERO_SPEC.md section 3 (v2, measured from the fitted AI
model, Renders/cradle_ai_sections.png). Standard: ASSET_RULES.md, Hero tier. Axes: spec = Unity
(metres); geometry is authored in cradle-local spec coordinates (origin on the floor at the cradle
centre, front = -Z) and mapped to Blender per EXPORT_CONTRACT (x -> -x, y -> z, z -> -y).

Parts (review file D:/AI_Labyrinth/Blender/Source/Heroes/Cradle/LAB_HERO_Cradle_v2.blend):
  LAB_HERO_Cradle_Base_01    static body, origin floor centre, placed at spec (0, 0, 4.69)
    LAB_HERO_Cradle_Arm_R_01   origin on the right pin axis (+0.385, 0.637, 0); arm + rest plate
      LAB_HERO_Cradle_Pad_R_01   amber pad, mesh LAB_HERO_Cradle_Pad_01 (shared), origin bottom centre
    LAB_HERO_Cradle_Arm_L_01   exact mirror of Arm_R, origin on the left pin axis
      LAB_HERO_Cradle_Riser_L_01 grey riser (54.4 mm) under the left pad, origin bottom centre
      LAB_HERO_Cradle_Pad_L_01   amber pad, same mesh as Pad_R
Opening: Arm_L rotates +deg, Arm_R -deg about Blender Y (spec Z); 75 deg = released.

Construction: 16-vertex rings on the round/octagonal stack (24 on the tier-2 octagons, which carry
the tray ends), quads by bridging; planar n-gons (tray surround, caps) are triangulated and joined
back to quads, so the only triangles sit on flat faces. Separate intersecting shells are used where
cheaper (beam, drums, boss, web); every face that is hidden in both the closed and the released
pose is deleted (ray visibility test).

Run:  blender -b --factory-startup -P Tools/Blender/heroes/cradle_v2.py            (build + save)
Checks and renders: cradle_v2_check.py.
"""
import bpy
import bmesh
import math
import os
import sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERO = "LAB_HERO_Cradle"
SAVE = "D:/AI_Labyrinth/Blender/Source/Heroes/Cradle/LAB_HERO_Cradle_v2.blend"
CZ = 4.69                                   # cradle origin z (spec)

# --------------------------------------------------------------------------- parameters (HERO_SPEC §3)
PIN_X, PIN_Y = 0.385, 0.637                 # pin axes (+-x), axis parallel to Z
RELEASE_DEG = 75.0

# tier 1: 16-gon plan (+x+z quadrant, CCW), mirrored to all quadrants
T1_Q = [(1.214, 0.442), (1.027, 0.608), (0.632, 1.028), (0.490, 1.214)]
T1_RINGS = [(0.016, 0.000), (0.000, 0.016), (0.000, 0.162), (0.036, 0.203)]   # (inset, y)
T1_TOP, TRAY_FLOOR = 0.203, 0.162

# tier 2 and inner octagons: (flat X, flat Z, flat diagonal, y); all carry the tray-end points
T2_RINGS = [(0.863, 0.843, 0.850, 0.203), (0.863, 0.843, 0.850, 0.246), (0.842, 0.827, 0.818, 0.274),
            (0.769, 0.763, 0.757, 0.288), (0.744, 0.740, 0.737, 0.318), (0.738, 0.733, 0.729, 0.318),
            (0.738, 0.733, 0.729, 0.300), (0.662, 0.654, 0.636, 0.300), (0.644, 0.636, 0.614, 0.290),
            (0.642, 0.634, 0.612, 0.253)]
# tray pockets (hexagonal: the ends bulge outward mid-depth). Per end: (t inner, t mid, w mid, t floor-outer,
# t top-outer); t measured from the face centre for X/Z faces, from the X-side / Z-side corner for diagonals.
# Widths from the tier-2 wall: (floor outer, top outer). Measured on plan sections at y 0.172.
TRAY_END = {"X": (0.311, 0.357, 0.128, 0.327, 0.330), "Z": (0.282, 0.341, 0.153, 0.289, 0.300),
            "DX": (0.069, 0.063, 0.060, 0.070, 0.072), "DZ": (0.131, 0.101, 0.095, 0.112, 0.113)}
TRAY_W = {"X": (0.167, 0.221), "Z": (0.206, 0.261), "D": (0.114, 0.182)}

# turntable, rings, column, collar, hub cap
CIRCLES = [((0.516, 0.516), 0.253), ((0.515, 0.515), 0.301), ((0.497, 0.497), 0.333), ((0.385, 0.385), 0.333),
           ((0.385, 0.385), 0.356), ((0.293, 0.267), 0.356), ((0.293, 0.267), 0.384), ((0.285, 0.259), 0.392)]
COL_Q = [(0.258, 0.052), (0.180, 0.085), (0.174, 0.149), (0.118, 0.224)]
COL_YS = [0.392, 0.440, 0.600, 0.700, 0.724]
COL_TOP_Q = [(0.240, 0.045), (0.168, 0.074), (0.162, 0.128), (0.104, 0.191)]
COLLAR_Q = [(0.167, 0.030), (0.167, 0.102), (0.117, 0.152), (0.030, 0.152)]
LEDGE_Y, COLLAR_Y1 = 0.761, 0.810
HUB = [((0.150, 0.150), 0.812), ((0.150, 0.150), 0.860), ((0.130, 0.130), 0.884)]

# hinge beam (right side; mirrored), stations along x: (x, bottom y); section bands in z
BEAM_ST = [(0.120, 0.500), (0.322, 0.502), (0.400, 0.508)]   # underside ~y 0.50 (plan/z-sections at x 0.22)
BEAM_TOP = 0.755
# drums and pin caps: (radius, z) rings along the pin axis, front (-z) to back (+z)
DRUM_R, DRUM_SEG = 0.118, 16
DRUM_PROFILE = [(0.065, -0.2404), (0.080, -0.228), (0.080, -0.190), (0.110, -0.190), (0.118, -0.182),
                (0.118, -0.153), (0.118, 0.153),            # split at the beam depth: the buried part is deleted
                (0.118, 0.195), (0.110, 0.203), (0.100, 0.203), (0.085, 0.2219)]

# arm (right side, cradle-local), stations (inner edge, step, outer edge) in the front plane
def _arc(r, deg):
    return (PIN_X + r * math.cos(math.radians(deg)), PIN_Y + r * math.sin(math.radians(deg)))
ARM_ST = [
    (_arc(0.140, 97), _arc(0.140, 62), _arc(0.160, 6.5)),        # outer: on the boss rim, AI outer contour
    ((0.421, 0.901), (0.509, 0.898), (0.671, 0.819)),
    ((0.424, 0.981), (0.524, 0.983), (0.709, 1.009)),
    ((0.422, 1.126), (0.489, 1.126), (0.689, 1.126)),
    ((0.420, 1.271), (0.454, 1.271), (0.666, 1.271)),
    ((0.411, 1.372), (0.430, 1.372), (0.654, 1.372)),
    ((0.409, 1.500), (0.433, 1.500), (0.640, 1.500)),
    ((0.405, 1.550), (0.435, 1.550), (0.592, 1.550)),
]
STRIP_Z, BODY_Z, CH_IN, CH_OUT = 0.110, 0.151, 0.008, 0.015
BOSS_R0, BOSS_R1, BOSS_Z, BOSS_A0, BOSS_A1, BOSS_SEG, BOSS_CH = 0.124, 0.160, 0.160, 0.0, 98.0, 5, 0.008
WEB = [(0.398, 1.545), (0.600, 1.545), (0.600, 1.400), (0.651, 1.410), (0.681, 1.437), (0.905, 1.508),
       (0.942, 1.588), (0.940, 1.600), (0.398, 1.600)]            # top 12 mm inside the plate: deleted as hidden
WEB_Z = 0.095
PLATE_X0, PLATE_X1, PLATE_Z, PLATE_K = 0.280, 1.139, 0.211, 0.012
PLATE_TOP = 1.6991
PLATE_IN_CH = (0.040, 0.008)                 # inner top edge chamfer (w, h): fold clearance to the limb
PLATE_RINGS = [(1.588, 0.013, 0.033), (1.594, 0.004, 0.020), (1.616, 0.000, 0.020), (1.624, 0.000, 0.000),
               (1.663, 0.000, 0.000), (1.671, 0.000, 0.020), (PLATE_TOP - PLATE_IN_CH[1], 0.000, 0.020),
               (PLATE_TOP, PLATE_IN_CH[0], 0.035)]
# pads and riser (bottom-centred), positions along the limbs (x = +-0.50)
PAD = dict(hx=0.110, hz=0.070, h=0.010, ch=0.003)
RISER = dict(hx=0.115, hz=0.075, h=0.0544, ch=0.004)
PAD_X = 0.500

# --------------------------------------------------------------------------- helpers


def to_blender(p):
    return Vector((-p[0], -p[2], p[1]))


def ear_clip(pts):
    """triangulate a simple planar polygon (3D points) -> index triples; concave outlines are respected"""
    P = np.array(pts, float)
    nrm = np.zeros(3)
    for i in range(len(P)):                               # Newell normal
        a, b = P[i], P[(i + 1) % len(P)]
        nrm += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
    ax = int(np.argmax(np.abs(nrm)))
    keep = [(ax + 1) % 3, (ax + 2) % 3]                   # cyclic order: right-handed 2D axes for the normal axis
    Q = P[:, keep]
    if nrm[ax] < 0: Q = Q[:, ::-1]                        # make the 2D outline counter-clockwise
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    idx = list(range(len(Q))); tris = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cross(Q[i0], Q[i1], Q[i2]) <= 1e-12: continue          # reflex or flat corner
            if any(j not in (i0, i1, i2) and cross(Q[i0], Q[i1], Q[j]) >= -1e-12 and cross(Q[i1], Q[i2], Q[j]) >= -1e-12
                   and cross(Q[i2], Q[i0], Q[j]) >= -1e-12 for j in idx):
                continue                                               # another vertex inside the ear
            tris.append((i0, i1, i2)); idx.pop(k); break
        else:
            break
    if len(idx) == 3: tris.append(tuple(idx))
    return tris


class SpecMesh:
    """vertices by spec coordinate (merged on a 1e-6 grid), faces by point loops"""

    def __init__(self):
        self.bm = bmesh.new()
        self.cache = {}
        self.join = []                       # triangles to join back to quads

    def v(self, p):
        key = (round(p[0], 6) + 0.0, round(p[1], 6) + 0.0, round(p[2], 6) + 0.0)
        if key not in self.cache:
            self.cache[key] = self.bm.verts.new(key)
        return self.cache[key]

    def f(self, *pts):
        vs = [self.v(p) for p in pts]
        if len(set(vs)) < 3:
            return None
        if len(set(vs)) < len(vs):                        # drop repeated (degenerate) corners
            seen, out = set(), []
            for x in vs:
                if x not in seen: seen.add(x); out.append(x)
            vs = out
        if len(vs) > 4:                                   # planar n-gon: own ear clipping, joined to quads later
            for tri in ear_clip([tuple(v.co) for v in vs]):
                try:
                    fc = self.bm.faces.new([vs[i] for i in tri]); fc.smooth = True; self.join.append(fc)
                except ValueError:
                    pass
            return None
        try:
            face = self.bm.faces.new(vs)
        except ValueError:
            return None
        face.smooth = True
        return face

    def bridge(self, a, b, closed=True):
        n = len(a)
        assert n == len(b)
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            self.f(a[i], a[j], b[j], b[i])

    def zipper(self, a, b):
        """bridge two closed rings with different counts (planar annulus): triangles, joined later"""
        def ang(p):
            return math.atan2(p[2], p[0]) % (2 * math.pi)
        a = sorted(a, key=ang); b = sorted(b, key=ang)
        aa = [ang(p) for p in a] + [ang(a[0]) + 2 * math.pi]
        bb = [ang(p) for p in b] + [ang(b[0]) + 2 * math.pi]
        i = j = 0
        while i < len(a) or j < len(b):
            ai, bj = a[i % len(a)], b[j % len(b)]
            if j >= len(b) or (i < len(a) and aa[i + 1] <= bb[j + 1]):
                fc = self.f(ai, a[(i + 1) % len(a)], bj); i += 1
            else:
                fc = self.f(ai, b[(j + 1) % len(b)], bj); j += 1
            if fc is not None and len(fc.verts) == 3:
                self.join.append(fc)

    def grid_fill(self, ring):
        """16-vertex planar ring -> 4x4 quad grid (Coons patch)"""
        n = len(ring)
        assert n == 16
        P = [np.array(p, float) for p in ring]
        def B(i): return P[i]                   # bottom row j=0, i=0..4
        def Rr(j): return P[4 + j]              # right col i=4
        def T(i): return P[(12 - i) % 16]       # top row j=4
        def L(j): return P[(16 - j) % 16]       # left col i=0
        G = {}
        for i in range(5):
            for j in range(5):
                if j == 0: G[i, j] = B(i)
                elif i == 4: G[i, j] = Rr(j)
                elif j == 4: G[i, j] = T(i)
                elif i == 0: G[i, j] = L(j)
                else:
                    u, w = i / 4, j / 4
                    G[i, j] = ((1 - w) * B(i) + w * T(i) + (1 - u) * L(j) + u * Rr(j)
                               - ((1 - u) * (1 - w) * P[0] + u * (1 - w) * P[4] + (1 - u) * w * P[12] + u * w * P[8]))
        for i in range(4):
            for j in range(4):
                self.f(tuple(G[i, j]), tuple(G[i + 1, j]), tuple(G[i + 1, j + 1]), tuple(G[i, j + 1]))

    def cap3(self, ring8):
        """chamfered-rectangle ring (8) -> 3 quads"""
        r = ring8
        self.f(r[0], r[1], r[6], r[7]); self.f(r[1], r[2], r[5], r[6]); self.f(r[2], r[3], r[4], r[5])

    def finish(self, name, offset=(0, 0, 0)):
        bm = self.bm
        if self.join:
            live = [f for f in set(self.join) if f.is_valid and len(f.verts) == 3]
            inner = list({e for f in live for e in f.edges if all(g in live for g in e.link_faces) and len(e.link_faces) == 2})
            res = bmesh.ops.beautify_fill(bm, faces=live, edges=inner)           # better-shaped triangles on flat areas
            live = [f for f in set(live) | set(res["geom"]) if isinstance(f, bmesh.types.BMFace) and f.is_valid and len(f.verts) == 3]
            bmesh.ops.join_triangles(bm, faces=live, cmp_seam=False, cmp_sharp=False, cmp_uvs=False,
                                     cmp_vcols=False, cmp_materials=False,
                                     angle_face_threshold=math.radians(0.5), angle_shape_threshold=math.radians(70))
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        ox, oy, oz = offset
        for v in bm.verts:
            x, y, z = v.co
            v.co = (-(x - ox), -(z - oz), (y - oy))
        bm.normal_update()
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me); bm.free()
        for p in me.polygons: p.use_smooth = True
        return me


def ring3(pts2d, y):
    return [(x, y, z) for x, z in pts2d]


def mirror_quadrants(q):
    """quadrant list (+x,+z, CCW) -> full closed CCW list"""
    a = list(q)
    b = [(-x, z) for x, z in reversed(q)]
    c = [(-x, -z) for x, z in q]
    d = [(x, -z) for x, z in reversed(q)]
    return a + b + c + d


def poly_offset(poly, d):
    """CCW polygon (x, z) offset inward by d"""
    n = len(poly); lines = []
    for i in range(n):
        p = np.array(poly[i], float); q = np.array(poly[(i + 1) % n], float)
        e = q - p; e /= np.linalg.norm(e)
        lines.append((p + np.array([-e[1], e[0]]) * d, e))
    out = []
    for i in range(n):
        p1, e1 = lines[i - 1]; p2, e2 = lines[i]
        t, s = np.linalg.solve(np.array([e1, -e2]).T, p2 - p1)
        out.append(tuple(p1 + t * e1))
    return out


def ellipse16(rx, rz, y, off=11.25):
    return [(rx * math.cos(math.radians(off + 22.5 * k)), y, rz * math.sin(math.radians(off + 22.5 * k))) for k in range(16)]


def octa_corners(fx, fz, fd):
    c1 = fd * math.sqrt(2) - fx; c2 = fd * math.sqrt(2) - fz
    return [(fx, -c1), (fx, c1), (c2, fz), (-c2, fz), (-fx, c1), (-fx, -c1), (-c2, -fz), (c2, -fz)]


FACE_TYPES = ["X", "D+", "Z", "D-", "X", "D+", "Z", "D-"]    # D+: X-side corner first, D-: Z-side first


def tray_ends(k, L):
    """(end a, end b) as tuples of t measured from the face's start corner: (inner, mid, w mid, floor outer, top outer)"""
    t = FACE_TYPES[k]
    if t in ("X", "Z"):
        i, m, wm, fo, to = TRAY_END[t]; c = L / 2
        return (c - i, c - m, wm, c - fo, c - to), (c + i, c + m, wm, c + fo, c + to)
    x, z = TRAY_END["DX"], TRAY_END["DZ"]
    from_end = lambda e: (L - e[0], L - e[1], e[2], L - e[3], L - e[4])
    if t == "D+":                                     # X-side corner first
        return x, from_end(z)
    return z, from_end(x)


def base_face_lengths():
    C = octa_corners(*T2_RINGS[0][:3])
    return [float(np.linalg.norm(np.array(C[(k + 1) % 8]) - np.array(C[k]))) for k in range(8)]


def tray_fracs(k):
    L = base_face_lengths()[k]
    a, b = tray_ends(k, L)
    return a[0] / L, b[0] / L


def t2_ring(fx, fz, fd, y):
    """24 points: per face [corner A, tray end a, tray end b], CCW from the X+ face"""
    C = octa_corners(fx, fz, fd); out = []
    for k in range(8):
        A = np.array(C[k]); Bc = np.array(C[(k + 1) % 8]); fa, fb = tray_fracs(k)
        for p in (A, A + fa * (Bc - A), A + fb * (Bc - A)):
            out.append((p[0], y, p[1]))
    return out


# --------------------------------------------------------------------------- base


def build_base():
    sm = SpecMesh()
    # tier 1 (16-gon, bottom chamfer, wall, top chamfer)
    t1 = mirror_quadrants(T1_Q)
    t1_rings = [ring3(poly_offset(t1, d) if d else t1, y) for d, y in T1_RINGS]
    for a, b in zip(t1_rings, t1_rings[1:]):
        sm.bridge(a, b)
    outer = t1_rings[-1]                       # top outer edge, y 0.203, 16 points
    # tier 2 / inner octagon rings (24)
    t2 = [t2_ring(*r) for r in T2_RINGS]
    for a, b in zip(t2, t2[1:]):
        sm.bridge(a, b)
    # tier-1 top: 8 sectors, each with a tray pocket against the tier-2 wall
    base = t2[0]
    O = outer
    sector_outer = {0: [O[15], O[0]], 1: [O[0], O[1], O[2], O[3]], 2: [O[3], O[4]], 3: [O[4], O[5], O[6], O[7]],
                    4: [O[7], O[8]], 5: [O[8], O[9], O[10], O[11]], 6: [O[11], O[12]], 7: [O[12], O[13], O[14], O[15]]}
    C = octa_corners(*T2_RINGS[0][:3])
    for k in range(8):
        A = base[3 * k]; a = base[3 * k + 1]; b = base[3 * k + 2]; Bn = base[(3 * k + 3) % 24]
        e = np.array(C[(k + 1) % 8]) - np.array(C[k]); e /= np.linalg.norm(e)
        n = np.array([e[1], -e[0]])            # outward normal (right of the CCW edge)
        kind = "D" if FACE_TYPES[k].startswith("D") else FACE_TYPES[k]
        wf, wt = TRAY_W[kind]
        L = float(np.linalg.norm(np.array(C[(k + 1) % 8]) - np.array(C[k])))
        ea, eb = tray_ends(k, L)
        A2 = np.array(C[k])
        def pt(t, w, y):
            q = A2 + e * t + n * w
            return (float(q[0]), y, float(q[1]))
        a_f, b_f = (a[0], TRAY_FLOOR, a[2]), (b[0], TRAY_FLOOR, b[2])
        am_f, bm_f = pt(ea[1], ea[2], TRAY_FLOOR), pt(eb[1], eb[2], TRAY_FLOOR)      # bulge, floor
        am_t, bm_t = pt(ea[1], ea[2], T1_TOP), pt(eb[1], eb[2], T1_TOP)              # bulge, top (end walls vertical)
        a_ff, b_ff = pt(ea[3], wf, TRAY_FLOOR), pt(eb[3], wf, TRAY_FLOOR)            # floor outer corners
        a_t, b_t = pt(ea[4], wt, T1_TOP), pt(eb[4], wt, T1_TOP)                      # top outer corners
        sm.f(*(sector_outer[k] + [Bn, b, bm_t, b_t, a_t, am_t, a, A]))              # tier-1 top around the tray
        sm.f(a_f, b_f, bm_f, b_ff, a_ff, am_f)                                       # tray floor (hexagon)
        sm.f(a_ff, b_ff, b_t, a_t)                                                   # sloped outer wall
        sm.f(a, a_f, am_f, am_t); sm.f(am_t, am_f, a_ff, a_t)                        # end walls
        sm.f(b, bm_t, bm_f, b_f); sm.f(bm_t, b_t, b_ff, bm_f)
        sm.f(a, b, b_f, a_f)                                                         # tier-2 wall down to the floor
    # trough floor (24 -> 16) and the turntable / rings
    circles = [ellipse16(r[0], r[1], y) for r, y in CIRCLES]
    sm.zipper(t2[-1], circles[0])
    for a, b in zip(circles, circles[1:]):
        sm.bridge(a, b)
    # column (16), ledge, collar, hub cap
    col = mirror_quadrants(COL_Q)
    col_rings = [ring3(col, y) for y in COL_YS]
    sm.bridge(circles[-1], col_rings[0])
    for a, b in zip(col_rings, col_rings[1:]):
        sm.bridge(a, b)
    col_top = ring3(mirror_quadrants(COL_TOP_Q), LEDGE_Y)
    collar0 = ring3(mirror_quadrants(COLLAR_Q), LEDGE_Y)
    collar1 = ring3(mirror_quadrants(COLLAR_Q), COLLAR_Y1)
    sm.bridge(col_rings[-1], col_top); sm.bridge(col_top, collar0); sm.bridge(collar0, collar1)
    hub = [ellipse16(r[0], r[1], y) for r, y in HUB]
    sm.bridge(collar1, hub[0])
    for a, b in zip(hub, hub[1:]):
        sm.bridge(a, b)
    sm.grid_fill(hub[-1])
    # hinge beams, drums with pin caps (both sides)
    for sx in (1, -1):
        add_beam(sm, sx)
        add_beam_fillet(sm, sx)
        add_drum(sm, sx)
    return sm.finish(f"{HERO}_Base_01")


def beam_section(yb):
    zb, zm = 0.090, 0.153
    return [(-zb, yb), (zb, yb), (zb, 0.560), (zm, 0.600), (zm, 0.700), (zb, 0.720), (zb, BEAM_TOP),
            (-zb, BEAM_TOP), (-zb, 0.720), (-zm, 0.700), (-zm, 0.600), (-zb, 0.560)]


def add_beam(sm, sx):
    rings = [[(sx * x, y, z) for z, y in beam_section(yb)] for x, yb in BEAM_ST]
    for a, b in zip(rings, rings[1:]):
        sm.bridge(a, b)
    for r in (rings[0], rings[-1]):
        sm.f(*r)


BEAM_FILLET = [(0.150, 0.440), (0.257, 0.441), (0.270, 0.462), (0.322, 0.506), (0.150, 0.506)]   # wedge under the beam
BEAM_FILLET_Z = 0.066


def add_beam_fillet(sm, sx):
    front = [(sx * x, y, -BEAM_FILLET_Z) for x, y in BEAM_FILLET]; back = [(sx * x, y, BEAM_FILLET_Z) for x, y in BEAM_FILLET]
    sm.f(*front); sm.f(*reversed(back))
    for i in range(len(front)):
        j = (i + 1) % len(front)
        sm.f(front[i], front[j], back[j], back[i])


def add_drum(sm, sx):
    cx = sx * PIN_X
    rings = []
    for r, z in DRUM_PROFILE:
        rings.append([(cx + r * math.cos(math.radians(11.25 + 22.5 * k)), PIN_Y + r * math.sin(math.radians(11.25 + 22.5 * k)), z)
                      for k in range(DRUM_SEG)])
    for a, b in zip(rings, rings[1:]):
        sm.bridge(a, b)
    for r in (rings[0], rings[-1]):
        # grid fill works in any plane: remap to (x, y=const, z) order is fine since the ring is planar
        sm.grid_fill(r)


# --------------------------------------------------------------------------- arm (right side, then mirrored)


def arm_section(st):
    """12-point stepped section at one station, loop order"""
    pin, pst, pout = (np.array(p, float) for p in st)
    n = pout - pin; n /= np.linalg.norm(n)
    I0, Ip = pin, pin + n * CH_IN
    Op, O0 = pout - n * CH_OUT, pout
    top = [(I0, STRIP_Z - CH_IN), (Ip, STRIP_Z), (pst, STRIP_Z), (pst, BODY_Z), (Op, BODY_Z), (O0, BODY_Z - CH_OUT)]
    loop = top + [(p, -z) for p, z in reversed(top)]
    return [(p[0], p[1], z) for p, z in loop]


def add_arm_body(sm):
    secs = [arm_section(st) for st in ARM_ST]
    for a, b in zip(secs, secs[1:]):
        sm.bridge(a, b)
    for q in (secs[0], secs[-1]):                    # end caps across the depth (sections are bent, not one plane)
        sm.f(q[0], q[1], q[10], q[11]); sm.f(q[1], q[2], q[9], q[10])
        sm.f(q[2], q[4], q[7], q[9]); sm.f(q[4], q[5], q[6], q[7])
        sm.f(q[2], q[3], q[4]); sm.f(q[9], q[7], q[8])   # the strip/body step closes with two triangles


def add_boss(sm):
    prof = [(BOSS_R0, -BOSS_Z), (BOSS_R1 - BOSS_CH, -BOSS_Z), (BOSS_R1, -BOSS_Z + BOSS_CH),
            (BOSS_R1, BOSS_Z - BOSS_CH), (BOSS_R1 - BOSS_CH, BOSS_Z), (BOSS_R0, BOSS_Z)]
    rings = []
    for i in range(BOSS_SEG + 1):
        a = math.radians(BOSS_A0 + (BOSS_A1 - BOSS_A0) * i / BOSS_SEG)
        rings.append([(PIN_X + r * math.cos(a), PIN_Y + r * math.sin(a), z) for r, z in prof])
    for a, b in zip(rings, rings[1:]):
        sm.bridge(a, b)
    for r in (rings[0], rings[-1]):
        sm.f(r[0], r[1], r[4], r[5]); sm.f(r[1], r[2], r[3], r[4])


def add_web(sm):
    front = [(x, y, -WEB_Z) for x, y in WEB]; back = [(x, y, WEB_Z) for x, y in WEB]
    sm.f(*front); sm.f(*reversed(back))
    n = len(WEB)
    for i in range(n):
        j = (i + 1) % n
        sm.f(front[i], front[j], back[j], back[i])


def rect8(x0, x1, z0, z1, k, y):
    return [(x0, y, z0 + k), (x0 + k, y, z0), (x1 - k, y, z0), (x1, y, z0 + k),
            (x1, y, z1 - k), (x1 - k, y, z1), (x0 + k, y, z1), (x0, y, z1 - k)]


def add_plate(sm):
    rings = [rect8(PLATE_X0 + ins_in, PLATE_X1 - ins, -PLATE_Z + ins, PLATE_Z - ins, PLATE_K, y)
             for y, ins_in, ins in PLATE_RINGS]
    for a, b in zip(rings, rings[1:]):
        sm.bridge(a, b)
    sm.cap3(rings[0]); sm.cap3(rings[-1])


def build_arm_r():
    sm = SpecMesh()
    add_boss(sm); add_arm_body(sm); add_web(sm); add_plate(sm)
    return sm.finish(f"{HERO}_Arm_R_01", offset=(PIN_X, PIN_Y, 0.0))


def mirrored_mesh(src, name):
    me = src.copy(); me.name = name
    bm = bmesh.new(); bm.from_mesh(me)
    for v in bm.verts:
        v.co.x = -v.co.x
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.normal_update()
    bm.to_mesh(me); bm.free()
    return me


def build_block(name, d):
    sm = SpecMesh()
    hx, hz, h, c = d["hx"], d["hz"], d["h"], d["ch"]
    r0 = rect8(-hx, hx, -hz, hz, c, 0.0)
    r1 = rect8(-hx, hx, -hz, hz, c, h - c)
    r2 = rect8(-hx + c, hx - c, -hz + c, hz - c, c, h)
    sm.bridge(r0, r1); sm.bridge(r1, r2); sm.cap3(r2)     # bottom face sits on the plate / riser: omitted
    return sm.finish(name)


# --------------------------------------------------------------------------- visibility (hidden faces)


def fib_dirs(n):
    out = []
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n; r = math.sqrt(max(0, 1 - y * y)); th = math.pi * (3 - math.sqrt(5)) * i
        out.append(Vector((r * math.cos(th), r * math.sin(th), y)))
    return out


def scene_bvh(objs):
    verts, polys = [], []
    for o in objs:
        m = o.matrix_world; b = len(verts)
        verts.extend(m @ v.co for v in o.data.vertices)
        polys.extend([b + i for i in p.vertices] for p in o.data.polygons)
    return BVHTree.FromPolygons(verts, polys)


def set_pose(arms, deg):
    arms["L"].rotation_euler = (0, math.radians(deg), 0)
    arms["R"].rotation_euler = (0, -math.radians(deg), 0)
    bpy.context.view_layer.update()


def visible_faces(obj, tree, dirs, box):
    """face indices of obj that see open space in at least one direction from at least one sample"""
    mw = obj.matrix_world; nm = mw.to_3x3().inverted().transposed()
    (x0, y0, z0), (x1, y1, z1) = box
    vis = set()
    for p in obj.data.polygons:
        n = (nm @ p.normal).normalized()
        c = mw @ p.center
        pts = [c] + [c + ((mw @ obj.data.vertices[i].co) - c) * 0.8 for i in p.vertices]
        found = False
        for q in pts:
            o = q + n * 5e-4
            for d in dirs:
                if d.dot(n) <= 0.05: continue
                # exit distance from the review box; the floor (Blender z = 0) blocks
                ts = []
                for k, lo, hi in ((0, x0, x1), (1, y0, y1), (2, z0, z1)):
                    if d[k] > 1e-9: ts.append((hi - o[k]) / d[k])
                    elif d[k] < -1e-9: ts.append((lo - o[k]) / d[k])
                t_exit = min(ts)
                if d.z < -1e-9 and -o.z / d.z < t_exit: continue
                hit = tree.ray_cast(o, d, t_exit)
                if hit[0] is None:
                    found = True; break
            if found: break
        if found: vis.add(p.index)
    return vis


def delete_hidden(parts, arms, only=None):
    dirs = fib_dirs(96)
    box = ((-2.0, -4.69 - 2.0, -1.0), (2.0, -4.69 + 2.0, 2.6))       # below the floor: floor hits always count
    keep = {o.name: set() for o in parts}
    for deg in (0.0, RELEASE_DEG):
        set_pose(arms, deg)
        tree = scene_bvh(parts)
        for o in parts:
            keep[o.name] |= visible_faces(o, tree, dirs, box)
    set_pose(arms, 0.0)
    report = {}
    for o in parts:
        if only and not any(k in o.name for k in only): continue
        if o.data.users > 1 and o.data.name in report: continue
        bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
        kill = [f for f in bm.faces if f.index not in keep[o.name]]
        report[o.data.name] = len(kill)
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(o.data); bm.free()
    return report


# --------------------------------------------------------------------------- shading


def apply_shading(obj, sharp_deg=50.0):
    bm = bmesh.new(); bm.from_mesh(obj.data)
    lim = math.radians(sharp_deg)
    for e in bm.edges:
        e.smooth = not (e.is_manifold and e.calc_face_angle(0.0) > lim) and not e.is_boundary
    for f in bm.faces: f.smooth = True
    bm.to_mesh(obj.data); bm.free()
    mod = obj.modifiers.new("WN", 'WEIGHTED_NORMAL'); mod.mode = 'FACE_AREA'; mod.weight = 50
    mod.keep_sharp = True; mod.thresh = 0.01
    for o in bpy.context.view_layer.objects: o.select_set(False)
    bpy.context.view_layer.objects.active = obj; obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)


# --------------------------------------------------------------------------- materials, assembly


def mat(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b: b.inputs["Base Color"].default_value = (*rgb, 1.0)
    return m


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 1.0
    col = bpy.data.collections.new("Cradle_v2"); sc.collection.children.link(col)
    m_metal = mat("M_Cradle_Metal", (0.18, 0.19, 0.21))
    m_amber = mat("M_Cradle_Amber", (0.75, 0.36, 0.02))

    def obj(name, me, parent=None, loc_spec=(0, 0, 0), m=m_metal):
        o = bpy.data.objects.new(name, me); col.objects.link(o)
        if not me.materials: me.materials.append(m)
        o.parent = parent; o.location = to_blender(loc_spec)
        return o
    base = obj(f"{HERO}_Base_01", build_base(), None, (0, 0, CZ))
    arm_r_me = build_arm_r()
    arm_l_me = mirrored_mesh(arm_r_me, f"{HERO}_Arm_L_01")
    arm_r = obj(f"{HERO}_Arm_R_01", arm_r_me, base, (PIN_X, PIN_Y, 0))
    arm_l = obj(f"{HERO}_Arm_L_01", arm_l_me, base, (-PIN_X, PIN_Y, 0))
    pad_me = build_block(f"{HERO}_Pad_01", PAD)
    riser_me = build_block(f"{HERO}_Riser_01", RISER)
    pad_r = obj(f"{HERO}_Pad_R_01", pad_me, arm_r, (PAD_X - PIN_X, PLATE_TOP - PIN_Y, 0), m_amber)
    riser_l = obj(f"{HERO}_Riser_L_01", riser_me, arm_l, (-(PAD_X - PIN_X), PLATE_TOP - PIN_Y, 0))
    bpy.context.view_layer.update()
    arms = {"L": arm_l, "R": arm_r}
    removed = delete_hidden([base, arm_l, arm_r, pad_r, riser_l], arms, only=("Base", "Arm_R", "Pad_R", "Riser_L"))
    # Arm_L stays the exact mirror of the final Arm_R (hidden faces decided on the right side)
    old_l = arm_l.data
    arm_l.data = mirrored_mesh(arm_r.data, f"{HERO}_Arm_L_01")
    bpy.data.meshes.remove(old_l)
    arm_l.data.name = f"{HERO}_Arm_L_01"
    apply_shading(base, 40.0)                     # plinth/octagon corners (~45 deg) read crisp
    for o in (arm_r, arm_l, pad_r, riser_l):
        apply_shading(o)
    # second pad instance only now: a modifier cannot be applied to multi-user mesh data
    pad_l = obj(f"{HERO}_Pad_L_01", pad_me, arm_l, (-(PAD_X - PIN_X), PLATE_TOP + RISER["h"] - PIN_Y, 0), m_amber)
    bpy.context.view_layer.update()
    return [base, arm_l, arm_r, pad_r, riser_l, pad_l], arms, removed


def main():
    parts, arms, removed = build()
    print("HIDDEN faces deleted:", removed)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, compress=True)
    print("SAVED", SAVE)


if __name__ == "__main__":
    main()
