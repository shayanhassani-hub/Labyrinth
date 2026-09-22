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

## Naming and contracts
- New environment assets go under `Assets/Environment/` (Git LFS tracks binaries there only).
- Asset IDs: `LAB_ENV_<Name>_<Var>_<NN>` (e.g. LAB_ENV_Wall_A_01), `LAB_PROP_<Name>_<NN>`.
  Same name in Blender and Unity.
- 1 Unity unit = 1 m. Details: `Documentation/EXPORT_CONTRACT.md` (when it exists).
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
