# Hero Spec — Launch Sequence Assets

Status: **v6, 2026-09-25 — all design decisions resolved**. Design direction set by the owner; cradle sized from the live
drone measurement (2026-09-25). All values in meters, Unity axes (+Y up, +Z toward the far wall
and corridor), 1 unit = 1 m.

Inputs: `ENVIRONMENT_SPEC.md` (room, protected volumes), `ProtectedAssets/DroneBaseline.md`
(drone reference), `EXPORT_CONTRACT.md` (export/import). If a protected volume changes, re-check
every "Released" pose below.

## 1. The sequence

| # | State | Trigger | What happens |
|---|---|---|---|
| 0 | **Arrival** | scene start | Player spawns at the corridor end, (−1, 0, 13.0), facing the closed gate. Room teleport area disabled. Beyond the gate the room is already in *Standby*: drone docked in the cradle, service arm working on it, lights cyan. `DroneHoverAIV2` disabled. |
| 1 | **Gate open** | player presses the gate button (corridor wall, right of the gate) | Gate leaf slides open (2.0 s). Room teleport area enabled. The player enters and teleports along the left (−X) side of the room to the terminal. |
| 2 | **Armed** | player presses the terminal's central button | t = 0: three terminal indicators cyan → **red** instantly, red beacon on. t = 0 → 2.5 s: room accent lights cyan → **orange** (smoothstep). t = 2.5 s: service arm starts folding (2.0 s). t ≈ 4.5 s: arm stowed → lever armed (amber indicator pulses). |
| 3 | **Released** | player pulls the lever (only once armed) | Yoke arms swing open (1.2 s). t = +1.0 s: `DroneHoverAIV2` enabled (and `PropellerSpin`, once attached): the drone lifts off and the game runs. |

A lever pull before *Armed* does nothing except a short "denied" cue. The lever stays locked
until the service arm is fully stowed, so the drone can never launch into it.

## 2. Rules for every hero

- **Rigid hinges, no skinning.** Every moving part is a separate static mesh; motion is a
  transform rotation or slide between a **closed** and an **open** pose. No armatures, no
  imported animation. The export contract is unchanged.
- **One FBX per part, origin on its hinge / slide reference.** Parts are modelled in the closed
  pose and assembled into a hierarchy in Unity by an Editor builder (same pattern as
  `GreyboxBuilder`) from the tables below. Multi-object FBX hierarchies under
  `bake_space_transform` are unverified, so we don't depend on them.
- **Naming:** `LAB_HERO_<Hero>_<Part>_01`, files in `Assets/Environment/Heroes/<Hero>/`.
- **Released-state rule:** once the drone flies, nothing may intersect the drone volume
  (X −2.45 … 2.39, Y 1.19 … 3.48, Z 2.84 … 6.32). Standby poses may, because the drone is docked.
- **Palette rule:** amber-yellow marks equipment that *handles the drone* (yoke pads, service-arm
  tool head, lever grip). Everything else: dark painted metal, black polymer, cyan emissive.
  Red is reserved for the Armed state.
- **Quality:** Hero tier in `ASSET_RULES.md`. Heroes whose dimensions are fully specified (the
  Cradle) are built directly at production quality, no separate greybox.

## 3. Hero 01 — Docking cradle (`Cradle`), v2 (AI transfer workflow)

Status: **v2 spec, 2026-09-28** (Step 2 of the AI transfer workflow, ASSET_RULES "Hero workflow v1").
Supersedes the Part 1 design (§3a). Design source: Hunyuan 3D model `cradle_hy_*`
(D:\AI_Labyrinth\Hunyuan\Downloads\Cradle, originals untouched), fitted and measured in
`D:\AI_Labyrinth\Blender\Source\Heroes\Cradle\LAB_HERO_Cradle_AI.blend` (collection `AI_FIT_A`).
Scripts: `Tools/Blender/heroes/cradle_ai_*.py`. Sections: `Renders/cradle_ai_sections.png`.
All values: Unity axes, metres, cradle origin **(0, 0, 4.69)**, yaw 0. The front (pin caps
towards the viewer) faces **−Z**, towards the labyrinth and the player. "r" = distance from the
cradle axis (x 0, z 4.69).

**Fit.** Uniform scale **s = 2.5885** of the AI mesh (native → spec: x' = s(x − cx), y' = s·z,
z' = 4.69 + s(y − cy); in Blender a 180° turn about Z). s puts the front limb's pad top 3 mm under
the limb at the drone's current height. Mirror symmetry of the AI mesh: mean 0.49 mm, p95 0.92 mm
(native); one plinth defect (back-right diagonal face, up to 65 mm native). The plinth region
(y < 0.415) was symmetrized from the **−X half** (`AI_A_Static_sym`, `AI_A_TexImg_sym`, texture
mirrored with it); after: max 0.1 mm. Above the cut the mesh is untouched (mean 0.8 mm; up to
19 mm only at the splitter's cut faces on the hinge beam under the arm roots).

### Parts

| Part | Contents | Origin / pivot | Moves |
|---|---|---|---|
| `LAB_HERO_Cradle_Base_01` | plinth tiers, turntable rings, column, hinge beam, both hinge drums, pin caps, hub — one continuous static body | floor centre (0, 0, 4.69) | no |
| `LAB_HERO_Cradle_Arm_L_01` | left arm + rest plate (one mesh) | on the left pin axis: (−0.385, 0.637, 4.69), axis Z | 0 → **+75°** about local Z |
| `LAB_HERO_Cradle_Arm_R_01` | mirror image of Arm_L | (+0.385, 0.637, 4.69), axis Z | 0 → **−75°** |
| `LAB_HERO_Cradle_Pad_R_01` / `_Pad_L_01` (amber) | two instances of one mesh `LAB_HERO_Cradle_Pad_01`: 0.22 × 0.010 × 0.14, 3 mm chamfers | own bottom centre, child of Arm_R / Arm_L | with the arm |
| `LAB_HERO_Cradle_Riser_L_01` (grey metal) | riser under the left pad, 0.23 × **0.0544** × 0.15, 4 mm chamfers | own bottom centre, child of Arm_L | with Arm_L |

Unity sign: a +Z rotation turns +Y towards −X, so +75° opens Arm_L outward and −75° opens Arm_R.
Arm_L/Arm_R are two meshes (mirror copies), no negative scale. The pin itself is not a separate
part: the caps are on the static body and the arm root turns around the drum (see Hinge beam).

### Pivots (measured: cylinder fits on the pin caps, rms 0.15–0.20 mm)

| | Front cap centre | Back cap centre | Axis vs Z |
|---|---|---|---|
| Left | (−0.3869, 0.6382, 4.455) | (−0.3881, 0.6365, 4.903) | 0.26° |
| Right | (0.3827, 0.6381, 4.450) | (0.3850, 0.6364, 4.911) | 0.36° |

The two axes are 0.43° apart and symmetric within 0.8 mm. **Build value: x ±0.385, y 0.637, axis ∥ Z.**

### Dimensions for construction (from `cradle_ai_sections.png`, ray-cast profiles and plan fans)

**Plinth, tier 1** (y 0 … 0.206). Plan: axis faces at 1.214 from the axis — Z faces (front/back)
0.98 long (x ±0.490), X faces 0.88 long (z ±0.442); diagonal faces at **1.16**, joined to the axis
faces by short corner facets ((±1.214, ±0.442) → (±1.075, ±0.559) and (±0.490, ±1.214) → (±0.606, ±1.05)).
Not a regular octagon: follow these corners. Wall y 0.018 … 0.160, bottom chamfer 15 mm; top
chamfer 40 × 46 mm to the top face at y 0.203–0.206. **Top trays**: 8 (one per face), r 0.876 … 1.084,
floor y 0.160 (43 mm deep), outer wall sloped 16 mm, 0.66 (Z faces) / 0.70 (X faces) long:
geometry. **Side panels**: outline groove 10 mm, y 0.052 … 0.126, 0.60 / 0.56 long: normal map.
The AI plinth is a thin hollow shell, open underneath; the low-poly is closed, floor face deleted.

**Tier 2** (y 0.206 … 0.318). Octagon, flats 0.863 (X) / 0.843 (Z) / 0.85 (diagonal). Wall to
y 0.246, chamfer to (r 0.841, y 0.274), sloped top to (0.769, 0.288), chamfer up to a rim at
y 0.318 (r 0.744). Inner top y 0.300, octagon flats 0.75. **Trough** r 0.522 … 0.642, floor y 0.253
(47 mm deep), rounded outer edge (~12 mm).

**Turntable and rings.** Disc r 0.505 (four small notches: normal map), y 0.253 … 0.334, top
chamfer 14 mm. Ring 2 r 0.385, y 0.334 … 0.356. Ring 3 slightly elliptical 0.295 (X) × 0.267 (Z),
y 0.356 … 0.392.

**Column** (y 0.392 … ~0.72, hidden above y 0.52 by the beam). Block X ±0.18 × Z ±0.224, corner
chamfers (0.174, 0.149) → (0.118, 0.224); side tabs out to x ±0.258 (tapered, z ±0.052 at the tip).

**Hinge beam and drums.** Beam top y 0.755; depth 0.307 (z 4.538 … 4.845) for y 0.60 … 0.70, a
0.18-deep band above and below. **Drums**: cylinders r 0.117–0.119 about each pin axis, faces at
z 4.500 and 4.893 (0.393 deep), bottom y 0.52, top y 0.756. **Pin caps**: front Ø 0.13 face on a
Ø 0.16 chamfered base, **50 mm proud** (face z 4.450); back Ø 0.17 face, chamfer to Ø 0.20,
19 mm proud (face z 4.912).

**Hub** (on the beam). Collar y 0.756 … 0.810, X ±0.165 × Z ±0.152, chamfered corners; cap round
r 0.150 (16 segments), y 0.81 … 0.882, top chamfer ~20 mm.

**Arm (Arm_R; Arm_L mirrored).** Depth 0.302 (z 4.541 … 4.843), centred z 4.692. Path in the front
plane (x, y):
- *Root*: a shoe on top of the drum, concentric with the pin. The AI root overlaps the drum by
  ~20 mm; the low-poly gets a proper boss/shoe with clearance over the sweep.
- *Lower segment*: (0.46, 0.76) → elbow (0.563, 0.96), leaning **31.7° outward**; section 0.255 × 0.302.
- *Elbow*: section 0.286 × 0.301.
- *Upper segment*: elbow → (0.513, 1.42), leaning **6.9° inward**; section 0.283 × 0.301, inner
  face stepped ~20 mm (normal map or a small bevel).
- *Gusset* (y 1.42 … 1.56): outer edge flares from x 0.65 to 0.94; section at y 1.48: 0.452 × 0.301.
- *Neck* (y 1.56 … 1.588): x 0.398 … 0.94, depth 0.19 (z 4.598 … 4.788).
- *Rest plate*: y **1.588 … 1.700** (0.111 thick), x 0.280 … 1.139 (0.859), z 4.480 … 4.902 (0.422)
  including the edge rib; top flat x 0.290 … 1.110, z ±0.197. Edge: a **rib** 40 mm tall
  (y 1.624 … 1.664), 16.5 mm proud of the upper and lower bands (24 mm each); top edge chamfer ~4 mm.

Overall: plinth 2.428 across the axis faces, plate tops y 1.699 (1.764 with the left pad), plate
span x −1.139 … 1.138, fixed body top y 0.884.

### Docking pose

- **DroneAI2**: rotation Y **−28.30°**, position **(−0.032, 2.000, 4.754)** (moves 33 mm from
  (0, 2, 4.76)). Body centre then (0.003, 1.758, 4.689).
- The drone's front limbs sit 54.4 mm lower than its back limbs (flat undersides y 1.7121 / 1.7665,
  r 0.28 … 0.62 from the body centre, 0.118 wide). The yaw lines up the **front-right** limb along +X
  (onto the right plate) and the **back-left** limb along −X (onto the left plate); limb axes within
  0.9 mm of the plate centre lines.
- **Pads** (Step 3, owner decision 2026-09-28): two **identical** amber pads (one mesh, 10 mm, 0.22 × 0.14,
  along the limb from r 0.39 to 0.61, outboard of the pin). The left limb's extra 54.4 mm is a grey metal
  **riser** under the left pad (0.23 × 0.15, 5 mm larger per side), parented to Arm_L; the arms stay exact
  mirror images. Pad tops y 1.7091 (right) / 1.7635 (left); contact gap **3.0 mm** on both limbs
  (low-poly check: 3.04 / 2.97 mm); plate tops y 1.6991.
- **Plate inner edge**: 40 × 8 mm chamfer on the inner top edge (x 0.280 … 0.320), so the rising inner
  edge keeps limbs ≥ 10 mm away during the fold (low-poly: min 11.1 mm at 3°).
- Docked clearances: limbs to arms/plates ≥ 12.2 mm; engines ≥ 13.8 mm (to the right plate);
  body ≥ 49.8 mm (arms), 0.68 m (hub); spinning propeller discs ≥ 106.5 mm (pads), ≥ 116.5 mm (arms).

**Pad design study (2026-09-28, owner request).** Two identical amber saddles with a limb groove
(floor 54 mm deeper on the front-limb side) were evaluated (`cradle_ai_saddle.py`) and **rejected**:
- The groove walls must rise above the left groove floor (y ≥ 1.764) on both sides. On the right
  that leaves **37 mm** to the front propeller discs (needed ≥ 100 mm; the front props are only
  104 mm above the front limb). A short chock outside the prop discs still gave 42 mm. Groove
  tuning cannot fix this.
- The limb runs 16 mm off the body-to-engine line near its root, so a 128 mm groove also clips the
  limb (7–12 mm); fixable, but moot.

Plain pads were kept. The Step 1 pads (r 0.29 … 0.61) **failed** the fold check: their inner end
lies inboard of the pin and rises ~4 mm in the first 5° of the fold, into the 3 mm gap (−1.3 mm).
Moved outboard of the pin (r 0.39 … 0.61) they pass. During a 0 → 75° fold with the drone still
docked: pads to limbs ≥ 3.1 mm (they only fall away), engines ≥ 11.7 mm, body ≥ 162 mm, prop discs
≥ 106.7 mm; arms/plates to limbs ≥ 8.5 mm (at 5°). Renders: `cradle_v2_s2_pads_*`,
`cradle_v2_s2_saddle_rejected_front.png`.

### Release

- Each arm (with its pad) swings **outward about its pin axis by 75° in 1.2 s** (was 100°).
- Why 75°: the highest point drops below the drone volume floor (y 1.19) at 65° (right) / 70° (left,
  thick pad); at 75° it is at 1.007 / 1.023, and the plate tips stay 0.16 m above the floor. Past
  ~85° the plate's outer end hits the **floor** (80° is the last clear 5° step), and at 90–95° the
  arm hits the **plinth**. The old 100° is impossible with this design.
- Sweep checked in 5° steps with the AI geometry: no collision with the plinth or hinge blocks up to
  80°. The drum sits inside the arm's root shoe in the AI mesh at every angle (a constant ~20 mm
  overlap, not a collision); the low-poly boss needs its own clearance check over 0 … 75°.
- Protected volumes: labyrinth ≥ 1.0 m, player ≥ 2.47 m, spawn ≥ 6.5 m clear; the static body
  (top 0.884) and the released arms (≤ 1.023) stay below the drone volume.

## 3a. Superseded Part 1 design (2026-09-26)

Procedural cradle (`Tools/Blender/heroes/cradle.py`, `LAB_HERO_Cradle.blend`, `HERO_Cradle` in
BasicScene, `CradleBuilder`), kept in the project until the v2 cradle is accepted. Drone docked at
yaw 0 on its body: two narrow arms (0.06 × 0.50 × 0.18) hinged at (∓0.13, 1.04) in a clevis hub,
amber pads (0.10 × 0.025 × 0.22) 2.8 mm under the body (y 1.565), released 100° outward.
Base: octagon tiers 2.4 / 1.6, turntable Ø 0.8, column 0.30 × 0.70 × 0.30, hub 0.40 × 0.08 × 0.30.
Verified 2026-09-26 (540 / 68 / 36 tris for Base / Arm / Pad).

## 4. Hero 01b — Ceiling service arm (`ServiceArm`)

A robot arm that works on the docked drone from above and behind, then folds flat against the
ceiling. Mount **(0, 4.0, 5.30)**, 0.61 behind the body centre, so it never blocks the player's view.

| Part | Size | Hinge (parent-local) | Axis |
|---|---|---|---|
| Mount | plate 0.40 × 0.05 × 0.40 | ceiling face, body downward | — |
| Turret | cylinder Ø 0.26 × 0.07 | (0, −0.05, 0) | Y (yaw) |
| UpperArm | 0.12 × 0.12 × 1.00 | shoulder (0, −0.12, 0) | X (pitch) |
| Forearm | 0.10 × 0.10 × 0.90 | elbow, **offset 0.12 in X** | X |
| Wrist | 0.10 × 0.10 × 0.10 | wrist, offset 0.10 in X | X |
| ToolHead (amber) | 0.14 × 0.10 × 0.20 | on wrist | Z (roll) |

- **Working pose (Standby):** tool tip ~0.05 above the drone's top (y ≈ 2.04, drone top 1.986),
  pointing down, near x = 0: the propellers start at |x| ≥ 0.44, so the arm stays inside
  |x| < 0.3. **Re-check (2026-09-28):** with the v2 docking yaw (−28.3°, §3) the back-right and
  front-left prop discs reach in to |x| ≈ 0.14; re-derive the working pose and this rule. Roughly shoulder −60°, elbow +70°, wrist keeping the tool vertical. Tune by eye;
  the hard rule is only that nothing touches the drone. Reach check: 1.60 needed, 1.90 available.
- **Idle motion (Standby):** procedural, no clips: turret ±10° yaw, wrist ±15°, tool roll
  spinning, each on its own slow sine (0.2–0.5 Hz) so it never visibly loops.
- **Stowed pose:** all links horizontal, pointing +Z; the X offsets at elbow and wrist lay the
  forearm and tool *beside* the upper arm, not under it. One flat layer at **y 3.77 … 3.95**,
  0.29 above the drone volume. Stowed footprint z 5.30 … 6.30: keep ceiling lights out of it.
- **Fold:** starts 2.5 s after the terminal button, takes 2.0 s, ease-in-out.

## 5. Hero 02 — Control terminal (`Terminal`)

Against the back wall, left of centre (read from the owner's top-down sketch; position confirmed). Origin
**(−2.2, 0, −2.0)** on the wall's inner face, yaw 0: the body extends +Z into the room and the
player operates it facing the wall. Reference: a console with end pillars, sloped desk and a
display rising behind.

| Part | Size / placement (terminal-local) |
|---|---|
| Body | 2.40 × 0.90 × 0.80 (z 0 … 0.80) |
| Desk | sloped 15°: 0.92 high at the front edge, 1.05 at the back |
| Pillar_L / Pillar_R | 0.30 × 1.25 × 0.80 at each end; red beacon Ø 0.08 on Pillar_L |
| Display | 1.50 × 0.85 quad, bottom at 1.10, z 0.15, leaning back 8° |
| Button | Ø 0.12 × 0.04 in a guard ring Ø 0.20, desk centre; press travel 0.015 |
| Indicators | 6 emissive strips on the desk, cyan; 3 of them switch to red on Armed |

- **Display: see-through holo screen** (owner decision). On Quest a transparent emissive quad this
  size is cheap to render; the effort is authoring the UI texture, not the effect. Greybox: plain
  emissive quad.
- Footprint x −3.4 … −1.0, z −2.0 … −1.2. The player reaches it by teleporting along the −X side
  of the room, clear of the cradle and the drone's path.

## 6. Hero 02b — Lever stand (`LeverStand`)

Right (+X) of the labyrinth panel. Origin **(0.85, 0, 0.60)**, yaw 180 (front toward the player).
Reference: a throttle-style lever on a plain pedestal, in room style.

| Part | Size |
|---|---|
| Pedestal | 0.30 × 0.95 × 0.30, 0.02 chamfers, cyan strip, black/yellow warning band 0.06 under the top |
| Housing | 0.22 × 0.08 × 0.16 on top, with a slot |
| Lever | shaft Ø 0.03 × 0.22 + grip Ø 0.05 × 0.10 (amber); hinge in the slot, axis X; rest +30° (away from the player), pulled −30°; triggers at 80 % of travel |
| Indicator | small lamp on the housing: off → amber pulse when Armed |

- 1.04 from the labyrinth operating position, reachable with one step. It sits inside the
  labyrinth's protected cylinder (r 1.24) as a deliberate exception: it's a control used from
  the same spot.
- 0.15 clear of the panel's +X edge when level; the panel's tilt only moves that edge up/down.

## 7. Hero 03 — Facility gate (`Gate`)

The opening in `LAB_ENV_Wall_Door_01` (x −1.8 … −0.2, y 0 … 2.4, far wall z 8.0 … 8.2).

| Part | Size / placement |
|---|---|
| Leaf | 1.70 × 2.45 × 0.06, on the **room side** of the far wall at z 7.88 … 7.94 (clear of the trim), covering x −1.85 … −0.15. Slide reference: its +X edge. |
| Rail | 3.60 × 0.10 × 0.08 on the wall above the opening, y 2.45 … 2.55, x −3.60 … 0.00 |
| GateButton panel | 0.08 × 0.30 × 0.22 on the corridor's −X wall (x −2.0), centre (−1.96, 1.20, 8.70); button Ø 0.07 facing +X, cyan ring light. On the player's right as they face the gate. |

- **Open:** the leaf slides −X by 1.70 (to x −3.55 … −1.85) in 2.0 s, ease-in-out, along the room
  side of the wall; the 2 m of solid wall left of the door takes it.
- The leaf carries a BoxCollider so, while closed, it blocks the player and the teleport ray.
- Player spawn: **(−1, 0, 13.0), yaw 180**, 1 m in front of the corridor's end cap.

## 8. Labyrinth v2 — panel, stand and tilt mechanic (props, not heroes)

The current panel is a placeholder: loosely modelled, with its origin at a corner, so any tilt
turns it about that corner. Panel and control are **replaced**, keeping the size set in the
headset test (1.05 × 1.05) and the same place in the room.

**Panel** `LAB_PROP_LabyrinthPanel_01`
- Base plate 1.05 × 0.025 × 1.05, maze walls on top, outer rim 0.05 thick × 0.08 high.
  **Origin at the underside centre** — that point is the pivot. Placed with the pivot at
  **(0.025, 1.00, 1.225)**. Plate top at panel-local y = 0.025.
- Maze layout: open decision (owner sketch, or generated from a grid in Blender like the kit).
- **Handle** `LAB_PROP_LabyrinthPanel_Handle_01`: bar Ø 0.035 × 0.25 on the front edge (player
  side, −Z), standing 0.08 off the rim. It is the only grab point. Dark metal with a cyan cap;
  not amber, because the palette keeps amber for drone-handling equipment.
- **Maze v1** (from the owner's reference, 2026-09-25). Panel-local metres, +Z = far edge,
  −Z = player/handle edge. Interior x, z −0.475 … 0.475. Inner walls 0.03 thick × 0.07 high.
  Data: `Tools/Blender/labyrinth_maze_v1.json`; picture: `Documentation/Images/labyrinth_v1_layout.png`.

  | Wall | x | z | Note |
  |---|---|---|---|
  | W1 | −0.105 … −0.075 | 0.109 … 0.475 | from the far rim |
  | W2 | 0.295 … 0.325 | 0.199 … 0.475 | from the far rim, left side of the goal channel |
  | W3 | 0.095 … 0.125 | −0.075 … 0.325 | rises from W5, 0.15 short of the far rim |
  | W4 | −0.305 … −0.275 | −0.105 … 0.244 | rises from W5, L-corner |
  | W5 | −0.305 … 0.475 | −0.105 … −0.075 | from W4 to the right rim |
  | W6 | −0.475 … 0.254 | −0.305 … −0.275 | from the left rim |

  - Ball start (−0.304, −0.390); **goal hole Ø 0.14 at (0.400, 0.400)**, through the plate, with a
    trigger under it — the ball dropping in is the win condition.
  - Changes from the reference, needed at our ball size (Ø 0.11): walls thinned to 0.03 and the goal
    channel widened from ~0.09 (too narrow for the ball) to 0.15. Topology and route unchanged.
    Every passage ≥ 0.15 (most 0.17). If the ball feels cramped on Quest, it can shrink to
    ~Ø 0.08 without changing the maze.
  - Look (after greybox): steel in the room's language — dark gunmetal plate, brushed steel walls,
    thin cyan emissive line on the rim, cyan ring around the goal.
- **Ball-only lid:** an invisible BoxCollider covering the maze **0.12 above the plate top**, on its own
  physics layer (`LabyrinthLid`) that collides **only** with the ball's layer (`LabyrinthBall`).
  The ball can never leave the board; drone bullets (`Projectile` layer) pass through the lid and
  still hit the ball. No renderer. Needs three new physics layers and collision-matrix entries
  (Project Settings change **approved** by the owner)
  (a Project Settings change). Lid height must stay below *wall height + ball Ø* (0.07 + 0.11):
  then the ball can never cross a wall under the lid, even when a bullet kicks it upward.

**Stand** `LAB_PROP_LabyrinthStand_01` — a simple prop, minimal detail
- A **cone**: base octagon 0.40 across flats × 0.04, then a tapered body narrowing to Ø 0.04 at
  the pivot, one cyan strip facing the player; joint sphere Ø 0.06 whose top touches the pivot.
- The cone shape is also the clearance solution: its sides slope ~11° from vertical, so the panel
  would have to tilt ~79° before touching it. At 12° there is no contact anywhere.

**Mechanic**
- Hierarchy: `LabyrinthPivot` (at the pivot, kinematic Rigidbody) → panel mesh + handle. The stand
  is separate and static. The panel's position and yaw never change — only pitch and roll — so it
  cannot be pulled off the stand.
- **Tilt limit is a cone:** the panel's up-vector stays within θmax of world up, in every direction.
  Separate pitch and roll limits would allow a steeper diagonal (both at once), which is exactly
  when the ball escapes. Start θmax = **12°**, tune on Quest.
- **Control — the pan model (owner decision):** like tilting a pan of oil by its handle, with the
  pan's centre fixed on the stand's tip.
  - Forward/back tilt: the handle follows the hand **up and down** around the pivot (lift the
    handle and the far side dips).
  - Sideways tilt: **twisting the wrist** around the handle's axis rolls the board.
  - Moving the hand sideways does nothing (yaw is locked).
  - Both combined, then clamped to the cone.
- **Physics:** the pivot is moved with `Rigidbody.MoveRotation` in FixedUpdate so the ball receives
  the surface's real motion; angular speed capped (start 90°/s) so a wrist flick can't punch the
  ball through a wall. Ball keeps ContinuousDynamic collision.
- **Bullets must switch to Continuous collision.** `Sphere.prefab` is Discrete at 15 m/s: at 50
  physics steps/s it moves 0.30 m between checks — nearly 3× the ball's Ø 0.11 — so most shots
  would pass through the ball. Set ContinuousDynamic (or ContinuousSpeculative) on the bullet.
- On release the panel **keeps its tilt** (owner decision).
- Clearances: at 12° the panel edges move ≤ 0.11 up or down; the lever stand (0.15 from the +X
  edge) and the stand column stay clear. The labyrinth protected cylinder is unchanged.

### Backlog (owner, 2026-09-26, parked)

- **L1. Panel bigger, ball size unchanged** (Ø 0.1096). Scale the maze table, lid, goal trigger,
  handle and GrabPoint together. Re-check the labyrinth protected cylinder and the LeverStand
  clearance (currently 0.15 from the +X edge); the lever stand may need to move.
- **L2. Tiny shakes while tilting** (likely hand tremor). Smooth the hand input before
  `ComputeTargetRotation` (e.g. a One Euro filter or low-pass, plus a small dead-zone), keeping the
  existing tests green.
- **L3. Lower walls and rim** so bullets reach the ball more easily (H 0.07 now; ball Ø 0.11). Walls
  must still contain a rolling ball at 12° tilt. Re-check the lid rule: the lid must stay below
  wall height + ball Ø so the ball can't jump a wall.

## 9. Atmosphere states (brief for the lighting pass)

| State | Room accent lights | Terminal | Notes |
|---|---|---|---|
| Arrival / Gate open / Standby | cyan / blue | cyan | calm lab |
| Armed | cyan → orange over 2.5 s | 3 indicators red + beacon | the facility wakes up |
| Released | orange, **slow alarm pulse** (owner decision) | red | combat |

Implementation constraint: a runtime colour change rules out fully baked lighting for the accent
lights. Plan: emissive strips and panels change colour via MaterialPropertyBlock (cheap), plus at
most 2–3 realtime lights whose colour lerps, plus an ambient/probe tint. Everything else can bake.

## 10. Wiring (for the gameplay step)

- `FacilitySequence`: the state machine above; all timings serialized.
- `HingeDriver` / `SlideDriver`: move one part between its closed and open pose (duration, easing).
  Cradle v2: Arm_L 0 → +75°, Arm_R 0 → −75° about local Z, 1.2 s (§3).
- Drone start pose (Cradle v2; integration note, not implemented yet): `DroneAI2` starts docked at
  rotation Y **−28.3°**, position (−0.032, 2.000, 4.754). `DroneHoverAIV2` must take off from that
  yaw and turn smoothly, without snapping to 0°. After the pose change, re-read the drone live and
  update `ProtectedAssets/DroneBaseline.md`.
- `ServiceArmIdle`: procedural idle motion; disabled on fold.
- `LabyrinthTilt`: handle grab → cone-clamped pitch/roll on `LabyrinthPivot` (§8). Replaces the old panel control.
- `AtmosphereController`: light and emissive colour transitions.
- Buttons: XRI poke (`XRSimpleInteractable` + poke filter). Lever: grab-driven hinge; settle the
  exact XRI setup when implementing.
- Drone: `DroneHoverAIV2` starts **disabled** in BasicScene and `FacilitySequence` enables it.
  The drone is no longer locked (owner decision 2026-09-25), so its scripts may also be changed
  if that turns out cleaner.
- Teleport: `NAV_TeleportFloor`'s room collider is disabled until the gate opens. The corridor
  collider stays on. The cradle, terminal and stand footprints may need excluding later.
- XR Origin moves to the spawn point (§7).
- The inactive leftovers (`Ruller`, `Ruller (1)`, `Plane`, `DroneAI`, `Drone` (Tripo)) were
  deleted by the owner on 2026-09-25.

## 11. Decisions (all resolved 2026-09-25)

| Question | Decision |
|---|---|
| Released lighting | slow alarm pulse |
| Terminal display | see-through holo screen |
| Terminal position | back wall, x −3.4 … −1.0 — confirmed |
| Route to the terminal | teleport along the −X side of the room — confirmed |
| Labyrinth control | pan model: lift = forward/back, wrist twist = sideways, spin locked |
| Labyrinth on release | keeps its tilt |
| Ball containment | invisible ball-only lid; bullets pass through it |
| Maze layout | owner's reference, traced to v1 grid — approved |
| Physics layers | approved |
| Inactive leftovers | deleted |
| Drone and gameplay lock | removed |
