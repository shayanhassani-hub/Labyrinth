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
| 1 | Square ceiling plate, chamfered edge | geometry (0.40 × 0.025, 45° corner clips 12 mm, 6 mm chamfer) | | |
| 2 | 4 hex nuts + stud ends on the plate underside | geometry (30 mm AF × 16 mm) | | |
| 3 | Washers under the nuts | normal map (3 mm) | | |
| 4 | Octagonal adapter under the plate | geometry (frustum 0.34 → 0.28, 23 mm) | | |
| 5 | Adapter side ports (rectangular slot, oval slot) | normal map + dark texture | | |
| 6 | Small bolts on the adapter | normal map | | |
| 7 | Turret bearing disc Ø 0.26 × 0.07 | geometry (32 sides, 6 mm chamfers) | | |
| 8 | Turret groove ring | normal map | | |
| 9 | Round boss on the turret side | geometry (Ø 44 mm, 23 mm proud) | | |
| 10 | Shoulder housing / bracket | geometry (cheek on −X, rounded r 0.055) | | |
| 11 | Shoulder slotted cap | geometry (Ø 72 mm × 15 mm); slot normal map | | |
| 12 | Bracket outer cap | geometry (Ø 80 mm) | | |
| 13 | Cable connector box with gland | geometry (48 × 42 × 44 mm + gland) | | |
| 14 | Link bodies with chamfered edges | geometry (6 / 5 mm chamfers), rounded ends on the hinges | | |
| 15 | Link end collars (wider bands) | normal map + texture (the step is < 15 mm) | | |
| 16 | Side panel: groove outline, raised plate with stepped edge | normal map | | |
| 17 | Panel bolts, link-end bolts | normal map | | |
| 18 | Cyan light strip on each link side | emission + normal map (slot < 15 mm) | | |
| 19 | Elbow: big disc with 8-bolt ring and centre cap | geometry disc r 0.06 × 17 mm, cap r 0.03 × 15 mm; bolts normal map | | |
| 20 | Wrist: rounded knuckle with small cap | geometry (cap Ø 64 mm) | | |
| 21 | Wrist neck with ring grooves | geometry (Ø 84 mm); grooves normal map | | |
| 22 | Tool collar (steel) | geometry (Ø 88 mm × 35 mm) | | |
| 23 | Ochre tool block with the side notch | geometry (0.14 × 0.10 × 0.135, notch 35 mm) | | |
| 24 | Tool bolts, soot / grime on the ochre | normal map, texture | | |
| 25 | Steel pin | geometry (Ø 36 × 40 mm) | | |
| 26 | Flexible conduit along the arm | geometry tube Ø 22 mm (8 sides) on clips; corrugation normal map | | |
| 27 | Cable clips (band clamps) | geometry (34 × 16 mm arches) | | |
| 28 | Slack loops at the joints | geometry: over the elbow and wrist ends, joined on the hinge axes at swivels | | |
| 29 | Second, thinner cable beside the conduit | left out at H0 (see open points) | | |
| 30 | Rust: edges, bottoms, around bolts, panel corners, streaks | texture (rust rule) | | |
| 31 | Edge wear to steel, grime, scratches | texture | | |

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
