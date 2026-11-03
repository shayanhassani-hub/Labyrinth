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
| P1 | Chunky pillar blocks, chamfered vertical edges (plan octagon: big outer chamfers, small inner) | both pillars | G (half-space block: outer 40 mm, inner-front 8 mm) | ✓ | | |
| P2 | Large top-front chamfer, smaller top-side chamfers | pillar tops | G (90 / 30 mm) | ✓ | | |
| P3 | Top cap seam ~0.1 below the top | pillar front / sides | N (groove) | | | |
| P4 | Base band | pillars, lower body | G (plinth 0.16 high, 15 mm inset; also the trim notch) | ✓ | | |
| P5 | Front: recessed field with a raised "dog-bone" plate (wide top / bottom, narrow waist, 45° tapers) | pillar fronts | G (field 18 mm, plate 12 mm proud) | | | |
| P6 | Vertical cyan light strip in the plate's waist | pillar fronts | G (slot 15 mm) + emission | | | |
| P7 | Hazard stripes on the outer vertical chamfers (front and back) | pillars | T (ochre / black 45°), faces split at y 0.22 / 1.10 | ✓ | | |
| P8 | Outer side: framed field, three panels with stepped (Z) dividers | pillar outer sides | G (field 18 mm, panels 10 mm proud) | | | |
| P9 | Inner side: big plate with a cut corner | pillar inner sides | N (panel groove); only ~0.2 m shows above the desk at spec heights | | | |
| P10 | Bolts at plate / panel / frame corners | everywhere | N (hex heads, washers) | | | |
| P11 | Pillar top: corner bolts, seams | pillar tops | N | | | |
| P12 | Rust on edges, corners, bottom, streaks; worn hazard paint | everywhere | T (STYLE_GUIDE rust rule) | | | |
| B1 | Beacon base (black) | Pillar_L top | G (Ø 0.10 × 0.022, 16 seg) | ✓ | | |
| B2 | Red beacon lens (dome) | Pillar_L top | G, own mesh (Ø 0.08, dome) | ✓ | | |
| B3 | Wire cage round the lens | Pillar_L top | G (4 posts 6 mm, ring, top cross) | | | |
| B4 | Red glow halo around the beacon | – | – (Unity bloom / a light in the lighting pass, not geometry) | – | – | – |
| D1 | Desk slab: thick front edge, top-front chamfer | desk | G (50 mm edge, 8 mm chamfers) | ✓ | | |
| D2 | Deep shadow under the desk slab (overhang over the lower body) | desk | G (100 mm overhang) | ✓ | | |
| D3 | Framed desk panel: border with 45° cut ends, five panels | desk top | N (grooves) | | | |
| D4 | Bolts at the desk panel corners | desk top | N | | | |
| D5 | 6 indicator slots with cyan strips (2 × 3) | desk top | G (slots 15 mm) + emission; 3 = Indicators_01 | | | |
| D6 | Button guard: flange, thick collar with a notch | desk centre | G (flange 8 mm, collar 35 mm, 24 seg) | ✓ (plain collar) | | |
| D7 | Red cap with chamfer, steel cup ring under it | desk centre | G (cap Ø 0.12, 24 seg) + T (steel cup floor) | ✓ | | |
| D8 | Display base bar / slot along the back | desk shelf | G (1.60 × 0.05 × 0.07) | ✓ | | |
| S1 | Transparent holo panel, glowing frame with corner tabs | display | own holo texture (≤ 1024) + transparent material | ✓ (quad) | | |
| S2 | Holo UI: room / drone wireframe, graphs, grid, data blocks | display | holo texture; no readable text | | | |
| L1 | Three recessed front panels | lower body | G (18 mm) | | | |
| L2 | Stepped divider: lower panel raised in the middle | lower body | G (panels 10 mm proud) | | | |
| L3 | Bolts at the lower panel corners | lower body | N | | | |
| C1 | Overall colour: blue-grey gunmetal, darker frames | all | T | | | |

## Deviations from the concept (spec wins)
| Concept | Model | Reason |
|---|---|---|
| Squat: desk ≈ half the pillar height above the floor, pillars ≈ 0.84 high relative to a 2.4 m width | Desk 0.92 … 1.05, pillars 1.25 (spec) | HERO_SPEC §5 heights for a standing VR player (owner's brief) |
| Pillars ≈ 0.43 wide (18 % of the width) | 0.30 (spec) | HERO_SPEC §5 size; the pillars read slimmer than in the concept (open question) |
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

## Open questions for the owner
1. Pillar width: keep 0.30 (spec) or widen towards the concept (e.g. 0.36 → desk 1.68 wide, footprint unchanged)?
2. Screen aspect: spec 1.50 × 0.85 vs the concept's ≈ 2.2 : 1 (e.g. 1.50 × 0.68).
3. Which indicator group turns red: player's right (chosen) or left (with the beacon)?
