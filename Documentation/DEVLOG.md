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
