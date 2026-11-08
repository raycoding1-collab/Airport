"""Five leaf-shaped piers: PV roofs with herring-bone skylight 'veins',
glass facades, gate lounges, apron-drive boarding bridges and parked aircraft."""
import math

import bpy
import numpy as np
from mathutils import Vector

from . import aircraft
from . import params as P
from .util import MB, TAU, collection


def frame(theta_deg):
    a = theta_deg * P.D2R
    d = np.array([math.cos(a), math.sin(a)])
    n = np.array([-math.sin(a), math.cos(a)])
    return d, n


def w2(d, n, t, s):
    p = (P.PIER_START + t) * d + s * n
    return float(p[0]), float(p[1])


def roof_z(t, s, hw):
    ridge = P.PIER_RIDGE0 + (P.PIER_RIDGE1 - P.PIER_RIDGE0) * min(max(t, 0) / P.PIER_LEN, 1)
    W = hw + 4.5
    q = min(abs(s) / max(W, 1e-3), 1.0)
    return P.PIER_EAVE + (ridge - P.PIER_EAVE) * (1 - q ** 2) ** 0.75


def _sweep_section(mb, a, b, w, h, n=20, glass_mat=2, body_mat=0, cap=True):
    """Superellipse tube from a to b (boarding-bridge tunnel) with a glazed band."""
    a = Vector(a)
    b = Vector(b)
    d = (b - a)
    L = d.length
    t = d / L
    side = t.cross(Vector((0, 0, 1))).normalized()
    up = side.cross(t).normalized()
    sec = []
    for i in range(n):
        ang = TAU * i / n
        c, s_ = math.cos(ang), math.sin(ang)
        sx = math.copysign(abs(c) ** 0.35, c) * w / 2
        sy = math.copysign(abs(s_) ** 0.35, s_) * h / 2
        sec.append((sx, sy, ang))
    verts = []
    for p in (a, b):
        for (sx, sy, _) in sec:
            verts.append(tuple(p + side * sx + up * sy))
    faces, mats = [], []
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
        mid = math.sin(TAU * (i + 0.5) / n)
        mats.append(glass_mat if 0.05 < mid < 0.75 and abs(math.cos(TAU * (i + 0.5) / n)) > 0.5 else body_mat)
    if cap:
        faces.append(tuple(range(n))[::-1])
        mats.append(body_mat)
        faces.append(tuple(range(n, 2 * n)))
        mats.append(body_mat)
    mb.add(verts, faces, mats)


def build_pier(k, theta, M, coll, ac_coll, protos, rs):
    d, n = frame(theta)
    roof, fac, fl, br, mk = MB(), MB(), MB(), MB(), MB()
    nt, ns = 150, 26
    ts = np.linspace(-14.0, P.PIER_LEN + 3.0, nt)
    Pr = np.zeros((nt, ns, 3))
    uv = np.zeros((nt, ns, 2))
    for i, t in enumerate(ts):
        hw = float(P.pier_hw(min(t, P.PIER_LEN)))
        W = max(hw + 4.5, 0.6)
        for j in range(ns):
            s = -W + 2 * W * j / (ns - 1)
            x, y = w2(d, n, t, s)
            Pr[i, j] = (x, y, roof_z(t, s, hw))
            uv[i, j] = (t, s)
    roof.grid_surface(Pr, 0, uv)
    # fascia along both long edges
    for j in (0, ns - 1):
        for i in range(nt - 1):
            a, b = Pr[i, j], Pr[i + 1, j]
            roof.add([tuple(a), tuple(b), (b[0], b[1], b[2] - 1.1), (a[0], a[1], a[2] - 1.1)],
                     [(0, 1, 2, 3)], 1)
    roof.build(f'Pier{k}_Roof', coll, [M['pv_pier'], M['champagne']])

    # facade loop
    ring = []
    tt = np.linspace(-6.0, P.PIER_LEN, 140)
    for t in tt:
        ring.append((t, -float(P.pier_hw(t))))
    for t in tt[::-1]:
        ring.append((t, float(P.pier_hw(t))))
    verts, uvs, faces = [], [], []
    acc = 0.0
    prev = None
    for (t, s) in ring:
        x, y = w2(d, n, t, s)
        if prev:
            acc += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
        zt = roof_z(t, s, float(P.pier_hw(t))) - 0.4
        verts += [(x, y, 0.0), (x, y, zt)]
        uvs += [(acc, 0.0), (acc, zt)]
    for i in range(len(ring) - 1):
        faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    fac.add(verts, faces, 0, uvs)
    fac.build(f'Pier{k}_Facade', coll, [M['facade']])

    # gate-lounge floor (top) + soffit
    Pf = np.zeros((nt, 8, 3))
    for i, t in enumerate(ts):
        hw = max(float(P.pier_hw(min(max(t, -6), P.PIER_LEN))) - 0.4, 0.1)
        for j in range(8):
            s = -hw + 2 * hw * j / 7
            x, y = w2(d, n, t, s)
            Pf[i, j] = (x, y, P.Z_PIER)
    fl.grid_surface(Pf, 0)
    Pb = Pf.copy()
    Pb[..., 2] = P.Z_PIER - 0.8
    fl.grid_surface(Pb[:, ::-1], 1)
    fl.build(f'Pier{k}_Floor', coll, [M['terrazzo'], M['soffit']])

    # gates
    gates = []
    for side in (-1, 1):
        for g in range(P.GATES_PER_SIDE):
            t = P.GATE_T0 + g * P.GATE_PITCH
            gates.append((t, side))
    gates.append((P.PIER_LEN + 0.0, 0))
    for gi, (t, side) in enumerate(gates):
        if side == 0:
            # tip gate: aircraft facing the pier tip
            nose = (P.PIER_START + P.PIER_LEN + 12.0) * d
            fwd = -d
            hw = 0.0
        else:
            hw = float(P.pier_hw(t))
            nose = (P.PIER_START + t) * d + side * (hw + 7.0) * n
            fwd = -side * n
        kind = 'wide' if (gi % 3 != 1 and t < 380) or side == 0 else 'narrow'
        if rs.rand() < 0.12:
            continue
        L, R, span, zc = aircraft.TYPES[kind][:4]
        heading = math.atan2(fwd[1], fwd[0])
        aircraft.place(protos[kind], (float(nose[0]), float(nose[1]), 0.0), heading, ac_coll,
                       f'AC_{k}_{gi}')
        # stand markings: lead-in line, stop bar, stand envelope corners
        a0 = nose + fwd * 1.0
        a1 = nose - fwd * 118.0
        mk.ribbon([(float(a0[0]), float(a0[1])), (float(a1[0]), float(a1[1]))], 0.3, 0.03, 0)
        lft = np.array([-fwd[1], fwd[0]])
        sb0, sb1 = nose + lft * 3.0 + fwd * 2.0, nose - lft * 3.0 + fwd * 2.0
        mk.ribbon([(float(sb0[0]), float(sb0[1])), (float(sb1[0]), float(sb1[1]))], 0.5, 0.03, 0)
        for sgn in (-1, 1):
            e0 = nose + lft * sgn * (span / 2 + 4.0) + fwd * 3.0
            e1 = e0 - fwd * (L + 8.0)
            mk.ribbon([(float(e0[0]), float(e0[1])), (float(e1[0]), float(e1[1]))], 0.25, 0.03, 1)
        left = np.array([-fwd[1], fwd[0]])
        door = nose - fwd * (0.13 * L) + left * (R + 0.2)
        door_z = zc + 0.35 * R - 1.0
        # boarding bridge
        if side == 0:
            rot = (P.PIER_START + P.PIER_LEN - 4.0) * d + left * 14.0
        else:
            rot = (P.PIER_START + t) * d + side * (hw + 2.5) * n + left * 12.0
        rz = P.Z_PIER + 0.3
        br.cylinder((float(rot[0]), float(rot[1]), rz - 0.2), 2.6, 3.6, 20, 0)
        br.cylinder((float(rot[0]), float(rot[1]), 0.0), 0.6, rz - 0.2, 10, 1)
        a = np.array([rot[0], rot[1], rz + 1.6])
        b = np.array([door[0], door[1], door_z + 1.5]) + np.append(left * 2.2, 0.0)
        v = b - a
        # two telescoping tunnel sections + cab, glazed band on both sides
        m1 = a + v * 0.52
        _sweep_section(br, a, m1 + v * 0.02, 3.6, 3.2)
        _sweep_section(br, m1 - v * 0.02, b, 3.3, 2.95)
        cab_end = b + np.append(-left * 2.4, 0.0)
        _sweep_section(br, b - v / max(np.linalg.norm(v), 1e-3) * 0.6, cab_end, 3.9, 3.3)
        # bellows canopy at the door
        _sweep_section(br, cab_end, cab_end + np.append(-left * 0.9, 0.0), 3.0, 2.6, glass_mat=1, body_mat=1)
        # drive column with wheel bogie
        leg = a + v * 0.74
        br.tube((leg[0], leg[1], 1.1), (leg[0], leg[1], leg[2] - 1.6), 0.32, 0.32, 12, 1)
        br.tube((leg[0] - 0.9 * v[1] / np.linalg.norm(v), leg[1] + 0.9 * v[0] / np.linalg.norm(v), 0.55),
                (leg[0] + 0.9 * v[1] / np.linalg.norm(v), leg[1] - 0.9 * v[0] / np.linalg.norm(v), 0.55),
                0.55, 0.55, 16, 3)
    br.build(f'Pier{k}_Bridges', coll, [M['aluminium'], M['metal_dark'], M['glass_dark'], M['rubber']], smooth=True)
    mk.build(f'Pier{k}_StandMarks', coll, [M['paint_yellow'], M['paint_red']])


def build_night(root, M):
    coll = collection('Night_Piers', root)
    for k, th in enumerate(P.PIER_DIRS):
        d, n = frame(th)
        for t in np.arange(20, P.PIER_LEN - 30, 45.0):
            x, y = w2(d, n, t, 0.0)
            ld = bpy.data.lights.new(f'pier_{k}_{int(t)}', 'AREA')
            ld.shape = 'RECTANGLE'
            ld.size = 30.0
            ld.size_y = 14.0
            ld.energy = 2.2e4
            ld.color = (1.0, 0.8, 0.6)
            ob = bpy.data.objects.new(ld.name, ld)
            ob.location = (x, y, 13.0)
            ob.rotation_euler = (0, 0, th * P.D2R)
            coll.objects.link(ob)
            # apron flood-light masts
            for side in (-1, 1):
                hw = float(P.pier_hw(t))
                if int(t) % 90 != 20:
                    continue
                px, py = w2(d, n, t + 20, side * (hw + 84.0))
                ld2 = bpy.data.lights.new(f'mast_{k}_{int(t)}_{side}', 'SPOT')
                ld2.energy = 1.6e5
                ld2.spot_size = math.radians(150)
                ld2.spot_blend = 1.0
                ld2.color = (1.0, 0.86, 0.7)
                ob2 = bpy.data.objects.new(ld2.name, ld2)
                ob2.location = (px, py, 32.0)
                coll.objects.link(ob2)


def build(M, root):
    coll = collection('Piers', root)
    ac_coll = collection('Aircraft', root)
    protos = {'wide': aircraft.make_airliner('wide'), 'narrow': aircraft.make_airliner('narrow')}
    rs = np.random.RandomState(7)
    for k, th in enumerate(P.PIER_DIRS):
        build_pier(k, th, M, coll, ac_coll, protos, rs)
    build_night(root, M)
    return protos
