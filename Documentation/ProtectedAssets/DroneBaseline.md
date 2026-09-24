# Drone Baseline (locked asset)

Purpose: a verified record of the locked drone, so any change to it can be detected.
Every value below must come from a LIVE Editor read, not from YAML parsing.
Status: FILLED — production step 2.

- Verified on: 2026-09-24 (transforms/scales/bounds refresh after owner's hand rescale + Quest test;
  earlier sections below — Assets, Material properties, hierarchy — last verified 2026-09-22 and
  re-confirmed unchanged this pass except where noted). Read live twice this session, several
  minutes apart; the owner was still actively tuning DroneBounds and VFX_RingSparks between the two
  reads, so the values below are from the **second** read.
- Verified at Git commit: 23b78f056c4b2b22bde336d2f8474829ebc91e25
- Unity: 6000.3.24f1
- Read from: BasicScene (open, isDirty=false at read time — not saved, no changes made)

## Assets
| Item | Path | GUID |
|---|---|---|
| Model | Assets/Drone_Asset/drone_low.fbx | a72a4f49a01c2a54d8db5286e8f88c17 |
| Material | Assets/Drone_Asset/M_Drone.mat | 054186815ab8661469b902129eea4eac |
| Shader Graph | Assets/Materials/Drone_Mat_V2/SG_DroneOptimized.shadergraph | 922cf7110072ad84faa6dc2f9f60f082 |
| Textures used by M_Drone | _BaseMap: Assets/Materials/Drone_Mat_V4/drone_low_M_Drone_AlbedoTransparency.png · _MaskMap: Assets/Materials/Drone_Mat_V4/drone_low_M_Drone_MetallicSmoothness.png · _NormalMap: Assets/Materials/Drone_Mat_V3/drone_low_M_Drone_Normal.png · _EmissiveMap: Assets/Materials/Drone_Mat_V4/drone_low_M_Drone_Emission.png · _Ring_Flash_Mask: Assets/Materials/Drone_Mat_V2/Ring_Flash_Mask.png | d24c9a0e2fdc0c0469b69ec740c8a479 · 22c0dc83e2b3f5c449b84feef6e10483 · e5b91aa041c3efc469d52cb8b8ec71df · c2628b6dac36f6a4c9a18d1f10ae2dc7 · d6909fa5a61c493438090fff48a44088 |
| Projectile prefab | Assets/3D Models/Sphere.prefab | df2a75de699d8f44b9916e706d89bae6 |
| Other drone materials (hologram, scanner, pulse) | MAT_Hologram: Assets/Shaders/Holographic Mode/MAT_Hologram.mat (shader SH_Hologram) · MAT_FakeBloom: Assets/Shaders/Scanner Light/MAT_FakeBloom.mat (shader SG_FakeBloom) · MAT_DroneScanner: Assets/Shaders/Scanner Light/MAT_DroneScanner.mat (shader SG_DroneScanner) · MAT_PulseScanner: Assets/Shaders/Scanner Light/MAT_PulseScanner.mat (shader SG_PulseScanner) | 892e79f615230dc43857e6efd6976dad · aa3831f7bc426c44abb8b4ae547911b3 · e521ab1c30331c3418f515fe2c5634de · 3ce878953e4d1674e9cda503b49b80cf |

## Material properties (M_Drone)
Shader: `Shader Graphs/SG_DroneOptimized`, render queue -1, no enabled keywords.

| Property | Value |
|---|---|
| _Ring_Intensity | 0 |
| _Ring_Flash_Mask | Ring_Flash_Mask.png (see Assets table above) |
| _Ring_Flash_Color | [0.5773585, 0.008408133, 0, 0] |
| _BaseMap / _MaskMap / _NormalMap / _EmissiveMap | assigned, see Assets table above |
| _QueueOffset / _QueueControl | 0 / 0 |

## Scene object: BasicScene / DroneAI2
Hierarchy (names, active state, components):
```
DroneAI2 [active] (Transform, DroneHoverAIV2)
└── drone_low [active] (Transform, HologramToggle)
    ├── ArmLeft_low [active] (Transform, MeshFilter, MeshRenderer)
    ├── ArmRight_low [active] (Transform, MeshFilter, MeshRenderer)
    ├── Body_low [active] (Transform, MeshFilter, MeshRenderer)
    ├── Engine1_low [active] (Transform, MeshFilter, MeshRenderer)
    ├── Engine3_low [active] (Transform, MeshFilter, MeshRenderer)
    ├── Engine4_low [active] (Transform, MeshFilter, MeshRenderer)
    ├── Engline2_low [active] (Transform, MeshFilter, MeshRenderer)   -- note: source asset naming typo, not ours
    ├── Propellor1_low [active] (Transform, MeshFilter, MeshRenderer) -- no PropellerSpin attached
    ├── Propellor2_low [active] (Transform, MeshFilter, MeshRenderer) -- no PropellerSpin attached
    ├── Propellor3_low [active] (Transform, MeshFilter, MeshRenderer) -- no PropellerSpin attached
    ├── Propellor4_low [active] (Transform, MeshFilter, MeshRenderer) -- no PropellerSpin attached
    ├── Ring_low [active] (Transform, MeshFilter, MeshRenderer)
    │   └── VFX_RingSparks [active] (Transform, ParticleSystem, ParticleSystemRenderer)
    ├── Top_low [active] (Transform, MeshFilter, MeshRenderer)
    ├── ToShoot_low [active] (Transform, MeshFilter, MeshRenderer)
    │   └── Shoot Point [active] (Transform)
    └── ScannerGlow [INACTIVE] (Transform, MeshFilter, MeshRenderer)  -- material MAT_FakeBloom
```
`DroneBounds` (BoxCollider) and `Labyrinth Ball` are separate root-level scene objects referenced by
`DroneHoverAIV2`, not children of `DroneAI2`.

Important transforms (local position / rotation / scale) — **updated 2026-09-24, post-rescale**:
| Object | Position | Rotation (quaternion x,y,z,w) | Scale |
|---|---|---|---|
| DroneAI2 | (0, 2, 4.76) — unchanged | (0, 0, 0, 1) — identity, unchanged | (1, 1, 1) — unchanged |
| drone_low | (0, -0.228, 0) — was (0, 0, 0) | (0, -1, 0, 0.00023) — ≈180.03° about Y, unchanged | (0.59, 0.59, 0.59) — was (1, 1, 1) |
| ToShoot_low/Shoot Point | (0, -0.00813, 0) — unchanged | (0, 0, 0, 1) — identity | (1, 1, 1) |

World position, DroneAI2/drone_low/ToShoot_low/Shoot Point: **(0, 1.767203, 4.76)** — not previously
recorded (2026-09-22 baseline only had the local offset above; DroneAI2 world pos (0,2,4.76) confirmed
still inside DroneBounds' world bounds, see below).

VFX_RingSparks (`.../Ring_low/VFX_RingSparks`, ParticleSystem, main module) — re-verified live a second
time same session, value changed mid-session (owner actively tuning): scalingMode `Hierarchy`
(was briefly `Local` on the first read this session), startSize mode `TwoConstants`, constantMin
`0.02`, constantMax `0.05`.

## DroneHoverAIV2 on DroneAI2 (BasicScene)
Re-verified live 2026-09-24: every field below is **unchanged** from 2026-09-22, including the
object references (bounds, labyrinthBall, projectilePrefab, firePoint, droneRenderer, ringSparks).
| Field | Value |
|---|---|
| bounds | BoxCollider on `/DroneBounds` |
| labyrinthBall | GameObject `/Labyrinth Ball` |
| moveSpeed / reachThreshold | 1.5 / 0.1 |
| hoverAmplitude / hoverFrequency | 0.3 / 2 |
| rotationSpeed | 3 |
| projectilePrefab | Assets/3D Models/Sphere.prefab (guid df2a75de699d8f44b9916e706d89bae6) |
| firePoint | Transform `/DroneAI2/drone_low/ToShoot_low/Shoot Point` |
| shootInterval / projectileSpeed | 2 / 15 |
| droneRenderer | MeshRenderer on `/DroneAI2/drone_low/Ring_low` |
| ringSparks | ParticleSystem on `/DroneAI2/drone_low/Ring_low/VFX_RingSparks` |
| peakEmissionIntensity / flashDecaySpeed | 1 / 15 |

## DroneBounds, Labyrinth Panel, Labyrinth Ball, projectile — added 2026-09-24 (first live capture)
These were referenced from DroneHoverAIV2 in the 2026-09-22 pass but their own transforms/components
were not read live until now, after the owner's rescale.

**DroneBounds** (`/DroneBounds`, root-level, BoxCollider) — read live twice this session; the owner was
actively tuning it between the two reads (Y position/scale changed, X/Z unchanged), second read wins:
- Transform: local pos (-0.044537, 2.241, 4.4437), rot (0,0,0), scale (0.65, 1.004395, 1.632813)
  — Y pos was 2.277, Y scale was 1.068506 on the first read this session, both moved down
- BoxCollider: center (0.02289, 0.090929, 0.084183), size (5.915247, 1.282193, 1.52144) — unchanged
  by the Y transform tweak (BoxCollider values are local to DroneBounds, the transform scale/pos
  is what shifted the resulting world bounds)
- Resulting world bounds (raw, no margin): min (-1.952, 1.688, 3.339), max (1.893, 2.976, 5.823)
- With the +0.5 m margin used for the protected drone volume: min (-2.452, 1.188, 2.839),
  max (2.393, 3.476, 6.323)
- DroneAI2's world position (0, 2, 4.76) is inside the raw (un-margined) bounds — PASS.
- Old value: only the margined protected-volume row existed (ENVIRONMENT_SPEC.md, pre-rescale):
  X −2.96…+2.93, Y 0.77…3.80, Z 2.69…7.04. The local transform/BoxCollider numbers above were never
  recorded before this session, so no direct old→new comparison exists for them beyond the two live
  reads noted above.

**Labyrinth Panel** (`/Labyrinth Panel`):
- Transform: local/world pos (-0.5, 1, 0.7), rot (0, 180, 0), scale (1.5, 1.5, 1.5)
- One renderer (`Object_1`); world bounds: min (-0.5, 1, 0.7), max (0.55, 1.075, 1.75),
  center (0.025, 1.0375, 1.225), size (1.05 × 0.075 × 1.05), top y = 1.075
- Old value (ENVIRONMENT_SPEC.md, pre-rescale): 1.4 × 1.4 footprint, top y ≈ 1.1, center (0.2, 1.05, 1.4).

**Labyrinth Ball** (`/Labyrinth Ball`) — not previously recorded:
- Transform: local/world pos (-0.142, 1.014, 0.998), scale (2, 2, 2)
- Components: Transform, Rigidbody, SphereCollider
- SphereCollider: local radius 0.02738798, local center (-0.075663, 0.02906, -0.084417);
  world bounds size 0.109552 per axis → world radius ≈ 0.0548
- Rigidbody: mass 0.2, linearDamping (drag) 0, angularDamping (angularDrag) 0.05,
  interpolation `None`, collisionDetectionMode `ContinuousDynamic`, isKinematic false, useGravity true

**Projectile — `Assets/3D Models/Sphere.prefab`** — not previously recorded beyond path/GUID:
- localScale (0.17, 0.17, 0.17)
- Components: Transform, MeshFilter, MeshRenderer, SphereCollider, Rigidbody, ProjectileLifetime
- SphereCollider: radius 0.5, center (0,0,0), isTrigger false
- Rigidbody: mass 0.3, linearDamping (drag) 0, angularDamping (angularDrag) 0.05,
  interpolation `None`, collisionDetectionMode `Discrete`, isKinematic false, useGravity false
- ProjectileLifetime.lifetime = 6

No component lists above differ from what DroneHoverAIV2 already referenced by name/type in the
2026-09-22 baseline; nothing extra was found attached to any of these four objects.

## Other scripts on the drone
| Script | Object | Key values |
|---|---|---|
| PropellerSpin | NOT ATTACHED in BasicScene | `find_gameobjects --type PropellerSpin --include_inactive true` returned 0 results anywhere in the open scene. The script file exists on disk (`Assets/Scripts/PropellerSpin.cs`) but is not on any GameObject in BasicScene today — propeller spin (if any) is not driven by this component currently. |
| HologramToggle | `/DroneAI2/drone_low` | pbrMaterial: Assets/Drone_Asset/M_Drone.mat (guid 054186815ab8661469b902129eea4eac) · hologramMaterial: Assets/Shaders/Holographic Mode/MAT_Hologram.mat (guid 892e79f615230dc43857e6efd6976dad) |

## RenderScene differences
| Field | BasicScene | RenderScene |
|---|---|---|
| Drone present / hierarchy | as above | not re-verified |
| Transforms | as above | not re-verified |
| DroneHoverAIV2 values | as above | not re-verified |
| Material / shader | SG_DroneOptimized, values above | not re-verified |
| HologramToggle / ScannerGlow state | as above | not re-verified |

No RenderScene values have been read live in any prior session; nothing here is carried over from
file/YAML inspection. RenderScene was not opened for this pass either (2026-09-22 or 2026-09-24) —
BasicScene stayed the only open scene, per instruction not to open/save scenes.

## Known issues (recorded, not fixed)
- HologramToggle needs a keyboard and uses `r.material` (creates material copies).
- PropellerSpin is not attached to any GameObject in BasicScene as of this verification (see "Other
  scripts" above) — flagged for the user, not changed.
- Of the three Scanner Light shader graphs in `Assets/Shaders/Scanner Light/`, only SG_FakeBloom
  (via MAT_FakeBloom.mat) is actually referenced by the drone, on the inactive `ScannerGlow` child.
  SG_DroneScanner and SG_PulseScanner (MAT_DroneScanner.mat / MAT_PulseScanner.mat) are not referenced
  anywhere in BasicScene.unity.

## Owner decisions (Shayan, 2026-09-22)
- PropellerSpin is attached only in RenderScene. It will be attached to the propellers in
  BasicScene later. This is an approved drone change; update this baseline when it's done.
- Holographic Mode (SH_Hologram / MAT_Hologram) was an experimental Shader Graph. Stays
  protected; its use in the final game is not decided.
- Scanner Light: several glow variants exist (SG_FakeBloom, SG_DroneScanner, SG_PulseScanner).
  Which one ships is decided later. Whole folder stays protected until then.
- 2026-09-24: Rescale of drone, labyrinth, projectile, DroneBounds and DroneHoverAIV2 tuning, tested
  on Quest 3S. Approved change, done by the owner directly in the Editor (not by Claude). Old → new:
  - drone_low local scale (1,1,1) → (0.59,0.59,0.59); local pos (0,0,0) → (0,-0.228,0); rotation
    unchanged (~180° about Y)
  - DroneAI2 transform: unchanged (0,2,4.76), identity rotation, scale (1,1,1)
  - DroneBounds world bounds (raw): was only known margined (ENVIRONMENT_SPEC, X −2.96…2.93,
    Y 0.77…3.80, Z 2.69…7.04) → now raw min(-1.95,1.69,3.34) max(1.89,2.98,5.82), margined
    min(-2.45,1.19,2.84) max(2.39,3.48,6.32) — read live twice this session, Y shrank further
    between the two reads as the owner kept tuning it (see DroneBounds section above)
  - Labyrinth Panel: was 1.4×1.4, top y≈1.1, center (0.2,1.05,1.4) → now 1.05×1.05 (renderer bounds),
    top y 1.075, center (0.025,1.0375,1.225)
  - Labyrinth Ball, Sphere.prefab (projectile): scale/collider/Rigidbody values captured live for the
    first time (see section above) — no prior recorded baseline to diff against
  - DroneHoverAIV2 numeric fields: unchanged from 2026-09-22 (moveSpeed, hoverAmplitude/Frequency,
    rotationSpeed, shootInterval, projectileSpeed, peakEmissionIntensity, flashDecaySpeed all identical)
  - Verified: DroneAI2's world position still lies inside DroneBounds' world bounds; no ENV_Greybox
    renderer or NAV_TeleportFloor collider intersects the new (margined) drone volume
