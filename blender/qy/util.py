"""Low-level helpers: collections, mesh building, node wiring.

Everything in the Qingyun model is generated from code, so these helpers are
kept small and fast (plain lists + foreach_set) to handle ~10^6 vertices.
"""
import math
import random

import bpy
import numpy as np
from mathutils import Vector, Matrix

TAU = math.tau


# --------------------------------------------------------------------------
# Collections / objects
# --------------------------------------------------------------------------
def collection(name, parent=None, link=True):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        if link:
            (parent or bpy.context.scene.collection).children.link(c)
    return c


def library_collection(name):
    """A collection that is NOT linked to the scene (instancing source)."""
    return collection(name, link=False)


def link(obj, coll):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


# --------------------------------------------------------------------------
# Mesh builder
# --------------------------------------------------------------------------
class MB:
    """Accumulates vertices / faces / material indices / per-vertex UVs."""

    def __init__(self):
        self.v = []
        self.f = []
        self.m = []
        self.uv = []

    def __len__(self):
        return len(self.v)

    def add(self, verts, faces, mat=0, uvs=None):
        off = len(self.v)
        self.v.extend(verts)
        if uvs is None:
            self.uv.extend([(0.0, 0.0)] * len(verts))
        else:
            self.uv.extend(uvs)
        self.f.extend([tuple(i + off for i in face) for face in faces])
        if isinstance(mat, (list, tuple)):
            self.m.extend(mat)
        else:
            self.m.extend([mat] * len(faces))
        return off

    # ---- primitives -------------------------------------------------------
    def tube(self, p0, p1, r0, r1=None, seg=8, mat=0, cap=True, up=None):
        r1 = r0 if r1 is None else r1
        p0 = Vector(p0)
        p1 = Vector(p1)
        d = p1 - p0
        L = d.length
        if L < 1e-6:
            return
        z = d / L
        ref = Vector((0, 0, 1)) if abs(z.z) < 0.95 else Vector((1, 0, 0))
        if up is not None:
            ref = Vector(up)
        x = z.cross(ref).normalized()
        y = z.cross(x)
        verts = []
        uvs = []
        for k, (p, r) in enumerate(((p0, r0), (p1, r1))):
            for i in range(seg):
                a = TAU * i / seg
                verts.append(tuple(p + (x * math.cos(a) + y * math.sin(a)) * r))
                uvs.append((i / seg * TAU * r, k * L))
        faces = [(i, (i + 1) % seg, seg + (i + 1) % seg, seg + i) for i in range(seg)]
        if cap:
            faces.append(tuple(reversed(range(seg))))
            faces.append(tuple(range(seg, 2 * seg)))
        self.add(verts, faces, mat, uvs)

    def path_tube(self, pts, radii, seg=8, mat=0, cap=True):
        """Swept circle along a polyline with per-point radius."""
        pts = [Vector(p) for p in pts]
        n = len(pts)
        verts, uvs = [], []
        ref = Vector((0, 0, 1))
        acc = 0.0
        prev_x = None
        for k in range(n):
            if k == 0:
                t = pts[1] - pts[0]
            elif k == n - 1:
                t = pts[-1] - pts[-2]
            else:
                t = pts[k + 1] - pts[k - 1]
            t.normalize()
            if prev_x is None:
                r = ref if abs(t.z) < 0.95 else Vector((1, 0, 0))
                x = t.cross(r).normalized()
            else:  # parallel transport
                x = (prev_x - t * prev_x.dot(t)).normalized()
            y = t.cross(x)
            prev_x = x
            if k > 0:
                acc += (pts[k] - pts[k - 1]).length
            for i in range(seg):
                a = TAU * i / seg
                verts.append(tuple(pts[k] + (x * math.cos(a) + y * math.sin(a)) * radii[k]))
                uvs.append((i / seg * TAU * radii[k], acc))
        faces = []
        for k in range(n - 1):
            for i in range(seg):
                a = k * seg + i
                b = k * seg + (i + 1) % seg
                faces.append((a, b, b + seg, a + seg))
        if cap:
            faces.append(tuple(reversed(range(seg))))
            faces.append(tuple(range((n - 1) * seg, n * seg)))
        self.add(verts, faces, mat, uvs)

    def box(self, c, size, rz=0.0, mat=0, rx=0.0, ry=0.0):
        sx, sy, sz = (s / 2 for s in size)
        R = (Matrix.Rotation(rz, 3, 'Z') @ Matrix.Rotation(ry, 3, 'Y') @ Matrix.Rotation(rx, 3, 'X'))
        c = Vector(c)
        corners = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
                   (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
        verts = [tuple(c + R @ Vector(p)) for p in corners]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        uvs = [(p[0] + p[1], p[2]) for p in corners]
        self.add(verts, faces, mat, uvs)

    def cylinder(self, c, r, h, seg=24, mat=0, cap=True, r_top=None):
        c = Vector(c)
        self.tube(c, c + Vector((0, 0, h)), r, r_top if r_top is not None else r, seg, mat, cap)

    def disc(self, c, r, seg=32, mat=0, z_up=True):
        c = Vector(c)
        verts = [tuple(c)] + [tuple(c + Vector((r * math.cos(TAU * i / seg), r * math.sin(TAU * i / seg), 0)))
                              for i in range(seg)]
        faces = [(0, 1 + i, 1 + (i + 1) % seg) for i in range(seg)]
        if not z_up:
            faces = [tuple(reversed(f)) for f in faces]
        uvs = [(v[0], v[1]) for v in verts]
        self.add(verts, faces, mat, uvs)

    def ribbon(self, pts, width, z=0.0, mat=0, close=False):
        """Flat strip along a 2D polyline (for road / runway markings)."""
        pts = [Vector((p[0], p[1])) for p in pts]
        n = len(pts)
        verts, uvs = [], []
        acc = 0.0
        for k in range(n):
            if close:
                t = pts[(k + 1) % n] - pts[k - 1]
            elif k == 0:
                t = pts[1] - pts[0]
            elif k == n - 1:
                t = pts[-1] - pts[-2]
            else:
                t = pts[k + 1] - pts[k - 1]
            t.normalize()
            nrm = Vector((-t.y, t.x))
            if k > 0:
                acc += (pts[k] - pts[k - 1]).length
            zz = z[k] if isinstance(z, (list, tuple)) else z
            a = pts[k] + nrm * width / 2
            b = pts[k] - nrm * width / 2
            verts += [(a.x, a.y, zz), (b.x, b.y, zz)]
            uvs += [(acc, width / 2), (acc, -width / 2)]
        m = n if close else n - 1
        faces = [(2 * k + 1, 2 * ((k + 1) % n) + 1, 2 * ((k + 1) % n), 2 * k) for k in range(m)]
        self.add(verts, faces, mat, uvs)

    def grid_surface(self, P, mat=0, uv=None, close_u=False):
        """P: array (nu, nv, 3) of points -> quad surface."""
        nu, nv = P.shape[0], P.shape[1]
        verts = [tuple(p) for p in P.reshape(-1, 3)]
        faces = []
        mu = nu if close_u else nu - 1
        for i in range(mu):
            i2 = (i + 1) % nu
            for j in range(nv - 1):
                faces.append((i * nv + j, i2 * nv + j, i2 * nv + j + 1, i * nv + j + 1))
        uvs = None
        if uv is not None:
            uvs = [tuple(q) for q in uv.reshape(-1, 2)]
        self.add(verts, faces, mat, uvs)

    # ---- output -----------------------------------------------------------
    def build(self, name, coll, mats=(), smooth=False):
        me = bpy.data.meshes.new(name)
        v = np.asarray(self.v, dtype=np.float32).reshape(-1)
        me.vertices.add(len(self.v))
        me.vertices.foreach_set('co', v)
        # faces of mixed arity
        sizes = np.fromiter((len(f) for f in self.f), dtype=np.int32, count=len(self.f))
        loops = np.fromiter((i for f in self.f for i in f), dtype=np.int32, count=int(sizes.sum()))
        starts = np.zeros(len(sizes), dtype=np.int32)
        if len(sizes) > 1:
            starts[1:] = np.cumsum(sizes)[:-1]
        me.loops.add(len(loops))
        me.loops.foreach_set('vertex_index', loops)
        me.polygons.add(len(sizes))
        me.polygons.foreach_set('loop_start', starts)
        if mats:
            me.polygons.foreach_set('material_index', np.asarray(self.m, dtype=np.int32))
        uvl = me.uv_layers.new(name='UVMap')
        uvv = np.asarray(self.uv, dtype=np.float32)
        uvl.data.foreach_set('uv', uvv[loops].reshape(-1))
        me.update(calc_edges=True)
        me.validate(clean_customdata=False)
        if smooth:
            me.polygons.foreach_set('use_smooth', np.ones(len(sizes), dtype=bool))
        for m in mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob


# --------------------------------------------------------------------------
# Node helpers
# --------------------------------------------------------------------------
def new_material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m, m.node_tree
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return m, nt


def N(nt, kind, inputs=None, **attrs):
    n = nt.nodes.new(kind)
    for k, v in attrs.items():
        setattr(n, k, v)
    if inputs:
        for k, v in inputs.items():
            sock = n.inputs[k]
            if hasattr(v, 'is_output') or hasattr(v, 'links'):
                nt.links.new(v, sock)
            else:
                sock.default_value = v
    return n


def L(nt, a, b):
    nt.links.new(a, b)


def math_node(nt, op, a, b=None, clamp=False):
    n = nt.nodes.new('ShaderNodeMath')
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if hasattr(v, 'is_output'):
            nt.links.new(v, n.inputs[i])
        else:
            n.inputs[i].default_value = v
    return n.outputs[0]


def mix_rgb(nt, fac, a, b, blend='MIX'):
    n = nt.nodes.new('ShaderNodeMix')
    n.data_type = 'RGBA'
    n.blend_type = blend
    for sock, v in ((n.inputs[0], fac), (n.inputs[6], a), (n.inputs[7], b)):
        if hasattr(v, 'is_output'):
            nt.links.new(v, sock)
        else:
            sock.default_value = v if not isinstance(v, (int, float)) else v
    return n.outputs[2]


def mix_shader(nt, fac, a, b):
    n = nt.nodes.new('ShaderNodeMixShader')
    if hasattr(fac, 'is_output'):
        nt.links.new(fac, n.inputs[0])
    else:
        n.inputs[0].default_value = fac
    nt.links.new(a, n.inputs[1])
    nt.links.new(b, n.inputs[2])
    return n.outputs[0]


def rng(seed):
    return random.Random(seed)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)
