"""
Labyrinth VR -- Hero 01, docking cradle (LAB_HERO_Cradle_*), production low-poly.

Source of truth for every number: Documentation/HERO_SPEC.md section 3 (spec = Unity axes,
metres). Quality standard: Documentation/ASSET_RULES.md, Hero tier. Export/axis contract:
Documentation/EXPORT_CONTRACT.md. The mapping, spec-object and export helpers come from
env_kit_generator.py (imported, not copied).

Built by construction (no booleans), quads except the deliberate chamfer-corner triangles:
  Base_01  one static mesh: two octagon plinths, turntable, column and clevis hub as one
           continuous surface (every ring carries 16 vertices and bridges 16-to-16 with
           quads), plus the two hinge pins (separate pieces, hidden parts deleted).
  Arm_01   one mesh for both sides, origin on the hinge; rounded boss around the pin.
  Pad_01   one mesh for both sides, origin on the same hinge point.

Normals: faces smooth, edges sharp only on uncamfered hard edges (> 60 deg) and on the
octagon corners, then face-area weighted normals baked into the mesh as custom normals.
UVs (Part 1 only): temporary world-scale box UVs from env_kit_generator.apply_box_uv.

Run headless:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
        -P Tools/Blender/heroes/cradle.py -- [--unity] [--render] [--dump <json>]
  --unity   also copy the FBX files to Assets/Environment/Heroes/Cradle/
  --render  write the Part 1 review renders to <UnityProject>/Renders/
  --dump    write per-vertex position/normal sets of the exported meshes (spec axes) for
            the Unity import check
"""

import bpy
import bmesh
import json
import math
import os
import shutil
import sys
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import env_kit_generator as kit  # noqa: E402

# ---------------------------------------------------------------------------
# Parameters -- HERO_SPEC.md section 3 (v6 + clevis 2026-09-26). Spec axes, metres.
# ---------------------------------------------------------------------------

HERO = "LAB_HERO_Cradle"
BASE_NAME = f"{HERO}_Base_01"
ARM_NAME = f"{HERO}_Arm_01"
PAD_NAME = f"{HERO}_Pad_01"

CHAMFER = 0.008                 # ASSET_RULES: one-segment ~8 mm chamfer on large exposed edges
RING = 16                       # vertices per ring of the stack (octagons carry edge midpoints)

T1_APOTHEM, T1_Y0, T1_Y1 = 1.2, 0.0, 0.10          # octagon 2.4 across flats
T2_APOTHEM, T2_Y0, T2_Y1 = 0.8, 0.10, 0.20         # octagon 1.6 across flats
TT_RADIUS, TT_Y0, TT_Y1 = 0.4, 0.20, 0.30          # turntable D 0.8
COL_HALF, COL_Y0, COL_Y1 = 0.15, 0.30, 1.00        # column 0.30 x 0.70 x 0.30

HUB_HALF_X, HUB_Y1, HUB_HALF_Z = 0.20, 1.08, 0.15  # hub envelope 0.40 x 0.08 x 0.30 at y 1.00
SLOT_HALF_Z = 0.095                                # cheeks at |z| 0.095 ... 0.15
BLOCK_HALF_X = 0.095                               # centre block |x| < 0.095

HINGE_X, HINGE_Y = 0.13, 1.04                      # hinges at (-/+0.13, 1.04, 0), axis Z
PIN_RADIUS, PIN_SEGMENTS, PIN_PROUD = 0.01, 8, 0.003

ARM_HALF_X, ARM_LENGTH, ARM_HALF_Z = 0.03, 0.50, 0.09   # arm 0.06 x 0.50 x 0.18
BOSS_RADIUS, BOSS_SEGMENTS = 0.03, 12                   # full-circle equivalent

PAD_HALF_X, PAD_Y0, PAD_Y1, PAD_HALF_Z = 0.05, 0.50, 0.525, 0.11  # pad 0.10 x 0.025 x 0.22

CRADLE_ORIGIN_UNITY = (0.0, 0.0, 4.69)             # for reference; the builder places it
RELEASE_DEG = 100.0
SHARP_ANGLE_DEG = 60.0

AMBER_NAME = "M_Greybox_Amber"
AMBER_SRGB = (0xE0, 0xA0, 0x20)

SOURCE_BLEND = "D:/AI_Labyrinth/Blender/Source/Heroes/Cradle/LAB_HERO_Cradle.blend"
EXPORT_DIR = "D:/AI_Labyrinth/Blender/Export/Heroes/Cradle"
PROJECT_DIR = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
UNITY_DIR = os.path.join(PROJECT_DIR, "Assets", "Environment", "Heroes", "Cradle")
RENDER_DIR = os.path.join(PROJECT_DIR, "Renders")


# ---------------------------------------------------------------------------
# Spec-space helpers
# ---------------------------------------------------------------------------

def to_spec(v):
    """Blender -> spec (the inverse of the authoring mapping; it is its own inverse up to order)."""
    return Vector((-v[0], v[2], -v[1]))


def to_blender(s):
    return Vector((-s[0], -s[2], s[1]))


class SpecMesh:
    """Vertices by spec coordinate (merged on a 1e-6 grid) and faces by vertex loops."""

    def __init__(self, bm):
        self.bm = bm
        self.cache = {}

    def v(self, x, y, z):
        key = (round(x, 6) + 0.0, round(y, 6) + 0.0, round(z, 6) + 0.0)
        if key not in self.cache:
            self.cache[key] = self.bm.verts.new(key)
        return self.cache[key]

    def f(self, *pts):
        verts = [self.v(*p) for p in pts]
        assert len(set(verts)) == len(verts), f"degenerate face {pts}"
        face = self.bm.faces.new(verts)
        face.smooth = True
        return face

    def bridge(self, ring_a, ring_b):
        n = len(ring_a)
        for i in range(n):
            j = (i + 1) % n
            self.f(ring_a[i], ring_a[j], ring_b[j], ring_b[i])


def ring_octagon(apothem, y):
    """16 points at 22.5 deg steps: flat midpoints (even k) and corners (odd k), flats face +-X/+-Z."""
    corner_r = apothem / math.cos(math.radians(22.5))
    return [((apothem if k % 2 == 0 else corner_r) * math.cos(math.radians(22.5 * k)), y,
             (apothem if k % 2 == 0 else corner_r) * math.sin(math.radians(22.5 * k)))
            for k in range(RING)]


def ring_circle(radius, y):
    return [(radius * math.cos(math.radians(22.5 * k)), y, radius * math.sin(math.radians(22.5 * k)))
            for k in range(RING)]


def ring_column(y):
    """
    The column cross-section as a 16-vertex chamfered square, in angle order so it bridges to
    the turntable circle with quads. +-X faces carry z = 0 and +-0.095 (the slot and cheek
    planes meet the column top there); +-Z faces carry x = 0. Symmetric in X and Z.
    """
    c, cc, m = COL_HALF, COL_HALF - CHAMFER, SLOT_HALF_Z
    xz = [(c, 0), (c, m), (c, cc), (cc, c), (0, c), (-cc, c), (-c, cc), (-c, m),
          (-c, 0), (-c, -m), (-c, -cc), (-cc, -c), (0, -c), (cc, -c), (c, -cc), (c, -m)]
    return [(x, y, z) for x, z in xz]


# ---------------------------------------------------------------------------
# Base_01: plinths + turntable + column + clevis hub + pins
# ---------------------------------------------------------------------------

def add_stack(sm):
    rings = [
        ring_octagon(T1_APOTHEM, T1_Y0),                        # floor border (floor face deleted)
        ring_octagon(T1_APOTHEM, T1_Y1 - CHAMFER),
        ring_octagon(T1_APOTHEM - CHAMFER, T1_Y1),              # T1 rim chamfer
        ring_octagon(T2_APOTHEM, T2_Y0),                        # T1 top annulus -> T2 foot
        ring_octagon(T2_APOTHEM, T2_Y1 - CHAMFER),
        ring_octagon(T2_APOTHEM - CHAMFER, T2_Y1),              # T2 rim chamfer
        ring_circle(TT_RADIUS, TT_Y0),                          # T2 top annulus -> turntable foot
        ring_circle(TT_RADIUS, TT_Y1 - CHAMFER),
        ring_circle(TT_RADIUS - CHAMFER, TT_Y1),                # turntable rim chamfer
        ring_column(COL_Y0),                                    # turntable top -> column foot
        ring_column(COL_Y1),                                    # column top (meets the hub)
    ]
    for a, b in zip(rings, rings[1:]):
        sm.bridge(a, b)


def add_hub(sm):
    """
    Clevis hub, one quadrant at a time (x >= 0, z >= 0), mirrored in X and Z. Every face lives
    in one quadrant, so faces that cross x = 0 or z = 0 are split there. Chamfered: top
    perimeter and the four vertical end corners (outer envelope). Slot edges stay sharp.
    """
    X0, XC = HUB_HALF_X, HUB_HALF_X - CHAMFER
    Z0, ZC = HUB_HALF_Z, HUB_HALF_Z - CHAMFER
    ZS, XB = SLOT_HALF_Z, BLOCK_HALF_X
    C, CC = COL_HALF, COL_HALF - CHAMFER
    YB, YT, YTC = COL_Y1, HUB_Y1, HUB_Y1 - CHAMFER
    quadrant = [
        [(0, YB, Z0), (CC, YB, Z0), (CC, YTC, Z0), (0, YTC, Z0)],       # front face, over column
        [(CC, YB, Z0), (XC, YB, Z0), (XC, YTC, Z0), (CC, YTC, Z0)],     # front face, overhang
        [(0, YTC, Z0), (CC, YTC, Z0), (CC, YT, ZC), (0, YT, ZC)],       # top-front chamfer
        [(CC, YTC, Z0), (XC, YTC, Z0), (XC, YT, ZC), (CC, YT, ZC)],
        [(XC, YTC, Z0), (X0, YTC, ZC), (XC, YT, ZC)],                   # chamfer corner (tri)
        [(XC, YB, Z0), (X0, YB, ZC), (X0, YTC, ZC), (XC, YTC, Z0)],     # vertical corner chamfer
        [(X0, YB, ZS), (X0, YB, ZC), (X0, YTC, ZC), (X0, YTC, ZS)],     # cheek end face
        [(X0, YTC, ZS), (X0, YTC, ZC), (XC, YT, ZC), (XC, YT, ZS)],     # top-end chamfer
        [(0, YT, 0), (XB, YT, 0), (XB, YT, ZS), (0, YT, ZS)],           # top: centre block
        [(0, YT, ZS), (XB, YT, ZS), (CC, YT, ZC), (0, YT, ZC)],         # top: cheek, inner
        [(XB, YT, ZS), (XC, YT, ZS), (XC, YT, ZC), (CC, YT, ZC)],       # top: cheek, outer
        [(XB, YB, ZS), (C, YB, ZS), (XC, YT, ZS), (XB, YT, ZS)],        # cheek inner face (slot wall)
        [(C, YB, ZS), (X0, YB, ZS), (X0, YTC, ZS), (XC, YT, ZS)],
        [(XB, YB, 0), (XB, YB, ZS), (XB, YT, ZS), (XB, YT, 0)],         # centre block end (slot back)
        [(XB, YB, 0), (C, YB, 0), (C, YB, ZS), (XB, YB, ZS)],           # slot floor = column top
        [(CC, YB, Z0), (C, YB, ZC), (X0, YB, ZC), (XC, YB, Z0)],        # overhang underside
        [(C, YB, ZC), (C, YB, ZS), (X0, YB, ZS), (X0, YB, ZC)],
    ]
    for sx in (1, -1):
        for sz in (1, -1):
            for loop in quadrant:
                pts = [(sx * x, y, sz * z) for x, y, z in loop]
                sm.f(*(pts if sx * sz > 0 else pts[::-1]))


def pin_ring(cx, cy, z):
    """8 points around the pin axis (Z) at (cx, cy); vertices at 22.5 + 45k deg, X-symmetric."""
    return [(cx + PIN_RADIUS * math.cos(math.radians(22.5 + 45 * k)),
             cy + PIN_RADIUS * math.sin(math.radians(22.5 + 45 * k)), z) for k in range(PIN_SEGMENTS)]


def add_pins(sm):
    """
    Per hinge: a 3 mm pin head proud of each cheek, open where it meets the cheek face.
    Not built: the pin inside the cheeks and inside the boss (always hidden, the boss is
    concentric), and the pin in the 5 mm gaps between cheek and boss -- only visible through
    that 5 mm slit at grazing angles, and 5 of its 32 faces tested fully hidden (2026-09-26).
    """
    for hx in (-HINGE_X, HINGE_X):
        for sz in (1, -1):
            face_z, out_z = sz * HUB_HALF_Z, sz * (HUB_HALF_Z + PIN_PROUD)
            a, b = pin_ring(hx, HINGE_Y, face_z), pin_ring(hx, HINGE_Y, out_z)
            sm.bridge(a, b)
            q = b  # cap: 8-gon as 3 quads
            sm.f(q[0], q[1], q[2], q[3])
            sm.f(q[0], q[3], q[4], q[7])
            sm.f(q[4], q[5], q[6], q[7])


def build_base():
    def add(bm):
        sm = SpecMesh(bm)
        add_stack(sm)
        add_hub(sm)
        add_pins(sm)
    return kit.build_spec_object(BASE_NAME, add)


# ---------------------------------------------------------------------------
# Arm_01 and Pad_01 (local = hinge space)
# ---------------------------------------------------------------------------

def arm_profile(half_w):
    """Open profile in the XY plane: right side top -> down -> round boss -> up left side."""
    half = BOSS_SEGMENTS // 2
    arc = [(half_w * math.cos(math.radians(180 + 360.0 / BOSS_SEGMENTS * k)),
            half_w * math.sin(math.radians(180 + 360.0 / BOSS_SEGMENTS * k))) for k in range(half + 1)]
    return [(half_w, ARM_LENGTH)] + arc[::-1] + [(-half_w, ARM_LENGTH)]


def build_arm():
    assert abs(BOSS_RADIUS - ARM_HALF_X) < 1e-9, "boss radius = half arm width (tangent sides)"

    def add(bm):
        sm = SpecMesh(bm)
        outer, inner = arm_profile(ARM_HALF_X), arm_profile(ARM_HALF_X - CHAMFER)
        zc = ARM_HALF_Z - CHAMFER
        for i in range(len(outer) - 1):                       # perimeter band (top stays open:
            (x0, y0), (x1, y1) = outer[i], outer[i + 1]       # the pad covers it)
            sm.f((x0, y0, zc), (x1, y1, zc), (x1, y1, -zc), (x0, y0, -zc))
        half = BOSS_SEGMENTS // 2
        wc = ARM_HALF_X - CHAMFER
        for sz in (1, -1):
            for i in range(len(outer) - 1):                   # side-face perimeter chamfer
                (ox0, oy0), (ox1, oy1) = outer[i], outer[i + 1]
                (ix0, iy0), (ix1, iy1) = inner[i], inner[i + 1]
                loop = [(ox0, oy0, sz * zc), (ox1, oy1, sz * zc),
                        (ix1, iy1, sz * ARM_HALF_Z), (ix0, iy0, sz * ARM_HALF_Z)]
                sm.f(*(loop if sz > 0 else loop[::-1]))
            z = sz * ARM_HALF_Z
            arc = inner[1:half + 2]                           # (wc,0) ... (-wc,0)
            faces = [[(0, 0, z), (wc, 0, z), (wc, ARM_LENGTH, z), (0, ARM_LENGTH, z)],
                     [(0, 0, z), (0, ARM_LENGTH, z), (-wc, ARM_LENGTH, z), (-wc, 0, z)]]
            for k in range(0, half, 2):                       # boss: quads fanned from the pin centre
                faces.append([(0, 0, z)] + [(arc[k + d][0], arc[k + d][1], z) for d in range(3)])
            for loop in faces:
                sm.f(*(loop if sz > 0 else loop[::-1]))
    return kit.build_spec_object(ARM_NAME, add)


def build_pad():
    def add(bm):
        sm = SpecMesh(bm)
        px, pz, c = PAD_HALF_X, PAD_HALF_Z, CHAMFER
        octo = [(px - c, -pz), (px, -pz + c), (px, pz - c), (px - c, pz),
                (-px + c, pz), (-px, pz - c), (-px, -pz + c), (-px + c, -pz)]
        bottom = [(x, PAD_Y0, z) for x, z in octo]
        rim = [(x, PAD_Y1 - c, z) for x, z in octo]
        top = [(px - c, PAD_Y1, -(pz - c)), (px - c, PAD_Y1, pz - c),
               (-(px - c), PAD_Y1, pz - c), (-(px - c), PAD_Y1, -(pz - c))]
        sm.bridge(bottom, rim)                                # 4 sides + 4 vertical chamfers
        sm.f(rim[1], rim[2], top[1], top[0])                  # top chamfers
        sm.f(rim[3], rim[4], top[2], top[1])
        sm.f(rim[5], rim[6], top[3], top[2])
        sm.f(rim[7], rim[0], top[0], top[3])
        sm.f(rim[0], rim[1], top[0])                          # chamfer corners (tris)
        sm.f(rim[2], rim[3], top[1])
        sm.f(rim[4], rim[5], top[2])
        sm.f(rim[6], rim[7], top[3])
        sm.f(*top)
        b = bottom                                            # underside octagon as 3 quads
        sm.f(b[0], b[1], b[2], b[3])
        sm.f(b[0], b[3], b[4], b[7])
        sm.f(b[4], b[5], b[6], b[7])
    return kit.build_spec_object(PAD_NAME, add)


# ---------------------------------------------------------------------------
# Normals: sharp edges + face-area weighted custom normals
# ---------------------------------------------------------------------------

def is_octagon_corner_edge(e):
    """Vertical/slanted edges on the plinth bands at an octagon corner angle (22.5 + 45k)."""
    a, b = to_spec(e.verts[0].co), to_spec(e.verts[1].co)
    if abs(a.y - b.y) < 1e-6 or a.y > T2_Y1 + 1e-6 or b.y > T2_Y1 + 1e-6:
        return False
    ra, rb = math.hypot(a.x, a.z), math.hypot(b.x, b.z)
    if ra < 0.5 or rb < 0.5:
        return False
    ang_a, ang_b = math.degrees(math.atan2(a.z, a.x)), math.degrees(math.atan2(b.z, b.x))
    same = abs((ang_a - ang_b + 180) % 360 - 180) < 0.01
    return same and abs(((ang_a - 22.5) % 45 + 22.5) % 45 - 22.5) < 0.01


def apply_shading(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    limit = math.radians(SHARP_ANGLE_DEG)
    for e in bm.edges:
        sharp = e.is_manifold and e.calc_face_angle(0.0) > limit
        e.smooth = not (sharp or is_octagon_corner_edge(e))
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(obj.data)
    bm.free()
    mod = obj.modifiers.new("WeightedNormal", 'WEIGHTED_NORMAL')
    mod.mode = 'FACE_AREA'
    mod.weight = 50
    mod.keep_sharp = True
    mod.thresh = 0.01
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)


# ---------------------------------------------------------------------------
# Materials and assembly
# ---------------------------------------------------------------------------

def srgb_to_linear(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def get_amber_material():
    mat = bpy.data.materials.get(AMBER_NAME) or bpy.data.materials.new(AMBER_NAME)
    rgba = tuple(srgb_to_linear(c) for c in AMBER_SRGB) + (1.0,)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.5
    mat.diffuse_color = rgba
    return mat


def collection(name):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    return col


def move_to(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def build_assembly(base, arm, pad):
    """
    Export collection: the three parts at identity (what gets exported).
    Assembly collection: Hinge_L / Hinge_R empties at the hinge points with linked-data
    instances of the arm and pad -- the working view and the render rig. Rotating a hinge
    empty about Blender Y by +deg (L) / -deg (R) opens that arm outward.
    """
    exp, asm = collection("Export"), collection("Assembly")
    for o in (base, arm, pad):
        move_to(o, exp)
    arm.hide_set(True)
    pad.hide_set(True)
    arm.hide_render = pad.hide_render = True
    hinges = {}
    for side, sx in (("L", -1), ("R", 1)):
        hinge = bpy.data.objects.new(f"Hinge_{side}", None)
        hinge.empty_display_type = 'ARROWS'
        hinge.empty_display_size = 0.05
        hinge.location = to_blender((sx * HINGE_X, HINGE_Y, 0.0))
        asm.objects.link(hinge)
        for src, part in ((arm, "Arm"), (pad, "Pad")):
            inst = bpy.data.objects.new(f"{part}_{side}", src.data)
            inst.parent = hinge
            asm.objects.link(inst)
        hinges[side] = hinge
    return hinges


def set_pose(hinges, deg):
    hinges["L"].rotation_euler = (0.0, math.radians(deg), 0.0)
    hinges["R"].rotation_euler = (0.0, -math.radians(deg), 0.0)
    bpy.context.view_layer.update()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def islands(bm):
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(isl)
    return out


def island_orientation_ok(isl):
    """Consistent winding + positive signed volume about the centroid of the open border
    (the missing faces lie in planes through it, so they add nothing) -> normals point out."""
    edges = {e for f in isl for e in f.edges}
    if any(len(e.link_faces) == 2 and not e.is_contiguous for e in edges):
        return False
    border = {v for e in edges if e.is_boundary for v in e.verts}
    pts = border or {v for f in isl for v in f.verts}
    ref = sum((v.co for v in pts), Vector()) / len(pts)
    vol = 0.0
    for f in isl:
        co = [v.co - ref for v in f.verts]
        for i in range(1, len(co) - 1):
            vol += co[0].dot(co[i].cross(co[i + 1])) / 6.0
    return vol > 0.0


def topology_report(obj, open_border_note):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    quads = sum(1 for f in bm.faces if len(f.verts) == 4)
    tris = sum(1 for f in bm.faces if len(f.verts) == 3)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2 or len(e.link_faces) == 0)
    loose_v = sum(1 for v in bm.verts if not v.link_faces)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    dup = len(bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=1e-5)["targetmap"])
    isl = islands(bm)
    bad_orient = sum(1 for i in isl if not island_orientation_ok(i))
    sharp = sum(1 for e in bm.edges if not e.smooth)
    bm.free()
    obj.data.calc_loop_triangles()
    tri_total = len(obj.data.loop_triangles)
    ok = ngons == 0 and nonmanifold == 0 and loose_v == 0 and zero == 0 and dup == 0 and bad_orient == 0
    lines = [
        f"{obj.name}",
        f"  faces: {quads} quads, {tris} tris, {ngons} n-gons -> {tri_total} triangles",
        f"  islands: {len(isl)}, flipped islands: {bad_orient}",
        f"  open border edges: {boundary} ({open_border_note})",
        f"  non-manifold edges: {nonmanifold}, loose verts: {loose_v}, duplicate verts: {dup}, "
        f"zero-area faces: {zero}",
        f"  sharp edges: {sharp}",
        f"  TOPOLOGY: {'PASS' if ok else 'FAIL'}",
    ]
    return ok, tri_total, lines


def world_tris(objs):
    verts, polys = [], []
    for o in objs:
        m = o.matrix_world
        base = len(verts)
        verts.extend(m @ v.co for v in o.data.vertices)
        polys.extend([base + i for i in p.vertices] for p in o.data.polygons)
    return verts, polys


def fibonacci_dirs(n):
    out = []
    ga = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1.0 - 2.0 * (i + 0.5) / n
        r = math.sqrt(1.0 - y * y)
        out.append(Vector((math.cos(ga * i) * r, math.sin(ga * i) * r, y)))
    return out


def hidden_faces(parts, hinges):
    """
    A face counts as hidden when no ray from it (5 sample points, ~600 hemisphere directions)
    escapes the assembly plus the floor, in the standby AND in the released pose.
    Returns {object name: [face indices]}.
    """
    dirs = fibonacci_dirs(1200)
    visible = {o.name: set() for o in parts}
    for deg in (0.0, RELEASE_DEG):
        set_pose(hinges, deg)
        verts, polys = world_tris(parts)
        floor = len(verts)
        verts += [Vector((-50, -50, 0)), Vector((50, -50, 0)), Vector((50, 50, 0)), Vector((-50, 50, 0))]
        polys.append([floor, floor + 1, floor + 2, floor + 3])
        bvh = BVHTree.FromPolygons(verts, polys, epsilon=0.0)
        for o in parts:
            m = o.matrix_world
            nm = m.to_3x3().inverted().transposed()
            for p in o.data.polygons:
                if p.index in visible[o.name]:
                    continue
                n = (nm @ p.normal).normalized()
                c = m @ p.center
                corners = [m @ o.data.vertices[i].co for i in p.vertices]
                samples = [c] + [c.lerp(q, 0.8) for q in corners]
                hemi = [d for d in dirs if d.dot(n) > 0.0]
                if any(bvh.ray_cast(s + n * 1e-5, d, 100.0)[0] is None for s in samples for d in hemi):
                    visible[o.name].add(p.index)
    set_pose(hinges, 0.0)
    return {o.name: sorted(set(range(len(o.data.polygons))) - visible[o.name]) for o in parts}


def classify_base_face(center_spec):
    x, y, z = abs(center_spec.x), center_spec.y, abs(center_spec.z)
    if y < COL_Y0 - 1e-6:
        return "stack"
    if y <= COL_Y1 + 1e-6:
        return "column"
    if x <= BLOCK_HALF_X + 1e-6 and z < SLOT_HALF_Z:
        return "hub centre block"
    return "cheeks"


def is_pin_face(obj, p):
    for i in p.vertices:
        s = to_spec(obj.data.vertices[i].co)
        if min(math.hypot(s.x - hx, s.y - HINGE_Y) for hx in (-HINGE_X, HINGE_X)) > PIN_RADIUS + 1e-4:
            return False
    return True


def sample_points(objs, step=0.002):
    pts = []
    for o in objs:
        m = o.matrix_world
        co = [m @ v.co for v in o.data.vertices]
        pts.extend(co)
        for e in o.data.edges:
            a, b = co[e.vertices[0]], co[e.vertices[1]]
            n = int((b - a).length / step)
            pts.extend(a.lerp(b, (k + 1) / (n + 1)) for k in range(n))
    return pts


def sweep_report(base, hinges):
    """Min clearance of each arm+pad to hub centre block, cheeks and column, 0..100 deg."""
    groups = {}
    for p in base.data.polygons:
        if is_pin_face(base, p):
            continue
        groups.setdefault(classify_base_face(to_spec(p.center)), []).append(p)
    bvhs = {}
    for g, polys in groups.items():
        bvhs[g] = BVHTree.FromPolygons([v.co.copy() for v in base.data.vertices],
                                       [list(p.vertices) for p in polys], epsilon=0.0)
    lines, worst, overlap_any = [], {g: 9.0 for g in ("hub centre block", "cheeks", "column")}, False
    arms = {side: [c for c in hinges[side].children] for side in ("L", "R")}
    at100 = {}
    for step in range(0, int(RELEASE_DEG) + 1, 5):
        set_pose(hinges, float(step))
        row = []
        for side in ("L", "R"):
            pts = sample_points(arms[side])
            vs, ps = world_tris(arms[side])
            moving = BVHTree.FromPolygons(vs, ps, epsilon=0.0)
            for g in ("hub centre block", "cheeks", "column"):
                d = min(bvhs[g].find_nearest(q)[3] for q in pts)
                if bvhs[g].overlap(moving):
                    overlap_any = True
                    d = -d
                worst[g] = min(worst[g], d)
                row.append(d)
            if step == int(RELEASE_DEG):
                ys = [to_spec(q).y for q in vs]
                pad = [c for c in arms[side] if c.data.name.startswith(PAD_NAME)][0]
                tip = to_spec(pad.matrix_world @ Vector(to_blender((0, (PAD_Y0 + PAD_Y1) / 2, 0))))
                at100[side] = (max(ys), min(ys), tip)
        lines.append(f"  {step:3d} deg  L: block {row[0]*1000:5.1f}  cheeks {row[1]*1000:5.1f}  column {row[2]*1000:5.1f}"
                     f"   R: block {row[3]*1000:5.1f}  cheeks {row[4]*1000:5.1f}  column {row[5]*1000:5.1f}  (mm)")
    set_pose(hinges, 0.0)
    ok = not overlap_any and min(worst.values()) >= 0.003
    lines.append(f"  minimum over sweep: " + ", ".join(f"{g} {d*1000:.1f} mm" for g, d in worst.items()))
    for side, (top, low, tip) in at100.items():
        ok &= top < 1.19
        lines.append(f"  at {RELEASE_DEG:.0f} deg {side}: highest y {top:.3f} (< 1.19), lowest y {low:.3f}, "
                     f"pad centre ({tip.x:.3f}, {tip.y:.3f})")
    lines.append(f"  SWEEP: {'PASS' if ok else 'FAIL'}")
    return ok, lines


# ---------------------------------------------------------------------------
# Export check data for Unity
# ---------------------------------------------------------------------------

def export_signature(obj):
    """Unique (position, normal) pairs of the triangulated export mesh, spec axes, 1e-4 grid."""
    copy = kit.triangulated_export_copy(obj)
    me = copy.data
    pairs = set()
    for li, loop in enumerate(me.loops):
        p = to_spec(me.vertices[loop.vertex_index].co)
        n = to_spec(me.corner_normals[li].vector)
        pairs.add(tuple(round(c, 4) + 0.0 for c in (*p, *n)))
    tris = len(me.polygons)
    bpy.data.objects.remove(copy, do_unlink=True)
    bpy.data.meshes.remove(me)
    return {"tris": tris, "pairs": sorted(pairs)}


# ---------------------------------------------------------------------------
# Renders
# ---------------------------------------------------------------------------

def render_setup():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    shading = scene.display.shading
    shading.light = 'STUDIO'
    shading.color_type = 'MATERIAL'
    shading.show_cavity = False
    shading.show_specular_highlight = True
    scene.display.render_aa = '16'
    scene.render.film_transparent = False
    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.render.image_settings.file_format = 'PNG'
    grey = bpy.data.materials.get(kit.MATERIAL_NAME)
    grey.diffuse_color = (0.30, 0.31, 0.33, 1.0)
    floor = bpy.data.meshes.new("RenderFloor")
    floor.from_pydata([(-40, -40, -0.0005), (40, -40, -0.0005), (40, 40, -0.0005), (-40, 40, -0.0005)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("RenderFloor", floor)
    fm = bpy.data.materials.new("RenderFloor")
    fm.diffuse_color = (0.08, 0.08, 0.09, 1.0)
    floor.materials.append(fm)
    rig = collection("RenderRig")
    rig.objects.link(fo)
    return rig


def add_wire_overlays(rig, thickness):
    mat = bpy.data.materials.get("RenderWire") or bpy.data.materials.new("RenderWire")
    mat.diffuse_color = (0.02, 0.02, 0.02, 1.0)
    wires = []
    for o in list(collection("Assembly").objects) + [bpy.data.objects[BASE_NAME]]:
        if o.type != 'MESH':
            continue
        w = bpy.data.objects.new(o.name + "_wire", o.data)
        w.parent = o.parent
        w.matrix_parent_inverse = o.matrix_parent_inverse
        w.matrix_basis = o.matrix_basis
        mod = w.modifiers.new("Wire", 'WIREFRAME')
        mod.thickness = thickness
        mod.use_even_offset = True
        mod.use_replace = True
        mod.offset = 0.6
        mod.use_boundary = True
        rig.objects.link(w)
        w.material_slots[0].link = 'OBJECT'     # the mesh is shared: colour the overlay per object
        w.material_slots[0].material = mat
        wires.append(w)
    return wires


def camera(rig, name, loc_spec, target_spec, ortho_width=None, lens=50.0):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        rig.objects.link(cam)
    loc, tgt = to_blender(loc_spec), to_blender(target_spec)
    cam.location = loc
    cam.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
    if ortho_width:
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = ortho_width
    else:
        cam.data.type = 'PERSP'
        cam.data.lens = lens
    cam.data.clip_start, cam.data.clip_end = 0.01, 100.0
    return cam


def render_panels(views, hinges, path, size=(1600, 1000), cols=2):
    """views: list of (camera, pose_deg). Renders each, tiles them into one PNG."""
    import numpy as np
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    tiles = []
    for i, (cam, deg) in enumerate(views):
        set_pose(hinges, deg)
        scene.camera = cam
        tmp = os.path.join(RENDER_DIR, f"_tile_{i}.png")
        scene.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(size[1], size[0], 4)
        tiles.append(px)
        bpy.data.images.remove(img)
        os.remove(tmp)
    set_pose(hinges, 0.0)
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.ones((rows * size[1], cols * size[0], 4), dtype=np.float32)
    for i, t in enumerate(tiles):
        r, c = i // cols, i % cols
        # image pixels start bottom-left; row 0 of the sheet is the top row of panels
        y0 = (rows - 1 - r) * size[1]
        sheet[y0:y0 + size[1], c * size[0]:(c + 1) * size[0]] = t
    out = bpy.data.images.new(os.path.basename(path), cols * size[0], rows * size[1], alpha=True)
    out.pixels = sheet.ravel()
    out.filepath_raw = path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    return path


def make_renders(hinges):
    os.makedirs(RENDER_DIR, exist_ok=True)
    rig = render_setup()
    # "Front" = seen from spec +Z (the side the player enters from); spec -X (Arm_L) is on the right.
    front = camera(rig, "Cam_Front", (0, 0.85, 6.0), (0, 0.85, 0), ortho_width=2.9)
    q34 = camera(rig, "Cam_34", (2.6, 2.2, 3.4), (0, 0.7, 0), lens=40)
    views = [(front, 0.0), (q34, 0.0), (front, RELEASE_DEG), (q34, RELEASE_DEG)]
    out = [render_panels(views, hinges, os.path.join(RENDER_DIR, "cradle_p1_shaded.png"))]
    wires = add_wire_overlays(rig, 0.0022)
    out.append(render_panels(views, hinges, os.path.join(RENDER_DIR, "cradle_p1_wire.png")))
    for w in wires:
        w.modifiers["Wire"].thickness = 0.0007
    c1 = camera(rig, "Cam_Clevis34", (0.95, 1.75, 1.25), (0, 1.27, 0), lens=50)
    c2 = camera(rig, "Cam_ClevisFront", (0, 1.28, 3.0), (0, 1.28, 0), ortho_width=0.95)
    c3 = camera(rig, "Cam_ClevisTop", (0.0, 2.6, 0.001), (0, 1.0, 0), ortho_width=0.55)
    c4 = camera(rig, "Cam_ClevisLow", (0.42, 0.95, 0.5), (-0.05, 1.05, 0), lens=50)
    for w in wires:
        w.hide_render = True
    views = [(c1, 0.0), (c2, 0.0), (c4, RELEASE_DEG), (c3, RELEASE_DEG)]
    out.append(render_panels(views, hinges, os.path.join(RENDER_DIR, "cradle_p1_clevis.png")))
    for w in wires:
        w.hide_render = False
    out.append(render_panels(views, hinges, os.path.join(RENDER_DIR, "cradle_p1_clevis_wire.png")))
    for o in list(rig.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(rig)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    to_unity, do_render = "--unity" in argv, "--render" in argv
    dump = argv[argv.index("--dump") + 1] if "--dump" in argv else None

    kit.clear_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0

    base, arm, pad = build_base(), build_arm(), build_pad()
    pad.data.materials.clear()
    pad.data.materials.append(get_amber_material())
    for o in (base, arm, pad):
        apply_shading(o)
        kit.apply_box_uv(o)          # Part 1: temporary UVs, replaced by the unwrap in Part 2
    hinges = build_assembly(base, arm, pad)

    report, ok, total = [f"[cradle] {HERO} low-poly"], True, 0
    notes = {BASE_NAME: "16 floor edges + 4 x 8 pin-head edges on the cheek faces",
             ARM_NAME: "top, covered by the pad", PAD_NAME: "none expected"}
    tri_counts = {}
    for o in (base, arm, pad):
        part_ok, tris, lines = topology_report(o, notes[o.name])
        ok &= part_ok
        tri_counts[o.name] = tris
        report += lines
    total = tri_counts[BASE_NAME] + 2 * (tri_counts[ARM_NAME] + tri_counts[PAD_NAME])
    report.append(f"Cradle total (Base + 2 x Arm + 2 x Pad): {total} triangles (target 1,500-3,000)")

    parts = [base] + [c for side in ("L", "R") for c in hinges[side].children]
    hidden = hidden_faces(parts, hinges)
    n_hidden = sum(len(v) for v in hidden.values())
    report.append(f"hidden faces (standby and released): {n_hidden}"
                  + ("" if not n_hidden else " -> " + "; ".join(f"{k}: {v}" for k, v in hidden.items() if v)))
    ok &= n_hidden == 0

    sweep_ok, lines = sweep_report(base, hinges)
    ok &= sweep_ok
    report.append("sweep (outward: Blender Y +deg for L, -deg for R):")
    report += lines

    # bounds per part (spec axes, local = export space)
    for o in (base, arm, pad):
        s = [to_spec(v.co) for v in o.data.vertices]
        lo = Vector((min(p.x for p in s), min(p.y for p in s), min(p.z for p in s)))
        hi = Vector((max(p.x for p in s), max(p.y for p in s), max(p.z for p in s)))
        report.append(f"bounds {o.name}: ({lo.x:.3f}, {lo.y:.3f}, {lo.z:.3f}) .. ({hi.x:.3f}, {hi.y:.3f}, {hi.z:.3f})")

    os.makedirs(os.path.dirname(SOURCE_BLEND), exist_ok=True)
    paths = [kit.export_fbx(o, EXPORT_DIR, f"{o.name}.fbx", mode="hero") for o in (base, arm, pad)]
    report += [f"exported {p}" for p in paths]
    if to_unity:
        os.makedirs(UNITY_DIR, exist_ok=True)
        for p in paths:
            shutil.copy2(p, os.path.join(UNITY_DIR, os.path.basename(p)))
        report.append(f"copied {len(paths)} FBX to {UNITY_DIR}")
    if dump:
        with open(dump, "w") as f:
            json.dump({o.name: export_signature(o) for o in (base, arm, pad)}, f)
        report.append(f"export signature -> {dump}")

    set_pose(hinges, 0.0)
    bpy.ops.wm.save_as_mainfile(filepath=SOURCE_BLEND)
    report.append(f"saved {SOURCE_BLEND}")
    if do_render:
        report += [f"render {p}" for p in make_renders(hinges)]
    report.append(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print("\n".join(report))


if __name__ == "__main__":
    main()
