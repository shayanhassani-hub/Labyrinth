"""
Labyrinth VR -- Hero 02, control terminal (LAB_HERO_Terminal_*), hero workflow v3 (Blender-textured, no high-poly).

Source of every size: Documentation/HERO_SPEC.md section 5 (origin, footprint, desk heights and slope, pillars,
display, button, indicators, beacon) and section 1 (Armed state). Design: the owner's concept
Documentation/References/Terminal/terminal_front.jpg (master for look and detail) and terminal_ortho_{front,top,side}.jpg
(proportions); the concept is squatter than the spec, so the spec heights and footprint are kept and the concept's
layout, bevels, pillar shapes and details are fitted onto them (Documentation/Heroes/Terminal_BUILD.md lists every
feature and every deviation). Standard: ASSET_RULES.md Hero tier, workflow v3; STYLE_GUIDE.md.

Axes: geometry is written in terminal-local coordinates (x across, +X = the player's LEFT as they face the wall,
y up, z from the back wall's inner face into the room), placed at the HERO_SPEC origin (-2.2, 0, -2.0), yaw 0, and
mapped to Blender per EXPORT_CONTRACT (x -> -x, y -> z, z -> -y); each mesh is local to its part origin.

Parts (review file D:/AI_Labyrinth/Blender/Source/Heroes/Terminal/LAB_HERO_Terminal_v1.blend):
  LAB_HERO_Terminal_Body_01        static: both pillars, desk + lower body, display base bar, button guard, beacon
                                   base and cage, the 3 always-cyan indicator strips and the pillar light strips.
                                   Origin = terminal origin (-2.2, 0, -2.0) (back wall face, floor, centre).
  LAB_HERO_Terminal_Button_01      moving: red cap; origin on its top-face centre at rest; press 0.015 along the desk
                                   normal (into the desk).
  LAB_HERO_Terminal_Indicators_01  switching: the 3 strips that turn red on Armed (player's right group); origin =
                                   terminal origin. Driven by a MaterialPropertyBlock (emission map white there).
  LAB_HERO_Terminal_Beacon_01      switching: the red beacon lens on Pillar_L; origin on its base centre.
  LAB_HERO_Terminal_Display_01     the holo screen: one quad, own transparent material (M_..._Holo), own texture;
                                   origin on its bottom-edge centre.
Pillar_L / Pillar_R are named from the player's view (facing the wall): Pillar_L at +X carries the beacon.

Construction: pillars are convex blocks from half-spaces (scipy HalfspaceIntersection: chamfered vertical edges and
top edges in one step), the desk + lower body is one profile extruded along x between the pillars. Faces with
recesses are planar regions with holes (gate.GateMesh.region: scanfill, joined back to quads); recess walls and raised
panels are quad tubes between loops of equal count. Where the body meets a pillar, the pillar's inner face is cut
along the body profile (shapely difference) so the surfaces share their vertices (no hidden faces, no T-junctions;
every point that lands on another face's edge is inserted into that edge). Faces hidden by construction (backs on
the wall, floor contacts, body end caps inside the pillars) are deleted; a ray test decides only for a few named
candidates (plinth slots, cage bar ends).

Run:  python (bpy 5.2.2) or  blender -b --factory-startup -P Tools/Blender/heroes/terminal.py
      TERMINAL_DETAIL=0  -> H0 blockout (main forms only), saved as LAB_HERO_Terminal_h0.blend
Checks and review renders: terminal_check.py.
"""
import bpy
import bmesh
import math
import os
import sys
import numpy as np
from mathutils import Vector
from scipy.spatial import HalfspaceIntersection
import shapely.geometry as SG
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cradle_v2 as CV                       # SpecMesh, poly offsets, ray visibility
import cradle_v2_uv as UV                    # unwrap, island scaling, packing
import gate as G                             # GateMesh (material / kind per face, regions with holes), clip_graph, circle

HERO = "LAB_HERO_Terminal"
DETAIL = int(os.environ.get("TERMINAL_DETAIL", "1"))
SAVE = "D:/AI_Labyrinth/Blender/Source/Heroes/Terminal/" + ("LAB_HERO_Terminal_v1.blend" if DETAIL else
                                                             "LAB_HERO_Terminal_h0.blend")

# --------------------------------------------------------------------------- parameters (HERO_SPEC §5), terminal-local
OX, OZ = -2.2, -2.0                          # origin on the back wall's inner face, yaw 0
HALF_W, DEPTH = 1.20, 0.80                   # footprint 2.40 x 0.80 (x -3.4 ... -1.0, z -2.0 ... -1.2)
PIL_IN, PIL_H = 0.90, 1.25                   # pillar 0.30 wide (|x| 0.90 ... 1.20), 1.25 high
PIL_OF, PIL_OB, PIL_IF = 0.040, 0.040, 0.008  # vertical chamfers: outer-front / outer-back (hazard bands), inner-front
PIL_TF, PIL_TO, PIL_TI = 0.150, 0.030, 0.030  # top chamfers: front (concept side view: ~0.17), outer, inner
PLINTH_H, PLINTH_IN = 0.16, 0.015            # base plinth, inset 15 mm (toe recess)
TRIM_CLEAR = 0.055                           # plinths stop 5 mm in front of the floor trim (z 0 ... 0.05, y 0 ... 0.15)
HAZ_Y = (0.22, 1.04)                         # hazard bands on the outer vertical chamfers

DESK_FRONT_Y, DESK_BACK_Y, SLOPE = 0.92, 1.05, 15.0
DESK_FRONT_Z = 0.75                          # desk 50 mm behind the pillar fronts (concept top view)
SLAB_T = 0.05                                # desk slab front edge (0.87 ... 0.92)
BODY_FRONT_Z = 0.65                          # lower body front: 100 mm toe / knee recess under the slab
CH = 0.008                                   # large-edge chamfer
SLOPE_L = (DESK_BACK_Y - DESK_FRONT_Y) / math.sin(math.radians(SLOPE))       # 0.502 along the slope
SLOPE_BACK_Z = DESK_FRONT_Z - SLOPE_L * math.cos(math.radians(SLOPE))         # 0.265

_c, _s = math.cos(math.radians(SLOPE)), math.sin(math.radians(SLOPE))
PROFILE = [  # body section (z, y) extruded along x between the pillars (|x| <= 0.90)
    (TRIM_CLEAR, 0.0), (BODY_FRONT_Z - PLINTH_IN, 0.0), (BODY_FRONT_Z - PLINTH_IN, PLINTH_H), (BODY_FRONT_Z, PLINTH_H),
    (BODY_FRONT_Z, DESK_FRONT_Y - SLAB_T), (DESK_FRONT_Z - CH, DESK_FRONT_Y - SLAB_T),
    (DESK_FRONT_Z, DESK_FRONT_Y - SLAB_T + CH), (DESK_FRONT_Z, DESK_FRONT_Y - CH),
    (DESK_FRONT_Z - CH * _c, DESK_FRONT_Y + CH * _s), (SLOPE_BACK_Z, DESK_BACK_Y), (0.0, DESK_BACK_Y), (0.0, PLINTH_H),
    (TRIM_CLEAR, PLINTH_H)]
P_SLOPE = 8                                  # profile segment index of the sloped desk top (and 3 lower front, 9 shelf)

DISPLAY_W, DISPLAY_H, DISPLAY_Y0, DISPLAY_Z, DISPLAY_LEAN = 1.50, 0.85, 1.10, 0.15, 8.0
BAR = dict(hx=0.80, z0=0.115, z1=0.185, y1=DISPLAY_Y0)                        # display base bar on the shelf

# desk-surface layout in (u, s): u = x, s along the slope from its front edge (0) to the back (SLOPE_L)
BUTTON_US = (0.0, 0.25)
BUTTON_R, BUTTON_TOP, BUTTON_BOTTOM, BUTTON_CH = 0.060, 0.048, -0.030, 0.003       # cap Ø 0.12, 0.04 above the cup
BUTTON_TRAVEL = 0.015
GUARD = dict(flange=0.115, outer=0.100, inner=0.075, hole=0.0615, floor_h=0.008, flange_h=0.008, top_h=0.035,
             ch=0.003, hole_floor=-0.060, notch_deg=240.0, notch_w=45.0)
SEG = 24                                     # button, guard (interactive close-up: up to 24, ASSET_RULES)
SLOT_L, SLOT_W, SLOT_D, STRIP_IN, STRIP_H = 0.245, 0.034, 0.015, 0.008, -0.007
SLOT_U, SLOT_S = 0.44, (0.15, 0.25, 0.35)    # three slots each side; the -X group (player's right) switches to red

BEACON = dict(x=1.05, z=0.33, base_r=0.050, base_h=0.022, lens_r=0.040, cage_r=0.047, cage_t=0.006, cage_h=0.094)

# materials (review shading; the bake replaces them). SWITCH: indicator strips that turn red (emission set at runtime)
MATS = [("M_Term_Paint", (0.060, 0.078, 0.095)), ("M_Term_Polymer", (0.017, 0.018, 0.020)),
        ("M_Term_Steel", (0.50, 0.51, 0.53)), ("M_Term_Hazard", (0.34, 0.19, 0.04)),
        ("M_Term_Cyan", (0.061, 0.402, 1.0)), ("M_Term_Switch", (0.061, 0.402, 1.0)),
        ("M_Term_RedCap", (0.45, 0.04, 0.025)), ("M_Term_Lens", (0.79, 0.017, 0.010))]
PAINT, POLYMER, STEEL, HAZARD, CYAN, SWITCH, REDCAP, LENS = range(8)
FLAT, CHAMFER, ROUND = G.FLAT, G.CHAMFER, G.ROUND
KEEP, CULL, RAY = 0, 1, 2                    # face attribute "cull": keep / delete (hidden by construction) / ray test
Z_NONE, Z_RECESS, Z_CUP, Z_CAGE = 0, 1, 2, 3  # face attribute "zone" for the texture: recess floor / walls (darker
                                             # paint), the guard's cup floor (steel ring), the beacon cage (dark paint)


def T(p, sx=1.0):
    """terminal-local (x, y, z) -> Unity world; sx = -1 mirrors to the other pillar"""
    return (OX + sx * p[0], p[1], OZ + p[2])


def to_blender(p):
    return Vector((-p[0], -p[2], p[1]))


def offset(poly, d):
    return [tuple(p) for p in CV.poly_offset(poly, d)]


def ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return list(poly) if a > 0 else list(reversed(poly))


class TMesh(G.GateMesh):
    """GateMesh + a per-face cull tag; faces are collected first (so edge points can be inserted), then emitted"""

    def __init__(self):
        super().__init__()
        self.cull = KEEP; self.zone = Z_NONE
        self.cull_layer = self.bm.faces.layers.int.new("cull")
        self.zone_layer = self.bm.faces.layers.int.new("zone")

    def tag(self):
        for f in self.bm.faces:
            if f not in self.known:
                f.material_index = self.mat; f[self.kind_layer] = self.kind; f[self.cull_layer] = self.cull
                f[self.zone_layer] = self.zone
                self.known.add(f)

    def set(self, mat=None, kind=None, cull=None, zone=None):
        if mat is not None: self.mat = mat
        if kind is not None: self.kind = kind
        if cull is not None: self.cull = cull
        if zone is not None: self.zone = zone


class Frame:
    """a plane in world space: p(u, v, d) = o + a u + b v - n d (d = depth into the surface)"""

    def __init__(self, o, a, b, n):
        self.o, self.a, self.b, self.n = (np.array(x, float) for x in (o, a, b, n))

    def p(self, u, v, d=0.0):
        return tuple(self.o + self.a * u + self.b * v - self.n * d)

    def loop(self, poly, d=0.0):
        return [self.p(u, v, d) for u, v in poly]


def desk_frame():
    """sloped desk top: u = world x offset, v = s along the slope (front edge 0), d = depth below the surface"""
    o = T((0.0, DESK_FRONT_Y, DESK_FRONT_Z))
    return Frame(o, (1, 0, 0), (0, _s, -_c), (0, _c, _s))


# --------------------------------------------------------------------------- edge points (no T-junctions)


class Faces:
    """collected planar faces [(loops, mat, kind, cull)], emitted after every edge point is known"""

    def __init__(self):
        self.items = []; self.points = []

    def add(self, loops, mat=PAINT, kind=FLAT, cull=KEEP):
        self.items.append(([list(L) for L in loops], mat, kind, cull))

    def point(self, p):
        self.points.append(np.array(p, float))

    def insert(self, loop):
        out = []
        n = len(loop)
        for i in range(n):
            a, b = np.array(loop[i], float), np.array(loop[(i + 1) % n], float)
            out.append(tuple(a))
            ab = b - a; L2 = ab @ ab
            if L2 < 1e-12: continue
            mids = []
            for q in self.points:
                t = (q - a) @ ab / L2
                if 1e-6 < t < 1 - 1e-6 and np.linalg.norm(a + ab * t - q) < 1e-6: mids.append((t, tuple(q)))
            out += [q for _, q in sorted(mids)]
        clean = []
        for q in out:                                                         # drop repeats (points registered twice)
            if not clean or np.linalg.norm(np.array(q) - np.array(clean[-1])) > 1e-7: clean.append(q)
        if len(clean) > 1 and np.linalg.norm(np.array(clean[0]) - np.array(clean[-1])) < 1e-7: clean.pop()
        return clean

    def emit(self, sm):
        for loops, mat, kind, cull in self.items:
            sm.set(mat, kind, cull, Z_NONE)
            loops = [self.insert(loops[0])] + loops[1:]
            if len(loops) == 1 and len(loops[0]) <= 4: sm.f(*loops[0])
            else: sm.region(loops)


# --------------------------------------------------------------------------- pillars


def pillar_halfspaces(top=PIL_H, y0=PLINTH_H):
    """pillar L (x >= 0) as half-spaces A p + b <= 0 (p = x, y, z), with names"""
    x0, x1, z1 = PIL_IN, HALF_W, DEPTH
    H = [("inner", (-1, 0, 0), x0), ("outer", (1, 0, 0), -x1), ("back", (0, 0, -1), 0.0), ("front", (0, 0, 1), -z1),
         ("bottom", (0, -1, 0), y0), ("top", (0, 1, 0), -top),
         ("of", (1, 0, 1), -(x1 + z1 - PIL_OF)), ("ob", (1, 0, -1), -(x1 - PIL_OB)),
         ("if", (-1, 0, 1), -(-x0 + z1 - PIL_IF)),
         ("tf", (0, 1, 1), -(top + z1 - PIL_TF)), ("to", (1, 1, 0), -(top + x1 - PIL_TO)),
         ("ti", (-1, 1, 0), -(top - x0 - PIL_TI))]
    return H


def hull_faces(H, interior):
    hs = np.array([list(a) + [b] for _, a, b in H], float)
    hi = HalfspaceIntersection(hs, np.array(interior, float))
    V = np.unique(np.round(hi.intersections, 9), axis=0)
    faces = {}
    for name, a, b in H:
        a = np.array(a, float)
        on = V[np.abs(V @ a + b) < 1e-7]
        if len(on) < 3: continue
        c = on.mean(0); n = a / np.linalg.norm(a)
        u = on[0] - c; u -= n * (u @ n); u /= np.linalg.norm(u); w = np.cross(n, u)
        ang = np.arctan2((on - c) @ w, (on - c) @ u)
        faces[name] = [tuple(p) for p in on[np.argsort(ang)]]
    return faces


def plan_outline(faces):
    """the pillar's plan outline at the bottom (x, z), CCW in (x, z)"""
    return ccw([(p[0], p[2]) for p in faces["bottom"]])


def body_upper_poly():
    """the body profile above the plinth, (z, y)"""
    i0 = PROFILE.index((BODY_FRONT_Z, PLINTH_H))
    return SG.Polygon(PROFILE[i0:] + [(BODY_FRONT_Z - PLINTH_IN, PLINTH_H)]).buffer(0)


def split_y(loop, ys):
    """split a planar face loop (3D) by horizontal planes y = ys -> pieces bottom to top"""
    pieces = []; cuts = [-1e9] + list(ys) + [1e9]
    for lo, hi in zip(cuts, cuts[1:]):
        P = loop
        for yb, keep_above in ((lo, True), (hi, False)):
            out = []
            for i in range(len(P)):
                a, b = np.array(P[i]), np.array(P[(i + 1) % len(P)])
                fa = (a[1] - yb) if keep_above else (yb - a[1]); fb = (b[1] - yb) if keep_above else (yb - b[1])
                if fa >= -1e-12: out.append(tuple(a))
                if (fa > 1e-12 and fb < -1e-12) or (fa < -1e-12 and fb > 1e-12):
                    out.append(tuple(a + (b - a) * fa / (fa - fb)))
            P = out
            if len(P) < 3: break
        if len(P) >= 3: pieces.append(P)
    return pieces


def pillar(FC, sm, sx):
    """one pillar (sx = +1: Pillar_L at +X, -1: Pillar_R) into the face list / mesh"""
    H = pillar_halfspaces()
    fs = hull_faces(H, (1.05, 0.7, 0.4))
    W = lambda p: T(p, sx)
    for name, loop in fs.items():
        L = [W(p) for p in loop]
        if name == "back":
            FC.add([L], cull=CULL)
        elif name == "bottom":
            out = plan_outline(fs)
            pl = plinth_outline(out)
            FC.add([L, [W((x, PLINTH_H, z)) for x, z in pl]], cull=KEEP)
        elif name == "inner":
            inner_face(FC, loop, sx)
        elif name in ("of", "ob"):
            for k, piece in enumerate(split_y(loop, HAZ_Y)):
                FC.add([[W(p) for p in piece]], mat=HAZARD if k == 1 else PAINT)
            for y in HAZ_Y:                                                     # split points on the shared edges
                for q in split_y(loop, [y])[0]:
                    if abs(q[1] - y) < 1e-9: FC.point(W(q))
        elif name == "front" and DETAIL:
            pillar_front(FC, sm, loop, sx)
        elif name == "outer" and DETAIL:
            pillar_outer(FC, sm, loop, sx)
        elif name == "top" and sx > 0:
            beacon_seat(FC, sm, loop)
        else:
            FC.add([L], kind=CHAMFER if name == "if" else FLAT)
    # plinth: walls from the floor to the pillar's underside, bottom on the floor (deleted)
    pl = plinth_outline(plan_outline(fs))
    sm.set(PAINT, FLAT, RAY)
    sm.tube([[W((x, 0.0, z)) for x, z in pl], [W((x, PLINTH_H, z)) for x, z in pl]])
    sm.set(cull=CULL); sm.f(*[W((x, 0.0, z)) for x, z in pl]); sm.set(cull=KEEP)


def plinth_outline(out):
    """plinth = pillar outline inset PLINTH_IN (mitred), cut at z = TRIM_CLEAR at the back; CCW (x, z). A plain
    per-edge offset would turn the 40 mm outer-back chamfer inside out (its offset is larger than the edge)"""
    g = SG.Polygon(out).buffer(-PLINTH_IN, join_style=2, mitre_limit=10.0)
    g = g.intersection(SG.box(-10.0, TRIM_CLEAR, 10.0, 10.0))
    pts = [tuple(round(c, 9) for c in q) for q in list(g.exterior.coords)[:-1]]
    clean = []
    for i, q in enumerate(pts):                                              # drop collinear points
        a_, b_ = pts[i - 1], pts[(i + 1) % len(pts)]
        if abs((q[0] - a_[0]) * (b_[1] - a_[1]) - (q[1] - a_[1]) * (b_[0] - a_[0])) < 1e-12: continue
        clean.append(q)
    return ccw(clean)


def inner_face(FC, loop, sx):
    """the pillar's inner face minus the body section (the body runs into it): shared vertices, no hidden part"""
    face = SG.Polygon([(p[2], p[1]) for p in loop]).buffer(0)
    rest = face.difference(body_upper_poly())
    geoms = [rest] if rest.geom_type == "Polygon" else list(rest.geoms)
    for g in geoms:
        if g.area < 1e-8: continue
        pts = list(g.exterior.coords)[:-1]
        L = [T((PIL_IN, y, z), sx) for z, y in pts]
        FC.add([L])
        for q in L: FC.point(q)


def recess(sm, fr, fld, depth, wall, panels=(), prise=0.0, pslope=0.003, mat=PAINT):
    """recessed field fld (u, v, CCW) in frame fr: sloped walls, floor with raised panels; returns the panel tops
    (loops in (u, v) at their depth) for the caller to fill (holes for light slots)"""
    sm.set(mat, FLAT, KEEP, Z_RECESS)
    floor = offset(fld, wall)
    sm.tube([fr.loop(fld, 0.0), fr.loop(floor, depth)])
    sm.region([fr.loop(floor, depth)] + [fr.loop(p, depth) for p in panels])
    sm.set(zone=Z_NONE)
    tops = []
    for p in panels:
        top = offset(p, pslope)
        sm.tube([fr.loop(p, depth), fr.loop(top, depth - prise)])
        tops.append((top, depth - prise))
    return tops


def slot(sm, fr, rect, d0, depth, strip_in, strip_top, strip_mat, strip_sm=None):
    """light slot: opening rect at depth d0, walls to d0 + depth, floor with the strip (strip_sm: separate mesh)"""
    sm.set(POLYMER, FLAT, KEEP)
    sm.tube([fr.loop(rect, d0), fr.loop(rect, d0 + depth)])
    strip = offset(rect, strip_in)
    sm.region([fr.loop(rect, d0 + depth), fr.loop(strip, d0 + depth)])
    tm = strip_sm or sm
    tm.set(POLYMER, FLAT, KEEP)
    tm.tube([fr.loop(strip, d0 + depth), fr.loop(strip, strip_top)])
    tm.set(strip_mat)
    tm.f(*fr.loop(strip, strip_top))
    tm.set(POLYMER)


FRONT_FIELD_IN = (0.025, 0.025, 0.025, 0.055)  # field inset from the front face: left, bottom, right, top (cap band)


def front_frame(sx):
    return Frame(T((PIL_IN, 0.0, DEPTH), sx), (sx, 0, 0), (0, 1, 0), (0, 0, 1))


def front_layout(loop):
    """pillar front (u from the inner face, v = y): face outline, field, dog-bone plate, light slot"""
    f2 = ccw([((p[0] - PIL_IN), p[1]) for p in loop])
    u0, u1 = min(q[0] for q in f2), max(q[0] for q in f2)
    v0, v1 = min(q[1] for q in f2), max(q[1] for q in f2)
    il, ib, ir, it = FRONT_FIELD_IN
    fld = [(u0 + il, v0 + ib), (u1 - ir, v0 + ib), (u1 - ir, v1 - it), (u0 + il, v1 - it)]
    uc = (fld[0][0] + fld[1][0]) / 2; hw = (fld[1][0] - fld[0][0]) / 2 - 0.014; wa = 0.035
    vb, vt = fld[0][1] + 0.014, fld[2][1] - 0.014
    t = hw - wa                                                               # 45 deg taper
    a0, a1, b0, b1 = vb + 0.15, vb + 0.15 + t, vt - 0.15 - t, vt - 0.15
    plate = [(uc - hw, vb), (uc + hw, vb), (uc + hw, a0), (uc + wa, a1), (uc + wa, b0), (uc + hw, b1), (uc + hw, vt),
             (uc - hw, vt), (uc - hw, b1), (uc - wa, b0), (uc - wa, a1), (uc - hw, a0)]
    vm = (a1 + b0) / 2
    sl = [(uc - 0.011, vm - 0.20), (uc + 0.011, vm - 0.20), (uc + 0.011, vm + 0.20), (uc - 0.011, vm + 0.20)]
    return dict(face=f2, field=fld, plate=plate, slot=sl, top_y=v1)


def pillar_front(FC, sm, loop, sx):
    """front face (z = DEPTH): recessed field with the dog-bone plate and the vertical cyan light strip"""
    fr = front_frame(sx); lay = front_layout(loop)
    FC.add([fr.loop(lay["face"], 0.0), fr.loop(lay["field"])])
    tops = recess(sm, fr, lay["field"], 0.018, 0.006, [lay["plate"]], prise=0.012)
    top, d = tops[0]
    sm.set(PAINT, FLAT, KEEP)
    sm.region([fr.loop(top, d), fr.loop(lay["slot"], d)])
    slot(sm, fr, lay["slot"], d, 0.015, 0.004, d + 0.010, CYAN)


def outer_frame(sx):
    return Frame(T((HALF_W, 0.0, 0.0), sx), (0, 0, 1), (0, 1, 0), (sx, 0, 0))


def outer_layout(loop):
    """pillar outer side (u = z, v = y): face outline, field, three raised panels (concept side view, front on the
    left there): a narrow strip of field along the front edge; the top panel reaches lower at the back, the bottom
    panel higher at the back; ~35 deg ramps between 30 % and 62 % of the width"""
    f2 = ccw([(p[2], p[1]) for p in loop])
    z0, z1 = min(q[0] for q in f2), max(q[0] for q in f2)
    v0, v1 = min(q[1] for q in f2), max(q[1] for q in f2)
    fld = [(z0 + 0.03, v0 + 0.03), (z1 - 0.03, v0 + 0.03), (z1 - 0.03, v1 - 0.03), (z0 + 0.03, v1 - 0.03)]
    inner = offset(offset(fld, 0.006), 0.016)
    gap = 0.010
    uf, ub = fld[1][0], fld[0][0]                                             # field front / back edge (u = z)
    wz = lambda w: uf - w * (uf - ub)                                         # w: 0 front ... 1 back -> u
    vv = lambda t: fld[0][1] + t * (fld[2][1] - fld[0][1])
    inner = [(min(u, wz(0.09)), v) for u, v in inner]                         # front strip (field floor) 9 % wide
    div1 = [(-1.0, vv(0.66)), (wz(0.62), vv(0.66)), (wz(0.30), vv(0.79)), (3.0, vv(0.79))]
    div2 = [(-1.0, vv(0.34)), (wz(0.62), vv(0.34)), (wz(0.30), vv(0.20)), (3.0, vv(0.20))]
    sh = lambda g, dv: [(u, v + dv) for u, v in g]
    top = G.clip_graph(inner, sh(div1, gap), True)
    mid = G.clip_graph(G.clip_graph(inner, sh(div1, -gap), False), sh(div2, gap), True)
    bot = G.clip_graph(inner, sh(div2, -gap), False)
    return dict(face=f2, field=fld, panels=[top, mid, bot])


def pillar_outer(FC, sm, loop, sx):
    """outer side face (x = HALF_W): recessed field with three raised panels, stepped dividers"""
    fr = outer_frame(sx); lay = outer_layout(loop)
    FC.add([fr.loop(lay["face"], 0.0), fr.loop(lay["field"])])
    tops = recess(sm, fr, lay["field"], 0.018, 0.006, lay["panels"], prise=0.010)
    sm.set(PAINT, FLAT, KEEP)
    for t_, d in tops: sm.region([fr.loop(t_, d)])


def beacon_seat(FC, sm, loop):
    """Pillar_L top with the beacon base (polymer) and the wire cage (paint); the lens is its own mesh"""
    c2 = (BEACON["x"], BEACON["z"]); y = PIL_H
    ring = lambda r, n=16: [(c2[0] + r * math.cos(2 * math.pi * (k + 0.5) / n), c2[1] + r * math.sin(2 * math.pi * (k + 0.5) / n))
                            for k in range(n)]
    P = lambda xz, h: T((xz[0], y + h, xz[1]))
    FC.add([[T(p) for p in loop], [P(q, 0.0) for q in ring(BEACON["base_r"])]])
    sm.set(POLYMER, ROUND, KEEP)
    sm.tube([[P(q, 0.0) for q in ring(BEACON["base_r"])], [P(q, BEACON["base_h"]) for q in ring(BEACON["base_r"])]])
    sm.set(POLYMER, FLAT)
    sm.bridge([P(q, BEACON["base_h"]) for q in ring(BEACON["base_r"])], [P(q, BEACON["base_h"]) for q in ring(BEACON["lens_r"])])
    sm.tag()
    if not DETAIL: return
    sm.set(PAINT, FLAT, RAY, Z_CAGE)                                          # cage: 4 posts, top ring, top cross
    t, r, h0, h1 = BEACON["cage_t"], BEACON["cage_r"], BEACON["base_h"], BEACON["cage_h"]
    for k in range(4):
        a = math.radians(45 + 90 * k); cx, cz = c2[0] + r * math.cos(a), c2[1] + r * math.sin(a)
        sq = [(cx - t / 2, cz - t / 2), (cx + t / 2, cz - t / 2), (cx + t / 2, cz + t / 2), (cx - t / 2, cz + t / 2)]
        sm.tube([[P(q, h0 - 0.002) for q in sq], [P(q, h1 - t / 2) for q in sq]])
        sm.f(*[P(q, h1 - t / 2) for q in reversed(sq)])
    ro, ri = ring(r + t / 2, 16), ring(r - t / 2, 16)
    sm.tube([[P(q, h1 - t) for q in ro], [P(q, h1) for q in ro]])
    sm.tube([[P(q, h1 - t) for q in ri], [P(q, h1) for q in ri]])
    sm.bridge([P(q, h1) for q in ro], [P(q, h1) for q in ri]); sm.bridge([P(q, h1 - t) for q in ri], [P(q, h1 - t) for q in ro])
    sm.tag()
    for a in (0.0, 90.0):                                                     # cross bars on the ring
        e = (math.cos(math.radians(a)), math.sin(math.radians(a))); nrm = (-e[1], e[0]); L = r
        q = lambda s_, w: (c2[0] + e[0] * s_ + nrm[0] * w, c2[1] + e[1] * s_ + nrm[1] * w)
        sec = [q(-L, -t / 2), q(L, -t / 2), q(L, t / 2), q(-L, t / 2)]
        hh = h1 - t / 2 + (0.0015 if a else 0.0)
        sm.tube([[P(p, hh - t / 2) for p in sec], [P(p, hh + t / 2) for p in sec]])
        sm.f(*[P(p, hh + t / 2) for p in reversed(sec)]); sm.f(*[P(p, hh - t / 2) for p in sec])
    sm.set(zone=Z_NONE)


# --------------------------------------------------------------------------- body (desk + lower body), display bar, guard


def body(FC, sm, ind):
    xs = (-PIL_IN, PIL_IN)
    n = len(PROFILE)
    rect = lambda i: [T((xs[0], PROFILE[i][1], PROFILE[i][0])), T((xs[1], PROFILE[i][1], PROFILE[i][0])),
                      T((xs[1], PROFILE[(i + 1) % n][1], PROFILE[(i + 1) % n][0])),
                      T((xs[0], PROFILE[(i + 1) % n][1], PROFILE[(i + 1) % n][0]))]
    for z, y in PROFILE:
        for x in xs: FC.point(T((x, y, z)))
    role = {0: CULL, 10: CULL, 12: CULL, 11: RAY}
    for i in range(n):
        kind = CHAMFER if i in (5, 7) else FLAT
        if i == 3 and DETAIL: lower_front(FC, sm, rect(i)); continue
        if i == P_SLOPE: desk_top(FC, sm, ind); continue
        if i == 9: shelf(FC, sm); continue
        FC.add([rect(i)], kind=kind, cull=role.get(i, KEEP))
    i0 = PROFILE.index((BODY_FRONT_Z, PLINTH_H))
    upper = PROFILE[i0:] + [(BODY_FRONT_Z - PLINTH_IN, PLINTH_H)]
    plinth = [PROFILE[0], PROFILE[1], PROFILE[2], PROFILE[-1]]
    for x in xs:                                                              # end caps: upper part inside the pillar
        FC.add([[T((x, y, z)) for z, y in upper]], cull=CULL)
        FC.add([[T((x, y, z)) for z, y in plinth]], cull=RAY)


def lower_frame():
    return Frame(T((0.0, 0.0, BODY_FRONT_Z)), (1, 0, 0), (0, 1, 0), (0, 0, 1))


def lower_layout():
    """lower body front (u = x, v = y): three fields, each with two raised panels and a stepped divider (the lower
    panel rises in the middle, concept)"""
    y0, y1 = PLINTH_H + 0.03, DESK_FRONT_Y - SLAB_T - 0.03
    out = []
    gap = 0.010
    for a, b in [(-0.87, -0.31), (-0.28, 0.28), (0.31, 0.87)]:
        fld = [(a, y0), (b, y0), (b, y1), (a, y1)]
        inner = offset(offset(fld, 0.006), 0.016)
        w = b - a; yl, yh = y0 + 0.38, y0 + 0.44
        div = [(a - 1, yl), (a + 0.30 * w, yl), (a + 0.30 * w + 0.06, yh), (b - 0.30 * w - 0.06, yh), (b - 0.30 * w, yl), (b + 1, yl)]
        sh = lambda g, dv: [(u, v + dv) for u, v in g]
        out.append(dict(field=fld, panels=[G.clip_graph(inner, sh(div, gap), True), G.clip_graph(inner, sh(div, -gap), False)]))
    return out


def lower_front(FC, sm, rect):
    """lower body front (z = BODY_FRONT_Z): three recessed fields with two raised panels each"""
    fr = lower_frame(); lay = lower_layout()
    FC.add([[fr.p(*q) for q in [(-PIL_IN, PLINTH_H), (PIL_IN, PLINTH_H), (PIL_IN, DESK_FRONT_Y - SLAB_T),
                                (-PIL_IN, DESK_FRONT_Y - SLAB_T)]]] + [fr.loop(f["field"]) for f in lay])
    for f in lay:
        tops = recess(sm, fr, f["field"], 0.018, 0.006, f["panels"], prise=0.010)
        sm.set(PAINT, FLAT, KEEP)
        for t_, d in tops: sm.region([fr.loop(t_, d)])


def slot_rects():
    out = []
    for sx in (1, -1):
        for s in SLOT_S:
            u = sx * SLOT_U
            out.append((sx, [(u - SLOT_L / 2, s - SLOT_W / 2), (u + SLOT_L / 2, s - SLOT_W / 2), (u + SLOT_L / 2, s + SLOT_W / 2),
                             (u - SLOT_L / 2, s + SLOT_W / 2)]))
    return out


def gcirc(r, n=SEG, phase=0.5):
    return G.circle(BUTTON_US, r, n, phase)


def desk_top(FC, sm, ind):
    fr = desk_frame()
    s0 = CH                                                                   # after the front chamfer
    outer = [(-PIL_IN, s0), (PIL_IN, s0), (PIL_IN, SLOPE_L), (-PIL_IN, SLOPE_L)]
    holes = []
    if DETAIL:
        holes = [r for _, r in slot_rects()] + [gcirc(GUARD["flange"])]
    else:
        holes = [gcirc(GUARD["outer"])]
    FC.add([fr.loop(outer)] + [fr.loop(h) for h in holes])
    if not DETAIL:
        sm.set(PAINT, ROUND, KEEP)
        sm.tube([fr.loop(gcirc(GUARD["outer"])), fr.loop(gcirc(GUARD["outer"]), -GUARD["top_h"])])
        sm.set(PAINT, FLAT); sm.region([fr.loop(gcirc(GUARD["outer"]), -GUARD["top_h"]), fr.loop(gcirc(GUARD["hole"]), -GUARD["top_h"])])
        sm.set(POLYMER, ROUND)
        sm.tube([fr.loop(gcirc(GUARD["hole"]), -GUARD["top_h"]), fr.loop(gcirc(GUARD["hole"]), -GUARD["hole_floor"])])
        sm.set(POLYMER, FLAT); sm.f(*fr.loop(gcirc(GUARD["hole"]), -GUARD["hole_floor"]))
        return
    for sx, r in slot_rects():
        slot(sm, fr, r, 0.0, SLOT_D, STRIP_IN, -STRIP_H, SWITCH if sx < 0 else CYAN, ind if sx < 0 else None)
    guard(sm, fr)


def guard(sm, fr):
    """button guard: flange on the desk, C-shaped collar (notch toward the player's front-right), cup floor (steel),
    hole for the cap's stroke"""
    g = GUARD
    sm.set(PAINT, ROUND, KEEP)
    sm.tube([fr.loop(gcirc(g["flange"])), fr.loop(gcirc(g["flange"]), -g["flange_h"])])
    # collar footprint: arcs of the outer / inner circle outside the notch (vertex angles every 15 deg)
    step = 360.0 / SEG
    n0 = g["notch_deg"] - g["notch_w"] / 2; n1 = g["notch_deg"] + g["notch_w"] / 2
    angs = [n1 + step * k for k in range(int(round((360 - g["notch_w"]) / step)) + 1)]
    arc = lambda r: [(BUTTON_US[0] + r * math.cos(math.radians(a)), BUTTON_US[1] + r * math.sin(math.radians(a))) for a in angs]
    co, ci, cc = arc(g["outer"]), arc(g["inner"]), arc(g["outer"] - g["ch"])
    foot = co + list(reversed(ci))
    hf = -g["flange_h"]
    sm.set(PAINT, FLAT)
    # flange top + notch floor: annulus flange .. inner minus the collar footprint; cup floor (steel) inner .. hole
    outer_region = [fr.loop(gcirc(g["flange"]), hf), fr.loop(ccw(foot), hf)]
    # the notch connects flange top and cup floor: one planar region bounded by the flange circle, with the
    # collar C and the hole as holes; the steel cup ring is the part inside r_inner (texture split, same plane)
    sm.region(outer_region + [fr.loop(gcirc(g["hole"]), hf)])
    sm.set(PAINT, ROUND)
    sm.tube([fr.loop(co, hf), fr.loop(co, -(g["top_h"] - g["ch"]))], closed=False)
    sm.set(PAINT, CHAMFER)
    sm.tube([fr.loop(co, -(g["top_h"] - g["ch"])), fr.loop(cc, -g["top_h"])], closed=False)
    sm.set(PAINT, ROUND)
    sm.tube([fr.loop(ci, hf), fr.loop(ci, -g["top_h"])], closed=False)
    sm.set(PAINT, FLAT)
    sm.tube([fr.loop(cc, -g["top_h"]), fr.loop(ci, -g["top_h"])], closed=False)  # collar top (C)
    for e in (0, -1):                                                         # notch end walls (radial)
        sm.f(fr.p(*co[e], hf), fr.p(*co[e], -(g["top_h"] - g["ch"])), fr.p(*cc[e], -g["top_h"]), fr.p(*ci[e], -g["top_h"]),
             fr.p(*ci[e], hf))
    sm.set(POLYMER, ROUND)
    sm.tube([fr.loop(gcirc(g["hole"]), hf), fr.loop(gcirc(g["hole"]), -g["hole_floor"])])
    sm.set(POLYMER, FLAT); sm.f(*fr.loop(gcirc(g["hole"]), -g["hole_floor"]))


def shelf(FC, sm):
    """flat shelf behind the slope (y = DESK_BACK_Y) with the display base bar"""
    y = DESK_BACK_Y; b = BAR
    outer = [T((-PIL_IN, y, SLOPE_BACK_Z)), T((PIL_IN, y, SLOPE_BACK_Z)), T((PIL_IN, y, 0.0)), T((-PIL_IN, y, 0.0))]
    foot = lambda i, yy: [T((-b["hx"] + i, yy, b["z0"] + i)), T((b["hx"] - i, yy, b["z0"] + i)),
                          T((b["hx"] - i, yy, b["z1"] - i)), T((-b["hx"] + i, yy, b["z1"] - i))]
    FC.add([outer, foot(0, y)])
    sm.set(PAINT, FLAT, KEEP)
    sm.tube([foot(0, y), foot(0, b["y1"] - CH)])
    sm.set(PAINT, CHAMFER)
    sm.tube([foot(0, b["y1"] - CH), foot(CH, b["y1"])])
    sm.set(PAINT, FLAT)
    sm.f(*foot(CH, b["y1"]))


# --------------------------------------------------------------------------- moving / switching parts


def button_top():
    return desk_frame().p(BUTTON_US[0], BUTTON_US[1], -BUTTON_TOP)


def build_button():
    sm = TMesh(); fr = desk_frame()
    top_r = BUTTON_R - BUTTON_CH
    sm.set(REDCAP, ROUND, KEEP)
    sm.tube([fr.loop(gcirc(BUTTON_R), -BUTTON_BOTTOM), fr.loop(gcirc(BUTTON_R), -(BUTTON_TOP - BUTTON_CH))])
    sm.set(REDCAP, CHAMFER)
    sm.tube([fr.loop(gcirc(BUTTON_R), -(BUTTON_TOP - BUTTON_CH)), fr.loop(gcirc(top_r), -BUTTON_TOP)])
    sm.set(REDCAP, FLAT)
    sm.f(*fr.loop(gcirc(top_r), -BUTTON_TOP)); sm.f(*reversed(fr.loop(gcirc(BUTTON_R), -BUTTON_BOTTOM)))
    return sm.finish(f"{HERO}_Button_01", button_top())


def beacon_origin():
    return T((BEACON["x"], PIL_H + BEACON["base_h"], BEACON["z"]))


def build_beacon():
    sm = TMesh(); c2 = (BEACON["x"], BEACON["z"]); y = PIL_H + BEACON["base_h"]
    ring = lambda r, h, n=16: [T((c2[0] + r * math.cos(2 * math.pi * (k + 0.5) / n), y + h,
                                  c2[1] + r * math.sin(2 * math.pi * (k + 0.5) / n))) for k in range(n)]
    r = BEACON["lens_r"]
    prof = [(r, 0.0), (r, 0.040), (0.034, 0.053), (0.021, 0.061), (0.0, 0.064)] if DETAIL else [(r, 0.0), (r, 0.064)]
    sm.set(LENS, ROUND, KEEP)
    if DETAIL:                                                                # cylinder + dome, apex fan (round)
        sm.tube([ring(a, h) for a, h in prof[:-1]])
        top = ring(prof[-2][0], prof[-2][1]); apex = T((c2[0], y + prof[-1][1], c2[1]))
        for k in range(16):
            sm.f(top[k], top[(k + 1) % 16], apex)
    else:
        sm.tube([ring(a, h) for a, h in prof])
        sm.set(LENS, FLAT); sm.f(*ring(prof[-1][0], prof[-1][1]))
    return sm.finish(f"{HERO}_Beacon_01", beacon_origin())


def display_origin():
    return T((0.0, DISPLAY_Y0, DISPLAY_Z))


def build_display():
    me = bpy.data.meshes.new(f"{HERO}_Display_01")
    lean = math.radians(DISPLAY_LEAN)
    up = np.array((0.0, math.cos(lean), -math.sin(lean)))
    o = np.array(display_origin())
    P = [o + np.array((-DISPLAY_W / 2, 0, 0)), o + np.array((DISPLAY_W / 2, 0, 0)),
         o + np.array((DISPLAY_W / 2, 0, 0)) + up * DISPLAY_H, o + np.array((-DISPLAY_W / 2, 0, 0)) + up * DISPLAY_H]
    # Blender coordinates relative to the origin; face normal toward the player (+z)
    V = [to_blender(p - o) for p in P]
    me.from_pydata([tuple(v) for v in V], [], [(0, 1, 2, 3)])
    me.update()
    if me.polygons[0].normal.y > 0: me.flip_normals()                      # face the player (Unity +z = Blender -y)
    # seen from the player (facing -Z) the +X corner is on the LEFT: U runs from +X (0) to -X (1)
    uv = me.uv_layers.new(name="UVMap"); table = {0: (1, 0), 1: (0, 0), 2: (0, 1), 3: (1, 1)}
    for li, l in enumerate(me.loops): uv.data[li].uv = table[l.vertex_index]
    me.update()
    return me


# --------------------------------------------------------------------------- room occluders, hidden faces


ROOM_BOXES = [  # (x0, x1, y0, y1, z0, z1) Unity world: back wall, its floor trim, the left wall
    (-4.0, 0.5, 0.0, 3.0, -2.2, -2.0), (-4.0, 0.5, 0.0, 0.15, -2.0, -1.95), (-4.2, -4.0, 0.0, 3.0, -2.2, 1.0)]


def room_object():
    sm = TMesh()
    for b in ROOM_BOXES:
        G.box(sm, *b)
    me = sm.finish("TerminalRoomProxy")
    return bpy.data.objects.new("TerminalRoomProxy", me)


def delete_hidden(parts, button, room):
    """CULL faces always; RAY faces only when no ray from them escapes (button at rest and pressed)"""
    dirs = CV.fib_dirs(96)
    box_ = ((-1.0, -0.5, -0.5), (4.3, 2.3, 3.0))                               # Blender: x = -spec x, y = -spec z
    keep = {o.name: set() for o in parts}
    rest = button.location.copy()
    n = Vector(desk_frame().n); press = to_blender(tuple(-n * BUTTON_TRAVEL)) - to_blender((0, 0, 0))
    for loc in (rest, rest + press):
        button.location = loc; bpy.context.view_layer.update()
        tree = CV.scene_bvh(parts + [room])
        for o in parts:
            cl = o.data.attributes["cull"].data
            sub = [p for p in o.data.polygons if cl[p.index].value == RAY]
            keep[o.name] |= vis_subset(o, tree, dirs, box_, sub)
    button.location = rest; bpy.context.view_layer.update()
    rep = {}
    for o in parts:
        bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
        lay = bm.faces.layers.int.get("cull")
        kill = [f for f in bm.faces if f[lay] == CULL or (f[lay] == RAY and f.index not in keep[o.name])]
        rep[o.name.replace(HERO + "_", "")] = dict(construction=sum(1 for f in kill if f[lay] == CULL),
                                                   ray=sum(1 for f in kill if f[lay] == RAY),
                                                   ray_candidates=sum(1 for f in bm.faces if f[lay] == RAY))
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bm.to_mesh(o.data); bm.free()
    return rep


def vis_subset(o, tree, dirs, box_, polys):
    """CV.visible_faces restricted to the given polygons"""
    me = o.data
    keep_idx = set(p.index for p in polys)
    class _P:                                                                 # thin proxy: only the candidates
        pass
    proxy = _P(); proxy.matrix_world = o.matrix_world
    class _D:
        pass
    d = _D(); d.vertices = me.vertices; d.polygons = [p for p in me.polygons if p.index in keep_idx]
    proxy.data = d
    return CV.visible_faces(proxy, tree, dirs, box_)


# --------------------------------------------------------------------------- hard edges, UVs, normals


HARD_FLAT = 1.0                              # flat | flat: every crease is hard (the desk's 15 deg crease included)
HARD_ROUND = 30.0
CHAMFER_MAX, CHAMFER_CORNER = 50.0, 15.0


def hard_edge_keys(me):
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
        elif ROUND in (ka, kb): lim = HARD_ROUND
        else: lim = HARD_FLAT
        if a > lim: hard.add(k)
    return hard


def uv_density(o, isl):
    a = sum(f.calc_area() for f in isl)
    n = sum((f.normal * f.calc_area() for f in isl), Vector()).normalized()
    c = sum((f.calc_center_median() * f.calc_area() for f in isl), Vector()) / max(a, 1e-12)
    W = o.matrix_world @ c; sx = -W.x                                         # Unity x
    if n.z < -0.9: return 0.5                                                  # undersides
    if W.z < PLINTH_H - 0.001: return 0.6                                     # plinths
    if n.x > 0.9 and sx < OX - HALF_W + 0.01: return 0.5                      # Pillar_R outer side: 0.6 m from the side wall
    return 1.0


def unwrap_and_pack(parts):
    UV.is_hard = G._is_hard
    UV.HARD_DEG = 0.0
    rep = {}
    for o in parts:
        if not o.data.uv_layers: o.data.uv_layers.new(name="UVMap")
        G._HARD.clear(); G._HARD.update(hard_edge_keys(o.data))
        rep[o.name] = UV.unwrap_object(o)
        UV.scale_islands(o, lambda isl, o=o: uv_density(o, isl))
    rep["px_per_m"] = round(pack_fixed(parts, TEXEL), 1)
    return rep


TEXEL = 512.0                                # ASSET_RULES hero target (px/m at 2048); the sheet has room to spare


def pack_fixed(objs, d):
    """cradle_v2_uv.pack at a fixed density d (px per UV unit) instead of the densest that fits: same skyline
    packing, padding and border; fails loudly if the islands do not fit"""
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
    assert pos, f"islands do not fit the {UV.TEX} sheet at {d} px/m"
    for (uvl, isl, mn, sz), (x, y, turned) in zip(isls, pos):
        ox = (x + UV.PAD_PX // 2 + 0.5) / UV.TEX; oy = (y + UV.PAD_PX // 2 + 0.5) / UV.TEX
        for f in isl:
            for l in f.loops:
                u, v = l[uvl].uv[0] - mn[0], l[uvl].uv[1] - mn[1]
                if turned: u, v = sz[1] - v, u
                l[uvl].uv = (ox + u * d / UV.TEX, oy + v * d / UV.TEX)
    for o, bm, uvl in bms:
        bm.to_mesh(o.data); bm.free()
    return d


def apply_shading(obj):
    G.apply_shading(obj)


# --------------------------------------------------------------------------- materials, assembly


def review_material(name, rgb):
    m = bpy.data.materials.new(name); m.use_nodes = True; m.diffuse_color = (*rgb, 1.0)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = 1.0 if "Steel" in name else 0.0
    b.inputs["Roughness"].default_value = {"Steel": 0.35, "Polymer": 0.65, "RedCap": 0.35, "Lens": 0.2}.get(
        name.split("_")[-1], 0.55)
    if name.endswith(("Cyan", "Switch", "Lens")):
        b.inputs["Emission Color"].default_value = (*rgb, 1.0); b.inputs["Emission Strength"].default_value = 3.0
    if name.endswith("Hazard"):
        nt = m.node_tree
        tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        add = nt.nodes.new("ShaderNodeMath"); add.operation = 'ADD'
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 1 / 0.085
        fr = nt.nodes.new("ShaderNodeMath"); fr.operation = 'FRACT'
        gt = nt.nodes.new("ShaderNodeMath"); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.5
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'
        mix.inputs[6].default_value = (*rgb, 1.0); mix.inputs[7].default_value = (0.017, 0.017, 0.019, 1.0)
        nt.links.new(tc.outputs["Object"], sep.inputs[0]); nt.links.new(sep.outputs[1], add.inputs[0])
        nt.links.new(sep.outputs[2], add.inputs[1]); nt.links.new(add.outputs[0], mul.inputs[0])
        nt.links.new(mul.outputs[0], fr.inputs[0]); nt.links.new(fr.outputs[0], gt.inputs[0])
        nt.links.new(gt.outputs[0], mix.inputs[0]); nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return m


def holo_review_material():
    m = bpy.data.materials.new("M_Term_Holo"); m.use_nodes = True; nt = m.node_tree
    b = nt.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.05, 0.35, 0.45, 1)
    b.inputs["Alpha"].default_value = 0.35; b.inputs["Emission Color"].default_value = (0.06, 0.40, 1.0, 1)
    b.inputs["Emission Strength"].default_value = 0.6
    m.surface_render_method = 'BLENDED'
    return m


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 1.0
    col = bpy.data.collections.new("Terminal_v1"); sc.collection.children.link(col)
    mats = [review_material(n, c) for n, c in MATS]

    def obj(name, me, loc_spec, ms=mats):
        o = bpy.data.objects.new(name, me); col.objects.link(o)
        for m in ms: me.materials.append(m)
        o.location = to_blender(loc_spec)
        return o
    sm = TMesh(); FC = Faces(); ind = TMesh()
    body(FC, sm, ind)
    for sx in (1, -1): pillar(FC, sm, sx)
    FC.emit(sm)
    origin = T((0.0, 0.0, 0.0))
    body_o = obj(f"{HERO}_Body_01", sm.finish(f"{HERO}_Body_01", origin), origin)
    parts = [body_o]
    btn = obj(f"{HERO}_Button_01", build_button(), button_top()); parts.append(btn)
    if DETAIL:
        parts.append(obj(f"{HERO}_Indicators_01", ind.finish(f"{HERO}_Indicators_01", origin), origin))
    parts.append(obj(f"{HERO}_Beacon_01", build_beacon(), beacon_origin()))
    disp = obj(f"{HERO}_Display_01", build_display(), display_origin(), [holo_review_material()])
    room = room_object(); col.objects.link(room)
    bpy.context.view_layer.update()
    removed = delete_hidden(parts, btn, room)
    bpy.data.objects.remove(room)
    uv_report = unwrap_and_pack(parts) if DETAIL else {}
    for o in parts:
        apply_shading(o)
    return parts + [disp], removed, uv_report


def main():
    parts, removed, uv_report = build()
    print("HIDDEN faces deleted:", removed)
    print("UV px/m:", uv_report.get("px_per_m"), {k: v.get("islands") for k, v in uv_report.items() if isinstance(v, dict)})
    os.makedirs(os.path.dirname(SAVE), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, compress=True)
    print("SAVED", SAVE)


if __name__ == "__main__":
    main()
