"""Cradle v2 STEP 1 analysis + renders. Called from cradle_ai_study.py (stages analyze / render).
All distances in metres, spec (Unity) axes unless a line says "native"."""
import bpy, os, json, math, sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import cradle_ai_study as S

RNG = np.random.default_rng(7)
OUT = os.path.join(S.CACHE, "analysis.json")
VOL_Y0 = 1.19                                   # drone flight volume floor (ENVIRONMENT_SPEC)
GAP = 0.003                                     # docking gap target
PAD_T = 0.010                                   # thinnest amber pad


def load(name):
    d = np.load(os.path.join(S.CACHE, name + ".npz")); return d["v"], d["t"]


def bvh(v, t): return BVHTree.FromPolygons(v.tolist(), t.tolist(), all_triangles=True)


def to_spec(v, t, s, cx, cy):
    """native -> spec. The mapping swaps y/z (a mirror), so triangle winding is reversed."""
    sv = np.column_stack((s * (v[:, 0] - cx), s * v[:, 2], S.CZ + s * (v[:, 1] - cy)))
    return sv, t[:, ::-1].copy()


def sample_surface(v, t, n):
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    idx = RNG.choice(len(t), n, p=area / area.sum())
    r1 = np.sqrt(RNG.random(n)); r2 = RNG.random(n)
    return (1 - r1)[:, None] * a[idx] + (r1 * (1 - r2))[:, None] * b[idx] + (r1 * r2)[:, None] * c[idx]


def signed(tree, pts):
    """signed distance to a closed mesh: negative = inside"""
    out = np.empty(len(pts))
    for i, p in enumerate(pts):
        loc, nrm, _, d = tree.find_nearest(Vector(p))
        out[i] = d if (Vector(p) - loc).dot(nrm) >= 0 else -d
    return out


def nearest(tree, pts):
    return np.array([tree.find_nearest(Vector(p))[3] for p in pts])


def inward_fraction(v, t):
    """share of faces whose normal points toward the mesh centre (winding sanity check)"""
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    n = np.cross(b - a, c - a); ctr = (a + b + c) / 3
    return float(np.mean(np.einsum('ij,ij->i', n, ctr - v.mean(0)) < 0))


def section(v, t, axis, level):
    """edge/plane intersection points of a triangle mesh with plane coord[axis] = level"""
    d = v[:, axis] - level
    pts = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = t[:, i], t[:, j]
        m = (d[a] * d[b]) < 0
        a, b = a[m], b[m]
        f = (d[a] / (d[a] - d[b]))[:, None]
        pts.append(v[a] + f * (v[b] - v[a]))
    return np.vstack(pts)


def fit_circle(p):
    """Kasa fit with iterative outlier rejection; p = (n,2)"""
    keep = np.ones(len(p), bool)
    for _ in range(8):
        q = p[keep]
        A = np.column_stack((2 * q[:, 0], 2 * q[:, 1], np.ones(len(q))))
        b = (q ** 2).sum(1)
        cx, cz, c = np.linalg.lstsq(A, b, rcond=None)[0]
        r = math.sqrt(c + cx * cx + cz * cz)
        res = np.abs(np.hypot(p[:, 0] - cx, p[:, 1] - cz) - r)
        keep = res < max(0.0015, 2.5 * np.median(res[keep]))
    return cx, cz, r, float(np.sqrt(np.mean(res[keep] ** 2))), float(keep.mean()), int(keep.sum())


def rot_axis(pts, origin, axis, deg):
    k = axis / np.linalg.norm(axis); th = math.radians(deg)
    p = pts - origin
    return origin + p * math.cos(th) + np.cross(k, p) * math.sin(th) + np.outer(p @ k, k) * (1 - math.cos(th))


def yaw(p, deg, about):
    """Unity rotation about +Y by deg (positive turns +Z toward +X)"""
    th = math.radians(deg); c, s = math.cos(th), math.sin(th)
    q = p - about
    return np.column_stack((q[:, 0] * c + q[:, 2] * s, q[:, 1], -q[:, 0] * s + q[:, 2] * c)) + about


def box(c, size, yaw_deg=0.0):
    """spec box (verts, tris) centred c, size (x,y,z), yawed about Y"""
    hx, hy, hz = np.array(size) / 2
    v = np.array([[x, y, z] for x in (-hx, hx) for y in (-hy, hy) for z in (-hz, hz)])
    v = yaw(v, yaw_deg, np.zeros(3)) + c
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    t = []
    for a, b, cc, d in q: t += [(a, b, cc), (a, cc, d)]
    t = np.array(t)
    # make winding outward
    if inward_fraction(v, t) > 0.5: t = t[:, ::-1].copy()
    return v, t


# ----------------------------------------------------------------------------- analysis
def run(args):
    B = json.load(open(os.path.join(S.CACHE, "build.json"))); cx, cy = B["cx"], B["cy"]
    R = {"centre_native": [cx, cy]}
    raw_v, raw_t = load("AI_geo1p5m_Mesh_0")
    parts = {k: load("AI_split_" + k) for k in ("part_0", "part_1", "part_2")}
    print("PASS loaded raw", len(raw_t), "tris; split", {k: len(v[1]) for k, v in parts.items()})
    raw_tree = bvh(raw_v, raw_t)

    # --- 3. split vs raw alignment (native, as delivered: no transform needed)
    al = {}
    for k, (v, t) in parts.items():
        d = nearest(raw_tree, sample_surface(v, t, 20000))
        al[k] = dict(mean_mm=1e3 * d.mean(), p95_mm=1e3 * np.percentile(d, 95), max_mm=1e3 * d.max())
    split_all = (np.vstack([p[0] for p in parts.values()]),
                 np.vstack([parts["part_0"][1], parts["part_1"][1] + len(parts["part_0"][0]),
                            parts["part_2"][1] + len(parts["part_0"][0]) + len(parts["part_1"][0])]))
    d = nearest(bvh(*split_all), sample_surface(raw_v, raw_t, 30000))
    al["raw_to_split"] = dict(mean_mm=1e3 * d.mean(), p95_mm=1e3 * np.percentile(d, 95), max_mm=1e3 * d.max())
    R["alignment"] = al; print("ALIGN", json.dumps(al, indent=0))

    # --- 4. mirror symmetry across x = c (native)
    smp = sample_surface(raw_v, raw_t, 20000)
    best = None
    for c in np.arange(cx - 0.004, cx + 0.0041, 0.0005):
        m = smp.copy(); m[:, 0] = 2 * c - m[:, 0]
        e = nearest(raw_tree, m).mean()
        if best is None or e < best[1]: best = (c, e)
    c = best[0]
    smp = sample_surface(raw_v, raw_t, 120000)
    m = smp.copy(); m[:, 0] = 2 * c - m[:, 0]
    d = nearest(raw_tree, m)
    def region(p):
        x, y, z = p
        if z > 0.595: return "plates"
        if z < 0.135: return "plinth"
        if abs(x) < 0.065 and z < 0.36: return "column/hub"
        if 0.19 < z < 0.30 and abs(x) < 0.23: return "hinge blocks/caps"
        return "arms"
    regs = {}
    for p, dd in zip(smp, d):
        r = region(p); regs.setdefault(r, []).append(dd)
    worst = np.argsort(d)[-12:][::-1]
    R["symmetry"] = dict(plane_x_native=float(c), plane_offset_from_plinth_centre_mm=1e3 * (c - cx),
                         mean_mm=1e3 * d.mean(), p95_mm=1e3 * np.percentile(d, 95), p99_mm=1e3 * np.percentile(d, 99),
                         max_mm=1e3 * d.max(),
                         by_region={r: dict(mean_mm=1e3 * np.mean(v), p99_mm=1e3 * np.percentile(v, 99), max_mm=1e3 * np.max(v), n=len(v))
                                    for r, v in regs.items()},
                         worst_points_native=[[*np.round(smp[i], 4).tolist(), round(1e3 * d[i], 1), region(smp[i])] for i in worst])
    print("SYM", json.dumps(R["symmetry"], indent=0))

    # --- plates (native): top plane, extents, flat top
    pl = {}
    for side, sg in (("L", -1), ("R", 1)):
        sel = (raw_v[:, 2] > 0.595) & (raw_v[:, 0] * sg > 0.05)
        pv = raw_v[sel]
        ztop = pv[:, 2].max()
        top = pv[pv[:, 2] > ztop - 0.001]
        pl[side] = dict(x=[float(pv[:, 0].min()), float(pv[:, 0].max())], y=[float(pv[:, 1].min()), float(pv[:, 1].max())],
                        z=[float(pv[:, 2].min()), float(ztop)],
                        top_flat_x=[float(top[:, 0].min()), float(top[:, 0].max())],
                        top_flat_y=[float(top[:, 1].min()), float(top[:, 1].max())])
        # height profile across the plate width through its middle (edge step)
        xm = (pl[side]["x"][0] + pl[side]["x"][1]) / 2
        prof = []
        for yy in np.linspace(pl[side]["y"][0] - 0.002, pl[side]["y"][1] + 0.002, 41):
            h = raw_tree.ray_cast(Vector((xm, yy, 1.0)), Vector((0, 0, -1)), 2)
            prof.append(round(h[0].z, 4) if h[0] else None)
        pl[side]["profile_across_z"] = prof
    R["plates_native"] = pl; print("PLATES", json.dumps(pl, indent=0))

    # --- 5. hinge pins: circle fits on sections through the caps (native)
    pins = {}
    for side, sg in (("L", -1), ("R", 1)):
        for face, levels in (("front", np.arange(-0.0940, -0.0870, 0.0010)), ("back", np.arange(0.0700, 0.0845, 0.0010))):
            fits = []
            for lv in levels:
                p = section(raw_v, raw_t, 1, lv)
                p = p[(p[:, 0] * sg > 0.07) & (p[:, 0] * sg < 0.23) & (p[:, 2] > 0.18) & (p[:, 2] < 0.32)]
                if len(p) < 30: continue
                fx, fz, r, rms, inl, n = fit_circle(p[:, [0, 2]])
                fits.append(dict(level=float(lv), x=fx, z=fz, r=r, rms_mm=1e3 * rms, inliers=inl, n=n))
            pins[f"{side}_{face}"] = fits
    R["pin_sections"] = pins
    for k, fits in pins.items():
        print("PIN", k); [print("   ", {a: (round(b, 5) if isinstance(b, float) else b) for a, b in f.items()}) for f in fits]
    json.dump(R, open(OUT, "w"), indent=1, default=float)


def pick_pins(R):
    """one centre per cap: the section level with the lowest rms among those with a clean circle"""
    out = {}
    for k, fits in R["pin_sections"].items():
        good = [f for f in fits if f["inliers"] > 0.8 and 0.02 < f["r"] < 0.06]
        f = min(good, key=lambda f: f["rms_mm"]) if good else None
        out[k] = f
    return out


def docking(args):
    R = json.load(open(OUT)); cx, cy = R["centre_native"]
    pins = pick_pins(R)
    axes = {}
    for side in ("L", "R"):
        f, b = pins[f"{side}_front"], pins[f"{side}_back"]
        p0 = np.array([f["x"], f["level"], f["z"]]); p1 = np.array([b["x"], b["level"], b["z"]])
        dvec = (p1 - p0) / np.linalg.norm(p1 - p0)
        axes[side] = dict(front=p0, back=p1, dir=dvec, r_front=f["r"], r_back=b["r"],
                          angle_to_Y_deg=math.degrees(math.acos(abs(dvec[1]))))
    print("AXES native", {k: {a: np.round(b, 5).tolist() if hasattr(b, 'tolist') else round(b, 4) for a, b in v.items()} for k, v in axes.items()})
    sym = dict(dx_mm=1e3 * ((axes["L"]["front"][0] + axes["R"]["front"][0]) / 2 - R["symmetry"]["plane_x_native"]),
               dz_mm=1e3 * (axes["L"]["front"][2] - axes["R"]["front"][2]),
               angle_between_deg=math.degrees(math.acos(min(1, abs(axes["L"]["dir"] @ axes["R"]["dir"])))))
    print("AXES symmetry (native mm)", sym)
    R["pin_axes_native"] = {k: {a: (b.tolist() if hasattr(b, 'tolist') else b) for a, b in v.items()} for k, v in axes.items()}
    R["pin_axes_symmetry"] = sym

    parts = {k: load("AI_split_" + k) for k in ("part_0", "part_1", "part_2")}
    drone = S.read_drone_obj()
    dv = {k: v for k, (v, t) in drone.items() if k != "ScannerGlow"}
    dt = {k: t for k, (v, t) in drone.items() if k != "ScannerGlow"}   # Unity winding reads outward here
    for k in ("Body_low", "ArmLeft_low"):
        print("CHECK drone inward-face fraction", k, round(inward_fraction(dv[k], dt[k]), 3))
    eng = {k: (dv[n][:, [0, 2]].min(0) + dv[n][:, [0, 2]].max(0)) / 2 for k, n in
           (("FR", "Engine1_low"), ("FL", "Engline2_low"), ("BR", "Engine3_low"), ("BL", "Engine4_low"))}
    body_c = (dv["Body_low"].min(0) + dv["Body_low"].max(0)) / 2
    P0 = np.array([0.0, 2.0, 4.76])                       # DroneAI2 today (live)
    FRONT_Y, BACK_Y = 1.7121, 1.7665                      # limb flat undersides (ray cast, live mesh)
    ztop = {s: R["plates_native"][s]["z"][1] for s in ("L", "R")}
    pcz = {s: (R["plates_native"][s]["y"][0] + R["plates_native"][s]["y"][1]) / 2 for s in ("L", "R")}

    # FR-BL pair: line through both engine centres -> spec +X/-X
    v = eng["FR"] - eng["BL"]; th_pair = math.degrees(math.atan2(v[1], v[0]))   # angle x->z
    mid_pair = np.array([(eng["FR"][0] + eng["BL"][0]) / 2, 0, (eng["FR"][1] + eng["BL"][1]) / 2])
    opts = {}
    for name, s, thick_R, thick_L, mode in (("A", None, PAD_T, PAD_T + BACK_Y - FRONT_Y, "pair"),
                                            ("B", None, 0.0, 0.0, "front"),
                                            ("C", 2.45, PAD_T, PAD_T + BACK_Y - FRONT_Y, "pair")):
        if s is None:                                      # keep drone height: pad top = front limb - gap
            s = (FRONT_Y - GAP - thick_R) / ztop["R"]
        plate_top = {k: s * ztop[k] for k in ztop}
        dy = plate_top["R"] + thick_R + GAP - FRONT_Y
        plate_z = {k: S.CZ + s * (pcz[k] - cy) for k in pcz}
        if mode == "pair":
            theta = th_pair                                # Unity yaw that turns FR->+X
            about = mid_pair
            target = np.array([0.0, 0.0, (plate_z["L"] + plate_z["R"]) / 2])
        else:
            theta = 0.0
            about = np.array([body_c[0], 0, body_c[2]])
            dz = 0.45 * math.sin(math.radians(28.1))       # front limbs' flat mid (r 0.45) on the plate centre line
            target = np.array([0.0, 0.0, (plate_z["L"] + plate_z["R"]) / 2 + dz])
        def pose(p, theta=theta, about=about, target=target, dy=dy):
            q = yaw(p, theta, about) - about + target
            q[:, 1] += dy
            return q
        newP = pose(P0[None])[0]
        opts[name] = dict(s=s, yaw_deg=theta, dy=dy, pad_R=thick_R, pad_L=thick_L, DroneAI2_new=newP.tolist(),
                          DroneAI2_move=(newP - P0).tolist(), move_len=float(np.linalg.norm(newP - P0)),
                          body_centre_new=pose(body_c[None])[0].tolist(), plate_top=plate_top, plate_z=plate_z, mode=mode)
        opts[name]["_pose"] = pose
    R["options"] = {}
    for name, o in opts.items():
        rep = evaluate(name, o, parts, dv, dt, axes, R, cx, cy)
        R["options"][name] = {k: v for k, v in o.items() if not k.startswith("_")} | rep
    json.dump(R, open(OUT, "w"), indent=1, default=float)
    print("WROTE", OUT)


def pads_for(o, R, cx, cy):
    """amber pads under the two contact limbs (spec boxes), lying along the limb on the plate"""
    pads = []
    s = o["s"]
    for side, sg in (("L", -1), ("R", 1)):
        t = o["pad_" + side]
        if t <= 0: continue
        r0, r1 = 0.29, 0.61                                # limb flat underside span from the drone centre
        cxz = np.array([sg * (r0 + r1) / 2, o["plate_top"][side] + t / 2, o["plate_z"][side]])
        pads.append((side, box(cxz, (r1 - r0, t, 0.14))))
    return pads


def evaluate(name, o, parts, dv, dt, axes, R, cx, cy):
    s = o["s"]; pose = o["_pose"]; rep = {}
    cr = {k: to_spec(*parts[k], s, cx, cy) for k in parts}
    rep["inward_frac"] = {k: round(inward_fraction(*cr[k]), 3) for k in cr}
    pads = pads_for(o, R, cx, cy)
    groups = {"static": cr["part_0"], "arm_L": cr["part_1"], "arm_R": cr["part_2"]}
    for side, pv in pads: groups["pad_" + side] = pv
    trees = {k: bvh(*v) for k, v in groups.items()}
    allv = np.vstack([v for v, t in groups.values()])
    # dimensions
    plin = cr["part_0"][0]; low = plin[plin[:, 1] < 0.02 * s]
    rep["dims"] = dict(plinth_across_flats_x=float(np.ptp(low[:, 0])), plinth_across_flats_z=float(np.ptp(low[:, 2])),
                       total_height_with_pads=float(allv[:, 1].max()),
                       plate_len_x=s * float(np.diff(R["plates_native"]["R"]["x"])[0]),
                       plate_width_z=s * float(np.diff(R["plates_native"]["R"]["y"])[0]),
                       plate_inner_edges_x=[s * (R["plates_native"]["L"]["x"][1] - cx), s * (R["plates_native"]["R"]["x"][0] - cx)],
                       plate_outer_edges_x=[s * (R["plates_native"]["L"]["x"][0] - cx), s * (R["plates_native"]["R"]["x"][1] - cx)],
                       static_top_y=float(cr["part_0"][0][:, 1].max()))
    # pins in spec
    pins = {}
    for side in ("L", "R"):
        a = axes[side]
        f = to_spec(a["front"][None], np.zeros((0, 3), int), s, cx, cy)[0][0]
        b = to_spec(a["back"][None], np.zeros((0, 3), int), s, cx, cy)[0][0]
        pins[side] = dict(front=f.tolist(), back=b.tolist(), r=s * (a["r_front"] + a["r_back"]) / 2)
    rep["pins_spec"] = pins
    # drone groups in dock pose
    D = {k: pose(v) for k, v in dv.items()}
    dgroups = {"body(Body,Ring,Top,ToShoot)": ["Body_low", "Ring_low", "Top_low", "ToShoot_low"],
               "limbs": ["ArmLeft_low", "ArmRight_low"],
               "engines": ["Engine1_low", "Engline2_low", "Engine3_low", "Engine4_low"],
               "propellers(blades)": ["Propellor1_low", "Propellor2_low", "Propellor3_low", "Propellor4_low"]}
    clr = {}
    for gname, members in dgroups.items():
        pts = np.vstack([sample_surface(D[m], dt[m], 6000) for m in members])
        for cname, tr in trees.items():
            if cname.startswith("pad_"):                     # exact box distance (axis-aligned pads)
                bv = groups[cname][0]; c = (bv.min(0) + bv.max(0)) / 2; h = (bv.max(0) - bv.min(0)) / 2
                q = np.abs(pts - c) - h
                sd = np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(1), 0)
            else:
                sd = signed(tr, pts)
            clr[f"{gname} -> {cname}"] = round(1e3 * float(sd.min()), 1)
    rep["clearance_mm"] = clr
    # spinning propeller discs vs cradle
    pd = {}
    for pn, en in (("Propellor1_low", "Engine1_low"), ("Propellor2_low", "Engline2_low"),
                   ("Propellor3_low", "Engine3_low"), ("Propellor4_low", "Engine4_low")):
        e = D[en]; c = (e.min(0) + e.max(0)) / 2
        p = D[pn]; rad = np.hypot(p[:, 0] - c[0], p[:, 2] - c[2]).max(); y0, y1 = p[:, 1].min(), p[:, 1].max()
        q = allv[(np.abs(allv[:, 0] - c[0]) < rad + 0.3) & (np.abs(allv[:, 2] - c[2]) < rad + 0.3)]
        if len(q):
            h = np.maximum(np.hypot(q[:, 0] - c[0], q[:, 2] - c[2]) - rad, 0)
            v_ = np.maximum(np.maximum(y0 - q[:, 1], q[:, 1] - y1), 0)
            pd[pn] = round(1e3 * float(np.hypot(h, v_).min()), 1)
        else: pd[pn] = None
    rep["prop_disc_clearance_mm"] = pd
    # contact: ray down from the limb underside
    con = {}
    limb_dirs = {}
    for k, n in (("FR", "Engine1_low"), ("FL", "Engline2_low"), ("BR", "Engine3_low"), ("BL", "Engine4_low")):
        e = D[n]; limb_dirs[k] = (e.min(0) + e.max(0)) / 2
    bc = (D["Body_low"].min(0) + D["Body_low"].max(0)) / 2
    limb_tree = bvh(np.vstack([D["ArmLeft_low"], D["ArmRight_low"]]),
                    np.vstack([dt["ArmLeft_low"], dt["ArmRight_low"] + len(D["ArmLeft_low"])]))
    cradle_tree = bvh(allv, np.vstack(_offset_tris(groups)))
    for k, ec in limb_dirs.items():
        u = np.array([ec[0] - bc[0], ec[2] - bc[2]]); L = np.linalg.norm(u); u /= L; nrm = np.array([-u[1], u[0]])
        gaps = []; lat = []
        for r in np.linspace(0.30, 0.60, 13):
            for w in np.linspace(-0.045, 0.045, 7):
                x, z = np.array([bc[0], bc[2]]) + u * r + nrm * w
                hu = limb_tree.ray_cast(Vector((x, 0.5, z)), Vector((0, 1, 0)), 3)
                if hu[0] is None: continue
                hd = cradle_tree.ray_cast(Vector((x, hu[0].y - 1e-4, z)), Vector((0, -1, 0)), 3)
                if hd[0] is None: continue
                gaps.append(hu[0].y - hd[0].y)
        if gaps:
            g = np.array(gaps)
            con[k] = dict(min_mm=round(1e3 * g.min(), 1), mean_mm=round(1e3 * g.mean(), 1), max_mm=round(1e3 * g.max(), 1), n=len(g))
    rep["limb_gap_to_cradle_below_mm"] = con
    # lateral offset of each contact limb from its plate centre line
    rep["limb_axis_vs_plate"] = {}
    for k, ec in limb_dirs.items():
        u = np.array([ec[0] - bc[0], ec[2] - bc[2]]); u /= np.linalg.norm(u)
        side = "R" if u[0] > 0 else "L"
        mid = np.array([bc[0], bc[2]]) + u * 0.45
        rep["limb_axis_vs_plate"][k] = dict(side=side, limb_mid_xz=np.round(mid, 3).tolist(),
                                            dz_from_plate_centre_mm=round(1e3 * (mid[1] - o["plate_z"][side]), 1),
                                            limb_angle_deg=round(math.degrees(math.atan2(u[1], u[0])), 2))
    # release sweep: arm+pad about its pin axis, outward
    st_tree = trees["static"]; st_v = groups["static"][0]
    rel = {}
    for side, sg, part in (("L", -1, "arm_L"), ("R", 1, "arm_R")):
        f = np.array(pins[side]["front"]); b = np.array(pins[side]["back"]); ax = b - f
        ax = ax / np.linalg.norm(ax)
        if ax[2] < 0: ax = -ax                               # point along +Z
        v, t = groups[part]
        mv = [v] + ([groups["pad_" + side][0]] if "pad_" + side in groups else [])
        mt = [t] + ([groups["pad_" + side][1] + len(v)] if "pad_" + side in groups else [])
        av = np.vstack(mv); at = np.vstack(mt)
        arm_tree = bvh(av, at)
        smp_arm = sample_surface(av, at, 15000)
        near_st = st_v[np.linalg.norm(st_v - f, axis=1) < 0.9 * s * 0.45]
        near_st = near_st[RNG.choice(len(near_st), min(15000, len(near_st)), replace=False)]
        rows = []
        # outward: top goes toward sg*X. Rotating +Y about +Z by +deg moves it to -X.
        sgn = 1 if sg < 0 else -1
        for deg in range(0, 181, 5):
            p = rot_axis(smp_arm, f, ax, sgn * deg)
            maxy = float(rot_axis(av, f, ax, sgn * deg)[:, 1].max())
            sd1 = signed(st_tree, p)
            q = rot_axis(near_st, f, ax, -sgn * deg)          # static into the arm's frame
            sd2 = signed(arm_tree, q)
            rows.append(dict(deg=deg, max_y=round(maxy, 4), arm_in_static=int((sd1 < -0.002).sum()),
                             arm_depth_mm=round(-1e3 * min(0, sd1.min()), 1),
                             static_in_arm=int((sd2 < -0.002).sum()), static_depth_mm=round(-1e3 * min(0, sd2.min()), 1),
                             min_y=round(float(p[:, 1].min()), 4)))
        base = rows[0]
        below = next((r["deg"] for r in rows if r["max_y"] < VOL_Y0), None)
        # the pin sits inside the arm boss in the AI mesh: a constant ~20 mm overlap at every angle.
        # A real hit = overlap grows by > 5 mm or the overlapping sample count jumps by half.
        bd = max(r["arm_depth_mm"] for r in rows[:8]); bs = max(r["static_depth_mm"] for r in rows[:8])
        bn = max(r["arm_in_static"] for r in rows[:8]); bm = max(r["static_in_arm"] for r in rows[:8])
        def hit(r):
            return (r["arm_depth_mm"] > bd + 5 or r["static_depth_mm"] > bs + 5
                    or r["arm_in_static"] > 1.5 * bn or r["static_in_arm"] > 1.5 * bm)
        first_hit = next((r["deg"] for r in rows if hit(r)), None)
        floor = next((r["deg"] for r in rows if r["min_y"] < 0), None)
        lim = min(x for x in (first_hit, floor, 185) if x is not None)
        rel[side] = dict(axis_dir=ax.tolist(), below_1_19_at_deg=below, first_static_collision_deg=first_hit,
                         first_floor_contact_deg=floor, max_free_deg=lim - 5, rows=rows)
    rep["release"] = rel
    # protected volumes (ENVIRONMENT_SPEC)
    fp = np.hypot(allv[:, 0] - 0.03, allv[:, 2] - 1.23).min() - 1.24
    pl = np.hypot(allv[:, 0], allv[:, 2]).min() - 1.0
    sp = np.hypot(allv[:, 0] + 1, allv[:, 2] - 13.0).min() - 0.6
    rep["protected_clearance_m"] = dict(labyrinth=round(float(fp), 3), player=round(float(pl), 3), spawn=round(float(sp), 3),
                                        cradle_xz_bounds=[np.round(allv[:, [0, 2]].min(0), 3).tolist(), np.round(allv[:, [0, 2]].max(0), 3).tolist()])
    print(f"OPTION {name}: s {s:.4f} yaw {o['yaw_deg']:.2f} dy {o['dy']:.4f} DroneAI2 -> {np.round(o['DroneAI2_new'], 4)}")
    print("  dims", {k: (np.round(v, 4).tolist() if isinstance(v, list) else round(v, 4)) for k, v in rep["dims"].items()})
    print("  clearance_mm", rep["clearance_mm"]); print("  prop discs", rep["prop_disc_clearance_mm"])
    print("  limb gaps", rep["limb_gap_to_cradle_below_mm"]); print("  limb vs plate", rep["limb_axis_vs_plate"])
    for side, r in rel.items():
        print(f"  release {side}: below 1.19 at {r['below_1_19_at_deg']} deg, static hit {r['first_static_collision_deg']}, floor {r['first_floor_contact_deg']}, max free {r['max_free_deg']}")
    print("  protected", rep["protected_clearance_m"])
    return rep


def _offset_tris(groups):
    out = []; off = 0
    for v, t in groups.values():
        out.append(t + off); off += len(v)
    return out


# ----------------------------------------------------------------------------- renders
DSP = np.array([[-1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])          # spec -> Blender (a mirror)


def spec_affine_to_blender(A, t):
    """spec map p -> A p + t  ==>  Blender 4x4"""
    Ab = DSP @ A @ DSP.T; tb = DSP @ t
    M = Matrix.Identity(4)
    for i in range(3):
        for j in range(3): M[i][j] = Ab[i, j]
        M[i][3] = tb[i]
    return M


def yaw_matrix(deg):
    th = math.radians(deg); c, s = math.cos(th), math.sin(th)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def axis_matrix(axis, deg):
    k = axis / np.linalg.norm(axis); th = math.radians(deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def spec_mesh(name, v, t, coll, color):
    me = bpy.data.meshes.new(name)
    me.from_pydata([Vector(DSP @ p) for p in v], [], [tuple(int(i) for i in f[::-1]) for f in t])
    me.update(); o = bpy.data.objects.new(name, me); coll.objects.link(o); o.color = color
    return o


def render(args):
    opt = args[0] if args else "A"
    release_deg = float(args[1]) if len(args) > 1 else 75.0
    R = json.load(open(OUT)); cx, cy = R["centre_native"]; o = R["options"][opt]
    bpy.ops.wm.open_mainfile(filepath=S.BLEND)
    sc = bpy.context.scene
    for c in bpy.data.collections:
        c.hide_render = c.name not in ("SRC_split", "DRONE_FBX", "AI_SOURCES", "STUDY")
    root = bpy.data.objects["AI_Root"]; root.scale = (o["s"],) * 3
    GREY, ARM, AMBER, YEL = (0.30, 0.31, 0.34, 1), (0.42, 0.43, 0.47, 1), (1.0, 0.55, 0.05, 1), (0.95, 0.80, 0.20, 1)
    for ob in bpy.data.collections["SRC_split"].objects:
        ob.color = GREY if ob.name.endswith("part_0") else ARM
    st = bpy.data.collections.new("STUDY"); sc.collection.children.link(st)
    pads = {side: spec_mesh(f"STUDY_Pad_{side}", pv[0], pv[1], st, AMBER) for side, pv in pads_for(o, R, cx, cy)}
    # floor + drone-volume floor frame (y 1.19)
    fv, ft = box(np.array([0, -0.005, S.CZ]), (8, 0.01, 8)); spec_mesh("STUDY_Floor", fv, ft, st, (0.55, 0.55, 0.57, 1))
    # drone into the docking pose
    A = yaw_matrix(o["yaw_deg"])
    P0 = np.array([0.0, 2.0, 4.76]); P1 = np.array(o["DroneAI2_new"])
    # DroneAI2 moves P0 -> P1 and turns by yaw: world p -> A (p - P0) + P1
    Md = spec_affine_to_blender(A, P1 - A @ P0)
    for ob in bpy.data.collections["DRONE_FBX"].objects:
        if ob.parent is None: ob.matrix_world = Md @ ob.matrix_world
        if ob.type == 'MESH': ob.color = (0.75, 0.8, 0.85, 1) if "Propellor" in ob.name else YEL
    sh = sc.display.shading
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.render.resolution_x, sc.render.resolution_y = 2400, 1500
    sc.render.resolution_percentage = 100; sc.display.render_aa = '16'
    sh.light = 'STUDIO'; sh.color_type = 'OBJECT'; sh.show_cavity = True; sh.cavity_type = 'BOTH'
    sh.show_object_outline = True; sh.show_shadows = True; sh.shadow_intensity = 0.35
    sh.background_type = 'VIEWPORT'; sh.background_color = (0.18, 0.19, 0.21)
    tgt = Vector(DSP @ np.array([0, 1.0, S.CZ]))
    def cam(name, loc_spec, ortho=None, look=None, up_rot=None):
        cd = bpy.data.cameras.new(name); cd.clip_end = 100
        c = bpy.data.objects.new(name, cd); sc.collection.objects.link(c)
        c.location = Vector(DSP @ np.array(loc_spec))
        look = Vector(DSP @ np.array(look)) if look is not None else tgt
        c.rotation_euler = (look - c.location).to_track_quat('-Z', 'Y').to_euler()
        if up_rot is not None: c.rotation_euler = up_rot
        if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
        else: cd.lens = 40
        sc.camera = c
    def shot(fn):
        sc.render.filepath = os.path.join(S.RENDERS, fn); bpy.ops.render.render(write_still=True); print("RENDER", fn)
    tag = "" if opt == "A" else "_" + opt
    if len(args) < 3 or args[2] != "release_only":
        cam("CamFront", [0, 1.0, S.CZ - 8], ortho=3.4); shot(f"cradle_ai_dock_front{tag}.png")
        cam("Cam34", [-2.9, 2.5, S.CZ - 3.4], look=[0, 0.95, S.CZ]); shot(f"cradle_ai_dock_34{tag}.png")
        cam("CamTop", [0, 8, S.CZ], ortho=4.0, up_rot=(0, 0, math.pi)); shot(f"cradle_ai_dock_top{tag}.png")
    # release: arms (+pads) fold outward about their pin axes, drone lifted 0.5 m
    for side, part in (("L", "part_1"), ("R", "part_2")):
        f = np.array(o["pins_spec"][side]["front"]); ax = np.array(o["release"][side]["axis_dir"])
        sgn = 1 if side == "L" else -1
        Ar = axis_matrix(ax, sgn * release_deg); Mr = spec_affine_to_blender(Ar, f - Ar @ f)
        arm = next(ob for ob in bpy.data.collections["SRC_split"].objects if ob.name.endswith(part))
        arm.matrix_world = Mr @ arm.matrix_world
        if side in pads: pads[side].matrix_world = Mr @ pads[side].matrix_world
    Ml = spec_affine_to_blender(np.eye(3), np.array([0, 0.5, 0]))
    for ob in bpy.data.collections["DRONE_FBX"].objects:
        if ob.parent is None: ob.matrix_world = Ml @ ob.matrix_world
    RED = (0.9, 0.1, 0.1, 1)
    for i, (c, sz) in enumerate(((np.array([0, 1.19, S.CZ - 1.4]), (2.9, 0.012, 0.012)), (np.array([0, 1.19, S.CZ + 1.4]), (2.9, 0.012, 0.012)),
                                 (np.array([-1.45, 1.19, S.CZ]), (0.012, 0.012, 2.8)), (np.array([1.45, 1.19, S.CZ]), (0.012, 0.012, 2.8)))):
        bv, bt = box(c, sz); spec_mesh(f"STUDY_Vol119_{i}", bv, bt, st, RED)
    cam("CamRel", [0, 1.1, S.CZ - 8], ortho=3.6); shot(f"cradle_ai_release{tag}.png")
    cam("CamRel34", [-2.9, 2.5, S.CZ - 3.4], look=[0, 0.95, S.CZ]); shot(f"cradle_ai_release_34{tag}.png")
