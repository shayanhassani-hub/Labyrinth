# Labyrinth VR — Claude Code project notes

Portfolio project: expand Labyrinth VR (Meta Quest 3S) into a compact
"Industrial Robotics Research Facility" environment. The game stays the primary
product. Full plan: `Documentation/PIPELINE_V9.md` (read only the section you need).

## Project facts
- Unity 6000.3.24f1, URP 17.3, XRI 3.3.2, OpenXR 1.16.1, Input System 1.20 (new only)
- Target: Android / Meta Quest 3S. Main game scene: `Assets/Scenes/BasicScene.unity`
- `RenderScene` = look-dev/recording (drone tuned differently). `SampleScene` = VR template leftover
- Project root is on an HDD (D:). Compiles and imports are slow; don't trigger them needlessly
- Git repo = this folder; GitHub `shayanhassani-hub/Labyrinth`. Tags: baseline, unity-working
- Outside this repo: `D:\AI_Labyrinth\` Blender\ (Source, Working, Generated, Export), Meshy\, Gemini\, Logs\

## Locked drone — do not modify
BasicScene / `DroneAI2` / `drone_low`: `Assets/Drone_Asset/drone_low.fbx`, `M_Drone.mat`,
Shader Graph `Assets/Materials/Drone_Mat_V2/SG_DroneOptimized`, scripts `DroneHoverAIV2`,
`PropellerSpin`, `HologramToggle`. No changes to its geometry, materials, textures, shader,
prefab structure, scripts or behavior unless the user explicitly decides it.
File edits are blocked in `.claude/settings.json`; Editor commands are NOT blocked, so never
change these objects through `unity command` either. Facts: `Documentation/ProtectedAssets/DroneBaseline.md`.
Inactive leftovers `DroneAI` and `Drone` (Tripo) are not the locked drone.

## Working rules
- Read Inspector values LIVE through the Editor (`unity command ...`), never infer them from
  scene/prefab YAML — YAML misreads prefab overrides.
- Never save a scene unless asked. Say which scene is open before changing anything.
- One deliberate change at a time. After changes, report `git status --short`.
- Prefer one script (Editor C# or Blender Python) over many small Editor calls. Keep
  validator output short (PASS/FAIL lines).
- Say clearly what you confirmed versus what you expect.
- Don't commit or push unless asked. Never force-push, never `git reset --hard`.
- Don't install packages or change Project/XR/Player settings without asking first.
- Quest is the runtime authority; Editor results are not proof of Quest behavior.

## Unity connection (com.unity.pipeline 0.7.0-exp.1, experimental)
- Check with `unity status` (expect: ready, port 7800). The Editor must be open.
- `MSYS_NO_PATHCONV=1` is set in settings, so Git Bash doesn't rewrite Unity paths.
- `create_gameobject` has no position argument: create, then `set_transform`.
- `delete_gameobject` has no `--confirm` flag.
- After a C# change: recompile, poll `recompile_status`, then `unity status` before continuing.
- Editing .cs files with the file tools can log an import-timestamp warning; harmless.
- The package hooks into builds. If a Quest build fails oddly, it is a suspect.
- Some commands change settings/assets only in memory (e.g. `eval` with PlayerSettings, `attach_script`
  on a prefab). After such changes run `AssetDatabase.SaveAssets()` and confirm with `git diff`.
  SaveAssets does not save scenes.
- Put temporary files (eval scripts etc.) in `Temp/` (git-ignored), never in the project root.
- Active build target is Android (switched 2026-09-22). Editor Play Mode still uses the Standalone XR settings.

## Blender CLI
- Headless: `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python-expr "..."`
- `-b --factory-startup` is the default for generator/validator runs.
- Scripts live in `Tools/Blender/`.

## Known Android build side effects (verified 2026-09-22 — don't re-investigate)
- NullReferenceException in OpenXR `MetaQuestFeature.cs:554` during build preprocess: Unity package bug
  (rule reads `selectedBuildTargetGroup` = Standalone). Non-fatal; build still succeeds.
- `m_optimizeBufferDiscards` 0→1 in OpenXRPackageSettings: set by the Meta Quest feature on every Android build.
- URP Config prefilter flags, DefaultVolumeProfile, URP GlobalSettings runtime list, and XR entries in
  `preloadedAssets`: normal build output. Commit once; only investigate if something else changes.
- Warning "Pipeline will be disabled in Player builds": expected and wanted.
- 29 CS0618 warnings from XRI 3.0.x sample scripts: known, harmless.
- First IL2CPP build ≈18 min on this HDD; APK goes to `Builds/` (git-ignored).

## Naming and contracts
- New environment assets go under `Assets/Environment/` (Git LFS tracks binaries there only).
- Asset IDs: `LAB_ENV_<Name>_<Var>_<NN>` (e.g. LAB_ENV_Wall_A_01), `LAB_PROP_<Name>_<NN>`.
  Same name in Blender and Unity.
- 1 Unity unit = 1 m. Blender->Unity export/import settings, axis conversion and the wall yaw
  table: `Documentation/EXPORT_CONTRACT.md` (verified 2026-09-23 - follow it, don't re-derive it).
- Color textures sRGB; normal/metallic/roughness/AO/masks linear.

## Visual direction (short)
Dark painted metal, black polymer, cyan/blue emissive accents, selective warning colors.
The yellow drone is tied in through warning-yellow accents. Details: `Documentation/STYLE_GUIDE.md`.

## Documents (read on demand, don't load all)
- `Documentation/PIPELINE_V9.md` — the plan; production sequence in section 53
- `Documentation/ProtectedAssets/DroneBaseline.md` — verified drone facts
- `Documentation/DEVLOG.md` — session log

## End of session
When the user says the session is ending, append ~5 lines to `Documentation/DEVLOG.md`:
date, what was done, decisions, problems, next step, rough hours.
