# Terminal (Hero 02) — build notes

Cloud build, started 2026-11-03 on branch `cloud/hero-terminal`, hero workflow v3 (ASSET_RULES), the Gate as the
reference implementation. Sizes, pivots and motion: `HERO_SPEC.md` §5 (read-only here; proposed changes at the end).
Concept (owner, Gemini): `Documentation/References/Terminal/terminal_front.jpg` (3/4, master for look and detail),
`terminal_ortho_{front,top,side}.jpg` (proportions). The owner was away; every decision below was taken without
asking and is written down with its reason.

## Setup (outside the repo)
- `bpy==5.2.2` from PyPI (= Blender 5.2.2 LTS) in a venv (`/home/user/bpyvenv`, Python 3.13), plus `scipy`
  (half-space intersection), `shapely` (polygon difference), `pillow` (holo UI texture, composites).
- Launcher `/home/user/blender_run.sh <script> -- <args>`: runs the venv Python from a scratch folder, so the
  scripts' `D:/AI_Labyrinth/...` paths land in scratch, as in the Gate cloud sessions.
- Scripts (repo): `Tools/Blender/heroes/terminal.py` (generator), `terminal_check.py` (checks, concept-matched and
  review renders), `terminal_tex.py` (H2 bake), `terminal_holo.py` (holo UI texture), `terminal_export.py` (H3a).
  `terminal.py` imports the Gate / Cradle helpers (`gate.GateMesh`, `cradle_v2`, `cradle_v2_uv`) without changing them.

## Coordinates and names
- Terminal-local: x across, **+X = the player's left** when they face the wall, y up, z from the back wall's inner face
  into the room. World = local + (−2.2, 0, −2.0), yaw 0 (HERO_SPEC §5).
- **Pillar_L / Pillar_R are named from the player's view** (as in the concept's front view): Pillar_L is at +X (world
  x −1.0 … −1.3, the room side) and carries the beacon; Pillar_R at −X (world −3.1 … −3.4, 0.6 m from the side wall).

## Parts (meshes)
| Part | Origin (Unity world) | Motion / switching | Why separate |
|---|---|---|---|
| `LAB_HERO_Terminal_Body_01` | (−2.2, 0, −2.0) = terminal origin | static | both pillars, desk, lower body, display base bar, button guard, beacon base + cage, the 3 always-cyan strips, pillar light strips: one mesh, one draw |
| `LAB_HERO_Terminal_Button_01` | cap top centre at rest | press 0.015 along the desk normal (into the desk) | moving |
| `LAB_HERO_Terminal_Indicators_01` | terminal origin | cyan → red on Armed (MaterialPropertyBlock) | switching: the 3 strips of the player's-right group |
| `LAB_HERO_Terminal_Beacon_01` | lens base centre | off → red on Armed (MaterialPropertyBlock) | switching |
| `LAB_HERO_Terminal_Display_01` | display bottom-edge centre | static, own transparent material | the one allowed second material |

## Decisions
- **Paint: gunmetal (STYLE_GUIDE 90 104 115)**, as on the Gate. The concept's fully lit faces sample at 95 100 110
  (pillar tops, ortho top view) and its desk top at 124 138 144 (lit + teal reflection); the gunmetal is within ~5
  levels of the pillar tops and keeps the hero family consistent. Charcoal (structure) would be too dark for the concept.
- **Trim clearance:** the room's floor trim runs along the back wall (z 0 … 0.05 local, y 0 … 0.15). All plinths stop
  at z 0.055 and are 0.16 high (pillar and body backs above them touch the wall), so the terminal stands flush on the
  wall with a notch over the trim — no gap at the wall, no intersection.
- **Desk 50 mm behind the pillar fronts** (desk front edge z 0.75, concept top view: the pillars stand proud of the
  desk). The desk heights stay at the spec values (0.92 front edge, 1.05 back, 15°) — the slope runs from z 0.75 back to
  z 0.265, a flat shelf behind it carries the display base bar.
- **Lower body front 100 mm behind the desk edge** (z 0.65): toe / knee recess for a standing player, and the concept's
  deep shadow line under the desk slab.
- **Switching indicators:** the player's-right group (−X) turns red on Armed, the beacon is on the player's left
  pillar: the alarm reads across the whole console. (The spec does not say which three; open question below.)
- **Switching parts via MaterialPropertyBlock, no runtime material copies:** Indicators_01 and Beacon_01 are separate
  meshes that use the same hero material; their emission-map texels are white, and a MaterialPropertyBlock sets
  `_EmissionColor` (cyan in Standby, red when Armed; beacon black → red). The Body's emission map carries its own
  colours (cyan strips) with `_EmissionColor` = white × intensity on the material.
- **Button guard** with a notch toward the player's front-right (as in the concept's top view); the cap stands 13 mm
  above the collar at rest and 2 mm below it when pressed (guarded, still clearly a push button).

## Feature inventory (concept → model)
Method: **G** = geometry (≥ 15 mm, depth rule), **N** = normal map (H2 bake), **T** = texture (colour / mask), **–** = left out
(reason given). Status: H0 = in the blockout, H1 = modelled, H2 = textured.

| # | Feature (concept) | Where | Method | H0 | H1 | H2 |
|---|---|---|---|---|---|---|
| P1 | Chunky pillar blocks, chamfered vertical edges (plan octagon: big outer chamfers, small inner) | both pillars | G (half-space block: outer 40 mm, inner-front 8 mm) | ✓ | ✓ | ✓ |
| P2 | Large top-front chamfer, smaller top-side chamfers | pillar tops | G (150 / 30 mm) | ✓ | ✓ | ✓ |
| P3 | Top cap seam under the top-front chamfer | pillar fronts | G (55 mm cap band above the field) + N (groove) | | ✓ (band) | ✓ (groove) |
| P4 | Base band | pillars, lower body | G (plinth 0.16 high, 15 mm inset; also the trim notch) | ✓ | ✓ | ✓ |
| P5 | Front: recessed field with a raised "dog-bone" plate (wide top / bottom, narrow waist, 45° tapers) | pillar fronts | G (field 18 mm, plate 12 mm proud) | | ✓ | ✓ |
| P6 | Vertical cyan light strip in the plate's waist | pillar fronts | G (slot 15 mm) + emission | | ✓ | ✓ |
| P7 | Hazard stripes on the outer vertical chamfers (front and back) | pillars | T (ochre / black 45°), faces split at y 0.22 / 1.04 | ✓ | ✓ (faces) | ✓ |
| P8 | Outer side: framed field, three panels with stepped (Z) dividers | pillar outer sides | G (field 18 mm, panels 10 mm proud) | | ✓ | ✓ |
| P9 | Inner side: big plate with a cut corner | pillar inner sides | – left plain: at spec heights only ~0.2 m of it shows above the desk | | – | – |
| P10 | Bolts at plate / panel / frame corners | everywhere | N (hex heads, washers) | | | ✓ (70 bolts) |
| P11 | Pillar top: corner bolts, seams | pillar tops | N | | | ✓ (bolts) |
| P12 | Rust on edges, corners, bottom, streaks; worn hazard paint | everywhere | T (STYLE_GUIDE rust rule) | | | ✓ (5.3 %) |
| B1 | Beacon base (black) | Pillar_L top | G (Ø 0.10 × 0.022, 16 seg) | ✓ | ✓ | ✓ |
| B2 | Red beacon lens (dome) | Pillar_L top | G, own mesh (Ø 0.08, dome) | ✓ | ✓ | ✓ (white emission, MPB) |
| B3 | Wire cage round the lens | Pillar_L top | G (4 posts 6 mm, ring, top cross) | | ✓ | ✓ |
| B4 | Red glow halo around the beacon | – | – (Unity bloom / a light in the lighting pass, not geometry) | – | – | – |
| D1 | Desk slab: thick front edge, top-front chamfer | desk | G (50 mm edge, 8 mm chamfers) | ✓ | ✓ | ✓ |
| D2 | Deep shadow under the desk slab (overhang over the lower body) | desk | G (100 mm overhang) | ✓ | ✓ | ✓ |
| D3 | Framed desk panel: border with 45° cut ends, five panels | desk top | N (grooves) | | | ✓ |
| D4 | Bolts at the desk panel corners | desk top | N | | | ✓ |
| D5 | 6 indicator slots with cyan strips (2 × 3) | desk top | G (slots 15 mm) + emission; 3 = Indicators_01 | | ✓ | ✓ |
| D6 | Button guard: flange, thick collar with a notch | desk centre | G (flange 8 mm, collar 35 mm, 24 seg) | ✓ (plain collar) | ✓ | ✓ |
| D7 | Red cap with chamfer, steel cup ring under it | desk centre | G (cap Ø 0.12, 24 seg) + T (steel cup floor) | ✓ | ✓ (cap) | ✓ (cup ring steel) |
| D8 | Display base bar / slot along the back | desk shelf | G (1.60 × 0.05 × 0.07) | ✓ | ✓ | ✓ |
| S1 | Transparent holo panel, glowing frame with corner tabs | display | own holo texture (≤ 1024) + transparent material | ✓ (quad) | ✓ (quad) | ✓ (holo texture) |
| S2 | Holo UI: room / drone wireframe, graphs, grid, data blocks | display | holo texture; no readable text | | | ✓ |
| L1 | Three recessed front panels | lower body | G (18 mm) | | ✓ | ✓ |
| L2 | Stepped divider: lower panel raised in the middle | lower body | G (panels 10 mm proud) | | ✓ | ✓ |
| L3 | Bolts at the lower panel corners | lower body | N | | | ✓ |
| C1 | Overall colour: blue-grey gunmetal, darker frames | all | T | | | ✓ |

## Deviations from the concept (spec wins)
| Concept | Model | Reason |
|---|---|---|
| Squat: desk ≈ half the pillar height above the floor, pillars ≈ 0.84 high relative to a 2.4 m width | Desk 0.92 … 1.05, pillars 1.25 (spec) | HERO_SPEC §5 heights for a standing VR player (owner's brief) |
| Pillars ≈ 0.43 wide (18 % of the width) | 0.36 (owner, H2b; spec 0.30) | closer to the concept within the 2.40 footprint |
| Screen ≈ 2.2 : 1, ≈ 1.0 m wide relative | 1.50 × 0.85 (1.76 : 1), bottom 1.10, 8° lean (spec) | HERO_SPEC §5 |
| Pillars ≈ 0.72 deep, body set back from the wall | Pillars and body 0.80 deep, backs on the wall | spec footprint 2.40 × 0.80 |
| Thin base band | 0.16 plinth, 15 mm inset | the floor-trim notch needs 0.155; also a toe recess |
| Desk slab slightly wider than the gap, tucked into the pillar chamfers | desk spans exactly between the pillars | clean junction (shared vertices, no hidden faces) |

## Stage log
### H0 — blockout (2026-11-03)
- `TERMINAL_DETAIL=0 terminal.py` → main forms only: pillar blocks (half-space), plinths with the trim notch, desk +
  lower body profile, display base bar, guard ring, cap, beacon base and lens, display quad.
- Concept cameras: `terminal_check.py -- concept h0`. Four cameras: 3/4 perspective (azimuth 22° to the player's right,
  elevation 15°, 50 mm; estimated from the concept's pillar face ratio 210 : 140 px → tan az = 0.40, and its top-face /
  front-face ratio → el ≈ 13–15°) and orthographic front, top, side (side from the player's right, as in the concept:
  front on the left). Each camera is fitted so the model's projected bounding box sits in the concept's terminal box
  (same floor line, centred; the spec model is taller, so it fits the height and comes out narrower). Composites:
  `Documentation/Media/terminal/terminal_h0_vs_concept.jpg` (left render, right concept; rows 3/4, front, top, side).
- Read from H0: the layout matches (beacon left, button centre, desk set back, deep under-desk shadow, hazard bands on
  the outer chamfers); the differences are the spec proportions listed above (taller pillars and desk, slimmer pillars,
  taller screen).

### H1 — model (2026-11-03)
`terminal.py` (default `TERMINAL_DETAIL=1`) → review file `D:/AI_Labyrinth/Blender/Source/Heroes/Terminal/LAB_HERO_Terminal_v1.blend`.

| Part | Tris | Faces | UV islands | Notes |
|---|---|---|---|---|
| Body_01 | 1,670 | 722 quads, 226 tris (flat regions only), 0 n-gons | 443 | open borders = deliberate: backs on the wall, floor contacts, the body ↔ pillar cut |
| Button_01 | 140 | 70 quads | 3 | 24 segments, 3 mm top chamfer |
| Indicators_01 | 30 | 15 quads | 15 | 3 strips (top + walls; they sit on the slot floors) |
| Beacon_01 | 112 | 48 quads, 16 tris (dome apex fan) | 2 | 16 segments, open bottom on the base |
| Display_01 | 2 | 1 quad | 1 (own 0–1 UV) | holo material |
| **Total** | **1,954** | | | no LOD needed (< 10k, ASSET_RULES) |

- **Construction:** pillars = half-space blocks (outer vertical chamfers 40 mm = hazard bands, inner-front 8 mm chamfer
  strip, top-front 150 mm (concept side view ≈ 170 mm), top sides 30 mm). Front: field 18 mm deep (frame 25 mm, cap band
  55 mm), dog-bone plate 12 mm proud with 45° tapers, light slot 22 × 400 mm, 15 mm deep, strip 10 mm below the plate.
  Outer sides: field 18 mm, three panels 10 mm proud, ~35° stepped dividers as in the concept's side view (top panel
  reaches lower at the back, bottom panel higher at the back, a 9 % strip of field along the front). Lower body: three
  fields 18 mm, two panels each, the lower one rising in the middle (concept). Desk: 6 slots 245 × 34 × 15 mm (strips
  7 mm below the surface), guard flange Ø 0.23 × 8 mm, collar Ø 0.20 / 0.15 × 35 mm with a 45° notch toward the
  player's front-right, cup floor and a hole Ø 0.123 for the cap's stroke. Display bar 1.60 × 0.05 × 0.07 on the shelf.
  Beacon: base Ø 0.10 × 22 mm, lens Ø 0.08 with a dome, cage of four 6 mm posts, a ring and a top cross (one
  plus-shaped piece 2 mm above the ring since H2: two crossing bars and coplanar tops left hidden, black-AO faces).
- **Shading:** every face has a kind (FLAT / CHAMFER / ROUND, as on the Gate). Hard edge + UV seam: flat | flat at any
  crease (> 1°, so the desk's 15° crease to the shelf is hard), round | flat > 30°, chamfer | flat > 50°, chamfer |
  chamfer > 15°. Face-weighted normals (Gate `apply_shading`).
- **UVs:** `cradle_v2_uv` unwrap with the hard-edge rule, packed at a fixed **512 px/m** (the densest fit would be
  583; ASSET_RULES target 512 ± 10 %), padding 8 px, border 4 px, **43.7 %** of the 2048 sheet. Undersides 0.5,
  plinths 0.6, Pillar_R's outer side (0.6 m from the room's side wall) 0.5. The display has its own 0–1 UV.
- **Hidden faces:** 29 deleted by construction (backs on the wall, floor contacts, the body's end caps inside the
  pillars, the cage post tops inside the ring), 6 of 115 ray candidates (plinth slots, cage bar ends) deleted by the ray test (96 directions, button at
  rest and pressed, room proxy: back wall, floor trim, side wall).

**Checks** (`terminal_check.py -- topo / clearance`), all PASS:
- Topology: 0 n-gons, non-manifold, loose, duplicate or zero-area elements, 0 winding faults, 0 bow-tie / concave
  quads, 0 corner normals against the custom normals; planarity: 0 quads with diagonals > 2 mm apart; shading: 0 flat
  faces with a corner normal > 0.5° off (worst 0.19°); nothing behind the wall or below the floor.
- UVs: padding ≥ 8 px, border 4 px, island density 512 px/m (256 / 307 on the reduced faces).
- Clearance sweep, button 0 … 15 mm along the desk normal in 11 steps: min gap cap ↔ body 1.5 mm (the hole wall),
  no contact; cap ↔ collar 15 mm radial; cap 13 mm above the collar at rest, 2 mm below it pressed; 40 mm above the
  cup floor (spec 0.04); 15 mm above the hole floor pressed.
- Room: footprint x −3.4 … −1.0, z −2.0 … −1.2 (spec), y 0 … 1.345 (beacon); backs on the wall face, 5.0 mm to the
  floor trim and the side wall; display top edge 32 mm from the wall (y 1.10 … 1.94, z −1.85 … −1.97).
- Spec sizes on the mesh: desk 0.92 at the front edge (chamfer 0.912 … 0.922), 1.05 at the back of the slope, 15°;
  pillars 1.25.
- Reach: shoulder (1.40 high) → button top 0.69 m standing 0.30 in front of the pillars, 0.57 m at 0.15 (comfortable
  arm reach 0.60–0.70 m); the button is also selectable with the ray.
- Motion: only the button moves (press); the indicators and the beacon switch colour (no motion). No part comes near
  the drone volume (terminal z ≤ −1.2, drone volume z ≥ 2.84).

**Renders** (`Documentation/Media/terminal/`): `terminal_h1_vs_concept.jpg` (four concept cameras, flat review
colours), `terminal_h1_room / 34 / button / beacon / pillar / lower`, `terminal_h1_shading_*` (flat grey: no gradients
on flat faces), `terminal_h1_wire_*`, `terminal_h1_checker_*`, `terminal_h1_uv_layout`. Workbench needs EGL, which
the headless container lacks: wire and checker renders are Cycles (wire = the Wireframe modifier copy, checker =
emission).

**Iteration against the concept:** the H1 side view showed the outer-side dividers stepping the wrong way and a top
chamfer about half the concept's; both fixed (dividers reversed, front strip added, top-front chamfer 90 → 150 mm),
front field cap band added for the concept's seam under the chamfer.

### H2 — textures (2026-11-03)
`terminal_tex.py` (Gate pipeline, `gate_tex` helpers reused unchanged) → one 2048 set
`Assets/Environment/Heroes/Terminal/Textures/T_LAB_HERO_Terminal_{BaseColor,Normal,Mask,Emission}.png` (Git LFS):
BaseColor sRGB, Normal OpenGL, Mask linear (R metallic, G AO, A smoothness), Emission sRGB colour. Baked on the
export-identical triangulated lows (Body, Button, Indicators, Beacon), Cycles CPU, 4 cores: full bake 13.3 min
(pre-bakes 6.6 min), with reused pre-bakes ~7 min (normal map at 32 samples 4 min); 512 test bakes 40 s.
Holo screen: `terminal_holo.py` → `T_LAB_HERO_Terminal_Holo.png`, 1024 × 512 RGBA (683 × 602 px/m on the
1.50 × 0.85 quad), the one allowed second texture.
- **Materials** (STYLE_GUIDE): gunmetal paint 90 104 115 (baked median 86 98 108) with large mottling, roughness
  breakup, hairline scratches (three angle sets), sparse edge wear to bare steel on convex edges (0.25 % of the
  texels metal), grime in cavities and towards the floor; recess floors and walls ×0.72 (the concept's darker fields);
  beacon cage ×0.55. Polymer 35 37 39 (slots, beacon base). Steel cup ring under the button. Hazard bands: ochre /
  black 45° stripes, 85 mm pitch, across the 40 mm outer chamfers, worn at their edges. Red cap: red polymer
  168 40 30 (the arming-button exception). Lens: dark red glass 96 20 16, smoothness 0.88. Cyan strips: emission
  70 170 255, off-state albedo 30 45 55.
- **Switching texels** (Indicators, Beacon lens): emission WHITE; TerminalController sets the colour per renderer
  (MaterialPropertyBlock), so the map never decides cyan or red there.
- **Normal-map detail** (numpy height map + Cycles bevel 1.5 mm / bump): 70 hex bolts with washers (dog-bone plate
  corners, cap band, outer-side panel and frame corners, pillar tops, top-front chamfers, desk panel corners, lower
  panel corners, display bar ends), the desk's panel frame (border with 45° cut ends, four dividers) and the pillar cap
  seam as 4.8 mm grooves, 1.2 mm deep. Detail inputs are dilated 6 px past the island borders before the bake.
- **Rust** (STYLE_GUIDE rust rule): patchy on exposed edges and corners, round ~60 % of the bolts (irregular, off-centre),
  blotches at the plinth / body / desk corners, 12 run-off streaks below rusty bolts and the desk frame's front corners,
  patchy (not banded) near the floor; non-metal, smoothness ~0.15. Coverage **5.3 % of the Body paint** (8.3 % below
  y 0.6, 2.8 % above y 1.0).
- **Checks** (`terminal_tex.py -- check`, 2048), all PASS: AO black scan (Body: contact lines plus 6 accepted crevices =
  the 4 mm gaps beside the pillar light strips and the 8 mm gaps in the desk slots, polymer walls 15 mm deep);
  PBR: non-metal albedo 30–240: 0.15 % below, 0 % above; metal albedo ≥ 180: 0.06 % of 4,666 metal texels below;
  emission: cyan strips exactly 70 170 255, switching texels 255 255 255; normal seams on the Body's flat faces: 61
  samples, 0 over 6° (worst 1.9°). The Gate's seam check stepped 2.5 px toward each face's centroid, which on an
  oblique seam put the two samples ~5 mm apart (one in a groove, one not: false 16° readings); the Terminal's check
  samples the same 3D point from both islands and skips samples on deliberate relief (grooves, bolts) or within 4 mm
  of a real edge (bevel zone).
- **Iterations:** 512 test bake → 2048; dark metal texels in the cup ring (grime spared bare steel only partly) fixed;
  black-AO patches at the beacon cage (overlapping cross bars, post tops inside the ring) fixed in the geometry; rust
  4.7 → 7.1 % then the floor band removed (patchy instead) and the level set to 5.3 %; the concept-light renders were
  too bright at first (paint read pale) — lights halved to the concept's values.
- **Renders** (`Documentation/Media/terminal/`): `terminal_h2_vs_concept.jpg` (four concept cameras, concept-like
  neutral light on the concept's mid-grey, beacon lit as in the concept), room position, 3/4, player view, button,
  beacon, pillar, lower panels, side, Armed (3/4 and beacon close-up: three strips red, beacon red), dim facility light
  (lamps at 40 %), flat maps. No white clipping in the render checks.
- **Differences to the concept that remain** (texture level): the concept's rust reaches further into the panel
  fields; its holo glass is paler / more teal than STYLE_GUIDE cyan; its frames read darker relative to the plates.

### H2b — owner review of H2 vs the concept (2026-11-03, one iteration)
Owner decisions (recorded here; HERO_SPEC / STYLE_GUIDE not edited):
1. **Pillars 0.36 wide** (|x| 0.84 … 1.20; the desk / lower body shorten to 1.68 inside the unchanged 2.40 footprint).
   Hazard-band chamfers 40 → 60 mm (wider bands, as in the concept); top chamfers kept (150 / 30 mm). Lower-body
   fields 0.52 wide, desk dividers and slots scaled (slots 230 mm at |x| 0.41), beacon centred at |x| 1.02.
2. **Desk overhang as in the concept:** slab front edge 70 mm (0.85 … 0.92, was 50), lower body front at z 0.62
   (overhang 130 mm, was 100) — a deep, visible shadow gap under the slab. Desk heights and slope unchanged.
3. **Look closer to the concept's values:** paint 72 86 98 (darker, more saturated gunmetal; baked median 68 80 90)
   with stronger mottling and large teal-grey patches; brighter worn edges (bare steel 206 208 210, more edge sections,
   smoother); 20 run-off streaks (was 12), longer; **rust 9.0 % of the Body paint** (13.3 % below y 0.6, 5.4 % above
   y 1.0; threshold `TERMINAL_RUST_LO` 0.20, chosen from 512 tests).
4. **Holo screen only: the concept's paler teal.** Sampled from terminal_front / ortho_front: glass ~88 115 119 and
   lines ~135 178 182 over the grey background (hue ~186°). Texture now lines 120 200 205, highlights 165 225 228,
   tint 120 200 205 at alpha ~0.10. Screen stays 1.50 × 0.85. The light strips keep STYLE_GUIDE cyan 70 170 255.
   **Proposed STYLE_GUIDE row:** "Holo teal (holo screens only) | screen UI lines and tint | emission 120 200 205,
   highlights 165 225 228 (sampled from the Terminal concept, hue ~186°) | – | –".
5. Kept: the player's-right indicators switch red; the beacon is steady when Armed.

Results (all checks PASS): model 1,958 tris (Body 1,676; others unchanged), topology / shading / UV (512 px/m,
44.5 % packing) / clearance (button sweep 1.5 mm, trim 5 mm, footprint) PASS. Bake 12.8 min; AO black PASS (8
accepted: the 6 strip / slot crevices and the two display-bar end faces, which now look into the 40 mm slot between
the bar end and the wider pillars — visible deep corners, not hidden faces); PBR PASS (non-metal 0.15 % below 30,
metal albedo ≥ 180: 0.02 % below, 0.35 % of texels metal); normal seams 2 of 69 over 6° (allowance 2) PASS; no white
clipping. FBX re-exported, re-import PASS; TerminalBuilder numbers updated (Body 1,676 tris, Beacon at (1.02, 1.272,
0.33), pillar colliders 0.36 wide at ±1.02, desk collider 1.68 wide).
Renders: `terminal_h2b_vs_concept_34.jpg`, `terminal_h2b_room.jpg`, `terminal_h2b_dim_facility.jpg`. The other H2
renders show the H2 state (0.30 pillars, lighter paint).

### H3a — Unity preparation (cloud, no Unity)
- **FBX** (`terminal_export.py`, EXPORT_CONTRACT hero mode, same procedure as `gate_export.py`):
  `Assets/Environment/Heroes/Terminal/LAB_HERO_Terminal_{Body,Button,Indicators,Beacon,Display}_01.fbx` (Git LFS),
  each at identity (mesh local to its origin), one material slot. Re-import check in bpy, all PASS: tris 1,670 / 140 / 30 / 112 / 2 (= export copy), root
  transform identity, one material slot, review-file origins = the table above, custom normals (worst 0.027°, every
  corner matched). World boxes: Body x −3.4 … −1.0, y 0 … 1.346, z −2.0 … −1.2; Button x −2.259 … −2.141, y 0.940 …
  1.046; Indicators x −2.754 … −2.526; Beacon y 1.272 … 1.336; Display y 1.10 … 1.942, z −1.968 … −1.85.
- **Textures** (Git LFS): `Textures/T_LAB_HERO_Terminal_{BaseColor,Normal,Mask,Emission}.png` (2048) and
  `T_LAB_HERO_Terminal_Holo.png` (1024 × 512 RGBA).
- **Builder** `Assets/Environment/Editor/TerminalBuilder.cs` (GateBuilder pattern; menu Tools > Labyrinth > Terminal:
  Apply Import Settings / Build Terminal / Verify Terminal): model import settings (hero mode: normals + tangents
  imported, no materials / animation / colliders), texture settings (BaseColor + Emission sRGB, Normal as normal map,
  Mask linear with alpha; mipmaps; max 2048; Android ASTC 6x6, normal 4x4; Holo sRGB + alpha, clamp, max 1024,
  ASTC 6x6). Materials `M_LAB_HERO_Terminal` (URP Lit, as M_LAB_HERO_Gate) and `M_LAB_HERO_Terminal_Holo` (URP Unlit,
  transparent alpha blend, both faces, no depth write). `HERO_Terminal` at (−2.2, 0, −2.0) yaw 0 (HERO_SPEC §5), the
  parts at their origins (table above), prefab `HERO_Terminal.prefab`. Colliders are primitives: Body 3 boxes
  (Pillar_L, Pillar_R, desk + lower body), Button a sphere (r 0.06) for XRI; none on the display, indicators, beacon.
  Verify: root placement, tris, origins, materials, no mesh colliders, footprint, button wiring and travel,
  controller wiring, material keywords, holo material, texture settings.
- **Runtime** (`Assets/Scripts/Facility/`): the button reuses **GateButton** unchanged (XRSimpleInteractable select →
  cap moves `pressOffset` = −0.015 × desk normal = (0, −0.01449, −0.00388) in 0.08 s, `onPressed` at the bottom, back
  in 0.15 s). New **TerminalController** (root): states Standby / Armed / Released; `Arm()` (wired persistently from
  GateButton.onPressed; only the first press counts) turns the three indicators red and the beacon on at once
  (HERO_SPEC §1 state 2) and invokes `onArmed` for FacilitySequence; `Release()` keeps them red (§9). Colours, emission
  intensities and an optional beacon pulse are public fields. MaterialPropertyBlock on the Indicators and Beacon
  renderers (`_EmissionColor`), no material copies; `[ExecuteAlways]`, so the Editor shows the Standby colours.
- C# syntax-checked with tree-sitter-c-sharp (0 errors in both files); the Unity APIs follow GateBuilder /
  GateButton. **Not compiled** (no Unity in the container).

#### To verify in Unity (H3b, local)
1. Recompile; no errors. Tools > Labyrinth > Terminal: Apply Import Settings; then `git diff` the .meta files
   (normalImportMode 0, tangentImportMode 0, materialImportMode 0, Android overrides).
2. Build Terminal on BasicScene (not saved by the builder); Verify Terminal → RESULT: PASS. Save the scene only when
   asked. Commit the .meta files, prefab and the two materials.
3. EXPORT_CONTRACT hero-mode comparison (vertex / normal / tangent) for at least the Body and the Button (first v3
   hero import together with the Gate).
4. Look: the switching strips show cyan in Edit Mode (TerminalController applies the block; if they glow white, the
   block is missing); Body strips and the switching strips must match in colour and brightness (indicatorIntensity =
   material emission intensity); no white clipping with the room's bloom / tonemapping.
5. Holo screen: transparent both ways, readable from the player position, not sorting wrongly against the room's
   other transparent objects (queue 3000); check its brightness against the strips (Unlit: its texture is its colour).
6. Play Mode: GateButton context menu "Press" on Button → the cap moves 15 mm into the desk along its normal and back;
   TerminalController goes Armed, three strips red, beacon red, `onArmed` fires once; a second press does nothing.
   With the rig's ray / near-far interactor: select the button from the player position (0.15–0.30 in front).
7. Teleport: the Body's box colliders block the teleport ray at the terminal (HERO_SPEC §10: the footprint may need
   excluding from NAV_TeleportFloor); the player can stand 0.15–0.30 in front of the pillars.
8. Quest: frame time with the two MaterialPropertyBlock renderers (they leave the SRP Batcher; 2 small meshes), the
   transparent holo quad (1.5 × 0.85 m overdraw), ASTC quality of the normal map on the desk grooves; decide 2048 vs 1024.
9. Lightmapping: the Body and Display can be static; the Button, Indicators and Beacon should not be baked with
   emission (their emission changes at runtime).

## Open questions for the owner
1. ~~Pillar width~~ — decided H2b: 0.36. HERO_SPEC §5 still says 0.30 (proposal: update).
2. ~~Screen aspect~~ — decided H2b: stays 1.50 × 0.85.
3. ~~Indicator group~~ — decided H2b: player's right.
4. ~~Holo colour~~ — decided H2b: holo teal (proposed STYLE_GUIDE row above).
5. ~~Rust~~ — decided H2b: 9.0 %. (Was: 5.3 % of the paint (the rule's lower end, edges / corners / bolts / floor zone); the concept carries more rust
   inside the panel fields.)
6. ~~Beacon~~ — decided H2b: steady when Armed. (Option kept: (TerminalController.pulseWhenArmed /
   pulseWhenReleased, off.)
7. Poke: like the Gate, the button is selected with the rig's ray / near-far interactors; HERO_SPEC §10 asks for poke
   (needs a poke interactor on the rig and an XRPokeFilter on the button).
