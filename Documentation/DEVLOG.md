# Development Log

Short entries, newest at the bottom. Date, done, decisions, problems, next, hours.

## 2026-09-21
- Done: moved project to D:\AI_Labyrinth\UnityProject; baseline tag; committed the
  Unity 6000.3.24f1 upgrade; installed Git, Claude Code, Unity plugin; C: cleanup and
  cache redirect to D:\DevCache; read-only project inspection.
- Decisions: Git repo stays inside UnityProject; project stays on D: (HDD) for now.
- Problems: project had never been built for Quest; build list only has SampleScene.
- Next: Editor connection.  Hours: ~5

## 2026-09-22
- Done: installed com.unity.pipeline 0.7.0-exp.1; live Editor reads; connection tests
  2–5 passed (connection survives domain reload); tag unity-working; Pipeline V9 written.
- Decisions: follow Pipeline V9; keep V8 palette, tie yellow drone in via warning accents;
  crystals were never built (optional future feature).
- Problems: file-based inspection misread DroneAI2's prefab overrides; live read correct.
- Afternoon: step 2 done (CLAUDE.md, permission rules incl. drone deny rules — tested, DroneBaseline
  filled live, Git LFS scoped to Assets/Environment/). Step 3 prep: BasicScene only build scene,
  package ID com.shayanhassani.labyrinthvr, product "Labyrinth VR", company "Shayan Hassani",
  active target Android, ProjectileLifetime (6 s) on the bullet. First APK built: 63 MB, ~18 min.
- Decisions: PropellerSpin to be added to BasicScene later; Holographic Mode experimental; Scanner
  Light variant decided later; XR auto-loading needs no change (verified in package source).
- Problems: in-memory changes needing SaveAssets; OpenXR MetaQuestFeature validation NRE (Unity
  bug, non-fatal); build side effects documented in CLAUDE.md; long investigation cost tokens.
- Next: install APK + Quest baseline when headset is available; step 4 (Blender in Claude Code).
  Hours today: ~7

## 2026-09-23
- Done: ENVIRONMENT_SPEC written (8x10 room, 4 m ceiling, 2 m grid, protected volumes);
  env_kit_generator refactored into a MODULES registry; full greybox kit built and
  live-verified (Wall_A, Wall_Panel, Wall_Corner, Wall_Door, Wall_Corridor, Floor_A,
  Ceiling_A, Pillar_A, Trim_A); room layout in BasicScene (96 instances) + corridor
  (13 instances); M_Greybox created; EXPORT_CONTRACT.md finally written and corrected.
- Decisions: walls 2.0 + 2.0 m panels; facility door at x = -1 (no module centers on x = 0
  in a 4-module wall); corridor 5.8 m so tiles and end cap close flush; Hero 01 = docking
  cradle from reference (octagonal base, yoke arms, 4 panels) that opens flat to clear the
  drone volume, plus an articulated arm; hero parts are rigid hinges in a transform
  hierarchy, NOT rigged/skinned meshes; palette rule - amber-yellow means drone-handling
  equipment, everything else dark metal + blue emissive.
- Problems: two geometry bugs, both "one end right, other end wrong". (1) Unity mirrors X
  on FBX import; Wall_A's symmetric X bounds hid it until Wall_Corner (X 0..0.2) exposed it -
  generator now pre-negates spec X. (2) Corridor floor/ceiling stopped at z 14.0 while the
  end cap sat at 14.2, leaving an open strip where the player can stand. Also: EXPORT_CONTRACT
  had been claimed as written in an earlier session but never created, and its importer
  settings were never actually applied to Wall_A.
- Next: owner rescales drone, labyrinth panel, ball, bullets, DroneBounds and the related
  DroneHoverAIV2 values (incl. lowering the bounds ceiling ~0.5 m for the overhead arm);
  then Claude Code re-reads everything live and rewrites DroneBaseline.md + the protected
  volume table; then HERO_SPEC.md and the Hero 01 blockout.
  Hours today: ~6

## 2026-09-24
- Done: stripped Claude session links from history (rewrite + force-push, backup branch kept);
  attribution kept on the 4 code-heavy commits. GreyboxBuilder (Tools > Labyrinth > Rebuild
  Greybox) replaces the layout scripts Unity wiped from Temp/. First Quest test of the greybox:
  room scale good, drone and labyrinth too big, teleport broken. Teleport floor added. Owner
  rescale: drone 0.59, labyrinth panel 1.05 m, projectile 0.17, DroneBounds reduced; baseline and
  protected volumes re-read live.
- Decisions: attribution "Co-Authored-By: Claude <noreply@anthropic.com>" only on commits with
  substantial Claude code, never session links; scale drone_low, not DroneAI2; ring sparks on
  Hierarchy scaling; teleport surface = one NAV_TeleportFloor object, not per-tile colliders;
  owner tunes scale/gameplay values by hand, baseline re-read after each change.
- Problems: re-sending a file under the same name delivered stale copies - last night's CLAUDE.md
  rule and corridor spec never landed (now fresh names + read-back check). Trim was buried inside
  the walls since 09-23. Deactivating the old Plane silently removed teleport. URP auto-edits
  to M_Drone and FresnelHighlight (harmless). Rebuild() used as a check = 10k-line scene diffs.
- Next: HERO_SPEC.md for the docking cradle + ceiling arm against the final volumes (open-state
  limit y 1.19, +X bay 1.61 m, ceiling gap 0.52 m, cradle the drone BODY, 0.228 m below DroneAI2).
  Next build confirms the last DroneBounds tweak. Performance baseline (release build) still open.
  Delete backup/pre-rewrite branch after a few days.
  Hours today: ~5

## 2026-09-25
- Done: HERO_SPEC.md v1-v6 - the full launch sequence (corridor spawn, gate + button, terminal
  arms the room, lever releases the drone), cradle sized from a live drone measurement, ceiling
  service arm, terminal, lever, gate, all decisions resolved. Labyrinth v2 built end to end: maze
  traced from the owner's layout (goal channel widened so the ball fits), panel/handle/cone stand
  generated from JSON, assembled around a fixed pivot (LabyrinthBuilder), physics layers + ball-only
  lid + goal trigger, pan-style tilt control (LabyrinthTilt, 7 tests), goal reset, functional
  lighting v0 (task spot, no sun shadows), handle ray fix. Drone/gameplay lock removed.
- Decisions: pan model (lift = forward/back, wrist twist = sideways, spin locked, 12 deg cone,
  holds on release); invisible lid stops only the ball so bullets still hit it; alarm-pulse lighting
  after release; see-through terminal display; hero parts = one FBX per rigid part, pivot on hinge.
- Problems: panel boolean ran on touching boxes and dropped the rim/walls (164 tris); spec-built
  meshes came out inside-out (normals refreshed too late) - the stand's cone, and the hole cutter,
  so the hole never cut. Both fixed at the root; export contract gained non-box rules (expected tri
  range, inward-face count, render checked by a human). Test Runner save dialog jammed the Pipeline
  command channel - fixed by saving + restarting Unity; rule in CLAUDE.md. First headset test
  exposed the shadow circle (2.5 m shadow distance) and the ray snapping to the board centre.
- Next: headset test of the labyrinth (visibility at intensity 8, ray hidden while held, 12 deg feel,
  speed, goal reset, bullets knocking the ball) and tune; then hero blockouts (cradle, service arm,
  terminal, lever, gate) and the sequence wiring.
  Hours today: ~8

## 2026-09-26
- Done: labyrinth v2 tested on Quest, works; three adjustments parked as backlog L1-L3
  (HERO_SPEC §8). UVs for everything the generator exports (world-scale box projection,
  1 unit = 1 m); kit + labyrinth regenerated, verified live (bounds/tris unchanged,
  0 mirrored faces). 7 kit importers fixed. ASSET_RULES.md written (tiers: hero strict,
  secondary, architecture kit, greybox). Hero export mode (triangulated, custom
  normals, MikkTSpace). Cradle Part 1: production low-poly built by construction
  (748 tris, clean quads, clevis hub with pins), CradleBuilder + live sweep verify.
- Decisions: from now on every non-greybox asset follows professional standalone-VR
  standards (topology, UVs, bakes, PBR), strict for heroes, lighter for secondary;
  kit uses tiling materials + trim sheet; Cradle built directly at production quality,
  no greybox; packed mask R metallic / G AO / A smoothness.
- Problems: the 2026-09-23 importer fix had never persisted on 7 modules; Code couldn't
  view renders outside the project (renders now in UnityProject/Renders, git-ignored);
  capture_scene_view writes into Assets/; Pipeline eval 5 s limit on the hinge sweep
  (run via delayCall); .gitignore line endings rewritten by a script.
- Open: Cradle silhouette is weak (thin post on a big plinth, stick-like arms) -
  silhouette pass by Code vs Meshy for the static body, decide next session. Meshy
  test (V9 step 5) still open. STYLE_GUIDE.md missing. Hero budget (12 h) likely too
  small for five heroes at this standard - re-plan after timing the Cradle.
- Next: decide Cradle direction; then Part 2 (UVs, high-poly, bake exports).
  Hours today: ~6

## 2026-09-27
- Done: researched AI 3D tools (Meshy, Tripo, Hunyuan3D: latest features, licensing).
  Hunyuan global site (hy3d.tencent.ai / 3d.hunyuanglobal.com) is usable from the EU and
  assigns output rights to the user (ToS §6.3); the mainland site 3d.hunyuan.tencent.com
  is China-only. Cradle redesigned from the owner's reference image with Gemini (drone,
  monitor posts, cables and floor plate removed; flat rest plates on the U-yoke; details
  simplified; symmetry fixed) plus orthographic views (front; back = mirrored front;
  side view plate fixed by hand; right = mirrored left; top). Hunyuan 3D Studio test on
  the Cradle: 3.1 multi-view geometry (1.5M faces, clean hard surface), Texture Painting
  (image- and text-based), Component Splitting (3 complete parts: static body, left arm +
  plate, right arm + plate), Retopology Low/Quads (5,710 faces). Meshy remesh of the same
  high-poly for comparison (11,091 quads). Downloads in D:\AI_Labyrinth\Hunyuan\Downloads\Cradle\.
- Decisions: Pipeline V9's time budget is no longer used (the project needs more time).
  Hero workflow v1 = AI transfer workflow: Hunyuan high-poly, parts and textures as the
  detail source; Claude Code builds the clean hero low-poly to the AI shape; transfer
  bake; finish in Substance. Fallback: the more hand-made workflow if the result is not
  good enough. Hunyuan chosen over Meshy for hard-surface work (generation and retopo);
  Meshy kept as backup / organic props. New Cradle design: the drone rests on two of its
  arms on the yoke plates (docked with a yaw rotation); yoke halves still fold for release.
- Problems: Gemini ignored some symmetry/proportion edits (side view plate fixed by
  hand); Hunyuan Repaint replaces the texture with no history, and textured 1.5M downloads
  failed until the browser was restarted; split parts interpenetrate and leave thin shards;
  Hunyuan retopo has fans/slivers and a modelled underside; Meshy remesh loses hard edges.
- Open: HERO_SPEC §3 must be rewritten for the new Cradle (docking pose, contact points on
  the plates, hinge positions, release fold) from live drone measurements; Cradle Part 1
  procedural model is superseded; ASSET_RULES.md to record the AI workflow, tool choice and
  AI reference rules; STYLE_GUIDE.md still missing.
- Next: Claude Code imports the Hunyuan files, fits them to the spec, measures the drone
  contact, compares, and runs a trial transfer bake.
  Hours today: ~7

## 2026-09-28
- Done: Cradle v2 (AI transfer workflow) Steps 1-4. Step 1: Hunyuan high-poly, split parts
  and textured variants imported and fitted (x2.589); docking study with the live drone dump.
  Step 2: pad study, cross-sections and measurement sheet, plinth symmetrized from the -X
  half, HERO_SPEC §3 rewritten (old design -> §3a), ASSET_RULES: hero workflow v1, AI tool
  choice, AI reference rules. Step 3/3b/3c: clean hero low-poly by construction
  (cradle_v2.py + cradle_v2_check.py): 3,620 tris, quads (8 tris on the base), arms exact
  mirrors, all clearances pass (limbs >= 11.1 mm over the whole fold), new hole test.
  Step 4: UV module (cradle_v2_uv.py): no overlaps/flips, low distortion, ~410 px/m.
  Personal copy of the pre-UV low-poly on G:\AI_Labyrinth_Personal\Cradle\.
- Decisions: docking option A (drone yaw -28.3 deg, two opposite limbs on the plates);
  release angle 75 deg (100 deg hits floor/plinth), timing 1.2 s; front faces -Z.
  Identical 10 mm amber pads + grey 54.4 mm riser under the left pad (saddles rejected:
  prop clearance). Plate inner-edge chamfer 40 x 8 mm for fold clearance. Depth rule:
  visible relief > ~15 mm is geometry. Deviation acceptance: every over-limit area
  classified a) modelled / b) design difference / c) AI junk, unexplained > 15 mm < 0.5 %
  per part (Cradle passes). Turntable notches removed (read as damage). AI junk zones are
  corrected in the high-poly before any bake (bake transfers detail, never shape decisions).
- Problems: holes at the notch ends and, found by the new test, partly visible faces
  deleted by the hidden-face pass (fixed: dense sampling + hole test). Code's fold check
  initially below 10 mm (fixed by the chamfer). UVs too fragmented (473 islands, 45 %
  packing): 45 deg octagon turns marked hard -> every ring cut into pieces.
  Blender review file was open during a Code run (not saved, no harm) - rule: close
  without saving before a run.
- Open: service arm §4 conflicts with the turned drone (prop discs reach |x| ~0.14);
  DroneHoverAIV2 must take off from yaw -28.3 deg without snapping; STYLE_GUIDE.md missing.
- Next: Step 4b UVs (fewer, larger islands, octagon bands as continuous strips, target
  >= 480 px/m on one 2048 set); then Step 5 bake-source cleanup (AI junk zones patched)
  and a test transfer bake; then Substance.
  Hours today: ~6

## 2026-10-03
- Done: Cradle v2 UVs finished (Steps 4b/4c): smooth chamfer corners, octagon bands as continuous
  strips, ring cuts kept off the front half, 8/4 px padding; 428.5 px/m on one 2048 set, 176 islands,
  52 % packing, deterministic generator. Step 5a: AI-based bake sources (fitted AI mesh with junk zones
  patched, colour highs, Substance export). Step 5b: comparison bake on the same low - AI high vs clean
  bevelled high. Step 6a: production high-poly built by Code (bevels with measured radii, 3 mm inside
  fillets, detail set: plinth side panels x8, tray outlines, pin cap retaining rings, drum bands, hub
  groove, column access panel + 4 screws, turntable radial seams, elbow grooves, strip panel lines,
  gusset bolts, arm outer inset panel, plate top outline, riser bolts) and per-vertex cages.
  Personal snapshots on G: (UV'd low-poly, 5b comparison renders and test bakes).
- Decisions: hero texel density >= 400 px/m acceptable for heroes > 2 m on one 2048 set (target 512);
  padding 8 px / 4 px border; no fixed island count, seams avoid front/main views. Hero workflow v2:
  the AI model is the shape, measurement and colour reference only; high-poly = low + controlled
  bevels + clean detail (5b: ray misses 4.61 % vs 0.02 %, AI surfaces wavy/"melted", patch borders
  jagged). Code does the full high-poly detail pass; the owner textures in Substance.
- Problems: 4b missed its targets (194 islands, 409 px/m) - thin strips and 16 px padding were the
  cause, my 480-520 estimate was wrong; non-deterministic island output (fixed); 5a patch borders
  ragged; colour bakes first blank (colour-space bug, fixed); 5b dashed seam lines from a 25 mm ray
  offset (cages built in 6a). The Monday DEVLOG commit had not run (committed today).
- Open: high-poly round parts are still 16-faceted (to become true circles in 6b); turntable seams
  break over the rounded top edge; ID map groups; final bake verification + Substance export (6b).
  Service arm §4 conflict, DroneHoverAIV2 yaw, STYLE_GUIDE.md still open.
- Next: Step 6b (round parts, seam fix, ID vertex colours, cage bake check, export + README for
  Substance); then the owner textures the Cradle in Substance Painter.
  Hours today: ~4

## 2026-10-04
- Done: owner reviewed the Code-built high-poly in Blender and approved it. Step 6b: round parts true
  circles in the high (96 segments, revolution normals), grooves projected onto the real surface,
  ID vertex colours (6 groups: painted structure, machined metal, amber pads, riser, fasteners,
  column access panel), cages enclose all highs, Blender verification bake (ray misses 0.03 %),
  Substance export + README. Substance export re-done in the assembled closed pose (Arm_L and
  Pad_L left out: they share their twin's UVs). Substance Painter 6.1.3 (2020.1) project set up,
  first 1024 test bake: ID and normals correct. Step 6c: turntable and rings 2/3 raised to 32
  segments (sliver at the turntable foot 13.9 -> 2.7 mm, round outline from above), 3,876 tris,
  438 px/m, re-export. Backups on G: (bake .blend, Substance meshes).
- Decisions: Code does the full high-poly detail pass; Substance texturing is the owner's part.
  Round-shape rule: 32 segments for diameter >= 0.5 m, 16 for 0.2-0.5 m, 8-12 below. Substance
  bake from the assembled pose, match by mesh name, cage file, ID from vertex colour, AO only same
  mesh name + ground plane; final bake 2048 with 2x2 subsampling (TdrDelay not changed).
  Starting palette proposed (warm light-grey paint, brushed steel, drone-yellow pads, graphite
  riser, zinc fasteners) - to be confirmed in Substance and written up as STYLE_GUIDE.md.
- Problems: 6a bugs found in 6b (inside-out bolts/drum bands, tray outlines on the edge bevel,
  cross-part AO); first Painter export had the parts piled at their pivots; Painter shows a GPU
  preemption warning (long bakes may be killed by Windows TDR); the 16-segment turntable baked
  normal slivers at every facet foot (fixed in 6c).
- Open: re-do the Painter project with the 6c low (new project, test bake, final bake, save
  _v01_baked); then texturing; custom export preset (BaseColor / Normal OpenGL / Mask R metallic,
  G mixed AO, A glossiness); Unity import of the Cradle v2 (separate Unity export at own pivots);
  STYLE_GUIDE.md; service arm §4 conflict; DroneHoverAIV2 yaw.
- Next: Painter - new project with the 6c Cradle_low.fbx, bake (1024 test, check the turntable
  foot, then 2048 2x2), save; start the base materials per ID group.
  Hours today: ~5
