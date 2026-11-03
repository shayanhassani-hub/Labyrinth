"""
Terminal (Hero 02) holo screen texture: an original UI in the concept's style (terminal_front.jpg), no readable text.

  python Tools/Blender/heroes/terminal_holo.py [out.png]       (plain Python 3 + numpy + Pillow; no Blender needed)

Writes Assets/Environment/Heroes/Terminal/Textures/T_LAB_HERO_Terminal_Holo.png: 1024 x 512 RGBA (sRGB colour,
straight alpha). The display quad is 1.50 x 0.85 m, so 1024 x 512 gives 683 x 602 px/m (nearly square texels).
Material (TerminalBuilder): URP Unlit, transparent, alpha blend, both faces; the colour is the light (holo teal
120 200 205 and a paler highlight 165 225 228, H2b), the alpha is the panel's opacity (faint tint, opaque lines).

Layout (seen from the player): glowing frame with tab steps top and bottom (concept), a fine grid; left column: a
scatter field with a fitted curve, level bars and "data rows" (dashes, not glyphs); centre: a perspective wireframe of
the facility room with the cradle, the docked drone (four rotor rings) and the gate opening; right column: three line
graphs (smooth, spiky, rising). Drawn at 4x, blurred copy added as glow, downsampled.
"""
import math
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(PROJ, "Assets", "Environment", "Heroes", "Terminal", "Textures", "T_LAB_HERO_Terminal_Holo.png")
W, H, S = 1024, 512, 4                       # final size, supersampling
# H2b (owner review): the concept's paler "holo teal" for the screen only (sampled from terminal_front / ortho_front:
# lines ~135 178 182 over the grey background, hue ~186 deg); proposed STYLE_GUIDE row. The strips keep 70 170 255.
CYAN = (120, 200, 205)                       # holo teal lines and panel tint
PALE = (165, 225, 228)                       # highlights (min channel 165: no white)
RNG = np.random.default_rng(7)


class Canvas:
    def __init__(self):
        self.col = Image.new("RGB", (W * S, H * S), (0, 0, 0))
        self.a = Image.new("L", (W * S, H * S), 0)
        self.dc = ImageDraw.Draw(self.col); self.da = ImageDraw.Draw(self.a)

    def line(self, pts, alpha=230, width=1.0, col=CYAN):
        p = [(x * S, y * S) for x, y in pts]
        self.dc.line(p, fill=col, width=max(1, int(width * S)), joint="curve")
        self.da.line(p, fill=alpha, width=max(1, int(width * S)), joint="curve")

    def rect(self, x0, y0, x1, y1, alpha=230, width=1.0, col=CYAN, fill=None):
        if fill is not None:
            self.dc.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
            self.da.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)
        self.line([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], alpha, width, col)

    def dot(self, x, y, r, alpha=200, col=CYAN):
        self.dc.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=col)
        self.da.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=alpha)


def frame(c):
    """outer frame with tab steps (top: raised tab in the middle, bottom: lowered), corner brackets"""
    m = 6
    top = [(m, m + 14), (300, m + 14), (318, m), (706, m), (724, m + 14), (W - m, m + 14)]
    bot = [(W - m, H - m - 14), (724, H - m - 14), (706, H - m), (318, H - m), (300, H - m - 14), (m, H - m - 14)]
    c.line(top + bot + [top[0]], 240, 2.2, PALE)
    c.line([(m + 6, m + 22), (W - m - 6, m + 22)], 70, 0.8)
    c.line([(m + 6, H - m - 22), (W - m - 6, H - m - 22)], 70, 0.8)
    for x0, y0, sx, sy in ((m + 4, m + 18, 1, 1), (W - m - 4, m + 18, -1, 1), (m + 4, H - m - 18, 1, -1), (W - m - 4, H - m - 18, -1, -1)):
        c.line([(x0, y0 + sy * 26), (x0, y0), (x0 + sx * 26, y0)], 250, 2.6, PALE)


def grid(c):
    for x in range(16, W, 16):
        c.line([(x, 28), (x, H - 28)], 26 if x % 128 else 48, 0.6)
    for y in range(28, H - 20, 16):
        c.line([(10, y), (W - 10, y)], 26 if (y - 28) % 128 else 48, 0.6)


def data_rows(c, x0, y0, rows, w, step=11):
    """abstract text lines: dashes of random length, not glyphs"""
    for r in range(rows):
        x = x0
        while x < x0 + w:
            L = RNG.integers(6, 30)
            if x + L > x0 + w: break
            c.line([(x, y0 + r * step), (x + L, y0 + r * step)], 170, 1.6)
            x += L + RNG.integers(4, 10)


def left_column(c):
    x0, x1 = 30, 280
    c.rect(x0, 46, x1, 228, 200, 1.2)
    data_rows(c, x0, 36, 1, 110, 0)
    for i in range(14):                                                       # scatter field
        for j in range(9):
            if RNG.random() < 0.8:
                c.dot(x0 + 14 + i * 17 + RNG.normal(0, 1.5), 60 + j * 18 + RNG.normal(0, 1.5), 1.1, 140)
    xs = np.linspace(x0 + 10, x1 - 10, 60)                                    # fitted curve (V shape)
    ys = 70 + 140 * (1 - np.abs((xs - (x0 + x1) / 2) / ((x1 - x0) / 2)) ** 1.4)
    c.line(list(zip(xs, ys)), 230, 1.8, PALE)
    c.rect(x0, 240, x1, 262, 160, 1.0)
    for k in range(3):
        data_rows(c, x0 + 8 + k * 82, 251, 1, 60, 0)
    c.rect(x0, 276, x1, 470, 200, 1.2)
    data_rows(c, x0, 286 - 20, 1, 80, 0)
    for k in range(4):                                                        # level bars
        h = [120, 70, 150, 95][k]
        c.rect(x0 + 14 + k * 20, 456 - h, x0 + 26 + k * 20, 456, 220, 1.0, CYAN, fill=110)
    for r in range(8):                                                        # rows with small meters
        y = 296 + r * 20
        data_rows(c, x0 + 110, y, 1, 70, 0)
        L = RNG.integers(20, 50)
        c.rect(x1 - 60, y - 4, x1 - 60 + L, y + 3, 200, 0.8, CYAN, fill=150)


def project(P, cam, f=420.0, cx=520.0, cy=255.0):
    """simple perspective: P (n, 3) world, camera at cam looking at the room centre"""
    tgt = np.array((0.0, 1.0, 3.0)); fwd = tgt - cam; fwd /= np.linalg.norm(fwd)
    r = np.cross(np.array((0.0, 1.0, 0.0)), fwd); r /= np.linalg.norm(r); u = np.cross(fwd, r)
    d = P - cam; z = d @ fwd
    return np.column_stack((cx + f * (d @ r) / z, cy - f * (d @ u) / z))


def room_wireframe(c):
    """the facility room (8 x 4 x 10, x -4 ... 4, z -2 ... 8) in perspective: floor grid, walls, gate opening,
    cradle ring and the docked drone (four rotor rings)"""
    cam = np.array((7.5, 8.0, -9.0))
    seg = lambda a, b, al=150, w=1.0, col=CYAN: c.line([tuple(q) for q in project(np.array([a, b], float), cam)], al, w, col)
    for x in np.arange(-4, 4.01, 1.0): seg((x, 0, -2), (x, 0, 8), 70, 0.7)
    for z in np.arange(-2, 8.01, 1.0): seg((-4, 0, z), (4, 0, z), 70, 0.7)
    box = [(-4, -2), (4, -2), (4, 8), (-4, 8)]
    for (x, z), (x2, z2) in zip(box, box[1:] + box[:1]):
        seg((x, 0, z), (x2, 0, z2), 230, 1.4, PALE); seg((x, 4, z), (x2, 4, z2), 120, 1.0)
    for x, z in box: seg((x, 0, z), (x, 4, z), 150, 1.0)
    door = [(-1.8, 0, 8), (-1.8, 2.4, 8), (-0.2, 2.4, 8), (-0.2, 0, 8)]
    c.line([tuple(q) for q in project(np.array(door, float), cam)], 220, 1.4, PALE)
    def ring(cx_, y, cz, r, n=28, al=200, w=1.0, col=CYAN):
        a = np.linspace(0, 2 * math.pi, n + 1)
        P = np.column_stack((cx_ + r * np.cos(a), np.full_like(a, y), cz + r * np.sin(a)))
        c.line([tuple(q) for q in project(P, cam)], al, w, col)
    for y, r in ((0.0, 1.1), (0.35, 0.95), (0.62, 0.70)): ring(0.0, y, 4.69, r, 40, 170)       # cradle tiers
    for k in range(8):
        a = 2 * math.pi * k / 8
        seg((1.1 * math.cos(a), 0, 4.69 + 1.1 * math.sin(a)), (0.70 * math.cos(a), 0.62, 4.69 + 0.70 * math.sin(a)), 110, 0.8)
    dc = np.array((0.0, 2.0, 4.75)); yaw = math.radians(-28.3)                 # docked drone
    R = lambda v: np.array((v[0] * math.cos(yaw) - v[2] * math.sin(yaw), v[1], v[0] * math.sin(yaw) + v[2] * math.cos(yaw)))
    arms = [R((sx * 0.55, 0, sz * 0.55)) for sx in (-1, 1) for sz in (-1, 1)]          # drawn ~1.2x for legibility
    for a in arms:
        seg(dc, dc + a, 240, 1.8, PALE)
        ring(dc[0] + a[0], dc[1] + 0.05, dc[2] + a[2], 0.33, 24, 210, 1.2, PALE)
    body = [dc + R(v) for v in ((-0.2, 0, -0.3), (0.2, 0, -0.3), (0.2, 0, 0.3), (-0.2, 0, 0.3))]
    c.line([tuple(q) for q in project(np.array(body + body[:1]), cam)], 240, 1.8, PALE)
    for t in np.linspace(0, 1, 7):                                            # launch path (dashed) upward
        if int(t * 6) % 2 == 0:
            seg(dc + np.array((0, 0.3 + t * 1.2, 0)), dc + np.array((0, 0.45 + t * 1.2, 0)), 180, 1.2)
    seg((-2.2, 0.0, -2.0), (-2.2, 1.3, -2.0), 120, 1.0)                       # terminal marker on the back wall
    c.dot(*project(np.array([(-2.2, 1.3, -2.0)], float), cam)[0], 2.5, 240, PALE)


def graph(c, x0, y0, x1, y1, kind):
    c.rect(x0, y0, x1, y1, 200, 1.2)
    data_rows(c, x0, y0 - 9, 1, 90, 0)
    for k in range(1, 4):
        y = y0 + (y1 - y0) * k / 4; c.line([(x0, y), (x1, y)], 60, 0.6)
    for k in range(1, 6):
        x = x0 + (x1 - x0) * k / 6; c.line([(x, y0), (x, y1)], 60, 0.6)
    xs = np.linspace(x0 + 4, x1 - 4, 90); t = np.linspace(0, 1, 90)
    if kind == 0: v = 0.5 + 0.25 * np.sin(t * 7.5 + 1) + 0.08 * np.sin(t * 23)
    elif kind == 1: v = 0.45 + 0.18 * np.sin(t * 11) + 0.22 * (RNG.random(90) - 0.5) * (RNG.random(90) > 0.6)
    else: v = 0.15 + 0.6 * t ** 1.6 + 0.06 * np.sin(t * 40) + 0.04 * RNG.standard_normal(90)
    ys = y1 - 6 - np.clip(v, 0.02, 0.98) * (y1 - y0 - 12)
    c.line(list(zip(xs, ys)), 240, 1.8, PALE)
    if kind == 2:                                                             # filled area under the rising curve
        poly = [(x * S, y * S) for x, y in zip(xs, ys)] + [(xs[-1] * S, y1 * S), (xs[0] * S, y1 * S)]
        c.dc.polygon(poly, fill=CYAN); c.da.polygon(poly, fill=60)


def right_column(c):
    x0, x1 = 760, 994
    graph(c, x0, 50, x1, 168, 0)
    graph(c, x0, 196, x1, 314, 1)
    graph(c, x0, 342, x1, 470, 2)


def centre(c):
    c.rect(300, 40, 740, 478, 90, 0.8)
    data_rows(c, 312, 52, 2, 120)
    room_wireframe(c)
    for k in range(5):                                                        # status chips along the bottom
        c.rect(330 + k * 82, 452, 398 + k * 82, 466, 170, 0.8, CYAN, fill=50 if k != 2 else 120)


def build(out=OUT):
    c = Canvas()
    grid(c); frame(c); left_column(c); centre(c); right_column(c)
    col = np.asarray(c.col, np.float32); a = np.asarray(c.a, np.float32)
    ga = np.asarray(c.a.filter(ImageFilter.GaussianBlur(5 * S)), np.float32)                    # glow coverage
    gc = np.asarray(c.col.filter(ImageFilter.GaussianBlur(5 * S)), np.float32)
    cov = np.asarray(Image.fromarray((a > 0).astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(5 * S)), np.float32)
    gcol = gc / np.maximum(cov[..., None], 1) * 255                                              # mean line colour nearby
    base = 26.0                                                               # faint panel tint (alpha ~0.10)
    tint = np.array(CYAN, np.float32)
    wsum = a + 0.9 * ga + base
    C = np.clip((col * a[..., None] + gcol * 0.9 * ga[..., None] + tint * base) / wsum[..., None], 0, 255)
    A = np.clip(a + 0.9 * ga + base, 0, 255)
    img = Image.fromarray(np.dstack([C, A]).astype(np.uint8), "RGBA").resize((W, H), Image.LANCZOS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    arr = np.asarray(img).astype(int)
    print(f"SAVED {os.path.relpath(out, PROJ)}: {W} x {H} RGBA; alpha mean {arr[..., 3].mean() / 255:.2f}, "
          f"max channel min {arr[..., :3].max(2).min()} (no black), white texels (all channels > 230): "
          f"{int(((arr[..., :3] > 230).all(2)).sum())}")
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else OUT)
