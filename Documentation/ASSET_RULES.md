# Asset Rules
Owner decision 2026-09-26. The project is also a 3D-art portfolio piece: assets are
built the way a professional does it for a standalone VR headset (Quest 3S).

## Tiers
| Tier | Assets | Standard |
|---|---|---|
| Hero (strict) | Cradle, ServiceArm, Terminal, LeverStand, Gate | everything below |
| Secondary | props (incl. Meshy-sourced), labyrinth panel/handle/stand | clean, lighter (see Secondary) |
| Architecture kit | walls, floors, ceilings, pillars, trims | tiling materials + trim sheet, world-scale UVs (1 unit = 1 m), no unique bakes |
| Greybox | blockouts, temporary geometry | function only, no standard |

## Hero standard
### Modelling
- Real-world scale and pivots per HERO_SPEC. Moving parts are separate meshes with
  origin on the hinge.
- Quads in the working .blend. Triangles only where deliberate (terminating a loop on a
  flat face). No n-gons in any export. No poles on curved shading surfaces.
- Silhouette gets geometry; surface detail (bolts, seams, vents, small bevels) goes
  into the normal map from the high-poly.
- Large exposed edges get a one-segment chamfer (~8 mm) on the low-poly for edge
  highlights. Everything smaller is baked.
- Depth rule (owner decision 2026-09-28): on visible surfaces, recesses and protrusions
  deeper than ~15 mm are modelled as geometry; shallower detail goes to the normal map.
  Reason: in VR, stereo depth makes large baked-only detail look flat at 1-2 m.
- Round shapes: **32 segments for Ø >= 0.5 m, 16 for Ø 0.2-0.5 m, 8-12 below 0.2 m**
  (owner decision 2026-10-04, Cradle Step 6c). Reason: the high-poly is truly round, so it
  bulges r(1 - cos(180°/n)) out of the low between two corners: on a 16-gon of Ø 1 m that is
  9.9 mm, which bakes as normal slivers at the foot of every facet and a cornered outline;
  at 32 it is 2.5 mm, about one texel at hero density. Interactive close-up parts, e.g. buttons:
  up to 24 segments (owner decision 2026-11-03; the Gate button and bezel use 24). A small part that is one continuous
  stack with a larger one (e.g. pin caps on a drum) keeps the stack's count. Where round and
  straight forms meet, match vertex counts so the transition is quads; where the counts
  cannot match on a flat face, bridge quad-first (triangles only where the counts force them).
- Stacked forms prefer continuous geometry. Separate intersecting elements are
  allowed where cheaper (pins, small bolts as geometry), but every fully hidden face
  (floor contact, covered areas, inside intersections) is deleted and gets no UV space.
- No duplicate vertices, zero-area faces, loose geometry, flipped normals, or
  non-manifold edges (deliberate open borders such as a deleted floor face are
  allowed and reported).
### Normals and baking
- Low-poly: sharp edges only where there is a UV seam. Custom normals exported.
  Triangulated on export; the SAME low file goes to the bake/texturing tool and Unity.
  Tangents: MikkTSpace.
- **Scope of the rest of this section: hero workflow v2 only (the Cradle).** Heroes on
  workflow v3 (ServiceArm, Terminal, LeverStand, Gate) have no high-poly, no cage, no ID map
  and no Substance step: their small detail and materials are baked in Cycles onto the low
  itself; see "Hero workflow v3" for their steps and checks.
- High-poly (bake source): low-poly + bevels (2-3 segments) + detail, floaters allowed.
  Low/high meshes named <Part>_low / <Part>_high so bakes match by name.
- Bakes in Substance Painter (v2): Normal (OpenGL), World Normal, AO, Curvature, Position,
  Thickness, ID.
- Hero bake checks, workflow v2 (Step 6d; `cradle_v2_bake_final.py -- verify`), all PASS before a Substance export:
  - Cage both ways: every high vertex inside the cage, and no cage sample point inside the high over a visible low point (contact-line samples within 1 texel tolerated).
  - ID per feature: every feature of the HERO_SPEC ID table selects faces and all of them carry its colour (flat fills included); the FBX carries the same colours.
  - AO black scan on the verification bake: visible texels with AO < 0.05 may only form contact lines (<= 2 texels thick); any patch is a FAIL.
  - Checks and the verification bake use the export-identical triangulated high (Step 6g; `verify` FAILs if the bake file's high and the exported high differ).
### UVs
- One texture set (one material) per hero where possible: fewer draw calls, SRP Batcher.
- Texel density: hero target 512 px/m (5.12 px/cm) at 2048. Large heroes (> 2 m across)
  on one 2048 set: >= 400 px/m is acceptable; the achieved value is recorded in HERO_SPEC
  (owner decision 2026-10-03). Labyrinth panel/handle 1024 px/m (hand-held); secondary
  256 px/m. Tolerance +/-10%; rarely seen faces may go lower.
- Seams follow the hard edges; no fixed island count. Seams avoid front-facing and
  main-view areas (hidden places, back, sides). Rectangular shells straightened and
  aligned to U/V. Report distortion.
- Padding at 2048: 8 px min between islands, 4 px to the border (owner decision
  2026-10-03); 8 px edge padding (dilation) in texture export. Island count and packing
  % are reported, not pass/fail.
- Overlapping UVs only for identical repeated elements (offset by 1 during baking).
- UV0 = texture. Lightmap UV (UV1) generated by Unity, and only on static parts that
  are lightmapped.
### Textures and materials (Quest 3S)
- URP Lit (or the project's master Shader Graph once it exists).
- Maps: BaseColor (sRGB), Normal (OpenGL, linear), Mask (linear, packed): R metallic,
  G AO, A smoothness. R and A match the drone's SG_DroneOptimized mask; G = AO is added
  (the drone's shader doesn't use it). In URP Lit the same texture goes into both the
  Metallic and the Occlusion slot. Emission only when needed.
- Authored at 2048 for heroes, may ship at 1024 after the Quest test; secondary
  1024 or less; power of two.
- Unity Android override: ASTC (start at 6x6 color/mask, 4x4 normal), mipmaps on.
- PBR-plausible values: non-metal albedo roughly sRGB 30-240, metal albedo bright
  (sRGB >= 180), metallic 0 or 1 except transitions (dirt, rust, worn paint).
- Palette per PIPELINE_V9 §7 and STYLE_GUIDE.md; wear level matches the drone.
### Engine
- Colliders are primitives, never the render mesh.
- LODs: none required in this room unless a hero exceeds ~10k tris; document the
  decision per asset.
- Non-moving parts marked Static where lighting/batching needs it.
- Naming per PIPELINE_V9 §49; textures T_<AssetName>_<Map>.
### Validation (per asset)
- The hero's own checker script (no generic validator exists yet; V9 §31 describes one as a
  future tool): `cradle_v2_check.py` + `cradle_v2_bake_final.py -- verify` (Cradle),
  `gate_check.py` + `gate_tex.py -- check` (Gate), one per later hero. Output: topology stats
  (quads/tris/n-gons, hidden faces, manifold) and the workflow's checks, plus renders: shaded,
  wireframe, UV layout, texel checker. These double as portfolio material.
- Artistic validation by the owner (V9 §32). Technical pass does not mean accepted.
### Source files
- A procedural hero's source is its generator script until the first hand edit. After
  a hand edit the .blend in D:\AI_Labyrinth\Blender\Source\Heroes\<Hero>\ is the
  source and the script is frozen (note it in DEVLOG). .blend and .spp files are
  backed up to G: per V9.

## Hero workflow v2 (AI as reference, clean high-poly)
Owner decision 2026-10-03, after the Cradle bake comparison (HERO_SPEC §3, Step 5b).
1. **Concept**: one concept image plus orthographic views (see "AI reference rules").
2. **AI 3D model** (Hunyuan 3D) as the **shape, measurement and colour reference only**. Originals stay
   untouched in `D:\AI_Labyrinth\Hunyuan\Downloads\<Hero>\`; import, fit and study in
   `D:\AI_Labyrinth\Blender\Source\Heroes\<Hero>\LAB_HERO_<Hero>_AI.blend` (orientation per
   EXPORT_CONTRACT, one uniform scale set by gameplay constraints, symmetry and pivot measurements,
   motion and clearance checks against live Unity data); cross-sections, dimensions and pivots into
   HERO_SPEC.
3. **Low-poly by construction** to the measurements (Hero standard above), checked against the AI model
   (see "Deviation acceptance").
4. **High-poly = low-poly + controlled bevels + clean detail** (grooves, bolts, panel seams; floaters
   allowed), modelled to the bake-size rules of the hero (detail sizes from the texel density). No AI
   geometry in the bake source.
5. **Bake** (normal, AO, ...) with a proper cage (the low pushed out just enough to enclose its high).
6. **Substance Painter** (owner): materials and wear; the AI texture is a colour reference only.

**Why v2** (Cradle Step 5b, same low, same bake settings): the AI-derived high (fitted AI mesh with
junk zones patched from the low) had **4.61 % ray misses** against **0.02 %** for the clean high; its
surfaces are wavy ("melted" edges and faces read as dents on machined metal), and the patch borders
bake as jagged lines. The clean high reads as machined metal. Transferring the AI texture is no
better: its grime layout is random and the patches show as flat grey.

**Hero workflow v1 (AI transfer) - tried, superseded 2026-10-03.** The AI high-poly was to be the bake
source (colour and normals transferred onto the clean low). Tried on the Cradle (Steps 5a/5b); dropped
for the reasons above. Its measurement steps live on in v2.

**Deviation acceptance** (owner decision 2026-09-28, replaces the hard 3 mm / 5 mm pass/fail):
- 3 mm on flat faces and 5 mm on edges stay the *reporting* limits (visible surface only).
- A hero low-poly **passes** when every over-limit area is classified as
  a) modelled (residual of a feature that is geometry), b) deliberate design difference, or
  c) AI junk (excluded from the bake), **and** the unclassified visible area deviating more than
  15 mm is **< 0.5 % per part**.

**Fallback**: if the AI shape cannot be used (contradicts the mechanism, unreadable detail, more
cleanup than rebuilding), skip it: blockout from the spec, then steps 3-6.

Lessons from the Cradle: AI meshes come normalised (~1 m) and may be thin hollow shells; split
parts can overlap at joints and carry extra cut faces; front/back and left/right are only roughly
symmetric. Mechanical fit (pivots, clearances, motion range) is the modeller's job, never the AI's.

## Hero workflow v3 (fast, Blender-textured)
Owner decision 2026-10-29. Applies to **ServiceArm, Terminal, LeverStand, Gate**. The Cradle stays on
workflow v2 (the owner textures it in Substance Painter). Code models **and** textures in Blender: no
Substance, no separate high-poly, no cage.
1. **Design**: built from HERO_SPEC and the owner's concept image; the design is approved on renders
   (Renders/<hero>_g1_*.png) before texturing starts. HERO_SPEC sizes and positions win over the concept.
2. **Low-poly** by construction (generator script, Tools/Blender/heroes/<hero>.py): real chamfers on the
   large edges and custom normals (face-area weighted, hard edges only on UV seams). Detail >= 15 mm is
   geometry (depth rule).
3. **Small detail** (< 15 mm: seams, bolts, panel lines, small bevels) is baked in Cycles from a procedural
   bevel / bump shader onto the low itself (no high-poly).
4. **Materials**: procedural Blender materials baked to **BaseColor** (sRGB), **Normal** (OpenGL),
   **Mask** (R metallic, G AO, A smoothness), **Emission** only if needed. Palette and wear per
   STYLE_GUIDE.md.
5. **Each hero is finished end-to-end** (design, low, UVs, textures, Unity import, Quest check) before the
   next one starts.

All other Hero-standard rules stay: real-world scale and pivots, chamfers, depth rule, round segment counts,
UVs at 512 px/m with the padding rules, one texture set per hero, ASTC, naming, validation renders, hero
export mode. Hero checks kept: topology (incl. hidden faces), winding / bow-tie, planarity report, and the
AO black scan on the baked AO. Added for v3 (Gate): shading check (no flat face with a corner normal more than
0.5° off its face normal), PBR value check (ranges above, metal albedo sRGB >= 180), normal-map seam check, and
a clearance sweep over every moving part's motion. Dropped with the high-poly: cage both ways, ID per feature (the materials are
assigned on the low itself).

## AI tool choice
- **Hunyuan 3D Global** (hy3d.tencent.ai): first choice for hard-surface generation, part
  splitting and texture sources.
- **Meshy**: backup, and for organic or soft shapes.
- All AI outputs are disclosed as AI-assisted (portfolio text and credits). The low-poly, UVs,
  bakes and texturing are hand work.

## AI reference rules
For concept images and views fed to an AI 3D generator:
- Few, large, readable details; small detail goes into the normal map anyway.
- Exact symmetry where the object is symmetric.
- No parts that contradict the mechanism (moving parts clear each other, pivots where the motion
  needs them).
- No text or logos.
- Orthographic views at one level camera height and one scale.
- One concept image works best as the texture-painting reference.

## Secondary standard
No n-gons, no non-manifold or loose geometry, no hidden faces, sensible tri count for
size and distance, unwrapped without visible stretching, 256 px/m (labyrinth pieces
1024 px/m), may use tiling materials, trim sheets or a shared atlas; Substance optional.
