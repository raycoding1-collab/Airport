"""Non-branded twin-engine airliners (wide-body and narrow-body).

Fuselage is lofted from a nose-ogive / barrel / up-swept tail-cone profile,
wings are cranked, swept and built from NACA 4-digit sections, with winglets,
under-wing turbofan nacelles, pylons and landing gear.  Object origin = ground
point under the nose gear; local +X = forward; fuselage centreline at Z = zc.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from .util import MB, TAU

TYPES = {
    #            L     R    span  zc   nac_r nac_L eng_y  sweep
    'wide':   (66.0, 3.0, 64.0, 6.1, 1.75, 6.8, 0.33, 31.0),
    'narrow': (39.0, 2.0, 35.8, 4.0, 1.10, 4.6, 0.34, 26.0),
}


def naca(t_c, camber=0.02, n=14):
    xs = (1 - np.cos(np.linspace(0, math.pi, n))) / 2
    yt = 5 * t_c * (0.2969 * np.sqrt(xs) - 0.1260 * xs - 0.3516 * xs ** 2 + 0.2843 * xs ** 3 - 0.1036 * xs ** 4)
    yc = np.where(xs < 0.4, camber / 0.16 * (0.8 * xs - xs ** 2), camber / 0.36 * (0.2 + 0.8 * xs - xs ** 2))
    up = list(zip(xs, yc + yt))
    lo = list(zip(xs[::-1], (yc - yt)[::-1]))
    return up + lo[1:-1]      # closed loop, LE -> TE upper -> TE lower -> LE


def loft_sections(mb, sections, mat, cap=True):
    """sections: list of (le_point Vector, chord, t/c, twist_up_vector) -> loft."""
    loops = []
    for (le, chord, tc, dirx, dirz) in sections:
        prof = naca(tc)
        loops.append([tuple(le + dirx * (px * chord) + dirz * (py * chord)) for px, py in prof])
    m = len(loops[0])
    verts = [v for loop in loops for v in loop]
    faces = []
    for k in range(len(loops) - 1):
        for i in range(m):
            a = k * m + i
            b = k * m + (i + 1) % m
            faces.append((a, b, b + m, a + m))
    if cap:
        faces.append(tuple(range(m))[::-1])
        faces.append(tuple(range((len(loops) - 1) * m, len(loops) * m)))
    mb.add(verts, faces, mat)


def make_airliner(kind, name=None):
    L, R, span, zc, nr, nL, ey, sweep = TYPES[kind]
    mb = MB()
    # ---------------- fuselage ----------------
    seg = 32
    stations = np.concatenate([np.linspace(0, 0.12, 14) ** 1.0, np.linspace(0.13, 0.70, 10),
                               np.linspace(0.72, 1.0, 14)])
    rings = []
    for xn in stations:
        if xn <= 0.12:
            t = xn / 0.12
            r = R * (1 - (1 - t) ** 2.2) ** 0.5
            zo = -0.22 * R * (1 - t) ** 2
        elif xn <= 0.70:
            r, zo = R, 0.0
        else:
            t = (xn - 0.70) / 0.30
            r = R * (1 - 0.86 * t ** 1.25)
            zo = 0.62 * R * t ** 1.5
        rings.append((-xn * L, max(r, 0.02), zo))
    verts, faces = [], []
    for (x, r, zo) in rings:
        for i in range(seg):
            a = TAU * i / seg
            verts.append((x, r * math.cos(a), zo + 1.04 * r * math.sin(a)))
    nring = len(rings)
    for k in range(nring - 1):
        for i in range(seg):
            a = k * seg + i
            b = k * seg + (i + 1) % seg
            faces.append((a, a + seg, b + seg, b))
    tip = len(verts)
    verts.append((0.25, 0.0, -0.22 * R))
    for i in range(seg):
        faces.append((tip, i, (i + 1) % seg))
    faces.append(tuple(range((nring - 1) * seg, nring * seg)))
    mb.add(verts, faces, 0)

    # ---------------- wings ----------------
    b2 = span / 2
    y0 = R * 0.85
    yk = 0.36 * b2
    cr = 0.20 * L
    ct = 0.045 * L
    tan_s = math.tan(math.radians(sweep))
    x_le0 = -0.36 * L
    zw = -0.5 * R
    dih = math.tan(math.radians(5.5))
    te_x = x_le0 - cr
    ck = (x_le0 - (yk - y0) * tan_s) - te_x
    for side in (-1, 1):
        secs = []
        for (yy, ch, tc) in ((y0, cr, 0.14), (yk, ck, 0.115), (b2 * 0.985, ct, 0.10)):
            le = Vector((x_le0 - (yy - y0) * tan_s, side * yy, zw + (yy - y0) * dih))
            secs.append((le, ch, tc, Vector((-1, 0, 0)), Vector((0, 0, 1))))
        # winglet: rotate the section plane to vertical
        le_t = secs[-1][0]
        wl_h = 0.075 * span
        secs.append((le_t + Vector((-0.6, side * 0.35, 0.25)), ct * 0.9, 0.09, Vector((-1, 0, 0)), Vector((0, -side * 0.9, 0.3)).normalized()))
        secs.append((le_t + Vector((-ct * 0.9, side * 0.75, wl_h)), ct * 0.45, 0.08, Vector((-1, 0, 0)), Vector((0, -side, 0)).normalized()))
        loft_sections(mb, secs, 1)
        # ---------------- engines ----------------
        ye = ey * b2
        xl = x_le0 - (ye - y0) * tan_s
        zl = zw + (ye - y0) * dih
        c = Vector((xl + 0.45 * nL, side * ye, zl - nr * 0.92))
        prof = [(0.0, 0.92), (0.05, 1.0), (0.35, 1.0), (0.75, 0.86), (1.0, 0.55)]
        pts = [c + Vector((-p * nL, 0, 0)) for p, _ in prof]
        rads = [nr * q for _, q in prof]
        mb.path_tube(pts, rads, 28, 2, cap=False)
        # fan face
        verts_d = []
        for i in range(28):
            a = TAU * i / 28
            verts_d.append(tuple(c + Vector((-0.35, nr * 0.9 * math.cos(a), nr * 0.9 * math.sin(a)))))
        mb.add(verts_d + [tuple(c + Vector((-0.7, 0, 0)))], [(28, (i + 1) % 28, i) for i in range(28)], 3)
        # exhaust cone
        mb.tube(c + Vector((-nL, 0, 0)), c + Vector((-nL - 1.4 * nr, 0, 0)), nr * 0.42, 0.05, 16, 2)
        # pylon
        mb.box(tuple(c + Vector((-0.55 * nL, 0, nr * 0.95))), (0.75 * nL, 0.35 * nr, 0.9 * nr), mat=1)

    # ---------------- empennage ----------------
    ht_root = Vector((-0.865 * L, 0, 0.28 * R))
    for side in (-1, 1):
        hb = 0.17 * span
        secs = [(ht_root + Vector((0, side * 0.3 * R, 0)), 0.10 * L, 0.11, Vector((-1, 0, 0)), Vector((0, 0, 1))),
                (ht_root + Vector((-hb * math.tan(math.radians(sweep + 5)), side * hb, hb * 0.1)), 0.035 * L, 0.09,
                 Vector((-1, 0, 0)), Vector((0, 0, 1)))]
        loft_sections(mb, secs, 0)
    vt_root = Vector((-0.80 * L, 0, 0.75 * R))
    vh = 0.17 * L if kind == 'wide' else 0.20 * L
    secs = [(vt_root, 0.16 * L, 0.11, Vector((-1, 0, 0)), Vector((0, 1, 0))),
            (vt_root + Vector((-vh * math.tan(math.radians(40)), 0, vh)), 0.065 * L, 0.10, Vector((-1, 0, 0)),
             Vector((0, 1, 0)))]
    loft_sections(mb, secs, 0)

    # ---------------- landing gear ----------------
    wr = 0.62 if kind == 'wide' else 0.5
    gz = -zc
    def wheel(cx, cy):
        verts, fcs = [], []
        n = 16
        for s in (-0.22, 0.22):
            for i in range(n):
                a = TAU * i / n
                verts.append((cx + wr * math.cos(a), cy + s, gz + wr + wr * math.sin(a)))
        for i in range(n):
            j = (i + 1) % n
            fcs.append((i, j, n + j, n + i))
        fcs.append(tuple(range(n))[::-1])
        fcs.append(tuple(range(n, 2 * n)))
        mb.add(verts, fcs, 3)
    nx = -0.085 * L
    mb.tube((nx, 0, gz + wr), (nx, 0, -R * 0.8), 0.14, 0.14, 8, 2)
    wheel(nx, -0.3)
    wheel(nx, 0.3)
    mx = x_le0 - 0.6 * cr
    for side in (-1, 1):
        my = side * (R * 1.55 if kind == 'wide' else R * 1.45)
        mb.tube((mx, my, gz + wr), (mx, my, zw), 0.22, 0.22, 8, 2)
        if kind == 'wide':
            for dx in (-0.8, 0.8):
                for dy in (-0.45, 0.45):
                    wheel(mx + dx, my + dy)
        else:
            for dy in (-0.35, 0.35):
                wheel(mx, my + dy)

    # ---------------- assemble ----------------
    from . import materials as _m  # noqa
    coll = bpy.data.collections.get('LIB_aircraft') or bpy.data.collections.new('LIB_aircraft')
    mats = [bpy.data.materials['aircraft_' + kind], bpy.data.materials['aircraft_wing'],
            bpy.data.materials['engine_metal'], bpy.data.materials['rubber']]
    ob = mb.build(name or ('AC_' + kind), coll, mats, smooth=True)
    # shift so origin is on the ground under the fuselage axis
    me = ob.data
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    co[:, 2] += zc
    me.vertices.foreach_set('co', co.reshape(-1))
    me.update()
    return ob


def place(proto, loc, heading, coll, name=None):
    ob = bpy.data.objects.new(name or proto.name + '_inst', proto.data)
    ob.location = loc
    ob.rotation_euler = (0, 0, heading)
    coll.objects.link(ob)
    return ob
