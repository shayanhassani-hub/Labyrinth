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
| 1 | Pedestal block, vertical corner chamfers | G: 0.30 × 0.95 × 0.30, 20 mm chamfers (spec) | | |
| 2 | Plinth with a 45° bottom bevel | G: 18 mm chamfer; floor face not built | | |
| 3 | Groove between plinth and body, between body and ledge | N (flush in geometry) | | |
| 4 | Cap slab, chamfered top edge | G: 35 mm cap, 12 mm top chamfer | | |
| 5 | Black/yellow hazard band under the cap | G: 0.06 band (spec), recessed 6 mm (kept as geometry for the silhouette step); T: ochre/black 45° stripes, worn | | |
| 6 | Ledge under the band | N: groove lines (flush) | | |
| 7 | Recessed field between corner posts, all four faces | G: 18 mm deep, sloped walls | | |
| 8 | Front: I-shaped ("dogbone") raised plate | G: 10 mm proud, 45° transitions (Gate plate standard) | | |
| 9 | Light channel in the plate's waist | G: 18 mm deep, polymer | | |
| 10 | Cyan light strip | G: 8 mm proud of the channel floor; T: emission sRGB 70 170 255 | | |
| 11 | Sides: three plates, stepped (diagonal) dividers | G: 10 mm proud, 10 mm gaps; divider heights from the ortho | | |
| 12 | Bolts: I-plate 4, side plates 4 per face, back plate 4, cap top 4, housing front 2 and sides 2 each | N (heads, washers) + T | | |
| 13 | Small edge bevels on every panel edge | N (1.5 mm bevel bake) | | |
| 14 | Housing: low front, sloped front, flat top, rounded back top edge, chamfered sides | G: 0.22 × 0.08 × 0.16 (spec), 8 mm perimeter chamfer, 15 mm back fillet (3 segments) | | |
| 15 | Slot with a dark interior | G: 42 × 88 mm opening, pocket 65 mm deep (polymer) | | |
| 16 | Slot lip / frame | N | | |
| 17 | Lever shaft (steel) | G: Ø 0.03 12-gon (spec), chamfered bottom end in the pocket | | |
| 18 | Ochre grip, rounded top, collar at the bottom | G: Ø 0.05 × 0.10 16-gon (spec), bottom chamfer, 2-ring dome; N: longitudinal ribs and collar line | | |
| 19 | Lamp base collar | G: Ø 40 × 10 mm 12-gon, polymer | | |
| 20 | Amber lamp glass | G: separate part `Lamp_01`, Ø 26 mm; T: emission sRGB 240 150 60; runtime: MaterialPropertyBlock | | |
| 21 | Wire cage | G: 4 bars 3 × 3 mm, octagonal top ring, cross over the dome (see-through: cannot be a normal map) | | |
| 22 | Rust: edges, corners, plinth, round some bolts, panel corners, run-off streaks, rusty band | T (STYLE_GUIDE rust rule, 5–15 % of the paint, more toward the bottom) | | |
| 23 | Edge wear to bare steel, hairline scratches, grime | T (Gate G2c rules) | | |
| 24 | Back face (not in the concept) | G: same field and one plain plate; N: 4 bolts | | |

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
