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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cradle_v2_uv as UV

HERO = "LAB_HERO_Cradle"
SAVE = "D:/AI_Labyrinth/Blender/Source/Heroes/Cradle/LAB_HERO_Cradle_v2.blend"
CZ = 4.69                                   # cradle origin z (spec)

# --------------------------------------------------------------------------- parameters (HERO_SPEC §3)
PIN_X, PIN_Y = 0.385, 0.637                 # pin axes (+-x), axis parallel to Z
RELEASE_DEG = 75.0

# tier 1: 16-gon plan (+x+z quadrant, CCW), mirrored to all quadrants
T1_Q = [(1.214, 0.442), (1.027, 0.608), (0.632, 1.028), (0.490, 1.214)]
T1_RINGS = [(0.016, 0.000), (0.000, 0.016), (0.000, 0.162), (0.036, 0.203)]   # (inset, y); last = band outer edge
T1_TOP, TRAY_FLOOR = 0.203, 0.162
# tier-1 top (Step 3b, AI height map): an outer band at y 0.203, a 20 mm slope, then a sunken ring at y 0.176
# down to the tier-2 wall; the trays are cut 14 mm deeper into that ring. Band inner edge inset per T1 edge type.
T1_EDGE_TYPES = ["F", "D", "F", "Z", "F", "D", "F", "X", "F", "D", "F", "Z", "F", "D", "F", "X"]   # edge i: vertex i -> i+1
BAND_IN = {"X": 0.130, "Z": 0.110, "D": 0.134, "F": 0.130}
BAND_SLOPE, RING_Y = 0.020, 0.176
SECTOR_EDGE = {0: 15, 1: 1, 2: 3, 3: 5, 4: 7, 5: 9, 6: 11, 7: 13}          # tier-2 face k -> parallel tier-1 edge
SECTOR_START = {0: 15, 1: 0, 2: 3, 3: 4, 4: 7, 5: 8, 6: 11, 7: 12}         # first tier-1 vertex of each sector

# tier 2 and inner octagons: (flat X, flat Z, flat diagonal, y); all carry the tray-end points
T2_RINGS = [(0.863, 0.843, 0.850, 0.176), (0.863, 0.843, 0.850, 0.246), (0.842, 0.827, 0.818, 0.274),
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
# turntable: continuous ring (the AI's rim notches are classed as AI junk, owner decision Step 3c)
CIRCLES = [((0.516, 0.516), 0.253), ((0.515, 0.515), 0.301), ((0.497, 0.497), 0.333), ((0.385, 0.385), 0.333),
           ((0.385, 0.385), 0.356), ((0.293, 0.267), 0.356), ((0.293, 0.267), 0.384), ((0.285, 0.259), 0.392)]
COL_Q = [(0.258, 0.052), (0.180, 0.085), (0.174, 0.149), (0.118, 0.224)]
COL_YS = [0.392, 0.440, 0.600, 0.700, 0.724]
COL_TOP_Q = [(0.240, 0.045), (0.168, 0.074), (0.162, 0.128), (0.104, 0.191)]
COLLAR_Q = [(0.167, 0.030), (0.167, 0.102), (0.117, 0.152), (0.030, 0.152)]
LEDGE_Y, COLLAR_Y1 = 0.761, 0.810
HUB = [((0.150, 0.150), 0.812), ((0.150, 0.150), 0.860), ((0.130, 0.130), 0.884)]

# hinge beam (right side; mirrored), stations along x: (x, bottom y); section bands in z
BEAM_ST = [(0.120, 0.500, 0.090), (0.270, 0.500, 0.090), (0.322, 0.502, 0.120), (0.400, 0.508, 0.120)]   # (x, underside y, lower-band half depth): band widens under the drum (Step 3b)
BEAM_TOP = 0.755
# drums and pin caps: (radius, z) rings along the pin axis, front (-z) to back (+z)
DRUM_R, DRUM_SEG = 0.118, 16
DRUM_PROFILE = [(0.065, -0.2404), (0.080, -0.228), (0.080, -0.190), (0.110, -0.190), (0.118, -0.182),
                (0.118, -0.153), (0.118, -0.120), (0.118, -0.090), (0.118, 0.090), (0.118, 0.120),
                (0.118, 0.153),                             # split at the beam band depths: buried parts are deleted
                (0.118, 0.195), (0.110, 0.203), (0.100, 0.203), (0.085, 0.2219)]

# arm (right side, cradle-local), stations (inner edge, step, outer edge) in the front plane
def _arc(r, deg):
    return (PIN_X + r * math.cos(math.radians(deg)), PIN_Y + r * math.sin(math.radians(deg)))
STRIP_Z, BODY_Z, CH_IN, CH_OUT = 0.110, 0.151, 0.015, 0.015       # rail edge chamfer 15 mm (AI bevel)
CHANNEL_Z = 0.067                          # inner-face channel half width (Step 3b), between two rails
_S0 = (_arc(0.140, 97), _arc(0.140, 62), _arc(0.160, 6.5))           # outer: on the boss rim, AI outer contour
_S1 = ((0.421, 0.901), (0.509, 0.898), (0.671, 0.819))
_S0B = tuple(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(_S0, _S1))
# (inner edge = rail face, step, outer edge, strip half depth, channel depth). Root full depth up to y ~0.84;
# inner edge on the rails (Step 3 had traced the channel floor); channel y 0.99 .. 1.54, 35-40 mm deep.
ARM_ST = [
    (*_S0, BODY_Z, 0.0),
    (*_S0B, STRIP_Z, 0.0),                     # full depth only at the root: AI step ~y 0.78 (inner) .. 0.86 (outer)
    (*_S1, STRIP_Z, 0.0),
    ((0.424, 0.981), (0.524, 0.983), (0.709, 1.009), STRIP_Z, 0.0),
    ((0.417, 0.995), (0.521, 0.997), (0.708, 1.017), STRIP_Z, 0.040),
    ((0.397, 1.126), (0.489, 1.126), (0.689, 1.126), STRIP_Z, 0.037),
    ((0.385, 1.271), (0.454, 1.271), (0.666, 1.271), STRIP_Z, 0.036),
    ((0.377, 1.372), (0.430, 1.372), (0.654, 1.372), STRIP_Z, 0.035),
    ((0.375, 1.500), (0.433, 1.500), (0.640, 1.500), STRIP_Z, 0.035),
    ((0.398, 1.550), (0.435, 1.550), (0.592, 1.550), STRIP_Z, 0.0),
]
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


def _plane2d(pts):
    P = np.array(pts, float)
    nrm = np.zeros(3)
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        nrm += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
    ax = int(np.argmax(np.abs(nrm)))
    Q = P[:, [(ax + 1) % 3, (ax + 2) % 3]]
    return Q[:, ::-1] if nrm[ax] < 0 else Q                # counter-clockwise


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _seg_cross(p1, p2, p3, p4):
    d1, d2 = _cross(p3, p4, p1), _cross(p3, p4, p2); d3, d4 = _cross(p1, p2, p3), _cross(p1, p2, p4)
    return (d1 * d2 < -1e-14) and (d3 * d4 < -1e-14)


def quad_fill(pts):
    """split a simple planar polygon into quads that follow its outline (ear-style: cut off 4 consecutive
    vertices whose quad is convex, empty and whose closing diagonal stays inside); a triangle only when needed"""
    Q = _plane2d(pts); idx = list(range(len(Q))); out = []
    def inside_empty(q):
        for j in idx:
            if j in q: continue
            if all(_cross(Q[q[k]], Q[q[(k + 1) % len(q)]], Q[j]) >= -1e-12 for k in range(len(q))): return False
        a, b = Q[q[-1]], Q[q[0]]
        for k in range(len(idx)):
            e0, e1 = idx[k], idx[(k + 1) % len(idx)]
            if e0 in (q[0], q[-1]) or e1 in (q[0], q[-1]): continue
            if _seg_cross(a, b, Q[e0], Q[e1]): return False
        return True
    def quality(q):
        worst = 0.0
        for k in range(4):
            a, b, c = Q[q[k - 1]], Q[q[k]], Q[q[(k + 1) % 4]]
            u, w = a - b, c - b
            ang = math.degrees(math.acos(max(-1, min(1, (u @ w) / (np.linalg.norm(u) * np.linalg.norm(w) + 1e-12)))))
            worst = max(worst, abs(ang - 90))
        return worst
    guard = 0
    while len(idx) > 4 and guard < 1000:
        guard += 1; best = None
        for k in range(len(idx)):
            q = [idx[(k + j) % len(idx)] for j in range(4)]
            if any(_cross(Q[q[j - 1]], Q[q[j]], Q[q[(j + 1) % 4]]) <= 1e-12 for j in range(4)): continue
            if not inside_empty(q): continue
            sc = quality(q)
            if best is None or sc < best[0]: best = (sc, k, q)
        if best is None:                                    # no valid quad: clip one triangle ear
            for k in range(len(idx)):
                t = [idx[k - 1], idx[k], idx[(k + 1) % len(idx)]]
                if _cross(Q[t[0]], Q[t[1]], Q[t[2]]) <= 1e-12 or not inside_empty(t): continue
                out.append(tuple(t)); idx.pop(k); break
            else:
                break
            continue
        _, k, q = best
        out.append(tuple(q))
        for j in sorted([(k + 1) % len(idx), (k + 2) % len(idx)], reverse=True): idx.pop(j)
    if len(idx) == 4 and all(_cross(Q[idx[j - 1]], Q[idx[j]], Q[idx[(j + 1) % 4]]) > 1e-12 for j in range(4)):
        out.append(tuple(idx))
    elif len(idx) == 4:                                     # concave remainder: split on the inner diagonal
        r = next(j for j in range(4) if _cross(Q[idx[j - 1]], Q[idx[j]], Q[idx[(j + 1) % 4]]) <= 1e-12)
        out += [(idx[r], idx[(r + 1) % 4], idx[(r + 2) % 4]), (idx[r], idx[(r + 2) % 4], idx[(r + 3) % 4])]
    elif len(idx) == 3:
        out.append(tuple(idx))
    return out


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
        if len(vs) > 4:                                   # planar n-gon: quad-first fill that follows the outline
            for poly in quad_fill([tuple(v.co) for v in vs]):
                try:
                    fc = self.bm.faces.new([vs[i] for i in poly]); fc.smooth = True
                    if len(poly) == 3: self.join.append(fc)
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
        bm.normal_update()
        # concave quads (e.g. the 1 mm-wide column-top ledge, Step 4): split on the reflex diagonal, so the
        # triangulation (bake, UVs, engine) cannot fold the face over itself
        for f in [f for f in bm.faces if len(f.verts) == 4]:
            vs = [v.co for v in f.verts]; n = f.normal
            reflex = [i for i in range(4) if (vs[i] - vs[i - 1]).cross(vs[(i + 1) % 4] - vs[i]).dot(n) < -1e-12]
            if reflex:
                i = reflex[0]
                bmesh.ops.connect_verts(bm, verts=[f.verts[i], f.verts[(i + 2) % 4]])
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


def poly_offset_var(poly, ds):
    """CCW polygon (x, z), edge i (vertex i -> i+1) offset inward by ds[i]"""
    n = len(poly); lines = []
    for i in range(n):
        p = np.array(poly[i], float); q = np.array(poly[(i + 1) % n], float)
        e = q - p; e /= np.linalg.norm(e)
        lines.append((p + np.array([-e[1], e[0]]) * ds[i], e))
    out = []
    for i in range(n):
        p1, e1 = lines[i - 1]; p2, e2 = lines[i]
        t, _ = np.linalg.solve(np.array([e1, -e2]).T, p2 - p1)
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


def ledge_ring_xz():
    """tier-1 ledge ring (outer edge of the sunken ring), plan points only, no inserts"""
    return poly_offset_var(mirror_quadrants(T1_Q), [BAND_IN[t] + BAND_SLOPE for t in T1_EDGE_TYPES])


def diag_tray_ends(k):
    """(t start, t end) along diagonal tier-2 face k: projections of the ledge facet corners (Step 3c)"""
    C = octa_corners(*T2_RINGS[0][:3]); A = np.array(C[k]); B = np.array(C[(k + 1) % 8])
    e = (B - A) / np.linalg.norm(B - A)
    ei = SECTOR_EDGE[k]; led = ledge_ring_xz()
    p0, p1 = np.array(led[ei]), np.array(led[(ei + 1) % 16])      # ends of the parallel diagonal ledge edge
    return float((p0 - A) @ e), float((p1 - A) @ e)


def tray_fracs(k):
    L = base_face_lengths()[k]
    if FACE_TYPES[k].startswith("D"):
        ta, tb = diag_tray_ends(k)
        return ta / L, tb / L
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
    # tier 1: 16-gon walls with extra vertical edge lines at the tray ends (all quads), outer band, slope,
    # sunken ring at y 0.176 with the tray pockets (Step 3b)
    t2 = [t2_ring(*r) for r in T2_RINGS]
    for a, b in zip(t2, t2[1:]):
        sm.bridge(a, b)
    base = t2[0]
    C = octa_corners(*T2_RINGS[0][:3])
    t1 = mirror_quadrants(T1_Q)
    trays = {}; inserts = {}
    for k in range(8):
        e = np.array(C[(k + 1) % 8]) - np.array(C[k]); e /= np.linalg.norm(e)
        n = np.array([e[1], -e[0]])
        kind = "D" if FACE_TYPES[k].startswith("D") else FACE_TYPES[k]
        wf = TRAY_W[kind][0]
        L = float(np.linalg.norm(np.array(C[(k + 1) % 8]) - np.array(C[k])))
        ea, eb = tray_ends(k, L)
        A2 = np.array(C[k])
        pt = lambda t, w, y, A2=A2, e=e, n=n: (float((A2 + e * t + n * w)[0]), y, float((A2 + e * t + n * w)[1]))
        trays[k] = dict(e=e, n=n, a_o=ea[3], b_o=eb[3], wf=wf, pt=pt)
        # X / Z trays: tray-end corners projected along n onto the parallel tier-1 edge -> extra vertices on every
        # tier-1 ring. Diagonal trays end on the facet corners, so they need no extra vertices (Step 3c).
        t = FACE_TYPES[k]
        trays[k]["kind_ends"] = t
        if t in ("X", "Z"):
            ei = SECTOR_EDGE[k]; led = ledge_ring_xz()          # fraction measured on the ledge ring edge,
            v0 = np.array(led[ei]); v1 = np.array(led[(ei + 1) % 16])   # so the strip quads stay square there
            for tt in (ea[3], eb[3]):
                q = A2 + e * tt + n * wf
                f, _ = np.linalg.solve(np.array([v1 - v0, -n]).T, q - v0)
                inserts.setdefault(ei, []).append(float(f))
        else:
            ta, tb = diag_tray_ends(k)
            trays[k]["a_o"], trays[k]["b_o"] = ta, tb

    def t1_ring(ds, y):
        off = poly_offset_var(t1, ds)
        out = []; tags = []
        for i in range(16):
            out.append((off[i][0], y, off[i][1])); tags.append(("v", i))
            p0, p1 = np.array(off[i]), np.array(off[(i + 1) % 16])
            for f in sorted(inserts.get(i, [])):
                q = p0 + f * (p1 - p0); out.append((q[0], y, q[1])); tags.append(("p", i, f))
        return out, tags
    rings = [t1_ring([d] * 16, y)[0] for d, y in T1_RINGS]
    band_in, tags = t1_ring([BAND_IN[t] for t in T1_EDGE_TYPES], T1_TOP)
    ledge, _ = t1_ring([BAND_IN[t] + BAND_SLOPE for t in T1_EDGE_TYPES], RING_Y)
    rings += [band_in, ledge]
    for a, b in zip(rings, rings[1:]):
        sm.bridge(a, b)
    pos = {tg: i for i, tg in enumerate(tags)}
    N = len(ledge)
    # sector boundary midpoints (tier-2 corner -> ledge corner): every corner region becomes a hexagon = 2 quads
    mids = []
    for k in range(8):
        A = base[3 * k]; O = ledge[pos[("v", SECTOR_START[k])]]
        mids.append(((A[0] + O[0]) / 2, RING_Y, (A[2] + O[2]) / 2))
    for k in range(8):
        tr = trays[k]; pt = tr["pt"]; ei = SECTOR_EDGE[k]
        A = base[3 * k]; a = base[3 * k + 1]; b = base[3 * k + 2]; Bn = base[(3 * k + 3) % 24]
        i0 = pos[("v", SECTOR_START[k])]; i1 = pos[("v", SECTOR_START[(k + 1) % 8])]
        idx = [(i0 + j) % N for j in range(((i1 - i0) % N) + 1)]
        Lr = [ledge[i] for i in idx]
        if tr["kind_ends"] in ("X", "Z"):
            ins = [j for j, i in enumerate(idx) if tags[i][0] == "p" and tags[i][1] == ei]; ja, jb = ins[0], ins[1]
        else:
            ja, jb = idx.index(pos[("v", ei)]), idx.index(pos[("v", (ei + 1) % 16)])
        # straight tray ends (the AI's 14 mm-deep end bulge is below the depth rule -> normal map)
        a_t, b_t = pt(tr["a_o"], tr["wf"], RING_Y), pt(tr["b_o"], tr["wf"], RING_Y)
        a_f, b_f = (a[0], TRAY_FLOOR, a[2]), (b[0], TRAY_FLOOR, b[2])
        a_ff, b_ff = pt(tr["a_o"], tr["wf"], TRAY_FLOOR), pt(tr["b_o"], tr["wf"], TRAY_FLOOR)
        Mk, Mn = mids[k], mids[(k + 1) % 8]
        sm.f(*(Lr[:ja + 1] + [a_t, a, A, Mk]))                        # sunken ring, start corner (hexagon)
        sm.f(*(Lr[ja:jb + 1] + [b_t, a_t]))                           # strip outside the tray
        sm.f(*(Lr[jb:] + [Mn, Bn, b, b_t]))                           # sunken ring, end corner (hexagon)
        sm.f(a_f, b_f, b_ff, a_ff)                                    # tray floor
        sm.f(a_ff, b_ff, b_t, a_t)                                    # tray walls (14 mm, vertical)
        sm.f(a, a_f, a_ff, a_t)
        sm.f(b, b_t, b_ff, b_f)
        sm.f(a, b, b_f, a_f)                                          # tier-2 wall continues down to the floor
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


def beam_section(yb, zb=0.090):
    zm = 0.153
    return [(-zb, yb), (zb, yb), (zb, 0.560), (zm, 0.600), (zm, 0.700), (zb, 0.720), (zb, BEAM_TOP),
            (-zb, BEAM_TOP), (-zb, 0.720), (-zm, 0.700), (-zm, 0.600), (-zb, 0.560)]


def add_beam(sm, sx):
    rings = [[(sx * x, y, z) for z, y in beam_section(yb, zb)] for x, yb, zb in BEAM_ST]
    for a, b in zip(rings, rings[1:]):
        sm.bridge(a, b)
    for r in (rings[0], rings[-1]):
        sm.f(*r)


BEAM_FILLET = [(0.150, 0.440), (0.257, 0.441), (0.322, 0.506), (0.150, 0.506)]   # wedge under the beam: one quad (AI's <10 mm bend in the slope -> normal map)
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
    """16-point stepped section at one station: 12-point strip/body loop + 4 channel points on the inner face"""
    pin, pst, pout = (np.array(p, float) for p in st[:3])
    sz, ch = st[3], st[4]
    n = pout - pin; n /= np.linalg.norm(n)
    I0, Ip = pin, pin + n * CH_IN
    Op, O0 = pout - n * CH_OUT, pout
    top = [(I0, sz - CH_IN), (Ip, sz), (pst, sz), (pst, BODY_Z), (Op, BODY_Z), (O0, BODY_Z - CH_OUT)]
    loop = top + [(p, -z) for p, z in reversed(top)]
    loop += [(I0, -CHANNEL_Z), (I0 + n * ch, -CHANNEL_Z), (I0 + n * ch, CHANNEL_Z), (I0, CHANNEL_Z)]
    return [(p[0], p[1], z) for p, z in loop]


def add_arm_body(sm):
    secs = [arm_section(st) for st in ARM_ST]
    for a, b in zip(secs, secs[1:]):
        sm.bridge(a, b)
    for q in (secs[0], secs[-1]):                    # end caps across the depth (sections are bent, not one plane)
        sm.f(q[0], q[1], q[10], q[11], q[12], q[15]); sm.f(q[1], q[2], q[9], q[10])
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
        vw = [mw @ obj.data.vertices[i].co for i in p.vertices]
        pts = [c]
        for k in range(len(vw)):                          # corners and edge midpoints, 2 mm inside the face
            for q in (vw[k], (vw[k] + vw[(k + 1) % len(vw)]) / 2):
                d = c - q
                pts.append(q + d.normalized() * min(0.002, d.length * 0.5) if d.length > 1e-9 else q)
        for k in range(1, len(vw) - 1):                    # interior grid, ~2 cm spacing, per fan triangle
            a, b, cc = vw[0], vw[k], vw[k + 1]
            m = max(2, int(max((b - a).length, (cc - a).length, (cc - b).length) / 0.02))
            for i in range(1, m):
                for j in range(1, m - i):
                    pts.append(a + (b - a) * (i / m) + (cc - a) * (j / m))
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


def apply_shading(obj):
    """smooth faces + face-area weighted normals; hard edges were set by cradle_v2_uv.mark_edges"""
    bm = bmesh.new(); bm.from_mesh(obj.data)
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


UV_REDUCED = {"underside": 0.5, "back": 0.7}      # texel density factors for rarely seen islands (Step 4, option c)
UV_CLASS_AREA = {}


def uv_density(o, isl):
    """density factor per island: undersides (facing down in the closed and the released pose) x0.5;
    Base faces on the back half facing back (spec +Z, away from the front / approach side) x0.7"""
    a = sum(f.calc_area() for f in isl)
    n = sum((f.normal * f.calc_area() for f in isl), Vector()).normalized()
    c = sum((o.matrix_world @ f.calc_center_median() * f.calc_area() for f in isl), Vector()) / max(a, 1e-12)
    ns = [n]
    if "Arm" in o.name or "Pad" in o.name or "Riser" in o.name:            # also the released pose (arms turn about Y)
        s = -1 if "_R_" in o.name else 1
        ns.append(Matrix.Rotation(math.radians(s * RELEASE_DEG), 3, 'Y') @ n)
    cls = None
    if all(m.z < -0.5 for m in ns):
        cls = "underside"
    elif "Base" in o.name and -n.y > 0.5 and (-c.y - CZ) > 0.2:
        cls = "back"
    k = f"{o.name.replace(HERO + '_', '')}:{cls}"
    UV_CLASS_AREA[k] = UV_CLASS_AREA.get(k, 0.0) + a
    return UV_REDUCED.get(cls, 1.0)


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
    # Step 4: hard edges, seams, UVs on the unique meshes (Arm_L shares Arm_R's UV space, mirrored)
    uv_report = UV.unwrap_and_pack([base, arm_r, pad_r, riser_l], uv_density)
    uv_report["class_area_m2"] = {k: round(v, 3) for k, v in sorted(UV_CLASS_AREA.items())}
    old_l = arm_l.data
    arm_l.data = mirrored_mesh(arm_r.data, f"{HERO}_Arm_L_01")
    bpy.data.meshes.remove(old_l)
    arm_l.data.name = f"{HERO}_Arm_L_01"
    for o in (base, arm_r, arm_l, pad_r, riser_l):
        apply_shading(o)
    # second pad instance only now: a modifier cannot be applied to multi-user mesh data
    pad_l = obj(f"{HERO}_Pad_L_01", pad_me, arm_l, (-(PAD_X - PIN_X), PLATE_TOP + RISER["h"] - PIN_Y, 0), m_amber)
    bpy.context.view_layer.update()
    return [base, arm_l, arm_r, pad_r, riser_l, pad_l], arms, removed, uv_report


def main():
    parts, arms, removed, uv_report = build()
    print("HIDDEN faces deleted:", removed)
    print("UV:", uv_report)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, compress=True)
    print("SAVED", SAVE)


if __name__ == "__main__":
    main()
