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
- **Greybox budget:** ≤ 500 tris per hero, M_Greybox plus one emissive placeholder material.

## 3. Hero 01 — Docking cradle (`Cradle`)

**Drone at rest (measured live 2026-09-25):** body (`Body_low`) x −0.177 … 0.177,
y 1.568 … 1.949, z 4.49 … 4.88, centre (0, 1.758, 4.687). The drone's arms leave the body sides
at |x| ≈ 0.13 with their underside at y ≈ 1.65, so **the body can't be gripped from the sides**:
the yoke is a fork that cups the body's underside, which hangs 8 cm below the arms. Whole drone
including propellers: x ±0.944, y 1.568 … 1.986, z 4.07 … 5.31.

Cradle origin: **(0, 0, 4.69)** (under the body centre, not under `DroneAI2`), yaw 0.

| Part | Shape / size | Hinge / origin (cradle-local) | Moves | Standby | Released |
|---|---|---|---|---|---|
| Base_T1 | octagon 2.4 across flats × 0.10 | floor centre | no | — | — |
| Base_T2 | octagon 1.6 × 0.10 | (0, 0.10, 0) | no | — | — |
| Turntable | cylinder Ø 0.8 × 0.10 | (0, 0.20, 0) | no | — | — |
| Column | 0.30 × 0.70 × 0.30 | (0, 0.30, 0) | no | — | — |
| Hub | 0.40 × 0.08 × 0.30 | (0, 1.00, 0) | no | — | — |
| Arm_L / Arm_R | 0.06 × 0.50 × 0.18 | hinge (∓0.13, 1.04, 0), axis Z | yes | vertical | 100° outward: tip y ≈ 0.95, highest point ≈ 1.08 |
| Pad_L / Pad_R (amber) | 0.10 × 0.025 × 0.22 | top of arm | with arm | top face at y 1.565, 3 mm under the body's lower edges (x ±0.08 … 0.18) | — |

Checks: static parts top out at 1.08; released arms stay below 1.19. In standby the arms
(x 0.10 … 0.16, up to y 1.565) stay clear of the drone arms (y ≥ 1.65).

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
  |x| < 0.3. Roughly shoulder −60°, elbow +70°, wrist keeping the tool vertical. Tune by eye;
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
