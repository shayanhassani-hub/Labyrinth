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

## Drone and gameplay (no lock - owner decision 2026-09-25)
The drone (`DroneAI2` / `drone_low`, `DroneHoverAIV2`, `PropellerSpin`, `HologramToggle`, `M_Drone`,
`SG_DroneOptimized`), the labyrinth and all gameplay code are normal, editable project code. Pipeline V9's
locked-drone rules are superseded. Change them when a task asks for it, and say what you changed.
The owner often tunes values by hand in the Editor - don't overwrite hand-tuned values unless asked.
`Documentation/ProtectedAssets/DroneBaseline.md` = reference of the last verified state (not a lock):
after any change to scale, bounds or gameplay values, re-read LIVE and update it and the protected-volume
table in ENVIRONMENT_SPEC.md - never carry old numbers forward.
Inactive leftovers `DroneAI` and `Drone` (Tripo) are not the game drone. Source-model name typo:
`Engline2_low` (search both spellings). Launch-sequence heroes: `Documentation/HERO_SPEC.md`.

## Working rules
- Read Inspector values LIVE through the Editor (`unity command ...`), never infer them from
  scene/prefab YAML — YAML misreads prefab overrides.
- Never save a scene unless asked. Say which scene is open before changing anything.
- One deliberate change at a time. After changes, report `git status --short`.
- Prefer one script (Editor C# or Blender Python) over many small Editor calls. Keep
  validator output short (PASS/FAIL lines).
- Say clearly what you confirmed versus what you expect.
- Don't commit or push unless asked. Never force-push, never `git reset --hard`.
- Commit messages: NEVER include Claude session links. Add the trailer
  `Co-Authored-By: Claude <noreply@anthropic.com>` only when Claude wrote substantial code
  (generators, builder/Editor scripts, non-trivial fixes). No trailer on docs, settings, small
  edits, or the owner's own work. No model name in the trailer.
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
  Unity deletes `Temp/` when it closes: anything worth keeping goes in the repo (e.g. `Assets/Environment/Editor/`).
- XRI 3.3 lookups (verified 2026-09-24 - don't search again): interaction layer names are in
  `Assets/XRI/Settings/Resources/InteractionLayerSettings.asset` (`m_LayerNames`; bit 31 = Teleport).
  Each hand has an XRRayInteractor "Teleport Interactor". Teleport surface = `ENV_Greybox/NAV_TeleportFloor`.
- `GreyboxBuilder.Rebuild()` regenerates every kit instance's ID, so each run is a ~10k-line BasicScene diff.
  Run it only when the layout actually changes - never as a verification step.
- Active build target is Android (switched 2026-09-22). Editor Play Mode still uses the Standalone XR settings.

## Blender CLI
- Headless: `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python-expr "..."`
- `-b --factory-startup` is the default for generator/validator runs.
- Scripts live in `Tools/Blender/`.

## Known Android build side effects (verified 2026-09-22 — don't re-investigate)
- NullReferenceException in OpenXR `MetaQuestFeature.cs:554` during build preprocess: Unity package bug
  (rule reads `selectedBuildTargetGroup` = Standalone). Non-fatal; build still succeeds.
- `m_optimizeBufferDiscards` 0→1 in OpenXRPackageSettings: set by the Meta Quest feature on every Android build.
- URP Config prefilter flags, DefaultVolumeProfile, URP GlobalSettings runtime list: normal build output.
- `ProjectSettings.asset` `preloadedAssets` FLIPS between `[]` and two XR entries on its own (a build adds
  them, Unity later drops them). Harmless either way: commit whatever state is there, never investigate.
  Do check the rest of any ProjectSettings diff - package ID and product settings live in the same file.
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
