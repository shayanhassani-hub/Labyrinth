# Environment Spec — Industrial Robotics Research Facility

Approved 2026-09-23. All values in meters, 1 Unity unit = 1 m. The Blender generator in
`Tools/Blender/` must read its parameters from this file's values; if a value changes here,
regenerate the kit rather than editing meshes by hand.

## Room (interior dimensions)

| Item | Value |
|---|---|
| Footprint | 8.0 (X) × 10.0 (Z) |
| Interior extents | X −4.0 … +4.0, Z −2.0 … +8.0 |
| Floor level | y = 0 |
| Ceiling height | 4.0 |
| Grid | 2.0 m modules → 4 × 5 modules, walls 2 panels high |
| Player | at (0, 0, 0), eye height 1.36 |
| Labyrinth panel | 1.4 × 1.4, top at y ≈ 1.1, center (0.2, 1.05, 1.4) |
| Corridor | 2.0 wide × 3.0 high × 6.0 long, beyond the far wall (+Z), centered on X = 0 |

## Protected free volumes (no geometry, no props)

| Volume | Extents |
|---|---|
| Drone flight (DroneBounds + 0.5 margin) | X −2.96 … +2.93, Y 0.77 … 3.80, Z 2.69 … 7.04 |
| Labyrinth | cylinder r = 1.5 around (0.2, ·, 1.4), y 0 … 2.5 |
| Player | cylinder r = 1.0 around (0, ·, 0), y 0 … 2.5 |

## Module dimensions

| Module | Size (X × Y × Z) | Notes |
|---|---|---|
| Wall_A | 2.0 × 2.0 × 0.2 | base wall panel, stacks 2 high |
| Wall_Panel | 2.0 × 2.0 × 0.2 | variant with recessed panel detail |
| Wall_Corner | 0.2 × 4.0 × 0.2 | fills the corner column |
| Wall_Door | 2.0 × 4.0 × 0.2 | opening 1.6 wide × 2.4 high, centered on X |
| Floor_A | 2.0 × 0.1 × 2.0 | top face at y = 0 |
| Ceiling_A | 2.0 × 0.1 × 2.0 | bottom face at ceiling height |
| Pillar_A | 0.4 × 4.0 × 0.4 | free-standing or against a wall |
| Trim_A | 2.0 × 0.15 × 0.05 | floor/ceiling edge trim |
| Pipe_Straight | length 2.0, Ø 0.16 and 0.25 | along +X |
| Pipe_Corner | 90°, radius 0.3 | same two diameters |
| Pipe_Junction | T-piece | same two diameters |

Other constants: wall thickness 0.2 · doorway 1.6 × 2.4 · pipe clearance from wall face 0.35 ·
trim height 0.15.

## Pivot and orientation rules

- Unity convention: +Y up, +Z forward, meters, scale 1,1,1. No rotation baked into the mesh.
- **Wall modules**: origin at floor level, centered on the module width, on the **inner face**.
  The wall body extends in +Z (away from the room interior).
- **Wall_Corner**: origin at floor level, at the inner corner point.
- **Floor_A**: origin at the center of the top face; body extends downward.
- **Ceiling_A**: origin at the center of the bottom face; body extends upward.
- **Pillar_A, Trim_A**: origin at floor level, centered on the footprint (trim: inner face).
- **Pipes**: origin at the start end, center of the cross-section, axis along +X.

## Naming

`LAB_ENV_<Module>_<Variant>_<NN>`, e.g. `LAB_ENV_Wall_A_01`, `LAB_ENV_Pipe_Straight_01`.
The same name is used for the Blender object, the FBX file and the Unity asset.

## Greybox stage (pass 1)

- No textures. One grey material for everything; emissive strips come later.
- Geometry stays minimal: a plain wall panel should be under ~100 triangles.
- Goal: check scale, readability of the labyrinth, drone clearance and player comfort on Quest.

## Layout (first pass)

- Walls on all four sides, 2 panels high, with `Wall_Corner` at the four corners.
- **Facility door (Hero 03)** in the far wall (+Z), centered on X, corridor behind it.
- **Hero 01, large machine / drone dock gantry**: right side (+X), Z 5.5 … 7.5, reaching over
  from the wall but staying outside the drone volume.
- **Hero 02, control terminal**: left wall (−X), near Z ≈ −1, facing the player.
- Pipes run along the ceiling edges and the upper wall band; light panels in the ceiling grid.
