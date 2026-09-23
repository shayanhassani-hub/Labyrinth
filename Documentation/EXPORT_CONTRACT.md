# Export Contract — Blender → Unity

Verified 2026-09-23 with `LAB_ENV_Wall_A_01` (Blender 5.2.2 LTS → Unity 6000.3.24f1).
These settings are the result of a live import check, not documentation reading. Do not
change them without re-verifying mesh bounds and transform in the Editor.

## Units and scale

- 1 Blender unit = 1 Unity unit = **1 meter**. Blender scene unit scale 1.0, unit system Metric.
- Meshes are authored at final real-world size. No scaling in Unity, ever.
- A correctly imported asset shows **position (0,0,0), rotation (0,0,0), scale (1,1,1)** on the
  root of the instantiated prefab, and mesh bounds equal to the spec dimensions.

## Axis conversion (the part that bites)

Blender is Z-up / -Y-forward; Unity is Y-up / +Z-forward. Two things must line up:

1. **Author vertices with a pre-negated depth axis.** In the generator, a point given in
   spec (Unity) coordinates is written into Blender as:

   | Spec (Unity) | Blender |
   |---|---|
   | X | X |
   | Y (up) | Z |
   | Z (depth) | **−Y** |

2. **Bake the conversion into the mesh on export**, so nothing lands on the FBX root node.

Without step 2 the Z-up→Y-up rotation and the cm/m scale end up on the root node and Unity
imports the asset with rotation (270, 0, 0) and scale (100, 100, 100). Without step 1 the
depth axis is mirrored. Both are wrong; both are silent.

## FBX export settings (verified)

```python
bpy.ops.export_scene.fbx(
    filepath=out_path,
    use_selection=True,
    apply_unit_scale=True,
    global_scale=1.0,
    apply_scale_options='FBX_SCALE_NONE',
    bake_space_transform=True,      # critical — bakes axis conversion into the mesh
    axis_forward='-Z',
    axis_up='Y',
    object_types={'MESH'},
    use_mesh_modifiers=True,
    mesh_smooth_type='FACE',
    use_tspace=True,                # tangents for normal maps later
    add_leaf_bones=False,
    bake_anim=False,
)
```

Before exporting: apply all transforms on the object (`location`, `rotation`, `scale`), so the
object transform in Blender is identity and the pivot is where the spec says it is.

## Unity importer settings (verified)

Model tab:
- Scale Factor **1**
- Convert Units **on**
- Bake Axis Conversion **off** (the bake already happened in Blender; doing it twice is wrong)
- Import BlendShapes off, Import Visibility off, Import Cameras off, Import Lights off
- Mesh Compression Off, **Read/Write off**, Optimize Mesh on
- Generate Colliders off (colliders are added per-instance in the scene)

Rig tab: Animation Type **None**.
Animation tab: Import Animation **off**.
Materials tab: Material Creation Mode **None** — materials are assigned in Unity, never
imported from the FBX.

Normals: Import; Tangents: Calculate Mitchell (default) unless the asset ships tangents.

## Pivot rules

Authoritative list lives in `ENVIRONMENT_SPEC.md` → "Pivot and orientation rules". Summary:
wall modules have their origin at floor level, centered on the module width, **on the inner
face**, with the body extending in +Z (away from the room interior).

## Wall placement yaw table

Because the wall body extends in +Z from the inner face, each wall of the room needs a
specific Y rotation so the body goes into the wall, not into the room:

| Wall | Faces the room toward | Y rotation |
|---|---|---|
| Back wall (−Z side, behind the player) | +Z | **180°** |
| Far wall (+Z side, facility door) | −Z | **0°** |
| Left wall (−X side) | +X | **270°** |
| Right wall (+X side) | −X | **90°** |

Panel origins sit on the interior line of the room: back wall z = −2.0, far wall z = +8.0,
left wall x = −4.0, right wall x = +4.0. Stacked panels repeat at y = 0 and y = 2.0.

## Verification checklist (run for every new module)

1. Import the FBX into `Assets/Environment/Kit/`.
2. Live-read the mesh bounds through the Editor and compare to the spec dimensions.
3. Confirm the imported root transform is identity (rotation 0, scale 1).
4. Confirm triangle count is within the greybox budget (~100 tris for a plain panel).
5. Place one instance with the yaw from the table above and confirm the body goes into the
   wall, not into the room.

## Known-good reference

`LAB_ENV_Wall_A_01` — 8 verts, 12 tris, material `M_Greybox`, Unity mesh bounds
(−1, 0, 0) … (1, 2, 0.2), transform identity. If a new module misbehaves, diff its export
call against this one.

## Git LFS

Binaries under `Assets/Environment/**` plus `*.blend` and `*.spp` go through Git LFS
(`.gitattributes`). `.meta` files are plain text and must be committed alongside every asset.
