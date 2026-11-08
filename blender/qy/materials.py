"""Procedural PBR material library (Cycles).

No external textures: every surface is synthesised from noise / voronoi /
coordinate math so the model is fully reproducible from source.  The only
bitmap (the leaf-cluster atlas) is itself generated with numpy at build time.
"""
import math

import bpy
import numpy as np

EMITTERS = {}   # name -> (node, day_strength, night_strength)


def _sock(v):
    return hasattr(v, 'is_output')


class G:
    """Tiny node-graph DSL around a material node tree."""

    def __init__(self, mat):
        self.mat = mat
        self.nt = mat.node_tree
        for n in list(self.nt.nodes):
            self.nt.nodes.remove(n)
        self._tc = None

    # basic ------------------------------------------------------------
    def node(self, kind, inp=None, **attrs):
        n = self.nt.nodes.new(kind)
        for k, v in attrs.items():
            setattr(n, k, v)
        for k, v in (inp or {}).items():
            s = n.inputs[k]
            if _sock(v):
                self.nt.links.new(v, s)
            else:
                s.default_value = v
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    @property
    def tc(self):
        if self._tc is None:
            self._tc = self.node('ShaderNodeTexCoord')
        return self._tc

    def sep(self, vec):
        n = self.node('ShaderNodeSeparateXYZ', {'Vector': vec})
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def comb(self, x=0.0, y=0.0, z=0.0):
        return self.node('ShaderNodeCombineXYZ', {'X': x, 'Y': y, 'Z': z}).outputs[0]

    def m(self, op, a, b=None, c=None, clamp=False):
        n = self.nt.nodes.new('ShaderNodeMath')
        n.operation = op
        n.use_clamp = clamp
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if _sock(v):
                self.nt.links.new(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs[0]

    def vm(self, op, a, b=None, scale=None):
        n = self.nt.nodes.new('ShaderNodeVectorMath')
        n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if _sock(v):
                self.nt.links.new(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        if scale is not None:
            n.inputs['Scale'].default_value = scale
        return n.outputs[0] if op not in ('LENGTH', 'DOT_PRODUCT', 'DISTANCE') else n.outputs[1]

    def noise(self, vec, scale, detail=4.0, rough=0.55, dims='3D', distortion=0.0, w=0.0):
        n = self.node('ShaderNodeTexNoise', {'Scale': scale, 'Detail': detail, 'Roughness': rough,
                                             'Distortion': distortion}, noise_dimensions=dims)
        if vec is not None:
            self.link(vec, n.inputs['Vector'])
        if dims in ('4D', '1D'):
            n.inputs['W'].default_value = w
        return n

    def voronoi(self, vec, scale, feature='F1', dims='3D', rand=1.0):
        n = self.node('ShaderNodeTexVoronoi', {'Scale': scale, 'Randomness': rand},
                      feature=feature, voronoi_dimensions=dims)
        if vec is not None:
            self.link(vec, n.inputs['Vector'])
        return n

    def ramp(self, fac, stops, interp='LINEAR'):
        n = self.node('ShaderNodeValToRGB')
        cr = n.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        for i, (p, c) in enumerate(stops):
            e = cr.elements[0] if i == 0 else cr.elements.new(p)
            e.position = p
            e.color = tuple(c) + ((1.0,) if len(c) == 3 else ())
        if _sock(fac):
            self.link(fac, n.inputs[0])
        else:
            n.inputs[0].default_value = fac
        return n.outputs[0]

    def mixc(self, fac, a, b, blend='MIX'):
        n = self.nt.nodes.new('ShaderNodeMix')
        n.data_type = 'RGBA'
        n.blend_type = blend
        ins = {s.identifier: s for s in n.inputs}
        for key, v in (('Factor_Float', fac), ('A_Color', a), ('B_Color', b)):
            s = ins[key]
            if _sock(v):
                self.link(v, s)
            else:
                s.default_value = (tuple(v) + (1.0,)) if isinstance(v, (tuple, list)) and len(v) == 3 else v
        return [s for s in n.outputs if s.identifier == 'Result_Color'][0]

    def mixs(self, fac, a, b):
        n = self.nt.nodes.new('ShaderNodeMixShader')
        if _sock(fac):
            self.link(fac, n.inputs[0])
        else:
            n.inputs[0].default_value = fac
        self.link(a, n.inputs[1])
        self.link(b, n.inputs[2])
        return n.outputs[0]

    def adds(self, a, b):
        n = self.nt.nodes.new('ShaderNodeAddShader')
        self.link(a, n.inputs[0])
        self.link(b, n.inputs[1])
        return n.outputs[0]

    def bump(self, height, strength=0.2, distance=0.1, normal=None):
        n = self.node('ShaderNodeBump', {'Strength': strength, 'Distance': distance, 'Height': height})
        if normal is not None:
            self.link(normal, n.inputs['Normal'])
        return n.outputs[0]

    def bsdf(self, base, rough=0.5, metal=0.0, **kw):
        n = self.node('ShaderNodeBsdfPrincipled')
        names = {'spec': 'Specular IOR Level', 'coat': 'Coat Weight', 'coat_rough': 'Coat Roughness',
                 'trans': 'Transmission Weight', 'ior': 'IOR', 'normal': 'Normal', 'alpha': 'Alpha',
                 'sss': 'Subsurface Weight', 'sss_radius': 'Subsurface Radius', 'sss_scale': 'Subsurface Scale',
                 'emit': 'Emission Color', 'emit_s': 'Emission Strength', 'film': 'Thin Film Thickness',
                 'film_ior': 'Thin Film IOR', 'sheen': 'Sheen Weight', 'sheen_tint': 'Sheen Tint',
                 'aniso': 'Anisotropic', 'coat_normal': 'Coat Normal', 'thin_wall': 'Thin Wall'}
        vals = {'Base Color': base, 'Roughness': rough, 'Metallic': metal}
        for k, v in kw.items():
            vals[names.get(k, k)] = v
        for k, v in vals.items():
            s = n.inputs[k]
            if _sock(v):
                self.link(v, s)
            else:
                if isinstance(v, (tuple, list)) and len(v) == 3 and s.type == 'RGBA':
                    v = tuple(v) + (1.0,)
                s.default_value = v
        return n.outputs[0]

    def sh(self, kind, **inp):
        n = self.node(kind)
        for k, v in inp.items():
            s = n.inputs[k]
            if _sock(v):
                self.link(v, s)
            else:
                if isinstance(v, (tuple, list)) and len(v) == 3 and s.type == 'RGBA':
                    v = tuple(v) + (1.0,)
                s.default_value = v
        return n.outputs[0]

    def out(self, surface=None, volume=None):
        o = self.node('ShaderNodeOutputMaterial')
        if surface is not None:
            self.link(surface, o.inputs['Surface'])
        if volume is not None:
            self.link(volume, o.inputs['Volume'])
        return o

    def emission(self, name, color, day, night):
        n = self.node('ShaderNodeEmission', {'Color': tuple(color) + (1.0,), 'Strength': day})
        n.label = f'EMIT:{day}:{night}'      # persisted in the .blend for day/night switching
        EMITTERS[name] = (n, day, night)
        return n.outputs[0]


def _new(name):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    return m, G(m)


def set_lighting_mode(mode):
    """mode: 'day' or 'night' -> set every emitter tagged EMIT:<day>:<night>."""
    for mat in bpy.data.materials:
        if not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.label.startswith('EMIT:'):
                _, day, night = node.label.split(':')
                node.inputs['Strength'].default_value = float(night if mode == 'night' else day)


# ==========================================================================
# Leaf atlas (procedural bitmap)
# ==========================================================================
def leaf_atlas(name='leaf_atlas', size=512, n_leaves=26, seed=3, shape='broad'):
    """Paint a cluster of leaves into an RGBA image (alpha-tested leaf card)."""
    rs = np.random.RandomState(seed)
    H = W = size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32) / size
    rgb = np.zeros((H, W, 3), np.float32)
    a = np.zeros((H, W), np.float32)
    for i in range(n_leaves):
        cx, cy = rs.uniform(0.18, 0.82, 2)
        ang = rs.uniform(0, math.tau)
        if shape == 'needle':
            ln, wd = rs.uniform(0.10, 0.18), rs.uniform(0.012, 0.02)
        elif shape == 'fan':        # ginkgo-like
            ln, wd = rs.uniform(0.09, 0.13), rs.uniform(0.07, 0.10)
        elif shape == 'narrow':     # willow / bamboo
            ln, wd = rs.uniform(0.16, 0.26), rs.uniform(0.022, 0.035)
        else:
            ln, wd = rs.uniform(0.10, 0.17), rs.uniform(0.04, 0.065)
        dx, dy = xx - cx, yy - cy
        u = dx * math.cos(ang) + dy * math.sin(ang)
        v = -dx * math.sin(ang) + dy * math.cos(ang)
        t = u / ln                      # -1..1 along leaf
        prof = np.clip(1 - t ** 2, 0, 1) ** (0.6 if shape != 'fan' else 0.35) * wd
        if shape == 'fan':
            prof = np.where(t > 0, wd * np.clip(1 - (1 - t) ** 2, 0, 1) ** 0.5 * (t > 0), prof * 0.15)
        inside = (np.abs(v) < prof) & (np.abs(t) < 1)
        shade = 0.75 + 0.25 * rs.rand()
        vein = np.exp(-(v / (wd * 0.08 + 1e-4)) ** 2) * 0.18
        side = 0.85 + 0.15 * np.sign(v)
        col = np.stack([0.30, 0.42, 0.16]) * shade
        leafc = col[None, None, :] * (side * (1 - vein) * (0.85 + 0.15 * t))[..., None]
        m = inside & (a < 0.5)
        rgb[m] = leafc[m]
        a[m] = 1.0
    # stems
    img = np.dstack([rgb, a])
    im = bpy.data.images.new(name, W, H, alpha=True, float_buffer=False)
    im.pixels.foreach_set(img[::-1].reshape(-1).astype(np.float32))
    im.pack()
    im.colorspace_settings.name = 'sRGB'
    return im


def _concrete_shader(g):
    co = g.tc.outputs['Object']
    n1 = g.noise(co, 0.012, 3)
    n2 = g.noise(co, 0.6, 8)
    base = g.mixc(n1.outputs['Fac'], (0.38, 0.375, 0.355), (0.50, 0.49, 0.46))
    base = g.mixc(0.25, base, n2.outputs['Color'], 'OVERLAY')
    x, y, z = g.sep(co)
    jx = g.m('ABSOLUTE', g.m('SUBTRACT', g.m('FRACT', g.m('DIVIDE', x, 7.5)), 0.5))
    jy = g.m('ABSOLUTE', g.m('SUBTRACT', g.m('FRACT', g.m('DIVIDE', y, 7.5)), 0.5))
    joint = g.m('GREATER_THAN', g.m('MAXIMUM', jx, jy), 0.488)
    base = g.mixc(g.m('MULTIPLY', joint, 0.45), base, (0.18, 0.18, 0.17))
    stain = g.noise(co, 0.05, 6, 0.6)
    base = g.mixc(g.m('MULTIPLY', g.ramp(stain.outputs['Fac'], [(0.55, (0, 0, 0)), (0.75, (1, 1, 1))]), 0.25),
                  base, (0.25, 0.24, 0.22))
    return (g.bsdf(base, 0.78, normal=g.bump(n2.outputs['Fac'], 0.05, 0.05)))




def _grass_shader(g):
    co = g.tc.outputs['Object']
    n1 = g.noise(co, 0.003, 4)
    n2 = g.noise(co, 0.03, 6)
    n3 = g.noise(co, 1.5, 8)
    x, y, z = g.sep(co)
    stripes = g.m('MULTIPLY', g.m('SINE', g.m('MULTIPLY', g.m('ADD', x, g.m('MULTIPLY', y, 0.3)), 0.21)), 0.5)
    base = g.mixc(n1.outputs['Fac'], (0.055, 0.12, 0.03), (0.12, 0.19, 0.05))
    base = g.mixc(g.m('MULTIPLY', n2.outputs['Fac'], 0.35), base, (0.20, 0.22, 0.08))
    base = g.mixc(g.m('MULTIPLY', g.m('ADD', stripes, 0.5), 0.18), base, (0.13, 0.22, 0.06))
    return (g.bsdf(base, 0.92, spec=0.3, normal=g.bump(n3.outputs['Fac'], 0.15, 0.1)))




# ==========================================================================
# Library
# ==========================================================================
def build_library():
    M = {}

    # ---------------- ground & paving -------------------------------------
    m, g = _new('concrete_apron')
    g.out(_concrete_shader(g))
    M['concrete'] = m

    m, g = _new('asphalt')
    co = g.tc.outputs['Object']
    n1 = g.noise(co, 0.02, 3)
    n2 = g.noise(co, 2.0, 6)
    base = g.mixc(n1.outputs['Fac'], (0.035, 0.036, 0.04), (0.075, 0.075, 0.078))
    g.out(g.bsdf(base, 0.86, normal=g.bump(n2.outputs['Fac'], 0.08, 0.05)))
    M['asphalt'] = m

    for nm, col, r in (('paint_white', (0.78, 0.78, 0.76), 0.6), ('paint_yellow', (0.85, 0.55, 0.04), 0.6),
                       ('paint_red', (0.6, 0.05, 0.04), 0.6), ('paint_green', (0.05, 0.35, 0.18), 0.6)):
        m, g = _new(nm)
        g.out(g.bsdf(col, r))
        M[nm] = m

    m, g = _new('grass_airside')
    g.out(_grass_shader(g))
    M['grass'] = m

    m, g = _new('landscape_far')      # farmland mosaic + forest patches (delta plain)
    co = g.tc.outputs['Object']
    x, y, z = g.sep(co)
    # slightly rotated field grid with jittered strip widths
    xr = g.m('ADD', g.m('MULTIPLY', x, 0.966), g.m('MULTIPLY', y, 0.259))
    yr = g.m('SUBTRACT', g.m('MULTIPLY', y, 0.966), g.m('MULTIPLY', x, 0.259))
    big = g.noise(co, 0.00025, 2)
    cell = g.comb(g.m('FLOOR', g.m('DIVIDE', xr, 140.0)), g.m('FLOOR', g.m('DIVIDE', yr, 46.0)), 0.0)
    wn = g.node('ShaderNodeTexWhiteNoise', {'Vector': cell}, noise_dimensions='3D')
    fields = g.ramp(wn.outputs['Value'],
                    [(0.0, (0.07, 0.14, 0.04)), (0.18, (0.12, 0.18, 0.05)), (0.34, (0.30, 0.25, 0.11)),
                     (0.50, (0.10, 0.17, 0.05)), (0.64, (0.08, 0.15, 0.045)), (0.78, (0.34, 0.28, 0.13)),
                     (0.90, (0.06, 0.12, 0.04))], 'CONSTANT')
    # hedgerows / field margins
    fxr = g.m('ABSOLUTE', g.m('SUBTRACT', g.m('FRACT', g.m('DIVIDE', xr, 140.0)), 0.5))
    fyr = g.m('ABSOLUTE', g.m('SUBTRACT', g.m('FRACT', g.m('DIVIDE', yr, 46.0)), 0.5))
    hedge = g.m('MAXIMUM', g.m('GREATER_THAN', fxr, 0.485), g.m('GREATER_THAN', fyr, 0.47))
    fields = g.mixc(g.m('MULTIPLY', hedge, 0.8), fields, (0.04, 0.07, 0.03))
    # forest / village patches at large scale
    patch = g.ramp(big.outputs['Fac'], [(0.55, (0, 0, 0)), (0.62, (1, 1, 1))])
    fields = g.mixc(g.sep(patch)[0], fields, (0.035, 0.06, 0.025))
    n2 = g.noise(co, 0.02, 6)
    base = g.mixc(0.3, fields, n2.outputs['Color'], 'OVERLAY')
    g.out(g.bsdf(base, 0.95, spec=0.25))
    M['landscape'] = m

    m, g = _new('mountain')
    co = g.tc.outputs['Object']
    x, y, z = g.sep(co)
    n = g.noise(co, 0.004, 8, 0.6)
    hz = g.m('DIVIDE', z, 900.0, clamp=True)
    base = g.mixc(n.outputs['Fac'], (0.03, 0.055, 0.03), (0.07, 0.09, 0.05))
    base = g.mixc(g.m('MULTIPLY', hz, 0.6), base, (0.16, 0.15, 0.13))
    g.out(g.bsdf(base, 0.9, spec=0.2))
    M['mountain'] = m

    m, g = _new('soil')
    co = g.tc.outputs['Object']
    n = g.noise(co, 0.5, 6)
    g.out(g.bsdf(g.mixc(n.outputs['Fac'], (0.12, 0.09, 0.06), (0.2, 0.15, 0.1)), 0.95))
    M['soil'] = m

    m, g = _new('gravel_path')
    co = g.tc.outputs['Object']
    n = g.noise(co, 3.0, 6)
    g.out(g.bsdf(g.mixc(n.outputs['Fac'], (0.5, 0.46, 0.4), (0.68, 0.64, 0.56)), 0.85))
    M['path'] = m

    # ---------------- water -------------------------------------------------
    m, g = _new('water_lake')
    co = g.tc.outputs['Object']
    w1 = g.noise(g.vm('MULTIPLY', co, (1.0, 2.2, 1.0)), 0.08, 5, 0.55)
    w2 = g.noise(co, 0.9, 4, 0.5)
    h = g.m('ADD', w1.outputs['Fac'], g.m('MULTIPLY', w2.outputs['Fac'], 0.25))
    g.out(g.bsdf((0.010, 0.030, 0.034), 0.02, ior=1.333, spec=0.5, normal=g.bump(h, 0.05, 0.2)))
    M['water_lake'] = m

    m, g = _new('water_clear')     # pools / channels; shadow-transparent
    co = g.tc.outputs['Object']
    w = g.noise(co, 0.7, 5)
    surf = g.bsdf((0.75, 0.92, 0.88), 0.02, ior=1.333, trans=1.0, normal=g.bump(w.outputs['Fac'], 0.08, 0.1))
    lp = g.node('ShaderNodeLightPath')
    tr = g.sh('ShaderNodeBsdfTransparent', Color=(0.85, 0.96, 0.94))
    g.out(g.mixs(lp.outputs['Is Shadow Ray'], surf, tr))
    M['water_clear'] = m

    m, g = _new('waterfall')
    uv = g.tc.outputs['UV']
    u, v, _ = g.sep(uv)
    p = g.comb(g.m('MULTIPLY', u, 1.6), g.m('MULTIPLY', v, 0.03), 0.0)
    s1 = g.noise(p, 3.0, 8, 0.62, distortion=0.25)
    p2 = g.comb(g.m('MULTIPLY', u, 0.25), g.m('MULTIPLY', v, 0.012), 7.3)
    s2 = g.noise(p2, 2.0, 3, 0.5)
    fac = g.m('ADD', g.m('MULTIPLY', s1.outputs['Fac'], 0.75), g.m('MULTIPLY', s2.outputs['Fac'], 0.35))
    aer = g.m('MULTIPLY', g.m('SUBTRACT', 1.0, g.m('DIVIDE', g.m('ADD', v, 22.0), 60.0), clamp=True), 0.16)
    fac = g.m('ADD', fac, aer)
    foam = g.ramp(fac, [(0.60, (0, 0, 0)), (0.70, (1, 1, 1))])
    white = g.mixs(0.45, g.sh('ShaderNodeBsdfTranslucent', Color=(0.85, 0.9, 0.92)),
                   g.sh('ShaderNodeBsdfDiffuse', Color=(0.82, 0.86, 0.88)))
    white = g.adds(white, g.sh('ShaderNodeBsdfGlossy', Color=(0.12, 0.12, 0.12), Roughness=0.15))
    lw = g.node('ShaderNodeLayerWeight', {'Blend': 0.2})
    clear = g.mixs(lw.outputs['Fresnel'], g.sh('ShaderNodeBsdfTransparent', Color=(0.9, 0.97, 0.97)),
                   g.sh('ShaderNodeBsdfGlossy', Color=(1, 1, 1), Roughness=0.04))
    g.out(g.mixs(g.sep(foam)[0], clear, white))
    M['waterfall'] = m

    m, g = _new('cascade_thin')
    u, v, _ = g.sep(g.tc.outputs['UV'])
    s1 = g.noise(g.comb(g.m('MULTIPLY', u, 2.2), g.m('MULTIPLY', v, 0.25), 0.0), 3.0, 8, 0.62, distortion=0.3)
    foam = g.ramp(s1.outputs['Fac'], [(0.52, (0, 0, 0)), (0.62, (1, 1, 1))])
    white = g.mixs(0.5, g.sh('ShaderNodeBsdfTranslucent', Color=(0.85, 0.9, 0.92)),
                   g.sh('ShaderNodeBsdfDiffuse', Color=(0.82, 0.86, 0.88)))
    lw = g.node('ShaderNodeLayerWeight', {'Blend': 0.25})
    clear = g.mixs(lw.outputs['Fresnel'], g.sh('ShaderNodeBsdfTransparent', Color=(0.92, 0.98, 0.98)),
                   g.sh('ShaderNodeBsdfGlossy', Color=(1, 1, 1), Roughness=0.03))
    g.out(g.mixs(g.sep(foam)[0], clear, white))
    M['cascade_thin'] = m

    m, g = _new('mist')
    vol = g.node('ShaderNodeVolumePrincipled', {'Color': (0.9, 0.95, 1.0, 1), 'Density': 0.035, 'Anisotropy': 0.35})
    # fade density towards the top of the bounding object (Generated z)
    gz = g.sep(g.tc.outputs['Generated'])[2]
    dens = g.m('MULTIPLY', g.m('POWER', g.m('SUBTRACT', 1.0, gz, clamp=True), 2.0), 0.05)
    g.link(dens, vol.inputs['Density'])
    g.out(volume=vol.outputs[0])
    M['mist'] = m

    # ---------------- glass & metal ---------------------------------------
    def thin_glass(name, tint, refl_blend, rough=0.015):
        m, g = _new(name)
        lw = g.node('ShaderNodeLayerWeight', {'Blend': refl_blend})
        s = g.mixs(lw.outputs['Fresnel'], g.sh('ShaderNodeBsdfTransparent', Color=tint),
                   g.sh('ShaderNodeBsdfGlossy', Color=(1, 1, 1), Roughness=rough))
        g.out(s)
        return m
    M['glass'] = thin_glass('glass_clear', (0.86, 0.93, 0.92), 0.12)
    M['glass_low'] = thin_glass('glass_lowiron', (0.93, 0.97, 0.96), 0.08)

    m, g = _new('glass_facade')
    u, v, _ = g.sep(g.tc.outputs['UV'])
    fu = g.m('FRACT', g.m('DIVIDE', u, 3.0))
    fv = g.m('FRACT', g.m('DIVIDE', v, 4.5))
    mull = g.m('MAXIMUM', g.m('LESS_THAN', fu, 0.045), g.m('LESS_THAN', fv, 0.035))
    lw = g.node('ShaderNodeLayerWeight', {'Blend': 0.22})
    glass = g.mixs(lw.outputs['Fresnel'], g.sh('ShaderNodeBsdfTransparent', Color=(0.80, 0.90, 0.90)),
                   g.sh('ShaderNodeBsdfGlossy', Color=(0.95, 0.97, 1.0), Roughness=0.02))
    frame = g.bsdf((0.16, 0.17, 0.18), 0.35, 1.0)
    g.out(g.mixs(mull, glass, frame))
    M['facade'] = m

    m, g = _new('steel_white')
    g.out(g.bsdf((0.84, 0.84, 0.82), 0.32, 0.0, coat=0.25, coat_rough=0.2))
    M['steel'] = m

    m, g = _new('metal_dark')
    g.out(g.bsdf((0.07, 0.075, 0.08), 0.35, 1.0))
    M['metal_dark'] = m

    m, g = _new('champagne')
    g.out(g.bsdf((0.80, 0.66, 0.47), 0.24, 1.0))
    M['champagne'] = m

    m, g = _new('bronze_caps')
    g.out(g.bsdf((0.80, 0.73, 0.62), 0.26, 0.65, coat=0.3, coat_rough=0.1))
    M['bronze'] = m

    m, g = _new('aluminium')
    g.out(g.bsdf((0.78, 0.79, 0.80), 0.3, 1.0))
    M['aluminium'] = m

    m, g = _new('concrete_light')
    co = g.tc.outputs['Object']
    n = g.noise(co, 1.2, 6)
    g.out(g.bsdf(g.mixc(n.outputs['Fac'], (0.62, 0.61, 0.58), (0.75, 0.74, 0.71)), 0.7,
                 normal=g.bump(n.outputs['Fac'], 0.05, 0.05)))
    M['concrete_light'] = m

    m, g = _new('stone_wall')       # terrace retaining walls: stratified stone
    co = g.tc.outputs['Object']
    x, y, z = g.sep(co)
    strata = g.noise(g.comb(g.m('MULTIPLY', x, 0.05), g.m('MULTIPLY', y, 0.05), g.m('MULTIPLY', z, 2.2)), 1.0, 6, 0.6)
    n2 = g.noise(co, 1.6, 6)
    base = g.mixc(strata.outputs['Fac'], (0.36, 0.33, 0.29), (0.56, 0.51, 0.44))
    base = g.mixc(0.3, base, n2.outputs['Color'], 'OVERLAY')
    g.out(g.bsdf(base, 0.82, normal=g.bump(g.m('ADD', strata.outputs['Fac'], n2.outputs['Fac']), 0.3, 0.2)))
    M['stone'] = m

    m, g = _new('stone_vines')       # terrace walls with cascading planting
    co = g.tc.outputs['Object']
    x, y, z = g.sep(co)
    strata = g.noise(g.comb(g.m('MULTIPLY', x, 0.05), g.m('MULTIPLY', y, 0.05), g.m('MULTIPLY', z, 2.2)), 1.0, 6, 0.6)
    stone = g.mixc(strata.outputs['Fac'], (0.24, 0.22, 0.19), (0.38, 0.35, 0.30))
    fz = g.m('FRACT', g.m('DIVIDE', z, 2.7))                       # 0 at foot .. 1 at lip
    vn = g.noise(g.comb(g.m('MULTIPLY', x, 0.9), g.m('MULTIPLY', y, 0.9), g.m('MULTIPLY', z, 0.15)), 1.0, 6, 0.6)
    hang = g.m('SUBTRACT', g.m('ADD', fz, g.m('MULTIPLY', vn.outputs['Fac'], 1.1)), 0.62)
    vines = g.m('GREATER_THAN', hang, 0.0)
    leafc = g.mixc(vn.outputs['Fac'], (0.05, 0.12, 0.03), (0.16, 0.24, 0.05))
    leafc = g.mixc(g.m('GREATER_THAN', g.noise(co, 0.6, 3).outputs['Fac'], 0.66), leafc, (0.55, 0.12, 0.08))
    base = g.mixc(vines, stone, leafc)
    g.out(g.bsdf(base, 0.85, normal=g.bump(g.m('ADD', strata.outputs['Fac'], g.m('MULTIPLY', vines, vn.outputs['Fac'])), 0.4, 0.2)))
    M['stone_green'] = m

    m, g = _new('terrazzo')
    co = g.tc.outputs['Object']
    vor = g.voronoi(co, 9.0)
    speck = g.ramp(vor.outputs['Distance'], [(0.0, (0.3, 0.3, 0.3)), (0.08, (1, 1, 1))])
    base = g.mixc(0.5, (0.80, 0.78, 0.74), speck, 'MULTIPLY')
    n = g.noise(co, 0.08, 3)
    base = g.mixc(g.m('MULTIPLY', n.outputs['Fac'], 0.3), base, (0.70, 0.66, 0.60))
    g.out(g.bsdf(base, 0.32, coat=0.08, coat_rough=0.15))
    M['terrazzo'] = m

    m, g = _new('timber')
    co = g.tc.outputs['Object']
    x, y, z = g.sep(co)
    grain = g.noise(g.comb(g.m('MULTIPLY', x, 0.2), g.m('MULTIPLY', y, 0.2), g.m('MULTIPLY', z, 6.0)), 2.0, 6, 0.6)
    base = g.mixc(grain.outputs['Fac'], (0.42, 0.26, 0.13), (0.62, 0.42, 0.23))
    g.out(g.bsdf(base, 0.45, coat=0.2))
    M['timber'] = m

    # ---------------- photovoltaics ---------------------------------------
    def pv_cell_shader(g, cell_fac=None):
        n = g.noise(g.tc.outputs['Object'], 0.15, 2)
        base = g.mixc(n.outputs['Fac'], (0.006, 0.012, 0.035), (0.016, 0.03, 0.07))
        return g.bsdf(base, 0.16, 0.0, coat=1.0, coat_rough=0.025, film=420.0, film_ior=1.9, spec=0.6)

    # semi-transparent BIPV laminate for the hub roof: cells in world XY grid
    m, g = _new('pv_bipv')
    x, y, z = g.sep(g.tc.outputs['Object'])
    fx = g.m('FRACT', g.m('DIVIDE', x, 0.62))
    fy = g.m('FRACT', g.m('DIVIDE', y, 0.62))
    gap = g.m('MAXIMUM', g.m('GREATER_THAN', fx, 0.915), g.m('GREATER_THAN', fy, 0.915))
    lw = g.node('ShaderNodeLayerWeight', {'Blend': 0.12})
    glass = g.mixs(lw.outputs['Fresnel'], g.sh('ShaderNodeBsdfTransparent', Color=(0.85, 0.92, 0.9)),
                   g.sh('ShaderNodeBsdfGlossy', Color=(1, 1, 1), Roughness=0.02))
    g.out(g.mixs(gap, pv_cell_shader(g), glass))
    M['pv_bipv'] = m

    # pier roof: opaque PV with leaf-vein skylights (UV in metres: u=along, v=across)
    m, g = _new('pv_pier')
    u, v, _ = g.sep(g.tc.outputs['UV'])
    av = g.m('ABSOLUTE', v)
    mid = g.m('LESS_THAN', av, 2.6)
    herr = g.m('LESS_THAN', g.m('FRACT', g.m('DIVIDE', g.m('SUBTRACT', u, g.m('MULTIPLY', av, 1.15)), 34.0)), 0.055)
    herr = g.m('MULTIPLY', herr, g.m('LESS_THAN', av, 23.0))
    vein = g.m('MAXIMUM', mid, herr)
    fu = g.m('FRACT', g.m('DIVIDE', u, 2.1))
    fv = g.m('FRACT', g.m('DIVIDE', v, 1.15))
    frame = g.m('MAXIMUM', g.m('LESS_THAN', fu, 0.03), g.m('LESS_THAN', fv, 0.04))
    pv = g.mixs(frame, pv_cell_shader(g), g.bsdf((0.55, 0.56, 0.58), 0.3, 1.0))
    lw = g.node('ShaderNodeLayerWeight', {'Blend': 0.15})
    sky = g.mixs(lw.outputs['Fresnel'], g.sh('ShaderNodeBsdfTransparent', Color=(0.88, 0.95, 0.93)),
                 g.sh('ShaderNodeBsdfGlossy', Color=(1, 1, 1), Roughness=0.02))
    g.out(g.mixs(vein, pv, sky))
    M['pv_pier'] = m

    m, g = _new('pv_field')
    u, v, _ = g.sep(g.tc.outputs['UV'])
    fu = g.m('FRACT', g.m('DIVIDE', u, 1.13))
    fv = g.m('FRACT', g.m('DIVIDE', v, 2.28))
    frame = g.m('MAXIMUM', g.m('LESS_THAN', fu, 0.03), g.m('LESS_THAN', fv, 0.025))
    g.out(g.mixs(frame, pv_cell_shader(g), g.bsdf((0.6, 0.6, 0.62), 0.3, 1.0)))
    M['pv_field'] = m

    # ---------------- vegetation -------------------------------------------
    m, g = _new('bark')
    co = g.tc.outputs['Object']
    n = g.noise(g.vm('MULTIPLY', co, (3, 3, 0.4)), 4.0, 6)
    g.out(g.bsdf(g.mixc(n.outputs['Fac'], (0.07, 0.055, 0.045), (0.2, 0.16, 0.12)), 0.9,
                 normal=g.bump(n.outputs['Fac'], 0.4, 0.05)))
    M['bark'] = m

    atlases = {
        'broad': leaf_atlas('leaf_broad', shape='broad', seed=3),
        'fan': leaf_atlas('leaf_fan', shape='fan', seed=5, n_leaves=30),
        'narrow': leaf_atlas('leaf_narrow', shape='narrow', seed=7, n_leaves=34),
        'needle': leaf_atlas('leaf_needle', shape='needle', seed=9, n_leaves=60),
    }

    def foliage(name, atlas, c0, c1, c_var=None, trans=0.35):
        m, g = _new(name)
        im = g.node('ShaderNodeTexImage', image=atlases[atlas], interpolation='Linear')
        g.link(g.tc.outputs['UV'], im.inputs['Vector'])
        oi = g.node('ShaderNodeObjectInfo')
        r = oi.outputs['Random']
        n = g.noise(g.tc.outputs['Object'], 0.35, 2)
        tone = g.mixc(g.m('ADD', g.m('MULTIPLY', r, 0.7), g.m('MULTIPLY', n.outputs['Fac'], 0.3)), c0, c1)
        if c_var is not None:
            tone = g.mixc(g.m('MULTIPLY', g.m('GREATER_THAN', r, 0.82), 0.85), tone, c_var)
        col = g.mixc(1.0, im.outputs['Color'], tone, 'MULTIPLY')
        col = g.mixc(1.0, col, (3.4, 3.4, 3.4), 'MULTIPLY')
        diff = g.bsdf(col, 0.55, spec=0.35, sheen=0.2)
        tr = g.sh('ShaderNodeBsdfTranslucent', Color=col)
        leaf = g.mixs(trans, diff, tr)
        alpha = g.m('GREATER_THAN', im.outputs['Alpha'], 0.5)
        g.out(g.mixs(alpha, g.sh('ShaderNodeBsdfTransparent', Color=(1, 1, 1)), leaf))
        return m

    M['leaf_camphor'] = foliage('leaf_camphor', 'broad', (0.20, 0.33, 0.09), (0.12, 0.25, 0.07), (0.45, 0.42, 0.10))
    M['leaf_ginkgo'] = foliage('leaf_ginkgo', 'fan', (0.95, 0.62, 0.06), (0.75, 0.48, 0.05), (0.45, 0.45, 0.08))
    M['leaf_maple'] = foliage('leaf_maple', 'broad', (0.72, 0.12, 0.04), (0.85, 0.30, 0.05), (0.85, 0.55, 0.08))
    M['leaf_blossom'] = foliage('leaf_blossom', 'broad', (0.95, 0.52, 0.62), (0.85, 0.30, 0.45), (0.95, 0.85, 0.85))
    M['leaf_willow'] = foliage('leaf_willow', 'narrow', (0.32, 0.45, 0.10), (0.42, 0.50, 0.14), None, 0.45)
    M['leaf_pine'] = foliage('leaf_pine', 'needle', (0.07, 0.17, 0.07), (0.10, 0.22, 0.08), None, 0.2)
    M['leaf_bamboo'] = foliage('leaf_bamboo', 'narrow', (0.25, 0.42, 0.09), (0.18, 0.35, 0.06), None, 0.45)
    M['leaf_shrub'] = foliage('leaf_shrub', 'broad', (0.12, 0.24, 0.06), (0.18, 0.30, 0.07), (0.85, 0.25, 0.45))

    m, g = _new('bamboo_cane')
    g.out(g.bsdf((0.33, 0.42, 0.12), 0.35, coat=0.3))
    M['bamboo_cane'] = m

    m, g = _new('planting_terrace')   # rice / meadow terrace beds, autumn mix
    co = g.tc.outputs['Object']
    n1 = g.noise(co, 0.02, 4)
    n2 = g.noise(co, 0.25, 6)
    n3 = g.noise(co, 3.0, 6)
    base = g.ramp(g.m('ADD', g.m('MULTIPLY', n1.outputs['Fac'], 0.7), g.m('MULTIPLY', n2.outputs['Fac'], 0.3)),
                  [(0.30, (0.06, 0.15, 0.03)), (0.48, (0.16, 0.27, 0.05)), (0.58, (0.46, 0.33, 0.07)),
                   (0.70, (0.14, 0.25, 0.05)), (0.80, (0.55, 0.16, 0.24))])
    base = g.mixc(0.35, base, n3.outputs['Color'], 'OVERLAY')
    g.out(g.bsdf(base, 0.8, spec=0.35, sheen=0.5, sheen_tint=(0.9, 1, 0.8),
                 normal=g.bump(n3.outputs['Fac'], 0.6, 0.1)))
    M['planting'] = m

    # ---------------- aircraft ---------------------------------------------
    def aircraft_paint(name, L, R, zc):
        m, g = _new(name)
        x, y, z0 = g.sep(g.tc.outputs['Object'])
        z = g.m('SUBTRACT', z0, zc)
        xn = g.m('DIVIDE', g.m('MULTIPLY', x, -1.0), L)        # 0 nose .. 1 tail
        win = g.m('MULTIPLY', g.m('LESS_THAN', g.m('ABSOLUTE', g.m('SUBTRACT', z, R * 0.28)), R * 0.075),
                  g.m('LESS_THAN', g.m('FRACT', g.m('DIVIDE', x, 0.53)), 0.55))
        win = g.m('MULTIPLY', win, g.m('MULTIPLY', g.m('GREATER_THAN', xn, 0.11), g.m('LESS_THAN', xn, 0.80)))
        cock = g.m('MULTIPLY', g.m('LESS_THAN', g.m('ABSOLUTE', g.m('SUBTRACT', z, R * 0.42)), R * 0.10),
                   g.m('MULTIPLY', g.m('GREATER_THAN', xn, 0.025), g.m('LESS_THAN', xn, 0.05)))
        win = g.m('MAXIMUM', win, cock)
        # jade sweep on the rear fuselage + fin, gold pin-stripe
        sweep = g.m('ADD', xn, g.m('DIVIDE', z, L * 0.9))
        jade = g.m('GREATER_THAN', sweep, 0.86)
        stripe = g.m('LESS_THAN', g.m('ABSOLUTE', g.m('SUBTRACT', sweep, 0.845)), 0.006)
        belly = g.m('LESS_THAN', z, -R * 0.55)
        col = g.mixc(belly, (0.86, 0.87, 0.88), (0.62, 0.64, 0.66))
        col = g.mixc(jade, col, (0.0, 0.30, 0.25))
        col = g.mixc(stripe, col, (0.85, 0.62, 0.25))
        paint = g.bsdf(col, 0.22, coat=0.6, coat_rough=0.05)
        glassy = g.bsdf((0.01, 0.012, 0.015), 0.05, coat=1.0)
        g.out(g.mixs(win, paint, glassy))
        return m
    M['ac_wide'] = aircraft_paint('aircraft_wide', 66.0, 3.0, 6.1)
    M['ac_narrow'] = aircraft_paint('aircraft_narrow', 39.0, 2.0, 4.0)

    m, g = _new('aircraft_wing')
    g.out(g.bsdf((0.70, 0.72, 0.74), 0.3, 0.2, coat=0.3))
    M['ac_wing'] = m

    m, g = _new('engine_metal')
    g.out(g.bsdf((0.55, 0.56, 0.58), 0.28, 1.0))
    M['engine'] = m

    m, g = _new('rubber')
    g.out(g.bsdf((0.02, 0.02, 0.02), 0.7))
    M['rubber'] = m

    m, g = _new('glass_dark')
    g.out(g.bsdf((0.01, 0.012, 0.015), 0.04, coat=1.0))
    M['glass_dark'] = m

    # ---------------- vehicles / people -------------------------------------
    m, g = _new('car_paint')
    oi = g.node('ShaderNodeObjectInfo')
    col = g.ramp(oi.outputs['Random'],
                 [(0.0, (0.85, 0.85, 0.85)), (0.30, (0.55, 0.56, 0.58)), (0.48, (0.02, 0.02, 0.025)),
                  (0.62, (0.06, 0.12, 0.25)), (0.74, (0.55, 0.03, 0.03)), (0.84, (0.85, 0.85, 0.85)),
                  (0.93, (0.05, 0.25, 0.22))], 'CONSTANT')
    g.out(g.bsdf(col, 0.25, 0.4, coat=1.0, coat_rough=0.03))
    M['car'] = m

    m, g = _new('people')
    oi = g.node('ShaderNodeObjectInfo')
    col = g.ramp(oi.outputs['Random'],
                 [(0.0, (0.8, 0.78, 0.74)), (0.2, (0.05, 0.05, 0.06)), (0.35, (0.12, 0.18, 0.35)),
                  (0.5, (0.55, 0.12, 0.08)), (0.6, (0.75, 0.6, 0.4)), (0.72, (0.2, 0.3, 0.22)),
                  (0.84, (0.85, 0.85, 0.85)), (0.92, (0.6, 0.45, 0.1))], 'CONSTANT')
    g.out(g.bsdf(col, 0.7))
    M['people'] = m

    m, g = _new('skin_hair')
    g.out(g.bsdf((0.25, 0.16, 0.11), 0.6))
    M['skin'] = m

    # ---------------- emitters (day / night strengths) ----------------------
    def emitter(name, color, day, night, glass_mix=False):
        m, g = _new(name)
        e = g.emission(name, color, day, night)
        g.out(e)
        return m
    M['em_interior'] = emitter('em_interior', (1.0, 0.78, 0.55), 0.0, 6.0)
    M['em_cool'] = emitter('em_cool', (0.85, 0.92, 1.0), 0.0, 8.0)
    M['em_runway'] = emitter('em_runway', (1.0, 0.92, 0.75), 0.0, 120.0)
    M['em_taxi_blue'] = emitter('em_taxi_blue', (0.08, 0.25, 1.0), 0.0, 55.0)
    M['em_taxi_green'] = emitter('em_taxi_green', (0.1, 1.0, 0.35), 0.0, 60.0)
    M['em_red'] = emitter('em_red', (1.0, 0.04, 0.02), 0.0, 90.0)
    M['em_head'] = emitter('em_head', (1.0, 0.92, 0.8), 0.0, 60.0)
    M['em_tail'] = emitter('em_tail', (1.0, 0.03, 0.02), 0.0, 40.0)
    M['em_street'] = emitter('em_street', (1.0, 0.75, 0.45), 0.0, 40.0)
    M['em_pool'] = emitter('em_pool', (0.55, 0.9, 1.0), 0.0, 30.0)
    M['em_accent'] = emitter('em_accent', (0.2, 1.0, 0.8), 0.0, 25.0)

    # interior glow behind glass: emissive at night, dim warm diffuse by day
    m, g = _new('interior_soffit')
    e = g.emission('interior_soffit', (1.0, 0.80, 0.58), 0.0, 3.0)
    g.out(g.adds(g.bsdf((0.75, 0.68, 0.58), 0.6), e))
    M['soffit'] = m

    return M
