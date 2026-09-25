"""
Labyrinth VR -- modular environment kit generator.

Builds the greybox kit for the Industrial Robotics Research Facility from a
single parameter block below, copied from Documentation/ENVIRONMENT_SPEC.md.
If a value changes in the spec, update the block here and regenerate --
do not hand-edit the resulting meshes.

Pass 2 builds the full wall/floor/ceiling/pillar/trim greybox set. Modules are
declared in the MODULES registry at the bottom of the parameter/helper section:
adding a module later means adding a registry entry (dimensions + pivot bounds
function), not new export/build code.

Run headless:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
        -P Tools/Blender/env_kit_generator.py -- --out "D:/AI_Labyrinth/Blender/Generated"

Saves LAB_ENV_kit.blend to --out and exports one FBX per module to
D:/AI_Labyrinth/Blender/Export. Does not touch the Unity project's Assets folder.
"""

import bpy
import bmesh
import json
import math
import os
import sys

# ---------------------------------------------------------------------------
# Parameters -- Documentation/ENVIRONMENT_SPEC.md, approved 2026-09-23.
# All values in meters, spec axes: X width, Y up, Z depth/forward.
# ---------------------------------------------------------------------------

# Room
ROOM_WIDTH_X = 8.0
ROOM_DEPTH_Z = 10.0
INTERIOR_X_MIN, INTERIOR_X_MAX = -4.0, 4.0
INTERIOR_Z_MIN, INTERIOR_Z_MAX = -2.0, 8.0
FLOOR_Y = 0.0
CEILING_HEIGHT = 4.0
GRID_SIZE = 2.0
GRID_MODULES_X = 4
GRID_MODULES_Z = 5
WALL_PANELS_HIGH = 2

# Wall thickness / doorway constants
WALL_THICKNESS = 0.2
DOORWAY_WIDTH = 1.6
DOORWAY_HEIGHT = 2.4
PIPE_CLEARANCE_FROM_WALL = 0.35
TRIM_HEIGHT = 0.15

# Module sizes (X, Y, Z)
WALL_A_SIZE = (2.0, 2.0, WALL_THICKNESS)
WALL_PANEL_SIZE = (2.0, 2.0, WALL_THICKNESS)
WALL_CORNER_SIZE = (WALL_THICKNESS, 4.0, WALL_THICKNESS)
WALL_DOOR_SIZE = (2.0, 4.0, WALL_THICKNESS)
WALL_CORRIDOR_SIZE = (2.0, 3.0, WALL_THICKNESS)
FLOOR_A_SIZE = (2.0, 0.1, 2.0)
CEILING_A_SIZE = (2.0, 0.1, 2.0)
PILLAR_A_SIZE = (0.4, 4.0, 0.4)
TRIM_A_SIZE = (2.0, TRIM_HEIGHT, 0.05)

# Wall_Panel recess -- not yet catalogued in ENVIRONMENT_SPEC.md, given directly for this
# pass. Rectangle centered on the inner face, recessed (pushed away from the room, +spec Z)
# by PANEL_RECESS_DEPTH. Border = (WALL_PANEL_SIZE.xy - PANEL_RECESS_RECT) / 2 = 0.2 all round.
PANEL_RECESS_RECT = (1.6, 1.6)
PANEL_RECESS_DEPTH = 0.05

PIPE_LENGTH = 2.0
PIPE_DIAMETER_SMALL = 0.16
PIPE_DIAMETER_LARGE = 0.25
PIPE_CORNER_RADIUS = 0.3

MATERIAL_NAME = "M_Greybox"
MATERIAL_COLOR = (0.5, 0.5, 0.5, 1.0)
MATERIAL_ROUGHNESS = 0.6

EXPORT_DIR = "D:/AI_Labyrinth/Blender/Export"
BLEND_FILENAME = "LAB_ENV_kit.blend"

# ---------------------------------------------------------------------------
# Labyrinth v2 props -- Documentation/HERO_SPEC.md section 8, approved
# 2026-09-25. Maze layout (walls, ball, goal) is read from
# Tools/Blender/labyrinth_maze_v1.json at build time, never copied by hand.
# ---------------------------------------------------------------------------

MAZE_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "labyrinth_maze_v1.json")

PANEL_HALF_XZ = 0.525            # 1.05 x 1.05 footprint, origin at the centre
PANEL_PLATE_THICKNESS = 0.025
PANEL_RIM_THICKNESS = 0.05
PANEL_RIM_TOP_Y = 0.105
PANEL_GOAL_SEGMENTS = 32
PANEL_GOAL_CUTTER_MARGIN = 0.01  # cutter pokes this far past each plate face

HANDLE_BAR_DIA = 0.035
HANDLE_BAR_LENGTH = 0.25
HANDLE_BAR_CENTER = (0.0, 0.065, -0.605)
HANDLE_BAR_SEGMENTS = 24
HANDLE_BRACKET_SIZE = 0.02
HANDLE_BRACKET_X = (0.10, -0.10)

STAND_BASE_ACROSS_FLATS = 0.40
STAND_BASE_THICKNESS = 0.04
STAND_CONE_DIA_BOTTOM = 0.36
STAND_CONE_DIA_TOP = 0.04
STAND_CONE_Y0 = STAND_BASE_THICKNESS
STAND_CONE_Y1 = 0.97
STAND_CONE_SEGMENTS = 16
STAND_SPHERE_DIA = 0.06
STAND_SPHERE_CENTER_Y = 0.97


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def parse_out_dir():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out_dir = None
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_dir = argv[i + 1]
            i += 2
        else:
            i += 1
    if not out_dir:
        raise SystemExit("Missing required --out <dir> argument")
    return out_dir


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def get_or_create_greybox_material():
    mat = bpy.data.materials.get(MATERIAL_NAME)
    if mat is None:
        mat = bpy.data.materials.new(MATERIAL_NAME)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = MATERIAL_COLOR
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = MATERIAL_ROUGHNESS
    return mat


# ---------------------------------------------------------------------------
# Box-building primitives
#
# Axis conversion: a point given in spec (Unity) coordinates is written into
# Blender as Blender X = -spec X, Blender Y = -spec Z, Blender Z = spec Y (up).
# Combined with bake_space_transform=True + axis_forward='-Z' on export, the
# imported Unity mesh lands with X = spec X, Y = spec Y, Z = spec Z directly,
# transform identity.
#
# CORRECTION (pass 2, 2026-09-23): Documentation/EXPORT_CONTRACT.md's axis
# table says spec X maps straight to Blender X, with no flip. That was only
# ever checked against LAB_ENV_Wall_A_01, whose X bounds are symmetric
# (-1..1) -- a sign error on X is invisible on a symmetric box. Building the
# first asymmetric-X module (LAB_ENV_Wall_Corner_01, X 0..0.2) and live-
# reading its Unity bounds exposed it: the exporter/importer pair also
# mirrors X, not just Y/Z. Pre-negating spec X here cancels that. The
# contract doc's table is wrong on this one row -- flag it, don't just trust it.
# ---------------------------------------------------------------------------

def add_box_geometry(bm, x_min, x_max, y_min, y_max, z_min, z_max):
    """Add one axis-aligned box (spec-space bounds) into an existing bmesh."""
    size_x = x_max - x_min
    size_y = y_max - y_min  # spec Y (up) -> Blender Z
    size_z = z_max - z_min  # spec Z (forward) -> Blender Y, sign-flipped on export

    ret = bmesh.ops.create_cube(bm, size=1.0)
    verts = ret['verts']
    bmesh.ops.scale(bm, verts=verts, vec=(size_x, size_z, size_y))
    bmesh.ops.translate(
        bm, verts=verts,
        vec=(-(x_min + x_max) / 2.0, -(z_min + z_max) / 2.0, (y_min + y_max) / 2.0),
    )
    return verts


def add_recessed_wall_face(bm, bounds, rect_size, depth):
    """
    Add a wall box (spec-space bounds) whose inner face (z_min) has a rectangular
    recess, centered on X and Y, pushed in by `depth` (+spec Z, away from the room).

    Built as explicit verts/faces (not a boolean/inset op) so the topology is
    exact and predictable: outer box minus its inner face, plus a frame ring,
    pocket side walls and a recessed floor -- 14 planar quads, 28 tris.
    """
    x_min, x_max, y_min, y_max, z_min, z_max = bounds
    rect_w, rect_h = rect_size
    cx, cy = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0
    rx0, rx1 = cx - rect_w / 2.0, cx + rect_w / 2.0
    ry0, ry1 = cy - rect_h / 2.0, cy + rect_h / 2.0
    rz = z_min + depth

    vcache = {}

    def V(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in vcache:
            vcache[key] = bm.verts.new((-key[0], -key[2], key[1]))
        return vcache[key]

    A, B = V(x_min, y_min, z_min), V(x_max, y_min, z_min)
    C, D = V(x_max, y_max, z_min), V(x_min, y_max, z_min)
    E, F = V(x_min, y_min, z_max), V(x_max, y_min, z_max)
    G, H = V(x_max, y_max, z_max), V(x_min, y_max, z_max)
    I1, I2 = V(rx0, ry0, z_min), V(rx1, ry0, z_min)
    I3, I4 = V(rx1, ry1, z_min), V(rx0, ry1, z_min)
    J1, J2 = V(rx0, ry0, rz), V(rx1, ry0, rz)
    J3, J4 = V(rx1, ry1, rz), V(rx0, ry1, rz)

    for loop in (
        (A, B, I2, I1), (B, C, I3, I2), (C, D, I4, I3), (D, A, I1, I4),          # recess frame
        (I1, I2, J2, J1), (I2, I3, J3, J2), (I3, I4, J4, J3), (I4, I1, J1, J4),  # pocket walls
        (J1, J2, J3, J4),                                                        # recess floor
        (H, G, F, E),                                                            # outer face
        (A, D, H, E), (C, B, F, G), (B, A, E, F), (D, C, G, H),                  # sides
    ):
        bm.faces.new(loop)


def build_spec_object(name, add_fn):
    """
    General helper for non-box modules (cones, cylinders, spheres, n-gons --
    anything a box helper can't build). `add_fn(bm)` adds geometry into a
    fresh bmesh using any bmesh primitive/op or hand-placed bm.verts.new(...)
    call, with vertex coordinates authored directly in SPEC space (Unity
    axes: X width, Y up, Z depth) -- see build_cylinder_spec/build_sphere_spec
    below for the primitive builders used by the labyrinth props.

    This function then maps every vertex spec->Blender per
    EXPORT_CONTRACT.md (Blender X = -spec X, Y = -spec Z, Z = spec Y),
    recalculates normals and returns the finished object. Box modules keep
    using add_box_geometry, which bakes the same mapping into a cube
    scale+translate instead of a post-hoc vertex pass.
    """
    bm = bmesh.new()
    add_fn(bm)
    for v in bm.verts:
        sx, sy, sz = v.co
        v.co = (-sx, -sz, sy)
    return new_object_from_bmesh(bm, name)


def build_cylinder_spec(bm, axis, center, radius1, radius2, length, segments, angle_offset=0.0):
    """
    Add a capped cylinder/cone (spec space, before the spec->Blender mapping)
    whose axis of revolution is the given spec axis ('X' or 'Y'), centered at
    `center` (spec x, y, z) and spanning `length` along that axis. `angle_offset`
    (radians) rotates the cross-section about the axis before placement -- used
    to turn the stand's octagon so its flats face the cardinal spec axes
    instead of its vertices.

    bmesh.ops.create_cone always builds along its own local Z with the
    cross-section in local X/Y; this relabels those native axes onto whichever
    spec axis was asked for, then hands off to build_spec_object's mapping.
    """
    ret = bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segments,
        radius1=radius1, radius2=radius2, depth=length,
    )
    cx, cy, cz = center
    cos_a, sin_a = math.cos(angle_offset), math.sin(angle_offset)
    for v in ret['verts']:
        nx, ny, nz = v.co
        if angle_offset:
            nx, ny = nx * cos_a - ny * sin_a, nx * sin_a + ny * cos_a
        if axis == 'Y':
            v.co = (nx + cx, nz + cy, ny + cz)
        elif axis == 'X':
            v.co = (nz + cx, nx + cy, ny + cz)
        else:
            raise ValueError(f"build_cylinder_spec: unsupported axis {axis!r}")
    return ret['verts']


def build_sphere_spec(bm, center, radius, segments=16, ring_count=8):
    """Add a UV sphere (spec space, before the spec->Blender mapping) at `center`."""
    ret = bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=ring_count, radius=radius)
    cx, cy, cz = center
    for v in ret['verts']:
        nx, ny, nz = v.co
        v.co = (nx + cx, nz + cy, ny + cz)
    return ret['verts']


def apply_boolean_difference(obj, cutter_obj):
    """Cut `cutter_obj` out of `obj` with an EXACT boolean modifier, applied and
    baked into the mesh, then remove the (now-unused) cutter object."""
    mod = obj.modifiers.new(name="BooleanCut", type='BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter_obj
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter_obj, do_unlink=True)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def join_objects(objects, name):
    """Join `objects` into the first one (bpy.ops.object.join) and rename it."""
    for o in bpy.data.objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    objects[0].name = name
    return objects[0]


def load_maze_data():
    with open(MAZE_JSON_PATH, "r") as f:
        return json.load(f)


def new_object_from_bmesh(bm, name):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.materials.append(get_or_create_greybox_material())
    return obj


# ---------------------------------------------------------------------------
# Module registry -- name -> builder()
#
# Bounds functions derive box extents from the SIZE constants above per the
# pivot rules in Documentation/ENVIRONMENT_SPEC.md "Pivot and orientation rules".
# Adding a module later is a new SIZE constant + bounds function + registry
# entry, not new build/export code.
# ---------------------------------------------------------------------------

def bounds_wall(size):
    """Origin at floor, centered on width, on the inner face; body extends +Z."""
    w, h, d = size
    return (-w / 2.0, w / 2.0, 0.0, h, 0.0, d)


def bounds_corner(size):
    """Origin at floor at the inner corner point; body extends +X and +Z."""
    w, h, d = size
    return (0.0, w, 0.0, h, 0.0, d)


def bounds_floor(size):
    """Origin at the center of the top face; body extends downward."""
    w, th, d = size
    return (-w / 2.0, w / 2.0, -th, 0.0, -d / 2.0, d / 2.0)


def bounds_ceiling(size):
    """Origin at the center of the bottom face; body extends upward."""
    w, th, d = size
    return (-w / 2.0, w / 2.0, 0.0, th, -d / 2.0, d / 2.0)


def bounds_pillar(size):
    """Origin at floor, centered on the footprint."""
    w, h, d = size
    return (-w / 2.0, w / 2.0, 0.0, h, -d / 2.0, d / 2.0)


def bounds_trim(size):
    """Origin at floor, centered on width, on the inner face."""
    w, h, d = size
    return (-w / 2.0, w / 2.0, 0.0, h, 0.0, d)


def bounds_door_parts(size):
    """Two jambs (full height) + a header closing the top of the opening."""
    w, h, d = size
    jamb_w = (w - DOORWAY_WIDTH) / 2.0
    return [
        (-w / 2.0, -w / 2.0 + jamb_w, 0.0, h, 0.0, d),                             # left jamb
        (w / 2.0 - jamb_w, w / 2.0, 0.0, h, 0.0, d),                               # right jamb
        (-DOORWAY_WIDTH / 2.0, DOORWAY_WIDTH / 2.0, DOORWAY_HEIGHT, h, 0.0, d),    # header
    ]


def build_box_module(name, size, bounds_fn):
    def builder():
        bm = bmesh.new()
        add_box_geometry(bm, *bounds_fn(size))
        return new_object_from_bmesh(bm, name)
    return builder


def build_multi_box_module(name, size, bounds_list_fn):
    def builder():
        bm = bmesh.new()
        for bounds in bounds_list_fn(size):
            add_box_geometry(bm, *bounds)
        return new_object_from_bmesh(bm, name)
    return builder


def build_wall_panel():
    bm = bmesh.new()
    add_recessed_wall_face(bm, bounds_wall(WALL_PANEL_SIZE), PANEL_RECESS_RECT, PANEL_RECESS_DEPTH)
    return new_object_from_bmesh(bm, "LAB_ENV_Wall_Panel_01")


def build_labyrinth_panel():
    """
    LAB_PROP_LabyrinthPanel_01 -- HERO_SPEC.md section 8. Origin = pivot =
    underside centre of the base plate. Base plate + outer rim + inner maze
    walls are all boxes, merged into one bmesh via add_box_geometry (already
    Blender-space, mapping baked in). The round goal hole is not a box, so it
    is cut with an EXACT boolean against a cylinder built via build_spec_object.
    """
    maze = load_maze_data()
    interior = maze["I"]
    wall_height = maze["H"]
    goal_cx, goal_cz = maze["goal"]["c"]
    goal_radius = maze["goal"]["d"] / 2.0

    bm = bmesh.new()
    add_box_geometry(bm, -PANEL_HALF_XZ, PANEL_HALF_XZ, 0.0, PANEL_PLATE_THICKNESS,
                      -PANEL_HALF_XZ, PANEL_HALF_XZ)

    rim_y0, rim_y1 = PANEL_PLATE_THICKNESS, PANEL_RIM_TOP_Y
    add_box_geometry(bm, -PANEL_HALF_XZ, PANEL_HALF_XZ, rim_y0, rim_y1, interior, PANEL_HALF_XZ)     # +Z rail
    add_box_geometry(bm, -PANEL_HALF_XZ, PANEL_HALF_XZ, rim_y0, rim_y1, -PANEL_HALF_XZ, -interior)   # -Z rail
    add_box_geometry(bm, interior, PANEL_HALF_XZ, rim_y0, rim_y1, -interior, interior)               # +X rail
    add_box_geometry(bm, -PANEL_HALF_XZ, -interior, rim_y0, rim_y1, -interior, interior)             # -X rail
    assert math.isclose(PANEL_HALF_XZ - interior, PANEL_RIM_THICKNESS, abs_tol=1e-9), \
        "rim thickness drifted from the JSON interior"

    wall_y0, wall_y1 = PANEL_PLATE_THICKNESS, PANEL_PLATE_THICKNESS + wall_height
    for x0, x1, z0, z1 in maze["walls"].values():
        add_box_geometry(bm, x0, x1, wall_y0, wall_y1, z0, z1)

    panel_obj = new_object_from_bmesh(bm, "LAB_PROP_LabyrinthPanel_01")

    cutter_y0 = -PANEL_GOAL_CUTTER_MARGIN
    cutter_y1 = PANEL_PLATE_THICKNESS + PANEL_GOAL_CUTTER_MARGIN

    def add_cutter(cbm):
        build_cylinder_spec(
            cbm, axis='Y', center=(goal_cx, (cutter_y0 + cutter_y1) / 2.0, goal_cz),
            radius1=goal_radius, radius2=goal_radius, length=cutter_y1 - cutter_y0,
            segments=PANEL_GOAL_SEGMENTS,
        )

    cutter_obj = build_spec_object("_GoalHoleCutter", add_cutter)
    apply_boolean_difference(panel_obj, cutter_obj)
    return panel_obj


def build_labyrinth_handle():
    """
    LAB_PROP_LabyrinthPanel_Handle_01 -- origin also at the panel pivot, so it
    sits at identity under the same parent as the panel. The bar is a cylinder
    (build_spec_object); the two brackets joining it to the rim are boxes,
    built separately with add_box_geometry and then joined into one mesh.
    """
    bar_radius = HANDLE_BAR_DIA / 2.0

    def add_bar(bbm):
        build_cylinder_spec(
            bbm, axis='X', center=HANDLE_BAR_CENTER,
            radius1=bar_radius, radius2=bar_radius, length=HANDLE_BAR_LENGTH,
            segments=HANDLE_BAR_SEGMENTS,
        )

    bar_obj = build_spec_object("_HandleBar", add_bar)

    bm = bmesh.new()
    bh = HANDLE_BRACKET_SIZE / 2.0
    bar_cx, bar_cy, bar_cz = HANDLE_BAR_CENTER
    y0, y1 = bar_cy - bh, bar_cy + bh
    z0, z1 = -PANEL_HALF_XZ, bar_cz  # rim's outer face to the bar centre
    for bx in HANDLE_BRACKET_X:
        add_box_geometry(bm, bx - bh, bx + bh, y0, y1, z0, z1)
    brackets_obj = new_object_from_bmesh(bm, "_HandleBrackets")

    return join_objects([bar_obj, brackets_obj], "LAB_PROP_LabyrinthPanel_Handle_01")


def build_labyrinth_stand():
    """
    LAB_PROP_LabyrinthStand_01 -- origin at floor centre. Octagon base +
    tapered cone body + joint sphere, all non-box primitives built in spec
    space and merged into one object via build_spec_object.
    """
    base_apothem = STAND_BASE_ACROSS_FLATS / 2.0
    base_radius = base_apothem / math.cos(math.radians(22.5))
    cone_r0, cone_r1 = STAND_CONE_DIA_BOTTOM / 2.0, STAND_CONE_DIA_TOP / 2.0
    sphere_radius = STAND_SPHERE_DIA / 2.0

    def add_geo(bm):
        build_cylinder_spec(
            bm, axis='Y', center=(0.0, STAND_BASE_THICKNESS / 2.0, 0.0),
            radius1=base_radius, radius2=base_radius, length=STAND_BASE_THICKNESS,
            segments=8, angle_offset=math.radians(22.5),  # flats on the axes, not the verts
        )
        build_cylinder_spec(
            bm, axis='Y', center=(0.0, (STAND_CONE_Y0 + STAND_CONE_Y1) / 2.0, 0.0),
            radius1=cone_r0, radius2=cone_r1, length=STAND_CONE_Y1 - STAND_CONE_Y0,
            segments=STAND_CONE_SEGMENTS,
        )
        build_sphere_spec(bm, center=(0.0, STAND_SPHERE_CENTER_Y, 0.0), radius=sphere_radius)

    return build_spec_object("LAB_PROP_LabyrinthStand_01", add_geo)


MODULES = {
    "LAB_ENV_Wall_A_01": build_box_module("LAB_ENV_Wall_A_01", WALL_A_SIZE, bounds_wall),
    "LAB_ENV_Wall_Panel_01": build_wall_panel,
    "LAB_ENV_Wall_Corner_01": build_box_module("LAB_ENV_Wall_Corner_01", WALL_CORNER_SIZE, bounds_corner),
    "LAB_ENV_Wall_Door_01": build_multi_box_module("LAB_ENV_Wall_Door_01", WALL_DOOR_SIZE, bounds_door_parts),
    "LAB_ENV_Wall_Corridor_01": build_box_module("LAB_ENV_Wall_Corridor_01", WALL_CORRIDOR_SIZE, bounds_wall),
    "LAB_ENV_Floor_A_01": build_box_module("LAB_ENV_Floor_A_01", FLOOR_A_SIZE, bounds_floor),
    "LAB_ENV_Ceiling_A_01": build_box_module("LAB_ENV_Ceiling_A_01", CEILING_A_SIZE, bounds_ceiling),
    "LAB_ENV_Pillar_A_01": build_box_module("LAB_ENV_Pillar_A_01", PILLAR_A_SIZE, bounds_pillar),
    "LAB_ENV_Trim_A_01": build_box_module("LAB_ENV_Trim_A_01", TRIM_A_SIZE, bounds_trim),
    "LAB_PROP_LabyrinthPanel_01": build_labyrinth_panel,
    "LAB_PROP_LabyrinthPanel_Handle_01": build_labyrinth_handle,
    "LAB_PROP_LabyrinthStand_01": build_labyrinth_stand,
}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_fbx(obj, export_dir, filename):
    os.makedirs(export_dir, exist_ok=True)
    for o in bpy.data.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    filepath = os.path.join(export_dir, filename)
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        check_existing=False,
        use_selection=True,
        object_types={'MESH'},
        global_scale=1.0,
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_NONE',
        use_space_transform=True,
        bake_space_transform=True,
        mesh_smooth_type='FACE',
        axis_forward='-Z',
        axis_up='Y',
    )
    return filepath


def main():
    out_dir = parse_out_dir()
    clear_scene()

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0

    objects = []
    for name, builder in MODULES.items():
        obj = builder()
        # Boxes are authored directly in world space (object transform never
        # touched), so this is already identity; assert it rather than call
        # transform_apply, since there is nothing to bake.
        assert tuple(obj.location) == (0.0, 0.0, 0.0), name
        assert tuple(obj.rotation_euler) == (0.0, 0.0, 0.0), name
        assert tuple(obj.scale) == (1.0, 1.0, 1.0), name
        objects.append(obj)

    os.makedirs(out_dir, exist_ok=True)
    blend_path = os.path.join(out_dir, BLEND_FILENAME)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[env_kit_generator] saved blend: {blend_path}")

    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        fbx_path = export_fbx(obj, EXPORT_DIR, f"{obj.name}.fbx")
        print(f"[env_kit_generator] exported fbx: {fbx_path}")
        print(f"[env_kit_generator] {obj.name}: "
              f"{len(mesh.vertices)} verts, {len(mesh.loop_triangles)} tris")


if __name__ == "__main__":
    main()
