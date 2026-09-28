"""Cradle v2 STEP 2 - cross-sections of the fitted AI design (option A scale), spec axes, metres.
  -- sections explore : section polylines -> quick raster PNGs + horizontal/vertical run lists
"""
import os, json, math
import numpy as np
import bpy
import cradle_ai_study as S
from cradle_ai_analyze import OUT, load, to_spec

SCR = os.path.join(S.CACHE, "sections")


def fitted():
    R = json.load(open(OUT)); cx, cy = R["centre_native"]; s = R["options"]["A"]["s"]
    return {k: to_spec(*load("AI_split_" + p), s, cx, cy) for k, p in (("static", "part_0"), ("arm_L", "part_1"), ("arm_R", "part_2"))}, R


def section_segments(v, t, n, d0):
    """segments where the plane n.p = d0 cuts the triangles; returns (m, 2, 3)"""
    d = v @ n - d0
    dt = d[t]
    m = (dt.min(1) < 0) & (dt.max(1) > 0)
    t = t[m]; dt = dt[m]
    segs = []
    pts = np.zeros((len(t), 2, 3)); cnt = np.zeros(len(t), int)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = t[:, i], t[:, j]; da, db = dt[:, i], dt[:, j]
        c = (da * db) < 0
        f = np.where(c, da / np.where(c, da - db, 1), 0)
        p = v[a] + f[:, None] * (v[b] - v[a])
        c &= cnt < 2
        idx = np.nonzero(c)[0]
        pts[idx, cnt[idx]] = p[idx]; cnt[idx] += 1
    return pts[cnt == 2]


def plane2d(segs, axes):
    return segs[:, :, axes]


def raster(segsets, fn, bounds, px_per_m=1200, grid=0.05):
    (x0, y0), (x1, y1) = bounds
    W = int((x1 - x0) * px_per_m) + 1; H = int((y1 - y0) * px_per_m) + 1
    img = np.ones((H, W, 4), np.float32); img[..., :3] = 1.0
    for gx in np.arange(math.ceil(x0 / grid) * grid, x1, grid):
        c = int((gx - x0) * px_per_m); img[:, c, :3] = 0.85 if abs(gx / 0.25 - round(gx / 0.25)) > 1e-6 else 0.6
    for gy in np.arange(math.ceil(y0 / grid) * grid, y1, grid):
        r = int((gy - y0) * px_per_m); img[r, :, :3] = 0.85 if abs(gy / 0.25 - round(gy / 0.25)) > 1e-6 else 0.6
    for segs, col in segsets:
        for a, b in segs:
            n = int(np.linalg.norm(b - a) * px_per_m * 2) + 2
            pts = a[None] + np.linspace(0, 1, n)[:, None] * (b - a)[None]
            c = ((pts[:, 0] - x0) * px_per_m).astype(int); r = ((pts[:, 1] - y0) * px_per_m).astype(int)
            ok = (c >= 0) & (c < W) & (r >= 0) & (r < H)
            for dr in (0, 1):
                for dc in (0, 1):
                    rr = np.clip(r[ok] + dr, 0, H - 1); cc = np.clip(c[ok] + dc, 0, W - 1)
                    img[rr, cc, :3] = col
    im = bpy.data.images.new(fn, W, H, alpha=True)
    im.pixels.foreach_set(img.ravel()); im.filepath_raw = os.path.join(SCR, fn); im.file_format = 'PNG'; im.save()


def runs(segs2d, axis, tol=0.0008, minlen=0.004):
    """merge near-axis-parallel segments: axis=1 -> horizontal runs (constant y); returns [(level, lo, hi)]"""
    other = 1 - axis
    d = segs2d[:, 1] - segs2d[:, 0]
    L = np.linalg.norm(d, axis=1)
    par = np.abs(d[:, axis]) < 0.02 * np.maximum(L, 1e-9)
    s = segs2d[par & (L > 1e-5)]
    lv = s[:, :, axis].mean(1)
    order = np.argsort(lv); s = s[order]; lv = lv[order]
    out = []; i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and lv[j + 1] - lv[i] < tol: j += 1
        grp = s[i:j + 1]
        iv = sorted([tuple(sorted(g[:, other])) for g in grp])
        cur = list(iv[0])
        for a, b in iv[1:]:
            if a <= cur[1] + 0.002: cur[1] = max(cur[1], b)
            else:
                if cur[1] - cur[0] >= minlen: out.append((round(float(lv[i:j + 1].mean()), 4), round(cur[0], 4), round(cur[1], 4)))
                cur = [a, b]
        if cur[1] - cur[0] >= minlen: out.append((round(float(lv[i:j + 1].mean()), 4), round(cur[0], 4), round(cur[1], 4)))
        i = j + 1
    return out


def explore(args):
    os.makedirs(SCR, exist_ok=True)
    M, R = fitted(); o = R["options"]["A"]
    ST, AL, AR = M["static"], M["arm_L"], M["arm_R"]
    pin = o["pins_spec"]["R"]; px = (pin["front"][0] + pin["back"][0]) / 2
    rep = {}
    # A: front vertical section, plane z = 4.69 -> (x, y)
    cz = S.CZ
    sets = [(plane2d(section_segments(*ST, np.array([0, 0, 1.0]), cz), [0, 1]), (0, 0, 0)),
            (plane2d(section_segments(*AL, np.array([0, 0, 1.0]), cz), [0, 1]), (0.8, 0, 0)),
            (plane2d(section_segments(*AR, np.array([0, 0, 1.0]), cz), [0, 1]), (0, 0, 0.8))]
    raster(sets, "sec_front_z469.png", ((-1.25, -0.02), (1.25, 1.80)), 800)
    rep["front_h"] = runs(sets[0][0], 1); rep["front_v"] = runs(sets[0][0], 0)
    # B: side vertical section, plane x = 0 -> (z, y)
    sb = plane2d(section_segments(*ST, np.array([1.0, 0, 0]), 0.0), [2, 1])
    raster([(sb, (0, 0, 0))], "sec_side_x0.png", ((cz - 1.25, -0.02), (cz + 1.25, 1.0)), 800)
    rep["side_h"] = runs(sb, 1); rep["side_v"] = runs(sb, 0)
    # C: hinge section, plane x = pin x (right) -> (z, y)
    sc = [(plane2d(section_segments(*ST, np.array([1.0, 0, 0]), px), [2, 1]), (0, 0, 0)),
          (plane2d(section_segments(*AR, np.array([1.0, 0, 0]), px), [2, 1]), (0, 0, 0.8))]
    raster(sc, "sec_hinge_xpin.png", ((cz - 0.5, 0.3), (cz + 0.5, 1.0)), 1500)
    rep["hinge_static_h"] = runs(sc[0][0], 1); rep["hinge_static_v"] = runs(sc[0][0], 0)
    rep["hinge_arm_h"] = runs(sc[1][0], 1); rep["hinge_arm_v"] = runs(sc[1][0], 0)
    # D: plan sections at heights
    levels = [0.02, 0.10, 0.17, 0.24, 0.29, 0.33, 0.40, 0.50, 0.60, 0.64, 0.70, 0.80, 0.86]
    for yl in levels:
        ss = plane2d(section_segments(*ST, np.array([0, 1.0, 0]), yl), [0, 2])
        sa = [plane2d(section_segments(*A, np.array([0, 1.0, 0]), yl), [0, 2]) for A in (AL, AR)]
        raster([(ss, (0, 0, 0))] + [(x, (0, 0, 0.8)) for x in sa], f"plan_y{int(yl*1000):04d}.png", ((-1.25, cz - 1.25), (1.25, cz + 1.25)), 500)
        rep[f"plan_{yl}_x_extent"] = [round(float(ss[:, :, 0].min()), 4), round(float(ss[:, :, 0].max()), 4)] if len(ss) else None
        rep[f"plan_{yl}_z_extent"] = [round(float(ss[:, :, 1].min()), 4), round(float(ss[:, :, 1].max()), 4)] if len(ss) else None
    # E: arm path: plan sections of arm R every 2 cm in y -> centroid + extents
    path = []
    for yl in np.arange(0.52, 1.72, 0.02):
        sa = section_segments(*AR, np.array([0, 1.0, 0]), yl)
        if len(sa) == 0: continue
        p = sa.reshape(-1, 3)
        path.append([round(yl, 3), round(float(p[:, 0].min()), 4), round(float(p[:, 0].max()), 4), round(float(p[:, 2].min()), 4), round(float(p[:, 2].max()), 4)])
    rep["arm_R_plan_extents_by_y"] = path
    json.dump(rep, open(os.path.join(SCR, "explore.json"), "w"), indent=0)
    for k, v in rep.items():
        print(k, v if not isinstance(v, list) or len(v) < 60 else v[:60])


def measure(args):
    from mathutils import Vector
    from cradle_ai_analyze import bvh
    M, R = fitted(); ST, AL, AR = M["static"], M["arm_L"], M["arm_R"]
    tS = bvh(*ST); tA = bvh(*AR); cz = S.CZ
    out = {}
    def top(tree, pts):
        h = []
        for p in pts:
            r = tree.ray_cast(Vector((p[0], 3.0, p[1])), Vector((0, -1, 0)), 5)
            h.append(round(r[0].y, 4) if r[0] else None)
        return h
    def side(tree, origin_fn, dirv, ys):
        out_ = []
        for y in ys:
            o_ = origin_fn(y); r = tree.ray_cast(Vector(o_), Vector(dirv), 5)
            out_.append(round(float(np.linalg.norm(np.array(r[0])[[0, 2]] - np.array([0, cz]))), 4) if r[0] else None)
        return out_
    rr = np.arange(0.0, 1.26, 0.002)
    for name, ang in (("X", 0.0), ("Zfront", -90.0), ("corner22", -22.5), ("diag45", -45.0), ("Zback", 90.0)):
        a = math.radians(ang); d = np.array([math.cos(a), math.sin(a)])
        out["top_" + name] = top(tS, [(r_ * d[0], cz + r_ * d[1]) for r_ in rr])
        ys = np.arange(0.002, 0.95, 0.002)
        out["wall_" + name] = side(tS, lambda y: (3 * d[0], y, cz + 3 * d[1]), (-d[0], 0, -d[1]), ys)
    out["rr"] = rr.round(4).tolist(); out["ys"] = np.arange(0.002, 0.95, 0.002).round(4).tolist()
    json.dump(out, open(os.path.join(SCR, "profiles.json"), "w"))
    # plots: top profiles (r, h) and wall profiles (r, y)
    sets = []
    cols = {"X": (0, 0, 0), "Zfront": (0.8, 0, 0), "corner22": (0, 0.6, 0), "diag45": (0, 0, 0.8), "Zback": (0.8, 0.5, 0)}
    for k, c in cols.items():
        p = [(r_, h) for r_, h in zip(rr, out["top_" + k]) if h is not None]
        segs = np.array([[p[i], p[i + 1]] for i in range(len(p) - 1) if abs(p[i + 1][1] - p[i][1]) < 0.2])
        sets.append((segs, c))
    raster(sets, "prof_top.png", ((0, 0), (1.26, 0.95)), 1500, grid=0.02)
    sets = []
    for k, c in cols.items():
        p = [(r_, y) for r_, y in zip(out["wall_" + k], out["ys"]) if r_ is not None]
        segs = np.array([[p[i], p[i + 1]] for i in range(len(p) - 1)])
        sets.append((segs, c))
    raster(sets, "prof_wall.png", ((0, 0), (1.26, 0.95)), 1500, grid=0.02)
    print("OK")
