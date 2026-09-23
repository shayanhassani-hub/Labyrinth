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

1. **Author vertices with pre-negated X and depth axes.** In the generator, a point given
   in spec (Unity) coordinates is written into Blender as:

   | Spec (Unity) | Blender |
   |---|---|
   | X | **−X** |
   | Y (up) | Z |
   | Z (depth) | **−Y** |

2. **Bake the conversion into the mesh on export**, so nothing lands on the FBX root node.

Without step 2 the Z-up→Y-up rotation and the cm/m scale end up on the root node and Unity
imports the asset with rotation (270, 0, 0) and scale (100, 100, 100). Without step 1 the
geometry is mirrored. Both are wrong; both are silent.

**Why X is negated.** Blender is right-handed, Unity is left-handed. The conversion cannot
be a pure rotation — one axis must be mirrored, and Unity mirrors **X** on FBX import
(flipping triangle winding to compensate, which is why imported meshes are not inside-out).
The exporter's `-90°` rotation about X gives Unity = (Bx, Bz, −By); Unity's own mirror makes
it (−Bx, Bz, −By). Pre-negating spec X in the authoring cancels it.

**This row was wrong until 2026-09-23 (pass 2).** The original table said spec X → Blender X.
It was only ever checked against `LAB_ENV_Wall_A_01`, whose X bounds are −1 … +1 —
**symmetric, so a sign error on X is invisible**. `LAB_ENV_Wall_Corner_01` (X 0 … 0.2) is the
first asymmetric-X module and imported mirrored, (−0.2, 0, 0) … (0, 4, 0.2). Lesson: **every
verification batch must include at least one module that is asymmetric on each axis**, or the
check proves nothing.

**Side effect:** because authoring pre-negates X, the geometry inside `LAB_ENV_kit.blend` is
mirrored in X relative to the spec. That is harmless for procedural work — the generator is
the source of truth, not the .blend — but do not hand-model in that file expecting Blender X
to read as spec X.

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

Rig tab: Animation Type **None**. (Checked live 2026-09-23: Wall_A had imported as Generic
with BlendShapes/Visibility/Cameras/Lights on — the defaults, not these settings. Applying
them is a real step, not something the importer does on its own. All 8 modules corrected.)
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
2. Apply the importer settings above — they are NOT the defaults.
3. Live-read the mesh bounds through the Editor and compare to the spec dimensions.
4. Confirm the imported root transform is identity (rotation 0, scale 1).
5. Confirm triangle count is within the greybox budget (~100 tris for a plain panel).
6. Confirm normals: the module must not read inside-out in the Scene view. The authoring
   mirror reverses winding, so `recalc_face_normals` must run before export.
7. Place one instance with the yaw from the table above and confirm the body goes into the
   wall, not into the room.

A batch verification is only meaningful if it contains a module that is asymmetric on X, on
Y and on Z. Symmetric boxes hide sign errors — see the axis-conversion note above.

## Known-good reference — greybox kit, verified 2026-09-23

All bounds live-read from the Editor, all transforms identity, all material `M_Greybox`.

| Module | Verts | Tris | Unity bounds (min … max) |
|---|---|---|---|
| LAB_ENV_Wall_A_01 | 8 | 12 | (−1, 0, 0) … (1, 2, 0.2) |
| LAB_ENV_Wall_Panel_01 | 16 | 28 | (−1, 0, 0) … (1, 2, 0.2) |
| LAB_ENV_Wall_Corner_01 | 8 | 12 | (0, 0, 0) … (0.2, 4, 0.2) |
| LAB_ENV_Wall_Door_01 | 24 | 36 | (−1, 0, 0) … (1, 4, 0.2) |
| LAB_ENV_Floor_A_01 | 8 | 12 | (−1, −0.1, −1) … (1, 0, 1) |
| LAB_ENV_Ceiling_A_01 | 8 | 12 | (−1, 0, −1) … (1, 0.1, 1) |
| LAB_ENV_Pillar_A_01 | 8 | 12 | (−0.2, 0, −0.2) … (0.2, 4, 0.2) |
| LAB_ENV_Trim_A_01 | 8 | 12 | (−1, 0, 0) … (1, 0.15, 0.05) |

If a new module misbehaves, diff its registry entry against these.

## Git LFS

Binaries under `Assets/Environment/**` plus `*.blend` and `*.spp` go through Git LFS
(`.gitattributes`). `.meta` files are plain text and must be committed alongside every asset.
