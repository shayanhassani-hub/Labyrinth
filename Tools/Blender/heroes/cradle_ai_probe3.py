"""plan outlines by 360 deg horizontal ray fans (spec, option A scale) -> DP-simplified corner lists"""
import math, json, os, numpy as np
from mathutils import Vector
import cradle_ai_study as S
from cradle_ai_sections import fitted, SCR
from cradle_ai_analyze import bvh


def dp(pts, tol):
    if len(pts) < 3: return pts
    a, b = np.array(pts[0]), np.array(pts[-1]); d = b - a; L = np.linalg.norm(d) or 1e-9
    dist = [abs(d[1] * (p[0] - a[0]) - d[0] * (p[1] - a[1])) / L for p in pts]
    i = int(np.argmax(dist))
    if dist[i] > tol: return dp(pts[:i + 1], tol)[:-1] + dp(pts[i:], tol)
    return [pts[0], pts[-1]]


def run(args):
    M, R = fitted(); tS = bvh(*M["static"]); cz = S.CZ
    out = {}
    for y, lab in ((0.10, "T1 wall"), (0.185, "T1 top edge"), (0.225, "T2 wall"), (0.31, "T2 top"), (0.33, "turntable"), (0.37, "ring 3"), (0.42, "column"), (0.84, "hub")):
        pts = []
        for a in np.arange(0, 360, 0.25):
            u = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
            r = tS.ray_cast(Vector((3 * u[0], y, cz + 3 * u[1])), Vector((-u[0], 0, -u[1])), 4)
            if r[0]: pts.append([round(r[0].x, 4), round(r[0].z - cz, 4)])
        # start at +X, close the loop
        n = len(pts); simp = dp(pts[:n // 2 + 1], 0.004)[:-1] + dp(pts[n // 2:] + [pts[0]], 0.004)[:-1]
        rad = [math.hypot(*p) for p in pts]
        out[lab] = dict(y=y, corners=simp, r_min=round(min(rad), 4), r_max=round(max(rad), 4))
        print(f"{lab} (y {y}): r {min(rad):.3f}..{max(rad):.3f}; {len(simp)} corners:", " ".join(f"({x:.3f},{z:.3f})" for x, z in simp))
    json.dump(out, open(os.path.join(SCR, "plan_outlines.json"), "w"), indent=0)
