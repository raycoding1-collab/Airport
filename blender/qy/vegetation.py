"""Procedural trees (branching skeleton + alpha-tested leaf-cluster cards)
and a geometry-nodes instancer that scatters them from point sets.

Planting palette (Yangtze-delta, November): evergreen camphor, golden ginkgo,
red maple, pink 'autumn-flowering' cherry, weeping willow by water, pine,
bamboo groves and clipped shrubs."""
import math

import bpy
import numpy as np
from mathutils import Vector

from .util import MB, TAU

VARIANTS = []          # (name, object)


def _cards(mb, centers, size, rs, mat, normals=None, hang=False):
    for idx, c in enumerate(centers):
        c = Vector(c)
        if hang:
            nrm = Vector((rs.uniform(-1, 1), rs.uniform(-1, 1), 0)).normalized()
            up = Vector((0, 0, 1))
        else:
            nrm = Vector(normals[idx]) if normals is not None else Vector(rs.normal(size=3)).normalized()
            nrm = (nrm + Vector(rs.normal(size=3)) * 0.6).normalized()
            up = Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((1, 0, 0))
        t1 = nrm.cross(up).normalized()
        t2 = nrm.cross(t1).normalized()
        a = rs.uniform(0, TAU)
        t1, t2 = t1 * math.cos(a) + t2 * math.sin(a), -t1 * math.sin(a) + t2 * math.cos(a)
        s = size * rs.uniform(0.75, 1.25)
        if hang:
            t1 = Vector((nrm.y, -nrm.x, 0)).normalized()
            t2 = Vector((0, 0, 1))
            v = [c - t1 * s * 0.25 + t2 * 0.0, c + t1 * s * 0.25, c + t1 * s * 0.25 - t2 * s * 1.6,
                 c - t1 * s * 0.25 - t2 * s * 1.6]
        else:
            v = [c - t1 * s / 2 - t2 * s / 2, c + t1 * s / 2 - t2 * s / 2, c + t1 * s / 2 + t2 * s / 2,
                 c - t1 * s / 2 + t2 * s / 2]
        mb.add([tuple(p) for p in v], [(0, 1, 2, 3)], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])


def _branch(mb, p0, d, length, r0, depth, rs, tips, up_bias=0.35, spread=0.75):
    p1 = p0 + d * length
    mb.tube(p0, p1, r0, r0 * 0.62, 6 if depth > 0 else 4, 0, cap=False)
    if depth == 0:
        tips.append(p1)
        return
    n = rs.randint(2, 4)
    for _ in range(n):
        nd = (d + Vector(rs.normal(size=3)) * spread + Vector((0, 0, up_bias))).normalized()
        _branch(mb, p1, nd, length * rs.uniform(0.55, 0.8), r0 * 0.6, depth - 1, rs, tips, up_bias, spread)


def make_tree(name, kind, H, crown, leaf_mat, seed, n_cards=900, card=1.4):
    rs = np.random.RandomState(seed)
    mb = MB()
    tips = []
    if kind == 'round':
        trunk_h = 0.36 * H
        r0 = 0.045 * H
        mb.tube((0, 0, -0.3), (0, 0, trunk_h), r0 * 1.25, r0, 8, 0)
        for b in range(rs.randint(4, 7)):
            a = rs.uniform(0, TAU)
            d = Vector((math.cos(a) * 0.7, math.sin(a) * 0.7, 0.9)).normalized()
            _branch(mb, Vector((0, 0, trunk_h)), d, H * 0.25, r0 * 0.7, 2, rs, tips)
        cz = 0.64 * H
        # lumpy crown: leaf clusters gathered around sub-crowns at branch tips
        centers = []
        for _ in range(rs.randint(7, 12)):
            v = Vector(rs.normal(size=3)).normalized()
            v.z = abs(v.z) * 0.8 + 0.1
            rr = rs.uniform(0.35, 0.7)
            centers.append(Vector((v.x * crown * rr, v.y * crown * rr, cz + v.z * (H - cz) * 0.6 * rr)))
        for c in centers:   # visible limbs to each sub-crown
            mb.tube((0, 0, trunk_h), tuple(c), r0 * 0.45, r0 * 0.12, 5, 0, cap=False)
        pts, nrm = [], []
        for _ in range(n_cards):
            c = centers[rs.randint(len(centers))]
            v = Vector(rs.normal(size=3)).normalized()
            rad = crown * rs.uniform(0.38, 0.55)
            rr = rs.uniform(0.45, 1.0) ** 0.6
            p = c + Vector((v.x * rad * rr, v.y * rad * rr, v.z * rad * 0.8 * rr))
            pts.append(p)
            nrm.append((p - Vector((0, 0, cz * 0.8))).normalized())
        _cards(mb, pts, card, rs, 1, nrm)
    elif kind == 'cone':
        r0 = 0.04 * H
        mb.tube((0, 0, -0.3), (0, 0, H * 0.95), r0, r0 * 0.2, 8, 0)
        for w in range(7):
            z = H * (0.22 + 0.1 * w)
            for b in range(4):
                a = rs.uniform(0, TAU)
                L = crown * (1 - (z / H)) * 1.1
                d = Vector((math.cos(a), math.sin(a), 0.25)).normalized()
                mb.tube((0, 0, z), tuple(Vector((0, 0, z)) + d * L), r0 * 0.35, r0 * 0.08, 5, 0, cap=False)
        pts, nrm = [], []
        for _ in range(n_cards):
            z = rs.uniform(0.18, 1.0) ** 0.8 * H
            a = rs.uniform(0, TAU)
            rmax = crown * (1 - (z - 0.18 * H) / (0.82 * H)) ** 0.9 + 0.3
            rmax *= 0.75 + 0.5 * (0.5 + 0.5 * math.sin(3 * a + z * 0.9)) * (0.6 + 0.4 * math.sin(z * 1.7))
            rr = rmax * rs.uniform(0.4, 1.0) ** 0.5
            pts.append((rr * math.cos(a), rr * math.sin(a), z))
            nrm.append((math.cos(a), math.sin(a), 0.3))
        _cards(mb, pts, card, rs, 1, nrm)
    elif kind == 'willow':
        trunk_h = 0.42 * H
        r0 = 0.05 * H
        mb.tube((0, 0, -0.3), (0, 0, trunk_h), r0 * 1.3, r0, 8, 0)
        tips = []
        for b in range(7):
            a = b / 7 * TAU + rs.uniform(-0.3, 0.3)
            d = Vector((math.cos(a) * 0.75, math.sin(a) * 0.75, 0.75)).normalized()
            _branch(mb, Vector((0, 0, trunk_h)), d, H * 0.24, r0 * 0.6, 2, rs, tips, 0.55, 0.6)
        # long weeping strands hanging from every twig tip
        pts = []
        for t in tips:
            for _ in range(int(n_cards / max(len(tips), 1)) + 1):
                pts.append(t + Vector((rs.normal() * 1.2, rs.normal() * 1.2, rs.uniform(-0.5, 1.0))))
        for p in pts:
            p = Vector(p)
            ang = rs.uniform(0, TAU)
            t1 = Vector((math.cos(ang), math.sin(ang), 0))
            w = 0.32 * card
            Lh = rs.uniform(2.5, 5.0) * (p.z / H) ** 0.5
            v = [p - t1 * w, p + t1 * w, p + t1 * w * 0.6 - Vector((0, 0, Lh)), p - t1 * w * 0.6 - Vector((0, 0, Lh))]
            mb.add([tuple(q) for q in v], [(0, 1, 2, 3)], 1, [(0, 1), (1, 1), (1, 0), (0, 0)])
        tips = []
    elif kind == 'shrub':
        pts, nrm = [], []
        for _ in range(n_cards):
            v = Vector(rs.normal(size=3)).normalized()
            rr = rs.uniform(0.5, 1.0) ** 0.4
            pts.append((v.x * crown * rr, v.y * crown * rr, max(0.1, H * 0.5 + v.z * H * 0.5 * rr)))
            nrm.append(v)
        _cards(mb, pts, card, rs, 1, nrm)
    elif kind == 'bamboo':
        for c in range(14):
            a = rs.uniform(0, TAU)
            rr = rs.uniform(0, crown * 0.35)
            base = Vector((rr * math.cos(a), rr * math.sin(a), -0.2))
            top = base + Vector((rs.normal() * 0.6, rs.normal() * 0.6, H * rs.uniform(0.8, 1.05)))
            mb.tube(base, top, 0.06, 0.03, 5, 2, cap=False)
            for q in range(30):
                t = rs.uniform(0.35, 1.0)
                p = base + (top - base) * t + Vector(rs.normal(size=3)) * 0.5
                tips.append(p)
        _cards(mb, tips, card, rs, 1, None)
        tips = []
    # leaves at branch tips for broadleaf trees (fills the skeleton visibly)
    if tips and kind in ('round', 'willow'):
        _cards(mb, [t + Vector(rs.normal(size=3)) * 0.4 for t in tips for _ in range(3)], card, rs, 1)
    lib = bpy.data.collections.get('LIB_trees') or bpy.data.collections.new('LIB_trees')
    mats = [bpy.data.materials['bark'], leaf_mat, bpy.data.materials['bamboo_cane']]
    ob = mb.build(name, lib, mats)
    return ob


def build_variants():
    M = bpy.data.materials
    spec = [
        # name, kind, H, crown, leaf, cards, card size
        ('T00_camphor_a', 'round', 13.0, 6.5, 'leaf_camphor', 1400, 1.6),
        ('T01_camphor_b', 'round', 10.0, 5.0, 'leaf_camphor', 1100, 1.4),
        ('T02_ginkgo_a', 'round', 15.0, 4.6, 'leaf_ginkgo', 1500, 1.3),
        ('T03_ginkgo_b', 'round', 10.5, 3.6, 'leaf_ginkgo', 1100, 1.1),
        ('T04_maple', 'round', 8.0, 4.4, 'leaf_maple', 1000, 1.2),
        ('T05_blossom', 'round', 6.5, 3.8, 'leaf_blossom', 900, 1.0),
        ('T06_willow', 'willow', 11.0, 6.0, 'leaf_willow', 1500, 1.3),
        ('T07_pine', 'cone', 14.0, 3.6, 'leaf_pine', 1300, 1.4),
        ('T08_bamboo', 'bamboo', 8.0, 3.0, 'leaf_bamboo', 0, 0.9),
        ('T09_shrub_a', 'shrub', 1.4, 1.3, 'leaf_shrub', 160, 0.7),
        ('T10_shrub_b', 'shrub', 1.0, 1.0, 'leaf_camphor', 120, 0.6),
        ('T11_shrub_c', 'shrub', 1.8, 1.6, 'leaf_maple', 180, 0.8),
    ]
    lib = bpy.data.collections.get('LIB_trees') or bpy.data.collections.new('LIB_trees')
    objs = {}
    for i, (nm, kind, H, cr, leaf, nc, cs) in enumerate(spec):
        objs[nm] = make_tree(nm, kind, H, cr, M[leaf], 100 + i, nc, cs)
    return objs, lib


# --------------------------------------------------------------------------
# Geometry-nodes instancer
# --------------------------------------------------------------------------
def _gn_scatter_group(lib):
    name = 'GN_scatter_' + lib.name
    ng = bpy.data.node_groups.get(name)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi = ng.nodes.new('NodeGroupInput')
    go = ng.nodes.new('NodeGroupOutput')
    ci = ng.nodes.new('GeometryNodeCollectionInfo')
    ci.inputs['Collection'].default_value = lib
    ci.inputs['Separate Children'].default_value = True
    ci.inputs['Reset Children'].default_value = True
    ci.transform_space = 'ORIGINAL'
    iop = ng.nodes.new('GeometryNodeInstanceOnPoints')
    iop.inputs['Pick Instance'].default_value = True
    na_v = ng.nodes.new('GeometryNodeInputNamedAttribute')
    na_v.data_type = 'INT'
    na_v.inputs['Name'].default_value = 'vid'
    na_r = ng.nodes.new('GeometryNodeInputNamedAttribute')
    na_r.data_type = 'FLOAT_VECTOR'
    na_r.inputs['Name'].default_value = 'rot'
    na_s = ng.nodes.new('GeometryNodeInputNamedAttribute')
    na_s.data_type = 'FLOAT_VECTOR'
    na_s.inputs['Name'].default_value = 'scl'
    e2r = ng.nodes.new('FunctionNodeEulerToRotation')
    ng.links.new(gi.outputs[0], iop.inputs['Points'])
    ng.links.new(ci.outputs[0], iop.inputs['Instance'])
    ng.links.new(na_v.outputs['Attribute'], iop.inputs['Instance Index'])
    ng.links.new(na_r.outputs['Attribute'], e2r.inputs[0])
    ng.links.new(e2r.outputs[0], iop.inputs['Rotation'])
    ng.links.new(na_s.outputs['Attribute'], iop.inputs['Scale'])
    ng.links.new(iop.outputs[0], go.inputs[0])
    return ng


def scatter(name, coll, lib, pts, vids, scales, rs=None, yaw=None):
    """pts (N,3); vids (N,) int index into the sorted children of `lib`."""
    rs = rs or np.random.RandomState(abs(hash(name)) % 2 ** 31)
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 3)
    N = len(pts)
    if N == 0:
        return None
    me = bpy.data.meshes.new('pts_' + name)
    me.vertices.add(N)
    me.vertices.foreach_set('co', pts.reshape(-1))
    a = me.attributes.new('vid', 'INT', 'POINT')
    a.data.foreach_set('value', np.asarray(vids, dtype=np.int32))
    r = me.attributes.new('rot', 'FLOAT_VECTOR', 'POINT')
    rot = np.zeros((N, 3), np.float32)
    rot[:, 2] = rs.uniform(0, TAU, N) if yaw is None else yaw
    rot[:, 0] = rs.normal(0, 0.03, N)
    rot[:, 1] = rs.normal(0, 0.03, N)
    r.data.foreach_set('vector', rot.reshape(-1))
    s = me.attributes.new('scl', 'FLOAT_VECTOR', 'POINT')
    sc = np.repeat(np.asarray(scales, np.float32).reshape(-1, 1), 3, axis=1)
    s.data.foreach_set('vector', sc.reshape(-1))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    mod = ob.modifiers.new('scatter', 'NODES')
    mod.node_group = _gn_scatter_group(lib)
    return ob


def variant_index(lib):
    names = sorted(o.name for o in lib.objects)
    return {n: i for i, n in enumerate(names)}
