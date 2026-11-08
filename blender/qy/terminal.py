"""The Lotus hub: inverted-lotus spiral gridshell, oculus, Sky Well canyon,
vortex waterfall, banyan tree-columns, Lotus Hall floor and night lighting."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import params as P
from .materials import _new
from .util import MB, TAU, collection


# --------------------------------------------------------------------------
# ring stitching (used for the lattice zones and transitions)
# --------------------------------------------------------------------------
def stitch(A, aA, B, aB):
    """Triangulate between two closed rings (index lists + ascending angles)."""
    nA, nB = len(A), len(B)
    aA = np.asarray(aA)
    aB = np.asarray(aB)
    j0 = int(np.argmin(np.abs((aB - aA[0] + math.pi) % TAU - math.pi)))
    uA = np.concatenate([aA - aA[0], [TAU]]) + aA[0]
    rot = np.concatenate([aB[j0:], aB[:j0] + TAU])
    if rot[0] - aA[0] > math.pi:
        rot -= TAU
    if aA[0] - rot[0] > math.pi:
        rot += TAU
    uB = np.concatenate([rot, [rot[0] + TAU]])
    Bi = [B[(j0 + j) % nB] for j in range(nB + 1)]
    Ai = [A[i % nA] for i in range(nA + 1)]
    faces = []
    i = j = 0
    while i < nA or j < nB:
        if j >= nB or (i < nA and uA[i + 1] <= uB[j + 1]):
            faces.append((Ai[i], Bi[j], Ai[i + 1]))
            i += 1
        else:
            faces.append((Ai[i], Bi[j], Bi[j + 1]))
            j += 1
    return faces


def roof_point(r, th):
    return (r * math.cos(th), r * math.sin(th), float(P.roof_z(r, th)))


# --------------------------------------------------------------------------
# Roof
# --------------------------------------------------------------------------
def build_roof(coll, M):
    R_MEAN = 0.5 * (P.R_NOTCH + P.R_LOBE)
    zones = [(96, P.R_OCULUS, 74.0), (192, 74.0, R_MEAN)]
    rows = []       # list of (N, offset, s) ; s normalised radius 0..1
    for zi, (Nz, r0, r1) in enumerate(zones):
        dth = TAU / Nz
        drho = dth / 2.0
        nrow = int(round(math.log(r1 / r0) / drho))
        for b in range(nrow + (1 if zi == len(zones) - 1 else 0)):
            r = r0 * math.exp(b * math.log(r1 / r0) / nrow)
            s = (r - P.R_OCULUS) / (R_MEAN - P.R_OCULUS)
            rows.append((Nz, 0.5 * (b % 2), min(s, 1.0), zi))
    verts, row_id = [], []
    ring_idx = []
    for ri, (Nz, off, s, zi) in enumerate(rows):
        idx, aa = [], []
        for k in range(Nz):
            th = (k + off) * TAU / Nz + P.D2R * 0.0
            Rth = float(P.r_eave(th))
            r = P.R_OCULUS + s * (Rth - P.R_OCULUS)
            idx.append(len(verts))
            aa.append(th)
            verts.append(roof_point(r, th))
            row_id.append(ri)
        ring_idx.append((idx, aa))
    faces = []
    for ri in range(len(rows) - 1):
        A, aA = ring_idx[ri]
        B, aB = ring_idx[ri + 1]
        faces += stitch(A, aA, B, aB)
    # orient faces upward
    V = np.asarray(verts)
    fixed = []
    for f in faces:
        a, b, c = V[list(f)]
        if np.cross(b - a, c - a)[2] < 0:
            f = (f[0], f[2], f[1])
        fixed.append(f)

    me = bpy.data.meshes.new('roof_lattice')
    me.from_pydata(verts, [], fixed)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    transition = {ri for ri in range(1, len(rows)) if rows[ri][3] != rows[ri - 1][3]}
    transition |= {ri - 1 for ri in transition}
    last = len(rows) - 1
    ring_edges = []
    for e in bm.edges:
        r1, r2 = row_id[e.verts[0].index], row_id[e.verts[1].index]
        if r1 == r2 and r1 not in (0, last) and r1 not in transition:
            ring_edges.append(e)
    bmesh.ops.dissolve_edges(bm, edges=ring_edges, use_verts=False)
    bm.to_mesh(me)
    bm.free()

    # ---- material assignment -------------------------------------------------
    me.materials.append(M['pv_bipv'])
    me.materials.append(M['glass_low'])
    mi = np.zeros(len(me.polygons), dtype=np.int32)
    cen = np.zeros(len(me.polygons) * 3, dtype=np.float32)
    me.polygons.foreach_get('center', cen)
    cen = cen.reshape(-1, 3)
    r = np.hypot(cen[:, 0], cen[:, 1])
    th = np.arctan2(cen[:, 1], cen[:, 0])
    u = (r - P.R_OCULUS) / (P.r_eave(th) - P.R_OCULUS)
    vein_step = TAU / 24
    dv = np.abs(((th + vein_step / 2) % vein_step) - vein_step / 2) * r
    lobe = P.lobe(th)
    glass = (r < 36.0) | (dv < 3.2 + 6.0 * lobe * (u > 0.55)) | (np.abs(u - 0.47) < 0.012)
    mi[glass] = 1
    me.polygons.foreach_set('material_index', mi)
    me.update()
    panels = bpy.data.objects.new('Roof_Panels', me)
    coll.objects.link(panels)

    # members = wireframe of the same lattice
    mem = bpy.data.objects.new('Roof_Gridshell', me.copy())
    coll.objects.link(mem)
    mem.data.materials.clear()
    mem.data.materials.append(M['bronze'])
    wf = mem.modifiers.new('members', 'WIREFRAME')
    wf.thickness = 0.36
    wf.offset = 0.0
    wf.use_even_offset = True
    wf.use_boundary = True
    wf.use_replace = True
    mem.location.z = -0.05

    # ---- primary ribs ("leaf veins") under the shell -------------------------
    mb = MB()
    for k in range(24):
        th0 = k * vein_step
        pts = []
        nseg = 70
        for i in range(nseg + 1):
            uu = i / nseg
            rr = P.R_OCULUS + 1.2 + uu * (float(P.r_eave(th0)) - P.R_OCULUS - 1.5)
            x, y, z = roof_point(rr, th0)
            pts.append((x, y, z - 1.15))
        _rect_sweep(mb, pts, 1.0, 2.1, mat=0)
    # oculus compression ring + weir lip
    _ring_box(mb, P.R_OCULUS + 1.6, P.Z_OCULUS - 0.6, 3.2, 2.6, 192, mat=1)
    # eave fascia band
    eave = []
    for i in range(721):
        th0 = i / 720 * TAU
        eave.append(roof_point(float(P.r_eave(th0)), th0))
    for i in range(720):
        a, b = Vector(eave[i]), Vector(eave[i + 1])
        mb.add([tuple(a), tuple(b), tuple(b - Vector((0, 0, 1.6))), tuple(a - Vector((0, 0, 1.6)))],
               [(0, 1, 2, 3)], 1)
    mb.build('Roof_Ribs', coll, [M['steel'], M['champagne']], smooth=True)
    return panels


def _rect_sweep(mb, pts, w, h, mat=0):
    pts = [Vector(p) for p in pts]
    n = len(pts)
    verts = []
    for k in range(n):
        t = (pts[min(k + 1, n - 1)] - pts[max(k - 1, 0)]).normalized()
        side = t.cross(Vector((0, 0, 1))).normalized()
        up = side.cross(t).normalized()
        c = pts[k]
        for sx, sy in ((-1, 0.5), (1, 0.5), (1, -0.5), (-1, -0.5)):
            verts.append(tuple(c + side * (sx * w / 2) + up * (sy * h)))
    faces = []
    for k in range(n - 1):
        for i in range(4):
            a = k * 4 + i
            b = k * 4 + (i + 1) % 4
            faces.append((a, b, b + 4, a + 4))
    faces.append((3, 2, 1, 0))
    faces.append(tuple(range((n - 1) * 4, n * 4)))
    mb.add(verts, faces, mat)


def _ring_box(mb, r, z, w, h, seg, mat=0, z_profile=None):
    verts = []
    for i in range(seg):
        a = TAU * i / seg
        c, s = math.cos(a), math.sin(a)
        for dr, dz in ((-w / 2, h / 2), (w / 2, h / 2), (w / 2, -h / 2), (-w / 2, -h / 2)):
            verts.append(((r + dr) * c, (r + dr) * s, z + dz))
    faces = []
    for i in range(seg):
        j = (i + 1) % seg
        for q in range(4):
            a = i * 4 + q
            b = i * 4 + (q + 1) % 4
            faces.append((a, b, j * 4 + (q + 1) % 4, j * 4 + q))
    mb.add(verts, faces, mat)


# --------------------------------------------------------------------------
# Facade, floors, Sky Well
# --------------------------------------------------------------------------
def build_envelope(coll, M):
    n = 1440
    mb = MB()
    verts, uvs, faces = [], [], []
    acc = 0.0
    prev = None
    for i in range(n + 1):
        th = i / n * TAU
        rf = float(P.r_facade(th))
        x, y = rf * math.cos(th), rf * math.sin(th)
        ztop = float(P.roof_z(rf, th)) - 0.6
        if prev is not None:
            acc += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
        verts += [(x, y, 0.0), (x, y, ztop)]
        uvs += [(acc, 0.0), (acc, ztop)]
    for i in range(n):
        faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    mb.add(verts, faces, 0, uvs)
    mb.build('Hub_Facade', coll, [M['facade']])

    # --- departure floor (Lotus Hall) ------------------------------------------
    mb = MB()
    nr = 10
    P_top = np.zeros((n, nr, 3))
    for i in range(n):
        th = i / n * TAU
        rf = float(P.r_facade(th)) - 0.3
        for j in range(nr):
            rr = P.R_SKYWELL + (rf - P.R_SKYWELL) * (j / (nr - 1)) ** 1.0
            P_top[i, j] = (rr * math.cos(th), rr * math.sin(th), P.Z_DEP)
    mb.grid_surface(P_top, mat=0, close_u=True)
    P_bot = P_top.copy()
    P_bot[..., 2] = P.Z_DEP - 1.4
    mb.grid_surface(P_bot[:, ::-1], mat=1, close_u=True)
    # void edge band
    edge = []
    for i in range(n):
        th = i / n * TAU
        edge.append((P.R_SKYWELL * math.cos(th), P.R_SKYWELL * math.sin(th)))
    for i in range(n):
        a, b = edge[i], edge[(i + 1) % n]
        mb.add([(a[0], a[1], P.Z_DEP), (b[0], b[1], P.Z_DEP), (b[0], b[1], P.Z_DEP - 1.4),
                (a[0], a[1], P.Z_DEP - 1.4)], [(0, 3, 2, 1)], 2)
    # ground floor
    P_g = np.zeros((n, 6, 3))
    for i in range(n):
        th = i / n * TAU
        rf = float(P.r_facade(th)) - 0.3
        for j in range(6):
            rr = 51.5 + (rf - 51.5) * j / 5
            P_g[i, j] = (rr * math.cos(th), rr * math.sin(th), 0.05)
    mb.grid_surface(P_g, mat=0, close_u=True)
    mb.build('Hub_Floors', coll, [M['terrazzo'], M['soffit'], M['stone']])

    # balustrade + handrail around the void
    mb = MB()
    seg = 360
    vs, fs = [], []
    for i in range(seg):
        th = i / seg * TAU
        x, y = (P.R_SKYWELL - 0.3) * math.cos(th), (P.R_SKYWELL - 0.3) * math.sin(th)
        vs += [(x, y, P.Z_DEP), (x, y, P.Z_DEP + 1.15)]
    for i in range(seg):
        j = (i + 1) % seg
        fs.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    mb.add(vs, fs, 0)
    mb.build('SkyWell_Balustrade', coll, [M['glass_low'], M['champagne']])

    # "follow the water": rills on every lobe axis run towards the Sky Well
    rl = MB()
    for d in P.LOBE_DIRS:
        for off in (-7.0, 7.0):
            th = d * P.D2R
            n_ = (-math.sin(th), math.cos(th))
            r1 = float(P.r_facade(th)) - 4.0
            pts = [(r * math.cos(th) + off * n_[0], r * math.sin(th) + off * n_[1])
                   for r in np.linspace(P.R_SKYWELL + 1.0, r1, 40)]
            rl.ribbon(pts, 1.1, P.Z_DEP + 0.03, 0)
            rl.ribbon(pts, 1.5, P.Z_DEP + 0.02, 1)
    rl.build('Hall_Rills', coll, [M['water_clear'], M['stone']])


def build_skywell(coll, M):
    """Terraced garden canyon from the Lotus Hall (z=12) down to the B2 pool."""
    n = 720
    step = (P.Z_DEP - P.Z_RAIL) / P.N_SKY_TERRACES
    dr = (P.R_SKYWELL - P.R_POOL) / P.N_SKY_TERRACES
    beds = MB()
    walls = MB()
    falls = MB()
    lips = MB()
    terraces = []
    for i in range(P.N_SKY_TERRACES):
        z = P.Z_DEP - (i + 1) * step
        r_in_base = P.R_SKYWELL - (i + 1) * dr
        r_out_base = P.R_SKYWELL - i * dr
        rin, rout = [], []
        for k in range(n):
            th = k / n * TAU
            wob = 1.3 * math.sin(3 * th + 1.7 * i) + 0.7 * math.sin(7 * th - 0.9 * i)
            rin.append(max(P.R_POOL, r_in_base + (wob if i < P.N_SKY_TERRACES - 1 else 0.0)))
            rout.append(r_out_base + 0.6)
        terraces.append((z, rin))
        # tread
        Pt = np.zeros((n, 4, 3))
        for k in range(n):
            th = k / n * TAU
            for j, rr in enumerate(np.linspace(rin[k] + 0.9, rout[k] + 2.0, 4)):
                Pt[k, j] = (rr * math.cos(th), rr * math.sin(th), z + (0.35 if j > 0 else 0.25))
        if i < P.N_SKY_TERRACES - 1:
            beds.grid_surface(Pt, mat=0, close_u=True)
        # lip water channel
        Pl = np.zeros((n, 2, 3))
        for k in range(n):
            th = k / n * TAU
            for j, rr in enumerate((rin[k] + 0.05, rin[k] + 0.9)):
                Pl[k, j] = (rr * math.cos(th), rr * math.sin(th), z + 0.15)
        if i < P.N_SKY_TERRACES - 1:
            lips.grid_surface(Pl, mat=0, close_u=True)
        # riser wall (down to next tread)
        Pw = np.zeros((n, 2, 3))
        z_lo = z - step - 0.5
        for k in range(n):
            th = k / n * TAU
            Pw[k, 0] = (rin[k] * math.cos(th), rin[k] * math.sin(th), z + 0.3)
            Pw[k, 1] = (rin[k] * math.cos(th), rin[k] * math.sin(th), z_lo)
        if i < P.N_SKY_TERRACES - 1:
            walls.grid_surface(Pw, mat=0, close_u=True)
            # cascades on part of the riser
            for k0 in range(0, n, 36):
                if (k0 // 36 + i) % 3 != 0:
                    continue
                w = 10 + (k0 * 7 + i * 13) % 14
                Pf = np.zeros((w, 2, 3))
                for q in range(w):
                    k = (k0 + q) % n
                    th = k / n * TAU
                    rr = rin[k] - 0.25
                    Pf[q, 0] = (rr * math.cos(th), rr * math.sin(th), z + 0.2)
                    Pf[q, 1] = ((rr - 0.6) * math.cos(th), (rr - 0.6) * math.sin(th), z - step + 0.3)
                uv = np.zeros((w, 2, 2))
                for q in range(w):
                    uv[q, 0] = (q * TAU * rr / n, step)
                    uv[q, 1] = (q * TAU * rr / n, 0.0)
                falls.grid_surface(Pf, mat=0, uv=uv)
    # the first riser: from Lotus Hall slab down to tread 0
    Pw = np.zeros((n, 2, 3))
    for k in range(n):
        th = k / n * TAU
        Pw[k, 0] = (P.R_SKYWELL * math.cos(th), P.R_SKYWELL * math.sin(th), P.Z_DEP - 1.4)
        Pw[k, 1] = (P.R_SKYWELL * math.cos(th), P.R_SKYWELL * math.sin(th), P.Z_DEP - step - 0.3)
    walls.grid_surface(Pw, mat=0, close_u=True)
    beds_ob = beds.build('SkyWell_Beds', coll, [M['planting']])
    walls.build('SkyWell_Walls', coll, [M['stone_green']])
    falls.build('SkyWell_Cascades', coll, [M['waterfall']])
    lips.build('SkyWell_Rills', coll, [M['water_clear']])

    # pool + floor
    mb = MB()
    mb.disc((0, 0, P.Z_RAIL - 0.35), P.R_POOL + 1.0, 128, 0)
    mb.disc((0, 0, P.Z_RAIL - 1.6), P.R_POOL + 1.0, 128, 1)
    # acrylic funnel
    Pf = np.zeros((128, 6, 3))
    for k in range(128):
        th = k / 128 * TAU
        for j in range(6):
            t = j / 5
            rr = 14.5 - 8.0 * t ** 0.7
            Pf[k, j] = (rr * math.cos(th), rr * math.sin(th), P.Z_RAIL - 0.3 - 9.0 * t)
    mb.grid_surface(Pf, mat=2, close_u=True)
    mb.build('Vortex_Pool', coll, [M['water_clear'], M['stone'], M['glass_low']])
    return terraces, beds_ob


def _foam_material():
    m, g = _new('foam')
    co = g.tc.outputs['Object']
    n1 = g.noise(co, 1.4, 8, 0.65)
    a = g.ramp(n1.outputs['Fac'], [(0.42, (0, 0, 0)), (0.62, (1, 1, 1))])
    white = g.mixs(0.5, g.sh('ShaderNodeBsdfTranslucent', Color=(0.9, 0.93, 0.95)),
                   g.sh('ShaderNodeBsdfDiffuse', Color=(0.9, 0.92, 0.94)))
    g.out(g.mixs(g.sep(a)[0], g.sh('ShaderNodeBsdfTransparent', Color=(1, 1, 1)), white))
    return m


def build_vortex(coll, M):
    """The Sky Well vortex: a 58 m cylindrical water curtain from the oculus
    to the B2 pool, plus spill lip, splash foam and a mist plume."""
    from mathutils.noise import noise as pnoise
    seg, rows = 288, 150
    z0, z1 = P.Z_OCULUS - 1.8, P.Z_RAIL - 0.3
    mb = MB()
    for layer, (r_top, r_bot, ph) in enumerate(((P.R_OCULUS - 1.3, P.R_OCULUS - 2.6, 0.0),
                                                 (P.R_OCULUS - 2.0, P.R_OCULUS - 3.6, 3.1))):
        Pt = np.zeros((seg, rows, 3))
        uv = np.zeros((seg, rows, 2))
        for k in range(seg):
            th = k / seg * TAU
            for j in range(rows):
                t = j / (rows - 1)
                z = z0 + (z1 - z0) * t
                r = r_top + (r_bot - r_top) * t ** 0.8
                # swirl: the curtain twists ~25 deg over its height
                tw = th + 0.45 * t
                wob = 0.35 * pnoise(Vector((math.cos(th) * 3, math.sin(th) * 3, z * 0.08 + ph)))
                wob += 0.6 * t * pnoise(Vector((math.cos(th) * 9, math.sin(th) * 9, z * 0.2 + ph)))
                Pt[k, j] = ((r + wob) * math.cos(tw), (r + wob) * math.sin(tw), z)
                uv[k, j] = (th * r + layer * 13.0, z)
        mb.grid_surface(Pt, mat=0, uv=uv, close_u=True)
    # spill lip: water curling over the oculus weir
    Pl = np.zeros((seg, 8, 3))
    uvl = np.zeros((seg, 8, 2))
    for k in range(seg):
        th = k / seg * TAU
        for j in range(8):
            t = j / 7
            r = P.R_OCULUS + 0.9 - 2.2 * math.sin(t * math.pi / 2)
            z = P.Z_OCULUS + 0.7 - 2.5 * t ** 2
            Pl[k, j] = (r * math.cos(th), r * math.sin(th), z)
            uvl[k, j] = (th * r, z + 60)
    mb.grid_surface(Pl, mat=0, uv=uvl, close_u=True)
    vortex = mb.build('Vortex_Waterfall', coll, [M['waterfall']], smooth=True)

    foam = _foam_material()
    mb = MB()
    Pf = np.zeros((seg, 10, 3))
    for k in range(seg):
        th = k / seg * TAU
        for j in range(10):
            t = j / 9
            r = 10.0 + 9.0 * t
            h = 2.4 * math.sin(math.pi * min(1, t * 1.15)) * (0.6 + 0.4 * pnoise(Vector((math.cos(th) * 6, math.sin(th) * 6, t * 3))))
            Pf[k, j] = (r * math.cos(th), r * math.sin(th), P.Z_RAIL - 0.3 + max(0.0, h))
    mb.grid_surface(Pf, mat=0, close_u=True)
    mb.build('Vortex_Splash', coll, [foam], smooth=True)

    # mist plume volume
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=24.0, depth=16.0,
                                        location=(0, 0, P.Z_RAIL + 7.5))
    mist = bpy.context.active_object
    mist.name = 'Vortex_Mist'
    for c in mist.users_collection:
        c.objects.unlink(mist)
    coll.objects.link(mist)
    mist.data.materials.append(M['mist'])
    return vortex


# --------------------------------------------------------------------------
# Banyan tree-columns
# --------------------------------------------------------------------------
def build_columns(coll, M):
    mb = MB()
    rings = [(104.0, 12, 15.0), (184.0, 12, 0.0)]
    for rc, cnt, off in rings:
        for k in range(cnt):
            th = (off + k * 360.0 / cnt) * P.D2R
            # skip columns that would land inside a pier junction axis
            cx, cy = rc * math.cos(th), rc * math.sin(th)
            z_roof = float(P.roof_z(rc, th))
            z_split = P.Z_DEP + 0.58 * (z_roof - P.Z_DEP)
            mb.path_tube([(cx, cy, 0.0), (cx, cy, P.Z_DEP), (cx, cy, z_split - 4), (cx, cy, z_split)],
                         [1.5, 1.45, 1.75, 2.3], seg=20, mat=0)
            mb.cylinder((cx, cy, z_split - 0.6), 2.6, 1.2, seg=24, mat=1)
            nb = 6
            for b in range(nb):
                a = th + b * TAU / nb + 0.3
                rr = 15.0
                tx, ty = cx + rr * math.cos(a), cy + rr * math.sin(a)
                tr = math.hypot(tx, ty)
                tth = math.atan2(ty, tx)
                tz = float(P.roof_z(tr, tth)) - 1.1
                mid = (cx + 0.45 * (tx - cx), cy + 0.45 * (ty - cy), z_split + 0.62 * (tz - z_split))
                mb.path_tube([(cx, cy, z_split), mid, (tx, ty, tz)], [1.1, 0.8, 0.55], seg=12, mat=0)
    mb.build('Tree_Columns', coll, [M['steel'], M['champagne']], smooth=True)


# --------------------------------------------------------------------------
# Lotus Hall planters (positions returned for scatter)
# --------------------------------------------------------------------------
def build_hall(coll, M):
    mb = MB()
    planters = []
    # circular planters on the Lotus Hall
    for k in range(36):
        th = (k * 10.0 + 5) * P.D2R
        rr = [178.0, 160.0, 205.0][k % 3]
        if rr > float(P.r_facade(th)) - 12:
            continue
        x, y = rr * math.cos(th), rr * math.sin(th)
        mb.cylinder((x, y, P.Z_DEP), 4.2, 0.9, seg=32, mat=3)
        mb.disc((x, y, P.Z_DEP + 0.88), 3.9, 32, 4)
        planters.append((x, y, P.Z_DEP + 0.88))
    mb.build('Hall_Pavilions', coll, [M['timber'], M['timber'], M['glass'], M['stone'], M['soil']])
    return planters


# --------------------------------------------------------------------------
# Night lighting rig (toggled per shot)
# --------------------------------------------------------------------------
def build_night_lights(coll, M):
    lights = []
    # roof up-lights: wash the gridshell soffit
    for k in range(24):
        th = (k * 15.0 + 7.5) * P.D2R
        for rr in (60.0, 120.0, 190.0):
            if rr > float(P.r_facade(th)) - 8:
                continue
            ld = bpy.data.lights.new(f'uplight_{k}_{int(rr)}', 'AREA')
            ld.shape = 'DISK'
            ld.size = 14.0
            ld.energy = 1.4e5 if rr > 70 else 0.9e5
            ld.color = (1.0, 0.78, 0.55)
            ob = bpy.data.objects.new(ld.name, ld)
            ob.location = (rr * math.cos(th), rr * math.sin(th), P.Z_DEP + 2.0)
            ob.rotation_euler = (0, 0, 0)  # pointing down by default -> flip
            ob.rotation_euler = (math.pi, 0, 0)
            coll.objects.link(ob)
            lights.append(ob)
    # down-lights for the hall floor
    for k in range(36):
        th = k * 10.0 * P.D2R
        for rr in (95.0, 150.0, 200.0):
            if rr > float(P.r_facade(th)) - 8:
                continue
            ld = bpy.data.lights.new(f'down_{k}_{int(rr)}', 'AREA')
            ld.shape = 'DISK'
            ld.size = 10.0
            ld.energy = 5.0e4
            ld.color = (1.0, 0.82, 0.62)
            ob = bpy.data.objects.new(ld.name, ld)
            ob.location = (rr * math.cos(th), rr * math.sin(th), float(P.roof_z(rr, th)) - 6.0)
            coll.objects.link(ob)
            lights.append(ob)
    # vortex: pool up-light ring
    for k in range(16):
        th = k / 16 * TAU
        ld = bpy.data.lights.new(f'vortex_{k}', 'SPOT')
        ld.energy = 2.5e5
        ld.spot_size = math.radians(30)
        ld.spot_blend = 0.6
        ld.color = (0.55, 0.85, 1.0)
        ob = bpy.data.objects.new(ld.name, ld)
        ob.location = (19.0 * math.cos(th), 19.0 * math.sin(th), P.Z_RAIL + 0.5)
        ob.rotation_euler = Vector((-math.cos(th) * 0.4, -math.sin(th) * 0.4, 1.0)).to_track_quat('-Z', 'Y').to_euler()
        coll.objects.link(ob)
        lights.append(ob)
    return lights


def build(M, root):
    coll = collection('Hub', root)
    build_roof(coll, M)
    build_envelope(coll, M)
    terr, beds = build_skywell(coll, M)
    build_vortex(coll, M)
    build_columns(coll, M)
    planters = build_hall(coll, M)
    night = collection('Night_Hub', root)
    build_night_lights(night, M)
    return {'skywell_terraces': terr, 'planters': planters}
