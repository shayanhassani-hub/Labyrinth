"""
Labyrinth VR -- modular environment kit generator.

Builds the greybox kit for the Industrial Robotics Research Facility from a
single parameter block below, copied from Documentation/ENVIRONMENT_SPEC.md.
If a value changes in the spec, update the block here and regenerate --
do not hand-edit the resulting meshes.

Pass 1 implements Wall_A only; the rest of the module sizes are declared here
so later passes read the same spec values.

Run headless:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
        -P Tools/Blender/env_kit_generator.py -- --out "D:/AI_Labyrinth/Blender/Generated"

Saves LAB_ENV_kit.blend to --out and exports LAB_ENV_Wall_A_01.fbx to
D:/AI_Labyrinth/Blender/Export. Does not touch the Unity project's Assets folder.
"""

import bpy
import bmesh
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

# Module sizes (X, Y, Z) -- only Wall_A is built in this pass
WALL_A_SIZE = (2.0, 2.0, WALL_THICKNESS)
WALL_PANEL_SIZE = (2.0, 2.0, WALL_THICKNESS)
WALL_CORNER_SIZE = (WALL_THICKNESS, 4.0, WALL_THICKNESS)
WALL_DOOR_SIZE = (2.0, 4.0, WALL_THICKNESS)
FLOOR_A_SIZE = (2.0, 0.1, 2.0)
CEILING_A_SIZE = (2.0, 0.1, 2.0)
PILLAR_A_SIZE = (0.4, 4.0, 0.4)
TRIM_A_SIZE = (2.0, TRIM_HEIGHT, 0.05)

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
# Helpers
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


def create_box_mesh(name, x_min, x_max, y_min, y_max, z_min, z_max):
    """
    Build a box directly from spec-space bounds (X width, Y up, Z forward).

    Vertices are authored so that Blender X = spec X, Blender Y = -spec Z,
    Blender Z = spec Y (up), then exported with bake_space_transform=True,
    axis_forward='-Z', axis_up='Y'. Empirically (verified by round-tripping
    a test box through this exact export+import), that exporter/importer
    pair bakes a -90 deg rotation about X into the mesh data, which maps
    Blender Y -> Unity -Z. Pre-negating spec Z here cancels that flip, so
    the imported Unity mesh ends up with X = spec X, Y = spec Y (up),
    Z = spec Z (forward) directly, rotation (0,0,0), scale (1,1,1).
    """
    size_x = x_max - x_min
    size_y = y_max - y_min  # spec Y (up) -> Blender Z
    size_z = z_max - z_min  # spec Z (forward) -> Blender Y, sign-flipped on export

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(size_x, size_z, size_y))
    bmesh.ops.translate(
        bm,
        verts=bm.verts,
        vec=((x_min + x_max) / 2.0, -(z_min + z_max) / 2.0, (y_min + y_max) / 2.0),
    )

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    return obj


def build_wall_a():
    half_w = WALL_A_SIZE[0] / 2.0
    obj = create_box_mesh(
        "LAB_ENV_Wall_A_01",
        -half_w, half_w,        # spec X: centered on width
        0.0, WALL_A_SIZE[1],    # spec Y: floor level -> top
        0.0, WALL_A_SIZE[2],    # spec Z: inner face -> body extends +Z
    )
    obj.data.materials.append(get_or_create_greybox_material())
    return obj


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

    wall_a = build_wall_a()

    os.makedirs(out_dir, exist_ok=True)
    blend_path = os.path.join(out_dir, BLEND_FILENAME)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    fbx_path = export_fbx(wall_a, EXPORT_DIR, "LAB_ENV_Wall_A_01.fbx")

    mesh = wall_a.data
    mesh.calc_loop_triangles()
    print(f"[env_kit_generator] saved blend: {blend_path}")
    print(f"[env_kit_generator] exported fbx: {fbx_path}")
    print(f"[env_kit_generator] {wall_a.name}: "
          f"{len(mesh.vertices)} verts, {len(mesh.loop_triangles)} tris")


if __name__ == "__main__":
    main()
