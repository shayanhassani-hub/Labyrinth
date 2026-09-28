"""tray and side-panel extents on the plinth by ray casts along each face (spec, option A scale)"""
import math, numpy as np
from mathutils import Vector
import cradle_ai_study as S
from cradle_ai_sections import fitted
from cradle_ai_analyze import bvh


def spans(ts, mask):
    out = []; i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]: j += 1
            out.append((round(float(ts[i]), 3), round(float(ts[j]), 3))); i = j + 1
        else: i += 1
    return out


def run(args):
    M, R = fitted(); tS = bvh(*M["static"]); cz = S.CZ
    ts = np.arange(-0.70, 0.701, 0.004)
    for k in (0, 1, 2):
        a = math.radians(-90 + k * 45)                    # front face, front-right diagonal, right face
        u = np.array([math.cos(a), 0, math.sin(a)]); v = np.array([-u[2], 0, u[0]])
        c = np.array([0, 0, cz])
        # tray: ray down at r 0.97
        h = []
        for t in ts:
            p = c + u * 0.97 + v * t
            r = tS.ray_cast(Vector((p[0], 2.0, p[2])), Vector((0, -1, 0)), 3); h.append(r[0].y if r[0] else np.nan)
        h = np.array(h)
        print(f"face {k*45}deg from front: tray floor (h<0.17) spans {spans(ts, h < 0.17)}; top h(t=0)={h[len(h)//2]:.3f}")
        # side face: horizontal rays inward at several heights
        for y in (0.030, 0.052, 0.090, 0.126, 0.150):
            d = []
            for t in ts:
                p = c + u * 3.0 + v * t
                r = tS.ray_cast(Vector((p[0], y, p[2])), Vector(-u), 5)
                d.append(float((np.array(r[0]) - c) @ u) if r[0] else np.nan)
            d = np.array(d); face = np.nanmax(d)
            print(f"   side y {y:.3f}: face r {face:.3f}; recessed (>4 mm) spans {spans(ts, d < face - 0.004)}; min r {np.nanmin(d):.3f}")
