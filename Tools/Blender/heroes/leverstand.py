"""
Labyrinth VR -- Hero 02b, lever stand (LAB_HERO_LeverStand_*), hero workflow v3 (Blender-textured, no high-poly).

Source of every size: Documentation/HERO_SPEC.md section 6 (pedestal 0.30 x 0.95 x 0.30, housing 0.22 x 0.08 x 0.16,
lever shaft 0.03 x 0.22 + grip 0.05 x 0.10, lamp), section 8 (labyrinth panel, for the clearance). Design: the owner's
concept Documentation/References/LeverStand/leverstand_front.jpg (3/4, master for look and detail) and
leverstand_ortho_side.jpg (proportions and depth). Build notes, feature inventory and deviations:
Documentation/Heroes/LeverStand_BUILD.md. Standard: ASSET_RULES.md hero tier, workflow v3.

Frame: STAND-LOCAL Unity coordinates (metres), origin on the floor under the pedestal centre; +Z local = the front
(cyan strip), which faces the player once the stand is placed at (0.85, 0, 0.60) with yaw 180 (HERO_SPEC §6).
+X local = world -X (toward the labyrinth panel). Mapped to Blender per EXPORT_CONTRACT (x -> -x, y -> z, z -> -y);
the review file holds the stand at the Blender origin WITHOUT the yaw (the checks move the room into this frame).

Parts (review file D:/AI_Labyrinth/Blender/Source/Heroes/LeverStand/LAB_HERO_LeverStand_v1.blend):
  LAB_HERO_LeverStand_Body_01   static: pedestal + housing (slot pocket) + lamp base and cage. Origin = stand origin.
  LAB_HERO_LeverStand_Lever_01  moving: shaft + grip, modelled UPRIGHT (0 deg = middle of the travel), origin on the
                                hinge (HINGE). Hinge axis local X. Stand-local Euler X: rest -30 (leans away from the
                                player = HERO_SPEC "+30 away" in world axes, yaw 180), pulled +30, trigger at 80 %.
  LAB_HERO_LeverStand_Lamp_01   switching: amber glass of the caged lamp (own renderer, so the lamp's emission can be
                                driven by a MaterialPropertyBlock without touching the cyan strip). Origin = its base.

Run:  blender -b --factory-startup -P Tools/Blender/heroes/leverstand.py -- [build|blockout]
Checks and renders: leverstand_check.py; textures: leverstand_tex.py; FBX: leverstand_export.py.
"""
import bpy
import bmesh
import math
import os
import sys
import numpy as np
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cradle_v2 as CV                       # noqa: E402  SpecMesh, polygon offsets, hidden-face ray test
import cradle_v2_uv as UV                    # noqa: E402  unwrap, island scaling, packing
import gate as G                             # noqa: E402  GateMesh (material + face kind per face), hard edges, shading

HERO = "LAB_HERO_LeverStand"
AI_ROOT = os.environ.get("LAB_AI_ROOT", "D:/AI_Labyrinth")
SAVE = f"{AI_ROOT}/Blender/Source/Heroes/LeverStand/LAB_HERO_LeverStand_v1.blend"
SAVE_BLOCKOUT = f"{AI_ROOT}/Blender/Source/Heroes/LeverStand/LAB_HERO_LeverStand_h0_blockout.blend"

# --------------------------------------------------------------------------- placement (HERO_SPEC §6)
WORLD_ORIGIN = (0.85, 0.0, 0.60)
WORLD_YAW = 180.0

# --------------------------------------------------------------------------- pedestal (HERO_SPEC §6 + concept ortho)
PW = 0.30                                    # width = depth (spec; widening fails the 0.15 panel clearance, BUILD.md)
PH = 0.95
CORNER = 0.020                               # vertical corner chamfers (spec 0.02)
BOT_CH = 0.018                               # plinth bottom chamfer, 45 deg (concept)
BAND_Y0, BAND_Y1, BAND_D = 0.855, 0.915, 0.006   # hazard band 0.06 under the cap (spec), recessed 6 mm (concept)
TOP_CH = 0.012                               # cap top edge chamfer (concept)
FIELD = dict(u=0.105, v0=0.080, v1=0.805, c=0.010)   # recessed field between the corner posts, per face
RECESS, FIELD_SLOPE = 0.018, 0.006           # field depth (>= 15 mm: geometry, depth rule), wall inset over the depth
PANEL_D, PANEL_SLOPE = 0.008, 0.003          # raised plates: 10 mm proud of the field floor
PANEL_EDGE, PANEL_GAP = 0.012, 0.005         # plate inset from the field edge; half gap between side plates
CH_D = 0.018                                 # light channel depth into the I-plate
STRIP_PROUD = 0.008                          # light strip face 8 mm proud of the channel floor (Gate)
# front: I-shaped plate ("dogbone", concept) with the cyan strip in a channel in its waist. (u, v): u = viewer's right
I_TOP, I_BOT = (0.700, 0.805 - PANEL_EDGE), (0.080 + PANEL_EDGE, 0.170)
I_W, I_WAIST = 0.093, 0.040                  # half widths: top / bottom parts, waist
I_CUT = 0.045                                # 45 deg transitions (height = width change)
CHANNEL = dict(u=0.020, v0=0.215, v1=0.640)  # light channel (polymer), half width
STRIP = dict(u=0.011, v0=0.240, v1=0.615)    # cyan strip 22 x 375 mm (concept ~25 x 310 at the concept's scale)
# sides: three plates, stepped dividers (concept ortho), f = distance from the plate's FRONT edge as a fraction
DIV_TOP = [(0.0, 0.679), (0.25, 0.679), (0.62, 0.589), (1.0, 0.589)]
DIV_BOT = [(0.0, 0.228), (0.25, 0.228), (0.62, 0.325), (1.0, 0.325)]

# --------------------------------------------------------------------------- housing (HERO_SPEC §6: 0.22 x 0.08 x 0.16)
HX, HZ, HY0, HY1 = 0.110, 0.080, PH, PH + 0.080
H_CH = 0.008                                 # perimeter chamfer of both side faces
# side profile (z, y), CCW seen from +X: low front face, sloped front (concept), flat top, rounded back top edge
H_FRONT_Y, H_SLOPE_Z = 0.995, 0.050
H_FILLET_R = 0.015
SLOT = dict(x0=0.020, x1=0.062, z0=-0.054, z1=0.034, floor=0.965)   # slot (pocket) in the top face, polymer inside
HINGE = (0.041, 0.995, -0.010)               # lever hinge (stand-local), axis X, 35 mm below the housing top
LAMP_C = (-0.055, -0.035)                    # lamp centre (x, z) on the housing top: back half, opposite the slot
LAMP_BASE = dict(r=0.024, h=0.010)
GLASS = dict(r=0.016, h=0.030, dome=0.007, top_r=0.010)
CAGE = dict(r=0.0205, t=0.003, top=0.078)    # bar ring radius, bar section, top ring height above the base top

# --------------------------------------------------------------------------- lever (HERO_SPEC §6)
SHAFT_R, SHAFT_L, SHAFT_BOTTOM = 0.015, 0.220, -0.015
GRIP_R, GRIP_L = 0.025, 0.100
GRIP_CH, GRIP_DOME = 0.0025, 0.015           # grip bottom chamfer, dome height at the top
REST_DEG, PULLED_DEG, TRIGGER_FRAC = -30.0, 30.0, 0.80
SEG = dict(shaft=12, grip=16, lamp=12, cage=8)

MATS = [("M_LeverStand_Paint", (0.10, 0.135, 0.16)), ("M_LeverStand_Polymer", (0.017, 0.018, 0.020)),
        ("M_LeverStand_Steel", (0.50, 0.51, 0.53)), ("M_LeverStand_Hazard", (0.34, 0.19, 0.04)),
        ("M_LeverStand_Cyan", (0.061, 0.402, 1.0)), ("M_LeverStand_Amber", (0.87, 0.30, 0.05)),
        ("M_LeverStand_Ochre", (0.34, 0.19, 0.04))]
PAINT, POLYMER, STEEL, HAZARD, CYAN, AMBER, OCHRE = range(7)
FLAT, CHAMFER, ROUND = G.FLAT, G.CHAMFER, G.ROUND


def to_blender(p):
    return Vector((-p[0], -p[2], p[1]))


def circle(c2, r, n, phase=0.5):
    return [(c2[0] + r * math.cos(2 * math.pi * (k + phase) / n), c2[1] + r * math.sin(2 * math.pi * (k + phase) / n))
            for k in range(n)]


def offset(poly, d):
    return [tuple(p) for p in CV.poly_offset(poly, d)]


class Mesh(G.GateMesh):
    pass


# --------------------------------------------------------------------------- pedestal


def plan(d=0.0):
    """pedestal outline (x, z) inset by d, CCW seen from above in (x, z)... as (x, z) pairs, 8 points (corner chamfers)"""
    h, c = PW / 2, CORNER
    sq = [(h - c, -h), (h, -h + c), (h, h - c), (h - c, h), (-h + c, h), (-h, h - c), (-h, -h + c), (-h + c, -h)]
    return offset(sq, d) if d else sq


def _ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return poly if a > 0 else list(reversed(poly))


# face frames: (u, v, d) -> stand-local point; u = viewer's right seen from outside, d = depth into the pedestal
FACES = {
    "front": lambda u, v, d: (-u, v, PW / 2 - d),
    "back": lambda u, v, d: (u, v, -PW / 2 + d),
    "px": lambda u, v, d: (PW / 2 - d, v, u),        # +X side: the front (+Z) is on the viewer's right
    "nx": lambda u, v, d: (-PW / 2 + d, v, -u),      # -X side: the front is on the viewer's left
}
FRONT_SIGN = {"px": 1.0, "nx": -1.0}                 # u of the front edge = sign * half width


def ring(poly2, y):
    return [(x, y, z) for x, z in poly2]


def loopf(face, poly, d):
    return [FACES[face](u, v, d) for u, v in poly]


def field_poly():
    f = FIELD; u, v0, v1, c = f["u"], f["v0"], f["v1"], f["c"]
    return [(-u + c, v0), (u - c, v0), (u, v0 + c), (u, v1 - c), (u - c, v1), (-u + c, v1), (-u, v1 - c), (-u, v0 + c)]


def i_plate():
    w, ws, c = I_W, I_WAIST, I_CUT
    (vt0, vt1), (vb0, vb1) = I_TOP, I_BOT
    right = [(w, vb0), (w, vb1), (ws, vb1 + c), (ws, vt0 - c), (w, vt0), (w, vt1)]
    left = [(-u, v) for u, v in reversed(right)]
    return right + left                              # CCW (u right, v up), starts bottom right


def rect(u0, u1, v0, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def side_plates(face):
    inner = offset(field_poly(), PANEL_EDGE)
    sgn = FRONT_SIGN[face]; uw = FIELD["u"] - PANEL_EDGE
    def graph(div, dv):                              # divider knots in u (monotone), from the front fractions
        pts = [(sgn * (uw - 2 * uw * f), v + dv) for f, v in div]
        pts = sorted(pts)
        return [(pts[0][0] - 1.0, pts[0][1])] + pts + [(pts[-1][0] + 1.0, pts[-1][1])]
    top = G.clip_graph(inner, graph(DIV_TOP, PANEL_GAP), True)
    mid = G.clip_graph(G.clip_graph(inner, graph(DIV_TOP, -PANEL_GAP), False), graph(DIV_BOT, PANEL_GAP), True)
    bot = G.clip_graph(inner, graph(DIV_BOT, -PANEL_GAP), False)
    return [top, mid, bot]


def face_plates(face):
    if face == "front": return [i_plate()]
    if face == "back": return [offset(field_poly(), PANEL_EDGE)]
    return side_plates(face)


def build_pedestal(sm):
    sm.mat = PAINT
    out0 = plan(); outb = plan(BOT_CH); outband = plan(BAND_D); outtop = plan(TOP_CH)
    # bottom chamfer (floor face not built: floor contact)
    sm.kind = CHAMFER
    sm.tube([ring(outb, 0.0), ring(out0, BOT_CH)])
    # corner chamfer strips from the plinth up to the band (the side planes are regions with the field holes)
    sides = []                                       # (face, its 4 corner points on the ring)
    for i in range(0, 8, 2):                         # out0[i] -> out0[i+1] is a corner chamfer edge
        a, b = out0[i], out0[i + 1]
        sm.kind = CHAMFER
        sm.f((a[0], BOT_CH, a[1]), (b[0], BOT_CH, b[1]), (b[0], BAND_Y0, b[1]), (a[0], BAND_Y0, a[1]))
    # flat side planes y BOT_CH .. BAND_Y0 with the field hole, field walls, floor, plates
    for face in FACES:
        sm.kind = FLAT
        h = PW / 2 - CORNER
        outer = loopf(face, [(-h, BOT_CH), (h, BOT_CH), (h, BAND_Y0), (-h, BAND_Y0)], 0.0)
        sm.mat = PAINT
        fp = field_poly()
        sm.region([outer, loopf(face, fp, 0.0)])
        floor = offset(fp, FIELD_SLOPE)
        sm.tube([loopf(face, fp, 0.0), loopf(face, floor, RECESS)])
        plates = face_plates(face)
        sm.region([loopf(face, floor, RECESS)] + [loopf(face, p, RECESS) for p in plates])
        for p in plates:
            top = offset(p, PANEL_SLOPE)
            sm.tube([loopf(face, p, RECESS), loopf(face, top, PANEL_D)])
            if face == "front":
                ch = rect(-CHANNEL["u"], CHANNEL["u"], CHANNEL["v0"], CHANNEL["v1"])
                sm.region([loopf(face, top, PANEL_D), loopf(face, ch, PANEL_D)])
                sm.mat = POLYMER
                chf = offset(ch, 0.004)
                d_floor = PANEL_D + CH_D
                sm.tube([loopf(face, ch, PANEL_D), loopf(face, chf, d_floor)])
                st = rect(-STRIP["u"], STRIP["u"], STRIP["v0"], STRIP["v1"])
                sm.region([loopf(face, chf, d_floor), loopf(face, st, d_floor)])
                sm.tube([loopf(face, st, d_floor), loopf(face, st, d_floor - STRIP_PROUD)])
                sm.mat = CYAN
                sm.region([loopf(face, st, d_floor - STRIP_PROUD)])
                sm.mat = PAINT
            else:
                sm.region([loopf(face, top, PANEL_D)])
    # hazard band: step in, band, step out; corner chamfers continue on the band (CHAMFER strips)
    sm.mat = PAINT; sm.kind = FLAT
    sm.bridge(ring(out0, BAND_Y0), ring(outband, BAND_Y0))
    sm.tag()
    sm.mat = HAZARD
    for i in range(8):
        sm.kind = CHAMFER if i % 2 == 0 else FLAT
        a, b = outband[i], outband[(i + 1) % 8]
        sm.f((a[0], BAND_Y0, a[1]), (b[0], BAND_Y0, b[1]), (b[0], BAND_Y1, b[1]), (a[0], BAND_Y1, a[1]))
    sm.mat = PAINT; sm.kind = FLAT
    sm.bridge(ring(outband, BAND_Y1), ring(out0, BAND_Y1)); sm.tag()
    for i in range(8):                                                       # cap sides
        sm.kind = CHAMFER if i % 2 == 0 else FLAT
        a, b = out0[i], out0[(i + 1) % 8]
        sm.f((a[0], BAND_Y1, a[1]), (b[0], BAND_Y1, b[1]), (b[0], PH - TOP_CH, b[1]), (a[0], PH - TOP_CH, a[1]))
    sm.kind = CHAMFER
    sm.tube([ring(out0, PH - TOP_CH), ring(outtop, PH)])
    # cap top with the housing footprint as a hole (the top under the housing is hidden: not built)
    sm.kind = FLAT
    sm.region([ring(outtop, PH), ring(housing_footprint(), PH)])


# --------------------------------------------------------------------------- housing, slot, lamp base, cage


def housing_profile():
    """(z, y) CCW seen from +X (z right, y up): front face, slope, top, back fillet, back"""
    r = H_FILLET_R; cz, cy = -HZ + r, HY1 - r
    fil = [(cz + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (90, 120, 150, 180)]
    return [(HZ, HY0), (HZ, H_FRONT_Y), (H_SLOPE_Z, HY1)] + fil + [(-HZ, HY0)]


def housing_side_inset():
    prof = housing_profile()
    ds = [H_CH] * (len(prof) - 1) + [0.0]            # the bottom edge (last -> first) stays on the cap top
    return [tuple(p) for p in CV.poly_offset_var(prof, ds)]


def housing_footprint():
    ins = housing_side_inset()
    zf, zb = ins[0][0], ins[-1][0]                    # side faces' bottom ends (inset by the front/back chamfer)
    x0, x1 = HX - H_CH, HX
    return _ccw([(x0, HZ), (x1, zf), (x1, zb), (x0, -HZ), (-x0, -HZ), (-x1, zb), (-x1, zf), (-x0, HZ)])


def build_housing(sm):
    sm.mat = PAINT
    prof = housing_profile(); ins = housing_side_inset()
    xi = HX - H_CH
    P = lambda x, zy: (x, zy[1], zy[0])
    for s in (1, -1):
        sm.kind = FLAT
        sm.f(*[P(s * HX, p) for p in ins])                                   # side face (planar n-gon -> quads)
        sm.kind = CHAMFER
        sm.tube([[P(s * HX, p) for p in ins], [P(s * xi, p) for p in prof]], closed=False)
    # extruded faces between the two chamfer rows: front, slope, top (region with holes), fillet, back
    n = len(prof)
    top_i = 2                                                               # prof[2] -> prof[3]: the flat top
    for i in range(n - 1):
        a, b = prof[i], prof[i + 1]
        if i == top_i: continue
        sm.kind = ROUND if 3 <= i < 6 else FLAT
        sm.f(P(xi, a), P(xi, b), P(-xi, b), P(-xi, a))
    sm.kind = FLAT
    a, b = prof[top_i], prof[top_i + 1]
    top = _ccw_xz([(xi, a[0]), (xi, b[0]), (-xi, b[0]), (-xi, a[0])])
    slot = _ccw_xz([(SLOT["x0"], SLOT["z0"]), (SLOT["x1"], SLOT["z0"]), (SLOT["x1"], SLOT["z1"]), (SLOT["x0"], SLOT["z1"])])
    base = circle(LAMP_C, LAMP_BASE["r"], SEG["lamp"])
    sm.region([ring(top, HY1), ring(slot, HY1), ring(base, HY1)])
    # slot pocket (polymer)
    sm.mat = POLYMER
    sm.tube([ring(slot, HY1), ring(slot, SLOT["floor"])])
    sm.f(*ring(slot, SLOT["floor"]))
    # lamp base (polymer collar), top annulus with holes for the cage bars; glass = the Lamp part
    ytop = HY1 + LAMP_BASE["h"]
    sm.kind = ROUND
    sm.tube([ring(base, HY1), ring(base, ytop)])
    sm.kind = FLAT
    glass = circle(LAMP_C, GLASS["r"], SEG["lamp"])
    bars = cage_bars()
    sm.region([ring(base, ytop), ring(glass, ytop)] + [ring(b, ytop) for b in bars])
    # cage (steel): 4 bars up into the top ring, top ring (octagon, square section), cross over the dome
    sm.mat = STEEL
    yr = ytop + CAGE["top"] - LAMP_BASE["h"]
    t = CAGE["t"]
    for b in bars:
        sm.tube([ring(b, ytop), ring(b, yr)])                                 # top end inside the ring: not built
    oct_o = circle(LAMP_C, CAGE["r"] + t / 2, SEG["cage"], 0.0); oct_i = circle(LAMP_C, CAGE["r"] - t / 2, SEG["cage"], 0.0)
    y0, y1 = yr - t / 2, yr + t / 2
    sm.tube([ring(oct_o, y0), ring(oct_o, y1), ring(oct_i, y1), ring(oct_i, y0), ring(oct_o, y0)])
    for ang in (0.0, 90.0):                                                 # cross bars over the dome
        a = math.radians(ang + 45.0)
        dx, dz = math.cos(a), math.sin(a); nx, nz = -dz, dx
        L = CAGE["r"] - t / 2
        cx, cz = LAMP_C
        p0 = (cx - dx * L, cz - dz * L); p1 = (cx + dx * L, cz + dz * L)
        hw = t / 2 * (1.0 if ang == 0 else 0.999)
        yb, yt = (y1, y1 + t) if ang == 0 else (y1 + t, y1 + 2 * t)
        sec = [(p0[0] + nx * hw, p0[1] + nz * hw), (p0[0] - nx * hw, p0[1] - nz * hw),
               (p1[0] - nx * hw, p1[1] - nz * hw), (p1[0] + nx * hw, p1[1] + nz * hw)]
        box_xz(sm, sec, yb if ang == 0 else y1, yt)


def _ccw_xz(poly):
    return _ccw(poly)


def box_xz(sm, quad, y0, y1):
    q = _ccw(quad)
    sm.tube([ring(q, y0), ring(q, y1)])
    sm.f(*ring(q, y1)); sm.f(*reversed(ring(q, y0)))


def cage_bars():
    t = CAGE["t"]; out = []
    for k in range(4):
        a = math.radians(45 + 90 * k)
        cx, cz = LAMP_C[0] + CAGE["r"] * math.cos(a), LAMP_C[1] + CAGE["r"] * math.sin(a)
        out.append(_ccw([(cx - t / 2, cz - t / 2), (cx + t / 2, cz - t / 2), (cx + t / 2, cz + t / 2), (cx - t / 2, cz + t / 2)]))
    return out


def build_body():
    sm = Mesh()
    build_pedestal(sm)
    build_housing(sm)
    return sm.finish(f"{HERO}_Body_01", (0.0, 0.0, 0.0))


def lamp_origin():
    return (LAMP_C[0], HY1 + LAMP_BASE["h"], LAMP_C[1])


def build_lamp():
    sm = Mesh(); sm.mat = AMBER
    ox, oy, oz = lamp_origin()
    g = circle((ox, oz), GLASS["r"], SEG["lamp"]); gt = circle((ox, oz), GLASS["top_r"], SEG["lamp"])
    y1 = oy + GLASS["h"]
    sm.kind = ROUND
    sm.tube([ring(g, oy), ring(g, y1 - GLASS["dome"])])
    sm.kind = CHAMFER
    sm.tube([ring(g, y1 - GLASS["dome"]), ring(gt, y1)])
    sm.kind = FLAT
    sm.f(*ring(gt, y1))
    return sm.finish(f"{HERO}_Lamp_01", lamp_origin())


# --------------------------------------------------------------------------- lever (upright, origin on the hinge)


def build_lever():
    sm = Mesh()
    hx, hy, hz = HINGE
    C = (hx, hz)
    sh = circle(C, SHAFT_R, SEG["shaft"]); shb = circle(C, SHAFT_R - 0.003, SEG["shaft"])
    y_b, y_t = hy + SHAFT_BOTTOM, hy + SHAFT_L
    sm.mat = STEEL
    sm.kind = FLAT; sm.f(*reversed(ring(shb, y_b)))
    sm.kind = CHAMFER; sm.tube([ring(shb, y_b), ring(sh, y_b + 0.003)])
    sm.kind = ROUND; sm.tube([ring(sh, y_b + 0.003), ring(sh, y_t)])
    sm.mat = OCHRE
    gs = SEG["grip"]
    g0 = circle(C, GRIP_R - GRIP_CH, gs); g1 = circle(C, GRIP_R, gs)
    gd1 = circle(C, GRIP_R - 0.005, gs); gd2 = circle(C, GRIP_R - 0.013, gs)
    shg = circle(C, SHAFT_R, gs)                          # shaft section re-sampled at the grip's count
    yg0, yg1 = y_t, y_t + GRIP_L
    sm.kind = FLAT
    # grip underside: annulus between the 12-gon shaft and the 16-gon grip bottom (quad-first bridge)
    annulus_bridge(sm, ring(g0, yg0), ring(sh, y_t))
    sm.kind = CHAMFER; sm.tube([ring(g0, yg0), ring(g1, yg0 + GRIP_CH)])
    sm.kind = ROUND; sm.tube([ring(g1, yg0 + GRIP_CH), ring(g1, yg1 - GRIP_DOME)])
    sm.kind = ROUND; sm.tube([ring(g1, yg1 - GRIP_DOME), ring(gd1, yg1 - 0.005), ring(gd2, yg1)])
    sm.kind = FLAT; sm.f(*ring(gd2, yg1))
    return sm.finish(f"{HERO}_Lever_01", HINGE)


def annulus_bridge(sm, outer, inner):
    """flat annulus (y = const) between rings of different counts: quad-first bridge of cradle_v2 (it expects rings in
    the (x, z) plane via atan2(z, x)); our rings are centred off the origin, so shift to the centre and back"""
    cx = sum(p[0] for p in outer) / len(outer); cz = sum(p[2] for p in outer) / len(outer); y = outer[0][1]
    sh = lambda R: [(p[0] - cx, p[1], p[2] - cz) for p in R]
    class Proxy:
        def __init__(s): s.bridge_report = []
        def f(s, *pts): return sm.f(*[(p[0] + cx, p[1], p[2] + cz) for p in pts])
    px = Proxy()
    CV.SpecMesh.quad_bridge(px, sh(outer), sh(inner))
    sm.tag()


# --------------------------------------------------------------------------- blockout (H0)


def build_blockout():
    """H0: primary forms only (spec sizes): pedestal box with corner chamfers, band, cap, housing profile, slot as a
    dark plate, lever cylinders, lamp cylinder, strip plate. Same frame and origins as the H1 parts."""
    parts = {}
    sm = Mesh(); sm.mat = PAINT
    o = plan()
    sm.kind = FLAT
    sm.tube([ring(o, 0.0), ring(o, BAND_Y0)]); sm.mat = HAZARD
    sm.tube([ring(plan(BAND_D), BAND_Y0), ring(plan(BAND_D), BAND_Y1)]); sm.mat = PAINT
    sm.bridge(ring(o, BAND_Y0), ring(plan(BAND_D), BAND_Y0)); sm.bridge(ring(plan(BAND_D), BAND_Y1), ring(o, BAND_Y1))
    sm.tube([ring(o, BAND_Y1), ring(o, PH)]); sm.f(*ring(o, PH))
    sm.mat = CYAN
    st = rect(-STRIP["u"], STRIP["u"], STRIP["v0"], STRIP["v1"])
    sm.f(*loopf("front", st, -0.002))
    sm.mat = PAINT
    prof = housing_profile()
    P = lambda x, zy: (x, zy[1], zy[0])
    sm.f(*[P(HX, p) for p in prof]); sm.f(*reversed([P(-HX, p) for p in prof]))
    sm.tube([[P(HX, p) for p in prof], [P(-HX, p) for p in prof]], closed=False)
    sm.mat = POLYMER
    slot = _ccw([(SLOT["x0"], SLOT["z0"]), (SLOT["x1"], SLOT["z0"]), (SLOT["x1"], SLOT["z1"]), (SLOT["x0"], SLOT["z1"])])
    sm.f(*ring(slot, HY1 + 0.001))
    base = circle(LAMP_C, LAMP_BASE["r"], SEG["lamp"])
    sm.tube([ring(base, HY1), ring(base, HY1 + LAMP_BASE["h"])]); sm.f(*ring(base, HY1 + LAMP_BASE["h"]))
    parts["Body_01"] = (sm.finish(f"{HERO}_Body_01_h0", (0, 0, 0)), (0, 0, 0))
    lm = Mesh(); lm.mat = AMBER
    ox, oy, oz = lamp_origin(); g = circle((ox, oz), GLASS["r"], SEG["lamp"])
    lm.tube([ring(g, oy), ring(g, oy + GLASS["h"])]); lm.f(*ring(g, oy + GLASS["h"]))
    parts["Lamp_01"] = (lm.finish(f"{HERO}_Lamp_01_h0", lamp_origin()), lamp_origin())
    lv = Mesh(); lv.mat = STEEL
    C = (HINGE[0], HINGE[2]); sh = circle(C, SHAFT_R, SEG["shaft"]); gr = circle(C, GRIP_R, SEG["grip"])
    lv.tube([ring(sh, HINGE[1]), ring(sh, HINGE[1] + SHAFT_L)]); lv.mat = OCHRE
    lv.tube([ring(gr, HINGE[1] + SHAFT_L), ring(gr, HINGE[1] + SHAFT_L + GRIP_L)])
    lv.f(*ring(gr, HINGE[1] + SHAFT_L + GRIP_L)); lv.f(*reversed(ring(gr, HINGE[1] + SHAFT_L)))
    parts["Lever_01"] = (lv.finish(f"{HERO}_Lever_01_h0", HINGE), HINGE)
    return parts


# --------------------------------------------------------------------------- materials, UVs, shading, assembly


def review_material(name, rgb):
    m = G.review_material(name, rgb)
    if name.endswith("Ochre"):
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.34, 0.19, 0.045, 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.5
    if name.endswith("Hazard"):                                            # stripes in stand-local object space
        pass
    return m


LEVER_DENSITY = 2.0                     # hand-held: 2 x the hero density (ASSET_RULES: hand-held props 1024 px/m)
LOW_DENSITY = 0.5                       # undersides, the slot pocket, the lamp base top: rarely seen


def uv_density(o, isl):
    if o.name.endswith("Lever_01"): return LEVER_DENSITY
    n = sum((f.normal * f.calc_area() for f in isl), Vector()).normalized()
    if n.z < -0.9: return LOW_DENSITY                                       # faces looking down
    if all(f.material_index == POLYMER for f in isl):
        c = sum((f.calc_center_median() for f in isl), Vector()) / len(isl)
        if c.z < HY1 - 0.002 and c.z > PH: return LOW_DENSITY            # slot pocket
    return 1.0


UV_TEX = int(os.environ.get("LEVERSTAND_UV", "1024"))


def unwrap_and_pack(parts):
    UV.is_hard = G._is_hard
    UV.HARD_DEG = 0.0
    UV.TEX = UV_TEX
    rep = {}
    for o in parts:
        if not o.data.uv_layers: o.data.uv_layers.new(name="UVMap")
        G._HARD.clear(); G._HARD.update(G.hard_edge_keys(o.data))
        rep[o.name] = UV.unwrap_object(o)
        UV.scale_islands(o, lambda isl, o=o: uv_density(o, isl))
    rep["px_per_m"] = round(UV.pack(parts), 1)
    return rep


def new_scene(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 1.0
    col = bpy.data.collections.new(name); sc.collection.children.link(col)
    return col


def build():
    col = new_scene("LeverStand_v1")
    mats = [review_material(n, c) for n, c in MATS]

    def obj(name, me, loc):
        o = bpy.data.objects.new(name, me); col.objects.link(o)
        for m in mats: me.materials.append(m)
        o.location = to_blender(loc)
        return o
    body = obj(f"{HERO}_Body_01", build_body(), (0, 0, 0))
    lever = obj(f"{HERO}_Lever_01", build_lever(), HINGE)
    lamp = obj(f"{HERO}_Lamp_01", build_lamp(), lamp_origin())
    parts = [body, lever, lamp]
    bpy.context.view_layer.update()
    removed = delete_hidden(parts, lever)
    print("HIDDEN faces deleted:", removed)
    uv = unwrap_and_pack(parts)
    for o in parts:
        G.apply_shading(o)
    set_lever(lever, REST_DEG)
    return parts, uv


def delete_hidden(parts, lever):
    """faces never seen in 96 directions over the lever's rest / upright / pulled poses (cradle_v2 ray test). Only the
    lever's faces inside the slot pocket may go (the shaft's bottom end); the body and the lamp are built without
    hidden faces (the check reports them)"""
    dirs = CV.fib_dirs(96)
    box = ((-0.6, -0.6, -0.1), (0.6, 0.6, 1.6))
    keep = set()
    for deg in (REST_DEG, 0.0, PULLED_DEG):
        set_lever(lever, deg)
        tree = CV.scene_bvh(parts)
        keep |= CV.visible_faces(lever, tree, dirs, box)
    set_lever(lever, 0.0)
    bm = bmesh.new(); bm.from_mesh(lever.data); bm.faces.ensure_lookup_table()
    kill = [f for f in bm.faces if f.index not in keep and f.calc_center_median().z < HY1 - HINGE[1]]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(lever.data); bm.free()
    return {"Lever_01": len(kill)}


def set_lever(lever, deg):
    """stand-local Euler X of the hinge (Unity); Blender rotation about its local X has the same sign here
    (x mirrored and the rotation sense mirrored: +deg leans the lever toward local +Z = the front)"""
    lever.rotation_euler = (math.radians(deg), 0.0, 0.0)
    bpy.context.view_layer.update()


def blockout():
    col = new_scene("LeverStand_h0")
    mats = [review_material(n, c) for n, c in MATS]
    objs = {}
    for k, (me, loc) in build_blockout().items():
        o = bpy.data.objects.new(f"{HERO}_{k}", me); col.objects.link(o)
        for m in mats: me.materials.append(m)
        o.location = to_blender(loc); objs[k] = o
    set_lever(objs["Lever_01"], REST_DEG)
    os.makedirs(os.path.dirname(SAVE_BLOCKOUT), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE_BLOCKOUT, compress=True)
    print("SAVED", SAVE_BLOCKOUT)


def main(args):
    if args and args[0] == "blockout":
        blockout(); return
    parts, uv = build()
    print("UV:", {k: v for k, v in uv.items() if k == "px_per_m"})
    for o in parts:
        o.data.calc_loop_triangles(); print(f"PART {o.name}: {len(o.data.loop_triangles)} tris")
    os.makedirs(os.path.dirname(SAVE), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, compress=True)
    print("SAVED", SAVE)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
