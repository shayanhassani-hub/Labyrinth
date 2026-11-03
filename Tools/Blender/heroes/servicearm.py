"""
Labyrinth VR -- Hero 01b, ceiling service arm (LAB_HERO_ServiceArm_*), hero workflow v3 (Blender-textured).

Sizes, hinges and poses: Documentation/HERO_SPEC.md §4 (kinematics in servicearm_kin.py). Look: the owner's concept
Documentation/References/ServiceArm/servicearm_front.jpg (master for look and detail) and servicearm_ortho_side.jpg
(proportions). Build notes, feature inventory and every deviation: Documentation/Heroes/ServiceArm_BUILD.md.

Parts (one mesh each, origin on its hinge, modelled in the STOWED pose = all joint angles 0; Unity axes in the
comments, the mesh data in Blender axes via EXPORT_CONTRACT x -> -x, y -> z, z -> -y):
  LAB_HERO_ServiceArm_Mount_01     ceiling plate (0.40 x 0.025), octagonal adapter, 4 hex nuts      origin ceiling face
  LAB_HERO_ServiceArm_Turret_01    bearing disc d 0.26 x 0.07, shoulder bracket (-X), cap, side boss, cable connector,
                                   cable swivel on the shoulder axis, first cable segment             yaw (Y)
  LAB_HERO_ServiceArm_UpperArm_01  0.12 x 0.12 link, shoulder lug (r 0.044, clears the turret), slotted cap (+X),
                                   elbow caps, cable segment with a slack loop over the elbow, 2 clips   pitch (X)
  LAB_HERO_ServiceArm_Forearm_01   0.10 x 0.10 link beside the upper arm (+X 0.12), elbow disc with cap and the
                                   elbow cable swivel, cable segment with a loop over the wrist, 2 clips   pitch (X)
  LAB_HERO_ServiceArm_Wrist_01     0.09 x 0.10 x 0.10 knuckle (+X 0.10), cap, wrist swivel, roll neck, cable end
  LAB_HERO_ServiceArm_ToolHead_01  steel collar, ochre block 0.14 x 0.10 with the concept's side notch, steel pin  roll (Z)

Cables: each segment is part of the link it rides on (rigid, no skinning). Consecutive segments meet on the joint's
hinge axis at a small swivel (points on the axis don't move relative to either link), so the cable stays continuous
in every pose; the loops are routed through the sectors the neighbouring link never sweeps (servicearm_check.py
clearance proves it).

Construction as the Gate (gate.GateMesh): chamfered prisms, quads on the walls, flat regions filled and joined back to
quads; intersecting shells; faces hidden inside a part's own shells are deleted by a ray test (self only: hidden in
every pose). Hard edges by face kind and angle (gate.hard_edge_keys) = UV seams; face-weighted normals.

Run:  blender -b --factory-startup -P Tools/Blender/heroes/servicearm.py [-- blockout]   (build + save)
Checks and renders: servicearm_check.py.
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
import gate as G                             # GateMesh, hard_edge_keys, apply_shading, polygon offset
import cradle_v2 as CV                       # fib_dirs
import cradle_v2_uv as UV
import servicearm_kin as K

HERO = "LAB_HERO_ServiceArm"
SAVE = "D:/AI_Labyrinth/Blender/Source/Heroes/ServiceArm/LAB_HERO_ServiceArm_v1.blend"
SAVE_H0 = "D:/AI_Labyrinth/Blender/Source/Heroes/ServiceArm/LAB_HERO_ServiceArm_h0.blend"
FLAT, CHAMFER, ROUND = G.FLAT, G.CHAMFER, G.ROUND

MATS = [("M_ServiceArm_Paint", (0.10, 0.13, 0.16)), ("M_ServiceArm_Polymer", (0.017, 0.018, 0.020)),
        ("M_ServiceArm_Steel", (0.50, 0.51, 0.53)), ("M_ServiceArm_Ochre", (0.34, 0.19, 0.04)),
        ("M_ServiceArm_Cable", (0.20, 0.21, 0.22))]
PAINT, POLYMER, STEEL, OCHRE, CABLE = range(5)

X, Y, Z = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
O = np.zeros(3)

# --------------------------------------------------------------------------- dimensions (Unity metres, part-local)
CH = 0.006                                    # large-edge chamfer (links, plate, disc)
# H1b (owner review 2026-11-03: "thin and spindly", stowed layer may go to y 3.60): taller stack (turret hinge 0.07
# under the ceiling, shoulder 0.16 under the turret: ceiling -> shoulder axis 0.23, concept ~0.25), links 0.16 / 0.14
# tall, joints r 0.08-0.10. Widths and the X offsets (0.12 / 0.10) stay as HERO_SPEC.
# Mount
PLATE_H, PLATE_T, PLATE_CLIP = 0.20, 0.035, 0.012
FRUST_TOP, FRUST_TOP_CLIP, FRUST_BOT, FRUST_BOT_CLIP, FRUST_Y0, FRUST_Y1 = 0.170, 0.060, 0.140, 0.050, 0.030, 0.068
NUT_AT, NUT_AF, NUT_T = 0.172, 0.030, 0.016
# Turret (origin 0.07 below the ceiling)
DISC_R, DISC_Y0, DISC_Y1 = 0.13, -0.002, -0.050       # bearing disc d 0.26 ...
HUB_R, HUB_Y1 = 0.080, -0.072                         # ... over a narrower hub (the stowed forearm passes under the disc)
BOSS_R, BOSS_Y, BOSS_X1 = 0.015, -0.026, 0.145     # on the disc side, clear of its chamfers
SHOULDER_Y = -0.16                            # = T_UPPER
CHEEK_X0, CHEEK_X1, CHEEK_R = -0.068, -0.118, 0.100   # the concept's big shoulder housing (-X), lobe r 0.10
CHEEK_CAP_R, CHEEK_CAP_X1 = 0.068, -0.134
SWIVEL_X, SWIVEL_R = -0.160, 0.016            # cable swivel on the shoulder axis (-X side)
CONN = dict(x0=-0.100, x1=-0.182, y0=-0.018, y1=-0.062, hz=0.024)
# UpperArm
UA_HW, UA_HH, LUG_R = 0.06, 0.08, 0.08        # 0.12 wide x 0.16 tall; the root is the full r 0.08 end (8 mm under the hub)
SLOT_CAP_R, SLOT_CAP_T = 0.064, 0.018         # the concept's big slotted cap on the shoulder (+X, camera side)
ELBOW_CAP_R = 0.085
# Forearm
FA_HW, FA_HH = 0.05, 0.07                     # 0.10 wide x 0.14 tall
ELBOW_DISC_R, ELBOW_DISC_X1, ELBOW_HUB_R, ELBOW_HUB_X1 = 0.095, 0.072, 0.045, 0.090
P_X = 0.128                                    # elbow swivel: forearm-local x (upper-local 0.248)
# Wrist
WR_HW, WR_R, WR_Z1 = 0.045, 0.065, -0.060
WR_CAP_R, WR_CAP_X1 = 0.046, 0.062
Q_X = 0.090                                    # wrist swivel: wrist-local x (forearm-local 0.190)
NECK_R, NECK_Z0, NECK_Z1 = 0.050, -0.055, -0.075
# ToolHead (origin TOOL_Z below the wrist axis)
COLLAR_R, COLLAR_Z1 = 0.044, -0.035
BLOCK_HY = 0.05
BLOCK = [(-0.07, -0.145), (-0.05, -0.165), (0.055, -0.165), (0.07, -0.15), (0.07, -0.135), (0.035, -0.12),
         (0.035, -0.075), (0.07, -0.06), (0.07, -0.03), (-0.07, -0.03)]          # (x, z): the concept's side notch
PIN_R, PIN_Z0, PIN_Z1 = 0.018, -0.160, -0.200
# cables: thick corrugated conduit + thin black cable beside it (the concept's pair)
CABLE_R, CABLE_N = 0.012, 8
THIN_R, THIN_N, THIN_OFF = 0.0055, 6, 0.020
SEG = dict(big=32, mid=24, small=16, tiny=12)


# --------------------------------------------------------------------------- mesh helpers


class ArmMesh(G.GateMesh):
    pass


def arc(c, r, a0, a1, n):
    """points on an arc in a 2D plane, from a0 to a1 (deg), n segments (n + 1 points)"""
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


def circle(c, r, n, phase=0.5):
    return [(c[0] + r * math.cos(2 * math.pi * (k + phase) / n), c[1] + r * math.sin(2 * math.pi * (k + phase) / n)) for k in range(n)]


def signed_area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))


def clean(poly, kinds):
    """drop repeated points (arc joins); keep the kind of the edge that starts at each kept point"""
    P, Kd = [], []
    for p, k in zip(poly, kinds):
        if P and math.dist(p, P[-1]) < 1e-7:
            Kd[-1] = k if k == ROUND else Kd[-1]; continue
        P.append(p); Kd.append(k)
    if math.dist(P[0], P[-1]) < 1e-7: P.pop(); Kd.pop()
    return P, Kd


def profile(*pieces):
    """pieces: (points, kind) -- consecutive pieces share end points; kind applies to the edges inside a piece and to
    the edge from its last point to the next piece's first point (FLAT for joins)"""
    pts, kinds = [], []
    for pp, k in pieces:
        for i, p in enumerate(pp):
            pts.append(p); kinds.append(k if i < len(pp) - 1 else FLAT)
    return clean(pts, kinds)


def pt(frame, u, v, d):
    o, U, V, N = frame
    return tuple(np.asarray(o, float) + u * U + v * V + d * N)


def loop(frame, poly, d):
    return [pt(frame, u, v, d) for u, v in poly]


def prism(sm, poly, frame, d0, d1, kinds=None, ch0=CH, ch1=CH, cap0=True, cap1=True, round_all=False):
    """poly (u, v) extruded along the frame normal from d0 to d1 (d1 > d0), 45 deg chamfers ch0 / ch1 on the two end
    edges; kinds per edge (edge i -> i+1) for the walls"""
    if kinds is None: kinds = [ROUND if round_all else FLAT] * len(poly)
    # an end built without a chamfer is the one embedded in the parent shell (or against the ceiling): no cap there,
    # it would only be a buried face (and intersecting caps confuse the normal recalculation)
    cap0 = cap0 and ch0 > 0; cap1 = cap1 and ch1 > 0
    n = len(poly)
    a = loop(frame, G.offset(poly, ch0) if ch0 > 0 else poly, d0)
    b = loop(frame, poly, d0 + ch0)
    c = loop(frame, poly, d1 - ch1)
    e = loop(frame, G.offset(poly, ch1) if ch1 > 0 else poly, d1)
    keep = sm.kind
    if cap0: sm.kind = FLAT; sm.region([a])
    if ch0 > 0: sm.kind = CHAMFER; sm.tube([a, b])
    for i in range(n):
        j = (i + 1) % n
        sm.kind = kinds[i]; sm.f(b[i], b[j], c[j], c[i])
    if ch1 > 0: sm.kind = CHAMFER; sm.tube([c, e])
    if cap1: sm.kind = FLAT; sm.region([e])
    sm.kind = keep


def oriented(poly, kinds):
    """CCW copy of a polygon with its edge kinds carried along"""
    if signed_area(poly) >= 0: return poly, kinds
    n = len(poly)
    rp = poly[::-1]
    # reversed edge i: rp[i] -> rp[i+1] = poly[n-1-i] -> poly[n-2-i] = original edge (n-2-i)
    rk = [kinds[(n - 2 - i) % n] for i in range(n)]
    return rp, rk


def solid(sm, poly, kinds, frame, d0, d1, ch0=CH, ch1=CH, cap0=True, cap1=True):
    poly, kinds = oriented(poly, kinds)
    prism(sm, poly, frame, d0, d1, kinds, ch0, ch1, cap0, cap1)


def cylinder(sm, frame, c, r, n, d0, d1, ch0=0.003, ch1=0.003, cap0=True, cap1=True):
    poly = circle(c, r, n)
    solid(sm, poly, [ROUND] * n, frame, d0, d1, ch0, ch1, cap0, cap1)


def loft(sm, polyA, dA, polyB, dB, frame, kinds):
    """walls between two polygons of equal count (frustum)"""
    a = loop(frame, polyA, dA); b = loop(frame, polyB, dB); keep = sm.kind
    for i in range(len(a)):
        j = (i + 1) % len(a); sm.kind = kinds[i]; sm.f(a[i], a[j], b[j], b[i])
    sm.kind = keep


def clipped_square(h, c):
    """square half size h with 45 deg corner clips c (8 points, CCW in (u, v))"""
    return [(h, -h + c), (h, h - c), (h - c, h), (-h + c, h), (-h, h - c), (-h, -h + c), (-h + c, -h), (h - c, -h)]


def catmull(P, step=0.012):
    """centripetal Catmull-Rom (alpha 0.5: no cusps or overshoot with unevenly spaced points), sampled at ~step"""
    P = [np.asarray(p, float) for p in P]
    Q = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        t0 = 0.0; t1 = t0 + np.linalg.norm(p1 - p0) ** 0.5; t2 = t1 + np.linalg.norm(p2 - p1) ** 0.5
        t3 = t2 + np.linalg.norm(p3 - p2) ** 0.5
        n = max(1, int(np.linalg.norm(p2 - p1) / step))
        for k in range(n):
            t = t1 + (t2 - t1) * k / n
            A1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            A2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            A3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            B1 = (t2 - t) / (t2 - t0) * A1 + (t - t0) / (t2 - t0) * A2
            B2 = (t3 - t) / (t3 - t1) * A2 + (t - t1) / (t3 - t1) * A3
            out.append((t2 - t) / (t2 - t1) * B1 + (t - t1) / (t2 - t1) * B2)
    out.append(P[-1])
    res = [out[0]]
    for p in out[1:]:
        if np.linalg.norm(p - res[-1]) > 0.004: res.append(p)
    if np.linalg.norm(res[-1] - P[-1]) > 1e-9: res[-1] = P[-1]
    return simplify(res)


def simplify(path, turn=7.0, max_len=0.25):
    """keep a point when the direction has turned by > turn deg since the last kept point (or after max_len)"""
    keep = [path[0]]
    for i in range(1, len(path) - 1):
        a = path[i] - keep[-1]; b = path[i + 1] - path[i]
        ang = math.degrees(math.acos(max(-1, min(1, a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)))))
        if ang > turn or np.linalg.norm(path[i + 1] - keep[-1]) > max_len: keep.append(path[i])
    keep.append(path[-1])
    return keep


def tube(sm, path, r, n, mat):
    """tube along a sampled path (parallel-transport rings), flat end caps"""
    path = [np.asarray(p, float) for p in path]
    T = [path[1] - path[0]] + [path[i + 1] - path[i - 1] for i in range(1, len(path) - 1)] + [path[-1] - path[-2]]
    T = [t / np.linalg.norm(t) for t in T]
    a = np.cross(T[0], X if abs(T[0] @ X) < 0.9 else Y); a /= np.linalg.norm(a)
    rings = []
    for i, p in enumerate(path):
        if i:
            a = a - (a @ T[i]) * T[i]; a /= np.linalg.norm(a)
        b = np.cross(T[i], a)
        rings.append([tuple(p + r * (math.cos(2 * math.pi * (k + 0.5) / n) * a + math.sin(2 * math.pi * (k + 0.5) / n) * b))
                      for k in range(n)])
    keep = sm.mat; sm.mat = mat
    sm.kind = ROUND; sm.tube(rings)
    sm.kind = FLAT; sm.region([rings[0]]); sm.region([rings[-1]])
    sm.mat = keep


def cable(sm, ctrl, r=CABLE_R, n=CABLE_N):
    """the thick conduit along a Catmull-Rom curve through ctrl"""
    path = catmull(ctrl)
    tube(sm, path, r, n, CABLE)
    return path


def clip(sm, c, along, up, w=0.016, half=0.017, foot=0.017):
    """band clamp over a cable: arch around the cable centre c (spec), foot down to the link face; along = cable
    direction, up = away from the face"""
    along = np.asarray(along, float) / np.linalg.norm(along); up = np.asarray(up, float); up /= np.linalg.norm(up)
    side = np.cross(up, along)
    fr = (np.asarray(c, float) - along * (w / 2), side, up, along)
    poly = [(-half, -foot), (half, -foot)] + [(u, v) for u, v in arc((0, 0), half, 0, 180, 8)]
    kinds = [FLAT, FLAT] + [ROUND] * 8 + [FLAT]
    poly, kinds = clean(poly, kinds)
    keep = sm.mat; sm.mat = STEEL
    solid(sm, poly, kinds, fr, 0.0, w, 0.002, 0.002)
    sm.mat = keep


# frames: (origin, u, v, n)
def fr_side(x0=0.0, o=(0, 0, 0)):
    """link side profile: u = +Z, v = +Y, extruded along +X from x0"""
    return (np.asarray(o, float) + X * x0, Z, Y, X)


def fr_down(y0=0.0):
    """plan profile: u = +X, v = +Z, extruded downward (-Y) from y0"""
    return (Y * y0, X, Z, -Y)


def fr_axis_z(o=(0, 0, 0)):
    """tool profile: u = +X, v = +Y, extruded along -Z"""
    return (np.asarray(o, float), X, Y, -Z)


# --------------------------------------------------------------------------- parts


def build_mount(detail=True):
    sm = ArmMesh(); sm.mat = PAINT
    plate = clipped_square(PLATE_H, PLATE_CLIP)
    solid(sm, plate, [FLAT] * 8, fr_down(), 0.0, PLATE_T, ch0=0.0, ch1=CH)
    top = clipped_square(FRUST_TOP, FRUST_TOP_CLIP); bot = clipped_square(FRUST_BOT, FRUST_BOT_CLIP)
    fr = fr_down()
    sm.kind = FLAT; sm.region([loop(fr, top, FRUST_Y0)])                     # inside the plate (ray test removes it)
    loft(sm, top, FRUST_Y0, bot, FRUST_Y1 - 0.004, fr, [FLAT] * 8)
    sm.kind = CHAMFER; sm.tube([loop(fr, bot, FRUST_Y1 - 0.004), loop(fr, G.offset(bot, 0.004), FRUST_Y1)])
    sm.kind = FLAT; sm.region([loop(fr, G.offset(bot, 0.004), FRUST_Y1)])
    if detail:
        sm.mat = STEEL
        rr = NUT_AF / math.sqrt(3)
        for sx in (-1, 1):
            for sz in (-1, 1):
                hexa = circle((sx * NUT_AT, sz * NUT_AT), rr, 6, 0.0)
                solid(sm, hexa, [FLAT] * 6, fr, PLATE_T - 0.004, PLATE_T + NUT_T, ch0=0.0, ch1=0.002)
                cylinder(sm, fr, (sx * NUT_AT, sz * NUT_AT), 0.0065, SEG["tiny"], PLATE_T + NUT_T - 0.002,
                         PLATE_T + NUT_T + 0.006, ch0=0.0, ch1=0.0015)                       # stud end
    return sm.finish(f"{HERO}_Mount_01")


def build_turret(detail=True):
    sm = ArmMesh(); sm.mat = PAINT
    fr = fr_down()
    cylinder(sm, fr, (0, 0), DISC_R, SEG["big"], -DISC_Y0, -DISC_Y1, CH, CH)
    cylinder(sm, fr, (0, 0), HUB_R, SEG["mid"], -DISC_Y1 - 0.004, -HUB_Y1, 0.0, 0.004)
    # shoulder bracket (single cheek on -X, the forearm folds on +X): profile (z, y)
    cheek, ck = profile((arc((0, SHOULDER_Y), CHEEK_R, 180, 360, 8), ROUND),
                        ([(CHEEK_R, -0.095), (0.125, -0.045), (-0.125, -0.045), (-CHEEK_R, -0.095)], FLAT))
    solid(sm, cheek, ck, fr_side(), CHEEK_X1, CHEEK_X0, 0.004, 0.004)
    # pin stub between cheek and lug (2 mm short of the lug)
    cylinder(sm, fr_side(), (0, SHOULDER_Y), 0.030, SEG["mid"], CHEEK_X0 - 0.004, -UA_HW - 0.002, 0.0, 0.0015)
    if detail:
        cylinder(sm, fr_side(), (0, SHOULDER_Y), CHEEK_CAP_R, SEG["mid"], CHEEK_CAP_X1, CHEEK_X1 + 0.004, 0.004, 0.0)
        cylinder(sm, fr_side(), (0, BOSS_Y), BOSS_R, SEG["small"], DISC_R - 0.008, BOSS_X1, 0.0, 0.003)   # side boss
        # cable connector box on -X and the swivel on the shoulder axis
        sm.mat = POLYMER
        box = [(CONN["x0"], CONN["y0"]), (CONN["x1"], CONN["y0"]), (CONN["x1"], CONN["y1"]), (CONN["x0"], CONN["y1"])]
        solid(sm, [(-p[0], p[1]) for p in box], [FLAT] * 4, (O, -X, Y, Z), -CONN["hz"], CONN["hz"], 0.003, 0.003)
        sm.mat = STEEL
        cylinder(sm, fr_down(), (SWIVEL_X, 0), 0.014, SEG["tiny"], -CONN["y1"] - 0.002, -CONN["y1"] + 0.010, 0.0, 0.002)  # gland
        cylinder(sm, fr_side(), (0, SHOULDER_Y), SWIVEL_R, SEG["small"], SWIVEL_X - 0.020, CHEEK_CAP_X1 + 0.002, 0.003, 0.0)
        cable(sm, CABLES["Turret"]())
    return sm.finish(f"{HERO}_Turret_01")


UA_CABLE = [(SWIVEL_X, 0.0, SWIVEL_R + 0.003), (SWIVEL_X, 0.0, 0.09), (-0.155, 0.02, 0.17), (-0.11, 0.07, 0.25),
            (-0.04, 0.099, 0.31), (0.02, 0.099, 0.37), (0.025, 0.099, 0.45), (0.025, 0.099, 0.80),
            (0.04, 0.11, 0.90), (0.10, 0.128, 0.975), (0.17, 0.133, 1.02), (0.248, 0.12, 1.075),
            (0.248, 0.07, 1.10), (0.248, 0.035, 1.045)]
UA_CLIPS = (0.50, 0.74)
CABLE_TOP_UA, CABLE_TOP_FA = 0.099, 0.089      # cable centre over the link tops (7 mm stand-off)


def ua_cable_ctrl():
    c = list(UA_CABLE)
    d = (SWIVEL_R + 0.003) / math.sqrt(2)       # radial approach to the elbow swivel along 45 deg, 2 mm off it
    c.append((0.12 + P_X, d, 1.0 + d))
    return c


def thin_cable(sm, ctrl, fade=0.10):
    """the thin cable: the thick cable's curve shifted +X by THIN_OFF on the straight runs, fading into it over
    `fade` at both ends (so both end at the same swivel point, hidden inside the thick one)"""
    path = np.array(catmull(ctrl, 0.008), float)
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    w = np.clip(np.minimum(L, L[-1] - L) / fade, 0, 1); w = w * w * (3 - 2 * w)
    pts = path + np.outer(w * THIN_OFF, X)
    keep = sm.mat; sm.mat = POLYMER
    tube(sm, simplify(list(pts)), THIN_R, THIN_N, POLYMER)
    sm.mat = keep


def build_upper(detail=True):
    sm = ArmMesh(); sm.mat = PAINT
    prof, kinds = profile(
        ([(0.0, -UA_HH), (1.0, -UA_HH)], FLAT),
        (arc((1.0, 0), UA_HH, -90, 90, 12), ROUND),
        ([(1.0, UA_HH), (0.0, UA_HH)], FLAT),
        (arc((0, 0), LUG_R, 90, 270, 12), ROUND))
    solid(sm, prof, kinds, fr_side(), -UA_HW, UA_HW)
    if detail:
        cylinder(sm, fr_side(), (0, 0), SLOT_CAP_R, SEG["big"], UA_HW, UA_HW + SLOT_CAP_T, 0.0, 0.004)
        cylinder(sm, fr_side(), (1.0, 0), ELBOW_CAP_R, SEG["big"], -UA_HW - 0.016, -UA_HW, 0.004, 0.0)
        cylinder(sm, fr_side(), (1.0, 0), 0.045, SEG["mid"], UA_HW, 0.068, 0.0, 0.0015)    # elbow hub washer
        cable(sm, CABLES["UpperArm"]())
        thin_cable(sm, CABLES["UpperArm"]())
        for zc in UA_CLIPS:
            clip(sm, (0.035, CABLE_TOP_UA, zc), Z, Y, foot=0.026, half=0.025)   # 0.010 ... 0.060: inside the top
    return sm.finish(f"{HERO}_UpperArm_01")


FA_CABLE = [(P_X, 0.0, -(SWIVEL_R + 0.003)), (P_X, 0.0, -0.07), (0.115, 0.03, -0.14), (0.08, 0.075, -0.20),
            (0.024, 0.089, -0.26), (0.012, 0.089, -0.32), (0.012, 0.089, -0.70), (0.024, 0.095, -0.77),
            (0.08, 0.110, -0.85), (0.15, 0.115, -0.895), (Q_X + 0.10, 0.100, -0.90), (Q_X + 0.10, 0.050, -0.90)]
FA_CLIPS = (-0.40, -0.62)


def fa_cable_ctrl():
    return FA_CABLE + [(Q_X + 0.10, 0.014 + 0.003, -0.90)]


def build_forearm(detail=True):
    sm = ArmMesh(); sm.mat = PAINT
    prof, kinds = profile(
        (arc((0, 0), FA_HH, -90, 90, 12), ROUND),
        ([(0, FA_HH), (-0.90, FA_HH)], FLAT),
        (arc((-0.90, 0), FA_HH, 90, 270, 12), ROUND),
        ([(-0.90, -FA_HH), (0, -FA_HH)], FLAT))
    solid(sm, prof, kinds, fr_side(), -FA_HW, FA_HW, 0.005, 0.005)
    if detail:
        cylinder(sm, fr_side(), (0, 0), ELBOW_DISC_R, SEG["big"], FA_HW, ELBOW_DISC_X1, 0.0, 0.004)
        cylinder(sm, fr_side(), (0, 0), ELBOW_HUB_R, SEG["mid"], ELBOW_DISC_X1 - 0.002, ELBOW_HUB_X1, 0.0, 0.003)
        sm.mat = STEEL
        cylinder(sm, fr_side(), (0, 0), SWIVEL_R, SEG["small"], ELBOW_HUB_X1 - 0.002, P_X + 0.012, 0.0, 0.003)
        sm.mat = PAINT
        cylinder(sm, fr_side(), (-0.90, 0), 0.040, SEG["mid"], FA_HW, 0.052, 0.0, 0.0015)   # wrist washer
        cable(sm, CABLES["Forearm"]())
        thin_cable(sm, CABLES["Forearm"]())
        for zc in FA_CLIPS:
            clip(sm, (0.022, CABLE_TOP_FA, zc), -Z, Y, foot=0.026, half=0.024)   # -0.002 ... 0.046: inside the top
    return sm.finish(f"{HERO}_Forearm_01")


def build_wrist(detail=True):
    sm = ArmMesh(); sm.mat = PAINT
    prof, kinds = profile(
        (arc((0, 0), WR_R, -90, 90, 12), ROUND),
        ([(0, WR_R), (WR_Z1, WR_R), (WR_Z1, -WR_R), (0, -WR_R)], FLAT))
    solid(sm, prof, kinds, fr_side(), -WR_HW, WR_HW, 0.005, 0.005)
    sm.mat = POLYMER
    cylinder(sm, fr_axis_z(), (0, 0), NECK_R, SEG["mid"], -NECK_Z0 - 0.004, -NECK_Z1, 0.0, 0.003)
    if detail:
        sm.mat = PAINT
        cylinder(sm, fr_side(), (0, 0), WR_CAP_R, SEG["mid"], WR_HW, WR_CAP_X1, 0.0, 0.003)
        sm.mat = STEEL
        cylinder(sm, fr_side(), (0, 0), 0.014, SEG["small"], WR_CAP_X1 - 0.002, Q_X + 0.010, 0.0, 0.003)
        cylinder(sm, fr_side(), (-0.062, 0), 0.010, SEG["tiny"], WR_HW, 0.064, 0.0, 0.002)   # cable gland (6 mm over the tool)
        cable(sm, CABLES["Wrist"]())
    return sm.finish(f"{HERO}_Wrist_01")


def build_tool(detail=True):
    sm = ArmMesh(); sm.mat = STEEL
    cylinder(sm, fr_axis_z(), (0, 0), COLLAR_R, SEG["mid"], 0.0, -COLLAR_Z1 + 0.004, 0.003, 0.0)
    sm.mat = OCHRE
    solid(sm, BLOCK, [FLAT] * len(BLOCK), (np.array([0, -BLOCK_HY, 0]), X, Z, Y), 0.0, 2 * BLOCK_HY, 0.005, 0.005)
    sm.mat = STEEL
    cylinder(sm, fr_axis_z(), (0, 0), PIN_R, SEG["small"], -PIN_Z0 - 0.006, -PIN_Z1, 0.0, 0.003)
    return sm.finish(f"{HERO}_ToolHead_01")


CABLES = {   # cable control points per part (part-local); servicearm_tex.py uses the same curves for the corrugation
    "Turret": lambda: [(SWIVEL_X, CONN["y1"] - 0.008, 0.0), (SWIVEL_X, SHOULDER_Y + SWIVEL_R + 0.003, 0.0)],
    "UpperArm": lambda: ua_cable_ctrl(),
    "Forearm": lambda: fa_cable_ctrl(),
    "Wrist": lambda: [(Q_X, 0.0, -0.017), (Q_X, 0.0, -0.035), (0.080, 0.0, -0.058), (0.068, 0.0, -0.062)]}


BUILDERS = {"Mount": build_mount, "Turret": build_turret, "UpperArm": build_upper, "Forearm": build_forearm,
            "Wrist": build_wrist, "ToolHead": build_tool}


# --------------------------------------------------------------------------- placement, hidden faces

C3 = np.array([[-1, 0, 0], [0, 0, -1], [0, 1, 0]], float)              # spec -> Blender
C4 = np.eye(4); C4[:3, :3] = C3


def to_blender(p):
    return Vector((-p[0], -p[2], p[1]))


def blender_matrix(W):
    return Matrix((C4 @ W @ C4.T).tolist())


def set_pose(objs, pose):
    W = K.fk(pose)
    for name, o in objs.items():
        o.matrix_world = blender_matrix(W[name])
    bpy.context.view_layer.update()


def visible_faces(obj, tree, dirs, reach=3.0):
    """faces of obj that see open space (no hit within reach) in at least one direction from at least one sample;
    obj at identity, tree = the part's own triangles (+ the ceiling for the mount)"""
    me = obj.data; vis = set()
    for p in me.polygons:
        n = p.normal; c = p.center
        vw = [me.vertices[i].co for i in p.vertices]
        pts = [c]
        for k in range(len(vw)):
            for q in (vw[k], (vw[k] + vw[(k + 1) % len(vw)]) / 2):
                d = c - q
                pts.append(q + d.normalized() * min(0.002, d.length * 0.5) if d.length > 1e-9 else q)
        for k in range(1, len(vw) - 1):
            a, b, cc = vw[0], vw[k], vw[k + 1]
            m = max(2, int(max((b - a).length, (cc - a).length, (cc - b).length) / 0.01))
            for i in range(1, m):
                for j in range(1, m - i):
                    pts.append(a + (b - a) * (i / m) + (cc - a) * (j / m))
        found = False
        for q in pts:
            o = q + n * 3e-4
            for d in dirs:
                if d.dot(n) <= 0.05: continue
                if tree.ray_cast(o, d, reach)[0] is None:
                    found = True; break
            if found: break
        if found: vis.add(p.index)
    return vis


def delete_hidden(o, ceiling=False):
    verts = [v.co.copy() for v in o.data.vertices]; polys = [list(p.vertices) for p in o.data.polygons]
    if ceiling:                                        # spec y >= 0 (part-local ceiling face): Blender z >= 0
        k = len(verts)
        verts += [Vector(v) for v in ((-1, -1, 0.001), (1, -1, 0.001), (1, 1, 0.001), (-1, 1, 0.001))]
        polys.append([k, k + 1, k + 2, k + 3])
    tree = BVHTree.FromPolygons(verts, polys)
    keep = visible_faces(o, tree, CV.fib_dirs(160))
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
    kill = [f for f in bm.faces if f.index not in keep]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(o.data); bm.free()
    return len(kill)


# --------------------------------------------------------------------------- UVs and shading (as the Gate)

_HARD = set()


FLAT_FLAT_HARD = 3.0                            # two FLAT faces meeting at more than this: hard (flat faces never blend;
                                                # the Gate's 30 deg let the ramp, the lug chamfer and the adapter sides
                                                # smooth into their neighbours)


def hard_edge_keys(me):
    hard = G.hard_edge_keys(me)
    kind = me.attributes["kind"].data
    faces = {}
    for p in me.polygons:
        for k in p.edge_keys: faces.setdefault(k, []).append(p)
    for k, fs in faces.items():
        if len(fs) == 2 and kind[fs[0].index].value == FLAT and kind[fs[1].index].value == FLAT \
                and math.degrees(fs[0].normal.angle(fs[1].normal, 0.0)) > FLAT_FLAT_HARD:
            hard.add(k)
    return hard


def _is_hard(e):
    return len(e.link_faces) == 2 and tuple(sorted(v.index for v in e.verts)) in _HARD


def uv_density(o, isl):
    """cable tubes (thick conduit, thin cable: long, thin, seen from metres away) at half density, so the arm fits
    one 1024 sheet; everything else full"""
    mats = {f.material_index for f in isl}
    if mats == {CABLE}: return 0.5
    if mats == {POLYMER} and all(len(f.verts) == 4 for f in isl) and sum(f.calc_area() for f in isl) > 0.02: return 0.5
    return 1.0


def unwrap_and_pack(parts):
    UV.TEX = SHEET
    UV.MAX_STRIP = 1.9                          # longest island (m): fits the 1024 sheet at 512 px/m (cradle_v2_uv: 4.1 at 2048)
    UV.PAD_PX, UV.BORDER_PX = 4, 2              # ASSET_RULES 8 / 4 px at 2048 = 4 / 2 px at 1024 (same size on the model)
    UV.is_hard = _is_hard
    UV.HARD_DEG = 0.0
    rep = {}
    for o in parts:
        if not o.data.uv_layers: o.data.uv_layers.new(name="UVMap")
        _HARD.clear(); _HARD.update(hard_edge_keys(o.data))
        rep[o.name] = UV.unwrap_object(o)
        UV.scale_islands(o, lambda isl, o=o: uv_density(o, isl))
    d = TEXEL
    while True:                                  # 512 px/m, or the highest density within -10 % that fits the sheet
        try:
            rep["px_per_m"] = round(pack_fixed(parts, d), 1); break
        except AssertionError:
            d -= 4.0
            if d < TEXEL * 0.9: raise
    return rep


TEXEL = 512.0                                   # ASSET_RULES hero density (px/m)
SHEET = 1024                                    # H1b (owner): one 1024 sheet; the arm is far from the player


def pack_fixed(objs, d):
    """cradle_v2_uv.pack at a FIXED density (the arm's islands fill only part of the 2048 sheet at 512 px/m; the
    bisection in UV.pack would scale them up to fill it): same skyline packer, padding and placement"""
    bms = []; isls = []
    for o in objs:
        bm = bmesh.new(); bm.from_mesh(o.data); uvl = bm.loops.layers.uv.active
        bms.append((o, bm, uvl))
        for isl in UV.islands(bm):
            U = np.array([l[uvl].uv[:] for f in isl for l in f.loops])
            isls.append((uvl, isl, U.min(0), np.ptp(U, 0)))
    rects = [(int(math.ceil(sz[0] * d)) + UV.PAD_PX + 1, int(math.ceil(sz[1] * d)) + UV.PAD_PX + 1) for _, _, _, sz in isls]
    pos = None
    for key in UV.ORDERS:
        pos = UV._skyline(rects, UV.TEX, UV.TEX, key)
        if pos: break
    if not pos:
        for o, bm, uvl in bms: bm.free()
        raise AssertionError("islands do not fit the sheet at this density")
    T = UV.TEX
    for (uvl, isl, mn, sz), (x, y, turned) in zip(isls, pos):
        ox = (x + UV.PAD_PX // 2 + 0.5) / T; oy = (y + UV.PAD_PX // 2 + 0.5) / T
        for f in isl:
            for l in f.loops:
                u, v = l[uvl].uv[0] - mn[0], l[uvl].uv[1] - mn[1]
                if turned: u, v = sz[1] - v, u
                l[uvl].uv = (ox + u * d / T, oy + v * d / T)
    for o, bm, uvl in bms:
        bm.to_mesh(o.data); bm.free()
    return d


def review_material(name, rgb):
    m = bpy.data.materials.new(name); m.use_nodes = True; m.diffuse_color = (*rgb, 1.0)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = 1.0 if name.endswith("Steel") else 0.0
    b.inputs["Roughness"].default_value = {"Steel": 0.35, "Polymer": 0.6, "Cable": 0.5, "Ochre": 0.5}.get(
        name.split("_")[-1], 0.5)
    return m


def build(detail=True, finish=True):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 1.0
    col = bpy.data.collections.new("ServiceArm_v1"); sc.collection.children.link(col)
    mats = [review_material(n, c) for n, c in MATS]
    objs = {}
    removed = {}
    for name in K.PARTS:
        me = BUILDERS[name](detail)
        o = bpy.data.objects.new(f"{HERO}_{name}_01", me); col.objects.link(o)
        for m in mats: me.materials.append(m)
        objs[name] = o
    bpy.context.view_layer.update()
    for name, o in objs.items():
        removed[name] = delete_hidden(o, ceiling=(name == "Mount"))
    uv = None
    if finish:
        uv = unwrap_and_pack(list(objs.values()))
        for o in objs.values():
            G.apply_shading(o)
    set_pose(objs, K.WORKING)
    return objs, removed, uv


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blockout = "blockout" in argv
    objs, removed, uv = build(detail=not blockout, finish=not blockout)
    print("HIDDEN faces deleted:", removed)
    if uv: print("UV px/m:", uv["px_per_m"], {k.replace(HERO + "_", ""): v.get("islands") for k, v in uv.items() if isinstance(v, dict)})
    for n, o in objs.items():
        o.data.calc_loop_triangles(); print(f"TRIS {n}: {len(o.data.loop_triangles)}")
    path = SAVE_H0 if blockout else SAVE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("SAVED", path)


if __name__ == "__main__":
    main()
