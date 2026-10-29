"""
Labyrinth VR -- Hero 03, facility gate (LAB_HERO_Gate_*), hero workflow v3 (Blender-textured, no high-poly).

Source of every number: Documentation/HERO_SPEC.md section 7 (sizes, positions, slide), design from the owner's
concept D:/AI_Labyrinth/Gemini/References/Gate/gate_front.jpg (room side). Standard: ASSET_RULES.md, Hero tier,
workflow v3. Geometry is authored in Unity world coordinates (metres) and mapped to Blender per EXPORT_CONTRACT
(x -> -x, y -> z, z -> -y); each mesh is local to its part origin.

Parts (review file D:/AI_Labyrinth/Blender/Source/Heroes/Gate/LAB_HERO_Gate_v1.blend):
  LAB_HERO_Gate_Leaf_01         moving; origin on the +X edge, leaf bottom, mid thickness (-0.15, 0.01, 7.91).
                                Slide: -X by LEAF_TRAVEL (2.0 s). Carries the hanger plates, straps, axles, rollers.
  LAB_HERO_Gate_Rail_01         static; origin on the wall face under the rail centre (-1.80, RAIL_Y0, 8.00)
  LAB_HERO_Gate_ButtonPanel_01  static; corridor -X wall, origin on the wall face (-2.00, 1.20, 8.70)
  LAB_HERO_Gate_Button_01       moving; origin on its front face centre (rest), press -X by BUTTON_TRAVEL

Leaf layout in leaf coordinates u (from the -X edge, m) and v (from the leaf bottom); d = depth into the leaf from
either face. Both faces carry the same frame, channel + light strip, panels and hazard band (mirrored through the
mid plane, so the band stays on the physical +X edge); hanger plates and straps only on the room side.

Construction: flat regions with holes are filled by scanfill and joined back to quads (triangles stay only on
flat faces); walls between loops of equal count are quads. Separate shells (rail plates, end stops, bezel, lamp)
intersect or touch; every face hidden in both leaf positions (closed, open) is deleted by a ray test against the
gate parts plus the room around it (far wall with the doorway, trims, corridor walls, floor).

Run:  blender -b --factory-startup -P Tools/Blender/heroes/gate.py        (build + save)
Checks and review renders: gate_check.py.
"""
import bpy
import bmesh
import math
import os
import sys
import numpy as np
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cradle_v2 as CV                       # SpecMesh, polygon helpers, hidden-face ray test, shading
import cradle_v2_uv as UV

HERO = "LAB_HERO_Gate"
SAVE = "D:/AI_Labyrinth/Blender/Source/Heroes/Gate/LAB_HERO_Gate_v1.blend"

# --------------------------------------------------------------------------- parameters (HERO_SPEC §7)
LEAF_X0, LEAF_X1 = -1.85, -0.15              # closed
LEAF_Y0, LEAF_H = 0.010, 2.450               # 10 mm floor gap (G1); spec height kept
LEAF_Z0, LEAF_Z1 = 7.88, 7.94                # room face, corridor face
LEAF_TRAVEL = 1.70                           # open: x -3.55 ... -1.85
CH = 0.008                                   # large-edge chamfer
RAIL_X0, RAIL_X1 = -3.60, 0.00
RAIL_Y0, RAIL_Y1 = 2.475, 2.575              # raised 15 mm over the spec so the leaf top (2.46) clears it
RAIL_Z0, RAIL_Z1 = 7.92, 8.00                # 0.08 deep, on the wall face
WALL_Z = 8.00

# leaf outline (u, v), CCW: big chamfers on the -X corners (concept), small on +X
OUTLINE = [(0.09, 0.0), (1.675, 0.0), (1.70, 0.025), (1.70, 2.425), (1.675, 2.45), (0.09, 2.45), (0.0, 2.36), (0.0, 0.09)]
CHANNEL = [(0.115, 0.20), (0.165, 0.20), (0.205, 0.24), (0.205, 0.82), (0.235, 0.85), (0.235, 1.64), (0.205, 1.67),
           (0.205, 2.21), (0.165, 2.25), (0.115, 2.25)]
LIGHT = [(0.150, 0.93), (0.185, 0.93), (0.185, 1.53), (0.150, 1.53)]
FIELD = [(0.285, 0.12), (1.44, 0.12), (1.48, 0.16), (1.48, 2.21), (1.44, 2.25), (0.285, 2.25), (0.245, 2.21),
         (0.245, 1.67), (0.275, 1.64), (0.275, 0.85), (0.245, 0.82), (0.245, 0.16)]
BAND = [(1.52, 0.10), (1.64, 0.10), (1.64, 2.35), (1.52, 2.35)]
RECESS = 0.018                               # channel and field depth (> 15 mm: geometry)
FIELD_SLOPE, CHANNEL_SLOPE = 0.010, 0.006    # recess wall inset over the depth
LIGHT_D = 0.010                              # light strip face depth (8 mm proud of the channel floor)
PANEL_D, PANEL_SLOPE = 0.008, 0.003          # panel faces 10 mm proud of the field floor
PANEL_EDGE, PANEL_GAP = 0.022, 0.010         # panel inset from the field edge; half gap between panels
DIV1 = [(-1.0, 1.89), (0.585, 1.89), (1.010, 1.62), (3.0, 1.62)]      # top / waisted panel divider
DIV2 = [(-1.0, 0.57), (0.585, 0.57), (1.010, 0.87), (3.0, 0.87)]      # waisted / bottom panel divider
HANGERS = (0.40, 1.36)                       # hanger centres (u)
PLATE = dict(hw=0.08, v0=2.28, v1=2.43, t=0.010)
STRAP = dict(hw=0.03, v0=2.30, t=0.012)
STRAP_HEAD = [(0.03, 2.55), (0.068, 2.57), (0.068, 2.625), (0.05, 2.638)]   # right half above the strap (du, v)
AXLE_DU, AXLE_V = 0.050, 2.606               # twin axles: hanger centre +- 0.050, y 2.616 (roller on the rail top)
AXLE_R, AXLE_HEAD_R, AXLE_HEAD_T = 0.008, 0.012, 0.006
ROLLER_A, ROLLER_W = 0.040, 0.025            # 12-gon apothem (flat on the rail), width
ROLLER_ZC = 7.94                             # roller centre plane (20 mm behind the rail front)

# rail profile (y, z) CCW seen from +X; front groove 16 mm deep (geometry)
RAIL_PROFILE = [(2.475, 8.00), (2.475, 7.926), (2.481, 7.92), (2.505, 7.92), (2.505, 7.936), (2.545, 7.936),
                (2.545, 7.92), (2.569, 7.92), (2.575, 7.926), (2.575, 8.00)]
RAIL_PLATES = (-3.53, -2.40, -1.20, -0.07)   # bracket plate centres (x), 0.10 wide, on the rail front
RAIL_PLATE = dict(hw=0.05, y0=2.478, y1=2.572, z0=7.908)
STOP = dict(w=0.04, y1=2.625, z0=7.926)      # end stops on the rail top at both ends

# button panel (corridor -X wall), button
PANEL_C = (-2.00, 1.20, 8.70)
PANEL_SZ = (0.08, 0.30, 0.22)                # x (depth), y, z
PANEL_CH = 0.010
BEZEL_C = (1.235, 8.70)                      # (y, z)
BEZEL_R, RING_R, HOLE_R, BEZEL_T, HOLE_DEPTH = 0.055, 0.046, 0.037, 0.015, 0.035
BUTTON_R, BUTTON_CH, BUTTON_PROUD, BUTTON_BACK = 0.035, 0.003, 0.012, 0.025
BUTTON_TRAVEL = 0.008
LAMP_C, LAMP_R, LAMP_T = (1.105, 8.70), 0.012, 0.008
BUTTON_SEG, LAMP_SEG = 24, 16                # G2: bezel, ring light, hole, button 24; lamp 16

MATS = [("M_Gate_Paint", (0.046, 0.052, 0.062)), ("M_Gate_Polymer", (0.017, 0.018, 0.020)),
        ("M_Gate_Steel", (0.50, 0.51, 0.53)), ("M_Gate_Hazard", (0.34, 0.19, 0.04)),
        ("M_Gate_Cyan", (0.061, 0.402, 1.0)), ("M_Gate_Amber", (0.80, 0.27, 0.04))]
PAINT, POLYMER, STEEL, HAZARD, CYAN, AMBER = range(6)

# face kinds (face attribute "kind") for hard edges and normals (G2): FLAT faces keep their own normal, CHAMFER strips
# are the only smoothed transitions, ROUND sides of cylinders are smooth among themselves
FLAT, CHAMFER, ROUND = 0, 1, 2
HARD_ANGLE = 30.0                            # flat | flat and round | flat above this: hard (and a UV seam); 30 not 35:
                                             # the panel walls bend 32-34 deg at the divider corners
CHAMFER_MAX = 50.0                           # chamfer | flat up to this stays smooth (a 45 deg chamfer)
CHAMFER_CORNER = 15.0                        # chamfer | chamfer above this (at outline corners): hard


def to_blender(p):
    return Vector((-p[0], -p[2], p[1]))


def circle(c2, r, n, phase=0.5):
    """n points on a circle (centre c2 in the plane's 2D coords), vertices at (k + phase) * 360 / n"""
    return [(c2[0] + r * math.cos(2 * math.pi * (k + phase) / n), c2[1] + r * math.sin(2 * math.pi * (k + phase) / n))
            for k in range(n)]


def offset(poly, d):
    return [tuple(p) for p in CV.poly_offset(poly, d)]


def clip_graph(poly, g, above):
    """clip a CCW polygon (u, v) to v >= g(u) (above) or v <= g(u); g: piecewise linear knots [(u, v)], monotone u"""
    gu = [k[0] for k in g]

    def gv(u): return float(np.interp(u, gu, [k[1] for k in g]))

    def f(p): return (p[1] - gv(p[0])) * (1 if above else -1)
    pts = []                                              # subdivide every edge at the knots: f is linear per piece
    n = len(poly)
    for i in range(n):
        p, q = np.array(poly[i]), np.array(poly[(i + 1) % n])
        ts = [0.0] + sorted(t for t in ((k - p[0]) / (q[0] - p[0]) for k in gu) if 1e-9 < t < 1 - 1e-9) \
            if abs(q[0] - p[0]) > 1e-12 else [0.0]
        pts += [tuple(p + (q - p) * t) for t in ts]
    out = []
    m = len(pts)
    for i in range(m):
        p, q = pts[i], pts[(i + 1) % m]
        fp, fq = f(p), f(q)
        if fp >= -1e-12: out.append(("in", p))
        if (fp > 1e-12 and fq < -1e-12) or (fp < -1e-12 and fq > 1e-12):
            t = fp / (fp - fq); x = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
            out.append(("exit" if fp > 0 else "entry", x))
    res = []                                              # between an exit and the next entry, follow g
    for i, (kind, p) in enumerate(out):
        res.append(p)
        if kind == "exit":
            nxt = next(out[(i + j) % len(out)] for j in range(1, len(out) + 1) if out[(i + j) % len(out)][0] == "entry")
            a, b = p[0], nxt[1][0]
            ks = [k for k in g if min(a, b) + 1e-9 < k[0] < max(a, b) - 1e-9]
            res += [(k[0], k[1]) for k in sorted(ks, key=lambda k: k[0], reverse=a > b)]
    clean = []                                            # drop collinear / repeated points
    for i, p in enumerate(res):
        a, b = res[i - 1], res[(i + 1) % len(res)]
        if math.dist(p, a) < 1e-7: continue
        if abs((p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])) < 1e-10: continue
        clean.append(p)
    return clean


def panels():
    inner = offset(FIELD, PANEL_EDGE)
    sh = lambda g, dv: [(u, v + dv) for u, v in g]
    top = clip_graph(inner, sh(DIV1, PANEL_GAP), True)
    mid = clip_graph(clip_graph(inner, sh(DIV1, -PANEL_GAP), False), sh(DIV2, PANEL_GAP), True)
    bot = clip_graph(inner, sh(DIV2, -PANEL_GAP), False)
    return [top, mid, bot]


class GateMesh(CV.SpecMesh):
    """SpecMesh + material per face + flat regions with holes"""

    def __init__(self):
        super().__init__()
        self.mat = PAINT
        self.kind = FLAT
        self.known = set()
        self.kind_layer = self.bm.faces.layers.int.new("kind")

    def tag(self):
        for f in self.bm.faces:
            if f not in self.known:
                f.material_index = self.mat; f[self.kind_layer] = self.kind; self.known.add(f)

    def f(self, *pts):
        r = super().f(*pts); self.tag(); return r

    def region(self, loops):
        """flat region: first loop outer, the others holes (all on one plane)"""
        edges = []
        for L in loops:
            vs = [self.v(p) for p in L]
            for i in range(len(vs)):
                a, b = vs[i], vs[(i + 1) % len(vs)]
                edges.append(self.bm.edges.get((a, b)) or self.bm.edges.new((a, b)))
        P = np.array(loops[0], float); n = np.zeros(3)
        for i in range(len(P)):
            n += np.cross(P[i], P[(i + 1) % len(P)])
        res = bmesh.ops.triangle_fill(self.bm, use_beauty=True, use_dissolve=False, edges=edges,
                                      normal=Vector(n).normalized())
        for g in res["geom"]:
            if isinstance(g, bmesh.types.BMFace):
                g.smooth = True; self.join.append(g)
        self.tag()

    def tube(self, loops, closed=True):
        """quad walls between consecutive loops of equal count"""
        for a, b in zip(loops, loops[1:]):
            self.bridge(a, b, closed)
        self.tag()

    def finish(self, name, offset_spec=(0, 0, 0)):
        bm = self.bm
        if self.join:
            live = [f for f in set(self.join) if f.is_valid and len(f.verts) == 3]
            inner = list({e for f in live for e in f.edges
                          if len(e.link_faces) == 2 and all(g in live for g in e.link_faces)
                          and e.link_faces[0].material_index == e.link_faces[1].material_index})
            res = bmesh.ops.beautify_fill(bm, faces=live, edges=inner)
            live = [f for f in set(live) | set(res["geom"]) if isinstance(f, bmesh.types.BMFace) and f.is_valid
                    and len(f.verts) == 3]
            bmesh.ops.join_triangles(bm, faces=live, cmp_seam=False, cmp_sharp=False, cmp_uvs=False, cmp_vcols=False,
                                     cmp_materials=True, angle_face_threshold=math.radians(0.5),
                                     angle_shape_threshold=math.radians(70))
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bm.normal_update()
        for f in [f for f in bm.faces if len(f.verts) == 4]:          # concave quads: split on the reflex diagonal
            vs = [v.co for v in f.verts]; n = f.normal
            reflex = [i for i in range(4) if (vs[i] - vs[i - 1]).cross(vs[(i + 1) % 4] - vs[i]).dot(n) < -1e-12]
            if reflex:
                i = reflex[0]
                bmesh.ops.connect_verts(bm, verts=[f.verts[i], f.verts[(i + 2) % 4]])
        ox, oy, oz = offset_spec
        for v in bm.verts:
            x, y, z = v.co
            v.co = (-(x - ox), -(z - oz), (y - oy))
        bm.normal_update()
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me); bm.free()
        for p in me.polygons: p.use_smooth = True
        return me


# --------------------------------------------------------------------------- leaf


def leaf_pt(u, v, d, side):
    """leaf (u, v) + depth d into the leaf from the face of side (+1 room, -1 corridor) -> spec world"""
    z = LEAF_Z0 + d if side > 0 else LEAF_Z1 - d
    return (LEAF_X0 + u, LEAF_Y0 + v, z)


def loop3(poly, d, side):
    return [leaf_pt(u, v, d, side) for u, v in poly]


def build_leaf():
    sm = GateMesh()
    face_out = offset(OUTLINE, CH)
    pnl = panels()
    for side in (1, -1):
        sm.mat = PAINT
        sm.kind = CHAMFER
        sm.tube([loop3(face_out, 0.0, side), loop3(OUTLINE, CH, side)])               # edge chamfer
        sm.kind = FLAT
        holes = [CHANNEL, FIELD, BAND]
        plates = []
        if side > 0:
            for hc in HANGERS:
                plates.append([(hc - PLATE["hw"], PLATE["v0"]), (hc + PLATE["hw"], PLATE["v0"]),
                               (hc + PLATE["hw"], PLATE["v1"]), (hc + STRAP["hw"], PLATE["v1"]),
                               (hc - STRAP["hw"], PLATE["v1"]), (hc - PLATE["hw"], PLATE["v1"])])
        sm.region([loop3(face_out, 0.0, side)] + [loop3(h, 0.0, side) for h in holes + plates])
        sm.mat = HAZARD
        sm.region([loop3(BAND, 0.0, side)])
        # channel + light strip
        sm.mat = POLYMER
        ch_floor = offset(CHANNEL, CHANNEL_SLOPE)
        sm.tube([loop3(CHANNEL, 0.0, side), loop3(ch_floor, RECESS, side)])
        sm.region([loop3(ch_floor, RECESS, side), loop3(LIGHT, RECESS, side)])
        sm.tube([loop3(LIGHT, RECESS, side), loop3(LIGHT, LIGHT_D, side)])
        sm.mat = CYAN
        sm.region([loop3(LIGHT, LIGHT_D, side)])
        # field recess + three panels
        sm.mat = PAINT
        f_floor = offset(FIELD, FIELD_SLOPE)
        sm.tube([loop3(FIELD, 0.0, side), loop3(f_floor, RECESS, side)])
        sm.region([loop3(f_floor, RECESS, side)] + [loop3(p, RECESS, side) for p in pnl])
        for p in pnl:
            top = offset(p, PANEL_SLOPE)
            sm.tube([loop3(p, RECESS, side), loop3(top, PANEL_D, side)])
            sm.region([loop3(top, PANEL_D, side)])
        # hanger plates, straps, axles, rollers (room side)
        for hc, pl in zip(HANGERS, plates):
            t = PLATE["t"]
            sm.mat = PAINT
            sm.tube([loop3(pl, 0.0, side), loop3(pl, -t, side)])
            notch = [(hc - PLATE["hw"], PLATE["v0"]), (hc + PLATE["hw"], PLATE["v0"]), (hc + PLATE["hw"], PLATE["v1"]),
                     (hc + STRAP["hw"], PLATE["v1"]), (hc + STRAP["hw"], STRAP["v0"]), (hc - STRAP["hw"], STRAP["v0"]),
                     (hc - STRAP["hw"], PLATE["v1"]), (hc - PLATE["hw"], PLATE["v1"])]
            sm.f(*loop3(notch, -t, side))
            build_strap(sm, hc, -t, side)
    sm.mat = PAINT
    sm.tube([loop3(OUTLINE, CH, 1), loop3(OUTLINE, CH, -1)])                          # leaf sides
    return sm.finish(f"{HERO}_Leaf_01", (LEAF_X1, LEAF_Y0, (LEAF_Z0 + LEAF_Z1) / 2))


def build_strap(sm, hc, d_back, side):
    t = STRAP["t"]; hw = STRAP["hw"]
    head = [(hc + du, v) for du, v in STRAP_HEAD]
    right = [(hc + hw, STRAP["v0"]), (hc + hw, PLATE["v1"])] + head
    left = [(2 * hc - u, v) for u, v in reversed(head)] + [(hc - hw, PLATE["v1"]), (hc - hw, STRAP["v0"])]
    outline = right + left                                                  # CCW from the bottom right corner
    d_front = d_back - t
    axles = [(hc - AXLE_DU, AXLE_V), (hc + AXLE_DU, AXLE_V)]
    sm.mat = PAINT
    sm.tube([loop3(outline, d_back, side), loop3(outline, d_front, side)])
    sm.region([loop3(outline, d_front, side)] + [loop3(circle(a, AXLE_HEAD_R, 8), d_front, side) for a in axles])
    upper = outline[1:-1]                                                   # back face above the plate
    sm.region([loop3(upper, d_back, side)] + [loop3(circle(a, AXLE_R, 8), d_back, side) for a in axles])
    z_roll0 = ROLLER_ZC - ROLLER_W / 2 - LEAF_Z0                            # depth of the roller front (room side)
    for a in axles:
        sm.mat = STEEL
        hd = circle(a, AXLE_HEAD_R, 8)
        sm.kind = ROUND
        sm.tube([loop3(hd, d_front, side), loop3(hd, d_front - AXLE_HEAD_T, side)])
        sm.kind = FLAT
        sm.f(*loop3(hd, d_front - AXLE_HEAD_T, side))
        ax = circle(a, AXLE_R, 8)
        sm.kind = ROUND
        sm.tube([loop3(ax, d_back, side), loop3(ax, z_roll0, side)])
        sm.kind = FLAT
        rr = ROLLER_A / math.cos(math.pi / 12)
        ring = [(a[0] + rr * math.cos(math.radians(15 + 30 * k)), a[1] + rr * math.sin(math.radians(15 + 30 * k)))
                for k in range(12)]                                         # flats at the bottom and top
        z1 = z_roll0 + ROLLER_W
        sm.region([loop3(ring, z_roll0, side), loop3(ax, z_roll0, side)])
        sm.kind = ROUND
        sm.tube([loop3(ring, z_roll0, side), loop3(ring, z1, side)])
        sm.kind = FLAT
        sm.f(*loop3(ring, z1, side))


# --------------------------------------------------------------------------- rail


def box(sm, x0, x1, y0, y1, z0, z1, xs=()):
    """closed box; xs: extra x stations (loop cuts) on the four long faces"""
    X = [x0] + sorted(x for x in xs if x0 < x < x1) + [x1]
    ring = lambda x: [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]
    sm.tube([ring(x) for x in X])
    sm.f(*reversed(ring(x0))); sm.f(*ring(x1))


RAIL_CHAMFER_SEG = (1, 7)                    # profile segments i -> i+1 that are the 6 mm chamfers
RAIL_RUN_SEG = 8                             # the top the rollers ride on: machined steel (G2)


def build_rail():
    sm = GateMesh(); sm.mat = PAINT
    xs = sorted({RAIL_X0, RAIL_X1} | {c + s * RAIL_PLATE["hw"] for c in RAIL_PLATES for s in (-1, 1)}
                | {RAIL_X0 + STOP["w"], RAIL_X1 - STOP["w"]})
    prof = lambda x: [(x, y, z) for y, z in RAIL_PROFILE]
    n = len(RAIL_PROFILE)
    for i in range(n):                                                      # closed: the back strip goes to the ray test
        sm.mat = STEEL if i == RAIL_RUN_SEG else PAINT
        sm.kind = CHAMFER if i in RAIL_CHAMFER_SEG else FLAT
        sm.tube([[prof(x)[i], prof(x)[(i + 1) % n]] for x in xs], closed=False)
    sm.mat = PAINT; sm.kind = FLAT
    sm.f(*reversed(prof(RAIL_X0))); sm.f(*prof(RAIL_X1))
    for c in RAIL_PLATES:
        p = RAIL_PLATE
        box(sm, c - p["hw"], c + p["hw"], p["y0"], p["y1"], p["z0"], RAIL_Z0)
    for x0, x1 in ((RAIL_X0, RAIL_X0 + STOP["w"]), (RAIL_X1 - STOP["w"], RAIL_X1)):
        box(sm, x0, x1, RAIL_Y1, STOP["y1"], STOP["z0"], RAIL_Z1)
    return sm.finish(f"{HERO}_Rail_01", ((RAIL_X0 + RAIL_X1) / 2, RAIL_Y0, WALL_Z))


# --------------------------------------------------------------------------- button panel, button


def build_panel():
    sm = GateMesh(); sm.mat = PAINT
    cx, cy, cz = PANEL_C; dx, hy, hz = PANEL_SZ[0], PANEL_SZ[1] / 2, PANEL_SZ[2] / 2
    xf = cx + dx                                                           # front face x
    rect = lambda x, i: [(x, cy - hy + i, cz - hz + i), (x, cy - hy + i, cz + hz - i), (x, cy + hy - i, cz + hz - i),
                         (x, cy + hy - i, cz - hz + i)]
    sm.tube([rect(cx, 0), rect(xf - PANEL_CH, 0)])
    sm.kind = CHAMFER
    sm.tube([rect(xf - PANEL_CH, 0), rect(xf, PANEL_CH)])
    sm.kind = FLAT
    sm.f(*reversed(rect(cx, 0)))                                           # back (deleted by the ray test)
    yz = lambda pts, x: [(x, y, z) for y, z in pts]
    bez = circle(BEZEL_C, BEZEL_R, BUTTON_SEG); lamp = circle(LAMP_C, LAMP_R, LAMP_SEG)
    sm.region([rect(xf, PANEL_CH), yz(bez, xf), yz(lamp, xf)])
    sm.mat = POLYMER
    xb = xf + BEZEL_T
    ring = circle(BEZEL_C, RING_R, BUTTON_SEG); hole = circle(BEZEL_C, HOLE_R, BUTTON_SEG)
    sm.kind = ROUND
    sm.tube([yz(bez, xf), yz(bez, xb)])
    sm.kind = FLAT
    sm.bridge(yz(bez, xb), yz(ring, xb)); sm.tag()
    sm.mat = CYAN
    sm.bridge(yz(ring, xb), yz(hole, xb)); sm.tag()
    sm.mat = POLYMER
    sm.kind = ROUND
    sm.tube([yz(hole, xb), yz(hole, xb - HOLE_DEPTH)])
    sm.kind = FLAT
    sm.f(*yz(hole, xb - HOLE_DEPTH))
    sm.mat = AMBER
    sm.kind = ROUND
    sm.tube([yz(lamp, xf), yz(lamp, xf + LAMP_T)])
    sm.kind = FLAT
    sm.f(*yz(lamp, xf + LAMP_T))
    return sm.finish(f"{HERO}_ButtonPanel_01", (cx, cy, cz))


def button_front():
    return PANEL_C[0] + PANEL_SZ[0] + BEZEL_T + BUTTON_PROUD


def build_button():
    sm = GateMesh(); sm.mat = POLYMER
    xf = button_front(); xb = xf - BUTTON_PROUD - BUTTON_BACK
    yz = lambda pts, x: [(x, y, z) for y, z in pts]
    outer = circle(BEZEL_C, BUTTON_R, BUTTON_SEG); top = circle(BEZEL_C, BUTTON_R - BUTTON_CH, BUTTON_SEG)
    sm.kind = ROUND
    sm.tube([yz(outer, xb), yz(outer, xf - BUTTON_CH)])
    sm.kind = CHAMFER
    sm.tube([yz(outer, xf - BUTTON_CH), yz(top, xf)])
    sm.kind = FLAT
    sm.f(*yz(top, xf)); sm.f(*reversed(yz(outer, xb)))
    return sm.finish(f"{HERO}_Button_01", (xf, BEZEL_C[0], BEZEL_C[1]))


# --------------------------------------------------------------------------- room occluders, hidden faces


ROOM_BOXES = [  # (x0, x1, y0, y1, z0, z1), spec: far wall around the doorway, trims, corridor walls
    (-4.0, -1.8, 0.0, 4.0, 8.0, 8.2), (-0.2, 4.0, 0.0, 4.0, 8.0, 8.2), (-1.8, -0.2, 2.4, 4.0, 8.0, 8.2),
    (-4.0, -2.0, 0.0, 0.15, 7.95, 8.0), (0.0, 2.0, 0.0, 0.15, 7.95, 8.0),
    (-2.2, -2.0, 0.0, 3.0, 8.2, 14.2), (0.0, 0.2, 0.0, 3.0, 8.2, 14.2), (-4.05, -4.0, 0.0, 4.0, -2.0, 8.0)]


def room_object():
    sm = GateMesh()
    for b in ROOM_BOXES:
        box(sm, *b)
    me = sm.finish("GateRoomProxy")
    o = bpy.data.objects.new("GateRoomProxy", me)
    return o


def cull_candidate(o, f):
    """the leaf's recesses have narrow sight lines (20 mm panel gaps, the channel seen through the doorway) that 96
    ray directions miss, so on the leaf only the floor-facing bottom and the hanger parts above the leaf top
    (roller backs facing the wall) may be culled; everything else is built without hidden faces"""
    if "Leaf" not in o.name: return True
    y = (o.matrix_world @ f.calc_center_median()).z                          # Blender z = spec y
    return y < LEAF_Y0 + 0.001 or y > LEAF_Y0 + LEAF_H + 0.001


def delete_hidden(parts, leaf, room):
    dirs = CV.fib_dirs(96)
    box_ = ((-0.5, -15.0, -0.5), (4.5, -6.0, 3.5))                          # Blender: x = -spec x, y = -spec z
    keep = {o.name: set() for o in parts}
    for dx in (0.0, -LEAF_TRAVEL):
        leaf.location = to_blender((LEAF_X1 + dx, LEAF_Y0, (LEAF_Z0 + LEAF_Z1) / 2))
        bpy.context.view_layer.update()
        tree = CV.scene_bvh(parts + [room])
        for o in parts:
            keep[o.name] |= CV.visible_faces(o, tree, dirs, box_)
    leaf.location = to_blender((LEAF_X1, LEAF_Y0, (LEAF_Z0 + LEAF_Z1) / 2))
    bpy.context.view_layer.update()
    rep = {}
    for o in parts:
        bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
        kill = [f for f in bm.faces if f.index not in keep[o.name] and cull_candidate(o, f)]
        rep[o.name.replace(HERO + "_", "")] = len(kill)
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(o.data); bm.free()
    return rep


# --------------------------------------------------------------------------- materials, assembly


def review_material(name, rgb):
    """G1 review shading only (flat values from STYLE_GUIDE); the v3 texture bake replaces it"""
    m = bpy.data.materials.new(name); m.use_nodes = True; m.diffuse_color = (*rgb, 1.0)
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = 1.0 if "Steel" in name else 0.0
    b.inputs["Roughness"].default_value = {"Steel": 0.35, "Polymer": 0.65, "Cyan": 0.4, "Amber": 0.4}.get(
        name.split("_")[-1], 0.55)
    if name.endswith(("Cyan", "Amber")):
        b.inputs["Emission Color"].default_value = (*rgb, 1.0); b.inputs["Emission Strength"].default_value = 6.0
    if name.endswith("Hazard"):                                            # 45 deg ochre / black stripes, 60 mm pitch
        tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        add = nt.nodes.new("ShaderNodeMath"); add.operation = 'ADD'
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 1 / 0.085
        fr = nt.nodes.new("ShaderNodeMath"); fr.operation = 'FRACT'
        gt = nt.nodes.new("ShaderNodeMath"); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.5
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'
        mix.inputs[6].default_value = (*rgb, 1.0); mix.inputs[7].default_value = (0.017, 0.017, 0.019, 1.0)
        nt.links.new(tc.outputs["Object"], sep.inputs[0]); nt.links.new(sep.outputs[0], add.inputs[0])
        nt.links.new(sep.outputs[2], add.inputs[1]); nt.links.new(add.outputs[0], mul.inputs[0])
        nt.links.new(mul.outputs[0], fr.inputs[0]); nt.links.new(fr.outputs[0], gt.inputs[0])
        nt.links.new(gt.outputs[0], mix.inputs[0]); nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return m


TOP_DENSITY = 0.5                                  # leaf top / bottom edges, undersides: rarely seen


def uv_density(o, isl):
    a = sum(f.calc_area() for f in isl)
    n = sum((f.normal * f.calc_area() for f in isl), Vector()).normalized()
    if "Leaf" in o.name and abs(n.z) > 0.9: return TOP_DENSITY            # leaf top under the rail, bottom
    if n.z < -0.9: return TOP_DENSITY
    return 1.0


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 1.0
    col = bpy.data.collections.new("Gate_v1"); sc.collection.children.link(col)
    mats = [review_material(n, c) for n, c in MATS]

    def obj(name, me, loc_spec):
        o = bpy.data.objects.new(name, me); col.objects.link(o)
        for m in mats: me.materials.append(m)
        o.location = to_blender(loc_spec)
        return o
    leaf = obj(f"{HERO}_Leaf_01", build_leaf(), (LEAF_X1, LEAF_Y0, (LEAF_Z0 + LEAF_Z1) / 2))
    rail = obj(f"{HERO}_Rail_01", build_rail(), ((RAIL_X0 + RAIL_X1) / 2, RAIL_Y0, WALL_Z))
    panel = obj(f"{HERO}_ButtonPanel_01", build_panel(), PANEL_C)
    button = obj(f"{HERO}_Button_01", build_button(), (button_front(), BEZEL_C[0], BEZEL_C[1]))
    room = room_object(); col.objects.link(room)
    bpy.context.view_layer.update()
    parts = [leaf, rail, panel, button]
    removed = delete_hidden(parts, leaf, room)
    bpy.data.objects.remove(room)
    uv_report = unwrap_and_pack(parts)
    for o in parts:
        apply_shading(o)
    return parts, removed, uv_report


# --------------------------------------------------------------------------- hard edges, UVs, normals (G2)


def hard_edge_keys(me):
    """edges that get a hard edge (and a UV seam), by face kind and angle (see FLAT / CHAMFER / ROUND)"""
    kind = me.attributes["kind"].data
    faces = {}
    for p in me.polygons:
        for k in p.edge_keys: faces.setdefault(k, []).append(p)
    hard = set()
    for k, fs in faces.items():
        if len(fs) != 2: continue
        a = math.degrees(fs[0].normal.angle(fs[1].normal, 0.0))
        ka, kb = kind[fs[0].index].value, kind[fs[1].index].value
        if ka == ROUND and kb == ROUND: continue
        if ka == CHAMFER and kb == CHAMFER: lim = CHAMFER_CORNER
        elif CHAMFER in (ka, kb): lim = CHAMFER_MAX
        else: lim = HARD_ANGLE
        if a > lim: hard.add(k)
    return hard


_HARD = set()


def _is_hard(e):
    return len(e.link_faces) == 2 and tuple(sorted(v.index for v in e.verts)) in _HARD


def unwrap_and_pack(parts):
    """cradle_v2_uv per object, with the Gate's hard-edge rule in place of the dihedral bands"""
    UV.is_hard = _is_hard
    UV.HARD_DEG = 0.0                         # no pruning of short hard runs: every hard edge is wanted
    rep = {}
    for o in parts:
        if not o.data.uv_layers: o.data.uv_layers.new(name="UVMap")
        _HARD.clear(); _HARD.update(hard_edge_keys(o.data))
        rep[o.name] = UV.unwrap_object(o)
        UV.scale_islands(o, lambda isl, o=o: uv_density(o, isl))
    rep["px_per_m"] = round(UV.pack(parts), 1)
    return rep


FACE_STRENGTH = {FLAT: 3, ROUND: 2, CHAMFER: 1}        # weighted normal face influence: strong / medium / weak


def apply_shading(obj):
    """face-area weighted normals with face influence: flat faces keep their own normal, chamfers blend between
    their neighbours (the only smoothed transitions), hard edges as marked by the unwrap"""
    me = obj.data
    kind = me.attributes["kind"].data
    fw = me.attributes.get("__mod_weightednormals_faceweight") or \
        me.attributes.new("__mod_weightednormals_faceweight", 'INT', 'FACE')
    for p in me.polygons:
        fw.data[p.index].value = FACE_STRENGTH[kind[p.index].value]; p.use_smooth = True
    mod = obj.modifiers.new("WN", 'WEIGHTED_NORMAL'); mod.mode = 'FACE_AREA'; mod.weight = 50
    mod.keep_sharp = True; mod.use_face_influence = True; mod.thresh = 0.01
    for o in bpy.context.view_layer.objects: o.select_set(False)
    bpy.context.view_layer.objects.active = obj; obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def main():
    parts, removed, uv_report = build()
    print("HIDDEN faces deleted:", removed)
    print("UV:", uv_report)
    os.makedirs(os.path.dirname(SAVE), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, compress=True)
    print("SAVED", SAVE)


if __name__ == "__main__":
    main()
