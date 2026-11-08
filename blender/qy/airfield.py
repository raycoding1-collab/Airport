"""Airfield: terrain, four runways with ICAO-style markings, horseshoe taxiway
system, radial apron, solar fields and the night lighting point clouds."""
import math

import bpy
import numpy as np

from . import params as P
from .materials import _new
from .util import MB, TAU, collection


def _rubber_material():
    m, g = _new('rubber_deposit')
    co = g.tc.outputs['Object']
    x, y, z = g.sep(co)
    n = g.noise(g.comb(g.m('MULTIPLY', x, 0.6), g.m('MULTIPLY', y, 0.015), 0.0), 3.0, 6)
    a = g.ramp(n.outputs['Fac'], [(0.35, (0, 0, 0)), (0.7, (0.75, 0.75, 0.75))])
    g.out(g.mixs(g.sep(a)[0], g.sh('ShaderNodeBsdfTransparent', Color=(1, 1, 1)),
                 g.bsdf((0.012, 0.012, 0.013), 0.6)))
    return m


def _holed_rect(mb, r_hole, x0, x1, y0, y1, z, mat, n=256, rings=24):
    """Rectangle with a circular hole at the origin (the Sky Well shaft)."""
    P_ = np.zeros((n, rings, 3))
    for i in range(n):
        a = TAU * i / n
        c, s_ = math.cos(a), math.sin(a)
        tx = (x1 if c > 0 else x0) / c if abs(c) > 1e-9 else 1e18
        ty = (y1 if s_ > 0 else y0) / s_ if abs(s_) > 1e-9 else 1e18
        R = min(tx, ty)
        for j in range(rings):
            t = (j / (rings - 1)) ** 2.0
            r = r_hole + (R - r_hole) * t
            P_[i, j] = (r * c, r * s_, z)
    mb.grid_surface(P_, mat, uv=P_[..., :2].copy(), close_u=True)


def build_ground(root, M):
    coll = collection('Ground', root)
    mb = MB()
    S = 70000.0
    _holed_rect(mb, 58.0, -S, S, -S, S, -0.6, 0)
    mb.build('Ground_Far', coll, [M['landscape']])
    build_mountains(coll, M)
    mb = MB()
    _holed_rect(mb, 58.0, -3650.0, 3650.0, -2600.0, 3100.0, -0.08, 0)
    mb.build('Airside_Grass', coll, [M['grass']])
    return coll


def build_mountains(coll, M):
    """Layered ridges 9-34 km out (north / west / east): the 'shan' of shanshui,
    dissolved by aerial perspective into ink-wash silhouettes."""
    from mathutils.noise import ridged_multi_fractal, noise as pn
    from mathutils import Vector
    mb = MB()
    bands = [(9000.0, 13000.0, 220.0, 1.0), (15000.0, 21000.0, 520.0, 2.0), (24000.0, 34000.0, 1100.0, 3.0)]
    for (r0, r1, H, seed) in bands:
        na, nr = 420, 34
        a0, a1 = 0.0, TAU * (1 - 1.0 / 420)              # full ring
        Pg = np.zeros((na, nr, 3))
        for i in range(na):
            a = a0 + (a1 - a0) * i / (na - 1)
            for j in range(nr):
                t = j / (nr - 1)
                r = r0 + (r1 - r0) * t
                x, y = r * math.sin(a), r * math.cos(a)
                q = Vector((x / 5200.0, y / 5200.0, seed))
                h = ridged_multi_fractal(q, 0.9, 2.1, 6, 0.9, 2.0)
                env = math.sin(math.pi * t) ** 0.7
                gap = 0.55 + 0.45 * pn(Vector((math.sin(a) * 2.5, math.cos(a) * 2.5, seed * 3)))
                Pg[i, j] = (x, y, max(0.0, H * 0.55 * h * env * gap) - 1.0)
        mb.grid_surface(Pg, 0, close_u=True)
    mb.build('Mountains', coll, [M['mountain']], smooth=True)


def apron_mask_image(res=3072, half=1010.0):
    """Rasterise the apron footprint (stands + taxilanes + hub forecourt) into a
    smooth mask texture, so the concrete/grass edge is clean at any distance."""
    from scipy.ndimage import gaussian_filter
    xs = np.linspace(-half, half, res, dtype=np.float32)
    X, Y = np.meshgrid(xs, xs)
    R = np.hypot(X, Y)
    TH = np.degrees(np.arctan2(Y, X))
    m = R < 380.0
    for d in P.PIER_DIRS:
        a = d * P.D2R
        t = X * math.cos(a) + Y * math.sin(a) - P.PIER_START
        sl = -X * math.sin(a) + Y * math.cos(a)
        hw = P.pier_hw(np.clip(t, 0, P.PIER_LEN))
        m |= (t > -40) & (t < P.PIER_LEN + 95) & (np.abs(sl) < hw + 102.0)
        if d != P.PIER_DIRS[-1]:
            b = a + 30.0 * P.D2R
            sb = -X * math.sin(b) + Y * math.cos(b)
            m |= (np.abs(sb) < 42.0) & (X * math.cos(b) + Y * math.sin(b) > 0)
    m &= R < P.APRON_R + 22.0
    m &= ~((TH > -128.0) & (TH < -52.0) & (R > 230.0))
    mf = gaussian_filter(m.astype(np.float32), 1.2)
    im = bpy.data.images.new('apron_mask', res, res, alpha=True, float_buffer=False)
    px = np.dstack([mf, mf, mf, np.ones_like(mf)])
    im.pixels.foreach_set(px.reshape(-1).astype(np.float32))
    im.pack()
    im.colorspace_settings.name = 'Non-Color'
    return im, half


def _apron_material(M):
    from .materials import _concrete_shader, _grass_shader
    im, half = apron_mask_image()
    m, g = _new('apron_mixed')
    co = g.tc.outputs['Object']
    x, y, z = g.sep(co)
    uv = g.comb(g.m('ADD', g.m('DIVIDE', x, 2 * half), 0.5), g.m('ADD', g.m('DIVIDE', y, 2 * half), 0.5), 0.0)
    tex = g.node('ShaderNodeTexImage', image=im, interpolation='Cubic', extension='EXTEND')
    g.link(uv, tex.inputs['Vector'])
    g.out(g.mixs(g.sep(tex.outputs['Color'])[0], _grass_shader(g), _concrete_shader(g)))
    return m


def build_apron(root, M):
    coll = collection('Apron', root)
    mb = MB()
    nth, nr = 720, 60
    Pg = np.zeros((nth, nr, 3))
    for i in range(nth):
        th = i / nth * TAU
        for j in range(nr):
            r = 62.0 + (P.APRON_R + 40.0 - 62.0) * (j / (nr - 1))
            Pg[i, j] = (r * math.cos(th), r * math.sin(th), 0.0)
    mb.grid_surface(Pg, 0, close_u=True)
    mb.build('Apron_Concrete', coll, [_apron_material(M)])

    # apron markings: taxilanes on pier bisectors, service roads along piers
    mk = MB()
    for d in P.PIER_DIRS[:-1]:
        b = (d + 30.0) * P.D2R
        pts = [(r * math.cos(b), r * math.sin(b)) for r in np.linspace(250, P.APRON_R + 40, 40)]
        mk.ribbon(pts, 0.45, 0.03, 1)
    for d in P.PIER_DIRS:
        a = d * P.D2R
        ca, sa = math.cos(a), math.sin(a)
        for side in (-1, 1):
            # stand-clearance line (red) and service road edges (white)
            for off, w, mat in ((P.PIER_HW0 + 82.0, 0.35, 2), (P.PIER_HW0 + 88.0, 0.25, 0), (P.PIER_HW0 + 96.0, 0.25, 0)):
                pts = []
                for t in np.linspace(20, P.PIER_LEN - 20, 60):
                    hw = float(P.pier_hw(t))
                    o = hw + (off - P.PIER_HW0)
                    r = P.PIER_START + t
                    pts.append((r * ca - side * o * sa, r * sa + side * o * ca))
                mk.ribbon(pts, w, 0.03, mat)
    mk.build('Apron_Markings', coll, [M['paint_white'], M['paint_yellow'], M['paint_red']])
    return coll


def _runway(mb, mk, rub, x, y0, y1, w):
    L = y1 - y0
    # pavement + shoulders
    mb.add([(x - w / 2, y0, 0.02), (x + w / 2, y0, 0.02), (x + w / 2, y1, 0.02), (x - w / 2, y1, 0.02)],
           [(0, 1, 2, 3)], 0)
    for s in (-1, 1):
        xa, xb = x + s * w / 2, x + s * (w / 2 + 7.5)
        mb.add([(xa, y0, 0.015), (xb, y0, 0.015), (xb, y1, 0.015), (xa, y1, 0.015)],
               [(0, 1, 2, 3) if s > 0 else (0, 3, 2, 1)], 1)
    z = 0.035

    def rect(cx, cy, sx, sy, mat=0):
        mk.add([(cx - sx / 2, cy - sy / 2, z), (cx + sx / 2, cy - sy / 2, z), (cx + sx / 2, cy + sy / 2, z),
                (cx - sx / 2, cy + sy / 2, z)], [(0, 1, 2, 3)], mat)
    # edge lines
    for s in (-1, 1):
        rect(x + s * (w / 2 - 0.6), (y0 + y1) / 2, 0.9, L)
    # centreline 30 m stripe / 20 m gap
    yy = y0 + 70.0
    while yy < y1 - 70.0:
        rect(x, yy + 15, 0.9, 30)
        yy += 50.0
    for end, sgn in ((y0, 1), (y1, -1)):
        # threshold piano keys (16 stripes)
        for k in range(8):
            off = 3.0 + k * 3.6
            for s in (-1, 1):
                rect(x + s * off, end + sgn * 21.0, 1.8, 30.0)
        # aiming point
        for s in (-1, 1):
            rect(x + s * 13.5, end + sgn * 430.0, 10.0, 60.0)
        # touchdown zone bars
        for k, n_bars in ((150, 3), (300, 3), (600, 2), (750, 2), (900, 1)):
            for s in (-1, 1):
                for b in range(n_bars):
                    rect(x + s * (9.0 + b * 3.0), end + sgn * (k + 11), 1.8, 22.5)
        # rubber deposits
        rub.add([(x - 16, end + sgn * 120, 0.03), (x + 16, end + sgn * 120, 0.03),
                 (x + 16, end + sgn * 1100, 0.03), (x - 16, end + sgn * 1100, 0.03)],
                [(0, 1, 2, 3) if sgn > 0 else (0, 3, 2, 1)], 0)


def build_runways(root, M):
    coll = collection('Runways', root)
    mb, mk, rub = MB(), MB(), MB()
    lights = {'edge': [], 'centre': [], 'green': [], 'red': [], 'approach': []}
    for (x, y0, y1, w) in P.RUNWAYS:
        _runway(mb, mk, rub, x, y0, y1, w)
        for yy in np.arange(y0, y1 + 1, 60.0):
            for s in (-1, 1):
                lights['edge'].append((x + s * (w / 2 + 1.5), yy, 0.4))
        for yy in np.arange(y0 + 15, y1, 15.0):
            lights['centre'].append((x + 0.0, yy, 0.12))
        for k in range(-14, 15):
            lights['green'].append((x + k * 2.2, y0 - 2.0, 0.3))
            lights['red'].append((x + k * 2.2, y1 + 2.0, 0.3))
        for end, sgn in ((y0, -1), (y1, 1)):
            for d in np.arange(30, 900, 30.0):
                lights['approach'].append((x, end + sgn * d, 0.8))
                if int(d) % 150 == 0:
                    for k in range(-6, 7):
                        lights['approach'].append((x + k * 2.5, end + sgn * d, 0.8))
    mb.build('Runway_Pavement', coll, [M['asphalt'], M['concrete']])
    mk.build('Runway_Markings', coll, [M['paint_white']])
    rub.build('Runway_Rubber', coll, [_rubber_material()])
    return lights


def _taxi(mb, mk, pts, w=24.0):
    mb.ribbon(pts, w, 0.012, 0)
    mk.ribbon(pts, 0.35, 0.03, 0)


def build_taxiways(root, M):
    coll = collection('Taxiways', root)
    mb, mk = MB(), MB()
    blue, green = [], []

    def add(pts, w=24.0):
        _taxi(mb, mk, pts, w)
        pts = np.asarray(pts)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        for d in np.arange(0, s[-1], 30.0):
            i = min(np.searchsorted(s, d) - 1, len(pts) - 2)
            i = max(i, 0)
            t = (d - s[i]) / max(seg[i], 1e-6)
            p = pts[i] + (pts[i + 1] - pts[i]) * t
            green.append((p[0], p[1], 0.1))
            if int(d) % 60 == 0:
                dirv = (pts[i + 1] - pts[i]) / max(seg[i], 1e-6)
                nrm = np.array([-dirv[1], dirv[0]])
                for sgn in (-1, 1):
                    q = p + nrm * sgn * (w / 2 + 1.0)
                    blue.append((q[0], q[1], 0.35))

    for R in P.RING_TAXI_R:
        a = np.linspace(-58.0, 238.0, 300) * P.D2R
        add([(R * math.cos(t), R * math.sin(t)) for t in a])
    # parallel taxiways
    for xp in (-2520.0, -1950.0, -1380.0, 1380.0, 1950.0, 2520.0):
        add([(xp, -1650.0), (xp, 2250.0)])
    # cross connectors (ring -> parallels), and two full-width northern links
    for yc in (-700.0, -350.0, 200.0, 750.0):
        xr = math.sqrt(P.RING_TAXI_R[1] ** 2 - yc ** 2)
        for sgn in (-1, 1):
            add([(sgn * xr, yc), (sgn * 2520.0, yc)])
    for yc in (1300.0, 1850.0):
        add([(-2520.0, yc), (2520.0, yc)])
    add([(0.0, P.RING_TAXI_R[1]), (0.0, 1300.0)])
    # rapid exits (angled)
    for (x, y0, y1, w) in P.RUNWAYS:
        sgn = -1 if x > 0 else 1
        for yy in (y0 + 1700.0, y0 + 2300.0):
            xt = x + sgn * 180.0
            add([(x, yy), (xt, yy + 420.0)], 22.0)
    mb.build('Taxiway_Pavement', coll, [M['asphalt']])
    mk.build('Taxiway_Markings', coll, [M['paint_yellow']])
    return blue, green


def build_solar_fields(root, M):
    coll = collection('Solar_Fields', root)
    mb = MB()
    tilt = 22.0 * P.D2R
    depth = 4.6
    for x0, x1 in ((2760.0, 3560.0), (-3560.0, -2760.0)):
        for blk in range(6):
            yb0 = -1250.0 + blk * 520.0
            for row in range(int(480 / 11.0)):
                y = yb0 + row * 11.0
                z0 = 0.9
                y_hi = y + depth * math.cos(tilt)
                z1 = z0 + depth * math.sin(tilt)
                # panel faces south (-Y): low edge at south
                v = [(x0, y, z0), (x1, y, z0), (x1, y_hi, z1), (x0, y_hi, z1)]
                L = x1 - x0
                mb.add(v, [(0, 1, 2, 3)], 0, [(0, 0), (L, 0), (L, depth), (0, depth)])
    mb.build('PV_Fields', coll, [M['pv_field']])


def build_point_lights(root, M, groups):
    """Night lights as instanced emissive spheres (geometry nodes)."""
    coll = collection('Night_Airfield', root)
    lib = bpy.data.collections.get('LIB_lights') or bpy.data.collections.new('LIB_lights')
    out = []
    for name, (pts, mat, rad) in groups.items():
        if not pts:
            continue
        sph = bpy.data.objects.get('lamp_' + name)
        if sph is None:
            me = bpy.data.meshes.new('lamp_' + name)
            import bmesh
            bm = bmesh.new()
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=rad)
            bm.to_mesh(me)
            bm.free()
            me.materials.append(M[mat])
            sph = bpy.data.objects.new('lamp_' + name, me)
            lib.objects.link(sph)
        me = bpy.data.meshes.new('pts_' + name)
        me.from_pydata([tuple(p) for p in pts], [], [])
        ob = bpy.data.objects.new('Lights_' + name, me)
        coll.objects.link(ob)
        mod = ob.modifiers.new('inst', 'NODES')
        mod.node_group = _instance_object_group(sph)
        out.append(ob)
    return coll


def _instance_object_group(obj):
    name = 'GN_inst_' + obj.name
    ng = bpy.data.node_groups.get(name)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi = ng.nodes.new('NodeGroupInput')
    go = ng.nodes.new('NodeGroupOutput')
    oi = ng.nodes.new('GeometryNodeObjectInfo')
    oi.inputs['Object'].default_value = obj
    iop = ng.nodes.new('GeometryNodeInstanceOnPoints')
    ng.links.new(gi.outputs[0], iop.inputs['Points'])
    ng.links.new(oi.outputs['Geometry'], iop.inputs['Instance'])
    ng.links.new(iop.outputs[0], go.inputs[0])
    return ng


def build(M, root):
    build_ground(root, M)
    build_apron(root, M)
    rl = build_runways(root, M)
    blue, green = build_taxiways(root, M)
    build_solar_fields(root, M)
    groups = {
        'rwy_edge': (rl['edge'], 'em_runway', 1.0),
        'rwy_centre': (rl['centre'], 'em_runway', 0.7),
        'rwy_green': (rl['green'], 'em_taxi_green', 0.8),
        'rwy_red': (rl['red'], 'em_red', 0.8),
        'approach': (rl['approach'], 'em_runway', 1.1),
        'taxi_blue': (blue, 'em_taxi_blue', 0.55),
        'taxi_green': (green, 'em_taxi_green', 0.6),
    }
    build_point_lights(root, M, groups)
