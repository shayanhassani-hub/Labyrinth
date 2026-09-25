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
