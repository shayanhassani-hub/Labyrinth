<!-- Markdown copy of Pipeline_V9.docx (22 Sep 2026). The .docx is the master; update both together. -->

# AI-Assisted 3D & Technical Art Production Pipeline

**Labyrinth VR: Industrial Robotics Research Facility**

**Version 9** · 22 September 2026 · Shayan Hassani

---

## 0. What Changed in V9

V9 revises V8 after the first two setup days. The philosophy of V8 is unchanged. The revisions come from verified facts about the real project and from using Claude Code properly.

- **Verified state replaces assumptions.** A new section 3 records what the live inspection actually found. Several V8 assumptions were wrong (crystals, XR stack, storage, drone design).
- **The Quest comes first, not last.** The project has never run on the headset. The first Quest build and performance baseline now happen right after the Unity connection (section 53).
- **Claude Code is used natively.** New section 11: a short CLAUDE.md, permission rules (including drone protection), scripts instead of many small calls, one Claude Code hub for Unity and Blender, and session habits that save tokens.
- **Blender generator is a Python script**, which is the source of truth and lives in Git.
- **Git LFS** is required before the first new binary assets.
- **Visual direction is decided:** the V8 palette stays. The drone is no longer the visual anchor; its yellow is tied into the environment through warning accents.
- **Storage reflects the hardware:** only C: is an SSD.
- **Time budget is rebalanced:** setup ran over and is paid from contingency.
- **A development log** (DEVLOG.md) is written by Claude at the end of each session.

## 1. Project Purpose

Expand the existing **Labyrinth VR** project into a visually coherent realtime environment:

**Industrial Robotics Research Facility**

The project has three equal portfolio goals:

#### 3D Art

- environment art
- hard-surface props
- materials
- lighting
- composition
- asset optimization

#### Technical Art

- procedural environment modeling
- AI-assisted 3D production
- Blender automation
- Unity Editor tooling
- reusable material systems
- technical validation
- VR optimization

#### XR / Game Development

- Unity
- C#
- VR interaction
- Quest 3S deployment
- realtime performance

The game remains the primary product.

The Technical Art systems exist only when they:

1. make the game faster to build,
2. improve the final game,
3. demonstrate a meaningful Technical Art skill.

## 2. Core Principle

The project is **not** an AI game-production platform.

It is: **A real VR game developed with an AI production partner and a small set of purpose-built Technical Art tools.**

The working loop is:

```
YOU  (creative direction, decisions)
  │
  ├── Claude app chat ── planning, review, decisions
  │        │  decisions are written into the repo docs
  │        ▼
  └── CLAUDE CODE  (execution hub, one session)
           ├── Unity    (official plugin + Pipeline package)
           ├── Blender  (official MCP + headless Python)
           └── Meshy    (candidate 3D generation)
                  ▲
           Gemini ─ references
                  │
           Labyrinth VR ──► Quest 3S
```

The detailed production loop is:

`Decide → Ask Claude → Execute → Inspect → Validate → Iterate`

Do not add infrastructure merely because it is technically possible.

## 3. Current Verified Project State

Verified on 21–22 September 2026 through a read-only inspection and live reads from the Unity Editor. This section replaces assumptions. Update it when the facts change.

### Project facts

| Item | Verified state |
|---|---|
| Unity project | D:\AI_Labyrinth\UnityProject (Git repo, GitHub: shayanhassani-hub/Labyrinth) |
| Unity version | 6000.3.24f1 (Unity 6.3 LTS), upgraded from 6000.0.26f1 |
| Packages | URP 17.3.0 · XR Interaction Toolkit 3.3.2 · OpenXR 1.16.1 · XR Management 4.6.1 · Input System 1.20.0 · com.unity.pipeline 0.7.0-exp.1 |
| XR | OpenXR loader; Meta Quest feature and Oculus Touch profile on (Android); hand tracking, foveation, SpaceWarp off; new Input System only |
| Android | Min SDK 32, ARM64, IL2CPP; package ID still com.unity.template.vr (must change) |
| Main game scene | Assets/Scenes/BasicScene.unity |
| Other scenes | RenderScene (look-dev/recording, drone tuned separately); SampleScene (VR template, currently the only build scene) |
| Locked drone | DroneAI2 in BasicScene: drone_low.fbx, M_Drone.mat, Shader Graph SG_DroneOptimized, DroneHoverAIV2 |
| Crystals / throwables | Never built. Optional future feature, not protected gameplay |
| Quest 3S | The project has never been built or run on the headset |

### Git checkpoints so far

| Commit / tag | Content |
|---|---|
| baseline (ec34076) | Last game state before the pipeline, on Unity 6000.0.26f1 |
| fc872f6 | Upgrade to Unity 6000.3.24f1 |
| 3243400 | Unity Claude Code plugin (project scope) |
| dae4fb1 | com.unity.pipeline for live Editor control |
| unity-working | Connection tests 1–5 passed; live Editor control works and survives domain reload |

### Known issues from the inspection

**Before the first Quest build:**

- Only SampleScene is in the build list. BasicScene must be added.
- The package ID is still the template default. Change it, for example to com.shayanhassani.labyrinthvr.
- Verify that the bullet (Sphere.prefab) has a Rigidbody and that bullets are destroyed.

**Recorded, decided later:**

- HologramToggle needs a keyboard (does not work on Quest) and uses r.material (creates material copies). It belongs to the locked drone, so it is only changed by explicit decision.
- Quest quality level uses 4096 shadow maps, 4× MSAA and HDR. Measure first (section 42), then change one setting at a time.
- The XR rig comes from the XRI 3.0.6 samples; the package is 3.3.2. Re-import only if the rig misbehaves on Quest.
- Cleanup candidates: inactive DroneAI and Drone (Tripo) objects, unused Oculus loader, legacy post-processing define, Test.cs, DroneHoverAI.cs, the leftover "Labyrinth Game" folder, the stale Labyrinth Game.sln.

### Lesson from the inspection

Reading scene files as text misread the drone's prefab overrides. Reading the live Editor was correct. **Rule: values shown in the Inspector are only trusted when Claude reads them live from the Editor.**

## 4. Tool Roles

| Tool | Primary Role |
|---|---|
| Claude Code | Main AI production partner and execution hub |
| Claude app (chat) | Planning, review, decisions; results recorded in the repo docs |
| Official Unity plugin + com.unity.pipeline | Live Unity Editor control from Claude Code |
| Blender MCP (in Claude Code) | Blender inspection and interactive work |
| Blender headless (Python) | Procedural generation, batch processing, validation |
| Claude Desktop Blender connector | Fallback for Blender work |
| Gemini | Visual ideation and reference generation |
| Meshy | Candidate AI 3D generation |
| Substance Painter | Material refinement |
| Unity | Realtime game and environment |
| Quest 3S | Runtime authority |
| Git + Git LFS / GitHub | Backup, version control, off-machine copy |

## 5. Technology Baseline

#### Development

- Windows
- Claude Pro + Claude Code (native install, 2.1.x)
- Git for Windows 2.55 + Git LFS 3.7
- Gemini Pro
- Meshy Pro
- GitHub

#### 3D

- Blender 5.2.2 LTS
- Substance 3D Painter

Blender 5.2.2 is the current 5.2 LTS maintenance release as of September 15, 2026, with the 5.2 LTS line supported until July 2028.

#### Engine

- Unity 6000.3.24f1 (Unity 6.3 LTS)
- URP 17.3
- Official Unity plugin for Claude Code (31 skills, project scope)
- com.unity.pipeline 0.7.0-exp.1 (experimental): Editor server for the Unity CLI

The Pipeline package hooks into builds (IPreprocessBuildWithContext). If a Quest build fails in an unexplained way, remove it temporarily to rule it out.

#### XR

- Meta Quest 3S
- Unity OpenXR 1.16.1 with the Meta Quest feature
- XR Interaction Toolkit 3.3.2

Version facts about external tools (Meshy models, Unity issues, Meta recommendations) are checked again at the moment they are used. They change quickly.

## 6. Project Scope

The environment is intentionally compact.

Target:

- one primary laboratory/research room
- one connected corridor/transition area
- modular architectural system
- approximately three hero assets
- controlled secondary prop library
- reusable environment materials
- limited environmental interactions
- limited VFX
- Quest 3S optimization

The environment must support the existing Labyrinth gameplay instead of competing with it.

## 7. Visual Direction

The environment follows this palette and language:

- dark industrial structure
- engineered hard-surface forms
- dark painted metal
- black polymer
- cyan or blue emissive accents
- selective warning colors
- functional pipes
- cables
- control panels
- restrained futuristic styling
- believable industrial infrastructure

#### The drone in this palette

The drone is **not** the source of the palette. It is a worn yellow/ochre machine with grey metal and a red indicator. That is a deliberate contrast: a bright hazard-colored machine against a dark, cool facility, which keeps the enemy readable in VR.

The drone must still look as though it belongs. Tie it in through:

- **warning-yellow accents** in the environment (hazard stripes, safety markings, machine labels) using the same yellow family as the drone,
- the same **level of wear** (edge wear, dirt) as the drone's texture,
- the same **hard-surface language** (chamfered panels, vents, bolted plates),
- cyan/blue emissives in the environment as the cool counterpart to the drone's warm body.

The exact yellow values are sampled from M_Drone's textures and recorded in STYLE_GUIDE.md.

## 8. Protected Existing Gameplay

Existing gameplay is protected. Before modifying the project, Claude inspects the live Editor state of:

- scene hierarchy of BasicScene
- player rig (XR Origin)
- Labyrinth Panel and walls
- Labyrinth Ball
- drone (DroneAI2)
- projectile system (Sphere.prefab, fire point)
- interaction system
- cameras
- existing scripts
- existing materials
- build configuration
- XR configuration

Crystals/throwables are not part of the existing gameplay. If they are ever built, it is a recorded gameplay decision in PROJECT_BIBLE.md, and section 52 applies: only a few interactions, no second game.

The drone is a locked asset. Do not modify its:

- geometry
- materials
- textures
- shader
- prefab structure
- scripts
- behavior

unless explicitly decided later and recorded as a gameplay change.

## 9. Drone Protection

Three small layers, no asset management system:

1. **Claude Code deny rules** (section 11) block edits to the drone's files: Assets/Drone_Asset/, Assets/Materials/Drone_Mat_V2/, DroneHoverAIV2.cs, PropellerSpin.cs, HologramToggle.cs.
2. **DroneBaseline.md** records the verified facts, because Editor commands can still change the drone inside a scene.
3. **A lightweight validate_drone_integrity check** may be added to Validate Scene later.

```
Documentation/
└── ProtectedAssets/
    └── DroneBaseline.md
```

Record, from live reads:

- asset path: Assets/Drone_Asset/drone_low.fbx
- scene object: BasicScene / DroneAI2 / drone_low
- material: Assets/Drone_Asset/M_Drone.mat with SG_DroneOptimized (_Ring_Intensity, _Ring_Flash_Mask, _Ring_Flash_Color)
- script references and wiring: DroneHoverAIV2 (bounds, labyrinthBall, projectilePrefab, firePoint = ToShoot_low/Shoot Point, droneRenderer = Ring_low, ringSparks = Ring_low/VFX_RingSparks)
- tuning values per scene (BasicScene and RenderScene differ)
- important transforms
- Git commit

## 10. Storage

Only **C: is an SSD** (119 GB, small). D:, G: and H: are HDDs. The layout follows from that:

| Location | Content |
|---|---|
| C: (SSD) | Windows, Unity editor 6000.3.24f1 + Android modules, Claude Code. Keep ≥ 20 GB free. |
| D:\AI_Labyrinth (HDD) | Project, art files, builds, backups |
| D:\DevCache (HDD) | Unity package cache (UPM_CACHE_ROOT), Gradle (GRADLE_USER_HOME), npm cache |
| Unity Hub downloads | D: (install location stays C:) |

```
D:\AI_Labyrinth\
├── UnityProject\      Git repo: Unity project, CLAUDE.md,
│                      Documentation\, Tools\Blender\ (generator scripts)
├── Blender\
│   ├── Source\        known-good .blend files
│   ├── Working\       Claude's active workspace
│   ├── Generated\     procedural output (reproducible from scripts)
│   └── Export\        Unity-ready FBX
├── Gemini\References\
├── Meshy\ (References\, Downloads\, Archive\)
├── Substance\
├── Scripts\           one-off setup scripts
├── Documentation\     large non-versioned reference material only
├── Logs\              raw test outputs
├── Portfolio\
└── Backups\
```

If compiles or domain reloads on the HDD regularly interrupt work, fix it then: an external USB-C SSD is the clean solution; moving only Library\ to C: with a directory junction is the fallback. Excluding UnityProject\ (only that folder) from Windows Defender real-time scanning speeds up imports.

Do not assume moving the project moves every cache automatically. Substance Painter's cache is moved to D: in its own preferences.

## 11. Working with Claude Code

This section is new in V9. It is the main lever for speed, token usage and safety.

### 11.1 One execution hub

Claude Code is started in D:\AI_Labyrinth\UnityProject. It reaches Unity (plugin + Pipeline package), Blender (Blender MCP added to Claude Code) and, when useful, Meshy, in one session. Folders outside the project that Claude needs (Blender\, Meshy\, Logs\) are added as additional directories. Claude Desktop's Blender connector remains the fallback.

The Claude app chat is for planning, review and decisions. Decisions are written into the repo documents so Claude Code sees them. Nothing important lives only in a chat.

### 11.2 CLAUDE.md: short and factual

Claude Code reads CLAUDE.md at the start of every session, so every line costs tokens every time. Keep it to roughly 60–100 lines of facts and rules, and point to the longer documents instead of copying them:

- paths, main scene, Unity/package versions, build target
- the locked drone and what "locked" means
- rules: never save a scene unless asked; read Inspector values live, not from YAML; one change at a time; report git status after changes
- how to reach the Editor (unity status) and Blender
- naming (section 49), export and texture contracts (section 50), by reference
- where the detailed documents are and when to read them

### 11.3 Permission rules

Defined in UnityProject/.claude/settings.json and committed:

- **Allow without asking:** read-only commands such as ls, cat, grep, head, wc, git status / diff / log, unity status / list and read-only unity queries.
- **Deny:** git push --force, git reset --hard, rm -rf, and Edit/Write on the drone's files (section 9).
- **Ask (default):** everything else, including all edits and Editor-changing commands.

Auto mode is not used until the workflow has proven reliable. The exact rules are written and tested in production step 2.

### 11.4 Scripts over many small calls

Every Editor call, MCP call and screenshot costs tokens. The efficient pattern is:

`Claude writes one script → Run it → Read a short text result → Fix and re-run`

Blender generators and validators are Python scripts run headless. Repeated Unity operations become an Editor script or menu item. Live connections are used mainly to inspect and verify. Scripts are text, so Git tracks them, and they are better portfolio evidence.

### 11.5 Session habits

- One task per session. /clear between unrelated tasks; /compact when a long task must continue.
- claude --continue only when the previous context is really needed.
- Plan mode (Shift+Tab) for anything larger than a small change: approve the plan, then execute.
- Subagents for broad read-only searches, so the main session stays small.
- Validators print short summaries (PASS/FAIL lines), not full dumps.
- Lighter model for routine work, strongest model for hard problems (/model).
- Claude Pro has usage limits. Check actual usage after the first working days and adjust habits or plan if limits become a bottleneck.

### 11.6 Skills and slash commands before Editor tools

If a repeated workflow is really a checklist, a small project skill or slash command in .claude/ is enough (minutes to write). A C# Editor tool is built when it needs to run without Claude, gives the game real value, or is meaningful portfolio evidence.

### 11.7 Verify, then trust

Claude reports what it confirmed and what it only expects. Anything that matters (Inspector values, build results, performance numbers) is verified live, in the Editor, or on the Quest.

### 11.8 Development log

At the end of each working session Claude appends about five lines to Documentation/DEVLOG.md: what was done, decisions, problems, next step. This becomes most of the portfolio write-up.

## 12. Claude Project Knowledge

Create only (inside the Unity repo, so they are versioned and visible to Claude Code):

```
UnityProject/
├── CLAUDE.md                 short facts + rules (always loaded)
├── .claude/settings.json     plugin + permission rules
└── Documentation/
    ├── PROJECT_BIBLE.md       defines the game and gameplay decisions
    ├── ENVIRONMENT_SPEC.md    dimensions and modular rules
    ├── ASSET_RULES.md         asset production rules
    ├── STYLE_GUIDE.md         palette, materials, shapes, visual language
    ├── EXPORT_CONTRACT.md     scale, axes, pivots, export settings
    ├── DEVLOG.md              session log
    └── ProtectedAssets/DroneBaseline.md
```

These documents start from the verified state in section 3, not from assumptions. Do not build a large project-knowledge framework.

## 13. Git Strategy

Git is the rollback mechanism. The Unity repo stays inside UnityProject\ with its existing GitHub history.

#### Git LFS

Git LFS tracks binaries (fbx, png, tga, exr, psd, wav) only under Assets/Environment/, where all new environment assets go, plus *.blend and *.spp everywhere. Existing binaries stay in normal Git; tracking them globally would make every existing texture and model show as modified.

#### Art files

Blender generator scripts live in UnityProject/Tools/Blender/ (text, versioned). Generated and exported files can be recreated from the scripts. **Decision (22 Sep 2026): no second Git repo.** Hand-made art (hero .blend files, Substance projects) is copied to a second physical disk (G:) with a small script at the end of a work session, optionally to OneDrive as well. Reason: GitHub's free LFS quota (~1 GB) is too small for Substance projects. Watch the LFS quota for Assets/Environment/ too; if GitHub warns, stop using LFS for new files.

#### Checkpoints

`baseline ✓ → unity-working → quest-baseline → blender-working → greybox → hero-assets → environment-complete → quest-optimized → final`

Create a checkpoint before: Unity or package upgrades, major XR changes, large scene modifications, mass asset imports, major material-system changes, final optimization.

Commit each deliberate change separately with a clear message. Never force-push. Fetch before pushing; if GitHub has other commits, inspect them first, then pull --rebase.

Do not build a custom rollback system.

## 14. Unity Connection

Use the official Unity Claude Code plugin first. Do not create a custom Unity MCP framework.

Live Editor control needs the com.unity.pipeline package in the project (installed through unity pipeline install, pinned version). The Editor must be open; unity status shows it as ready.

### First Unity Test

| # | Test | Status |
|---|---|---|
| 1 | Read-only inspection of structure, scenes, XR, render pipeline, objects, scripts, drone | Passed (file-based) |
| 1b | Live read of the drone components in BasicScene and RenderScene | Passed (live) |
| 2 | Create temporary cube AI_Test (scene not saved) | Passed |
| 3 | Move it | Passed |
| 4 | Delete it | Passed |
| 5 | Create a sandbox C# script, compile, survive domain reload, read Console, delete it | Passed |

All tests passed on 22 September 2026 and unity-working is tagged. Quirks found (create_gameobject has no position argument, delete_gameobject has no --confirm flag, Git Bash path rewriting) are recorded in CLAUDE.md.

### Domain Reload Strategy

`Modify → Compile → Wait → Reconnect / verify (unity status) → Continue`

If the official integration handles this reliably, no special framework is needed. If a specific reconnect problem repeatedly wastes time, add a small solution only then.

## 15. Blender Connection

Use Blender's official MCP server as the Blender connection and add it to **Claude Code**, so Unity and Blender work happen in one session. The official Blender MCP requires Blender 5.1 or newer, so Blender 5.2.2 is suitable.

`Blender → Edit > Preferences > Add-ons → Blender MCP → Start MCP Server → Add server to Claude Code → Test`

For generation and batch work, Claude prefers headless runs (blender -b --factory-startup -P script.py). The MCP connection is used for inspection, screenshots and interactive corrections. Claude Desktop's Blender connector is the fallback.

**Verified setup (22 Sep 2026):** the server is the one shipped with the Claude desktop extension. Its .exe launcher fails from that folder, so Claude Code starts it through the extension's own Python with PYTHONPATH set to the extension folder, registered at local scope. If a desktop-app update moves the extension, register it again.

## 16. Blender Safety

Blender's official documentation warns that the MCP server executes LLM-generated code without built-in safeguards against destructive operations or data exfiltration. Therefore:

- keep the project isolated
- use Git and the Source/Working split
- save before large operations
- do not expose sensitive directories to the workflow
- use Working files for experimental operations

Do not build an elaborate security system. Good backups are the practical protection.

## 17. Blender Working Structure

```
Blender/
├── Source/
├── Working/
├── Generated/
└── Export/
```

- **Source** = known-good
- **Working** = Claude's active workspace
- **Generated** = procedural output
- **Export** = Unity-ready output

This prevents experimental operations from becoming the only copy.

## 18. Blender Procedural System

This is the main custom Technical Art feature: a reusable modular environment generator written as a **Python script** (bpy/bmesh), not as Geometry Nodes. Claude writes and edits Python reliably; node graphs are hard to author as text. The script is the source of truth, lives in UnityProject/Tools/Blender/, runs headless and can be shown line by line in the portfolio.

Generate approximately:

- Wall_A
- Wall_Panel
- Wall_Corner
- Wall_Door
- Floor_A
- Ceiling_A
- Pillar_A
- Trim_A
- Pipe_Straight
- Pipe_Corner
- Pipe_Junction

The system uses explicit dimensions and consistent pivots, read from one parameter block that matches ENVIRONMENT_SPEC.md.

## 19. Why the Blender System Matters

It directly solves a production problem: how can the environment architecture be changed quickly without manually rebuilding every structural asset?

It demonstrates procedural modeling, Python, modular environment design, parameterization, production automation and Technical Art thinking.

## 20. Modular Environment Rules

Define in ENVIRONMENT_SPEC.md:

- module width
- module height
- wall thickness
- ceiling height
- doorway dimensions
- pillar dimensions
- pipe clearance
- player clearance
- Labyrinth clearance
- drone flight volume (DroneBounds) clearance

Every architectural element follows these rules.

## 21. Blender Procedure

`Requirement → Claude → Python generator (headless) → Generate → Inspect (MCP / render) → Correct parameters → Save → Export`

No generalized procedural framework is required.

## 22. AI Asset Generation Strategy

Use AI generation primarily for: industrial machinery, control terminals, unusual equipment, secondary props, decorative mechanical objects.

Do not use AI generation for architectural modules that require exact dimensions.

## 23. Gemini Role

Gemini produces visual references: concepts, reference images, variations, material references, signage, decals, hero asset exploration, multiple views. References follow the palette in section 7.

`Gemini: what should it look like? → Claude: how should we produce it?`

## 24. Meshy

Meshy is the primary AI 3D generator. It generates **candidate models**. It does not determine whether the model is production-ready.

#### Default generation decision

| Situation | Use |
|---|---|
| Good single reference | Image-to-3D |
| Multiple useful views | Multi-Image-to-3D |
| Need better topology control | Test Smart Topology |

As of V8: Meshy's API listed meshy-7.1 as the standard model and meshy-t2 for Smart Topology (target face count 100–15,000; the actual result can deviate). The August 2026 update introduced Meshy 7, Meshy 7 Texture, Meshy 6 Lite, faster Smart Topology (about 2 s) and semantic segmentation. Check these facts again at initialization.

**Meshy face count is not the final Unity triangle budget.** Blender and Unity remain the final authorities.

#### Model selection at initialization

1. test the currently available standard model;
2. test Smart Topology;
3. compare results on one or two representative props;
4. record the selected configuration in ASSET_RULES.md.

Do not hard-code "latest" as the final production model.

## 25. Meshy vs Tripo

Tripo is **not** a required production dependency. The project already contains an earlier Tripo drone import (inactive), so some Tripo experience exists. A small benchmark on one representative asset is optional if it costs little:

- silhouette
- part separation
- topology
- cleanup time
- UV quality
- final triangle count
- visual fidelity
- total production time

Use the result, not vendor marketing. Tripo remains an **optional benchmark**, not a pipeline replacement.

## 26. Explicitly Excluded 3D Technologies

**MeshAnything V2:** research-oriented retopology with constrained output and significant local compute requirements. **TRELLIS 2:** high hardware requirements. Neither is part of the production path.

## 27. No Universal Face Rule

Asset complexity depends on silhouette, viewing distance, material complexity, object size, importance, animation and scene context. A large hero machine should not automatically receive the same budget as a small background prop. The final budget is determined experimentally, against the Quest baseline.

## 28. AI Prop Pipeline

`Asset need → Claude specification → Gemini reference → Meshy → Candidate model → Blender → Cleanup → Technical check → Substance if needed → Unity → Prefab → Quest`

## 29. Hero Asset Pipeline

Approximately three hero assets: **Hero 01** large industrial machine · **Hero 02** control terminal · **Hero 03** facility door.

Hero assets receive stronger references, better silhouette control, more careful material work, stronger composition, additional cleanup and more portfolio documentation.

## 30. Blender Production Gate

Every AI-generated model passes through Blender before final Unity integration. Check: dimensions, scale, pivot, normals, topology, UVs, materials, object count, collision strategy, LOD strategy, export.

Do not attempt to make every AI mesh perfect through a large automatic repair system. If the geometry is fundamentally wrong: **regenerate it.**

## 31. Minimal Blender Validation

A small headless Python validator reports: triangles, vertices, objects, non-manifold geometry, UV presence, material count, scale, bounding box, collision status, LOD status. Output stays short:

```
LAB_PROP_TERMINAL_03
Triangles: 5,842
UV: PASS
Scale: PASS
Materials: 2
Collision: PASS
LOD: PASS
RESULT: PASS
```

This is enough.

## 32. Artistic Validation

Technical validation is not artistic validation. After the technical pass, ask: Does it look like the reference? Does it belong to the environment? Does its silhouette work? Does it have the right visual language? Does it improve the scene? Is it worth keeping? An asset can technically pass and still be rejected.

## 33. Substance Painter Strategy

Substance Painter is a production tool, not a separate automation project. Use it primarily for hero assets, distinctive surfaces, controlled wear, dirt, damage, edge treatment and presentation-quality materials. For simple secondary props, reusable Unity materials may be sufficient. Do not automate Substance until repeated manual work proves that automation is worthwhile.

## 34. Environment Material System

Build a reusable material family: M_IndustrialMetal, M_PaintedMetal, M_Concrete, M_Plastic, M_Rubber, M_Glass, M_Emissive, plus M_WarningPaint for the yellow hazard accents (section 7).

Use a reusable Shader Graph master material where practical. Parameters can include tint, dirt, damage, wetness, emission strength, emission color and edge wear. Keep the shader simple enough for Quest. Use a documented packed mask convention (like the drone's Metallic/AO/Smoothness mask).

## 35. Emissive Strategy

Emissive materials are useful for control panels, machine indicators, status lights, warning lights and futuristic accents. Bloom is **not required**. Do not add bloom merely because something is emissive. Meta's Vulkan subpass documentation lists Bloom among effects that cannot be implemented through subpasses.

## 36. Shader Stereo Rule

Shader Graph is the default. Custom HLSL only when necessary; then follow Unity's stereo rendering requirements. Do not invent custom stereo logic.

## 37. Unity Environment Assembly

`Inspect Labyrinth (live) → Create Environment Root → Build Greybox → Import Architecture → Create Prefabs → Add Hero Assets → Add Secondary Props → Materials → Lighting → VFX → Interactions → Validation`

Claude performs as much of this as the official Unity integration reliably supports, preferring Editor scripts for repeated steps (section 11.4).

## 38. Unity Technical Art Tools

Only create tools for operations that repeatedly consume time. Initial maximum:

```
Labyrinth Tools
1. Import / Setup Asset
2. Validate Selected Asset
3. Validate Scene
4. Build Quest Test
```

For each, first check whether a Claude Code skill or slash command is enough (section 11.6). Build the C# Editor tool when it must run without Claude or has real portfolio value. Do not build more until a real workflow problem appears.

#### Import / Setup Asset

Can eventually handle import, naming checks, material assignment, collider setup, prefab creation and basic importer settings. The exact features are determined by actual repetition.

#### Validate Selected Asset

Checks: asset exists, correct scale, UV exists, material exists, triangle count, collider, LOD where required, naming. Output simple and readable.

#### Validate Scene

Checks: missing references, missing scripts, missing materials, obvious oversized assets, unexpected objects, expensive rendering risks, collisions, drone integrity (against DroneBaseline.md), build scene list. Do not build a giant static-analysis framework.

#### Build Quest Test

`Save → Validate → Build → Deploy`

Meta's Quest workflow uses Unity Build Profiles and supports deploying builds to connected Quest devices.

## 39. Environment Passes

#### Pass 1: Greybox

Build only floor, walls, ceiling, door, corridor, gameplay area. Questions: Is the Labyrinth readable? Can the player move comfortably? Does the drone work? Does the room have the right scale? Does the architecture feel believable? Do not polish yet. **Test on Quest.**

#### Pass 2: Hero Assets

Add machine, terminal, door. Focus on composition, visual hierarchy, player viewpoint, lighting and the relationship with the Labyrinth.

#### Pass 3: Secondary Dressing

AI-generated crates, tools, cabinets, machinery, lamps, panels, cables, containers, utility equipment. This is where AI generation saves the most manual modeling time.

#### Pass 4: Surface Language

Decals, signage, warning labels (the yellow link to the drone), dirt, damage, material variation, emissive details.

#### Pass 5: Lighting

Controlled realtime lights, baked lighting where useful, limited shadow casting, emissive materials, clear gameplay lighting. Do not optimize for desktop appearance. Optimize for Quest.

#### Pass 6: Interactions

Only a few: machine activation, button/control, door, status panel, indicator state. Avoid building a second game.

#### Pass 7: VFX

Sparks, steam, warning lights, machine indicators, subtle dust, emissive effects. Avoid excessive transparent particles and screen-space effects.

Every pass ends with a Quest build, not only the last one.

## 40. Quest XR Configuration Philosophy

The Unity 6.3 upgrade already moved the project to OpenXR 1.16.1, XRI 3.3.2 and Input System 1.20. The principle stays: **do not change a working XR stack without a reason.** The first Quest build (production step 3) establishes whether it works. Inspect XR provider, package versions, input system, controller behavior and the Quest build, then decide on any change.

## 41. Quest Rendering Optimization

Do not turn every available optimization on at once:

`Enable one → Build → Quest 3S → Inspect → Measure → Keep / disable`

This applies especially to Symmetric Projection, Foveated Rendering, Subsampled Layout, Multiview Render Regions and Vulkan-specific optimizations. Foveation is currently off; record the state of the others at the first Quest build.

#### Symmetric Projection

A legitimate multiview optimization. Enable, test on Quest, measure, keep if stable. Do not assume it is safe with every other XR optimization.

#### Foveation / Subsampled Layout compatibility test

A Unity issue affecting Quest 3/3S (open as of V8) can truncate eye viewports when Foveated Rendering, Subsampled Layout and Symmetric Projection are combined. Test that combination on the physical Quest 3S before adopting it. If artifacts appear, disable the problematic combination, keep the stable settings and record the configuration. Recheck the issue status first.

#### Vulkan subpasses

Use only with a reason. In Meta's subpass workflow, Depth Texture = OFF and Opaque Texture = OFF. These are subpass-specific rules, not universal URP rules.

#### Depth-based effects

Do not build a custom depth-subpass architecture by default. Only if an effect (e.g. scanning) needs it, implement Meta's documented approach and test on Quest.

#### Optimize Buffer Discards

Inspect Meta's current recommendation. If supported safely: enable, test on Quest, measure. Do not modify unrelated rendering systems for it.

#### Multiview Render Regions, Late Latching, SpaceWarp

Optional. Test Multiview Render Regions only when the scene is heavy enough. Late Latching after basic performance is stable. Application SpaceWarp only if profiling shows a reason.

#### Known heavy settings

The Quest quality level currently uses 4096 shadow maps, 4× MSAA and HDR. These are the first candidates, one at a time, after the baseline.

## 42. Quest Performance Baseline

Done early (production step 3), not at the end:

`Existing Labyrinth → Quest 3S → Measure → Save baseline`

Measure where practical: FPS, App GPU time, CPU/GPU behavior, thermal behavior, throttling, stale frames, render scaling. Save the numbers in Documentation/ and compare every later pass against them.

## 43. Performance Tool and Optimization Order

Use Meta's tooling such as OVR Metrics Tool. Do not build your own performance platform.

`Measure → Identify bottleneck → Fix → Measure again`

Classify the problem first. **GPU:** shader complexity, shadows, overdraw, materials, transparency, geometry. **CPU:** scripts, physics, object count, update frequency. Do not randomly optimize both at once.

## 44. Thermal Test

Near final completion:

`Cold start → Representative scene → 15–30 minute continuous test → Monitor → Check throttling → Check stability`

## 45. Technical Art Development Rules

**Do it manually once. Repeat it. Notice the repetition. Automate it.**

`Import one asset manually → Import another → Import another → Notice repetition → Claude creates the smallest fitting tool (skill, script or Editor tool)`

Not: design a universal importer, spend three days building it, discover it wasn't necessary.

A tool is worth keeping when it saves meaningful production time, improves the game, or demonstrates a meaningful Technical Art skill. Prefer tools satisfying two or all three.

Stop developing a tool when it becomes difficult to maintain, saves almost no time, does not improve the final game, or has become an engineering exercise. Return to the game.

## 46. Human / Claude Responsibilities

**You:** creative direction, visual selection, gameplay decisions, quality judgment, final composition, performance judgment, portfolio direction, approving changes, verifying what matters.

**Claude:** planning, implementation, repetitive operations, Blender and Unity operations, C#, Python, asset processing, debugging, documentation (including DEVLOG), validation, and honest reporting of what is confirmed versus assumed.

Claude should increasingly handle the computer work. You remain the person deciding what the work should become.

## 47. Failure Strategy

`Failure → Read error → Identify cause → Fix → Test`

Git provides rollback.

- **Blender MCP unreliable:** Claude generates Blender Python, runs Blender headless, exports, continues. Blender MCP is an accelerator, never a single point of failure.
- **Meshy asset fails:** retry, modify prompt/reference, regenerate, simplify, or replace. One prop never blocks the environment.
- **Unity connection fails:** check unity status and the Editor; if needed remove com.unity.pipeline temporarily. Claude can still write C#, create Blender assets and prepare files; you can do small Unity operations manually. The game remains viable.
- **Quest build fails:** read the build log; suspects in order: build settings, Android/XR settings, the Pipeline package build hook.

## 48. Production State

Do not create an asset-state machine. A practical folder structure (References, Generated, Processed, Final) plus a short note per asset (source, generation method, processing, final triangle count, texture resolution) is sufficient.

## 49. Asset Naming

Stable IDs, identical in Blender and Unity:

```
LAB_ENV_Wall_A_01
LAB_ENV_Pillar_A_01
LAB_ENV_Pipe_Straight_01
LAB_PROP_Terminal_03
LAB_PROP_Machine_01
LAB_PROP_Crate_04
```

## 50. Scale / Export and Texture Contracts

1 Unity unit = 1 meter. Blender uses metric units. Document scale, axis convention, origin rules, pivot rules and export settings in EXPORT_CONTRACT.md. Do not guess import settings asset by asset.

Color textures: sRGB. Data textures (normal, metallic, roughness, AO, masks): linear/non-color. Document the packed mask convention.

## 51. Golden Paths

#### Golden Path 1: Structural Asset

`Specification → Claude → Python generator (headless Blender) → Procedural model → Inspect → Validate → Export → Unity (Editor script import) → Prefab → Quest`

#### Golden Path 2: AI Prop

`Specification → Gemini → Reference → Meshy → Blender → Cleanup → Validate → Substance if necessary → Unity → Prefab → Quest`

#### Golden Path 3: Unity Development

`Claude → Official Unity plugin → Inspect (live) → Plan → Modify → Compile → Read Console → Test → Build → Quest`

Use Unity's built-in skills before creating custom tooling.

## 52. Scope Guard for Gameplay

Crystals/throwables, extra enemies or new mechanics are gameplay decisions. They are only added if recorded in PROJECT_BIBLE.md and they fit the budget. The environment project does not become a second game.

## 53. Production Sequence

Replaces V8's "First Production Day". Do not start by developing the Technical Art toolkit.

| # | Step | Status (22 Sep 2026) |
|---|---|---|
| 1 | Connect Claude to Unity: plugin, Pipeline package, tests 1–5, tag unity-working | Done (tag unity-working) |
| 2 | CLAUDE.md + permission rules (incl. drone deny rules) + DroneBaseline.md + turn on Git LFS | Done (commit e3a0edf) |
| 3 | First Quest build + performance baseline: add BasicScene to build, change package ID, build, fix, measure, tag quest-baseline | Needs the headset |
| 4 | Connect Blender to Claude Code; decide art-file backup | Done 22 Sep: headless Blender 5.2.2 works; Blender MCP registered in Claude Code (local scope) |
| 5 | Test Meshy (standard vs Smart Topology on one prop) | Open |
| 6 | One modular wall from the Python generator | Open |
| 7 | One AI prop through Golden Path 2 | Open |
| 8 | Both into Unity; play in Editor and on Quest | Open |

If all eight work: **stop configuring and start building the environment.**

## 54. Milestones

- **First real milestone:** a playable greybox environment around the existing Labyrinth, running on Quest, with believable scale, player clearance, drone clearance, correct gameplay, basic industrial style and functioning collision. No detailed dressing yet.
- **Second milestone:** the greybox becomes a visually coherent environment with the three hero assets.
- **Third milestone:** the environment becomes fully dressed and Quest-playable.
- **Final milestone:** the final Quest 3S build is visually polished, technically validated and performance-tested against the baseline.

## 55. Portfolio

#### Evidence captured during production

- **Art:** environment concept, greybox, final scene, hero assets, material breakdown
- **Technical Art:** Python generator (code + results), Blender/Unity workflow via Claude Code, Unity Editor tools, validation output, Shader Graph, modular architecture
- **AI:** Gemini reference, Meshy generation, Claude workflow, processed asset, Unity result
- **XR:** Quest screenshots, baseline and final performance data, optimization comparisons, final runtime
- **DEVLOG.md** as the running record

#### Positioning

Present it as: **An AI-assisted 3D and Technical Art workflow used to develop a realtime VR environment.** It demonstrates AI-assisted content creation + procedural modeling + technical art tooling + realtime environment art + XR optimization. Do not describe it as "a game made by AI."

## 56. Time Budget

Target approximately **80 hours**, stretch ceiling approximately **85 hours**. Setup ran over (a new drive layout, cleanup, Unity upgrade, the Pipeline package); the overrun is taken from contingency deliberately.

| Area | V8 | V9 |
|---|---|---|
| Connections / setup | 4 | 8 |
| Existing Labyrinth baseline + first Quest build | 3 | 4 |
| Environment concept / greybox | 6 | 6 |
| Blender modular system | 8 | 8 |
| Hero assets | 12 | 12 |
| Secondary AI assets | 8 | 7 |
| Materials / Shader Graph | 8 | 7 |
| Unity integration / Technical Art tools | 8 | 7 |
| Interactions / VFX | 5 | 5 |
| Quest optimization / testing | 8 | 8 |
| Portfolio documentation (DEVLOG reduces it) | 5 | 4 |
| Contingency | 5 | 4 |
| **Total** | **80** | **80** |

Track hours roughly in DEVLOG.md so the budget stays honest.

#### Extra time priority

1. Better hero assets.
2. Better environment composition.
3. Quest optimization.
4. Better Blender procedural tooling.
5. Better Unity tooling.

Do not spend additional time on abstract infrastructure.

## 57. The Technical Art Balance

**Artist side:** design, model, texture, compose, light, optimize. **Technical side:** parameterize, automate, script, build tools, validate, optimize, integrate AI into production. That combination is the intended portfolio signal.

## 58. Minimum Custom Toolset

```
BLENDER   Modular Environment Generator (Python) + validator
UNITY     Labyrinth Tools (Asset Setup, Asset Validation,
          Scene Validation, Quest Build) — only where proven useful
SHADER    Reusable Environment Material System
CLAUDE    CLAUDE.md, permission rules, a few project skills
```

That is enough Technical Art infrastructure for this project.

## 59. Things Not to Build

- generalized AI orchestration platform
- universal asset state machine
- large AssetRegistry
- generalized environment dressing tool
- custom scheduler
- custom rollback engine
- elaborate error taxonomy
- automated Substance framework
- MeshAnything pipeline
- TRELLIS pipeline
- mandatory Tripo pipeline
- universal 1,600-face budget
- custom Vulkan renderer unless an actual project requirement appears
- custom Unity MCP server
- a long CLAUDE.md or large knowledge framework
- Geometry Nodes rewrite of the Python generator

## 60. Final Production Philosophy

**Small enough to understand. Powerful enough to save time. Technical enough to demonstrate Technical Art. Simple enough that the game remains the priority.**

`Idea → Reference → Specification → Generate → Blender / Unity processing → Inspect → Validate → Integrate → Play → Quest → Measure → Improve`

Whenever you are considering a new automation feature, ask: **Will this make the game faster to build, make the game better, or demonstrate a meaningful Technical Art skill?** If yes, build it. If not, keep working on the game.

## 61. Definition of Done

**Game:** Labyrinth gameplay works; drone works; player works; the few environment interactions work.

**Environment:** research facility feels coherent; architectural kit is consistent; hero assets are strong; secondary assets add richness; lighting is intentional; materials follow the palette; the drone reads as belonging; VFX are controlled.

**Technical Art:** Python modular generator exists; Unity tools exist where they proved useful; material system is reusable; asset validation exists; AI-assisted workflow is documented.

**AI:** Claude Code actively operates Unity and Blender; Gemini provides references; Meshy generates useful candidate assets.

**XR:** Quest 3S build works; XR configuration is stable; rendering options have been tested rather than blindly enabled; performance has been measured against the baseline; thermal behavior has been checked.

**Portfolio:** final environment, hero assets, procedural modeling, Unity tools, Shader Graph, AI workflow, Quest optimization evidence, DEVLOG.

## 62. Final Principle

**The project is a game.**

**The Technical Art tools make the game faster and better.**

**The AI tools make the artist more productive.**

**The automation never becomes more important than the final game.**
