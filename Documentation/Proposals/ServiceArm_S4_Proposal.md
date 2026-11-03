# Proposal — ServiceArm working envelope vs the docked drone (HERO_SPEC §4)

Status: **Accepted: option B (2026-11-03).** The §5 text is in HERO_SPEC §4 (with "owner decision
2026-11-03"); the §6 DroneHoverAIV2 fix was applied on 2026-11-03 (untested in Unity).
Units: metres, Unity axes (+Y up, +Z toward the far wall), as in HERO_SPEC.

## 1. The conflict

HERO_SPEC §4 (Working pose) says: *"the propellers start at |x| ≥ 0.44, so the arm stays inside
|x| < 0.3"*, and adds a 2026-09-28 note that with the v2 docking yaw (−28.3°, §3) the back-right
and front-left prop discs reach in to |x| ≈ 0.14. DEVLOG has carried this as open since 2026-09-28
("Next: Service Arm, starting with the §4 conflict").

## 2. Verification

### Method
I could not read the live Editor here, so the drone was rebuilt from the repo:
- Geometry: `Assets/Drone_Asset/drone_low.fbx` (binary FBX 7.4, UnitScaleFactor 1 = cm, Y-up),
  read with a small Python parser. Propeller pivots are the FBX `Lcl Translation` of
  `Propellor1–4_low`; the engine meshes give the hub positions.
- Transform chain from `ProtectedAssets/DroneBaseline.md` (live read 2026-09-24): FBX → Unity
  (cm → m, X mirrored), `drone_low` local position (0, −0.228, 0), rotation ≈ 180° about Y,
  scale 0.59; `DroneAI2` at (0, 2, 4.76), yaw 0.
- Docking pose from HERO_SPEC §3: `DroneAI2` rotation Y −28.30°, position (−0.032, 2.000, 4.754).
- Spinning disc = cylinder about the propeller pivot (vertical axis) with the largest blade-vertex
  radius, over the blade's y range.

### The reconstruction matches the documented values

| Value | Documented | Recomputed |
|---|---|---|
| Body centre, docked (HERO_SPEC §3) | (0.003, 1.758, 4.689) | (0.0028, 1.7584, 4.6895) |
| Drone top (HERO_SPEC §4) | 1.986 | 1.9859 |
| Front engines lower than back (HERO_SPEC §3: front limbs 54.4 mm lower) | 54.4 mm | 54 mm (engine bottoms 1.713 / 1.767) |
| Docked: front-right and back-left limbs along ±X on the plate centre line (z 4.69) | z ≈ 4.69 | FR hub (0.699, 4.692), BL hub (−0.699, 4.692) |
| Static blade inner edge at yaw 0 (the old "0.44") | 0.44 | 0.438 / 0.440 |
| Drone triangle count (14 meshes) | — | 2,114 |

### Propeller discs (disc radius 0.327 for all four)

| Prop (engine) | Yaw 0, pivot x, z | Yaw 0 disc x | Docked (−28.3°) pivot x, z | Docked disc x | Docked disc z | Disc y |
|---|---|---|---|---|---|---|
| Propellor1 (FR) | 0.614, 4.359 | 0.287 … 0.942 | 0.699, 4.692 | 0.372 … 1.026 | 4.365 … 5.020 | 1.817 … 1.845 |
| Propellor2 (FL) | −0.614, 4.359 | −0.942 … −0.287 | −0.383, 4.110 | **−0.710 … −0.055** | 3.782 … 4.437 | 1.817 … 1.845 |
| Propellor3 (BR) | 0.616, 5.021 | 0.289 … 0.944 | 0.387, 5.276 | **0.060 … 0.714** | 4.949 … 5.603 | 1.870 … 1.898 |
| Propellor4 (BL) | −0.616, 5.021 | −0.944 … −0.289 | −0.699, 4.692 | −1.026 … −0.371 | 4.364 … 5.019 | 1.870 … 1.898 |

### Findings
1. **Conflict confirmed, and tighter than documented.** Docked, the front-left and back-right
   spinning discs reach |x| = **0.055 / 0.060**, not ≈ 0.14. The static blades (as modelled, not
   spinning) reach 0.097 / 0.101. Either way they are deep inside the |x| < 0.3 strip.
2. **The old rule was already wrong at yaw 0.** "|x| ≥ 0.44" is the static blade position. The
   spinning discs reach 0.287 / 0.289 at yaw 0, so even the undocked drone violated |x| < 0.3 by
   ~13 mm.
3. **No yaw fixes it.** Sweeping yaw −90° … +90° in 0.5° steps, the best value of the innermost
   disc edge is 0.287 m at yaw 0. A plan-view strip of half-width 0.3 cannot be kept clear of the
   spinning discs at any yaw.
4. **The conflict is in plan view only.** The highest disc top is y 1.898 (back discs); the tool
   tip in the working pose is y ≈ 2.04, i.e. **142 mm above** it, and every other arm part is
   higher. A real collision needs an arm part to drop below ~1.9 inside a disc footprint.
5. In Standby the props do not spin (`PropellerSpin` is enabled at *Released*, HERO_SPEC §1, and
   is not attached in BasicScene per DroneBaseline). I still use the spinning discs as the envelope,
   as the Cradle clearance checks do, so the rule stays valid once `PropellerSpin` is attached.

What is confirmed vs expected: the numbers above are recomputed from repo files and match the
documented live values; they are **not** a live Editor read. Confirm with a live read (or the
Cradle clearance stage, which uses the live drone dump) before building the arm.

## 3. Options

### A. Different docking yaw
- Numbers: no yaw clears |x| < 0.3 (best 0.287 at yaw 0, finding 3). The mirrored yaw (+28.3°)
  only swaps the pair: FR and BL discs would then reach inward instead.
- Pros: none for this rule.
- Cons: the whole Cradle v2 is built around −28.3°: the FR/BL limbs on the plates, identical pads
  plus the 54.4 mm riser, the fold checks (limbs ≥ 11.1 mm), UVs, high-poly and the final Substance
  bake. Changing the yaw re-opens all of it.
- **Rejected.**

### B. Replace the plan strip with a 3D clearance envelope (mount and pose unchanged)
- Rule: every ServiceArm part keeps **≥ 100 mm** from the four spinning-disc volumes and **≥ 50 mm**
  from the drone mesh, in the working pose and over the whole idle motion. Inside a disc footprint
  no arm part goes below **y 2.00** (1.898 + 0.10).
  - 100 mm is the disc margin already used for the Cradle ("needed ≥ 100 mm", pad study, §3).
  - The current pose already passes in height: tool tip 2.04 → 142 mm over the back discs, 54 mm
    over the drone top (1.986).
- Idle motion: turret ±10° yaw swings the tool sideways; with the tool ~0.6 m in front of the
  turret axis (mount z 5.30, body centre z 4.69) that is about ±0.10 m. It stays above y 2.00, so
  the rule holds, but it must be part of the sweep.
- Pros: no change to the Cradle, the drone or the mount; stowed pose (y 3.77 … 3.95, footprint
  z 5.30 … 6.30) unchanged; the rule describes the real hazard.
- Cons: the clearance now depends on height, so the tool cannot reach down beside the body; needs a
  3D sweep check in the ServiceArm checker (the Cradle checker already has the drone and disc
  geometry to reuse).

### C. Align the arm with the drone's axis (moved mount + base yaw)
- Put the mount on the drone's own back axis, 0.61 behind the body centre (the same distance as
  today): back axis at yaw −28.3° = (−0.474, 0, 0.881) → mount **(−0.286, 4.0, 5.227)**, turret
  base yaw **−28.3°**.
- In the drone's frame the disc inner edges are at |x_local| 0.287 / 0.289, so the plan rule
  becomes |x_local| < **0.189** (100 mm margin).
- Arm width from the §4 table: UpperArm 0.12, Forearm offset 0.12, Wrist offset 0.10, ToolHead
  0.14 → about 0.35 across if both offsets go to one side. Centred on the axis that is ±0.175,
  inside ±0.189 with **14 mm** to spare.
- Pros: keeps a simple plan rule; the arm works symmetrically over the drone.
- Cons: very tight lateral margin; §4 table, stowed footprint and ceiling-light keep-out move
  (stowing along the turned axis ends near x −0.76, z 6.1, or the turret must unwind before the
  fold); more spec churn for little gain over B.

## 4. Recommendation

**Option B.** It removes a rule that never matched the spinning discs, keeps the finished Cradle and
the mount untouched, and the current working pose already clears the discs by 142 mm in height.
Option C is the fallback if the owner wants the tool to reach lower than the disc plane.

## 5. Proposed replacement text for HERO_SPEC §4

Replace the whole **Working pose (Standby)** bullet with:

```markdown
- **Working pose (Standby):** tool tip ~0.05 above the drone's top (y ≈ 2.04, drone top 1.986),
  pointing down, near x = 0. Roughly shoulder −60°, elbow +70°, wrist keeping the tool vertical;
  tune by eye. Reach check: 1.60 needed, 1.90 available.
- **Clearance rule (3D; replaces the |x| < 0.3 strip, owner decision pending):** docked at yaw
  −28.3° (§3), the spinning propeller discs (radius 0.327 about each propeller pivot) reach in to
  |x| 0.055 (front-left, y 1.817 … 1.845) and 0.060 (back-right, y 1.870 … 1.898); even at yaw 0
  they reach |x| 0.287, so no plan-view strip can stay clear. Instead, every ServiceArm part keeps
  **≥ 100 mm** from the four disc volumes and **≥ 50 mm** from the drone mesh, in the working pose
  and over the whole idle motion (turret ±10°, wrist ±15°, tool roll); inside a disc footprint no
  part goes below **y 2.00**. Checked by a clearance sweep against the drone at the docking pose
  (re-read the drone live first). The hard rule is still that nothing touches the drone.
```

## 6. DroneHoverAIV2 — yaw handling review (`Assets/Scripts/DroneHoverAIV2.cs`)

HERO_SPEC §10 asks that the drone take off from yaw −28.3° "and turn smoothly, without snapping
to 0°". Values used below: rotationSpeed 3, hoverAmplitude 0.3, hoverFrequency 2, moveSpeed 1.5
(live, DroneBaseline); ball at (−0.142, 1.014, 0.998) (DroneBaseline 2026-09-24; Labyrinth v2 may
have moved it slightly).

1. **Yaw itself: no snap.** Rotation is `Quaternion.Slerp(transform.rotation, targetRot, 3·dt)`
   from the *current* rotation, so a drone that starts at −28.3° turns smoothly. Target from the
   docking position: the look direction is (−0.110, −0.986, −3.756) → yaw −178.3°, plus the
   built-in 180° flip → **+1.7°**: a ~30° turn. The §10 yaw requirement is already met by the code.
2. **The target includes pitch (expected behaviour, but it matters at take-off).**
   `LookRotation(lookDir)` uses the full 3D direction, so the drone also tips nose-down by
   **14.7°** toward the ball. With `DroneAI2`'s pivot at y 2.0, the front engines (0.40 m in front
   of the pivot) drop by roughly **0.09 m** when the full pitch is reached (estimate from the
   geometry above; Slerp at 3/s gets most of the way within about a second). This happens while
   the yoke arms are still opening (drone enabled at +1.0 s of a 1.2 s swing, §1).
3. **Bug — hover phase snaps on enable (confirmed from the code).** `hoverOffset =
   Sin(Time.time · f) · A` uses absolute game time, and `basePosition` is the docked position. When
   `FacilitySequence` enables the component at an arbitrary `Time.time`, the first frame moves the
   drone by up to **±0.30 m** vertically. A downward jump puts the limb undersides (y ≈ 1.71) as low
   as ~1.41 next to arms that are still swinging open. Whether that touches the arms depends on
   the easing at that moment; it is a visible snap either way.
4. **Init only in `Start`.** `basePosition` and the first `targetPoint` are set in `Start()`. If
   the sequence ever disables and re-enables the drone (e.g. a reset), it resumes from stale values
   and teleports. Moving the init to `OnEnable` covers the first enable and any later one.
5. **Minor — reach check uses the bobbing position.** `Distance(transform.position, targetPoint)`
   includes the ±0.3 m bob while `reachThreshold` is 0.1, so a target only counts as reached when
   the sine is near zero. `basePosition` is the intended point.
6. **Note only (not changed):** `Lerp`/`Slerp` with `k · Time.deltaTime` is frame-rate dependent.
   Changing it would change the hand-tuned feel, so it is left alone.

### Proposed fix (diff, not applied; `git apply --check` passes against the current file)

The defaults keep today's flight behaviour after take-off; only the first `takeoffBlend` seconds
change (hover fades in from phase 0, yaw-only turn so the drone doesn't tip into the opening arms).

```diff
--- a/Assets/Scripts/DroneHoverAIV2.cs
+++ b/Assets/Scripts/DroneHoverAIV2.cs
@@ -28,6 +28,10 @@ public class DroneHoverAIV2 : MonoBehaviour
     [Tooltip("How quickly the drone rotates to face the target.")]
     public float rotationSpeed = 3f;
 
+    [Header("Take-off")]
+    [Tooltip("Seconds after enable during which the hover fades in and the drone turns on yaw only (no pitch).")]
+    public float takeoffBlend = 1.5f;
+
     // --------------------------------------------------------
     // [2] SHOOTING VARIABLES
     // --------------------------------------------------------
@@ -62,19 +66,14 @@ public class DroneHoverAIV2 : MonoBehaviour
     // Internal navigation tracking
     private Vector3 targetPoint;
     private Vector3 basePosition;
+    private float enabledTime;
 
     // ========================================================
     // UNITY METHODS
     // ========================================================
 
-    void Start()
+    void Awake()
     {
-        // Pick the very first random destination inside our bounding box
-        targetPoint = GetRandomPointInBounds();
-
-        // Record where the drone is currently sitting in the world
-        basePosition = transform.position;
-
         // Initialize the MaterialPropertyBlock. 
         // I use this instead of modifying the material directly so Unity doesn't 
         // accidentally create a duplicate material in memory, which would hurt VR performance.
@@ -84,8 +83,21 @@ public class DroneHoverAIV2 : MonoBehaviour
         emissionPropertyID = Shader.PropertyToID("_Ring_Intensity");
     }
 
+    void OnEnable()
+    {
+        // Runs on every enable (FacilitySequence enables the drone at release),
+        // so take-off always starts from the current (docked) pose without a jump.
+        targetPoint = GetRandomPointInBounds();
+        basePosition = transform.position;
+        enabledTime = Time.time;
+        shootTimer = 0f;
+    }
+
     void Update()
     {
+        float sinceEnable = Time.time - enabledTime;
+        float takeoff = takeoffBlend > 0f ? Mathf.Clamp01(sinceEnable / takeoffBlend) : 1f;
+
         // --------------------------------------------------------
         // 1. HANDLE VFX (The Emissive Flash Decay)
         // --------------------------------------------------------
@@ -114,9 +126,10 @@ public class DroneHoverAIV2 : MonoBehaviour
             moveSpeed * Time.deltaTime
         );
 
-        // Calculate the physical bobbing motion using a Sine wave (Mathf.Sin)
-        // Time.time keeps it smoothly animating forever based on the game clock
-        float hoverOffset = Mathf.Sin(Time.time * hoverFrequency) * hoverAmplitude;
+        // Bobbing starts at phase 0 when the drone is enabled and fades in over takeoffBlend,
+        // so the first frame after release does not jump by up to hoverAmplitude.
+        float hoverOffset = Mathf.Sin(sinceEnable * hoverFrequency) * hoverAmplitude
+                            * Mathf.SmoothStep(0f, 1f, takeoff);
 
         // Apply the physical bobbing offset to the base position
         Vector3 finalPosition = basePosition + new Vector3(0, hoverOffset, 0);
@@ -130,6 +143,10 @@ public class DroneHoverAIV2 : MonoBehaviour
             // Find the direction from the drone to the target
             Vector3 lookDir = labyrinthBall.transform.position - transform.position;
 
+            // During take-off turn on yaw only, so the body doesn't tip into the opening cradle arms.
+            if (takeoff < 1f)
+                lookDir.y = 0f;
+
             // Only rotate if the target isn't sitting inside the drone (prevents math errors)
             if (lookDir.sqrMagnitude > 0.001f)
             {
@@ -153,7 +170,7 @@ public class DroneHoverAIV2 : MonoBehaviour
         // 4. HANDLE NAVIGATION (Picking a new target)
         // --------------------------------------------------------
         // If the drone is close enough to its current destination, pick a new one
-        if (Vector3.Distance(transform.position, targetPoint) < reachThreshold)
+        if (Vector3.Distance(basePosition, targetPoint) < reachThreshold)
         {
             targetPoint = GetRandomPointInBounds();
         }
```

Notes on the diff:
- `shootTimer = 0f` in `OnEnable` keeps today's first shot 2 s after release.
- When `takeoff` reaches 1 the pitch returns smoothly (Slerp), so there is no snap at the end of
  the blend either.
- `takeoffBlend` is a new serialized field (default 1.5 s, an assumption for the owner to tune on
  Quest). Hand-tuned existing values are untouched.
- After applying: recompile, then check in Play Mode that the drone leaves the cradle without a
  vertical jump, and re-read the drone live for DroneBaseline.md (HERO_SPEC §10).
