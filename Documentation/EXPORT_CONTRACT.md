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
them is a real step, not something the importer does on its own. The 2026-09-23 correction
was not persisted on 7 of the 9 kit modules — they still had Import Animation on and Material
Creation Mode "Import via Material Description". Settings re-applied, saved to the `.meta`
files and verified live on 2026-09-26; confirm with `git diff` on the `.meta` after any importer change.)
Animation tab: Import Animation **off**.
Materials tab: Material Creation Mode **None** — materials are assigned in Unity, never
imported from the FBX.

Normals: Import; Tangents: Calculate Mitchell (default) unless the asset ships tangents.

## UVs (added 2026-09-26)

Every mesh gets exactly one UV map, `UVMap`, from `apply_box_uv(obj)` in
`Tools/Blender/env_kit_generator.py`. It runs inside `export_fbx`, so kit modules, labyrinth
props and future heroes all get it without extra calls. No lightmap UV2: Unity generates that at
bake time (the importer's Generate Lightmap UVs stays off until a bake needs it).

- **Box projection per face**, picked by the dominant axis of the face normal, in spec axes:
  ±X faces → U = ±Z, V = Y · ±Z faces → U = ∓X, V = Y · ±Y faces → U = X, V = ±Z.
- **World scale: 1 UV unit = 1 m**, so tiling materials line up across modules.
- **V = up (spec +Y) on every vertical face**, so a texture never lies sideways.
- **No mirrored faces.** The sign of U (V on horizontal faces) follows the normal, so every face
  reads correctly from outside. Verified live 2026-09-26: all triangles of all 12 assets have the
  same UV winding. The authoring mapping mirrors coordinates but only yaws the model 180° in
  appearance, and Unity's X mirror only touches positions, so UVs read the same in Blender and Unity.
- Seams sit on every edge where the dominant axis changes (all box edges; every few segments on
  cylinders, cones and spheres). Adding UVs did not change any Unity vertex or triangle count.

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

## Non-box geometry rules (learned 2026-09-25, Labyrinth v2)

Everything that isn't a plain box goes through `build_spec_object` (cylinders, cones, spheres,
cutters). Three rules, each from a real bug:

1. **Mirror ⇒ refresh normals.** The spec→Blender mapping is a mirror. After it, call
   `bm.normal_update()` *before* `recalc_face_normals`, or the mesh stays inside-out (the stand's
   cone was, and so was the goal-hole cutter). `build_spec_object` does this; don't bypass it.
2. **Booleans only on one closed mesh, before joining.** Cut holes from a single closed part
   (the plate), *then* join the rest. Boxes that merely touch are not a closed volume: the EXACT
   solver silently discards faces (the first panel lost most of its rim and walls).
3. **Numbers alone don't prove a shape.** Bounds stay correct when faces go missing inside, and a
   budget ("≤ 1500 tris") passes a broken mesh. Every generated asset is verified with:
   - an **expected triangle range**, not only a ceiling;
   - an **inward-face count** per part (face normal vs. part centre) — must be 0;
   - a **Workbench render** (top and/or 3/4 view) that a human looks at before commit.

## Known-good reference — greybox kit, verified 2026-09-23

All bounds live-read from the Editor, all transforms identity, all material `M_Greybox`.

| Module | Blender verts | Unity verts | Tris | Unity bounds (min … max) |
|---|---|---|---|---|
| LAB_ENV_Wall_A_01 | 8 | 24 | 12 | (−1, 0, 0) … (1, 2, 0.2) |
| LAB_ENV_Wall_Panel_01 | 16 | 48 | 28 | (−1, 0, 0) … (1, 2, 0.2) |
| LAB_ENV_Wall_Corner_01 | 8 | 24 | 12 | (0, 0, 0) … (0.2, 4, 0.2) |
| LAB_ENV_Wall_Door_01 | 24 | 72 | 36 | (−1, 0, 0) … (1, 4, 0.2) |
| LAB_ENV_Wall_Corridor_01 | 8 | 24 | 12 | (−1, 0, 0) … (1, 3, 0.2) |
| LAB_ENV_Floor_A_01 | 8 | 24 | 12 | (−1, −0.1, −1) … (1, 0, 1) |
| LAB_ENV_Ceiling_A_01 | 8 | 24 | 12 | (−1, 0, −1) … (1, 0.1, 1) |
| LAB_ENV_Pillar_A_01 | 8 | 24 | 12 | (−0.2, 0, −0.2) … (0.2, 4, 0.2) |
| LAB_ENV_Trim_A_01 | 8 | 24 | 12 | (−1, 0, 0) … (1, 0.15, 0.05) |

If a new module misbehaves, diff its registry entry against these.

## Git LFS

Binaries under `Assets/Environment/**` plus `*.blend` and `*.spp` go through Git LFS
(`.gitattributes`). `.meta` files are plain text and must be committed alongside every asset.
