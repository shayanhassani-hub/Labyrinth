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
| Player | spawns at the corridor end (−1, 0, 13.0) facing −Z (the gate); labyrinth operating position (0, 0, 0); eye height 1.36 |
| Labyrinth panel | 1.05 × 1.05, top at y = 1.075, center (0.03, 1.04, 1.23) — updated 2026-09-24 after owner's hand rescale, read live from renderer bounds |
| Corridor | 2.0 wide × 3.0 high × 5.8 long, beyond the far wall (+Z), centered on X = −1 |

## Protected free volumes (no geometry, no props)

| Volume | Extents |
|---|---|
| Drone flight (DroneBounds + 0.5 margin) | X −2.45 … +2.39, Y 1.19 … 3.48, Z 2.84 … 6.32 — updated 2026-09-24, DroneBounds rescaled by owner (Y re-read live a second time same session, Y range shrank further as the owner kept tuning) |
| Labyrinth | cylinder r = 1.24 around (0.03, ·, 1.23), y 0 … 2.5 — updated 2026-09-24, radius = panel XZ half-diagonal (renderer bounds) + 0.5 m margin |
| Player | labyrinth operating position: cylinder r = 1.0 around (0, ·, 0); spawn: r = 0.6 around (−1, ·, 13.0); both y 0 … 2.5 |

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
trim height 0.15 · Wall_Panel recess 1.6 × 1.6, depth 0.05, centered (0.2 border all round).

Wall height: 4.0, built as **two stacked 2.0 m Wall_A / Wall_Panel modules** (seam at
y = 2.0). Decided 2026-09-23; Wall_Corner and Wall_Door are authored at the full 4.0 m.

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

## Corridor (built 2026-09-23)

Interior x −2.0 … 0.0, y 0 … 3.0, z 8.2 … **14.0** (5.8 m long — see below). Walls are
`Wall_Corridor` (2.0 × 3.0 × 0.2) at x = −2.0 yaw 270 and x = 0.0 yaw 90, z centers
9.2 / 11.2 / 13.2, plus one end cap at (−1, 0, **14.0**) yaw 0. Floor and ceiling: 3 tiles
each at z centers 9, 11, 13. Overall extents X −2.2 … 0.2, Y −0.1 … 3.1, Z 8.0 … 14.2.

**Why 5.8 and not the 6.0 first specified.** Tiles are 2.0 m and cannot be part-placed, so
the corridor length has to resolve against both ends at once. The near end is fixed: floor
must start at z = 8.0 so it runs unbroken under the doorway, where the player walks through.
That puts the last tile's far edge at z = 14.0, so the end cap goes there — tiles meet its
inner face, side walls end flush with its outer face, nothing overhangs and no strip is left
open. Reaching a true 6.0 would mean either padding with tiles that hang 1.6 m into dead
space (visibly wrong from outside) or sliding the tiles to 8.2 … 14.2, which reopens the gap
at the threshold — the one place it would be walked over. 20 cm is the cheaper loss.

General rule this produced: a floor or ceiling run must reach where a wall body *starts*, and
both ends must be checked. Getting the near end right does not make the far end right.

## Greybox stage (pass 1)

- No textures. One grey material for everything; emissive strips come later.
- Geometry stays minimal: a plain wall panel should be under ~100 triangles.
- Goal: check scale, readability of the labyrinth, drone clearance and player comfort on Quest.

## Layout (first pass)

- Walls on all four sides, 2 panels high, with `Wall_Corner` at the four corners.
- **Facility door (Hero 03)** in the far wall (+Z) at **x = −1**, corridor behind it.
  The 8 m wall is 4 modules wide, so module centers fall at x = −3, −1, +1, +3 and no module
  is centered on x = 0. The door sits one grid cell left of center, balancing Hero 01's mass
  on the +X side. Decided 2026-09-23.
- **Heroes** (cradle, service arm, terminal, lever, gate, labyrinth stand): placement and design
  in `HERO_SPEC.md`, which supersedes the first-pass hero notes that were here.
- Pipes run along the ceiling edges and the upper wall band; light panels in the ceiling grid.
- **Trim** sits on the wall's inner face and protrudes 0.05 m into the room, so its yaw is the
  wall's yaw **+ 180°** (back 0°, far 180°, left 90°, right 270°). Placing trim with the wall's
  own yaw buries it inside the wall body — invisible, and it was built that way on 2026-09-23
  until the greybox builder corrected it on 2026-09-24.

## Rebuilding

The whole greybox (room + corridor) is rebuilt from one data table by
`Assets/Environment/Editor/GreyboxBuilder.cs` → menu **Tools → Labyrinth → Rebuild Greybox**.
It replaces kit instances only; lights and anything else under `ENV_Greybox` are left alone.
If a layout number changes here, change it in the builder's table too.

**Teleport floor** (`ENV_Greybox/NAV_TeleportFloor`, added 2026-09-24): one TeleportationArea with two
BoxColliders, tops at y = 0 - room X −4 … 4, Z −2 … 8; corridor X −2 … 0, Z 8 … 14. The builder does NOT
generate it (it only replaces kit instances), so if the room or corridor extents change, update these
two colliders by hand. Walls have no colliders yet: the teleport ray and bullets pass through them.
