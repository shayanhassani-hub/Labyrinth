# Docs Consistency Report

Date: 2026-11-03. **Report only, nothing was fixed.** Scope: every file in `Documentation/`
(ASSET_RULES, STYLE_GUIDE, HERO_SPEC, EXPORT_CONTRACT, ENVIRONMENT_SPEC, DEVLOG, PIPELINE_V9.md,
ProtectedAssets/DroneBaseline.md), `CLAUDE.md`, and the scripts in `Tools/Blender/`, compared
against each other and against the repo contents. State read at commit `11f3707` (main). HERO_SPEC,
STYLE_GUIDE and the Gate files were being edited in another session at the same time; re-check
those rows against the newest version.

Line numbers refer to that commit. Severity: **high** = following the text leads to wrong work or
a broken rule; **medium** = outdated or contradictory, but a careful reader can resolve it;
**low** = wording, stale references, cosmetic.

## Findings

| # | File | Section / line | Issue | Suggested fix | Severity |
|---|---|---|---|---|---|
| 1 | HERO_SPEC.md | §4 Working pose, l.455–459 (also DEVLOG l.175) | "Propellers start at \|x\| ≥ 0.44, so the arm stays inside \|x\| < 0.3" uses the **static** blade position. Recomputed from `drone_low.fbx` + DroneBaseline transforms: spinning discs (r 0.327) reach \|x\| 0.287 at yaw 0 and **0.055 / 0.060** when docked at −28.3°, not ≈ 0.14 as the 2026-09-28 note says. No yaw keeps them outside 0.3. | Replace the plan strip with a 3D clearance rule; full analysis and replacement text in `Proposals/ServiceArm_S4_Proposal.md`. | high |
| 2 | ASSET_RULES.md | Hero standard → "Normals and baking", l.40–52 | Written as the rule for **all** heroes (high-poly bake source, `<Part>_low/_high`, Substance bakes, cage both ways, ID per feature, `cradle_v2_bake_final.py -- verify`). Hero workflow v3 (l.138–159) drops the high-poly, cage, ID and Substance for ServiceArm, Terminal, LeverStand and Gate. Someone who reads only the Hero standard follows the wrong workflow. | Label l.44–52 "workflow v2 (Cradle) only" and add one line: "v3 heroes: see Hero workflow v3 (Cycles bake onto the low, no high-poly, no cage)". | high |
| 3 | ASSET_RULES.md | l.46 | "Bakes in Substance Painter: Normal, World Normal, AO, Curvature, Position, Thickness, ID" contradicts v3 step 3–4 (procedural Blender materials baked in Cycles, no Substance). | Same scoping as #2. | high |
| 4 | PIPELINE_V9.md (+ Pipeline_V9.docx) | §3 l.113 "Locked drone", l.137; §8 l.264–274; §9 (deny rules); §11.2 l.349 | The drone is still described as a locked asset with deny rules on its files. Owner decision 2026-09-25 removed the lock (CLAUDE.md, HERO_SPEC §10/§11); `.claude/settings.json` no longer has drone deny rules. | Add a "superseded 2026-09-25: drone and gameplay are normal editable code" note to §3, §8 and §9 (and in the .docx, which the header names as master). | high |
| 5 | DEVLOG.md | 2026-10-13…10-29, l.245 | Decision "model all heroes first, Substance texturing afterwards" contradicts ASSET_RULES v3 step 5 (2026-10-29): "each hero is finished end-to-end … before the next one starts". The Gate (G1/G2) was built the v3 way. | Next DEVLOG entry: record that v3 (end-to-end per hero) replaces "model all first" for the v3 heroes; Cradle stays on v2. | high |
| 6 | DEVLOG.md | end of file, l.249–252 | No entry for hero workflow v3, STYLE_GUIDE, Gate G1 and G2 (commits `11438ed`, `11f3707`). The last entry still lists STYLE_GUIDE.md as open and says "Next: Service Arm", but the Gate was built next. | Add a 2026-10-29 entry (v3, STYLE_GUIDE, Gate G1/G2, tris/px/m, next step). | medium |
| 7 | HERO_SPEC.md | l.3 status line | "v6, 2026-09-25 — all design decisions resolved" is outdated: §3 is v2 (2026-09-28 onward), §7 has G1/G2 (2026-10-29), §4 has an open conflict. | Update the status line (version, date, open items: §4). | medium |
| 8 | HERO_SPEC.md | §3 heading l.41, status l.43 | "Cradle, v2 (AI transfer workflow)" and "Step 2 of … ASSET_RULES 'Hero workflow v1'". ASSET_RULES says v1 was superseded on 2026-10-03 and the Cradle is on **workflow v2** (AI as reference, clean high-poly). | Rename to "v2 (hero workflow v2)" and add "v1 superseded 2026-10-03". | medium |
| 9 | EXPORT_CONTRACT.md | Hero mode, l.118–148 | Hero mode was verified only with the **superseded** Part 1 cradle (540 / 68 / 36 tris, HERO_SPEC §3a) and `CradleBuilder.ApplyImportSettings()`. `Assets/Environment/Heroes/Cradle/` still holds only the Part 1 FBX files; Cradle v2 and the Gate have not been imported or verified in Unity. | Mark as "verified with Part 1 only"; re-run the vertex/normal/tangent comparison on the first v2/v3 hero import and record it here. | medium |
| 10 | ASSET_RULES.md ↔ Tools/Blender/heroes/gate_tex.py | ASSET_RULES l.77–78; gate_tex.py l.641, l.649; HERO_SPEC §7 G2 "metal ≥ 175: all" | ASSET_RULES requires metal albedo **sRGB ≥ 180**; the Gate PBR check tests ≥ 175, and HERO_SPEC reports the pass against 175. | Use 180 in `gate_tex.py -- check` (and HERO_SPEC), or record 175 as a deliberate tolerance in ASSET_RULES. | medium |
| 11 | PIPELINE_V9.md | §6 l.207, §29 l.616 | "Approximately three hero assets" (machine, terminal, door). ASSET_RULES tiers and HERO_SPEC define **five**: Cradle, ServiceArm, Terminal, LeverStand, Gate. | Update §6/§29 to the five heroes. | medium |
| 12 | PIPELINE_V9.md | §4 l.157, §24–25, §28 l.612, §51 Golden Path 2 | Meshy is the AI 3D generator in every path. ASSET_RULES "AI tool choice": Hunyuan 3D first choice for hard surface, Meshy backup / organic. | Add Hunyuan to §4/§24 and the paths, or point to ASSET_RULES. | medium |
| 13 | PIPELINE_V9.md | §33, §29 | Substance Painter as the hero texturing tool. ASSET_RULES v3: four of five heroes are textured in Blender (Cycles bakes); only the Cradle uses Substance. | Add a v3 note to §33. | medium |
| 14 | PIPELINE_V9.md | §3 l.110 and l.115, §53 l.879 | "Package ID still com.unity.template.vr", "never been built or run on the headset", step 3 "Needs the headset". DEVLOG 2026-09-22/24: package ID changed, first APK built, greybox and labyrinth tested on Quest. The performance baseline is still open. | Update the §3 table and §53 status (step 3: build done, baseline open). | medium |
| 15 | PIPELINE_V9.md ↔ ASSET_RULES.md ↔ HERO_SPEC.md ↔ CLAUDE.md | V9 §49 l.832–843; ASSET_RULES l.85; HERO_SPEC §2; CLAUDE.md l.88 | ASSET_RULES sends naming to V9 §49, which has only `LAB_ENV_` / `LAB_PROP_` (example `LAB_PROP_Terminal_03`). HERO_SPEC uses `LAB_HERO_<Hero>_<Part>_01`; CLAUDE.md also lists only ENV/PROP. | Add `LAB_HERO_<Hero>_<Part>_<NN>` and `T_<AssetName>_<Map>` to §49 and CLAUDE.md; drop the Terminal-as-prop example. | medium |
| 16 | ASSET_RULES.md ↔ PIPELINE_V9.md ↔ Tools/ | ASSET_RULES l.87 "V9 §31 validator output"; V9 §31 | V9 §31 describes one generic headless validator (tris, UV, scale, materials, collision, LOD → RESULT). No such script exists in `Tools/`; validation is per hero (`cradle_v2_check.py`, `gate_check.py`, `gate_tex.py -- check`) and does not report collision/LOD. | Either point ASSET_RULES to the per-hero checkers, or add the generic validator to the roadmap. | medium |
| 17 | HERO_SPEC.md ↔ STYLE_GUIDE.md | HERO_SPEC §2 palette rule, §3 pads, §4 ToolHead, §6 grip ("amber", "amber-yellow") | STYLE_GUIDE names that material **Ochre** (159 120 58, drone median) and uses **Amber** for the small lamps (emission 240 150 60). "Amber pad" can be read as the lamp colour. | Use "ochre" for drone-handling parts in HERO_SPEC; keep "amber" for lamps/indicators only. | medium |
| 18 | DroneBaseline.md | title l.1, purpose l.3 | "Drone Baseline (locked asset)", "record of the locked drone". CLAUDE.md: it is a reference of the last verified state, not a lock. | Retitle "Drone Baseline (last verified state)". | medium |
| 19 | ASSET_RULES.md | v3 "Hero checks kept", l.156–158 | Lists topology, winding/bow-tie, planarity and AO black scan. The Gate also runs the shading check (corner-normal ≤ 0.5°), PBR value check, normal-seam check and the clearance sweep; they are not in the rule. | Add them to the v3 check list. | low |
| 20 | ASSET_RULES.md ↔ HERO_SPEC.md | ASSET_RULES l.26 (8–12 segments below Ø 0.2 m); HERO_SPEC §7 (button Ø 70 mm and bezel Ø 110 mm at 24 segments, lamp 16) | The Gate's small round parts exceed the segment rule. Probably deliberate (close-up interactive parts), but not recorded as an exception. | Record the exception in HERO_SPEC §7, or extend the rule ("interactive close-up parts: up to 24"). | low |
| 21 | Tools/Blender/heroes/gate_tex.py | docstring l.17 | Says the convex-edge pre-bake uses "6 mm"; the code uses `EDGE_DIST = 0.008` (l.49) and HERO_SPEC §7 G2 says 8 mm. | Fix the docstring to 8 mm. | low |
| 22 | PIPELINE_V9.md | §56 time budget | 80 h total, heroes 12 h. DEVLOG 2026-09-27: the V9 time budget is no longer used. | Mark §56 as retired. | low |
| 23 | PIPELINE_V9.md | §8 l.262, §12 l.404, §52 l.869 | References `PROJECT_BIBLE.md`, which does not exist. Gameplay decisions live in HERO_SPEC §11. | Point to HERO_SPEC §11 (or create the file). | low |
| 24 | PIPELINE_V9.md | header l.1 | The Markdown copy says the .docx is the master and both are updated together; the Markdown is dated 22 Sep and carries all the drift above. | When fixing #4, #11–#14, #22, update both or declare the Markdown the master. | low |
| 25 | CLAUDE.md | l.23 | "Inactive leftovers DroneAI and Drone (Tripo) are not the game drone." HERO_SPEC §10: deleted by the owner on 2026-09-25. | Replace with "deleted 2026-09-25". | low |
| 26 | ENVIRONMENT_SPEC.md | l.98 | Lists the "labyrinth stand" among the heroes. HERO_SPEC §8 says panel, stand and handle are props, and ASSET_RULES puts them in the Secondary tier. | Remove "labyrinth stand" from the hero list. | low |
| 27 | ENVIRONMENT_SPEC.md ↔ env_kit_generator.py | ENVIRONMENT_SPEC l.3–5; generator docstring | The spec says the generator "must read its parameters from this file"; the generator uses a parameter block **copied** from the spec. | Change the spec text to "copied into the generator's parameter block; keep both in sync". | low |
| 28 | HERO_SPEC.md ↔ STYLE_GUIDE.md | §1 Armed, §9 atmosphere ("orange" accent lights) | STYLE_GUIDE has no orange entry (amber lamp, red, cyan only). | Add the Armed/Released accent colour to STYLE_GUIDE (lighting pass). | low |
| 29 | EXPORT_CONTRACT.md | Verification checklist l.173 | "Import the FBX into `Assets/Environment/Kit/`": kit-only wording, while heroes go to `Assets/Environment/Heroes/<Hero>/` (HERO_SPEC §2). | "…into the asset's folder (Kit/, Heroes/<Hero>/, Props/)". | low |

## Not contradictions (checked)
- Drone volume X −2.45 … 2.39, Y 1.19 … 3.48, Z 2.84 … 6.32: identical in ENVIRONMENT_SPEC,
  HERO_SPEC §2 and DroneBaseline.
- Player spawn (−1, 0, 13.0) facing the gate: ENVIRONMENT_SPEC "facing −Z" = HERO_SPEC §7 "yaw 180".
- Texel density: Cradle 438 px/m (> 2 m across, ≥ 400 allowed) and Gate 487 px/m (within −10 % of
  512) both meet ASSET_RULES.
- Mask packing R metallic / G AO / A smoothness: same in ASSET_RULES, STYLE_GUIDE, HERO_SPEC §7 and
  `gate_tex.py`.
- Cyan emissive 70 170 255: STYLE_GUIDE and HERO_SPEC §7 agree.
- Git LFS for `*.blend` / `*.spp` (EXPORT_CONTRACT) is present in `.gitattributes`.
- Docked drone body centre, drone top and the 54.4 mm limb-height difference (HERO_SPEC §3/§4)
  match a recomputation from `drone_low.fbx` (see the ServiceArm proposal).

## Summary
29 findings: 5 high, 13 medium, 11 low. Most of the drift is in three places: ASSET_RULES' Hero
standard still reads as the v2 (high-poly, Substance) workflow for every hero; PIPELINE_V9 still
describes the 22 September state (locked drone, three heroes, Meshy, time budget); and DEVLOG has no
entry for the v3 / Gate work. The one geometry error (#1) is analysed in the ServiceArm proposal.
