"""Cradle v2 STEP 2 - saddle / pad study for option A (called from cradle_ai_study.py -- saddle).
Checks docked clearances and a fold sweep (0-75 deg) of arm + saddle against the stationary docked drone.
Spec (Unity) axes, metres."""
import os, json, math
import numpy as np
import cradle_ai_study as S
from cradle_ai_analyze import (OUT, GAP, load, bvh, to_spec, sample_surface, nearest, yaw_matrix, axis_matrix)


def _seg_dist(p, a, b):
    ab = b - a; t = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


class Prism:
    """convex CCW polygon in (w, y) extruded along u in [u0, u1]. Frame: origin o, eu (along the limb), ew, +Y."""
    def __init__(self, poly, u0, u1, o, a_deg):
        self.poly = np.array(poly, float); self.u0, self.u1 = u0, u1; self.o = np.array(o, float)
        a = math.radians(a_deg)
        self.eu = np.array([math.cos(a), 0, math.sin(a)]); self.ew = np.array([-math.sin(a), 0, math.cos(a)])

    def local(self, p):
        q = p - self.o
        return q @ self.eu, q @ self.ew, q[:, 1]

    def sdist(self, p):
        u, w, y = self.local(p); P = np.column_stack((w, y)); n = len(self.poly)
        d2 = np.min([_seg_dist(P, self.poly[i], self.poly[(i + 1) % n]) for i in range(n)], axis=0)
        ins = np.ones(len(P), bool)
        for i in range(n):
            a, b = self.poly[i], self.poly[(i + 1) % n]
            ins &= ((b[0] - a[0]) * (P[:, 1] - a[1]) - (b[1] - a[1]) * (P[:, 0] - a[0])) >= 0
        d2s = np.where(ins, -d2, d2)
        du = np.maximum(self.u0 - u, u - self.u1)
        return np.where((d2s > 0) | (du > 0), np.hypot(np.maximum(d2s, 0), np.maximum(du, 0)), np.maximum(d2s, du))

    def mesh(self):
        n = len(self.poly); v = []
        for u in (self.u0, self.u1):
            for w, y in self.poly: v.append(self.o + u * self.eu + w * self.ew + np.array([0, y, 0]))
        t = []
        for i in range(n):
            j = (i + 1) % n; t += [(i, j, n + j), (i, n + j, n + i)]
        for i in range(1, n - 1): t += [(0, i + 1, i), (n, n + i, n + i + 1)]
        return np.array(v), np.array(t)


def saddle_parts(kind, o_xz, a_deg, plate_top, floor, P):
    """'saddle' = U section (3 convex prisms), 'pad' = block. floor = groove floor / pad top above the plate.
    u runs from the drone centre outward along the resting limb."""
    o = np.array([o_xz[0], plate_top, o_xz[1]]); r0, r1 = P["r0"], P["r1"]
    if kind == "pad":
        W = P["W"]; return [Prism([(-W / 2, 0), (W / 2, 0), (W / 2, floor), (-W / 2, floor)], r0, r1, o, a_deg)]
    W, g, H, ch = P["W"], P["g"], P["H"], P["ch"]
    left = [(-W / 2, 0), (-g / 2, 0), (-g / 2, H - ch), (-g / 2 - ch, H), (-W / 2, H)]
    bottom = [(-g / 2, 0), (g / 2, 0), (g / 2, floor), (-g / 2, floor)]
    right = [(g / 2, 0), (W / 2, 0), (W / 2, H), (g / 2 + ch, H), (g / 2, H - ch)]
    return [Prism(pl, r0, r1, o, a_deg) for pl in (left, bottom, right)]


def union_sdist(prisms, p):
    return np.min([pr.sdist(p) for pr in prisms], axis=0)


def disc_cloud(c, rad, y0, y1, n=48):
    pts = []
    for rr in np.linspace(0, rad, 10):
        for a in np.linspace(0, 2 * math.pi, max(6, int(n * rr / rad)), endpoint=False):
            for y in (y0, y1): pts.append([c[0] + rr * math.cos(a), y, c[2] + rr * math.sin(a)])
    return np.array(pts)


def docked_drone(o):
    drone = S.read_drone_obj()
    P0 = np.array([0.0, 2.0, 4.76]); P1 = np.array(o["DroneAI2_new"]); A = yaw_matrix(o["yaw_deg"])
    D = {k: (v - P0) @ A.T + P1 for k, (v, t) in drone.items() if k != "ScannerGlow"}
    T = {k: t for k, (v, t) in drone.items() if k != "ScannerGlow"}
    return D, T


def limb_frames(D):
    bc = (D["Body_low"].min(0) + D["Body_low"].max(0)) / 2
    lim = {}
    for side, en in (("R", "Engine1_low"), ("L", "Engine4_low")):     # FR rests on the right plate, BL on the left
        e = D[en]; ec = (e.min(0) + e.max(0)) / 2
        u = np.array([ec[0] - bc[0], ec[2] - bc[2]]); u /= np.linalg.norm(u)
        lim[side] = dict(o=[float(bc[0]), float(bc[2])], a=math.degrees(math.atan2(u[1], u[0])))
    return lim


VARIANTS = {
    "S1 full saddle r0.29-0.61 H80": ("saddle", dict(r0=0.29, r1=0.61, W=0.20, g=0.128, H=0.080, ch=0.006)),
    "S2 short chock r0.29-0.36 H80": ("saddle", dict(r0=0.29, r1=0.36, W=0.20, g=0.128, H=0.080, ch=0.006)),
    "S3 saddle outboard of pin r0.39-0.61 H80": ("saddle", dict(r0=0.39, r1=0.61, W=0.20, g=0.128, H=0.080, ch=0.006)),
    "P0 plain pads r0.29-0.61 (Step 1 A)": ("pad", dict(r0=0.29, r1=0.61, W=0.14)),
    "P1 plain pads r0.39-0.61 (outboard of pin)": ("pad", dict(r0=0.39, r1=0.61, W=0.14)),
}
FRONT_Y, BACK_Y = 1.7121, 1.7665


def run(args):
    R = json.load(open(OUT)); cx, cy = R["centre_native"]; o = R["options"]["A"]; s = o["s"]
    parts = {k: load("AI_split_" + k) for k in ("part_1", "part_2")}
    arms = {"L": to_spec(*parts["part_1"], s, cx, cy), "R": to_spec(*parts["part_2"], s, cx, cy)}
    arm_trees = {k: bvh(*v) for k, v in arms.items()}
    D, T = docked_drone(o)
    groups = {"limbs": ["ArmLeft_low", "ArmRight_low"], "engines": ["Engine1_low", "Engline2_low", "Engine3_low", "Engine4_low"],
              "body": ["Body_low", "Ring_low", "Top_low", "ToShoot_low"]}
    G = {g: np.vstack([sample_surface(D[m], T[m], 8000) for m in ms] + [D[m] for m in ms]) for g, ms in groups.items()}
    props = []
    for pn, en in (("Propellor1_low", "Engine1_low"), ("Propellor2_low", "Engline2_low"), ("Propellor3_low", "Engine3_low"), ("Propellor4_low", "Engine4_low")):
        e = D[en]; c = (e.min(0) + e.max(0)) / 2; p = D[pn]
        props.append(disc_cloud(c, np.hypot(p[:, 0] - c[0], p[:, 2] - c[2]).max(), p[:, 1].min(), p[:, 1].max()))
    G["props"] = np.vstack(props)
    lim = limb_frames(D)
    floor = {"R": FRONT_Y - GAP - o["plate_top"]["R"], "L": BACK_Y - GAP - o["plate_top"]["L"]}
    pins = {k: (np.array(o["pins_spec"][k]["front"]), np.array(o["release"][k]["axis_dir"])) for k in ("L", "R")}
    only = args[0] if args else None
    res = {}
    for vname, (kind, P) in VARIANTS.items():
        if only and not vname.startswith(only): continue
        pr = {sd: saddle_parts(kind, lim[sd]["o"], lim[sd]["a"], o["plate_top"][sd], floor[sd], P) for sd in ("L", "R")}
        rows = []
        for deg in list(range(0, 16)) + list(range(20, 76, 5)):
            row = {"deg": deg}
            for sd in ("L", "R"):
                f, ax = pins[sd]; sgn = 1 if sd == "L" else -1
                Ainv = axis_matrix(ax, -sgn * deg)                  # drone into the arm's closed-pose frame
                for g, pts in G.items():
                    q = (pts - f) @ Ainv.T + f
                    row[f"{sd}.pad->{g}"] = round(1e3 * float(union_sdist(pr[sd], q).min()), 1)
                    if deg % 5 == 0:
                        row[f"{sd}.arm->{g}"] = round(1e3 * float(nearest(arm_trees[sd], q[:: max(1, len(q) // 4000)]).min()), 1)
            rows.append(row)
        det = {}
        for sd in ("L", "R"):
            lp = G["limbs"]; u_, w_, y_ = pr[sd][0].local(lp)
            near = lp[(u_ > P["r0"] - 0.01) & (u_ < P["r1"] + 0.01) & (np.abs(w_) < 0.15)]
            if kind == "saddle":
                det[sd] = dict(floor_gap_mm=round(1e3 * pr[sd][1].sdist(near).min(), 1),
                               wall_gap_mm=round(1e3 * min(pr[sd][0].sdist(near).min(), pr[sd][2].sdist(near).min()), 1),
                               walls_top_y=round(o["plate_top"][sd] + P["H"], 4), groove_depth_mm=round(1e3 * (P["H"] - floor[sd]), 1))
            else:
                det[sd] = dict(pad_gap_mm=round(1e3 * pr[sd][0].sdist(near).min(), 1), pad_top_y=round(o["plate_top"][sd] + floor[sd], 4))
        sweep = [r for r in rows if r["deg"] > 0]
        worst = {}
        for k in rows[0]:
            if k == "deg": continue
            rr = [r for r in sweep if k in r]
            b = min(rr, key=lambda r: r[k]); worst[k] = (b[k], b["deg"])
        res[vname] = dict(kind=kind, params=P, floor=floor, lim=lim, contact=det, docked=rows[0], sweep_min=worst, rows=rows)
        print("VARIANT", vname)
        print("  contact", det)
        print("  docked ", {k: v for k, v in rows[0].items() if k != "deg"})
        print("  sweep min (mm @deg)", {k: v for k, v in worst.items() if ".pad" in k})
        print("  sweep min arm      ", {k: v for k, v in worst.items() if ".arm" in k})
    old = {}
    p = os.path.join(S.CACHE, "saddle.json")
    if os.path.exists(p) and only: old = json.load(open(p))
    old.update(res)
    json.dump(old, open(p, "w"), indent=1, default=float)
