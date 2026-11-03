# LeverStand — build notes (Hero 02b, workflow v3)

Cloud build, 2026-11-03, branch `cloud/hero-leverstand`. Sizes, pivots, motion and clearances: HERO_SPEC §6 (and §8
for the labyrinth panel). Concept (owner, Gemini): `Documentation/References/LeverStand/leverstand_front.jpg` (3/4,
master for look and detail) and `leverstand_ortho_side.jpg` (proportions and depth).
Scripts: `Tools/Blender/heroes/leverstand.py` (generator), `leverstand_check.py` (checks, renders, concept
comparison), `leverstand_tex.py` (H2 bake), `leverstand_export.py` (H3a FBX). Renders: `Documentation/Media/leverstand/`.

Environment: bpy 5.2.2 from PyPI in a venv with a small launcher (both outside the repo, as for the Gate G2b–G3a).
`D:/AI_Labyrinth` paths in the LeverStand scripts go through the environment variable `LAB_AI_ROOT` (default
`D:/AI_Labyrinth`, so the scripts run unchanged on the owner's machine).

## Frame and placement
- Authored in **stand-local** Unity coordinates. The origin is on the floor under the pedestal centre; **+Z local is
  the front** (cyan strip). Placed at world (0.85, 0, 0.60) with yaw 180, so local +Z faces world −Z, toward the
  player. Local +X = world −X, toward the labyrinth.
- The review .blend holds the stand at the Blender origin without the yaw. The checks move the labyrinth panel into
  this frame.
- **Lever angle convention:** HERO_SPEC "rest +30° (away from the player), pulled −30°" holds in **world** axes. In the
  stand's yawed frame the same motion is **local Euler X −30° (rest) … +30° (pulled)**, because positive local X tilts
  the lever toward local +Z, which faces the player. The lever is modelled upright (0° = middle of the travel). The
  80 % trigger is at local +18°.

## Camera match (concept views)
Fitted to six landmarks on the concept's pedestal corner edges (top and bottom of the three visible corners),
6 px RMS. The fit also estimated the concept's footprint at about 0.36 × 0.40 m (at 0.95 m tall); the side view reads
~0.44 m deep.
- 3/4 (`leverstand_front.jpg`): camera at stand-local (−2.555, 1.608, 3.442), yaw 143.0°, pitch −13.0°, **62 mm**
  lens (36 mm sensor width).
- Side (`leverstand_ortho_side.jpg`): **orthographic**, looking +X at the −X side (front on the image's left),
  centre height 0.634, ortho scale 2.40 (image width; taken from the concept's 0.95 m pedestal height).
- `leverstand_<stage>_vs_concept.jpg`: renders on the left, concept on the right (3/4 top row, side bottom row).
  `_top.jpg` is the same pair cropped to the housing. The lever is shown **pulled**, the pose the concept shows (it leans
  toward the front).

## Feature inventory
Method: G = geometry (≥ 15 mm, or silhouette), N = normal map, T = texture (BaseColor/Mask/Emission). Ticks: H1 =
modelled and checked, H2 = textured and checked.

| # | Feature (concept) | How | H1 | H2 |
|---|---|---|---|---|
| 1 | Pedestal block, vertical corner chamfers | G: 0.30 × 0.95 × 0.30, 20 mm chamfers (spec) | ✓ | |
| 2 | Plinth with a 45° bottom bevel | G: 18 mm chamfer; floor face not built | ✓ | |
| 3 | Groove between plinth and body, between body and ledge | N (flush in geometry) | | |
| 4 | Cap slab, chamfered top edge | G: 35 mm cap, 12 mm top chamfer | ✓ | |
| 5 | Black/yellow hazard band under the cap | G: 0.06 band (spec), recessed 6 mm (kept as geometry for the silhouette step); T: ochre/black 45° stripes, worn | ✓ | |
| 6 | Ledge under the band | N: groove lines (flush) | | |
| 7 | Recessed field between corner posts, all four faces | G: 18 mm deep, sloped walls | ✓ | |
| 8 | Front: I-shaped ("dogbone") raised plate | G: 10 mm proud, 45° transitions (Gate plate standard) | ✓ | |
| 9 | Light channel in the plate's waist | G: 18 mm deep, polymer | ✓ | |
| 10 | Cyan light strip | G: 8 mm proud of the channel floor; T: emission sRGB 70 170 255 | ✓ | |
| 11 | Sides: three plates, stepped (diagonal) dividers | G: 10 mm proud, 10 mm gaps; divider heights from the ortho | ✓ | |
| 12 | Bolts: I-plate 4, side plates 4 per face, back plate 4, cap top 4, housing front 2 and sides 2 each | N (heads, washers) + T | | |
| 13 | Small edge bevels on every panel edge | N (1.5 mm bevel bake) | | |
| 14 | Housing: low front, sloped front, flat top, rounded back top edge, chamfered sides | G: 0.22 × 0.08 × 0.16 (spec), 8 mm perimeter chamfer, 15 mm back fillet (3 segments) | ✓ | |
| 15 | Slot with a dark interior | G: 42 × 88 mm opening, pocket 65 mm deep (polymer) | ✓ | |
| 16 | Slot lip / frame | N | | |
| 17 | Lever shaft (steel) | G: Ø 0.03 12-gon (spec), chamfered bottom end in the pocket | ✓ | |
| 18 | Ochre grip, rounded top, collar at the bottom | G: Ø 0.05 × 0.10 16-gon (spec), bottom chamfer, 2-ring dome; N: longitudinal ribs and collar line | ✓ | |
| 19 | Lamp base collar | G: Ø 40 × 10 mm 12-gon, polymer | ✓ | |
| 20 | Amber lamp glass | G: separate part `Lamp_01`, Ø 26 mm; T: emission sRGB 240 150 60; runtime: MaterialPropertyBlock | ✓ | |
| 21 | Wire cage | G: 4 bars 3 × 3 mm, octagonal top ring, cross over the dome (see-through: cannot be a normal map) | ✓ | |
| 22 | Rust: edges, corners, plinth, round some bolts, panel corners, run-off streaks, rusty band | T (STYLE_GUIDE rust rule, 5–15 % of the paint, more toward the bottom) | | |
| 23 | Edge wear to bare steel, hairline scratches, grime | T (Gate G2c rules) | | |
| 24 | Back face (not in the concept) | G: same field and one plain plate; N: 4 bolts | ✓ | |

Left out or changed (with the reason):
- The concept's chunkier pedestal (≈ 0.44 m) and bigger housing (≈ 0.21 deep × 0.12 tall at concept scale): HERO_SPEC
  sizes win; see "Deviations".
- The concept's thin shaft (≈ 15 mm): the spec sets Ø 0.03.
- The concept places the slot in the low front step, with the lever leaning toward the front. That works for a lever
  that only leans forward. The spec's ±30° swing needs a slot that is open on both sides of the hinge, so the slot sits
  on the flat top with the hinge 35 mm below it.

## Deviations from the concept (spec wins, or clearance)
1. **Pedestal width stays 0.30** (concept ≈ 0.44). At 0.30 the pedestal's −X face is exactly 0.15 from the labyrinth
   panel's +X edge (x 0.70 vs 0.55), so any widening breaks the HERO_SPEC §6/§8 clearance. The tilt check is in H1.
   Depth was kept at 0.30 too. Making it deeper (to ~0.42) would keep the 0.15 x-gap, but it is a spec size: open
   question for the owner.
2. Housing at the spec's 0.22 (wide) × 0.08 (tall) × 0.16 (deep). The concept's housing is deeper than wide and
   ~50 % taller.
3. Slot on the flat top, centred on the hinge (see above). Lamp on the opposite back corner of the top (concept:
   behind the slot), 63 mm clear of the lever's swing plane.
4. Lever: rest leans away from the player (spec). The concept shows it leaning toward the front, i.e. our pulled pose;
   the concept comparisons use that pose.

## H0 — blockout (done)
`leverstand.py -- blockout` builds the primary forms at spec size: pedestal with corner chamfers, recessed band, cap,
housing profile, slot plate, lamp, lever, strip. Comparison: `leverstand_h0_vs_concept.jpg`, `_top.jpg`.
Findings: camera angle and framing match. Silhouette differences are the deviations above (narrower pedestal, smaller
housing). The concept's stack heights (cap 35 mm, band 60–70 mm, ledge 30 mm, plinth 65 mm) and side-panel divider
heights were measured on the ortho view and carry into H1.

## H1 — model (done)
Generator `leverstand.py -- build` (review file `D:/AI_Labyrinth/Blender/Source/Heroes/LeverStand/LAB_HERO_LeverStand_v1.blend`,
in the cloud under `LAB_AI_ROOT`). Gate construction: `gate.GateMesh` (material + face kind per face), flat regions with
holes filled quad-first, hard edges by face kind (flat | flat > 30°, chamfer | flat > 50°, chamfer | chamfer > 15°,
round | round smooth) = UV seams, face-area weighted normals with face influence (flat strong, round medium, chamfer
weak), `cradle_v2_uv` unwrap and packing.

| Part | Origin (stand-local) | Motion | Tris |
|---|---|---|---|
| `LAB_HERO_LeverStand_Body_01` | (0, 0, 0) floor centre | static | 836 |
| `LAB_HERO_LeverStand_Lever_01` | (0.041, 0.995, −0.010) hinge | local X −30 (rest) … +30 (pulled), trigger +18 | 206 |
| `LAB_HERO_LeverStand_Lamp_01` | (−0.055, 1.040, −0.035) glass base | emission only | 58 |

Total **1,100 tris** (no LOD needed).
- Pedestal: 0.30 × 0.95 × 0.30, 20 mm corner chamfers, 18 mm bottom bevel, band 0.855–0.915 recessed 6 mm,
  cap with a 12 mm top chamfer. Fields 18 mm deep (u ±0.105, v 0.08–0.805), plates 10 mm proud. Front I-plate (top/bottom
  ±0.093, waist ±0.040, 45° transitions), light channel 40 × 425 mm, 18 mm deep, strip 22 × 375 mm. Side plates with
  stepped dividers (front 0.679 / 0.228, back 0.589 / 0.325, diagonal between 25 % and 62 % of the width from the front),
  10 mm gaps. Back: one plain plate.
- Housing: 0.22 × 0.08 × 0.16. Front face 45 mm, slope up to the top at z 0.05, flat top, 15 mm back fillet, 8 mm
  perimeter chamfer. Slot 42 × 88 mm, pocket floor at y 0.965.
- Lamp: base Ø 48 × 10 mm, glass Ø 32 × 30 mm with a dome (`Lamp_01`), cage of 4 bars 3 mm, octagonal ring, cross.
  The lamp was enlarged after the H1 comparison: the first one (glass Ø 26) read thinner than the concept.
- Lever: shaft Ø 30 12-gon, grip Ø 50 × 100 16-gon with a 2.5 mm bottom chamfer and a 2-ring dome. The shaft's
  bottom end in the pocket (11 faces) is never visible in any pose and was deleted (ray test, 96 directions, rest /
  upright / pulled).

**Checks** (`leverstand_check.py -- topo`, `-- clearance`), all PASS:
- Topology: 0 n-gons, non-manifold, loose, duplicate or zero-area elements; 0 bow-tie or concave quads; 0 winding
  faults; planarity 0 quads over 2 mm. Shading: 0 flat faces with a corner normal > 0.5° off (worst 0.03°).
  Deliberate open borders: pedestal floor contact, housing on the cap, lamp glass on the base, shaft end in the pocket.
- Hidden faces: 0 on every part over the three lever poses.
- UVs: **one 1024 set** (ASSET_RULES: the asset fills a 1024 sheet at hero density; at 2048 it would be 1,160 px/m
  with half the sheet empty). **580 px/m** (+13 % over the 512 target; the packer uses the whole sheet). The lever is
  at 2× (1,161 px/m, hand-held like the labyrinth handle), and downward faces and the slot pocket at ½. 228 islands,
  padding ≥ 8 px, border 5 px, no overlaps, packing 49.6 %. Checker render: even, square checks.
- Lever sweep −30 … +30° (1° steps) against the body and the lamp: min gap **6.1 mm** (slot ends at both extremes).
  Slot: shaft edge 37.5 mm from the hinge at the top face, slot ends at 44 mm → 6.5 mm clear.
- Labyrinth panel (HERO_SPEC §8 v2 geometry: plate 1.05 × 0.025, rim 0.05 × 0.08, handle bar), pivot (0.025, 1.00,
  1.225): level, the pedestal face is **150.0 mm** from the panel's +X edge (spec), min surface gap 162 mm. Tilt cone
  0–12°, every 15° of azimuth, lever at rest and pulled: no contact, **min 145.5 mm** (azimuth 330°, 12°). Below
  150 mm because the 80 mm rim swings ~5 mm outward when the edge dips; §8 assumes the tilt moves the edge only up
  and down. Gate kept at "spec 0.15 level + no contact ≥ 100 mm"; **open question** for the owner (move the stand
  +X by 5 mm, or accept).
- Drone volume (released): stand world box x 0.70–1.00, y 0–1.28, z 0.45–0.78, outside. Labyrinth protected
  cylinder: inside by design (§6 exception). Origin 1.04 m from the operating position (spec 1.04).
- Reach (player at the operating position, right shoulder estimated at (0.18, 1.40, 0)): grip centre 0.99 m away at
  rest, 0.81 m pulled; one step (0.26–0.44 m) brings it to a comfortable 0.55 m, as the spec intends.

Renders (`Documentation/Media/leverstand/`): `leverstand_h1_vs_concept.jpg`, `_top.jpg`, `leverstand_h1_{room, 34,
front, side, side_pulled, top, lever, lamp, base}.jpg`, `leverstand_h1_shading_{34, top, lever, base}.jpg`,
`leverstand_h1_wire_{34, top}.jpg`, `leverstand_h1_checker_{34, top}.jpg`, `leverstand_h1_uv_layout.jpg`. Workbench
needs OpenGL, which the cloud container lacks, so the wire and checker renders use Cycles.
