"""
ServiceArm (Hero 01b) -- shared numbers: HERO_SPEC §4 kinematics, poses, the docked drone and its disc volumes.
Imported by servicearm.py / servicearm_check.py / servicearm_tex.py / servicearm_export.py; no bpy needed except in
docked_drone() (FBX import).

Axes: Unity / HERO_SPEC (metres, +Y up, +Z toward the far wall). Blender = C @ spec with C: x -> -x, y -> z, z -> -y
(EXPORT_CONTRACT). Rotation matrices act on column vectors and equal Unity's Quaternion.Euler numerically:
Euler(a,0,0) = Rx(a) turns +Z toward -Y (pitch down), Euler(0,b,0) = Ry(b) turns +Z toward +X, Euler(0,0,g) = Rz(g).

Chain (HERO_SPEC §4 table; every part's origin is on its hinge, parts modelled in the STOWED pose = all angles 0):
  Mount     world (0, 4.00, 5.30), ceiling face
  Turret    mount   (0, -0.05, 0)      yaw   psi   about Y
  UpperArm  turret  (0, -0.12, 0)      pitch th1   about X   link along +Z, 1.00 to the elbow
  Forearm   upper   (+0.12, 0, 1.00)   pitch th2   about X   link along -Z (folded back beside the upper arm), 0.90
  Wrist     forearm (+0.10, 0, -0.90)  pitch th3   about X
  ToolHead  wrist   (0, 0, -TOOL_Z)    roll  th4   about Z   tool along -Z, tip at TIP_Z below the tool origin
The X offsets go to +X (forearm and tool lie beside the upper arm when stowed, HERO_SPEC §4); the concept's side view
(camera on +X looking -X, screen right = +Z) then shows the elbow on the right and the wrist on the left, as drawn.
"""
import json
import math
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DRONE_FBX = os.path.join(PROJ, "Assets", "Drone_Asset", "drone_low.fbx")

MOUNT = np.array([0.0, 4.00, 5.30])
CEILING_Y = 4.00
T_TURRET = np.array([0.0, -0.07, 0.0])            # H1b: 0.05 -> 0.07 (taller mount, owner review)
T_UPPER = np.array([0.0, -0.16, 0.0])             # H1b: 0.12 -> 0.16 (big shoulder housing)
T_FORE = np.array([0.12, 0.0, 1.00])
T_WRIST = np.array([0.10, 0.0, -0.90])
TOOL_Z = 0.078                      # tool origin below the wrist hinge (wrist body 0.060 + neck 0.015 + 3 mm gap)
TIP_Z = 0.200                       # ToolHead length (HERO_SPEC 0.20): collar + ochre block + pin
L_UPPER, L_FORE = 1.00, 0.90
PARTS = ["Mount", "Turret", "UpperArm", "Forearm", "Wrist", "ToolHead"]
PARENT = {"Turret": "Mount", "UpperArm": "Turret", "Forearm": "UpperArm", "Wrist": "Forearm", "ToolHead": "Wrist"}

# HERO_SPEC §4 timings / idle (the runtime driver uses the same numbers)
FOLD_DELAY, FOLD_TIME = 2.5, 2.0
IDLE_TURRET, IDLE_WRIST = 10.0, 15.0

# docking pose (HERO_SPEC §3 / §10) and the drone chain (ProtectedAssets/DroneBaseline.md, live read 2026-09-24)
DRONE_POS = np.array([-0.032, 2.000, 4.754])
DRONE_YAW = -28.3
DRONE_LOW_POS = np.array([0.0, -0.228, 0.0])
DRONE_LOW_Q = (0.0, -1.0, 0.0, 0.00023)          # x, y, z, w
DRONE_LOW_SCALE = 0.59

# clearance rule (HERO_SPEC §4, option B, owner decision 2026-11-03)
DISC_MIN, DRONE_MIN, DISC_FLOOR_Y = 0.100, 0.050, 2.00
STOW_Y0, STOW_Y1 = 3.60, 3.95                 # owner decision 2026-11-03 (was 3.77)
DRONE_VOLUME = ((-2.45, 2.39), (1.19, 3.48), (2.84, 6.32))   # released-state rule (HERO_SPEC §2)


def Rx(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def Ry(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def Rz(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def M4(R=None, t=(0, 0, 0)):
    M = np.eye(4)
    if R is not None: M[:3, :3] = R
    M[:3, 3] = t
    return M


def fk(pose):
    """pose: dict psi, th1, th2, th3, th4 (deg) -> {part: 4x4 world matrix (spec)}"""
    W = {"Mount": M4(t=MOUNT)}
    W["Turret"] = W["Mount"] @ M4(Ry(pose["psi"]), T_TURRET)
    W["UpperArm"] = W["Turret"] @ M4(Rx(pose["th1"]), T_UPPER)
    W["Forearm"] = W["UpperArm"] @ M4(Rx(pose["th2"]), T_FORE)
    W["Wrist"] = W["Forearm"] @ M4(Rx(pose["th3"]), T_WRIST)
    W["ToolHead"] = W["Wrist"] @ M4(Rz(pose["th4"]), (0, 0, -TOOL_Z))
    return W


def tip(pose):
    return (fk(pose)["ToolHead"] @ np.array([0, 0, -TIP_Z, 1.0]))[:3]


def local_rotation(part, pose):
    """Unity localEulerAngles of a part for a pose"""
    return {"Mount": (0, 0, 0), "Turret": (0, pose["psi"], 0), "UpperArm": (pose["th1"], 0, 0),
            "Forearm": (pose["th2"], 0, 0), "Wrist": (pose["th3"], 0, 0), "ToolHead": (0, 0, pose["th4"])}[part]


def local_position(part):
    return {"Mount": tuple(MOUNT), "Turret": tuple(T_TURRET), "UpperArm": tuple(T_UPPER), "Forearm": tuple(T_FORE),
            "Wrist": tuple(T_WRIST), "ToolHead": (0.0, 0.0, -TOOL_Z)}[part]


# --------------------------------------------------------------------------- poses

STOWED = dict(psi=0.0, th1=0.0, th2=0.0, th3=0.0, th4=0.0)
TIP_TARGET = np.array([0.0, 2.04, 4.69])        # HERO_SPEC §4: ~0.05 above the drone top (1.986), near x 0, over the body


def ik_working(target=TIP_TARGET, elbow_back=True):
    """tool vertical (pointing down) with its tip on target. The turret yaw brings the +X offsets (0.22) onto the
    target line; the planar 2-link IK then puts the wrist hinge TOOL_Z + TIP_Z above the tip. elbow_back: the elbow
    behind the shoulder (+Z), the concept's Z shape."""
    off = T_FORE[0] + T_WRIST[0]
    tx, tz = target[0] - MOUNT[0], target[2] - MOUNT[2]
    r = math.hypot(tx, tz)
    # turret frame: target at (x' = off, z' = -sqrt(r^2 - off^2)); world = Ry(psi) @ frame
    zp = -math.sqrt(r * r - off * off)
    psi = math.degrees(math.atan2(tx, tz) - math.atan2(off, zp))
    sy = MOUNT[1] + T_TURRET[1] + T_UPPER[1]
    wy = target[1] + TOOL_Z + TIP_Z
    dy, dz = wy - sy, zp
    D = math.hypot(dy, dz)
    cos_int = (L_UPPER ** 2 + L_FORE ** 2 - D * D) / (2 * L_UPPER * L_FORE)
    interior = math.degrees(math.acos(max(-1, min(1, cos_int))))
    a = math.degrees(math.acos((L_UPPER ** 2 + D * D - L_FORE ** 2) / (2 * L_UPPER * D)))
    # direction shoulder -> wrist as a pitch angle phi: dir = (0, -sin phi, cos phi) (= Rx(phi) applied to +Z)
    phi = math.degrees(math.atan2(-dy, dz))
    th1 = phi - a if elbow_back else phi + a
    # forearm points along Rx(th1 + th2) (0, 0, -1) = (0, sin s, -cos s)
    ey = sy - L_UPPER * math.sin(math.radians(th1)); ez = L_UPPER * math.cos(math.radians(th1))
    fy, fz = (wy - ey) / L_FORE, (dz - ez) / L_FORE
    s = math.degrees(math.atan2(fy, -fz))
    th2 = s - th1
    th3 = -90.0 - s
    pose = dict(psi=psi, th1=th1, th2=th2, th3=th3, th4=0.0)
    return pose, dict(reach_needed=D, reach_available=L_UPPER + L_FORE, elbow_interior=interior)


WORKING, WORKING_INFO = ik_working()
# comparison pose only (not a gameplay pose): the joint angles read off servicearm_ortho_side.jpg (upper arm 37 deg
# below horizontal, forearm 22.6 deg below horizontal coming back, tool vertical), turret straight
CONCEPT = dict(psi=0.0, th1=37.0, th2=-59.6, th3=-67.4, th4=0.0)


def idle_pose(base, dpsi, dth3, th4):
    p = dict(base); p["psi"] += dpsi; p["th3"] += dth3; p["th4"] = th4
    return p


def smoothstep(t):
    t = min(1.0, max(0.0, t)); return t * t * (3 - 2 * t)


def fold_pose(start, t):
    """fold at normalised time t (0..1, ease-in-out); roll unwinds the short way"""
    e = smoothstep(t)
    p = {}
    for k in ("psi", "th1", "th2", "th3"):
        p[k] = start[k] + (STOWED[k] - start[k]) * e
    r = ((start["th4"] + 180.0) % 360.0) - 180.0
    p["th4"] = r * (1 - e)
    return p


# --------------------------------------------------------------------------- docked drone (from the repo FBX)


def quat_matrix(q):
    x, y, z, w = q; n = math.sqrt(x * x + y * y + z * z + w * w); x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def drone_to_world(v_fbx_spec):
    """FBX node space (Unity axes, metres after the importer's cm scale) -> docked world"""
    R1 = quat_matrix(DRONE_LOW_Q)
    v = (DRONE_LOW_SCALE * v_fbx_spec) @ R1.T + DRONE_LOW_POS
    return v @ Ry(DRONE_YAW).T + DRONE_POS


def docked_drone():
    """{mesh name: (verts Nx3 spec world, tris Mx3)} -- imports drone_low.fbx into the current (empty) scene and
    removes it again. Unity's FBX import = Blender import followed by the contract mapping (x -> -x, z <-> y)."""
    import bpy
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=DRONE_FBX)
    out = {}
    for o in [o for o in bpy.data.objects if o not in before]:
        if o.type != 'MESH' or o.name.startswith("ScannerGlow"): continue
        me = o.data; me.calc_loop_triangles()
        M = np.array(o.matrix_world)
        v = np.array([M[:3, :3] @ np.array(x.co) + M[:3, 3] for x in me.vertices])
        vs = np.column_stack((-v[:, 0], v[:, 2], -v[:, 1]))
        t = np.array([tuple(lt.vertices) for lt in me.loop_triangles], np.int32)[:, ::-1]
        out[o.name.split(".")[0]] = (drone_to_world(vs), t)
    for o in [o for o in bpy.data.objects if o not in before]:
        bpy.data.objects.remove(o, do_unlink=True)
    return out


PROPS = (("Propellor1_low", "Engine1_low"), ("Propellor2_low", "Engline2_low"),
         ("Propellor3_low", "Engine3_low"), ("Propellor4_low", "Engine4_low"))


def discs(D):
    """spinning prop disc volumes: (centre x, z, radius, y0, y1) about each engine hub (vertical axis)"""
    out = []
    for pn, en in PROPS:
        e = D[en][0]; c = (e.min(0) + e.max(0)) / 2; p = D[pn][0]
        out.append((c[0], c[2], float(np.hypot(p[:, 0] - c[0], p[:, 2] - c[2]).max()), float(p[:, 1].min()),
                    float(p[:, 1].max())))
    return out


def disc_distance(P, d):
    """distance from points P (Nx3) to the solid disc cylinder d"""
    cx, cz, r, y0, y1 = d
    rad = np.maximum(np.hypot(P[:, 0] - cx, P[:, 2] - cz) - r, 0.0)
    ver = np.maximum(np.maximum(y0 - P[:, 1], P[:, 1] - y1), 0.0)
    return np.hypot(rad, ver)


def in_footprint(P, d):
    cx, cz, r, y0, y1 = d
    return np.hypot(P[:, 0] - cx, P[:, 2] - cz) <= r


if __name__ == "__main__":
    print(json.dumps({"working": {k: round(v, 2) for k, v in WORKING.items()},
                      "info": {k: round(v, 3) for k, v in WORKING_INFO.items()},
                      "tip": np.round(tip(WORKING), 4).tolist(), "concept_tip": np.round(tip(CONCEPT), 3).tolist(),
                      "stowed_tip": np.round(tip(STOWED), 3).tolist()}, indent=1))
