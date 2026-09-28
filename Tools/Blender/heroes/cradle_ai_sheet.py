"""Cradle v2 STEP 2 - perpendicular arm / plate / hinge sections and the annotated section sheet.
  blender -b --factory-startup --python cradle_ai_study.py -- sheet
Output: Renders/cradle_ai_sections.png, Temp/claude/cradle_ai/sections/arm_sections.json"""
import os, json, math
import numpy as np
import bpy
from mathutils import Vector
import cradle_ai_study as S
from cradle_ai_sections import fitted, section_segments, plane2d, SCR


def local_section(v, t, origin, normal, e1, e2):
    n = np.array(normal, float); n /= np.linalg.norm(n)
    seg = section_segments(v, t, n, float(n @ np.array(origin, float)))
    q = seg - np.array(origin, float)
    return np.stack((q @ np.array(e1, float), q @ np.array(e2, float)), axis=-1)


def ext(seg2d):
    p = seg2d.reshape(-1, 2)
    if len(p) == 0: return None
    return [round(float(p[:, 0].min()), 4), round(float(p[:, 0].max()), 4), round(float(p[:, 1].min()), 4), round(float(p[:, 1].max()), 4)]


def arm_sections(M, R):
    AR = M["arm_R"]; ST = M["static"]; cz = S.CZ
    out = {}

    def perp(name, p0, ang, keep):
        a = math.radians(ang)
        d = [math.sin(a), math.cos(a), 0.0]                       # arm direction in the front plane
        w = [math.cos(a), -math.sin(a), 0.0]                      # across the arm, in the front plane
        sg = local_section(*AR, [p0[0], p0[1], cz], d, w, [0, 0, 1.0])
        sg = sg[np.all(np.abs(sg[:, :, 0]) < keep, axis=1)]
        out[name] = dict(origin=list(p0), dir_from_vertical_deg=ang, extents_w_z=ext(sg), segs=sg)

    perp("lower segment", (0.510, 0.840), 31.7, 0.3)
    perp("elbow", (0.562, 0.960), 12.0, 0.3)
    perp("upper segment", (0.537, 1.200), -6.9, 0.3)
    perp("gusset y1.48", (0.63, 1.480), 0.0, 0.5)
    perp("neck y1.57", (0.66, 1.570), 0.0, 0.5)
    sg = local_section(*AR, [0.71, 0, cz], [1, 0, 0], [0, 0, 1.0], [0, 1.0, 0]); sg = sg[np.all(sg[:, :, 1] > 1.52, axis=1)]
    out["plate across x0.71"] = dict(extents_z_y=ext(sg), segs=sg)
    sg = local_section(*AR, [0, 0, cz], [0, 0, 1], [1.0, 0, 0], [0, 1.0, 0]); sg = sg[np.all(sg[:, :, 1] > 1.52, axis=1)]
    out["plate along z4.69"] = dict(extents_x_y=ext(sg), segs=sg)
    pin = R["options"]["A"]["pins_spec"]["R"]
    px = (pin["front"][0] + pin["back"][0]) / 2; py = (pin["front"][1] + pin["back"][1]) / 2
    sg = local_section(*ST, [px, py, cz], [1, 0, 0], [0, 0, 1.0], [0, 1.0, 0])
    sg = sg[np.all(np.abs(sg[:, :, 1]) < 0.16, axis=1)]
    out["hinge at pin x"] = dict(extents_z_y=ext(sg), segs=sg, pin=[px, py])
    # hinge block face depth and cap protrusion along the pin line (ray casts along z at the pin centre)
    return out


def run(args):
    M, R = fitted()
    ST, AL, AR = M["static"], M["arm_L"], M["arm_R"]; cz = S.CZ
    arm = arm_sections(M, R)
    nums = {k: {a: b for a, b in v.items() if a != "segs"} for k, v in arm.items()}
    json.dump(nums, open(os.path.join(SCR, "arm_sections.json"), "w"), indent=1, default=float)
    for k, v in nums.items(): print("SEC", k, v)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    def quads(name, segs, off, scale, width, col):
        segs = np.asarray(segs, float)
        if len(segs) == 0: return
        a = segs[:, 0] * scale + off; b = segs[:, 1] * scale + off
        d = b - a; L = np.linalg.norm(d, axis=1); ok = L > 1e-9
        a, b, d, L = a[ok], b[ok], d[ok], L[ok]
        nrm = np.stack((-d[:, 1], d[:, 0]), 1) / L[:, None] * width / 2
        # extend each quad along its direction by half the width so joints close
        ext_ = d / L[:, None] * width / 2
        a = a - ext_; b = b + ext_
        v = np.concatenate([a - nrm, a + nrm, b + nrm, b - nrm], axis=0)
        n = len(a); idx = np.arange(n)
        f = np.stack((idx, idx + n, idx + 2 * n, idx + 3 * n), 1)
        v3 = np.column_stack((v, np.zeros(len(v))))
        me = bpy.data.meshes.new(name); me.from_pydata(v3.tolist(), [], f.tolist()); me.update()
        o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.color = col

    def text(s_, pos, size=0.06, col=(0, 0, 0, 1)):
        cu = bpy.data.curves.new("t", 'FONT'); cu.body = s_; cu.size = size
        o = bpy.data.objects.new("t", cu); sc.collection.objects.link(o)
        o.location = (pos[0], pos[1], 0.001); o.color = col

    def grid(off, scale, x0, x1, y0, y1, step):
        segs = []
        for x in np.arange(math.ceil(x0 / step - 1e-9) * step, x1 + 1e-9, step): segs.append([[x, y0], [x, y1]])
        for y in np.arange(math.ceil(y0 / step - 1e-9) * step, y1 + 1e-9, step): segs.append([[x0, y], [x1, y]])
        quads("grid", segs, off, scale, 0.002, (0.80, 0.82, 0.87, 1))

    BLK, RED, BLU = (0.05, 0.05, 0.05, 1), (0.8, 0.1, 0.1, 1), (0.1, 0.25, 0.85, 1)
    W = 0.0045

    def panel(title, off, scale, box, sets, note="", step=0.1):
        off = np.array(off, float) - np.array([box[0], box[2]]) * scale     # lower-left corner at off
        grid(off, scale, *box, step)
        for segs, col in sets: quads(title, segs, off, scale, W, col)
        text(title, (off[0] + box[0] * scale, off[1] + box[3] * scale + 0.03), 0.075)
        if note: text(note, (off[0] + box[0] * scale, off[1] + box[2] * scale - 0.09), 0.05, (0.25, 0.25, 0.3, 1))

    fz = lambda M_: plane2d(section_segments(*M_, np.array([0, 0, 1.0]), cz), [0, 1])
    panel("A  Front section, plane z 4.69  (x, y)", (0, 0), 1.0, (-1.3, 1.3, 0, 1.8),
          [(fz(ST), BLK), (fz(AL), RED), (fz(AR), BLU)],
          "grid 0.1 m.  static black, Arm_L red, Arm_R blue.  AI plinth = thin hollow shell")
    sx = plane2d(section_segments(*ST, np.array([1.0, 0, 0]), 0.0), [2, 1]); sx[:, :, 0] -= cz
    panel("B  Side section, plane x 0  (z-4.69, y)", (2.9, 0), 1.0, (-1.3, 1.3, 0, 1.0), [(sx, BLK)],
          "front (-Z, player side) at left")
    h = arm["hinge at pin x"]; py = h["pin"][1]
    hs = h["segs"].copy(); hs[:, :, 1] += py
    ha = local_section(*AR, [h["pin"][0], 0, cz], [1, 0, 0], [0, 0, 1.0], [0, 1.0, 0])
    ha = ha[np.all((ha[:, :, 1] < 0.95) & (ha[:, :, 1] > 0.45), axis=1)]
    panel("C  Hinge section, plane x = pin 0.384  (z-4.69, y)  x2", (2.9, 1.3), 2.0, (-0.35, 0.35, 0.45, 0.95),
          [(hs, BLK), (ha, BLU)], "pin axis y 0.637.  front (-Z) at left", step=0.05)
    plans = ((0.17, "tier 1 top trays"), (0.24, "tier 2"), (0.33, "turntable"), (0.60, "hinge beam"))
    offs = ((6.0, 0.0), (8.9, 0.0), (6.0, 3.0), (8.9, 3.0))
    for (yl, lab), off in zip(plans, offs):
        ss = plane2d(section_segments(*ST, np.array([0, 1.0, 0]), yl), [0, 2]); ss[:, :, 1] = -(ss[:, :, 1] - cz)
        sets = [(ss, BLK)]
        for A_ in (AL, AR):
            x = plane2d(section_segments(*A_, np.array([0, 1.0, 0]), yl), [0, 2])
            if len(x): x[:, :, 1] = -(x[:, :, 1] - cz); sets.append((x, BLU))
        panel(f"D  Plan y {yl:.2f}  ({lab})", off, 1.0, (-1.3, 1.3, -1.3, 1.3), sets, "front (-Z) at bottom")
    names = ("lower segment", "elbow", "upper segment", "gusset y1.48", "neck y1.57")
    aoffs = ((0.0, 2.3), (1.0, 2.3), (2.0, 2.3), (0.0, 3.2), (1.0, 3.2))
    for k, off in zip(names, aoffs):
        e = arm[k]["extents_w_z"]
        panel(f"E  Arm_R {k}  x1.5", off, 1.5, (-0.3, 0.3, -0.2, 0.2), [(arm[k]["segs"], BLU)],
              f"across {e[1]-e[0]:.3f}  x  depth {e[3]-e[2]:.3f}", step=0.05)
    pa = arm["plate across x0.71"]["segs"]
    panel("F  Plate across, x 0.71  (z-4.69, y)  x2", (3.1, 2.75), 2.0, (-0.25, 0.25, 1.53, 1.72), [(pa, BLU)], step=0.05)
    panel("F  Plate along, z 4.69  (x, y)  x2", (2.0, 4.1), 2.0, (0.2, 1.2, 1.53, 1.72), [(arm["plate along z4.69"]["segs"], BLU)], step=0.05)
    bpy.context.view_layer.update()
    vs = [o for o in sc.objects if o.type in ('MESH', 'FONT')]
    pts = np.array([list(o.matrix_world @ Vector(c)) for o in vs for c in o.bound_box])
    mn, mx = pts.min(0), pts.max(0)
    cd = bpy.data.cameras.new("c"); cd.type = 'ORTHO'
    cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam)
    cam.location = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, 10); sc.camera = cam
    wid, hei = mx[0] - mn[0] + 0.3, mx[1] - mn[1] + 0.3
    sc.render.resolution_x = 5600; sc.render.resolution_y = int(5600 * hei / wid); sc.render.resolution_percentage = 100
    cd.ortho_scale = max(wid, hei * 5600 / sc.render.resolution_y)
    sc.render.engine = 'BLENDER_WORKBENCH'; sh = sc.display.shading; sh.light = 'FLAT'; sh.color_type = 'OBJECT'
    sh.background_type = 'VIEWPORT'; sh.background_color = (1, 1, 1); sc.display.render_aa = '8'
    sc.view_settings.view_transform = 'Standard'
    sc.render.filepath = os.path.join(S.RENDERS, "cradle_ai_sections.png"); bpy.ops.render.render(write_still=True)
    print("RENDER cradle_ai_sections.png", sc.render.resolution_x, sc.render.resolution_y)
