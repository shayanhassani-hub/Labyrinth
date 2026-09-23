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
