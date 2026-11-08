"""Landside 'Shanshui' landscape: terraced hills (green roofs over the ground
transport centre & car parks) split by a gorge that carries roads, water
channels and the maglev; the water-curtain gateway; the sponge lake with
floating PV; lily-pad vertiports; maglev and the control tower."""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.noise import noise as pnoise

from . import params as P
from .util import MB, TAU, collection

NL = 10
DZ = 2.7


def X_k(k):
    return P.CANYON_HALF + 3.2 * k


def R_k(k):
    return 610.0 - 30.0 * k


def PHI_k(k):
    return (36.0 - 0.6 * k) * P.D2R


def r_in(phi):
    th = -math.pi / 2 + phi
    return float(P.r_eave(th)) + 7.0


def _piece_grid(k, side, ns=34, nt=44):
    """(s,t) parameterised terrace patch for level k on one side of the gorge."""
    Rk = R_k(k)
    Xk = X_k(k)
    pm = PHI_k(k)
    G = np.zeros((ns, nt, 3))
    for i in range(ns):
        s = i / (ns - 1)
        phi_guess = pm * 0.7
        for _ in range(3):
            ri = r_in(phi_guess)
            r = ri + s * (Rk - ri)
            pc = math.asin(min(0.999, Xk / r))
            phi_guess = 0.5 * (pc + pm)
        if pc >= pm:
            pc = pm - 1e-3
        for j in range(nt):
            t = j / (nt - 1)
            phi = pc + t * (pm - pc)
            ri = r_in(phi)
            rr = ri + s * (Rk - ri)
            pc2 = math.asin(min(0.999, Xk / rr))
            phi = max(phi, pc2) if j == 0 else phi
            x = side * rr * math.sin(phi)
            y = -rr * math.cos(phi)
            G[i, j] = (x, y, k * DZ)
    return G


def build_terraces(root, M):
    coll = collection('Terraces', root)
    treads, walls, rims, falls = MB(), MB(), MB(), MB()
    tread_pts = []
    for k in range(1, NL + 1):
        for side in (-1, 1):
            G = _piece_grid(k, side)
            if side < 0:
                G = G[:, ::-1]
            ns, nt = G.shape[:2]
            treads.grid_surface(G, 0)
            tread_pts.append(G)
            z_lo = (k - 1) * DZ - 0.05
            # boundary loop of the patch -> vertical walls
            loop = [G[i, 0] for i in range(ns)] + [G[ns - 1, j] for j in range(1, nt)] + \
                   [G[i, nt - 1] for i in range(ns - 2, -1, -1)] + [G[0, j] for j in range(nt - 2, 0, -1)]
            for q in range(len(loop)):
                a, b = loop[q], loop[(q + 1) % len(loop)]
                walls.add([(a[0], a[1], a[2] + 0.35), (b[0], b[1], b[2] + 0.35), (b[0], b[1], z_lo),
                           (a[0], a[1], z_lo)], [(0, 1, 2, 3)], 0)
            # water rim along the outer arc (s = 1) and the gorge edge
            gorge_edge = [G[i, 0] if side > 0 else G[i, nt - 1] for i in range(ns)]
            outer_arc = [G[ns - 1, j] for j in range(nt)]
            for edge in (outer_arc, gorge_edge):
                pts = [(p[0], p[1]) for p in edge]
                # pull the rim 0.9 m inward along the patch
                rims.ribbon(pts, 1.2, k * DZ + 0.12, 0)
            # cascades: several falls down the gorge-facing wall
            for i0 in range(3, ns - 6, 7):
                if (i0 + k) % 2:
                    continue
                seg = gorge_edge[i0:i0 + 4]
                Pf = np.zeros((len(seg), 2, 3))
                uv = np.zeros((len(seg), 2, 2))
                acc = 0.0
                for q, p in enumerate(seg):
                    if q:
                        acc += math.hypot(p[0] - seg[q - 1][0], p[1] - seg[q - 1][1])
                    out = np.array([-side * 0.5, 0.0])
                    Pf[q, 0] = (p[0] + out[0], p[1], k * DZ + 0.2)
                    Pf[q, 1] = (p[0] + out[0] * 2.4, p[1], (k - 1) * DZ + 0.1)
                    uv[q, 0] = (acc, DZ)
                    uv[q, 1] = (acc, 0)
                falls.grid_surface(Pf, 0, uv)
    treads.build('Terrace_Beds', coll, [M['planting']])
    walls.build('Terrace_Walls', coll, [M['stone_green']])
    rims.build('Terrace_Rills', coll, [M['water_clear']])
    falls.build('Terrace_Cascades', coll, [M['cascade_thin']])
    return tread_pts


def build_gorge(root, M):
    """Canyon floor between the hills + hub forecourt + water curtain."""
    coll = collection('Gorge', root)
    y_hub = -float(P.r_facade(-math.pi / 2))     # ~ -266
    y_eave = -float(P.r_eave(-math.pi / 2))      # ~ -282
    y_end = -1880.0
    road, mk, water, paths, banks = MB(), MB(), MB(), MB(), MB()

    def strip(mbx, x0, x1, ya, yb, z, mat=0):
        mbx.add([(x0, ya, z), (x1, ya, z), (x1, yb, z), (x0, yb, z)], [(0, 3, 2, 1)], mat,
                [(x0, ya), (x1, ya), (x1, yb), (x0, yb)])

    # carriageways
    for s in (-1, 1):
        x0, x1 = sorted((s * 13.0, s * 34.0))
        strip(road, x0, x1, y_end, y_hub - 40.0, 0.06)
        # lane lines (dashed)
        for lane in (1, 2, 3):
            xl = min(x0, x1) + lane * 5.25
            y = y_end
            while y < y_hub - 45:
                strip(mk, xl - 0.08, xl + 0.08, y, y + 6.0, 0.08)
                y += 15.0
        for xe in (x0 + 0.3, x1 - 0.3):
            strip(mk, xe - 0.1, xe + 0.1, y_end, y_hub - 40.0, 0.08)
        # walk + planted bank
        xa, xb = sorted((s * 34.0, s * 46.0))
        strip(paths, xa, xb, y_end, y_hub - 8.0, 0.12)
        xa, xb = sorted((s * 46.0, s * 66.0))
        strip(banks, xa, xb, -660.0, y_hub - 8.0, 0.1)
    # causeway across the lake (planted base under roads / channels)
    strip(banks, -66.0, 66.0, -1880.0, -640.0, 0.045)
    # central water channels under the maglev
    strip(water, -12.5, 12.5, -735.0, y_hub - 30.0, 0.05)
    # forecourt drop-off plaza
    strip(paths, -62.0, 62.0, y_hub - 40.0, y_hub - 10.0, 0.14)
    strip(road, -46.0, 46.0, y_hub - 40.0, y_hub - 28.0, 0.12)
    # curtain basin
    seg = 64
    Pb = np.zeros((seg, 2, 3))
    for i in range(seg):
        th = -math.pi / 2 + (-0.22 + 0.44 * i / (seg - 1))
        for j, rr in enumerate((float(P.r_eave(th)) - 3.0, float(P.r_eave(th)) + 4.0)):
            Pb[i, j] = (rr * math.cos(th), rr * math.sin(th), 0.2)
    water.grid_surface(Pb, 0)
    # moat floor between hub facade and terraces (shallow water garden)
    Pm = np.zeros((96, 2, 3))
    for i in range(96):
        th = -math.pi / 2 + (-0.70 + 1.40 * i / 95)
        r0 = float(P.r_facade(th)) + 0.5
        r1 = float(P.r_eave(th)) + 7.5
        for j, rr in enumerate((r0, r1)):
            Pm[i, j] = (rr * math.cos(th), rr * math.sin(th), 0.04)
    water.grid_surface(Pm, 0)

    road.build('Gorge_Roads', coll, [M['asphalt']])
    mk.build('Gorge_RoadMarks', coll, [M['paint_white']])
    water.build('Gorge_Water', coll, [M['water_lake']])
    paths.build('Gorge_Paths', coll, [M['path']])
    banks.build('Gorge_Banks', coll, [M['planting']])

    # ---- water curtain gateway --------------------------------------------
    cur = MB()
    gaps = [(-4.5, 4.5), (-27.0, -19.0), (19.0, 27.0)]
    nseg = 240
    cols = []
    for i in range(nseg):
        th = -math.pi / 2 + (-0.205 + 0.41 * i / (nseg - 1))
        r = float(P.r_eave(th)) + 0.6
        x = r * math.cos(th)
        if any(a < x < b for a, b in gaps):
            cols.append(None)
            continue
        cols.append((th, r))
    runs, cur_run = [], []
    for c in cols:
        if c is None:
            if len(cur_run) > 1:
                runs.append(cur_run)
            cur_run = []
        else:
            cur_run.append(c)
    if len(cur_run) > 1:
        runs.append(cur_run)
    for run in runs:
        nr = 40
        Pc = np.zeros((len(run), nr, 3))
        uv = np.zeros((len(run), nr, 2))
        for q, (th, r) in enumerate(run):
            ztop = float(P.roof_z(r - 0.6, th)) - 1.2
            for j in range(nr):
                t = j / (nr - 1)
                z = ztop * (1 - t) + 0.2 * t
                rr = r + 1.6 * t ** 1.8 + 0.25 * pnoise(Vector((th * 40, z * 0.15, 0.3)))
                Pc[q, j] = (rr * math.cos(th), rr * math.sin(th), z)
                uv[q, j] = (th * r, z)
        cur.grid_surface(Pc, 0, uv)
    cur.build('Water_Curtain', coll, [M['cascade_thin']], smooth=True)
    # pedestrian / rail bridges through the curtain gaps
    br = MB()
    for a, b in gaps:
        br.box(((a + b) / 2, y_eave - 2.0, 0.6), (b - a - 0.6, 18.0, 0.5), mat=0)
    br.build('Curtain_Bridges', coll, [M['stone']])
    return {'y_hub': y_hub}


def build_lake(root, M):
    coll = collection('Lake', root)
    cx, cy = P.LAKE_C
    ax, ay = P.LAKE_R
    n = 360
    shore = []
    for i in range(n):
        a = TAU * i / n
        wob = 1 + 0.06 * pnoise(Vector((math.cos(a) * 2.2, math.sin(a) * 2.2, 0.5))) + \
            0.03 * math.sin(5 * a + 1.3)
        shore.append((cx + ax * wob * math.cos(a), cy + ay * wob * math.sin(a)))
    mb = MB()
    verts = [(cx, cy, 0.03)] + [(x, y, 0.03) for x, y in shore]
    mb.add(verts, [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)], 0, [(v[0], v[1]) for v in verts])
    # stone rim
    rim = MB()
    rim.ribbon(shore, 5.0, 0.15, 0, close=True)
    mb.build('Lake_Water', coll, [M['water_lake']])
    rim.build('Lake_Rim', coll, [M['stone']])

    # floating PV islands (hexagonal) on east & west basins
    pv, fl = MB(), MB()
    Rh = 34.0
    dx = Rh * 1.5
    dy = Rh * math.sqrt(3)
    islands = 0
    for i in range(-14, 15):
        for j in range(-6, 7):
            x = cx + i * (dx + 6)
            y = cy + j * (dy + 6) + (0.5 * (dy + 6) if i % 2 else 0)
            if abs(x) < 330 or (i * 7 + j * 3) % 5 in (0, 3):
                continue
            if ((x - cx) / (ax * 0.88)) ** 2 + ((y - cy) / (ay * 0.82)) ** 2 > 1:
                continue
            islands += 1
            hexv = [(x, y, 0.35)] + [(x + Rh * math.cos(TAU * q / 6), y + Rh * math.sin(TAU * q / 6), 0.35)
                                     for q in range(6)]
            fl.add(hexv, [(0, 1 + q, 1 + (q + 1) % 6) for q in range(6)], 0)
            # PV rows inside the hexagon (clipped by width)
            for rrow in np.arange(-Rh * 0.8, Rh * 0.8, 3.4):
                half = (Rh * math.sqrt(3) / 2 - abs(rrow) * 0.58) * 0.95
                yy = y + rrow
                if half < 3:
                    continue
                v = [(x - half, yy, 0.6), (x + half, yy, 0.6), (x + half, yy + 2.3, 1.15), (x - half, yy + 2.3, 1.15)]
                pv.add(v, [(0, 1, 2, 3)], 0, [(0, 0), (2 * half, 0), (2 * half, 2.3), (0, 2.3)])
    fl.build('FloatPV_Floats', coll, [M['steel']])
    pv.build('FloatPV_Panels', coll, [M['pv_field']])
    return shore


def build_vertiports(root, M):
    coll = collection('Vertiports', root)
    mb = MB()
    pads = [(-215.0, -905.0, 0.0), (215.0, -905.0, 0.0), (-390.0, -935.0, 0.0), (390.0, -935.0, 0.0)]
    top = 16.0
    R = 24.0
    marks = MB()
    for (x, y, _) in pads:
        notch_dir = math.atan2(1.0, -0.25 * math.copysign(1.0, x))  # towards the north shore
        # stem (lotus stalk), flaring into the pad
        mb.path_tube([(x, y, -1.0), (x, y, top - 9), (x, y, top - 3.5), (x, y, top - 1.2)],
                     [2.6, 2.4, 6.0, 15.0], 24, 1)
        # pad: disc with a notch (access bridge slot)
        seg = 72
        verts = [(x, y, top)]
        uvs = [(0, 0)]
        ring = []
        for i in range(seg + 1):
            a = notch_dir + 0.28 + (TAU - 0.56) * i / seg
            ring.append((x + R * math.cos(a), y + R * math.sin(a)))
        for (px, py) in ring:
            verts.append((px, py, top))
            uvs.append((px - x, py - y))
        faces = [(0, 1 + i, 2 + i) for i in range(seg)]
        mb.add(verts, faces, 0, uvs)
        # rim / underside
        rv = []
        for (px, py) in ring:
            rv += [(px, py, top), (px, py, top - 1.2)]
        mb.add(rv, [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(seg)], 2)
        under = [(x, y, top - 1.2)] + [(px, py, top - 1.2) for (px, py) in ring]
        mb.add(under, [(0, 2 + i, 1 + i) for i in range(seg)], 2)
        # planted rim ring + landing circle
        ring_pts = [(x + (R - 2.2) * math.cos(notch_dir + 0.4 + (TAU - 0.8) * i / 64),
                     y + (R - 2.2) * math.sin(notch_dir + 0.4 + (TAU - 0.8) * i / 64)) for i in range(65)]
        marks.ribbon(ring_pts, 3.2, top + 0.08, 1)
        circ = [(x + 9.5 * math.cos(TAU * i / 64), y + 9.5 * math.sin(TAU * i / 64)) for i in range(64)]
        marks.ribbon(circ, 0.6, top + 0.06, 0, close=True)
        # access bridge to the shore
        bx, by = x + (R + 30) * math.cos(notch_dir), y + (R + 30) * math.sin(notch_dir)
        mx, my = x + R * 0.4 * math.cos(notch_dir), y + R * 0.4 * math.sin(notch_dir)
        L = math.hypot(bx - mx, by - my)
        mb.box(((bx + mx) / 2, (by + my) / 2, top - 0.4), (L, 4.0, 0.8), rz=notch_dir, mat=2)
    mb.build('Vertiport_Pads', coll, [M['concrete_light'], M['steel'], M['steel']])
    marks.build('Vertiport_Marks', coll, [M['paint_white'], M['planting']])
    return pads


def build_maglev(root, M):
    """Elevated over the lake, diving into a portal at the north shore; it runs
    in tunnel beneath the gorge to the B2 station under the Sky Well."""
    coll = collection('Maglev', root)
    mb = MB()
    y_portal = -760.0

    def zs(y):
        if y < -1060.0:
            return 11.0
        t = (y - (-1060.0)) / (y_portal + 1060.0)
        return 11.0 * (1.0 - t) - 1.5 * t
    ys = np.arange(-3600.0, y_portal + 1.0, 6.0)
    for x0 in (-2.6, 2.6):
        for q in range(len(ys) - 1):
            a, b = ys[q], ys[q + 1]
            za, zb = zs(a), zs(b)
            mb.box((x0, (a + b) / 2, (za + zb) / 2 - 1.0), (2.4, 6.05, 2.0), mat=0,
                   rx=math.atan2(zb - za, 6.0))
    for y in np.arange(-3600.0, -1080.0, 30.0):
        mb.cylinder((0, y, -1.0), 1.3, zs(y) - 1.0, 16, 0)
        mb.box((0, y, zs(y) - 2.4), (9.0, 2.2, 1.0), mat=0)
    # portal: sculpted mouth with a green roof
    seg = 24
    verts, faces = [], []
    for j, (yy, sc_) in enumerate(((y_portal - 26.0, 1.25), (y_portal + 0.0, 1.0), (y_portal + 30.0, 1.0))):
        for i in range(seg + 1):
            a = math.pi * i / seg
            verts.append((10.5 * sc_ * math.cos(a), yy, -2.0 + 9.0 * sc_ * math.sin(a)))
    for j in range(2):
        for i in range(seg):
            a = j * (seg + 1) + i
            faces.append((a, a + 1, a + seg + 2, a + seg + 1))
    mb.add(verts, faces, 1)
    mb.build('Maglev_Guideway', coll, [M['concrete_light'], M['stone']])
    # train: 8 cars over the lake heading north
    tr = MB()
    y0 = -1420.0
    car = 25.5
    n = 8
    x = 2.6
    sec = 20
    stations = []
    total = car * n
    for q in np.linspace(0, 1, 120):
        yy = y0 + q * total
        dn = min(yy - y0, y0 + total - yy)
        f = min(1.0, dn / 16.0)
        w = 1.85 * (0.25 + 0.75 * math.sqrt(f))
        h = 2.1 * (0.35 + 0.65 * f ** 0.7)
        stations.append((yy, w, h))
    verts, faces = [], []
    for (yy, w, h) in stations:
        zc = zs(yy) + 0.3 + h
        for i in range(sec):
            a = TAU * i / sec
            c, s_ = math.cos(a), math.sin(a)
            sx = math.copysign(abs(c) ** 0.45, c) * w
            sz = math.copysign(abs(s_) ** 0.6, s_) * h
            verts.append((x + sx, yy, zc + sz))
    for k in range(len(stations) - 1):
        for i in range(sec):
            a = k * sec + i
            b = k * sec + (i + 1) % sec
            faces.append((a, b, b + sec, a + sec))
    tr.add(verts, faces, 0)
    tr.build('Maglev_Train', coll, [bpy.data.materials['aircraft_narrow']], smooth=True)


def build_tower(root, M):
    coll = collection('Tower', root)
    mb = MB()
    x0, y0 = P.TOWER_POS
    H = P.TOWER_H
    # twisted shaft with 8 fins
    rows = 60
    sec = 32
    verts, faces = [], []
    for j in range(rows):
        t = j / (rows - 1)
        z = t * (H - 22)
        r = 8.5 - 4.2 * t + 1.2 * t ** 6
        tw = t * 0.9
        for i in range(sec):
            a = TAU * i / sec + tw
            verts.append((x0 + r * math.cos(a), y0 + r * math.sin(a), z))
    for j in range(rows - 1):
        for i in range(sec):
            a = j * sec + i
            b = j * sec + (i + 1) % sec
            faces.append((a, b, b + sec, a + sec))
    mb.add(verts, faces, 0)
    for f in range(8):
        pts, rads = [], []
        for j in range(30):
            t = j / 29
            z = t * (H - 20)
            r = 8.5 - 4.2 * t + 1.2 * t ** 6 + 1.2
            a = TAU * f / 8 + t * 0.9
            pts.append((x0 + r * math.cos(a), y0 + r * math.sin(a), z))
            rads.append(0.55)
        mb.path_tube(pts, rads, 6, 1)
    # cab: outward-leaning glazing ring
    zc0 = H - 22
    cab = []
    for j, (r, z) in enumerate(((9.5, zc0), (12.5, zc0 + 6.5), (11.0, zc0 + 7.2))):
        cab.append([(x0 + r * math.cos(TAU * i / 48), y0 + r * math.sin(TAU * i / 48), z) for i in range(48)])
    vv = [p for ring in cab for p in ring]
    ff = []
    for j in range(2):
        for i in range(48):
            a = j * 48 + i
            b = j * 48 + (i + 1) % 48
            ff.append((a, b, b + 48, a + 48))
    mb.add(vv, ff, 2)
    # bud crown: petals closing to a tip
    for pidx in range(8):
        pts, rads = [], []
        for j in range(14):
            t = j / 13
            r = 11.0 * (1 - t) ** 0.8
            z = zc0 + 7.2 + 15.0 * t
            a = TAU * pidx / 8 + 0.2 * t
            pts.append((x0 + r * math.cos(a), y0 + r * math.sin(a), z))
            rads.append(0.6 * (1 - 0.7 * t))
        mb.path_tube(pts, rads, 6, 1)
    mb.disc((x0, y0, zc0 + 7.2), 11.0, 48, 3)
    mb.cylinder((x0, y0, zc0 - 3.0), 9.4, 3.0, 48, 3)
    mb.build('Control_Tower', coll, [M['concrete_light'], M['champagne'], M['glass_dark'], M['steel']], smooth=True)


def build(M, root):
    terr = build_terraces(root, M)
    build_gorge(root, M)
    shore = build_lake(root, M)
    pads = build_vertiports(root, M)
    build_maglev(root, M)
    build_tower(root, M)
    return {'terraces': terr, 'shore': shore, 'pads': pads}
