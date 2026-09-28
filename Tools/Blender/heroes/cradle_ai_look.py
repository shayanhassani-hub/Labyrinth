"""quick look renders of the fitted AI static body (scratch, Temp/claude/cradle_ai/sections/look_*.png)"""
import bpy, os, math, json
import numpy as np
from mathutils import Vector
import cradle_ai_study as S
from cradle_ai_analyze import OUT, DSP


def run(args):
    R = json.load(open(OUT)); s = R["options"]["A"]["s"]
    bpy.ops.wm.open_mainfile(filepath=S.BLEND)
    sc = bpy.context.scene
    for c in bpy.data.collections: c.hide_render = c.name not in ("SRC_split", "AI_SOURCES")
    bpy.data.objects["AI_Root"].scale = (s,) * 3
    for o in bpy.data.collections["SRC_split"].objects: o.color = (0.55, 0.56, 0.6, 1)
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.render.resolution_x, sc.render.resolution_y = 1800, 1100
    sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'OBJECT'; sh.show_cavity = True; sh.cavity_type = 'BOTH'
    sh.background_type = 'VIEWPORT'; sh.background_color = (0.2, 0.2, 0.22)
    def cam(name, loc_spec, look_spec, lens=50, ortho=None):
        cd = bpy.data.cameras.new(name); c = bpy.data.objects.new(name, cd); sc.collection.objects.link(c)
        c.location = Vector(DSP @ np.array(loc_spec)); t = Vector(DSP @ np.array(look_spec))
        c.rotation_euler = (t - c.location).to_track_quat('-Z', 'Y').to_euler()
        if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
        else: cd.lens = lens
        sc.camera = c
        sc.render.filepath = os.path.join(S.CACHE, "sections", f"look_{name}.png"); bpy.ops.render.render(write_still=True)
    cz = S.CZ
    cam("front_plinth", [0, 0.25, cz - 5], [0, 0.2, cz], ortho=2.8)
    a = math.radians(45); cam("diag_front_right", [5 * math.sin(a), 0.25, cz - 5 * math.cos(a)], [0, 0.2, cz], ortho=2.8)
    cam("back_right_defect", [2.6, 1.2, cz + 2.6], [0.4, 0.1, cz + 0.4], lens=40)
    cam("top_plinth", [0, 6, cz + 0.001], [0, 0, cz], ortho=2.8)
