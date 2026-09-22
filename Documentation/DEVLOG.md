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
- Next: production step 2 (CLAUDE.md, permissions, DroneBaseline, Git LFS).  Hours: ~3
