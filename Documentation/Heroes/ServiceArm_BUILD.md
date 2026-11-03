# ServiceArm (Hero 01b) — build notes

Cloud build, 2026-11-03, branch `cloud/hero-servicearm`. Hero workflow v3 (ASSET_RULES), Gate as the reference
implementation. Blender: bpy 5.2.2 from PyPI in a venv outside the repo (same version as the project's Blender 5.2.2
LTS, Cycles CPU, 4 cores); `D:/AI_Labyrinth/...` paths resolve under the launcher's scratch folder. No Unity here.

Inputs: HERO_SPEC §4 (sizes, hinges, poses, motion, clearance rule; read-only for this build), the owner's concept
`Documentation/References/ServiceArm/servicearm_front.jpg` (master: look and detail) and `servicearm_ortho_side.jpg`
(proportions), STYLE_GUIDE (palette, wear, rust rule), EXPORT_CONTRACT hero mode,
`Proposals/ServiceArm_S4_Proposal.md` (drone rebuild method).

Scripts (`Tools/Blender/heroes/`):

| Script | Does |
|---|---|
| `servicearm_kin.py` | §4 chain, IK for the working pose, idle and fold poses, docked drone rebuilt from `drone_low.fbx`, disc volumes |
| `servicearm.py` | generator (`-- blockout` = H0); saves the review file `D:/AI_Labyrinth/Blender/Source/Heroes/ServiceArm/LAB_HERO_ServiceArm_v1.blend` |
| `servicearm_check.py` | `topo`, `clearance`, `renders <stage>` |
| `servicearm_tex.py` | `bake`, `check`, `renders` (H2) |
| `servicearm_export.py` | hero-mode FBX export + re-import check (H3a) |

## Decisions (made without the owner, who was away; reasons given)

1. **Offsets to +X, camera on +X.** The §4 elbow (0.12) and wrist (0.10) offsets lay the forearm and tool beside the
   upper arm when stowed; with both offsets on the same side the tool lands at x 0.22 in the arm plane, so the turret
   yaws the arm plane to bring the tip onto x = 0 (working yaw +21.1°). Opposite-sign offsets would put the stowed
   tool on top of the upper arm or the turret. +X was chosen because the concept's side sheet then reads correctly:
   seen from +X (screen right = +Z) the elbow is on the right and the wrist on the left, as drawn.
2. **Elbow behind the shoulder ("elbow back").** Working pose from IK (`servicearm_kin.ik_working`): tip on
   (0, 2.04, 4.69), tool vertical; turret +21.14°, shoulder +81.18°, elbow −117.79°, wrist −53.38° (Unity
   localEulerAngles). Reach shoulder → wrist 1.628 m (§4: 1.60 needed, 1.90 available). Elbow-back is the concept's Z
   (upper arm away from the drone, forearm coming back) and folds to the stowed pose by lifting straight up and back;
   elbow-forward would have to swing the upper arm through the vertical (140°) over the drone.
3. **Tool vertical in the working pose, roll spinning about the tool axis.** The tip 0.265 below the wrist hinge.
4. **Concept pose** (renders only, not a gameplay pose): joint angles read off the side sheet (upper arm 37° below
   horizontal, forearm 22.6° below horizontal coming back, tool vertical; shoulder 37°, elbow −59.6°, wrist −67.4°,
   roll −90° so the tool's notch faces the camera). Used for every "vs concept" render, because the working pose is
   nearly stretched (elbow interior 118°) and does not show the concept's folded Z.

## Spec vs concept (the spec wins; each deviation listed)

Concept scale from the side sheet: plate 0.40 m = 490 px → 1225 px/m.

| Item | Concept (at that scale) | Built (HERO_SPEC §4) | Why |
|---|---|---|---|
| Upper arm length / section | ≈ 0.60 / 0.14 | 1.00 / 0.12 × 0.12 | §4 sizes; reach 1.60 needs the length |
| Forearm length / section | ≈ 0.62 / 0.11 | 0.90 / 0.10 × 0.10 | §4 sizes |
| Link thickening toward the concept | — | not done | stowed layer: the shoulder axis is at y 3.83 and the layer bottom at 3.77, so any link or joint taller than ±0.06 about its axis leaves the layer (all links lie at the shoulder height when stowed); widths are bound by the 0.12 / 0.10 offsets (10 mm / 5 mm gaps) |
| Joint lobes (elbow disc etc.) | r ≈ 0.078 | r 0.060 (elbow disc), 0.055 shoulder cheek | same stowed-layer limit |
| Ceiling → shoulder axis | ≈ 0.25 | 0.17 | §4 hinges (turret 0.05, shoulder 0.12) |
| Shoulder under the turret | axis ≈ 0.05 toward −Z | on the turret axis | §4 hinge (0, −0.12, 0) |
| Shoulder housing | one wide block under the turret, rounded lobe | single cheek on −X + lug with slotted cap on +X | §4 turret bottom (y 3.88) is only 0.05 above the shoulder axis: a 0.12 link root (±0.06) would hit it, so the root is a lug r 0.044 and the bar's full height starts outside the turret disc (z ≥ 0.165) |
| Mount stack | plate 0.045 + adapter 0.045 | plate 0.025 + adapter 0.023 | §4: the turret hinge is 0.05 under the ceiling |
| Wrist knuckle width | ≈ 0.10 | 0.09 | 0.10 wide at a 0.10 offset would touch the forearm (0 gap); 5 mm gap |
| Stowed footprint | — | z 5.135 … 6.36 (tool beside the turret) | §4 says z 5.30 … 6.30; with the wrist straight the tool lies along −Z past the shoulder (inside the mount plate's own z 5.10 … 5.50); the rounded link ends add 0.06 at the elbow |

## Feature inventory (concept → build)

Rule (ASSET_RULES depth rule): ≥ 15 mm → geometry, smaller → normal map / texture. H1 = modelled, H2 = textured.

| # | Feature (concept) | How | H1 | H2 |
|---|---|---|---|---|
| 1 | Square ceiling plate, chamfered edge | geometry (0.40 × 0.025, 45° corner clips 12 mm, 6 mm chamfer) | ✓ | ✓ |
| 2 | 4 hex nuts + stud ends on the plate underside | geometry (30 mm AF × 16 mm) | ✓ | ✓ |
| 3 | Washers under the nuts | normal map (3 mm) | n/a (map) | ✓ |
| 4 | Octagonal adapter under the plate | geometry (frustum 0.34 → 0.28, 23 mm) | ✓ | ✓ |
| 5 | Adapter side ports (rectangular slot, oval slot) | normal map + dark texture | n/a (map) | ✓ |
| 6 | Small bolts on the adapter | normal map | n/a (map) | ✓ |
| 7 | Turret bearing disc Ø 0.26 × 0.07 | geometry (32 sides, 6 mm chamfers) | ✓ | ✓ |
| 8 | Turret groove ring | normal map | n/a (map) | ✓ |
| 9 | Round boss on the turret side | geometry (Ø 30 mm, 23 mm proud; H2: smaller and higher, clear of the disc chamfers) | ✓ | ✓ |
| 10 | Shoulder housing / bracket | geometry (cheek on −X, rounded r 0.055) | ✓ | ✓ |
| 11 | Shoulder slotted cap | geometry (Ø 72 mm × 15 mm); slot normal map | ✓ | ✓ |
| 12 | Bracket outer cap | geometry (Ø 80 mm) | ✓ | ✓ |
| 13 | Cable connector box with gland | geometry (box into the cheek, 42 × 44 mm face + gland) | ✓ | ✓ |
| 14 | Link bodies with chamfered edges | geometry (6 / 5 mm chamfers), rounded ends on the hinges | ✓ | ✓ |
| 15 | Link end collars (wider bands) | normal map + texture (the step is < 15 mm) | n/a (map) | ✓ |
| 16 | Side panel: groove outline, raised plate with stepped edge | normal map | n/a (map) | ✓ |
| 17 | Panel bolts, link-end bolts | normal map | n/a (map) | ✓ |
| 18 | Cyan light strip on each link side | emission + normal map (slot < 15 mm) | n/a (map) | ✓ |
| 19 | Elbow: big disc with 8-bolt ring and centre cap | geometry disc r 0.06 × 17 mm, cap r 0.03 × 15 mm; bolts normal map | ✓ | ✓ |
| 20 | Wrist: rounded knuckle with small cap | geometry (cap Ø 64 mm) | ✓ | ✓ |
| 21 | Wrist neck with ring grooves | geometry (Ø 84 mm); grooves normal map | ✓ | ✓ |
| 22 | Tool collar (steel) | geometry (Ø 88 mm × 35 mm) | ✓ | ✓ |
| 23 | Ochre tool block with the side notch | geometry (0.14 × 0.10 × 0.135, notch 35 mm) | ✓ | ✓ |
| 24 | Tool bolts, soot / grime on the ochre | normal map, texture | n/a (map) | ✓ |
| 25 | Steel pin | geometry (Ø 36 × 40 mm) | ✓ | ✓ |
| 26 | Flexible conduit along the arm | geometry tube Ø 22 mm (8 sides) on clips; corrugation normal map | ✓ | ✓ |
| 27 | Cable clips (band clamps) | geometry (34 × 16 mm arches) | ✓ | ✓ |
| 28 | Slack loops at the joints | geometry: over the elbow and wrist ends, joined on the hinge axes at swivels | ✓ | ✓ |
| 29 | Second, thinner cable beside the conduit | left out at H0 (see open points) | left out | left out |
| 30 | Rust: edges, bottoms, around bolts, panel corners, streaks | texture (rust rule) | n/a (map) | ✓ |
| 31 | Edge wear to steel, grime, scratches | texture | n/a (map) | ✓ |

## H0 — blockout (2026-11-03)

`servicearm.py -- blockout`: main forms only (plate and adapter, two-tier turret with the shoulder cheek, links with
their hinge profiles, wrist knuckle and neck, tool block and pin; no caps, nuts, clips or cables), flat review colours.
Renders in `Documentation/Media/servicearm/`: `servicearm_h0_vs_concept.jpg` (master camera, concept pose),
`servicearm_h0_vs_concept_side.jpg` (orthographic side camera, framed like the sheet), `..._side_platescale.jpg`
(same camera at the sheet's plate scale, 1225 px/m: shows how much longer the spec arm is), `servicearm_h0_working_*`
(over the docked drone: 3/4, side, player view from the terminal side), `servicearm_h0_stowed_*`.

Clearance on the blockout (`servicearm_check.py -- clearance h0`, 1,952 poses: working, 600 idle combinations
(turret −10 … +10, wrist −15 … +15, roll 0 … 345 in 15° steps), the fold from 54 idle extremes in 25 steps each,
stowed): all PASS — discs ≥ 252 mm, drone mesh 54.1 mm (the tool tip over the top, working pose), nothing inside a
disc footprint below y 2.37, stowed layer 3.770 … 3.948, released volume clear, reach 1.628 / 1.90.

H0 finding, fixed: stowed, the forearm's wrist end lay 2 mm into the underside of a full-height turret disc (spec disc
bottom y 3.878, forearm top 3.88, at r 0.086 from the turret axis). The turret is now two-tier like the concept's
ring over its housing: disc Ø 0.26 × 0.048 over a hub Ø 0.15 × 0.022 (total height 0.07 as in §4); gap 20 mm.

## H1 — model (2026-11-03)

`servicearm.py` (full) + `servicearm_check.py -- topo / clearance / renders h1`. Results on the final H1 geometry
(after the H2-driven tweaks below, which changed no sizes in §4):

| Part | Tris | Quads / tris | UV islands |
|---|---|---|---|
| Mount | 420 | 206 / 8 | 18 |
| Turret | 950 | 439 / 72 | 23 |
| UpperArm | 1,198 | 566 / 66 | 19 |
| Forearm | 1,137 | 531 / 75 | 19 |
| Wrist | 546 | 254 / 38 | 13 |
| ToolHead | 272 | 131 / 10 | 10 |
| **Total** | **4,523** | | 102 |

- Topology PASS for every part: no n-gons, non-manifold edges, loose geometry, duplicates, zero-area faces or
  inconsistent winding; no bow-tie / concave quads; winding agrees with the custom normals; 0 quads over 2 mm twist.
  Open borders are the deleted hidden faces and the uncapped ends embedded in a parent shell (by design, as the Gate).
- Shading PASS: no flat face has a corner normal > 0.5° off its face normal. Rule added for the arm: two FLAT faces
  meeting at > 3° are always a hard edge (the Gate's 30° let the upper arm's ramp, the lug chamfer and the adapter sides
  blend into their neighbours); CHAMFER strips and ROUND sides as the Gate. Hard edges = UV seams.
- UVs PASS: every island at 512 px/m (fixed-density pack: `servicearm.pack_fixed`, same skyline packer as
  `cradle_v2_uv.pack`, which would otherwise scale the islands up to fill the sheet: 999 px/m), padding ≥ 8 px,
  border 4 px. The arm fills only **11.9 %** of the 2048 sheet at 512 px/m — the set could ship at 1024 (or go to
  ~1000 px/m) after the Quest test; owner decision.
- Cables: centripetal Catmull-Rom (the uniform version overshot at unevenly spaced points and folded the tube at the
  forearm's wrist loop: 3 faces against their normals), simplified to a point per 7° of turn; 8-sided tube Ø 22 mm.
- Clearance PASS (1,952 poses, see H0 for the set): discs ≥ 252.4 mm, drone mesh 54.1 mm (tool tip over the top),
  lowest point inside a disc footprint y 2.371 (rule ≥ 2.00); part pairs: adjacent ≥ 2.0 mm (lug under the turret hub,
  forearm beside the upper arm), others ≥ 20 mm; stowed layer y 3.770 … 3.948; released volume clear; ceiling clear;
  reach 1.628 / 1.90.
- H1 fixes found by the sweep: the wrist's cable gland dipped 1 mm into the tool collar (gland and cable end raised
  6 mm); found by the texture checks (H2) and fixed in the model: cables lifted to 7 mm above the link tops on their
  clips (AO crevice), turret boss Ø 30 mm moved up clear of the disc chamfers, connector box run into the cheek (no
  10 mm pocket), embedded cylinder / prism ends no longer capped (buried faces; one had its normal flipped).
- Renders (`Documentation/Media/servicearm/`): `servicearm_h1_vs_concept.jpg`, `..._vs_concept_side.jpg`,
  `..._vs_concept_side_platescale.jpg`, `servicearm_h1_working_{34,side,player}.jpg`,
  `servicearm_h1_stowed_{34,close,side}.jpg`, `servicearm_h1_wire.jpg`, `servicearm_h1_wire_wrist.jpg`,
  `servicearm_h1_checker.jpg` (32 px cells = 6.25 cm), `servicearm_h1_uv_layout.jpg`.
- Renders are Cycles only: Workbench needs a GPU context (libEGL) that the container doesn't have.

## H2 — textures (2026-11-03)

`servicearm_tex.py -- bake / check / renders` (Gate pipeline and helpers from `gate_tex.py`). One 2048 set:
`Assets/Environment/Heroes/ServiceArm/Textures/T_LAB_HERO_ServiceArm_{BaseColor,Normal,Mask,Emission}.png` (Git LFS),
BaseColor / Emission sRGB, Normal OpenGL, Mask R metallic / G AO / A smoothness (linear). Full bake 7 min (pre-bakes
3 min, reusable with `bake reuse`).

- **Arm paint** sRGB **88 92 100**, sampled from the concept's lit link side panels (medians 88-95 / 89-92 / 94-98):
  a cool neutral grey, lighter and less blue than the Gate's gunmetal (90 104 115). Proposed for STYLE_GUIDE as
  "service-arm paint" (each hero's paint is decided in its design step). Ochre, polymer, machined steel, cyan
  70 170 255 and rust from the STYLE_GUIDE palette; cable conduit non-metal grey 84 86 86 (corrugation in the normal map).
- Detail (normal map / mask, from part-local positions): link side panels with a groove frame, a raised plate with the
  concept's stepped edge, 4 plate bolts, the cyan strip in a dark slot below the step, end-block seams and bolts;
  elbow disc 8-bolt ring; shoulder cap slot; bracket cap 6 bolts; wrist cap 4 bolts; turret groove; neck and collar
  grooves; adapter side ports (rectangular / oval) and nut washers; tool bolts and soot (bottom, notch, edges);
  cable corrugation (7.5 mm pitch along the curve). Rust streaks run down the faces in the working pose.
- Look iterations (3, 2048 with reused pre-bakes), against `servicearm_front.jpg`: (1) review lights were overexposing
  (steel clipped white), rust read as orange rings round the bolts, panel lines too faint, soot too weak → dimmer
  lights, fewer and tighter bolt rings, browner rust, more edge rust, grooves darken the albedo; (2) more edge rust;
  (3) the tool came out too dirty (median 87 65 39: soot + "more rust low" + grime stack up on the lowest part) → the
  ochre keeps 30 % of the rust and half the grime, lighter soot: median 129 97 49, it stays one of the brightest
  things (STYLE_GUIDE).
- Checks (`check`), all PASS: AO black scan (contact lines only; documented crevices accepted and printed: texels
  < 15 mm from a cable / the link face under it, and buried texels inside a part's own intersecting shells from which
  no ray escapes; one 13-texel wedge between the shoulder cheek and the turret hub reported as a small crevice);
  PBR non-metal 30-240: 0.00 % outside; metal ≥ 180: 0.22 % below; **rust 7.7 %** of the painted texels (rule
  5-15 %; lower half 6.3 %, upper half 8.5 %); emission only in the strips (median sRGB 66 162 243); normal seams:
  ≤ 2 bad samples per part (the worst ones sit where a slot or bolt crosses a split on the small cap faces: shoulder
  slotted cap, bracket cap, tool block side). Medians: paint 84 87 94 / smoothness 0.42, polymer 38 39 39, steel
  185 187 189 (metallic 1, smoothness 0.27), ochre 129 97 49, cable 80 82 82.
- Renders (Cycles, Standard view, `Documentation/Media/servicearm/`): `servicearm_h2_vs_concept.jpg` (master camera),
  `servicearm_h2_vs_concept_side.jpg`, `servicearm_h2_working_34.jpg` (over the docked drone in its room position),
  `servicearm_h2_working_player.jpg` (from the terminal side), `servicearm_h2_closeup_{elbow,tool,mount}.jpg`,
  `servicearm_h2_dim_facility.jpg` (lamps at 35 %), `servicearm_h2_stowed_{34,close}.jpg`,
  `servicearm_h2_map_{basecolor,normal,emission,mask_metallic,mask_ao,mask_smoothness}.jpg`. White-clip check on
  every render: PASS (no pixel with all channels > 0.85).

## H3a — Unity preparation, cloud part (2026-11-03)

Written and checked in the cloud (bpy 5.2.2, no Unity); H3b runs it in the Editor.

- **FBX** (`servicearm_export.py`, EXPORT_CONTRACT hero mode): `Assets/Environment/Heroes/ServiceArm/`
  `LAB_HERO_ServiceArm_{Mount,Turret,UpperArm,Forearm,Wrist,ToolHead}_01.fbx` (Git LFS), each at identity with one
  material slot, mesh in the STOWED pose with the origin on its hinge. Re-import check all PASS: tris 420 / 950 /
  1,198 / 1,137 / 546 / 272 (= export copy = build table), root identity, one slot, one UV map, custom normals (worst
  0.029°), and the builder's local hinge offsets = `servicearm_kin` chain.
- **Builder** `Assets/Environment/Editor/ServiceArmBuilder.cs` (GateBuilder pattern; Tools > Labyrinth >
  ServiceArm: Apply Import Settings / Build ServiceArm / Verify ServiceArm): hero-mode import settings, textures
  (BaseColor / Emission sRGB, Normal map, Mask linear with alpha, mipmaps, ASTC 6x6 / 4x4 normal, max 2048), URP Lit
  material `M_LAB_HERO_ServiceArm` as the Gate's, hierarchy `HERO_ServiceArm` > Mount (0, 4.00, 5.30) > Turret >
  UpperArm > Forearm > Wrist > ToolHead, `ServiceArmDriver` on the root with the joints wired, the arm left in the
  working pose, prefab `HERO_ServiceArm.prefab`. **No colliders** (decision): the arm is ≥ 2.04 m up over the docked
  drone, outside the teleport floor and out of reach, and nothing in the sequence needs to hit it; Verify fails on
  any collider. Verify: hierarchy, tris, local positions, material, keywords, texture settings, driver timings, the
  working-pose tool tip at (0, 2.04, 4.69) ± 5 mm, and the stowed layer from the renderer bounds.
- **Runtime** `Assets/Scripts/Facility/ServiceArmDriver.cs` (namespace LabyrinthVR.Gameplay): working pose
  (turret 21.14°, shoulder 81.18°, elbow −117.79°, wrist −53.38°), idle (turret ±10°, wrist ±15°, each 0.6/0.4 of
  two sines at 0.21 + 0.34 Hz / 0.27 + 0.43 Hz with random phases, so the sum never exceeds the swept amplitude and
  never visibly repeats; tool spin 90°/s varied ±35 % by a 0.23 Hz sine; 1.5 s fade-in), fold to the stowed pose
  (`RequestFold()` = the terminal button: starts after 2.5 s; `BeginFold()` = now; 2.0 s, smoothstep per joint; roll
  unwinds the short way), events `onFoldStarted` / `onStowed` (FacilitySequence arms the lever from `onStowed`), all
  values public; context menus "Fold Now" / "Reset To Working". FacilitySequence is not written (§10).
- C# parsed with a C# grammar (tree-sitter-c-sharp, GateBuilder as control): no syntax errors. Unity APIs written
  against GateBuilder; **not compiled**.

### To verify in Unity (H3b)
1. Recompile; Tools > Labyrinth > ServiceArm: Apply Import Settings; commit the `.meta` files (check `git diff`).
2. Build ServiceArm in BasicScene, read the Verify report (expect RESULT: PASS); the scene is not saved by the builder.
3. EXPORT_CONTRACT hero-mode comparison on one part (vertex / normal / tangent), as noted there for the first v3 hero.
4. Play Mode: idle looks calm and non-repeating; ServiceArmDriver "Fold Now" folds in 2.0 s to the flat layer;
   `RequestFold()` waits 2.5 s; no part passes through another (the offline sweep says so; confirm by eye).
5. Docked drone: re-read `DroneAI2` live (docking pose −28.3°, (−0.032, 2.000, 4.754)) and confirm the tool tip
   clears the top (offline 54 mm; rule ≥ 50 mm). The clearance sweep used the drone rebuilt from `drone_low.fbx` +
   DroneBaseline, not a live read.
6. Ceiling lights: keep them out of the stowed footprint x −0.20 … 0.29, z 5.10 … 6.36.
7. Quest: draw calls (6 renderers, 1 material), texture memory at 2048 vs 1024, emission brightness of the strips.

### Open (not done here)
- **Cradle v2 clearance:** the Cradle v2 meshes are not in the repo, so the arm was not swept against the cradle.
  The cradle sits below the drone (yoke arms around the body), the arm's lowest point is the tool tip at y 2.04 over
  the drone's top — expected clear, **not checked**.
- FacilitySequence wiring (terminal button → `RequestFold`, `onStowed` → lever armed).

## Owner decision 2026-11-03 — HERO_SPEC §4 change to apply at merge

Owner review of H2 vs the concept: "the arm reads thin and spindly; the concept is chunky". Decision: **the stowed
layer may go down to y 3.60** (0.12 above the drone volume top 3.48; was 3.77). HERO_SPEC is read-only for this
branch, so apply these §4 changes when merging:
- Stowed pose: "One flat layer at **y 3.60 … 3.95**, 0.12 above the drone volume" (was 3.77 … 3.95, 0.29 above).
- Table: Turret hinge **(0, −0.07, 0)** (was −0.05), UpperArm shoulder **(0, −0.16, 0)** (was −0.12); UpperArm
  **0.12 × 0.16 × 1.00**, Forearm **0.10 × 0.14 × 0.90** (were 0.12 / 0.10 tall); ToolHead on the wrist 0.078 below
  its hinge. Widths and the X offsets 0.12 / 0.10 unchanged.
- Working pose: turret +21.14°, shoulder +78.61°, elbow −110.22°, wrist −58.39°, tip (0, 2.04, 4.69); reach
  shoulder → wrist 1.559 (available 1.90).
- Stowed footprint and the texture sheet: see H1b below.

## H1b / H2b — chunkier arm toward the concept (2026-11-03)

One look iteration on the owner's review (limited budget).
- **Stack:** plate 0.035 + adapter to 0.068, turret hinge 0.07 under the ceiling, shoulder axis 0.16 under the turret:
  ceiling → shoulder 0.23 m (concept ≈ 0.25, was 0.17).
- **Links:** upper arm 0.12 × 0.16, forearm 0.10 × 0.14 (were 0.12 / 0.10 tall). The upper arm's root is now its full
  r 0.08 end (8 mm under the turret hub; the lug / ramp of H1 is gone).
- **Joints:** the concept's big shoulder housing on −X (lobe r 0.10, reaching 0.125 fore and aft, outer cap r 0.068
  with 8 bolts) and the big slotted cap r 0.064 × 8 mm on the shoulder (+X, camera side; 18 mm touched the stowed forearm); elbow disc r 0.095 with an 8-bolt
  circle (r 0.072) and hub r 0.045 (was r 0.06); upper-arm elbow cap r 0.085; wrist knuckle r 0.065, cap r 0.046
  (6 bolts), neck r 0.044 (r 0.05 grazed the forearm side). Link widths stay 0.12 / 0.10 (the 0.12 / 0.10 offsets would otherwise close the gaps).
- **Cables:** the thick corrugated conduit (Ø 24 mm) plus a thin black cable (Ø 11 mm) beside it on the link tops,
  both under wider band clamps; the thin cable follows the thick one's curve 24 mm to the side (6.5 mm slot between them) and fades into it
  0.10 m before each swivel, so both still meet on the hinge axes.
- **Working pose:** same tool tip; with the lower shoulder the elbow bends more (interior 110°, was 118°). More bend
  would need *longer* links (the tip is fixed, so shorter links straighten the arm); the concept's ~54° Z is not
  reachable with HERO_SPEC lengths — the concept pose stays a render-only comparison pose.
- **UVs:** one **1024** sheet (owner), 512 px/m on everything except the two cable tubes (256 px/m: long, thin, seen
  from metres away); padding 4 px / border 2 px at 1024 (= ASSET_RULES 8 / 4 at 2048); islands capped at 1.9 m so the
  1.27 m-long upper-arm wall strip splits. Packing 56 % of the sheet.
- **Results:** 5,254 tris (Mount 420, Turret 936, UpperArm 1,621, Forearm 1,441, Wrist 564, ToolHead 272); topology,
  shading, UV checks PASS. Texture checks PASS at 1024 (AO black, PBR, rust 6.9 %, emission only in the strips,
  seams: samples on bolts / grooves are skipped (relief, not a bake mismatch); ≤ max(3, 5 %) of the rest may exceed
  6° — the remaining ones sit on shell contact edges (housing cap rim, turret top) where the bevel shader bends the
  normal; all printed by the check). FBX re-export + re-import check PASS. Builder / driver numbers updated
  (local positions, tris, stowed layer 3.60, MaxTextureSize 1024, working angles); C# parses, not compiled.
- Renders: `Documentation/Media/servicearm/servicearm_h2b_*` (vs_concept, vs_concept_side, working_34,
  working_player, closeup_elbow, closeup_tool, stowed_34, stowed_close, maps).
