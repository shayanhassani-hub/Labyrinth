"""Cradle v2 STEP 2 - direct ray probes for hinge block, caps and plate (spec axes, option A scale).
  blender -b --factory-startup --python cradle_ai_study.py -- probe"""
import json, os
import numpy as np
from mathutils import Vector
import cradle_ai_study as S
from cradle_ai_sections import fitted, SCR
from cradle_ai_analyze import bvh


def hit(tree, o, d):
    r = tree.ray_cast(Vector(o), Vector(d), 10)
    return None if r[0] is None else [round(c, 4) for c in r[0]]


def run(args):
    M, R = fitted(); tS = bvh(*M["static"]); tA = bvh(*M["arm_R"]); cz = S.CZ
    pin = R["options"]["A"]["pins_spec"]["R"]; px = (pin["front"][0] + pin["back"][0]) / 2
    out = {"pin_x": px}
    for lab, x in (("pin", px), ("pin+0.09", px + 0.09), ("pin-0.09", px - 0.09), ("x0.22", 0.22)):
        rows = []
        for y in np.arange(0.50, 0.80, 0.01):
            f = hit(tS, (x, y, cz - 3), (0, 0, 1)); b = hit(tS, (x, y, cz + 3), (0, 0, -1))
            rows.append((round(y, 3), f[2] if f else None, b[2] if b else None))
        out["hinge_z_faces_" + lab] = rows
    # caps: radial profile of the front cap face (x from pin centre outward at pin height)
    out["front_cap_radial"] = [(round(dx, 3), (hit(tS, (px + dx, 0.6372, cz - 3), (0, 0, 1)) or [0, 0, None])[2]) for dx in np.arange(0, 0.14, 0.005)]
    out["back_cap_radial"] = [(round(dx, 3), (hit(tS, (px + dx, 0.6372, cz + 3), (0, 0, -1)) or [0, 0, None])[2]) for dx in np.arange(0, 0.14, 0.005)]
    # plate: underside (ray up) and top along x at z = cz; edge profile across z at x = 0.9
    out["plate_under_along_x"] = [(round(x, 3), (hit(tA, (x, 1.0, cz), (0, 1, 0)) or [0, None, 0])[1]) for x in np.arange(0.26, 1.16, 0.02)]
    out["plate_top_along_x"] = [(round(x, 3), (hit(tA, (x, 2.5, cz), (0, -1, 0)) or [0, None, 0])[1]) for x in np.arange(0.26, 1.16, 0.02)]
    out["plate_edge_front_by_y"] = [(round(y, 4), (hit(tA, (0.9, y, cz - 2), (0, 0, 1)) or [0, 0, None])[2]) for y in np.arange(1.58, 1.705, 0.004)]
    out["plate_edge_outer_by_y"] = [(round(y, 4), (hit(tA, (3.0, y, cz), (-1, 0, 0)) or [None])[0]) for y in np.arange(1.58, 1.705, 0.004)]
    json.dump(out, open(os.path.join(SCR, "probe.json"), "w"), indent=0)
    for k, v in out.items(): print(k, v)
