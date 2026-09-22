# Drone Baseline (locked asset)

Purpose: a verified record of the locked drone, so any change to it can be detected.
Every value below must come from a LIVE Editor read, not from YAML parsing.
Status: FILLED — production step 2.

- Verified on: 2026-09-22
- Verified at Git commit: dae4fb1625640552a8de8747c8f496ab5d43f8a4
- Unity: 6000.3.24f1
- Read from: BasicScene (open, isDirty=true at read time — not saved, no changes made)

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

Important transforms (local position / rotation / scale):
| Object | Position | Rotation (quaternion x,y,z,w) | Scale |
|---|---|---|---|
| DroneAI2 | (0, 2, 4.76) | (0, 0, 0, 1) — identity | (1, 1, 1) |
| drone_low | (0, 0, 0) | (0, -1, 0, 0.00023034) — ≈180° about Y | (1, 1, 1) |
| ToShoot_low/Shoot Point | (0, -0.00813, 0) | (0, 0, 0, 1) — identity | (1, 1, 1) |

## DroneHoverAIV2 on DroneAI2 (BasicScene)
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

## Other scripts on the drone
| Script | Object | Key values |
|---|---|---|
| PropellerSpin | NOT ATTACHED in BasicScene | `find_gameobjects --type PropellerSpin --include_inactive true` returned 0 results anywhere in the open scene. The script file exists on disk (`Assets/Scripts/PropellerSpin.cs`) but is not on any GameObject in BasicScene today — propeller spin (if any) is not driven by this component currently. |
| HologramToggle | `/DroneAI2/drone_low` | pbrMaterial: Assets/Drone_Asset/M_Drone.mat (guid 054186815ab8661469b902129eea4eac) · hologramMaterial: Assets/Shaders/Holographic Mode/MAT_Hologram.mat (guid 892e79f615230dc43857e6efd6976dad) |

## RenderScene differences
| Field | BasicScene | RenderScene |
|---|---|---|
| Drone present / hierarchy | as above | not verified |
| Transforms | as above | not verified |
| DroneHoverAIV2 values | as above | not verified |
| Material / shader | SG_DroneOptimized, values above | not verified |
| HologramToggle / ScannerGlow state | as above | not verified |

No RenderScene values have been read live in any prior session; nothing here is carried over from
file/YAML inspection. RenderScene was not opened for this pass (BasicScene stayed the only open scene,
per instruction not to open/save scenes).

## Known issues (recorded, not fixed)
- HologramToggle needs a keyboard and uses `r.material` (creates material copies).
- PropellerSpin is not attached to any GameObject in BasicScene as of this verification (see "Other
  scripts" above) — flagged for the user, not changed.
- Of the three Scanner Light shader graphs in `Assets/Shaders/Scanner Light/`, only SG_FakeBloom
  (via MAT_FakeBloom.mat) is actually referenced by the drone, on the inactive `ScannerGlow` child.
  SG_DroneScanner and SG_PulseScanner (MAT_DroneScanner.mat / MAT_PulseScanner.mat) are not referenced
  anywhere in BasicScene.unity.
